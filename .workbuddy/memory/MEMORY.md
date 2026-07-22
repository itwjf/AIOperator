# AIOperator 项目记忆

## 项目定位
- **AIOperator** — 用户自研的 LangChain Agent 学习项目（练手项目）
- 基于 LangChain/LangGraph 的智能运维 Agent 系统
- 2026-07-22 已部署到云服务器，出现多个 bug，待逐一排查

## 技术栈（不可变更）
- Python ≥3.11 / FastAPI + uvicorn / sse-starlette
- LLM: 阿里云 DashScope qwen-plus（通过 ChatOpenAI 兼容接口）
- Agent: LangChain create_agent + LangGraph StateGraph
- MCP: FastMCP + streamable-http（端口 8003-8007）
- 向量库: Milvus 2.4（端口 19530）
- 数据库: MySQL 8.0（端口 3306）
- 配置: pydantic-settings（app/config.py 集中管理）
- 日志: loguru（唯一日志库）
- 部署: Docker Compose（单 Dockerfile，多 service）

## 四种 Agent 模式
| 模式 | API 路径 | 实现 | Service 文件 |
|------|---------|------|-------------|
| RAG Agent | /api/chat | create_agent（黑盒） | app/services/rag_agent_service.py |
| 手动 Agent | /api/agent/chat | StateGraph + ToolNode（白盒） | app/services/manual_agent_service.py |
| AIOps 诊断 | /api/aiops | Plan-Execute-Replan | app/services/aiops_service.py |
| MCP Agent | /api/mcp/chat | 本地 + MCP 远程工具混合 | app/services/mcp_agent_service.py |

## 5 个 MCP Server（独立进程）
| 服务 | 端口 | 文件 |
|------|:----:|------|
| Time | 8003 | mcp_servers/time_server.py |
| DB | 8004 | mcp_servers/db_server.py |
| PPT | 8005 | mcp_servers/ppt_server.py |
| Docker | 8006 | mcp_servers/docker_server.py |
| Search | 8007 | mcp_servers/search_server.py |

## 核心架构约束
- **单例模式**：_agent / _memory / _graph / _client / MCPClientManager._instance
- **自愈降级**：外部依赖挂了系统降级而非崩溃（MCP→空列表、Milvus→VectorDBError、LLM→LLMServiceError）
- **三层异常处理**：基础设施层 raise → 服务层 catch 返回友好消息 → API 层 catch raise HTTPException
- **安全模型**：execute_shell 四层防护、execute_query SQL 白名单、calculate eval 白名单
- **流式协议**：统一 SSE 格式 {"type": "content/tool_start/done/error"}

## 关键设计注意点（潜在 bug 区）
1. **MCPClientManager.get_tools() 缓存问题**：_tools 缓存后不会自动刷新，MCP Server 重启需调用 reset()
2. **Windows 路径反斜杠**：Milvus JSON 表达式不认 `\`，需 normalize 为 `/`
3. **DashScope embedding 单次最多 10 条**：需分批处理
4. **MemorySaver 是内存存储**：服务重启后对话历史丢失（云服务器重启可能相关问题）
5. **MCP Server 独立进程**：不能用 `from app.config import settings`，用 os.getenv()
6. **Docker 部署地址覆盖**：docker-compose 用 environment 覆盖 127.0.0.1 为容器名

## 云服务器部署相关（待排查 bug 区）
- 部署方式：Docker Compose（docker-compose.yml）
- 主应用端口：9900
- Docker socket 挂载：/var/run/docker.sock（Docker MCP 需要）
- 数据卷：mysql_data, milvus_data
- 健康检查：Milvus 需 60-90s 启动时间
