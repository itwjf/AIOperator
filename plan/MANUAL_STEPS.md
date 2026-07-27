# AIOperator 手动操作指南

> 本文档汇总了开发过程中需要你手动执行的步骤（无法由 AI 自动完成的）。
> 换电脑或全新部署时，按本文档逐项执行。

---

## 一、GitHub OAuth App 注册

1. 打开 [GitHub Developer Settings](https://github.com/settings/developers) → OAuth Apps → New OAuth App
2. 填写：
   - Application name: `AIOperator`
   - Homepage URL: `http://127.0.0.1:9900`
   - Authorization callback URL: `http://127.0.0.1:9900/api/auth/github/callback`
3. 注册成功后获取 **Client ID**，点击 "Generate a new client secret" 获取 **Client Secret**
4. 记下这两个值，填入 `.env`（见下方）

---

## 二、`.env` 配置

从 `.env.example` 复制并编辑：

```bash
cp .env.example .env
```

然后编辑 `.env`，填入以下值：

| 变量 | 如何获取 | 说明 |
|------|---------|------|
| `DASHSCOPE_API_KEY` | 阿里云百炼平台 | 已有，保持不动 |
| `GITHUB_CLIENT_ID` | 第一步获取 | GitHub OAuth App Client ID |
| `GITHUB_CLIENT_SECRET` | 第一步获取 | GitHub OAuth App Client Secret |
| `JWT_SECRET_KEY` | 运行下方生成命令 | JWT 签名密钥 |
| `MCP_SECRET_TOKEN` | 运行下方生成命令 | MCP Server 共享密钥 |

生成密钥命令（PowerShell）：

```powershell
python -c "import secrets; print('JWT_SECRET_KEY=' + secrets.token_urlsafe(48))"
python -c "import secrets; print('MCP_SECRET_TOKEN=' + secrets.token_urlsafe(48))"
```

---

## 三、数据库初始化

### 3.1 确保 MySQL 正在运行

```powershell
# 检查 MySQL 服务状态
Get-Service -Name MySQL* | Select-Object Name, Status
```

### 3.2 创建数据库（如果还没有）

```powershell
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS aioperator CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

### 3.3 一键建表

在项目根目录下执行：

```powershell
mysql -u root -p aioperator < migrations\init_all.sql
```

这会依次创建 4 张表：`users`、`sessions`、`messages`，以及只读账号。

---

## 四、创建 MCP Server 只读 MySQL 账号（可选）

如果需要启用 DB Server 的安全加固（第三层防护），执行：

```powershell
# 先编辑 migrations\004_create_readonly_user.sql
# 把 <生成随机密码> 替换为实际密码
mysql -u root -p < migrations\004_create_readonly_user.sql
```

然后将密码配置到 `.env`（DB Server 使用只读账号连接时才需要）。

---

## 五、Python 环境安装

```powershell
# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate

# 安装依赖
pip install -e .
```

---

## 六、启动服务（6 个终端）

```powershell
# 终端 1：MCP 时间服务
python mcp_servers\time_server.py         # :8003

# 终端 2：MCP 数据库服务
python mcp_servers\db_server.py           # :8004

# 终端 3：MCP PPT 生成服务
python mcp_servers\ppt_server.py          # :8005

# 终端 4：MCP Docker 管理服务
python mcp_servers\docker_server.py       # :8006

# 终端 5：MCP Web 搜索服务
python mcp_servers\search_server.py       # :8007

# 终端 6：主应用
python app\main.py                        # :9900
```

---

## 七、验证

```powershell
# 健康检查
curl http://127.0.0.1:9900/health

# Swagger API 文档（浏览器打开）
# http://127.0.0.1:9900/docs

# 登录（浏览器打开）
# http://127.0.0.1:9900
# → 自动跳转登录页 → 点击 GitHub 登录 → 授权 → 回到主页面

# 测试 MCP Token 防护
curl http://127.0.0.1:8004/mcp
# → 应返回 403 或连接拒绝

# 测试 API 认证
curl -X POST http://127.0.0.1:9900/api/chat `
  -H "Content-Type: application/json" `
  -d '{"question":"你好"}'
# → 应返回 401 "未登录，请先登录"
```

---

## 后续新增手动步骤

> 每完成一个开发阶段，AI 会在此处追加新的手动步骤。

| 日期 | 阶段 | 新增手动步骤 |
|------|:--:|------|
| 2026-07-27 | 一 | GitHub OAuth App 注册、`.env` 密钥生成、`users` 建表 |
| 2026-07-27 | 二 | `sessions` + `messages` 建表 |
| 2026-07-27 | 三 | `MCP_SECRET_TOKEN` 配置、只读账号创建、Docker 端口绑定 |
