import React, { startTransition, useCallback, useDeferredValue, useEffect, useState } from "react";
import {
  AlertCircle,
  Bot,
  Boxes,
  Building2,
  CalendarDays,
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  ClipboardCheck,
  Clock3,
  Eye,
  FileBadge2,
  FileSearch,
  FileText,
  Hash,
  Landmark,
  ListChecks,
  Loader2,
  Package,
  ReceiptText,
  RefreshCw,
  Route,
  ScanSearch,
  Search,
  ShieldAlert,
  ScrollText,
  Sparkles,
  Users,
  Workflow,
  X,
  XCircle,
} from "lucide-react";
import adminApi from "../../api/admin";
import AuditSourceFilesPanel from "../../components/AuditSourceFilesPanel";

const VIEW_OPTIONS = [
  { key: "warnings", label: "合同履约异常预警", icon: ShieldAlert },
  { key: "reports", label: "合同履约审核报告", icon: ClipboardCheck },
];

const DOC_TYPE_OPTIONS = [
  { value: "", label: "单据类型" },
  { value: "contract", label: "合同" },
  { value: "invoice", label: "发票" },
  { value: "packing_list", label: "装箱单" },
  { value: "bill_of_lading", label: "提单" },
  { value: "payment", label: "付款单" },
  { value: "expense", label: "报销单" },
];

const STATUS_OPTIONS = [
  { value: "", label: "处理状态" },
  { value: "done", label: "已完成" },
  { value: "pending", label: "待处理" },
  { value: "running", label: "处理中" },
  { value: "failed", label: "失败" },
];

const RISK_OPTIONS = [
  { value: "", label: "风险等级" },
  { value: "high", label: "高风险" },
  { value: "medium", label: "中风险" },
  { value: "low", label: "低风险" },
];

const REVIEW_OPTIONS = [
  { value: "", label: "复核结论" },
  { value: "approved", label: "已通过" },
  { value: "rejected", label: "已驳回" },
  { value: "need_more", label: "补充材料" },
  { value: "pending", label: "待复核" },
];

const AUDIT_RECORD_PAGE_SIZE = 100;

const cn = (...parts) => parts.filter(Boolean).join(" ");

const formatDate = (value) => {
  if (!value) return "-";
  const raw = String(value);
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw.slice(0, 10);
  return date.toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" });
};

const formatDateTime = (value) => {
  if (!value) return "-";
  const raw = String(value);
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw;
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
};

const formatMoney = (value, currency = "CNY") => {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "-";
  if (currency && currency !== "CNY") return `${currency} ${numeric.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}`;
  return `￥${numeric.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}`;
};

const riskTone = (risk) => {
  const normalized = String(risk || "").toLowerCase();
  if (normalized === "high") return "bg-red-50 text-red-700 border-red-200 dark:bg-red-950/40 dark:text-red-300 dark:border-red-900/70";
  if (normalized === "medium") return "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-900/70";
  return "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-900/70";
};

const riskLabel = (risk) => {
  const normalized = String(risk || "").toLowerCase();
  if (normalized === "high") return "高风险";
  if (normalized === "medium") return "中风险";
  return "低风险";
};

const reviewTone = (status) => {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "approved") return "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-900/70";
  if (normalized === "rejected") return "bg-red-50 text-red-700 border-red-200 dark:bg-red-950/40 dark:text-red-300 dark:border-red-900/70";
  if (normalized === "need_more") return "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-900/70";
  return "bg-slate-50 text-slate-600 border-slate-200 dark:bg-slate-900 dark:text-slate-300 dark:border-slate-700";
};

const reviewLabel = (status) => {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "approved") return "已通过";
  if (normalized === "rejected") return "已驳回";
  if (normalized === "need_more") return "补充材料";
  return "待复核";
};

const processTone = (status) => {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "done") return "text-emerald-600 dark:text-emerald-300";
  if (normalized === "failed") return "text-red-600 dark:text-red-300";
  if (normalized === "running") return "text-sky-600 dark:text-sky-300";
  return "text-slate-500 dark:text-slate-400";
};

const processLabel = (status) => {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "done") return "已完成";
  if (normalized === "failed") return "失败";
  if (normalized === "running") return "处理中";
  if (normalized === "pending") return "待处理";
  return normalized || "-";
};

const WORKFLOW_LABELS = {
  idle: "待处理",
  uploading: "上传中",
  pending: "待处理",
  pending_docs: "待补件",
  ocr: "OCR解析中",
  extract: "字段抽取中",
  extracting: "字段抽取中",
  rules: "规则校核中",
  rule_checking: "规则校核中",
  ai: "AI复核中",
  ai_review: "AI复核中",
  review: "结果汇总中",
  report: "报告输出中",
  aggregating: "报告输出中",
  review_required: "需人工复核",
  review_optional: "建议抽检",
  ready_for_erp: "可回写ERP",
  erp_pending_sync: "ERP同步中",
  done: "已完成",
  failed: "失败",
};

const workflowLabel = (value) => {
  const normalized = String(value || "").toLowerCase();
  return WORKFLOW_LABELS[normalized] || processLabel(normalized);
};

const DOC_TYPE_META = {
  contract: { label: "合同", icon: FileBadge2 },
  invoice: { label: "发票", icon: ReceiptText },
  packing_list: { label: "装箱单", icon: Package },
  bill_of_lading: { label: "提单", icon: ScrollText },
  payment: { label: "付款单", icon: CircleDollarSign },
  expense: { label: "报销单", icon: CircleDollarSign },
  trade_case: { label: "业务 Case", icon: Boxes },
};

const getDocTypeMeta = (value) => {
  const normalized = String(value || "").toLowerCase();
  return DOC_TYPE_META[normalized] || {
    label: DOC_TYPE_OPTIONS.find((item) => item.value === normalized)?.label || normalized || "未知类型",
    icon: FileSearch,
  };
};

const FIELD_META = {
  contract_title: { label: "合同标题", icon: FileText },
  project_name: { label: "项目名称", icon: FileText },
  subject: { label: "主题", icon: FileText },
  contract_no: { label: "合同编号", icon: FileBadge2 },
  invoice_no: { label: "发票编号", icon: ReceiptText },
  application_no: { label: "申请编号", icon: FileSearch },
  tax_no: { label: "税号", icon: Hash },
  vendor: { label: "供应商", icon: Building2 },
  payee: { label: "收款方", icon: Landmark },
  buyer: { label: "买方", icon: Users },
  customer: { label: "客户", icon: Users },
  payer: { label: "付款方", icon: Landmark },
  drawer: { label: "出票方", icon: Landmark },
  total_amount: { label: "总金额", icon: CircleDollarSign },
  currency: { label: "币种", icon: CircleDollarSign },
  contract_date: { label: "合同日期", icon: CalendarDays },
  invoice_date: { label: "发票日期", icon: CalendarDays },
  payment_date: { label: "付款日期", icon: CalendarDays },
  expense_date: { label: "报销日期", icon: CalendarDays },
  sign_date: { label: "签署日期", icon: CalendarDays },
  issue_date: { label: "签发日期", icon: CalendarDays },
  bank_name: { label: "开户行", icon: Landmark },
  bank_account: { label: "银行账号", icon: Landmark },
  po_no: { label: "采购订单号", icon: Hash },
  bl_no: { label: "提单号", icon: ScrollText },
  port_of_loading: { label: "装运港", icon: Route },
  port_of_discharge: { label: "目的港", icon: Route },
  remark: { label: "备注", icon: FileText },
};

