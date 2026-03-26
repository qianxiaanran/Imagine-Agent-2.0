import json
import re
import hashlib
from datetime import datetime
from typing import Annotated, Literal, List, Dict, Any, Optional
from typing_extensions import TypedDict

# ✅ [修复] 兼容 Message 类的导入路径
try:
    from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
except ImportError:
    try:
        from langchain.schema import BaseMessage, HumanMessage, AIMessage
    except ImportError:
        print("❌ [LangGraph] 无法导入 BaseMessage/HumanMessage/AIMessage")
        BaseMessage = None
        HumanMessage = None
        AIMessage = None

from langgraph.graph import StateGraph, END

# 复用现有组件
from deepseek_llm import llm, ask_llm
from database_manager import db_manager, DB_NAME as DEFAULT_DB_NAME, ALLOWED_TABLES
from documents_processing import search_user_documents

# 可选：长期记忆写入（复用 documents 表）
try:
    from documents_processing import get_embeddings  # type: ignore
    from supabase_client import require_supabase  # type: ignore
except Exception:
    get_embeddings = None
    require_supabase = None

from context_hub import ContextHub


# ============================================================
# 4. Memory 系统 (核心架构升级)
# ============================================================

class ConversationBuffer:
    """
    第一层：工作记忆 (Working Memory)

    目标：
    - 只保留“最近且干净”的对话片段，避免把工具/调试日志塞进上下文导致跑偏
    - 用 token 预算裁剪，防止上下文爆炸
    """

    def __init__(self, max_tokens: int = 2000):
        self.max_tokens = max_tokens
        self.messages: List[str] = []

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """轻量 token 估算（不依赖 tiktoken）。"""
        if not text:
            return 0
        s = str(text)
        # 英文大致 4 字符≈1 token；中文按字符数更接近 token
        return max(len(s.split()), int(len(s) / 4) + 1)

    @staticmethod
    def _sanitize_text(text: str) -> str:
        """清洗文本：去掉工具/调试/思考日志，避免污染上下文。"""
        if text is None:
            return ""
        s = str(text)

        # 特殊 token
        s = s.replace("<|im_start|>", "").replace("<|im_end|>", "")

        # 前端/中间层 meta，例如：Assistant: {"modelId":0,"mode":"general"}
        s = re.sub(r'^\s*Assistant:\s*\{.*?\}\s*$', '', s, flags=re.MULTILINE)

        # Explainable AI / 工具思考日志
        s = re.sub(r'^\s*>\s*🧠.*$', '', s, flags=re.MULTILINE)
        s = re.sub(r'^\s*🧠.*$', '', s, flags=re.MULTILINE)

        # ReAct 过程日志
        s = re.sub(r'^\s*ReAct\s*(思考|行动|观察).*$', '', s, flags=re.MULTILINE)

        # 各种调试图标日志行（如：🚦 Router、🗄️ DB Agent 等）
        s = re.sub(r'^\s*[🔍🗄️📅🚦⚙️📢].*$', '', s, flags=re.MULTILINE)

        # 空行收敛
        s = re.sub(r'\n{3,}', '\n\n', s)
        return s.strip()

    def count_tokens(self) -> int:
        return sum(self._estimate_tokens(m) for m in self.messages)

    def add_message(self, message: str):
        if not message:
            return
        self.messages.append(message)
        while self.count_tokens() > self.max_tokens:
            self.messages.pop(0)

    def _prune_by_tokens(self, lines: List[str]) -> List[str]:
        total = 0
        kept: List[str] = []
        for line in reversed(lines):
            t = self._estimate_tokens(line)
            if kept and total + t > self.max_tokens:
                break
            if not kept and t > self.max_tokens:
                # 单条超预算：硬截断
                approx_chars = max(200, int(self.max_tokens * 4))
                kept.append(line[:approx_chars])
                break
            kept.append(line)
            total += t
        return list(reversed(kept))

    def format_history(self, messages: List[BaseMessage], limit: int = 6) -> str:
        """将消息对象列表转换为字符串，供 Prompt 使用"""
        if not messages:
            return "（无历史对话）"

        recent = messages[-limit:]
        lines: List[str] = []
        for m in recent:
            if HumanMessage and isinstance(m, HumanMessage):
                role = "User"
            elif AIMessage and isinstance(m, AIMessage):
                role = "Assistant"
            else:
                # 兜底逻辑
                role = "User" if m.type == "human" else "Assistant"

            content = self._sanitize_text((m.content or "").strip())
            if content:
                lines.append(f"{role}: {content}")

        lines = self._prune_by_tokens(lines)
        return "\n".join(lines) if lines else "（无历史对话）"


