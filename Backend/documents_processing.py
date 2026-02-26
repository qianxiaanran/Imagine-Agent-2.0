import tempfile
import os
import re
from datetime import datetime
from typing import List, Tuple, Optional, Iterable
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

# 1. 文本切分器配置（保留默认，实际切分使用自适应构建）
if RecursiveCharacterTextSplitter:
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
else:
    text_splitter = None

# 2. Embedding 模型 (单例模式)
_embeddings = None


def _make_document(text: str, metadata: dict):
    if Document:
        return Document(page_content=text, metadata=metadata)

    class SimpleDoc:
        def __init__(self, page_content, metadata):
            self.page_content = page_content
            self.metadata = metadata

    return SimpleDoc(page_content=text, metadata=metadata)


def _estimate_chunk_params(total_len: int) -> tuple[int, int]:
    if total_len >= 200000:
        return 1200, 120
    if total_len >= 80000:
        return 900, 90
    if total_len >= 30000:
        return 700, 70
    if total_len >= 10000:
        return 600, 60
    return 500, 50


def _build_splitter(chunk_size: int, overlap: int):
    if not RecursiveCharacterTextSplitter:
        return None
    separators = ["\n\n", "\n", "。", "；", "，", " ", ""]
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=separators
    )


_CONTRACT_HINT_RE = re.compile(r"(合同|协议|条款|甲方|乙方|第[一二三四五六七八九十百千万0-9]+条)")
_HEADING_RE = re.compile(r"^\s*(第[一二三四五六七八九十百千万0-9]+[条章节]|[一二三四五六七八九十]+、|\d+\.\s+|\d+\)\s+)")


def _is_table_like(text: str) -> bool:
    if not text:
        return False
    return text.count("|") >= 6 or text.count("\t") >= 3


def _split_by_headings(text: str) -> list[str]:
    if not text:
        return []
    lines = text.splitlines()
    sections = []
    current = []
    for line in lines:
        stripped = line.strip()
        if stripped and _HEADING_RE.match(stripped):
            if current:
                sections.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append("\n".join(current).strip())
    return [s for s in sections if s]


def _adaptive_split_documents(docs: Iterable, filename: str) -> list:
    docs = list(docs or [])
    if not docs:
        return []

    total_len = sum(len(getattr(d, "page_content", "") or "") for d in docs)
    chunk_size, overlap = _estimate_chunk_params(total_len)
    splitter = _build_splitter(chunk_size, overlap)

    all_chunks = []
    for doc in docs:
        content = getattr(doc, "page_content", "") or ""
        if not content.strip():
            continue
        metadata = dict(getattr(doc, "metadata", {}) or {})
        page = metadata.get("page", 0)

        is_contract = _CONTRACT_HINT_RE.search(content) is not None
        is_table = _is_table_like(content)

        sections = [content]
        if is_contract:
            split_sections = _split_by_headings(content)
            if len(split_sections) >= 2:
                sections = split_sections
        elif is_table:
            # 表格类：优先按空行切分，避免条目被打散
            sections = [s for s in re.split(r"\n{2,}", content) if s.strip()]

        for section in sections:
            section = section.strip()
            if not section:
                continue
            if splitter and len(section) > chunk_size * 1.4:
                # 使用 splitter 二次拆分，保留 page 元数据
                temp_doc = _make_document(section, metadata)
                for piece in splitter.split_documents([temp_doc]):
                    all_chunks.append(piece)
            else:
                all_chunks.append(_make_document(section, metadata))

    return all_chunks


def _adaptive_split_text(text: str) -> list[str]:
    if not text or not text.strip():
        return []
    total_len = len(text)
    chunk_size, overlap = _estimate_chunk_params(total_len)
    splitter = _build_splitter(chunk_size, overlap)
    if splitter:
        return splitter.split_text(text)
    # fallback: naive split
    return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]


def _make_snippet(text: str, limit: int = 90) -> str:
    if not text:
        return ""
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit] + "..."


def _normalize_source_name(value: Optional[str]) -> str:
    if not value:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    text = text.replace("\\", "/")
    if "/" in text:
        text = text.rsplit("/", 1)[-1]
    return text.strip()


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