const formatFieldLabel = (key) =>
  String(key || "")
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");

const getFieldMeta = (key) => FIELD_META[key] || { label: formatFieldLabel(key), icon: Hash };

const FINDING_SOURCE_LABELS = {
  rule: "规则校核",
  cross_doc: "跨单据比对",
  anomaly: "异常识别",
  history: "历史画像",
  ai: "AI研判",
  manual: "人工标注",
};

const findingSourceLabel = (value) => {
  const normalized = String(value || "").toLowerCase();
  return FINDING_SOURCE_LABELS[normalized] || (normalized ? formatFieldLabel(normalized) : "系统识别");
};

const MetricCard = ({ label, value, tone = "blue", icon: Icon, hint }) => {
  const toneClass =
    tone === "red"
      ? "from-red-50 to-white border-red-100 text-red-700 dark:from-red-950/30 dark:to-slate-900 dark:border-red-900/50 dark:text-red-300"
      : tone === "green"
        ? "from-emerald-50 to-white border-emerald-100 text-emerald-700 dark:from-emerald-950/30 dark:to-slate-900 dark:border-emerald-900/50 dark:text-emerald-300"
        : tone === "amber"
          ? "from-amber-50 to-white border-amber-100 text-amber-700 dark:from-amber-950/30 dark:to-slate-900 dark:border-amber-900/50 dark:text-amber-300"
          : "from-sky-50 to-white border-sky-100 text-sky-700 dark:from-sky-950/30 dark:to-slate-900 dark:border-sky-900/50 dark:text-sky-300";
  return (
    <div className={cn("rounded-2xl border bg-gradient-to-br p-4", toneClass)}>
      <div className="flex items-start justify-between gap-3">
        <div className="text-xs font-medium opacity-80">{label}</div>
        {Icon ? (
          <div className="flex h-9 w-9 items-center justify-center rounded-2xl border border-current/15 bg-white/60 dark:bg-slate-950/50">
            <Icon size={16} />
          </div>
        ) : null}
      </div>
      <div className="mt-2 text-2xl font-semibold">{value}</div>
      {hint ? <div className="mt-1 text-xs opacity-80">{hint}</div> : null}
    </div>
  );
};

const AuditAdminSkeleton = () => (
  <div className="space-y-4">
    {Array.from({ length: 5 }).map((_, idx) => (
      <div key={idx} className="rounded-2xl border border-slate-200 bg-white p-5 animate-pulse dark:border-slate-800 dark:bg-slate-900">
        <div className="h-4 w-56 rounded bg-slate-200 dark:bg-slate-700" />
        <div className="mt-3 h-3 w-80 rounded bg-slate-100 dark:bg-slate-800" />
        <div className="mt-4 grid grid-cols-3 gap-3">
          <div className="h-10 rounded-xl bg-slate-100 dark:bg-slate-800" />
          <div className="h-10 rounded-xl bg-slate-100 dark:bg-slate-800" />
          <div className="h-10 rounded-xl bg-slate-100 dark:bg-slate-800" />
        </div>
      </div>
    ))}
  </div>
);

