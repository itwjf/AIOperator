"""
会话管理 API — 会话的创建、列表、删除、重命名。
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from app.core.auth_middleware import get_current_user
from app.core.checkpoint import delete_thread_all
from app.services import session_service, message_service

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


# 前端 mode 值 → 后端合法 agent_type 的映射
# 前端 ModeSwitcher 使用 chat/agent/mcp/aiops，后端仅接受 rag/manual/mcp/aiops
_MODE_MAP = {"chat": "rag", "agent": "manual", "mcp": "mcp", "aiops": "aiops"}


class CreateSessionRequest(BaseModel):
    session_id: str = Field(..., description="前端生成的 UUID 会话 ID")
    agent_type: str = Field(default="rag", description="Agent 类型")
    title: str | None = Field(default=None, description="会话标题")


class RenameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=100, description="新标题")


@router.get("")
async def list_sessions(current_user: dict = Depends(get_current_user)):
    """获取当前用户的会话列表。"""
    return session_service.list_sessions(current_user["id"])


@router.post("")
async def create_session(req: CreateSessionRequest, current_user: dict = Depends(get_current_user)):
    """创建新会话。"""
    # 前端 mode 值映射为后端合法 agent_type，兜底避免 400
    agent_type = _MODE_MAP.get(req.agent_type, req.agent_type)
    if agent_type not in ("rag", "manual", "mcp", "aiops"):
        raise HTTPException(status_code=400, detail="不支持的 Agent 类型")
    return session_service.create_session(
        current_user["id"], req.session_id, agent_type, req.title
    )


@router.delete("/{session_id}")
async def delete_session(session_id: str, current_user: dict = Depends(get_current_user)):
    """删除会话。

    清理三处数据：
      1. MySQL sessions 表（含 messages 表，见 session_service.delete_session）
      2. SQLite checkpointer 中该线程在 rag/manual/mcp/aiops 四种 Agent 的记忆
    """
    if not session_service.delete_session(current_user["id"], session_id):
        raise HTTPException(status_code=404, detail="会话不存在")

    # 同步清理四种 Agent 在 SQLite 中的对话记忆（thread_id = f"{user_id}:{session_id}"）
    thread_id = f"{current_user['id']}:{session_id}"
    await delete_thread_all(thread_id)

    return {"status": "ok"}


@router.put("/{session_id}/title")
async def rename_session(
    session_id: str, req: RenameRequest, current_user: dict = Depends(get_current_user)
):
    """重命名会话。"""
    if not session_service.update_session_title(current_user["id"], session_id, req.title):
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"status": "ok"}


@router.get("/{session_id}/messages")
async def get_session_messages(
    session_id: str, current_user: dict = Depends(get_current_user)
):
    """获取指定会话的历史消息（只返回用户与助手的对话，过滤工具消息）。"""
    session_fk = session_service.get_session_internal_id(current_user["id"], session_id)
    if session_fk is None:
        return {"messages": []}
    rows = message_service.get_messages(session_fk, limit=100)
    messages = [
        {"role": m["role"], "content": m["content"], "created_at": m["created_at"]}
        for m in rows
        if m["role"] in ("user", "assistant")
    ]
    return {"messages": messages}
