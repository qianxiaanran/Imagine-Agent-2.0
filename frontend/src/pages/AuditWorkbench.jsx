import React, { useState, useEffect } from 'react';
import { 
  Box, Typography, Button, Table, TableBody, TableCell, 
  TableContainer, TableHead, TableRow, Paper, Chip, 
  Tabs, Tab, Card, CardContent, Grid, IconButton,
  Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, Alert, AlertTitle, CircularProgress,
  Badge, Tooltip, FormControl, InputLabel, Select, MenuItem
} from '@mui/material';
import { 
  CheckCircle, Cancel, Warning, Refresh, Visibility, 
  FilePresent, Assessment, TrendingUp, History,
  Approval, Replay, Delete
} from '@mui/icons-material';
import axios from 'axios';
import { collectAuditSourceDocuments } from '../utils/auditSourceLinks';

// API 配置
const API_BASE = '/api';

// 单据类型映射
const DOC_TYPE_LABELS = {
  contract: '合同',
  invoice: '发票',
  payment: '付款单',
  expense: '报销单',
  packing_list: '装箱单',
  bill_of_lading: '提单',
  air_waybill: '空运单',
  import_declaration: '进口报关单',
  export_declaration: '出口报关单',
  certificate_of_origin: '原产地证',
  trade_case: '贸易单据包',
};

// 风险等级颜色和标签
const RISK_LEVEL_CONFIG = {
  low: { color: 'success', label: '低风险', icon: CheckCircle },
  medium: { color: 'warning', label: '中风险', icon: Warning },
  high: { color: 'error', label: '高风险', icon: Cancel },
};

// 状态映射
const STATUS_CONFIG = {
  pending: { color: 'default', label: '待处理' },
  running: { color: 'info', label: '处理中' },
  done: { color: 'success', label: '已完成' },
  failed: { color: 'error', label: '失败' },
  cancelled: { color: 'default', label: '已取消' },
};

const WORKFLOW_LABELS = {
  pending: '待处理',
  running: '处理中',
  pending_docs: '待补件',
  ocr: 'OCR 解析中',
  extract: '字段抽取中',
  extracting: '字段抽取中',
  rules: '规则校核中',
  rule_checking: '规则校核中',
  ai: 'AI 复核中',
  ai_review: 'AI 复核中',
  review: '结果汇总中',
  report: '报告输出中',
  aggregating: '报告输出中',
  ready_for_erp: '可回写 ERP',
  done: '已完成',
  failed: '失败',
};

const FIELD_LABELS = {
  contract_title: '合同标题',
  project_name: '项目名称',
  subject: '主题',
  contract_no: '合同编号',
  invoice_no: '发票编号',
  application_no: '申请编号',
  vendor: '供应商',
  payee: '收款方',
  buyer: '买方',
  customer: '客户',
  payer: '付款方',
  total_amount: '总金额',
  currency: '币种',
  contract_date: '合同日期',
  invoice_date: '发票日期',
  payment_date: '付款日期',
  issue_date: '签发日期',
  sign_date: '签署日期',
  bank_name: '开户行',
  bank_account: '银行账号',
  po_no: '采购订单号',
  bl_no: '提单号',
  remark: '备注',
};

const FINDING_SOURCE_LABELS = {
  rule: '规则校核',
  cross_doc: '跨单据比对',
  anomaly: '异常识别',
  history: '历史画像',
  ai: 'AI 研判',
  manual: '人工标注',
};

const formatDateTime = (value) => {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value || '-');
  return date.toLocaleString('zh-CN');
};

const formatFieldLabel = (key) => FIELD_LABELS[key] || String(key || '-');
const formatWorkflowLabel = (value) => WORKFLOW_LABELS[String(value || '').toLowerCase()] || String(value || '-');
const formatFindingSource = (value) => FINDING_SOURCE_LABELS[String(value || '').toLowerCase()] || String(value || '系统识别');

/**
 * 审单工作台主组件
 */
