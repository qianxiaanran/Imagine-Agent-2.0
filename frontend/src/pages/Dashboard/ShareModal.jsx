import React, { useMemo, useState } from 'react';
import {
  Check,
  Clock,
  Copy,
  ExternalLink,
  Globe,
  Loader2,
  Share2,
  ShieldAlert,
  X,
} from 'lucide-react';

import shareApi from '../../api/share';
import { copyTextToClipboard, shareWithSystem } from '../../utils/browserActions';
import { getFriendlyRequestError } from '../../utils/requestErrors';

const EXPIRY_OPTIONS = [1, 7, 30];

const ShareModal = ({ isOpen, onClose, sessionId, userId, sessionTitle }) => {
  const [step, setStep] = useState('config');
  const [days, setDays] = useState(7);
  const [isLoading, setIsLoading] = useState(false);
  const [isSharing, setIsSharing] = useState(false);
  const [shareUrl, setShareUrl] = useState('');
  const [isCopied, setIsCopied] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [noticeMessage, setNoticeMessage] = useState('');

  const nativeShareSupported = typeof navigator !== 'undefined' && typeof navigator.share === 'function';
  const safeTitle = String(sessionTitle || '未命名会话').trim() || '未命名会话';
  const canCreate = Boolean(String(sessionId || '').trim() && String(userId || '').trim() && userId !== 'anonymous');
  const sharePayload = useMemo(() => ({
    title: safeTitle,
    text: `与你分享会话：${safeTitle}`,
    url: shareUrl,
  }), [safeTitle, shareUrl]);

  if (!isOpen) return null;

  const resetLocalState = () => {
    setStep('config');
    setDays(7);
    setShareUrl('');
    setIsCopied(false);
    setErrorMessage('');
    setNoticeMessage('');
    setIsSharing(false);
    setIsLoading(false);
  };

  const handleCreateShare = async () => {
    if (!canCreate) {
      setErrorMessage('当前会话尚未保存，或登录状态无效，暂时无法生成分享链接。');
      return;
    }

    setIsLoading(true);
    setErrorMessage('');
    setNoticeMessage('');
    try {
      const res = await shareApi.createShare(sessionId, userId, {
        title: safeTitle,
        days,
      });

      if (!res?.success || !res?.token) {
        throw new Error(res?.error || '创建分享失败');
      }

      const origin = window.location.origin;
      setShareUrl(`${origin}/share/${res.token}`);
      setStep('result');
      setNoticeMessage(`分享链接已生成，可在 ${days} 天内访问。`);
    } catch (error) {
      setErrorMessage(getFriendlyRequestError(error, '创建分享失败，请稍后重试。'));
    } finally {
      setIsLoading(false);
    }
  };

  const handleCopy = async () => {
    if (!shareUrl) return;
    setErrorMessage('');
    try {
      await copyTextToClipboard(shareUrl);
      setIsCopied(true);
      setNoticeMessage('分享链接已复制。');
      window.setTimeout(() => setIsCopied(false), 2000);
    } catch (error) {
      setErrorMessage(getFriendlyRequestError(error, '复制失败，请手动复制链接。'));
    }
  };

  const handleNativeShare = async () => {
    if (!shareUrl || !nativeShareSupported) return;
    setIsSharing(true);
    setErrorMessage('');
    try {
      await shareWithSystem(sharePayload);
      setNoticeMessage('已调用系统分享面板。');
    } catch (error) {
      if (String(error?.name || '') !== 'AbortError') {
        setErrorMessage(getFriendlyRequestError(error, '系统分享失败，请改用复制链接。'));
      }
    } finally {
      setIsSharing(false);
    }
  };

  const handleOpenShareLink = () => {
    if (!shareUrl) return;
    window.open(shareUrl, '_blank', 'noopener,noreferrer');
  };

  const handleClose = () => {
    resetLocalState();
    onClose?.();
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-white dark:bg-gray-800 w-full max-w-md rounded-2xl shadow-2xl border border-gray-100 dark:border-gray-700 overflow-hidden animate-in zoom-in-95 duration-200 flex max-h-[min(92vh,760px)] flex-col">
        <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-700 flex justify-between items-center bg-gray-50/50 dark:bg-gray-900/50">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
            <Share2 size={20} className="text-blue-500" />
            分享聊天记录
          </h3>
          <button onClick={handleClose} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors">
            <X size={20} />
          </button>
        </div>

        <div className="p-6 overflow-y-auto">
          <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-4 dark:border-slate-700 dark:bg-slate-900/60">
            <div className="text-xs uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">当前会话</div>
            <div className="mt-2 text-sm font-semibold text-slate-900 dark:text-white break-all">{safeTitle}</div>
          </div>

          {step === 'config' ? (
            <div className="mt-5 space-y-6">
              <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-xl border border-blue-100 dark:border-blue-800 flex gap-3">
                <Globe className="text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5" size={20} />
                <div>
                  <h4 className="text-sm font-medium text-blue-800 dark:text-blue-200 mb-1">公开访问链接</h4>
                  <p className="text-xs text-blue-600 dark:text-blue-300 leading-relaxed">
                    分享的是当前会话的静态快照，生成后不会随聊天继续更新。适合发给同事做查看和汇报。
                  </p>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-2">
                  <Clock size={16} /> 选择有效期
                </label>
                <div className="grid grid-cols-3 gap-3">
                  {EXPIRY_OPTIONS.map((value) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setDays(value)}
                      className={`py-2 px-3 rounded-lg text-sm font-medium border transition-all ${
                        days === value
                          ? 'bg-blue-600 text-white border-blue-600 shadow-md'
                          : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200 border-gray-200 dark:border-gray-600 hover:border-blue-400'
                      }`}
                    >
                      {value} 天
                    </button>
                  ))}
                </div>
                <div className="mt-2 flex items-center gap-2 text-xs text-gray-400">
                  <ShieldAlert size={12} />
                  <span>链接过期后将自动失效，无法继续访问。</span>
                </div>
              </div>

              {!canCreate ? (
                <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700 dark:border-amber-900/60 dark:bg-amber-950/20 dark:text-amber-300">
                  当前会话还没有可分享的有效快照。请先保存或发起一次会话，再生成分享链接。
                </div>
              ) : null}
            </div>
          ) : (
            <div className="mt-5 space-y-5 py-1">
              <div className="w-16 h-16 bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400 rounded-full flex items-center justify-center mx-auto">
                <Check size={32} />
              </div>
              <div className="text-center">
                <h4 className="text-xl font-bold text-gray-900 dark:text-white">链接已生成</h4>
                <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">复制链接或直接调起系统分享即可发给同事。</p>
              </div>

              <div className="relative">
                <textarea
                  readOnly
                  value={shareUrl}
                  rows={3}
                  className="w-full resize-none rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 pr-12 text-sm text-gray-700 focus:outline-none dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200"
                />
                <button
                  type="button"
                  onClick={handleCopy}
                  className="absolute right-2 top-3 p-1.5 hover:bg-gray-200 dark:hover:bg-gray-800 rounded-lg text-gray-500 transition-colors"
                  title="复制链接"
                >
                  {isCopied ? <Check size={18} className="text-green-500" /> : <Copy size={18} />}
                </button>
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <button
                  type="button"
                  onClick={handleCopy}
                  className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-700 transition hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
                >
                  <Copy size={16} />
                  复制链接
                </button>
                <button
                  type="button"
                  onClick={handleOpenShareLink}
                  className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-700 transition hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
                >
                  <ExternalLink size={16} />
                  预览分享页
                </button>
                {nativeShareSupported ? (
                  <button
                    type="button"
                    onClick={handleNativeShare}
                    disabled={isSharing}
                    className="inline-flex items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60 sm:col-span-2"
                  >
                    {isSharing ? <Loader2 size={16} className="animate-spin" /> : <Share2 size={16} />}
                    {isSharing ? '正在调起系统分享' : '系统分享'}
                  </button>
                ) : null}
              </div>
            </div>
          )}

          {errorMessage ? (
            <div className="mt-5 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/20 dark:text-rose-300">
              {errorMessage}
            </div>
          ) : null}

          {!errorMessage && noticeMessage ? (
            <div className="mt-5 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700 dark:border-emerald-900/60 dark:bg-emerald-950/20 dark:text-emerald-300">
              {noticeMessage}
            </div>
          ) : null}
        </div>

        <div className="px-6 py-4 bg-gray-50 dark:bg-gray-900/50 border-t border-gray-100 dark:border-gray-700 flex justify-end gap-3">
          {step === 'config' ? (
            <>
              <button onClick={handleClose} className="px-4 py-2 text-sm font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors">
                取消
              </button>
              <button
                onClick={handleCreateShare}
                disabled={isLoading || !canCreate}
                className="px-6 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm disabled:opacity-70 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {isLoading ? <Loader2 size={14} className="animate-spin" /> : null}
                {isLoading ? '生成中' : '生成链接'}
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                onClick={() => {
                  setStep('config');
                  setErrorMessage('');
                  setNoticeMessage('');
                  setIsCopied(false);
                }}
                className="px-4 py-2 text-sm font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
              >
                重新生成
              </button>
              <button onClick={handleClose} className="px-6 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm">
                完成
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default ShareModal;
