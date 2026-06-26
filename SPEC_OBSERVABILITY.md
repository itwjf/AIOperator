# SPEC: Agent 可观测性系统

> **版本**: v4.0
> **创建日期**: 2026-06-26
> **状态**: 待开发
> **依赖**: 消息修剪、异常处理、日志系统、计算器工具 已完成
>
> **项目约束**: 技术栈、架构规范、编码风格、AI 禁止事项详见 `CLAUDE.md`。本 SPEC 仅定义可观测性功能本身的开发规格。

---

## 一、目标

集成 **LangFuse**（开源 MIT，Docker 自托管），让 AIOperator 的 Agent 行为从黑盒变白盒。

### 1.1 要达成的能力

| 编号 | 能力 | 优先级 | 一句话验收标准 |
|:----:|------|:------:|--------------|
| O1 | LLM 调用自动追踪 | **P0** | 调一次 `/api/chat`，Dashboard 出现一条 Trace，含 model、tokens、duration |
| O2 | Agent 全链路 Span | **P0** | 四种 Agent 模式的请求各有独立 Trace，metadata 含 `agent_mode` |
| O3 | Token / 成本统计 | **P0** | Dashboard 能按天查看 Token 用量和费用趋势 |
| O4 | 工具调用细粒度追踪 | P1 | 每个工具调用显示为独立 Span，含输入参数和耗时 |
| O5 | 优雅降级 | **P0** | `LANGFUSE_ENABLED=false` 或 LangFuse Server 未启动时，Agent 正常响应 |
| O6 | 质量评估反馈 | P2 | `/api/chat` 响应返回 `trace_id`，前端可提交 👍/👎 |

### 1.2 非目标

- 不替换 loguru（LangFuse 追踪 LLM 行为，loguru 记录应用日志，互不替代）
- 不上传数据到外部云端（数据存在自托管 Postgres 中）
- 不阻塞 Agent 响应（追踪数据异步上报）

---

## 二、架构

### 2.1 数据流

```
Agent 运行时                      LangFuse Server (Docker)
  llm.ainvoke() ──┐
  tool.ainvoke() ─┼── CallbackHandler ── HTTP POST (异步) ──→ Postgres → Web Dashboard :3000
  graph.astream()─┘
```

### 2.2 新增/改动文件

| 文件 | 动作 | Phase | 说明 |
|------|:----:|:-----:|------|
| `app/core/langfuse_client.py` | ✨ 新建 | P1 | 客户端单例，管理 `Langfuse` 和 `CallbackHandler` |
| `app/core/llm_factory.py` | ✏️ 改 | P1 | `create_llm()` 中注入 CallbackHandler |
| `app/config.py` | ✏️ 改 | P1 | 新增 4 个 langfuse 配置字段 |
| `.env` | ✏️ 改 | P1 | 新增 LANGFUSE_* 变量 |
| `pyproject.toml` | ✏️ 改 | P1 | 新增 `langfuse>=2.50.0` |
| `docker-compose.yml` | ✏️ 改 | P1 | 新增 `langfuse-server` + `langfuse-postgres` |
| `app/services/rag_agent_service.py` | ✏️ 改 | P2 | `query_stream()` 外层 Trace |
| `app/services/manual_agent_service.py` | ✏️ 改 | P2 | `chat_stream()` 外层 Trace |
| `app/services/mcp_agent_service.py` | ✏️ 改 | P2 | `chat_stream()` 外层 Trace |
| `app/services/aiops_service.py` | ✏️ 改 | P2 | `diagnose()` 外层 Trace + 各节点子 Span |
| `app/tools/knowledge_tool.py` | ✏️ 改 | P3 | 工具 Span |
| `app/tools/calculator_tool.py` | ✏️ 改 | P3 | 工具 Span |
| `app/agent/mcp_client.py` | ✏️ 改 | P3 | MCP 工具 Span |

### 2.3 Trace 标准结构

每个请求在 LangFuse 中的 Trace 必须包含：

```
📊 Trace
  ├── metadata: { agent_mode, session_id, streaming, environment, app_version }
  ├── input: 用户问题原文
  ├── output: { status: "completed" | "error", error?: "异常信息" }
  │
  ├── 🔷 Generation (LLM 调用 — CallbackHandler 自动捕获)
  │     model, usage{input,output}, duration, cost
  │
  ├── 🔶 Span (工具调用 — 手动创建)
  │     name, input, output(截断≤500字符), metadata{工具类型}, status
  │
  └── session_id: 关联同一会话的所有请求
```

---

## 三、Phase 1：LLM 自动追踪（P0）

### 3.1 `app/core/langfuse_client.py` — 客户端单例

参考现有 `app/agent/mcp_client.py` 的 `MCPClientManager` 单例模式实现。

**规格**：

- 类名 `LangfuseClientManager`，模块级 `__new__` 单例
- 属性 `enabled: bool` — 读取 `settings.langfuse_enabled and bool(settings.langfuse_public_key)`
- 方法 `get_client() -> Langfuse | None` — 返回 `Langfuse` 实例（用于手动 Span），失败返回 None
- 方法 `get_callback_handler() -> CallbackHandler | None` — 返回 `CallbackHandler` 实例（注入 LLM），失败返回 None
- 初始化失败不抛异常，记录 `logger.warning` 并返回 None
- 模块级函数 `get_langfuse_manager()` 返回单例

