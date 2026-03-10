import React, { Suspense, useEffect, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';

const MarkdownCodeBlock = React.lazy(() => import('./MarkdownCodeBlock'));

const mermaidCache = {};
let mermaidModulePromise;

const loadMermaid = async () => {
  if (!mermaidModulePromise) {
    mermaidModulePromise = import('mermaid').then((module) => module.default || module);
  }
  return mermaidModulePromise;
};

const Mermaid = ({ chart }) => {
  const [svg, setSvg] = useState(() => mermaidCache[chart] || '');

  useEffect(() => {
    if (mermaidCache[chart]) {
      return undefined;
    }

    let cancelled = false;

    const renderChart = async () => {
      try {
        const mermaid = await loadMermaid();
        if (cancelled) return;
        mermaid.initialize({
          startOnLoad: false,
          theme: document.documentElement.classList.contains('dark') ? 'dark' : 'default',
          securityLevel: 'loose',
        });
        const id = `mermaid-${Math.random().toString(36).slice(2, 11)}`;
        const { svg: renderedSvg } = await mermaid.render(id, chart);
        if (cancelled) return;
        mermaidCache[chart] = renderedSvg;
        setSvg(renderedSvg);
      } catch (error) {
        if (cancelled) return;
        const message = error instanceof Error ? error.message : 'Unknown mermaid render error';
        setSvg(`<div class="rounded border border-red-200 bg-red-50 p-2 text-xs text-red-500">Mermaid Render Error: ${message}</div>`);
      }
    };

    if (chart) {
      void renderChart();
    }

    return () => {
      cancelled = true;
    };
  }, [chart]);

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
