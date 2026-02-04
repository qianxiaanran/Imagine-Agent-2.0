import json
import re
from typing import Dict, List, Generator, Any
from datetime import datetime

# 复用现有模块
from deepseek_llm import ask_llm, ask_llm_stream
from documents_processing import search_user_documents
from database_manager import db_manager
from supabase_client import require_supabase


# ==========================================
# 1. 实体定义 (Schemas)
# ==========================================
class AuditFinding:
    def __init__(self, type: str, severity: str, message: str, field: str = None, evidence: str = None):
        self.type = type  # RULE, ANOMALY, POLICY, MISSING_INFO
        self.severity = severity  # HIGH, MEDIUM, LOW
        self.message = message
        self.field = field
        self.evidence = evidence

    def to_dict(self):
        return self.__dict__


# ==========================================
# 2. 各阶段处理器 (Processors)
# ==========================================

def _step_normalize_input(raw_input: str, model_type: str = "local") -> Dict[str, Any]:
    """
    步骤 A: 输入标准化
    尝试解析 JSON，如果失败则用 LLM 提取结构化数据
    """
    # 1. 尝试直接解析 JSON
    try:
        if raw_input.strip().startswith("{"):
            return json.loads(raw_input)
    except:
        pass

    # 2. 如果是自然语言文本，用 LLM 提取
    prompt = f"""
    请从以下文本中提取订单信息，并以严格的 JSON 格式输出。
    如果缺少字段，请保留为 null。
    不要输出 Markdown 标记，只输出纯 JSON 字符串。

    目标字段结构：
    {{
      "order_id": "订单号",
      "customer_name": "客户名称",
      "items": [{{"sku": "商品编码", "qty": 数量, "unit_price": 单价}}],
      "currency": "币种(CNY/USD)",
      "total_amount": 总金额(数字),
      "pay_terms": "付款条款",
      "order_date": "YYYY-MM-DD"
    }}

    待提取文本：
    {raw_input}
    """
    # ✅ 使用传入的 model_type
    json_str = ask_llm(prompt, model_type=model_type)

    # 清理可能存在的 markdown 代码块标记
    json_str = re.sub(r"```json|```", "", json_str).strip()
    try:
        return json.loads(json_str)
    except Exception as e:
        print(f"❌ JSON 提取失败: {e}")
        return {"error": "无法解析订单信息，请提供更清晰的文本或标准 JSON。"}


def _step_rule_check(order: Dict[str, Any]) -> List[AuditFinding]:
    """
    步骤 B: 基础规则校验 (硬编码规则 + 完整性检查)
    """
    findings = []

    # 1. 必填字段检查
    required_fields = ["customer_name", "items", "total_amount"]
    for field in required_fields:
        if not order.get(field):
            findings.append(AuditFinding("MISSING_INFO", "HIGH", f"缺少必填字段: {field}", field))

    # 2. 业务规则示例：总金额不能为负
    if order.get("total_amount", 0) < 0:
        findings.append(
            AuditFinding("RULE", "HIGH", "订单总金额不能为负数", "total_amount", str(order.get("total_amount"))))

    # 3. 业务规则示例：SKU 数量检查
    if order.get("items"):
        for item in order["items"]:
            if item.get("qty", 0) <= 0:
                findings.append(AuditFinding("RULE", "MEDIUM", f"商品 {item.get('sku')} 数量必须大于 0", "items"))

    return findings


def _step_anomaly_detection(order: Dict[str, Any]) -> List[AuditFinding]:
    """
    步骤 C: 异常检测 (基于数据库历史数据)
    """
    findings = []
    cust_name = order.get("customer_name")

    if not cust_name:
        return findings

    # 模拟：简单查询历史平均订单金额 (需要 database_manager 支持)
    # 这里为了演示，我们假设如果金额 > 100万 则为异常
    # 实际生产中应调用 db_manager 执行 SQL: SELECT AVG(total_amount) FROM orders WHERE customer_name = ...

    current_amount = float(order.get("total_amount", 0))

    # 简单的阈值规则 (实际可替换为 IsolationForest 模型预测)
    if current_amount > 500000:
        findings.append(AuditFinding(
            "ANOMALY", "MEDIUM",
            f"订单金额 ({current_amount}) 显著高于该客户历史平均水平",
            "total_amount"
        ))

    return findings


