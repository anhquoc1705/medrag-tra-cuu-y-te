"""Lịch sử hỏi đáp của người đã đăng nhập (mỗi người chỉ thấy cuộc của mình)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.auth import require_user
from app.db import Conversation, Message, User, session

router = APIRouter(prefix="/conversations", tags=["conversations"])


def _own(db, conversation_id: int, user: User) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != user.id:
        raise HTTPException(404, "Không tìm thấy cuộc hỏi đáp")
    return conversation


@router.get("")
def list_conversations(user: User = Depends(require_user)) -> list[dict]:
    with session() as db:
        rows = db.scalars(select(Conversation).where(Conversation.user_id == user.id)
                          .order_by(Conversation.updated_at.desc()).limit(100))
        return [{"id": c.id, "title": c.title, "updated_at": c.updated_at.isoformat()} for c in rows]


@router.get("/{conversation_id}")
def get_conversation(conversation_id: int, user: User = Depends(require_user)) -> dict:
    with session() as db:
        conversation = _own(db, conversation_id, user)
        messages = db.scalars(select(Message).where(Message.conversation_id == conversation.id).order_by(Message.id))
        return {"id": conversation.id, "title": conversation.title,
                "messages": [{"id": m.id, "question": m.question, "result": m.result} for m in messages]}


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: int, user: User = Depends(require_user)) -> None:
    with session() as db:
        db.delete(_own(db, conversation_id, user))
        db.commit()
