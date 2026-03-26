"""
报告 / PPT 大纲生成 + 邮件起草 (增强版 - 结构化 JSON 输出 + 智能上下文)
"""
import json
from typing import Generator, List, Dict, Optional
from deepseek_llm import ask_llm, ask_llm_stream

# ------------------------------------------------
# 📝 智能 Chat 模式的 Prompt (JSON 版 - 内容增强 + 上下文支持)
# ------------------------------------------------

SMART_EMAIL_PROMPT = """
### 角色设定
你是一名专业的职场沟通专家，擅长撰写得体、详尽且高效的商务邮件。

### 上下文背景
{context}

### 用户指令
{user_input}

### 输出语言要求
{language_requirement}

### 任务要求
请根据指令和上下文生成（或修改）一封**内容完整、细节丰富**的专业邮件，信息要具体、可执行、可直接发送。默认按企业业务往来中的“回复邮件”来处理，优先覆盖确认、解释、承诺、附件说明、下一步动作与时间节点。
**必须**且**只能**输出包含以下字段的 JSON 数据（包裹在 ```json 代码块中）：

JSON 结构示例：
```json
{{
  "type": "email",
  "subject": "邮件主题（要具体且有吸引力）",
  "recipient": "收件人称呼",
  "body": "邮件正文内容。请注意：\n1. 至少 4-6 段，每段 1-3 句，段落之间用 \\n\\n 分隔。\n2. 必须包含：称呼、背景、目的/请求、关键信息（时间/地点/金额/对象）、行动项与时间节点、结束语/署名建议。\n3. 使用 Markdown 换行符(\\n)进行分段，可用项目符号列出行动项。",
  "actions": ["具体的行动建议1", "具体的行动建议2（如需要对方确认时间、提供文档等）"],
  "tone": "专业/委婉/热情"
}}
```

**注意：**
1. **不要输出任何开场白**，直接输出 JSON 代码块。
2. **上下文一致性**：如果这是对之前邮件的修改，请务必保留之前正确的背景信息，只针对用户要求的部分进行调整。
3. `body` 部分请展开写，确保语气通顺，逻辑严密，信息量充足，**避免空洞的套话**。
4. 若关键信息缺失，请使用清晰占位符（如【时间】、【金额】、【附件名称】），不要省略。
5. `actions` 列表给出 2-5 条具体、可执行、可核对的行动项。
"""

SMART_REPORT_PROMPT = """
### 角色设定
你是一名资深的企业咨询顾问，擅长产出深度分析报告。

### 上下文背景
{context}

### 用户指令
{user_input}

### 任务要求
请根据指令和上下文生成（或修改）一份**内容详实、有深度、可直接写作**的结构化报告大纲。
**必须**且**只能**输出包含以下字段的 JSON 数据（包裹在 ```json 代码块中）：

JSON 结构示例：
```json
{{
  "type": "report",
  "title": "报告总标题",
  "subtitle": "副标题或背景说明",
  "sections": [
    {{
      "heading": "章节标题",
      "content": "本章节的核心详细内容。请注意：\n- 目标/结论：……\n- 分析维度：……\n- 数据/指标/口径：……\n- 原因/影响：……\n- 建议/行动：……\n- 风险与对策：……\n支持 Markdown 格式。",
      "icon": "file-text" // 可选图标建议: file-text, trending-up, alert-triangle, check-circle
    }},
    {{
      "heading": "详细的数据/风险分析",
      "content": "1. 市场风险分析：详细描述...\n2. 运营风险：详细描述...",
      "icon": "alert-triangle"
    }}
  ]
}}
```

**注意：**
1. **不要输出任何开场白**，直接输出 JSON 代码块。
2. **主题一致性**：如果这并非第一次生成，请仔细阅读【上下文背景】中的旧报告内容，确保新生成的章节与原主题紧密相关，逻辑连贯。
3. **章节数量**：建议 8-12 章（若用户指定或篇幅允许可更多），并覆盖用户指定的“必含模块”。
4. **关键要求**：`content` 字段中的内容要尽可能丰富，**不要只列标题**。每章至少 5-8 条要点，包含目标/关键结论/分析维度/数据指标/原因影响/建议行动/风险对策。
5. 若数据缺失，请合理给出假设或占位符（如【样本量】、【同比/环比】），不要留空。
"""

