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
    mcp_docker_url: str = "http://127.0.0.1:8006/mcp"
    mcp_search_url: str = "http://127.0.0.1:8007/mcp"

    # ---- Milvus 向量数据库 ----
    milvus_host: str = "127.0.0.1"
    milvus_port: int = 19530
    milvus_collection_name: str = "aiops_knowledge"

    # ---- Embedding 模型 ----
    embedding_model: str = "text-embedding-v4"  # DashScope 的向量化模型
    embedding_dimension: int = 1024  # text-embedding-v4 输出 1024 维

    # ---- 消息修剪 ----
    # 对话历史超过此数量时自动截断，防止超出 LLM token 限制
    max_chat_messages: int = 20

    # ---- Shell 工具配置 ----
    shell_timeout: int = 30       # 命令执行超时（秒）
    shell_max_output: int = 5000  # 输出截断字符数

    # ---- 数据库配置（MySQL）----
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "aioperator"

    # ---- 认证配置 ----
    jwt_secret_key: str = ""          # JWT 签名密钥（64 字节随机字符串）
    jwt_algorithm: str = "HS256"      # JWT 签名算法
    jwt_expire_hours: int = 24        # access_token 过期时间（小时）

    # ---- GitHub OAuth 配置 ----
    github_client_id: str = ""
    github_client_secret: str = ""
    github_redirect_uri: str = "http://127.0.0.1:9900/api/auth/github/callback"
    # GitHub 授权页 prompt 行为：
    #   - "select_account"（默认）：每次登录弹出账号选择器，便于切换账号
    #   - "login"：强制要求重新输入密码
    #   - 空字符串：静默复用当前登录态（单账号场景无多余一步）
    github_oauth_prompt: str = "select_account"

    # ---- MCP 安全配置 ----
    mcp_secret_token: str = ""

    # ---- LangSmith 可观测性 ----
    langchain_tracing_v2: bool = False
    langchain_endpoint: str = "https://api.smith.langchain.com"
    langchain_api_key: str = ""
    langchain_project: str = "aioperator"

    # ---- 对话历史持久化（Checkpointer）----
    # SQLite 文件存放目录；Docker 部署时挂载到 volume，保证重启不丢
    checkpoint_dir: str = "data"

    # ---- 日志配置 ----
    log_level: str = "INFO"  # DEBUG / INFO / WARNING / ERROR
    log_dir: str = "logs"    # 日志文件目录

    # 告诉 pydantic-settings 去读 .env 文件
    # env_file 找不到不会报错（比如生产环境用真正的环境变量）
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


# 全局唯一的配置实例 — 其他模块都 from config import settings 来用
settings = Settings()
