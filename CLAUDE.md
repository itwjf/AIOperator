# CLAUDE.md — AIOperator 项目规范

> AI 开发助手必读。每次对话自动加载，定义了本项目能做什么、不能做什么、怎么做。

---

## 一、项目身份

**AIOperator** — 基于 LangChain/LangGraph 的智能运维 Agent 系统。

- 4 种 Agent 模式：RAG Agent、手动 Agent、MCP Agent、AIOps 诊断
- 3 个 MCP Server：时间服务、数据库服务、PPT 生成服务
- 1 个向量知识库：Milvus + DashScope Embedding
- 前端：纯 HTML/CSS/JS 单页应用（`static/`）

## 二、技术栈（不可变更）

| 层 | 技术 | 版本约束 |
|----|------|---------|
| 语言 | Python | ≥3.11 |
| 包管理 | pip + pyproject.toml | 不用 poetry/uv/pipenv |
| Web 框架 | FastAPI + uvicorn | SSE 用 sse-starlette |
| LLM | **阿里云 DashScope**（qwen-plus） | 通过 ChatOpenAI 兼容接口 |
| LLM 温度 | chat=0.7, 诊断/规划=0, 报告=0.3 | |
| Agent | LangChain create_agent + LangGraph StateGraph | |
| MCP | FastMCP + streamable-http transport | 端口 8003-8007 |
| 向量库 | Milvus 2.4 | 端口 19530 |
| 数据库 | MySQL 8.0 | 端口 3306 |
| 配置 | pydantic-settings BaseSettings | `app/config.py` 集中管理 |
| 日志 | **loguru**（唯一日志库） | 入口：`from app.core.logger import logger` |
| 部署 | Docker Compose | 一个 Dockerfile，多 service |

## 三、目录结构

```
AIOperator/
├── app/
│   ├── main.py              # FastAPI 入口 + 路由注册 + uvicorn 启动
│   ├── config.py            # 全局配置（BaseSettings，从 .env 读取）
│   ├── api/                 # API 路由层（只做参数解析 + 调用服务层）
│   │   ├── chat.py          # POST /api/chat, /api/chat_stream → RAG Agent
│   │   ├── agent.py         # POST /api/agent/chat, /api/agent/chat_stream → 手动 Agent
│   │   ├── mcp.py           # POST /api/mcp/chat, /api/mcp/chat_stream, GET /api/mcp/tools
│   │   ├── aiops.py         # POST /api/aiops → AIOps 诊断
│   │   ├── file.py          # POST /api/upload → 文档上传入库
│   │   └── title.py         # POST /api/title/summarize → 会话标题生成
│   ├── core/                # 核心基础设施
│   │   ├── llm_factory.py   # create_llm() + create_llm_streaming()
│   │   ├── logger.py        # loguru 日志系统初始化
│   │   ├── exceptions.py    # 应用异常类层次
│   │   ├── message_trimmer.py  # 对话历史滑动窗口修剪
│   │   └── milvus_client.py # Milvus 连接单例 + Collection 管理
│   ├── services/            # 业务逻辑层
│   │   ├── rag_agent_service.py     # RAG Agent（create_agent + knowledge_tool）
│   │   ├── manual_agent_service.py  # 手动 Agent（StateGraph + ToolNode）
│   │   ├── mcp_agent_service.py     # MCP Agent（本地工具 + MCP 远程工具混合）
│   │   ├── aiops_service.py         # AIOps 诊断（Plan-Execute-Replan 工作流）
│   │   ├── vector_store_manager.py  # Milvus 读写（add / search / delete）
│   │   ├── embedding_service.py     # DashScope Embedding（批量 + 单条）
│   │   └── document_splitter.py     # Markdown 文档两级分割
│   ├── agent/               # Agent 组件
│   │   ├── mcp_client.py    # MCPClientManager 单例（自愈连接 + 重试）
│   │   └── aiops/           # AIOps 工作流节点
│   │       ├── state.py     # PlanExecuteState 类型定义
│   │       ├── planner.py   # Planner 节点（生成诊断计划）
│   │       ├── executor.py  # Executor 节点（执行单步）
│   │       └── replanner.py # Replanner 节点（评估进度 + 决策）
│   └── tools/               # 本地工具（@tool 装饰器）
│       ├── knowledge_tool.py   # retrieve_knowledge — Milvus 语义搜索
│       ├── calculator_tool.py  # calculate — 安全数学表达式计算
│       └── time_tool.py        # get_current_time — 时区时间查询
├── mcp_servers/             # MCP Server（独立进程）
│   ├── time_server.py       # TimeTool :8003
│   ├── db_server.py         # DBTool :8004（MySQL 只读查询）
│   └── ppt_server.py        # PPTTool :8005（PPT 生成）
├── static/                  # 前端（HTML/CSS/JS 单页应用）
├── aiops-docs/              # 知识库 Markdown 源文件
├── logs/                    # 日志文件（按天轮转）
├── output/                  # PPT 导出目录
├── docker-compose.yml       # 8 个服务：mysql, milvus, app, 5×mcp
├── Dockerfile               # 单镜像多服务
├── pyproject.toml           # 依赖管理
├── .env                     # 环境变量（含 secrets，不提交 git）
├── start.bat / stop.bat     # 本地开发启停脚本
└── SPEC_*.md                # SPEC 规范文档
```

