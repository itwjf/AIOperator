"""消息修剪工具的单元测试。

覆盖 Bug #1 的核心场景：修剪后开头出现孤立 AIMessage(tool_calls) 时应被删除。
同时覆盖 validate_message_sequence 的校验逻辑。
"""

import pytest
from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    ToolMessage,
    SystemMessage,
)

from app.core.message_trimmer import (
    trim_conversation_history,
    validate_message_sequence,
)


# === trim_conversation_history 测试 ===


def test_no_trim_when_under_limit():
    """消息数 < max 时不修剪。"""
    messages = [
        HumanMessage("问题1"),
        AIMessage("回答1"),
    ]
    result = trim_conversation_history(messages, max_messages=20)
    assert result == messages


def test_trim_to_max_messages():
    """超过 max 时保留最后 N 条。"""
    messages = [HumanMessage(f"问题{i}") for i in range(25)]
    result = trim_conversation_history(messages, max_messages=10)
    assert len(result) == 10
    # 保留的是最后 10 条
    assert result[0].content == "问题15"
    assert result[-1].content == "问题24"


def test_remove_leading_orphan_tool_message():
    """开头孤立 ToolMessage 被删除（原有逻辑）。"""
    messages = [
        HumanMessage(f"问题{i}") for i in range(15)
    ]
    # 在开头插入一个孤立的 ToolMessage（对应的 AIMessage tool_calls 被裁掉了）
    messages.insert(0, ToolMessage(content="孤立结果", tool_call_id="call_0"))
    result = trim_conversation_history(messages, max_messages=10)
    # 第一条不应是 ToolMessage
    assert not isinstance(result[0], ToolMessage)


def test_remove_leading_orphan_ai_message_with_tool_calls():
    """Bug #1 核心场景：开头孤立 AIMessage(tool_calls) 且后续无 ToolMessage → 被删除。"""
    messages = [
        HumanMessage("问题1"),
        AIMessage("回答1"),
        HumanMessage("问题2"),
        AIMessage("回答2"),
        HumanMessage("问题3"),
        # 这条带 tool_calls，但它的 ToolMessage 在窗口外（被裁掉）
        AIMessage(
            content="",
            tool_calls=[{"name": "get_time", "args": {}, "id": "call_1"}],
        ),
        HumanMessage("问题4"),
    ]
    # max=2 → 取最后 2 条：[AIMessage(tool_calls=...), HumanMessage("问题4")]
    # 第一条是带 tool_calls 的 AIMessage，后面没有 ToolMessage → 应被删除
    result = trim_conversation_history(messages, max_messages=2)
    # 修复后：开头的孤立 AIMessage(tool_calls) 应被删除
    assert not any(
        getattr(m, "tool_calls", None) for m in result
    ), "仍存在孤立的 tool_calls"
    # 第一条应是 HumanMessage（问题4）
    assert isinstance(result[0], HumanMessage)


def test_keep_paired_tool_calls_at_start():
    """开头 AIMessage(tool_calls) 后跟齐全的 ToolMessage → 保留。"""
    messages = [
        HumanMessage(f"问题{i}") for i in range(20)
    ]
    # 构造：AIMessage(tool_calls) + ToolMessage（配对完整）
    messages.append(
        AIMessage(
            content="",
            tool_calls=[{"name": "get_time", "args": {}, "id": "call_1"}],
        )
    )
    messages.append(ToolMessage(content="14:30", tool_call_id="call_1"))
    messages.append(AIMessage("现在是 14:30"))
    messages.append(HumanMessage("问题20"))

    result = trim_conversation_history(messages, max_messages=5)
    # 配对完整的 AIMessage(tool_calls) 应被保留
    has_tool_calls = any(getattr(m, "tool_calls", None) for m in result)
    assert has_tool_calls, "配对完整的 tool_calls 不应被删除"


def test_remove_multiple_leading_orphans():
    """连续多个孤立消息（Tool + AI(tool_calls) 交替）都被清理。"""
    messages = [
        HumanMessage(f"问题{i}") for i in range(15)
    ]
    # 在开头插入多个孤立消息
    messages.insert(0, ToolMessage(content="结果", tool_call_id="call_99"))
    messages.insert(
        0,
        AIMessage(
            content="",
            tool_calls=[{"name": "search", "args": {}, "id": "call_98"}],
        ),
    )
    messages.insert(0, ToolMessage(content="结果2", tool_call_id="call_97"))

    result = trim_conversation_history(messages, max_messages=10)
    # 开头不应有任何孤立消息
    assert isinstance(result[0], HumanMessage)


def test_system_message_preserved():
    """SystemMessage 在窗口内时，while 循环不会误删它。"""
    messages = [HumanMessage(f"问题{i}") for i in range(20)]
    # 在窗口内放一个 SystemMessage（倒数第二条）
    messages.append(SystemMessage(content="你是助手"))
    messages.append(HumanMessage("最后一个问题"))
    # 总共 22 条，max=5 → 取最后 5 条，SystemMessage 在窗口内
    result = trim_conversation_history(messages, max_messages=5)
    # SystemMessage 应被保留（while 循环不应删它）
    assert any(isinstance(m, SystemMessage) for m in result), "SystemMessage 被误删"


# === validate_message_sequence 测试 ===


def test_validate_valid_sequence():
    """合法序列校验通过。"""
    messages = [
        HumanMessage("几点了？"),
        AIMessage(
            content="",
            tool_calls=[{"name": "get_time", "args": {}, "id": "call_1"}],
        ),
        ToolMessage(content="14:30", tool_call_id="call_1"),
        AIMessage("现在是 14:30"),
    ]
    is_valid, issues = validate_message_sequence(messages)
    assert is_valid is True
    assert issues == []


def test_validate_missing_tool_response():
    """tool_calls 后缺 ToolMessage → 校验报错。"""
    messages = [
        HumanMessage("几点了？"),
        AIMessage(
            content="",
            tool_calls=[{"name": "get_time", "args": {}, "id": "call_1"}],
        ),
        # 缺少 ToolMessage，直接跳到 HumanMessage
        HumanMessage("那日期呢？"),
    ]
    is_valid, issues = validate_message_sequence(messages)
    assert is_valid is False
    assert len(issues) > 0
    assert "未响应" in issues[0] or "中断" in issues[0]


def test_validate_orphan_tool_message():
    """孤立 ToolMessage → 校验报错。"""
    messages = [
        HumanMessage("你好"),
        ToolMessage(content="结果", tool_call_id="call_orphan"),
        AIMessage("你好！"),
    ]
    is_valid, issues = validate_message_sequence(messages)
    assert is_valid is False
    assert any("无对应请求" in issue for issue in issues)
