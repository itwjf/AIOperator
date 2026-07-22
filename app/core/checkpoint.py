"""
Checkpointer 工厂 — 统一管理所有 Agent 的对话历史持久化。

为什么抽公共模块？
  4 个 service 原本各自维护 _get_memory() + _memory 全局变量，代码完全重复。
  抽到一处后：
    - 消除重复
    - 集中管理 db 路径 / 单例缓存 / setup() 调用
    - 未来切换 PostgresSaver 只改这一处

存储方案：SqliteSaver（同步版）
  - 每个 Agent 独立 db 文件，避免会话冲突
  - check_same_thread=False：async agent 在线程池调用同步 saver 时不会报错
  - setup()：创建 checkpoint 表（from_conn_string 上下文管理器会自动调，直接构造需手动调）
"""

import sqlite3
from pathlib import Path
from langgraph.checkpoint.sqlite import SqliteSaver

from app.config import settings
from app.core.logger import logger

# 各 Agent 的 checkpointer 单例缓存：{agent_name: SqliteSaver}
_savers: dict[str, SqliteSaver] = {}


def get_checkpointer(agent_name: str) -> SqliteSaver:
    """获取指定 Agent 的 SqliteSaver 单例。

    每个 Agent 用独立的 SQLite 文件（checkpoints_{agent_name}.db），
    避免不同 Agent 的会话数据混在同一个库里。

    Args:
        agent_name: Agent 标识，如 "rag" / "mcp" / "manual" / "aiops"

    Returns:
        SqliteSaver 实例（首次调用时创建并初始化表结构）
    """
    if agent_name not in _savers:
        db_dir = Path(settings.checkpoint_dir)
        db_dir.mkdir(parents=True, exist_ok=True)
        db_path = db_dir / f"checkpoints_{agent_name}.db"

        # check_same_thread=False：允许跨线程使用（async agent 场景必需）
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        saver = SqliteSaver(conn)
        saver.setup()  # 创建 checkpoint 相关表（必须调用）

        _savers[agent_name] = saver
        logger.info("Checkpointer 初始化完成 — agent: {}, db: {}", agent_name, db_path)

    return _savers[agent_name]
