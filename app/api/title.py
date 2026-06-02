"""
会话标题生成 API — 将对话内容浓缩为 3-8 字标题。

调用链路：
  POST /api/title/summarize
    → LLM（轻量调用，0.3 temperature）
    → 返回 {"title": "浓缩标题"}
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.llm_factory import create_llm

router = APIRouter(prefix="/api/title", tags=["title"])


class TitleRequest(BaseModel):
    content: str = Field(
        ...,
        description="对话内容（用户消息 + AI 回复摘要），用于生成标题",
        min_length=1,
        max_length=4000,
    )


@router.post("/summarize")
async def summarize(req: TitleRequest):
    """将对话内容浓缩为 3-8 字中文标题。

    使用与主对话相同的 LLM 配置，temperature=0.3 保证稳定输出。
    如果出现异常，返回空标题由前端降级处理。
    """
    llm = create_llm(temperature=0.3, streaming=False)
    

    prompt = (
        "你是一个标题生成助手。请根据以下对话内容，生成一个 3-8 个字的简洁中文标题，"
        "准确概括对话的核心主题。\n\n"
        "要求：\n"
        "- 只返回标题本身，不要加引号、标点、解释\n"
        "- 3-8 个汉字\n"
        "- 精确概括对话主题，不要泛泛而谈\n\n"
        f"对话内容：\n{req.content}"
    )

    try:
        response = await llm.ainvoke(prompt)
        title = response.content.strip()
        # 清理可能的引号和多余空白
        title = title.strip('"\'').strip()
        if not title:
            title = ""
        return {"title": title}
    except Exception:
        # LLM 调用失败时返回空标题，前端降级为截取标题
        return {"title": ""}
