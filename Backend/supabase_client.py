# supabase_client.py
import os
from supabase import create_client, Client
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# =========================
# 1. Supabase API config (for Auth/Storage)
# =========================
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://gjbmkzduwtcfhmivvklj.supabase.co")

# anon key (用于前端交互、登录鉴权)
SUPABASE_ANON_KEY = os.getenv(
    "SUPABASE_ANON_KEY",
    "***REMOVED_SUPABASE_ANON_TOKEN***",
)

# service role key (用于后端管理 API)
# ⚠️ 注意：此 Key 拥有超级管理员权限，绝对不能泄露给前端
SUPABASE_SERVICE_ROLE_KEY = os.getenv(
    "SUPABASE_SERVICE_ROLE_KEY",
    "***REMOVED_SUPABASE_SERVICE_ROLE_TOKEN***",
)

# =========================
# 2. SQLAlchemy + Pooler database config
# =========================


# ⚠️ 注意：Service Key 不是数据库密码！
# 请在此处填入你的 Supabase 数据库密码 (Database Password)
SUPABASE_DB_PASSWORD = os.getenv("SUPABASE_DB_PASSWORD", "在此处填入你的真实数据库密码")

# Extract Project ID from URL (gjbmkzduwtcfhmivvklj)
PROJECT_ID = SUPABASE_URL.split("//")[1].split(".")[0]

# Supabase Pooler connection string
DB_USER = f"postgres.{PROJECT_ID}"
DB_HOST = "aws-0-us-east-1.pooler.supabase.com" # Update by your actual region
DB_PORT = "6543"
DB_NAME = "postgres"

SQLALCHEMY_DATABASE_URL = f"postgresql://{DB_USER}:{SUPABASE_DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?pgbouncer=true"

# 创建 SQLAlchemy 引擎
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True
)

# 创建 Session 工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ORM 基类
Base = declarative_base()

def get_db():
    """FastAPI/Flask 依赖注入使用的生成器"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# =========================
# 3. Client 单例管理
# =========================
_anon_client: Client | None = None
_admin_client: Client | None = None

def get_anon_supabase(fresh: bool = False) -> Client:
    """Return anon client; use fresh=True to avoid shared auth session state."""
    global _anon_client
    if fresh:
        return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    if _anon_client is None:
        _anon_client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    return _anon_client

def get_admin_supabase(fresh: bool = False) -> Client:
    """Return admin client; use fresh=True to avoid shared auth session state."""
    global _admin_client
    if fresh:
        return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    if _admin_client is None:
        _admin_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    return _admin_client

# ✨ [关键修复] 将默认导出的 supabase 客户端切换为 Admin Client
# 这样 history_manager 和 chat_router 将自动拥有写入权限，不再报 42501 错误。
supabase: Client = get_admin_supabase()

def require_supabase() -> Client:
    return supabase


