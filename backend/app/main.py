"""Điểm khởi động FastAPI. Chạy: uvicorn app.main:app --reload (trong thư mục backend/)."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import settings_store
from app.admin_api import router as admin_router
from app.auth_api import router as auth_router
from app.chat_api import router as chat_router
from app.config import get_settings
from app.conversations_api import router as conversations_router
from app.embedding import get_model
from app.health import router as health_router
from app.search_api import router as search_router

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings_store.load()  # áp cấu hình quản trị đã lưu (bảng app_settings) lên giá trị trong .env
    get_model()  # nạp bge-m3 khi khởi động (~10–20 giây) để câu hỏi đầu tiên không phải chờ
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(search_router)
app.include_router(chat_router)
app.include_router(auth_router)
app.include_router(conversations_router)
app.include_router(admin_router)


@app.get("/")
def root() -> dict:
    return {"name": settings.app_name, "docs": "/docs", "health": "/health", "search": "POST /search", "chat": "POST /chat",
            "auth": "/auth/*", "conversations": "/conversations", "admin": "/admin/*"}
