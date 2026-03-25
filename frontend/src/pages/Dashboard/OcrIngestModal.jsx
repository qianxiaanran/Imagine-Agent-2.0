import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { X, Loader2, AlertTriangle, FileText, CheckCircle2 } from 'lucide-react';
import { API_BASE_URL, AUTH_TOKEN_KEY } from '../../api/config';

const OcrIngestModal = ({ isOpen, onClose, onSuccess, content, userId, sessionId, llmBackend }) => {
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [docType, setDocType] = useState('');
  const [docTypes, setDocTypes] = useState([]);
  const [schema, setSchema] = useState(null);
  const [fields, setFields] = useState({});
  const [title, setTitle] = useState('');

  const docTypeLabel = useMemo(() => {
    if (schema?.label) return schema.label;
    const match = docTypes.find((item) => item.value === docType);
    return match ? match.label : '文档';
  }, [schema, docTypes, docType]);

  const resetState = () => {
    setLoading(false);
    setSubmitting(false);
    setError('');
    setDocType('');
    setDocTypes([]);
    setSchema(null);
    setFields({});
    setTitle('');
  };

  const requestParse = useCallback(async (hintType = null) => {
    if (!content || !content.trim()) {
      setError('暂无可解析的内容');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const token = localStorage.getItem(AUTH_TOKEN_KEY);
      const headers = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;
      const response = await fetch(`${API_BASE_URL}/api/ocr/parse`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          content,
          hint_type: hintType || undefined,
          llm_backend: llmBackend || undefined,
          use_llm: true
        })
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.error || data.detail || '识别失败');
      }
      const payload = data.data || {};
      setDocType(payload.doc_type || '');
      setDocTypes(payload.doc_types || []);
      setSchema(payload.schema || null);
      setFields(payload.fields || {});
      const nextTitle = `${payload.doc_type_label || payload.schema?.label || '文档'}-${new Date().toISOString().slice(0, 10)}`;
      setTitle(nextTitle);
    } catch (e) {
      setError(e?.message || '识别失败，请重试');
    } finally {
      setLoading(false);
    }
  }, [content, llmBackend]);

  useEffect(() => {
    if (!isOpen) {
      resetState();
      return;
    }
    requestParse();
  }, [isOpen, requestParse]);

  const handleDocTypeChange = (value) => {
    setDocType(value);
    requestParse(value);
  };

  const updateField = (key, value) => {
    setFields((prev) => ({ ...prev, [key]: value }));
  };

  const handleSubmit = async () => {
    if (!docType) {
      setError('请先选择文档类型');
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      const token = localStorage.getItem(AUTH_TOKEN_KEY);
      const headers = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;
      const response = await fetch(`${API_BASE_URL}/api/ocr/submit`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          doc_type: docType,
          fields,
          content,
          user_id: userId,
          session_id: sessionId,
          title
        })
      });
      const data = await response.json();
      if (!response.ok || !data.success) {
        throw new Error(data.error || data.detail || '入库失败');
      }
      onSuccess?.('OCR 结果已提交入库。');
      onClose();
    } catch (e) {
      setError(e?.message || '入库失败，请重试');
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4 py-6">
      <div className="w-full max-w-4xl max-h-[90vh] bg-white dark:bg-gray-900 rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-800 overflow-hidden flex flex-col">
        <div className="px-5 py-4 border-b border-gray-100 dark:border-gray-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-300 flex items-center justify-center">
              <FileText size={20} />
            </div>
            <div>
              <div className="text-xs text-gray-500 dark:text-gray-400">OCR 智能录入</div>
              <div className="text-lg font-semibold text-gray-900 dark:text-white">字段识别与电子版预览</div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500 dark:text-gray-400"
          >
            <X size={18} />
          </button>
        </div>

        <div className="px-5 py-4 space-y-4 flex-1 overflow-y-auto min-h-0">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="md:col-span-2">
              <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">文档标题</label>
              <input
                className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-sm text-gray-800 dark:text-gray-200"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="输入文档标题"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">文档类型</label>
              <select
                className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-sm text-gray-800 dark:text-gray-200"
                value={docType}
                onChange={(e) => handleDocTypeChange(e.target.value)}
                disabled={loading}
              >
                {docTypes.map((item) => (
                  <option key={item.value} value={item.value}>{item.label}</option>
                ))}
              </select>
            </div>
          </div>

          {error && (
            <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2">
              <AlertTriangle size={16} />
              <span>{error}</span>
            </div>
          )}

          {loading ? (
            <div className="flex items-center justify-center py-12 text-gray-500">
              <Loader2 size={20} className="animate-spin mr-2" /> 正在识别字段...
            </div>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-medium text-gray-700 dark:text-gray-200">可编辑字段</div>
                  <div className="text-xs text-gray-400">共 {Object.keys(fields || {}).length} 项</div>
                </div>
                {schema?.sections?.map((section) => (
                  <div key={section.title} className="border border-gray-200 dark:border-gray-800 rounded-xl p-3">
                    <div className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2">{section.title}</div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {section.fields.map((field) => {
                        const value = fields?.[field.key] ?? '';
                        const isTextarea = field.type === 'textarea';
                        const inputType = field.type === 'date' ? 'date' : 'text';
                        return (
                          <div key={field.key} className={isTextarea ? 'sm:col-span-2' : ''}>
                            <label className="block text-[11px] text-gray-500 dark:text-gray-400 mb-1">{field.label}</label>
                            {isTextarea ? (
                              <textarea
                                className="w-full min-h-[72px] px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-sm text-gray-800 dark:text-gray-200"
                                placeholder={field.placeholder || ''}
                                value={value}
                                onChange={(e) => updateField(field.key, e.target.value)}
                              />
                            ) : (
                              <input
                                type={inputType}
                                className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-sm text-gray-800 dark:text-gray-200"
                                placeholder={field.placeholder || ''}
                                value={value}
                                onChange={(e) => updateField(field.key, e.target.value)}
                              />
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-medium text-gray-700 dark:text-gray-200">电子版预览</div>
                  <div className="text-xs text-emerald-600 flex items-center gap-1">
                    <CheckCircle2 size={12} /> 实时同步
                  </div>
                </div>
                <div className="border border-gray-200 dark:border-gray-800 rounded-2xl bg-gray-50 dark:bg-gray-900/40 p-4">
                  <div className="text-center">
                    <div className="text-lg font-semibold text-gray-900 dark:text-white">{docTypeLabel}</div>
                    <div className="text-[11px] text-gray-400 mt-1">{title || '未命名文档'}</div>
                  </div>
                  <div className="mt-4 space-y-3">
                    {schema?.sections?.map((section) => (
                      <div key={section.title} className="border border-gray-100 dark:border-gray-800 rounded-xl bg-white/70 dark:bg-gray-900/60 p-3">
                        <div className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2">{section.title}</div>
                        <div className="space-y-2 text-sm">
                          {section.fields.map((field) => {
                            const value = fields?.[field.key];
                            return (
                              <div key={field.key} className="flex items-start gap-2">
                                <div className="w-24 text-[11px] text-gray-400">{field.label}</div>
                                <div className={`flex-1 text-sm ${value ? 'text-gray-800 dark:text-gray-200' : 'text-gray-300 dark:text-gray-600 italic'}`}>
                                  {value || '未填写'}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="px-5 py-4 border-t border-gray-100 dark:border-gray-800 bg-gray-50/70 dark:bg-gray-900/60 flex items-center justify-between">
          <div className="text-xs text-gray-400">
            OCR 识别结果可随时修改，确认无误后提交入库。
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-sm font-medium border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800"
            >
              取消
            </button>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={loading || submitting}
              className="px-5 py-2 rounded-lg text-sm font-medium bg-black text-white disabled:opacity-50"
            >
              {submitting ? '提交中...' : '提交入库'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default OcrIngestModal;
