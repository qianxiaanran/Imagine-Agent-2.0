import React from 'react';
import {
  CheckCircle2,
  CircleDashed,
  AlertTriangle,
  Loader2,
  PauseCircle,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react';

const statusMeta = {
  pending: {
    icon: CircleDashed,
    badge: '待执行',
    className: 'bg-gray-50 text-gray-600 border-gray-200',
  },
  running: {
    icon: Loader2,
    badge: '执行中',
    className: 'bg-blue-50 text-blue-600 border-blue-200',
  },
  blocked: {
    icon: PauseCircle,
    badge: '待确认',
    className: 'bg-amber-50 text-amber-700 border-amber-200',
  },
  done: {
    icon: CheckCircle2,
    badge: '已完成',
    className: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  },
  failed: {
    icon: AlertTriangle,
    badge: '失败',
    className: 'bg-red-50 text-red-700 border-red-200',
  },
};

const toDisplayValue = (value) => {
  if (value == null) return '';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
};

const StepCard = ({
  step,
  canConfirm = false,
  canRetry = false,
  actionLoading = false,
  onConfirm,
  onRetry,
}) => {
  const status = String(step?.status || 'pending').toLowerCase();
  const meta = statusMeta[status] || statusMeta.pending;
  const Icon = meta.icon;
  const outputText = toDisplayValue(step?.output_json);
  const errorText = step?.error ? String(step.error) : '';
  const durationLabel =
    Number.isFinite(Number(step?.duration_ms)) && Number(step.duration_ms) > 0
      ? `${(Number(step.duration_ms) / 1000).toFixed(2)}s`
      : '';

  return (
    <div className="rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2">
          <div className={`mt-0.5 p-1.5 rounded-full border ${meta.className}`}>
            <Icon size={14} className={status === 'running' ? 'animate-spin' : ''} />
          </div>
          <div>
            <div className="text-sm font-semibold text-gray-900 dark:text-white">
              {step?.step_order}. {step?.step_name || step?.step_key}
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400">{step?.step_key}</div>
          </div>
        </div>
        <div className={`text-[11px] px-2 py-1 rounded-full border ${meta.className}`}>{meta.badge}</div>
      </div>

      {durationLabel && (
        <div className="text-[11px] text-gray-400 dark:text-gray-500">耗时：{durationLabel}</div>
      )}

      {errorText && (
        <div className="rounded-lg border border-red-200 bg-red-50 text-red-700 text-xs px-3 py-2 whitespace-pre-wrap">
          {errorText}
        </div>
      )}

      {outputText && (
        <pre className="text-xs leading-relaxed text-gray-600 dark:text-gray-300 bg-gray-50 dark:bg-gray-800/70 rounded-xl border border-gray-200 dark:border-gray-700 p-3 max-h-48 overflow-auto custom-scrollbar whitespace-pre-wrap">
          {outputText}
        </pre>
      )}

      {(canConfirm || canRetry) && (
        <div className="flex items-center gap-2 pt-1">
          {canConfirm && (
            <>
              <button
                type="button"
                disabled={actionLoading}
                onClick={() => onConfirm && onConfirm('approved')}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-60"
              >
                <ShieldCheck size={13} />
                人工确认并继续
              </button>
              <button
                type="button"
                disabled={actionLoading}
                onClick={() => onConfirm && onConfirm('rejected')}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border border-red-200 bg-red-50 text-red-700 hover:bg-red-100 disabled:opacity-60"
              >
                驳回
              </button>
            </>
          )}
          {canRetry && (
            <button
              type="button"
              disabled={actionLoading}
              onClick={() => onRetry && onRetry()}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border border-gray-300 text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-800 disabled:opacity-60"
            >
              <RefreshCw size={13} />
              重试工作流
            </button>
          )}
        </div>
      )}
    </div>
  );
};

export default StepCard;

