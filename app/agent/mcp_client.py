"""
MCP 客户端管理器 — 连接远程 MCP Server，获取工具列表。

核心设计（对应学习计划 7.3）：

1. **单例模式** — 全局只有一个 MCP 客户端实例，避免重复创建连接。
2. **自愈加载** — MCP Server 挂了也不影响主程序启动，
   Agent 用剩余的本地工具继续工作。
3. **重试机制** — 工具调用失败时自动重试（指数退避），
   最终失败返回错误信息而不是崩溃。
"""

import asyncio
import time
from langchain_mcp_adapters.client import MultiServerMCPClient
from app.config import settings


def _build_mcp_servers():
    """构建 MCP Server 配置，地址从环境变量读取（支持 Docker 部署）。"""
    return {
        "time_tool": {
            "transport": "streamable-http",
            "url": settings.mcp_time_url,
        },
        "db_tool": {
            "transport": "streamable-http",
            "url": settings.mcp_db_url,
        },
        "ppt_tool": {
            "transport": "streamable-http",
            "url": settings.mcp_ppt_url,
        },
    }

# 重试配置
MAX_RETRIES = 2           # 最大重试次数
RETRY_BASE_DELAY = 1.0    # 基础延迟（秒），指数退避：1s → 2s


class MCPClientManager:
    """MCP 客户端管理器。

    设计要点：
      - 单例：全应用共享一个实例
      - 自愈：get_tools() 失败时返回空列表，不阻塞 Agent 启动
      - 重试：_call_with_retry() 指数退避 + 兜底错误信息
    """

    _instance: "MCPClientManager | None" = None
    _client: MultiServerMCPClient | None = None
    _tools: list = []       # 缓存已获取的工具
    _connected: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _get_client(self) -> MultiServerMCPClient:
        """延迟创建 MCP 客户端（用到才连，不用不连）。"""
        if self._client is None:
            self._client = MultiServerMCPClient(_build_mcp_servers())
        return self._client

    def reset(self):
        """重置连接和工具缓存，强制下次 get_tools() 重新连接所有 MCP Server。

        使用场景：MCP Server 重启后工具签名变化时调用。
        """
        self._client = None
        self._tools = []
        self._connected = False

    async def get_tools(self) -> list:
        """获取所有 MCP 远程工具。

        自愈逻辑：
          - 连接成功 → 缓存工具列表 → 标记 connected=True
          - 连接失败 → 返回空列表 → Agent 仍可用本地工具
        """
        if self._tools:
            return self._tools

        try:
            client = self._get_client()
            tools = await client.get_tools()
            self._tools = list(tools)
            self._connected = True
            return self._tools
        except Exception:
            self._connected = False
            return []

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def call_tool(self, tool_name: str, **kwargs) -> str:
        """调用 MCP 工具（带重试机制）。

        重试策略：指数退避 — 第 1 次等 1s，第 2 次等 2s
        """
        last_error = ""
        for attempt in range(MAX_RETRIES + 1):
            try:
                tools = await self.get_tools()
                if not tools:
                    return f"[MCP 未连接] 无法调用 {tool_name}，MCP Server 不可用"

                for tool in tools:
                    if tool.name == tool_name:
                        result = await tool.ainvoke(kwargs)
                        return str(result)

                return f"[MCP 错误] 未找到工具 {tool_name}"

            except Exception as e:
                last_error = str(e)
                if attempt < MAX_RETRIES:
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    await asyncio.sleep(delay)
                self._tools = []  # 清缓存，下次重新获取

        return f"[MCP 错误] 调用 {tool_name} 失败（重试 {MAX_RETRIES} 次后）: {last_error}"


# 全局单例入口
def get_mcp_client() -> MCPClientManager:
    return MCPClientManager()
