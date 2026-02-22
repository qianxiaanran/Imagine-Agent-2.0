import os
import sys
from datetime import datetime
from typing import Generator, Optional, Any

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
        # 最后的兜底
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
            # --- 🚀 性能优化参数 ---
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
    """
    构建消息列表，自动注入当前时间
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 默认系统提示词（注入时间）
    base_sys = (
        f"Current System Time: {now}\n"
        "你是企业智能助手。请专注完成用户任务，避免自我介绍或虚构身份设定。"
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
        "你是一个路由分类器，只负责输出严格 JSON。"
        "不要解释，不要输出 Markdown。"
    )
    if not SystemMessage or not HumanMessage:
        return [
             {"role": "system", "content": base_sys},
             {"role": "user", "content": prompt}
        ]
    return [SystemMessage(content=base_sys), HumanMessage(content=prompt)]


# =================================================
# ✅ 新接口：流式调用 (供 Chat Router 使用)
# =================================================
def ask_llm_stream(prompt: str, system_prompt: Optional[str] = None, model_type: str = "local") -> Generator[
    str, None, None]:
    """
    流式调用接口
    :param prompt: 用户输入
    :param system_prompt: 系统提示词
    :param model_type: 'local' (Qwen/Ollama) 或 'cloud' (DeepSeek API)
    """
    target_llm = None

    try:
        # DeepSeek V3 建议稍高温度以获得更好性能
        temp = 1.3 if (model_type == "cloud" or model_type == "deepseek") else 0.3
        target_llm = get_llm_instance(model_type, temperature=temp)
    except Exception as e:
        print(f"❌ [LLM Init Error]: {e}")
        yield f"⚠️ 模型初始化失败 ({model_type}): {str(e)}"
        return

    if not prompt or not prompt.strip():
        yield "内容不能为空"
        return

    messages = _build_messages(prompt, system_prompt)

    try:
        # 使用 LangChain 的 stream 方法
        for chunk in target_llm.stream(messages):
            if hasattr(chunk, "content"):
                yield chunk.content
            elif isinstance(chunk, str):
                yield chunk
    except Exception as e:
        print(f"❌ [LLM Stream Error] ({model_type}): {e}")
        yield f"⚠️ 模型调用出错 ({model_type})，请检查服务状态。\n错误信息: {str(e)}"


# =================================================
# 🔄 兼容性接口 (供老代码使用)
# =================================================

def ask_llm(prompt: str, model_type: str = "local") -> str:
    """
    同步调用接口
    """
    try:
        # 复用 get_llm_instance
        target_llm = get_llm_instance(model_type)
    except Exception as e:
        return f"❌ 系统错误：LLM 模型未初始化 ({e})"

    messages = _build_messages(prompt)
    try:
        # invoke 会等待完整生成
        response = target_llm.invoke(messages)
        return response.content
    except Exception as e:
        return f"模型调用失败：{str(e)}"


# 导出默认本地实例，供旧代码兼容 (但建议尽量改用 get_llm_instance)
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
