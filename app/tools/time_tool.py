"""
时间工具 — 获取当前时间，支持时区参数。

教学要点：
  @tool 装饰器把 docstring 变成 LLM 的「工具使用说明书」。
  LLM 读到 docstring 后就知道：什么场景该调、需要传什么参数。
"""

from datetime import datetime, timezone, timedelta
from langchain_core.tools import tool


# 常用时区映射表 — 让 LLM 知道支持哪些时区
TIMEZONE_MAP = {
    "Asia/Shanghai": "北京时间 (UTC+8)",
    "Asia/Tokyo": "东京时间 (UTC+9)",
    "Asia/Singapore": "新加坡时间 (UTC+8)",
    "America/New_York": "美东时间 (UTC-5/UTC-4)",
    "America/Los_Angeles": "美西时间 (UTC-8/UTC-7)",
    "Europe/London": "伦敦时间 (UTC+0/UTC+1)",
    "UTC": "协调世界时",
}


@tool
def get_current_time(timezone_name: str = "Asia/Shanghai") -> str:
    """获取指定时区的当前日期和时间。

    使用场景：
      - 用户问「现在几点」
      - 需要知道当前时间来做判断（如判断高峰期）
      - 需要对比不同时区的时间

    参数：
        timezone_name: 时区名称，如 Asia/Shanghai、America/New_York、UTC。
                      不传则默认使用 Asia/Shanghai（北京时间）。

    返回：
        格式化的时间字符串，如 "2026-05-22 15:30:00 (北京时间)"
    """
    try:
        tz = timezone(timedelta(hours=8))  # 默认北京时间
        if timezone_name in TIMEZONE_MAP:
            # 对于非 UTC 的命名时区，用简单的 UTC 偏移近似
            # 实际生产环境应该用 zoneinfo 库做完整时区处理
            offset_map = {
                "Asia/Shanghai": 8,
                "Asia/Tokyo": 9,
                "Asia/Singapore": 8,
                "America/New_York": -5,
                "America/Los_Angeles": -8,
                "Europe/London": 0,
                "UTC": 0,
            }
            offset = offset_map.get(timezone_name, 8)
            tz = timezone(timedelta(hours=offset))
    except Exception:
        tz = timezone(timedelta(hours=8))

    now = datetime.now(tz)
    label = TIMEZONE_MAP.get(timezone_name, timezone_name)
    return now.strftime(f"%Y-%m-%d %H:%M:%S ({label})")
