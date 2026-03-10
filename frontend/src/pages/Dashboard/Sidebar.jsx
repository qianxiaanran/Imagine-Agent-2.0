import React, { useState, useRef, useEffect, Suspense, useMemo } from "react";
import { Plus, PanelLeftClose, Search, Database, MessageSquare, Sparkles, Settings, LogOut, ChevronDown, Server, BookOpen, Activity, X, MoreHorizontal, Pencil, Trash2, Lock, Share2, Pin, PinOff } from "lucide-react";
import ChangePasswordModal from "./ChangePasswordModal";
import userApi from "../../api/user";
import historyApi from "../../api/history";
import AvatarContent from "../../components/AvatarContent";
import {
  appendCacheBuster,
  extractAvatarUrl,
  getPreferredAvatarSource,
} from "../../utils/avatar";

// 懒加载 ShareModal
const EditProfileModal = React.lazy(() => import("./EditProfileModal"));
const ShareModal = React.lazy(() => import('./ShareModal'));
const INITIAL_SESSION_RENDER_COUNT = 40;
const SESSION_RENDER_STEP = 40;

const SessionListSkeleton = ({ rows = 7 }) => (
  <div className="space-y-2 px-1 pt-1">
    {Array.from({ length: rows }).map((_, idx) => (
      <div key={`session-skeleton-${idx}`} className="flex items-center gap-2 rounded-lg px-2 py-2">
        <div className="h-4 w-4 rounded-full bg-gray-200 dark:bg-gray-700 animate-pulse" />
        <div className="h-3 w-full rounded bg-gray-200 dark:bg-gray-700 animate-pulse" />
      </div>
    ))}
  </div>
);

const ProfileCardSkeleton = () => (
  <div className="flex items-center gap-3 w-full px-3 py-2 rounded-lg">
    <div className="h-8 w-8 rounded-full bg-gray-200 dark:bg-gray-700 animate-pulse flex-shrink-0" />
    <div className="flex-1 min-w-0 space-y-1.5">
      <div className="h-3 w-20 rounded bg-gray-200 dark:bg-gray-700 animate-pulse" />
      <div className="h-2.5 w-14 rounded bg-gray-100 dark:bg-gray-800 animate-pulse" />
    </div>
  </div>
);

