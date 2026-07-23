"""
MCP Web 搜索服务 — 提供互联网搜索和网页内容获取功能。

搜索后端策略（自愈降级）：
  有 TAVILY_API_KEY → Tavily（高质量，专为 AI Agent 设计）
  无 TAVILY_API_KEY → DuckDuckGo（免费备选）

启动方式：
  python mcp_servers/search_server.py

访问：
  http://127.0.0.1:8007/mcp    — MCP 端点
  http://127.0.0.1:8007/health — 健康检查
"""

import os
import re
import sys
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

# 创建 MCP Server 实例
mcp = FastMCP("SearchTool")


# 简单的日志输出（MCP Server 独立进程，不依赖 app.core.logger）
def _log(level: str, msg: str):
    print(f"[SearchTool|{level}] {msg}", file=sys.stderr, flush=True)


# === 搜索后端初始化 ===

_tavily_client = None
_search_backend = None  # "tavily" 或 "duckduckgo"

# 尝试初始化 Tavily
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "").strip()
if TAVILY_API_KEY:
    try:
        from tavily import TavilyClient
        _tavily_client = TavilyClient(api_key=TAVILY_API_KEY)
        _search_backend = "tavily"
        _log("INFO", "搜索后端: Tavily（API Key 已配置）")
    except ImportError:
        _log("WARNING", "tavily-python 未安装，降级到 DuckDuckGo")
    except Exception as e:
        _log("WARNING", f"Tavily 初始化失败: {e}，降级到 DuckDuckGo")

# Tavily 不可用时使用 DuckDuckGo
if _search_backend is None:
    try:
        from duckduckgo_search import DDGS
        _search_backend = "duckduckgo"
        _log("INFO", "搜索后端: DuckDuckGo（免费备选）")
    except ImportError:
        _log("ERROR", "duckduckgo-search 未安装，搜索功能不可用")
    except Exception as e:
        _log("ERROR", f"DuckDuckGo 初始化失败: {e}")


# === 辅助函数 ===

def _strip_html(html: str) -> str:
    """去除 HTML 标签，提取纯文本。"""
    # 移除 script/style 标签及其内容
    text = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
    # 移除 HTML 标签
    text = re.sub(r'<[^>]+>', '', text)
    # 合并空白行
    text = re.sub(r'\n\s*\n', '\n\n', text)
    # 去除首尾空白
    text = text.strip()
    return text


def _format_search_error(msg: str) -> str:
    """统一错误格式。"""
    return f"[搜索错误] {msg}"


# === 工具 1: web_search ===

@mcp.tool()
def web_search(query: str, max_results: int = 5, search_depth: str = "basic") -> str:
    """搜索互联网，返回相关网页的标题、URL 和摘要。

    使用场景：
      - 用户问「最新的 Kubernetes 版本是什么」
      - 用户需要查找最新的技术资讯或文档
      - Agent 需要获取实时信息补充知识库

    参数：
        query: 搜索关键词或问题，如 "Kubernetes 最新版本 2026"
        max_results: 返回结果数量，范围 1-10，默认 5
        search_depth: 搜索深度，"basic"（快速）或 "advanced"（深度），默认 "basic"

    返回：
        Markdown 格式的搜索结果列表，每条含标题、URL、摘要。
    """
    max_results = min(max(max_results, 1), 10)

    if _search_backend == "tavily" and _tavily_client:
        try:
            depth = "advanced" if search_depth == "advanced" else "basic"
            response = _tavily_client.search(
                query=query,
                max_results=max_results,
                search_depth=depth,
            )
            results = response.get("results", [])
            if not results:
                return f"未找到与 '{query}' 相关的结果"

            lines = [f"搜索 '{query}' 共 {len(results)} 条结果（Tavily）："]
            for i, r in enumerate(results, 1):
                title = r.get("title", "无标题")
                url = r.get("url", "")
                content = r.get("content", "无摘要")
                score = r.get("score", 0)
                lines.append(f"\n{i}. **{title}**")
                lines.append(f"   URL: {url}")
                if score:
                    lines.append(f"   相关度: {score:.2f}")
                lines.append(f"   摘要: {content[:300]}")
            return "\n".join(lines)

        except Exception as e:
            _log("ERROR", f"Tavily 搜索失败: {e}")
            return _format_search_error(f"Tavily 搜索失败: {e}")

    elif _search_backend == "duckduckgo":
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
            if not results:
                return f"未找到与 '{query}' 相关的结果"

            lines = [f"搜索 '{query}' 共 {len(results)} 条结果（DuckDuckGo）："]
            for i, r in enumerate(results, 1):
                title = r.get("title", "无标题")
                href = r.get("href", "")
                body = r.get("body", "无摘要")
                lines.append(f"\n{i}. **{title}**")
                lines.append(f"   URL: {href}")
                lines.append(f"   摘要: {body[:300]}")
            return "\n".join(lines)

        except Exception as e:
            _log("ERROR", f"DuckDuckGo 搜索失败: {e}")
            return _format_search_error(f"DuckDuckGo 搜索失败: {e}")

    else:
        return _format_search_error("搜索服务当前不可用，请配置 TAVILY_API_KEY 或检查网络连接")


# === 工具 2: fetch_webpage ===

@mcp.tool()
def fetch_webpage(url: str, max_length: int = 3000) -> str:
    """获取指定 URL 的网页文本内容（用于深度阅读）。

    使用场景：
      - Agent 通过 web_search 找到相关页面后，需要阅读完整内容
      - 用户提供了 URL，要求总结网页内容

    参数：
        url: 要获取的网页 URL，如 "https://example.com/article"
        max_length: 返回的最大字符数，范围 500-10000，默认 3000

    返回：
        去除 HTML 标签后的纯文本内容。
    """
    import urllib.request
    import urllib.error

    max_length = min(max(max_length, 500), 10000)

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; AIOperator/0.1; +https://github.com/aioperator)"
            }
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            # 检查 Content-Type，只处理文本类型
            content_type = response.headers.get("Content-Type", "")
            if "text" not in content_type and "html" not in content_type:
                return _format_search_error(f"不支持的内容类型: {content_type}，仅支持文本/HTML 页面")

            html = response.read().decode("utf-8", errors="replace")

        # 去除 HTML 标签
        text = _strip_html(html)

        if not text.strip():
            return _format_search_error("网页内容为空或无法解析")

        # 截断
        if len(text) > max_length:
            text = text[:max_length] + "\n…（已截断）"

        return text

    except urllib.error.HTTPError as e:
        return _format_search_error(f"HTTP 错误 {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        return _format_search_error(f"URL 错误: {e.reason}")
    except Exception as e:
        _log("ERROR", f"fetch_webpage 失败: {e}")
        return _format_search_error(f"获取网页失败: {e}")


# === 健康检查 ===

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """健康检查端点，返回服务状态。"""
    return JSONResponse({"status": "ok", "service": "SearchTool"})


# 启动入口
if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8007, path="/mcp")
