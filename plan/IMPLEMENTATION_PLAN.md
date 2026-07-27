# AIOperator 多用户化实施计划

> 基于 [ROADMAP.md](ROADMAP.md) 展开的详细实施文档，供 AI 编程时逐任务执行。
> 每个任务有明确的文件路径、函数签名、实现细节和测试方法。

---

## 进度总览

| 阶段 | 名称 | 状态 | 开始日期 | 完成日期 |
|------|------|:--:|----------|----------|
| 一 | GitHub OAuth 认证体系 | ✅ 已完成 | 2026-07-27 | 2026-07-27 |
| 二 | 会话 & 消息持久化迁移 | ⬜ 待开始 | — | — |
| 三 | MCP Server 安全加固 | ⬜ 待开始 | — | — |
| 四 | 流控 & 并发保护 | ⬜ 待开始 | — | — |
| 五 | 前端模块化拆分 | ⬜ 待开始 | — | — |
| 六 | LangSmith 可观测性集成 | ⬜ 待开始 | — | — |
| 七 | 工程化 & 质量 | ⬜ 待开始 | — | — |

---

## 阶段一：GitHub OAuth 认证体系

**目标**：打通从 GitHub 登录到 API 鉴权的完整链路，实现用户隔离。

**认证流程**：
```
用户点击「GitHub 登录」→ 重定向到 GitHub 授权页 → 用户确认授权
→ GitHub 回调 /api/auth/github/callback?code=xxx&state=yyy
→ 后端用 code 换 access_token → 用 access_token 查 GitHub 用户 API
→ 创建/查找本地 users 记录 → 签发 JWT → 重定向回前端并携带 token
→ 前端存储 token → 后续所有 API 请求带 Authorization: Bearer <JWT>
```

**产出物**：
- `app/core/security.py` — JWT 生成/验证
- `app/core/auth_middleware.py` — 请求鉴权依赖注入
- `app/core/db.py` — MySQL 连接工具
- `app/api/auth.py` — GitHub OAuth 回调 + 当前用户 API
- `static/login.html` — 登录页面
- `static/js/auth.js` — 前端 Token 管理
- `static/js/api.js` — 前端 HTTP 封装
- `static/js/config.js` — 前端配置常量
- `migrations/001_create_users.sql` — 建表 DDL

### 1.0 前置条件：注册 GitHub OAuth App

- [x] **1.0.1 在 GitHub 注册 OAuth App**

  1. GitHub → Settings → Developer settings → OAuth Apps → New OAuth App
  2. Application name: `AIOperator`（或自定义）
  3. Homepage URL: `http://127.0.0.1:9900`
  4. Authorization callback URL: `http://127.0.0.1:9900/api/auth/github/callback`
  5. 注册成功后获取 **Client ID**，点击 "Generate a new client secret" 获取 **Client Secret**
  6. 将这两个值填入 `.env`：
     ```bash
     GITHUB_CLIENT_ID=your-client-id
     GITHUB_CLIENT_SECRET=your-client-secret
     ```

### 1.1 数据库：创建 users 表

- [x] **1.1.0 创建 `migrations/` 目录**

  路径：`migrations/`
  操作：新建空目录。

- [x] **1.1.1 编写 DDL 文件**

  路径：`migrations/001_create_users.sql`

  ```sql
  CREATE TABLE IF NOT EXISTS users (
      id INT AUTO_INCREMENT PRIMARY KEY,
      username VARCHAR(100) NOT NULL,
      email VARCHAR(200) DEFAULT NULL,
      github_id INT NOT NULL UNIQUE,
      avatar_url VARCHAR(500) DEFAULT NULL,
      access_token VARCHAR(255) DEFAULT NULL,
      is_active BOOLEAN NOT NULL DEFAULT TRUE,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      last_login_at DATETIME DEFAULT NULL
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
  ```

  > 注意：不设 password_hash 字段。认证全部委托给 GitHub，本项目只存 GitHub 用户标识。

  测试：在 MySQL 中手动执行 `SOURCE migrations/001_create_users.sql;`，确认表创建成功。

### 1.2 配置：新增认证相关配置项

- [x] **1.2 修改 `app/config.py`**

  在 `Settings` 类中新增以下字段（追加在 Shell 工具配置之后）：

  ```python
  # ---- 数据库配置（MySQL）----
  db_host: str = "127.0.0.1"
  db_port: int = 3306
  db_user: str = "root"
  db_password: str = ""
  db_name: str = "aioperator"

  # ---- 认证配置 ----
  jwt_secret_key: str = ""                          # JWT 签名密钥（64 字节随机字符串）
  jwt_algorithm: str = "HS256"                      # JWT 签名算法
  jwt_expire_hours: int = 24                        # access_token 过期时间（小时）

  # ---- GitHub OAuth 配置 ----
  github_client_id: str = ""
  github_client_secret: str = ""
  github_redirect_uri: str = "http://127.0.0.1:9900/api/auth/github/callback"

  # ---- MCP 安全配置（阶段三才用，提前定义）----
  mcp_secret_token: str = ""

  # ---- LangSmith 可观测性（阶段六才用，提前定义）----
  langchain_tracing_v2: bool = False
  langchain_endpoint: str = "https://api.smith.langchain.com"
  langchain_api_key: str = ""
  langchain_project: str = "aioperator"
  ```

- [x] **1.2.1 更新 `.env.example`**

  路径：`.env.example`
  在文件末尾追加：

  ```bash
  # === 数据库配置（MySQL）===
  DB_HOST=127.0.0.1
  DB_PORT=3306
  DB_USER=root
  DB_PASSWORD=root123
  DB_NAME=aioperator

  # === 认证配置 ===
  # 生成方式：python -c "import secrets; print(secrets.token_urlsafe(48))"
  JWT_SECRET_KEY=change-me-to-a-random-secret
  JWT_ALGORITHM=HS256
  JWT_EXPIRE_HOURS=24

  # === GitHub OAuth ===
  # 在 https://github.com/settings/developers 创建 OAuth App 获取
  GITHUB_CLIENT_ID=your-github-client-id
  GITHUB_CLIENT_SECRET=your-github-client-secret
  GITHUB_REDIRECT_URI=http://127.0.0.1:9900/api/auth/github/callback

  # === MCP 安全（阶段三）===
  # 和 JWT_SECRET_KEY 一样用 secrets.token_urlsafe(48) 生成
  MCP_SECRET_TOKEN=change-me-to-another-random-secret

  # === LangSmith 可观测性（阶段六）===
  # 在 https://smith.langchain.com 注册获取 API Key
  LANGCHAIN_TRACING_V2=false
  LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
  LANGCHAIN_API_KEY=your-langsmith-api-key
  LANGCHAIN_PROJECT=aioperator
  ```

