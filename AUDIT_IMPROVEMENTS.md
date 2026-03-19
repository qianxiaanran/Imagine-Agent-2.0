# 🔴 AI 审单系统 - 高优先级改进实施指南

**创建时间**: 2026-03-19  
**作者**: 小猫娘 🐱  
**状态**: 待实施

---

## 📋 目录

1. [任务 1: 补充数据库建表脚本](#任务-1-补充数据库建表脚本)
2. [任务 2: 实现真实 ERP 接口](#任务-2-实现真实-erp-接口)
3. [任务 3: 开发审单工作台前端](#任务-3-开发审单工作台前端)
4. [验证与测试](#验证与测试)
5. [常见问题](#常见问题)

---

## 任务 1: 补充数据库建表脚本

### 📁 涉及文件

- `Backend/schema/audit_tables.sql` - 建表脚本（✅ 已创建）
- `Backend/schema/init_audit_db.sql` - 初始化脚本（✅ 已创建）

### 🚀 实施步骤

#### 步骤 1: 在 Supabase 执行建表脚本

**方法 A: 使用 Supabase Web 控制台**

1. 登录 Supabase: https://supabase.com
2. 选择你的项目
3. 进入 **SQL Editor**
4. 复制 `Backend/schema/audit_tables.sql` 全部内容
5. 点击 **Run** 执行
6. 验证：在 Table Editor 中查看新表

**方法 B: 使用 psql 命令行**

```bash
# 连接到 Supabase 数据库
psql postgresql://postgres:[你的密码]@[你的主机]:5432/postgres

# 执行建表脚本
\i Backend/schema/audit_tables.sql

# 验证
\dt audit_*
\dt erp_*
```

**方法 C: 使用 Python 脚本**

```python
# scripts/init_audit_db.py
from supabase import create_client
import os

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase = create_client(supabase_url, supabase_key)

# 读取 SQL 文件
with open("Backend/schema/audit_tables.sql", "r", encoding="utf-8") as f:
    sql_script = f.read()

# 执行（需要拆分语句）
statements = sql_script.split(";")
for stmt in statements:
    if stmt.strip():
        try:
            supabase.rpc("exec_sql", {"sql": stmt}).execute()
        except Exception as e:
            print(f"执行失败：{e}")
```

#### 步骤 2: 验证表结构

```sql
-- 检查表是否存在
SELECT tablename 
FROM pg_tables 
WHERE schemaname = 'public' 
  AND (tablename LIKE 'audit_%' OR tablename LIKE 'erp_%');

-- 预期输出:
-- audit_jobs
-- audit_docs
-- audit_results
-- audit_findings
-- audit_reviews
-- audit_cases
-- audit_erp_actions
-- audit_rules
-- erp_contracts
-- erp_invoices
-- erp_vendors
```

#### 步骤 3: 配置环境变量

在 `.env.local` 或系统环境变量中添加：

```bash
# 数据库配置（如果和现有不同）
SUPABASE_DB_HOST=xxx.supabase.co
SUPABASE_DB_USER=postgres
SUPABASE_DB_PASSWORD=你的密码
SUPABASE_DB_NAME=postgres
SUPABASE_DB_PORT=5432
SUPABASE_DB_SSLMODE=require
```

#### 步骤 4: 更新后端配置

修改 `Backend/audit_pipeline.py`，确保使用新的数据库连接：

```python
# 已有代码会自动使用 supabase_client
# 无需修改，确保 supabase_client.py 配置正确即可
```

---

## 任务 2: 实现真实 ERP 接口

### 📁 涉及文件

- `Backend/erp_adapters.py` - ERP 适配器实现（✅ 已创建）
- `Backend/erp_adapter.py` - 原有适配器（需要更新）

### 🚀 实施步骤

#### 步骤 1: 备份原有文件

```bash
cd Backend
cp erp_adapter.py erp_adapter.py.bak
```

#### 步骤 2: 更新 erp_adapter.py

在 `Backend/erp_adapter.py` 文件末尾添加：

```python
# 导入新适配器
try:
    from erp_adapters import (
        YonyouERPAdapter,
        KingdeeERPAdapter,
        SAPERPAdapter,
        get_erp_adapter as get_new_erp_adapter,
        get_supported_erp_providers as get_new_providers
    )
    
    # 覆盖原有函数
    get_erp_adapter = get_new_erp_adapter
    get_supported_erp_providers = get_new_providers
    print("[ERP] 已加载新版 ERP 适配器（用友/金蝶/SAP）")
except ImportError as e:
    print(f"[ERP] 新版适配器加载失败：{e}")
```

#### 步骤 3: 配置 ERP 连接信息

在 `.env.local` 中添加：

```bash
# ERP 提供商选择：mock/yonyou/kingdee/sap
AUDIT_ERP_PROVIDER=yonyou

# 用友 NC/U8 配置
YONYOU_BASE_URL=https://api.yonyou.com/ncchrk
YONYOU_APP_KEY=你的 app_key
YONYOU_APP_SECRET=你的 app_secret
YONYOU_ACCESS_TOKEN=你的 access_token（可选）
YONYOU_TIMEOUT=10
YONYOU_MAX_RETRIES=3
YONYOU_CACHE_TTL=300

# 金蝶 K/3 配置
KINGDEE_BASE_URL=https://api.kingdee.com/K3Cloud
KINGDEE_DB_ID=你的账套 ID

# SAP 配置
SAP_BASE_URL=https://api.sap.com/erp
SAP_CLIENT=100
SAP_USER=你的用户名
SAP_PASSWORD=你的密码
```

#### 步骤 4: 测试 ERP 连接

创建测试脚本 `scripts/test_erp_adapter.py`:

```python
#!/usr/bin/env python
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Backend'))

from erp_adapters import YonyouERPAdapter

# 测试用友适配器
adapter = YonyouERPAdapter(user_id="test_user")

# 测试查询合同
contract = adapter._query_contract("CT-2026-001")
print("合同查询结果:", contract)

# 测试查询供应商
vendor = adapter._query_vendor(vendor_name="天津纺织集团")
print("供应商查询结果:", vendor)

# 测试上下文获取
context = adapter.fetch_context({
    "contract_no": "CT-2026-001",
    "vendor": "天津纺织集团"
})
print("ERP 上下文:", context)
```

运行测试：

```bash
cd F:\Enterprise-Intelligent-Office-Agent-2.0
python scripts/test_erp_adapter.py
```

#### 步骤 5: 根据实际 ERP 调整接口

**重要**: 示例代码使用的是通用接口格式，实际使用时需要根据你公司的 ERP 版本调整：

- **用友 NC65**: 需要调整 API 路径和参数格式
- **用友 U8**: 使用 U8 OpenAPI
- **金蝶 K/3 Cloud**: 使用金蝶标准 WebAPI
- **SAP**: 使用 RFC 或 OData 服务

建议联系 ERP 供应商获取最新的 API 文档。

---

## 任务 3: 开发审单工作台前端

### 📁 涉及文件

- `frontend/src/pages/AuditWorkbench.jsx` - 审单工作台页面（✅ 已创建）
- `frontend/src/App.jsx` 或路由配置 - 需要添加路由

### 🚀 实施步骤

#### 步骤 1: 安装依赖（如果需要）

```bash
cd frontend
# 确保 MUI 已安装
npm install @mui/material @mui/icons-material @emotion/react @emotion/styled
# 确保 axios 已安装
npm install axios
```

#### 步骤 2: 添加路由

在 `frontend/src/App.jsx` 或路由配置文件中添加：

```jsx
import AuditWorkbench from './pages/AuditWorkbench';

// 在路由配置中添加
<Route path="/audit" element={<AuditWorkbench />} />
```

或者如果使用 React Router v6:

```jsx
// App.jsx
import { Routes, Route } from 'react-router-dom';
import AuditWorkbench from './pages/AuditWorkbench';

function App() {
  return (
    <Routes>
      {/* 其他路由 */}
      <Route path="/audit" element={<AuditWorkbench />} />
    </Routes>
  );
}
```

#### 步骤 3: 在导航栏添加入口

在导航组件中添加：

```jsx
import AssessmentIcon from '@mui/icons-material/Assessment';

// 在导航菜单中添加
<ListItem button component={Link} to="/audit">
  <ListItemIcon>
    <AssessmentIcon />
  </ListItemIcon>
  <ListItemText primary="审单工作台" />
</ListItem>
```

#### 步骤 4: 配置 API 代理

确保前端能访问后端 API，在 `frontend/vite.config.js` 中：

```javascript
export default {
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:18011',
        changeOrigin: true,
      }
    }
  }
}
```

#### 步骤 5: 启动测试

```bash
# 启动后端
cd Backend
python main.py

# 启动前端（新终端）
cd frontend
npm run dev
```

访问 `http://localhost:5173/audit` 查看审单工作台。

---

## 验证与测试

### ✅ 数据库验证

```sql
-- 1. 检查表数量
SELECT COUNT(*) FROM audit_jobs;
SELECT COUNT(*) FROM erp_vendors;

-- 2. 插入测试数据
INSERT INTO audit_jobs (job_id, user_id, doc_type, status, file_url, file_name)
VALUES ('test-001', 'user123', 'invoice', 'pending', '/test.pdf', '测试发票.pdf');

-- 3. 查询测试数据
SELECT * FROM audit_jobs WHERE job_id = 'test-001';
```

### ✅ 后端 API 测试

使用 curl 或 Postman 测试：

```bash
# 获取审单任务列表
curl http://localhost:18011/api/admin/audit/records

# 获取任务详情
curl http://localhost:18011/api/audit/test-001

# 上传审单文件
curl -X POST http://localhost:18011/api/audit/start \
  -F "file=@/path/to/invoice.pdf" \
  -F "doc_type=invoice" \
  -F "user_id=test_user"
```

### ✅ 前端功能测试

1. **页面加载**: 访问 `/audit` 应显示审单工作台
2. **数据展示**: 应能看到审单任务列表
3. **筛选功能**: 状态/风险等级筛选应正常工作
4. **详情查看**: 点击"查看详情"应显示完整信息
5. **人工复核**: 复核对话框应能正常提交

---

## 常见问题

### ❓ Q1: 数据库表创建失败

**A**: 检查以下几点：
1. 确保有创建表的权限
2. 检查是否已存在同名的表
3. 查看 Supabase 日志获取详细错误信息

### ❓ Q2: ERP 连接失败

**A**: 
1. 检查网络连接
2. 验证 API Key/Secret 是否正确
3. 确认 ERP 系统是否允许外部访问
4. 查看防火墙设置

### ❓ Q3: 前端页面空白

**A**:
1. 打开浏览器开发者工具查看错误
2. 确保后端 API 正常运行
3. 检查 API 代理配置
4. 清除浏览器缓存

### ❓ Q4: 审单任务卡住不动

**A**:
1. 检查 Redis/RQ 是否正常运行
2. 查看后端日志 `Backend/.runlogs/`
3. 确认 OCR 引擎正常加载
4. 检查文件路径是否正确

---

## 📞 技术支持

如果在实施过程中遇到问题：

1. 查看项目日志：`Backend/.runlogs/`
2. 检查数据库状态：Supabase Dashboard
3. 联系项目维护者
4. 查阅官方文档：https://docs.openclaw.ai

---

## 🎉 完成清单

- [ ] 数据库表创建成功
- [ ] Mock 数据插入成功
- [ ] ERP 适配器配置完成
- [ ] ERP 连接测试通过
- [ ] 前端路由配置完成
- [ ] 审单工作台页面可访问
- [ ] 任务列表正常显示
- [ ] 详情查看功能正常
- [ ] 人工复核功能正常
- [ ] 所有测试通过

**恭喜！高优先级改进完成！** 🎊

---

*文档最后更新：2026-03-19*  
*维护者：小猫娘 🐱*
