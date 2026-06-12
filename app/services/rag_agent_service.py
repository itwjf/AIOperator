"""
RAG Agent 服务 — 将检索工具 + LLM + 记忆组合成一个能自动查阅知识库的 Agent。

核心流程：
  用户提问
    → Agent 决定：需要查知识库吗？
      → 需要：调用 retrieve_knowledge 工具 → 拿到文档 → LLM 基于文档回答
      → 不需要：LLM 直接回答

技术实现：
  - LangChain create_agent：自动处理「规划 → 调工具 → 拿结果 → 回答」循环
  - LangGraph MemorySaver：持久化对话历史，用 thread_id 区分会话
  - 消息修剪：通过 AgentMiddleware 在每次 LLM 调用前自动截断，防止爆 token
"""

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage

from app.core.llm_factory import create_llm
from app.core.message_trimmer import trim_conversation_history
from app.core.exceptions import AIOperatorException
from app.core.logger import logger
from app.tools.knowledge_tool import retrieve_knowledge
from app.config import settings


# 全局单例
_agent = None
_memory: MemorySaver | None = None


# === Message Trimmer Middleware ===
# 在每次 LLM 调用前自动修剪消息历史，防止超出 token 限制。
# AgentMiddleware.awrap_model_call 可以拦截并修改发往 LLM 的消息列表。


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
# 指导 Agent 的行为准则 — 直接影响 Agent 的行为

SYSTEM_PROMPT = """你是一个智能运维助手，专门帮助运维工程师排查系统问题。

你的能力：
1. **知识库检索**：当用户问题涉及具体技术排查、故障诊断、运维操作时，
   使用 `retrieve_knowledge` 工具搜索内部运维文档。
2. **通用对话**：对于不涉及技术排查的一般性问题（如打招呼、闲聊），直接回答。

重要规则：
- 如果调用了 retrieve_knowledge 工具，回答时必须引用工具返回的文档内容
- 如果知识库中没有相关信息，诚实告知用户，不要编造
- 回答格式使用 Markdown，代码片段使用代码块
- 用中文回答，技术术语保持英文
- 引用来源时注明文档名
"""


def _get_memory() -> MemorySaver:
    """获取 MemorySaver 单例 — 存储所有会话的对话历史。

    MemorySaver 是 LangGraph 的内存级检查点存储：
      - 每个 thread_id 对应一份独立的对话历史
      - 服务重启后历史会丢失
      - 生产环境应该换成 SqliteSaver 或 PostgresSaver
    """
    global _memory
    if _memory is None:
        _memory = MemorySaver()
    return _memory


def _get_agent():
    """获取 Agent 单例 — 首次调用时初始化。

    初始化做了什么？
      1. 创建 LLM 实例（temperature=0.7，适合对话）
      2. 注册知识检索工具
      3. 挂载 MemorySaver（用于会话记忆）
      4. 注入 system_prompt（定义 Agent 行为）
    """
    global _agent
    if _agent is None:
        llm = create_llm(temperature=0.7, streaming=True)

                # create_agent 会自动根据 system_prompt 和工具定义，构建一个能自动规划调用工具的 Agent。
                # 封装了 LangGraph 的 StateGraph + ToolNodes，开发者只需提供 LLM、工具和提示词。
                # Agent 内部会根据用户输入和对话历史，自动判断是否需要调用工具，并处理工具调用的结果。
                # 例如，用户问了一个技术问题，Agent 会判断需要查知识库，就自动调用 retrieve_knowledge 工具，拿到文档后再生成回答。
        _agent = create_agent(
            llm,                        # 语言模型
            tools=[retrieve_knowledge], # 工具列表
            checkpointer=_get_memory(), # 记忆（会话持久化）
            system_prompt=SYSTEM_PROMPT, # 行为准则 系统提示词
            middleware=[MessageTrimmerMiddleware(settings.max_chat_messages)],
        )
        logger.info("RAG Agent 初始化完成 — 模型: {}, 消息上限: {}",
                     settings.llm_model, settings.max_chat_messages)
    return _agent


# === 公共 API ===


async def query(question: str, session_id: str = "default") -> str:
    """非流式对话 — 等 Agent 完整执行完，返回最终答案。

    Agent 内部会自动判断是否需要调用工具，
    所有工具调用对调用者透明。

    参数：
        question:   用户问题
        session_id: 会话 ID，同一 ID 的对话有记忆

    返回：
        Agent 的最终回答文本
    """
    try:
        agent = _get_agent()
        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=question)]},
            config={"configurable": {"thread_id": session_id}},
        )

        # result["messages"] 是完整的消息历史
        # 最后一条 AI 消息就是 Agent 的最终回答
        last_message = result["messages"][-1]
        return last_message.content
    except AIOperatorException as e:
        return f"❌ {e.message}"
    except Exception as e:
        return f"❌ 服务暂时不可用，请稍后重试（详情: {e}）"


async def query_stream(question: str, session_id: str = "default"):
    """流式对话 — 异步生成器，逐 token 产出 Agent 的响应。

    相比非流式的优势：
      - 用户能实时看到回答逐字出现
      - 能展示工具调用状态（正忙、正在搜索知识库等）

    产出的字典格式：
      {"type": "content", "data": "token"}      — 文本 token
      {"type": "tool_start", "data": "工具名"}   — 开始调用工具
      {"type": "done"}                           — 对话结束
      {"type": "error", "data": "错误信息"}      — 出错
    """
    agent = _get_agent()

    try:
        # stream_mode="messages" 返回 (message_chunk, metadata) 元组
        # message_chunk 是 AIMessageChunk 或 ToolMessage
        async for chunk, metadata in agent.astream(
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

            # 检测工具返回消息（不要发给用户）
            from langchain_core.messages import ToolMessage
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
        yield {"type": "error", "data": f"服务暂时不可用，请稍后重试（详情: {e}）"}
