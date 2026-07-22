# AIOperator 故障排查手册

> 本文档记录项目开发与部署过程中遇到的真实 Bug，从现象到根因到修复，完整复盘。
> 面向 LangChain / LangGraph 初学者，每个 Bug 都讲清楚「为什么」，而不只是「怎么改」。

---

## 太长不看版（TL;DR）

> 💡 **一句话总结**：对话聊多了就报错，因为「消息修剪」时把工具调用的"请求"留下了、"回复"裁丢了，导致消息序列不完整被 LLM API 拒绝。

**这次踩了两个坑**：

1. **消息修剪 Bug**（🔴 严重）：Agent 对话超过 20 条消息后，程序会裁掉旧消息只留最近 20 条。但裁剪逻辑有漏洞——只防了"回复被留下、请求被裁掉"的情况，没防"请求被留下、回复被裁掉"的情况。结果发给 AI 的消息序列里出现了"我要查时间"但后面没有"时间是 14:30"，AI API 直接报 400 拒绝。

2. **内存存储风险**（🟡 中等）：对话历史存在内存里（MemorySaver），服务一重启全丢。而且正因为内存里攒了太多对话（超过 20 条），才触发了上面那个修剪 Bug。本地开发时频繁重启、对话短，所以一直没发现；上了云服务器长时间运行，Bug 才现身。

**修复思路**：
- 消息修剪 → 补全边界处理，删掉"没回复"的工具调用请求
- 内存存储 → 换成 SqliteSaver，把对话存到文件里，重启不丢

---

## Bug #1：对话报 400 错误 — tool_calls 必须后跟 tool messages

### 基本信息

| 项目 | 内容 |
|------|------|
| 发现时间 | 2026-07-22（云服务器部署后） |
| 影响范围 | 对话模式（RAG Agent）、MCP 模式、诊断模式（AIOps） |
| 不受影响 | 手动 Agent 模式（但存在同源隐患，见下文） |
| 严重程度 | 🔴 严重 — 核心功能不可用 |
| 触发条件 | 同一会话对话超过 20 条消息后 |

### 1.1 现象

部署到云服务器后，前端对话界面返回：

```
服务暂时不可用，请稍后重试
（详情: Error code: 400 - {'error': {'message': "An assistant message with
'tool_calls' must be followed by tool messages responding to each 'tool_call_id'.
(insufficient tool messages following tool_calls message)",
'type': 'invalid_request_error', ...}}）
```

**特征**：
- 刚部署完 fresh start 时一切正常
- 聊了一会儿（多轮对话后）突然开始报错
- 报错后该会话持续报错，换一个新会话又能短暂正常
- 四种模式中只有「手动 Agent」不报错

### 1.2 前置知识：Agent 的消息序列长什么样

理解这个 Bug 之前，必须先搞清楚 LangChain Agent 工作时的消息流。

> 💡 **通俗理解：Agent 调工具就像餐厅点餐**
>
> 想象你在餐厅吃饭：
> 1. **你点菜**：跟服务员说"来份宫保鸡丁" → 这就是 `HumanMessage`（用户提问）
> 2. **服务员去后厨问**：服务员说"稍等，我去后厨看看有没有食材" → 这就是 `AIMessage(tool_calls)`（AI 决定调工具）
> 3. **后厨回复**：后厨说"有鸡丁，没花生" → 这就是 `ToolMessage`（工具返回结果）
> 4. **服务员告诉你**：服务员回来说"鸡丁有，但缺花生，要不要换个菜？" → 这就是 `AIMessage`（AI 基于结果回答你）
>
> 这四步是一个完整的「对话回合」。**问题在于：第 2 步和第 3 步必须成对出现**——服务员说了"去后厨问"，就必须拿回后厨的回复。如果服务员只说了"去后厨问"然后直接跳到你下一次点菜，餐厅经理（LLM API）就会说："你刚才说去后厨问，结果呢？拒绝服务！"——这就是 400 错误。

一次带工具调用的对话，消息序列是这样的：

```
HumanMessage("现在几点？")                          ← 用户提问
AIMessage(tool_calls=[{name:"get_time", id:"call_1"}])  ← LLM 决定调工具
ToolMessage(tool_call_id="call_1", content="14:30")     ← 工具返回结果
AIMessage("现在是下午 14:30")                       ← LLM 基于结果回答
```

