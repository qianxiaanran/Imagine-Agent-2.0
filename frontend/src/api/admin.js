import apiClient from "./apiClient";

const adminApi = {
  listUsers: (params = {}) => {
    const search = new URLSearchParams(params).toString();
    return apiClient(`/api/admin/users${search ? `?${search}` : ""}`, { method: "GET" });
  },
  updateUserRole: (userId, role) =>
    apiClient(`/api/admin/users/${userId}/role`, {
      method: "POST",
      body: JSON.stringify({ role }),
    }),
  updateUserStatus: (userId, status) =>
    apiClient(`/api/admin/users/${userId}/status`, {
      method: "POST",
      body: JSON.stringify({ status }),
    }),
  forceLogout: (userId, reason) =>
    apiClient(`/api/admin/users/${userId}/force_logout`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  deleteUser: (userId) =>
    apiClient(`/api/admin/users/${userId}`, { method: "DELETE" }),
  listAuditRecords: (params = {}) => {
    const search = new URLSearchParams(params).toString();
    return apiClient(`/api/admin/audit/records${search ? `?${search}` : ""}`, { method: "GET" });
  },
  getAuditDetail: (jobId) =>
    apiClient(`/api/admin/audit/records/${jobId}`, { method: "GET" }),
  reviewAudit: (payload) =>
    apiClient(`/api/admin/audit/review`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getAuditRules: (docType) =>
    apiClient(`/api/admin/audit/rules/${docType}`, { method: "GET" }),
  updateAuditRules: (docType, rules) =>
    apiClient(`/api/admin/audit/rules/${docType}`, {
      method: "PUT",
      body: JSON.stringify({ rules }),
    }),
  listJobs: (params = {}) => {
    const search = new URLSearchParams(params).toString();
    return apiClient(`/api/admin/jobs${search ? `?${search}` : ""}`, { method: "GET" });
  },
  cancelJob: (jobId) =>
    apiClient(`/api/admin/jobs/${jobId}/cancel`, { method: "POST" }),
  retryJob: (jobId) =>
    apiClient(`/api/admin/jobs/${jobId}/retry`, { method: "POST" }),
  listKbDocuments: (params = {}) => {
    const search = new URLSearchParams(params).toString();
    return apiClient(`/api/admin/kb/documents${search ? `?${search}` : ""}`, { method: "GET" });
  },
  updateKbStatus: (payload) =>
    apiClient(`/api/admin/kb/documents/approve`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  deleteKbDocument: (payload) =>
    apiClient(`/api/admin/kb/documents/delete`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  reindexKbDocument: (payload) =>
    apiClient(`/api/admin/kb/documents/reindex`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  listAdminLogs: (params = {}) => {
    const search = new URLSearchParams(params).toString();
    return apiClient(`/api/admin/logs${search ? `?${search}` : ""}`, { method: "GET" });
  },
};

export default adminApi;
