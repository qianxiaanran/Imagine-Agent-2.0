import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  Boxes,
  Building2,
  CalendarDays,
  CheckCircle2,
  CircleDollarSign,
  Clock3,
  ClipboardCheck,
  ExternalLink,
  FileBadge2,
  FileSearch,
  FileText,
  Hash,
  ListChecks,
  Loader2,
  Mic,
  Package,
  RefreshCw,
  ReceiptText,
  RotateCcw,
  ScrollText,
  Shield,
  Sparkles,
  Users,
  Workflow,
} from 'lucide-react';

import tasksApi from '../api/tasks';
import AuditSourceFilesPanel from '../components/AuditSourceFilesPanel';
import { getFriendlyRequestError } from '../utils/requestErrors';

const STATUS_TABS = [
  { key: 'all', label: '全部' },
  { key: 'running', label: '运行中' },
  { key: 'completed', label: '已完成' },
  { key: 'failed', label: '失败' },
];

const TYPE_TABS = [
  { key: 'all', label: '全部类型' },
  { key: 'audit', label: '审单' },
  { key: 'ocr', label: 'OCR' },
  { key: 'seal', label: '印章' },
  { key: 'voice', label: '语音' },
  { key: 'ppt', label: 'PPT' },
];

const STATUS_STYLES = {
  queued: 'bg-slate-100 text-slate-700 border border-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:border-slate-700',
  running: 'bg-cyan-100 text-cyan-700 border border-cyan-200 dark:bg-cyan-950/40 dark:text-cyan-200 dark:border-cyan-800',
  completed: 'bg-emerald-100 text-emerald-700 border border-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-200 dark:border-emerald-800',
  failed: 'bg-rose-100 text-rose-700 border border-rose-200 dark:bg-rose-950/30 dark:text-rose-200 dark:border-rose-800',
  cancelled: 'bg-amber-100 text-amber-700 border border-amber-200 dark:bg-amber-950/30 dark:text-amber-200 dark:border-amber-800',
};

const TYPE_ICONS = {
  audit: Shield,
  ocr: FileText,
  seal: FileBadge2,
  voice: Mic,
  ppt: Sparkles,
};

const dateTimeFormatter = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
});

function formatDateTime(value) {
  if (!value) return '-';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value || '-');
  return dateTimeFormatter.format(parsed).replace(/\//g, '-');
}

function getQueryTaskId() {
  const params = new URLSearchParams(window.location.search || '');
  return String(params.get('task') || '').trim();
}

function updateQueryTaskId(taskId) {
  const nextUrl = new URL(window.location.href);
  if (taskId) {
    nextUrl.searchParams.set('task', taskId);
  } else {
    nextUrl.searchParams.delete('task');
  }
  window.history.replaceState({}, '', `${nextUrl.pathname}${nextUrl.search}${nextUrl.hash}`);
}

function TaskSummaryCard({ label, value, tone = 'slate' }) {
  const toneMap = {
    slate: 'from-slate-100 to-white dark:from-slate-900 dark:to-slate-950 border-slate-200 dark:border-slate-800',
    cyan: 'from-cyan-100 to-white dark:from-cyan-950/40 dark:to-slate-950 border-cyan-200 dark:border-cyan-800',
    emerald: 'from-emerald-100 to-white dark:from-emerald-950/30 dark:to-slate-950 border-emerald-200 dark:border-emerald-800',
    rose: 'from-rose-100 to-white dark:from-rose-950/30 dark:to-slate-950 border-rose-200 dark:border-rose-800',
  };
  return (
    <div className={`rounded-2xl border bg-gradient-to-br ${toneMap[tone] || toneMap.slate} px-4 py-4`}>
      <div className="text-xs tracking-[0.22em] uppercase text-slate-500 dark:text-slate-400">{label}</div>
      <div className="mt-3 text-3xl font-semibold text-slate-900 dark:text-white">{value}</div>
    </div>
  );
}

function EmptyState({ title, description, actionLabel, onAction }) {
  return (
    <div className="rounded-3xl border border-dashed border-slate-300 dark:border-slate-700 bg-white/70 dark:bg-slate-900/70 px-6 py-16 text-center">
      <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-300">
        <Clock3 size={24} />
      </div>
      <div className="text-lg font-semibold text-slate-900 dark:text-white">{title}</div>
      <p className="mx-auto mt-3 max-w-xl text-sm text-slate-500 dark:text-slate-400">{description}</p>
      {onAction ? (
        <button
          type="button"
          onClick={onAction}
          className="mt-5 inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-700 dark:bg-blue-600 dark:hover:bg-blue-500"
        >
          <RefreshCw size={16} />
          {actionLabel || '重试'}
        </button>
      ) : null}
    </div>
  );
}

const AUDIT_WORKFLOW_LABELS = {
  queued: '已排队',
  running: '处理中',
  pending: '待处理',
  pending_docs: '待补件',
  ocr: 'OCR 解析中',
  extract: '字段抽取中',
  extracting: '字段抽取中',
  rules: '规则校核中',
  rule_checking: '规则校核中',
  ai: 'AI 复核中',
  ai_review: 'AI 复核中',
  review: '结果汇总中',
  report: '报告输出中',
  aggregating: '报告输出中',
  review_required: '需人工复核',
  ready_for_erp: '可回写 ERP',
  erp_pending_sync: 'ERP 同步中',
  completed: '已完成',
  failed: '失败',
};

