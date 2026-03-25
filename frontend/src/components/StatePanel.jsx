import React from 'react';
import {
  AlertTriangle,
  ArrowLeft,
  Lock,
  RefreshCw,
  SearchX,
  ShieldOff,
} from 'lucide-react';

const TONE_MAP = {
  slate: {
    shell: 'border-slate-200 bg-white text-slate-900 dark:border-slate-800 dark:bg-slate-900 dark:text-white',
    icon: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-200',
    secondary: 'border-slate-200 text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800',
    primary: 'bg-slate-900 text-white hover:bg-slate-700 dark:bg-blue-600 dark:hover:bg-blue-500',
  },
  rose: {
    shell: 'border-rose-200 bg-white text-slate-900 dark:border-rose-900/60 dark:bg-slate-900 dark:text-white',
    icon: 'bg-rose-100 text-rose-600 dark:bg-rose-950/40 dark:text-rose-300',
    secondary: 'border-rose-200 text-rose-700 hover:bg-rose-50 dark:border-rose-900/60 dark:text-rose-200 dark:hover:bg-rose-950/30',
    primary: 'bg-rose-600 text-white hover:bg-rose-500 dark:bg-rose-600 dark:hover:bg-rose-500',
  },
  amber: {
    shell: 'border-amber-200 bg-white text-slate-900 dark:border-amber-900/60 dark:bg-slate-900 dark:text-white',
    icon: 'bg-amber-100 text-amber-600 dark:bg-amber-950/40 dark:text-amber-300',
    secondary: 'border-amber-200 text-amber-700 hover:bg-amber-50 dark:border-amber-900/60 dark:text-amber-200 dark:hover:bg-amber-950/30',
    primary: 'bg-amber-500 text-slate-950 hover:bg-amber-400 dark:bg-amber-500 dark:hover:bg-amber-400',
  },
};

const ICON_MAP = {
  empty: SearchX,
  error: AlertTriangle,
  permission: ShieldOff,
  auth: Lock,
};

function StateActionButton({ action, tone, compact = false }) {
  const Icon = action?.icon || (action?.href ? ArrowLeft : RefreshCw);
  const toneStyle = TONE_MAP[tone] || TONE_MAP.slate;
  const baseClass = action?.primary ? toneStyle.primary : `border ${toneStyle.secondary}`;
  const sizeClass = compact ? 'px-3 py-2 text-xs' : 'px-4 py-2.5 text-sm';

  if (action?.href) {
    return (
      <a
        href={action.href}
        className={`inline-flex items-center justify-center gap-2 rounded-xl font-medium transition ${baseClass} ${sizeClass}`}
      >
        <Icon size={compact ? 14 : 16} />
        {action.label}
      </a>
    );
  }

  return (
    <button
      type="button"
      onClick={action?.onClick}
      className={`inline-flex items-center justify-center gap-2 rounded-xl font-medium transition ${baseClass} ${sizeClass}`}
    >
      <Icon size={compact ? 14 : 16} />
      {action?.label}
    </button>
  );
}

export default function StatePanel({
  title,
  description,
  tone = 'slate',
  icon = 'empty',
  Icon = null,
  actions = [],
  fullScreen = false,
  compact = false,
  className = '',
  children = null,
}) {
  const toneStyle = TONE_MAP[tone] || TONE_MAP.slate;
  const ResolvedIcon = Icon || ICON_MAP[icon] || SearchX;
  const shellClass = fullScreen
    ? 'min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950 px-4'
    : '';

  return (
    <div className={`${shellClass} ${className}`.trim()}>
      <div className={`w-full ${fullScreen ? 'max-w-lg' : ''} rounded-3xl border px-6 py-8 text-center shadow-sm ${toneStyle.shell}`}>
        <div className={`mx-auto flex h-14 w-14 items-center justify-center rounded-2xl ${toneStyle.icon}`}>
          <ResolvedIcon size={compact ? 20 : 24} />
        </div>
        <div className={`mt-4 font-semibold ${compact ? 'text-base' : 'text-xl'}`}>{title}</div>
        {description ? (
          <p className={`mx-auto mt-3 max-w-xl leading-6 text-slate-500 dark:text-slate-400 ${compact ? 'text-xs' : 'text-sm'}`}>
            {description}
          </p>
        ) : null}
        {children ? <div className="mt-4">{children}</div> : null}
        {actions.length > 0 ? (
          <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
            {actions.map((action, index) => (
              <StateActionButton
                key={`${action?.label || 'action'}-${index}`}
                action={action}
                tone={tone}
                compact={compact}
              />
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