- [x] **1.2.2 更新 `.env`（本地开发用）**

  手动生成两个随机密钥并更新本地 `.env`：
  ```bash
  python -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(48))"
  python -c "import secrets; print('MCP_SECRET_TOKEN=' + secrets.token_urlsafe(48))"
  ```

### 1.3 安全模块：JWT

- [x] **1.3 新建 `app/core/security.py`**

  功能清单：
  - `create_access_token(user_id: int) -> str` — 生成 JWT
  - `decode_access_token(token: str) -> dict | None` — 解码 JWT

  实现细节：

  ```python
  """
  安全模块 — JWT 令牌生成/验证。
  """
  import jwt
  from datetime import datetime, timedelta, timezone
  from app.config import settings

  def create_access_token(user_id: int) -> str:
      """生成 JWT access_token。payload 包含 user_id 和过期时间。"""
      expire = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)
      payload = {
          "sub": str(user_id),
          "exp": expire,
          "iat": datetime.now(timezone.utc),
      }
      return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

  def decode_access_token(token: str) -> dict | None:
      """解码 JWT token，返回 payload；无效/过期则返回 None。"""
      try:
          return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
      except jwt.PyJWTError:
          return None
  ```

  依赖：需要在 `pyproject.toml` 中新增 `pyjwt`（不需要 passlib/bcrypt，因为没有密码）。

- [x] **1.3.1 更新 `pyproject.toml` 依赖**

  在 `dependencies` 列表中新增：
  ```
  "pyjwt>=2.9.0",
  "httpx>=0.27.0",
  ```

  说明：
  - `pyjwt` — JWT 令牌生成和验证
  - `httpx` — 用于 GitHub OAuth API 调用（换 access_token、查用户信息）

### 1.4 数据库连接工具

- [x] **1.4 新建 `app/core/db.py`**

  提供统一的 MySQL 连接获取方式：

  ```python
  """
  数据库工具 — 提供 MySQL 连接获取函数。
  """
  import pymysql
  from app.config import settings

  def get_db_connection():
      """创建 MySQL 连接（调用方负责 conn.close()）。"""
      return pymysql.connect(
          host=settings.db_host,
          port=settings.db_port,
          user=settings.db_user,
          password=settings.db_password,
          database=settings.db_name,
          charset="utf8mb4",
          cursorclass=pymysql.cursors.DictCursor,
      )
  ```

### 1.5 认证 API：GitHub OAuth 回调 + 当前用户

- [x] **1.5 新建 `app/api/auth.py`**

  路由前缀：`/api/auth`
  需要三个端点：

  **1.5.1 GET `/api/auth/github/login`** — 发起 GitHub OAuth

  逻辑：
  1. 生成随机 `state` 参数（防 CSRF）
  2. 将 state 存入 session 或临时 cookie
  3. 重定向到：
     ```
     https://github.com/login/oauth/authorize
       ?client_id={GITHUB_CLIENT_ID}
       &redirect_uri={GITHUB_REDIRECT_URI}
       &scope=user:email
       &state={random_state}
     ```

  实现：
  ```python
  import secrets
  from fastapi.responses import RedirectResponse

  @router.get("/github/login")
  async def github_login():
      state = secrets.token_urlsafe(32)
      # 存 state 到 cookie 用于回调验证
      redirect_url = (
          f"https://github.com/login/oauth/authorize"
          f"?client_id={settings.github_client_id}"
          f"&redirect_uri={settings.github_redirect_uri}"
          f"&scope=user:email"
          f"&state={state}"
      )
      response = RedirectResponse(url=redirect_url)
      response.set_cookie(key="oauth_state", value=state, httponly=True, max_age=600)
      return response
  ```

  **1.5.2 GET `/api/auth/github/callback`** — GitHub OAuth 回调

  逻辑：
  1. 从 query params 拿 `code` 和 `state`
  2. 验证 state（对比 cookie 中的 oauth_state）→ 不匹配则 403
  3. 用 httpx POST `https://github.com/login/oauth/access_token` 换 `access_token`
     - Headers: `Accept: application/json`
     - Body: `client_id`, `client_secret`, `code`
  4. 用 access_token GET `https://api.github.com/user` 拿用户信息（`id`, `login`, `avatar_url`）
  5. 用 access_token GET `https://api.github.com/user/emails` 拿邮箱
  6. 查 MySQL：`SELECT * FROM users WHERE github_id = ?`
     - 存在 → 更新 `username`, `email`, `avatar_url`, `last_login_at`
     - 不存在 → INSERT INTO users
  7. `create_access_token(user_id)` → 签发 JWT
  8. 重定向到 `/static/index.html?token={jwt}`

  ```python
  import httpx
  from app.core.db import get_db_connection
  from app.core.security import create_access_token

  @router.get("/github/callback")
  async def github_callback(code: str, state: str, request: Request):
      # 1. 验证 state
      saved_state = request.cookies.get("oauth_state", "")
      if state != saved_state:
          raise HTTPException(status_code=403, detail="CSRF 验证失败")

      # 2. 用 code 换 access_token
      async with httpx.AsyncClient() as client:
          token_resp = await client.post(
              "https://github.com/login/oauth/access_token",
              json={
                  "client_id": settings.github_client_id,
                  "client_secret": settings.github_client_secret,
                  "code": code,
              },
              headers={"Accept": "application/json"},
          )
          token_data = token_resp.json()
          access_token = token_data.get("access_token")
          if not access_token:
              raise HTTPException(status_code=400, detail="GitHub 授权失败")

          # 3. 查 GitHub 用户信息
          headers = {"Authorization": f"Bearer {access_token}"}
          user_resp = await client.get("https://api.github.com/user", headers=headers)
          user_data = user_resp.json()

          # 4. 查邮箱
          email_resp = await client.get("https://api.github.com/user/emails", headers=headers)
          emails = email_resp.json()
          primary_email = next((e["email"] for e in emails if e.get("primary")), None)

      # 5. 创建或更新用户
      github_id = user_data["id"]
      conn = get_db_connection()
      with conn.cursor() as cursor:
          cursor.execute("SELECT id FROM users WHERE github_id = %s", (github_id,))
          existing = cursor.fetchone()

          if existing:
              cursor.execute(
                  "UPDATE users SET username=%s, email=%s, avatar_url=%s, last_login_at=NOW() WHERE github_id=%s",
                  (user_data["login"], primary_email, user_data.get("avatar_url"), github_id),
              )
              user_id = existing["id"]
          else:
              cursor.execute(
                  "INSERT INTO users (username, email, github_id, avatar_url, access_token) VALUES (%s,%s,%s,%s,%s)",
                  (user_data["login"], primary_email, github_id, user_data.get("avatar_url"), access_token),
              )
              user_id = cursor.lastrowid
      conn.commit()
      conn.close()

      # 6. 签发 JWT，重定向回前端
      jwt_token = create_access_token(user_id)
      response = RedirectResponse(url=f"/static/index.html?token={jwt_token}")
      response.delete_cookie("oauth_state")
      return response
  ```

  **1.5.3 GET `/api/auth/me`** — 获取当前用户信息

  ```python
  @router.get("/me")
  async def get_me(current_user: dict = Depends(get_current_user)):
      """返回当前登录用户信息（需要 JWT）。"""
      return current_user
  ```