**关键规则（OpenAI 协议规范，DashScope 兼容接口同样遵守）**：

> 每个 `AIMessage` 如果带有 `tool_calls`，后面**必须紧跟**对应的 `ToolMessage`，
> 每个 `tool_call_id` 都要有对应的响应。否则 API 直接返回 400 拒绝。

这就像写信：你寄出了一封「请查收附件」的信（tool_calls），
就必须附上附件（ToolMessage）。收件人（LLM API）发现附件缺失就会拒收。

### 1.3 根因分析

> 💡 **通俗理解：消息修剪就像「聊天记录截图」**
>
> 想象你在微信里跟人聊了 100 条消息，但 LLM 一次只能看 20 条。于是你截图发给它——只截最近 20 条。
>
> 问题来了：如果截图的**裁剪线**恰好切在「服务员说去后厨问」（AIMessage tool_calls）和「后厨回复」（ToolMessage）之间，截图里就只有"去后厨问"没有"后厨的回复"。LLM 看到这个截图就懵了："你说去问了，但结果呢？"——于是报错。
>
> 代码里的修复只处理了一半：它检查了"截图开头是不是后厨回复（孤立的 ToolMessage）"，但**忘了检查"截图开头是不是服务员的那句去后厨问（孤立的 AIMessage tool_calls）"**。这就是 Bug 的根源。

#### Bug 出在消息修剪函数

文件：`app/core/message_trimmer.py`

Agent 的对话历史会越来越长，超过 LLM 的 token 限制。所以项目用滑动窗口修剪：只保留最近 20 条消息。

```python
# 修剪逻辑（有 Bug 的版本）
def trim_conversation_history(messages, max_messages=20):
    if len(messages) <= max_messages:
        return messages

    # 保留最近 20 条
    trimmed = messages[-max_messages:]

    # 修复工具调用链完整性：删掉开头的孤立 ToolMessage
    while trimmed and isinstance(trimmed[0], ToolMessage):
        trimmed = trimmed[1:]

    return trimmed
```

这个函数处理了一种边界情况，但**漏了另一种**：

**已处理** ✅：裁剪后第一条是 `ToolMessage` → 说明它对应的 `AIMessage(tool_calls)` 被裁掉了 → 删掉这个孤立 ToolMessage。

**未处理** ❌：裁剪后第一条是 `AIMessage(tool_calls)` → 它对应的 `ToolMessage` 可能被裁到窗口外了 → 这个 AIMessage 成了「孤儿 tool_calls」。

#### 用具体场景说明

假设对话历史有 24 条消息（已超过 20 条上限），裁剪窗口取最后 20 条：

```
完整历史（24 条）：
[1]  HumanMessage("CPU 高怎么排查？")
[2]  AIMessage(tool_calls=[retrieve_knowledge])     ← 带 tool_calls
[3]  ToolMessage("知识库检索结果...")               ← 响应 #2
[4]  AIMessage("根据文档，先检查 top 进程...")
... 中间省略 ...
[21] AIMessage(tool_calls=[get_current_time])       ← 带 tool_calls ⚠️
[22] ToolMessage("当前时间 14:30")                  ← 响应 #21
[23] AIMessage("现在是 14:30")
[24] HumanMessage("那内存使用情况呢？")

裁剪窗口 messages[-20:] 取 [5]~[24]：
[5]  ... (某条消息)
...
[21] AIMessage(tool_calls=[get_current_time])       ← 留在窗口内
[22] ToolMessage("当前时间 14:30")                  ← 留在窗口内 ✅ 完整
[23] AIMessage("现在是 14:30")
[24] HumanMessage("那内存使用情况呢？")

这没问题。但如果裁剪窗口刚好从 [22] 开始呢？

裁剪窗口 messages[-20:] 取 [5]~[24]，但 #21 恰好是第 5 条：
[21] AIMessage(tool_calls=[get_current_time])       ← 第一条！带 tool_calls
[22] ToolMessage("当前时间 14:30")                  ← 还在，配对完整 ✅

再极端一点，如果裁剪点落在 #21 和 #22 之间：
[21] AIMessage(tool_calls=[get_current_time])       ← 第一条！
[22] ToolMessage("...")                             ← 被裁掉了！❌
[23] AIMessage("现在是 14:30")
[24] HumanMessage("那内存使用情况呢？")

→ 发给 DashScope 的序列：AIMessage(tool_calls) → AIMessage → HumanMessage
→ tool_calls 后面没有 ToolMessage → 400 错误！
```

