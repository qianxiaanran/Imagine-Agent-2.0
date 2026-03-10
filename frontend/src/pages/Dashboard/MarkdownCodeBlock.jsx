import React from 'react';
import { Copy } from 'lucide-react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';

function MarkdownCodeBlock({ codeContent, language, syntaxProps }) {
  return (
    <div className="group relative my-3 overflow-hidden rounded-md border border-gray-200 dark:border-gray-700">
      <div className="absolute right-2 top-2 z-10 opacity-0 transition-opacity group-hover:opacity-100">
        <button
          onClick={() => navigator.clipboard.writeText(codeContent)}
          className="rounded bg-gray-800/80 p-1.5 text-white transition-colors hover:bg-gray-700"
          title="Copy Code"
        >
          <Copy size={12} />
        </button>
      </div>
      <SyntaxHighlighter
        style={vscDarkPlus}
        language={language}
        PreTag="div"
        customStyle={{ margin: 0, borderRadius: 0, fontSize: '0.9em' }}
        {...syntaxProps}
      >
        {codeContent}
      </SyntaxHighlighter>
    </div>
  );
}

export default React.memo(MarkdownCodeBlock);
