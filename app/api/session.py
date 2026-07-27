"""
会话管理 API — 会话的创建、列表、删除、重命名。
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from app.core.auth_middleware import get_current_user
from app.services import session_service

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


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
    if req.agent_type not in ("rag", "manual", "mcp", "aiops"):
        raise HTTPException(status_code=400, detail="不支持的 Agent 类型")
    return session_service.create_session(
        current_user["id"], req.session_id, req.agent_type, req.title
    )


@router.delete("/{session_id}")
async def delete_session(session_id: str, current_user: dict = Depends(get_current_user)):
    """删除会话。"""
    if not session_service.delete_session(current_user["id"], session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"status": "ok"}


@router.put("/{session_id}/title")
async def rename_session(
    session_id: str, req: RenameRequest, current_user: dict = Depends(get_current_user)
):
    """重命名会话。"""
    if not session_service.update_session_title(current_user["id"], session_id, req.title):
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"status": "ok"}
