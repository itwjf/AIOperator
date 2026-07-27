"""
流控模块 — 基于 slowapi 的 API 限流。
已登录用户按 user_id 限流，公开路由回退到 IP。
"""
import jwt
from fastapi import Request
from slowapi import Limiter
from app.config import settings


def _get_user_or_ip(request: Request) -> str:
    """优先用 JWT user_id 做限流 key，未登录则回退 IP。"""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            payload = jwt.decode(
                auth[7:],
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
                options={"verify_exp": False},
            )
            return f"user:{payload.get('sub', 'unknown')}"
        except Exception:
            pass
    host = request.client.host if request.client else "unknown"
    return f"ip:{host}"


limiter = Limiter(key_func=_get_user_or_ip)
