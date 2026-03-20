import React, { Suspense, useEffect, useRef, useState } from 'react';
import {
  Zap,
  ScanText,
  ClipboardCheck,
  Loader2,
  FileUp,
  ChevronDown,
  CheckCircle2,
  AlertTriangle,
  Save,
  Database,
  Download,
  Sparkles,
  Play,
  Pause,
  RotateCcw,
  Volume2,
  VolumeX,
  Volume1,
  Search,
  Mic,
  User,
} from 'lucide-react';

const MarkdownRenderer = React.lazy(() => import('./MarkdownRenderer'));
const AuditWorkspace = React.lazy(() => import('./AuditWorkspace'));
const DEFAULT_PANEL_STYLE = {
  border: 'border-gray-200 dark:border-gray-800',
  headerBg: 'bg-gray-50/50 dark:bg-gray-900/20',
  headerText: 'text-gray-800 dark:text-gray-300',
  btnBg: 'bg-gray-900 hover:bg-black',
  textareaBg: 'bg-white/50 dark:bg-gray-900/50',
};

const AudioPlayer = ({ src }) => {
  const audioRef = useRef(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [duration, setDuration] = useState(0);
  const [speed, setSpeed] = useState(1);
  const [volume, setVolume] = useState(1);
  const [isMuted, setIsMuted] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

  const speeds = [1.0, 1.25, 1.5, 2.0];

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const updateTime = () => {
      if (!isDragging) setProgress(audio.currentTime);
    };
    const updateDuration = () => setDuration(audio.duration);
    const onEnded = () => {
      setIsPlaying(false);
      if (audio.duration) setProgress(audio.duration);
    };

    audio.addEventListener('timeupdate', updateTime);
    audio.addEventListener('loadedmetadata', updateDuration);
    audio.addEventListener('ended', onEnded);

    return () => {
      audio.removeEventListener('timeupdate', updateTime);
      audio.removeEventListener('loadedmetadata', updateDuration);
      audio.removeEventListener('ended', onEnded);
    };
  }, [src, isDragging]);

  useEffect(() => {
    if (audioRef.current) audioRef.current.volume = isMuted ? 0 : volume;
  }, [volume, isMuted]);

  const togglePlay = () => {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
    } else {
      if (progress >= duration) {
        audioRef.current.currentTime = 0;
        setProgress(0);
      }
      audioRef.current.play();
    }
    setIsPlaying(!isPlaying);
  };

  const handleSeekStart = () => setIsDragging(true);
  const handleProgressChange = (e) => {
    const newTime = Number(e.target.value);
    setProgress(newTime);
    if (audioRef.current) audioRef.current.currentTime = newTime;
  };
  const handleSeekEnd = (e) => {
    setIsDragging(false);
    const newTime = Number(e.target.value);
    if (audioRef.current) {
      audioRef.current.currentTime = newTime;
      if (isPlaying) audioRef.current.play();
    }
  };

  const toggleSpeed = () => {
    const nextIdx = (speeds.indexOf(speed) + 1) % speeds.length;
    const newSpeed = speeds[nextIdx];
    setSpeed(newSpeed);
    if (audioRef.current) audioRef.current.playbackRate = newSpeed;
  };

  const toggleMute = () => setIsMuted(!isMuted);
  const handleVolumeChange = (e) => {
    const val = Number(e.target.value);
    setVolume(val);
    if (val > 0 && isMuted) setIsMuted(false);
  };

  const formatTime = (t) => {
    if (!t || isNaN(t)) return "00:00";
    const mins = Math.floor(t / 60);
    const secs = Math.floor(t % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="flex flex-col gap-3 w-full select-none bg-white/70 dark:bg-gray-900/60 rounded-xl p-3 border border-gray-200 dark:border-gray-700">
      <audio ref={audioRef} src={src} preload="metadata" />
      <div className="flex items-center gap-3 text-xs font-mono text-gray-500 dark:text-gray-400">
        <span className="w-10 text-right">{formatTime(progress)}</span>
        <input
          type="range"
          min="0"
          max={duration || 0}
          step="0.1"
          value={progress}
          onMouseDown={handleSeekStart}
          onTouchStart={handleSeekStart}
          onChange={handleProgressChange}
          onMouseUp={handleSeekEnd}
          onTouchEnd={handleSeekEnd}
          className="flex-1 h-1.5 bg-gray-200 dark:bg-gray-700 rounded-lg appearance-none cursor-pointer accent-gray-900 dark:accent-gray-200 hover:accent-gray-700 focus:outline-none focus:ring-2 focus:ring-gray-500/20"
        />
        <span className="w-10">{formatTime(duration)}</span>
      </div>
      <div className="flex items-center justify-between px-1">
        <div className="flex items-center gap-4">
          <button
            onClick={togglePlay}
            className="p-2.5 rounded-full bg-gray-900 hover:bg-black text-white shadow-md hover:shadow-lg transition-all active:scale-95 flex items-center justify-center"
            title={isPlaying ? "暂停" : "播放"}
          >
            {isPlaying ? <Pause size={18} fill="currentColor" /> : <Play size={18} fill="currentColor" className="ml-0.5" />}
          </button>
          <button
            onClick={() => { if (audioRef.current) { audioRef.current.currentTime = Math.max(0, audioRef.current.currentTime - 10); } }}
            className="text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100 transition-colors p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full"
            title="后退 10 秒"
          >
            <RotateCcw size={18} />
          </button>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 group relative">
            <button onClick={toggleMute} className="text-gray-400 hover:text-gray-800 dark:text-gray-500 dark:hover:text-gray-200 transition-colors">
              {isMuted || volume === 0 ? <VolumeX size={18} /> : (volume < 0.5 ? <Volume1 size={18} /> : <Volume2 size={18} />)}
            </button>
            <div className="w-16 md:w-20 flex items-center">
              <input type="range" min="0" max="1" step="0.05" value={isMuted ? 0 : volume} onChange={handleVolumeChange} className="w-full h-1 bg-gray-200 dark:bg-gray-700 rounded-lg appearance-none cursor-pointer accent-gray-400 hover:accent-gray-700" />
            </div>
          </div>
          <div className="w-px h-4 bg-gray-300 dark:bg-gray-700 mx-1"></div>
          <button onClick={toggleSpeed} className="flex items-center gap-1 px-2.5 py-1.5 rounded-md text-xs font-bold text-gray-700 dark:text-gray-200 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors w-[52px] justify-center">
            {speed}x
          </button>
        </div>
      </div>
    </div>
  );
};

