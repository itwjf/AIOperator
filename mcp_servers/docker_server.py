"""
MCP Docker 管理服务 — 提供容器和镜像的查看与管理功能。

通过 MCP 协议暴露 Docker 管理工具，支持：
  - 6 个只读工具：容器列表、资源统计、日志查看、详细信息、镜像列表、进程列表
  - 1 个危险工具：重启容器（需提供原因）

启动方式：
  python mcp_servers/docker_server.py

访问：
  http://127.0.0.1:8006/mcp    — MCP 端点
  http://127.0.0.1:8006/health — 健康检查
"""

import sys
import json
from dotenv import load_dotenv
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_servers.shared import TokenCheckMiddleware

load_dotenv()


# 简单的日志输出（MCP Server 独立进程，不依赖 app.core.logger）
def _log(level: str, msg: str):
    print(f"[DockerTool|{level}] {msg}", file=sys.stderr, flush=True)

# 创建 MCP Server 实例
mcp = FastMCP("DockerTool")
mcp.add_middleware(TokenCheckMiddleware)

# 尝试导入 Docker SDK
try:
    import docker
    _docker_client = docker.from_env()
    _docker_available = True
    _log("INFO", "Docker SDK 连接成功")
except Exception as e:
    _docker_client = None
    _docker_available = False
    _log("WARNING", f"Docker SDK 不可用 — {e}")


def _get_docker():
    """获取 Docker 客户端，不可用时返回 None。"""
    if _docker_available:
        return _docker_client
    return None


def _format_error(msg: str) -> str:
    """统一错误格式。"""
    return f"[Docker 错误] {msg}"


# === 工具 1: list_containers ===

@mcp.tool()
def list_containers(all_containers: bool = False) -> str:
    """列出所有 Docker 容器及其状态。

    使用场景：
      - 用户问「有哪些容器在运行」「容器状态怎么样」
      - 需要查看容器列表和基本状态信息

    参数：
        all_containers: 是否包含已停止的容器，默认 False（仅运行中的）

    返回：
        格式化的容器列表，含 ID、名称、镜像、状态、端口映射。
    """
    client = _get_docker()
    if client is None:
        return _format_error("Docker 服务不可用，请检查 Docker 是否正在运行")

    try:
        containers = client.containers.list(all=all_containers)
        if not containers:
            return "没有容器" + ("（包括已停止的）" if all_containers else "（正在运行的）")

        lines = [f"共 {len(containers)} 个容器："]
        for c in containers:
            name = c.name
            cid = c.short_id
            image = c.image.tags[0] if c.image.tags else c.image.short_id
            status = c.status
            ports = ", ".join(
                f"{k.split('/')[0]}→{v[0]['HostPort']}"
                for k, v in (c.ports or {}).items()
                if v
            ) or "无端口映射"
            lines.append(f"  [{cid}] {name} | {image} | {status} | {ports}")
        return "\n".join(lines)
    except Exception as e:
        _log("ERROR", f"list_containers 失败 — {e}")
        return _format_error(f"获取容器列表失败: {e}")


# === 工具 2: container_stats ===