**降级约束**：`enabled` 为 False 或任一 get 方法返回 None 时，调用方必须静默跳过追踪逻辑。

### 3.2 `app/core/llm_factory.py` — 注入 CallbackHandler

在 `create_llm()` 中新增两行，注入到 `ChatOpenAI(callbacks=callbacks, ...)`。

**约束**：不修改 `create_llm()` 的函数签名。

### 3.3 配置变更

**`app/config.py`** 新增字段：

```python
langfuse_enabled: bool = True
langfuse_public_key: str = ""
langfuse_secret_key: str = ""
langfuse_host: str = "http://localhost:3000"
```

**`.env`** 新增 4 个 `LANGFUSE_*` 变量。**`pyproject.toml`** dependencies 新增 `"langfuse>=2.50.0"`。

### 3.4 Docker Compose

新增两个服务：`langfuse-postgres`（postgres:15-alpine，端口 5433）和 `langfuse-server`（langfuse/langfuse:latest，端口 3000），以及 volumes 中新增 `langfuse_db:`。

---

## 四、Phase 2：Agent 全链路 Span（P0）

### 4.1 改动范围

| 文件 | 方法 | Trace name | agent_mode |
|------|------|------------|------------|
| `app/services/rag_agent_service.py` | `query_stream()` | `rag_agent` | `chat` |
| `app/services/manual_agent_service.py` | `chat_stream()` | `manual_agent` | `agent` |
| `app/services/mcp_agent_service.py` | `chat_stream()` | `mcp_agent` | `mcp` |
| `app/services/aiops_service.py` | `diagnose()` | `aiops_diagnose` | `aiops` |

### 4.2 外层 Trace 规格

每个流式方法的改造模式：

1. 方法入口获取 `lf = get_langfuse_manager()`
2. `lf.enabled` 时创建 `client.trace(name=..., input=..., metadata={agent_mode, session_id, streaming, app_version, environment}, session_id=...)`
3. `yield {"type": "done"}` 前执行 `trace.update(output={"status": "completed"})`
4. 异常处理块中执行 `trace.update(output={"status": "error", "error": str(e)}, level="ERROR")`
5. `lf.enabled` 为 False 时跳过全部 trace 操作

### 4.3 AIOps 特殊要求

`diagnose()` 除顶层 Trace 外，需在 Planner、Executor、Replanner、Reporter 各节点产出事件时创建子 Span（name 分别为 `planner` / `executor` / `replanner` / `reporter`），用 `trace.span()` 创建。

---

## 五、Phase 3：工具调用细粒度追踪（P1）

### 5.1 本地工具

| 文件 | 函数 | Span name | metadata |
|------|------|-----------|----------|
| `app/tools/knowledge_tool.py` | `retrieve_knowledge` | `retrieve_knowledge` | `{tool_type: "local", source: "milvus"}` |
| `app/tools/calculator_tool.py` | `calculate` | `calculate` | `{tool_type: "local"}` |

每个 Span 记录 input、output（截断至 500 字符）。异常时标记 `level="ERROR"` 后 re-raise。

**约束**：不能在 `@tool` 函数签名中新增参数。

### 5.2 MCP 远程工具

在 `app/agent/mcp_client.py` 的 `MCPClientManager.call_tool()` 中创建 Span：name = `mcp:{tool_name}`，metadata 含 `{tool_type: "mcp", server_name}`。

---

## 六、Phase 4：评估与反馈（P2，可选）

- `/api/chat` 流式响应末尾返回 `trace_id`，前端收集 👍/👎
- 通过 `client.score()` 将反馈关联到对应 Trace

---

## 七、验收标准

### 7.1 Phase 1（必须全部通过才进入 Phase 2）

- [ ] `docker compose up -d langfuse-postgres langfuse-server` 后 `localhost:3000` 可访问
- [ ] Dashboard 中创建 Project，获取 Public Key 和 Secret Key
- [ ] `.env` 填入 Key 后，`curl -X POST http://127.0.0.1:9900/api/chat -d '{"question":"你好"}'`，Dashboard 出现 Trace
- [ ] Trace 中 LLM 调用字段完整：`model`、`usage.input`、`usage.output`、`duration`
- [ ] `LANGFUSE_ENABLED=false` 时 Agent 正常响应，不报错
- [ ] LangFuse 容器未启动时 Agent 正常响应，`logger.warning` 有警告

### 7.2 Phase 2

- [ ] 四种模式（`/api/chat`、`/api/agent/chat`、`/api/mcp/chat`、`/api/aiops/diagnose`）Dashboard 中各有一条 Trace
- [ ] 每条 Trace 的 metadata 含 `agent_mode`，Dashboard 可按此筛选
- [ ] AIOps Trace 详情页能看到 `planner` → `executor` → `replanner` → `reporter` 子 Span 层级
- [ ] 异常请求的 Trace 标记为 ERROR

### 7.3 Phase 3

- [ ] `retrieve_knowledge` 调用显示为独立 Span，含 input 和 output 摘要
- [ ] MCP 远程工具调用也有对应 Span
- [ ] MCP Server 不可用时工具 Span 标记为 ERROR

### 7.4 通用

- [ ] 所有新增 `.py` 文件有模块级 docstring，所有新增函数有 docstring
- [ ] 所有异常路径有 `logger.warning` 或 `logger.error`
- [ ] `pyproject.toml` 新增依赖 ≤1 个，Docker Compose 新增服务 ≤2 个
- [ ] 不修改现有函数签名