const MeetingTranscribingPlaceholder = () => {
  const bars = [12, 20, 16, 28, 18, 22, 13];

  return (
    <div className="h-full min-h-[260px] flex items-center justify-center px-6">
      <style>{`
        @keyframes meetingScanLine {
          0% { transform: translateY(-2px); opacity: 0; }
          10% { opacity: 0.92; }
          50% { opacity: 1; }
          90% { opacity: 0.92; }
          100% { transform: translateY(116px); opacity: 0; }
        }
        @keyframes meetingPanelPulse {
          0%, 100% { transform: scale(1); opacity: 0.9; }
          50% { transform: scale(1.015); opacity: 1; }
        }
        @keyframes meetingWaveRise {
          0%, 100% { transform: scaleY(0.42); opacity: 0.38; }
          50% { transform: scaleY(1); opacity: 0.92; }
        }
        @media (prefers-reduced-motion: reduce) {
          .meeting-wave-bar,
          .meeting-scan-line,
          .meeting-panel-core {
            animation: none !important;
            transform: none !important;
          }
        }
      `}</style>
      <div className="flex flex-col items-center gap-4">
        <div className="relative h-44 w-44">
          <span className="absolute -top-1 -left-1 h-5 w-5 border-t-2 border-l-2 border-slate-900 dark:border-slate-200" />
          <span className="absolute -top-1 -right-1 h-5 w-5 border-t-2 border-r-2 border-slate-900 dark:border-slate-200" />
          <span className="absolute -bottom-1 -left-1 h-5 w-5 border-b-2 border-l-2 border-slate-900 dark:border-slate-200" />
          <span className="absolute -bottom-1 -right-1 h-5 w-5 border-b-2 border-r-2 border-slate-900 dark:border-slate-200" />

          <div
            className="meeting-panel-core absolute inset-6 overflow-hidden rounded-2xl border border-sky-200 dark:border-sky-800/70 bg-gradient-to-br from-sky-50 via-indigo-100 to-sky-200 dark:from-sky-950/40 dark:via-indigo-950/30 dark:to-sky-900/40 shadow-md"
            style={{ animation: 'meetingPanelPulse 2.2s ease-in-out infinite' }}
          >
            <div className="absolute left-4 right-4 top-4 flex items-center gap-2.5">
              <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-white/88 text-slate-700 shadow-sm dark:bg-slate-900/85 dark:text-slate-200">
                <Mic size={14} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="h-2 w-16 rounded-full bg-white/90 dark:bg-slate-200/90" />
                <div className="mt-1.5 h-1.5 w-24 rounded-full bg-white/70 dark:bg-slate-300/60" />
              </div>
            </div>

            <div className="absolute left-4 right-4 top-[62px] flex h-10 items-end gap-1.5">
              {bars.map((height, index) => (
                <span
                  key={`meeting-wave-${index}`}
                  className="meeting-wave-bar rounded-full bg-white/90 dark:bg-slate-200/90"
                  style={{
                    width: '6px',
                    height: `${height}px`,
                    transformOrigin: 'center bottom',
                    animation: `meetingWaveRise 1.35s ease-in-out ${index * 0.09}s infinite`,
                  }}
                />
              ))}
            </div>

            <div className="absolute left-4 right-5 bottom-9 h-2 rounded-full bg-white/85 dark:bg-slate-200/85" />
            <div className="absolute left-4 right-10 bottom-5 h-2 rounded-full bg-white/72 dark:bg-slate-300/70" />
          </div>

          <div className="absolute left-6 right-6 top-6 bottom-6 overflow-hidden rounded-2xl">
            <div
              className="meeting-scan-line absolute left-0 right-0 h-2 bg-gradient-to-r from-sky-300/0 via-sky-500/85 to-sky-300/0 blur-[1px]"
              style={{ animation: 'meetingScanLine 1.9s ease-in-out infinite' }}
            />
          </div>
        </div>

        <div className="text-center">
          <div className="text-sm font-medium text-slate-700 dark:text-slate-200">正在解析语音...</div>
          <div className="mt-1 text-xs leading-6 text-slate-500 dark:text-slate-400">
            转写完成后会自动填入逐字稿区域。
          </div>
        </div>
      </div>
    </div>
  );
};

