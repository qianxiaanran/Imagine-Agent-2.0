import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  ArrowLeft,
  BarChart3,
  CircleDollarSign,
  Clock3,
  Database,
  Gauge,
  Package,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Truck,
  Users,
} from 'lucide-react';

import decisionApi from '../api/decision';

const DATA_AUTO_REFRESH_MS = 5 * 60 * 1000;
const AI_AUTO_REFRESH_MS = 30 * 60 * 1000;

const currencyFormatter = new Intl.NumberFormat('zh-CN', {
  style: 'currency',
  currency: 'CNY',
  maximumFractionDigits: 0,
});

const compactCurrencyFormatter = new Intl.NumberFormat('zh-CN', {
  style: 'currency',
  currency: 'CNY',
  notation: 'compact',
  maximumFractionDigits: 1,
});

const compactNumberFormatter = new Intl.NumberFormat('zh-CN', {
  notation: 'compact',
  maximumFractionDigits: 1,
});

const percentFormatter = new Intl.NumberFormat('zh-CN', {
  style: 'percent',
  maximumFractionDigits: 1,
});

const ratioFormatter = new Intl.NumberFormat('zh-CN', {
  maximumFractionDigits: 2,
});

const KPI_ICON_MAP = {
  sales_total: CircleDollarSign,
  purchase_total: Truck,
  gross_margin_rate: Gauge,
  collection_rate: Database,
  delivery_rate: BarChart3,
  inventory_turnover_proxy: Package,
  low_stock_sku: AlertTriangle,
  active_customers_90d: Users,
};

const CAPABILITY_COLORS = ['#0ea5e9', '#06b6d4', '#14b8a6', '#22c55e', '#f59e0b', '#ef4444'];

const WARNING_STYLE_MAP = {
  high: {
    badge: 'bg-rose-100 text-rose-700 border border-rose-200',
    row: 'bg-rose-50/70 dark:bg-rose-950/25',
    icon: ShieldAlert,
  },
  medium: {
    badge: 'bg-amber-100 text-amber-700 border border-amber-200',
    row: 'bg-amber-50/70 dark:bg-amber-950/25',
    icon: AlertTriangle,
  },
  low: {
    badge: 'bg-emerald-100 text-emerald-700 border border-emerald-200',
    row: 'bg-emerald-50/70 dark:bg-emerald-950/25',
    icon: Sparkles,
  },
};

function formatMetric(value, unit) {
  const numeric = Number(value || 0);
  if (unit === 'CNY') return compactCurrencyFormatter.format(numeric);
  if (unit === 'ratio') return percentFormatter.format(numeric);
  if (unit === 'times') return `${ratioFormatter.format(numeric)} 次`;
  if (unit === 'count') return compactNumberFormatter.format(numeric);
  return ratioFormatter.format(numeric);
}

function formatTrend(value) {
  const numeric = Number(value || 0);
  const sign = numeric > 0 ? '+' : '';
  return `${sign}${(numeric * 100).toFixed(1)}%`;
}

function formatCurrency(value) {
  return currencyFormatter.format(Number(value || 0));
}

