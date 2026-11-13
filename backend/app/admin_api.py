"""API trang quản trị: thống kê từ chat_logs, xem hội thoại, cấu hình hệ thống, người dùng, thử nghiệm so sánh.

Mọi đường dẫn yêu cầu vai trò quản trị (email nằm trong ADMIN_EMAILS).
"""

import csv
import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, or_, select

from app import settings_store
from app.auth import is_admin, require_admin
from app.chat_api import Config, run_chat
from app.db import ChatLog, Conversation, Message, User, session
from app.llm import PROVIDERS

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])
CATALOG = Path(__file__).resolve().parents[2] / "data" / "catalog" / "documents.csv"


def decision_of(log: ChatLog) -> str:
    """Cấu hình không có Guardrails không ghi decision → suy ra từ refused."""
    return log.decision or ("no_info" if log.refused else "answered")


@lru_cache
def document_titles() -> dict[str, str]:
    try:
        with CATALOG.open(encoding="utf-8", newline="") as f:
            return {row["document_id"]: row["title"] for row in csv.DictReader(f)}
    except OSError:  # chạy trong Docker không có thư mục data/ → hiện mã tài liệu
        return {}


def _p95(values: list[int]) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


@router.get("/stats")
def stats(days: int = Query(7, ge=1, le=365)) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    with session() as db:
        logs = list(db.scalars(select(ChatLog).where(ChatLog.created_at >= since)))
        user_count = db.scalar(select(func.count(User.id)))
    decisions = Counter(decision_of(log) for log in logs)
    faith = [log.faithfulness for log in logs if log.faithfulness is not None]
    documents = Counter(chunk.split("#")[0] for log in logs for chunk in (log.cited_chunks or []))
    titles = document_titles()
    per_day = Counter(log.created_at.astimezone().date().isoformat() for log in logs)
    return {
        "days": days, "questions": len(logs), "answered": decisions.get("answered", 0) + decisions.get("emergency_info", 0),
        "guest_questions": sum(log.user_id is None for log in logs), "users": user_count,
        "faithfulness_avg": round(sum(faith) / len(faith), 3) if faith else None,
        "latency_avg_ms": round(sum(log.total_ms for log in logs) / len(logs)) if logs else None,
        "latency_p95_ms": _p95([log.total_ms for log in logs]),
        "decisions": dict(decisions.most_common()),
        "top_documents": [{"document_id": d, "title": titles.get(d, d), "count": n} for d, n in documents.most_common(6)],
        "per_day": dict(sorted(per_day.items())),
    }


@router.get("/logs")
def logs(decision: str | None = None, q: str | None = Query(None, max_length=200),
         who: Literal["all", "user", "guest"] = "all", limit: int = Query(50, ge=1, le=200),
         offset: int = Query(0, ge=0)) -> dict:
    stmt = select(ChatLog, User.email).outerjoin(User, User.id == ChatLog.user_id)
    if decision == "answered":
        stmt = stmt.where(or_(ChatLog.decision == "answered", (ChatLog.decision.is_(None)) & (~ChatLog.refused)))
    elif decision == "no_info":
        stmt = stmt.where(or_(ChatLog.decision == "no_info", (ChatLog.decision.is_(None)) & ChatLog.refused))
    elif decision:
        stmt = stmt.where(ChatLog.decision == decision)
    if q:
        stmt = stmt.where(ChatLog.question.ilike(f"%{q}%"))
    if who == "user":
        stmt = stmt.where(ChatLog.user_id.is_not(None))
    elif who == "guest":
        stmt = stmt.where(ChatLog.user_id.is_(None))
    with session() as db:
        total = db.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = db.execute(stmt.order_by(ChatLog.id.desc()).limit(limit).offset(offset)).all()
        items = [{"id": log.id, "created_at": log.created_at.isoformat(), "user": email, "question": log.question,
                  "config": log.config, "model": log.model, "decision": decision_of(log),
                  "faithfulness": log.faithfulness, "attempts": log.attempts, "total_ms": log.total_ms,
                  "first_faithfulness": next((a.get("faithfulness") for a in (log.details or {}).get("guard", {})
                                              .get("attempts", []) if a.get("faithfulness") is not None), None)}
                 for log, email in rows]
    return {"total": total, "items": items}


@router.get("/logs/{log_id}")
def log_detail(log_id: int) -> dict:
    with session() as db:
        log = db.get(ChatLog, log_id)
        if log is None:
            raise HTTPException(404, "Không tìm thấy")
        user = db.get(User, log.user_id) if log.user_id else None
        return {"id": log.id, "created_at": log.created_at.isoformat(), "user": user.email if user else None,
                "question": log.question, "config": log.config, "provider": log.provider, "model": log.model,
                "decision": decision_of(log), "faithfulness": log.faithfulness, "total_ms": log.total_ms,
                "cited_chunks": log.cited_chunks, "details": log.details}


class DeleteLogsIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)


@router.post("/logs/delete")
def delete_logs(body: DeleteLogsIn) -> dict:
    """Xoá hoàn toàn: dòng chat_logs + câu hỏi tương ứng trong lịch sử người dùng (messages);
    cuộc hỏi đáp không còn câu nào thì xoá luôn. Không hoàn tác được."""
    with session() as db:
        logs = list(db.scalars(select(ChatLog).where(ChatLog.id.in_(body.ids))))
        message_ids: set[int] = set(db.scalars(select(Message.id).where(Message.chat_log_id.in_(body.ids))))
        for log in logs:  # câu lưu trước khi có cột chat_log_id: khớp theo người hỏi + câu hỏi + thời điểm
            if log.user_id is None:
                continue
            message_ids |= set(db.scalars(
                select(Message.id).join(Conversation, Conversation.id == Message.conversation_id)
                .where(Message.chat_log_id.is_(None), Conversation.user_id == log.user_id,
                       Message.question == log.question,
                       Message.created_at.between(log.created_at - timedelta(minutes=5), log.created_at + timedelta(minutes=5)))
                .limit(1)))
        conversation_ids = set(db.scalars(select(Message.conversation_id).where(Message.id.in_(message_ids))))
        db.execute(delete(Message).where(Message.id.in_(message_ids)))
        db.execute(delete(ChatLog).where(ChatLog.id.in_([log.id for log in logs])))
        still_used = set(db.scalars(select(Message.conversation_id).where(Message.conversation_id.in_(conversation_ids))))
        empty = conversation_ids - still_used
        db.execute(delete(Conversation).where(Conversation.id.in_(empty)))
        db.commit()
    return {"logs": len(logs), "messages": len(message_ids), "conversations": len(empty)}


# ---------------------------------------------------------------- cấu hình

@router.get("/settings")
def get_runtime_settings() -> dict:
    return settings_store.info()


@router.put("/settings")
def put_runtime_settings(values: settings_store.RuntimeSettings, admin: User = Depends(require_admin)) -> dict:
    if values.llm_provider == values.guard_verifier_provider:
        raise HTTPException(422, "Mô hình kiểm tra chéo phải khác mô hình trả lời (không để LLM tự chấm bài)")
    return settings_store.save(values, admin.email)


@router.post("/settings/reset")
def reset_runtime_settings(admin: User = Depends(require_admin)) -> dict:
    return settings_store.reset(admin.email)


# ---------------------------------------------------------------- người dùng

@router.get("/users")
def users() -> list[dict]:
    with session() as db:
        counts = dict(db.execute(select(Conversation.user_id, func.count(Conversation.id)).group_by(Conversation.user_id)).all())
        rows = db.scalars(select(User).order_by(User.created_at.desc()))
        return [{"id": u.id, "email": u.email, "name": u.name, "role": "admin" if is_admin(u) else "user",
                 "disabled": u.disabled,
                 "login": [m for m, ok in (("google", u.google_sub), ("email", u.password_hash)) if ok],
                 "created_at": u.created_at.isoformat(), "last_seen_at": u.last_seen_at.isoformat() if u.last_seen_at else None,
                 "conversations": counts.get(u.id, 0)} for u in rows]


class UserPatch(BaseModel):
    disabled: bool


@router.patch("/users/{user_id}")
def patch_user(user_id: int, body: UserPatch) -> dict:
    with session() as db:
        user = db.get(User, user_id)
        if user is None:
            raise HTTPException(404, "Không tìm thấy người dùng")
        if is_admin(user):
            raise HTTPException(400, "Không khoá tài khoản quản trị")
        user.disabled = body.disabled
        db.commit()
        return {"id": user.id, "disabled": user.disabled}


# ---------------------------------------------------------------- thử nghiệm so sánh (demo)

class CompareIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    configs: list[Config] = Field(min_length=1, max_length=2)
    provider: Literal[PROVIDERS] | None = None


@router.post("/compare")
def compare(body: CompareIn, admin: User = Depends(require_admin)) -> list[dict]:
    """Chạy cùng câu hỏi với từng cấu hình (lần lượt, để không vượt hạn mức token/phút của Groq)."""
    return [run_chat(body.question, config, body.provider, user_id=admin.id) for config in body.configs]
