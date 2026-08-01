"""
Agent API — 使用手动搭建的 Agent 图（非 create_agent）。

和 /api/chat 的区别：
  - /api/chat 用 create_agent（第四阶段，黑盒封装）
  - /api/agent/chat 用手动 StateGraph（第五阶段，透明的图结构）

除此之外，请求/响应格式完全一致。
"""

import json
from fastapi import APIRouter, HTTPException, Depends, Request
from sse_starlette.sse import EventSourceResponse

from app.api.chat import ChatRequest  # 复用同一个请求模型
from app.services.manual_agent_service import chat, chat_stream
from app.core.exceptions import AIOperatorException
from app.core.auth_middleware import get_current_user
from app.core.rate_limiter import limiter

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post("/chat")
@limiter.limit("30/minute")
async def agent_chat(request: Request, req: ChatRequest, current_user: dict = Depends(get_current_user)):
    """非流式对话 — 手动 Agent 图版本。

    内部用 StateGraph + ToolNode + bind_tools 实现，
    和 create_agent 功能等价但结构透明。
    """
    try:
        thread_id = f"{current_user['id']}:{req.session_id}" if current_user else req.session_id
        answer = await chat(req.question, thread_id)
        return {"answer": answer}
    except AIOperatorException as e:
        raise HTTPException(status_code=503, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent 服务异常: {e}")


@router.post("/chat_stream")
@limiter.limit("30/minute")
async def agent_chat_stream(request: Request, req: ChatRequest, current_user: dict = Depends(get_current_user)):
    """流式对话 — 手动 Agent 图版本。

    SSE 事件格式和 /api/chat_stream 完全一致：
      {"type": "content", "data": "文本片段"}
      {"type": "tool_start", "data": "工具名"}
      {"type": "done"}
      {"type": "error", "data": "错误信息"}
    """

    async def event_generator():
        thread_id = f"{current_user['id']}:{req.session_id}" if current_user else req.session_id
        async for event in chat_stream(req.question, thread_id):
            yield {
                "event": "message",
                "data": json.dumps(event, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())