当前代码的 `while` 循环只检查了 `isinstance(trimmed[0], ToolMessage)`，
**没有检查 `trimmed[0]` 是不是带 `tool_calls` 的 `AIMessage`**。这就是 Bug。

#### 为什么手动 Agent 不报错？

> 💡 **通俗理解：就像两辆都有刹车隐患的车**
>
> 手动 Agent 和其他三个模式用了**同一个有缺陷的修剪函数**，就像两辆车都有刹车隐患。一辆经常跑高速（对话多、工具多），隐患很快暴露了；另一辆只在小区里低速开（对话少、工具少），暂时没出事。但**隐患是一样的**，哪天上高速一样会出事。
>
> 所以手动 Agent "正常"不是因为它没 Bug，只是还没触发。它是个**定时炸弹**——多聊几轮、多调几次工具，照样炸。

手动 Agent（`manual_agent_service.py`）同样调了 `trim_conversation_history`，按理说也有这个 Bug。但它「暂时正常」的原因：

1. **工具少**：手动 Agent 只有 4 个本地工具，单轮对话产生的消息少
2. **触发概率低**：需要对话历史超过 20 条才会修剪，手动模式测试时轮数不够
3. **本质是定时炸弹**：多聊几轮、多触发几次工具调用，一样会炸

这也说明：**「能跑」不等于「没 Bug」**，只是触发条件没满足而已。

#### 为什么云服务器部署后才出现？

> 💡 **通俗理解：草稿纸 vs 笔记本**
>
> 本地开发时，你频繁重启服务，每次重启 `MemorySaver`（内存存储）就**清空了**——就像在草稿纸上记事，关灯（重启）后擦得干干净净。所以本地聊天记录永远很短，不会触发修剪，Bug 也就没机会暴露。
>
> 云服务器上服务**长时间不重启**，对话历史一直累积——就像写进笔记本里，越写越多。累积超过 20 条后触发修剪 → Bug 现身。
>
> 这也解释了为什么"换一个新会话又能短暂正常"：新会话从 0 开始计数，还没到 20 条，当然不报错。等聊到 20 条以上，又炸了。

| | 本地开发 | 云服务器 |
|---|---------|---------|
| 服务运行时长 | 短，频繁重启调试 | 长时间持续运行 |
| MemorySaver 状态 | 重启即清空 | 一直在内存中累积 |
| 对话历史长度 | 短，通常不超过 20 条 | 长，多轮对话后超过 20 条 |
| 是否触发修剪 | 否 | 是 |
| 是否暴露 Bug | 否 | 是 |

本地开发时每次重启服务，`MemorySaver`（内存存储）就清空了，对话历史很短，根本不会触发修剪逻辑。云服务器上服务持续运行，同一个 `session_id` 的对话历史不断累积，超过 20 条后触发修剪 → 暴露 Bug。

### 1.4 修复方案

> 💡 **通俗理解：修复就像「补全截图的裁剪逻辑」**
>
> 原来的代码截图时会检查："截图开头是不是后厨的回复（孤立 ToolMessage）？是的话删掉。"
> 修复就是补上另一半检查："截图开头是不是服务员那句'去后厨问'（孤立 AIMessage tool_calls），而且后面没跟着后厨回复？是的话也删掉。"
>
> 两边都检查后，截图开头一定是干净的（要么是用户提问，要么是 AI 的正常回答），不会再出现"半截对话"。

#### 方案 A：补全修剪函数的边界处理（推荐，最小改动）

在现有的 `while` 循环中，增加对「开头是带 tool_calls 的 AIMessage」的检查：

