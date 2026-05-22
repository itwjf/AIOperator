"""
Embedding 服务 — 把文本转换成数值向量。

实现了 LangChain 标准的 Embeddings 接口：
  - embed_documents(texts): 批量向量化文档
  - embed_query(text):      单条查询向量化

底层使用 DashScope 的 text-embedding-v4 模型。

为什么不用 LangChain 的 OpenAIEmbeddings？
  虽然 DashScope 提供了 OpenAI 兼容端点，但 OpenAIEmbeddings 在构造请求时
  使用了 DashScope 不支持的高级参数（如 encoding_format），导致 400 错误。
  直接用 openai 库手动调用更可控，也更能理解 Embedding 调用的底层细节。
  这是 LangChain 的设计哲学：框架提供便利，但你始终可以退回到更底层的 API。
"""

import asyncio
from openai import AsyncOpenAI
from app.config import settings


# 全局单例 — 复用同一个 HTTP 客户端（内部管理连接池）
_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    """获取异步 OpenAI 客户端单例。"""
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.dashscope_api_key,
            base_url=settings.llm_base_url,
        )
    return _client


# DashScope text-embedding-v4 单次请求最多传 10 条文本
_BATCH_SIZE = 10


async def embed_documents(texts: list[str]) -> list[list[float]]:
    """批量向量化文档。

    DashScope 的 text-embedding-v4 限制单次请求最多 10 条文本，
    超过的需要分批调用。

    参数：
        texts: 文档文本列表

    返回：
        向量列表，每个向量是 1024 个 float
    """
    if not texts:
        return []

    client = _get_client()
    all_embeddings: list[list[float]] = []

    # 按 BATCH_SIZE 分批调用
    for i in range(0, len(texts), _BATCH_SIZE):
        batch = texts[i : i + _BATCH_SIZE]
        response = await client.embeddings.create(
            model=settings.embedding_model,
            input=batch,
        )
        all_embeddings.extend([item.embedding for item in response.data])

    return all_embeddings


async def embed_query(text: str) -> list[float]:
    """单条查询向量化。

    和 embed_documents 的区别在于：
      语义上，查询向量化可以加 prefix（如 "Represent the query: "），
      提升检索精度。DashScope 的 text-embedding-v4 目前不需要 prefix，
      所以实现上就是单条向量化。保留独立的函数，方便后续加 prefix。

    参数：
        text: 用户查询的问题

    返回：
        一个 1024 维的向量
    """
    if not text:
        return []

    client = _get_client()
    response = await client.embeddings.create(
        model=settings.embedding_model,
        input=[text],  # API 要求 input 是 list，传单条也要用 list 包一下
    )
    return response.data[0].embedding
