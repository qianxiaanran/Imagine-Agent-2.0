from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ContextHub(BaseModel):
    """
    【Layer 2】上下文调度中心 (Context Hub) - 增强版
    """
    user_id: str
    session_id: str
    query: str

    # === 前端模式选择（用于“强制模式”锁定）===
    # ui_mode: 前端当前选择的模式（general / database / rag ...）
    # forced_intent: 当用户手动选择数据库/文档模式时，在 Router 层强制锁定到对应 intent
    ui_mode: str = "general"
    forced_intent: Optional[str] = None

    # === 状态与记忆 ===
    user_permission: str = "user"
    history_summary: str = ""

    # === ✨ 长期记忆 / 压缩事实（给 Agent 用，不等同于知识库文档）===
    # memory_tokens: 结构化、稳定的长期事实（如“用户偏好/硬约束/关键信息”）
    memory_tokens: List[str] = Field(default_factory=list)
    # compressed_facts: 对话“废话剥离”后的极简事实，适合当作提示词中的约束/背景
    compressed_facts: List[str] = Field(default_factory=list)
    # long_term_memory: 从长期记忆（向量库/档案）召回的少量片段（只放 1-4 条，避免淹没回答）
    long_term_memory: List[str] = Field(default_factory=list)

    # Working Memory (工作记忆)
    # 存储当前回合的临时变量，如 SQL、检索到的片段等
    working_memory: Dict[str, Any] = Field(default_factory=dict)

    # === 核心上下文数据 ===
    # Active Context: 用户当前打开的文档/OCR结果/选中的文本
    active_context_content: Optional[str] = None

    # Retrieved Knowledge: 从向量库检索到的碎片
    retrieved_knowledge: List[str] = Field(default_factory=list)

    # === ✨ 新增：上下文策略状态 ===
    # 用于指导 RAG Agent 如何工作
    context_strategy: str = "auto"  # focus_active (只看文档) / search_global (只搜知识库) / hybrid (混合对比) / none
    search_keywords: List[str] = Field(default_factory=list)  # 提取出的精准搜索词

    # 记录上下文来源（可选：前端“参考来源”面板可用）
    sources: List[str] = Field(default_factory=list)

    def update_working_memory(self, key: str, value: Any):
        self.working_memory[key] = value

    def add_source(self, src: str):
        if not src:
            return
        if src not in self.sources:
            self.sources.append(src)

    def add_retrieved_knowledge(self, chunks: List[str], source: str = "知识库"):
        if not chunks:
            return
        for c in chunks:
            if c and c.strip():
                self.retrieved_knowledge.append(c.strip())
        self.add_source(source)

    def add_memory_tokens(self, tokens: List[str], source: str = "长期记忆"):
        if not tokens:
            return
        for t in tokens:
            if t and t.strip() and t.strip() not in self.memory_tokens:
                self.memory_tokens.append(t.strip())
        self.add_source(source)

    def add_compressed_facts(self, facts: List[str], source: str = "压缩事实"):
        if not facts:
            return
        for f in facts:
            if f and f.strip() and f.strip() not in self.compressed_facts:
                self.compressed_facts.append(f.strip())
        self.add_source(source)

    def add_long_term_memory(self, snippets: List[str], source: str = "长期记忆召回"):
        if not snippets:
            return
        for s in snippets:
            if s and s.strip() and s.strip() not in self.long_term_memory:
                self.long_term_memory.append(s.strip())
        self.add_source(source)

    def _resolve_auto_strategy(self) -> str:
        """当 context_strategy=auto 时，基于当前状态自动选择策略。"""
        has_active = bool(self.active_context_content and self.active_context_content.strip())
        has_kb = bool(self.retrieved_knowledge)
        if has_active and has_kb:
            return "hybrid"
        if has_active:
            return "focus_active"
        if has_kb:
            return "search_global"
        return "none"

    def get_combined_context(self, max_len=3000) -> str:
        """
        根据策略智能组装上下文
        """
        parts = []

        # ✅ 记忆区块优先（短且稳定）
        if self.memory_tokens:
            parts.append("【长期记忆要点】\n" + "\n".join(self.memory_tokens[:12]))
        if self.long_term_memory:
            parts.append("【长期记忆召回】\n" + "\n---\n".join(self.long_term_memory[:4]))
        if self.compressed_facts:
            parts.append("【压缩事实】\n" + "\n".join(self.compressed_facts[:12]))

        # 自动策略：根据当前数据自动选择
        strategy = self.context_strategy
        if strategy == "auto":
            strategy = self._resolve_auto_strategy()

        # 策略 1: 专注当前文档 (或混合模式)
        if strategy in ["focus_active", "hybrid"] and self.active_context_content:
            content = self.active_context_content[:2000]  # 给当前文档更多配额
            parts.append(f"【当前屏幕文档内容】\n{content}\n(用户正在阅读此文档)")

        # 策略 2: 全局检索 (或混合模式)
        if strategy in ["search_global", "hybrid"] and self.retrieved_knowledge:
            knowledge_str = "\n".join(self.retrieved_knowledge)[:1500]
            parts.append(f"【知识库参考资料】\n{knowledge_str}")

        # 历史摘要总是作为背景
        if self.history_summary:
            parts.append(f"【历史对话摘要】\n{self.history_summary}")

        # Working Memory 只放关键字段，避免噪声
        if self.working_memory:
            keys = [k for k in ["sql_executed", "db_result"] if k in self.working_memory]
            if keys:
                wm_lines = []
                for k in keys:
                    v = self.working_memory.get(k)
                    if v is None:
                        continue
                    s = str(v)
                    wm_lines.append(f"- {k}: {s[:800]}")
                if wm_lines:
                    parts.append("【本轮工作记忆】\n" + "\n".join(wm_lines))

        full_context = "\n\n".join(parts)
        return full_context[:max_len]
