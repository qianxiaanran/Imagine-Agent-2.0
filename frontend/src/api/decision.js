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

  getDrilldown: async ({
    source,
    granularity = 'month',
    bucket = '',
    status = '',
    category = '',
    name = '',
    limit = 8,
  } = {}) => {
    const params = new URLSearchParams({
      source: source || '',
      granularity: granularity || 'month',
      limit: String(Number(limit || 8)),
    });
    if (bucket) params.set('bucket', bucket);
    if (status) params.set('status', status);
    if (category) params.set('category', category);
    if (name) params.set('name', name);
    return apiClient(`/api/decision/drilldown?${params.toString()}`, { method: 'GET' });
  },
};

export default decisionApi;
