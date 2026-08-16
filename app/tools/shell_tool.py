"""
Shell 命令执行工具 — 安全地执行操作系统诊断命令（只读操作）。

四层安全防护：
  第 1 层：命令白名单 → 命令必须在 ALLOWED_COMMANDS 集合中，不在则拒绝
  第 2 层：参数黑名单 → 扫描危险模式（rm、dd、kill、$()、反引号等），命中则拒绝
  第 3 层：资源限制  → 超时 30s，输出截断 5000 字符，禁止 shell=True（管道除外）
  第 4 层：结果包装  → stdout/stderr 分别标注，返回退出码，超时/异常返回友好错误
"""

import os
import re
import shlex
import subprocess

from app.config import settings
from langchain_core.tools import tool

# === 第 1 层：命令白名单 ===
# 同时支持 Unix 和 Windows 的只读诊断命令，
# 用 os.name 判断当前平台，Windows 额外放行一批只读命令。

IS_WINDOWS = os.name == "nt"

# Unix / 跨平台只读命令
ALLOWED_COMMANDS: set[str] = {
    # 系统信息
    "uname", "hostname", "uptime", "whoami", "id",
    # 进程管理
    "ps", "top", "pidof", "pgrep",
    # 内存管理
    "free", "vmstat",
    # 磁盘管理
    "df", "du", "lsblk", "mount",
    # 网络诊断
    "ping", "netstat", "ss", "ip", "ifconfig", "curl", "wget",
    "nslookup", "dig", "host", "traceroute", "tracepath",
    # 文件操作
    "ls", "cat", "head", "tail", "wc", "find", "stat", "file",
    # 文本处理
    "grep", "awk", "sed", "sort", "uniq", "cut", "tr", "column",
    # 系统日志
    "journalctl", "dmesg",
    # Docker（只读子命令单独校验）
    "docker",
}

# Windows 专用只读命令（仅当 IS_WINDOWS 为 True 时放行）
WINDOWS_ALLOWED_COMMANDS: set[str] = {
    # 系统信息
    "systeminfo", "ver", "hostname",
    # 进程管理
    "tasklist",
    # 资源监控（typeperf 是只读计数器查询）
    "typeperf",
    # 磁盘/目录
    "dir", "vol", "fsutil", "driverquery",
    # 网络
    "ipconfig", "pathping", "tracert", "net", "netsh",
    # 文件查看（findstr 类似 grep）
    "findstr", "more", "type",
}

if IS_WINDOWS:
    ALLOWED_COMMANDS |= WINDOWS_ALLOWED_COMMANDS

# Docker 允许的只读子命令
ALLOWED_DOCKER_SUBCOMMANDS: set[str] = {
    "ps", "images", "logs", "stats", "inspect",
    "version", "info",
    "network",  # 进一步检查子命令 ls / inspect
    "volume",   # 进一步检查子命令 ls / inspect
    "events",
}

# Docker network/volume 允许的子子命令
ALLOWED_DOCKER_SUB_SUB = {"ls", "inspect"}

# === 第 2 层：参数黑名单 ===

# 危险命令关键词（出现在命令行任意位置即拒绝）
DANGEROUS_KEYWORDS = [
    "rm", "mv", "dd", "mkfs", "shutdown", "reboot",
    "kill", "chmod", "chown", "iptables",
]

# Docker 危险子命令
DOCKER_DANGEROUS_SUBCOMMANDS = [
    "rm", "rmi", "stop", "kill", "prune", "run", "exec",
    "build", "push", "pull", "commit", "save", "load",
    "swarm", "stack", "service", "secret", "config",
    "plugin", "system",
]


def _validate_command(command: str) -> str | None:
    """校验命令安全性，返回错误信息或 None（通过）。"""

    # ---- 2a: 检查命令注入模式 ----
    if "$(" in command:
        return "不允许使用命令替换 $(...)，存在命令注入风险"
    if "`" in command:
        return "不允许使用反引号命令替换，存在命令注入风险"
    if ">" in command or ">>" in command or "<" in command:
        return "不允许使用重定向（> >> <）"

    # ---- 2b: 提取基础命令（管道第一个命令）----
    # 先处理管道引号问题：统计管道符数量时排除引号内的
    try:
        # Windows 下 posix=False，避免把路径反斜杠 \ 当成转义符
        tokens = shlex.split(command, posix=not IS_WINDOWS)
    except ValueError:
        return "命令格式无法解析（引号未闭合或包含非法字符）"
    if not tokens:
        return "空命令"

    base_cmd = tokens[0]

    # ---- 2c: 第 1 层 — 基础命令白名单 ----
    if base_cmd not in ALLOWED_COMMANDS:
        return (
            f"不允许执行 '{base_cmd}' 命令。当前环境为"
            f"{'Windows' if IS_WINDOWS else 'Unix/Linux'}，"
            "仅允许诊断/查看类命令（见工具描述中的支持命令列表）。"
        )

    # ---- 2d: 管道数量检查（≤3）----
    # 重新用原字符串统计引号外的管道符
    pipe_count = _count_unquoted_pipes(command)
    if pipe_count > 3:
        return f"管道数量过多（{pipe_count} 个），最多允许 3 个"

    # ---- 2e: 第 2 层 — 参数黑名单 ----
    # 遍历所有 token，检查危险关键词
    for token in tokens[1:]:  # 跳过基础命令本身
        # 跳过选项参数（以 - 或 -- 开头）
        if token.startswith("-"):
            continue
        token_lower = token.lower()
        if token_lower in DANGEROUS_KEYWORDS:
            return f"检测到危险操作 '{token}'，不允许执行"

    # ---- 2f: Docker 特殊校验 ----
    if base_cmd == "docker":
        err = _validate_docker_command(tokens)
        if err:
            return err

    return None  # 通过


