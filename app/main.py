"""
FastAPI 应用入口 — 创建应用实例、注册路由、启动服务。

运行方式：python app/main.py
或者：uvicorn app.main:app --host 127.0.0.1 --port 9900 --reload
"""

from fastapi import FastAPI
import uvicorn

from app.config import settings


# === 创建 FastAPI 应用实例 ===
# title/version 会显示在 Swagger 文档页（/docs）的顶部
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
)


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

app.include_router(chat_router)
app.include_router(file_router)
app.include_router(agent_router)


# === 启动入口 ===
# if __name__ == "__main__" 的意思是：当直接运行 python app/main.py 时执行
# 如果被其他模块 import（比如测试），不会执行这部分
if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.debug,  # debug=True 时，代码改动自动重启服务
    )
