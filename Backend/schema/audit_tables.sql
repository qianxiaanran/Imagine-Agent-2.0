-- ============================================================
-- AI 审单系统数据库表结构
-- 创建时间：2026-03-19
-- 说明：支持审单任务、单据管理、风险检测、ERP 同步
-- ============================================================

-- 1. 审单任务主表
CREATE TABLE IF NOT EXISTS audit_jobs (
    job_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    case_id VARCHAR(64),                    -- 审单包 ID（多单据关联）
    doc_type VARCHAR(32) NOT NULL,          -- 单据类型：contract/invoice/payment/expense/...
    model_type VARCHAR(16) DEFAULT 'local', -- 模型类型：local/cloud
    status VARCHAR(16) NOT NULL DEFAULT 'pending',  -- pending/running/done/failed/cancelled
    stage VARCHAR(32) DEFAULT 'pending_docs',       -- 当前处理阶段
    progress INTEGER DEFAULT 0,             -- 进度 0-100
    workflow_state VARCHAR(32),             -- 工作流状态：pending_docs/review_required/ready_for_erp
    error_message TEXT,
    file_url TEXT NOT NULL,                 -- 文件存储路径
    file_name VARCHAR(256) NOT NULL,        -- 原始文件名
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 索引优化
CREATE INDEX idx_audit_jobs_user_id ON audit_jobs(user_id);
CREATE INDEX idx_audit_jobs_status ON audit_jobs(status);
CREATE INDEX idx_audit_jobs_case_id ON audit_jobs(case_id);
CREATE INDEX idx_audit_jobs_created_at ON audit_jobs(created_at DESC);

-- 2. 单据文件表
CREATE TABLE IF NOT EXISTS audit_docs (
    doc_id VARCHAR(64) PRIMARY KEY,
    job_id VARCHAR(64) NOT NULL REFERENCES audit_jobs(job_id) ON DELETE CASCADE,
    doc_type VARCHAR(32) NOT NULL,
    file_url TEXT NOT NULL,
    raw_text TEXT,                          -- OCR 识别原文
    page_texts JSONB,                       -- 分页文本
    ocr_confidence FLOAT,                   -- OCR 置信度
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_docs_job_id ON audit_docs(job_id);
CREATE INDEX idx_audit_docs_doc_type ON audit_docs(doc_type);

-- 3. 审单结果表
CREATE TABLE IF NOT EXISTS audit_results (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(64) UNIQUE NOT NULL REFERENCES audit_jobs(job_id) ON DELETE CASCADE,
    result_json JSONB NOT NULL,             -- 完整审单结果
    risk_level VARCHAR(16),                 -- low/medium/high
    audit_score FLOAT,                      -- 审单评分 0-100
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_results_risk_level ON audit_results(risk_level);

-- 4. 风险发现表（详细记录每条风险）
CREATE TABLE IF NOT EXISTS audit_findings (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(64) NOT NULL REFERENCES audit_jobs(job_id) ON DELETE CASCADE,
    rule_id VARCHAR(64),                    -- 命中的规则 ID
    source VARCHAR(32),                     -- rule/ai/anomaly/cross_doc
    severity VARCHAR(16) NOT NULL,          -- low/medium/high
    message TEXT NOT NULL,                  -- 风险描述
    suggestion TEXT,                        -- 处理建议
    evidence JSONB,                         -- 证据信息
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_findings_job_id ON audit_findings(job_id);
CREATE INDEX idx_audit_findings_severity ON audit_findings(severity);

-- 5. 人工复核记录表
CREATE TABLE IF NOT EXISTS audit_reviews (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(64) NOT NULL REFERENCES audit_jobs(job_id) ON DELETE CASCADE,
    reviewer_id VARCHAR(64) NOT NULL,       -- 复核人 ID
    status VARCHAR(16) NOT NULL,            -- approved/rejected/need_more
    comment TEXT,                           -- 复核意见
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_reviews_job_id ON audit_reviews(job_id);
CREATE INDEX idx_audit_reviews_reviewer_id ON audit_reviews(reviewer_id);

-- 6. 审单包（多单据关联）
CREATE TABLE IF NOT EXISTS audit_cases (
    case_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    doc_type_hint VARCHAR(32),              -- 期望的单据类型
    latest_job_id VARCHAR(64),              -- 最新的任务 ID
    documents JSONB DEFAULT '[]'::jsonb,    -- 单据列表快照
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_cases_user_id ON audit_cases(user_id);

-- 7. ERP 回写记录表
CREATE TABLE IF NOT EXISTS audit_erp_actions (
    id SERIAL PRIMARY KEY,
    trace_id VARCHAR(64) UNIQUE NOT NULL,   -- 追踪 ID
    job_id VARCHAR(64) NOT NULL REFERENCES audit_jobs(job_id),
    action VARCHAR(16) NOT NULL,            -- approved/rejected/need_more
    operator_id VARCHAR(64) NOT NULL,
    provider VARCHAR(32) NOT NULL,          -- ERP 提供商：mock/yonyou/kingdee/sap
    status VARCHAR(16) DEFAULT 'queued',    -- queued/synced/failed
    risk_level VARCHAR(16),
    audit_score FLOAT,
    comment TEXT,
    response_json JSONB,                    -- ERP 响应
    last_error TEXT,
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_erp_actions_job_id ON audit_erp_actions(job_id);
CREATE INDEX idx_audit_erp_actions_trace_id ON audit_erp_actions(trace_id);

-- 8. 审单规则表（支持动态配置）
CREATE TABLE IF NOT EXISTS audit_rules (
    id SERIAL PRIMARY KEY,
    doc_type VARCHAR(32) NOT NULL,          -- 适用单据类型
    rule_id VARCHAR(64) NOT NULL,           -- 规则唯一标识
    version INTEGER DEFAULT 1,              -- 规则版本
    severity VARCHAR(16) NOT NULL,          -- low/medium/high
    message TEXT NOT NULL,
    suggestion TEXT,
    checks_json JSONB NOT NULL,             -- 检查条件
    when_json JSONB,                        -- 触发条件
    evidence_json JSONB,                    -- 证据配置
    enabled BOOLEAN DEFAULT TRUE,           -- 是否启用
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(doc_type, rule_id, version)
);

CREATE INDEX idx_audit_rules_doc_type ON audit_rules(doc_type);
CREATE INDEX idx_audit_rules_enabled ON audit_rules(enabled);

-- ============================================================
-- ERP 主数据表（Mock 数据，实际使用时对接真实 ERP）
-- ============================================================

-- 合同主数据
CREATE TABLE IF NOT EXISTS erp_contracts (
    id SERIAL PRIMARY KEY,
    contract_no VARCHAR(64) UNIQUE NOT NULL,
    contract_name VARCHAR(256),
    contract_type VARCHAR(32),              -- sales/purchase/service/...
    vendor_name VARCHAR(128),
    vendor_id VARCHAR(64),
    contract_amount DECIMAL(18,2),
    currency VARCHAR(8) DEFAULT 'CNY',
    signed_date DATE,
    start_date DATE,
    end_date DATE,
    status VARCHAR(16) DEFAULT 'active',    -- active/completed/cancelled
    paid_amount DECIMAL(18,2) DEFAULT 0,
    budget_remaining DECIMAL(18,2),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_erp_contracts_contract_no ON erp_contracts(contract_no);
CREATE INDEX idx_erp_contracts_vendor ON erp_contracts(vendor_name);

-- 发票主数据
CREATE TABLE IF NOT EXISTS erp_invoices (
    id SERIAL PRIMARY KEY,
    invoice_no VARCHAR(64) UNIQUE NOT NULL,
    invoice_code VARCHAR(32),               -- 发票代码
    invoice_date DATE,
    vendor_name VARCHAR(128),
    vendor_tax_no VARCHAR(32),
    total_amount DECIMAL(18,2),
    tax_amount DECIMAL(18,2),
    net_amount DECIMAL(18,2),
    contract_no VARCHAR(64),                -- 关联合同
    status VARCHAR(16) DEFAULT 'pending',   -- pending/verified/rejected
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_erp_invoices_invoice_no ON erp_invoices(invoice_no);
CREATE INDEX idx_erp_invoices_contract_no ON erp_invoices(contract_no);

-- 供应商主数据
CREATE TABLE IF NOT EXISTS erp_vendors (
    id SERIAL PRIMARY KEY,
    vendor_id VARCHAR(64) UNIQUE NOT NULL,
    vendor_name VARCHAR(128) NOT NULL,
    tax_no VARCHAR(32),
    contact_person VARCHAR(64),
    contact_phone VARCHAR(32),
    contact_email VARCHAR(128),
    bank_name VARCHAR(128),
    bank_account VARCHAR(64),
    vendor_status VARCHAR(16) DEFAULT 'active',  -- active/blacklist/suspended/inactive
    blacklist_hit BOOLEAN DEFAULT FALSE,
    risk_level VARCHAR(16) DEFAULT 'low',   -- low/medium/high
    rating INTEGER DEFAULT 5,               -- 1-5 评分
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_erp_vendors_vendor_name ON erp_vendors(vendor_name);
CREATE INDEX idx_erp_vendors_status ON erp_vendors(vendor_status);

-- ============================================================
-- 初始化 Mock 数据（用于测试）
-- ============================================================

-- 插入测试供应商
INSERT INTO erp_vendors (vendor_id, vendor_name, tax_no, vendor_status, blacklist_hit, rating) VALUES
('V001', '天津纺织集团进出口股份有限公司', '91120000123456789X', 'active', false, 5),
('V002', '上海贸易有限公司', '91310000987654321A', 'active', false, 4),
('V003', '黑名单测试公司', '91110000111111111B', 'blacklist', true, 1)
ON CONFLICT (vendor_id) DO NOTHING;

-- 插入测试合同
INSERT INTO erp_contracts (contract_no, contract_name, contract_type, vendor_name, contract_amount, paid_amount, budget_remaining, status) VALUES
('CT-2026-001', '纺织品采购合同', 'purchase', '天津纺织集团进出口股份有限公司', 500000.00, 200000.00, 300000.00, 'active'),
('CT-2026-002', '设备采购框架合同', 'purchase', '上海贸易有限公司', 1000000.00, 0, 1000000.00, 'active')
ON CONFLICT (contract_no) DO NOTHING;

-- ============================================================
-- 视图：审单任务统计
-- ============================================================

CREATE OR REPLACE VIEW v_audit_dashboard AS
SELECT 
    DATE(created_at) AS audit_date,
    status,
    risk_level,
    COUNT(*) AS job_count,
    AVG((result_json->>'audit_score')::FLOAT) AS avg_score
FROM audit_jobs j
LEFT JOIN audit_results r ON j.job_id = r.job_id
GROUP BY DATE(created_at), status, risk_level
ORDER BY audit_date DESC;

-- ============================================================
-- 触发器：自动更新 updated_at
-- ============================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 为所有需要自动更新时间的表添加触发器
CREATE TRIGGER update_audit_jobs_updated_at BEFORE UPDATE ON audit_jobs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_audit_docs_updated_at BEFORE UPDATE ON audit_docs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_audit_results_updated_at BEFORE UPDATE ON audit_results
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_audit_cases_updated_at BEFORE UPDATE ON audit_cases
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_audit_erp_actions_updated_at BEFORE UPDATE ON audit_erp_actions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_audit_rules_updated_at BEFORE UPDATE ON audit_rules
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
