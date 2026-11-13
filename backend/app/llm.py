"""Tạo LLM theo nhà cung cấp (cấu hình trong .env). Đổi / thêm mô hình chỉ cần sửa .env, không sửa code.

| Nhà cung cấp | Mô hình mặc định                          | Vai trò trong đồ án                 |
|--------------|-------------------------------------------|-------------------------------------|
| groq         | qwen/qwen3.8-27b                          | Qwen – LLM chính của chatbot        |
| cloudflare   | @cf/meta/llama-3.3-70b-instruct-fp8-fast  | Llama 3 – cấu hình so sánh          |
| gemini       | gemini-3.8-flash                          | Thay GPT-4o (GitHub Models đã ngừng)|

Qwen trên Groq hết hạn mức → tự chuyển sang cùng mô hình trên Cloudflare (FALLBACKS).
"""

import re
import threading
import time
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from functools import lru_cache

from langchain_core.language_models import BaseChatModel

from app.config import get_settings

DEFAULT_MODELS = {
    "groq": "qwen/qwen3.8-27b",
    "cloudflare": "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
    "gemini": "gemini-3.8-flash",  # gemini-2.5-flash không còn mở cho tài khoản mới
}
PROVIDERS = tuple(DEFAULT_MODELS)
_THINK = re.compile(r"<think>.*?</think>", re.S)
_USAGE: deque = deque(maxlen=2000)  # (thời điểm, nhà cung cấp, số token) – để điều nhịp theo hạn mức token/phút
TIMEOUT = 60  # giây – không để một lời gọi treo mãi khi mạng chập chờn (mặc định của thư viện là chờ vô hạn)
# GĐ 7 – hai nhóm luồng riêng để không tự chờ lẫn nhau (bước song song gọi generate → generate dùng nhóm hedge):
POOL = ThreadPoolExecutor(max_workers=32, thread_name_prefix="medrag-step")   # các bước G1 / tìm kiếm chạy cùng lúc
_HEDGE_POOL = ThreadPoolExecutor(max_workers=32, thread_name_prefix="medrag-llm")  # chỉ chạy lời gọi LLM đơn lẻ
_LOCK = threading.Lock()
_HEDGES = [0]  # số lần đã phải gửi yêu cầu dự phòng (để đo hiệu quả)


def hedge_count() -> int:
    return _HEDGES[0]


def resolve(provider: str | None, model: str | None) -> tuple[str, str]:
    s = get_settings()
    provider = (provider or s.llm_provider).lower()
    if provider not in DEFAULT_MODELS:
        raise ValueError(f"Nhà cung cấp LLM không hỗ trợ: {provider} (chọn một trong {PROVIDERS})")
    if not model:
        model = s.llm_model if provider == s.llm_provider.lower() and s.llm_model else DEFAULT_MODELS[provider]
    return provider, model


@lru_cache
def get_llm(provider: str | None = None, model: str | None = None, max_tokens: int | None = None) -> BaseChatModel:
    s = get_settings()
    provider, model = resolve(provider, model)
    max_tokens = max_tokens or s.llm_max_tokens
    if provider == "groq":
        from langchain_groq import ChatGroq

        if not s.groq_api_key:
            raise ValueError("Thiếu GROQ_API_KEY trong .env")
        return ChatGroq(model_name=model, groq_api_key=s.groq_api_key, temperature=s.llm_temperature,
                        max_tokens=max_tokens, max_retries=2, request_timeout=TIMEOUT)
    if provider == "cloudflare":
        from langchain_cloudflare import ChatCloudflareWorkersAI

        if not (s.cloudflare_account_id and s.cloudflare_api_token):
            raise ValueError("Thiếu CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN trong .env")
        return ChatCloudflareWorkersAI(model=model, account_id=s.cloudflare_account_id,
                                       api_token=s.cloudflare_api_token, temperature=s.llm_temperature,
                                       max_tokens=max_tokens, request_timeout=TIMEOUT, max_retries=2)
    from langchain_google_genai import ChatGoogleGenerativeAI

    if not s.gemini_api_key:
        raise ValueError("Thiếu GEMINI_API_KEY trong .env")
    return ChatGoogleGenerativeAI(model=model, google_api_key=s.gemini_api_key, temperature=s.llm_temperature,
                                  max_output_tokens=max_tokens, thinking_budget=0, max_retries=2, timeout=TIMEOUT)


# Cùng mô hình ở nhà cung cấp khác – dùng khi nhà cung cấp chính hết hạn mức (Groq miễn phí: 200.000 token/ngày).
FALLBACKS = {("groq", "qwen/qwen3.8-27b"): ("cloudflare", "@cf/qwen/qwen3.8-27b")}
_CALLS: deque = deque(maxlen=2000)  # (nhà cung cấp, mô hình) thực sự xử lý từng lời gọi – để ghi log minh bạch
_CALLS_TOTAL = [0]


