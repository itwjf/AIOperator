# SPEC: 工具系统扩展开发规范

> **版本**: v1.0  
> **创建日期**: 2026-06-23  
> **状态**: 待开发  
> **依赖**: 本项目的第九阶段已完成（消息修剪、异常处理、日志系统、计算器工具）

---

## 目录

- [1. 概述与目标](#1-概述与目标)
- [2. 工具一：Shell 命令执行工具（本地工具）](#2-工具一shell-命令执行工具本地工具)
- [3. 工具二：Docker 管理 MCP Server](#3-工具二docker-管理-mcp-server)
- [4. 工具三：Web 搜索 MCP Server](#4-工具三web-搜索-mcp-server)
- [5. 工具注册与集成规范](#5-工具注册与集成规范)
- [6. 开发顺序与依赖关系](#6-开发顺序与依赖关系)
- [7. 验收标准](#7-验收标准)

---

## 1. 概述与目标

### 1.1 背景

当前 AIOperator 已具备以下工具能力：

| 工具 | 类型 | 来源 |
|------|------|------|
| `retrieve_knowledge` | 知识库检索 | 本地 `@tool` |
| `get_current_time` | 时间查询 | MCP Server (8003) |
| `calculate` | 安全计算器 | 本地 `@tool` |
| `list_tables` / `describe_table` / `execute_query` / `get_row_count` | 数据库查询 | MCP Server (8004) |
| `create_presentation` / `add_content_slide` / `add_table_slide` / `export_pptx` | PPT 生成 | MCP Server (8005) |

**缺口**：Agent 缺少与操作系统交互的能力（执行诊断命令、管理容器）和获取外部信息的能力（互联网搜索）。

### 1.2 本次开发目标

新增 **3 个工具**，让 Agent 具备真正的运维操作能力：

1. **Shell 命令执行工具**（本地 `@tool`）——安全地执行操作系统诊断命令
2. **Docker 管理 MCP Server**（FastMCP 独立进程）——容器生命周期管理
3. **Web 搜索 MCP Server**（FastMCP 独立进程）——互联网信息检索

### 1.3 设计原则

- **安全第一**：所有涉及系统操作的工具必须有白名单/黑名单/超时/输出截断
- **自愈降级**：MCP Server 不可用时不影响主程序运行（延续现有设计）
- **统一技术栈**：MCP Server 均基于 FastMCP + streamable-http transport
- **工具描述即文档**：docstring 必须精确（LLM 靠它判断何时调用）

---

## 2. 工具一：Shell 命令执行工具（本地工具）

### 2.1 基本信息

| 属性 | 值 |
|------|-----|
| **文件名** | `app/tools/shell_tool.py` |
| **工具名** | `execute_shell` |
| **工具类型** | 本地 `@tool`（同步函数） |
| **预估代码量** | ~150 行 |
| **新增依赖** | 无（仅使用 Python 标准库 `subprocess`） |

### 2.2 功能描述

让 Agent 能够安全地执行操作系统诊断命令。Agent 调用此工具时，传入一个白名单内的命令，工具在受限环境中执行，返回截断后的输出。

### 2.3 安全模型（核心设计）

采用 **四层防护** 模型：

```
用户问题 → Agent 决定调用 execute_shell("top -bn1")
              │
              ▼
┌─────────────────────────────────────────────┐
│ 第 1 层：命令白名单检查                      │
│   - 命令必须在 ALLOWED_COMMANDS 集合中       │
│   - 不在白名单 → 拒绝并返回可用的命令列表     │
├─────────────────────────────────────────────┤
│ 第 2 层：参数黑名单检查                      │
│   - 扫描参数中的危险模式（管道链>3、重定向等）│
│   - 命中黑名单 → 拒绝并说明原因              │
├─────────────────────────────────────────────┤
│ 第 3 层：资源限制                            │
│   - 超时: 30 秒（subprocess timeout）        │
│   - 输出截断: 5000 字符                      │
│   - 禁止 shell=True（防止 shell 注入）        │
├─────────────────────────────────────────────┤
│ 第 4 层：结果安全包装                         │
│   - stdout 和 stderr 分别标注               │
│   - 返回退出码                               │
│   - 超时/异常返回友好错误信息                 │
└─────────────────────────────────────────────┘
```

#### 2.3.1 命令白名单

```python
ALLOWED_COMMANDS = {
    # 系统信息
    "uname", "hostname", "uptime", "whoami", "id",
    # 进程管理（只读）
    "ps", "top", "pidof", "pgrep",
    # 内存管理（只读）
    "free", "vmstat",
    # 磁盘管理（只读）
    "df", "du", "lsblk", "mount",
    # 网络诊断（只读）
    "ping", "netstat", "ss", "ip", "ifconfig",
    "curl", "wget", "nslookup", "dig", "host",
    "traceroute", "tracepath",
    # 文件操作（只读）
    "ls", "cat", "head", "tail", "wc", "find", "stat",
    "file", "du",
    # 文本处理
    "grep", "awk", "sed", "sort", "uniq", "cut",
    "tr", "column",
    # 系统日志（只读）
    "journalctl", "dmesg",
    # Docker（只读操作）
    "docker",
}
```

#### 2.3.2 参数黑名单模式

```python
DANGEROUS_PATTERNS = [
    # 危险命令（即使白名单命令也不允许的操作）
    r"\brm\b", r"\bmv\b", r"\bdd\b", r"\bmkfs\b",
    r"\bshutdown\b", r"\breboot\b", r"\bkill\b",
    r"\bchmod\b", r"\bchown\b", r"\biptables\b",
    # shell 特殊字符（防止命令注入）
    r"\$\(",   # 命令替换 $()
    r"`[^`]+`", # 反引号命令替换
    # 危险的 docker 子命令
    r"docker\s+(rm|rmi|stop|kill|prune|system\s+prune)",
]
```

#### 2.3.3 "docker" 的特殊处理

`docker` 在白名单中，但只允许**只读**子命令：

```python
ALLOWED_DOCKER_SUBCOMMANDS = [
    "ps", "images", "logs", "stats", "inspect",
    "version", "info", "network ls", "network inspect",
    "volume ls", "volume inspect", "events",
]
```

当命令以 `docker` 开头时，先解析子命令，再检查子命令是否在白名单中。

### 2.4 工具签名

```python
@tool
def execute_shell(command: str) -> str:
    """安全地执行操作系统诊断命令（只读操作）。

    使用场景：
      - 用户问「CPU 使用率多少」「内存还剩多少」→ top, free
      - 用户问「磁盘满了没」→ df -h
      - 用户问「网络通不通」→ ping -c 3 8.8.8.8, curl -I https://example.com
      - 用户问「有哪些进程」「某个进程在不在」→ ps aux | grep nginx
      - 用户问「容器运行状态」→ docker ps, docker stats --no-stream
      - 用户问「系统日志有什么异常」→ journalctl -n 50 --no-pager, dmesg | tail -30

    安全限制：
      - 仅允许执行白名单内的命令（诊断/查看类）
      - 禁止任何修改系统的操作（删除、移动、终止进程等）
      - 命令执行超时 30 秒
      - 输出超过 5000 字符自动截断

    参数：
        command: 完整的 shell 命令，如 "free -h"、"ps aux | head -20"、
                 "docker ps --format '{{.Names}} {{.Status}}'"。
                 支持管道（最多 3 个），不支持重定向（> >> <）。

    返回：
        包含退出码、stdout、stderr 的结构化输出。
        格式：
          [退出码: 0]
          --- STDOUT ---
          （命令输出）
          --- STDERR ---
          （错误输出，如有）
    """
```

### 2.5 实现要点

#### 2.5.1 命令解析

```python
import shlex

def _parse_command(command: str) -> tuple[str, list[str]]:
    """解析命令字符串为 (可执行文件, 参数列表)。"""
    parts = shlex.split(command)
    return parts[0], parts[1:] if len(parts) > 1 else []
```

#### 2.5.2 管道支持

```python
MAX_PIPES = 3  # 最多 3 个管道

def _check_pipes(command: str) -> bool:
    """检查管道数量是否超限。"""
    # 引号内的 | 不算管道
    outside_quotes = re.sub(r'"[^"]*"', '', command)
    outside_quotes = re.sub(r"'[^']*'", '', outside_quotes)
    pipe_count = outside_quotes.count('|')
    return pipe_count <= MAX_PIPES
```

#### 2.5.3 执行逻辑

```python
import subprocess
import asyncio

async def _run_command(command: str, timeout: int = 30) -> dict:
    """异步执行命令（在线程池中运行同步 subprocess）。"""
    loop = asyncio.get_event_loop()
    
    def _sync_run():
        return subprocess.run(
            command,
            shell=True,          # 允许管道（安全检查在前置步骤完成）
            capture_output=True, # 捕获 stdout + stderr
            text=True,           # 文本模式（非 bytes）
            timeout=timeout,     # 30 秒超时
            executable="/bin/bash" if os.name != "nt" else None,
        )
    
    try:
        result = await loop.run_in_executor(None, _sync_run)
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "", "stderr": f"命令超时（>{timeout}秒）"}
```

### 2.6 注册到 Agent

需要在以下文件中添加 `execute_shell` 工具：

**文件 1: `app/services/manual_agent_service.py`**
```python
from app.tools.shell_tool import execute_shell

TOOLS = [retrieve_knowledge, get_current_time, calculate, execute_shell]

# SYSTEM_PROMPT 新增：
# 5. **Shell 命令执行**（execute_shell 工具）：
#    当用户需要查看系统状态、资源使用、进程信息、网络状态、Docker 容器状态时使用。
#    支持常用诊断命令（top, free, df, ps, netstat, docker ps 等）。
#    仅能执行只读诊断命令，无法修改系统。
```

**文件 2: `app/services/rag_agent_service.py`**
```python
from app.tools.shell_tool import execute_shell

# tools 列表新增 execute_shell
# SYSTEM_PROMPT 同步更新
```

---

## 3. 工具二：Docker 管理 MCP Server

### 3.1 基本信息

| 属性 | 值 |
|------|-----|
| **文件名** | `mcp_servers/docker_server.py` |
| **MCP Server 名** | `DockerTool` |
| **端口** | `8006` |
| **MCP 端点路径** | `/mcp` |
| **健康检查** | `/health`（FastMCP 自动提供） |
| **预估代码量** | ~180 行 |
| **新增依赖** | `docker>=7.0.0`（Docker SDK for Python） |

### 3.2 功能描述

通过 Docker SDK 与 Docker Daemon 通信，让 Agent 能够管理容器生命周期。采用**只读优先 + 危险操作确认**的设计。

### 3.3 提供的工具列表

| 工具名 | 类型 | 风险等级 | 描述 |
|--------|------|:--------:|------|
| `list_containers` | 只读 | 🟢 安全 | 列出所有容器及其状态 |
| `container_stats` | 只读 | 🟢 安全 | 获取容器的 CPU/内存/网络/IO 统计 |
| `container_logs` | 只读 | 🟢 安全 | 获取指定容器的日志（最近 N 行） |
| `inspect_container` | 只读 | 🟢 安全 | 查看容器详细信息（镜像、端口、挂载、环境变量） |
| `list_images` | 只读 | 🟢 安全 | 列出本地 Docker 镜像 |
| `restart_container` | 写入 | 🔴 危险 | 重启指定容器 |
| `container_processes` | 只读 | 🟢 安全 | 查看容器内运行的进程 |

### 3.4 安全设计

```
list_containers / container_stats / container_logs / inspect_container / list_images / container_processes
  → 直接执行，无需确认（只读操作）

restart_container
  → 工具返回确认请求（"即将重启容器 xxx，请确认"）
  → Agent 需要再次调用并传 confirmed=True 才真正执行
  → 这是软确认（通过 Agent 判断），而非硬编码确认
```

**为什么不用硬编码确认而用 Agent 判断？**
- 硬编码确认（如 `confirm=True` 参数）在 Agent 循环中表现不好
- Agent 会在 System Prompt 的约束下自己判断是否真的需要重启
- 工具描述中明确标注「危险」和「需要谨慎」就足够引导 Agent

### 3.5 工具详细签名

```python
@mcp.tool()
def list_containers(all_containers: bool = False) -> str:
    """列出 Docker 容器。

    使用场景：
      - 用户问「有哪些容器在运行」→ all_containers=False (默认只显示运行中的)
      - 用户问「所有容器（包括已停止的）」→ all_containers=True

    参数：
        all_containers: 是否显示所有容器（包括已停止的），默认 False

    返回：
        容器列表（Markdown 表格），包含：容器名、镜像、状态、运行时间
    """
```

```python
@mcp.tool()
def container_stats(container_name: str) -> str:
    """获取容器的实时资源使用统计（CPU、内存、网络、IO）。

    使用场景：
      - 用户问「xxx 容器用了多少内存/CPU」
      - 排查容器资源异常

    参数：
        container_name: 容器名或 ID

    返回：
        CPU 使用率、内存使用量/限制、网络流量、块 IO（Markdown 格式）
    """
```

```python
@mcp.tool()
def container_logs(container_name: str, tail: int = 50, since: str = "") -> str:
    """获取容器的日志输出。

    使用场景：
      - 用户问「看看 xxx 容器的日志」
      - 排查容器启动失败或异常原因

    参数：
        container_name: 容器名或 ID
        tail: 返回最后 N 行，默认 50，最大 200
        since: 时间过滤（可选），如 "5m"（5分钟前）、"2026-06-23T10:00:00"

    返回：
        容器日志内容
    """
```

```python
@mcp.tool()
def restart_container(container_name: str, reason: str = "") -> str:
    """重启指定的 Docker 容器。⚠️ 危险操作！

    使用场景：
      - 用户明确要求重启某个容器
      - 诊断发现问题后确认需要重启

    参数：
        container_name: 要重启的容器名或 ID
        reason: 重启原因（必须提供），如 "排查后确认需要重启 nginx"

    返回：
        重启结果
    """
```

```python
@mcp.tool()
def list_images() -> str:
    """列出本地所有 Docker 镜像。

    返回：
        镜像列表（Markdown 表格），包含：仓库、标签、镜像 ID、大小
    """
```

```python
@mcp.tool()
def inspect_container(container_name: str) -> str:
    """查看容器的详细配置信息。

    使用场景：
      - 了解容器的镜像、端口映射、挂载卷、环境变量等

    参数：
        container_name: 容器名或 ID

    返回：
        容器详细信息（Markdown 格式，含镜像、端口、挂载、环境变量）
    """
```

```python
@mcp.tool()
def container_processes(container_name: str) -> str:
    """查看容器内运行的进程列表。

    使用场景：
      - 用户问「xxx 容器里在跑什么进程」

    参数：
        container_name: 容器名或 ID

    返回：
        进程列表，类似 'ps aux' 输出
    """
```

### 3.6 实现要点

#### 3.6.1 Docker 客户端创建

```python
import docker

def _get_client() -> docker.DockerClient:
    """创建 Docker 客户端 — 优先连本地 Docker Daemon。"""
    try:
        return docker.from_env()
    except docker.errors.DockerException:
        # 如果默认环境连接失败，尝试 TCP 连接
        return docker.DockerClient(base_url="tcp://localhost:2375")
```

#### 3.6.2 日志长度限制

```python
MAX_LOG_LINES = 200   # 容器日志最多返回 200 行
MAX_STATS_LENGTH = 3000  # 统计信息最多 3000 字符
```

#### 3.6.3 环境变量加载

```python
# docker_server.py 独立运行时需要加载 .env
from dotenv import load_dotenv
load_dotenv()

# 可选配置项（放入 .env）：
# DOCKER_HOST=unix:///var/run/docker.sock  # Docker 连接地址
# DOCKER_MAX_LOG_LINES=200                  # 日志最大行数
```

### 3.7 启动方式

```bash
# 本地开发
python mcp_servers/docker_server.py
# → MCP endpoint: http://127.0.0.1:8006/mcp
# → Health: http://127.0.0.1:8006/health
```

### 3.8 Docker Compose 集成

在 `docker-compose.yml` 中新增服务：

```yaml
mcp-docker:
  build: .
  container_name: aioperator-mcp-docker
  restart: unless-stopped
  command: python mcp_servers/docker_server.py
  ports:
    - "8006:8006"
  env_file: .env
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock  # 挂载 Docker socket
```

---

## 4. 工具三：Web 搜索 MCP Server

### 4.1 基本信息

| 属性 | 值 |
|------|-----|
| **文件名** | `mcp_servers/search_server.py` |
| **MCP Server 名** | `SearchTool` |
| **端口** | `8007` |
| **MCP 端点路径** | `/mcp` |
| **预估代码量** | ~120 行 |
| **新增依赖** | `tavily-python>=0.5.0` |

### 4.2 技术选型分析

| 方案 | 搜索后端 | 优点 | 缺点 |
|------|---------|------|------|
| **Tavily（推荐）** | Tavily API | 专为 AI Agent 设计，返回已提取摘要的内容；免费额度 1000 次/月 | 需要注册 API Key |
| Brave Search | Brave API | Anthropic 官方 MCP Server，质量高 | 免费额度仅 2000 次/月 |
| Serper | Google 搜索 | 搜索结果质量高 | 无免费额度 |
| DuckDuckGo（备选） | DuckDuckGo | 完全免费，无需 API Key | 结果质量不如付费方案，可能被限流 |

**最终方案：Tavily 优先 + DuckDuckGo 降级**

```python
# 有 TAVILY_API_KEY → 使用 Tavily（高质量）
# 无 TAVILY_API_KEY → 使用 DuckDuckGo（免费备选）
```

此设计延续了本项目的「自愈降级」理念。

### 4.3 提供的工具列表

| 工具名 | 描述 |
|--------|------|
| `web_search` | 搜索互联网信息 |
| `fetch_webpage` | 获取指定 URL 的网页内容（可选） |

### 4.4 工具详细签名

```python
@mcp.tool()
def web_search(query: str, max_results: int = 5, search_depth: str = "basic") -> str:
    """搜索互联网上的最新信息。

    使用场景：
      - 用户问「最新的 xxx 技术是什么」→ 知识库没有的内容
      - 用户问「官方文档里 xxx 怎么配置」→ 搜索最新文档
      - 用户需要当前事件、新闻、最新版本信息
      - 知识库返回空或相关性低时，作为补充信息来源

    参数：
        query:        搜索关键词，如 "Docker 容器内存限制 OOM 排查"
        max_results:  返回结果数量 1-10，默认 5
        search_depth: "basic"（快速搜索）或 "advanced"（深度搜索，更全面但更慢）

    返回：
        搜索结果（Markdown 格式），每条包含：标题、URL、内容摘要、相关性分数
        格式：
          ## 搜索结果: "xxx"
          1. **[标题]** (相关度: 0.95)
             https://example.com/article
             > 内容摘要...
          2. ...
    """
```

```python
@mcp.tool()
def fetch_webpage(url: str, max_length: int = 3000) -> str:
    """获取指定网页的文本内容（用于深度阅读搜索结果中感兴趣的页面）。

    使用场景：
      - 搜索到一篇相关文章，需要了解详细内容
      - Agent 先调用 web_search 找到 URL，再调用本工具深度阅读

    参数：
        url:         网页地址，如 "https://docs.docker.com/config/containers/resource_constraints/"
        max_length:  返回内容最大字符数，默认 3000，最大 10000

    返回：
        网页的文本内容（已去除 HTML 标签和脚本），如果无法获取则返回错误信息
    """
```

### 4.5 实现要点

#### 4.5.1 Tavily 搜索

```python
from tavily import TavilyClient

def _tavily_search(query: str, max_results: int = 5, search_depth: str = "basic") -> str:
    """使用 Tavily API 搜索。"""
    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        return None  # 降级到 DuckDuckGo
    
    client = TavilyClient(api_key=api_key)
    response = client.search(
        query=query,
        max_results=max_results,
        search_depth=search_depth,
    )
    return _format_results(query, response["results"])
```

#### 4.5.2 DuckDuckGo 降级

```python
from duckduckgo_search import DDGS

def _ddg_search(query: str, max_results: int = 5) -> str:
    """使用 DuckDuckGo 搜索（免费备选）。"""
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=max_results))
    return _format_results(query, results)
```

#### 4.5.3 结果格式化

```python
def _format_results(query: str, results: list) -> str:
    """统一格式化搜索结果。"""
    if not results:
        return f"搜索「{query}」没有找到相关结果。"
    
    lines = [f"## 搜索结果: \"{query}\"", ""]
    for i, r in enumerate(results, 1):
        title = r.get("title", "无标题")
        url = r.get("url", "")
        content = r.get("content", r.get("snippet", ""))
        score = r.get("score", r.get("relevance_score", ""))
        
        lines.append(f"{i}. **{title}**")
        if score:
            lines.append(f"   相关度: {score}")
        lines.append(f"   {url}")
        lines.append(f"   > {content[:500]}")
        lines.append("")
    
    return "\n".join(lines)
```

### 4.6 启动方式

```bash
# 本地开发
python mcp_servers/search_server.py
# → MCP endpoint: http://127.0.0.1:8007/mcp
# → Health: http://127.0.0.1:8007/health
```

### 4.7 Docker Compose 集成

```yaml
mcp-search:
  build: .
  container_name: aioperator-mcp-search
  restart: unless-stopped
  command: python mcp_servers/search_server.py
  ports:
    - "8007:8007"
  env_file: .env
```

---

## 5. 工具注册与集成规范

### 5.1 本地工具注册

所有本地 `@tool` 工具需要注册到以下位置：

| 文件 | 要改的位置 | 说明 |
|------|-----------|------|
| `app/services/manual_agent_service.py` | `TOOLS` 列表 + `SYSTEM_PROMPT` | 手动 Agent 图 |
| `app/services/rag_agent_service.py` | `tools` 参数 + `SYSTEM_PROMPT` | RAG Agent (create_agent) |

### 5.2 MCP Server 注册

所有 MCP Server 需要注册到以下位置：

| 文件 | 要改的位置 | 说明 |
|------|-----------|------|
| `app/agent/mcp_client.py` | `_build_mcp_servers()` | MCP Server 连接配置 |
| `app/config.py` | 新增 `mcp_search_url` / `mcp_docker_url` | 配置项 |
| `app/services/mcp_agent_service.py` | `SYSTEM_PROMPT` | Agent 需要知道新工具的存在和用法 |
| `docker-compose.yml` | 新增 `mcp-docker` / `mcp-search` 服务 | Docker 部署 |

### 5.3 .env 配置模板

```bash
# ============================================
# 新增：MCP Server 地址
# ============================================

# Docker 管理 MCP Server
MCP_DOCKER_URL=http://127.0.0.1:8006/mcp

# Web 搜索 MCP Server
MCP_SEARCH_URL=http://127.0.0.1:8007/mcp

# Tavily API Key（可选，不填则用 DuckDuckGo 免费搜索）
TAVILY_API_KEY=

# Docker 连接配置（可选，默认连本地）
DOCKER_HOST=unix:///var/run/docker.sock
```

### 5.4 config.py 新增配置项

```python
# MCP Server 地址 — 新增
mcp_docker_url: str = "http://127.0.0.1:8006/mcp"
mcp_search_url: str = "http://127.0.0.1:8007/mcp"

# Shell 工具配置
shell_timeout: int = 30        # 命令超时秒数
shell_max_output: int = 5000   # 输出截断字符数
```

### 5.5 pyproject.toml 新增依赖

```toml
dependencies = [
    # ... 现有依赖 ...
    "docker>=7.0.0",          # Docker SDK（docker_server.py 使用）
    "tavily-python>=0.5.0",   # Tavily AI 搜索（search_server.py 使用）
    "duckduckgo-search>=6.0", # DuckDuckGo 搜索（search_server.py 降级方案）
]
```

---

## 6. 开发顺序与依赖关系

```
第 1 步: Shell 命令执行工具（无外部依赖，只需 subprocess）
  ├── 新建 app/tools/shell_tool.py
  ├── 注册到 manual_agent_service.py 和 rag_agent_service.py
  └── 本地验证：curl 调用 /api/agent/chat 测试命令执行

第 2 步: Docker 管理 MCP Server（依赖 docker SDK）
  ├── pip install docker
  ├── 新建 mcp_servers/docker_server.py
  ├── 注册到 mcp_client.py + config.py
  ├── 更新 docker-compose.yml
  └── 验证：启动 server → 用 /api/mcp/tools 确认工具可见

第 3 步: Web 搜索 MCP Server（依赖 tavily / duckduckgo-search）
  ├── pip install tavily-python duckduckgo-search
  ├── 新建 mcp_servers/search_server.py
  ├── 注册到 mcp_client.py + config.py
  ├── 更新 docker-compose.yml
  └── 验证：启动 server → 用 /api/mcp/chat 测试搜索
```

### 6.1 依赖关系图

```
Shell Tool ──→ 无依赖，可立即开发
Docker MCP ──→ 无依赖 Shell Tool，可并行开发
Web Search MCP → 无依赖，可并行开发
               三者独立，但都需要在最后统一注册到 Agent
```

## 7. 验收标准

### 7.1 Shell 命令执行工具

- [ ] `calculate("free -h")` 在本地 Python 中返回内存信息
- [ ] 危险命令被拒绝：`execute_shell("rm -rf /")` 返回包含"不允许"的错误信息
- [ ] 命令超时生效：`execute_shell("sleep 60")` 30 秒后返回超时错误
- [ ] 通过 `/api/agent/chat` 提问"看看内存使用情况"，Agent 自动调用 execute_shell
- [ ] 通过 `/api/mcp/chat` 也能正常调用（MCP Agent 从 mcp_agent_service.py 获取工具）
- [ ] 输出超过 5000 字符时自动截断，末尾标注"...（已截断）"

### 7.2 Docker 管理 MCP Server

- [ ] `python mcp_servers/docker_server.py` 启动成功，端口 8006
- [ ] `GET /api/mcp/tools` 返回包含 `list_containers`、`container_stats`、`container_logs`、`restart_container` 等工具
- [ ] 通过 `/api/mcp/chat` 提问"有哪些容器在运行"，Agent 调用 `list_containers`
- [ ] 通过 `/api/mcp/chat` 提问"nginx 容器最近有什么日志"，Agent 调用 `container_logs`
- [ ] Docker Daemon 未运行时，Docker Server 返回友好错误信息（不崩溃）
- [ ] `docker compose up -d` 后 mcp-docker 服务正常启动

### 7.3 Web 搜索 MCP Server

- [ ] `python mcp_servers/search_server.py` 启动成功，端口 8007
- [ ] 有 TAVILY_API_KEY 时使用 Tavily 搜索，返回高质量结果
- [ ] 无 TAVILY_API_KEY 时自动降级使用 DuckDuckGo，返回搜索结果
- [ ] 通过 `/api/mcp/chat` 提问"最新的 Kubernetes 版本是多少"，Agent 调用 `web_search`
- [ ] 搜索结果包含标题、URL、摘要
- [ ] `docker compose up -d` 后 mcp-search 服务正常启动

---

## 附录 A：现有工具参考

### A.1 本地 @tool 模板（参考 shell_tool.py 的写法）

参考文件：[app/tools/calculator_tool.py](app/tools/calculator_tool.py) — 最简洁的本地工具示例（105 行）

### A.2 MCP Server 模板（参考 docker_server.py 和 search_server.py 的写法）

参考文件：[mcp_servers/db_server.py](mcp_servers/db_server.py) — 最完整的 MCP Server 示例（273 行）

### A.3 MCP Client 注册模板（向现有列表追加）

参考文件：[app/agent/mcp_client.py](app/agent/mcp_client.py) — `_build_mcp_servers()` 函数

---

## 附录 B：System Prompt 合并后的完整版

所有工具注册后，`mcp_agent_service.py` 的 `SYSTEM_PROMPT` 应更新为：

```python
SYSTEM_PROMPT = """你是一个智能运维助手，具备以下能力：

1. **知识库检索**（retrieve_knowledge 工具）：
   当用户问题涉及技术排查、故障诊断、运维操作时使用。

2. **时间查询**（get_current_time 工具）：
   当用户问「现在几点」或需要时间信息做判断时使用。

3. **数据库查询**（list_tables / describe_table / execute_query / get_row_count 工具）：
   当用户需要查看或分析数据库中的数据时使用。
   先 list_tables 了解有哪些表，再用 describe_table 看结构，最后 execute_query 查数据。

4. **PPT 生成**（create_presentation / add_table_slide / add_content_slide / export_pptx 工具）：
   当用户要求生成 PPT 或报告时使用。

5. **Shell 命令执行**（execute_shell 工具）：
   当用户需要查看系统状态、资源使用、进程信息、网络状态时使用。
   仅能执行只读诊断命令（top, free, df, ps, docker ps 等）。

6. **Docker 容器管理**（list_containers / container_stats / container_logs / restart_container 等工具）：
   当用户需要查看容器状态、日志、资源使用，或重启容器时使用。

7. **互联网搜索**（web_search 工具）：
   当知识库中没有相关信息，或用户询问最新技术动态、最新版本文档时使用。

重要规则：
- 调用工具后，基于工具返回的结果来回答
- 如果工具调用失败，诚实告知用户，尝试其他方式
- 回答用 Markdown 格式，中文回答
"""
```
