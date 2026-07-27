"""
MCP Server 共享模块 — Token 校验中间件（各 MCP Server 复用）。
"""
import os
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class TokenCheckMiddleware(BaseHTTPMiddleware):
    """校验请求中的 MCP_SECRET_TOKEN。"""

    async def dispatch(self, request, call_next):
        if request.url.path == "/health":
            return await call_next(request)
        expected = os.getenv("MCP_SECRET_TOKEN", "")
        if not expected:
            return await call_next(request)
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if token != expected:
            return JSONResponse({"detail": "禁止访问"}, status_code=403)
        return await call_next(request)
