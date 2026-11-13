"""Luồng RAG: (dịch câu hỏi) → tìm kiếm → đưa các đoạn cho LLM → câu trả lời có trích dẫn.

Bốn cấu hình để so sánh trong đánh giá:
- llm_only         : LLM tự trả lời, không có tài liệu.
- vector_rag       : chỉ tìm kiếm vector (bge-m3 / Milvus).
- hybrid_rag       : BM25 (câu hỏi gốc + bản dịch tiếng Anh) + vector, ghép bằng RRF.
- hybrid_rag_guard : hybrid_rag + Guardrails (G1 đầu vào, G2 bằng chứng, G3 kiểm tra chéo + vòng sinh lại) – hệ thống đề xuất.
"""

import re
import time
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app import guardrails, prompts
from app.config import get_settings
from app.llm import POOL, call_count, calls_since, generate, hedge_count, resolve
from app.search import SearchFilters, search

RagConfig = Literal["llm_only", "vector_rag", "hybrid_rag", "hybrid_rag_guard"]
_CITATION = re.compile(r"\[(\d{1,2})\]")
_VIETNAMESE = re.compile(r"[ăâđêôơưàảãạáằẳẵặắầẩẫậấèẻẽẹéềểễệếìỉĩịíòỏõọóồổỗộốờởỡợớùủũụúừửữựứỳỷỹỵý]", re.I)
SOURCE_FIELDS = ("chunk_id", "document_id", "title", "issuing_organization", "section_title", "page_number",
                 "page_end", "source_url", "text")


def translate_query(question: str, provider: str | None = None, model: str | None = None) -> str | None:
    """Bản tiếng Anh của câu hỏi cho BM25; None nếu câu hỏi đã là tiếng Anh hoặc dịch lỗi."""
    if not _VIETNAMESE.search(question):
        return None
    try:
        english = generate([SystemMessage(prompts.TRANSLATE_SYSTEM),
                            HumanMessage(prompts.TRANSLATE_USER.format(question=question))],
                           provider, model, max_tokens=200)
    except Exception:  # noqa: BLE001 – dịch lỗi thì vẫn tìm bằng câu gốc, không làm hỏng câu trả lời
        return None
    english = english.strip().strip('"').splitlines()[0] if english.strip() else ""
    return english or None


