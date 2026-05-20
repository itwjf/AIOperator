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
# 第一阶段只写一个最简路由，后续阶段再拆分到 api/ 目录下


@app.get("/health")
async def health_check():
    """健康检查接口 — 用于验证服务是否正常运行。

    返回固定的 {"status": "ok"}，不做任何复杂逻辑。
    后续可以扩展：检查数据库连接、外部服务可达性等。
    """
    return {"status": "ok"}


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
