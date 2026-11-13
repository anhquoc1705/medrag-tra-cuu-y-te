"""Đo chất lượng truy xuất trên các câu hỏi có `expected_chunk_ids` cho 4 chế độ: BM25 / Vector / Hybrid (RRF) /
Hybrid + bản dịch tiếng Anh của câu hỏi cho BM25 (`hybrid_translate`, gọi LLM để dịch).

Chỉ số (độ liên quan nhị phân: đoạn nằm trong expected_chunk_ids là liên quan):
- Recall@k : tỉ lệ đoạn liên quan xuất hiện trong top-k.
- MRR@10   : trung bình 1 / hạng của đoạn liên quan đầu tiên (0 nếu không có trong top 10).
- nDCG@10  : DCG / DCG lý tưởng, DCG = Σ 1 / log2(hạng + 1) trên các đoạn liên quan.

Cách chạy (từ thư mục gốc dự án, Docker đang chạy ES + Milvus):
    .venv/Scripts/python eval/retrieval_eval.py
Kết quả: in bảng tổng hợp và ghi chi tiết từng câu vào eval/results/retrieval_<ngày giờ>.csv
"""

import csv
import json
import math
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.rag import translate_query  # noqa: E402
from app.search import search  # noqa: E402

QUESTIONS = ROOT / "eval" / "questions.jsonl"
RESULTS_DIR = ROOT / "eval" / "results"
MODES = ("bm25", "vector", "hybrid", "hybrid_translate")
DEPTH = 10


def recall_at(ranked: list[str], relevant: set[str], k: int) -> float:
    return len(set(ranked[:k]) & relevant) / len(relevant)


def mrr(ranked: list[str], relevant: set[str]) -> float:
    for rank, cid in enumerate(ranked[:DEPTH], start=1):
        if cid in relevant:
            return 1.0 / rank
    return 0.0


def ndcg(ranked: list[str], relevant: set[str]) -> float:
    dcg = sum(1.0 / math.log2(rank + 1) for rank, cid in enumerate(ranked[:DEPTH], start=1) if cid in relevant)
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, min(len(relevant), DEPTH) + 1))
    return dcg / ideal


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["dev", "test"], help="chỉ đo bộ dev (tinh chỉnh) hoặc test (chấm điểm cuối)")
    args = parser.parse_args()
    questions = [json.loads(line) for line in QUESTIONS.open(encoding="utf-8") if line.strip()]
    if args.split:
        questions = [q for q in questions if q.get("split") == args.split]
    labelled = [q for q in questions if q.get("expected_chunk_ids")]
    if not labelled:
        print("Chưa có câu hỏi nào có expected_chunk_ids")
        return 1
    print(f"{len(labelled)}/{len(questions)} câu có đáp án được dùng để đo\n")

    rows, totals = [], {m: {"R@5": 0.0, "R@10": 0.0, "MRR@10": 0.0, "nDCG@10": 0.0} for m in MODES}
    for q in labelled:
        relevant = set(q["expected_chunk_ids"])
        english = translate_query(q["question"])
        for mode in MODES:
            if mode == "hybrid_translate":
                hits = search(q["question"], "hybrid", top_k=DEPTH, extra_bm25_queries=[english] if english else [])
            else:
                hits = search(q["question"], mode, top_k=DEPTH)
            ranked = [r["chunk_id"] for r in hits]
            metrics = {"R@5": recall_at(ranked, relevant, 5), "R@10": recall_at(ranked, relevant, 10),
                       "MRR@10": mrr(ranked, relevant), "nDCG@10": ndcg(ranked, relevant)}
            for name, value in metrics.items():
                totals[mode][name] += value
            first_hit = next((i for i, cid in enumerate(ranked, 1) if cid in relevant), None)
            rows.append({"id": q["id"], "category": q["category"], "mode": mode, "first_relevant_rank": first_hit,
                         **{k: round(v, 4) for k, v in metrics.items()}, "top3": " ".join(ranked[:3]),
                         "translated_query": english if mode == "hybrid_translate" else ""})
        print(f"  {q['id']} xong", flush=True)

    n = len(labelled)
    print(f"\n{'Chế độ':17} {'R@5':>7} {'R@10':>7} {'MRR@10':>8} {'nDCG@10':>8}")
    for mode in MODES:
        t = totals[mode]
        print(f"{mode:17}{t['R@5'] / n:7.3f} {t['R@10'] / n:7.3f} {t['MRR@10'] / n:8.3f} {t['nDCG@10'] / n:8.3f}")

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"retrieval_{datetime.now():%Y%m%d_%H%M}.csv"
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nChi tiết từng câu: {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
