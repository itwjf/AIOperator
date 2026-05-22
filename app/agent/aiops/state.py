"""
Plan-Execute-Replan 状态定义。

核心概念 — Annotated[list, operator.add] reducer：
  past_steps 用 operator.add 做 reducer，
  每次节点返回 {"past_steps": [新元组]} 时，
  LangGraph 把新元组追加到现有列表末尾，而不是覆盖。

  这和 messages 的 add_messages reducer 是同样的机制，
  只不过 past_steps 存的是 (步骤描述, 执行结果) 元组。
"""

from typing import Annotated, TypedDict, List, Tuple
import operator


class PlanExecuteState(TypedDict):
    """Plan-Execute-Replan 工作流的状态。"""
    input: str
    plan: List[str]
    past_steps: Annotated[List[Tuple[str, str]], operator.add]
    response: str
    action: str  # "continue" | "respond" | "replan"