## 四、核心架构约束（不可破坏）

### 4.1 单例模式

以下资源必须用模块级全局变量 + 懒初始化：

- `_agent` — Agent 实例（`rag_agent_service`, `manual_agent_service`, `mcp_agent_service`）
- `_memory` — MemorySaver（每个 service 独立）
- `_graph` — StateGraph 编译结果
- `_client` — MilvusClient / AsyncOpenAI / MultiServerMCPClient
- `MCPClientManager._instance` — MCP 客户端管理器

### 4.2 自愈降级

**所有外部依赖不可用时，系统降级而非崩溃：**

- MCP Server 挂了 → `get_tools()` 返回空列表，Agent 用剩余工具继续
- Milvus 挂了 → raise `VectorDBError`，服务层 catch 返回友好消息
- LLM API 挂了 → raise `LLMServiceError`，服务层 catch 返回友好消息

### 4.3 三层异常处理

```
基础设施层（core/services 底层）
  → raise AIOperatorException 子类（LLMServiceError, VectorDBError, ...）

服务层（services/*）
  → catch AIOperatorException → 返回友好错误消息字符串

API 层（api/*）
  → catch AIOperatorException → raise HTTPException 带状态码
```

详见 `app/core/exceptions.py` 的 6 个异常子类。

### 4.4 安全模型

- 所有涉及外部输入的操作必须有白名单/黑名单校验
- `execute_shell`：四层防护（命令白名单 → 参数黑名单 → 资源限制 → 结果包装）
- `execute_query`：SQL 前缀白名单 + 表黑名单
- `calculate`：`eval` 命名空间白名单 + 危险关键字检测
- 校验失败 → 返回明确拒绝信息（不是模糊的"操作失败"）

### 4.5 流式协议

所有流式接口统一 SSE 格式：
```json
{"type": "content", "data": "token"}
{"type": "tool_start", "data": "工具名"}
{"type": "done"}
{"type": "error", "data": "错误信息"}
```
AIOps 额外类型：`plan`, `step_start`, `step_result`, `replan`, `report`

## 五、代码风格（AI 必须遵守）

### 5.1 文件结构

- 每个 `.py` 顶部：模块级 `"""docstring"""` 说明用途
- 导入顺序：标准库 → 第三方 → 项目内部（每组空一行）
- MCP Server 独立运行时顶部加 `load_dotenv()`，不 import `app.config`

### 5.2 函数规范

- 公开函数：有 docstring
- **@tool 函数 docstring 固定四段**：使用场景 / 参数 / 返回 / 安全限制（如有）
- 函数返回值类型用 `str | None` 语法（Python 3.10+），不用 `Optional[str]`

### 5.3 日志

- 统一：`from app.core.logger import logger`
- 格式：`logger.info("描述 — {}", variable)`，用 `—` 分隔
- 异常路径：`logger.warning` 或 `logger.error`
- 不引入 print、logging、其他日志库

### 5.4 配置

- `from app.config import settings`，不直接 `os.getenv()`
- 新增配置 → `app/config.py` 加字段 + `.env` 加变量
- MCP Server 例外：独立进程可用 `os.getenv()`

