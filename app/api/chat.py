"""
聊天 API — 处理 /chat 和 /chat_stream 请求。

第四阶段改造：
  - 不再直接调裸 LLM，改用 RAG Agent（LLM + 知识检索工具 + 记忆）
  - 新增 session_id 参数，区分不同会话
  - 流式接口新增 tool_start 事件，展示工具调用状态

这一层只负责「接客」：
  - 解析请求参数
  - 调用 RAG Agent 服务
  - 把结果按约定格式返回
业务逻辑（Agent 编排、工具调用）在 services/rag_agent_service.py 中。
"""

import json
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.services.rag_agent_service import query, query_stream
from app.core.exceptions import AIOperatorException
from app.core.auth_middleware import get_current_user

router = APIRouter(prefix="/api", tags=["chat"])


# === 请求模型 ===
class ChatRequest(BaseModel):
    question: str = Field(..., description="用户输入的问题", min_length=1)
    session_id: str = Field(
        default="default",
        description="会话 ID，同一 ID 的对话有记忆。不传则使用默认会话。",
    )


# === /chat — 非流式对话（RAG Agent）===
@router.post("/chat")
async def chat(req: ChatRequest, current_user: dict = Depends(get_current_user)):
    """非流式对话接口：Agent 自动决定是否需要检索知识库。

    调用链路：
      HTTP POST /api/chat
        → RAG Agent（LLM + retrieve_knowledge 工具 + MemorySaver）
        → Agent 判断：需要查知识库？→ 调用工具 → 拿到文档 → 回答
                     不需要？→ 直接回答
        → 返回 {"answer": "完整回答文本"}
    """
    try:
        thread_id = f"{current_user['id']}:{req.session_id}" if current_user else req.session_id
        answer = await query(req.question, thread_id)
        return {"answer": answer}
    except AIOperatorException as e:
        raise HTTPException(status_code=503, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"对话服务异常: {e}")


# === /chat_stream — SSE 流式对话（RAG Agent）===
@router.post("/chat_stream")
async def chat_stream(req: ChatRequest, current_user: dict = Depends(get_current_user)):
    """流式对话接口：边生成边推送，能看到工具调用过程。

    SSE 事件类型：
      {"type": "content", "data": "文本片段"}  — AI 生成的文本 token
      {"type": "tool_start", "data": "工具名"} — 正在调用某个工具
      {"type": "done"}                          — 对话结束
      {"type": "error", "data": "错误信息"}     — 出错
    """

    async def event_generator():
        thread_id = f"{current_user['id']}:{req.session_id}" if current_user else req.session_id
        async for event in query_stream(req.question, thread_id):
            yield {
                "event": "message",
                "data": json.dumps(event, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())
