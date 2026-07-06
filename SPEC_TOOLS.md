# SPEC: 工具系统扩展

> **版本**: v2.0
> **创建日期**: 2026-06-23
> **状态**: 待开发
> **依赖**: 消息修剪、异常处理、日志系统、计算器工具 已完成
>
> **项目约束**: 技术栈、架构规范、编码风格、AI 禁止事项详见 `CLAUDE.md`。本 SPEC 仅定义三个新工具的开发规格。

---

## 一、概述

### 1.1 当前工具清单

| 工具 | 类型 | 来源 |
|------|------|------|
| `retrieve_knowledge` | 知识库检索 | 本地 `@tool` |
| `calculate` | 安全计算器 | 本地 `@tool` |
| `get_current_time` | 时间查询 | MCP Server :8003 |
| `list_tables` / `describe_table` / `execute_query` / `get_row_count` | 数据库查询 | MCP Server :8004 |
| `create_presentation` / `add_table_slide` / `add_content_slide` / `export_pptx` | PPT 生成 | MCP Server :8005 |

### 1.2 本次新增

| 工具 | 类型 | 端口 | 新增依赖 |
|------|------|:----:|---------|
| `execute_shell` | 本地 `@tool` | — | 无（仅 subprocess） |
| Docker 管理 (7 个工具*) | MCP Server | 8006 | `docker>=7.0.0` |
| `web_search` + `fetch_webpage` | MCP Server | 8007 | `tavily-python>=0.5.0`, `duckduckgo-search>=6.0` |

> *`list_containers`, `container_stats`, `container_logs`, `inspect_container`, `list_images`, `restart_container`, `container_processes`

---

## 二、工具一：`execute_shell`（本地 @tool）

### 2.1 基本信息

| 属性 | 值 |
|------|-----|
| **文件名** | `app/tools/shell_tool.py` |
| **工具名** | `execute_shell` |
| **工具类型** | 本地 `@tool`（同步函数） |

### 2.2 安全模型（四层防护）

```
第 1 层：命令白名单 → 命令必须在 ALLOWED_COMMANDS 集合中，不在则拒绝
第 2 层：参数黑名单 → 扫描危险模式（rm、dd、kill、$()、反引号等），命中则拒绝
第 3 层：资源限制  → 超时 30s，输出截断 5000 字符，禁止 shell=True（管道除外）
第 4 层：结果包装  → stdout/stderr 分别标注，返回退出码，超时/异常返回友好错误
```

### 2.3 命令白名单（只读诊断类）

```
系统信息: uname, hostname, uptime, whoami, id
进程管理: ps, top, pidof, pgrep
内存管理: free, vmstat
磁盘管理: df, du, lsblk, mount
网络诊断: ping, netstat, ss, ip, ifconfig, curl, wget, nslookup, dig, host, traceroute, tracepath
文件操作: ls, cat, head, tail, wc, find, stat, file
文本处理: grep, awk, sed, sort, uniq, cut, tr, column
系统日志: journalctl, dmesg
Docker: docker（仅限只读子命令：ps, images, logs, stats, inspect, version, info, network ls/inspect, volume ls/inspect, events）
```

### 2.4 参数黑名单模式

```
危险命令: rm, mv, dd, mkfs, shutdown, reboot, kill, chmod, chown, iptables
命令注入: $(...), `...`
Docker 危险子命令: docker rm/rmi/stop/kill/prune/system prune
```

### 2.5 工具签名

```python
@tool
def execute_shell(command: str) -> str:
    """安全地执行操作系统诊断命令（只读操作）。

    使用场景：
      - 用户问「CPU 使用率多少」「内存还剩多少」→ top, free
      - 用户问「磁盘满了没」→ df -h
      - 用户问「网络通不通」→ ping -c 3 8.8.8.8, curl -I https://example.com
      - 用户问「容器运行状态」→ docker ps, docker stats --no-stream
      - 用户问「系统日志有什么异常」→ journalctl -n 50 --no-pager

    安全限制：
      - 仅允许执行白名单内的命令（诊断/查看类）
      - 禁止任何修改系统的操作
      - 命令执行超时 30 秒
      - 输出超过 5000 字符自动截断

    参数：
        command: 完整的 shell 命令，如 "free -h"、"ps aux | head -20"。
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
```