const AUDIT_DOC_META = {
  contract: { label: '合同', icon: FileBadge2 },
  invoice: { label: '发票', icon: ReceiptText },
  packing_list: { label: '装箱单', icon: Package },
  bill_of_lading: { label: '提单', icon: ScrollText },
  payment: { label: '付款单', icon: CircleDollarSign },
  expense: { label: '报销单', icon: CircleDollarSign },
};

const AUDIT_FIELD_LABELS = {
  contract_title: '合同标题',
  project_name: '项目名称',
  subject: '主题',
  contract_no: '合同编号',
  invoice_no: '发票编号',
  application_no: '申请编号',
  tax_no: '税号',
  vendor: '供应商',
  payee: '收款方',
  buyer: '买方',
  customer: '客户',
  payer: '付款方',
  drawer: '出票方',
  total_amount: '总金额',
  currency: '币种',
  contract_date: '合同日期',
  invoice_date: '发票日期',
  payment_date: '付款日期',
  expense_date: '报销日期',
  sign_date: '签署日期',
  issue_date: '签发日期',
  bank_name: '开户行',
  bank_account: '银行账号',
  po_no: '采购订单号',
  bl_no: '提单号',
  port_of_loading: '装运港',
  port_of_discharge: '目的港',
  remark: '备注',
};

const AUDIT_FINDING_SOURCE_LABELS = {
  rule: '规则校核',
  cross_doc: '跨单据比对',
  anomaly: '异常识别',
  history: '历史画像',
  ai: 'AI 研判',
  manual: '人工标注',
};

function formatAuditWorkflow(value) {
  const normalized = String(value || '').trim().toLowerCase();
  return AUDIT_WORKFLOW_LABELS[normalized] || String(value || '待处理');
}

function getAuditDocMeta(value) {
  const normalized = String(value || '').trim().toLowerCase();
  return AUDIT_DOC_META[normalized] || { label: normalized || '未知类型', icon: FileSearch };
}

function formatAuditFieldLabel(key) {
  const raw = String(key || '').trim();
  if (!raw) return '-';
  return AUDIT_FIELD_LABELS[raw] || raw.split('_').filter(Boolean).map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(' ');
}

function getAuditFindingSource(value) {
  const normalized = String(value || '').trim().toLowerCase();
  return AUDIT_FINDING_SOURCE_LABELS[normalized] || (normalized || '系统识别');
}

