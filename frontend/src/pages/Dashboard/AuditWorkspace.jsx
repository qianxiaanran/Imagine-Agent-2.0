import React, { useRef, useState } from "react";
import {
  AlertTriangle,
  FileUp,
  Loader2,
  Search,
} from "lucide-react";

const OVERVIEW_TEXT = [
  "AI 合同审校与预警方案，覆盖合同上传、关键信息提取、风险识别预警与履约审核报告全流程。",
  "通过 OCR、NLP 与规则引擎协同，可替代大量重复核对工作，并将审核决策沉淀为可追踪数据。",
  "支持法律、财务、业务多角色配置审查标准，降低人工成本并提升风控质量。",
];

const FEATURE_BLOCKS = [
  {
    title: "合同上传及智能识别",
    lines: ["支持 PDF/Word/图片上传", "自动识别合同结构和文段", "支持在线预览与定位审查"],
  },
  {
    title: "关键信息精准提取",
    lines: ["主体信息、财务条款、履约要素", "支持合同金额、税率、付款条件提取", "减少人工录入错误与遗漏"],
  },
  {
    title: "多维智能评审引擎",
    lines: ["合同风险排查", "敏感词审查", "企业风险评估与履约监控"],
  },
];

const ADVANTAGES = [
  "垂直模型适配合同场景，支持持续学习优化。",
  "OCR + NLP + 规则引擎协同，兼顾精度与稳定性。",
  "规则可配置，支持企业自定义审查清单。",
];

const SOURCE_LABEL = {
  rule: "规则命中",
  ai: "AI语义",
  cross_doc: "跨单据核对",
  anomaly: "异常检测",
};

const escapeRegExp = (v = "") => v.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const HighlightedText = ({ text, highlight }) => {
  if (!text) return <span>暂无证据片段</span>;
  if (!highlight) return <span>{text}</span>;
  const safe = String(highlight);
  const parts = String(text).split(new RegExp(`(${escapeRegExp(safe)})`, "gi"));
  return (
    <span>
      {parts.map((part, idx) =>
        part.toLowerCase() === safe.toLowerCase()
          ? <mark key={idx} className="bg-amber-100 text-amber-700 px-0.5 rounded">{part}</mark>
          : <span key={idx}>{part}</span>
      )}
    </span>
  );
};

const riskBadgeClass = (level = "low") => {
  if (level === "high") return "bg-red-100 text-red-700 border-red-200 dark:bg-red-950/40 dark:text-red-300 dark:border-red-900/60";
  if (level === "medium") return "bg-amber-100 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-900/60";
  return "bg-emerald-100 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-900/60";
};

const confidenceText = (v) => {
  const n = Number(v);
  if (!Number.isFinite(n)) return "";
  return `${Math.round(Math.max(0, Math.min(1, n)) * 100)}%`;
};

const formatValue = (value) => {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toLocaleString("zh-CN", { maximumFractionDigits: 4 });
  }
  if (Array.isArray(value)) {
    return value.map((item) => formatValue(item)).filter((item) => item && item !== "-").join(" / ") || "-";
  }
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
};

const BASE_FIELD_SECTIONS = [
  {
    group: "文档画像",
    items: [
      { key: "recognized_doc_type_label", name: "识别类型", requirement: "应识别出明确单据类型", source: "result" },
      { key: "recognized_doc_subtype_label", name: "细分类", requirement: "应识别出合同/付款细分类", source: "result" },
      { key: "workflow_state", name: "流程状态", requirement: "应生成明确的处理流转状态", source: "result" },
      { key: "next_action", name: "系统建议", requirement: "应给出下一步处理动作", source: "result" },
    ],
  },
  {
    group: "基础字段",
    items: [
      { key: "contract_no", name: "合同编号", requirement: "必须存在且可追溯" },
      { key: "request_no", name: "申请单编号", requirement: "付款单应有申请单编号" },
      { key: "contract_date", name: "合同日期", requirement: "合同场景应识别签订日期" },
      { key: "request_date", name: "申请日期", requirement: "付款单应识别申请日期" },
      { key: "payment_date", name: "计划付款日", requirement: "付款场景应识别付款日期" },
      { key: "currency", name: "币种", requirement: "应识别交易币种" },
      { key: "total_amount", name: "金额", requirement: "金额字段可解析" },
    ],
  },
];

