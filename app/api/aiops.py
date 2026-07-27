"""
AIOps API — SSE 流式诊断接口。

POST /api/aiops
  → aiops_service.diagnose()
  → SSE 流式返回诊断进度 + 最终报告

这是第六阶段的核心接口，展示 Plan-Execute-Replan 工作流的完整过程。
"""

import json
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.services.aiops_service import diagnose
from app.core.auth_middleware import get_current_user

router = APIRouter(prefix="/api", tags=["aiops"])


class AIOpsRequest(BaseModel):
    session_id: str = Field(
        default="default",
        description="会话 ID，用于记忆隔离",
    )


@router.post("/aiops")
async def aiops_diagnose(req: AIOpsRequest, current_user: dict = Depends(get_current_user)):
    """启动 AIOps 智能诊断。

    SSE 事件类型：
      {"type": "plan", "data": {"steps": [...]}}
        — 诊断计划已制定，steps 是步骤列表

      {"type": "step_start", "data": "步骤描述"}
        — 开始执行一个步骤

      {"type": "step_result", "data": {"step": "...", "result": "..."}}
        — 步骤执行完成，含结果

      {"type": "replan", "data": {"new_plan": [...]}}
        — 计划被调整（Replanner 判定原计划需要修改）

      {"type": "report", "data": "完整诊断报告（Markdown）"}
        — 最终诊断报告

      {"type": "done"}
        — 诊断结束

      {"type": "error", "data": "错误信息"}
        — 出错
    """

    async def event_generator():
        thread_id = f"{current_user['id']}:{req.session_id}" if current_user else req.session_id
        async for event in diagnose(thread_id):
            yield {
                "event": "message",
                "data": json.dumps(event, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())