function AuditDetailSection({ icon: Icon = FileText, title, hint, children }) {
  const iconNode = React.createElement(Icon, { size: 18 });
  return (
    <section className="overflow-hidden rounded-3xl border border-slate-200 bg-slate-50/70 dark:border-slate-800 dark:bg-slate-950/40">
      <div className="flex items-start gap-3 border-b border-slate-200/80 bg-white/70 px-4 py-4 dark:border-slate-800 dark:bg-slate-900/80">
        <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-slate-900 text-white dark:bg-slate-800">
          {iconNode}
        </div>
        <div className="min-w-0">
          <div className="text-sm font-semibold text-slate-900 dark:text-white">{title}</div>
          {hint ? <div className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">{hint}</div> : null}
        </div>
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}

function AuditMetricCard({ icon: Icon = Shield, label, value, hint, tone = 'slate' }) {
  const iconNode = React.createElement(Icon, { size: 16 });
  const toneMap = {
    slate: 'from-slate-100 to-white border-slate-200 dark:from-slate-900 dark:to-slate-950 dark:border-slate-800',
    cyan: 'from-cyan-100 to-white border-cyan-200 dark:from-cyan-950/40 dark:to-slate-950 dark:border-cyan-800',
    emerald: 'from-emerald-100 to-white border-emerald-200 dark:from-emerald-950/30 dark:to-slate-950 dark:border-emerald-800',
    rose: 'from-rose-100 to-white border-rose-200 dark:from-rose-950/30 dark:to-slate-950 dark:border-rose-800',
    amber: 'from-amber-100 to-white border-amber-200 dark:from-amber-950/30 dark:to-slate-950 dark:border-amber-800',
  };
  return (
    <div className={`rounded-2xl border bg-gradient-to-br px-4 py-4 ${toneMap[tone] || toneMap.slate}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="text-xs tracking-[0.18em] uppercase text-slate-500 dark:text-slate-400">{label}</div>
        <div className="flex h-9 w-9 items-center justify-center rounded-2xl bg-white/80 text-slate-700 dark:bg-slate-900 dark:text-slate-200">
          {iconNode}
        </div>
      </div>
      <div className="mt-3 text-2xl font-semibold text-slate-900 dark:text-white">{value}</div>
      {hint ? <div className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">{hint}</div> : null}
    </div>
  );
}

function AuditInfoRow({ icon: Icon = FileText, label, value, hint }) {
  const iconNode = React.createElement(Icon, { size: 15 });
  return (
    <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-900/80">
      <div className="flex items-center gap-2 text-slate-500 dark:text-slate-400">
        {iconNode}
        <div className="text-xs tracking-[0.18em] uppercase">{label}</div>
      </div>
      <div className="mt-2 text-sm font-medium break-all text-slate-900 dark:text-white">{value || '-'}</div>
      {hint ? <div className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">{hint}</div> : null}
    </div>
  );
}

function AuditTaskDetail({ task, rawJson, retryingTaskId, onRefresh, onOpenResult, onRetry }) {
  const detail = task?.detail || {};
  const result = detail?.result && typeof detail.result === 'object' ? detail.result : {};
  const findings = Array.isArray(result?.findings) ? result.findings : [];
  const checks = Array.isArray(result?.erp_checks) ? result.erp_checks : [];
  const fields = result?.extracted_fields && typeof result.extracted_fields === 'object' ? result.extracted_fields : {};
  const caseSummary = result?.case_summary && typeof result.case_summary === 'object' ? result.case_summary : {};
  const completeness = caseSummary?.completeness && typeof caseSummary.completeness === 'object' ? caseSummary.completeness : {};
  const caseDocuments = Array.isArray(caseSummary?.documents)
    ? caseSummary.documents
    : Array.isArray(detail?.case_documents)
      ? detail.case_documents
      : [];
  const currentDocMeta = getAuditDocMeta(detail?.doc_type);
  const CurrentDocIcon = currentDocMeta.icon;
  const activeWorkflow = formatAuditWorkflow(detail?.workflow_state || detail?.stage || task?.status);
  const caseId = detail?.case_id || caseSummary?.case_id || task?.summary?.case_id || '';
  const missingDocs = Array.isArray(completeness?.missing) ? completeness.missing : [];
  const requiredDocs = Array.isArray(completeness?.required) ? completeness.required : [];
  const presentDocs = new Set(
    Array.isArray(completeness?.present) && completeness.present.length > 0
      ? completeness.present
      : caseDocuments.map((item) => String(item?.tag || item?.doc_type || '').trim().toLowerCase()).filter(Boolean)
  );
  const caseDocumentCount = Number(completeness?.total_documents || caseDocuments.length || 0);
  const orderedFieldEntries = Object.entries(fields).filter(([, value]) => value !== undefined && value !== null && String(value).trim() !== '');
  const passedChecks = checks.filter((item) => item?.passed === true).length;
  const highRiskCount = findings.filter((item) => String(item?.severity || '').toLowerCase() === 'high').length;

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-lg font-semibold text-slate-900 dark:text-white">{task.title}</div>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
            <span className={`inline-flex items-center rounded-full px-2.5 py-1 font-medium ${STATUS_STYLES[task.status] || STATUS_STYLES.queued}`}>
              {task.status_label}
            </span>
            <span className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-100 px-2.5 py-1 dark:border-slate-700 dark:bg-slate-800">
              <CurrentDocIcon size={13} />
              {currentDocMeta.label}
            </span>
            <span>{activeWorkflow}</span>
            {caseId ? <span>Case {caseId}</span> : null}
          </div>
        </div>
        <button
          type="button"
          onClick={() => void onRefresh(task.task_id)}
          className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-xs font-medium text-slate-600 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          <RefreshCw size={14} />
          刷新详情
        </button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <AuditMetricCard icon={Shield} label="风险命中" value={`${findings.length} 项`} hint={`高风险 ${highRiskCount} 项`} tone="rose" />
        <AuditMetricCard icon={ListChecks} label="规则校验" value={`${passedChecks}/${checks.length || 0}`} hint="结构化规则与 ERP 校验" tone="emerald" />
        <AuditMetricCard icon={Sparkles} label="审单评分" value={result?.audit_score ?? '-'} hint="综合规则、AI 与上下文评分" tone="cyan" />
        <AuditMetricCard icon={Boxes} label="Case 文件" value={caseDocumentCount > 0 ? `${caseDocumentCount} 份` : '-'} hint={caseId ? (missingDocs.length > 0 ? `缺 ${missingDocs.length} 类` : '上下文已齐套') : '尚未关联 Case'} tone={missingDocs.length > 0 ? 'amber' : 'slate'} />
      </div>

      <AuditDetailSection icon={Sparkles} title="AI 摘要与建议" hint="任务中心里直接看结论和建议动作，不再只显示通用键值。">
        <div className="space-y-3">
          <div className="rounded-2xl border border-cyan-200 bg-cyan-50/70 px-4 py-4 text-sm leading-7 text-slate-700 dark:border-cyan-800 dark:bg-cyan-950/20 dark:text-slate-200">
            {result?.summary || '暂无审单摘要'}
          </div>
          <AuditInfoRow icon={AlertCircle} label="当前建议" value={result?.next_action || '暂无建议动作'} />
        </div>
      </AuditDetailSection>

      <AuditDetailSection icon={Building2} title="业务与单据画像" hint="将任务、单据和业务主体信息拆成结构化块。">
        <div className="grid gap-3 sm:grid-cols-2">
          <AuditInfoRow icon={CurrentDocIcon} label="单据类型" value={currentDocMeta.label} hint={result?.recognized_doc_subtype_label || '系统识别结果'} />
          <AuditInfoRow icon={Hash} label="任务 ID" value={task.task_id} />
          <AuditInfoRow icon={CalendarDays} label="开始时间" value={formatDateTime(task.started_at)} />
          <AuditInfoRow icon={Workflow} label="当前流程" value={activeWorkflow} />
          <AuditInfoRow icon={Building2} label="业务主体" value={fields?.vendor || fields?.payee || '-'} />
          <AuditInfoRow icon={Users} label="对手方" value={fields?.buyer || fields?.customer || fields?.payer || '-'} />
          <AuditInfoRow icon={CircleDollarSign} label="单据金额" value={fields?.total_amount ? `${fields.total_amount}${fields?.currency ? ` ${fields.currency}` : ''}` : '-'} />
          <AuditInfoRow icon={FileText} label="文件名" value={detail?.filename || task?.summary?.filename || '-'} />
        </div>
      </AuditDetailSection>

      <AuditDetailSection icon={FileBadge2} title="原始文件" hint="所有审单详情都保留打开原始文件的入口，单文件和整包 Case 都能直接进入源文件。">
        <AuditSourceFilesPanel
          fileUrl={detail?.file_url}
          fileName={detail?.filename || task?.summary?.filename}
          jobId={task?.task_id}
          documents={caseDocuments}
          emptyText="当前任务还没有可打开的原始文件地址。"
          showHeader={false}
        />
      </AuditDetailSection>

      <AuditDetailSection icon={Boxes} title="Case 上下文" hint="在任务中心直接看到齐套状态、待补件和已挂载文件。">
        {caseId || caseDocuments.length > 0 ? (
          <div className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <AuditInfoRow icon={Boxes} label="Case ID" value={caseId || '-'} hint={caseDocumentCount > 0 ? `${caseDocumentCount} 份上下文文件` : '当前没有挂载文件'} />
              <AuditInfoRow icon={FileSearch} label="待补件" value={missingDocs.length > 0 ? missingDocs.map((item) => getAuditDocMeta(item).label).join(' / ') : '无'} />
            </div>
            {requiredDocs.length > 0 ? (
              <div className="grid gap-3 sm:grid-cols-2">
                {requiredDocs.map((item) => {
                  const meta = getAuditDocMeta(item);
                  const MetaIcon = meta.icon;
                  const present = presentDocs.has(item);
                  return (
                    <div key={item} className={`rounded-2xl border px-4 py-3 ${present ? 'border-emerald-200 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/20' : 'border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/20'}`}>
                      <div className="flex items-center gap-3">
                        <div className="flex h-9 w-9 items-center justify-center rounded-2xl bg-white dark:bg-slate-900">
                          <MetaIcon size={16} />
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="text-sm font-medium text-slate-900 dark:text-white">{meta.label}</div>
                          <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{present ? '已挂载到 Case' : '待补件'}</div>
                        </div>
                        <div className={`text-xs font-semibold ${present ? 'text-emerald-700 dark:text-emerald-300' : 'text-amber-700 dark:text-amber-300'}`}>{present ? '已挂载' : '待补'}</div>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : null}
          </div>
        ) : (
          <div className="rounded-2xl border border-dashed border-slate-300 px-4 py-6 text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
            当前任务还没有关联业务 Case。
          </div>
        )}
      </AuditDetailSection>

      <AuditDetailSection icon={Shield} title="风险清单" hint={`共 ${findings.length} 项，展示来源、原因和建议动作。`}>
        {findings.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-300 px-4 py-6 text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">当前没有风险项。</div>
        ) : (
          <div className="space-y-3">
            {findings.map((item, idx) => (
              <div key={`${item?.message || idx}`} className="rounded-2xl border border-slate-200 bg-white px-4 py-4 dark:border-slate-800 dark:bg-slate-900/80">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${
                    String(item?.severity || '').toLowerCase() === 'high'
                      ? 'bg-rose-100 text-rose-700 dark:bg-rose-950/30 dark:text-rose-200'
                      : String(item?.severity || '').toLowerCase() === 'medium'
                        ? 'bg-amber-100 text-amber-700 dark:bg-amber-950/30 dark:text-amber-200'
                        : 'bg-cyan-100 text-cyan-700 dark:bg-cyan-950/30 dark:text-cyan-200'
                  }`}
                  >
                    {String(item?.severity || '').toLowerCase() === 'high' ? '高风险' : String(item?.severity || '').toLowerCase() === 'medium' ? '中风险' : '低风险'}
                  </span>
                  <span className="inline-flex items-center rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300">
                    {getAuditFindingSource(item?.source)}
                  </span>
                </div>
                <div className="mt-3 text-sm font-semibold text-slate-900 dark:text-white">{item?.message || '未命名风险'}</div>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <AuditInfoRow icon={AlertCircle} label="触发原因" value={item?.reason || '-'} />
                  <AuditInfoRow icon={ClipboardCheck} label="建议动作" value={item?.suggestion || item?.action || '-'} />
                </div>
              </div>
            ))}
          </div>
        )}
      </AuditDetailSection>

      <AuditDetailSection icon={FileText} title="结构化字段" hint={`已抽取 ${orderedFieldEntries.length} 个字段。`}>
        {orderedFieldEntries.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-300 px-4 py-6 text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">当前没有可展示的结构化字段。</div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {orderedFieldEntries.map(([key, value]) => (
              <AuditInfoRow key={key} icon={Hash} label={formatAuditFieldLabel(key)} value={Array.isArray(value) ? value.join(' / ') : String(value)} />
            ))}
          </div>
        )}
      </AuditDetailSection>

      <AuditDetailSection icon={ListChecks} title="规则与 ERP 校验" hint={`通过 ${passedChecks} 项，未通过 ${Math.max(checks.length - passedChecks, 0)} 项。`}>
        {checks.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-300 px-4 py-6 text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">当前没有结构化校验项。</div>
        ) : (
          <div className="space-y-3">
            {checks.map((item, idx) => (
              <div key={`${item?.name || idx}`} className="rounded-2xl border border-slate-200 bg-white px-4 py-4 dark:border-slate-800 dark:bg-slate-900/80">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-slate-900 dark:text-white">{item?.name || '未命名检查项'}</div>
                    <div className="mt-2 text-xs leading-6 text-slate-500 dark:text-slate-400">{item?.reason || '-'}</div>
                  </div>
                  <div className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${item?.passed ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-200' : 'bg-rose-100 text-rose-700 dark:bg-rose-950/30 dark:text-rose-200'}`}>
                    {item?.passed ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />}
                    {item?.passed ? '通过' : '未通过'}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </AuditDetailSection>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => onOpenResult(task)}
          className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-700 dark:bg-blue-600 dark:hover:bg-blue-500"
        >
          <ExternalLink size={16} />
          打开结果
        </button>
        {task.retry_supported && task.status === 'failed' ? (
          <button
            type="button"
            disabled={retryingTaskId === task.task_id}
            onClick={() => void onRetry(task)}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            {retryingTaskId === task.task_id ? <Loader2 size={16} className="animate-spin" /> : <RotateCcw size={16} />}
            失败重试
          </button>
        ) : null}
      </div>

      {rawJson ? (
        <div className="rounded-2xl border border-slate-200 bg-slate-950 px-4 py-4 dark:border-slate-800">
          <div className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-200">
            <FileText size={16} />
            原始返回
          </div>
          <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap break-words text-xs leading-6 text-slate-200">
            {rawJson}
          </pre>
        </div>
      ) : null}
    </div>
  );
}

export default function TaskCenterPage() {
  const [statusFilter, setStatusFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all');
  const [tasks, setTasks] = useState([]);
  const [meta, setMeta] = useState({ counts: { all: 0, running: 0, completed: 0, failed: 0 } });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedTaskId, setSelectedTaskId] = useState(() => getQueryTaskId());
  const [selectedTask, setSelectedTask] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');
  const [retryingTaskId, setRetryingTaskId] = useState('');

  const loadTasks = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const response = await tasksApi.listOverview({
        limit: 50,
        offset: 0,
        status: statusFilter === 'all' ? undefined : statusFilter,
        task_type: typeFilter === 'all' ? undefined : typeFilter,
      });
      const nextTasks = Array.isArray(response?.data) ? response.data : [];
      setTasks(nextTasks);
      setMeta(response?.meta || { counts: { all: nextTasks.length } });
      setError('');
    } catch (err) {
      setTasks([]);
      setMeta({ counts: { all: 0, running: 0, completed: 0, failed: 0 } });
      setError(getFriendlyRequestError(err, '任务中心加载失败'));
    } finally {
      setLoading(false);
    }
  }, [statusFilter, typeFilter]);

  const loadTaskDetail = useCallback(async (taskId) => {
    const safeTaskId = String(taskId || '').trim();
    if (!safeTaskId) {
      setSelectedTask(null);
      setDetailError('');
      return;
    }
    setDetailLoading(true);
    setDetailError('');
    try {
      const response = await tasksApi.getTaskDetail(safeTaskId);
      setSelectedTask(response?.data || null);
      setDetailError('');
    } catch (err) {
      setSelectedTask(null);
      setDetailError(getFriendlyRequestError(err, '任务详情加载失败'));
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadTasks();
  }, [loadTasks]);

  useEffect(() => {
    if (!selectedTaskId && tasks.length > 0) {
      const firstId = String(tasks[0]?.task_id || '').trim();
      if (firstId) {
        setSelectedTaskId(firstId);
        updateQueryTaskId(firstId);
      }
    }
  }, [selectedTaskId, tasks]);

  useEffect(() => {
    updateQueryTaskId(selectedTaskId);
    void loadTaskDetail(selectedTaskId);
  }, [selectedTaskId, loadTaskDetail]);

  useEffect(() => {
    const hasRunningTask = tasks.some((task) => ['queued', 'running'].includes(String(task?.status || '').trim()));
    if (!hasRunningTask) return undefined;
    const timer = window.setInterval(() => {
      void loadTasks();
      if (selectedTaskId) {
        void loadTaskDetail(selectedTaskId);
      }
    }, 8000);
    return () => window.clearInterval(timer);
  }, [loadTaskDetail, loadTasks, selectedTaskId, tasks]);

  const statusPills = useMemo(() => STATUS_TABS.map((item) => ({
    ...item,
    count: item.key === 'all' ? meta?.counts?.all || 0 : meta?.counts?.[item.key] || 0,
  })), [meta]);

  const handleSelectTask = useCallback((taskId) => {
    setSelectedTaskId(String(taskId || '').trim());
  }, []);

  const handleRetry = useCallback(async (task) => {
    const taskId = String(task?.task_id || '').trim();
    if (!taskId) return;
    setRetryingTaskId(taskId);
    try {
      const response = await tasksApi.retryTask(taskId);
      const nextTaskId = String(response?.data?.task_id || '').trim();
      await loadTasks();
      if (nextTaskId) {
        setSelectedTaskId(nextTaskId);
      }
    } catch (err) {
      setError(getFriendlyRequestError(err, '任务重试失败'));
    } finally {
      setRetryingTaskId('');
    }
  }, [loadTasks]);

  const handleOpenResult = useCallback((task) => {
    const detailDownloadUrl = task?.detail?.download_url || task?.summary?.download_url;
    if (detailDownloadUrl) {
      window.open(detailDownloadUrl, '_blank', 'noopener,noreferrer');
      return;
    }
    const archiveUrl = task?.detail?.archive_url || task?.summary?.archive_url;
    if (archiveUrl) {
      window.open(archiveUrl, '_blank', 'noopener,noreferrer');
      return;
    }
    const resultLink = String(task?.result_link || '').trim();
    if (!resultLink || resultLink.startsWith('/tasks')) {
      handleSelectTask(task?.task_id);
      return;
    }
    window.open(resultLink, '_blank', 'noopener,noreferrer');
  }, [handleSelectTask]);

  const selectedTaskRawJson = useMemo(() => {
    if (!selectedTask?.raw) return '';
    try {
      return JSON.stringify(selectedTask.raw, null, 2);
    } catch {
      return String(selectedTask.raw || '');
    }
  }, [selectedTask]);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-white" style={{ minHeight: 'var(--app-height, 100vh)' }}>
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/90 backdrop-blur dark:border-slate-800 dark:bg-slate-950/90">
        <div className="mx-auto flex max-w-[1580px] items-center justify-between px-4 py-4 sm:px-6">
            <div>
              <div className="text-xs tracking-[0.28em] uppercase text-slate-500 dark:text-slate-400">Task Center</div>
              <div className="mt-1 text-xl font-semibold">统一任务中心</div>
            <div className="mt-1 text-sm text-slate-500 dark:text-slate-400">聚合审单、OCR、印章提取、语音转写与 PPT 生成任务，统一查看状态、失败原因和结果入口。</div>
            </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void loadTasks()}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              <RefreshCw size={16} />
              刷新
            </button>
            <a
              href="/"
              className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-700 dark:bg-blue-600 dark:hover:bg-blue-500"
            >
              <ArrowLeft size={16} />
              返回工作台
            </a>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1580px] px-4 py-6 sm:px-6">
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <TaskSummaryCard label="全部任务" value={meta?.counts?.all || 0} tone="slate" />
          <TaskSummaryCard label="运行中" value={meta?.counts?.running || 0} tone="cyan" />
          <TaskSummaryCard label="已完成" value={meta?.counts?.completed || 0} tone="emerald" />
          <TaskSummaryCard label="失败任务" value={meta?.counts?.failed || 0} tone="rose" />
        </div>

        <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(360px,0.9fr)]">
          <section className="rounded-3xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <div className="border-b border-slate-100 px-5 py-4 dark:border-slate-800">
              <div className="flex flex-wrap items-center gap-3">
                <div className="flex flex-wrap gap-2">
                  {statusPills.map((item) => (
                    <button
                      key={item.key}
                      type="button"
                      onClick={() => setStatusFilter(item.key)}
                      className={`rounded-full px-3 py-1.5 text-sm transition ${
                        statusFilter === item.key
                          ? 'bg-slate-900 text-white dark:bg-blue-600'
                          : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'
                      }`}
                    >
                      {item.label}
                      <span className="ml-1.5 opacity-75">{item.count}</span>
                    </button>
                  ))}
                </div>
                <div className="ml-auto flex flex-wrap gap-2">
                  {TYPE_TABS.map((item) => (
                    <button
                      key={item.key}
                      type="button"
                      onClick={() => setTypeFilter(item.key)}
                      className={`rounded-full px-3 py-1.5 text-sm transition ${
                        typeFilter === item.key
                          ? 'bg-cyan-600 text-white dark:bg-cyan-500'
                          : 'bg-cyan-50 text-cyan-700 hover:bg-cyan-100 dark:bg-cyan-950/30 dark:text-cyan-200 dark:hover:bg-cyan-900/40'
                      }`}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="p-4">
              {loading ? (
                <div className="flex min-h-[320px] items-center justify-center text-sm text-slate-500 dark:text-slate-400">
                  <Loader2 size={18} className="mr-2 animate-spin" />
                  正在加载任务列表...
                </div>
              ) : error ? (
                <EmptyState
                  title="任务列表加载失败"
                  description={error}
                  actionLabel="重新获取任务"
                  onAction={() => void loadTasks()}
                />
              ) : tasks.length === 0 ? (
                <EmptyState
                  title="暂无匹配任务"
                  description="当前筛选条件下还没有任务记录。后续发起审单、OCR、印章提取、语音转写或 PPT 生成后，这里会自动聚合展示。"
                />
              ) : (
                <div className="space-y-3">
                  {tasks.map((task) => {
                    const Icon = TYPE_ICONS[task.task_type] || FileText;
                    const isActive = selectedTaskId === task.task_id;
                    return (
                      <button
                        key={task.task_id}
                        type="button"
                        onClick={() => handleSelectTask(task.task_id)}
                        className={`w-full rounded-2xl border px-4 py-4 text-left transition ${
                          isActive
                            ? 'border-cyan-300 bg-cyan-50 shadow-sm dark:border-cyan-700 dark:bg-cyan-950/20'
                            : 'border-slate-200 bg-slate-50 hover:border-slate-300 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-950/40 dark:hover:border-slate-700 dark:hover:bg-slate-900'
                        }`}
                      >
                        <div className="flex items-start gap-3">
                          <div className="mt-0.5 flex h-10 w-10 items-center justify-center rounded-2xl bg-slate-900 text-white dark:bg-slate-800">
                            <Icon size={18} />
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <div className="truncate text-base font-semibold text-slate-900 dark:text-white">{task.title}</div>
                              <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${STATUS_STYLES[task.status] || STATUS_STYLES.queued}`}>
                                {task.status_label}
                              </span>
                              <span className="text-xs text-slate-500 dark:text-slate-400">{task.task_type_label}</span>
                            </div>
                            <div className="mt-3 h-2 rounded-full bg-slate-200 dark:bg-slate-800">
                              <div
                                className={`h-full rounded-full transition-all ${
                                  task.status === 'failed'
                                    ? 'bg-rose-500'
                                    : task.status === 'completed'
                                      ? 'bg-emerald-500'
                                      : 'bg-cyan-500'
                                }`}
                                style={{ width: `${Math.max(4, Math.min(100, Number(task.progress) || 0))}%` }}
                              />
                            </div>
                            <div className="mt-3 grid gap-2 text-xs text-slate-500 dark:text-slate-400 sm:grid-cols-3">
                              <div>任务ID：{task.task_id.slice(0, 8)}...</div>
                              <div>开始时间：{formatDateTime(task.started_at)}</div>
                              <div>更新时间：{formatDateTime(task.updated_at)}</div>
                            </div>
                            {task.error_message ? (
                              <div className="mt-3 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:border-rose-800 dark:bg-rose-950/30 dark:text-rose-200">
                                {task.error_message}
                              </div>
                            ) : null}
                            <div className="mt-4 flex flex-wrap gap-2">
                              <button
                                type="button"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  handleOpenResult(task);
                                }}
                                className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
                              >
                                <ExternalLink size={14} />
                                打开结果
                              </button>
                              {task.retry_supported && task.status === 'failed' ? (
                                <button
                                  type="button"
                                  disabled={retryingTaskId === task.task_id}
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    void handleRetry(task);
                                  }}
                                  className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-blue-600 dark:hover:bg-blue-500"
                                >
                                  {retryingTaskId === task.task_id ? <Loader2 size={14} className="animate-spin" /> : <RotateCcw size={14} />}
                                  失败重试
                                </button>
                              ) : null}
                            </div>
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </section>

          <aside className="rounded-3xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <div className="border-b border-slate-100 px-5 py-4 dark:border-slate-800">
              <div className="text-base font-semibold text-slate-900 dark:text-white">任务详情</div>
              <div className="mt-1 text-sm text-slate-500 dark:text-slate-400">查看统一字段、失败原因、结果入口和原始返回内容。</div>
            </div>

            <div className="p-5">
              {detailLoading ? (
                <div className="flex min-h-[320px] items-center justify-center text-sm text-slate-500 dark:text-slate-400">
                  <Loader2 size={18} className="mr-2 animate-spin" />
                  正在加载任务详情...
                </div>
              ) : detailError ? (
                <EmptyState
                  title="任务详情加载失败"
                  description={detailError}
                  actionLabel="重新加载详情"
                  onAction={() => void loadTaskDetail(selectedTaskId)}
                />
              ) : !selectedTask ? (
                <EmptyState
                  title="选择一条任务查看详情"
                  description="左侧任务列表会持续刷新，你可以随时查看失败原因、结果链接和任务原始回包。"
                />
              ) : selectedTask.task_type === 'audit' ? (
                <AuditTaskDetail
                  task={selectedTask}
                  rawJson={selectedTaskRawJson}
                  retryingTaskId={retryingTaskId}
                  onRefresh={loadTaskDetail}
                  onOpenResult={handleOpenResult}
                  onRetry={handleRetry}
                />
              ) : (
                <div className="space-y-5">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-lg font-semibold text-slate-900 dark:text-white">{selectedTask.title}</div>
                      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                        <span className={`inline-flex items-center rounded-full px-2.5 py-1 font-medium ${STATUS_STYLES[selectedTask.status] || STATUS_STYLES.queued}`}>
                          {selectedTask.status_label}
                        </span>
                        <span>{selectedTask.task_type_label}</span>
                        <span>Task ID: {selectedTask.task_id}</span>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => void loadTaskDetail(selectedTask.task_id)}
                      className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-xs font-medium text-slate-600 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
                    >
                      <RefreshCw size={14} />
                      刷新详情
                    </button>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-800 dark:bg-slate-950/40">
                      <div className="text-xs text-slate-500 dark:text-slate-400">开始时间</div>
                      <div className="mt-2 text-sm font-medium text-slate-900 dark:text-white">{formatDateTime(selectedTask.started_at)}</div>
                    </div>
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-800 dark:bg-slate-950/40">
                      <div className="text-xs text-slate-500 dark:text-slate-400">更新时间</div>
                      <div className="mt-2 text-sm font-medium text-slate-900 dark:text-white">{formatDateTime(selectedTask.updated_at)}</div>
                    </div>
                  </div>

                  <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4 dark:border-slate-800 dark:bg-slate-950/40">
                    <div className="flex items-center justify-between">
                      <div className="text-sm font-medium text-slate-700 dark:text-slate-200">统一进度</div>
                      <div className="text-sm text-slate-500 dark:text-slate-400">{selectedTask.progress}%</div>
                    </div>
                    <div className="mt-3 h-2 rounded-full bg-slate-200 dark:bg-slate-800">
                      <div
                        className={`h-full rounded-full transition-all ${
                          selectedTask.status === 'failed'
                            ? 'bg-rose-500'
                            : selectedTask.status === 'completed'
                              ? 'bg-emerald-500'
                              : 'bg-cyan-500'
                        }`}
                        style={{ width: `${Math.max(4, Math.min(100, Number(selectedTask.progress) || 0))}%` }}
                      />
                    </div>
                  </div>

                  {selectedTask.error_message ? (
                    <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-4 dark:border-rose-800 dark:bg-rose-950/30">
                      <div className="flex items-center gap-2 text-sm font-medium text-rose-700 dark:text-rose-200">
                        <AlertTriangle size={16} />
                        失败原因
                      </div>
                      <div className="mt-2 text-sm leading-6 text-rose-700 dark:text-rose-200">{selectedTask.error_message}</div>
                    </div>
                  ) : null}

                  <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4 dark:border-slate-800 dark:bg-slate-950/40">
                    <div className="text-sm font-medium text-slate-700 dark:text-slate-200">任务摘要</div>
                    <div className="mt-3 space-y-2 text-sm text-slate-600 dark:text-slate-300">
                      {Object.entries(selectedTask.detail || {}).map(([key, value]) => {
                        if (value === undefined || value === null || value === '' || typeof value === 'object') {
                          return null;
                        }
                        return (
                          <div key={key} className="flex items-start justify-between gap-4 border-b border-slate-200/70 py-2 last:border-b-0 dark:border-slate-800/80">
                            <div className="min-w-0 text-slate-500 dark:text-slate-400">{key}</div>
                            <div className="min-w-0 flex-1 text-right break-all text-slate-800 dark:text-slate-100">{String(value)}</div>
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => handleOpenResult(selectedTask)}
                      className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-700 dark:bg-blue-600 dark:hover:bg-blue-500"
                    >
                      <ExternalLink size={16} />
                      打开结果
                    </button>
                    {(selectedTask?.detail?.archive_url || selectedTask?.summary?.archive_url) ? (
                      <button
                        type="button"
                        onClick={() => window.open(selectedTask?.detail?.archive_url || selectedTask?.summary?.archive_url, '_blank', 'noopener,noreferrer')}
                        className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
                      >
                        <ExternalLink size={16} />
                        批量下载
                      </button>
                    ) : null}
                    {selectedTask.retry_supported && selectedTask.status === 'failed' ? (
                      <button
                        type="button"
                        disabled={retryingTaskId === selectedTask.task_id}
                        onClick={() => void handleRetry(selectedTask)}
                        className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
                      >
                        {retryingTaskId === selectedTask.task_id ? <Loader2 size={16} className="animate-spin" /> : <RotateCcw size={16} />}
                        失败重试
                      </button>
                    ) : null}
                  </div>

                  {selectedTaskRawJson ? (
                    <div className="rounded-2xl border border-slate-200 bg-slate-950 px-4 py-4 dark:border-slate-800">
                      <div className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-200">
                        <FileText size={16} />
                        原始返回
                      </div>
                      <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap break-words text-xs leading-6 text-slate-200">
                        {selectedTaskRawJson}
                      </pre>
                    </div>
                  ) : (
                    <div className="rounded-2xl border border-dashed border-slate-300 px-4 py-6 text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
                      当前任务暂无原始回包可展示。
                    </div>
                  )}
                </div>
              )}
            </div>
          </aside>
        </div>
      </main>
    </div>
  );
}
