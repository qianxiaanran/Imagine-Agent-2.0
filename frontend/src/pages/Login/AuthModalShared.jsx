import React, { memo, useEffect, useState } from 'react';
import { X } from 'lucide-react';
import AnimatedLoginCharacters from './AnimatedLoginCharacters';

export const fieldClassName = 'w-full rounded-2xl border border-slate-200/80 bg-white/90 px-4 py-3 text-[15px] text-slate-900 outline-none transition-all placeholder:text-slate-400 focus:border-slate-400 focus:ring-4 focus:ring-slate-200/50 dark:border-slate-700 dark:bg-slate-900/90 dark:text-white dark:placeholder:text-slate-500 dark:focus:border-slate-500 dark:focus:ring-slate-800/70';
export const secondaryButtonClassName = 'w-full rounded-full border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-700 transition-all hover:-translate-y-0.5 hover:border-slate-400 hover:text-slate-900 hover:shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:border-slate-500 dark:hover:text-white';
export const smallActionClassName = 'inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors';

export const Field = ({
  type = 'text',
  value,
  onChange,
  placeholder,
  disabled = false,
  trailing = null,
  onFocus,
  onBlur,
  className = '',
  wrapperClassName = '',
}) => (
  <div className={`relative ${wrapperClassName}`.trim()}>
    <input
      type={type}
      value={value}
      disabled={disabled}
      placeholder={placeholder}
      onChange={onChange}
      onFocus={onFocus}
      onBlur={onBlur}
      className={`${fieldClassName} ${trailing ? 'pr-12' : ''} ${disabled ? 'cursor-not-allowed text-slate-500 dark:text-slate-400' : ''} ${className}`.trim()}
    />
    {trailing && <div className="absolute right-4 top-1/2 -translate-y-1/2">{trailing}</div>}
  </div>
);

export const SectionHeader = ({ eyebrow, title, description, backAction = null }) => (
  <div className="mb-9">
    {backAction}
    <div className="text-[11px] font-semibold uppercase tracking-[0.26em] text-slate-400 dark:text-slate-500">
      {eyebrow}
    </div>
    <h1 className="mt-3 text-3xl font-black tracking-tight text-slate-900 dark:text-white">{title}</h1>
    <p className="mt-3 text-sm leading-6 text-slate-500 dark:text-slate-400">{description}</p>
  </div>
);

export const InfoDialog = ({ open, onClose, title, children }) => {
  if (!open) return null;

  return (
    <div className="absolute inset-0 z-20 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        style={{ willChange: 'opacity', backfaceVisibility: 'hidden' }}
        onClick={onClose}
      ></div>
      <div className="relative w-full max-w-sm rounded-[28px] border border-slate-200 bg-white p-6 shadow-2xl dark:border-slate-700 dark:bg-slate-900">
        <div className="mb-3 flex items-start justify-between gap-3">
          <h3 className="text-base font-semibold text-slate-900 dark:text-white">{title}</h3>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 transition-colors hover:text-slate-700 dark:hover:text-slate-200"
            aria-label="关闭"
          >
            ×
          </button>
        </div>
        <div className="text-sm leading-relaxed text-slate-700 dark:text-slate-300">{children}</div>
        <div className="mt-5 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded-full bg-slate-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-slate-800 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-200"
          >
            我知道了
          </button>
        </div>
      </div>
    </div>
  );
};

const useReducedMotionPreference = () => {
  const [reducedMotion, setReducedMotion] = useState(() =>
    typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
      : false
  );

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return undefined;
    }

    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    const updateReducedMotion = () => setReducedMotion(mediaQuery.matches);

    updateReducedMotion();
    mediaQuery.addEventListener?.('change', updateReducedMotion);

    return () => {
      mediaQuery.removeEventListener?.('change', updateReducedMotion);
    };
  }, []);

  return reducedMotion;
};

