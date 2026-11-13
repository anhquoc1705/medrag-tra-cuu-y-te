"""API tài khoản – luồng "Đăng nhập hoặc đăng ký": Google, hoặc email → (mật khẩu | tạo tài khoản)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.auth import create_token, hash_password, require_user, user_out, verify_google, verify_password
from app.config import get_settings
from app.db import User, session

router = APIRouter(prefix="/auth", tags=["auth"])


class EmailIn(BaseModel):
    email: str = Field(max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")  # kiểm tra dạng cơ bản, không cần thêm thư viện


class LoginIn(EmailIn):
    password: str = Field(min_length=1, max_length=200)


class RegisterIn(EmailIn):
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=200)


class GoogleIn(BaseModel):
    credential: str = Field(min_length=10)


def _session_out(user: User) -> dict:
    return {"token": create_token(user), "user": user_out(user)}


@router.get("/config")
def auth_config() -> dict:
    """Giao diện hỏi trước để biết có hiện nút Google không."""
    return {"google_client_id": get_settings().google_client_id or None}


@router.post("/check-email")
def check_email(body: EmailIn) -> dict:
    """Bước 1 của hộp đăng nhập: email đã có tài khoản chưa, có mật khẩu không (tài khoản tạo bằng Google thì không)."""
    with session() as db:
        user = db.scalar(select(User).where(User.email == body.email.lower()))
        return {"exists": user is not None, "has_password": bool(user and user.password_hash)}


@router.post("/register")
def register(body: RegisterIn) -> dict:
    with session() as db:
        email = body.email.lower()
        if db.scalar(select(User).where(User.email == email)):
            raise HTTPException(409, "Email đã có tài khoản – hãy đăng nhập")
        user = User(email=email, name=body.name.strip(), password_hash=hash_password(body.password))
        db.add(user)
        db.commit()
        db.refresh(user)
        return _session_out(user)


@router.post("/login")
def login(body: LoginIn) -> dict:
    with session() as db:
        user = db.scalar(select(User).where(User.email == body.email.lower()))
        if user and user.password_hash is None:
            raise HTTPException(400, "Tài khoản này đăng nhập bằng Google")
        if user is None or not verify_password(body.password, user.password_hash):
            raise HTTPException(401, "Email hoặc mật khẩu không đúng")
        if user.disabled:
            raise HTTPException(403, "Tài khoản đã bị khoá")
        return _session_out(user)


@router.post("/google")
def google(body: GoogleIn) -> dict:
    info = verify_google(body.credential)
    with session() as db:
        user = db.scalar(select(User).where(User.google_sub == info["sub"])) or \
            db.scalar(select(User).where(User.email == info["email"]))
        if user is None:
            user = User(email=info["email"], name=info["name"], google_sub=info["sub"])
            db.add(user)
        elif user.google_sub is None:  # tài khoản email có sẵn → liên kết với Google (Google đã xác minh email)
            user.google_sub = info["sub"]
        if user.disabled:
            raise HTTPException(403, "Tài khoản đã bị khoá")
        db.commit()
        db.refresh(user)
        return _session_out(user)


@router.get("/me")
def me(user: User = Depends(require_user)) -> dict:
    return user_out(user)