## 六、AI 禁止事项

- ❌ **不得切换 LLM 供应商**（DashScope / qwen-plus 不可变）
- ❌ **不得引入新依赖管理工具**（不用 poetry/uv/pipenv）
- ❌ **不得移除或替换 loguru**
- ❌ **不得绕过安全白名单/黑名单**
- ❌ **不得破坏自愈降级**（外部调用必须有 try/except 兜底）
- ❌ **不得修改 `app/core/exceptions.py` 的异常类层次**
- ❌ **不得在 MCP Server 中 `from app.config import settings`**（MCP Server 是独立进程）
- ❌ **不得修改现有函数签名**（除非 SPEC 明确要求）
- ❌ **不得在 @tool 函数签名中新增参数**（LangChain 靠签名推断 input schema）

## 七、开发规范

### 7.1 按 SPEC 开发

| 要开发的功能 | 先读的 SPEC |
|-------------|------------|
| 新增工具（Shell/Docker/WebSearch） | `SPEC_TOOLS.md` |

### 7.2 依赖管理

- 新增依赖 → `pyproject.toml` 的 `dependencies` 列表
- 不在 `pyproject.toml` 中加注释（会被 pip 解析器忽略）

### 7.3 Docker Compose

- 新 MCP Server → 新增 service（容器名 `aioperator-mcp-xxx`，端口不冲突）
- 新 volumes → `volumes:` 节新增
- 本地地址 127.0.0.1，容器内用容器名

### 7.4 注释语言

- 代码标识符（变量名、函数名、类名）→ **英文**
- 注释和 docstring → **中文**
- 给用户看的错误消息 → **中文**

## 八、常用命令

```bash
# 本地开发启动
python app/main.py                    # 主应用 :9900
python mcp_servers/time_server.py     # 时间服务 :8003
python mcp_servers/db_server.py       # 数据库服务 :8004
python mcp_servers/ppt_server.py      # PPT 服务 :8005
# 或一键：start.bat

# Docker 部署
docker compose up -d                  # 启动全部服务
docker compose logs -f app            # 查看主应用日志
docker compose down                   # 停止全部服务

# 安装依赖
pip install -e .                      # editable 模式（pyproject.toml）

# 验证接口
curl http://127.0.0.1:9900/health
curl -X POST http://127.0.0.1:9900/api/chat -H "Content-Type: application/json" -d '{"question":"你好"}'
```

## 九、当前工具清单

| 工具 | 来源 | 类型 | 说明 |
|------|------|------|------|
| `retrieve_knowledge` | `app/tools/knowledge_tool.py` | 本地 @tool | Milvus 语义搜索 |
| `calculate` | `app/tools/calculator_tool.py` | 本地 @tool | 安全数学计算 |
| `get_current_time` | `mcp_servers/time_server.py` | MCP :8003 | 时区时间查询 |
| `list_tables` | `mcp_servers/db_server.py` | MCP :8004 | 列出数据库表 |
| `describe_table` | `mcp_servers/db_server.py` | MCP :8004 | 查看表结构 |
| `execute_query` | `mcp_servers/db_server.py` | MCP :8004 | 只读 SQL 查询 |
| `get_row_count` | `mcp_servers/db_server.py` | MCP :8004 | 表行数统计 |
| `create_presentation` | `mcp_servers/ppt_server.py` | MCP :8005 | 创建 PPT |
| `add_table_slide` | `mcp_servers/ppt_server.py` | MCP :8005 | 添加表格页 |
| `add_content_slide` | `mcp_servers/ppt_server.py` | MCP :8005 | 添加文字页 |
| `export_pptx` | `mcp_servers/ppt_server.py` | MCP :8005 | 导出 PPT 文件 |

## 十、端口分配

| 端口 | 服务 | 说明 |
|:----:|------|------|
| 9900 | FastAPI 主应用 | 含前端页面 |
| 8003 | MCP Time | 时间查询 |
| 8004 | MCP DB | 数据库查询 |
| 8005 | MCP PPT | PPT 生成 |
| 8006 | MCP Docker | Docker 容器管理 |
| 8007 | MCP Search | Web 搜索 |
| 19530 | Milvus | 向量数据库 |
| 3306 | MySQL | 关系型数据库 |
