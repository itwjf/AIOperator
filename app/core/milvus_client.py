"""
Milvus 客户端 — 管理 Milvus 向量数据库的连接和 Collection。

Collection（类比 SQL 表）的 Schema 设计：

| 字段      | 类型          | 说明                                |
|----------|---------------|-------------------------------------|
| id       | VARCHAR(256)  | 主键，用 UUID 生成                   |
| vector   | FLOAT_VECTOR  | Embedding 向量，1024 维              |
| content  | VARCHAR(65535)| 文档片段的原始文本                    |
| metadata | JSON          | 元数据（来源文件、标题、分块序号等）    |

为什么 metadata 用 JSON 而不是 VARCHAR？
  - JSON 字段可以按 key 过滤（如按来源文件删除）
  - 后续可能按文件、时间、类型等维度查询
"""

from pymilvus import (
    MilvusClient,
    DataType,
)

from app.config import settings


# 全局单例 — 整个应用只有一个 Milvus 客户端连接
_client: MilvusClient | None = None


def get_milvus_client() -> MilvusClient:
    """获取 Milvus 客户端单例。

    第一次调用时创建连接，后续直接返回已有实例。
    单例模式避免了反复建立 TCP 连接的开销。
    """
    global _client
    if _client is None:
        _client = MilvusClient(
            uri=f"http://{settings.milvus_host}:{settings.milvus_port}"
        )
    return _client


# === Collection Schema 定义 ===
# pymilvus 2.4+ 推荐用 MilvusClient.create_collection() 的方式定义 Schema
# 这里把 Schema 集中定义，建表和建索引都在一个函数里完成

COLLECTION_SCHEMA = {
    "id": {"dtype": DataType.VARCHAR, "is_primary": True, "max_length": 256},
    "vector": {"dtype": DataType.FLOAT_VECTOR, "dim": settings.embedding_dimension},
    "content": {"dtype": DataType.VARCHAR, "max_length": 65535},
    "metadata": {"dtype": DataType.JSON},
}


def ensure_collection() -> None:
    """确保 Collection 存在，不存在则创建。

    幂等操作 — 多次调用不会重复建表。
    生产环境应该在这里创建索引（IVF_FLAT / HNSW），
    学习阶段数据量小，用默认索引就够了。
    """
    client = get_milvus_client()
    collection_name = settings.milvus_collection_name

    if client.has_collection(collection_name):
        return  # Collection 已存在，不需要重复创建

    # 创建 Collection，同时定义 Schema
    client.create_collection(
        collection_name=collection_name,
        dimension=settings.embedding_dimension,
        metric_type="IP",  # IP = Inner Product（内积），即余弦相似度（向量已归一化时）
        primary_field_name="id",
        id_type=DataType.VARCHAR,
        max_length=256,
        vector_field_name="vector",
    )


def drop_collection() -> None:
    """删除 Collection — 仅用于测试/重置环境。"""
    client = get_milvus_client()
    if client.has_collection(settings.milvus_collection_name):
        client.drop_collection(settings.milvus_collection_name)
