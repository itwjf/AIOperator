"""
消息修剪工具 — 防止对话历史超出 LLM 的 token 限制。

策略：滑动窗口
  - 当消息数量超过 max_messages 时，只保留最近的 N 条消息
  - 保留消息的语义完整性：不会在工具调用链中间截断
"""

from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage


def trim_conversation_history(
    messages: list[BaseMessage],
    max_messages: int = 20,
) -> list[BaseMessage]:
    """修剪对话历史，保留最近的 max_messages 条消息。

    修剪策略：
      1. 如果消息总数 ≤ max_messages，不做任何处理
      2. 否则保留最近 max_messages 条消息
      3. 确保不截断工具调用链：如果修剪后的第一条消息是 ToolMessage
         （说明它对应的 AIMessage tool_call 被裁掉了），则连带删除这些
         孤立的 ToolMessage，直到遇到 HumanMessage 或 AIMessage

    Args:
        messages: 完整的消息列表
        max_messages: 保留的最大消息数

    Returns:
        修剪后的消息列表

    Example:
        >>> # 30 条消息 → 保留最近 20 条
        >>> trimmed = trim_conversation_history(messages, max_messages=20)
    """
    if len(messages) <= max_messages:
        return messages

    # 保留最近 max_messages 条
    trimmed = messages[-max_messages:]

    # 修复工具调用链完整性：
    # 如果修剪后第一条就是 ToolMessage，说明它对应的 tool_call 请求（AIMessage）
    # 已经被裁掉了。孤立的 ToolMessage 会导致 LLM 困惑，需要删除。
    # 连续删除开头的 ToolMessage，直到遇到 HumanMessage 或 AIMessage
    while trimmed and isinstance(trimmed[0], ToolMessage):
        trimmed = trimmed[1:]

    return trimmed
