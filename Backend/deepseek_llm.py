import os
import sys
import json
import asyncio
import threading
from contextlib import asynccontextmanager
from datetime import datetime
from queue import Queue, Empty
from typing import Generator, Optional, Any, Callable, List, Dict, AsyncGenerator

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(errors="replace")

# ✅ [修复] 优先尝试使用 langchain_ollama (LangChain 0.3+ 标准)，否则回退
try:
    from langchain_ollama import ChatOllama
except ImportError:
    try:
        from langchain_community.chat_models import ChatOllama
    except ImportError:
        ChatOllama = None

# 引入 DeepSeek 兼容的 ChatOpenAI
try:
    from langchain_openai import ChatOpenAI
except ImportError:
    try:
        from langchain_community.chat_models import ChatOpenAI
    except ImportError:
        ChatOpenAI = None

# ✅ [修复] 优先使用 langchain_core.messages (LangChain 0.2+)，否则回退到 langchain.schema
try:
    from langchain_core.messages import HumanMessage, SystemMessage
except ImportError:
    try:
        from langchain.schema import HumanMessage, SystemMessage
    except ImportError:
        # Fallback import path for compatibility
        print("❌ [DeepSeek] 无法导入 HumanMessage/SystemMessage")
        HumanMessage = None
        SystemMessage = None

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

# =================================================
# 🔥 配置：LLM 模型设置 (支持环境变量)
# =================================================
# Local Ollama Config
MODEL_NAME = os.getenv("LLM_MODEL_NAME", "qwen2.5-coder")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_NUM_GPU = int(os.getenv("OLLAMA_NUM_GPU", "1"))
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "1h")
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "8192"))
LLM_LOCAL_MAX_CONCURRENT = max(1, int(os.getenv("LLM_LOCAL_MAX_CONCURRENT", "3")))
LLM_CLOUD_MAX_CONCURRENT = max(1, int(os.getenv("LLM_CLOUD_MAX_CONCURRENT", "12")))
LLM_STREAM_SLOT_TIMEOUT_SECONDS = float(os.getenv("LLM_STREAM_SLOT_TIMEOUT_SECONDS", "12"))
OLLAMA_HTTP_CONNECT_TIMEOUT = float(os.getenv("OLLAMA_HTTP_CONNECT_TIMEOUT", "8"))
OLLAMA_HTTP_READ_TIMEOUT = float(os.getenv("OLLAMA_HTTP_READ_TIMEOUT", "120"))
OLLAMA_HTTP_WRITE_TIMEOUT = float(os.getenv("OLLAMA_HTTP_WRITE_TIMEOUT", "30"))
OLLAMA_HTTP_POOL_TIMEOUT = float(os.getenv("OLLAMA_HTTP_POOL_TIMEOUT", "30"))
# Local Router (small) model config
ROUTER_MODEL_NAME = os.getenv("ROUTER_MODEL_NAME", "deepseek-r1:1.5b")
ROUTER_NUM_CTX = int(os.getenv("ROUTER_NUM_CTX", "2048"))
ROUTER_TEMPERATURE = float(os.getenv("ROUTER_TEMPERATURE", "0.1"))
ROUTER_TOP_P = float(os.getenv("ROUTER_TOP_P", "0.9"))
ROUTER_KEEP_ALIVE = os.getenv("ROUTER_KEEP_ALIVE", "1h")

# Cloud DeepSeek Config (Inserted per user request)
DEEPSEEK_URL = "https://api.deepseek.com"
DEEPSEEK_KEY = "***REMOVED_DEEPSEEK_KEY***"
DEEPSEEK_MODEL_NAME = "deepseek-chat"  # V3

print(f"🤖 [LLM Init] Local: {MODEL_NAME} @ {OLLAMA_BASE_URL} (ctx={OLLAMA_NUM_CTX})")
print(
    f"🚦 [LLM Limits] local={LLM_LOCAL_MAX_CONCURRENT}, "
    f"cloud={LLM_CLOUD_MAX_CONCURRENT}, wait={LLM_STREAM_SLOT_TIMEOUT_SECONDS}s"
)

