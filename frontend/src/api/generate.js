import apiClient from './apiClient';

const generateApi = {
  report: (prompt) => apiClient('/api/generate/report', { method: 'POST', body: JSON.stringify({ prompt }) }),
  email: (prompt) => apiClient('/api/generate/email', { method: 'POST', body: JSON.stringify({ prompt }) })
};

export default generateApi;