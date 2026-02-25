import React, { useState, useEffect, lazy, Suspense, memo, useRef, useMemo } from "react";
import { X, Plus, Search, Database, MessageSquare, ChevronDown, Sparkles, Settings, LogOut, BookOpen, Server, ArrowLeft, MoreHorizontal, Pencil, Trash2, Lock, Share2, Pin, PinOff } from "lucide-react";
import userApi from "../../api/user";
import historyApi from "../../api/history";
import ChangePasswordModal from "./ChangePasswordModal";
import AvatarContent from "../../components/AvatarContent";
import {
  appendCacheBuster,
  extractAvatarUrl,
  getPreferredAvatarSource,
} from "../../utils/avatar";

// Performance optimization: lazy-load modal
const EditProfileModal = lazy(() => import("./EditProfileModal"));
const ShareModal = lazy(() => import('./ShareModal'));
const INITIAL_SESSION_RENDER_COUNT = 40;
const SESSION_RENDER_STEP = 40;

const SessionListSkeleton = ({ rows = 7 }) => (
  <div className="space-y-2 px-1">
    {Array.from({ length: rows }).map((_, idx) => (
      <div key={`mobile-session-skeleton-${idx}`} className="flex items-center gap-3 rounded-lg px-2 py-2">
        <div className="h-4 w-4 rounded-full bg-gray-200 dark:bg-gray-700 animate-pulse" />
        <div className="h-3 w-full rounded bg-gray-200 dark:bg-gray-700 animate-pulse" />
      </div>
    ))}
  </div>
);

const ProfileCardSkeleton = () => (
  <div className="w-full flex items-center gap-3 p-2 rounded-lg border border-transparent">
    <div className="h-9 w-9 rounded-full bg-gray-200 dark:bg-gray-700 animate-pulse flex-shrink-0" />
    <div className="flex-1 min-w-0 space-y-1.5">
      <div className="h-3 w-24 rounded bg-gray-200 dark:bg-gray-700 animate-pulse" />
      <div className="h-2.5 w-16 rounded bg-gray-100 dark:bg-gray-800 animate-pulse" />
    </div>
  </div>
);