function ScoreRing({ score = 0 }) {
  const radius = 54;
  const stroke = 10;
  const normalizedScore = Math.max(0, Math.min(100, Number(score || 0)));
  const circumference = 2 * Math.PI * radius;
  const dash = (normalizedScore / 100) * circumference;

  return (
    <div className="relative h-40 w-40">
      <svg viewBox="0 0 140 140" className="h-full w-full -rotate-90">
        <circle cx="70" cy="70" r={radius} fill="none" stroke="rgba(148,163,184,0.25)" strokeWidth={stroke} />
        <circle
          cx="70"
          cy="70"
          r={radius}
          fill="none"
          stroke="url(#decisionRing)"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${dash} ${circumference - dash}`}
        />
        <defs>
          <linearGradient id="decisionRing" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#0284c7" />
            <stop offset="100%" stopColor="#14b8a6" />
          </linearGradient>
        </defs>
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <div className="text-xs uppercase tracking-[0.18em] text-slate-500">经营评分</div>
        <div className="mt-1 text-3xl font-semibold text-slate-800 dark:text-slate-100">{normalizedScore.toFixed(1)}</div>
      </div>
    </div>
  );
}

function DualLineChart({ rows = [] }) {
  if (!rows.length) {
    return <div className="h-56 rounded-2xl border border-dashed border-slate-300/70 bg-white/50" />;
  }

  const width = 760;
  const height = 240;
  const padX = 24;
  const padY = 18;

  const maxValue = Math.max(
    1,
    ...rows.map((item) =>
      Math.max(Number(item.sales_amount || 0), Number(item.purchase_amount || 0), Number(item.net_amount || 0))
    )
  );

  const toPoint = (index, value) => {
    const x = padX + (index * (width - padX * 2)) / Math.max(rows.length - 1, 1);
    const y = height - padY - (Number(value || 0) / maxValue) * (height - padY * 2);
    return [x, y];
  };

  const salesPoints = rows.map((item, index) => toPoint(index, item.sales_amount));
  const purchasePoints = rows.map((item, index) => toPoint(index, item.purchase_amount));

  const pathFromPoints = (points) => points.map((point, idx) => `${idx === 0 ? 'M' : 'L'}${point[0]},${point[1]}`).join(' ');

  const salesPath = pathFromPoints(salesPoints);
  const purchasePath = pathFromPoints(purchasePoints);

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="h-56 w-full rounded-2xl bg-slate-950/[0.03]">
      {[0, 1, 2, 3].map((grid) => {
        const y = padY + (grid * (height - padY * 2)) / 3;
        return <line key={grid} x1={padX} y1={y} x2={width - padX} y2={y} stroke="rgba(100,116,139,0.2)" strokeDasharray="4 4" />;
      })}

      <path d={salesPath} fill="none" stroke="#0ea5e9" strokeWidth="3.2" strokeLinecap="round" />
      <path d={purchasePath} fill="none" stroke="#f97316" strokeWidth="3.2" strokeLinecap="round" />

      {salesPoints.map((point, idx) => (
        <circle key={`sales-${idx}`} cx={point[0]} cy={point[1]} r="3.5" fill="#0ea5e9" />
      ))}
      {purchasePoints.map((point, idx) => (
        <circle key={`purchase-${idx}`} cx={point[0]} cy={point[1]} r="3.5" fill="#f97316" />
      ))}
    </svg>
  );
}

function DecisionCenterPage() {
  const [dashboardData, setDashboardData] = useState(null);
  const [aiAnalysis, setAiAnalysis] = useState({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false); // data section refresh state
  const [refreshingAi, setRefreshingAi] = useState(false);
  const [error, setError] = useState('');
  const [backend, setBackend] = useState('local');

  const fetchDataSection = useCallback(async ({ refreshData = false, silent = false } = {}) => {
    if (!silent) {
      setError('');
      setRefreshing(true);
    }
    try {
      const payload = await decisionApi.getData({ refreshData });
      setDashboardData(payload || null);
    } catch (fetchError) {
      setError(fetchError?.message || '数据模块刷新失败');
    } finally {
      setRefreshing(false);
    }
  }, []);

  const fetchAiSection = useCallback(
    async ({ refreshAi = false, refreshData = false, silent = false } = {}) => {
      if (!silent) {
        setError('');
        setRefreshingAi(true);
      }
      try {
        const payload = await decisionApi.getAi({ refreshAi, refreshData, backend });
        setAiAnalysis(payload?.ai_analysis || {});
      } catch (fetchError) {
        setError(fetchError?.message || 'AI分析模块刷新失败');
      } finally {
        setRefreshingAi(false);
      }
    },
    [backend]
  );

  useEffect(() => {
    let disposed = false;
    setLoading(true);
    setError('');

    (async () => {
      try {
        const dataPayload = await decisionApi.getData({ refreshData: false });
        if (disposed) return;
        setDashboardData(dataPayload || null);
        setLoading(false);

        try {
          const aiPayload = await decisionApi.getAi({ refreshAi: false, refreshData: false, backend });
          if (!disposed) {
            setAiAnalysis(aiPayload?.ai_analysis || {});
          }
        } catch (aiError) {
          if (!disposed) {
            console.warn('AI section init failed:', aiError);
          }
        }
      } catch (dataError) {
        if (!disposed) {
          setError(dataError?.message || '数据决策面板加载失败');
          setLoading(false);
        }
      }
    })();

    return () => {
      disposed = true;
    };
  }, []);

  useEffect(() => {
    if (!dashboardData) return;
    void fetchAiSection({ refreshAi: false, refreshData: false, silent: true });
  }, [backend, dashboardData, fetchAiSection]);

  useEffect(() => {
    if (!dashboardData) return undefined;
    const timer = window.setInterval(() => {
      void fetchDataSection({ refreshData: true, silent: true });
    }, DATA_AUTO_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [dashboardData, fetchDataSection]);

  useEffect(() => {
    if (!dashboardData) return undefined;
    const timer = window.setInterval(() => {
      void fetchAiSection({ refreshAi: true, refreshData: false, silent: true });
    }, AI_AUTO_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [dashboardData, fetchAiSection]);

  const kpis = dashboardData?.kpis || [];
  const warnings = dashboardData?.warnings || [];
  const aiPending = Boolean(aiAnalysis?.pending);
  const trends = dashboardData?.trends || [];
  const cockpit = dashboardData?.cockpit || {};
  const capabilities = cockpit?.capabilities || [];
  const riskTable = dashboardData?.risk_table || [];
  const topProducts = dashboardData?.top_products || [];
  const warehouseRows = dashboardData?.warehouses || [];
  const categoryProfitRows = dashboardData?.category_profit || [];

  const displayKpis = useMemo(() => kpis.slice(0, 8), [kpis]);

  const aiRefreshText = useMemo(() => {
    const seconds = Number(aiAnalysis?.refresh_after_seconds || 0);
    if (seconds <= 0) return '即将自动刷新';
    const minutes = Math.ceil(seconds / 60);
    return `${minutes} 分钟后自动刷新`;
  }, [aiAnalysis]);

  useEffect(() => {
    if (!aiPending) return undefined;
    const timer = window.setTimeout(() => {
      void fetchAiSection({ refreshAi: false, refreshData: false, silent: true });
    }, 4000);
    return () => window.clearTimeout(timer);
  }, [aiPending, fetchAiSection]);

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-100 dark:bg-slate-950 flex items-center justify-center text-slate-600 dark:text-slate-300">
        <div className="flex items-center gap-2 text-sm">
          <RefreshCw size={16} className="animate-spin" />
          正在加载数据决策系统...
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-100 dark:bg-slate-950 text-slate-800 dark:text-slate-100">
      <div className="relative overflow-hidden border-b border-slate-200/80 dark:border-slate-800 bg-gradient-to-br from-cyan-100/70 via-sky-100/60 to-emerald-100/60 dark:from-slate-900 dark:via-slate-900 dark:to-slate-950">
        <div className="pointer-events-none absolute -top-28 -right-16 h-72 w-72 rounded-full bg-cyan-300/35 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-28 left-12 h-64 w-64 rounded-full bg-emerald-300/35 blur-3xl" />

        <div className="mx-auto max-w-[1400px] px-4 sm:px-6 lg:px-8 py-6 relative">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex items-start gap-3">
              <button
                type="button"
                onClick={() => window.location.assign('/')}
                className="mt-0.5 inline-flex items-center gap-1 rounded-full border border-slate-300/70 dark:border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-white/80 dark:hover:bg-slate-800 transition-colors"
              >
                <ArrowLeft size={14} />
                返回工作台
              </button>
              <div>
                <div className="inline-flex items-center gap-2 rounded-full border border-cyan-200/70 bg-white/70 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-cyan-700 dark:border-cyan-900/60 dark:bg-slate-900/70 dark:text-cyan-300">
                  <Gauge size={13} />
                  Decision Cockpit
                </div>
                <h1 className="mt-2 text-2xl md:text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-50">企业数据决策系统</h1>
                <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
                  聚合销售、采购、库存与履约数据，提供经营驾驶舱、可视化分析和风险预警。
                </p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <select
                value={backend}
                onChange={(event) => setBackend(event.target.value)}
                className="rounded-full border border-slate-300 dark:border-slate-700 bg-white/90 dark:bg-slate-900 px-3 py-2 text-xs font-medium outline-none focus:ring-2 focus:ring-cyan-300/70"
              >
                <option value="local">AI 分析: 本地模型</option>
                <option value="cloud">AI 分析: 云端模型</option>
              </select>

              <button
                type="button"
                onClick={() => void fetchDataSection({ refreshData: true, silent: false })}
                className="inline-flex items-center gap-1 rounded-full border border-slate-300 dark:border-slate-700 bg-white/90 dark:bg-slate-900 px-3 py-2 text-xs font-semibold hover:border-cyan-400 transition-colors"
              >
                <RefreshCw size={13} className={refreshing ? 'animate-spin' : ''} />
                刷新数据
              </button>

              <button
                type="button"
                onClick={() => void fetchAiSection({ refreshAi: true, refreshData: false, silent: false })}
                className="inline-flex items-center gap-1 rounded-full border border-slate-300 dark:border-slate-700 bg-white/90 dark:bg-slate-900 px-3 py-2 text-xs font-semibold hover:border-emerald-400 transition-colors"
              >
                <Sparkles size={13} className={refreshingAi ? 'animate-pulse' : ''} />
                刷新AI分析
              </button>

              <div className="inline-flex items-center gap-1 rounded-full border border-slate-300/80 dark:border-slate-700 px-3 py-2 text-xs text-slate-600 dark:text-slate-300 bg-white/65 dark:bg-slate-900/70">
                <Clock3 size={13} />
                数据5分钟，AI30分钟
              </div>
            </div>
          </div>

          {!!error && (
            <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900/50 dark:bg-rose-950/30 dark:text-rose-300">
              {error}
            </div>
          )}
        </div>
      </div>

      <main className="mx-auto max-w-[1400px] px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        <section className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
          {displayKpis.map((item) => {
            const Icon = KPI_ICON_MAP[item.key] || BarChart3;
            const trend = Number(item.trend || 0);
            const isPositive = trend >= 0;
            return (
              <article
                key={item.key}
                className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white/95 dark:bg-slate-900/80 p-4 shadow-[0_8px_28px_rgba(15,23,42,0.06)]"
              >
                <div className="flex items-start justify-between">
                  <div className="text-xs font-semibold uppercase tracking-[0.13em] text-slate-500">{item.label}</div>
                  <div className="rounded-xl bg-slate-100 dark:bg-slate-800 p-2 text-slate-600 dark:text-slate-300">
                    <Icon size={14} />
                  </div>
                </div>
                <div className="mt-2 text-2xl font-bold text-slate-900 dark:text-slate-100">{formatMetric(item.value, item.unit)}</div>
                <div className={`mt-2 inline-flex items-center gap-1 text-xs font-semibold ${isPositive ? 'text-emerald-600' : 'text-rose-600'}`}>
                  {isPositive ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
                  {formatTrend(item.trend)}
                </div>
                <div className="mt-3 h-1.5 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                  <div
                    className={`h-full rounded-full ${isPositive ? 'bg-emerald-400' : 'bg-rose-400'}`}
                    style={{ width: `${Math.max(6, Math.min(Number(item.target_progress || 0) * 100, 100))}%` }}
                  />
                </div>
              </article>
            );
          })}
        </section>

        <section className="grid grid-cols-1 xl:grid-cols-[1.25fr_1fr] gap-4">
          <article className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-[0_8px_28px_rgba(15,23,42,0.06)]">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">经营驾驶舱评分</h2>
                <p className="text-xs text-slate-500 dark:text-slate-400">盈利、运营、供应、库存、财务、增长六维能力</p>
              </div>
              <div className="inline-flex items-center gap-1 rounded-full bg-slate-100 dark:bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-600 dark:text-slate-300">
                <BarChart3 size={13} />
                总评分 {Number(cockpit.score || 0).toFixed(1)}
              </div>
            </div>

            <div className="mt-4 grid grid-cols-1 md:grid-cols-[170px_1fr] gap-4 items-center">
              <div className="flex justify-center">
                <ScoreRing score={cockpit.score || 0} />
              </div>
              <div className="space-y-2">
                {capabilities.map((item, index) => (
                  <div key={item.key || item.label}>
                    <div className="flex items-center justify-between text-xs text-slate-600 dark:text-slate-300">
                      <span className="font-semibold">{item.label}</span>
                      <span>{Number(item.score || 0).toFixed(1)}</span>
                    </div>
                    <div className="mt-1 h-2 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${Math.max(4, Math.min(Number(item.score || 0), 100))}%`,
                          backgroundColor: CAPABILITY_COLORS[index % CAPABILITY_COLORS.length],
                        }}
                      />
                    </div>
                    <div className="mt-0.5 text-[11px] text-slate-400">{item.desc}</div>
                  </div>
                ))}
              </div>
            </div>
          </article>

          <article className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-[0_8px_28px_rgba(15,23,42,0.06)]">
            <div className="flex items-center justify-between gap-2">
              <div>
                <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">AI 经营分析</h2>
                <p className="text-xs text-slate-500 dark:text-slate-400">自动汇总关键变化并给出管理建议</p>
              </div>
              <div className="inline-flex items-center gap-1 rounded-full bg-slate-100 dark:bg-slate-800 px-3 py-1.5 text-[11px] text-slate-600 dark:text-slate-300">
                <Clock3 size={12} />
                {aiRefreshText}
              </div>
            </div>

            <div className="mt-4 rounded-xl border border-cyan-200/70 dark:border-cyan-900/50 bg-cyan-50/50 dark:bg-cyan-950/20 p-3 text-sm leading-relaxed text-slate-700 dark:text-slate-200">
              {aiAnalysis.summary || '暂无 AI 分析结果。'}
            </div>
            {aiPending && (
              <div className="mt-2 text-xs text-cyan-700 dark:text-cyan-300 inline-flex items-center gap-1">
                <RefreshCw size={12} className="animate-spin" />
                AI分析正在后台生成，结果将自动更新...
              </div>
            )}

            <div className="mt-4 grid grid-cols-1 gap-3">
              <div className="rounded-xl border border-slate-200/70 dark:border-slate-800 p-3">
                <div className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">关键洞察</div>
                <ul className="mt-2 space-y-1 text-sm text-slate-700 dark:text-slate-200">
                  {(aiAnalysis.insights || []).map((item, idx) => (
                    <li key={`insight-${idx}`} className="flex gap-2">
                      <span className="mt-[7px] h-1.5 w-1.5 rounded-full bg-sky-500 shrink-0" />
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="rounded-xl border border-slate-200/70 dark:border-slate-800 p-3">
                <div className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">建议动作</div>
                <ul className="mt-2 space-y-1 text-sm text-slate-700 dark:text-slate-200">
                  {(aiAnalysis.actions || []).map((item, idx) => (
                    <li key={`action-${idx}`} className="flex gap-2">
                      <span className="mt-[7px] h-1.5 w-1.5 rounded-full bg-emerald-500 shrink-0" />
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            <div className="mt-3 text-xs text-slate-500 dark:text-slate-400">
              风险展望: {aiAnalysis.risk_outlook || '暂无'}
            </div>
          </article>
        </section>

        <section className="grid grid-cols-1 xl:grid-cols-[1.45fr_1fr] gap-4">
          <article className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-[0_8px_28px_rgba(15,23,42,0.06)]">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold">销售 vs 采购趋势</h2>
                <p className="text-xs text-slate-500 dark:text-slate-400">近12个月金额趋势（单位：人民币）</p>
              </div>
              <div className="flex items-center gap-3 text-xs text-slate-500">
                <span className="inline-flex items-center gap-1">
                  <span className="h-2 w-2 rounded-full bg-sky-500" />
                  销售
                </span>
                <span className="inline-flex items-center gap-1">
                  <span className="h-2 w-2 rounded-full bg-orange-500" />
                  采购
                </span>
              </div>
            </div>

            <div className="mt-4">
              <DualLineChart rows={trends} />
            </div>

            <div className="mt-3 grid grid-cols-3 gap-2 text-[11px] text-slate-500 dark:text-slate-400">
              {trends.slice(-3).map((row) => (
                <div key={row.month} className="rounded-lg bg-slate-50 dark:bg-slate-800/70 px-2 py-1.5">
                  <div>{row.month}</div>
                  <div className="font-medium text-slate-700 dark:text-slate-200">{formatMetric(row.net_amount, 'CNY')}</div>
                </div>
              ))}
            </div>
          </article>

          <article className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-[0_8px_28px_rgba(15,23,42,0.06)]">
            <h2 className="text-lg font-semibold">数据预警</h2>
            <p className="text-xs text-slate-500 dark:text-slate-400">结合经营规则自动生成</p>

            <div className="mt-4 space-y-2">
              {warnings.map((item, idx) => {
                const style = WARNING_STYLE_MAP[item.level] || WARNING_STYLE_MAP.medium;
                const Icon = style.icon;
                return (
                  <div key={`${item.title}-${idx}`} className={`rounded-xl px-3 py-2 ${style.row}`}>
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <Icon size={14} className="shrink-0 text-slate-600 dark:text-slate-300" />
                        <div className="text-sm font-semibold text-slate-800 dark:text-slate-100 truncate">{item.title}</div>
                      </div>
                      <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${style.badge}`}>
                        {item.level}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-slate-600 dark:text-slate-300">{item.description}</div>
                  </div>
                );
              })}
            </div>
          </article>
        </section>

        <section className="grid grid-cols-1 xl:grid-cols-[1.3fr_1fr] gap-4">
          <article className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-[0_8px_28px_rgba(15,23,42,0.06)] overflow-x-auto">
            <h2 className="text-lg font-semibold">风险明细</h2>
            <p className="text-xs text-slate-500 dark:text-slate-400">客户回款、库存缺口与采购积压重点对象</p>

            <table className="mt-4 min-w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-[0.08em] text-slate-500 border-b border-slate-200 dark:border-slate-800">
                  <th className="px-2 py-2">类别</th>
                  <th className="px-2 py-2">对象</th>
                  <th className="px-2 py-2">数值</th>
                  <th className="px-2 py-2">计数</th>
                  <th className="px-2 py-2">说明</th>
                </tr>
              </thead>
              <tbody>
                {riskTable.slice(0, 12).map((row, idx) => (
                  <tr key={`${row.category}-${row.name}-${idx}`} className="border-b border-slate-100 dark:border-slate-800/70">
                    <td className="px-2 py-2 font-medium text-slate-700 dark:text-slate-200">{row.category}</td>
                    <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{row.name}</td>
                    <td className="px-2 py-2 text-slate-700 dark:text-slate-200">
                      {row.category === '库存缺口' ? compactNumberFormatter.format(Number(row.value || 0)) : formatCurrency(row.value)}
                    </td>
                    <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{compactNumberFormatter.format(Number(row.count || 0))}</td>
                    <td className="px-2 py-2 text-xs text-slate-500 dark:text-slate-400">{row.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </article>

          <div className="space-y-4">
            <article className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-[0_8px_28px_rgba(15,23,42,0.06)]">
              <h3 className="text-base font-semibold">Top 商品销售</h3>
              <div className="mt-3 space-y-2">
                {topProducts.slice(0, 6).map((row, idx) => {
                  const maxRevenue = Math.max(...topProducts.map((item) => Number(item.revenue || 0)), 1);
                  const width = (Number(row.revenue || 0) / maxRevenue) * 100;
                  return (
                    <div key={`${row.prod_name}-${idx}`}>
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-medium text-slate-700 dark:text-slate-200 truncate pr-2">{row.prod_name}</span>
                        <span className="text-slate-500">{formatMetric(row.revenue, 'CNY')}</span>
                      </div>
                      <div className="mt-1 h-2 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                        <div className="h-full rounded-full bg-cyan-500" style={{ width: `${Math.max(width, 4)}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </article>

            <article className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-[0_8px_28px_rgba(15,23,42,0.06)]">
              <h3 className="text-base font-semibold">仓库库存分布</h3>
              <div className="mt-3 space-y-2">
                {warehouseRows.map((row, idx) => {
                  const maxUnits = Math.max(...warehouseRows.map((item) => Number(item.units || 0)), 1);
                  const width = (Number(row.units || 0) / maxUnits) * 100;
                  return (
                    <div key={`${row.warehouse}-${idx}`}>
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-medium text-slate-700 dark:text-slate-200">{row.warehouse}</span>
                        <span className="text-slate-500">{compactNumberFormatter.format(Number(row.units || 0))}</span>
                      </div>
                      <div className="mt-1 h-2 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                        <div className="h-full rounded-full bg-emerald-500" style={{ width: `${Math.max(width, 5)}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </article>
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-[0_8px_28px_rgba(15,23,42,0.06)] overflow-x-auto">
          <h2 className="text-lg font-semibold">品类盈利分析</h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">销售额、成本额与毛利率对比</p>

          <table className="mt-4 min-w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-[0.08em] text-slate-500 border-b border-slate-200 dark:border-slate-800">
                <th className="px-2 py-2">品类</th>
                <th className="px-2 py-2">销售额</th>
                <th className="px-2 py-2">成本额</th>
                <th className="px-2 py-2">利润额</th>
                <th className="px-2 py-2">毛利率</th>
              </tr>
            </thead>
            <tbody>
              {categoryProfitRows.map((row) => (
                <tr key={row.category} className="border-b border-slate-100 dark:border-slate-800/70">
                  <td className="px-2 py-2 font-medium text-slate-700 dark:text-slate-200">{row.category}</td>
                  <td className="px-2 py-2 text-slate-700 dark:text-slate-200">{formatCurrency(row.sales_amount)}</td>
                  <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{formatCurrency(row.cost_amount)}</td>
                  <td className="px-2 py-2 text-slate-700 dark:text-slate-200">{formatCurrency(row.profit_amount)}</td>
                  <td className="px-2 py-2 text-slate-700 dark:text-slate-200">{percentFormatter.format(Number(row.margin_rate || 0))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </main>
    </div>
  );
}

export default DecisionCenterPage;
