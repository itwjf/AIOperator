"""
MCP 数据库服务 — 让 AI Agent 能够从 MySQL 读取数据。

通过 MCP 协议，Agent 可以列出表、查看表结构、执行 SELECT 查询。
只读安全设计：拒绝一切写入/修改操作。

启动方式：
  python mcp_servers/db_server.py

访问：
  http://127.0.0.1:8004/mcp    — MCP 端点
  http://127.0.0.1:8004/health — 健康检查

环境变量（在 .env 中配置）：
  DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
"""

import os
import pymysql
from dotenv import load_dotenv
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

# 独立运行时加载 .env（不依赖 app.config）
load_dotenv()

# 创建 MCP Server 实例
mcp = FastMCP("DBTool")

from mcp_servers.shared import TokenCheckMiddleware
mcp.add_middleware(TokenCheckMiddleware)

# === 数据库连接 ===

# 默认查询限制 — 防止大结果集撑爆 Token
DEFAULT_LIMIT = 100
# SQL 白名单 — 只允许以这些关键字开头的语句
ALLOWED_PREFIXES = ("SELECT", "SHOW", "DESC", "DESCRIBE", "EXPLAIN")
# 敏感表黑名单 — 这些表不能被查询/描述（逗号分隔，通过环境变量配置）
_BLACKLIST: set[str] = set()


def _get_blacklist() -> set[str]:
    """延迟加载黑名单（首次调用时从环境变量读取并缓存）。"""
    global _BLACKLIST
    if not _BLACKLIST:
        raw = os.getenv("DB_BLACKLIST_TABLES", "")
        if raw.strip():
            _BLACKLIST = {t.strip().lower() for t in raw.split(",") if t.strip()}
    return _BLACKLIST


def _check_table_allowed(table_name: str) -> str | None:
    """检查表是否在黑名单中。通过返回 None，被拒返回错误信息。"""
    blacklist = _get_blacklist()
    if table_name.lower() in blacklist:
        return f"[安全拒绝] 表 `{table_name}` 在黑名单中，不允许访问。"
    return None


def _get_connection():
    """创建数据库连接（每次调用独立获取，用完即关，防止连接泄露）。"""
    return pymysql.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "aioperator"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def _is_read_only(sql: str) -> bool:
    """校验 SQL 是否为只读操作（白名单模式）。"""
    stripped = sql.strip().upper()
    return stripped.startswith(ALLOWED_PREFIXES)


def _format_query_result(columns: list, rows: list, sql: str) -> str:
    """将查询结果格式化为 Markdown 表格，便于 LLM 阅读。"""
    if not rows:
        return f"查询: `{sql}`\n\n结果: **（无匹配数据）**"

    # 表头
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join(["---"] * len(columns)) + " |"

    # 数据行（不超过 DEFAULT_LIMIT 条）
    body_lines = []
    for row in rows[:DEFAULT_LIMIT]:
        body_lines.append("| " + " | ".join(str(v) if v is not None else "NULL" for v in row.values()) + " |")

    lines = [
        f"查询: `{sql}`",
        f"返回: {len(rows)} 行（展示前 {min(len(rows), DEFAULT_LIMIT)} 行）",
        "",
        header,
        separator,
        *body_lines,
    ]

    if len(rows) > DEFAULT_LIMIT:
        lines.append(f"\n> ⚠️ 结果已截断，共 {len(rows)} 行仅展示前 {DEFAULT_LIMIT} 行。请加 WHERE 条件缩小范围。")

    return "\n".join(lines)


# === MCP 工具 ===


@mcp.tool()
def list_tables() -> str:
    """列出数据库中所有的表名。

    使用场景：
      - 不知道有哪些表时，先调此工具了解数据库结构
      - 确定下一步要查哪个表

    返回：
        表名列表（Markdown 格式）
    """
    try:
        conn = _get_connection()
        with conn.cursor() as cursor:
            cursor.execute("SHOW TABLES")
            tables = [row[list(row.keys())[0]] for row in cursor.fetchall()]
        conn.close()

        blacklist = _get_blacklist()
        visible = [t for t in tables if t.lower() not in blacklist]
        hidden = len(tables) - len(visible)

        if not visible:
            return "当前数据库中没有可访问的表。"

        lines = ["## 数据库表列表", ""]
        for i, t in enumerate(visible, 1):
            lines.append(f"{i}. `{t}`")
        if hidden > 0:
            lines.append(f"\n> 🔒 {hidden} 个表因安全策略被隐藏。")
        return "\n".join(lines)

    except Exception as e:
        return f"[数据库错误] 无法列出表: {str(e)}"


