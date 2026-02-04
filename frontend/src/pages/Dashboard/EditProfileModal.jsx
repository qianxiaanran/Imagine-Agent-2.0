import React, { useState, useEffect, useRef } from "react";
import { X, Camera } from "lucide-react";

const EditProfileModal = ({ isOpen, onClose, userProfile, onSave }) => {
  const [displayName, setDisplayName] = useState("");
  const [username, setUsername] = useState("");
  const [avatar, setAvatar] = useState("U");

  const [previewUrl, setPreviewUrl] = useState(null); // ObjectURL
  const [avatarFile, setAvatarFile] = useState(null); // File
  const [isProcessing, setIsProcessing] = useState(false);

  const fileInputRef = useRef(null);

  useEffect(() => {
    if (userProfile) {
      setDisplayName(userProfile.name || "");
      setUsername(userProfile.username || userProfile.name || "");
      setAvatar(userProfile.avatar || "U");
      setAvatarFile(null);

      if (previewUrl) URL.revokeObjectURL(previewUrl);
      setPreviewUrl(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userProfile, isOpen]);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsProcessing(true);
    try {
      if (!file.type?.startsWith("image/")) return;

      // 简单大小限制（后端还有 2MB 限制）
      if (file.size > 2 * 1024 * 1024) {
        console.error("头像过大（>2MB）");
        return;
      }

      setAvatarFile(file);
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      setPreviewUrl(URL.createObjectURL(file));
    } finally {
      setIsProcessing(false);
    }
  };

  const handleSave = () => {
    onSave({
      ...userProfile,
      name: displayName,
      username, // 仍保留显示用（后端会忽略更新）
      avatar, // 旧头像（URL/字母）
      avatarFile, // ⭐关键：给父组件上传 Storage
      previewUrl, // 仅用于 UI 乐观显示
    });
    onClose();
  };

  if (!isOpen) return null;

  const renderAvatar = () => {
    if (previewUrl) {
      return <img src={previewUrl} alt="Avatar" className="w-full h-full object-cover" />;
    }
    if (typeof avatar === "string" && avatar.length > 5) {
      return <img src={avatar} alt="Avatar" className="w-full h-full object-cover" />;
    }
    return avatar || "U";
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm transition-opacity" onClick={onClose} />

      <div className="relative w-full max-w-md bg-white dark:bg-gray-800 rounded-2xl shadow-2xl transform transition-all animate-in fade-in zoom-in-95 duration-200">
        <div className="p-6">
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">编辑个人资料</h2>
            <button
              onClick={onClose}
              className="p-1 rounded-full hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500 transition-colors"
            >
              <X size={20} />
            </button>
          </div>

          <div className="flex flex-col items-center mb-8">
            <div
              className={`relative group cursor-pointer ${isProcessing ? "opacity-50 pointer-events-none" : ""}`}
              onClick={() => fileInputRef.current?.click()}
            >
              <div className="w-24 h-24 rounded-full bg-blue-500 flex items-center justify-center text-white text-3xl font-medium overflow-hidden border-4 border-white dark:border-gray-700 shadow-md">
                {renderAvatar()}
              </div>

              <div className="absolute inset-0 bg-black/30 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                <Camera className="text-white" size={24} />
              </div>

              <input
                type="file"
                ref={fileInputRef}
                className="hidden"
                accept="image/*"
                onChange={handleFileChange}
              />
            </div>

            <span className="mt-2 text-xs text-gray-500 dark:text-gray-400">
              {isProcessing ? "处理中..." : "点击更换头像"}
            </span>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5 uppercase tracking-wider">
                显示名称 (昵称)
              </label>
              <input
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                className="w-full px-4 py-2.5 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-all"
                placeholder="输入您的昵称"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5 uppercase tracking-wider">
                用户名 (ID)
              </label>
              <div className="relative">
                <input
                  type="text"
                  value={username}
                  disabled
                  className="w-full px-4 py-2.5 rounded-xl border border-gray-100 dark:border-gray-800 bg-gray-100 dark:bg-gray-800/50 text-gray-500 dark:text-gray-500 cursor-not-allowed select-none"
                />
                <div className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400">
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
                    <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
                  </svg>
                </div>
              </div>
              <p className="text-[10px] text-gray-400 mt-1 ml-1">用户名由系统生成，无法修改</p>
            </div>
          </div>

          <div className="flex items-center justify-end gap-3 mt-6 pt-4 border-t border-gray-100 dark:border-gray-700">
            <button
              onClick={onClose}
              disabled={isProcessing}
              className="px-5 py-2 text-sm font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
            >
              取消
            </button>
            <button
              onClick={handleSave}
              disabled={isProcessing}
              className="px-5 py-2 text-sm font-medium text-white bg-black dark:bg-white dark:text-black rounded-full hover:opacity-80 transition-opacity shadow-sm disabled:opacity-50"
            >
              {isProcessing ? "处理中..." : "保存修改"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default EditProfileModal;
