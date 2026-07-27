"""
LLM 请求守卫 — 限制单用户并发数，防止 LLM API 被打穿。

TODO: 后续在 Service 层包裹 LLM 调用时使用：
      async with get_user_semaphore(user_id):
          result = await agent.ainvoke(...)
"""
import asyncio

MAX_CONCURRENT_PER_USER = 3

_user_semaphores: dict[int, asyncio.Semaphore] = {}


def get_user_semaphore(user_id: int) -> asyncio.Semaphore:
    """获取用户级别的信号量（最多 MAX_CONCURRENT_PER_USER 个并发）。"""
    if user_id not in _user_semaphores:
        _user_semaphores[user_id] = asyncio.Semaphore(MAX_CONCURRENT_PER_USER)
    return _user_semaphores[user_id]
