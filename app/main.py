"""
FastAPI 应用入口 — 创建应用实例、注册路由、启动服务。

运行方式：python app/main.py
或者：uvicorn app.main:app --host 127.0.0.1 --port 9900 --reload
"""

import os as _os
import time
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

from app.config import settings
from app.core.logger import setup_logger, logger

# === 初始化日志系统 ===
# 必须在创建 app 之前调用，确保所有后续模块都能正常使用 logger
setup_logger(log_level=settings.log_level, log_dir=settings.log_dir)

# === 启用 LangSmith 追踪 ===
if settings.langchain_tracing_v2 and settings.langchain_api_key:
    import os
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_ENDPOINT"] = settings.langchain_endpoint
    os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
    logger.info("LangSmith 追踪已启用 — 项目: {}", settings.langchain_project)

# === 创建 FastAPI 应用实例 ===
# title/version 会显示在 Swagger 文档页（/docs）的顶部
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
)

# === 注册流控 ===
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.core.rate_limiter import limiter

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# === 请求日志中间件 ===
# 每个 HTTP 请求进来时自动记录方法、路径、耗时和状态码
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """记录每个 HTTP 请求的方法、路径、耗时和状态码。"""
    start_time = time.time()
    response = await call_next(request)
    elapsed = (time.time() - start_time) * 1000  # 毫秒
    logger.info(
        "{} {} → {} ({:.0f}ms)",
        request.method,
        request.url.path,
        response.status_code,
        elapsed,
    )
    return response


# === 注册路由 ===
# 按模块拆分路由，用 include_router 注册
# 每个模块只管自己的前缀路径（如 /api），main.py 不需要知道细节


@app.get("/health")
async def health_check():
    """健康检查接口 — 用于验证服务是否正常运行。"""
    return {"status": "ok"}


from app.api.chat import router as chat_router
from app.api.file import router as file_router
from app.api.agent import router as agent_router
from app.api.aiops import router as aiops_router
from app.api.mcp import router as mcp_router
from app.api.title import router as title_router
from app.api.auth import router as auth_router
from app.api.session import router as session_router

app.include_router(chat_router)
app.include_router(file_router)
app.include_router(agent_router)
app.include_router(aiops_router)
app.include_router(mcp_router)
app.include_router(title_router)
app.include_router(auth_router)
app.include_router(session_router)


# === 前端服务 ===
# 开发环境：Vite dev server 在 :5173 代理到本服务，FastAPI 不直接服务前端
# 生产环境：npm run build 后 dist/ 存在，FastAPI 直接 serve
#
# 前端使用 Vue Router history 模式（如 /login），刷新或直接访问这些前端路由时
# 不能返回 404，需 fallback 到 index.html 交给前端路由渲染。
#
# 路由注册顺序很关键（Starlette 按注册顺序匹配）：
#   1. API 路由已在前面的 include_router 注册，优先命中；
#   2. 静态打包资源 /assets/* 用 mount 注册（必须在 catch-all 之前）；
#   3. catch-all 兜底：其余非 API 路径返回 index.html。
_FRONTEND_DIST = "frontend/dist"
_ASSETS_DIR = _os.path.join(_FRONTEND_DIST, "assets")

# 后端路径前缀，绝不能被 SPA fallback 拦截（兜底保护）
_NON_SPA_PREFIXES = ("/api", "/health", "/docs", "/redoc", "/openapi.json", "/assets")


if _os.path.isdir(_FRONTEND_DIST):
    # 静态打包资源（Vite 产物，带内容 hash）—— 必须在 catch-all 之前注册
    if _os.path.isdir(_ASSETS_DIR):
        app.mount("/assets", StaticFiles(directory=_ASSETS_DIR), name="assets")


# catch-all 兜底：放在 mount 之后，避免抢走 /assets 等静态资源。
# 只有当前面所有路由都没匹配到时（即用户直接访问 history 路由如 /login）才进入。
if _os.path.isdir(_FRONTEND_DIST):
    from fastapi import HTTPException

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        """SPA catch-all：非 API/静态资源路径返回 index.html，交给 Vue Router 渲染。"""
        request_path = "/" + full_path if full_path else "/"
        if request_path.startswith(_NON_SPA_PREFIXES):
            raise HTTPException(status_code=404, detail="Not Found")
        return FileResponse(_os.path.join(_FRONTEND_DIST, "index.html"))


# === 启动入口 ===
# if __name__ == "__main__" 的意思是：当直接运行 python app/main.py 时执行
# 如果被其他模块 import（比如测试），不会执行这部分
if __name__ == "__main__":
    # 把 uvicorn 的日志也接入 loguru，统一管理
    import logging as std_logging

    class _InterceptHandler(std_logging.Handler):
        """把标准库 logging 的日志重定向到 loguru。"""
        def emit(self, record):
            from loguru import logger as loguru_logger
            level_map = {
                std_logging.DEBUG: "DEBUG",
                std_logging.INFO: "INFO",
                std_logging.WARNING: "WARNING",
                std_logging.ERROR: "ERROR",
                std_logging.CRITICAL: "CRITICAL",
            }
            loguru_logger.opt(depth=6, exception=record.exc_info).log(
                level_map.get(record.levelno, "INFO"),
                record.getMessage(),
            )

    # 截获 uvicorn 和 fastapi 的日志
    for name in ["uvicorn", "uvicorn.access", "uvicorn.error", "fastapi"]:
        std_logging.getLogger(name).handlers = [_InterceptHandler()]

    logger.info("启动服务器 — {} v{}", settings.app_name, settings.app_version)
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.debug,  # debug=True 时，代码改动自动重启服务
        log_level=settings.log_level.lower(),
    )
