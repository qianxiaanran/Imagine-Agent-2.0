import tempfile
import os
import re
import subprocess
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Tuple, Optional, Iterable, Set
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader, TextLoader
from langchain_community.embeddings import HuggingFaceEmbeddings
from supabase_client import require_supabase

# 文档跨LangChain版本的兼容性导入。
try:
    from langchain_core.documents import Document
except ImportError:
    try:
        from langchain.schema import Document
    except ImportError:
        print("[Documents] failed to import Document")
        Document = None

# 跨 LangChain 版本的文本分割器的兼容性导入。
try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:
    try:
        from langchain.text_splitter import RecursiveCharacterTextSplitter
    except ImportError:
        print("[Documents] failed to import RecursiveCharacterTextSplitter")
        RecursiveCharacterTextSplitter = None

# 默认分离器配置；稍后使用自适应分割逻辑。
if RecursiveCharacterTextSplitter:
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
else:
    text_splitter = None

# 嵌入模型单例
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
            # 对于类似表格的文本，首先用空行分割以保留行。
            sections = [s for s in re.split(r"\n{2,}", content) if s.strip()]

        for section in sections:
            section = section.strip()
            if not section:
                continue
            if splitter and len(section) > chunk_size * 1.4:
                # 第二遍分割，同时保留页面元数据。
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
    # 后备：天真的分裂
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


def _extract_source_candidates(metadata: Optional[dict]) -> Set[str]:
    if not isinstance(metadata, dict):
        return set()
    return {
        _normalize_source_name(metadata.get("source")).lower(),
        _normalize_source_name(metadata.get("file_name")).lower(),
        _normalize_source_name(metadata.get("title")).lower(),
    } - {""}


def _is_generic_summary_query(query: str) -> bool:
    if not query:
        return False
    q = " ".join(str(query).lower().split())
    if not q:
        return False

    summary_keywords = (
        "\u603b\u7ed3", "\u6982\u62ec", "\u6458\u8981", "\u63d0\u70bc",
        "\u68b3\u7406", "\u6982\u8ff0", "\u603b\u89c8",
        "summary", "summarize", "overview", "tldr", "recap",
    )
    trigger = any(k in q for k in summary_keywords)
    if not trigger:
        return False

    broad_keywords = (
        "\u6587\u6863", "\u6587\u4ef6", "\u5168\u6587", "\u5185\u5bb9",
        "\u8fd9\u4e2a", "\u8fd9\u4efd", "\u9644\u4ef6",
        "document", "file", "full text", "full-text", "all",
    )
    # Keep this conservative: mostly short broad prompts like "总结文档".
    return len(q) <= 48 or any(k in q for k in broad_keywords)


def _get_recent_source_names(sb, user_id: str, max_sources: int = 2, scan_rows: int = 240) -> List[str]:
    rows = []
    try:
        rows = (
            sb.table("documents")
            .select("metadata, created_at")
            .eq("metadata->>user_id", user_id)
            .order("created_at", desc=True)
            .limit(scan_rows)
            .execute()
        ).data or []
    except Exception:
        try:
            rows = (
                sb.table("documents")
                .select("metadata, id")
                .eq("metadata->>user_id", user_id)
                .order("id", desc=True)
                .limit(scan_rows)
                .execute()
            ).data or []
        except Exception:
            rows = []

    ordered_sources: List[str] = []
    seen = set()
    for row in rows:
        metadata = dict(row.get("metadata") or {})
        source = (
            _normalize_source_name(metadata.get("source"))
            or _normalize_source_name(metadata.get("file_name"))
            or _normalize_source_name(metadata.get("title"))
        )
        if not source:
            continue
        key = source.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered_sources.append(source)
        if len(ordered_sources) >= max_sources:
            break
    return ordered_sources


def _get_torch_device() -> str:
    """
    Prefer GPU (CUDA); fallback to CPU when unavailable.
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
    Compatibility shim for older torch versions used by transformers.
    """
    try:
        import torch  # noqa: F401
        from torch.utils import _pytree

        if hasattr(_pytree, "_register_pytree_node"):
            base_fn = _pytree._register_pytree_node  # type: ignore[attr-defined]

            def _register_wrapper(*args, **kwargs):
                # 删除旧版本不支持的新 kwargs。
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
                    # 一些旧版本只接受（typ、flatten_fn、unflatten_fn）。
                    if len(args) >= 3:
                        return base_fn(args[0], args[1], args[2])
                    raise

            # 始终换行以避免签名不匹配。
            _pytree.register_pytree_node = _register_wrapper  # type: ignore[attr-defined]
    except Exception:
        # 不要阻塞主流。
        pass


