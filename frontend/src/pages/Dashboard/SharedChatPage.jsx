import React, { useEffect, useState, Suspense, lazy } from 'react';
import { Bot, User, Clock, FileText } from 'lucide-react';
import shareApi from '../../api/share';
import StatePanel from '../../components/StatePanel';
import { getFriendlyRequestError, isPermissionDeniedError } from '../../utils/requestErrors';

const MarkdownRenderer = lazy(() => import('./MarkdownRenderer'));
const SourcePanel = lazy(() => import('./SourcePanel'));

const CONTEXT_LABELS = {
  voice_context: '会议纪要/转写',
  ocr_context: '文档识别结果',
  audit_context: '智能审单记录',
  context_save: '内容记录'
};

const isLikelyJson = (value = '') => {
  const text = String(value || '').trim();
  return (text.startsWith('{') && text.endsWith('}')) || (text.startsWith('[') && text.endsWith(']'));
};

const normalizeContextContent = (raw) => {
  if (raw === null || raw === undefined) return { text: '', isJson: false };
  if (typeof raw !== 'string') return { text: String(raw), isJson: false };
  const trimmed = raw.trim();
  if (!trimmed) return { text: '', isJson: false };
  if (!isLikelyJson(trimmed)) return { text: raw, isJson: false };
  try {
    const parsed = JSON.parse(trimmed);
    const extracted =
      (typeof parsed?.text === 'string' && parsed.text) ||
      (typeof parsed?.data?.text === 'string' && parsed.data.text) ||
      (typeof parsed?.result?.text === 'string' && parsed.result.text);
    if (extracted && extracted.trim()) {
      return { text: extracted, isJson: false };
    }
    return { text: JSON.stringify(parsed, null, 2), isJson: true };
  } catch {
    return { text: raw, isJson: false };
  }
};

