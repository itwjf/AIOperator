"""
文档分割服务 — 把长文档切成适合检索的小块（Chunk）。

为什么不能整篇存？
  - 长文档包含多个主题，检索精度会下降
  - LLM 上下文窗口有限，塞不进整篇长文档
  - 小块检索能更精准地找到相关段落

两阶段分割策略：
  1. 先按 Markdown 标题切 — 保持每个 chunk 的语义完整性
  2. 再按字符数二次切 — 确保 chunk 不会太长
  3. 合并太短的小碎片 — 避免碎片化过度

参数说明：
  - chunk_size=800: 每个 chunk 约 800 字符
  - chunk_overlap=100: 相邻 chunk 重叠 100 字符
    重叠的作用：当关键信息正好在分割边界上时，
    上一个 chunk 的末尾和下一个 chunk 的开头都能包含它
"""

import re
import uuid
from dataclasses import dataclass, field

from app.core.exceptions import DocumentProcessError


@dataclass
class Document:
    """文档分片的数据结构。

    参考 LangChain 的 Document 类型，保持兼容。
    """
    id: str                        # 唯一 ID
    page_content: str              # 分片的文本内容
    metadata: dict = field(default_factory=dict)  # 元数据（来源、标题层级等）


class MarkdownSplitter:
    """两阶段 Markdown 文档分割器。"""

    def __init__(
        self,
        chunk_size: int = 800,
        chunk_overlap: int = 100,
        min_chunk_size: int = 100,  # 小于这个值的碎片会和前一个合并
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size

    def split_file(self, file_path: str) -> list[Document]:
        """读取文件并分割为 chunk 列表。"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError as e:
            raise DocumentProcessError(detail=f"文件不存在: {file_path}") from e
        except PermissionError as e:
            raise DocumentProcessError(detail=f"没有权限读取文件: {file_path}") from e
        except UnicodeDecodeError as e:
            raise DocumentProcessError(detail=f"文件编码不支持，请使用 UTF-8 编码: {file_path}") from e
        except OSError as e:
            raise DocumentProcessError(detail=f"文件读取失败: {e}") from e
        return self.split_text(content, source=file_path)

    def split_text(self, text: str, source: str = "") -> list[Document]:
        """分割文本。

        第一阶段：按 Markdown 标题（#, ##, ###）分割。
        第二阶段：对每个段落按字符数二次分割。
        第三阶段：合并太短的碎片。
        """
        # === 第一阶段：按 Markdown 标题分割 ===
        sections = self._split_by_headers(text)

        # === 第二阶段：按字符数二次分割 ===
        all_chunks: list[Document] = []
        for section_title, section_text in sections:
            sub_chunks = self._split_by_characters(
                section_text,
                title=section_title,
                source=source,
            )
            all_chunks.extend(sub_chunks)

        # === 第三阶段：合并太小的碎片 ===
        all_chunks = self._merge_short_chunks(all_chunks)

        # 给每个 chunk 生成唯一 ID
        for i, chunk in enumerate(all_chunks):
            chunk.metadata["chunk_index"] = i
            chunk.metadata["total_chunks"] = len(all_chunks)

        return all_chunks

    def _split_by_headers(self, text: str) -> list[tuple[str, str]]:
        """按 Markdown 标题分割。

        返回 [(标题路径, 段落文本), ...]。
        标题路径如 "## CPU 性能排查 > ### 检查 CPU 使用率"。
        """
        lines = text.split("\n")
        sections: list[tuple[str, str]] = []
        current_header = ""
        current_lines: list[str] = []

        for line in lines:
            # 判断是否是 Markdown 标题行
            header_match = re.match(r"^(#{1,3})\s+(.+)", line)
            if header_match:
                # 保存上一个 section
                if current_lines:
                    section_text = "\n".join(current_lines).strip()
                    if section_text:
                        sections.append((current_header, section_text))
                # 开始新的 section
                current_header = header_match.group(2)
                current_lines = []
            else:
                current_lines.append(line)

        # 保存最后一个 section
        if current_lines:
            section_text = "\n".join(current_lines).strip()
            if section_text:
                sections.append((current_header, section_text))

        # 如果没有标题，整个文本作为一个 section
        if not sections:
            sections.append(("", text.strip()))

        return sections

    def _split_by_characters(
        self,
        text: str,
        title: str = "",
        source: str = "",
    ) -> list[Document]:
        """按字符数分割段落，带 overlap。

        滑动窗口：每次前进 (chunk_size - overlap) 个字符。
        """
        if len(text) <= self.chunk_size:
            return [
                Document(
                    id=str(uuid.uuid4()),
                    page_content=text,
                    metadata={
                        "source": source,
                        "title": title,
                    },
                )
            ]

        chunks: list[Document] = []
        start = 0
        while start < len(text):
            end = start + self.chunk_size
            chunk_text = text[start:end]
            chunks.append(
                Document(
                    id=str(uuid.uuid4()),
                    page_content=chunk_text,
                    metadata={
                        "source": source,
                        "title": title,
                    },
                )
            )
            # 下一次窗口起点：前进 chunk_size - overlap
            start += self.chunk_size - self.chunk_overlap
            if end >= len(text):
                break

        return chunks

    def _merge_short_chunks(self, chunks: list[Document]) -> list[Document]:
        """合并太短的 chunk 到前一个 chunk。

        太小的碎片本身没有检索价值，反而浪费存储和计算。
        """
        if len(chunks) <= 1:
            return chunks

        merged: list[Document] = []
        for chunk in chunks:
            if (
                merged
                and len(chunk.page_content) < self.min_chunk_size
                and merged[-1].metadata.get("title") == chunk.metadata.get("title")
            ):
                # 合并到前一个 chunk（同标题下）
                merged[-1].page_content += "\n" + chunk.page_content
            else:
                merged.append(chunk)

        return merged
