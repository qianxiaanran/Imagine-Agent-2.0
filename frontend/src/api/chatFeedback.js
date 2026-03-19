import apiClient from './apiClient';

const normalizeFeedbackMap = (result) => {
  const raw = result?.feedback && typeof result.feedback === 'object'
    ? result.feedback
    : (result && typeof result === 'object' ? result : {});
  const feedbackMap = {};

  Object.entries(raw).forEach(([key, value]) => {
    const normalizedKey = String(key || '').trim();
    const normalizedValue = String(value || '').trim().toLowerCase();
    if (!normalizedKey) return;
    if (normalizedValue !== 'up' && normalizedValue !== 'down') return;
    feedbackMap[normalizedKey] = normalizedValue;
  });

  return feedbackMap;
};

const chatFeedbackApi = {
  getSessionFeedback: async (sessionId) => {
    const safeSessionId = encodeURIComponent(String(sessionId || '').trim());
    if (!safeSessionId) return {};
    const result = await apiClient(`/api/chat/feedback/${safeSessionId}`, { method: 'GET' });
    return normalizeFeedbackMap(result);
  },

  submitFeedback: async (payload) => {
    const result = await apiClient('/api/chat/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload || {}),
    });
    return result || {};
  },
};

export default chatFeedbackApi;
