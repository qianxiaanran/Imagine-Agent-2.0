import React, { memo, useMemo } from "react";
import {
  Sparkles,
  Building2,
  ClipboardList,
  ShieldCheck,
  Users,
  Search,
  Database,
  FileText,
} from "lucide-react";

/**
 * Suggestions（建议卡片）
 *
 * ✅ 只在“通用企业问答”显示：
 *    - general / chat / qa / enterprise_qa ...
 *    - database  （数据库查询）
 *    - documents （文档分析 / RAG）
 *
 * Props:
 * - mode?: string
 * - onSuggestionClick?: (text: string) => void
 * - className?: string
 * - disabled?: boolean
 * - showHeader?: boolean
 * - generalModes?: string[]   // 允许显示建议的 mode 列表
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

  // ✅ 非通用企业问答模式：不显示
  if (!isGeneralEnterpriseQA) return null;

  const suggestions = useMemo(() => {
    if (Array.isArray(overrideSuggestions) && overrideSuggestions.length > 0) {
      return overrideSuggestions;
    }
    // ——通用问答（适用于 general/chat/qa）
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

    // ——数据库查询（适用于 database）
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

    // ——文档分析（适用于 documents）
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

    // ✅ 根据 mode 做“更相关”的建议集合（避免在 database 里出现太多闲聊建议）
    if (normalizedMode === "database") return [...db];
    if (normalizedMode === "documents") return [...docs];

    // general/chat/qa：给通用问答 + 也给一点点入口提示（可选）
    return [...common, ...db.slice(0, 1), ...docs.slice(0, 1)];
  }, [normalizedMode, overrideSuggestions]);

  const visibleSuggestions = useMemo(() => {
    if (typeof limit === "number") {
      return suggestions.slice(0, Math.max(0, limit));
    }
    return suggestions;
  }, [suggestions, limit]);

  const headerTitle =
    normalizedMode === "database"
      ? "试试这些数据库查询"
      : normalizedMode === "documents"
      ? "试试这些文档分析"
      : "试试这些企业问答";

  return (
    <div className={`w-full ${className}`}>
      {showHeader && (
        <div className="px-4 mb-3 flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-gray-600 dark:text-gray-300" />
          <div className="text-sm font-semibold text-gray-800 dark:text-gray-100">
            {headerTitle}
          </div>
          <div className="text-xs text-gray-500 dark:text-gray-400">
            点击即可填入输入框
          </div>
        </div>
      )}

      <div className="w-full grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-2 gap-3 px-4">
        {visibleSuggestions.map((s) => {
          const Icon = s.Icon || Sparkles;

          return (
            <button
              key={s.key}
              type="button"
              disabled={disabled}
              onClick={() => !disabled && onSuggestionClick?.(s.text)}
              className={[
                "group relative text-left w-full",
                "flex items-start gap-4",
                "p-4 rounded-2xl",
                "backdrop-blur-md",
                "bg-white/70 dark:bg-white/5",
                "border border-white/40 dark:border-white/10",
                "shadow-sm hover:shadow-md",
                "transition-all duration-200",
                "focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-0",
                "focus-visible:ring-gray-900/15 dark:focus-visible:ring-white/20",
                "hover:bg-white/85 dark:hover:bg-white/10",
                disabled ? "opacity-60 cursor-not-allowed" : "cursor-pointer",
              ].join(" ")}
              aria-label={`建议：${s.title}`}
            >
              <div
                className={[
                  "shrink-0 mt-0.5",
                  "w-10 h-10 rounded-xl",
                  "flex items-center justify-center",
                  "bg-gray-900/5 dark:bg-white/10",
                  "border border-gray-900/5 dark:border-white/10",
                  "transition-transform duration-200",
                  "group-hover:scale-[1.03]",
                ].join(" ")}
              >
                <Icon className="w-5 h-5 text-gray-700 dark:text-gray-200" />
              </div>

              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold text-gray-900 dark:text-white leading-snug">
                  {s.title}
                </div>
                <div className="mt-1 text-xs text-gray-600 dark:text-gray-300 leading-relaxed line-clamp-2">
                  {s.text}
                </div>
              </div>

              <div className="pointer-events-none absolute inset-0 rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                <div className="absolute -top-10 -right-10 w-28 h-28 rounded-full blur-2xl bg-gray-900/5 dark:bg-white/10" />
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
});

export default Suggestions;