def get_embeddings():
    global _embeddings
    if _embeddings is None:
        # 本地嵌入模型路径。
        local_model_path = r"F:\Enterprise-Intelligent-Office-Agent-2.0\bge-small-zh-v1.5"

        print(f"[Model] loading local embedding model: {local_model_path} ...", flush=True)

        if not os.path.exists(local_model_path):
            print(f"[Model] warning: path not found {local_model_path}", flush=True)

        _ensure_torch_pytree_compat()
        device = _get_torch_device()
        if device == "cuda":
            print("[Model] embedding on GPU (CUDA)", flush=True)
        else:
            print("[Model] embedding fallback to CPU", flush=True)

        def _build_embeddings(target_device: str):
            return HuggingFaceEmbeddings(
                model_name=local_model_path,
                model_kwargs={"device": target_device}
            )

        try:
            _embeddings = _build_embeddings(device)
        except Exception as e:
            # 部分 torch/transformers 组合在 CUDA 路径会触发 meta tensor 迁移异常。
            # 失败时自动回退到 CPU，避免文档上传直接中断。
            err_text = str(e)
            if device == "cuda" and "meta tensor" in err_text.lower():
                print(f"[Model] embedding CUDA init failed, fallback to CPU: {e}", flush=True)
                _embeddings = _build_embeddings("cpu")
            else:
                raise

        print("[Model] BGE-Small (512d) loaded", flush=True)
    return _embeddings


def warmup_embeddings():
    """
    Warm up embedding model to reduce first-request latency.
    """
    try:
        model = get_embeddings()
        _ = model.embed_query("warmup")
        print("[Warmup] embedding warmup completed", flush=True)
    except Exception as e:
        print(f"[Warmup] embedding warmup failed: {e}", flush=True)


def _build_single_doc(text: str, filename: str):
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    return [
        _make_document(
            cleaned,
            {
                "source": filename,
                "file_name": filename,
                "title": filename,
                "page": 0,
                "page_index": 0,
            },
        )
    ]


def _extract_docx_xml_text(path: str) -> str:
    """
    Fallback parser for .docx without external dependencies:
    read `word/document.xml` and flatten text nodes.
    """
    try:
        with zipfile.ZipFile(path) as zf:
            xml_bytes = zf.read("word/document.xml")
        root = ET.fromstring(xml_bytes)
        texts = [node.text for node in root.iter() if node.tag.endswith("}t") and node.text]
        return "\n".join(texts).strip()
    except Exception:
        return ""


def _extract_doc_text_via_cli(path: str) -> str:
    """
    Best-effort parser for legacy .doc using optional system tools.
    """
    for cmd in (["antiword", path], ["catdoc", path]):
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=20,
                check=False,
            )
            out = (proc.stdout or "").strip()
            if proc.returncode == 0 and out:
                return out
        except Exception:
            continue
    return ""


def _load_word_documents(path: str, filename: str, ext: str):
    if ext == ".docx":
        try:
            docs = Docx2txtLoader(path).load()
            if docs and any((getattr(d, "page_content", "") or "").strip() for d in docs):
                return docs
        except Exception:
            pass
        text = _extract_docx_xml_text(path)
        return _build_single_doc(text, filename)

    if ext == ".doc":
        text = _extract_doc_text_via_cli(path)
        if text:
            return _build_single_doc(text, filename)
        print(
            f"[Loader] .doc parsing tool missing for {filename}; "
            f"install antiword/catdoc or convert to .docx.",
            flush=True,
        )
        return []

    return []


