import apiClient from './apiClient';

const historyApi = {
  getSessions: (userId) =>
    apiClient(`/api/history/sessions?user_id=${userId}`, { method: 'GET' }),

  getSessionMessages: (sessionId, userId) =>
    apiClient(`/api/history/${sessionId}?user_id=${userId}`, { method: 'GET' }),

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