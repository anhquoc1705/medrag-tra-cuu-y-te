"""Guardrails – Cross-Check nội bộ (đề cương: "NeMo Guardrails hoặc các logic Cross-Check nội bộ").

- G1 guard_input   : phân loại câu hỏi trước khi tìm kiếm (cấp cứu / ngoài phạm vi / đòi chẩn đoán–kê đơn /
                     lách quy tắc / chào hỏi / hợp lệ). Kết hợp 3 tín hiệu:
                       (a) từ khoá cấp cứu – luật cố định, không bỏ sót ca rõ ràng;
                       (b) Llama Prompt Guard 2 (Groq) chấm câu gốc và bản dịch tiếng Anh (mô hình yếu với tiếng Việt);
                       (c) LLM phân loại theo ngữ nghĩa (Qwen).
- G2 check_evidence: điểm cosine bge-m3 cao nhất của các đoạn tìm được; thấp hơn ngưỡng = không có bằng chứng.
- G3 verify_answer : tách câu trả lời thành từng ý, một LLM KHÁC (Llama 3.3) đối chiếu từng ý với đoạn được trích;
                     Faithfulness = số ý được hỗ trợ / tổng số ý.
Vòng sinh lại khi Faithfulness dưới ngưỡng nằm ở rag.py.
"""

import json
import re
import time
from dataclasses import asdict, dataclass, field

import requests
from langchain_core.messages import HumanMessage, SystemMessage

from app import prompts
from app.config import get_settings
from app.llm import generate

# ---------------------------------------------------------------- G1. Kiểm tra đầu vào

# Dấu hiệu cấp cứu rõ ràng (tim mạch, đột quỵ, hạ/tăng đường huyết nặng, tăng huyết áp cấp cứu).
EMERGENCY_PATTERNS = [
    r"đau (thắt |tức )?ngực (dữ dội|nhiều|lan|kèm|không (giảm|dứt))", r"đau ngực.{0,30}(vã mồ hôi|khó thở|lan ra)",
    r"khó thở (dữ dội|nặng|đột ngột)|thở (dốc|hổn hển) không (nói|dứt)",
    r"(yếu|liệt|tê) (nửa người|một bên|nửa mặt)|méo miệng|nói (khó|ngọng|không ra tiếng) đột ngột",
    r"(ngất|bất tỉnh|hôn mê|co giật|lơ mơ|lú lẫn)",
    r"(đường huyết|đường máu|glucose).{0,25}(dưới|<|thấp hơn) ?(3|2|1)[,.]?\d? ?mmol",
    r"(đường huyết|đường máu|glucose).{0,25}(trên|>|cao hơn) ?(2\d|3\d) ?mmol",
    r"huyết áp.{0,25}(2[0-9]{2}|1[89][0-9]) ?/ ?1[1-9][0-9]",
    # Các nhóm bệnh mở rộng (12/11/2026): hô hấp, dị ứng, tiêu hoá, truyền nhiễm, tâm thần
    r"(môi|da|mặt|đầu ngón) tím tái|tím tái",
    r"sốc phản vệ|phù (môi|lưỡi|họng|thanh quản)|sưng (môi|lưỡi|họng) (đột ngột|khó thở)",
    r"(nôn|ói|ho) ra máu|đi (ngoài|cầu) ra máu|phân (đen|có máu)",
    r"đau bụng (dữ dội|quằn quại|không chịu nổi)",
    r"sốt cao.{0,20}(li bì|co giật|không hạ|chảy máu)|chảy máu (cam|chân răng) không (cầm|ngừng)",
    r"(muốn|định|ý định|nghĩ đến) (tự tử|tự sát|chết)|tự (tử|sát)",
    r"chest pain|can'?t breathe|face drooping|slurred speech|unconscious|seizure|fainted",
    r"anaphyla|vomiting blood|coughing up blood|suicid",
]
_EMERGENCY = re.compile("|".join(f"(?:{p})" for p in EMERGENCY_PATTERNS), re.I)
LABELS = ("in_scope", "emergency", "personal_advice", "prompt_injection", "out_of_scope", "greeting")
PROMPT_GUARD_TIMEOUT = 5  # giây – tín hiệu phụ, thường < 0,5 s; quá hạn thì bỏ qua (None) thay vì chờ (trước: 20 s)


@dataclass
class InputVerdict:
    label: str                       # nhãn cuối cùng
    action: str                      # answer | block
    message: str | None = None       # câu trả lời mẫu khi block
    signals: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def emergency_keywords(question: str) -> list[str]:
    return [m.group(0) for m in _EMERGENCY.finditer(question)]


