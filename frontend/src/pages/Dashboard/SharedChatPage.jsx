import React, { useEffect, useState, Suspense, lazy } from 'react';
import { Bot, User, Clock, AlertCircle, FileText } from 'lucide-react';
import shareApi from '../../api/share';

const MarkdownRenderer = lazy(() => import('./MarkdownRenderer'));

const SharedChatPage = () => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);

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
      } catch (e) {
        setError("无法加载分享内容");
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  if (loading) {
    return (
      <div
        className="bg-gray-50 dark:bg-gray-900 flex items-center justify-center"
        style={{ height: 'var(--app-height, 100vh)' }}
      >
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
          <p className="text-gray-500 text-sm">正在获取分享内容...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div
        className="bg-gray-50 dark:bg-gray-900 flex items-center justify-center p-4"
        style={{ height: 'var(--app-height, 100vh)' }}
      >
        <div className="bg-white dark:bg-gray-800 p-8 rounded-2xl shadow-xl max-w-md w-full text-center">
          <div className="w-16 h-16 bg-red-100 dark:bg-red-900/30 rounded-full flex items-center justify-center mx-auto mb-4 text-red-500">
            <AlertCircle size={32} />
          </div>
          <h2 className="text-xl font-bold text-gray-800 dark:text-white mb-2">会话已过期</h2>
          <p className="text-gray-500 dark:text-gray-400 mb-6">{error}</p>
          <a href="/" className="inline-block px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors font-medium">
            返回主页
          </a>
        </div>
      </div>
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
               return (
                   <div key={idx} className="flex justify-center">
                       <div className="bg-gray-50 dark:bg-gray-900 border border-gray-100 dark:border-gray-800 rounded-lg p-3 w-full max-w-lg text-xs text-gray-500 dark:text-gray-400 flex items-center gap-2">
                           <FileText size={14} className="flex-shrink-0" />
                           <span className="truncate">该部分包含上下文或文件解析内容</span>
                           <span className="opacity-50 ml-auto">(已折叠)</span>
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
