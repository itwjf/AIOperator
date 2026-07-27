"""
MCP 时间服务 — 把 get_current_time 拆成独立的 MCP Server。

通过 MCP 协议，这个工具可以被任何支持 MCP 的客户端调用，
不局限于当前 Python 项目。其他语言（Go、Java、Node.js）也能用。

启动方式：
  python mcp_servers/time_server.py

访问：
  http://127.0.0.1:8003/mcp    — MCP 端点
  http://127.0.0.1:8003/health — 健康检查
"""

from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_servers.shared import TokenCheckMiddleware

load_dotenv()

# 创建 MCP Server 实例
mcp = FastMCP("TimeTool")
mcp.add_middleware(TokenCheckMiddleware)

# 时区偏移映射（和本地工具保持一致）
TIMEZONE_MAP = {
    "Asia/Shanghai": "北京时间 (UTC+8)",
    "Asia/Tokyo": "东京时间 (UTC+9)",
    "Asia/Singapore": "新加坡时间 (UTC+8)",
    "America/New_York": "美东时间 (UTC-5/UTC-4)",
    "America/Los_Angeles": "美西时间 (UTC-8/UTC-7)",
    "Europe/London": "伦敦时间 (UTC+0/UTC+1)",
    "UTC": "协调世界时",
}

OFFSET_MAP = {
    "Asia/Shanghai": 8,
    "Asia/Tokyo": 9,
    "Asia/Singapore": 8,
    "America/New_York": -5,
    "America/Los_Angeles": -8,
    "Europe/London": 0,
    "UTC": 0,
}


@mcp.tool()
def get_current_time(timezone_name: str = "Asia/Shanghai") -> str:
    """获取指定时区的当前日期和时间。

    使用场景：用户问「现在几点」、需要时间信息做判断。

    参数：
        timezone_name: 时区名称，如 Asia/Shanghai、America/New_York、UTC。
                      不传默认使用 Asia/Shanghai（北京时间）。

    返回：
        格式化的时间字符串，如 "2026-05-22 15:30:00 (北京时间)"
    """
    offset = OFFSET_MAP.get(timezone_name, 8)
    try:
        tz = timezone(timedelta(hours=offset))
    except Exception:
        tz = timezone(timedelta(hours=8))

    now = datetime.now(tz)
    label = TIMEZONE_MAP.get(timezone_name, timezone_name)
    return now.strftime(f"%Y-%m-%d %A %H:%M:%S ({label})")


# === 健康检查 ===

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """健康检查端点，返回服务状态。"""
    return JSONResponse({"status": "ok", "service": "TimeTool"})


# 启动入口
if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8003, path="/mcp")
