"""
LLM 工厂 — 封装大语言模型的创建逻辑。

把 LLM 的创建集中在这里的好处：
  1. 切换模型供应商只需改这一个地方（降耦合）
  2. 其他地方不需要知道 base_url、api_key 这些细节
  3. 可以统一加日志、重试、监控等横切逻辑

当前使用阿里云 DashScope 的 OpenAI 兼容端点：
  - 实际上调用的是通义千问（qwen-plus）
  - 但接口格式和 OpenAI 完全一样
  - LangChain 的 ChatOpenAI 直接就能调

思考题回答（对应学习计划第 2 阶段）：
  Q: 为什么原项目用了 ChatQwen 类，这里却用 ChatOpenAI？
  A: ChatQwen 是 langchain-qwq 包的专用类，封装了 Qwen 独特的 API。
     ChatOpenAI 走 OpenAI 兼容接口，更通用。两者都能用，兼容模式的好处是
     换成 DeepSeek / 智谱 / Ollama 等其他平台时，只改 URL 和 Key 就行，
     不需要换类名。专用模式的优势是有可能用到 Qwen 专属特性。
"""

from langchain_openai import ChatOpenAI
from app.config import settings


def create_llm(
    model: str | None = None,
    temperature: float | None = None,
    streaming: bool = False,
) -> ChatOpenAI:
    """创建 LLM 实例。

    参数：
        model:      模型名，不传就用配置里的默认值（qwen-plus）
        temperature: 采样温度，0=确定性强，0.7=有创造性。
                     诊断/规划场景建议 0，对话场景建议 0.7。
        streaming:   是否启用流式输出。
                     注意：这里设为 True 不代表调用时一定是流式，
                     最终是否流式取决于调用 ainvoke() 还是 astream()。

    返回：
        ChatOpenAI 实例，已配置好 base_url 和 api_key。
    """
    return ChatOpenAI(
        model=model or settings.llm_model,
        temperature=temperature if temperature is not None else settings.llm_temperature,
        api_key=settings.dashscope_api_key,
        base_url=settings.llm_base_url,
        streaming=streaming,
    )


def create_llm_non_streaming() -> ChatOpenAI:
    """创建非流式 LLM — `/chat` 接口用，一次性返回完整结果。"""
    return create_llm(streaming=False)


def create_llm_streaming() -> ChatOpenAI:
    """创建流式 LLM — `/chat_stream` 接口用，边生成边返回。

    streaming=True 让底层 HTTP 连接保持流式通道，
    astream() 时能逐 token 获取增量文本。
    """
    return create_llm(streaming=True)