- [x] **1.5.4 在 `app/main.py` 中注册路由**

  ```python
  from app.api.auth import router as auth_router
  app.include_router(auth_router)
  ```

### 1.6 认证中间件：JWT 验证 + current_user 注入

- [x] **1.6 新建 `app/core/auth_middleware.py`**

  使用 FastAPI `Depends` + 路由级依赖注入（不是全局中间件），因为部分路由需要公开。

  ```python
  """
  认证中间件 — 验证 JWT 并注入 current_user。
  """
  from fastapi import Request, HTTPException, Depends
  from app.core.security import decode_access_token
  from app.core.db import get_db_connection

  # 不需要认证的路由前缀
  PUBLIC_PREFIXES = ("/health", "/docs", "/openapi.json", "/static", "/api/auth")

  async def get_current_user(request: Request) -> dict | None:
      """从 Authorization header 提取 JWT，返回当前用户信息；未登录/公开路径返回 None。"""
      path = request.url.path

      # 白名单放行
      if any(path.startswith(p) for p in PUBLIC_PREFIXES):
          return None

      auth_header = request.headers.get("Authorization", "")
      if not auth_header.startswith("Bearer "):
          raise HTTPException(status_code=401, detail="未登录，请先登录")

      token = auth_header[7:]  # 去掉 "Bearer " 前缀
      payload = decode_access_token(token)
      if payload is None:
          raise HTTPException(status_code=401, detail="登录已过期，请重新登录")

      user_id = int(payload.get("sub", 0))

      # 从 MySQL 查用户
      conn = get_db_connection()
      with conn.cursor() as cursor:
          cursor.execute(
              "SELECT id, username, email, avatar_url, is_active, created_at, last_login_at FROM users WHERE id = %s",
              (user_id,),
          )
          user = cursor.fetchone()
      conn.close()

      if not user:
          raise HTTPException(status_code=401, detail="用户不存在")

      if not user["is_active"]:
          raise HTTPException(status_code=403, detail="账号已被禁用")

      return user
  ```

  **实际使用方式**：在每个需要认证的路由函数参数中加 `current_user: dict = Depends(get_current_user)`。

  **session_id → thread_id 改造**：API 层拿到 `current_user["id"]` 后，构造 `thread_id = f"{user_id}:{session_id}"`，传给 service 层。

### 1.7 API 层：session_id → thread_id 改造

- [x] **1.7.1 修改 `app/api/chat.py`**

  在 `chat()` 和 `chat_stream()` 中，将 `session_id` 拼接为 `thread_id`：

  ```python
  from app.core.auth_middleware import get_current_user

  # 函数签名新增：current_user: dict = Depends(get_current_user)
  # 原来：answer = await query(req.question, req.session_id)
  # 改为：
  thread_id = f"{current_user['id']}:{req.session_id}" if current_user else req.session_id
  answer = await query(req.question, thread_id)
  ```

- [x] **1.7.2 修改 `app/api/agent.py`**

  同上，`chat()` 和 `chat_stream()` 中做相同的 thread_id 拼接。

- [x] **1.7.3 修改 `app/api/mcp.py`**

  同上，`mcp_chat()` 和 `mcp_chat_stream()` 中做相同的 thread_id 拼接。

- [x] **1.7.4 修改 `app/api/aiops.py`**

  同上，`diagnose()` 中做相同的 thread_id 拼接。

- [x] **1.7.5 修改 `app/api/file.py`**

  加 `current_user: dict = Depends(get_current_user)` 参数，做用户归属校验。

### 1.8 前端：GitHub 登录页面 + Token 管理

- [x] **1.8.1 新建 `static/js/config.js`**

  ```javascript
  // AIOperator 前端配置
  const CONFIG = {
      API_BASE: '',
      JWT_KEY: 'aioperator_jwt_token',
      USER_KEY: 'aioperator_user',
  };
  ```

- [x] **1.8.2 新建 `static/js/api.js`**

  封装 `fetch`，自动注入 JWT，处理 401 跳转登录页：

  ```javascript
  async function apiRequest(path, options = {}) {
      const token = localStorage.getItem(CONFIG.JWT_KEY);
      const headers = {
          'Content-Type': 'application/json',
          ...(options.headers || {}),
      };
      if (token) {
          headers['Authorization'] = `Bearer ${token}`;
      }

      const response = await fetch(path, { ...options, headers });

      if (response.status === 401) {
          localStorage.removeItem(CONFIG.JWT_KEY);
          localStorage.removeItem(CONFIG.USER_KEY);
          if (!window.location.pathname.endsWith('login.html')) {
              window.location.href = '/static/login.html';
          }
          throw new Error('登录已过期，请重新登录');
      }

      return response;
  }
  ```

- [x] **1.8.3 新建 `static/login.html`**

  简约的登录页面：
  - 项目 Logo / 名称
  - "使用 GitHub 登录" 按钮（一个按钮即可）
  - 点击 → `window.location.href = '/api/auth/github/login'`
  - 样式与主应用保持一致（暗色主题、毛玻璃效果）

