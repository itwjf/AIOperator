"""
应用配置 — 使用 pydantic-settings 从 .env 文件加载所有配置项。

为什么用 pydantic-settings 而不是 os.getenv()？
  - 自动类型转换（str/int/bool 不用手动 cast）
  - 字段名即配置名，不需要到处写字符串 key
  - 新增配置项只需加一个字段，IDE 有自动补全
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """应用的全局配置，所有字段自动从 .env 读取。"""

    # ---- 应用基础配置 ----
    app_name: str = "AIOperator"
    app_version: str = "0.1.0"
    app_host: str = "127.0.0.1"
    app_port: int = 9900
    debug: bool = True

    # ---- LLM 配置（阿里云 DashScope / 百炼平台）----
    # 通过 OpenAI 兼容接口调用通义千问，所以用 langchain_openai.ChatOpenAI
    dashscope_api_key: Optional[str] = None
    llm_model: str = "qwen-plus"  # qwen-plus 性价比最高，学习够用
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_temperature: float = 0.7  # 0=确定性强，0.7=有一定创造性

    # ---- MCP Server 地址 ----
    # 本地开发用 127.0.0.1，Docker 部署用容器名（mcp-time / mcp-db / mcp-ppt）
    mcp_time_url: str = "http://127.0.0.1:8003/mcp"
    mcp_db_url: str = "http://127.0.0.1:8004/mcp"
    mcp_ppt_url: str = "http://127.0.0.1:8005/mcp"

    # ---- Milvus 向量数据库 ----
    milvus_host: str = "127.0.0.1"
    milvus_port: int = 19530
    milvus_collection_name: str = "aiops_knowledge"

    # ---- Embedding 模型 ----
    embedding_model: str = "text-embedding-v4"  # DashScope 的向量化模型
    embedding_dimension: int = 1024  # text-embedding-v4 输出 1024 维

    # 告诉 pydantic-settings 去读 .env 文件
    # env_file 找不到不会报错（比如生产环境用真正的环境变量）
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


# 全局唯一的配置实例 — 其他模块都 from config import settings 来用
settings = Settings()
