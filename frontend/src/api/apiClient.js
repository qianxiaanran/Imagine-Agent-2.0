const USE_MOCK_DATA = false;
export const API_BASE_URL = '';
export const AUTH_TOKEN_KEY = 'app_auth_token';
const REMEMBER_UNTIL_KEY = 'app_auth_remember_until';

const mockResponses = {
  '/health': { status: 'ok', timestamp: new Date().toISOString() },
  '/api/auth/login': { success: true, token: 'mock-jwt-token', user: { id: 1, name: 'Admin User', email: 'admin@flowus.cn' } },
  '/api/auth/register': { success: true, token: 'mock-jwt-token', user: { id: 2, name: 'New User', email: 'new@flowus.cn' } },
  '/api/auth/send_code': { success: true, message: 'Verification code sent' },
  '/api/user/profile': { id: 1, name: 'John Doe', plan: 'Enterprise', avatar: 'JD' },
};

let supabaseClientPromise;
const getSupabaseClient = async () => {
  if (!supabaseClientPromise) {
    supabaseClientPromise = import('./supabaseClient').then((module) => module.supabase);
  }
  return supabaseClientPromise;
};

const extractErrorMessage = (response, data) =>
  (data && (data.detail || data.message)) ||
  (typeof data === 'string' ? data : '') ||
  `API Error: ${response.status} ${response.statusText}`;

const parseResponseBody = async (response) => {
  const text = await response.text();
  try {
    return text ? JSON.parse(text) : null;
  } catch {
    return text;
  }
};

const rememberWindowValid = () => {
  const rememberUntil = Number(localStorage.getItem(REMEMBER_UNTIL_KEY) || 0);
  return rememberUntil > Date.now();
};

const shouldClearTokenOnUnauthorized = (endpoint) => {
  const path = String(endpoint || '');
  // 管理后台权限问题不应直接判定为“登录失效”
  if (path.includes('/api/admin/')) return false;
  return true;
};

const refreshAccessToken = async () => {
  if (!rememberWindowValid()) return null;

  try {
    const supabase = await getSupabaseClient();
    const { data, error } = await supabase.auth.refreshSession();
    if (error || !data?.session?.access_token) return null;
    localStorage.setItem(AUTH_TOKEN_KEY, data.session.access_token);
    return data.session.access_token;
  } catch (error) {
    console.warn('Token refresh failed:', error);
    return null;
  }
};

const executeRequest = async (endpoint, options, tokenOverride = null) => {
  const url = endpoint.startsWith('http') ? endpoint : `${API_BASE_URL}${endpoint}`;
  const token = tokenOverride ?? localStorage.getItem(AUTH_TOKEN_KEY);
  const authHeaders = token ? { Authorization: `Bearer ${token}` } : {};
  const isFormData = options.body instanceof FormData;
  const headers = {
    ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
    ...authHeaders,
    ...options.headers,
  };
  const response = await fetch(url, { ...options, headers });
  const data = await parseResponseBody(response);
  return { response, data };
};

const apiClient = async (endpoint, options = {}) => {
  if (USE_MOCK_DATA) {
    console.log(`[Mock API] Calling ${endpoint}`, options);
    await new Promise(resolve => setTimeout(resolve, 600));
    return mockResponses[endpoint] || { success: true, message: 'Mock response' };
  }


  try {
    const firstAttempt = await executeRequest(endpoint, options);
    if (firstAttempt.response.ok) return firstAttempt.data;

    if (firstAttempt.response.status === 401) {
      const refreshedToken = await refreshAccessToken();
      if (refreshedToken) {
        const retryAttempt = await executeRequest(endpoint, options, refreshedToken);
        if (retryAttempt.response.ok) return retryAttempt.data;

        if (retryAttempt.response.status === 401 && shouldClearTokenOnUnauthorized(endpoint)) {
          localStorage.removeItem(AUTH_TOKEN_KEY);
        }
        throw new Error(extractErrorMessage(retryAttempt.response, retryAttempt.data));
      }

      if (shouldClearTokenOnUnauthorized(endpoint)) {
        localStorage.removeItem(AUTH_TOKEN_KEY);
      }
    }

    throw new Error(extractErrorMessage(firstAttempt.response, firstAttempt.data));
  } catch (error) {
    console.error('API Request Failed:', error);
    throw error;
  }
};

export default apiClient;
