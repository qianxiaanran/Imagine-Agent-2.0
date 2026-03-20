import React, { Suspense, useEffect, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';

const MarkdownCodeBlock = React.lazy(() => import('./MarkdownCodeBlock'));

const mermaidCache = {};
let mermaidModulePromise;
let mermaidWorkerInstance;
let mermaidWorkerPromise;
let mermaidWorkerRequestId = 0;
let mermaidWorkerEnabled = typeof Worker !== 'undefined';
const mermaidWorkerJobs = new Map();

const WORKER_ENV_ERROR_PATTERNS = [
  /document is not defined/i,
  /window is not defined/i,
  /dompurify/i,
  /createelement/i,
  /appendchild/i,
  /html.*element/i,
];

const getMermaidTheme = () => (
  document.documentElement.classList.contains('dark') ? 'dark' : 'default'
);

const getMermaidCacheKey = (chart, theme) => `${theme}::${chart}`;

const escapeHtml = (value) => String(value || '')
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  .replace(/'/g, '&#39;');

const loadMermaid = async () => {
  if (!mermaidModulePromise) {
    mermaidModulePromise = import('mermaid').then((module) => module.default || module);
  }
  return mermaidModulePromise;
};

const isWorkerEnvironmentError = (error) => {
  const message = error instanceof Error ? error.message : String(error || '');
  return WORKER_ENV_ERROR_PATTERNS.some((pattern) => pattern.test(message));
};

const destroyMermaidWorker = ({ disable = false, error } = {}) => {
  if (disable) {
    mermaidWorkerEnabled = false;
  }

  if (mermaidWorkerInstance) {
    mermaidWorkerInstance.onmessage = null;
    mermaidWorkerInstance.onerror = null;
    mermaidWorkerInstance.terminate();
    mermaidWorkerInstance = null;
  }
  mermaidWorkerPromise = null;

  if (error) {
    mermaidWorkerJobs.forEach(({ reject }) => reject(error));
    mermaidWorkerJobs.clear();
  }
};

const loadMermaidWorker = async () => {
  if (!mermaidWorkerEnabled || typeof Worker === 'undefined') {
    throw new Error('Mermaid worker unavailable');
  }

  if (!mermaidWorkerPromise) {
    mermaidWorkerPromise = Promise.resolve().then(() => {
      const worker = new Worker(new URL('./mermaid.worker.js', import.meta.url), { type: 'module' });
      worker.onmessage = (event) => {
        const { requestId, svg: renderedSvg, error } = event.data || {};
        const job = mermaidWorkerJobs.get(requestId);
        if (!job) {
          return;
        }
        mermaidWorkerJobs.delete(requestId);
        if (error) {
          job.reject(new Error(error));
          return;
        }
        job.resolve(renderedSvg);
      };
      worker.onerror = (event) => {
        const workerError = new Error(event?.message || 'Mermaid worker crashed');
        destroyMermaidWorker({ disable: true, error: workerError });
      };
      mermaidWorkerInstance = worker;
      return worker;
    });
  }

  return mermaidWorkerPromise;
};

const renderMermaidInWorker = async (chart, theme) => {
  const worker = await loadMermaidWorker();
  return new Promise((resolve, reject) => {
    const requestId = `mermaid-worker-${++mermaidWorkerRequestId}`;
    mermaidWorkerJobs.set(requestId, { resolve, reject });
    worker.postMessage({ requestId, chart, theme });
  });
};

const renderMermaidOnMainThread = async (chart, theme) => {
  const mermaid = await loadMermaid();
  mermaid.initialize({
    startOnLoad: false,
    theme,
    securityLevel: 'loose',
  });
  const id = `mermaid-${Math.random().toString(36).slice(2, 11)}`;
  const { svg } = await mermaid.render(id, chart);
  return svg;
};

const Mermaid = ({ chart }) => {
  const [theme, setTheme] = useState(getMermaidTheme);
  const cacheKey = useMemo(() => getMermaidCacheKey(chart, theme), [chart, theme]);
  const [svg, setSvg] = useState(() => mermaidCache[cacheKey] || '');

  useEffect(() => {
    if (typeof MutationObserver === 'undefined') {
      return undefined;
    }

    const root = document.documentElement;
    const syncTheme = () => setTheme(getMermaidTheme());
    const observer = new MutationObserver(syncTheme);

    observer.observe(root, { attributes: true, attributeFilter: ['class'] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (mermaidCache[cacheKey]) {
      setSvg(mermaidCache[cacheKey]);
      return undefined;
    }

    setSvg('');
    let cancelled = false;

    const renderChart = async () => {
      try {
        let renderedSvg = '';
        try {
          renderedSvg = await renderMermaidInWorker(chart, theme);
        } catch (workerError) {
          if (isWorkerEnvironmentError(workerError)) {
            destroyMermaidWorker({ disable: true, error: workerError });
          }
          renderedSvg = await renderMermaidOnMainThread(chart, theme);
        }
        if (cancelled) return;
        mermaidCache[cacheKey] = renderedSvg;
        setSvg(renderedSvg);
      } catch (error) {
        if (cancelled) return;
        const message = error instanceof Error ? error.message : 'Unknown mermaid render error';
        setSvg(`<div class="rounded border border-red-200 bg-red-50 p-2 text-xs text-red-500">Mermaid Render Error: ${escapeHtml(message)}</div>`);
      }
    };

    if (chart) {
      void renderChart();
    }

    return () => {
      cancelled = true;
    };
  }, [cacheKey, chart, theme]);

  return (
    <div
      className="mermaid-wrapper my-4 flex min-h-[60px] justify-center overflow-x-auto rounded-lg border border-gray-100 bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
};

const MarkdownRendererRich = (props) => {
  const content = props.content;

  useEffect(() => {
    if (!document.getElementById('katex-css')) {
      const link = document.createElement('link');
      link.id = 'katex-css';
      link.rel = 'stylesheet';
      link.href = 'https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css';
      link.integrity = 'sha384-n8MVd4RsNIU0tAv4ct0nTaAbDJwPJzDEaqSD1odI+WdtXRGWt2kTvGFasHpSy3SV';
      link.crossOrigin = 'anonymous';
      document.head.appendChild(link);
    }
  }, []);

  const remarkPlugins = useMemo(() => [remarkGfm, remarkMath], []);
  const rehypePlugins = useMemo(() => [rehypeKatex], []);

  const markdownComponents = useMemo(() => ({
    code({ inline, className, children, ...rest }) {
      const match = /language-(\w+)/.exec(className || '');
      const codeContent = String(children).replace(/\n$/, '');
      const isMermaid = match && match[1] === 'mermaid';

      if (!inline && isMermaid) {
        return <Mermaid key={codeContent} chart={codeContent} />;
      }

      if (!inline && match) {
        return (
          <Suspense
            fallback={
              <pre className="my-3 overflow-x-auto rounded-md border border-gray-200 bg-gray-950 px-4 py-3 text-sm text-gray-100 dark:border-gray-700">
                <code className={className}>{codeContent}</code>
              </pre>
            }
          >
            <MarkdownCodeBlock codeContent={codeContent} language={match[1]} syntaxProps={rest} />
          </Suspense>
        );
      }

      return (
        <code
          className={`${className || ''} rounded bg-gray-100 px-1.5 py-0.5 font-mono text-[0.9em] text-pink-600 dark:bg-gray-700/50 dark:text-pink-400`}
          {...rest}
        >
          {children}
        </code>
      );
    },
    table({ children }) {
      return (
        <div className="my-4 overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">{children}</table>
        </div>
      );
    },
    thead({ children }) {
      return <thead className="bg-gray-50 dark:bg-gray-800">{children}</thead>;
    },
    th({ children }) {
      return <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">{children}</th>;
    },
    td({ children }) {
      return <td className="border-t border-gray-100 px-4 py-2 text-[15px] text-gray-700 dark:border-gray-800 dark:text-gray-300">{children}</td>;
    },
    a({ ...rest }) {
      return <a className="cursor-pointer text-blue-600 hover:underline dark:text-blue-400" target="_blank" rel="noopener noreferrer" {...rest} />;
    },
    blockquote({ children }) {
      return <blockquote className="my-4 rounded-r border-l-4 border-gray-300 bg-gray-50 py-2 pl-4 pr-2 italic text-gray-600 dark:border-gray-600 dark:bg-gray-800/30 dark:text-gray-400">{children}</blockquote>;
    },
    ul({ children }) {
      return <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>;
    },
    ol({ children }) {
      return <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>;
    },
    h1({ children }) {
      return <h1 className="mb-4 mt-6 border-b border-gray-100 pb-2 text-2xl font-bold text-gray-900 dark:border-gray-800 dark:text-white">{children}</h1>;
    },
    h2({ children }) {
      return <h2 className="mb-3 mt-5 text-xl font-bold text-gray-900 dark:text-white">{children}</h2>;
    },
    h3({ children }) {
      return <h3 className="mb-2 mt-4 text-lg font-bold text-gray-800 dark:text-gray-100">{children}</h3>;
    },
    p({ children }) {
      return <p className="mb-2 last:mb-0">{children}</p>;
    },
    img({ ...rest }) {
      return <img {...rest} className="my-3 h-auto max-w-full rounded-lg border border-gray-100 shadow-sm dark:border-gray-800" alt={rest.alt || 'image'} />;
    },
  }), []);

  return (
    <div className="markdown-body text-base leading-relaxed">
      <ReactMarkdown
        remarkPlugins={remarkPlugins}
        rehypePlugins={rehypePlugins}
        components={markdownComponents}
      >
        {content || ''}
      </ReactMarkdown>
    </div>
  );
};

export default React.memo(
  MarkdownRendererRich,
  (prev, next) => prev.content === next.content && prev.streaming === next.streaming
);