_LOCAL_STREAM_SEMAPHORE = threading.BoundedSemaphore(LLM_LOCAL_MAX_CONCURRENT)
_CLOUD_STREAM_SEMAPHORE = threading.BoundedSemaphore(LLM_CLOUD_MAX_CONCURRENT)

# 初始化 Local LLM (Ollama)
try:
    if ChatOllama:
        llm_local = ChatOllama(
            model=MODEL_NAME,
            base_url=OLLAMA_BASE_URL,
            temperature=0.3,
            top_p=0.9,
            num_gpu=OLLAMA_NUM_GPU,
            # streaming=True, # langchain_ollama 部分版本可能不需要显式传此参数，视情况而定
            # --- performance tuning options ---
            num_ctx=OLLAMA_NUM_CTX,
            keep_alive=OLLAMA_KEEP_ALIVE,
            num_predict=OLLAMA_NUM_PREDICT,
            repeat_penalty=1.1
        )
    else:
        print("❌ [LLM Init] ChatOllama class not found. Please install langchain-ollama.")
        llm_local = None
except Exception as e:
    print(f"❌ [LLM Init Error] Failed to initialize ChatOllama: {e}")
    llm_local = None

# Initialize local router model (small, low-latency)
try:
    if ChatOllama:
        router_llm = ChatOllama(
            model=ROUTER_MODEL_NAME,
            base_url=OLLAMA_BASE_URL,
            temperature=ROUTER_TEMPERATURE,
            top_p=ROUTER_TOP_P,
            num_gpu=OLLAMA_NUM_GPU,
            # streaming=False,
            num_ctx=ROUTER_NUM_CTX,
            keep_alive=ROUTER_KEEP_ALIVE,
            repeat_penalty=1.05
        )
        print(f"🧭 [Router Init] Local Router: {ROUTER_MODEL_NAME} @ {OLLAMA_BASE_URL}")
    else:
        router_llm = None
except Exception as e:
    print(f"⚠️ [Router Init] Failed to initialize router model: {e}")
    router_llm = None


def get_llm_instance(model_type: str = "local", temperature: float = 0.7) -> Any:
    """
    获取 LangChain LLM 实例
    :param model_type: 'local' (Ollama) 或 'cloud' / 'deepseek' (DeepSeek API)
    :param temperature: 温度参数
    """
    if model_type == "cloud" or model_type == "deepseek":
        if not ChatOpenAI:
            print("⚠️ langchain_openai 未安装，无法使用 Cloud 模式")
            if llm_local: return llm_local
            raise ImportError("Missing langchain_openai. Please install it.")

        return ChatOpenAI(
            model=DEEPSEEK_MODEL_NAME,
            openai_api_key=DEEPSEEK_KEY,
            openai_api_base=DEEPSEEK_URL,
            temperature=temperature,
            streaming=True
        )
    else:
        # Local
        if not llm_local:
            raise ValueError("Local LLM not initialized. Please check Ollama and langchain-ollama.")
        return llm_local


