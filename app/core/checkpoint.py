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

# 所有 Agent 的标识，删除会话时需要遍历清理每个 Agent 的记忆
AGENT_NAMES = ("rag", "manual", "mcp", "aiops")


async def delete_thread(agent_name: str, thread_id: str) -> bool:
    """删除指定 Agent 中某个会话线程的对话记忆。

    对应 LangGraph 的 `adelete_thread`：会连同 checkpoint 数据、
    写日志（WAL）、以及检查点元数据一起清理。

    Args:
        agent_name: Agent 标识，如 "rag" / "mcp" / "manual" / "aiops"
        thread_id:   会话线程 ID（本项目为 f"{user_id}:{session_id}"）

    Returns:
        True 表示成功删除（含本来就不存在的情况），False 表示删除失败
    """
    try:
        saver = await get_checkpointer(agent_name)
        await saver.adelete_thread(thread_id)
        logger.info("Checkpointer 已删除 — agent: {}, thread: {}", agent_name, thread_id)
        return True
    except Exception as e:
        logger.warning("Checkpointer 删除失败 — agent: {}, thread: {}, err: {}",
                       agent_name, thread_id, e)
        return False


async def delete_thread_all(thread_id: str) -> bool:
    """遍历所有 Agent，清理某个会话线程的记忆（切换模式后各 Agent 都有独立记忆）。"""
    ok = True
    for agent_name in AGENT_NAMES:
        if not await delete_thread(agent_name, thread_id):
            ok = False
    return ok


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