def warmup_embeddings():
    """
    预热 Embedding 模型，降低首轮请求延迟。
    """
    try:
        model = get_embeddings()
        _ = model.embed_query("warmup")
        print("✅ [Warmup] Embedding warmup completed", flush=True)
    except Exception as e:
        print(f"⚠️ [Warmup] Embedding warmup failed: {e}", flush=True)


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
        print(f"📂 [Logic] 开始处理文件: {filename}", flush=True)
        docs = load_documents(file_bytes, filename)
        if not docs: return False, "空文件", None

        chunks = _adaptive_split_documents(docs, filename)
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

        display_name = _normalize_source_name(filename) or filename
        records = []
        for i, (text, vector, chunk) in enumerate(zip(texts, vectors, chunks)):
            meta = dict(chunk.metadata or {}) if hasattr(chunk, "metadata") else {}
            raw_page = meta.get("page", meta.get("page_number", 0))
            page_index = None
            page_display = None
            try:
                page_index = int(raw_page)
            except Exception:
                page_index = raw_page
            if isinstance(page_index, int):
                page_display = page_index + 1 if filename.lower().endswith(".pdf") else page_index
            else:
                page_display = page_index

            file_name = (
                _normalize_source_name(meta.get("file_name"))
                or _normalize_source_name(meta.get("source"))
                or display_name
            )
            title = _normalize_source_name(meta.get("title")) or display_name
            meta.update({
                "source": display_name,
                "file_name": file_name,
                "title": title,
                "page": page_display,
                "page_index": page_index,
                "chunk_index": i,
                "snippet": _make_snippet(text),
            })
            records.append({
                "content": text,
                "metadata": {
                    **meta,
                    "user_id": user_id
                },
                "embedding": vector
            })

        print(f"🚀 [Logic] 正在写入 Supabase...", flush=True)
        sb = require_supabase()
        try:
            # Remove older chunks of the same file to avoid mixing old/new versions.
            sb.table("documents").delete().eq("metadata->>user_id", user_id).eq("metadata->>source", display_name).execute()
        except Exception as cleanup_err:
            print(f"⚠️ [Logic] pre-clean same-source chunks failed: {cleanup_err}", flush=True)
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
        chunks = _adaptive_split_text(text)
        if not chunks:
            return False, "empty", 0

        embeddings_model = get_embeddings()
        vectors = embeddings_model.embed_documents(chunks)
        timestamp = datetime.utcnow().isoformat() + "Z"

        records = []
        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            metadata = {
                "source": source,
                "type": "ocr",
                "user_id": user_id,
                "timestamp": timestamp,
                "page": 0,
                "page_index": 0,
                "chunk_index": i,
                "snippet": _make_snippet(chunk),
            }
            if title:
                metadata["title"] = title
                metadata["file_name"] = title
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


def _extract_tags_from_query(query: str) -> List[str]:
    if not query:
        return []
    tags = []
    for match in re.findall(r"(?:#|标签[:：=]|tag[:：=])([\\w\\u4e00-\\u9fff_-]+)", query):
        if match and match not in tags:
            tags.append(match)
    return tags


def _normalize_tags(raw_tags) -> List[str]:
    if not raw_tags:
        return []
    if isinstance(raw_tags, str):
        parts = re.split(r"[，,;；\s]+", raw_tags)
        return [p.strip() for p in parts if p.strip()]
    if isinstance(raw_tags, list):
        return [str(t).strip() for t in raw_tags if str(t).strip()]
    return []


def _title_filename_boost(query: str, title: str) -> float:
    if not query or not title:
        return 0.0
    q = query.lower()
    t = title.lower()
    t = re.sub(r"\.[a-z0-9]{1,5}$", "", t)
    if t and t in q:
        return 0.3
    tokens = [x for x in re.split(r"[^a-z0-9\\u4e00-\\u9fff]+", t) if len(x) >= 2]
    for token in tokens:
        if token in q:
            return 0.18
    return 0.0


def _content_boost(query: str, content: str) -> float:
    if not query or not content:
        return 0.0
    q = query.lower()
    c = content.lower()
    if q in c:
        return 0.1
    return 0.0


def _fallback_documents_by_source(sb, user_id: str, source_names: List[str], k: int) -> List:
    if not source_names:
        return []

    max_items = max(1, int(k))
    docs = []
    seen = set()
    per_source_limit = max(6, max_items * 2)

    for source_name in source_names:
        try:
            response = (
                sb.table("documents")
                .select("content, metadata")
                .eq("metadata->>user_id", user_id)
                .eq("metadata->>source", source_name)
                .limit(per_source_limit)
                .execute()
            )
        except Exception:
            continue

        for row in (response.data or []):
            content = str(row.get("content") or "").strip()
            if not content:
                continue
            metadata = dict(row.get("metadata") or {})
            source = _normalize_source_name(metadata.get("source")) or source_name
            file_name = _normalize_source_name(metadata.get("file_name")) or source
            title = _normalize_source_name(metadata.get("title")) or file_name
            page = metadata.get("page", metadata.get("page_number", 0))
            metadata["source"] = source
            metadata["file_name"] = file_name
            metadata["title"] = title
            metadata.setdefault("page", page)
            metadata.setdefault("snippet", _make_snippet(content))

            dedup_key = (
                metadata.get("source"),
                metadata.get("page_index", metadata.get("page")),
                metadata.get("chunk_index"),
                content[:64],
            )
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            docs.append(_make_document(content, metadata))
            if len(docs) >= max_items:
                return docs

    return docs