// 🚀 Memo 优化
const MobileSidebar = memo(({
  isOpen,
  onClose,
  userProfile,
  sessionList,
  currentSessionId,
  onSessionClick,
  onNewChat,
  onLogout,
  onShowAppearance,
  currentMode = "general",
  onModeChange = () => {},
  isLoading = false,
  onSessionListUpdate,
  selectedModel = 0, // 新增：接收模型参数
}) => {
  const [isProfileExpanded, setIsProfileExpanded] = useState(false);
  const [isEditProfileOpen, setIsEditProfileOpen] = useState(false);
  const [isChangePasswordOpen, setIsChangePasswordOpen] = useState(false); // ✨
  const [localUserProfile, setLocalUserProfile] = useState(userProfile);
  const [isKbExpanded, setIsKbExpanded] = useState(false);
  const isAdmin = (localUserProfile?.role || userProfile?.role) === "admin";

  useEffect(() => {
    setLocalUserProfile(userProfile);
  }, [userProfile]);

  useEffect(() => {
    if (isLoading) {
      setIsProfileExpanded(false);
    }
  }, [isLoading]);

  // 搜索
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const searchInputRef = useRef(null);

  // Pinned session state (local storage)
  const [pinnedSessionIds, setPinnedSessionIds] = useState(() => {
    try {
      const saved = localStorage.getItem(`pinned_sessions_${userProfile?.id || 'anonymous'}`);
      return new Set(saved ? JSON.parse(saved) : []);
    } catch {
      return new Set();
    }
  });

  // Session operation state
  const [menuOpenId, setMenuOpenId] = useState(null);
  const [deleteModal, setDeleteModal] = useState({ isOpen: false, sessionId: null, title: "" });
  const [renameModal, setRenameModal] = useState({ isOpen: false, sessionId: null, title: "" });
  const [newTitleInput, setNewTitleInput] = useState("");

  // 分享弹窗
  const [shareModal, setShareModal] = useState({ isOpen: false, sessionId: null, title: "" });

  // 🚀 Optimistic UI: 乐观更新状态
  const [optimisticDeletedIds, setOptimisticDeletedIds] = useState(new Set());
  const [optimisticRenames, setOptimisticRenames] = useState({});

  // Visible list: base list minus optimistic deletions
  const safeSessions = Array.isArray(sessionList) ? sessionList : [];

  // Sorting logic
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

  const filteredSessions = displaySessions.filter(session => {
    const t = optimisticRenames[session.id] || session.title;
    return t.toLowerCase().includes(searchQuery.toLowerCase());
  });
  const [visibleSessionCount, setVisibleSessionCount] = useState(INITIAL_SESSION_RENDER_COUNT);
  const shouldRenderAllSessions = isSearchOpen || searchQuery.trim().length > 0;
  const sessionsToRender = shouldRenderAllSessions
    ? displaySessions
    : displaySessions.slice(0, visibleSessionCount);
  const hasMoreSessions = !shouldRenderAllSessions && displaySessions.length > sessionsToRender.length;

  // Update pinned state and persist locally
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

  // 🔒 逻辑变更：只有在“通用企业问答” (Model ID: 0) 时才允许使用知识库/数据库
  // 其他所有模式 (会议、OCR、写作、审单) 均视为受限模式
  const isRestrictedMode = selectedModel !== 0;

  useEffect(() => {
    // If switched to restricted mode, collapse knowledge menu
    if (isRestrictedMode) {
      setIsKbExpanded(false);
    }
  }, [isRestrictedMode]);

  useEffect(() => {
    if (userProfile) {
      setLocalUserProfile((prev) => ({ ...prev, ...userProfile }));
      // Reload pinned config when user changes
      try {
        const saved = localStorage.getItem(`pinned_sessions_${userProfile.id}`);
        setPinnedSessionIds(new Set(saved ? JSON.parse(saved) : []));
      } catch {
        setPinnedSessionIds(new Set());
      }
    }
  }, [userProfile]);

  useEffect(() => {
    if (!isOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previousOverflow || '';
    };
  }, [isOpen]);

  // 当从父组件接收到新的列表时，清空乐观缓存
  useEffect(() => {
    setOptimisticDeletedIds(new Set());
    setOptimisticRenames({}); // 清空临时重命名
  }, [sessionList]);

  useEffect(() => {
    setVisibleSessionCount(INITIAL_SESSION_RENDER_COUNT);
  }, [displaySessions.length, userProfile?.id]);

  useEffect(() => {
    if (!isOpen) return;
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
  }, [isOpen, shouldRenderAllSessions, visibleSessionCount, displaySessions.length]);

  useEffect(() => {
    if (isSearchOpen && searchInputRef.current) {
        setTimeout(() => searchInputRef.current.focus(), 100);
    }
  }, [isSearchOpen]);

  // 🚀 Optimistic Delete 逻辑
  const handleDeleteSession = () => {
    const sid = deleteModal.sessionId;
    if (!sid) return;

    setOptimisticDeletedIds(prev => {
        const newSet = new Set(prev);
        newSet.add(sid);
        return newSet;
    });

    setDeleteModal({ isOpen: false, sessionId: null, title: "" });

    if (currentSessionId === sid) {
      onNewChat();
    }

    historyApi.deleteSession(sid, localUserProfile?.id || "anonymous")
      .then(() => {
          if (onSessionListUpdate) onSessionListUpdate();
      })
      .catch(error => {
          console.error("Delete failed:", error);
      });
  };

  // 🚀 Optimistic Rename 逻辑
  const handleRenameSession = async () => {
    const sid = renameModal.sessionId;
    const title = newTitleInput.trim();
    if (!sid || !title) return;

    // 1. 立即更新 UI
    setOptimisticRenames(prev => ({ ...prev, [sid]: title }));

    // 2. 立即关闭窗口
    setRenameModal({ isOpen: false, sessionId: null, title: "" });

    try {
      await historyApi.renameSession(sid, title, localUserProfile?.id || "anonymous");
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

  if (!isOpen) return null;

  return (
    <>
      {/* Delete confirmation modal (Mobile) */}
      {deleteModal.isOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 bg-black/50 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-white dark:bg-gray-800 w-full max-w-sm rounded-2xl shadow-2xl p-6 flex flex-col gap-4 animate-in zoom-in-95 duration-200">
             <div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">Delete Chat?</h3>
              <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
                这会删除“<span className="font-medium text-gray-900 dark:text-gray-200">{deleteModal.title}</span>”。
              </p>
              <p className="text-xs text-gray-400 mt-1">访问设置以删除此聊天期间保存的所有记忆。</p>
            </div>
            <div className="flex justify-end gap-3 mt-2">
              <button
                onClick={() => setDeleteModal({ isOpen: false, sessionId: null, title: "" })}
                className="px-4 py-2.5 text-sm font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-full bg-gray-100 dark:bg-gray-700"
              >
                取消
              </button>
              <button
                onClick={handleDeleteSession}
                className="px-4 py-2.5 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-full shadow-sm"
              >
                删除
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Rename modal */}
      {renameModal.isOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 bg-black/50 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-white dark:bg-gray-800 w-full max-w-sm rounded-2xl shadow-2xl p-6 flex flex-col gap-4 animate-in zoom-in-95 duration-200">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">重命名会话</h3>
            <input
              type="text"
              value={newTitleInput}
              onChange={(e) => setNewTitleInput(e.target.value)}
              className="w-full px-3 py-3 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-transparent dark:text-white"
              autoFocus
            />
            <div className="flex justify-end gap-3">
               <button
                onClick={() => setRenameModal({ isOpen: false, sessionId: null, title: "" })}
                className="px-4 py-2.5 text-sm font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-full bg-gray-100 dark:bg-gray-700"
              >
                取消
              </button>
              <button
                onClick={handleRenameSession}
                className="px-4 py-2.5 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-full shadow-sm"
              >
                保存
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="fixed inset-0 z-50 md:hidden flex">
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm transition-opacity" onClick={onClose}></div>

        <div
          className="relative w-[85%] max-w-[300px] bg-[#f9f9f9] dark:bg-gray-900 h-full shadow-2xl animate-in slide-in-from-left duration-300 flex flex-col z-50"
          style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
        >

          {/* Search overlay */}
          {isSearchOpen ? (
            <div
              className="absolute inset-0 bg-[#f9f9f9] dark:bg-gray-900 z-20 flex flex-col animate-in fade-in duration-200"
              style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
            >
              <div
                className="px-4 pb-4 flex items-center gap-2 border-b border-gray-100 dark:border-gray-800"
                style={{ paddingTop: 'calc(env(safe-area-inset-top) + 16px)' }}
              >
                <button onClick={() => setIsSearchOpen(false)} className="p-2 -ml-2 text-gray-500">
                  <ArrowLeft size={20} />
                </button>
                <input
                  ref={searchInputRef}
                  type="text"
                  className="flex-1 bg-transparent border-none outline-none text-gray-900 dark:text-white placeholder-gray-400"
                  placeholder="搜索..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
                {searchQuery && (
                    <button onClick={() => setSearchQuery("")} className="text-gray-400">
                        <X size={16} />
                    </button>
                )}
              </div>
              <div className="flex-1 overflow-y-auto px-2 py-2">
                  {filteredSessions.length === 0 ? (
                      <div className="text-center text-gray-400 py-10 text-sm">无搜索结果</div>
                  ) : (
                      filteredSessions.map(session => (
                          <div
                              key={session.id}
                              onClick={() => {
                                  onSessionClick(session.id);
                                  setIsSearchOpen(false);
                                  onClose();
                              }}
                              className="px-3 py-3 text-sm text-gray-600 dark:text-gray-300 border-b border-gray-100 dark:border-gray-800/50 last:border-0 hover:bg-gray-100 dark:hover:bg-gray-800"
                          >
                              {/* Prefer optimistic title when available */}
                              <div className="font-medium truncate">{optimisticRenames[session.id] || session.title}</div>
                              <div className="text-xs text-gray-400 mt-0.5">{new Date(session.date).toLocaleDateString()}</div>
                          </div>
                      ))
                  )}
              </div>
            </div>
          ) : (
            <>
              {/* Mobile Header: New Chat Title */}
              <div
                className="px-4 pb-4 flex items-center justify-between border-b border-gray-100 dark:border-gray-800 bg-[#f9f9f9] dark:bg-gray-900 flex-shrink-0"
                style={{ paddingTop: 'calc(env(safe-area-inset-top) + 16px)' }}
              >
                <div className="font-bold text-gray-900 dark:text-white text-lg">New Chat</div>
                <button onClick={onClose} className="p-2 text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-800 rounded-lg">
                  <X size={20} />
                </button>
              </div>

              {/* Fixed top controls (Mobile) */}
              <div className="flex-shrink-0 px-3 pt-4 pb-2">
                <button
                    className="w-full flex items-center gap-3 px-3 py-3 rounded-lg hover:bg-gray-200/60 dark:hover:bg-gray-800 transition-colors text-sm text-gray-700 dark:text-gray-200 font-medium bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow-sm mb-3"
                    onClick={onNewChat}
                  >
                    <div className="w-6 h-6 rounded-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 flex items-center justify-center">
                      <Plus size={14} />
                    </div>
                    开启新对话
                </button>

                <div className="space-y-1">
                  <div
                      onClick={() => setIsSearchOpen(true)}
                      className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-gray-200/60 dark:hover:bg-gray-800 text-sm text-gray-700 dark:text-gray-300 cursor-pointer"
                  >
                    <Search size={16} /> 搜索聊天
                  </div>

                  <div>
                    <button
                      onClick={() => !isRestrictedMode && setIsKbExpanded(!isKbExpanded)}
                      disabled={isRestrictedMode}
                      className={`w-full flex items-center justify-between px-3 py-2 rounded-lg transition-colors ${
                        isRestrictedMode
                          ? "opacity-50 cursor-not-allowed text-gray-400 dark:text-gray-500"
                          : `hover:bg-gray-200/60 dark:hover:bg-gray-800 text-sm text-gray-700 dark:text-gray-300 cursor-pointer ${isKbExpanded ? 'bg-gray-100 dark:bg-gray-800' : ''}`
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <Database size={16} /> 知识库管理
                      </div>
                      {isRestrictedMode ? (
                        <Lock size={12} className="text-gray-400" />
                      ) : (
                        <ChevronDown size={14} className={`transition-transform ${isKbExpanded ? 'rotate-180' : ''}`} />
                      )}
                    </button>

                    {isKbExpanded && !isRestrictedMode && (
                      <div className="pl-4 mt-1 space-y-1 animate-in slide-in-from-top-1">
                        <button
                          onClick={() => {
                            onModeChange('database');
                            onClose();
                          }}
                          className={`w-full flex items-center gap-3 px-3 py-3 rounded-lg text-sm transition-colors ${
                            currentMode === 'database'
                              ? 'bg-green-50 text-green-600 dark:bg-green-900/20 dark:text-green-400 font-medium'
                              : 'text-gray-600 dark:text-gray-400'
                          }`}
                        >
                          <Server size={14} /> 企业数据库 (SQL)
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>

               {/* Divider */}
              <div className="h-px bg-gray-100 dark:bg-gray-800 mx-4 mb-2"></div>

              {/* Scroll area: history list only */}
              <div className="flex-1 overflow-y-auto px-3 py-2 custom-scrollbar" onClick={() => setMenuOpenId(null)}>
                <div className="">
                  <h3 className="px-3 text-xs font-medium text-gray-400 mb-3">最近聊天</h3>
                  {isLoading && displaySessions.length === 0 ? (
                    <SessionListSkeleton rows={8} />
                  ) : displaySessions.length === 0 ? (
                    <div className="px-3 py-2 text-xs text-gray-400">暂无历史记录</div>
                  ) : (
                    sessionsToRender.map((session) => (
                      <div
                        key={session.id}
                        className={`relative px-3 py-3 text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-200/60 dark:hover:bg-gray-800 rounded-lg cursor-pointer flex items-center gap-3 ${
                          currentSessionId === session.id ? "bg-gray-200/80 dark:bg-gray-800 font-medium text-gray-900 dark:text-white" : ""
                        } ${pinnedSessionIds.has(session.id) ? "border-l-2 border-blue-500 bg-blue-50/50 dark:bg-blue-900/10" : ""}`}
                        onClick={() => onSessionClick(session.id)}
                      >
                        <div className="relative">
                          <MessageSquare size={16} className="flex-shrink-0 opacity-50" />
                          {pinnedSessionIds.has(session.id) && (
                            <div className="absolute -top-1 -right-1 w-2 h-2 bg-blue-500 rounded-full border border-white dark:border-gray-900"></div>
                          )}
                        </div>
                        <span className="truncate flex-1">{optimisticRenames[session.id] || session.title}</span>

                        {/* 置顶标识 */}
                        {pinnedSessionIds.has(session.id) && (
                          <Pin size={12} className="text-blue-500 flex-shrink-0 mr-1 rotate-45" />
                        )}

                        <button
                          className="p-1 rounded-md text-gray-400 hover:text-gray-800 hover:bg-gray-300/50 dark:hover:bg-gray-700"
                          onClick={(e) => {
                            e.stopPropagation();
                            setMenuOpenId(menuOpenId === session.id ? null : session.id);
                          }}
                        >
                          <MoreHorizontal size={16} />
                        </button>

                         {menuOpenId === session.id && (
                          <div
                            className="absolute right-4 top-10 z-50 w-32 bg-white dark:bg-gray-800 rounded-lg shadow-xl border border-gray-200 dark:border-gray-700 py-1 overflow-hidden animate-in fade-in zoom-in-95 duration-100"
                            onClick={(e) => e.stopPropagation()}
                          >
                             {/* 置顶按钮 */}
                             <button
                               onClick={() => {
                                 setMenuOpenId(null);
                                 togglePinSession(session.id);
                               }}
                               className="w-full text-left px-3 py-3 text-xs text-gray-700 dark:text-gray-200 active:bg-gray-100 dark:active:bg-gray-700 flex items-center gap-2"
                             >
                               {pinnedSessionIds.has(session.id) ? <PinOff size={14} className="text-gray-500"/> : <Pin size={14} className="text-blue-500"/>}
                               {pinnedSessionIds.has(session.id) ? "取消置顶" : "置顶会话"}
                             </button>
                             <div className="h-px bg-gray-100 dark:bg-gray-700 my-0.5"></div>
                             <button
                               onClick={() => {
                                 setMenuOpenId(null);
                                 setShareModal({ isOpen: true, sessionId: session.id, title: session.title });
                               }}
                               className="w-full text-left px-3 py-3 text-xs text-blue-600 dark:text-blue-400 active:bg-blue-50 dark:active:bg-blue-900/20 flex items-center gap-2"
                             >
                               <Share2 size={14} /> 分享
                             </button>

                             <button
                              onClick={() => {
                                setMenuOpenId(null);
                                setNewTitleInput(optimisticRenames[session.id] || session.title);
                                setRenameModal({ isOpen: true, sessionId: session.id, title: session.title });
                              }}
                              className="w-full text-left px-3 py-3 text-xs text-gray-700 dark:text-gray-200 active:bg-gray-100 dark:active:bg-gray-700 flex items-center gap-2"
                            >
                              <Pencil size={14} /> 重命名
                            </button>
                            <div className="h-px bg-gray-100 dark:bg-gray-700 my-0.5"></div>
                            <button
                              onClick={() => {
                                setMenuOpenId(null);
                                setDeleteModal({ isOpen: true, sessionId: session.id, title: session.title });
                              }}
                              className="w-full text-left px-3 py-3 text-xs text-red-600 active:bg-red-50 dark:active:bg-red-900/20 flex items-center gap-2"
                            >
                              <Trash2 size={14} /> 删除
                            </button>
                          </div>
                        )}
                      </div>
                    ))
                  )}
                  {!isLoading && hasMoreSessions && (
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

              {/* 底部用户区域 */}
              <div className="border-t border-gray-100 dark:border-gray-800 p-3 bg-gray-50 dark:bg-gray-900/50 flex-shrink-0">
                {/* Changed max-h-48 to max-h-72 to accommodate all items in the expanded menu.
                   Previous value was too short for (Profile + Appearance + Settings + Logout).
                */}
                <div className={`transition-all duration-300 ease-in-out overflow-hidden ${isProfileExpanded && !isLoading ? "max-h-72 opacity-100 mb-3" : "max-h-0 opacity-0"}`}>
                  <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 overflow-hidden py-1">
                    <div
                      className="px-4 py-3 border-b border-gray-100 dark:border-gray-700 flex items-center gap-3 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/50"
                      onClick={() => {
                        setIsEditProfileOpen(true);
                        setIsProfileExpanded(false);
                      }}
                    >
                      <div className="w-8 h-8 rounded-full bg-blue-500 flex items-center justify-center text-white text-xs font-bold overflow-hidden">
                        {renderAvatar(localUserProfile?.avatar)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-bold text-gray-900 dark:text-white truncate">{localUserProfile?.name}</div>
                        <div className="text-xs text-gray-500 dark:text-gray-400 truncate">
                          @{localUserProfile?.username || localUserProfile?.name}
                        </div>
                      </div>
                    </div>

                    <button
                      onClick={() => {
                        onShowAppearance("personalization");
                        onClose();
                      }}
                      className="w-full flex items-center gap-3 px-4 py-3 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                    >
                      <Sparkles size={16} /> 个性化
                    </button>

                     {/* [New] Change password button */}
                    <button
                       onClick={() => {
                         setIsChangePasswordOpen(true);
                         setIsProfileExpanded(false);
                       }}
                       className="w-full flex items-center gap-3 px-4 py-3 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                    >
                      <Lock size={16} /> 修改密码
                    </button>
{isAdmin && (
                      <button
                        onClick={() => {
                          setIsProfileExpanded(false);
                          window.location.href = "/admin";
                        }}
                        className="w-full flex items-center gap-3 px-4 py-3 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                      >
                        <Server size={16} /> 管理员后台
                      </button>
                    )}


                    <button
                      onClick={() => {
                        onShowAppearance("general");
                        onClose();
                      }}
                      className="w-full flex items-center gap-3 px-4 py-3 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                    >
                      <Settings size={16} /> 设置
                    </button>

                    <div className="h-px bg-gray-100 dark:bg-gray-700 my-1"></div>

                    <button
                      onClick={onLogout}
                      className="w-full flex items-center gap-3 px-4 py-3 text-sm text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                    >
                      <LogOut size={16} /> 注销
                    </button>
                  </div>
                </div>

                {isLoading ? (
                  <ProfileCardSkeleton />
                ) : (
                  <button
                    onClick={() => setIsProfileExpanded(!isProfileExpanded)}
                    className={`w-full flex items-center gap-3 p-2 rounded-lg transition-colors border ${
                      isProfileExpanded ? "bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 shadow-sm" : "border-transparent hover:bg-gray-200 dark:hover:bg-gray-800"
                    }`}
                  >
                    <div className="w-9 h-9 rounded-full bg-blue-500 flex items-center justify-center text-white text-sm font-bold flex-shrink-0 overflow-hidden">
                      {renderAvatar(localUserProfile?.avatar)}
                    </div>
                    <div className="flex-1 text-left min-w-0">
                      <div className="text-sm font-bold text-gray-900 dark:text-white truncate">{localUserProfile?.name || 'User'}</div>
                      <div className="text-xs text-gray-500 dark:text-gray-400">{localUserProfile?.plan || "Enterprise"}</div>
                    </div>
                    <ChevronDown size={16} className={`text-gray-400 transition-transform ${isProfileExpanded ? "rotate-180" : ""}`} />
                  </button>
                )}
              </div>
            </>
          )}
        </div>

        <Suspense fallback={null}>
          <EditProfileModal
              isOpen={isEditProfileOpen}
              onClose={() => setIsEditProfileOpen(false)}
              userProfile={localUserProfile || {}}
              onSave={handleUpdateProfile}
          />
          {/* [New] Change password modal */}
          <ChangePasswordModal
            isOpen={isChangePasswordOpen}
            onClose={() => setIsChangePasswordOpen(false)}
          />
          <ShareModal
            isOpen={shareModal.isOpen}
            onClose={() => setShareModal({ isOpen: false, sessionId: null, title: "" })}
            sessionId={shareModal.sessionId}
            sessionTitle={shareModal.title}
            userId={localUserProfile?.id || "anonymous"}
          />
        </Suspense>
      </div>
    </>
  );
});

export default MobileSidebar;
