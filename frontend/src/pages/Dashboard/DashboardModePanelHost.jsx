import React, { Suspense, lazy, memo } from "react";

const ModePanel = lazy(() => import("./ModePanel"));
const DEFAULT_PANEL_STYLE = {
  border: "border-gray-200 dark:border-gray-800",
  headerBg: "bg-gray-50/50 dark:bg-gray-900/20",
  headerText: "text-gray-800 dark:text-gray-300",
  btnBg: "bg-gray-900 hover:bg-black",
  textareaBg: "bg-white/50 dark:bg-gray-900/50",
};

const DashboardModePanelFallback = memo(function DashboardModePanelFallback({
  isAuditSinglePane,
  panelStyle,
}) {
  const safePanelStyle = panelStyle || DEFAULT_PANEL_STYLE;
  return (
    <div
      className={`dashboard-pane w-full ${isAuditSinglePane ? "md:w-full md:border-r-0" : "md:w-1/2 md:border-r"} flex flex-col flex-shrink-0 border-b md:border-b-0 border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 transition-all duration-300 ${safePanelStyle.border} shadow-sm z-20`}
    >
      <div className={`px-4 py-3 border-b flex justify-between items-center ${safePanelStyle.headerBg} ${safePanelStyle.border}`}>
        <div className="h-4 w-40 bg-gray-200 dark:bg-gray-800 rounded animate-pulse"></div>
        <div className="h-3 w-16 bg-gray-200 dark:bg-gray-800 rounded animate-pulse"></div>
      </div>
      <div className="flex-1 p-4">
        <div className="h-5 w-full bg-gray-100 dark:bg-gray-800 rounded animate-pulse"></div>
        <div className="h-5 w-5/6 bg-gray-100 dark:bg-gray-800 rounded animate-pulse mt-3"></div>
        <div className="h-5 w-2/3 bg-gray-100 dark:bg-gray-800 rounded animate-pulse mt-3"></div>
      </div>
    </div>
  );
});

const DashboardModePanelHost = memo(function DashboardModePanelHost(props) {
  if (!props.shouldRenderPanel) {
    return null;
  }

  const { shouldRenderPanel, isAuditSinglePane, panelStyle, ...modePanelProps } = props;

  return (
    <Suspense fallback={<DashboardModePanelFallback isAuditSinglePane={isAuditSinglePane} panelStyle={panelStyle || DEFAULT_PANEL_STYLE} />}>
      <ModePanel panelStyle={panelStyle || DEFAULT_PANEL_STYLE} {...modePanelProps} />
    </Suspense>
  );
});

export default DashboardModePanelHost;