const InfoItem = ({ icon: Icon = FileText, label, value, hint }) => (
  <div className="rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-3 dark:border-slate-700 dark:bg-slate-900">
    <div className="flex items-center gap-2 text-slate-500 dark:text-slate-400">
      <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-white text-sky-700 shadow-sm dark:bg-slate-950 dark:text-sky-300">
        <Icon size={15} />
      </div>
      <div className="text-[11px] uppercase tracking-[0.18em]">{label}</div>
    </div>
    <div className="mt-2 text-sm font-medium text-slate-700 break-all dark:text-slate-200">{value || "-"}</div>
    {hint ? <div className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">{hint}</div> : null}
  </div>
);

const DetailSection = ({ icon: Icon = FileText, title, hint, children }) => (
  <section className="overflow-hidden rounded-[26px] border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950">
    <div className="flex items-start gap-3 border-b border-slate-100 bg-slate-50/90 px-4 py-4 dark:border-slate-800 dark:bg-slate-900/80">
      <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-white text-sky-700 shadow-sm dark:bg-slate-950 dark:text-sky-300">
        <Icon size={18} />
      </div>
      <div className="min-w-0">
        <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">{title}</div>
        {hint ? <div className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">{hint}</div> : null}
      </div>
    </div>
    <div className="p-4">{children}</div>
  </section>
);

const TimelineItem = ({ icon: Icon = Clock3, title, meta, desc }) => (
  <div className="relative flex gap-3 pb-4 last:pb-0">
    <div className="relative flex flex-col items-center">
      <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-sky-100 bg-sky-50 text-sky-700 dark:border-sky-900/60 dark:bg-sky-950/40 dark:text-sky-300">
        <Icon size={16} />
      </div>
      <div className="mt-2 h-full w-px bg-slate-200 dark:bg-slate-800" />
    </div>
    <div className="min-w-0 flex-1 pt-1">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">{title}</div>
        <div className="text-[11px] text-slate-400 dark:text-slate-500">{meta || "-"}</div>
      </div>
      <div className="mt-1 text-sm leading-6 text-slate-600 dark:text-slate-300">{desc || "-"}</div>
    </div>
  </div>
);

const DetailModal = ({
  record,
  detail,
  open,
  loading,
  reviewComment,
  reviewSubmitting,
  onClose,
  onReviewCommentChange,
  onSubmitReview,
}) => {
  if (!open) return null;
  const job = detail?.job || {};
  const result = job?.result || {};
  const fields = result?.extracted_fields || {};
  const findings = Array.isArray(result?.findings) ? result.findings : [];
  const checks = Array.isArray(result?.erp_checks) ? result.erp_checks : [];
  const caseSummary = result?.case_summary && typeof result.case_summary === "object" ? result.case_summary : {};
  const completeness = caseSummary?.completeness && typeof caseSummary.completeness === "object" ? caseSummary.completeness : {};
  const caseDocuments = Array.isArray(caseSummary?.documents)
    ? caseSummary.documents
    : Array.isArray(job?.case_documents)
      ? job.case_documents
      : [];
  const documentReports = Array.isArray(caseSummary?.document_reports) ? caseSummary.document_reports : [];
  const historyIntelligence = result?.history_intelligence && typeof result.history_intelligence === "object" ? result.history_intelligence : {};
  const similarCases = Array.isArray(historyIntelligence?.similar_cases) ? historyIntelligence.similar_cases : [];
  const duplicateSignals = Array.isArray(historyIntelligence?.duplicate_signals) ? historyIntelligence.duplicate_signals : [];
  const vendorHistory = historyIntelligence?.vendor_history && typeof historyIntelligence.vendor_history === "object" ? historyIntelligence.vendor_history : {};
  const review = detail?.review && typeof detail.review === "object" ? detail.review : record?.review || {};
  const findingBreakdown = result?.finding_breakdown && typeof result.finding_breakdown === "object" ? result.finding_breakdown : {};
  const decisionTrace = Array.isArray(result?.decision_trace) ? result.decision_trace.filter(Boolean) : [];
  const aiAssessment = result?.ai_assessment;
  const aiSummary =
    typeof aiAssessment === "string"
      ? aiAssessment
      : aiAssessment?.summary || aiAssessment?.conclusion || aiAssessment?.decision || "";
  const currentDocMeta = getDocTypeMeta(job?.doc_type || record?.doc_type);
  const CurrentDocIcon = currentDocMeta.icon;
  const activeRiskLevel = result?.risk_level || record?.risk_level;
  const activeReviewStatus = review?.status || record?.review_status;
  const completenessRequired = Array.isArray(completeness?.required) ? completeness.required : [];
  const completenessMissing = Array.isArray(completeness?.missing) ? completeness.missing : [];
  const completenessPresent = new Set(
    Array.isArray(completeness?.present) && completeness.present.length > 0
      ? completeness.present
      : caseDocuments.map((item) => String(item?.tag || item?.doc_type || "").toLowerCase()).filter(Boolean)
  );
  const caseDocumentCount = Number(completeness?.total_documents || caseDocuments.length || record?.case_document_count || 0);
  const reviewScope = detail?.review_scope && typeof detail.review_scope === "object" ? detail.review_scope : {};
  const reviewScopeCount = Number(reviewScope?.affected_count || (record?.case_id && caseDocumentCount > 1 ? caseDocumentCount : 1));
  const isBatchReview = Boolean((reviewScope?.type === "case") || (record?.case_id && reviewScopeCount > 1));
  const passedChecks = checks.filter((item) => item?.passed === true).length;
  const failedChecks = Math.max(checks.length - passedChecks, 0);
  const orderedFieldEntries = [
    ...[
      "contract_title",
      "project_name",
      "subject",
      "contract_no",
      "invoice_no",
      "application_no",
      "vendor",
      "payee",
      "buyer",
      "customer",
      "payer",
      "drawer",
      "total_amount",
      "currency",
      "contract_date",
      "invoice_date",
      "payment_date",
      "expense_date",
      "sign_date",
      "issue_date",
      "bank_name",
      "bank_account",
      "po_no",
      "bl_no",
      "port_of_loading",
      "port_of_discharge",
      "remark",
    ]
      .filter((key) => fields?.[key] !== undefined && fields?.[key] !== null && String(fields[key]).trim() !== "")
      .map((key) => [key, fields[key]]),
    ...Object.entries(fields).filter(
      ([key, value]) =>
        ![
          "contract_title",
          "project_name",
          "subject",
          "contract_no",
          "invoice_no",
          "application_no",
          "vendor",
          "payee",
          "buyer",
          "customer",
          "payer",
          "drawer",
          "total_amount",
          "currency",
          "contract_date",
          "invoice_date",
          "payment_date",
          "expense_date",
          "sign_date",
          "issue_date",
          "bank_name",
          "bank_account",
          "po_no",
          "bl_no",
          "port_of_loading",
          "port_of_discharge",
          "remark",
        ].includes(key) &&
        value !== undefined &&
        value !== null &&
        String(value).trim() !== ""
    ),
  ];
  const summaryText = result?.summary || record?.summary || "暂无摘要";
  const nextAction = result?.next_action || record?.next_action || "暂无处置建议";
  const workflowText = workflowLabel(record?.workflow_state || job?.workflow_state || record?.status || job?.status);
  const reviewUpdatedAt = review?.updated_at || record?.review_updated_at;

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/45 backdrop-blur-sm px-4 py-8 overflow-y-auto">
      <div className="mx-auto max-w-6xl rounded-[28px] border border-slate-200 bg-white shadow-2xl overflow-hidden dark:border-slate-800 dark:bg-slate-950">
        <div className="flex items-center justify-between px-6 py-5 bg-gradient-to-r from-sky-700 to-blue-600 text-white">
          <div>
            <div className="text-xs uppercase tracking-[0.28em] text-white/70">Audit Detail</div>
            <div className="mt-1 text-2xl font-semibold">{record?.document_title || "审单详情"}</div>
            <div className="mt-2 flex flex-wrap gap-2 text-xs text-white/80">
              <span className="inline-flex items-center gap-1 rounded-full border border-white/20 bg-white/10 px-3 py-1">
                <CurrentDocIcon size={13} />
                {record?.doc_type_label || currentDocMeta.label}
              </span>
              <span className="inline-flex items-center gap-1 rounded-full border border-white/20 bg-white/10 px-3 py-1">
                <Workflow size={13} />
                {workflowText}
              </span>
              <span className="inline-flex items-center gap-1 rounded-full border border-white/20 bg-white/10 px-3 py-1">
                <Clock3 size={13} />
                {formatDateTime(job?.created_at || record?.created_at)}
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-white/20 bg-white/10 hover:bg-white/20"
          >
            <X size={18} />
          </button>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-[1.35fr_0.95fr]">
          <div className="p-6 space-y-5">
            <div className="flex flex-wrap gap-2">
              <span className={cn("inline-flex items-center justify-center whitespace-nowrap rounded-full border px-3 py-1 text-xs font-medium leading-none", riskTone(activeRiskLevel))}>
                {riskLabel(activeRiskLevel)}
              </span>
              <span className={cn("inline-flex items-center justify-center whitespace-nowrap rounded-full border px-3 py-1 text-xs font-medium leading-none", reviewTone(activeReviewStatus))}>
                {reviewLabel(activeReviewStatus)}
              </span>
              <span className="inline-flex items-center justify-center whitespace-nowrap rounded-full border border-slate-200 px-3 py-1 text-xs font-medium text-slate-600 dark:border-slate-700 dark:text-slate-300">
                流程：{workflowText}
              </span>
              {record?.case_id ? (
                <span className="inline-flex items-center justify-center whitespace-nowrap rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-xs font-medium text-sky-700 dark:border-sky-900/60 dark:bg-sky-950/40 dark:text-sky-300">
                  Case：{record.case_id}
                </span>
              ) : null}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
              <MetricCard
                label="风险命中"
                value={`${record?.finding_stats?.total || findings.length || 0} 项`}
                tone="red"
                icon={ShieldAlert}
                hint={`高风险 ${findingBreakdown?.by_severity?.high || 0} 项`}
              />
              <MetricCard
                label="校验通过"
                value={`${record?.erp_check_stats?.passed || passedChecks || 0} 项`}
                tone="green"
                icon={ListChecks}
                hint={`未通过 ${record?.erp_check_stats?.failed || failedChecks || 0} 项`}
              />
              <MetricCard
                label="审单评分"
                value={record?.audit_score ?? result?.audit_score ?? "-"}
                tone="blue"
                icon={Sparkles}
                hint={job?.model_type ? `模型 ${job.model_type}` : "综合规则、AI 与上下文评分"}
              />
              <MetricCard
                label="Case 文件"
                value={caseDocumentCount > 0 ? `${caseDocumentCount} 份` : "-"}
                tone={completenessMissing.length > 0 ? "amber" : "blue"}
                icon={Boxes}
                hint={record?.case_id ? (completenessMissing.length > 0 ? `缺 ${completenessMissing.length} 类` : "上下文已齐套") : "尚未关联"}
              />
            </div>

            <DetailSection icon={Sparkles} title="AI 摘要与处置建议" hint="点开后直接呈现摘要、建议动作与复核状态，而不是只停留在一句说明。">
              <div className="space-y-4">
                <div className="rounded-2xl border border-sky-100 bg-gradient-to-br from-sky-50 via-white to-cyan-50 p-4 dark:border-sky-900/40 dark:from-sky-950/30 dark:via-slate-950 dark:to-slate-950">
                  <div className="text-xs font-semibold uppercase tracking-[0.18em] text-sky-700 dark:text-sky-300">Summary</div>
                  <div className="mt-2 text-sm leading-7 text-slate-700 dark:text-slate-200">{summaryText}</div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <InfoItem icon={AlertCircle} label="当前建议" value={nextAction} />
                  <InfoItem
                    icon={ClipboardCheck}
                    label="复核状态"
                    value={reviewLabel(activeReviewStatus)}
                    hint={reviewUpdatedAt ? `最近更新：${formatDateTime(reviewUpdatedAt)}` : "尚未提交人工复核"}
                  />
                </div>
              </div>
            </DetailSection>

            <DetailSection icon={Building2} title="业务与单据画像" hint="把业务主体、对手方、金额、文件和单据归属拆成结构化信息，管理员点开后能快速判断。">
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                <InfoItem icon={CurrentDocIcon} label="单据类型" value={record?.doc_type_label || currentDocMeta.label} hint={result?.recognized_doc_subtype_label || "系统识别结果"} />
                <InfoItem icon={Hash} label="单据编号" value={record?.document_number} hint={`任务号 ${record?.job_id || "-"}`} />
                <InfoItem icon={CalendarDays} label="业务日期" value={record?.document_date ? formatDate(record.document_date) : formatDate(job?.created_at || record?.created_at)} />
                <InfoItem icon={Building2} label="业务主体" value={record?.company_name} />
                <InfoItem icon={Users} label="对手方" value={record?.counterparty_name} />
                <InfoItem icon={CircleDollarSign} label="单据金额" value={formatMoney(record?.amount, record?.currency)} />
                <InfoItem icon={FileText} label="文件名" value={record?.file_name || job?.file_name} />
                <InfoItem icon={Boxes} label="Case ID" value={record?.case_id} hint={record?.case_id ? `${caseDocumentCount} 份上下文文件` : "当前未挂载业务事项"} />
                <InfoItem icon={Users} label="提交用户" value={job?.user_id || record?.user_id} hint={job?.updated_at ? `最近更新 ${formatDateTime(job.updated_at)}` : undefined} />
              </div>
            </DetailSection>

            <DetailSection icon={FileBadge2} title="原始文件" hint="管理员查看详情时可以直接打开该次审单的原始文件，整包事项会列出全部关联单据。">
              <AuditSourceFilesPanel
                fileUrl={job?.file_url || record?.file_url}
                fileName={job?.file_name || record?.file_name}
                jobId={job?.job_id || record?.job_id}
                documents={caseDocuments}
                emptyText="当前记录还没有可打开的原始文件地址。"
                showHeader={false}
              />
            </DetailSection>

            <DetailSection icon={Boxes} title="Case 上下文" hint="点开审单记录就能看到业务事项的文件齐套度和已挂载文件，避免来回翻页面找上下文。">
              {record?.case_id || caseDocuments.length > 0 ? (
                <div className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <MetricCard
                      label="齐套状态"
                      value={completenessMissing.length > 0 ? `缺 ${completenessMissing.length} 类` : "已齐套"}
                      tone={completenessMissing.length > 0 ? "amber" : "green"}
                      icon={completenessMissing.length > 0 ? AlertCircle : CheckCircle2}
                      hint={completenessMissing.length > 0 ? completenessMissing.map((item) => getDocTypeMeta(item).label).join(" / ") : "合同、发票、装箱单、提单已齐全"}
                    />
                    <MetricCard
                      label="已挂载文件"
                      value={`${caseDocumentCount} 份`}
                      tone="blue"
                      icon={Boxes}
                      hint={documentReports.length > 0 ? `已形成 ${documentReports.length} 条文档报告` : "当前 Case 文件数量"}
                    />
                    <MetricCard
                      label="待补件"
                      value={completenessMissing.length > 0 ? `${completenessMissing.length} 类` : "无"}
                      tone={completenessMissing.length > 0 ? "amber" : "green"}
                      icon={FileSearch}
                      hint={completenessMissing.length > 0 ? completenessMissing.map((item) => getDocTypeMeta(item).label).join(" / ") : "当前无需补件"}
                    />
                  </div>

                  {completenessRequired.length > 0 ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {completenessRequired.map((item) => {
                        const meta = getDocTypeMeta(item);
                        const MetaIcon = meta.icon;
                        const isPresent = completenessPresent.has(item);
                        return (
                          <div
                            key={item}
                            className={cn(
                              "flex items-center justify-between gap-3 rounded-2xl border px-4 py-3",
                              isPresent
                                ? "border-emerald-200 bg-emerald-50 dark:border-emerald-900/60 dark:bg-emerald-950/30"
                                : "border-amber-200 bg-amber-50 dark:border-amber-900/60 dark:bg-amber-950/30"
                            )}
                          >
                            <div className="flex items-center gap-3">
                              <div className={cn(
                                "flex h-10 w-10 items-center justify-center rounded-2xl",
                                isPresent ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300" : "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300"
                              )}>
                                <MetaIcon size={18} />
                              </div>
                              <div>
                                <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">{meta.label}</div>
                                <div className="text-xs text-slate-500 dark:text-slate-400">{isPresent ? "已进入 Case 上下文" : "仍需补件"}</div>
                              </div>
                            </div>
                            <div className={cn("text-xs font-semibold", isPresent ? "text-emerald-700 dark:text-emerald-300" : "text-amber-700 dark:text-amber-300")}>
                              {isPresent ? "已挂载" : "待补"}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  ) : null}

                  {caseDocuments.length > 0 ? (
                    <div className="space-y-2">
                      <div className="text-xs uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">Case Documents</div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        {caseDocuments.slice(0, 8).map((item, idx) => {
                          const meta = getDocTypeMeta(item?.tag || item?.doc_type);
                          const MetaIcon = meta.icon;
                          return (
                            <div key={`${item?.job_id || item?.doc_id || idx}`} className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4 dark:border-slate-800 dark:bg-slate-900">
                              <div className="flex items-start gap-3">
                                <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-white text-sky-700 shadow-sm dark:bg-slate-950 dark:text-sky-300">
                                  <MetaIcon size={17} />
                                </div>
                                <div className="min-w-0 flex-1">
                                  <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">{item?.file_name || `${meta.label} 文件`}</div>
                                  <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-slate-500 dark:text-slate-400">
                                    <span>{meta.label}</span>
                                    <span>状态 {processLabel(item?.status)}</span>
                                    <span>{formatDateTime(item?.updated_at)}</span>
                                  </div>
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ) : null}
                </div>
              ) : (
                <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-5 text-sm leading-6 text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
                  当前记录还没有挂入业务 Case，上下文文件和齐套状态暂不可见。
                </div>
              )}
            </DetailSection>

            <DetailSection icon={ShieldAlert} title="风险清单" hint={`共 ${findings.length} 项，已拆出风险来源、触发原因和建议动作。`}>
              <div className="space-y-3">
                {loading ? (
                  <div className="rounded-2xl border border-slate-200 bg-slate-50 p-6 text-sm text-slate-500 flex items-center gap-2 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400"><Loader2 size={16} className="animate-spin" />加载详情中...</div>
                ) : findings.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-6 text-sm text-slate-400 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-500">暂无风险提示</div>
                ) : (
                  findings.map((item, idx) => (
                    <div key={`${item?.type || item?.message || idx}`} className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4 dark:border-slate-800 dark:bg-slate-900">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="flex items-start gap-3">
                          <div className={cn("mt-0.5 flex h-10 w-10 items-center justify-center rounded-2xl border", riskTone(item?.severity))}>
                            <ShieldAlert size={16} />
                          </div>
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className={cn("inline-flex items-center justify-center whitespace-nowrap rounded-full border px-2.5 py-1 text-[11px] font-medium leading-none", riskTone(item?.severity))}>
                                {riskLabel(item?.severity)}
                              </span>
                              <span className="inline-flex items-center justify-center whitespace-nowrap rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-medium text-slate-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300">
                                {findingSourceLabel(item?.source)}
                              </span>
                            </div>
                            <div className="mt-2 text-sm font-semibold text-slate-800 dark:text-slate-100">{item?.message || "未命名风险"}</div>
                          </div>
                        </div>
                        <span className={cn("inline-flex items-center justify-center whitespace-nowrap rounded-full border px-2.5 py-1 text-[11px] font-medium leading-none", riskTone(item?.severity))}>
                          {riskLabel(item?.severity)}
                        </span>
                      </div>
                      <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
                        <InfoItem icon={AlertCircle} label="触发原因" value={item?.reason || "-"} />
                        <InfoItem icon={ClipboardCheck} label="建议动作" value={item?.suggestion || item?.action || "-"} />
                      </div>
                    </div>
                  ))
                )}
              </div>
            </DetailSection>
          </div>

          <div className="border-l border-slate-200 bg-slate-50 p-6 space-y-5 dark:border-slate-800 dark:bg-slate-900/70">
            <DetailSection icon={FileText} title="结构化字段" hint={`已抽取 ${orderedFieldEntries.length} 个字段，点开即可看到比摘要更完整的字段细节。`}>
              {orderedFieldEntries.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-5 text-sm text-slate-400 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-500">
                  暂无结构化字段，可能仍在处理中或当前文件提取结果为空。
                </div>
              ) : (
                <div className="grid grid-cols-1 gap-3">
                  {orderedFieldEntries.map(([key, value]) => {
                    const meta = getFieldMeta(key);
                    const MetaIcon = meta.icon;
                    return (
                      <InfoItem
                        key={key}
                        icon={MetaIcon}
                        label={meta.label}
                        value={Array.isArray(value) ? value.join(" / ") : String(value)}
                      />
                    );
                  })}
                </div>
              )}
            </DetailSection>

            <DetailSection icon={ListChecks} title="规则与 ERP 校验" hint={`通过 ${record?.erp_check_stats?.passed || passedChecks || 0} 项，未通过 ${record?.erp_check_stats?.failed || failedChecks || 0} 项。`}>
              <div className="space-y-3">
                {checks.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-5 text-sm text-slate-400 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-500">暂无结构化校验项</div>
                ) : (
                  checks.map((item, idx) => (
                    <div key={`${item?.id || item?.name || idx}`} className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-950">
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex items-start gap-3">
                          <div className={cn(
                            "flex h-10 w-10 items-center justify-center rounded-2xl",
                            item?.passed ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300" : "bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-300"
                          )}>
                            {item?.passed ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
                          </div>
                          <div className="min-w-0">
                            <div className="text-sm font-semibold text-slate-700 dark:text-slate-200">{item?.name || "未命名检查项"}</div>
                            <div className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">{item?.reason || "-"}</div>
                          </div>
                        </div>
                        <span className={cn("text-xs font-semibold", item?.passed ? "text-emerald-600 dark:text-emerald-300" : "text-red-600 dark:text-red-300")}>
                          {item?.passed ? "通过" : "未通过"}
                        </span>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </DetailSection>

            <DetailSection icon={Workflow} title="处理轨迹" hint="把创建、解析、识别、Case 串联和人工复核放在同一条轨迹里，减少排查成本。">
              <div className="space-y-0">
                <TimelineItem
                  icon={Clock3}
                  title="任务创建"
                  meta={formatDateTime(job?.created_at || record?.created_at)}
                  desc={`审单编号 ${record?.job_id || job?.job_id || "-"}，当前流程为 ${workflowText}。`}
                />
                <TimelineItem
                  icon={ScanSearch}
                  title="文本解析与识别"
                  meta={result?.text_extract_mode || "未记录模式"}
                  desc={[result?.recognized_doc_type_label || currentDocMeta.label, result?.recognized_doc_subtype_label].filter(Boolean).join(" / ") || "已完成文本解析。"}
                />
                <TimelineItem
                  icon={ShieldAlert}
                  title="风险识别与建议"
                  meta={`${findings.length} 项风险 · ${record?.audit_score ?? result?.audit_score ?? "-"} 分`}
                  desc={nextAction}
                />
                <TimelineItem
                  icon={Boxes}
                  title="Case 串联"
                  meta={record?.case_id ? `Case ${record.case_id}` : "未挂载 Case"}
                  desc={record?.case_id
                    ? (completenessMissing.length > 0
                      ? `当前仍缺少 ${completenessMissing.map((item) => getDocTypeMeta(item).label).join(" / ")}。`
                      : "当前审单包文件齐套，可直接查看上下文。")
                    : "当前记录尚未挂载业务 Case。"}
                />
                <TimelineItem
                  icon={ClipboardCheck}
                  title="人工复核"
                  meta={reviewUpdatedAt ? formatDateTime(reviewUpdatedAt) : reviewLabel(activeReviewStatus)}
                  desc={review?.comment || (activeReviewStatus ? `当前复核结论：${reviewLabel(activeReviewStatus)}` : "待管理员补充复核意见。")}
                />
              </div>
            </DetailSection>

            <DetailSection icon={Bot} title="AI 研判与历史参照" hint="补充相似案例、重复信号、主体画像和决策轨迹，避免点开后只有一段摘要。">
              <div className="space-y-4">
                <div className="grid grid-cols-1 gap-3">
                  <InfoItem icon={Bot} label="AI 结论" value={aiSummary || "当前未产出独立 AI 结论，已合并进摘要。"} />
                  <InfoItem
                    icon={Building2}
                    label="供应商历史画像"
                    value={vendorHistory?.name || "暂无历史画像"}
                    hint={vendorHistory?.name ? `历史单据 ${vendorHistory?.total_documents || 0} 份，最近出现 ${formatDateTime(vendorHistory?.last_seen_at)}` : "历史画像暂未形成"}
                  />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <MetricCard label="相似案例" value={`${similarCases.length} 条`} tone="blue" icon={FileSearch} />
                  <MetricCard label="重复信号" value={`${duplicateSignals.length} 项`} tone={duplicateSignals.length > 0 ? "amber" : "green"} icon={Search} />
                </div>

                {similarCases.length > 0 ? (
                  <div className="space-y-2">
                    <div className="text-xs uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">Similar Cases</div>
                    {similarCases.slice(0, 3).map((item, idx) => (
                      <div key={`${item?.job_id || item?.file_name || idx}`} className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4 dark:border-slate-800 dark:bg-slate-900">
                        <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">{item?.file_name || item?.job_id || "历史单据"}</div>
                        <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                          相似度 {Math.round((Number(item?.score) || 0) * 100)}% {item?.contract_no ? `· 合同 ${item.contract_no}` : ""}
                        </div>
                        <div className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">{Array.isArray(item?.reasons) && item.reasons.length > 0 ? item.reasons.join(" / ") : "暂无额外说明"}</div>
                      </div>
                    ))}
                  </div>
                ) : null}

                {decisionTrace.length > 0 ? (
                  <div className="space-y-2">
                    <div className="text-xs uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">Decision Trace</div>
                    <div className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4 text-sm leading-6 text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
                      {decisionTrace.slice(0, 6).map((item, idx) => (
                        <div key={idx} className={cn(idx > 0 ? "mt-2 border-t border-slate-200 pt-2 dark:border-slate-800" : "")}>
                          {typeof item === "string" ? item : JSON.stringify(item)}
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            </DetailSection>

            <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-950">
              <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">管理员处置</div>
              <div className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">
                {isBatchReview ? `本次提交会对同一批次的 ${reviewScopeCount} 份单据一起生效。` : "可直接补充复核意见、要求补件或完成驳回，记录状态会在提交后同步刷新。"}
              </div>
              <textarea
                className="mt-3 min-h-[120px] w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none focus:border-sky-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:placeholder:text-slate-500"
                placeholder={isBatchReview ? "填写整包复核意见、补件说明或处置建议..." : "填写复核意见、补件说明或处置建议..."}
                value={reviewComment}
                onChange={(e) => onReviewCommentChange(e.target.value)}
              />
              {(review?.reviewer_id || reviewUpdatedAt) ? (
                <div className="mt-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs leading-5 text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
                  {review?.reviewer_id ? `复核人：${review.reviewer_id}` : "复核人：-"}
                  {reviewUpdatedAt ? ` · 最近更新：${formatDateTime(reviewUpdatedAt)}` : ""}
                </div>
              ) : null}
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => onSubmitReview("approved")}
                  disabled={!!reviewSubmitting}
                  className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
                >
                  {reviewSubmitting === "approved" ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
                  {isBatchReview ? "整包通过" : "复核通过"}
                </button>
                <button
                  type="button"
                  onClick={() => onSubmitReview("need_more")}
                  disabled={!!reviewSubmitting}
                  className="inline-flex items-center gap-2 rounded-xl bg-amber-500 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
                >
                  {reviewSubmitting === "need_more" ? <Loader2 size={14} className="animate-spin" /> : <AlertCircle size={14} />}
                  {isBatchReview ? "整包补件" : "要求补件"}
                </button>
                <button
                  type="button"
                  onClick={() => onSubmitReview("rejected")}
                  disabled={!!reviewSubmitting}
                  className="inline-flex items-center gap-2 rounded-xl bg-red-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
                >
                  {reviewSubmitting === "rejected" ? <Loader2 size={14} className="animate-spin" /> : <XCircle size={14} />}
                  {isBatchReview ? "整包驳回" : "驳回"}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

const WarningTable = ({ records, onOpenDetail }) => (
  <div className="overflow-x-auto">
    <table className="min-w-[1080px] w-full text-sm text-slate-700 dark:text-slate-200">
      <thead>
        <tr className="text-left text-xs text-slate-500 border-b border-slate-200 dark:text-slate-400 dark:border-slate-800">
          <th className="py-3 pr-4">序号</th>
          <th className="py-3 pr-4 whitespace-nowrap">Case 类型</th>
          <th className="py-3 pr-4">Case 标题</th>
          <th className="py-3 pr-4 whitespace-nowrap">业务公司</th>
          <th className="py-3 pr-4 whitespace-nowrap">单据日期</th>
          <th className="py-3 pr-4 whitespace-nowrap">风险级别</th>
          <th className="py-3 pr-4 whitespace-nowrap">处置情况</th>
          <th className="py-3 pr-4 whitespace-nowrap">当前流程</th>
          <th className="py-3 pr-0 text-right whitespace-nowrap">操作</th>
        </tr>
      </thead>
      <tbody>
        {records.map((record, idx) => (
          <tr key={record.job_id} className="border-b border-slate-100 hover:bg-sky-50/40 transition-colors dark:border-slate-800 dark:hover:bg-sky-950/20">
            <td className="py-4 pr-4 text-slate-500 dark:text-slate-400">{idx + 1}</td>
            <td className="py-4 pr-4 whitespace-nowrap">{record.doc_type_label}</td>
            <td className="py-4 pr-4 min-w-[340px]">
              <div className="font-medium text-slate-900 dark:text-slate-100">{record.document_title}</div>
              <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{record.case_id || record.document_number || record.file_name || record.job_id}</div>
            </td>
            <td className="py-4 pr-4">
              <div>{record.company_name || "-"}</div>
              <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{record.counterparty_name || "-"}</div>
            </td>
            <td className="py-4 pr-4 whitespace-nowrap">{formatDate(record.document_date || record.created_at)}</td>
            <td className="py-4 pr-4 whitespace-nowrap">
              <span className={cn("inline-flex items-center justify-center whitespace-nowrap rounded-full border px-2.5 py-1 text-xs font-medium leading-none", riskTone(record.risk_level))}>
                {riskLabel(record.risk_level)}
              </span>
            </td>
            <td className="py-4 pr-4 whitespace-nowrap">
              <div className={cn("inline-flex items-center justify-center whitespace-nowrap rounded-full border px-2.5 py-1 text-xs font-medium leading-none", reviewTone(record.review_status))}>
                {reviewLabel(record.review_status)}
              </div>
            </td>
            <td className={cn("py-4 pr-4 whitespace-nowrap font-medium", processTone(record.status))}>
              {record.workflow_state || processLabel(record.status)}
            </td>
            <td className="py-4 pr-0 text-right">
              <button
                type="button"
                onClick={() => onOpenDetail(record)}
                className="inline-flex items-center gap-1 text-sky-700 hover:text-sky-900 font-medium dark:text-sky-300 dark:hover:text-sky-200"
              >
                <Eye size={14} /> 查看
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);

const ReportCards = ({ records, onOpenDetail }) => (
  <div className="space-y-4">
    {records.map((record) => (
      <button
        key={record.job_id}
        type="button"
        onClick={() => onOpenDetail(record)}
        className="w-full rounded-[24px] border border-slate-200 bg-white p-5 text-left shadow-sm hover:shadow-md hover:border-sky-200 transition-all dark:border-slate-800 dark:bg-slate-900 dark:hover:border-sky-700"
      >
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <div className="text-lg font-semibold text-slate-900 dark:text-slate-100">{record.document_title}</div>
              <span className={cn("inline-flex items-center justify-center whitespace-nowrap rounded-full border px-2.5 py-1 text-[11px] font-medium leading-none", riskTone(record.risk_level))}>
                {riskLabel(record.risk_level)}
              </span>
            </div>
            <div className="mt-2 flex flex-wrap gap-x-5 gap-y-2 text-xs text-slate-500 dark:text-slate-400">
              <span>签发日期：{formatDate(record.document_date || record.created_at)}</span>
              <span>{record.case_id ? `Case：${record.case_id}` : `审单编号：${record.job_id}`}</span>
              <span>类型：{record.doc_type_label}</span>
            </div>
            <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-sm text-slate-600 dark:text-slate-300">
              <span>甲方/业务主体：{record.company_name || "-"}</span>
              <span>乙方/对手方：{record.counterparty_name || "-"}</span>
              <span>金额：{formatMoney(record.amount, record.currency)}</span>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <span className="rounded-full bg-red-500 px-3 py-1 text-xs font-medium text-white">
                风险命中：{record.finding_stats?.total || 0} 项
              </span>
              <span className="rounded-full bg-emerald-500 px-3 py-1 text-xs font-medium text-white">
                校验通过：{record.erp_check_stats?.passed || 0} 项
              </span>
              <span className="rounded-full bg-amber-500 px-3 py-1 text-xs font-medium text-white">
                校验未过：{record.erp_check_stats?.failed || 0} 项
              </span>
            </div>
            <div className="mt-3 text-sm text-slate-600 line-clamp-2 dark:text-slate-300">{record.headline || record.summary || "暂无异常说明"}</div>
          </div>

          <div className="w-full xl:w-[220px] rounded-2xl bg-slate-50 border border-slate-200 px-4 py-4 dark:bg-slate-950 dark:border-slate-800">
            <div className="text-right text-2xl font-semibold text-slate-900 dark:text-slate-100">{formatMoney(record.amount, record.currency)}</div>
            <div className="mt-3 flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
              <span>审单评分</span>
              <span className="font-semibold text-slate-700 dark:text-slate-200">{record.audit_score ?? "-"}</span>
            </div>
            <div className="mt-2 flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
              <span>复核结论</span>
              <span className="font-semibold text-slate-700 dark:text-slate-200">{reviewLabel(record.review_status)}</span>
            </div>
            <div className="mt-2 flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
              <span>当前流程</span>
              <span className="font-semibold text-slate-700 dark:text-slate-200">{record.workflow_state || processLabel(record.status)}</span>
            </div>
          </div>
        </div>
      </button>
    ))}
  </div>
);

const AuditAdminWorkspace = () => {
  const [view, setView] = useState("warnings");
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [page, setPage] = useState(0);
  const [meta, setMeta] = useState({
    count: 0,
    total_visible: 0,
    offset: 0,
    limit: AUDIT_RECORD_PAGE_SIZE,
    has_more: false,
    stats: null,
  });
  const [filters, setFilters] = useState({
    query: "",
    docType: "",
    status: "",
    risk: "",
    review: "",
  });
  const [detailOpen, setDetailOpen] = useState(false);
  const [activeRecord, setActiveRecord] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [reviewComment, setReviewComment] = useState("");
  const [reviewSubmitting, setReviewSubmitting] = useState("");
  const deferredQuery = useDeferredValue(filters.query);

  const loadRecords = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    const effectiveQuery = (deferredQuery || filters.query || "").trim();
    try {
      const res = await adminApi.listAuditRecords({
        limit: AUDIT_RECORD_PAGE_SIZE,
        offset: page * AUDIT_RECORD_PAGE_SIZE,
        group_by: "case",
        query: effectiveQuery || undefined,
        doc_type: filters.docType || undefined,
        status: filters.status || undefined,
        risk_level: filters.risk || undefined,
        review_status: filters.review || undefined,
      });
      startTransition(() => {
        setRecords(Array.isArray(res?.data) ? res.data : []);
        setMeta({
          count: Number(res?.meta?.count || 0),
          total_visible: Number(res?.meta?.total_visible || 0),
          offset: Number(res?.meta?.offset || 0),
          limit: Number(res?.meta?.limit || AUDIT_RECORD_PAGE_SIZE),
          has_more: Boolean(res?.meta?.has_more),
          stats: res?.meta?.stats && typeof res.meta.stats === "object" ? res.meta.stats : null,
        });
      });
    } catch {
      setRecords([]);
      setMeta({
        count: 0,
        total_visible: 0,
        offset: page * AUDIT_RECORD_PAGE_SIZE,
        limit: AUDIT_RECORD_PAGE_SIZE,
        has_more: false,
        stats: null,
      });
      setLoadError("审单记录加载失败，请检查当前账号权限、登录状态或后端接口。");
    } finally {
      setLoading(false);
    }
  }, [deferredQuery, filters.docType, filters.query, filters.review, filters.risk, filters.status, page]);

  useEffect(() => {
    loadRecords();
  }, [loadRecords]);

  const visibleRecords = records;

  const openDetail = async (record) => {
    setActiveRecord(record);
    setDetailOpen(true);
    setDetailLoading(true);
    setReviewComment(record?.review?.comment || "");
    try {
      const res = await adminApi.getAuditDetail(record.job_id);
      setDetail(res?.data || null);
      setReviewComment(res?.data?.review?.comment || record?.review?.comment || "");
    } catch {
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const closeDetail = () => {
    setDetailOpen(false);
    setActiveRecord(null);
    setDetail(null);
    setReviewComment("");
    setReviewSubmitting("");
  };

  const submitReview = async (reviewStatus) => {
    if (!activeRecord?.job_id) return;
    setReviewSubmitting(reviewStatus);
    const activeCaseId = activeRecord?.case_id || detail?.job?.case_id || detail?.job?.result?.case_summary?.case_id || "";
    const activeCaseDocuments = Array.isArray(detail?.job?.result?.case_summary?.documents)
      ? detail.job.result.case_summary.documents
      : Array.isArray(detail?.job?.case_documents)
        ? detail.job.case_documents
        : [];
    const applyToCase = Boolean(activeCaseId) && activeCaseDocuments.length > 1;
    try {
      await adminApi.reviewAudit({
        job_id: activeRecord.job_id,
        status: reviewStatus,
        comment: reviewComment || undefined,
        case_id: applyToCase ? activeCaseId : undefined,
        apply_to_case: applyToCase || undefined,
      });
      await loadRecords();
      const latest = await adminApi.getAuditDetail(activeRecord.job_id);
      setDetail(latest?.data || null);
      const nextReview = latest?.data?.review || {};
      setReviewComment(nextReview.comment || reviewComment);
      setActiveRecord((prev) => ({
        ...(prev || {}),
        review_status: nextReview.status || reviewStatus,
        review: nextReview,
      }));
    } catch (error) {
      window.alert(error?.message || "复核提交失败");
    } finally {
      setReviewSubmitting("");
    }
  };

  const totalAmount = visibleRecords.reduce((sum, item) => sum + (Number(item?.amount) || 0), 0);
  const metaStats = meta?.stats && typeof meta.stats === "object" ? meta.stats : {};
  const metrics = {
    total: Number(metaStats.total ?? meta.total_visible ?? visibleRecords.length),
    high: Number(metaStats.high ?? visibleRecords.filter((item) => item?.risk_level === "high").length),
    pending: Number(metaStats.pending ?? visibleRecords.filter((item) => !item?.review_status || item?.review_status === "need_more").length),
    approved: Number(metaStats.approved ?? visibleRecords.filter((item) => item?.review_status === "approved").length),
  };

  return (
    <div className="rounded-[32px] border border-slate-200 bg-white shadow-[0_30px_80px_rgba(15,23,42,0.08)] overflow-hidden dark:border-slate-800 dark:bg-slate-950 dark:shadow-[0_30px_80px_rgba(2,6,23,0.65)]">
      <div className="flex items-center justify-between bg-gradient-to-r from-sky-700 via-blue-700 to-blue-600 px-6 py-4 text-white">
        <div>
          <div className="text-xs tracking-[0.32em] uppercase text-white/70">Enterprise Intelligent Audit</div>
          <div className="mt-1 text-xl font-semibold">合同履约智能审查后台</div>
        </div>
        <div className="hidden md:flex items-center gap-3 text-sm text-white/80">
          <Sparkles size={16} />
          企业级审单预警、报告与复核中心
        </div>
      </div>

      <div className="flex flex-col lg:flex-row min-h-[780px]">
        <aside className="w-full lg:w-[220px] border-r border-slate-200 bg-slate-50 px-4 py-5 dark:border-slate-800 dark:bg-slate-950">
          <div className="space-y-2">
            {VIEW_OPTIONS.map((item) => {
              const Icon = item.icon;
              const active = view === item.key;
              return (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => setView(item.key)}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-2xl px-4 py-3 text-left text-sm font-medium transition-colors",
                    active ? "bg-blue-600 text-white shadow-sm" : "text-slate-600 hover:bg-white dark:text-slate-300 dark:hover:bg-slate-900"
                  )}
                >
                  <Icon size={16} />
                  <span className="flex-1">{item.label}</span>
                  <ChevronRight size={14} className={active ? "opacity-100" : "opacity-40"} />
                </button>
              );
            })}
          </div>

          <div className="mt-6 space-y-3">
            <MetricCard label="当前 Case 数" value={metrics.total} tone="blue" />
            <MetricCard label="高风险 Case" value={metrics.high} tone="red" />
            <MetricCard label="待处置/补件" value={metrics.pending} tone="amber" />
            <MetricCard label="已复核通过" value={metrics.approved} tone="green" />
          </div>
        </aside>

        <section className="flex-1 bg-[#f6f8fc] dark:bg-[#07111f]">
          <div className="border-b border-slate-200 bg-white px-6 py-5 dark:border-slate-800 dark:bg-slate-950">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
              <div>
                <div className="flex items-center gap-2 text-sm text-slate-400 dark:text-slate-500">
                  <FileBadge2 size={16} />
                  <span>审单后台</span>
                  <ChevronRight size={14} />
                  <span className="text-slate-600 dark:text-slate-300">{view === "warnings" ? "合同履约异常预警" : "合同履约审核报告"}</span>
                </div>
                <div className="mt-2 text-xs text-sky-700 dark:text-sky-300">
                  {view === "warnings" ? `找到相关异常 Case ${meta.total_visible || visibleRecords.length} 个` : `找到相关审核报告 Case ${meta.total_visible || visibleRecords.length} 个`}
                </div>
              </div>
              <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
                <CircleDollarSign size={15} />
                关联金额合计：<span className="font-semibold text-slate-800 dark:text-slate-100">{formatMoney(totalAmount)}</span>
              </div>
            </div>

            <div className="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-[1.2fr_repeat(4,minmax(0,160px))_110px]">
              <label className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-700 dark:bg-slate-900">
                <Search size={16} className="text-slate-400 dark:text-slate-500" />
                <input
                  value={filters.query}
                  onChange={(e) => {
                    const value = e.target.value;
                    setPage(0);
                    setFilters((prev) => ({ ...prev, query: value }));
                  }}
                  placeholder="请输入合同名称、编号、公司名称"
                  className="w-full bg-transparent text-sm text-slate-700 outline-none placeholder:text-slate-400 dark:text-slate-200 dark:placeholder:text-slate-500"
                />
              </label>

              <select
                value={filters.docType}
                onChange={(e) => {
                  const value = e.target.value;
                  setPage(0);
                  setFilters((prev) => ({ ...prev, docType: value }));
                }}
                className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
              >
                {DOC_TYPE_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>

              <select
                value={filters.status}
                onChange={(e) => {
                  const value = e.target.value;
                  setPage(0);
                  setFilters((prev) => ({ ...prev, status: value }));
                }}
                className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
              >
                {STATUS_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>

              <select
                value={filters.risk}
                onChange={(e) => {
                  const value = e.target.value;
                  setPage(0);
                  setFilters((prev) => ({ ...prev, risk: value }));
                }}
                className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
              >
                {RISK_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>

              <select
                value={filters.review}
                onChange={(e) => {
                  const value = e.target.value;
                  setPage(0);
                  setFilters((prev) => ({ ...prev, review: value }));
                }}
                className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
              >
                {REVIEW_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>

              <button
                type="button"
                onClick={loadRecords}
                className="inline-flex items-center justify-center gap-2 rounded-2xl bg-blue-600 px-4 py-3 text-sm font-medium text-white hover:bg-blue-700"
              >
                <RefreshCw size={15} />
                刷新
              </button>
            </div>

            <div className="mt-4 flex flex-col gap-3 text-xs text-slate-500 dark:text-slate-400 md:flex-row md:items-center md:justify-between">
              <div>
                当前显示 {visibleRecords.length} 个 Case，匹配结果 {meta.total_visible || visibleRecords.length} 个 Case
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setPage((prev) => Math.max(prev - 1, 0))}
                  disabled={loading || page === 0}
                  className="rounded-xl border border-slate-200 px-3 py-1.5 text-slate-600 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:text-slate-300"
                >
                  上一页
                </button>
                <span>第 {page + 1} 页</span>
                <button
                  type="button"
                  onClick={() => setPage((prev) => prev + 1)}
                  disabled={loading || !meta.has_more}
                  className="rounded-xl border border-slate-200 px-3 py-1.5 text-slate-600 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:text-slate-300"
                >
                  下一页
                </button>
              </div>
            </div>
          </div>

          <div className="p-6">
            {loading ? (
              <AuditAdminSkeleton />
            ) : loadError ? (
              <div className="rounded-[28px] border border-amber-200 bg-amber-50 px-6 py-10 text-center dark:border-amber-900/60 dark:bg-amber-950/20">
                <AlertCircle className="mx-auto text-amber-500 dark:text-amber-300" size={34} />
                <div className="mt-4 text-lg font-medium text-amber-900 dark:text-amber-100">审单记录暂时无法加载</div>
                <div className="mt-2 text-sm text-amber-700 dark:text-amber-300">{loadError}</div>
              </div>
            ) : visibleRecords.length === 0 ? (
              <div className="rounded-[28px] border border-dashed border-slate-300 bg-white px-6 py-20 text-center dark:border-slate-700 dark:bg-slate-900">
                <FileSearch className="mx-auto text-slate-300 dark:text-slate-600" size={34} />
                <div className="mt-4 text-lg font-medium text-slate-700 dark:text-slate-200">暂无符合条件的审单 Case</div>
                <div className="mt-2 text-sm text-slate-400 dark:text-slate-500">调整筛选条件后重试，或等待新的审单批次进入后台。</div>
              </div>
            ) : view === "warnings" ? (
              <div className="rounded-[28px] border border-slate-200 bg-white px-6 py-3 shadow-sm dark:border-slate-800 dark:bg-slate-900">
                <WarningTable records={visibleRecords} onOpenDetail={openDetail} />
              </div>
            ) : (
              <ReportCards records={visibleRecords} onOpenDetail={openDetail} />
            )}
          </div>
        </section>
      </div>

      <DetailModal
        record={activeRecord}
        detail={detail}
        open={detailOpen}
        loading={detailLoading}
        reviewComment={reviewComment}
        reviewSubmitting={reviewSubmitting}
        onClose={closeDetail}
        onReviewCommentChange={setReviewComment}
        onSubmitReview={submitReview}
      />
    </div>
  );
};

export default AuditAdminWorkspace;
