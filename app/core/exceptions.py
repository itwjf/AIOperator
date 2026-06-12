"""
应用级异常定义 — 将底层技术异常翻译为用户友好的错误消息。

每层只捕获自己负责的外部调用异常，重新抛为本层异常：
  基础设施层（embedding, milvus）→ re-raise as AppException
  服务层（rag_agent, manual_agent）→ catch AppException → 返回友好消息
  API 层（FastAPI route）→ catch AppException → 返回 HTTP 错误响应
"""


class AIOperatorException(Exception):
    """所有应用异常的基类。

    每个子类都有两个信息：
      - message: 给用户看的友好提示
      - detail:  给开发者看的原始错误（用于日志排查）
    """

    def __init__(self, message: str, detail: str = ""):
        self.message = message
        self.detail = detail
        super().__init__(message)

    def __str__(self):
        if self.detail:
            return f"{self.message}（详情: {self.detail}）"
        return self.message


# === LLM 相关 ===


class LLMServiceError(AIOperatorException):
    """LLM API 调用失败。

    可能原因：API Key 无效、网络不通、模型不存在、账号欠费、速率限制。
    """

    def __init__(self, detail: str = ""):
        super().__init__(
            message="AI 模型服务暂时不可用，请稍后重试",
            detail=detail,
        )


# === Embedding 相关 ===


class EmbeddingServiceError(AIOperatorException):
    """Embedding API 调用失败。

    可能原因：网络超时、批量过大、API Key 无效。
    """

    def __init__(self, detail: str = ""):
        super().__init__(
            message="文本向量化服务暂时不可用，请稍后重试",
            detail=detail,
        )


# === 向量数据库相关 ===


class VectorDBError(AIOperatorException):
    """Milvus 操作失败。

    可能原因：Milvus 服务未启动、网络不通、Collection 不存在、Schema 不匹配。
    """

    def __init__(self, detail: str = ""):
        super().__init__(
            message="知识库服务暂时不可用，请稍后重试",
            detail=detail,
        )


# === 文档处理相关 ===


class DocumentProcessError(AIOperatorException):
    """文档处理失败。

    可能原因：文件不存在、编码不支持、文件格式损坏、磁盘空间不足。
    """

    def __init__(self, detail: str = ""):
        super().__init__(
            message="文档处理失败，请检查文件格式是否正确",
            detail=detail,
        )


# === MCP 相关 ===


class MCPServiceError(AIOperatorException):
    """MCP 远程工具调用失败。

    可能原因：MCP Server 未启动、网络不通、工具参数错误。
    """

    def __init__(self, detail: str = ""):
        super().__init__(
            message="远程工具服务暂时不可用，部分功能可能受限",
            detail=detail,
        )
