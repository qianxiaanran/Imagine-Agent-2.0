import apiClient from './apiClient';

const decisionApi = {
  getOverview: async ({ refreshAi = false, refreshData = false, backend = 'cloud' } = {}) => {
    const params = new URLSearchParams({
      refresh_ai: String(Boolean(refreshAi)),
      refresh_data: String(Boolean(refreshData)),
      analysis_backend: backend || 'cloud',
    });
    return apiClient(`/api/decision/overview?${params.toString()}`, { method: 'GET' });
  },

  getData: async ({ refreshData = false } = {}) => {
    const params = new URLSearchParams({
      refresh_data: String(Boolean(refreshData)),
    });
    return apiClient(`/api/decision/data?${params.toString()}`, { method: 'GET' });
  },

  getAi: async ({ refreshAi = false, refreshData = false, backend = 'cloud' } = {}) => {
    const params = new URLSearchParams({
      refresh_ai: String(Boolean(refreshAi)),
      refresh_data: String(Boolean(refreshData)),
      analysis_backend: backend || 'cloud',
    });
    return apiClient(`/api/decision/ai?${params.toString()}`, { method: 'GET' });
  },
};

export default decisionApi;
