# 📦 AIOperator 部署指南

<div align="center">

**Docker Compose 全栈部署 | 本地开发 | 生产环境配置**

</div>

---

## 目录

- [环境要求](#环境要求)
- [快速部署（Docker Compose）](#快速部署docker-compose)
- [服务架构](#服务架构)
- [环境变量说明](#环境变量说明)
- [本地开发部署](#本地开发部署)
- [常用运维命令](#常用运维命令)
- [故障排查](#故障排查)
- [生产环境建议](#生产环境建议)

---

## 环境要求

### Docker 部署（推荐）

| 依赖 | 最低版本 |
|------|----------|
| Docker | 20.10+ |
| Docker Compose | 2.0+ |
| 空闲内存 | ≥ 8 GB（Milvus 需要 4GB+） |
| 空闲磁盘 | ≥ 10 GB |

### 本地部署

| 依赖 | 版本 | 说明 |
|------|------|------|
| Python | ≥ 3.11 | 运行环境 |
| MySQL | 8.0 | 关系型数据库 |
| Milvus | ≥ 2.4 | 向量数据库 |
| DashScope API Key | — | 阿里云百炼平台 |

---

## 快速部署（Docker Compose）

### 第一步：克隆项目

```bash
git clone https://github.com/itwjf/AIOperator.git
cd AIOperator
```

### 第二步：配置环境变量

```bash
# 从模板创建 .env 文件
cp .env.example .env
```

编辑 `.env`，**至少填写以下两项**：

```bash
# LLM API Key（必填）
DASHSCOPE_API_KEY=sk-your-real-api-key-here

# MySQL root 密码（本地部署时修改，生产环境使用强密码）
DB_PASSWORD=your-strong-password
```

> 其余配置项已有合理默认值，一般不需要修改。完整配置项见 [环境变量说明](#环境变量说明)。

### 第三步：启动服务

```bash
docker compose up -d
```

首次启动会自动：
1. 拉取基础镜像（`python:3.11-slim`、`mysql:8.0`、`milvusdb/milvus:v2.4.17`）
2. 构建 AIOperator 应用镜像（安装 195 个 Python 依赖）
3. 启动所有服务

预计耗时：首次 3–5 分钟，后续增量构建只需 20–30 秒。

### 第四步：验证部署

```bash
# 查看服务状态
docker compose ps
```

预期所有服务状态为 `Up (healthy)`：

```
NAME                   STATUS
aioperator-app         Up
aioperator-mcp-time    Up
aioperator-mcp-db      Up
aioperator-mcp-ppt     Up
aioperator-mysql       Up (healthy)
aioperator-milvus      Up (healthy)
```

```bash
# 健康检查
curl http://localhost:9900/health
# 返回: {"status":"ok"}

# 浏览器访问
# http://localhost:9900
```

### 第五步：使用前端

1. 打开 `http://localhost:9900`
2. 上传运维文档到知识库（侧边栏 → 📄 上传文档）
3. 选择任意模式开始对话

---

## 服务架构

```
                    ┌──────────────────────────┐
                    │    用户浏览器              │
                    │    http://localhost:9900  │
                    └────────────┬─────────────┘
                                 │
                                 ▼
                    ┌──────────────────────────┐
                    │  app (FastAPI 主应用)      │
                    │  Port: 9900               │
                    │  - API 路由                │
                    │  - 前端页面                │
                    │  - LangChain Agent        │
                    └──┬───────┬───────┬───────┘
                       │       │       │
                 ┌─────▼──┐ ┌──▼───┐ ┌▼──────┐
                 │Milvus  │ │MySQL │ │MCP    │
                 │:19530  │ │:3306 │ │Server │
                 └────────┘ └──────┘ └───────┘
                                             │
                    ┌────────────┬───────────┼───────────┬────────────┐
                    │            │           │           │            │
                    ▼            ▼           ▼           ▼            ▼
              ┌──────────┐ ┌──────────┐ ┌──────────┐
              │mcp-time  │ │mcp-db    │ │mcp-ppt   │
              │:8003     │ │:8004     │ │:8005     │
              │时间查询   │ │只读SQL   │ │PPT 生成   │
              └──────────┘ └──────────┘ └──────────┘
```

### 服务清单

| 服务 | 容器名 | 镜像 | 端口 |
|------|------|------|:----:|
| **MySQL** | `aioperator-mysql` | `mysql:8.0` | 3306 |
| **Milvus** | `aioperator-milvus` | `milvusdb/milvus:v2.4.17` | 19530, 9091 |
| **MCP Time** | `aioperator-mcp-time` | 本机构建 | 8003 |
| **MCP DB** | `aioperator-mcp-db` | 本机构建 | 8004 |
| **MCP PPT** | `aioperator-mcp-ppt` | 本机构建 | 8005 |
| **Main App** | `aioperator-app` | 本机构建 | 9900 |

### 依赖关系

```
app ──depends_on──▶ milvus (healthy)
app ──depends_on──▶ mcp-time (started)
app ──depends_on──▶ mcp-db (started)
app ──depends_on──▶ mcp-ppt (started)
mcp-db ──depends_on──▶ mysql (healthy)
```

---

## 环境变量说明

全部配置项及默认值：

### LLM 配置

| 变量 | 默认值 | 说明 |
|------|------|------|
| `DASHSCOPE_API_KEY` | — | **必填**，阿里云百炼 API Key |
| `LLM_MODEL` | `qwen-plus` | 模型名称，可选 `qwen-max`、`deepseek-chat` 等 |
| `LLM_BASE_URL` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | LLM API 地址 |
| `LLM_TEMPERATURE` | `0.7` | 模型温度（0=确定，1=随机） |

### Milvus 向量数据库

| 变量 | 默认值 | 说明 |
|------|------|------|
| `MILVUS_HOST` | `milvus` | Docker 中为容器名，本地开发改为 `127.0.0.1` |
| `MILVUS_PORT` | `19530` | Milvus 端口 |
| `MILVUS_COLLECTION_NAME` | `aiops_knowledge` | 集合名称 |
| `EMBEDDING_MODEL` | `text-embedding-v4` | 向量化模型 |
| `EMBEDDING_DIMENSION` | `1024` | 向量维度 |

### MySQL 数据库

| 变量 | 默认值 | 说明 |
|------|------|------|
| `DB_HOST` | `mysql` | Docker 中为容器名，本地开发改为 `127.0.0.1` |
| `DB_PORT` | `3306` | MySQL 端口 |
| `DB_USER` | `root` | 数据库用户 |
| `DB_PASSWORD` | `root123` | **生产环境务必修改** |
| `DB_NAME` | `aioperator` | 数据库名 |
| `DB_BLACKLIST_TABLES` | — | 敏感表黑名单，逗号分隔 |

### MCP Server 地址

| 变量 | 默认值 | 说明 |
|------|------|------|
| `MCP_TIME_URL` | `http://mcp-time:8003/mcp` | 时间服务地址 |
| `MCP_DB_URL` | `http://mcp-db:8004/mcp` | 数据库服务地址 |
| `MCP_PPT_URL` | `http://mcp-ppt:8005/mcp` | PPT 服务地址 |

### 应用配置

| 变量 | 默认值 | 说明 |
|------|------|------|
| `APP_HOST` | `0.0.0.0` | 监听地址 |
| `APP_PORT` | `9900` | 监听端口 |
| `DEBUG` | `false` | 调试模式，生产环境关闭 |

---

## 本地开发部署

适合需要频繁改代码、调试源码的开发者。

### 启动基础设施

```bash
# 仅启动数据库（不启动应用和 MCP Server）
docker compose up -d mysql milvus
```

### 启动应用和 MCP Server

**Windows / 本地开发**：

分别在多个终端中启动主应用与所需 MCP Server：

```bash
# 分别在不同终端中启动
python mcp_servers/time_server.py    # Port 8003
python mcp_servers/db_server.py     # Port 8004
python mcp_servers/ppt_server.py    # Port 8005
uvicorn app.main:app --reload --port 9900  # 主应用（热重载）
```

### 数据库初始化

DB MCP Server 启动后，需要在 MySQL 中创建数据库和表：

```sql
CREATE DATABASE IF NOT EXISTS aioperator;
USE aioperator;

-- 创建示例表供 Agent 查询
CREATE TABLE IF NOT EXISTS servers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    hostname VARCHAR(100),
    ip VARCHAR(45),
    cpu_cores INT,
    memory_gb INT,
    status VARCHAR(20)
);

INSERT INTO servers VALUES
    (1, 'web-01', '10.0.1.10', 8, 32, 'running'),
    (2, 'web-02', '10.0.1.11', 8, 32, 'running'),
    (3, 'db-master', '10.0.2.50', 16, 64, 'running');
```

---

## 常用运维命令

### 服务管理

```bash
# 启动全部服务
docker compose up -d

# 停止全部服务
docker compose down

# 停止并删除数据（慎用！会清空 MySQL 和 Milvus 数据）
docker compose down -v

# 重启单个服务
docker compose restart app
docker compose restart mcp-db

# 查看服务状态
docker compose ps

# 查看资源占用
docker stats aioperator-app aioperator-mysql aioperator-milvus
```

### 日志查看

```bash
# 实时查看主应用日志
docker compose logs -f app

# 查看特定 MCP 服务日志
docker compose logs -f mcp-db
docker compose logs -f mcp-time
docker compose logs -f mcp-ppt

# 查看 MySQL 日志
docker compose logs mysql

# 查看最近 100 行
docker compose logs --tail=100 app
```

### 进入容器调试

```bash
# 进入主应用容器
docker exec -it aioperator-app bash

# 进入 MySQL
docker exec -it aioperator-mysql mysql -u root -p

# 查看 Milvus 集合
docker exec aioperator-milvus curl -s http://localhost:9091/api/v1/collections
```

### 镜像管理

```bash
# 重新构建镜像（依赖变更后）
docker compose build

# 仅重新构建不启动
docker compose build --no-cache

# 清理未使用的镜像
docker image prune -a
```

---

## 故障排查

### Milvus 启动失败（unhealthy）

**症状**：`docker compose up -d` 后 Milvus 一直显示 `health: starting`，最终 `unhealthy`。

```bash
# 1. 查看日志
docker compose logs milvus

# 2. 清理旧数据卷
docker compose down
docker volume rm aioperator_milvus_data
docker compose up -d

# 3. 确认没有旧的 Milvus 容器残留
docker ps -a --filter "name=milvus"
docker rm -f milvus-etcd milvus-minio  # 如果有旧容器
```

### 端口冲突

```bash
# 查看端口占用（Windows）
netstat -ano | findstr "3306 8003 8004 8005 9900 19530"

# 修改 .env 中的端口配置
APP_PORT=9901
DB_PORT=3307
```

### 应用无法连接 MySQL

```bash
# 进入 MySQL 容器检查
docker exec -it aioperator-mysql mysql -u root -p
# 输入密码（默认 root123）

# 检查数据库是否存在
SHOW DATABASES;
USE aioperator;
SHOW TABLES;

# 检查 .env 中的 DB_HOST 配置
# Docker 部署应为 DB_HOST=mysql（由 docker-compose 自动覆盖）
```

### 应用无法连接 Milvus

```bash
# 检查 Milvus 是否就绪
curl http://localhost:9091/healthz
# 正常返回: OK

# 如果 Milvus 刚启动，可能需要等待 60-90 秒
docker compose logs milvus | grep "successfully"
```

### LLM API 调用失败

```bash
# 检查 API Key 是否正确
docker exec aioperator-app env | grep DASHSCOPE

# 测试 API Key
curl -X POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions \
  -H "Authorization: Bearer $DASHSCOPE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen-plus","messages":[{"role":"user","content":"test"}]}'
```

### 完全重置

```bash
# 停止所有服务并删除所有数据
docker compose down -v

# 清理镜像
docker rmi aioperator-app aioperator-mcp-time aioperator-mcp-db aioperator-mcp-ppt

# 重新开始
docker compose up -d
```

---

## 生产环境建议

### 安全加固

```bash
# 1. 修改所有默认密码
#    .env 中的 DB_PASSWORD 必须改为强密码
#    不要使用 root123、admin 等弱密码

# 2. 关闭对外端口
#    在 docker-compose.yml 中，不需要对外暴露的端口去掉 "8080:8080" 映射
#    只保留 app 的 9900 端口供反向代理使用

# 3. 使用外部 MySQL/Milvus
#    将 docker-compose.yml 中的 mysql/milvus 服务注释掉
#    在 .env 中填写已部署的数据库地址
```

### 性能优化

```yaml
# docker-compose.yml 中增加资源限制
services:
  app:
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 512M

  milvus:
    deploy:
      resources:
        limits:
          memory: 4G
        reservations:
          memory: 2G
```

### 数据持久化

数据已通过 Docker Volume 持久化：

```
aioperator_mysql_data   → MySQL 数据
aioperator_milvus_data  → Milvus 向量数据
```

定期备份：

```bash
# 备份 MySQL
docker exec aioperator-mysql mysqldump -u root -p aioperator > backup.sql

# 备份 Milvus 数据卷
docker run --rm -v aioperator_milvus_data:/data -v $(pwd):/backup alpine tar czf /backup/milvus_backup.tar.gz -C /data .
```

### 反向代理（Nginx）

```nginx
server {
    listen 80;
    server_name aioperator.example.com;

    location / {
        proxy_pass http://127.0.0.1:9900;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 300s;  # SSE 流需要长超时
    }
}
```

### 日志管理

```yaml
# docker-compose.yml 中增加日志轮转
services:
  app:
    logging:
      driver: "json-file"
      options:
        max-size: "50m"
        max-file: "3"
```

### 健康监控

```bash
# 定期检查服务状态
curl -s http://localhost:9900/health
curl -s http://localhost:8003/health
curl -s http://localhost:8004/health
curl -s http://localhost:8005/health

# 设置 cron 定时检查
*/5 * * * * curl -sf http://localhost:9900/health || echo "AIOperator is down" | mail -s "Alert" admin@example.com
```

---

## 相关文档

- [README.md](README.md) — 项目总览和开发指南
- [.env.example](.env.example) — 环境变量模板

---

<div align="center">

**如有部署问题，欢迎提交 [GitHub Issue](https://github.com/itwjf/AIOperator/issues)**

</div>
