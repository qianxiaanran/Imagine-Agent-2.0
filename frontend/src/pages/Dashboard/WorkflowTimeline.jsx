import React from 'react';
import { GitBranch, Loader2, Play, RefreshCw, BarChart3 } from 'lucide-react';
import StepCard from './StepCard';

const statusLabelMap = {
  pending: '待启动',
  running: '执行中',
  blocked: '待人工确认',
  done: '已完成',
  failed: '执行失败',
  cancelled: '已取消',
};

const calcProgress = (steps = []) => {
  if (!Array.isArray(steps) || steps.length === 0) return 0;
  const doneCount = steps.filter((step) => String(step?.status || '').toLowerCase() === 'done').length;
  return Math.round((doneCount / steps.length) * 100);
};

const WorkflowTimeline = ({
  workflowJob,
  inputQuery,
  onInputQueryChange,
  onStart,
  onRefresh,
  onConfirm,
  onRetry,
  isLoading = false,
  actionLoading = false,
  error = '',
}) => {
  const steps = Array.isArray(workflowJob?.steps) ? workflowJob.steps : [];
  const status = String(workflowJob?.status || 'pending').toLowerCase();
  const statusLabel = statusLabelMap[status] || status;
  const progress = calcProgress(steps);
  const canRetry = status === 'failed' || status === 'cancelled';

  return (
    <div className="w-full h-full flex flex-col border-b md:border-b-0 md:border-r border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
      <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-gray-900 dark:text-white font-semibold">
          <GitBranch size={17} />
          Workflow 编排
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={isLoading || !workflowJob?.job_id}
          className="text-xs inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-full border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-60"
        >
          <RefreshCw size={12} className={isLoading ? 'animate-spin' : ''} />
          刷新
        </button>
      </div>

      <div className="flex-1 overflow-y-auto custom-scrollbar p-4 space-y-4">
        <section className="rounded-2xl border border-gray-200 dark:border-gray-700 bg-gray-50/70 dark:bg-gray-900/40 p-4 space-y-3">
          <div className="text-sm font-semibold text-gray-900 dark:text-white">月度经营分析流程</div>
          <div className="text-xs text-gray-500 dark:text-gray-400">
            流程：查库 -&gt; 结论 -&gt; 报告草案 -&gt; 人工确认 -&gt; 生成分享链接
          </div>
          <textarea
            value={inputQuery}
            onChange={(event) => onInputQueryChange && onInputQueryChange(event.target.value)}
            className="w-full min-h-[88px] resize-y rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2 text-sm text-gray-800 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-gray-400/20"
            placeholder="输入本次月度分析目标，例如：分析销售、毛利和库存周转，给出下月动作建议。"
          />
          <button
            type="button"
            onClick={onStart}
            disabled={isLoading || !String(inputQuery || '').trim()}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-black text-white dark:bg-white dark:text-black text-sm font-medium hover:opacity-90 disabled:opacity-50"
          >
            {isLoading ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />}
            启动工作流
          </button>
        </section>

        {error ? (
          <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 text-xs px-3 py-2 whitespace-pre-wrap">
            {error}
          </div>
        ) : null}

        {workflowJob?.job_id ? (
          <section className="rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-xs text-gray-500 dark:text-gray-400">任务ID：{workflowJob.job_id}</div>
              <div className="text-xs px-2 py-1 rounded-full border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-200">
                {statusLabel}
              </div>
            </div>
            <div className="space-y-1">
              <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
                <span>进度</span>
                <span>{progress}%</span>
              </div>
              <div className="w-full h-2 rounded-full bg-gray-100 dark:bg-gray-800 overflow-hidden">
                <div className="h-full bg-gray-900 dark:bg-white transition-all" style={{ width: `${progress}%` }} />
              </div>
            </div>
            {workflowJob?.result_json?.share?.share_url ? (
              <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-700">
                <div className="font-medium mb-1">已生成分享链接</div>
                <div>{workflowJob.result_json.share.share_url}</div>
              </div>
            ) : null}
            {canRetry ? (
              <button
                type="button"
                onClick={onRetry}
                disabled={actionLoading}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border border-gray-300 text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-800 disabled:opacity-60"
              >
                <RefreshCw size={12} />
                重试工作流
              </button>
            ) : null}
          </section>
        ) : null}

        {steps.length > 0 ? (
          <section className="space-y-3">
            <div className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-white">
              <BarChart3 size={15} />
              执行时间线
            </div>
            {steps.map((step) => (
              <StepCard
                key={`${workflowJob?.job_id || 'job'}-${step.step_key}`}
                step={step}
                canConfirm={status === 'blocked' && step.step_key === 'manual_confirm' && String(step.status).toLowerCase() === 'blocked'}
                canRetry={false}
                actionLoading={actionLoading}
                onConfirm={onConfirm}
                onRetry={onRetry}
              />
            ))}
          </section>
        ) : null}
      </div>
    </div>
  );
};

export default WorkflowTimeline;
