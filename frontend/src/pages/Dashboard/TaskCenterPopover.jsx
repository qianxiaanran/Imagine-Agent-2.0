import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Clock3,
  ExternalLink,
  FileBadge2,
  FileText,
  Loader2,
  Mic,
  RefreshCw,
  RotateCcw,
  Shield,
  Sparkles,
  X,
} from 'lucide-react';

import tasksApi from '../../api/tasks';
import { getFriendlyRequestError } from '../../utils/requestErrors';

const STATUS_TABS = [
  { key: 'all', label: '全部' },
  { key: 'running', label: '运行中' },
  { key: 'completed', label: '已完成' },
  { key: 'failed', label: '失败' },
];

const TYPE_OPTIONS = [
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

function buildProgressBarClass(status) {
  if (status === 'failed') return 'bg-rose-500';
  if (status === 'completed') return 'bg-emerald-500';
  return 'bg-cyan-500';
}

function SummaryStat({ label, value, tone = 'slate' }) {
  const toneMap = {
    slate: 'border-slate-200 bg-slate-50/90 dark:border-slate-800 dark:bg-slate-900/70',
    cyan: 'border-cyan-200 bg-cyan-50/80 dark:border-cyan-800 dark:bg-cyan-950/20',
    emerald: 'border-emerald-200 bg-emerald-50/80 dark:border-emerald-800 dark:bg-emerald-950/20',
    rose: 'border-rose-200 bg-rose-50/80 dark:border-rose-800 dark:bg-rose-950/20',
  };
  return (
    <div className={`rounded-2xl border px-3 py-3 ${toneMap[tone] || toneMap.slate}`}>
      <div className="text-[11px] tracking-[0.18em] uppercase text-slate-500 dark:text-slate-400">{label}</div>
      <div className="mt-2 text-xl font-semibold text-slate-900 dark:text-white">{value}</div>
    </div>
  );
}

function InlineEmptyState({ title, description, onRetry, retryLabel = '重试' }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50/80 px-4 py-10 text-center dark:border-slate-700 dark:bg-slate-900/50">
      <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-2xl bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-300">
        <Clock3 size={18} />
      </div>
      <div className="text-sm font-semibold text-slate-900 dark:text-white">{title}</div>
      <div className="mx-auto mt-2 max-w-sm text-xs leading-6 text-slate-500 dark:text-slate-400">{description}</div>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-4 inline-flex items-center gap-2 rounded-xl bg-slate-900 px-3 py-2 text-xs font-medium text-white transition hover:bg-slate-700 dark:bg-blue-600 dark:hover:bg-blue-500"
        >
          <RefreshCw size={14} />
          {retryLabel}
        </button>
      ) : null}
    </div>
  );
}

