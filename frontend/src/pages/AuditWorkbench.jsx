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
          status: filterStatus !== 'all' ? filterStatus : undefined,
          risk_level: filterRisk !== 'all' ? filterRisk : undefined,
        }
      });
      setAuditJobs(response.data.records || []);
      
      // 计算统计
      const stats = {
        total: response.data.records?.length || 0,
        pending: response.data.records?.filter(j => j.status === 'pending').length || 0,
        highRisk: response.data.records?.filter(j => j.result?.risk_level === 'high').length || 0,
        today: response.data.records?.filter(j => {
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
  const handleViewDetail = async (jobId) => {
    try {
      const response = await axios.get(`${API_BASE}/audit/${jobId}`);
      setSelectedJob(response.data);
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
                    总任务数
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
                    今日审单
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
              <TableCell>任务 ID</TableCell>
              <TableCell>单据类型</TableCell>
              <TableCell>文件名</TableCell>
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
                  <Typography color="text.secondary">暂无审单任务</Typography>
                </TableCell>
              </TableRow>
            ) : (
              auditJobs.map((job) => {
                const riskConfig = RISK_LEVEL_CONFIG[job.result?.risk_level || 'low'];
                const RiskIcon = riskConfig.icon;
                const statusConfig = STATUS_CONFIG[job.status];

                return (
                  <TableRow key={job.job_id} hover>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                        {job.job_id.slice(0, 8)}...
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
                            value={job.result?.audit_score || 0}
                            size={24}
                            thickness={6}
                            color={
                              (job.result?.audit_score || 0) >= 80 ? 'success' :
                              (job.result?.audit_score || 0) >= 60 ? 'warning' : 'error'
                            }
                          />
                        </Box>
                        <Typography variant="body2">
                          {job.result?.audit_score || '-'}
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
                          onClick={() => handleViewDetail(job.job_id)}
                        >
                          <Visibility />
                        </IconButton>
                      </Tooltip>
                      
                      {job.status === 'failed' && (
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
                      
                      {job.status === 'pending' && (
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
          maxWidth="md"
          fullWidth
        >
          <DialogTitle>
            审单详情 - {selectedJob.file_name}
          </DialogTitle>
          <DialogContent dividers>
            {/* 基本信息 */}
            <Box sx={{ mb: 3 }}>
              <Typography variant="h6" gutterBottom>基本信息</Typography>
              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <Typography variant="body2" color="text.secondary">任务 ID</Typography>
                  <Typography variant="body2" fontFamily="monospace">
                    {selectedJob.job_id}
                  </Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="body2" color="text.secondary">单据类型</Typography>
                  <Typography variant="body2">
                    {DOC_TYPE_LABELS[selectedJob.doc_type] || selectedJob.doc_type}
                  </Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="body2" color="text.secondary">状态</Typography>
                  <Chip 
                    label={STATUS_CONFIG[selectedJob.status]?.label}
                    size="small"
                    color={STATUS_CONFIG[selectedJob.status]?.color}
                  />
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="body2" color="text.secondary">风险等级</Typography>
                  <Chip 
                    label={RISK_LEVEL_CONFIG[selectedJob.result?.risk_level || 'low']?.label}
                    size="small"
                    color={RISK_LEVEL_CONFIG[selectedJob.result?.risk_level || 'low']?.color}
                  />
                </Grid>
              </Grid>
            </Box>

            {/* 审单结果 */}
            {selectedJob.result && (
              <Box sx={{ mb: 3 }}>
                <Typography variant="h6" gutterBottom>审单结果</Typography>
                <Alert severity={
                  selectedJob.result.risk_level === 'high' ? 'error' :
                  selectedJob.result.risk_level === 'medium' ? 'warning' : 'success'
                } sx={{ mb: 2 }}>
                  <AlertTitle>
                    {selectedJob.result.summary || '审单完成'}
                  </AlertTitle>
                  {selectedJob.result.next_action && (
                    <Typography variant="body2">
                      建议：{selectedJob.result.next_action}
                    </Typography>
                  )}
                </Alert>

                {/* 提取字段 */}
                {selectedJob.result.extracted_fields && (
                  <Box sx={{ mb: 2 }}>
                    <Typography variant="subtitle2" gutterBottom>提取字段</Typography>
                    <Paper variant="outlined" sx={{ p: 2, bgcolor: 'grey.50' }}>
                      <Grid container spacing={1}>
                        {Object.entries(selectedJob.result.extracted_fields).map(([key, value]) => (
                          <Grid item xs={6} key={key}>
                            <Typography variant="body2" color="text.secondary">
                              {key}:
                            </Typography>
                            <Typography variant="body2" fontFamily="monospace">
                              {value || '-'}
                            </Typography>
                          </Grid>
                        ))}
                      </Grid>
                    </Paper>
                  </Box>
                )}

                {/* 风险发现 */}
                {selectedJob.result.findings && selectedJob.result.findings.length > 0 && (
                  <Box sx={{ mb: 2 }}>
                    <Typography variant="subtitle2" gutterBottom>
                      风险发现 ({selectedJob.result.findings.length})
                    </Typography>
                    {selectedJob.result.findings.map((finding, idx) => (
                      <Alert 
                        key={idx}
                        severity={finding.severity === 'high' ? 'error' : finding.severity === 'medium' ? 'warning' : 'info'}
                        sx={{ mb: 1 }}
                      >
                        <Typography variant="body2">{finding.message}</Typography>
                        {finding.suggestion && (
                          <Typography variant="caption" display="block" sx={{ mt: 0.5 }}>
                            建议：{finding.suggestion}
                          </Typography>
                        )}
                      </Alert>
                    ))}
                  </Box>
                )}
              </Box>
            )}
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
                人工复核
              </Button>
            )}
          </DialogActions>
        </Dialog>
      )}

      {/* 复核对话框 */}
      <Dialog open={reviewDialogOpen} onClose={() => setReviewDialogOpen(false)}>
        <DialogTitle>人工复核</DialogTitle>
        <DialogContent>
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
            要求补充
          </Button>
          <Button 
            onClick={() => handleSubmitReview('rejected')}
            color="error"
            variant="outlined"
          >
            驳回
          </Button>
          <Button 
            onClick={() => handleSubmitReview('approved')}
            color="success"
            variant="contained"
          >
            批准
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