def _is_quota_error(error: Exception) -> bool:
    text = f"{type(error).__name__} {error}".lower()
    return "ratelimit" in text or "rate limit" in text or "429" in text or "quota" in text


def hedged(fn, *args, after: float, **kwargs):
    """Gọi fn; nếu sau `after` giây chưa xong thì gửi thêm MỘT yêu cầu giống hệt và lấy kết quả về trước (GĐ 7).

    Dịch vụ miễn phí thỉnh thoảng nghẽn: phần lớn lời gọi xong trong vài giây nhưng có lời gọi kéo dài 30–40 giây.
    Yêu cầu thứ hai thường được xử lý ở máy chủ khác nên về sớm hơn → cắt "đuôi" độ trễ mà chỉ tốn thêm hạn mức
    ở những lời gọi chậm. Cùng mô hình, cùng đầu vào → kết quả tương đương, không ảnh hưởng tính nhất quán.
    """
    first = _HEDGE_POOL.submit(fn, *args, **kwargs)
    done, _ = wait([first], timeout=after)
    if done:
        return first.result()
    with _LOCK:
        _HEDGES[0] += 1
    pending = {first, _HEDGE_POOL.submit(fn, *args, **kwargs)}
    error: BaseException | None = None
    while pending:
        done, pending = wait(pending, return_when=FIRST_COMPLETED)
        for future in done:
            if future.exception() is None:
                return future.result()
            error = future.exception()
    raise error  # cả hai đều lỗi


def generate(messages: list, provider: str | None = None, model: str | None = None,
             max_tokens: int | None = None, hedge: bool = True) -> str:
    """Gọi LLM, trả về văn bản (đã bỏ phần suy nghĩ <think>…</think> nếu mô hình có xuất ra).

    Nếu nhà cung cấp chính báo hết hạn mức và có bản dự phòng cùng mô hình (FALLBACKS) thì gọi bản dự phòng.
    hedge=True: gửi thêm một yêu cầu dự phòng khi lời gọi chậm quá LLM_HEDGE_AFTER_S giây (0 = tắt).
    """
    after = get_settings().llm_hedge_after_s if hedge else 0
    if after > 0:
        return hedged(_generate_once, messages, provider, model, max_tokens, after=after)
    return _generate_once(messages, provider, model, max_tokens)


def _generate_once(messages: list, provider: str | None, model: str | None, max_tokens: int | None) -> str:
    provider, model = resolve(provider, model)
    try:
        reply = get_llm(provider, model, max_tokens).invoke(messages)
    except Exception as e:
        backup = FALLBACKS.get((provider, model))
        if not (backup and get_settings().llm_fallback and _is_quota_error(e)):
            raise
        provider, model = backup
        reply = get_llm(provider, model, max_tokens).invoke(messages)
    usage = getattr(reply, "usage_metadata", None) or {}
    with _LOCK:  # nhiều lời gọi chạy song song (GĐ 7) → khoá khi cập nhật bộ đếm
        _USAGE.append((time.time(), provider, int(usage.get("total_tokens") or 0)))
        _CALLS.append((provider, model))
        _CALLS_TOTAL[0] += 1
    content = reply.content if isinstance(reply.content, str) else "".join(
        part.get("text", "") if isinstance(part, dict) else str(part) for part in reply.content)
    text = _THINK.sub("", content).strip()
    if not text:  # ví dụ Qwen trên Cloudflare đôi khi trả rỗng – coi là lỗi, không coi là "câu trả lời không có ý"
        raise RuntimeError(f"LLM trả về nội dung rỗng ({provider}:{model})")
    return text


def call_count() -> int:
    """Số lời gọi đã thực hiện – lấy mốc trước một luồng xử lý để biết những lời gọi nào thuộc luồng đó."""
    return _CALLS_TOTAL[0]


def calls_since(mark: int) -> list[tuple[str, str]]:
    """Các (nhà cung cấp, mô hình) đã xử lý kể từ mốc `mark`."""
    n = _CALLS_TOTAL[0] - mark
    return list(_CALLS)[-n:] if n > 0 else []


def recent_tokens(provider: str, seconds: float = 60) -> int:
    """Tổng token đã dùng với một nhà cung cấp trong `seconds` giây gần nhất (để không vượt hạn mức token/phút)."""
    since = time.time() - seconds
    return sum(tokens for t, p, tokens in _USAGE if p == provider and t >= since)
