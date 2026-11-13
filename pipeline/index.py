"""Lập chỉ mục các đoạn trong data/processed/chunks.jsonl vào Elasticsearch (BM25) và Milvus (vector bge-m3).

- Hai kho dùng chung `chunk_id` làm khoá → bước RRF ghép được kết quả.
- Mỗi lần chạy xoá và tạo lại index/collection (dữ liệu luôn tái tạo được từ chunks.jsonl).
- Cấu hình đọc từ .env: ES_URL, ES_INDEX, MILVUS_URI, MILVUS_COLLECTION, EMBEDDING_MODEL, EMBEDDING_DIM, HF_HOME.

Cách chạy (từ thư mục gốc dự án, cần Docker đang chạy ES + Milvus):
    .venv/Scripts/python pipeline/index.py                     # lập chỉ mục mọi đoạn
    .venv/Scripts/python pipeline/index.py --approved-only     # chỉ tài liệu đã duyệt (bản chính thức)
    .venv/Scripts/python pipeline/index.py --query "Tiêu chuẩn chẩn đoán tiền đái tháo đường?"   # thử tìm
"""

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")  # phải nạp trước khi import sentence_transformers để HF_HOME có hiệu lực

from elasticsearch import Elasticsearch, helpers  # noqa: E402
from pymilvus import DataType, MilvusClient  # noqa: E402

CHUNKS = ROOT / "data" / "processed" / "chunks.jsonl"
CATALOG = ROOT / "data" / "catalog" / "documents.csv"

ES_URL = os.getenv("ES_URL", "http://localhost:9200")
ES_INDEX = os.getenv("ES_INDEX", "medical_chunks")
MILVUS_URI = os.getenv("MILVUS_URI", "http://localhost:19530")
MILVUS_COLLECTION = os.getenv("MILVUS_COLLECTION", "medical_chunks")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))
MAX_SEQ_LENGTH = 1024  # đoạn dài nhất ~450 từ, đủ chỗ; nhỏ hơn mặc định 8192 để chạy nhanh trên CPU

# Tiếng Việt: tokenizer chuẩn tách theo âm tiết; trường phụ `.shingle` lưu thêm cặp âm tiết liền nhau
# ("huyết áp") để từ ghép được khớp chính xác hơn.
ES_SETTINGS = {
    "number_of_shards": 1,
    "number_of_replicas": 0,
    "analysis": {
        "filter": {
            "bigram": {"type": "shingle", "min_shingle_size": 2, "max_shingle_size": 2, "output_unigrams": False},
        },
        "analyzer": {
            "syllable": {"type": "custom", "tokenizer": "standard", "filter": ["lowercase"]},
            "syllable_bigram": {"type": "custom", "tokenizer": "standard", "filter": ["lowercase", "bigram"]},
        },
    },
}
TEXT_FIELD = {"type": "text", "analyzer": "syllable", "fields": {"shingle": {"type": "text", "analyzer": "syllable_bigram"}}}
ES_MAPPINGS = {
    "properties": {
        "chunk_id": {"type": "keyword"},
        "text": TEXT_FIELD,
        "section_title": TEXT_FIELD,
        "title": TEXT_FIELD,
        "document_id": {"type": "keyword"},
        "organization_id": {"type": "keyword"},
        "issuing_organization": {"type": "keyword"},
        "document_type": {"type": "keyword"},
        "topic": {"type": "keyword"},
        "jurisdiction": {"type": "keyword"},
        "target_population": {"type": "keyword"},
        "language": {"type": "keyword"},
        "publication_date": {"type": "keyword"},
        "page_number": {"type": "integer"},
        "page_end": {"type": "integer"},
        "source_url": {"type": "keyword", "index": False},
    }
}
ES_FIELDS = [k for k in ES_MAPPINGS["properties"]]
# Trường metadata lưu kèm vector trong Milvus để lọc khi tìm kiếm.
MILVUS_META = {
    "document_id": 64, "organization_id": 32, "jurisdiction": 8, "language": 8, "target_population": 32,
}


def load_chunks(approved_only: bool) -> list[dict]:
    chunks = [json.loads(line) for line in CHUNKS.open(encoding="utf-8")]
    if approved_only:
        with CATALOG.open(encoding="utf-8", newline="") as f:
            approved = {d["document_id"] for d in csv.DictReader(f) if d["review_status"] == "approved"}
        chunks = [c for c in chunks if c["document_id"] in approved]
    return chunks


def embedding_text(chunk: dict) -> str:
    # Thêm tên tài liệu để vector mang ngữ cảnh (ví dụ đoạn "Mục tiêu điều trị" thuộc hướng dẫn tiền ĐTĐ).
    return f"{chunk['title']}\n{chunk['text']}"


