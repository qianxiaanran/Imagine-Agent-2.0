import React, { memo } from "react";
import { Bot, FileText, FileUp, Image as ImageIcon } from "lucide-react";

const DashboardGlobalOverlays = memo(function DashboardGlobalOverlays({
  isDragActive,
  showOnboarding,
  onboardingMessages,
  onStartOnboarding,
}) {
  return (
    <>
      {isDragActive && (
        <div className="pointer-events-none fixed inset-0 z-[130] flex items-center justify-center bg-black/55 backdrop-blur-[2px] animate-in fade-in duration-150">
          <div className="relative flex flex-col items-center px-8 py-10 rounded-3xl border border-blue-300/25 bg-[#121826]/85 shadow-[0_30px_80px_rgba(0,0,0,0.55)]">
            <div className="relative h-24 w-28 mb-4">
              <div className="absolute left-1 top-3 w-12 h-12 rounded-2xl bg-indigo-300/95 text-indigo-900 flex items-center justify-center rotate-[-14deg] shadow-lg">
                <FileText size={20} />
              </div>
              <div className="absolute right-1 top-5 w-12 h-12 rounded-2xl bg-blue-300/95 text-blue-900 flex items-center justify-center rotate-[14deg] shadow-lg">
                <ImageIcon size={20} />
              </div>
              <div className="absolute left-1/2 -translate-x-1/2 bottom-0 w-14 h-14 rounded-2xl bg-blue-600 text-white flex items-center justify-center shadow-xl animate-pulse">
                <FileUp size={24} />
              </div>
            </div>
            <div className="text-3xl font-bold text-white tracking-tight">添加任意内容</div>
            <div className="mt-2 text-base text-blue-100/90">将文件拖放到此处，松手即可添加到对话中</div>
          </div>
        </div>
      )}

      {showOnboarding && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/30 backdrop-blur-[2px] px-4">
          <div className="w-full max-w-xl rounded-2xl border border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900 shadow-2xl p-5 sm:p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-9 h-9 rounded-full bg-green-500 text-white flex items-center justify-center">
                <Bot size={18} />
              </div>
              <div>
                <div className="text-sm font-semibold text-gray-900 dark:text-white">快速上手</div>
                <div className="text-xs text-gray-500 dark:text-gray-400">入口位置一眼看懂</div>
              </div>
            </div>
            <div className="space-y-3">
              {onboardingMessages.map((msg, idx) => (
                <div key={`onboarding-${idx}`} className="rounded-xl border border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/60 px-4 py-3 text-sm text-gray-700 dark:text-gray-200 leading-relaxed">
                  {msg}
                </div>
              ))}
            </div>
            <div className="mt-4 text-right">
              <a
                href="#"
                onClick={onStartOnboarding}
                className="text-sm font-medium text-blue-600 hover:text-blue-700 hover:underline"
              >
                立即开始
              </a>
            </div>
          </div>
        </div>
      )}
    </>
  );
});

export default DashboardGlobalOverlays;
