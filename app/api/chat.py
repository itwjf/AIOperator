"""
聊天 API — 处理 /chat 和 /chat_stream 请求。

这一层只负责「接客」：
  - 解析请求参数
  - 调用 LLM
  - 把结果按约定格式返回
不包含任何业务逻辑（比如 RAG、Agent 编排），那些在服务层做。
"""

import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.core.llm_factory import create_llm_non_streaming, create_llm_streaming

router = APIRouter(prefix="/api", tags=["chat"])


# === 请求模型 ===
class ChatRequest(BaseModel):
    question: str = Field(..., description="用户输入的问题", min_length=1)


# === /chat — 非流式对话 ===
@router.post("/chat")
async def chat(req: ChatRequest):
    """非流式对话接口：接收问题，一次性返回 LLM 的完整回答。

    调用链路：
      HTTP POST /api/chat
        → ChatOpenAI.ainvoke(messages)   # 异步调用，等 LLM 生成完
        → 返回 {"answer": "完整回答文本"}
    """
    llm = create_llm_non_streaming()

    # messages 是对话历史的列表，每条消息包含 role 和 content
    # 目前最简单形式：只有一条 HumanMessage（用户消息）
    # 后面阶段会加入 SystemMessage、历史消息等
    from langchain_core.messages import HumanMessage

    response = await llm.ainvoke([HumanMessage(content=req.question)])

    # response 是 LangChain 的 AIMessage 对象
    # .content 是 LLM 返回的纯文本
    return {"answer": response.content}


# === /chat_stream — SSE 流式对话 ===
@router.post("/chat_stream")
async def chat_stream(req: ChatRequest):
    """流式对话接口：边生成边推送，用户能看到文字逐字出现。

    为什么用 SSE（Server-Sent Events）而不是 WebSocket？
      - SSE 基于标准 HTTP，更简单，浏览器原生支持 EventSource
      - 这个场景是单向推送（服务端 → 客户端），不需要双向通信
      - FastAPI 配合 sse-starlette 实现很方便

    SSE 事件格式：
      event: message
      data: {"type": "content", "data": "文本片段"}

      event: message
      data: {"type": "done"}
    """

    async def event_generator():
        """异步生成器 — 逐 token 产出 SSE 事件。

        LangChain 的 astream() 返回一个异步迭代器：
          - 流式模式下，每次 yield 一个 token 的增量内容
          - token 不等于字，可能是一个字、一个词、甚至标点符号
          - 非流式模式下，astream() 也可以工作，但只会 yield 一次完整结果
        """
        llm = create_llm_streaming()
        from langchain_core.messages import HumanMessage

        try:
            # astream() 返回 AsyncIterator[AIMessageChunk]
            # 每个 chunk 的 .content 是当前 token 的增量文本
            async for chunk in llm.astream(
                [HumanMessage(content=req.question)]
            ):
                token = chunk.content
                if token:  # 有些 chunk 可能为空（如工具调用占位），跳过
                    yield {
                        "event": "message",
                        "data": json.dumps(
                            {"type": "content", "data": token},
                            ensure_ascii=False,
                        ),
                    }

            # 告诉客户端：流结束了
            yield {
                "event": "message",
                "data": json.dumps({"type": "done"}, ensure_ascii=False),
            }

        except Exception as e:
            # 异常时也要发事件给前端，让它知道出错了
            yield {
                "event": "message",
                "data": json.dumps(
                    {"type": "error", "data": str(e)}, ensure_ascii=False
                ),
            }

    return EventSourceResponse(event_generator())
