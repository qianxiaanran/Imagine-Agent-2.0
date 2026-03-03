import apiClient from './apiClient';

const workflowApi = {
  startMonthlyAnalysis: ({
    userId,
    sessionId,
    query,
    modelBackend = 'local',
    topic = '月度经营分析',
    title = '月度经营分析',
  }) =>
    apiClient('/api/workflow/jobs/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scenario: 'monthly_operating_analysis',
        user_id: userId,
        session_id: sessionId || null,
        query,
        model_backend: modelBackend,
        topic,
        title,
      }),
    }),

  getJob: (jobId, userId) =>
    apiClient(`/api/workflow/jobs/${jobId}?user_id=${encodeURIComponent(userId)}`, {
      method: 'GET',
    }),

  listJobs: (userId, limit = 20) =>
    apiClient(`/api/workflow/jobs?user_id=${encodeURIComponent(userId)}&limit=${limit}`, {
      method: 'GET',
    }),

  confirmJob: ({ jobId, userId, action = 'approved', comment = '' }) =>
    apiClient(`/api/workflow/jobs/${jobId}/confirm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: userId,
        action,
        comment,
      }),
    }),

  retryJob: ({ jobId, userId }) =>
    apiClient(`/api/workflow/jobs/${jobId}/retry`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: userId,
      }),
    }),
};

export default workflowApi;

