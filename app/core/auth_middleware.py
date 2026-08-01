"""
认证中间件 — 验证 JWT 并注入 current_user。
"""
from fastapi import Request, HTTPException
from app.core.security import decode_access_token

# 不需要认证的路由前缀
PUBLIC_PREFIXES = ("/health", "/docs", "/openapi.json", "/api/auth/github")


async def get_current_user(request: Request) -> dict | None:
    """从 Authorization header 提取 JWT，返回当前用户信息。

    公开路径返回 None，业务 API 未登录抛 401。
    用户信息从 JWT payload 直接解析，不查 DB（无状态验证）。
    """
    path = request.url.path

    # 白名单放行
    if any(path.startswith(p) for p in PUBLIC_PREFIXES):
        return None

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录，请先登录")

    token = auth_header[7:]
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")

    if not payload.get("is_active", True):
        raise HTTPException(status_code=403, detail="账号已被禁用")

    return {
        "id": int(payload.get("sub", 0)),
        "username": payload.get("username", ""),
    }