def search_user_documents(
    user_id: str,
    query: str,
    k: int = 4,
    match_threshold: float = 0.3,
    tags: Optional[List[str]] = None,
    source_files: Optional[List[str]] = None,
):
    """
    使用原生 RPC 调用检索（增强：标题/文件名加权 + 显式标签过滤）
    """
    try:
        print(f"🔍 [Search] 正在为用户 {user_id} 检索: {query}", flush=True)

        embeddings_model = get_embeddings()
        query_vector = embeddings_model.embed_query(query)

        # 拉更多候选，便于加权与过滤
        source_filter_names = []
        for name in (source_files or []):
            normalized = _normalize_source_name(str(name).strip())
            if normalized and normalized not in source_filter_names:
                source_filter_names.append(normalized)
        source_filter_set = {name.lower() for name in source_filter_names}
        fetch_k = max(k * (8 if source_filter_set else 3), k)
        rpc_params = {
            "query_embedding": query_vector,
            "match_threshold": float(match_threshold),
            "match_count": fetch_k,
            "filter": {"user_id": user_id}
        }

        sb = require_supabase()
        response = sb.rpc("match_documents", rpc_params).execute()

        result_items = response.data or []
        if not result_items:
            if source_filter_names:
                fallback_docs = _fallback_documents_by_source(sb, user_id, source_filter_names, k)
                if fallback_docs:
                    print(f"[Search] fallback by source hit {len(fallback_docs)} chunks", flush=True)
                    return fallback_docs
            print("⚠️ [Search] 未找到匹配的文档片段", flush=True)
            return []

        explicit_tags = tags or _extract_tags_from_query(query)
        explicit_tags = _normalize_tags(explicit_tags)

        scored_docs = []
        for item in result_items:
            content = item.get("content", "") or ""
            metadata = dict(item.get("metadata") or {})

            file_name = (
                _normalize_source_name(metadata.get("file_name"))
                or _normalize_source_name(metadata.get("source"))
                or _normalize_source_name(metadata.get("title"))
                or "文档"
            )
            title = _normalize_source_name(metadata.get("title")) or file_name
            page = metadata.get("page", metadata.get("page_number", 0))
            metadata.setdefault("file_name", file_name)
            metadata.setdefault("title", title)
            metadata.setdefault("page", page)
            metadata.setdefault("snippet", _make_snippet(content))

            if source_filter_set:
                source_candidates = {
                    _normalize_source_name(metadata.get("source")).lower(),
                    _normalize_source_name(metadata.get("file_name")).lower(),
                    _normalize_source_name(metadata.get("title")).lower(),
                }
                if not (source_candidates & source_filter_set):
                    continue

            meta_tags = _normalize_tags(metadata.get("tags"))
            if explicit_tags:
                if not meta_tags or not any(t in meta_tags for t in explicit_tags):
                    continue

            base = item.get("similarity")
            if base is None:
                base = item.get("score")
            if base is None and item.get("distance") is not None:
                try:
                    base = 1 - float(item.get("distance"))
                except Exception:
                    base = 0.0
            base = float(base) if base is not None else 0.0

            boost = 0.0
            boost += _title_filename_boost(query, title)
            boost += _title_filename_boost(query, file_name)
            boost += _content_boost(query, content)
            if explicit_tags:
                boost += 0.08

            score = base + boost
            doc = _make_document(content, metadata)
            scored_docs.append((score, doc))

        if not scored_docs:
            if source_filter_names:
                fallback_docs = _fallback_documents_by_source(sb, user_id, source_filter_names, k)
                if fallback_docs:
                    print(f"[Search] fallback after filter hit {len(fallback_docs)} chunks", flush=True)
                    return fallback_docs
            print("⚠️ [Search] 标签过滤后无结果", flush=True)
            return []

        scored_docs.sort(key=lambda x: x[0], reverse=True)
        documents = [doc for _, doc in scored_docs[:k]]

        print(f"✅ [Search] 检索完成，找到 {len(documents)} 条相关片段", flush=True)
        return documents

    except Exception as e:
        print(f"❌ [Search] 检索发生严重错误: {e}", flush=True)
        return []
