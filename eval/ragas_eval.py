"""GĐ 9 – chấm RAGAS cho các câu "cần trả lời" của bộ 50 câu test (đề cương: Faithfulness / Answer Relevance /
Context Precision).

Đầu vào: eval/results/gd9_test50_{qwen,llama,gemini35lite}.jsonl (do guard_eval.py tạo).
Chỉ chấm câu expected_behavior = answer, không lỗi, KHÔNG bị từ chối (câu bị từ chối đã tính là chặn nhầm
trong guard_eval; câu từ chối / cấp cứu chấm đúng–sai theo hành vi – phương án GĐ 9 SV duyệt 13/11/2026).

| Chỉ số (RAGAS 0.4)                  | Chấm gì                                     | Áp dụng cho                    |
|-------------------------------------|---------------------------------------------|--------------------------------|
| Faithfulness                        | ý trong câu trả lời có trong tài liệu không | cấu hình có RAG                |
| ResponseRelevancy (Answer Relevance)| câu trả lời có đúng trọng tâm câu hỏi không | mọi cấu hình (kể cả LLM thuần) |
| LLMContextPrecisionWithReference    | đoạn đúng có được xếp lên đầu không         | từng chế độ tìm kiếm (vector / hybrid) – không phụ thuộc LLM trả lời |
| IDBasedContextPrecision             | như trên nhưng so mã đoạn với expected_chunk_ids (không cần LLM) | như trên |

Giám khảo (LLM chấm): gemini-3.1-flash-lite (miễn phí, hạn mức riêng; KHÔNG phải mô hình nào đang được đánh giá).
Embedding cho ResponseRelevancy: bge-m3 chạy local (cùng mô hình của hệ thống, hiểu tiếng Việt).

Vì sao phải dựng lại đoạn tài liệu: guard_eval chỉ lưu mã các đoạn ĐƯỢC TRÍCH, không lưu đủ 5 đoạn đã đưa cho LLM.
Tìm kiếm là tất định (cùng câu hỏi, cùng kho → cùng kết quả); chế độ hybrid cần bản dịch tiếng Anh (LLM mặc định –
Qwen/Groq, như lúc chạy thật). Bước `summary` kiểm tra lại: mọi đoạn được trích phải nằm trong 5 đoạn dựng lại.

Cách chạy (thư mục gốc dự án, Docker đang chạy ES + Milvus):
    .venv/Scripts/python eval/ragas_eval.py contexts            # bước 1: dựng lại đoạn tài liệu (vector + hybrid)
    .venv/Scripts/python eval/ragas_eval.py score               # bước 2: chấm (tự chạy tiếp phần chưa chấm)
    .venv/Scripts/python eval/ragas_eval.py score --limit 3     # chấm thử 3 mục
    .venv/Scripts/python eval/ragas_eval.py summary             # bước 3: bảng tổng hợp + CSV
"""

import argparse
import asyncio
import csv
import json
import os
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "eval"))
os.environ["LLM_FALLBACK"] = "false"   # như guard_eval: bản dịch lấy từ Qwen/Groq, không chuyển sang Cloudflare
os.environ["LLM_HEDGE_AFTER_S"] = "0"

from guard_eval import is_rate_limit, wait_seconds  # noqa: E402
from app.guardrails import is_daily_quota  # noqa: E402

QUESTIONS = ROOT / "eval" / "questions.jsonl"
IDS_FILE = ROOT / "eval" / "test50_ids.txt"
RESULTS = ROOT / "eval" / "results"
SOURCES = {"qwen": "gd9_test50_qwen.jsonl", "llama": "gd9_test50_llama.jsonl",
           "gemini35lite": "gd9_test50_gemini35lite.jsonl"}
CONTEXTS = RESULTS / "ragas_gd9_contexts.jsonl"
SCORES = RESULTS / "ragas_gd9.jsonl"
SUMMARY_CSV = RESULTS / "ragas_gd9_summary.csv"
JUDGE = "gemini-3.1-flash-lite"
MODE_OF = {"vector_rag": "vector", "hybrid_rag": "hybrid", "hybrid_rag_guard": "hybrid"}
METRICS = ("faithfulness", "answer_relevancy", "context_precision")


