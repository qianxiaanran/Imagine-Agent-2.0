import React from 'react';
import { ArrowRight } from 'lucide-react';

const AuthHoverButton = React.forwardRef(function AuthHoverButton(
  { text = 'Continue', icon, className = '', disabled = false, animated = true, ...props },
  ref
) {
  const baseClassName = [
    animated
      ? 'group relative w-full overflow-hidden rounded-full border px-6 py-3 text-center text-sm font-semibold transition-all duration-300'
      : 'relative w-full overflow-hidden rounded-full border px-6 py-3 text-center text-sm font-semibold',
    disabled
      ? 'cursor-not-allowed border-slate-300 bg-slate-300 text-white dark:border-slate-700 dark:bg-slate-700 dark:text-slate-400'
      : animated
        ? 'border-slate-900 bg-slate-900 text-white hover:-translate-y-0.5 hover:shadow-[0_18px_50px_rgba(15,23,42,0.2)] dark:border-white dark:bg-white dark:text-slate-900'
        : 'border-slate-900 bg-slate-900 text-white dark:border-white dark:bg-white dark:text-slate-900',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <button ref={ref} disabled={disabled} className={baseClassName} {...props}>
      <span
        className={`inline-flex items-center justify-center gap-2 ${
          !disabled && animated ? 'transition-all duration-300 group-hover:translate-y-10 group-hover:opacity-0' : ''
        }`}
      >
        {text}
        {!animated && icon}
      </span>
      {!disabled && animated && (
        <span className="absolute inset-0 z-10 flex items-center justify-center gap-2 rounded-full bg-gradient-to-r from-slate-900 via-slate-800 to-emerald-500 text-white opacity-0 transition-all duration-300 group-hover:opacity-100 dark:from-white dark:via-slate-100 dark:to-emerald-400 dark:text-slate-900">
          <span>{text}</span>
          {icon || <ArrowRight size={16} />}
        </span>
      )}
    </button>
  );
});

export default AuthHoverButton;
