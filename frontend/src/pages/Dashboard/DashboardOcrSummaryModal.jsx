import React, { Suspense, lazy, memo } from "react";
import { Cpu, Sparkles, X } from "lucide-react";

const MarkdownRenderer = lazy(() => import("./MarkdownRenderer"));

const PlainTextRenderer = ({ content, className = "text-gray-800 dark:text-gray-200" }) => (
  <div className={`whitespace-pre-wrap text-[16px] leading-relaxed ${className}`}>
    {content || ""}
  </div>
);

const DashboardOcrSummaryModal = memo(function DashboardOcrSummaryModal({
  isOpen,
  onClose,
  ocrSummaryFirstDone,
  ocrSummaryBackend,
  backendOptions,
  onBackendChange,
  isLoading,
  onRegenerate,
  scrollRef,
  messages,
  inputValue,
  onInputChange,
  onSend,
}) {
  if (!isOpen) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-[70] bg-black/40 backdrop-blur-[2px] flex items-center justify-center px-4 py-6">
      <div className="w-full max-w-3xl h-[75vh] bg-white dark:bg-gray-900 rounded-2xl shadow-2xl border border-gray-100 dark:border-gray-800 flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 dark:border-gray-800">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-full bg-indigo-50 dark:bg-indigo-900/40 text-indigo-600 dark:text-indigo-300 flex items-center justify-center">
              <Sparkles size={16} />
            </div>
            <div className="text-sm font-semibold text-gray-900 dark:text-white">OCR 总结</div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-full text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800"
            title="关闭"
          >
            <X size={18} />
          </button>
        </div>
        <div className="px-4 py-2 border-b border-gray-100 dark:border-gray-800">
          {ocrSummaryFirstDone ? (
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                <Cpu size={13} />
                <span>总结模型</span>
                <select
                  value={ocrSummaryBackend}
                  onChange={(event) => onBackendChange?.(event.target.value)}
                  disabled={isLoading}
                  className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-2 py-1 text-xs text-gray-700 dark:text-gray-200 outline-none focus:ring-2 focus:ring-indigo-500/20"
                >
                  {backendOptions.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </div>
              <button
                type="button"
                onClick={onRegenerate}
                disabled={isLoading}
                className="px-3 py-1.5 rounded-lg text-xs font-medium border border-indigo-200 dark:border-indigo-700 text-indigo-600 dark:text-indigo-300 hover:bg-indigo-50/80 dark:hover:bg-indigo-900/30 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                重新总结
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
              <Cpu size={13} />
              <span>首次总结默认使用 Qwen 2.5-coder</span>
            </div>
          )}
        </div>
        <div ref={scrollRef} className="flex-1 overflow-auto px-4 py-3 space-y-4">
          {messages.length === 0 && <div className="text-sm text-gray-400">正在生成总结...</div>}
          {messages.map((msg, idx) => (
            <div key={`ocr-summary-${idx}`} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm leading-relaxed ${msg.role === "user" ? "bg-gray-900 text-white" : "bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-100"}`}>
                {msg.role === "assistant" ? (
                  <Suspense fallback={<PlainTextRenderer content={msg.content} className="text-gray-800 dark:text-gray-100" />}>
                    <MarkdownRenderer content={msg.content} streaming={isLoading && idx === messages.length - 1} />
                  </Suspense>
                ) : (
                  msg.content
                )}
              </div>
            </div>
          ))}
          {isLoading && <div className="text-xs text-gray-400">模型正在生成...</div>}
        </div>
        <div className="border-t border-gray-100 dark:border-gray-800 px-4 py-3">
          <div className="flex items-end gap-2">
            <textarea
              className="flex-1 min-h-[44px] max-h-[120px] resize-none rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400"
              placeholder="继续追问文档内容..."
              value={inputValue}
              onChange={(event) => onInputChange?.(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  onSend?.();
                }
              }}
            />
            <button
              type="button"
              onClick={onSend}
              disabled={!String(inputValue || "").trim() || isLoading}
              className="px-4 py-2 rounded-xl bg-indigo-600 text-white text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
            >
              发送
            </button>
          </div>
        </div>
      </div>
    </div>
  );
});

export default DashboardOcrSummaryModal;
