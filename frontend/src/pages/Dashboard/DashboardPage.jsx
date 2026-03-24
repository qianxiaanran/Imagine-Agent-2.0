import React, { useState, useEffect, useLayoutEffect, useRef, Suspense, lazy, useMemo, useCallback } from 'react';
import {
  Bot, Zap, FileText, Layout, PanelLeftOpen, ChevronDown, Check, User,
  BookOpen, X, Mic, StopCircle, ArrowRight, Plus,
  Loader2, Sparkles, Database, Download, ScanText,
  ClipboardCheck, Mail, ArrowLeft, Share2, Copy, PencilLine, Presentation,
  TrendingUp, AlertTriangle, Play, Image as ImageIcon,
  Volume2, File as FileIcon,
  ThumbsUp, ThumbsDown, Square, RefreshCw, Globe, Star, Trash2,
  FileUp, Cloud, Cpu
} from 'lucide-react';

// 原料药进口
import { API_BASE_URL, AUTH_TOKEN_KEY, refreshAccessToken as refreshAccessTokenFromApiClient } from '../../api/apiClient';
import userApi from '../../api/user';
import historyApi from '../../api/history';
import chatFeedbackApi from '../../api/chatFeedback';
import presentationApi from '../../api/presentation';
import { convertWebMToWav } from '../../utils/audio';
import {
  HISTORY_PAGE_SIZE,
  normalizeHistoryChatMessages,
  useSessionHistoryPagination,
} from './useSessionHistoryPagination';
import {
  StandalonePptSelect,
  StandaloneTemplatePreviewCard,
} from './StandalonePptWidgets';
import WritingEntryHub from './WritingEntryHub';
import DashboardEmptyState from './DashboardEmptyState';
import DashboardGlobalOverlays from './DashboardGlobalOverlays';
import DashboardModePanelHost from './DashboardModePanelHost';
import DashboardOcrSummaryModal from './DashboardOcrSummaryModal';
import DashboardSidebars from './DashboardSidebars';
import DashboardTopbar from './DashboardTopbar';
import {
  APP_SETTINGS_UPDATED_EVENT,
  DEFAULT_APP_SETTINGS,
  loadAppSettings,
  normalizeAppSettings,
  buildChatPersonalizationPayload
} from '../../utils/appSettings';
import LoadingScreen from '../../components/LoadingScreen';

const SettingsModal = lazy(() => import('../../components/SettingsModal'));
const VoiceRecorder = lazy(() => import('../../components/VoiceRecorder'));
const ShareModal = lazy(() => import('./ShareModal'));
const OcrIngestModal = lazy(() => import('./OcrIngestModal'));
const MarkdownRenderer = lazy(() => import('./MarkdownRenderer'));
const SourcePanel = lazy(() => import('./SourcePanel'));
const TaskCenterPopover = lazy(() => import('./TaskCenterPopover'));

const INITIAL_MESSAGE_COUNT = 20;
const MARKDOWN_MESSAGE_COUNT = 6;
const AUDIT_DOC_TYPES = [
  { value: '', label: '自动识别' },
  { value: 'invoice', label: '发票' },
  { value: 'contract', label: '合同' },
  { value: 'payment', label: '付款单' },
  { value: 'expense', label: '报销单' },
];
const AUDIT_POLL_INTERVAL = 1500;
const INSTANT_TRANSCRIBE_MAX_SECONDS = 75;
const HISTORY_FIRST_PAINT_COUNT = 6;
// 常量 STREAM_UI_THROTTLE_MS = 24; // 已删除：不再使用油门
const STREAM_UI_FLUSH_MS = 12;
const MAX_CONTEXT_CHARS = 6000;
const OCR_SUMMARY_MAX_CONTEXT_CHARS = 32000;
const OCR_SUMMARY_STREAM_TIMEOUT_MS = 180000;
const OCR_SUMMARY_IDLE_TIMEOUT_MS = 90000;
const OCR_SUMMARY_RETRY_LIMIT = 1;
const OCR_SUMMARY_RETRY_DELAY_MS = 800;
const OCR_SUMMARY_DEFAULT_PROMPT = "请总结文档内容，给出结构化要点和结论。";
const OCR_SUMMARY_BACKEND_OPTIONS = [
  { value: "local", label: "Qwen 2.5-coder" },
  { value: "cloud", label: "DeepSeek（云端）" },
];
const USER_MARKDOWN_HINT_RE = /```|`[^`]+`|\[[^\]]+\]\([^)]+\)|(^|\n)\s*[-*+]\s|(^|\n)\s*\d+\.\s|(^|\n)\s*>|(^|\n)\s*#|(^|\n)\s*\|.+\|\s*(\n|$)|(^|\n)\s*[-:\s|]{3,}\|[-:\s|]*/;
const WRITING_FORM_AUDIENCE_LIMIT = 10;
const WRITING_CONTENT_TYPE_OPTIONS = ["营销文案", "功能发布公告", "产品介绍", "活动邀请函", "客户案例故事"];
const WRITING_PLATFORM_OPTIONS = ["微信公众号", "企业微信", "官网", "小红书", "抖音", "LinkedIn", "邮件触达"];
const WRITING_AUDIENCE_PRESET = ["外贸业务员", "采购负责人", "运营主管", "财务/合规", "管理层", "跨境电商团队"];
const WRITING_TONE_OPTIONS = ["专业严谨", "商务简洁", "数据驱动", "亲和易读", "行动导向"];
const STANDALONE_PPT_INPUT_MODES = [
  { key: "topic", label: "输入PPT主题", icon: Sparkles },
  { key: "document", label: "上传文档生成PPT", icon: FileUp },
  { key: "longText", label: "大段文本生成PPT", icon: FileText },
];
const STANDALONE_PPT_DEFAULT_CONTENT_FOCUS = "work_report";
const STANDALONE_PPT_CONTENT_FOCUS_OPTIONS = [
  {
    key: "work_report",
    label: "工作汇报",
    description: "适合阶段总结、项目复盘、进展同步",
    emphasizeMetrics: true,
    previewSections: ["封面", "汇报摘要", "目录", "背景与目标", "阶段进展", "核心成果", "问题与挑战", "原因复盘", "改进动作", "下一步计划", "资源诉求", "总结"],
    promptLines: [
      "内容导向：工作汇报，适合周报、月报、阶段复盘、项目总结类 PPT。",
      "结构重点：交代目标背景、阶段进展、关键成果、存在问题、复盘原因和下一步计划。",
      "表达方式：结论前置，结果清晰，既能支撑管理汇报，也便于团队同步。",
      "页面组织：优先使用结论式标题，每页围绕一个核心信息展开，再补充事实、数据和行动要点。",
    ],
  },
  {
    key: "proposal",
    label: "方案提案",
    description: "适合项目方案、解决方案、立项汇报",
    emphasizeMetrics: true,
    previewSections: ["封面", "提案摘要", "目录", "现状痛点", "目标与原则", "方案总览", "关键模块", "实施路径", "资源与分工", "收益评估", "风险保障", "结论"],
    promptLines: [
      "内容导向：方案提案，适合项目立项、解决方案、实施建议类 PPT。",
      "结构重点：讲清现状痛点、目标原则、方案设计、实施路径、资源需求、收益与风险。",
      "表达方式：强调决策价值和可执行性，让听众能快速判断是否推进。",
      "页面组织：优先使用问题-方案-收益的表达顺序，让每页都能服务于决策判断。",
    ],
  },
  {
    key: "analysis",
    label: "分析解读",
    description: "适合研究分析、行业洞察、专题汇报",
    emphasizeMetrics: true,
    previewSections: ["封面", "核心结论", "目录", "研究背景", "现状与趋势", "关键数据", "原因拆解", "对比分析", "洞察发现", "策略建议", "风险提示", "总结"],
    promptLines: [
      "内容导向：分析解读，适合行业研究、专题分析、经营复盘类 PPT。",
      "结构重点：基于事实和数据得出洞察，形成结论、判断与建议。",
      "表达方式：强调逻辑链和证据链，避免只有结论没有支撑。",
      "页面组织：优先使用结论-证据-影响的表达顺序，让听众能快速跟上分析逻辑。",
    ],
  },
  {
    key: "training",
    label: "培训讲解",
    description: "适合课程分享、制度讲解、方法培训",
    emphasizeMetrics: false,
    previewSections: ["封面", "培训目标", "目录", "概念导入", "知识拆解", "方法步骤", "案例演示", "常见问题", "注意事项", "实操建议", "练习复盘", "总结"],
    promptLines: [
      "内容导向：培训讲解，适合课程分享、制度宣讲、方法培训类 PPT。",
      "结构重点：概念解释、知识拆解、步骤演示、案例说明、注意事项和练习复盘。",
      "表达方式：更注重可理解性和可学习性，内容要循序渐进。",
      "页面组织：优先使用概念-步骤-示例-提醒的表达顺序，帮助听众边看边学。",
    ],
  },
  {
    key: "product_pitch",
    label: "产品路演",
    description: "适合产品介绍、业务路演、价值展示",
    emphasizeMetrics: true,
    previewSections: ["封面", "一句话价值", "目录", "用户场景", "痛点机会", "产品方案", "核心亮点", "竞争优势", "商业价值", "客户案例", "实施计划", "结语"],
    promptLines: [
      "内容导向：产品路演，适合产品介绍、业务宣讲、商业展示类 PPT。",
      "结构重点：说明场景与痛点、产品价值、核心亮点、竞争优势、商业价值和落地计划。",
      "表达方式：强调价值主张和说服力，让听众快速理解卖点。",
      "页面组织：优先使用场景-价值-亮点-证明的表达顺序，让页面更有路演说服力。",
    ],
  },
];

function useStableCallback(callback) {
  const callbackRef = useRef(callback);

  useLayoutEffect(() => {
    callbackRef.current = callback;
  }, [callback]);

  return useCallback((...args) => callbackRef.current?.(...args), []);
}

const extractOcrLinesFromPayload = (data) => {
  if (!data) return [];
  return data.lines
    || data?.data?.lines
    || data?.ocrData?.lines
    || data?.ocrData?.data?.lines
    || [];
};

const extractOcrTextFromPayload = (data) => {
  if (!data) return '';
  return data.text
    || data?.data?.text
    || data?.result?.text
    || '';
};

const extractOcrPagesFromPayload = (data) => {
  if (!data) return [];
  return data.pages
    || data?.data?.pages
    || data?.ocrData?.pages
    || data?.ocrData?.data?.pages
    || [];
};

const resolveOcrLinesForFile = (file) => {
  if (!file) return [];
  if (Array.isArray(file.lines) && file.lines.length) return file.lines;
  const dataLines = extractOcrLinesFromPayload(file.ocrData);
  if (Array.isArray(dataLines) && dataLines.length) return dataLines;
  const text = file.ocrText || extractOcrTextFromPayload(file.ocrData);
  return (text || '')
    .split(/\r?\n/)
    .filter((line) => line.trim())
    .map((textLine) => ({ text: textLine }));
};
const STANDALONE_PPT_TOPIC_SUGGESTIONS = ["学术报告", "教学备课", "政策宣讲", "心得体会分享", "工作总结"];
const STANDALONE_PPT_TOPIC_SUGGESTION_PROMPTS = {
  "学术报告": "PPT主题：\n研究对象：\n希望突出：研究背景、方法思路、核心结论",
  "教学备课": "PPT主题：\n适用课程：\n希望突出：教学目标、重点难点、课堂安排",
  "政策宣讲": "PPT主题：\n适用范围：\n希望突出：政策背景、关键要点、落实建议",
  "心得体会分享": "PPT主题：\n分享场景：\n希望突出：主要经历、体会收获、后续行动",
  "工作总结": "PPT主题：\n时间范围/项目：\n希望突出：重点成果、问题复盘、下一步计划",
};
const STANDALONE_PPT_TEMPLATE_ID_ALIASES = {
  corporate: "standard",
  minimal: "modern",
};
const STANDALONE_PPT_TEMPLATE_ORDER = [
  "neo-general",
  "neo-standard",
  "neo-modern",
  "neo-swift",
  "general",
  "modern",
  "standard",
  "swift",
];
const STANDALONE_PPT_BUILTIN_TEMPLATES = [
  { template_id: "neo-general", name: "Neo 通用", source: "builtin" },
  { template_id: "neo-standard", name: "Neo 标准", source: "builtin" },
  { template_id: "neo-modern", name: "Neo 现代", source: "builtin" },
  { template_id: "neo-swift", name: "Neo 迅捷", source: "builtin" },
  { template_id: "general", name: "经典通用", source: "builtin" },
  { template_id: "modern", name: "经典现代", source: "builtin" },
  { template_id: "standard", name: "经典标准", source: "builtin" },
  { template_id: "swift", name: "经典迅捷", source: "builtin" },
];
const STANDALONE_PPT_TEMPLATE_LABELS = {
  "neo-general": "Neo 通用",
  "neo-standard": "Neo 标准",
  "neo-modern": "Neo 现代",
  "neo-swift": "Neo 迅捷",
  general: "经典通用",
  modern: "经典现代",
  standard: "经典标准",
  swift: "经典迅捷",
  corporate: "经典标准",
  minimal: "经典现代",
};
const STANDALONE_PPT_TEMPLATE_PREVIEW_META = {
  "neo-general": {
    summary: "新版通用风格，适合综合汇报、日常演示与常规业务表达。",
    tags: ["新版", "平衡型", "综合汇报"],
    gradient: "from-sky-500 via-cyan-400 to-emerald-300",
    shell: "bg-[#0a2742]",
    slideTone: "bg-white/95",
    accentTone: "bg-sky-500",
    mutedTone: "bg-sky-100",
    linesTone: "bg-slate-300",
  },
  "neo-standard": {
    summary: "新版标准风格，章节层次更规整，适合正式汇报与制度宣讲。",
    tags: ["新版", "规整结构", "正式汇报"],
    gradient: "from-indigo-600 via-slate-500 to-slate-300",
    shell: "bg-[#141b2d]",
    slideTone: "bg-white/95",
    accentTone: "bg-indigo-600",
    mutedTone: "bg-indigo-100",
    linesTone: "bg-slate-300",
  },
  "neo-modern": {
    summary: "新版现代风格，视觉更鲜明，适合方案展示、产品介绍与重点表达。",
    tags: ["新版", "视觉强化", "方案展示"],
    gradient: "from-fuchsia-500 via-rose-400 to-orange-300",
    shell: "bg-[#2a1231]",
    slideTone: "bg-white/95",
    accentTone: "bg-rose-500",
    mutedTone: "bg-rose-100",
    linesTone: "bg-slate-300",
  },
  "neo-swift": {
    summary: "新版迅捷风格，节奏更明快，适合路演展示、数据快报与结论先行表达。",
    tags: ["新版", "节奏明快", "路演展示"],
    gradient: "from-emerald-500 via-teal-400 to-lime-300",
    shell: "bg-[#0d2c29]",
    slideTone: "bg-white/95",
    accentTone: "bg-emerald-500",
    mutedTone: "bg-emerald-100",
    linesTone: "bg-slate-300",
  },
  general: {
    summary: "经典通用模板，适合常规商务汇报、周报月报和多场景演示。",
    tags: ["经典", "商务蓝", "多场景"],
    gradient: "from-sky-500 via-cyan-500 to-blue-300",
    shell: "bg-[#0f1b33]",
    slideTone: "bg-white/95",
    accentTone: "bg-sky-500",
    mutedTone: "bg-sky-100",
    linesTone: "bg-slate-300",
  },
  modern: {
    summary: "经典现代模板，适合产品介绍、品牌表达和较强视觉感的页面。",
    tags: ["经典", "现代感", "视觉型"],
    gradient: "from-violet-500 via-fuchsia-400 to-rose-300",
    shell: "bg-[#28163d]",
    slideTone: "bg-white/95",
    accentTone: "bg-fuchsia-500",
    mutedTone: "bg-fuchsia-100",
    linesTone: "bg-slate-300",
  },
  standard: {
    summary: "经典标准模板，适合制度宣讲、项目汇报、章节内容较重的文稿。",
    tags: ["经典", "正式感", "章节清晰"],
    gradient: "from-slate-700 via-slate-600 to-slate-300",
    shell: "bg-[#161c28]",
    slideTone: "bg-white",
    accentTone: "bg-slate-900",
    mutedTone: "bg-slate-100",
    linesTone: "bg-slate-200",
  },
  swift: {
    summary: "经典迅捷模板，适合快节奏汇报、数据概览与行动建议型页面。",
    tags: ["经典", "节奏快", "重点突出"],
    gradient: "from-amber-500 via-orange-400 to-yellow-200",
    shell: "bg-[#2b1e0f]",
    slideTone: "bg-white/95",
    accentTone: "bg-amber-500",
    mutedTone: "bg-amber-100",
    linesTone: "bg-slate-300",
  },
  corporate: {
    summary: "旧模板别名，已对应到经典标准模板。",
    tags: ["旧别名", "正式汇报"],
    gradient: "from-slate-700 via-slate-600 to-slate-300",
    shell: "bg-[#161c28]",
    slideTone: "bg-white",
    accentTone: "bg-slate-900",
    mutedTone: "bg-slate-100",
    linesTone: "bg-slate-200",
  },
  minimal: {
    summary: "旧模板别名，已对应到经典现代模板。",
    tags: ["旧别名", "视觉型"],
    gradient: "from-violet-500 via-fuchsia-400 to-rose-300",
    shell: "bg-[#28163d]",
    slideTone: "bg-white/95",
    accentTone: "bg-fuchsia-500",
    mutedTone: "bg-fuchsia-100",
    linesTone: "bg-slate-300",
  },
};
const normalizeStandalonePptTemplateId = (value) => {
  const templateId = String(value || "").trim();
  if (!templateId) return "";
  return STANDALONE_PPT_TEMPLATE_ID_ALIASES[templateId] || templateId;
};
const sortStandalonePptTemplateCatalog = (items) => {
  const templateOrderIndex = new Map(STANDALONE_PPT_TEMPLATE_ORDER.map((item, index) => [item, index]));
  return [...(Array.isArray(items) ? items : [])].sort((left, right) => {
    const leftId = normalizeStandalonePptTemplateId(left?.template_id || left?.id || "");
    const rightId = normalizeStandalonePptTemplateId(right?.template_id || right?.id || "");
    const leftIndex = templateOrderIndex.has(leftId) ? templateOrderIndex.get(leftId) : Number.MAX_SAFE_INTEGER;
    const rightIndex = templateOrderIndex.has(rightId) ? templateOrderIndex.get(rightId) : Number.MAX_SAFE_INTEGER;
    if (leftIndex !== rightIndex) return leftIndex - rightIndex;
    const leftName = String(left?.name || leftId || "").trim();
    const rightName = String(right?.name || rightId || "").trim();
    return leftName.localeCompare(rightName, "zh-CN");
  });
};
const getStandalonePptTemplateLabel = (template) => {
  const rawTemplateId = String(template?.template_id || template?.id || template || "").trim();
  const templateId = normalizeStandalonePptTemplateId(rawTemplateId);
  if (!templateId) return "";
  const fallbackName = typeof template === "object" && template
    ? String(template.name || template.template_name || "").trim()
    : "";
  return STANDALONE_PPT_TEMPLATE_LABELS[templateId] || STANDALONE_PPT_TEMPLATE_LABELS[rawTemplateId] || fallbackName || templateId;
};
const getStandalonePptTemplatePreviewMeta = (template) => {
  const rawTemplateId = String(template?.template_id || template?.id || template || "").trim();
  const templateId = normalizeStandalonePptTemplateId(rawTemplateId);
  return STANDALONE_PPT_TEMPLATE_PREVIEW_META[templateId]
    || STANDALONE_PPT_TEMPLATE_PREVIEW_META[rawTemplateId]
    || STANDALONE_PPT_TEMPLATE_PREVIEW_META.general;
};
const getStandalonePptContentFocusConfig = (focusKey) => {
  const rawValue = String(focusKey || '').trim();
  if (!rawValue) return STANDALONE_PPT_CONTENT_FOCUS_OPTIONS[0];
  return STANDALONE_PPT_CONTENT_FOCUS_OPTIONS.find((item) => item.key === rawValue)
    || STANDALONE_PPT_CONTENT_FOCUS_OPTIONS.find((item) => item.label === rawValue)
    || STANDALONE_PPT_CONTENT_FOCUS_OPTIONS[0];
};
const getStandalonePptTopicSuggestionPrompt = (topic) =>
  STANDALONE_PPT_TOPIC_SUGGESTION_PROMPTS[String(topic || "").trim()]
  || `PPT主题：\n内容方向：${String(topic || "").trim()}`;
const WRITING_CONSULTING_TYPE_OPTIONS = ["流程优化建议", "合规风控建议", "增长策略咨询", "系统落地方案"];
const WRITING_CONSULTING_ROLE_OPTIONS = ["管理层", "运营团队", "销售团队", "财务风控团队", "IT实施团队"];
const WRITING_OUTPUT_FORMAT_OPTIONS = ["执行清单", "分阶段计划", "OKR/KPI方案", "风险-对策矩阵"];
const WRITING_PROJECT_CONTEXT = "项目是 Enterprise Intelligent Office Agent 2.0，面向进出口企业，核心能力包括：智能对话、会议纪要、OCR识别、智能审单、企业数据库查询、数据决策驾驶舱，以及本地/云模型切换。";
const WRITING_FIELD_SUGGESTIONS = {
  report: {
    referenceContent: "围绕“企业智能办公助手”场景，突出会议纪要、OCR识别、智能审单、数据决策等能力，强调可在进出口企业真实业务中落地。",
    keywords: "进出口企业, 智能办公, 会议纪要, OCR识别, 智能审单",
  },
  ppt: {
    analysisInput: "PPT主题：进出口企业智能办公升级方案\n汇报目标：向管理层说明当前问题、建设思路、预期收益和推进计划。\n希望重点突出：效率提升、风险控制、跨部门协同和数据决策价值。",
  },
  email: {
    consultingContext: "公司准备将智能办公系统用于进出口业务全流程，需要给出可执行的落地建议。",
    consultingConstraints: "预算有限；需分阶段实施；合规优先；兼容现有流程。",
  },
};
const ONBOARDING_STORAGE_PREFIX = "onboarding_seen_v1_";
const ONBOARDING_MESSAGES = [
  "顶部左侧的模式下拉可切换到报告/PPT/邮件写作、会议纪要、OCR、审单等场景。",
  "左侧栏（手机点左上角菜单）有新建/搜索聊天和历史会话，知识库入口也在这里；输入框左侧“＋”用于上传文件并启用知识库/数据库/联网。这是我首次完成这种类型的项目，目前可能还有诸多bug，如有建议请联系我，我会尽可能改正，感谢使用！"
];
const MODEL_OPTIONS = [
  { id: 0, name: "通用助手", icon: Bot },
  { id: 1, name: "会议纪要", icon: Mic },
  { id: 2, name: "OCR 识别", icon: ScanText },
  { id: 3, name: "智能创作", icon: PencilLine },
  { id: 4, name: "智能审单", icon: ClipboardCheck }
];

const CONVERSATION_PATH_PREFIX = '/c/';

const isLikelyMarkdown = (text = '') => USER_MARKDOWN_HINT_RE.test(text);

const normalizePathname = (pathname = '/') => {
    const normalized = String(pathname || '/').replace(/\/+$/, '');
    return normalized || '/';
};

const extractConversationSessionId = (pathname = '') => {
    const normalizedPath = normalizePathname(pathname);
    if (!normalizedPath.startsWith(CONVERSATION_PATH_PREFIX)) return null;
    const encodedSessionId = normalizedPath.slice(CONVERSATION_PATH_PREFIX.length).split('/')[0];
    if (!encodedSessionId) return null;
    try {
        return decodeURIComponent(encodedSessionId);
    } catch {
        return encodedSessionId;
    }
};

const buildConversationPath = (sessionId) => {
    if (!sessionId) return '/';
    return `${CONVERSATION_PATH_PREFIX}${encodeURIComponent(String(sessionId))}`;
};

const PRESENTON_PROXY_PREFIX = '/api/presentation/presenton/proxy';
const PRESENTON_EMBED_PREFIX = '/api/presentation/presenton/embed';
const PRESENTON_LOCAL_HOSTS = new Set(['127.0.0.1', 'localhost', '0.0.0.0', 'host.docker.internal']);

const buildPresentonEmbedUrl = (targetUrl) => {
    const value = String(targetUrl || '').trim();
    if (!value) return '';
    if (value.startsWith(PRESENTON_EMBED_PREFIX)) {
        return value;
    }
    return `${PRESENTON_EMBED_PREFIX}?target=${encodeURIComponent(value)}`;
};

const normalizePresentonEditUrl = (rawUrl) => {
    const value = String(rawUrl || '').trim();
    if (!value) return '';
    if (value.startsWith(PRESENTON_EMBED_PREFIX)) {
        return value;
    }
    if (value.startsWith(PRESENTON_PROXY_PREFIX)) {
        return buildPresentonEmbedUrl(value);
    }
    if (value.startsWith('/')) {
        return buildPresentonEmbedUrl(value);
    }
    try {
        const parsed = new URL(value);
        if (!PRESENTON_LOCAL_HOSTS.has((parsed.hostname || '').toLowerCase())) {
            return value;
        }
        return buildPresentonEmbedUrl(`${PRESENTON_PROXY_PREFIX}${parsed.pathname}${parsed.search || ''}`);
    } catch {
        return value;
    }
};

const buildFallbackOutlineSlides = (count = 8) => {
    const safeCount = Math.max(3, Math.min(40, Number(count) || 8));
    return Array.from({ length: safeCount }, (_, idx) => ({
        index: idx + 1,
        title: `第 ${idx + 1} 页`,
        points: ["补充本页核心观点", "补充本页关键支撑信息"],
        notes: "",
    }));
};

const PPT_OUTLINE_PREVIEW_SECTIONS = getStandalonePptContentFocusConfig(STANDALONE_PPT_DEFAULT_CONTENT_FOCUS).previewSections;
const STANDALONE_PPT_METRIC_HINT_RE = /(\d+(?:\.\d+)?%|ROI|同比|环比|增长|下降|提升|万元|亿元|人天|小时|天|周|月|季度|年度)/i;
const STANDALONE_PPT_EVIDENCE_HINT_RE = /(数据|指标|案例|样本|调研|反馈|对比|图表|结果|证据|事实依据)/i;
const STANDALONE_PPT_ACTION_HINT_RE = /(行动|动作|计划|推进|执行|落实|安排|实施|优化|建议|下一步|里程碑)/i;
const STANDALONE_PPT_CONTEXT_HINT_RE = /(背景|现状|场景|目标|问题|痛点|机会|定义|范围|对象)/i;
const STANDALONE_PPT_EXAMPLE_HINT_RE = /(案例|示例|演示|场景|易错|注意事项|提醒)/i;
const STANDALONE_PPT_TIME_OWNER_HINT_RE = /(本周|本月|季度|年度|阶段|时间节点|里程碑|负责人|牵头|协同|部门|排期)/i;
const STANDALONE_PPT_AGENDA_TITLE_RE = /(目录|议程|章节安排|内容导航)/;
const STANDALONE_PPT_SUMMARY_TITLE_RE = /(汇报摘要|提案摘要|核心结论|总结|结语|一句话价值|汇报结论)/;
const STANDALONE_PPT_BACKGROUND_TITLE_RE = /(背景|目标|现状|场景|痛点|机会|研究背景|概念导入)/;
const STANDALONE_PPT_ISSUE_TITLE_RE = /(问题|挑战|风险|原因|复盘|难点|瓶颈|常见问题)/;
const STANDALONE_PPT_ACTION_TITLE_RE = /(方案|路径|动作|计划|建议|实施|分工|资源|下一步|实操建议|练习复盘)/;
const STANDALONE_PPT_TRAINING_TITLE_RE = /(知识拆解|方法步骤|案例演示|注意事项|实操建议|练习复盘)/;
const STANDALONE_PPT_GENERIC_POINT_RE = /^(补充|说明|围绕|提炼|介绍|梳理|分析|给出|明确|保留)/;
const STANDALONE_PPT_LANGUAGE_LEAK_RE = /\s*[·•｜|]\s*(?:Chinese|中文|简体中文|Simplified Chinese|zh-CN|zh_cn)\s*$/i;

const createIdlePresentonProgress = () => ({
    taskId: '',
    status: 'idle',
    progress: 0,
    message: '',
    previewLines: [],
    previewCursor: 0,
});

const sanitizeStandaloneHistoryLine = (value = '', maxLength = 300) =>
    String(value || '')
        .replace(/\r?\n+/g, '；')
        .replace(/\s+/g, ' ')
        .trim()
        .slice(0, maxLength);

const sanitizeStandaloneOutlineSubtitle = (value = '', focusLabel = '') => {
    const raw = String(value || '').replace(/\s+/g, ' ').trim();
    if (!raw) return '';
    const cleaned = raw
        .replace(STANDALONE_PPT_LANGUAGE_LEAK_RE, '')
        .replace(/^(?:language|语言)\s*[:：]\s*(?:Chinese|中文|简体中文|Simplified Chinese|zh-CN|zh_cn)\s*$/i, '')
        .trim();
    if (!cleaned) return '';
    const normalizedFocus = String(focusLabel || '').replace(/\s+/g, ' ').trim().toLowerCase();
    if (normalizedFocus && cleaned.toLowerCase() === normalizedFocus) {
        return '';
    }
    return cleaned;
};

const parseStructuredStandaloneOutlineHistory = (rawText = '') => {
    const lines = String(rawText || '')
        .split(/\r?\n/)
        .map((line) => String(line || '').trim())
        .filter(Boolean);
    if (!lines.length) return null;

    const headerMatch = lines[0].match(/\]\s*(.+?)(?:[（(]\s*(\d+)\s*页\s*[）)])?$/);
    const title = String(headerMatch?.[1] || '业务汇报').trim() || '业务汇报';
    let subtitle = '';
    let contentFocus = '';
    const slides = [];
    let currentSlide = null;

    const pushCurrentSlide = () => {
        if (!currentSlide?.title) return;
        slides.push({
            index: slides.length + 1,
            title: currentSlide.title,
            points: Array.isArray(currentSlide.points) && currentSlide.points.length
                ? currentSlide.points.slice(0, 10)
                : ["补充本页核心观点", "补充本页关键支撑信息"],
            notes: String(currentSlide.notes || '').trim(),
        });
    };

    lines.slice(1).forEach((line) => {
        if (line.startsWith('副标题：')) {
            subtitle = line.slice('副标题：'.length).trim();
            return;
        }
        if (line.startsWith('内容导向：')) {
            contentFocus = line.slice('内容导向：'.length).trim();
            return;
        }

        const slideMatch = line.match(/^(\d+)\.\s*(.+)$/);
        if (slideMatch) {
            pushCurrentSlide();
            currentSlide = {
                title: String(slideMatch[2] || '').trim(),
                points: [],
                notes: '',
            };
            return;
        }

        if (!currentSlide) return;
        if (/^(?:[-*•]|\u2022)\s*/.test(line)) {
            const point = line.replace(/^(?:[-*•]|\u2022)\s*/, '').trim();
            if (point) currentSlide.points.push(point);
            return;
        }
        if (/^(?:备注|讲解备注|讲解展开)[:：]\s*/.test(line)) {
            currentSlide.notes = line.replace(/^(?:备注|讲解备注|讲解展开)[:：]\s*/, '').trim();
        }
    });
    pushCurrentSlide();

    if (!slides.length) return null;
    return {
        title,
        subtitle: sanitizeStandaloneOutlineSubtitle(subtitle, contentFocus),
        contentFocus,
        slides,
    };
};

const formatStandaloneOutlineHistory = (outlinePayload, headerLabel = '[智能创作/PPT大纲]') => {
    const focusConfig = getStandalonePptContentFocusConfig(
        outlinePayload?.contentFocus || STANDALONE_PPT_DEFAULT_CONTENT_FOCUS,
    );
    const safeTitle = String(outlinePayload?.title || '业务汇报').trim() || '业务汇报';
    const normalized = {
        title: safeTitle,
        subtitle: sanitizeStandaloneOutlineSubtitle(
            outlinePayload?.subtitle || '',
            focusConfig?.label || '',
        ),
        slides: (Array.isArray(outlinePayload?.slides) ? outlinePayload.slides : [])
            .map((slide, idx) => ({
                index: idx + 1,
                title: String(slide?.title || `第 ${idx + 1} 页`).trim(),
                points: (Array.isArray(slide?.points) ? slide.points : [])
                    .map((item) => String(item || '').trim())
                    .filter(Boolean)
                    .slice(0, 10),
                notes: String(slide?.notes || '').trim(),
            }))
            .filter((slide) => slide.title),
    };
    const slides = Array.isArray(normalized?.slides) ? normalized.slides : [];
    const lines = [`${headerLabel} ${normalized.title || '业务汇报'}（${slides.length || 0}页）`];
    if (normalized.subtitle) {
        lines.push(`副标题：${sanitizeStandaloneHistoryLine(normalized.subtitle, 160)}`);
    }
    if (focusConfig?.label) {
        lines.push(`内容导向：${focusConfig.label}`);
    }
    slides.forEach((slide, idx) => {
        lines.push(`${idx + 1}. ${sanitizeStandaloneHistoryLine(slide?.title || `第 ${idx + 1} 页`, 120)}`);
        const points = Array.isArray(slide?.points) ? slide.points : [];
        points
            .map((item) => sanitizeStandaloneHistoryLine(item, 220))
            .filter(Boolean)
            .slice(0, 6)
            .forEach((point) => lines.push(`- ${point}`));
        const notes = sanitizeStandaloneHistoryLine(slide?.notes || '', 260);
        if (notes) {
            lines.push(`讲解备注：${notes}`);
        }
    });
    return lines.join('\n');
};

const pickOutlinePreviewTopic = (rawText = '', fallback = '业务汇报') => {
    const lines = String(rawText || '')
        .split(/\r?\n/)
        .map((line) => String(line || '').trim())
        .filter(Boolean);
    for (const rawLine of lines) {
        const line = rawLine
            .replace(/^(分析对象|主题|标题|题目|课题|研究主题|汇报主题|演示主题|文档名称|参考文档|文档补充说明)\s*[：:]\s*/i, '')
            .trim();
        if (!line) continue;
        const sentence = line.split(/[。！？!?；;]/)[0]?.trim() || '';
        if (sentence) return sentence.slice(0, 60);
    }
    return String(fallback || '业务汇报').trim() || '业务汇报';
};

const buildOutlinePreviewLinesFromResolved = (resolved) => {
    const slideCount = Math.max(3, Math.min(40, Number(resolved?.slideCount) || 8));
    const focusConfig = getStandalonePptContentFocusConfig(resolved?.contentFocus || STANDALONE_PPT_DEFAULT_CONTENT_FOCUS);
    const inputMode = String(resolved?.inputMode || 'topic').trim() || 'topic';
    const rawSource = [resolved?.documentName, resolved?.analysisInput, resolved?.typedInput].filter(Boolean).join('\n');
    const topic = pickOutlinePreviewTopic(rawSource, resolved?.documentName || resolved?.typedInput || '业务汇报');
    const subtitle = `${focusConfig.label} · 预计 ${slideCount} 页`;
    const sections = Array.isArray(focusConfig.previewSections) && focusConfig.previewSections.length
        ? focusConfig.previewSections
        : PPT_OUTLINE_PREVIEW_SECTIONS;
    const lines = [`标题：${topic}`, `副标题：${subtitle}`, `输入模式：${inputMode}`];
    for (let idx = 0; idx < slideCount; idx += 1) {
        const sectionTitle = sections[idx] || `补充页 ${idx + 1}`;
        lines.push(`${idx + 1}. ${sectionTitle}`);
        if (idx > 0) {
            lines.push(`   - 围绕“${topic}”补全本页核心观点`);
            lines.push("   - 补充关键事实、分析逻辑或数据依据");
        }
    }
    return lines;
};

const buildOutlinePreviewLinesFromOutline = (outlinePayload) => {
    const title = String(outlinePayload?.title || '业务汇报').trim() || '业务汇报';
    const focusConfig = getStandalonePptContentFocusConfig(
        outlinePayload?.contentFocus || STANDALONE_PPT_DEFAULT_CONTENT_FOCUS,
    );
    const subtitle = sanitizeStandaloneOutlineSubtitle(
        outlinePayload?.subtitle || '',
        focusConfig?.label || '',
    );
    const slides = Array.isArray(outlinePayload?.slides) ? outlinePayload.slides : [];
    const lines = [`标题：${title}`];
    if (subtitle) lines.push(`副标题：${subtitle}`);
    slides.forEach((slide, idx) => {
        const slideTitle = String(slide?.title || `第 ${idx + 1} 页`).trim();
        lines.push(`${idx + 1}. ${slideTitle}`);
        const points = Array.isArray(slide?.points)
            ? slide.points.map((item) => String(item || '').trim()).filter(Boolean).slice(0, 3)
            : [];
        points.forEach((point) => lines.push(`   - ${point}`));
    });
    return lines.slice(0, 42);
};

const compactStandaloneSourceContext = (rawText = '', maxItems = 6) =>
    Array.from(new Set(
        String(rawText || '')
            .split(/\r?\n/)
            .map((line) => String(line || '').trim())
            .filter(Boolean)
            .flatMap((line) => line.split(/[；;。！？!?]/))
            .map((item) => item.replace(/\s+/g, ' ').trim())
            .filter(Boolean),
    )).slice(0, maxItems);

const normalizeStandaloneOutlineTextLine = (value = '') =>
    String(value || '')
        .replace(/^#{1,6}\s*/, '')
        .replace(/^\s*[-*•]\s*/, '')
        .replace(/^\s*\d+\s*[.、)）]\s*/, '')
        .replace(/^\s*[一二三四五六七八九十]+\s*[、.)）]\s*/, '')
        .trim();

const splitStandaloneOutlinePointCandidates = (value = '') =>
    Array.from(new Set(
        String(value || '')
            .split(/\r?\n/)
            .flatMap((line) => {
                const normalizedLine = normalizeStandaloneOutlineTextLine(line);
                if (!normalizedLine) return [];
                return normalizedLine
                    .split(/[；;。！？!?]/)
                    .map((item) => item.replace(/\s+/g, ' ').trim())
                    .filter(Boolean);
            }),
    )).slice(0, 36);

const parseStandalonePptHistoryState = (messages = []) => {
    const contexts = (Array.isArray(messages) ? messages : [])
        .filter((msg) => msg?.role === "context" && String(msg?.func_type || "").toLowerCase().startsWith("ppt_"));
    if (!contexts.length) {
        return null;
    }

    const findLatestByType = (type) => {
        for (let i = contexts.length - 1; i >= 0; i -= 1) {
            if (String(contexts[i]?.func_type || "").toLowerCase() === type) {
                return contexts[i];
            }
        }
        return null;
    };

    const latest = contexts[contexts.length - 1] || null;
    const latestOutline = findLatestByType("ppt_outline");
    const latestTask = findLatestByType("ppt_task");
    const latestResult = findLatestByType("ppt_result");

    const splitLines = (rawText) =>
        String(rawText || "")
            .split(/\r?\n/)
            .map((line) => String(line || "").trim())
            .filter(Boolean);

    const parseHeader = (line) => {
        const text = String(line || "").trim();
        const matched = text.match(/\]\s*(.+?)(?:[（(]\s*(\d+)\s*页\s*[）)])?$/);
        const title = String(matched?.[1] || "业务汇报").trim();
        const count = Math.max(0, Math.min(40, Number(matched?.[2]) || 0));
        return { title, count };
    };

    const extractLineValue = (lines, prefix) => {
        const cleanPrefix = String(prefix || "").trim();
        if (!cleanPrefix) return "";
        const line = lines.find((item) => item.startsWith(cleanPrefix));
        return line ? String(line.slice(cleanPrefix.length)).trim() : "";
    };

    const parsedStructuredOutline = parseStructuredStandaloneOutlineHistory(latestOutline?.content || "");
    const outlineLines = splitLines(latestOutline?.content || "");
    const outlineHeader = parseHeader(outlineLines[0] || "");
    const outlineContentFocusLabel = parsedStructuredOutline?.contentFocus || extractLineValue(outlineLines, "内容导向：");
    const outlineSubtitle = sanitizeStandaloneOutlineSubtitle(
        parsedStructuredOutline?.subtitle || extractLineValue(outlineLines, "副标题："),
        outlineContentFocusLabel,
    );
    const outlineSlideTitles = outlineLines
        .filter((line) => /^\d+\.\s*/.test(line))
        .map((line) => line.replace(/^\d+\.\s*/, "").trim())
        .filter(Boolean);
    const outlineSlides = Array.isArray(parsedStructuredOutline?.slides) && parsedStructuredOutline.slides.length
        ? parsedStructuredOutline.slides
        : outlineSlideTitles.length
            ? outlineSlideTitles.map((title, idx) => ({
                  index: idx + 1,
                  title,
                  points: ["补充本页核心观点", "补充本页关键支撑信息"],
                  notes: "",
              }))
            : buildFallbackOutlineSlides(outlineHeader.count || 8);

    const resultLines = splitLines(latestResult?.content || "");
    const taskLines = splitLines(latestTask?.content || "");
    const latestLines = splitLines(latest?.content || "");
    const resultHeader = parseHeader(resultLines[0] || latestLines[0] || "");

    const restoredTemplate =
        extractLineValue(resultLines, "模板：") ||
        extractLineValue(taskLines, "模板：") ||
        "general";

    const downloadUrl = extractLineValue(resultLines, "下载链接：");
    const editUrl = extractLineValue(resultLines, "在线编辑：");
    const errorText = extractLineValue(resultLines, "错误：");
    const taskId = extractLineValue(taskLines, "任务ID：");
    const latestHeader = String(latestLines[0] || "").trim();
    const latestType = String(latest?.func_type || "").toLowerCase();

    let progress = createIdlePresentonProgress();
    if (latestType === "ppt_result") {
        const isFailed = latestHeader.includes("失败") || !!errorText;
        progress = {
            taskId,
            status: isFailed ? "failed" : "completed",
            progress: isFailed ? 0 : 100,
            message: isFailed ? (errorText || latestHeader || "PPT 生成失败") : (latestHeader || "PPT 生成完成"),
            previewLines: [],
            previewCursor: 0,
        };
    } else if (latestType === "ppt_task") {
        progress = {
            taskId,
            status: "pending",
            progress: 35,
            message: latestHeader || "任务已提交，正在生成...",
            previewLines: [],
            previewCursor: 0,
        };
    } else if (latestType === "ppt_outline") {
        progress = {
            taskId: "",
            status: "outline_ready",
            progress: 100,
            message: latestHeader || "内容结构已就绪",
            previewLines: [],
            previewCursor: 0,
        };
    }

    const resultPayload = latestResult
        ? {
              provider: "presenton",
              slideCount: outlineSlides.length || resultHeader.count || 8,
              contentFocus: STANDALONE_PPT_DEFAULT_CONTENT_FOCUS,
              downloadUrl: downloadUrl || "",
              editUrl: normalizePresentonEditUrl(editUrl || ""),
              finishedAt: latestResult?.created_at || new Date().toISOString(),
              ...(errorText ? { error: errorText } : {}),
          }
        : null;

    return {
        outline: {
            title: parsedStructuredOutline?.title || outlineHeader.title || resultHeader.title || "业务汇报",
            subtitle: outlineSubtitle,
            slides: outlineSlides,
            contentFocus: getStandalonePptContentFocusConfig(outlineContentFocusLabel || STANDALONE_PPT_DEFAULT_CONTENT_FOCUS).key,
        },
        template: restoredTemplate,
        result: resultPayload,
        progress,
    };
};

const splitUserMessageContent = (raw = '') => {
    const lines = raw.split('\n');
    const firstLine = lines[0] || '';
    const attachmentMatches = [...firstLine.matchAll(/\[📎 ([^\]]+)\]/g)];
    const attachments = attachmentMatches.map((m) => m[1]).filter(Boolean);
    const remainingText = attachmentMatches.length > 0 ? lines.slice(1).join('\n') : raw;
    return { attachments, remainingText };
};

const buildUserMessageContent = (attachments, text) => {
    if (!attachments.length) return text;
    const prefix = attachments.map((name) => `[📎 ${name}]`).join(' ');
    return text ? `${prefix}\n${text}` : prefix;
};

// --------------------------------------------------------------------------
// 🧜‍♂️ Mermaid 图表组件
// --------------------------------------------------------------------------
const PlainTextRenderer = ({ content, className = 'text-gray-800 dark:text-gray-200' }) => (
    <div className={`whitespace-pre-wrap text-[16px] leading-relaxed ${className}`}>
        {content || ''}
    </div>
);

const StructuredContent = ({ content, role, enableMarkdown = true, streaming = false }) => {
    // 对 user 侧保留性能优化；assistant 即使被“降级”也允许通过特征检测启用 Markdown。
    if (!enableMarkdown && role !== 'assistant') {
        return <PlainTextRenderer content={content} />;
    }

    const renderMarkdown = (text, { streaming: isStreaming = false, fallbackClassName } = {}) => (
        <Suspense fallback={<PlainTextRenderer content={text} className={fallbackClassName} />}>
            <MarkdownRenderer content={text} streaming={isStreaming} />
        </Suspense>
    );
    // 用户消息默认走纯文本，只有疑似 Markdown 时才启用渲染
    if (role !== 'assistant') {
        const raw = content || "";
        const lines = raw.split('\n');
        const firstLine = lines[0] || "";
        const attachmentMatches = [...firstLine.matchAll(/\[📎 ([^\]]+)\]/g)];
        const attachments = attachmentMatches.map((m) => m[1]).filter(Boolean);
        const remainingText = attachmentMatches.length > 0 ? lines.slice(1).join('\n') : raw;

        const shouldUseMarkdown = enableMarkdown && isLikelyMarkdown(remainingText);

        return (
            <div className="w-full min-w-0">
                {attachments.length > 0 && (
                    <div className="mb-2 flex flex-wrap gap-2">
                        {attachments.map((name, idx) => (
                            <div key={`${name}-${idx}`} className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-xs font-medium text-gray-700 dark:text-gray-200 shadow-sm">
                                <FileText size={14} className="text-gray-500" />
                                <span className="truncate max-w-[200px]">{name}</span>
                            </div>
                        ))}
                    </div>
                )}
                {remainingText ? (
                    shouldUseMarkdown
                        ? renderMarkdown(remainingText, { fallbackClassName: 'text-gray-900 dark:text-white' })
                        : <PlainTextRenderer content={remainingText} className="text-gray-900 dark:text-white" />
                ) : null}
            </div>
        );
    }

    // 🔴 修复：只有在流式输出中且内容为空时，才显示加载动画。
    // 如果已经结束（!streaming），即使 content 为空（极少见），也不应该显示加载动画，避免闪烁。
    if (!content && streaming) {
        return (
            <div className="flex items-center gap-1 h-5 pt-1">
                <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:-0.3s]"></div>
                <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce [animation-delay:-0.15s]"></div>
                <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce"></div>
            </div>
        );
    }

    // 如果不是流式，且内容为空，显示空占位符或什么都不显示
    if (!content) return null;

    // 4. 渲染结构化 UI (Report / Email / PPT) - 检测 JSON
    const jsonMatch = content.match(/```json\n([\s\S]*?)\n```/);
    let jsonData = null;
    let preText = content;

    if (jsonMatch) {
        try {
            jsonData = JSON.parse(jsonMatch[1]);
            // 提取 JSON 前的文本（如果有）
            preText = content.split('```json')[0].trim();
        } catch {
            // Streaming responses may briefly contain incomplete JSON blocks.
        }
    }

    // 如果没有 JSON 或者在流式输出中（可能 JSON 还没闭合），直接渲染 Markdown
    if (!jsonData) {
        const shouldUseMarkdown = enableMarkdown || isLikelyMarkdown(content);
        return (
            <div className="w-full min-w-0">
               {shouldUseMarkdown
                   ? renderMarkdown(content, { streaming })
                   : <PlainTextRenderer content={content} className="text-gray-900 dark:text-white" />}
               {content.includes('```json') && !content.includes('\n```') && (
                   <div className="mt-2 text-xs text-gray-400 animate-pulse flex items-center gap-1">
                       <Loader2 size={12} className="animate-spin"/> 正在生成结构化内容...
                   </div>
               )}
            </div>
        );
    }

    // 4. 渲染结构化 UI (Report / Email / PPT)
    return (
        <div className="flex flex-col gap-3 w-full">
            {preText && (isLikelyMarkdown(preText)
                ? renderMarkdown(preText)
                : <PlainTextRenderer content={preText} className="text-gray-900 dark:text-white" />)}
            {jsonData.type === 'report' && (
                <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden shadow-sm w-full">
                    <div className="bg-blue-50/50 dark:bg-blue-900/20 p-4 border-b border-blue-100 dark:border-blue-800">
                        <div className="flex items-center gap-2 mb-1">
                            <FileText size={16} className="text-blue-600 dark:text-blue-400"/>
                            <span className="text-xs font-bold text-blue-600 dark:text-blue-400 uppercase tracking-wider">Report Outline</span>
                        </div>
                        <h3 className="text-lg font-bold text-gray-900 dark:text-white">{jsonData.title}</h3>
                        {jsonData.subtitle && <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{jsonData.subtitle}</p>}
                    </div>
                    <div className="p-4 space-y-4">
                        {jsonData.sections?.map((sec, idx) => (
                            <div key={idx} className="group">
                                <h4 className="flex items-center gap-2 text-sm font-bold text-gray-800 dark:text-gray-200 mb-1.5">
                                    {sec.icon === 'alert-triangle' ? <AlertTriangle size={14} className="text-amber-500"/> :
                                     sec.icon === 'trending-up' ? <TrendingUp size={14} className="text-green-500"/> :
                                     <div className="w-1.5 h-1.5 rounded-full bg-blue-500"></div>}
                                    {sec.heading}
                                </h4>
                                <div className="pl-3.5 border-l-2 border-gray-100 dark:border-gray-800 ml-0.5 text-sm text-gray-600 dark:text-gray-400 whitespace-pre-wrap leading-relaxed">
                                    {renderMarkdown(sec.content)}
                                </div>
                            </div>
                        ))}
                    </div>
                    <div className="px-4 py-3 bg-gray-50 dark:bg-gray-800/50 border-t border-gray-100 dark:border-gray-800 flex justify-end gap-2">
                        <button className="text-xs font-medium text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1">
                            <Download size={12}/> 导出 PDF
                        </button>
                    </div>
                </div>
            )}
            {jsonData.type === 'email' && (
                <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden shadow-sm w-full relative group">
                    <div className="bg-gray-50 dark:bg-gray-800 p-3 border-b border-gray-200 dark:border-gray-700 flex justify-between items-start">
                         <div className="space-y-1 w-full">
                            <div className="flex gap-2 text-sm">
                                <span className="text-gray-500 w-10">To:</span>
                                <span className="font-medium text-gray-800 dark:text-gray-200">{jsonData.recipient}</span>
                            </div>
                            <div className="flex gap-2 text-sm">
                                <span className="text-gray-500 w-10">Sub:</span>
                                <span className="font-bold text-gray-900 dark:text-white">{jsonData.subject}</span>
                            </div>
                        </div>
                        <button className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors" title="复制全文" onClick={() => {navigator.clipboard.writeText(`Subject: ${jsonData.subject}\n\n${jsonData.body}`)}}>
                            <Copy size={16}/>
                        </button>
                    </div>
                    <div className="p-5 text-sm text-gray-700 dark:text-gray-300 leading-relaxed font-serif">
                        {renderMarkdown(jsonData.body)}
                    </div>
                </div>
            )}
            {jsonData.type === 'ppt' && (
                <div className="w-full">
                    <div className="flex items-center justify-between mb-3">
                        <h3 className="text-sm font-bold text-gray-700 dark:text-gray-300 flex items-center gap-2">
                             <Presentation size={16} className="text-purple-500"/>
                             {jsonData.title} <span className="text-xs font-normal text-gray-400">({jsonData.total_pages} 页)</span>
                        </h3>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        {jsonData.slides?.map((slide, idx) => (
                            <div key={idx} className="bg-white dark:bg-gray-900 p-4 rounded-lg border border-gray-200 dark:border-gray-700 hover:shadow-md transition-shadow relative overflow-hidden">
                                <div className="absolute top-0 left-0 w-1 h-full bg-purple-500"></div>
                                <div className="flex justify-between items-start mb-2 pl-2">
                                    <h4 className="font-bold text-gray-800 dark:text-gray-100 text-sm">{slide.title}</h4>
                                    <span className="text-[10px] font-mono text-gray-400 bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded">P{slide.page}</span>
                                </div>
                                <ul className="space-y-1 pl-2">
                                    {slide.points?.map((p, pi) => (
                                        <li key={pi} className="text-xs text-gray-600 dark:text-gray-400 flex items-start gap-1.5">
                                            <span className="mt-1 w-1 h-1 rounded-full bg-gray-400 flex-shrink-0"></span>
                                            {p}
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
};


const DashboardPage = ({ onLogout, currentMode, onModeChange }) => {
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [selectedModel, setSelectedModel] = useState(0);
  const [inputValue, setInputValue] = useState('');
  const [chatHistory, setChatHistory] = useState([]);
  const [visibleMessageCount, setVisibleMessageCount] = useState(INITIAL_MESSAGE_COUNT);
  const [expandedSources, setExpandedSources] = useState({});

  const [historyRenderTarget, setHistoryRenderTarget] = useState(INITIAL_MESSAGE_COUNT);

  // ✨ [新增] 模型后端状态 (local | cloud)
  const [llmBackend, setLlmBackend] = useState('local');
  const [isBackendDropdownOpen, setIsBackendDropdownOpen] = useState(false); // ✨ 后端选择下拉状态


  // ✨ 暂存待发送的文件 (Gemini-style)
  const [pendingFiles, setPendingFiles] = useState([]);

  // 通用内容面板状态
  const [panelContent, setPanelContent] = useState('');
  const [auditDocType, setAuditDocType] = useState('contract');
  const [auditModelBackend, setAuditModelBackend] = useState('cloud');
  const [auditFile, setAuditFile] = useState(null);
  const [auditBatch, setAuditBatch] = useState({
    active: false,
    currentIndex: -1,
    docTypeOverride: null,
    items: []
  });
  const [auditNotice, setAuditNotice] = useState('');
  const [auditState, setAuditState] = useState({
    status: 'idle',
    jobId: null,
    caseId: null,
    caseDocuments: [],
    progress: 0,
    stage: null,
    workflow_state: null,
    result: null,
    error: null,
    error_message: null
  });
  const [isAuditErpActionLoading, setIsAuditErpActionLoading] = useState(false);
  // ✨ 新增：音频文件播放 URL 状态
  const [audioFileUrl, setAudioFileUrl] = useState(null);
  // ✨ 新增：保存当前音频在服务端的存储路径
  const [currentAudioPath, setCurrentAudioPath] = useState(null);

  const [reportStep, setReportStep] = useState('selection');
  const [reportType, setReportType] = useState(null);
  const [reportFormData, setReportFormData] = useState({});
  const [reportAudienceInput, setReportAudienceInput] = useState('');
  const [writingEntryMode, setWritingEntryMode] = useState('root');
  const [standalonePptForm, setStandalonePptForm] = useState({
    inputMode: STANDALONE_PPT_INPUT_MODES[0].key,
    contentFocus: STANDALONE_PPT_DEFAULT_CONTENT_FOCUS,
    pptSlideCount: 8,
    analysisInput: "",
    documentName: "",
    requireMetrics: getStandalonePptContentFocusConfig(STANDALONE_PPT_DEFAULT_CONTENT_FOCUS).emphasizeMetrics,
    includeImages: true,
    template: 'general',
  });
  const [standalonePptOutline, setStandalonePptOutline] = useState(null);
  const [isOutlineGenerating, setIsOutlineGenerating] = useState(false);
  const [isOutlineEditorOpen, setIsOutlineEditorOpen] = useState(false);
  const [isPptWorkspaceOpen, setIsPptWorkspaceOpen] = useState(false);
  const [isTemplatePreviewOpen, setIsTemplatePreviewOpen] = useState(false);
  const [templatePreviewSelection, setTemplatePreviewSelection] = useState({ routeId: '', templateId: '' });
  const [standaloneTemplateCatalog, setStandaloneTemplateCatalog] = useState(STANDALONE_PPT_BUILTIN_TEMPLATES);
  const [isTemplateCatalogLoading, setIsTemplateCatalogLoading] = useState(false);
  const [standalonePptResult, setStandalonePptResult] = useState(null);
  const [isPresentonGenerating, setIsPresentonGenerating] = useState(false);
  const [presentonProgress, setPresentonProgress] = useState(() => createIdlePresentonProgress());
  const presentonPollingTaskRef = useRef('');

  const [isProcessing, setIsProcessing] = useState(false);
  const [isUploadingFile, setIsUploadingFile] = useState(false);
  const isOcrSaving = false;
  const [isProfileLoading, setIsProfileLoading] = useState(true);
  const [isSessionsLoading, setIsSessionsLoading] = useState(true);
  const [isSavingContext, setIsSavingContext] = useState(false);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [isTaskCenterOpen, setIsTaskCenterOpen] = useState(false);
  const [appSettings, setAppSettings] = useState(() => loadAppSettings());
  const [settingsModalState, setSettingsModalState] = useState({ isOpen: false, category: 'general' });

  const [userProfile, setUserProfile] = useState({ id: 'anonymous', name: 'User', avatar: '' });
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const currentSessionIdRef = useRef(null);
  const [sessionList, setSessionList] = useState([]);
  const [historyCursor, setHistoryCursor] = useState(null);
  const [historyHasMoreServer, setHistoryHasMoreServer] = useState(false);
  const [isHistoryPageLoading, setIsHistoryPageLoading] = useState(false);
  const sessionRefreshPromiseRef = useRef(null);
  const sessionRefreshQueuedUidRef = useRef('');
  const [isRecordingMode, setIsRecordingMode] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);
  const [isMobileModelDropdownOpen, setIsMobileModelDropdownOpen] = useState(false);
  const [shareModal, setShareModal] = useState({ isOpen: false, sessionId: null, title: "" });
  const [ocrIngestModal, setOcrIngestModal] = useState({ isOpen: false, content: "" });
  const [ocrEngine, setOcrEngine] = useState("pp-ocrv5");
  const [ocrFiles, setOcrFiles] = useState([]);
  const [activeOcrId, setActiveOcrId] = useState(null);
  const [ocrViewTab, setOcrViewTab] = useState("match");
  const [ocrPageIndex, setOcrPageIndex] = useState(0);
  const [isOcrEngineOpen, setIsOcrEngineOpen] = useState(false);
  const [isOcrDownloadOpen, setIsOcrDownloadOpen] = useState(false);
  const [selectedOcrLine, setSelectedOcrLine] = useState(null);
  const [editingOcrLine, setEditingOcrLine] = useState(null);
  const [editingOcrValue, setEditingOcrValue] = useState('');
  const [jsonEditError, setJsonEditError] = useState('');
  const [copyToast, setCopyToast] = useState('');
  const [ocrPreviewSize, setOcrPreviewSize] = useState({ width: 0, height: 0 });
  const [ocrImageMetrics, setOcrImageMetrics] = useState({ width: 0, height: 0, offsetX: 0, offsetY: 0 });
  const [ocrRenderSize, setOcrRenderSize] = useState({ width: 0, height: 0 });
  const ocrCanvasRef = useRef(null);
  const copyToastTimerRef = useRef(null);
  const [isOcrSummaryOpen, setIsOcrSummaryOpen] = useState(false);
  const [ocrSummaryMessages, setOcrSummaryMessages] = useState([]);
  const [ocrSummaryInput, setOcrSummaryInput] = useState('');
  const [isOcrSummaryLoading, setIsOcrSummaryLoading] = useState(false);
  const [ocrSummaryFileId, setOcrSummaryFileId] = useState(null);
  const [ocrSummaryBackend, setOcrSummaryBackend] = useState('local');
  const [ocrSummaryFirstDone, setOcrSummaryFirstDone] = useState(false);
  const ocrSummaryAbortRef = useRef(null);
  const ocrSummaryContextRef = useRef('');
  const ocrSummaryBufferRef = useRef([]);
  const ocrSummaryDisplayRef = useRef('');
  const ocrSummaryRafRef = useRef(null);
  const ocrSummaryScrollRef = useRef(null);
  const ocrSummaryLastChunkRef = useRef(0);
  const ocrSummaryIdleTimerRef = useRef(null);
  const ocrSummaryTimeoutRef = useRef(null);
  const ocrSummaryLastFlushRef = useRef(0);
  const ocrSummaryRequestLockRef = useRef(false);
  const ocrSummarySessionIdRef = useRef(null);

  // ✨ 交互状态
  const [copiedIdx, setCopiedIdx] = useState(null);
  const [speakingIdx, setSpeakingIdx] = useState(null);
  const [feedbackState, setFeedbackState] = useState({}); // { messageKey: 'up' | 'down' }
  const [editingMessageIndex, setEditingMessageIndex] = useState(null);
  const [editingMessageText, setEditingMessageText] = useState('');
  const [editingMessageAttachments, setEditingMessageAttachments] = useState([]);
  const [streamingAssistantText, setStreamingAssistantText] = useState('');

  // ✨ 新增 UI 状态
  const [isPlusMenuOpen, setIsPlusMenuOpen] = useState(false);
  const [isDragActive, setIsDragActive] = useState(false);
  const [, setIsInputFocused] = useState(false);
  const [keyboardOffset, setKeyboardOffset] = useState(0);
  const [isMobileViewport, setIsMobileViewport] = useState(false);
  const [mobileWorkspaceTab, setMobileWorkspaceTab] = useState('chat');
  const [ocrMobileTab, setOcrMobileTab] = useState('preview');
  const fileInputRef = useRef(null);
  const handleFileSelectRef = useRef(null);
  const dragDepthRef = useRef(0);
  const messageInputRef = useRef(null);
  const auditPollRef = useRef(null);
  const auditPollGenerationRef = useRef(0);
  const auditPollFailureCountRef = useRef(0);
  const auditHistorySavedRef = useRef(null);
  const auditBatchRef = useRef({
    active: false,
    currentIndex: -1,
    docTypeOverride: null,
    items: []
  });
  const auditBatchTransitionRef = useRef('');
  // constscrollRafRef = useRef(null); // REMOVED: 删除节流

  // ✨✨✨ 流畅的流媒体参考 ✨✨✨
  // streamBufferRef: 存储网络接收到但尚未显示的字符队列
  const streamBufferRef = useRef('');
  // streamDisplayRef: 存储当前屏幕上已显示的完整文本（用于闭包中获取最新状态）
  const streamDisplayRef = useRef("");
  // rafIdRef: 存储动画帧ID
  const rafIdRef = useRef(null);
  const streamLastFlushRef = useRef(0);
  const trackedBlobUrlsRef = useRef(new Set());
  const sessionClickHandlerRef = useRef(null);
  const newChatHandlerRef = useRef(null);
  const hasHandledInitialRouteRef = useRef(false);
  const isApplyingRouteSessionRef = useRef(false);
  const initialRouteSessionIdRef = useRef(
    typeof window !== 'undefined' ? extractConversationSessionId(window.location.pathname) : null
  );
  const [isInitialRouteLoading, setIsInitialRouteLoading] = useState(() => Boolean(initialRouteSessionIdRef.current));

  const dropdownRef = useRef(null);
  const mobileDropdownRef = useRef(null);
  const backendDropdownRef = useRef(null); // ✨ 后端下拉 Ref
  const ocrPreviewRef = useRef(null);
  const ocrImageRef = useRef(null);
  const ocrRenderRef = useRef(null);
  const chatEndRef = useRef(null);
  const chatScrollRef = useRef(null);
  const abortControllerRef = useRef(null); // ✨ 控制打断的 Ref
  const activeChatRequestRef = useRef(null);
  const keyboardLockPrevRef = useRef({ body: null, html: null });
  const virtualKeyboardEnabledRef = useRef(false);

  const historyExpandTaskRef = useRef(null);
  const autoProcessFilesRef = useRef(null);
  const autoProcessModeRef = useRef(null);

  const isMeetingMode = selectedModel === 1;
  const isOCRMode = selectedModel === 2;
  const isReportMode = selectedModel === 3;
  const isAuditMode = selectedModel === 4;
  const isRAGMode = currentMode === 'rag';
  const isKeyboardVisible = isMobileViewport && keyboardOffset > 80;
  const isSearchMode = currentMode === 'search'; // ✅ 搜索模式判断

  const isFileDragEvent = (event) => {
    const types = event?.dataTransfer?.types;
    if (!types) return false;
    return Array.from(types).includes('Files');
  };

  const getVirtualKeyboardHeight = () => {
    if (typeof navigator === 'undefined') return 0;
    const vk = navigator.virtualKeyboard;
    if (!vk || !vk.overlaysContent) return 0;
    const rect = vk.boundingRect;
    return Math.max(0, Math.round(rect?.height || 0));
  };

  const showContentPanel = isMeetingMode || isOCRMode || isAuditMode || (panelContent && panelContent.length > 0);
  const isAuditSinglePane = isAuditMode && showContentPanel;
  const showMobileWorkspaceTabs = isMobileViewport && showContentPanel && !isAuditSinglePane;
  const shouldRenderPanel = showContentPanel && (!showMobileWorkspaceTabs || mobileWorkspaceTab === 'panel');
  const shouldRenderChat = !isAuditSinglePane && (!showMobileWorkspaceTabs || mobileWorkspaceTab === 'chat');
  const mobilePanelTabLabel = isMeetingMode ? '工作台' : (isOCRMode ? '识别面板' : '上下文');
  const activeOcrFile = useMemo(() => ocrFiles.find((item) => item.id === activeOcrId) || null, [ocrFiles, activeOcrId]);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const syncSettings = (event) => {
      if (event?.detail) {
        setAppSettings(normalizeAppSettings(event.detail));
        return;
      }
      setAppSettings(loadAppSettings());
    };
    window.addEventListener(APP_SETTINGS_UPDATED_EVENT, syncSettings);
    return () => window.removeEventListener(APP_SETTINGS_UPDATED_EVENT, syncSettings);
  }, []);

  useEffect(() => {
      if (!ocrPreviewRef.current) return;
      const element = ocrPreviewRef.current;
      const updateSize = () => {
          const rect = element.getBoundingClientRect();
          setOcrPreviewSize({ width: rect.width, height: rect.height });
      };
      updateSize();
      if (typeof ResizeObserver !== 'undefined') {
          const observer = new ResizeObserver(updateSize);
          observer.observe(element);
          return () => observer.disconnect();
      }
  }, [activeOcrFile?.id]);

  useEffect(() => {
      if (!ocrRenderRef.current) return;
      const element = ocrRenderRef.current;
      const updateSize = () => {
          const rect = element.getBoundingClientRect();
          setOcrRenderSize({ width: rect.width, height: rect.height });
      };
      updateSize();
      if (typeof ResizeObserver !== 'undefined') {
          const observer = new ResizeObserver(updateSize);
          observer.observe(element);
          return () => observer.disconnect();
      }
  }, [activeOcrFile?.id, activeOcrFile?.status, ocrViewTab]);

  useEffect(() => {
      if (!ocrCanvasRef.current || !activeOcrFile || !Array.isArray(activeOcrFile.pages) || !activeOcrFile.pages[ocrPageIndex]) return;
      if (!ocrRenderSize.width) return;
      if (ocrViewTab !== 'match') return;

      const page = activeOcrFile.pages[ocrPageIndex];
      const scale = ocrRenderSize.width / page.width;
      const canvas = ocrCanvasRef.current;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      const dpr = window.devicePixelRatio || 1;
      const renderWidth = Math.max(1, Math.round(ocrRenderSize.width));
      const renderHeight = Math.max(1, Math.round(page.height * scale));

      canvas.width = Math.round(renderWidth * dpr);
      canvas.height = Math.round(renderHeight * dpr);
      canvas.style.width = `${renderWidth}px`;
      canvas.style.height = `${renderHeight}px`;

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, renderWidth, renderHeight);
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, renderWidth, renderHeight);
      ctx.textBaseline = 'top';
      ctx.fillStyle = '#111';

      const fontFamily = '"Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif';

      const drawTextFitted = (text, x, y, w, h) => {
          if (!text) return;
          const fontSize = Math.max(10, Math.min(30, h * 0.82));
          ctx.font = `${fontSize}px ${fontFamily}`;
          ctx.textAlign = 'left';
          const textWidth = ctx.measureText(text).width || 0;
          if (textWidth <= 0) return;
          if (textWidth > w) {
              const scaleX = w / textWidth;
              ctx.save();
              ctx.translate(x, y);
              ctx.scale(scaleX, 1);
              ctx.fillText(text, 0, 0);
              ctx.restore();
          } else {
              ctx.fillText(text, x, y);
          }
      };

      ctx.save();
      ctx.scale(scale, scale);
      const lines = resolveOcrLinesForFile(activeOcrFile);
      const pageLines = lines.filter((line) => {
          const linePage = line.page === undefined || line.page === null ? 0 : line.page;
          return linePage === ocrPageIndex;
      });
      const hasBoxes = pageLines.some((line) => Array.isArray(line.box) && line.box.length >= 4);
      if (hasBoxes) {
          pageLines.forEach((line) => {
              if (!line.box) return;
              const points = line.box;
              if (!Array.isArray(points) || points.length < 4) return;
              const xs = points.map((p) => p[0]);
              const ys = points.map((p) => p[1]);
              const left = Math.min(...xs);
              const top = Math.min(...ys);
              const width = Math.max(...xs) - Math.min(...xs);
              const height = Math.max(...ys) - Math.min(...ys);
              drawTextFitted(line.text, left, top, width, height);
          });
      } else {
          const textLines = (activeOcrFile.ocrText || '').split(/\r?\n/).filter(Boolean);
          let y = 16;
          textLines.forEach((line) => {
              drawTextFitted(line, 16, y, page.width - 32, 18);
              y += 22;
          });
      }
      ctx.restore();
  }, [
      activeOcrFile,
      ocrRenderSize.width,
      ocrRenderSize.height,
      ocrViewTab,
      ocrFiles.length,
      ocrPageIndex
  ]);

  useEffect(() => {
      setJsonEditError('');
      if (!activeOcrFile) return;
      if (!activeOcrFile.jsonText && activeOcrFile.ocrData) {
          setOcrFiles((prev) => prev.map((item) => (
              item.id === activeOcrFile.id
                  ? { ...item, jsonText: JSON.stringify(activeOcrFile.ocrData, null, 2) }
                  : item
          )));
      }
  }, [activeOcrFile, ocrViewTab]);

  useEffect(() => {
      if (!activeOcrFile) return;
      const total = Array.isArray(activeOcrFile.pages) ? activeOcrFile.pages.length : 1;
      if (ocrPageIndex >= total) {
          setOcrPageIndex(0);
      }
      setSelectedOcrLine(null);
  }, [activeOcrFile, ocrPageIndex]);

  useEffect(() => {
      return () => {
          if (copyToastTimerRef.current) {
              clearTimeout(copyToastTimerRef.current);
              copyToastTimerRef.current = null;
          }
      };
  }, []);

  const showCopyToast = (message = '复制成功') => {
      setCopyToast(message);
      if (copyToastTimerRef.current) clearTimeout(copyToastTimerRef.current);
      copyToastTimerRef.current = setTimeout(() => {
          setCopyToast('');
          copyToastTimerRef.current = null;
      }, 1600);
  };

  useEffect(() => {
      const updateMetrics = () => {
          if (!ocrPreviewRef.current || !ocrImageRef.current) return;
          const containerRect = ocrPreviewRef.current.getBoundingClientRect();
          const imageRect = ocrImageRef.current.getBoundingClientRect();
          setOcrImageMetrics({
              width: imageRect.width,
              height: imageRect.height,
              offsetX: imageRect.left - containerRect.left,
              offsetY: imageRect.top - containerRect.top
          });
      };
      updateMetrics();
      const handleResize = () => updateMetrics();
      window.addEventListener('resize', handleResize);
      return () => window.removeEventListener('resize', handleResize);
  }, [activeOcrFile?.id, ocrPreviewSize.width, ocrPreviewSize.height]);
  // 保持桌面输入栏高度稳定：不要隐藏/显示焦点提示。
  const shouldHideInputHint = isMobileViewport;
  const shouldLockSuggestionsScroll =
    !isMobileViewport &&
    chatHistory.length === 0 &&
    !showContentPanel &&
    !panelContent &&
    !isUploadingFile &&
    pendingFiles.length === 0;
  const inputBarStyle = {
    paddingBottom: isMobileViewport
      ? (isKeyboardVisible ? '0px' : 'env(safe-area-inset-bottom)')
      : 'calc(env(safe-area-inset-bottom) + 16px)',
    bottom: (isMobileViewport && isKeyboardVisible) ? `${keyboardOffset}px` : '0px',
  };
  const chatContentStyle = {
    paddingTop: isMobileViewport ? '12px' : '16px',
    paddingBottom: isMobileViewport
      ? (isKeyboardVisible ? '112px' : '152px')
      : '40px',
  };
  const normalizedVisibleCount = Math.min(visibleMessageCount, chatHistory.length);
  const visibleMessages = useMemo(() => {
    if (normalizedVisibleCount === 0) return [];
    return chatHistory.slice(-normalizedVisibleCount);
  }, [chatHistory, normalizedVisibleCount]);
  const shouldPreloadMarkdown = useMemo(() => {
    if (!chatHistory.length) return false;
    return chatHistory
      .slice(-MARKDOWN_MESSAGE_COUNT)
      .some((msg) => msg?.role === 'assistant' && isLikelyMarkdown(msg?.content || ''));
  }, [chatHistory]);
  const { loadOlderSessionMessages, resetHistoryPaginationState } = useSessionHistoryPagination({
    currentSessionIdRef,
    userId: userProfile.id,
    historyCursor,
    historyHasMoreServer,
    chatHistoryLength: chatHistory.length,
    setChatHistory,
    setVisibleMessageCount,
    setHistoryCursor,
    setHistoryHasMoreServer,
    setIsHistoryPageLoading,
    initialMessageCount: INITIAL_MESSAGE_COUNT,
  });
  const hasMoreMessages = chatHistory.length > normalizedVisibleCount || historyHasMoreServer;
  const showChatSkeleton = (isProfileLoading || isSessionsLoading) && chatHistory.length === 0;

  useEffect(() => {
    if (typeof URL === 'undefined' || typeof URL.revokeObjectURL !== 'function') return;
    const nextBlobUrls = new Set();

    pendingFiles.forEach((file) => {
      const preview = file?.previewUrl;
      if (typeof preview === 'string' && preview.startsWith('blob:')) {
        nextBlobUrls.add(preview);
      }
    });

    ocrFiles.forEach((file) => {
      const preview = file?.previewUrl;
      if (typeof preview === 'string' && preview.startsWith('blob:')) {
        nextBlobUrls.add(preview);
      }
    });

    if (typeof audioFileUrl === 'string' && audioFileUrl.startsWith('blob:')) {
      nextBlobUrls.add(audioFileUrl);
    }

    trackedBlobUrlsRef.current.forEach((blobUrl) => {
      if (!nextBlobUrls.has(blobUrl)) {
        URL.revokeObjectURL(blobUrl);
      }
    });

    trackedBlobUrlsRef.current = nextBlobUrls;
  }, [pendingFiles, ocrFiles, audioFileUrl]);

  useEffect(() => {
    return () => {
      if (typeof URL === 'undefined' || typeof URL.revokeObjectURL !== 'function') return;
      trackedBlobUrlsRef.current.forEach((blobUrl) => URL.revokeObjectURL(blobUrl));
      trackedBlobUrlsRef.current.clear();
    };
  }, []);

  const resizeMessageInput = (element) => {
    if (!element) return;
    element.style.height = 'auto';
    const nextHeight = Math.min(Math.max(element.scrollHeight, 44), 200);
    element.style.height = `${nextHeight}px`;
  };

  const scrollToBottom = (behavior = "auto") => {
    const container = chatScrollRef.current;
    if (container && typeof container.scrollTo === "function") {
      const top = container.scrollHeight;
      container.scrollTo({ top, behavior });
      return;
    }
    if (!chatEndRef.current) return;
    chatEndRef.current.scrollIntoView({ behavior, block: "end" });
  };

  const queueScrollToBottom = (behavior = "auto") => {
      scrollToBottom(behavior);
  };

  const flushStreamingUi = (force = false) => {
      const now = performance.now ? performance.now() : Date.now();
      if (!force && now - streamLastFlushRef.current < STREAM_UI_FLUSH_MS) return;
      streamLastFlushRef.current = now;
      setStreamingAssistantText(streamDisplayRef.current);
      scrollToBottom("auto");
  };

  // ✨✨✨ 流畅的动画循环 ✨✨✨
  // 启动平滑动画循环
  const startSmoothStream = () => {
    if (rafIdRef.current) cancelAnimationFrame(rafIdRef.current);
    streamLastFlushRef.current = 0;

    const animate = () => {
        if (streamBufferRef.current.length > 0) {
            const queueLength = streamBufferRef.current.length;
            const charsToTake = queueLength > 1800 ? 64
              : queueLength > 1000 ? 48
              : queueLength > 500 ? 32
              : queueLength > 220 ? 20
              : queueLength > 90 ? 12
              : queueLength > 24 ? 6
              : 3;

            const chunk = streamBufferRef.current.slice(0, charsToTake);
            streamBufferRef.current = streamBufferRef.current.slice(charsToTake);
            streamDisplayRef.current += chunk;

            flushStreamingUi(streamBufferRef.current.length === 0);
        }

        rafIdRef.current = requestAnimationFrame(animate);
    };

    rafIdRef.current = requestAnimationFrame(animate);
  };

  // 停止平滑动画，并强制刷新剩余内容
  const stopSmoothStream = () => {
      if (rafIdRef.current) {
          cancelAnimationFrame(rafIdRef.current);
          rafIdRef.current = null;
      }
      // 将缓冲区剩余所有内容一次性倒出
      if (streamBufferRef.current.length > 0) {
          const remaining = streamBufferRef.current;
          streamBufferRef.current = '';
          streamDisplayRef.current += remaining;
      }
      flushStreamingUi(true);
  };

  const clearHistoryExpandTask = () => {
    const task = historyExpandTaskRef.current;
    if (!task) return;
    if (task.type === 'idle' && typeof window !== 'undefined' && typeof window.cancelIdleCallback === 'function') {
      window.cancelIdleCallback(task.id);
    } else if (task.type === 'timeout') {
      clearTimeout(task.id);
    }
    historyExpandTaskRef.current = null;
  };

  const scheduleHistoryExpand = () => {
    clearHistoryExpandTask();
    if (typeof window !== 'undefined' && typeof window.requestIdleCallback === 'function') {
      const id = window.requestIdleCallback(() => {
        setHistoryRenderTarget(INITIAL_MESSAGE_COUNT);
        historyExpandTaskRef.current = null;
      }, { timeout: 1200 });
      historyExpandTaskRef.current = { type: 'idle', id };
      return;
    }
    const id = setTimeout(() => {
      setHistoryRenderTarget(INITIAL_MESSAGE_COUNT);
      historyExpandTaskRef.current = null;
    }, 200);
    historyExpandTaskRef.current = { type: 'timeout', id };
  };

  useEffect(() => {
    resizeMessageInput(messageInputRef.current);
  }, [inputValue]);

  useEffect(() => {
    return () => {
      clearHistoryExpandTask();
      if (rafIdRef.current) cancelAnimationFrame(rafIdRef.current); // Cleanup RAF
      if (ocrSummaryRafRef.current) cancelAnimationFrame(ocrSummaryRafRef.current);
    };
  }, []);

  useEffect(() => {
    if (!shouldPreloadMarkdown) return;
    let cancelled = false;
    const preload = () => {
      if (!cancelled) {
        import('./MarkdownRenderer');
      }
    };
    if (typeof window !== 'undefined' && typeof window.requestIdleCallback === 'function') {
      const id = window.requestIdleCallback(preload, { timeout: 1200 });
      return () => {
        cancelled = true;
        window.cancelIdleCallback(id);
      };
    }
    const id = setTimeout(preload, 200);
    return () => {
      cancelled = true;
      clearTimeout(id);
    };
  }, [shouldPreloadMarkdown]);

  const refreshSessionList = useCallback(async (uid, { silent = true } = {}) => {
    const safeUid = String(uid || userProfile.id || 'anonymous').trim();
    if (!safeUid || safeUid === 'undefined') return [];

    if (sessionRefreshPromiseRef.current) {
      sessionRefreshQueuedUidRef.current = safeUid;
      return sessionRefreshPromiseRef.current;
    }

    if (!silent) {
      setIsSessionsLoading(true);
    }

    const request = (async () => {
      try {
        const sessions = await historyApi.getSessions(safeUid);
        setSessionList(sessions || []);
        return sessions || [];
      } catch (e) {
        console.error('Failed to load sessions', e);
        return [];
      } finally {
        sessionRefreshPromiseRef.current = null;
        if (!silent) {
          setIsSessionsLoading(false);
        }

        const queuedUid = sessionRefreshQueuedUidRef.current;
        if (queuedUid) {
          sessionRefreshQueuedUidRef.current = '';
          void refreshSessionList(queuedUid, { silent: true });
        }
      }
    })();

    sessionRefreshPromiseRef.current = request;
    return request;
  }, [userProfile.id]);

  useEffect(() => {
    let isActive = true;
    const schedule = (fn, delay = 500) => {
      if (typeof window.requestIdleCallback === 'function') {
        const id = window.requestIdleCallback(() => fn(), { timeout: delay + 1500 });
        return () => window.cancelIdleCallback(id);
      }
      const id = setTimeout(fn, delay);
      return () => clearTimeout(id);
    };

    const loadProfile = async () => {
      if (!isActive) return;
      setIsProfileLoading(true);
      let profile = { id: 'anonymous', name: 'User', avatar: '' };
      const tokenBeforeLoad = localStorage.getItem(AUTH_TOKEN_KEY);
      try {
        profile = await userApi.getProfile();
        const localToken = localStorage.getItem(AUTH_TOKEN_KEY);
        if (localToken && (!profile || !profile.id || profile.id === 'anonymous')) {
          onLogout();
          return;
        }
        if (isActive) setUserProfile(profile);
      } catch (e) {
        console.error("Profile load error", e);
        const message = String(e?.message || '');
        const isAuthError = /401|not logged in|invalid session|missing token|jwt/i.test(message);
        if (tokenBeforeLoad && isAuthError) {
          onLogout();
          return;
        }
      } finally {
        if (isActive) setIsProfileLoading(false);
      }

      if (!isActive) return;
      const uid = profile.id || 'anonymous';
      if (uid && uid !== 'undefined') {
        schedule(() => {
          void refreshSessionList(uid, { silent: false });
        }, 600);
      } else {
        if (isActive) setIsSessionsLoading(false);
      }
    };

    const cancelProfile = schedule(loadProfile, 300);
    return () => {
      isActive = false;
      cancelProfile();
    };
  }, [onLogout, refreshSessionList]);

  useEffect(() => {
    if (isProfileLoading || isSessionsLoading) return;
    const uid = userProfile?.id;
    if (!uid || uid === 'anonymous') return;
    const storageKey = `${ONBOARDING_STORAGE_PREFIX}${uid}`;
    try {
      if (localStorage.getItem(storageKey)) {
        setShowOnboarding(false);
        return;
      }
    } catch {
      return;
    }
    if (sessionList.length > 0) return;
    setShowOnboarding(true);
  }, [isProfileLoading, isSessionsLoading, userProfile?.id, sessionList.length]);

  useEffect(() => {
    if (isProfileLoading || isSessionsLoading) return;
    const uid = userProfile?.id;
    if (!uid || uid === 'anonymous') return;
    const storageKey = `${ONBOARDING_STORAGE_PREFIX}${uid}`;
    try {
      if (localStorage.getItem(storageKey)) {
        setShowOnboarding(false);
        return;
      }
    } catch {
      return;
    }
    if (sessionList.length > 0) return;
    setShowOnboarding(true);
  }, [isProfileLoading, isSessionsLoading, userProfile?.id, sessionList.length]);

  useLayoutEffect(() => {
    if (chatHistory.length === 0) return;
    scrollToBottom('auto');
  }, [chatHistory, visibleMessageCount]);

  useEffect(() => {
    if (chatHistory.length === 0) {
      setVisibleMessageCount(0);
      return;
    }
    setVisibleMessageCount((prev) => {
      const minCount = Math.min(historyRenderTarget, chatHistory.length);
      return Math.max(prev, minCount);
    });
  }, [chatHistory.length, historyRenderTarget]);

  useEffect(() => {
    const jobId = auditState.jobId;
    const status = auditState.status;

    if (!jobId || !['pending', 'running'].includes(status)) {
      if (auditPollRef.current) {
        clearTimeout(auditPollRef.current);
        auditPollRef.current = null;
      }
      return;
    }

    const generation = auditPollGenerationRef.current + 1;
    auditPollGenerationRef.current = generation;
    auditPollFailureCountRef.current = 0;
    let cancelled = false;
    const poll = async () => {
      if (cancelled) return;
      try {
        const token = localStorage.getItem(AUTH_TOKEN_KEY);
        const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
        const res = await fetch(`${API_BASE_URL}/api/audit/${jobId}`, { headers });
        if (cancelled || auditPollGenerationRef.current !== generation) return;
        const data = await res.json();
        if (cancelled || auditPollGenerationRef.current !== generation) return;

        if (!res.ok) {
          throw new Error(data.detail || data.error || '获取审单状态失败');
        }

        const returnedStatus = String(data.status || status || '').toLowerCase();
        const hasFinalResult = !!(data.result && typeof data.result === 'object');
        const nextStatus = (['pending', 'running'].includes(returnedStatus) && hasFinalResult)
          ? 'done'
          : (returnedStatus || status);
        const progressValue = Number(data.progress);
        const resolvedProgress = Number.isFinite(progressValue)
          ? progressValue
          : (nextStatus === 'done' ? 100 : undefined);
        auditPollFailureCountRef.current = 0;
        setAuditState((prev) => ({
          ...prev,
          status: nextStatus,
          progress: Number.isFinite(resolvedProgress) ? resolvedProgress : prev.progress,
          stage: data.stage || (nextStatus === 'done' ? 'done' : prev.stage),
          workflow_state: data.workflow_state || data.result?.workflow_state || prev.workflow_state,
          caseId: data.case_id || prev.caseId,
          caseDocuments: Array.isArray(data.case_documents) ? data.case_documents : prev.caseDocuments,
          result: data.result || prev.result,
          error_message: nextStatus === 'failed' ? (data.error_message || prev.error_message) : null,
          error: nextStatus === 'failed' ? (data.error_message || prev.error) : null
        }));

        if (['pending', 'running'].includes(nextStatus)) {
          auditPollRef.current = setTimeout(poll, AUDIT_POLL_INTERVAL);
        }
      } catch (error) {
        if (cancelled || auditPollGenerationRef.current !== generation) return;
        const message = error?.message || '获取审单状态失败';
        const failureCount = auditPollFailureCountRef.current + 1;
        auditPollFailureCountRef.current = failureCount;
        if (failureCount === 3) {
          showAuditNotice('审单状态同步暂时中断，系统正在自动重试。');
        }
        const retryDelay = Math.min(AUDIT_POLL_INTERVAL * Math.max(1, failureCount), 8000);
        setAuditState((prev) => ({
          ...prev,
          error: message,
          error_message: prev.status === 'failed' ? (prev.error_message || message) : null
        }));
        auditPollRef.current = setTimeout(poll, retryDelay);
      }
    };

    poll();

    return () => {
      cancelled = true;
      if (auditPollRef.current) {
        clearTimeout(auditPollRef.current);
        auditPollRef.current = null;
      }
    };
  }, [auditState.jobId, auditState.status]);

  useEffect(() => {
    auditBatchRef.current = auditBatch;
  }, [auditBatch]);

  useEffect(() => {
    const items = Array.isArray(auditBatch.items) ? auditBatch.items : [];
    if (!items.length) {
      setAuditFile(null);
      return;
    }
    const safeIndex = auditBatch.currentIndex >= 0
      ? Math.min(auditBatch.currentIndex, items.length - 1)
      : Math.max(0, items.findIndex((item) => ['uploading', 'pending', 'running'].includes(item.status)));
    const activeIndex = safeIndex >= 0 ? safeIndex : 0;
    const currentItem = items[activeIndex] || items[items.length - 1];
    const completedCount = items.filter((item) => item.status === 'done').length;
    const failedCount = items.filter((item) => item.status === 'failed').length;
    setAuditFile({
      name: currentItem?.name || '',
      size: currentItem?.size || 0,
      sizeLabel: currentItem?.sizeLabel || '',
      isBatch: items.length > 1,
      totalCount: items.length,
      currentIndex: activeIndex + 1,
      completedCount,
      failedCount,
      queue: items.map((item) => ({
        id: item.id,
        name: item.name,
        size: item.size,
        sizeLabel: item.sizeLabel,
        status: item.status
      }))
    });
  }, [auditBatch]);

  useEffect(() => {
    const batch = auditBatchRef.current;
    if (!batch?.items?.length || batch.currentIndex < 0) return;
    const currentIndex = Math.min(batch.currentIndex, batch.items.length - 1);
    const nextStatus = String(auditState.status || 'idle').toLowerCase();
    if (!['uploading', 'pending', 'running', 'done', 'failed'].includes(nextStatus)) return;
    setAuditBatch((prev) => {
      if (!prev.items[currentIndex] || prev.items[currentIndex].status === nextStatus) return prev;
      const nextItems = prev.items.map((item, index) => (
        index === currentIndex ? { ...item, status: nextStatus } : item
      ));
      return { ...prev, items: nextItems };
    });
  }, [auditState.status]);

  useEffect(() => {
    const batch = auditBatchRef.current;
    const terminalStatus = String(auditState.status || '').toLowerCase();
    if (!auditState.jobId || !['done', 'failed'].includes(terminalStatus)) return;
    if (!batch?.items?.length || batch.currentIndex < 0) return;

    const marker = `${auditState.jobId}:${terminalStatus}`;
    if (auditBatchTransitionRef.current === marker) return;
    auditBatchTransitionRef.current = marker;

    const currentIndex = Math.min(batch.currentIndex, batch.items.length - 1);
    const currentCaseDocumentCount = Array.isArray(auditState.caseDocuments) ? auditState.caseDocuments.length : 0;
    if (terminalStatus === 'failed') {
      setAuditBatch((prev) => ({ ...prev, active: false }));
      if (batch.items.length > 1) {
        showAuditNotice(`第 ${currentIndex + 1}/${batch.items.length} 份文件审单失败，批量流程已暂停。`);
      }
      return;
    }

    const nextIndex = batch.items.findIndex((item, index) => index > currentIndex && item.status === 'queued');
    if (nextIndex === -1) {
      const shouldRefreshCaseReport = Boolean(auditState.caseId) && currentCaseDocumentCount > 1;
      if (batch.active && batch.items.length > 1) {
        setAuditBatch((prev) => ({ ...prev, active: false }));
      }
      if (shouldRefreshCaseReport) {
        window.setTimeout(() => {
          void (async () => {
            const aggregatedResult = auditState.caseId ? await fetchAuditCaseReport(auditState.caseId) : null;
            if (batch.active && batch.items.length > 1) {
              showAuditNotice(
                aggregatedResult
                  ? `批量审单完成，共处理 ${batch.items.length} 份文件，已切换为整包汇总报告。`
                  : `批量审单完成，共处理 ${batch.items.length} 份文件。`
              );
              return;
            }
            if (aggregatedResult) {
              showAuditNotice(`已更新当前审单包汇总，共关联 ${currentCaseDocumentCount} 份文件。`);
            }
          })();
        }, 120);
      } else if (batch.active && batch.items.length > 1) {
        showAuditNotice(`批量审单完成，共处理 ${batch.items.length} 份文件。`);
      }
      return;
    }

    const nextItem = batch.items[nextIndex];
    if (!nextItem?.file) return;
    window.setTimeout(() => {
      startAuditJob(nextItem.file, {
        docTypeOverride: batch.docTypeOverride || 'auto',
        suppressBusyCheck: true,
        batchIndex: nextIndex
      });
    }, 120);
  }, [auditState.caseId, auditState.jobId, auditState.status]);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) setIsDropdownOpen(false);
      if (mobileDropdownRef.current && !mobileDropdownRef.current.contains(event.target)) setIsMobileModelDropdownOpen(false);
      // 如果在外部单击则关闭加号菜单
      if (isPlusMenuOpen && !event.target.closest('.plus-menu-container')) setIsPlusMenuOpen(false);
      // 关闭后端下拉菜单
      if (backendDropdownRef.current && !backendDropdownRef.current.contains(event.target)) setIsBackendDropdownOpen(false);
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isPlusMenuOpen, isBackendDropdownOpen]);

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 767px)');
    const handleChange = () => setIsMobileViewport(mq.matches);
    handleChange();
    if (mq.addEventListener) {
      mq.addEventListener('change', handleChange);
    } else {
      mq.addListener(handleChange);
    }
    return () => {
      if (mq.removeEventListener) {
        mq.removeEventListener('change', handleChange);
      } else {
        mq.removeListener(handleChange);
      }
    };
  }, []);

  useEffect(() => {
    if (!isMobileViewport || typeof navigator === 'undefined') return;
    const vk = navigator.virtualKeyboard;
    if (!vk) {
      virtualKeyboardEnabledRef.current = false;
      return;
    }

    const syncFromVirtualKeyboard = () => {
      const height = getVirtualKeyboardHeight();
      if (height >= 0) setKeyboardOffset(height);
    };

    try {
      vk.overlaysContent = true;
      virtualKeyboardEnabledRef.current = !!vk.overlaysContent;
    } catch {
      virtualKeyboardEnabledRef.current = false;
    }

    syncFromVirtualKeyboard();
    vk.addEventListener?.('geometrychange', syncFromVirtualKeyboard);
    return () => {
      vk.removeEventListener?.('geometrychange', syncFromVirtualKeyboard);
    };
  }, [isMobileViewport]);

  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) return;
    const handleViewportChange = () => {
      const virtualHeight = getVirtualKeyboardHeight();
      if (virtualKeyboardEnabledRef.current && virtualHeight > 0) {
        setKeyboardOffset(virtualHeight);
        return;
      }
      const offset = Math.max(0, Math.round(window.innerHeight - viewport.height - viewport.offsetTop));
      setKeyboardOffset(offset);
    };
    handleViewportChange();
    viewport.addEventListener('resize', handleViewportChange);
    viewport.addEventListener('scroll', handleViewportChange);
    return () => {
      viewport.removeEventListener('resize', handleViewportChange);
      viewport.removeEventListener('scroll', handleViewportChange);
    };
  }, []);

  useEffect(() => {
    if (!isMobileViewport) return;
    const lockRef = keyboardLockPrevRef.current;
    if (isKeyboardVisible) {
      if (lockRef.body === null) lockRef.body = document.body.style.overflow || '';
      if (lockRef.html === null) lockRef.html = document.documentElement.style.overflow || '';
      document.body.style.overflow = 'hidden';
      document.documentElement.style.overflow = 'hidden';
      return;
    }
    if (lockRef.body !== null) {
      document.body.style.overflow = lockRef.body;
      lockRef.body = null;
    }
    if (lockRef.html !== null) {
      document.documentElement.style.overflow = lockRef.html;
      lockRef.html = null;
    }
  }, [isMobileViewport, isKeyboardVisible]);

  useEffect(() => {
    const lockRef = keyboardLockPrevRef.current;
    return () => {
      if (lockRef.body !== null) {
        document.body.style.overflow = lockRef.body;
        lockRef.body = null;
      }
      if (lockRef.html !== null) {
        document.documentElement.style.overflow = lockRef.html;
        lockRef.html = null;
      }
    };
  }, []);

  useEffect(() => {
    if (!isMobileViewport) return;
    if (!showContentPanel) {
      setMobileWorkspaceTab('chat');
      return;
    }
    if (isMeetingMode || isOCRMode || isAuditMode) {
      setMobileWorkspaceTab('panel');
      return;
    }
    setMobileWorkspaceTab('chat');
  }, [isMobileViewport, showContentPanel, isMeetingMode, isOCRMode, isAuditMode]);

  useEffect(() => {
    if (!isMobileViewport || !isOCRMode) return;
    if (!activeOcrFile) {
      setOcrMobileTab('preview');
      return;
    }
    if (activeOcrFile.status === 'done' || activeOcrFile.status === 'error') {
      setOcrMobileTab('result');
    }
  }, [isMobileViewport, isOCRMode, activeOcrFile]);

  // 监听语音播放结束，重置图标状态
  useEffect(() => {
     const handleSpeechEnd = () => {
         setSpeakingIdx(null);
     };
     window.speechSynthesis.addEventListener('end', handleSpeechEnd);
     return () => {
        window.speechSynthesis.removeEventListener('end', handleSpeechEnd);
     }
  }, []);

  // -------------------------------------------------------------------------
  // 🖱️ 全局拖放处理（任意位置拖入文件都可上传）
  // -------------------------------------------------------------------------
  const processDroppedFiles = (fileList) => {
      const files = Array.from(fileList || []);
      if (!files.length) return;
      handleFileSelectRef.current?.({ target: { files } });
  };

  const formatFileSize = (size) => {
      if (!Number.isFinite(size)) return '';
      if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`;
      return `${Math.max(1, Math.round(size / 1024))} KB`;
  };

  const resolveFileUrl = (value) => {
      if (!value) return null;
      const raw = String(value);
      if (!raw) return null;
      if (/^https?:\/\//i.test(raw)) return raw;
      if (raw.startsWith('data:')) return raw;
      if (raw.startsWith('/api/static/')) return `${API_BASE_URL}${raw}`;
      if (raw.startsWith('/static/')) return `${API_BASE_URL}/api${raw}`;
      if (raw.startsWith('/')) return `${API_BASE_URL}${raw}`;
      return `${API_BASE_URL}/${raw}`;
  };

  const buildPdfPageUrl = (url, page) => {
      if (!url) return url;
      const base = String(url).split('#')[0];
      const safePage = Math.max(1, Number(page) || 1);
      return `${base}#page=${safePage}`;
  };

  const normalizeOcrEngine = (engine) => {
      const value = String(engine || '').trim().toLowerCase();
      if (!value) return 'standard';
      if (value === 'pp-ocrv5' || value === 'ppocrv5' || value === 'pp-ocr') return 'standard';
      return value;
  };

  const buildOcrEntry = (wrapper) => {
      const file = wrapper.file;
      const previewUrl = wrapper.previewUrl || URL.createObjectURL(file);
      return {
          id: wrapper.id,
          name: file.name,
          size: file.size,
          sizeLabel: formatFileSize(file.size),
          type: file.type || '',
          fileType: file.type || '',
          fileRef: file,
          previewUrl,
          serverUrl: null,
          status: 'queued',
          ocrText: '',
          ocrData: null,
          jsonText: '',
          lines: [],
          pages: [],
          error: '',
          createdAt: Date.now()
      };
  };

  const updateOcrEntry = (id, updates) => {
      setOcrFiles((prev) => prev.map((item) => (item.id === id ? { ...item, ...updates } : item)));
  };

  const saveOcrResultToHistory = async (textContent, ocrPayload, sessionIdOverride = null) => {
      const text = (textContent || "").trim();
      const payload = { ...(ocrPayload || {}) };
      if (!payload.text) payload.text = text;
      const hasContent = Boolean(
          (payload.text && payload.text.trim()) ||
          (Array.isArray(payload.lines) && payload.lines.length) ||
          payload.file_url
      );
      if (!hasContent) return null;
      const serialized = JSON.stringify(payload);

      let targetSessionId = sessionIdOverride || currentSessionId;
      if (!targetSessionId) {
          targetSessionId = crypto.randomUUID ? crypto.randomUUID() : `sid_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
          setCurrentSessionId(targetSessionId);
      }

      await savePanelContext(targetSessionId, serialized, 'ocr_context');
      if (!currentSessionId) {
          const uid = userProfile.id || 'anonymous';
          void refreshSessionList(uid);
      }
      return targetSessionId;
  };

  const triggerOcrReparse = async () => {
      if (!activeOcrFile || !activeOcrFile.fileRef) return;
      const wrapper = {
          file: activeOcrFile.fileRef,
          id: activeOcrFile.id,
          previewUrl: activeOcrFile.previewUrl
      };
      await processFiles([wrapper]);
  };

  const downloadOcrFile = (type) => {
      if (!activeOcrFile) return;
      const name = activeOcrFile.name || 'ocr_result';
      if (type === 'txt') {
          const content = activeOcrFile.ocrText || getOcrLines(activeOcrFile).map((l) => l.text).join('\n');
          const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
          const url = URL.createObjectURL(blob);
          const link = document.createElement('a');
          link.href = url;
          link.download = `${name}.txt`;
          link.click();
          URL.revokeObjectURL(url);
      } else if (type === 'json') {
          const content = activeOcrFile.jsonText || JSON.stringify(activeOcrFile.ocrData || {}, null, 2);
          const blob = new Blob([content], { type: 'application/json;charset=utf-8' });
          const url = URL.createObjectURL(blob);
          const link = document.createElement('a');
          link.href = url;
          link.download = `${name}.json`;
          link.click();
          URL.revokeObjectURL(url);
      }
  };

  const extractOcrLinesFromData = (data) => extractOcrLinesFromPayload(data);

  const extractOcrTextFromData = (data) => extractOcrTextFromPayload(data);

  const extractOcrPagesFromData = (data) => extractOcrPagesFromPayload(data);

  const getOcrLines = (file) => resolveOcrLinesForFile(file);

  useEffect(() => {
      if (!activeOcrFile) return;
      const updates = {};

      const hasLines = Array.isArray(activeOcrFile.lines) && activeOcrFile.lines.length > 0;
      const dataLines = extractOcrLinesFromData(activeOcrFile.ocrData);
      if (!hasLines && Array.isArray(dataLines) && dataLines.length) {
          updates.lines = dataLines;
      }

      const hasText = Boolean((activeOcrFile.ocrText || '').trim());
      const dataText = extractOcrTextFromData(activeOcrFile.ocrData);
      if (!hasText && dataText) {
          updates.ocrText = dataText;
      }

      const hasPages = Array.isArray(activeOcrFile.pages) && activeOcrFile.pages.length > 0;
      if (!hasPages) {
          let nextPages = extractOcrPagesFromData(activeOcrFile.ocrData);
          if (!Array.isArray(nextPages) || nextPages.length === 0) {
              const lines = updates.lines || activeOcrFile.lines || dataLines || [];
              const boxes = (lines || []).flatMap((line) => Array.isArray(line.box) ? line.box : []);
              const xs = boxes.map((p) => p[0]).filter((v) => Number.isFinite(v));
              const ys = boxes.map((p) => p[1]).filter((v) => Number.isFinite(v));
              if (xs.length && ys.length) {
                  nextPages = [{
                      page: 0,
                      width: Math.ceil(Math.max(...xs)),
                      height: Math.ceil(Math.max(...ys))
                  }];
              } else {
                  const textLineCount = (lines || []).length || (dataText ? dataText.split(/\r?\n/).filter(Boolean).length : 0);
                  nextPages = [{
                      page: 0,
                      width: 1000,
                      height: Math.max(600, textLineCount * 22 + 40)
                  }];
              }
          }
          if (Array.isArray(nextPages) && nextPages.length) {
              updates.pages = nextPages;
          }
      }

      if (Object.keys(updates).length) {
          setOcrFiles((prev) => prev.map((item) => (
              item.id === activeOcrFile.id
                  ? { ...item, ...updates }
                  : item
          )));
      }
  }, [activeOcrFile]);

  const updateOcrLine = (fileId, lineIndex, newText) => {
      setOcrFiles((prev) => prev.map((item) => {
          if (item.id !== fileId) return item;
          const lines = getOcrLines(item);
          if (!lines[lineIndex]) return item;
          const updatedLines = lines.map((line, idx) => (idx === lineIndex ? { ...line, text: newText } : line));
          const updatedText = updatedLines.map((line) => line.text).join('\n');
          return { ...item, ocrText: updatedText, lines: updatedLines };
      }));
  };

  const buildAuditHistoryText = (result, file) => {
      if (!result || typeof result !== 'object') return '';
      const riskMap = { high: '高风险', medium: '中风险', low: '低风险' };
      const riskRaw = String(result.risk_level || '').toLowerCase();
      const riskLabel = riskMap[riskRaw] || '低风险';
      const passValue = typeof result.pass === 'boolean' ? result.pass : (riskRaw ? riskRaw === 'low' : true);
      const summary = result.summary ? String(result.summary) : '';
      const auditScore = Number.isFinite(Number(result.audit_score)) ? Number(result.audit_score) : null;
      const erpTrace = result.erp_trace_id ? String(result.erp_trace_id) : '';
      const findings = Array.isArray(result.findings) ? result.findings : [];
      const topFindings = findings.slice(0, 5).map((item, idx) => {
          const message = item?.message ? String(item.message) : '风险点';
          const suggestion = item?.suggestion ? `（建议：${item.suggestion}）` : '';
          return `${idx + 1}. ${message}${suggestion}`;
      });

      const lines = [
          `【智能审单】${file?.name || '未命名文件'}`,
          `风险等级：${riskLabel}`,
          `结论：${passValue ? '通过' : '需复核'}`,
      ];
      if (auditScore !== null) lines.push(`审单评分：${auditScore}`);
      if (summary) lines.push(`摘要：${summary}`);
      if (erpTrace) lines.push(`ERP Trace：${erpTrace}`);
      if (topFindings.length) {
          lines.push('问题：');
          lines.push(...topFindings);
      } else {
          lines.push('问题：未发现明确问题');
      }
      return lines.join('\n');
  };

  const getAudioDuration = (file) => new Promise((resolve) => {
      try {
          const audio = document.createElement('audio');
          const url = URL.createObjectURL(file);
          const cleanup = () => {
              URL.revokeObjectURL(url);
              audio.removeAttribute('src');
          };
          audio.preload = 'metadata';
          audio.onloadedmetadata = () => {
              const duration = Number.isFinite(audio.duration) ? audio.duration : 0;
              cleanup();
              resolve(duration);
          };
          audio.onerror = () => {
              cleanup();
              resolve(0);
          };
          audio.src = url;
      } catch {
          resolve(0);
      }
  });

  const tryInstantTranscribe = async (file) => {
      try {
          const duration = await getAudioDuration(file);
          if (duration <= 0 || duration > INSTANT_TRANSCRIBE_MAX_SECONDS) return null;
          const wavBlob = await convertWebMToWav(file);
          const formData = new FormData();
          formData.append('file', wavBlob, 'instant.wav');
          const token = localStorage.getItem(AUTH_TOKEN_KEY);
          const voiceHeaders = token ? { Authorization: `Bearer ${token}` } : {};
          const res = await fetch(`${API_BASE_URL}/api/voice/instant`, {
              method: 'POST',
              headers: voiceHeaders,
              body: formData
          });
          const result = await res.json();
          const text = typeof result?.text === 'string' ? result.text.trim() : '';
          if (text.startsWith('❌') || text.startsWith('[ERROR]')) {
              console.warn('Instant transcribe returned legacy failure text:', text);
              return null;
          }
          if (result?.success === false) {
              console.warn('Instant transcribe failed, fallback to async:', result?.error || result);
              return null;
          }
          if (text) {
              return { text, filePath: result.file_path || null };
          }
      } catch (e) {
          console.warn('Instant transcribe failed', e);
      }
      return null;
  };

  const buildAuditBatchItems = (files) => files.map((file, index) => ({
      id: `${Date.now()}-${index}-${Math.random().toString(36).slice(2, 8)}`,
      file,
      name: file.name,
      size: file.size,
      sizeLabel: formatFileSize(file.size),
      status: 'queued'
  }));

  const resolveAuditCaseFlags = (documents = []) => {
      const tradeTags = new Set([
          'invoice',
          'packing_list',
          'bill_of_lading',
          'air_waybill',
          'customs_declaration',
          'certificate_of_origin',
          'purchase_order',
          'import_declaration',
          'export_declaration',
          'trade_case'
      ]);
      let hasContractDoc = false;
      let hasTradeDoc = false;
      for (const doc of documents) {
          const status = String(doc?.status || '').trim().toLowerCase();
          if (status === 'failed' || status === 'cancelled') continue;
          const tag = String(doc?.tag || '').trim().toLowerCase();
          const docType = String(doc?.doc_type || '').trim().toLowerCase();
          if (tag === 'contract' || docType === 'contract') hasContractDoc = true;
          if (tradeTags.has(tag) || tradeTags.has(docType)) hasTradeDoc = true;
      }
      return { hasContractDoc, hasTradeDoc };
  };

  const inferAuditUploadStep = (fileName, docTypeValue = 'auto') => {
      const normalizedDocType = String(docTypeValue || '').trim().toLowerCase();
      if (normalizedDocType === 'contract') return 1;
      if (['invoice', 'packing_list', 'bill_of_lading', 'air_waybill', 'import_declaration', 'export_declaration', 'certificate_of_origin', 'trade_case'].includes(normalizedDocType)) return 2;
      if (['payment', 'expense'].includes(normalizedDocType)) return 3;

      const name = String(fileName || '');
      const lower = name.toLowerCase();
      if (/(销售合同|采购合同|购销合同|框架合同|服务合同|劳务合同|租赁合同|contract|agreement|协议|cont\.?\s*no)/i.test(name)) return 1;
      if (/(预付款|付款申请|付款|支付|payment|expense|reimbursement|advance|prepayment|remittance|报销)/i.test(name)) return 3;
      if (/(invoice|commercial invoice|proforma invoice|packing|packing list|装箱|箱单|bill of lading|提单|b\/l|awb|air waybill|运单|shipping advice|origin|原产地|certificate of origin|declaration|报关|purchase order|采购单)/i.test(lower)) return 2;
      return 2;
  };

  const reorderAuditUploadSelection = (files, docTypeValue, existingDocs = []) => {
      if (!Array.isArray(files) || files.length <= 1) return { files, reordered: false };

      const { hasContractDoc, hasTradeDoc } = resolveAuditCaseFlags(existingDocs);
      const rankOffset = hasContractDoc ? 1 : 0;
      const paymentOffset = hasTradeDoc ? 2 : 0;
      const annotated = files.map((file, index) => {
          const step = inferAuditUploadStep(file?.name, docTypeValue);
          let rank = step;
          if (step === 1 && hasContractDoc) rank = 1 + rankOffset;
          if (step === 3 && hasTradeDoc) rank = 3 - 1;
          if (step === 3 && !hasTradeDoc) rank = 3 + paymentOffset;
          return { file, index, step, rank };
      });
      const sorted = [...annotated].sort((a, b) => {
          if (a.rank !== b.rank) return a.rank - b.rank;
          if (a.step !== b.step) return a.step - b.step;
          return a.index - b.index;
      });
      const reordered = sorted.some((item, index) => item.index !== index);
      return {
          files: sorted.map((item) => item.file),
          reordered
      };
  };

  const inspectAuditUploadSelection = (files, docTypeValue, existingDocs = []) => {
      const { hasContractDoc: initialContractFlag, hasTradeDoc: initialTradeFlag } = resolveAuditCaseFlags(existingDocs);
      let hasContractDoc = initialContractFlag;
      let hasTradeDoc = initialTradeFlag;
      const warnings = new Set();

      for (const file of files) {
          const step = inferAuditUploadStep(file?.name, docTypeValue);
          if (!hasContractDoc && step !== 1) {
              warnings.add('当前审单包还没有合同主文档，本次先按测试模式继续处理。');
          }
          if (step === 3 && !hasTradeDoc) {
              warnings.add('当前还没有履约/贸易单据，付款类单据会先做单据内审核。');
          }
          if (step === 1) hasContractDoc = true;
          if (step === 2) hasTradeDoc = true;
      }

      return Array.from(warnings).join(' ');
  };

  const resetAuditState = () => {
      setAuditState({
          status: 'idle',
          jobId: null,
          caseId: null,
          caseDocuments: [],
          progress: 0,
          stage: null,
          workflow_state: null,
          result: null,
          error: null,
          error_message: null
      });
      setAuditBatch({
          active: false,
          currentIndex: -1,
          docTypeOverride: null,
          items: []
      });
      setAuditFile(null);
      setAuditNotice('');
      setIsAuditErpActionLoading(false);
      auditBatchTransitionRef.current = '';
      auditPollGenerationRef.current = 0;
      auditPollFailureCountRef.current = 0;
      auditHistorySavedRef.current = null;
  };

  const showAuditNotice = (message) => {
      if (!message) return;
      setAuditNotice(message);
      setTimeout(() => setAuditNotice(''), 2500);
  };

  const fetchAuditCaseReport = async (caseId) => {
      const normalizedCaseId = String(caseId || '').trim();
      if (!normalizedCaseId) return null;
      try {
          const token = localStorage.getItem(AUTH_TOKEN_KEY);
          const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
          const response = await fetch(`${API_BASE_URL}/api/audit/case/${normalizedCaseId}`, { headers });
          const data = await response.json();
          if (!response.ok) {
              throw new Error(data.detail || data.error || '获取整包审单报告失败');
          }
          if (!data?.result || typeof data.result !== 'object') {
              return null;
          }
          auditHistorySavedRef.current = null;
          setAuditState((prev) => ({
              ...prev,
              status: 'done',
              progress: 100,
              stage: 'done',
              workflow_state: data.workflow_state || data.result?.workflow_state || prev.workflow_state,
              caseId: data.case_id || prev.caseId,
              caseDocuments: Array.isArray(data.case_documents) ? data.case_documents : prev.caseDocuments,
              result: data.result,
              error: null,
              error_message: null
          }));
          return data.result;
      } catch (error) {
          console.error('Failed to load audit case report', error);
          return null;
      }
  };

  const startAuditJob = async (file, options = {}) => {
      if (!file) return;
      const {
          docTypeOverride = auditDocType,
          suppressBusyCheck = false,
          batchIndex = -1,
          clientRequestId: providedClientRequestId = null
      } = options;
      if (!suppressBusyCheck && ['uploading', 'pending', 'running'].includes(auditState.status)) {
          showAuditNotice('审单进行中，请等待完成后再提交新文件。');
          return;
      }

      const name = file.name || '';
      const lower = name.toLowerCase();
      const allowedExt = ['.pdf', '.doc', '.docx', '.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff'];
      const allowedMime = [
          'application/pdf',
          'application/msword',
          'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
      ];
      const isAllowed = allowedExt.some((ext) => lower.endsWith(ext)) || (file.type && (file.type.startsWith('image/') || allowedMime.includes(file.type)));
      if (!isAllowed) {
          showAuditNotice('仅支持图片、PDF、Word 文件');
          return;
      }

      const currentCaseDocs = Array.isArray(auditState?.caseDocuments) ? auditState.caseDocuments : [];
      const currentCaseId = auditState?.caseId || '';
      const preserveCaseResult = Boolean(
          String(currentCaseId).trim()
          && currentCaseDocs.length > 0
          && auditState?.result
          && typeof auditState.result === 'object'
      );
      const uploadSequenceNotice = inspectAuditUploadSelection([file], docTypeOverride, currentCaseDocs);
      const clientRequestId = providedClientRequestId
          || (crypto.randomUUID
              ? crypto.randomUUID()
              : `audit_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`);

      setAuditNotice('');
      if (batchIndex >= 0) {
          setAuditBatch((prev) => {
              if (!prev.items[batchIndex]) return prev;
              const nextItems = prev.items.map((item, index) => (
                  index === batchIndex ? { ...item, status: 'uploading' } : item
              ));
              return {
                  ...prev,
                  currentIndex: batchIndex,
                  items: nextItems
              };
          });
      } else {
          setAuditBatch({
              active: false,
              currentIndex: 0,
              docTypeOverride,
              items: buildAuditBatchItems([file]).map((item) => ({ ...item, status: 'uploading' }))
          });
      }
      setAuditState((prev) => ({
          ...prev,
          status: 'uploading',
          jobId: null,
          progress: 0,
          stage: 'pending_docs',
          workflow_state: 'pending_docs',
          result: preserveCaseResult ? prev.result : null,
          error: null,
          error_message: null
      }));

      try {
          const effectiveAuditBackend = auditModelBackend === 'cloud' ? 'cloud' : 'local';
          const token = localStorage.getItem(AUTH_TOKEN_KEY);
          const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
          const buildStartFormData = () => {
              const formData = new FormData();
              formData.append('file', file);
              if (docTypeOverride) formData.append('doc_type', docTypeOverride);
              formData.append('model_type', effectiveAuditBackend);
              formData.append('user_id', userProfile.id || 'anonymous');
              formData.append('client_request_id', clientRequestId);
              if (currentCaseId) formData.append('case_id', currentCaseId);
              return formData;
          };
          const requestAuditStart = async () => {
              const response = await fetch(`${API_BASE_URL}/api/audit/start`, {
                  method: 'POST',
                  headers,
                  body: buildStartFormData()
              });
              let data = {};
              try {
                  data = await response.json();
              } catch (parseError) {
                  data = {};
              }
              if (!response.ok || !data?.job_id) {
                  throw new Error(data.detail || data.error || '审单启动失败');
              }
              return data;
          };
          const isTransportError = (error) => {
              const message = String(error?.message || '');
              return error instanceof TypeError
                  || /Failed to fetch|NetworkError|Load failed|Network request failed/i.test(message);
          };

          let data;
          try {
              data = await requestAuditStart();
          } catch (error) {
              if (!isTransportError(error)) {
                  throw error;
              }
              console.warn('Audit start transport error, retrying with same client_request_id', {
                  clientRequestId,
                  error
              });
              await new Promise((resolve) => window.setTimeout(resolve, 350));
              data = await requestAuditStart();
          }

          if (batchIndex >= 0) {
              setAuditBatch((prev) => {
                  if (!prev.items[batchIndex]) return prev;
                  const nextItems = prev.items.map((item, index) => (
                      index === batchIndex ? { ...item, status: data.status || 'pending' } : item
                  ));
                  return { ...prev, items: nextItems };
              });
          }
          setAuditState((prev) => ({
              ...prev,
              status: data.status || 'pending',
              jobId: data.job_id,
              caseId: data.case_id || prev.caseId,
              caseDocuments: Array.isArray(data.case_documents) ? data.case_documents : prev.caseDocuments,
              progress: 0,
              stage: data.stage || 'pending_docs',
              workflow_state: data.workflow_state || data.stage || 'pending_docs',
              result: preserveCaseResult ? prev.result : null,
              error: null,
              error_message: null
          }));
          const nextNotice = data.upload_sequence_notice || uploadSequenceNotice;
          if (nextNotice && batchIndex < 0) {
              showAuditNotice(nextNotice);
          }
          return {
              started: true,
              notice: nextNotice || ''
          };
      } catch (error) {
          const rawMessage = error?.message || '审单启动失败';
          const isTransportError = error instanceof TypeError
              || /Failed to fetch|NetworkError|Load failed|Network request failed/i.test(String(rawMessage));
          const message = isTransportError
              ? '上传请求未收到服务端响应，请稍后重试。若服务端已接收，系统会在重试时自动接回原任务。'
              : rawMessage;
          if (batchIndex >= 0) {
              setAuditBatch((prev) => {
                  if (!prev.items[batchIndex]) return { ...prev, active: false };
                  const nextItems = prev.items.map((item, index) => (
                      index === batchIndex ? { ...item, status: 'failed' } : item
                  ));
                  return { ...prev, active: false, items: nextItems };
              });
          }
          setAuditState((prev) => ({
              ...prev,
              status: 'failed',
              jobId: null,
              progress: 0,
              stage: 'failed',
              workflow_state: 'failed',
              result: preserveCaseResult ? prev.result : null,
              error: message,
              error_message: message
          }));
          return {
              started: false,
              error: message
          };
      }
  };

  const startAuditBatch = async (files) => {
      if (!Array.isArray(files) || !files.length) return;
      if (['uploading', 'pending', 'running'].includes(auditState.status) || auditBatchRef.current.active) {
          showAuditNotice('当前审单批次仍在处理中，请等待完成后再追加文件。');
          return;
      }

      const effectiveDocType = files.length > 1 ? 'auto' : auditDocType;
      const currentCaseDocs = Array.isArray(auditState?.caseDocuments) ? auditState.caseDocuments : [];
      const {
          files: orderedFiles,
          reordered: filesReordered
      } = reorderAuditUploadSelection(files, effectiveDocType, currentCaseDocs);
      const uploadSequenceNotice = inspectAuditUploadSelection(orderedFiles, effectiveDocType, currentCaseDocs);

      const items = buildAuditBatchItems(orderedFiles);
      const switchedToAuto = files.length > 1 && auditDocType !== 'auto';
      auditBatchTransitionRef.current = '';
      setAuditBatch({
          active: files.length > 1,
          currentIndex: 0,
          docTypeOverride: effectiveDocType,
          items
      });
      setAuditNotice('');
      const startResult = await startAuditJob(items[0].file, {
          docTypeOverride: effectiveDocType,
          suppressBusyCheck: true,
          batchIndex: 0
      });
      const notices = [];
      if (filesReordered && switchedToAuto) {
          notices.push('批量审单已自动切换为“自动识别”，并按合同→履约→付款顺序重排提交。');
      } else if (filesReordered) {
          notices.push('系统已按合同→履约→付款顺序自动重排本次批量审单。');
      } else if (switchedToAuto) {
          notices.push('批量审单已自动切换为“自动识别”，系统会按选择顺序逐份审单。');
      }
      if (startResult?.notice) {
          notices.push(startResult.notice);
      } else if (uploadSequenceNotice) {
          notices.push(uploadSequenceNotice);
      }
      if (notices.length) {
          showAuditNotice(notices.join(' '));
      }
  };

  const handleAuditFileSelect = async (e) => {
      const files = Array.from(e?.target?.files || []);
      if (!files.length) return;
      await startAuditBatch(files);
      if (e?.target) e.target.value = '';
  };

  const handleAuditErpAction = async (action, comment = '') => {
      if (!auditState?.jobId || auditState?.status !== 'done' || isAuditErpActionLoading) return;
      const allowed = ['approved', 'rejected', 'need_more'];
      if (!allowed.includes(action)) {
          showAuditNotice('ERP 回写动作不合法');
          return;
      }
      setIsAuditErpActionLoading(true);
      try {
          const token = localStorage.getItem(AUTH_TOKEN_KEY);
          const headers = {
              'Content-Type': 'application/json',
              ...(token ? { Authorization: `Bearer ${token}` } : {})
          };
          const res = await fetch(`${API_BASE_URL}/api/audit/${auditState.jobId}/erp-action`, {
              method: 'POST',
              headers,
              body: JSON.stringify({
                  action,
                  operator_id: userProfile?.id || 'anonymous',
                  comment: comment || ''
              })
          });
          const data = await res.json();
          if (!res.ok || !data?.success) {
              throw new Error(data?.detail || data?.error || 'ERP 回写失败');
          }
          setAuditState((prev) => ({
              ...prev,
              result: data?.result || prev.result
          }));
          const traceId = data?.erp_action?.trace_id;
          showAuditNotice(traceId ? `ERP 回写成功：${traceId}` : 'ERP 回写成功');
      } catch (error) {
          showAuditNotice(error?.message || 'ERP 回写失败');
      } finally {
          setIsAuditErpActionLoading(false);
      }
  };


  const handleOpenSettingsModal = (category = 'general') => {
      setSettingsModalState({ isOpen: true, category });
  };

  const handleModelChange = (modelId) => {
      if (isProcessing) return;
      if (selectedModel === modelId) {
          if (modelId === 3) {
              // Re-enter writing assistant from the mode switch: always return to first-level choices.
              setWritingEntryMode('root');
              setReportStep('selection');
              setReportType(null);
              setReportFormData({});
              setReportAudienceInput('');
              setStandalonePptForm(buildDefaultStandalonePptFormData());
              setStandalonePptOutline(null);
              setIsOutlineEditorOpen(false);
              setIsPptWorkspaceOpen(false);
              setIsTemplatePreviewOpen(false);
              setTemplatePreviewSelection({ routeId: '', templateId: '' });
              setStandalonePptResult(null);
              setIsPresentonGenerating(false);
              setIsOutlineGenerating(false);
              setPresentonProgress(createIdlePresentonProgress());
          }
          return;
      }

      if (modelId !== 0 && (currentMode === 'database' || currentMode === 'rag' || currentMode === 'search')) {
          onModeChange('general');
      }

      setSelectedModel(modelId);
      setChatHistory([]);
      setFeedbackState({});
      currentSessionIdRef.current = null;
      resetHistoryPaginationState();
      clearHistoryExpandTask();
      setHistoryRenderTarget(INITIAL_MESSAGE_COUNT);
      setVisibleMessageCount(INITIAL_MESSAGE_COUNT);
      setExpandedSources({});
      setCurrentSessionId(null);
      setPanelContent('');
      setAudioFileUrl(null);
      setCurrentAudioPath(null);
      setPendingFiles([]);
      resetAuditState();
      setOcrFiles([]);
      setActiveOcrId(null);
      setOcrPageIndex(0);
      setSelectedOcrLine(null);
      setEditingOcrLine(null);
      setEditingOcrValue('');
      setJsonEditError('');
      setCopyToast('');
      setIsOcrSummaryOpen(false);
      setOcrSummaryMessages([]);
      setOcrSummaryInput('');
      setIsOcrSummaryLoading(false);
      setOcrSummaryFileId(null);
      setOcrSummaryBackend('local');
      setOcrSummaryFirstDone(false);
      ocrSummarySessionIdRef.current = null;
      ocrSummaryContextRef.current = '';
      ocrSummaryBufferRef.current = [];
      ocrSummaryDisplayRef.current = '';
      if (ocrSummaryAbortRef.current) {
          ocrSummaryAbortRef.current.abort();
          ocrSummaryAbortRef.current = null;
      }
      if (ocrSummaryTimeoutRef.current) {
          clearTimeout(ocrSummaryTimeoutRef.current);
          ocrSummaryTimeoutRef.current = null;
      }
      if (ocrSummaryIdleTimerRef.current) {
          clearInterval(ocrSummaryIdleTimerRef.current);
          ocrSummaryIdleTimerRef.current = null;
      }

      setReportStep('selection');
      setReportType(null);
      setReportFormData({});
      setReportAudienceInput('');
      setWritingEntryMode('root');
      setStandalonePptForm(buildDefaultStandalonePptFormData());
      setStandalonePptOutline(null);
      setIsOutlineEditorOpen(false);
      setIsPptWorkspaceOpen(false);
      setIsTemplatePreviewOpen(false);
      setTemplatePreviewSelection({ routeId: '', templateId: '' });
      setStandalonePptResult(null);
      setIsPresentonGenerating(false);
      setIsOutlineGenerating(false);
      setPresentonProgress(createIdlePresentonProgress());
      setSpeakingIdx(null);
      window.speechSynthesis.cancel();
  };

  const handleOpenDecisionCenter = (event) => {
      event?.preventDefault?.();
      event?.stopPropagation?.();
      if (typeof window === 'undefined') return;
      const popup = window.open('/decision', '_blank', 'noopener,noreferrer');
      if (!popup) {
          console.warn('Popup blocked when opening decision center.');
          return;
      }
      try {
          popup.opener = null;
      } catch {
          // Ignore browsers that disallow writing to opener.
      }
  };

  const handleOpenTaskCenter = (event) => {
      event?.preventDefault?.();
      event?.stopPropagation?.();
      setIsTaskCenterOpen((prev) => !prev);
  };

  const handleGoToTaskCenterPage = (event) => {
      event?.preventDefault?.();
      event?.stopPropagation?.();
      setIsTaskCenterOpen(false);
      if (typeof window === 'undefined') return;
      const popup = window.open('/tasks', '_blank', 'noopener,noreferrer');
      if (!popup) {
          console.warn('Popup blocked when opening task center page.');
          return;
      }
      try {
          popup.opener = null;
      } catch {
          // Ignore browsers that disallow writing to opener.
      }
  };

  const handleMeetingUploadClick = () => {
      if (fileInputRef.current) {
          fileInputRef.current.click();
      }
  };

  const handleLoadMoreMessages = useCallback(() => {
    if (normalizedVisibleCount < chatHistory.length) {
      setVisibleMessageCount((count) => Math.min(chatHistory.length, count + INITIAL_MESSAGE_COUNT));
      return;
    }
    if (historyHasMoreServer && !isHistoryPageLoading) {
      void loadOlderSessionMessages();
    }
  }, [chatHistory.length, historyHasMoreServer, isHistoryPageLoading, loadOlderSessionMessages, normalizedVisibleCount]);

  const loadSessionFeedbackState = useCallback(async (sessionId) => {
    const safeSessionId = String(sessionId || '').trim();
    const safeUserId = String(userProfile?.id || '').trim();
    if (!safeSessionId || !safeUserId || safeUserId === 'anonymous') {
      setFeedbackState({});
      return {};
    }

    try {
      const nextFeedbackMap = await chatFeedbackApi.getSessionFeedback(safeSessionId);
      setFeedbackState(nextFeedbackMap || {});
      return nextFeedbackMap || {};
    } catch (error) {
      console.error('Failed to load session feedback', error);
      setFeedbackState({});
      return {};
    }
  }, [userProfile?.id]);

  const handleSessionClick = async (sessionId) => {
    if (isProcessing) return;
    setIsMobileSidebarOpen(false);
    setIsProcessing(true);
    setIsPresentonGenerating(false);
    setIsOutlineGenerating(false);
    setIsOutlineEditorOpen(false);
    setIsPptWorkspaceOpen(false);
    setIsTemplatePreviewOpen(false);
    setTemplatePreviewSelection({ routeId: '', templateId: '' });
    setPresentonProgress(createIdlePresentonProgress());
    setAudioFileUrl(null);
    setCurrentAudioPath(null);
    setPendingFiles([]);
    setFeedbackState({});
    currentSessionIdRef.current = null;
    resetHistoryPaginationState();
    resetAuditState();
    setSpeakingIdx(null);
    window.speechSynthesis.cancel();

    try {
      const uid = userProfile.id || 'anonymous';
      const messagePage = await historyApi.getSessionMessagesPage(sessionId, uid, {
        limit: HISTORY_PAGE_SIZE,
        includeContext: true,
      });
      await loadSessionFeedbackState(sessionId);
      const safeMessages = [...(messagePage.contextItems || []), ...(messagePage.items || [])];

      let metaMsg = null;
      let contextMsg = null;
      for (let i = safeMessages.length - 1; i >= 0; i -= 1) {
        const msg = safeMessages[i];
        if (!metaMsg && msg.role === 'meta' && msg.func_type === 'session_meta') metaMsg = msg;
        if (!contextMsg && msg.role === 'context') contextMsg = msg;
        if (metaMsg && contextMsg) break;
      }

      // 默认按“通用聊天”恢复，避免在 OCR/会议模式下点击普通聊天历史时看不到消息。
      let targetModel = 0;
      let targetMode = 'general';
      let loadedAudioPath = null;
      let savedBackend = 'local';

      if (metaMsg?.content) {
        try {
          const meta = JSON.parse(metaMsg.content);
          if (meta?.modelId !== undefined) targetModel = Number(meta.modelId);
          if (meta?.mode) targetMode = String(meta.mode);
          if (meta?.audio_path) loadedAudioPath = meta.audio_path;
          if (meta?.backend) savedBackend = meta.backend;
        } catch (error) {
          console.warn('Invalid session_meta json:', metaMsg.content, error);
        }
      }
      else if (contextMsg) {
        const contextType = contextMsg.func_type;
        if (contextType === 'voice_context') targetModel = 1;
        else if (contextType === 'ocr_context') targetModel = 2;
        else if (contextType === 'audit_context') targetModel = 4;
        targetMode = 'general';
      } else {
        const latestChatLikeMsg = [...safeMessages].reverse().find((msg) => msg?.role === 'user' || msg?.role === 'assistant');
        const inferredType = String(latestChatLikeMsg?.func_type || '').toLowerCase();
        if (inferredType === 'database' || inferredType === 'rag' || inferredType === 'search') {
          targetMode = inferredType;
        } else if (inferredType === 'meeting') {
          targetModel = 1;
        } else if (inferredType === 'audit') {
          targetModel = 4;
          targetMode = 'general';
        }
      }

      if (targetMode === 'audit') targetMode = 'general';

      setSelectedModel(targetModel);
      setLlmBackend(savedBackend);
      if (targetMode && targetMode !== currentMode) onModeChange(targetMode);
      const restoredStandalonePptState = targetModel === 3 ? parseStandalonePptHistoryState(safeMessages) : null;
      const isStandalonePptHistory = !!restoredStandalonePptState;

      const normalizedChatMsgs = normalizeHistoryChatMessages(messagePage.items);
      const resolvedChatHistory = normalizedChatMsgs.length > 0
        ? normalizedChatMsgs
        : (isStandalonePptHistory
          ? []
          : safeMessages.length > 0
          ? [{
              role: 'assistant',
              content: '该历史会话未找到可展示的对话消息（仅包含上下文/元数据）。'
            }]
          : [{
              role: 'assistant',
              content: '该历史会话暂无内容。'
            }]);
      setHistoryRenderTarget(HISTORY_FIRST_PAINT_COUNT);
      setChatHistory(resolvedChatHistory);
      setVisibleMessageCount(Math.min(HISTORY_FIRST_PAINT_COUNT, resolvedChatHistory.length));
      setExpandedSources({});
      setHistoryCursor(messagePage.nextBeforeId);
      setHistoryHasMoreServer(Boolean(messagePage.hasMore));
      scheduleHistoryExpand();
      setPanelContent(isStandalonePptHistory ? '' : (contextMsg ? contextMsg.content : ''));
      currentSessionIdRef.current = sessionId;
      setCurrentSessionId(sessionId);

      if (targetModel === 2 && contextMsg?.content) {
        let ocrEntry = null;
        try {
          const parsed = JSON.parse(contextMsg.content);
          const dataLines = parsed?.lines || parsed?.data?.lines || [];
          const dataPages = parsed?.pages || parsed?.data?.pages || [];
          const fileUrl = parsed?.file_url || parsed?.data?.file_url || parsed?.ocrData?.file_url || parsed?.ocrData?.data?.file_url || '';
          const fileType = parsed?.file_type || parsed?.data?.file_type || parsed?.ocrData?.file_type || parsed?.ocrData?.data?.file_type || '';
          const fileName = parsed?.file_name || parsed?.data?.file_name || parsed?.ocrData?.file_name || parsed?.ocrData?.data?.file_name || '历史记录';
          const previewUrl = resolveFileUrl(fileUrl);
          let pages = dataPages;
          if (!pages || pages.length === 0) {
            const maxX = (dataLines || []).flatMap((l) => (l.box || []).map((p) => p[0]));
            const maxY = (dataLines || []).flatMap((l) => (l.box || []).map((p) => p[1]));
            if (maxX.length && maxY.length) {
              pages = [{ page: 0, width: Math.ceil(Math.max(...maxX)), height: Math.ceil(Math.max(...maxY)) }];
            }
          }
          ocrEntry = {
            id: `history_${sessionId}`,
            name: fileName,
            size: 0,
            sizeLabel: '',
            type: 'history/ocr',
            fileType: fileType || '',
            fileRef: null,
            previewUrl: previewUrl,
            serverUrl: previewUrl,
            status: 'done',
            ocrText: parsed?.text || parsed?.data?.text || '',
            ocrData: parsed?.ocrData || parsed,
            jsonText: parsed ? JSON.stringify(parsed?.ocrData || parsed, null, 2) : '',
            lines: dataLines || [],
            pages: pages || [],
            error: '',
            createdAt: Date.now()
          };
        } catch {
          const text = contextMsg.content || '';
          const lines = text.split(/\r?\n/).filter(Boolean);
          ocrEntry = {
            id: `history_${sessionId}`,
            name: '历史记录',
            size: 0,
            sizeLabel: '',
            type: 'history/ocr',
            fileRef: null,
            previewUrl: null,
            jsonText: '',
            status: 'done',
            ocrText: text,
            ocrData: null,
            lines: [],
            pages: [{ page: 0, width: 1000, height: Math.max(600, lines.length * 22 + 40) }],
            error: '',
            createdAt: Date.now()
          };
        }
        setOcrFiles(ocrEntry ? [ocrEntry] : []);
        setActiveOcrId(ocrEntry ? ocrEntry.id : null);
      }

      if (loadedAudioPath) {
          setCurrentAudioPath(loadedAudioPath);
          try {
              const res = await fetch(`${API_BASE_URL}/api/voice/playback_url?path=${encodeURIComponent(loadedAudioPath)}`);
              const data = await res.json();
              if (data.success && data.url) {
                  setAudioFileUrl(data.url);
              }
          } catch (e) {
              console.error("Failed to load audio url", e);
          }
      }

      if (targetModel === 3) {
        setReportStep('selection');
        setReportType(isStandalonePptHistory ? 'ppt' : null);
        setReportFormData({});
        setReportAudienceInput('');
        if (isStandalonePptHistory) {
          const restoredOutline = restoredStandalonePptState?.outline || null;
          const restoredResult = restoredStandalonePptState?.result || null;
          const restoredTemplate = String(restoredStandalonePptState?.template || "general").trim() || "general";
          const restoredProgress = restoredStandalonePptState?.progress || createIdlePresentonProgress();
          const restoredFocusKey = String(restoredStandalonePptState?.outline?.contentFocus || STANDALONE_PPT_DEFAULT_CONTENT_FOCUS).trim();
          const restoredFocus = getStandalonePptContentFocusConfig(restoredFocusKey);
          const hasRestoredOutline = Array.isArray(restoredOutline?.slides) && restoredOutline.slides.length > 0;
          const hasRestoredResult = !!(restoredResult?.downloadUrl || restoredResult?.editUrl || restoredResult?.error);
          setWritingEntryMode('ppt');
          setStandalonePptForm(() => ({
            ...buildDefaultStandalonePptFormData(),
            contentFocus: restoredFocus.key,
            requireMetrics: !!restoredFocus.emphasizeMetrics,
            template: restoredTemplate,
            includeImages: true,
          }));
          setStandalonePptOutline(restoredOutline);
          setStandalonePptResult(restoredResult);
          setIsPptWorkspaceOpen(hasRestoredOutline || hasRestoredResult);
          setPresentonProgress({
            taskId: String(restoredProgress?.taskId || ''),
            status: String(restoredProgress?.status || 'idle'),
            progress: Math.max(0, Math.min(100, Number(restoredProgress?.progress) || 0)),
            message: String(restoredProgress?.message || ''),
            previewLines: Array.isArray(restoredProgress?.previewLines) ? restoredProgress.previewLines : [],
            previewCursor: Math.max(0, Number(restoredProgress?.previewCursor) || 0),
          });
        } else {
          // 写作模式普通会话回到一级入口（写作助手 / PPT生成）
          setWritingEntryMode('root');
          setStandalonePptForm(buildDefaultStandalonePptFormData());
          setStandalonePptOutline(null);
          setStandalonePptResult(null);
          setIsPptWorkspaceOpen(false);
          setPresentonProgress(createIdlePresentonProgress());
        }
        setIsOutlineEditorOpen(false);
        setIsTemplatePreviewOpen(false);
        setTemplatePreviewSelection({ routeId: '', templateId: '' });
        setIsPresentonGenerating(false);
        setIsOutlineGenerating(false);
      } else {
        setWritingEntryMode('root');
        setReportStep('selection');
        setReportType(null);
        setReportFormData({});
        setReportAudienceInput('');
        setStandalonePptForm(buildDefaultStandalonePptFormData());
        setStandalonePptOutline(null);
        setIsOutlineEditorOpen(false);
        setIsPptWorkspaceOpen(false);
        setIsTemplatePreviewOpen(false);
        setTemplatePreviewSelection({ routeId: '', templateId: '' });
        setStandalonePptResult(null);
        setIsPresentonGenerating(false);
        setIsOutlineGenerating(false);
        setPresentonProgress(createIdlePresentonProgress());
      }
    } catch (e) {
      console.error("Failed to load session", e);
      setFeedbackState({});
      setChatHistory([{
        role: 'assistant',
        content: '历史会话加载失败，请重试。'
      }]);
      setVisibleMessageCount(1);
      setExpandedSources({});
    } finally {
      setIsProcessing(false);
    }
  };


  const handleNewChat = () => {
      setChatHistory([]);
      setFeedbackState({});
      currentSessionIdRef.current = null;
      resetHistoryPaginationState();
      clearHistoryExpandTask();
      setHistoryRenderTarget(INITIAL_MESSAGE_COUNT);
      setVisibleMessageCount(0);
      setExpandedSources({});
      setCurrentSessionId(null);
      setPanelContent('');
      setAudioFileUrl(null);
      setCurrentAudioPath(null);
      setPendingFiles([]);
            setOcrFiles([]);
            setActiveOcrId(null);
            setOcrPageIndex(0);
            setSelectedOcrLine(null);
            setEditingOcrLine(null);
            setEditingOcrValue('');
            setJsonEditError('');
      resetAuditState();
      setIsMobileSidebarOpen(false);
      setReportStep('selection');
      setReportType(null);
      setReportFormData({});
      setReportAudienceInput('');
      setWritingEntryMode('root');
      setStandalonePptForm(buildDefaultStandalonePptFormData());
      setStandalonePptOutline(null);
      setIsOutlineEditorOpen(false);
      setIsPptWorkspaceOpen(false);
      setIsTemplatePreviewOpen(false);
      setTemplatePreviewSelection({ routeId: '', templateId: '' });
      setStandalonePptResult(null);
      setIsPresentonGenerating(false);
      setIsOutlineGenerating(false);
      setPresentonProgress(createIdlePresentonProgress());
      setSpeakingIdx(null);
      window.speechSynthesis.cancel();
  };

  sessionClickHandlerRef.current = handleSessionClick;
  newChatHandlerRef.current = handleNewChat;

  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (hasHandledInitialRouteRef.current) return;
    if (isProfileLoading || isSessionsLoading) return;
    const uid = userProfile?.id;
    if (!uid || uid === 'anonymous') {
      hasHandledInitialRouteRef.current = true;
      setIsInitialRouteLoading(false);
      return;
    }

    hasHandledInitialRouteRef.current = true;
    const routeSessionId = initialRouteSessionIdRef.current || extractConversationSessionId(window.location.pathname);
    if (!routeSessionId || routeSessionId === currentSessionId) return;

    isApplyingRouteSessionRef.current = true;
    Promise.resolve(sessionClickHandlerRef.current?.(routeSessionId)).finally(() => {
      isApplyingRouteSessionRef.current = false;
      setIsInitialRouteLoading(false);
    });
  }, [isInitialRouteLoading, isProfileLoading, isSessionsLoading, userProfile?.id, currentSessionId]);

  useEffect(() => {
    if (!isInitialRouteLoading) return;
    if (typeof window === 'undefined') {
      setIsInitialRouteLoading(false);
      return;
    }
    const routeSessionId = initialRouteSessionIdRef.current;
    if (!routeSessionId) {
      setIsInitialRouteLoading(false);
      return;
    }
    if (currentSessionId && currentSessionId === routeSessionId) {
      setIsInitialRouteLoading(false);
    }
  }, [isInitialRouteLoading, isProfileLoading, isSessionsLoading, userProfile?.id, currentSessionId]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (!hasHandledInitialRouteRef.current) return;
    if (isApplyingRouteSessionRef.current) return;
    const nextPath = buildConversationPath(currentSessionId);
    const currentPath = normalizePathname(window.location.pathname);
    if (currentPath === nextPath) return;
    window.history.pushState(window.history.state, '', nextPath);
  }, [currentSessionId]);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const handlePopState = () => {
      const routeSessionId = extractConversationSessionId(window.location.pathname);
      if (routeSessionId) {
        if (routeSessionId === currentSessionId) return;
        isApplyingRouteSessionRef.current = true;
        Promise.resolve(sessionClickHandlerRef.current?.(routeSessionId)).finally(() => {
          isApplyingRouteSessionRef.current = false;
        });
        return;
      }
      if (currentSessionId) {
        newChatHandlerRef.current?.();
      }
    };

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, [currentSessionId]);

  const models = useMemo(() => {
    if (appSettings?.showAdvancedModels === false) {
      return MODEL_OPTIONS.filter((item) => item.id === 0);
    }
    return MODEL_OPTIONS;
  }, [appSettings?.showAdvancedModels]);
  const selectedModelInfo = useMemo(() => {
    return models.find((m) => m.id === selectedModel) || MODEL_OPTIONS[0];
  }, [models, selectedModel]);

  useEffect(() => {
    currentSessionIdRef.current = currentSessionId;
  }, [currentSessionId]);

  useEffect(() => {
    if (!models.some((item) => item.id === selectedModel)) {
      setSelectedModel(0);
    }
  }, [models, selectedModel]);

  const savePanelContext = useCallback(async (sid, content, type = 'context_save') => {
      if (!sid || !content) return;
      try {
          setIsSavingContext(true);
          await historyApi.saveContext(sid, content, userProfile.id, type);
      } catch (e) {
          console.error("Failed to save context", e);
      } finally {
          setIsSavingContext(false);
      }
  }, [userProfile.id]);

  const saveSessionMeta = useCallback(async (sid, modelId, mode, audioPath = null, backend = 'local') => {
    if (!sid) return;
    try {
        const metaObj = {
            modelId: Number(modelId),
            mode: String(mode || 'general'),
            backend: backend
        };
        if (audioPath) {
            metaObj.audio_path = audioPath;
        }

        const meta = JSON.stringify(metaObj);
        await historyApi.saveContext(sid, meta, userProfile.id, 'session_meta');
    } catch (e) {
        console.error("Failed to save session meta", e);
    }
  }, [userProfile.id]);

  const createClientSessionId = () => (
      crypto.randomUUID ? crypto.randomUUID() : `sid_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
  );

  const ensureHistorySessionForCreative = useCallback(() => {
      let sid = currentSessionId;
      if (!sid) {
          sid = crypto.randomUUID ? crypto.randomUUID() : `sid_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
          setCurrentSessionId(sid);
      }
      return sid;
  }, [currentSessionId]);

  const refreshSessionListForCreative = useCallback(async () => {
      const uid = userProfile.id || 'anonymous';
      try {
          await refreshSessionList(uid);
      } catch (e) {
          console.error("Failed to refresh creative sessions", e);
      }
  }, [refreshSessionList, userProfile.id]);

  const persistStandaloneCreativeHistory = useCallback(async (content, contextType = 'ppt_context') => {
      const safeContent = String(content || '').trim();
      if (!safeContent) return null;
      const sid = ensureHistorySessionForCreative();
      try {
          await savePanelContext(sid, safeContent.slice(0, 12000), contextType);
          await saveSessionMeta(sid, 3, 'general', currentAudioPath, llmBackend);
          await refreshSessionListForCreative();
      } catch (e) {
          console.error("Failed to persist standalone creative history", e);
      }
      return sid;
  }, [
      currentAudioPath,
      ensureHistorySessionForCreative,
      llmBackend,
      refreshSessionListForCreative,
      savePanelContext,
      saveSessionMeta,
  ]);

  const pollPresentonTaskUntilSettled = useCallback(async ({
      taskId,
      outlineTitle,
      slideCount,
      templateId,
      contentFocusLabel,
      sessionId,
      shouldPersistResult = true,
  }) => {
      const safeTaskId = String(taskId || '').trim();
      if (!safeTaskId) return null;
      if (presentonPollingTaskRef.current === safeTaskId) return null;

      presentonPollingTaskRef.current = safeTaskId;
      const boundSessionId = String(sessionId || currentSessionIdRef.current || '').trim();

      try {
          const deadline = Date.now() + 15 * 60 * 1000;
          let finalResult = null;

          while (Date.now() < deadline) {
              if (boundSessionId && currentSessionIdRef.current && boundSessionId !== currentSessionIdRef.current) {
                  return null;
              }

              const statusResult = await presentationApi.getPresentonPptTaskStatus(safeTaskId);
              const status = String(statusResult?.status || 'pending').toLowerCase();
              const progressValue = Math.max(0, Math.min(100, Number(statusResult?.progress) || 0));
              const message = String(statusResult?.message || '');
              const isSuccessStatus = ['completed', 'done', 'success', 'succeeded'].includes(status);
              const isFailureStatus = ['failed', 'error', 'cancelled', 'canceled'].includes(status);

              setPresentonProgress((prev) => {
                  const previous = Math.max(0, Math.min(100, Number(prev?.progress) || 0));
                  let nextProgress = progressValue;
                  if (isSuccessStatus) {
                      nextProgress = 100;
                  } else if (!isFailureStatus) {
                      nextProgress = Math.max(previous, progressValue, 12);
                  }
                  const nextMessage = message || prev?.message || '';
                  if (
                      prev?.taskId === safeTaskId
                      && prev?.status === status
                      && Number(prev?.progress || 0) === nextProgress
                      && String(prev?.message || '') === nextMessage
                  ) {
                      return prev;
                  }
                  return {
                      taskId: safeTaskId,
                      status,
                      progress: nextProgress,
                      message: nextMessage,
                  };
              });

              if (isSuccessStatus) {
                  finalResult = statusResult;
                  break;
              }

              if (isFailureStatus) {
                  throw new Error(message || 'PPT 生成失败');
              }

              await new Promise((resolve) => setTimeout(resolve, 1800));
          }

          if (!finalResult) {
              throw new Error('PPT 生成超时，请稍后重试');
          }

          const provider = finalResult?.provider || 'presenton';
          const downloadUrl = finalResult?.download_url || '';
          const editUrl = normalizePresentonEditUrl(finalResult?.edit_url || '');
          setPresentonProgress({
              taskId: safeTaskId,
              status: 'completed',
              progress: 100,
              message: 'PPT 生成完成',
          });
          setStandalonePptResult({
              provider,
              slideCount,
              contentFocus: contentFocusLabel,
              downloadUrl,
              editUrl,
              finishedAt: new Date().toISOString(),
          });
          setIsPptWorkspaceOpen(true);

          if (shouldPersistResult) {
              await persistStandaloneCreativeHistory(
                  [
                      `[智能创作/PPT生成完成] ${outlineTitle}（${slideCount}页）`,
                      `模板：${templateId}`,
                      `下载链接：${downloadUrl || '无'}`,
                      `在线编辑：${editUrl || '无'}`,
                  ].join('\n'),
                  'ppt_result',
              );
          }

          return finalResult;
      } catch (error) {
          const errMsg = String(error?.message || '未知错误');
          setPresentonProgress((prev) => ({
              ...prev,
              taskId: safeTaskId,
              status: 'failed',
              message: errMsg,
          }));
          setStandalonePptResult({
              error: errMsg,
          });
          setIsPptWorkspaceOpen(true);

          if (shouldPersistResult) {
              await persistStandaloneCreativeHistory(
                  [
                      `[智能创作/PPT生成失败] ${outlineTitle}（${slideCount}页）`,
                      `模板：${templateId}`,
                      `错误：${errMsg}`,
                  ].join('\n'),
                  'ppt_result',
              );
          }

          return null;
      } finally {
          if (presentonPollingTaskRef.current === safeTaskId) {
              presentonPollingTaskRef.current = '';
          }
          setIsPresentonGenerating(false);
      }
  }, [persistStandaloneCreativeHistory]);

  useEffect(() => {
      const taskId = String(presentonProgress?.taskId || '').trim();
      const status = String(presentonProgress?.status || 'idle').toLowerCase();
      const hasResult = !!(standalonePptResult?.downloadUrl || standalonePptResult?.editUrl || standalonePptResult?.error);
      const isTerminalStatus = ['completed', 'done', 'success', 'succeeded', 'failed', 'error', 'cancelled', 'canceled', 'idle', 'outline_ready'].includes(status);

      if (!taskId || hasResult || isTerminalStatus || isPresentonGenerating) return;
      if (presentonPollingTaskRef.current === taskId) return;

      const outlineTitle = String(standalonePptOutline?.title || '业务汇报').trim() || '业务汇报';
      const slideCount = Math.max(
          1,
          Number(standalonePptOutline?.slides?.length) || Number(standalonePptForm?.pptSlideCount) || 8,
      );
      const templateId = normalizeStandalonePptTemplateId(standalonePptForm?.template || 'general') || 'general';
      const focusConfig = getStandalonePptContentFocusConfig(
          standalonePptOutline?.contentFocus || standalonePptForm?.contentFocus || STANDALONE_PPT_DEFAULT_CONTENT_FOCUS,
      );

      setIsPresentonGenerating(true);
      pollPresentonTaskUntilSettled({
          taskId,
          outlineTitle,
          slideCount,
          templateId,
          contentFocusLabel: focusConfig.label,
          sessionId: currentSessionId,
      }).catch((error) => {
          console.error('Failed to resume Presenton task polling', error);
      });
  }, [
      currentSessionId,
      isPresentonGenerating,
      pollPresentonTaskUntilSettled,
      presentonProgress?.status,
      presentonProgress?.taskId,
      standalonePptForm?.contentFocus,
      standalonePptForm?.pptSlideCount,
      standalonePptForm?.template,
      standalonePptOutline,
      standalonePptResult,
  ]);

  useEffect(() => {
      if (!isAuditMode) return;
      if (auditState.status !== 'done' || !auditState.jobId || !auditState.result) return;
      if (auditHistorySavedRef.current === auditState.jobId) return;

      const persistAuditHistory = async () => {
          const content = buildAuditHistoryText(auditState.result, auditFile);
          auditHistorySavedRef.current = auditState.jobId;
          if (!content) return;

          let targetSessionId = currentSessionId;
          if (!targetSessionId) {
              targetSessionId = crypto.randomUUID ? crypto.randomUUID() : `sid_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
              setCurrentSessionId(targetSessionId);
          }

          try {
              await savePanelContext(targetSessionId, content, 'audit_context');
              await saveSessionMeta(targetSessionId, selectedModel, currentMode, currentAudioPath, llmBackend);

              if (!currentSessionId) {
                  const uid = userProfile.id || 'anonymous';
                  void refreshSessionList(uid);
              }
          } catch {
              auditHistorySavedRef.current = null;
          }
      };

      persistAuditHistory();
  }, [
      auditState.status,
      auditState.jobId,
      auditState.result,
      auditFile,
      isAuditMode,
      currentSessionId,
      selectedModel,
      currentMode,
      currentAudioPath,
      llmBackend,
      refreshSessionList,
      savePanelContext,
      saveSessionMeta,
      userProfile.id
  ]);

  const handleManualSave = async () => {
      if (!panelContent || !panelContent.trim()) return;
      let targetSessionId = currentSessionId;
      if (!targetSessionId) {
          targetSessionId = crypto.randomUUID ? crypto.randomUUID() : `sid_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
          setCurrentSessionId(targetSessionId);
      }
      let type = 'context_save';
      if (isMeetingMode) type = 'voice_context';
      if (isOCRMode) type = 'ocr_context';
      if (isAuditMode) type = 'audit_context';
      await savePanelContext(targetSessionId, panelContent, type);
      await saveSessionMeta(targetSessionId, selectedModel, currentMode, currentAudioPath, llmBackend);

      if (!currentSessionId) {
          const uid = userProfile.id || 'anonymous';
          void refreshSessionList(uid);
      }
  };

  // -------------------------------------------------------------------------
  // 🚀 文件上传和处理逻辑
  // -------------------------------------------------------------------------
  const applyFileContext = async (context, audioPathOverride = null, options = {}) => {
      if (!context) return;

      const replaceExisting = options?.replaceExisting === true;
      const forcedSessionId = String(options?.sessionIdOverride || '').trim();
      const baseContent = replaceExisting ? '' : panelContent;
      const newContent = (baseContent ? baseContent + '\n\n' : '') + context;
      setPanelContent(newContent);

      let targetSessionId = forcedSessionId || currentSessionIdRef.current || currentSessionId;
      if (!targetSessionId) {
          targetSessionId = createClientSessionId();
          currentSessionIdRef.current = targetSessionId;
          setCurrentSessionId(targetSessionId);
      } else if (forcedSessionId && forcedSessionId !== currentSessionId) {
          currentSessionIdRef.current = targetSessionId;
          setCurrentSessionId(targetSessionId);
      }

      let type = 'context_save';
      if (isMeetingMode) type = 'voice_context';
      if (isOCRMode) type = 'ocr_context';
      if (isAuditMode) type = 'audit_context';
      await savePanelContext(targetSessionId, newContent, type);

      if (isMeetingMode) {
          const audioPath = audioPathOverride || currentAudioPath;
          if (audioPath) {
              if (audioPathOverride && audioPathOverride !== currentAudioPath) {
                  setCurrentAudioPath(audioPathOverride);
              }
              await saveSessionMeta(targetSessionId, selectedModel, currentMode, audioPath, llmBackend);
          }
      }

      if (!currentSessionId || (forcedSessionId && forcedSessionId !== currentSessionId)) {
          const uid = userProfile.id || 'anonymous';
          void refreshSessionList(uid);
      }
  };

  const applyOcrContext = (context, sessionId) => {
      if (!context) return;
      setPanelContent((prev) => (prev ? `${prev}\n\n${context}` : context));
      if (sessionId && sessionId !== currentSessionId) {
          setCurrentSessionId(sessionId);
      }
  };

  const updatePendingFile = (id, updates) => {
      setPendingFiles(prev => prev.map(pf => (pf.id === id ? { ...pf, ...updates } : pf)));
  };

  const uploadDocumentWithProgress = (wrapper) => {
      const formData = new FormData();
      formData.append('files', wrapper.file);
      if (userProfile?.id) {
      formData.append('user_id', userProfile.id);
      }

      const sendOnce = (authToken) => (
          new Promise((resolve, reject) => {
              const xhr = new XMLHttpRequest();
              xhr.open('POST', `${API_BASE_URL}/api/documents/upload`);
              if (authToken) {
                  xhr.setRequestHeader('Authorization', `Bearer ${authToken}`);
              }

              xhr.upload.onprogress = (event) => {
                  if (!event.lengthComputable) return;
                  const percent = Math.round((event.loaded / event.total) * 100);
                  updatePendingFile(wrapper.id, { status: 'uploading', progress: percent });
              };

              xhr.upload.onload = () => {
                  updatePendingFile(wrapper.id, { status: 'processing', progress: 100 });
              };

              xhr.onload = () => {
                  let data = null;
                  try {
                      data = xhr.responseText ? JSON.parse(xhr.responseText) : null;
                  } catch {
                      data = null;
                  }
                  resolve({ status: xhr.status, data });
              };

              xhr.onerror = () => reject(new Error('Upload failed'));

              updatePendingFile(wrapper.id, { status: 'uploading', progress: 0 });
              xhr.send(formData);
          })
      );

      return (async () => {
          let token = localStorage.getItem(AUTH_TOKEN_KEY);
          let result = await sendOnce(token);

          if (result.status === 401) {
              const refreshedToken = await refreshAccessTokenFromApiClient();
              if (refreshedToken) {
                  token = refreshedToken;
                  result = await sendOnce(token);
              }
          }

          if (result.status >= 200 && result.status < 300) {
              const initialData = result.data || {};
              const taskId = initialData?.task_id;
              if (!taskId) {
                  return initialData;
              }

              updatePendingFile(wrapper.id, { status: 'processing', progress: 0 });
              return await pollDocumentUploadTaskWithAuthRetry(taskId, (task) => {
                  updatePendingFile(wrapper.id, {
                      status: task?.status === 'failed' ? 'error' : 'processing',
                      progress: Math.max(0, Math.min(100, Number(task?.progress) || 0)),
                      error: task?.status === 'failed' ? (task?.error_message || '') : ''
                  });
              });
          }

          const message = result?.data?.detail || result?.data?.error || `Upload failed with status ${result.status}`;
          throw new Error(message);
      })();
  };

  const pollDocumentUploadTaskWithAuthRetry = async (taskId, onProgress) => {
      const fetchOnce = async (authToken) => {
          const headers = authToken ? { Authorization: `Bearer ${authToken}` } : {};
          const response = await fetch(`${API_BASE_URL}/api/documents/upload/result/${taskId}`, {
              method: 'GET',
              headers
          });
          let data = null;
          try {
              data = await response.json();
          } catch {
              data = null;
          }
          return { response, data };
      };

      let token = localStorage.getItem(AUTH_TOKEN_KEY);
      const startedAt = Date.now();

      while (true) {
          let result = await fetchOnce(token);
          if (result.response.status === 401) {
              const refreshedToken = await refreshAccessTokenFromApiClient();
              if (refreshedToken) {
                  token = refreshedToken;
                  result = await fetchOnce(token);
              }
          }

          const data = result.data || {};
          if (!result.response.ok && data?.status !== 'failed') {
              const message = data?.detail || data?.error || `Task polling failed with status ${result.response.status}`;
              throw new Error(message);
          }

          onProgress?.(data);

          if (data?.status === 'completed' || data?.status === 'failed') {
              return data;
          }

          if (Date.now() - startedAt > 15 * 60 * 1000) {
              throw new Error('文档上传处理超时');
          }

          await new Promise((resolve) => setTimeout(resolve, 1500));
      }
  };

  const uploadDocumentWithAuthRetry = async (formData) => {
      const sendOnce = async (authToken) => {
          const headers = authToken ? { 'Authorization': `Bearer ${authToken}` } : {};
          const response = await fetch(`${API_BASE_URL}/api/documents/upload`, {
              method: 'POST',
              headers,
              body: formData
          });
          let data = null;
          try {
              data = await response.json();
          } catch {
              data = null;
          }
          return { response, data };
      };

      let token = localStorage.getItem(AUTH_TOKEN_KEY);
      let result = await sendOnce(token);

      if (result.response.status === 401) {
          const refreshedToken = await refreshAccessTokenFromApiClient();
          if (refreshedToken) {
              token = refreshedToken;
              result = await sendOnce(token);
          }
      }

      if (result.response.ok && result.data?.task_id) {
          const finalData = await pollDocumentUploadTaskWithAuthRetry(result.data.task_id);
          return {
              response: {
                  ok: finalData?.status === 'completed',
                  status: finalData?.status === 'failed' ? 500 : 200
              },
              data: finalData
          };
      }

      return result;
  };

  const parseUploadResult = (data) => {
      const okCount = Number(data?.ok ?? 0);
      const status = data?.result_status || data?.status;
      const isSuccess = (status === 'success' || status === 'partial') && okCount > 0;
      let error = data?.error || '';

      if (!error && Array.isArray(data?.errors) && data.errors.length > 0) {
          error = data.errors
              .map(item => item?.error || item?.file)
              .filter(Boolean)
              .join('; ');
      }

      if (!error && status === 'failed') {
          error = 'Upload failed';
      }

      return { isSuccess, error };
  };
  const uploadAndVectorizeFiles = async (wrappers) => {
      if (!wrappers.length) return;
      setIsUploadingFile(true);

      try {
          for (const wrapper of wrappers) {
              try {
                  const data = await uploadDocumentWithProgress(wrapper);
                  const { isSuccess, error } = parseUploadResult(data);
                  if (isSuccess) {
                      updatePendingFile(wrapper.id, {
                          status: 'done',
                          progress: 100,
                          uploaded: true,
                          previewText: data.previews || ''
                      });
                  } else {
                      updatePendingFile(wrapper.id, {
                          status: 'error',
                          uploaded: false,
                          error: error || 'Upload failed'
                      });
                  }
              } catch (error) {
                  console.error(`RAG Upload failed for ${wrapper.file.name}`, error);
                  updatePendingFile(wrapper.id, {
                      status: 'error',
                      uploaded: false,
                      error: error.message || 'Upload failed'
                  });
              }
          }
      } finally {
          setIsUploadingFile(false);
      }
  };

  const processFiles = async (filesToProcess) => {
      if (!filesToProcess || filesToProcess.length === 0) return { context: "", success: true };

      let combinedContext = "";
      let hasError = false;
      let ocrSessionId = null;
      let meetingAudioPath = null;

      setIsUploadingFile(true);

      try {
          for (const wrapper of filesToProcess) {
              const file = wrapper.file;

              if (isMeetingMode) {
                  if (!audioFileUrl) setAudioFileUrl(URL.createObjectURL(file));

                  const instantResult = await tryInstantTranscribe(file);
                  if (instantResult?.text) {
                      if (instantResult.filePath) {
                          setCurrentAudioPath(instantResult.filePath);
                          meetingAudioPath = instantResult.filePath;
                      }
                      combinedContext += `[音频文件: ${file.name}]\n${instantResult.text}\n\n`;
                      continue;
                  }

                  // ✨ [注意] 这里是文件上传，走 /api/voice/transcribe (异步文件转写)
                  const formData = new FormData();
                  formData.append('file', file);
                  formData.append('engine', normalizeOcrEngine(ocrEngine));
                  const token = localStorage.getItem(AUTH_TOKEN_KEY);
                  const voiceHeaders = token ? { Authorization: `Bearer ${token}` } : {};
                  const res = await fetch(`${API_BASE_URL}/api/voice/transcribe`, {
                      method: 'POST',
                      headers: voiceHeaders,
                      body: formData
                  });
                  const data = await res.json();

                  if (data.task_id) {
                      if (data.file_path) {
                          setCurrentAudioPath(data.file_path);
                          meetingAudioPath = data.file_path;
                      }

                      const poll = async (taskId) => {
                         for(let i=0; i<60; i++) {
                             await new Promise(r => setTimeout(r, 2000));
                             const r = await fetch(`${API_BASE_URL}/api/voice/result/${taskId}`);
                             const d = await r.json();
                             if (d.status === 'completed') return d.result;
                             if (d.status === 'failed') throw new Error(d.result);
                         }
                         throw new Error("转写超时");
                     };
                     const text = await poll(data.task_id);
                     combinedContext += `[音频文件: ${file.name}]\n${text}\n\n`;
                  } else {
                      alert(`文件 ${file.name} 上传失败: ${data.error}`);
                      hasError = true;
                  }
              }
              else if (isOCRMode || isAuditMode) {
                  const formData = new FormData();
                  formData.append('file', file);
                  if (isOCRMode) {
                      formData.append('engine', normalizeOcrEngine(ocrEngine));
                      updateOcrEntry(wrapper.id, { status: 'processing', error: '' });
                      if (!activeOcrId) setActiveOcrId(wrapper.id);
                  }
                  const token = localStorage.getItem(AUTH_TOKEN_KEY);
                  const headers = token ? { 'Authorization': `Bearer ${token}` } : {};

                  // 增加超时控制，防止超大图片导致前端由于等待太久而以为请求断开
                  const controller = new AbortController();
                  const timeoutId = setTimeout(() => controller.abort(), 120000); // 2分钟超时

                  try {
                      const res = await fetch(`${API_BASE_URL}/api/ocr/recognize`, {
                          method: 'POST',
                          headers,
                          body: formData,
                          signal: controller.signal
                      });
                      clearTimeout(timeoutId);

                      const data = await res.json();

                      // 🔴 [修复] 核心修复：放宽判断逻辑。
                      // 只要 data.text 存在，或者 data.data.text 存在，就视为成功。
                      // 即使后端没有返回 success: true 字段，只要有内容就不应该拦截。
                      // ⚠️ 修正：如果 text 是空字符串（纯公式/模糊），data.success 仍然可能是 true
                      const ocrText = data.text || (data.data && data.data.text) || data.result || '';
                      // ✨ 增加容错：移除不可见字符后再判断是否为空
                      const hasEffectiveContent = ocrText && ocrText.replace(/[\s\n\r\t]/g, '').length > 0;
                      const isExplicitFailure = data.success === false || data.status === 'failed';

                      if (!isExplicitFailure) {
                          if (hasEffectiveContent) {
                              combinedContext += `[文档/附件: ${file.name}]\n${ocrText}\n\n`;
                              if (isOCRMode) {
                                  const dataLines = data?.data?.lines || data?.lines || [];
                                  const dataPages = data?.data?.pages || data?.pages || [];
                                  const fileUrl = data?.data?.file_url || data?.file_url || '';
                                  const fileType = data?.data?.file_type || data?.file_type || file.type || '';
                                  const fileName = data?.data?.file_name || data?.file_name || file.name || '';
                                  const serverUrl = resolveFileUrl(fileUrl);
                                  updateOcrEntry(wrapper.id, {
                                      status: 'done',
                                      ocrText,
                                      ocrData: data,
                                      jsonText: JSON.stringify(data, null, 2),
                                      lines: dataLines,
                                      pages: dataPages,
                                      fileType,
                                      serverUrl
                                  });
                                  const savedSessionId = await saveOcrResultToHistory(ocrText, {
                                      text: ocrText,
                                      lines: dataLines,
                                      pages: dataPages,
                                      ocrData: data,
                                      file_url: fileUrl,
                                      file_type: fileType,
                                      file_name: fileName,
                                      file_size: file.size || 0
                                  }, ocrSessionId);
                                  if (savedSessionId) ocrSessionId = savedSessionId;
                              }
                          } else {
                              // 后端返回成功，但没有提取到文字（可能是纯公式或模糊图片）
                              console.warn(`OCR finished for ${file.name} but returned empty text. Raw response:`, data);
                              alert(`文件 ${file.name} 识别完成，但在图片中未发现可提取的文字（可能是纯公式、模糊或分辨率不足）。请尝试上传更清晰的图片。`);
                              if (isOCRMode) {
                                  const dataLines = data?.data?.lines || data?.lines || [];
                                  const dataPages = data?.data?.pages || data?.pages || [];
                                  const fileUrl = data?.data?.file_url || data?.file_url || '';
                                  const fileType = data?.data?.file_type || data?.file_type || file.type || '';
                                  const fileName = data?.data?.file_name || data?.file_name || file.name || '';
                                  const serverUrl = resolveFileUrl(fileUrl);
                                  updateOcrEntry(wrapper.id, {
                                      status: 'done',
                                      ocrText,
                                      ocrData: data,
                                      jsonText: JSON.stringify(data, null, 2),
                                      lines: dataLines,
                                      pages: dataPages,
                                      fileType,
                                      serverUrl
                                  });
                                  const savedSessionId = await saveOcrResultToHistory(ocrText, {
                                      text: ocrText,
                                      lines: dataLines,
                                      pages: dataPages,
                                      ocrData: data,
                                      file_url: fileUrl,
                                      file_type: fileType,
                                      file_name: fileName,
                                      file_size: file.size || 0
                                  }, ocrSessionId);
                                  if (savedSessionId) ocrSessionId = savedSessionId;
                              }
                              // 不设置 hasError，允许流程继续，只是没有内容
                          }
                      } else {
                          console.warn(`OCR result invalid for ${file.name}`, data);
                          // 如果有错误信息，尝试显示，否则显示通用错误
                          alert(`文件 ${file.name} 识别失败: ${data.error || '未知错误'}`);
                          if (isOCRMode) {
                              updateOcrEntry(wrapper.id, { status: 'error', error: data.error || '识别失败', ocrData: data });
                          }
                          hasError = true;
                      }
                  } catch (error) {
                      clearTimeout(timeoutId);
                      console.error(`OCR request failed for ${file.name}`, error);
                      alert(`文件 ${file.name} 识别请求失败: ${error.name === 'AbortError' ? '处理超时，图片可能过大' : error.message}`);
                      if (isOCRMode) {
                          updateOcrEntry(wrapper.id, { status: 'error', error: error.message || '识别失败' });
                      }
                      hasError = true;
                  }
              }
              else {
                  try {
                      const formData = new FormData();
                      formData.append('files', file);
                      if (userProfile?.id) {
                      formData.append('user_id', userProfile.id);
                      }

                      const { response, data } = await uploadDocumentWithAuthRetry(formData);
                      if (!response.ok) {
                          throw new Error(data?.detail || data?.error || `Upload failed with status ${response.status}`);
                      }
                      const { isSuccess, error } = parseUploadResult(data);

                      if (isSuccess) {
                          if (data.previews) {
                             combinedContext += `[新上传文档摘要]\n${data.previews}\n\n`;
                          }
                      } else {
                          console.error(`RAG Upload failed`, data);
                          alert(`文件 ${file.name} 上传失败: ${error || 'Upload failed'}`);
                          hasError = true;
                      }

                  } catch (e) {
                      console.error(`RAG Upload failed for ${file.name}`, e);
                      hasError = true;
                  }
              }
          }
      } catch (error) {
          console.error("Batch upload processing failed", error);
          hasError = true;
      } finally {
          setIsUploadingFile(false);
      }

      return { context: combinedContext, success: !hasError, sessionId: ocrSessionId, audioPath: meetingAudioPath };
  };

  const handleFileSelect = async (e) => {
    const files = Array.from(e.target.files);
    if (!files.length) return;

    if (isAuditMode) {
        await startAuditBatch(files);
        if (fileInputRef.current) fileInputRef.current.value = '';
        if (e.target && e.target.value) e.target.value = '';
        return;
    }

    const isAudioFile = (file) => file.type.startsWith('audio/') || file.type.startsWith('video/') || ['.wav', '.m4a', '.mp3'].some(ext => file.name.toLowerCase().endsWith(ext));
    const isImageFile = (file) => file.type.startsWith('image/');

    const newWrappers = files.map(file => ({
        file,
        id: Math.random().toString(36).substr(2, 9),
        previewUrl: (file.type.startsWith('image/') || file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf'))
          ? URL.createObjectURL(file)
          : null,
        status: 'queued',
        progress: 0,
        uploaded: false,
        previewText: ''
    }));

    const willSwitchToOcr = selectedModel === 0 && files.some(isImageFile) && !files.some(isAudioFile);
    if (isOCRMode || willSwitchToOcr) {
        const newEntries = newWrappers.map(buildOcrEntry);
        if (newEntries.length) {
            currentSessionIdRef.current = null;
            setCurrentSessionId(null);
            setPanelContent('');
            setSelectedOcrLine(null);
            setEditingOcrLine(null);
            setEditingOcrValue('');
            setOcrFiles(newEntries);
            setActiveOcrId(newEntries[0].id);
            setOcrPageIndex(0);
        }
    }

    if (selectedModel === 0) {
        const hasAudio = files.some(isAudioFile);
        const hasImage = files.some(isImageFile);

        if (hasAudio || hasImage) {
            if (hasAudio && hasImage) {
                alert("请分别上传音频或图片文件");
                return;
            }

            autoProcessFilesRef.current = newWrappers;
            autoProcessModeRef.current = hasAudio ? 'meeting' : 'ocr';
            handleModelChange(hasAudio ? 1 : 2);

            if (fileInputRef.current) fileInputRef.current.value = '';
            if (e.target && e.target.value) e.target.value = '';
            return;
        }
    }

    if (isMeetingMode) {
        const invalid = files.find(f => !f.type.startsWith('audio/') && !f.type.startsWith('video/') && !['.wav','.m4a','.mp3'].some(ext => f.name.endsWith(ext)));
        if (invalid) { alert("会议模式仅支持音频文件"); return; }
    } else if (isOCRMode) {
        const invalid = files.find(f => !['image/jpeg', 'image/png', 'image/bmp', 'application/pdf'].includes(f.type) && !f.name.toLowerCase().endsWith('.pdf'));
        if (invalid) { alert("OCR 模式仅支持图片或 PDF"); return; }
    }

    const shouldStartFreshMeetingSession = isMeetingMode && files.some(isAudioFile);
    const freshMeetingSessionId = shouldStartFreshMeetingSession ? createClientSessionId() : '';
    if (shouldStartFreshMeetingSession) {
        setChatHistory([]);
        setFeedbackState({});
        currentSessionIdRef.current = freshMeetingSessionId;
        resetHistoryPaginationState();
        clearHistoryExpandTask();
        setHistoryRenderTarget(INITIAL_MESSAGE_COUNT);
        setVisibleMessageCount(0);
        setExpandedSources({});
        setCurrentSessionId(freshMeetingSessionId);
        setPanelContent('');
        setAudioFileUrl(null);
        setCurrentAudioPath(null);
        setPendingFiles([]);
        setIsMobileSidebarOpen(false);
        setSpeakingIdx(null);
        window.speechSynthesis.cancel();
    }

    if (selectedModel === 0) {
        setPendingFiles(prev => [...prev, ...newWrappers]);
        await uploadAndVectorizeFiles(newWrappers);
    } else {
        // 清除输入值以允许重新选择同一文件
        if (fileInputRef.current) fileInputRef.current.value = '';
        if (e.target && e.target.value) e.target.value = '';

        const { context, sessionId, audioPath } = await processFiles(newWrappers);
        if (isOCRMode) {
            applyOcrContext(context, sessionId);
        } else {
            await applyFileContext(context, audioPath, {
                replaceExisting: shouldStartFreshMeetingSession,
                sessionIdOverride: freshMeetingSessionId,
            });
        }
    }
    // 清除输入
    if (fileInputRef.current) fileInputRef.current.value = '';
    if (e.target && e.target.value) e.target.value = '';
  };

  useEffect(() => {
    const resetDragState = () => {
      dragDepthRef.current = 0;
      setIsDragActive(false);
    };

    const onDragEnter = (event) => {
      if (!isFileDragEvent(event)) return;
      event.preventDefault();
      dragDepthRef.current += 1;
      setIsDragActive(true);
    };

    const onDragOver = (event) => {
      if (!isFileDragEvent(event)) return;
      event.preventDefault();
      if (event.dataTransfer) {
        event.dataTransfer.dropEffect = 'copy';
      }
      setIsDragActive(true);
    };

    const onDragLeave = (event) => {
      if (!isFileDragEvent(event)) return;
      event.preventDefault();
      dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
      if (dragDepthRef.current === 0) {
        setIsDragActive(false);
      }
    };

    const onDrop = (event) => {
      if (!isFileDragEvent(event)) return;
      event.preventDefault();
      resetDragState();
      processDroppedFiles(event.dataTransfer?.files);
    };

    const onVisibilityChange = () => {
      if (document.hidden) resetDragState();
    };

    window.addEventListener('dragenter', onDragEnter);
    window.addEventListener('dragover', onDragOver);
    window.addEventListener('dragleave', onDragLeave);
    window.addEventListener('drop', onDrop);
    window.addEventListener('dragend', resetDragState);
    window.addEventListener('blur', resetDragState);
    document.addEventListener('visibilitychange', onVisibilityChange);

    return () => {
      window.removeEventListener('dragenter', onDragEnter);
      window.removeEventListener('dragover', onDragOver);
      window.removeEventListener('dragleave', onDragLeave);
      window.removeEventListener('drop', onDrop);
      window.removeEventListener('dragend', resetDragState);
      window.removeEventListener('blur', resetDragState);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, []);

  const removePendingFile = (id) => {
      setPendingFiles(prev => prev.filter(f => f.id !== id));
  };

  const restoreCancelledDraft = (requestState) => {
      if (!requestState?.restoreOnCancel) return;
      setInputValue(requestState.text || '');
      setPendingFiles(Array.isArray(requestState.files) ? requestState.files : []);
      if (typeof window !== 'undefined') {
          window.requestAnimationFrame(() => {
              const input = messageInputRef.current;
              if (!input) return;
              input.focus();
              const cursor = String(requestState.text || '').length;
              input.setSelectionRange(cursor, cursor);
          });
      }
  };

  // ✨ 新增：停止生成功能
  const handleStopGeneration = () => {
      const activeRequest = activeChatRequestRef.current;
      if (activeRequest) {
          activeRequest.cancelled = true;
          activeChatRequestRef.current = null;
          setChatHistory((prev) => prev.slice(0, Math.max(0, activeRequest.historyLengthBeforeSend || 0)));
          restoreCancelledDraft(activeRequest);
      }
      if (abortControllerRef.current) {
          abortControllerRef.current.abort();
          abortControllerRef.current = null;
      }
      stopSmoothStream(); // 停止动画并清空当前流
      setStreamingAssistantText('');
      streamBufferRef.current = '';
      streamDisplayRef.current = "";
      setIsProcessing(false);
  };

  const handleSendMessage = async (textOverride = null, isHidden = false, options = {}) => {
    const effectiveBackend = options?.modelBackend || llmBackend;
    const textToSend = textOverride || inputValue;
    const hasPendingUpload = pendingFiles.some(pf => pf.status && pf.status !== 'done');
    if ((!textToSend.trim() && pendingFiles.length === 0) || isProcessing || isUploadingFile || hasPendingUpload) return;

    if (isMobileViewport && showMobileWorkspaceTabs) {
      setMobileWorkspaceTab('chat');
    }

    const filesToDisplay = [...pendingFiles];
    const attachedFileNames = Array.from(
      new Set(
        filesToDisplay
          .map((item) => item?.file?.name)
          .filter((name) => typeof name === 'string' && name.trim().length > 0)
      )
    );
    const filesToProcess = pendingFiles.filter(pf => !pf.uploaded);
    const uploadedContext = pendingFiles
        .filter(pf => pf.uploaded && pf.previewText)
        .map(pf => pf.previewText)
        .join('\n\n');
    const requestId = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const requestState = {
        id: requestId,
        cancelled: false,
        historyLengthBeforeSend: chatHistory.length,
        restoreOnCancel: !isHidden,
        text: textToSend,
        files: filesToDisplay,
        userClientMessageId: isHidden ? null : `user-${requestId}`,
        assistantClientMessageId: `assistant-${requestId}`,
    };
    activeChatRequestRef.current = requestState;

    if (!textOverride) {
        setInputValue('');
        setPendingFiles([]);
    }

    if (!isHidden) {
        let displayContent = textToSend;
        if (filesToDisplay.length > 0) {
            const fileNames = filesToDisplay.map(f => `[📎 ${f.file.name}]`).join(' ');
            displayContent = `${fileNames}\n${displayContent}`;
        }

        const userMessage = {
            role: 'user',
            content: displayContent,
            clientMessageId: requestState.userClientMessageId,
            session_id: currentSessionId || null,
        };
        setChatHistory(prev => [...prev, userMessage]);
        if (isReportMode) setReportStep('chat');
    }

    setIsProcessing(true);
    setChatHistory(prev => [...prev, {
      role: 'assistant',
      content: '',
      sources: [],
      clientMessageId: requestState.assistantClientMessageId,
      session_id: currentSessionId || null,
      func_type: currentMode,
    }]);
    setVisibleMessageCount((prev) => {
      const addedCount = isHidden ? 1 : 2;
      const targetCount = Math.min(historyRenderTarget, chatHistory.length + addedCount);
      return Math.max(prev, targetCount);
    });
    // 立即滚动到底部
    queueScrollToBottom("auto");

    // ✨✨✨ 重置流媒体状态 ✨✨✨
    setStreamingAssistantText('');
    streamBufferRef.current = '';
    streamDisplayRef.current = "";

    // 启动动画循环
    startSmoothStream();

    // ✨ 创建新的 AbortController
    const controller = new AbortController();
    abortControllerRef.current = controller;
    let shouldPostProcessReply = false;

    // ✨ 关键修复：定义外部累加变量，避免闭包陷阱
    // let currentText = ""; // 移除：使用 streamBufferRef 代替

    try {
         const { context: fileContext, sessionId: ocrSessionId, audioPath: meetingAudioPath } = await processFiles(filesToProcess);
         if (requestState.cancelled) return;
         if (isOCRMode && ocrSessionId && ocrSessionId !== currentSessionId) {
             setCurrentSessionId(ocrSessionId);
         }
         if (isMeetingMode && meetingAudioPath && meetingAudioPath !== currentAudioPath) {
             setCurrentAudioPath(meetingAudioPath);
         }

         let activePanelContent = panelContent;
         if (fileContext) {
             if (isMeetingMode || isOCRMode || isAuditMode) {
                 const newContent = (panelContent ? panelContent + '\n\n' : '') + fileContext;
                 setPanelContent(newContent);
                 activePanelContent = newContent;
             } else {
                 if (!activePanelContent) {
                     activePanelContent = fileContext;
                 } else {
                     activePanelContent += `\n\n${fileContext}`;
                 }
             }

             const effectiveSessionId = currentSessionId || ocrSessionId;
             if (effectiveSessionId) {
                 let type = 'context_save';
                 if (isMeetingMode) type = 'voice_context';
                 if (isOCRMode) type = 'ocr_context';
                 if (isAuditMode) type = 'audit_context';
                 if (isMeetingMode || isAuditMode) {
                     savePanelContext(effectiveSessionId, activePanelContent, type);
                 }
                 if (isMeetingMode && (meetingAudioPath || currentAudioPath)) {
                     saveSessionMeta(effectiveSessionId, selectedModel, currentMode, meetingAudioPath || currentAudioPath, effectiveBackend);
                 }
             }
         }
         if (uploadedContext && !isMeetingMode && !isOCRMode && !isAuditMode) {
             if (!activePanelContent) {
                 activePanelContent = uploadedContext;
             } else {
                 activePanelContent += `\n\n${uploadedContext}`;
             }
         }

         const token = localStorage.getItem(AUTH_TOKEN_KEY);
         const headers = { 'Content-Type': 'application/json' };
         if (token) headers['Authorization'] = `Bearer ${token}`;

         let effectiveMode = isAuditMode ? 'audit' : currentMode;

         const shouldIsolateRagContext = effectiveMode === 'rag' && attachedFileNames.length > 0;
         const isolatedRagContext = [fileContext, uploadedContext].filter(Boolean).join('\n\n');
         const contextBase = shouldIsolateRagContext ? isolatedRagContext : activePanelContent;
         const contextToSend = contextBase ? contextBase.slice(0, MAX_CONTEXT_CHARS) : contextBase;

         const sessionIdToSend = currentSessionId || ocrSessionId;
         const payload = {
            message: textToSend || "请分析上传的文件",
            modelId: String(selectedModel),
            session_id: sessionIdToSend,
            user_id: userProfile.id,
            mode: effectiveMode,
            context_content: contextToSend,
            files: attachedFileNames,
            // ✨ 传递用户选择的后端 (local / cloud)
            model_backend: effectiveBackend,
            personalization: buildChatPersonalizationPayload(appSettings)
         };

         // ✨ 传递 signal 以支持取消
         const response = await fetch(`${API_BASE_URL}/api/chat`, {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(payload),
            signal: controller.signal
         });
         if (requestState.cancelled) return;

         if (!response.ok) throw new Error("API Error");
         if (!response.body) throw new Error("No response body");

         const reader = response.body.getReader();
         const decoder = new TextDecoder();
         let done = false;
         // let currentText = ""; // 移除内部定义，使用外部定义的 currentText
         let buffer = "";
         let sessionAssigned = false;
         const processMainStreamLine = (line) => {
            if (requestState.cancelled || !line || !line.trim()) return;
            try {
                const json = JSON.parse(line);
                if (json.t === 'c') {
                    const newChunk = typeof json.v === 'string' ? json.v : String(json.v || '');
                    streamBufferRef.current += newChunk;
                } else if (json.t === 'm') {
                    if (json.src) {
                         setChatHistory(prev => {
                             const newHistory = [...prev];
                             let assistantIndex = -1;
                             for (let i = newHistory.length - 1; i >= 0; i -= 1) {
                                 if (newHistory[i]?.clientMessageId === requestState.assistantClientMessageId) {
                                     assistantIndex = i;
                                     break;
                                 }
                             }
                             const targetIndex = assistantIndex >= 0 ? assistantIndex : newHistory.length - 1;
                             if (targetIndex >= 0) {
                                 newHistory[targetIndex] = { ...newHistory[targetIndex], sources: json.src };
                             }
                             return newHistory;
                         });
                    }
                    if (json.sid && !sessionAssigned) {
                        sessionAssigned = true;
                        currentSessionIdRef.current = json.sid;
                        setChatHistory(prev => prev.map((item) => {
                            if (!item) return item;
                            if (item.clientMessageId === requestState.assistantClientMessageId) {
                                return { ...item, session_id: json.sid };
                            }
                            if (requestState.userClientMessageId && item.clientMessageId === requestState.userClientMessageId) {
                                return { ...item, session_id: json.sid };
                            }
                            return item;
                        }));
                        if (!currentSessionId) {
                            setCurrentSessionId(json.sid);
                            saveSessionMeta(json.sid, selectedModel, effectiveMode, currentAudioPath, effectiveBackend);
                            if (activePanelContent && activePanelContent.trim()) {
                                let type = 'context_save';
                                if (isMeetingMode) type = 'voice_context';
                                if (isOCRMode) type = 'ocr_context';
                                if (isAuditMode) type = 'audit_context';
                                savePanelContext(json.sid, activePanelContent, type);
                            }
                        }
                    }
                    if (json.history_ids) {
                        setChatHistory(prev => {
                            const next = [...prev];
                            const assistantHistoryId = json.history_ids?.assistant;
                            const userHistoryId = json.history_ids?.user;
                            let assistantIndex = -1;
                            for (let i = next.length - 1; i >= 0; i -= 1) {
                                if (next[i]?.clientMessageId === requestState.assistantClientMessageId) {
                                    assistantIndex = i;
                                    break;
                                }
                            }
                            if (assistantIndex >= 0 && assistantHistoryId) {
                                next[assistantIndex] = {
                                    ...next[assistantIndex],
                                    id: assistantHistoryId,
                                    messageKey: `h:${assistantHistoryId}`,
                                };
                            }
                            if (requestState.userClientMessageId && userHistoryId) {
                                let userIndex = -1;
                                for (let i = next.length - 1; i >= 0; i -= 1) {
                                    if (next[i]?.clientMessageId === requestState.userClientMessageId) {
                                        userIndex = i;
                                        break;
                                    }
                                }
                                if (userIndex >= 0) {
                                    next[userIndex] = {
                                        ...next[userIndex],
                                        id: userHistoryId,
                                        messageKey: `h:${userHistoryId}`,
                                    };
                                }
                            }
                            return next;
                        });
                    }
                    if (json.end) {
                        shouldPostProcessReply = true;
                        const uid = userProfile.id || 'anonymous';
                        if (uid && uid !== 'anonymous') {
                            void refreshSessionList(uid);
                        }
                    }
                }
            } catch {
                // Ignore malformed stream chunks and continue parsing subsequent lines.
            }
         };

         while (!done && !requestState.cancelled) {
            const { value, done: doneReading } = await reader.read();
            done = doneReading;
            const chunkValue = decoder.decode(value, { stream: true });
            buffer += chunkValue;
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                processMainStreamLine(line);
            }
         }
         if (requestState.cancelled) return;

         // 处理 decoder/缓冲区尾包，避免最后一段无换行时被丢弃
         const tailChunk = decoder.decode();
         if (tailChunk) buffer += tailChunk;
         if (buffer && buffer.trim()) {
             const tailLines = buffer.split('\n').filter((line) => line && line.trim());
             tailLines.forEach(processMainStreamLine);
         }
    } catch (e) {
      if (requestState.cancelled || e.name === 'AbortError') {
          console.log('Generation stopped by user');
      } else {
          // 出错时重置动画状态
          setStreamingAssistantText('');
          console.error(e);
          setChatHistory(prev => {
              const newHistory = [...prev];
              newHistory[newHistory.length - 1] = { role: 'assistant', content: '抱歉，服务暂时不可用或网络中断。' };
              return newHistory;
          });
      }
    } finally {
      if (!requestState.cancelled) {
        // ✨ 停止动画
        stopSmoothStream();

        // ⚠️ 关键修复：确保状态更新的顺序，避免闪烁和“变回加载动画”

        // 修复开始：在清除引用之前捕获本地值
        const finalContent = streamDisplayRef.current;
        const resolvedFinalContent =
          (!finalContent || !finalContent.trim()) && shouldPostProcessReply
            ? '未收到模型返回内容，请重试；如在知识库模式，建议减少上下文长度或切换云端模型。'
            : finalContent;
        // 固定结束

        // 1. 先同步更新历史记录 - 保证 UI 有内容可读
        setChatHistory(prev => {
          if (!prev.length) return prev;
          const lastIndex = prev.length - 1;
          // 如果已经是这个内容了，直接返回
          if (prev[lastIndex].content === resolvedFinalContent) return prev; // Use local variable
          const next = [...prev];
          next[lastIndex] = { ...next[lastIndex], content: resolvedFinalContent }; // Use local variable
          return next;
        });

        // 2. 关闭处理状态
        setIsProcessing(false);

        // 3. 最后清除流式缓冲
        setStreamingAssistantText('');
        streamBufferRef.current = '';
        streamDisplayRef.current = "";

        if (shouldPostProcessReply && resolvedFinalContent && resolvedFinalContent.trim()) {
          if (
            appSettings.desktopNotifications &&
            typeof window !== 'undefined' &&
            'Notification' in window &&
            Notification.permission === 'granted' &&
            document.hidden
          ) {
            try {
              new Notification('助手回复完成', {
                body: resolvedFinalContent.slice(0, 120),
              });
            } catch {
              // 忽略
            }
          }
          if (appSettings.autoReadReplies) {
            setSpeakingIdx(null);
            speakTextWithSettings(finalContent);
          }
        }
      }

      if (activeChatRequestRef.current?.id === requestState.id) {
        activeChatRequestRef.current = null;
        abortControllerRef.current = null;
      }
    }
  };

  const handleSuggestionClick = (text) => {
    handleSendMessage(text);
  };

  // ✨ [修改] 语音录制确认逻辑：改为走实时接口
  const handleVoiceConfirm = async (wavBlob) => {
    setIsRecordingMode(false);
    setIsProcessing(true);
    try {
      if (isMeetingMode && wavBlob) {
        setAudioFileUrl(URL.createObjectURL(wavBlob));
      }

      // 🔴 旧逻辑：调用 voiceApi.transcribe (默认指向文件转写)
      // const 结果 = 等待 voiceApi.transcribe(wavBlob);

      // 🟢 新逻辑：调用 /api/voice/instant (实时转写)
      const formData = new FormData();
      formData.append('file', wavBlob, 'recording.wav');
      const token = localStorage.getItem(AUTH_TOKEN_KEY);
      const voiceHeaders = token ? { Authorization: `Bearer ${token}` } : {};

      const res = await fetch(`${API_BASE_URL}/api/voice/instant`, {
          method: 'POST',
          headers: voiceHeaders,
          body: formData
      });
      const result = await res.json();
      const recognizedText = typeof result?.text === 'string' ? result.text.trim() : '';
      const isLegacyFailText = recognizedText.startsWith('❌') || recognizedText.startsWith('[ERROR]');

      if (!res.ok || result?.success === false || isLegacyFailText) {
          const msg = result?.error || (isLegacyFailText ? recognizedText : `语音识别失败（${result?.error_code ?? 'unknown'}）`);
          alert(msg);
          return;
      }

      if (result.file_path && isMeetingMode) {
          setCurrentAudioPath(result.file_path);
          if (currentSessionId) {
              saveSessionMeta(currentSessionId, selectedModel, currentMode, result.file_path, llmBackend);
          }
      }

      if (recognizedText) {
          let newText = "";
          if (isMeetingMode || isAuditMode) {
              const prevContent = panelContent;
              newText = prevContent + (prevContent ? '\n' : '') + recognizedText;
              setPanelContent(newText);
              const type = isAuditMode ? 'audit_context' : 'voice_context';
              if (currentSessionId) savePanelContext(currentSessionId, newText, type);
          } else {
              setInputValue(prev => prev + (prev ? '\n' : '') + recognizedText);
          }
      } else {
          alert(result.error || '未能识别出语音内容');
      }
    } catch (e) {
        console.error('语音识别请求失败', e);
        alert('语音识别失败，请检查网络');
    } finally {
        setIsProcessing(false);
    }
  };

  const handleExportWord = () => {
    if (!panelContent.trim()) { alert("暂无内容可导出"); return; }
    const header = "<html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word' xmlns='http://www.w3.org/TR/REC-html40'><head><meta charset='utf-8'><title>Export</title></head><body>";
    const footer = "</body></html>";
    const contentHtml = panelContent.replace(/\n/g, "<br>");
    const sourceHTML = header + contentHtml + footer;
    const source = 'data:application/vnd.ms-word;charset=utf-8,' + encodeURIComponent(sourceHTML);
    const fileDownload = document.createElement("a");
    document.body.appendChild(fileDownload);
    fileDownload.href = source;
    fileDownload.download = `export_${new Date().toISOString().slice(0,10)}.doc`;
    fileDownload.click();
    document.body.removeChild(fileDownload);
  };

  const handleGenerateSummary = () => {
      if (isAuditMode) return;
      if (!panelContent.trim()) return;
      const prompt = isOCRMode ? `分析整理文档内容，提取关键信息：\n\n${panelContent}` : panelContent;
      handleSendMessage(prompt, true);
  };

  const handleOcrStore = async () => {
      if (!isOCRMode) return;
      if (!panelContent.trim()) return;
      setOcrIngestModal({ isOpen: true, content: panelContent });
  };

  const handleOcrStoreFromActive = () => {
      if (!isOCRMode) return;
      const source = activeOcrFile?.ocrText || getOcrLines(activeOcrFile).map((line) => line.text).join('\n');
      const content = (source || '').trim();
      if (!content) {
          alert('暂无可录入的识别内容');
          return;
      }
      setOcrIngestModal({ isOpen: true, content });
  };

  const resetAuditStateStable = useStableCallback(resetAuditState);
  const buildOcrEntryStable = useStableCallback(buildOcrEntry);
  const applyOcrContextStable = useStableCallback(applyOcrContext);
  const applyFileContextStable = useStableCallback(applyFileContext);
  const processFilesStable = useStableCallback(processFiles);
  const handleFileSelectStable = useStableCallback(handleFileSelect);
  const handleAuditFileSelectStable = useStableCallback(handleAuditFileSelect);
  const handleAuditErpActionStable = useStableCallback(handleAuditErpAction);
  const handleMeetingUploadClickStable = useStableCallback(handleMeetingUploadClick);
  const handleManualSaveStable = useStableCallback(handleManualSave);
  const handleExportWordStable = useStableCallback(handleExportWord);
  const handleGenerateSummaryStable = useStableCallback(handleGenerateSummary);
  const handleOcrStoreStable = useStableCallback(handleOcrStore);

  useEffect(() => {
      const pending = autoProcessFilesRef.current;
      const mode = autoProcessModeRef.current;
      if (!pending || !mode) return;

      if ((mode === 'meeting' && selectedModel !== 1) || (mode === 'ocr' && selectedModel !== 2)) return;

      autoProcessFilesRef.current = null;
      autoProcessModeRef.current = null;

      const run = async () => {
          if (mode === 'ocr') {
              const entries = pending.map(buildOcrEntryStable);
              if (entries.length) {
                  currentSessionIdRef.current = null;
                  setCurrentSessionId(null);
                  setPanelContent('');
                  setSelectedOcrLine(null);
                  setEditingOcrLine(null);
                  setEditingOcrValue('');
                  setOcrFiles(entries);
                  setActiveOcrId(entries[0].id);
                  setOcrPageIndex(0);
              }
          }
          const { context, sessionId, audioPath } = await processFilesStable(pending);
          if (mode === 'ocr') {
              applyOcrContextStable(context, sessionId);
          } else {
              await applyFileContextStable(context, audioPath);
          }
      };
      run();
  }, [applyFileContextStable, applyOcrContextStable, buildOcrEntryStable, processFilesStable, selectedModel]);

  useEffect(() => {
    handleFileSelectRef.current = handleFileSelectStable;
  }, [handleFileSelectStable]);

  const handleSubmitReportForm = () => {
      const listOrNone = (items) => (Array.isArray(items) && items.length ? items.join('、') : '无');
      let prompt = "";
      const chosenBackend = reportFormData.modelBackend || llmBackend;
      if (reportType === 'report') {
          const minWords = Math.max(100, Number(reportFormData.minWords) || 200);
          prompt = `[指令:创意内容生成]\n项目背景：${WRITING_PROJECT_CONTEXT}\n我要写一个：${reportFormData.contentType || WRITING_CONTENT_TYPE_OPTIONS[0]}\n发布平台：${reportFormData.platform || WRITING_PLATFORM_OPTIONS[0]}\n目标人群：${listOrNone(reportFormData.targetAudiences)}\n语气风格：${reportFormData.tone || WRITING_TONE_OPTIONS[0]}\n字数不少于：${minWords}\n参考内容：${reportFormData.referenceContent || '无'}\n包含关键词：${reportFormData.keywords || '无'}\n是否允许适量emoji：${reportFormData.withEmoji ? '是' : '否'}\n请输出以下内容（使用中文，Markdown结构清晰）：\n1) 标题候选 3 个\n2) 正文 1 篇（至少 ${minWords} 字）\n3) 末尾行动引导（CTA）\n4) 适合该平台的标签/话题建议\n要求：必须结合“进出口企业办公协同”与本项目能力，不要写成泛泛的互联网文案。`;
      } else if (reportType === 'ppt') {
          const minWords = Math.max(200, Number(reportFormData.analysisMinWords) || 350);
          const pptFocusConfig = getStandalonePptContentFocusConfig(reportFormData.contentFocus || STANDALONE_PPT_DEFAULT_CONTENT_FOCUS);
          prompt = [
              `[指令:PPT内容策划]`,
              `项目背景：${WRITING_PROJECT_CONTEXT}`,
              `内容导向：${pptFocusConfig.label}`,
              `字数不少于：${minWords}`,
              `输入信息：${reportFormData.analysisInput || '无'}`,
              `是否要求丰富数据指标：${reportFormData.requireMetrics ? '是' : '否'}`,
              ...pptFocusConfig.promptLines,
              "请输出一份适合直接制作成 PPT 的中文内容方案（Markdown）：",
              "1) 演示标题与副标题",
              "2) 适合开场页呈现的 3 条核心结论",
              "3) 推荐目录（6-8 个章节）",
              "4) 每个章节建议的页标题与 3-5 条页面要点",
              "5) 建议补充的数据、案例或图表表达",
              "6) 结尾页的行动建议、决策诉求或总结收束",
              pptFocusConfig.emphasizeMetrics
                  ? "要求：尽量补充效率、成本、时效、准确率、转化率、ROI 等可验证指标，避免只有观点没有支撑。"
                  : "要求：尽量补充步骤、案例、注意事项和实操建议，确保内容适合讲解和培训场景。",
              "表达要求：标题更像结论，正文更像提纲，适合直接转成页级演示内容，不要写成传统长篇报告。",
          ].join('\n');
      } else if (reportType === 'email') {
          const minWords = Math.max(200, Number(reportFormData.consultingMinWords) || 300);
          prompt = `[指令:建议咨询]\n项目背景：${WRITING_PROJECT_CONTEXT}\n咨询类型：${reportFormData.consultingType || WRITING_CONSULTING_TYPE_OPTIONS[0]}\n面向对象：${reportFormData.consultingRole || WRITING_CONSULTING_ROLE_OPTIONS[0]}\n输出形式偏好：${reportFormData.outputFormat || WRITING_OUTPUT_FORMAT_OPTIONS[0]}\n字数不少于：${minWords}\n业务背景：${reportFormData.consultingContext || '无'}\n约束条件：${reportFormData.consultingConstraints || '无'}\n是否需要分阶段时间表：${reportFormData.includeTimeline ? '是' : '否'}\n请给出一份可执行建议方案（Markdown）：\n1) 问题定义\n2) 方案建议（含优先级）\n3) 风险与应对\n4) 关键指标/KPI\n5) 执行步骤与负责人建议\n${reportFormData.includeTimeline ? '6) 分阶段时间表（周/月）' : ''}\n要求：建议必须贴合进出口企业场景，不要空泛。`;
      }
      if (!prompt.trim()) return;
      handleSendMessage(prompt, false, { modelBackend: chosenBackend });
  };

  const resolveStandalonePptInput = () => {
      const inputMode = standalonePptForm.inputMode || STANDALONE_PPT_INPUT_MODES[0].key;
      const rawSlides = Number(standalonePptForm.pptSlideCount);
      const slideCount = Math.max(3, Math.min(40, rawSlides || 8));
      const focusConfig = getStandalonePptContentFocusConfig(standalonePptForm.contentFocus || STANDALONE_PPT_DEFAULT_CONTENT_FOCUS);
      const typedInput = String(standalonePptForm.analysisInput || '').trim();
      const documentName = String(standalonePptForm.documentName || '').trim();

      if (inputMode === "topic") {
          if (!typedInput) return { error: "请先输入 PPT 主题。" };
          return { inputMode, slideCount, contentFocus: focusConfig.key, analysisInput: typedInput, documentName, typedInput };
      }

      if (inputMode === "document") {
          if (!documentName && !typedInput) return { error: "请先上传 Word/PDF 文档，或补充文档说明。" };
          const docInputs = [];
          if (documentName) docInputs.push(`参考文档：${documentName}`);
          if (typedInput) docInputs.push(`文档补充说明：${typedInput}`);
          docInputs.push("请优先根据文档内容组织目录与正文，缺失信息请合理补齐。");
          return {
              inputMode,
              slideCount,
              contentFocus: focusConfig.key,
              analysisInput: docInputs.join('\n'),
              documentName,
              typedInput,
          };
      }

      if (!typedInput) return { error: "请先粘贴需要转换的大段文本内容。" };
      return {
          inputMode,
          slideCount,
          contentFocus: focusConfig.key,
          analysisInput: typedInput,
          documentName,
          typedInput,
      };
  };

  const normalizeOutline = (outlinePayload, fallbackTitle = "业务汇报") => {
      const slides = Array.isArray(outlinePayload?.slides) ? outlinePayload.slides : [];
      const deckTitle = String(outlinePayload?.title || fallbackTitle || "业务汇报").trim();
      const focusConfig = getStandalonePptContentFocusConfig(
          outlinePayload?.contentFocus || STANDALONE_PPT_DEFAULT_CONTENT_FOCUS,
      );
      const normalizedSlides = slides.map((slide, idx) => {
          const title = String(slide?.title || `第 ${idx + 1} 页`).trim();
          const pointsRaw = Array.isArray(slide?.points) ? slide.points : [];
          const points = pointsRaw.map((item) => String(item || '').trim()).filter(Boolean);
          const fallbackPoints = [
              `说明“${title}”与“${deckTitle}”的关系和本页核心结论。`,
              "补充关键事实、现状、案例或数据依据。",
              "拆解主要影响因素、分析逻辑或结构要点。",
              "给出对应建议、行动方向或预期结果。",
          ];
          const mergedPoints = [...points];
          fallbackPoints.forEach((item) => {
              if (mergedPoints.length < 4 && !mergedPoints.includes(item)) {
                  mergedPoints.push(item);
              }
          });
          return {
              index: idx + 1,
              title,
              points: mergedPoints.length ? mergedPoints.slice(0, 10) : fallbackPoints,
              notes: String(slide?.notes || '').trim() || `围绕“${title}”补充定义、案例、数据指标或图表建议，避免内容过于简略。`,
          };
      }).filter((slide) => slide.title);
      return {
          title: deckTitle,
          subtitle: sanitizeStandaloneOutlineSubtitle(
              outlinePayload?.subtitle || "",
              focusConfig?.label || "",
          ),
          slides: normalizedSlides,
      };
  };

  const buildStandaloneOutlineFromLongText = (resolved) => {
      const rawText = String(resolved?.analysisInput || "").trim();
      const focusConfig = getStandalonePptContentFocusConfig(resolved?.contentFocus || STANDALONE_PPT_DEFAULT_CONTENT_FOCUS);
      const targetSlideCount = Math.max(3, Math.min(40, Number(resolved?.slideCount) || 8));
      const previewSections = Array.isArray(focusConfig?.previewSections) && focusConfig.previewSections.length
          ? focusConfig.previewSections
          : PPT_OUTLINE_PREVIEW_SECTIONS;
      const fallbackTitle = pickOutlinePreviewTopic(rawText, focusConfig.label || "业务汇报");
      const rawBlocks = rawText
          .split(/\n\s*\n+/)
          .map((block) => String(block || "").trim())
          .filter(Boolean);

      let slideDrafts = rawBlocks
          .map((block, idx) => {
              const rawLines = String(block || "")
                  .split(/\r?\n/)
                  .map((line) => normalizeStandaloneOutlineTextLine(line))
                  .filter(Boolean);
              if (!rawLines.length) return null;
              const firstLine = rawLines[0];
              const hasStructuredLines = rawLines.length > 1 || String(block || "").trim().startsWith("#");
              const title = hasStructuredLines && firstLine.length <= 32
                  ? firstLine
                  : (previewSections[idx] || `第 ${idx + 1} 页`);
              const detailSource = hasStructuredLines ? rawLines.slice(1).join("\n") : rawLines.join("\n");
              const points = splitStandaloneOutlinePointCandidates(detailSource).filter((item) => item !== title);
              return {
                  title,
                  points: points.slice(0, 6),
                  notes: rawLines.join("；").slice(0, 180),
              };
          })
          .filter(Boolean)
          .slice(0, targetSlideCount);

      if (slideDrafts.length < 3) {
          const pointCandidates = splitStandaloneOutlinePointCandidates(rawText);
          const effectiveCount = Math.max(3, Math.min(targetSlideCount, Math.max(3, Math.ceil(pointCandidates.length / 3) || 3)));
          const chunkSize = Math.max(2, Math.ceil(Math.max(pointCandidates.length, effectiveCount * 2) / effectiveCount));
          slideDrafts = Array.from({ length: effectiveCount }, (_, idx) => {
              const chunk = pointCandidates.slice(idx * chunkSize, (idx + 1) * chunkSize).filter(Boolean);
              return {
                  title: previewSections[idx] || `第 ${idx + 1} 页`,
                  points: chunk.slice(0, 6),
                  notes: chunk.join("；").slice(0, 180),
              };
          });
      }

      const normalizedOutline = normalizeOutline(
          {
              title: fallbackTitle,
              subtitle: `${focusConfig.label} · 文本整理`,
              slides: slideDrafts,
          },
          fallbackTitle,
      );
      const nextSlides = Array.isArray(normalizedOutline.slides) ? [...normalizedOutline.slides] : [];
      while (nextSlides.length < 3) {
          const nextIndex = nextSlides.length;
          const title = previewSections[nextIndex] || `第 ${nextIndex + 1} 页`;
          nextSlides.push({
              index: nextIndex + 1,
              title,
              points: [
                  `围绕“${fallbackTitle}”补充“${title}”的核心内容。`,
                  "补充关键观点、事实依据或案例支撑。",
                  "提炼适合直接展示在 PPT 页面中的重点信息。",
                  "保留必要的结论、提示或后续动作。",
              ],
              notes: `从原始长文本中提炼“${title}”相关内容，保持表达紧凑清晰。`,
          });
      }
      return {
          ...normalizedOutline,
          slides: nextSlides.map((slide, idx) => ({ ...slide, index: idx + 1 })),
          sourceContext: rawText,
          inputMode: String(resolved?.inputMode || "longText").trim() || "longText",
          documentName: String(resolved?.documentName || "").trim(),
          contentFocus: focusConfig.key,
      };
  };

  const shouldRefreshStandaloneOutlineForResolvedInput = (resolved) => {
      if (!standalonePptOutline?.slides?.length) return true;
      return (
          String(standalonePptOutline?.sourceContext || "").trim() !== String(resolved?.analysisInput || "").trim()
          || String(standalonePptOutline?.inputMode || "").trim() !== String(resolved?.inputMode || "").trim()
          || String(standalonePptOutline?.documentName || "").trim() !== String(resolved?.documentName || "").trim()
          || String(standalonePptOutline?.contentFocus || "").trim() !== String(resolved?.contentFocus || "").trim()
      );
  };

  const inferStandaloneOutlineSlideRole = (slide, slideIndex, allSlides, focusConfig) => {
      const title = String(slide?.title || "").trim();
      const totalSlides = Array.isArray(allSlides) ? allSlides.length : 0;
      if (slideIndex === 0 && /封面|标题/.test(title)) return "cover";
      if (STANDALONE_PPT_AGENDA_TITLE_RE.test(title)) return "agenda";
      if (STANDALONE_PPT_SUMMARY_TITLE_RE.test(title)) return "summary";
      if (STANDALONE_PPT_BACKGROUND_TITLE_RE.test(title)) return "background";
      if (STANDALONE_PPT_ISSUE_TITLE_RE.test(title)) return "issue";
      if (STANDALONE_PPT_ACTION_TITLE_RE.test(title)) return "action";
      if (STANDALONE_PPT_TRAINING_TITLE_RE.test(title) || !focusConfig?.emphasizeMetrics) return "training";
      if (slideIndex === totalSlides - 1 && totalSlides > 1) return "closing";
      return "evidence";
  };

  const buildDenseSlidesMarkdownFromOutline = (outlinePayload) => {
      const slides = Array.isArray(outlinePayload?.slides) ? outlinePayload.slides : [];
      const deckTitle = String(outlinePayload?.title || "业务汇报").trim() || "业务汇报";
      const focusConfig = getStandalonePptContentFocusConfig(
          outlinePayload?.contentFocus || STANDALONE_PPT_DEFAULT_CONTENT_FOCUS,
      );
      const sourceContextHints = compactStandaloneSourceContext(outlinePayload?.sourceContext || "", 8);

      return slides.map((slide, idx) => {
          const title = String(slide?.title || `第 ${idx + 1} 页`).trim();
          const points = Array.isArray(slide?.points) ? slide.points.map((item) => String(item || '').trim()).filter(Boolean) : [];
          const notes = String(slide?.notes || "").trim();
          const slideRole = inferStandaloneOutlineSlideRole(slide, idx, slides, focusConfig);
          const sourceHints = sourceContextHints
              .filter((item) => item.includes(title.slice(0, 6)) || item.includes(deckTitle.slice(0, 6)))
              .slice(0, 3);
          const fallbackSourceHints = sourceHints.length ? sourceHints : sourceContextHints.slice(idx, idx + 2);
          const expandedPoints = points.length ? points : [
              `先点明“${title}”这一页最重要的判断或结论。`,
              "补充关键事实、现状、案例或数据依据。",
              "拆解主要影响因素、分析逻辑或结构要点。",
              "给出对应建议、行动方向或预期结果。",
          ];

          const agendaPoints = slides
              .map((item, slideIdx) => (slideIdx === idx ? "" : String(item?.title || "").trim()))
              .filter(Boolean)
              .filter((item) => !STANDALONE_PPT_AGENDA_TITLE_RE.test(item))
              .slice(0, 5);

            const bulletCandidates = slideRole === "agenda" && agendaPoints.length
                ? agendaPoints.map((item, orderIdx) => `第 ${orderIdx + 1} 部分：${item}`)
                : expandedPoints.slice();
            const shouldBackfillContext = points.length < 2 && slideRole !== "cover" && slideRole !== "agenda";

            if (shouldBackfillContext && notes && bulletCandidates.length < 6) {
                bulletCandidates.push(notes);
            }
            if (shouldBackfillContext) {
                fallbackSourceHints.forEach((item) => {
                    if (bulletCandidates.length >= 6) return;
                    bulletCandidates.push(item);
                });
            }

          const normalizedBullets = Array.from(new Set(
              bulletCandidates
                  .map((item) => String(item || '')
                      .replace(/^(?:页面角色|内容导向|讲解备注|可参考素材|展开要求|Language|语言)\s*[:：]\s*/i, '')
                      .replace(STANDALONE_PPT_LANGUAGE_LEAK_RE, '')
                      .replace(/\s+/g, ' ')
                      .trim())
                  .filter(Boolean),
          )).filter((item) => item !== title).slice(0, slideRole === "cover" ? 3 : 6);

          return [
              `# ${title}`,
              normalizedBullets.map((item) => `- ${item}`).join('\n'),
          ].filter(Boolean).join('\n\n');
      });
  };

  const buildStandaloneOutlineRevisionSuggestions = (slide, slideIndex, allSlides, focusConfig) => {
      const title = String(slide?.title || "").trim();
      const points = Array.isArray(slide?.points) ? slide.points.map((item) => String(item || "").trim()).filter(Boolean) : [];
      const notes = String(slide?.notes || "").trim();
      const combinedText = [title, ...points, notes].join(" ");
      const role = inferStandaloneOutlineSlideRole(slide, slideIndex, allSlides, focusConfig);
      const hasMetrics = STANDALONE_PPT_METRIC_HINT_RE.test(combinedText);
      const hasEvidence = STANDALONE_PPT_EVIDENCE_HINT_RE.test(combinedText);
      const hasAction = STANDALONE_PPT_ACTION_HINT_RE.test(combinedText);
      const hasContext = STANDALONE_PPT_CONTEXT_HINT_RE.test(combinedText);
      const hasExample = STANDALONE_PPT_EXAMPLE_HINT_RE.test(combinedText);
      const hasTimeOwner = STANDALONE_PPT_TIME_OWNER_HINT_RE.test(combinedText);
      const longPointCount = points.filter((item) => item.length > 28).length;
      const genericPointCount = points.filter((item) => STANDALONE_PPT_GENERIC_POINT_RE.test(item) || item.length < 10).length;
      const suggestions = [];
      const seen = new Set();

      const pushSuggestion = (code, text) => {
          if (!code || !text || seen.has(code)) return;
          seen.add(code);
          suggestions.push({ code, text });
      };

      if (title && role !== "cover" && role !== "agenda" && !/(结论|建议|目标|计划|风险|问题|亮点|复盘|方案|路径|动作)/.test(title)) {
          pushSuggestion("title_conclusion", "建议把页标题改成结论或动作句，让听众一眼看懂这页要表达什么。");
      }

      if (role === "agenda") {
          if (points.length < 3 || longPointCount > 0) {
              pushSuggestion("agenda_chapters", "这一页更适合只保留 4-5 个章节短语作为目录，不要混入解释性长句。");
          }
      } else if (role === "summary" || role === "closing") {
          if (focusConfig?.emphasizeMetrics && !hasMetrics) {
              pushSuggestion("summary_evidence", "建议补 1 个结果指标或关键对比，让开场/结尾页更有抓手。");
          }
          if (!hasAction) {
              pushSuggestion("add_next_step", role === "closing"
                  ? "建议补一句下一步动作或决策请求，形成明确收束。"
                  : "建议补一句总判断后的业务影响或行动方向，让摘要页更完整。");
          }
      } else if (role === "background") {
          if (!hasContext) {
              pushSuggestion("add_context", "建议补充业务背景、适用场景或当前现状，为后文分析做好铺垫。");
          }
          if (!hasEvidence) {
              pushSuggestion("add_fact_basis", "建议增加一条事实、案例或数据依据，避免背景页只有概念描述。");
          }
      } else if (role === "issue") {
          if (!/(原因|影响|导致|制约|优先级)/.test(combinedText)) {
              pushSuggestion("add_cause_impact", "建议把问题写成“现象-原因-影响”，不要只罗列现象。");
          }
          if (!hasAction) {
              pushSuggestion("add_risk_response", "建议补充对应缓解动作或应对方案，让问题页能承接后文。");
          }
      } else if (role === "action") {
          if (!hasTimeOwner) {
              pushSuggestion("add_plan_owner", "建议写明时间节点、负责人或里程碑，方案页会更可执行。");
          }
          if (points.length < 3) {
              pushSuggestion("expand_points", "建议把方案拆成 2-3 个关键动作，而不是只写一句总话。");
          }
      } else if (role === "training") {
          if (!hasExample) {
              pushSuggestion("add_example", "建议补一个案例、演示步骤或易错提醒，讲解会更具体。");
          }
          if (!/(步骤|先|再|最后|注意|提醒)/.test(combinedText)) {
              pushSuggestion("add_step_sequence", "建议按步骤顺序重写要点，帮助听众跟上讲解节奏。");
          }
      } else {
          if (focusConfig?.emphasizeMetrics && !hasMetrics) {
              pushSuggestion("add_metrics", "建议加入量化指标、结果对比或阶段数据，增强这一页的说服力。");
          }
          if (!hasEvidence) {
              pushSuggestion("add_evidence", "建议补 1 条事实、案例或对比结果，支撑这一页的判断。");
          }
          if (!hasAction && /(成果|分析|洞察|亮点|价值|优势)/.test(title)) {
              pushSuggestion("add_implication", "建议补一句业务影响或后续动作，避免停留在描述层。");
          }
      }

      if (points.length < 3 && role !== "agenda" && !seen.has("expand_points")) {
          pushSuggestion("expand_points", "建议再补 1-2 条支撑要点，避免页面信息量过薄。");
      }
      if (longPointCount >= 2 || genericPointCount >= Math.max(2, points.length)) {
          pushSuggestion("tighten_bullets", "建议把过长或过泛的要点拆成短 bullet，每条只表达一个信息点。");
      }
      if (!notes) {
          pushSuggestion("add_notes", role === "training"
              ? "建议补充讲解顺序、示例说明或注意事项，方便现场讲解。"
              : "建议补充讲解备注，说明数据口径、案例背景或下一步动作。");
      }

      return suggestions.slice(0, 3);
  };

  const applyStandaloneOutlineSuggestion = (slideIndex, suggestionCode) => {
      const focusConfig = getStandalonePptContentFocusConfig(
          standalonePptOutline?.contentFocus || standalonePptForm.contentFocus || STANDALONE_PPT_DEFAULT_CONTENT_FOCUS,
      );
      const allSlides = Array.isArray(standalonePptOutline?.slides) ? standalonePptOutline.slides : [];
      updateStandaloneOutlineSlide(slideIndex, (prevSlide) => {
          const currentTitle = String(prevSlide?.title || `第 ${slideIndex + 1} 页`).trim();
          const currentPoints = Array.isArray(prevSlide?.points) ? prevSlide.points.map((item) => String(item || "").trim()).filter(Boolean) : [];
          const currentNotes = String(prevSlide?.notes || "").trim();
          const slideRole = inferStandaloneOutlineSlideRole(prevSlide, slideIndex, allSlides, focusConfig);
          const nextSlide = {
              ...prevSlide,
              title: currentTitle,
              points: currentPoints.slice(),
              notes: currentNotes,
          };
          const pushUniquePoint = (value) => {
              const normalized = String(value || "").trim();
              if (!normalized || nextSlide.points.includes(normalized) || nextSlide.points.length >= 8) return;
              nextSlide.points.push(normalized);
          };

          if (suggestionCode === "title_conclusion") {
              if (currentTitle && !/^结论[:：]/.test(currentTitle)) {
                  nextSlide.title = `结论：${currentTitle}`;
              }
              return nextSlide;
          }

          if (suggestionCode === "agenda_chapters") {
              const chapterTitles = allSlides
                  .map((item, idx) => idx === slideIndex ? "" : String(item?.title || "").trim())
                  .filter(Boolean)
                  .filter((item) => !STANDALONE_PPT_AGENDA_TITLE_RE.test(item))
                  .slice(0, 4);
              nextSlide.points = chapterTitles.length
                  ? chapterTitles.map((item, idx) => `第 ${idx + 1} 部分：${item}`)
                  : ["第一部分：背景与目标", "第二部分：分析与判断", "第三部分：关键动作", "第四部分：结论与下一步"];
              if (!nextSlide.notes) {
                  nextSlide.notes = "目录页只保留章节导航，不展开解释性内容。";
              }
              return nextSlide;
          }

          if (suggestionCode === "summary_evidence") {
              pushUniquePoint(focusConfig?.emphasizeMetrics
                  ? "补充一个最能代表结果的关键指标或阶段变化，支撑本页结论。"
                  : "补充本次分享最值得记住的一条核心收获。");
              pushUniquePoint("用一句话说明这页结论对后续内容或决策意味着什么。");
              return nextSlide;
          }

          if (suggestionCode === "add_next_step") {
              pushUniquePoint(slideRole === "closing"
                  ? "明确下一步动作、责任分工或决策请求，形成页面收束。"
                  : "补充结论落地后的业务影响或后续推进方向。");
              return nextSlide;
          }

          if (suggestionCode === "add_context") {
              pushUniquePoint("补充当前业务背景、适用场景和本次内容聚焦范围。");
              pushUniquePoint("说明现状或目标，为后续分析和建议建立起点。");
              return nextSlide;
          }

          if (suggestionCode === "add_fact_basis" || suggestionCode === "add_evidence") {
              pushUniquePoint("补充一条事实、案例或数据依据，说明本页判断来自哪里。");
              return nextSlide;
          }

          if (suggestionCode === "add_cause_impact") {
              pushUniquePoint("拆解主要问题产生的原因，并说明对结果或进度的影响。");
              return nextSlide;
          }

          if (suggestionCode === "add_risk_response") {
              pushUniquePoint("补充对应缓解动作、优先级和触发条件，形成闭环。");
              return nextSlide;
          }

          if (suggestionCode === "add_plan_owner") {
              pushUniquePoint("明确时间节点、负责人和关键里程碑，说明推进节奏。");
              return nextSlide;
          }

          if (suggestionCode === "expand_points") {
              const additions = slideRole === "action"
                  ? ["拆分 2-3 个关键动作，分别说明目标、动作和输出。", "补充阶段安排、依赖条件或资源需求。"]
                  : focusConfig?.emphasizeMetrics
                      ? ["补充关键数据表现、变化趋势或结果对比。", "补充对应动作、阶段目标或落地安排。"]
                      : ["补充步骤拆解、案例说明或关键提醒。", "补充适合讲解的结论和行动提示。"];
              additions.forEach((item) => {
                  pushUniquePoint(item);
              });
              return nextSlide;
          }

          if (suggestionCode === "add_metrics") {
              pushUniquePoint("补充量化指标、结果对比或时间节点，说明变化幅度与业务价值。");
              return nextSlide;
          }

          if (suggestionCode === "add_example") {
              pushUniquePoint("补充一个案例、演示步骤或典型场景，帮助听众理解。");
              return nextSlide;
          }

          if (suggestionCode === "add_step_sequence") {
              pushUniquePoint("按“先准备、再执行、最后检查”的顺序重写本页要点。");
              return nextSlide;
          }

          if (suggestionCode === "add_implication") {
              pushUniquePoint("补充这一页结论对应的业务影响、管理启示或后续动作。");
              return nextSlide;
          }

          if (suggestionCode === "tighten_bullets") {
              nextSlide.points = nextSlide.points.map((item) => {
                  if (item.length <= 26) return item;
                  const fragments = item
                      .split(/[，；;。]/)
                      .map((part) => part.trim())
                      .filter(Boolean);
                  return fragments.length > 1 ? fragments.slice(0, 2).join("，") : item.slice(0, 26);
              });
              if (!nextSlide.notes) {
                  nextSlide.notes = "每条要点尽量只表达一个信息点，解释性内容放到讲解备注里。";
              }
              return nextSlide;
          }

          if (suggestionCode === "add_notes") {
              if (!nextSlide.notes) {
                  nextSlide.notes = slideRole === "training"
                      ? "补充本页讲解顺序、示例说明和注意事项，便于现场表达。"
                      : focusConfig?.emphasizeMetrics
                          ? "补充本页数据口径、案例背景和下一步动作，支撑页面结论。"
                          : "补充本页讲解顺序、案例说明和核心提醒，便于现场表达。";
              }
              return nextSlide;
          }

          const logicNote = slideRole === "issue"
              ? "建议本页按“现象/原因/影响/动作”顺序展开，减少信息跳跃。"
              : focusConfig?.emphasizeMetrics
                  ? "建议本页按“现状/结果/动作”顺序展开，减少信息跳跃。"
                  : "建议本页按“概念/步骤/提醒”顺序展开，增强可理解性。";
          if (!nextSlide.notes) {
              nextSlide.notes = logicNote;
          } else if (!nextSlide.notes.includes(logicNote)) {
              nextSlide.notes = `${nextSlide.notes}\n${logicNote}`.trim();
          }
          return nextSlide;
      });
  };

  const applyTemplateSelection = (templateId, routeId = "") => {
      const selectedId = normalizeStandalonePptTemplateId(templateId || "");
      if (!selectedId) return;
      setStandalonePptForm((prev) => ({
          ...prev,
          template: selectedId,
          includeImages: true,
      }));
      setStandaloneTemplateCatalog((prev) => {
          const existing = Array.isArray(prev) ? prev : [];
          if (existing.some((item) => item.template_id === selectedId)) return existing;
          return [
              { template_id: selectedId, name: getStandalonePptTemplateLabel(selectedId), description: "来自模板预览页", source: "template_preview" },
              ...existing,
          ];
      });
      setTemplatePreviewSelection({ routeId: normalizeStandalonePptTemplateId(routeId || selectedId), templateId: selectedId });
  };

  const openTemplatePreviewPicker = () => {
      setTemplatePreviewSelection((prev) => {
          if (prev?.templateId) return prev;
          const currentTemplate = normalizeStandalonePptTemplateId(standalonePptForm.template || "");
          return currentTemplate ? { routeId: currentTemplate, templateId: currentTemplate } : { routeId: "", templateId: "" };
      });
      setIsTemplatePreviewOpen(true);
  };

  const closeTemplatePreviewPicker = () => {
      setIsTemplatePreviewOpen(false);
  };

  const handleApplyTemplateFromPreview = () => {
      if (!templatePreviewSelection?.templateId) return;
      applyTemplateSelection(templatePreviewSelection.templateId, templatePreviewSelection.routeId);
      setIsTemplatePreviewOpen(false);
  };

  const handleGeneratePresentonOutline = async () => {
      if (isOutlineGenerating || isPresentonGenerating) return;
        const resolved = resolveStandalonePptInput();
      if (resolved.error) {
          setStandalonePptResult({ error: resolved.error });
          return null;
      }

      setIsOutlineGenerating(true);
      setIsOutlineEditorOpen(false);
      setIsTemplatePreviewOpen(false);
      setStandalonePptResult(null);
      const initialPreviewLines = buildOutlinePreviewLinesFromResolved(resolved);
      setPresentonProgress({
          taskId: "",
          status: "outline_generating",
          progress: 12,
          message: "正在整理内容结构，请稍候...",
          previewLines: initialPreviewLines,
          previewCursor: Math.min(3, initialPreviewLines.length),
      });
      const outlineStartAt = Date.now();
      const progressTimer = setInterval(() => {
          setPresentonProgress((prev) => {
              if (prev.status !== "outline_generating") return prev;
              const current = Math.max(12, Number(prev.progress) || 12);
              const elapsedMs = Date.now() - outlineStartAt;
              const step = current < 36 ? 3 : (current < 72 ? 2 : 1);
              let phaseCap = 40;
              if (elapsedMs >= 6000) phaseCap = 68;
              if (elapsedMs >= 12000) phaseCap = 84;
              if (elapsedMs >= 18000) phaseCap = 93;
              if (elapsedMs >= 26000) phaseCap = 96;
              const next = Math.min(phaseCap, current + step);
              const previewLines = Array.isArray(prev.previewLines) && prev.previewLines.length ? prev.previewLines : initialPreviewLines;
              const targetCursor = Math.max(
                  1,
                  Math.min(
                      previewLines.length,
                      Math.ceil((next / 100) * previewLines.length) + (next >= 55 ? 2 : 0),
                  ),
              );
              const message = next < 30
                  ? "正在解析输入内容..."
                  : next < 55
                      ? "正在规划章节结构..."
                      : next < 80
                          ? "正在补全页级要点..."
                          : next < 94
                              ? "正在校验页间逻辑..."
                              : "正在整理最终结果...";
              return {
                  ...prev,
                  progress: next,
                  message,
                  previewLines,
                  previewCursor: Math.max(Number(prev.previewCursor) || 0, targetCursor),
              };
          });
      }, 420);

      try {
          const outlineResp = await presentationApi.generatePresentonOutline({
              input_mode: resolved.inputMode,
              content_focus: resolved.contentFocus,
              analysis_framework: getStandalonePptContentFocusConfig(resolved.contentFocus).label,
              analysis_input: resolved.analysisInput,
              document_name: resolved.documentName,
              n_slides: resolved.slideCount,
              language: "Chinese",
              require_metrics: !!standalonePptForm.requireMetrics,
                include_images: !!standalonePptForm.includeImages,
                model_backend: llmBackend === "cloud" ? "cloud" : "local",
            });

          const normalizedOutline = normalizeOutline(outlineResp?.outline, resolved.typedInput || resolved.documentName || "业务汇报");
          const outlineData = {
              ...normalizedOutline,
              sourceContext: resolved.analysisInput,
              inputMode: resolved.inputMode,
              documentName: resolved.documentName,
              contentFocus: resolved.contentFocus,
          };
          if (!outlineData.slides.length) {
              throw new Error("未生成有效大纲，请重试。");
          }
          const elapsed = Date.now() - outlineStartAt;
          const minDurationMs = 3200;
          if (elapsed < minDurationMs) {
              await new Promise((resolve) => setTimeout(resolve, minDurationMs - elapsed));
          }
          const finalPreviewLines = buildOutlinePreviewLinesFromOutline(outlineData);
          setPresentonProgress({
              taskId: "",
              status: "outline_ready",
              progress: 100,
              message: "内容结构已整理完成，正在打开编辑窗口...",
              previewLines: finalPreviewLines,
              previewCursor: finalPreviewLines.length,
          });
          await new Promise((resolve) => setTimeout(resolve, 520));
          setStandalonePptOutline(outlineData);
          setIsOutlineEditorOpen(true);
          setIsPptWorkspaceOpen(false);
          const outlineHistory = formatStandaloneOutlineHistory(outlineData, '[智能创作/PPT大纲]');
          await persistStandaloneCreativeHistory(outlineHistory, 'ppt_outline');
          setPresentonProgress({
              taskId: "",
              status: "outline_ready",
              progress: 100,
              message: "内容结构已整理完成，可编辑后继续生成 PPT。",
              previewLines: finalPreviewLines,
              previewCursor: finalPreviewLines.length,
          });
          return outlineData;
      } catch (error) {
          const errMsg = String(error?.message || "大纲生成失败");
          await persistStandaloneCreativeHistory(`[智能创作/PPT大纲失败]\n${errMsg}`, 'ppt_outline');
          setPresentonProgress({
              taskId: "",
              status: "failed",
              progress: 0,
              message: errMsg,
              previewLines: [],
              previewCursor: 0,
          });
          setIsOutlineEditorOpen(false);
          setStandalonePptResult({ error: errMsg });
          return null;
      } finally {
          clearInterval(progressTimer);
          setIsOutlineGenerating(false);
      }
  };

  const submitPresentonPptFromOutline = async (outlinePayload) => {
      if (!outlinePayload?.slides?.length) {
          setStandalonePptResult({ error: "当前内容不足以生成 PPT，请先补充输入信息。" });
          return;
      }
      setStandalonePptOutline(outlinePayload);
      const slideCount = Math.max(3, Math.min(40, outlinePayload.slides.length));
      const focusConfig = getStandalonePptContentFocusConfig(
          outlinePayload?.contentFocus || standalonePptForm.contentFocus || STANDALONE_PPT_DEFAULT_CONTENT_FOCUS,
      );
      const outlineTitle = String(outlinePayload?.title || "业务汇报").trim();
      const outlineSubtitle = sanitizeStandaloneOutlineSubtitle(
          outlinePayload?.subtitle || "",
          focusConfig?.label || "",
      );
      const sourceContext = String(outlinePayload?.sourceContext || "").trim();
      const sourceContextSnippet = sourceContext.length > 1800 ? `${sourceContext.slice(0, 1800)}...` : sourceContext;
      const sourceMode = String(outlinePayload?.inputMode || standalonePptForm.inputMode || "topic").trim();
      const sourceDocumentName = String(outlinePayload?.documentName || "").trim();
      const slidesMarkdown = buildDenseSlidesMarkdownFromOutline(outlinePayload);
      const slideTitleLines = (Array.isArray(outlinePayload?.slides) ? outlinePayload.slides : [])
          .map((slide, idx) => `${idx + 1}. ${String(slide?.title || `第 ${idx + 1} 页`).trim()}`)
          .filter(Boolean)
          .slice(0, 40);
      await persistStandaloneCreativeHistory(
          formatStandaloneOutlineHistory(outlinePayload, '[智能创作/PPT大纲]'),
          'ppt_outline',
      );

      const projectPrompt = [
          `请根据已确认大纲生成一个 ${slideCount} 页的中文 PPT。`,
          `内容导向：${focusConfig.label}`,
          `演示主题：${outlineTitle}`,
          outlineSubtitle ? `副标题：${outlineSubtitle}` : "副标题：无",
          `输入来源：${sourceMode}`,
          sourceDocumentName ? `参考文档：${sourceDocumentName}` : "",
          sourceContextSnippet ? `原始输入素材：${sourceContextSnippet}` : "",
          ...focusConfig.promptLines,
          focusConfig.emphasizeMetrics
              ? "内容要求：优先补充关键数据、事实依据、结果对比、量化收益或可验证指标，让页面更有支撑。"
              : "内容要求：优先补充概念解释、步骤拆解、案例说明、注意事项和可执行建议，让页面更容易讲清楚。",
          "一致性要求：最终内容必须以用户输入和已确认大纲为准，允许补充同主题下的细节，但不得偏离主题或重写成其他项目。",
          "禁止事项：如果用户输入或已确认大纲未明确提到 Enterprise Intelligent Office Agent 2.0、进出口企业协同办公、会议纪要、OCR、审单、数据库、数据决策等内容，禁止自行引入这些项目背景。",
          "执行要求：严格依据 slides_markdown 的页级结构生成，保持章节顺序一致；允许在同主题下补充细节，但不能只复述大纲原句。",
          "页标题规则：封面页可使用演示主题；从第 2 页开始，必须使用对应页标题，不得把“演示主题”重复写成每一页的大标题。",
          slideTitleLines.length ? `页标题清单：\n${slideTitleLines.join('\n')}` : "",
          "控制要求：language、内容导向、页面角色、展开要求、讲解备注、参考素材等辅助控制信息只用于生成约束，不得原样显示在 PPT 页面中。",
          "标题要求：各页标题必须具体、彼此有区分度，避免连续出现“背景、分析、建议、总结”这类重复泛标题；正文页标题尽量写成结论式、动作式或判断式短句。",
          "页面要求：封面和目录可简洁；正文页必须明显展开大纲内容，体现定义/现状/原因/证据/影响/动作中的多个层次，每页文字量要足以支撑单独成页。",
          "扩写要求：如果大纲要点较短，需要结合原始输入素材与内容导向补足上下文、解释和支撑信息，但不要虚构具体事实。",
          "排版要求：避免每页只有两三条很短的 bullet；正文页应形成较完整的信息块、说明句或多层要点。",
      ].filter(Boolean).join('\n');

      setIsPresentonGenerating(true);
      setIsOutlineEditorOpen(false);
      setIsPptWorkspaceOpen(true);
      setIsTemplatePreviewOpen(false);
      setStandalonePptResult(null);
      const resolvedTemplateId = normalizeStandalonePptTemplateId(standalonePptForm.template || "general") || "general";
      try {
          const submitPayload = {
              prompt: projectPrompt,
              n_slides: slideCount,
              language: "Chinese",
              template: resolvedTemplateId,
              export_as: "pptx",
              verbosity: "standard",
              provider: "cloud_async",
              slides_markdown: slidesMarkdown,
                include_images: !!standalonePptForm.includeImages,
                web_search: false,
                include_title_slide: false,
              include_table_of_contents: false,
              allow_access_to_user_info: false,
              trigger_webhook: false,
              user_id: userProfile?.id || undefined,
          };

          const submitResult = await presentationApi.submitPresentonPptTask(submitPayload);
          const taskId = String(submitResult?.task_id || "").trim();
          if (!taskId) {
              throw new Error("未获取到任务ID");
          }

          setPresentonProgress({
              taskId,
              status: "pending",
              progress: 36,
              message: submitResult?.message || "已提交生成任务，正在执行...",
          });
          const creativeSessionId = await persistStandaloneCreativeHistory(
              [
                  `[智能创作/PPT任务已提交] ${outlineTitle}（${slideCount}页）`,
                  `任务ID：${taskId}`,
                  `模板：${resolvedTemplateId}`,
                  `内容导向：${focusConfig.label}`,
              ].join('\n'),
              'ppt_task',
          );
          await pollPresentonTaskUntilSettled({
              taskId,
              outlineTitle,
              slideCount,
              templateId: resolvedTemplateId,
              contentFocusLabel: focusConfig.label,
              sessionId: creativeSessionId || currentSessionIdRef.current,
          });
      } catch (error) {
          const errMsg = String(error?.message || "未知错误");
          setPresentonProgress((prev) => ({
              ...prev,
              status: "failed",
              message: errMsg,
          }));
          await persistStandaloneCreativeHistory(
              [
                  `[智能创作/PPT生成失败] ${outlineTitle}（${slideCount}页）`,
                  `模板：${resolvedTemplateId}`,
                  `错误：${errMsg}`,
              ].join('\n'),
              'ppt_result',
          );
          setStandalonePptResult({
              error: errMsg,
          });
          setIsPptWorkspaceOpen(true);
      } finally {
          setIsPresentonGenerating(false);
      }
  };

  const handleGeneratePresentonPpt = async () => {
      if (isPresentonGenerating || isOutlineGenerating) return;
        const resolved = resolveStandalonePptInput();
      if (resolved.error) {
          setStandalonePptResult({ error: resolved.error });
          return;
      }

      if (resolved.inputMode === "longText") {
          const outlinePayload = shouldRefreshStandaloneOutlineForResolvedInput(resolved)
              ? buildStandaloneOutlineFromLongText(resolved)
              : standalonePptOutline;
          await submitPresentonPptFromOutline(outlinePayload);
          return;
      }

      if (shouldRefreshStandaloneOutlineForResolvedInput(resolved)) {
          await handleGeneratePresentonOutline();
          return;
      }

      await submitPresentonPptFromOutline(standalonePptOutline);
  };

  const updateStandaloneOutlineSlide = (slideIndex, updater) => {
      setStandalonePptOutline((prev) => {
          if (!prev || !Array.isArray(prev.slides)) return prev;
          const nextSlides = prev.slides.map((slide, idx) => {
              if (idx !== slideIndex) return slide;
              return updater(slide, idx);
          });
          return { ...prev, slides: nextSlides };
      });
  };

  const addStandaloneOutlineSlide = () => {
      setStandalonePptOutline((prev) => {
          const currentSlides = Array.isArray(prev?.slides) ? prev.slides : [];
          const nextIndex = currentSlides.length + 1;
          return {
              title: prev?.title || "业务汇报",
              subtitle: prev?.subtitle || "",
              slides: [
                  ...currentSlides,
                  {
                      index: nextIndex,
                      title: `新增页面 ${nextIndex}`,
                      points: ["补充本页核心观点", "补充本页关键数据与论据"],
                      notes: "",
                  },
              ],
          };
      });
  };

  const removeStandaloneOutlineSlide = (slideIndex) => {
      setStandalonePptOutline((prev) => {
          if (!prev || !Array.isArray(prev.slides) || prev.slides.length <= 1) return prev;
          const nextSlides = prev.slides
              .filter((_, idx) => idx !== slideIndex)
              .map((slide, idx) => ({ ...slide, index: idx + 1 }));
          return { ...prev, slides: nextSlides };
      });
  };

  const handleShareClick = () => {
    if (!currentSessionId) return;
    const session = sessionList.find(s => s.id === currentSessionId);
    setShareModal({ isOpen: true, sessionId: currentSessionId, title: session ? session.title : '新聊天' });
  };

  const handleSessionClickStable = useStableCallback(handleSessionClick);
  const handleNewChatStable = useStableCallback(handleNewChat);
  const handleSuggestionClickStable = useStableCallback(handleSuggestionClick);
  const handleModelChangeStable = useStableCallback(handleModelChange);
  const handleOpenSettingsModalStable = useStableCallback(handleOpenSettingsModal);
  const handleOpenDecisionCenterStable = useStableCallback(handleOpenDecisionCenter);
  const handleOpenTaskCenterStable = useStableCallback(handleOpenTaskCenter);
  const handleGoToTaskCenterPageStable = useStableCallback(handleGoToTaskCenterPage);
  const handleShareClickStable = useStableCallback(handleShareClick);
  const handleModeChangeStable = useStableCallback(onModeChange);
  const handleLogoutStable = useStableCallback(onLogout);

  const handleOpenSidebar = useCallback(() => setIsSidebarOpen(true), []);
  const handleCloseSidebar = useCallback(() => setIsSidebarOpen(false), []);
  const handleOpenMobileSidebar = useCallback(() => setIsMobileSidebarOpen(true), []);
  const handleCloseMobileSidebar = useCallback(() => setIsMobileSidebarOpen(false), []);
  const handleCloseTaskCenter = useCallback(() => setIsTaskCenterOpen(false), []);
  const handleToggleDesktopModelDropdown = useCallback(() => setIsDropdownOpen((open) => !open), []);
  const handleToggleMobileModelDropdown = useCallback(() => setIsMobileModelDropdownOpen((open) => !open), []);
  const handleSelectDesktopModel = useCallback((modelId) => {
    handleModelChangeStable(modelId);
    setIsDropdownOpen(false);
  }, [handleModelChangeStable]);
  const handleSelectMobileModel = useCallback((modelId) => {
    handleModelChangeStable(modelId);
    setIsMobileModelDropdownOpen(false);
  }, [handleModelChangeStable]);
  const handleHeaderOpenDecisionCenter = useCallback((event) => {
    setIsDropdownOpen(false);
    setIsMobileModelDropdownOpen(false);
    setIsTaskCenterOpen(false);
    handleOpenDecisionCenterStable(event);
  }, [handleOpenDecisionCenterStable]);
  const handleHeaderOpenTaskCenter = useCallback((event) => {
    setIsDropdownOpen(false);
    setIsMobileModelDropdownOpen(false);
    handleOpenTaskCenterStable(event);
  }, [handleOpenTaskCenterStable]);
  const handleHeaderGotoTaskCenter = useCallback((event) => {
    setIsDropdownOpen(false);
    setIsMobileModelDropdownOpen(false);
    handleGoToTaskCenterPageStable(event);
  }, [handleGoToTaskCenterPageStable]);
  const handleEmptyStateQuickAction = useCallback((prompt) => {
    setInputValue(prompt);
  }, []);

  // --- 动作处理程序 ---
  const trimIndexedState = (state, maxIndex) => {
      const next = {};
      Object.keys(state).forEach((key) => {
          const idx = Number(key);
          if (!Number.isNaN(idx) && idx <= maxIndex) {
              next[idx] = state[key];
          }
      });
      return next;
  };

  const getMessageFeedbackKey = useCallback((message, fallbackIndex = null) => {
      if (!message || typeof message !== 'object') {
          return fallbackIndex == null ? '' : `idx:${fallbackIndex}`;
      }
      if (message.id !== undefined && message.id !== null && String(message.id).trim() !== '') {
          return `h:${message.id}`;
      }
      if (message.history_id !== undefined && message.history_id !== null && String(message.history_id).trim() !== '') {
          return `h:${message.history_id}`;
      }
      if (message.messageKey && String(message.messageKey).trim()) {
          return String(message.messageKey).trim();
      }
      if (message.clientMessageId && String(message.clientMessageId).trim()) {
          return `c:${String(message.clientMessageId).trim()}`;
      }
      const safeSessionId = String(message.session_id || currentSessionId || '').trim();
      if (safeSessionId && fallbackIndex !== null && fallbackIndex !== undefined) {
          return `s:${safeSessionId}:${fallbackIndex}:${message.role || 'assistant'}`;
      }
      return fallbackIndex == null
          ? `role:${message.role || 'assistant'}`
          : `idx:${fallbackIndex}:${message.role || 'assistant'}`;
  }, [currentSessionId]);

  const setFeedbackValue = useCallback((messageKey, nextValue) => {
      const safeKey = String(messageKey || '').trim();
      if (!safeKey) return;
      setFeedbackState((prev) => {
          const next = { ...prev };
          if (!nextValue) {
              delete next[safeKey];
          } else {
              next[safeKey] = nextValue;
          }
          return next;
      });
  }, []);

  const handleEditMessageStart = (idx, content) => {
      if (isProcessing || isUploadingFile) return;
      const { attachments, remainingText } = splitUserMessageContent(content || '');
      setEditingMessageIndex(idx);
      setEditingMessageText(remainingText);
      setEditingMessageAttachments(attachments);
  };

  const handleEditMessageCancel = () => {
      setEditingMessageIndex(null);
      setEditingMessageText('');
      setEditingMessageAttachments([]);
  };

  const handleEditMessageSend = () => {
      if (editingMessageIndex === null) return;
      const trimmed = editingMessageText.trim();
      if (!trimmed && editingMessageAttachments.length === 0) return;

      const updatedContent = buildUserMessageContent(editingMessageAttachments, editingMessageText);
      setChatHistory((prev) => {
          if (!prev[editingMessageIndex] || prev[editingMessageIndex].role !== 'user') return prev;
          const next = [...prev];
          next[editingMessageIndex] = { ...next[editingMessageIndex], content: updatedContent };
          return next.slice(0, editingMessageIndex + 1);
      });

      setExpandedSources((prev) => trimIndexedState(prev, editingMessageIndex));
      setFeedbackState({});
      setCopiedIdx(null);
      setSpeakingIdx(null);
      setEditingMessageIndex(null);
      setEditingMessageText('');
      setEditingMessageAttachments([]);

      handleSendMessage(editingMessageText, true);
  };

  const getRenderedMessageText = (idx) => {
      if (typeof document === 'undefined') return '';
      const target = document.querySelector(`[data-message-content-id="${idx}"]`);
      if (!target) return '';
      return String(target.innerText || target.textContent || '')
          .replace(/\u00A0/g, ' ')
          .trim();
  };

  const handleCopy = (content, idx) => {
      const renderedText = getRenderedMessageText(idx);
      const textToCopy = renderedText || String(content || '');
      navigator.clipboard.writeText(textToCopy).then(() => {
          setCopiedIdx(idx);
          setTimeout(() => setCopiedIdx(null), 2000);
      });
  };

  const pickSpeechVoice = () => {
      if (typeof window === 'undefined' || !window.speechSynthesis) return null;
      const voices = window.speechSynthesis.getVoices() || [];
      const preferredName = appSettings?.voiceName;
      if (preferredName && preferredName !== 'auto') {
          const exact = voices.find((v) => v.name === preferredName);
          if (exact) return exact;
      }
      const language = appSettings?.replyLanguage || 'zh-CN';
      if (language === 'en-US') {
          return voices.find((v) => /en/i.test(v.lang)) || voices[0] || null;
      }
      return voices.find((v) => /zh|cn/i.test(v.lang)) || voices[0] || null;
  };

  const speakTextWithSettings = (content, onEnd) => {
      if (!content || typeof window === 'undefined' || !window.speechSynthesis) return;
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(content);
      const selectedVoice = pickSpeechVoice();
      if (selectedVoice) utterance.voice = selectedVoice;
      utterance.onend = () => {
          onEnd?.();
      };
      utterance.onerror = () => {
          onEnd?.();
      };
      window.speechSynthesis.speak(utterance);
  };

  const handleSpeak = (content, idx) => {
      if (speakingIdx === idx) {
          window.speechSynthesis.cancel();
          setSpeakingIdx(null);
          return;
      }
      setSpeakingIdx(idx);
      speakTextWithSettings(content, () => setSpeakingIdx(null));
  };

  const handleRegenerate = () => {
      // 1. 找到倒数第二个消息 (Role=User)
      // 2. 移除最后两个消息（AI 回复 + 刚刚的用户提问；注意：用户提问要保留）
      // 一般逻辑：重新生成是对上一条用户指令的重新响应。
      // 所以：获取最后一条 User Message 的内容，删除最后一条 AI Message，然后重新调用 handleSendMessage(userContent, true)

      if (chatHistory.length < 2) return;
      const lastMsg = chatHistory[chatHistory.length - 1];
      if (lastMsg.role !== 'assistant') return;

      const lastUserMsg = chatHistory[chatHistory.length - 2];
      if (!lastUserMsg || lastUserMsg.role !== 'user') return; // Should be user

      // 删除最后一条 AI 消息
      setChatHistory(prev => prev.slice(0, -1));

      // 重新发送对UI不可见（因为UI已经有用户气泡）
      // 等等，如果我使用 isHidden=true，则不会添加用户气泡。正确的。
      // 但我需要提取文本内容，剥离“附加文件”前缀（如果有）。
      let textToResend = lastUserMsg.content;

      // 简单的逻辑：传递原始内容。
      // 注意：如果 isHidden=false，handleSendMessage 将附加新的用户消息。
      // 所以我们使用isHidden=true。
      handleSendMessage(textToResend, true);
  };

  const handleFeedback = async (idx, type) => {
      const targetMessage = chatHistory[idx];
      if (!targetMessage || targetMessage.role !== 'assistant') return;

      const safeUserId = String(userProfile?.id || '').trim();
      if (!safeUserId || safeUserId === 'anonymous') return;

      const messageKey = getMessageFeedbackKey(targetMessage, idx);
      if (!messageKey) return;

      const previousFeedback = feedbackState[messageKey] || null;
      const nextFeedback = previousFeedback === type ? null : type;
      const previousMessage = idx > 0 && chatHistory[idx - 1]?.role === 'user' ? chatHistory[idx - 1] : null;
      const safeSessionId = String(
          targetMessage.session_id || currentSessionId || currentSessionIdRef.current || ''
      ).trim();

      setFeedbackValue(messageKey, nextFeedback);

      try {
          await chatFeedbackApi.submitFeedback({
              session_id: safeSessionId,
              history_id: targetMessage.id ?? targetMessage.history_id ?? null,
              message_key: messageKey,
              feedback_type: nextFeedback,
              user_message: previousMessage?.content || '',
              assistant_message: targetMessage.content || '',
              mode: targetMessage.func_type || currentMode,
              model_backend: llmBackend,
              model_id: String(selectedModel ?? ''),
          });
      } catch (error) {
          console.error('Failed to submit feedback', error);
          setFeedbackValue(messageKey, previousFeedback);
      }
  };

  const buildDefaultReportFormData = (type, backend) => {
      const resolvedBackend = backend || llmBackend;
      if (type === 'report') {
          return {
              modelBackend: resolvedBackend,
              contentType: WRITING_CONTENT_TYPE_OPTIONS[0],
              platform: WRITING_PLATFORM_OPTIONS[0],
              targetAudiences: [WRITING_AUDIENCE_PRESET[0]],
              tone: WRITING_TONE_OPTIONS[0],
              minWords: 200,
              referenceContent: "",
              keywords: "",
              withEmoji: true,
          };
      }
      if (type === 'ppt') {
          const defaultFocus = getStandalonePptContentFocusConfig(STANDALONE_PPT_DEFAULT_CONTENT_FOCUS);
          return {
              modelBackend: resolvedBackend,
              contentFocus: defaultFocus.key,
              pptSlideCount: 6,
              analysisMinWords: 350,
              analysisInput: "",
              requireMetrics: !!defaultFocus.emphasizeMetrics,
          };
      }
      return {
          modelBackend: resolvedBackend,
          consultingType: WRITING_CONSULTING_TYPE_OPTIONS[0],
          consultingRole: WRITING_CONSULTING_ROLE_OPTIONS[0],
          outputFormat: WRITING_OUTPUT_FORMAT_OPTIONS[0],
          consultingMinWords: 300,
          consultingContext: "",
          consultingConstraints: "",
          includeTimeline: true,
      };
  };

  const buildDefaultStandalonePptFormData = () => {
      const defaultFocus = getStandalonePptContentFocusConfig(STANDALONE_PPT_DEFAULT_CONTENT_FOCUS);
      return {
          inputMode: STANDALONE_PPT_INPUT_MODES[0].key,
          contentFocus: defaultFocus.key,
          pptSlideCount: 8,
          analysisInput: "",
          documentName: "",
          requireMetrics: !!defaultFocus.emphasizeMetrics,
           includeImages: true,
          template: 'general',
      };
  };

  const loadStandaloneTemplateCatalog = async () => {
      setIsTemplateCatalogLoading(true);
      try {
          const result = await presentationApi.getPresentonTemplateCatalog();
          const catalog = Array.isArray(result?.data) ? result.data : [];
          const normalized = sortStandalonePptTemplateCatalog(catalog
              .map((item) => {
                  const templateId = normalizeStandalonePptTemplateId(item?.template_id || item?.id || "");
                  const rawName = String(item?.name || item?.template_name || item?.template_id || "").trim();
                  return {
                      template_id: templateId,
                      name: getStandalonePptTemplateLabel({ template_id: templateId, name: rawName }),
                      description: String(item?.description || getStandalonePptTemplatePreviewMeta(templateId)?.summary || "").trim(),
                      thumbnail_url: String(item?.thumbnail_url || "").trim(),
                      source: String(item?.source || "").trim(),
                  };
              })
              .filter((item) => item.template_id));
          const finalCatalog = normalized.length ? normalized : STANDALONE_PPT_BUILTIN_TEMPLATES;
          setStandaloneTemplateCatalog(finalCatalog);
          setStandalonePptForm((prev) => {
              const normalizedTemplate = normalizeStandalonePptTemplateId(prev.template);
              if (finalCatalog.some((item) => item.template_id === normalizedTemplate)) {
                  return normalizedTemplate === prev.template ? prev : { ...prev, template: normalizedTemplate };
              }
              return { ...prev, template: finalCatalog[0]?.template_id || "general" };
          });
      } catch {
          setStandaloneTemplateCatalog(STANDALONE_PPT_BUILTIN_TEMPLATES);
      } finally {
          setIsTemplateCatalogLoading(false);
      }
  };

  useEffect(() => {
      if (writingEntryMode !== "ppt") return;
      loadStandaloneTemplateCatalog();
  }, [writingEntryMode]);

  const applyReportType = (nextType) => {
      if (!nextType) return;
      setReportType(nextType);
      setReportFormData((prev) => {
          const existingBackend = prev?.modelBackend || llmBackend;
          return buildDefaultReportFormData(nextType, existingBackend);
      });
      setReportAudienceInput('');
      setIsPresentonGenerating(false);
      setPresentonProgress(createIdlePresentonProgress());
      setReportStep('form');
  };

  const addAudienceTag = (rawValue) => {
      const value = String(rawValue || '').trim();
      if (!value) return;
      setReportFormData((prev) => {
          const current = Array.isArray(prev.targetAudiences) ? prev.targetAudiences : [];
          if (current.includes(value) || current.length >= WRITING_FORM_AUDIENCE_LIMIT) return prev;
          return { ...prev, targetAudiences: [...current, value] };
      });
      setReportAudienceInput('');
  };

  const removeAudienceTag = (tag) => {
      setReportFormData((prev) => {
          const current = Array.isArray(prev.targetAudiences) ? prev.targetAudiences : [];
          return { ...prev, targetAudiences: current.filter((item) => item !== tag) };
      });
  };

  const clearCurrentWritingForm = () => {
      const activeType = reportType || 'report';
      const backend = reportFormData?.modelBackend || llmBackend;
      setReportFormData(buildDefaultReportFormData(activeType, backend));
      setReportAudienceInput('');
      setIsPresentonGenerating(false);
      setPresentonProgress(createIdlePresentonProgress());
  };

  const getActiveOcrText = () => {
      if (!activeOcrFile) return '';
      const text = (activeOcrFile.ocrText || getOcrLines(activeOcrFile).map((line) => line.text).join('\n') || '').trim();
      return text;
  };

  const updateOcrSummaryDisplay = (nextText) => {
      setOcrSummaryMessages(prev => {
          if (!prev.length) return prev;
          const lastIndex = prev.length - 1;
          const last = prev[lastIndex];
          if (last.role !== 'assistant' || last.content === nextText) return prev;
          const next = [...prev];
          next[lastIndex] = { ...last, content: nextText };
          return next;
      });
  };

  const scrollOcrSummaryToBottom = () => {
      const container = ocrSummaryScrollRef.current;
      if (!container) return;
      container.scrollTop = container.scrollHeight;
  };

  const startOcrSummaryStream = () => {
      if (ocrSummaryRafRef.current) cancelAnimationFrame(ocrSummaryRafRef.current);
      const animate = () => {
          const now = performance.now ? performance.now() : Date.now();
          if (now - ocrSummaryLastFlushRef.current < 32 && ocrSummaryBufferRef.current.length < 30) {
              ocrSummaryRafRef.current = requestAnimationFrame(animate);
              return;
          }
          if (ocrSummaryBufferRef.current.length > 0) {
              const queueLength = ocrSummaryBufferRef.current.length;
              const charsToTake = queueLength > 50 ? 6 : (queueLength > 20 ? 3 : 1);
              const chunk = ocrSummaryBufferRef.current.splice(0, charsToTake).join('');
              ocrSummaryDisplayRef.current += chunk;
              updateOcrSummaryDisplay(ocrSummaryDisplayRef.current);
              scrollOcrSummaryToBottom();
          }
          ocrSummaryLastFlushRef.current = now;
          ocrSummaryRafRef.current = requestAnimationFrame(animate);
      };
      ocrSummaryRafRef.current = requestAnimationFrame(animate);
  };

  const stopOcrSummaryStream = () => {
      if (ocrSummaryRafRef.current) {
          cancelAnimationFrame(ocrSummaryRafRef.current);
          ocrSummaryRafRef.current = null;
      }
      if (ocrSummaryBufferRef.current.length > 0) {
          const remaining = ocrSummaryBufferRef.current.join('');
          ocrSummaryBufferRef.current = [];
          ocrSummaryDisplayRef.current += remaining;
          updateOcrSummaryDisplay(ocrSummaryDisplayRef.current);
          scrollOcrSummaryToBottom();
      }
  };

  const appendOcrSummaryChunk = (chunk) => {
      if (!chunk) return;
      const chars = chunk.split('');
      ocrSummaryBufferRef.current.push(...chars);
  };

  const sendOcrSummaryMessage = async (message, options = {}) => {
      const {
          silentUser = false,
          backendOverride = null,
          resetConversation = false
      } = options;
      const trimmed = (message || '').trim();
      if (!trimmed || isOcrSummaryLoading || ocrSummaryRequestLockRef.current) return;
      ocrSummaryRequestLockRef.current = true;
      const backendToUse = backendOverride || ocrSummaryBackend || 'local';

      if (resetConversation) {
          if (!silentUser) {
              setOcrSummaryMessages([{ role: 'user', content: trimmed }, { role: 'assistant', content: '' }]);
          } else {
              setOcrSummaryMessages([{ role: 'assistant', content: '' }]);
          }
      } else if (!silentUser) {
          setOcrSummaryMessages(prev => [...prev, { role: 'user', content: trimmed }, { role: 'assistant', content: '' }]);
      } else {
          setOcrSummaryMessages(prev => [...prev, { role: 'assistant', content: '' }]);
      }
      setIsOcrSummaryLoading(true);
      ocrSummaryBufferRef.current = [];
      ocrSummaryDisplayRef.current = "";
      startOcrSummaryStream();

      if (ocrSummaryAbortRef.current) {
          ocrSummaryAbortRef.current.abort();
      }
      const delay = (ms) => new Promise(resolve => setTimeout(resolve, ms));
      const token = localStorage.getItem(AUTH_TOKEN_KEY);
      const headers = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const contextContent = (ocrSummaryContextRef.current || '').slice(0, OCR_SUMMARY_MAX_CONTEXT_CHARS);
      let ocrSummarySessionId = ocrSummarySessionIdRef.current;
      if (resetConversation || !ocrSummarySessionId) {
          ocrSummarySessionId = crypto.randomUUID
              ? crypto.randomUUID()
              : `sid_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
          ocrSummarySessionIdRef.current = ocrSummarySessionId;
      }
      const payload = {
          message: trimmed,
          modelId: String(selectedModel || 0),
          session_id: ocrSummarySessionId,
          user_id: userProfile.id || 'anonymous',
          mode: 'ocr_summary',
          context_content: contextContent,
          model_backend: backendToUse,
          personalization: buildChatPersonalizationPayload(appSettings)
      };

      const runStreamAttempt = async () => {
          const controller = new AbortController();
          ocrSummaryAbortRef.current = controller;
          ocrSummaryLastChunkRef.current = Date.now();

          const clearTimers = () => {
              if (ocrSummaryTimeoutRef.current) {
                  clearTimeout(ocrSummaryTimeoutRef.current);
                  ocrSummaryTimeoutRef.current = null;
              }
              if (ocrSummaryIdleTimerRef.current) {
                  clearInterval(ocrSummaryIdleTimerRef.current);
                  ocrSummaryIdleTimerRef.current = null;
              }
          };

          clearTimers();
          ocrSummaryTimeoutRef.current = setTimeout(() => controller.abort(), OCR_SUMMARY_STREAM_TIMEOUT_MS);
          ocrSummaryIdleTimerRef.current = setInterval(() => {
              if (Date.now() - ocrSummaryLastChunkRef.current > OCR_SUMMARY_IDLE_TIMEOUT_MS) {
                  controller.abort();
              }
          }, 1000);

          let receivedAny = false;
          let receivedEnd = false;
          try {
              const response = await fetch(`${API_BASE_URL}/api/chat`, {
                  method: 'POST',
                  headers,
                  body: JSON.stringify(payload),
                  signal: controller.signal
              });

              if (!response.ok || !response.body) {
                  throw new Error('API Error');
              }

              const reader = response.body.getReader();
              const decoder = new TextDecoder();
              let done = false;
              let buffer = '';
              const processOcrSummaryStreamLine = (line) => {
                  if (!line || !line.trim()) return;
                  try {
                      const json = JSON.parse(line);
                      if (json.t === 'c') {
                          receivedAny = true;
                          ocrSummaryLastChunkRef.current = Date.now();
                          appendOcrSummaryChunk(json.v || '');
                      } else if (json.t === 'm') {
                          if (json.end) {
                              receivedEnd = true;
                          }
                      }
                  } catch {
                      // 忽略
                  }
              };

              while (!done) {
                  const { value, done: doneReading } = await reader.read();
                  done = doneReading;
                  const chunkValue = decoder.decode(value || new Uint8Array(), { stream: true });
                  buffer += chunkValue;
                  const lines = buffer.split('\n');
                  buffer = lines.pop();

                  for (const line of lines) {
                      processOcrSummaryStreamLine(line);
                  }
              }

              // 处理 decoder/缓冲区尾包，避免最后一段无换行时被丢弃
              const tailChunk = decoder.decode();
              if (tailChunk) buffer += tailChunk;
              if (buffer && buffer.trim()) {
                  const tailLines = buffer.split('\n').filter((line) => line && line.trim());
                  tailLines.forEach(processOcrSummaryStreamLine);
              }
          } catch (error) {
              if (controller.signal.aborted) {
                  return {
                      receivedAny,
                      completed: false,
                      aborted: true
                  };
              }
              throw error;
          } finally {
              clearTimers();
          }

          return {
              receivedAny,
              completed: receivedEnd,
              aborted: false
          };
      };

      let attempt = 0;
      let completed = false;
      let hadAnyContent = false;
      let interrupted = false;
      try {
          while (attempt <= OCR_SUMMARY_RETRY_LIMIT && !completed) {
              if (attempt > 0) {
                  // 失败重试时清空上一轮半截输出，避免重复拼接。
                  ocrSummaryBufferRef.current = [];
                  ocrSummaryDisplayRef.current = '';
                  updateOcrSummaryDisplay('');
              }
              try {
                  const result = await runStreamAttempt();
                  hadAnyContent = hadAnyContent || !!result?.receivedAny;
                  completed = !!result?.completed;
                  interrupted = !!result?.aborted;
              } catch {
                  completed = false;
                  interrupted = false;
              }
              if (!completed && attempt < OCR_SUMMARY_RETRY_LIMIT) {
                  await delay(OCR_SUMMARY_RETRY_DELAY_MS);
              }
              attempt += 1;
          }
          if (!completed) {
              if (hadAnyContent || interrupted) {
                  appendOcrSummaryChunk('\n（输出中断，已自动重试仍未完成，请点击“重新总结”）');
              } else {
                  appendOcrSummaryChunk('\n（生成失败，请稍后重试）');
              }
          }
      } finally {
          setIsOcrSummaryLoading(false);
          stopOcrSummaryStream();
          ocrSummaryRequestLockRef.current = false;
          if (!ocrSummaryFirstDone) setOcrSummaryFirstDone(true);
      }
  };

  const handleOpenOcrSummary = () => {
      const text = getActiveOcrText();
      if (!text) {
          alert('暂无可总结的识别内容');
          return;
      }
      ocrSummaryContextRef.current = text;
      const currentId = activeOcrFile?.id || 'active';
      if (ocrSummaryFileId !== currentId) {
          setOcrSummaryFileId(currentId);
          setOcrSummaryBackend('local');
          setOcrSummaryFirstDone(false);
          setOcrSummaryMessages([]);
          setOcrSummaryInput('');
          ocrSummarySessionIdRef.current = null;
          setIsOcrSummaryOpen(true);
          setTimeout(() => {
              sendOcrSummaryMessage(OCR_SUMMARY_DEFAULT_PROMPT, {
                silentUser: true,
                backendOverride: 'local',
                resetConversation: true
              });
          }, 0);
          return;
      }
      setIsOcrSummaryOpen(true);
  };

  const handleRegenerateOcrSummary = () => {
      if (isOcrSummaryLoading) return;
      const text = getActiveOcrText();
      if (!text) {
          alert('暂无可总结的识别内容');
          return;
      }
      ocrSummaryContextRef.current = text;
      setOcrSummaryInput('');
      sendOcrSummaryMessage(OCR_SUMMARY_DEFAULT_PROMPT, {
          silentUser: true,
          resetConversation: true
      });
  };

  const handleCloseOcrSummary = () => {
      if (ocrSummaryAbortRef.current) {
          ocrSummaryAbortRef.current.abort();
          ocrSummaryAbortRef.current = null;
      }
      if (ocrSummaryTimeoutRef.current) {
          clearTimeout(ocrSummaryTimeoutRef.current);
          ocrSummaryTimeoutRef.current = null;
      }
      if (ocrSummaryIdleTimerRef.current) {
          clearInterval(ocrSummaryIdleTimerRef.current);
          ocrSummaryIdleTimerRef.current = null;
      }
      stopOcrSummaryStream();
      setIsOcrSummaryLoading(false);
      ocrSummaryRequestLockRef.current = false;
      setIsOcrSummaryOpen(false);
  };

  const handleOnboardingStart = (event) => {
      if (event?.preventDefault) event.preventDefault();
      const uid = userProfile?.id;
      if (uid && uid !== 'anonymous') {
          try {
              localStorage.setItem(`${ONBOARDING_STORAGE_PREFIX}${uid}`, new Date().toISOString());
          } catch {
              // Ignore onboarding persistence errors.
          }
      }
      setShowOnboarding(false);
      if (selectedModel !== 0) {
          handleModelChange(0);
          return;
      }
      handleNewChat();
  };

  const handleSendCurrentOcrSummaryMessage = useCallback(() => {
      const nextMessage = (ocrSummaryInput || '').trim();
      if (!nextMessage) return;
      sendOcrSummaryMessage(nextMessage);
      setOcrSummaryInput('');
  }, [ocrSummaryInput, sendOcrSummaryMessage]);

  const handleOpenWritingAssistantEntry = useCallback(() => {
      setWritingEntryMode('assistant');
      setReportStep('selection');
      setReportType(null);
      setReportFormData({});
      setReportAudienceInput('');
  }, []);

  const handleOpenStandalonePptEntry = useCallback(() => {
      setWritingEntryMode('ppt');
      setStandalonePptForm(buildDefaultStandalonePptFormData());
      setStandalonePptOutline(null);
      setIsOutlineEditorOpen(false);
      setIsPptWorkspaceOpen(false);
      setIsTemplatePreviewOpen(false);
      setTemplatePreviewSelection({ routeId: '', templateId: '' });
      setStandalonePptResult(null);
      setIsPresentonGenerating(false);
      setIsOutlineGenerating(false);
      setPresentonProgress(createIdlePresentonProgress());
  }, []);

  const renderStandalonePptGenerator = () => {
      const inputMode = standalonePptForm.inputMode || STANDALONE_PPT_INPUT_MODES[0].key;
      const progressValue = Math.max(0, Math.min(100, Number(presentonProgress.progress) || 0));
      const progressStatus = String(presentonProgress.status || 'idle').toLowerCase();
      const progressStatusLabelMap = {
          idle: "待开始",
          pending: "排队中",
          running: "生成中",
          processing: "处理中",
          outline_generating: "内容整理中",
          outline_ready: "内容已就绪",
          completed: "已完成",
          done: "已完成",
          success: "已完成",
          succeeded: "已完成",
          failed: "失败",
          error: "失败",
          cancelled: "已取消",
          canceled: "已取消",
      };
      const progressStatusLabel = progressStatusLabelMap[progressStatus] || progressStatus || "处理中";
      const isProgressVisible = progressStatus !== 'idle' || isPresentonGenerating || isOutlineGenerating || progressValue > 0 || !!presentonProgress.message;
      const slideCountPreview = Math.max(3, Math.min(40, Number(standalonePptForm.pptSlideCount) || 8));
      const inputLength = String(standalonePptForm.analysisInput || "").length;
      const textInputClass = "w-full rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-4 py-3 text-sm text-gray-800 dark:text-gray-100 outline-none focus:border-emerald-400 dark:focus:border-emerald-500 focus:ring-4 focus:ring-emerald-100 dark:focus:ring-emerald-900/40";
      const textAreaClass = `${textInputClass} min-h-[200px] resize-none`;
      const hasOutline = Array.isArray(standalonePptOutline?.slides) && standalonePptOutline.slides.length > 0;
      const selectedFocusConfig = getStandalonePptContentFocusConfig(standalonePptForm.contentFocus || STANDALONE_PPT_DEFAULT_CONTENT_FOCUS);
      const editorFocusConfig = getStandalonePptContentFocusConfig(
          standalonePptOutline?.contentFocus || selectedFocusConfig.key,
      );
      const fallbackPreviewLines = buildOutlinePreviewLinesFromResolved({
          inputMode,
          slideCount: slideCountPreview,
          contentFocus: selectedFocusConfig.key,
          analysisInput: standalonePptForm.analysisInput,
          typedInput: standalonePptForm.analysisInput,
          documentName: standalonePptForm.documentName,
      });
      const outlineProgressLines =
          Array.isArray(presentonProgress.previewLines) && presentonProgress.previewLines.length
              ? presentonProgress.previewLines
              : fallbackPreviewLines;
      const outlineProgressCursor = Math.max(
          1,
          Math.min(
              outlineProgressLines.length,
              Number(presentonProgress.previewCursor) || Math.ceil((Math.max(12, progressValue) / 100) * outlineProgressLines.length),
          ),
      );
      const visibleOutlineProgressLines = outlineProgressLines.slice(0, outlineProgressCursor);
      const resolvedStandaloneInput = resolveStandalonePptInput();
      const isCurrentOutlineReusable = !resolvedStandaloneInput?.error && !shouldRefreshStandaloneOutlineForResolvedInput(resolvedStandaloneInput);
      const resolvedStandaloneTemplateId = normalizeStandalonePptTemplateId(standalonePptForm.template || "general") || "general";
      const selectedTemplate = standaloneTemplateCatalog.find((item) => item.template_id === resolvedStandaloneTemplateId);
      const selectedTemplateLabel = getStandalonePptTemplateLabel(selectedTemplate || resolvedStandaloneTemplateId);
      const hasGeneratedPpt = !!(standalonePptResult?.editUrl || standalonePptResult?.downloadUrl);
      const hasStandalonePptActions = !!(standalonePptResult?.downloadUrl || standalonePptResult?.editUrl);
      const slideCountOptions = [6, 8, 10, 12, 15, 20].map((count) => ({ value: count, label: `${count}页` }));
      const contentFocusOptions = STANDALONE_PPT_CONTENT_FOCUS_OPTIONS.map((item) => ({ value: item.key, label: item.label }));
      const templateOptions = standaloneTemplateCatalog.map((item) => ({
          value: item.template_id,
          label: getStandalonePptTemplateLabel(item),
      }));
      const templatePreviewCatalog = standaloneTemplateCatalog.length ? standaloneTemplateCatalog : STANDALONE_PPT_BUILTIN_TEMPLATES;

      return (
          <div className="h-full w-full overflow-y-auto bg-[linear-gradient(180deg,#e8f6f2_0%,#f4f8f7_46%,#f8fbfa_100%)] dark:bg-[radial-gradient(circle_at_20%_10%,#1f2937_0%,#111827_45%,#030712_100%)] px-3 py-4 md:px-6 md:py-7">
              <div className="mx-auto max-w-6xl">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                      <button
                          type="button"
                          onClick={() => {
                              if (isPptWorkspaceOpen) {
                                  setIsPptWorkspaceOpen(false);
                                  return;
                              }
                              setWritingEntryMode('root');
                              setStandalonePptOutline(null);
                              setIsOutlineEditorOpen(false);
                              setIsPptWorkspaceOpen(false);
                              setIsTemplatePreviewOpen(false);
                              setTemplatePreviewSelection({ routeId: '', templateId: '' });
                              setStandalonePptResult(null);
                              setIsPresentonGenerating(false);
                              setIsOutlineGenerating(false);
                              setPresentonProgress(createIdlePresentonProgress());
                          }}
                          className="inline-flex items-center gap-1 rounded-xl border border-gray-300 dark:border-slate-700 bg-white/80 dark:bg-slate-900/80 px-3 py-2 text-sm text-gray-600 dark:text-gray-300 hover:bg-white dark:hover:bg-slate-800"
                      >
                          <ArrowLeft size={14} /> {isPptWorkspaceOpen ? "返回生成配置" : "返回一级功能"}
                      </button>
                      <div className="rounded-xl border border-emerald-200/80 dark:border-emerald-500/30 bg-emerald-50/90 dark:bg-emerald-900/20 px-3 py-2 text-xs text-emerald-700 dark:text-emerald-200">
                          固定模型：qwen3:1.7b
                      </div>
                  </div>

                  {!isPptWorkspaceOpen && (
                      <>
                  <div className="mt-6 text-center">
                      <h2 className="text-[34px] leading-tight font-black text-gray-900 dark:text-white md:text-[56px]">
                          AI生成PPT，<span className="text-[#4fbf53]">高效交付</span>
                      </h2>
                      <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
                          系统会根据输入自动整理内容结构；长文本可直接转为 PPT
                      </p>
                  </div>

                  <div className="mx-auto mt-5 max-w-4xl rounded-full border border-gray-200 dark:border-slate-700 bg-[#e5e7ea]/95 dark:bg-slate-800/90 p-1.5">
                      <div className="flex flex-wrap gap-1">
                          {STANDALONE_PPT_INPUT_MODES.map((mode) => {
                              const Icon = mode.icon;
                              const active = inputMode === mode.key;
                              return (
                                  <button
                                      key={mode.key}
                                      type="button"
                                      onClick={() => setStandalonePptForm((prev) => ({ ...prev, inputMode: mode.key }))}
                                      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm transition-colors ${
                                          active
                                              ? "bg-white dark:bg-slate-900 text-emerald-600 dark:text-emerald-300 shadow-sm"
                                              : "text-gray-600 dark:text-gray-300 hover:text-gray-800 dark:hover:text-white"
                                      }`}
                                  >
                                      <Icon size={15} />
                                      {mode.label}
                                  </button>
                              );
                          })}
                      </div>
                  </div>

                  <div className="mx-auto mt-4 max-w-5xl rounded-2xl border border-gray-300/90 dark:border-slate-700 bg-white/85 dark:bg-slate-900/85 p-4 shadow-[0_12px_30px_rgba(15,23,42,0.08)] md:p-6">
                      <div className="min-h-[280px] rounded-xl border border-gray-200 dark:border-slate-700 bg-[#f7f8f8] dark:bg-slate-900/80 p-4 md:p-5">
                          {inputMode === "topic" && (
                              <textarea
                                  className={textAreaClass}
                                  placeholder="请输入你想制作的 PPT 主题"
                                  value={standalonePptForm.analysisInput || ""}
                                  maxLength={10000}
                                  onChange={(event) => setStandalonePptForm((prev) => ({ ...prev, analysisInput: event.target.value }))}
                              />
                          )}

                          {inputMode === "document" && (
                              <div className="space-y-4">
                                  <div className="rounded-xl border border-dashed border-gray-300 dark:border-slate-600 bg-white/80 dark:bg-slate-950/70 px-4 py-7 text-center">
                                      <label className="inline-flex cursor-pointer items-center gap-1 rounded-lg bg-emerald-500 px-5 py-2.5 text-sm font-semibold text-white hover:bg-emerald-600">
                                          上传文档
                                          <input
                                              type="file"
                                              accept=".pdf,.doc,.docx,.txt"
                                              className="hidden"
                                              onChange={(event) => {
                                                  const file = event.target.files?.[0];
                                                  setStandalonePptForm((prev) => ({ ...prev, documentName: file ? file.name : "" }));
                                              }}
                                          />
                                      </label>
                                      <p className="mt-3 text-sm text-gray-700 dark:text-gray-200">或者直接将文档拖到这里</p>
                                      <p className="mt-2 text-xs text-gray-400 dark:text-gray-400">
                                          建议上传 10000 字、10MB 以内的 PDF/DOC/DOCX/TXT 文件
                                      </p>
                                      {standalonePptForm.documentName && (
                                          <p className="mt-3 text-xs font-medium text-emerald-700 dark:text-emerald-300">
                                              已选择：{standalonePptForm.documentName}
                                          </p>
                                      )}
                                  </div>
                                  <textarea
                                      className={`${textInputClass} min-h-[100px] resize-none`}
                                      placeholder="可选：补充文档内容说明（例如目标受众、汇报重点）"
                                      value={standalonePptForm.analysisInput || ""}
                                      maxLength={10000}
                                      onChange={(event) => setStandalonePptForm((prev) => ({ ...prev, analysisInput: event.target.value }))}
                                  />
                              </div>
                          )}

                          {inputMode === "longText" && (
                              <div className="relative h-full">
                                  <textarea
                                      className={textAreaClass}
                                      placeholder="输入或粘贴大纲或任意文本内容，可直接生成 PPT"
                                      value={standalonePptForm.analysisInput || ""}
                                      maxLength={10000}
                                      onChange={(event) => setStandalonePptForm((prev) => ({ ...prev, analysisInput: event.target.value }))}
                                  />
                                  <div className="mt-2 text-right text-xs text-gray-500 dark:text-gray-400">{inputLength}/10000</div>
                              </div>
                          )}
                      </div>

                      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                          <div className="flex flex-wrap items-center gap-2">
                              <StandalonePptSelect
                                  label="篇幅"
                                  value={standalonePptForm.pptSlideCount ?? 8}
                                  options={slideCountOptions}
                                  onChange={(nextValue) => setStandalonePptForm((prev) => ({ ...prev, pptSlideCount: Number(nextValue) }))}
                              />
                              <StandalonePptSelect
                                  label="内容导向"
                                  value={selectedFocusConfig.key}
                                  options={contentFocusOptions}
                                  onChange={(nextValue) => {
                                      const nextFocus = getStandalonePptContentFocusConfig(nextValue);
                                      setStandalonePptForm((prev) => ({
                                          ...prev,
                                          contentFocus: nextFocus.key,
                                          requireMetrics: !!nextFocus.emphasizeMetrics,
                                      }));
                                  }}
                              />
                              <StandalonePptSelect
                                  label="模板"
                                  value={resolvedStandaloneTemplateId}
                                  options={templateOptions}
                                  onChange={(nextValue) => setStandalonePptForm((prev) => ({ ...prev, template: normalizeStandalonePptTemplateId(nextValue) }))}
                                  disabled={templateOptions.length === 0}
                              />
                              <button
                                  type="button"
                                  onClick={openTemplatePreviewPicker}
                                  className="inline-flex items-center gap-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-gray-700 dark:text-gray-100 hover:bg-gray-50 dark:hover:bg-slate-800"
                              >
                                  模板预览选择
                              </button>
                          </div>

                          <div className="flex flex-wrap items-center gap-2">
                              <button
                                  type="button"
                                  onClick={() => {
                                      setStandalonePptForm(buildDefaultStandalonePptFormData());
                                      setStandalonePptOutline(null);
                                      setIsOutlineEditorOpen(false);
                                      setIsPptWorkspaceOpen(false);
                                      setIsTemplatePreviewOpen(false);
                                      setTemplatePreviewSelection({ routeId: '', templateId: '' });
                                      setStandalonePptResult(null);
                                      setPresentonProgress(createIdlePresentonProgress());
                                  }}
                                  className="rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-slate-800"
                              >
                                  重置
                              </button>
                              <button
                                  type="button"
                                  onClick={handleGeneratePresentonPpt}
                                  disabled={isOutlineGenerating || isPresentonGenerating}
                                  className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-60"
                              >
                                  {(isOutlineGenerating || isPresentonGenerating) ? <Loader2 size={15} className="animate-spin" /> : <Presentation size={15} />}
                                  {isOutlineGenerating ? "内容整理中" : (isPresentonGenerating ? `生成中 ${Math.round(progressValue)}%` : "生成PPT")}
                              </button>
                              <button
                                  type="button"
                                  onClick={() => setIsOutlineEditorOpen(true)}
                                  disabled={!hasOutline || isOutlineGenerating || !isCurrentOutlineReusable}
                                  className="inline-flex items-center gap-1.5 rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-4 py-2 text-sm font-semibold text-gray-700 dark:text-gray-100 hover:bg-gray-50 dark:hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
                              >
                                  编辑大纲
                              </button>
                          </div>
                      </div>
                      <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                          {isTemplateCatalogLoading
                              ? "模板加载中..."
                              : `当前模板：${selectedTemplateLabel}`}
                      </div>
                  </div>

                  <div className="mx-auto mt-4 flex max-w-5xl flex-wrap gap-3">
                      {STANDALONE_PPT_TOPIC_SUGGESTIONS.map((item) => (
                          <button
                              key={item}
                              type="button"
                              onClick={() => setStandalonePptForm((prev) => ({
                                  ...prev,
                                  inputMode: "topic",
                                  analysisInput: getStandalonePptTopicSuggestionPrompt(item),
                              }))}
                              className="rounded-full border border-emerald-200 dark:border-emerald-500/30 bg-white/80 dark:bg-slate-900/80 px-5 py-2 text-sm text-gray-700 dark:text-gray-200 hover:border-emerald-300 dark:hover:border-emerald-400 hover:text-emerald-700 dark:hover:text-emerald-300"
                          >
                              {item}
                          </button>
                      ))}
                  </div>
                      </>
                  )}

                  {isPptWorkspaceOpen && hasOutline && (
                      <div className="mx-auto mt-4 max-w-5xl rounded-2xl border border-gray-200 dark:border-slate-700 bg-white/90 dark:bg-slate-900/90 p-3 md:p-4">
                          <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-gray-200 dark:border-slate-700 bg-gray-50/70 dark:bg-slate-800/50 px-3 py-2">
                              <div className="text-xs text-gray-600 dark:text-gray-300">左侧大纲 / 右侧PPT，可在这里切换模板后重新生成</div>
                              <div className="flex flex-wrap items-center gap-2">
                                  <select
                                      className="rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-2.5 py-1.5 text-xs text-gray-700 dark:text-gray-100 outline-none"
                                      value={resolvedStandaloneTemplateId}
                                      onChange={(event) => setStandalonePptForm((prev) => ({ ...prev, template: normalizeStandalonePptTemplateId(event.target.value) }))}
                                  >
                                      {standaloneTemplateCatalog.map((item) => (
                                          <option key={`workspace-template-${item.template_id}`} value={item.template_id}>
                                              {getStandalonePptTemplateLabel(item)}
                                          </option>
                                      ))}
                                  </select>
                                  <button
                                      type="button"
                                      onClick={openTemplatePreviewPicker}
                                      className="rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-1.5 text-xs font-semibold text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-slate-800"
                                  >
                                      模板预览选择
                                  </button>
                                  <button
                                      type="button"
                                      onClick={handleGeneratePresentonPpt}
                                      disabled={isPresentonGenerating || isOutlineGenerating || !hasOutline}
                                      className="rounded-lg bg-emerald-500 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-60"
                                  >
                                      按当前模板重新生成
                                  </button>
                              </div>
                          </div>
                          {hasStandalonePptActions && (
                              <div className="mb-3 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-emerald-200 dark:border-emerald-500/30 bg-emerald-50/80 dark:bg-emerald-900/20 px-3 py-3">
                                  <div className="min-w-0">
                                      <div className="text-sm font-semibold text-emerald-700 dark:text-emerald-200">PPT 生成完成</div>
                                      <div className="mt-1 text-xs text-emerald-700/80 dark:text-emerald-200/80">
                                          来源：{standalonePptResult?.provider || 'presenton'} · 页数：{standalonePptResult?.slideCount || slideCountPreview}
                                      </div>
                                  </div>
                                  <div className="flex flex-wrap items-center gap-2">
                                      {standalonePptResult?.downloadUrl && (
                                          <a
                                              href={standalonePptResult.downloadUrl}
                                              target="_blank"
                                              rel="noreferrer"
                                              className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-2 text-xs font-semibold text-white hover:bg-emerald-700"
                                          >
                                              <Download size={13} /> 下载PPT
                                          </a>
                                      )}
                                      {standalonePptResult?.editUrl && (
                                          <a
                                              href={standalonePptResult.editUrl}
                                              target="_blank"
                                              rel="noreferrer"
                                              className="inline-flex items-center gap-1 rounded-lg border border-emerald-300 dark:border-emerald-500/40 px-3 py-2 text-xs font-semibold text-emerald-700 dark:text-emerald-200 hover:bg-emerald-50 dark:hover:bg-emerald-900/30"
                                          >
                                              在线编辑
                                          </a>
                                      )}
                                  </div>
                              </div>
                          )}
                          {isProgressVisible && (
                              <div className="mb-3 rounded-xl border border-emerald-100 dark:border-emerald-500/30 bg-emerald-50/70 dark:bg-emerald-900/20 p-3">
                                  <div className="flex flex-wrap items-center justify-between gap-2">
                                      <div className="text-sm font-semibold text-emerald-700 dark:text-emerald-200">
                                          {presentonProgress.message || "任务执行中..."}
                                      </div>
                                      <div className="inline-flex items-center gap-2 text-xs text-emerald-700/90 dark:text-emerald-200/90">
                                          <span className="rounded-full border border-emerald-200 dark:border-emerald-500/30 bg-white/70 dark:bg-emerald-900/40 px-2 py-0.5">{progressStatusLabel}</span>
                                          <span>{Math.round(progressValue)}%</span>
                                      </div>
                                  </div>
                                  <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-emerald-100 dark:bg-emerald-800/40">
                                      <div className="h-full bg-emerald-500 transition-all duration-300" style={{ width: `${progressValue}%` }} />
                                  </div>
                                  {presentonProgress.taskId && (
                                      <div className="mt-2 text-[11px] text-emerald-700/80 dark:text-emerald-200/80 break-all">
                                          任务ID：{presentonProgress.taskId}
                                      </div>
                                  )}
                              </div>
                          )}
                          <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(320px,0.44fr)_minmax(0,0.56fr)]">
                              <div className="rounded-xl border border-gray-200 dark:border-slate-700 bg-gray-50/70 dark:bg-slate-900/60 overflow-hidden">
                                  <div className="px-3 py-2 border-b border-gray-200 dark:border-slate-700 text-sm font-semibold text-gray-900 dark:text-white">
                                      大纲区
                                  </div>
                                  <div className="max-h-[620px] overflow-y-auto p-3 space-y-3 custom-scrollbar">
                                      {standalonePptOutline.slides.map((slide, idx) => (
                                          <div key={`workspace-outline-${idx}`} className="rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800/70 p-3">
                                              <div className="text-xs font-semibold text-emerald-700 dark:text-emerald-300">第 {idx + 1} 页</div>
                                              <div className="mt-1 text-sm font-medium text-gray-900 dark:text-white">{slide.title || `第 ${idx + 1} 页`}</div>
                                              <div className="mt-2 space-y-1 text-xs text-gray-600 dark:text-gray-300">
                                                  {(Array.isArray(slide.points) ? slide.points : []).map((point, pointIdx) => (
                                                      <div key={`workspace-outline-point-${idx}-${pointIdx}`}>• {point}</div>
                                                  ))}
                                              </div>
                                          </div>
                                      ))}
                                  </div>
                              </div>
                              <div className="rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 overflow-hidden">
                                  <div className="px-3 py-2 border-b border-gray-200 dark:border-slate-700 text-sm font-semibold text-gray-900 dark:text-white">
                                      PPT区
                                  </div>
                                  <div className="h-[620px] bg-gray-50 dark:bg-slate-950">
                                      {standalonePptResult?.editUrl ? (
                                          <iframe
                                              src={standalonePptResult.editUrl}
                                              title="PPT 在线预览"
                                              className="w-full h-full border-0"
                                          />
                                      ) : standalonePptResult?.error ? (
                                          <div className="flex h-full items-center justify-center p-6">
                                              <div className="w-full max-w-md rounded-2xl border border-red-200 dark:border-red-500/30 bg-white/95 dark:bg-slate-900/90 p-6 text-center shadow-sm">
                                                  <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-red-50 text-red-500 dark:bg-red-900/20 dark:text-red-300">
                                                      <AlertTriangle size={24} />
                                                  </div>
                                                  <div className="mt-4 text-lg font-semibold text-gray-900 dark:text-white">PPT 生成失败</div>
                                                  <div className="mt-2 text-sm leading-6 text-gray-500 dark:text-gray-400">
                                                      {standalonePptResult.error}
                                                  </div>
                                                  <div className="mt-4 text-xs text-gray-400 dark:text-gray-500">
                                                      可调整左侧大纲或切换模板后重新生成。
                                                  </div>
                                              </div>
                                          </div>
                                      ) : !hasGeneratedPpt ? (
                                          <div className="flex h-full items-center justify-center p-6">
                                              <div className="w-full max-w-lg rounded-[28px] border border-emerald-100 dark:border-emerald-500/20 bg-white/95 dark:bg-slate-900/90 p-6 shadow-[0_18px_50px_rgba(16,24,40,0.12)]">
                                                  <div className="flex items-center justify-between gap-3">
                                                      <div>
                                                          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-600 dark:text-emerald-300">
                                                              PPT Rendering
                                                          </div>
                                                          <div className="mt-2 text-xl font-semibold text-gray-900 dark:text-white">
                                                              正在生成演示文稿
                                                          </div>
                                                      </div>
                                                      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-600 dark:bg-emerald-900/20 dark:text-emerald-300">
                                                          <Loader2 size={22} className="animate-spin" />
                                                      </div>
                                                  </div>

                                                  <div className="mt-4 rounded-2xl border border-emerald-100 dark:border-emerald-500/20 bg-emerald-50/80 dark:bg-emerald-900/10 px-4 py-3">
                                                      <div className="flex items-center justify-between gap-3 text-sm">
                                                          <span className="font-medium text-emerald-700 dark:text-emerald-200">
                                                              {presentonProgress.message || "正在根据当前大纲排版并生成页面..."}
                                                          </span>
                                                          <span className="text-emerald-700/80 dark:text-emerald-200/80">
                                                              {Math.round(progressValue)}%
                                                          </span>
                                                      </div>
                                                      <div className="mt-3 h-2 overflow-hidden rounded-full bg-emerald-100 dark:bg-emerald-800/40">
                                                          <div className="h-full rounded-full bg-gradient-to-r from-emerald-500 via-teal-400 to-cyan-400 transition-all duration-500" style={{ width: `${Math.max(8, progressValue)}%` }} />
                                                      </div>
                                                  </div>

                                                  <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
                                                      {[0, 1, 2, 3].map((cardIdx) => (
                                                          <div key={`ppt-loading-skeleton-${cardIdx}`} className="rounded-2xl border border-gray-200 dark:border-slate-700 bg-gray-50/90 dark:bg-slate-800/60 p-4">
                                                              <div className="h-3 w-16 rounded-full bg-emerald-100 dark:bg-emerald-900/40 animate-pulse" />
                                                              <div className="mt-4 h-20 rounded-xl bg-gradient-to-br from-emerald-100 via-white to-cyan-100 dark:from-slate-700 dark:via-slate-800 dark:to-slate-700 animate-pulse" />
                                                              <div className="mt-4 space-y-2">
                                                                  <div className="h-2.5 w-5/6 rounded-full bg-gray-200 dark:bg-slate-700 animate-pulse" />
                                                                  <div className="h-2.5 w-2/3 rounded-full bg-gray-200 dark:bg-slate-700 animate-pulse" />
                                                                  <div className="h-2.5 w-3/4 rounded-full bg-gray-200 dark:bg-slate-700 animate-pulse" />
                                                              </div>
                                                          </div>
                                                      ))}
                                                  </div>

                                                  <div className="mt-5 flex items-center justify-between gap-3 text-xs text-gray-500 dark:text-gray-400">
                                                      <span>模板：{selectedTemplateLabel}</span>
                                                      <span>{selectedFocusConfig.label} · {slideCountPreview} 页</span>
                                                  </div>
                                              </div>
                                          </div>
                                      ) : (
                                          <div className="flex h-full items-center justify-center p-6">
                                              <div className="w-full max-w-md rounded-2xl border border-emerald-200 dark:border-emerald-500/30 bg-white/95 dark:bg-slate-900/90 p-6 text-center shadow-sm">
                                                  <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-600 dark:bg-emerald-900/20 dark:text-emerald-300">
                                                      <Check size={24} />
                                                  </div>
                                                  <div className="mt-4 text-lg font-semibold text-gray-900 dark:text-white">PPT 已生成完成</div>
                                                  <div className="mt-2 text-sm leading-6 text-gray-500 dark:text-gray-400">
                                                      当前结果已可下载。若返回在线编辑地址，这里会自动切换为 PPT 编辑区。
                                                  </div>
                                                  <div className="mt-4 rounded-xl border border-gray-200 dark:border-slate-700 bg-gray-50 dark:bg-slate-800/60 px-4 py-3 text-xs text-gray-600 dark:text-gray-300">
                                                      模板：{selectedTemplateLabel} · {slideCountPreview} 页 · {selectedFocusConfig.label}
                                                  </div>
                                              </div>
                                          </div>
                                      )}
                                  </div>
                              </div>
                          </div>
                      </div>
                  )}

                  {!isPptWorkspaceOpen && (
                  <div className="mx-auto mt-4 grid max-w-5xl grid-cols-1 gap-3 md:grid-cols-2">
                      <div className="rounded-xl border border-emerald-100 dark:border-emerald-500/30 bg-emerald-50/70 dark:bg-emerald-900/20 p-4">
                          <div className="text-sm font-semibold text-emerald-700 dark:text-emerald-200">{presentonProgress.message || "等待生成任务"}</div>
                          <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-emerald-100 dark:bg-emerald-800/40">
                              <div className="h-full bg-emerald-500 transition-all duration-300" style={{ width: `${progressValue}%` }} />
                          </div>
                          <div className="mt-2 text-xs text-emerald-700/80 dark:text-emerald-200/80">{Math.round(progressValue)}%</div>
                      </div>

                      <div className="rounded-xl border border-gray-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/80 p-4">
                          <div className="text-sm font-semibold text-gray-900 dark:text-white">生成概览</div>
                          <div className="mt-2 space-y-1 text-xs text-gray-600 dark:text-gray-300">
                              <p>内容导向：{selectedFocusConfig.label}</p>
                              <p>预计页数：{slideCountPreview} 页</p>
                              <p>模板：{selectedTemplateLabel}</p>
                              <p>输入模式：{STANDALONE_PPT_INPUT_MODES.find((item) => item.key === inputMode)?.label || "输入PPT主题"}</p>
                              <p>内容提示：{selectedFocusConfig.description}</p>
                              <p>大纲状态：{hasOutline ? `已生成（${standalonePptOutline.slides.length} 页）` : "待生成"}</p>
                          </div>
                      </div>
                  </div>
                  )}

                  {!isPptWorkspaceOpen && standalonePptResult?.downloadUrl && (
                      <div className="mx-auto mt-3 max-w-5xl rounded-xl border border-emerald-200 dark:border-emerald-500/30 bg-emerald-50/70 dark:bg-emerald-900/20 p-4">
                          <p className="text-sm font-semibold text-emerald-700 dark:text-emerald-200">PPT 生成完成</p>
                          <p className="mt-1 text-xs text-emerald-700/80 dark:text-emerald-200/80">
                              来源：{standalonePptResult.provider} · 页数：{standalonePptResult.slideCount}
                          </p>
                          <div className="mt-3 flex flex-wrap gap-2">
                              <a
                                  href={standalonePptResult.downloadUrl}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-2 text-xs font-semibold text-white hover:bg-emerald-700"
                              >
                                  <Download size={13} /> 下载PPT
                              </a>
                              {standalonePptResult.editUrl && (
                                  <a
                                      href={standalonePptResult.editUrl}
                                      target="_blank"
                                      rel="noreferrer"
                                      className="inline-flex items-center gap-1 rounded-lg border border-emerald-300 dark:border-emerald-500/40 px-3 py-2 text-xs font-semibold text-emerald-700 dark:text-emerald-200 hover:bg-emerald-50 dark:hover:bg-emerald-900/30"
                                  >
                                      在线编辑
                                  </a>
                              )}
                          </div>
                      </div>
                  )}

                  {standalonePptResult?.error && (
                      <div className="mx-auto mt-3 max-w-5xl rounded-xl border border-red-200 dark:border-red-500/40 bg-red-50/80 dark:bg-red-900/20 p-4 text-sm text-red-700 dark:text-red-200">
                          {standalonePptResult.error}
                      </div>
                  )}

                  {isTemplatePreviewOpen && (
                      <div className="fixed inset-0 z-[75] flex items-center justify-center p-3 md:p-5">
                          <div className="absolute inset-0 bg-black/50" onClick={closeTemplatePreviewPicker} />
                          <div className="relative w-full max-w-[1180px] rounded-2xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-2xl overflow-hidden flex max-h-[90vh] flex-col">
                              <div className="px-5 py-3 border-b border-gray-200 dark:border-slate-700 flex items-center justify-between gap-2">
                                  <div className="text-lg font-semibold text-gray-900 dark:text-white">模板预览与选择</div>
                                  <button
                                      type="button"
                                      onClick={closeTemplatePreviewPicker}
                                      className="rounded-lg border border-gray-200 dark:border-slate-700 p-2 text-gray-500 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-slate-800"
                                  >
                                      <X size={18} />
                                  </button>
                              </div>
                              <div className="px-5 py-3 border-b border-gray-200 dark:border-slate-700 text-sm text-gray-500 dark:text-gray-400">
                                  直接选择适合当前 PPT 的模板风格。这里展示的是系统内可稳定使用的模板，不再依赖外部预览页。
                              </div>
                              <div className="flex-1 overflow-y-auto bg-gray-50 dark:bg-slate-950/70 p-5">
                                  {isTemplateCatalogLoading ? (
                                      <div className="flex min-h-[320px] items-center justify-center rounded-2xl border border-dashed border-gray-300 bg-white/70 text-sm text-gray-500 dark:border-slate-700 dark:bg-slate-900/60 dark:text-gray-400">
                                          正在加载模板目录...
                                      </div>
                                  ) : (
                                      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                                          {templatePreviewCatalog.map((item) => (
                                              <StandaloneTemplatePreviewCard
                                                  key={item.template_id}
                                                  template={item}
                                                  resolvePreviewMeta={getStandalonePptTemplatePreviewMeta}
                                                  resolveTemplateId={normalizeStandalonePptTemplateId}
                                                  resolveTemplateLabel={getStandalonePptTemplateLabel}
                                                  selected={
                                                      normalizeStandalonePptTemplateId(templatePreviewSelection?.templateId || "")
                                                      === normalizeStandalonePptTemplateId(item.template_id || "")
                                                  }
                                                  onSelect={(templateId) => {
                                                      const value = normalizeStandalonePptTemplateId(templateId || "");
                                                      setTemplatePreviewSelection({ routeId: value, templateId: value });
                                                  }}
                                              />
                                          ))}
                                      </div>
                                  )}
                              </div>
                              <div className="px-5 py-4 border-t border-gray-200 dark:border-slate-700 flex flex-wrap items-end justify-between gap-3">
                                  <div className="flex min-w-[280px] flex-1 items-center gap-2">
                                      <span className="text-xs text-gray-500 dark:text-gray-400 shrink-0">模板编号</span>
                                      <input
                                          className="w-full rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-gray-800 dark:text-gray-100 outline-none"
                                          placeholder="也可手动输入模板编号"
                                          value={templatePreviewSelection?.templateId || ""}
                                          onChange={(event) => {
                                              const value = normalizeStandalonePptTemplateId(event.target.value || "");
                                              setTemplatePreviewSelection({ routeId: value, templateId: value });
                                          }}
                                      />
                                  </div>
                                  <div className="flex items-center gap-2">
                                      <button
                                          type="button"
                                          onClick={closeTemplatePreviewPicker}
                                          className="rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-slate-800"
                                      >
                                          取消
                                      </button>
                                      <button
                                          type="button"
                                          onClick={handleApplyTemplateFromPreview}
                                          disabled={!templatePreviewSelection?.templateId}
                                          className="rounded-lg bg-emerald-500 hover:bg-emerald-600 text-white px-4 py-2 text-sm font-semibold disabled:opacity-60"
                                      >
                                          应用所选模板
                                      </button>
                                  </div>
                              </div>
                          </div>
                      </div>
                  )}

                  {isOutlineGenerating && (
                      <div className="fixed inset-0 z-[70] flex items-center justify-center p-4">
                          <div className="absolute inset-0 bg-black/45" />
                          <div className="relative w-full max-w-3xl rounded-2xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-2xl">
                              <div className="p-5">
                                  <div className="text-3xl font-semibold text-gray-900 dark:text-white">
                                                  AI正在整理内容结构...{Math.max(12, Math.round(progressValue))}%
                                  </div>
                                  <div className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                                      大纲内容生成时间约30秒-1分钟，内容可在生成完毕后自由编辑
                                  </div>
                                  <div className="mt-4 rounded-xl border border-gray-200 dark:border-slate-700 bg-gray-50 dark:bg-slate-950 max-h-[420px] overflow-y-auto p-4 space-y-2 custom-scrollbar">
                                      {visibleOutlineProgressLines.map((line, idx) => {
                                          const trimmed = String(line || '').trim();
                                          const isSectionLine = /^\d+\.\s/.test(trimmed);
                                          const isMetaLine = /^(标题|副标题|输入模式)：/.test(trimmed);
                                          const isBulletLine = /^\s*-\s*/.test(trimmed);
                                          return (
                                              <div
                                                  key={`outline-progress-preview-${idx}`}
                                                  className={[
                                                      "whitespace-pre-wrap text-sm leading-7",
                                                      isMetaLine
                                                          ? "font-semibold text-gray-900 dark:text-white"
                                                          : isSectionLine
                                                              ? "font-medium text-gray-800 dark:text-gray-100"
                                                              : isBulletLine
                                                                  ? "text-gray-600 dark:text-gray-300 pl-2"
                                                                  : "text-gray-700 dark:text-gray-200",
                                                  ].join(' ')}
                                              >
                                                  {trimmed}
                                                  {idx === visibleOutlineProgressLines.length - 1 && progressStatus === 'outline_generating' && (
                                                      <span className="ml-1 inline-block h-4 w-1 rounded bg-emerald-400 align-middle animate-pulse" />
                                                  )}
                                              </div>
                                          );
                                      })}
                                  </div>
                              </div>
                          </div>
                      </div>
                  )}

                  {isOutlineEditorOpen && hasOutline && (
                      <div className="fixed inset-0 z-[80] flex items-center justify-center p-3 md:p-5">
                          <div className="absolute inset-0 bg-black/50" onClick={() => setIsOutlineEditorOpen(false)} />
                          <div className="relative w-full max-w-[1320px] h-[min(88vh,900px)] rounded-2xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-2xl flex flex-col overflow-hidden">
                              <div className="px-5 py-4 border-b border-gray-200 dark:border-slate-700 flex items-center justify-between gap-2">
                                  <div className="flex items-center gap-2">
                                      <Sparkles size={18} className="text-emerald-500" />
                                      <div className="text-3xl font-semibold text-gray-900 dark:text-white">点击下方文字编辑内容</div>
                                      <div className="text-sm text-gray-500 dark:text-gray-400 ml-2">该内容由AI生成</div>
                                  </div>
                                  <button
                                      type="button"
                                      onClick={() => setIsOutlineEditorOpen(false)}
                                      className="rounded-lg border border-gray-200 dark:border-slate-700 p-2 text-gray-500 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-slate-800"
                                  >
                                      <X size={20} />
                                  </button>
                              </div>

                              <div className="flex-1 min-h-0 p-4">
                                  <div className="grid h-full grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,0.95fr)]">
                                      <div className="rounded-xl border border-gray-200 dark:border-slate-700 bg-gray-50/80 dark:bg-slate-800/60 p-3 overflow-hidden flex flex-col">
                                          <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                                              <input
                                                  className={textInputClass}
                                                  placeholder="大纲标题"
                                                  value={standalonePptOutline?.title || ""}
                                                  onChange={(event) => setStandalonePptOutline((prev) => ({ ...(prev || {}), title: event.target.value }))}
                                              />
                                              <input
                                                  className={textInputClass}
                                                  placeholder="副标题（可选）"
                                                  value={standalonePptOutline?.subtitle || ""}
                                                  onChange={(event) => setStandalonePptOutline((prev) => ({ ...(prev || {}), subtitle: event.target.value }))}
                                              />
                                          </div>
                                          <div className="mt-3 flex-1 overflow-y-auto space-y-3 custom-scrollbar pr-1">
                                              {standalonePptOutline.slides.map((slide, idx) => (
                                                  <div key={`outline-modal-slide-${idx}`} className="rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-3">
                                                      <div className="mb-2 flex items-center justify-between">
                                                          <div className="text-xs font-semibold text-emerald-700 dark:text-emerald-300">第 {idx + 1} 页</div>
                                                          <div className="flex items-center gap-2">
                                                              <button
                                                                  type="button"
                                                                  onClick={addStandaloneOutlineSlide}
                                                                  className="text-gray-500 dark:text-gray-300 hover:text-gray-800 dark:hover:text-white"
                                                                  title="新增页"
                                                              >
                                                                  <Plus size={16} />
                                                              </button>
                                                              <button
                                                                  type="button"
                                                                  onClick={() => removeStandaloneOutlineSlide(idx)}
                                                                  className="text-red-500 hover:text-red-600"
                                                                  title="删除页"
                                                              >
                                                                  <Trash2 size={16} />
                                                              </button>
                                                          </div>
                                                      </div>
                                                      <input
                                                          className={textInputClass}
                                                          placeholder="页面标题"
                                                          value={slide.title || ""}
                                                          onChange={(event) => updateStandaloneOutlineSlide(idx, (prevSlide) => ({ ...prevSlide, title: event.target.value }))}
                                                      />
                                                      <textarea
                                                          className={`${textInputClass} mt-2 min-h-[94px] resize-y`}
                                                          placeholder="每行一个要点"
                                                          value={(Array.isArray(slide.points) ? slide.points : []).join('\n')}
                                                          onChange={(event) => {
                                                              const points = String(event.target.value || "")
                                                                  .split('\n')
                                                                  .map((item) => item.trim())
                                                                  .filter(Boolean);
                                                              updateStandaloneOutlineSlide(idx, (prevSlide) => ({
                                                                  ...prevSlide,
                                                                  points: points.length ? points : [""],
                                                              }));
                                                          }}
                                                      />
                                                      <textarea
                                                          className={`${textInputClass} mt-2 min-h-[72px] resize-y`}
                                                          placeholder="讲解备注（可选）"
                                                          value={slide.notes || ""}
                                                          onChange={(event) => updateStandaloneOutlineSlide(idx, (prevSlide) => ({ ...prevSlide, notes: event.target.value }))}
                                                      />
                                                  </div>
                                              ))}
                                          </div>
                                      </div>

                                      <div className="rounded-xl border border-gray-200 dark:border-slate-700 bg-gray-50/80 dark:bg-slate-800/60 p-3 overflow-hidden flex flex-col">
                                          <div className="mb-2 text-3xl font-semibold text-gray-900 dark:text-white">修改建议</div>
                                          <div className="flex-1 overflow-y-auto custom-scrollbar space-y-3 pr-1">
                                              {standalonePptOutline.slides.map((slide, idx) => (
                                                  <div key={`outline-suggestion-${idx}`} className="rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-3">
                                                      <div className="flex items-start justify-between gap-3">
                                                          <div>
                                                              <div className="text-xs font-semibold text-emerald-700 dark:text-emerald-300">第 {idx + 1} 页</div>
                                                              <div className="mt-1 text-lg font-medium text-gray-900 dark:text-white">{slide.title || `第 ${idx + 1} 页`}</div>
                                                          </div>
                                                          <div className="rounded-full border border-gray-200 dark:border-slate-700 px-2 py-1 text-[11px] text-gray-500 dark:text-gray-400">
                                                              {editorFocusConfig.label}
                                                          </div>
                                                      </div>
                                                      <div className="mt-3 space-y-2">
                                                          {buildStandaloneOutlineRevisionSuggestions(slide, idx, standalonePptOutline.slides, editorFocusConfig).map((suggestion) => (
                                                              <div key={`outline-suggestion-${idx}-${suggestion.code}`} className="rounded-lg border border-gray-200 dark:border-slate-700 bg-gray-50 dark:bg-slate-800/60 px-3 py-2">
                                                                  <div className="text-sm text-gray-700 dark:text-gray-200">{suggestion.text}</div>
                                                                  <div className="mt-2 flex justify-end">
                                                                      <button
                                                                          type="button"
                                                                          onClick={() => applyStandaloneOutlineSuggestion(idx, suggestion.code)}
                                                                          className="rounded-lg border border-emerald-300 text-emerald-600 dark:text-emerald-300 px-3 py-1.5 text-sm hover:bg-emerald-50 dark:hover:bg-emerald-900/30"
                                                                      >
                                                                          采用建议
                                                                      </button>
                                                                  </div>
                                                              </div>
                                                          ))}
                                                      </div>
                                                  </div>
                                              ))}
                                          </div>
                                      </div>
                                  </div>
                              </div>

                              <div className="px-5 py-4 border-t border-gray-200 dark:border-slate-700 flex items-center justify-end gap-2">
                                  <button
                                      type="button"
                                      onClick={handleGeneratePresentonPpt}
                                      disabled={isPresentonGenerating || isOutlineGenerating || !hasOutline}
                                      className="rounded-lg bg-emerald-500 hover:bg-emerald-600 text-white px-6 py-2 text-sm font-semibold disabled:opacity-60"
                                  >
                                      生成PPT
                                  </button>
                              </div>
                          </div>
                      </div>
                  )}
              </div>
          </div>
      );
  };

  const renderReportWizard = () => {
      const activeType = reportType || 'report';
      const backend = reportFormData.modelBackend || llmBackend;
      const tabs = [
          { key: 'report', label: '创意内容生成', desc: '营销文案、功能发布', icon: FileText, activeClass: 'bg-blue-50 text-blue-700 border-blue-300 dark:bg-blue-900/30 dark:text-blue-200 dark:border-blue-500/50' },
          { key: 'ppt', label: 'PPT内容策划', desc: '按演示结构生成内容', icon: Layout, activeClass: 'bg-indigo-50 text-indigo-700 border-indigo-300 dark:bg-indigo-900/30 dark:text-indigo-200 dark:border-indigo-500/50' },
          { key: 'email', label: '建议/咨询', desc: '面向团队的落地方案', icon: Mail, activeClass: 'bg-emerald-50 text-emerald-700 border-emerald-300 dark:bg-emerald-900/30 dark:text-emerald-200 dark:border-emerald-500/50' },
      ];
      const activeMeta = tabs.find((item) => item.key === activeType) || tabs[0];
      const labelClass = 'text-sm font-medium text-gray-700 dark:text-gray-200';
      const inputClass = 'w-full rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2.5 text-sm text-gray-800 dark:text-gray-100 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/10';
      const textareaClass = `${inputClass} min-h-[110px] resize-y`;
      const writingSuggestions = WRITING_FIELD_SUGGESTIONS[activeType] || {};
      const audiences = Array.isArray(reportFormData.targetAudiences) ? reportFormData.targetAudiences : [];
      const selectedPptFocus = getStandalonePptContentFocusConfig(reportFormData.contentFocus || STANDALONE_PPT_DEFAULT_CONTENT_FOCUS);

      const updateField = (field, value) => {
          setReportFormData((prev) => ({ ...prev, [field]: value }));
      };

      const previewRows = activeType === 'report'
          ? [
              ['我要写一个', reportFormData.contentType || WRITING_CONTENT_TYPE_OPTIONS[0]],
              ['发布平台', reportFormData.platform || WRITING_PLATFORM_OPTIONS[0]],
              ['目标人群', audiences.length ? audiences.join('、') : '未填写'],
              ['语气风格', reportFormData.tone || WRITING_TONE_OPTIONS[0]],
              ['最少字数', `${Math.max(100, Number(reportFormData.minWords) || 200)} 字`],
            ]
          : activeType === 'ppt'
              ? [
                  ['内容导向', selectedPptFocus.label],
                  ['最少字数', `${Math.max(200, Number(reportFormData.analysisMinWords) || 350)} 字`],
                  ['信息输入', reportFormData.analysisInput ? `已填写 ${String(reportFormData.analysisInput).length} 字` : '未填写'],
                  ['内容提示', selectedPptFocus.description],
                ]
              : [
                  ['咨询类型', reportFormData.consultingType || WRITING_CONSULTING_TYPE_OPTIONS[0]],
                  ['面向角色', reportFormData.consultingRole || WRITING_CONSULTING_ROLE_OPTIONS[0]],
                  ['输出形式', reportFormData.outputFormat || WRITING_OUTPUT_FORMAT_OPTIONS[0]],
                  ['最少字数', `${Math.max(200, Number(reportFormData.consultingMinWords) || 300)} 字`],
                ];

      if (reportStep === 'selection') {
          return (
              <div className="h-full w-full overflow-y-auto bg-gradient-to-br from-gray-100 via-white to-blue-50/40 dark:from-gray-950 dark:via-gray-950 dark:to-gray-900 px-4 py-6 md:px-8 md:py-8">
                  <div className="max-w-6xl mx-auto">
                      <div className="mb-4">
                          <button
                              type="button"
                              onClick={() => {
                                  setWritingEntryMode('root');
                                  setReportStep('selection');
                                  setReportType(null);
                                  setReportFormData({});
                                  setReportAudienceInput('');
                              }}
                              className="inline-flex items-center gap-1 rounded-xl border border-gray-200 dark:border-gray-700 px-3 py-2 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
                          >
                              <ArrowLeft size={14} /> 返回上一级
                          </button>
                      </div>
                      <div className="rounded-3xl border border-gray-200 dark:border-gray-800 bg-white/90 dark:bg-gray-900/85 shadow-sm px-6 py-7 mb-6">
                          <div className="inline-flex items-center gap-2 rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700 dark:border-blue-500/40 dark:bg-blue-900/30 dark:text-blue-200">
                              <Sparkles size={14} /> 写作助手
                          </div>
                          <h2 className="mt-3 text-2xl font-bold text-gray-900 dark:text-white">请选择生成场景</h2>
                          <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">内容会自动结合你的项目背景和进出口企业业务语境。</p>
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                          {tabs.map((item) => {
                              const Icon = item.icon;
                              return (
                                  <button
                                      key={item.key}
                                      type="button"
                                      onClick={() => applyReportType(item.key)}
                                      className="rounded-3xl border border-gray-200 dark:border-gray-700 bg-white/95 dark:bg-gray-900/80 p-6 text-left hover:shadow-lg hover:-translate-y-0.5 transition-all"
                                  >
                                      <div className="inline-flex rounded-xl border border-gray-200 dark:border-gray-700 p-2.5 text-gray-700 dark:text-gray-300">
                                          <Icon size={20} />
                                      </div>
                                      <div className="mt-4 text-lg font-semibold text-gray-900 dark:text-white">{item.label}</div>
                                      <div className="mt-1 text-sm text-gray-500 dark:text-gray-400">{item.desc}</div>
                                      <div className="mt-4 inline-flex items-center gap-1 text-xs font-semibold text-gray-700 dark:text-gray-300">
                                          进入配置 <ArrowRight size={14} />
                                      </div>
                                  </button>
                              );
                          })}
                      </div>
                  </div>
              </div>
          );
      }

      if (reportStep !== 'form') return null;

      return (
          <div className="h-full w-full overflow-y-auto bg-gradient-to-br from-gray-100 via-white to-indigo-50/40 dark:from-gray-950 dark:via-gray-950 dark:to-gray-900 px-3 py-4 md:px-6 md:py-6">
              <div className="max-w-[1320px] mx-auto space-y-4">
                  <div className="rounded-3xl border border-gray-200 dark:border-gray-800 bg-white/90 dark:bg-gray-900/85 shadow-sm p-4 md:p-5">
                      <div className="flex flex-wrap items-center gap-2 justify-between">
                          <button
                              type="button"
                              onClick={() => setReportStep('selection')}
                              className="inline-flex items-center gap-1 rounded-xl border border-gray-200 dark:border-gray-700 px-3 py-2 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
                          >
                              <ArrowLeft size={14} /> 返回场景
                          </button>
                          <select
                              className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-700 dark:text-gray-200"
                              value={backend}
                              onChange={(event) => updateField('modelBackend', event.target.value)}
                          >
                              <option value="local">本地模型（Qwen 2.5-coder）</option>
                              <option value="cloud">云端模型（DeepSeek）</option>
                          </select>
                      </div>
                      <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-2">
                          {tabs.map((item) => {
                              const active = item.key === activeType;
                              const Icon = item.icon;
                              return (
                                  <button
                                      key={item.key}
                                      type="button"
                                      onClick={() => applyReportType(item.key)}
                                      className={`rounded-2xl border px-4 py-3 text-left transition-all ${active ? item.activeClass : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-gray-600 dark:text-gray-300 hover:border-gray-300 dark:hover:border-gray-600'}`}
                                  >
                                      <div className="flex items-center gap-2 text-sm font-semibold">
                                          <Icon size={16} /> {item.label}
                                      </div>
                                      <div className="mt-1 text-xs opacity-80">{item.desc}</div>
                                  </button>
                              );
                          })}
                      </div>
                  </div>

                  <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.15fr)_minmax(340px,0.85fr)] gap-4">
                      <div className="rounded-3xl border border-gray-200 dark:border-gray-800 bg-white/95 dark:bg-gray-900/90 shadow-sm p-4 md:p-6 space-y-4">
                          {activeType === 'report' && (
                              <>
                                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                      <label className="space-y-1.5"><span className={labelClass}>我要写一个</span><select className={inputClass} value={reportFormData.contentType || WRITING_CONTENT_TYPE_OPTIONS[0]} onChange={(event) => updateField('contentType', event.target.value)}>{WRITING_CONTENT_TYPE_OPTIONS.map((item) => <option key={item}>{item}</option>)}</select></label>
                                      <label className="space-y-1.5"><span className={labelClass}>想发布的平台是</span><select className={inputClass} value={reportFormData.platform || WRITING_PLATFORM_OPTIONS[0]} onChange={(event) => updateField('platform', event.target.value)}>{WRITING_PLATFORM_OPTIONS.map((item) => <option key={item}>{item}</option>)}</select></label>
                                  </div>
                                  <div className="space-y-2">
                                      <span className={labelClass}>目标人群类型是</span>
                                      <div className="min-h-[44px] rounded-xl border border-gray-200 dark:border-gray-700 px-3 py-2 flex flex-wrap gap-2 items-center">
                                          {audiences.length === 0 && <span className="text-sm text-gray-400 dark:text-gray-500">暂未添加目标人群</span>}
                                          {audiences.map((tag) => (
                                              <span key={tag} className="inline-flex items-center gap-1 rounded-lg bg-blue-50 dark:bg-blue-900/35 text-blue-700 dark:text-blue-200 px-2 py-1 text-xs">{tag}<button type="button" onClick={() => removeAudienceTag(tag)}><X size={12} /></button></span>
                                          ))}
                                      </div>
                                      <div className="flex flex-col sm:flex-row gap-2">
                                          <input className={inputClass} value={reportAudienceInput} placeholder="输入后回车或点击添加" onChange={(event) => setReportAudienceInput(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); addAudienceTag(reportAudienceInput); } }} />
                                          <button type="button" onClick={() => addAudienceTag(reportAudienceInput)} className="rounded-xl border border-gray-200 dark:border-gray-700 px-3 py-2 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800">添加目标人群</button>
                                          <span className="inline-flex items-center justify-center rounded-xl border border-gray-200 dark:border-gray-700 px-3 py-2 text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">{audiences.length} / {WRITING_FORM_AUDIENCE_LIMIT}</span>
                                      </div>
                                  </div>
                                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                      <label className="space-y-1.5"><span className={labelClass}>语气或风格是</span><select className={inputClass} value={reportFormData.tone || WRITING_TONE_OPTIONS[0]} onChange={(event) => updateField('tone', event.target.value)}>{WRITING_TONE_OPTIONS.map((item) => <option key={item}>{item}</option>)}</select></label>
                                      <label className="space-y-1.5"><span className={labelClass}>字数不少于(字)</span><input type="number" min={100} max={5000} className={inputClass} value={reportFormData.minWords ?? 200} onChange={(event) => updateField('minWords', event.target.value)} /></label>
                                  </div>
                                  <label className="space-y-1.5 block">
                                      <span className={labelClass}>参考这些内容</span>
                                      <textarea className={textareaClass} maxLength={1200} placeholder={writingSuggestions.referenceContent || '选填。可输入你希望模型重点参考的业务背景、卖点、素材。'} value={reportFormData.referenceContent || ''} onChange={(event) => updateField('referenceContent', event.target.value)} />
                                      <span className="block text-right text-xs text-gray-400 dark:text-gray-500">{String(reportFormData.referenceContent || '').length} / 1200</span>
                                  </label>
                                  <label className="space-y-1.5 block">
                                      <span className={labelClass}>包含这些关键词</span>
                                      <textarea className={textareaClass} maxLength={300} placeholder={writingSuggestions.keywords || '选填。多个关键词可用逗号分隔。'} value={reportFormData.keywords || ''} onChange={(event) => updateField('keywords', event.target.value)} />
                                      <span className="block text-right text-xs text-gray-400 dark:text-gray-500">{String(reportFormData.keywords || '').length} / 300</span>
                                  </label>
                                  <label className="inline-flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300"><input type="checkbox" checked={!!reportFormData.withEmoji} onChange={(event) => updateField('withEmoji', event.target.checked)} className="h-4 w-4 rounded border-gray-300 dark:border-gray-600" />带一点emoji</label>
                              </>
                          )}

                          {activeType === 'ppt' && (
                              <>
                                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                      <label className="space-y-1.5"><span className={labelClass}>内容导向</span><select className={inputClass} value={selectedPptFocus.key} onChange={(event) => {
                                          const nextFocus = getStandalonePptContentFocusConfig(event.target.value);
                                          setReportFormData((prev) => ({
                                              ...prev,
                                              contentFocus: nextFocus.key,
                                              requireMetrics: !!nextFocus.emphasizeMetrics,
                                          }));
                                      }}>{STANDALONE_PPT_CONTENT_FOCUS_OPTIONS.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}</select></label>
                                      <label className="space-y-1.5"><span className={labelClass}>字数不少于(字)</span><input type="number" min={200} max={5000} className={inputClass} value={reportFormData.analysisMinWords ?? 350} onChange={(event) => updateField('analysisMinWords', event.target.value)} /></label>
                                  </div>
                                  <label className="space-y-1.5 block">
                                      <span className={labelClass}>相关信息输入</span>
                                      <textarea className={textareaClass} maxLength={2000} placeholder={writingSuggestions.analysisInput || '选填。输入汇报主题、业务背景、现状问题、目标和希望重点展开的方向。'} value={reportFormData.analysisInput || ''} onChange={(event) => updateField('analysisInput', event.target.value)} />
                                      <span className="block text-right text-xs text-gray-400 dark:text-gray-500">{String(reportFormData.analysisInput || '').length} / 2000</span>
                                  </label>
                                  <label className="inline-flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300"><input type="checkbox" checked={!!reportFormData.requireMetrics} onChange={(event) => updateField('requireMetrics', event.target.checked)} className="h-4 w-4 rounded border-gray-300 dark:border-gray-600" />要求结合丰富的数据指标</label>
                              </>
                          )}

                          {activeType === 'email' && (
                              <>
                                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                      <label className="space-y-1.5"><span className={labelClass}>咨询类型</span><select className={inputClass} value={reportFormData.consultingType || WRITING_CONSULTING_TYPE_OPTIONS[0]} onChange={(event) => updateField('consultingType', event.target.value)}>{WRITING_CONSULTING_TYPE_OPTIONS.map((item) => <option key={item}>{item}</option>)}</select></label>
                                      <label className="space-y-1.5"><span className={labelClass}>面向角色</span><select className={inputClass} value={reportFormData.consultingRole || WRITING_CONSULTING_ROLE_OPTIONS[0]} onChange={(event) => updateField('consultingRole', event.target.value)}>{WRITING_CONSULTING_ROLE_OPTIONS.map((item) => <option key={item}>{item}</option>)}</select></label>
                                  </div>
                                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                      <label className="space-y-1.5"><span className={labelClass}>输出形式</span><select className={inputClass} value={reportFormData.outputFormat || WRITING_OUTPUT_FORMAT_OPTIONS[0]} onChange={(event) => updateField('outputFormat', event.target.value)}>{WRITING_OUTPUT_FORMAT_OPTIONS.map((item) => <option key={item}>{item}</option>)}</select></label>
                                      <label className="space-y-1.5"><span className={labelClass}>字数不少于(字)</span><input type="number" min={200} max={5000} className={inputClass} value={reportFormData.consultingMinWords ?? 300} onChange={(event) => updateField('consultingMinWords', event.target.value)} /></label>
                                  </div>
                                  <label className="space-y-1.5 block">
                                      <span className={labelClass}>业务背景描述</span>
                                      <textarea className={textareaClass} maxLength={1600} placeholder={writingSuggestions.consultingContext || '选填。输入当前业务场景、目标问题和希望达成的效果。'} value={reportFormData.consultingContext || ''} onChange={(event) => updateField('consultingContext', event.target.value)} />
                                      <span className="block text-right text-xs text-gray-400 dark:text-gray-500">{String(reportFormData.consultingContext || '').length} / 1600</span>
                                  </label>
                                  <label className="space-y-1.5 block">
                                      <span className={labelClass}>约束条件/限制</span>
                                      <textarea className={textareaClass} maxLength={1000} placeholder={writingSuggestions.consultingConstraints || '选填。输入预算、时间、合规、系统兼容等限制条件。'} value={reportFormData.consultingConstraints || ''} onChange={(event) => updateField('consultingConstraints', event.target.value)} />
                                      <span className="block text-right text-xs text-gray-400 dark:text-gray-500">{String(reportFormData.consultingConstraints || '').length} / 1000</span>
                                  </label>
                                  <label className="inline-flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300"><input type="checkbox" checked={!!reportFormData.includeTimeline} onChange={(event) => updateField('includeTimeline', event.target.checked)} className="h-4 w-4 rounded border-gray-300 dark:border-gray-600" />需要分阶段时间表</label>
                              </>
                          )}

                          <div className="pt-4 border-t border-gray-200 dark:border-gray-700 flex items-center justify-end gap-2">
                              <button type="button" onClick={clearCurrentWritingForm} className="rounded-xl border border-gray-200 dark:border-gray-700 px-4 py-2 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800">一键清空</button>
                              <button type="button" onClick={handleSubmitReportForm} className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium text-white ${activeType === 'report' ? 'bg-blue-600 hover:bg-blue-700' : (activeType === 'ppt' ? 'bg-indigo-600 hover:bg-indigo-700' : 'bg-emerald-600 hover:bg-emerald-700')}`}><Sparkles size={15} />立即生成</button>
                          </div>
                      </div>

                      <div className="rounded-3xl border border-gray-200 dark:border-gray-800 bg-white/95 dark:bg-gray-900/90 shadow-sm p-4 md:p-5">
                          <div className="flex items-center justify-between">
                              <div>
                                  <p className="text-sm font-semibold text-gray-900 dark:text-white">{activeMeta.label}</p>
                                  <p className="text-xs text-gray-500 dark:text-gray-400">Powered by AIGC</p>
                              </div>
                              <span className="inline-flex items-center rounded-lg border border-gray-200 dark:border-gray-700 px-2 py-1 text-xs text-gray-500 dark:text-gray-400">{backend === 'cloud' ? '云端模型' : '本地模型'}</span>
                          </div>
                          <div className="mt-4 rounded-2xl border border-gray-200 dark:border-gray-700 bg-gray-50/80 dark:bg-gray-800/60 p-4 space-y-3">
                              {previewRows.map(([label, value]) => (
                                  <div key={label}>
                                      <div className="text-xs text-gray-500 dark:text-gray-400">{label}</div>
                                      <div className="text-sm text-gray-900 dark:text-gray-100 leading-relaxed">{value}</div>
                                  </div>
                              ))}
                          </div>
                          <div className="mt-4 rounded-2xl border border-blue-100 dark:border-blue-900/40 bg-blue-50/70 dark:bg-blue-900/25 p-4 text-sm text-blue-700 dark:text-blue-200 leading-relaxed">
                              点击“立即生成”后，会在对话区输出初稿。后续可继续追问细化，保持当前所有写作功能不变。
                          </div>
                      </div>
                  </div>
              </div>
          </div>
      );
  };

  const renderWritingWorkspace = () => {
      if (writingEntryMode === 'assistant') return renderReportWizard();
      if (writingEntryMode === 'ppt') return renderStandalonePptGenerator();
      return (
          <WritingEntryHub
              onOpenAssistant={handleOpenWritingAssistantEntry}
              onOpenPptGenerator={handleOpenStandalonePptEntry}
          />
      );
  };

  const panelStyle = useMemo(() => {
      if (isMeetingMode) return { border: 'border-gray-200 dark:border-gray-800', headerBg: 'bg-gray-50/80 dark:bg-gray-900/60', headerText: 'text-gray-800 dark:text-gray-200', btnBg: 'bg-gray-900 hover:bg-black', textareaBg: 'bg-white/60 dark:bg-gray-900/60' };
      if (isAuditMode) return { border: 'border-teal-100 dark:border-teal-900/50', headerBg: 'bg-teal-50/50 dark:bg-teal-900/20', headerText: 'text-teal-800 dark:text-teal-300', btnBg: 'bg-teal-600 hover:bg-teal-700', textareaBg: 'bg-white/50 dark:bg-gray-900/50' };
      return { border: 'border-orange-100 dark:border-orange-900/50', headerBg: 'bg-orange-50/50 dark:bg-orange-900/20', headerText: 'text-orange-800 dark:text-orange-300', btnBg: 'bg-orange-600 hover:bg-orange-700', textareaBg: 'bg-white/50 dark:bg-gray-900/50' };
  }, [isMeetingMode, isAuditMode]);
  const showEmptyState = chatHistory.length === 0 && !showContentPanel && !panelContent && !isUploadingFile && pendingFiles.length === 0;
  const greetingName = userProfile?.name && userProfile.name !== 'User' ? userProfile.name : '';
  const greetingText = greetingName ? `${greetingName}，你好` : '你好';
  const emptyStateContent = (
    <DashboardEmptyState
      isMobileViewport={isMobileViewport}
      greetingText={greetingText}
      selectedModelInfo={selectedModelInfo}
      isMeetingMode={isMeetingMode}
      isAuditMode={isAuditMode}
      isOCRMode={isOCRMode}
      onQuickAction={handleEmptyStateQuickAction}
      onSuggestionClick={handleSuggestionClickStable}
    />
  );

  const renderOcrWorkspace = () => {
    const activeFile = activeOcrFile;
    const activeFileType = activeFile?.fileType || activeFile?.type || '';
    const isPdf = activeFile && (activeFileType === 'application/pdf' || (activeFile.name || '').toLowerCase().endsWith('.pdf'));
    const ocrLines = getOcrLines(activeFile);
    const totalPages = Array.isArray(activeFile?.pages) && activeFile.pages.length > 0 ? activeFile.pages.length : 1;
    const pageIndex = Math.max(0, Math.min(ocrPageIndex, totalPages - 1));
    const pageLines = ocrLines
      .map((line, idx) => ({ ...line, __index: idx }))
      .filter((line) => {
        const linePage = line.page === undefined || line.page === null ? 0 : line.page;
        return linePage === pageIndex;
      });
    const jsonContent = activeFile?.jsonText ?? (activeFile?.ocrData ? JSON.stringify(activeFile.ocrData, null, 2) : '');
    const previewUrl = activeFile?.previewUrl || activeFile?.serverUrl || null;
    const pdfPreviewUrl = isPdf ? buildPdfPageUrl(previewUrl, pageIndex + 1) : previewUrl;
    const engineLabel = ocrEngine === 'vl' ? 'PaddleOCR-VL' : 'PP-OCRv5';
    const canUpload = !isUploadingFile;
    const pageMeta = Array.isArray(activeFile?.pages) ? activeFile.pages[pageIndex] : null;
    const selectedLine = selectedOcrLine !== null ? ocrLines[selectedOcrLine] : null;
    const previewPaneHiddenOnMobile = isMobileViewport && ocrMobileTab !== 'preview';
    const resultPaneHiddenOnMobile = isMobileViewport && ocrMobileTab !== 'result';

    const renderBoxes = () => {
      if (!activeFile || !pageMeta || !ocrImageMetrics.width || !ocrImageMetrics.height) return null;
      const scaleX = ocrImageMetrics.width / pageMeta.width;
      const scaleY = ocrImageMetrics.height / pageMeta.height;
      return (
        <div className="absolute inset-0 pointer-events-none">
          {ocrLines.map((line, idx) => {
            const linePage = line.page === undefined || line.page === null ? 0 : line.page;
            if (!line.box || linePage !== pageIndex) return null;
            const points = line.box || [];
            if (!Array.isArray(points) || points.length < 4) return null;
            const xs = points.map((p) => p[0]);
            const ys = points.map((p) => p[1]);
            const left = Math.min(...xs) * scaleX + ocrImageMetrics.offsetX;
            const top = Math.min(...ys) * scaleY + ocrImageMetrics.offsetY;
            const width = (Math.max(...xs) - Math.min(...xs)) * scaleX;
            const height = (Math.max(...ys) - Math.min(...ys)) * scaleY;
            const isActive = selectedOcrLine === idx;
            return (
              <div
                key={`box-${idx}`}
                className={`absolute border ${isActive ? 'border-blue-500 bg-blue-200/20' : 'border-amber-400/60'} rounded-sm`}
                style={{ left, top, width, height }}
              />
            );
          })}
        </div>
      );
    };

    const renderOcrPage = () => {
      return (
        <div ref={ocrRenderRef} className="w-full">
          {!activeFile && (
            <div className="text-xs text-gray-400 dark:text-gray-500">暂无渲染内容</div>
          )}
          {activeFile && pageMeta && ocrRenderSize.width > 0 && (
            (() => {
              const scale = ocrRenderSize.width / pageMeta.width;
              const renderHeight = pageMeta.height * scale;
              return (
                <div
                  className="relative w-full bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden"
                  style={{ height: `${Math.max(renderHeight, isMobileViewport ? 280 : 420)}px` }}
                  onMouseLeave={() => {
                    if (editingOcrLine === null) setSelectedOcrLine(null);
                  }}
                >
                  <canvas
                    ref={ocrCanvasRef}
                    className="block w-full"
                    onMouseMove={(e) => {
                      if (editingOcrLine !== null) return;
                      const canvas = ocrCanvasRef.current;
                      if (!canvas || !pageLines.length) return;
                      const rect = canvas.getBoundingClientRect();
                      const x = e.clientX - rect.left;
                      const y = e.clientY - rect.top;
                      const scale = rect.width / pageMeta.width;
                      const ox = x / scale;
                      const oy = y / scale;
                      const hit = pageLines.findIndex((line) => {
                        if (!line.box) return false;
                        const pts = line.box;
                        if (!Array.isArray(pts) || pts.length < 4) return false;
                        const xs = pts.map((p) => p[0]);
                        const ys = pts.map((p) => p[1]);
                        const left = Math.min(...xs);
                        const top = Math.min(...ys);
                        const right = Math.max(...xs);
                        const bottom = Math.max(...ys);
                        return ox >= left && ox <= right && oy >= top && oy <= bottom;
                      });
                      if (hit >= 0) {
                        const globalIndex = pageLines[hit].__index;
                        if (globalIndex !== selectedOcrLine) {
                          setSelectedOcrLine(globalIndex);
                        }
                      }
                    }}
                  />
                  {selectedOcrLine !== null && selectedLine && selectedLine.box && (
                    (() => {
                      const linePage = selectedLine.page === undefined || selectedLine.page === null ? 0 : selectedLine.page;
                      if (linePage !== pageIndex) return null;
                      const points = selectedLine.box || [];
                      if (!Array.isArray(points) || points.length < 4) return null;
                      const xs = points.map((p) => p[0]);
                      const ys = points.map((p) => p[1]);
                      const left = Math.min(...xs) * scale;
                      const top = Math.min(...ys) * scale;
                      const width = (Math.max(...xs) - Math.min(...xs)) * scale;
                      const height = (Math.max(...ys) - Math.min(...ys)) * scale;
                      return (
                        <div
                          className="absolute border-2 border-blue-500/70 bg-blue-200/15 rounded-sm pointer-events-none"
                          style={{ left, top, width, height }}
                        />
                      );
                    })()
                  )}
                  {selectedOcrLine !== null && selectedLine && selectedLine.box && (
                    (() => {
                      const linePage = selectedLine.page === undefined || selectedLine.page === null ? 0 : selectedLine.page;
                      if (linePage !== pageIndex) return null;
                      const points = selectedLine.box || [];
                      if (!Array.isArray(points) || points.length < 4) return null;
                      const xs = points.map((p) => p[0]);
                      const ys = points.map((p) => p[1]);
                      const left = Math.min(...xs) * scale;
                      const top = Math.min(...ys) * scale;
                      const width = (Math.max(...xs) - Math.min(...xs)) * scale;
                      return (
                        <div
                          className="absolute flex items-center gap-2 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-full shadow-md px-2 py-1 text-xs text-gray-700 dark:text-gray-200"
                          style={{ left: left + width + 8, top: Math.max(0, top - 4) }}
                        >
                          <button
                            type="button"
                            className="px-2 py-0.5 rounded-full hover:bg-gray-100 dark:hover:bg-gray-700/70"
                            onClick={() => {
                              navigator.clipboard.writeText(selectedLine.text || '');
                              showCopyToast();
                            }}
                          >
                            复制
                          </button>
                          <button
                            type="button"
                            className="px-2 py-0.5 rounded-full hover:bg-gray-100 dark:hover:bg-gray-700/70"
                            onClick={() => {
                              setEditingOcrLine(selectedOcrLine);
                              setEditingOcrValue(selectedLine.text || '');
                            }}
                          >
                            纠正
                          </button>
                        </div>
                      );
                    })()
                  )}
                </div>
              );
            })()
          )}
        </div>
      );
    };

    const showOcrProcessing = !!activeFile && activeFile.status === 'processing';

    return (
      <div className="flex-1 flex flex-col lg:flex-row h-full overflow-hidden bg-gray-50 dark:bg-gray-950 relative">
        <style>{`
          @keyframes ocrScanLine {
            0% { transform: translateY(-28px); opacity: 0; }
            15% { opacity: 1; }
            85% { opacity: 1; }
            100% { transform: translateY(160px); opacity: 0; }
          }
          @keyframes ocrPulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.03); }
          }
        `}</style>
        {copyToast && (
          <div className="absolute top-4 left-1/2 -translate-x-1/2 z-30">
            <div className="flex items-center gap-2 px-4 py-2 rounded-full bg-white dark:bg-gray-800 shadow-lg border border-gray-100 dark:border-gray-700 text-sm text-gray-700 dark:text-gray-200">
              <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-emerald-100 text-emerald-600 text-xs">✓</span>
              {copyToast}
            </div>
          </div>
        )}
        {isMobileViewport && (
          <div className="px-3 py-2 border-b border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900">
            <div className="grid grid-cols-2 gap-2 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50/90 dark:bg-gray-900/70 p-1">
              <button
                type="button"
                onClick={() => setOcrMobileTab('preview')}
                className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  ocrMobileTab === 'preview'
                    ? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-white shadow-sm'
                    : 'text-gray-500 dark:text-gray-400'
                }`}
              >
                Preview
              </button>
              <button
                type="button"
                onClick={() => setOcrMobileTab('result')}
                className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  ocrMobileTab === 'result'
                    ? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-white shadow-sm'
                    : 'text-gray-500 dark:text-gray-400'
                }`}
              >
                Result
              </button>
            </div>
          </div>
        )}
        <div className={`${previewPaneHiddenOnMobile ? 'hidden lg:flex' : 'flex'} flex-1 w-full lg:w-1/2 lg:border-r border-b lg:border-b-0 border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900 flex-col min-h-0`}>
          <div className="p-4 border-b border-gray-100 dark:border-gray-800 space-y-4">
            <div
              className={`max-w-[520px] mx-auto rounded-xl border-2 border-dashed px-3 py-3 text-center transition-colors cursor-pointer ${isDragActive ? 'border-blue-400 bg-blue-50 dark:bg-blue-900/20' : 'border-gray-200 dark:border-gray-700 hover:border-blue-300 dark:hover:border-blue-600'}`}
              onClick={() => fileInputRef.current && fileInputRef.current.click()}
            >
              <div className="mx-auto w-8 h-8 rounded-full bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-300 flex items-center justify-center mb-2">
                <FileUp size={16} />
              </div>
              <div className="text-sm font-medium text-gray-800 dark:text-gray-100">点击或拖拽上传文件</div>
              <div className="text-xs text-gray-400 dark:text-gray-500 mt-1">支持图片、PDF</div>
              <button
                type="button"
                disabled={!canUpload}
                className="mt-2 px-3 py-1.5 rounded-lg text-[11px] font-medium bg-black text-white dark:bg-white dark:text-black disabled:opacity-50 disabled:cursor-not-allowed"
              >
                选择文件
              </button>
            </div>

          </div>

          <div className="flex-1 min-h-0 overflow-auto p-4 pt-2">
            <div className="mb-2 rounded-2xl border border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900 overflow-hidden">
              <div className="px-3 py-2 border-b border-gray-100 dark:border-gray-800 bg-gray-50/70 dark:bg-gray-800/40">
                <span className="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium text-blue-600 dark:text-blue-300 bg-blue-50 dark:bg-blue-900/30">
                  源文件
                </span>
              </div>
              <div className="px-3 py-2 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 min-w-0">
                  <div className="w-9 h-9 rounded-lg bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-300 flex items-center justify-center">
                    {(activeFile?.fileType || activeFile?.type || '').startsWith('image/') ? <ImageIcon size={16} /> : <FileText size={16} />}
                  </div>
                  <div className="min-w-0">
                    <div className="text-xs font-medium text-gray-800 dark:text-gray-100 truncate">
                      {activeFile?.name || '暂无文件'}
                    </div>
                    {activeFile?.sizeLabel && (
                      <div className="text-[10px] text-gray-400 dark:text-gray-500">{activeFile.sizeLabel}</div>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2 text-gray-400 dark:text-gray-500">
                  <button
                    type="button"
                    disabled={!activeFile}
                    className="p-1.5 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-40"
                    title="收藏"
                  >
                    <Star size={16} />
                  </button>
                  <button
                    type="button"
                    disabled={!activeFile}
                    className="flex items-center gap-1 px-2 py-1 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800 text-xs text-gray-500 dark:text-gray-400 disabled:opacity-40"
                    title="语言"
                  >
                    <Globe size={14} />
                    默认(中日英)
                    <ChevronDown size={12} />
                  </button>
                </div>
              </div>
            </div>
            {!activeFile && (
              <div className="h-full flex items-center justify-center text-sm text-gray-400 dark:text-gray-500">暂无预览</div>
            )}
            {activeFile && (
              <div
                ref={ocrPreviewRef}
                className="w-full h-full min-h-[280px] sm:min-h-[420px] bg-gray-50 dark:bg-gray-900/70 rounded-2xl border border-gray-100 dark:border-gray-800 flex items-start justify-start overflow-hidden relative"
              >
                {!previewUrl && (
                  <div className="text-xs text-gray-400 dark:text-gray-500">历史记录不包含原图/原 PDF 预览</div>
                )}
                {previewUrl && isPdf ? (
                  <iframe key={pdfPreviewUrl} title={activeFile.name} src={pdfPreviewUrl} className="w-full h-full bg-white" />
                ) : previewUrl ? (
                  <>
                    <img
                      ref={ocrImageRef}
                      src={previewUrl}
                      alt={activeFile.name}
                      className="max-w-full max-h-full object-contain"
                      onLoad={() => {
                        if (ocrPreviewRef.current && ocrImageRef.current) {
                          const containerRect = ocrPreviewRef.current.getBoundingClientRect();
                          const imageRect = ocrImageRef.current.getBoundingClientRect();
                          setOcrImageMetrics({
                            width: imageRect.width,
                            height: imageRect.height,
                            offsetX: imageRect.left - containerRect.left,
                            offsetY: imageRect.top - containerRect.top
                          });
                        }
                      }}
                    />
                    {renderBoxes()}
                  </>
                ) : null}
              </div>
            )}
          </div>
        </div>

        <div className={`${resultPaneHiddenOnMobile ? 'hidden lg:flex' : 'flex'} flex-1 w-full lg:w-1/2 flex-col bg-white dark:bg-gray-900 min-w-0 min-h-0`}>
          <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-800 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative">
              <button
                type="button"
                onClick={() => setIsOcrEngineOpen((prev) => !prev)}
                className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-200 hover:text-gray-900 dark:hover:text-white"
              >
                解析结果 by {engineLabel} <ChevronDown size={16} className={`text-gray-400 transition-transform ${isOcrEngineOpen ? 'rotate-180' : ''}`} />
              </button>
              {isOcrEngineOpen && (
                <div className="absolute top-full left-0 mt-2 w-44 rounded-lg border border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-lg z-20">
                  <button
                    type="button"
                    onClick={() => { setOcrEngine('pp-ocrv5'); setIsOcrEngineOpen(false); }}
                    className={`w-full px-3 py-2 text-left text-xs hover:bg-gray-50 dark:hover:bg-gray-700/60 ${ocrEngine === 'pp-ocrv5' ? 'text-blue-600 dark:text-blue-300 font-semibold' : 'text-gray-600 dark:text-gray-300'}`}
                  >
                    PP-OCRv5
                  </button>
                  <button
                    type="button"
                    onClick={() => { setOcrEngine('vl'); setIsOcrEngineOpen(false); }}
                    className={`w-full px-3 py-2 text-left text-xs hover:bg-gray-50 dark:hover:bg-gray-700/60 ${ocrEngine === 'vl' ? 'text-blue-600 dark:text-blue-300 font-semibold' : 'text-gray-600 dark:text-gray-300'}`}
                  >
                    PaddleOCR-VL
                  </button>
                </div>
              )}
            </div>
            <div className="w-full sm:w-auto overflow-x-auto">
              <div className="flex items-center gap-2 min-w-max pb-1 sm:pb-0">
                <div className="flex items-center gap-1 rounded-lg bg-gray-100 dark:bg-gray-800 p-1 text-xs flex-shrink-0">
                  <button
                    type="button"
                    onClick={() => setOcrViewTab('match')}
                    className={`px-2 py-1 rounded-md ${ocrViewTab === 'match' ? 'bg-white dark:bg-gray-900 text-gray-900 dark:text-white shadow' : 'text-gray-500 dark:text-gray-400'}`}
                  >
                    OCR识别对应
                  </button>
                  <button
                    type="button"
                    onClick={() => setOcrViewTab('json')}
                    className={`px-2 py-1 rounded-md ${ocrViewTab === 'json' ? 'bg-white dark:bg-gray-900 text-gray-900 dark:text-white shadow' : 'text-gray-500 dark:text-gray-400'}`}
                  >
                    JSON
                  </button>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  {ocrViewTab === 'json' && (
                    <button
                      type="button"
                      onClick={() => {
                        navigator.clipboard.writeText(jsonContent || '');
                        showCopyToast();
                      }}
                      className="p-2 rounded-md border border-gray-200 dark:border-gray-700 text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800"
                      title="复制JSON"
                    >
                      <Copy size={16} />
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={handleOcrStoreFromActive}
                    className="p-2 rounded-md border border-gray-200 dark:border-gray-700 text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800"
                    title="录入数据库"
                  >
                    <Database size={16} />
                  </button>
                  <button
                    type="button"
                    onClick={triggerOcrReparse}
                    className="p-2 rounded-md border border-gray-200 dark:border-gray-700 text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800"
                    title="重新解析"
                  >
                    <RefreshCw size={16} />
                  </button>
                  <button
                    type="button"
                    onClick={handleOpenOcrSummary}
                    className="p-2 rounded-md border border-gray-200 dark:border-gray-700 text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800"
                    title="总结"
                  >
                    <Sparkles size={16} />
                  </button>
                  <div className="relative">
                    <button
                      type="button"
                      onClick={() => setIsOcrDownloadOpen((prev) => !prev)}
                      className="p-2 rounded-md border border-gray-200 dark:border-gray-700 text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800"
                      title="下载"
                    >
                      <Download size={16} />
                    </button>
                    {isOcrDownloadOpen && (
                      <div className="absolute right-0 top-full mt-2 w-44 rounded-xl border border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-lg z-20 overflow-hidden">
                        <button
                          type="button"
                          onClick={() => { setIsOcrDownloadOpen(false); downloadOcrFile('txt'); }}
                          className="w-full text-left px-3 py-2 text-xs hover:bg-gray-50 dark:hover:bg-gray-700/60 text-gray-600 dark:text-gray-300"
                        >
                          TXT
                          <div className="text-[10px] text-gray-400 dark:text-gray-500 mt-0.5">仅包含纯文本</div>
                        </button>
                        <button
                          type="button"
                          onClick={() => { setIsOcrDownloadOpen(false); downloadOcrFile('json'); }}
                          className="w-full text-left px-3 py-2 text-xs hover:bg-gray-50 dark:hover:bg-gray-700/60 text-gray-600 dark:text-gray-300"
                        >
                          JSON（文字识别）
                          <div className="text-[10px] text-gray-400 dark:text-gray-500 mt-0.5">包含文字与坐标信息</div>
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div className="flex-1 min-h-0 overflow-auto p-4 relative">
            {!activeFile && (
              <div className="h-full flex items-center justify-center text-sm text-gray-400 dark:text-gray-500">暂无识别结果</div>
            )}
            {showOcrProcessing && (
              <div className="absolute inset-0 z-20 flex items-center justify-center bg-white dark:bg-gray-900">
                <div className="flex flex-col items-center gap-3">
                  <div className="relative w-40 h-40">
                    <span className="absolute -top-1 -left-1 w-5 h-5 border-t-2 border-l-2 border-gray-900 dark:border-gray-200"></span>
                    <span className="absolute -top-1 -right-1 w-5 h-5 border-t-2 border-r-2 border-gray-900 dark:border-gray-200"></span>
                    <span className="absolute -bottom-1 -left-1 w-5 h-5 border-b-2 border-l-2 border-gray-900 dark:border-gray-200"></span>
                    <span className="absolute -bottom-1 -right-1 w-5 h-5 border-b-2 border-r-2 border-gray-900 dark:border-gray-200"></span>
                    <div className="absolute inset-6 rounded-xl border border-blue-200 dark:border-blue-700 bg-gradient-to-br from-blue-50 via-indigo-100 to-blue-200 dark:from-blue-900/40 dark:via-indigo-900/30 dark:to-blue-800/40 shadow-md animate-[ocrPulse_2s_ease-in-out_infinite]">
                      <div className="absolute top-3 left-3 w-10 h-1.5 rounded-full bg-white/90"></div>
                      <div className="absolute top-6 left-3 w-16 h-1.5 rounded-full bg-white/80"></div>
                      <div className="absolute top-9 left-3 w-12 h-1.5 rounded-full bg-white/70"></div>
                      <div className="absolute bottom-6 left-6 w-10 h-10 rotate-45 bg-white/85 rounded-sm"></div>
                      <div className="absolute bottom-4 right-6 w-6 h-6 bg-gray-800/60 rounded-full"></div>
                      <div className="absolute bottom-5 right-10 w-10 h-10 bg-indigo-600/70 rotate-45"></div>
                    </div>
                    <div className="absolute left-6 right-6 top-6 bottom-6 overflow-hidden rounded-xl">
                      <div className="absolute left-0 right-0 h-2 bg-gradient-to-r from-blue-300/0 via-blue-500/80 to-blue-300/0 blur-[1px]" style={{ animation: 'ocrScanLine 1.8s ease-in-out infinite' }}></div>
                    </div>
                  </div>
                  <div className="text-sm text-gray-700 dark:text-gray-200">正在解析内容...</div>
                </div>
              </div>
            )}
            {activeFile && ocrViewTab === 'match' && (
              <div className="space-y-3">
                {totalPages > 1 && (
                  <div className="flex items-center justify-between gap-2 flex-wrap text-xs text-gray-500">
                    <span>页码 {pageIndex + 1} / {totalPages}</span>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setOcrPageIndex((prev) => Math.max(0, prev - 1))}
                        disabled={pageIndex <= 0}
                        className="px-2 py-1 rounded-md border border-gray-200 dark:border-gray-700 disabled:opacity-40"
                      >
                        上一页
                      </button>
                      <button
                        type="button"
                        onClick={() => setOcrPageIndex((prev) => Math.min(totalPages - 1, prev + 1))}
                        disabled={pageIndex >= totalPages - 1}
                        className="px-2 py-1 rounded-md border border-gray-200 dark:border-gray-700 disabled:opacity-40"
                      >
                        下一页
                      </button>
                    </div>
                  </div>
                )}
                {activeFile.status === 'processing' && !showOcrProcessing && (
                  <div className="flex items-center gap-2 text-xs text-gray-500">
                    <Loader2 size={14} className="animate-spin" /> 正在识别中...
                  </div>
                )}
                {activeFile.status === 'error' && (
                  <div className="text-xs text-red-500">{activeFile.error || '识别失败'}</div>
                )}
                {ocrLines.length === 0 && activeFile.status === 'done' && (
                  <div className="text-xs text-gray-400 dark:text-gray-500">未检测到可识别文本</div>
                )}
                {editingOcrLine !== null && ocrLines[editingOcrLine] && (
                  <div className="sticky top-0 z-20 flex flex-wrap items-center gap-2 p-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white/95 dark:bg-gray-800/95 backdrop-blur shadow-sm">
                    <span className="text-xs text-gray-400 dark:text-gray-500">纠正文本</span>
                    <input
                      value={editingOcrValue}
                      onChange={(e) => setEditingOcrValue(e.target.value)}
                      className="flex-1 min-w-[140px] text-sm px-2 py-1 border border-gray-200 dark:border-gray-700 rounded-md bg-white dark:bg-gray-900"
                    />
                    <button
                      type="button"
                      className="text-xs px-2 py-1 rounded-md bg-blue-600 text-white"
                      onClick={() => {
                        updateOcrLine(activeFile.id, editingOcrLine, editingOcrValue.trim());
                        setEditingOcrLine(null);
                        setSelectedOcrLine(null);
                      }}
                    >
                      保存
                    </button>
                    <button
                      type="button"
                      className="text-xs px-2 py-1 rounded-md border border-gray-200 dark:border-gray-700"
                      onClick={() => setEditingOcrLine(null)}
                    >
                      取消
                    </button>
                  </div>
                )}
                {!showOcrProcessing && renderOcrPage()}
              </div>
            )}
            {activeFile && ocrViewTab === 'json' && (
              <div className="space-y-2">
                <textarea
                  value={jsonContent || ''}
                  onChange={(e) => {
                    if (!activeFile) return;
                    updateOcrEntry(activeFile.id, { jsonText: e.target.value });
                    if (jsonEditError) setJsonEditError('');
                  }}
                  onBlur={() => {
                    if (!activeFile) return;
                    const current = (activeFile.jsonText || '').trim();
                    if (!current) return;
                    try {
                      const parsed = JSON.parse(current);
                      updateOcrEntry(activeFile.id, { ocrData: parsed });
                      setJsonEditError('');
                    } catch {
                      setJsonEditError('JSON 格式错误，未保存到识别结果');
                    }
                  }}
                  className="w-full min-h-[320px] sm:min-h-[420px] text-[11px] leading-relaxed text-gray-600 dark:text-gray-300 whitespace-pre-wrap break-words bg-gray-50 dark:bg-gray-800/60 rounded-xl p-3 border border-gray-100 dark:border-gray-700 font-mono"
                  placeholder="暂无 JSON 数据"
                />
                {jsonEditError && (
                  <div className="text-xs text-red-500">{jsonEditError}</div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  };

  if (isInitialRouteLoading) {
    return <LoadingScreen text="正在恢复历史会话..." isVisible />;
  }

  return (
    <div className="dashboard-unified-dark flex h-screen bg-white dark:bg-gray-950 font-sans text-gray-900 dark:text-gray-100 overflow-hidden animate-in fade-in duration-500 transition-colors">
      <DashboardGlobalOverlays
        isDragActive={isDragActive}
        showOnboarding={showOnboarding}
        onboardingMessages={ONBOARDING_MESSAGES}
        onStartOnboarding={handleOnboardingStart}
      />
      <DashboardOcrSummaryModal
        isOpen={isOcrSummaryOpen}
        onClose={handleCloseOcrSummary}
        ocrSummaryFirstDone={ocrSummaryFirstDone}
        ocrSummaryBackend={ocrSummaryBackend}
        backendOptions={OCR_SUMMARY_BACKEND_OPTIONS}
        onBackendChange={setOcrSummaryBackend}
        isLoading={isOcrSummaryLoading}
        onRegenerate={handleRegenerateOcrSummary}
        scrollRef={ocrSummaryScrollRef}
        messages={ocrSummaryMessages}
        inputValue={ocrSummaryInput}
        onInputChange={setOcrSummaryInput}
        onSend={handleSendCurrentOcrSummaryMessage}
      />
      <Suspense fallback={null}>
        <TaskCenterPopover
          isOpen={isTaskCenterOpen}
          onClose={handleCloseTaskCenter}
        />
      </Suspense>
      <DashboardSidebars
        isMobileSidebarOpen={isMobileSidebarOpen}
        onCloseMobileSidebar={handleCloseMobileSidebar}
        isSidebarOpen={isSidebarOpen}
        onCloseSidebar={handleCloseSidebar}
        userProfile={userProfile}
        sessionList={sessionList}
        currentSessionId={currentSessionId}
        onSessionClick={handleSessionClickStable}
        onNewChat={handleNewChatStable}
        onLogout={handleLogoutStable}
        onShowAppearance={handleOpenSettingsModalStable}
        currentMode={currentMode}
        onModeChange={handleModeChangeStable}
        isProfileLoading={isProfileLoading}
        isSessionsLoading={isSessionsLoading}
        selectedModel={selectedModel}
      />

      <div className="dashboard-main-surface flex-1 flex flex-col h-full relative bg-white dark:bg-gray-950 min-w-0 transition-colors">
        <DashboardTopbar
          isSidebarOpen={isSidebarOpen}
          onOpenSidebar={handleOpenSidebar}
          onOpenMobileSidebar={handleOpenMobileSidebar}
          models={models}
          selectedModel={selectedModel}
          selectedModelInfo={selectedModelInfo}
          isDropdownOpen={isDropdownOpen}
          onToggleDropdown={handleToggleDesktopModelDropdown}
          onSelectDesktopModel={handleSelectDesktopModel}
          isMobileModelDropdownOpen={isMobileModelDropdownOpen}
          onToggleMobileModelDropdown={handleToggleMobileModelDropdown}
          onSelectMobileModel={handleSelectMobileModel}
          onOpenDecisionCenter={handleHeaderOpenDecisionCenter}
          onOpenTaskCenter={handleHeaderOpenTaskCenter}
          onGotoTaskCenter={handleHeaderGotoTaskCenter}
          isTaskCenterOpen={isTaskCenterOpen}
          currentSessionId={currentSessionId}
          onShareClick={handleShareClickStable}
          onNewChat={handleNewChatStable}
          dropdownRef={dropdownRef}
          mobileDropdownRef={mobileDropdownRef}
        />

        {/* UI 隐藏文件输入（共享） */}
        <input
          type="file"
          className="hidden"
          ref={fileInputRef}
          onChange={handleFileSelect}
          disabled={isUploadingFile}
          multiple
          accept={isMeetingMode ? "audio/*,.wav,.mp3,.m4a" : (isOCRMode ? "image/*,application/pdf" : (isAuditMode ? "image/*,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document" : "*/*"))}
        />

        {/* MA 主要内容 */}
        <div className="flex-1 flex flex-col md:flex-row overflow-hidden relative pt-14 md:pt-0">
            {isOCRMode ? (
                renderOcrWorkspace()
            ) : (
            <>
              {showMobileWorkspaceTabs && (
                <div className="dashboard-topbar md:hidden px-4 py-2 border-b border-gray-100 dark:border-gray-800 bg-white/95 dark:bg-gray-950/95">
                  <div className="grid grid-cols-2 gap-2 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50/90 dark:bg-gray-900/70 p-1">
                    <button
                      type="button"
                      onClick={() => setMobileWorkspaceTab('panel')}
                      className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                        mobileWorkspaceTab === 'panel'
                          ? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-white shadow-sm'
                          : 'text-gray-500 dark:text-gray-400'
                      }`}
                    >
                      {mobilePanelTabLabel}
                    </button>
                    <button
                      type="button"
                      onClick={() => setMobileWorkspaceTab('chat')}
                      className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                        mobileWorkspaceTab === 'chat'
                          ? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-white shadow-sm'
                          : 'text-gray-500 dark:text-gray-400'
                      }`}
                    >
                      对话
                    </button>
                  </div>
                </div>
              )}
              <DashboardModePanelHost
                  shouldRenderPanel={shouldRenderPanel}
                  isAuditSinglePane={isAuditSinglePane}
                  panelStyle={panelStyle}
                  isMeetingMode={isMeetingMode}
                  isOCRMode={isOCRMode}
                  isAuditMode={isAuditMode}
                  panelContent={panelContent}
                  setPanelContent={setPanelContent}
                  isUploadingFile={isUploadingFile}
                  audioFileUrl={audioFileUrl}
                  isProcessing={isProcessing}
                  isOcrSaving={isOcrSaving}
                  isSavingContext={isSavingContext}
                  handleManualSave={handleManualSaveStable}
                  handleExportWord={handleExportWordStable}
                  handleGenerateSummary={handleGenerateSummaryStable}
                  onOcrStore={handleOcrStoreStable}
                  ocrEngine={ocrEngine}
                  onOcrEngineChange={setOcrEngine}
                  auditState={auditState}
                  auditDocType={auditDocType}
                  auditDocTypes={AUDIT_DOC_TYPES}
                  auditModelBackend={auditModelBackend}
                  auditFile={auditFile}
                  auditNotice={auditNotice}
                  onAuditDocTypeChange={setAuditDocType}
                  onAuditModelBackendChange={setAuditModelBackend}
                  onAuditFileSelect={handleAuditFileSelectStable}
                  onAuditReset={resetAuditStateStable}
                  onAuditErpAction={handleAuditErpActionStable}
                  isAuditErpActionLoading={isAuditErpActionLoading}
                  fullWidth={isAuditSinglePane}
                  onMeetingUploadClick={handleMeetingUploadClickStable}
              />

              {shouldRenderChat && (
              <div className={`flex flex-col h-full relative transition-all duration-300 ${showContentPanel ? 'w-full md:w-1/2' : 'w-full'}`}>
                  {isReportMode && chatHistory.length === 0 ? (
                      renderWritingWorkspace()
                  ) : (
                      <>
                          <div
                            ref={chatScrollRef}
                            className={`flex-1 w-full custom-scrollbar ${
                              shouldLockSuggestionsScroll ? "overflow-y-hidden overscroll-none" : "overflow-y-auto overscroll-contain"
                            }`}
                          >
                          <div
                            className={`mx-auto w-full px-4 sm:px-0 ${showContentPanel ? 'max-w-full px-4' : 'max-w-3xl'}`}
                            style={chatContentStyle}
                          >
                            {chatHistory.length === 0 ? (
                              showChatSkeleton ? (
                                <div className="w-full space-y-4 px-4 py-6">
                                  <div className="h-4 w-2/3 bg-gray-100 dark:bg-gray-800 rounded animate-pulse"></div>
                                  <div className="h-4 w-5/6 bg-gray-100 dark:bg-gray-800 rounded animate-pulse"></div>
                                  <div className="h-4 w-1/2 bg-gray-100 dark:bg-gray-800 rounded animate-pulse"></div>
                                </div>
                              ) : (
                                showEmptyState && emptyStateContent
                              )
                            ) : (
                              <div className="w-full space-y-6">
                                {hasMoreMessages && (
                                  <div className="flex justify-center">
                                    <button
                                      onClick={handleLoadMoreMessages}
                                      disabled={isHistoryPageLoading}
                                      className="text-xs font-medium text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 px-3 py-1.5 rounded-full border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                                    >
                                      {isHistoryPageLoading ? '加载中...' : '加载更多'}
                                    </button>
                                  </div>
                                )}
                                {visibleMessages.map((msg, idx) => {
                                  const messageIndex = chatHistory.length - visibleMessages.length + idx;
                                  const messageRenderKey = msg?.id ?? msg?.clientMessageId ?? msg?.messageKey ?? messageIndex;
                                  const feedbackKey = msg.role === 'assistant' ? getMessageFeedbackKey(msg, messageIndex) : '';
                                  const allowMarkdown = msg.role === 'assistant'
                                    ? (messageIndex >= chatHistory.length - MARKDOWN_MESSAGE_COUNT || isLikelyMarkdown(msg?.content || ''))
                                    : (messageIndex >= chatHistory.length - MARKDOWN_MESSAGE_COUNT);
                                  const sourcesExpanded = !!expandedSources[messageIndex];
                                  const isUserMessage = msg.role === 'user';
                                  const isEditing = isUserMessage && editingMessageIndex === messageIndex;
                                  const isStreamingMessage = msg.role === 'assistant' && messageIndex === chatHistory.length - 1 && isProcessing;
                                  const userBubbleSize = isEditing ? 'w-full max-w-full' : 'max-w-[85%] sm:max-w-[80%]';
                                  const userBubblePadding = isEditing ? 'p-4' : 'py-2 px-3';
                                  return (
                                  <div key={messageRenderKey} className={`flex flex-col gap-1 ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
                                    <div className={`flex gap-4 ${msg.role === 'user' ? 'flex-row-reverse' : ''} group max-w-full w-full`}>
                                      <div className={`w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center border border-gray-100 dark:border-gray-700 ${msg.role === 'user' ? 'bg-white dark:bg-gray-800' : 'bg-green-500 text-white'}`}>
                                        {msg.role === 'user' ? <User size={16} className="text-gray-600 dark:text-gray-300"/> : <Bot size={16} />}
                                      </div>
                                      <div className="flex flex-col gap-1.5 max-w-full w-full">
                                          <div className={`rounded-2xl text-[16px] ${msg.role === 'user' ? `bg-[#f4f4f4] dark:bg-gray-800 text-gray-900 dark:text-white rounded-tr-sm self-end ${userBubbleSize} ${userBubblePadding}` : 'py-2 px-3 text-gray-800 dark:text-gray-200 w-full'}`}>
                                            {isEditing ? (
                                              <div className="w-full">
                                                {editingMessageAttachments.length > 0 && (
                                                  <div className="mb-2 flex flex-wrap gap-2">
                                                    {editingMessageAttachments.map((name, attachmentIndex) => (
                                                      <div key={`${name}-${attachmentIndex}`} className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 text-xs font-medium text-gray-700 dark:text-gray-200 shadow-sm">
                                                        <FileText size={14} className="text-gray-500" />
                                                        <span className="truncate max-w-[200px]">{name}</span>
                                                      </div>
                                                    ))}
                                                  </div>
                                                )}
                                                <textarea
                                                  value={editingMessageText}
                                                  onChange={(e) => setEditingMessageText(e.target.value)}
                                                  rows={3}
                                                  autoFocus
                                                  className="w-full bg-transparent resize-none outline-none text-[16px] leading-relaxed text-gray-900 dark:text-white"
                                                />
                                                <div className="mt-3 flex items-center justify-end gap-2">
                                                  <button
                                                    type="button"
                                                    onClick={handleEditMessageCancel}
                                                    className="px-3 py-1.5 rounded-full text-xs font-medium border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-white/70 dark:hover:bg-gray-700/60 transition-colors"
                                                  >
                                                    取消
                                                  </button>
                                                  <button
                                                    type="button"
                                                    onClick={handleEditMessageSend}
                                                    disabled={(!editingMessageText.trim() && editingMessageAttachments.length === 0) || isProcessing}
                                                    className="px-3 py-1.5 rounded-full text-xs font-medium bg-black text-white dark:bg-white dark:text-black disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                                                  >
                                                    发送
                                                  </button>
                                                </div>
                                              </div>
                                            ) : (
                                              <div data-message-content-id={messageIndex}>
                                                <StructuredContent content={isStreamingMessage ? (streamingAssistantText || msg.content || "") : msg.content} role={msg.role} enableMarkdown={allowMarkdown} streaming={isStreamingMessage} />
                                              </div>
                                            )}
                                            {msg.role === 'assistant' && msg.sources && msg.sources.length > 0 && (
                                              <div className="mt-1">
                                                <button
                                                  onClick={() => setExpandedSources((prev) => ({ ...prev, [messageIndex]: !prev[messageIndex] }))}
                                                  className="text-[11px] text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 transition-colors"
                                                >
                                                  {sourcesExpanded ? '收起数据来源' : '查看数据来源'}
                                                </button>
                                                {sourcesExpanded && (
                                                  <Suspense fallback={<div className="text-xs text-gray-400 mt-1">加载来源...</div>}>
                                                    <SourcePanel sources={msg.sources} />
                                                  </Suspense>
                                                )}
                                              </div>
                                            )}
                                          </div>

                                          {msg.role === 'user' && !isEditing && msg.content && (
                                            <div
                                              className={`flex items-center gap-1 self-end mt-0.5 transition-all duration-200 ${
                                                isMobileViewport
                                                  ? 'opacity-100 pointer-events-auto'
                                                  : 'opacity-0 translate-y-1 pointer-events-none group-hover:opacity-100 group-hover:translate-y-0 group-hover:pointer-events-auto'
                                              }`}
                                            >
                                              <button
                                                onClick={() => handleCopy(msg.content, messageIndex)}
                                                className={`p-1 rounded-md border border-gray-200 dark:border-gray-700 bg-white/90 dark:bg-gray-800 text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-white dark:hover:bg-gray-700 transition-colors ${copiedIdx === messageIndex ? 'text-green-500' : ''}`}
                                                title="复制内容"
                                              >
                                                {copiedIdx === messageIndex ? <Check size={12} /> : <Copy size={12} />}
                                              </button>
                                              <button
                                                onClick={() => handleEditMessageStart(messageIndex, msg.content)}
                                                disabled={isProcessing || isUploadingFile}
                                                className="p-1 rounded-md border border-gray-200 dark:border-gray-700 bg-white/90 dark:bg-gray-800 text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-white dark:hover:bg-gray-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                                                title="编辑消息"
                                              >
                                                <PencilLine size={12} />
                                              </button>
                                            </div>
                                          )}

                                          {/* ✨ 功能栏 (Action Bar) - 仅在 AI 回复下方显示 */}
                                          {msg.role === 'assistant' && !isProcessing && msg.content && (
                                              <div className="flex items-center gap-1.5 ml-1 mt-0.5 animate-in fade-in duration-300">
                                                  <button
                                                      onClick={() => handleSpeak(msg.content, messageIndex)}
                                                      className={`p-1.5 rounded-md transition-colors hover:bg-gray-100 dark:hover:bg-gray-800 ${speakingIdx === messageIndex ? 'text-blue-500 bg-blue-50 dark:bg-blue-900/20' : 'text-gray-400 dark:text-gray-500'}`}
                                                      title={speakingIdx === messageIndex ? "停止朗读" : "朗读"}
                                                  >
                                                      {speakingIdx === messageIndex ? <Square size={14} fill="currentColor"/> : <Volume2 size={14} />}
                                                  </button>

                                                  <button
                                                      onClick={() => handleCopy(msg.content, messageIndex)}
                                                      className={`p-1.5 rounded-md transition-colors hover:bg-gray-100 dark:hover:bg-gray-800 ${copiedIdx === messageIndex ? 'text-green-500' : 'text-gray-400 dark:text-gray-500'}`}
                                                      title="复制内容"
                                                  >
                                                      {copiedIdx === messageIndex ? <Check size={14} /> : <Copy size={14} />}
                                                  </button>

                                                  {/* 重新生成 - 仅最后一条且是AI回复显示 */}
                                                  {messageIndex === chatHistory.length - 1 && (
                                                      <button
                                                          onClick={handleRegenerate}
                                                          className="p-1.5 rounded-md transition-colors hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-400 dark:text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
                                                          title="重新生成"
                                                      >
                                                          <RefreshCw size={14} />
                                                      </button>
                                                  )}

                                                  <div className="h-3 w-px bg-gray-200 dark:bg-gray-800 mx-1"></div>

                                                  <button
                                                      onClick={() => handleFeedback(messageIndex, 'up')}
                                                      className={`p-1.5 rounded-md transition-colors hover:bg-gray-100 dark:hover:bg-gray-800 ${feedbackState[feedbackKey] === 'up' ? 'text-green-500 bg-green-50 dark:bg-green-900/20' : 'text-gray-400 dark:text-gray-500'}`}
                                                      title="有帮助"
                                                  >
                                                      <ThumbsUp size={14} />
                                                  </button>

                                                  <button
                                                      onClick={() => handleFeedback(messageIndex, 'down')}
                                                      className={`p-1.5 rounded-md transition-colors hover:bg-gray-100 dark:hover:bg-gray-800 ${feedbackState[feedbackKey] === 'down' ? 'text-red-500 bg-red-50 dark:bg-red-900/20' : 'text-gray-400 dark:text-gray-500'}`}
                                                      title="无帮助"
                                                  >
                                                      <ThumbsDown size={14} />
                                                  </button>
                                              </div>
                                          )}
                                      </div>
                                    </div>
                                  </div>
                                  );
                                })}
                                <div ref={chatEndRef} />
                              </div>
                            )}
                          </div>
                        </div>

                        <div
                          className="dashboard-input-dock w-full bg-white/95 dark:bg-gray-950/95 backdrop-blur-md px-4 pt-2 transition-colors z-30 fixed bottom-0 left-0 right-0 md:static"
                          style={inputBarStyle}
                        >
                          <div className={`mx-auto w-full relative ${showContentPanel ? 'max-w-full px-2' : 'max-w-3xl'}`}>

                            {/* ✨ REMOVED OLD MODEL SWITCHER */}

                            {isRAGMode && !showContentPanel && (
                                <div className="mb-2 animate-in fade-in slide-in-from-bottom-2 duration-300">
                                    <div className="inline-flex items-center gap-2 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 px-3 py-1.5 rounded-lg text-xs font-medium border border-blue-100 dark:border-blue-800 shadow-sm">
                                        <BookOpen size={14} className="text-blue-600 dark:text-blue-400" /> <span>知识库模式已开启</span>
                                        <div className="w-px h-3 bg-blue-200 dark:bg-blue-700 mx-1"></div>
                                        <button onClick={() => onModeChange('general')} className="hover:text-blue-900 dark:hover:text-blue-100 hover:bg-blue-100 dark:hover:bg-blue-800 rounded p-0.5 transition-colors" title="切换回通用问答"><X size={12} /></button>
                                    </div>
                                </div>
                            )}
                            {currentMode === 'database' && !showContentPanel && (
                                <div className="mb-2 animate-in fade-in slide-in-from-bottom-2 duration-300">
                                    <div className="inline-flex items-center gap-2 bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-300 px-3 py-1.5 rounded-lg text-xs font-medium border border-green-100 dark:border-green-800 shadow-sm">
                                        <Database size={14} className="text-green-600 dark:text-green-400" /> <span>企业数据库模式已开启</span>
                                        <div className="w-px h-3 bg-green-200 dark:bg-green-700 mx-1"></div>
                                        <button onClick={() => onModeChange('general')} className="hover:text-green-900 dark:hover:text-green-100 hover:bg-green-100 dark:hover:bg-green-800 rounded p-0.5 transition-colors" title="切换回通用问答"><X size={12} /></button>
                                    </div>
                                </div>
                            )}
                            {isSearchMode && !showContentPanel && (
                                <div className="mb-2 animate-in fade-in slide-in-from-bottom-2 duration-300">
                                    <div className="inline-flex items-center gap-2 bg-sky-50 dark:bg-sky-900/30 text-sky-700 dark:text-sky-300 px-3 py-1.5 rounded-lg text-xs font-medium border border-sky-100 dark:border-sky-800 shadow-sm">
                                        <Globe size={14} className="text-sky-600 dark:text-sky-400" /> <span>联网搜索模式已开启</span>
                                        <div className="w-px h-3 bg-sky-200 dark:bg-sky-700 mx-1"></div>
                                        <button onClick={() => onModeChange('general')} className="hover:text-sky-900 dark:hover:text-sky-100 hover:bg-sky-100 dark:hover:bg-sky-800 rounded p-0.5 transition-colors" title="切换回通用问答"><X size={12} /></button>
                                    </div>
                                </div>
                            )}

                            {isRecordingMode ? (
                              <div className="w-full h-[60px] flex items-center justify-center animate-in slide-in-from-bottom-2 duration-300">
                                 <Suspense fallback={<div className="flex items-center gap-2 text-sm text-gray-500"><Loader2 className="animate-spin" size={16}/> 加载录音组件...</div>}>
                                    <VoiceRecorder onCancel={() => setIsRecordingMode(false)} onConfirm={handleVoiceConfirm} />
                                 </Suspense>
                              </div>
                            ) : (
                                // ✨ 通过拖放更新了输入栏容器
                              <div
                                className={`dashboard-composer relative flex flex-col w-full bg-white dark:bg-gray-800 rounded-[30px] border shadow-sm transition-all duration-200 focus-within:shadow-md focus-within:border-gray-300 dark:focus-within:border-gray-500 ${isDragActive ? 'border-blue-400 ring-2 ring-blue-200/70 dark:ring-blue-500/40 bg-blue-50/60 dark:bg-blue-900/20' : (isRAGMode ? 'border-blue-200 dark:border-blue-800' : (currentMode === 'database' ? 'border-green-200 dark:border-green-800' : (isSearchMode ? 'border-sky-200 dark:border-sky-800' : 'border-gray-200 dark:border-gray-700')))}`}
                              >
                                {/* ✨  ✨ 文件预览区 */}
                                {pendingFiles.length > 0 && (
                                    <div className="px-4 pt-1 pb-1 flex flex-wrap gap-2">
                                        {pendingFiles.map((pf) => (
                                            <div key={pf.id} className="relative group inline-flex flex-col items-start gap-2 bg-white dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-xl p-2 pr-3 shadow-sm select-none animate-in fade-in zoom-in-95 duration-200 min-w-[200px]">
                                                <div className="flex items-center gap-2 w-full">
                                                    {pf.previewUrl && pf.file?.type?.startsWith('image/') ? (
                                                        <img src={pf.previewUrl} alt="preview" className="w-10 h-10 object-cover rounded-lg bg-gray-100" />
                                                    ) : (
                                                        <div className="w-10 h-10 rounded-lg bg-gray-100 dark:bg-gray-600 flex items-center justify-center">
                                                            {((pf.file?.type || '') === 'application/pdf' || (pf.file?.name || '').toLowerCase().endsWith('.pdf')) ? (
                                                                <FileText size={20} className="text-red-500 dark:text-red-400" />
                                                            ) : (
                                                                <FileIcon size={20} className="text-gray-500 dark:text-gray-300" />
                                                            )}
                                                        </div>
                                                    )}
                                                    <div className="flex flex-col max-w-[120px]">
                                                        <span className="text-xs font-medium text-gray-800 dark:text-gray-200 truncate">{pf.file.name}</span>
                                                        <span className="text-[10px] text-gray-500 dark:text-gray-400">{(pf.file.size / 1024).toFixed(0)} KB</span>
                                                    </div>
                                                    <button
                                                        onClick={() => removePendingFile(pf.id)}
                                                        disabled={pf.status === 'uploading' || pf.status === 'processing'}
                                                        className="ml-auto p-1 rounded-full text-gray-400 hover:text-red-500 hover:bg-gray-100 dark:hover:bg-gray-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                                                    >
                                                        <X size={14} />
                                                    </button>
                                                </div>
                                                <div className="w-full">
                                                    <div className="h-1.5 w-full bg-gray-200 dark:bg-gray-600 rounded-full overflow-hidden">
                                                        <div
                                                            className="h-full bg-blue-500 transition-all duration-200"
                                                            style={{ width: `${pf.progress || 0}%` }}
                                                        />
                                                    </div>
                                                    <div className="mt-1 text-[10px] text-gray-500 dark:text-gray-400">
                                                        {pf.status === 'done' && '已完成'}
                                                        {pf.status === 'uploading' && `上传中 ${pf.progress || 0}%`}
                                                        {pf.status === 'processing' && '解析中...'}
                                                        {pf.status === 'error' && '上传失败'}
                                                        {!pf.status || pf.status === 'queued' ? '排队中...' : null}
                                                    </div>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}

                                {/* ✨  ✨ 输入和操作区域 */}
                                <div className="flex items-center w-full px-2.5 py-1.5 relative gap-1.5">
                                    {/* ✨  ✨ 加号菜单按钮 */}
                                    <div className="relative z-20 plus-menu-container flex items-center">
                                        <button
                                            onClick={() => setIsPlusMenuOpen(!isPlusMenuOpen)}
                                            className={`h-9 w-9 inline-flex items-center justify-center rounded-full transition-all duration-200 ${isPlusMenuOpen ? 'bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-white rotate-45' : 'text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 hover:text-gray-900 dark:hover:text-white'}`}
                                            title="更多功能"
                                        >
                                            <Plus size={18} strokeWidth={1.6} />
                                        </button>

                                        {/* ✨  ✨ 加号菜单下拉 */}
                                        {isPlusMenuOpen && (
                                            <div
                                              className={`dashboard-dropdown bg-white dark:bg-gray-800 rounded-2xl shadow-xl border border-gray-100 dark:border-gray-700 overflow-hidden animate-in fade-in slide-in-from-bottom-2 p-1.5 flex flex-col gap-0.5 z-50 ${
                                                isMobileViewport
                                                  ? 'fixed left-3 right-3 bottom-[calc(env(safe-area-inset-bottom)+88px)] max-h-[55vh] overflow-y-auto'
                                                  : 'absolute bottom-full left-0 mb-3 w-56'
                                              }`}
                                            >
                                                {!isMeetingMode ? (
                                                    <button
                                                        onClick={() => { if (fileInputRef.current) fileInputRef.current.click(); setIsPlusMenuOpen(false); }}
                                                        className="flex items-center gap-3 px-3 py-2.5 hover:bg-gray-100 dark:hover:bg-gray-700/50 rounded-xl text-left text-sm font-medium text-gray-700 dark:text-gray-200 transition-colors group"
                                                    >
                                                        <div className="w-8 h-8 rounded-full bg-orange-50 dark:bg-orange-900/20 text-orange-600 dark:text-orange-400 flex items-center justify-center group-hover:scale-110 transition-transform">
                                                            <FileUp size={16} />
                                                        </div>
                                                        添加文件
                                                    </button>
                                                ) : (
                                                    <div className="px-3 py-2 text-xs text-gray-500 dark:text-gray-400 leading-5 bg-gray-50/80 dark:bg-gray-900/50 rounded-xl border border-gray-100 dark:border-gray-700">
                                                        会议纪要模式请使用左侧面板顶部的“上传音频文件”按钮。
                                                    </div>
                                                )}

                                                <button
                                                    onClick={() => { onModeChange(isRAGMode ? 'general' : 'rag'); setIsPlusMenuOpen(false); }}
                                                    className="flex items-center gap-3 px-3 py-2.5 hover:bg-gray-100 dark:hover:bg-gray-700/50 rounded-xl text-left text-sm font-medium text-gray-700 dark:text-gray-200 transition-colors group"
                                                >
                                                    <div className={`w-8 h-8 rounded-full flex items-center justify-center group-hover:scale-110 transition-transform ${isRAGMode ? 'bg-blue-100 text-blue-600' : 'bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400'}`}>
                                                        {isRAGMode ? <BookOpen size={16} fill="currentColor" /> : <BookOpen size={16} />}
                                                    </div>
                                                    <div className="flex-1 flex items-center justify-between">
                                                        知识库模式
                                                        {isRAGMode && <span className="text-[10px] bg-blue-100 dark:bg-blue-900 text-blue-600 px-1.5 py-0.5 rounded-full">开启</span>}
                                                    </div>
                                                </button>

                                                <button
                                                    onClick={() => { onModeChange(currentMode === 'database' ? 'general' : 'database'); setIsPlusMenuOpen(false); }}
                                                    className="flex items-center gap-3 px-3 py-2.5 hover:bg-gray-100 dark:hover:bg-gray-700/50 rounded-xl text-left text-sm font-medium text-gray-700 dark:text-gray-200 transition-colors group"
                                                >
                                                    <div className={`w-8 h-8 rounded-full flex items-center justify-center group-hover:scale-110 transition-transform ${currentMode === 'database' ? 'bg-green-100 text-green-600' : 'bg-green-50 dark:bg-green-900/20 text-green-600 dark:text-green-400'}`}>
                                                        <Database size={16} />
                                                    </div>
                                                    <div className="flex-1 flex items-center justify-between">
                                                        企业数据库
                                                        {currentMode === 'database' && <span className="text-[10px] bg-green-100 dark:bg-green-900 text-green-600 px-1.5 py-0.5 rounded-full">开启</span>}
                                                    </div>
                                                </button>

                                                <button
                                                    onClick={() => { onModeChange(isSearchMode ? 'general' : 'search'); setIsPlusMenuOpen(false); }}
                                                    className="flex items-center gap-3 px-3 py-2.5 hover:bg-gray-100 dark:hover:bg-gray-700/50 rounded-xl text-left text-sm font-medium text-gray-700 dark:text-gray-200 transition-colors group"
                                                >
                                                    <div className={`w-8 h-8 rounded-full flex items-center justify-center group-hover:scale-110 transition-transform ${isSearchMode ? 'bg-sky-100 text-sky-600' : 'bg-sky-50 dark:bg-sky-900/20 text-sky-600 dark:text-sky-400'}`}>
                                                        <Globe size={16} />
                                                    </div>
                                                    <div className="flex-1 flex items-center justify-between">
                                                         搜索联网
                                                         {isSearchMode && <span className="text-[10px] bg-sky-100 dark:bg-sky-900 text-sky-600 px-1.5 py-0.5 rounded-full">开启</span>}
                                                    </div>
                                                </button>
                                            </div>
                                        )}
                                    </div>

                                    <textarea
                                      className="flex-1 w-full max-h-[200px] min-h-[44px] py-[10px] px-2 bg-transparent border-0 focus:ring-0 resize-none outline-none text-gray-800 dark:text-gray-100 placeholder:text-gray-500 dark:placeholder:text-gray-400 leading-6 text-[15px] custom-scrollbar"
                                      ref={messageInputRef}
                                      placeholder={
                                          isUploadingFile ? "正在上传处理中，请稍候..." :
                                          (isMeetingMode ? (panelContent ? "在此提问关于会议内容的问题..." : "上传音频或录音...") :
                                          (isAuditMode ? "上传单据开始审单..." :
                                          (isReportMode ? "输入修改意见..." :
                                          (isOCRMode ? (panelContent ? "在此分析文档内容..." : "上传图片或PDF...") :
                                          (currentMode === 'database' ? "查询企业数据..." :
                                          (isSearchMode ? "输入问题，将为您联网搜索..." :
                                          (isRAGMode ? "向知识库提问..." : "询问任何问题...")))))))
                                      }
                                      rows={1}
                                      value={inputValue}
                                      onChange={(e) => setInputValue(e.target.value)}
                                      onFocus={() => setIsInputFocused(true)}
                                      onBlur={() => setIsInputFocused(false)}
                                      onKeyDown={(e) => {
                                        if (e.key !== 'Enter') return;
                                        if (appSettings.enterToSend !== false) {
                                          if (!e.shiftKey) {
                                            e.preventDefault();
                                            handleSendMessage();
                                          }
                                          return;
                                        }
                                        if (e.ctrlKey || e.metaKey) {
                                          e.preventDefault();
                                          handleSendMessage();
                                        }
                                      }}
                                      style={{ minHeight: '44px' }}

                                      onInput={(e) => resizeMessageInput(e.target)}
                                      disabled={isUploadingFile}
                                    />

                                    <div className="flex items-center gap-1 flex-shrink-0">
                                       <div className="relative" ref={backendDropdownRef}>
                                          <button
                                            type="button"
                                            onClick={() => setIsBackendDropdownOpen((prev) => !prev)}
                                            className="inline-flex items-center gap-1 rounded-full border border-gray-200 dark:border-gray-700 bg-white/90 dark:bg-gray-800 px-2.5 py-1.5 text-[11px] font-medium text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white hover:border-gray-300 dark:hover:border-gray-600 transition-colors"
                                            title="切换模型后端"
                                          >
                                            {llmBackend === 'local' ? (
                                              <>
                                                <Cpu size={13} className="text-purple-500" />
                                                <span className="hidden sm:inline">本地</span>
                                              </>
                                            ) : (
                                              <>
                                                <Cloud size={13} className="text-blue-500" />
                                                <span className="hidden sm:inline">云端</span>
                                              </>
                                            )}
                                            <ChevronDown size={12} className={`transition-transform duration-200 ${isBackendDropdownOpen ? 'rotate-180' : ''}`} />
                                          </button>

                                          {isBackendDropdownOpen && (
                                            <div className="dashboard-dropdown absolute bottom-full right-0 mb-2 w-56 rounded-xl border border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-xl z-50 overflow-hidden animate-in fade-in zoom-in-95 duration-200">
                                              <button
                                                type="button"
                                                onClick={() => { setLlmBackend('local'); setIsBackendDropdownOpen(false); }}
                                                className={`w-full text-left px-3 py-2 text-xs font-medium flex items-center gap-2 hover:bg-gray-50 dark:hover:bg-gray-700/50 ${llmBackend === 'local' ? 'text-purple-600 bg-purple-50 dark:bg-purple-900/20' : 'text-gray-700 dark:text-gray-300'}`}
                                              >
                                                      <Cpu size={14} /> 本地 (Qwen 2.5-coder)
                                                {llmBackend === 'local' && <Check size={12} className="ml-auto"/>}
                                              </button>
                                              <button
                                                type="button"
                                                onClick={() => { setLlmBackend('cloud'); setIsBackendDropdownOpen(false); }}
                                                className={`w-full text-left px-3 py-2 text-xs font-medium flex items-center gap-2 hover:bg-gray-50 dark:hover:bg-gray-700/50 ${llmBackend === 'cloud' ? 'text-blue-600 bg-blue-50 dark:bg-blue-900/20' : 'text-gray-700 dark:text-gray-300'}`}
                                              >
                                                      <Cloud size={14} /> 云端 (DeepSeek V3.2)
                                                {llmBackend === 'cloud' && <Check size={12} className="ml-auto"/>}
                                              </button>
                                            </div>
                                          )}
                                       </div>
                                       {!inputValue && (
                                          <button className="p-2 text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-200 dark:hover:bg-gray-700 rounded-full transition-colors" onClick={() => setIsRecordingMode(true)} disabled={isProcessing || isUploadingFile}><Mic size={20} /></button>
                                       )}
                                       <button
                                            className={`p-2 rounded-full transition-all duration-200 ${(inputValue.trim() || pendingFiles.length > 0 || isProcessing) ? 'bg-black dark:bg-white text-white dark:text-black' : 'bg-[#e5e5e5] dark:bg-gray-700 text-gray-400 dark:text-gray-500 cursor-not-allowed'}`}
                                            onClick={isProcessing ? handleStopGeneration : () => handleSendMessage()}
                                            disabled={(!inputValue.trim() && pendingFiles.length === 0 && !isProcessing) || isUploadingFile}
                                            title={isProcessing ? "停止生成" : "发送"}
                                        >
                                          {isProcessing ? <StopCircle size={18} /> : <ArrowRight size={18} />}
                                        </button>
                                    </div>
                                </div>

                              </div>
                            )}
                            {!shouldHideInputHint && (
                              <div className="text-center mt-2.5 text-xs text-gray-400 dark:text-gray-500">智能助手可能会犯错。请核查重要信息。</div>
                            )}
                          </div>
                        </div>

                        </>
                )}
            </div>
            )}
            </>
        )}
        </div>
        <Suspense fallback={null}>
            {settingsModalState.isOpen && (
              <SettingsModal
                key={`${settingsModalState.category}:${userProfile?.id || 'anonymous'}`}
                isOpen
                initialCategory={settingsModalState.category}
                onClose={() => setSettingsModalState((prev) => ({ ...prev, isOpen: false }))}
                userProfile={userProfile}
                onLogout={onLogout}
                onSettingsChange={(next) => setAppSettings(normalizeAppSettings(next || DEFAULT_APP_SETTINGS))}
              />
            )}
            <ShareModal isOpen={shareModal.isOpen} onClose={() => setShareModal({ isOpen: false, sessionId: null, title: "" })} sessionId={shareModal.sessionId} sessionTitle={shareModal.title} userId={userProfile?.id || "anonymous"} />
            <OcrIngestModal
              isOpen={ocrIngestModal.isOpen}
              onClose={() => setOcrIngestModal({ isOpen: false, content: "" })}
              content={ocrIngestModal.content}
              userId={userProfile?.id || "anonymous"}
              sessionId={currentSessionId}
              llmBackend={llmBackend}
            />
        </Suspense>
      </div>
    </div>
  );
};

export default DashboardPage;




