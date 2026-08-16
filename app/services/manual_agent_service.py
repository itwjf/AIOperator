"""
手动 Agent 服务 — 不靠 create_agent，自己用 StateGraph + ToolNode 搭建。

这是第五阶段的核心教学代码。create_agent 内部就做了三件事：
  1. llm.bind_tools(tools)      → 把工具"绑"到 LLM，让它知道有哪些工具可用
  2. ToolNode(tools)             → 创建工具执行节点，真正调工具
  3. StateGraph + 条件边        → 搭循环图：LLM ↔ 工具执行

理解了这个文件，你就理解了 LangGraph Agent 的底层原理。

消息修剪：
  在 call_model 中，每次发给 LLM 前修剪对话历史。
  注意：只修剪发送给 LLM 的消息副本，StateGraph 的 state 仍保留完整历史
  （完整历史保存在 checkpointer 中，用于调试和审计）。

图的拓扑结构：

    START
      │
      ▼
  ┌──────┐    有 tool_calls    ┌───────┐
  │ agent │ ─────────────────→ │ tools  │
  └──────┘                     └───────┘
      │                            │
      │ 无 tool_calls              │ 结果返回 LLM
      ▼                            ▼
     END                       ┌──────┐
                               │ agent │ (再判断：继续调工具还是结束)
                               └──────┘
"""

from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from app.core.llm_factory import create_llm
from app.core.message_trimmer import trim_conversation_history
from app.core.checkpoint import get_checkpointer
from app.core.exceptions import AIOperatorException
from app.core.logger import logger
from app.tools.knowledge_tool import retrieve_knowledge
from app.tools.time_tool import get_current_time
from app.tools.calculator_tool import calculate
from app.tools.shell_tool import execute_shell
from app.config import settings

# === 全局工具清单 ===
TOOLS = [retrieve_knowledge, get_current_time, calculate, execute_shell]

# === System Prompt ===
SYSTEM_PROMPT = """你是一个智能运维助手，具备以下能力：

1. **知识库检索**（retrieve_knowledge 工具）：
   当用户问题涉及技术排查、故障诊断、运维操作、内部文档时使用。

2. **时间查询**（get_current_time 工具）：
   当用户问「现在几点」「当前时间」或需要时间信息做判断时使用。

3. **数值计算**（calculate 工具）：
   当用户需要精确计算、单位换算、时间戳转换时使用。
   如「xx 字节是多少 GB」「sqrt(144) 等于多少」。

4. **系统诊断**（execute_shell 工具）：
   当用户需要查看系统状态、资源使用、进程信息、网络连通性时使用。
   如「CPU 使用率多少」「磁盘满了没」「网络通不通」「容器运行状态」。
   支持常用的诊断命令（ps, free, df, ping, docker ps 等），
   所有操作均为只读，不会修改系统。

5. **通用对话**：
   对于不涉及以上工具的日常闲聊，直接回答。

重要规则：
- 调用工具后，基于工具返回的结果来回答，不要编造
- 回答格式使用 Markdown，代码用代码块
- 用中文回答，技术术语保持英文
- 引用知识库来源时注明文档名

工具容错（重要）：
- 当某个工具返回「[工具不可用]」「[执行失败]」「[超时]」「连接失败」等不可用信号时，
  不要反复重试同一工具，也不要因此卡住或绕圈子。
- 请根据用户实际需求自主决策：
    1) 改用其他可用工具（例如知识库不可用时，改用 execute_shell 直接查系统）；
    2) 基于已有信息直接回答；
    3) 如实告知用户某项服务暂不可用。
- 不要因为一个工具失败而无法完成回答。
"""

# === 全局单例 ===
_graph = None


# === State 定义 ===
# Annotated[list, add_messages] 是 LangGraph 的 reducer 机制：
# 每次节点返回 {"messages": [新消息]} 时，不是覆盖旧消息，
# 而是追加到消息列表末尾。
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]