class SummaryMemory:
    """
    第二层：短期记忆 (Short-term Memory)

    目标：
    - 不要每次都总结（贵+慢）
    - 但也不能永远不总结（会遗忘+复读）
    - 重点：摘要里绝对不能混入工具日志/调试输出
    """

    def __init__(self, flush_every: int = 10, window_limit: int = 12):
        self.flush_every = flush_every
        self.window_limit = window_limit
        # 存储结构：{"summary": str, "recent": List[str], "seen": set, "last_digest": str}
        self._store: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _key(user_id: str, session_id: str) -> str:
        return f"{user_id}::{session_id}"

    def add_message(
            self,
            user_id: str,
            session_id: str,
            role: str,
            message: str,
            current_summary: str,
            model_type: str = "local"
    ) -> str:
        if not message:
            return current_summary

        k = self._key(user_id, session_id)
        if k not in self._store:
            self._store[k] = {
                "summary": current_summary or "",
                "recent": [],
                "seen": set(),
            }

        mem = self._store[k]
        summary = mem.get("summary") or current_summary or ""

        clean = ConversationBuffer._sanitize_text(message.strip())
        if not clean:
            return summary

        sig = hashlib.sha1(f"{role}:{clean}".encode("utf-8", errors="ignore")).hexdigest()
        if sig in mem["seen"]:
            return summary
        mem["seen"].add(sig)
        mem["recent"].append(f"{role}: {clean}")

        if len(mem["recent"]) < self.flush_every:
            return summary

        text_to_summarize = "\n".join(mem["recent"]).strip()
        if not text_to_summarize:
            return summary

        prompt = (
            "请把对话中稳定且重要的信息压缩成简短摘要，"
            "只保留事实/偏好/约束，不要包含工具日志。\n\n"
            f"旧摘要:\n{summary}\n\n新对话:\n{text_to_summarize}\n\n输出合并后的新摘要:"
        )

        try:
            new_summary = ask_llm(prompt, model_type=model_type).strip()
            if new_summary:
                mem["summary"] = new_summary[:1200]
                mem["recent"] = []
                return mem["summary"]
        except Exception:
            return summary

        return summary

    def update_from_messages(
            self,
            user_id: str,
            session_id: str,
            current_summary: str,
            messages: List[BaseMessage],
            model_type: str = "local"  # allow caller to choose the summarization backend
    ) -> str:
        if not messages:
            return current_summary

        summary = current_summary
        window = messages[-self.window_limit:]
        for m in window:
            if HumanMessage and isinstance(m, HumanMessage):
                role = "user"
            else:
                role = "assistant"
            summary = self.add_message(
                user_id=user_id,
                session_id=session_id,
                role=role,
                message=str(m.content or ""),
                current_summary=summary,
                model_type=model_type
            )

        return summary


