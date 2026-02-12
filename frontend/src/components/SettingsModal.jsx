import React, { useEffect, useRef, useState } from "react";
import {
  X,
  Settings,
  Bell,
  Sparkles,
  User,
  ChevronDown,
  Check,
  LogOut,
  RotateCcw,
} from "lucide-react";
import { useTheme } from "../context/ThemeContext";
import {
  APP_SETTINGS_STORAGE_KEY,
  DEFAULT_APP_SETTINGS,
  loadAppSettings,
  normalizeAppSettings,
  saveAppSettings,
} from "../utils/appSettings";

const CATEGORIES = [
  { id: "general", label: "常规", icon: Settings },
  { id: "notifications", label: "通知", icon: Bell },
  { id: "personalization", label: "个性化", icon: Sparkles },
  { id: "account", label: "账户", icon: User },
];

const STYLE_OPTIONS = [
  { value: "default", label: "默认" },
  { value: "concise", label: "简洁专业" },
  { value: "warm", label: "温和体贴" },
  { value: "direct", label: "直接果断" },
];

const TRAIT_OPTIONS = [
  { value: "default", label: "默认" },
  { value: "low", label: "较少" },
  { value: "medium", label: "适中" },
  { value: "high", label: "较多" },
];

const LANGUAGE_OPTIONS = [
  { value: "zh-CN", label: "简体中文" },
  { value: "en-US", label: "English" },
];

