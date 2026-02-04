import tempfile
import os
from datetime import datetime
from typing import List, Tuple, Optional
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader, TextLoader
from langchain_community.embeddings import HuggingFaceEmbeddings
from supabase_client import require_supabase

# ✅ [修复] 兼容 Document 类的导入路径
try:
    from langchain_core.documents import Document
except ImportError:
    try:
        from langchain.schema import Document
    except ImportError:
        print("❌ [Documents] 无法导入 Document 类")
        Document = None

# ✅ [修复] 兼容 TextSplitter 类的导入路径
try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:
    try:
        from langchain.text_splitter import RecursiveCharacterTextSplitter
    except ImportError:
        print("❌ [Documents] 无法导入 RecursiveCharacterTextSplitter")
        RecursiveCharacterTextSplitter = None

# 1. 文本切分器配置
if RecursiveCharacterTextSplitter:
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
else:
    text_splitter = None

# 2. Embedding 模型 (单例模式)
_embeddings = None


def _get_torch_device() -> str:
    """
    优先使用 GPU（CUDA），不可用时回退 CPU。
    """
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def _ensure_torch_pytree_compat():
    """
    兼容旧版 torch：transformers 期望 torch.utils._pytree.register_pytree_node
    但旧版仅有 _register_pytree_node，做一次别名补齐即可。
    """
    try:
        import torch  # noqa: F401
        from torch.utils import _pytree

        if hasattr(_pytree, "_register_pytree_node"):
            base_fn = _pytree._register_pytree_node  # type: ignore[attr-defined]

            def _register_wrapper(*args, **kwargs):
                # 兼容 transformers 传入的新参数
                for key in (
                    "serialized_type_name",
                    "to_dumpable_context",
                    "from_dumpable_context",
                    "flatten_with_keys_fn",
                ):
                    kwargs.pop(key, None)
                try:
                    return base_fn(*args, **kwargs)
                except TypeError:
                    # 某些老版本签名只接受 (typ, flatten_fn, unflatten_fn)
                    if len(args) >= 3:
                        return base_fn(args[0], args[1], args[2])
                    raise

            # 无论是否已存在，都用 wrapper 覆盖，防止参数不匹配
            _pytree.register_pytree_node = _register_wrapper  # type: ignore[attr-defined]
    except Exception:
        # 不阻断主流程，后续由实际报错提示
        pass


def get_embeddings():
    global _embeddings
    if _embeddings is None:
        # ✅ 本地模型路径
        local_model_path = r"F:\Enterprise-Intelligent-Office-Agent-2.0\bge-small-zh-v1.5"

        print(f"📥 [Model] 正在加载本地 Embedding 模型: {local_model_path} ...", flush=True)

        if not os.path.exists(local_model_path):
            print(f"❌ [Model] 警告：找不到路径 {local_model_path}", flush=True)

        _ensure_torch_pytree_compat()
        device = _get_torch_device()
        if device == "cuda":
            print("✅ [Model] Embedding 使用 GPU (CUDA)", flush=True)
        else:
            print("⚠️ [Model] Embedding 未检测到 GPU，回退 CPU", flush=True)

        _embeddings = HuggingFaceEmbeddings(
            model_name=local_model_path,
            model_kwargs={"device": device}
        )
        print("✅ [Model] BGE-Small (512维) 加载完成", flush=True)
    return _embeddings


