import React, { useEffect, useRef, useState } from 'react';
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
} from 'lucide-react';
import MarkdownRenderer from './MarkdownRenderer';

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
    <div className="flex flex-col gap-3 w-full select-none bg-white/50 dark:bg-gray-800/50 rounded-xl p-3 border border-purple-100 dark:border-purple-900/30">
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
          className="flex-1 h-1.5 bg-gray-200 dark:bg-gray-700 rounded-lg appearance-none cursor-pointer accent-purple-600 dark:accent-purple-500 hover:accent-purple-700 focus:outline-none focus:ring-2 focus:ring-purple-500/20"
        />
        <span className="w-10">{formatTime(duration)}</span>
      </div>
      <div className="flex items-center justify-between px-1">
        <div className="flex items-center gap-4">
          <button
            onClick={togglePlay}
            className="p-2.5 rounded-full bg-purple-600 hover:bg-purple-700 text-white shadow-md hover:shadow-lg transition-all active:scale-95 flex items-center justify-center"
            title={isPlaying ? "暂停" : "播放"}
          >
            {isPlaying ? <Pause size={18} fill="currentColor" /> : <Play size={18} fill="currentColor" className="ml-0.5" />}
          </button>
          <button
            onClick={() => { if (audioRef.current) { audioRef.current.currentTime = Math.max(0, audioRef.current.currentTime - 10); } }}
            className="text-gray-500 hover:text-purple-600 dark:text-gray-400 dark:hover:text-purple-400 transition-colors p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full"
            title="后退 10秒"
          >
            <RotateCcw size={18} />
          </button>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 group relative">
            <button onClick={toggleMute} className="text-gray-400 hover:text-purple-600 dark:text-gray-500 dark:hover:text-purple-400 transition-colors">
              {isMuted || volume === 0 ? <VolumeX size={18} /> : (volume < 0.5 ? <Volume1 size={18} /> : <Volume2 size={18} />)}
            </button>
            <div className="w-16 md:w-20 flex items-center">
              <input type="range" min="0" max="1" step="0.05" value={isMuted ? 0 : volume} onChange={handleVolumeChange} className="w-full h-1 bg-gray-200 dark:bg-gray-700 rounded-lg appearance-none cursor-pointer accent-gray-400 hover:accent-purple-500" />
            </div>
          </div>
          <div className="w-px h-4 bg-gray-300 dark:bg-gray-700 mx-1"></div>
          <button onClick={toggleSpeed} className="flex items-center gap-1 px-2.5 py-1.5 rounded-md text-xs font-bold text-purple-600 dark:text-purple-400 bg-purple-50 dark:bg-purple-900/30 border border-purple-100 dark:border-purple-800 hover:bg-purple-100 dark:hover:bg-purple-900/50 transition-colors w-[52px] justify-center">
            {speed}x
          </button>
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
  onFileSelect,
  auditState,
  auditFile,
  onReset,
  notice,
  fullWidth = false,
}) => {
  const fileInputRef = useRef(null);
  const [expandedFindings, setExpandedFindings] = useState({});

  useEffect(() => {
    setExpandedFindings({});
  }, [auditState?.jobId]);

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
    { key: "extract", label: "字段抽取" },
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
    : (riskLevel === "medium" ? "建议人工复核/补材料" : "建议通过");
  const isPass = typeof result.pass === "boolean" ? result.pass : riskLevel === "low";

  const extracted = result.extracted_fields || {};
  const fieldPreview = [
    { key: "total_amount", label: "金额" },
    { key: "invoice_no", label: "发票号" },
    { key: "contract_no", label: "合同号" },
    { key: "vendor", label: "供应商" },
  ].filter((item) => extracted[item.key]);

  const statusLabel = status === "uploading" ? "文件上传中" : (status === "pending" ? "排队中" : "审单进行中");

  const widthClass = fullWidth ? "md:w-full md:border-r-0" : "md:w-1/2 md:border-r";

  return (
    <div className={`w-full ${widthClass} flex flex-col flex-shrink-0 border-b md:border-b-0 border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 transition-all duration-300 ${panelStyle.border} shadow-sm z-20`}>
      <div className={`px-4 py-3 border-b flex justify-between items-center ${panelStyle.headerBg} ${panelStyle.border}`}>
        <div className={`flex items-center gap-2 font-medium ${panelStyle.headerText}`}>
          <ClipboardCheck size={18} />
          <span className="truncate">智能审单</span>
        </div>
        {isBusy && (
          <span className={`text-xs flex items-center gap-1 ${panelStyle.headerText}`}>
            <Loader2 size={12} className="animate-spin" /> {statusLabel}
          </span>
        )}
      </div>

      <div className="flex-1 p-4 overflow-y-auto space-y-4 custom-scrollbar">
        {notice && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 text-amber-700 text-xs px-3 py-2">
            {notice}
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

        <div className="rounded-xl border border-gray-200 dark:border-gray-800 p-4 bg-white dark:bg-gray-900">
          <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">单据类型（可选）</div>
          <div className="flex flex-wrap gap-2">
            {docTypes.map((item) => {
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

        <div className="rounded-xl border border-dashed border-gray-200 dark:border-gray-700 p-4 bg-gray-50/60 dark:bg-gray-900/40">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-teal-50 text-teal-600 flex items-center justify-center">
              <FileUp size={18} />
            </div>
            <div className="flex-1">
              <div className="text-sm font-medium text-gray-800 dark:text-gray-200">上传审单文件</div>
              <div className="text-xs text-gray-500 dark:text-gray-400">支持图片 / PDF / Word</div>
            </div>
          </div>
          <div className="mt-3 flex items-center gap-2">
            <button
              type="button"
              onClick={() => fileInputRef.current && fileInputRef.current.click()}
              disabled={isBusy}
              className="px-3 py-1.5 rounded-lg bg-black text-white text-xs font-medium disabled:opacity-50 disabled:cursor-not-allowed"
            >
              选择文件
            </button>
            <span className="text-[11px] text-gray-400">选择后立即开始审单</span>
          </div>
          {auditFile && (
            <div className="mt-2 px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 text-xs text-gray-600 dark:text-gray-300 bg-white dark:bg-gray-800 flex items-center justify-between gap-3">
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
              {result.summary && <div className="text-sm text-gray-600 dark:text-gray-300">{result.summary}</div>}
              <div className="text-xs text-gray-500 dark:text-gray-400">
                建议动作：<span className="text-gray-700 dark:text-gray-200 font-medium">{actionAdvice}</span>
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

            <div className="rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900">
              <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-800 text-sm font-medium text-gray-800 dark:text-gray-200">
                问题清单
              </div>
              <div className="p-4 space-y-3">
                {sortedFindings.length === 0 && (
                  <div className="text-sm text-gray-500 dark:text-gray-400">未发现需要提示的问题。</div>
                )}
                {sortedFindings.map((finding, idx) => {
                  const key = finding.rule_id || `finding-${idx}`;
                  const severity = String(finding.severity || "").toLowerCase();
                  const severityStyle = severity === "high"
                    ? "bg-red-50 text-red-600 border-red-100"
                    : (severity === "medium" ? "bg-amber-50 text-amber-600 border-amber-100" : "bg-emerald-50 text-emerald-600 border-emerald-100");
                  const expanded = !!expandedFindings[key];
                  const evidence = finding.evidence || {};
                  const evidenceText = typeof evidence === "string" ? evidence : evidence.text;
                  const evidenceHighlight = typeof evidence === "string" ? "" : evidence.highlight;

                  return (
                    <div key={key} className="rounded-lg border border-gray-100 dark:border-gray-800 bg-gray-50/60 dark:bg-gray-900/30">
                      <button
                        type="button"
                        onClick={() => setExpandedFindings((prev) => ({ ...prev, [key]: !expanded }))}
                        className="w-full text-left px-3 py-3 flex items-start justify-between gap-3"
                      >
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <span className={`px-2 py-0.5 rounded-full text-[10px] border ${severityStyle}`}>
                              {severity === "high" ? "高风险" : (severity === "medium" ? "中风险" : "低风险")}
                            </span>
                            <span className="text-sm font-medium text-gray-800 dark:text-gray-100">
                              {finding.message || "规则命中"}
                            </span>
                          </div>
                          {finding.suggestion && (
                            <div className="text-xs text-gray-600 dark:text-gray-300 mt-1">
                              建议：{finding.suggestion}
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
            className="px-4 py-2 rounded-lg text-sm font-medium bg-black text-white"
          >
            重新审单
          </button>
        </div>
      )}
    </div>
  );
};

const ModePanel = ({
  panelStyle,
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
  auditFile,
  auditNotice,
  onAuditDocTypeChange,
  onAuditFileSelect,
  onAuditReset,
  ocrEngine,
  onOcrEngineChange,
  fullWidth = false,
}) => {
  const [ocrViewMode, setOcrViewMode] = useState("edit");
  if (isAuditMode) {
    return (
      <AuditPanel
        panelStyle={panelStyle}
        panelContent={panelContent}
        docTypes={auditDocTypes}
        docType={auditDocType}
        onDocTypeChange={onAuditDocTypeChange}
        onFileSelect={onAuditFileSelect}
        auditState={auditState}
        auditFile={auditFile}
        onReset={onAuditReset}
        notice={auditNotice}
        fullWidth={fullWidth}
      />
    );
  }
  const showEnhancedPanel = isMeetingMode || isOCRMode;
  const panelTitle = isMeetingMode ? "会议纪要 · 转写区" : (isOCRMode ? "OCR 智能录入" : "内容面板");
  const statusLabel = isMeetingMode ? "转写中..." : "识别中...";
  const guideTitle = isMeetingMode ? "会议纪要整理" : "OCR 识别与录入";
  const guideDesc = isMeetingMode
    ? "上传音频后自动转写，支持编辑补充，再生成纪要。"
    : "上传图片或 PDF，自动识别文本，可直接修订并智能录入。";
  const stepItems = isMeetingMode
    ? ["上传音频", "自动转写", "生成纪要"]
    : ["上传文件", "文本识别", "智能录入"];
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
  const charCount = (panelContent || "").replace(/\s/g, "").length;
  const widthClass = fullWidth ? "md:w-full md:border-r-0" : "md:w-1/2 md:border-r";
  const isOcrPreview = isOCRMode && ocrViewMode === "preview";

  return (
    <div className={`w-full ${widthClass} flex flex-col flex-shrink-0 border-b md:border-b-0 border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 transition-all duration-300 ${panelStyle.border} shadow-sm z-20`}>
      <div className={`px-4 py-3 border-b flex justify-between items-center ${panelStyle.headerBg} ${panelStyle.border}`}>
        <div className={`flex items-center gap-2 font-medium ${panelStyle.headerText}`}>
          {isMeetingMode && <Zap size={18} />}
          {isOCRMode && <ScanText size={18} />}
          {isAuditMode && <ClipboardCheck size={18} />}
          <span className="truncate">{panelTitle}</span>
        </div>
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
      {showEnhancedPanel ? (
        <div className="flex-1 p-4 md:p-5 flex flex-col gap-4 overflow-hidden">
          <div className={`rounded-2xl border ${panelStyle.border} bg-gradient-to-br from-white to-gray-50/80 dark:from-gray-900 dark:to-gray-800/60 p-4`}>
            <div className="flex items-start gap-3">
              <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${panelStyle.headerBg} ${panelStyle.headerText}`}>
                {isMeetingMode ? <Zap size={16} /> : <ScanText size={16} />}
              </div>
              <div className="flex-1">
                <div className="text-sm font-semibold text-gray-900 dark:text-white">{guideTitle}</div>
                <div className="text-xs text-gray-500 dark:text-gray-400">{guideDesc}</div>
              </div>
              <div className="text-[11px] text-gray-400">{isMeetingMode ? "语音" : "图片/PDF"}</div>
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2 text-[11px] text-gray-500 dark:text-gray-400">
              {stepItems.map((item, idx) => (
                <div key={item} className="rounded-full border border-gray-200 dark:border-gray-700 px-2.5 py-1 bg-white/70 dark:bg-gray-900/70 text-center">
                  <span className="font-medium text-gray-700 dark:text-gray-200">{idx + 1}</span> {item}
                </div>
              ))}
            </div>
          </div>

          {isMeetingMode && audioFileUrl && (
            <div className="border border-purple-100 dark:border-purple-900/50 bg-purple-50/30 dark:bg-purple-900/10 rounded-2xl p-3 animate-in slide-in-from-bottom-2">
              <AudioPlayer src={audioFileUrl} />
            </div>
          )}

          <div className={`flex-1 rounded-2xl border border-gray-200 dark:border-gray-800 overflow-hidden flex flex-col ${panelStyle.textareaBg}`}>
            <div className="px-4 py-2.5 border-b border-gray-100 dark:border-gray-800 flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <div className="text-xs font-medium text-gray-500 dark:text-gray-400">
                  {isOcrPreview ? "识别文本 · 预览" : contentLabel}
                </div>
                {isOCRMode && (
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
                )}
              </div>
              <div className="text-xs text-gray-400">{charCount} 字</div>
            </div>
            <div className="relative flex-1">
              {isOcrPreview ? (
                <div className="w-full h-full min-h-[220px] overflow-y-auto px-4 py-3 text-sm leading-relaxed text-gray-700 dark:text-gray-300 custom-scrollbar">
                  {(panelContent || "").trim() ? (
                    <MarkdownRenderer content={panelContent} />
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
      <div className="px-4 py-3 bg-gray-50/80 dark:bg-gray-800/80 border-t border-gray-100 dark:border-gray-800 flex flex-wrap items-center justify-between gap-2 backdrop-blur-sm">
        <div className="flex items-center gap-2">
          <button onClick={handleManualSave} disabled={isProcessing || isUploadingFile || !panelContent.trim() || isSavingContext} className="flex items-center gap-2 bg-white dark:bg-gray-700 hover:bg-gray-100 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-200 border border-gray-200 dark:border-gray-600 px-3 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm">
            {isSavingContext ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />} <span className="hidden sm:inline">保存</span>
          </button>
          <button onClick={handleExportWord} disabled={isProcessing || isUploadingFile || !panelContent.trim()} className="flex items-center gap-2 bg-white dark:bg-gray-700 hover:bg-gray-100 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-200 border border-gray-200 dark:border-gray-600 px-3 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm">
            <Download size={16} /> <span className="hidden sm:inline">导出</span>
          </button>
        </div>
        {isOCRMode ? (
          <div className="flex items-center gap-2">
            <button
              onClick={onOcrStore}
              disabled={isOcrSaving || isUploadingFile || !panelContent.trim()}
              className="flex items-center gap-2 bg-white dark:bg-gray-700 hover:bg-gray-100 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-200 border border-gray-200 dark:border-gray-600 px-3 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
            >
              {isOcrSaving ? <Loader2 size={16} className="animate-spin" /> : <Database size={16} />} 数据库录入
            </button>
            <button
              onClick={handleGenerateSummary}
              disabled={isProcessing || isUploadingFile || !panelContent.trim()}
              className={`flex items-center gap-2 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm hover:shadow ${panelStyle.btnBg}`}
            >
              {isProcessing ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />} 智能分析
            </button>
          </div>
        ) : (
          <button onClick={handleGenerateSummary} disabled={isProcessing || isUploadingFile || !panelContent.trim()} className={`flex items-center gap-2 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm hover:shadow ${panelStyle.btnBg}`}>
            {isProcessing ? <Loader2 size={16} className="animate-spin" /> : <Sparkles size={16} />} {isMeetingMode ? "生成纪要" : (isAuditMode ? "提交审单" : "智能分析")}
          </button>
        )}

      </div>
    </div>
  );
};
export default ModePanel;
