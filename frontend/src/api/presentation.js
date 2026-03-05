import apiClient from './apiClient';

const presentationApi = {
  generatePresentonPpt: (payload) =>
    apiClient('/api/presentation/presenton/generate', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  submitPresentonPptTask: (payload) =>
    apiClient('/api/presentation/presenton/generate/async', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getPresentonPptTaskStatus: (taskId) =>
    apiClient(`/api/presentation/presenton/generate/status/${encodeURIComponent(taskId)}`),
};

export default presentationApi;
