import apiClient from './apiClient';

const authApi = {
  sendCode: (phone) => apiClient('/api/auth/send_code', { method: 'POST', body: JSON.stringify({ phone }) }),

  login: (account, password) => apiClient('/api/auth/login', { method: 'POST', body: JSON.stringify({ account, password }) }),

  loginWithCode: (account, code) => apiClient('/api/auth/login', { method: 'POST', body: JSON.stringify({ phone: account, code }) }),

  register: (account, password, code) => apiClient('/api/auth/register', { method: 'POST', body: JSON.stringify({ account, password, code }) }),

  // ✨ 新增重置密码接口
  resetPassword: (account, code, password) => apiClient('/api/auth/reset_password', { method: 'POST', body: JSON.stringify({ account, code, password }) }),
};

export default authApi;