@mcp.tool()
def describe_table(table_name: str) -> str:
    """查看指定表的结构（列名、类型、是否可空、默认值、注释）。

    使用场景：
      - 执行查询前，先了解表有哪些字段
      - 不确定字段含义时查看注释

    参数：
        table_name: 表名，如 "users"

    返回：
        表结构信息（Markdown 表格）
    """
    try:
        error = _check_table_allowed(table_name)
        if error:
            return error

        conn = _get_connection()
        with conn.cursor() as cursor:
            cursor.execute(f"DESCRIBE `{table_name}`")
            rows = cursor.fetchall()
        conn.close()

        if not rows:
            return f"表 `{table_name}` 不存在或没有列信息。"

        columns = ["字段名", "类型", "允许 NULL", "默认值", "注释"]
        lines = [f"## 表结构: `{table_name}`", ""]
        lines.append("| " + " | ".join(columns) + " |")
        lines.append("| " + " | ".join(["---"] * len(columns)) + " |")

        for r in rows:
            lines.append(
                f"| {r.get('Field', '')} "
                f"| {r.get('Type', '')} "
                f"| {r.get('Null', '')} "
                f"| {r.get('Default', 'NULL')} "
                f"| {r.get('Comment', '') or ''} |"
            )

        return "\n".join(lines)

    except Exception as e:
        return f"[数据库错误] 无法查看表结构: {str(e)}"


@mcp.tool()
def execute_query(sql: str) -> str:
    """执行只读 SQL 查询（仅允许 SELECT / SHOW / DESCRIBE / EXPLAIN）。

    使用场景：
      - 需要从数据库读取数据时
      - 统计、筛选、关联查询

    安全限制：
      - 禁止 INSERT / UPDATE / DELETE / DROP 等写操作
      - 结果最多返回 100 行

    参数：
        sql: 完整的 SELECT 查询语句

    返回：
        查询结果（Markdown 表格）
    """
    if not _is_read_only(sql):
        return (
            f"[安全拒绝] 仅允许只读查询（SELECT / SHOW / DESCRIBE / EXPLAIN），"
            f"当前语句被拒绝: `{sql[:80]}{'...' if len(sql) > 80 else ''}`"
        )

    # 检查是否引用了黑名单表（简单子串匹配）
    blacklist = _get_blacklist()
    sql_lower = sql.lower()
    for table in blacklist:
        if table in sql_lower:
            return (
                f"[安全拒绝] SQL 中引用了黑名单表 `{table}`，不允许访问。\n"
                f"被拒语句: `{sql[:100]}{'...' if len(sql) > 100 else ''}`"
            )

    try:
        conn = _get_connection()
        with conn.cursor() as cursor:
            cursor.execute(sql)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
        conn.close()

        return _format_query_result(columns, rows, sql)

    except Exception as e:
        return f"[数据库错误] 查询执行失败: {str(e)}\n\nSQL: `{sql}`"


@mcp.tool()
def get_row_count(table_name: str) -> str:
    """获取指定表的行数。

    使用场景：
      - 了解表的数据量
      - 判断是否需要缩小查询范围

    参数：
        table_name: 表名，如 "orders"

    返回：
        表的行数
    """
    try:
        error = _check_table_allowed(table_name)
        if error:
            return error

        conn = _get_connection()
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS cnt FROM `{table_name}`")
            result = cursor.fetchone()
        conn.close()

        count = result.get("cnt", 0) if result else 0
        return f"表 `{table_name}` 共有 **{count}** 行数据。"

    except Exception as e:
        return f"[数据库错误] 无法获取行数: {str(e)}"


# === 健康检查 ===

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """健康检查端点，返回服务状态。"""
    return JSONResponse({"status": "ok", "service": "DBTool"})


# 启动入口
if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8004, path="/mcp")
