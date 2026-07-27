# AIOperator 多用户化改进方案

> 版本：v2.1
> 日期：2026-07-27
> 作者：架构规划（AI 辅助）
> 状态：待评审

---

## 目录

- [一、现状分析](#一现状分析)
- [二、GitHub OAuth 方案](#二github-oauth-方案)
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
| 6 | **前端架构简陋** — Vue 3 CDN 单文件 484 行，逻辑和模板混在 setup() 里，无组件化、无路由 | P1 | 可维护性 |
| 7 | **无流控** — 无 rate limit，无请求队列，多用户并发会打穿 LLM API | P1 | 稳定性 |
| 8 | **无可观测性** — Agent 调用链、工具调用、Token 用量全黑盒，排查问题靠猜 | P0 | 运维 |
| 9 | **无测试** — 虽然配了 pytest 但没有实际用例 | P2 | 质量 |
| 10 | **日志非结构化** — 字符串拼接，不方便接入日志平台 | P2 | 运维 |
| 11 | **无多环境配置** — dev/staging/prod 混在 .env | P2 | 工程化 |

### 1.3 现有可用资产

已具备、可直接复用的能力：

- `app/core/checkpoint.py` — 已抽象为 `get_checkpointer(agent_name)` 工厂，切换存储后端只需改一处
- `mcp_servers/db_server.py` — 已有 `DB_BLACKLIST_TABLES` 黑名单机制（`.env` 中配置），可直接用于隔离用户表
- `app/core/exceptions.py` — 已有 6 类异常子类，三层异常处理体系完整
- `app/config.py` — 基于 pydantic-settings，新增配置项只需加字段
- `CLAUDE.md` — 项目规范文档完整，AI 辅助开发有章可循
- `static/app.js` — 484 行 Vue 3 Composition API，功能完整可迁移

---

## 二、GitHub OAuth 方案

### 2.1 工作流程

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

### 2.2 为什么只用 GitHub OAuth

| 考量 | 决策 |
|------|------|
| **用户群** | 本项目面向开发者/运维工程师，GitHub 账号人手一个 |
| **安全性** | 不存储密码 → 没有密码泄露风险。登录安全由 GitHub 保障（2FA、异常检测） |
| **维护成本** | 不维护密码策略（强度、过期、重置），零运维负担 |
| **免费** | GitHub OAuth App 完全免费，无需企业认证 |

### 2.3 users 表设计

```
users 表:
  id              INT PK AUTO_INCREMENT
  username        VARCHAR(100)    — GitHub 用户名（login）
  email           VARCHAR(200)    — GitHub 主邮箱（唯一，可选）
  github_id       INT UNIQUE      — GitHub 用户数字 ID
  avatar_url      VARCHAR(500)    — GitHub 头像 URL
  is_active       BOOLEAN         — 管理员可禁用用户
  created_at      DATETIME        — 首次登录时间
  last_login_at   DATETIME        — 最近登录时间
```

> JWT payload 携带 user_id + username + is_active，中间件不查 DB（无状态验证）。
> GitHub access_token 不存储，OAuth 回调阶段用完即弃。

---

## 三、技术选型

### 3.1 总览

| 层 | 选型 | 理由 |
|----|------|------|
| **认证** | GitHub OAuth + JWT (PyJWT) | GitHub 账号认证，JWT 无状态会话，payload 携带用户信息 |
| **用户存储** | MySQL `users` 表 | 复用现有 MySQL，减少组件 |
| **会话/消息存储** | MySQL `sessions` + `messages` 表 | 统一数据源、支持按 user_id JOIN |
| **前端** | **Vite + Vue 3 SPA**（.vue 单文件组件 + Vue Router） | 真正的组件化开发，HMR 热更新，TypeScript 可选 |
| **前端工程化** | Node.js + npm | Vite 构建，开发代理到 FastAPI |
| **API 鉴权** | FastAPI Depends + 中间件注入 `current_user` | FastAPI 原生依赖注入 |
| **MCP 安全** | 共享 Secret Token（.env 配置） | 内网部署足够，不引入 mTLS 复杂度 |
| **可观测性** | **LangSmith**（LangChain 官方平台） | 自动追踪 Agent 调用链、工具调用、Token 用量、延迟 |
| **流控** | slowapi | 轻量、内存存储、单机够用 |
| **日志** | loguru → 结构化 JSON 输出 | 不换库，只改 format |
| **配置** | pydantic-settings .env 多文件 | 不引入新工具 |
| **测试** | pytest + pytest-asyncio (已有) | 不增加新依赖 |

### 3.2 选型理由详述

**为什么用 GitHub OAuth 而不是密码登录？**
- 目标用户是开发者，人人都有 GitHub 账号
- 不存储密码 → 不存在密码泄露、暴力破解等安全风险
- 开发量少（不需要注册页、密码重置、邮箱验证）

**为什么用 Vue SPA（Vite）而不是 CDN Vue？**
- CDN 版 Vue 只是"能用"，不适合长期迭代。单文件 484 行全堆在一个 setup() 里
- Vite 提供 HMR 热更新（改代码浏览器无需刷新重载）
- .vue 单文件组件让模板/样式/逻辑聚合，三个功能各得其所
- Vue Router 支持多页面（登录页 / 主页面），无需跳转独立 HTML
- Vite 开发代理（5173 → 9900）避免跨域问题
- 生产构建后 `dist/` 由 FastAPI 直接 serve

**为什么引入 LangSmith？**
- 当前 Agent 调用链完全黑盒：LLM 调了几次、每次用了多少 Token、工具调用耗时多少——全部不知道
- LangSmith 是 LangChain 官方可观测性平台，和 LangGraph/LangChain 零摩擦集成
- 免费额度够用（3000 trace/月），个人项目不计成本
- 接入只需要 3 个环境变量，不改代码

---

## 四、架构方案

### 4.1 目标架构

```
┌─────────────────────────────────────────────────────┐
│              前端 (Vite + Vue 3 SPA)                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │LoginPage │  │ MainPage │  │ 各功能组件        │  │
│  │ 登录页    │  │ 主页面   │  │ ChatPanel        │  │
│  │          │  │          │  │ Sidebar          │  │
│  │          │  │          │  │ AIOpsPanel       │  │
│  │          │  │          │  │ ModeSwitcher     │  │
│  │          │  │          │  │ Uploader         │  │
│  └──────────┘  └──────────┘  └──────────────────┘  │
│                        │                             │
│    开发: Vite 代理 5173 → FastAPI 9900               │
│    生产: FastAPI 直接 serve dist/                     │
│         Authorization: Bearer <JWT>                  │
└────────────────────────┼────────────────────────────┘
                         │
┌────────────────────────┼────────────────────────────┐
│                 FastAPI :9900                         │
│                                                       │
│  ┌─────────────────────────────────────────────┐    │
│  │          Auth 中间件 (Depends)                │    │
│  │  1. 提取 Authorization header                │    │
│  │  2. 验证 JWT → 从 payload 解析用户信息        │    │
│  │  3. 注入 current_user                        │    │
│  └─────────────────────────────────────────────┘    │
│                                                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐  │
│  │ /api/auth│ │/api/chat │ │/api/agent│ │/api/   │  │
│  │ GitHub OAuth│          │ │          │ │ mcp等  │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └───┬────┘  │
│       │             │             │            │      │
│       │     thread_id = f"{user_id}:{session_id}"     │
│       │             │             │            │      │
│  ┌────┴─────────────┴─────────────┴────────────┴──┐  │
│  │              Services 层                         │  │
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
│  │    Rate Limiter (slowapi) + LLM Guard            │  │
│  └──────────────────────────────────────────────────┘  │
│                                                       │
│  ┌──────────────────────────────────────────────────┐  │
│  │         LangSmith Tracing                        │  │
│  └──────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
                         │
     ┌───────────────────┼───────────────────┐
     ▼                   ▼                   ▼
MCP Server (8003-8007) — 均加 Secret Token 校验
```

### 4.2 核心设计决策

**决策 1：thread_id 改造方案（最小侵入）**

```python
config = {"configurable": {"thread_id": f"{user_id}:{session_id}"}}
```

API 层拼接，Service 层无感知。LangGraph checkpoint 天然支持任意 thread_id 字符串。

**决策 2：对话历史前端存储 → 后端存储**

- 新增 `sessions` 表（MySQL），联合唯一索引 `(user_id, session_id)`
- 新增 `messages` 表，按 session 拉取历史
- 前端不再用 localStorage 存消息（仅保留 JWT token）

**决策 3：前端从 CDN Vue → Vite Vue SPA**

```
旧:  static/index.html + app.js (CDN Vue, 484 行单文件)
新:  frontend/ (Vite + Vue 3 SFC + Vue Router)
       ├── src/
       │   ├── App.vue
       │   ├── main.js
       │   ├── router/
       │   ├── pages/
       │   │   ├── LoginPage.vue
       │   │   └── MainPage.vue
       │   ├── components/
       │   │   ├── ChatPanel.vue
       │   │   ├── Sidebar.vue
       │   │   ├── AIOpsPanel.vue
       │   │   ├── ModeSwitcher.vue
       │   │   └── Uploader.vue
       │   └── utils/
       │       ├── api.js
       │       └── auth.js
       ├── vite.config.js
       └── package.json

FastAPI 改动:
  - 开发环境: 不服务前端（Vite 自己做）
  - 生产环境: app.mount("/", StaticFiles(directory="frontend/dist"))
```

### 4.3 数据库表设计概要

**users 表**（新增）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT PK AUTO_INCREMENT | 用户ID |
| username | VARCHAR(100) NOT NULL | GitHub 用户名（login） |
| email | VARCHAR(200) UNIQUE | GitHub 公开邮箱（可选） |
| github_id | INT UNIQUE NOT NULL | GitHub 用户数字 ID |
| avatar_url | VARCHAR(500) | GitHub 头像 URL |
| is_active | BOOLEAN DEFAULT TRUE | 管理员可禁用 |
| created_at | DATETIME | 首次登录时间 |
| last_login_at | DATETIME | 最近登录时间 |

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

**messages 表**（新增）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INT PK AUTO_INCREMENT | |
| session_id | INT FK → sessions.id | 归属会话 |
| role | ENUM('user','assistant','tool','system') | 消息角色 |
| content | TEXT | 消息内容 |
| tool_name | VARCHAR(100) | 工具名（role=tool 时） |
| created_at | DATETIME | |

---

## 五、安全方案（重点）

### 5.1 认证安全

- **身份认证**：委托 GitHub OAuth，信任 GitHub 的身份验证体系（含 2FA、异常登录检测）
- **会话保持**：JWT access_token，24 小时过期，payload 携带 username + is_active（不查 DB）
- **JWT secret**：64 字节随机字符串，存在 `.env` 的 `JWT_SECRET_KEY`
- **GitHub access_token 处理**：OAuth callback 期间使用，用完即弃，不存储
- **CSRF 防护**：OAuth callback 使用 `state` 参数防 CSRF（随机字符串，httponly cookie）

### 5.2 API 鉴权流程

```
请求 → get_current_user (Depends)
        │
        ├── 路径在白名单？（/health, /docs, /openapi.json, /api/auth/github）
        │   ├── 是 → 放行，current_user = None
        │   └── 否 ↓
        │
        ├── Header 有 Authorization: Bearer <token>？
        │   ├── 否 → 401
        │   └── 是 ↓
        │
        ├── JWT 解码成功？
        │   ├── 否 → 401
        │   └── 是 ↓
        │
        ├── payload.is_active？
        │   ├── 否 → 403
        │   └── 是 ↓
        │
        └── return {id, username} → 进入业务逻辑
```

路由白名单：`/health`, `/docs`, `/openapi.json`, `/api/auth/github`

### 5.3 MCP Server 安全加固

- 5 个 MCP Server 校验 `Authorization: Bearer <MCP_SECRET_TOKEN>`
- `/health` 端点白名单放行
- Token 未配置时放行（向后兼容）
- MCP Client 在 `_build_mcp_servers()` 中自动注入 token
- Docker 部署时 MCP 端口绑定 `127.0.0.1`（不对外暴露）

### 5.4 DB 工具安全（四层防护）

1. **表级黑名单**：`DB_BLACKLIST_TABLES=users,sessions,messages`（list_tables 隐藏，execute_query 拒绝）
2. **SQL 白名单**：只允许 SELECT / SHOW / DESCRIBE / EXPLAIN
3. **只读账号**：DB Server 用独立的 MySQL 只读用户连接（无敏感表权限）
4. **审计日志**：所有 SQL 查询记录到 JSON 日志文件

---

## 六、开发阶段计划

### 阶段一：GitHub OAuth 认证体系 ✅ 已完成

### 阶段二：会话 & 消息持久化迁移

- [ ] 2.1 MySQL 新增 `sessions` 表 + `messages` 表
- [ ] 2.2 `app/services/session_service.py` — 会话 CRUD（按 user_id 隔离）
- [ ] 2.3 `app/services/message_service.py` — 消息存取
- [ ] 2.4 `app/api/session.py` — 会话管理 API
- [ ] 2.5 前端改造：从 localStorage 切换到 API 拉取

### 阶段三：MCP Server 安全加固

- [ ] 3.1 5 个 MCP Server 各加 TokenCheckMiddleware
- [ ] 3.2 `app/agent/mcp_client.py` — headers Token 注入
- [ ] 3.3 Docker Compose 端口绑定 127.0.0.1
- [ ] 3.4 `DB_BLACKLIST_TABLES=users,sessions,messages`

### 阶段四：流控 & 并发保护

- [ ] 4.1 slowapi 集成 + 限流规则
- [ ] 4.2 LLM 请求队列（单用户最多 3 并发）

### 阶段五：Vue SPA 前端迁移

**范围**：`static/` (CDN Vue) → `frontend/` (Vite + Vue 3 SFC + Vue Router)

**前端目录结构**：
```
frontend/
├── package.json
├── vite.config.js
├── index.html
└── src/
    ├── main.js              # createApp + router + mount
    ├── App.vue              # 根组件（router-view）
    ├── router/
    │   └── index.js         # /login → LoginPage, / → MainPage（需认证）
    ├── pages/
    │   ├── LoginPage.vue    # GitHub 登录页
    │   └── MainPage.vue     # 主页面（聊天 + 侧边栏布局）
    ├── components/
    │   ├── ChatPanel.vue    # 消息列表 + 输入框 + 流式渲染
    │   ├── Sidebar.vue      # 会话列表 + 新建/切换/删除
    │   ├── AIOpsPanel.vue   # 诊断确认弹窗 + SSE 进度
    │   ├── ModeSwitcher.vue # 四种 Agent 模式切换
    │   └── Uploader.vue     # 文件上传
    └── utils/
        ├── config.js        # 常量（API_BASE, JWT_KEY 等）
        ├── api.js           # fetch 封装（JWT 注入 + 401 处理）
        └── auth.js          # Token 管理 + 登录/退出
```

**任务清单**：
- [ ] 5.1 `npm create vite@latest frontend -- --template vue` 初始化项目
- [ ] 5.2 安装依赖：`vue-router`, `marked`, `highlight.js`
- [ ] 5.3 迁移 `static/js/config.js` → `src/utils/config.js`
- [ ] 5.4 迁移 `static/js/api.js` → `src/utils/api.js`
- [ ] 5.5 迁移 `static/js/auth.js` → `src/utils/auth.js` + Vue Router 导航守卫
- [ ] 5.6 创建 `LoginPage.vue`（从 `static/login.html` 迁移）
- [ ] 5.7 创建 `MainPage.vue`（布局容器：顶栏 + 侧边栏 + 聊天区）
- [ ] 5.8 创建 `Sidebar.vue`（从 `static/app.js` 提取会话管理逻辑）
- [ ] 5.9 创建 `ChatPanel.vue`（从 `static/app.js` 提取消息/流式/SSE 逻辑）
- [ ] 5.10 创建 `ModeSwitcher.vue`（四种 Agent 模式切换器）
- [ ] 5.11 创建 `AIOpsPanel.vue`（诊断弹窗 + SSE 进度）
- [ ] 5.12 创建 `Uploader.vue`（文件上传）
- [ ] 5.13 迁移 `static/styles.css` → 各 .vue 组件的 `<style scoped>`
- [ ] 5.14 配置 Vite 代理：`/api/*` → `http://127.0.0.1:9900`
- [ ] 5.15 修改 FastAPI：生产环境 serve `frontend/dist/`
- [ ] 5.16 更新 Dockerfile / docker-compose.yml（构建阶段 + Node.js）
- [ ] 5.17 清理旧 `static/` 目录（保留 styles.css 作为基础变量）
- [ ] 5.18 功能回归测试：四种模式对话、会话管理、文件上传、登录/退出

### 阶段六：LangSmith 可观测性集成

- [ ] 6.1 注册 LangSmith 账号 + 获取 API Key
- [ ] 6.2 配置环境变量（零代码接入）

### 阶段七：工程化 & 质量

- [ ] 7.1 多环境配置（APP_ENV）
- [ ] 7.2 loguru JSON 格式（可选切换）
- [ ] 7.3 tests: test_security.py, test_auth.py, test_session.py
- [ ] 7.4 DB Server 审计日志

---

## 七、风险与注意事项

### 7.1 技术风险

| 风险 | 等级 | 缓解措施 |
|------|:--:|------|
| GitHub OAuth API 限流 | 低 | 每小时 5000 次请求，个人使用完全够 |
| LangGraph MySQLSaver 无官方支持 | 低 | 继续 SQLite + thread_id 天然隔离 |
| `langchain.agents.create_agent` API 变更 | 中 | 锁定 `0.3.x` 版本，不随意升级 |
| JWT secret 泄露 | 低 | 64 字节随机生成，仅存在 `.env`，不提交 git |
| MCP Server Token 泄露 | 低 | 仅 Docker 内网可达，Token 存在 `.env` |
| LangSmith 免费额度不够 | 低 | 3000 trace/月，个人项目足够 |
| Vue SPA 迁移破坏现有功能 | 中 | 逐组件迁移，保持 API 接口不变，每个组件迁移后测试 |

### 7.2 Vue SPA 迁移策略

**分步迁移，不一次性替换**：
1. 先在 `frontend/` 建好空 Vite 项目 + 路由框架
2. 把 `LoginPage.vue` 写好（此时登录就能看到效果）
3. 逐个组件迁移：Sidebar → ChatPanel → ModeSwitcher → AIOpsPanel → Uploader
4. 每个组件迁移后立即测试，确认功能正常再继续
5. 全部完成后删除旧的 `static/` 文件，FastAPI 指向 `frontend/dist/`

**API 层不变**：前后端接口完全不变，Vue SPA 只是换了前端渲染方式。

---

## 附录 A：涉及文件总览

```
新增文件：
  frontend/                      # Vite + Vue 3 SPA 工程（~15 个文件）
  └── src/
      ├── main.js, App.vue
      ├── router/index.js
      ├── pages/LoginPage.vue, MainPage.vue
      ├── components/ChatPanel.vue, Sidebar.vue, AIOpsPanel.vue, ModeSwitcher.vue, Uploader.vue
      └── utils/config.js, api.js, auth.js

  app/
  ├── core/security.py           # JWT 生成/验证
  ├── core/auth_middleware.py    # 请求鉴权依赖注入
  ├── core/db.py                 # MySQL 连接工具
  ├── core/rate_limiter.py       # 流控
  ├── api/auth.py                # GitHub OAuth + 用户信息
  ├── api/session.py             # 会话管理 API
  └── services/
      ├── session_service.py     # 会话 CRUD
      ├── message_service.py     # 消息存取
      └── llm_guard.py           # LLM 请求队列

  migrations/
  ├── 001_create_users.sql
  ├── 002_create_sessions.sql
  ├── 003_create_messages.sql
  └── 004_create_readonly_user.sql

  tests/
  ├── test_security.py
  ├── test_auth.py
  └── test_session.py

修改文件：
  app/config.py, app/main.py
  app/api/chat.py, agent.py, mcp.py, aiops.py, file.py, title.py
  app/agent/mcp_client.py
  app/core/logger.py
  mcp_servers/{time,db,ppt,docker,search}_server.py
  docker-compose.yml, Dockerfile
  pyproject.toml, .env.example

删除文件：
  static/login.html, app.js, js/*  （迁移到 frontend/ 后删除）
```

## 附录 B：关键设计决策速查

| 决策 | 选择 | 理由 |
|------|------|------|
| 认证方式 | GitHub OAuth（唯一） | 面向开发者，零密码维护成本 |
| 会话保持 | JWT（PyJWT），payload 携带用户信息 | 无状态，中间件不查 DB |
| 认证注入 | Depends + 路由级注入 | 精确控制，公开路由放行 |
| 用户存储 | MySQL users 表 (pymysql) | 复用现有 MySQL |
| 会话/消息存储 | MySQL sessions + messages 表 | 统一数据源，JOIN 方便 |
| checkpoint 存储 | 继续 SQLite（thread_id 含 user_id 前缀） | 不破坏现有机制，天然隔离 |
| MCP 安全 | 共享 Secret Token | 内网部署足够 |
| 可观测性 | LangSmith | LangChain 官方，零代码接入 |
| **前端** | **Vite + Vue 3 SFC + Vue Router** | 组件化、HMR、.vue 单文件、路由支持 |
| 限流 | slowapi（内存存储） | 单机够用 |
| 日志 | loguru JSON format（可选切换） | 不换库 |
