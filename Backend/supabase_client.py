from supabase import Client, create_client
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app_settings import (
    SQLALCHEMY_DATABASE_URL,
    SUPABASE_ANON_KEY,
    SUPABASE_SERVICE_ROLE_KEY,
    SUPABASE_URL,
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