const DOC_FIELD_SECTIONS = {
  contract: [
    {
      group: "主体信息",
      items: [
        { key: "party_a", name: "甲方", requirement: "应识别合同甲方" },
        { key: "party_b", name: "乙方", requirement: "应识别合同乙方" },
        { key: "seller", name: "卖方", requirement: "应识别卖方主体" },
        { key: "buyer", name: "买方", requirement: "应识别买方主体" },
        { key: "vendor", name: "供应方基线", requirement: "应识别用于付款核对的供应方" },
      ],
    },
    {
      group: "交易明细",
      items: [
        { key: "commodity_name", name: "货品/品名", requirement: "应识别主要货品" },
        { key: "quantity", name: "数量", requirement: "应识别数量" },
        { key: "quantity_unit", name: "数量单位", requirement: "应识别计量单位" },
        { key: "unit_price", name: "单价", requirement: "应尽量识别单价" },
        { key: "vat_amount", name: "税额", requirement: "采购合同应尽量识别税额" },
      ],
    },
    {
      group: "履约条款",
      items: [
        { key: "delivery_date", name: "交货日期", requirement: "采购合同应识别交货日期" },
        { key: "shipment_date", name: "装运期限", requirement: "销售合同应识别装运期限" },
        { key: "incoterm", name: "贸易术语", requirement: "销售合同应尽量识别 INCOTERM" },
        { key: "port_loading", name: "装运港", requirement: "出口合同应识别装运港" },
        { key: "port_discharge", name: "目的港/目的地", requirement: "出口合同应识别目的港或目的地" },
        { key: "beneficiary_account", name: "收汇账号", requirement: "如存在应识别收款账号" },
      ],
    },
  ],
  payment: [
    {
      group: "付款申请",
      items: [
        { key: "application_status", name: "审批状态", requirement: "应识别审批状态" },
        { key: "payment_type", name: "付款类型", requirement: "应识别预付款/尾款等类型" },
        { key: "payment_method", name: "付款方式", requirement: "应识别电汇/转账等方式" },
        { key: "payment_status", name: "支付状态", requirement: "应识别当前支付状态" },
      ],
    },
    {
      group: "收款信息",
      items: [
        { key: "payee", name: "收款人", requirement: "必须识别收款对象" },
        { key: "bank_name", name: "收款银行", requirement: "应识别开户银行" },
        { key: "bank_account", name: "银行账号", requirement: "必须识别银行账号" },
        { key: "advance_guarantee", name: "担保情况", requirement: "预付款应识别担保/预收外汇说明" },
      ],
    },
    {
      group: "关联单据",
      items: [
        { key: "sales_contract_no", name: "销售合同号", requirement: "应尽量识别销售合同号" },
        { key: "purchase_contract_no", name: "采购合同号", requirement: "应尽量识别采购合同号" },
        { key: "vendor", name: "供应方基线", requirement: "应保留和合同核对的主体信息" },
      ],
    },
    {
      group: "经办信息",
      items: [
        { key: "remark", name: "备注", requirement: "应保留付款用途说明" },
        { key: "handler", name: "经办人", requirement: "应识别经办人" },
        { key: "department", name: "部门", requirement: "应识别所属部门" },
      ],
    },
  ],
};