def prompt_guard_score(text: str | None) -> float | None:
    """Xác suất câu là prompt injection / jailbreak theo Llama Prompt Guard 2 (None nếu lỗi)."""
    s = get_settings()
    if not text or not s.groq_api_key:
        return None
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                          headers={"Authorization": f"Bearer {s.groq_api_key}"},
                          json={"model": s.guard_prompt_guard_model, "messages": [{"role": "user", "content": text}]},
                          timeout=PROMPT_GUARD_TIMEOUT)
        r.raise_for_status()
        return float(r.json()["choices"][0]["message"]["content"])
    except Exception:  # noqa: BLE001 – lỗi tín hiệu phụ không được làm hỏng luồng chính
        return None


def classify(question: str) -> dict:
    s = get_settings()
    try:
        raw = generate([SystemMessage(prompts.CLASSIFY_SYSTEM),
                        HumanMessage(prompts.CLASSIFY_USER.format(question=question))],
                       s.guard_classifier_provider or None, max_tokens=150)
        data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        label = data.get("label", "")
        return {"label": label if label in LABELS else "in_scope", "reason": data.get("reason", "")}
    except Exception as e:  # noqa: BLE001 – phân loại lỗi thì coi như hợp lệ, các lớp sau vẫn kiểm tra
        return {"label": "in_scope", "reason": f"lỗi phân loại: {type(e).__name__}"}


def guard_input(question: str, english: str | None, pg: dict | None = None, cls: dict | None = None) -> InputVerdict:
    """Quyết định G1. `pg` (điểm Prompt Guard) và `cls` (kết quả phân loại) có thể được tính sẵn song song
    ở rag.py (GĐ 7); không truyền thì tự tính lần lượt như cũ."""
    s = get_settings()
    keywords = emergency_keywords(question) + (emergency_keywords(english) if english else [])
    if pg is None:
        pg = {"original": prompt_guard_score(question), "english": prompt_guard_score(english)}
    if cls is None:
        cls = classify(question)
    signals = {"emergency_keywords": keywords, "prompt_guard": pg, "classifier": cls}
    injection = any(v is not None and v >= s.guard_prompt_guard_threshold for v in pg.values())

    if cls["label"] == "emergency" or (keywords and cls["label"] != "in_scope"):  # đang cấp cứu → chỉ cảnh báo
        return InputVerdict("emergency", "block", prompts.EMERGENCY_ANSWER, signals)
    if injection or cls["label"] == "prompt_injection":
        return InputVerdict("prompt_injection", "block", prompts.INJECTION_ANSWER, signals)
    if keywords:  # có dấu hiệu cấp cứu nhưng là câu hỏi thông tin → vẫn trả lời, kèm cảnh báo 115
        return InputVerdict("emergency_info", "answer", prompts.EMERGENCY_ANSWER, signals)
    if cls["label"] == "personal_advice":
        return InputVerdict("personal_advice", "block", prompts.PERSONAL_ADVICE_ANSWER, signals)
    if cls["label"] == "out_of_scope":
        return InputVerdict("out_of_scope", "block", prompts.OUT_OF_SCOPE_ANSWER, signals)
    if cls["label"] == "greeting":
        return InputVerdict("greeting", "block", prompts.GREETING_ANSWER, signals)
    return InputVerdict("in_scope", "answer", None, signals)


# ---------------------------------------------------------------- G2. Kiểm tra bằng chứng

def check_evidence(hits: list[dict]) -> tuple[bool, float]:
    """Điểm bằng chứng = cosine bge-m3 cao nhất trong các đoạn tìm được."""
    scores = [h.get("methods", {}).get("vector", {}).get("score") for h in hits]
    best = max((sc for sc in scores if sc is not None), default=0.0)
    return best >= get_settings().guard_min_evidence, round(best, 4)


# ---------------------------------------------------------------- G3. Kiểm tra chéo đầu ra

VERIFY_RETRIES = 3
_CITE = re.compile(r"\[(\d{1,2})\]")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-ZĐÀ-Ỹ])")


def extract_claims(answer: str) -> list[dict]:
    """Tách câu trả lời thành các ý: mỗi dòng gạch đầu dòng hoặc mỗi câu; bỏ dòng tiêu đề / dẫn nhập ngắn."""
    claims = []
    for line in answer.splitlines():
        line = re.sub(r"^\s*([*\-•]|\d+[.)])\s*", "", line).strip()
        if not line:
            continue
        for sentence in _SENTENCE_END.split(line):
            text = sentence.strip()
            plain = _CITE.sub("", text).replace("*", "").strip()
            # bỏ câu dẫn nhập chỉ kết thúc bằng ":" và quá ngắn để kiểm chứng
            if len(plain.split()) < 4 or (plain.endswith(":") and not _CITE.search(text)):
                continue
            claims.append({"text": plain, "cited": sorted({int(n) for n in _CITE.findall(text)})})
    return claims


