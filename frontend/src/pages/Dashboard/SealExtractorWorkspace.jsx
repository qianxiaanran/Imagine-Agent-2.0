import React, { useEffect, useRef, useState } from "react";
import { ArrowLeft, Download, FileUp, Image as ImageIcon, Loader2, RefreshCw, Sparkles, X } from "lucide-react";
import { downloadBlobFile } from "../../utils/browserActions";
import { API_BASE_URL, AUTH_TOKEN_KEY } from "../../api/apiClient";

const DEFAULT_SETTINGS = {
  extractMode: "smart",
  targetColor: "#d81e2f",
  tolerance: 30,
  grayThreshold: 0.06,
  channelMode: "auto",
  channelRatio: 38,
  cropMode: "focus",
  fillRadius: 10,
};

const CHANNEL_OPTIONS = [
  { key: "auto", label: "自动" },
  { key: "r", label: "R" },
  { key: "g", label: "G" },
  { key: "b", label: "B" },
];

const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

const formatKilobytes = (value) => {
  if (!Number.isFinite(value) || value <= 0) return "-- KB";
  return `${(value / 1024).toFixed(value >= 1024 * 100 ? 0 : 1)} KB`;
};

const formatRatio = (part, total) => {
  if (!Number.isFinite(part) || !Number.isFinite(total) || total <= 0) return "--";
  return `${((part / total) * 100).toFixed(1)}%`;
};

const hexToRgb = (hex) => {
  const normalized = String(hex || "")
    .trim()
    .replace("#", "")
    .padEnd(6, "0")
    .slice(0, 6);

  return {
    r: Number.parseInt(normalized.slice(0, 2), 16) || 0,
    g: Number.parseInt(normalized.slice(2, 4), 16) || 0,
    b: Number.parseInt(normalized.slice(4, 6), 16) || 0,
  };
};

const loadImage = (src) =>
  new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("图片加载失败，请更换更清晰的 JPG/PNG 图片。"));
    image.src = src;
  });

const canvasToBlob = (canvas) =>
  new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) {
        resolve(blob);
        return;
      }
      reject(new Error("PNG 导出失败，请稍后重试。"));
    }, "image/png");
  });

const resolveAssetUrl = (value) => {
  const raw = String(value || "").trim();
  if (!raw) return "";
  if (/^https?:\/\//i.test(raw)) return raw;
  if (raw.startsWith("blob:")) return raw;
  if (raw.startsWith("/")) return `${API_BASE_URL}${raw}`;
  return `${API_BASE_URL}/${raw.replace(/^\/+/, "")}`;
};

const revokeObjectUrl = (value) => {
  if (typeof value === "string" && value.startsWith("blob:")) {
    URL.revokeObjectURL(value);
  }
};

const normalizeSealResultItem = (rawItem, index, mode) => {
  const item = rawItem && typeof rawItem === "object" ? rawItem : {};
  return {
    id: String(item.candidate_index ?? index),
    label: item.candidate_label || `印章 ${index + 1}`,
    resultUrl: resolveAssetUrl(item.result_url || item.resultUrl),
    downloadName: item.download_name || item.downloadName || `seal_${index + 1}.png`,
    blob: item.blob || null,
    pixelCount: Number(item.pixel_count ?? item.pixelCount ?? 0),
    resultSizeBytes: Number(item.result_size_bytes ?? item.resultSizeBytes ?? item.blob?.size ?? 0),
    bbox: Array.isArray(item.bbox) ? item.bbox : null,
    pageIndex: Number(item.page_index ?? item.pageIndex ?? 0),
    mode,
    raw: item,
  };
};

const buildMetaFromSealItem = (item) => ({
  ...(item?.raw || {}),
  mode: item?.mode || "idle",
  detectionSource: item?.raw?.detection_source || item?.raw?.detectionSource || "",
  pixelCount: Number(item?.pixelCount || 0),
  result_size_bytes: Number(item?.resultSizeBytes || 0),
});

const buildPersistableSealItem = (item, index) => {
  if (!item?.resultUrl || item.resultUrl.startsWith("blob:")) return null;
  const raw = item?.raw && typeof item.raw === "object" ? { ...item.raw } : {};
  delete raw.blob;
  return {
    ...raw,
    candidate_index: Number(item?.raw?.candidate_index ?? item?.id ?? index),
    candidate_label: item?.label || `印章 ${index + 1}`,
    result_url: item.resultUrl,
    download_name: item.downloadName || `seal_${index + 1}.png`,
    pixel_count: Number(item?.pixelCount || 0),
    result_size_bytes: Number(item?.resultSizeBytes || 0),
    bbox: Array.isArray(item?.bbox) ? item.bbox : null,
    page_index: Number(item?.pageIndex ?? 0),
  };
};

const buildSealHistorySnapshot = ({
  sourcePersistUrl,
  sourceName,
  sourceSizeBytes,
  settings,
  resultItems,
  selectedResultIndex,
  archiveUrl,
  archiveDownloadName,
}) => {
  if (!sourcePersistUrl || sourcePersistUrl.startsWith("blob:")) return null;
  const items = (resultItems || [])
    .map((item, index) => buildPersistableSealItem(item, index))
    .filter(Boolean);
  if (!items.length) return null;
  const safeSelectedIndex = clamp(Number(selectedResultIndex || 0), 0, items.length - 1);
  const selectedItem = items[safeSelectedIndex];
  return {
    version: 1,
    tool: "seal_extractor",
    workspace: "seal",
    source_url: sourcePersistUrl,
    source_name: sourceName || "seal-source",
    source_size_bytes: Number(sourceSizeBytes || 0),
    settings: { ...DEFAULT_SETTINGS, ...(settings || {}) },
    selected_index: safeSelectedIndex,
    item_count: items.length,
    items,
    archive_url: archiveUrl || "",
    archive_download_name: archiveDownloadName || "seals.zip",
    ...(selectedItem || {}),
  };
};

const normalizeSealHistorySnapshot = (rawSnapshot) => {
  const snapshot = rawSnapshot && typeof rawSnapshot === "object" ? rawSnapshot : null;
  if (!snapshot) return null;

  const sourceUrl = resolveAssetUrl(snapshot.source_url || snapshot.sourceUrl);
  const itemList = Array.isArray(snapshot.items) && snapshot.items.length
    ? snapshot.items
    : (snapshot.result_url || snapshot.resultUrl ? [snapshot] : []);
  const items = itemList
    .map((item, index) => normalizeSealResultItem(item, index, "history"))
    .filter((item) => item.resultUrl);

  if (!sourceUrl && !items.length) return null;

  const selectedIndex = items.length
    ? clamp(Number(snapshot.selected_index ?? snapshot.selectedIndex ?? 0), 0, items.length - 1)
    : 0;

  return {
    sourceUrl,
    sourceName: snapshot.source_name || snapshot.sourceName || "历史记录",
    sourceSizeBytes: Number(snapshot.source_size_bytes ?? snapshot.sourceSizeBytes ?? 0),
    settings: { ...DEFAULT_SETTINGS, ...(snapshot.settings && typeof snapshot.settings === "object" ? snapshot.settings : {}) },
    items,
    selectedIndex,
    archiveUrl: resolveAssetUrl(snapshot.archive_url || snapshot.archiveUrl),
    archiveDownloadName: snapshot.archive_download_name || snapshot.archiveDownloadName || "seals.zip",
  };
};

const runServerSealExtraction = async (file, settings, signal) => {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("target_color", settings.targetColor);
  formData.append("tolerance", String(settings.tolerance));
  formData.append("gray_threshold", String(settings.grayThreshold));
  formData.append("channel_mode", settings.channelMode);
  formData.append("channel_ratio", String(settings.channelRatio));
  formData.append("crop_mode", settings.cropMode);
  formData.append("fill_radius", String(settings.fillRadius));
  formData.append("extract_mode", settings.extractMode);
  formData.append("prefer_paddle", "true");

  const token = localStorage.getItem(AUTH_TOKEN_KEY);
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  const response = await fetch(`${API_BASE_URL}/api/ocr/seal-extract`, {
    method: "POST",
    headers,
    body: formData,
    signal,
  });

  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok || data?.success === false) {
    throw new Error(data?.error || `印章提取接口请求失败 (${response.status})`);
  }

  const payload = data?.data || {};
  return {
    resultUrl: resolveAssetUrl(payload.result_url),
    downloadName: payload.download_name || "seal_transparent.png",
    meta: payload,
  };
};

