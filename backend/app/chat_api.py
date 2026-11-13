"""API POST /chat: hỏi đáp có trích dẫn (RAG).

- Khách: trả lời bình thường, KHÔNG lưu cuộc trò chuyện (giao diện giữ tạm trên trình duyệt); câu hỏi vẫn ghi ẩn danh
  vào chat_logs để quản trị thống kê.
- Người đã đăng nhập: lưu vào conversations / messages để xem lại.
- Cấu hình / LLM do quản trị đặt (settings_store); chỉ quản trị được chọn khác khi gọi API (dùng để so sánh, demo).
"""

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import prompts
from app.auth import is_admin, optional_user
from app.config import get_settings
from app.db import Conversation, Message, User, log_chat, session
from app.llm import PROVIDERS
from app.rag import answer
from app.search import SearchFilters
from app.search_api import FiltersIn

router = APIRouter(tags=["chat"])
Config = Literal["llm_only", "vector_rag", "hybrid_rag", "hybrid_rag_guard"]


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    conversation_id: int | None = None           # trống = cuộc mới (chỉ có ý nghĩa khi đã đăng nhập)
    # Chỉ quản trị viên được ghi đè; người dùng thường luôn dùng cấu hình quản trị đã đặt.
    config: Config | None = None
    provider: Literal[PROVIDERS] | None = None
    model: str | None = Field(default=None, max_length=100)
    top_k: int | None = Field(default=None, ge=1, le=10)
    filters: FiltersIn = FiltersIn()


def run_chat(question: str, config: str | None = None, provider: str | None = None, model: str | None = None,
             top_k: int | None = None, filters: SearchFilters | None = None, user_id: int | None = None) -> dict:
    try:
        result = answer(question, config or get_settings().chat_config, provider, model, top_k, filters)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001 – lỗi từ dịch vụ LLM (hết hạn mức, mất mạng…)
        raise HTTPException(status_code=502, detail=f"Lỗi khi gọi LLM: {type(e).__name__}: {e}") from e
    result["log_id"] = log_chat(result, user_id)
    return result


@router.get("/topics")
def topics() -> dict:
    """Danh sách bệnh đang hỗ trợ (đọc từ data/catalog/topics.csv) – giao diện hiển thị cho người dùng."""
    return {"topics": prompts.TOPICS}


@router.post("/chat")
def chat(req: ChatRequest, user: User | None = Depends(optional_user)) -> dict:
    override = user is not None and is_admin(user)
    conversation = None
    if user is not None and req.conversation_id is not None:
        with session() as db:
            conversation = db.get(Conversation, req.conversation_id)
            if conversation is None or conversation.user_id != user.id:
                raise HTTPException(404, "Không tìm thấy cuộc hỏi đáp")

    result = run_chat(req.question, req.config if override else None, req.provider if override else None,
                      req.model if override else None, req.top_k if override else None,
                      SearchFilters(**req.filters.model_dump()), user.id if user else None)

    if user is not None:
        with session() as db:
            if conversation is None:
                conversation = Conversation(user_id=user.id, title=req.question.strip()[:200])
                db.add(conversation)
                db.flush()
            else:
                conversation = db.merge(conversation)
            conversation.updated_at = datetime.now(timezone.utc)
            db.add(Message(conversation_id=conversation.id, chat_log_id=result.get("log_id"), question=req.question, result=result))
            db.commit()
            result["conversation_id"] = conversation.id
    return result
