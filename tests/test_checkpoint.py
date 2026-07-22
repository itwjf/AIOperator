"""Checkpointer 公共模块的基础测试。"""

import os
import pytest
from pathlib import Path

from app.core.checkpoint import get_checkpointer, _savers


def test_get_checkpointer_returns_singleton(monkeypatch, tmp_path):
    """同一 agent_name 返回同一实例。"""
    # 用 monkeypatch 临时覆盖 checkpoint_dir 配置
    monkeypatch.setattr("app.core.checkpoint.settings.checkpoint_dir", str(tmp_path))
    # 清空单例缓存，确保干净测试
    _savers.clear()

    saver1 = get_checkpointer("test_agent")
    saver2 = get_checkpointer("test_agent")
    assert saver1 is saver2

    # 清理
    _savers.clear()


def test_different_agents_get_different_savers(monkeypatch, tmp_path):
    """不同 agent_name 返回不同实例。"""
    monkeypatch.setattr("app.core.checkpoint.settings.checkpoint_dir", str(tmp_path))
    _savers.clear()

    saver_rag = get_checkpointer("rag")
    saver_mcp = get_checkpointer("mcp")
    assert saver_rag is not saver_mcp

    _savers.clear()


def test_checkpointer_creates_db_file(monkeypatch, tmp_path):
    """调用后 db 文件存在。"""
    monkeypatch.setattr("app.core.checkpoint.settings.checkpoint_dir", str(tmp_path))
    _savers.clear()

    get_checkpointer("file_test")

    db_path = tmp_path / "checkpoints_file_test.db"
    assert db_path.exists(), f"数据库文件未创建: {db_path}"

    _savers.clear()
