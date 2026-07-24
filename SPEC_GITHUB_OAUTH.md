# AIOperator — GitHub OAuth 登录技术方案

> 版本：v1.0  
> 日期：2026-07-24  
> 状态：待评审

---

## 目录

- [一、快速问答](#一快速问答)
- [二、OAuth 是什么（用大白话讲）](#二oauth-是什么用大白话讲)
- [三、GitHub OAuth 怎么工作的](#三github-oauth-怎么工作的)
- [四、注册 OAuth App 全流程](#四注册-oauth-app-全流程)
- [五、后端实现方案](#五后端实现方案)
- [六、前端实现方案](#六前端实现方案)
- [七、数据库设计](#七数据库设计)
- [八、与现有认证体系的关系](#八与现有认证体系的关系)
- [九、开发计划](#九开发计划)
- [十、可行性分析](#十可行性分析)

---

## 一、快速问答

### Q1：用 GitHub OAuth 是不是就不用维护用户账号了？

**不完全是。** 你不需要维护"密码"了，但还是要维护"账号"。

| | 传统密码登录 | GitHub OAuth 登录 |
|---|---|---|
| 谁来验证用户身份？ | 你自己（比对密码哈希） | GitHub（GitHub 说这个人就是他） |
| 密码谁来管？ | 你自己（存储 bcrypt 哈希） | 不用你管（GitHub 管） |
| 用户表还要不要？ | 要 | **要**，记录用户信息 + 登录态 |
| 注册流程？ | 填邮箱 + 设密码 | 点击授权 → 自动创建账号 |
| 忘记密码？ | 自己做找回流程 | 不存在这个问题 |

**总结**：你的数据库仍然有一张 `users` 表，但 `password_hash` 列变为**可为 NULL**。GitHub 用户注册时，`password_hash` 就是空的，身份验证交给 GitHub。

### Q2：个人开发者能做 GitHub OAuth 吗？

**完全可以，而且免费、不需要企业认证。**

- 注册 OAuth App：免费，GitHub 不收费
- 前提条件：你有一个 GitHub 账号（你已经有 `itwjf`）
- 白嫖流量：GitHub OAuth 没有调用次数限制
- 不需要审核：不像微信 OAuth 需要企业资质，GitHub OAuth 直接创建即可

### Q3：可行性高不高？

**非常高。** 对 "DeepSeek 网页版 + 工具" 这个定位来说，GitHub OAuth 是最佳选择：

- 你的目标用户很大概率有 GitHub 账号（技术人员）
- 实现简单，3 个 HTTP 请求就搞定了
- 零成本，不增加运维负担
- 如果需要，可以和密码登录并存

---

## 二、OAuth 是什么（用大白话讲）

### 一个类比

你去住酒店，前台不用认识你，也不存你的身份证号。流程是：

```
你 → 前台："我要入住"
前台 → 你："去旁边公安系统刷脸验证"
你 → 公安系统：刷脸
公安系统 → 前台："这个人确实是张三，身份证号是 XXXXX"
前台 → 你："OK，给你钥匙"
```

在这个类比里：
- **酒店前台** = AIOperator
- **公安系统** = GitHub
- **刷脸** = 你在 GitHub 上点「授权」
- **"这个人确实是张三"** = GitHub 返回你的用户名、邮箱

### OAuth 的核心思想

**让用户在不暴露密码的情况下，授权第三方应用获取自己的基本信息。**

AIOperator 永远不知道你的 GitHub 密码，它只知道 GitHub 说"这个人是谁"。

---

## 三、GitHub OAuth 怎么工作的

### 3.1 完整流程图

```
      浏览器                        AIOperator 后端                  GitHub
        │                              │                            │
        │  ① 点击「GitHub 登录」       │                            │
        │─────────────────────────────>│                            │
        │                              │                            │
        │  ② 302 重定向                │                            │
        │<─────────────────────────────│                            │
        │                              │                            │
        │  ③ 浏览器跳转到 GitHub       │                            │
        │  https://github.com/login/oauth/authorize                 │
        │  ?client_id=xxx               │                            │
        │  &redirect_uri=xxx            │                            │
        │──────────────────────────────────────────────────────────>│
        │                              │                            │
        │  ④ GitHub 展示授权页面       │                            │
        │  「AIOperator 想获取你的      │                            │
        │    公开信息和邮箱」           │                            │
        │  [ 授权 ]  [ 取消 ]           │                            │
        │<──────────────────────────────────────────────────────────│
        │                              │                            │
        │  ⑤ 用户点击「授权」          │                            │
        │──────────────────────────────────────────────────────────>│
        │                              │                            │
        │  ⑥ 302 重定向回 AIOperator   │                            │
        │  /api/auth/github/callback   │                            │
        │  ?code=abc123def456           │                            │
        │─────────────────────────────>│                            │
        │                              │                            │
        │                              │  ⑦ 用 code 换 access_token │
        │                              │  POST /login/oauth/access_token
        │                              │  {client_id, client_secret, code}
        │                              │────────────────────────────>│
        │                              │                            │
        │                              │  ⑧ 返回 access_token       │
        │                              │<────────────────────────────│
        │                              │                            │
        │                              │  ⑨ 用 token 查用户信息     │
        │                              │  GET /user (Authorization: Bearer token)
        │                              │────────────────────────────>│
        │                              │                            │
        │                              │  ⑩ 返回用户信息            │
        │                              │  {login, email, avatar_url, id}
        │                              │<────────────────────────────│
        │                              │                            │
        │                              │  ⑪ 查找或创建用户记录      │
        │                              │  签发 JWT                   │
        │                              │                            │
        │  ⑫ 302 重定向到前端首页     │                            │
        │  （URL 中携带 JWT token）    │                            │
        │<─────────────────────────────│                            │
        │                              │                            │
        │  ⑬ 前端存储 JWT             │                            │
        │  用户已登录，可以对话        │                            │
```

### 3.2 三个关键 API

整个流程中，后端只需要跟 GitHub 打三次交道：

| 步骤 | 方法 | URL | 作用 |
|:----:|------|-----|------|
| 1 | 前端重定向 | `https://github.com/login/oauth/authorize` | 让用户去 GitHub 授权 |
| 2 | 后端 POST | `https://github.com/login/oauth/access_token` | 用临时 code 换 access_token |
| 3 | 后端 GET | `https://api.github.com/user` | 拿用户信息（用户名、邮箱、头像） |

### 3.3 请求参数详解

**第一步：重定向到 GitHub 授权页**

```
GET https://github.com/login/oauth/authorize

参数：
  client_id     — OAuth App 的 Client ID（注册后获得）
  redirect_uri  — 授权后的回调地址（必须与注册时填的一致）
  scope         — 请求的权限范围，如 "user:email"
  state         — 随机字符串，防止 CSRF 攻击（可选但建议加）
```

**第二步：用 code 换 token**

```
POST https://github.com/login/oauth/access_token

Header:
  Accept: application/json

Body (form-urlencoded):
  client_id     — OAuth App 的 Client ID
  client_secret — OAuth App 的 Client Secret（绝密，只在后端用）
  code          — 上一步回调 URL 中 GitHub 给的临时 code
  redirect_uri  — 必须与第一步一致
```

返回：
```json
{
  "access_token": "gho_xxxxxxxxxxxx",
  "token_type": "bearer",
  "scope": "user:email"
}
```

**第三步：拿用户信息**

```
GET https://api.github.com/user

Header:
  Authorization: Bearer gho_xxxxxxxxxxxx
```

返回：
```json
{
  "id": 12345678,
  "login": "itwjf",
  "name": "张三",
  "email": "zhangsan@example.com",
  "avatar_url": "https://avatars.githubusercontent.com/u/12345678"
}
```

> 如果 email 字段为 null（用户设置了隐私），再调 `GET https://api.github.com/user/emails` 获取已验证邮箱列表。

---

## 四、注册 OAuth App 全流程

### 4.1 操作步骤

1. 登录 GitHub → 右上角头像 → **Settings**
2. 左侧菜单最下面 → **Developer settings**
3. 左侧 → **OAuth Apps** → 点击 **New OAuth App**
4. 填写表单：

   | 字段 | 填什么 | 示例 |
   |------|--------|------|
   | **Application name** | 你的应用名 | `AIOperator` |
   | **Homepage URL** | 你的应用首页 | `http://localhost:9900`（开发） / `https://your-domain.com`（生产） |
   | **Application description** | 描述（选填） | `AI 智能运维助手` |
   | **Authorization callback URL** | 授权后的回调地址 | `http://localhost:9900/api/auth/github/callback` |

5. 点击 **Register application**
6. 进入应用详情页 → 看到 **Client ID** 和 **Client Secrets**（点 Generate a new client secret 生成）
7. 把这两个值记下来，存到 `.env` 中

### 4.2 开发 vs 生产的回调地址

| 环境 | Authorization callback URL |
|------|--------------------------|
| 本地开发 | `http://127.0.0.1:9900/api/auth/github/callback` |
| Docker 部署 | `https://your-domain.com:9900/api/auth/github/callback` |
| 生产（有域名 + HTTPS） | `https://aiop.example.com/api/auth/github/callback` |

本地开发时用 `127.0.0.1` 而不是 `localhost`，因为 GitHub 回调是从浏览器端发起的，两者实际是同一个地址。

### 4.3 环境变量配置

在 `.env` 中新增 3 个变量：

```bash
# GitHub OAuth
GITHUB_CLIENT_ID=Ov23liXXXX你的ClientID
GITHUB_CLIENT_SECRET=你的ClientSecret（保密！不要提交git）
GITHUB_REDIRECT_URI=http://127.0.0.1:9900/api/auth/github/callback
```

---

## 五、后端实现方案

### 5.1 要新增/修改的文件

```
新增：
  app/core/security.py           # JWT 生成/验证  +  GitHub token 交换

修改：
  app/config.py                  # +3 个 GitHub 配置项
  app/api/auth.py                # +2 个端点
  app/core/auth_middleware.py    # JWT 鉴权中间件（阶段一共用）
```

### 5.2 config.py 新增字段

```python
# GitHub OAuth
github_client_id: str = ""
github_client_secret: str = ""
github_redirect_uri: str = "http://127.0.0.1:9900/api/auth/github/callback"
```

### 5.3 两个新 API 端点

**端点 1：`GET /api/auth/github/login`**

作用：生成 GitHub 授权 URL 并 302 重定向。

流程：
1. 构造 URL：`https://github.com/login/oauth/authorize?client_id=xxx&redirect_uri=xxx&scope=user:email`
2. 可选：生成随机 `state` 参数防 CSRF，存入 session/cookie
3. 返回 302 重定向

```
GET /api/auth/github/login
  → 302 → https://github.com/login/oauth/authorize?client_id=xxx&...
```

**端点 2：`GET /api/auth/github/callback`**

作用：处理 GitHub 回调，完成登录。

流程：
1. 从 `?code=xxx` 拿到临时 code
2. POST 到 GitHub 换 access_token
3. GET GitHub `/user` + `/user/emails` 拿用户信息
4. 查 `users` 表 — 找到就更新最后登录时间，没找到就 INSERT
5. 签发 JWT（有效期 24 小时）
6. 302 重定向到前端首页，URL 中携带 JWT：`/static/index.html?token=jwt_xxx`

```
GET /api/auth/github/callback?code=abc123
  → 换 token → 拿用户信息 → 建/查用户 → 签发 JWT
  → 302 → /static/index.html?token=jwt_xxx
```

### 5.4 核心逻辑（伪代码级）

```
# ———— GitHub 回调处理 ————

async def github_callback(code: str):
    # 1. 用 code 换 access_token
    token_resp = await httpx.post(
        "https://github.com/login/oauth/access_token",
        data={
            "client_id": settings.github_client_id,
            "client_secret": settings.github_client_secret,
            "code": code,
            "redirect_uri": settings.github_redirect_uri,
        },
        headers={"Accept": "application/json"},
    )
    access_token = token_resp.json()["access_token"]

    # 2. 拿用户信息
    user_resp = await httpx.get(
        "https://api.github.com/user",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    github_user = user_resp.json()
    # github_user = {id, login, name, email, avatar_url}

    # 3. 如果 email 为空，再查邮箱列表
    if not github_user.get("email"):
        email_resp = await httpx.get(
            "https://api.github.com/user/emails",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        emails = email_resp.json()
        primary = next((e for e in emails if e["primary"]), None)
        if primary:
            github_user["email"] = primary["email"]

    # 4. 查找或创建用户
    user = await db_find_user_by_provider("github", github_user["id"])
    if not user:
        user = await db_create_user(
            username=github_user["login"],
            email=github_user.get("email"),
            auth_provider="github",
            provider_user_id=str(github_user["id"]),
            avatar_url=github_user.get("avatar_url"),
        )

    # 5. 签发 JWT
    jwt_token = create_jwt(user.id)
    
    # 6. 重定向到前端
    return RedirectResponse(f"/static/index.html?token={jwt_token}")
```

### 5.5 依赖项

需要新增的 pip 依赖：

```toml
# pyproject.toml
dependencies = [
    ...
    "httpx>=0.27.0",        # 异步 HTTP 客户端（调 GitHub API）
    "python-jose>=3.3.0",   # JWT 生成和验证
    "passlib[bcrypt]>=1.7", # bcrypt 密码哈希（密码登录用）
]
```

> `httpx` 是用在 GitHub OAuth 的 token 交换和用户信息查询，不需要引入 `authlib` 等重量级 OAuth 库——因为 GitHub OAuth 本质上就是 3 个 HTTP 请求，自己写反而更清晰可控。

---

## 六、前端实现方案

### 6.1 登录页设计

新增一个简单的登录页面 `static/login.html`（或在 `index.html` 中加一个登录面板）：

```
┌──────────────────────────────────┐
│         🤖 AIOperator            │
│       AI 智能运维助手            │
│                                  │
│  ┌────────────────────────────┐  │
│  │  🔑 使用 GitHub 账号登录   │  │
│  └────────────────────────────┘  │
│                                  │
│  ──────── 或 ────────            │
│                                  │
│  邮箱：[_______________]         │
│  密码：[_______________]         │
│  [ 登录 ]  [ 注册 ]              │
└──────────────────────────────────┘
```

### 6.2 前端 JS 逻辑

**GitHub 登录按钮的点击行为**：直接跳转：

```javascript
function loginWithGithub() {
    window.location.href = `${API_BASE}/api/auth/github/login`;
}
```

**处理回调返回的 token**（在 `index.html` 初始化时检查 URL 参数）：

```javascript
// index.html 加载时
const urlParams = new URLSearchParams(window.location.search);
const token = urlParams.get('token');
if (token) {
    // 存储到 localStorage
    localStorage.setItem('aioperator_token', token);
    // 清除 URL 中的 token 参数（避免泄露到浏览器历史）
    window.history.replaceState({}, '', '/static/index.html');
}
```

### 6.3 全局 fetch 封装

所有 API 请求自动带 JWT：

```javascript
async function api(url, options = {}) {
    const token = localStorage.getItem('aioperator_token');
    const headers = {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
    };
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    const resp = await fetch(url, { ...options, headers });
    if (resp.status === 401) {
        // Token 过期 → 跳转登录页
        localStorage.removeItem('aioperator_token');
        window.location.href = '/static/login.html';
    }
    return resp;
}
```

### 6.4 判断登录状态

```javascript
// 页面加载时检查
async function checkLogin() {
    const token = localStorage.getItem('aioperator_token');
    if (!token) {
        window.location.href = '/static/login.html';
        return;
    }
    // 调 /api/auth/me 验证 token 有效
    const resp = await api('/api/auth/me');
    if (!resp.ok) {
        window.location.href = '/static/login.html';
        return;
    }
    const user = await resp.json();
    // user = { id, username, email, avatar_url }
}
```

---

## 七、数据库设计

### 7.1 users 表（最终版，支持密码 + GitHub 双模式）

```sql
CREATE TABLE users (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    username    VARCHAR(50)  NOT NULL,
    email       VARCHAR(100) DEFAULT NULL,       -- GitHub 用户可能邮箱为空
    password_hash VARCHAR(255) DEFAULT NULL,     -- 密码登录才有，GitHub 用户为 NULL

    -- OAuth 字段
    auth_provider   ENUM('local', 'github') NOT NULL DEFAULT 'local',
    provider_user_id VARCHAR(100) DEFAULT NULL,  -- GitHub 用户 ID（数字转字符串）

    -- 通用字段
    avatar_url      VARCHAR(500) DEFAULT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at   DATETIME DEFAULT NULL,

    -- 安全字段
    failed_attempts INT NOT NULL DEFAULT 0,      -- 仅密码登录用
    locked_until    DATETIME DEFAULT NULL,       -- 仅密码登录用

    UNIQUE KEY uk_username (username),
    UNIQUE KEY uk_email (email),
    UNIQUE KEY uk_provider_user (auth_provider, provider_user_id)  -- OAuth 唯一
);
```

**关键设计点**：

- `password_hash` 可为 NULL：GitHub 用户不需要密码
- `auth_provider` + `provider_user_id` 联合唯一索引：防止同一个 GitHub 账号创建多个用户
- GitHub 的 `id` 是数字（如 `12345678`），存为 VARCHAR 以防不同平台的 ID 格式不同
- 如果用户先用 GitHub 登录，又想设置密码（用于本地登录），后续可以追加 `password_hash`

### 7.2 用户创建逻辑

```
注册（密码模式）:
  INSERT INTO users (username, email, password_hash, auth_provider)
  VALUES ('itwjf', 'xx@qq.com', '$2b$12$...', 'local')

GitHub OAuth 登录:
  SELECT * FROM users WHERE auth_provider='github' AND provider_user_id='12345678'
  → 找到了 → 更新 last_login_at
  → 没找到 → INSERT INTO users (username, email, auth_provider, provider_user_id, avatar_url)
              VALUES ('itwjf', 'xx@qq.com', 'github', '12345678', 'https://...')
```

---

## 八、与现有认证体系的关系

### 8.1 建议：双模式并存

```
登录方式
  ├── GitHub OAuth（推荐，一键登录）
  └── 邮箱 + 密码（兜底，给没有 GitHub 账号的用户）
```

两个入口共享同一张 `users` 表、同一个 JWT 签发逻辑、同一个鉴权中间件。

### 8.2 在 ROADMAP 中的位置

如果只做 GitHub OAuth + 密码登录双模式，对应的就是 `ROADMAP.md` 的阶段一 + 阶段六合并：

| 原计划 | 调整后 |
|--------|--------|
| 阶段一：密码登录体系 | 保留，作为兜底 |
| 阶段六：GitHub OAuth | **提前**，和阶段一合并开发 |

开发顺序建议：先做密码登录（跑通 JWT 鉴权链路），再加 GitHub OAuth（只需加 2 个端点 + 前端一个按钮）。

### 8.3 纯 GitHub OAuth 模式（最简方案）

如果暂时不做密码登录，**只做 GitHub OAuth**，那整个认证体系的复杂度减半：

- ❌ 不需要 `password_hash` 列
- ❌ 不需要 bcrypt
- ❌ 不需要注册表单
- ❌ 不需要忘记密码
- ❌ 不需要登录失败锁定
- ✅ 只需要一张 `users` 表（auth_provider='github'，password_hash 为空）
- ✅ 2 个 API 端点
- ✅ 前端一个 GitHub 登录按钮

**这种模式下，`users` 表就是一张简单的映射表**：记录哪个 GitHub 用户用过你的系统。开发量大约 1 天。

---

## 九、开发计划

### 纯 GitHub OAuth 模式（推荐先做这个）

**预计 1 天**

| # | 任务 | 文件 | 工作量 |
|:--:|------|------|:--:|
| 1 | 注册 GitHub OAuth App，获取 Client ID / Secret | GitHub 后台 | 10 min |
| 2 | `config.py` 新增 3 个 GitHub 配置项 | `app/config.py` | 5 min |
| 3 | `security.py` — JWT 生成/验证 | `app/core/security.py` | 30 min |
| 4 | `auth.py` — `GET /api/auth/github/login` + `GET /api/auth/github/callback` | `app/api/auth.py` | 1 h |
| 5 | `auth_middleware.py` — JWT 鉴权中间件 + 白名单路由 | `app/core/auth_middleware.py` | 30 min |
| 6 | `main.py` 注册中间件 + 添加路由 | `app/main.py` | 10 min |
| 7 | `users` 表 DDL + 执行 | `migrations/001_users.sql` | 15 min |
| 8 | 前端 `login.html` — GitHub 登录页 | `static/login.html` | 30 min |
| 9 | 前端 `api.js` — fetch 封装 + JWT 自动注入 | `static/js/api.js` | 30 min |
| 10 | 前端 `index.html` — 登录态检查 + token 解析 | `static/index.html` | 15 min |
| 11 | `.env.example` 新增 GitHub 配置示例 | `.env.example` | 5 min |
| 12 | 端到端测试：GitHub 登录 → 获取 JWT → 创建会话 → 对话 | 手动 | 30 min |

### GitHub OAuth + 密码登录双模式（完整版）

**预计 2 天**

在纯 GitHub OAuth 基础上增加：

| # | 任务 | 文件 | 工作量 |
|:--:|------|------|:--:|
| +1 | `security.py` — bcrypt 密码哈希 | `app/core/security.py` | 15 min |
| +2 | `auth.py` — `POST /api/auth/register` + `POST /api/auth/login` | `app/api/auth.py` | 1 h |
| +3 | 前端 `login.html` — 密码登录表单 + 注册表单 | `static/login.html` | 1 h |
| +4 | 用户表：`password_hash` 可为 NULL，`failed_attempts` + `locked_until` | `migrations/001_users.sql` | 10 min |
| +5 | 端到端测试：密码注册/登录 + GitHub 登录 | 手动 | 30 min |

---

## 十、可行性分析

### 10.1 个人开发者能做吗？

| 维度 | 结论 |
|------|------|
| **需要企业资质吗？** | 不需要，个人 GitHub 账号即可 |
| **需要付费吗？** | 免费，无调用次数限制 |
| **需要审核吗？** | 不需要，创建即生效 |
| **注册入口在哪？** | GitHub Settings → Developer settings → OAuth Apps |
| **需要 HTTPS 吗？** | 本地开发 `127.0.0.1` 不需要；生产环境建议有 |
| **GitHub 账号要求** | 你已经有了 (`itwjf`)，不需要额外注册 |

### 10.2 对本项目的好处

1. **零维护成本**：不用做注册流程、忘记密码、邮箱验证、密码强度校验
2. **用户门槛低**：目标用户（程序员/运维）大概率有 GitHub 账号，点一下就能用
3. **安全**：密码验证交给 GitHub 这个全球最大代码托管平台，比你自己做安全
4. **信任感**：用户看到 "使用 GitHub 登录" 比 "输入邮箱密码注册" 更放心
5. **自带头像**：GitHub 返回 `avatar_url`，直接显示在界面上

### 10.3 局限性

1. **目标用户局限**：没有 GitHub 账号的人用不了。但你的产品定位是"智能运维助手"，目标用户重合度很高
2. **网速问题**：GitHub 在国内偶尔不稳定。用户点击登录 → 跳转 GitHub 授权页 → 如果 GitHub 加载慢，体验会差。可以后续加 Gitee OAuth 做国内兜底（Gitee 也支持 OAuth，流程一模一样）
3. **单点依赖**：如果 GitHub 挂了（虽然概率极低），登录功能全挂。但你家产品本身就依赖网络，这个问题可以接受

### 10.4 总结建议

**先做纯 GitHub OAuth 模式**，这是投入产出比最高的方案。上线后观察：如果用户反馈"我没有 GitHub 账号能不能用"，再花半天加上密码登录即可。两者不冲突。

如果想把 OAuth 做完整，后续可以加：
- **Gitee OAuth**（国内用户友好，流程和 GitHub 完全一致）
- **微信扫码登录**（需要微信开放平台企业认证，个人开发者暂时做不了）
