"""
安全模块 — JWT 令牌生成/验证。
"""
import jwt
from datetime import datetime, timedelta, timezone
from app.config import settings


def create_access_token(user_id: int, username: str = "", is_active: bool = True) -> str:
    """生成 JWT access_token。payload 携带用户信息，避免中间件每次查 DB。"""
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)
    payload = {
        "sub": str(user_id),
        "username": username,
        "is_active": is_active,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict | None:
    """解码 JWT token，返回 payload；无效/过期则返回 None。"""
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None
