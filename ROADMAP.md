# AIOperator 多用户化改进方案

> 版本：v1.0  
> 日期：2026-07-24  
> 作者：架构规划（AI 辅助）  
> 状态：待评审

---

## 目录

- [一、现状分析](#一现状分析)
- [二、第三方 OAuth 方案科普](#二第三方-oauth-方案科普)
- [三、技术选型](#三技术选型)
- [四、架构方案](#四架构方案)
- [五、安全方案（重点）](#五安全方案重点)
- [六、开发阶段计划](#六开发阶段计划)
- [七、风险与注意事项](#七风险与注意事项)

---

## 一、现状分析

### 1.1 当前架构总览

```
浏览器 (localStorage 存 session)
    │
    ▼
FastAPI :9900
    ├── /api/chat        → RAG Agent    (create_agent + 本地工具)
    ├── /api/agent/chat  → 手动 Agent   (StateGraph + ToolNode)
    ├── /api/aiops       → AIOps 诊断   (Plan-Execute-Replan)
    ├── /api/mcp/chat    → MCP Agent    (本地工具 + MCP 远程工具)
    ├── /api/upload      → 文档上传
    └── /api/title       → 会话标题生成
    │
    ├── Agent 记忆: SQLite (data/checkpoints_{agent}.db)
    ├── 前端消息:   localStorage (浏览器本地)
    │
    └── MCP 客户端 ──── HTTP ────┬── Time Server   :8003
                                  ├── DB Server     :8004  → MySQL
                                  ├── PPT Server    :8005
                                  ├── Docker Server :8006  → Docker Daemon
                                  └── Search Server :8007  → Tavily/DuckDuckGo
```

### 1.2 核心问题清单

| # | 问题 | 严重度 | 影响面 |
|---|------|:------:|--------|
| 1 | **无用户认证** — 任何人访问 URL 即可使用，session_id 由前端随机生成 | P0 | 全局 |
| 2 | **无会话隔离** — 知道别人的 session_id 就能看对话历史 | P0 | 安全 |
| 3 | **MCP Server 无认证** — 5 个服务端口裸跑，Shell/Docker/DB 操作全暴露 | P0 | 安全 |
| 4 | **对话存储零散** — localStorage + SQLite + MemorySaver 三层各存各的 | P1 | 数据一致性 |
| 5 | **20 条消息截断硬编码** — 按条数而非 token 数裁剪，体验不好 | P1 | 用户体验 |
| 6 | **前端单文件 2200+ 行** — 无模块化，后续功能迭代困难 | P1 | 可维护性 |
| 7 | **无流控** — 无 rate limit，无请求队列，多用户并发会打穿 LLM API | P1 | 稳定性 |
| 8 | **无测试** — 虽然配了 pytest 但没有实际用例 | P2 | 质量 |
| 9 | **日志非结构化** — 字符串拼接，不方便接入日志平台 | P2 | 运维 |
| 10 | **无多环境配置** — dev/staging/prod 混在 .env | P2 | 工程化 |

### 1.3 现有可用资产

已具备、可直接复用的能力：

- `app/core/checkpoint.py` — 已抽象为 `get_checkpointer(agent_name)` 工厂，切换存储后端只需改一处
- `mcp_servers/db_server.py` — 已有 `DB_BLACKLIST_TABLES` 黑名单机制（`.env` 中配置），可直接用于隔离用户表
- `app/core/exceptions.py` — 已有 6 类异常子类，三层异常处理体系完整
- `app/config.py` — 基于 pydantic-settings，新增配置项只需加字段
- `CLAUDE.md` — 项目规范文档完整，AI 辅助开发有章可循

---

## 二、第三方 OAuth 方案科普

### 2.1 什么是 OAuth

OAuth 2.0 是一种**授权协议**，允许用户在不暴露密码的情况下，授权第三方应用访问自己在某个平台（如 GitHub、微信）上的身份信息。

通俗类比：你去酒店入住，前台不需要你的身份证密码，而是让公安系统发一个临时凭证，证明"这人确实是他本人"。

### 2.2 工作流程（以 GitHub OAuth 为例）

```
用户                        AIOperator                      GitHub
 │                              │                              │
 │  ① 点击「GitHub 登录」      │                              │
 │─────────────────────────────>│                              │
 │                              │  ② 重定向到 GitHub 授权页    │
 │<───────────────────────────────────────────────────────────│
 │  ③ 用户确认授权              │                              │
 │────────────────────────────────────────────────────────────>│
 │                              │  ④ GitHub 发来临时 code      │
 │                              │<─────────────────────────────│
 │                              │  ⑤ 用 code 换 access_token   │
 │                              │──────────────────────────────>│
 │                              │  ⑥ 返回 access_token         │
 │                              │<──────────────────────────────│
 │                              │  ⑦ 用 token 查用户信息       │
 │                              │──────────────────────────────>│
 │                              │  ⑧ 返回用户名/邮箱/头像      │
 │                              │<──────────────────────────────│
 │  ⑨ 登录成功，返回 JWT       │                              │
 │<─────────────────────────────│                              │
```

### 2.3 三种方案对比

| 方案 | 用户体验 | 开发成本 | 适用场景 |
|------|:--:|:--:|------|
| **纯密码登录**（邮箱+密码） | 需注册，一般 | 低 | 内部系统、小团队 |
| **GitHub OAuth** | 一键登录，好 | 中 | 面向开发者产品 |
| **微信 OAuth** | 扫码登录，国内用户友好 | 高（需企业认证） | 面向大众产品 |
| **OAuth + 密码双模式** | 两个入口，最好 | 中高 | 通用产品 |

### 2.4 本项目的推荐策略

**短期（阶段一）**：纯密码登录（邮箱 + bcrypt 加密密码 + JWT Token），开发成本最低。

**中期（阶段二）**：增加 GitHub OAuth，技术用户一键登录。

**长期**：可扩展微信扫码登录（需要微信开放平台企业资质）。

双模式不互斥，可以用同一张 `users` 表，通过 `auth_provider` 字段区分：

```
users 表:
  id, username, email, password_hash (可为 NULL), 
  auth_provider (local / github / wechat),
  provider_user_id (可为 NULL),  -- OAuth 平台的用户 ID
  avatar_url, created_at, last_login_at
```

---

## 三、技术选型

### 3.1 总览

| 层 | 选型 | 理由 |
|----|------|------|
| **认证** | JWT (python-jose) + bcrypt (passlib) | 无状态、轻量、无需 Redis |
| **OAuth** | GitHub OAuth App (httpx 对接) | 免费、无需企业认证、面向开发者 |
| **用户存储** | MySQL `users` 表 | 复用现有 MySQL，减少组件 |
| **会话存储** | MySQL 替换 SQLite | 统一数据源、支持按 user_id 查询 |
| **前端** | 保持 Vue 3 CDN + 拆模块为多个 JS 文件 | 不引入构建工具，保持简单 |
| **API 鉴权** | FastAPI Depends + 中间件注入 `current_user` | FastAPI 原生依赖注入 |
| **MCP 安全** | 共享 Secret Token（.env 配置） | 内网部署足够，不引入 mTLS 复杂度 |
| **流控** | slowapi (基于 Flask-Limiter 的 FastAPI 版) | 轻量、内存存储、单机够用 |
| **日志** | loguru → 结构化 JSON 输出 | 不换库，只改 format |
| **配置** | pydantic-settings .env 多文件 | 不引入新工具 |
| **测试** | pytest + pytest-asyncio (已有) | 不增加新依赖 |

### 3.2 选型理由详述

**为什么用 MySQL 替换 SQLite 存会话？**
- 你已有 MySQL，不需要新组件
- 用户表、会话表可以 JOIN 查询
- Docker 部署时 MySQL 已有 volume 持久化
- 后续如果用户量大，MySQL → PostgreSQL 迁移成本低（都是关系型）

**为什么不用 Redis？**
- 单用户量级不需要
- JWT 无状态，不需要服务端存 session
- 引入新组件增加运维复杂度
- 等日活用户破百再考虑

**为什么 MCP Server 用共享 Secret 而不是 OAuth2 Proxy？**
- 5 个 MCP Server 按微服务部署在同一 Docker 网络内（或同一台机器）
- 共享 Secret 足够，复杂度低
- 如果未来需要对外暴露 MCP，再加 mTLS

---

## 四、架构方案

### 4.1 目标架构

```
┌─────────────────────────────────────────────────────┐
│                   前端 (Vue 3 CDN)                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ login.js │  │ app.js   │  │ chat/aiops/mcp/  │  │
│  │ 登录/注册 │  │ 主逻辑   │  │ upload/*.js      │  │
│  └──────────┘  └──────────┘  └──────────────────┘  │
│                        │                             │
│         Authorization: Bearer <JWT>                  │
└────────────────────────┼────────────────────────────┘
                         │
┌────────────────────────┼────────────────────────────┐
│                 FastAPI :9900                         │
│                                                       │
│  ┌─────────────────────────────────────────────┐    │
│  │          Auth 中间件 (全局)                    │    │
│  │  1. 提取 Authorization header                │    │
│  │  2. 验证 JWT → 解析 user_id                  │    │
│  │  3. 注入 current_user 到 request.state       │    │
│  └─────────────────────────────────────────────┘    │
│                                                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐  │
│  │ /api/auth│ │/api/chat │ │/api/agent│ │/api/   │  │
│  │ 登录注册  │ │          │ │          │ │ mcp等  │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └───┬────┘  │
│       │             │             │            │      │
│       │     thread_id = f"{user_id}:{session_id}"     │
│       │             │             │            │      │
│  ┌────┴─────────────┴─────────────┴────────────┴──┐  │
│  │              Services 层                         │  │
│  │  所有 session_id → 内部拼接 user_id 前缀         │  │
│  └────────────────────┬────────────────────────────┘  │
│                       │                               │
│  ┌────────────────────┴────────────────────────────┐  │
│  │            MySQL (统一存储)                       │  │
│  │  ┌─────────┐  ┌──────────┐  ┌───────────────┐  │  │
│  │  │ users   │  │ sessions │  │ checkpoint_*  │  │  │
│  │  └─────────┘  └──────────┘  └───────────────┘  │  │
│  └──────────────────────────────────────────────────┘  │
│                                                       │
│  ┌──────────────────────────────────────────────────┐  │
│  │         Rate Limiter (slowapi)                    │  │
│  │  /api/auth/*  → 10次/分钟 (防暴力破解)            │  │
│  │  /api/chat/*  → 30次/分钟/用户                    │  │
│  └──────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
                         │
     ┌───────────────────┼───────────────────┐
     ▼                   ▼                   ▼
MCP Server (8003-8007) — 均加 Secret Token 校验
```

### 4.2 核心设计决策

**决策 1：thread_id 改造方案（最小侵入）**

不改 LangGraph SDK 内部逻辑，只在传入时做一层包装：

```
前端传入:  session_id = "abc-123"
后端改造:  thread_id  = f"{user_id}:{session_id}"
```

即 config 变为：

```python
config = {"configurable": {"thread_id": f"{user_id}:{session_id}"}}
```

四个 Agent service 的 `query()` / `query_stream()` 入口各加一行拼接逻辑即可。LangGraph 的 checkpoint 内部天然支持任意字符串作为 thread_id，不需要改动框架代码。

**决策 2：对话历史前端存储 → 后端存储**

现状：聊天消息存在浏览器 `localStorage` 中，切换设备/清缓存则丢失。

改造：
- 新增 `sessions` 表（MySQL），建联合索引 `(user_id, session_id)`
- 新增 `messages` 表，用户对话消息持久化到 MySQL
- 前端仍然缓存最近 N 条（加速首屏渲染），但以服务端为准

**决策 3：前端 JS 拆分策略**

不引入 webpack/vite（保持项目简单），采用 ES Module 方式拆分：

```
static/
├── index.html
├── css/
│   └── styles.css
├── js/
│   ├── config.js        # API 地址、常量
│   ├── auth.js           # 登录/注册/Token 管理
│   ├── api.js            # HTTP 封装 (fetch + JWT 自动注入)
│   ├── components/
│   │   ├── chat.js       # 聊天组件
│   │   ├── sidebar.js    # 会话列表
│   │   ├── aiops.js      # 诊断面板
│   │   └── upload.js     # 文件上传
│   └── app.js            # 主入口，组装各模块
```

### 4.3 数据库表设计概要

**users 表**（新增）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT PK AUTO_INCREMENT | 用户ID |
| username | VARCHAR(50) UNIQUE | 用户名 |
| email | VARCHAR(100) UNIQUE | 邮箱（登录凭据） |
| password_hash | VARCHAR(255) | bcrypt 哈希后的密码 |
| auth_provider | ENUM('local','github') | 认证来源 |
| provider_user_id | VARCHAR(100) | OAuth 平台用户ID |
| avatar_url | VARCHAR(500) | 头像地址 |
| is_active | BOOLEAN | 是否启用 |
| created_at | DATETIME | 注册时间 |
| last_login_at | DATETIME | 最后登录时间 |

**sessions 表**（新增）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT PK AUTO_INCREMENT | |
| session_id | VARCHAR(36) | UUID，前端生成 |
| user_id | INT FK → users.id | 归属用户 |
| title | VARCHAR(100) | 会话标题 |
| agent_type | ENUM('rag','manual','mcp','aiops') | Agent 类型 |
| created_at | DATETIME | |
| updated_at | DATETIME | |

联合唯一索引：`(user_id, session_id)`

**messages 表**（新增，替代 localStorage）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT PK AUTO_INCREMENT | |
| session_id | INT FK → sessions.id | 归属会话 |
| role | ENUM('user','assistant','tool','system') | 消息角色 |
| content | TEXT | 消息内容 |
| tool_name | VARCHAR(100) | 工具名（role=tool 时） |
| created_at | DATETIME | |

**checkpoint 迁移**

当前 SQLite `data/checkpoints_{agent}.db` → MySQL `checkpoint_rag` / `checkpoint_mcp` / `checkpoint_manual` / `checkpoint_aiops` 四张表。LangGraph 的 `AsyncSqliteSaver` 替换为 `AsyncMySqlSaver`（或使用 LangGraph 官方 `PostgresSaver` 的 MySQL 适配版）。

> 备用方案：继续用 SQLite（每个用户一个 db 文件），MySQL 只存 users + sessions + messages。这是更简单的方案，且不会引入 LangGraph MySQL saver 的兼容问题。两种方案在开发阶段一末尾评估。

---

## 五、安全方案（重点）

### 5.1 用户密码安全

- 密码哈希：bcrypt (passlib)，cost factor = 12
- 密码规则：≥ 8 位，包含字母 + 数字
- 登录失败限制：同一邮箱 5 次失败后锁定 15 分钟（在 users 表加 `failed_attempts` + `locked_until` 字段）
- JWT 过期：access_token 24 小时，可选 refresh_token 7 天
- JWT secret：64 字节随机字符串，存在 `.env` 的 `JWT_SECRET_KEY`

### 5.2 API 鉴权流程

```
请求 → AuthMiddleware
        │
        ├── 路径在白名单？（/health, /api/auth/*, /docs, /static）
        │   ├── 是 → 放行
        │   └── 否 ↓
        │
        ├── Header 有 Authorization: Bearer <token>？
        │   ├── 否 → 401 {"detail": "未登录，请先登录"}
        │   └── 是 ↓
        │
        ├── JWT 解码成功？
        │   ├── 否 → 401 {"detail": "登录已过期，请重新登录"}
        │   └── 是 ↓
        │
        ├── user_id 对应的用户存在且 is_active=True？
        │   ├── 否 → 403 {"detail": "账号已被禁用"}
        │   └── 是 ↓
        │
        └── request.state.current_user = user → 进入业务逻辑
```

路由白名单：`/health`, `/docs`, `/openapi.json`, `/static`, `/api/auth/login`, `/api/auth/register`

### 5.3 MCP Server 安全加固

**问题**：5 个 MCP Server（8003-8007 端口）全是裸跑的，任何人都能直接调用。

**方案**：共享 Secret Token 校验

```
配置层：
  .env 中新增 MCP_SECRET_TOKEN=<64字节随机字符串>

请求链：
  main.py 启动 → 读 MCP_SECRET_TOKEN 
  mcp_server 启动 → 读 MCP_SECRET_TOKEN
  
  外部直接访问 :8004/mcp → Request header 无 Token → 403
  main.py → MCP Client → 自动注入 Token → 200
```

**实现方式**：
- MCP Server 侧：FastMCP 支持自定义路由中间件，加一个 `check_token` 钩子
- 主应用侧：`MCPClientManager` 在创建 `MultiServerMCPClient` 时通过 headers 参数注入 Token
- Docker 部署时 MCP Server 不映射端口到宿主机（只暴露主应用 9900），只有内网 Docker 网络可达

### 5.4 DB 工具安全（防止 AI 查询用户表）

**用户的担忧**：Agent 有 `execute_query` 工具可以读 MySQL，如果用户表（`users`、`sessions`）存在同一个库中，用户通过 AI 对话可能查到其他用户的信息。

**方案：四层防护，纵深防御**

**第一层：表级黑名单（已有）**

DB Server 现有的 `DB_BLACKLIST_TABLES` 环境变量，在 `.env` 中配置：

```bash
DB_BLACKLIST_TABLES=users,sessions,messages,checkpoint_rag,checkpoint_mcp,checkpoint_manual,checkpoint_aiops
```

- `list_tables()` → 直接隐藏黑名单表
- `describe_table()` → 拒绝访问黑名单表
- `execute_query()` → SQL 中包含黑名单表名则拒绝
- `get_row_count()` → 拒绝访问黑名单表

**第二层：行级隔离（新增）**

在 `execute_query` 的 SQL 执行前，自动注入 `WHERE` 条件。方法是拦截 SQL 语句，如果是查业务表，自动追加查询限制。

> 这一层不完整，因为用户可以自己写完整 SQL 覆盖。更稳妥的办法是：

**第三层：只读账号（推荐）**

在 MySQL 中创建一个**只读业务账号**，只给业务表的 SELECT 权限：

```sql
-- 创建只读用户（只能查业务库的业务表）
CREATE USER 'aioperator_readonly'@'%' IDENTIFIED BY 'readonly_password';
-- 授予业务表的 SELECT 权限（不包含 users/sessions/messages 等系统表）
GRANT SELECT ON aioperator.business_table_1 TO 'aioperator_readonly'@'%';
GRANT SELECT ON aioperator.business_table_2 TO 'aioperator_readonly'@'%';
-- users / sessions / messages 不授权 → 即使 SQL 写了也查不了
```

DB Server 用这个只读账号连接，**从数据库引擎层面屏蔽敏感表**，比黑名单可靠。

**第四层：审计日志**

DB Server 中所有 SQL 查询记录审计日志（JSON 格式），记录时间、SQL 内容、返回行数。用于：发现异常查询、追溯数据泄露。

---

## 六、开发阶段计划

### 阶段一：用户认证体系（预计 2-3 天）

**范围**：打通从登录到 API 鉴权的完整链路

**任务清单**：

- [ ] 1.1 MySQL 新增 `users` 表，执行建表 DDL
- [ ] 1.2 `app/config.py` 新增配置项：`JWT_SECRET_KEY`, `JWT_ALGORITHM`, `JWT_EXPIRE_HOURS`, `BCRYPT_ROUNDS`
- [ ] 1.3 `app/core/security.py` — JWT 生成/验证 + bcrypt 密码哈希/验证
- [ ] 1.4 `app/api/auth.py` — `/api/auth/register`（注册）、`/api/auth/login`（登录）、`/api/auth/me`（获取当前用户信息）
- [ ] 1.5 `app/core/auth_middleware.py` — 请求中间件，验证 JWT 并注入 `current_user`
- [ ] 1.6 四个 Agent API 的 `session_id` → `thread_id` 改造（拼接 user_id 前缀）
- [ ] 1.7 前端 `static/js/auth.js` — 登录/注册页面 + Token 管理（`localStorage` 存 JWT）
- [ ] 1.8 前端 `static/js/api.js` — 全局 `fetch` 封装，自动注入 `Authorization` header，401 时跳转登录页
- [ ] 1.9 手动测试：注册 → 登录 → 创建会话 → 切换会话 → 另一个浏览器登录看不到别人的会话

**产出物**：
- `app/core/security.py`
- `app/core/auth_middleware.py`
- `app/api/auth.py`
- `static/js/auth.js`, `static/js/api.js`
- 数据库 DDL: `users` 表

---

### 阶段二：会话 & 消息持久化迁移（预计 2 天）

**范围**：对话历史从 localStorage + SQLite → MySQL

**任务清单**：

- [ ] 2.1 MySQL 新增 `sessions` 表 + `messages` 表，执行建表 DDL
- [ ] 2.2 `app/services/session_service.py` — 会话 CRUD（创建、列表、删除、重命名）+ 按 user_id 隔离
- [ ] 2.3 `app/services/message_service.py` — 消息存取（新增、查询、按 session 拉取历史）
- [ ] 2.4 `app/api/session.py` — `/api/sessions` 路由（GET 列表、POST 创建、DELETE 删除）
- [ ] 2.5 前端改造：移除 localStorage 消息存取，改用 API 拉取历史消息
- [ ] 2.6 checkpoint 存储评估：决定继续 SQLite（每用户单文件）还是迁移到 MySQL
- [ ] 2.7 手动测试：创建多个会话 → 对话 → 刷新页面 → 历史还在 → 换浏览器登录 → 能看到自己的所有会话

**产出物**：
- `app/services/session_service.py`
- `app/services/message_service.py`
- `app/api/session.py`
- 数据库 DDL: `sessions` 表, `messages` 表

---

### 阶段三：MCP Server 安全加固（预计 1 天）

**范围**：5 个 MCP Server 加 token 校验

**任务清单**：

- [ ] 3.1 `app/config.py` 新增 `MCP_SECRET_TOKEN` 配置项
- [ ] 3.2 5 个 MCP Server 各加 `/health` 已有的基础上，对 `/mcp` 端点加 token 校验中间件
- [ ] 3.3 `app/agent/mcp_client.py` — `_build_mcp_servers()` 中为每个 server 注入 `headers: {"Authorization": "Bearer <token>"}`
- [ ] 3.4 更新 `docker-compose.yml`：MCP Server 不映射端口到宿主机（仅保留 app:9900），或映射到 `127.0.0.1` 仅本机访问
- [ ] 3.5 更新 `.env.example` 加 `MCP_SECRET_TOKEN`
- [ ] 3.6 DB Server 安全加固：新增只读 MySQL 账号方案，更新黑名单配置
- [ ] 3.7 手动测试：curl 直接访问 :8004/mcp → 403；通过 Agent 对话正常使用数据库工具

**产出物**：
- 5 个 MCP Server 的 token 校验逻辑
- `docker-compose.yml` 安全更新
- MySQL 只读账号创建脚本

---

### 阶段四：流控 & 并发保护（预计 1 天）

**范围**：防止 API 被刷、保护 LLM API 调用

**任务清单**：

- [ ] 4.1 `pyproject.toml` 加 `slowapi` 依赖
- [ ] 4.2 `app/core/rate_limiter.py` — slowapi 初始化 + 自定义限流策略
- [ ] 4.3 配置限流规则：
  - `/api/auth/*` → 10 次/分钟/IP
  - `/api/chat/*` → 30 次/分钟/用户
  - `/api/aiops` → 5 次/分钟/用户（诊断耗时最长）
  - `/api/upload` → 10 次/分钟/用户
- [ ] 4.4 `app/services/llm_guard.py` — LLM 调用队列（同一用户最多 3 个并发请求排队）
- [ ] 4.5 错误响应标准化：429 Too Many Requests + 返回 Retry-After header

**产出物**：
- `app/core/rate_limiter.py`
- `app/services/llm_guard.py`

---

### 阶段五：前端模块化拆分（预计 1.5 天）

**范围**：`app.js` (当前 2200+ 行) 拆分为多个 JS 文件

**任务清单**：

- [ ] 5.1 建立前端文件结构：`static/js/config.js`, `static/js/api.js`, `static/js/auth.js`, `static/js/components/`
- [ ] 5.2 从 `app.js` 中提取 API 调用逻辑 → `api.js`
- [ ] 5.3 从 `app.js` 中提取配置常量 → `config.js`
- [ ] 5.4 从 `app.js` 中提取聊天组件 → `components/chat.js`
- [ ] 5.5 从 `app.js` 中提取诊断组件 → `components/aiops.js`
- [ ] 5.6 从 `app.js` 中提取会话侧边栏 → `components/sidebar.js`
- [ ] 5.7 从 `app.js` 中提取文件上传组件 → `components/upload.js`
- [ ] 5.8 更新 `index.html` 的 `<script>` 引入顺序
- [ ] 5.9 功能回归测试：四种模式对话、会话管理、文件上传

**产出物**：
- 前端模块化目录结构
- 多个 JS 组件文件

---

### 阶段六：GitHub OAuth 登录（预计 1 天）

**范围**：在密码登录基础上增加 GitHub OAuth 入口

**任务清单**：

- [ ] 6.1 `app/config.py` 新增 `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_REDIRECT_URI`
- [ ] 6.2 `app/api/auth.py` 新增 `/api/auth/github/login`（重定向到 GitHub 授权页）、`/api/auth/github/callback`（处理回调）
- [ ] 6.3 前端登录页增加「使用 GitHub 登录」按钮
- [ ] 6.4 GitHub OAuth App 注册指南写到 README

**产出物**：
- GitHub OAuth API 端点
- 前端 GitHub 登录按钮

---

### 阶段七：工程化 & 质量（预计 1.5 天）

**范围**：测试覆盖 + 结构化日志 + 多环境配置

**任务清单**：

- [ ] 7.1 多环境配置：`.env.example` 模板 + `.env.dev` / `.env.prod` 示例
- [ ] 7.2 `app/core/config.py` 支持 `APP_ENV` 环境变量切换配置文件
- [ ] 7.3 结构化日志：loguru 输出 JSON 格式（保留控制台彩色输出）
- [ ] 7.4 `tests/` 目录补充：
  - `tests/test_security.py` — JWT 生成/验证 + bcrypt 哈希
  - `tests/test_auth.py` — 注册/登录 API 测试
  - `tests/test_session.py` — 会话隔离测试（用户A查不到用户B的会话）
- [ ] 7.5 DB Server 审计日志：所有 SQL 查询记录到 JSON 日志文件

**产出物**：
- 多环境配置
- JSON 日志格式
- 测试用例（至少覆盖认证 + 会话隔离）

---

## 七、风险与注意事项

### 7.1 技术风险

| 风险 | 等级 | 缓解措施 |
|------|:--:|------|
| LangGraph MySQLSaver 无官方支持 | 中 | 阶段性评估，备选继续 SQLite（每用户一个文件） |
| `langchain.agents.create_agent` API 变更 | 中 | 已在全局用 `0.3.x` 锁定版本，不随意升级 |
| 前端 ES Module 在 CDN Vue 3 环境下的兼容性 | 低 | Vue 3 CDN 版支持 ES Module，已验证 |
| JWT secret 泄露 | 低 | 64 字节随机生成，仅存在 `.env`，不提交 git |
| MCP Server Token 泄露 | 低 | 仅 Docker 内网可达，Token 存在 `.env` |

### 7.2 开发注意事项

1. **向后兼容**：所有 API 的 `session_id` 参数保持必填但允许默认值，不破坏现有前端
2. **渐进式迁移**：每个阶段完成后独立可测试，不依赖后续阶段
3. **数据库变更**：DDL 脚本单独存放（`migrations/` 目录），按序号命名（`001_create_users.sql`, `002_create_sessions.sql` ...）
4. **不破坏现有功能**：每完成一个阶段，都要回归测试四种 Agent 模式的对话功能
5. **遵循 CLAUDE.md 规范**：不用 poetry/uv，不用其他日志库，不修改异常类层次，MCP Server 不 import app.config

### 7.3 如果只能做一件事

如果时间极度有限，**只做阶段一（用户认证）**。它提供的价值最大——至少有了用户区分，每个人只能看到自己的对话。其他问题（存储零散、前端混乱）可以慢慢迭代。

---

## 附录

### A. 涉及文件清单（全阶段）

```
新增文件：
  app/core/security.py           # JWT + bcrypt
  app/core/auth_middleware.py    # 请求鉴权中间件
  app/core/rate_limiter.py       # 流控
  app/api/auth.py                # 注册/登录 API
  app/api/session.py             # 会话管理 API
  app/services/session_service.py # 会话 CRUD
  app/services/message_service.py # 消息存取
  app/services/llm_guard.py      # LLM 请求队列
  static/js/config.js            # 前端配置
  static/js/api.js               # 前端 HTTP 封装
  static/js/auth.js              # 前端登录模块
  static/js/components/chat.js   # 聊天组件
  static/js/components/sidebar.js# 侧边栏组件
  static/js/components/aiops.js  # 诊断组件
  static/js/components/upload.js # 上传组件
  migrations/                    # DDL 脚本目录
  tests/test_security.py
  tests/test_auth.py
  tests/test_session.py

修改文件：
  app/config.py                  # +JWT/OAuth/MCP_SECRET 配置项
  app/main.py                    # +Auth 中间件 + Rate limiter
  app/api/chat.py                # thread_id 拼接 user_id
  app/api/agent.py               # 同上
  app/api/mcp.py                 # 同上
  app/api/aiops.py               # 同上
  app/services/rag_agent_service.py    # 同上
  app/services/manual_agent_service.py # 同上
  app/services/mcp_agent_service.py    # 同上
  app/services/aiops_service.py        # 同上
  app/agent/mcp_client.py        # +Token 注入
  mcp_servers/time_server.py     # +Token 校验
  mcp_servers/db_server.py       # +Token 校验 + 审计日志
  mcp_servers/ppt_server.py      # +Token 校验
  mcp_servers/docker_server.py   # +Token 校验
  mcp_servers/search_server.py   # +Token 校验
  docker-compose.yml             # -MCP 宿主机端口映射
  pyproject.toml                 # +slowapi 依赖
  .env.example                   # +新增环境变量
  static/index.html              # <script> 引入调整
  static/app.js                  # 拆分后变瘦，只留主入口
```