```python
from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage, AIMessage


def trim_conversation_history(
    messages: list[BaseMessage],
    max_messages: int = 20,
) -> list[BaseMessage]:
    """修剪对话历史，保留最近的 max_messages 条消息。

    修剪策略：
      1. 如果消息总数 ≤ max_messages，不做任何处理
      2. 否则保留最近 max_messages 条
      3. 确保不截断工具调用链：
         - 删除开头的孤立 ToolMessage（对应的 AIMessage tool_call 被裁掉了）
         - 删除开头的孤立 AIMessage(tool_calls)（对应的 ToolMessage 被裁掉了）
    """
    if len(messages) <= max_messages:
        return messages

    trimmed = messages[-max_messages:]

    # 修复工具调用链完整性
    while trimmed:
        first = trimmed[0]

        # 情况 1：开头是孤立的 ToolMessage
        # → 它对应的 AIMessage(tool_calls) 已被裁掉，删掉这个 ToolMessage
        if isinstance(first, ToolMessage):
            trimmed = trimmed[1:]
            continue

        # 情况 2：开头是带 tool_calls 的 AIMessage
        # → 检查后面是否紧跟足够的 ToolMessage 响应
        #   如果不够，说明对应的 ToolMessage 被裁掉了，删掉这个 AIMessage
        if isinstance(first, AIMessage) and getattr(first, "tool_calls", None):
            num_tool_calls = len(first.tool_calls)
            # 数一下紧随其后的 ToolMessage 数量
            following_tool_msgs = 0
            for i in range(1, len(trimmed)):
                if isinstance(trimmed[i], ToolMessage):
                    following_tool_msgs += 1
                else:
                    break
            if following_tool_msgs < num_tool_calls:
                # ToolMessage 不够，删掉这个孤立的 AIMessage(tool_calls)
                trimmed = trimmed[1:]
                continue
            # ToolMessage 够，配对完整，停止修剪
            break

        # 其他情况（HumanMessage 或无 tool_calls 的 AIMessage），正常保留
        break

    return trimmed
```

**修复要点**：与原有的「删孤立 ToolMessage」逻辑对称，增加「删孤立 AIMessage(tool_calls)」逻辑。两种情况都处理后，修剪后的消息序列一定不会出现断裂的工具调用链。

#### 方案 B：使用 LangChain 官方 trim_messages（备选）

LangChain 0.3 提供了官方的消息修剪工具 `trim_messages`，内置了更完善的边界处理：

```python
from langchain_core.messages import trim_messages

def trim_conversation_history(messages, max_messages=20):
    return trim_messages(
        messages,
        max_tokens=max_messages,      # 用消息数当 token 数
        token_counter=len,            # 按消息条数计数，不按 token
        strategy="last",              # 保留最后 N 条
        start_on="human",             # 确保以 HumanMessage 开头（避免孤立 tool_calls）
        include_system=True,          # 保留 SystemMessage
    )
```

`start_on="human"` 确保修剪后的第一条一定是 `HumanMessage`，从根源上避免了以 `AIMessage(tool_calls)` 或 `ToolMessage` 开头的情况。

**两种方案对比**：

| | 方案 A（手动修复） | 方案 B（官方工具） |
|---|---|---|
| 改动量 | 小，只改一个函数 | 小，替换函数实现 |
| 可控性 | 高，逻辑透明 | 中，依赖官方实现 |
| 保留消息数 | 可能少于 max（删孤立消息后） | 可能少于 max（跳到 HumanMessage） |
| 维护成本 | 需自己维护边界逻辑 | 官方维护 |
| 推荐场景 | 想完全掌控逻辑 | 想用官方方案省心 |

> **本项目建议用方案 A**：作为学习项目，手写修剪逻辑能更深入理解消息序列的配对关系。

### 1.5 验证方法

修复后可以用以下方式验证：

```python
# 单元测试：模拟裁剪后开头是孤立 AIMessage(tool_calls) 的场景
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from app.core.message_trimmer import trim_conversation_history

messages = [
    HumanMessage("问题1"),
    AIMessage("回答1"),
    HumanMessage("问题2"),
    AIMessage("回答2"),
    # 下面这条带 tool_calls，但它的 ToolMessage 在窗口外
    AIMessage(content="", tool_calls=[{"name": "get_time", "args": {}, "id": "call_1"}]),
    HumanMessage("问题3"),  # ← 注意：tool_calls 后面没有 ToolMessage
]

trimmed = trim_conversation_history(messages, max_messages=3)
# 修复前：trimmed = [AIMessage(tool_calls=...), HumanMessage("问题3")] → 会触发 400
# 修复后：trimmed = [HumanMessage("问题3")] → 正常
assert not any(getattr(m, "tool_calls", None) for m in trimmed), "仍存在孤立 tool_calls"
```

---

