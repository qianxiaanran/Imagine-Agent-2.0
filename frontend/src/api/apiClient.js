const USE_MOCK_DATA = false;
export const API_BASE_URL = '';
export const AUTH_TOKEN_KEY = 'app_auth_token';

const mockResponses = {
  '/health': { status: 'ok', timestamp: new Date().toISOString() },
  '/api/auth/login': { success: true, token: 'mock-jwt-token', user: { id: 1, name: 'Admin User', email: 'admin@flowus.cn' } },
  '/api/auth/register': { success: true, token: 'mock-jwt-token', user: { id: 2, name: 'New User', email: 'new@flowus.cn' } },
  '/api/auth/send_code': { success: true, message: 'Verification code sent' },
  '/api/user/profile': { id: 1, name: 'John Doe', plan: 'Enterprise', avatar: 'JD' },
};

const apiClient = async (endpoint, options = {}) => {
  if (USE_MOCK_DATA) {
    console.log(`[Mock API] Calling ${endpoint}`, options);
    await new Promise(resolve => setTimeout(resolve, 600));
    return mockResponses[endpoint] || { success: true, message: 'Mock response' };
  }


  try {
    const url = endpoint.startsWith('http') ? endpoint : `${API_BASE_URL}${endpoint}`;
    const token = localStorage.getItem(AUTH_TOKEN_KEY);
    const authHeaders = token ? { Authorization: `Bearer ${token}` } : {};

    const isFormData = options.body instanceof FormData;

    const headers = {
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...authHeaders,
      ...options.headers,
    };

    const response = await fetch(url, { ...options, headers });

    // 尽量把后端 detail/message 解析出来（更好排错）
    const text = await response.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = text;
    }

    if (!response.ok) {
      if (response.status === 401) localStorage.removeItem(AUTH_TOKEN_KEY);
      const msg =
        (data && (data.detail || data.message)) ||
        (typeof data === 'string' ? data : '') ||
        `API Error: ${response.status} ${response.statusText}`;
      throw new Error(msg);
    }

    return data;
  } catch (error) {
    console.error('API Request Failed:', error);
    throw error;
  }
};

export default apiClient;
