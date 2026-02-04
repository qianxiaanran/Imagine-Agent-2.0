import apiClient from "./apiClient";

const userApi = {
  getProfile: () => apiClient("/api/user/profile", { method: "GET" }),

  updateProfile: (data) =>
    apiClient("/api/user/profile", {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  // ✅ 上传头像到 Storage：统一走 apiClient（会自动带 app_auth_token）
  uploadAvatar: (file) => {
    const form = new FormData();
    form.append("file", file);

    return apiClient("/api/user/avatar", {
      method: "POST",
      body: form,
    });
  },
};

export default userApi;