## 风险点 #1：对话记忆使用内存存储（MemorySaver）

### 基本信息

| 项目 | 内容 |
|------|------|
| 风险等级 | 🟡 中等 — 不影响功能正确性，但影响用户体验和数据安全 |
| 涉及文件 | `rag_agent_service.py`、`manual_agent_service.py`、`mcp_agent_service.py`、`aiops_service.py` |
| 当前实现 | `MemorySaver`（纯内存） |

### 2.1 问题分析

> 💡 **通俗理解：MemorySaver 就像「脑子里记事」**
>
> `MemorySaver` 把所有对话存在进程的内存里，就像你在脑子里记事。好处是快，坏处是：
> - **睡觉就忘**（服务重启）→ 所有用户的对话历史全部消失，用户会觉得"AI 怎然失忆了"
> - **只能一个人记**（多实例部署）→ 两个服务员各记各的，客人换了个服务员，之前说的话全不知道
> - **脑子越塞越满**（内存增长）→ 长期运行后内存只增不减，最后可能 OOM 崩溃
>
> 这也是 Bug #1 的帮凶：正因为在云服务器上"脑子里记的事越来越多"，累积超过 20 条才触发了那个修剪 Bug。本地开发时频繁"睡觉清空"，永远触发不了。

当前四个 Agent 服务都用 LangGraph 的 `MemorySaver` 作为 checkpointer（检查点存储器）：

```python
from langgraph.checkpoint.memory import MemorySaver

_memory: MemorySaver | None = None

def _get_memory() -> MemorySaver:
    global _memory
    if _memory is None:
        _memory = MemorySaver()
    return _memory
```

`MemorySaver` 把所有对话状态存在进程内存里，这意味着：

| 风险场景 | 后果 |
|---------|------|
| 服务重启（容器重启、部署更新、OOM） | **所有用户的对话历史全部丢失**，用户会感觉「AI 失忆了」 |
| 多实例部署（横向扩展） | 每个实例的 MemorySaver 独立，**同一个用户打到不同实例时历史不连贯** |
| 内存增长 | 长期运行后内存占用持续增长，**没有清理机制**，可能导致 OOM |
| 容器编排重启 | Docker `restart: unless-stopped` 重启后历史清空 |

**为什么这是 Bug #1 的帮凶**：

Bug #1（消息修剪）之所以在云服务器上才暴露，正是因为 `MemorySaver` 让对话历史在内存中持续累积，超过了 20 条触发修剪。如果每次重启都清空，本地开发时永远触发不了。这两个问题叠加在一起，才让 Bug 在部署后才显现。

### 2.2 LangGraph 的 Checkpointer 体系

> 💡 **通俗理解：三种「存钱方式」**
>
> LangGraph 提供了三种 Checkpointer，就像三种存钱的方式：
>
> | Checkpointer | 比喻 | 特点 |
> |-------------|------|------|
> | `MemorySaver` | **把钱攥手里** | 最快，但转身就丢（重启就没） |
> | `SqliteSaver` | **存进存钱罐** | 安全，摔不坏（文件保存），但只能一个人用 |
> | `PostgresSaver` | **存进银行** | 最安全，多人共享，但要去银行排队（需要额外服务） |
>
> 好消息是：**三种方式的用法完全一样**，切换时只改一行初始化代码，其他业务逻辑不动。这就是"抽象层"的价值——你不需要关心钱存在哪，存取接口都一样。

LangGraph 提供了三种官方 Checkpointer，按持久化程度递增：

| Checkpointer | 存储介质 | 是否需要额外服务 | 适用场景 |
|-------------|---------|:---------------:|---------|
| `MemorySaver` | 进程内存 | 否 | 开发调试、单次会话 |
| `SqliteSaver` | SQLite 文件 | 否 | 单机部署、小型项目 |
| `PostgresSaver` | PostgreSQL | 是（需 PG 服务） | 生产环境、多实例 |

它们的 API 完全一致，切换时只需改一行 import 和初始化代码，**不影响任何业务逻辑**。这就是 LangGraph 设计 checkpointer 抽象层的价值——解耦存储介质与业务逻辑。

```
MemorySaver（内存）  →  SqliteSaver（文件）  →  PostgresSaver（数据库）
   开发调试               单机生产               多实例生产
   ↗ 重启丢失             ↗ 重启保留             ↗ 重启保留 + 多实例共享
```