@mcp.tool()
def container_stats(container_name: str) -> str:
    """获取指定容器的资源使用统计（CPU/内存/网络/IO）。

    使用场景：
      - 用户问「xxx 容器 CPU 占用多少」「容器内存使用情况」
      - 排查容器性能问题

    参数：
        container_name: 容器名称或 ID

    返回：
        格式化的资源统计信息，输出上限 3000 字符。
    """
    client = _get_docker()
    if client is None:
        return _format_error("Docker 服务不可用")

    try:
        container = client.containers.get(container_name)
        stats = container.stats(stream=False)

        # 解析 CPU 使用率
        cpu_delta = stats["cpu_stats"]["cpu_usage"]["total_usage"] - \
                    stats["precpu_stats"]["cpu_usage"]["total_usage"]
        system_delta = stats["cpu_stats"].get("system_cpu_usage", 0) - \
                       stats["precpu_stats"].get("system_cpu_usage", 0)
        num_cpus = stats["cpu_stats"]["online_cpus"]
        cpu_percent = round((cpu_delta / system_delta) * num_cpus * 100, 2) if system_delta > 0 else 0.0

        # 解析内存使用
        mem_usage = stats["memory_stats"]["usage"]
        mem_limit = stats["memory_stats"]["limit"]
        mem_percent = round((mem_usage / mem_limit) * 100, 2) if mem_limit > 0 else 0.0

        # 解析网络 IO
        net_io = stats.get("networks", {})
        net_rx = sum(v.get("rx_bytes", 0) for v in net_io.values())
        net_tx = sum(v.get("tx_bytes", 0) for v in net_io.values())

        result = (
            f"容器 {container_name} 资源统计：\n"
            f"  CPU: {cpu_percent}% ({num_cpus} 核)\n"
            f"  内存: {_format_bytes(mem_usage)} / {_format_bytes(mem_limit)} ({mem_percent}%)\n"
            f"  网络接收: {_format_bytes(net_rx)}\n"
            f"  网络发送: {_format_bytes(net_tx)}"
        )

        # 截断至 3000 字符
        if len(result) > 3000:
            result = result[:3000] + "\n…（已截断）"
        return result
    except docker.errors.NotFound:
        return _format_error(f"容器 '{container_name}' 不存在")
    except Exception as e:
        _log("ERROR", f"container_stats 失败 — {e}")
        return _format_error(f"获取容器统计失败: {e}")


# === 工具 3: container_logs ===

@mcp.tool()
def container_logs(container_name: str, tail: int = 50, since: str = "") -> str:
    """获取指定容器的最近日志。

    使用场景：
      - 用户问「xxx 容器最近有什么日志」「看看 nginx 的错误日志」
      - 排查容器运行问题

    参数：
        container_name: 容器名称或 ID
        tail: 返回最近 N 行日志，默认 50，最多 200
        since: 起始时间（如 "10m" 表示 10 分钟前，"1h" 表示 1 小时前），留空则不限

    返回：
        容器的最近日志文本，最多 200 行。
    """
    client = _get_docker()
    if client is None:
        return _format_error("Docker 服务不可用")

    tail = min(max(tail, 1), 200)  # 限制 1-200

    try:
        container = client.containers.get(container_name)
        kwargs = {"tail": tail}
        if since:
            kwargs["since"] = since
        logs = container.logs(**kwargs).decode("utf-8", errors="replace")

        if not logs.strip():
            return f"容器 {container_name} 最近 {tail} 行没有日志输出"

        return f"容器 {container_name} 最近 {tail} 行日志：\n{logs}"
    except docker.errors.NotFound:
        return _format_error(f"容器 '{container_name}' 不存在")
    except Exception as e:
        _log("ERROR", f"container_logs 失败 — {e}")
        return _format_error(f"获取容器日志失败: {e}")


# === 工具 4: inspect_container ===

@mcp.tool()
def inspect_container(container_name: str) -> str:
    """查看容器的详细信息（镜像、端口、挂载、环境变量等）。

    使用场景：
      - 用户问「xxx 容器用的什么镜像」「容器挂载了哪些目录」
      - 排查容器配置问题

    参数：
        container_name: 容器名称或 ID

    返回：
        容器详细信息的格式化文本。
    """
    client = _get_docker()
    if client is None:
        return _format_error("Docker 服务不可用")

    try:
        container = client.containers.get(container_name)
        attrs = container.attrs

        # 基本信息
        info = attrs["Config"]
        state = attrs["State"]
        network = attrs.get("NetworkSettings", {})

        result = (
            f"容器 {container_name} 详细信息：\n"
            f"  ID: {container.short_id}\n"
            f"  镜像: {attrs['Config']['Image']}\n"
            f"  状态: {attrs['State']['Status']}\n"
            f"  创建时间: {attrs['Created'][:19]}\n"
        )

        # 端口映射
        ports = network.get("Ports", {}) or {}
        if ports:
            result += "  端口映射:\n"
            for container_port, host_bindings in ports.items():
                if host_bindings:
                    for binding in host_bindings:
                        result += f"    {container_port} → {binding['HostIp']}:{binding['HostPort']}\n"
                else:
                    result += f"    {container_port} (未映射)\n"

        # 挂载
        mounts = attrs.get("Mounts", [])
        if mounts:
            result += "  挂载卷:\n"
            for m in mounts:
                result += f"    {m['Source']} → {m['Destination']} ({m.get('Mode', 'rw')})\n"

        # 环境变量
        env_vars = info.get("Env", [])
        if env_vars:
            result += "  环境变量:\n"
            for ev in env_vars:
                # 过滤敏感信息（含 key/secret/password/token 的变量显示为 ***）
                key, _, val = ev.partition("=")
                if any(s in key.lower() for s in ("key", "secret", "password", "token", "passwd")):
                    val = "***"
                result += f"    {key}={val}\n"

        return result
    except docker.errors.NotFound:
        return _format_error(f"容器 '{container_name}' 不存在")
    except Exception as e:
        _log("ERROR", f"inspect_container 失败 — {e}")
        return _format_error(f"获取容器详情失败: {e}")


