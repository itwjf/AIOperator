"""
Executor 节点 — 执行诊断计划的当前步骤。

核心设计：
  - 只关注 plan 里的第一个步骤，不看原始任务
  - 用 create_agent 创建子 Agent（绑定了知识检索 + 时间工具）
  - 执行完把步骤从 plan 移除，追加到 past_steps

为什么「只看当前步骤」？
  如果把整个 plan + 原始任务都塞给 LLM，它会分心。
  只给当前步骤，LLM 才能专注执行一件事。
"""

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

from app.core.llm_factory import create_llm
from app.tools.knowledge_tool import retrieve_knowledge
from app.tools.time_tool import get_current_time
from app.tools.shell_tool import execute_shell

# 执行器可用的工具
EXECUTOR_TOOLS = [retrieve_knowledge, get_current_time, execute_shell]

# 执行器子 Agent（单例）
_executor_agent = None

EXECUTOR_SYSTEM_PROMPT = """你是一个 SRE 运维专家，正在执行诊断计划中的**当前步骤**。

你会收到需要执行的步骤描述，请：
  1. 根据步骤描述，选择合适的工具来获取信息
  2. 如果步骤涉及知识检索，用 retrieve_knowledge 工具
  3. 如果需要查看系统状态/资源/进程/网络，用 execute_shell 工具执行只读诊断命令
  4. 如果需要时间信息，用 get_current_time 工具
  5. 执行完给出简洁的结果描述，说明发现了什么

工具容错（重要）：
- 当某个工具返回「[工具不可用]」「[执行失败]」「[超时]」「连接失败」等不可用信号时，
  不要反复重试同一工具，也不要因此卡住。
- 请根据当前步骤需求自主决策：改用其他可用工具 / 基于已有信息继续 / 如实记录不可用。
- 例如知识库检索不可用时，可改用 execute_shell 直接查询系统现状来完成当前步骤。

注意：
  - 只执行当前这一个步骤，不要尝试执行整个计划
  - 如果不需要调工具，直接给出分析结果
"""


def _get_executor_agent():
    global _executor_agent
    if _executor_agent is None:
        llm = create_llm(temperature=0.3, streaming=False)
        _executor_agent = create_agent(
            llm,
            tools=EXECUTOR_TOOLS,
            system_prompt=EXECUTOR_SYSTEM_PROMPT,
        )
    return _executor_agent


async def run_executor(state: dict) -> dict:
    """Executor 节点：执行 plan 中的第一个步骤。

    流程：
      1. 取出 plan[0] 作为当前步骤
      2. 构建聚焦消息（只包含当前步骤 + 已完成步骤的上下文）
      3. 子 Agent 执行 → 获取结果
      4. 返回：plan 移除第一步，past_steps 追加执行记录
    """
    plan = state.get("plan", [])
    past_steps = state.get("past_steps", [])

    if not plan:
        return {}

    current_step = plan[0]

    # 构建执行上下文：当前步骤 + 已完成步骤的简要回顾
    context_parts = [f"当前步骤：{current_step}"]
    if past_steps:
        done = "\n".join([f"  [{i+1}] {s} → {r[:150]}" for i, (s, r) in enumerate(past_steps)])
        context_parts.append(f"已完成的步骤及结果：\n{done}")
        context_parts.append("请基于已完成步骤的结果，继续执行当前步骤。")

    task = "\n\n".join(context_parts)

    agent = _get_executor_agent()
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=task)]}
    )

    answer = result["messages"][-1].content

    return {
        "plan": plan[1:],  # 移除已执行的步骤
        "past_steps": [(current_step, answer)],
    }