const dilateAlpha = (alpha, width, height, iterations) => {
  let current = alpha;
  for (let step = 0; step < iterations; step += 1) {
    const next = new Uint8ClampedArray(current.length);
    for (let y = 0; y < height; y += 1) {
      const rowOffset = y * width;
      for (let x = 0; x < width; x += 1) {
        const idx = rowOffset + x;
        let value = current[idx];
        if (x > 0) value = Math.max(value, current[idx - 1]);
        if (x < width - 1) value = Math.max(value, current[idx + 1]);
        if (y > 0) value = Math.max(value, current[idx - width]);
        if (y < height - 1) value = Math.max(value, current[idx + width]);
        next[idx] = value;
      }
    }
    current = next;
  }
  return current;
};

const erodeAlpha = (alpha, width, height, iterations) => {
  let current = alpha;
  for (let step = 0; step < iterations; step += 1) {
    const next = new Uint8ClampedArray(current.length);
    for (let y = 0; y < height; y += 1) {
      const rowOffset = y * width;
      for (let x = 0; x < width; x += 1) {
        const idx = rowOffset + x;
        let value = current[idx];
        if (x > 0) value = Math.min(value, current[idx - 1]);
        if (x < width - 1) value = Math.min(value, current[idx + 1]);
        if (y > 0) value = Math.min(value, current[idx - width]);
        if (y < height - 1) value = Math.min(value, current[idx + width]);
        next[idx] = value;
      }
    }
    current = next;
  }
  return current;
};

