"""
向量存储管理器 — 封装 Milvus 的读写操作。

对外暴露三个核心操作：
  - add_documents(docs)      — 把文档分片入库
  - similarity_search(query) — 语义搜索
  - delete_by_source(path)   — 按来源文件删除

完整的数据写入链路：
  文档分片 → Embedding 向量化 → Milvus insert
  用户搜索 → Embedding 向量化 → Milvus search → 返回最相似的 k 条
"""

from app.core.milvus_client import get_milvus_client, ensure_collection
from app.services.embedding_service import embed_documents, embed_query
from app.services.document_splitter import Document
from app.config import settings
from app.core.exceptions import VectorDBError, EmbeddingServiceError


async def add_documents(docs: list[Document]) -> int:
    """将文档分片批量写入 Milvus。

    流程：提取文本 → 向量化 → 构造 Milvus 数据格式 → insert

    返回：成功插入的条数。
    """
    if not docs:
        return 0

    try:
        ensure_collection()
        client = get_milvus_client()

        # 提取所有文本
        texts = [doc.page_content for doc in docs]

        # 批量向量化
        vectors = await embed_documents(texts)

        # 构造 Milvus 插入数据
        data = []
        for doc, vector in zip(docs, vectors):
            data.append({
                "id": doc.id,
                "vector": vector,
                "content": doc.page_content,
                "metadata": doc.metadata,
            })

        result = client.insert(
            collection_name=settings.milvus_collection_name,
            data=data,
        )
        return result["insert_count"]
    except (VectorDBError, EmbeddingServiceError):
        raise  # 已经是应用异常，直接向上抛
    except Exception as e:
        raise VectorDBError(detail=f"文档入库失败: {e}") from e


async def similarity_search(
    query: str,
    k: int = 5,
) -> list[dict]:
    """语义搜索：找与 query 最相似的 k 个文档片段。

    流程：query 向量化 → Milvus search → 返回内容 + 元数据 + 相似度分数

    返回示例：
    [
        {
            "content": "CPU 使用率过高时应该先查看进程列表...",
            "source": "aiops-docs/cpu_troubleshooting.md",
            "title": "CPU 性能排查",
            "score": 0.92,
        },
        ...
    ]
    """
    try:
        ensure_collection()
        client = get_milvus_client()

        # 查询向量化
        query_vector = await embed_query(query)

        # Milvus 搜索
        results = client.search(
            collection_name=settings.milvus_collection_name,
            data=[query_vector],
            limit=k,
            output_fields=["content", "metadata"],
        )

        # 格式化结果
        formatted = []
        for hit in results[0]:  # results[0] 是第一个（也是唯一一个）查询向量的结果
            formatted.append({
                "content": hit["entity"]["content"],
                "source": hit["entity"]["metadata"].get("source", ""),
                "title": hit["entity"]["metadata"].get("title", ""),
                "score": hit["distance"],  # Milvus 返回的相似度分数
            })

        return formatted
    except (VectorDBError, EmbeddingServiceError):
        raise
    except Exception as e:
        raise VectorDBError(detail=f"语义搜索失败: {e}") from e


async def delete_by_source(file_path: str) -> int:
    """按来源文件删除对应的所有分片。

    用途：用户重新上传同名文件时，先删旧数据再入库。
    """
    try:
        ensure_collection()
        client = get_milvus_client()

        # 用 JSON 字段过滤：metadata 中的 source 字段匹配
        # Windows 路径的 \ 会被 Milvus 表达式解析器误解为转义字符，统一转成 /
        normalized_path = file_path.replace("\\", "/")
        results = client.query(
            collection_name=settings.milvus_collection_name,
            filter=f'metadata["source"] == "{normalized_path}"',
            output_fields=["id"],
        )

        if not results:
            return 0

        ids = [r["id"] for r in results]
        client.delete(
            collection_name=settings.milvus_collection_name,
            ids=ids,
        )
        return len(ids)
    except VectorDBError:
        raise
    except Exception as e:
        raise VectorDBError(detail=f"按来源删除失败: {e}") from e