def load_documents(file_bytes: bytes, filename: str):
    ext = os.path.splitext(filename)[1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    docs = []
    try:
        if ext == ".pdf":
            docs = PyPDFLoader(tmp_path).load()
        elif ext == ".docx":
            docs = Docx2txtLoader(tmp_path).load()
        else:
            docs = TextLoader(tmp_path).load()
    except Exception as e:
        print(f"❌ [Loader] 文件加载失败 {filename}: {e}", flush=True)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except:
                pass
    return docs


def delete_user_documents(user_id: str):
    """
    🧹 清空该用户的所有文档数据
    """
    try:
        print(f"🧹 [Delete] 正在清空用户 {user_id} 的旧文档...", flush=True)
        sb = require_supabase()
        # 使用 metadata 字段中的 user_id 进行过滤删除
        # 注意：这里假设 Supabase 支持 ->> 语法，如果报错可能需要改用 RPC
        sb.table("documents").delete().eq("metadata->>user_id", user_id).execute()
        print(f"✅ [Delete] 旧文档清理完毕", flush=True)
        return True
    except Exception as e:
        print(f"⚠️ [Delete] 清理失败 (可能是首次上传): {e}", flush=True)
        return False


def upload_document_to_vector_store(file_bytes: bytes, filename: str, user_id: str) -> Tuple[bool, str, Optional[str]]:
    """
    手动向量化并写入 Supabase。
    返回: (Success, Message, PreviewText)
    PreviewText 用于首次上传时直接给 LLM 提供上下文，解决"总结全文"类问题检索不到的尴尬。
    """
    try:
        if not text_splitter:
            return False, "TextSplitter 未初始化", None

        print(f"📂 [Logic] 开始处理文件: {filename}", flush=True)
        docs = load_documents(file_bytes, filename)
        if not docs: return False, "空文件", None

        chunks = text_splitter.split_documents(docs)
        print(f"✂️  [Logic] 已切分为 {len(chunks)} 个片段", flush=True)

        if not chunks: return False, "无法切分", None

        # ✨ 提取前 N 个字符作为预览 (热数据)
        # 通常取前 2000-3000 字符足够做摘要
        full_text_preview = "\n".join([c.page_content for c in chunks[:5]])
        if len(full_text_preview) > 3000:
            full_text_preview = full_text_preview[:3000] + "...(剩余内容在知识库中)"

        print("🧠 [Logic] 正在生成向量...", flush=True)
        embeddings_model = get_embeddings()
        texts = [c.page_content for c in chunks]

        # 批量生成向量
        vectors = embeddings_model.embed_documents(texts)

        records = []
        for i, (text, vector, chunk) in enumerate(zip(texts, vectors, chunks)):
            records.append({
                "content": text,
                "metadata": {
                    "source": filename,
                    "user_id": user_id,
                    "page": chunk.metadata.get("page", 0)
                },
                "embedding": vector
            })

        print(f"🚀 [Logic] 正在写入 Supabase...", flush=True)
        sb = require_supabase()
        response = sb.table("documents").insert(records).execute()

        inserted_count = len(response.data) if response.data else 0
        print(f"✅ [Logic] 写入成功! 行数: {inserted_count}", flush=True)

        return True, f"成功存入 {inserted_count} 个片段", full_text_preview

    except Exception as e:
        print(f"❌ [Logic] 上传错误: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return False, str(e), None


def store_text_to_vector_store(
    text: str,
    user_id: str,
    source: str = "ocr",
    title: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Tuple[bool, str, int]:
    """
    直接写入 OCR 文本到 Supabase documents（含向量）
    """
    if not text or not text.strip():
        return False, "empty", 0
    try:
        if not text_splitter:
            return False, "TextSplitter 未初始化", 0

        chunks = text_splitter.split_text(text)
        if not chunks:
            return False, "empty", 0

        embeddings_model = get_embeddings()
        vectors = embeddings_model.embed_documents(chunks)
        timestamp = datetime.utcnow().isoformat() + "Z"

        records = []
        for chunk, vector in zip(chunks, vectors):
            metadata = {
                "source": source,
                "type": "ocr",
                "user_id": user_id,
                "timestamp": timestamp,
            }
            if title:
                metadata["title"] = title
            if session_id:
                metadata["session_id"] = session_id

            records.append({
                "content": chunk,
                "metadata": metadata,
                "embedding": vector
            })

        sb = require_supabase()
        response = sb.table("documents").insert(records).execute()
        inserted = len(response.data) if response.data else 0
        return True, "ok", inserted
    except Exception as e:
        print(f"⚠️ [Logic] OCR 写入失败: {e}", flush=True)
        return False, str(e), 0


def search_user_documents(user_id: str, query: str, k: int = 4, match_threshold: float = 0.3):
    """
    使用原生 RPC 调用检索
    """
    try:
        print(f"🔍 [Search] 正在为用户 {user_id} 检索: {query}", flush=True)

        embeddings_model = get_embeddings()
        query_vector = embeddings_model.embed_query(query)

        rpc_params = {
            "query_embedding": query_vector,
            "match_threshold": float(match_threshold),
            "match_count": k,
            "filter": {"user_id": user_id}
        }

        sb = require_supabase()
        response = sb.rpc("match_documents", rpc_params).execute()

        documents = []
        if response.data:
            for item in response.data:
                # 兼容性处理：如果 Document 加载失败，使用简单的 dict 或对象
                if Document:
                    doc = Document(
                        page_content=item.get("content", ""),
                        metadata=item.get("metadata", {})
                    )
                else:
                    # 极简兜底对象
                    class SimpleDoc:
                        def __init__(self, page_content, metadata):
                            self.page_content = page_content
                            self.metadata = metadata
                    doc = SimpleDoc(
                        page_content=item.get("content", ""),
                        metadata=item.get("metadata", {})
                    )
                documents.append(doc)

            print(f"✅ [Search] 检索完成，找到 {len(documents)} 条相关片段", flush=True)
            return documents
        else:
            print("⚠️ [Search] 未找到匹配的文档片段", flush=True)
            return []

    except Exception as e:
        print(f"❌ [Search] 检索发生严重错误: {e}", flush=True)
        return []