const InlineSelect = ({ value, options, onChange }) => {
  const [isOpen, setIsOpen] = useState(false);
  const rootRef = useRef(null);
  const selectedOption = options.find((item) => item.value === value) || options[0];

  useEffect(() => {
    if (!isOpen) return undefined;
    const handlePointerDown = (event) => {
      if (!rootRef.current?.contains(event.target)) {
        setIsOpen(false);
      }
    };
    const handleEscape = (event) => {
      if (event.key === "Escape") {
        setIsOpen(false);
      }
    };

    window.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("keydown", handleEscape);
    return () => {
      window.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("keydown", handleEscape);
    };
  }, [isOpen]);

  return (
    <div ref={rootRef} className="relative inline-flex">
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className="inline-flex min-w-[102px] items-center justify-between gap-2 rounded-full border border-gray-200/90 bg-gray-100/85 px-3 py-1.5 text-sm text-gray-800 transition-colors duration-150 hover:bg-gray-200/80 active:bg-gray-200 dark:border-gray-700/90 dark:bg-gray-800/90 dark:text-gray-100 dark:hover:bg-gray-700/85 dark:active:bg-gray-700"
      >
        <span className="truncate">{selectedOption?.label || value}</span>
        <ChevronDown
          size={14}
          className={`text-gray-500 transition-transform duration-150 dark:text-gray-300 ${isOpen ? "rotate-180" : ""}`}
        />
      </button>

      {isOpen && (
        <div className="absolute right-0 top-full z-20 mt-2 min-w-[170px] rounded-2xl border border-gray-200/90 bg-white/95 p-1.5 shadow-xl backdrop-blur-xl dark:border-gray-700/80 dark:bg-[#2f2f2f]/95">
          {options.map((item) => {
            const active = item.value === value;
            return (
              <button
                key={item.value}
                type="button"
                onClick={() => {
                  onChange(item.value);
                  setIsOpen(false);
                }}
                className={`flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-sm transition-colors duration-150 ${
                  active
                    ? "bg-gray-200 text-gray-900 dark:bg-gray-700 dark:text-white"
                    : "text-gray-700 hover:bg-gray-100 active:bg-gray-200 dark:text-gray-200 dark:hover:bg-gray-800 dark:active:bg-gray-700"
                }`}
              >
                <span>{item.label}</span>
                {active ? <Check size={14} className="text-gray-700 dark:text-gray-100" /> : null}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};

const Toggle = ({ checked, onChange }) => (
  <button
    type="button"
    aria-pressed={checked}
    onClick={() => onChange(!checked)}
    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
      checked ? "bg-gray-900 dark:bg-white" : "bg-gray-300 dark:bg-gray-700"
    }`}
  >
    <span
      className={`inline-block h-5 w-5 transform rounded-full bg-white dark:bg-gray-900 transition-transform ${
        checked ? "translate-x-5" : "translate-x-1"
      }`}
    />
  </button>
);

const Row = ({ label, description, children }) => (
  <div className="py-4 border-b border-gray-200 dark:border-gray-800">
    <div className="flex items-start justify-between gap-4">
      <div className="min-w-0">
        <div className="text-[16px] text-gray-900 dark:text-gray-100">{label}</div>
        {description ? <p className="mt-1 text-sm text-gray-500 dark:text-gray-400 leading-relaxed">{description}</p> : null}
      </div>
      <div className="flex-shrink-0">{children}</div>
    </div>
  </div>
);

const SettingsModal = ({
  isOpen,
  onClose,
  initialCategory = "general",
  userProfile,
  onLogout,
  onSettingsChange,
}) => {
  const { theme, setTheme } = useTheme();
  const [activeCategory, setActiveCategory] = useState(initialCategory || "general");
  const [settings, setSettings] = useState(loadAppSettings);
  const [voiceOptions, setVoiceOptions] = useState([{ value: "auto", label: "自动选择" }]);

  useEffect(() => {
    if (!isOpen) return;
    setActiveCategory(initialCategory || "general");
    setSettings(loadAppSettings());
  }, [isOpen, initialCategory]);

  useEffect(() => {
    const normalized = saveAppSettings(settings);
    onSettingsChange?.(normalized);
  }, [settings, onSettingsChange]);

  useEffect(() => {
    if (!settings.aboutNickname && userProfile?.name) {
      setSettings((prev) => ({ ...prev, aboutNickname: userProfile.name }));
    }
  }, [userProfile?.name, settings.aboutNickname]);

  useEffect(() => {
    if (typeof window === "undefined" || !window.speechSynthesis) return undefined;
    const synth = window.speechSynthesis;

    const refreshVoices = () => {
      const voices = synth.getVoices() || [];
      const mapped = voices
        .filter((voice) => voice && voice.name)
        .map((voice) => ({
          value: voice.name,
          label: `${voice.name} (${voice.lang || "unknown"})`,
        }));
      const unique = [];
      const seen = new Set();
      mapped.forEach((item) => {
        if (seen.has(item.value)) return;
        seen.add(item.value);
        unique.push(item);
      });
      const sorted = unique.sort((a, b) => {
        const aIsZh = /zh|cn/i.test(a.label);
        const bIsZh = /zh|cn/i.test(b.label);
        if (aIsZh !== bIsZh) return aIsZh ? -1 : 1;
        return a.label.localeCompare(b.label);
      });

      const options = [{ value: "auto", label: "自动选择" }, ...sorted];
      setVoiceOptions(options);
      if (settings.voiceName !== "auto" && !options.some((item) => item.value === settings.voiceName)) {
        setSettings((prev) => ({ ...prev, voiceName: "auto" }));
      }
    };

    refreshVoices();
    if (typeof synth.addEventListener === "function") {
      synth.addEventListener("voiceschanged", refreshVoices);
      return () => synth.removeEventListener("voiceschanged", refreshVoices);
    }

    synth.onvoiceschanged = refreshVoices;
    return () => {
      if (synth.onvoiceschanged === refreshVoices) synth.onvoiceschanged = null;
    };
  }, [settings.voiceName]);

  useEffect(() => {
    if (!isOpen) return undefined;
    const onKeyDown = (event) => {
      if (event.key === "Escape") onClose();
    };
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow || "";
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [isOpen, onClose]);

  const updateSetting = (key, value) => {
    setSettings((prev) => normalizeAppSettings({ ...prev, [key]: value }));
  };

  const resetLocalSettings = () => {
    localStorage.removeItem(APP_SETTINGS_STORAGE_KEY);
    setTheme("system");
    setSettings({ ...DEFAULT_APP_SETTINGS, aboutNickname: userProfile?.name || "" });
  };

  const requestAndSetNotification = async (next) => {
    if (!next) {
      updateSetting("desktopNotifications", false);
      return;
    }
    if (typeof window === "undefined" || !("Notification" in window)) {
      updateSetting("desktopNotifications", false);
      return;
    }
    if (Notification.permission === "granted") {
      updateSetting("desktopNotifications", true);
      return;
    }
    const result = await Notification.requestPermission();
    updateSetting("desktopNotifications", result === "granted");
  };

  const sendTestNotification = () => {
    if (typeof window === "undefined" || !("Notification" in window)) return;
    if (Notification.permission !== "granted") return;
    // eslint-disable-next-line no-new
    new Notification("设置通知测试", {
      body: "通知已开启，后续会在回复完成或关键任务完成时提醒你。",
    });
  };

  if (!isOpen) return null;

  const currentCategory = CATEGORIES.find((item) => item.id === activeCategory) || CATEGORIES[0];
  const voiceSelectOptions = voiceOptions;

  const renderGeneral = () => (
    <>
      <Row label="外观">
        <InlineSelect
          value={theme}
          onChange={setTheme}
          options={[
            { value: "system", label: "系统" },
            { value: "light", label: "浅色" },
            { value: "dark", label: "深色" },
          ]}
        />
      </Row>
      <Row label="回复语言" description="控制助手默认使用的输出语言。">
        <InlineSelect
          value={settings.replyLanguage}
          onChange={(v) => updateSetting("replyLanguage", v)}
          options={LANGUAGE_OPTIONS}
        />
      </Row>
      <Row label="回车发送" description="关闭后使用 Ctrl/Command + Enter 发送，Enter 仅换行。">
        <Toggle checked={settings.enterToSend} onChange={(v) => updateSetting("enterToSend", v)} />
      </Row>
      <Row label="显示其他业务模型" description="关闭后仅显示通用问答模型。">
        <Toggle checked={settings.showAdvancedModels} onChange={(v) => updateSetting("showAdvancedModels", v)} />
      </Row>
      <Row label="自动朗读回复" description="收到新回复后自动播放语音。">
        <Toggle checked={settings.autoReadReplies} onChange={(v) => updateSetting("autoReadReplies", v)} />
      </Row>
      <Row label="朗读声音" description="用于消息朗读和自动朗读。">
        <InlineSelect
          value={settings.voiceName}
          onChange={(v) => updateSetting("voiceName", v)}
          options={voiceSelectOptions}
        />
      </Row>
      <Row label="重置本地设置" description="清空当前设备保存的配置，不影响历史聊天记录。">
        <button
          type="button"
          onClick={resetLocalSettings}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800"
        >
          <RotateCcw size={14} /> 重置
        </button>
      </Row>
    </>
  );

  const renderNotifications = () => (
    <>
      <Row label="桌面通知" description="回复完成时可在系统通知栏提醒。">
        <Toggle checked={settings.desktopNotifications} onChange={requestAndSetNotification} />
      </Row>
      <Row label="发送测试通知">
        <button
          type="button"
          onClick={sendTestNotification}
          disabled={!settings.desktopNotifications}
          className="px-3 py-1.5 rounded-md text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          测试
        </button>
      </Row>
    </>
  );

  const renderPersonalization = () => (
    <>
      <Row
        label="基本风格和语调"
        description="设置助手回复你的风格和语调。"
      >
        <InlineSelect value={settings.styleTone} onChange={(v) => updateSetting("styleTone", v)} options={STYLE_OPTIONS} />
      </Row>

      <div className="pt-4 pb-2">
        <h4 className="text-[16px] text-gray-900 dark:text-gray-100">特征</h4>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">在基本风格和语调的基础上选择额外的自定义项。</p>
      </div>

      <Row label="温和体贴">
        <InlineSelect value={settings.traitWarm} onChange={(v) => updateSetting("traitWarm", v)} options={TRAIT_OPTIONS} />
      </Row>
      <Row label="热情洋溢">
        <InlineSelect value={settings.traitEnthusiasm} onChange={(v) => updateSetting("traitEnthusiasm", v)} options={TRAIT_OPTIONS} />
      </Row>
      <Row label="标题和列表">
        <InlineSelect value={settings.traitTitles} onChange={(v) => updateSetting("traitTitles", v)} options={TRAIT_OPTIONS} />
      </Row>
      <Row label="表情符号">
        <InlineSelect value={settings.traitEmoji} onChange={(v) => updateSetting("traitEmoji", v)} options={TRAIT_OPTIONS} />
      </Row>

      <div className="pt-5">
        <h4 className="text-[16px] text-gray-900 dark:text-gray-100 mb-2">自定义指令</h4>
        <textarea
          rows={3}
          value={settings.customInstruction}
          onChange={(e) => updateSetting("customInstruction", e.target.value)}
          placeholder="其他行为、风格和语调偏好设置"
          className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-sm text-gray-800 dark:text-gray-200 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-300 dark:focus:ring-gray-600"
        />
      </div>

      <div className="pt-7">
        <h4 className="text-[16px] text-gray-900 dark:text-gray-100">关于你</h4>
      </div>
      <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-800">
        <label className="block text-[16px] text-gray-900 dark:text-gray-100 mb-2">昵称</label>
        <input
          value={settings.aboutNickname}
          onChange={(e) => updateSetting("aboutNickname", e.target.value)}
          placeholder="你希望助手如何称呼你"
          className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-sm text-gray-800 dark:text-gray-200 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-gray-300 dark:focus:ring-gray-600"
        />
      </div>
    </>
  );

  const renderAccount = () => (
    <>
      <Row label="账号名称">
        <span className="text-sm text-gray-700 dark:text-gray-300">{userProfile?.name || "User"}</span>
      </Row>
      <Row label="账号 ID">
        <span className="text-sm text-gray-500 dark:text-gray-400">{userProfile?.id || "anonymous"}</span>
      </Row>
      <Row label="退出登录">
        <button
          type="button"
          onClick={() => {
            onClose();
            onLogout?.();
          }}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20"
        >
          <LogOut size={14} /> 退出
        </button>
      </Row>
    </>
  );

  const renderContent = () => {
    if (activeCategory === "general") return renderGeneral();
    if (activeCategory === "notifications") return renderNotifications();
    if (activeCategory === "personalization") return renderPersonalization();
    return renderAccount();
  };

  return (
    <div className="fixed inset-0 z-[110] flex items-center justify-center p-4 animate-in fade-in duration-150">
      <div className="absolute inset-0 bg-black/35 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-[min(920px,94vw)] h-[min(86vh,700px)] bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 shadow-2xl overflow-hidden">
        <div className="h-full grid grid-cols-1 md:grid-cols-[185px_1fr]">
          <aside className="hidden md:flex flex-col border-r border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-900/60 p-3">
            <button
              type="button"
              onClick={onClose}
              className="w-8 h-8 mb-3 rounded-lg flex items-center justify-center text-gray-500 hover:bg-gray-200/70 dark:hover:bg-gray-800"
            >
              <X size={18} />
            </button>
            <div className="space-y-1 overflow-y-auto">
              {CATEGORIES.map((item) => {
                const Icon = item.icon;
                const active = activeCategory === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setActiveCategory(item.id)}
                    className={`w-full px-3 py-2 rounded-lg text-sm flex items-center gap-2 transition-colors ${
                      active
                        ? "bg-white dark:bg-gray-800 text-gray-900 dark:text-white shadow-sm"
                        : "text-gray-600 dark:text-gray-300 hover:bg-gray-200/70 dark:hover:bg-gray-800"
                    }`}
                  >
                    <Icon size={16} />
                    <span>{item.label}</span>
                  </button>
                );
              })}
            </div>
          </aside>

          <section className="h-full overflow-y-auto">
            <div className="md:hidden sticky top-0 z-10 bg-white/95 dark:bg-gray-900/95 backdrop-blur border-b border-gray-200 dark:border-gray-800 p-3">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-base font-semibold text-gray-900 dark:text-white">{currentCategory.label}</h3>
                <button
                  type="button"
                  onClick={onClose}
                  className="w-8 h-8 rounded-lg flex items-center justify-center text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"
                >
                  <X size={18} />
                </button>
              </div>
              <div className="flex gap-2 overflow-x-auto no-scrollbar">
                {CATEGORIES.map((item) => {
                  const Icon = item.icon;
                  const active = activeCategory === item.id;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => setActiveCategory(item.id)}
                      className={`flex-shrink-0 px-3 py-1.5 rounded-full text-xs flex items-center gap-1.5 ${
                        active
                          ? "bg-gray-900 text-white dark:bg-white dark:text-gray-900"
                          : "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300"
                      }`}
                    >
                      <Icon size={12} />
                      {item.label}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="px-5 md:px-7 py-5 md:py-6">
              <div className="hidden md:flex items-center pb-4 border-b border-gray-200 dark:border-gray-800">
                <h2 className="text-[34px] leading-none font-semibold text-gray-900 dark:text-white">{currentCategory.label}</h2>
              </div>
              {renderContent()}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
};

export default SettingsModal;


