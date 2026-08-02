"""
工具容错统一辅助模块。

设计目标：
  让所有工具在「依赖服务不可用 / 执行失败」时，返回格式统一、语义清晰的文案，
  方便 LLM 稳定识别「工具不可用」信号，并自主决策（换工具 / 基于已有信息 /
  如实告知用户），而不是被裸异常卡住或反复重试同一工具。

约定：
  所有错误文案统一以方括号前缀开头，作为 LLM 可识别的信号标签：
    [工具不可用]   → 工具依赖的外部服务挂了（如知识库、网络、shell 环境）
    [执行失败]     → 工具本身执行出错（如表达式错误、命令执行异常）
    [安全拒绝]     → 工具因安全校验拒绝了请求
    [超时]         → 工具执行超时

工具不应直接抛出裸异常给 Agent，而应将故障转成这些文案返回。
"""

from typing import Callable, TypeVar, ParamSpec

from app.core.logger import logger
from app.core.exceptions import AIOperatorException, ToolUnavailableError

# 统一前缀标签 — 供 Agent 的 system prompt 引用，作为"不可用"识别信号
TOOL_UNAVAILABLE_TAG = "[工具不可用]"
TOOL_EXEC_FAILED_TAG = "[执行失败]"
TOOL_SECURITY_REJECT_TAG = "[安全拒绝]"
TOOL_TIMEOUT_TAG = "[超时]"


def unavailable_hint(tool_name: str) -> str:
    """构造「工具不可用」的标准文案（不写死具体替代方案，让 AI 自主决策）。

    Args:
        tool_name: 工具名称，用于文案提示。

    Returns:
        一段友好的、供 LLM 判断的文案。
    """
    return (
        f"{TOOL_UNAVAILABLE_TAG} {tool_name} 服务当前不可用，本次无法获取该工具的数据。"
        "请根据用户实际需求自主选择处理方式：改用其他可用工具、"
        "基于已有信息回答，或明确告知用户该服务暂不可用。不要反复重试同一工具。"
    )


P = ParamSpec("P")
R = TypeVar("R")


def safe_call(
    tool_name: str,
    func: Callable[P, R],
    *args: P.args,
    **kwargs: P.kwargs,
) -> R:
    """统一容错包装：调用工具内部函数，异常时记录日志并抛出 ToolUnavailableError。

    工具函数内部不应再各自 try/except 一大段，而是调用这个包装器：
      1. 成功 → 原样返回结果
      2. 应用级异常（AIOperatorException）→ 转成 ToolUnavailableError（记录日志）
      3. 其他异常 → 记录日志，抛 ToolUnavailableError

    Args:
        tool_name: 工具名，用于日志和错误信息。
        func:      要调用的底层函数。
        *args:     传给 func 的位置参数。
        **kwargs:  传给 func 的关键字参数。

    Returns:
        func 的返回值。

    Raises:
        ToolUnavailableError: 底层调用失败时抛出。
    """
    try:
        return func(*args, **kwargs)
    except AIOperatorException as e:
        logger.warning("{} 工具不可用（应用异常）: {}", tool_name, e.detail)
        raise ToolUnavailableError(detail=f"{tool_name}: {e.detail}") from e
    except Exception as e:  # noqa: BLE001 - 工具层兜底所有异常
        logger.warning("{} 工具执行异常: {}", tool_name, e)
        raise ToolUnavailableError(detail=f"{tool_name}: {e}") from e
