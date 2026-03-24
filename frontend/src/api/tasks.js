import apiClient from './apiClient';

const tasksApi = {
  listOverview: (params = {}) => {
    const search = new URLSearchParams();
    Object.entries(params || {}).forEach(([key, value]) => {
      if (value === undefined || value === null || value === '') return;
      search.set(key, String(value));
    });
    const suffix = search.toString();
    return apiClient(`/api/tasks/overview${suffix ? `?${suffix}` : ''}`);
  },
  getTaskDetail: (taskId) =>
    apiClient(`/api/tasks/overview/${encodeURIComponent(taskId)}`),
  retryTask: (taskId) =>
    apiClient(`/api/tasks/overview/${encodeURIComponent(taskId)}/retry`, {
      method: 'POST',
    }),
};

export default tasksApi;
