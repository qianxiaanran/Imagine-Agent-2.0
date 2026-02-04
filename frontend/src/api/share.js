import apiClient from './apiClient';

const shareApi = {
  // 创建分享链接
  createShare: (sessionId, userId, options = {}) => {
    // options: { title: string, days: number }
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
    // 直接 fetch，不经过 apiClient (apiClient 可能会附加 auth token，虽不影响但最好纯净)
    // 这里假设 API_BASE_URL 和 apiClient 里的一样，我们直接拼
    const baseUrl = apiClient.defaults?.baseURL || '';
    // 注意：如果是 create-react-app 代理模式，baseUrl 为空即可

    return fetch(`${baseUrl}/api/public/share/${token}`)
      .then(res => res.json());
  }
};

export default shareApi;