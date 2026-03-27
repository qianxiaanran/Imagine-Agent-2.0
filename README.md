# 🧠 Imagine-Agent-2.0 企业智能办公助手

[![LangChain](https://img.shields.io/badge/LangChain-00C2FF?style=for-the-badge)](https://www.langchain.com/)
[![DeepSeek](https://img.shields.io/badge/DeepSeek-LLM-blue?style=for-the-badge)](https://deepseek.com/)

Imagine-Agent-2.0 是面向企业办公场景的多模态智能助手，覆盖“对话 + 文档 + 数据 + OCR + 语音 + 审单 + 写作 + 决策”的完整流程。后端基于 FastAPI 构建，前端采用 React + Vite，支持本地 Ollama 与云端 DeepSeek 双模型后端，适合本地部署、私有化运行和持续迭代。

---

## 📋 目录
1. [项目概述](#-项目概述)
2. [功能特性](#-功能特性)
3. [技术架构](#-技术架构)
4. [安装部署](#-安装部署)
安装部署子项：
1. [环境要求](#环境要求)
2. [克隆项目](#1-克隆项目)
3. [安装依赖](#2-安装依赖)
4. [准备 Embedding 模型](#3-准备-embedding-模型)
5. [配置本地环境变量](#4-配置本地环境变量)
6. [准备本地服务](#5-准备本地服务可选)
7. [运行系统](#6-运行系统)
5. [配置文件详解](#-配置文件详解)
6. [项目结构详解](#-项目结构详解)
7. [核心模块说明](#-核心模块说明)
核心模块子项：
1. [文档处理与知识库模块](#1-文档处理与知识库模块)
2. [数据库查询模块](#2-数据库查询模块)
3. [任务中心模块](#3-任务中心模块)
4. [决策中心模块](#4-决策中心模块)
5. [OCR 与印章提取模块](#5-ocr-与印章提取模块)
6. [语音处理模块](#6-语音处理模块)
7. [写作与 PPT 模块](#7-写作与-ppt-模块)
8. [审单与风控模块](#8-审单与风控模块)
9. [鉴权与后台管理模块](#9-鉴权与后台管理模块)
8. [使用指南](#-使用指南)
使用指南子项：
1. [智能对话与知识检索](#1-智能对话与知识检索)
2. [数据库查询与 Excel 导出](#2-数据库查询与-excel-导出)
3. [语音转写与会议纪要](#3-语音转写与会议纪要)
4. [OCR 识别与印章提取](#4-ocr-识别与印章提取)
5. [报告 邮件与 PPT 生成](#5-报告-邮件与-ppt-生成)
6. [任务中心与决策看板](#6-任务中心与决策看板)
9. [API接口说明](#-api接口说明)
10. [常见问题解答](#-常见问题解答)
11. [性能优化建议](#-性能优化建议)
12. [开发计划](#-开发计划)

---

## 🏢 项目概述
Imagine-Agent-2.0 聚焦企业办公场景下的信息处理、知识检索、结构化录入与自动化产出，强调“能跑通业务流程”和“便于持续运营”。系统提供统一工作台，用户可以在同一套界面中完成文档问答、数据库查询、OCR 录入、语音转写、审单风控、PPT 生成、任务跟踪与经营决策分析。

核心定位：
- 企业智能办公助手
- 本地部署与私有化友好
- 多路由多工具统一入口
- 本地模型与云端模型可切换
- 配置与密钥集中管理

适用场景：
- 企业制度、合同、规范、知识文档问答
- 销售、库存、订单、采购等业务数据查询
- OCR 文档识别、结构化录入、印章提取
- 会议录音转写、纪要沉淀与继续追问
- 审单风控、异常检测、ERP 动作处理
- 报告、邮件、PPT 等办公内容生成
- 任务中心追踪与经营决策分析

## ✨ 功能特性
- 多模式对话：支持通用对话、知识库检索、数据库查询、联网搜索、审单等模式，统一通过 `/api/chat` 流式输出
- 文档知识库（RAG）：支持 PDF、DOCX、TXT 上传解析、向量化、分块检索与来源展示，支持共享库与私有库
- 数据库查询：自然语言转 SQL，限制在白名单业务表内执行，只允许只读查询；结果统一导出 Excel，对话中仅展示前 10 行预览并显示总行数
- OCR 识别与结构化录入：支持图片/PDF OCR、字段抽取、结构化解析、录入任务流转
- 印章提取：支持印章透明底抠图与任务化处理，前端提供专门工作区与预览
- 语音能力：支持长音频异步转写、即时转写、Supabase 存储音频转写、实时语音 WebSocket 代理与回放链接
- 写作能力：支持报告、邮件和 PPT 大纲生成，并集成 Presenton 模板目录、在线编辑、异步生成与下载
- 审单与风控：支持多类贸易单据审单、规则治理、异常记录、复核与 ERP 动作触发
- 任务中心：统一聚合审单、OCR、印章提取、语音转写、PPT 生成等任务状态，支持详情查看与部分任务重试
- 决策中心：聚合销售、采购、库存、客户、供应商、员工等经营指标，提供 AI 解读与钻取分析
- 分享与公开访问：支持会话分享链接和公开查看
- 后台管理：支持用户管理、角色状态调整、知识库治理、日志查看、审单规则维护

## 🏗️ 技术架构
关键组件：
- 前端：React + Vite，包含 Landing、Capabilities、QuickStart、Dashboard、Decision Center、Task Center、Admin 等页面
- 后端：FastAPI，多路由拆分，统一对外提供 `/api/*` 接口
- 模型层：本地 Ollama 与云端 DeepSeek API 双后端切换
- 检索层：BGE Embedding + 向量化分块 + 知识库检索
- OCR 层：PaddleOCR / OpenCV，支持识别、结构化解析、印章提取
- 数据层：Supabase Postgres + Storage，兼容本地 Supabase 启动脚本
- 任务层：本地任务注册表 + 任务中心聚合视图

简化架构示意：
```text
前端（React + Vite）
  ├─ Dashboard：对话 / 文档 / 数据库 / OCR / 写作 / 印章提取
  ├─ /decision：经营决策中心
  ├─ /tasks：统一任务中心
  ├─ /admin：后台管理
  └─ /share/{token}：公开分享页

后端（FastAPI）
  ├─ chat_router              多模式对话与历史会话
  ├─ documents_processing     文档解析、分块、Embedding、检索
  ├─ database_manager         SQL 生成、安全校验、Excel 导出
  ├─ ocr_*                    OCR、结构化录入、印章提取
  ├─ voice_*                  音频转写、实时代理、结果回查
  ├─ presentation_router      Presenton PPT 生成与模板代理
  ├─ audit_*                  审单风控与复核流
  ├─ tasks_router             统一任务聚合与重试
  ├─ decision_router          经营看板与 AI 分析
  └─ auth/admin routers       登录鉴权、用户中心、后台治理
```

## 📦 安装部署

### 环境要求
- Python 3.10+
- Node.js 18+
- Git
- Docker Desktop（可选，本地 Supabase 需要）
- CUDA / GPU（可选，用于本地模型、OCR、Embedding 加速）

### 1 克隆项目
```bash
git clone https://github.com/qianxiaanran/Imagine-Agent-2.0.git
cd Imagine-Agent-2.0
```

### 2 安装依赖
```bash
cd Backend
python -m venv .venv
.venv\Scripts\activate
pip install -r ..\requirements.txt

cd ..\frontend
npm install
```

### 3 准备 Embedding 模型
将 `bge-small-zh-v1.5` 放在项目根目录，供文档向量化使用：

```text
./bge-small-zh-v1.5/
```

如你的模型路径不同，请同步检查 `Backend/documents_processing.py` 中本地模型路径配置。

### 4 配置本地环境变量
当前项目的密钥与运行配置统一由 `Backend/app_settings.py` 读取。建议把真实配置写入：

```text
Backend/.env.local
```

常见变量示例：

```bash
# LLM
DEEPSEEK_URL=https://api.deepseek.com
DEEPSEEK_KEY=sk-xxx
DEEPSEEK_MODEL_NAME=deepseek-chat
OLLAMA_BASE_URL=http://127.0.0.1:11434

# Supabase / Postgres
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_ANON_KEY=your-public-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_DB_HOST=127.0.0.1
SUPABASE_DB_PORT=54322
SUPABASE_DB_USER=postgres
SUPABASE_DB_PASSWORD=postgres
SUPABASE_DB_NAME=postgres

# 语音转写（百度）
BAIDU_APP_ID=your-baidu-app-id
BAIDU_API_KEY=your-baidu-api-key
BAIDU_SECRET_KEY=your-baidu-secret-key

# 短信登录（阿里云）
ALIYUN_ACCESS_KEY_ID=your-aliyun-ak
ALIYUN_ACCESS_KEY_SECRET=your-aliyun-sk

# 搜索 / 联网
SERPER_API_KEY=your-serper-key
SERPAPI_API_KEY=your-serpapi-key
TAVILY_API_KEY=your-tavily-key

# Presenton
PRESENTON_BASE_URL=http://127.0.0.1:5000
PRESENTON_API_KEY=your-presenton-key
```

说明：
- `Backend/.env` 可放默认配置，`Backend/.env.local` 会覆盖默认值
- 前端公开配置通过 `frontend/vite.config.js` 从后端环境读取，不需要在前端源码中硬编码具体 key
- 不要把真实 `.env.local` 提交到 Git 仓库

### 5 准备本地服务（可选）
- 如使用本地 Ollama，请提前确保 `ollama serve` 可用
- 如项目根目录存在 `supabase/config.toml`，`start-prod.bat` 会尝试自动启动本地 Supabase
- 数据库查询依赖 Supabase Postgres 连接，具体白名单业务表定义在 `Backend/database_manager.py`

### 6 运行系统
开发模式：

```bash
# 后端
cd Backend
python main.py

# 前端
cd frontend
npm run dev
```

默认地址：
- 后端：`http://127.0.0.1:18011`
- 前端：`http://127.0.0.1:5173`

生产脚本：

```bash
rebuild-prod.bat
start-prod.bat
stop-prod.bat
```

脚本说明：
- `rebuild-prod.bat`：重新构建前端并重启服务，`--full` 时会连同 Supabase 一起重启
- `start-prod.bat`：检查并启动 Ollama、本地 Supabase、后端和前端静态服务
- `stop-prod.bat`：停止 8080、18001、18011 端口相关服务，可选保留 Supabase

生产脚本默认地址：
- 前端：`http://127.0.0.1:8080`
- 后端：`http://127.0.0.1:18011`
- Supabase API：`http://127.0.0.1:54321`
- Supabase Studio：`http://127.0.0.1:54323`

## ⚙️ 配置文件详解
- `Backend/app_settings.py`：统一读取 `.env` 与 `.env.local`，集中管理 DeepSeek、Supabase、百度、阿里云、搜索服务、Presenton 等配置
- `Backend/config.py`：系统常量、提示词模板、业务开关与运行参数
- `Backend/deepseek_llm.py`：本地 Ollama 与云端 DeepSeek 模型接入、流式生成与统一调用
- `Backend/documents_processing.py`：文档解析、Embedding、向量检索、知识库索引与格式支持
- `Backend/database_manager.py`：数据库提示词、白名单表、只读校验、显式 Top N 控制、Excel 导出与预览逻辑
- `Backend/ocr_manager.py` / `Backend/ocr_structured.py` / `Backend/seal_extractor.py`：OCR 识别、结构化录入、印章提取
- `Backend/voice_manager.py` / `Backend/voice_files_processing.py` / `Backend/voice_ws_proxy.py`：即时转写、异步转写、实时语音代理与结果回查
- `Backend/presentation_router.py`：Presenton 模板目录、PPT 大纲生成、异步生成、在线编辑代理与下载
- `Backend/tasks_router.py`：任务中心聚合接口，统一汇总 `audit / ocr / seal / voice / ppt`
- `Backend/decision_router.py`：经营数据预聚合、AI 分析缓存、趋势钻取接口
- `start-prod.bat` / `rebuild-prod.bat` / `stop-prod.bat`：本地生产化启动、重建、停止脚本
- `frontend/vite.config.js`：前端构建配置、API 代理、环境变量注入

## 🗂️ 项目结构详解
```text
.
├── Backend/                          # FastAPI 后端
│   ├── main.py                       # 应用入口、静态挂载、启动时预热
│   ├── app_settings.py               # 统一环境变量与密钥读取
│   ├── chat_router.py                # 多模式对话、历史会话、反馈
│   ├── auth_router.py                # 注册、登录、验证码、用户资料
│   ├── admin_router.py               # 后台治理、用户管理、知识库治理
│   ├── audit_router.py               # 审单任务接口
│   ├── audit_pipeline.py             # 审单规则、异常检测与结果处理
│   ├── decision_router.py            # 决策中心聚合数据与 AI 解读
│   ├── tasks_router.py               # 任务中心接口
│   ├── documents_processing.py       # 文档解析、向量化、知识库检索
│   ├── database_manager.py           # SQL 生成、安全校验、Excel 导出
│   ├── ocr_manager.py                # OCR 主流程
│   ├── ocr_structured.py             # OCR 结构化抽取与录入
│   ├── seal_extractor.py             # 印章提取与透明底输出
│   ├── presentation_router.py        # Presenton PPT 生成与代理
│   ├── report_email_manager.py       # 报告、邮件、PPT 内容生成
│   ├── voice_manager.py              # 即时语音转写与接口协调
│   ├── voice_files_processing.py     # 音频文件异步转写
│   ├── voice_ws_proxy.py             # 实时语音 WebSocket 代理
│   └── runtime_storage.py            # 运行期文件目录与产物管理
├── frontend/                         # React 前端
│   ├── src/App.jsx                   # 路由入口、鉴权切换、页面装载
│   ├── src/pages/LandingPage.jsx     # 首页
│   ├── src/pages/CapabilitiesPage.jsx# 能力介绍页
│   ├── src/pages/QuickStartPage.jsx  # 快速开始页
│   ├── src/pages/Dashboard/          # 主工作台与功能面板
│   ├── src/pages/DecisionCenterPage.jsx # 决策中心
│   ├── src/pages/TaskCenterPage.jsx  # 任务中心
│   ├── src/pages/Admin/              # 后台管理
│   ├── src/pages/Login/              # 登录注册
│   ├── src/api/                      # 接口封装与 Supabase 客户端
│   └── src/components/               # 通用组件与全局样式
├── tools/prod-server.mjs             # 前端生产静态服务与 API 代理
├── start-prod.bat                    # 本地生产启动脚本
├── rebuild-prod.bat                  # 重建并启动
├── stop-prod.bat                     # 停止脚本
├── requirements.txt                  # Python 依赖
├── frontend/package.json             # 前端依赖与脚本
└── README.md
```

## 🔧 核心模块说明

### 1 文档处理与知识库模块
- 入口：`Backend/documents_processing.py`
- 能力：PDF / DOCX / TXT 解析、分块、Embedding、向量检索、知识库写入
- 特点：支持共享知识库与用户私有知识库，回答中可回传来源文件
- 说明：`.doc` 需依赖系统转换工具，推荐优先使用 `.docx`

### 2 数据库查询模块
- 入口：`Backend/database_manager.py`
- 能力：自然语言转 SQL、白名单表过滤、只读校验、结果格式化
- 当前策略：明确 `TOP N / 前 N 条` 时按用户要求限行；查询结果统一导出单个 Excel；对话中仅展示前 10 行预览并提示总行数
- 数据范围：聚焦客户、订单、采购、库存、员工、部门、产品等业务表

### 3 任务中心模块
- 入口：`Backend/tasks_router.py`
- 能力：统一汇总 `audit / ocr / seal / voice / ppt` 任务
- 接口：支持列表、详情、按任务类型筛选、部分任务重试
- 目标：把异步能力收口到同一视图，方便查看状态与结果链接

### 4 决策中心模块
- 入口：`Backend/decision_router.py`
- 能力：销售、采购、库存、客户、供应商、员工等经营数据聚合与 AI 经营分析
- 特点：支持趋势粒度切换、下钻分析、缓存预聚合、AI 分析异步刷新
- 适用：经营周报、月报、风险提示、管理层数据看板

### 5 OCR 与印章提取模块
- 入口：`Backend/ocr_manager.py`、`Backend/ocr_structured.py`、`Backend/seal_extractor.py`
- 能力：图片/PDF OCR、结构化字段提取、结构化录入、印章透明底提取
- 配套前端：工作台内置 OCR 解析面板与印章提取工作区
- 输出：结构化字段结果、预览图片、任务记录与下载产物

### 6 语音处理模块
- 入口：`Backend/voice_manager.py`、`Backend/voice_files_processing.py`、`Backend/voice_ws_proxy.py`
- 能力：长音频异步转写、即时转写、Supabase 存储转写、实时语音 WebSocket 代理
- 配套能力：回放地址获取、转写结果轮询、会议纪要继续追问

### 7 写作与 PPT 模块
- 入口：`Backend/report_email_manager.py`、`Backend/presentation_router.py`
- 能力：报告、邮件、PPT 提纲生成，Presenton 模板目录读取、模板导入、在线编辑、异步生成与下载
- 特点：PPT 任务会进入统一任务中心，支持状态查询与结果回链

### 8 审单与风控模块
- 入口：`Backend/audit_router.py`、`Backend/audit_pipeline.py`
- 能力：审单任务发起、单据规则校验、异常识别、案例详情查看、ERP 动作触发
- 管理后台配套：规则读取与更新、审单记录、人工复核、任务再执行

### 9 鉴权与后台管理模块
- 入口：`Backend/auth_router.py`、`Backend/admin_router.py`
- 能力：短信验证码、注册登录、刷新令牌、资料修改、头像处理、管理员后台治理
- 管理能力：用户 CRUD、角色与状态调整、强制下线、日志查看、知识库治理、审单规则维护
- 前端：`/admin`、`/decision`、`/tasks` 为受保护页面

## 📖 使用指南

### 1 智能对话与知识检索
1. 登录后进入工作台
2. 在通用或文档检索场景上传 PDF / DOCX / TXT
3. 等待文档解析完成后继续提问
4. 系统会结合知识库内容生成回答，并在来源区展示关联文件

### 2 数据库查询与 Excel 导出
1. 进入数据库查询模式，或在自动路由中直接提出业务数据问题
2. 使用自然语言输入，例如“查询销售订单金额 TOP20 客户，并按客户汇总”
3. 系统会自动生成并校验只读 SQL
4. 完整结果统一导出为 Excel；对话中只显示总行数和前 10 行预览

### 3 语音转写与会议纪要
1. 上传音频文件，或选择已有 Supabase 存储音频
2. 根据场景选择即时转写或异步转写
3. 轮询结果页或在任务中心查看完成状态
4. 基于转写结果继续生成纪要、总结或追问

### 4 OCR 识别与印章提取
1. 上传图片或 PDF
2. 选择 OCR 识别、结构化解析或印章提取
3. 查看识别文本、结构化字段和提取产物
4. 如为结构化录入任务，可继续走录入和后续处理流程

### 5 报告 邮件与 PPT 生成
1. 在工作台输入报告、邮件或 PPT 生成意图
2. 系统会生成对应大纲或内容结构
3. PPT 任务可选择模板并进入 Presenton 生成链路
4. 完成后可在线编辑、下载产物，或在任务中心查看状态

### 6 任务中心与决策看板
1. 打开 `/tasks` 查看 OCR、审单、印章、语音、PPT 等异步任务
2. 需要时查看详情或重试支持的任务
3. 打开 `/decision` 查看经营指标、趋势图、风险预警与 AI 解读
4. 结合下钻分析定位客户、SKU、库存或回款异常

## 🌐 API接口说明

常用接口一览：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/chat` | 多模式对话流式输出 |
| GET | `/api/history/sessions` | 获取会话列表 |
| GET | `/api/history/{session_id}` | 获取会话详情 |
| DELETE | `/api/history/{session_id}` | 删除会话 |
| PATCH | `/api/history/{session_id}/title` | 修改会话标题 |
| PATCH | `/api/history/{session_id}/pin` | 会话置顶 |
| GET | `/api/chat/feedback/{session_id}` | 获取反馈记录 |
| POST | `/api/chat/feedback` | 提交对话反馈 |

文档、OCR、语音与分享接口：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/documents/upload` | 上传文档并进入知识库处理 |
| GET | `/api/documents/upload/result/{task_id}` | 获取文档上传处理结果 |
| POST | `/api/ocr/recognize` | OCR 识别 |
| POST | `/api/ocr/ingest` | OCR 结构化录入 |
| POST | `/api/ocr/parse` | OCR 结构化解析 |
| POST | `/api/ocr/submit` | OCR 结构化提交 |
| POST | `/api/ocr/seal-extract` | 印章提取 |
| POST | `/api/voice/transcribe` | 长音频异步转写 |
| POST | `/api/voice/instant` | 即时语音转写 |
| POST | `/api/voice/transcribe_supabase` | 基于 Supabase 路径的语音转写 |
| GET | `/api/voice/result/{task_id}` | 获取转写结果 |
| GET | `/api/voice/playback_url` | 获取回放地址 |
| POST | `/api/share/create` | 创建分享链接 |
| GET | `/api/public/share/{token}` | 访问分享内容 |

鉴权、任务、决策与 PPT 接口：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/send_code` | 发送验证码 |
| POST | `/api/auth/register` | 注册 |
| POST | `/api/auth/login` | 登录 |
| POST | `/api/auth/refresh` | 刷新令牌 |
| POST | `/api/auth/reset_password` | 重置密码 |
| POST | `/api/auth/check_account` | 检查账号状态 |
| GET | `/api/user/profile` | 获取个人资料 |
| PUT | `/api/user/profile` | 更新个人资料 |
| PUT | `/api/user/password` | 修改密码 |
| POST | `/api/user/avatar` | 上传头像 |
| GET | `/api/tasks/overview` | 获取任务中心列表 |
| GET | `/api/tasks/overview/{task_id}` | 获取任务详情 |
| POST | `/api/tasks/overview/{task_id}/retry` | 重试支持的任务 |
| GET | `/api/decision/overview` | 获取决策中心总览 |
| GET | `/api/decision/data` | 获取决策数据 |
| GET | `/api/decision/ai` | 获取 AI 经营分析 |
| GET | `/api/decision/drilldown` | 获取下钻分析 |
| POST | `/api/presentation/presenton/outline/generate` | 生成 PPT 大纲 |
| GET | `/api/presentation/presenton/template/catalog` | 获取模板目录 |
| GET | `/api/presentation/presenton/template/imported` | 获取已导入模板 |
| POST | `/api/presentation/presenton/template/import` | 导入模板 |
| DELETE | `/api/presentation/presenton/template/import/{template_id}` | 删除导入模板 |
| POST | `/api/presentation/presenton/generate` | 同步生成 PPT |
| POST | `/api/presentation/presenton/generate/async` | 异步生成 PPT |
| GET | `/api/presentation/presenton/generate/status/{task_id}` | 查询 PPT 任务状态 |
| GET | `/api/presentation/presenton/download` | 下载 PPT |
| GET | `/api/presentation/presenton/embed` | 内嵌在线编辑页 |

审单与后台接口：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/audit/start` | 发起审单任务 |
| GET | `/api/audit/{job_id}` | 获取审单结果 |
| GET | `/api/public/audit/source` | 获取公开审单来源 |
| GET | `/api/audit/case/{case_id}` | 获取审单案例详情 |
| POST | `/api/audit/{job_id}/erp-action` | 执行 ERP 动作 |
| GET | `/api/admin/users` | 用户列表 |
| POST | `/api/admin/users` | 创建用户 |
| POST | `/api/admin/users/{user_id}/role` | 修改角色 |
| POST | `/api/admin/users/{user_id}/status` | 修改状态 |
| POST | `/api/admin/users/{user_id}/force_logout` | 强制下线 |
| DELETE | `/api/admin/users/{user_id}` | 删除用户 |
| GET | `/api/admin/audit/records` | 审单记录列表 |
| GET | `/api/admin/audit/records/{job_id}` | 审单记录详情 |
| POST | `/api/admin/audit/review` | 提交审单复核 |
| GET | `/api/admin/audit/rules/{doc_type}` | 获取审单规则 |
| PUT | `/api/admin/audit/rules/{doc_type}` | 更新审单规则 |
| GET | `/api/admin/jobs` | 后台任务列表 |
| POST | `/api/admin/jobs/{job_id}/cancel` | 取消任务 |
| POST | `/api/admin/jobs/{job_id}/retry` | 重试任务 |
| GET | `/api/admin/kb/documents` | 知识库文档列表 |
| POST | `/api/admin/kb/documents/approve` | 审核通过文档 |
| POST | `/api/admin/kb/documents/delete` | 删除知识库文档 |
| POST | `/api/admin/kb/documents/reindex` | 重建知识库索引 |
| GET | `/api/admin/logs` | 获取后台日志 |

## ❓ 常见问题解答

Q: 为什么仓库里看不到具体 API Key？
A: 当前项目已把密钥集中到 `Backend/app_settings.py` + `Backend/.env.local` 管理，前后端代码中不应再硬编码真实 key。

Q: 数据库查询为什么对话里只显示前 10 行？
A: 这是当前设计。完整结果会导出为 Excel，对话里只展示前 10 行预览并提示总行数，避免超长表格淹没对话内容。

Q: 我问了 `TOP20`，为什么以前会跑出全量数据？
A: 旧逻辑对中文场景中的 `TOP20` 识别不稳。当前后端已补齐显式限行识别，明确的 `TOP N / 前 N 条` 会按用户要求执行。

Q: `start-prod.bat` 启动后为什么没有看到后端窗口？
A: 如果端口已经被旧进程占用，脚本会判断后端已启动并跳过。可先执行 `stop-prod.bat`，再重新运行 `start-prod.bat`。

Q: 文档上传后无法检索？
A: 先检查 `bge-small-zh-v1.5` 是否放在正确位置，再确认文档解析和索引任务是否成功完成。

Q: OCR 或语音任务失败怎么办？
A: 先查看任务中心和后端日志，再检查 OCR 依赖、百度语音配置、文件格式和网络连通性。支持重试的任务可直接在任务中心重试。

## 🚀 性能优化建议
1. 优先启用 GPU，用于 Embedding、OCR 和本地模型推理
2. 本地部署时为 Ollama 配置合理的并发与队列参数
3. 对高频文档和高频决策数据启用缓存与预热，减少首屏等待
4. 数据库查询尽量补齐索引，并控制白名单表规模与字段说明长度
5. 大文件、长音频、复杂 OCR 建议走任务化异步流程，不要全部塞进同步请求
6. 生产环境建议使用 `rebuild-prod.bat` / `start-prod.bat` 统一管理本地服务状态

## 📅 开发计划
1. 继续提升多轮对话上下文稳定性与任务衔接体验
2. 扩充 OCR 结构化模板和行业单据适配范围
3. 完善任务中心筛选、搜索和结果归档能力
4. 扩展决策中心指标体系与经营预测能力
5. 增加更多写作模板、PPT 模板和审单规则配置项

---

本项目持续迭代中，欢迎反馈与共建。
