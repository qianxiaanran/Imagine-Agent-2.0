import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  ArrowLeft,
  BarChart3,
  CircleDollarSign,
  Clock3,
  Database,
  Download,
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
import StatePanel from '../components/StatePanel';
import { getFriendlyRequestError, isAuthRequiredError, isPermissionDeniedError } from '../utils/requestErrors';

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

const chartNumberFormatter = new Intl.NumberFormat('zh-CN', {
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

const dateTimeFormatter = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
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

const BREAKDOWN_COLORS = ['#0ea5e9', '#22c55e', '#f59e0b', '#a855f7', '#ef4444', '#14b8a6'];
const RISK_TILE_COLORS = ['#0ea5e9', '#f59e0b', '#ef4444', '#22c55e'];
const STATUS_LABEL_MAP = {
  pending: '待处理',
  unpaid: '未付款',
  partial: '部分付款',
  paid: '已付款',
  delivered: '已交付',
  shipped: '已发货',
  shipping: '运输中',
  processing: '处理中',
  completed: '已完成',
  cancelled: '已取消',
  canceled: '已取消',
  active: '活跃',
};

const TREND_GRANULARITY_LABELS = {
  week: '按周',
  month: '按月',
  quarter: '按季',
};

const DECISION_METRIC_NOTES = {
  trend: '按订单日期与采购日期分桶汇总金额，口径为含税总额，不按行项目数计。',
  payment: '以订单金额统计付款状态结构，适合判断回款压力和催收优先级。',
  delivery: '以订单金额统计履约状态结构，用于识别发货、交付和资金兑现之间的错配。',
  purchase: '以采购单金额统计采购状态，重点看在途、处理中和已完成采购的资金占用。',
  risk: '风险对象按客户回款、库存缺口、采购积压三类聚合，支持点选联动明细。',
  product: '基于近180日销售额排序，同时补充销量和品类信息。',
  category: '按品类汇总销售额、成本额和利润额，帮助定位利润贡献与承压区域。',
  warehouse: '按当前库存快照统计仓库件数与行数，反映库存集中度和仓位压力。',
};

const DRILLDOWN_GROUP_META = {
  customer: {
    label: '客户',
    Icon: Users,
    emptyText: '当前维度下没有关联客户对象',
  },
  sku: {
    label: 'SKU',
    Icon: Package,
    emptyText: '当前维度下没有关联 SKU',
  },
  receivable: {
    label: '回款项',
    Icon: CircleDollarSign,
    emptyText: '当前维度下没有关联回款项',
  },
  inventory: {
    label: '库存对象',
    Icon: Database,
    emptyText: '当前维度下没有关联库存对象',
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

function formatCompactCurrency(value) {
  return compactCurrencyFormatter.format(Number(value || 0));
}

function formatTrendMonth(value, withYear = false) {
  const match = String(value || '').match(/^(\d{4})-(\d{1,2})$/);
  if (!match) return String(value || '-');

  const year = Number(match[1]);
  const month = Number(match[2]);
  return withYear ? `${year}年${month}月` : `${month}月`;
}

function formatDateTime(value) {
  if (!value) return '-';
  const parsed = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value || '-');
  return dateTimeFormatter.format(parsed).replace(/\//g, '-');
}

function clampNumber(value, min = 0, max = 100) {
  return Math.min(max, Math.max(min, Number(value || 0)));
}

function sumBy(items = [], key) {
  return items.reduce((sum, item) => sum + Number(item?.[key] || 0), 0);
}

function resolveBreakdownCount(item = {}) {
  return Number(item?.order_count ?? item?.purchase_count ?? item?.count ?? 0);
}

function formatStatusLabel(status) {
  const normalized = String(status || '').trim();
  if (!normalized) return '未分类';
  const mapped = STATUS_LABEL_MAP[normalized.toLowerCase()];
  return mapped || normalized;
}

function formatTrendBucketLabel(row, withYear = false) {
  if (!row) return '-';
  const granularity = String(row?.granularity || 'month');
  const bucket = String(row?.bucket || row?.month || row?.label || '').trim();
  if (granularity === 'week' || granularity === 'quarter') {
    return String(row?.label || bucket || '-');
  }
  return formatTrendMonth(bucket, withYear);
}

function formatDrilldownMetricValue(value, unit) {
  if (unit === 'CNY') return formatCurrency(value);
  if (unit === 'count') return compactNumberFormatter.format(Number(value || 0));
  if (unit === 'ratio') return percentFormatter.format(Number(value || 0));
  if (unit === 'times') return `${ratioFormatter.format(Number(value || 0))} 次`;
  if (unit === 'text') return String(value || '-');
  const rawValue = String(value ?? '').trim();
  return rawValue || '-';
}

function resolveFirstPopulatedGroup(objectGroups = {}, preferredGroup = 'customer') {
  if (preferredGroup && Array.isArray(objectGroups?.[preferredGroup]) && objectGroups[preferredGroup].length) {
    return preferredGroup;
  }

  const fallbackKey = Object.keys(DRILLDOWN_GROUP_META).find((key) => Array.isArray(objectGroups?.[key]) && objectGroups[key].length);
  return fallbackKey || preferredGroup || 'customer';
}

function isSameDrilldownContext(left, right) {
  if (!left || !right) return false;
  return (
    String(left.source || '') === String(right.source || '') &&
    String(left.granularity || '') === String(right.granularity || '') &&
    String(left.bucket || '') === String(right.bucket || '') &&
    String(left.status || '') === String(right.status || '') &&
    String(left.category || '') === String(right.category || '') &&
    String(left.name || '') === String(right.name || '')
  );
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function formatReportRiskValue(row = {}) {
  if (row.category === '库存缺口') {
    return compactNumberFormatter.format(Number(row.value || 0));
  }
  return formatCurrency(row.value);
}

function buildMetricCardsHtml(kpis = []) {
  if (!kpis.length) {
    return '<div class="empty-box">暂无关键指标数据</div>';
  }

  return kpis
    .slice(0, 8)
    .map((item) => {
      const trend = Number(item?.trend || 0);
      const trendClass = trend >= 0 ? 'positive' : 'negative';
      return `
        <article class="metric-card">
          <div class="metric-label">${escapeHtml(item?.label || '-')}</div>
          <div class="metric-value">${escapeHtml(formatMetric(item?.value, item?.unit))}</div>
          <div class="metric-trend ${trendClass}">${escapeHtml(formatTrend(trend))}</div>
        </article>
      `;
    })
    .join('');
}

function buildSimpleListHtml(items = [], emptyText = '暂无数据') {
  if (!items.length) {
    return `<div class="empty-box">${escapeHtml(emptyText)}</div>`;
  }

  return `
    <ul class="bullet-list">
      ${items.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}
    </ul>
  `;
}

function buildTableHtml(headers = [], rows = [], emptyText = '暂无数据') {
  if (!rows.length) {
    return `<div class="empty-box">${escapeHtml(emptyText)}</div>`;
  }

  return `
    <table class="report-table">
      <thead>
        <tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join('')}</tr>
      </thead>
      <tbody>
        ${rows
          .map(
            (row) => `
              <tr>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join('')}</tr>
            `
          )
          .join('')}
      </tbody>
    </table>
  `;
}

function useEntranceAnimation(delay = 0) {
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setIsReady(true), delay);
    return () => window.clearTimeout(timer);
  }, [delay]);

  return isReady;
}

function buildDecisionFinancialReportHtml({ dashboardData, aiAnalysis, backendLabel }) {
  const kpis = Array.isArray(dashboardData?.kpis) ? dashboardData.kpis : [];
  const cockpit = dashboardData?.cockpit || {};
  const trends = Array.isArray(dashboardData?.trends) ? dashboardData.trends : [];
  const warnings = Array.isArray(dashboardData?.warnings) ? dashboardData.warnings : [];
  const riskTable = Array.isArray(dashboardData?.risk_table) ? dashboardData.risk_table : [];
  const topProducts = Array.isArray(dashboardData?.top_products) ? dashboardData.top_products : [];
  const warehouses = Array.isArray(dashboardData?.warehouses) ? dashboardData.warehouses : [];
  const categoryProfit = Array.isArray(dashboardData?.category_profit) ? dashboardData.category_profit : [];
  const totals = dashboardData?.totals || {};
  const capabilities = Array.isArray(cockpit?.capabilities) ? cockpit.capabilities : [];
  const aiInsights = Array.isArray(aiAnalysis?.risk_reasons || aiAnalysis?.insights)
    ? (aiAnalysis?.risk_reasons || aiAnalysis?.insights)
    : [];
  const aiActions = Array.isArray(aiAnalysis?.suggested_actions || aiAnalysis?.actions)
    ? (aiAnalysis?.suggested_actions || aiAnalysis?.actions)
    : [];

  const title = `企业财政经营报表_${formatDateTime(new Date()).replace(/[^\d]/g, '').slice(0, 14)}`;
  const generatedAtText = formatDateTime(dashboardData?.generated_at);
  const exportedAtText = formatDateTime(new Date());

  const trendTable = buildTableHtml(
    ['期间', '销售额', '采购额', '净额', '销售单量', '采购单量'],
    trends.map((row) => [
      formatTrendBucketLabel(row, true),
      formatCurrency(row.sales_amount),
      formatCurrency(row.purchase_amount),
      formatCurrency(row.net_amount),
      compactNumberFormatter.format(Number(row.sales_orders || 0)),
      compactNumberFormatter.format(Number(row.purchase_orders || 0)),
    ]),
    '暂无趋势数据'
  );

  const categoryTable = buildTableHtml(
    ['品类', '销售额', '成本额', '利润额', '毛利率'],
    categoryProfit.slice(0, 12).map((row) => [
      row.category || '-',
      formatCurrency(row.sales_amount),
      formatCurrency(row.cost_amount),
      formatCurrency(row.profit_amount),
      percentFormatter.format(Number(row.margin_rate || 0)),
    ]),
    '暂无品类盈利数据'
  );

  const warehouseTable = buildTableHtml(
    ['仓库', '库存件数'],
    warehouses.map((row) => [
      row.warehouse || '-',
      compactNumberFormatter.format(Number(row.units || 0)),
    ]),
    '暂无仓库库存数据'
  );

  const productTable = buildTableHtml(
    ['商品', '销售额'],
    topProducts.slice(0, 10).map((row) => [row.prod_name || '-', formatCurrency(row.revenue)]),
    '暂无商品销售数据'
  );

  const riskTableHtml = buildTableHtml(
    ['类别', '对象', '数值', '计数', '说明'],
    riskTable.slice(0, 12).map((row) => [
      row.category || '-',
      row.name || '-',
      formatReportRiskValue(row),
      compactNumberFormatter.format(Number(row.count || 0)),
      row.note || '-',
    ]),
    '暂无风险明细'
  );

  const warningListHtml = warnings.length
    ? warnings
        .slice(0, 8)
        .map(
          (item) => `
            <div class="notice-item">
              <div class="notice-head">
                <strong>${escapeHtml(item?.title || '-')}</strong>
                <span class="level">${escapeHtml(String(item?.level || 'medium').toUpperCase())}</span>
              </div>
              <div class="notice-body">${escapeHtml(item?.description || '-')}</div>
            </div>
          `
        )
        .join('')
    : '<div class="empty-box">暂无预警信息</div>';

  const capabilityHtml = capabilities.length
    ? capabilities
        .map(
          (item) => `
            <div class="capability-item">
              <span>${escapeHtml(item?.label || '-')}</span>
              <strong>${escapeHtml(Number(item?.score || 0).toFixed(1))}</strong>
            </div>
          `
        )
        .join('')
    : '<div class="empty-box">暂无能力评分</div>';

  return `
    <!DOCTYPE html>
    <html lang="zh-CN">
      <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>${escapeHtml(title)}</title>
        <style>
          @page {
            size: A4;
            margin: 14mm;
          }
          * {
            box-sizing: border-box;
          }
          body {
            margin: 0;
            color: #0f172a;
            background: #f8fafc;
            font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif;
            -webkit-print-color-adjust: exact;
            print-color-adjust: exact;
          }
          .report-shell {
            padding: 18px;
          }
          .hero {
            border-radius: 24px;
            padding: 24px 26px;
            color: #e2e8f0;
            background:
              radial-gradient(circle at top right, rgba(34, 197, 94, 0.28), transparent 34%),
              radial-gradient(circle at left center, rgba(14, 165, 233, 0.22), transparent 36%),
              linear-gradient(135deg, #0f172a 0%, #162033 48%, #13313c 100%);
          }
          .hero-kicker {
            display: inline-block;
            padding: 6px 10px;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.08);
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.12em;
            text-transform: uppercase;
          }
          .hero h1 {
            margin: 14px 0 8px;
            font-size: 30px;
            line-height: 1.15;
          }
          .hero p {
            margin: 0;
            max-width: 760px;
            font-size: 13px;
            line-height: 1.7;
            color: #cbd5e1;
          }
          .meta-grid,
          .summary-grid,
          .dual-grid,
          .triple-grid {
            display: grid;
            gap: 14px;
          }
          .meta-grid {
            grid-template-columns: repeat(4, minmax(0, 1fr));
            margin-top: 18px;
          }
          .summary-grid {
            grid-template-columns: repeat(4, minmax(0, 1fr));
            margin-top: 18px;
          }
          .dual-grid {
            grid-template-columns: 1.2fr 1fr;
            margin-top: 14px;
          }
          .triple-grid {
            grid-template-columns: 1fr 1fr 1fr;
            margin-top: 14px;
          }
          .panel {
            background: #ffffff;
            border: 1px solid #dbe5f1;
            border-radius: 22px;
            padding: 18px;
            box-shadow: 0 12px 30px rgba(15, 23, 42, 0.06);
            break-inside: avoid;
          }
          .meta-card {
            border-radius: 18px;
            padding: 14px 16px;
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.08);
          }
          .meta-label,
          .section-kicker {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.12em;
            color: #64748b;
            font-weight: 700;
          }
          .hero .meta-label {
            color: #94a3b8;
          }
          .meta-value {
            margin-top: 8px;
            font-size: 14px;
            font-weight: 700;
            line-height: 1.5;
          }
          .hero .meta-value {
            color: #f8fafc;
          }
          .section-title {
            margin: 6px 0 0;
            font-size: 21px;
            color: #0f172a;
          }
          .section-desc {
            margin: 8px 0 0;
            color: #475569;
            font-size: 13px;
            line-height: 1.7;
          }
          .metric-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 12px;
            margin-top: 16px;
          }
          .metric-card {
            border: 1px solid #dbe5f1;
            border-radius: 18px;
            padding: 16px;
            background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
          }
          .metric-label {
            color: #64748b;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
          }
          .metric-value {
            margin-top: 10px;
            font-size: 24px;
            font-weight: 800;
            color: #0f172a;
          }
          .metric-trend {
            margin-top: 8px;
            font-size: 12px;
            font-weight: 700;
          }
          .positive {
            color: #15803d;
          }
          .negative {
            color: #dc2626;
          }
          .score-board {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            margin-top: 16px;
            padding: 18px;
            border-radius: 18px;
            background: linear-gradient(135deg, #e0f2fe 0%, #ecfeff 100%);
            border: 1px solid #bae6fd;
          }
          .score-number {
            font-size: 42px;
            font-weight: 800;
            color: #0f172a;
            line-height: 1;
          }
          .score-caption {
            margin-top: 6px;
            font-size: 12px;
            color: #0f766e;
          }
          .capability-stack {
            display: grid;
            gap: 10px;
            min-width: 240px;
          }
          .capability-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            padding-bottom: 8px;
            border-bottom: 1px dashed #cbd5e1;
            font-size: 12px;
          }
          .capability-item:last-child {
            border-bottom: 0;
            padding-bottom: 0;
          }
          .hero-summary {
            margin-top: 16px;
            padding: 16px 18px;
            border-radius: 18px;
            background: #f8fafc;
            border: 1px solid #dbe5f1;
            color: #334155;
            font-size: 13px;
            line-height: 1.75;
          }
          .report-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 14px;
            font-size: 12px;
          }
          .report-table th,
          .report-table td {
            padding: 10px 12px;
            border-bottom: 1px solid #e2e8f0;
            text-align: left;
            vertical-align: top;
          }
          .report-table th {
            color: #64748b;
            font-size: 11px;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            background: #f8fafc;
          }
          .bullet-list {
            margin: 14px 0 0;
            padding-left: 18px;
            color: #334155;
          }
          .bullet-list li {
            margin-top: 8px;
            line-height: 1.7;
          }
          .bullet-list li:first-child {
            margin-top: 0;
          }
          .notice-item {
            margin-top: 12px;
            padding: 14px 16px;
            border-radius: 16px;
            border: 1px solid #e2e8f0;
            background: #fffdf7;
          }
          .notice-item:first-child {
            margin-top: 14px;
          }
          .notice-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            font-size: 13px;
            color: #0f172a;
          }
          .level {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 64px;
            padding: 4px 10px;
            border-radius: 999px;
            background: #fee2e2;
            color: #b91c1c;
            font-size: 11px;
            font-weight: 800;
          }
          .notice-body {
            margin-top: 8px;
            color: #475569;
            font-size: 12px;
            line-height: 1.7;
          }
          .empty-box {
            margin-top: 14px;
            padding: 14px 16px;
            border-radius: 16px;
            border: 1px dashed #cbd5e1;
            color: #64748b;
            font-size: 12px;
            background: #f8fafc;
          }
          .footer-note {
            margin-top: 18px;
            color: #64748b;
            font-size: 11px;
            text-align: right;
          }
          @media print {
            body {
              background: #ffffff;
            }
            .report-shell {
              padding: 0;
            }
          }
          @media (max-width: 1024px) {
            .meta-grid,
            .summary-grid,
            .metric-grid,
            .dual-grid,
            .triple-grid {
              grid-template-columns: 1fr;
            }
          }
        </style>
      </head>
      <body>
        <main class="report-shell">
          <section class="hero">
            <div class="hero-kicker">Decision Cockpit</div>
            <h1>企业财政经营报表</h1>
            <p>基于当前企业数据决策系统快照生成，覆盖经营指标、近月收支趋势、库存与商品销售、风险预警以及 AI 经营分析摘要。</p>
            <div class="meta-grid">
              <div class="meta-card">
                <div class="meta-label">导出时间</div>
                <div class="meta-value">${escapeHtml(exportedAtText)}</div>
              </div>
              <div class="meta-card">
                <div class="meta-label">数据快照时间</div>
                <div class="meta-value">${escapeHtml(generatedAtText)}</div>
              </div>
              <div class="meta-card">
                <div class="meta-label">AI 分析引擎</div>
                <div class="meta-value">${escapeHtml(backendLabel || '本地模型')}</div>
              </div>
              <div class="meta-card">
                <div class="meta-label">经营评分</div>
                <div class="meta-value">${escapeHtml(Number(cockpit?.score || 0).toFixed(1))}</div>
              </div>
            </div>
          </section>

          <section class="panel">
            <div class="section-kicker">Executive Summary</div>
            <h2 class="section-title">关键财务指标概览</h2>
            <p class="section-desc">以下指标用于快速复盘当前销售、采购、利润、回款、履约与库存状态。</p>
            <div class="metric-grid">${buildMetricCardsHtml(kpis)}</div>
            <div class="score-board">
              <div>
                <div class="section-kicker">Cockpit Score</div>
                <div class="score-number">${escapeHtml(Number(cockpit?.score || 0).toFixed(1))}</div>
                <div class="score-caption">
                  订单数 ${escapeHtml(compactNumberFormatter.format(Number(totals.order_count || 0)))} /
                  采购单 ${escapeHtml(compactNumberFormatter.format(Number(totals.purchase_count || 0)))} /
                  客户 ${escapeHtml(compactNumberFormatter.format(Number(totals.total_customers || 0)))}
                </div>
              </div>
              <div class="capability-stack">${capabilityHtml}</div>
            </div>
            <div class="hero-summary">${escapeHtml(aiAnalysis?.summary || '暂无 AI 分析结果。')}</div>
          </section>

          <section class="dual-grid">
            <article class="panel">
              <div class="section-kicker">Trend Snapshot</div>
              <h2 class="section-title">近月收支趋势</h2>
              <p class="section-desc">按月展示销售额、采购额、净额以及对应单量，便于财务和经营复盘。</p>
              ${trendTable}
            </article>
            <article class="panel">
              <div class="section-kicker">Alerts</div>
              <h2 class="section-title">风险预警摘要</h2>
              <p class="section-desc">系统根据库存、回款与采购积压情况自动生成重点提示。</p>
              ${warningListHtml}
            </article>
          </section>

          <section class="triple-grid">
            <article class="panel">
              <div class="section-kicker">Product Sales</div>
              <h2 class="section-title">重点商品销售</h2>
              <p class="section-desc">按销售额查看当前带动收入的关键商品。</p>
              ${productTable}
            </article>
            <article class="panel">
              <div class="section-kicker">Warehouse</div>
              <h2 class="section-title">仓库库存分布</h2>
              <p class="section-desc">用于查看库存集中度及仓储调拨参考。</p>
              ${warehouseTable}
            </article>
            <article class="panel">
              <div class="section-kicker">AI Actions</div>
              <h2 class="section-title">AI 建议动作</h2>
              <p class="section-desc">基于当前数据快照生成的管理动作建议。</p>
              ${buildSimpleListHtml(aiActions, '暂无 AI 建议动作')}
            </article>
          </section>

          <section class="dual-grid">
            <article class="panel">
              <div class="section-kicker">Category Profitability</div>
              <h2 class="section-title">品类盈利分析</h2>
              <p class="section-desc">用于识别利润贡献高、成本占比较高或毛利承压的品类。</p>
              ${categoryTable}
            </article>
            <article class="panel">
              <div class="section-kicker">AI Insights</div>
              <h2 class="section-title">AI 洞察与风险展望</h2>
              <p class="section-desc">结合当前财务经营数据输出的洞察与风险判断。</p>
              ${buildSimpleListHtml(aiInsights, '暂无 AI 洞察')}
              <div class="hero-summary" style="margin-top: 16px;">
                <strong>风险展望：</strong>${escapeHtml(aiAnalysis?.risk_outlook || '暂无')}
              </div>
            </article>
          </section>

          <section class="panel">
            <div class="section-kicker">Risk Detail</div>
            <h2 class="section-title">风险明细台账</h2>
            <p class="section-desc">列示当前需重点跟踪的客户回款、库存缺口与采购积压对象。</p>
            ${riskTableHtml}
            <div class="footer-note">提示：此报表由浏览器打印通道导出，保存时请选择“另存为 PDF”。</div>
          </section>
        </main>
        <script>
          window.addEventListener('load', function () {
            setTimeout(function () {
              window.focus();
              window.print();
            }, 320);
          });
          window.addEventListener('afterprint', function () {
            window.close();
          });
        </script>
      </body>
    </html>
  `;
}

function ScoreRing({ score = 0 }) {
  const isReady = useEntranceAnimation(120);
  const radius = 54;
  const stroke = 10;
  const normalizedScore = clampNumber(score);
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
          strokeDasharray={`${circumference} ${circumference}`}
          strokeDashoffset={isReady ? circumference - dash : circumference}
          style={{ transition: 'stroke-dashoffset 900ms cubic-bezier(0.22,1,0.36,1)' }}
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
        <div
          className="mt-1 text-3xl font-semibold text-slate-800 transition-all duration-700 dark:text-slate-100"
          style={{ opacity: isReady ? 1 : 0.3, transform: isReady ? 'translateY(0)' : 'translateY(8px)' }}
        >
          {normalizedScore.toFixed(1)}
        </div>
      </div>
    </div>
  );
}

