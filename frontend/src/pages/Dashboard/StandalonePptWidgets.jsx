import React, { useEffect, useRef, useState } from 'react';
import { Check, ChevronDown, Layout } from 'lucide-react';

export const StandalonePptSelect = ({
  label,
  value,
  options,
  onChange,
  disabled = false,
  className = '',
}) => {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const handlePointerDown = (event) => {
      if (rootRef.current && !rootRef.current.contains(event.target)) {
        setOpen(false);
      }
    };
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('touchstart', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('touchstart', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [open]);

  const normalizedOptions = Array.isArray(options) ? options : [];
  const selectedOption = normalizedOptions.find((item) => String(item?.value) === String(value)) || normalizedOptions[0];
  const selectedLabel = String(selectedOption?.label || value || '').trim();

  return (
    <div ref={rootRef} className={`relative ${className}`}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((previousOpen) => !previousOpen)}
        className="inline-flex min-w-[112px] items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-left text-sm text-gray-700 shadow-sm transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900 dark:text-gray-100 dark:hover:bg-slate-800"
      >
        <span className="shrink-0 text-gray-500 dark:text-gray-300">{label}</span>
        <span className="max-w-[140px] flex-1 truncate font-medium text-gray-900 dark:text-white">{selectedLabel}</span>
        <ChevronDown size={15} className={`shrink-0 text-gray-400 transition-transform dark:text-gray-500 ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && normalizedOptions.length > 0 && (
        <div className="absolute left-0 top-full z-30 mt-2 min-w-full overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-[#081224]">
          <div className="max-h-72 overflow-y-auto p-1.5">
            {normalizedOptions.map((item) => {
              const itemValue = item?.value;
              const active = String(itemValue) === String(selectedOption?.value);
              return (
                <button
                  key={String(itemValue)}
                  type="button"
                  onClick={() => {
                    onChange?.(itemValue);
                    setOpen(false);
                  }}
                  className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition ${
                    active
                      ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/12 dark:text-emerald-300'
                      : 'text-gray-700 hover:bg-gray-50 dark:text-gray-200 dark:hover:bg-slate-800/90'
                  }`}
                >
                  <span className="flex-1 truncate">{item.label}</span>
                  {active && <Check size={14} className="shrink-0" />}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};

export const StandaloneTemplatePreviewCard = ({
  template,
  selected = false,
  onSelect,
  resolvePreviewMeta,
  resolveTemplateId,
  resolveTemplateLabel,
}) => {
  const previewMeta = resolvePreviewMeta(template);
  const templateId = resolveTemplateId(template?.template_id || template?.id || '');
  const title = resolveTemplateLabel(template);
  const description = String(previewMeta.summary || template?.description || '').trim();
  const thumbnailUrl = String(template?.thumbnail_url || '').trim();
  const tags = Array.isArray(previewMeta.tags) ? previewMeta.tags : [];

  return (
    <button
      type="button"
      onClick={() => onSelect?.(templateId)}
      className={`group w-full overflow-hidden rounded-2xl border text-left transition ${
        selected
          ? 'border-emerald-400 bg-emerald-50/80 shadow-[0_18px_60px_rgba(16,185,129,0.18)] dark:border-emerald-400/70 dark:bg-emerald-500/10'
          : 'border-gray-200 bg-white shadow-sm hover:-translate-y-0.5 hover:border-emerald-200 hover:shadow-xl dark:border-slate-700 dark:bg-slate-900/90 dark:hover:border-emerald-500/40'
      }`}
    >
      <div className={`relative h-44 overflow-hidden bg-gradient-to-br ${previewMeta.gradient}`}>
        <div className={`absolute inset-0 ${previewMeta.shell} opacity-90`} />
        {thumbnailUrl ? (
          <div
            className="absolute inset-0 bg-cover bg-center opacity-95"
            style={{ backgroundImage: `url(${thumbnailUrl})` }}
          />
        ) : (
          <div className="absolute inset-0 p-4">
            <div className="grid h-full grid-cols-[1.15fr_0.85fr] gap-3">
              <div className={`rounded-2xl ${previewMeta.slideTone} p-3 shadow-lg`}>
                <div className={`h-2.5 w-20 rounded-full ${previewMeta.accentTone}`} />
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <div className={`h-14 rounded-xl ${previewMeta.mutedTone}`} />
                  <div className={`h-14 rounded-xl ${previewMeta.mutedTone}`} />
                </div>
                <div className="mt-3 space-y-2">
                  <div className={`h-2 rounded-full ${previewMeta.linesTone}`} />
                  <div className={`h-2 w-4/5 rounded-full ${previewMeta.linesTone}`} />
                </div>
              </div>
              <div className="flex flex-col gap-3">
                <div className={`flex-1 rounded-2xl ${previewMeta.slideTone} p-3 shadow-lg`}>
                  <div className={`h-2.5 w-14 rounded-full ${previewMeta.accentTone}`} />
                  <div className="mt-3 space-y-2">
                    <div className={`h-2 rounded-full ${previewMeta.linesTone}`} />
                    <div className={`h-2 w-3/4 rounded-full ${previewMeta.linesTone}`} />
                    <div className={`h-2 w-2/3 rounded-full ${previewMeta.linesTone}`} />
                  </div>
                </div>
                <div className={`h-16 rounded-2xl ${previewMeta.slideTone} p-3 shadow-lg`}>
                  <div className="flex h-full items-end gap-1.5">
                    <div className={`w-3 rounded-md ${previewMeta.linesTone}`} style={{ height: '38%' }} />
                    <div className={`w-3 rounded-md ${previewMeta.accentTone}`} style={{ height: '78%' }} />
                    <div className={`w-3 rounded-md ${previewMeta.linesTone}`} style={{ height: '55%' }} />
                    <div className={`w-3 rounded-md ${previewMeta.linesTone}`} style={{ height: '68%' }} />
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
        <div className="absolute left-4 top-4 inline-flex items-center gap-1.5 rounded-full bg-white/14 px-2.5 py-1 text-[11px] font-medium text-white backdrop-blur">
          <Layout size={12} />
          {templateId || 'template'}
        </div>
        {selected && (
          <div className="absolute right-4 top-4 inline-flex h-8 w-8 items-center justify-center rounded-full bg-emerald-500 text-white shadow-lg">
            <Check size={16} />
          </div>
        )}
      </div>
      <div className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-base font-semibold text-gray-900 dark:text-white">{title}</div>
            <div className="mt-1 text-sm text-gray-500 dark:text-gray-400">{description || '适合当前 PPT 生成场景。'}</div>
          </div>
          <div className={`shrink-0 rounded-full px-2 py-1 text-[11px] font-medium ${
            selected
              ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-200'
              : 'bg-gray-100 text-gray-600 dark:bg-slate-800 dark:text-gray-300'
          }`}>
            {String(template?.source || 'builtin').trim() || 'builtin'}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {tags.map((tag) => (
            <span
              key={`${templateId}-${tag}`}
              className="rounded-full bg-gray-100 px-2.5 py-1 text-[11px] text-gray-600 dark:bg-slate-800 dark:text-gray-300"
            >
              {tag}
            </span>
          ))}
        </div>
      </div>
    </button>
  );
};
