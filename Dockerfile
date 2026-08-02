# ============================================
# AIOperator Docker 镜像
# 一个镜像，六个服务：主应用 + 5 个 MCP Server
#
# 多阶段构建：
#   阶段一 frontend-builder：用 Node 构建 Vue 前端，产出 frontend/dist/
#   阶段二 最终镜像：Python 运行时 + FastAPI，直接托管前端 dist
# ============================================

# ---- 阶段一：构建 Vue 前端（仅构建用，不进入最终镜像）----
FROM node:20-slim AS frontend-builder
WORKDIR /frontend

# 先只复制依赖清单，利用 Docker 缓存层（源码改动不重复 npm install）
COPY frontend/package*.json ./
RUN npm install

# 复制前端源码并构建，产物输出到 /frontend/dist
COPY frontend/ ./
RUN npm run build

# ---- 阶段二：最终 Python 镜像 ----
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 先复制依赖文件，利用 Docker 缓存层（改了代码不会重装依赖）
COPY pyproject.toml .

# 安装 Python 依赖（自动从 pyproject.toml 读取，无需手动同步）
RUN python -c "import tomllib; deps = tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']; import subprocess, sys; sys.exit(subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--no-cache-dir'] + deps))"

# 复制应用代码
COPY app/ ./app/
COPY mcp_servers/ ./mcp_servers/

# 复制前端构建产物（FastAPI 静态托管，路径与 app/main.py 的 _FRONTEND_DIST 一致）
COPY --from=frontend-builder /frontend/dist ./frontend/dist

# 创建输出目录
RUN mkdir -p /app/output

# 默认暴露主应用端口
EXPOSE 9900

# 默认启动主应用（可在 docker-compose 中覆盖 command）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9900"]
