import React, { Suspense, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const MarkdownRendererRich = React.lazy(() => import('./MarkdownRendererRich'));

const RICH_MARKDOWN_RE = /```|~~~|\$\$|\\\(|\\\[|```mermaid/i;

const basicMarkdownComponents = {
  code({ className, children, ...props }) {
    const codeContent = String(children).replace(/\n$/, '');
    const hasLanguage = /\blanguage-/.test(className || '');

    if (hasLanguage) {
      return (
        <pre className="my-3 overflow-x-auto rounded-md border border-gray-200 bg-gray-950 px-4 py-3 text-sm text-gray-100 dark:border-gray-700">
          <code className={className} {...props}>
            {codeContent}
          </code>
        </pre>
      );
    }

    return (
      <code
        className={`${className || ''} rounded bg-gray-100 px-1.5 py-0.5 font-mono text-[0.9em] text-pink-600 dark:bg-gray-700/50 dark:text-pink-400`}
        {...props}
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
  a({ ...props }) {
    return <a className="cursor-pointer text-blue-600 hover:underline dark:text-blue-400" target="_blank" rel="noopener noreferrer" {...props} />;
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
  img({ ...props }) {
    return <img {...props} className="my-3 h-auto max-w-full rounded-lg border border-gray-100 shadow-sm dark:border-gray-800" alt={props.alt || 'image'} />;
  },
};

const BasicMarkdownContent = React.memo(function BasicMarkdownContent({ content }) {
  const remarkPlugins = useMemo(() => [remarkGfm], []);

  return (
    <div className="markdown-body text-base leading-relaxed">
      <ReactMarkdown remarkPlugins={remarkPlugins} components={basicMarkdownComponents}>
        {content || ''}
      </ReactMarkdown>
    </div>
  );
});

export default React.memo(
  function MarkdownRenderer({ content, streaming = false }) {
    const shouldUseRichRenderer = useMemo(
      () => RICH_MARKDOWN_RE.test(String(content || '')),
      [content]
    );

    if (shouldUseRichRenderer) {
      return (
        <Suspense fallback={<BasicMarkdownContent content={content} />}>
          <MarkdownRendererRich content={content} streaming={streaming} />
        </Suspense>
      );
    }

    return <BasicMarkdownContent content={content} />;
  },
  (prev, next) => prev.content === next.content && prev.streaming === next.streaming
);
