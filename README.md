# Imagine-Agent-2.0 企业智能办公助手

Imagine-Agent-2.0 是一个面向企业办公场景的多模态智能工作台。当前代码已经覆盖统一对话、知识库检索、数据库自然语言查询、OCR 与结构化录入、印章提取、语音转写、审单、报告/邮件/PPT 生成、决策看板、任务中心、分享协作和后台管理。

后端基于 FastAPI，前端基于 React + Vite，支持本地 Ollama 与云端 DeepSeek 双模型后端，适合本地部署、内网部署和持续迭代。

## 功能总览

| 模块 | 当前能力 | 关键代码 |
| --- | --- | --- |
| 统一对话 | 通用对话、数据库模式、RAG 模式、联网搜索、审单模式、流式输出、历史会话、会话反馈 | `Backend/chat_router.py` |
| 文档知识库 | 文档上传任务、分块向量化、共享/私有检索、来源展示 | `Backend/documents_processing.py` `Backend/document_upload_tasks.py` |
| 数据库查询 | 自然语言转 SQL、11 张白名单表、安全校验、完整 Excel 导出、对话仅预览前 10 行 | `Backend/database_manager.py` |
| OCR | OCR 识别、结构化解析、结构化录入、OCR 结果继续追问 | `Backend/main.py` `Backend/ocr_manager.py` `Backend/ocr_structured.py` |
| 印章提取 | 从图片或扫描件提取透明背景电子章，支持任务化追踪 | `Backend/seal_extractor.py` `Backend/seal_task_manager.py` |
| 语音 | 长音频异步转写、短音频即时转写、回放链接、任务重试 | `Backend/voice_files_processing.py` `Backend/voice_manager.py` |
| 写作 | 报告大纲、邮件草稿、PPT 内容规划 | `Backend/report_email_manager.py` |
| 演示文稿 | Presenton 模板目录、模板导入、同步/异步 PPT 生成、在线预览与下载 | `Backend/presentation_router.py` |
| 审单 | 审单任务、规则引擎、历史相似案例、异常检测、ERP 上下文、后台复核 | `Backend/audit_pipeline.py` `Backend/audit_router.py` `Backend/admin_router.py` |
| 决策中心 | 销售、采购、库存、人员等经营看板与 AI 分析 | `Backend/decision_router.py` |
| 任务中心 | 聚合审单、OCR、印章、语音、PPT 任务，支持详情与重试 | `Backend/tasks_router.py` |
| 用户与权限 | Supabase 登录、短信验证码、刷新令牌、头像代理、用户资料、后台用户管理 | `Backend/auth_router.py` `Backend/admin_router.py` |
| 分享协作 | 会话分享、公开分享页、审单源文件公开访问 | `Backend/main.py` `Backend/share_manager.py` |

## 技术栈

- 前端：React 19、Vite 7、React Lazy、Supabase JS、Markdown/KaTeX/Mermaid 渲染
- 后端：FastAPI、Pydantic、SQLAlchemy、httpx、requests
- 大模型：Ollama 本地模型、DeepSeek API
- 数据与存储：Supabase Auth、Postgres、Storage
- OCR：PaddleOCR、PaddleX
- 文档检索：LangChain、HuggingFace Embeddings、本地 BGE 向量模型
- 办公扩展：Presenton PPT 服务、百度语音识别、阿里云短信认证

## 主要页面

- `/`：官网落地页
- `/capabilities`：能力清单页
- `/quickstart`：快速开始页
- `/share/{token}`：公开分享会话页
- 登录后主工作台：统一对话、文档、数据库、OCR、写作、语音、印章等入口
- `/decision`：决策中心
- `/tasks`：任务中心
- `/admin`：后台管理页

## 项目结构

