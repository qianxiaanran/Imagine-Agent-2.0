import React, { useEffect, useRef, useState, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import mermaid from 'mermaid';
import { Copy } from 'lucide-react';

// 在组件外部定义一个简单的缓存对象，避免重新挂载时丢失数据
const mermaidCache = {};

const Mermaid = ({ chart }) => {
  // 1. 初始化 state 时，尝试直接从缓存获取，如果有缓存，直接显示，不再等待异步渲染
  const [svg, setSvg] = useState(() => {
    if (mermaidCache[chart]) {
      return mermaidCache[chart];
    }
    return '';
  });

  const containerRef = useRef(null);

  useEffect(() => {
    // 如果缓存里已经有了，且 state 也对其了，就不需要再渲染了
    if (mermaidCache[chart] && svg === mermaidCache[chart]) {
      return;
    }

    mermaid.initialize({
      startOnLoad: false,
      theme: document.documentElement.classList.contains('dark') ? 'dark' : 'default',
      securityLevel: 'loose',
    });

    const renderChart = async () => {
      try {
        const id = `mermaid-${Math.random().toString(36).substr(2, 9)}`;
        const { svg: renderedSvg } = await mermaid.render(id, chart);

        // 2. 渲染成功后，写入缓存
        mermaidCache[chart] = renderedSvg;
        setSvg(renderedSvg);
      } catch (error) {
        console.error('Mermaid render error:', error);
        const errorHtml = `<div class="text-red-500 text-xs p-2 border border-red-200 rounded bg-red-50">Mermaid Render Error: ${error.message}</div>`;
        setSvg(errorHtml);
      }
    };

    if (chart) {
      renderChart();
    }
  }, [chart, svg]); // 添加 svg 依赖以配合缓存检查

  // 3. 渲染时增加 min-height 防止高度塌陷（可选优化）
  return (
    <div
      ref={containerRef}
      className="mermaid-wrapper flex justify-center my-4 overflow-x-auto bg-white dark:bg-gray-800 p-4 rounded-lg border border-gray-100 dark:border-gray-700 shadow-sm"
      style={{ minHeight: '60px' }}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
};

const MarkdownRenderer = ({ content, streaming = false }) => {
  // 直接使用内容，不做延迟，以保证流式表格实时更新
  const renderContent = content;

  // 始终加载数学公式样式
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

  // 无条件加载插件，避免流式输出遇到表格字符时出现样式闪烁
  const remarkPlugins = useMemo(() => [remarkGfm, remarkMath], []);
  const rehypePlugins = useMemo(() => [rehypeKatex], []);

  const markdownComponents = useMemo(() => ({
    code({ node, inline, className, children, ...props }) {
      const match = /language-(\w+)/.exec(className || '');
      const codeContent = String(children).replace(/\n$/, '');
      const isMermaid = match && match[1] === 'mermaid';

      if (!inline && isMermaid) {
        return <Mermaid chart={codeContent} />;
      }

      return !inline && match ? (
        <div className="relative group rounded-md overflow-hidden my-3 border border-gray-200 dark:border-gray-700">
          <div className="absolute right-2 top-2 opacity-0 group-hover:opacity-100 transition-opacity z-10">
            <button
              onClick={() => navigator.clipboard.writeText(codeContent)}
              className="p-1.5 bg-gray-800/80 text-white rounded hover:bg-gray-700 transition-colors"
              title="Copy Code"
            >
              <Copy size={12} />
            </button>
          </div>
          <SyntaxHighlighter
            style={vscDarkPlus}
            language={match[1]}
            PreTag="div"
            customStyle={{ margin: 0, borderRadius: 0, fontSize: '0.9em' }}
            {...props}
          >
            {codeContent}
          </SyntaxHighlighter>
        </div>
      ) : (
        <code className={`${className} bg-gray-100 dark:bg-gray-700/50 text-pink-600 dark:text-pink-400 px-1.5 py-0.5 rounded text-[0.9em] font-mono`} {...props}>
          {children}
        </code>
      );
    },
    table({ children }) {
      return <div className="overflow-x-auto my-4 rounded-lg border border-gray-200 dark:border-gray-700"><table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">{children}</table></div>;
    },
    thead({ children }) {
      return <thead className="bg-gray-50 dark:bg-gray-800">{children}</thead>;
    },
    th({ children }) {
      return <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider">{children}</th>;
    },
    td({ children }) {
      return <td className="px-4 py-2 whitespace-nowrap text-[15px] text-gray-700 dark:text-gray-300 border-t border-gray-100 dark:border-gray-800">{children}</td>;
    },
    a({ node, ...props }) {
      return <a className="text-blue-600 dark:text-blue-400 hover:underline cursor-pointer" target="_blank" rel="noopener noreferrer" {...props} />;
    },
    blockquote({ children }) {
      return <blockquote className="border-l-4 border-gray-300 dark:border-gray-600 pl-4 italic text-gray-600 dark:text-gray-400 my-4 bg-gray-50 dark:bg-gray-800/30 py-2 pr-2 rounded-r">{children}</blockquote>;
    },
    ul({ children }) {
      return <ul className="list-disc pl-5 my-2 space-y-1">{children}</ul>;
    },
    ol({ children }) {
      return <ol className="list-decimal pl-5 my-2 space-y-1">{children}</ol>;
    },
    h1({ children }) { return <h1 className="text-2xl font-bold mt-6 mb-4 text-gray-900 dark:text-white pb-2 border-b border-gray-100 dark:border-gray-800">{children}</h1>; },
    h2({ children }) { return <h2 className="text-xl font-bold mt-5 mb-3 text-gray-900 dark:text-white">{children}</h2>; },
    h3({ children }) { return <h3 className="text-lg font-bold mt-4 mb-2 text-gray-800 dark:text-gray-100">{children}</h3>; },
    p({ children }) { return <p className="mb-2 last:mb-0">{children}</p>; },
    img({ node, ...props }) {
      return <img {...props} className="max-w-full h-auto rounded-lg shadow-sm my-3 border border-gray-100 dark:border-gray-800" alt={props.alt || 'image'} />;
    }
  }), []);

  return (
    <div className="markdown-body text-base leading-relaxed">
      <ReactMarkdown
        remarkPlugins={remarkPlugins}
        rehypePlugins={rehypePlugins}
        components={markdownComponents}
      >
        {renderContent}
      </ReactMarkdown>
    </div>
  );
};

export default React.memo(
  MarkdownRenderer,
  (prev, next) => prev.content === next.content && prev.streaming === next.streaming
);
