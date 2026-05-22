"""
Replanner 节点 — 评估诊断进度，决定下一步行动。

三种决策：
  - respond  — 信息够了，生成最终报告
  - continue — 计划合理，继续执行下一步
  - replan   — 原计划需要调整，用新步骤替换

保护机制（防止死循环）：
  1. 已执行步骤 >= 5 → 强制 respond（不管还剩多少步骤）
  2. replan 时新步骤数不超过当前剩余步骤数
"""

from typing import Optional, Literal
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm_factory import create_llm


class Act(BaseModel):
    """Replanner 的决策输出。"""
    action: Literal["respond", "continue", "replan"] = Field(
        description="下一步行动：respond=生成报告, continue=继续执行, replan=调整计划"
    )
    reasoning: str = Field(
        description="决策理由，简要说明为什么做这个决定"
    )
    new_plan: Optional[list[str]] = Field(
        default=None,
        description="如果 action=replan，提供新的步骤列表（替换剩余步骤）",
    )


REPLANNER_SYSTEM_PROMPT = """你是一个 SRE 运维专家。评估诊断进度，决定下一步。

## 决策指南

- **respond**：已收集足够信息，可以生成诊断报告。适用场景：
  - 所有关键步骤已完成
  - 已定位到问题根因
  - 虽然没有完成全部步骤，但已有足够信息输出结论

- **continue**：计划合理，继续执行下一步。适用场景：
  - 还有步骤未执行
  - 当前结果没有发现需要改变计划的新情况
  - 信息还不够，需要继续收集

- **replan**：原计划需要调整。适用场景：
  - 发现了预期之外的情况（如知识库返回了关键线索）
  - 原计划的某些步骤不切实际
  - 需要增加新的调查方向

## 重要规则

1. 如果所有步骤都已执行完，必须 respond
2. 如果已执行的步骤已经定位到明确根因，优先 respond
3. replan 时新步骤必须具体可执行，数量不超过当前剩余步骤数
4. 用中文输出"""


async def run_replanner(state: dict) -> dict:
    """Replanner 节点：评估进度，决定下一步。

    保护机制（内置于代码逻辑，不依赖 LLM）：
      - past_steps >= 5 → 强制 respond
      - 如果 plan 为空 → 强制 respond
    """
    plan = state.get("plan", [])
    past_steps = state.get("past_steps", [])

    # 保护机制 1：所有步骤已完成 → 强制 respond
    if not plan:
        return {"action": "respond"}

    # 保护机制 2：已执行过多步骤 → 强制 respond
    if len(past_steps) >= 5:
        return {"action": "respond"}

    # 构建评估上下文
    steps_done = "\n".join([
        f"  [{i+1}] {step}\n      结果：{result[:200]}"
        for i, (step, result) in enumerate(past_steps)
    ])
    steps_left = "\n".join([f"  [{i+1+len(past_steps)}] {s}" for i, s in enumerate(plan)])

    user_message = f"""## 原始任务
{state.get("input", "")}

## 已完成的步骤及结果
{steps_done if steps_done else "（尚无）"}

## 剩余待执行的步骤
{steps_left}

请评估当前进度，决定下一步行动（respond / continue / replan）。"""

    llm = create_llm(temperature=0, streaming=False)
    structured_llm = llm.with_structured_output(Act)

    result: Act = await structured_llm.ainvoke([
        SystemMessage(content=REPLANNER_SYSTEM_PROMPT),
        HumanMessage(content=user_message),
    ])

    output = {"action": result.action}

    if result.action == "replan" and result.new_plan:
        # 限制新计划步数不超过当前剩余
        max_new = len(plan)
        new_plan = result.new_plan[:max_new]
        output["plan"] = new_plan

    return output