# === 工具 5: list_images ===

@mcp.tool()
def list_images() -> str:
    """列出本地所有的 Docker 镜像。

    使用场景：
      - 用户问「有哪些镜像」「镜像占用多少空间」

    返回：
        格式化的镜像列表，含仓库名、标签、ID、大小。
    """
    client = _get_docker()
    if client is None:
        return _format_error("Docker 服务不可用")

    try:
        images = client.images.list()
        if not images:
            return "本地没有 Docker 镜像"

        lines = [f"共 {len(images)} 个镜像："]
        for img in images:
            tags = ", ".join(img.tags) if img.tags else "<none>"
            size = _format_bytes(img.attrs.get("Size", 0))
            lines.append(f"  [{img.short_id}] {tags} | {size}")
        return "\n".join(lines)
    except Exception as e:
        _log("ERROR", f"list_images 失败 — {e}")
        return _format_error(f"获取镜像列表失败: {e}")


# === 工具 6: container_processes ===

@mcp.tool()
def container_processes(container_name: str) -> str:
    """列出指定容器内的进程。

    使用场景：
      - 用户问「xxx 容器里在跑什么进程」
      - 排查容器内进程异常

    参数：
        container_name: 容器名称或 ID

    返回：
        容器内进程列表（PID、用户、命令）。
    """
    client = _get_docker()
    if client is None:
        return _format_error("Docker 服务不可用")

    try:
        container = client.containers.get(container_name)
        top = container.top()
        if not top.get("Processes"):
            return f"容器 {container_name} 内没有运行中的进程"

        titles = top.get("Titles", [])
        lines = [f"容器 {container_name} 进程列表："]
        lines.append("  " + " | ".join(titles))
        for proc in top["Processes"]:
            lines.append("  " + " | ".join(proc))
        return "\n".join(lines)
    except docker.errors.NotFound:
        return _format_error(f"容器 '{container_name}' 不存在")
    except Exception as e:
        _log("ERROR", f"container_processes 失败 — {e}")
        return _format_error(f"获取容器进程失败: {e}")


# === 工具 7: restart_container ⚠️ 危险操作 ===

@mcp.tool()
def restart_container(container_name: str, reason: str = "") -> str:
    """⚠️ 危险操作：重启指定容器。

    使用场景：
      - 容器无响应、异常时需要重启恢复
      - 仅在确认重启是必要操作时才调用

    参数：
        container_name: 要重启的容器名称或 ID
        reason: 重启原因（必填，用于记录操作理由）

    返回：
        重启操作的结果。

    安全提示：
        此操作会中断容器服务，请确认后再执行。
    """
    client = _get_docker()
    if client is None:
        return _format_error("Docker 服务不可用")

    if not reason:
        return _format_error("重启容器需要提供 reason 参数说明原因")

    try:
        container = client.containers.get(container_name)
        container.restart()
        reason_text = f"，原因: {reason}"
        _log("WARNING", f"容器已重启 — {container_name} ({reason})")
        return f"容器 {container_name} 已成功重启{reason_text}"
    except docker.errors.NotFound:
        return _format_error(f"容器 '{container_name}' 不存在")
    except Exception as e:
        _log("ERROR", f"restart_container 失败 — {e}")
        return _format_error(f"重启容器失败: {e}")


# === 辅助函数 ===

def _format_bytes(size: int) -> str:
    """将字节数格式化为可读单位。"""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


# === 健康检查 ===

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """健康检查端点，返回服务状态。"""
    return JSONResponse({"status": "ok", "service": "DockerTool"})


# 启动入口
if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8006, path="/mcp")