### 2.6 实现要点

- 命令解析用 `shlex.split()`
- 管道数量 ≤3，引号内的 `|` 不计入
- subprocess 在线程池中异步执行（`loop.run_in_executor`）

### 2.7 注册位置

- `app/services/manual_agent_service.py` — `TOOLS` 列表 + `SYSTEM_PROMPT`
- `app/services/rag_agent_service.py` — `tools` 参数 + `SYSTEM_PROMPT`

### 2.8 验收标准

- [ ] `execute_shell("free -h")` 返回内存信息
- [ ] `execute_shell("rm -rf /")` 返回包含"不允许"的错误
- [ ] `execute_shell("sleep 60")` 30 秒后返回超时错误
- [ ] `/api/agent/chat` 提问"看看内存使用情况"，Agent 自动调用 execute_shell
- [ ] `/api/mcp/chat` 也能正常调用该工具
- [ ] 输出超过 5000 字符时截断，末尾标注"...（已截断）"

---

## 三、工具二：Docker 管理 MCP Server

### 3.1 基本信息

| 属性 | 值 |
|------|-----|
| **文件名** | `mcp_servers/docker_server.py` |
| **MCP Server 名** | `DockerTool` |
| **端口** | `8006` |
| **新增依赖** | `docker>=7.0.0` |

### 3.2 工具列表

| 工具名 | 风险等级 | 描述 |
|--------|:--------:|------|
| `list_containers` | 🟢 安全 | 列出所有容器及状态（支持 all 参数含已停止的） |
| `container_stats` | 🟢 安全 | 容器 CPU/内存/网络/IO 统计 |
| `container_logs` | 🟢 安全 | 容器日志（最近 N 行，最多 200） |
| `inspect_container` | 🟢 安全 | 容器详细信息（镜像、端口、挂载、环境变量） |
| `list_images` | 🟢 安全 | 本地 Docker 镜像列表 |
| `container_processes` | 🟢 安全 | 容器内进程列表 |
| `restart_container` | 🔴 危险 | 重启指定容器（需传 reason 参数说明原因） |

### 3.3 安全设计

- 只读操作（前 6 个）→ 直接执行，无需确认
- `restart_container` → 工具描述中明确标注 ⚠️ 危险，Agent 需自行判断是否真的需要重启
- 容器日志上限 200 行，统计信息上限 3000 字符
- Docker 连接失败 → 返回友好错误信息，不崩溃

### 3.4 工具签名摘要

```python
list_containers(all_containers: bool = False) -> str
container_stats(container_name: str) -> str
container_logs(container_name: str, tail: int = 50, since: str = "") -> str
inspect_container(container_name: str) -> str
list_images() -> str
container_processes(container_name: str) -> str
restart_container(container_name: str, reason: str = "") -> str
```

每个工具的 docstring 必须含：使用场景 / 参数 / 返回。

### 3.5 Docker Compose

新增 `mcp-docker` 服务：挂载 `/var/run/docker.sock`，端口 8006。

### 3.6 注册位置

- `app/agent/mcp_client.py` — `_build_mcp_servers()` 新增 `docker_tool`
- `app/config.py` — 新增 `mcp_docker_url`
- `app/services/mcp_agent_service.py` — `SYSTEM_PROMPT` 新增 Docker 管理说明

### 3.7 验收标准