def _build_messages(prompt: str, system_prompt: Optional[str] = None):
    """Build prompt messages for chat models."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    base_sys = (
        f"Current System Time: {now}\n"
        "You are an enterprise assistant. Focus on user tasks and avoid inventing identity details."
    )

    if system_prompt:
        base_sys = f"{base_sys}\n{system_prompt}"

    if not SystemMessage or not HumanMessage:
        return [
            {"role": "system", "content": base_sys},
            {"role": "user", "content": prompt}
        ]

    messages = [
        SystemMessage(content=base_sys),
        HumanMessage(content=prompt)
    ]
    return messages


def _build_router_messages(prompt: str, system_prompt: Optional[str] = None):
    base_sys = system_prompt or (
        "You are a router classifier. Output strict JSON only. "
        "Do not explain and do not output Markdown."
    )
    if not SystemMessage or not HumanMessage:
        return [
             {"role": "system", "content": base_sys},
             {"role": "user", "content": prompt}
        ]
    return [SystemMessage(content=base_sys), HumanMessage(content=prompt)]


def _is_local_backend(model_type: str) -> bool:
    mt = (model_type or "").strip().lower()
    return mt in {"", "local", "ollama"}


def _pick_stream_semaphore(model_type: str) -> threading.BoundedSemaphore:
    if _is_local_backend(model_type):
        return _LOCAL_STREAM_SEMAPHORE
    return _CLOUD_STREAM_SEMAPHORE


def _stream_busy_error(model_type: str) -> str:
    backend_label = "local" if _is_local_backend(model_type) else "cloud"
    return (
        f"Model backend is busy ({backend_label}). "
        f"Please retry in a few seconds."
    )


def _acquire_stream_slot_or_raise(model_type: str) -> threading.BoundedSemaphore:
    sem = _pick_stream_semaphore(model_type)
    acquired = sem.acquire(timeout=LLM_STREAM_SLOT_TIMEOUT_SECONDS)
    if not acquired:
        raise RuntimeError(_stream_busy_error(model_type))
    return sem


@asynccontextmanager
async def _acquire_stream_slot_async(model_type: str):
    sem = _pick_stream_semaphore(model_type)
    acquired = await asyncio.to_thread(sem.acquire, True, LLM_STREAM_SLOT_TIMEOUT_SECONDS)
    if not acquired:
        raise RuntimeError(_stream_busy_error(model_type))
    try:
        yield
    finally:
        sem.release()


def _to_ollama_messages(messages: List[Any]) -> List[Dict[str, str]]:
    converted: List[Dict[str, str]] = []
    for msg in messages:
        role = "user"
        content = ""

        if isinstance(msg, dict):
            role = str(msg.get("role") or "user").strip().lower() or "user"
            content = str(msg.get("content") or "")
        else:
            content = str(getattr(msg, "content", "") or "")
            msg_type = str(getattr(msg, "type", "") or "").lower()
            cls_name = msg.__class__.__name__.lower()
            if msg_type == "system" or "system" in cls_name:
                role = "system"
            elif msg_type in {"ai", "assistant"} or "assistant" in cls_name or cls_name.startswith("ai"):
                role = "assistant"
            else:
                role = "user"

        if not content:
            continue
        if role not in {"system", "user", "assistant"}:
            role = "user"
        converted.append({"role": role, "content": content})

    if converted:
        return converted
    return [{"role": "user", "content": ""}]


def _stream_local_ollama_http(
    messages: List[Any],
    stop_checker: Optional[Callable[[], bool]] = None,
) -> Generator[str, None, None]:
    try:
        import requests
    except Exception as e:
        raise RuntimeError(f"requests not available: {e}")

    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    payload = {
        "model": MODEL_NAME,
        "messages": _to_ollama_messages(messages),
        "stream": True,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {
            "temperature": 0.3,
            "top_p": 0.9,
            "num_gpu": OLLAMA_NUM_GPU,
            "num_ctx": OLLAMA_NUM_CTX,
            "num_predict": OLLAMA_NUM_PREDICT,
            "repeat_penalty": 1.1,
        },
    }

    queue: Queue = Queue(maxsize=256)
    stop_event = threading.Event()
    response_ref: Dict[str, Any] = {"response": None}

    def _close_response():
        resp = response_ref.get("response")
        if resp is not None:
            try:
                resp.close()
            except Exception:
                pass

    def _worker():
        try:
            with requests.post(url, json=payload, stream=True, timeout=(8, 120)) as resp:
                response_ref["response"] = resp
                resp.raise_for_status()
                for raw_line in resp.iter_lines(decode_unicode=True):
                    if stop_event.is_set():
                        break
                    if not raw_line:
                        continue
                    try:
                        event = json.loads(raw_line)
                    except Exception:
                        continue
                    if event.get("error"):
                        queue.put(("error", str(event.get("error"))))
                        break

                    chunk = (event.get("message") or {}).get("content") or ""
                    if chunk:
                        queue.put(("chunk", chunk))
                    if event.get("done"):
                        break
        except Exception as e:
            if not stop_event.is_set():
                queue.put(("error", str(e)))
        finally:
            stop_event.set()
            _close_response()
            queue.put(("done", None))

    worker = threading.Thread(target=_worker, daemon=True)
    worker.start()

    try:
        while True:
            if stop_checker and stop_checker():
                stop_event.set()
                _close_response()
                break
            try:
                item_type, payload_item = queue.get(timeout=0.1)
            except Empty:
                continue

            if item_type == "chunk":
                yield payload_item
            elif item_type == "error":
                raise RuntimeError(payload_item)
            elif item_type == "done":
                break
    finally:
        stop_event.set()
        _close_response()
        worker.join(timeout=1.0)


# =================================================
# ✅ 新接口：流式调用 (供 Chat Router 使用)
# =================================================
def ask_llm_stream(
    prompt: str,
    system_prompt: Optional[str] = None,
    model_type: str = "local",
    stop_checker: Optional[Callable[[], bool]] = None,
) -> Generator[str, None, None]:
    """Stream text chunks from selected model backend."""
    if not prompt or not prompt.strip():
        yield "Input message is empty."
        return

    try:
        sem = _acquire_stream_slot_or_raise(model_type)
    except Exception as e:
        yield str(e)
        return

    messages = _build_messages(prompt, system_prompt)

    try:
        if _is_local_backend(model_type):
            try:
                for piece in _stream_local_ollama_http(messages, stop_checker=stop_checker):
                    if stop_checker and stop_checker():
                        break
                    if piece:
                        yield piece
                return
            except Exception as e:
                print(f"[LLM Stream] local HTTP stream failed, fallback to LangChain stream: {e}")

        target_llm = None
        try:
            temp = 1.3 if (model_type == "cloud" or model_type == "deepseek") else 0.3
            target_llm = get_llm_instance(model_type, temperature=temp)
        except Exception as e:
            print(f"[LLM Init Error] {model_type}: {e}")
            yield f"Model init failed ({model_type}): {e}"
            return

        stream_iter = None
        try:
            stream_iter = target_llm.stream(messages)
            for chunk in stream_iter:
                if stop_checker and stop_checker():
                    break
                if hasattr(chunk, "content"):
                    content = chunk.content
                elif isinstance(chunk, str):
                    content = chunk
                else:
                    content = ""
                if content:
                    yield content
        except Exception as e:
            print(f"[LLM Stream Error] ({model_type}): {e}")
            yield f"Model stream failed ({model_type}): {e}"
        finally:
            if stream_iter is not None:
                close_fn = getattr(stream_iter, "close", None)
                if callable(close_fn):
                    try:
                        close_fn()
                    except Exception:
                        pass
    finally:
        sem.release()


async def _stream_local_ollama_http_async(
    messages: List[Any],
    stop_checker: Optional[Callable[[], bool]] = None,
) -> AsyncGenerator[str, None]:
    try:
        import httpx
    except Exception as e:
        raise RuntimeError(f"httpx not available: {e}")

    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat"
    payload = {
        "model": MODEL_NAME,
        "messages": _to_ollama_messages(messages),
        "stream": True,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {
            "temperature": 0.3,
            "top_p": 0.9,
            "num_gpu": OLLAMA_NUM_GPU,
            "num_ctx": OLLAMA_NUM_CTX,
            "num_predict": OLLAMA_NUM_PREDICT,
            "repeat_penalty": 1.1,
        },
    }
    timeout = httpx.Timeout(
        connect=OLLAMA_HTTP_CONNECT_TIMEOUT,
        read=OLLAMA_HTTP_READ_TIMEOUT,
        write=OLLAMA_HTTP_WRITE_TIMEOUT,
        pool=OLLAMA_HTTP_POOL_TIMEOUT,
    )

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", url, json=payload) as resp:
            resp.raise_for_status()
            async for raw_line in resp.aiter_lines():
                if stop_checker and stop_checker():
                    break
                if not raw_line:
                    continue
                try:
                    event = json.loads(raw_line)
                except Exception:
                    continue
                if event.get("error"):
                    raise RuntimeError(str(event.get("error")))
                chunk = (event.get("message") or {}).get("content") or ""
                if chunk:
                    yield chunk
                if event.get("done"):
                    break


async def _iter_sync_stream_async(
    sync_iter: Any,
    stop_checker: Optional[Callable[[], bool]] = None,
) -> AsyncGenerator[Any, None]:
    _iter_done = object()
    iterator = iter(sync_iter)

    def _next_or_done():
        try:
            return next(iterator)
        except StopIteration:
            return _iter_done

    try:
        while True:
            if stop_checker and stop_checker():
                break
            item = await asyncio.to_thread(_next_or_done)
            if item is _iter_done:
                break
            if stop_checker and stop_checker():
                break
            yield item
    finally:
        close_fn = getattr(iterator, "close", None)
        if callable(close_fn):
            try:
                close_fn()
            except Exception:
                pass


async def ask_llm_stream_async(
    prompt: str,
    system_prompt: Optional[str] = None,
    model_type: str = "local",
    stop_checker: Optional[Callable[[], bool]] = None,
) -> AsyncGenerator[str, None]:
    if not prompt or not prompt.strip():
        yield "Input message is empty."
        return

    try:
        async with _acquire_stream_slot_async(model_type):
            messages = _build_messages(prompt, system_prompt)

            if _is_local_backend(model_type):
                try:
                    async for piece in _stream_local_ollama_http_async(messages, stop_checker=stop_checker):
                        if stop_checker and stop_checker():
                            break
                        if piece:
                            yield piece
                    return
                except Exception as e:
                    print(f"[LLM Async Stream] local HTTP stream failed, fallback to LangChain stream: {e}")

            try:
                temp = 1.3 if (model_type == "cloud" or model_type == "deepseek") else 0.3
                target_llm = get_llm_instance(model_type, temperature=temp)
            except Exception as e:
                print(f"[LLM Init Error] {model_type}: {e}")
                yield f"Model init failed ({model_type}): {e}"
                return

            stream_iter = None
            try:
                stream_iter = target_llm.stream(messages)
                async for chunk in _iter_sync_stream_async(stream_iter, stop_checker=stop_checker):
                    if hasattr(chunk, "content"):
                        content = chunk.content
                    elif isinstance(chunk, str):
                        content = chunk
                    else:
                        content = ""
                    if content:
                        yield content
            except Exception as e:
                print(f"[LLM Async Stream Error] ({model_type}): {e}")
                yield f"Model stream failed ({model_type}): {e}"
            finally:
                if stream_iter is not None:
                    close_fn = getattr(stream_iter, "close", None)
                    if callable(close_fn):
                        try:
                            close_fn()
                        except Exception:
                            pass
    except Exception as e:
        yield str(e)


def ask_llm(prompt: str, model_type: str = "local") -> str:
    """
    Synchronous invoke helper.
    """
    try:
        sem = _acquire_stream_slot_or_raise(model_type)
    except Exception as e:
        return str(e)

    try:
        try:
            # Get model instance via get_llm_instance
            target_llm = get_llm_instance(model_type)
        except Exception as e:
            return f"❌ 系统错误：LLM 模型未初始化 ({e})"

        messages = _build_messages(prompt)
        try:
            # invoke 会等待完整生成
            response = target_llm.invoke(messages)
            return response.content
        except Exception as e:
            return f"Model invoke failed: {str(e)}"
    finally:
        sem.release()


# Export default instance for legacy callers (prefer get_llm_instance)
def ask_router(prompt: str, system_prompt: Optional[str] = None) -> str:
    """
    Local small-model router for intent classification.
    Returns raw text (expected JSON).
    """
    if not router_llm:
        print("⚠️ Router model not initialized, returning empty.")
        return ""
    if not prompt or not prompt.strip():
        return ""
    messages = _build_router_messages(prompt, system_prompt)
    try:
        resp = router_llm.invoke(messages)
        return resp.content if hasattr(resp, "content") else str(resp)
    except Exception as e:
         print(f"❌ Router invoke failed: {e}")
         return ""


def warmup_models():
    """Warm up local and router models to reduce first-token latency."""
    try:
        if llm_local:
            if HumanMessage:
                llm_local.invoke([HumanMessage(content="ping")])
            else:
                 llm_local.invoke("ping")
    except Exception as e:
        print(f" [Warmup] Local LLM warmup failed: {e}")
    try:
        if router_llm:
            if HumanMessage:
                router_llm.invoke(_build_router_messages("ping", "You are a router. Output JSON only."))
    except Exception as e:
        print(f" [Warmup] Router warmup failed: {e}")

llm = llm_local