class VectorMemory:
    """
    第三层：长期记忆 (Long-term Memory)

    - 检索：沿用 search_user_documents（你现有的向量检索/文档检索管线）
    - 存储：可选（如果 embeddings + supabase 可用则写入 documents 表）
    """

    MEMORY_SOURCE = "__long_term_memory__"

    def _can_store(self) -> bool:
        return get_embeddings is not None and require_supabase is not None

    def store(self, user_id: str, text: str, importance: int = 3):
        if not text or not text.strip():
            return False, "empty"
        if not self._can_store():
            return False, "vector_store_disabled"
        try:
            embeddings_model = get_embeddings()
            vector = embeddings_model.embed_query(text)

            record = {
                "content": text,
                "metadata": {
                    "source": self.MEMORY_SOURCE,
                    "user_id": user_id,
                    "type": "memory",
                    "scope": "user_private",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "importance": int(max(1, min(5, importance))),
                },
                "embedding": vector,
            }
            sb = require_supabase()
            sb.table("documents").insert([record]).execute()
            return True, "ok"
        except Exception as e:
            return False, str(e)

    def retrieve(self, user_id: str, query: str, top_k: int = 5):
        return search_user_documents(user_id, query, k=top_k, search_scope="memory_private")

    def maybe_store_from_messages(self, user_id: str, messages: List[BaseMessage]):
        """轻量触发：只把更可能长期有用的信息写入长期记忆，避免污染。"""
        if user_id == "anonymous":
            return
        if not messages:
            return
        last = messages[-1]

        # 兼容性检查
        is_human = (HumanMessage and isinstance(last, HumanMessage)) or (last.type == "human")
        if not is_human:
            return

        text = ConversationBuffer._sanitize_text((last.content or "").strip())
        if not text:
            return

        triggers = ["从现在起", "以后", "记住", "不要", "必须", "我的项目", "我想", "我叫"]
        if not any(k in text for k in triggers):
            return

        importance = 3
        if any(k in text for k in ["从现在起", "以后", "必须", "不要", "记住"]):
            importance = 5

        self.store(user_id=user_id, text=text, importance=importance)


# 实例化
memory_buffer = ConversationBuffer()
memory_summary = SummaryMemory()
memory_vector = VectorMemory()


# ============================================================
# 定义 Graph 状态
# ============================================================

class AgentState(TypedDict):
    hub: ContextHub
    messages: List[BaseMessage]
    intent: str
    agent_output: Dict[str, Any]
    plan: Optional[List[str]]
    final_response: str
    explain_steps: List[str]
    # ✅ 新增：存储 RAG 检索到的来源 (Source Files)
    sources: Optional[List[Dict[str, Any]]]
    # ✅ 新增：模型后端选择
    model_backend: str


# ============================================================
# 辅助函数
# ============================================================

def parse_action_json(llm_output: str) -> Dict:
    try:
        match = re.search(r"```json\s*([\s\S]*?)\s*```", llm_output)
        if match:
            return json.loads(match.group(1))
        return json.loads(llm_output)
    except:
        return {}


def _make_snippet(text: Optional[str], limit: int = 90) -> str:
    if not text:
        return ""
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit] + "..."


def _build_source_meta(meta: Dict[str, Any], content: Optional[str]) -> Dict[str, Any]:
    file_name = (
        meta.get("file_name")
        or meta.get("source")
        or meta.get("filename")
        or meta.get("title")
        or "文档"
    )
    src_type = meta.get("type")
    page_display = None
    if src_type != "ocr":
        file_lower = str(file_name).lower()
        is_pdf = file_lower.endswith(".pdf")
        page_index = meta.get("page_index")
        if page_index is not None:
            try:
                page_display = int(page_index) + 1
            except Exception:
                page_display = None
        else:
            raw_page = meta.get("page") if "page" in meta else meta.get("page_number")
            try:
                raw_page = int(raw_page)
                if is_pdf and raw_page >= 0:
                    page_display = raw_page + 1
                else:
                    page_display = raw_page if raw_page > 0 else 1
            except Exception:
                page_display = None

    title = file_name
    if page_display:
        title = f"{file_name} · 第{page_display}页"

    snippet = meta.get("snippet") or _make_snippet(content)
    source = {
        "title": title,
        "file_name": file_name,
        "page": page_display,
        "snippet": snippet,
    }
    if meta.get("source"):
        source["source"] = meta.get("source")
    if src_type:
        source["type"] = src_type
    return source


# ============================================================
# 第一层：路由器
# ============================================================