- [x] **1.8.4 新建 `static/js/auth.js`**

  ```javascript
  // AIOperator 认证模块
  function handleOAuthCallback() {
      const params = new URLSearchParams(window.location.search);
      const token = params.get('token');
      if (token) {
          localStorage.setItem(CONFIG.JWT_KEY, token);
          // 清除 URL 中的 token 参数
          window.history.replaceState({}, document.title, window.location.pathname);
          // 拉取用户信息
          fetchUserInfo();
      }
  }

  async function fetchUserInfo() {
      const resp = await apiRequest('/api/auth/me');
      if (resp.ok) {
          const user = await resp.json();
          localStorage.setItem(CONFIG.USER_KEY, JSON.stringify(user));
      }
  }

  function logout() {
      localStorage.removeItem(CONFIG.JWT_KEY);
      localStorage.removeItem(CONFIG.USER_KEY);
      window.location.href = '/static/login.html';
  }

  function getCurrentUser() {
      const raw = localStorage.getItem(CONFIG.USER_KEY);
      return raw ? JSON.parse(raw) : null;
  }

  // 页面加载时检查 OAuth 回调
  if (window.location.search.includes('token=')) {
      handleOAuthCallback();
  }
  ```

- [x] **1.8.5 修改 `static/index.html`**

  - 在 `<head>` 中新增：
    ```html
    <script src="js/config.js"></script>
    <script src="js/api.js"></script>
    <script src="js/auth.js"></script>
    ```
  - 页面加载时检查 JWT，无 token 则跳转 login.html：
    ```javascript
    if (!localStorage.getItem(CONFIG.JWT_KEY)) {
        window.location.href = '/static/login.html';
    }
    ```
  - 顶部栏增加用户名显示 + 退出按钮

### 1.9 阶段一测试

- [x] **1.9.1 手动测试清单**

  1. 访问 `http://127.0.0.1:9900` → 无 token → 自动跳转登录页
  2. 点击「GitHub 登录」→ 跳转 GitHub 授权页
  3. 确认授权 → 回调 → 自动跳转回主页面，已登录状态
  4. 页面顶部显示 GitHub 用户名和头像
  5. 创建会话 → 对话 → 正常
  6. 另一个浏览器（或无痕模式）登录同一个 GitHub 账号 → 能看到自己之前的会话
  7. 另一个浏览器登录不同的 GitHub 账号 → 看不到别人的会话
  8. JWT 过期后 → 发请求 → 返回 401 → 前端自动跳转登录页
  9. 直接 curl 访问 `/api/chat` 不带 token → 401
  10. 带有效 token 访问 `/api/auth/me` → 返回用户信息

---

## 阶段二：会话 & 消息持久化迁移

**目标**：对话历史从 localStorage + SQLite → MySQL，支持跨设备访问历史。

**产出物**：
- `app/services/session_service.py` — 会话 CRUD
- `app/services/message_service.py` — 消息存取
- `app/api/session.py` — 会话管理 API
- `migrations/002_create_sessions.sql` — 建表 DDL
- `migrations/003_create_messages.sql` — 建表 DDL

### 2.1 数据库建表

- [ ] **2.1.1 编写 `migrations/002_create_sessions.sql`**

  ```sql
  CREATE TABLE IF NOT EXISTS sessions (
      id INT AUTO_INCREMENT PRIMARY KEY,
      session_id VARCHAR(36) NOT NULL,
      user_id INT NOT NULL,
      title VARCHAR(100) DEFAULT NULL,
      agent_type ENUM('rag', 'manual', 'mcp', 'aiops') NOT NULL DEFAULT 'rag',
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
      UNIQUE KEY uk_user_session (user_id, session_id),
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
  ```

- [ ] **2.1.2 编写 `migrations/003_create_messages.sql`**

  ```sql
  CREATE TABLE IF NOT EXISTS messages (
      id INT AUTO_INCREMENT PRIMARY KEY,
      session_id INT NOT NULL,
      role ENUM('user', 'assistant', 'tool', 'system') NOT NULL,
      content TEXT NOT NULL,
      tool_name VARCHAR(100) DEFAULT NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
      INDEX idx_session_id (session_id)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
  ```

### 2.2 会话服务

- [ ] **2.2 新建 `app/services/session_service.py`**

  使用 `app/core/db.py` 的 `get_db_connection()` 获取连接，写成同步函数：

  ```python
  """
  会话服务 — 会话 CRUD，按 user_id 隔离。
  """
  from app.core.db import get_db_connection

  def create_session(user_id: int, session_id: str, agent_type: str = "rag", title: str = None) -> dict:
      conn = get_db_connection()
      with conn.cursor() as cursor:
          cursor.execute(
              "INSERT INTO sessions (session_id, user_id, agent_type, title) VALUES (%s,%s,%s,%s)",
              (session_id, user_id, agent_type, title),
          )
          conn.commit()
      conn.close()
      return {"session_id": session_id, "agent_type": agent_type, "title": title}

  def list_sessions(user_id: int) -> list[dict]:
      conn = get_db_connection()
      with conn.cursor() as cursor:
          cursor.execute(
              "SELECT session_id, title, agent_type, created_at, updated_at FROM sessions WHERE user_id=%s ORDER BY updated_at DESC",
              (user_id,),
          )
          rows = cursor.fetchall()
      conn.close()
      return list(rows)

  def delete_session(user_id: int, session_id: str) -> bool:
      conn = get_db_connection()
      with conn.cursor() as cursor:
          cursor.execute(
              "DELETE FROM sessions WHERE user_id=%s AND session_id=%s",
              (user_id, session_id),
          )
          conn.commit()
          affected = cursor.rowcount
      conn.close()
      return affected > 0

  def update_session_title(user_id: int, session_id: str, title: str) -> bool:
      conn = get_db_connection()
      with conn.cursor() as cursor:
          cursor.execute(
              "UPDATE sessions SET title=%s WHERE user_id=%s AND session_id=%s",
              (title, user_id, session_id),
          )
          conn.commit()
          affected = cursor.rowcount
      conn.close()
      return affected > 0
  ```

  注意：pymysql 是同步的，但在 FastAPI 的 `async def` 路由中直接调用同步函数不会阻塞事件循环（pymysql 网络 I/O 很快）。

### 2.3 消息服务

