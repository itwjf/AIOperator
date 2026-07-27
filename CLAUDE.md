# CLAUDE.md — AIOperator 项目规范

> AI 开发助手必读。定义项目能做什么、不能做什么、怎么做。

---

## 一、项目身份

**AIOperator** — 基于 LangChain/LangGraph 的智能运维 Agent 系统（多用户版）。

- 4 种 Agent 模式：RAG Agent、手动 Agent、MCP Agent、AIOps 诊断
- 5 个 MCP Server：时间 / 数据库 / PPT / Docker / Web 搜索
- 用户认证：GitHub OAuth + JWT 无状态会话
- 可观测性：LangSmith 全链路追踪
- 前端：纯 HTML/CSS/JS 单页应用

## 二、技术栈（不可变更）

| 层 | 技术 | 约束 |
|----|------|------|
| 语言 | Python ≥3.11 | — |
| 包管理 | pip + pyproject.toml | 不用 poetry/uv/pipenv |
| Web 框架 | FastAPI + uvicorn | SSE 用 sse-starlette |
| LLM | **阿里云 DashScope**（qwen-plus） | ChatOpenAI 兼容接口，不可换供应商 |
| LLM 温度 | chat=0.7, 诊断/规划=0, 报告=0.3 | |
| Agent | LangChain create_agent + LangGraph StateGraph | |
| MCP | FastMCP + streamable-http | 端口 8003-8007 |
| 向量库 | Milvus 2.4 | 端口 19530 |
| 数据库 | MySQL 8.0 | 端口 3306 |
| 认证 | GitHub OAuth + JWT (PyJWT) | 不存储密码，不用 bcrypt |
| HTTP 客户端 | httpx | GitHub API 调用 |
| 可观测性 | LangSmith | 环境变量启用，零代码改动 |
| 流控 | slowapi | 内存存储 |
| 配置 | pydantic-settings BaseSettings | `app/config.py` 集中管理 |
| 日志 | **loguru**（唯一） | `from app.core.logger import logger` |
| 部署 | Docker Compose | 单 Dockerfile，多 service |

## 三、目录结构（目标态）

> 部分文件尚在开发中。以 `plan/IMPLEMENTATION_PLAN.md` 进度为准。

```
AIOperator/
├── app/
│   ├── main.py              # FastAPI 入口 + 路由注册 + LangSmith 启动
│   ├── config.py            # 全局配置（BaseSettings，读 .env）
│   ├── api/                 # 路由层（参数解析 + 调用服务层）
│   │   ├── chat.py          # RAG Agent 对话
│   │   ├── agent.py         # 手动 Agent 对话
│   │   ├── mcp.py           # MCP Agent 对话 + 工具列表
│   │   ├── aiops.py         # AIOps 诊断
│   │   ├── file.py          # 文件上传
│   │   ├── title.py         # 会话标题生成
│   │   ├── auth.py          # GitHub OAuth 回调 + 当前用户
│   │   └── session.py       # 会话管理 CRUD
│   ├── core/                # 核心基础设施
│   │   ├── llm_factory.py   # LLM 实例工厂
│   │   ├── logger.py        # loguru 初始化
│   │   ├── exceptions.py    # 异常类层次
│   │   ├── message_trimmer.py  # 对话历史修剪
│   │   ├── checkpoint.py    # Agent 记忆持久化
│   │   ├── milvus_client.py # Milvus 连接单例
│   │   ├── security.py      # JWT 生成/验证
│   │   ├── auth_middleware.py  # 鉴权 Depends 注入
│   │   ├── db.py            # MySQL 连接工具
│   │   └── rate_limiter.py  # slowapi 流控
│   ├── services/            # 业务逻辑
│   │   ├── rag_agent_service.py
│   │   ├── manual_agent_service.py
│   │   ├── mcp_agent_service.py
│   │   ├── aiops_service.py
│   │   ├── session_service.py   # 会话 CRUD
│   │   ├── message_service.py   # 消息存取
│   │   ├── llm_guard.py         # LLM 并发队列
│   │   └── ...（vector_store / embedding / document_splitter）
│   ├── agent/               # Agent 组件
│   │   ├── mcp_client.py    # MCP 客户端管理器（单例 + Token 注入）
│   │   └── aiops/           # Plan-Execute-Replan 节点
│   └── tools/               # 本地 @tool 函数
├── mcp_servers/             # 5 个独立 MCP 进程
├── static/                  # 前端（含 login.html + js/ 组件）
├── plan/                    # 规划文档（ROADMAP + IMPLEMENTATION_PLAN）
├── migrations/              # 数据库 DDL（按序号命名）
├── tests/                   # pytest
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── .env / .env.example
└── SPEC_*.md
```