export default function TaskCenterPopover({ isOpen, onClose }) {
  const [statusFilter, setStatusFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all');
  const [tasks, setTasks] = useState([]);
  const [meta, setMeta] = useState({ counts: { all: 0, running: 0, completed: 0, failed: 0 } });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [selectedTaskId, setSelectedTaskId] = useState('');
  const [selectedTask, setSelectedTask] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');
  const [retryingTaskId, setRetryingTaskId] = useState('');

  const loadTasks = useCallback(async () => {
    if (!isOpen) return;
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
      setMeta(response?.meta || { counts: { all: nextTasks.length, running: 0, completed: 0, failed: 0 } });
      if (!nextTasks.some((task) => String(task?.task_id || '') === selectedTaskId)) {
        setSelectedTaskId(String(nextTasks[0]?.task_id || '').trim());
      }
      setError('');
    } catch (err) {
      setTasks([]);
      setMeta({ counts: { all: 0, running: 0, completed: 0, failed: 0 } });
      setError(getFriendlyRequestError(err, '任务加载失败'));
    } finally {
      setLoading(false);
    }
  }, [isOpen, selectedTaskId, statusFilter, typeFilter]);

  const loadTaskDetail = useCallback(async (taskId) => {
    const safeTaskId = String(taskId || '').trim();
    if (!isOpen || !safeTaskId) {
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
  }, [isOpen]);

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
      setSelectedTaskId(String(task?.task_id || '').trim());
      return;
    }
    window.open(resultLink, '_blank', 'noopener,noreferrer');
  }, []);

  const selectedTaskRawJson = useMemo(() => {
    if (!selectedTask?.raw) return '';
    try {
      return JSON.stringify(selectedTask.raw, null, 2);
    } catch {
      return String(selectedTask.raw || '');
    }
  }, [selectedTask]);

  useEffect(() => {
    if (!isOpen) return undefined;
    void loadTasks();
    return undefined;
  }, [isOpen, loadTasks]);

  useEffect(() => {
    if (!isOpen) return undefined;
    void loadTaskDetail(selectedTaskId);
    return undefined;
  }, [isOpen, selectedTaskId, loadTaskDetail]);

  useEffect(() => {
    if (!isOpen) return undefined;
    const hasRunningTask = tasks.some((task) => ['queued', 'running'].includes(String(task?.status || '').trim()));
    if (!hasRunningTask) return undefined;
    const timer = window.setInterval(() => {
      void loadTasks();
      if (selectedTaskId) {
        void loadTaskDetail(selectedTaskId);
      }
    }, 8000);
    return () => window.clearInterval(timer);
  }, [isOpen, loadTaskDetail, loadTasks, selectedTaskId, tasks]);

  useEffect(() => {
    if (!isOpen) return undefined;
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        onClose?.();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50" aria-modal="true" role="dialog">
      <button
        type="button"
        aria-label="关闭任务中心"
        onClick={onClose}
        className="absolute inset-0 bg-slate-950/10 backdrop-blur-[1px] dark:bg-black/30"
      />
      <div className="pointer-events-none absolute inset-x-3 top-16 bottom-3 md:inset-x-auto md:top-20 md:right-6 md:bottom-6 md:w-[min(92vw,520px)]">
        <section
          className="pointer-events-auto flex h-full flex-col overflow-hidden rounded-[28px] border border-slate-200 bg-white/96 shadow-2xl shadow-slate-900/15 dark:border-slate-700 dark:bg-slate-950/96 dark:shadow-black/40"
          onClick={(event) => event.stopPropagation()}
        >
          <div className="border-b border-slate-100 px-4 py-4 dark:border-slate-800">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-[11px] tracking-[0.26em] uppercase text-slate-500 dark:text-slate-400">Task Center</div>
                <div className="mt-1 text-lg font-semibold text-slate-900 dark:text-white">统一任务中心</div>
                <div className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">查看最近 50 条审单、OCR、印章提取、语音与 PPT 任务。</div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => void loadTasks()}
                  className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200 text-slate-500 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
                >
                  <RefreshCw size={16} />
                </button>
                <button
                  type="button"
                  onClick={onClose}
                  className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200 text-slate-500 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
                >
                  <X size={16} />
                </button>
              </div>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3">
              <SummaryStat label="全部" value={meta?.counts?.all || 0} tone="slate" />
              <SummaryStat label="运行中" value={meta?.counts?.running || 0} tone="cyan" />
              <SummaryStat label="已完成" value={meta?.counts?.completed || 0} tone="emerald" />
              <SummaryStat label="失败" value={meta?.counts?.failed || 0} tone="rose" />
            </div>
          </div>

          <div className="border-b border-slate-100 px-4 py-3 dark:border-slate-800">
            <div className="flex flex-wrap gap-2">
              {STATUS_TABS.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => setStatusFilter(item.key)}
                  className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
                    statusFilter === item.key
                      ? 'bg-slate-900 text-white dark:bg-blue-600'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'
                  }`}
                >
                  {item.label}
                </button>
              ))}
              <select
                value={typeFilter}
                onChange={(event) => setTypeFilter(event.target.value)}
                className="ml-auto rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 outline-none transition focus:border-cyan-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
              >
                {TYPE_OPTIONS.map((item) => (
                  <option key={item.key} value={item.key}>{item.label}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid min-h-0 flex-1 gap-0 md:grid-rows-[minmax(0,1.02fr)_minmax(0,1fr)]">
            <div className="min-h-0 border-b border-slate-100 px-4 py-4 dark:border-slate-800">
              {loading ? (
                <div className="flex h-full min-h-[180px] items-center justify-center text-sm text-slate-500 dark:text-slate-400">
                  <Loader2 size={16} className="mr-2 animate-spin" />
                  正在加载任务列表...
                </div>
              ) : error ? (
                <InlineEmptyState title="任务列表加载失败" description={error} onRetry={() => void loadTasks()} retryLabel="重新加载" />
              ) : tasks.length === 0 ? (
                <InlineEmptyState title="暂无任务" description="后续发起审单、OCR、印章提取、语音转写或 PPT 生成后，这里会自动聚合展示。" />
              ) : (
                <div className="h-full space-y-3 overflow-y-auto pr-1">
                  {tasks.map((task) => {
                    const Icon = TYPE_ICONS[task.task_type] || FileText;
                    const isActive = selectedTaskId === task.task_id;
                    return (
                      <button
                        key={task.task_id}
                        type="button"
                        onClick={() => setSelectedTaskId(String(task.task_id || '').trim())}
                        className={`w-full rounded-2xl border px-3 py-3 text-left transition ${
                          isActive
                            ? 'border-cyan-300 bg-cyan-50 shadow-sm dark:border-cyan-700 dark:bg-cyan-950/20'
                            : 'border-slate-200 bg-slate-50/90 hover:border-slate-300 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-950/40 dark:hover:border-slate-700 dark:hover:bg-slate-900'
                        }`}
                      >
                        <div className="flex items-start gap-3">
                          <div className="mt-0.5 flex h-10 w-10 items-center justify-center rounded-2xl bg-slate-900 text-white dark:bg-slate-800">
                            <Icon size={17} />
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <div className="truncate text-sm font-semibold text-slate-900 dark:text-white">{task.title}</div>
                              <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${STATUS_STYLES[task.status] || STATUS_STYLES.queued}`}>
                                {task.status_label}
                              </span>
                            </div>
                            <div className="mt-2 h-1.5 rounded-full bg-slate-200 dark:bg-slate-800">
                              <div
                                className={`h-full rounded-full transition-all ${buildProgressBarClass(task.status)}`}
                                style={{ width: `${Math.max(4, Math.min(100, Number(task.progress) || 0))}%` }}
                              />
                            </div>
                            <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-slate-500 dark:text-slate-400">
                              <span>{task.task_type_label}</span>
                              <span>{formatDateTime(task.updated_at)}</span>
                              <span>{task.task_id.slice(0, 8)}...</span>
                            </div>
                            {task.error_message ? (
                              <div className="mt-2 line-clamp-2 rounded-xl border border-rose-200 bg-rose-50 px-2.5 py-2 text-[11px] leading-5 text-rose-700 dark:border-rose-800 dark:bg-rose-950/30 dark:text-rose-200">
                                {task.error_message}
                              </div>
                            ) : null}
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="min-h-0 px-4 py-4">
              {detailLoading ? (
                <div className="flex h-full min-h-[180px] items-center justify-center text-sm text-slate-500 dark:text-slate-400">
                  <Loader2 size={16} className="mr-2 animate-spin" />
                  正在加载任务详情...
                </div>
              ) : detailError ? (
                <InlineEmptyState title="任务详情加载失败" description={detailError} onRetry={() => void loadTaskDetail(selectedTaskId)} retryLabel="刷新详情" />
              ) : !selectedTask ? (
                <InlineEmptyState title="选择一条任务" description="上方任务列表会持续刷新，你可以查看失败原因、结果入口和原始回包。" />
              ) : (
                <div className="flex h-full flex-col">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-semibold text-slate-900 dark:text-white">{selectedTask.title}</div>
                      <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-500 dark:text-slate-400">
                        <span className={`inline-flex items-center rounded-full px-2 py-0.5 font-medium ${STATUS_STYLES[selectedTask.status] || STATUS_STYLES.queued}`}>
                          {selectedTask.status_label}
                        </span>
                        <span>{selectedTask.task_type_label}</span>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => void loadTaskDetail(selectedTask.task_id)}
                      className="inline-flex h-8 w-8 items-center justify-center rounded-xl border border-slate-200 text-slate-500 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
                    >
                      <RefreshCw size={14} />
                    </button>
                  </div>

                  <div className="mt-4 flex-1 space-y-3 overflow-y-auto pr-1">
                    <div className="grid grid-cols-2 gap-3 text-[11px] text-slate-500 dark:text-slate-400">
                      <div className="rounded-2xl border border-slate-200 bg-slate-50/90 px-3 py-3 dark:border-slate-800 dark:bg-slate-900/60">
                        <div className="text-[10px] uppercase tracking-[0.16em]">开始时间</div>
                        <div className="mt-2 text-xs text-slate-700 dark:text-slate-200">{formatDateTime(selectedTask.started_at)}</div>
                      </div>
                      <div className="rounded-2xl border border-slate-200 bg-slate-50/90 px-3 py-3 dark:border-slate-800 dark:bg-slate-900/60">
                        <div className="text-[10px] uppercase tracking-[0.16em]">更新时间</div>
                        <div className="mt-2 text-xs text-slate-700 dark:text-slate-200">{formatDateTime(selectedTask.updated_at)}</div>
                      </div>
                    </div>

                    {selectedTask.error_message ? (
                      <div className="rounded-2xl border border-rose-200 bg-rose-50 px-3 py-3 text-xs leading-6 text-rose-700 dark:border-rose-800 dark:bg-rose-950/30 dark:text-rose-200">
                        {selectedTask.error_message}
                      </div>
                    ) : null}

                    <div className="rounded-2xl border border-slate-200 bg-slate-50/90 px-3 py-3 dark:border-slate-800 dark:bg-slate-900/60">
                      <div className="text-[10px] uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">任务信息</div>
                        <div className="mt-3 space-y-2 text-xs text-slate-600 dark:text-slate-300">
                        <div>Task ID：{selectedTask.task_id}</div>
                        {selectedTask?.summary?.filename ? <div>文件：{selectedTask.summary.filename}</div> : null}
                        {selectedTask?.summary?.doc_type ? <div>单据类型：{selectedTask.summary.doc_type}</div> : null}
                        {selectedTask?.summary?.item_count ? <div>印章数：{selectedTask.summary.item_count}</div> : null}
                        {selectedTask?.summary?.provider ? <div>来源：{selectedTask.summary.provider}</div> : null}
                        {selectedTask?.summary?.template ? <div>模板：{selectedTask.summary.template}</div> : null}
                      </div>
                    </div>

                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => handleOpenResult(selectedTask)}
                        className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-xs font-medium text-slate-600 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
                      >
                        <ExternalLink size={14} />
                        打开结果
                      </button>
                      {(selectedTask?.detail?.archive_url || selectedTask?.summary?.archive_url) ? (
                        <button
                          type="button"
                          onClick={() => window.open(selectedTask?.detail?.archive_url || selectedTask?.summary?.archive_url, '_blank', 'noopener,noreferrer')}
                          className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-xs font-medium text-slate-600 transition hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
                        >
                          <ExternalLink size={14} />
                          批量下载
                        </button>
                      ) : null}
                      {selectedTask.retry_supported && selectedTask.status === 'failed' ? (
                        <button
                          type="button"
                          disabled={retryingTaskId === selectedTask.task_id}
                          onClick={() => void handleRetry(selectedTask)}
                          className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-3 py-2 text-xs font-medium text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-blue-600 dark:hover:bg-blue-500"
                        >
                          {retryingTaskId === selectedTask.task_id ? <Loader2 size={14} className="animate-spin" /> : <RotateCcw size={14} />}
                          失败重试
                        </button>
                      ) : null}
                    </div>

                    {selectedTaskRawJson ? (
                      <div className="rounded-2xl border border-slate-200 bg-slate-950 px-3 py-3 dark:border-slate-700">
                        <div className="mb-2 text-[10px] uppercase tracking-[0.16em] text-slate-400">原始返回</div>
                        <pre className="max-h-44 overflow-auto whitespace-pre-wrap break-all text-[11px] leading-5 text-slate-200">{selectedTaskRawJson}</pre>
                      </div>
                    ) : null}
                  </div>
                </div>
              )}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