class StopRun(Exception):
    """Hết hạn mức ngày / lỗi liên tiếp → dừng gọn, lần sau chạy tiếp."""


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def append_jsonl(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def answer_questions() -> dict[str, dict]:
    ids = [line.strip() for line in IDS_FILE.read_text(encoding="utf-8").splitlines()
           if line.strip() and not line.startswith("#")]
    qs = {q["id"]: q for q in read_jsonl(QUESTIONS)}
    return {i: qs[i] for i in ids if qs[i]["expected_behavior"] == "answer"}


def judged_rows() -> list[dict]:
    """Các lượt cần chấm: câu cần trả lời, không lỗi, không bị từ chối (lấy dòng cuối cùng của mỗi (cấu hình, câu))."""
    qs = answer_questions()
    rows = []
    for source, name in SOURCES.items():
        latest = {}
        for r in read_jsonl(RESULTS / name):
            if r["id"] in qs:
                latest[(r["config"], r["id"])] = r
        for r in latest.values():
            if not r.get("error") and not r.get("refused"):
                rows.append({**r, "source": source})
    return rows


# ------------------------------------------------------------------ bước 1: dựng lại đoạn tài liệu

def translate(question: str) -> str | None:
    """Giống rag.translate_query nhưng KHÔNG bỏ qua lỗi (bản dịch sai → đoạn tài liệu sai)."""
    from langchain_core.messages import HumanMessage, SystemMessage

    from app import prompts
    from app.llm import generate
    from app.rag import _VIETNAMESE

    if not _VIETNAMESE.search(question):
        return None
    for attempt in range(6):
        try:
            text = generate([SystemMessage(prompts.TRANSLATE_SYSTEM),
                             HumanMessage(prompts.TRANSLATE_USER.format(question=question))], max_tokens=200)
            text = text.strip().strip('"').splitlines()[0] if text.strip() else ""
            return text or None
        except Exception as e:  # noqa: BLE001
            if not is_rate_limit(e) or attempt == 5:
                raise
            wait = min(wait_seconds(str(e)) or 65, 1800) + 5
            print(f"    Groq giới hạn – chờ {wait:.0f} giây rồi dịch lại", flush=True)
            time.sleep(wait)
    return None


def build_contexts() -> int:
    from app.search import search

    done = {(c["id"], c["mode"]) for c in read_jsonl(CONTEXTS)}
    qs = answer_questions()
    for i, (qid, q) in enumerate(qs.items(), start=1):
        for mode in ("vector", "hybrid"):
            if (qid, mode) in done:
                continue
            english = translate(q["question"]) if mode == "hybrid" else None
            hits = search(q["question"], mode, extra_bm25_queries=[english] if english else [])
            append_jsonl(CONTEXTS, {
                "id": qid, "mode": mode, "translated_query": english,
                "chunk_ids": [h["chunk_id"] for h in hits],
                "contexts": [f"Nguồn: {h.get('issuing_organization', '')} – {h.get('title', '')}"
                             f"{' – ' + h['section_title'] if h.get('section_title') else ''}\n{h.get('text', '')}"
                             for h in hits]})
            print(f"[{i}/{len(qs)}] {qid} {mode}: {len(hits)} đoạn", flush=True)
    print(f"Xong: {CONTEXTS.relative_to(ROOT)}")
    return 0


# ------------------------------------------------------------------ bước 2: chấm RAGAS

def make_judge():
    from langchain_core.embeddings import Embeddings
    from langchain_core.rate_limiters import InMemoryRateLimiter
    from langchain_google_genai import ChatGoogleGenerativeAI
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.run_config import RunConfig

    from app.config import get_settings
    from app.embedding import get_model

    class BgeM3(Embeddings):
        def embed_documents(self, texts):
            return get_model().encode(texts, normalize_embeddings=True).tolist()

        def embed_query(self, text):
            return self.embed_documents([text])[0]

    run_config = RunConfig(timeout=180, max_retries=3, max_wait=60)
    # gói miễn phí giới hạn lượt/phút → tối đa ~12 lượt/phút
    limiter = InMemoryRateLimiter(requests_per_second=0.2, check_every_n_seconds=0.5, max_bucket_size=1)
    chat = ChatGoogleGenerativeAI(model=JUDGE, google_api_key=get_settings().gemini_api_key, temperature=0,
                                  max_output_tokens=4096, max_retries=1, timeout=120, thinking_level="minimal",
                                  rate_limiter=limiter)
    # bypass_n: Flash-Lite không cho nhiều câu trả lời trong 1 lần gọi (400 "Multiple candidates is not enabled")
    # → ResponseRelevancy (strictness = 3) gửi 3 lời gọi riêng.
    return (LangchainLLMWrapper(chat, run_config=run_config, bypass_n=True), LangchainEmbeddingsWrapper(BgeM3()),
            run_config)


def score(limit: int | None, only: list[str]) -> int:
    from ragas.dataset_schema import SingleTurnSample
    from ragas.metrics import Faithfulness, LLMContextPrecisionWithReference, ResponseRelevancy

    contexts = {(c["id"], c["mode"]): c for c in read_jsonl(CONTEXTS)}
    if not contexts:
        print("Chưa có đoạn tài liệu – chạy bước `contexts` trước.")
        return 1
    qs = answer_questions()
    llm, emb, run_config = make_judge()
    metrics = {"faithfulness": Faithfulness(llm=llm), "answer_relevancy": ResponseRelevancy(llm=llm, embeddings=emb),
               "context_precision": LLMContextPrecisionWithReference(llm=llm)}
    for m in metrics.values():
        m.init(run_config)

    # Danh sách việc: (khoá, metric, mẫu). Chấm theo thứ tự chỉ số để kết quả dở dang vẫn so sánh được.
    units = []
    rows = judged_rows()
    for metric in [m for m in METRICS if not only or m in only]:
        if metric == "context_precision":
            for (qid, mode), c in sorted(contexts.items()):
                if qs[qid]["reference_answer"]:
                    units.append(({"source": "retrieval", "model": "-", "config": mode, "id": qid}, metric,
                                  SingleTurnSample(user_input=qs[qid]["question"], retrieved_contexts=c["contexts"],
                                                   reference=qs[qid]["reference_answer"])))
            continue
        for r in rows:
            mode = MODE_OF.get(r["config"])
            if metric == "faithfulness" and not mode:
                continue  # LLM thuần không có tài liệu → không có Faithfulness
            if mode and (r["id"], mode) not in contexts:
                continue
            sample = SingleTurnSample(user_input=r["question"], response=r["answer"],
                                      retrieved_contexts=contexts[(r["id"], mode)]["contexts"] if mode else None)
            units.append(({"source": r["source"], "model": r["model"], "config": r["config"], "id": r["id"]},
                          metric, sample))

    done = {(d["source"], d["config"], d["id"], d["metric"]) for d in read_jsonl(SCORES) if d.get("score") is not None}
    todo = [u for u in units if (u[0]["source"], u[0]["config"], u[0]["id"], u[1]) not in done]
    print(f"Tổng {len(units)} mục, đã chấm {len(units) - len(todo)}, còn {len(todo)}"
          f"{f' (lần này chấm {limit})' if limit else ''} – giám khảo {JUDGE}", flush=True)
    failures = 0
    for i, (key, metric, sample) in enumerate(todo[:limit] if limit else todo, start=1):
        t = time.perf_counter()
        record = {**key, "metric": metric, "judge": JUDGE, "score": None, "error": ""}
        try:
            value = asyncio.run(metrics[metric].single_turn_ascore(sample))
            if value is None or value != value:  # NaN: giám khảo trả JSON hỏng sau khi đã thử lại
                record["error"] = "NaN (giám khảo trả kết quả không đọc được)"
            else:
                record["score"] = round(float(value), 4)
                failures = 0
        except Exception as e:  # noqa: BLE001
            text = f"{type(e).__name__}: {e}"
            record["error"] = text[:400]
            if is_daily_quota(text):
                append_jsonl(SCORES, {**record, "ms": round((time.perf_counter() - t) * 1000)})
                print(f"Hết hạn mức ngày của {JUDGE} – dừng, mai chạy lại `score` để chấm tiếp.", flush=True)
                return 2
        failures = failures + 1 if record["score"] is None else 0
        record["ms"] = round((time.perf_counter() - t) * 1000)
        record["at"] = datetime.now().isoformat(timespec="seconds")
        append_jsonl(SCORES, record)
        shown = f"{record['score']:.3f}" if record["score"] is not None else f"LỖI {record['error'][:120]}"
        print(f"[{i}/{len(todo)}] {metric:17} {key['source']:12} {key['config']:16} {key['id']} {shown}"
              f" ({record['ms'] / 1000:.1f} s)", flush=True)
        if failures >= 5:
            print("5 mục lỗi liên tiếp – dừng để không tốn hạn mức; xem lỗi rồi chạy lại.", flush=True)
            return 3
    return 0


# ------------------------------------------------------------------ bước 3: tổng hợp

def mean(values: list[float]) -> str:
    return f"{statistics.mean(values):.3f}" if values else "–"


def summary() -> int:
    from ragas.dataset_schema import SingleTurnSample
    from ragas.metrics import IDBasedContextPrecision

    qs = answer_questions()
    contexts = {(c["id"], c["mode"]): c for c in read_jsonl(CONTEXTS)}
    latest = {}
    for d in read_jsonl(SCORES):
        if d.get("score") is not None:
            latest[(d["source"], d["config"], d["id"], d["metric"])] = d["score"]

    # Lượt trả lời / bị từ chối theo (mô hình, cấu hình) – câu cần trả lời
    counts = defaultdict(lambda: [0, 0, 0])  # trả lời, từ chối, lỗi
    models = {}
    for source, name in SOURCES.items():
        last = {}
        for r in read_jsonl(RESULTS / name):
            if r["id"] in qs:
                last[(r["config"], r["id"])] = r
        for (config, _), r in last.items():
            models[(source, config)] = r.get("model") or models.get((source, config), "")
            counts[(source, config)][2 if r.get("error") else 1 if r.get("refused") else 0] += 1

    out = []
    print(f"\nRAGAS – {len(qs)} câu cần trả lời / 50 câu test, giám khảo {JUDGE}")
    print(f"{'Mô hình':14} {'Cấu hình':17} {'Trả lời':>8} {'Từ chối':>8} {'Lỗi':>4} "
          f"{'Faithfulness':>13} {'Answer Rel.':>12}")
    for (source, config), (n_ans, n_ref, n_err) in sorted(counts.items()):
        f = [v for (s, c, _, m), v in latest.items() if s == source and c == config and m == "faithfulness"]
        a = [v for (s, c, _, m), v in latest.items() if s == source and c == config and m == "answer_relevancy"]
        print(f"{source:14} {config:17} {n_ans:>8} {n_ref:>8} {n_err:>4} {mean(f):>8} (n={len(f):>2}) "
              f"{mean(a):>7} (n={len(a):>2})")
        out.append({"source": source, "model": models[(source, config)], "config": config, "answered": n_ans,
                    "refused": n_ref, "errors": n_err, "faithfulness": mean(f), "faithfulness_n": len(f),
                    "answer_relevancy": mean(a), "answer_relevancy_n": len(a)})

    print(f"\n{'Tìm kiếm':10} {'Context Precision (LLM)':>26} {'Context Precision (mã đoạn)':>28}")
    id_metric = IDBasedContextPrecision()
    for mode in ("vector", "hybrid"):
        llm_cp = [v for (s, c, _, m), v in latest.items() if s == "retrieval" and c == mode]
        id_cp = []
        for qid, q in qs.items():
            c = contexts.get((qid, mode))
            if c and q["expected_chunk_ids"]:
                id_cp.append(id_metric.single_turn_score(SingleTurnSample(
                    retrieved_context_ids=c["chunk_ids"], reference_context_ids=q["expected_chunk_ids"])))
        print(f"{mode:10} {mean(llm_cp):>18} (n={len(llm_cp):>2}) {mean(id_cp):>20} (n={len(id_cp):>2})")
        out.append({"source": "retrieval", "model": "-", "config": mode, "context_precision": mean(llm_cp),
                    "context_precision_n": len(llm_cp), "id_context_precision": mean(id_cp),
                    "id_context_precision_n": len(id_cp)})

    # Kiểm tra đoạn dựng lại: đoạn được trích trong lần chạy thật phải nằm trong 5 đoạn dựng lại
    total = inside = 0
    for r in judged_rows():
        mode = MODE_OF.get(r["config"])
        c = contexts.get((r["id"], mode)) if mode else None
        if c:
            total += len(r.get("cited") or [])
            inside += sum(1 for x in r.get("cited") or [] if x in c["chunk_ids"])
    if total:
        print(f"\nKiểm tra đoạn dựng lại: {inside}/{total} đoạn được trích nằm trong đoạn dựng lại ({inside / total:.1%})")

    fields = ["source", "model", "config", "answered", "refused", "errors", "faithfulness", "faithfulness_n",
              "answer_relevancy", "answer_relevancy_n", "context_precision", "context_precision_n",
              "id_context_precision", "id_context_precision_n"]
    with SUMMARY_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out)
    print(f"CSV: {SUMMARY_CSV.relative_to(ROOT)}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=["contexts", "score", "summary"])
    p.add_argument("--limit", type=int, help="score: chỉ chấm N mục (để thử)")
    p.add_argument("--metrics", nargs="*", choices=METRICS, default=[], help="score: chỉ chấm các chỉ số này")
    args = p.parse_args()
    if args.step == "contexts":
        return build_contexts()
    if args.step == "score":
        return score(args.limit, args.metrics)
    return summary()


if __name__ == "__main__":
    sys.exit(main())
