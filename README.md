# 🤖 AIOperator — 智能运维助手

<div align="center">

**从零复刻的 LangChain Agent 学习项目 | AIOps 智能诊断 | MCP 协议集成**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![LangChain](https://img.shields.io/badge/LangChain-0.3+-green.svg)](https://www.langchain.com/)
[![Milvus](https://img.shields.io/badge/Milvus-2.4+-orange.svg)](https://milvus.io/)
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
- [学习路线](#学习路线)
- [常见问题](#常见问题)
- [License](#license)

---

## 项目简介

**AIOperator** 是一个从零复刻的 **LangChain Agent** 学习项目，定位为 **智能运维助手**。它完整实现了 RAG 检索增强生成、Agent 工具调用、Plan-Execute-Replan 诊断工作流、以及 MCP（Model Context Protocol）远程工具集成。

项目的核心理念是 **"理解底层，不依赖黑盒"**—— 不仅使用 LangChain 的高级封装 `create_agent`，还手动用 `StateGraph` + `ToolNode` + `bind_tools` 搭建了完全等价的 Agent 图，让开发者深入理解 Agent 的运作机制。

> 🎯 **适用场景**: 运维故障诊断、知识库问答、Agent 工作流学习、MCP 协议实践

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
| **Manual Agent** | `StateGraph` + `ToolNode`（手动搭建） | `/api/agent/chat` | 学习原理，深度定制 |

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

### 🔌 MCP 混合工具
- **本地工具**: 知识库检索（`retrieve_knowledge`）
- **远程工具**: 时间服务（`get_current_time`，通过 MCP 协议暴露）
- **自愈设计**: MCP Server 不可用时，Agent 自动降级为纯本地工具模式
- **工具透明**: Agent 不关心工具来自本地还是远程 —— MCP 协议的核心价值

### 🌊 SSE 流式响应
所有对话接口均支持 SSE（Server-Sent Events）流式输出：
- 实时推送 AI 生成的文本 Token
- 展示工具调用状态（`tool_start` 事件）
- Plan-Execute-Replan 各阶段进度可视化

### 🖥 Vue 3 交互式前端
- 四种模式一键切换：对话 / Agent / 诊断 / MCP
- 诊断计划实时展示，步骤进度可视化
- 会话管理：创建、切换、删除会话
- 文件上传：支持拖拽或选择 Markdown/TXT 文件
- Markdown 渲染 + 代码高亮

---

## 架构概览

```
┌─────────────────────────────────────────────────────┐
│                    前端 (Vue 3)                       │
│  static/index.html + app.js + styles.css             │
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
│  │  Milvus │ DashScope(LLM) │ Embedding Service    │  │
│  └─────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘

┌──────────────────────┐
│    MCP Server (独立)  │
│  mcp_servers/        │
│  time_server.py      │
│  (FastMCP, Port 8003)│
└──────────────────────┘
```

---

## 快速开始

### 环境要求

| 依赖 | 版本 | 说明 |
|------|------|------|
| Python | ≥ 3.11 | 运行环境 |
| Milvus | ≥ 2.4 | 向量数据库（需单独安装） |
| DashScope API Key | — | 阿里云百炼平台（LLM + Embedding） |

### 1. 克隆项目

```bash
git clone https://github.com/itwjf/AIOperator.git
cd AIOperator
```

### 2. 安装依赖

```bash
# 推荐使用虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

pip install -e .
```

### 3. 配置环境变量

复制 `.env` 文件，填入你的 API Key：

```bash
# .env
DASHSCOPE_API_KEY=sk-your-api-key-here
LLM_MODEL=qwen-plus
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

MILVUS_HOST=127.0.0.1
MILVUS_PORT=19530
MILVUS_COLLECTION_NAME=aiops_knowledge
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIMENSION=1024
```

> 💡 **获取 API Key**: 前往 [阿里云百炼平台](https://bailian.console.aliyun.com/) 开通 DashScope 服务。

### 4. 启动 Milvus

```bash
# 使用 Docker 快速启动（需要先安装 Docker Desktop）
docker-compose -f vector-database.yml up -d
```

### 5. 启动 MCP 时间服务（可选）

```bash
# 新开一个终端
python mcp_servers/time_server.py
# → MCP Server 运行在 http://127.0.0.1:8003/mcp
```

> 💡 即使不启动 MCP Server，Agent 也能正常使用本地工具，自动降级运行。

### 6. 启动应用

```bash
python app/main.py
# 或者
uvicorn app.main:app --host 127.0.0.1 --port 9900 --reload
```

浏览器打开 **http://127.0.0.1:9900** 即可访问前端页面。

### 7. 上传知识库文档

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
│   ├── api/                       # API 路由层（"接客"）
│   │   ├── chat.py                #   /api/chat, /api/chat_stream
│   │   ├── agent.py               #   /api/agent/chat, /api/agent/chat_stream
│   │   ├── aiops.py               #   /api/aiops (诊断接口)
│   │   ├── mcp.py                 #   /api/mcp/chat, /api/mcp/tools
│   │   └── file.py                #   /api/upload (文件上传)
│   ├── services/                  # 业务逻辑层（"做事"）
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
│   ├── tools/                     # Agent 工具
│   │   ├── knowledge_tool.py      #   知识库检索工具
│   │   └── time_tool.py           #   时间查询工具
│   └── core/                      # 基础设施
│       ├── llm_factory.py         #   LLM 工厂
│       └── milvus_client.py       #   Milvus 连接管理
├── mcp_servers/                   # MCP 远程服务
│   └── time_server.py             #   时间服务（FastMCP）
├── aiops-docs/                    # 上传文档存储目录
├── static/                        # 前端静态文件
│   ├── index.html                 #   Vue 3 单页应用
│   ├── app.js                     #   应用逻辑
│   └── styles.css                 #   样式
├── .env                           # 环境变量（需自行创建）
├── pyproject.toml                 # 项目依赖
├── vector-database.yml            # Milvus Docker Compose
└── README.md                      # 本文件
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
| `GET` | `/health` | 健康检查 | — |

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
  -d '{"question": "现在几点？顺便帮我查一下 Redis 内存满的处理方案"}'
# Agent 自动判断：时间 → MCP 远程工具，知识库 → 本地工具
```

---

## 技术栈

| 类别 | 技术 | 用途 |
|------|------|------|
| **Web 框架** | FastAPI + Uvicorn | HTTP API + SSE 流式响应 |
| **LLM** | 通义千问 (Qwen-Plus) via DashScope | 对话生成、计划制定、报告生成 |
| **Agent 框架** | LangChain + LangGraph | Agent 编排、状态图、工具调用 |
| **向量数据库** | Milvus | 文档片段存储 + 语义检索 |
| **Embedding** | text-embedding-v4 (DashScope) | 文本向量化 |
| **MCP 协议** | FastMCP + langchain-mcp-adapters | 远程工具服务 + 客户端适配 |
| **前端** | Vue 3 (CDN) + marked.js + highlight.js | SPA 交互界面 |
| **配置管理** | pydantic-settings | 类型安全的配置加载 |
| **日志** | loguru | 结构化日志 |

---

## 学习路线

本项目按阶段构建，每个阶段对应 LangChain/LangGraph 的一个核心概念：

| 阶段 | 主题 | 关键文件 | 核心概念 |
|:----:|------|------|------|
| 1 | **项目骨架** | `main.py`, `config.py` | FastAPI 路由、pydantic-settings |
| 2 | **LLM 集成** | `llm_factory.py` | DashScope OpenAI 兼容接口、temperature |
| 3 | **向量数据库** | `milvus_client.py`, `vector_store_manager.py` | Milvus Schema、向量检索 |
| 4 | **RAG Agent** | `rag_agent_service.py` | `create_agent`、MemorySaver、工具注册 |
| 5 | **手动 Agent** | `manual_agent_service.py` | `StateGraph`、`ToolNode`、`bind_tools` |
| 6 | **AIOps 诊断** | `aiops_service.py`, `planner.py`, `executor.py`, `replanner.py` | Plan-Execute-Replan、`with_structured_output` |
| 7 | **MCP 协议** | `mcp_client.py`, `time_server.py` | FastMCP、MultiServerMCPClient、自愈设计 |

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
<summary><b>Q: 为什么 MemorySaver 用内存存储？</b></summary>

学习阶段使用 `MemorySaver`（内存存储）是为了降低复杂度。**生产环境应替换为 `SqliteSaver` 或 `PostgresSaver`**，以保证服务重启后对话历史不丢失。

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
