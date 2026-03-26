import React from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardCheck,
  Database,
  ExternalLink,
  FileText,
  Hash,
  ScrollText,
  ShieldAlert,
  Sparkles,
} from "lucide-react";

const cn = (...parts) => parts.filter(Boolean).join(" ");
const SOURCE_LABELS = {
  rule: "规则命中",
  ai: "AI语义",
  cross_doc: "跨单据核对",
  anomaly: "异常检测",
  history: "历史相似",
  erp: "ERP校验",
};
const escapeRegExp = (v = "") => v.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const parseAuditHistoryText = (text) => {
  const lines = String(text || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  const parsed = {
    title: "历史审单记录",
    risk: "",
    verdict: "",
    score: "",
    summary: "",
    erpTrace: "",
    dataSources: [],
    issues: [],
    extras: [],
    raw: String(text || "").trim(),
  };

  let inIssues = false;
  for (const line of lines) {
    if (/^【智能审单】/.test(line)) {
      parsed.title = line.replace(/^【智能审单】/, "").trim() || parsed.title;
      inIssues = false;
      continue;
    }
    if (/^风险等级[:：]/.test(line)) {
      parsed.risk = line.replace(/^风险等级[:：]\s*/, "").trim();
      inIssues = false;
      continue;
    }
    if (/^结论[:：]/.test(line)) {
      parsed.verdict = line.replace(/^结论[:：]\s*/, "").trim();
      inIssues = false;
      continue;
    }
    if (/^审单评分[:：]/.test(line)) {
      parsed.score = line.replace(/^审单评分[:：]\s*/, "").trim();
      inIssues = false;
      continue;
    }
    if (/^摘要[:：]/.test(line)) {
      parsed.summary = line.replace(/^摘要[:：]\s*/, "").trim();
      inIssues = false;
      continue;
    }
    if (/^ERP Trace[:：]/i.test(line)) {
      parsed.erpTrace = line.replace(/^ERP Trace[:：]\s*/i, "").trim();
      inIssues = false;
      continue;
    }
    if (/^数据来源[:：]/.test(line)) {
      parsed.dataSources = line
        .replace(/^数据来源[:：]\s*/, "")
        .split(/\s*\/\s*/)
        .map((item) => item.trim())
        .filter(Boolean);
      inIssues = false;
      continue;
    }
    if (/^问题[:：]?$/.test(line)) {
      inIssues = true;
      continue;
    }
    if (inIssues) {
      const issueLine = line.replace(/^\d+[.、)]\s*/, "").trim() || line;
      if (issueLine && issueLine !== "未发现明确问题") {
        parsed.issues.push(issueLine);
      }
      continue;
    }
    parsed.extras.push(line);
  }

  if (!parsed.summary && parsed.extras.length > 0) {
    parsed.summary = parsed.extras[0];
  }

  const aggregateMatch = String(parsed.summary || "").match(/本次审单包共\s*(\d+)\s*份文档/);
  if (aggregateMatch) {
    parsed.isAggregate = true;
    parsed.aggregateDocumentCount = Number(aggregateMatch[1]) || 0;
    parsed.displayTitle = `整包汇总${parsed.aggregateDocumentCount > 0 ? ` · ${parsed.aggregateDocumentCount}份单据` : ""}`;
  } else {
    parsed.isAggregate = false;
    parsed.aggregateDocumentCount = 0;
    parsed.displayTitle = parsed.title;
  }

  return parsed;
};

