# Agent 工具包
"""
本地工具

包含各种工具类和函数，用于支持 Agent 的功能和操作。
用@tool装饰器注册工具，使其能够被 Agent 调用。
已有的工具包括：
knowledge_base_tool：用于查询知识库中的信息。
time_tool：用于获取当前时间。

在manual_agent_service.py的TOOLS列表中注册这些工具，LLM会自动在docstring读懂工具的功能，并在需要时调用它们。

本质上一个 @tool 装饰器 + 一行列表注册，你的工具就能被 LLM 理解和调用。 
只要 docstring 写清楚「什么时候用、参数是什么意思」，LLM 就能自己判断何时调用。



MCP 远程工具

如果想用MCP远程工具，用 FastMCP 创建一个新的 MCP Server（十几行代码）
在 app/agent/mcp_client.py 的 MCP_SERVERS 字典里加一行配置
MCP 模式的 Agent 自动就能调用它
好处是工具独立部署、独立升级、挂了不影响主服务。
"""