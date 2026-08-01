"""
消息修剪工具 — 防止对话历史超出 LLM 的 token 限制。

策略：滑动窗口
  - 当消息数量超过 max_messages 时，只保留最近的 N 条消息
  - 保留消息的语义完整性：不会在工具调用链中间截断

包含三个部分：
  1. trim_conversation_history — 滑动窗口修剪，确保 tool_calls 配对完整
  2. validate_message_sequence — 兜底校验，检查消息序列是否合法
  3. MessageTrimmerMiddleware   — Agent 中间件，自动修剪 + 校验
"""

from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage, AIMessage


def trim_conversation_history(
    messages: list[BaseMessage],
    max_messages: int = 20,
) -> list[BaseMessage]:
    """修剪对话历史，保留最近的 max_messages 条消息。

    修剪策略：
      1. 如果消息总数 ≤ max_messages，只修复孤儿 tool_calls，不裁剪
      2. 否则保留最近 max_messages 条
      3. 确保不截断工具调用链（开头 + 中段）：
         - 删除开头的孤立 ToolMessage（对应的 AIMessage tool_call 被裁掉了）
         - 删除开头/中段的孤立 AIMessage(tool_calls)（对应的 ToolMessage 缺失）

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
        return _repair_orphan_tool_calls(list(messages))

    # 保留最近 max_messages 条
    trimmed = list(messages[-max_messages:])

    # 修复开头工具调用链完整性（删除被裁掉对应消息的孤立 ToolMessage / AIMessage）
    while trimmed:
        first = trimmed[0]

        # 情况 1：开头是孤立的 ToolMessage
        # → 它对应的 AIMessage(tool_calls) 已被裁掉，删掉这个 ToolMessage
        if isinstance(first, ToolMessage):
            trimmed = trimmed[1:]
            continue

        # 情况 2：开头是带 tool_calls 的 AIMessage
        # → 检查后面是否紧跟足够的 ToolMessage 响应
        #   如果不够，说明对应的 ToolMessage 被裁掉了，删掉这个 AIMessage
        if isinstance(first, AIMessage) and getattr(first, "tool_calls", None):
            num_tool_calls = len(first.tool_calls)
            # 数一下紧随其后的 ToolMessage 数量
            following_tool_msgs = 0
            for i in range(1, len(trimmed)):
                if isinstance(trimmed[i], ToolMessage):
                    following_tool_msgs += 1
                else:
                    break
            if following_tool_msgs < num_tool_calls:
                # ToolMessage 不够，删掉这个孤立的 AIMessage(tool_calls)
                trimmed = trimmed[1:]
                continue
            # ToolMessage 够，配对完整，停止修剪
            break

        # 其他情况（HumanMessage / 无 tool_calls 的 AIMessage / SystemMessage），正常保留
        break

    # 修复中段的孤儿 AIMessage(tool_calls)（工具执行失败残留，会导致 LLM 400）
    return _repair_orphan_tool_calls(trimmed)


def _repair_orphan_tool_calls(messages: list[BaseMessage]) -> list[BaseMessage]:
    """删除中段「带 tool_calls 但后续没有足够 ToolMessage 响应」的孤儿 AIMessage。

    场景：Agent 调用工具时工具执行失败（抛异常），checkpointer 只保存了
    带 tool_calls 的 AIMessage，对应的 ToolMessage 未写入 → 记忆被污染。
    下次对话恢复该记忆发给 LLM 会报 400：
      "An assistant message with 'tool_calls' must be followed by tool messages"

    策略：从后往前扫描，遇到带 tool_calls 的 AIMessage，统计其后紧跟的
    ToolMessage 数量；若不足覆盖其 tool_calls，则删掉该 AIMessage。
    """
    if not messages:
        return messages

    result = list(messages)
    i = len(result) - 1
    while i >= 0:
        msg = result[i]
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            num_calls = len(msg.tool_calls)
            # 数紧随其后的 ToolMessage
            following = 0
            j = i + 1
            while j < len(result) and isinstance(result[j], ToolMessage):
                following += 1
                j += 1
            if following < num_calls:
                # 孤立的 AIMessage(tool_calls)，删掉它
                del result[i]
        i -= 1

    return result


def validate_message_sequence(messages: list[BaseMessage]) -> tuple[bool, list[str]]:
    """校验消息序列的 tool_calls 配对完整性。

    检查规则：每个带 tool_calls 的 AIMessage 后，必须紧跟对应数量的 ToolMessage，
    且每个 tool_call_id 都有对应的 ToolMessage 响应。
    违反此规则会导致 LLM API 返回 400 错误。

    Args:
        messages: 待校验的消息列表

    Returns:
        (is_valid, issues)
        - is_valid: True 表示序列合法，可直接发给 LLM
        - issues: 不合法时的问题描述列表（供日志记录）
    """
    issues = []
    pending_call_ids: list[str] = []

    for i, msg in enumerate(messages):
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            # 遇到新的 tool_calls，检查上一组是否已全部响应
            if pending_call_ids:
                issues.append(
                    f"消息[{i}] 带新 tool_calls，但上一组 tool_calls "
                    f"(ids={pending_call_ids}) 未被全部响应"
                )
            pending_call_ids = [tc["id"] for tc in msg.tool_calls if tc.get("id")]

        elif isinstance(msg, ToolMessage):
            tool_call_id = getattr(msg, "tool_call_id", None)
            if tool_call_id in pending_call_ids:
                pending_call_ids.remove(tool_call_id)
            else:
                issues.append(f"消息[{i}] ToolMessage(tool_call_id={tool_call_id}) 无对应请求")

        else:
            # HumanMessage / 纯文本 AIMessage / SystemMessage：若有未响应的 tool_calls，报错
            if pending_call_ids:
                issues.append(
                    f"消息[{i}] 中断了 tool_calls 响应链，未响应 ids={pending_call_ids}"
                )
                pending_call_ids = []

    if pending_call_ids:
        issues.append(f"序列末尾仍有未响应的 tool_calls ids={pending_call_ids}")

    return (len(issues) == 0, issues)


# === Message Trimmer Middleware ===
# 在每次 LLM 调用前自动修剪消息历史，防止超出 token 限制。
# AgentMiddleware.awrap_model_call 可以拦截并修改发往 LLM 的消息列表。

from langchain.agents.middleware import AgentMiddleware
from app.core.logger import logger


class MessageTrimmerMiddleware(AgentMiddleware):
    """Agent 中间件：在每次模型调用前自动修剪消息历史。

    修剪后调用 validate_message_sequence 做兜底校验，
    若发现非法序列记录警告日志（不阻断，因为 trim 已处理主要场景）。
    """

    def __init__(self, max_messages: int = 20):
        super().__init__()
        self.max_messages = max_messages

    async def awrap_model_call(self, request, handler):
        """拦截模型调用，修剪消息后交给 handler 执行。

        始终执行修剪（内部会清理孤儿 tool_calls），
        这样即使消息数未超限也能修复工具执行失败残留的非法序列。
        """
        trimmed = trim_conversation_history(
            list(request.messages), self.max_messages
        )
        # 兜底校验：修剪后理论上不应有非法序列
        is_valid, issues = validate_message_sequence(trimmed)
        if not is_valid:
            logger.warning("修剪后消息序列仍不合法: {}", issues)
        request = request.override(messages=trimmed)
        return await handler(request)
