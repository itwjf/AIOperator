"""
知识库检索工具 — Agent 可调用的工具函数。

@tool 装饰器将普通 Python 函数变成 LangChain Tool：
  - 函数名 → 工具名
  - docstring → 工具描述（LLM 据此判断何时调用）
  - 参数类型注解 → 工具的输入 Schema

关键设计：response_format="content_and_artifact"
  - content: 返回给 LLM 看的格式化文本
  - artifact: 返回给程序用的原始数据（后续节点可以用）
"""

import asyncio
from langchain_core.tools import tool
from app.services.vector_store_manager import similarity_search
from app.tools._fault import unavailable_hint
from app.core.logger import logger


def _format_search_results(results: list[dict]) -> str:
    """将检索结果格式化为 LLM 可读的上下文文本。

    格式要点：
      - 标注来源文件和标题，让 LLM 能引用出处
      - 添加分隔线，区分不同文档
      - 如果没搜到，给出明确提示而不是空字符串
    """
    if not results:
        return "（未在知识库中找到相关内容）"

    lines = ["以下是知识库中与问题相关的文档片段：", ""]
    for i, r in enumerate(results, 1):
        source_info = f"来源: {r['source']}"
        if r["title"]:
            source_info += f" > {r['title']}"
        lines.append(f"--- 片段 {i}（相似度: {r['score']:.2f}）---")
        lines.append(source_info)
        lines.append(r["content"])
        lines.append("")

    return "\n".join(lines)


@tool(response_format="content_and_artifact")
def retrieve_knowledge(query: str) -> tuple[str, list[dict]]:
    """搜索内部知识库，获取与问题相关的运维文档片段。

    当用户问题涉及以下类型时，应该调用此工具：
      - 技术排查 / 故障诊断
      - 系统运维 / 部署操作
      - 需要查找内部文档或最佳实践
      - 对某个技术概念需要参考内部资料

    参数：
        query: 搜索关键词或问题描述，如 "CPU 使用率过高怎么排查"

    返回：
        (格式化文本, 原始文档列表)
        当知识库服务不可用时，返回 (不可用提示, [])，而不是抛异常，
        让 Agent 能自主选择其他处理方式。
    """
    try:
        # @tool 装饰器默认包装同步函数，内部用 asyncio.run 调异步方法
        results = asyncio.run(similarity_search(query, k=5))
        formatted = _format_search_results(results)
        return formatted, results
    except Exception as e:  # noqa: BLE001 - 工具层兜底所有异常，转成友好提示
        logger.warning("知识库检索失败，已返回不可用提示: {}", e)
        # 不写死"改用某个工具"，只声明"知识库不可用"，由 Agent 根据实际情况决策
        return unavailable_hint("知识库检索"), []