def load_model():
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
    model.max_seq_length = MAX_SEQ_LENGTH
    return model


def index_elasticsearch(es: Elasticsearch, chunks: list[dict]) -> None:
    es.indices.delete(index=ES_INDEX, ignore_unavailable=True)
    es.indices.create(index=ES_INDEX, settings=ES_SETTINGS, mappings=ES_MAPPINGS)
    actions = ({"_index": ES_INDEX, "_id": c["chunk_id"], "_source": {k: c.get(k) for k in ES_FIELDS}} for c in chunks)
    ok, errors = helpers.bulk(es, actions, raise_on_error=False)
    es.indices.refresh(index=ES_INDEX)
    print(f"Elasticsearch: {ok} đoạn vào index '{ES_INDEX}'" + (f", {len(errors)} lỗi" if errors else ""))


def index_milvus(client: MilvusClient, chunks: list[dict], vectors) -> None:
    if client.has_collection(MILVUS_COLLECTION):
        client.drop_collection(MILVUS_COLLECTION)
    schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field("chunk_id", DataType.VARCHAR, is_primary=True, max_length=64)
    schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM)
    for name, length in MILVUS_META.items():
        schema.add_field(name, DataType.VARCHAR, max_length=length)
    schema.add_field("topic", DataType.ARRAY, element_type=DataType.VARCHAR, max_capacity=8, max_length=32)
    index_params = client.prepare_index_params()
    index_params.add_index(field_name="embedding", index_type="HNSW", metric_type="COSINE",
                           params={"M": 16, "efConstruction": 200})
    client.create_collection(MILVUS_COLLECTION, schema=schema, index_params=index_params)

    rows = [
        {"chunk_id": c["chunk_id"], "embedding": v.tolist(), "topic": c["topic"],
         **{k: c.get(k) or "" for k in MILVUS_META}}
        for c, v in zip(chunks, vectors)
    ]
    for i in range(0, len(rows), 100):
        client.insert(MILVUS_COLLECTION, rows[i:i + 100])
    client.flush(MILVUS_COLLECTION)
    print(f"Milvus: {len(rows)} vector vào collection '{MILVUS_COLLECTION}'")


def try_query(question: str, k: int = 5) -> None:
    """Thử tìm trên từng kho riêng lẻ (Hybrid + RRF làm ở giai đoạn 4)."""
    es = Elasticsearch(ES_URL)
    res = es.search(index=ES_INDEX, size=k, query={"multi_match": {
        "query": question, "fields": ["text", "text.shingle", "section_title^2", "title"]}})
    print(f"\n== BM25 (Elasticsearch): {question}")
    for i, hit in enumerate(res["hits"]["hits"], 1):
        s = hit["_source"]
        print(f"{i}. {hit['_score']:6.2f}  {s['chunk_id']:28} {s['section_title'][:50]}")

    model = load_model()
    vector = model.encode([question], normalize_embeddings=True)[0].tolist()
    client = MilvusClient(uri=MILVUS_URI)
    client.load_collection(MILVUS_COLLECTION)
    hits = client.search(MILVUS_COLLECTION, data=[vector], limit=k, output_fields=["chunk_id"],
                         search_params={"params": {"ef": 64}})[0]
    titles = {c["chunk_id"]: c["section_title"] for c in load_chunks(False)}
    print(f"\n== Vector (Milvus, bge-m3): {question}")
    for i, hit in enumerate(hits, 1):
        chunk_id = hit["chunk_id"]
        print(f"{i}. {hit['distance']:6.3f}  {chunk_id:28} {titles.get(chunk_id, '')[:50]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--approved-only", action="store_true", help="chỉ lập chỉ mục tài liệu đã duyệt")
    parser.add_argument("--query", help="không lập chỉ mục, chỉ thử tìm câu hỏi này trên 2 kho")
    args = parser.parse_args()

    if args.query:
        try_query(args.query)
        return 0

    chunks = load_chunks(args.approved_only)
    if not chunks:
        print("Không có đoạn nào để lập chỉ mục" + (" (chưa có tài liệu approved)" if args.approved_only else ""))
        return 1
    print(f"{len(chunks)} đoạn từ {len({c['document_id'] for c in chunks})} tài liệu")

    index_elasticsearch(Elasticsearch(ES_URL), chunks)

    started = time.time()
    model = load_model()
    vectors = model.encode([embedding_text(c) for c in chunks], batch_size=8, normalize_embeddings=True,
                           show_progress_bar=True)
    print(f"Đã tạo {len(vectors)} vector {vectors.shape[1]} chiều trong {time.time() - started:.0f} giây")
    index_milvus(MilvusClient(uri=MILVUS_URI), chunks, vectors)
    return 0


if __name__ == "__main__":
    sys.exit(main())
