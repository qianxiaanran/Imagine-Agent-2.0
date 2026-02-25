import os

from supabase import Client, create_client
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Local Supabase defaults (supabase start)
DEFAULT_SUPABASE_URL = "http://127.0.0.1:54321"
DEFAULT_SUPABASE_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9."
    "CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0"
)
DEFAULT_SUPABASE_SERVICE_ROLE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0."
    "EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU"
)

SUPABASE_URL = os.getenv("SUPABASE_URL", DEFAULT_SUPABASE_URL)
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", DEFAULT_SUPABASE_ANON_KEY)
SUPABASE_SERVICE_ROLE_KEY = os.getenv(
    "SUPABASE_SERVICE_ROLE_KEY", DEFAULT_SUPABASE_SERVICE_ROLE_KEY
)

# Database defaults point to local Supabase Postgres
DB_USER = os.getenv("SUPABASE_DB_USER", "postgres")
DB_PASSWORD = os.getenv("SUPABASE_DB_PASSWORD", "postgres")
DB_HOST = os.getenv("SUPABASE_DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("SUPABASE_DB_PORT", "54322")
DB_NAME = os.getenv("SUPABASE_DB_NAME", "postgres")
SQLALCHEMY_DATABASE_URL = os.getenv(
    "SUPABASE_SQLALCHEMY_DATABASE_URL",
    f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
)

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


_anon_client: Client | None = None
_admin_client: Client | None = None


def get_anon_supabase(fresh: bool = False) -> Client:
    global _anon_client
    if fresh:
        return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    if _anon_client is None:
        _anon_client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    return _anon_client


def get_admin_supabase(fresh: bool = False) -> Client:
    global _admin_client
    if fresh:
        return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    if _admin_client is None:
        _admin_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    return _admin_client


supabase: Client = get_admin_supabase()


def require_supabase() -> Client:
    return supabase
