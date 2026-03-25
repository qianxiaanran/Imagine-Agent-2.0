import apiClient from './apiClient';

const parseResponseBody = async (response) => {
  const text = await response.text();
  try {
    return text ? JSON.parse(text) : null;
  } catch {
    return text;
  }
};

const createShareError = (response, data) => {
  const error = new Error(
    (data && (data.detail || data.error || data.message)) ||
    (typeof data === 'string' ? data : '') ||
    `API Error: ${response.status} ${response.statusText}`
  );
  error.statusCode = Number(response?.status || 0);
  error.payload = data;
  return error;
};

const shareApi = {
  // 创建分享链接
  createShare: (sessionId, userId, options = {}) => {
    // options 参数：{ title: string, days: number }
    return apiClient(`/api/share/create?user_id=${userId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        title: options.title,
        days: options.days || 7
      })
    });
  },

  // 获取公开分享内容 (无需 user_id)
  getSharedContent: (token) => {
    const baseUrl = apiClient.defaults?.baseURL || '';
    return fetch(`${baseUrl}/api/public/share/${token}`)
      .then(async (response) => {
        const data = await parseResponseBody(response);
        if (!response.ok || data?.success === false) {
          throw createShareError(response, data);
        }
        return data;
      });
  }
};

export default shareApi;
