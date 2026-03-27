import os

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app_settings import (
    BAIDU_API_KEY,
    BAIDU_APP_ID,
    BAIDU_SECRET_KEY,
    DEEPSEEK_KEY,
    DEEPSEEK_MODEL_NAME,
    DEEPSEEK_URL,
    SUPABASE_ANON_KEY,
    SUPABASE_SERVICE_ROLE_KEY,
    SUPABASE_URL,
)

SUPABASE_PUBLIC_URL = SUPABASE_URL
DEEPSEEK_MODEL = DEEPSEEK_MODEL_NAME

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