```text
.
├── Backend/
│   ├── main.py                    # FastAPI 入口，挂载各业务路由
│   ├── app_settings.py            # 统一读取 Backend/.env 与 Backend/.env.local
│   ├── chat_router.py             # 对话、历史、反馈
│   ├── documents_processing.py    # 文档解析、分块、向量检索
│   ├── document_upload_tasks.py   # 文档上传任务
│   ├── database_manager.py        # NL2SQL、安全校验、Excel 导出
│   ├── ocr_manager.py             # OCR 主流程
│   ├── ocr_structured.py          # OCR 结构化解析与入库字段
│   ├── seal_extractor.py          # 印章提取
│   ├── voice_files_processing.py  # 语音任务与存储
│   ├── voice_manager.py           # 语音识别
│   ├── report_email_manager.py    # 报告/邮件/PPT 内容生成
│   ├── presentation_router.py     # Presenton PPT 集成
│   ├── audit_pipeline.py          # 审单核心逻辑
│   ├── audit_router.py            # 审单接口
│   ├── decision_router.py         # 决策看板接口
│   ├── tasks_router.py            # 任务中心接口
│   ├── auth_router.py             # 登录、注册、密码、头像
│   ├── admin_router.py            # 后台管理
│   ├── history_manager.py         # 会话上下文存储
│   └── runtime_storage.py         # 运行期文件目录与清理
├── frontend/
│   ├── src/App.jsx
│   ├── src/pages/Dashboard/       # 主工作台
│   ├── src/pages/Admin/           # 后台
│   ├── src/pages/DecisionCenterPage.jsx
│   ├── src/pages/TaskCenterPage.jsx
│   ├── src/api/                   # 前端 API 封装
│   └── vite.config.js             # 代理、分包、公开配置注入
├── tools/
│   ├── prod-server.mjs            # 前端生产静态服务 + /api 反向代理
│   ├── migrate_supabase_api_fallback.py
│   └── migrate_supabase_storage.py
├── rebuild-prod.bat               # Windows 一键重建并启动
├── start-prod.bat                 # Windows 启动脚本
├── stop-prod.bat                  # Windows 停止脚本
└── requirements.txt
```

## 环境要求

- Python 3.10+
- Node.js 18+
- Git
- Ollama
  说明：需要本地模型时使用；只走云端模型可不启用
- Docker Desktop + Supabase CLI
  说明：需要本地 Supabase 时使用；也可以改为连接你自己的 Supabase 环境
- Windows
  说明：仓库内现成的生产脚本为 `.bat`；开发模式本身不依赖 Windows

## 安装

### 1. 克隆项目

```bash
git clone https://github.com/qianxiaanran/Imagine-Agent-2.0.git
cd Imagine-Agent-2.0
```

### 2. 安装后端依赖

```bash
python -m venv Backend/.venv
Backend\.venv\Scripts\python.exe -m pip install --upgrade pip
Backend\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 3. 安装前端依赖

```bash
cd frontend
npm install
cd ..
```

### 4. 准备本地 Embedding 模型

项目默认使用本地 `bge-small-zh-v1.5`。将模型目录放在项目根目录或按你的实际路径调整文档检索相关配置。

```text
Imagine-Agent-2.0/
└── bge-small-zh-v1.5/
```

## 配置方式

### 密钥与运行配置

当前代码已经把敏感配置统一收口到后端：

- 统一入口：`Backend/app_settings.py`
- 本地配置文件：`Backend/.env.local`
- 前端不会再在源码里写具体 key
- 前端需要的 Supabase 公开配置会在构建时由 `frontend/vite.config.js` 从 `Backend/.env.local` 注入

也就是说：

- 功能文件和界面文件不应该写死 API key
- 真正的密钥只放在 `Backend/.env.local`
- `Backend/.env.local` 不应提交到 Git

### 推荐的 `Backend/.env.local` 示例

```env
# Supabase
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_ANON_KEY=your-supabase-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-supabase-service-role-key
SUPABASE_DB_HOST=127.0.0.1
SUPABASE_DB_PORT=54322
SUPABASE_DB_USER=postgres
SUPABASE_DB_PASSWORD=your-db-password
SUPABASE_DB_NAME=postgres
SUPABASE_DB_SSLMODE=disable

# LLM
DEEPSEEK_URL=https://api.deepseek.com
DEEPSEEK_KEY=your-deepseek-key
DEEPSEEK_MODEL_NAME=deepseek-chat
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_API_BASE=http://127.0.0.1:11434
LLM_MODEL_NAME=qwen2.5-coder

# Voice / SMS
BAIDU_APP_ID=your-baidu-app-id
BAIDU_API_KEY=your-baidu-api-key
BAIDU_SECRET_KEY=your-baidu-secret-key
ALIYUN_ACCESS_KEY_ID=your-aliyun-access-key-id
ALIYUN_ACCESS_KEY_SECRET=your-aliyun-access-key-secret