# === 构建 Agent 图 ===
async def _build_graph():
    """手动搭建 Agent 工作流图。

    这是 create_agent 的等价替代，逐步展示内部构造：
      步骤 1: llm.bind_tools(tools) → 让 LLM 学会"说"要调哪个工具
      步骤 2: ToolNode(tools)      → 创建执行工具的节点
      步骤 3: StateGraph           → 搭图：LLM ↔ 工具
      步骤 4: 条件边               → 判断是否继续调工具
      步骤 5: checkpointer          → 持久化对话历史
    """
    llm = create_llm(temperature=0.7, streaming=True)

    # 步骤 1: bind_tools — 把工具的描述和参数 Schema 注入 LLM
    # 这之后 LLM 输出里可能出现 tool_calls，而不是纯文本
    llm_with_tools = llm.bind_tools(TOOLS)

    # 步骤 2: ToolNode — LangGraph 内置节点，自动执行 tool_calls
    # 当图的 state 里最后一条消息包含 tool_calls 时，
    # ToolNode 会逐个调用对应的工具函数，返回 ToolMessage
    tool_node = ToolNode(TOOLS)

    # 步骤 3: 定义 LLM 调用节点
    async def call_model(state: AgentState):
        """Agent 节点：把消息发给 LLM，返回响应。

        LLM 的响应可能有两种：
          - AIMessage(content="...")              → 纯文本回答，对话结束
          - AIMessage(tool_calls=[...])           → 要求调工具，继续循环

        消息修剪：
          发送给 LLM 前裁掉过期消息，防止超出 token 限制。
          StateGraph 的 state 保留完整历史（不修改），
          本次推理只使用最近 N 条消息的副本。
        """
        # 在消息前插入 system_prompt
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]

        # 消息修剪：只保留最近 max_chat_messages 条（不含 system_prompt）
        messages = trim_conversation_history(messages, settings.max_chat_messages)

        response = await llm_with_tools.ainvoke(messages)
        return {"messages": [response]}

    # 步骤 4: 条件边 — 判断下一步走向
    def should_continue(state: AgentState) -> str:
        """检查最后一条消息是否包含 tool_calls。

        返回 "tools" → 执行工具（然后回到 agent）
        返回 "__end__" → 对话结束
        """
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return "__end__"

    # 步骤 5: 搭图 + 编译
    graph = StateGraph(AgentState)

    # 注册节点
    graph.add_node("agent", call_model)
    graph.add_node("tools", tool_node)

    # 连线
    graph.set_entry_point("agent")  # START → agent
    graph.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "__end__": END},
    )
    graph.add_edge("tools", "agent")  # tools 执行完 → 回到 agent 再判断

    # 编译时注入 checkpointer，所有 state 变更自动持久化
    return graph.compile(checkpointer=await get_checkpointer("manual"))


async def _get_graph():
    global _graph
    if _graph is None:
        _graph = await _build_graph()
    return _graph


# === 公共 API ===


async def chat(question: str, session_id: str = "default") -> str:
    """非流式对话 — 手动 Agent 图。

    调用链路：
      graph.ainvoke({messages: [HumanMessage]}, config={thread_id})
        → agent 节点 → LLM 可能多次调工具 → 循环
        → 最终返回完整消息列表
    """
    try:
        graph = await _get_graph()
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=question)]},
            config={"configurable": {"thread_id": session_id}},
        )
        return result["messages"][-1].content
    except AIOperatorException as e:
        return f"❌ {e.message}"
    except Exception as e:
        logger.exception("手动 Agent 对话异常 — session_id: {}, question: {}", session_id, question)
        return f"❌ 服务暂时不可用，请稍后重试（详情: {e}）"


async def chat_stream(question: str, session_id: str = "default"):
    """流式对话 — 手动 Agent 图。

    和 create_agent 版的区别：
      这里用 graph.astream() 替代 agent.astream()，
      底层原理完全一样，只是图是自己手动搭的。
    """
    graph = await _get_graph()

    try:
        async for chunk, metadata in graph.astream(
            {"messages": [HumanMessage(content=question)]},
            config={"configurable": {"thread_id": session_id}},
            stream_mode="messages",
        ):
            # 检测工具调用
            if hasattr(chunk, "tool_calls") and chunk.tool_calls:
                for tc in chunk.tool_calls:
                    if tc.get("name"):
                        yield {"type": "tool_start", "data": tc["name"]}
                continue

            # 跳过工具返回消息
            if isinstance(chunk, ToolMessage):
                continue

            # 文本内容
            token = getattr(chunk, "content", "")
            if token:
                yield {"type": "content", "data": token}

        yield {"type": "done"}

    except AIOperatorException as e:
        yield {"type": "error", "data": e.message}
    except Exception as e:
        logger.exception("手动 Agent 流式对话异常 — session_id: {}, question: {}", session_id, question)
        yield {"type": "error", "data": f"服务暂时不可用，请稍后重试（详情: {e}）"}