function EmptyChartState({ label = '暂无可视化数据', heightClassName = 'h-56' }) {
  return (
    <div
      className={`flex ${heightClassName} items-center justify-center rounded-2xl border border-dashed border-slate-300/70 bg-white/50 text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-950/30 dark:text-slate-400`}
    >
      {label}
    </div>
  );
}

function MetricNote({ text }) {
  return (
    <div className="mt-3 inline-flex max-w-full items-start gap-2 rounded-2xl border border-slate-200/80 bg-slate-50/90 px-3 py-2 text-[11px] leading-5 text-slate-500 dark:border-slate-800 dark:bg-slate-950/40 dark:text-slate-300">
      <Database size={13} className="mt-0.5 shrink-0 text-slate-400 dark:text-slate-500" />
      <span>
        <span className="font-semibold text-slate-700 dark:text-slate-100">指标说明：</span>
        {text}
      </span>
    </div>
  );
}

function DrilldownObjectCard({ item }) {
  return (
    <article className="rounded-2xl border border-slate-200/80 bg-white/95 p-4 shadow-[0_8px_20px_rgba(15,23,42,0.05)] dark:border-slate-800 dark:bg-slate-950/30">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">{item?.name || '-'}</div>
          {!!item?.subtitle && <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{item.subtitle}</div>}
        </div>
        <div className="shrink-0 rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          {item?.primary_label || '指标'}
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="text-2xl font-semibold text-slate-900 dark:text-slate-100">
            {formatDrilldownMetricValue(item?.primary_value, item?.primary_unit)}
          </div>
          {!!item?.primary_label && <div className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">{item.primary_label}</div>}
        </div>

        {(item?.secondary_value || item?.secondary_value === 0) && (
          <div className="text-right">
            <div className="text-sm font-medium text-slate-700 dark:text-slate-200">
              {formatDrilldownMetricValue(item?.secondary_value, item?.secondary_unit)}
            </div>
            {!!item?.secondary_label && <div className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">{item.secondary_label}</div>}
          </div>
        )}
      </div>

      {(item?.meta || item?.note) && (
        <div className="mt-4 space-y-1 text-xs leading-5 text-slate-500 dark:text-slate-400">
          {!!item?.meta && <div>{item.meta}</div>}
          {!!item?.note && <div>{item.note}</div>}
        </div>
      )}
    </article>
  );
}

function DecisionDrilldownPanel({
  data,
  loading = false,
  error = '',
  activeGroup = 'customer',
  onGroupChange,
}) {
  const objectGroups = data?.object_groups || {};
  const currentGroup = DRILLDOWN_GROUP_META[activeGroup] ? activeGroup : 'customer';
  const currentItems = Array.isArray(objectGroups?.[currentGroup]) ? objectGroups[currentGroup] : [];
  const context = data?.context || {};

  if (loading) {
    return (
      <section className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-[0_8px_28px_rgba(15,23,42,0.06)] dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-300">
          <RefreshCw size={14} className="animate-spin" />
          正在加载下钻明细...
        </div>
      </section>
    );
  }

  if (error) {
    return (
      <section className="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-300">
        {error}
      </section>
    );
  }

  if (!data) {
    return (
      <section className="rounded-2xl border border-dashed border-slate-300/80 bg-white/70 p-5 text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-400">
        点击上方图表、风险对象或榜单卡片后，这里会展示当前指标对应的客户、SKU、回款项和库存对象明细。
      </section>
    );
  }

  return (
    <section className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-[0_8px_28px_rgba(15,23,42,0.06)] dark:border-slate-800 dark:bg-slate-900">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-cyan-200 bg-cyan-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-cyan-700 dark:border-cyan-900/60 dark:bg-cyan-950/30 dark:text-cyan-300">
            <BarChart3 size={12} />
            Drilldown Workspace
          </div>
          <h2 className="mt-3 text-lg font-semibold text-slate-900 dark:text-slate-100">{data?.title || '经营明细下钻'}</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600 dark:text-slate-300">{data?.metric_description || '暂无指标说明。'}</p>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2 text-[11px]">
        {!!context?.label && (
          <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-slate-600 dark:border-slate-800 dark:bg-slate-950/30 dark:text-slate-300">
            周期: {context.label}
          </span>
        )}
        {!!context?.status && (
          <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-slate-600 dark:border-slate-800 dark:bg-slate-950/30 dark:text-slate-300">
            状态: {formatStatusLabel(context.status)}
          </span>
        )}
        {!!context?.category && (
          <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-slate-600 dark:border-slate-800 dark:bg-slate-950/30 dark:text-slate-300">
            类别: {context.category}
          </span>
        )}
        {!!context?.name && (
          <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-slate-600 dark:border-slate-800 dark:bg-slate-950/30 dark:text-slate-300">
            对象: {context.name}
          </span>
        )}
      </div>

      <div className="mt-5 flex flex-wrap gap-2">
        {Object.entries(DRILLDOWN_GROUP_META).map(([key, meta]) => {
          const Icon = meta.Icon;
          const itemCount = Array.isArray(objectGroups?.[key]) ? objectGroups[key].length : 0;
          const active = currentGroup === key;
          return (
            <button
              key={key}
              type="button"
              onClick={() => onGroupChange?.(key)}
              className={`inline-flex items-center gap-2 rounded-full border px-3 py-2 text-xs font-medium transition-colors ${
                active
                  ? 'border-cyan-300 bg-cyan-50 text-cyan-700 dark:border-cyan-800 dark:bg-cyan-950/40 dark:text-cyan-300'
                  : 'border-slate-200 bg-white text-slate-600 hover:border-cyan-200 hover:text-cyan-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-cyan-900/60 dark:hover:text-cyan-300'
              }`}
            >
              <Icon size={13} />
              {meta.label}
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-500 dark:bg-slate-800 dark:text-slate-300">{itemCount}</span>
            </button>
          );
        })}
      </div>

      <div className="mt-5">
        {currentItems.length ? (
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            {currentItems.map((item, index) => (
              <DrilldownObjectCard key={`${currentGroup}-${item?.id || item?.name || index}`} item={item} />
            ))}
          </div>
        ) : (
          <div className="rounded-2xl border border-dashed border-slate-300/80 bg-slate-50/70 px-4 py-8 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-950/30 dark:text-slate-400">
            {DRILLDOWN_GROUP_META[currentGroup]?.emptyText || '当前维度下暂无关联对象'}
          </div>
        )}
      </div>
    </section>
  );
}

function StatusDonutCard({
  title,
  subtitle,
  items = [],
  palette = BREAKDOWN_COLORS,
  delay = 0,
  activeStatus = '',
  onSelect,
}) {
  const isReady = useEntranceAnimation(delay);
  const isInteractive = typeof onSelect === 'function';
  const radius = 44;
  const stroke = 12;
  const circumference = 2 * Math.PI * radius;

  const normalizedItems = useMemo(() => {
    const source = Array.isArray(items) ? items : [];
    const rows = source
      .map((item, index) => ({
        key: `${item?.status || 'unknown'}-${index}`,
        label: formatStatusLabel(item?.status),
        status: item?.status,
        value: Number(item?.amount || 0),
        count: resolveBreakdownCount(item),
        color: palette[index % palette.length],
      }))
      .filter((item) => item.value > 0 || item.count > 0);

    const total = sumBy(rows, 'value');
    return rows.map((item) => ({
      ...item,
      share: total > 0 ? item.value / total : 0,
    }));
  }, [items, palette]);

  const totalValue = sumBy(normalizedItems, 'value');
  const totalCount = sumBy(normalizedItems, 'count');

  const arcSegments = useMemo(() => {
    let offset = 0;
    return normalizedItems.map((item) => {
      const dash = item.share * circumference;
      const segment = {
        ...item,
        dash,
        offset,
      };
      offset += dash;
      return segment;
    });
  }, [circumference, normalizedItems]);

  if (!normalizedItems.length) {
    return (
      <div className="rounded-2xl border border-slate-200/80 bg-white/90 p-4 dark:border-slate-800 dark:bg-slate-900/80">
        <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">{title}</div>
        <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{subtitle}</div>
        <div className="mt-4">
          <EmptyChartState label={`${title} 暂无数据`} heightClassName="h-52" />
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white/90 p-4 shadow-[0_8px_24px_rgba(15,23,42,0.05)] dark:border-slate-800 dark:bg-slate-900/80">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">{title}</div>
          <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{subtitle}</div>
        </div>
        <div className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          {compactNumberFormatter.format(totalCount)} 条
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-[150px_1fr] sm:items-center">
        <div className="flex justify-center">
          <div className="relative h-36 w-36">
            <svg viewBox="0 0 120 120" className="h-full w-full -rotate-90">
              <circle cx="60" cy="60" r={radius} fill="none" stroke="rgba(148,163,184,0.16)" strokeWidth={stroke} />
              {arcSegments.map((item, index) => (
                <circle
                  key={item.key}
                  cx="60"
                  cy="60"
                  r={radius}
                  fill="none"
                  stroke={item.color}
                  strokeWidth={stroke}
                  strokeLinecap="round"
                  strokeDasharray={`${isReady ? item.dash : 0} ${circumference}`}
                  strokeDashoffset={-item.offset}
                  opacity={activeStatus && activeStatus !== item.status ? 0.28 : 1}
                  onClick={() => onSelect?.(item)}
                  style={{
                    cursor: isInteractive ? 'pointer' : 'default',
                    transition: 'stroke-dasharray 800ms cubic-bezier(0.22,1,0.36,1)',
                    transitionDelay: `${delay + index * 90}ms`,
                  }}
                />
              ))}
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
              <div className="text-[10px] uppercase tracking-[0.16em] text-slate-500">总金额</div>
              <div className="mt-1 text-xl font-semibold text-slate-900 dark:text-slate-100">{formatCompactCurrency(totalValue)}</div>
              <div className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">{compactNumberFormatter.format(totalCount)} 笔记录</div>
            </div>
          </div>
        </div>

        <div className="space-y-2.5">
          {arcSegments.map((item, index) => (
            <button
              key={`${item.key}-legend`}
              type="button"
              onClick={() => onSelect?.(item)}
              className={`block w-full rounded-2xl border px-3 py-2 text-left transition-colors ${
                activeStatus && activeStatus === item.status
                  ? 'border-cyan-200 bg-cyan-50/70 dark:border-cyan-900/60 dark:bg-cyan-950/20'
                  : 'border-transparent hover:border-slate-200 hover:bg-slate-50/70 dark:hover:border-slate-800 dark:hover:bg-slate-950/20'
              } ${isInteractive ? 'cursor-pointer' : 'cursor-default'}`}
            >
              <div className="flex items-center justify-between gap-3 text-xs">
                <span className="inline-flex items-center gap-2 text-slate-700 dark:text-slate-200">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: item.color }} />
                  {item.label}
                </span>
                <span className="text-slate-500 dark:text-slate-400">{(item.share * 100).toFixed(1)}%</span>
              </div>
              <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: isReady ? `${Math.max(item.share * 100, 5)}%` : '0%',
                    backgroundColor: item.color,
                    transition: 'width 800ms cubic-bezier(0.22,1,0.36,1)',
                    transitionDelay: `${delay + index * 90 + 120}ms`,
                  }}
                />
              </div>
              <div className="mt-1 flex items-center justify-between text-[11px] text-slate-500 dark:text-slate-400">
                <span>{formatCompactCurrency(item.value)}</span>
                <span>{compactNumberFormatter.format(item.count)} 笔</span>
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function StatusSegmentsCard({
  title,
  subtitle,
  items = [],
  palette = BREAKDOWN_COLORS,
  delay = 0,
  activeStatus = '',
  onSelect,
}) {
  const isReady = useEntranceAnimation(delay);
  const isInteractive = typeof onSelect === 'function';
  const normalizedItems = useMemo(() => {
    const source = Array.isArray(items) ? items : [];
    const rows = source
      .map((item, index) => ({
        key: `${item?.status || 'unknown'}-${index}`,
        label: formatStatusLabel(item?.status),
        value: Number(item?.amount || 0),
        count: resolveBreakdownCount(item),
        color: palette[index % palette.length],
      }))
      .filter((item) => item.value > 0 || item.count > 0);

    const total = sumBy(rows, 'value');
    return rows.map((item) => ({
      ...item,
      share: total > 0 ? item.value / total : 0,
    }));
  }, [items, palette]);

  if (!normalizedItems.length) {
    return (
      <div className="rounded-2xl border border-slate-200/80 bg-white/90 p-4 dark:border-slate-800 dark:bg-slate-900/80">
        <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">{title}</div>
        <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{subtitle}</div>
        <div className="mt-4">
          <EmptyChartState label={`${title} 暂无数据`} heightClassName="h-52" />
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white/90 p-4 shadow-[0_8px_24px_rgba(15,23,42,0.05)] dark:border-slate-800 dark:bg-slate-900/80">
      <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">{title}</div>
      <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{subtitle}</div>

      <div className="mt-4 overflow-hidden rounded-2xl border border-slate-200/70 bg-slate-50 p-1.5 dark:border-slate-800 dark:bg-slate-950/40">
        <div className="flex h-16 items-stretch gap-1 overflow-hidden rounded-xl">
          {normalizedItems.map((item, index) => (
            <button
              key={`${item.key}-segment`}
              type="button"
              onClick={() => onSelect?.(item)}
              className="relative flex min-w-[64px] flex-1 items-end overflow-hidden rounded-xl p-2 text-left text-white"
              style={{
                background: `linear-gradient(135deg, ${item.color}, ${item.color}CC)`,
                flexBasis: isReady ? `${Math.max(item.share * 100, 14)}%` : '0%',
                opacity: activeStatus && activeStatus !== item.status ? 0.4 : 1,
                cursor: isInteractive ? 'pointer' : 'default',
                transition: 'flex-basis 800ms cubic-bezier(0.22,1,0.36,1)',
                transitionDelay: `${delay + index * 80}ms`,
              }}
            >
              <div className="relative z-10">
                <div className="text-[10px] font-semibold uppercase tracking-[0.14em]">{item.label}</div>
                <div className="mt-1 text-sm font-semibold">{formatCompactCurrency(item.value)}</div>
              </div>
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(255,255,255,0.25),transparent_58%)]" />
            </button>
          ))}
        </div>
      </div>

      <div className="mt-4 space-y-2">
        {normalizedItems.map((item) => (
          <button
            key={`${item.key}-row`}
            type="button"
            onClick={() => onSelect?.(item)}
            className={`flex w-full items-center justify-between gap-3 rounded-xl border px-3 py-2 text-left text-xs transition-colors ${
              activeStatus && activeStatus === item.status
                ? 'border-cyan-200 bg-cyan-50/70 dark:border-cyan-900/60 dark:bg-cyan-950/20'
                : 'border-slate-200/70 hover:border-slate-300 hover:bg-slate-50/70 dark:border-slate-800 dark:hover:border-slate-700 dark:hover:bg-slate-950/20'
            } ${isInteractive ? 'cursor-pointer' : 'cursor-default'}`}
          >
            <span className="inline-flex items-center gap-2 text-slate-700 dark:text-slate-200">
              <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: item.color }} />
              {item.label}
            </span>
            <span className="text-slate-500 dark:text-slate-400">
              {compactNumberFormatter.format(item.count)} 笔 / {(item.share * 100).toFixed(1)}%
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

function RiskHeatGrid({ rows = [], activeCategory = '', onSelect }) {
  const isReady = useEntranceAnimation(160);
  const isInteractive = typeof onSelect === 'function';
  const groups = useMemo(() => {
    const source = Array.isArray(rows) ? rows : [];
    const map = new Map();

    source.forEach((row) => {
      const key = String(row?.category || '未分类').trim() || '未分类';
      const current = map.get(key) || {
        key,
        label: key,
        value: 0,
        count: 0,
        examples: [],
      };

      current.value += Number(row?.value || 0);
      current.count += Number(row?.count || 0);
      if (row?.name && current.examples.length < 2) {
        current.examples.push(String(row.name));
      }
      map.set(key, current);
    });

    const list = Array.from(map.values()).sort((a, b) => b.value - a.value);
    const total = sumBy(list, 'value');
    return list.map((item, index) => ({
      ...item,
      color: RISK_TILE_COLORS[index % RISK_TILE_COLORS.length],
      share: total > 0 ? item.value / total : 0,
    }));
  }, [rows]);

  if (!groups.length) {
    return <EmptyChartState label="暂无风险分类数据" heightClassName="h-48" />;
  }

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      {groups.map((group, index) => (
        <button
          key={group.key}
          type="button"
          onClick={() => onSelect?.(group)}
          className={`relative overflow-hidden rounded-2xl border bg-white/95 p-4 text-left shadow-[0_8px_20px_rgba(15,23,42,0.05)] transition-colors dark:bg-slate-900/90 ${
            activeCategory && activeCategory === group.key
              ? 'border-cyan-300 dark:border-cyan-900/60'
              : 'border-slate-200/80 dark:border-slate-800'
          } ${isInteractive ? 'cursor-pointer hover:border-cyan-200 dark:hover:border-cyan-900/60' : 'cursor-default'}`}
        >
          <div
            className="pointer-events-none absolute inset-0"
            style={{
              background: `radial-gradient(circle at top right, ${group.color}30, transparent 62%)`,
              opacity: isReady ? 1 : 0.25,
              transition: 'opacity 700ms ease',
              transitionDelay: `${index * 80}ms`,
            }}
          />
          <div className="relative z-10">
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">{group.label}</div>
            <div className="mt-2 text-xl font-semibold text-slate-900 dark:text-slate-100">{formatCompactCurrency(group.value)}</div>
            <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{compactNumberFormatter.format(group.count)} 个风险对象</div>
            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
              <div
                className="h-full rounded-full"
                style={{
                  width: isReady ? `${Math.max(group.share * 100, 8)}%` : '0%',
                  backgroundColor: group.color,
                  transition: 'width 800ms cubic-bezier(0.22,1,0.36,1)',
                  transitionDelay: `${index * 90 + 100}ms`,
                }}
              />
            </div>
            <div className="mt-2 text-[11px] leading-5 text-slate-500 dark:text-slate-400">
              {(group.examples || []).length ? group.examples.join(' · ') : '暂无代表对象'}
            </div>
          </div>
        </button>
      ))}
    </div>
  );
}

function CategoryProfitChart({ rows = [], activeCategory = '', onSelect }) {
  const isReady = useEntranceAnimation(180);
  const maxSales = Math.max(1, ...rows.map((row) => Number(row.sales_amount || 0)));

  if (!rows.length) {
    return <EmptyChartState label="暂无品类盈利数据" heightClassName="h-72" />;
  }

  return (
    <div className="space-y-3">
      {rows.map((row, index) => {
        const salesWidth = (Number(row.sales_amount || 0) / maxSales) * 100;
        const costRatio = Number(row.sales_amount || 0) > 0 ? (Number(row.cost_amount || 0) / Number(row.sales_amount || 0)) * 100 : 0;
        const marginValue = Number(row.margin_rate || 0);
        const marginTone =
          marginValue >= 0.35 ? 'bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-300 dark:border-emerald-900/60'
            : marginValue >= 0.2
            ? 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/30 dark:text-amber-300 dark:border-amber-900/60'
            : 'bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/30 dark:text-rose-300 dark:border-rose-900/60';

        return (
          <button
            key={row.category}
            type="button"
            onClick={() => onSelect?.(row)}
            className={`rounded-2xl border bg-white/90 p-4 text-left transition-transform duration-300 hover:-translate-y-0.5 dark:bg-slate-950/30 ${
              activeCategory && activeCategory === row.category
                ? 'border-cyan-300 dark:border-cyan-900/60'
                : 'border-slate-200/80 dark:border-slate-800'
            } ${typeof onSelect === 'function' ? 'cursor-pointer' : 'cursor-default'}`}
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="font-semibold text-slate-900 dark:text-slate-100">{row.category}</div>
                <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">利润 {formatCompactCurrency(row.profit_amount)}</div>
              </div>
              <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${marginTone}`}>
                毛利率 {percentFormatter.format(marginValue)}
              </span>
            </div>

            <div className="mt-3 rounded-full bg-slate-100 p-1 dark:bg-slate-800">
              <div className="relative h-3 overflow-hidden rounded-full bg-slate-200/80 dark:bg-slate-900">
                <div
                  className="absolute inset-y-0 left-0 rounded-full bg-cyan-200/70 dark:bg-cyan-900/40"
                  style={{
                    width: isReady ? `${Math.max(salesWidth, 12)}%` : '0%',
                    transition: 'width 850ms cubic-bezier(0.22,1,0.36,1)',
                    transitionDelay: `${index * 70}ms`,
                  }}
                />
                <div
                  className="absolute inset-y-0 left-0 rounded-full bg-cyan-500/85"
                  style={{
                    width: isReady ? `${Math.max((Math.max(salesWidth, 12) * Math.min(costRatio, 100)) / 100, 6)}%` : '0%',
                    transition: 'width 850ms cubic-bezier(0.22,1,0.36,1)',
                    transitionDelay: `${index * 70 + 90}ms`,
                  }}
                />
              </div>
            </div>

            <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-500 dark:text-slate-400">
              <span>销售 {formatCompactCurrency(row.sales_amount)}</span>
              <span>成本 {formatCompactCurrency(row.cost_amount)}</span>
              <span>利润 {formatCompactCurrency(row.profit_amount)}</span>
            </div>
          </button>
        );
      })}
    </div>
  );
}

function DualLineChart({ rows = [], activeBucket = '', onSelect }) {
  const isReady = useEntranceAnimation(80);
  const containerRef = useRef(null);
  const [hoveredIndex, setHoveredIndex] = useState(null);
  const [chartSize, setChartSize] = useState({ width: 0, height: 0 });
  const isInteractive = typeof onSelect === 'function';

  const width = 800;
  const height = 320;
  const padLeft = 68;
  const padRight = 24;
  const padTop = 20;
  const padBottom = 44;

  const maxValue = Math.max(
    1,
    ...rows.map((item) =>
      Math.max(Number(item.sales_amount || 0), Number(item.purchase_amount || 0), Number(item.net_amount || 0))
    )
  );
  const chartMaxValue = maxValue * 1.12;
  const innerWidth = width - padLeft - padRight;
  const innerHeight = height - padTop - padBottom;

  useEffect(() => {
    const node = containerRef.current;
    if (!node) return undefined;

    const updateSize = () => {
      const nextWidth = node.clientWidth;
      const nextHeight = node.clientHeight;

      setChartSize((current) => {
        if (current.width === nextWidth && current.height === nextHeight) return current;
        return { width: nextWidth, height: nextHeight };
      });
    };

    updateSize();

    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', updateSize);
      return () => window.removeEventListener('resize', updateSize);
    }

    const observer = new ResizeObserver(() => updateSize());
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const xForIndex = (index) => padLeft + (index * innerWidth) / Math.max(rows.length - 1, 1);
  const yForValue = (value) => height - padBottom - (Number(value || 0) / chartMaxValue) * innerHeight;

  const chartPoints = rows.map((item, index) => ({
    index,
    x: xForIndex(index),
    salesY: yForValue(item.sales_amount),
    purchaseY: yForValue(item.purchase_amount),
  }));

  const pathFromSeries = (key) =>
    chartPoints
      .map((point, index) => {
        const y = key === 'sales' ? point.salesY : point.purchaseY;
        return `${index === 0 ? 'M' : 'L'}${point.x},${y}`;
      })
      .join(' ');

  const salesPath = pathFromSeries('sales');
  const purchasePath = pathFromSeries('purchase');
  const yTicks = Array.from({ length: 5 }, (_, index) => (chartMaxValue * (4 - index)) / 4);

  const tickStep = Math.max(1, Math.ceil((rows.length - 1) / 4));
  const xTickIndexes = [];
  for (let index = 0; index < rows.length; index += tickStep) {
    xTickIndexes.push(index);
  }
  if (xTickIndexes[xTickIndexes.length - 1] !== rows.length - 1) {
    xTickIndexes.push(rows.length - 1);
  }

  const activeIndex = hoveredIndex == null ? null : Math.max(0, Math.min(hoveredIndex, rows.length - 1));
  const activeRow = activeIndex == null ? null : rows[activeIndex];
  const activePoint = activeIndex == null ? null : chartPoints[activeIndex];

  const handlePointerMove = useCallback(
    (event) => {
      const rect = event.currentTarget.getBoundingClientRect();
      if (!rect.width) return;

      const rawX = ((event.clientX - rect.left) / rect.width) * width;
      const clampedX = Math.max(padLeft, Math.min(rawX, width - padRight));
      const ratio = (clampedX - padLeft) / Math.max(innerWidth, 1);
      const nextIndex = Math.round(ratio * Math.max(rows.length - 1, 0));
      setHoveredIndex(nextIndex);
    },
    [innerWidth, rows.length]
  );

  const handlePointerLeave = useCallback(() => {
    setHoveredIndex(null);
  }, []);

  if (!rows.length) {
    return <div className="h-56 rounded-2xl border border-dashed border-slate-300/70 bg-white/50" />;
  }

  const tooltipMetrics =
    activePoint && chartSize.width && chartSize.height
      ? (() => {
          const tooltipWidth = 196;
          const tooltipHeight = 108;
          const pointX = (activePoint.x / width) * chartSize.width;
          const pointY = (Math.min(activePoint.salesY, activePoint.purchaseY) / height) * chartSize.height;
          const left =
            pointX > chartSize.width * 0.62
              ? Math.max(12, pointX - tooltipWidth - 18)
              : Math.min(chartSize.width - tooltipWidth - 12, pointX + 18);
          const top = Math.max(12, Math.min(chartSize.height - tooltipHeight - 12, pointY - 18));

          return { left, top };
        })()
      : null;

  return (
    <div
      ref={containerRef}
      className="relative h-72 w-full overflow-hidden rounded-2xl border border-slate-200/70 bg-slate-950/[0.03] dark:border-slate-800"
    >
      {activeRow && tooltipMetrics && (
        <div
          className="pointer-events-none absolute z-10 w-48 rounded-2xl border border-slate-200/90 bg-white/95 p-3 text-xs shadow-[0_18px_40px_rgba(15,23,42,0.18)] backdrop-blur dark:border-slate-700 dark:bg-slate-900/95"
          style={{ left: tooltipMetrics.left, top: tooltipMetrics.top }}
        >
          <div className="font-semibold text-slate-900 dark:text-slate-100">{formatTrendBucketLabel(activeRow, true)}</div>
          <div className="mt-2 space-y-1.5 text-slate-600 dark:text-slate-300">
            <div className="flex items-center justify-between gap-3">
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-sky-500" />
                销售
              </span>
              <span className="font-medium text-slate-900 dark:text-slate-100">{formatCurrency(activeRow.sales_amount)}</span>
            </div>
            <div className="flex items-center justify-between gap-3">
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-orange-500" />
                采购
              </span>
              <span className="font-medium text-slate-900 dark:text-slate-100">{formatCurrency(activeRow.purchase_amount)}</span>
            </div>
            <div className="flex items-center justify-between gap-3 border-t border-slate-200/80 pt-1.5 dark:border-slate-700">
              <span>净额</span>
              <span className="font-semibold text-slate-900 dark:text-slate-100">{formatCurrency(activeRow.net_amount)}</span>
            </div>
          </div>
        </div>
      )}

      <svg viewBox={`0 0 ${width} ${height}`} className="h-full w-full">
        <defs>
          <linearGradient id="decision-sales-fill" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#0ea5e9" stopOpacity="0.18" />
            <stop offset="100%" stopColor="#0ea5e9" stopOpacity="0.02" />
          </linearGradient>
        </defs>

        {yTicks.map((value, index) => {
          const y = yForValue(value);
          return (
            <g key={`y-tick-${index}`}>
              <line x1={padLeft} y1={y} x2={width - padRight} y2={y} stroke="rgba(100,116,139,0.18)" strokeDasharray="4 6" />
              <text x={padLeft - 10} y={y + 4} textAnchor="end" fontSize="11" fill="#64748b">
                {chartNumberFormatter.format(value)}
              </text>
            </g>
          );
        })}

        {xTickIndexes.map((index) => (
          <text
            key={`x-tick-${index}`}
            x={chartPoints[index].x}
            y={height - 14}
            textAnchor="middle"
            fontSize="11"
            fill="#64748b"
          >
            {formatTrendBucketLabel(rows[index], index === 0)}
          </text>
        ))}

        <path
          d={`${salesPath} L${chartPoints[chartPoints.length - 1].x},${height - padBottom} L${chartPoints[0].x},${height - padBottom} Z`}
          fill="url(#decision-sales-fill)"
          opacity={isReady ? 1 : 0}
          style={{ transition: 'opacity 600ms ease' }}
        />
        <path
          d={salesPath}
          fill="none"
          stroke="#0ea5e9"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
          pathLength="1"
          strokeDasharray="1"
          strokeDashoffset={isReady ? 0 : 1}
          opacity={activeBucket && activeRow?.bucket && activeBucket !== activeRow.bucket ? 0.4 : 1}
          style={{ transition: 'stroke-dashoffset 900ms cubic-bezier(0.22,1,0.36,1)' }}
        />
        <path
          d={purchasePath}
          fill="none"
          stroke="#f97316"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
          pathLength="1"
          strokeDasharray="1"
          strokeDashoffset={isReady ? 0 : 1}
          opacity={activeBucket && activeRow?.bucket && activeBucket !== activeRow.bucket ? 0.4 : 1}
          style={{ transition: 'stroke-dashoffset 900ms cubic-bezier(0.22,1,0.36,1)', transitionDelay: '120ms' }}
        />

        {activePoint && (
          <>
            <line
              x1={activePoint.x}
              y1={padTop}
              x2={activePoint.x}
              y2={height - padBottom}
              stroke="rgba(15,23,42,0.35)"
              strokeDasharray="4 5"
            />
            <circle cx={activePoint.x} cy={activePoint.salesY} r="10" fill="rgba(14,165,233,0.14)" />
            <circle cx={activePoint.x} cy={activePoint.salesY} r="5" fill="#0ea5e9" stroke="white" strokeWidth="2" />
            <circle cx={activePoint.x} cy={activePoint.purchaseY} r="10" fill="rgba(249,115,22,0.14)" />
            <circle cx={activePoint.x} cy={activePoint.purchaseY} r="5" fill="#f97316" stroke="white" strokeWidth="2" />
          </>
        )}

        {chartPoints.map((point, index) => (
          <g key={`point-${index}`}>
            <circle
              cx={point.x}
              cy={point.salesY}
              r="3.5"
              fill="#0ea5e9"
              opacity={activeIndex === index ? 0 : (isReady ? 1 : 0)}
              style={{ transition: 'opacity 500ms ease', transitionDelay: `${index * 25}ms` }}
            />
            <circle
              cx={point.x}
              cy={point.purchaseY}
              r="3.5"
              fill="#f97316"
              opacity={activeIndex === index ? 0 : (isReady ? 1 : 0)}
              style={{ transition: 'opacity 500ms ease', transitionDelay: `${index * 25 + 80}ms` }}
            />
          </g>
        ))}

        {rows.map((row, index) => {
          const leftBoundary = index === 0 ? padLeft : (chartPoints[index - 1].x + chartPoints[index].x) / 2;
          const rightBoundary = index === rows.length - 1 ? width - padRight : (chartPoints[index].x + chartPoints[index + 1].x) / 2;
          return (
            <rect
              key={`line-hit-${row.bucket || row.month || index}`}
              x={leftBoundary}
              y={padTop}
              width={Math.max(rightBoundary - leftBoundary, 10)}
              height={innerHeight}
              fill="transparent"
              style={{ cursor: isInteractive ? 'pointer' : 'crosshair' }}
              onPointerEnter={() => setHoveredIndex(index)}
              onPointerMove={handlePointerMove}
              onPointerDown={handlePointerMove}
              onPointerLeave={handlePointerLeave}
              onClick={() => onSelect?.(row)}
            />
          );
        })}
      </svg>
    </div>
  );
}

function DecisionCenterPage() {
  const [dashboardData, setDashboardData] = useState(null);
  const [aiAnalysis, setAiAnalysis] = useState({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false); // data section refresh state
  const [refreshingAi, setRefreshingAi] = useState(false);
  const [exportingPdf, setExportingPdf] = useState(false);
  const [error, setError] = useState('');
  const [backend, setBackend] = useState('cloud');
  const [trendGranularity, setTrendGranularity] = useState('month');
  const [drilldownData, setDrilldownData] = useState(null);
  const [drilldownLoading, setDrilldownLoading] = useState(false);
  const [drilldownError, setDrilldownError] = useState('');
  const [activeObjectGroup, setActiveObjectGroup] = useState('customer');
  const [selectedDrilldownContext, setSelectedDrilldownContext] = useState(null);
  const dataRequestRef = useRef(null);
  const aiRequestRef = useRef(null);
  const drilldownRequestRef = useRef(0);
  const trendGranularityRefreshRef = useRef(new Set());
  const overviewBootstrappedRef = useRef(false);
  const currentAiBackendRef = useRef('cloud');
  const initialBackendRef = useRef(backend);
  const drilldownSectionRef = useRef(null);

  const fetchDataSection = useCallback(async ({ refreshData = false, silent = false } = {}) => {
    if (dataRequestRef.current) return dataRequestRef.current;
    if (!silent) {
      setError('');
      setRefreshing(true);
    }
    const request = (async () => {
      try {
        const payload = await decisionApi.getData({ refreshData });
        setDashboardData(payload || null);
        return payload || null;
      } catch (fetchError) {
        setError(getFriendlyRequestError(fetchError, '数据模块刷新失败'));
        return null;
      } finally {
        dataRequestRef.current = null;
        setRefreshing(false);
      }
    })();
    dataRequestRef.current = request;
    return request;
  }, []);

  const fetchAiSection = useCallback(
    async ({ refreshAi = false, refreshData = false, silent = false } = {}) => {
      if (aiRequestRef.current) return aiRequestRef.current;
      if (!silent) {
        setError('');
        setRefreshingAi(true);
      }
      const request = (async () => {
        try {
          const payload = await decisionApi.getAi({ refreshAi, refreshData, backend });
          setAiAnalysis(payload?.ai_analysis || {});
          currentAiBackendRef.current = backend;
          return payload || null;
        } catch (fetchError) {
          setError(getFriendlyRequestError(fetchError, 'AI分析模块刷新失败'));
          return null;
        } finally {
          aiRequestRef.current = null;
          setRefreshingAi(false);
        }
      })();
      aiRequestRef.current = request;
      return request;
    },
    [backend]
  );

  const loadDrilldown = useCallback(async (params = {}) => {
    const normalizedContext = {
      source: params?.source || '',
      granularity: params?.granularity || 'month',
      bucket: params?.bucket || '',
      status: params?.status || '',
      category: params?.category || '',
      name: params?.name || '',
      limit: params?.limit || 8,
    };

    const requestId = drilldownRequestRef.current + 1;
    drilldownRequestRef.current = requestId;
    setSelectedDrilldownContext(normalizedContext);
    setDrilldownLoading(true);
    setDrilldownError('');

    try {
      const payload = await decisionApi.getDrilldown(normalizedContext);
      if (drilldownRequestRef.current !== requestId) return null;
      setDrilldownData(payload || null);
      setActiveObjectGroup(resolveFirstPopulatedGroup(payload?.object_groups || {}, payload?.default_group || 'customer'));
      window.requestAnimationFrame(() => {
        drilldownSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
      return payload || null;
    } catch (fetchError) {
      if (drilldownRequestRef.current !== requestId) return null;
      setDrilldownError(getFriendlyRequestError(fetchError, '下钻明细加载失败'));
      setDrilldownData(null);
      return null;
    } finally {
      if (drilldownRequestRef.current === requestId) {
        setDrilldownLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    let disposed = false;
    setLoading(true);
    setError('');

    (async () => {
      try {
        const overviewPayload = await decisionApi.getOverview({
          refreshAi: false,
          refreshData: false,
          backend: initialBackendRef.current,
        });
        if (disposed) return;
        setDashboardData(overviewPayload || null);
        setAiAnalysis(overviewPayload?.ai_analysis || {});
        overviewBootstrappedRef.current = true;
        currentAiBackendRef.current = initialBackendRef.current;
        setLoading(false);
      } catch (dataError) {
        if (!disposed) {
          setError(getFriendlyRequestError(dataError, '数据决策面板加载失败'));
          setLoading(false);
        }
      }
    })();

    return () => {
      disposed = true;
    };
  }, []);

  useEffect(() => {
    if (!dashboardData || !overviewBootstrappedRef.current) return;
    if (currentAiBackendRef.current === backend) return;
    void fetchAiSection({ refreshAi: false, refreshData: false, silent: true });
  }, [backend, dashboardData, fetchAiSection]);

  useEffect(() => {
    if (!dashboardData) return undefined;
    let disposed = false;
    let timer = null;
    const schedule = () => {
      timer = window.setTimeout(async () => {
        await fetchDataSection({ refreshData: true, silent: true });
        if (!disposed) schedule();
      }, DATA_AUTO_REFRESH_MS);
    };
    schedule();
    return () => {
      disposed = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [dashboardData, fetchDataSection]);

  useEffect(() => {
    if (!dashboardData) return undefined;
    let disposed = false;
    let timer = null;
    const schedule = () => {
      timer = window.setTimeout(async () => {
        await fetchAiSection({ refreshAi: true, refreshData: false, silent: true });
        if (!disposed) schedule();
      }, AI_AUTO_REFRESH_MS);
    };
    schedule();
    return () => {
      disposed = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [dashboardData, fetchAiSection]);

  const kpis = useMemo(() => (Array.isArray(dashboardData?.kpis) ? dashboardData.kpis : []), [dashboardData?.kpis]);
  const warnings = dashboardData?.warnings || [];
  const aiPending = Boolean(aiAnalysis?.pending);
  const trends = dashboardData?.trends || [];
  const trendsByGranularity = dashboardData?.trends_by_granularity || {};
  const trendGranularityOptions = dashboardData?.trend_granularity_options || [];
  const cockpit = dashboardData?.cockpit || {};
  const cockpitMeta = cockpit?.meta || {};
  const capabilities = cockpit?.capabilities || [];
  const breakdowns = dashboardData?.breakdowns || {};
  const paymentBreakdown = breakdowns?.payment || [];
  const deliveryBreakdown = breakdowns?.delivery || [];
  const purchaseStatusBreakdown = breakdowns?.purchase_status || [];
  const riskTable = dashboardData?.risk_table || [];
  const topProducts = dashboardData?.top_products || [];
  const warehouseRows = dashboardData?.warehouses || [];
  const categoryProfitRows = dashboardData?.category_profit || [];
  const totals = dashboardData?.totals || {};
  const dataCache = dashboardData?.cache || {};
  const preaggregationPending = Boolean(dataCache?.preaggregation_pending_refresh);
  const preaggregationAgeSeconds = Number(dataCache?.preaggregation_age_seconds || 0);
  const aiRiskReasons = aiAnalysis?.risk_reasons || aiAnalysis?.insights || [];
  const aiSuggestedActions = aiAnalysis?.suggested_actions || aiAnalysis?.actions || [];
  const aiEvidenceData = aiAnalysis?.evidence_data || [];
  const selectedGranularityRows = Array.isArray(trendsByGranularity?.[trendGranularity]) ? trendsByGranularity[trendGranularity] : [];
  const hasSelectedGranularityRows = selectedGranularityRows.length > 0;

  const trendRows = useMemo(() => {
    return hasSelectedGranularityRows ? selectedGranularityRows : trends;
  }, [hasSelectedGranularityRows, selectedGranularityRows, trends]);
  const trendWindowLabel = useMemo(() => {
    if (trendGranularity === 'week') return '近12周';
    if (trendGranularity === 'quarter') return '近8季';
    return '近12月';
  }, [trendGranularity]);
  const isTrendGranularityFallback = useMemo(() => {
    return trendGranularity !== 'month' && Boolean(trendRows.length) && !hasSelectedGranularityRows;
  }, [hasSelectedGranularityRows, trendGranularity, trendRows.length]);

  useEffect(() => {
    if (!trendGranularityOptions.length) return;
    const hasCurrent = trendGranularityOptions.some((item) => item?.key === trendGranularity);
    if (!hasCurrent) {
      setTrendGranularity(trendGranularityOptions[0]?.key || 'month');
    }
  }, [trendGranularity, trendGranularityOptions]);

  useEffect(() => {
    if (!dashboardData) return;
    if (trendGranularity === 'month') return;
    if (hasSelectedGranularityRows) return;
    if (!trends.length) return;
    if (refreshing) return;

    const attempted = trendGranularityRefreshRef.current;
    if (attempted.has(trendGranularity)) return;
    attempted.add(trendGranularity);
    void fetchDataSection({ refreshData: true, silent: true });
  }, [dashboardData, fetchDataSection, hasSelectedGranularityRows, refreshing, trendGranularity, trends.length]);

  const displayKpis = useMemo(() => kpis.slice(0, 8), [kpis]);
  const topProductMaxRevenue = useMemo(() => Math.max(1, ...topProducts.map((item) => Number(item.revenue || 0))), [topProducts]);
  const warehouseMaxUnits = useMemo(() => Math.max(1, ...warehouseRows.map((item) => Number(item.units || 0))), [warehouseRows]);
  const warehouseTotalUnits = useMemo(() => sumBy(warehouseRows, 'units'), [warehouseRows]);
  const employeeActiveRate = useMemo(() => {
    const totalEmployees = Number(cockpitMeta?.total_employees || 0);
    if (!totalEmployees) return 0;
    return Number(cockpitMeta?.active_employees || 0) / totalEmployees;
  }, [cockpitMeta?.active_employees, cockpitMeta?.total_employees]);
  const analysisBackendLabel = useMemo(() => (backend === 'cloud' ? '云端模型' : '本地模型'), [backend]);
  const preaggregationText = useMemo(() => {
    if (!dataCache?.preaggregation_enabled) return '实时聚合';
    const minutes = Math.max(0, Math.round(preaggregationAgeSeconds / 60));
    if (preaggregationPending) return `预聚合快照 ${minutes} 分钟前，后台刷新中`;
    return `预聚合快照 ${minutes} 分钟前`;
  }, [dataCache?.preaggregation_enabled, preaggregationAgeSeconds, preaggregationPending]);

  const aiRefreshText = useMemo(() => {
    const seconds = Number(aiAnalysis?.refresh_after_seconds || 0);
    if (seconds <= 0) return '即将自动刷新';
    const minutes = Math.ceil(seconds / 60);
    return `${minutes} 分钟后自动刷新`;
  }, [aiAnalysis]);
  const filteredRiskTable = useMemo(() => {
    if (selectedDrilldownContext?.source !== 'risk') return riskTable;
    return riskTable.filter((row) => {
      const categoryMatched = !selectedDrilldownContext?.category || row?.category === selectedDrilldownContext.category;
      const nameMatched = !selectedDrilldownContext?.name || row?.name === selectedDrilldownContext.name;
      return categoryMatched && nameMatched;
    });
  }, [riskTable, selectedDrilldownContext]);
  const activeRiskCategory = selectedDrilldownContext?.source === 'risk' ? selectedDrilldownContext?.category || '' : '';
  const visualsReady = useEntranceAnimation(60);
  const summaryBadges = useMemo(
    () => [
      {
        label: '近30日销售',
        value: formatCompactCurrency(cockpitMeta?.sales_30d || 0),
      },
      {
        label: '近30日采购',
        value: formatCompactCurrency(cockpitMeta?.purchase_30d || 0),
      },
      {
        label: '库存估值',
        value: formatCompactCurrency(cockpitMeta?.inventory_value || 0),
      },
      {
        label: '员工活跃率',
        value: percentFormatter.format(employeeActiveRate),
      },
    ],
    [cockpitMeta?.inventory_value, cockpitMeta?.purchase_30d, cockpitMeta?.sales_30d, employeeActiveRate]
  );

  useEffect(() => {
    if (!aiPending) return undefined;
    const timer = window.setTimeout(() => {
      void fetchAiSection({ refreshAi: false, refreshData: false, silent: true });
    }, 4000);
    return () => window.clearTimeout(timer);
  }, [aiPending, fetchAiSection]);

  const handleExportPdfReport = useCallback(() => {
    if (!dashboardData) {
      setError('暂无可导出的财政报表数据');
      return;
    }

    const reportWindow = window.open('', '_blank', 'width=1180,height=900');
    if (!reportWindow) {
      setError('浏览器拦截了报表导出窗口，请允许弹出窗口后重试');
      return;
    }

    setError('');
    setExportingPdf(true);

    try {
      const reportHtml = buildDecisionFinancialReportHtml({
        dashboardData,
        aiAnalysis,
        backendLabel: analysisBackendLabel,
      });

      reportWindow.document.open();
      reportWindow.document.write(reportHtml);
      reportWindow.document.close();
    } catch (exportError) {
      reportWindow.close();
      setError(exportError?.message || '财政报表导出失败');
    } finally {
      window.setTimeout(() => setExportingPdf(false), 300);
    }
  }, [aiAnalysis, analysisBackendLabel, dashboardData]);

  if (loading) {
    return (
      <StatePanel
        fullScreen
        tone="slate"
        title="正在加载数据决策系统"
        description="系统正在聚合经营指标、风险预警和 AI 分析结果。"
      />
    );
  }

  if (!dashboardData && error) {
    const permissionDenied = isPermissionDeniedError({ message: error });
    const authRequired = isAuthRequiredError({ message: error });
    return (
      <StatePanel
        fullScreen
        tone={permissionDenied || authRequired ? 'amber' : 'rose'}
        icon={permissionDenied ? 'permission' : authRequired ? 'auth' : 'error'}
        title={
          permissionDenied
            ? '无权限访问决策中心'
            : authRequired
              ? '登录状态已失效'
              : '决策中心加载失败'
        }
        description={error}
        actions={[
          { label: '返回工作台', href: '/' },
          { label: '重新加载', onClick: () => window.location.reload(), primary: true },
        ]}
      />
    );
  }

  if (!dashboardData) {
    return (
      <StatePanel
        fullScreen
        tone="slate"
        icon="empty"
        title="暂无可展示的决策数据"
        description="当前还没有可用于驾驶舱展示的聚合结果。可以稍后刷新，或先返回工作台补充数据来源。"
        actions={[
          { label: '返回工作台', href: '/' },
          { label: '刷新数据', onClick: () => void fetchDataSection({ refreshData: true, silent: false }), primary: true },
        ]}
      />
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
                className="mt-0.5 inline-flex items-center gap-1 whitespace-nowrap rounded-full border border-slate-300/70 dark:border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-white/80 dark:hover:bg-slate-800 transition-colors"
              >
                <ArrowLeft size={14} />
                返回
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
                <option value="cloud">AI 分析: 云端模型</option>
                <option value="local">AI 分析: 本地模型</option>
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

              <button
                type="button"
                onClick={handleExportPdfReport}
                disabled={exportingPdf || !dashboardData}
                className="inline-flex items-center gap-1 rounded-full border border-slate-300 dark:border-slate-700 bg-white/90 dark:bg-slate-900 px-3 py-2 text-xs font-semibold hover:border-sky-500 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
              >
                <Download size={13} className={exportingPdf ? 'animate-pulse' : ''} />
                {exportingPdf ? '正在生成报表' : '导出 PDF 财政报表'}
              </button>

              <div className="inline-flex items-center gap-1 rounded-full border border-slate-300/80 dark:border-slate-700 px-3 py-2 text-xs text-slate-600 dark:text-slate-300 bg-white/65 dark:bg-slate-900/70">
                <Clock3 size={13} />
                数据5分钟，AI30分钟
              </div>
              <div className="inline-flex items-center gap-1 rounded-full border border-slate-300/80 dark:border-slate-700 px-3 py-2 text-xs text-slate-600 dark:text-slate-300 bg-white/65 dark:bg-slate-900/70">
                <Database size={13} />
                {preaggregationText}
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
                className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white/95 dark:bg-slate-900/80 p-4 shadow-[0_8px_28px_rgba(15,23,42,0.06)] transition-transform duration-300 hover:-translate-y-1"
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
                <div className="mt-2 text-[11px] text-slate-500 dark:text-slate-400">
                  目标完成度 {(Number(item.target_progress || 0) * 100).toFixed(0)}%
                </div>
                <div className="mt-3 h-1.5 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                  <div
                    className={`h-full rounded-full ${isPositive ? 'bg-emerald-400' : 'bg-rose-400'}`}
                    style={{
                      width: visualsReady ? `${Math.max(6, Math.min(Number(item.target_progress || 0) * 100, 100))}%` : '0%',
                      transition: 'width 800ms cubic-bezier(0.22,1,0.36,1)',
                    }}
                  />
                </div>
              </article>
            );
          })}
        </section>

        <section className="grid grid-cols-1 xl:grid-cols-[1.18fr_0.92fr] gap-4 items-start">
          <div className="space-y-4">
            <article className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-[0_8px_28px_rgba(15,23,42,0.06)]">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">经营驾驶舱评分</h2>
                  <p className="text-xs text-slate-500 dark:text-slate-400">盈利、运营、供应、库存、财务、增长六维能力协同评分</p>
                </div>
                <div className="inline-flex items-center gap-1 rounded-full bg-slate-100 dark:bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-600 dark:text-slate-300">
                  <BarChart3 size={13} />
                  总评分 {Number(cockpit.score || 0).toFixed(1)}
                </div>
              </div>

              <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-[180px_1fr] lg:items-center">
                <div className="flex justify-center">
                  <ScoreRing score={cockpit.score || 0} />
                </div>

                <div className="space-y-3">
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
                            width: visualsReady ? `${Math.max(4, Math.min(Number(item.score || 0), 100))}%` : '0%',
                            backgroundColor: CAPABILITY_COLORS[index % CAPABILITY_COLORS.length],
                            transition: 'width 800ms cubic-bezier(0.22,1,0.36,1)',
                            transitionDelay: `${index * 70}ms`,
                          }}
                        />
                      </div>
                      <div className="mt-0.5 text-[11px] text-slate-400">{item.desc}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
                {summaryBadges.map((item) => (
                  <div key={item.label} className="rounded-xl border border-slate-200/70 bg-slate-50/80 px-3 py-2 dark:border-slate-800 dark:bg-slate-950/40">
                    <div className="text-[11px] uppercase tracking-[0.12em] text-slate-500">{item.label}</div>
                    <div className="mt-1 text-sm font-semibold text-slate-900 dark:text-slate-100">{item.value}</div>
                  </div>
                ))}
              </div>
            </article>

            <article className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-[0_8px_28px_rgba(15,23,42,0.06)]">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">经营结构拆解</h2>
                  <p className="text-xs text-slate-500 dark:text-slate-400">把回款、履约、采购状态拆成不同图表类型，便于快速识别结构问题</p>
                </div>
                <div className="inline-flex items-center gap-1 rounded-full bg-slate-100 dark:bg-slate-800 px-3 py-1.5 text-[11px] font-medium text-slate-600 dark:text-slate-300">
                  三种可视化
                </div>
              </div>

              <MetricNote text={`${DECISION_METRIC_NOTES.payment} 点击任一分段可直接查看该状态下的对象明细。`} />

              <div className="mt-4 grid grid-cols-1 gap-4 2xl:grid-cols-3">
                <StatusDonutCard
                  title="回款结构"
                  subtitle="按订单金额拆分付款状态"
                  items={paymentBreakdown}
                  palette={['#0ea5e9', '#22c55e', '#f59e0b', '#ef4444']}
                  delay={40}
                  activeStatus={selectedDrilldownContext?.source === 'payment' ? selectedDrilldownContext?.status : ''}
                  onSelect={(item) =>
                    void loadDrilldown({
                      source: 'payment',
                      status: item?.status,
                    })
                  }
                />
                <StatusDonutCard
                  title="履约结构"
                  subtitle="按金额拆分交付状态"
                  items={deliveryBreakdown}
                  palette={['#06b6d4', '#10b981', '#8b5cf6', '#f97316']}
                  delay={120}
                  activeStatus={selectedDrilldownContext?.source === 'delivery' ? selectedDrilldownContext?.status : ''}
                  onSelect={(item) =>
                    void loadDrilldown({
                      source: 'delivery',
                      status: item?.status,
                    })
                  }
                />
                <StatusSegmentsCard
                  title="采购状态"
                  subtitle="在途、处理中与已完成采购的金额构成"
                  items={purchaseStatusBreakdown}
                  palette={['#6366f1', '#8b5cf6', '#14b8a6', '#f59e0b']}
                  delay={180}
                  activeStatus={selectedDrilldownContext?.source === 'purchase' ? selectedDrilldownContext?.status : ''}
                  onSelect={(item) =>
                    void loadDrilldown({
                      source: 'purchase',
                      status: item?.status,
                    })
                  }
                />
              </div>
            </article>
          </div>

          <article className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-[0_8px_28px_rgba(15,23,42,0.06)] xl:sticky xl:top-6">
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

            <div className="mt-3 flex flex-wrap gap-2 text-[11px]">
              <span className="rounded-full border border-cyan-200 bg-cyan-50 px-2.5 py-1 text-cyan-700 dark:border-cyan-900/60 dark:bg-cyan-950/30 dark:text-cyan-300">
                模型: {analysisBackendLabel}
              </span>
              <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-slate-600 dark:border-slate-800 dark:bg-slate-950/30 dark:text-slate-300">
                预警 {warnings.length} 项
              </span>
              <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-slate-600 dark:border-slate-800 dark:bg-slate-950/30 dark:text-slate-300">
                风险订单 {compactNumberFormatter.format(Number(totals.at_risk_orders || 0))}
              </span>
            </div>

            <div className="mt-4 rounded-xl border border-cyan-200/70 dark:border-cyan-900/50 bg-cyan-50/50 dark:bg-cyan-950/20 p-4 text-sm leading-relaxed text-slate-700 dark:text-slate-200">
              <div className="flex items-start gap-3">
                <div className="rounded-xl bg-cyan-100 p-2 text-cyan-700 dark:bg-cyan-950/50 dark:text-cyan-300">
                  <Sparkles size={15} />
                </div>
                <div>
                  <div className="text-xs font-semibold uppercase tracking-[0.12em] text-cyan-700 dark:text-cyan-300">核心结论</div>
                  <div className="mt-2">{aiAnalysis.core_conclusion || aiAnalysis.summary || '暂无 AI 分析结果。'}</div>
                </div>
              </div>
            </div>
            {aiPending && (
              <div className="mt-2 text-xs text-cyan-700 dark:text-cyan-300 inline-flex items-center gap-1">
                <RefreshCw size={12} className="animate-spin" />
                AI分析正在后台生成，结果将自动更新...
              </div>
            )}

            <div className="mt-4 grid grid-cols-1 gap-3">
              <div className="rounded-xl border border-slate-200/70 dark:border-slate-800 p-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
                    <ShieldAlert size={13} />
                    风险原因
                  </div>
                  <div className="text-[11px] text-slate-400">{aiRiskReasons.length} 条</div>
                </div>
                <ul className="mt-2 space-y-1.5 text-sm text-slate-700 dark:text-slate-200">
                  {aiRiskReasons.length ? (
                    aiRiskReasons.map((item, idx) => (
                      <li key={`insight-${idx}`} className="flex gap-2">
                        <span className="mt-[7px] h-1.5 w-1.5 rounded-full bg-rose-500 shrink-0" />
                        <span>{item}</span>
                      </li>
                    ))
                  ) : (
                    <li className="text-sm text-slate-500 dark:text-slate-400">暂无风险原因</li>
                  )}
                </ul>
              </div>

              <div className="rounded-xl border border-slate-200/70 dark:border-slate-800 p-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
                    <TrendingUp size={13} />
                    建议动作
                  </div>
                  <div className="text-[11px] text-slate-400">{aiSuggestedActions.length} 条</div>
                </div>
                <ul className="mt-2 space-y-1.5 text-sm text-slate-700 dark:text-slate-200">
                  {aiSuggestedActions.length ? (
                    aiSuggestedActions.map((item, idx) => (
                      <li key={`action-${idx}`} className="flex gap-2">
                        <span className="mt-[7px] h-1.5 w-1.5 rounded-full bg-emerald-500 shrink-0" />
                        <span>{item}</span>
                      </li>
                    ))
                  ) : (
                    <li className="text-sm text-slate-500 dark:text-slate-400">暂无建议动作</li>
                  )}
                </ul>
              </div>

              <div className="rounded-xl border border-slate-200/70 dark:border-slate-800 p-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
                    <Database size={13} />
                    证据数据
                  </div>
                  <div className="text-[11px] text-slate-400">{aiEvidenceData.length} 项</div>
                </div>
                {aiEvidenceData.length ? (
                  <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
                    {aiEvidenceData.map((item, idx) => (
                      <div key={`evidence-${idx}`} className="rounded-xl border border-slate-200/70 bg-slate-50/80 px-3 py-2 dark:border-slate-800 dark:bg-slate-950/30">
                        <div className="text-[11px] uppercase tracking-[0.12em] text-slate-500">{item?.label || `证据 ${idx + 1}`}</div>
                        <div className="mt-1 text-base font-semibold text-slate-900 dark:text-slate-100">
                          {item?.display_value || formatDrilldownMetricValue(item?.value, item?.unit)}
                        </div>
                        <div className="mt-1 text-[11px] leading-5 text-slate-500 dark:text-slate-400">{item?.description || '暂无说明'}</div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="mt-2 text-sm text-slate-500 dark:text-slate-400">暂无证据数据</div>
                )}
              </div>
            </div>

            <div className="mt-3 rounded-xl border border-slate-200/70 bg-slate-50/80 px-3 py-3 text-xs leading-6 text-slate-600 dark:border-slate-800 dark:bg-slate-950/30 dark:text-slate-300">
              <span className="font-semibold text-slate-800 dark:text-slate-100">风险展望：</span>
              {aiAnalysis.risk_outlook || '暂无'}
            </div>
          </article>
        </section>

        <div ref={drilldownSectionRef}>
          <DecisionDrilldownPanel
            data={drilldownData}
            loading={drilldownLoading}
            error={drilldownError}
            activeGroup={activeObjectGroup}
            onGroupChange={setActiveObjectGroup}
          />
        </div>

        <div className="space-y-4 xl:space-y-0 xl:columns-2 xl:gap-4">
        <section className="grid grid-cols-1 gap-4 xl:contents">
          <article className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-[0_8px_28px_rgba(15,23,42,0.06)] xl:mb-4 xl:break-inside-avoid">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold">销售 vs 采购趋势</h2>
                <p className="text-xs text-slate-500 dark:text-slate-400">{trendWindowLabel}经营趋势，支持按周、按月、按季切换，点击任一周期直接查看对象明细</p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
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
                <div className="flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50/80 p-1 dark:border-slate-800 dark:bg-slate-950/40">
                  {(trendGranularityOptions.length ? trendGranularityOptions : Object.entries(TREND_GRANULARITY_LABELS).map(([key, label]) => ({ key, label }))).map((option) => (
                    <button
                      key={option.key}
                      type="button"
                      onClick={() => setTrendGranularity(option.key)}
                      className={`rounded-full px-3 py-1 text-[11px] font-medium transition-colors ${
                        trendGranularity === option.key
                          ? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
                          : 'text-slate-500 hover:text-slate-900 dark:text-slate-300 dark:hover:text-slate-100'
                      }`}
                    >
                      {option.label || TREND_GRANULARITY_LABELS[option.key] || option.key}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <MetricNote text={`${DECISION_METRIC_NOTES.trend} 当前时间粒度：${TREND_GRANULARITY_LABELS[trendGranularity] || trendGranularity}。`} />
            {isTrendGranularityFallback && (
              <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:border-amber-900/60 dark:bg-amber-950/20 dark:text-amber-300">
                当前仍在显示月度趋势。已尝试刷新数据快照；如果切到该粒度后仍无变化，说明当前后端还没返回对应的周/季聚合数据。
              </div>
            )}

            <div className="mt-4">
              <DualLineChart
                key={trendGranularity}
                rows={trendRows}
                activeBucket={selectedDrilldownContext?.source === 'trend' ? selectedDrilldownContext?.bucket : ''}
                onSelect={(row) =>
                  void loadDrilldown({
                    source: 'trend',
                    granularity: row?.granularity || trendGranularity,
                    bucket: row?.bucket,
                  })
                }
              />
            </div>

            <div className="mt-3 grid grid-cols-3 gap-2 text-[11px] text-slate-500 dark:text-slate-400">
              {trendRows.slice(-3).map((row, index) => (
                <div key={row.bucket || row.month || index} className="rounded-lg bg-slate-50 dark:bg-slate-800/70 px-2 py-1.5">
                  <div>{formatTrendBucketLabel(row, true)}</div>
                  <div className="font-medium text-slate-700 dark:text-slate-200">{formatMetric(row.net_amount, 'CNY')}</div>
                </div>
              ))}
            </div>
          </article>

          <div className="xl:contents">
            <article className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-[0_8px_28px_rgba(15,23,42,0.06)] xl:mb-4 xl:break-inside-avoid">
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
                          <div className="min-w-0">
                            <div className="text-sm font-semibold text-slate-800 dark:text-slate-100 truncate">{item.title}</div>
                            <div className="text-[11px] text-slate-500 dark:text-slate-400">{item.module}</div>
                          </div>
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
          </div>
        </section>

        <section className="grid grid-cols-1 gap-4 xl:contents">
          <article className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-[0_8px_28px_rgba(15,23,42,0.06)] xl:mb-4 xl:break-inside-avoid">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">风险结构热力图</h3>
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">按客户回款、库存缺口、采购积压分类聚合</p>
              </div>
              <div className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                {filteredRiskTable.length}/{riskTable.length} 条明细
              </div>
            </div>

            <MetricNote text={DECISION_METRIC_NOTES.risk} />

            <div className="mt-4">
              <RiskHeatGrid
                rows={riskTable}
                activeCategory={activeRiskCategory}
                onSelect={(group) =>
                  void loadDrilldown({
                    source: 'risk',
                    category: group?.key,
                  })
                }
              />
            </div>
          </article>
        </section>

        <section className="grid grid-cols-1 gap-4 xl:contents">
          <article className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-[0_8px_28px_rgba(15,23,42,0.06)] xl:mb-4 xl:break-inside-avoid">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="text-base font-semibold">Top 商品销售</h3>
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">按近180日销售额排序，补充销量与品类信息</p>
              </div>
              <div className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                Top {Math.min(topProducts.length, 6)}
              </div>
            </div>

            <MetricNote text={`${DECISION_METRIC_NOTES.product} 点击某个商品即可下钻到客户、SKU、回款项和库存对象。`} />

            <div className="mt-4 space-y-3">
              {topProducts.slice(0, 6).map((row, idx) => {
                const width = (Number(row.revenue || 0) / topProductMaxRevenue) * 100;
                return (
                  <button
                    key={`${row.prod_name}-${idx}`}
                    type="button"
                    onClick={() =>
                      void loadDrilldown({
                        source: 'product',
                        name: row?.prod_name,
                      })
                    }
                    className={`rounded-2xl border bg-slate-50/80 p-3 text-left dark:bg-slate-950/30 ${
                      selectedDrilldownContext?.source === 'product' && selectedDrilldownContext?.name === row?.prod_name
                        ? 'border-cyan-300 dark:border-cyan-900/60'
                        : 'border-slate-200/70 dark:border-slate-800'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-slate-900 text-[11px] font-semibold text-white dark:bg-slate-100 dark:text-slate-900">
                            {idx + 1}
                          </span>
                          <span className="truncate font-semibold text-slate-800 dark:text-slate-100">{row.prod_name}</span>
                        </div>
                        <div className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">{row.category || '未分类'} · 销量 {compactNumberFormatter.format(Number(row.sold_units || 0))}</div>
                      </div>
                      <div className="shrink-0 text-right">
                        <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">{formatCompactCurrency(row.revenue)}</div>
                        <div className="text-[11px] text-slate-500 dark:text-slate-400">销售额</div>
                      </div>
                    </div>
                    <div className="mt-3 h-2 rounded-full bg-slate-200/80 dark:bg-slate-800 overflow-hidden">
                      <div
                        className="h-full rounded-full bg-cyan-500"
                        style={{
                          width: visualsReady ? `${Math.max(width, 6)}%` : '0%',
                          transition: 'width 850ms cubic-bezier(0.22,1,0.36,1)',
                          transitionDelay: `${idx * 70}ms`,
                        }}
                      />
                    </div>
                  </button>
                );
              })}
            </div>
          </article>
        </section>

        <section className="grid grid-cols-1 gap-4 xl:contents">
          <article className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-[0_8px_28px_rgba(15,23,42,0.06)] xl:mb-4 xl:break-inside-avoid">
            <h2 className="text-lg font-semibold">品类盈利结构</h2>
            <p className="text-xs text-slate-500 dark:text-slate-400">用销售额、成本额和毛利率的叠层结构看出利润贡献与承压位置</p>

            <MetricNote text={`${DECISION_METRIC_NOTES.category} 点击某个品类可进入对象明细。`} />

            <div className="mt-4">
              <CategoryProfitChart
                rows={categoryProfitRows}
                activeCategory={selectedDrilldownContext?.source === 'category' ? selectedDrilldownContext?.category : ''}
                onSelect={(row) =>
                  void loadDrilldown({
                    source: 'category',
                    category: row?.category,
                  })
                }
              />
            </div>
          </article>

          <article className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-[0_8px_28px_rgba(15,23,42,0.06)] xl:mb-4 xl:break-inside-avoid">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="text-base font-semibold">仓库库存分布</h3>
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">查看库存集中度、仓库体量与明细行数</p>
              </div>
              <div className="text-right">
                <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">{compactNumberFormatter.format(warehouseTotalUnits)}</div>
                <div className="text-[11px] text-slate-500 dark:text-slate-400">总库存件数</div>
              </div>
            </div>

            <MetricNote text={`${DECISION_METRIC_NOTES.warehouse} 点击仓库条目可查看该仓库关联的客户、回款项和库存对象。`} />

            <div className="mt-4 grid grid-cols-2 gap-3">
              <div className="rounded-xl border border-slate-200/70 bg-slate-50/80 px-3 py-2 dark:border-slate-800 dark:bg-slate-950/30">
                <div className="text-[11px] uppercase tracking-[0.12em] text-slate-500">库存估值</div>
                <div className="mt-1 text-sm font-semibold text-slate-900 dark:text-slate-100">{formatCompactCurrency(cockpitMeta.inventory_value || 0)}</div>
              </div>
              <div className="rounded-xl border border-slate-200/70 bg-slate-50/80 px-3 py-2 dark:border-slate-800 dark:bg-slate-950/30">
                <div className="text-[11px] uppercase tracking-[0.12em] text-slate-500">供应活跃度</div>
                <div className="mt-1 text-sm font-semibold text-slate-900 dark:text-slate-100">
                  {compactNumberFormatter.format(Number(totals.active_suppliers_90d || 0))}/{compactNumberFormatter.format(Number(totals.total_suppliers || 0))}
                </div>
              </div>
            </div>

            <div className="mt-4 space-y-3">
              {warehouseRows.map((row, idx) => {
                const width = (Number(row.units || 0) / warehouseMaxUnits) * 100;
                return (
                  <button
                    key={`${row.warehouse}-${idx}`}
                    type="button"
                    onClick={() =>
                      void loadDrilldown({
                        source: 'warehouse',
                        name: row?.warehouse,
                      })
                    }
                    className={`rounded-2xl border bg-slate-50/80 p-3 text-left dark:bg-slate-950/30 ${
                      selectedDrilldownContext?.source === 'warehouse' && selectedDrilldownContext?.name === row?.warehouse
                        ? 'border-cyan-300 dark:border-cyan-900/60'
                        : 'border-slate-200/70 dark:border-slate-800'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3 text-xs">
                      <span className="font-medium text-slate-700 dark:text-slate-200">{row.warehouse}</span>
                      <span className="text-slate-500 dark:text-slate-400">
                        {compactNumberFormatter.format(Number(row.units || 0))} 件 · {compactNumberFormatter.format(Number(row.line_count || 0))} 行
                      </span>
                    </div>
                    <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-200/80 dark:bg-slate-800">
                      <div
                        className="h-full rounded-full bg-emerald-500"
                        style={{
                          width: visualsReady ? `${Math.max(width, 6)}%` : '0%',
                          transition: 'width 850ms cubic-bezier(0.22,1,0.36,1)',
                          transitionDelay: `${idx * 70 + 60}ms`,
                        }}
                      />
                    </div>
                  </button>
                );
              })}
            </div>
          </article>
        </section>

        <section className="grid grid-cols-1 gap-4 xl:contents">
          <article className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-[0_8px_28px_rgba(15,23,42,0.06)] overflow-x-auto xl:mb-4 xl:break-inside-avoid">
            <h2 className="text-lg font-semibold">风险明细</h2>
            <p className="text-xs text-slate-500 dark:text-slate-400">客户回款、库存缺口与采购积压重点对象，点击任一对象会联动热力图和下钻面板</p>

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
                {filteredRiskTable.slice(0, 12).map((row, idx) => (
                  <tr
                    key={`${row.category}-${row.name}-${idx}`}
                    className={`cursor-pointer border-b border-slate-100 transition-colors dark:border-slate-800/70 ${
                      selectedDrilldownContext?.source === 'risk' &&
                      selectedDrilldownContext?.category === row?.category &&
                      (!selectedDrilldownContext?.name || selectedDrilldownContext?.name === row?.name)
                        ? 'bg-cyan-50/70 dark:bg-cyan-950/20'
                        : 'hover:bg-slate-50/70 dark:hover:bg-slate-950/20'
                    }`}
                    onClick={() =>
                      void loadDrilldown({
                        source: 'risk',
                        category: row?.category,
                        name: row?.name,
                      })
                    }
                  >
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

          <article className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-[0_8px_28px_rgba(15,23,42,0.06)] overflow-x-auto xl:mb-4 xl:break-inside-avoid">
            <h2 className="text-lg font-semibold">品类盈利台账</h2>
            <p className="text-xs text-slate-500 dark:text-slate-400">保留明细表，便于进一步人工复核和导出核对</p>

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
          </article>
        </section>
        </div>
      </main>
    </div>
  );
}

export default DecisionCenterPage;