export default function AuditWorkbench() {
  const [activeTab, setActiveTab] = useState(0);
  const [loading, setLoading] = useState(false);
  const [auditJobs, setAuditJobs] = useState([]);
  const [selectedJob, setSelectedJob] = useState(null);
  const [detailDialogOpen, setDetailDialogOpen] = useState(false);
  const [reviewDialogOpen, setReviewDialogOpen] = useState(false);
  const [reviewComment, setReviewComment] = useState('');
  const [filterStatus, setFilterStatus] = useState('all');
  const [filterRisk, setFilterRisk] = useState('all');
  const [stats, setStats] = useState({
    total: 0,
    pending: 0,
    highRisk: 0,
    today: 0,
  });

  // 加载审单任务列表
  const loadAuditJobs = async () => {
    setLoading(true);
    try {
      const response = await axios.get(`${API_BASE}/admin/audit/records`, {
        params: {
          group_by: 'case',
          status: filterStatus !== 'all' ? filterStatus : undefined,
          risk_level: filterRisk !== 'all' ? filterRisk : undefined,
        }
      });
      const rows = response.data?.data || response.data?.records || [];
      const responseMeta = response.data?.meta && typeof response.data.meta === 'object' ? response.data.meta : {};
      const responseStats = responseMeta?.stats && typeof responseMeta.stats === 'object' ? responseMeta.stats : {};
      setAuditJobs(rows);
      
      // 计算统计
      const stats = {
        total: Number(responseStats.total ?? responseMeta.total_visible ?? rows.length ?? 0),
        pending: Number(responseStats.pending ?? rows.filter(j => j.status === 'pending').length ?? 0),
        highRisk: Number(responseStats.high ?? rows.filter(j => String(j?.risk_level || j?.result?.risk_level || '').toLowerCase() === 'high').length ?? 0),
        today: rows.filter(j => {
          const jobDate = new Date(j.created_at);
          const today = new Date();
          return jobDate.toDateString() === today.toDateString();
        }).length || 0,
      };
      setStats(stats);
    } catch (error) {
      console.error('加载审单任务失败:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAuditJobs();
    // 每 30 秒自动刷新
    const interval = setInterval(loadAuditJobs, 30000);
    return () => clearInterval(interval);
  }, [filterStatus, filterRisk]);

  // 查看详情
  const handleViewDetail = async (job) => {
    try {
      const isCaseRow = String(job?.group_type || '').toLowerCase() === 'case' || (job?.case_id && Number(job?.case_document_count || 0) > 1);
      if (isCaseRow && job?.case_id) {
        const response = await axios.get(`${API_BASE}/audit/case/${encodeURIComponent(job.case_id)}`);
        const casePayload = response.data || {};
        setSelectedJob({
          ...job,
          ...casePayload,
          job_id: job.job_id,
          case_id: job.case_id || casePayload.case_id,
          doc_type: job.doc_type || casePayload.doc_type || 'trade_case',
          file_name: job.file_name || casePayload.file_name || '整包汇总',
          status: job.status || casePayload.status,
          workflow_state: casePayload.workflow_state || job.workflow_state,
          case_documents: Array.isArray(casePayload.case_documents) ? casePayload.case_documents : (job.case_documents || []),
          result: casePayload.result || job.result || {},
        });
      } else {
        const response = await axios.get(`${API_BASE}/audit/${job.job_id}`);
        const payload = response.data || {};
        setSelectedJob({
          ...job,
          ...payload,
          result: payload.result || job.result || {},
        });
      }
      setDetailDialogOpen(true);
    } catch (error) {
      console.error('加载详情失败:', error);
    }
  };

  // 提交复核
  const handleSubmitReview = async (status) => {
    try {
      await axios.post(`${API_BASE}/admin/audit/review`, {
        job_id: selectedJob.job_id,
        status,
        comment: reviewComment,
        case_id: selectedJob?.case_id || selectedJob?.result?.case_summary?.case_id || undefined,
        apply_to_case: Boolean((selectedJob?.result?.case_summary?.documents || selectedJob?.case_documents || []).length > 1) || undefined,
      });
      setReviewDialogOpen(false);
      setReviewComment('');
      loadAuditJobs();
    } catch (error) {
      console.error('提交复核失败:', error);
    }
  };

  // 重试失败任务
  const handleRetry = async (jobId) => {
    try {
      await axios.post(`${API_BASE}/admin/audit/${jobId}/retry`);
      loadAuditJobs();
    } catch (error) {
      console.error('重试失败:', error);
    }
  };

  // 取消任务
  const handleCancel = async (jobId) => {
    try {
      await axios.post(`${API_BASE}/admin/audit/${jobId}/cancel`);
      loadAuditJobs();
    } catch (error) {
      console.error('取消失败:', error);
    }
  };

  const selectedResult = selectedJob?.result || {};
  const selectedFields = selectedResult?.extracted_fields || {};
  const selectedFindings = Array.isArray(selectedResult?.findings) ? selectedResult.findings : [];
  const selectedChecks = Array.isArray(selectedResult?.erp_checks) ? selectedResult.erp_checks : [];
  const selectedCaseSummary = selectedResult?.case_summary && typeof selectedResult.case_summary === 'object' ? selectedResult.case_summary : {};
  const selectedCompleteness = selectedCaseSummary?.completeness && typeof selectedCaseSummary.completeness === 'object' ? selectedCaseSummary.completeness : {};
  const selectedCaseDocuments = Array.isArray(selectedCaseSummary?.documents)
    ? selectedCaseSummary.documents
    : Array.isArray(selectedJob?.case_documents)
      ? selectedJob.case_documents
      : [];
  const selectedCaseId = selectedJob?.case_id || selectedCaseSummary?.case_id || '';
  const isBatchReview = Boolean(selectedCaseId) && selectedCaseDocuments.length > 1;
  const selectedMissingDocs = Array.isArray(selectedCompleteness?.missing) ? selectedCompleteness.missing : [];
  const selectedRequiredDocs = Array.isArray(selectedCompleteness?.required) ? selectedCompleteness.required : [];
  const selectedPresentDocs = new Set(
    Array.isArray(selectedCompleteness?.present) && selectedCompleteness.present.length > 0
      ? selectedCompleteness.present
      : selectedCaseDocuments.map((item) => String(item?.tag || item?.doc_type || '').toLowerCase()).filter(Boolean)
  );
  const selectedAuditScore = selectedJob?.audit_score ?? selectedResult?.audit_score ?? '-';
  const selectedRiskConfig = RISK_LEVEL_CONFIG[selectedJob?.risk_level || selectedResult?.risk_level || 'low'] || RISK_LEVEL_CONFIG.low;
  const SelectedRiskIcon = selectedRiskConfig.icon;
  const selectedCheckPassed = selectedChecks.filter((item) => item?.passed === true).length;
  const selectedSourceDocuments = collectAuditSourceDocuments({
    file_url: selectedJob?.file_url,
    file_name: selectedJob?.file_name,
    job_id: selectedJob?.job_id,
    documents: selectedCaseDocuments,
  });

  return (
    <Box sx={{ p: 3 }}>
      {/* 页面标题 */}
      <Box sx={{ mb: 3, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography variant="h4" gutterBottom>
          📋 审单工作台
        </Typography>
        <Button 
          variant="contained" 
          color="primary"
          startIcon={<Refresh />}
          onClick={loadAuditJobs}
          disabled={loading}
        >
          刷新
        </Button>
      </Box>

      {/* 统计卡片 */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box>
                  <Typography color="text.secondary" variant="body2">
                    总 Case 数
                  </Typography>
                  <Typography variant="h4">{stats.total}</Typography>
                </Box>
                <FilePresent sx={{ fontSize: 48, color: 'text.secondary', opacity: 0.3 }} />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box>
                  <Typography color="text.secondary" variant="body2">
                    待处理
                  </Typography>
                  <Typography variant="h4" color="warning.main">{stats.pending}</Typography>
                </Box>
                <History sx={{ fontSize: 48, color: 'warning.main', opacity: 0.3 }} />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box>
                  <Typography color="text.secondary" variant="body2">
                    高风险
                  </Typography>
                  <Typography variant="h4" color="error.main">{stats.highRisk}</Typography>
                </Box>
                <Warning sx={{ fontSize: 48, color: 'error.main', opacity: 0.3 }} />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box>
                  <Typography color="text.secondary" variant="body2">
                    今日 Case
                  </Typography>
                  <Typography variant="h4" color="success.main">{stats.today}</Typography>
                </Box>
                <TrendingUp sx={{ fontSize: 48, color: 'success.main', opacity: 0.3 }} />
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* 筛选器 */}
      <Paper sx={{ p: 2, mb: 3 }}>
        <Grid container spacing={2} alignItems="center">
          <Grid item>
            <Typography variant="body2" sx={{ mr: 1 }}>筛选:</Typography>
          </Grid>
          <Grid item>
            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel>状态</InputLabel>
              <Select
                value={filterStatus}
                label="状态"
                onChange={(e) => setFilterStatus(e.target.value)}
              >
                <MenuItem value="all">全部</MenuItem>
                <MenuItem value="pending">待处理</MenuItem>
                <MenuItem value="running">处理中</MenuItem>
                <MenuItem value="done">已完成</MenuItem>
                <MenuItem value="failed">失败</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item>
            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel>风险等级</InputLabel>
              <Select
                value={filterRisk}
                label="风险等级"
                onChange={(e) => setFilterRisk(e.target.value)}
              >
                <MenuItem value="all">全部</MenuItem>
                <MenuItem value="high">高风险</MenuItem>
                <MenuItem value="medium">中风险</MenuItem>
                <MenuItem value="low">低风险</MenuItem>
              </Select>
            </FormControl>
          </Grid>
        </Grid>
      </Paper>

      {/* 任务列表 */}
      <TableContainer component={Paper}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Case / 任务</TableCell>
              <TableCell>类型</TableCell>
              <TableCell>汇总标题</TableCell>
              <TableCell>状态</TableCell>
              <TableCell>风险等级</TableCell>
              <TableCell>审单评分</TableCell>
              <TableCell>创建时间</TableCell>
              <TableCell align="right">操作</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={8} align="center">
                  <CircularProgress sx={{ m: 2 }} />
                  <Typography>加载中...</Typography>
                </TableCell>
              </TableRow>
            ) : auditJobs.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} align="center">
                  <Typography color="text.secondary">暂无审单 Case</Typography>
                </TableCell>
              </TableRow>
            ) : (
              auditJobs.map((job) => {
                const riskConfig = RISK_LEVEL_CONFIG[job.risk_level || job.result?.risk_level || 'low'];
                const RiskIcon = riskConfig.icon;
                const statusConfig = STATUS_CONFIG[job.status];
                const scoreValue = job.audit_score ?? job.result?.audit_score ?? 0;

                return (
                  <TableRow key={job.job_id} hover>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                        {job.case_id || `${job.job_id.slice(0, 8)}...`}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Chip 
                        label={DOC_TYPE_LABELS[job.doc_type] || job.doc_type}
                        size="small"
                        color="primary"
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell>{job.file_name}</TableCell>
                    <TableCell>
                      <Chip 
                        label={statusConfig.label}
                        size="small"
                        color={statusConfig.color}
                      />
                    </TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center' }}>
                        <RiskIcon sx={{ mr: 0.5, fontSize: 18 }} color={riskConfig.color} />
                        <Typography variant="body2" color={riskConfig.color}>
                          {riskConfig.label}
                        </Typography>
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center' }}>
                        <Box sx={{ width: 100, mr: 1 }}>
                          <CircularProgress 
                            variant="determinate" 
                            value={scoreValue || 0}
                            size={24}
                            thickness={6}
                            color={
                              (scoreValue || 0) >= 80 ? 'success' :
                              (scoreValue || 0) >= 60 ? 'warning' : 'error'
                            }
                          />
                        </Box>
                        <Typography variant="body2">
                          {scoreValue || '-'}
                        </Typography>
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" color="text.secondary">
                        {new Date(job.created_at).toLocaleString('zh-CN')}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Tooltip title="查看详情">
                        <IconButton 
                          size="small" 
                          onClick={() => handleViewDetail(job)}
                        >
                          <Visibility />
                        </IconButton>
                      </Tooltip>
                      
                      {String(job?.group_type || '').toLowerCase() !== 'case' && job.status === 'failed' && (
                        <Tooltip title="重试">
                          <IconButton 
                            size="small" 
                            color="warning"
                            onClick={() => handleRetry(job.job_id)}
                          >
                            <Replay />
                          </IconButton>
                        </Tooltip>
                      )}
                      
                      {String(job?.group_type || '').toLowerCase() !== 'case' && job.status === 'pending' && (
                        <Tooltip title="取消">
                          <IconButton 
                            size="small" 
                            color="error"
                            onClick={() => handleCancel(job.job_id)}
                          >
                            <Cancel />
                          </IconButton>
                        </Tooltip>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </TableContainer>

      {/* 详情对话框 */}
      {selectedJob && (
        <Dialog 
          open={detailDialogOpen} 
          onClose={() => setDetailDialogOpen(false)}
          maxWidth="lg"
          fullWidth
        >
          <DialogTitle>
            审单详情 - {selectedJob.file_name}
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              历史记录点开后直接展示摘要、Case 上下文、风险清单、结构化字段和校验结果。
            </Typography>
          </DialogTitle>
          <DialogContent dividers>
            <Box sx={{ mb: 3, display: 'flex', flexWrap: 'wrap', gap: 1 }}>
              <Chip label={selectedRiskConfig.label} color={selectedRiskConfig.color} size="small" icon={<SelectedRiskIcon />} />
              <Chip label={STATUS_CONFIG[selectedJob.status]?.label || selectedJob.status} color={STATUS_CONFIG[selectedJob.status]?.color || 'default'} size="small" />
              <Chip label={`流程：${formatWorkflowLabel(selectedJob.workflow_state || selectedJob.stage || selectedJob.status)}`} size="small" variant="outlined" />
              {selectedJob.case_id ? <Chip label={`Case：${selectedJob.case_id}`} size="small" color="info" variant="outlined" /> : null}
            </Box>

            <Grid container spacing={2} sx={{ mb: 3 }}>
              <Grid item xs={12} sm={6} md={3}>
                <Paper variant="outlined" sx={{ p: 2, borderRadius: 3, bgcolor: 'error.light' }}>
                  <Typography variant="caption" color="text.secondary">风险命中</Typography>
                  <Typography variant="h5" sx={{ mt: 1 }}>{selectedFindings.length}</Typography>
                  <Typography variant="body2" color="text.secondary">高风险 {selectedFindings.filter((item) => String(item?.severity || '').toLowerCase() === 'high').length} 项</Typography>
                </Paper>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Paper variant="outlined" sx={{ p: 2, borderRadius: 3, bgcolor: 'success.light' }}>
                  <Typography variant="caption" color="text.secondary">校验通过</Typography>
                  <Typography variant="h5" sx={{ mt: 1 }}>{selectedCheckPassed}/{selectedChecks.length || 0}</Typography>
                  <Typography variant="body2" color="text.secondary">结构化规则与 ERP 校验</Typography>
                </Paper>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Paper variant="outlined" sx={{ p: 2, borderRadius: 3, bgcolor: 'info.light' }}>
                  <Typography variant="caption" color="text.secondary">审单评分</Typography>
                  <Typography variant="h5" sx={{ mt: 1 }}>{selectedAuditScore}</Typography>
                  <Typography variant="body2" color="text.secondary">综合规则、AI 与上下文评分</Typography>
                </Paper>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Paper variant="outlined" sx={{ p: 2, borderRadius: 3, bgcolor: selectedMissingDocs.length > 0 ? 'warning.light' : 'grey.100' }}>
                  <Typography variant="caption" color="text.secondary">Case 文件</Typography>
                  <Typography variant="h5" sx={{ mt: 1 }}>{selectedCaseDocuments.length || 0}</Typography>
                  <Typography variant="body2" color="text.secondary">{selectedMissingDocs.length > 0 ? `缺 ${selectedMissingDocs.length} 类` : '上下文已齐套'}</Typography>
                </Paper>
              </Grid>
            </Grid>

            <Alert severity={selectedResult.risk_level === 'high' ? 'error' : selectedResult.risk_level === 'medium' ? 'warning' : 'success'} sx={{ mb: 3, borderRadius: 3 }}>
              <AlertTitle>{selectedResult.summary || '审单完成'}</AlertTitle>
              {selectedResult.next_action || '当前没有额外建议动作。'}
            </Alert>

            <Grid container spacing={2} sx={{ mb: 3 }}>
              <Grid item xs={12} md={7}>
                <Paper variant="outlined" sx={{ p: 2.5, borderRadius: 3, height: '100%' }}>
                  <Typography variant="subtitle1" gutterBottom>业务与单据画像</Typography>
                  <Grid container spacing={2}>
                    <Grid item xs={12} sm={6}>
                      <Typography variant="caption" color="text.secondary">任务 ID</Typography>
                      <Typography variant="body2" sx={{ fontFamily: 'monospace', wordBreak: 'break-all' }}>{selectedJob.job_id}</Typography>
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <Typography variant="caption" color="text.secondary">单据类型</Typography>
                      <Typography variant="body2">{DOC_TYPE_LABELS[selectedJob.doc_type] || selectedJob.doc_type}</Typography>
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <Typography variant="caption" color="text.secondary">文件名</Typography>
                      <Typography variant="body2">{selectedJob.file_name || '-'}</Typography>
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <Typography variant="caption" color="text.secondary">业务日期</Typography>
                      <Typography variant="body2">{formatDateTime(selectedFields?.contract_date || selectedFields?.invoice_date || selectedFields?.payment_date || selectedJob.created_at)}</Typography>
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <Typography variant="caption" color="text.secondary">业务主体</Typography>
                      <Typography variant="body2">{selectedFields?.vendor || selectedFields?.payee || '-'}</Typography>
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <Typography variant="caption" color="text.secondary">对手方</Typography>
                      <Typography variant="body2">{selectedFields?.buyer || selectedFields?.customer || selectedFields?.payer || '-'}</Typography>
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <Typography variant="caption" color="text.secondary">金额</Typography>
                      <Typography variant="body2">{selectedFields?.total_amount ? `${selectedFields.total_amount}${selectedFields?.currency ? ` ${selectedFields.currency}` : ''}` : '-'}</Typography>
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <Typography variant="caption" color="text.secondary">Case ID</Typography>
                      <Typography variant="body2">{selectedJob.case_id || selectedCaseSummary?.case_id || '-'}</Typography>
                    </Grid>
                  </Grid>
                </Paper>
              </Grid>

              <Grid item xs={12} md={5}>
                <Paper variant="outlined" sx={{ p: 2.5, borderRadius: 3, height: '100%' }}>
                  <Typography variant="subtitle1" gutterBottom>Case 上下文</Typography>
                  {selectedJob.case_id || selectedCaseDocuments.length > 0 ? (
                    <>
                      <Typography variant="body2" color="text.secondary">
                        待补件：{selectedMissingDocs.length > 0 ? selectedMissingDocs.map((item) => DOC_TYPE_LABELS[item] || item).join(' / ') : '无'}
                      </Typography>
                      <Box sx={{ mt: 2, display: 'grid', gap: 1 }}>
                        {selectedRequiredDocs.map((item) => (
                          <Box key={item} sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', px: 1.5, py: 1.2, borderRadius: 2, bgcolor: selectedPresentDocs.has(item) ? 'success.light' : 'warning.light' }}>
                            <Typography variant="body2">{DOC_TYPE_LABELS[item] || item}</Typography>
                            <Typography variant="caption" color={selectedPresentDocs.has(item) ? 'success.main' : 'warning.main'}>
                              {selectedPresentDocs.has(item) ? '已挂载' : '待补'}
                            </Typography>
                          </Box>
                        ))}
                      </Box>
                    </>
                  ) : (
                    <Typography variant="body2" color="text.secondary">当前记录还没有挂入业务 Case。</Typography>
                  )}
                </Paper>
              </Grid>
            </Grid>

            <Box sx={{ mb: 3 }}>
              <Paper variant="outlined" sx={{ p: 2.5, borderRadius: 3 }}>
                <Typography variant="subtitle1" gutterBottom>原始文件</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  历史详情和当前详情都保留原始文件入口，整包 Case 会列出全部关联单据。
                </Typography>
                {selectedSourceDocuments.length === 0 ? (
                  <Typography variant="body2" color="text.secondary">当前记录还没有可打开的原始文件地址。</Typography>
                ) : (
                  <Box sx={{ display: 'grid', gap: 1.5 }}>
                    {selectedSourceDocuments.map((doc, idx) => (
                      <Paper key={`${doc.fileName || 'doc'}-${doc.jobId || doc.docId || idx}`} variant="outlined" sx={{ p: 1.75, borderRadius: 2.5, bgcolor: 'grey.50' }}>
                        <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 1.5 }}>
                          <Box sx={{ minWidth: 0 }}>
                            <Typography variant="body2" sx={{ fontWeight: 600, wordBreak: 'break-all' }}>
                              {doc.fileName || `单据 ${idx + 1}`}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              {[doc.docType, doc.status, doc.jobId ? `任务 ${doc.jobId}` : ''].filter(Boolean).join(' · ') || '原始文件'}
                            </Typography>
                          </Box>
                          {doc.sourceUrl ? (
                            <Button
                              component="a"
                              href={doc.sourceUrl}
                              target="_blank"
                              rel="noreferrer"
                              size="small"
                              variant="outlined"
                              startIcon={<Visibility />}
                            >
                              打开原始文件
                            </Button>
                          ) : (
                            <Typography variant="caption" color="text.secondary">未保存可打开地址</Typography>
                          )}
                        </Box>
                      </Paper>
                    ))}
                  </Box>
                )}
              </Paper>
            </Box>

            <Box sx={{ mb: 3 }}>
              <Typography variant="subtitle1" gutterBottom>风险清单</Typography>
              {selectedFindings.length === 0 ? (
                <Paper variant="outlined" sx={{ p: 2.5, borderRadius: 3, bgcolor: 'grey.50' }}>
                  <Typography variant="body2" color="text.secondary">当前没有风险项。</Typography>
                </Paper>
              ) : (
                <Box sx={{ display: 'grid', gap: 1.5 }}>
                  {selectedFindings.map((finding, idx) => (
                    <Paper key={idx} variant="outlined" sx={{ p: 2, borderRadius: 3 }}>
                      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'center', mb: 1 }}>
                        <Chip
                          size="small"
                          color={finding.severity === 'high' ? 'error' : finding.severity === 'medium' ? 'warning' : 'info'}
                          label={finding.severity === 'high' ? '高风险' : finding.severity === 'medium' ? '中风险' : '低风险'}
                        />
                        <Chip size="small" variant="outlined" label={formatFindingSource(finding.source)} />
                      </Box>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>{finding.message || '未命名风险'}</Typography>
                      <Grid container spacing={2} sx={{ mt: 0.5 }}>
                        <Grid item xs={12} md={6}>
                          <Typography variant="caption" color="text.secondary">触发原因</Typography>
                          <Typography variant="body2">{finding.reason || '-'}</Typography>
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <Typography variant="caption" color="text.secondary">建议动作</Typography>
                          <Typography variant="body2">{finding.suggestion || finding.action || '-'}</Typography>
                        </Grid>
                      </Grid>
                    </Paper>
                  ))}
                </Box>
              )}
            </Box>

            <Grid container spacing={2}>
              <Grid item xs={12} md={6}>
                <Paper variant="outlined" sx={{ p: 2.5, borderRadius: 3, height: '100%' }}>
                  <Typography variant="subtitle1" gutterBottom>结构化字段</Typography>
                  {Object.keys(selectedFields).length === 0 ? (
                    <Typography variant="body2" color="text.secondary">当前没有结构化字段。</Typography>
                  ) : (
                    <Grid container spacing={1.5}>
                      {Object.entries(selectedFields).map(([key, value]) => {
                        if (value === undefined || value === null || value === '') return null;
                        return (
                          <Grid item xs={12} sm={6} key={key}>
                            <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2, bgcolor: 'grey.50' }}>
                              <Typography variant="caption" color="text.secondary">{formatFieldLabel(key)}</Typography>
                              <Typography variant="body2" sx={{ mt: 0.5, wordBreak: 'break-all' }}>
                                {Array.isArray(value) ? value.join(' / ') : String(value)}
                              </Typography>
                            </Paper>
                          </Grid>
                        );
                      })}
                    </Grid>
                  )}
                </Paper>
              </Grid>

              <Grid item xs={12} md={6}>
                <Paper variant="outlined" sx={{ p: 2.5, borderRadius: 3, height: '100%' }}>
                  <Typography variant="subtitle1" gutterBottom>规则与 ERP 校验</Typography>
                  {selectedChecks.length === 0 ? (
                    <Typography variant="body2" color="text.secondary">当前没有结构化校验项。</Typography>
                  ) : (
                    <Box sx={{ display: 'grid', gap: 1.2 }}>
                      {selectedChecks.map((item, idx) => (
                        <Paper key={idx} variant="outlined" sx={{ p: 1.5, borderRadius: 2, bgcolor: 'grey.50' }}>
                          <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 1 }}>
                            <Box>
                              <Typography variant="body2" sx={{ fontWeight: 600 }}>{item?.name || '未命名检查项'}</Typography>
                              <Typography variant="caption" color="text.secondary">{item?.reason || '-'}</Typography>
                            </Box>
                            <Chip size="small" color={item?.passed ? 'success' : 'error'} label={item?.passed ? '通过' : '未通过'} />
                          </Box>
                        </Paper>
                      ))}
                    </Box>
                  )}
                </Paper>
              </Grid>
            </Grid>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setDetailDialogOpen(false)}>关闭</Button>
            {selectedJob.status === 'done' && selectedJob.result?.risk_level !== 'low' && (
              <Button 
                variant="contained" 
                color="primary"
                onClick={() => {
                  setDetailDialogOpen(false);
                  setReviewDialogOpen(true);
                }}
              >
                {isBatchReview ? '整包复核' : '人工复核'}
              </Button>
            )}
          </DialogActions>
        </Dialog>
      )}

      {/* 复核对话框 */}
      <Dialog open={reviewDialogOpen} onClose={() => setReviewDialogOpen(false)}>
        <DialogTitle>{isBatchReview ? `整包复核 · ${selectedCaseDocuments.length} 份单据` : '人工复核'}</DialogTitle>
        <DialogContent>
          {isBatchReview && (
            <Alert severity="info" sx={{ mb: 2, borderRadius: 2 }}>
              当前提交会对同一批次的 {selectedCaseDocuments.length} 份单据一起生效，不需要逐张复核。
            </Alert>
          )}
          <TextField
            autoFocus
            margin="dense"
            label="复核意见"
            fullWidth
            multiline
            rows={4}
            value={reviewComment}
            onChange={(e) => setReviewComment(e.target.value)}
            placeholder="请输入复核意见..."
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setReviewDialogOpen(false)}>取消</Button>
          <Button 
            onClick={() => handleSubmitReview('need_more')}
            color="warning"
            variant="outlined"
          >
            {isBatchReview ? '整包补件' : '要求补充'}
          </Button>
          <Button 
            onClick={() => handleSubmitReview('rejected')}
            color="error"
            variant="outlined"
          >
            {isBatchReview ? '整包驳回' : '驳回'}
          </Button>
          <Button 
            onClick={() => handleSubmitReview('approved')}
            color="success"
            variant="contained"
          >
            {isBatchReview ? '整包通过' : '批准'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
