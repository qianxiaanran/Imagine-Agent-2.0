import React, { useState } from 'react';
import { Share2, X, Copy, Check, Clock, Globe, ShieldAlert, FileText } from 'lucide-react';
import shareApi from "../../api/share";


const ShareModal = ({ isOpen, onClose, sessionId, userId, sessionTitle }) => {
  const [step, setStep] = useState('config'); // 'config' | 'result'
  const [days, setDays] = useState(7);
  const [isLoading, setIsLoading] = useState(false);
  const [shareUrl, setShareUrl] = useState('');
  const [isCopied, setIsCopied] = useState(false);

  if (!isOpen) return null;

  const handleCreateShare = async () => {
    setIsLoading(true);
    try {
      const res = await shareApi.createShare(sessionId, userId, {
        title: sessionTitle,
        days: days
      });

      if (res.success && res.token) {
        // 构建完整的 URL
        const origin = window.location.origin;
        setShareUrl(`${origin}/share/${res.token}`);
        setStep('result');
      } else {
        alert('创建分享失败: ' + (res.error || '未知错误'));
      }
    } catch (e) {
      console.error(e);
      alert('网络请求失败');
    } finally {
      setIsLoading(false);
    }
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(shareUrl).then(() => {
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), 2000);
    });
  };


  const handleClose = () => {
    setStep('config');
    setShareUrl('');
    setIsCopied(false);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-white dark:bg-gray-800 w-full max-w-md rounded-2xl shadow-2xl border border-gray-100 dark:border-gray-700 overflow-hidden animate-in zoom-in-95 duration-200 flex flex-col">

        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-700 flex justify-between items-center bg-gray-50/50 dark:bg-gray-900/50">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <Share2 size={20} className="text-blue-500" />
            分享聊天记录
          </h3>
          <button onClick={handleClose} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors">
            <X size={20} />
          </button>
        </div>

        {/* Body */}
        <div className="p-6">
          {step === 'config' ? (
            <div className="space-y-6">
              <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-xl border border-blue-100 dark:border-blue-800 flex gap-3">
                <Globe className="text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5" size={20} />
                <div>
                  <h4 className="text-sm font-medium text-blue-800 dark:text-blue-200 mb-1">公开访问链接</h4>
                  <p className="text-xs text-blue-600 dark:text-blue-300 leading-relaxed">
                    任何获得此链接的人都可以查看当前聊天记录的<strong>静态快照</strong>。生成的链接不会随后续聊天更新。
                  </p>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-2">
                  <Clock size={16} /> 选择有效期
                </label>
                <div className="grid grid-cols-3 gap-3">
                  {[1, 7, 30].map(d => (
                    <button
                      key={d}
                      onClick={() => setDays(d)}
                      className={`py-2 px-3 rounded-lg text-sm font-medium border transition-all
                        ${days === d
                          ? 'bg-blue-600 text-white border-blue-600 shadow-md'
                          : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200 border-gray-200 dark:border-gray-600 hover:border-blue-400'
                        }`}
                    >
                      {d} 天
                    </button>
                  ))}
                </div>
                <div className="mt-2 flex items-center gap-2 text-xs text-gray-400">
                    <ShieldAlert size={12} />
                    <span>链接过期后将自动失效，无法访问。</span>
                </div>
              </div>
            </div>
          ) : (
            <div className="space-y-6 text-center py-2">
              <div className="w-16 h-16 bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400 rounded-full flex items-center justify-center mx-auto mb-4">
                <Check size={32} />
              </div>
              <div>
                <h4 className="text-xl font-bold text-gray-900 dark:text-white mb-2">链接已生成！</h4>
                <p className="text-sm text-gray-500">快去分享给你的同事或朋友吧</p>
              </div>

              <div className="relative">
                <input
                  type="text"
                  readOnly
                  value={shareUrl}
                  className="w-full pl-4 pr-12 py-3 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl text-sm text-gray-600 dark:text-gray-300 focus:outline-none"
                />
                <button
                  onClick={handleCopy}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 hover:bg-gray-200 dark:hover:bg-gray-800 rounded-lg text-gray-500 transition-colors"
                  title="复制"
                >
                  {isCopied ? <Check size={18} className="text-green-500" /> : <Copy size={18} />}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 bg-gray-50 dark:bg-gray-900/50 border-t border-gray-100 dark:border-gray-700 flex justify-end gap-3">
          {step === 'config' ? (
            <>
              <button onClick={handleClose} className="px-4 py-2 text-sm font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors">
                取消
              </button>
              <button
                onClick={handleCreateShare}
                disabled={isLoading}
                className="px-6 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm disabled:opacity-70 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {isLoading && <span className="animate-spin rounded-full h-3 w-3 border-2 border-white border-t-transparent"></span>}
                生成链接
              </button>
            </>
          ) : (
             <button onClick={handleClose} className="px-6 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm">
                完成
             </button>
          )}
        </div>

      </div>
    </div>
  );
};

export default ShareModal;