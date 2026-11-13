"""Cấu hình quản trị đổi được lúc chạy (trang Quản trị → Cấu hình).

Giá trị trong .env là mặc định; quản trị lưu thay đổi vào bảng app_settings (một dòng key="runtime"),
khi khởi động và khi lưu thì ghi đè lên đối tượng Settings đang dùng → rag.py / guardrails.py / llm.py
đọc get_settings() như cũ, không phải sửa.
"""

import logging
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.db import AppSetting, session
from app.llm import PROVIDERS

log = logging.getLogger(__name__)
KEY = "runtime"


class RuntimeSettings(BaseModel):
    chat_config: Literal["llm_only", "vector_rag", "hybrid_rag", "hybrid_rag_guard"]
    llm_provider: Literal[PROVIDERS]
    llm_model: str = Field("", max_length=100)       # trống = mô hình mặc định của nhà cung cấp
    guard_verifier_provider: Literal[PROVIDERS]
    search_top_k: int = Field(ge=1, le=10)
    translate_query: bool
    llm_fallback: bool
    guard_faithfulness_threshold: float = Field(ge=0, le=1)
    guard_max_retries: int = Field(ge=0, le=5)
    guard_min_evidence: float = Field(ge=0, le=1)
    guard_prompt_guard_threshold: float = Field(ge=0, le=1)


FIELDS = tuple(RuntimeSettings.model_fields)
_DEFAULTS = RuntimeSettings(**{f: getattr(Settings(), f) for f in FIELDS})  # giá trị từ .env, trước khi ghi đè


def current() -> RuntimeSettings:
    s = get_settings()
    return RuntimeSettings(**{f: getattr(s, f) for f in FIELDS})


def _apply(values: RuntimeSettings) -> None:
    s = get_settings()
    for f in FIELDS:
        setattr(s, f, getattr(values, f))


def load() -> None:
    """Gọi khi khởi động: áp cấu hình quản trị đã lưu (nếu có). Lỗi CSDL thì giữ giá trị .env."""
    try:
        with session() as db:
            row = db.get(AppSetting, KEY)
            if row:
                _apply(RuntimeSettings(**{**_DEFAULTS.model_dump(), **row.value}))
    except Exception:  # noqa: BLE001
        log.exception("Không đọc được app_settings – dùng cấu hình trong .env")


def info() -> dict:
    with session() as db:
        row = db.get(AppSetting, KEY)
        return {"values": current().model_dump(), "defaults": _DEFAULTS.model_dump(),
                "updated_at": row.updated_at.isoformat() if row else None, "updated_by": row.updated_by if row else None}


def save(values: RuntimeSettings, by: str) -> dict:
    with session() as db:
        row = db.get(AppSetting, KEY) or AppSetting(key=KEY)
        row.value, row.updated_at, row.updated_by = values.model_dump(), datetime.now(timezone.utc), by
        db.add(row)
        db.commit()
    _apply(values)
    return info()


def reset(by: str) -> dict:
    return save(_DEFAULTS, by)
