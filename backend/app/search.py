"""Hybrid Search: BM25 (Elasticsearch) + vector (Milvus, bge-m3), ghép bằng Reciprocal Rank Fusion.

Hai kho dùng chung `chunk_id` (xem pipeline/index.py) nên ghép được theo khoá này.
"""

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal

from elasticsearch import Elasticsearch
from pymilvus import MilvusClient

from app.config import get_settings
from app.embedding import embed_query

Mode = Literal["bm25", "vector", "hybrid"]

# Trường tìm BM25: nội dung + cặp âm tiết + tiêu đề mục (trọng số 2) + tên tài liệu.
BM25_FIELDS = ["text", "text.shingle", "section_title^2", "title"]
SOURCE_FIELDS = [
    "chunk_id", "document_id", "title", "issuing_organization", "section_title", "page_number", "page_end",
    "source_url", "topic", "jurisdiction", "language", "text",
]
_SAFE_VALUE = re.compile(r"^[A-Za-z0-9_\-]+$")


@dataclass
class SearchFilters:
    """Lọc theo metadata; danh sách rỗng = không lọc. Trong một trường là OR, giữa các trường là AND."""

    topic: list[str] = field(default_factory=list)
    jurisdiction: list[str] = field(default_factory=list)
    language: list[str] = field(default_factory=list)
    target_population: list[str] = field(default_factory=list)
    document_id: list[str] = field(default_factory=list)

    def items(self):
        for name in ("topic", "jurisdiction", "language", "target_population", "document_id"):
            values = getattr(self, name)
            if values:
                bad = [v for v in values if not _SAFE_VALUE.match(v)]
                if bad:
                    raise ValueError(f"Giá trị lọc không hợp lệ cho {name}: {bad}")
                yield name, values


@lru_cache
def get_es() -> Elasticsearch:
    return Elasticsearch(get_settings().es_url)


@lru_cache
def get_milvus() -> MilvusClient:
    s = get_settings()
    client = MilvusClient(uri=s.milvus_uri)
    client.load_collection(s.milvus_collection)
    return client


def _es_filters(filters: SearchFilters) -> list[dict]:
    return [{"terms": {name: values}} for name, values in filters.items()]


def _milvus_filter(filters: SearchFilters) -> str:
    parts = []
    for name, values in filters.items():
        quoted = ", ".join(f'"{v}"' for v in values)
        if name == "topic":
            parts.append(f"ARRAY_CONTAINS_ANY(topic, [{quoted}])")
        else:
            parts.append(f"{name} in [{quoted}]")
    return " and ".join(parts)


def bm25_search(query: str, k: int, filters: SearchFilters) -> list[tuple[str, float]]:
    s = get_settings()
    res = get_es().search(
        index=s.es_index, size=k, source=False,
        query={"bool": {"must": [{"multi_match": {"query": query, "fields": BM25_FIELDS}}],
                        "filter": _es_filters(filters)}},
    )
    return [(hit["_id"], hit["_score"]) for hit in res["hits"]["hits"]]


def vector_search(query: str, k: int, filters: SearchFilters) -> list[tuple[str, float]]:
    s = get_settings()
    hits = get_milvus().search(
        s.milvus_collection, data=[embed_query(query)], limit=k, filter=_milvus_filter(filters),
        output_fields=["chunk_id"], search_params={"params": {"ef": max(64, k)}},
    )[0]
    return [(hit["chunk_id"], hit["distance"]) for hit in hits]


def rrf_fuse(rankings: dict[str, list[str]], k: int, weights: dict[str, float] | None = None) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion có trọng số: điểm(d) = Σ_i w_i / (k + hạng_i(d)), hạng tính từ 1 (w mặc định 1).

    Chỉ dùng thứ hạng, không dùng điểm gốc → không cần chuẩn hoá điểm BM25 (0..∞) với cosine (-1..1).
    """
    weights = weights or {}
    scores: dict[str, float] = {}
    for method, ranked_ids in rankings.items():
        w = weights.get(method, 1.0)
        for rank, chunk_id in enumerate(ranked_ids, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + w / (k + rank)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)


def search(query: str, mode: Mode = "hybrid", top_k: int | None = None,
           filters: SearchFilters | None = None, extra_bm25_queries: list[str] | None = None) -> list[dict]:
    """Tìm kiếm theo chế độ; mỗi kết quả kèm nội dung, trích dẫn, điểm và hạng ở từng bên.

    `extra_bm25_queries`: các cách diễn đạt khác của câu hỏi (ví dụ bản dịch tiếng Anh) – BM25 tìm thêm
    với từng câu, mỗi câu là một danh sách xếp hạng riêng khi ghép RRF (bm25_2, bm25_3…). Cần thiết vì
    BM25 so khớp theo từ nên câu hỏi tiếng Việt không khớp được tài liệu tiếng Anh.
    """
    s = get_settings()
    top_k = top_k or s.search_top_k
    filters = filters or SearchFilters()
    candidates = max(s.search_candidates, top_k)

    per_method: dict[str, list[tuple[str, float]]] = {}
    if mode in ("bm25", "hybrid"):
        per_method["bm25"] = bm25_search(query, candidates, filters)
        for i, extra in enumerate(extra_bm25_queries or [], start=2):
            per_method[f"bm25_{i}"] = bm25_search(extra, candidates, filters)
    if mode in ("vector", "hybrid"):
        per_method["vector"] = vector_search(query, candidates, filters)

    if mode == "hybrid" or len(per_method) > 1:
        ranked = rrf_fuse({m: [cid for cid, _ in hits] for m, hits in per_method.items()}, s.rrf_k,
                          {"vector": s.rrf_vector_weight})
    else:
        ranked = per_method[mode]
    ranked = ranked[:top_k]
    if not ranked:
        return []

    docs = get_es().mget(index=s.es_index, ids=[cid for cid, _ in ranked], source_includes=SOURCE_FIELDS)["docs"]
    by_id = {d["_id"]: d["_source"] for d in docs if d.get("found")}
    results = []
    for rank, (chunk_id, score) in enumerate(ranked, start=1):
        detail = {m: {"rank": None, "score": None} for m in per_method}
        for m, hits in per_method.items():
            for i, (cid, sc) in enumerate(hits, start=1):
                if cid == chunk_id:
                    detail[m] = {"rank": i, "score": round(sc, 4)}
                    break
        results.append({"rank": rank, "score": round(score, 6), "methods": detail, **by_id.get(chunk_id, {"chunk_id": chunk_id})})
    return results