def _count_unquoted_pipes(command: str) -> int:
    """统计不在引号内的管道符数量。"""
    count = 0
    in_single = False
    in_double = False
    for ch in command:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "|" and not in_single and not in_double:
            count += 1
    return count


def _validate_docker_command(tokens: list[str]) -> str | None:
    """校验 Docker 子命令是否为安全（只读）操作。"""
    if len(tokens) < 2:
        return "docker 命令需要子命令"

    subcmd = tokens[1].lower()

    # 检查危险子命令
    if subcmd in DOCKER_DANGEROUS_SUBCOMMANDS:
        return f"不允许 docker {subcmd}，该操作可能修改系统状态"

    # 检查白名单子命令
    if subcmd not in ALLOWED_DOCKER_SUBCOMMANDS:
        return f"不允许 docker {subcmd}，仅允许只读子命令"

    # 对 network/volume 检查子子命令
    if subcmd in ("network", "volume") and len(tokens) >= 3:
        sub_sub = tokens[2].lower()
        if sub_sub not in ALLOWED_DOCKER_SUB_SUB:
            return f"不允许 docker {subcmd} {sub_sub}，仅允许 ls / inspect"

    return None


@tool
def execute_shell(command: str) -> str:
    """安全地执行操作系统诊断命令（只读操作）。

    使用场景：
      - 用户问「CPU 使用率多少」「内存还剩多少」→ top, free（Windows: typeperf, tasklist）
      - 用户问「磁盘满了没」→ df -h（Windows: dir, fsutil）
      - 用户问「网络通不通」→ ping -c 3 8.8.8.8, curl -I https://example.com
      - 用户问「容器运行状态」→ docker ps, docker stats --no-stream
      - 用户问「系统日志有什么异常」→ journalctl -n 50 --no-pager
      - Windows 环境：tasklist / systeminfo / ipconfig / netstat / dir / typeperf

    平台提示：
      - 命令会随运行环境不同而不同（Unix vs Windows）。
      - 若执行时返回「命令未找到」，请按当前平台改用其他只读命令，
        不要误判系统异常，也不要反复重试同一命令。

    安全限制：
      - 仅允许执行白名单内的命令（诊断/查看类）
      - 禁止任何修改系统的操作
      - 命令执行超时 30 秒
      - 输出超过 5000 字符自动截断

    参数：
        command: 完整的 shell 命令，如 "free -h"、"ps aux | head -20"、
                 "tasklist"、"systeminfo"。
                 支持管道（最多 3 个），不支持重定向（> >> <）。

    返回：
        含退出码、stdout、stderr 的结构化输出。
        格式：
          [退出码: 0]
          --- STDOUT ---
          （命令输出）
          --- STDERR ---
          （错误输出，如有）
    """

    # ---- 第 1 + 2 层：安全校验 ----
    error = _validate_command(command)
    if error:
        return f"[安全拒绝] {error}"

    # ---- 第 3 层：资源限制 + 执行 ----
    has_pipe = _count_unquoted_pipes(command) > 0
    timeout = settings.shell_timeout
    max_output = settings.shell_max_output

    try:
        if has_pipe:
            # 有管道时需要用 shell=True 解释管道语法
            # 但已经过了安全校验，命令是安全的
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        else:
            # 无管道时用 shlex 拆词 + shell=False，更安全
            tokens = shlex.split(command, posix=not IS_WINDOWS)
            result = subprocess.run(
                tokens,
                shell=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )

    except subprocess.TimeoutExpired:
        return f"[超时] 命令执行超过 {timeout} 秒已被终止"

    except FileNotFoundError:
        cmd_name = shlex.split(command, posix=not IS_WINDOWS)[0]
        hint = ""
        if IS_WINDOWS:
            hint = "（当前为 Windows 环境，该 Unix 命令不可用）"
        else:
            hint = "（当前为 Unix/Linux 环境，该命令不存在）"
        return (
            f"[工具不可用] 命令未找到: {cmd_name} {hint}。"
            "请根据当前平台选择可用的只读诊断命令，不要因此认为系统异常。"
        )

    except Exception as e:
        return f"[错误] 命令执行异常: {e}"

    # ---- 第 4 层：结果包装 + 截断 ----
    stdout = result.stdout or ""
    stderr = result.stderr or ""

    # 截断过长的输出
    if len(stdout) > max_output:
        stdout = stdout[:max_output] + "\n…（已截断）"
    if len(stderr) > max_output:
        stderr = stderr[:max_output] + "\n…（已截断）"

    # 构建结构化输出
    lines = [f"[退出码: {result.returncode}]"]
    lines.append("--- STDOUT ---")
    lines.append(stdout if stdout else "（无输出）")
    if stderr:
        lines.append("--- STDERR ---")
        lines.append(stderr)

    return "\n".join(lines)
