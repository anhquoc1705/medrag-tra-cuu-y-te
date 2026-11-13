"""Ghi log hội thoại + quyết định Guardrails vào PostgreSQL (SQLAlchemy).

Dùng cho: thống kê câu hỏi bị từ chối / ngoài phạm vi, tỉ lệ chặn, Faithfulness, độ trễ (trang quản trị ở GĐ 8).
Ghi log lỗi KHÔNG được làm hỏng câu trả lời cho người dùng.
"""

import logging
from datetime import datetime, timezone
from functools import lru_cache

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app.config import get_settings

log = logging.getLogger(__name__)
JSONType = JSON().with_variant(JSONB(), "postgresql")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str | None] = mapped_column(String(255))   # None = chỉ đăng nhập bằng Google
    google_sub: Mapped[str | None] = mapped_column(String(64), unique=True)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Conversation(Base):
    """Cuộc hỏi đáp của người đã đăng nhập (khách không được lưu – chỉ giữ tạm trên trình duyệt)."""
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    chat_log_id: Mapped[int | None] = mapped_column(Integer, index=True)   # dòng chat_logs tương ứng – để quản trị xoá cả hai
    question: Mapped[str] = mapped_column(Text)
    result: Mapped[dict] = mapped_column(JSONType)   # kết quả /chat đầy đủ (câu trả lời, nguồn, Guardrails) để hiển thị lại
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AppSetting(Base):
    """Cấu hình do quản trị đổi lúc chạy (ghi đè giá trị trong .env) – xem app/settings_store.py."""
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONType)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_by: Mapped[str | None] = mapped_column(String(254))


class ChatLog(Base):
    __tablename__ = "chat_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True)   # None = khách (ghi ẩn danh)
    question: Mapped[str] = mapped_column(Text)
    config: Mapped[str] = mapped_column(String(32))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(100))
    decision: Mapped[str | None] = mapped_column(String(32))      # nhãn G1 / no_evidence / low_faithfulness / answered
    refused: Mapped[bool] = mapped_column(Boolean)
    emergency: Mapped[bool] = mapped_column(Boolean)
    faithfulness: Mapped[float | None] = mapped_column(Float)
    attempts: Mapped[int | None] = mapped_column(Integer)
    cited_chunks: Mapped[list] = mapped_column(JSONType)
    total_ms: Mapped[int] = mapped_column(Integer)
    details: Mapped[dict] = mapped_column(JSONType)  # guard + timings đầy đủ


@lru_cache
def get_engine():
    url = get_settings().database_url
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)  # driver psycopg 3
    engine = create_engine(url, pool_pre_ping=True)
    Base.metadata.create_all(engine)  # tạo bảng nếu chưa có
    with engine.begin() as conn:      # bảng chat_logs tạo từ GĐ 6 chưa có cột user_id (create_all không thêm cột)
        conn.execute(text("ALTER TABLE chat_logs ADD COLUMN IF NOT EXISTS user_id INTEGER"))
        conn.execute(text("ALTER TABLE messages ADD COLUMN IF NOT EXISTS chat_log_id INTEGER"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_messages_chat_log_id ON messages (chat_log_id)"))
    return engine


def session() -> Session:
    return Session(get_engine())


def log_chat(result: dict, user_id: int | None = None) -> int | None:
    """Ghi một dòng chat_logs; trả id (None nếu tắt ghi log hoặc lỗi)."""
    if not get_settings().log_chats:
        return None
    guard = result.get("guard") or {}
    try:
        with Session(get_engine()) as session:
            row = ChatLog(
                user_id=user_id, question=result["question"], config=result["config"], provider=result["provider"],
                model=result["model"], decision=guard.get("decision"), refused=result["refused"],
                emergency=result.get("emergency", False), faithfulness=guard.get("faithfulness"),
                attempts=len(guard.get("attempts", [])) or None,
                cited_chunks=[src["chunk_id"] for src in result["sources"] if src.get("cited")],
                total_ms=result["timings"]["total_ms"],
                details={"guard": guard, "timings": result["timings"], "translated_query": result["translated_query"],
                         "llm_calls": result.get("llm_calls", []), "hedged_calls": result.get("hedged_calls", 0)},
            )
            session.add(row)
            session.commit()
            return row.id
    except Exception:  # noqa: BLE001
        log.exception("Không ghi được log hội thoại")
        return None