- [ ] **2.3 新建 `app/services/message_service.py`**

  函数清单：

  ```python
  def add_message(session_fk: int, role: str, content: str, tool_name: str = None) -> int
  def get_messages(session_fk: int) -> list[dict]
  def delete_messages(session_fk: int) -> None
  def save_conversation(session_fk: int, messages: list[dict]) -> None
  ```

### 2.4 会话管理 API

- [ ] **2.4 新建 `app/api/session.py`**

  路由前缀：`/api/sessions`

  - `GET /api/sessions` — 获取当前用户的会话列表
  - `POST /api/sessions` — 创建新会话
  - `DELETE /api/sessions/{session_id}` — 删除会话
  - `PUT /api/sessions/{session_id}/title` — 重命名会话

  所有端点都需要 `current_user: dict = Depends(get_current_user)`。

- [ ] **2.4.1 在 `app/main.py` 中注册路由**

  ```python
  from app.api.session import router as session_router
  app.include_router(session_router)
  ```

### 2.5 前端改造

- [ ] **2.5.1 修改前端消息存取逻辑**

  - 页面加载时从 API 拉取会话列表 → 渲染侧边栏
  - 创建新会话时 POST `/api/sessions` → 服务端建记录
  - 切换会话时从 API 拉取历史消息
  - 不再依赖 `localStorage` 存消息（仅保留 JWT token 和当前 session_id）

### 2.6 阶段二测试

- [ ] **2.6.1 手动测试清单**

  1. 用户 A 创建 3 个会话 → API 返回 3 个会话
  2. 用户 B 创建 2 个会话 → API 返回 2 个（看不到 A 的）
  3. 用户 A 在某会话中对话 → 消息存入 MySQL
  4. 刷新页面 → 历史消息还在
  5. 删除会话 → 会话和关联消息一起删除
  6. 换浏览器 → 登录后能看到自己的全部会话

---

## 阶段三：MCP Server 安全加固

**目标**：5 个 MCP Server 均加 token 校验，防止外部直接调用。

**产出物**：
- 5 个 MCP Server 的 token 校验逻辑
- MCPClientManager 自动注入 token
- Docker Compose 安全更新

### 3.1 Token 校验中间件（MCP Server 侧）

- [ ] **3.1.1 为 5 个 MCP Server 各加 token 校验**

  在每个 MCP Server 文件（如 `mcp_servers/db_server.py`）中，新增一个 Starlette 中间件检查 `Authorization` header：

  ```python
  import os
  from starlette.middleware.base import BaseHTTPMiddleware
  from starlette.responses import JSONResponse

  class TokenCheckMiddleware(BaseHTTPMiddleware):
      """校验请求中的 MCP_SECRET_TOKEN。"""
      async def dispatch(self, request, call_next):
          # /health 端点不需要 token
          if request.url.path == "/health":
              return await call_next(request)

          expected = os.getenv("MCP_SECRET_TOKEN", "")
          if not expected:
              # 未配置 token 则放行（向后兼容）
              return await call_next(request)

          token = request.headers.get("Authorization", "").replace("Bearer ", "")
          if token != expected:
              return JSONResponse({"detail": "禁止访问"}, status_code=403)

          return await call_next(request)

  # 在 mcp = FastMCP("XXX") 之后添加
  mcp.add_middleware(TokenCheckMiddleware)
  ```

  需要修改的文件：
  - `mcp_servers/time_server.py`
  - `mcp_servers/db_server.py`
  - `mcp_servers/ppt_server.py`
  - `mcp_servers/docker_server.py`
  - `mcp_servers/search_server.py`

  注意：MCP Server 不能 `from app.config import settings`（独立进程），所以用 `os.getenv("MCP_SECRET_TOKEN")`。

### 3.2 MCP Client 注入 Token

- [ ] **3.2 修改 `app/agent/mcp_client.py`**

  在 `_build_mcp_servers()` 中为每个 server 加上 `headers` 字段：

  ```python
  def _build_mcp_servers():
      token = settings.mcp_secret_token
      headers = {}
      if token:
          headers["Authorization"] = f"Bearer {token}"

      return {
          "time_tool": {
              "transport": "streamable-http",
              "url": settings.mcp_time_url,
              "headers": headers,
          },
          # ... 其余 4 个同理
      }
  ```

  注意：检查 `langchain-mcp-adapters` 的 `MultiServerMCPClient` 是否支持 `headers` 字段。如果不支持，需要改用 `httpx` 自定义 transport 或通过其他方式注入。

### 3.3 Docker Compose 安全更新

- [ ] **3.3 修改 `docker-compose.yml`**

  5 个 MCP Server 的 `ports` 从 `"8003:8003"` 改为 `"127.0.0.1:8003:8003"`（仅绑定本地，不对外暴露）。

### 3.4 DB Server 安全加固

- [ ] **3.4.1 编写 `migrations/004_create_readonly_user.sql`**

  ```sql
  -- 创建只读业务账号（手动在 MySQL 中执行）
  CREATE USER IF NOT EXISTS 'aioperator_readonly'@'%' IDENTIFIED BY '<生成随机密码>';
  -- 给业务表授权（按实际情况添加表名）
  -- GRANT SELECT ON aioperator.some_business_table TO 'aioperator_readonly'@'%';
  FLUSH PRIVILEGES;
  ```

- [ ] **3.4.2 更新 `.env.example` 的黑名单配置**

  ```bash
  DB_BLACKLIST_TABLES=users,sessions,messages
  ```

### 3.5 阶段三测试

- [ ] **3.5.1 手动测试清单**

  1. 无 token curl 访问 `:8004/mcp` → 403
  2. 错误 token curl 访问 → 403
  3. 正确 token curl 访问 → 200
  4. 通过 Agent 对话使用数据库工具 → 正常工作
  5. 通过 Agent 对话尝试 `SELECT * FROM users` → 被安全拒绝

---

## 阶段四：流控 & 并发保护

**目标**：防止 API 被刷，保护 LLM API 调用额度。

**产出物**：
- `app/core/rate_limiter.py` — 流控配置
- `app/services/llm_guard.py` — LLM 请求队列

### 4.1 依赖安装

- [ ] **4.1 更新 `pyproject.toml`**

  新增依赖：
  ```
  "slowapi>=0.1.9",
  ```

  然后运行 `pip install -e .`

### 4.2 Rate Limiter