def load_documents(file_bytes: bytes, filename: str):
    ext = os.path.splitext(filename)[1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    docs = []
    try:
        if ext == ".pdf":
            docs = PyPDFLoader(tmp_path).load()
        elif ext in {".doc", ".docx"}:
            docs = _load_word_documents(tmp_path, filename, ext)
        else:
            docs = TextLoader(tmp_path).load()
    except Exception as e:
        print(f"[Loader] failed to load file {filename}: {e}", flush=True)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except:
                pass
    return docs


def delete_user_documents(user_id: str):
    """
    Clear all document chunks for a user.
    """
    try:
        print(f"[Delete] clearing documents for user {user_id} ...", flush=True)
        sb = require_supabase()
        # 按元数据中保存的 user_id 进行过滤。
        sb.table("documents").delete().eq("metadata->>user_id", user_id).execute()
        print("[Delete] old documents cleared", flush=True)
        return True
    except Exception as e:
        print(f"[Delete] failed: {e}", flush=True)
        return False


def upload_document_to_vector_store(file_bytes: bytes, filename: str, user_id: str) -> Tuple[bool, str, Optional[str]]:
    """
    Vectorize and persist a document into Supabase.
    Returns (success, message, preview_text).
    """
    try:
        print(f"[Logic] processing file: {filename}", flush=True)
        docs = load_documents(file_bytes, filename)
        if not docs:
            ext = os.path.splitext(filename)[1].lower()
            if ext == ".doc":
                return False, "Legacy .doc parsing unavailable. Convert to .docx or install antiword/catdoc.", None
            return False, "Empty or unreadable document", None
        chunks = _adaptive_split_documents(docs, filename)
        ext = os.path.splitext(filename)[1].lower()
        total_pages = len(docs)
        non_empty_pages = sum(
            1 for d in docs if (getattr(d, "page_content", "") or "").strip()
        )
        print(
            f"[Logic] split into {len(chunks)} chunks "
            f"(pages={total_pages}, non_empty_pages={non_empty_pages})",
            flush=True,
        )

        if not chunks:
            if ext == ".pdf":
                return (
                    False,
                    "PDF 未提取到可用文本（可能是扫描件/图片型PDF或加密PDF）。请先做OCR后再上传。",
                    None,
                )
            return False, "Unable to split document", None

        # 使用前几个块作为直接上下文的预览文本。
        full_text_preview = "\n".join([c.page_content for c in chunks[:5]])
        if len(full_text_preview) > 3000:
            full_text_preview = full_text_preview[:3000] + "...(remaining content in knowledge base)"

        print("[Logic] generating embeddings...", flush=True)
        embeddings_model = get_embeddings()
        texts = [c.page_content for c in chunks]

        # 批量嵌入生成。
        vectors = embeddings_model.embed_documents(texts)

        display_name = _normalize_source_name(filename) or filename
        upload_timestamp = datetime.utcnow().isoformat() + "Z"
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
                "uploaded_at": upload_timestamp,
            })
            records.append({
                "content": text,
                "metadata": {
                    **meta,
                    "user_id": user_id
                },
                "embedding": vector
            })

        print("[Logic] writing chunks to Supabase...", flush=True)
        sb = require_supabase()
        try:
            # 删除同一文件的旧块以避免混合旧/新版本。
            sb.table("documents").delete().eq("metadata->>user_id", user_id).eq("metadata->>source", display_name).execute()
        except Exception as cleanup_err:
            print(f"[Logic] pre-clean same-source chunks failed: {cleanup_err}", flush=True)
        response = sb.table("documents").insert(records).execute()

        inserted_count = len(response.data) if response.data else 0
        print(f"[Logic] write success, rows={inserted_count}", flush=True)

        return True, f"Stored {inserted_count} chunks", full_text_preview

    except Exception as e:
        print(f"[Logic] upload failed: {e}", flush=True)
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
    Write OCR text directly into Supabase documents (with embeddings).
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
        print(f"[Logic] OCR write failed: {e}", flush=True)
        return False, str(e), 0


def _extract_tags_from_query(query: str) -> List[str]:
    if not query:
        return []
    tags = []
    for match in re.findall(r"(?:#|(?:\u6807\u7b7e)[:：=]|tag[:：=])([\w\u4e00-\u9fff_-]+)", query):
        if match and match not in tags:
            tags.append(match)
    return tags


