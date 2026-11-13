"""Tài khoản: băm mật khẩu, token đăng nhập (JWT), xác thực Google, phân quyền người dùng / quản trị.

- Mật khẩu băm bằng scrypt (thư viện chuẩn Python) kèm salt ngẫu nhiên – không lưu mật khẩu gốc.
- Token JWT ký HS256 bằng JWT_SECRET trong .env, hết hạn sau JWT_EXPIRE_DAYS ngày.
- Vai trò quản trị: email nằm trong ADMIN_EMAILS (.env) – không lưu trong CSDL để không ai tự nâng quyền qua API.
"""

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings
from app.db import User, session

_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}
_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str | None) -> bool:
    try:
        scheme, salt, digest = (stored or "").split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    candidate = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), **_SCRYPT)
    return hmac.compare_digest(candidate, base64.b64decode(digest))


def is_admin(user: User) -> bool:
    return user.email.lower() in get_settings().admin_email_list


def user_out(user: User) -> dict:
    return {"id": user.id, "email": user.email, "name": user.name, "role": "admin" if is_admin(user) else "user",
            "has_password": user.password_hash is not None, "has_google": user.google_sub is not None}


def create_token(user: User) -> str:
    s = get_settings()
    if not s.jwt_secret:
        raise HTTPException(503, "Máy chủ chưa cấu hình JWT_SECRET trong .env")
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user.id), "iat": now, "exp": now + timedelta(days=s.jwt_expire_days)},
                      s.jwt_secret, algorithm="HS256")


def verify_google(credential: str) -> dict:
    """Kiểm tra ID token do nút Google (Google Identity Services) trả về; trả email, tên, sub."""
    s = get_settings()
    if not s.google_client_id:
        raise HTTPException(503, "Máy chủ chưa cấu hình GOOGLE_CLIENT_ID")
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    try:
        info = id_token.verify_oauth2_token(credential, google_requests.Request(), s.google_client_id)
    except ValueError as e:
        raise HTTPException(401, "Đăng nhập Google không hợp lệ") from e
    if not info.get("email_verified"):
        raise HTTPException(401, "Email Google chưa được xác minh")
    return {"email": info["email"].lower(), "name": info.get("name") or info["email"].split("@")[0], "sub": info["sub"]}


def optional_user(cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> User | None:
    """Người dùng đang đăng nhập; None nếu là khách. Token sai / hết hạn → 401 để giao diện đăng xuất."""
    if cred is None:
        return None
    s = get_settings()
    try:
        payload = jwt.decode(cred.credentials, s.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as e:
        raise HTTPException(401, "Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại") from e
    with session() as db:
        user = db.get(User, int(payload["sub"]))
        if user is None or user.disabled:
            raise HTTPException(401, "Tài khoản không tồn tại hoặc đã bị khoá")
        user.last_seen_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(user)
        db.expunge(user)
        return user


def require_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise HTTPException(401, "Cần đăng nhập")
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    if not is_admin(user):
        raise HTTPException(403, "Chỉ quản trị viên được truy cập")
    return user
