-- ============================================================
-- 数据库初始化脚本
-- 用法：在 Supabase SQL Editor 中执行，或用 psql 命令行
-- ============================================================

-- 1. 检查是否已存在表（避免重复创建）
\echo '检查现有表...'
SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE 'audit_%' OR tablename LIKE 'erp_%';

-- 2. 执行建表脚本
\echo '开始创建审单系统表...'
\i audit_tables.sql

-- 3. 验证创建结果
\echo '验证表结构...'
SELECT 
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables 
WHERE schemaname = 'public' 
  AND (tablename LIKE 'audit_%' OR tablename LIKE 'erp_%')
ORDER BY tablename;

-- 4. 显示表记录数统计
\echo '记录数统计...'
SELECT 'audit_jobs' AS table_name, COUNT(*) AS row_count FROM audit_jobs
UNION ALL
SELECT 'audit_docs', COUNT(*) FROM audit_docs
UNION ALL
SELECT 'audit_results', COUNT(*) FROM audit_results
UNION ALL
SELECT 'audit_findings', COUNT(*) FROM audit_findings
UNION ALL
SELECT 'audit_reviews', COUNT(*) FROM audit_reviews
UNION ALL
SELECT 'audit_cases', COUNT(*) FROM audit_cases
UNION ALL
SELECT 'audit_erp_actions', COUNT(*) FROM audit_erp_actions
UNION ALL
SELECT 'audit_rules', COUNT(*) FROM audit_rules
UNION ALL
SELECT 'erp_contracts', COUNT(*) FROM erp_contracts
UNION ALL
SELECT 'erp_invoices', COUNT(*) FROM erp_invoices
UNION ALL
SELECT 'erp_vendors', COUNT(*) FROM erp_vendors;

\echo '数据库初始化完成！'