def answer(question: str, config: RagConfig = "hybrid_rag", provider: str | None = None, model: str | None = None,
           top_k: int | None = None, filters: SearchFilters | None = None) -> dict:
    s = get_settings()
    provider, model = resolve(provider, model)
    guarded = config == "hybrid_rag_guard"
    timings: dict[str, int] = {}
    started = time.perf_counter()
    first_call, first_hedge = call_count(), hedge_count()
    result = {"question": question, "config": config, "provider": provider, "model": model,
              "translated_query": None, "refused": False, "emergency": False, "emergency_notice": None,
              "sources": [], "cited": [],
              "disclaimer": prompts.DISCLAIMER, "guard": None}

    def finish() -> dict:
        for src in result["sources"]:
            src["cited"] = src["n"] in result["cited"]
        result["timings"] = {**timings, "total_ms": _ms(started)}
        # các (nhà cung cấp, mô hình) thực sự xử lý – có thể khác yêu cầu khi chuyển sang bản dự phòng vì hết hạn mức
        result["llm_calls"] = [f"{p}:{m}" for p, m in calls_since(first_call)]
        result["hedged_calls"] = hedge_count() - first_hedge  # số lời gọi phải gửi thêm yêu cầu dự phòng (GĐ 7)
        return result

    if config == "llm_only":
        t = time.perf_counter()
        result["answer"] = generate([SystemMessage(prompts.LLM_ONLY_SYSTEM), HumanMessage(question)], provider, model)
        timings["llm_ms"] = _ms(t)
        return finish()

    mode = "vector" if config == "vector_rag" else "hybrid"

    def timed_search(extra: list[str]) -> tuple[list[dict], int]:
        t0 = time.perf_counter()
        return search(question, mode, top_k, filters, extra_bm25_queries=extra), _ms(t0)

    # GĐ 7 – chạy song song: phân loại G1 + Prompt Guard (câu gốc) cùng lúc với bước dịch; có bản dịch thì
    # Prompt Guard (bản dịch) + tìm kiếm chạy cùng lúc với việc chờ kết quả G1. Bị G1 chặn thì bỏ kết quả tìm kiếm.
    if guarded:
        f_cls = POOL.submit(guardrails.classify, question)
        f_pg = POOL.submit(guardrails.prompt_guard_score, question)

    # Dịch bằng LLM mặc định (LLM_PROVIDER), KHÔNG dùng LLM đang trả lời: khi so sánh nhiều LLM,
    # mọi LLM nhận cùng một bộ tài liệu → khác biệt kết quả chỉ đến từ LLM.
    if config in ("hybrid_rag", "hybrid_rag_guard") and s.translate_query:
        t = time.perf_counter()
        result["translated_query"] = translate_query(question)
        timings["translate_ms"] = _ms(t)
    extra = [result["translated_query"]] if result["translated_query"] else []

    f_search = None
    if guarded:  # G1 – kiểm tra đầu vào trước khi dùng kết quả tìm kiếm
        t = time.perf_counter()
        f_pg_en = POOL.submit(guardrails.prompt_guard_score, result["translated_query"])
        f_search = POOL.submit(timed_search, extra)
        verdict = guardrails.guard_input(question, result["translated_query"],
                                         pg={"original": f_pg.result(), "english": f_pg_en.result()},
                                         cls=f_cls.result())
        timings["guard_input_ms"] = _ms(t)  # thời gian còn phải chờ G1 sau khi dịch xong (phần chạy song song không tính)
        result["guard"] = {"input": verdict.to_dict(), "decision": verdict.label}
        if verdict.label == "emergency_info":  # trả lời bình thường nhưng luôn kèm cảnh báo cấp cứu
            result.update(emergency=True, emergency_notice=verdict.message)
        if verdict.action == "block":
            result.update(answer=verdict.message, refused=verdict.label != "greeting",
                          emergency=verdict.label == "emergency")
            return finish()

    t = time.perf_counter()
    hits, timings["search_ms"] = f_search.result() if f_search else timed_search(extra)
    if f_search:
        timings["search_wait_ms"] = _ms(t)  # phần tìm kiếm chưa xong khi G1 đã có kết quả
    result["sources"] = [{"n": i, **{k: h.get(k) for k in SOURCE_FIELDS}} for i, h in enumerate(hits, start=1)]
    refusal = prompts.UNSAFE_ANSWER if guarded else prompts.REFUSAL_NO_EVIDENCE

    if guarded:  # G2 – có bằng chứng đủ gần câu hỏi không
        ok, best = guardrails.check_evidence(hits)
        result["guard"]["evidence"] = {"ok": ok, "best_vector_score": best,
                                       "threshold": s.guard_min_evidence}
        if not ok:
            result["guard"]["decision"] = "no_evidence"
            result.update(answer=refusal, refused=True)
            return finish()
    if not hits:
        result.update(answer=refusal, refused=True)
        return finish()

    messages = [SystemMessage(prompts.RAG_SYSTEM),
                HumanMessage(prompts.RAG_USER.format(context=prompts.format_context(hits), question=question))]
    attempts = []
    for attempt in range(1 + (s.guard_max_retries if guarded else 0)):
        t = time.perf_counter()
        text = generate(messages, provider, model)
        timings[f"llm_ms_{attempt + 1}"] = _ms(t)
        if prompts.NO_INFO in text:
            attempts.append({"attempt": attempt + 1, "no_info": True})
            result.update(answer=refusal, refused=True)
            break
        if not guarded:
            result["answer"] = text
            break
        t = time.perf_counter()  # G3 – kiểm tra chéo bằng LLM khác
        check = guardrails.verify_answer(text, result["sources"], provider)
        timings[f"verify_ms_{attempt + 1}"] = _ms(t)
        attempts.append({"attempt": attempt + 1, "answer": text, **check})
        if check.get("infra_error"):  # không kiểm chứng được (lỗi dịch vụ) → từ chối, ghi là lỗi hệ thống
            result.update(answer=prompts.UNSAFE_ANSWER, refused=True)
            break
        if check["faithfulness"] >= s.guard_faithfulness_threshold:
            result["answer"] = text
            break
        # Vòng sinh lại: báo cho LLM các ý không được tài liệu hỗ trợ, kèm lý do của bên kiểm tra chéo.
        problems = [f"- {c['text']} (lý do: {c.get('reason', '')})" for c in check["claims"] if not c.get("supported")]
        messages += [AIMessage(text), HumanMessage(prompts.REGENERATE_USER.format(
            unsupported="\n".join(problems), no_info=prompts.NO_INFO))]
    else:
        result.update(answer=prompts.UNSAFE_ANSWER, refused=True)  # hết số lần sinh lại mà vẫn dưới ngưỡng

    if guarded:
        last = next((a for a in reversed(attempts) if "faithfulness" in a), None)
        result["guard"].update(attempts=attempts, faithfulness=last["faithfulness"] if last else None,
                               threshold=s.guard_faithfulness_threshold,
                               decision="answered" if not result["refused"] else
                               "verify_error" if attempts and attempts[-1].get("infra_error") else
                               ("no_info" if attempts and attempts[-1].get("no_info") else "low_faithfulness"))
    if not result["refused"]:
        result["cited"] = sorted({int(n) for n in _CITATION.findall(result["answer"]) if 1 <= int(n) <= len(hits)})
    return finish()


def _ms(since: float) -> int:
    return round((time.perf_counter() - since) * 1000)