const extractSeal = async (sourceUrl, settings) => {
  const image = await loadImage(sourceUrl);
  const maxSide = 1600;
  const scale = Math.min(1, maxSide / Math.max(image.width, image.height, 1));
  const width = Math.max(1, Math.round(image.width * scale));
  const height = Math.max(1, Math.round(image.height * scale));
  const workCanvas = document.createElement("canvas");
  workCanvas.width = width;
  workCanvas.height = height;
  const context = workCanvas.getContext("2d", { willReadFrequently: true });
  if (!context) {
    throw new Error("当前浏览器不支持画布处理。");
  }

  context.drawImage(image, 0, 0, width, height);
  const frame = context.getImageData(0, 0, width, height);
  const data = frame.data;
  const alpha = new Uint8ClampedArray(width * height);
  const target = hexToRgb(settings.targetColor);
  const targetChannelIndex =
    target.r >= target.g && target.r >= target.b ? 0 : target.g >= target.b ? 1 : 2;
  const selectedChannelIndex =
    settings.channelMode === "r"
      ? 0
      : settings.channelMode === "g"
        ? 1
        : settings.channelMode === "b"
          ? 2
          : targetChannelIndex;

  const toleranceDistance = 30 + Number(settings.tolerance || 0) * 2.6;
  const grayThreshold = clamp(Number(settings.grayThreshold || 0.06), 0.01, 0.95);
  const ratioFactor = 1 + Number(settings.channelRatio || 0) / 45;

  let maskCount = 0;

  for (let idx = 0; idx < alpha.length; idx += 1) {
    const pixelOffset = idx * 4;
    const r = data[pixelOffset];
    const g = data[pixelOffset + 1];
    const b = data[pixelOffset + 2];
    const pixelAlpha = data[pixelOffset + 3];
    if (!pixelAlpha) continue;

    const maxChannel = Math.max(r, g, b);
    const minChannel = Math.min(r, g, b);
    const saturation = maxChannel === 0 ? 0 : (maxChannel - minChannel) / maxChannel;
    const brightness = (r + g + b) / (255 * 3);
    const channelValues = [r, g, b];
    const selected = channelValues[selectedChannelIndex];
    const others = channelValues.filter((_, channelIndex) => channelIndex !== selectedChannelIndex);
    const otherMax = Math.max(...others, 0);
    const dominance = clamp((selected - otherMax) / 255, 0, 1);
    const ratioScore = clamp((selected / Math.max(1, otherMax) - ratioFactor) / 1.4, 0, 1);

    const dr = r - target.r;
    const dg = g - target.g;
    const db = b - target.b;
    const distance = Math.sqrt(dr * dr + dg * dg + db * db);
    const colorScore = clamp(1 - distance / toleranceDistance, 0, 1);
    const grayScore = clamp((saturation - grayThreshold) / Math.max(0.05, 1 - grayThreshold), 0, 1);
    const inkScore = clamp((1 - brightness) * 0.7 + saturation * 0.8, 0, 1);

    const score =
      settings.extractMode === "red"
        ? colorScore * Math.max(dominance, ratioScore, 0.08) * Math.max(grayScore, 0.15)
        : Math.max(colorScore * Math.max(grayScore, 0.2), dominance * 0.9, ratioScore * 0.82) * Math.max(inkScore, 0.18);

    const nextAlpha = Math.round(clamp(score, 0, 1) * 255);
    alpha[idx] = nextAlpha < 18 ? 0 : nextAlpha;
    if (alpha[idx] > 18) maskCount += 1;
  }

  const iterations = Math.max(0, Math.min(3, Math.round(Number(settings.fillRadius || 0) / 4)));
  let processedAlpha = alpha;
  if (iterations > 0) {
    processedAlpha = dilateAlpha(processedAlpha, width, height, iterations);
    processedAlpha = erodeAlpha(processedAlpha, width, height, iterations);
  }

  let minX = width;
  let minY = height;
  let maxX = -1;
  let maxY = -1;

  for (let y = 0; y < height; y += 1) {
    const rowOffset = y * width;
    for (let x = 0; x < width; x += 1) {
      const value = processedAlpha[rowOffset + x];
      if (value <= 22) continue;
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }
  }

  const hasMask = maxX >= minX && maxY >= minY;
  const padding = Math.max(8, Math.round(Number(settings.fillRadius || 0) * 1.2));
  const cropToSeal = settings.cropMode === "focus" && hasMask;
  const left = cropToSeal ? Math.max(0, minX - padding) : 0;
  const top = cropToSeal ? Math.max(0, minY - padding) : 0;
  const right = cropToSeal ? Math.min(width - 1, maxX + padding) : width - 1;
  const bottom = cropToSeal ? Math.min(height - 1, maxY + padding) : height - 1;
  const outputWidth = Math.max(1, right - left + 1);
  const outputHeight = Math.max(1, bottom - top + 1);

  const outputCanvas = document.createElement("canvas");
  outputCanvas.width = outputWidth;
  outputCanvas.height = outputHeight;
  const outputContext = outputCanvas.getContext("2d");
  if (!outputContext) {
    throw new Error("当前浏览器不支持结果导出。");
  }

  const outputFrame = outputContext.createImageData(outputWidth, outputHeight);
  const outputData = outputFrame.data;

  for (let y = 0; y < outputHeight; y += 1) {
    const sourceY = top + y;
    for (let x = 0; x < outputWidth; x += 1) {
      const sourceX = left + x;
      const sourceIndex = sourceY * width + sourceX;
      const outputIndex = (y * outputWidth + x) * 4;
      const currentAlpha = processedAlpha[sourceIndex];
      if (currentAlpha <= 18) continue;
      outputData[outputIndex] = target.r;
      outputData[outputIndex + 1] = target.g;
      outputData[outputIndex + 2] = target.b;
      outputData[outputIndex + 3] = clamp(Math.round((currentAlpha / 255) ** 0.92 * 255), 0, 255);
    }
  }

  outputContext.putImageData(outputFrame, 0, 0);
  const blob = await canvasToBlob(outputCanvas);

  return {
    blob,
    pixelCount: maskCount,
  };
};

