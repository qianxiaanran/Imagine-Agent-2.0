import apiClient from './apiClient';

const presentationApi = {
  generatePresentonOutline: (payload) =>
    apiClient('/api/presentation/presenton/outline/generate', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
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
  getPresentonTemplateCatalog: () =>
    apiClient('/api/presentation/presenton/template/catalog'),
  listImportedPresentonTemplates: () =>
    apiClient('/api/presentation/presenton/template/imported'),
  importPresentonTemplate: (payload) =>
    apiClient('/api/presentation/presenton/template/import', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  removeImportedPresentonTemplate: (templateId) =>
    apiClient(`/api/presentation/presenton/template/import/${encodeURIComponent(templateId)}`, {
      method: 'DELETE',
    }),
};

export default presentationApi;