## 四、核心架构约束（不可破坏）

### 4.1 单例模式

以下资源用模块级全局变量 + 懒初始化：

- `_agent` / `_graph` — Agent 实例和编译后的图
- `_client` — MilvusClient / AsyncOpenAI / MultiServerMCPClient
- `MCPClientManager._instance` — MCP 客户端管理器
- `_savers` (checkpoint.py) — AsyncSqliteSaver 缓存

### 4.2 自愈降级

外部依赖不可用时降级而非崩溃：

- MCP Server 挂了 → `get_tools()` 返回空列表
- Milvus 挂了 → raise `VectorDBError`，服务层 catch
- LLM API 挂了 → raise `LLMServiceError`，服务层 catch
- GitHub API 不可用 → 登录回调 503，已登录用户不受影响
- LangSmith 不可用 → 追踪静默失败，不影响功能

### 4.3 三层异常处理

```
基础设施层 → raise AIOperatorException 子类
服务层      → catch → 返回友好错误消息
API 层      → catch → HTTPException + 状态码
```

异常子类（`app/core/exceptions.py`，不可修改层次）：`LLMServiceError`, `EmbeddingServiceError`, `VectorDBError`, `DocumentProcessError`, `MCPServiceError`

### 4.4 用户认证模型

- 唯一认证方式：GitHub OAuth → JWT
- 不存储密码，无注册页，无密码登录
- JWT 24 小时过期，无状态验证
- `get_current_user` 通过 FastAPI `Depends` 注入
- 公开路由白名单：`/health`, `/docs`, `/openapi.json`, `/static`, `/api/auth`

### 4.5 用户数据隔离

```
thread_id = f"{current_user['id']}:{session_id}"   # API 层拼接
```

- sessions / messages 表查询必须带 `WHERE user_id = ?`
- 禁止从前端传入 user_id，必须从 JWT 解析
- 禁止在 API 响应中返回其他用户的数据

### 4.6 MCP Server 安全

- 5 个 MCP Server 校验 `Authorization: Bearer <MCP_SECRET_TOKEN>`
- `/health` 白名单放行
- Token 未配置时放行（开发阶段向后兼容）
- MCP Client 在 `_build_mcp_servers()` 中自动注入 token

### 4.7 DB 工具安全（四层）

1. 表级黑名单（`DB_BLACKLIST_TABLES` 环境变量）
2. SQL 白名单（只允许 SELECT/SHOW/DESCRIBE/EXPLAIN）
3. 只读 MySQL 账号（无敏感表权限）
4. 审计日志（JSON 格式记录所有查询）

### 4.8 流式协议

统一 SSE 格式：`content`, `tool_start`, `done`, `error`
AIOps 额外：`plan`, `step_start`, `step_result`, `replan`, `report`

## 五、代码风格

- 导入顺序：标准库 → 第三方 → 项目内部（空行分隔）
- 公开函数必须有 docstring
- 返回值类型用 `str | None`，不用 `Optional[str]`
- 日志统一 `from app.core.logger import logger`，格式 `logger.info("描述 — {}", var)`
- 配置统一 `from app.config import settings`，不直接 `os.getenv()`
- 注释/docstring 用中文，标识符用英文，用户错误消息用中文
- MCP Server 独立进程顶部加 `load_dotenv()`，不 import `app.config`

## 六、AI 禁止事项

### 技术栈
- ❌ 不得切换 LLM 供应商（DashScope/qwen-plus 不可变）
- ❌ 不得引入 poetry/uv/pipenv
- ❌ 不得移除或替换 loguru
- ❌ 不得引入密码登录/微信/钉钉等新认证方式