def router_node(state: AgentState):
    print("🚦 [Layer 1] Router Analyzing...")
    hub = state["hub"]
    messages = state["messages"]
    model_backend = state.get("model_backend", "local")  # 获取用户选择的模型后端

    # === 手动模式锁定：当用户在前端手动选择数据库/文档模式时，强制只走对应 Agent ===
    forced = getattr(hub, "forced_intent", None)
    if forced in ("database", "rag", "planner", "chat"):
        print(f"🚦 [Router] Manual Lock -> {forced}")
        return {"intent": forced, "explain_steps": [f"手动模式锁定: {forced}"]}

    recent_history = memory_buffer.format_history(messages, limit=4)

    # === 规则兜底：写作/改写类请求优先走 chat，避免被上一轮数据库/工具内容误导 ===
    q = (hub.query or "").strip()
    writing_kw = ["小作文", "作文", "写一篇", "写一段", "扩写", "缩短", "改写", "润色", "字数", "写一个", "写文章"]
    db_kw = ["订单", "销售", "库存", "客户", "员工", "部门", "采购", "供应商", "金额", "表", "查询", "SQL", "数据库"]
    if any(k in q for k in writing_kw) and not any(k in q for k in db_kw):
        print("🚦 [Router] Rule Override -> chat (writing request)")
        return {"intent": "chat", "explain_steps": ["规则兜底: 写作类问题 -> chat"]}

    summary = hub.history_summary
    context_preview = hub.get_combined_context(max_len=500)

    # 快速路径路由以降低令牌成本。
    # 如果意图很明显，请跳过 LLM 路由器。
    doc_kw = ["document", "doc", "policy", "contract", "report", "pdf", "attachment", "附件", "文档", "合同", "制度",
              "报告", "纪要"]
    db_kw_quick = ["sql", "database", "table", "select", "where", "join", "order", "订单", "库存", "客户", "员工",
                   "部门", "销售", "数据库"]
    pronoun_kw = ["this", "that", "it", "该", "这个", "上述", "这份", "附件", "文档", "报告"]

    query_lower = (hub.query or "").lower()
    has_doc_signal = bool(hub.active_context_content) or any(k in (hub.query or "") for k in doc_kw)
    has_db_signal = any(k in query_lower for k in db_kw_quick) or any(k in (hub.query or "") for k in db_kw_quick)

    if has_doc_signal and any(k in (hub.query or "") for k in pronoun_kw):
        print("🚦 [Router] Fast-path -> rag (doc reference)")
        return {"intent": "rag", "explain_steps": ["快速路由: 文档指代 -> rag"]}

    if has_db_signal and not has_doc_signal:
        print("🚦 [Router] Fast-path -> database (db keywords)")
        return {"intent": "database", "explain_steps": ["快速路由: 数据库关键词 -> database"]}

    # 用于长多部分查询的轻量级分层拆分。
    if len(hub.query or "") > 120 and any(
            sep in (hub.query or "") for sep in ["；", "。", "?", "？", "并且", "同时", "以及"]):
        parts = [p.strip() for p in re.split(r"[；。?？]|并且|同时|以及", hub.query or "") if p.strip()]
        doc_hits = sum(1 for p in parts if any(k in p for k in doc_kw))
        db_hits = sum(1 for p in parts if any(k in p.lower() for k in db_kw_quick))
        if doc_hits and not db_hits:
            print("🚦 [Router] Fast-path -> rag (multi-part doc)")
            return {"intent": "rag", "explain_steps": ["快速路由: 多段文档问题 -> rag"]}
        if db_hits and not doc_hits:
            print("🚦 [Router] Fast-path -> database (multi-part db)")
            return {"intent": "database", "explain_steps": ["快速路由: 多段数据库问题 -> database"]}

    def _parse_router_intent(text: str) -> str:
        if not text:
            return "chat"
        t = text.lower()
        if "final" in t:
            for key in ["database", "rag", "planner", "chat"]:
                if key in t:
                    return key
        if "action" in t:
            if "database" in t:
                return "database"
            if "rag" in t:
                return "rag"
            if "planner" in t:
                return "planner"
            if "chat" in t:
                return "chat"
        if "database" in t:
            return "database"
        if "rag" in t or "doc" in t:
            return "rag"
        if "planner" in t:
            return "planner"
        return "chat"

    router_prompt = f"""
你是企业 Agent 路由器，请按 ReAct 风格判断最终路由意图。
输出格式：
Thought: ...
Action: <database|rag|planner|chat>
Observation: ...
Reflexion: ...
Final: <database|rag|planner|chat>

Few-shot 示例
Task: 用户问“本月销售额同比增长多少”
Thought: 需要查询结构化业务数据
Action: database
Observation: 这是 SQL / 指标统计问题
Reflexion: 应该走数据库查询链路
Final: database

Task: 用户问“这份制度文档第3章的审批条件是什么”
Thought: 需要从已上传文档中检索
Action: rag
Observation: 问题依赖文档内容
Reflexion: 应优先走 RAG
Final: rag

当前任务：{hub.query}
最近对话：{recent_history}
会话摘要：{summary}
检索上下文：{context_preview}
"""

    try:
        # ✅ 使用用户选择的模型进行意图识别 (local / cloud)
        print(f"🚦 [Router] Using backend: {model_backend}")
        response = ask_llm(router_prompt, model_type=model_backend)
        intent = _parse_router_intent(response.strip())
    except Exception as e:
        print(f"🚦 [Router Error] {e} -> Defaulting to chat")
        intent = "chat"

    # 反射护栏：修复 LLM 后常见的错误路线。
    if intent == "chat" and has_doc_signal and any(k in (hub.query or "") for k in pronoun_kw):
        intent = "rag"
    if intent == "database" and has_doc_signal and not has_db_signal:
        intent = "rag"

    print(f"🚦 [Router] Intent: {intent}")
    return {"intent": intent, "explain_steps": [f"识别意图: {intent}"]}