const SharedChatPage = () => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);
  const [expandedContexts, setExpandedContexts] = useState({});

  useEffect(() => {
    const pathParts = window.location.pathname.split('/');
    const token = pathParts[pathParts.length - 1];

    if (!token) {
      setError("无效的分享链接");
      setLoading(false);
      return;
    }

    const fetchData = async () => {
      try {
        const res = await shareApi.getSharedContent(token);
        if (res.success) {
          setData(res.data);
        } else {
          setError(res.error || "内容无法访问或已过期");
        }
      } catch (fetchError) {
        setError(getFriendlyRequestError(fetchError, "无法加载分享内容"));
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  if (loading) {
    return (
      <StatePanel
        fullScreen
        tone="slate"
        title="正在获取分享内容"
        description="请稍候，系统正在加载已分享的静态快照。"
      />
    );
  }

  if (error) {
    return (
      <StatePanel
        fullScreen
        tone={isPermissionDeniedError({ message: error }) ? 'amber' : 'rose'}
        icon="error"
        title="分享内容暂不可访问"
        description={error}
        actions={[{ label: '返回主页', href: '/', primary: true }]}
      />
    );
  }

  if (!Array.isArray(data?.messages) || data.messages.length === 0) {
    return (
      <StatePanel
        fullScreen
        tone="slate"
        icon="empty"
        title="这条分享还没有内容"
        description="该分享链接对应的会话快照中没有可展示的消息，可能是分享生成时尚未产生有效内容。"
        actions={[{ label: '返回主页', href: '/', primary: true }]}
      />
    );
  }

  return (
    /* 核心修复：添加 h-screen 和 overflow-y-auto 确保容器可滚动 */
    <div
      className="overflow-y-auto bg-white dark:bg-gray-950 font-sans scroll-smooth"
      style={{ height: 'var(--app-height, 100vh)' }}
    >
      {/* Header - 使用 sticky 保持在顶部 */}
      <div
        className="sticky top-0 z-20 bg-white/90 dark:bg-gray-950/90 backdrop-blur-md border-b border-gray-100 dark:border-gray-800 px-4"
        style={{ paddingTop: 'calc(env(safe-area-inset-top) + 12px)', paddingBottom: '12px' }}
      >
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold text-gray-900 dark:text-white truncate max-w-[150px] sm:max-w-md">
              {data.title || '未命名会话'}
            </h1>
            <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
               <Clock size={12} />
               <span>生成于 {new Date(data.snapshot_at).toLocaleDateString()}</span>
               <span className="hidden sm:inline-block bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-300 px-1.5 py-0.5 rounded text-[10px]">静态快照</span>
            </div>
          </div>
          <a href="/" className="px-3 py-1.5 sm:px-4 sm:py-2 bg-black dark:bg-white text-white dark:text-black text-sm font-medium rounded-lg hover:opacity-90 transition-opacity whitespace-nowrap">
            我也要用
          </a>
        </div>
      </div>

      {/* Content Area */}
      <div className="max-w-3xl mx-auto px-4 py-8">
        <div className="flex flex-col gap-6">
          {data.messages.map((msg, idx) => {
            // 忽略非展示角色
            if (msg.role === 'system' || msg.role === 'meta') return null;

            // 上下文提示
            if (msg.role === 'context') {
               const label = CONTEXT_LABELS[msg.func_type] || '上下文内容';
               const { text, isJson } = normalizeContextContent(msg.content);
               const isExpanded = expandedContexts[idx] !== undefined ? expandedContexts[idx] : true;
               return (
                   <div key={idx} className="flex justify-center">
                     <div className="bg-gray-50 dark:bg-gray-900 border border-gray-100 dark:border-gray-800 rounded-xl p-3 w-full max-w-3xl text-xs text-gray-600 dark:text-gray-300">
                       <div className="flex items-center gap-2">
                         <FileText size={14} className="flex-shrink-0 text-gray-400" />
                         <span className="font-medium text-gray-700 dark:text-gray-200">{label}</span>
                         <button
                           onClick={() => setExpandedContexts((prev) => ({ ...prev, [idx]: !isExpanded }))}
                           className="ml-auto text-[11px] text-blue-600 dark:text-blue-300 hover:underline"
                         >
                           {isExpanded ? '收起' : '展开'}
                         </button>
                       </div>
                       {isExpanded && (
                         <div className="mt-2 rounded-lg border border-gray-100 dark:border-gray-800 bg-white/60 dark:bg-gray-950/40 p-3">
                           {text ? (
                             isJson ? (
                               <pre className="whitespace-pre-wrap text-[12px] leading-relaxed text-gray-600 dark:text-gray-300">
                                 {text}
                               </pre>
                             ) : (
                               <Suspense fallback={<div className="text-xs text-gray-400">Loading...</div>}>
                                 <MarkdownRenderer content={text} />
                               </Suspense>
                             )
                           ) : (
                             <div className="text-[12px] text-gray-400">暂无内容</div>
                           )}
                         </div>
                       )}
                     </div>
                   </div>
               )
            }

            const isUser = msg.role === 'user';

            return (
              <div key={idx} className={`flex gap-3 sm:gap-4 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
                {/* 头像 */}
                <div className={`w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center border border-gray-100 dark:border-gray-700 ${isUser ? 'bg-white dark:bg-gray-800' : 'bg-green-600 text-white'}`}>
                  {isUser ? <User size={16} className="text-gray-600 dark:text-gray-300"/> : <Bot size={16} />}
                </div>

                {/* 气泡 */}
                <div className={`py-2.5 px-4 rounded-2xl max-w-[85%] sm:max-w-[80%] break-words leading-relaxed text-[15px] shadow-sm ${
                  isUser
                  ? 'bg-blue-600 text-white rounded-tr-none whitespace-pre-wrap'
                  : 'bg-gray-100 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 text-gray-800 dark:text-gray-200 rounded-tl-none'
                }`}>
                  {isUser ? (
                    msg.content
                  ) : (
                    <div className="w-full min-w-0">
                      <Suspense fallback={<div className="text-xs text-gray-400">Loading...</div>}>
                        <MarkdownRenderer content={msg.content || ''} />
                      </Suspense>
                      {Array.isArray(msg.sources) && msg.sources.length > 0 ? (
                        <Suspense fallback={<div className="mt-2 text-xs text-gray-400">加载来源...</div>}>
                          <SourcePanel sources={msg.sources} />
                        </Suspense>
                      ) : null}
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>

        {/* 底部间距防止被遮挡 */}
        <div className="h-24"></div>
      </div>

      {/* 底部版权或提示（可选） */}
      <div className="py-8 text-center text-gray-400 text-xs border-t border-gray-50 dark:border-gray-900">
        由 AI 助手提供技术支持 · 仅展示会话快照
      </div>
    </div>
  );
};

export default SharedChatPage;