- [ ] `python mcp_servers/docker_server.py` 启动成功，端口 8006
- [ ] `GET /api/mcp/tools` 返回 7 个 Docker 工具
- [ ] `/api/mcp/chat` 提问"有哪些容器在运行"，Agent 调用 `list_containers`
- [ ] `/api/mcp/chat` 提问"nginx 容器最近有什么日志"，Agent 调用 `container_logs`
- [ ] Docker Daemon 未运行时返回友好错误（不崩溃）
- [ ] `docker compose up -d` 后 mcp-docker 正常启动

---

## 四、工具三：Web 搜索 MCP Server

### 4.1 基本信息

| 属性 | 值 |
|------|-----|
| **文件名** | `mcp_servers/search_server.py` |
| **MCP Server 名** | `SearchTool` |
| **端口** | `8007` |
| **新增依赖** | `tavily-python>=0.5.0`, `duckduckgo-search>=6.0` |

### 4.2 搜索后端策略

```
有 TAVILY_API_KEY → Tavily（高质量，专为 AI Agent 设计）
无 TAVILY_API_KEY → DuckDuckGo（免费备选，降级方案）
```

延续项目的自愈降级理念。

### 4.3 工具列表

| 工具名 | 描述 |
|--------|------|
| `web_search` | 搜索互联网，返回标题+URL+摘要+相关度分数 |
| `fetch_webpage` | 获取指定 URL 的文本内容（用于深度阅读） |

### 4.4 工具签名摘要

```python
web_search(query: str, max_results: int = 5, search_depth: str = "basic") -> str
    # max_results: 1-10
    # search_depth: "basic" (快速) | "advanced" (深度)
    # 返回：Markdown 格式搜索结果列表

fetch_webpage(url: str, max_length: int = 3000) -> str
    # max_length: 最大 10000
    # 返回：已去除 HTML 标签的文本内容
```

### 4.5 Docker Compose

新增 `mcp-search` 服务，端口 8007。

### 4.6 注册位置

- `app/agent/mcp_client.py` — `_build_mcp_servers()` 新增 `search_tool`
- `app/config.py` — 新增 `mcp_search_url`
- `app/services/mcp_agent_service.py` — `SYSTEM_PROMPT` 新增搜索说明

### 4.7 验收标准

- [ ] `python mcp_servers/search_server.py` 启动成功，端口 8007
- [ ] 有 TAVILY_API_KEY 时使用 Tavily 搜索
- [ ] 无 TAVILY_API_KEY 时自动降级 DuckDuckGo
- [ ] `/api/mcp/chat` 提问"最新的 Kubernetes 版本"，Agent 调用 `web_search`
- [ ] 搜索结果含标题、URL、摘要
- [ ] `docker compose up -d` 后 mcp-search 正常启动

---

## 五、依赖与新增配置汇总

### 5.1 pyproject.toml

```toml
"docker>=7.0.0",
"tavily-python>=0.5.0",
"duckduckgo-search>=6.0",
```

### 5.2 app/config.py

```python
mcp_docker_url: str = "http://127.0.0.1:8006/mcp"
mcp_search_url: str = "http://127.0.0.1:8007/mcp"
shell_timeout: int = 30
shell_max_output: int = 5000
```

### 5.3 .env

```bash
MCP_DOCKER_URL=http://127.0.0.1:8006/mcp
MCP_SEARCH_URL=http://127.0.0.1:8007/mcp
TAVILY_API_KEY=
```

---

## 六、开发顺序

```
第 1 步: execute_shell（无外部依赖，可立即开始）
  └── 新建 app/tools/shell_tool.py → 注册到两个 agent service

第 2 步: Docker MCP Server（依赖 docker SDK）
  └── 新建 mcp_servers/docker_server.py → 注册到 mcp_client + config → docker-compose

第 3 步: Web Search MCP Server（依赖 tavily/duckduckgo）
  └── 新建 mcp_servers/search_server.py → 注册到 mcp_client + config → docker-compose
```

三个工具互不依赖，可并行开发。全部完成后统一更新 System Prompt。
