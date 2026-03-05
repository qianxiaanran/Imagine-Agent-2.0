import React, { useState, useEffect, useLayoutEffect, useRef, Suspense, lazy, useMemo } from 'react';
import {
  Bot, Zap, FileText, Layout, PanelLeftOpen, ChevronDown, Check, User,
  BookOpen, X, Mic, StopCircle, ArrowRight, Plus,
  Loader2, Sparkles, Database, Download, ScanText,
  ClipboardCheck, Mail, ArrowLeft, Share2, Copy, PencilLine, Presentation,
  TrendingUp, AlertTriangle, Play, Image as ImageIcon,
  Volume2, File as FileIcon,
  ThumbsUp, ThumbsDown, Square, RefreshCw, Globe, Star,
  FileUp, Cloud, Cpu
} from 'lucide-react';

import Sidebar from './Sidebar';
import MobileSidebar from './MobileSidebar';
import Suggestions from './Suggestions';
// 原料药进口
import { API_BASE_URL, AUTH_TOKEN_KEY, refreshAccessToken as refreshAccessTokenFromApiClient } from '../../api/apiClient';
import userApi from '../../api/user';
import historyApi from '../../api/history';
import { convertWebMToWav } from '../../utils/audio';
import {
  APP_SETTINGS_UPDATED_EVENT,
  DEFAULT_APP_SETTINGS,
  loadAppSettings,
  normalizeAppSettings,
  buildChatPersonalizationPayload
} from '../../utils/appSettings';