const SealExtractorWorkspace = ({
  isMobileViewport = false,
  onBack,
  onNotice,
  initialSnapshot = null,
  onPersistSnapshot,
}) => {
  const fileInputRef = useRef(null);
  const noticeRef = useRef(onNotice);
  const localResultUrlRef = useRef("");
  const persistSignatureRef = useRef("");
  const hydratingSnapshotRef = useRef(false);
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const [sourceFile, setSourceFile] = useState(null);
  const [sourceUrl, setSourceUrl] = useState("");
  const [sourcePersistUrl, setSourcePersistUrl] = useState("");
  const [sourceName, setSourceName] = useState("");
  const [sourceSizeBytes, setSourceSizeBytes] = useState(0);
  const [resultUrl, setResultUrl] = useState("");
  const [resultBlob, setResultBlob] = useState(null);
  const [resultDownloadName, setResultDownloadName] = useState("seal_transparent.png");
  const [resultItems, setResultItems] = useState([]);
  const [selectedResultIndex, setSelectedResultIndex] = useState(0);
  const [archiveUrl, setArchiveUrl] = useState("");
  const [archiveDownloadName, setArchiveDownloadName] = useState("seals.zip");
  const [isProcessing, setIsProcessing] = useState(false);
  const [resultMeta, setResultMeta] = useState({ pixelCount: 0, mode: "idle", detectionSource: "" });

  useEffect(() => {
    noticeRef.current = onNotice;
  }, [onNotice]);

  const revokeLocalResultUrl = () => {
    if (localResultUrlRef.current) {
      URL.revokeObjectURL(localResultUrlRef.current);
      localResultUrlRef.current = "";
    }
  };

  const resetResultState = () => {
    revokeLocalResultUrl();
    setResultUrl("");
    setResultBlob(null);
    setResultDownloadName("seal_transparent.png");
    setResultItems([]);
    setSelectedResultIndex(0);
    setArchiveUrl("");
    setArchiveDownloadName("seals.zip");
    setResultMeta({ pixelCount: 0, mode: "idle", detectionSource: "" });
  };

  const applySelectedResultItem = (item) => {
    if (!item) {
      setResultUrl("");
      setResultBlob(null);
      setResultDownloadName("seal_transparent.png");
      setResultMeta({ pixelCount: 0, mode: "idle", detectionSource: "" });
      return;
    }
    setResultUrl(item.resultUrl || "");
    setResultBlob(item.blob || null);
    setResultDownloadName(item.downloadName || "seal_transparent.png");
    setResultMeta(buildMetaFromSealItem(item));
  };

  useEffect(() => () => {
    revokeObjectUrl(sourceUrl);
  }, [sourceUrl]);

  useEffect(() => () => {
    revokeLocalResultUrl();
  }, []);

  useEffect(() => {
    const normalized = normalizeSealHistorySnapshot(initialSnapshot);
    if (!normalized) return;

    hydratingSnapshotRef.current = true;
    revokeLocalResultUrl();
    setSourceFile(null);
    setSourceUrl(normalized.sourceUrl || "");
    setSourcePersistUrl(normalized.sourceUrl || "");
    setSourceName(normalized.sourceName || "");
    setSourceSizeBytes(Number(normalized.sourceSizeBytes || 0));
    setSettings(normalized.settings);
    setResultItems(normalized.items);
    setSelectedResultIndex(normalized.selectedIndex);
    setArchiveUrl(normalized.archiveUrl);
    setArchiveDownloadName(normalized.archiveDownloadName);
    applySelectedResultItem(normalized.items[normalized.selectedIndex] || null);
    persistSignatureRef.current = JSON.stringify({
      sourceUrl: normalized.sourceUrl,
      selectedIndex: normalized.selectedIndex,
      itemCount: normalized.items.length,
    });
  }, [initialSnapshot]);

  useEffect(() => {
    if (!sourceUrl) {
      if (hydratingSnapshotRef.current) {
        return undefined;
      }
      revokeLocalResultUrl();
      setResultUrl("");
      setResultBlob(null);
      setResultDownloadName("seal_transparent.png");
      setResultItems([]);
      setSelectedResultIndex(0);
      setArchiveUrl("");
      setArchiveDownloadName("seals.zip");
      setResultMeta({ pixelCount: 0, mode: "idle", detectionSource: "" });
      return undefined;
    }
    hydratingSnapshotRef.current = false;
    if (!sourceFile) {
      return undefined;
    }

    let disposed = false;
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 60000);
    const timer = window.setTimeout(async () => {
      setIsProcessing(true);
      try {
        const serverOutput = await runServerSealExtraction(sourceFile, settings, controller.signal);
        if (disposed) return;
        revokeLocalResultUrl();
        const serverItemsRaw = Array.isArray(serverOutput.meta?.items) && serverOutput.meta.items.length
          ? serverOutput.meta.items
          : [serverOutput.meta];
        const serverItems = serverItemsRaw
          .map((item, index) => normalizeSealResultItem(item, index, "server"))
          .filter((item) => item.resultUrl);
        if (!serverItems.length) {
          throw new Error("后端未返回可用的印章结果。");
        }
        const nextSelectedIndex = clamp(Number(serverOutput.meta?.selected_index || 0), 0, serverItems.length - 1);
        const persistedSourceUrl = resolveAssetUrl(serverOutput.meta?.source_url);
        setResultItems(serverItems);
        setSelectedResultIndex(nextSelectedIndex);
        setSourcePersistUrl(persistedSourceUrl);
        setSourceName(serverOutput.meta?.source_name || sourceFile?.name || "");
        setSourceSizeBytes(Number(serverOutput.meta?.source_size_bytes ?? sourceFile?.size ?? 0));
        setArchiveUrl(resolveAssetUrl(serverOutput.meta?.archive_url));
        setArchiveDownloadName(serverOutput.meta?.archive_download_name || `${String(sourceFile?.name || "seal").replace(/\.[^.]+$/, "")}_seals.zip`);
        applySelectedResultItem(serverItems[nextSelectedIndex]);
      } catch (error) {
        if (disposed) return;
        if (error?.name === "AbortError") return;
        try {
          const output = await extractSeal(sourceUrl, settings);
          if (disposed) return;
          revokeLocalResultUrl();
          const nextUrl = URL.createObjectURL(output.blob);
          localResultUrlRef.current = nextUrl;
          const localItem = normalizeSealResultItem(
            {
              resultUrl: nextUrl,
              downloadName: `${String(sourceFile?.name || "seal").replace(/\.[^.]+$/, "").replace(/[^\w\u4e00-\u9fa5-]+/g, "_") || "seal"}_transparent.png`,
              blob: output.blob,
              pixel_count: output.pixelCount,
              result_size_bytes: output.blob.size,
              detection_source: "browser_local_preview",
            },
            0,
            "local"
          );
          setResultItems([localItem]);
          setSelectedResultIndex(0);
          setSourcePersistUrl("");
          setArchiveUrl("");
          setArchiveDownloadName("seals.zip");
          applySelectedResultItem(localItem);
          noticeRef.current?.(
            `后端印章提取接口暂不可用，已切换为浏览器本地预览模式：${error?.message || "未知错误"}`,
            "amber"
          );
        } catch (localError) {
          revokeLocalResultUrl();
          setResultUrl("");
          setResultBlob(null);
          setResultDownloadName("seal_transparent.png");
          setResultItems([]);
          setSelectedResultIndex(0);
          setArchiveUrl("");
          setArchiveDownloadName("seals.zip");
          setResultMeta({ pixelCount: 0, mode: "error", detectionSource: "" });
          noticeRef.current?.(localError?.message || "印章提取失败，请更换图片后重试。", "rose");
        }
      } finally {
        if (!disposed) {
          window.clearTimeout(timeoutId);
          setIsProcessing(false);
        }
      }
    }, 120);

    return () => {
      disposed = true;
      window.clearTimeout(timer);
      window.clearTimeout(timeoutId);
      controller.abort();
    };
  }, [settings, sourceFile, sourceUrl]);

  useEffect(() => {
    if (typeof onPersistSnapshot !== "function") return;
    if (!sourceFile || !resultItems.length) return;

    const snapshot = buildSealHistorySnapshot({
      sourcePersistUrl,
      sourceName: sourceName || sourceFile?.name || "",
      sourceSizeBytes: Number(sourceSizeBytes || sourceFile?.size || 0),
      settings,
      resultItems,
      selectedResultIndex,
      archiveUrl,
      archiveDownloadName,
    });
    if (!snapshot) return;

    const nextSignature = JSON.stringify(snapshot);
    if (persistSignatureRef.current === nextSignature) return;
    persistSignatureRef.current = nextSignature;
    Promise.resolve(onPersistSnapshot(snapshot)).catch((error) => {
      console.error("Failed to persist seal history snapshot", error);
    });
  }, [
    archiveDownloadName,
    archiveUrl,
    onPersistSnapshot,
    resultItems,
    selectedResultIndex,
    settings,
    sourceFile,
    sourceName,
    sourcePersistUrl,
    sourceSizeBytes,
  ]);

  const updateSetting = (key, value) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  };

  const resetSettings = () => {
    setSettings(DEFAULT_SETTINGS);
  };

  const clearAll = () => {
    hydratingSnapshotRef.current = false;
    revokeObjectUrl(sourceUrl);
    setSourceFile(null);
    setSourceUrl("");
    setSourcePersistUrl("");
    setSourceName("");
    setSourceSizeBytes(0);
    persistSignatureRef.current = "";
    resetResultState();
    setSettings(DEFAULT_SETTINGS);
  };

  const acceptFile = (file) => {
    if (!file) return;
    if (!String(file.type || "").startsWith("image/")) {
      noticeRef.current?.("印章提取工具当前仅支持 JPG/PNG/WebP 等图片文件。", "amber");
      return;
    }
    hydratingSnapshotRef.current = false;
    const nextUrl = URL.createObjectURL(file);
    revokeObjectUrl(sourceUrl);
    setSourceFile(file);
    setSourceUrl(nextUrl);
    setSourcePersistUrl("");
    setSourceName(file.name || "");
    setSourceSizeBytes(Number(file.size || 0));
    persistSignatureRef.current = "";
    resetResultState();
  };

  const handleDownload = async () => {
    if (!resultUrl) {
      noticeRef.current?.("当前还没有可下载的透明电子章。", "amber");
      return;
    }
    if (resultBlob) {
      downloadBlobFile(resultBlob, resultDownloadName || "seal_transparent.png");
      return;
    }
    try {
      const response = await fetch(resultUrl);
      const blob = await response.blob();
      downloadBlobFile(blob, resultDownloadName || "seal_transparent.png");
    } catch (error) {
      noticeRef.current?.(error?.message || "下载电子章失败。", "rose");
    }
  };

  const handleSelectResult = (index) => {
    const nextItem = resultItems[index];
    if (!nextItem) return;
    setSelectedResultIndex(index);
    applySelectedResultItem(nextItem);
  };

  const handleDownloadAll = async () => {
    if (resultItems.length <= 1) {
      handleDownload();
      return;
    }
    if (!archiveUrl) {
      noticeRef.current?.("当前没有可用的批量导出文件。", "amber");
      return;
    }
    try {
      const response = await fetch(archiveUrl);
      const blob = await response.blob();
      downloadBlobFile(blob, archiveDownloadName || "seals.zip");
    } catch (error) {
      noticeRef.current?.(error?.message || "批量下载失败。", "rose");
    }
  };

  const showResult = !!sourceUrl && !!resultUrl;
  const hasMultipleResults = resultItems.length > 1;
  const compactGrid = isMobileViewport ? "grid-cols-1" : "grid-cols-1 xl:grid-cols-[1.1fr_0.9fr]";
  const displayedSourceName = sourceFile?.name || sourceName || "原图";
  const displayedSourceSize = Number(sourceFile?.size || sourceSizeBytes || 0);

  return (
    <div className="flex-1 overflow-auto bg-[radial-gradient(circle_at_top,_rgba(255,75,113,0.08),_transparent_30%),linear-gradient(180deg,_#fff_0%,_#f8fafc_100%)] text-slate-900 dark:bg-[radial-gradient(circle_at_top,_rgba(244,63,94,0.12),_transparent_30%),linear-gradient(180deg,_#020617_0%,_#0f172a_100%)] dark:text-slate-100">
      <div className="mx-auto w-full max-w-[1380px] px-4 py-4 md:px-6 md:py-6 space-y-5">
        <div className="flex flex-col gap-4 rounded-[28px] border border-rose-100/70 bg-white/92 p-5 shadow-[0_20px_80px_rgba(15,23,42,0.06)] backdrop-blur md:p-6 dark:border-slate-800 dark:bg-slate-950/88 dark:shadow-[0_20px_80px_rgba(0,0,0,0.36)]">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-rose-100 bg-rose-50 px-3 py-1 text-xs font-medium text-rose-600 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200">
                <Sparkles size={14} />
                OCR 扩展工具
              </div>
              <h2 className="mt-3 text-2xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">印章提取工具</h2>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500 dark:text-slate-400">
                从扫描件或图片中提取印章区域，按颜色容差生成透明背景电子章。默认优先调用后端 PaddleOCR + OpenCV 接口；接口不可用时自动回退到浏览器本地预览。
              </p>
            </div>
            <button
              type="button"
              onClick={onBack}
              className="inline-flex items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-600 transition hover:border-slate-300 hover:text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-slate-600 dark:hover:text-slate-100"
            >
              <ArrowLeft size={16} />
              返回 OCR 识别
            </button>
          </div>

          {!sourceUrl ? (
            <div
              className="rounded-[30px] border-2 border-dashed border-slate-200 bg-slate-50/75 px-5 py-10 text-center transition hover:border-rose-300 hover:bg-white dark:border-slate-700 dark:bg-slate-900/70 dark:hover:border-rose-500/50 dark:hover:bg-slate-900"
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                event.preventDefault();
                acceptFile(event.dataTransfer?.files?.[0]);
              }}
            >
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-rose-50 text-rose-500 shadow-sm dark:bg-rose-500/15 dark:text-rose-200">
                <FileUp size={28} />
              </div>
              <div className="mt-5 text-2xl font-semibold text-slate-800 dark:text-slate-100">点击或拖拽印章图片到这里</div>
              <div className="mt-3 text-sm text-slate-500 dark:text-slate-400">建议上传扫描件或拍照图片，支持 JPG / PNG / WebP</div>
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="mt-6 inline-flex items-center gap-2 rounded-full bg-slate-900 px-5 py-3 text-sm font-medium text-white transition hover:bg-slate-800 dark:bg-rose-500 dark:text-white dark:hover:bg-rose-400"
              >
                <ImageIcon size={16} />
                选择图片
              </button>
            </div>
          ) : (
            <>
              <div className="rounded-[28px] border border-dashed border-slate-200 bg-slate-50/80 p-4 md:p-5 dark:border-slate-700 dark:bg-slate-900/60">
                <div className="flex flex-col gap-4">
                  <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
                    <div className="flex flex-wrap items-center gap-3">
                      <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 shadow-sm transition hover:border-slate-300 hover:text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200 dark:hover:border-slate-600 dark:hover:text-slate-50"
                      >
                        <RefreshCw size={15} />
                        点击替换图片
                      </button>
                      <button
                        type="button"
                        onClick={clearAll}
                        className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-600 transition hover:border-slate-300 hover:text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300 dark:hover:border-slate-600 dark:hover:text-slate-50"
                      >
                        <X size={15} />
                        清空
                      </button>
                      <div className="h-8 w-px bg-slate-200 dark:bg-slate-700" />
                      <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
                        <span>提取模式:</span>
                        <div className="inline-flex rounded-full border border-slate-200 bg-white p-1 dark:border-slate-700 dark:bg-slate-950">
                          <button
                            type="button"
                            onClick={() => updateSetting("extractMode", "smart")}
                            className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${settings.extractMode === "smart" ? "bg-rose-500 text-white shadow" : "text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-100"}`}
                          >
                            智能识别
                          </button>
                          <button
                            type="button"
                            onClick={() => updateSetting("extractMode", "red")}
                            className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${settings.extractMode === "red" ? "bg-slate-900 text-white shadow dark:bg-slate-100 dark:text-slate-950" : "text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-100"}`}
                          >
                            仅保留红色
                          </button>
                        </div>
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={resetSettings}
                      className="inline-flex items-center gap-2 self-start rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-500 transition hover:border-slate-300 hover:text-slate-800 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-400 dark:hover:border-slate-600 dark:hover:text-slate-100"
                    >
                      <RefreshCw size={14} />
                      恢复默认参数
                    </button>
                  </div>

                  <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
                    <label className="space-y-2">
                      <span className="text-sm font-medium text-slate-600 dark:text-slate-300">目标颜色</span>
                      <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-950">
                        <input
                          type="color"
                          value={settings.targetColor}
                          onChange={(event) => updateSetting("targetColor", event.target.value)}
                          className="h-10 w-10 cursor-pointer rounded-lg border border-slate-200 bg-transparent dark:border-slate-700"
                        />
                        <div className="min-w-0">
                          <div className="text-sm font-medium text-slate-800 dark:text-slate-100">{settings.targetColor.toUpperCase()}</div>
                          <div className="text-xs text-slate-400 dark:text-slate-500">输出颜色</div>
                        </div>
                      </div>
                    </label>

                    <label className="space-y-2">
                      <span className="text-sm font-medium text-slate-600 dark:text-slate-300">容差: {settings.tolerance}</span>
                      <div className="rounded-2xl border border-slate-200 bg-white px-3 py-3 dark:border-slate-700 dark:bg-slate-950">
                        <input
                          type="range"
                          min="5"
                          max="100"
                          value={settings.tolerance}
                          onChange={(event) => updateSetting("tolerance", Number(event.target.value))}
                          className="w-full accent-rose-500"
                        />
                      </div>
                    </label>

                    <label className="space-y-2">
                      <span className="text-sm font-medium text-slate-600 dark:text-slate-300">灰度过滤: {settings.grayThreshold.toFixed(2)}</span>
                      <div className="rounded-2xl border border-slate-200 bg-white px-3 py-3 dark:border-slate-700 dark:bg-slate-950">
                        <input
                          type="range"
                          min="0.01"
                          max="0.35"
                          step="0.01"
                          value={settings.grayThreshold}
                          onChange={(event) => updateSetting("grayThreshold", Number(event.target.value))}
                          className="w-full accent-rose-500"
                        />
                      </div>
                    </label>

                    <label className="space-y-2">
                      <span className="text-sm font-medium text-slate-600 dark:text-slate-300">智能填充: {settings.fillRadius}px</span>
                      <div className="rounded-2xl border border-slate-200 bg-white px-3 py-3 dark:border-slate-700 dark:bg-slate-950">
                        <input
                          type="range"
                          min="0"
                          max="20"
                          value={settings.fillRadius}
                          onChange={(event) => updateSetting("fillRadius", Number(event.target.value))}
                          className="w-full accent-rose-500"
                        />
                      </div>
                    </label>
                  </div>

                  <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_1.1fr_0.8fr]">
                    <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 dark:border-slate-700 dark:bg-slate-950">
                      <div className="text-sm font-medium text-slate-600 dark:text-slate-300">通道占比</div>
                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        {CHANNEL_OPTIONS.map((option) => (
                          <button
                            key={option.key}
                            type="button"
                            onClick={() => updateSetting("channelMode", option.key)}
                            className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${settings.channelMode === option.key ? "bg-rose-500 text-white shadow-sm" : "bg-slate-100 text-slate-500 hover:text-slate-800 dark:bg-slate-800 dark:text-slate-400 dark:hover:text-slate-100"}`}
                          >
                            {option.label}
                          </button>
                        ))}
                      </div>
                    </div>

                    <label className="space-y-2 rounded-2xl border border-slate-200 bg-white px-4 py-3 dark:border-slate-700 dark:bg-slate-950">
                      <span className="text-sm font-medium text-slate-600 dark:text-slate-300">通道强化: {settings.channelRatio}%</span>
                      <input
                        type="range"
                        min="0"
                        max="100"
                        value={settings.channelRatio}
                        onChange={(event) => updateSetting("channelRatio", Number(event.target.value))}
                        className="w-full accent-rose-500"
                      />
                    </label>

                    <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 dark:border-slate-700 dark:bg-slate-950">
                      <div className="text-sm font-medium text-slate-600 dark:text-slate-300">截取区域</div>
                      <div className="mt-3 inline-flex rounded-full border border-slate-200 bg-slate-50 p-1 dark:border-slate-700 dark:bg-slate-900">
                        <button
                          type="button"
                          onClick={() => updateSetting("cropMode", "focus")}
                          className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${settings.cropMode === "focus" ? "bg-slate-900 text-white shadow-sm dark:bg-slate-100 dark:text-slate-950" : "text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-100"}`}
                        >
                          开启
                        </button>
                        <button
                          type="button"
                          onClick={() => updateSetting("cropMode", "full")}
                          className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${settings.cropMode === "full" ? "bg-slate-900 text-white shadow-sm dark:bg-slate-100 dark:text-slate-950" : "text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-100"}`}
                        >
                          全图
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="text-xs leading-6 text-slate-400 dark:text-slate-500">
                支持拖拽新印章图片到图片区直接替换。默认优先调用后端 `PaddleOCR + OpenCV` 接口；若后端不可用，会自动回退到浏览器本地预览模式。
              </div>

              <div className={`grid gap-5 ${compactGrid}`}>
                <div className="rounded-[28px] border border-slate-100 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-950/72">
                  <div className="mb-4 flex items-center justify-between">
                    <span className="inline-flex rounded-xl bg-slate-500 px-3 py-1 text-xs font-medium text-white dark:bg-slate-700">原图</span>
                    <span className="text-sm text-slate-400 dark:text-slate-500">{formatKilobytes(displayedSourceSize)}</span>
                  </div>
                  <div
                    className="flex min-h-[320px] items-center justify-center overflow-hidden rounded-[24px] bg-slate-100/70 p-4 dark:bg-slate-900"
                    onDragOver={(event) => event.preventDefault()}
                    onDrop={(event) => {
                      event.preventDefault();
                      acceptFile(event.dataTransfer?.files?.[0]);
                    }}
                  >
                    <img src={sourceUrl} alt={displayedSourceName} className="max-h-[520px] w-full rounded-[18px] object-contain shadow-sm" />
                  </div>
                </div>

                <div className="rounded-[28px] border border-rose-200 bg-white p-4 shadow-[0_10px_40px_rgba(244,63,94,0.08)] dark:border-rose-500/30 dark:bg-slate-950/72 dark:shadow-[0_14px_46px_rgba(244,63,94,0.12)]">
                  <div className="mb-4 flex items-center justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <span className="inline-flex rounded-xl bg-rose-500 px-3 py-1 text-xs font-medium text-white">提取结果</span>
                      {resultItems.length ? (
                        <span className="text-xs font-medium text-slate-400 dark:text-slate-500">
                          {resultItems.length > 1 ? `检测到 ${resultItems.length} 个印章` : "检测到 1 个印章"}
                        </span>
                      ) : null}
                    </div>
                    <div className="flex items-center gap-2">
                      {isProcessing ? (
                        <span className="inline-flex items-center gap-2 rounded-full bg-rose-50 px-3 py-1 text-xs font-medium text-rose-500 dark:bg-rose-500/12 dark:text-rose-200">
                          <Loader2 size={14} className="animate-spin" />
                          正在处理
                        </span>
                      ) : null}
                      <button
                        type="button"
                        onClick={handleDownload}
                        disabled={!showResult}
                        className="inline-flex items-center gap-2 rounded-full bg-rose-500 px-4 py-2 text-sm font-medium text-white transition hover:bg-rose-600 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        <Download size={15} />
                        下载当前
                      </button>
                      {hasMultipleResults ? (
                        <button
                          type="button"
                          onClick={handleDownloadAll}
                          disabled={!showResult}
                          className="inline-flex items-center gap-2 rounded-full border border-rose-200 bg-white px-4 py-2 text-sm font-medium text-rose-500 transition hover:border-rose-300 hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-40 dark:border-rose-500/40 dark:bg-slate-900 dark:text-rose-200 dark:hover:border-rose-400 dark:hover:bg-rose-500/10"
                        >
                          <Download size={15} />
                          批量下载
                        </button>
                      ) : null}
                    </div>
                  </div>

                  <div className="relative flex min-h-[320px] items-center justify-center overflow-hidden rounded-[24px] bg-[linear-gradient(135deg,rgba(248,250,252,1),rgba(255,255,255,0.85)),linear-gradient(45deg,rgba(226,232,240,0.55)_25%,transparent_25%,transparent_75%,rgba(226,232,240,0.55)_75%,rgba(226,232,240,0.55)),linear-gradient(45deg,rgba(226,232,240,0.55)_25%,transparent_25%,transparent_75%,rgba(226,232,240,0.55)_75%,rgba(226,232,240,0.55))] bg-[length:auto,24px_24px,24px_24px] bg-[position:0_0,0_0,12px_12px] p-4 dark:bg-[linear-gradient(135deg,rgba(15,23,42,0.96),rgba(30,41,59,0.92)),linear-gradient(45deg,rgba(71,85,105,0.35)_25%,transparent_25%,transparent_75%,rgba(71,85,105,0.35)_75%,rgba(71,85,105,0.35)),linear-gradient(45deg,rgba(71,85,105,0.35)_25%,transparent_25%,transparent_75%,rgba(71,85,105,0.35)_75%,rgba(71,85,105,0.35))]">
                    {showResult ? (
                      <img src={resultUrl} alt="透明电子章" className="max-h-[520px] w-full object-contain" />
                    ) : (
                      <div className="text-sm text-slate-400 dark:text-slate-500">结果会显示在这里</div>
                    )}
                    {isProcessing && (
                      <div className="absolute inset-0 flex items-center justify-center bg-white/70 backdrop-blur-sm dark:bg-slate-950/72">
                        <div className="inline-flex items-center gap-2 rounded-full bg-slate-900 px-4 py-2 text-sm font-medium text-white dark:bg-slate-100 dark:text-slate-950">
                          <Loader2 size={15} className="animate-spin" />
                          提取中
                        </div>
                      </div>
                    )}
                  </div>

                  {hasMultipleResults ? (
                    <div className="mt-4 rounded-[22px] border border-slate-100 bg-slate-50/80 p-3 dark:border-slate-800 dark:bg-slate-900/80">
                      <div className="mb-3 text-sm font-medium text-slate-600 dark:text-slate-300">检测结果列表，点击切换预览</div>
                      <div className="grid gap-3 sm:grid-cols-2">
                        {resultItems.map((item, index) => {
                          const active = index === selectedResultIndex;
                          const bboxText = Array.isArray(item.bbox) && item.bbox.length >= 4
                            ? `${item.bbox[0]}, ${item.bbox[1]} · ${item.bbox[2]}, ${item.bbox[3]}`
                            : "--";
                          return (
                            <button
                              key={item.id}
                              type="button"
                              onClick={() => handleSelectResult(index)}
                              className={`rounded-[20px] border p-3 text-left transition ${
                                active
                                  ? "border-rose-300 bg-white shadow-sm dark:border-rose-400/50 dark:bg-slate-950"
                                  : "border-slate-200 bg-white/80 hover:border-slate-300 dark:border-slate-700 dark:bg-slate-950/70 dark:hover:border-slate-600"
                              }`}
                            >
                              <div className="flex items-start gap-3">
                                <div className="flex h-20 w-20 shrink-0 items-center justify-center overflow-hidden rounded-2xl bg-[linear-gradient(135deg,rgba(248,250,252,1),rgba(255,255,255,0.88)),linear-gradient(45deg,rgba(226,232,240,0.55)_25%,transparent_25%,transparent_75%,rgba(226,232,240,0.55)_75%,rgba(226,232,240,0.55)),linear-gradient(45deg,rgba(226,232,240,0.55)_25%,transparent_25%,transparent_75%,rgba(226,232,240,0.55)_75%,rgba(226,232,240,0.55))] bg-[length:auto,18px_18px,18px_18px] bg-[position:0_0,0_0,9px_9px] p-2 dark:bg-[linear-gradient(135deg,rgba(15,23,42,0.96),rgba(30,41,59,0.92)),linear-gradient(45deg,rgba(71,85,105,0.35)_25%,transparent_25%,transparent_75%,rgba(71,85,105,0.35)_75%,rgba(71,85,105,0.35)),linear-gradient(45deg,rgba(71,85,105,0.35)_25%,transparent_25%,transparent_75%,rgba(71,85,105,0.35)_75%,rgba(71,85,105,0.35))]">
                                  <img src={item.resultUrl} alt={item.label} className="max-h-full max-w-full object-contain" />
                                </div>
                                <div className="min-w-0 flex-1">
                                  <div className="flex items-center justify-between gap-2">
                                    <div className="truncate text-sm font-semibold text-slate-800 dark:text-slate-100">{item.label}</div>
                                    {active ? (
                                      <span className="rounded-full bg-rose-500 px-2 py-0.5 text-[10px] font-medium text-white">当前</span>
                                    ) : null}
                                  </div>
                                  <div className="mt-1 text-xs text-slate-400 dark:text-slate-500">
                                    第 {item.pageIndex + 1} 页 · {formatKilobytes(item.resultSizeBytes)}
                                  </div>
                                  <div className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                                    区域: {bboxText}
                                  </div>
                                </div>
                              </div>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  ) : null}

                  <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
                    <div>
                      <div className="text-[24px] font-semibold text-slate-900 dark:text-slate-100">{formatKilobytes(resultMeta?.result_size_bytes || resultBlob?.size)}</div>
                      <div className="text-sm text-emerald-500 dark:text-emerald-400">
                        透明背景 PNG，体积约为原图的 {formatRatio(resultMeta?.result_size_bytes || resultBlob?.size, displayedSourceSize)}
                      </div>
                    </div>
                    <div className="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-3 text-xs leading-6 text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
                      <div>当前检测到的前景像素: {resultMeta.pixelCount || 0}</div>
                      <div>当前模式: {resultMeta.mode === "server" ? "后端 API" : resultMeta.mode === "local" ? "浏览器本地预览" : resultMeta.mode === "history" ? "历史记录" : "--"}</div>
                      <div>定位来源: {resultMeta.detectionSource || resultMeta.detection_source || "--"}</div>
                      <div>定位器: {resultMeta.stamp_locator || "--"}</div>
                      <div>自动档位: {resultMeta.auto_profile || "--"}</div>
                      <div>细化方案: {resultMeta.refine_variant || "--"}</div>
                      <div>防过填充: {resultMeta.guard_mode || "--"}</div>
                      <div>渲染模式: {resultMeta.render_mode || "--"}</div>
                      <div>输出倍率: {resultMeta.render_scale ? `${resultMeta.render_scale}x` : "--"}</div>
                      <div>
                        裁剪策略: {
                          resultMeta.crop_strategy === "full_page_first"
                            ? "全图优先后截取"
                            : resultMeta.crop_strategy === "full_mask_then_paddle_crop"
                              ? "全图抠图后按印章框截取"
                              : resultMeta.crop_strategy || "--"
                        }
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        className="hidden"
        accept="image/png,image/jpeg,image/webp"
        onChange={(event) => {
          acceptFile(event.target.files?.[0]);
          event.target.value = "";
        }}
      />
    </div>
  );
};

export default SealExtractorWorkspace;