const useMinWidthMatch = (minWidth) => {
  const query = `(min-width: ${minWidth}px)`;
  const [matches, setMatches] = useState(() =>
    typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia(query).matches
      : false
  );

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return undefined;
    }

    const mediaQuery = window.matchMedia(query);
    const updateMatch = () => setMatches(mediaQuery.matches);

    updateMatch();
    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', updateMatch);
    } else if (typeof mediaQuery.addListener === 'function') {
      mediaQuery.addListener(updateMatch);
    }

    return () => {
      if (typeof mediaQuery.removeEventListener === 'function') {
        mediaQuery.removeEventListener('change', updateMatch);
      } else if (typeof mediaQuery.removeListener === 'function') {
        mediaQuery.removeListener(updateMatch);
      }
    };
  }, [query]);

  return matches;
};

const AuthVisualPanel = memo(function AuthVisualPanel({
  isTyping = false,
  showPassword = false,
  passwordLength = 0,
  reducedMotion = false,
}) {
  return (
  <div className="relative hidden overflow-hidden bg-gradient-to-br from-slate-400 via-slate-500 to-slate-600 dark:from-slate-200 dark:via-white dark:to-slate-200 lg:flex">
    <div className="relative z-10 flex flex-1 items-end justify-center px-6 py-8">
      <AnimatedLoginCharacters
        isTyping={isTyping}
        showPassword={showPassword}
        passwordLength={passwordLength}
        reducedMotion={reducedMotion}
      />
    </div>
    <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.06)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.06)_1px,transparent_1px)] bg-[size:22px_22px] opacity-70 dark:opacity-30" />
    <div className="absolute right-12 top-20 h-56 w-56 rounded-full bg-white/15 blur-3xl dark:bg-white/35" />
    <div className="absolute bottom-10 left-10 h-72 w-72 rounded-full bg-white/12 blur-3xl dark:bg-slate-300/30" />
  </div>
  );
});

export const AuthModalShell = ({
  modalRef,
  onClose,
  closeLabel,
  isTyping = false,
  showPassword = false,
  passwordLength = 0,
  children,
}) => {
  const reducedMotion = useReducedMotionPreference();
  const isLargeScreen = useMinWidthMatch(1024);

  return (
    <div className={`fixed inset-0 z-[100] flex items-center justify-center p-3 md:p-6 ${reducedMotion ? '' : 'animate-in fade-in duration-200'}`}>
      <div
        className="absolute inset-0 bg-black/55 backdrop-blur-md"
        style={{ willChange: 'opacity', backfaceVisibility: 'hidden', transform: 'translateZ(0)' }}
      />
      <div
        ref={modalRef}
        className={`relative grid max-h-[92vh] w-full max-w-[1120px] overflow-hidden rounded-[32px] border border-white/50 bg-white shadow-[0_30px_120px_rgba(15,23,42,0.24)] dark:border-slate-800 dark:bg-slate-950 lg:grid-cols-[1.04fr_0.96fr] ${reducedMotion ? '' : 'animate-in zoom-in-95 duration-200'}`}
        style={{ contain: 'layout paint style', willChange: 'transform, opacity', transform: 'translateZ(0)' }}
      >
        {isLargeScreen && (
          <AuthVisualPanel
            isTyping={isTyping}
            showPassword={showPassword}
            passwordLength={passwordLength}
            reducedMotion={reducedMotion}
          />
        )}

        <div className="relative flex min-h-0 flex-col bg-white/95 dark:bg-slate-950/95">
          <button
            type="button"
            onClick={onClose}
            className="absolute right-5 top-5 z-10 inline-flex h-10 w-10 items-center justify-center rounded-full border border-slate-200 bg-white/85 text-slate-500 hover:text-slate-900 dark:border-slate-800 dark:bg-slate-900/80 dark:text-slate-400 dark:hover:text-white"
            aria-label={closeLabel}
          >
            <X size={18} />
          </button>

          <div className="flex-1 overflow-y-auto px-6 py-8 sm:px-10 sm:py-10">
            <div className="mx-auto w-full max-w-[430px]">
              {children}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
