# SPEC: AI 开发规范 — AIOperator 项目编码标准

> **版本**: v1.0  
> **创建日期**: 2026-06-24  
> **状态**: 生效中  
> **适用范围**: 本项目所有 Python 代码、配置文件、Docker 编排、文档

---

## 目录

- [1. 项目身份与哲学](#1-项目身份与哲学)
- [2. 技术栈约束](#2-技术栈约束)
- [3. 文件与目录规范](#3-文件与目录规范)
- [4. 命名规范](#4-命名规范)
- [5. 类型注解规范](#5-类型注解规范)
- [6. 文档字符串规范](#6-文档字符串规范)
- [7. 架构分层规范](#7-架构分层规范)
- [8. 服务层规范](#8-服务层规范)
- [9. Agent 开发规范](#9-agent-开发规范)
- [10. 工具开发规范](#10-工具开发规范)
- [11. API 路由规范](#11-api-路由规范)
- [12. 异常处理规范](#12-异常处理规范)
- [13. 日志规范](#13-日志规范)
- [14. 配置管理规范](#14-配置管理规范)
- [15. 异步与流式规范](#15-异步与流式规范)
- [16. 单例模式规范](#16-单例模式规范)
- [17. 安全规范](#17-安全规范)
- [18. 依赖管理规范](#18-依赖管理规范)
- [19. Docker 与部署规范](#19-docker-与部署规范)
- [20. SPEC 文档编写规范](#20-spec-文档编写规范)
- [附录 A：代码模板](#附录-a代码模板)

---

## 1. 项目身份与哲学

### 1.1 项目定位

AIOperator 是一个**教育性 + 生产可用**的 LangChain Agent 项目。它的核心理念是 **"理解底层，不依赖黑盒"**。

### 1.2 三条开发铁律

所有 AI 生成的代码必须遵守以下三条：

| # | 铁律 | 含义 |
|:--:|------|------|
| **1** | **可读性优先于简洁性** | 禁止炫技式一行流。代码是给人读的，尤其是给学习者读的。每个关键决策必须附注释解释"为什么"。 |
| **2** | **中文注释 + 英文代码** | 变量名、函数名、类名：英文。注释、文档字符串、日志消息：中文。技术术语保留英文（如 `Token`、`Embedding`、`Chunk`）。 |
| **3** | **自愈降级，不崩溃** | 外部依赖不可用时，返回友好错误信息，绝不 crash。MCP Server 挂了 → 告诉用户 "xx 功能不可用"，不影响主流程。 |

### 1.3 禁止事项

- ❌ 删除或替换现有代码风格，必须匹配上下文
- ❌ 引入与现有技术栈重复的依赖（如项目已用 `loguru`，不允许再引入 `logging` 模块的复杂配置）
- ❌ 硬编码敏感信息（API Key、密码、连接字符串）
- ❌ 跳过类型注解（新代码必须全部有注解）
- ❌ 直接 `print()` 调试（用 `logger.debug()`）
- ❌ 在生产代码中保留 `TODO` 注释而不关联 Issue

---

## 2. 技术栈约束

### 2.1 语言与运行时

| 项 | 约束 |
|------|------|
| **Python 版本** | `>=3.11`（可用 `list[X]`、`str \| None`、`tomllib`） |
| **包管理器** | `pip`（非 Poetry/uv，pyproject.toml 仅用于依赖声明） |
| **虚拟环境** | 建议但非强制（Python 3.11+ 全局安装，或者 venv） |

### 2.2 核心依赖（不可替换）

| 包 | 版本 | 用途 | 是否可替换 |
|------|------|------|:--:|
| `fastapi` | >=0.115.0 | Web 框架 | ❌ |
| `uvicorn[standard]` | >=0.32.0 | ASGI 服务器 | ❌ |
| `langchain` | >=0.3.0 | Agent 框架 | ❌ |
| `langchain-openai` | >=0.2.0 | LLM 客户端（走 OpenAI 兼容接口） | ❌ |
| `langgraph` | 随 langchain 安装 | 图编排 | ❌ |
| `pydantic-settings` | >=2.6.0 | 配置管理 | ❌ |
| `loguru` | >=0.7.0 | 日志系统 | ❌ |
| `pymilvus` | >=2.4.0 | 向量数据库 | ⚠️ 可替换为其他向量库 |
| `fastmcp` | >=3.0.0 | MCP Server 框架 | ❌ |
| `langchain-mcp-adapters` | >=0.2.0 | MCP Client 集成 | ❌ |
| `sse-starlette` | >=2.0.0 | SSE 流式响应 | ❌ |
| `pymysql` | >=1.1.0 | MySQL 客户端 | ⚠️ 可按需替换 |
| `python-pptx` | >=1.0.0 | PPT 生成 | ⚠️ 可按需替换 |
| `langfuse` | >=2.50.0 | Agent 可观测性 | ❌（Phase 10 引入） |

### 2.3 隐式依赖（不需要在 pyproject.toml 中声明，但代码依赖）

以下包由上述核心依赖自动安装，代码中可以直接 `import`：

- `langgraph` — `StateGraph`、`ToolNode`、`MemorySaver`
- `langchain_core` — `BaseMessage`、`HumanMessage`、`SystemMessage`、`ToolMessage`、`tool`、`BaseModel`
- `pydantic` — `BaseModel`、`Field`
- `openai` — `AsyncOpenAI`（直接用于 Embedding API 调用）

---

## 3. 文件与目录规范

### 3.1 目录结构

```
AIOperator/
├── app/                        # 主应用
│   ├── __init__.py             # 包标识 + 简短描述
│   ├── main.py                 # FastAPI 入口（创建 app、注册路由、启动）
│   ├── config.py               # pydantic-settings 全局配置
│   ├── core/                   # 基础设施层（无业务逻辑）
│   │   ├── __init__.py
│   │   ├── exceptions.py       # 自定义异常层次
│   │   ├── llm_factory.py      # LLM 实例工厂
│   │   ├── logger.py           # loguru 初始化
│   │   ├── message_trimmer.py  # 对话消息修剪
│   │   └── milvus_client.py    # Milvus 连接管理
│   ├── services/               # 服务层（Agent 编排 + 业务逻辑）
│   │   ├── __init__.py
│   │   ├── rag_agent_service.py
│   │   ├── manual_agent_service.py
│   │   ├── mcp_agent_service.py
│   │   ├── aiops_service.py
│   │   ├── document_splitter.py
│   │   ├── embedding_service.py
│   │   └── vector_store_manager.py
│   ├── agent/                  # Agent 工作流（图节点、状态定义）
│   │   ├── __init__.py
│   │   ├── mcp_client.py       # MCP 客户端管理器
│   │   └── aiops/              # 子包示例：AIOps 诊断工作流
│   │       ├── __init__.py
│   │       ├── state.py        # 图状态 TypedDict
│   │       ├── planner.py      # 规划器节点
│   │       ├── executor.py     # 执行器节点
│   │       └── replanner.py    # 重规划器节点
│   ├── tools/                  # 本地工具（@tool 装饰器）
│   │   ├── __init__.py
│   │   ├── knowledge_tool.py
│   │   ├── time_tool.py
│   │   └── calculator_tool.py
│   └── api/                    # API 路由（只做请求/响应转换）
│       ├── __init__.py
│       ├── chat.py
│       ├── agent.py
│       ├── aiops.py
│       ├── mcp.py
│       ├── file.py
│       └── title.py
├── mcp_servers/                # MCP Server 独立进程
│   ├── time_server.py
│   ├── db_server.py
│   ├── ppt_server.py
│   └── ppt_builder.py
├── static/                     # 前端静态文件
├── aiops-docs/                 # 知识库源文档
├── logs/                       # 日志输出目录（gitignore）
├── output/                     # PPT 等输出文件（gitignore）
├── pyproject.toml              # 项目元数据
├── docker-compose.yml          # Docker 服务编排
├── Dockerfile                  # 应用镜像
├── .env                        # 环境变量（gitignore）
├── .env.example                # 环境变量模板（如存在）
├── README.md                   # 项目说明
├── DEPLOY.md                   # 部署指南
└── SPEC_*.md                   # 开发规范 / 功能规格文档
```

### 3.2 文件命名

| 类型 | 命名规则 | 示例 |
|------|---------|------|
| Python 模块 | `snake_case` | `message_trimmer.py`, `vector_store_manager.py` |
| 子包目录 | `snake_case` | `aiops/`, `mcp_servers/` |
| `__init__.py` | 永远只写一行注释，不导出符号 | `# 核心组件包` |
| SPEC 文档 | `SPEC_中文描述.md` | `SPEC_AI_开发规范.md` |
| 知识库文档 | `snake_case.md` | `cpu_troubleshooting.md` |

### 3.3 文件组织原则

1. **一个文件只做一件事**：不要在一个文件中混合 API 路由 + 业务逻辑 + 工具定义
2. **代码量和教学价值的边界**：文件超过 300 行时考虑拆分，但不要为了拆分而拆分成碎片文件
3. **`__init__.py` 不导出符号**：所有 import 走完整路径（`from app.core.llm_factory import create_llm`），不在 `__init__.py` 中做 `from .foo import *`
4. **新增模块放在正确的层级**：
   - 基础设施（LLM、DB、日志、异常）→ `app/core/`
   - 本地工具（`@tool` 函数）→ `app/tools/`
   - Agent 编排逻辑 → `app/services/`
   - API 路由 → `app/api/`
   - MCP Server 进程 → `mcp_servers/`
   - Agent 图节点/状态 → `app/agent/`（复杂的工作流可以像 `aiops/` 一样建子包）

---

## 4. 命名规范

### 4.1 命名速查表

| 元素 | 风格 | 示例 | 说明 |
|------|------|------|------|
| **模块名** | `snake_case` | `llm_factory.py` | 全小写，下划线分隔 |
| **包名** | `snake_case` | `mcp_servers/` | 同上 |
| **类名** | `PascalCase` | `PlanExecuteState`, `MCPClientManager` | 每个单词首字母大写 |
| **异常类名** | `PascalCase` + `Error` 后缀 | `LLMServiceError`, `VectorDBError` | 继承 `AIOperatorException` |
| **函数/方法** | `snake_case` | `trim_conversation_history`, `ensure_collection` | 动词开头 |
| **私有函数** | `_` 前缀 + `snake_case` | `_build_graph()`, `_get_memory()` | 模块内部使用 |
| **变量** | `snake_case` | `similar_cases_text`, `total_chunks` | 描述性强 |
| **常量（模块级）** | `UPPER_SNAKE` | `TOOLS`, `SYSTEM_PROMPT`, `MAX_RETRIES` | 全大写，下划线分隔 |
| **Pydantic 模型** | `PascalCase` | `ChatRequest`, `AIOpsRequest` | 类风格 |
| **API 路由函数** | `snake_case` | `agent_chat`, `mcp_chat_stream` | 动词/名词 |
| **Router 变量** | `router` | `router = APIRouter(...)` | 统一用 `router` |

### 4.2 命名细则

**函数命名**：
```python
# ✅ 好的命名：动词开头，说清楚做什么
def create_llm(streaming: bool = False) -> ChatOpenAI: ...
def trim_conversation_history(messages: list[BaseMessage], ...) -> list[BaseMessage]: ...
def run_planner(state: PlanExecuteState) -> dict: ...

# ❌ 不好的命名：模糊、缩写、无动词
def llm(): ...
def trim(): ...         # trim 什么？
def proc(s): ...        # 看不懂
```

**布尔变量命名**：
```python
# ✅ 用 is_/has_/should_/can_ 前缀
is_connected: bool
has_tool_calls: bool
should_continue: bool
can_restart: bool

# ❌ 不用这种（歧义）
connected: bool      # 是过去式还是过去时？
tool_calls: bool     # 是属性还是集合？
```

**常量命名**：
```python
# ✅ 模块级常量，清晰表达含义
MAX_CHAT_MESSAGES: int = 20
ALLOWED_COMMANDS: set[str] = {"ps", "top", "df"}
DEFAULT_SESSION_ID: str = "default"

# ❌ 魔法数字/字符串散落在代码中
if remaining_steps >= 5:  # 5 是什么？应该用 MAX_STEPS
```

---

## 5. 类型注解规范

### 5.1 强制要求

**所有新代码必须有类型注解**。包括：

- ✅ 所有公共函数的参数类型和返回值类型
- ✅ 所有类属性的类型声明
- ✅ TypedDict 的所有字段
- ✅ 模块级变量的类型声明
- ⚠️ 局部变量可以靠类型推断（但鼓励显式注解）

### 5.2 语法选择

使用 Python 3.11+ 的原生语法：

```python
# ✅ Python 3.11+ 原生语法（本项目首选）
def create_llm(
    model: str | None = None,
    temperature: float | None = None,
    streaming: bool = False,
) -> ChatOpenAI: ...

# ✅ 复杂泛型
from typing import Annotated, TypedDict, Literal

class PlanExecuteState(TypedDict):
    input: str
    plan: list[str]
    response: str
    action: Literal["continue", "replan", "respond"]

# ⚠️ 向后兼容时可用 Optional（代码中已有大量用法，保持一致性）
from typing import Optional
dashscope_api_key: Optional[str] = None

# ❌ 不要用小写的 typing 别名（已废弃）
from typing import List, Dict, Tuple  # 不要这样，用 list, dict, tuple
```

### 5.3 可为空类型

```python
# ✅ 明确标注 Optional / None
def get_client() -> MilvusClient | None: ...

# ✅ Pydantic 字段：用 Optional 表示非必填
dashscope_api_key: Optional[str] = None
```

### 5.4 Annotated 的使用

在 LangGraph 状态中使用 `Annotated` 定义 reducer：

```python
from typing import Annotated
import operator

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], operator.add]  # add = 追加而非覆盖
    steps: Annotated[list[str], lambda x, y: x + y]       # 自定义 reducer
```

---

## 6. 文档字符串规范

### 6.1 语言

- **中文描述** + **英文技术术语**
- 提示词（`SYSTEM_PROMPT`、`@tool` 的 docstring）例外：可以使用英文（LLM 对英文指令响应更好），但本项目目前用中文也足够

### 6.2 格式

采用 **类 Google 风格**（参数用 `Args:` / `Returns:`），但宽松处理：

```python
def function_name(
    param1: str,
    param2: int = 0,
) -> ReturnType:
    """一句话概述功能。

    详细描述（可选）：
      - 第一点
      - 第二点
      每行不超过 120 字符。

    Args:
        param1: 参数说明（中文冒号）
        param2: 参数说明，标注默认值含义

    Returns:
        返回值的描述

    Raises:
        SomeError: 什么情况下抛这个异常
    """
```

### 6.3 模块级文档字符串

每个 `.py` 文件必须以模块级文档字符串开头：

```python
"""
模块一句话说明 — 这个模块在整个系统中扮演什么角色。

关键设计决策（可选）：
  - 为什么这样设计
  - 有哪些权衡

使用方式：
  from app.xxx import yyy
"""
```

### 6.4 @tool 的 docstring

这是**特殊的**——LLM 读它来决定何时调用工具，所以必须：

1. 第一行：一句话说明工具干什么
2. `使用场景：` — 列出何时调用（越具体越好，LLM 靠这个做决策）
3. `安全限制：`（如适用）— 让 LLM 知道边界
4. `参数：` — 每个参数的含义和约束
5. `返回：` — 返回内容的格式

```python
@tool
def execute_shell(command: str) -> str:
    """安全地执行操作系统诊断命令（只读操作）。

    使用场景：
      - 用户问「CPU 使用率多少」「内存还剩多少」→ top, free
      - 用户问「磁盘满了没」→ df -h
      - 用户问「网络通不通」→ ping -c 3 8.8.8.8

    安全限制：
      - 仅允许执行白名单内的命令（诊断/查看类）
      - 命令执行超时 30 秒
      - 输出超过 5000 字符自动截断

    参数：
        command: 完整的 shell 命令，如 "free -h"。

    返回：
        包含退出码、stdout、stderr 的结构化输出。
    """
```

### 6.5 类文档字符串

```python
class AIOperatorException(Exception):
    """所有应用异常的基类。

    每个子类都有两个信息：
      - message: 给用户看的友好提示
      - detail:  给开发者看的原始错误（用于日志排查）

    __init__ 时自动把 detail 写入 loguru 日志。
    """
```

---

## 7. 架构分层规范

### 7.1 四层架构

```
┌─────────────────────────────────────────────┐
│          API 层（app/api/）                    │
│  - 解析 HTTP 请求/响应                         │
│  - 只调用服务层函数（不访问 LLM/DB/工具）       │
│  - 把异常映射到 HTTP 状态码                     │
├─────────────────────────────────────────────┤
│        服务层（app/services/）                 │
│  - Agent 编排逻辑                              │
│  - 调用工具、LLM、MCP Client                   │
│  - 处理业务错误，返回用户友好的消息              │
├─────────────────────────────────────────────┤
│      基础设施层（app/core/）                    │
│  - LLM 工厂（llm_factory.py）                  │
│  - 日志系统（logger.py）                        │
│  - 异常定义（exceptions.py）                    │
│  - Milvus 客户端（milvus_client.py）           │
│  - 可观测性客户端（langfuse_client.py）         │
├─────────────────────────────────────────────┤
│      工具层（app/tools/ + mcp_servers/）       │
│  - 本地工具：@tool 装饰的同步函数               │
│  - MCP 工具：FastMCP 独立进程                   │
│  - 工具之间互不依赖                             │
└─────────────────────────────────────────────┘
```

### 7.2 依赖方向

依赖**只能从上往下**，不能反向：

```
API 层 → 服务层 → 基础设施层 → 工具层
                └→ 工具层
```

- ✅ API 层 import 服务层
- ✅ 服务层 import 基础设施层
- ✅ 服务层 import 工具层
- ❌ 基础设施层 import 服务层（循环依赖）
- ❌ 工具层 import 服务层（工具是叶子节点）

### 7.3 各层职责边界

| 层 | 能做 | 不能做 |
|------|------|------|
| **API 层** | 解析请求参数、调用服务函数、返回 JSON/SSE、捕获异常转 HTTP 状态码 | 直接调 LLM、直接操作数据库、包含业务逻辑 |
| **服务层** | 编排 Agent 图、管理会话记忆、创建 Span、格式化输出 | 直接操作 HTTP 请求/响应对象、定义 FastAPI 路由 |
| **基础设施层** | 管理连接池、初始化配置、定义异常类、提供工厂函数 | 包含业务逻辑、依赖具体的业务模块 |
| **工具层** | 执行具体操作（检索/计算/查时间）、返回结构化结果 | 编排多个工具、管理会话、做 Agent 决策 |

---

## 8. 服务层规范

### 8.1 服务函数签名

```python
# 非流式 — 返回完整结果
async def query(question: str, session_id: str = "default") -> str: ...

# 流式 — 异步生成器，逐个产出事件
async def query_stream(question: str, session_id: str = "default"):
    """异步生成器：yield 统一事件字典"""
    ...
    yield {"type": "content", "data": "文本"}
    yield {"type": "done"}
```

### 8.2 事件字典格式（流式）

所有流式服务**必须**使用统一的事件字典格式：

```python
# 内容事件 — AI 生成的文本 token
{"type": "content", "data": "文本片段"}

# 工具调用事件 — 通知前端工具正在被调用
{"type": "tool_start", "data": "工具名称"}
{"type": "tool_result", "data": "工具返回摘要"}

# 计划/重规划事件（AIOps 专用）
{"type": "plan", "data": {"steps": ["步骤1", "步骤2"]}}
{"type": "replan", "data": {"new_plan": ["调整后的步骤"]}}

# 报告事件（AIOps 专用）
{"type": "report", "data": "Markdown 报告"}

# 结束事件
{"type": "done"}

# 错误事件
{"type": "error", "data": "错误信息字符串"}
```

### 8.3 服务初始化模式

每个服务模块维护私有全局变量（模块级单例），避免每次请求重新创建：

```python
# === 模块级全局变量（单例）===
_agent = None
_memory: MemorySaver | None = None

def _get_memory() -> MemorySaver:
    """获取或创建 MemorySaver 单例。"""
    global _memory
    if _memory is None:
        _memory = MemorySaver()
    return _memory

def _get_agent():
    """获取或创建 Agent 图单例。"""
    global _agent
    if _agent is None:
        _agent = create_agent(...)
    return _agent
```

### 8.4 服务层异常处理

```python
# ✅ 服务层捕获异常，返回用户友好的字符串
try:
    agent = _get_agent()
    result = await agent.ainvoke(...)
except AIOperatorException as e:
    return f"❌ {e.message}"      # 应用异常 → 用户友好消息
except Exception as e:
    logger.error("未预期的错误: {}", e)
    return f"❌ 服务暂时不可用，请稍后重试"  # 未知异常 → 通用消息
```

---

## 9. Agent 开发规范

### 9.1 Agent 创建方式选择

| 方式 | 使用场景 | 复杂度 |
|------|---------|:--:|
| `create_agent()` 高阶 API | 简单的 LLM + 工具循环（RAG Agent、MCP Agent） | 低 |
| 手动 `StateGraph` | 需要自定义循环逻辑（Manual Agent 教学对比） | 中 |
| 多节点图 + 条件路由 | 复杂工作流（Plan-Execute-Replan） | 高 |

**选择原则**：能用 `create_agent` 优先用，除非需要自定义路由逻辑或想教学展示底层原理。

### 9.2 StateGraph 节点函数

```python
# ✅ 节点函数签名：接收 state，返回 state 更新字典
async def run_planner(state: PlanExecuteState) -> dict:
    """从 state 中读取，处理后返回 dict 更新 state。"""
    ...
    return {"plan": new_plan, "past_steps": []}

# ✅ 条件路由函数：接收 state，返回路由键
def route_after_replan(state: PlanExecuteState) -> Literal["executor", "reporter"]:
    if state.get("action") == "replan":
        return "executor"
    return "reporter"
```

### 9.3 图保护机制

所有 Agent 图**必须**有死循环保护：

```python
# ✅ 方案 1：步骤计数器（Plan-Execute-Replan）
if len(past_steps) >= MAX_STEPS:
    return {"action": "respond"}

# ✅ 方案 2：迭代次数限制（在 invoke 层）
# 由 LangGraph 的 recursion_limit 参数控制（默认 25）
config = {"recursion_limit": 30}
```

### 9.4 System Prompt 编写

System Prompt 是一个常量字符串，放在服务文件顶部：

```python
SYSTEM_PROMPT = """你是一个智能运维助手，具备以下能力：

1. **知识库检索**（retrieve_knowledge 工具）：...
2. **时间查询**（get_current_time 工具）：...

重要规则：
- 调用工具后，基于工具返回的结果来回答
- 如果工具调用失败，诚实告知用户，尝试其他方式
- 回答用 Markdown 格式，中文回答
"""
```

**规则**：
- 在 Service 文件中定义，不单独存放为文件
- 每个工具的能力说明必须和工具 docstring 保持一致
- 更新 TOOLS 列表时必须同步更新 SYSTEM_PROMPT

---

## 10. 工具开发规范

### 10.1 本地工具（@tool）

```python
from langchain_core.tools import tool

# ✅ 基本 @tool — 返回字符串
@tool
def get_current_time(timezone_name: str = "Asia/Shanghai") -> str:
    """获取指定时区的当前日期和时间。

    使用场景：
      - 用户问「现在几点」
      - 需要时间信息做判断时

    参数：
        timezone_name: 时区名称，如 "Asia/Shanghai"、"America/New_York"
    """
    ...

# ✅ 返回内容 + 工件 — 用 response_format="content_and_artifact"
@tool(response_format="content_and_artifact")
def retrieve_knowledge(query: str) -> tuple[str, list[dict]]:
    """搜索内部知识库。

    返回：
        (格式化的文本结果, 原始文档列表)
    """
    ...

# ❌ 不要这样：异步函数用 @tool 装饰
@tool
async def bad_tool(): ...  # @tool 只支持同步函数！
```

### 10.2 工具注册

```python
# ✅ 集中定义工具列表
TOOLS = [retrieve_knowledge, get_current_time, calculate]

# ✅ 注册到 create_agent
_agent = create_agent(
    llm,
    tools=TOOLS,        # ← 工具列表
    ...
)

# ✅ 注册到手动图
llm_with_tools = llm.bind_tools(TOOLS)
tool_node = ToolNode(TOOLS)
```

### 10.3 MCP 远程工具（FastMCP）

```python
# ✅ Server 端定义
from fastmcp import FastMCP

mcp = FastMCP("ServerName")

@mcp.tool()
def tool_name(param: str) -> str:
    """工具描述。"""
    ...

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=800x)
```

### 10.4 工具安全检查清单

每个工具必须满足：

- [ ] 有超时机制（防止工具卡死 Agent）
- [ ] 有输出截断（防止一个工具返回 10MB 撑爆上下文）
- [ ] 异常时返回错误描述字符串（不抛异常到 Agent 框架）
- [ ] docstring 足够详细（LLM 靠它做决策）
- [ ] 涉及系统操作的工具必须有白名单/黑名单

---

## 11. API 路由规范

### 11.1 Router 创建

```python
# ✅ 每个路由文件创建一个 router，按功能设置 prefix 和 tags
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["chat"])          # /chat
router = APIRouter(prefix="/api/agent", tags=["agent"])   # /agent/chat
router = APIRouter(prefix="/api/mcp", tags=["mcp"])       # /mcp/tools
```

### 11.2 端点结构

```python
# ✅ 非流式端点
@router.post("/chat")
async def chat(req: ChatRequest):
    try:
        answer = await query(req.question, req.session_id)
        return {"answer": answer}
    except AIOperatorException as e:
        raise HTTPException(status_code=503, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"对话服务异常: {e}")

# ✅ 流式端点
@router.post("/chat_stream")
async def chat_stream(req: ChatRequest):
    async def event_generator():
        async for event in query_stream(req.question, req.session_id):
            yield {
                "event": "message",
                "data": json.dumps(event, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())
```

### 11.3 请求模型

```python
# ✅ 用 Pydantic BaseModel + Field 描述
class ChatRequest(BaseModel):
    question: str = Field(..., description="用户输入的问题", min_length=1)
    session_id: str = Field(default="default", description="会话 ID")
```

### 11.4 HTTP 状态码映射

| 异常类型 | HTTP 状态码 | 说明 |
|------|:--:|------|
| 正常返回 | 200 | |
| `AIOperatorException` | 503 | 服务不可用（LLM 挂了、Milvus 连不上） |
| `Exception` | 500 | 未预期的内部错误 |
| 参数校验失败 | 422 | Pydantic 自动处理（`min_length`、类型不匹配等） |

---

## 12. 异常处理规范

### 12.1 异常层次

```
Exception
 └── AIOperatorException           # 基类：message(用户) + detail(日志)
      ├── LLMServiceError          # LLM API 错误
      ├── EmbeddingServiceError    # Embedding 错误
      ├── VectorDBError            # Milvus 错误
      ├── DocumentProcessError     # 文档处理错误
      └── MCPServiceError          # MCP 错误
```

### 12.2 创建新异常类

```python
# ✅ 模式：message(固定用户友好提示) + detail(传入技术细节)
class NewServiceError(AIOperatorException):
    """新服务的异常。

    可能原因：xxx、yyy。
    """

    def __init__(self, detail: str = ""):
        super().__init__(
            message="xxx 服务暂时不可用，请稍后重试",
            detail=detail,
        )
```

### 12.3 三层捕获模式

```python
# 第 1 层 — 基础设施层：抛应用异常
try:
    _client = MilvusClient(...)
except Exception as e:
    raise VectorDBError(detail=f"无法连接到 Milvus: {e}") from e

# 第 2 层 — 服务层：捕获应用异常，返回友好字符串
try:
    result = await agent.ainvoke(...)
except AIOperatorException as e:
    return f"❌ {e.message}"

# 第 3 层 — API 层：捕获所有异常，映射 HTTP 状态码
try:
    answer = await query(...)
except AIOperatorException as e:
    raise HTTPException(status_code=503, detail=e.message)
except Exception as e:
    raise HTTPException(status_code=500, detail=f"对话服务异常: {e}")
```

### 12.4 异常处理铁律

1. **永不裸露 `except:`**（至少写 `except Exception:`）
2. **异常链必须保留**（`raise NewError(...) from original_error`）
3. **吃了异常就处理干净**（要么恢复，要么把信息返回给用户）
4. **不要在 finally 中 raise**（会覆盖原始异常）

---

## 13. 日志规范

### 13.1 日志系统

```python
# ✅ 唯一正确的导入方式
from app.core.logger import logger

# ❌ 不允许
import logging              # 禁止直接用标准库 logging
from loguru import logger   # 禁止绕过 core 模块
print("debug info")         # 禁止用 print 调试
```

### 13.2 日志级别使用

| 级别 | 使用场景 | 示例 |
|------|---------|------|
| `logger.debug()` | 开发调试细节 | Agent 每一步的状态变化 |
| `logger.info()` | 正常业务流程 | "用户上传了文件", "RAG Agent 初始化完成", HTTP 请求日志 |
| `logger.warning()` | 可恢复的问题 | "MCP Server 连接超时，将使用本地工具", "LangFuse 客户端连接失败" |
| `logger.error()` | 需要关注的错误 | "Milvus 连接失败", "LLM API 返回 500" |
| `logger.critical()` | 导致应用不可用的致命错误 | 极少使用 |

### 13.3 日志格式

使用 `{}` 占位符（loguru 风格），不是 `%s`：

```python
# ✅ loguru 风格
logger.info("用户上传了文件 {} ({} 字节)", file.filename, file.size)
logger.error("Milvus 连接失败: {}", error)
logger.info("RAG Agent 初始化完成 — 模型: {}, 消息上限: {}", model, max_msg)

# ❌ printf 风格
logger.info("用户上传了文件 %s (%d 字节)" % (file.filename, file.size))
```

### 13.4 日志内容要求

- 记录**外部调用**：每次 LLM API 调用、每次 Milvus 查询、每次 MCP 工具调用
- 记录**状态变化**：Agent 初始化完成、配置重载、连接建立/断开
- 记录**关键决策**：消息修剪（`"对话消息修剪: 45 → 20 条"`）
- 不记录**用户输入的具体内容**（隐私：可以记摘要，但不能原样记敏感信息）

---

## 14. 配置管理规范

### 14.1 配置类

使用 `pydantic-settings`：

```python
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    """应用的全局配置，所有字段自动从 .env 读取。"""

    # 每个字段都有默认值
    app_name: str = "AIOperator"
    app_version: str = "0.1.0"
    debug: bool = True

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",   # ← 关键：允许 .env 中有未定义的变量
    }

settings = Settings()   # 全局单例
```

### 14.2 新增配置项

按类别分组，加注释头：

```python
# ---- 新功能配置 ----
new_feature_enabled: bool = True
new_feature_url: str = "http://127.0.0.1:800x/mcp"
new_feature_api_key: Optional[str] = None
```

### 14.3 .env 文件

```bash
# ============================================
# 功能名
# ============================================
NEW_FEATURE_ENABLED=true
NEW_FEATURE_URL=http://127.0.0.1:800x/mcp
```

**规则**：
- `.env.example` 和 `.env` 保持同步（字段名、默认值）
- 环境变量名全大写、下划线分隔（pydantic-settings 自动映射）
- 敏感值（API Key、密码）在 `.env` 中，绝不提交到 Git

---

## 15. 异步与流式规范

### 15.1 async/await

```python
# ✅ 服务层函数用 async def
async def query(question: str, session_id: str = "default") -> str: ...

# ✅ LangChain/LangGraph 统一用 a 前缀的异步方法
result = await agent.ainvoke(...)       # 不是 agent.invoke()
async for chunk in agent.astream(...):  # 不是 agent.stream()
response = await llm.ainvoke(...)       # 不是 llm.invoke()

# ✅ 同步代码跑在线程池中
import asyncio
result = await asyncio.to_thread(sync_function, arg1, arg2)
# 或
loop = asyncio.get_event_loop()
result = await loop.run_in_executor(None, sync_function)
```

### 15.2 @tool 内的异步调用

`@tool` 必须是同步函数，内部用 `asyncio.run()` 调异步函数：

```python
@tool(response_format="content_and_artifact")
def retrieve_knowledge(query: str) -> tuple[str, list[dict]]:
    results = asyncio.run(similarity_search(query, k=5))  # ← 同步内调异步
    ...
```

### 15.3 流式生成器

```python
# ✅ 异步生成器模式
async def query_stream(question: str, session_id: str = "default"):
    """注意：这是一个 async generator，不是 async function。"""
    try:
        async for chunk, metadata in agent.astream(...):
            token = getattr(chunk, "content", "")
            if token:
                yield {"type": "content", "data": token}
        yield {"type": "done"}
    except Exception as e:
        yield {"type": "error", "data": str(e)}
```

---

## 16. 单例模式规范

### 16.1 模块级单例（推荐）

用于服务模块中的 Agent 图、Memory、客户端：

```python
# ✅ 模块级私有变量 + _get_xxx() 函数
_agent = None
_memory: MemorySaver | None = None

def _get_memory() -> MemorySaver:
    global _memory
    if _memory is None:
        _memory = MemorySaver()
    return _memory

def _get_agent():
    global _agent
    if _agent is None:
        _agent = create_agent(...)
    return _agent
```

### 16.2 类级单例（用于跨模块共享的客户端）

用于 MCP Client Manager、LangFuse Client Manager：

```python
class MCPClientManager:
    _instance: "MCPClientManager | None" = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
```

### 16.3 全局配置单例

```python
# ✅ config.py 中的 settings 实例是全局唯一的
from app.config import settings
```

---

## 17. 安全规范

### 17.1 敏感信息

```python
# ❌ 绝对禁止
DASHSCOPE_API_KEY = "sk-abc123..."  # 硬编码在代码中

# ✅ 正确的做法
from app.config import settings
api_key = settings.dashscope_api_key  # 从 .env 读取
```

### 17.2 Shell 命令执行（如涉及）

```python
# ✅ shell=False（默认），传参数列表
subprocess.run(["ps", "aux"], capture_output=True)

# ⚠️ 如果需要管道，shell=True 前必须做安全扫描
# 参见 SPEC_TOOLS.md 的四层安全模型
```

### 17.3 输出安全

- 工具输出必须截断（防止 10MB 输出撑爆 LLM 上下文）
- 用户输入不原样写入日志（可能包含敏感信息）
- API 返回的 error detail 不暴露内部路径/堆栈（生产环境）

---

## 18. 依赖管理规范

### 18.1 pyproject.toml

```toml
[project]
name = "aioperator"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115.0",
    # ...
]
```

### 18.2 新增依赖规则

1. **最小版本约束**：`>=` 而非 `==`（允许小版本升级）
2. **验证必要性**：能用标准库就不用第三方包
3. **避免重复**：检查是否已有功能相同的依赖
4. **按字母排序**：新增依赖插入到正确位置

### 18.3 Dockerfile 依赖安装

项目 Dockerfile 直接解析 `pyproject.toml` 安装依赖：

```dockerfile
RUN python -c "import tomllib; deps = tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']; import subprocess, sys; sys.exit(subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--no-cache-dir'] + deps))"
```

因此，**所有运行时依赖必须列在 `pyproject.toml` 的 `dependencies` 中**。

---

## 19. Docker 与部署规范

### 19.1 docker-compose.yml

- 每个服务必须有 `container_name`（`aioperator-xxx` 格式）
- 每个服务必须有 `restart: unless-stopped`
- 需要持久化的数据必须挂载 volume（不能丢失数据）
- 服务间依赖用 `depends_on` + `condition: service_healthy`
- 健康检查间隔合理（不要太频繁，建议 10s）

### 19.2 端口分配

| 端口 | 服务 | 说明 |
|:----:|------|------|
| 9900 | 主应用 | FastAPI |
| 8003 | mcp-time | MCP 时间服务 |
| 8004 | mcp-db | MCP 数据库服务 |
| 8005 | mcp-ppt | MCP PPT 服务 |
| 8006 | mcp-docker | MCP Docker 服务（规划中） |
| 8007 | mcp-search | MCP 搜索服务（规划中） |
| 3000 | langfuse-server | LangFuse Dashboard |
| 5433 | langfuse-postgres | LangFuse 数据库（映射到宿主机，避开 5432） |
| 3306 | mysql | MySQL 数据库 |
| 19530 | milvus | Milvus 向量数据库 |

### 19.3 新增 MCP Server 模板

```yaml
  mcp-xxx:
    build: .
    container_name: aioperator-mcp-xxx
    restart: unless-stopped
    command: python mcp_servers/xxx_server.py
    ports:
      - "800x:800x"
    env_file: .env
    # 如有依赖其他服务：
    # depends_on:
    #   mysql:
    #     condition: service_healthy
```

---

## 20. SPEC 文档编写规范

### 20.1 何时需要 SPEC

| 情况 | 是否需要 SPEC | 说明 |
|------|:--:|------|
| 新增一个完整的子系统 | ✅ | 如 可观测性系统、工具系统扩展 |
| 修改一个现有功能的小部分 | ❌ | 直接改代码，注释说清楚即可 |
| 跨多个文件的架构变更 | ✅ | 需要在 SPEC 中画出改动前后的对比 |
| Bug 修复 | ❌ | 修复+注释 |
| 新增一个全新的开发规范 | ✅ | 如本文档 |

### 20.2 SPEC 文档结构

```markdown
# SPEC: 中文标题

> **版本**: v1.0
> **创建日期**: YYYY-MM-DD
> **状态**: 待开发 | 开发中 | 已完成
> **依赖**: 依赖的其他 SPEC 或已完成的功能

---

## 目录

## 1. 概述与目标
### 1.1 背景 — 为什么需要这个功能
### 1.2 目标 — 要达成什么效果
### 1.3 非目标 — 明确不做的事情

## 2. 技术选型（如有选型决策）

## 3. 架构设计

## 4. 实现方案详解

## N. 分阶段实现计划

## N+1. 文件改动清单

## N+2. 验收标准

## 附录
```

### 20.3 SPEC 编写原则

1. **中文为主**，技术术语保留英文
2. **图表用 ASCII art**（方便在终端和 diff 中查看）
3. **代码示例必须可运行**（至少语法正确）
4. **文件路径用相对路径**（从项目根目录开始）
5. **验收标准可量化**：`[ ] 访问 localhost:3000 看到 Dashboard` 而非 `[ ] 启动成功`

---

## 附录 A：代码模板

### A.1 新建 API 路由文件

```python
"""
xxx API — 处理 /xxx 相关请求。

这一层只负责：
  - 解析请求参数
  - 调用对应的服务函数
  - 返回约定格式的响应
"""

import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.services.xxx_service import do_something, do_something_stream
from app.core.exceptions import AIOperatorException

router = APIRouter(prefix="/api/xxx", tags=["xxx"])


# === 请求模型 ===
class XxxRequest(BaseModel):
    param: str = Field(..., description="参数说明", min_length=1)
    session_id: str = Field(default="default", description="会话 ID")


# === 非流式端点 ===
@router.post("/action")
async def action(req: XxxRequest):
    try:
        result = await do_something(req.param, req.session_id)
        return {"result": result}
    except AIOperatorException as e:
        raise HTTPException(status_code=503, detail=e.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务异常: {e}")


# === 流式端点 ===
@router.post("/action_stream")
async def action_stream(req: XxxRequest):
    async def event_generator():
        async for event in do_something_stream(req.param, req.session_id):
            yield {
                "event": "message",
                "data": json.dumps(event, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())
```

### A.2 新建服务文件

```python
"""
xxx 服务 — 一句话说明这个服务的职责。
"""

from app.core.logger import logger
from app.core.exceptions import AIOperatorException
from app.core.llm_factory import create_llm, create_llm_streaming
from app.config import settings

# === 模块级单例 ===
_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        _agent = _build_agent()
        logger.info("Xxx Agent 初始化完成")
    return _agent


def _build_agent():
    """构建 Agent 图。"""
    ...


# === 公共 API ===
async def do_something(param: str, session_id: str = "default") -> str:
    try:
        agent = _get_agent()
        ...
    except AIOperatorException as e:
        return f"❌ {e.message}"
    except Exception as e:
        logger.error("未预期的错误: {}", e)
        return f"❌ 服务暂时不可用"


async def do_something_stream(param: str, session_id: str = "default"):
    try:
        agent = _get_agent()
        ...
        yield {"type": "done"}
    except Exception as e:
        yield {"type": "error", "data": str(e)}
```

### A.3 新建本地工具

```python
"""
xxx 工具 — 一句话说明。
"""

from langchain_core.tools import tool
from app.core.logger import logger


@tool
def tool_name(param: str) -> str:
    """一句话说明工具的功能。

    使用场景：
      - 场景 1
      - 场景 2

    参数：
        param: 参数说明

    返回：
        返回值说明
    """
    try:
        result = _do_work(param)
        return result
    except Exception as e:
        logger.error("工具执行失败: {}", e)
        return f"工具执行失败: {e}"


def _do_work(param: str) -> str:
    """实际执行逻辑（私有函数）。"""
    ...
```

### A.4 新建 MCP Server

```python
"""
Xxx MCP Server — 一句话说明。

启动方式: python mcp_servers/xxx_server.py
端口: 800x
"""

import os
from dotenv import load_dotenv
from fastmcp import FastMCP
from loguru import logger

load_dotenv()

logger.add("logs/xxx_server_{time:YYYY-MM-DD}.log", rotation="00:00", retention="30 days")

mcp = FastMCP("XxxTool")


@mcp.tool()
def tool_name(param: str = "") -> str:
    """工具描述（给 LLM 读的，要详细）。

    使用场景：
      - ...

    参数：
        param: ...

    返回：
        ...
    """
    try:
        ...
    except Exception as e:
        logger.error("工具执行失败: {}", e)
        return f"工具执行失败: {e}"


if __name__ == "__main__":
    logger.info("Xxx MCP Server 启动 — 端口: 800x")
    mcp.run(transport="streamable-http", host="0.0.0.0", port=800x)
```

---

> **本文档是 AI 生成代码的强制性规范。**  
> 所有在此项目中的代码变更必须遵守本规范。  
> 如有违反，应在 Code Review 中指出并要求修改。
