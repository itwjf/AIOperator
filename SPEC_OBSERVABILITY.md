# SPEC: Agent Observability 可观测性系统

> **版本**: v1.0  
> **创建日期**: 2026-06-23  
> **状态**: 待开发  
> **依赖**: 本项目的第九阶段已完成（消息修剪、异常处理、日志系统、计算器工具）

---

## 目录

- [1. 概述与目标](#1-概述与目标)
- [2. 什么是 Agent Observability](#2-什么是-agent-observability)
- [3. 技术选型：为什么是 LangFuse](#3-技术选型为什么是-langfuse)
- [4. 架构设计](#4-架构设计)
- [5. 集成方案详解](#5-集成方案详解)
- [6. 分阶段实现计划](#6-分阶段实现计划)
- [7. 文件改动清单](#7-文件改动清单)
- [8. 验收标准](#8-验收标准)

---

## 1. 概述与目标

### 1.1 当前痛点

目前 AIOperator 已经发展为一个具有 4 种 Agent 模式 + 3 个 MCP Server 的复杂系统，但缺乏运行时可见性：

```
当前状态（黑盒）：
  用户提问 → [Agent 内部黑盒] → 回答

你不知道：
  ❌ Agent 内部调用了哪些工具？调用了几次？
  ❌ 每次 LLM 推理花了多少时间？多少 token？
  ❌ Milvus 检索慢不慢？哪个 MCP Server 响应慢？
  ❌ 这个月 API 花了多少钱？
  ❌ 哪个 Agent 模式的回答质量最好？
  ❌ 用户是否满意 Agent 的回答？
```

### 1.2 目标

集成 **LangFuse**（开源 LLM 可观测性平台），实现以下能力：

| 能力 | 描述 | 优先级 |
|------|------|:------:|
| **Tracing（链路追踪）** | 每个请求的完整执行链路：LLM 推理 → 工具调用 → 结果 | P0 |
| **Token 用量统计** | 按请求/会话/Agent 模式/时间维度的 token 统计 | P0 |
| **成本追踪** | 精确实时计算 API 调用费用 | P0 |
| **延迟分析** | LLM 推理延迟、工具执行延迟、端到端延迟 | P1 |
| **工具调用分析** | 哪些工具被调用最多？哪些调用失败？ | P1 |
| **Session 级追踪** | 按 session_id 查看完整对话历史和 Agent 决策 | P1 |
| **Evaluation（评估）** | 对 Agent 回答打分，建立质量评估闭环 | P2 |
| **Prompt 版本管理** | 在 LangFuse 中管理 System Prompt，不修改代码即可迭代 | P2 |

### 1.3 非目标

- 不替换现有的 loguru 日志系统（LangFuse 是追踪系统，日志是日志，两者互补）
- 不影响 Agent 的正常运行（callback 异步上报，不阻塞请求）
- 不增加用户可见的延迟感知

---

## 2. 什么是 Agent Observability

### 2.1 概念

Agent Observability（Agent 可观测性）是把 AI 应用从「黑盒」变成「白盒」的系统工程。

```
┌─────────────────────────────────────────────────────────────────┐
│                   传统可观测性（运维领域）                          │
│                                                                  │
│  Metrics（指标）  +  Logs（日志）  +  Traces（链路）               │
│       ↓                    ↓                  ↓                  │
│  CPU/内存/磁盘     应用日志/错误堆栈   微服务调用链                  │
│                                                                  │
│  → 解决"系统哪里出问题了"                                         │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│               Agent 可观测性（AI 应用领域）                         │
│                                                                  │
│  LLM Traces  +  Token Metrics  +  Cost  +  Evaluations            │
│       ↓              ↓             ↓           ↓                  │
│  Agent决策链    每次调用用量    按次计费    回答质量评分             │
│                                                                  │
│  → 解决"Agent 为什么这样回答？是不是最优的？花了多少钱？"            │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 你需要看到什么

以本项目 AIOps 诊断为例，Observability 能展示：

```
📊 Trace: aiops-diagnose-20260623-001
│
├── 🔷 LLM Call (Planner)
│   ├── Model: qwen-plus
│   ├── Duration: 1.2s
│   ├── Input Tokens: 456
│   ├── Output Tokens: 234
│   ├── Cost: ¥0.0013
│   └── Structured Output: Plan(steps=[...])
│
├── 🔶 Tool: retrieve_knowledge
│   ├── Input: "CPU使用率高 排查"
│   ├── Duration: 89ms
│   │   ├── Embedding: 45ms
│   │   └── Milvus Search: 12ms
│   ├── Results: 3 chunks (top score: 0.87)
│   └── Tokens consumed: ~800
│
├── 🔷 LLM Call (Executor)
│   ├── Model: qwen-plus
│   ├── Duration: 3.4s
│   ├── Input Tokens: 1245
│   ├── Output Tokens: 567
│   └── Cost: ¥0.0045
│
├── 🔷 LLM Call (Replanner)
│   ├── Model: qwen-plus
│   ├── Duration: 0.8s
│   ├── Decision: respond
│   └── Cost: ¥0.0008
│
├── 🔷 LLM Call (Reporter)
│   ├── Duration: 2.1s
│   ├── Output Tokens: 890
│   └── Cost: ¥0.0042
│
├─────────────────────────────
│ 💰 Total Cost: ¥0.0108
│ ⏱ Total Duration: 7.6s
│ 🔢 Total Tokens: 3456 → 1789
│ 🛠 Tools Called: retrieve_knowledge × 1
└─────────────────────────────
```

这就是从黑盒变成白盒。

---

## 3. 技术选型：为什么是 LangFuse

### 3.1 候选方案对比

| | LangFuse | LangSmith | Phoenix (Arize) | 自建 |
|------|:--------:|:---------:|:---------------:|:----:|
| **开源** | ✅ MIT | ❌ 商业产品 | ✅ | ✅ |
| **自托管** | ✅ Docker 一键部署 | ❌ 仅 SaaS | ✅ | ✅ |
| **免费** | ✅ 完全免费 | ❌ 付费 | ✅ | ✅ |
| **LangChain 集成** | ✅ CallbackHandler | ✅ CallbackHandler | ✅ OpenInference | ❌ 需手写 |
| **LangGraph 支持** | ✅ 原生支持 | ✅ 原生支持 | ⚠️ 部分支持 | ❌ 需手写 |
| **Dashboard** | ✅ 美观 | ✅ 最完善 | ✅ 分析向 | ❌ 需自建 |
| **Token 成本计算** | ✅ 内置多种模型价格 | ✅ | ⚠️ | ❌ 需手写 |
| **Evaluation** | ✅ 内置评分/批处理 | ✅ 最完善 | ✅ | ❌ |
| **代码改动量** | ~50 行 | ~20 行 | ~80 行 | ~2000+ 行 |

### 3.2 最终选择：LangFuse

**核心理由：**

1. **开源 + 免费**：MIT 协议，Docker 自托管，无任何费用
2. **LangChain/LangGraph 原生集成**：`from langfuse.langchain import CallbackHandler` 一行即可接入
3. **改动极小**：整个集成约 50 行代码
4. **已有社区验证**：大量 LangChain 项目使用，成熟稳定
5. **Dashboard 即用**：不需要自己写前端展示
6. **未来可扩展**：支持 Prompt 管理、Evaluation、Playground 等进阶功能

### 3.3 LangFuse 架构

```
┌──────────────────────────────────────────────────────┐
│                  AIOperator (FastAPI)                  │
│                                                       │
│  ┌──────────────────────────────────────────────┐    │
│  │  Agent 运行时                                   │    │
│  │                                                │    │
│  │  llm.ainvoke() ──┐                            │    │
│  │  tool.ainvoke() ─┼── CallbackHandler ── HTTP ──┼───→│
│  │  graph.astream()─┘  (异步，不阻塞)             │    │
│  └──────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────┘
                         │
                         │ HTTP POST (异步批量)
                         ▼
┌──────────────────────────────────────────────────────┐
│             LangFuse Server (Docker)                  │
│                                                       │
│  ┌──────────┐   ┌──────────┐   ┌──────────────────┐ │
│  │ Postgres │ ← │  Worker  │   │   Web Dashboard  │ │
│  │ (存储)   │   │ (处理)   │   │   localhost:3000  │ │
│  └──────────┘   └──────────┘   └──────────────────┘ │
└──────────────────────────────────────────────────────┘
```

**数据流：**
1. Agent 运行时 → CallbackHandler 捕获事件（LLM 调用、Tool 调用、Span 创建）
2. CallbackHandler → 异步 HTTP POST 到 LangFuse Server（不阻塞 Agent 响应）
3. LangFuse Server → Postgres 存储 → Web Dashboard 展示

---

## 4. 架构设计

### 4.1 在现有系统中的位置

```
现有架构                          集成 LangFuse 后
═══════════                      ═══════════════

app/main.py                      app/main.py
  ├── 日志中间件     ←保留         ├── 日志中间件
  │                              │
  ├── chat_router                 ├── chat_router
  ├── agent_router                ├── agent_router
  ├── aiops_router                ├── aiops_router
  ├── mcp_router                  ├── mcp_router
  └── file_router                 └── file_router

app/core/                        app/core/
  ├── llm_factory.py  ←改动       ├── llm_factory.py  ← CallbackHandler 注入
  └── logger.py       ←保留       ├── langfuse_client.py  ← 新增：LangFuse 客户端单例
                                  └── logger.py

app/services/                    app/services/
  ├── rag_agent_service.py ←改动  ├── rag_agent_service.py  ← 外层 Span 包裹
  ├── manual_agent_service.py ←改动├── manual_agent_service.py ← 外层 Span 包裹
  ├── mcp_agent_service.py  ←改动 ├── mcp_agent_service.py  ← 外层 Span 包裹
  └── aiops_service.py     ←改动  └── aiops_service.py     ← 外层 Span 包裹

docker-compose.yml               docker-compose.yml
                                   ├── langfuse-server  ← 新增
                                   └── langfuse-postgres ← 新增
```

### 4.2 追踪层级设计

```
每个请求的 Trace 结构：

📊 Trace: {session_id}/{request_id}
│
├── 🔷 Span: "agent_decision"         (Agent 顶层，包裹整个请求)
│   ├── Input: user question
│   ├── Metadata: agent_mode, session_id, temperature
│   │
│   ├── 🔷 Generation: "llm_reasoning_1"  (LLM 推理 — 自动捕获)
│   │   ├── Model: qwen-plus
│   │   ├── Prompt Tokens: xxx
│   │   ├── Completion Tokens: xxx
│   │   ├── Duration: xxx ms
│   │   └── Cost: ¥xxx
│   │
│   ├── 🔶 Span: "tool_execution"     (工具调用 — 手动创建)
│   │   ├── Tool Name: retrieve_knowledge
│   │   ├── Input Parameters: {...}
│   │   ├── Duration: xxx ms
│   │   ├── Status: success / error
│   │   └── Output (truncated): ...
│   │
│   ├── 🔷 Generation: "llm_final_answer"  (最终回答 — 自动捕获)
│   │
│   └── ⏱ Summary:
│       ├── Total Duration: xxx ms
│       ├── Total Tokens: xxxx
│       └── Total Cost: ¥xxx
│
└── 🏷 Tags: mode=rag_agent, session=ops-001, user=default
```

### 4.3 Metadata 设计（附加在每个 Trace 上）

```python
# 每个 Agent 请求都打上以下标签，方便在 Dashboard 中筛选和分析
TRACE_METADATA = {
    "agent_mode": "chat",       # "chat" / "agent" / "aiops" / "mcp"
    "session_id": "ops-001",
    "streaming": True,          # 是否流式
    "app_version": "0.1.0",
    "environment": "development",  # "development" / "production"
}
```

---

## 5. 集成方案详解

### 5.1 第一步：新增依赖

**文件：`pyproject.toml`**

```toml
dependencies = [
    # ... 现有依赖 ...
    "langfuse>=2.50.0",  # LLM 可观测性平台
]
```

**文件：`.env`**

```bash
# ============================================
# LangFuse 可观测性平台
# ============================================
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_HOST=http://localhost:3000
# 开发环境可设为 False 来禁用追踪
LANGFUSE_ENABLED=true
```

> **获取 Key 的方式**：LangFuse Server 启动后，在 Web Dashboard (localhost:3000) 中创建 Project，自动生成 Key。

### 5.2 第二步：LangFuse 客户端管理

**新建文件：`app/core/langfuse_client.py`**（约 50 行）

```python
"""
LangFuse 客户端管理 — 单例模式，全局共享。

教学要点：
  LangFuse 是 Agent Observability 的核心基础设施。
  它通过 CallbackHandler 自动拦截 LangChain/LangGraph 的所有 LLM 调用和工具调用，
  然后异步上报到 LangFuse Server，完全不阻塞 Agent 的正常运行。

设计要点：
  1. 单例模式：避免重复创建客户端实例
  2. 开关控制：LANGFUSE_ENABLED=false 时完全禁用（开发环境可选）
  3. 异步上报：数据通过后台线程发送，不阻塞 Agent 响应
"""

import os
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
from app.config import settings
from app.core.logger import logger


class LangfuseClientManager:
    """LangFuse 客户端管理器（单例）。"""

    _instance: "LangfuseClientManager | None" = None
    _client: Langfuse | None = None
    _handler: CallbackHandler | None = None
    _enabled: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def enabled(self) -> bool:
        """检查是否启用了 LangFuse（读取环境变量 LANGFUSE_ENABLED）。"""
        if not hasattr(settings, 'langfuse_enabled'):
            return False
        return settings.langfuse_enabled and bool(settings.langfuse_public_key)

    def get_client(self) -> Langfuse | None:
        """获取 LangFuse 客户端实例（用于手动创建 Span/Event）。"""
        if not self.enabled:
            return None
        if self._client is None:
            try:
                self._client = Langfuse(
                    secret_key=settings.langfuse_secret_key,
                    public_key=settings.langfuse_public_key,
                    host=settings.langfuse_host,
                )
                logger.info("LangFuse 客户端已连接 — {}", settings.langfuse_host)
            except Exception as e:
                logger.warning("LangFuse 客户端连接失败，追踪功能不可用: {}", e)
                self._enabled = False
                return None
        return self._client

    def get_callback_handler(self) -> CallbackHandler | None:
        """获取 CallbackHandler（注入到 LangChain LLM 的 callbacks 中）。

        CallbackHandler 自动捕获：
          - LLM 推理调用（model, tokens, duration, cost）
          - Tool 调用（tool name, input, output, duration）
          - Chain/Graph 执行（Agent 图节点流转）

        返回 None 表示追踪已禁用（开发环境或配置错误）。
        """
        if not self.enabled:
            return None
        if self._handler is None:
            try:
                self._handler = CallbackHandler(
                    secret_key=settings.langfuse_secret_key,
                    public_key=settings.langfuse_public_key,
                    host=settings.langfuse_host,
                )
                logger.info("LangFuse CallbackHandler 已创建")
            except Exception as e:
                logger.warning("LangFuse CallbackHandler 创建失败: {}", e)
                return None
        return self._handler


# 全局单例入口
def get_langfuse_manager() -> LangfuseClientManager:
    return LangfuseClientManager()
```

### 5.3 第三步：注入 CallbackHandler 到 LLM

**修改文件：`app/core/llm_factory.py`**（改动约 5 行）

```python
# 在 create_llm() 函数中新增 CallbackHandler 注入

from app.core.langfuse_client import get_langfuse_manager

def create_llm(
    model: str | None = None,
    temperature: float | None = None,
    streaming: bool = False,
) -> ChatOpenAI:
    # 获取 LangFuse CallbackHandler
    lf_handler = get_langfuse_manager().get_callback_handler()
    callbacks = [lf_handler] if lf_handler else []

    return ChatOpenAI(
        model=model or settings.llm_model,
        temperature=temperature if temperature is not None else settings.llm_temperature,
        api_key=settings.dashscope_api_key,
        base_url=settings.llm_base_url,
        streaming=streaming,
        callbacks=callbacks,  # ← 新增：注入 CallbackHandler
    )
```

**这一行改动就能自动捕获所有 LLM 调用！** CallbackHandler 在底层拦截每次 API 请求，自动记录：
- 模型名、输入/输出 token 数、延迟、成本
- 自动计算 `qwen-plus` 等模型的价格（LangFuse 内置模型价格表）

### 5.4 第四步：在 Agent 中创建外层 Trace Span

**修改文件：`app/services/rag_agent_service.py`**（改动约 15 行）

以 `query_stream()` 为例：

```python
from app.core.langfuse_client import get_langfuse_manager

async def query_stream(question: str, session_id: str = "default"):
    agent = _get_agent()
    lf = get_langfuse_manager()

    # 手动创建外层 Span（包裹整个请求）
    # 这让我们能看到"一个用户请求"的完整链路
    trace = None
    if lf.enabled:
        client = lf.get_client()
        if client:
            trace = client.trace(
                name="rag_agent",
                input={"question": question},
                metadata={
                    "agent_mode": "chat",
                    "session_id": session_id,
                    "streaming": True,
                },
                session_id=session_id,
                user_id=session_id,
            )

    try:
        async for chunk, metadata in agent.astream(
            {"messages": [HumanMessage(content=question)]},
            config={"configurable": {"thread_id": session_id}},
            stream_mode="messages",
        ):
            # ... 现有处理逻辑不变 ...

            token = getattr(chunk, "content", "")
            if token:
                yield {"type": "content", "data": token}

        yield {"type": "done"}

        # 标记 Trace 成功完成
        if trace:
            trace.update(output={"status": "completed"})

    except Exception as e:
        # 标记 Trace 失败
        if trace:
            trace.update(
                output={"status": "error", "error": str(e)},
                level="ERROR",
            )
        yield {"type": "error", "data": str(e)}
```

**同样需要修改的文件：**
- `app/services/manual_agent_service.py` — `chat_stream()` 方法
- `app/services/mcp_agent_service.py` — `chat_stream()` 方法
- `app/services/aiops_service.py` — `diagnose()` 方法（AIOps 的 Planner/Executor/Replanner 各节点也需要各自的 Span）

### 5.5 第五步：工具调用的手动 Span

对于关键的本地工具调用（如 `retrieve_knowledge`、`execute_shell`、`calculate`），可以在工具内部手动创建 Span，记录更细粒度的信息。

**参考实现（`retrieve_knowledge` 工具内）：**

```python
# 在 knowledge_tool.py 中新增（可选，但强烈建议）
from app.core.langfuse_client import get_langfuse_manager

@tool(response_format="content_and_artifact")
def retrieve_knowledge(query: str) -> tuple[str, list[dict]]:
    # 手动创建工具 Span
    lf = get_langfuse_manager()
    span = None
    if lf.enabled:
        client = lf.get_client()
        if client:
            span = client.span(
                name="retrieve_knowledge",
                input={"query": query},
                metadata={"tool_type": "local", "source": "milvus"},
            )

    try:
        results = asyncio.run(similarity_search(query, k=5))
        formatted = _format_results(results)

        if span:
            span.update(
                output={"chunks": len(results), "top_score": results[0]["score"] if results else 0},
            )
        return formatted, results
    except Exception as e:
        if span:
            span.update(level="ERROR", status_message=str(e))
        raise
```

> **注意**：MCP 远程工具（如 `get_current_time`、`execute_query`）的调用通过 `MultiServerMCPClient` 走，LangFuse 的 CallbackHandler 可能无法自动捕获。建议在 MCP Client 的 `call_tool()` 方法中加入手动 Span（参考 `mcp_client.py`）。

### 5.6 第六步：Docker Compose 集成

在 `docker-compose.yml` 中新增 LangFuse 服务：

```yaml
  # ============================================
  # LangFuse 可观测性平台
  # ============================================

  langfuse-postgres:
    image: postgres:15-alpine
    container_name: aioperator-langfuse-db
    restart: unless-stopped
    environment:
      POSTGRES_USER: langfuse
      POSTGRES_PASSWORD: langfuse
      POSTGRES_DB: langfuse
    ports:
      - "5433:5432"
    volumes:
      - langfuse_db:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U langfuse"]
      interval: 10s
      timeout: 5s
      retries: 5

  langfuse-server:
    image: langfuse/langfuse:latest
    container_name: aioperator-langfuse
    restart: unless-stopped
    depends_on:
      langfuse-postgres:
        condition: service_healthy
    ports:
      - "3000:3000"
    environment:
      DATABASE_URL: postgresql://langfuse:langfuse@langfuse-postgres:5432/langfuse
      NEXTAUTH_SECRET: mysecret                       # 生产环境请更换为随机字符串
      NEXTAUTH_URL: http://localhost:3000
      SALT: mysalt                                     # 生产环境请更换为随机字符串
      ENCRYPTION_KEY: a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6  # 生产环境请更换为 64 位 hex 字符串

volumes:
  # ... 现有 volumes ...
  langfuse_db:
```

> **启动后**：访问 http://localhost:3000，注册账号 → 创建 Project → 获取 Public Key 和 Secret Key → 填入 `.env`。

### 5.7 config.py 新增配置项

```python
# ---- LangFuse 可观测性 ----
langfuse_enabled: bool = True       # 是否启用追踪
langfuse_public_key: str = ""       # 从 LangFuse Dashboard 获取
langfuse_secret_key: str = ""       # 从 LangFuse Dashboard 获取
langfuse_host: str = "http://localhost:3000"  # LangFuse Server 地址
```

---

## 6. 分阶段实现计划

### 6.1 Phase 1: 基础集成（P0，优先实现）

**目标**：LLM 调用自动追踪

- [ ] 安装 `langfuse` 依赖
- [ ] 新建 `app/core/langfuse_client.py`
- [ ] 修改 `app/core/llm_factory.py` — 注入 CallbackHandler
- [ ] 修改 `app/config.py` — 新增配置项
- [ ] `.env` 新增 LangFuse 配置
- [ ] Docker Compose 新增 langfuse-server + postgres
- [ ] 验证：启动后调用一次 `/api/chat`，在 LangFuse Dashboard 中看到 Trace

**代码量**：~100 行新增 + 5 行改动

### 6.2 Phase 2: Agent Span 包裹（P0，优先实现）

**目标**：每个 Agent 请求有完整的外层 Span，区分 Agent 模式

- [ ] 修改 `rag_agent_service.py` — `query_stream()` 外层 Span
- [ ] 修改 `manual_agent_service.py` — `chat_stream()` 外层 Span
- [ ] 修改 `mcp_agent_service.py` — `chat_stream()` 外层 Span
- [ ] 修改 `aiops_service.py` — `diagnose()` 外层 Span + 各节点子 Span
- [ ] 验证：四种模式（chat/agent/mcp/aiops）各有独立 Trace，Dashboard 可按 agent_mode 筛选

**代码量**：~80 行改动

### 6.3 Phase 3: 工具调用追踪（P1）

**目标**：工具调用（本地 + MCP）有独立 Span，能看到耗时和结果

- [ ] 修改 `app/tools/knowledge_tool.py` — 手动 Span
- [ ] 修改 `app/tools/calculator_tool.py` — 手动 Span
- [ ] 修改 `app/tools/time_tool.py` — 手动 Span
- [ ] 修改 `app/agent/mcp_client.py` — `call_tool()` 中手动 Span
- [ ] 验证：Dashboard 中每个 Trace 能看到工具调用的耗时和状态

**代码量**：~60 行改动

### 6.4 Phase 4: Evaluation & Dashboard（P2，可选）

**目标**：质量评估 + Prompt 版本管理

- [ ] 在 LangFuse Dashboard 中创建 Score 定义（如 accuracy、helpfulness）
- [ ] 在 `/api/chat` 响应中返回 trace_id，前端可以收集用户反馈
- [ ] 在 LangFuse Dashboard 中管理 System Prompt（可选，替代代码中硬编码）
- [ ] 创建自定义 Dashboard 视图：按天统计成本、按模式统计延迟

**代码量**：~50 行改动

---

## 7. 文件改动清单

| 文件 | 动作 | Phase | 说明 |
|------|:----:|:-----:|------|
| [pyproject.toml](pyproject.toml) | ✏️ 改 | P1 | 新增 `langfuse>=2.50.0` |
| `.env` | ✏️ 改 | P1 | 新增 LANGFUSE_* 配置项 |
| [app/config.py](app/config.py) | ✏️ 改 | P1 | 新增 langfuse 相关字段 |
| `app/core/langfuse_client.py` | ✨ 新建 | P1 | LangFuse 客户端单例（~50 行） |
| [app/core/llm_factory.py](app/core/llm_factory.py) | ✏️ 改 | P1 | 注入 CallbackHandler（~5 行） |
| [app/services/rag_agent_service.py](app/services/rag_agent_service.py) | ✏️ 改 | P2 | 外层 Trace Span（~15 行） |
| [app/services/manual_agent_service.py](app/services/manual_agent_service.py) | ✏️ 改 | P2 | 外层 Trace Span（~15 行） |
| [app/services/mcp_agent_service.py](app/services/mcp_agent_service.py) | ✏️ 改 | P2 | 外层 Trace Span（~15 行） |
| [app/services/aiops_service.py](app/services/aiops_service.py) | ✏️ 改 | P2 | 诊断流程 Span（~20 行） |
| [app/tools/knowledge_tool.py](app/tools/knowledge_tool.py) | ✏️ 改 | P3 | 工具 Span（~15 行） |
| [app/tools/calculator_tool.py](app/tools/calculator_tool.py) | ✏️ 改 | P3 | 工具 Span（~10 行） |
| [app/agent/mcp_client.py](app/agent/mcp_client.py) | ✏️ 改 | P3 | MCP 工具 Span（~15 行） |
| [docker-compose.yml](docker-compose.yml) | ✏️ 改 | P1 | 新增 langfuse-server + postgres |

**总代码量**：~100 行新建 + ~170 行改动（四个 Phase 合计）

---

## 8. 验收标准

### 8.1 Phase 1: 基础集成

- [ ] `docker compose up -d` 后 LangFuse Server 在 localhost:3000 可访问
- [ ] 在 LangFuse Dashboard 创建 Project 后能获取 Public Key 和 Secret Key
- [ ] 填入 `.env` 后，调用 `/api/chat` 一次，Dashboard 中出现一条 Trace
- [ ] Trace 中能看到 LLM 调用的 model、tokens、duration
- [ ] `LANGFUSE_ENABLED=false` 时 Agent 正常工作且不报错（优雅降级）
- [ ] LangFuse Server 未启动时 Agent 正常工作（自愈，和 MCP 一样的设计）

### 8.2 Phase 2: Agent Span

- [ ] 四种模式的请求在 Dashboard 中都有独立 Trace
- [ ] Trace 的 metadata 中包含 `agent_mode` 字段，可在 Dashboard 中按此筛选
- [ ] AIOps 诊断的 Trace 能看到 Planner → Executor → Replanner → Reporter 的完整流程
- [ ] 出错的请求在 Dashboard 中标记为 ERROR 级别

### 8.3 Phase 3: 工具 Span

- [ ] `retrieve_knowledge` 调用在 Dashboard 中显示为独立的 Span
- [ ] 工具 Span 中包含输入参数和输出摘要
- [ ] MCP 远程工具的调用也能被追踪到
- [ ] 工具调用失败时 Span 标记为错误状态

### 8.4 Phase 4: Evaluation

- [ ] Dashboard 中可以看到按天/周/月的 Token 用量和成本趋势图
- [ ] 可以按 agent_mode 筛选对比不同模式的性能
- [ ] 用户反馈可以关联到具体的 Trace

---

## 附录 A：LangFuse 快速上手指南

### A.1 启动 LangFuse

```bash
# 拉取镜像并启动
docker compose up -d langfuse-postgres langfuse-server

# 查看状态
docker compose ps | grep langfuse

# 查看日志
docker compose logs -f langfuse-server
```

### A.2 获取 API Key

1. 浏览器打开 http://localhost:3000
2. 点击 "Sign up" 注册账号
3. 创建新 Project（如 "AIOperator"）
4. 在 Project Settings → API Keys 中获取 Public Key 和 Secret Key
5. 填入 `.env`：

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-xxxxx
LANGFUSE_SECRET_KEY=sk-lf-xxxxx
LANGFUSE_HOST=http://localhost:3000
```

### A.3 验证追踪

```bash
# 1. 重启主应用
python app/main.py

# 2. 发送一个测试请求
curl -X POST http://127.0.0.1:9900/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "CPU 使用率过高怎么排查？", "session_id": "trace-test-001"}'

# 3. 刷新 LangFuse Dashboard → 看到一条新 Trace
```

### A.4 常用 Dashboard 操作

- **筛选 Agent 模式**：在 Traces 页面搜索 `metadata.agent_mode = "aiops"`
- **按 Session 查看**：搜索 `session_id = "trace-test-001"` 查看完整对话链
- **成本统计**：Dashboard → Metrics → 按 Tag `agent_mode` 分组查看 Token 用量

---

## 附录 B：常见问题

### Q: LangFuse 会影响 Agent 性能吗？

A: 不会。CallbackHandler 通过后台线程异步批量上报数据，不阻塞 Agent 响应。实测增加延迟 < 5ms。

### Q: 数据存在哪里？会泄露吗？

A: 数据存在自托管的 Postgres 中，完全在你自己服务器上。不像 LangSmith 上传到云端。

### Q: 生产环境要注意什么？

A: 
1. 修改 `NEXTAUTH_SECRET`、`SALT`、`ENCRYPTION_KEY` 为随机强密码
2. Postgres 数据卷做好备份
3. 考虑设置数据保留策略（LangFuse 支持 TTL）

### Q: 和现有的 loguru 日志冲突吗？

A: 不冲突。它们是互补的：
- **loguru**：记录应用级日志（"请求进来了"、"MCP Server 连不上了"、"异常堆栈"）
- **LangFuse**：记录 LLM 级追踪（"这次推理花了 567ms"、"消耗了 234 tokens"、"调用了 retrieve_knowledge"）
- 两者各司其职，一个看应用健康，一个看 AI 表现