- [ ] **4.2 新建 `app/core/rate_limiter.py`**

  ```python
  """
  流控模块 — 基于 slowapi 的 API 限流。
  """
  from slowapi import Limiter
  from slowapi.util import get_remote_address

  limiter = Limiter(key_func=get_remote_address)
  ```

- [ ] **4.2.1 修改 `app/main.py`**

  注册 slowapi：
  ```python
  from slowapi import _rate_limit_exceeded_handler
  from slowapi.errors import RateLimitExceeded
  from app.core.rate_limiter import limiter

  app.state.limiter = limiter
  app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
  ```

- [ ] **4.2.2 在各 API 路由上加限流装饰器**

  | 路由 | 限制 | 原因 |
  |------|------|------|
  | `/api/auth/*` | 10次/分钟/IP | 防暴力破解 |
  | `/api/chat`, `/api/chat_stream` | 30次/分钟/用户 | 常规对话 |
  | `/api/agent/chat`, `/api/agent/chat_stream` | 30次/分钟/用户 | 常规对话 |
  | `/api/mcp/chat`, `/api/mcp/chat_stream` | 30次/分钟/用户 | MCP 对话 |
  | `/api/aiops` | 5次/分钟/用户 | 诊断最耗资源 |
  | `/api/upload` | 10次/分钟/用户 | 文件上传 |

  实现方式：在每个路由文件（`chat.py`, `agent.py`, `mcp.py`, `aiops.py`, `auth.py`）的端点函数上加 `@limiter.limit("30/minute")` 装饰器。

### 4.3 LLM 请求队列

- [ ] **4.3 新建 `app/services/llm_guard.py`**

  功能：同一用户最多 3 个并发 LLM 请求，超出则排队等待。

  ```python
  """
  LLM 请求守卫 — 限制单用户并发数，防止 LLM API 被打穿。
  """
  import asyncio
  from collections import defaultdict

  MAX_CONCURRENT_PER_USER = 3

  _user_semaphores: dict[int, asyncio.Semaphore] = {}

  def get_user_semaphore(user_id: int) -> asyncio.Semaphore:
      """获取用户级别的信号量（最多 MAX_CONCURRENT_PER_USER 个并发）。"""
      if user_id not in _user_semaphores:
          _user_semaphores[user_id] = asyncio.Semaphore(MAX_CONCURRENT_PER_USER)
      return _user_semaphores[user_id]
  ```

  在 chat/agent/mcp 的 service 入口处，用 `async with get_user_semaphore(user_id):` 包裹 LLM 调用。

### 4.4 阶段四测试

- [ ] **4.4.1 手动测试清单**

  1. 同一用户 1 秒内发 35 次 `/api/chat` → 第 31 次起返回 429
  2. 429 响应包含 `Retry-After` header
  3. 同一用户同时发 5 个对话请求 → 第 4、5 个排队等待
  4. 不同用户同时发 → 各自独立限流

---

## 阶段五：前端模块化拆分

**目标**：当前 `static/app.js` (约 2200 行) 拆分为多个独立 JS 文件。

**产出物**：
- `static/js/config.js` — 常量（阶段一已创建）
- `static/js/api.js` — HTTP 封装（阶段一已创建）
- `static/js/auth.js` — 登录模块（阶段一已创建）
- `static/js/components/chat.js` — 聊天组件
- `static/js/components/sidebar.js` — 会话侧边栏
- `static/js/components/aiops.js` — 诊断面板
- `static/js/components/upload.js` — 文件上传模块
- `static/app.js` — 瘦身后的主入口

### 5.0 前置检查

- [ ] **5.0 确认阶段一的前端基础设施已完成**

  阶段一已经创建了 `config.js`、`api.js`、`auth.js`、`login.html`。阶段五在此基础上继续拆分业务组件。

### 5.1 拆分组件

> **拆分原则**：每个组件是一个 IIFE，暴露到 `window` 全局对象，避免构建工具。

- [ ] **5.1.1 提取 `static/js/components/chat.js`**

  从 `app.js` 提取以下内容：
  - `sendMessage()` — 发送消息逻辑
  - SSE 流式接收（`fetch` + `ReadableStream`）
  - `renderMessage()` — 渲染消息气泡
  - `switchAgentMode()` — 切换 Agent 模式（RAG/手动/MCP）
  - 消息列表 DOM 操作

  暴露到 `window.ChatComponent = { sendMessage, renderMessage, switchAgentMode }`

- [ ] **5.1.2 提取 `static/js/components/sidebar.js`**

  从 `app.js` 提取以下内容：
  - `renderSessionList()` — 渲染会话列表
  - `createSession()` — 新建会话（POST `/api/sessions`）
  - `deleteSession()` — 删除会话（DELETE `/api/sessions/{id}`）
  - `switchSession()` — 切换会话

  暴露到 `window.SidebarComponent = { renderSessionList, createSession, deleteSession, switchSession }`

- [ ] **5.1.3 提取 `static/js/components/aiops.js`**

  从 `app.js` 提取以下内容：
  - AIOps 诊断面板的 UI 逻辑
  - SSE 事件处理（plan/step_start/step_result/replan/report）
  - 进度展示

  暴露到 `window.AIOpsComponent = { startDiagnose, renderPlan, renderReport }`

- [ ] **5.1.4 提取 `static/js/components/upload.js`**

  从 `app.js` 提取以下内容：
  - 文件上传逻辑
  - 进度条
  - 上传结果展示

  暴露到 `window.UploadComponent = { uploadFile, renderUploadResult }`

- [ ] **5.1.5 精简 `static/app.js`**

  保留内容：
  - 应用初始化（`window.onload`）
  - 全局事件监听
  - 各组件之间的协调/通信

  删除内容：已被各组件提取走的具体实现。

### 5.2 更新 HTML

- [ ] **5.2 修改 `static/index.html`**

  更新 `<script>` 引入顺序：

  ```html
  <script src="js/config.js"></script>
  <script src="js/api.js"></script>
  <script src="js/auth.js"></script>
  <script src="js/components/chat.js"></script>
  <script src="js/components/sidebar.js"></script>
  <script src="js/components/aiops.js"></script>
  <script src="js/components/upload.js"></script>
  <script src="app.js"></script>
  ```

### 5.3 阶段五测试