const normalizeDataSourceItems = (historyMeta, parsed) => {
  const metaSources = Array.isArray(historyMeta?.dataSources) ? historyMeta.dataSources : [];
  if (metaSources.length > 0) {
    return metaSources
      .map((item) => {
        if (!item) return null;
        if (typeof item === "string") {
          return { label: item, count: 0 };
        }
        const label = String(item.label || item.name || item.key || "").trim();
        const count = Number(item.count);
        if (!label) return null;
        return {
          label,
          count: Number.isFinite(count) ? Math.max(0, Math.round(count)) : 0,
        };
      })
      .filter(Boolean);
  }

  const parsedSources = Array.isArray(parsed?.dataSources) ? parsed.dataSources : [];
  return parsedSources.map((item) => {
    const match = String(item).match(/^(.*?)(?:\((\d+)\))?$/);
    return {
      label: String(match?.[1] || item).trim(),
      count: Number(match?.[2] || 0) || 0,
    };
  }).filter((item) => item.label);
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

const formatConfidence = (value) => {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "";
  return `${Math.round(Math.max(0, Math.min(1, numeric)) * 100)}%`;
};

const issueLevelLabel = (severity = "") => {
  const normalized = String(severity || "").trim().toLowerCase();
  if (normalized === "high") return "高风险";
  if (normalized === "medium") return "中风险";
  if (normalized === "low") return "低风险";
  return "历史问题";
};

const issueLevelClass = (severity = "") => {
  const normalized = String(severity || "").trim().toLowerCase();
  if (normalized === "high") return "bg-red-50 text-red-700 border-red-200 dark:bg-red-950/30 dark:text-red-300 dark:border-red-900/60";
  if (normalized === "medium") return "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/30 dark:text-amber-300 dark:border-amber-900/60";
  if (normalized === "low") return "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-300 dark:border-emerald-900/60";
  return "bg-slate-50 text-slate-700 border-slate-200 dark:bg-slate-950/30 dark:text-slate-300 dark:border-slate-800";
};

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

const normalizeHistoryIssueItems = (historyMeta, parsed) => {
  const metaIssues = Array.isArray(historyMeta?.issues) ? historyMeta.issues : [];
  const issueSource = metaIssues.length > 0 ? metaIssues : parsed?.issues || [];
  return issueSource
    .map((item, index) => {
      if (!item) return null;
      if (typeof item === "string") {
        const text = String(item).trim();
        if (!text) return null;
        return {
          id: `history-issue-${index}`,
          title: text,
          sourceLabel: "历史摘要",
          severity: "",
          levelLabel: "历史问题",
          reason: "",
          suggestion: "",
          confidenceText: "",
          evidenceText: "",
          highlight: "",
          actual: null,
          expected: null,
          ruleId: "",
          documentName: "",
          hasStructuredDetail: false,
        };
      }
      if (typeof item !== "object") return null;
      const severity = String(item.severity || item.level || "").trim().toLowerCase();
      const source = String(item.source || item.source_key || "").trim().toLowerCase();
      const documentName = String(item.documentName || item.document_name || "").trim();
      const rawTitle = String(item.title || item.message || item.name || "风险项").trim();
      const title = documentName && rawTitle && !rawTitle.startsWith(`${documentName}：`) ? `${documentName}：${rawTitle}` : rawTitle;
      const evidenceRaw = item.evidence;
      const evidenceText = String(
        item.evidenceText
        || item.evidence_text
        || (typeof evidenceRaw === "string" ? evidenceRaw : evidenceRaw?.text)
        || ""
      ).trim();
      const highlight = String(
        item.highlight
        || (typeof evidenceRaw === "object" && evidenceRaw ? evidenceRaw.highlight : "")
        || ""
      ).trim();
      return {
        id: String(item.id || item.ruleId || item.rule_id || `history-issue-${index}`),
        title: title || "风险项",
        sourceLabel: String(item.sourceLabel || item.source_label || SOURCE_LABELS[source] || "风险项").trim(),
        severity,
        levelLabel: issueLevelLabel(severity),
        reason: String(item.reason || "").trim(),
        suggestion: String(item.suggestion || "").trim(),
        confidenceText: formatConfidence(item.confidence),
        evidenceText,
        highlight,
        actual: item.actual ?? null,
        expected: item.expected ?? null,
        ruleId: String(item.ruleId || item.rule_id || "").trim(),
        documentName,
        hasStructuredDetail: Boolean(
          String(item.reason || "").trim()
          || String(item.suggestion || "").trim()
          || evidenceText
          || item.actual !== undefined
          || item.expected !== undefined
          || String(item.ruleId || item.rule_id || "").trim()
        ),
      };
    })
    .filter(Boolean);
};

const toneClass = (risk) => {
  const normalized = String(risk || "").toLowerCase();
  if (normalized.includes("高")) return "bg-red-50 text-red-700 border-red-200 dark:bg-red-950/30 dark:text-red-300 dark:border-red-900/60";
  if (normalized.includes("中")) return "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/30 dark:text-amber-300 dark:border-amber-900/60";
  return "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-300 dark:border-emerald-900/60";
};

const verdictToneClass = (verdict) => {
  const normalized = String(verdict || "").toLowerCase();
  if (normalized.includes("复核") || normalized.includes("补")) return "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/30 dark:text-amber-300 dark:border-amber-900/60";
  if (normalized.includes("驳回") || normalized.includes("拒")) return "bg-red-50 text-red-700 border-red-200 dark:bg-red-950/30 dark:text-red-300 dark:border-red-900/60";
  return "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-300 dark:border-emerald-900/60";
};

const HistoryMetricCard = ({ icon: Icon, label, value, hint, tone = "slate" }) => {
  const iconNode = React.createElement(Icon, { size: 16 });
  const toneMap = {
    slate: "from-slate-100 to-white border-slate-200 dark:from-slate-900 dark:to-slate-950 dark:border-slate-800",
    cyan: "from-cyan-100 to-white border-cyan-200 dark:from-cyan-950/30 dark:to-slate-950 dark:border-cyan-800",
    amber: "from-amber-100 to-white border-amber-200 dark:from-amber-950/30 dark:to-slate-950 dark:border-amber-800",
    rose: "from-rose-100 to-white border-rose-200 dark:from-rose-950/30 dark:to-slate-950 dark:border-rose-800",
    emerald: "from-emerald-100 to-white border-emerald-200 dark:from-emerald-950/30 dark:to-slate-950 dark:border-emerald-800",
  };
  return (
    <div className={`rounded-2xl border bg-gradient-to-br px-4 py-4 ${toneMap[tone] || toneMap.slate}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="text-[11px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">{label}</div>
        <div className="flex h-9 w-9 items-center justify-center rounded-2xl bg-white/80 text-slate-700 dark:bg-slate-900 dark:text-slate-200">
          {iconNode}
        </div>
      </div>
      <div className="mt-3 text-lg font-semibold text-slate-900 dark:text-slate-100 break-all">{value || "-"}</div>
      {hint ? <div className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">{hint}</div> : null}
    </div>
  );
};

const formatHistoryTimestamp = (value) => {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (num) => String(num).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
};

const normalizeHistoryEntries = (historyText, historyMeta, historyEntries) => {
  if (Array.isArray(historyEntries) && historyEntries.length > 0) {
    return historyEntries
      .filter((entry) => String(entry?.content || "").trim())
      .map((entry, index) => ({
        id: String(entry?.id || `audit-entry-${index}`),
        content: String(entry?.content || "").trim(),
        historyMeta: entry?.historyMeta || null,
        createdAt: entry?.createdAt || "",
      }));
  }

  const fallbackText = String(historyText || "").trim();
  if (!fallbackText) return [];
  return [
    {
      id: "audit-entry-latest",
      content: fallbackText,
      historyMeta: historyMeta || null,
      createdAt: "",
    },
  ];
};

const AuditHistoryCard = ({ historyText, historyMeta, compact = false, badge = "", timestamp = "" }) => {
  const parsed = parseAuditHistoryText(historyText);
  const issueItems = React.useMemo(() => normalizeHistoryIssueItems(historyMeta, parsed), [historyMeta, parsed]);
  const issueCount = issueItems.length;
  const historyDocuments = Array.isArray(historyMeta?.documents) ? historyMeta.documents.filter(Boolean) : [];
  const showDocumentList = historyDocuments.length > 1 || (parsed.isAggregate && historyDocuments.length > 0);
  const dataSources = normalizeDataSourceItems(historyMeta, parsed);
  const [activeIssueId, setActiveIssueId] = React.useState(issueItems[0]?.id || null);

  React.useEffect(() => {
    if (!issueItems.length) {
      setActiveIssueId(null);
      return;
    }
    if (!issueItems.some((item) => item.id === activeIssueId)) {
      setActiveIssueId(issueItems[0]?.id || null);
    }
  }, [issueItems, activeIssueId]);

  const activeIssue = issueItems.find((item) => item.id === activeIssueId) || issueItems[0] || null;

  return (
    <section className="rounded-[28px] border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden shadow-[0_20px_50px_-24px_rgba(15,23,42,0.35)]">
      <div className="px-4 md:px-5 py-4 border-b border-slate-200 dark:border-slate-800 bg-gradient-to-r from-slate-50 via-white to-cyan-50 dark:from-slate-950 dark:via-slate-900 dark:to-slate-900">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2 text-[11px] font-semibold tracking-[0.18em] uppercase text-slate-500 dark:text-slate-400">
              <span className="inline-flex items-center gap-2">
                <ScrollText size={13} />
                Audit History
              </span>
              {badge ? <span className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[10px] tracking-[0.14em] text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300">{badge}</span> : null}
              {timestamp ? <span className="text-[10px] tracking-[0.14em] text-slate-400 dark:text-slate-500">{timestamp}</span> : null}
            </div>
            <div className="mt-2 text-xl font-semibold text-slate-900 dark:text-slate-100 break-all">{parsed.displayTitle}</div>
            <div className="mt-2 flex flex-wrap gap-2">
              {parsed.risk ? <span className={cn("inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium", toneClass(parsed.risk))}>{parsed.risk}</span> : null}
              {parsed.verdict ? <span className={cn("inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium", verdictToneClass(parsed.verdict))}>{parsed.verdict}</span> : null}
              {parsed.erpTrace ? <span className="inline-flex items-center rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-600 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300">ERP Trace: {parsed.erpTrace}</span> : null}
            </div>
          </div>
          <div className={cn("grid gap-3", compact ? "grid-cols-2" : "grid-cols-2 lg:grid-cols-4")}>
            <HistoryMetricCard icon={ShieldAlert} label="风险等级" value={parsed.risk || "-"} tone={String(parsed.risk).includes("高") ? "rose" : String(parsed.risk).includes("中") ? "amber" : "emerald"} />
            <HistoryMetricCard icon={ClipboardCheck} label="结论" value={parsed.verdict || "-"} tone={String(parsed.verdict).includes("复核") ? "amber" : "emerald"} />
            <HistoryMetricCard icon={Hash} label="审单评分" value={parsed.score || "-"} tone="cyan" />
            <HistoryMetricCard icon={AlertTriangle} label="问题数量" value={`${issueCount} 项`} tone={issueCount > 0 ? "rose" : "emerald"} />
          </div>
        </div>
      </div>

      <div className="p-4 md:p-5 space-y-4">
        {parsed.summary ? (
          <div className="rounded-2xl border border-cyan-200 dark:border-cyan-900/60 bg-cyan-50/80 dark:bg-cyan-950/20 p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-slate-100">
              <Sparkles size={16} className="text-cyan-600 dark:text-cyan-300" />
              审单摘要
            </div>
            <div className="mt-2 text-sm leading-7 text-slate-700 dark:text-slate-200">{parsed.summary}</div>
          </div>
        ) : null}

        <div className={cn("grid gap-4", compact ? "grid-cols-1" : "grid-cols-1 xl:grid-cols-[minmax(0,1.15fr)_minmax(280px,0.85fr)]")}>
          <div className="rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/60">
              <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">问题清单</div>
              <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">历史记录中的重点问题会拆成独立条目，便于逐条查看。</div>
            </div>
            <div className="p-4 space-y-3">
              {issueItems.length > 0 ? issueItems.map((issue, idx) => {
                const isActive = issue.id === activeIssue?.id;
                return (
                  <button
                    key={`${issue.id}-${idx}`}
                    type="button"
                    onClick={() => setActiveIssueId(issue.id)}
                    className={cn(
                      "w-full rounded-2xl border px-4 py-3 text-left transition",
                      isActive
                        ? "border-cyan-300 bg-cyan-50 shadow-sm dark:border-cyan-800 dark:bg-cyan-950/20"
                        : "border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 hover:border-slate-300 dark:hover:border-slate-700"
                    )}
                  >
                    <div className="flex items-start gap-3">
                      <div className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-2xl bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300">
                        <AlertTriangle size={15} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <div className="text-sm font-medium text-slate-900 dark:text-slate-100">问题 {idx + 1}</div>
                          {issue.severity ? (
                            <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium", issueLevelClass(issue.severity))}>
                              {issue.levelLabel}
                            </span>
                          ) : null}
                          {issue.sourceLabel ? (
                            <span className="inline-flex items-center rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[11px] font-medium text-slate-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300">
                              {issue.sourceLabel}
                            </span>
                          ) : null}
                        </div>
                        <div className="mt-1 text-sm leading-6 text-slate-600 dark:text-slate-300">{issue.title}</div>
                      </div>
                    </div>
                  </button>
                );
              }) : (
                <div className="rounded-2xl border border-emerald-200 dark:border-emerald-900/60 bg-emerald-50 dark:bg-emerald-950/20 px-4 py-4 text-sm text-emerald-700 dark:text-emerald-300">
                  <div className="flex items-center gap-2 font-medium">
                    <CheckCircle2 size={16} />
                    历史摘要里没有记录明确风险项
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="space-y-4">
            {activeIssue ? (
              <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/60 p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <div className={cn("inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium", issueLevelClass(activeIssue.severity))}>
                    {activeIssue.levelLabel}
                  </div>
                  {activeIssue.sourceLabel ? (
                    <div className="inline-flex items-center rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300">
                      {activeIssue.sourceLabel}
                    </div>
                  ) : null}
                  {activeIssue.confidenceText ? (
                    <div className="text-[11px] text-slate-400 dark:text-slate-500">置信度：{activeIssue.confidenceText}</div>
                  ) : null}
                </div>
                <div className="mt-3 text-base font-semibold text-slate-900 dark:text-slate-100 break-all">{activeIssue.title}</div>
                {activeIssue.reason ? (
                  <div className="mt-3 text-sm leading-6 text-slate-700 dark:text-slate-200">
                    <span className="font-medium">触发原因：</span>{activeIssue.reason}
                  </div>
                ) : null}
                {activeIssue.suggestion ? (
                  <div className="mt-2 text-sm leading-6 text-slate-700 dark:text-slate-200">
                    <span className="font-medium">建议动作：</span>{activeIssue.suggestion}
                  </div>
                ) : null}
                {(activeIssue.actual !== null && activeIssue.actual !== undefined) || (activeIssue.expected !== null && activeIssue.expected !== undefined) ? (
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-3">
                      <div className="text-[11px] uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">现值</div>
                      <div className="mt-2 text-sm text-slate-700 dark:text-slate-200 break-all">{formatValue(activeIssue.actual)}</div>
                    </div>
                    <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-3">
                      <div className="text-[11px] uppercase tracking-[0.16em] text-slate-400 dark:text-slate-500">期望</div>
                      <div className="mt-2 text-sm text-slate-700 dark:text-slate-200 break-all">{formatValue(activeIssue.expected)}</div>
                    </div>
                  </div>
                ) : null}
                {activeIssue.evidenceText ? (
                  <div className="mt-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-3 text-sm leading-6 text-slate-600 dark:text-slate-300 max-h-[240px] overflow-y-auto">
                    <HighlightedText text={activeIssue.evidenceText} highlight={activeIssue.highlight} />
                  </div>
                ) : null}
                {!activeIssue.hasStructuredDetail ? (
                  <div className="mt-3 text-xs leading-5 text-slate-500 dark:text-slate-400">
                    这条历史记录只保留了问题摘要，未保存更多结构化细节。
                  </div>
                ) : null}
                {(activeIssue.documentName || activeIssue.ruleId) ? (
                  <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-slate-500 dark:text-slate-400">
                    {activeIssue.documentName ? <span>关联文件：{activeIssue.documentName}</span> : null}
                    {activeIssue.ruleId ? <span>规则ID：{activeIssue.ruleId}</span> : null}
                  </div>
                ) : null}
              </div>
            ) : null}

            {dataSources.length > 0 ? (
              <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/60 p-4">
                <div className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-slate-100">
                  <Database size={16} />
                  数据来源
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {dataSources.map((item, idx) => (
                    <span
                      key={`${item.label}-${idx}`}
                      className="inline-flex items-center rounded-full border border-cyan-200 bg-cyan-50 px-3 py-1 text-xs font-medium text-cyan-700 dark:border-cyan-900/60 dark:bg-cyan-950/20 dark:text-cyan-300"
                    >
                      {item.label}
                      {item.count > 0 ? ` · ${item.count}` : ""}
                    </span>
                  ))}
                </div>
                <div className="mt-2 text-xs leading-5 text-slate-500 dark:text-slate-400">
                  这里展示这条审单结论主要来自哪些校验通道，例如规则、跨单据、ERP 或 AI 语义判断。
                </div>
              </div>
            ) : null}

            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/60 p-4">
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-slate-100">
                <FileText size={16} />
                历史说明
              </div>
              <div className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
                这是从历史会话里恢复出的审单结果。旧记录即使没有完整结构化 JSON，也会按标题、风险、结论、评分、摘要和问题列表重新整理显示。
              </div>
            </div>

            {showDocumentList ? (
              <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/60 p-4">
                <div className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-slate-100">
                  <FileText size={16} />
                  关联单据
                </div>
                <div className="mt-2 space-y-2">
                  {historyDocuments.map((doc, idx) => (
                    <div key={`${doc.fileName || 'doc'}-${doc.jobId || idx}`} className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3.5 py-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="text-sm font-medium text-slate-900 dark:text-slate-100 break-all">{doc.fileName || `单据 ${idx + 1}`}</div>
                          <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-slate-500 dark:text-slate-400">
                            {doc.docType ? <span>{doc.docType}</span> : null}
                            {doc.status ? <span>{doc.status}</span> : null}
                          </div>
                        </div>
                        {doc.sourceUrl ? (
                          <a
                            href={doc.sourceUrl}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-cyan-200 bg-cyan-50 px-2.5 py-1.5 text-xs font-medium text-cyan-700 transition hover:bg-cyan-100 dark:border-cyan-900/60 dark:bg-cyan-950/20 dark:text-cyan-300 dark:hover:bg-cyan-950/40"
                          >
                            <ExternalLink size={12} />
                            打开
                          </a>
                        ) : null}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : historyMeta?.sourceUrl || historyMeta?.fileName ? (
              <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/60 p-4">
                <div className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-slate-100">
                  <FileText size={16} />
                  原始单据
                </div>
                <div className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300 break-all">
                  {historyMeta?.fileName || "已关联原始单据"}
                </div>
                {historyMeta?.sourceUrl ? (
                  <a
                    href={historyMeta.sourceUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-3 inline-flex items-center gap-2 rounded-xl border border-cyan-200 bg-cyan-50 px-3.5 py-2 text-sm font-medium text-cyan-700 transition hover:bg-cyan-100 dark:border-cyan-900/60 dark:bg-cyan-950/20 dark:text-cyan-300 dark:hover:bg-cyan-950/40"
                  >
                    <ExternalLink size={14} />
                    打开原始单据
                  </a>
                ) : (
                  <div className="mt-2 text-xs leading-5 text-slate-500 dark:text-slate-400">
                    当前历史记录只保留了文件名，没有可直接打开的文件地址。
                  </div>
                )}
              </div>
            ) : null}

            {parsed.extras.length > 0 ? (
              <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/60 p-4">
                <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">补充信息</div>
                <div className="mt-2 space-y-2">
                  {parsed.extras.map((line, idx) => (
                    <div key={`${line}-${idx}`} className="text-sm leading-6 text-slate-600 dark:text-slate-300">{line}</div>
                  ))}
                </div>
              </div>
            ) : null}

            <details className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-950 overflow-hidden">
              <summary className="cursor-pointer px-4 py-3 text-sm font-medium text-slate-100 select-none">查看原始历史文本</summary>
              <div className="border-t border-slate-800 px-4 py-4">
                <pre className="whitespace-pre-wrap break-words text-xs leading-6 text-slate-200">{parsed.raw || "暂无原始文本"}</pre>
              </div>
            </details>
          </div>
        </div>
      </div>
    </section>
  );
};

export default function AuditHistoryPreview({ historyText, historyMeta = null, historyEntries = [], compact = false }) {
  const entries = normalizeHistoryEntries(historyText, historyMeta, historyEntries);
  const [activeEntryId, setActiveEntryId] = React.useState(entries[entries.length - 1]?.id || null);
  const aggregateCount = entries.filter((entry) => parseAuditHistoryText(entry.content).isAggregate).length;

  React.useEffect(() => {
    if (!entries.length) {
      setActiveEntryId(null);
      return;
    }
    if (!entries.some((entry) => entry.id === activeEntryId)) {
      setActiveEntryId(entries[entries.length - 1]?.id || null);
    }
  }, [entries, activeEntryId]);

  if (!entries.length) return null;

  const activeEntry = entries.find((entry) => entry.id === activeEntryId) || entries[entries.length - 1];
  if (entries.length === 1) {
    return (
      <AuditHistoryCard
        historyText={activeEntry.content}
        historyMeta={activeEntry.historyMeta || historyMeta}
        compact={compact}
      />
    );
  }

  return (
    <section className="space-y-4">
      <div className="rounded-[28px] border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 overflow-hidden shadow-[0_20px_50px_-24px_rgba(15,23,42,0.35)]">
        <div className="px-4 md:px-5 py-4 border-b border-slate-200 dark:border-slate-800 bg-gradient-to-r from-slate-50 via-white to-cyan-50 dark:from-slate-950 dark:via-slate-900 dark:to-slate-900">
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2 text-[11px] font-semibold tracking-[0.18em] uppercase text-slate-500 dark:text-slate-400">
              <ScrollText size={13} />
              Audit History
            </div>
            <div className="text-lg font-semibold text-slate-900 dark:text-slate-100">本会话共保存 {entries.length} 条审单记录</div>
            <div className="text-sm text-slate-500 dark:text-slate-400">
              默认展示最新一次，点击下方条目可以切换查看其他审核文件。{aggregateCount > 0 ? `其中包含 ${aggregateCount} 条整包汇总。` : ""}
            </div>
          </div>
        </div>
        <div className="p-4 md:p-5">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {entries.map((entry, index) => {
              const parsed = parseAuditHistoryText(entry.content);
              const entrySources = normalizeDataSourceItems(entry.historyMeta, parsed);
              const isActive = entry.id === activeEntry.id;
              const timestamp = formatHistoryTimestamp(entry.createdAt);
              return (
                <button
                  key={entry.id}
                  type="button"
                  onClick={() => setActiveEntryId(entry.id)}
                  className={cn(
                    "rounded-2xl border px-4 py-3 text-left transition",
                    isActive
                      ? "border-cyan-300 bg-cyan-50 shadow-sm dark:border-cyan-800 dark:bg-cyan-950/20"
                      : "border-slate-200 bg-white hover:border-slate-300 dark:border-slate-800 dark:bg-slate-950 dark:hover:border-slate-700"
                  )}
                >
                  <div className="text-[11px] uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
                    记录 {index + 1}{timestamp ? ` · ${timestamp}` : ""}
                  </div>
                  <div className="mt-2 text-sm font-semibold text-slate-900 dark:text-slate-100 break-all">{parsed.displayTitle}</div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {parsed.risk ? <span className={cn("inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium", toneClass(parsed.risk))}>{parsed.risk}</span> : null}
                    {parsed.verdict ? <span className={cn("inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium", verdictToneClass(parsed.verdict))}>{parsed.verdict}</span> : null}
                  </div>
                  {entrySources.length > 0 ? (
                    <div className="mt-2 text-xs leading-5 text-slate-500 dark:text-slate-400">
                      来源：{entrySources.slice(0, 3).map((item) => item.count > 0 ? `${item.label}(${item.count})` : item.label).join(" / ")}
                    </div>
                  ) : null}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <AuditHistoryCard
        historyText={activeEntry.content}
        historyMeta={activeEntry.historyMeta || historyMeta}
        compact={compact}
        badge={`记录 ${entries.findIndex((entry) => entry.id === activeEntry.id) + 1}/${entries.length}`}
        timestamp={formatHistoryTimestamp(activeEntry.createdAt)}
      />
    </section>
  );
}
