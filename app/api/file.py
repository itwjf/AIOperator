"""
文件上传 API — 接收运维文档，存入知识库。

上传 → 保存到磁盘 → 文档分割 → 向量化 → 存入 Milvus

后续 RAG 对话时，Agent 就能检索到这些文档的内容。
"""

import os
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.document_splitter import MarkdownSplitter
from app.services.vector_store_manager import add_documents, delete_by_source
from app.core.exceptions import (
    AIOperatorException,
    DocumentProcessError,
    VectorDBError,
    EmbeddingServiceError,
)

router = APIRouter(prefix="/api", tags=["file"])

# 上传文件保存目录
UPLOAD_DIR = "aiops-docs"

# 允许的文件扩展名
ALLOWED_EXTENSIONS = {".md", ".txt"}


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """上传 Markdown 或文本文件到知识库。

    处理流程：
      1. 校验文件类型
      2. 保存到 aiops-docs/ 目录
      3. 如果同名文件已有数据，先删除旧数据
      4. 文档分割 → 向量化 → 存入 Milvus
      5. 返回上传结果

    请求：multipart/form-data，字段名 file
    返回：{"filename": "...", "chunks": 12, "status": "ok"}
    """
    # 校验文件扩展名
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型 {ext}，仅支持 {', '.join(ALLOWED_EXTENSIONS)}",
        )

    try:
        # 保存到磁盘
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        file_path = os.path.join(UPLOAD_DIR, file.filename)

        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        # 路径统一用 / — Windows 的 \ 在 Milvus JSON 表达式中会被误解为转义字符
        normalized_path = file_path.replace("\\", "/")

        # 删旧 → 分割 → 入库
        await delete_by_source(normalized_path)
        splitter = MarkdownSplitter(chunk_size=800, chunk_overlap=100)
        chunks = splitter.split_file(file_path)
        # 把 source 统一为 / 分隔，保证后续查询能匹配
        for chunk in chunks:
            chunk.metadata["source"] = chunk.metadata["source"].replace("\\", "/")
        count = await add_documents(chunks)

        return {
            "filename": file.filename,
            "size_bytes": len(content),
            "chunks": count,
            "status": "ok",
        }
    except DocumentProcessError as e:
        raise HTTPException(status_code=400, detail=e.message)
    except (VectorDBError, EmbeddingServiceError) as e:
        raise HTTPException(status_code=503, detail=e.message)
    except AIOperatorException as e:
        raise HTTPException(status_code=503, detail=e.message)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"文件保存失败: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传处理失败: {e}")