- [ ] **5.3.1 功能回归测试清单**

  1. RAG Agent 对话 → 正常请求/响应/流式输出
  2. 手动 Agent 对话 → 正常
  3. MCP Agent 对话 → 工具列表正常加载、工具调用正常
  4. AIOps 诊断 → 完整流程（plan → step → replan → report）
  5. 会话管理 → 新建/切换/删除会话
  6. 文件上传 → 上传成功 + 入库
  7. 无 JS 报错（浏览器 Console 干净）

---

## 阶段六：LangSmith 可观测性集成

**目标**：接入 LangSmith 平台，实现 Agent 调用链全量追踪，告别黑盒调试。

**为什么需要 LangSmith？**

当前问题的具体表现：
- 用户说"AI 回答错了"，但不知道是 LLM 本身回答错了、还是工具返回了错误数据、还是 Agent 推理逻辑有误
- 每次对话用了多少 Token？不知道。只能用"20 条消息截断"这种粗糙策略
- 工具调用耗时长？不知道是哪个工具慢、为什么慢
- Agent 在 Planner → Executor → Replanner 之间到底跑了几轮？不知道

LangSmith 解决的问题：
- **Trace 视图**：每一步 LLM 调用/工具调用的输入输出、耗时、Token 用量一目了然
- **工具调用时序图**：Agent 调了哪些工具、顺序、每步耗时，可精确定位慢查询
- **错误定位**：哪一步失败、失败原因、堆栈，不用再翻日志猜
- **成本统计**：每次对话消耗的 Token 数和大致费用
- **免费额度**：3000 trace/月，个人项目足够

**产出物**：
- LangSmith 配置项（环境变量）
- 验证通过的 Trace 截图

### 6.0 前置条件

