import { API_BASE_URL, AUTH_TOKEN_KEY } from './config';

const chatApi = {
  // 修改为直接使用 fetch 以支持流式响应 (Streaming)
  sendMessage: async (message, modelId, sessionId, userId, mode) => {
    const token = localStorage.getItem(AUTH_TOKEN_KEY);

    // 手动构建 Header，因为我们跳过了 apiClient
    const headers = {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };

    const url = `${API_BASE_URL}/api/chat`;

    // ⚠️ 关键修改：直接使用 fetch
    // apiClient 会 await response.text() 导致流式卡顿，所以这里不能用它
    const response = await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        message,
        modelId: String(modelId),
        session_id: sessionId,
        user_id: userId,
        mode: mode // ✅ 确保将侧边栏选中的模式传递给后端
      }),
    });

    if (!response.ok) {
      throw new Error(`Chat request failed: ${response.statusText}`);
    }

    // 返回原始 response 对象，以便前端 (useChat 等 Hook) 使用 getReader() 读取流
    return response;
  },
};

export default chatApi;
