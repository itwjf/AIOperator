"""
Planner 节点 — 根据用户任务生成分步诊断计划。

输入：state.input（用户原始任务）
输出：state.plan（步骤列表）

关键设计：
  - 用 with_structured_output(Plan) 约束 LLM 输出结构化步骤
  - 先搜索知识库获取类似案例，作为参考
  - 把可用工具描述注入 prompt，让 LLM 知道「能做什么」
  - temperature=0：规划需要确定性，不要创造性
"""

from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm_factory import create_llm
from app.services.vector_store_manager import similarity_search
from app.tools.knowledge_tool import retrieve_knowledge
from app.tools.time_tool import get_current_time

# 执行器可用的工具列表（规划器需要知道有哪些工具可用）
AVAILABLE_TOOLS = [retrieve_knowledge, get_current_time]


class Plan(BaseModel):
    """LLM 产出的诊断计划。"""
    steps: list[str] = Field(
        description="诊断步骤列表，3-5 步，每步具体可执行",
        min_length=1,
        max_length=6,
    )


def _format_tools() -> str:
    """格式化工具描述，注入 Planner 的 system prompt。"""
    lines = []
    for t in AVAILABLE_TOOLS:
        lines.append(f"- **{t.name}**: {t.description}")
    return "\n".join(lines)


PLANNER_SYSTEM_PROMPT = """你是一个 SRE 运维专家。你的职责是**制定诊断计划**，而不是执行。

根据用户的问题描述，制定一个分步的诊断计划。每个步骤应该：
  1. 具体可执行（不是「分析问题」这种空话，而是「用 retrieve_knowledge 搜索 CPU 高排查文档」）
  2. 合理利用可用工具（检索知识库、获取当前时间等）
  3. 按逻辑顺序排列（先定位现象 → 再深入原因 → 最后给出建议）
  4. 每步只做一件事

可用工具：
{tools_description}

{similar_cases}

请为以下问题制定诊断计划（3-5 步）："""


async def run_planner(state: dict) -> dict:
    """Planner 节点：生成诊断计划。

    流程：
      1. 搜索知识库，获取与用户问题相关的类似案例
      2. 把工具描述 + 类似案例 + 用户任务发给 LLM
      3. 用 structured output 约束 LLM 返回步骤列表
    """
    user_input = state.get("input", "")

    # 搜索类似案例
    similar_cases_text = ""
    try:
        similar = await similarity_search(user_input, k=2)
        if similar:
            cases = "\n".join(
                [f"  - [{s['score']:.2f}] {s['content'][:200]}" for s in similar]
            )
            similar_cases_text = f"知识库中相关的历史案例（供参考）：\n{cases}"
    except Exception:
        similar_cases_text = "（知识库搜索暂时不可用）"

    # 构建 prompt
    tools_desc = _format_tools()
    system_prompt = PLANNER_SYSTEM_PROMPT.format(
        tools_description=tools_desc,
        similar_cases=similar_cases_text,
    )

    # 用 temperature=0 确保规划的确定性
    llm = create_llm(temperature=0, streaming=False)
    structured_llm = llm.with_structured_output(Plan)

    result: Plan = await structured_llm.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_input),
    ])

    return {"plan": result.steps}