# ============================================================
# 第 2 层：上下文处理器
# ============================================================

def context_processor_node(state: AgentState):
    hub = state["hub"]
    messages = state["messages"]
    intent = state["intent"]
    model_backend = state.get("model_backend", "local")  # ✅ 获取 model_backend

    steps = []
    found_sources: List[Dict[str, Any]] = []
    found_source_keys = set()

    # 修复点 2: 更新摘要 (Short-term Memory)
    # ✅ 传入 model_backend，确保记忆总结也使用 DeepSeek
    hub.history_summary = memory_summary.update_from_messages(
        user_id=hub.user_id,
        session_id=hub.session_id,
        current_summary=hub.history_summary,
        messages=messages,
        model_type=model_backend
    )

    # 可选：把更可能长期有用的信息写进长期记忆（轻量触发，不会每回合都写）
    memory_vector.maybe_store_from_messages(hub.user_id, messages)

    # RAG 模式下的 Long-term Memory 检索
    if intent == "rag" and not hub.active_context_content:
        docs = memory_vector.retrieve(hub.user_id, hub.query, top_k=5)
        if docs:
            doc_texts = []
            for d in docs:
                doc_texts.append(d.page_content)
                # ✅ 提取来源信息 (Source Metadata)
                meta = d.metadata or {}
                src_obj = _build_source_meta(meta, d.page_content)
                src_key = f"{src_obj.get('file_name')}|{src_obj.get('page')}|{src_obj.get('snippet')}"
                if src_key and src_key not in found_source_keys:
                    found_sources.append(src_obj)
                    found_source_keys.add(src_key)

            hub.retrieved_knowledge = doc_texts
            steps.append(f"长期记忆检索: 找到 {len(docs)} 条相关知识")

    # Database 模式下，尝试从历史中提取参数
    if intent == "database":
        pass

    return {"hub": hub, "explain_steps": steps, "sources": found_sources}


# ============================================================
# 第三层：代理
# ============================================================