const AuditWorkspace = ({
  panelStyle,
  panelContent,
  docTypes,
  docType,
  onDocTypeChange,
  auditModelBackend = "local",
  onAuditModelBackendChange,
  onFileSelect,
  auditState,
  auditFile,
  onReset,
  onErpAction,
  isErpActionLoading = false,
  notice,
  fullWidth = false,
}) => {
  const fileInputRef = useRef(null);
  const [module, setModule] = useState("warning");
  const [keyword, setKeyword] = useState("");
  const [selectedRiskId, setSelectedRiskId] = useState("");
  const [selectedReportId, setSelectedReportId] = useState("");

  const status = auditState?.status || "idle";
  const isBusy = ["uploading", "pending", "running"].includes(status);
  const isDone = status === "done";
  const isFailed = status === "failed";
  const progress = Math.max(0, Math.min(100, Number(auditState?.progress) || 0));

  const result = auditState?.result || {};
  const findings = Array.isArray(result.findings) ? result.findings : [];
  const erpChecks = Array.isArray(result.erp_checks) ? result.erp_checks : [];
  const extracted = result.extracted_fields || {};
  const decisionTrace = Array.isArray(result.decision_trace) ? result.decision_trace : [];
  const riskLevel = String(result.risk_level || "low").toLowerCase();
  const riskLabel = riskLevel === "high" ? "高风险" : (riskLevel === "medium" ? "中风险" : "低风险");
  const riskClass = riskBadgeClass(riskLevel);
  const historyText = typeof panelContent === "string" ? panelContent.trim() : "";
  const showHistory = !isBusy && !isDone && !isFailed && !!historyText;
  const openFilePicker = () => {
    if (isBusy) return;
    fileInputRef.current?.click();
  };
  const handleUploadCardKeyDown = (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    openFilePicker();
  };

  const rank = { high: 3, medium: 2, low: 1 };
  const sortedFindings = [...findings].sort((a, b) => (rank[String(b?.severity || "").toLowerCase()] || 0) - (rank[String(a?.severity || "").toLowerCase()] || 0));
  const caseSummary = result.case_summary || {};
  const caseCompleteness = caseSummary.completeness || {};
  const caseDocuments = Array.isArray(caseSummary.documents) ? caseSummary.documents : [];
  const erpContext = result.erp_context || {};
  const findingBreakdown = result.finding_breakdown || {};
  const recognizedDocType = String(result.recognized_doc_type || extracted.doc_type || "").toLowerCase();
  const docFieldSections = [...BASE_FIELD_SECTIONS, ...(DOC_FIELD_SECTIONS[recognizedDocType] || [])];

  const warningRows = sortedFindings
    .filter((item) => {
      if (!keyword.trim()) return true;
      const text = [item?.message, item?.reason, item?.suggestion, item?.rule_id].filter(Boolean).join(" ").toLowerCase();
      return text.includes(keyword.trim().toLowerCase());
    })
    .map((item, idx) => {
      const evidence = item?.evidence || {};
      return {
        id: `${item?.rule_id || item?.type || "risk"}-${idx}`,
        index: idx + 1,
        level: String(item?.severity || "low").toLowerCase(),
        levelLabel: String(item?.severity || "low").toLowerCase() === "high" ? "高风险" : (String(item?.severity || "low").toLowerCase() === "medium" ? "中风险" : "低风险"),
        source: SOURCE_LABEL[String(item?.source || "rule").toLowerCase()] || "风险项",
        title: item?.message || "规则命中",
        reason: item?.reason || "",
        suggestion: item?.suggestion || "",
        confidence: confidenceText(item?.confidence),
        evidenceText: typeof evidence === "string" ? evidence : (evidence?.text || ""),
        highlight: typeof evidence === "string" ? "" : (evidence?.highlight || ""),
        actual: item?.actual,
        expected: item?.expected,
      };
    });

  const effectiveRiskId = selectedRiskId || warningRows[0]?.id || "";
  const selectedRisk = warningRows.find((r) => r.id === effectiveRiskId) || null;

  const fieldChecks = docFieldSections.flatMap((section, sectionIdx) =>
    (section.items || []).map((item, idx) => {
      const rawValue = item.source === "result" ? result?.[item.key] : extracted?.[item.key];
      const value = formatValue(rawValue);
      const pass = rawValue !== null && rawValue !== undefined && rawValue !== "";
      return {
        id: `field-${sectionIdx}-${idx}`,
        group: section.group,
        name: item.name,
        value,
        requirement: item.requirement,
        pass,
        actual: value,
        expected: item.requirement,
        evidence: pass ? `${item.name}：${value}` : `${item.name}未提取到值`,
        highlight: pass ? String(value) : "",
      };
    })
  );
  const erpRows = erpChecks.map((item, idx) => ({
      id: `erp-${idx}`,
      group: "财务审单",
      name: item?.name || item?.id || `ERP检查${idx + 1}`,
      value: formatValue(item?.actual ?? item?.value),
      requirement: formatValue(item?.expected ?? "满足审查规则"),
      pass: item?.passed !== false,
      evidence: item?.reason || "",
      highlight: formatValue(item?.actual ?? item?.value),
      actual: item?.actual ?? item?.value,
      expected: item?.expected,
    }));
  const caseRows = [
    {
      id: "case-complete",
      group: "案件完整性",
      name: "单据完整度",
      value: `${(caseCompleteness.present || []).length || 0}/${(caseCompleteness.required || []).length || 0}`,
      requirement: (caseCompleteness.required || []).join(" / ") || "按案件要求补齐单据",
      pass: !!caseCompleteness.complete,
      actual: (caseCompleteness.present || []).join(" / ") || "未识别",
      expected: (caseCompleteness.required || []).join(" / ") || "按案件要求补齐单据",
      evidence: `已上传：${(caseCompleteness.present || []).join(" / ") || "无"}；缺失：${(caseCompleteness.missing || []).join(" / ") || "无"}`,
      highlight: (caseCompleteness.missing || [])[0] || "",
    },
    {
      id: "case-docs",
      group: "案件完整性",
      name: "案件文档清单",
      value: String(caseDocuments.length || 0),
      requirement: "案件内单据应可追踪",
      pass: caseDocuments.length > 0,
      actual: caseDocuments.map((item) => `${item?.file_name || item?.doc_type || "document"}(${item?.status || "-"})`).join(" / "),
      expected: "至少存在 1 份案件文档",
      evidence: caseDocuments.map((item) => `${item?.file_name || item?.doc_type || "document"} · ${item?.doc_type || "-"} · ${item?.status || "-"}`).join("\n") || "暂无案件文档",
      highlight: caseDocuments[0]?.file_name || "",
    },
    {
      id: "erp-context",
      group: "ERP基线",
      name: "ERP上下文摘要",
      value: formatValue(erpContext.provider || "mock"),
      requirement: "合同金额、供应商状态、历史付款等应尽量可回溯",
      pass: Object.keys(erpContext || {}).length > 0,
      actual: erpContext,
      expected: "ERP 基线可读取",
      evidence: [
        `提供方：${formatValue(erpContext.provider)}`,
        `ERP合同金额：${formatValue(erpContext.contract_amount)}`,
        `历史已付：${formatValue(erpContext.paid_amount)}`,
        `供应商状态：${formatValue(erpContext.vendor_status)}`,
        `期望供应商：${formatValue(erpContext.expected_vendor)}`,
      ].join("\n"),
      highlight: formatValue(erpContext.expected_vendor),
    },
  ];
  const reportRows = [...fieldChecks, ...erpRows, ...caseRows];
  const effectiveReportId = selectedReportId || reportRows[0]?.id || "";
  const selectedReport = reportRows.find((r) => r.id === effectiveReportId) || null;
  const previewText = [result.summary, ...sortedFindings.slice(0, 8).map((f) => f?.message)].filter(Boolean).join("\n");
  const reportSummaryCards = [
    { label: "审单分数", value: formatValue(result.audit_score), hint: "综合规则、跨单据与AI语义" },
    { label: "风险分布", value: `高${findingBreakdown?.by_severity?.high || 0} / 中${findingBreakdown?.by_severity?.medium || 0} / 低${findingBreakdown?.by_severity?.low || 0}`, hint: "按严重级别汇总" },
    { label: "字段提取", value: `${fieldChecks.filter((item) => item.pass).length}/${fieldChecks.length}`, hint: "当前页面可核对字段" },
    { label: "ERP检查", value: `${erpRows.filter((item) => item.pass).length}/${erpRows.length}`, hint: "规则与ERP回写前校验" },
  ];

  const widthClass = fullWidth ? "md:w-full md:border-r-0" : "md:w-1/2 md:border-r";
  const workflow = String(result.workflow_state || auditState?.workflow_state || status || "idle");

  return (
    <div className={`w-full ${widthClass} flex flex-col flex-shrink-0 border-b md:border-b-0 border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 transition-all duration-300 ${panelStyle.border} shadow-sm z-20`}>
      <div className="px-5 py-4 border-b border-slate-200 dark:border-slate-800 bg-gradient-to-r from-cyan-50 via-white to-emerald-50 dark:from-slate-900 dark:via-slate-900 dark:to-slate-800">
        <div className="text-[11px] font-semibold tracking-[0.18em] uppercase text-cyan-700 dark:text-cyan-300">Smart Contract Review</div>
        <h2 className="mt-1 text-2xl md:text-3xl font-black text-slate-900 dark:text-slate-100">AI合同审校与履约风控中台</h2>
        <div className="mt-1 text-sm text-slate-600 dark:text-slate-300">合同上传识别、风险预警、审核报告、溯源分析一体化工作台</div>
        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          <span className="px-2 py-1 rounded-full border border-slate-300 dark:border-slate-700 bg-white/85 dark:bg-slate-900 text-slate-700 dark:text-slate-100">流程状态：{workflow}</span>
          {isDone && <span className={`px-2 py-1 rounded-full border ${riskClass}`}>{riskLabel}</span>}
          {isBusy && <span className="px-2 py-1 rounded-full border border-cyan-200 text-cyan-700 dark:border-cyan-800 dark:text-cyan-300"><Loader2 size={12} className="inline mr-1 animate-spin" />处理中</span>}
        </div>
      </div>

      <div className="flex-1 p-4 overflow-y-auto custom-scrollbar space-y-4">
        {notice && <div className="rounded-xl border border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-300 text-xs px-3 py-2">{notice}</div>}

        <section className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 space-y-2">
          {OVERVIEW_TEXT.map((line, idx) => <p key={idx} className="text-sm text-slate-600 dark:text-slate-300 leading-6">{line}</p>)}
        </section>

        <section className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden">
            <div className="w-full px-4 py-3 border-b border-slate-100 dark:border-slate-800">
              <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">审单设置</div>
            </div>
            <div className="px-4 pb-4 space-y-3">
              <div className="pt-3">
                <div className="text-xs text-slate-500 dark:text-slate-400 mb-2">单据类型</div>
                <div className="flex flex-wrap gap-2">
                  {(docTypes || []).map((item) => (
                    <button key={item.value} type="button" disabled={isBusy} onClick={() => onDocTypeChange && onDocTypeChange(item.value)} className={`px-3 py-1.5 rounded-full text-xs border ${docType === item.value ? "bg-cyan-600 border-cyan-600 text-white" : "border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300"}`}>{item.label}</button>
                  ))}
                </div>
              </div>
              <div>
                <div className="text-xs text-slate-500 dark:text-slate-400 mb-2">审单模型</div>
                <div className="flex gap-2">
                  {["local", "cloud"].map((item) => (
                    <button key={item} type="button" disabled={isBusy} onClick={() => onAuditModelBackendChange && onAuditModelBackendChange(item)} className={`px-3 py-1.5 rounded-full text-xs border ${auditModelBackend === item ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900" : "border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300"}`}>{item === "local" ? "本地" : "云端"}</button>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div
            role="button"
            tabIndex={isBusy ? -1 : 0}
            aria-disabled={isBusy}
            onClick={openFilePicker}
            onKeyDown={handleUploadCardKeyDown}
            className={`rounded-2xl border-2 border-dashed p-5 min-h-[180px] bg-gradient-to-r transition-colors ${
              isBusy
                ? "border-slate-200 dark:border-slate-700 from-slate-100 to-white dark:from-slate-900/60 dark:to-slate-800/50 cursor-not-allowed opacity-80"
                : "border-slate-300 dark:border-slate-600 from-slate-50 to-white dark:from-slate-900/70 dark:to-slate-800/60 cursor-pointer hover:border-cyan-400 dark:hover:border-cyan-500"
            }`}
          >
            <div className="h-full flex flex-col items-center justify-center text-center">
              <div className="w-12 h-12 rounded-2xl bg-slate-900 text-white dark:bg-white dark:text-slate-900 flex items-center justify-center">
                <FileUp size={20} />
              </div>
              <div className="mt-4 text-sm font-semibold text-slate-900 dark:text-slate-100">
                点击整个区域上传审单文件
              </div>
              <div className="mt-1 max-w-md text-sm text-slate-600 dark:text-slate-300">
                请按顺序上传：先合同，再发票/提单/装箱单，最后付款/报销单据
              </div>
              <div className="mt-1 text-xs text-slate-400 dark:text-slate-500">
                支持图片、PDF、Word
              </div>
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  openFilePicker();
                }}
                disabled={isBusy}
                className="mt-4 px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-black text-white text-xs font-semibold disabled:opacity-50"
              >
                选择文件
              </button>
              {auditFile && (
                <span className="mt-3 max-w-full truncate text-xs text-slate-500 dark:text-slate-400">
                  {auditFile.name} · {auditFile.sizeLabel}
                </span>
              )}
            </div>
            <input ref={fileInputRef} type="file" className="hidden" accept="image/*,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={onFileSelect} disabled={isBusy} />
          </div>
        </section>

        {isBusy && (
          <section className="rounded-2xl border border-cyan-200 dark:border-cyan-900/60 bg-cyan-50/60 dark:bg-cyan-950/20 p-4">
            <div className="flex justify-between text-sm text-cyan-800 dark:text-cyan-200"><span>AI 正在执行审单流程</span><span>{progress}%</span></div>
            <div className="mt-2 h-2 rounded-full bg-cyan-100 dark:bg-cyan-950/60 overflow-hidden"><div className="h-full bg-cyan-500" style={{ width: `${progress}%` }} /></div>
          </section>
        )}

        {isFailed && <section className="rounded-2xl border border-red-200 dark:border-red-900/60 bg-red-50 dark:bg-red-950/20 text-red-700 dark:text-red-300 p-4 text-sm">{auditState?.error_message || auditState?.error || "审单失败，请重试。"}</section>}
        {showHistory && <section className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 text-sm text-slate-700 dark:text-slate-200 whitespace-pre-wrap">{historyText}</section>}

        {isDone && (
          <section className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden">
            <div className="grid grid-cols-1 xl:grid-cols-[220px_minmax(0,1fr)]">
              <aside className="border-r border-slate-200 dark:border-slate-800 p-3 bg-slate-50 dark:bg-slate-950/60 space-y-2">
                {["warning", "report", "trace", "intro"].map((key) => (
                  <button key={key} type="button" onClick={() => setModule(key)} className={`w-full text-left rounded-xl border px-3 py-2 text-sm ${module === key ? "border-cyan-200 bg-cyan-50 dark:border-cyan-800 dark:bg-cyan-950/30" : "border-slate-200 dark:border-slate-800"}`}>{key === "warning" ? "合同履约异常预警" : key === "report" ? "合同履约审核报告" : key === "trace" ? "智能评审结果溯源" : "方案能力介绍"}</button>
                ))}
              </aside>
              <div className="p-4 space-y-4">
                {module === "warning" && (
                  <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_320px] gap-4">
                    <div className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
                      <div className="px-3 py-2 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 flex items-center gap-2"><Search size={14} className="text-slate-400" /><input value={keyword} onChange={(e) => setKeyword(e.target.value)} className="w-full bg-transparent text-xs outline-none text-slate-700 dark:text-slate-200" placeholder="搜索风险项..." /></div>
                      <div className="max-h-[420px] overflow-y-auto custom-scrollbar">
                        {warningRows.map((row) => (
                          <button key={row.id} type="button" onClick={() => setSelectedRiskId(row.id)} className={`w-full text-left p-3 border-t border-slate-100 dark:border-slate-800 ${effectiveRiskId === row.id ? "bg-cyan-50 dark:bg-cyan-950/20" : ""}`}>
                            <div className="text-xs text-slate-500 dark:text-slate-400">#{row.index} · {row.source}</div>
                            <div className="text-sm font-medium text-slate-900 dark:text-slate-100">{row.title}</div>
                          </button>
                        ))}
                        {warningRows.length === 0 && <div className="p-4 text-xs text-slate-400">暂无风险项</div>}
                      </div>
                    </div>
                    <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/60 p-4 space-y-2">
                      {selectedRisk ? (
                        <>
                          <div className={`inline-flex px-2 py-0.5 rounded-full border text-xs ${riskBadgeClass(selectedRisk.level)}`}>{selectedRisk.levelLabel}</div>
                          <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">{selectedRisk.title}</div>
                          {selectedRisk.reason && <div className="text-xs text-slate-600 dark:text-slate-300">触发原因：{selectedRisk.reason}</div>}
                          {selectedRisk.suggestion && <div className="text-xs text-slate-600 dark:text-slate-300">建议：{selectedRisk.suggestion}</div>}
                          {(selectedRisk.actual !== undefined || selectedRisk.expected !== undefined) && (
                            <div className="grid grid-cols-1 gap-2 text-xs text-slate-600 dark:text-slate-300">
                              <div>现值：{formatValue(selectedRisk.actual)}</div>
                              <div>期望：{formatValue(selectedRisk.expected)}</div>
                            </div>
                          )}
                          <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-3 text-xs text-slate-600 dark:text-slate-300 max-h-[220px] overflow-y-auto custom-scrollbar"><HighlightedText text={selectedRisk.evidenceText} highlight={selectedRisk.highlight} /></div>
                          {selectedRisk.confidence && <div className="text-[11px] text-slate-400 dark:text-slate-500">置信度：{selectedRisk.confidence}</div>}
                        </>
                      ) : <div className="text-xs text-slate-400">请选择风险项</div>}
                    </div>
                  </div>
                )}

                {module === "report" && (
                  <div className="space-y-4">
                    <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
                      {reportSummaryCards.map((card) => (
                        <div key={card.label} className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/60 px-4 py-3">
                          <div className="text-[11px] uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">{card.label}</div>
                          <div className="mt-2 text-xl font-semibold text-slate-900 dark:text-slate-100">{card.value}</div>
                          <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{card.hint}</div>
                        </div>
                      ))}
                    </div>
                    <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_340px] gap-4">
                      <div className="rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden">
                        {reportRows.map((row) => (
                          <button key={row.id} type="button" onClick={() => setSelectedReportId(row.id)} className={`w-full text-left p-3 border-t border-slate-100 dark:border-slate-800 ${effectiveReportId === row.id ? "bg-cyan-50 dark:bg-cyan-950/20" : ""}`}>
                            <div className="flex items-center justify-between gap-3">
                              <div className="text-xs text-slate-500 dark:text-slate-400">{row.group}</div>
                              <span className={`px-2 py-0.5 rounded-full border text-[11px] ${row.pass ? riskBadgeClass("low") : riskBadgeClass("medium")}`}>{row.pass ? "已提取/通过" : "缺失/待复核"}</span>
                            </div>
                            <div className="mt-1 text-sm font-medium text-slate-900 dark:text-slate-100">{row.name}</div>
                            <div className="text-xs text-slate-500 dark:text-slate-400">{row.value}</div>
                          </button>
                        ))}
                      </div>
                      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/60 p-4 space-y-2">
                        {selectedReport && (
                          <>
                            <div className="flex items-center gap-2">
                              <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">{selectedReport.name}</div>
                              <span className={`px-2 py-0.5 rounded-full border text-[11px] ${selectedReport.pass ? riskBadgeClass("low") : riskBadgeClass("medium")}`}>{selectedReport.pass ? "通过" : "待复核"}</span>
                            </div>
                            <div className="text-xs text-slate-500 dark:text-slate-400">要求：{selectedReport.requirement}</div>
                            <div className="grid grid-cols-1 gap-2 text-xs text-slate-600 dark:text-slate-300">
                              <div>现值：{formatValue(selectedReport.actual ?? selectedReport.value)}</div>
                              <div>期望：{formatValue(selectedReport.expected ?? selectedReport.requirement)}</div>
                            </div>
                            <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-3 text-xs text-slate-600 dark:text-slate-300 max-h-[280px] overflow-y-auto custom-scrollbar"><HighlightedText text={selectedReport.evidence || previewText} highlight={selectedReport.highlight} /></div>
                          </>
                        )}
                        <div className="flex flex-wrap gap-2 pt-1">
                          <button type="button" onClick={() => onErpAction && onErpAction("approved")} disabled={isErpActionLoading} className="px-3 py-1.5 rounded-md text-xs bg-emerald-600 text-white disabled:opacity-50">{isErpActionLoading ? "提交中..." : "回写通过"}</button>
                          <button type="button" onClick={() => onErpAction && onErpAction("need_more")} disabled={isErpActionLoading} className="px-3 py-1.5 rounded-md text-xs bg-amber-600 text-white disabled:opacity-50">回写补件</button>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {module === "trace" && (
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                    <div className="rounded-xl border border-slate-200 dark:border-slate-800 p-4 bg-slate-50 dark:bg-slate-900/60">
                      <div className="text-sm font-semibold text-slate-900 dark:text-slate-100 mb-2">决策链路</div>
                      <div className="space-y-2 max-h-[320px] overflow-y-auto custom-scrollbar">
                        {decisionTrace.map((item, idx) => <div key={idx} className="text-xs text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-slate-800 rounded-lg px-3 py-2">{item?.step || "step"}：{item?.detail || "-"}</div>)}
                        {decisionTrace.length === 0 && <div className="text-xs text-slate-400">暂无链路数据</div>}
                      </div>
                    </div>
                    <div className="rounded-xl border border-slate-200 dark:border-slate-800 p-4 bg-slate-50 dark:bg-slate-900/60">
                      <div className="text-sm font-semibold text-slate-900 dark:text-slate-100 mb-2">企业风险评估</div>
                      <div className="text-xs text-slate-600 dark:text-slate-300 space-y-1">
                        <div>主体风险：{extracted.vendor || "未识别主体"}</div>
                        <div>金额风险：{extracted.total_amount || "未识别金额"}</div>
                        <div>单据类型：{result.recognized_doc_type_label || extracted.doc_type || "-"}</div>
                        <div>细分类：{result.recognized_doc_subtype_label || extracted.doc_subtype || "-"}</div>
                        <div>案件完整度：{(caseCompleteness.present || []).length || 0}/{(caseCompleteness.required || []).length || 0}</div>
                        <div>风险分布：高{findingBreakdown?.by_severity?.high || 0} / 中{findingBreakdown?.by_severity?.medium || 0} / 低{findingBreakdown?.by_severity?.low || 0}</div>
                        <div>审查建议：{result.next_action || "建议人工复核"}</div>
                      </div>
                    </div>
                  </div>
                )}

                {module === "intro" && (
                  <div className="space-y-3">
                    {FEATURE_BLOCKS.map((block, idx) => (
                      <div key={idx} className="rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/60 p-4">
                        <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">{block.title}</div>
                        {block.lines.map((line, lineIdx) => <div key={lineIdx} className="text-sm text-slate-600 dark:text-slate-300 mt-1">{line}</div>)}
                      </div>
                    ))}
                    <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
                      <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">三大核心优势</div>
                      {ADVANTAGES.map((item, idx) => <div key={idx} className="text-sm text-slate-600 dark:text-slate-300 mt-1">{item}</div>)}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </section>
        )}
      </div>

      {(isDone || isFailed) && (
        <div className="px-4 py-3 border-t border-slate-200 dark:border-slate-800 bg-slate-100/70 dark:bg-slate-900/70 flex justify-end">
          <button type="button" onClick={onReset} disabled={isErpActionLoading} className="px-4 py-2 rounded-lg text-sm font-medium bg-slate-900 hover:bg-black text-white dark:bg-white dark:text-slate-900 disabled:opacity-50">重新审单</button>
        </div>
      )}
    </div>
  );
};

export default AuditWorkspace;
