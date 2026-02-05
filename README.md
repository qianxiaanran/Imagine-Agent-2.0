# Imagine-Agent-2.0 企业智能办公助手

面向企业办公场景的多模态智能助手，提供对话问答、文档检索（RAG）、数据库查询、OCR 识别、语音转写、审单辅助，以及报告 / PPT / 邮件写作等功能。支持本地大模型（Ollama）与云端 DeepSeek 模型切换。

## 核心功能
- 多模式对话：通用对话 / 数据库查询 / 文档检索（RAG）/ 联网搜索 / 审单
- 文档检索：上传 PDF/DOCX/TXT 解析并向量化，支持引用来源
- OCR 识别：图片 / PDF 识别与结构化抽取，可继续对话总结
- 数据库查询：自然语言转 SQL（PostgreSQL/Supabase），白名单表结构约束
- 写作能力：报告 / PPT / 邮件大纲生成，支持模型后端选择
- 语音能力：语音上传转写、摘要与追问

## 技术栈
- 后端：FastAPI + LangChain + Supabase(Postgres/Storage)
- 前端：React + Vite
- OCR：PaddleOCR / PaddleX
- 向量：BGE Embedding（`bge-small-zh-v1.5`）
- LLM：本地 Ollama / 云端 DeepSeek

## 项目结构
```
.
├── Backend/                 # FastAPI 后端
├── frontend/                # React 前端
├── requirements.txt         # 后端依赖
├── package.json             # 前端依赖
└── README.md
```

## 快速开始

### 1) 启动后端
```bash
cd Backend
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r ..\requirements.txt
python main.py
```
默认端口：`http://127.0.0.1:18001`

### 2) 启动前端
```bash
cd frontend
npm install
npm run dev
```
默认端口：`http://127.0.0.1:5173`

前端开发代理已在 `frontend/vite.config.js` 中配置为转发 `/api` 到 `http://127.0.0.1:18001`。

## 配置说明
建议通过环境变量配置密钥与模型参数（避免硬编码）：

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

> 注意：当前 `Backend/config.py` 中仍包含默认值/示例值，正式部署前请替换为环境变量或自行修改。

## Embedding 模型
本项目默认使用本地模型 `bge-small-zh-v1.5`。请将模型目录放在项目根目录：
```
./bge-small-zh-v1.5/
```
并确认 `Backend/documents_processing.py` 中的 `local_model_path` 指向正确路径。

## 常见注意事项
- **不要提交模型与生成文件**：`.gitignore` 已默认忽略 `bge-small-zh-v1.5/`、`Backend/static/ocr/`、`Backend/storage/` 等目录。
- **GPU 支持**：Embedding / OCR / LLM 若本机支持 CUDA，会自动走 GPU。
- **数据库**：数据库查询基于 Supabase Postgres，表结构在 `Backend/database_manager.py` 中做了白名单限制。

---

如需定制部署、模型替换或功能扩展，可在此基础上继续迭代。
