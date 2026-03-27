from __future__ import annotations

import os
import urllib.parse
from pathlib import Path

from dotenv import load_dotenv

_ENV_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=_ENV_DIR / ".env", override=False)
load_dotenv(dotenv_path=_ENV_DIR / ".env.local", override=True)


def _get_env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return default


SUPABASE_URL = _get_env("SUPABASE_URL", "SUPABASE_PROJECT_URL", default="http://127.0.0.1:54321")
SUPABASE_ANON_KEY = _get_env("SUPABASE_ANON_KEY", "SUPABASE_KEY")
SUPABASE_SERVICE_ROLE_KEY = _get_env("SUPABASE_SERVICE_ROLE_KEY")

DB_HOST = _get_env("SUPABASE_DB_HOST", default="127.0.0.1")
DB_USER = _get_env("SUPABASE_DB_USER", default="postgres")
DB_PORT = _get_env("SUPABASE_DB_PORT", default="54322")
DB_NAME = _get_env("SUPABASE_DB_NAME", default="postgres")
DB_PASSWORD_RAW = os.getenv("SUPABASE_DB_PASSWORD", "postgres")
DB_SSLMODE = _get_env("SUPABASE_DB_SSLMODE", default="disable")

_ENCODED_DB_PASSWORD = urllib.parse.quote_plus(DB_PASSWORD_RAW)
SQLALCHEMY_DATABASE_URL = _get_env(
    "SUPABASE_SQLALCHEMY_DATABASE_URL",
    default=f"postgresql://{DB_USER}:{_ENCODED_DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
)

DEEPSEEK_URL = _get_env("DEEPSEEK_URL", default="https://api.deepseek.com")
DEEPSEEK_KEY = _get_env("DEEPSEEK_KEY")
DEEPSEEK_MODEL_NAME = _get_env("DEEPSEEK_MODEL_NAME", default="deepseek-chat")

BAIDU_APP_ID = _get_env("BAIDU_APP_ID")
BAIDU_API_KEY = _get_env("BAIDU_API_KEY")
BAIDU_SECRET_KEY = _get_env("BAIDU_SECRET_KEY")

ALIYUN_ACCESS_KEY_ID = _get_env("ALIYUN_ACCESS_KEY_ID")
ALIYUN_ACCESS_KEY_SECRET = _get_env("ALIYUN_ACCESS_KEY_SECRET")

BING_SUBSCRIPTION_KEY = _get_env("BING_SEARCH_V7_KEY", "BING_API_KEY")
BING_SEARCH_ENDPOINT = _get_env("BING_SEARCH_ENDPOINT", default="https://api.bing.microsoft.com/v7.0/search")
SERPAPI_API_KEY = _get_env("SERPAPI_API_KEY")
SERPER_API_KEY = _get_env("SERPER_API_KEY")
TAVILY_API_KEY = _get_env("TAVILY_API_KEY")

PRESENTON_BASE_URL = _get_env("PRESENTON_BASE_URL", default="http://127.0.0.1:5000")
PRESENTON_API_KEY = _get_env("PRESENTON_API_KEY")
