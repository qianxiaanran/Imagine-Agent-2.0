import React from "react";
import { ExternalLink, FileText } from "lucide-react";

import { collectAuditSourceDocuments } from "../utils/auditSourceLinks";

const cn = (...parts) => parts.filter(Boolean).join(" ");

export default function AuditSourceFilesPanel({
  title = "",
  hint = "",
  fileUrl = "",
  fileName = "",
  jobId = "",
  documents = [],
  emptyText = "当前记录还没有可打开的原始文件。",
  showHeader = true,
}) {
  const sourceDocuments = collectAuditSourceDocuments({
    file_url: fileUrl,
    file_name: fileName,
    job_id: jobId,
    documents,
  });
  const showMultiple = sourceDocuments.length > 1;
  const resolvedTitle = title || (showMultiple ? "关联单据" : "原始单据");

  return (
    <div className="space-y-3">
      {showHeader ? (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-slate-100">
            <FileText size={16} />
            {resolvedTitle}
          </div>
          {hint ? <div className="text-xs leading-5 text-slate-500 dark:text-slate-400">{hint}</div> : null}
        </div>
      ) : null}
      {sourceDocuments.length > 0 ? (
        <div className="space-y-2">
          {sourceDocuments.map((doc, idx) => (
            <div
              key={`${doc.fileName || "doc"}-${doc.jobId || doc.docId || idx}`}
              className="rounded-2xl border border-slate-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-900/80"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-medium break-all text-slate-900 dark:text-slate-100">
                    {doc.fileName || `单据 ${idx + 1}`}
                  </div>
                  <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-slate-500 dark:text-slate-400">
                    {doc.docType ? <span>{doc.docType}</span> : null}
                    {doc.status ? <span>{doc.status}</span> : null}
                    {doc.jobId ? <span>任务 {doc.jobId}</span> : null}
                  </div>
                </div>
                {doc.sourceUrl ? (
                  <a
                    href={doc.sourceUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex shrink-0 items-center gap-1.5 rounded-xl border border-cyan-200 bg-cyan-50 px-3 py-2 text-xs font-medium text-cyan-700 transition hover:bg-cyan-100 dark:border-cyan-900/60 dark:bg-cyan-950/20 dark:text-cyan-300 dark:hover:bg-cyan-950/40"
                  >
                    <ExternalLink size={13} />
                    打开原始文件
                  </a>
                ) : (
                  <div className="text-xs leading-5 text-slate-400 dark:text-slate-500">
                    当前只保留了文件名，没有可直接打开的地址。
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div
          className={cn(
            "rounded-2xl border border-dashed border-slate-300 px-4 py-5 text-sm leading-6 text-slate-500 dark:border-slate-700 dark:text-slate-400"
          )}
        >
          {emptyText}
        </div>
      )}
    </div>
  );
}
