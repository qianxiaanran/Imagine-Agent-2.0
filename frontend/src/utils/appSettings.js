export const APP_SETTINGS_STORAGE_KEY = "app_settings_v2";
export const APP_SETTINGS_UPDATED_EVENT = "app-settings-updated";

export const DEFAULT_APP_SETTINGS = {
  desktopNotifications: false,
  enterToSend: true,
  showAdvancedModels: true,
  autoReadReplies: false,
  replyLanguage: "zh-CN",
  voiceName: "auto",
  styleTone: "default",
  traitWarm: "default",
  traitEnthusiasm: "default",
  traitTitles: "default",
  traitEmoji: "default",
  customInstruction: "",
  aboutNickname: "",
};

const ALLOWED_STYLE_TONES = new Set(["default", "concise", "warm", "direct"]);
const ALLOWED_TRAITS = new Set(["default", "low", "medium", "high"]);
const ALLOWED_LANGUAGES = new Set(["zh-CN", "en-US"]);

const normalizeBoolean = (value, fallback) => {
  if (typeof value === "boolean") return value;
  return fallback;
};

const normalizeText = (value, maxLen = 300) => {
  if (typeof value !== "string") return "";
  return value.trim().slice(0, maxLen);
};

export const normalizeAppSettings = (input = {}) => {
  const raw = input || {};
  const styleTone = ALLOWED_STYLE_TONES.has(raw.styleTone) ? raw.styleTone : DEFAULT_APP_SETTINGS.styleTone;
  const traitWarm = ALLOWED_TRAITS.has(raw.traitWarm) ? raw.traitWarm : DEFAULT_APP_SETTINGS.traitWarm;
  const traitEnthusiasm = ALLOWED_TRAITS.has(raw.traitEnthusiasm) ? raw.traitEnthusiasm : DEFAULT_APP_SETTINGS.traitEnthusiasm;
  const traitTitles = ALLOWED_TRAITS.has(raw.traitTitles) ? raw.traitTitles : DEFAULT_APP_SETTINGS.traitTitles;
  const traitEmoji = ALLOWED_TRAITS.has(raw.traitEmoji) ? raw.traitEmoji : DEFAULT_APP_SETTINGS.traitEmoji;
  const replyLanguage = ALLOWED_LANGUAGES.has(raw.replyLanguage) ? raw.replyLanguage : DEFAULT_APP_SETTINGS.replyLanguage;

  return {
    ...DEFAULT_APP_SETTINGS,
    desktopNotifications: normalizeBoolean(raw.desktopNotifications, DEFAULT_APP_SETTINGS.desktopNotifications),
    enterToSend: normalizeBoolean(raw.enterToSend, DEFAULT_APP_SETTINGS.enterToSend),
    showAdvancedModels: normalizeBoolean(raw.showAdvancedModels, DEFAULT_APP_SETTINGS.showAdvancedModels),
    autoReadReplies: normalizeBoolean(raw.autoReadReplies, DEFAULT_APP_SETTINGS.autoReadReplies),
    replyLanguage,
    voiceName: normalizeText(raw.voiceName, 120) || DEFAULT_APP_SETTINGS.voiceName,
    styleTone,
    traitWarm,
    traitEnthusiasm,
    traitTitles,
    traitEmoji,
    customInstruction: normalizeText(raw.customInstruction, 600),
    aboutNickname: normalizeText(raw.aboutNickname, 80),
  };
};

export const loadAppSettings = () => {
  try {
    const raw = localStorage.getItem(APP_SETTINGS_STORAGE_KEY);
    if (!raw) return { ...DEFAULT_APP_SETTINGS };
    const parsed = JSON.parse(raw);
    return normalizeAppSettings(parsed);
  } catch {
    return { ...DEFAULT_APP_SETTINGS };
  }
};

export const saveAppSettings = (settings) => {
  const normalized = normalizeAppSettings(settings);
  localStorage.setItem(APP_SETTINGS_STORAGE_KEY, JSON.stringify(normalized));
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(APP_SETTINGS_UPDATED_EVENT, { detail: normalized }));
  }
  return normalized;
};

export const buildChatPersonalizationPayload = (settings) => {
  const normalized = normalizeAppSettings(settings);
  return {
    styleTone: normalized.styleTone,
    traitWarm: normalized.traitWarm,
    traitEnthusiasm: normalized.traitEnthusiasm,
    traitTitles: normalized.traitTitles,
    traitEmoji: normalized.traitEmoji,
    customInstruction: normalized.customInstruction,
    aboutNickname: normalized.aboutNickname,
    replyLanguage: normalized.replyLanguage,
  };
};

