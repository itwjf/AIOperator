"""
MCP PPT 服务 — 让 AI Agent 能够生成 PPT 文件。

通过 MCP 协议，Agent 可以创建演示文稿、添加页面、导出文件。

启动方式：
  python mcp_servers/ppt_server.py

访问：
  http://127.0.0.1:8005/mcp    — MCP 端点
  http://127.0.0.1:8005/health — 健康检查
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_servers.ppt_builder import get_builder

load_dotenv()
mcp = FastMCP("PPTTool")


@mcp.tool()
def add_table_slide(title: str, columns: list[str], rows_json: str, session_id: str = "default") -> str:
    """在当前 PPT 中添加一页数据表格页。

    使用场景：
      - 展示数据库查询结果
      - 展示数据明细、汇总统计等结构化数据

    参数：
        title:      本页标题，如 "5月交易明细"
        columns:    列名列表，如 ["日期", "摘要", "分类", "金额"]
        rows_json:  数据行的 JSON 字符串，每行是一个数组。
                   格式: '[["2026-05-10", "工资", "15000"], ["2026-05-12", "聚餐", "-156"]]'
                   注意必须是合法的 JSON 字符串（双引号）
        session_id: 会话 ID

    限制：
      - 最多 10 列，超出请拆分
      - 最多 50 行/页，超出部分自动截断

    返回：
        添加结果，含当前总页数
    """
    import json

    # 解析 JSON 字符串
    try:
        rows = json.loads(rows_json)
    except json.JSONDecodeError as e:
        example = '[["a","b"],["c","d"]]'
        return f"[错误] rows_json 不是合法的 JSON 字符串: {e}。示例格式: {example}"

    if not isinstance(rows, list):
        return f"[错误] rows_json 必须解析为数组，实际类型: {type(rows).__name__}"

    builder = get_builder(session_id)

    # 约束检查
    if len(columns) > 10:
        return f"[错误] 表格最多 10 列，当前 {len(columns)} 列。请拆分为多张表。"
    if len(rows) > 50:
        return f"[错误] 表格最多 50 行，当前 {len(rows)} 行。请用 WHERE 条件缩小范围。"

    builder.add_table_slide(title, columns, rows)
    return f"已添加表格页「{title}」，{len(columns)} 列 {len(rows)} 行，当前共 {builder.slide_count} 页。"


@mcp.tool()
def add_content_slide(title: str, bullets: list[str], session_id: str = "default") -> str:
    """在当前 PPT 中添加一页文字要点页。

    使用场景：
      - 添加分析结论、总结、建议等文字内容
      - 每页 5-8 个要点最佳

    参数：
        title:      本页标题
        bullets:    要点列表，每条一个字符串，如 ["CPU使用率正常", "内存有轻微波动"]
        session_id: 会话 ID

    返回：
        添加结果，含当前总页数
    """
    builder = get_builder(session_id)
    builder.add_content_slide(title, bullets)
    return f"已添加文字页「{title}」，共 {len(bullets)} 个要点，当前共 {builder.slide_count} 页。"


@mcp.tool()
def export_pptx(output_path: str = "", session_id: str = "default") -> str:
    """导出 PPT 文件。

    使用场景：
      - PPT 内容全部添加完毕后，调用此工具保存文件
      - 不传路径则自动保存到 output/ 目录

    参数：
        output_path: 输出路径，如 "output/5月财务分析.pptx"。不传则自动生成
        session_id:  会话 ID

    返回：
        保存文件的绝对路径
    """
    builder = get_builder(session_id)
    if not output_path:
        output_path = f"output/presentation_{session_id}.pptx"
    path = builder.save(output_path)
    return f"PPT 已保存到: {path}，共 {builder.slide_count} 页。"


@mcp.tool()
def create_presentation(title: str, subtitle: str = "", author: str = "", session_id: str = "default") -> str:
    """创建一个新的 PPT 演示文稿，包含封面页。

    使用场景：
      - 用户要求生成 PPT 时，先调用此工具初始化
      - 创建后返回状态，后续可继续添加页面

    参数：
        title:      PPT 主标题（显示在封面）
        subtitle:   副标题（可选）
        author:     作者名（可选）
        session_id: 会话 ID，同一会话的多次调用共享同一个 PPT

    返回：
        创建结果描述，含当前页数
    """
    builder = get_builder(session_id)
    builder.add_cover(title, subtitle, author)
    return f"PPT 已创建。标题: {title}，副标题: {subtitle or '（无）'}，当前共 {builder.slide_count} 页。"


# === 健康检查 ===

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """健康检查端点，返回服务状态。"""
    return JSONResponse({"status": "ok", "service": "PPTTool"})


# 启动入口
if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8005, path="/mcp")