SMART_PPT_PROMPT = """
### 角色设定
你是一名 PPT 制作专家，擅长策划逻辑清晰且内容饱满的演示文稿。

### 上下文背景
{context}

### 用户指令
{user_input}

### 任务要求
请根据指令和上下文生成（或修改）一份 PPT 演示文稿结构。
**必须**且**只能**输出包含以下字段的 JSON 数据（包裹在 ```json 代码块中）：

JSON 结构示例：
```json
{{
  "type": "ppt",
  "title": "演示文稿主题",
  "total_pages": 10,
  "slides": [
    {{
      "page": 1,
      "title": "封面页标题",
      "points": ["演讲人：XXX", "日期：2024-XX", "副标题：XXX"],
      "visual": "背景图建议（描述具体画面风格）"
    }},
    {{
      "page": 2,
      "title": "目录/议程",
      "points": [
        "1. 市场现状深度剖析：包含用户痛点与机会", 
        "2. 竞品详细分析：优劣势对比", 
        "3. 核心策略建议：短期与长期规划"
      ],
      "visual": "列表式布局，左侧配相关商务插图"
    }},
    {{
      "page": 3,
      "title": "具体内容页标题",
      "points": [
        "核心观点：详细阐述观点...",
        "数据支持：列举关键数据指标...",
        "结论：得出的具体结论..."
      ],
      "visual": "图表（柱状图/折线图）展示数据趋势"
    }}
  ]
}}
```

**注意：**
1. **不要输出任何开场白**，直接输出 JSON 代码块。
2. **上下文严格一致性（关键）**：
   - 仔细阅读【上下文背景】中已有的 PPT 内容。
   - **新增页**：必须紧扣原有主题，是对原有内容的补充或延伸，**绝对不要**开启一个无关的新话题。
   - **页数控制**：如果用户要求“加 N 页”，请在原有页数基础上准确增加 N 页，不要随意多加或少加。
   - **全量输出**：如果是修改，请输出包含【旧幻灯片 + 新增幻灯片】的完整 JSON 数据，不要只输出新增的部分。
3. **内容质量**：每一页的 `points` 内容要**具体且丰富**，写出完整的句子或论点（建议 3-6 条/页），并给出 1 句核心结论或主张。
4. **结构覆盖**：若页数允许，建议包含封面、目录、背景/问题、分析/洞察、方案/策略、实施路径/里程碑、资源/预算、风险与对策、总结/行动项、Q&A。
5. **可视化要求**：`visual` 必须具体到图表类型/布局/元素（如“左图右文、折线+关键注释、对标柱状图”）。
"""

# ------------------------------------------------
# 🛠 辅助函数：上下文与意图处理
# ------------------------------------------------

def format_history(history: List[Dict[str, str]]) -> str:
    """
    将历史消息格式化为 Prompt 可读的文本。
    关键修复：不再隐藏 JSON 历史内容，确保模型能看到之前的文档状态，防止“主题跑偏”。
    """
    if not history:
        return "（无历史上下文，这是第一轮对话）"

    formatted = []
    # 只保留最近 3 轮（为了防止 Token 溢出，同时保证最近一次的生成结果是完整的）
    # 如果生成的文档非常长，可以考虑只截取 JSON 的部分，但目前为了效果优先，保留全量。
    for msg in history[-3:]:
        role = "用户" if msg['role'] == 'user' else "AI助手"
        content = msg.get('content', '')
        formatted.append(f"{role}: {content}")

    return "\n---\n".join(formatted)

def detect_previous_intent(history: List[Dict[str, str]]) -> str:
    """
    从历史记录中推断上一次的任务类型。
    增强版逻辑：同时检查 AI 的输出结构和 User 的历史关键词。
    """
    if not history:
        return ""

    # 1. 优先检查 AI 回复中的 JSON 标记
    for msg in reversed(history):
        if msg['role'] == 'assistant':
            content = msg.get('content', '').replace(" ", "").replace("\n", "")
            if '"type":"email"' in content: return "email"
            if '"type":"ppt"' in content: return "ppt"
            if '"type":"report"' in content: return "report"

    # 2. 倒查用户历史中的“强意图”
    for msg in reversed(history):
        if msg['role'] == 'user':
            content = msg.get('content', '')
            if any(kw in content for kw in ["PPT", "ppt", "演示", "幻灯片", "Slide"]): return "ppt"
            if any(kw in content for kw in ["邮件", "Email", "email", "发信"]): return "email"
            if any(kw in content for kw in ["报告", "文档", "文章"]): return "report"

    return ""

# ------------------------------------------------
# 🚀 核心逻辑：流式生成入口
# ------------------------------------------------

