import {
  API_BASE_URL,
  AUTH_REFRESH_TOKEN_KEY,
  AUTH_REMEMBER_UNTIL_KEY,
  AUTH_TOKEN_KEY,
} from './config';

export {
  API_BASE_URL,
  AUTH_REFRESH_TOKEN_KEY,
  AUTH_REMEMBER_UNTIL_KEY,
  AUTH_TOKEN_KEY,
} from './config';

const USE_MOCK_DATA = false;

const mockResponses = {
  '/health': { status: 'ok', timestamp: new Date().toISOString() },
  '/api/auth/login': { success: true, token: 'mock-jwt-token', user: { id: 1, name: 'Admin User', email: 'admin@flowus.cn' } },
  '/api/auth/register': { success: true, token: 'mock-jwt-token', user: { id: 2, name: 'New User', email: 'new@flowus.cn' } },
  '/api/auth/send_code': { success: true, message: 'Verification code sent' },
  '/api/user/profile': { id: 1, name: 'John Doe', plan: 'Enterprise', avatar: 'JD' },
};

let supabaseClientPromise;
let refreshAccessTokenPromise = null;
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

const createApiError = (response, data, endpoint) => {
  const error = new Error(extractErrorMessage(response, data));
  error.statusCode = Number(response?.status || 0);
  error.endpoint = endpoint;
  error.payload = data;
  return error;
};

const parseResponseBody = async (response) => {
  const text = await response.text();
  try {
    return text ? JSON.parse(text) : null;
  } catch {
    return text;
  }
};

const rememberWindowValid = () => {
  const rememberUntil = Number(localStorage.getItem(AUTH_REMEMBER_UNTIL_KEY) || 0);
  return rememberUntil > Date.now();
};

const shouldClearTokenOnUnauthorized = (endpoint) => {
  const path = String(endpoint || '');
  // 管理后台权限问题不应直接判定为“登录失效”
  if (path.includes('/api/admin/')) return false;
  return true;
};

const isSmsToken = (token) => String(token || '').startsWith('sms-token-');

const clearStoredAuthTokens = () => {
  localStorage.removeItem(AUTH_TOKEN_KEY);
  localStorage.removeItem(AUTH_REFRESH_TOKEN_KEY);
};

const syncTokensFromSupabaseSession = async () => {
  try {
    const supabase = await getSupabaseClient();
    const { data } = await supabase.auth.getSession();
    const session = data?.session;
    if (!session?.access_token) return null;
    localStorage.setItem(AUTH_TOKEN_KEY, session.access_token);
    if (session.refresh_token) {
      localStorage.setItem(AUTH_REFRESH_TOKEN_KEY, session.refresh_token);
    }
    return session.access_token;
  } catch {
    return null;
  }
};

const refreshAccessTokenViaBackend = async (refreshTokenOverride = null) => {
  const refreshToken = refreshTokenOverride ?? localStorage.getItem(AUTH_REFRESH_TOKEN_KEY);
  if (!refreshToken) return null;

  try {
    const response = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    const data = await parseResponseBody(response);
    if (!response.ok || !data?.token) return null;

    localStorage.setItem(AUTH_TOKEN_KEY, data.token);
    if (data.refresh_token) {
      localStorage.setItem(AUTH_REFRESH_TOKEN_KEY, data.refresh_token);
    }
    return data.token;
  } catch (error) {
    console.warn('Backend token refresh failed:', error);
    return null;
  }
};

export const refreshAccessToken = async () => {
  if (refreshAccessTokenPromise) {
    return refreshAccessTokenPromise;
  }

  refreshAccessTokenPromise = (async () => {
    if (!rememberWindowValid()) return null;
    const currentToken = localStorage.getItem(AUTH_TOKEN_KEY);
    if (isSmsToken(currentToken)) return null;

    const initialRefreshToken = localStorage.getItem(AUTH_REFRESH_TOKEN_KEY);
    const backendRefreshedToken = await refreshAccessTokenViaBackend(initialRefreshToken);
    if (backendRefreshedToken) return backendRefreshedToken;

    // 若 refresh_token 已在 Supabase SDK 内被轮换，先同步一次再重试后端刷新。
    await syncTokensFromSupabaseSession();
    const rotatedRefreshToken = localStorage.getItem(AUTH_REFRESH_TOKEN_KEY);
    if (rotatedRefreshToken && rotatedRefreshToken !== initialRefreshToken) {
      const retryBySyncedToken = await refreshAccessTokenViaBackend(rotatedRefreshToken);
      if (retryBySyncedToken) return retryBySyncedToken;
    }

    try {
      const supabase = await getSupabaseClient();
      const { data, error } = await supabase.auth.refreshSession();
      if (error || !data?.session?.access_token) return null;
      localStorage.setItem(AUTH_TOKEN_KEY, data.session.access_token);
      if (data.session.refresh_token) {
        localStorage.setItem(AUTH_REFRESH_TOKEN_KEY, data.session.refresh_token);
      }
      return data.session.access_token;
    } catch (error) {
      console.warn('Token refresh failed:', error);
      return null;
    }
  })().finally(() => {
    refreshAccessTokenPromise = null;
  });

  return refreshAccessTokenPromise;
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
          clearStoredAuthTokens();
        }
        throw createApiError(retryAttempt.response, retryAttempt.data, endpoint);
      }

      if (shouldClearTokenOnUnauthorized(endpoint)) {
        clearStoredAuthTokens();
      }
    }

    throw createApiError(firstAttempt.response, firstAttempt.data, endpoint);
  } catch (error) {
    console.error('API Request Failed:', error);
    throw error;
  }
};

export default apiClient;
