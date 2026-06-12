"""
MCP Agent 服务 — 混合本地工具和 MCP 远程工具的 Agent。

核心教学点：
  本地工具（retrieve_knowledge）和 MCP 远程工具（get_current_time）
  被组合进同一个 Agent。Agent 不知道也不关心工具是本地的还是远程的
  —— 这就是 MCP 协议的核心价值：工具来源透明。

自愈设计：
  如果 MCP Server 没启动，Agent 也能正常工作，
  只是少了一个远程工具。Agent 会在回答中诚实告知。

消息修剪：
  通过 AgentMiddleware 在每次 LLM 调用前自动截断对话历史，
  防止超出 token 限制。
"""

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage

from app.core.llm_factory import create_llm
from app.core.message_trimmer import trim_conversation_history
from app.core.exceptions import AIOperatorException
from app.tools.knowledge_tool import retrieve_knowledge
from app.agent.mcp_client import get_mcp_client
from app.config import settings


# === Message Trimmer Middleware ===
# 在每次 LLM 调用前自动修剪消息历史，防止超出 token 限制。


class MessageTrimmerMiddleware(AgentMiddleware):
    """Agent 中间件：在每次模型调用前自动修剪消息历史。"""

    def __init__(self, max_messages: int = 20):
        super().__init__()
        self.max_messages = max_messages

    async def awrap_model_call(self, request, handler):
        """拦截模型调用，修剪消息后交给 handler 执行。"""
        if len(request.messages) > self.max_messages:
            trimmed = trim_conversation_history(
                list(request.messages), self.max_messages
            )
            request = request.override(messages=trimmed)
        return await handler(request)


# === System Prompt ===
SYSTEM_PROMPT = """你是一个智能运维助手，具备以下能力：

1. **知识库检索**（retrieve_knowledge 工具）：
   当用户问题涉及技术排查、故障诊断、运维操作时使用。

2. **时间查询**（get_current_time 工具）：
   当用户问「现在几点」或需要时间信息做判断时使用。

3. **数据库查询**（list_tables / describe_table / execute_query / get_row_count 工具）：
   当用户需要查看或分析数据库中的数据时使用。
   先 list_tables 了解有哪些表，再用 describe_table 看结构，最后 execute_query 查数据。

4. **PPT 生成**（create_presentation / add_table_slide / add_content_slide / export_pptx 工具）：
   当用户要求生成 PPT 或报告时使用。
   流程：create_presentation 初始化 → 根据需要交替使用 add_table_slide 和 add_content_slide
   → 最后 export_pptx 导出文件。

5. **通用对话**：
   不涉及以上工具的日常闲聊，直接回答。

重要规则：
- 调用工具后，基于工具返回的结果来回答
- 如果工具调用失败，诚实告知用户，尝试其他方式
- 回答用 Markdown 格式，中文回答
"""

# === 全局单例 ===
_agent = None
_memory: MemorySaver | None = None


def _get_memory() -> MemorySaver:
    global _memory
    if _memory is None:
        _memory = MemorySaver()
    return _memory


def get_all_tools_info() -> dict:
    """获取所有工具的信息（同步，供 API 调用）。"""
    local_tools = [
        {
            "name": retrieve_knowledge.name,
            "source": "local",
            "description": retrieve_knowledge.description,
        }
    ]

    mcp = get_mcp_client()
    mcp_tools_info = [
        {
            "name": t.name,
            "source": "mcp",
            "description": t.description,
        }
        for t in mcp._tools  # 读取缓存的工具
    ]

    return {
        "tools": local_tools + mcp_tools_info,
        "mcp_connected": mcp.is_connected,
    }


async def _get_agent():
    """获取 Agent 单例 — 组合本地 + MCP 远程工具。

    初始化流程：
      1. 获取本地工具列表
      2. 尝试获取 MCP 远程工具（自愈：失败则返回空列表）
      3. 合并 → create_agent
    """
    global _agent
    if _agent is None:
        # 重置 MCP 连接 → 强制重新获取工具定义（避免缓存旧签名）
        mcp = get_mcp_client()
        mcp.reset()

        # 本地工具：始终可用
        local_tools = [retrieve_knowledge]

        # MCP 远程工具：可能不可用（自愈）
        mcp_tools = await mcp.get_tools()

        # 合并工具列表
        all_tools = local_tools + list(mcp_tools)

        llm = create_llm(temperature=0.7, streaming=True)
        _agent = create_agent(
            llm,
            tools=all_tools,
            checkpointer=_get_memory(),
            system_prompt=SYSTEM_PROMPT,
            middleware=[MessageTrimmerMiddleware(settings.max_chat_messages)],
        )
    return _agent


async def chat(question: str, session_id: str = "default") -> str:
    """非流式对话 — MCP + 本地工具。"""
    try:
        agent = await _get_agent()
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=question)]},
            config={"configurable": {"thread_id": session_id}},
        )
        return result["messages"][-1].content
    except AIOperatorException as e:
        return f"❌ {e.message}"
    except Exception as e:
        return f"❌ 服务暂时不可用，请稍后重试（详情: {e}）"


async def chat_stream(question: str, session_id: str = "default"):
    """流式对话 — MCP + 本地工具。"""
    agent = await _get_agent()

    try:
        async for chunk, metadata in agent.astream(
            {"messages": [HumanMessage(content=question)]},
            config={"configurable": {"thread_id": session_id}},
            stream_mode="messages",
        ):
            from langchain_core.messages import ToolMessage

            if hasattr(chunk, "tool_calls") and chunk.tool_calls:
                for tc in chunk.tool_calls:
                    if tc.get("name"):
                        yield {"type": "tool_start", "data": tc["name"]}
                continue

            if isinstance(chunk, ToolMessage):
                continue

            token = getattr(chunk, "content", "")
            if token:
                yield {"type": "content", "data": token}

        yield {"type": "done"}

    except AIOperatorException as e:
        yield {"type": "error", "data": e.message}
    except Exception as e:
        yield {"type": "error", "data": f"服务暂时不可用，请稍后重试（详情: {e}）"}