def _step_policy_rag(user_id: str, order: Dict[str, Any], model_type: str = "local") -> List[AuditFinding]:
    """
    步骤 D: 政策/合同一致性比对 (RAG)
    """
    findings = []

    # 构建检索 Query
    query_text = f"客户 {order.get('customer_name')} 的付款条款 合同规定 账期"

    # 1. 检索相关文档
    docs = search_user_documents(user_id, query_text, k=2)
    if not docs:
        return findings  # 没找到相关合同，跳过

    context_text = "\n".join([d.page_content for d in docs])

    # 2. 让 LLM 判定
    current_terms = order.get("pay_terms", "未指定")

    prompt = f"""
    请对比以下“订单实际条款”与“检索到的合同条款”，判断是否存在违规风险。

    【订单实际情况】
    客户: {order.get('customer_name')}
    付款条款: {current_terms}
    总金额: {order.get('total_amount')}

    【参考合同/政策片段】
    {context_text}

    请输出 JSON 格式判定结果：
    {{
       "is_violation": true/false,
       "severity": "HIGH/MEDIUM/LOW",
       "reason": "简短说明不一致的地方"
    }}
    """

    try:
        # ✅ 使用传入的 model_type
        res = ask_llm(prompt, model_type=model_type)
        res_clean = re.sub(r"```json|```", "", res).strip()
        result = json.loads(res_clean)

        if result.get("is_violation"):
            findings.append(AuditFinding(
                "POLICY",
                result.get("severity", "MEDIUM"),
                result.get("reason"),
                "pay_terms",
                evidence=context_text[:100] + "..."
            ))
    except Exception as e:
        print(f"Policy Check Error: {e}")

    return findings


# ==========================================
# 3. 主流程控制器 (Main Pipeline)
# ==========================================

async def run_audit_pipeline(user_id: str, session_id: str, raw_message: str, model_type: str = "local") -> Generator[
    str, None, None]:
    """
    执行完整的审单流水线，并流式输出 Markdown 报告
    """
    yield "> 🚀 正在启动智能审单引擎 (Backend: {})\n\n".format(model_type)

    # --- Step A: Normalization ---
    yield "> 1️⃣ 正在解析订单结构...\n\n"
    # ✅ 传递 model_type
    order = _step_normalize_input(raw_message, model_type=model_type)

    if "error" in order:
        yield f"❌ **解析失败**: {order['error']}\n"
        return

    # 展示提取到的关键信息
    yield f"```json\n{json.dumps(order, ensure_ascii=False, indent=2)}\n```\n\n"

    # --- Step B: Rule Check ---
    yield "> 2️⃣ 正在执行规则引擎校验...\n\n"
    findings = _step_rule_check(order)

    # --- Step C: Anomaly Detection ---
    yield "> 3️⃣ 正在进行历史数据异常检测...\n\n"
    findings += _step_anomaly_detection(order)

    # --- Step D: Policy RAG ---
    yield "> 4️⃣ 正在检索合同条款并进行比对...\n\n"
    # ✅ 传递 model_type
    findings += _step_policy_rag(user_id, order, model_type=model_type)

    # --- Step E: Report Generation ---
    yield "> 📊 **生成最终审单报告**...\n\n"

    # 计算总体风险分和结论
    risk_score = 0
    high_risks = len([f for f in findings if f.severity == 'HIGH'])
    med_risks = len([f for f in findings if f.severity == 'MEDIUM'])

    risk_score = min(100, (high_risks * 40) + (med_risks * 15))

    status = "APPROVED"
    if high_risks > 0:
        status = "REJECTED"
    elif med_risks > 0:
        status = "REVIEW_REQUIRED"

    # 构建 Prompt 生成最终自然语言报告
    report_prompt = f"""
    你是一名专业的风控审计专家。请根据以下订单信息和发现的问题清单，生成一份 Markdown 格式的【智能审单报告】。

    【订单摘要】
    {json.dumps(order, ensure_ascii=False)}

    【发现的问题清单 (Findings)】
    {json.dumps([f.to_dict() for f in findings], ensure_ascii=False)}

    【结论要求】
    - 状态判定: {status}
    - 风险评分: {risk_score}/100

    请按以下 Markdown 结构输出：
    ## 📑 智能审单报告
    ### 1. 概览
    (包含结论、评分、客户名、金额)
    ### 2. 风险详情
    (列出所有 Findings，高风险项加粗)
    ### 3. 处理建议
    (针对问题给出具体的修改或放行建议)
    """

    full_report_content = ""

    # 流式生成报告
    # ✅ 传递 model_type
    for chunk in ask_llm_stream(report_prompt, model_type=model_type):
        if chunk:
            full_report_content += chunk
            yield chunk

    # --- Step F: Save to DB ---
    try:
        sb = require_supabase()

        # 1. 插入 audit_runs
        run_data = {
            "user_id": user_id,
            "session_id": session_id,
            "order_id": order.get("order_id"),
            "customer_name": order.get("customer_name"),
            "total_amount": float(order.get("total_amount", 0)) if order.get("total_amount") else 0,
            "currency": order.get("currency", "CNY"),
            "risk_score": risk_score,
            "status": status,
            "report_markdown": full_report_content
        }
        res = sb.table("audit_runs").insert(run_data).execute()
        run_id = res.data[0]['id'] if res.data else None

        # 2. 插入 audit_findings
        if run_id and findings:
            findings_data = []
            for f in findings:
                fdata = f.to_dict()
                fdata['run_id'] = run_id
                findings_data.append(fdata)

            sb.table("audit_findings").insert(findings_data).execute()

        yield f"\n\n> ✅ **审计记录已归档** (ID: {run_id})"

    except Exception as e:
        print(f"Save Audit Error: {e}")
        yield f"\n\n> ⚠️ **警告**: 报告生成成功，但保存到数据库失败 ({str(e)})"