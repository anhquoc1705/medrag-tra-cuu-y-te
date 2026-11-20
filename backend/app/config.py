"""Cấu hình đọc từ biến môi trường / file .env (không viết cứng URL hay mật khẩu trong code)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# .env đặt ở thư mục gốc dự án (cạnh docker-compose.yml)
ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_ENV, extra="ignore")

    app_name: str = "MedRAG API"

    # Kho dữ liệu
    es_url: str = "http://localhost:9200"
    es_index: str = "medical_chunks"
    milvus_uri: str = "http://localhost:19530"
    milvus_collection: str = "medical_chunks"
    database_url: str = "postgresql://medrag:medrag@localhost:5432/medrag"

    # Frontend được phép gọi API, phân tách bằng dấu phẩy
    cors_origins: str = "http://localhost:5173"

    # Thời gian chờ tối đa (giây) khi kiểm tra kết nối
    health_timeout: float = 3.0

    # Mô hình embedding (phải trùng mô hình đã dùng khi lập chỉ mục – pipeline/index.py)
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024
    embedding_max_seq_length: int = 1024
    hf_home: str = ""                           # nơi lưu mô hình; trống = mặc định của Hugging Face
    disable_safetensors_conversion: bool = True  # không tự tải thêm bản safetensors trùng lặp

    # Hybrid Search
    search_candidates: int = 20   # số ứng viên lấy từ mỗi bên (BM25, vector) trước khi ghép
    search_top_k: int = 5         # số đoạn trả về mặc định
    # GĐ 7 (13/11/2026, chọn trên bộ dev, xác nhận trên test): k 60 → 10 và vector ×2 (BM25 có 2 danh sách – câu gốc +
    # bản dịch – nên vector ×2 để hai bên cân bằng). Trúng đoạn đúng trong top 5: dev 20 → 29/31, test 45 → 53/62.
    rrf_k: int = 10               # hằng số k của Reciprocal Rank Fusion (bài báo gốc dùng 60; nhỏ hơn = ưu tiên hạng đầu)
    rrf_vector_weight: float = 2.0  # trọng số danh sách vector khi ghép RRF (BM25 mỗi danh sách = 1)

    # LLM – nhà cung cấp mặc định: groq (Qwen) | cloudflare (Llama 3) | gemini (Gemini, thay GPT-4o)
    llm_provider: str = "groq"
    llm_model: str = ""           # trống = mô hình mặc định của nhà cung cấp (xem app/llm.py)
    llm_temperature: float = 0.1  # thấp để câu trả lời bám tài liệu, ít "sáng tạo"
    llm_max_tokens: int = 1024
    llm_fallback: bool = True     # hết hạn mức thì chuyển sang cùng mô hình ở nhà cung cấp khác (xem app/llm.py)
    llm_hedge_after_s: float = 8.0  # GĐ 7: LLM chưa trả lời sau N giây → gửi thêm 1 yêu cầu giống hệt, lấy cái về trước (0 = tắt)
    groq_api_key: str = ""
    gemini_api_key: str = ""
    cloudflare_account_id: str = ""
    cloudflare_api_token: str = ""

    # RAG
    translate_query: bool = True  # dịch câu hỏi sang tiếng Anh cho BM25 (tài liệu WHO/MedlinePlus là tiếng Anh)

    # Guardrails (GĐ 6) – các ngưỡng tinh chỉnh ở GĐ 7
    guard_classifier_provider: str = ""   # LLM phân loại câu hỏi; trống = LLM_PROVIDER
    guard_verifier_provider: str = "cloudflare"  # LLM kiểm tra chéo – KHÁC LLM trả lời để không "tự chấm bài"
    guard_verifier_model: str = ""
    # khi LLM trả lời trùng bên kiểm tra: thử lần lượt (hết hạn mức ngày → bên sau); "nhà_cung_cấp:mô_hình" để chọn mô hình
    # 15/11: bỏ gemini-3.8-flash (quá tải 503/504 liên tục, 20 lượt/ngày) – Gemini chỉ dùng 3.5 Flash-Lite
    guard_verifier_alternates: str = "groq,gemini:gemini-3.5-flash-lite"
    guard_prompt_guard_model: str = "meta-llama/llama-prompt-guard-2-86m"  # chạy trên Groq
    guard_prompt_guard_threshold: float = 0.5
    guard_min_evidence: float = 0.5       # điểm cosine (bge-m3) cao nhất của tài liệu tìm được; thấp hơn = không có bằng chứng
    guard_faithfulness_threshold: float = 0.8
    guard_max_retries: int = 2            # số lần sinh lại khi Faithfulness dưới ngưỡng
    log_chats: bool = True                # ghi log hội thoại + quyết định Guardrails vào PostgreSQL

    # Cấu hình người dùng thường nhận (quản trị đổi được ở trang Quản trị → Cấu hình, lưu trong bảng app_settings)
    chat_config: str = "hybrid_rag_guard"

    # Tài khoản (GĐ 8)
    jwt_secret: str = ""                  # bắt buộc đặt trong .env; trống thì không đăng nhập được
    jwt_expire_days: int = 7
    google_client_id: str = ""            # OAuth Client ID (Google Cloud Console); trống = ẩn nút "Tiếp tục với Google"
    admin_emails: str = ""                # email có vai trò quản trị, phân tách bằng dấu phẩy

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def admin_email_list(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