### 安全
- ❌ 不得绕过安全白名单/黑名单
- ❌ 不得在 SQL 中拼接用户输入（必须参数化 `%s`）
- ❌ 不得硬编码 JWT_SECRET_KEY / MCP_SECRET_TOKEN
- ❌ 不得在 API 响应中泄露其他用户数据
- ❌ 不得从前端传入的字段中取 user_id

### 架构
- ❌ 不得破坏自愈降级（外部调用必须有 try/except）
- ❌ 不得修改现有函数签名（除非计划文档明确要求）
- ❌ 不得跳过认证 Depends（业务 API 必须声明 `current_user`）
- ❌ 不得修改 `app/core/exceptions.py` 异常类层次
- ❌ 不得在 @tool 函数签名中新增参数
- ❌ 不得在 MCP Server 中 `from app.config import settings`

## 七、开发流程

### 7.1 按阶段执行

所有多用户化改造严格按 `plan/IMPLEMENTATION_PLAN.md` 的阶段顺序进行，不可跳阶段。架构决策参考 `plan/ROADMAP.md`。

### 7.2 进度更新（每次会话结束必须执行）

每次开发会话完成后，更新 `plan/IMPLEMENTATION_PLAN.md`：

1. 完成的子任务 checkbox 从 `- [ ]` 改为 `- [x]`
2. 阶段状态更新：`⬜ 待开始` → `🔄 进行中` → `✅ 已完成`
3. 填入实际日期（格式 `YYYY-MM-DD`）
4. 上阶段完成前不开始下阶段

### 7.3 依赖管理

- 新增依赖 → `pyproject.toml` 的 `dependencies` 列表
- 新增后运行 `pip install -e .`
- 不在 pyproject.toml 中写注释

### 7.4 数据库变更

- DDL 放 `migrations/` 目录，按 `001_xxx.sql` 格式命名
- 手动执行，不引入 Alembic

## 八、常用命令

```bash
# 环境搭建
python -m venv .venv && .venv\Scripts\activate
pip install -e .
cp .env.example .env   # 编辑填入真实 Key

# 生成安全密钥
python -c "import secrets; print(secrets.token_urlsafe(48))"

# 初始化数据库
mysql -u root -p aioperator < migrations/001_create_users.sql

# 启动（分 6 个终端）
python mcp_servers/time_server.py      # :8003
python mcp_servers/db_server.py        # :8004
python mcp_servers/ppt_server.py       # :8005
python mcp_servers/docker_server.py    # :8006
python mcp_servers/search_server.py    # :8007
python app/main.py                     # :9900

# 验证
curl http://127.0.0.1:9900/health
curl http://127.0.0.1:9900/docs        # Swagger

# 测试
pip install -e ".[dev]"
pytest -v

# Docker 部署
docker compose up -d --build
docker compose logs -f app
docker compose down
```

## 九、工具清单

### 本地工具（`app/tools/`）

| 工具 | 说明 |
|------|------|
| `retrieve_knowledge` | Milvus 语义搜索 |
| `calculate` | 安全数学表达式计算 |
| `execute_shell` | 安全 Shell 命令执行 |

### MCP Time Server（:8003）

`get_current_time` — 时区时间查询

### MCP DB Server（:8004）

`list_tables`, `describe_table`, `execute_query`, `get_row_count`
— 只读查询 + 表黑名单 + 只读账号

### MCP PPT Server（:8005）

`create_presentation`, `add_table_slide`, `add_content_slide`, `export_pptx`

### MCP Docker Server（:8006）

`list_containers`, `container_stats`, `container_logs`, `inspect_container`, `list_images`, `container_processes`, `restart_container`

### MCP Search Server（:8007）

`web_search`, `fetch_webpage`

## 十、端口分配

| 端口 | 服务 |
|:----:|------|
| 9900 | FastAPI 主应用 |
| 8003 | MCP Time |
| 8004 | MCP DB |
| 8005 | MCP PPT |
| 8006 | MCP Docker |
| 8007 | MCP Search |
| 19530 | Milvus |
| 3306 | MySQL |
