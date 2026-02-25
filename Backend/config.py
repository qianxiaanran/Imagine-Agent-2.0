from langchain_text_splitters import RecursiveCharacterTextSplitter
import os

# config/supabase_config.py
SUPABASE_URL = os.getenv("SUPABASE_URL", "http://127.0.0.1:54321")

# 👇 前端等价权限（登录 / 查询 / 校验 JWT）
SUPABASE_ANON_KEY = os.getenv(
    "SUPABASE_ANON_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9."
    "CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0",
)

# 👇 后端管理员权限（仅后端使用）
SUPABASE_SERVICE_ROLE_KEY = os.getenv(
    "SUPABASE_SERVICE_ROLE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0."
    "EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU",
)

# API 配置 (建议从环境变量获取)
DEEPSEEK_URL = os.getenv("DEEPSEEK_URL", "https://api.deepseek.com")
DEEPSEEK_KEY = os.getenv("DEEPSEEK_KEY", "sk-xxx")

BAIDU_APP_ID = os.getenv("BAIDU_APP_ID" , "120885917")
BAIDU_API_KEY = os.getenv("BAIDU_API_KEY", "YxsmdI5HeKcDzMfaOmqnYAp1")
BAIDU_SECRET_KEY = os.getenv("BAIDU_SECRET_KEY", "YZzoL6rjEysCSo5PjJdWVI4XctrpnJx1")

# 向量模型路径 (可以是本地路径或 HuggingFace ID)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "./bge-small-zh-v1.5")

# 文本分割配置
TEXT_SPLITER = RecursiveCharacterTextSplitter(
    chunk_size=400,
    chunk_overlap=100,
    length_function=len,
    separators=[r"\n\n", r"\n", "。", "！", "？", " ", ""],
)

# 提示词模版 (保持不变)
RAG_SYS_PROMPT = """
【角色】企业文档助手
【文档内容】
{context}
【问题】
{question}
请根据文档回答。
"""
MEETING_MINUTES_PROMPT = """
【角色】会议记录员
【内容】
{context}
【要求】
{question}
请提炼会议纪要。
"""

REPORT_PPT_PROMPT = """
【角色】咨询顾问
请为主题"{topic}"（场景：{scene}）生成{length}的{audience}报告大纲。
关键点：{key_points}
"""

EMAIL_DRAFT_PROMPT = """
【角色】商务助手
请起草一封邮件。
主题：{subject}
收件人：{receiver_role}
场景：{scene}
语气：{tone}
要点：{key_points}
"""