const escapeRegExp = (value = "") => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const HighlightedText = ({ text, highlight }) => {
  if (!text) return null;
  if (!highlight) return <span>{text}</span>;
  const safeHighlight = String(highlight);
  const regex = new RegExp(`(${escapeRegExp(safeHighlight)})`, "gi");
  const parts = String(text).split(regex);
  return (
    <span>
      {parts.map((part, idx) => {
        if (part.toLowerCase() === safeHighlight.toLowerCase()) {
          return (
            <mark key={idx} className="bg-amber-100 text-amber-700 px-0.5 rounded">
              {part}
            </mark>
          );
        }
        return <span key={idx}>{part}</span>;
      })}
    </span>
  );
};
const AuditPanel = ({
  panelStyle,
  panelContent,
  docTypes,
  docType,
  onDocTypeChange,
  auditModelBackend = "local",
  onAuditModelBackendChange,
  onFileSelect,
  auditState,
  auditFile,
  onReset,
  onErpAction,
  isErpActionLoading = false,
  notice,
  fullWidth = false,
}) => {
  const fileInputRef = useRef(null);
  const auditStateKey = String(auditState?.jobId || "idle");
  const [auditUiState, setAuditUiState] = useState(() => ({
    stateKey: "idle",
    expandedFindings: {},
    isConfigExpanded: false,
  }));
  const expandedFindings = auditUiState.stateKey === auditStateKey ? auditUiState.expandedFindings : {};
  const isConfigExpanded = auditUiState.stateKey === auditStateKey ? auditUiState.isConfigExpanded : false;

  const toggleConfigExpanded = () => {
    setAuditUiState((prev) => {
      const prevExpandedFindings = prev.stateKey === auditStateKey ? prev.expandedFindings : {};
      const prevExpanded = prev.stateKey === auditStateKey ? prev.isConfigExpanded : false;
      return {
        stateKey: auditStateKey,
        expandedFindings: prevExpandedFindings,
        isConfigExpanded: !prevExpanded,
      };
    });
  };

  const toggleFindingExpanded = (key) => {
    setAuditUiState((prev) => {
      const prevExpandedFindings = prev.stateKey === auditStateKey ? prev.expandedFindings : {};
      return {
        stateKey: auditStateKey,
        expandedFindings: { ...prevExpandedFindings, [key]: !prevExpandedFindings[key] },
        isConfigExpanded: prev.stateKey === auditStateKey ? prev.isConfigExpanded : false,
      };
    });
  };

  const status = auditState?.status || "idle";
  const isBusy = ["uploading", "pending", "running"].includes(status);
  const isDone = status === "done";
  const isFailed = status === "failed";
  const historyText = typeof panelContent === "string" ? panelContent.trim() : "";
  const showHistory = !isBusy && !isDone && !isFailed && !!historyText;
  const rawProgress = Number(auditState?.progress);
  const progress = Number.isFinite(rawProgress) ? Math.min(rawProgress, 100) : 0;

  const steps = [
    { key: "ocr", label: "OCR 识别" },
    { key: "extract", label: "字段提取" },
    { key: "rules", label: "规则校验" },
    { key: "ai", label: "AI 风险审单" },
    { key: "report", label: "报告生成" },
  ];
  const thresholds = [30, 55, 70, 85, 100];
  const doneCount = thresholds.filter((t) => progress >= t).length;
  const currentIndex = isBusy ? Math.min(doneCount, steps.length - 1) : -1;

  const result = auditState?.result || {};
  const findings = Array.isArray(result.findings) ? result.findings : [];
  const severityRank = { high: 3, medium: 2, low: 1 };
  const sortedFindings = [...findings].sort((a, b) => {
    const aKey = String(a?.severity || "").toLowerCase();
    const bKey = String(b?.severity || "").toLowerCase();
    return (severityRank[bKey] || 0) - (severityRank[aKey] || 0);
  });

  const riskLevel = String(result.risk_level || "low").toLowerCase();
  const riskLabel = riskLevel === "high" ? "高风险" : (riskLevel === "medium" ? "中风险" : "低风险");
  const riskStyle = riskLevel === "high"
    ? "bg-red-50 text-red-600 border-red-100"
    : (riskLevel === "medium" ? "bg-amber-50 text-amber-600 border-amber-100" : "bg-emerald-50 text-emerald-600 border-emerald-100");
  const actionAdvice = riskLevel === "high"
    ? "建议驳回或人工复核"
    : (riskLevel === "medium" ? "建议人工复核/补充材料" : "建议通过");
  const isPass = typeof result.pass === "boolean" ? result.pass : riskLevel === "low";

  const extracted = result.extracted_fields || {};
  const detectedDocType = String(result.recognized_doc_type || extracted.doc_type || "").trim();
  const docTypeLabelMap = {
    auto: "自动识别",
    trade_case: "贸易单据包",
    invoice: "发票",
    contract: "合同",
    payment: "付款单",
    expense: "报销单",
    import_declaration: "进口报关单",
    export_declaration: "出口报关单",
    packing_list: "装箱单",
    bill_of_lading: "提单",
    air_waybill: "空运运单",
    certificate_of_origin: "原产地证",
  };
  const detectedDocTypeLabel = String(
    result.recognized_doc_type_label || docTypeLabelMap[detectedDocType] || detectedDocType || ""
  ).trim();
  const detectedDocSubtype = String(result.recognized_doc_subtype || extracted.doc_subtype || "").trim();
  const docSubtypeLabelMap = {
    sales_contract: "销售合同",
    purchase_contract: "采购合同",
    sale_purchase_contract: "购销合同",
    framework_contract: "框架合同",
    service_contract: "服务合同",
    labor_contract: "劳务合同",
    lease_contract: "租赁合同",
    nda_agreement: "保密协议",
    contract_generic: "普通合同",
    vat_special_invoice: "增值税专用发票",
    vat_general_invoice: "增值税普通发票",
    proforma_invoice: "形式发票",
    sales_invoice: "销项发票",
    purchase_invoice: "进项发票",
    invoice_generic: "普通发票",
    import_customs_declaration: "进口报关单",
    export_customs_declaration: "出口报关单",
    import_packing_list: "进口装箱单",
    export_packing_list: "出口装箱单",
    packing_list_generic: "装箱单",
    master_bill_of_lading: "主提单",
    house_bill_of_lading: "分提单",
    ocean_bill_of_lading: "海运提单",
    bill_of_lading_generic: "提单",
    master_air_waybill: "主空运单",
    house_air_waybill: "分空运单",
    air_waybill_generic: "空运运单",
    coo_form_e: "原产地证（Form E）",
    coo_form_a: "原产地证（Form A）",
    certificate_of_origin_generic: "原产地证",
    advance_payment: "预付款",
    final_payment: "尾款",
    payment_generic: "付款单",
    travel_expense: "差旅报销",
    marketing_expense: "营销报销",
    expense_generic: "报销单",
  };
  const detectedDocSubtypeLabel = String(
    result.recognized_doc_subtype_label || docSubtypeLabelMap[detectedDocSubtype] || detectedDocSubtype || ""
  ).trim();
  const fieldPreview = [
    { key: "total_amount", label: "金额" },
    { key: "invoice_no", label: "发票号" },
    { key: "contract_no", label: "合同号" },
    { key: "vendor", label: "供应商" },
  ].filter((item) => extracted[item.key]);
  const erpChecks = Array.isArray(result.erp_checks) ? result.erp_checks : [];
  const failedErpChecks = erpChecks.filter((item) => item && item.passed === false);
  const auditScore = Number.isFinite(Number(result.audit_score)) ? Number(result.audit_score) : null;
  const erpTraceId = result.erp_trace_id || result?.erp_action?.trace_id || "";
  const erpSyncStatus = String(result.erp_sync_status || result?.erp_action?.status || "").toLowerCase();
  const sourceLabelMap = {
    rule: "规则命中",
    ai: "AI语义",
    cross_doc: "跨单据",
    anomaly: "异常检测",
  };
  const sourceStyleMap = {
    rule: "bg-blue-50 text-blue-600 border-blue-100",
    ai: "bg-indigo-50 text-indigo-600 border-indigo-100",
    cross_doc: "bg-cyan-50 text-cyan-700 border-cyan-100",
    anomaly: "bg-fuchsia-50 text-fuchsia-600 border-fuchsia-100",
  };
  const formatConfidence = (val) => {
    const num = Number(val);
    if (!Number.isFinite(num)) return "";
    return `${Math.round(Math.max(0, Math.min(1, num)) * 100)}%`;
  };

  const statusLabel = status === "uploading" ? "文件上传中" : (status === "pending" ? "排队中" : "审单进行中");

  const widthClass = fullWidth ? "md:w-full md:border-r-0" : "md:w-1/2 md:border-r";
  const auditModelOptions = [
    { value: "local", label: "本地" },
    { value: "cloud", label: "云端" },
  ];
  const selectedDocTypeLabel = (docTypes || []).find((item) => item.value === docType)?.label || "自动识别";
  const selectedModelLabel = auditModelOptions.find((item) => item.value === auditModelBackend)?.label || "本地";
  const caseSummary = (result && typeof result.case_summary === "object") ? result.case_summary : {};
  const caseDocuments = Array.isArray(caseSummary.documents)
    ? caseSummary.documents
    : (Array.isArray(auditState?.caseDocuments) ? auditState.caseDocuments : []);
  const caseCompleteness = caseSummary && typeof caseSummary.completeness === "object" ? caseSummary.completeness : null;
  const workflowState = String(result.workflow_state || auditState?.workflow_state || status || "idle").toLowerCase();
  const workflowLabels = {
    pending_docs: "待补件",
    extracting: "提取中",
    rule_checking: "规则校验中",
    ai_review: "AI审查中",
    aggregating: "汇总中",
    review_required: "需人工复核",
    review_optional: "建议抽检",
    ready_for_erp: "可回写ERP",
    failed: "失败",
    done: "完成",
  };
  const workflowLabel = workflowLabels[workflowState] || workflowState || "处理中";
  const missingTags = Array.isArray(caseCompleteness?.missing) ? caseCompleteness.missing : [];
  const caseBadgeStyle = missingTags.length
    ? "bg-amber-50 text-amber-700 border-amber-200"
    : "bg-emerald-50 text-emerald-700 border-emerald-200";

  return (
    <div className={`w-full ${widthClass} flex flex-col flex-shrink-0 border-b md:border-b-0 border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 transition-all duration-300 ${panelStyle.border} shadow-sm z-20`}>
      <div className="px-4 py-3 border-b border-slate-200 dark:border-slate-700 bg-gradient-to-r from-slate-50 via-white to-cyan-50 dark:from-slate-900 dark:via-slate-900 dark:to-slate-800 flex justify-between items-center">
        <div className="flex items-center gap-2 font-medium text-slate-900 dark:text-slate-50">
          <div className="w-8 h-8 rounded-xl bg-slate-900 text-white dark:bg-white dark:text-slate-900 flex items-center justify-center shadow-sm">
            <ClipboardCheck size={16} />
          </div>
          <div>
            <div className="truncate text-sm font-semibold">智能审单中台</div>
            <div className="text-[11px] text-slate-500 dark:text-slate-300">规则校验 + AI评估 + ERP动作</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[11px] px-2 py-1 rounded-full border border-slate-300 dark:border-slate-600 bg-white/80 dark:bg-slate-900/80 text-slate-700 dark:text-slate-100">
            {workflowLabel}
          </span>
          {isBusy && (
            <span className="text-xs flex items-center gap-1 text-slate-600 dark:text-slate-200">
              <Loader2 size={12} className="animate-spin" /> {statusLabel}
            </span>
          )}
        </div>
      </div>

      <div className="flex-1 p-4 overflow-y-auto space-y-4 custom-scrollbar">
        {notice && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 text-amber-700 text-xs px-3 py-2">
            {notice}
          </div>
        )}

        {(auditState?.caseId || caseDocuments.length > 0) && (
          <div className="rounded-2xl border border-slate-200 dark:border-slate-700 bg-gradient-to-br from-white via-slate-50 to-white dark:from-slate-900 dark:via-slate-900 dark:to-slate-800 p-4 shadow-sm">
            <div className="flex items-center justify-between gap-2">
              <div className="text-xs font-medium text-slate-500 dark:text-slate-300">审单包 Case</div>
              <span className={`text-[11px] px-2 py-1 rounded-full border ${caseBadgeStyle}`}>
                {missingTags.length ? `缺少 ${missingTags.length} 项` : "单据齐套"}
              </span>
            </div>
            <div className="mt-1 text-[11px] text-slate-500 dark:text-slate-400 break-all">
              {auditState?.caseId || caseSummary?.case_id}
            </div>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {caseDocuments.slice(0, 10).map((doc, idx) => (
                <span
                  key={`${doc?.doc_id || doc?.job_id || idx}`}
                  className="px-2 py-1 rounded-full text-[11px] border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-200"
                  title={doc?.file_name || ""}
                >
                  {(doc?.tag || doc?.doc_type || "doc").replace(/_/g, " ")}
                </span>
              ))}
              {caseDocuments.length === 0 && (
                <span className="text-[11px] text-slate-400">尚未添加单据</span>
              )}
            </div>
            {missingTags.length > 0 && (
              <div className="mt-2 text-[11px] text-amber-700 dark:text-amber-300">
                缺失：{missingTags.join(" / ")}
              </div>
            )}
          </div>
        )}

        {showHistory && (
          <div className="rounded-xl border border-gray-200 dark:border-gray-800 p-4 bg-gray-50/70 dark:bg-gray-900/60">
            <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">历史审单摘要</div>
            <div className="text-sm text-gray-700 dark:text-gray-200 whitespace-pre-wrap leading-relaxed">
              {historyText}
            </div>
          </div>
        )}

        <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 overflow-hidden">
          <button
            type="button"
            onClick={toggleConfigExpanded}
            className="w-full px-4 py-3 flex items-center justify-between gap-3 text-left"
          >
            <div>
              <div className="text-sm font-semibold text-gray-900 dark:text-gray-100">审单设置</div>
              <div className="text-[11px] text-gray-500 dark:text-gray-400">
                单据类型：{selectedDocTypeLabel} · 模型：{selectedModelLabel}
              </div>
            </div>
            <ChevronDown size={16} className={`text-gray-400 transition-transform ${isConfigExpanded ? "rotate-180" : ""}`} />
          </button>
          {isConfigExpanded && (
            <div className="px-4 pb-4 pt-2 border-t border-gray-100 dark:border-gray-800 space-y-3">
              <div>
                <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">单据类型（可选）</div>
                <div className="flex flex-wrap gap-2">
                  {(docTypes || []).map((item) => {
                    const active = item.value === docType;
                    return (
                      <button
                        key={item.value}
                        type="button"
                        onClick={() => !isBusy && onDocTypeChange(item.value)}
                        disabled={isBusy}
                        className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                          active
                            ? "bg-teal-600 text-white border-teal-600"
                            : "bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border-gray-200 dark:border-gray-700 hover:border-teal-400"
                        } ${isBusy ? "opacity-50 cursor-not-allowed" : ""}`}
                      >
                        {item.label}
                      </button>
                    );
                  })}
                </div>
              </div>
              <div>
                <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">审单模型</div>
                <div className="flex flex-wrap gap-2">
                  {auditModelOptions.map((item) => {
                    const active = item.value === auditModelBackend;
                    return (
                      <button
                        key={item.value}
                        type="button"
                        onClick={() => !isBusy && onAuditModelBackendChange && onAuditModelBackendChange(item.value)}
                        disabled={isBusy}
                        className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                          active
                            ? "bg-gray-900 text-white border-gray-900"
                            : "bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border-gray-200 dark:border-gray-700 hover:border-gray-400"
                        } ${isBusy ? "opacity-50 cursor-not-allowed" : ""}`}
                      >
                        {item.label}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="rounded-2xl border border-dashed border-slate-300 dark:border-slate-600 p-4 bg-gradient-to-r from-slate-50 to-white dark:from-slate-900/70 dark:to-slate-800/60">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-slate-900 text-white dark:bg-white dark:text-slate-900 flex items-center justify-center shadow-sm">
              <FileUp size={18} />
            </div>
            <div className="flex-1">
              <div className="text-sm font-semibold text-gray-800 dark:text-gray-200">
                {caseDocuments.length > 0 ? "追加审单单据" : "上传首个审单文件"}
              </div>
              <div className="text-xs text-gray-500 dark:text-gray-400">支持图片 / PDF / Word，按 Case 累积上下文</div>
            </div>
          </div>
          <div className="mt-3 flex items-center gap-2">
            <button
              type="button"
              onClick={() => fileInputRef.current && fileInputRef.current.click()}
              disabled={isBusy}
              className="px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-black text-white text-xs font-semibold disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
            >
              {caseDocuments.length > 0 ? "继续添加" : "选择文件"}
            </button>
            <span className="text-[11px] text-gray-400">上传后自动进入下一轮审单</span>
          </div>
          {auditFile && (
            <div className="mt-2 px-3 py-2 rounded-lg border border-slate-200 dark:border-slate-700 text-xs text-gray-600 dark:text-gray-300 bg-white/90 dark:bg-slate-800 flex items-center justify-between gap-3">
              <span className="truncate">{auditFile.name}</span>
              <span className="text-gray-400">{auditFile.sizeLabel}</span>
            </div>
          )}
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            accept="image/*,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            onChange={onFileSelect}
            disabled={isBusy}
          />
        </div>

        {(isBusy || status === "pending") && (
          <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 space-y-3">
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium text-gray-800 dark:text-gray-200">审单进行中</span>
              <span className="text-gray-500 dark:text-gray-400">{progress}%</span>
            </div>
            <div className="w-full h-2 rounded-full bg-gray-100 dark:bg-gray-800 overflow-hidden">
              <div
                className="h-full bg-teal-500 transition-all"
                style={{ width: `${progress}%` }}
              />
            </div>
            <div className="space-y-2">
              {steps.map((step, idx) => {
                const isDone = idx < doneCount;
                const isCurrent = idx === currentIndex;
                return (
                  <div key={step.key} className="flex items-center gap-2 text-xs">
                    <div
                      className={`w-2.5 h-2.5 rounded-full border ${
                        isDone
                          ? "bg-teal-500 border-teal-500"
                          : isCurrent
                            ? "border-teal-500"
                            : "border-gray-300 dark:border-gray-600"
                      }`}
                    />
                    <span className={`${isDone ? "text-gray-800 dark:text-gray-200" : "text-gray-500 dark:text-gray-400"} ${isCurrent ? "font-medium" : ""}`}>
                      {step.label}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {isFailed && (
          <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 text-sm p-4 space-y-2">
            <div className="flex items-center gap-2 font-medium"><AlertTriangle size={16} /> 审单失败</div>
            <div className="text-xs">{auditState?.error_message || auditState?.error || "处理过程中出现异常，请重试。"}</div>
          </div>
        )}

        {isDone && (
          <div className="space-y-4">
            <div className="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">结论</div>
                  <div className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                    {isPass ? <CheckCircle2 size={18} className="text-emerald-500" /> : <AlertTriangle size={18} className="text-amber-500" />}
                    {isPass ? "通过" : "需复核"}
                  </div>
                </div>
                <div className={`px-2.5 py-1 rounded-full text-xs font-medium border ${riskStyle}`}>
                  {riskLabel}
                </div>
              </div>
              {auditScore !== null && (
                <div className="text-xs text-gray-500 dark:text-gray-400">
                  审单评分：<span className="font-semibold text-gray-800 dark:text-gray-200">{auditScore}</span>
                </div>
              )}
              {detectedDocType && (
                <div className="text-xs text-gray-500 dark:text-gray-400">
                  识别类型：
                  <span className="font-semibold text-gray-800 dark:text-gray-200">
                    {detectedDocTypeLabel}
                    {detectedDocTypeLabel !== detectedDocType ? `（${detectedDocType}）` : ""}
                  </span>
                </div>
              )}
              {detectedDocSubtype && (
                <div className="text-xs text-gray-500 dark:text-gray-400">
                  细分类型：
                  <span className="font-semibold text-gray-800 dark:text-gray-200">
                    {detectedDocSubtypeLabel}
                    {detectedDocSubtypeLabel !== detectedDocSubtype ? `（${detectedDocSubtype}）` : ""}
                  </span>
                </div>
              )}
              {result.summary && <div className="text-sm text-gray-600 dark:text-gray-300">{result.summary}</div>}
              {result.next_action && (
                <div className="text-xs text-slate-500 dark:text-slate-300">
                  下一步：<span className="font-medium text-slate-700 dark:text-slate-100">{result.next_action}</span>
                </div>
              )}
              <div className="text-xs text-gray-500 dark:text-gray-400">
                建议动作：<span className="text-gray-700 dark:text-gray-200 font-medium">{actionAdvice}</span>
              </div>
              <div className="pt-1 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => onErpAction && onErpAction('approved')}
                  disabled={isErpActionLoading}
                  className="px-3 py-1.5 rounded-full text-xs font-medium bg-emerald-600 text-white disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isErpActionLoading ? "回写中..." : "ERP回写：通过"}
                </button>
                <button
                  type="button"
                  onClick={() => onErpAction && onErpAction('rejected')}
                  disabled={isErpActionLoading}
                  className="px-3 py-1.5 rounded-full text-xs font-medium bg-rose-600 text-white disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  ERP回写：驳回
                </button>
                <button
                  type="button"
                  onClick={() => onErpAction && onErpAction('need_more')}
                  disabled={isErpActionLoading}
                  className="px-3 py-1.5 rounded-full text-xs font-medium bg-amber-600 text-white disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  ERP回写：补件
                </button>
                {erpTraceId && (
                  <span className="text-[11px] text-gray-500 dark:text-gray-400 px-2 py-1 rounded-full border border-gray-200 dark:border-gray-700">
                    Trace: {erpTraceId}
                  </span>
                )}
                {erpSyncStatus && (
                  <span className="text-[11px] text-gray-500 dark:text-gray-400">
                    状态：{erpSyncStatus}
                  </span>
                )}
              </div>
            </div>

            {fieldPreview.length > 0 && (
              <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4">
                <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">字段摘要</div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs text-gray-700 dark:text-gray-200">
                  {fieldPreview.map((item) => (
                    <div key={item.key} className="flex items-center gap-2 bg-gray-50 dark:bg-gray-800 rounded-lg px-2.5 py-2 border border-gray-100 dark:border-gray-700">
                      <span className="text-gray-500">{item.label}</span>
                      <span className="truncate">{String(extracted[item.key])}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {erpChecks.length > 0 && (
              <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="text-xs font-medium text-gray-500 dark:text-gray-400">ERP 对账检查</div>
                  <div className="text-[11px] text-gray-400">失败 {failedErpChecks.length} / {erpChecks.length}</div>
                </div>
                <div className="space-y-2">
                  {erpChecks.slice(0, 6).map((check) => (
                    <div key={check.id} className="text-xs rounded-lg border border-gray-100 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/60 px-3 py-2">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-gray-700 dark:text-gray-200 font-medium">{check.name || check.id}</span>
                        <span className={`px-2 py-0.5 rounded-full border ${check.passed ? "bg-emerald-50 text-emerald-600 border-emerald-100" : "bg-red-50 text-red-600 border-red-100"}`}>
                          {check.passed ? "通过" : "失败"}
                        </span>
                      </div>
                      {check.reason && <div className="text-gray-500 dark:text-gray-400 mt-1">{check.reason}</div>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
              <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-800 text-sm font-medium text-gray-800 dark:text-gray-200">
                问题清单
              </div>
              <div className="p-4 space-y-3">
                {sortedFindings.length === 0 && (
                  <div className="text-sm text-gray-500 dark:text-gray-400">未发现需要提示的问题。</div>
                )}
                {sortedFindings.map((finding, idx) => {
                  const key = `${finding.rule_id || finding.type || 'finding'}-${idx}`;
                  const severity = String(finding.severity || "").toLowerCase();
                  const source = String(finding.source || "rule").toLowerCase();
                  const sourceLabel = sourceLabelMap[source] || "风险项";
                  const severityStyle = severity === "high"
                    ? "bg-red-50 text-red-600 border-red-100"
                    : (severity === "medium" ? "bg-amber-50 text-amber-600 border-amber-100" : "bg-emerald-50 text-emerald-600 border-emerald-100");
                  const sourceStyle = sourceStyleMap[source] || "bg-gray-50 text-gray-600 border-gray-100";
                  const expanded = !!expandedFindings[key];
                  const evidence = finding.evidence || {};
                  const evidenceText = typeof evidence === "string" ? evidence : evidence.text;
                  const evidenceHighlight = typeof evidence === "string" ? "" : evidence.highlight;
                  const confidenceText = formatConfidence(finding.confidence);
                  const reasonText = finding.reason || "";

                  return (
                    <div key={key} className="rounded-lg border border-gray-100 dark:border-gray-800 bg-gray-50/60 dark:bg-gray-900/30">
                      <button
                        type="button"
                        onClick={() => toggleFindingExpanded(key)}
                        className="w-full text-left px-3 py-3 flex items-start justify-between gap-3"
                      >
                        <div className="flex-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className={`px-2 py-0.5 rounded-full text-[10px] border ${severityStyle}`}>
                              {severity === "high" ? "高风险" : (severity === "medium" ? "中风险" : "低风险")}
                            </span>
                            <span className={`px-2 py-0.5 rounded-full text-[10px] border ${sourceStyle}`}>{sourceLabel}</span>
                            {confidenceText && <span className="text-[10px] text-gray-400">置信度: {confidenceText}</span>}
                            <span className="text-sm font-medium text-gray-800 dark:text-gray-100">
                              {finding.message || "规则命中"}
                            </span>
                          </div>
                          {reasonText && (
                            <div className="text-xs text-gray-600 dark:text-gray-300 mt-1">
                              触发原因：{reasonText}
                            </div>
                          )}
                          {finding.suggestion && (
                            <div className="text-xs text-gray-600 dark:text-gray-300 mt-1">
                              建议动作：{finding.suggestion}
                            </div>
                          )}
                          {finding.rule_id && (
                            <div className="text-[11px] text-gray-400 mt-1">规则ID: {finding.rule_id}</div>
                          )}
                        </div>
                        <ChevronDown size={16} className={`text-gray-400 transition-transform ${expanded ? "rotate-180" : ""}`} />
                      </button>
                      {expanded && (
                        <div className="px-3 pb-3">
                          <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-3 text-xs text-gray-600 dark:text-gray-300 space-y-2">
                            <div className="text-[11px] uppercase tracking-wide text-gray-400">证据原文</div>
                            {evidenceText ? (
                              <div className="leading-relaxed">
                                <HighlightedText text={evidenceText} highlight={evidenceHighlight} />
                              </div>
                            ) : (
                              <div className="text-gray-400">暂无证据片段</div>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}
      </div>

      {(isDone || isFailed) && (
        <div className="px-4 py-3 border-t border-gray-100 dark:border-gray-800 bg-gray-50/80 dark:bg-gray-800/60 flex justify-end">
          <button
            type="button"
            onClick={onReset}
            disabled={isErpActionLoading}
            className="px-4 py-2 rounded-lg text-sm font-medium bg-black text-white disabled:opacity-50 disabled:cursor-not-allowed"
          >
            重新审单
          </button>
        </div>
      )}
    </div>
  );
};

const ModePanelComponent = ({
  panelStyle = DEFAULT_PANEL_STYLE,
  isMeetingMode,
  isOCRMode,
  isAuditMode,
  panelContent,
  setPanelContent,
  isUploadingFile,
  audioFileUrl,
  isProcessing,
  isOcrSaving,
  isSavingContext,
  handleManualSave,
  handleExportWord,
  handleGenerateSummary,
  onOcrStore,
  auditState,
  auditDocType,
  auditDocTypes,
  auditModelBackend,
  auditFile,
  auditNotice,
  onAuditDocTypeChange,
  onAuditModelBackendChange,
  onAuditFileSelect,
  onAuditReset,
  onAuditErpAction,
  isAuditErpActionLoading = false,
  ocrEngine,
  onOcrEngineChange,
  onMeetingUploadClick,
  fullWidth = false,
}) => {
  const [ocrViewMode, setOcrViewMode] = useState("edit");
  const [meetingViewTab, setMeetingViewTab] = useState("transcript");
  const [isMeetingEditing, setIsMeetingEditing] = useState(false);
  const [meetingSearchKeyword, setMeetingSearchKeyword] = useState("");
  const effectiveMeetingViewTab = isMeetingMode ? meetingViewTab : "transcript";
  const effectiveIsMeetingEditing = isMeetingMode ? isMeetingEditing : false;
  const effectiveMeetingSearchKeyword = isMeetingMode ? meetingSearchKeyword : "";

  if (isAuditMode) {
    return (
      <Suspense fallback={<div className="w-full h-full flex items-center justify-center text-sm text-gray-500 dark:text-gray-400"><Loader2 size={16} className="animate-spin mr-2" /> 加载审单工作区...</div>}>
        <AuditWorkspace
          key={auditState?.jobId || "audit-workspace"}
          panelStyle={panelStyle}
          panelContent={panelContent}
          docTypes={auditDocTypes}
          docType={auditDocType}
          onDocTypeChange={onAuditDocTypeChange}
          auditModelBackend={auditModelBackend}
          onAuditModelBackendChange={onAuditModelBackendChange}
          onFileSelect={onAuditFileSelect}
          auditState={auditState}
          auditFile={auditFile}
          onReset={onAuditReset}
          onErpAction={onAuditErpAction}
          isErpActionLoading={isAuditErpActionLoading}
          notice={auditNotice}
          fullWidth={fullWidth}
        />
      </Suspense>
    );
  }
  const showEnhancedPanel = isMeetingMode || isOCRMode;
  const panelTitle = isMeetingMode ? "会议纪要 · 智能整理" : (isOCRMode ? "OCR 智能录入" : "内容面板");
  const statusLabel = isMeetingMode ? "转写中..." : "识别中...";
  const contentLabel = isMeetingMode ? "转写内容" : "识别文本";
  const emptyTitle = isMeetingMode ? "等待转写内容" : "等待识别结果";
  const emptySubtitle = isMeetingMode
    ? "上传音频后会自动同步文字，也可粘贴文本快速开始。"
    : "上传图片/PDF 后自动识别，可直接修订。";
  const contentPlaceholder = isMeetingMode
    ? "转写内容将显示在这里，可直接编辑补充重点。"
    : (isOCRMode
      ? "识别结果将显示在这里，可直接修订纠错。"
      : "请上传图片或PDF，OCR 识别文字将显示在这里...");
  const ocrGuideTitle = "OCR 识别与录入";
  const ocrGuideDesc = "上传图片或 PDF，自动识别文本，可直接修订并智能录入。";
  const ocrStepItems = ["上传文件", "文本识别", "智能录入"];
  const charCount = (panelContent || "").replace(/\s/g, "").length;
  const widthClass = fullWidth ? "md:w-full md:border-r-0" : "md:w-1/2 md:border-r";
  const isOcrPreview = isOCRMode && ocrViewMode === "preview";
  const hasPanelContent = Boolean((panelContent || "").trim());
  const showMeetingTranscribingState = isMeetingMode && isUploadingFile && !hasPanelContent;
  const meetingStatusText = isUploadingFile
    ? "正在解析语音，请稍候..."
    : (hasPanelContent ? "转写已就绪，可直接生成纪要" : "请先上传录音文件");
  const transcriptLines = (panelContent || "")
    .split(/\r?\n+/)
    .map((line) => line.trim())
    .filter(Boolean);
  const normalizedMeetingSearch = effectiveMeetingSearchKeyword.trim().toLowerCase();
  const filteredTranscriptLines = normalizedMeetingSearch
    ? transcriptLines.filter((line) => line.toLowerCase().includes(normalizedMeetingSearch))
    : transcriptLines;
  const transcriptLineCount = transcriptLines.length;
  const secondaryActionClass = isMeetingMode
    ? "flex items-center gap-2 bg-white dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-100 border border-gray-200 dark:border-gray-700 px-3.5 py-2 rounded-full text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
    : "flex items-center gap-2 bg-white dark:bg-gray-700 hover:bg-gray-100 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-200 border border-gray-200 dark:border-gray-600 px-3 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm";
  const primaryActionClass = isMeetingMode
    ? "flex items-center gap-2 text-white px-5 py-2.5 rounded-full text-sm font-semibold transition-all disabled:opacity-50 disabled:cursor-not-allowed bg-gray-900 hover:bg-black shadow-[0_10px_24px_rgba(15,23,42,0.22)] hover:shadow-[0_14px_28px_rgba(15,23,42,0.3)]"
    : `flex items-center gap-2 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm hover:shadow ${panelStyle.btnBg}`;

  return (
    <div className={`w-full ${widthClass} flex flex-col flex-shrink-0 border-b md:border-b-0 border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 transition-all duration-300 ${panelStyle.border} shadow-sm z-20`}>
      {!isMeetingMode && (
        <div className={`px-4 py-3 border-b flex justify-between items-center gap-3 ${panelStyle.headerBg} ${panelStyle.border}`}>
          <div className={`flex items-center gap-2 font-medium ${panelStyle.headerText}`}>
            {isOCRMode && <ScanText size={18} />}
            {isAuditMode && <ClipboardCheck size={18} />}
            <span className="truncate">{panelTitle}</span>
          </div>
          <div className="flex items-center gap-2">
            {isOCRMode && (
              <div className="flex items-center gap-1 rounded-full border border-gray-200 dark:border-gray-700 bg-white/70 dark:bg-gray-900/50 p-0.5 text-[11px] text-gray-500">
                {[
                  { key: "standard", label: "标准" },
                  { key: "vl", label: "VL" },
                ].map((item) => (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => onOcrEngineChange && onOcrEngineChange(item.key)}
                    className={`px-2 py-0.5 rounded-full ${
                      (ocrEngine || "auto") === item.key ? "bg-gray-900 text-white" : "hover:text-gray-700 dark:hover:text-gray-200"
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            )}
            {isUploadingFile && (
              <span className={`text-xs flex items-center gap-1 ${panelStyle.headerText}`}>
                <Loader2 size={12} className="animate-spin" /> {statusLabel}
              </span>
            )}
          </div>
        </div>
      )}
      {showEnhancedPanel ? (
        isMeetingMode ? (
          <div className="flex-1 p-3 md:p-4 overflow-hidden bg-[radial-gradient(circle_at_top_right,rgba(15,23,42,0.06),transparent_45%)] dark:bg-[radial-gradient(circle_at_top_right,rgba(148,163,184,0.1),transparent_50%)]">
            <section className="h-full min-h-0 rounded-2xl border border-gray-200/90 dark:border-gray-800/90 bg-white/90 dark:bg-gray-900/80 flex flex-col overflow-hidden shadow-[0_10px_28px_rgba(15,23,42,0.06)] dark:shadow-[0_14px_30px_rgba(0,0,0,0.3)]">
              <div className="px-3.5 md:px-4 py-3 border-b border-gray-100 dark:border-gray-800 bg-white/90 dark:bg-gray-900/90">
                <div className="flex flex-col gap-2.5">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex items-center gap-2.5">
                      <div className="h-9 w-9 rounded-xl bg-black text-white dark:bg-white dark:text-black flex items-center justify-center">
                        <Mic size={16} />
                      </div>
                      <div>
                        <div className="text-sm font-semibold text-gray-900 dark:text-white">会议记录工作台</div>
                        <div className="text-[11px] text-gray-500 dark:text-gray-400">{meetingStatusText}</div>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => onMeetingUploadClick && onMeetingUploadClick()}
                      disabled={isUploadingFile || isProcessing}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
                    >
                      <FileUp size={14} />
                      上传音频文件
                    </button>
                  </div>

                  <div className="flex items-center gap-2">
                    <div className="relative flex-1">
                      <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                      <input
                        type="text"
                        value={effectiveMeetingSearchKeyword}
                        onChange={(e) => setMeetingSearchKeyword(e.target.value)}
                        placeholder="搜索逐字稿关键词"
                        className="w-full h-9 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 pl-9 pr-3 text-sm text-gray-700 dark:text-gray-200 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-200 dark:focus:ring-blue-800"
                      />
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        if (effectiveMeetingViewTab !== "transcript") {
                          setMeetingViewTab("transcript");
                          setIsMeetingEditing(true);
                          return;
                        }
                        setIsMeetingEditing((prev) => !prev);
                      }}
                      className="h-9 px-3 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-xs font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                    >
                      {effectiveIsMeetingEditing ? "完成编辑" : "手动编辑"}
                    </button>
                  </div>

                  <div className="flex items-center gap-1 rounded-xl bg-gray-100/90 dark:bg-gray-800/80 p-1 w-fit">
                    <button
                      type="button"
                      onClick={() => {
                        setMeetingViewTab("summary");
                        setIsMeetingEditing(false);
                      }}
                      className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                        effectiveMeetingViewTab === "summary"
                          ? "bg-white dark:bg-gray-900 text-gray-900 dark:text-white shadow-sm"
                          : "text-gray-500 dark:text-gray-400"
                      }`}
                    >
                      纪要视图
                    </button>
                    <button
                      type="button"
                      onClick={() => setMeetingViewTab("transcript")}
                      className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                        effectiveMeetingViewTab === "transcript"
                          ? "bg-white dark:bg-gray-900 text-gray-900 dark:text-white shadow-sm"
                          : "text-gray-500 dark:text-gray-400"
                      }`}
                    >
                      逐字稿
                    </button>
                  </div>
                </div>
              </div>

              <div className="flex-1 min-h-0 overflow-hidden">
                {effectiveMeetingViewTab === "summary" ? (
                  <div className="h-full overflow-y-auto custom-scrollbar p-4 space-y-3">
                    <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-gray-50/70 dark:bg-gray-900/60 p-3">
                      <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">纪要预览</div>
                      {hasPanelContent ? (
                        <div className="text-sm leading-7 text-gray-700 dark:text-gray-200">
                          <Suspense fallback={<div className="text-sm text-gray-400 dark:text-gray-500">加载预览...</div>}>
                            <MarkdownRenderer content={panelContent} />
                          </Suspense>
                        </div>
                      ) : showMeetingTranscribingState ? (
                        <MeetingTranscribingPlaceholder />
                      ) : (
                        <div className="text-sm text-gray-400 dark:text-gray-500">暂无内容，请先上传音频并完成转写。</div>
                      )}
                    </div>
                    <div className="rounded-xl border border-blue-100 dark:border-blue-900/60 bg-blue-50/70 dark:bg-blue-900/20 p-3 text-xs text-blue-700 dark:text-blue-300 leading-6">
                      建议操作：在右侧输入“请生成会议纪要（结论、行动项、负责人、截止时间）”，可快速得到结构化结果。
                    </div>
                  </div>
                ) : effectiveIsMeetingEditing ? (
                  <div className="h-full p-4">
                    <textarea
                      className="w-full h-full min-h-[260px] resize-none border border-gray-200 dark:border-gray-700 rounded-xl bg-white dark:bg-gray-900 px-4 py-3 text-sm leading-7 text-gray-700 dark:text-gray-300 custom-scrollbar focus:ring-2 focus:ring-blue-200 dark:focus:ring-blue-800"
                      value={panelContent}
                      onChange={(e) => setPanelContent(e.target.value)}
                      placeholder={contentPlaceholder}
                      disabled={isUploadingFile}
                    />
                  </div>
                ) : (
                  <div className="h-full overflow-y-auto custom-scrollbar p-4 space-y-2.5">
                    {filteredTranscriptLines.length > 0 ? (
                      filteredTranscriptLines.map((line, index) => (
                        <div
                          key={`${index}-${line.slice(0, 12)}`}
                          className="rounded-xl border border-gray-100 dark:border-gray-800 bg-white/80 dark:bg-gray-900/60 px-3 py-2.5"
                        >
                          <div className="flex items-start gap-2.5">
                            <div className="mt-0.5 h-7 w-7 rounded-full bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-300 flex items-center justify-center">
                              <User size={13} />
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="text-[11px] text-gray-400 dark:text-gray-500">片段 {String(index + 1).padStart(2, "0")}</div>
                              <div className="text-sm text-gray-700 dark:text-gray-200 leading-6 break-words">
                                <HighlightedText text={line} highlight={effectiveMeetingSearchKeyword} />
                              </div>
                            </div>
                          </div>
                        </div>
                      ))
                    ) : showMeetingTranscribingState ? (
                      <MeetingTranscribingPlaceholder />
                    ) : (
                      <div className="h-full min-h-[240px] flex items-center justify-center text-center px-6">
                        <div>
                          <div className="text-sm font-medium text-gray-500 dark:text-gray-400">
                            {hasPanelContent ? "没有匹配到关键词" : emptyTitle}
                          </div>
                          <div className="text-xs text-gray-400 mt-1">
                            {hasPanelContent ? "请更换关键词后重试。" : emptySubtitle}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              <div className="px-4 py-2.5 border-t border-gray-100 dark:border-gray-800 bg-gray-50/90 dark:bg-gray-900/70 flex items-center justify-between">
                <span className="text-[11px] text-gray-500 dark:text-gray-400">逐字稿片段：{transcriptLineCount} · 字数：{charCount}</span>
                <span className="text-[11px] text-gray-400 dark:text-gray-500">支持手动编辑与关键词检索</span>
              </div>

              {audioFileUrl && (
                <div className="border-t border-gray-100 dark:border-gray-800 bg-white/90 dark:bg-gray-900/85 p-3">
                  <div className="pb-2 text-xs text-gray-500 dark:text-gray-400">录音回放</div>
                  <AudioPlayer src={audioFileUrl} />
                </div>
              )}
            </section>
          </div>
        ) : (
          <div className="flex-1 p-4 md:p-5 flex flex-col gap-4 overflow-hidden">
            <div className={`rounded-2xl border ${panelStyle.border} bg-gradient-to-br from-white to-gray-50/80 dark:from-gray-900 dark:to-gray-800/60 p-4`}>
              <div className="flex items-start gap-3">
                <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${panelStyle.headerBg} ${panelStyle.headerText}`}>
                  <ScanText size={16} />
                </div>
                <div className="flex-1">
                  <div className="text-sm font-semibold text-gray-900 dark:text-white">{ocrGuideTitle}</div>
                  <div className="text-xs text-gray-500 dark:text-gray-400">{ocrGuideDesc}</div>
                </div>
                <div className="text-[11px] text-gray-400">图片/PDF</div>
              </div>
              <div className="mt-3 grid grid-cols-3 gap-2 text-[11px] text-gray-500 dark:text-gray-400">
                {ocrStepItems.map((item, idx) => (
                  <div key={item} className="rounded-full border border-gray-200 dark:border-gray-700 px-2.5 py-1 bg-white/70 dark:bg-gray-900/70 text-center">
                    <span className="font-medium text-gray-700 dark:text-gray-200">{idx + 1}</span> {item}
                  </div>
                ))}
              </div>
            </div>

            <div className={`flex-1 rounded-2xl border border-gray-200 dark:border-gray-800 overflow-hidden flex flex-col ${panelStyle.textareaBg}`}>
              <div className="px-4 py-2.5 border-b border-gray-100 dark:border-gray-800 flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <div className="text-xs font-medium text-gray-500 dark:text-gray-400">
                    {isOcrPreview ? "识别文本 · 预览" : contentLabel}
                  </div>
                  <div className="flex items-center gap-1 rounded-full border border-gray-200 dark:border-gray-700 bg-white/70 dark:bg-gray-900/50 p-0.5 text-[11px] text-gray-500">
                    <button
                      type="button"
                      onClick={() => setOcrViewMode("edit")}
                      className={`px-2 py-0.5 rounded-full ${!isOcrPreview ? "bg-gray-900 text-white" : "hover:text-gray-700 dark:hover:text-gray-200"}`}
                    >
                      编辑
                    </button>
                    <button
                      type="button"
                      onClick={() => setOcrViewMode("preview")}
                      className={`px-2 py-0.5 rounded-full ${isOcrPreview ? "bg-gray-900 text-white" : "hover:text-gray-700 dark:hover:text-gray-200"}`}
                    >
                      预览
                    </button>
                  </div>
                </div>
                <div className="text-xs text-gray-400">{charCount} 字</div>
              </div>
              <div className="relative flex-1">
                {isOcrPreview ? (
                  <div className="w-full h-full min-h-[220px] overflow-y-auto px-4 py-3 text-sm leading-relaxed text-gray-700 dark:text-gray-300 custom-scrollbar">
                    {(panelContent || "").trim() ? (
                      <Suspense fallback={<div className="text-sm text-gray-400 dark:text-gray-500">加载预览...</div>}>
                        <MarkdownRenderer content={panelContent} />
                      </Suspense>
                    ) : (
                      <div className="h-full flex items-center justify-center text-center px-6">
                        <div>
                          <div className="text-sm font-medium text-gray-500 dark:text-gray-400">{emptyTitle}</div>
                          <div className="text-xs text-gray-400 mt-1">{emptySubtitle}</div>
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <>
                    <textarea
                      className="w-full h-full min-h-[220px] resize-none border-0 bg-transparent px-4 py-3 text-sm leading-relaxed text-gray-700 dark:text-gray-300 custom-scrollbar focus:ring-0 focus:bg-white/80 dark:focus:bg-gray-900/60 transition-colors"
                      value={panelContent}
                      onChange={(e) => setPanelContent(e.target.value)}
                      placeholder={contentPlaceholder}
                      disabled={isUploadingFile}
                    />
                    {!(panelContent || "").trim() && (
                      <div className="pointer-events-none absolute inset-0 flex items-center justify-center px-6 text-center">
                        <div>
                          <div className="text-sm font-medium text-gray-500 dark:text-gray-400">{emptyTitle}</div>
                          <div className="text-xs text-gray-400 mt-1">{emptySubtitle}</div>
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          </div>
        )
      ) : (
        <div className="flex-1 p-0 relative min-h-[200px] md:min-h-0">
          <textarea
            className={`w-full h-full p-4 resize-none border-0 focus:ring-0 text-sm leading-relaxed text-gray-700 dark:text-gray-300 custom-scrollbar focus:bg-gray-50 dark:focus:bg-gray-800/50 transition-colors ${panelStyle.textareaBg}`}
            value={panelContent}
            onChange={(e) => setPanelContent(e.target.value)}
            placeholder={contentPlaceholder}
            disabled={isUploadingFile}
          />
        </div>
      )}
      <div className={`px-4 py-3 border-t border-gray-100 dark:border-gray-800 flex flex-wrap items-center justify-between gap-2 backdrop-blur-sm ${isMeetingMode ? "bg-white/95 dark:bg-gray-900/95" : "bg-gray-50/80 dark:bg-gray-800/80"}`}>
        <div className="flex items-center gap-2">
          <button onClick={handleManualSave} disabled={isProcessing || isUploadingFile || !panelContent.trim() || isSavingContext} className={secondaryActionClass}>
            {isSavingContext ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />} <span className="hidden sm:inline">保存</span>
          </button>
          <button onClick={handleExportWord} disabled={isProcessing || isUploadingFile || !panelContent.trim()} className={secondaryActionClass}>
            <Download size={16} /> <span className="hidden sm:inline">导出</span>
          </button>
        </div>
        {isOCRMode ? (
          <div className="flex items-center gap-2">
            <button
              onClick={onOcrStore}
              disabled={isOcrSaving || isUploadingFile || !panelContent.trim()}
              className={secondaryActionClass}
            >
              {isOcrSaving ? <Loader2 size={16} className="animate-spin" /> : <Database size={16} />} 数据库录入
            </button>
            <button
              onClick={handleGenerateSummary}
              disabled={isProcessing || isUploadingFile || !panelContent.trim()}
              className={primaryActionClass}
            >
              {isProcessing ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />} 智能分析
            </button>
          </div>
        ) : (
          <button onClick={handleGenerateSummary} disabled={isProcessing || isUploadingFile || !panelContent.trim()} className={primaryActionClass}>
            {isProcessing ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />} {isMeetingMode ? "生成纪要" : (isAuditMode ? "提交审单" : "智能分析")}
          </button>
        )}
      </div>
    </div>
  );
};

ModePanelComponent.displayName = 'ModePanel';

const ModePanel = React.memo(ModePanelComponent);

ModePanel.displayName = 'ModePanel';

export default ModePanel;
