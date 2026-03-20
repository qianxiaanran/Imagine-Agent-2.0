import React, { Suspense, lazy, memo } from "react";
import { BookOpen, FileText, Image as ImageIcon, Play, Sparkles } from "lucide-react";

const Suggestions = lazy(() => import("./Suggestions"));

const MOBILE_QUICK_ACTIONS = [
  { key: "image", label: "公司/业务介绍", prompt: "用数据库查询一下公司的基本信息（专业语气）", Icon: ImageIcon },
  { key: "video", label: "流程怎么走", prompt: "请用步骤说明：合同审批流程通常包含哪些节点？每个节点的输入输出是什么？", Icon: Play },
  { key: "write", label: "合规与风险提示", prompt: "帮我列一份“对外合同”常见风险点清单，并给出对应的规避建议（条款层面）", Icon: FileText },
  { key: "learn", label: "数据库：客户TOP统计", prompt: "查询订单金额TOP10客户，并按客户汇总（订单数/总额/最近下单日期）", Icon: BookOpen },
  { key: "energy", label: "HR/行政制度问答", prompt: "请给一个通用的“请假/报销/出差”制度说明模板，要求清晰可执行", Icon: Sparkles },
];

const DashboardEmptyState = memo(function DashboardEmptyState({
  isMobileViewport,
  greetingText,
  selectedModelInfo,
  isMeetingMode,
  isAuditMode,
  isOCRMode,
  onQuickAction,
  onSuggestionClick,
}) {
  if (isMobileViewport) {
    return (
      <div className="w-full -mx-4 px-6 flex flex-col justify-start pt-4 pb-2">
        <div>
          <div className="home-hero-kicker text-base text-gray-500 dark:text-gray-400">{greetingText}</div>
          <h2 className="home-hero-title mt-2 text-[26px] leading-tight text-gray-900 dark:text-white">
            需要我为你做些什么？
          </h2>
        </div>
        <div className="mt-6 flex flex-col gap-3">
          {MOBILE_QUICK_ACTIONS.map((action) => {
            const ActionIcon = action.Icon;
            return (
              <button
                key={action.key}
                type="button"
                onClick={() => onQuickAction?.(action.prompt)}
                className="w-fit max-w-[85%] inline-flex items-center gap-2 px-4 py-2.5 rounded-full bg-white/90 dark:bg-gray-900/60 border border-gray-200/80 dark:border-gray-700 text-sm font-medium text-gray-700 dark:text-gray-200 shadow-sm hover:shadow-md hover:bg-white dark:hover:bg-gray-900 transition-all"
              >
                <ActionIcon size={16} className="text-gray-500 dark:text-gray-400" />
                {action.label}
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col items-center justify-center pt-4 sm:pt-5">
      <div className="w-16 h-16 bg-white dark:bg-gray-800 rounded-full shadow-sm border border-gray-100 dark:border-gray-700 flex items-center justify-center mb-6">
        {selectedModelInfo?.icon
          ? React.createElement(selectedModelInfo.icon, { size: 32, className: "text-gray-800 dark:text-white" })
          : null}
      </div>
      <h2 className="home-hero-title text-2xl text-gray-800 dark:text-white mb-8 text-center px-4">
        {isMeetingMode
          ? "上传录音，一键总结"
          : isAuditMode
            ? "智能审单 & 风险合规检测"
            : isOCRMode
              ? "图片/PDF 转文字 & 智能分析"
              : "今天有什么计划？"}
      </h2>
      <Suspense fallback={<div className="text-sm text-gray-400 dark:text-gray-500">加载建议中...</div>}>
        <Suggestions onSuggestionClick={onSuggestionClick} />
      </Suspense>
    </div>
  );
});

export default DashboardEmptyState;