### 2.3 修复方案

#### 方案 1：改用 SqliteSaver（推荐，适合本项目）

SqliteSaver 把对话状态存到本地 SQLite 文件中，服务重启后历史不丢失，且不需要额外部署数据库服务。

```python
# 修复前
from langgraph.checkpoint.memory import MemorySaver

def _get_memory() -> MemorySaver:
    global _memory
    if _memory is None:
        _memory = MemorySaver()
    return _memory


# 修复后
from langgraph.checkpoint.sqlite import SqliteSaver
import os

_memory = None

def _get_memory():
    global _memory
    if _memory is None:
        # 对话历史持久化到 SQLite 文件，服务重启不丢失
        db_path = os.getenv("CHECKPOINT_DB", "checkpoints.db")
        _memory = SqliteSaver.from_conn_string(db_path)
    return _memory
```

**注意事项**：
- `SqliteSaver` 需要安装依赖：`pip install langgraph-checkpoint-sqlite`
- 在 `pyproject.toml` 中添加该依赖
- Docker 部署时需要把 `checkpoints.db` 挂载到 volume，否则容器重启文件丢失

```yaml
# docker-compose.yml 中 app 服务添加 volume 挂载
app:
  volumes:
    - checkpoint_data:/app/data    # 持久化 SQLite 文件
  environment:
    - CHECKPOINT_DB=/app/data/checkpoints.db
```

#### 方案 2：改用 PostgresSaver（生产级，本项目暂不需要）

如果未来需要多实例部署或更高并发，可以引入 PostgreSQL：

```python
from langgraph.checkpoint.postgres import PostgresSaver

def _get_memory():
    global _memory
    if _memory is None:
        _memory = PostgresSaver.from_conn_string(
            "postgresql://user:pass@postgres:5432/langgraph"
        )
    return _memory
```

**本项目建议**：当前是学习项目，单机部署，**SqliteSaver 足够**。等真正需要多实例时再升级到 PostgresSaver。

#### 两个方案都需要注意的细节

1. **每个 Agent 服务用独立的数据库文件或表**，避免会话冲突：
   ```python
   # rag_agent_service.py → checkpoints_rag.db
   # manual_agent_service.py → checkpoints_manual.db
   # mcp_agent_service.py → checkpoints_mcp.db
   # aiops_service.py → checkpoints_aiops.db
   ```

2. **Docker 中 SQLite 文件并发写入问题**：SQLite 对并发写入支持有限，
   如果有多个请求同时写同一个文件可能锁库。单实例部署没问题，多实例需要换 Postgres。

3. **定期清理过期会话**：MemorySaver 重启自动清空，换成持久化存储后需要自己管。
   可以加一个定时任务清理超过 N 天的 thread_id 记录。

---

## 经验总结

### 教训 1：「能跑」不等于「没 Bug」

手动 Agent 模式和报错的三个模式用了同一个 `trim_conversation_history` 函数，但手动模式「正常」——只是因为触发条件没满足（对话轮数不够）。这提醒我们：

- **共用代码 = 共用 Bug**：一个函数被多处调用，Bug 也会被多处继承
- **没触发 ≠ 不存在**：测试覆盖的场景不代表所有场景
- **边界条件是 Bug 重灾区**：滑动窗口的边界、空列表、首尾元素，这些地方最容易出问题

### 教训 2：开发环境掩盖了部署问题

本地开发时服务频繁重启，`MemorySaver` 不断清空，对话历史永远很短，修剪逻辑根本不会被触发。这导致一个严重的部署 Bug 在开发阶段完全 invisible。

**对策**：
- 开发时也要模拟「长时间运行」场景：连续对话 30+ 轮，验证修剪逻辑
- 部署前在类生产环境（持续运行、不重启）做集成测试
- 对所有「有上限阈值」的逻辑（如 `max_messages=20`）做边界测试

### 教训 3：理解协议规范比记 API 更重要

这个 Bug 的根因是违反了 OpenAI Chat Completions API 的消息序列规范：

> `assistant` 消息如果带 `tool_calls`，后续**必须**跟对应的 `tool` 消息。

DashScope 用的是 OpenAI 兼容接口，自然也遵守这个规范。理解了这个规范，就能预见到「消息修剪可能破坏配对关系」这个风险点。

