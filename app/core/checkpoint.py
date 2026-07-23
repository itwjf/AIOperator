"""
Checkpointer 工厂 — 统一管理所有 Agent 的对话历史持久化。

为什么抽公共模块？
  4 个 service 原本各自维护 _get_memory() + _memory 全局变量，代码完全重复。
  抽到一处后：
    - 消除重复
    - 集中管理 db 路径 / 单例缓存 / setup() 调用
    - 未来切换 PostgresSaver 只改这一处

存储方案：AsyncSqliteSaver（异步版）
  - create_agent / StateGraph 通过 ainvoke/astream 调用时，
    内部会用 aget/aput 等异步方法，同步 SqliteSaver 不支持这些方法，
    必须用 AsyncSqliteSaver。
  - 每个 Agent 独立 db 文件，避免会话冲突。
"""

import aiosqlite
from pathlib import Path
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.config import settings
from app.core.logger import logger

# 各 Agent 的 checkpointer 单例缓存：{agent_name: AsyncSqliteSaver}
_savers: dict[str, AsyncSqliteSaver] = {}


async def get_checkpointer(agent_name: str) -> AsyncSqliteSaver:
    """获取指定 Agent 的 AsyncSqliteSaver 单例。

    每个 Agent 用独立的 SQLite 文件（checkpoints_{agent_name}.db），
    避免不同 Agent 的会话数据混在同一个库里。

    Args:
        agent_name: Agent 标识，如 "rag" / "mcp" / "manual" / "aiops"

    Returns:
        AsyncSqliteSaver 实例（首次调用时创建并初始化表结构）
    """
    if agent_name not in _savers:
        db_dir = Path(settings.checkpoint_dir)
        db_dir.mkdir(parents=True, exist_ok=True)
        db_path = db_dir / f"checkpoints_{agent_name}.db"

        conn = await aiosqlite.connect(str(db_path))
        saver = AsyncSqliteSaver(conn)
        await saver.setup()  # 创建 checkpoint 相关表（必须调用）

        _savers[agent_name] = saver
        logger.info("Checkpointer 初始化完成 — agent: {}, db: {}", agent_name, db_path)

    return _savers[agent_name]
