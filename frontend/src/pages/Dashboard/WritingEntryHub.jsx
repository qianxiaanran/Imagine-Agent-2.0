import React from 'react';
import { ArrowRight, PencilLine, Presentation, Sparkles } from 'lucide-react';

const WritingEntryHub = ({ onOpenAssistant, onOpenPptGenerator }) => (
  <div className="h-full w-full overflow-y-auto bg-gradient-to-br from-gray-100 via-white to-blue-50/40 dark:from-gray-950 dark:via-gray-950 dark:to-gray-900 px-4 py-6 md:px-8 md:py-8">
    <div className="max-w-5xl mx-auto">
      <div className="rounded-3xl border border-gray-200 dark:border-gray-800 bg-white/90 dark:bg-gray-900/85 shadow-sm px-6 py-7 mb-6">
        <div className="inline-flex items-center gap-2 rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700 dark:border-blue-500/40 dark:bg-blue-900/30 dark:text-blue-200">
          <Sparkles size={14} /> 智能创作中心
        </div>
        <h2 className="mt-3 text-2xl font-bold text-gray-900 dark:text-white">请选择一级功能</h2>
        <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">先选择“写作助手”或“PPT生成”，再进入对应的二级配置界面。</p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        <button
          type="button"
          onClick={onOpenAssistant}
          className="rounded-3xl border border-gray-200 dark:border-gray-700 bg-white/95 dark:bg-gray-900/80 p-6 text-left hover:shadow-lg hover:-translate-y-0.5 transition-all"
        >
          <div className="inline-flex rounded-xl border border-gray-200 dark:border-gray-700 p-2.5 text-gray-700 dark:text-gray-300">
            <PencilLine size={20} />
          </div>
          <div className="mt-4 text-xl font-semibold text-gray-900 dark:text-white">写作助手</div>
          <div className="mt-1 text-sm text-gray-500 dark:text-gray-400">营销文案、行业分析、建议咨询等内容生成</div>
          <div className="mt-4 inline-flex items-center gap-1 text-xs font-semibold text-gray-700 dark:text-gray-300">
            进入写作助手 <ArrowRight size={14} />
          </div>
        </button>
        <button
          type="button"
          onClick={onOpenPptGenerator}
          className="rounded-3xl border border-fuchsia-200 dark:border-fuchsia-800/50 bg-white/95 dark:bg-gray-900/80 p-6 text-left hover:shadow-lg hover:-translate-y-0.5 transition-all"
        >
          <div className="inline-flex rounded-xl border border-fuchsia-200 dark:border-fuchsia-800/50 p-2.5 text-fuchsia-700 dark:text-fuchsia-300">
            <Presentation size={20} />
          </div>
          <div className="mt-4 text-xl font-semibold text-gray-900 dark:text-white">PPT生成</div>
          <div className="mt-1 text-sm text-gray-500 dark:text-gray-400">独立PPT生成页，支持进度展示与文件下载</div>
          <div className="mt-4 inline-flex items-center gap-1 text-xs font-semibold text-fuchsia-700 dark:text-fuchsia-300">
            进入PPT生成 <ArrowRight size={14} />
          </div>
        </button>
      </div>
    </div>
  </div>
);

export default WritingEntryHub;