const Sidebar = ({
  isOpen,
  onClose,
  onNewChat,
  sessionList,
  currentSessionId,
  onSessionClick,
  userProfile,
  onLogout,
  onShowAppearance,
  currentMode = "general",
  onModeChange = () => {},
  onSessionListUpdate,
  isLoadingSessions = false,
  isLoadingProfile = false,
  selectedModel = 0, // 新增：接收当前选择的模型ID
}) => {
  const [isProfileMenuOpen, setIsProfileMenuOpen] = useState(false);
  const [isEditProfileOpen, setIsEditProfileOpen] = useState(false);
  const [isChangePasswordOpen, setIsChangePasswordOpen] = useState(false); // ✨ 修改密码弹窗状态
  const [localUserProfile, setLocalUserProfile] = useState(userProfile);
  const [isKbExpanded, setIsKbExpanded] = useState(false);
  const isAdmin = (localUserProfile?.role || userProfile?.role) === "admin";

  useEffect(() => {
    setLocalUserProfile(userProfile);
  }, [userProfile]);

  useEffect(() => {
    if (isLoadingProfile) {
      setIsProfileMenuOpen(false);
    }
  }, [isLoadingProfile]);

  // 固定会话状态（本地存储）
  const [pinnedSessionIds, setPinnedSessionIds] = useState(() => {
    try {
      const saved = localStorage.getItem(`pinned_sessions_${userProfile?.id || 'anonymous'}`);
      return new Set(saved ? JSON.parse(saved) : []);
    } catch {
      return new Set();
    }
  });

  // 搜索相关
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0); // 新增：当前选中的索引
  const searchInputRef = useRef(null);
  const searchListRef = useRef(null); // 新增：列表容器Ref

  // 会话运行状态
  const [menuOpenId, setMenuOpenId] = useState(null);
  const menuRef = useRef(null);

  // 删除确认弹窗
  const [deleteModal, setDeleteModal] = useState({ isOpen: false, sessionId: null, title: "" });

  // 重命名模态状态
  const [renameModal, setRenameModal] = useState({ isOpen: false, sessionId: null, title: "" });
  const [newTitleInput, setNewTitleInput] = useState("");

  // 分享弹窗
  const [shareModal, setShareModal] = useState({ isOpen: false, sessionId: null, title: "" });

  // 🚀 Optimistic UI (乐观更新) 状态
  const [optimisticDeletedIds, setOptimisticDeletedIds] = useState(new Set());
  const [optimisticRenames, setOptimisticRenames] = useState({});

  const profileMenuRef = useRef(null);

  // 更新固定状态并在本地保留
  const togglePinSession = (sessionId) => {
    const newPinned = new Set(pinnedSessionIds);
    if (newPinned.has(sessionId)) {
      newPinned.delete(sessionId);
    } else {
      newPinned.add(sessionId);
    }
    setPinnedSessionIds(newPinned);
    localStorage.setItem(`pinned_sessions_${userProfile?.id || 'anonymous'}`, JSON.stringify([...newPinned]));
  };

  const safeSessions = Array.isArray(sessionList) ? sessionList : [];

  // 排序：删除已删除 -> 固定在第一位 -> 原始时间顺序
  const displaySessions = useMemo(() => {
    const active = safeSessions.filter(s => !optimisticDeletedIds.has(s.id));
    return active.sort((a, b) => {
      const aPinned = pinnedSessionIds.has(a.id);
      const bPinned = pinnedSessionIds.has(b.id);
      if (aPinned && !bPinned) return -1;
      if (!aPinned && bPinned) return 1;
      return 0; // 保持原有时间排序
    });
  }, [safeSessions, optimisticDeletedIds, pinnedSessionIds]);

  // 过滤后的会话列表
  const filteredSessions = displaySessions.filter(session => {
    const titleToCheck = optimisticRenames[session.id] || session.title;
    return titleToCheck.toLowerCase().includes(searchQuery.toLowerCase());
  });
  const [visibleSessionCount, setVisibleSessionCount] = useState(INITIAL_SESSION_RENDER_COUNT);
  const shouldRenderAllSessions = isSearchOpen || searchQuery.trim().length > 0;
  const sessionsToRender = shouldRenderAllSessions
    ? displaySessions
    : displaySessions.slice(0, visibleSessionCount);
  const hasMoreSessions = !shouldRenderAllSessions && displaySessions.length > sessionsToRender.length;

  // 🔒 逻辑变更：只有在“通用企业问答” (Model ID: 0) 时才允许使用知识库/数据库
  // 其他所有模式 (会议、OCR、写作、审单) 均视为受限模式
  const isRestrictedMode = selectedModel !== 0;

  useEffect(() => {
    // 如果切换到限制模式，强制折叠知识菜单
    if (isRestrictedMode) {
      setIsKbExpanded(false);
    }
  }, [isRestrictedMode]);

  useEffect(() => {
    if (userProfile) {
      setLocalUserProfile((prev) => ({ ...prev, ...userProfile }));
      // 用户更改时重新加载固定配置
      try {
        const saved = localStorage.getItem(`pinned_sessions_${userProfile.id}`);
        setPinnedSessionIds(new Set(saved ? JSON.parse(saved) : []));
      } catch {
        setPinnedSessionIds(new Set());
      }
    }
  }, [userProfile]);

  useEffect(() => {
    setOptimisticDeletedIds(new Set());
    setOptimisticRenames({});
  }, [sessionList]);

  useEffect(() => {
    setVisibleSessionCount(INITIAL_SESSION_RENDER_COUNT);
  }, [displaySessions.length, userProfile?.id]);

  useEffect(() => {
    if (shouldRenderAllSessions) return;
    if (visibleSessionCount >= displaySessions.length) return;

    let cancelled = false;
    const grow = () => {
      if (cancelled) return;
      setVisibleSessionCount((count) => Math.min(displaySessions.length, count + SESSION_RENDER_STEP));
    };

    if (typeof window !== "undefined" && typeof window.requestIdleCallback === "function") {
      const id = window.requestIdleCallback(grow, { timeout: 1500 });
      return () => {
        cancelled = true;
        window.cancelIdleCallback(id);
      };
    }

    const id = setTimeout(grow, 180);
    return () => {
      cancelled = true;
      clearTimeout(id);
    };
  }, [shouldRenderAllSessions, visibleSessionCount, displaySessions.length]);

  // 全局快捷监听器
  useEffect(() => {
    const handleGlobalKeyDown = (e) => {
      // Ctrl + K 或 Cmd + K 切换搜索
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        setIsSearchOpen((prev) => !prev);
      }
      // Esc 关闭搜索（全局处理，以防焦点丢失）
      if (e.key === 'Escape' && isSearchOpen) {
        setIsSearchOpen(false);
      }
    };

    window.addEventListener('keydown', handleGlobalKeyDown);
    return () => window.removeEventListener('keydown', handleGlobalKeyDown);
  }, [isSearchOpen]);

  // 打开时聚焦搜索输入，并重置选择
  useEffect(() => {
    if (isSearchOpen) {
      setSelectedIndex(0);
      if (searchInputRef.current) {
        setTimeout(() => searchInputRef.current.focus(), 100);
      }
    } else {
      setSearchQuery(""); // 关闭时清空搜索词
    }
  }, [isSearchOpen]);

  // 搜索查询更改时重置选择
  useEffect(() => {
    setSelectedIndex(0);
  }, [searchQuery]);

  // 自动滚动到所选项目
  useEffect(() => {
    if (isSearchOpen && searchListRef.current) {
      const selectedElement = searchListRef.current.children[selectedIndex];
      if (selectedElement) {
        selectedElement.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    }
  }, [selectedIndex, isSearchOpen]);

  // 搜索列表内的键盘导航
  const handleSearchKeyDown = (e) => {
    if (filteredSessions.length === 0) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev + 1) % filteredSessions.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev - 1 + filteredSessions.length) % filteredSessions.length);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const selectedSession = filteredSessions[selectedIndex];
      if (selectedSession) {
        onSessionClick(selectedSession.id);
        setIsSearchOpen(false);
      }
    }
  };

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (profileMenuRef.current && !profileMenuRef.current.contains(event.target)) {
        setIsProfileMenuOpen(false);
      }
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setMenuOpenId(null);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleDeleteSession = () => {
    const sessionIdToDelete = deleteModal.sessionId;
    if (!sessionIdToDelete) return;

    setOptimisticDeletedIds(prev => {
      const newSet = new Set(prev);
      newSet.add(sessionIdToDelete);
      return newSet;
    });

    setDeleteModal({ isOpen: false, sessionId: null, title: "" });

    if (currentSessionId === sessionIdToDelete) {
      onNewChat();
    }

    historyApi.deleteSession(sessionIdToDelete, localUserProfile?.id || "anonymous")
      .then(() => {
        if (onSessionListUpdate) onSessionListUpdate();
      })
      .catch((error) => {
        console.error("Delete failed:", error);
      });
  };

  const handleRenameSession = async () => {
    const { sessionId } = renameModal;
    const newTitle = newTitleInput.trim();

    if (!sessionId || !newTitle) return;

    setOptimisticRenames(prev => ({ ...prev, [sessionId]: newTitle }));
    setRenameModal({ isOpen: false, sessionId: null, title: "" });

    try {
      await historyApi.renameSession(sessionId, newTitle, localUserProfile?.id || "anonymous");
      if (onSessionListUpdate) onSessionListUpdate();
    } catch (error) {
      console.error("Rename failed:", error);
    }
  };

  const renderAvatar = (avatar) => {
    return (
      <AvatarContent
        avatar={avatar}
        name={localUserProfile?.name || userProfile?.name}
      />
    );
  };

  const handleUpdateProfile = async (newProfile) => {
    setLocalUserProfile((prev) => ({
      ...prev,
      name: newProfile.name ?? prev.name,
      username: newProfile.username ?? prev.username,
    }));

    let avatarUrlToSave = getPreferredAvatarSource(extractAvatarUrl(newProfile.avatar));
    let avatarUrlForDisplay = avatarUrlToSave ? appendCacheBuster(avatarUrlToSave) : "";
    try {
      if (newProfile.avatarFile) {
        const up = await userApi.uploadAvatar(newProfile.avatarFile);
        const uploadedUrl = extractAvatarUrl(up);
        if (!uploadedUrl) {
          throw new Error("Avatar upload succeeded but no URL was returned");
        }
        const preferredUrl = getPreferredAvatarSource(uploadedUrl) || uploadedUrl;
        avatarUrlToSave = preferredUrl;
        avatarUrlForDisplay = appendCacheBuster(preferredUrl);
        setLocalUserProfile((prev) => ({
          ...prev,
          avatar: avatarUrlForDisplay || prev.avatar,
        }));
      }

      const payload = {
        name: newProfile.name,
        username: newProfile.username,
      };
      if (avatarUrlToSave) payload.avatar = avatarUrlToSave;
      await userApi.updateProfile(payload);

      const avatarToRender =
        avatarUrlForDisplay ||
        (avatarUrlToSave ? appendCacheBuster(avatarUrlToSave) : "");

      setLocalUserProfile((prev) => ({
        ...prev,
        name: newProfile.name,
        username: newProfile.username,
        avatar: avatarToRender || prev.avatar,
      }));
    } catch (error) {
      console.error("Failed to save profile:", error);
      if (avatarUrlForDisplay) {
        setLocalUserProfile((prev) => ({
          ...prev,
          avatar: avatarUrlForDisplay,
        }));
      }
    }
  };

  return (
    <>
      {/* 删除确认弹窗 */}
      {deleteModal.isOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/20 backdrop-blur-[2px] animate-in fade-in duration-200">
          <div className="bg-white dark:bg-gray-800 w-[400px] rounded-2xl shadow-2xl border border-gray-100 dark:border-gray-700 p-6 flex flex-col gap-4 animate-in zoom-in-95 duration-200">
            <div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">删除聊天？</h3>
              <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
                这会删除“<span className="font-medium text-gray-900 dark:text-gray-200">{deleteModal.title}</span>”。
              </p>
              <p className="text-xs text-gray-400 mt-1">访问设置以删除此聊天期间保存的所有记忆。</p>
            </div>
            <div className="flex justify-end gap-3 mt-2">
              <button
                onClick={() => setDeleteModal({ isOpen: false, sessionId: null, title: "" })}
                className="px-4 py-2 text-sm font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-full transition-colors border border-gray-200 dark:border-gray-600"
              >
                取消
              </button>
              <button
                onClick={handleDeleteSession}
                className="px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-full transition-colors shadow-sm"
              >
                删除
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Re 重命名模态 */}
      {renameModal.isOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/20 backdrop-blur-[2px] animate-in fade-in duration-200">
          <div className="bg-white dark:bg-gray-800 w-[400px] rounded-2xl shadow-2xl border border-gray-100 dark:border-gray-700 p-6 flex flex-col gap-4 animate-in zoom-in-95 duration-200">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">重命名会话</h3>
            <input
              type="text"
              value={newTitleInput}
              onChange={(e) => setNewTitleInput(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-transparent dark:text-white"
              autoFocus
              onKeyDown={(e) => e.key === 'Enter' && handleRenameSession()}
            />
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setRenameModal({ isOpen: false, sessionId: null, title: "" })}
                className="px-4 py-2 text-sm font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-full border border-gray-200 dark:border-gray-600"
              >
                取消
              </button>
              <button
                onClick={handleRenameSession}
                className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-full shadow-sm"
              >
                保存
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 搜索模框 */}
      {isSearchOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm animate-in fade-in duration-200">
          <div
            className="bg-white dark:bg-gray-800 w-full max-w-2xl rounded-xl shadow-2xl border border-gray-200 dark:border-gray-700 overflow-hidden flex flex-col max-h-[70vh] animate-in zoom-in-95 duration-200"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-100 dark:border-gray-700">
              <Search className="text-gray-400" size={20} />
              <input
                ref={searchInputRef}
                type="text"
                className="flex-1 bg-transparent border-none outline-none text-gray-900 dark:text-white placeholder-gray-400 text-base"
                placeholder="搜索聊天记录..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={handleSearchKeyDown} // 绑定按键处理
              />
              <div className="flex items-center gap-2">

                 <button
                  onClick={() => setIsSearchOpen(false)}
                  className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 bg-gray-100 dark:bg-gray-700 rounded text-xs px-2"
                >
                  ESC
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-2 custom-scrollbar" ref={searchListRef}>
              {filteredSessions.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-10 text-gray-400">
                   <Search size={40} className="mb-2 opacity-20" />
                   <p className="text-sm">未找到相关聊天</p>
                </div>
              ) : (
                <div className="space-y-1">
                  {filteredSessions.map((session, index) => (
                    <div
                      key={session.id}
                      onClick={() => {
                        onSessionClick(session.id);
                        setIsSearchOpen(false);
                      }}
                      // 动态添加高亮背景色：如果 index === selectedIndex，则高亮
                      className={`flex items-center gap-3 px-3 py-3 rounded-lg cursor-pointer group transition-colors
                        ${index === selectedIndex
                          ? "bg-blue-50 dark:bg-blue-900/20 border border-blue-100 dark:border-blue-800"
                          : "hover:bg-gray-100 dark:hover:bg-gray-700/50 border border-transparent"
                        }`}
                    >
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 transition-colors
                         ${index === selectedIndex
                           ? "bg-blue-100 dark:bg-blue-800 text-blue-600 dark:text-blue-200"
                           : "bg-gray-100 dark:bg-gray-700 text-gray-500 group-hover:bg-white dark:group-hover:bg-gray-600"
                         }`}>
                        <MessageSquare size={16} />
                      </div>
                      <div className="flex-1 min-w-0 text-left">
                        <div className={`text-sm font-medium truncate ${index === selectedIndex ? "text-blue-700 dark:text-blue-100" : "text-gray-900 dark:text-gray-100"}`}>
                          {optimisticRenames[session.id] || session.title}
                        </div>
                        <div className={`text-xs ${index === selectedIndex ? "text-blue-400 dark:text-blue-300" : "text-gray-400"}`}>
                          {new Date(session.date).toLocaleDateString()}
                        </div>
                      </div>
                      {index === selectedIndex && (
                        <div className="hidden sm:block text-blue-400">
                           <span className="text-[10px]"></span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
              {hasMoreSessions && (
                <div className="px-3 pt-2 pb-3">
                  <button
                    type="button"
                    onClick={() => setVisibleSessionCount((count) => Math.min(displaySessions.length, count + SESSION_RENDER_STEP))}
                    className="w-full text-center text-[11px] font-medium text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 px-3 py-1.5 rounded-full border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                  >
                    加载更多
                  </button>
                </div>
              )}
            </div>
          </div>
          <div className="absolute inset-0 -z-10" onClick={() => setIsSearchOpen(false)}></div>
        </div>
      )}

      {/* De 桌面侧边栏主体 */}
      <div
        className={`dashboard-sidebar-shell ${isOpen ? "w-[260px] border-r" : "w-0 border-none"} bg-[#f9f9f9] dark:bg-gray-900 border-gray-100 dark:border-gray-800 flex-shrink-0 transition-[width] duration-300 hidden md:flex z-20 overflow-hidden relative flex-col`}
      >
        <div className="w-[260px] h-full flex flex-col">

          {/* Fi 固定顶部控件（不随历史记录滚动） */}
          <div className="flex-shrink-0">
              {/* 1. 1. 标题按钮 */}
              <div className="p-3 pb-1 flex items-center gap-2">
                <button
                  className="flex-1 flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-gray-200/60 dark:hover:bg-gray-800 transition-colors text-sm text-gray-700 dark:text-gray-200 font-medium"
                  onClick={onNewChat}
                >
                  <div className="w-6 h-6 rounded-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 flex items-center justify-center">
                    <Plus size={14} />
                  </div>
                  新聊天
                </button>

                <button
                  onClick={onClose}
                  className="p-2 text-gray-500 hover:text-gray-900 dark:hover:text-white hover:bg-gray-200/60 dark:hover:bg-gray-800 rounded-lg transition-colors"
                  title="收起边栏"
                >
                  <PanelLeftClose size={20} />
                </button>
              </div>

              {/* 2. 2. 工具：搜索和知识库管理 */}
              <div className="px-3 py-2 space-y-1">
                  <div
                    onClick={() => setIsSearchOpen(true)}
                    className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-gray-200/60 dark:hover:bg-gray-800 text-sm text-gray-700 dark:text-gray-300 cursor-pointer transition-colors group"
                  >
                    <Search size={16} className="text-gray-500 group-hover:text-gray-900 dark:group-hover:text-white" />
                    <span className="flex-1">搜索聊天</span>
                    <span className="text-xs text-gray-400 border border-gray-200 dark:border-gray-700 rounded px-1.5 py-0.5">⌘ K</span>
                  </div>

                  <div>
                    <button
                      onClick={() => !isRestrictedMode && setIsKbExpanded(!isKbExpanded)}
                      disabled={isRestrictedMode}
                      className={`w-full flex items-center justify-between px-3 py-2 rounded-lg transition-colors ${
                        isRestrictedMode
                          ? "opacity-50 cursor-not-allowed text-gray-400 dark:text-gray-500"
                          : `hover:bg-gray-200/60 dark:hover:bg-gray-800 text-sm text-gray-700 dark:text-gray-300 cursor-pointer ${isKbExpanded ? "bg-gray-100 dark:bg-gray-800" : ""}`
                      }`}
                      title={isRestrictedMode ? "仅在通用问答模式下可用" : "切换知识库模式"}
                    >
                      <div className="flex items-center gap-3">
                        <Database size={16} /> 知识库管理
                      </div>
                      {isRestrictedMode ? (
                        <Lock size={12} className="text-gray-400" />
                      ) : (
                        <ChevronDown
                          size={14}
                          className={`transition-transform duration-200 ${isKbExpanded ? "rotate-180" : ""}`}
                        />
                      )}
                    </button>

                    <div
                      className={`overflow-hidden transition-all duration-300 ease-in-out ${
                        isKbExpanded && !isRestrictedMode ? "max-h-40 opacity-100 mt-1" : "max-h-0 opacity-0"
                      }`}
                    >
                      <div className="pl-2 space-y-0.5">
                        <button
                          onClick={() => onModeChange("database")}
                          className={`w-full flex items-center gap-3 px-3 py-2 rounded-md text-xs transition-colors ${
                            currentMode === "database"
                              ? "bg-green-50 text-green-600 dark:bg-green-900/20 dark:text-green-400 font-medium"
                              : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
                          }`}
                        >
                          <Server size={14} /> 企业数据库 (SQL)
                        </button>
                         <div className="px-3 py-1 flex items-center gap-2">
                            <Activity size={10} className={currentMode === 'database' ? 'text-green-500' : 'text-blue-500'} />
                            <span className="text-[10px] text-gray-400">当前: {currentMode === 'database' ? 'SQL模式' : (currentMode === 'rag' ? '知识库模式' : '通用模式')}</span>
                         </div>
                      </div>
                    </div>
                  </div>
              </div>
          </div>

          {/* Di 分频器 */}
          <div className="h-px bg-gray-100 dark:bg-gray-800 mx-4 mb-2"></div>

          {/* 3. 滚动区域：仅包含历史记录 */}
          <div className="flex-1 overflow-y-auto px-3 pb-2 custom-scrollbar" onClick={() => setMenuOpenId(null)}>
            <div className="pt-0">
              <h3 className="px-3 text-xs font-medium text-gray-400 mb-2">最近聊天</h3>
              {isLoadingSessions && displaySessions.length === 0 ? (
                <SessionListSkeleton rows={8} />
              ) : displaySessions.length === 0 ? (
                <div className="px-3 py-2 text-xs text-gray-400">暂无历史记录</div>
              ) : (
                sessionsToRender.map((session) => (
                  <div
                    key={session.id}
                    className={`group relative px-3 py-2 text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-200/60 dark:hover:bg-gray-800 rounded-lg cursor-pointer flex items-center gap-2
                    ${currentSessionId === session.id ? "bg-gray-200/80 dark:bg-gray-800 font-medium text-gray-900 dark:text-white" : ""}
                    ${pinnedSessionIds.has(session.id) ? "border-l-2 border-blue-500 bg-blue-50/50 dark:bg-blue-900/10" : ""}`}
                    onClick={() => onSessionClick(session.id)}
                  >
                    <div className="relative">
                      <MessageSquare size={14} className="flex-shrink-0 opacity-50" />
                      {pinnedSessionIds.has(session.id) && (
                        <div className="absolute -top-1 -right-1 w-2 h-2 bg-blue-500 rounded-full border border-white dark:border-gray-900"></div>
                      )}
                    </div>
                    <span className="truncate flex-1">
                      {optimisticRenames[session.id] || session.title}
                    </span>

                    {/* 置顶标识 */}
                    {pinnedSessionIds.has(session.id) && (
                      <Pin size={10} className="text-blue-500 flex-shrink-0 mr-1 rotate-45" />
                    )}

                    <button
                      className={`p-1 rounded-md text-gray-500 hover:text-gray-800 hover:bg-gray-300/50 dark:hover:bg-gray-700
                      ${menuOpenId === session.id ? "opacity-100 block" : "opacity-0 group-hover:opacity-100 hidden group-hover:block"}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        setMenuOpenId(menuOpenId === session.id ? null : session.id);
                      }}
                    >
                      <MoreHorizontal size={14} />
                    </button>

                    {menuOpenId === session.id && (
                      <div
                        ref={menuRef}
                        className="dashboard-dropdown absolute right-2 top-8 z-50 w-32 bg-white dark:bg-gray-800 rounded-lg shadow-xl border border-gray-200 dark:border-gray-700 py-1 overflow-hidden animate-in fade-in zoom-in-95 duration-100"
                        onClick={(e) => e.stopPropagation()}
                      >
                         <button
                           onClick={() => {
                             setMenuOpenId(null);
                             togglePinSession(session.id);
                           }}
                           className="w-full text-left px-3 py-2 text-xs text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
                         >
                           {pinnedSessionIds.has(session.id) ? <PinOff size={12} className="text-gray-500"/> : <Pin size={12} className="text-blue-500"/>}
                           {pinnedSessionIds.has(session.id) ? "取消置顶" : "置顶会话"}
                         </button>
                         <div className="h-px bg-gray-100 dark:bg-gray-700 my-0.5"></div>
                         <button
                           onClick={() => {
                             setMenuOpenId(null);
                             setShareModal({ isOpen: true, sessionId: session.id, title: session.title });
                           }}
                           className="w-full text-left px-3 py-2 text-xs text-blue-600 dark:text-blue-400 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
                         >
                           <Share2 size={12} /> 分享
                         </button>
                         <button
                          onClick={() => {
                            setMenuOpenId(null);
                            setNewTitleInput(optimisticRenames[session.id] || session.title);
                            setRenameModal({ isOpen: true, sessionId: session.id, title: session.title });
                          }}
                          className="w-full text-left px-3 py-2 text-xs text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
                        >
                          <Pencil size={12} /> 重命名
                        </button>
                        <div className="h-px bg-gray-100 dark:bg-gray-700 my-0.5"></div>
                        <button
                          onClick={() => {
                            setMenuOpenId(null);
                            setDeleteModal({ isOpen: true, sessionId: session.id, title: session.title });
                          }}
                          className="w-full text-left px-3 py-2 text-xs text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 flex items-center gap-2"
                        >
                          <Trash2 size={12} /> 删除
                        </button>
                      </div>
                    )}
                  </div>
                ))
              )}
              {!isLoadingSessions && hasMoreSessions && (
                <div className="px-3 pt-2 pb-3">
                  <button
                    type="button"
                    onClick={() => setVisibleSessionCount((count) => Math.min(displaySessions.length, count + SESSION_RENDER_STEP))}
                    className="w-full text-center text-[11px] font-medium text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 px-3 py-1.5 rounded-full border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                  >
                    加载更多
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* 底部用户菜单 */}
          <div className="p-3 border-t border-gray-100 dark:border-gray-800 relative" ref={profileMenuRef}>
            {isProfileMenuOpen && !isLoadingProfile && (
              <div className="absolute bottom-full left-0 w-full px-3 mb-2 z-50 animate-in fade-in zoom-in-95 duration-200 origin-bottom">
                <div className="dashboard-dropdown bg-white dark:bg-gray-800 rounded-xl shadow-xl border border-gray-200 dark:border-gray-700 overflow-hidden w-full">
                  <div className="p-1.5">
                    <div
                      className="px-2 py-2 flex items-center gap-3 mb-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg cursor-pointer transition-colors"
                      onClick={() => {
                        setIsEditProfileOpen(true);
                        setIsProfileMenuOpen(false);
                      }}
                    >
                      <div className="w-8 h-8 rounded-full bg-blue-500 flex items-center justify-center text-white text-xs font-medium overflow-hidden">
                        {renderAvatar(localUserProfile?.avatar)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-gray-900 dark:text-white truncate">
                          {localUserProfile?.name}
                        </div>
                        <div className="text-xs text-gray-500 dark:text-gray-400 truncate">
                          @{localUserProfile?.username || localUserProfile?.name}
                        </div>
                      </div>
                    </div>

                    <div className="h-px bg-gray-100 dark:bg-gray-700 my-1"></div>

                    <button
                      className="w-full flex items-center gap-3 px-2 py-2.5 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors text-left"
                      onClick={() => {
                        onShowAppearance("personalization");
                        setIsProfileMenuOpen(false);
                      }}
                    >
                      <Sparkles size={18} strokeWidth={1.5} /> 个性化
                    </button>

                    {/* [N [新增]更改密码按钮 */}
                    <button
                      className="w-full flex items-center gap-3 px-2 py-2.5 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors text-left"
                      onClick={() => {
                        setIsChangePasswordOpen(true);
                        setIsProfileMenuOpen(false);
                      }}
                    >
                      <Lock size={18} strokeWidth={1.5} /> 修改密码
                    </button>

                    {isAdmin && (
                      <button
                        className="w-full flex items-center gap-3 px-2 py-2.5 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors text-left"
                        onClick={() => {
                          setIsProfileMenuOpen(false);
                          window.open("/admin", "_blank", "noopener,noreferrer");
                        }}
                      >
                        <Server size={18} strokeWidth={1.5} /> 管理员后台
                      </button>
                    )}

                    <button
                      className="w-full flex items-center gap-3 px-2 py-2.5 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors text-left"
                      onClick={() => {
                        onShowAppearance("general");
                        setIsProfileMenuOpen(false);
                      }}
                    >
                      <Settings size={18} strokeWidth={1.5} /> 设置
                    </button>

                    <div className="h-px bg-gray-100 dark:bg-gray-700 my-1"></div>

                    <button
                      className="w-full flex items-center gap-3 px-2 py-2.5 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors text-left"
                      onClick={onLogout}
                    >
                      <LogOut size={18} strokeWidth={1.5} /> 注销
                    </button>
                  </div>
                </div>
              </div>
            )}

            {isLoadingProfile ? (
              <ProfileCardSkeleton />
            ) : (
              <button
                className={`flex items-center gap-3 w-full px-3 py-2 rounded-lg hover:bg-gray-200/60 dark:hover:bg-gray-800 transition-colors text-left
                ${isProfileMenuOpen ? "bg-gray-100 dark:bg-gray-800" : ""}`}
                onClick={() => setIsProfileMenuOpen(!isProfileMenuOpen)}
              >
                <div className="w-8 h-8 rounded-full bg-blue-500 flex items-center justify-center text-white text-xs font-medium flex-shrink-0 overflow-hidden">
                  {renderAvatar(localUserProfile?.avatar)}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-gray-900 dark:text-white truncate">{localUserProfile?.name}</div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">{localUserProfile?.plan || "Free"}</div>
                </div>
              </button>
            )}
          </div>
        </div>

      </div>

      {/* [N [新增]修改密码模式 */}
      <ChangePasswordModal
        isOpen={isChangePasswordOpen}
        onClose={() => setIsChangePasswordOpen(false)}
      />

      <Suspense fallback={null}>
        <EditProfileModal
          isOpen={isEditProfileOpen}
          onClose={() => setIsEditProfileOpen(false)}
          userProfile={localUserProfile || {}}
          onSave={handleUpdateProfile}
        />
        <ShareModal
          isOpen={shareModal.isOpen}
          onClose={() => setShareModal({ isOpen: false, sessionId: null, title: "" })}
          sessionId={shareModal.sessionId}
          sessionTitle={shareModal.title}
          userId={localUserProfile?.id || "anonymous"}
        />
      </Suspense>
    </>
  );
};

export default React.memo(Sidebar);
