# 🤖 AIOperator — AI 智能助手

<div align="center">

**RAG + Agent + MCP 全栈 AI 智能助手平台**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![LangChain](https://img.shields.io/badge/LangChain-0.3+-green.svg)](https://www.langchain.com/)
[![Milvus](https://img.shields.io/badge/Milvus-2.4+-orange.svg)](https://milvus.io/)
[![Docker](https://img.shields.io/badge/Docker-✔-2496ED.svg)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

---

## 📖 目录

- [项目简介](#项目简介)
- [核心特性](#核心特性)
- [架构概览](#架构概览)
- [快速开始](#快速开始)
- [项目结构](#项目结构)
- [API 文档](#api-文档)
- [使用场景](#使用场景)
- [技术栈](#技术栈)
- [架构设计要点](#架构设计要点)
- [部署指南](#部署指南)
- [常见问题](#常见问题)
- [License](#license)

---

## 项目简介

**AIOperator** 是一个基于 **LangChain** 的 **全能 AI 智能助手**。它完整实现了 RAG 检索增强生成、Agent 工具调用、Plan-Execute-Replan 自动诊断工作流、数据库查询、PPT 生成以及 MCP（Model Context Protocol）远程工具集成。

项目的设计理念是 **"理解底层，不依赖黑盒"**—— 不仅使用 LangChain 的高级封装 `create_agent`，还手动用 `StateGraph` + `ToolNode` + `bind_tools` 搭建了完全等价的 Agent 图，让整个 Agent 的运作机制清晰可控。

> 🎯 **适用场景**: 智能问答、知识库检索、Agent 工作流、自动诊断、MCP 工具集成、PPT 报告生成

---

## 核心特性

### 🧠 RAG 智能问答
- 文件上传 → 文档分割 → Embedding 向量化 → Milvus 向量存储 → 语义检索
- Agent 自动判断是否需要查知识库，无需用户手动触发
- 支持 Markdown / TXT 文档，引用来源可追溯

### 🤖 双模式 Agent
| 模式 | 实现方式 | API 路径 | 适用场景 |
|------|---------|---------|---------|
| **RAG Agent** | `create_agent`（黑盒封装） | `/api/chat` | 快速集成，开箱即用 |
| **Manual Agent** | `StateGraph` + `ToolNode`（手动搭建） | `/api/agent/chat` | 透明可控，深度定制 |

两种模式功能完全等价，前者胜在简洁，后者胜在透明可控。

### 🔍 Plan-Execute-Replan 诊断工作流

```
START → Planner（制定计划）→ Executor（执行步骤）→ Replanner（评估 & 决策）
                ↑                                               │
                └─────────── continue / replan ←───────────────┘
                                    │
                              respond ↓
                              Reporter（生成报告）→ END
```

- **Planner**: 根据用户任务 + 知识库相似案例，制定 3–5 步诊断计划
- **Executor**: 专注执行当前步骤，子 Agent 自动调用知识检索 / 时间工具
- **Replanner**: 评估进度，决定继续、调整计划还是生成报告
- **Reporter**: 综合所有步骤结果，生成结构化 Markdown 诊断报告
- **保护机制**: 最多执行 5 步，防止死循环

### 🔌 工具体系（10+ 个工具，3 类来源）

Agent 可同时使用本地工具和远程 MCP 工具，对工具来源完全透明：

| 来源 | 工具数 | 说明 |
|------|:------:|------|
| **本地 @tool** | 4 | `retrieve_knowledge`、`calculate`、`get_current_time`、`execute_shell` |
| **MCP Server** | 14 | 时间、数据库、PPT、Docker 管理、Web 搜索 |
| **总计** | ~~11~~ → **18** | 本次新增 7 个（Shell + Docker ×7 + Search ×2，去重时间工具） |

#### MCP Server 一览

| MCP Server | 端口 | 工具数 | 关键工具 |
|------------|:----:|:------:|------|
| **Time Server** | 8003 | 1 | `get_current_time` — 时区感知时间查询 |
| **DB Server** | 8004 | 4 | `list_tables`、`describe_table`、`execute_query`、`get_row_count` |
| **PPT Server** | 8005 | 4 | `create_presentation`、`add_content_slide`、`add_table_slide`、`export_pptx` |
| **Docker Server** 🆕 | 8006 | 7 | `list_containers`、`container_stats`、`container_logs`、`inspect_container`、`list_images`、`container_processes`、`restart_container` |
| **Search Server** 🆕 | 8007 | 2 | `web_search`、`fetch_webpage` |

#### 安全设计亮点

- **Shell 工具四层防护**: 命令白名单 → 参数黑名单 → 资源限制（30s/5000 字符）→ 结果包装
- **自愈降级**: MCP Server 不可用时自动切换备用方案或降级为纯本地模式
- **搜索双后端**: 有 `TAVILY_API_KEY` → Tavily（高质量），无 → DuckDuckGo（免费）

### 🌊 SSE 流式响应
所有对话接口均支持 SSE（Server-Sent Events）流式输出：
- 实时推送 AI 生成的文本 Token
- 展示工具调用状态（`tool_start` 事件）
- Plan-Execute-Replan 各阶段进度可视化

### 🖥 Vue 3 交互式前端
- 四种模式一键切换：对话 / Agent / 诊断 / MCP
- 诊断计划实时展示，步骤进度可视化
- 会话管理：创建、切换、删除，自动生成标题
- 文件上传：支持拖拽或选择 Markdown/TXT 文件
- Markdown 渲染 + 代码高亮

### 🐳 Docker 一键部署
全栈容器化，一条命令拉起所有服务（FastAPI + 5 MCP Server + MySQL + Milvus）。详见 [部署指南](#部署指南)。

---

## 架构概览

```
┌─────────────────────────────────────────────────────┐
│                前端 (Vue 3 + Vite)                    │
│        frontend/ → npm run build → dist/             │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP/SSE
┌──────────────────────┴──────────────────────────────┐
│                  FastAPI 应用层                        │
│                                                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐  │
│  │ /api/    │ │/api/agent│ │/api/aiops│ │/api/mcp│  │
│  │  chat    │ │  /chat   │ │          │ │        │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └───┬────┘  │
│       │             │             │            │      │
│  ┌────┴─────────────┴─────────────┴────────────┴──┐  │
│  │                Services 层                       │  │
│  │  rag_agent_service  │ manual_agent_service      │  │
│  │  aiops_service      │ mcp_agent_service         │  │
│  └────────────────────┬───────────────────────────┘  │
│                       │                               │
│  ┌────────────────────┴───────────────────────────┐  │
│  │              Agent / Tools 层                    │  │
│  │  AIOps Planner/Executor/Replanner               │  │
│  │  knowledge_tool │ time_tool │ mcp_client        │  │
│  └────────────────────┬───────────────────────────┘  │
│                       │                               │
│  ┌────────────────────┴───────────────────────────┐  │
│  │              Infrastructure 层                   │  │
│  │  Milvus │ DashScope(LLM) │ MySQL │ Embedding   │  │
│  └─────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘

┌───────────────────────────────────────┐
│        MCP Servers（独立进程）          │
│                                       │
│  time_server   (8003) — 时间服务       │
│  db_server     (8004) — 数据库服务     │
│  ppt_server    (8005) — PPT 生成服务   │
│  docker_server (8006) — Docker 管理 🆕 │
│  search_server (8007) — Web 搜索   🆕 │
│  (均基于 FastMCP，通过 HTTP 暴露工具)   │
└───────────────────────────────────────┘
```

---

## 快速开始

### 方式一：Docker 一键部署（推荐）

```bash
# 1. 克隆项目
git clone https://github.com/itwjf/AIOperator.git
cd AIOperator

# 2. 配置环境变量（从模板复制，填入真实 API Key）
cp .env.example .env
# 编辑 .env，修改 DASHSCOPE_API_KEY 为你的真实 Key

# 3. 一键启动
docker compose up -d

# 4. 查看状态
docker compose ps

# 5. 浏览器打开
# http://localhost:9900
```

> 📖 详细部署说明、故障排查、生产环境配置请阅读 **[DEPLOY.md](DEPLOY.md)**。

### 方式二：本地开发运行（开发阶段推荐）

> ⚡ **开发阶段请使用本地方式，不要用 Docker。**  
> Docker 每次改代码都需要重新 build 镜像（下载 pip 包很慢），本地 `pip install -e .` 修改代码即时生效，配合 `--reload` 热重载，开发效率远高于 Docker。

#### 环境要求

| 依赖 | 版本 | 说明 |
|------|------|------|
| Python | ≥ 3.11 | 运行环境 |
| Node.js | 20 + npm | 前端构建（Vite + Vue 3） |
| MySQL | 8.0 | 关系型数据库（DB MCP Server 需要，可选） |
| Milvus | ≥ 2.4 | 向量数据库（可选） |
| DashScope API Key | — | 阿里云百炼平台（LLM + Embedding） |

#### 首次环境搭建

```bash
# 1. 创建虚拟环境
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

# 2. 安装依赖（editable 模式，修改代码即时生效）
pip install -e .

# 3. 配置环境变量（从模板复制，填入真实 API Key）
cp .env.example .env
# 编辑 .env，修改 DASHSCOPE_API_KEY 为你的真实 Key

# 4. 安装前端依赖（Vue 3 + Vite，仅首次需要）
cd frontend
npm install
cd ..
```

> 💡 **获取 API Key**: 前往 [阿里云百炼平台](https://bailian.console.aliyun.com/) 开通 DashScope 服务。

关键配置项（`.env`）：

```bash
# LLM（必填）
DASHSCOPE_API_KEY=sk-your-api-key-here
LLM_MODEL=qwen-plus

# 向量数据库（如使用 RAG 功能）
MILVUS_HOST=127.0.0.1
MILVUS_PORT=19530

# MySQL（DB MCP Server 使用，可选）
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your-password
DB_NAME=aioperator
```

```bash
# 4. 启动基础设施（按需）
# 如果需要 Milvus 向量数据库：
docker compose -f vector-database.yml up -d
# 如果需要 MySQL（DB MCP Server 使用），确保本地 MySQL 服务已启动
```

#### 日常开发启动（分终端）

MCP Server 支持"按需启动"——只需要启动你实际用到的 MCP 服务，未启动的服务会自动降级跳过。

```bash
# 终端 1：MCP 时间服务
python mcp_servers/time_server.py         # :8003

# 终端 2：MCP 数据库服务
python mcp_servers/db_server.py           # :8004

# 终端 3：MCP PPT 生成服务
python mcp_servers/ppt_server.py          # :8005

# 终端 4：MCP Docker 管理服务 🆕
python mcp_servers/docker_server.py       # :8006

# 终端 5：MCP Web 搜索服务 🆕
python mcp_servers/search_server.py       # :8007

# 终端 6：主应用（--reload 热重载）
python app/main.py                        # :9900
# 或 uvicorn app.main:app --host 127.0.0.1 --port 9900 --reload

# 终端 7：前端（Vite dev server，自动代理 API 到 :9900）
cd frontend && npm run dev                # :5173
```

浏览器打开：
- **前端开发地址**：http://127.0.0.1:5173（Vite 自动代理 `/api`、`/health` 到 :9900）
- **后端 API**：http://127.0.0.1:9900，API 文档见 http://127.0.0.1:9900/docs

#### 上传知识库文档

1. 点击侧边栏底部的「📄 上传文档」按钮
2. 选择 Markdown 或 TXT 文件
3. 上传成功后即可在对话中检索相关知识

---

## 项目结构

```
AIOperator/
├── app/                           # 应用主目录
│   ├── main.py                    # FastAPI 入口，路由注册
│   ├── config.py                  # 全局配置（pydantic-settings）
│   ├── api/                       # API 路由层
│   │   ├── chat.py                #   /api/chat, /api/chat_stream
│   │   ├── agent.py               #   /api/agent/chat, /api/agent/chat_stream
│   │   ├── aiops.py               #   /api/aiops (诊断接口)
│   │   ├── mcp.py                 #   /api/mcp/chat, /api/mcp/tools
│   │   ├── file.py                #   /api/upload (文件上传)
│   │   └── title.py               #   /api/title/summarize (会话标题)
│   ├── services/                  # 业务逻辑层
│   │   ├── rag_agent_service.py   #   RAG Agent (create_agent)
│   │   ├── manual_agent_service.py#   手动 Agent (StateGraph)
│   │   ├── aiops_service.py       #   Plan-Execute-Replan 工作流
│   │   ├── mcp_agent_service.py   #   MCP 混合 Agent
│   │   ├── document_splitter.py   #   文档分割器
│   │   ├── embedding_service.py   #   向量化服务
│   │   └── vector_store_manager.py#   Milvus 读写封装
│   ├── agent/                     # Agent 核心模块
│   │   ├── aiops/                 #   AIOps 诊断
│   │   │   ├── state.py           #     状态定义
│   │   │   ├── planner.py         #     规划器
│   │   │   ├── executor.py        #     执行器
│   │   │   └── replanner.py       #     重规划器
│   │   └── mcp_client.py          #   MCP 客户端管理器
│   ├── tools/                     # Agent 工具（4 个本地工具）
│   │   ├── knowledge_tool.py      #   知识库检索工具
│   │   ├── calculator_tool.py     #   安全数学计算器
│   │   ├── time_tool.py           #   时区时间查询
│   │   └── shell_tool.py          #   安全 Shell 命令执行 🆕
│   └── core/                      # 基础设施
│       ├── llm_factory.py         #   LLM 工厂
│       ├── logger.py              #   loguru 日志系统
│       ├── exceptions.py          #   应用异常类层次
│       ├── message_trimmer.py     #   对话历史修剪
│       └── milvus_client.py       #   Milvus 连接管理
├── mcp_servers/                   # MCP 远程服务（5 个独立进程）
│   ├── time_server.py             #   时间服务（FastMCP, Port 8003）
│   ├── db_server.py               #   数据库服务（FastMCP, Port 8004）
│   ├── ppt_server.py              #   PPT 生成服务（FastMCP, Port 8005）
│   ├── ppt_builder.py             #   PPT 渲染引擎（python-pptx）
│   ├── docker_server.py           #   Docker 管理服务（FastMCP, Port 8006）🆕
│   └── search_server.py           #   Web 搜索服务（FastMCP, Port 8007）🆕
├── frontend/                      # 前端源码（Vue 3 SFC + Vite）
│   ├── src/                       #   应用源码
│   │   ├── pages/                 #     路由级页面（LoginPage / MainPage）
│   │   ├── components/            #     可复用组件（ChatPanel / Sidebar 等）
│   │   ├── utils/                 #     工具函数（api / auth / config）
│   │   └── router/                #     Vue Router 路由配置
│   ├── dist/                      #   构建产物（npm run build 生成）
│   ├── vite.config.js             #   Vite 配置（dev 代理 → FastAPI）
│   └── package.json               #   前端依赖与脚本
├── aiops-docs/                    # 上传文档存储目录
├── Dockerfile                     # Docker 镜像构建文件
├── docker-compose.yml             # Docker 全栈编排配置
├── vector-database.yml            # Milvus 独立部署配置
├── .env.example                   # 环境变量模板（可提交 Git）
├── .env                           # 环境变量（敏感信息，需自行创建）
├── .dockerignore                  # Docker 构建排除文件
├── pyproject.toml                 # 项目依赖和元数据
├── README.md                      # 本文件
└── DEPLOY.md                      # 部署指南
```

---

## API 文档

启动服务后，访问 **http://127.0.0.1:9900/docs** 查看 Swagger 交互式 API 文档。

### 接口一览

| 方法 | 路径 | 说明 | 流式 |
|------|------|------|:----:|
| `POST` | `/api/chat` | RAG Agent 对话 | ❌ |
| `POST` | `/api/chat_stream` | RAG Agent 对话（SSE） | ✅ |
| `POST` | `/api/agent/chat` | 手动 Agent 对话 | ❌ |
| `POST` | `/api/agent/chat_stream` | 手动 Agent 对话（SSE） | ✅ |
| `POST` | `/api/aiops` | AIOps 诊断（SSE） | ✅ |
| `POST` | `/api/mcp/chat` | MCP 混合工具对话 | ❌ |
| `POST` | `/api/mcp/chat_stream` | MCP 混合工具对话（SSE） | ✅ |
| `GET` | `/api/mcp/tools` | 列出所有工具 | — |
| `POST` | `/api/upload` | 上传文档到知识库 | — |
| `POST` | `/api/title/summarize` | 生成会话标题 | — |
| `GET` | `/health` | 健康检查 | — |

### MCP Server 端点

| 服务 | 端口 | MCP 端点 | 健康检查 |
|------|:----:|------|:----:|
| Time Server | 8003 | `/mcp` | `/health` |
| DB Server | 8004 | `/mcp` | `/health` |
| PPT Server | 8005 | `/mcp` | `/health` |
| Docker Server 🆕 | 8006 | `/mcp` | `/health` |
| Search Server 🆕 | 8007 | `/mcp` | `/health` |

### SSE 事件类型

#### 对话接口 (`chat_stream`)

```json
{"type": "content",     "data": "文本 Token"}
{"type": "tool_start",  "data": "工具名"}
{"type": "done"}
{"type": "error",       "data": "错误信息"}
```

#### 诊断接口 (`/api/aiops`)

```json
{"type": "plan",        "data": {"steps": ["步骤1", "步骤2", ...]}}
{"type": "step_start",  "data": "当前步骤描述"}
{"type": "step_result", "data": {"step": "步骤", "result": "结果"}}
{"type": "replan",      "data": {"new_plan": ["新步骤1", ...]}}
{"type": "report",      "data": "完整 Markdown 诊断报告"}
{"type": "done"}
{"type": "error",       "data": "错误信息"}
```

---

## 使用场景

### 场景一：知识库问答

```bash
# 1. 上传运维文档
curl -F "file=@cpu_troubleshooting.md" http://127.0.0.1:9900/api/upload

# 2. 提问
curl -X POST http://127.0.0.1:9900/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "CPU 使用率过高怎么排查？", "session_id": "ops-001"}'
```

### 场景二：AIOps 自动诊断

```bash
curl -X POST http://127.0.0.1:9900/api/aiops \
  -H "Content-Type: application/json" \
  -d '{"session_id": "diagnose-001"}'
# 返回 SSE 流：Plan → Step by Step → Replan → Report
```

### 场景三：MCP 混合工具调用

```bash
curl -X POST http://127.0.0.1:9900/api/mcp/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "现在几点？数据库中都有哪些表？顺便帮我查一下 CPU 过高怎么处理"}'
# Agent 自动判断：时间 → MCP Time Server，数据库 → MCP DB Server，知识库 → 本地工具
```

### 场景四：生成 PPT 报告

```bash
curl -X POST http://127.0.0.1:9900/api/mcp/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "根据数据库查询结果，生成一份 PPT 报告"}'
# Agent 调用 MCP PPT Server 自动创建演示文稿
```

### 场景五：系统诊断 🆕

```bash
curl -X POST http://127.0.0.1:9900/api/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "看看服务器内存使用情况，查一下最近有什么异常日志"}'
# Agent 自动调用 execute_shell 执行 free -h / journalctl 等诊断命令
```

### 场景六：Docker 运维 🆕

```bash
curl -X POST http://127.0.0.1:9900/api/mcp/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "有哪些容器在运行？nginx 容器最近有什么错误日志？"}'
# Agent 调用 list_containers → container_logs（nginx）
```

### 场景七：联网搜索 🆕

```bash
curl -X POST http://127.0.0.1:9900/api/mcp/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "最新的 Kubernetes 1.32 版本有哪些新特性？"}'
# Agent 调用 web_search 获取互联网上最新信息
```

---

## 技术栈

| 类别 | 技术 | 用途 |
|------|------|------|
| **Web 框架** | FastAPI + Uvicorn | HTTP API + SSE 流式响应 |
| **LLM** | 通义千问 (Qwen-Plus) via DashScope | 对话生成、计划制定、报告生成 |
| **Agent 框架** | LangChain + LangGraph | Agent 编排、状态图、工具调用 |
| **向量数据库** | Milvus 2.4 | 文档片段存储 + 语义检索 |
| **关系数据库** | MySQL 8.0 | DB MCP Server 数据源 |
| **Embedding** | text-embedding-v4 (DashScope) | 文本向量化 |
| **MCP 协议** | FastMCP + langchain-mcp-adapters | 远程工具服务（5 个 Server） |
| **PPT 生成** | python-pptx | PowerPoint 文件创建和渲染 |
| **Docker SDK** 🆕 | docker-py ≥ 7.0 | Docker 容器/镜像管理 |
| **Web 搜索** 🆕 | Tavily + DuckDuckGo | 互联网搜索（双后端自愈降级） |
| **前端** | Vite + Vue 3 SFC + Vue Router（marked.js + highlight.js） | SPA 交互界面，HMR 热更新 |
| **配置管理** | pydantic-settings | 类型安全的配置加载 |
| **日志** | loguru | 结构化日志 |
| **容器化** | Docker + Docker Compose | 一键部署、环境隔离 |

---

## 架构设计要点

本项目按模块构建，每个模块对应 LangChain/LangGraph 的一个核心概念：

| 模块 | 主题 | 关键文件 | 核心概念 |
|:----:|------|------|------|
| 1 | **项目骨架** | `main.py`, `config.py` | FastAPI 路由、pydantic-settings |
| 2 | **LLM 集成** | `llm_factory.py` | DashScope OpenAI 兼容接口、temperature |
| 3 | **向量数据库** | `milvus_client.py`, `vector_store_manager.py` | Milvus Schema、向量检索 |
| 4 | **RAG Agent** | `rag_agent_service.py` | `create_agent`、MemorySaver、工具注册 |
| 5 | **手动 Agent** | `manual_agent_service.py` | `StateGraph`、`ToolNode`、`bind_tools` |
| 6 | **AIOps 诊断** | `aiops_service.py`, `planner.py`, `executor.py`, `replanner.py` | Plan-Execute-Replan、`with_structured_output` |
| 7 | **MCP 协议** | `mcp_client.py`, `mcp_servers/` | FastMCP、MultiServerMCPClient、自愈设计 |
| 8 | **工具扩展** 🆕 | `shell_tool.py`, `docker_server.py`, `search_server.py` | 安全模型设计、MCP Server 开发模式、双后端降级 |

---

## 部署指南

- **Docker 全栈部署**：[DEPLOY.md](DEPLOY.md) — 推荐方式，包含服务编排、环境变量、故障排查
- **本地开发**：见 [快速开始 - 方式二](#方式二本地开发运行)
- **Windows 本地运行**：见 [方式二 - 本地开发运行](#方式二本地开发运行)，手动启动主应用与所需 MCP Server

---

## 常见问题

<details>
<summary><b>Q: 为什么 LLM 用 ChatOpenAI 而不是 ChatQwen？</b></summary>

DashScope 提供了 OpenAI 兼容接口，`ChatOpenAI` 可以直接对接。这样做的好处是切换模型供应商（如换成 DeepSeek、智谱、Ollama）时，只需改 `base_url` 和 `api_key`，不需要换代码中的类名。

> 详见 [app/core/llm_factory.py](app/core/llm_factory.py) 中的注释。
</details>

<details>
<summary><b>Q: RAG Agent 和 Manual Agent 有什么区别？</b></summary>

功能完全等价。区别在于实现方式：
- **RAG Agent** 用 LangChain 的 `create_agent` 一行代码搞定，适合快速开发
- **Manual Agent** 手动搭建 `StateGraph` + `ToolNode` + 条件边，代码透明，适合学习和深度定制

> 对比阅读 [app/services/rag_agent_service.py](app/services/rag_agent_service.py) 和 [app/services/manual_agent_service.py](app/services/manual_agent_service.py) 可以直观理解两者的差异。
</details>

<details>
<summary><b>Q: MCP Server 没启动会怎样？</b></summary>

不会影响主程序正常运行。MCP Agent 采用了**自愈设计**：连接 MCP Server 失败时返回空工具列表，Agent 自动降级为纯本地工具模式。用户感知不到错误，只是少了一个远程工具可用。

> 详见 [app/agent/mcp_client.py](app/agent/mcp_client.py) 的 `get_tools()` 方法。
</details>

<details>
<summary><b>Q: Docker 部署时数据库和 MCP 地址需要改吗？</b></summary>

不需要。`docker-compose.yml` 已通过 `environment` 自动覆盖 `127.0.0.1` 为容器名（`mysql`、`mcp-time` 等）。你只需在 `.env` 中填写 API Key 即可。
</details>

<details>
<summary><b>Q: 为什么 MemorySaver 用内存存储？</b></summary>

默认使用 `MemorySaver`（内存存储）以降低部署复杂度。**生产环境应替换为 `SqliteSaver` 或 `PostgresSaver`**，以保证服务重启后对话历史不丢失。

```python
# 生产环境示例
from langgraph.checkpoint.sqlite import SqliteSaver
memory = SqliteSaver.from_conn_string("checkpoints.db")
```
</details>

<details>
<summary><b>Q: 如何切换到其他 LLM？</b></summary>

只需修改 `.env` 中的配置：

```bash
# 示例：切换到 DeepSeek
LLM_MODEL=deepseek-chat
LLM_BASE_URL=https://api.deepseek.com/v1
DASHSCOPE_API_KEY=sk-your-deepseek-key
```

`ChatOpenAI` 兼容所有 OpenAI 接口规范的 API。
</details>

---



## License

MIT © [itwjf](https://github.com/itwjf)

---

<div align="center">

**⭐ 如果这个项目对你有帮助，欢迎 Star！**

[GitHub](https://github.com/itwjf/AIOperator) · [Gitee](https://gitee.com/itwjf/aioperator)

</div>