def _error_text(e: Exception) -> str:
    """Tên lỗi + mã HTTP + đầu nội dung phản hồi (vd. Cloudflare 429 "…10,000 neurons…" mã 4006 = hết hạn mức ngày).

    Không dùng str(e) của httpx vì chuỗi đó chứa URL (có account id) mà không có nội dung phản hồi.
    """
    resp = getattr(e, "response", None)
    if resp is not None and hasattr(resp, "status_code"):
        return f"{type(e).__name__} {resp.status_code}: {resp.text[:200]}"
    return f"{type(e).__name__}: {e}"[:250]


# Dấu hiệu hết hạn mức THEO NGÀY (chờ vài giây không giải quyết được): Groq TPD, Cloudflare neuron, Gemini RPD.
_DAILY_QUOTA = ("tokens per day", "TPD", "neurons", "4006", "PerDay", "per day")


def is_daily_quota(text: str) -> bool:
    return any(marker in text for marker in _DAILY_QUOTA)


def verifier_candidates(answer_provider: str | None) -> list[tuple[str, str | None]]:
    """Bên kiểm tra chéo theo thứ tự thử: (nhà cung cấp, mô hình).

    Bình thường chỉ có GUARD_VERIFIER_PROVIDER. Nếu LLM trả lời trùng bên kiểm tra (vd. cấu hình Llama 3 trên Cloudflare)
    thì dùng GUARD_VERIFIER_ALTERNATES (SV chọn 13/11/2026: Qwen trước, hết hạn mức ngày thì Gemini) – không để LLM tự chấm bài.
    """
    s = get_settings()
    if answer_provider != s.guard_verifier_provider:
        return [(s.guard_verifier_provider, s.guard_verifier_model or None)]
    alternates = [p.strip() for p in s.guard_verifier_alternates.split(",") if p.strip()]
    return [(p, None) for p in alternates if p != answer_provider]


def verify_answer(answer: str, sources: list[dict], answer_provider: str | None = None) -> dict:
    """Faithfulness = số ý được tài liệu hỗ trợ / tổng số ý (LLM kiểm tra khác LLM trả lời)."""
    claims = extract_claims(answer)
    if not claims:
        return {"faithfulness": 0.0, "claims": [], "unsupported": [], "error": "không tách được ý nào"}
    src_text = "\n\n".join(f"[{src['n']}] {src.get('text', '')}" for src in sources)
    claim_text = "\n".join(
        f"{i}. {c['text']}" + (f" (cites: {', '.join(map(str, c['cited']))})" if c["cited"] else " (no citation)")
        for i, c in enumerate(claims, start=1))
    messages = [SystemMessage(prompts.VERIFY_SYSTEM),
                HumanMessage(prompts.VERIFY_USER.format(sources=src_text, claims=claim_text))]
    last_error, by_index, verifier = None, None, None
    candidates = verifier_candidates(answer_provider)
    for provider, model in candidates:
        for attempt in range(VERIFY_RETRIES):  # lỗi kết nối / dịch vụ thường là tạm thời → thử lại
            try:
                raw = generate(messages, provider, model, max_tokens=1500)
                verdicts = json.loads(raw[raw.find("["): raw.rfind("]") + 1])
                by_index = {int(v.get("claim", 0)): v for v in verdicts if isinstance(v, dict)}
                verifier = provider
                break
            except Exception as e:  # noqa: BLE001
                last_error = e
                if is_daily_quota(_error_text(e)):
                    break  # hết hạn mức ngày → thử lại vô ích, chuyển sang bên kiểm tra kế tiếp (nếu có)
                time.sleep(attempt + 1)  # GĐ 7: 1 s, 2 s (trước: 3 s, 6 s)
        if by_index is not None or not is_daily_quota(_error_text(last_error)):
            break  # chỉ chuyển bên kiểm tra khi hết hạn mức NGÀY (lỗi phút/mạng: không phí 20 lượt/ngày của Gemini)
    if by_index is None:
        # Không kiểm chứng được thì KHÔNG coi là an toàn – nhưng đánh dấu là lỗi hệ thống (không phải câu trả lời sai).
        return {"faithfulness": None, "claims": claims, "unsupported": [], "infra_error": True,
                "verifier": None, "error": f"lỗi kiểm tra chéo ({', '.join(p for p, _ in candidates)}): {_error_text(last_error)}"}
    for i, c in enumerate(claims, start=1):
        v = by_index.get(i, {})
        c["supported"] = bool(v.get("supported", False))
        c["reason"] = v.get("reason", "không có kết quả kiểm tra")
    supported = sum(c["supported"] for c in claims)
    return {"faithfulness": round(supported / len(claims), 3), "claims": claims, "verifier": verifier,
            "unsupported": [c["text"] for c in claims if not c["supported"]]}
