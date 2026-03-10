import React, { startTransition, useCallback, useDeferredValue, useEffect, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  ClipboardCheck,
  Eye,
  FileBadge2,
  FileSearch,
  Loader2,
  RefreshCw,
  Search,
  ShieldAlert,
  Sparkles,
  X,
  XCircle,
} from "lucide-react";
import adminApi from "../../api/admin";

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

const MetricCard = ({ label, value, tone = "blue" }) => {
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
      <div className="text-xs font-medium opacity-80">{label}</div>
      <div className="mt-2 text-2xl font-semibold">{value}</div>
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

const InfoItem = ({ label, value }) => (
  <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-700 dark:bg-slate-900">
    <div className="text-[11px] uppercase tracking-[0.18em] text-slate-400 dark:text-slate-500">{label}</div>
    <div className="mt-1 text-sm font-medium text-slate-700 break-all dark:text-slate-200">{value || "-"}</div>
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

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/45 backdrop-blur-sm px-4 py-8 overflow-y-auto">
      <div className="mx-auto max-w-6xl rounded-[28px] border border-slate-200 bg-white shadow-2xl overflow-hidden dark:border-slate-800 dark:bg-slate-950">
        <div className="flex items-center justify-between px-6 py-5 bg-gradient-to-r from-sky-700 to-blue-600 text-white">
          <div>
            <div className="text-xs uppercase tracking-[0.28em] text-white/70">Audit Detail</div>
            <div className="mt-1 text-2xl font-semibold">{record?.document_title || "审单详情"}</div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-white/20 bg-white/10 hover:bg-white/20"
          >
            <X size={18} />
          </button>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-[1.3fr_0.9fr]">
          <div className="p-6 space-y-5">
            <div className="flex flex-wrap gap-2">
              <span className={cn("inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium", riskTone(record?.risk_level))}>
                {riskLabel(record?.risk_level)}
              </span>
              <span className={cn("inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium", reviewTone(record?.review_status))}>
                {reviewLabel(record?.review_status)}
              </span>
              <span className="inline-flex items-center rounded-full border border-slate-200 px-3 py-1 text-xs font-medium text-slate-600 dark:border-slate-700 dark:text-slate-300">
                流程：{record?.workflow_state || processLabel(record?.status)}
              </span>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-900">
              <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">摘要</div>
              <div className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">{record?.summary || "暂无摘要"}</div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <InfoItem label="单据编号" value={record?.document_number} />
              <InfoItem label="单据日期" value={record?.document_date ? formatDate(record.document_date) : "-"} />
              <InfoItem label="业务主体" value={record?.company_name} />
              <InfoItem label="单据金额" value={formatMoney(record?.amount, record?.currency)} />
            </div>

            <div className="rounded-2xl border border-slate-200 overflow-hidden dark:border-slate-800">
              <div className="px-4 py-3 border-b border-slate-200 bg-slate-50 flex items-center justify-between dark:border-slate-800 dark:bg-slate-900">
                <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">风险提示</div>
                <div className="text-xs text-slate-500 dark:text-slate-400">共 {findings.length} 项</div>
              </div>
              <div className="max-h-[360px] overflow-y-auto">
                {loading ? (
                  <div className="p-6 text-sm text-slate-500 flex items-center gap-2 dark:text-slate-400"><Loader2 size={16} className="animate-spin" />加载详情中...</div>
                ) : findings.length === 0 ? (
                  <div className="p-6 text-sm text-slate-400 dark:text-slate-500">暂无风险提示</div>
                ) : (
                  findings.slice(0, 12).map((item, idx) => (
                    <div key={`${item?.type || item?.message || idx}`} className="px-4 py-4 border-t first:border-t-0 border-slate-100 dark:border-slate-800">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={cn("inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium", riskTone(item?.severity))}>
                          {riskLabel(item?.severity)}
                        </span>
                        <div className="text-sm font-semibold text-slate-800 dark:text-slate-100">{item?.message || "未命名风险"}</div>
                      </div>
                      <div className="mt-2 text-sm text-slate-600 leading-6 dark:text-slate-300">{item?.reason || "-"}</div>
                      <div className="mt-2 text-xs text-sky-700 dark:text-sky-300">建议：{item?.suggestion || item?.action || "-"}</div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>

          <div className="border-l border-slate-200 bg-slate-50 p-6 space-y-5 dark:border-slate-800 dark:bg-slate-900/70">
            <div className="grid grid-cols-1 gap-3">
              <MetricCard label="风险命中" value={`${record?.finding_stats?.total || 0} 项`} tone="red" />
              <MetricCard label="校验通过" value={`${record?.erp_check_stats?.passed || 0} 项`} tone="green" />
              <MetricCard label="审单评分" value={record?.audit_score ?? "-"} tone="blue" />
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden dark:border-slate-800 dark:bg-slate-950">
              <div className="px-4 py-3 border-b border-slate-200 bg-slate-50 text-sm font-semibold text-slate-900 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100">核心字段</div>
              <div className="p-4 grid grid-cols-1 gap-3">
                <InfoItem label="合同编号" value={fields?.contract_no} />
                <InfoItem label="发票编号" value={fields?.invoice_no} />
                <InfoItem label="供应商/收款方" value={fields?.vendor || fields?.payee} />
                <InfoItem label="Case ID" value={record?.case_id} />
              </div>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden dark:border-slate-800 dark:bg-slate-950">
              <div className="px-4 py-3 border-b border-slate-200 bg-slate-50 text-sm font-semibold text-slate-900 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-100">审核校验</div>
              <div className="max-h-[260px] overflow-y-auto">
                {checks.length === 0 ? (
                  <div className="p-4 text-sm text-slate-400 dark:text-slate-500">暂无结构化校验项</div>
                ) : (
                  checks.slice(0, 10).map((item, idx) => (
                    <div key={`${item?.id || item?.name || idx}`} className="px-4 py-3 border-t first:border-t-0 border-slate-100 dark:border-slate-800">
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-sm font-medium text-slate-700 dark:text-slate-200">{item?.name || "未命名检查项"}</div>
                        <span className={cn("text-xs font-medium", item?.passed ? "text-emerald-600" : "text-red-600")}>
                          {item?.passed ? "通过" : "未通过"}
                        </span>
                      </div>
                      <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{item?.reason || "-"}</div>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-950">
              <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">管理员处置</div>
              <textarea
                className="mt-3 min-h-[120px] w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none focus:border-sky-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:placeholder:text-slate-500"
                placeholder="填写复核意见、补件说明或处置建议..."
                value={reviewComment}
                onChange={(e) => onReviewCommentChange(e.target.value)}
              />
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => onSubmitReview("approved")}
                  disabled={!!reviewSubmitting}
                  className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
                >
                  {reviewSubmitting === "approved" ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
                  复核通过
                </button>
                <button
                  type="button"
                  onClick={() => onSubmitReview("need_more")}
                  disabled={!!reviewSubmitting}
                  className="inline-flex items-center gap-2 rounded-xl bg-amber-500 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
                >
                  {reviewSubmitting === "need_more" ? <Loader2 size={14} className="animate-spin" /> : <AlertCircle size={14} />}
                  要求补件
                </button>
                <button
                  type="button"
                  onClick={() => onSubmitReview("rejected")}
                  disabled={!!reviewSubmitting}
                  className="inline-flex items-center gap-2 rounded-xl bg-red-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
                >
                  {reviewSubmitting === "rejected" ? <Loader2 size={14} className="animate-spin" /> : <XCircle size={14} />}
                  驳回
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
    <table className="min-w-full text-sm text-slate-700 dark:text-slate-200">
      <thead>
        <tr className="text-left text-xs text-slate-500 border-b border-slate-200 dark:text-slate-400 dark:border-slate-800">
          <th className="py-3 pr-4">序号</th>
          <th className="py-3 pr-4">单据类型</th>
          <th className="py-3 pr-4">单据标题</th>
          <th className="py-3 pr-4">业务公司</th>
          <th className="py-3 pr-4">单据日期</th>
          <th className="py-3 pr-4">风险级别</th>
          <th className="py-3 pr-4">处置情况</th>
          <th className="py-3 pr-4">当前流程</th>
          <th className="py-3 pr-0 text-right">操作</th>
        </tr>
      </thead>
      <tbody>
        {records.map((record, idx) => (
          <tr key={record.job_id} className="border-b border-slate-100 hover:bg-sky-50/40 transition-colors dark:border-slate-800 dark:hover:bg-sky-950/20">
            <td className="py-4 pr-4 text-slate-500 dark:text-slate-400">{idx + 1}</td>
            <td className="py-4 pr-4 whitespace-nowrap">{record.doc_type_label}</td>
            <td className="py-4 pr-4 min-w-[340px]">
              <div className="font-medium text-slate-900 dark:text-slate-100">{record.document_title}</div>
              <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{record.document_number || record.file_name || record.job_id}</div>
            </td>
            <td className="py-4 pr-4">
              <div>{record.company_name || "-"}</div>
              <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{record.counterparty_name || "-"}</div>
            </td>
            <td className="py-4 pr-4 whitespace-nowrap">{formatDate(record.document_date || record.created_at)}</td>
            <td className="py-4 pr-4">
              <span className={cn("inline-flex rounded-full border px-2.5 py-1 text-xs font-medium", riskTone(record.risk_level))}>
                {riskLabel(record.risk_level)}
              </span>
            </td>
            <td className="py-4 pr-4">
              <div className={cn("inline-flex rounded-full border px-2.5 py-1 text-xs font-medium", reviewTone(record.review_status))}>
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
              <span className={cn("inline-flex rounded-full border px-2.5 py-1 text-[11px] font-medium", riskTone(record.risk_level))}>
                {riskLabel(record.risk_level)}
              </span>
            </div>
            <div className="mt-2 flex flex-wrap gap-x-5 gap-y-2 text-xs text-slate-500 dark:text-slate-400">
              <span>签发日期：{formatDate(record.document_date || record.created_at)}</span>
              <span>审单编号：{record.job_id}</span>
              <span>单据类型：{record.doc_type_label}</span>
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
  const [page, setPage] = useState(0);
  const [meta, setMeta] = useState({
    count: 0,
    total_visible: 0,
    offset: 0,
    limit: AUDIT_RECORD_PAGE_SIZE,
    has_more: false,
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
    const effectiveQuery = (deferredQuery || filters.query || "").trim();
    try {
      const res = await adminApi.listAuditRecords({
        limit: AUDIT_RECORD_PAGE_SIZE,
        offset: page * AUDIT_RECORD_PAGE_SIZE,
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
      });
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
    try {
      await adminApi.reviewAudit({
        job_id: activeRecord.job_id,
        status: reviewStatus,
        comment: reviewComment || undefined,
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
  const metrics = {
    total: Number(meta.total_visible || visibleRecords.length),
    high: visibleRecords.filter((item) => item?.risk_level === "high").length,
    pending: visibleRecords.filter((item) => !item?.review_status || item?.review_status === "need_more").length,
    approved: visibleRecords.filter((item) => item?.review_status === "approved").length,
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
            <MetricCard label="当前结果数" value={metrics.total} tone="blue" />
            <MetricCard label="高风险条目" value={metrics.high} tone="red" />
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
                  {view === "warnings" ? `找到相关异常 ${metrics.total} 个` : `找到相关审核报告 ${metrics.total} 份`}
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
                当前显示 {visibleRecords.length} 条，匹配结果 {meta.total_visible || visibleRecords.length} 条
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
            ) : visibleRecords.length === 0 ? (
              <div className="rounded-[28px] border border-dashed border-slate-300 bg-white px-6 py-20 text-center dark:border-slate-700 dark:bg-slate-900">
                <FileSearch className="mx-auto text-slate-300 dark:text-slate-600" size={34} />
                <div className="mt-4 text-lg font-medium text-slate-700 dark:text-slate-200">暂无符合条件的审单记录</div>
                <div className="mt-2 text-sm text-slate-400 dark:text-slate-500">调整筛选条件后重试，或等待新的审单任务进入后台。</div>
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