# Optional search providers
SERPER_API_KEY=your-serper-key
SERPAPI_API_KEY=your-serpapi-key
TAVILY_API_KEY=your-tavily-key
BING_SEARCH_V7_KEY=your-bing-key

# Optional PPT service
PRESENTON_BASE_URL=http://127.0.0.1:5000
PRESENTON_API_KEY=your-presenton-key
```

## 开发模式启动

### 启动后端

```bash
cd Backend
.venv\Scripts\python.exe main.py
```

默认地址：

- 后端：`http://127.0.0.1:18011`
- 健康检查：`http://127.0.0.1:18011/health`

### 启动前端

```bash
cd frontend
npm run dev
```

默认地址：

- 前端：`http://127.0.0.1:5173`

## Windows 生产脚本

仓库已经带了完整的 Windows 脚本链路。

### 一键重建并启动

```bat
rebuild-prod.bat
```

行为：

- 停掉现有前后端进程
- 检查 `frontend/package-lock.json` 是否变化
- 需要时自动执行 `npm install`
- 执行 `npm run build`
- 再调用 `start-prod.bat`

如果你想连 Supabase 一起完整重启：

```bat
rebuild-prod.bat --full
```

### 仅启动服务

```bat
start-prod.bat
```

默认行为：

- 读取 `Backend/.env.local` 里的 Ollama 配置
- 检查并尝试拉起 Ollama
- 如果存在 `supabase/config.toml`，检查并尝试拉起本地 Supabase
- 启动后端 `Backend/main.py`
- 用 `tools/prod-server.mjs` 启动前端静态服务并代理 `/api`

默认地址：

- 前端：`http://127.0.0.1:8080`
- 后端：`http://127.0.0.1:18011`
- Supabase API：`http://127.0.0.1:54321`
- Supabase Studio：`http://127.0.0.1:54323`

可选：

- `start-prod.bat 8080 18011`
- 设置 `FRONTEND_HOST=0.0.0.0` 后可供局域网访问

### 停止服务

```bat
stop-prod.bat
```

默认会停止前端、后端和相关监听端口。传 `--keep-supabase` 可保留本地 Supabase。

## 核心工作流

### 1. 对话工作台

- 支持通用、数据库、RAG、OCR、审单、写作等统一入口
- 支持会话历史、改标题、置顶、删除、分享、反馈
- 支持公开分享页查看上下文快照

### 2. 文档知识库

- 支持 `PDF`、`DOCX`、`TXT`
- 兼容旧式 `.doc`，但需要系统具备 `antiword/catdoc` 或先转换为 `.docx`
- 上传采用任务化处理，可轮询 `/api/documents/upload/result/{task_id}`
- 检索支持共享知识库和私有上下文

### 3. 数据库查询

- 当前白名单表共 11 张：`company_info`、`departments`、`roles`、`employees`、`customers`、`suppliers`、`products`、`inventory`、`orders`、`order_items`、`purchases`
- 只允许只读 SQL
- 会自动做表白名单校验和危险语句拦截
- 查询结果会导出完整 Excel
- 对话正文默认只展示前 10 行预览，并提示总行数
- 用户明确要求 `TOP N`、`前 N 条` 时会保留用户限行

### 4. OCR 与结构化录入

- `POST /api/ocr/recognize`：原始 OCR
- `POST /api/ocr/parse`：结构化解析
- `POST /api/ocr/submit`：结构化结果入库
- `POST /api/ocr/ingest`：OCR 内容继续进入对话上下文
- 当前结构化文档类型覆盖采购合同、销售合同、发票、通用合同、通用文档等

### 5. 印章提取

- `POST /api/ocr/seal-extract`
- 支持从扫描件中定位印章区域
- 支持透明背景结果、压缩包结果和任务详情回查

### 6. 语音转写

- `POST /api/voice/transcribe`：长音频异步任务
- `POST /api/voice/instant`：短音频即时返回文本
- `POST /api/voice/transcribe_supabase`：已有 Storage 文件发起转写
- `GET /api/voice/result/{task_id}`：查看结果
- `GET /api/voice/playback_url`：生成回放链接

### 7. 写作与 PPT