- [ ] **6.0.1 注册 LangSmith 账号**

  1. 访问 [smith.langchain.com](https://smith.langchain.com)
  2. 用 GitHub / Google 账号注册登录
  3. 创建项目（Project），名称如 `aioperator`
  4. 进入 Settings → API Keys → 创建 API Key
  5. 将 API Key 填入 `.env`：`LANGCHAIN_API_KEY=lsv2_pt_xxx`

### 6.1 配置 LangSmith

- [ ] **6.1.1 修改 `app/config.py`**

  确认阶段一已提前定义以下字段：
  ```python
  langchain_tracing_v2: bool = False
  langchain_endpoint: str = "https://api.smith.langchain.com"
  langchain_api_key: str = ""
  langchain_project: str = "aioperator"
  ```

- [ ] **6.1.2 修改 `app/main.py` 或 `app/core/logger.py`**

  在应用启动时（`setup_logger` 之后、创建 app 之前），设置 LangSmith 环境变量：

  ```python
  import os
  from app.config import settings

  # 启用 LangSmith 追踪
  if settings.langchain_tracing_v2 and settings.langchain_api_key:
      os.environ["LANGCHAIN_TRACING_V2"] = "true"
      os.environ["LANGCHAIN_ENDPOINT"] = settings.langchain_endpoint
      os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
      os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
      logger.info("LangSmith 追踪已启用 — 项目: {}", settings.langchain_project)
  ```

  > LangChain/LangGraph 会自动检测这些环境变量，零代码改动即可启用全量追踪。
  > 不需要在 Agent 代码中加任何 callback 或配置。

- [ ] **6.1.3 更新 `.env.example`**

  ```bash
  # === LangSmith 可观测性 ===
  LANGCHAIN_TRACING_V2=true
  LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
  LANGCHAIN_API_KEY=your-langsmith-api-key
  LANGCHAIN_PROJECT=aioperator
  ```

- [ ] **6.1.4 更新 `pyproject.toml`**

  不需要新增依赖。LangSmith 追踪功能内置于 `langchain` 包中。

### 6.2 验证

- [ ] **6.2.1 验证 LangSmith Trace**

  1. 设置 `.env` 中 `LANGCHAIN_TRACING_V2=true` 并填入真实 API Key
  2. 重启应用
  3. 进行一次完整对话（RAG Agent 或 MCP Agent 模式）
  4. 打开 [smith.langchain.com](https://smith.langchain.com) → 进入 `aioperator` 项目
  5. 确认看到一次完整的 Trace 记录，包含：
     - LLM 调用次数、每次的 prompt/completion
     - Token 用量（prompt_tokens + completion_tokens）
     - 工具调用（如果有）的名称、参数、返回值、耗时
     - 整个 Trace 的延迟分布

### 6.3 进阶（可选）

- [ ] **6.3.1 在 LangSmith 中创建 Dataset 做回归测试**

  收集 10-20 个典型问答对 → 在 LangSmith 中创建 Dataset → 后续改代码后可一键跑评估，验证是否引入退化。

- [ ] **6.3.2 添加自定义 metadata**

  在 service 层调用 `agent.ainvoke()` 时，通过 `config` 传入自定义 metadata（如 user_id、agent_type），方便在 LangSmith 中按维度筛选：

  ```python
  config = {
      "configurable": {"thread_id": thread_id},
      "metadata": {"user_id": user_id, "agent_type": "rag"},
  }
  ```

### 6.4 阶段六测试

- [ ] **6.4.1 验证清单**

  1. LangSmith Dashboard 能看到 RAG Agent 的完整 Trace
  2. LangSmith Dashboard 能看到 MCP Agent 的完整 Trace（含 MCP 远程工具调用）
  3. LangSmith Dashboard 能看到 AIOps 诊断的完整 Trace（Plan-Execute-Replan 各节点）
  4. 多次对话的 Token 用量在 Dashboard 中可统计
  5. `LANGCHAIN_TRACING_V2=false` 时可正常关闭追踪

---

## 阶段七：工程化 & 质量

**目标**：测试覆盖 + 结构化日志 + 多环境配置。

**产出物**：
- `tests/test_security.py`
- `tests/test_auth.py`
- `tests/test_session.py`
- 多环境配置文件
- JSON 日志格式

### 7.1 多环境配置

- [ ] **7.1.1 修改 `app/config.py`**

  新增 `APP_ENV` 字段：
  ```python
  app_env: str = "dev"  # dev / staging / prod
  ```

- [ ] **7.1.2 更新 `.env.example`**

  追加 `APP_ENV=dev`

### 7.2 结构化日志

- [ ] **7.2 修改 `app/core/logger.py`**

  增加 JSON 格式输出选项（通过环境变量 `LOG_FORMAT=json` 切换）：

  ```python
  import json
  from loguru import logger as loguru_logger

  def json_formatter(record):
      """将日志记录序列化为 JSON 一行。"""
      log_entry = {
          "time": record["time"].strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
          "level": record["level"].name,
          "message": record["message"],
          "module": record["name"],
          "function": record["function"],
          "line": record["line"],
      }
      if record["exception"]:
          log_entry["exception"] = str(record["exception"])
      return json.dumps(log_entry, ensure_ascii=False) + "\n"
  ```

### 7.3 测试用例

- [ ] **7.3.1 新建 `tests/test_security.py`**

  测 JWT：

  ```python
  import pytest
  from app.core.security import create_access_token, decode_access_token

  def test_create_and_decode_token():
      token = create_access_token(1)
      payload = decode_access_token(token)
      assert payload is not None
      assert payload["sub"] == "1"

  def test_decode_invalid_token():
      assert decode_access_token("not.a.valid.token") is None

  def test_decode_expired_token():
      # 可通过 monkeypatch settings.jwt_expire_hours 为负值来测试
      pass
  ```

- [ ] **7.3.2 新建 `tests/test_auth.py`**

  测认证 API（不需要真实 GitHub 账号，mock httpx 的 GitHub API 调用）：

  ```python
  import pytest
  from httpx import ASGITransport, AsyncClient
  from app.main import app

  @pytest.mark.asyncio
  async def test_unauthorized_access():
      async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
          resp = await client.post("/api/chat", json={"question": "你好"})
          assert resp.status_code == 401

  @pytest.mark.asyncio
  async def test_public_routes():
      async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
          resp = await client.get("/health")
          assert resp.status_code == 200
  ```

- [ ] **7.3.3 新建 `tests/test_session.py`**

  测会话隔离：

  ```python
  @pytest.mark.asyncio
  async def test_session_isolation():
      # 用户 A 创建会话 → 用户 B 看不到
      # ...
  ```

- [ ] **7.3.4 运行全部测试**

  ```bash
  pip install -e ".[dev]"
  pytest -v
  ```

### 7.4 阶段七测试

- [ ] **7.4.1 验证清单**

  1. `pytest -v` 全部通过
  2. 日志文件输出为 JSON 格式（设置 `LOG_FORMAT=json`）
  3. `.env.example` 包含所有新增配置项
  4. 生产环境 `.env` 可正常启动

---

## 附录 A：涉及文件总览

### 新增文件 (23个)

```
migrations/
├── 001_create_users.sql
├── 002_create_sessions.sql
├── 003_create_messages.sql
└── 004_create_readonly_user.sql

app/
├── core/
│   ├── security.py            # JWT 生成/验证
│   ├── auth_middleware.py      # 认证依赖注入
│   ├── db.py                  # MySQL 连接工具
│   └── rate_limiter.py        # slowapi 流控
├── api/
│   ├── auth.py                # GitHub OAuth / 用户信息 API
│   └── session.py             # 会话管理 API
└── services/
    ├── session_service.py     # 会话 CRUD
    ├── message_service.py     # 消息存取
    └── llm_guard.py           # LLM 请求队列

static/
├── login.html                 # GitHub 登录页面
└── js/
    ├── config.js              # 前端配置常量
    ├── api.js                 # 前端 HTTP 封装
    ├── auth.js                # 前端登录模块
    └── components/
        ├── chat.js            # 聊天组件
        ├── sidebar.js         # 侧边栏组件
        ├── aiops.js           # 诊断组件
        └── upload.js          # 上传组件

tests/
├── test_security.py
├── test_auth.py
└── test_session.py
```

### 修改文件 (21个)

```
app/
├── config.py                  # +JWT/GitHub OAuth/MCP_SECRET/DB/LangSmith 配置项
├── main.py                    # +slowapi + auth 路由 + session 路由 + LangSmith 启动
├── api/
│   ├── chat.py                # +认证依赖 + thread_id 拼接
│   ├── agent.py               # +认证依赖 + thread_id 拼接
│   ├── mcp.py                 # +认证依赖 + thread_id 拼接
│   ├── aiops.py               # +认证依赖 + thread_id 拼接
│   └── file.py                # +认证依赖
├── services/
│   ├── rag_agent_service.py   # +可选：user_id 感知（日志用）
│   ├── manual_agent_service.py
│   ├── mcp_agent_service.py
│   └── aiops_service.py
├── agent/
│   └── mcp_client.py          # +headers Token 注入
└── core/
    └── logger.py              # +JSON 日志格式

mcp_servers/
├── time_server.py             # +TokenCheckMiddleware
├── db_server.py               # +TokenCheckMiddleware
├── ppt_server.py              # +TokenCheckMiddleware
├── docker_server.py           # +TokenCheckMiddleware
└── search_server.py           # +TokenCheckMiddleware

docker-compose.yml             # MCP 端口绑定 127.0.0.1
pyproject.toml                 # +pyjwt, httpx, slowapi
.env.example                   # +认证/DB/GitHub OAuth/MCP_SECRET/LangSmith 配置
static/index.html              # <script> 引入调整 + 登录检查
static/app.js                  # 拆分后变瘦
```

---

## 附录 B：关键设计决策速查

| 决策 | 选择 | 理由 |
|------|------|------|
| 认证方式 | GitHub OAuth（唯一） | 面向开发者，零密码维护成本，安全由 GitHub 保障 |
| 会话保持 | JWT（PyJWT） | 无状态、轻量、不需要 Redis |
| 认证注入 | Depends + 路由级注入（不是全局中间件） | 部分路由需公开，Depends 可精确控制 |
| 用户存储 | MySQL users 表 (pymysql 直接操作，无 ORM) | 复用现有 MySQL，避免引入 SQLAlchemy |
| 会话存储 | MySQL sessions/messages 表 | 统一数据源，支持按 user_id JOIN |
| checkpoint 存储 | 继续 SQLite（每 Agent 独立文件） | 不破坏 LangGraph 现有机制，thread_id 已含 user_id 前缀天然隔离 |
| MCP 安全 | 共享 Secret Token | 内网部署足够，无需 mTLS |
| 可观测性 | LangSmith | LangChain 官方平台，零代码接入，自动追踪 Agent/LLM/Tool 全链路 |
| 前端拆分 | IIFE 暴露到 window（不用 ES Module / webpack） | 保持零构建工具，简单 |
| 限流 | slowapi（内存存储） | 单机够用，无额外组件 |
| 日志 | loguru JSON format（可选切换） | 不换库，只改格式 |