const SettingsModal = lazy(() => import('../../components/SettingsModal'));
const VoiceRecorder = lazy(() => import('../../components/VoiceRecorder'));
const ShareModal = lazy(() => import('./ShareModal'));
const OcrIngestModal = lazy(() => import('./OcrIngestModal'));
const MarkdownRenderer = lazy(() => import('./MarkdownRenderer'));
const SourcePanel = lazy(() => import('./SourcePanel'));
const ModePanel = lazy(() => import('./ModePanel'));

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
const DETAIL_LEVEL_OPTIONS = ["精简", "标准", "详细", "非常详细"];
const REPORT_STYLE_OPTIONS = ["咨询风", "管理层简报", "数据驱动", "叙事型", "执行导向", "学术/研究型"];
const PPT_STRUCTURE_OPTIONS = ["问题-分析-方案", "现状-挑战-突破", "数据驱动", "项目汇报", "战略规划", "销售路演"];
const PPT_VISUAL_OPTIONS = ["商务简洁", "科技感", "品牌一致", "极简黑白", "暖色活力", "深色高对比"];
const REPORT_SECTION_OPTIONS = [
  "执行摘要",
  "背景与范围",
  "目标与问题定义",
  "方法与数据来源",
  "现状分析",
  "原因/驱动因素",
  "市场/竞品分析",
  "用户/客户洞察",
  "财务/成本分析",
  "风险与合规",
  "策略与方案",
  "实施路径/里程碑",
  "资源与预算",
  "指标与评估",
  "结论与下一步"
];
const PPT_SECTION_OPTIONS = [
  "封面",
  "目录/议程",
  "背景/现状",
  "问题/痛点",
  "分析/洞察",
  "方案/策略",
  "实施计划",
  "资源/预算",
  "风险与对策",
  "案例/对标",
  "成果预期/KPI",
  "总结/行动项",
  "Q&A/致谢"
];
const EMAIL_ELEMENT_OPTIONS = [
  "背景说明",
  "明确诉求",
  "时间节点",
  "所需配合",
  "行动项列表",
  "附件说明",
  "风险/注意事项",
  "礼貌结束语"
];
const ONBOARDING_STORAGE_PREFIX = "onboarding_seen_v1_";
const ONBOARDING_MESSAGES = [
  "顶部左侧的模式下拉可切换到报告/PPT/邮件写作、会议纪要、OCR、审单等场景。",
  "左侧栏（手机点左上角菜单）有新建/搜索聊天和历史会话，知识库入口也在这里；输入框左侧“＋”用于上传文件并启用引用文档/数据库/联网。这是我首次完成这种类型的项目，目前可能还有诸多bug，如有建议请联系我，我会尽可能改正，感谢使用！"
];
const MODEL_OPTIONS = [
  { id: 0, name: "通用助手", icon: Bot },
  { id: 1, name: "会议纪要", icon: Mic },
  { id: 2, name: "OCR 识别", icon: ScanText },
  { id: 3, name: "写作助手", icon: PencilLine },
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
        } catch (e) {}
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
  const [auditDocType, setAuditDocType] = useState('');
  const [auditModelBackend, setAuditModelBackend] = useState('local');
  const [auditFile, setAuditFile] = useState(null);
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

  const [isProcessing, setIsProcessing] = useState(false);
  const [isUploadingFile, setIsUploadingFile] = useState(false);
  const [isOcrSaving, setIsOcrSaving] = useState(false);
  const [isProfileLoading, setIsProfileLoading] = useState(true);
  const [isSessionsLoading, setIsSessionsLoading] = useState(true);
  const [isSavingContext, setIsSavingContext] = useState(false);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [appSettings, setAppSettings] = useState(() => loadAppSettings());
  const [settingsModalState, setSettingsModalState] = useState({ isOpen: false, category: 'general' });

  const [userProfile, setUserProfile] = useState({ id: 'anonymous', name: 'User', avatar: '' });
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [sessionList, setSessionList] = useState([]);
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
  const ocrMeasureCanvasRef = useRef(null);
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
  const [feedbackState, setFeedbackState] = useState({}); // { msgIdx: 'up' | 'down' }
  const [editingMessageIndex, setEditingMessageIndex] = useState(null);
  const [editingMessageText, setEditingMessageText] = useState('');
  const [editingMessageAttachments, setEditingMessageAttachments] = useState([]);
  const [streamingAssistantText, setStreamingAssistantText] = useState('');

  // ✨ 新增 UI 状态
  const [isPlusMenuOpen, setIsPlusMenuOpen] = useState(false);
  const [isDragActive, setIsDragActive] = useState(false);
  const [isInputFocused, setIsInputFocused] = useState(false);
  const [keyboardOffset, setKeyboardOffset] = useState(0);
  const [isMobileViewport, setIsMobileViewport] = useState(false);
  const [mobileWorkspaceTab, setMobileWorkspaceTab] = useState('chat');
  const [ocrMobileTab, setOcrMobileTab] = useState('preview');
  const fileInputRef = useRef(null);
  const handleFileSelectRef = useRef(null);
  const dragDepthRef = useRef(0);
  const messageInputRef = useRef(null);
  const auditPollRef = useRef(null);
  const auditHistorySavedRef = useRef(null);
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


  const dropdownRef = useRef(null);
  const mobileDropdownRef = useRef(null);
  const backendDropdownRef = useRef(null); // ✨ 后端下拉 Ref
  const ocrPreviewRef = useRef(null);
  const ocrImageRef = useRef(null);
  const ocrRenderRef = useRef(null);
  const chatEndRef = useRef(null);
  const chatScrollRef = useRef(null);
  const abortControllerRef = useRef(null); // ✨ 控制打断的 Ref
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
      const lines = getOcrLines(activeOcrFile);
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
      activeOcrFile?.id,
      activeOcrFile?.status,
      activeOcrFile?.ocrText,
      activeOcrFile?.lines,
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
          updateOcrEntry(activeOcrFile.id, { jsonText: JSON.stringify(activeOcrFile.ocrData, null, 2) });
      }
  }, [activeOcrFile?.id, ocrViewTab]);

  useEffect(() => {
      if (!activeOcrFile) return;
      const total = Array.isArray(activeOcrFile.pages) ? activeOcrFile.pages.length : 1;
      if (ocrPageIndex >= total) {
          setOcrPageIndex(0);
      }
      setSelectedOcrLine(null);
  }, [activeOcrFile?.id, ocrPageIndex]);

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
  const hasMoreMessages = chatHistory.length > normalizedVisibleCount;
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


  const commitStreamToHistory = (finalTextOverride) => {
    const finalText = finalTextOverride || streamingAssistantText || '';
    if (!finalText) return;
    setChatHistory((prev) => {
        if (!prev.length) return prev;
        const lastIndex = prev.length - 1;
        const lastMsg = prev[lastIndex]; // Fix: Define lastMsg
        // 如果已经是这个内容了，或者不是 assistant，就不更新
        if (lastMsg.role !== 'assistant' || lastMsg.content === finalText) return prev;
        const next = [...prev];
        next[lastIndex] = { ...lastMsg, content: finalText };
        return next;
    });
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

    const loadSessions = async (uid) => {
      if (!isActive) return;
      setIsSessionsLoading(true);
      try {
        const sessions = await historyApi.getSessions(uid);
        if (isActive) setSessionList(sessions || []);
      } catch (e) {
        console.error('Failed to load sessions', e);
      } finally {
        if (isActive) setIsSessionsLoading(false);
      }
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
        schedule(() => loadSessions(uid), 600);
      } else {
        if (isActive) setIsSessionsLoading(false);
      }
    };

    const cancelProfile = schedule(loadProfile, 300);
    return () => {
      isActive = false;
      cancelProfile();
    };
  }, []);

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
    } catch (e) {
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
    } catch (e) {
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

    let cancelled = false;
    const poll = async () => {
      if (cancelled) return;
      try {
        const token = localStorage.getItem(AUTH_TOKEN_KEY);
        const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
        const res = await fetch(`${API_BASE_URL}/api/audit/${jobId}`, { headers });
        const data = await res.json();

        if (!res.ok) {
          throw new Error(data.detail || data.error || '获取审单状态失败');
        }

        const nextStatus = data.status || status;
        const progressValue = Number(data.progress);
        setAuditState((prev) => ({
          ...prev,
          status: nextStatus,
          progress: Number.isFinite(progressValue) ? progressValue : prev.progress,
          stage: data.stage || prev.stage,
          workflow_state: data.workflow_state || prev.workflow_state,
          caseId: data.case_id || prev.caseId,
          caseDocuments: Array.isArray(data.case_documents) ? data.case_documents : prev.caseDocuments,
          result: data.result || prev.result,
          error_message: data.error_message || prev.error_message,
          error: data.error_message ? data.error_message : prev.error
        }));

        if (['pending', 'running'].includes(nextStatus)) {
          auditPollRef.current = setTimeout(poll, AUDIT_POLL_INTERVAL);
        }
      } catch (error) {
        if (cancelled) return;
        const message = error?.message || '获取审单状态失败';
        setAuditState((prev) => ({
          ...prev,
          status: 'failed',
          error: message,
          error_message: message
        }));
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
    } catch (e) {
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
    return () => {
      const lockRef = keyboardLockPrevRef.current;
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
  }, [isMobileViewport, isOCRMode, activeOcrFile?.id, activeOcrFile?.status]);

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
          historyApi.getSessions(uid).then(sessions => setSessionList(sessions || []));
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

  const extractOcrLinesFromData = (data) => {
      if (!data) return [];
      return data.lines
          || data?.data?.lines
          || data?.ocrData?.lines
          || data?.ocrData?.data?.lines
          || [];
  };

  const extractOcrTextFromData = (data) => {
      if (!data) return '';
      return data.text
          || data?.data?.text
          || data?.result?.text
          || '';
  };

  const extractOcrPagesFromData = (data) => {
      if (!data) return [];
      return data.pages
          || data?.data?.pages
          || data?.ocrData?.pages
          || data?.ocrData?.data?.pages
          || [];
  };

  const getOcrLines = (file) => {
      if (!file) return [];
      if (Array.isArray(file.lines) && file.lines.length) return file.lines;
      const dataLines = extractOcrLinesFromData(file.ocrData);
      if (Array.isArray(dataLines) && dataLines.length) return dataLines;
      const text = file.ocrText || extractOcrTextFromData(file.ocrData);
      return (text || '')
          .split(/\r?\n/)
          .filter((line) => line.trim())
          .map((textLine) => ({ text: textLine }));
  };

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
          updateOcrEntry(activeOcrFile.id, updates);
      }
  }, [activeOcrFile?.id, activeOcrFile?.ocrData]);

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
      } catch (e) {
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
          const res = await fetch(`${API_BASE_URL}/api/voice/instant`, {
              method: 'POST',
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
      setAuditFile(null);
      setAuditNotice('');
      setIsAuditErpActionLoading(false);
      auditHistorySavedRef.current = null;
  };

  const showAuditNotice = (message) => {
      if (!message) return;
      setAuditNotice(message);
      setTimeout(() => setAuditNotice(''), 2500);
  };

  const startAuditJob = async (file) => {
      if (!file) return;
      if (['uploading', 'pending', 'running'].includes(auditState.status)) {
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

      setAuditNotice('');
      setAuditFile({ name: file.name, size: file.size, sizeLabel: formatFileSize(file.size) });
      setAuditState((prev) => ({
          ...prev,
          status: 'uploading',
          jobId: null,
          progress: 0,
          stage: 'pending_docs',
          workflow_state: 'pending_docs',
          result: null,
          error: null,
          error_message: null
      }));

      try {
          const formData = new FormData();
          formData.append('file', file);
          if (auditDocType) formData.append('doc_type', auditDocType);
          const effectiveAuditBackend = auditModelBackend === 'cloud' ? 'cloud' : 'local';
          formData.append('model_type', effectiveAuditBackend);
          formData.append('user_id', userProfile.id || 'anonymous');
          if (auditState.caseId) formData.append('case_id', auditState.caseId);

          const token = localStorage.getItem(AUTH_TOKEN_KEY);
          const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
          const response = await fetch(`${API_BASE_URL}/api/audit/start`, {
              method: 'POST',
              headers,
              body: formData

          });
          const data = await response.json();

          if (!response.ok || !data.job_id) {
              throw new Error(data.detail || data.error || '审单启动失败');
          }

          setAuditState((prev) => ({
              ...prev,
              status: data.status || 'pending',
              jobId: data.job_id,
              caseId: data.case_id || prev.caseId,
              caseDocuments: Array.isArray(data.case_documents) ? data.case_documents : prev.caseDocuments,
              progress: 0,
              stage: data.stage || 'pending_docs',
              workflow_state: data.stage || 'pending_docs',
              result: null,
              error: null,
              error_message: null
          }));
      } catch (error) {
          const message = error?.message || '审单启动失败';
          setAuditState((prev) => ({
              ...prev,
              status: 'failed',
              jobId: null,
              progress: 0,
              stage: 'failed',
              workflow_state: 'failed',
              result: null,
              error: message,
              error_message: message
          }));
      }
  };

  const handleAuditFileSelect = async (e) => {
      const files = Array.from(e?.target?.files || []);
      if (!files.length) return;
      if (files.length > 1) {
          showAuditNotice('当前按顺序处理单据包，请逐个上传。');
      }
      await startAuditJob(files[0]);
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
      if (selectedModel === modelId) return;

      if (modelId !== 0 && (currentMode === 'database' || currentMode === 'rag' || currentMode === 'search')) {
          onModeChange('general');
      }

      setSelectedModel(modelId);
      setChatHistory([]);
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
      setSpeakingIdx(null);
      window.speechSynthesis.cancel();
  };

  const handleSessionClick = async (sessionId) => {
    if (isProcessing) return;
    setIsMobileSidebarOpen(false);
    setIsProcessing(true);
    setAudioFileUrl(null);
    setCurrentAudioPath(null);
    setPendingFiles([]);
    resetAuditState();
    setSpeakingIdx(null);
    window.speechSynthesis.cancel();

    try {
      const uid = userProfile.id || 'anonymous';
      const messages = await historyApi.getSessionMessages(sessionId, uid);
      const safeMessages = Array.isArray(messages)
        ? messages
        : (Array.isArray(messages?.data)
          ? messages.data
          : (Array.isArray(messages?.items) ? messages.items : []));

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
        } catch (e) {
          console.warn("Invalid session_meta json:", metaMsg.content);
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

      const chatMsgs = safeMessages.filter((m) => m.role !== 'context' && m.role !== 'meta');
      const normalizedChatMsgs = chatMsgs.length > 0
        ? chatMsgs.map((msg) => ({
            ...msg,
            role: msg?.role === 'user' ? 'user' : 'assistant',
            content: typeof msg?.content === 'string'
              ? msg.content
              : (msg?.content == null ? '' : JSON.stringify(msg.content))
          }))
        : (safeMessages.length > 0
          ? [{
              role: 'assistant',
              content: '该历史会话未找到可展示的对话消息（仅包含上下文/元数据）。'
            }]
          : [{
              role: 'assistant',
              content: '该历史会话暂无内容。'
            }]);
      setHistoryRenderTarget(HISTORY_FIRST_PAINT_COUNT);
      setChatHistory(normalizedChatMsgs);
      setVisibleMessageCount(Math.min(HISTORY_FIRST_PAINT_COUNT, normalizedChatMsgs.length));
      setExpandedSources({});
      scheduleHistoryExpand();
      setPanelContent(contextMsg ? contextMsg.content : '');
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
        } catch (e) {
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
        setReportStep('chat');
      } else {
        setReportStep('selection');
        setReportType(null);
        setReportFormData({});
      }
    } catch (e) {
      console.error("Failed to load session", e);
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
    if (!uid || uid === 'anonymous') return;

    hasHandledInitialRouteRef.current = true;
    const routeSessionId = extractConversationSessionId(window.location.pathname);
    if (!routeSessionId || routeSessionId === currentSessionId) return;

    isApplyingRouteSessionRef.current = true;
    Promise.resolve(sessionClickHandlerRef.current?.(routeSessionId)).finally(() => {
      isApplyingRouteSessionRef.current = false;
    });
  }, [isProfileLoading, isSessionsLoading, userProfile?.id, currentSessionId]);

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
    if (!models.some((item) => item.id === selectedModel)) {
      setSelectedModel(0);
    }
  }, [models, selectedModel]);

  const savePanelContext = async (sid, content, type = 'context_save') => {
      if (!sid || !content) return;
      try {
          setIsSavingContext(true);
          await historyApi.saveContext(sid, content, userProfile.id, type);
      } catch (e) {
          console.error("Failed to save context", e);
      } finally {
          setIsSavingContext(false);
      }
  };

  const saveSessionMeta = async (sid, modelId, mode, audioPath = null, backend = 'local') => {
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
  };

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
                  historyApi.getSessions(uid).then(sessions => setSessionList(sessions || []));
              }
          } catch (e) {
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
          historyApi.getSessions(uid).then(sessions => setSessionList(sessions || []));
      }
  };

  // -------------------------------------------------------------------------
  // 🚀 文件上传和处理逻辑
  // -------------------------------------------------------------------------
  const applyFileContext = async (context, audioPathOverride = null) => {
      if (!context) return;

      const newContent = (panelContent ? panelContent + '\n\n' : '') + context;
      setPanelContent(newContent);

      let targetSessionId = currentSessionId;
      if (!targetSessionId) {
          targetSessionId = crypto.randomUUID ? crypto.randomUUID() : `sid_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
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

      if (!currentSessionId) {
          const uid = userProfile.id || 'anonymous';
          historyApi.getSessions(uid).then(sessions => setSessionList(sessions || []));
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
              return result.data || {};
          }

          const message = result?.data?.detail || result?.data?.error || `Upload failed with status ${result.status}`;
          throw new Error(message);
      })();
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

      return result;
  };

  const parseUploadResult = (data) => {
      const okCount = Number(data?.ok ?? 0);
      const status = data?.status;
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

      let ragTriggered = false;

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
                      ragTriggered = true;
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
          if (ragTriggered && currentMode !== 'rag') {
              onModeChange('rag');
          }
          setIsUploadingFile(false);
      }
  };

  useEffect(() => {
      const pending = autoProcessFilesRef.current;
      const mode = autoProcessModeRef.current;
      if (!pending || !mode) return;

      if ((mode === 'meeting' && selectedModel !== 1) || (mode === 'ocr' && selectedModel !== 2)) return;

      autoProcessFilesRef.current = null;
      autoProcessModeRef.current = null;

      const run = async () => {
          if (mode === 'ocr') {
              const entries = pending.map(buildOcrEntry);
              if (entries.length) {
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
          const { context, sessionId, audioPath } = await processFiles(pending);
          if (mode === 'ocr') {
              applyOcrContext(context, sessionId);
          } else {
              await applyFileContext(context, audioPath);
          }
      };
      run();
  }, [selectedModel]);

  const processFiles = async (filesToProcess) => {
      if (!filesToProcess || filesToProcess.length === 0) return { context: "", success: true, ragTriggered: false };

      let combinedContext = "";
      let hasError = false;
      let ragTriggered = false;
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
                  const res = await fetch(`${API_BASE_URL}/api/voice/transcribe`, { method: 'POST', body: formData });
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

                          if (currentMode !== 'rag') {
                             onModeChange('rag');
                          }
                          ragTriggered = true;
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

      return { context: combinedContext, success: !hasError, ragTriggered, sessionId: ocrSessionId, audioPath: meetingAudioPath };
  };

  const handleFileSelect = async (e) => {
    const files = Array.from(e.target.files);
    if (!files.length) return;

    if (isAuditMode) {
        await startAuditJob(files[0]);
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
            await applyFileContext(context, audioPath);
        }
    }
    // 清除输入
    if (fileInputRef.current) fileInputRef.current.value = '';
    if (e.target && e.target.value) e.target.value = '';
  };

  useEffect(() => {
    handleFileSelectRef.current = handleFileSelect;
  }, [handleFileSelect]);

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

  // ✨ 新增：停止生成功能
  const handleStopGeneration = () => {
      if (abortControllerRef.current) {
          abortControllerRef.current.abort();
          abortControllerRef.current = null;
      }
      stopSmoothStream(); // 停止动画并刷新剩余内容
      commitStreamToHistory(streamDisplayRef.current);
      setStreamingAssistantText('');
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

        const userMessage = { role: 'user', content: displayContent };
        setChatHistory(prev => [...prev, userMessage]);
        if (isReportMode) setReportStep('chat');
    }

    setIsProcessing(true);
    setChatHistory(prev => [...prev, { role: 'assistant', content: '', sources: [] }]);
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
         const { context: fileContext, success, ragTriggered, sessionId: ocrSessionId, audioPath: meetingAudioPath } = await processFiles(filesToProcess);
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
         if (ragTriggered) {
             effectiveMode = 'rag';
         }

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

         if (!response.ok) throw new Error("API Error");
         if (!response.body) throw new Error("No response body");

         const reader = response.body.getReader();
         const decoder = new TextDecoder();
         let done = false;
         // let currentText = ""; // 移除内部定义，使用外部定义的 currentText
         let buffer = "";
         let sessionAssigned = false;
         const processMainStreamLine = (line) => {
            if (!line || !line.trim()) return;
            try {
                const json = JSON.parse(line);
                if (json.t === 'c') {
                    const newChunk = typeof json.v === 'string' ? json.v : String(json.v || '');
                    streamBufferRef.current += newChunk;
                } else if (json.t === 'm') {
                    if (json.src) {
                         setChatHistory(prev => {
                             const newHistory = [...prev];
                             if (newHistory.length > 0) {
                                 newHistory[newHistory.length - 1] = { ...newHistory[newHistory.length - 1], sources: json.src };
                             }
                             return newHistory;
                         });
                    }
                    if (json.sid && !sessionAssigned) {
                        sessionAssigned = true;
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
                    if (json.end) {
                        shouldPostProcessReply = true;
                        const uid = userProfile.id || 'anonymous';
                        if (uid && uid !== 'anonymous') {
                            historyApi.getSessions(uid).then(sessions => setSessionList(sessions || []));
                        }
                    }
                }
            } catch (e) {}
         };

         while (!done) {
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

         // 处理 decoder/缓冲区尾包，避免最后一段无换行时被丢弃
         const tailChunk = decoder.decode();
         if (tailChunk) buffer += tailChunk;
         if (buffer && buffer.trim()) {
             const tailLines = buffer.split('\n').filter((line) => line && line.trim());
             tailLines.forEach(processMainStreamLine);
         }
    } catch (e) {
      if (e.name === 'AbortError') {
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
      // ✨ 停止动画
      stopSmoothStream();

      // ⚠️ 关键修复：确保状态更新的顺序，避免闪烁和“变回加载动画”

      // 修复开始：在清除引用之前捕获本地值
      const finalContent = streamDisplayRef.current;
      const resolvedFinalContent =
        (!finalContent || !finalContent.trim()) && shouldPostProcessReply
          ? '未收到模型返回内容，请重试；如在引用文档模式，建议减少上下文长度或切换云端模型。'
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
            // eslint-disable-next-line no-new
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

      abortControllerRef.current = null;
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

      const res = await fetch(`${API_BASE_URL}/api/voice/instant`, {
          method: 'POST',
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

  const handleSubmitReportForm = () => {
      const listOrNone = (items) => (Array.isArray(items) && items.length ? items.join('、') : '无');
      let prompt = "";
      const chosenBackend = reportFormData.modelBackend || llmBackend;
      if (reportType === 'report') {
          prompt = `[指令:生成报告]\n主题：${reportFormData.topic || '未指定'}\n场景：${reportFormData.scene || '通用'}\n受众：${reportFormData.audience || '通用'}\n时间范围：${reportFormData.timeRange || '未指定'}\n范围/对象：${reportFormData.scope || '未指定'}\n报告目的：${reportFormData.purpose || '未指定'}\n风格/表达：${reportFormData.reportStyle || REPORT_STYLE_OPTIONS[0]}\n详细程度：${reportFormData.detailLevel || DETAIL_LEVEL_OPTIONS[2]}\n必含模块：${listOrNone(reportFormData.reportModules)}\n关键问题/假设：${reportFormData.keyQuestions || '无'}\n数据/指标/素材：${reportFormData.dataMetrics || '无'}\n约束/风险关注：${reportFormData.constraints || '无'}\n预期结论/建议方向：${reportFormData.expectedOutcome || '无'}\n关键内容：${reportFormData.keyPoints || '无'}\n请生成一份“可直接写作”的详细报告大纲：章节不少于 8 个（可根据篇幅增加），覆盖必含模块。每个章节给出：目标/关键结论/分析维度/数据或指标/建议与行动/潜在风险与对策，使用 Markdown 列表组织，内容具体可执行。`;
      } else if (reportType === 'ppt') {
          prompt = `[指令:生成PPT]\n主题：${reportFormData.topic || '未指定'}\n演示目的：${reportFormData.pptPurpose || '未指定'}\n受众：${reportFormData.audience || '通用'}\n演讲时长：${reportFormData.duration || '未指定'}\n页数：${reportFormData.pages || '10'}页左右\n结构偏好：${reportFormData.structureStyle || PPT_STRUCTURE_OPTIONS[0]}\n视觉风格：${reportFormData.visualStyle || PPT_VISUAL_OPTIONS[0]}\n详细程度：${reportFormData.detailLevel || DETAIL_LEVEL_OPTIONS[2]}\n必含页/模块：${listOrNone(reportFormData.pptModules)}\n核心观点：${reportFormData.keyPoints || '无'}\n数据/图表/素材：${reportFormData.dataAssets || '无'}\n行动号召/期望结果：${reportFormData.cta || '无'}\n请规划一份详细的PPT演示文稿结构：包含封面、目录、背景/问题、分析、方案、实施/里程碑、资源/预算、风险、总结/行动项、Q&A（若页数允许）。每页给出 1 句关键结论 + 3-6 条要点（完整句），并给出明确的可视化建议。`;
      } else if (reportType === 'email') {
          prompt = `[指令:起草邮件]\n收件人：${reportFormData.recipient || '未指定'}\n发件人身份：${reportFormData.senderRole || '未指定'}\n主题/意图：${reportFormData.intent || '未指定'}\n语气风格：${reportFormData.tone || '专业正式'}\n详细程度：${reportFormData.detailLevel || DETAIL_LEVEL_OPTIONS[2]}\n背景/上下文：${reportFormData.background || '无'}\n请求/行动：${reportFormData.request || '无'}\n截止时间/期望回复：${reportFormData.deadline || '无'}\n附件/参考：${reportFormData.attachments || '无'}\n必须包含要素：${listOrNone(reportFormData.emailElements)}\n关键信息：${reportFormData.keyPoints || '无'}\n请起草一封详细、可直接发送的邮件：分段清晰，包含背景 -> 诉求 -> 细节 -> 行动项 -> 时间节点 -> 礼貌结束语，并给出明确的行动清单。`;
      }
      handleSendMessage(prompt, false, { modelBackend: chosenBackend });
  };

  const handleShareClick = () => {
    if (!currentSessionId) return;
    const session = sessionList.find(s => s.id === currentSessionId);
    setShareModal({ isOpen: true, sessionId: currentSessionId, title: session ? session.title : '新聊天' });
  };

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
      setFeedbackState((prev) => trimIndexedState(prev, editingMessageIndex));
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

  const handleFeedback = (idx, type) => {
      setFeedbackState(prev => ({
          ...prev,
          [idx]: prev[idx] === type ? null : type
      }));
      // 在这里，您通常会调用 API 来记录反馈
  };

  const toggleFormArrayValue = (field, value) => {
      setReportFormData(prev => {
          const current = Array.isArray(prev[field]) ? prev[field] : [];
          const exists = current.includes(value);
          const next = exists ? current.filter((item) => item !== value) : [...current, value];
          return { ...prev, [field]: next };
      });
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
                  } catch (e) {
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
              } catch (e) {
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
          } catch (e) {}
      }
      setShowOnboarding(false);
      if (selectedModel !== 0) {
          handleModelChange(0);
          return;
      }
      handleNewChat();
  };

  const renderReportWizard = () => {
      if (reportStep === 'selection') {
        return (
            <div className="h-full w-full overflow-y-auto bg-gradient-to-b from-gray-50 via-white to-gray-100 dark:from-gray-950 dark:via-gray-950 dark:to-gray-900 p-5 md:p-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
                <div className="max-w-6xl mx-auto">
                <div className="text-center mb-10 md:mb-12">
                    <span className="inline-flex items-center rounded-full border border-gray-200 dark:border-gray-700 bg-white/80 dark:bg-gray-900/80 px-3 py-1 text-xs font-medium text-gray-500 dark:text-gray-300 mb-4">写作助手</span>
                    <h2 className="text-3xl md:text-4xl font-bold text-gray-900 dark:text-white mb-3">选择写作场景</h2>
                    <p className="text-gray-500 dark:text-gray-400">选择一个场景，为你生成更完整、更可执行的写作框架</p>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-5 md:gap-6 w-full">
                    <button onClick={() => { setReportType('report'); setReportStep('form'); }} className="group relative flex h-full flex-col items-start p-7 bg-white/90 dark:bg-gray-900/70 backdrop-blur rounded-3xl border border-gray-200/70 dark:border-gray-700/70 hover:border-blue-400 dark:hover:border-blue-500 hover:shadow-2xl hover:-translate-y-1 transition-all duration-300">
                        <div className="w-14 h-14 rounded-2xl bg-blue-50 dark:bg-blue-900/30 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform"><FileText size={28} className="text-blue-600 dark:text-blue-300" /></div>
                        <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-2 text-left">报告大纲</h3>
                        <p className="text-sm text-gray-500 dark:text-gray-400 text-left leading-relaxed">适用于年度总结、项目汇报、调研报告等长文档规划。</p>
                        <span className="mt-5 inline-flex items-center gap-1 text-xs font-semibold text-blue-600 dark:text-blue-300">立即开始 <ArrowRight size={13} /></span>
                    </button>
                    <button onClick={() => { setReportType('ppt'); setReportStep('form'); }} className="group relative flex h-full flex-col items-start p-7 bg-white/90 dark:bg-gray-900/70 backdrop-blur rounded-3xl border border-gray-200/70 dark:border-gray-700/70 hover:border-purple-400 dark:hover:border-purple-500 hover:shadow-2xl hover:-translate-y-1 transition-all duration-300">
                        <div className="w-14 h-14 rounded-2xl bg-purple-50 dark:bg-purple-900/30 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform"><Layout size={28} className="text-purple-600 dark:text-purple-300" /></div>
                        <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-2 text-left">PPT 大纲</h3>
                        <p className="text-sm text-gray-500 dark:text-gray-400 text-left leading-relaxed">自动规划演示文稿结构，分配页码，提炼每页核心观点。</p>
                        <span className="mt-5 inline-flex items-center gap-1 text-xs font-semibold text-purple-600 dark:text-purple-300">立即开始 <ArrowRight size={13} /></span>
                    </button>
                    <button onClick={() => { setReportType('email'); setReportStep('form'); }} className="group relative flex h-full flex-col items-start p-7 bg-white/90 dark:bg-gray-900/70 backdrop-blur rounded-3xl border border-gray-200/70 dark:border-gray-700/70 hover:border-green-400 dark:hover:border-green-500 hover:shadow-2xl hover:-translate-y-1 transition-all duration-300">
                        <div className="w-14 h-14 rounded-2xl bg-green-50 dark:bg-green-900/30 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform"><Mail size={28} className="text-green-600 dark:text-green-300" /></div>
                        <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-2 text-left">邮件起草</h3>
                        <p className="text-sm text-gray-500 dark:text-gray-400 text-left leading-relaxed">根据对象和语气，快速起草正式、得体的职场沟通邮件。</p>
                        <span className="mt-5 inline-flex items-center gap-1 text-xs font-semibold text-green-600 dark:text-green-300">立即开始 <ArrowRight size={13} /></span>
                    </button>
                </div>
                </div>
            </div>
        );
    }
    if (reportStep === 'form') {
        const inputClass = "w-full px-3.5 py-3 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl shadow-sm focus:ring-4 focus:ring-blue-500/10 focus:border-blue-500 outline-none transition-all text-gray-800 dark:text-gray-100 placeholder:text-gray-400";
        const labelClass = "block text-xs font-semibold tracking-wide uppercase text-gray-600 dark:text-gray-300 mb-1.5";
        return (
            <div className="h-full w-full overflow-y-auto px-3 py-4 md:px-6 md:py-6 bg-gradient-to-b from-gray-50 via-white to-gray-100 dark:from-gray-950 dark:via-gray-950 dark:to-gray-900 animate-in fade-in zoom-in-95 duration-300">
                <div className="w-full max-w-6xl mx-auto bg-white/95 dark:bg-gray-900/90 rounded-3xl shadow-xl border border-gray-100 dark:border-gray-800 overflow-hidden flex flex-col backdrop-blur">
                    <div className="px-5 md:px-6 py-4 border-b border-gray-100 dark:border-gray-800 flex items-center gap-3 bg-white/85 dark:bg-gray-900/80 backdrop-blur sticky top-0 z-10">
                        <button onClick={() => setReportStep('selection')} className="p-1.5 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg text-gray-500 transition-colors"><ArrowLeft size={20} /></button>
                        <div className="min-w-0">
                        <h3 className="text-lg font-bold text-gray-800 dark:text-white flex items-center gap-2">
                           {reportType === 'report' ? '配置报告参数' : (reportType === 'ppt' ? '配置 PPT 大纲' : '配置邮件信息')}
                        </h3>
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">填写越具体，生成结果越贴近你的业务语境</p>
                        </div>
                        <span className="ml-auto hidden md:inline-flex items-center rounded-full border border-gray-200 dark:border-gray-700 px-3 py-1 text-xs font-medium text-gray-500 dark:text-gray-300 bg-white dark:bg-gray-900">
                            {reportType === 'report' ? 'Report' : (reportType === 'ppt' ? 'Slides' : 'Email')}
                        </span>
                    </div>
                    <div className="p-6 md:p-7 custom-scrollbar space-y-5 xl:space-y-0 xl:grid xl:grid-cols-2 xl:gap-x-6 xl:gap-y-5">
                        <div className="xl:col-span-2 rounded-xl border border-gray-200/80 dark:border-gray-700 bg-gray-50/80 dark:bg-gray-800/40 px-4 py-3 text-xs text-gray-600 dark:text-gray-300">
                            建议先填写主题、受众、目标，再补充关键数据与约束条件。
                        </div>
                        <div className="xl:col-span-2">
                            <label className={labelClass}>模型选择</label>
                            <select
                                className={inputClass}
                                value={reportFormData.modelBackend || llmBackend}
                                onChange={e => setReportFormData({ ...reportFormData, modelBackend: e.target.value })}
                            >
                                <option value="local">本地模型（Qwen 2.5-coder）</option>
                                <option value="cloud">云端模型（DeepSeek）</option>
                            </select>
                        </div>
                        {reportType === 'report' && (
                            <>
                                <div><label className={labelClass}>报告主题</label><input className={inputClass} placeholder="例如：2024年度市场营销总结" value={reportFormData.topic || ''} onChange={e => setReportFormData({...reportFormData, topic: e.target.value})} autoFocus/></div>
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                    <div><label className={labelClass}>使用场景</label><input className={inputClass} placeholder="例如：部门内部汇报" value={reportFormData.scene || ''} onChange={e => setReportFormData({...reportFormData, scene: e.target.value})}/></div>
                                    <div><label className={labelClass}>受众/阅读者</label><input className={inputClass} placeholder="例如：部门经理" value={reportFormData.audience || ''} onChange={e => setReportFormData({...reportFormData, audience: e.target.value})}/></div>
                                </div>
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                    <div><label className={labelClass}>时间范围</label><input className={inputClass} placeholder="例如：2024 Q1-Q4 / 近6个月" value={reportFormData.timeRange || ''} onChange={e => setReportFormData({...reportFormData, timeRange: e.target.value})}/></div>
                                    <div><label className={labelClass}>业务范围/对象</label><input className={inputClass} placeholder="例如：华东区域 / 新客转化业务线" value={reportFormData.scope || ''} onChange={e => setReportFormData({...reportFormData, scope: e.target.value})}/></div>
                                </div>
                                <div><label className={labelClass}>报告目的/用途</label><input className={inputClass} placeholder="例如：复盘问题、制定年度策略、向管理层汇报" value={reportFormData.purpose || ''} onChange={e => setReportFormData({...reportFormData, purpose: e.target.value})}/></div>
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                    <div>
                                        <label className={labelClass}>报告风格</label>
                                        <select className={inputClass} value={reportFormData.reportStyle || REPORT_STYLE_OPTIONS[0]} onChange={e => setReportFormData({...reportFormData, reportStyle: e.target.value})}>
                                            {REPORT_STYLE_OPTIONS.map((opt) => <option key={opt}>{opt}</option>)}
                                        </select>
                                    </div>
                                    <div>
                                        <label className={labelClass}>详细程度</label>
                                        <select className={inputClass} value={reportFormData.detailLevel || DETAIL_LEVEL_OPTIONS[2]} onChange={e => setReportFormData({...reportFormData, detailLevel: e.target.value})}>
                                            {DETAIL_LEVEL_OPTIONS.map((opt) => <option key={opt}>{opt}</option>)}
                                        </select>
                                    </div>
                                </div>
                                <div>
                                    <label className={labelClass}>必含模块 (可多选)</label>
                                    <div className="flex flex-wrap gap-2">
                                        {REPORT_SECTION_OPTIONS.map((opt) => {
                                            const active = (reportFormData.reportModules || []).includes(opt);
                                            return (
                                                <button
                                                    type="button"
                                                    key={opt}
                                                    onClick={() => toggleFormArrayValue('reportModules', opt)}
                                                    className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-all ${active ? 'bg-blue-600 text-white border-blue-600 shadow-sm' : 'bg-white dark:bg-gray-900 text-gray-600 dark:text-gray-300 border-gray-200 dark:border-gray-700 hover:border-blue-400'}`}
                                                >
                                                    {opt}
                                                </button>
                                            );
                                        })}
                                    </div>
                                </div>
                                <div><label className={labelClass}>核心关键点 (可选)</label><textarea className={inputClass} rows={4} placeholder="列出报告中必须包含的数据、结论或重点..." value={reportFormData.keyPoints || ''} onChange={e => setReportFormData({...reportFormData, keyPoints: e.target.value})}/></div>
                                <div><label className={labelClass}>关键问题/假设 (可选)</label><textarea className={inputClass} rows={3} placeholder="例如：增长放缓的主要原因是什么？核心假设有哪些？" value={reportFormData.keyQuestions || ''} onChange={e => setReportFormData({...reportFormData, keyQuestions: e.target.value})}/></div>
                                <div><label className={labelClass}>数据/指标/素材 (可选)</label><textarea className={inputClass} rows={3} placeholder="例如：GMV、CAC、转化率、投放成本、关键样本..." value={reportFormData.dataMetrics || ''} onChange={e => setReportFormData({...reportFormData, dataMetrics: e.target.value})}/></div>
                                <div><label className={labelClass}>约束/风险关注 (可选)</label><textarea className={inputClass} rows={3} placeholder="例如：预算上限、合规要求、资源受限等" value={reportFormData.constraints || ''} onChange={e => setReportFormData({...reportFormData, constraints: e.target.value})}/></div>
                                <div><label className={labelClass}>预期结论/建议方向 (可选)</label><textarea className={inputClass} rows={3} placeholder="例如：优化渠道结构，推进自动化，控制成本..." value={reportFormData.expectedOutcome || ''} onChange={e => setReportFormData({...reportFormData, expectedOutcome: e.target.value})}/></div>
                            </>
                        )}
                        {reportType === 'ppt' && (
                            <>
                                <div><label className={labelClass}>演示主题</label><input className={inputClass} placeholder="例如：新产品发布会演示" value={reportFormData.topic || ''} onChange={e => setReportFormData({...reportFormData, topic: e.target.value})} autoFocus/></div>
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                    <div><label className={labelClass}>预计页数</label><input className={inputClass} placeholder="例如：10-15页" value={reportFormData.pages || ''} onChange={e => setReportFormData({...reportFormData, pages: e.target.value})}/></div>
                                    <div><label className={labelClass}>听众/背景</label><input className={inputClass} placeholder="例如：潜在客户、管理层" value={reportFormData.audience || ''} onChange={e => setReportFormData({...reportFormData, audience: e.target.value})}/></div>
                                </div>
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                    <div><label className={labelClass}>演示目的</label><input className={inputClass} placeholder="例如：争取预算/对外路演/内部复盘" value={reportFormData.pptPurpose || ''} onChange={e => setReportFormData({...reportFormData, pptPurpose: e.target.value})}/></div>
                                    <div><label className={labelClass}>演讲时长</label><input className={inputClass} placeholder="例如：15-20分钟" value={reportFormData.duration || ''} onChange={e => setReportFormData({...reportFormData, duration: e.target.value})}/></div>
                                </div>
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                    <div>
                                        <label className={labelClass}>结构偏好</label>
                                        <select className={inputClass} value={reportFormData.structureStyle || PPT_STRUCTURE_OPTIONS[0]} onChange={e => setReportFormData({...reportFormData, structureStyle: e.target.value})}>
                                            {PPT_STRUCTURE_OPTIONS.map((opt) => <option key={opt}>{opt}</option>)}
                                        </select>
                                    </div>
                                    <div>
                                        <label className={labelClass}>视觉风格</label>
                                        <select className={inputClass} value={reportFormData.visualStyle || PPT_VISUAL_OPTIONS[0]} onChange={e => setReportFormData({...reportFormData, visualStyle: e.target.value})}>
                                            {PPT_VISUAL_OPTIONS.map((opt) => <option key={opt}>{opt}</option>)}
                                        </select>
                                    </div>
                                </div>
                                <div>
                                    <label className={labelClass}>详细程度</label>
                                    <select className={inputClass} value={reportFormData.detailLevel || DETAIL_LEVEL_OPTIONS[2]} onChange={e => setReportFormData({...reportFormData, detailLevel: e.target.value})}>
                                        {DETAIL_LEVEL_OPTIONS.map((opt) => <option key={opt}>{opt}</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label className={labelClass}>必含页/模块 (可多选)</label>
                                    <div className="flex flex-wrap gap-2">
                                        {PPT_SECTION_OPTIONS.map((opt) => {
                                            const active = (reportFormData.pptModules || []).includes(opt);
                                            return (
                                                <button
                                                    type="button"
                                                    key={opt}
                                                    onClick={() => toggleFormArrayValue('pptModules', opt)}
                                                    className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-all ${active ? 'bg-purple-600 text-white border-purple-600 shadow-sm' : 'bg-white dark:bg-gray-900 text-gray-600 dark:text-gray-300 border-gray-200 dark:border-gray-700 hover:border-purple-400'}`}
                                                >
                                                    {opt}
                                                </button>
                                            );
                                        })}
                                    </div>
                                </div>
                                <div><label className={labelClass}>核心观点/关键信息 (可选)</label><textarea className={inputClass} rows={4} placeholder="简述希望强调的关键结论、价值主张或数据..." value={reportFormData.keyPoints || ''} onChange={e => setReportFormData({...reportFormData, keyPoints: e.target.value})}/></div>
                                <div><label className={labelClass}>数据/图表/素材 (可选)</label><textarea className={inputClass} rows={3} placeholder="例如：增长曲线、市场份额、客户案例、竞品对标..." value={reportFormData.dataAssets || ''} onChange={e => setReportFormData({...reportFormData, dataAssets: e.target.value})}/></div>
                                <div><label className={labelClass}>行动号召/期望结果 (可选)</label><textarea className={inputClass} rows={3} placeholder="例如：批准预算、确认方案、推进试点" value={reportFormData.cta || ''} onChange={e => setReportFormData({...reportFormData, cta: e.target.value})}/></div>
                            </>
                        )}
                        {reportType === 'email' && (
                            <>
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                    <div><label className={labelClass}>收件人称呼/角色</label><input className={inputClass} placeholder="例如：李总、HR部门" value={reportFormData.recipient || ''} onChange={e => setReportFormData({...reportFormData, recipient: e.target.value})} autoFocus/></div>
                                    <div><label className={labelClass}>发件人身份/部门</label><input className={inputClass} placeholder="例如：市场部 张三" value={reportFormData.senderRole || ''} onChange={e => setReportFormData({...reportFormData, senderRole: e.target.value})}/></div>
                                </div>
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                    <div><label className={labelClass}>语气风格</label>
                                        <select className={inputClass} value={reportFormData.tone || '专业正式'} onChange={e => setReportFormData({...reportFormData, tone: e.target.value})}>
                                            <option>专业正式</option>
                                            <option>委婉客气</option>
                                            <option>热情积极</option>
                                            <option>严肃直接</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label className={labelClass}>详细程度</label>
                                        <select className={inputClass} value={reportFormData.detailLevel || DETAIL_LEVEL_OPTIONS[2]} onChange={e => setReportFormData({...reportFormData, detailLevel: e.target.value})}>
                                            {DETAIL_LEVEL_OPTIONS.map((opt) => <option key={opt}>{opt}</option>)}
                                        </select>
                                    </div>
                                </div>
                                <div><label className={labelClass}>邮件主题/意图</label><input className={inputClass} placeholder="例如：申请下周三调休" value={reportFormData.intent || ''} onChange={e => setReportFormData({...reportFormData, intent: e.target.value})}/></div>
                                <div><label className={labelClass}>背景/上下文 (可选)</label><textarea className={inputClass} rows={3} placeholder="说明事件背景、当前进展或原因..." value={reportFormData.background || ''} onChange={e => setReportFormData({...reportFormData, background: e.target.value})}/></div>
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                    <div><label className={labelClass}>请求/行动 (可选)</label><input className={inputClass} placeholder="例如：请批准、请协助、请确认" value={reportFormData.request || ''} onChange={e => setReportFormData({...reportFormData, request: e.target.value})}/></div>
                                    <div><label className={labelClass}>截止时间/期望回复 (可选)</label><input className={inputClass} placeholder="例如：请于周五前反馈" value={reportFormData.deadline || ''} onChange={e => setReportFormData({...reportFormData, deadline: e.target.value})}/></div>
                                </div>
                                <div><label className={labelClass}>附件/参考 (可选)</label><input className={inputClass} placeholder="例如：附件为预算表/方案PPT" value={reportFormData.attachments || ''} onChange={e => setReportFormData({...reportFormData, attachments: e.target.value})}/></div>
                                <div>
                                    <label className={labelClass}>必须包含要素 (可多选)</label>
                                    <div className="flex flex-wrap gap-2">
                                        {EMAIL_ELEMENT_OPTIONS.map((opt) => {
                                            const active = (reportFormData.emailElements || []).includes(opt);
                                            return (
                                                <button
                                                    type="button"
                                                    key={opt}
                                                    onClick={() => toggleFormArrayValue('emailElements', opt)}
                                                    className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-all ${active ? 'bg-green-600 text-white border-green-600 shadow-sm' : 'bg-white dark:bg-gray-900 text-gray-600 dark:text-gray-300 border-gray-200 dark:border-gray-700 hover:border-green-400'}`}
                                                >
                                                    {opt}
                                                </button>
                                            );
                                        })}
                                    </div>
                                </div>
                                <div><label className={labelClass}>关键信息点</label><textarea className={inputClass} rows={4} placeholder="需要包含的具体细节，例如时间、地点、原因..." value={reportFormData.keyPoints || ''} onChange={e => setReportFormData({...reportFormData, keyPoints: e.target.value})}/></div>
                            </>
                        )}
                    </div>
                    <div className="px-5 md:px-6 py-4 border-t border-gray-100 dark:border-gray-800 bg-white/80 dark:bg-gray-900/80 backdrop-blur flex items-center justify-between">
                        <span className="hidden md:block text-xs text-gray-500 dark:text-gray-400">可先生成一版，再在对话区继续迭代细化。</span>
                        <button onClick={handleSubmitReportForm} className={`px-6 py-2.5 rounded-xl font-medium text-white shadow-lg shadow-blue-500/20 transition-all active:scale-95 flex items-center gap-2 ${reportType === 'report' ? 'bg-blue-600 hover:bg-blue-700' : (reportType === 'ppt' ? 'bg-purple-600 hover:bg-purple-700' : 'bg-green-600 hover:bg-green-700')}`}>
                            <Sparkles size={18} /> 开始生成
                        </button>
                    </div>
                </div>
            </div>
        );
    }
  };

  const getPanelStyles = () => {
      if (isMeetingMode) return { border: 'border-gray-200 dark:border-gray-800', headerBg: 'bg-gray-50/80 dark:bg-gray-900/60', headerText: 'text-gray-800 dark:text-gray-200', btnBg: 'bg-gray-900 hover:bg-black', textareaBg: 'bg-white/60 dark:bg-gray-900/60' };
      if (isAuditMode) return { border: 'border-teal-100 dark:border-teal-900/50', headerBg: 'bg-teal-50/50 dark:bg-teal-900/20', headerText: 'text-teal-800 dark:text-teal-300', btnBg: 'bg-teal-600 hover:bg-teal-700', textareaBg: 'bg-white/50 dark:bg-gray-900/50' };
      return { border: 'border-orange-100 dark:border-orange-900/50', headerBg: 'bg-orange-50/50 dark:bg-orange-900/20', headerText: 'text-orange-800 dark:text-orange-300', btnBg: 'bg-orange-600 hover:bg-orange-700', textareaBg: 'bg-white/50 dark:bg-gray-900/50' };
  };
  const panelStyle = getPanelStyles();
  const showEmptyState = chatHistory.length === 0 && !showContentPanel && !panelContent && !isUploadingFile && pendingFiles.length === 0;
  const greetingName = userProfile?.name && userProfile.name !== 'User' ? userProfile.name : '';
  const greetingText = greetingName ? `${greetingName}，你好` : '你好';
  const mobileQuickActions = [
    { key: 'image', label: '公司/业务介绍', prompt: '用数据库查询一下公司的基本信息（专业语气）', Icon: ImageIcon },
    { key: 'video', label: '流程怎么走', prompt: '请用步骤说明：合同审批流程通常包含哪些节点？每个节点的输入输出是什么？', Icon: Play },
    { key: 'write', label: '合规与风险提示', prompt: '帮我列一份“对外合同”常见风险点清单，并给出对应的规避建议（条款层面）', Icon: FileText },
    { key: 'learn', label: '数据库：客户TOP统计', prompt: '查询订单金额TOP10客户，并按客户汇总（订单数/总额/最近下单日期）', Icon: BookOpen },
    { key: 'energy', label: 'HR/行政制度问答', prompt: '请给一个通用的“请假/报销/出差”制度说明模板，要求清晰可执行', Icon: Sparkles },
  ];

  const emptyStateContent = isMobileViewport ? (
    <div className="w-full -mx-4 px-6 flex flex-col justify-start pt-4 pb-2">
      <div>
        <div className="home-hero-kicker text-base text-gray-500 dark:text-gray-400">{greetingText}</div>
        <h2 className="home-hero-title mt-2 text-[26px] leading-tight text-gray-900 dark:text-white">
          需要我为你做些什么？
        </h2>
      </div>
      <div className="mt-6 flex flex-col gap-3">
        {mobileQuickActions.map(({ key, label, prompt, Icon }) => (
          <button
            key={key}
            type="button"
            onClick={() => setInputValue(prompt)}
            className="w-fit max-w-[85%] inline-flex items-center gap-2 px-4 py-2.5 rounded-full bg-white/90 dark:bg-gray-900/60 border border-gray-200/80 dark:border-gray-700 text-sm font-medium text-gray-700 dark:text-gray-200 shadow-sm hover:shadow-md hover:bg-white dark:hover:bg-gray-900 transition-all"
          >
            <Icon size={16} className="text-gray-500 dark:text-gray-400" />
            {label}
          </button>
        ))}
      </div>
    </div>
  ) : (
    <div className="h-full flex flex-col items-center justify-center pt-4 sm:pt-5">
       <div className="w-16 h-16 bg-white dark:bg-gray-800 rounded-full shadow-sm border border-gray-100 dark:border-gray-700 flex items-center justify-center mb-6">{React.createElement(selectedModelInfo.icon, { size: 32, className: "text-gray-800 dark:text-white" })}</div>
       <h2 className="home-hero-title text-2xl text-gray-800 dark:text-white mb-8 text-center px-4">
           {isMeetingMode ? "上传录音，一键总结" : (isAuditMode ? "智能审单 & 风险合规检测" : (isOCRMode ? "图片/PDF 转文字 & 智能分析" : "今天有什么计划？"))}
       </h2>
       <Suggestions onSuggestionClick={handleSuggestionClick} />
     </div>
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
                    } catch (err) {
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

  return (
    <div className="dashboard-unified-dark flex h-screen bg-white dark:bg-gray-950 font-sans text-gray-900 dark:text-gray-100 overflow-hidden animate-in fade-in duration-500 transition-colors">
      {isDragActive && (
        <div className="pointer-events-none fixed inset-0 z-[130] flex items-center justify-center bg-black/55 backdrop-blur-[2px] animate-in fade-in duration-150">
          <div className="relative flex flex-col items-center px-8 py-10 rounded-3xl border border-blue-300/25 bg-[#121826]/85 shadow-[0_30px_80px_rgba(0,0,0,0.55)]">
            <div className="relative h-24 w-28 mb-4">
              <div className="absolute left-1 top-3 w-12 h-12 rounded-2xl bg-indigo-300/95 text-indigo-900 flex items-center justify-center rotate-[-14deg] shadow-lg">
                <FileText size={20} />
              </div>
              <div className="absolute right-1 top-5 w-12 h-12 rounded-2xl bg-blue-300/95 text-blue-900 flex items-center justify-center rotate-[14deg] shadow-lg">
                <ImageIcon size={20} />
              </div>
              <div className="absolute left-1/2 -translate-x-1/2 bottom-0 w-14 h-14 rounded-2xl bg-blue-600 text-white flex items-center justify-center shadow-xl animate-pulse">
                <FileUp size={24} />
              </div>
            </div>
            <div className="text-3xl font-bold text-white tracking-tight">添加任意内容</div>
            <div className="mt-2 text-base text-blue-100/90">将文件拖放到此处，松手即可添加到对话中</div>
          </div>
        </div>
      )}

      {isOcrSummaryOpen && (
        <div className="fixed inset-0 z-[70] bg-black/40 backdrop-blur-[2px] flex items-center justify-center px-4 py-6">
          <div className="w-full max-w-3xl h-[75vh] bg-white dark:bg-gray-900 rounded-2xl shadow-2xl border border-gray-100 dark:border-gray-800 flex flex-col overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 dark:border-gray-800">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-full bg-indigo-50 dark:bg-indigo-900/40 text-indigo-600 dark:text-indigo-300 flex items-center justify-center">
                  <Sparkles size={16} />
                </div>
                <div className="text-sm font-semibold text-gray-900 dark:text-white">OCR 总结</div>
              </div>
              <button
                type="button"
                onClick={handleCloseOcrSummary}
                className="p-2 rounded-full text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800"
                title="关闭"
              >
                <X size={18} />
              </button>
            </div>
            <div className="px-4 py-2 border-b border-gray-100 dark:border-gray-800">
              {ocrSummaryFirstDone ? (
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                    <Cpu size={13} />
                    <span>总结模型</span>
                    <select
                      value={ocrSummaryBackend}
                      onChange={(e) => setOcrSummaryBackend(e.target.value)}
                      disabled={isOcrSummaryLoading}
                      className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-2 py-1 text-xs text-gray-700 dark:text-gray-200 outline-none focus:ring-2 focus:ring-indigo-500/20"
                    >
                      {OCR_SUMMARY_BACKEND_OPTIONS.map((item) => (
                        <option key={item.value} value={item.value}>{item.label}</option>
                      ))}
                    </select>
                  </div>
                  <button
                    type="button"
                    onClick={handleRegenerateOcrSummary}
                    disabled={isOcrSummaryLoading}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium border border-indigo-200 dark:border-indigo-700 text-indigo-600 dark:text-indigo-300 hover:bg-indigo-50/80 dark:hover:bg-indigo-900/30 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    重新总结
                  </button>
                </div>
              ) : (
                <div className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
                  <Cpu size={13} />
                  <span>首次总结默认使用 Qwen 2.5-coder</span>
                </div>
              )}
            </div>
            <div ref={ocrSummaryScrollRef} className="flex-1 overflow-auto px-4 py-3 space-y-4">
              {ocrSummaryMessages.length === 0 && (
                <div className="text-sm text-gray-400">正在生成总结...</div>
              )}
              {ocrSummaryMessages.map((msg, idx) => (
                <div key={`ocr-summary-${idx}`} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm leading-relaxed ${msg.role === 'user' ? 'bg-gray-900 text-white' : 'bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-100'}`}>
                    {msg.role === 'assistant' ? (
                      <Suspense fallback={<PlainTextRenderer content={msg.content} className="text-gray-800 dark:text-gray-100" />}>
                        <MarkdownRenderer content={msg.content} streaming={isOcrSummaryLoading && idx === ocrSummaryMessages.length - 1} />
                      </Suspense>
                    ) : (
                      msg.content
                    )}
                  </div>
                </div>
              ))}
              {isOcrSummaryLoading && (
                <div className="text-xs text-gray-400">模型正在生成...</div>
              )}
            </div>
            <div className="border-t border-gray-100 dark:border-gray-800 px-4 py-3">
              <div className="flex items-end gap-2">
                <textarea
                  className="flex-1 min-h-[44px] max-h-[120px] resize-none rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400"
                  placeholder="继续追问文档内容..."
                  value={ocrSummaryInput}
                  onChange={(e) => setOcrSummaryInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      sendOcrSummaryMessage(ocrSummaryInput);
                      setOcrSummaryInput('');
                    }
                  }}
                />
                <button
                  type="button"
                  onClick={() => {
                    sendOcrSummaryMessage(ocrSummaryInput);
                    setOcrSummaryInput('');
                  }}
                  disabled={!ocrSummaryInput.trim() || isOcrSummaryLoading}
                  className="px-4 py-2 rounded-xl bg-indigo-600 text-white text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  发送
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
      {showOnboarding && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/30 backdrop-blur-[2px] px-4">
          <div className="w-full max-w-xl rounded-2xl border border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900 shadow-2xl p-5 sm:p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-9 h-9 rounded-full bg-green-500 text-white flex items-center justify-center">
                <Bot size={18} />
              </div>
              <div>
                <div className="text-sm font-semibold text-gray-900 dark:text-white">快速上手</div>
                <div className="text-xs text-gray-500 dark:text-gray-400">入口位置一眼看懂</div>
              </div>
            </div>
            <div className="space-y-3">
              {ONBOARDING_MESSAGES.map((msg, idx) => (
                <div key={`onboarding-${idx}`} className="rounded-xl border border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/60 px-4 py-3 text-sm text-gray-700 dark:text-gray-200 leading-relaxed">
                  {msg}
                </div>
              ))}
            </div>
            <div className="mt-4 text-right">
              <a
                href="#"
                onClick={handleOnboardingStart}
                className="text-sm font-medium text-blue-600 hover:text-blue-700 hover:underline"
              >
                立即开始
              </a>
            </div>
          </div>
        </div>
      )}
      <MobileSidebar
        isOpen={isMobileSidebarOpen}
        onClose={() => setIsMobileSidebarOpen(false)}
        userProfile={userProfile}
        sessionList={sessionList}
        currentSessionId={currentSessionId}
        onSessionClick={handleSessionClick}
        onNewChat={handleNewChat}
        onLogout={onLogout}
        onShowAppearance={handleOpenSettingsModal}
        currentMode={currentMode}
        onModeChange={onModeChange}
        isLoading={isProfileLoading || isSessionsLoading}
        selectedModel={selectedModel}
      />

      <Sidebar
        isOpen={isSidebarOpen}
        onClose={() => setIsSidebarOpen(false)}
        onNewChat={handleNewChat}
        sessionList={sessionList}
        currentSessionId={currentSessionId}
        onSessionClick={handleSessionClick}
        userProfile={userProfile}
        onLogout={onLogout}
        onShowAppearance={handleOpenSettingsModal}
        currentMode={currentMode}
        onModeChange={onModeChange}
        isLoadingSessions={isSessionsLoading}
        isLoadingProfile={isProfileLoading}
        selectedModel={selectedModel}
      />

      <div className="dashboard-main-surface flex-1 flex flex-col h-full relative bg-white dark:bg-gray-950 min-w-0 transition-colors">
        {/* Mo 移动标头 */}
        <div className="dashboard-topbar md:hidden fixed top-0 left-0 right-0 flex items-center justify-between px-4 py-3 bg-white/95 dark:bg-gray-950/95 backdrop-blur-sm border-b border-gray-100 dark:border-gray-800 z-40">
          <div className="flex items-center gap-3">
            <button onClick={() => setIsMobileSidebarOpen(true)} className="text-gray-600 dark:text-gray-300 p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-md transition-colors"><PanelLeftOpen size={24} /></button>
            <div className="relative" ref={mobileDropdownRef}>
                <button onClick={() => setIsMobileModelDropdownOpen(!isMobileModelDropdownOpen)} className="flex items-center gap-1.5 font-bold text-gray-800 dark:text-white text-lg active:opacity-70 transition-opacity">
                  {selectedModelInfo?.name.split(' ')[0]} <span className="text-xs font-normal text-gray-500 bg-gray-100 dark:bg-gray-800 dark:text-gray-400 px-1.5 py-0.5 rounded-full">2.0</span> <ChevronDown size={16} className={`text-gray-400 transition-transform duration-200 ${isMobileModelDropdownOpen ? 'rotate-180' : ''}`} />
                </button>
                {isMobileModelDropdownOpen && (
                  <div className="dashboard-dropdown absolute top-full left-0 mt-2 w-[min(88vw,280px)] max-h-[65vh] overflow-y-auto bg-white dark:bg-gray-800 rounded-xl shadow-xl border border-gray-100 dark:border-gray-700 animate-in fade-in slide-in-from-top-2 duration-200 z-50">
                    <div className="p-1.5 space-y-0.5">
                      {models.map((model) => (
                        <div key={model.id} className={`flex items-center gap-3 px-3 py-3 rounded-lg cursor-pointer transition-colors ${selectedModel === model.id ? 'bg-gray-100 dark:bg-gray-700' : 'hover:bg-gray-50 dark:hover:bg-gray-700/50'}`} onClick={() => { handleModelChange(model.id); setIsMobileModelDropdownOpen(false); }}>
                          <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${selectedModel === model.id ? 'bg-black dark:bg-white text-white dark:text-black' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'}`}><model.icon size={18} /></div>
                          <div className="flex-1"><div className={`text-sm font-medium ${selectedModel === model.id ? 'text-gray-900 dark:text-white' : 'text-gray-700 dark:text-gray-300'}`}>{model.name}</div></div>
                          {selectedModel === model.id && <Check size={16} className="text-gray-900 dark:text-white" />}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {currentSessionId && <button onClick={handleShareClick} className="text-gray-600 dark:text-gray-300 p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-md transition-colors"><Share2 size={24} /></button>}
            <button onClick={handleNewChat} className="text-gray-600 dark:text-gray-300 p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-md transition-colors"><Plus size={24} /></button>
          </div>
        </div>

        {/* De 桌面标题 */}
        <div className="dashboard-topbar hidden md:flex items-center p-3 sticky top-0 z-30 bg-white/80 dark:bg-gray-950/80 backdrop-blur-sm border-b border-gray-100 dark:border-gray-800/50">
          <div className="flex items-center">
              {!isSidebarOpen && <button onClick={() => setIsSidebarOpen(true)} className="mr-3 p-2 text-gray-500 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"><PanelLeftOpen size={20} /></button>}
              <div className="relative" ref={dropdownRef}>
                <button className="flex items-center gap-2 px-3 py-2 rounded-xl hover:bg-gray-100/80 dark:hover:bg-gray-800/80 transition-colors text-lg font-semibold text-gray-700 dark:text-gray-200 group" onClick={() => setIsDropdownOpen(!isDropdownOpen)}>
                  {selectedModelInfo?.name.split(' ')[0]} <span className="text-gray-400 text-base font-normal">2.0</span> <ChevronDown size={16} className={`text-gray-400 transition-transform duration-200 ${isDropdownOpen ? 'rotate-180' : ''}`} />
                </button>
                {isDropdownOpen && (
                  <div className="dashboard-dropdown absolute top-full left-0 mt-2 w-[320px] bg-white dark:bg-gray-800 rounded-xl shadow-xl border border-gray-100 dark:border-gray-700 overflow-hidden animate-in fade-in slide-in-from-top-2 duration-200 z-50">
                    <div className="p-1.5 space-y-0.5">
                      {models.map((model) => (
                        <div key={model.id} className={`flex items-center gap-3 px-3 py-3 rounded-lg cursor-pointer transition-colors ${selectedModel === model.id ? 'bg-gray-100 dark:bg-gray-700' : 'hover:bg-gray-50 dark:hover:bg-gray-700/50'}`} onClick={() => { handleModelChange(model.id); setIsDropdownOpen(false); }}>
                          <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${selectedModel === model.id ? 'bg-black dark:bg-white text-white dark:text-black' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'}`}><model.icon size={18} /></div>
                          <div className="flex-1"><div className={`text-sm font-medium ${selectedModel === model.id ? 'text-gray-900 dark:text-white' : 'text-gray-700 dark:text-gray-300'}`}>{model.name}</div></div>
                          {selectedModel === model.id && <Check size={16} className="text-gray-900 dark:text-white" />}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
          </div>
          <div className="ml-auto flex items-center gap-2">
            {currentSessionId && <button onClick={handleShareClick} className="p-2 text-gray-500 hover:text-blue-600 dark:hover:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg transition-colors flex items-center gap-2"><Share2 size={20} /><span className="text-sm font-medium hidden lg:inline">分享</span></button>}
          </div>
        </div>

        {/* UI 隐藏文件输入（共享） */}
        <input
          type="file"
          className="hidden"
          ref={fileInputRef}
          onChange={handleFileSelect}
          disabled={isUploadingFile}
          multiple={!isAuditMode}
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
              {shouldRenderPanel && (
                  <Suspense fallback={
                      <div className={`dashboard-pane w-full ${isAuditSinglePane ? 'md:w-full md:border-r-0' : 'md:w-1/2 md:border-r'} flex flex-col flex-shrink-0 border-b md:border-b-0 border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 transition-all duration-300 ${panelStyle.border} shadow-sm z-20`}>
                          <div className={`px-4 py-3 border-b flex justify-between items-center ${panelStyle.headerBg} ${panelStyle.border}`}>
                              <div className="h-4 w-40 bg-gray-200 dark:bg-gray-800 rounded animate-pulse"></div>
                              <div className="h-3 w-16 bg-gray-200 dark:bg-gray-800 rounded animate-pulse"></div>
                          </div>
                          <div className="flex-1 p-4">
                              <div className="h-5 w-full bg-gray-100 dark:bg-gray-800 rounded animate-pulse"></div>
                              <div className="h-5 w-5/6 bg-gray-100 dark:bg-gray-800 rounded animate-pulse mt-3"></div>
                              <div className="h-5 w-2/3 bg-gray-100 dark:bg-gray-800 rounded animate-pulse mt-3"></div>
                          </div>
                      </div>
                  }>
                      <ModePanel
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
                          handleManualSave={handleManualSave}
                          handleExportWord={handleExportWord}
                          handleGenerateSummary={handleGenerateSummary}
                          onOcrStore={handleOcrStore}
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
                          onAuditFileSelect={handleAuditFileSelect}
                          onAuditReset={resetAuditState}
                          onAuditErpAction={handleAuditErpAction}
                          isAuditErpActionLoading={isAuditErpActionLoading}
                          fullWidth={isAuditSinglePane}
                      />
                  </Suspense>
              )}

              {shouldRenderChat && (
              <div className={`flex flex-col h-full relative transition-all duration-300 ${showContentPanel ? 'w-full md:w-1/2' : 'w-full'}`}>
                  {isReportMode && chatHistory.length === 0 ? (
                      renderReportWizard()
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
                                      onClick={() => setVisibleMessageCount((count) => Math.min(chatHistory.length, count + INITIAL_MESSAGE_COUNT))}
                                      className="text-xs font-medium text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 px-3 py-1.5 rounded-full border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                                    >
                                      加载更多
                                    </button>
                                  </div>
                                )}
                                {visibleMessages.map((msg, idx) => {
                                  const messageIndex = chatHistory.length - visibleMessages.length + idx;
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
                                  <div key={messageIndex} className={`flex flex-col gap-1 ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
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
                                                      className={`p-1.5 rounded-md transition-colors hover:bg-gray-100 dark:hover:bg-gray-800 ${feedbackState[messageIndex] === 'up' ? 'text-green-500 bg-green-50 dark:bg-green-900/20' : 'text-gray-400 dark:text-gray-500'}`}
                                                      title="有帮助"
                                                  >
                                                      <ThumbsUp size={14} />
                                                  </button>

                                                  <button
                                                      onClick={() => handleFeedback(messageIndex, 'down')}
                                                      className={`p-1.5 rounded-md transition-colors hover:bg-gray-100 dark:hover:bg-gray-800 ${feedbackState[messageIndex] === 'down' ? 'text-red-500 bg-red-50 dark:bg-red-900/20' : 'text-gray-400 dark:text-gray-500'}`}
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
                                        <BookOpen size={14} className="text-blue-600 dark:text-blue-400" /> <span>引用文档模式已开启</span>
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
                                                <button
                                                    onClick={() => { if (fileInputRef.current) fileInputRef.current.click(); setIsPlusMenuOpen(false); }}
                                                    className="flex items-center gap-3 px-3 py-2.5 hover:bg-gray-100 dark:hover:bg-gray-700/50 rounded-xl text-left text-sm font-medium text-gray-700 dark:text-gray-200 transition-colors group"
                                                >
                                                    <div className="w-8 h-8 rounded-full bg-orange-50 dark:bg-orange-900/20 text-orange-600 dark:text-orange-400 flex items-center justify-center group-hover:scale-110 transition-transform">
                                                        <FileUp size={16} />
                                                    </div>
                                                    添加文件
                                                </button>

                                                <button
                                                    onClick={() => { onModeChange(isRAGMode ? 'general' : 'rag'); setIsPlusMenuOpen(false); }}
                                                    className="flex items-center gap-3 px-3 py-2.5 hover:bg-gray-100 dark:hover:bg-gray-700/50 rounded-xl text-left text-sm font-medium text-gray-700 dark:text-gray-200 transition-colors group"
                                                >
                                                    <div className={`w-8 h-8 rounded-full flex items-center justify-center group-hover:scale-110 transition-transform ${isRAGMode ? 'bg-blue-100 text-blue-600' : 'bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400'}`}>
                                                        {isRAGMode ? <BookOpen size={16} fill="currentColor" /> : <BookOpen size={16} />}
                                                    </div>
                                                    <div className="flex-1 flex items-center justify-between">
                                                        引用文档
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
            <SettingsModal
              isOpen={settingsModalState.isOpen}
              initialCategory={settingsModalState.category}
              onClose={() => setSettingsModalState((prev) => ({ ...prev, isOpen: false }))}
              userProfile={userProfile}
              onLogout={onLogout}
              onSettingsChange={(next) => setAppSettings(normalizeAppSettings(next || DEFAULT_APP_SETTINGS))}
            />
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



