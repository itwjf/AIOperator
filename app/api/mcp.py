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
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.api.chat import ChatRequest
from app.services.mcp_agent_service import chat, chat_stream, get_all_tools_info

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


@router.get("/tools")
async def list_tools():
    """列出所有可用工具（本地 + MCP 远程）"""
    return get_all_tools_info()


@router.post("/chat")
async def mcp_chat(req: ChatRequest):
    """非流式对话 — 使用本地 + MCP 远程工具。"""
    answer = await chat(req.question, req.session_id)
    return {"answer": answer}


@router.post("/chat_stream")
async def mcp_chat_stream(req: ChatRequest):
    """流式对话 — 使用本地 + MCP 远程工具。"""

    async def event_generator():
        async for event in chat_stream(req.question, req.session_id):
            yield {
                "event": "message",
                "data": json.dumps(event, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())
