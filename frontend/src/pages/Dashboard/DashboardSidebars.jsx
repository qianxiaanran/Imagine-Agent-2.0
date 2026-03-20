import React, { Suspense, lazy, memo } from "react";

const Sidebar = lazy(() => import("./Sidebar"));
const MobileSidebar = lazy(() => import("./MobileSidebar"));

const DashboardSidebars = memo(function DashboardSidebars({
  isMobileSidebarOpen,
  onCloseMobileSidebar,
  isSidebarOpen,
  onCloseSidebar,
  userProfile,
  sessionList,
  currentSessionId,
  onSessionClick,
  onNewChat,
  onLogout,
  onShowAppearance,
  currentMode,
  onModeChange,
  isProfileLoading,
  isSessionsLoading,
  selectedModel,
}) {
  return (
    <>
      <Suspense fallback={null}>
        <MobileSidebar
          isOpen={isMobileSidebarOpen}
          onClose={onCloseMobileSidebar}
          userProfile={userProfile}
          sessionList={sessionList}
          currentSessionId={currentSessionId}
          onSessionClick={onSessionClick}
          onNewChat={onNewChat}
          onLogout={onLogout}
          onShowAppearance={onShowAppearance}
          currentMode={currentMode}
          onModeChange={onModeChange}
          isLoading={isProfileLoading || isSessionsLoading}
          selectedModel={selectedModel}
        />
      </Suspense>

      <Suspense fallback={<div className="hidden md:block w-[280px] shrink-0 border-r border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-950" />}>
        <Sidebar
          isOpen={isSidebarOpen}
          onClose={onCloseSidebar}
          onNewChat={onNewChat}
          sessionList={sessionList}
          currentSessionId={currentSessionId}
          onSessionClick={onSessionClick}
          userProfile={userProfile}
          onLogout={onLogout}
          onShowAppearance={onShowAppearance}
          currentMode={currentMode}
          onModeChange={onModeChange}
          isLoadingSessions={isSessionsLoading}
          isLoadingProfile={isProfileLoading}
          selectedModel={selectedModel}
        />
      </Suspense>
    </>
  );
});

export default DashboardSidebars;
