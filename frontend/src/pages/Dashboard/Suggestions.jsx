import React, { memo } from "react";
import {
  Sparkles,
  Building2,
  ClipboardList,
  ShieldCheck,
  Users,
  Search,
  Database,
  FileText,
  ArrowUpRight,
} from "lucide-react";

/**
 * Suggestions（建议卡片）
 *
 * ✅ 只在“通用企业问答”显示：
 *    - `general/chat/qa/enterprise_qa` 等
 *    - database  （数据库查询）
 *    - documents （文档分析 / RAG）
 *
 * 组件参数：
 * - mode：模式字符串
 * - onSuggestionClick：点击建议时的回调
 * - className：外层容器样式类名
 * - disabled：是否禁用点击
 * - showHeader：是否展示头部标题
 * - generalModes?: string[]   // 允许显示建议的模式列表
 */
const Suggestions = memo(function Suggestions({
  mode = "general",
  onSuggestionClick,
  className = "",
  disabled = false,
  showHeader = true,
  limit,
  overrideSuggestions,
  generalModes = [
    "general",
    "chat",
    "qa",
    "enterprise_qa",
    "enterprise",
    "common",
    "database",
    "documents",
  ],
}) {
  const normalizedMode = String(mode || "").toLowerCase();
  const isGeneralEnterpriseQA = generalModes.includes(normalizedMode);
  const common = [
    {
      key: "intro_company",
      title: "公司/业务介绍",
      text: "用数据库查询一下公司的基本信息（专业语气）",
      Icon: Building2,
    },
    {
      key: "process",
      title: "流程怎么走",
      text: "请用步骤说明：合同审批流程通常包含哪些节点？每个节点的输入输出是什么？",
      Icon: ClipboardList,
    },
    {
      key: "compliance",
      title: "合规与风险提示",
      text: "帮我列一份“对外合同”常见风险点清单，并给出对应的规避建议（条款层面）",
      Icon: ShieldCheck,
    },
    {
      key: "hr",
      title: "HR/行政制度问答",
      text: "请给一个通用的“请假/报销/出差”制度说明模板，要求清晰可执行",
      Icon: Users,
    },
  ];

  const db = [
    {
      key: "db_top_customers",
      title: "数据库：客户TOP统计",
      text: "查询销售订单金额TOP10客户，并按客户汇总（订单数/总额/最近下单日期）",
      Icon: Database,
    },
    {
      key: "db_sales_summary",
      title: "数据库：月度销售汇总",
      text: "统计近6个月每月销售额、订单数、客单价，并指出异常波动的月份及可能原因",
      Icon: Database,
    },
  ];

  const docs = [
    {
      key: "doc_terms",
      title: "文档：条款定位与解释",
      text: "从我上传的合同/制度中定位“付款条款/交付周期/违约责任”的原文，并用通俗话解释",
      Icon: FileText,
    },
    {
      key: "doc_compare",
      title: "文档：总结提取",
      text: "总结我上传的文档",
      Icon: Search,
    },
  ];

  const suggestionPool =
    Array.isArray(overrideSuggestions) && overrideSuggestions.length > 0
      ? overrideSuggestions
      : normalizedMode === "database"
        ? db
        : normalizedMode === "documents"
          ? docs
          : [...common, ...db.slice(0, 1), ...docs.slice(0, 1)];

  const visibleSuggestions =
    typeof limit === "number"
      ? suggestionPool.slice(0, Math.max(0, limit))
      : suggestionPool;

  if (!isGeneralEnterpriseQA) return null;

  const headerTitle =
    normalizedMode === "database"
      ? "试试这些数据库查询"
      : normalizedMode === "documents"
      ? "试试这些文档分析"
      : "试试这些企业问答";

  return (
    <div className={`w-full ${className}`}>
      {showHeader && (
        <div className="px-4 mb-4 flex items-center gap-2.5">
          <span className="inline-flex w-6 h-6 items-center justify-center rounded-full bg-white/85 dark:bg-white/10 border border-white/80 dark:border-white/15 shadow-sm">
            <Sparkles className="w-3.5 h-3.5 text-gray-700 dark:text-gray-200" />
          </span>
          <div className="text-sm font-semibold text-gray-800 dark:text-gray-100">
            {headerTitle}
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400/90">
            点击即可填入输入框
          </div>
        </div>
      )}

      <div className="w-full grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-2 gap-3.5 px-4">
        {visibleSuggestions.map((s) => {
          const Icon = s.Icon || Sparkles;

          return (
            <button
              key={s.key}
              type="button"
              disabled={disabled}
              onClick={() => !disabled && onSuggestionClick?.(s.text)}
              className={[
                "group relative text-left w-full overflow-hidden",
                "flex items-start gap-4",
                "p-4 rounded-[24px]",
                "backdrop-blur-xl",
                "bg-white/75 dark:bg-white/[0.06]",
                "border border-white/70 dark:border-white/12",
                "shadow-[0_10px_28px_-18px_rgba(15,23,42,0.5)] dark:shadow-[0_12px_28px_-18px_rgba(0,0,0,0.8)]",
                "transition-[transform,box-shadow,background-color,border-color] duration-300",
                "focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-0",
                "focus-visible:ring-gray-900/15 dark:focus-visible:ring-white/20",
                "hover:-translate-y-0.5",
                "hover:bg-white/90 dark:hover:bg-white/[0.09]",
                "hover:border-white/90 dark:hover:border-white/20",
                "hover:shadow-[0_20px_45px_-26px_rgba(15,23,42,0.7)] dark:hover:shadow-[0_22px_50px_-24px_rgba(0,0,0,0.9)]",
                "active:scale-[0.99]",
                disabled ? "opacity-60 cursor-not-allowed" : "cursor-pointer",
              ].join(" ")}
              aria-label={`建议：${s.title}`}
            >
              <div
                className={[
                  "shrink-0 mt-0.5",
                  "w-11 h-11 rounded-2xl",
                  "flex items-center justify-center",
                  "bg-gradient-to-br from-white/95 to-white/60 dark:from-white/18 dark:to-white/[0.05]",
                  "border border-white/85 dark:border-white/12",
                  "shadow-[inset_0_1px_0_rgba(255,255,255,0.85)] dark:shadow-[inset_0_1px_0_rgba(255,255,255,0.15)]",
                  "transition-transform duration-200",
                  "group-hover:scale-[1.05]",
                ].join(" ")}
              >
                <Icon className="w-5 h-5 text-gray-700 dark:text-gray-100" />
              </div>

              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold text-gray-900 dark:text-white leading-snug">
                  {s.title}
                </div>
                <div className="mt-1 text-[12.5px] text-gray-600 dark:text-gray-300 leading-relaxed line-clamp-2">
                  {s.text}
                </div>
              </div>

              <div className="pointer-events-none absolute right-3 top-3 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                <span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-white/90 dark:bg-white/10 border border-white/80 dark:border-white/15">
                  <ArrowUpRight className="w-3.5 h-3.5 text-gray-500 dark:text-gray-300" />
                </span>
              </div>

              <div className="pointer-events-none absolute inset-0 rounded-[24px] opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                <div className="absolute inset-x-10 -top-10 h-16 rounded-full blur-2xl bg-white/40 dark:bg-white/12" />
                <div className="absolute -bottom-12 -right-8 w-32 h-32 rounded-full blur-3xl bg-cyan-400/10 dark:bg-cyan-300/10" />
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
});

export default Suggestions;
