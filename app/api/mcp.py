"""
MCP API — 展示 MCP 远程工具 + 本地工具的协作。

接口：
  GET  /api/mcp/tools      — 列出所有可用工具（本地 + MCP 远程）
  POST /api/mcp/chat       — 使用混合工具集（本地 + MCP）对话
  POST /api/mcp/chat_stream — 流式版本

这演示了 MCP 的核心价值：
  本地工具 (retrieve_knowledge) + 远程工具 (get_current_time via MCP)
  被无缝组合进同一个 Agent。
"""

import json
from fastapi import APIRouter, HTTPException, Depends, Request
from sse_starlette.sse import EventSourceResponse

from app.api.chat import ChatRequest
from app.services.mcp_agent_service import chat, chat_stream, get_all_tools_info
from app.core.exceptions import AIOperatorException
from app.core.auth_middleware import get_current_user
from app.core.rate_limiter import limiter

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


@router.get("/tools")
@limiter.limit("30/minute")
async def list_tools(request: Request):
    """列出所有可用工具（本地 + MCP 远程）"""
    return get_all_tools_info()


@router.post("/chat")
@limiter.limit("30/minute")
async def mcp_chat(request: Request, req: ChatRequest, current_user: dict = Depends(get_current_user)):
    """非流式对话 — 使用本地 + MCP 远程工具。"""
    try:
        thread_id = f"{current_user['id']}:{req.session_id}" if current_user else req.session_id
        answer = await chat(req.question, thread_id)
        return {"answer": answer}
    except AIOperatorException as e:
        raise HTTPException(status_code=503, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MCP 服务异常: {e}")


@router.post("/chat_stream")
@limiter.limit("30/minute")
async def mcp_chat_stream(request: Request, req: ChatRequest, current_user: dict = Depends(get_current_user)):
    """流式对话 — 使用本地 + MCP 远程工具。"""

    async def event_generator():
        thread_id = f"{current_user['id']}:{req.session_id}" if current_user else req.session_id
        async for event in chat_stream(req.question, thread_id):
            yield {
                "event": "message",
                "data": json.dumps(event, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())