def stream_report_or_email(user_input: str, history: Optional[List[Dict[str, str]]] = None) -> Generator[str, None, None]:
    """
    智能判断用户意图，并流式生成邮件或报告 (JSON 格式)
    支持上下文历史，可处理“修改”、“变长一点”等模糊指令
    """
    if history is None:
        history = []

    # 准备上下文文本
    context_str = format_history(history)

    # --------------------------------------------------
    # ✨ 1. 精确指令匹配 (优先级最高 - 用于强制覆盖)
    # --------------------------------------------------
    if "[指令:生成PPT]" in user_input:
        prompt = SMART_PPT_PROMPT.format(user_input=user_input, context=context_str)
        yield "📊 正在深度规划 PPT 结构与内容...\n"
        yield from ask_llm_stream(prompt)
        return

    if "[指令:生成报告]" in user_input:
        prompt = SMART_REPORT_PROMPT.format(user_input=user_input, context=context_str)
        yield "📋 正在构思详细的报告框架与内容...\n"
        yield from ask_llm_stream(prompt)
        return

    if "[指令:起草邮件]" in user_input:
        prompt = SMART_EMAIL_PROMPT.format(
            user_input=user_input,
            context=context_str,
            language_requirement="请严格遵循用户在指令中指定的输出语言；若未指定，默认使用简体中文。",
        )
        yield "📧 正在撰写详细邮件内容...\n"
        yield from ask_llm_stream(prompt)
        return

    # --------------------------------------------------
    # ✨ 2. 智能意图识别 (结合历史上下文)
    # --------------------------------------------------

    # 2.1 显式关键词检测 (当前输入)
    kw_email = any(kw in user_input for kw in ["邮件", "Email", "email", "信", "回复"])
    kw_ppt = any(kw in user_input for kw in ["PPT", "ppt", "演示", "幻灯片", "Slide", "页", "封面"])

    # 2.2 将“报告”类关键词分为强弱两类
    kw_report_strong = any(kw in user_input for kw in ["报告", "文章", "文档", "文案"])
    kw_report_weak = any(kw in user_input for kw in ["大纲", "方案", "结构", "内容", "详情"])

    # 2.3 获取历史意图 (增强版检测)
    last_intent = detect_previous_intent(history)

    # 2.4 决策优先级
    final_intent = "report" # 最终兜底

    if kw_ppt:
        final_intent = "ppt"
    elif kw_email:
        final_intent = "email"
    elif kw_report_strong:
        final_intent = "report"
    elif last_intent:
        final_intent = last_intent
    elif kw_report_weak:
        final_intent = "report"
    else:
        final_intent = "report"

    # --------------------------------------------------
    # ✨ 3. 生成 Prompt 并执行
    # --------------------------------------------------

    if final_intent == "email":
        prompt = SMART_EMAIL_PROMPT.format(
            user_input=user_input,
            context=context_str,
            language_requirement="请严格遵循用户在指令中指定的输出语言；若未指定，默认使用简体中文。",
        )
        prefix = "📧 正在优化/撰写邮件内容...\n"
    elif final_intent == "ppt":
        prompt = SMART_PPT_PROMPT.format(user_input=user_input, context=context_str)
        prefix = "📊 正在优化/规划 PPT 结构...\n"
    else:
        # 默认为报告模式
        prompt = SMART_REPORT_PROMPT.format(user_input=user_input, context=context_str)
        prefix = "📋 正在优化/构思报告框架...\n"

    yield prefix
    yield from ask_llm_stream(prompt)


# ------------------------------------------------
# 🔄 保留旧接口 (兼容可能存在的表单调用)
# ------------------------------------------------

def generate_report_outline(
    topic: str,
    scene: str,
    audience: str,
    length: str,
    key_points: str,
) -> str:
    user_input = f"主题：{topic}, 场景：{scene}, 受众：{audience}, 详细程度/篇幅：{length}, 关键点：{key_points}"
    prompt = SMART_REPORT_PROMPT.format(user_input=user_input, context="（表单生成模式，无历史上下文）")
    return ask_llm(prompt).strip()


def generate_email_draft(
    subject: str,
    receiver_role: str,
    scene: str,
    key_points: str,
    tone: str,
    language: str = "简体中文",
) -> str:
    user_input = f"主题：{subject}, 收件人：{receiver_role}, 场景：{scene}, 关键点：{key_points}, 语气：{tone}"
    prompt = SMART_EMAIL_PROMPT.format(
        user_input=user_input,
        context="（表单生成模式，无历史上下文）",
        language_requirement=f"请使用{language}输出整封邮件；若用户明确要求双语，请按要求分段输出。",
    )
    return ask_llm(prompt).strip()