def _db_keyword_map() -> Dict[str, List[str]]:
    """基于 database_manager.ALLOWED_TABLES 构建“表 -> 关键词”映射，用于 DB Agent 判断是否该走数据库。"""
    # 仅使用白名单表，避免判断规则与数据库实际不一致
    m: Dict[str, List[str]] = {}

    # 中文业务词 -> 表 的对应（只加业务常用词，不引入不存在的表）
    # 你可以按需继续扩充关键词，但请保持表名必须在 ALLOWED_TABLES 中。
    if "orders" in ALLOWED_TABLES:
        m["orders"] = ["订单", "销售订单", "下单", "订单号", "order_no", "order_date", "payment_status",
                       "delivery_status"]
    if "order_items" in ALLOWED_TABLES:
        m["order_items"] = ["订单明细", "明细", "商品明细", "item", "quantity", "unit_price", "total_price"]
    if "customers" in ALLOWED_TABLES:
        m["customers"] = ["客户", "客户群体", "客户类型", "VIP", "cust_name", "cust_type", "cust_level"]
    if "employees" in ALLOWED_TABLES:
        m["employees"] = ["员工", "业务员", "销售员", "emp_name", "emp_no", "入职", "薪资", "部门员工"]
    if "departments" in ALLOWED_TABLES:
        m["departments"] = ["部门", "dept", "dept_name", "组织架构", "经理"]
    if "roles" in ALLOWED_TABLES:
        m["roles"] = ["角色", "权限", "role_name", "permissions"]
    if "products" in ALLOWED_TABLES:
        m["products"] = ["产品", "商品", "SKU", "品类", "prod_name", "category", "selling_price", "purchase_price"]
    if "inventory" in ALLOWED_TABLES:
        m["inventory"] = ["库存", "仓库", "盘点", "quantity", "warehouse"]
    if "suppliers" in ALLOWED_TABLES:
        m["suppliers"] = ["供应商", "供货", "supp_name", "rating"]
    if "purchases" in ALLOWED_TABLES:
        m["purchases"] = ["采购", "进货", "purchase_no", "purchase_date", "采购单"]
    if "company_info" in ALLOWED_TABLES:
        m["company_info"] = ["公司", "企业信息", "经营范围", "business_scope", "registration_code", "成立日期"]

    return m


def _is_db_question_by_tables(query: str) -> (bool, List[str]):
    """仅依据白名单表的关键词判断。返回：是否命中、命中证据（命中的表/关键词）。"""
    q = (query or "").strip().lower()
    if not q:
        return False, []

    hit_evidence: List[str] = []
    kw_map = _db_keyword_map()

    # 1) 命中表名（用户直接说了 orders / customers 这种）
    for t in ALLOWED_TABLES:
        if t.lower() in q:
            hit_evidence.append(f"命中表名:{t}")
            return True, hit_evidence

    # 2) 命中业务关键词
    for table, kws in kw_map.items():
        for kw in kws:
            if kw.lower() in q:
                hit_evidence.append(f"{table}:{kw}")
                # 不必收集太多证据，够用即可
                if len(hit_evidence) >= 3:
                    return True, hit_evidence
    return (len(hit_evidence) > 0), hit_evidence


def db_agent_node(state: AgentState):
    """
    🗄️ [Layer 3] DB Agent（改造版）
    - 只负责“判断是否走数据库”
    - 一旦判定走数据库：不在本文件生成 SQL、不执行 SQL、不重试
      直接把执行权交给 database_manager.db_manager.query_fast
    """
    print("🗄️ [Layer 3] DB Agent (Judge-only, delegate to database_manager)...")
    hub = state["hub"]
    # ✅ 传递模型后端
    model_backend = state.get("model_backend", "local")
    ok, evidence = _is_db_question_by_tables(hub.query)

    # 如果判定不是数据库问题：降级为 chat（不走数据库）
    if not ok:
        print("🗄️ [DB Agent] Not a DB question by table-based check -> downgrade to chat")
        return {
            "intent": "chat",
            "agent_output": {"type": "chat", "data": ""},
            "explain_steps": ["DB 判断: 未命中白名单表关键词，降级为通用回答"]
        }

    # ✅ 判定为数据库问题：执行完全交给 database_manager
    explain = ["DB 判断: 命中白名单表关键词 -> " + ", ".join(evidence)] if evidence else ["DB 判断: 命中白名单表关键词"]
    explain.append(f"DB 执行 (using {model_backend})")

    chunks: List[str] = []
    try:
        # ✅ 使用选定的模型进行 SQL 生成
        for ch in db_manager.query_fast(DEFAULT_DB_NAME, hub.query, model_type=model_backend):
            if ch:
                chunks.append(ch)
    except Exception as e:
        err = f"❌ database_manager 执行失败: {e}"
        print(err)
        return {
            "intent": "database",
            "agent_output": {"type": "database", "answer": err},
            "explain_steps": explain + [err],
        }

    answer = "".join(chunks).strip() if chunks else "（数据库未返回结果）"
    hub.update_working_memory("db_answer", answer)

    return {
        "intent": "database",
        "agent_output": {"type": "database", "answer": answer},
        "explain_steps": explain,
        "hub": hub,
    }


