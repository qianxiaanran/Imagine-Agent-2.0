# 🧠 Imagine-Agent-2.0 企业智能办公助手

[![LangChain](https://img.shields.io/badge/LangChain-00C2FF?style=for-the-badge)](https://www.langchain.com/)
[![DeepSeek](https://img.shields.io/badge/DeepSeek-LLM-blue?style=for-the-badge)](https://deepseek.com/)

Imagine-Agent-2.0 是面向企业办公场景的多模态智能助手，覆盖“对话 + 文档 + 数据 + OCR + 语音 + 写作 + 审单”的完整流程。后端基于 FastAPI 构建服务，前端采用 React + Vite，支持本地大模型（Ollama）与云端 DeepSeek 模型切换，适合私有化部署与持续迭代。

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
4. [下载Embedding模型](#3-下载embedding模型)
5. [配置API密钥](#4-配置api密钥)
6. [准备数据库](#5-准备数据库可选)
7. [运行系统](#6-运行系统)
5. [配置文件详解](#-配置文件详解)
6. [项目结构详解](#-项目结构详解)
7. [核心模块说明](#-核心模块说明)
核心模块子项：
1. [文档处理模块](#1-文档处理模块)
2. [数据库管理模块](#2-数据库管理模块)
3. [会议纪要总结模块](#3-会议纪要总结模块)
4. [OCR识别模块](#4-ocr识别模块)
5. [写作能力模块](#5-写作能力模块)
6. [多模式对话模块](#6-多模式对话模块)
7. [语音处理模块](#7-语音处理模块)
8. [检索与问答模块](#8-检索与问答模块)
9. [语言模型集成模块](#9-语言模型集成模块)
8. [使用指南](#-使用指南)
使用指南子项：
1. [文档分析功能](#1-文档分析功能)
2. [数据库查询功能](#2-数据库查询功能)
3. [会议纪要功能](#3-会议纪要功能)
4. [文档智能录入功能](#4-文档智能录入功能)
9. [API接口说明](#-api接口说明)
10. [常见问题解答](#-常见问题解答)
11. [性能优化建议](#-性能优化建议)
12. [开发计划](#-开发计划)

---

## 🏢 项目概述
Imagine-Agent-2.0 聚焦企业办公场景下的信息处理、知识检索和自动化写作，强调“可落地”和“可运营”。系统提供统一对话入口，用户可以在同一个界面里完成文档问答、数据库查询、OCR 识别、会议纪要与审单等任务，输出以流式方式展示，适合高频使用。

核心定位：
- 企业智能办公助手
- 私有化部署友好
- 多模式多工具统一入口
- 本地模型与云端模型可切换

适用场景：
- 企业制度、合同、规范文档查询
- 销售、库存、订单等业务数据查询
- OCR 文档结构化录入与校验
- 会议录音转写与总结
- 报告 / PPT / 邮件写作提纲生成

## ✨ 功能特性
- 多模式对话：通用 / 数据库 / 文档检索 / 联网搜索 / 审单模式
- 文档检索（RAG）：PDF/DOCX/TXT 上传解析、向量化、引用来源展示
- OCR 识别：图片/PDF 识别、结构化抽取、OCR 总结对话
- 数据库查询：自然语言转 SQL（Supabase Postgres），白名单表约束与安全校验
- 写作能力：报告 / PPT / 邮件大纲生成，支持模型后端选择
- 语音能力：上传音频转写、摘要、继续追问
- 分享能力：生成分享链接、公开访问会话
- 管理能力：用户管理、审单任务与规则管理、知识库管理
- 流式输出：对话与总结流式返回，响应更流畅

## 🏗️ 技术架构
关键组件：
- 前端：React + Vite，支持拖拽上传、OCR 预览、Markdown 渲染
- 后端：FastAPI，路由统一入口 `/api/*`
- LLM：本地 Ollama 与 DeepSeek API 双后端
- 向量检索：BGE Embedding（`bge-small-zh-v1.5`）
- OCR：PaddleOCR / PaddleOCR-VL + PaddleX
- 数据库：Supabase Postgres + Storage

简化架构示意：
```
前端(React)
  └─ /api/chat (流式)
  └─ /api/documents/upload
  └─ /api/ocr/recognize
  └─ /api/voice/transcribe_supabase

后端(FastAPI)
  ├─ chat_router (对话路由)
  ├─ documents_processing (文档向量化)
  ├─ database_manager (SQL生成与执行)
  ├─ ocr_manager (OCR识别与结构化)
  ├─ report_email_manager (报告/PPT/邮件)
  └─ audit_pipeline (审单规则与风险检测)
```

## 📦 安装部署

### 环境要求
- Python 3.10+
- Node.js 18+
- CUDA（可选，用于 GPU 推理）
- Git

### 1- 克隆项目
```bash
git clone https://github.com/qianxiaanran/Imagine-Agent-2.0.git
cd Imagine-Agent-2.0
```

### 2- 安装依赖
```bash
cd Backend
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r ..\requirements.txt

cd ..\frontend
npm install
```

### 3- 下载Embedding模型
将 `bge-small-zh-v1.5` 放在项目根目录：
```
./bge-small-zh-v1.5/
```
并确认 `Backend/documents_processing.py` 中 `local_model_path` 指向正确路径。

### 4- 配置API密钥
建议用环境变量配置，避免硬编码：
```bash
# DeepSeek
DEEPSEEK_URL=https://api.deepseek.com
DEEPSEEK_KEY=sk-xxx

# Supabase
SUPABASE_URL=...
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_DB_HOST=...
SUPABASE_DB_USER=...
SUPABASE_DB_PASSWORD=...
SUPABASE_DB_NAME=postgres
SUPABASE_DB_PORT=5432

# Ollama
OLLAMA_BASE_URL=http://localhost:11434
LLM_MODEL_NAME=qwen2.5-coder
OLLAMA_NUM_GPU=1

# 语音（百度 ASR）
BAIDU_APP_ID=...
BAIDU_API_KEY=...
BAIDU_SECRET_KEY=...
```

### 5- 准备数据库（可选）
数据库查询基于 Supabase Postgres，表结构白名单在 `Backend/database_manager.py` 中维护。需要提前建好相关表并配置连接信息。

### 6- 运行系统
```bash
# 后端
cd Backend
python main.py

# 前端
cd frontend
npm run dev
```
后端默认端口：`http://127.0.0.1:18001`
前端默认端口：`http://127.0.0.1:5173`

## ⚙️ 配置文件详解
- `Backend/config.py`：核心配置与提示词模板、Supabase 与 API 变量读取
- `Backend/deepseek_llm.py`：Ollama 与 DeepSeek 接入，流式输出与路由模型
- `Backend/documents_processing.py`：文档解析、分块与 Embedding 配置
- `Backend/database_manager.py`：SQL 生成规范、白名单表校验与执行策略
- `Backend/ocr_manager.py`：OCR 引擎初始化、PaddleOCR/VL 兼容与 GPU 选择
- `frontend/vite.config.js`：开发代理、HMR 配置与依赖优化

## 🗂️ 项目结构详解
```
.
├── Backend/                 # FastAPI 后端
│   ├── auth_router.py       # 注册/登录/验证码/用户资料
│   ├── chat_router.py       # 多模式对话入口与流式输出
│   ├── documents_processing.py # 文档解析与向量化
│   ├── database_manager.py  # SQL 生成与执行
│   ├── ocr_manager.py       # OCR 主流程
│   ├── ocr_structured.py    # OCR 结构化抽取
│   ├── report_email_manager.py # 报告/PPT/邮件写作
│   ├── audit_pipeline.py    # 审单规则与风险检测
│   ├── audit_router.py      # 审单任务接口
│   ├── admin_router.py      # 管理后台接口
│   ├── voice_manager.py     # 语音识别与转写
│   ├── voice_files_processing.py # 音频处理
│   └── main.py              # 服务入口
├── frontend/                # React 前端
│   ├── src/pages/Dashboard  # 主功能页（对话/文档/OCR/写作）
│   ├── src/pages/Admin      # 管理后台
│   ├── src/api              # API 封装
│   └── src/components       # 组件与基础样式
├── requirements.txt         # 后端依赖
├── package.json             # 前端依赖
└── README.md
```

## 🔧 核心模块说明

### 1- 文档处理模块
- 入口：`Backend/documents_processing.py`
- 能力：文档加载、分块、向量化、向量检索
- 支持格式：PDF / DOCX / TXT
- 关键点：Embedding 使用 `bge-small-zh-v1.5`，支持 GPU 优先

### 2- 数据库管理模块
- 入口：`Backend/database_manager.py`
- 能力：自然语言转 SQL、SQL 安全校验、白名单表控制
- 使用 Supabase Postgres 连接信息
- 提示词优化：支持按表关键词生成“精简 schema”以降低耗时

### 3- 会议纪要总结模块
- 入口：`Backend/voice_files_processing.py`、`Backend/voice_manager.py`
- 能力：音频上传、语音识别、会议纪要摘要与追问
- 可结合 Supabase Storage 进行异步转写

### 4- OCR识别模块
- 入口：`Backend/ocr_manager.py`、`Backend/ocr_structured.py`
- 能力：图片/PDF OCR、结构化抽取、摘要对话
- 引擎：PaddleOCR / PaddleOCR-VL / PaddleX

### 5- 写作能力模块
- 入口：`Backend/report_email_manager.py`
- 能力：报告 / PPT / 邮件大纲生成
- 输出格式：结构化 JSON，前端做可视化渲染

### 6- 多模式对话模块
- 入口：`Backend/chat_router.py`
- 能力：通用对话、数据库、RAG、搜索、审单路由
- 支持流式输出与前端增量渲染

### 7- 语音处理模块
- 入口：`Backend/voice_manager.py`
- 能力：语音转写、实时/异步模式、多端回放链接

### 8- 检索与问答模块
- 入口：`Backend/documents_processing.py`、`Backend/chat_router.py`
- 能力：向量检索 + 关键词检索 + 上下文拼接生成回答

### 9- 语言模型集成模块
- 入口：`Backend/deepseek_llm.py`
- 能力：Ollama 本地模型与 DeepSeek API 双后端
- 支持流式输出与温度、上下文长度配置

## 📖 使用指南

### 1- 文档分析功能
1. 上传 PDF/DOCX/TXT
2. 等待解析与向量化完成
3. 进入对话提问，系统基于文档回答并给出来源

### 2- 数据库查询功能
1. 选择数据库模式或自动路由进入数据库查询
2. 输入自然语言问题
3. 系统生成 SQL 并执行，返回总结

### 3- 会议纪要功能
1. 上传音频文件
2. 等待转写完成
3. 获取结构化纪要并继续追问

### 4- 文档智能录入功能
1. OCR 上传图片/PDF
2. 查看识别文本与结构化结果
3. 点击总结或继续对话

## 🌐 API接口说明

常用接口一览：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | /api/chat | 多模式对话（流式输出） |
| GET | /api/history/sessions | 获取会话列表 |
| GET | /api/history/{session_id} | 获取会话记录 |
| PATCH | /api/history/{session_id}/title | 修改会话标题 |
| POST | /api/documents/upload | 上传文档并向量化 |
| POST | /api/ocr/recognize | OCR 识别 |
| POST | /api/ocr/ingest | OCR 结构化录入 |
| POST | /api/ocr/parse | OCR 解析 |
| POST | /api/voice/transcribe_supabase | 语音转写任务 |
| GET | /api/voice/result/{task_id} | 获取转写结果 |
| POST | /api/generate/report | 报告大纲生成 |
| POST | /api/generate/email | 邮件草稿生成 |
| POST | /api/share/create | 创建分享链接 |
| GET | /api/public/share/{token} | 访问分享内容 |

管理与审单接口：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | /api/audit/start | 发起审单任务 |
| GET | /api/audit/{job_id} | 获取审单结果 |
| GET | /api/admin/users | 管理员用户列表 |
| POST | /api/admin/users/{user_id}/role | 修改用户角色 |
| POST | /api/admin/users/{user_id}/status | 修改用户状态 |
| POST | /api/admin/audit/review | 审单复核 |
| GET | /api/admin/audit/rules/{doc_type} | 获取规则 |
| PUT | /api/admin/audit/rules/{doc_type} | 更新规则 |
| POST | /api/admin/kb/documents/reindex | 知识库重建 |

## ❓ 常见问题解答

Q: 文档上传后无法检索？
A: 确认 Embedding 模型路径正确且向量化成功，建议查看后端日志。

Q: OCR 导入失败或报错？
A: 检查 PaddleOCR 与 CUDA 版本匹配，Windows 需确保 DLL 路径可用。

Q: 数据库查询慢？
A: 优化表结构与索引，开启精简 schema 提示词，减少上下文输入。

Q: 模型不走 GPU？
A: 确认 CUDA 驱动与 torch/paddle 版本一致，检查运行日志输出。

## 🚀 性能优化建议
1. 启用 GPU 推理（Embedding / OCR / LLM）
2. 减少上下文长度与历史输入
3. 使用更小的路由模型处理轻任务
4. 对高频查询加入缓存
5. 拆分超大文件并分批处理

## 📅 开发计划
1. 强化上下文记忆与长对话稳定性
2. 扩充 OCR 结构化模板库
3. 拓展数据库类型适配（MySQL/SQLServer）
4. 增加更多写作与审核模板

---

本项目持续迭代中，欢迎反馈与共建。
