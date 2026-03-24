import apiClient from './apiClient';

const normalizeHistoryPagePayload = (result) => {
  if (Array.isArray(result)) {
    return {
      items: result,
      contextItems: [],
      hasMore: false,
      nextBeforeId: null,
    };
  }

  const items = Array.isArray(result?.items)
    ? result.items
    : (Array.isArray(result?.data) ? result.data : []);
  const contextItems = Array.isArray(result?.context_items)
    ? result.context_items
    : (Array.isArray(result?.contextItems) ? result.contextItems : []);

  return {
    items,
    contextItems,
    hasMore: Boolean(result?.has_more),
    nextBeforeId: result?.next_before_id ?? null,
  };
};

const historyApi = {
  getSessions: (userId) =>
    apiClient(`/api/history/sessions?user_id=${userId}`, { method: 'GET' }),

  getSessionMessagesPage: async (sessionId, userId, { limit = 40, beforeId = null, includeContext = false } = {}) => {
    const params = new URLSearchParams({ user_id: userId });
    if (limit) params.set('limit', String(limit));
    if (beforeId) params.set('before_id', String(beforeId));
    if (includeContext) params.set('include_context', 'true');
    const result = await apiClient(`/api/history/${sessionId}?${params.toString()}`, { method: 'GET' });
    return normalizeHistoryPagePayload(result);
  },

  getSessionMessages: async (sessionId, userId, options = {}) => {
    const page = await historyApi.getSessionMessagesPage(sessionId, userId, options);
    const result = [...page.contextItems, ...page.items];
    if (Array.isArray(result)) return result;
    if (Array.isArray(result?.data)) return result.data;
    if (Array.isArray(result?.items)) return result.items;
    return [];
  },

  // ✨ 新增: 删除会话
  deleteSession: (sessionId, userId) =>
    apiClient(`/api/history/${sessionId}?user_id=${userId}`, { method: 'DELETE' }),

  // ✨ 新增: 重命名会话
  renameSession: (sessionId, newTitle, userId) =>
    apiClient(`/api/history/${sessionId}/title?user_id=${userId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: newTitle })
    }),

  setSessionPinned: (sessionId, pinned, userId) =>
    apiClient(`/api/history/${sessionId}/pin?user_id=${userId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pinned: Boolean(pinned) })
    }),

  // ✨ 修改: 保存会话上下文 (转写框内容)，增加 contextType 参数
  // contextType 建议: 'voice_context' | 'ocr_context'
  saveContext: (sessionId, content, userId, contextType = 'context_save') =>
    apiClient(`/api/history/${sessionId}/context?user_id=${userId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content, type: contextType })
    })
};

export default historyApi;