def rag_agent_node(state: AgentState):
    print("🔍 [Layer 3] RAG Agent...")
    hub = state["hub"]
    knowledge = []
    if hub.active_context_content:
        knowledge.append(f"【当前文档】\n{hub.active_context_content}")
    if hub.retrieved_knowledge:
        knowledge.append(f"【知识库】\n" + "\n".join(hub.retrieved_knowledge))
    return {
        "agent_output": {"type": "rag", "data": "\n\n".join(knowledge)},
        "explain_steps": ["整合知识..."]
    }


def planner_agent_node(state: AgentState):
    print("📅 [Layer 3] Planner Agent...")
    hub = state["hub"]
    plan_prompt = f"任务：{hub.query}。拆解为2-4步 JSON。"
    return {
        "agent_output": {"type": "planner", "plan": ["分析需求", "执行任务"], "status": "planned"},
        "explain_steps": ["生成计划"]
    }


def chat_placeholder_node(state: AgentState):
    return {"agent_output": {"type": "chat", "data": ""}}


# ============================================================
# 第 4 层：合成器
# ============================================================

def synthesizer_node(state: AgentState):
    print("📢 [Layer 4] Synthesizer Generating...")
    hub = state["hub"]
    agent_out = state["agent_output"]
    intent = state["intent"]
    messages = state["messages"]

    recent_history_str = memory_buffer.format_history(messages, limit=6)

    system_part = "你是企业智能助手。请结合上下文和工具结果回答，避免任何自我介绍或身份设定。"

    context_part = ""
    tool_result_part = ""

    if intent == "database":
        # database_manager 已经完成 SQL 生成/校验/执行/总结，这里只做“展示/轻量润色”。
        db_answer = agent_out.get("answer") or hub.working_memory.get("db_answer") or ""
        tool_result_part = f"【数据库查询结果】\n{db_answer}"

    elif intent == "rag":
        docs = agent_out.get("data", "")
        tool_result_part = f"【检索到的参考资料】\n{docs}"

    elif intent == "planner":
        plan = agent_out.get("plan", [])
        tool_result_part = f"【建议计划】\n" + "\n".join(plan)

    else:
        context = hub.get_combined_context()
        if context:
            context_part = f"【背景上下文】\n{context}"

    final_prompt = f"""
{system_part}

【对话历史】
{recent_history_str}

{context_part}
{tool_result_part}

User: {hub.query}
Assistant:
"""
    return {"final_response": final_prompt}


# ============================================================
# Graph 编译
# ============================================================

workflow = StateGraph(AgentState)
workflow.add_node("router", router_node)
workflow.add_node("context_processor", context_processor_node)
workflow.add_node("db_agent", db_agent_node)
workflow.add_node("rag_agent", rag_agent_node)
workflow.add_node("planner_agent", planner_agent_node)
workflow.add_node("chat_placeholder", chat_placeholder_node)
workflow.add_node("synthesizer", synthesizer_node)

workflow.set_entry_point("router")
workflow.add_edge("router", "context_processor")


def route_decision(state: AgentState):
    i = state["intent"]
    if i == "database": return "db_agent"
    if i == "rag": return "rag_agent"
    if i == "planner": return "planner_agent"
    return "chat_placeholder"


workflow.add_conditional_edges("context_processor", route_decision, {
    "db_agent": "db_agent", "rag_agent": "rag_agent", "planner_agent": "planner_agent",
    "chat_placeholder": "chat_placeholder"
})

workflow.add_edge("db_agent", "synthesizer")
workflow.add_edge("rag_agent", "synthesizer")
workflow.add_edge("planner_agent", "synthesizer")
workflow.add_edge("chat_placeholder", "synthesizer")
workflow.add_edge("synthesizer", END)

app_graph = workflow.compile()