- `POST /api/generate/report`：报告大纲
- `POST /api/generate/email`：邮件草稿
- `POST /api/presentation/presenton/outline/generate`：PPT 内容规划
- `POST /api/presentation/presenton/generate`：同步生成
- `POST /api/presentation/presenton/generate/async`：异步生成
- 支持模板目录、模板导入、在线嵌入预览与下载

### 8. 审单与后台

- `POST /api/audit/start`：发起审单
- `GET /api/audit/{job_id}`：查看审单结果
- `POST /api/audit/{job_id}/erp-action`：执行 ERP 侧动作
- 后台支持审单记录、规则管理、知识库文档审批、任务管理、日志查看、用户角色与状态管理

### 9. 决策中心与任务中心

- 决策中心接口：
  - `GET /api/decision/overview`
  - `GET /api/decision/data`
  - `GET /api/decision/ai`
  - `GET /api/decision/drilldown`
- 任务中心接口：
  - `GET /api/tasks/overview`
  - `GET /api/tasks/overview/{task_id}`
  - `POST /api/tasks/overview/{task_id}/retry`

## 主要 API 一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 服务健康检查 |
| POST | `/api/chat` | 统一对话入口 |
| GET | `/api/history/sessions` | 会话列表 |
| GET | `/api/history/{session_id}` | 会话详情 |
| PATCH | `/api/history/{session_id}/title` | 改标题 |
| PATCH | `/api/history/{session_id}/pin` | 置顶/取消置顶 |
| DELETE | `/api/history/{session_id}` | 删除会话 |
| POST | `/api/share/create` | 创建分享链接 |
| GET | `/api/public/share/{token}` | 获取公开分享内容 |
| POST | `/api/documents/upload` | 提交文档上传任务 |
| GET | `/api/documents/upload/result/{task_id}` | 获取文档上传结果 |
| POST | `/api/ocr/recognize` | OCR 识别 |
| POST | `/api/ocr/parse` | OCR 结构化解析 |
| POST | `/api/ocr/submit` | OCR 结构化入库 |
| POST | `/api/ocr/seal-extract` | 印章提取 |
| POST | `/api/voice/transcribe` | 长音频异步转写 |
| POST | `/api/voice/instant` | 短音频即时转写 |
| POST | `/api/voice/transcribe_supabase` | Supabase 文件转写 |
| POST | `/api/generate/report` | 生成报告大纲 |
| POST | `/api/generate/email` | 生成邮件草稿 |
| POST | `/api/presentation/presenton/generate/async` | 异步生成 PPT |
| GET | `/api/tasks/overview` | 任务列表 |
| GET | `/api/decision/overview` | 决策总览 |
| POST | `/api/audit/start` | 发起审单 |
| POST | `/api/auth/login` | 登录 |
| POST | `/api/auth/register` | 注册 |
| POST | `/api/auth/send_code` | 发送验证码 |

## 当前实现中的关键约束

- 仓库代码中不应保存真实 API key；真实值只放 `Backend/.env.local`
- 前端不会在源码中保存 Supabase 明文 key
- 数据库模式只允许访问白名单业务表
- 本地生产脚本默认围绕 Windows 环境编写
- 本地 Supabase 依赖 Docker Desktop；如果不使用本地 Supabase，请改为自己的远端配置

## 常见问题

### 前端启动时报 `Missing Supabase public config`

说明 `Backend/.env.local` 中缺少：

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`

前端构建时会从后端环境文件注入这两个公开变量。

### `start-prod.bat` 启动后没有前端页面

先确认：

- `frontend/dist/index.html` 是否存在
- 是否已经执行过 `rebuild-prod.bat`
- `tools/prod-server.mjs` 是否存在

### 文档上传后无法检索

优先检查：

- 本地 BGE 模型是否存在
- Supabase 连接是否正常
- 文档上传任务是否成功完成

### 数据库查询为什么没有把所有数据直接显示在对话里

当前逻辑是：

- 完整结果导出为 Excel
- 对话正文只预览前 10 行
- 同时提示总行数

这样可以避免大结果集直接把对话刷满。

### 语音或短信功能不可用

请检查：

- 百度语音识别配置
- 阿里云短信认证配置
- 对应网络是否可访问

## 补充说明

- 这个 README 已按当前仓库代码重写，不再沿用旧版本功能清单
- 如果你继续扩展新模块，优先同步更新 `Backend/main.py`、`Backend/app_settings.py` 和本 README
