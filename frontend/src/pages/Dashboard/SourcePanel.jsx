import React, { Suspense, lazy } from 'react';
import {
  Info,
  Globe,
  ExternalLink,
  FileText,
  Database,
  ScanText,
  BookOpen,
} from 'lucide-react';

const MarkdownRenderer = lazy(() => import('./MarkdownRenderer'));

const normalizeLink = (link) => {
  if (!link || typeof link !== 'string') return null;
  const trimmed = link.trim();
  if (!trimmed) return null;
  if (/^https?:\/\//i.test(trimmed) || trimmed.startsWith('/') || trimmed.startsWith('#')) return trimmed;
  if (trimmed.startsWith('//')) return `https:${trimmed}`;
  if (/^www\./i.test(trimmed)) return `https://${trimmed}`;
  return trimmed;
};

const isProbablyUrl = (value) => {
  if (typeof value !== 'string') return false;
  const trimmed = value.trim();
  return /^(https?:\/\/|\/\/|www\.)/i.test(trimmed);
};

const SourcePanel = ({ sources }) => {
  if (!sources || !Array.isArray(sources) || sources.length === 0) return null;

  return (
    <div className="mt-3 pt-2.5 border-t border-gray-100 dark:border-gray-800 w-full animate-in fade-in duration-500">
      <div className="flex flex-col gap-2">
        <span className="text-[10px] font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider flex items-center gap-1">
          <Info size={10} />
          来源</span>
        <div className="flex flex-wrap gap-2">
          {sources.map((src, i) => {
            const sourceObj = (typeof src === 'object' && src !== null) ? src : null;
            const linkValue = (typeof src === 'object' && src !== null)
              ? (src.link || src.url || src.href || src.uri)
              : (isProbablyUrl(src) ? src : null);
            const href = normalizeLink(linkValue);
            const label = (typeof src === 'object' && src !== null)
              ? (src.title || src.name || src.domain || src.link || src.url || src.href || src.uri || JSON.stringify(src))
              : (typeof src === 'string' ? src : JSON.stringify(src));
            const snippet = (typeof src === 'object' && src !== null)
              ? (src.snippet || src.excerpt || src.summary || '')
              : '';
            const sourceType = String(sourceObj?.type || '').toLowerCase();
            const sqlText = String(sourceObj?.sql || sourceObj?.query || sourceObj?.statement || '').trim();
            const sqlMarkdown = String(sourceObj?.markdown || '').trim() || (sqlText ? `\`\`\`sql\n${sqlText}\n\`\`\`` : '');
            const lowerSrc = label.toLowerCase();
            const isSqlSource = sourceType === 'sql' || Boolean(sqlMarkdown) || lowerSrc.includes('sql');

            if (isSqlSource) {
              const content = sqlMarkdown || snippet || label;
              return (
                <div
                  key={i}
                  className="w-full rounded-lg border border-blue-100 dark:border-blue-800 bg-blue-50/60 dark:bg-blue-900/20 overflow-hidden"
                >
                  <div className="px-3 py-2 text-xs font-semibold text-blue-700 dark:text-blue-300 flex items-center gap-1.5 border-b border-blue-100 dark:border-blue-800">
                    <Database size={12} />
                    {label || 'SQL 查询语句'}
                  </div>
                  <div className="px-3 py-2 text-xs text-gray-700 dark:text-gray-200 bg-white/80 dark:bg-gray-900/40">
                    <Suspense fallback={<pre className="whitespace-pre-wrap break-words text-[11px] leading-relaxed">{content}</pre>}>
                      <MarkdownRenderer content={content} />
                    </Suspense>
                  </div>
                </div>
              );
            }

            if (href) {
              return (
                <a
                  key={i}
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border text-xs font-medium bg-sky-50 dark:bg-sky-900/20 text-sky-700 dark:text-sky-300 border-sky-100 dark:border-sky-800 transition-all hover:opacity-80 hover:underline decoration-sky-300 underline-offset-2"
                  title={label || href}
                >
                  <Globe size={12} className="text-sky-500 flex-shrink-0" />
                  <span className="truncate max-w-[200px]">
                    {label || "Web Source"}
                  </span>
                  <ExternalLink size={10} className="text-sky-400 opacity-70" />
                </a>
              );
            }

            let icon = <FileText size={12} className="text-gray-500" />;
            let bgClass = "bg-gray-50 dark:bg-gray-800 text-gray-600 dark:text-gray-300";
            let borderClass = "border-gray-200 dark:border-gray-700";

            if (lowerSrc.includes('table') || lowerSrc.includes('database')) {
              icon = <Database size={12} className="text-blue-500" />;
              bgClass = "bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300";
              borderClass = "border-blue-100 dark:border-blue-800";
            } else if (lowerSrc.includes('扫描') || lowerSrc.includes('ocr')) {
              icon = <ScanText size={12} className="text-purple-500" />;
              bgClass = "bg-purple-50 dark:bg-purple-900/20 text-purple-700 dark:text-purple-300";
              borderClass = "border-purple-100 dark:border-purple-800";
            } else if (lowerSrc.includes('书') && lowerSrc.includes('页')) {
              icon = <BookOpen size={12} className="text-orange-500" />;
              bgClass = "bg-orange-50 dark:bg-orange-900/20 text-orange-700 dark:text-orange-300";
              borderClass = "border-orange-100 dark:border-orange-800";
            } else if (lowerSrc.includes('http') || lowerSrc.includes('.com') || lowerSrc.includes('web')) {
              icon = <Globe size={12} className="text-sky-500" />;
              bgClass = "bg-sky-50 dark:bg-sky-900/20 text-sky-700 dark:text-sky-300";
              borderClass = "border-sky-100 dark:border-sky-800";
            }

            return (
              <div key={i} className={`inline-flex items-start gap-1.5 px-2.5 py-1.5 rounded-md border text-xs font-medium ${bgClass} ${borderClass} transition-colors hover:opacity-80`}>
                {icon}
                <div className="flex flex-col min-w-0">
                  <span className="truncate max-w-[220px]" title={label}>{label}</span>
                  {snippet && (
                    <span className="text-[10px] text-gray-500 dark:text-gray-400 truncate max-w-[220px]" title={snippet}>
                      {snippet}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default React.memo(SourcePanel);
