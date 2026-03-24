import React, { memo } from "react";
import { ArrowRight, Check, ChevronDown, Clock3, Layout, PanelLeftOpen, Plus, Share2 } from "lucide-react";

const ModelMenu = memo(function ModelMenu({
  models,
  selectedModel,
  onSelectModel,
  onOpenDecisionCenter,
  onGotoTaskCenter,
  mobile = false,
}) {
  return (
    <div
      className={`dashboard-dropdown absolute top-full left-0 mt-2 ${mobile ? "w-[min(88vw,280px)] max-h-[65vh] overflow-y-auto" : "w-[320px]"} bg-white dark:bg-gray-800 rounded-xl shadow-xl border border-gray-100 dark:border-gray-700 ${mobile ? "" : "overflow-hidden"} animate-in fade-in slide-in-from-top-2 duration-200 z-50`}
    >
      <div className="p-1.5 space-y-0.5">
        {models.map((model) => (
          <div
            key={model.id}
            className={`flex items-center gap-3 px-3 py-3 rounded-lg cursor-pointer transition-colors ${selectedModel === model.id ? "bg-gray-100 dark:bg-gray-700" : "hover:bg-gray-50 dark:hover:bg-gray-700/50"}`}
            onClick={() => onSelectModel?.(model.id)}
          >
            <div
              className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${selectedModel === model.id ? "bg-black dark:bg-white text-white dark:text-black" : "bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300"}`}
            >
              <model.icon size={18} />
            </div>
            <div className="flex-1">
              <div className={`text-sm font-medium ${selectedModel === model.id ? "text-gray-900 dark:text-white" : "text-gray-700 dark:text-gray-300"}`}>
                {model.name}
              </div>
            </div>
            {selectedModel === model.id && <Check size={16} className="text-gray-900 dark:text-white" />}
          </div>
        ))}
        <div className="my-1 h-px bg-gray-100 dark:bg-gray-700" />
        <button
          type="button"
          onClick={onOpenDecisionCenter}
          className="w-full flex items-center gap-3 px-3 py-3 rounded-lg hover:bg-cyan-50 dark:hover:bg-cyan-900/20 transition-colors text-left"
        >
          <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 bg-cyan-100 dark:bg-cyan-900/40 text-cyan-600 dark:text-cyan-300">
            <Layout size={18} />
          </div>
          <div className="flex-1">
          <div className="text-sm font-medium text-cyan-700 dark:text-cyan-300">数据决策系统</div>
          </div>
          <ArrowRight size={16} className="text-cyan-500" />
        </button>
        <button
          type="button"
          onClick={onGotoTaskCenter}
          className="w-full flex items-center gap-3 px-3 py-3 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-700/60 transition-colors text-left"
        >
          <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300">
            <Clock3 size={18} />
          </div>
          <div className="flex-1">
            <div className="text-sm font-medium text-slate-700 dark:text-slate-200">任务中心</div>
          </div>
          <ArrowRight size={16} className="text-slate-400" />
        </button>
      </div>
    </div>
  );
});

const DashboardTopbar = memo(function DashboardTopbar({
  isSidebarOpen,
  onOpenSidebar,
  onOpenMobileSidebar,
  models,
  selectedModel,
  selectedModelInfo,
  isDropdownOpen,
  onToggleDropdown,
  onSelectDesktopModel,
  isMobileModelDropdownOpen,
  onToggleMobileModelDropdown,
  onSelectMobileModel,
  onOpenDecisionCenter,
  onOpenTaskCenter,
  onGotoTaskCenter,
  isTaskCenterOpen = false,
  currentSessionId,
  onShareClick,
  onNewChat,
  dropdownRef,
  mobileDropdownRef,
}) {
  return (
    <>
      <div className="dashboard-topbar md:hidden fixed top-0 left-0 right-0 flex items-center justify-between px-4 py-3 bg-white/95 dark:bg-gray-950/95 backdrop-blur-sm border-b border-gray-100 dark:border-gray-800 z-40">
        <div className="flex items-center gap-3">
          <button onClick={onOpenMobileSidebar} className="text-gray-600 dark:text-gray-300 p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-md transition-colors">
            <PanelLeftOpen size={24} />
          </button>
          <div className="relative" ref={mobileDropdownRef}>
            <button onClick={onToggleMobileModelDropdown} className="flex items-center gap-1.5 font-bold text-gray-800 dark:text-white text-lg active:opacity-70 transition-opacity">
              {selectedModelInfo?.name?.split(" ")[0]}
              <span className="text-xs font-normal text-gray-500 bg-gray-100 dark:bg-gray-800 dark:text-gray-400 px-1.5 py-0.5 rounded-full">2.0</span>
              <ChevronDown size={16} className={`text-gray-400 transition-transform duration-200 ${isMobileModelDropdownOpen ? "rotate-180" : ""}`} />
            </button>
            {isMobileModelDropdownOpen && (
              <ModelMenu
                mobile
                models={models}
                selectedModel={selectedModel}
                onSelectModel={onSelectMobileModel}
                onOpenDecisionCenter={onOpenDecisionCenter}
                onGotoTaskCenter={onGotoTaskCenter}
              />
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={onOpenTaskCenter}
            className={`p-1 rounded-md transition-colors ${
              isTaskCenterOpen
                ? "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-100"
                : "text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800"
            }`}
          >
            <Clock3 size={24} />
          </button>
          {currentSessionId && (
            <button onClick={onShareClick} className="text-gray-600 dark:text-gray-300 p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-md transition-colors">
              <Share2 size={24} />
            </button>
          )}
          <button onClick={onNewChat} className="text-gray-600 dark:text-gray-300 p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-md transition-colors">
            <Plus size={24} />
          </button>
        </div>
      </div>

      <div className="dashboard-topbar hidden md:flex items-center p-3 sticky top-0 z-30 bg-white/80 dark:bg-gray-950/80 backdrop-blur-sm border-b border-gray-100 dark:border-gray-800/50">
        <div className="flex items-center">
          {!isSidebarOpen && (
            <button onClick={onOpenSidebar} className="mr-3 p-2 text-gray-500 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors">
              <PanelLeftOpen size={20} />
            </button>
          )}
          <div className="relative" ref={dropdownRef}>
            <button className="flex items-center gap-2 px-3 py-2 rounded-xl hover:bg-gray-100/80 dark:hover:bg-gray-800/80 transition-colors text-lg font-semibold text-gray-700 dark:text-gray-200 group" onClick={onToggleDropdown}>
              {selectedModelInfo?.name?.split(" ")[0]}
              <span className="text-gray-400 text-base font-normal">2.0</span>
              <ChevronDown size={16} className={`text-gray-400 transition-transform duration-200 ${isDropdownOpen ? "rotate-180" : ""}`} />
            </button>
            {isDropdownOpen && (
              <ModelMenu
                models={models}
                selectedModel={selectedModel}
                onSelectModel={onSelectDesktopModel}
                onOpenDecisionCenter={onOpenDecisionCenter}
                onGotoTaskCenter={onGotoTaskCenter}
              />
            )}
          </div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={onOpenTaskCenter}
            className={`p-2 rounded-lg transition-colors flex items-center gap-2 ${
              isTaskCenterOpen
                ? "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-100"
                : "text-gray-500 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800"
            }`}
          >
            <Clock3 size={20} />
            <span className="text-sm font-medium hidden lg:inline">任务中心</span>
          </button>
          {currentSessionId && (
            <button onClick={onShareClick} className="p-2 text-gray-500 hover:text-blue-600 dark:hover:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg transition-colors flex items-center gap-2">
              <Share2 size={20} />
              <span className="text-sm font-medium hidden lg:inline">分享</span>
            </button>
          )}
        </div>
      </div>
    </>
  );
});

export default DashboardTopbar;
