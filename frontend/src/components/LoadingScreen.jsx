import React, { useEffect, useState } from 'react';
import { Bot } from 'lucide-react';

const LoadingScreen = ({ text = "正在启动智能办公空间...", isVisible = true }) => {
  const [shouldRender, setShouldRender] = useState(true);

  // 监听 isVisible 变化，处理淡出动画
  useEffect(() => {
    if (!isVisible) {
      // 延迟卸载：等待 CSS transition (700ms) 完成后再从 DOM 中移除
      const timer = setTimeout(() => {
        setShouldRender(false);
      }, 800);
      return () => clearTimeout(timer);
    } else {
      setShouldRender(true);
    }
  }, [isVisible]);

  if (!shouldRender) return null;

  return (
    <>
      <style>{`
        .loading-wrapper-fixed {
          position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
          display: flex; flex-direction: column; align-items: center; justify-content: center;
          background-color: #ffffff; z-index: 9999; overflow: hidden;
          /* 🚀 关键优化：添加 opacity 和 visibility 的过渡动画 */
          transition: opacity 0.7s ease-out, visibility 0.7s;
        }
        .dark .loading-wrapper-fixed { background-color: #030712; }

        /* 当 isVisible 为 false 时应用此样式 */
        .loading-fade-out {
            opacity: 0;
            visibility: hidden;
            pointer-events: none;
        }

        @keyframes loading-bar { 0% { transform: translateX(-100%); width: 20%; } 50% { width: 40%; } 100% { transform: translateX(300%); width: 20%; } }
        .animate-loading-bar { animation: loading-bar 1.5s ease-in-out infinite; }
      `}</style>

      <div className={`loading-wrapper-fixed text-gray-900 dark:text-white ${!isVisible ? 'loading-fade-out' : ''}`}>
        <div className="relative flex flex-col items-center animate-in fade-in duration-1000">
          <div className="relative w-24 h-24 mb-10">
            <div className="absolute inset-0 bg-blue-100 dark:bg-blue-900 rounded-3xl blur-2xl opacity-60 animate-pulse-soft"></div>
            <div className="relative w-full h-full bg-white dark:bg-gray-900 rounded-3xl shadow-[0_20px_50px_rgba(0,0,0,0.05)] border border-gray-100 dark:border-gray-800 flex items-center justify-center z-10 animate-float">
                <Bot size={42} className="text-gray-900 dark:text-white" strokeWidth={1.5} />
                <div className="absolute top-0 right-0 -mt-1 -mr-1">
                  <span className="relative flex h-3.5 w-3.5">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-3.5 w-3.5 bg-green-500 border-[2.5px] border-white dark:border-gray-900"></span>
                  </span>
                </div>
            </div>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-white mb-6 font-sans">Enterprise Agent</h1>
          <div className="flex flex-col items-center gap-4 w-64">
            <div className="w-full h-[3px] bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden relative">
                <div className="absolute inset-y-0 left-0 bg-gray-900 dark:bg-white rounded-full animate-loading-bar"></div>
            </div>
            <p className="text-xs text-gray-400 font-medium tracking-wider uppercase flex items-center gap-2">{text}</p>
          </div>
        </div>
        <div className="absolute bottom-12 text-[10px] text-gray-300 dark:text-gray-600 font-mono tracking-widest uppercase">Powered by LLM & RAG Engine</div>
      </div>
    </>
  );
};

export default LoadingScreen;