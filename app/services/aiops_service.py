"""
AIOps 诊断服务 — Plan-Execute-Replan 工作流编排。

图的拓扑结构：

    START
      │
      ▼
  ┌──────────┐
  │ planner   │  制定诊断计划
  └────┬─────┘
       │
       ▼
  ┌──────────┐
  │ executor  │  执行当前步骤（循环入口）
  └────┬─────┘
       │
       ▼
  ┌───────────┐
  │ replanner  │  评估进度，决定下一步
  └─────┬─────┘
        │
    ┌───┼───┐
    │   │   │
    ▼   ▼   ▼
  resp cont replan
    │   │   │
    │   └───┼──→ executor（循环）
    │       │
    ▼       │
┌──────────┐ │
│ reporter  │ │
└────┬─────┘ │
     │       │
     ▼       │
    END ◄────┘

关键保护机制：
  1. 已执行步骤 >= 5 → replanner 强制 respond（防止死循环）
  2. replan 时新步骤数不超过当前剩余步骤数
"""

from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.aiops.state import PlanExecuteState
from app.agent.aiops.planner import run_planner
from app.agent.aiops.executor import run_executor
from app.agent.aiops.replanner import run_replanner
from app.core.llm_factory import create_llm
from app.core.checkpoint import get_checkpointer
from app.core.exceptions import AIOperatorException

# === 全局单例 ===
_graph = None

# === 预设诊断 Prompt ===
DIAGNOSE_TEMPLATE = """请对当前系统进行全面诊断：

1. 分析系统整体状态（CPU、内存、磁盘、网络等关键指标）
2. 检查是否有告警或异常指标
3. 识别潜在的性能瓶颈和风险点
4. 如果发现问题，定位根因并给出修复建议
5. 如果无明显问题，给出优化建议

请按照你的诊断计划逐步执行，每步调用合适的工具获取信息。"""

# === Reporter 提示词 ===
REPORTER_PROMPT = """你是一个资深的 SRE 运维专家。请基于以下诊断过程，生成一份结构化的最终诊断报告。

## 原始诊断任务
{input}

## 已执行的诊断步骤和结果
{past_steps}

请生成包含以下部分的 Markdown 格式报告：

1. **诊断摘要** — 概述整个诊断过程和主要结论
2. **关键发现** — 列出诊断过程中发现的重要信息
3. **根因分析** — 如果定位到了问题根因，详细说明
4. **建议措施** — 具体的修复或优化建议（按优先级排列）
5. **后续步骤** — 建议的后续监控或深入调查方向"""


async def _run_reporter(state: dict) -> dict:
    """Reporter 节点：根据所有执行结果生成最终诊断报告。"""
    past_steps = state.get("past_steps", [])

    steps_text = "\n\n".join([
        f"### 步骤 {i+1}: {step}\n**执行结果**: {result}"
        for i, (step, result) in enumerate(past_steps)
    ])

    prompt = REPORTER_PROMPT.format(
        input=state.get("input", ""),
        past_steps=steps_text if steps_text else "（无诊断步骤记录）",
    )

    llm = create_llm(temperature=0.3, streaming=False)
    response = await llm.ainvoke([HumanMessage(content=prompt)])

    return {"response": response.content}


def _build_graph():
    """构建 Plan-Execute-Replan 工作流图。

    步骤：
      1. 创建 StateGraph，绑定 PlanExecuteState
      2. 注册 4 个节点：planner, executor, replanner, reporter
      3. 连线 + 条件边
      4. 编译（注入 checkpointer）
    """
    graph = StateGraph(PlanExecuteState)

    # 注册节点
    graph.add_node("planner", run_planner)
    graph.add_node("executor", run_executor)
    graph.add_node("replanner", run_replanner)
    graph.add_node("reporter", _run_reporter)

    # 连线
    graph.set_entry_point("planner")
    graph.add_edge("planner", "executor")
    graph.add_edge("executor", "replanner")

    # 条件边：replanner 根据 action 决定下一步
    def route_after_replan(state: PlanExecuteState) -> str:
        action = state.get("action", "continue")
        if action == "respond":
            return "reporter"
        # continue 或 replan 都回到 executor
        return "executor"

    graph.add_conditional_edges("replanner", route_after_replan, {
        "executor": "executor",
        "reporter": "reporter",
    })

    graph.add_edge("reporter", END)

    return graph.compile(checkpointer=get_checkpointer("aiops"))


def _get_graph():
    global _graph
    if _graph is None:
        _graph = _build_graph()
    return _graph


# === 公共 API ===


async def diagnose(session_id: str = "default"):
    """执行 AIOps 诊断（流式），逐节点产出进度事件。

    使用预设的诊断 prompt，自动制定计划并逐步执行。

    产出的 SSE 事件类型：
      {"type": "plan", "data": {"steps": [...]}}
      {"type": "step_start", "data": "步骤描述"}
      {"type": "step_result", "data": {"step": "...", "result": "..."}}
      {"type": "replan", "data": {"reasoning": "...", "new_plan": [...]}}
      {"type": "report", "data": "完整报告"}
      {"type": "done"}
      {"type": "error", "data": "错误信息"}
    """
    graph = _get_graph()
    initial_state = {"input": DIAGNOSE_TEMPLATE}
    config = {"configurable": {"thread_id": session_id}}

    try:
        prev_plan = []
        prev_past_steps_len = 0

        async for update in graph.astream(
            initial_state,
            config,
            stream_mode="updates",
        ):
            for node_name, node_output in update.items():
                if node_name == "planner":
                    plan = node_output.get("plan", [])
                    prev_plan = plan
                    yield {
                        "type": "plan",
                        "data": {"steps": plan},
                    }

                elif node_name == "executor":
                    new_plan = node_output.get("plan", prev_plan)
                    past_steps = node_output.get("past_steps", [])

                    # 检测当前执行的是哪个步骤
                    if len(past_steps) > prev_past_steps_len:
                        # 新步骤已执行
                        latest = past_steps[-1]
                        step_desc, step_result = latest
                        yield {
                            "type": "step_start",
                            "data": step_desc,
                        }
                        yield {
                            "type": "step_result",
                            "data": {"step": step_desc, "result": step_result},
                        }

                    prev_plan = new_plan
                    prev_past_steps_len = len(past_steps)

                elif node_name == "replanner":
                    action = node_output.get("action", "")
                    new_plan = node_output.get("plan")

                    if action == "replan" and new_plan:
                        yield {
                            "type": "replan",
                            "data": {"new_plan": new_plan},
                        }
                        prev_plan = new_plan

                elif node_name == "reporter":
                    response = node_output.get("response", "")
                    yield {
                        "type": "report",
                        "data": response,
                    }

        yield {"type": "done"}

    except AIOperatorException as e:
        yield {"type": "error", "data": e.message}
    except Exception as e:
        yield {"type": "error", "data": f"诊断服务暂时不可用，请稍后重试（详情: {e}）"}
