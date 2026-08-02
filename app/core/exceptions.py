"""
应用级异常定义 — 将底层技术异常翻译为用户友好的错误消息。

每层只捕获自己负责的外部调用异常，重新抛为本层异常：
  基础设施层（embedding, milvus）→ re-raise as AppException
  服务层（rag_agent, manual_agent）→ catch AppException → 返回友好消息
  API 层（FastAPI route）→ catch AppException → 返回 HTTP 错误响应

日志集成：
  每个异常在创建时会自动把 detail（技术细节）写入日志，
  确保排查问题时有关键信息，同时 message（友好提示）展示给用户。
"""

from app.core.logger import logger


class AIOperatorException(Exception):
    """所有应用异常的基类。

    每个子类都有两个信息：
      - message: 给用户看的友好提示
      - detail:  给开发者看的原始错误（用于日志排查）

    __init__ 时自动把 detail 写入 loguru 日志，
    这样开发者排查问题时不用四处找原始的异常堆栈。
    """

    def __init__(self, message: str, detail: str = ""):
        self.message = message
        self.detail = detail
        # 自动记录技术细节到日志
        if detail:
            logger.error("{} | 详情: {}", self.__class__.__name__, detail)
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


# === 工具容错相关 ===


class ToolUnavailableError(AIOperatorException):
    """工具依赖的外部服务不可用（如知识库、shell 命令环境）。

    这是「工具层」和「Agent 层」之间的语义化约定：
      工具在捕获底层异常后，转为抛出 ToolUnavailableError；
      Agent（system prompt + 逻辑）据此识别"工具不可用"信号，
      从而自主决定：改用其他工具 / 基于已有信息回答 / 如实告知用户。

    与 VectorDBError 的区别：
      VectorDBError 用于向量库技术故障的上抛；ToolUnavailableError
      是工具对调用方（Agent）的通用"当前不可用"信号，覆盖范围更广。
    """

    def __init__(self, detail: str = ""):
        super().__init__(
            message="该工具当前不可用，请根据实际情况选择其他方式继续处理",
            detail=detail,
        )
