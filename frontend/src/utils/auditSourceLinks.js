import { API_BASE_URL } from "../api/config";

const AUDIT_SOURCE_ROUTE = "/api/public/audit/source";

const normalizeText = (value) => String(value || "").trim();

const isSameDocument = (left, right) => {
  const leftRawFileUrl = normalizeText(left?.rawFileUrl);
  const rightRawFileUrl = normalizeText(right?.rawFileUrl);
  const leftJobId = normalizeText(left?.jobId);
  const rightJobId = normalizeText(right?.jobId);
  const leftDocId = normalizeText(left?.docId);
  const rightDocId = normalizeText(right?.docId);
  const leftFileName = normalizeText(left?.fileName);
  const rightFileName = normalizeText(right?.fileName);

  if (leftDocId && rightDocId && leftDocId === rightDocId) return true;
  if (leftJobId && rightJobId && leftJobId === rightJobId) return true;
  if (leftRawFileUrl && rightRawFileUrl && leftRawFileUrl === rightRawFileUrl) return true;
  if (!leftDocId && !rightDocId && !leftJobId && !rightJobId && leftRawFileUrl && rightRawFileUrl && leftRawFileUrl === rightRawFileUrl) return true;
  if (!leftDocId && !rightDocId && !leftJobId && !rightJobId && !leftRawFileUrl && !rightRawFileUrl && leftFileName && rightFileName && leftFileName === rightFileName) return true;
  return false;
};

const documentCompletenessScore = (doc) =>
  [
    normalizeText(doc?.rawFileUrl),
    normalizeText(doc?.sourceUrl),
    normalizeText(doc?.fileName),
    normalizeText(doc?.jobId),
    normalizeText(doc?.docId),
    normalizeText(doc?.docType),
    normalizeText(doc?.status),
  ].filter(Boolean).length;

const mergeDocuments = (primary, secondary) => {
  const preferred = documentCompletenessScore(primary) >= documentCompletenessScore(secondary) ? primary : secondary;
  const fallback = preferred === primary ? secondary : primary;
  return {
    rawFileUrl: normalizeText(preferred?.rawFileUrl || fallback?.rawFileUrl),
    fileName: normalizeText(preferred?.fileName || fallback?.fileName) || "原始单据",
    jobId: normalizeText(preferred?.jobId || fallback?.jobId),
    docId: normalizeText(preferred?.docId || fallback?.docId),
    docType: normalizeText(preferred?.docType || fallback?.docType),
    status: normalizeText(preferred?.status || fallback?.status),
    sourceUrl: normalizeText(preferred?.sourceUrl || fallback?.sourceUrl),
  };
};

export const buildAuditSourceUrl = ({ file_url = "", file_name = "", job_id = "" } = {}) => {
  const rawFileUrl = normalizeText(file_url);
  const fileName = normalizeText(file_name);
  const jobId = normalizeText(job_id);
  const query = new URLSearchParams();
  if (rawFileUrl) query.set("file_url", rawFileUrl);
  if (fileName) query.set("file_name", fileName);
  if (jobId) query.set("job_id", jobId);
  const search = query.toString();
  return search ? `${API_BASE_URL}${AUDIT_SOURCE_ROUTE}?${search}` : "";
};

export const normalizeAuditSourceDocument = (value) => {
  if (!value || typeof value !== "object") return null;
  const rawFileUrl = normalizeText(value.file_url || value.fileUrl || value.rawFileUrl);
  const fileName = normalizeText(value.file_name || value.fileName);
  const jobId = normalizeText(value.job_id || value.jobId);
  const docId = normalizeText(value.doc_id || value.docId);
  const docType = normalizeText(value.tag || value.doc_type || value.docType);
  const status = normalizeText(value.status);

  if (!rawFileUrl && !fileName && !jobId && !docId) return null;

  return {
    rawFileUrl,
    fileName: fileName || "原始单据",
    jobId,
    docId,
    docType,
    status,
    sourceUrl: buildAuditSourceUrl({
      file_url: rawFileUrl,
      file_name: fileName,
      job_id: jobId,
    }),
  };
};

export const collectAuditSourceDocuments = ({
  file_url = "",
  file_name = "",
  job_id = "",
  documents = [],
} = {}) => {
  const normalizedDocuments = [];

  const pushDocument = (value) => {
    const doc = normalizeAuditSourceDocument(value);
    if (!doc) return;
    const existingIndex = normalizedDocuments.findIndex((item) => isSameDocument(item, doc));
    if (existingIndex >= 0) {
      normalizedDocuments[existingIndex] = mergeDocuments(normalizedDocuments[existingIndex], doc);
      return;
    }
    normalizedDocuments.push(doc);
  };

  pushDocument({ file_url, file_name, job_id });

  for (const item of Array.isArray(documents) ? documents : []) {
    pushDocument(item);
  }

  return normalizedDocuments;
};
