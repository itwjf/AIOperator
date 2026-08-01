"""
计算器工具 — 安全地执行数学表达式。

教学要点：
  这个工具展示了如何把有风险的操作（eval）通过严格的命名空间白名单变得安全。
  LLM 自己不擅长精确计算（容易出幻觉），但 Python 不会算错。
  让 LLM 把计算任务「外包」给 Python，而不是自己硬算。
"""

import re
import math
import datetime as _datetime_module
from datetime import datetime, timedelta
from langchain_core.tools import tool

# === 安全的命名空间 ===
# eval 只允许访问这些名字，任何不在白名单里的都报错。
# 这就防止了 __import__、open、exec 等危险操作。

_SAFE_NAMESPACE = {
    # 数学常量
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
    # 数学函数
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "pow": pow,
    "int": int,
    "float": float,
    "str": str,
    "len": len,
    "range": range,
    # math 模块常用函数
    "sqrt": math.sqrt,
    "log": math.log,
    "log10": math.log10,
    "log2": math.log2,
    "ceil": math.ceil,
    "floor": math.floor,
    "sin": math.sin,
    "cos": math.cos,
    # 时间相关 — 方便做时间戳转换
    # 注意：这里暴露 datetime 模块（而非 datetime 类），
    # 才能支持 datetime.datetime.now()、datetime.datetime(2024,1,1) 等写法。
    "datetime": _datetime_module,
    "timedelta": timedelta,
}


@tool
def calculate(expression: str) -> str:
    """安全地执行数学计算表达式。

    使用场景：
      - 用户问「xx 字节是多少 GB」等需要换算的问题
      - 时间戳转换（如「1718123456 是几号」）
      - 任何需要精确数值计算的场景

    支持的运算：
      四则运算: + - * / // % **
      数学函数: abs, round, min, max, sqrt, log, log10, log2, ceil, floor
      常量: pi (3.14159...), e (2.71828...)
      时间转换: datetime.fromtimestamp(1718123456)
      单位换算: 8589934592 / 1024**3  → 得出 GB 数

    参数：
        expression: 合法的 Python 数学表达式，如 "1024 * 8"、"sqrt(144)"。
                   注意：字母部分需要使用英文，中文仅用于描述说明。

    返回：
        计算结果字符串，如 "8192"、"12.0"。

    示例：
        calculate("1024 * 8")              → "8192"
        calculate("8589934592 / 1024**3")  → "8.0"
        calculate("sqrt(144)")             → "12.0"
    """
    # 安全检查：先去掉字符串字面量再检查关键字，避免误伤
    # "open" + " door" → "" + ""  （open 在引号里，不是函数调用，安全）
    dangerous = ["import", "exec", "eval", "open", "compile",
                 "globals", "locals", "getattr", "setattr", "delattr"]
    no_quotes = expression
    no_quotes = re.sub(r'"[^"]*"', '""', no_quotes)   # 去掉双引号字符串
    no_quotes = re.sub(r"'[^']*'", "''", no_quotes)   # 去掉单引号字符串
    for keyword in dangerous:
        if re.search(r'\b' + keyword + r'\b', no_quotes):
            return f"错误：表达式包含不允许的关键字 '{keyword}'"
    # __ 双下划线单独检查（如 __import__、__class__ 等魔法方法）
    if "__" in no_quotes:
        return "错误：表达式包含不允许的关键字 '__'"

    try:
        result = eval(expression, {"__builtins__": {}}, _SAFE_NAMESPACE)
        # 处理 datetime 对象，转成可读字符串
        if isinstance(result, datetime):
            return result.strftime("%Y-%m-%d %H:%M:%S")
        return str(result)
    except SyntaxError as e:
        return f"表达式语法错误: {e}"
    except ZeroDivisionError:
        return "错误: 除数不能为零"
    except (NameError, TypeError, ValueError, OverflowError, AttributeError) as e:
        return f"计算错误: {e}"
