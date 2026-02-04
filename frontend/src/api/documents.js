import apiClient from './apiClient';

const documentsApi = {
  upload: (file, userId) => {
      const formData = new FormData();
      formData.append('files', file);
      formData.append('user_id', userId || 'anonymous');
      return apiClient('/api/documents/upload', { method: 'POST', body: formData });
  }
};

export default documentsApi;