**对策**：
- 用第三方 API 时，先读它的消息格式规范，理解约束条件
- 特别关注「必须」「不能」「顺序」这类硬性约束
- 这些约束就是 Bug 的温床

### 教训 4：自愈降级要兜底，但不能掩盖问题

项目有「自愈降级」设计（MCP 挂了返回空列表），这个设计很好。但消息修剪的 Bug 没有被自愈逻辑兜住——修剪后的消息直接发给 LLM API，API 返回 400，异常冒泡到服务层，用户看到错误提示。

这说明：**自愈降级覆盖的是外部依赖，不是自身逻辑 Bug**。自身的逻辑错误（如消息序列不合法）没法自愈，只能靠严谨的代码和测试预防。

### 排查方法论复盘

这次排查的思路链条，可以复用到以后的 Bug：

```
1. 读报错信息，提取关键词
   → "tool_calls must be followed by tool messages"
   → 关键词：tool_calls、tool messages、followed by（顺序）

2. 关键词对应到概念
   → tool_calls = AIMessage 的属性
   → tool messages = ToolMessage
   → followed by = 消息序列顺序约束

3. 问：什么操作会破坏消息序列顺序？
   → 消息修剪（滑动窗口裁剪）
   → 定位到 trim_conversation_history 函数

4. 对比「报错的」和「不报错的」有什么区别？
   → 四种模式中只有手动 Agent 不报错
   → 但手动 Agent 也用了同一个修剪函数
   → 推断：不报错只是没触发，不是没 Bug

5. 问：为什么云服务器才触发，本地不触发？
   → 差异：服务运行时长、MemorySaver 累积
   → 本地重启清空内存，云上持续累积
   → 累积超过 20 条 → 触发修剪 → 暴露 Bug

6. 验证根因
   → 读修剪函数代码，确认边界处理有遗漏
   → 构造测试场景，确认能复现
```

**核心原则**：Bug 排查的本质是「差异分析」——找到报错和不报错之间的差异，那个差异就是线索。

---

## 修复清单

| # | 问题 | 文件 | 方案 | 状态 |
|---|------|------|------|:----:|
| 1 | 消息修剪破坏 tool_calls 配对 | `app/core/message_trimmer.py` | 补全边界处理 + 兜底校验函数 + Middleware 抽取 | ✅ 已修复 |
| 2 | 对话记忆用内存存储 | 4 个 service + `app/core/checkpoint.py` | SqliteSaver（公共模块 + 独立 db 文件 + Docker volume） | ✅ 已修复 |
| 3 | AIOps 诊断模式报错待确认 | `app/agent/aiops/executor.py` | 需确认报错信息是否一致 | ⏳ 待确认 |

### 修复详情（2026-07-22）

**Bug #1 修复**（`app/core/message_trimmer.py`）：
- 修复 `trim_conversation_history`：增加删除开头孤立 `AIMessage(tool_calls)` 的逻辑（与原有删孤立 `ToolMessage` 对称）
- 新增 `validate_message_sequence` 兜底校验函数：修剪后扫一遍消息序列，发现非法配对记 warning 日志
- 抽取 `MessageTrimmerMiddleware` 到 `message_trimmer.py`，消除 rag/mcp 中的重复定义
- 新增 10 个单元测试覆盖核心 Bug 场景

**Bug #2 修复**（`app/core/checkpoint.py` + 4 个 service）：
- 新建公共 `app/core/checkpoint.py`，提供 `get_checkpointer(agent_name)` 工厂函数
- 4 个 service 统一改用 `get_checkpointer()`，删除各自的 `_get_memory()` 重复代码
- 每个 Agent 独立 db 文件（`checkpoints_rag.db` / `checkpoints_mcp.db` 等）
- `SqliteSaver` + `check_same_thread=False` + `setup()` 自动建表
- Docker 挂载 `checkpoint_data` volume，重启不丢对话历史
- 新增 3 个 checkpoint 单元测试

**配套更新**：`pyproject.toml`（+依赖 + dev 依赖 + pytest 配置）、`config.py`（+checkpoint_dir）、`.env.example`、`.gitignore`、`docker-compose.yml`

---

> 本文档会持续更新。每次遇到新 Bug，按相同格式（现象 → 根因 → 修复 → 教训）追加记录。
