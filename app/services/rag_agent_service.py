"""
RAG Agent 服务 — 将检索工具 + LLM + 记忆组合成一个能自动查阅知识库的 Agent。

核心流程：
  用户提问
    → Agent 决定：需要查知识库吗？
      → 需要：调用 retrieve_knowledge 工具 → 拿到文档 → LLM 基于文档回答
      → 不需要：LLM 直接回答

技术实现：
  - LangChain create_agent：自动处理「规划 → 调工具 → 拿结果 → 回答」循环
  - LangGraph SqliteSaver：持久化对话历史到文件，用 thread_id 区分会话
  - 消息修剪：通过 AgentMiddleware 在每次 LLM 调用前自动截断，防止爆 token
"""

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

from app.core.llm_factory import create_llm
from app.core.message_trimmer import trim_conversation_history, MessageTrimmerMiddleware
from app.core.checkpoint import get_checkpointer
from app.core.exceptions import AIOperatorException
from app.core.logger import logger
from app.tools.knowledge_tool import retrieve_knowledge
from app.tools.calculator_tool import calculate
from app.tools.shell_tool import execute_shell
from app.config import settings


# 全局单例
_agent = None


# === System Prompt ===
# 指导 Agent 的行为准则 — 直接影响 Agent 的行为

SYSTEM_PROMPT = """你是一个智能运维助手，专门帮助运维工程师排查系统问题。

你的能力：
1. **知识库检索**：当用户问题涉及具体技术排查、故障诊断、运维操作时，
   使用 `retrieve_knowledge` 工具搜索内部运维文档。
2. **系统诊断**：当用户需要查看系统状态、资源使用、进程或网络信息时，
   使用 `execute_shell` 工具执行安全的诊断命令（如 free、df、ping、docker ps 等）。
3. **通用对话**：对于不涉及技术排查的一般性问题（如打招呼、闲聊），直接回答。

重要规则：
- 如果调用了 retrieve_knowledge 工具，回答时必须引用工具返回的文档内容
- 如果知识库中没有相关信息，诚实告知用户，不要编造
- 回答格式使用 Markdown，代码片段使用代码块
- 用中文回答，技术术语保持英文
- 引用来源时注明文档名

工具容错（重要）：
- 当某个工具返回「[工具不可用]」「[执行失败]」「[超时]」「连接失败」等不可用信号时，
  不要反复重试同一工具，也不要因此卡住或绕圈子。
- 请根据用户实际需求自主决策：
    1) 改用其他可用工具（例如知识库不可用时，改用 execute_shell 直接查系统）；
    2) 基于已有信息直接回答；
    3) 如实告知用户某项服务暂不可用。
- 不要因为一个工具失败而无法完成回答。
"""


async def _get_agent():
    """获取 Agent 单例 — 首次调用时初始化。

    初始化做了什么？
      1. 创建 LLM 实例（temperature=0.7，适合对话）
      2. 注册知识检索工具
      3. 挂载 AsyncSqliteSaver（用于会话记忆，持久化到文件）
      4. 注入 system_prompt（定义 Agent 行为）
    """
    global _agent
    if _agent is None:
        llm = create_llm(temperature=0.7, streaming=True)

        _agent = create_agent(
            llm,                        # 语言模型
            tools=[retrieve_knowledge, calculate, execute_shell], # 工具列表
            checkpointer=await get_checkpointer("rag"), # 记忆（会话持久化，SQLite）
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
        agent = await _get_agent()
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
    agent = await _get_agent()

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