def _normalize_tags(raw_tags) -> List[str]:
    if not raw_tags:
        return []
    if isinstance(raw_tags, str):
        parts = re.split(r"[,，;；\s]+", raw_tags)
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
    """Search user documents from vector store with optional source and tag filters."""
    try:
        print(f"[Search] user={user_id} query={query}", flush=True)

        embeddings_model = get_embeddings()
        query_vector = embeddings_model.embed_query(query)

        source_filter_names = []
        for name in (source_files or []):
            normalized = _normalize_source_name(str(name).strip())
            if normalized and normalized not in source_filter_names:
                source_filter_names.append(normalized)
        source_filter_set = {name.lower() for name in source_filter_names}

        sb = require_supabase()
        summary_focus = (not source_filter_set) and _is_generic_summary_query(query)
        recent_source_names = _get_recent_source_names(sb, user_id, max_sources=2) if summary_focus else []
        recent_source_set = {name.lower() for name in recent_source_names}

        fetch_multiplier = 8 if source_filter_set else (10 if summary_focus else 3)
        fetch_k = max(k * fetch_multiplier, k)
        rpc_params = {
            "query_embedding": query_vector,
            "match_threshold": float(match_threshold),
            "match_count": fetch_k,
            "filter": {"user_id": user_id},
        }

        response = sb.rpc("match_documents", rpc_params).execute()

        result_items = response.data or []
        if not result_items:
            if source_filter_names:
                fallback_docs = _fallback_documents_by_source(sb, user_id, source_filter_names, k)
                if fallback_docs:
                    print(f"[Search] fallback by source hit {len(fallback_docs)} chunks", flush=True)
                    return fallback_docs
            if summary_focus and recent_source_names:
                fallback_docs = _fallback_documents_by_source(sb, user_id, recent_source_names, k)
                if fallback_docs:
                    print(f"[Search] fallback by recent source hit {len(fallback_docs)} chunks", flush=True)
                    return fallback_docs
            print("[Search] no matched chunks", flush=True)
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
                or "document"
            )
            title = _normalize_source_name(metadata.get("title")) or file_name
            page = metadata.get("page", metadata.get("page_number", 0))
            metadata.setdefault("file_name", file_name)
            metadata.setdefault("title", title)
            metadata.setdefault("page", page)
            metadata.setdefault("snippet", _make_snippet(content))

            source_candidates = _extract_source_candidates(metadata)
            if source_filter_set and not (source_candidates & source_filter_set):
                continue

            meta_tags = _normalize_tags(metadata.get("tags"))
            if explicit_tags and (not meta_tags or not any(t in meta_tags for t in explicit_tags)):
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
            if summary_focus and recent_source_set:
                if source_candidates & recent_source_set:
                    boost += 0.22
                else:
                    boost -= 0.08

            score = base + boost
            doc = _make_document(content, metadata)
            scored_docs.append((score, doc))

        if not scored_docs:
            if source_filter_names:
                fallback_docs = _fallback_documents_by_source(sb, user_id, source_filter_names, k)
                if fallback_docs:
                    print(f"[Search] fallback after filter hit {len(fallback_docs)} chunks", flush=True)
                    return fallback_docs
            if summary_focus and recent_source_names:
                fallback_docs = _fallback_documents_by_source(sb, user_id, recent_source_names, k)
                if fallback_docs:
                    print(f"[Search] fallback after summary filter hit {len(fallback_docs)} chunks", flush=True)
                    return fallback_docs
            print("[Search] no results after filters", flush=True)
            return []

        if summary_focus and recent_source_set:
            recent_scored = []
            for score, doc in scored_docs:
                doc_meta = getattr(doc, "metadata", {}) or {}
                if _extract_source_candidates(doc_meta) & recent_source_set:
                    recent_scored.append((score, doc))
            if recent_scored:
                scored_docs = recent_scored
            elif recent_source_names:
                fallback_docs = _fallback_documents_by_source(sb, user_id, recent_source_names, k)
                if fallback_docs:
                    print(f"[Search] summary fallback to recent source returned {len(fallback_docs)} chunks", flush=True)
                    return fallback_docs

        scored_docs.sort(key=lambda x: x[0], reverse=True)
        documents = [doc for _, doc in scored_docs[:k]]

        print(f"[Search] returned {len(documents)} chunks", flush=True)
        return documents

    except Exception as e:
        print(f"[Search] failed: {e}", flush=True)
        return []
