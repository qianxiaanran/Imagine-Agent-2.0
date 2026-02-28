import os
import re
import ast
import time
import hashlib
import urllib.parse
import logging
from collections import OrderedDict
from datetime import datetime
from typing import Any, Dict, Generator, Optional, Union, Callable

# ✅ [修复] 兼容 LangChain 新旧版本的导入路径
try:
    from langchain_core.messages import HumanMessage
except ImportError:
    try:
        from langchain.schema import HumanMessage
    except ImportError:
        print("❌ [Database Manager] 无法导入 HumanMessage，请检查 langchain 版本")
        HumanMessage = None

from langchain_community.utilities import SQLDatabase
from deepseek_llm import get_llm_instance

# ============================================================
# 🔌 数据库连接配置 (Supabase PostgreSQL)
# ============================================================
DB_HOST = os.getenv("SUPABASE_DB_HOST", "127.0.0.1")
DB_USER = os.getenv("SUPABASE_DB_USER", "postgres")
DB_PORT = os.getenv("SUPABASE_DB_PORT", "54322")
DB_NAME = os.getenv("SUPABASE_DB_NAME", "postgres")
DB_PASSWORD_RAW = os.getenv("SUPABASE_DB_PASSWORD", "postgres")
DB_SSLMODE = os.getenv("SUPABASE_DB_SSLMODE", "disable")

encoded_password = urllib.parse.quote_plus(DB_PASSWORD_RAW)
DB_CONNECTION_STRING = (
    f"postgresql://{DB_USER}:{encoded_password}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    f"?sslmode={DB_SSLMODE}&connect_timeout=15"
)

# ============================================================
# 定义严格的表白名单
# ============================================================
ALLOWED_TABLES = {
    "company_info", "departments", "roles", "employees", "customers",
    "suppliers", "products", "inventory", "orders", "order_items", "purchases"
}

# ============================================================
# 🚀 快速优化：slim schema + 表路由
# ============================================================
TABLE_ORDER = [
    "company_info", "departments", "roles", "employees", "customers",
    "suppliers", "products", "inventory", "orders", "order_items", "purchases"
]

TABLE_SCHEMAS = {
    "company_info": "company_info(id, company_name, registration_code, address, contact_phone, business_scope, established_date)",
    "departments": "departments(dept_id, dept_name, parent_dept_id, manager_id, location, description)",
    "roles": "roles(role_id, role_name, permissions, description)",
    "employees": "employees(emp_id, emp_no, emp_name, gender, birth_date, position, dept_id, role_id, hire_date, salary, status, phone, email)",
    "customers": "customers(cust_id, cust_no, cust_name, cust_type, cust_level, contact_person, phone, email, sales_id, tax_id)",
    "suppliers": "suppliers(supp_id, supp_no, supp_name, contact_person, phone, email, tax_id, rating)",
    "products": "products(prod_id, prod_no, prod_name, category, specification, unit, purchase_price, selling_price, status)",
    "inventory": "inventory(inv_id, prod_id, warehouse, quantity, last_check_date)",
    "orders": "orders(order_id, order_no, order_date, cust_id, emp_id, total_amount, payment_status, delivery_status)",
    "order_items": "order_items(item_id, order_id, prod_id, quantity, unit_price, total_price)",
    "purchases": "purchases(purchase_id, purchase_no, purchase_date, supp_id, emp_id, total_amount, status)",
}

TABLE_RELATIONS = [
    ("employees", "departments", "employees.dept_id = departments.dept_id"),
    ("orders", "customers", "orders.cust_id = customers.cust_id"),
    ("orders", "employees", "orders.emp_id = employees.emp_id"),
    ("order_items", "orders", "order_items.order_id = orders.order_id"),
    ("order_items", "products", "order_items.prod_id = products.prod_id"),
    ("inventory", "products", "inventory.prod_id = products.prod_id"),
    ("purchases", "suppliers", "purchases.supp_id = suppliers.supp_id"),
]

TABLE_RELATED = {
    "orders": {"customers", "employees", "order_items"},
    "order_items": {"orders", "products"},
    "inventory": {"products"},
    "purchases": {"suppliers", "employees"},
    "employees": {"departments", "roles"},
}

TABLE_KEYWORDS = {
    "orders": ["订单", "销售订单", "下单", "订单号", "order", "order_no", "order_date", "payment_status", "delivery_status", "销售"],
    "order_items": ["订单明细", "明细", "商品明细", "item", "quantity", "unit_price", "total_price"],
    "customers": ["客户", "客户群体", "客户类型", "客户等级", "vip", "cust_name", "cust_type", "cust_level"],
    "employees": ["员工", "业务员", "销售员", "emp_name", "emp_no", "入职", "薪资", "部门员工"],
    "departments": ["部门", "dept", "dept_name", "组织架构", "经理"],
    "roles": ["角色", "权限", "role_name", "permissions"],
    "products": ["产品", "商品", "sku", "品类", "prod_name", "category", "selling_price", "purchase_price"],
    "inventory": ["库存", "仓库", "盘点", "quantity", "warehouse"],
    "suppliers": ["供应商", "供货", "supp_name", "rating"],
    "purchases": ["采购", "进货", "purchase_no", "purchase_date", "采购单"],
    "company_info": ["公司", "企业信息", "经营范围", "business_scope", "registration_code", "成立日期"],
}

DB_PROMPT_TABLE_FILTER = os.getenv("DB_PROMPT_TABLE_FILTER", "true").lower() != "false"
DB_RESULT_PROMPT_MAX_CHARS = int(os.getenv("DB_RESULT_PROMPT_MAX_CHARS", "3000"))
DB_AUTO_LIMIT = int(os.getenv("DB_AUTO_LIMIT", "200"))
DB_SQL_CACHE_SIZE = int(os.getenv("DB_SQL_CACHE_SIZE", "256"))
DB_SQL_CACHE_TTL = int(os.getenv("DB_SQL_CACHE_TTL", "300"))
DB_RESULT_CACHE_SIZE = int(os.getenv("DB_RESULT_CACHE_SIZE", "128"))
DB_RESULT_CACHE_TTL = int(os.getenv("DB_RESULT_CACHE_TTL", "120"))
DB_SUMMARY_CACHE_SIZE = int(os.getenv("DB_SUMMARY_CACHE_SIZE", "128"))
DB_SUMMARY_CACHE_TTL = int(os.getenv("DB_SUMMARY_CACHE_TTL", "300"))
DB_STATUS_EVENTS_ENABLED = os.getenv("DB_STATUS_EVENTS_ENABLED", "true").lower() != "false"
DB_LOCAL_HISTORY_CONTEXT_MAX_CHARS = int(os.getenv("DB_LOCAL_HISTORY_CONTEXT_MAX_CHARS", "700"))
DB_LOCAL_SUMMARY_CONTEXT_MAX_CHARS = int(os.getenv("DB_LOCAL_SUMMARY_CONTEXT_MAX_CHARS", "700"))
DB_LOCAL_SESSION_STATE_MAX_CHARS = int(os.getenv("DB_LOCAL_SESSION_STATE_MAX_CHARS", "600"))
DB_LOCAL_ACTIVE_CONTEXT_MAX_CHARS = int(os.getenv("DB_LOCAL_ACTIVE_CONTEXT_MAX_CHARS", "500"))
DB_LOCAL_RESULT_PROMPT_MAX_CHARS = int(os.getenv("DB_LOCAL_RESULT_PROMPT_MAX_CHARS", "1200"))

# ============================================================
# 🧭 DDL 与 规范定义 (已根据 SQL 脚本更新)
# ============================================================
ENTERPRISE_DB_SPEC = r"""
================【企业数据库结构规范（严格白名单）】===============
⚠️ 权限警告：只允许查询以下 11 张表。禁止查询任何系统表（如 pg_table）或臆造表。

1) company_info (公司信息): id, company_name, registration_code, address, contact_phone, business_scope, established_date
2) departments (部门): dept_id, dept_name, parent_dept_id, manager_id, location, description
3) roles (角色): role_id, role_name, permissions, description
4) employees (员工): emp_id, emp_no, emp_name, gender, birth_date, position, dept_id, role_id, hire_date, salary, status, phone, email
5) customers (客户): cust_id, cust_no, cust_name, cust_type, cust_level, contact_person, phone, email, sales_id, tax_id
6) suppliers (供应商): supp_id, supp_no, supp_name, contact_person, phone, email, tax_id, rating
7) products (产品): prod_id, prod_no, prod_name, category, specification, unit, purchase_price, selling_price, status
8) inventory (库存): inv_id, prod_id, warehouse, quantity, last_check_date
9) orders (订单): order_id, order_no, order_date, cust_id, emp_id, total_amount, payment_status, delivery_status
10) order_items (订单明细): item_id, order_id, prod_id, quantity, unit_price, total_price
11) purchases (采购): purchase_id, purchase_no, purchase_date, supp_id, emp_id, total_amount, status


---------------- Core Relationships ---------------
- employees.dept_id = departments.dept_id
- orders.cust_id = customers.cust_id
- orders.emp_id = employees.emp_id
- order_items.order_id = orders.order_id
- order_items.prod_id = products.prod_id
- inventory.prod_id = products.prod_id
- purchases.supp_id = suppliers.supp_id
"""

SQL_GENERATION_RULES = r"""
================ SQL Generation Rules ================
1) 仅输出 SQL 本身，不要解释。必须使用 PostgreSQL 语法。
2) 禁止执行除了 SELECT 以外的任何操作。
3) 禁止查询上述 11 张表以外的任何表。
4) 如果问题涉及时间，请使用 date_trunc 或 CURRENT_DATE 进行计算。
5) 默认 LIMIT 10。
"""

# ============================================================
# 安全和政策验证器
# ============================================================
_ONLY_SELECT_PATTERN = re.compile(r"^\s*(WITH\b[\s\S]+?\bSELECT\b|SELECT\b)", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|REPLACE|GRANT|REVOKE)\b",
    re.IGNORECASE
)


def _clean_sql(sql: str) -> str:
    match = re.search(r"```(sql)?\s*([\s\S]*?)\s*```", sql, re.IGNORECASE)
    if match:
        sql = match.group(2)
    else:
        sql = sql.replace("```sql", "").replace("```", "").strip()
    return sql.strip().rstrip(";")


def _is_safe_readonly_sql(sql: str) -> bool:
    if not sql:
        return False
    if _FORBIDDEN_PATTERN.search(sql):
        return False
    if not _ONLY_SELECT_PATTERN.match(sql):
        return False
    return True


def _validate_table_whitelist(sql: str) -> tuple[bool, str]:
    """
    Extract all table names from SQL and compare against the whitelist.
    """
    # 匹配 FROM 或 JOIN 后面的单词，尝试识别表名
    # 逻辑：找 FROM/JOIN 后面跟着的单词，排除子查询 (SELECT ...)
    table_matches = re.findall(r"(?:FROM|JOIN)\s+([a-zA-Z0-9_]+)", sql, re.IGNORECASE)

    found_tables = {t.lower() for t in table_matches}
    unauthorized = found_tables - ALLOWED_TABLES

    if unauthorized:
        return False, f"SQL 校验拦截：禁止访问未授权的表: {', '.join(unauthorized)}"

    return True, ""


_AGG_FUNC_PATTERN = re.compile(r"\b(count|sum|avg|min|max)\s*\(", re.IGNORECASE)


class TTLCache:
    def __init__(self, maxsize: int = 128, ttl: int = 300):
        self.maxsize = maxsize
        self.ttl = ttl
        self._data: OrderedDict[str, tuple[object, float]] = OrderedDict()

    def get(self, key: str):
        if not key:
            return None
        item = self._data.get(key)
        if not item:
            return None
        value, expires_at = item
        if expires_at and expires_at < time.time():
            self._data.pop(key, None)
            return None
        self._data.move_to_end(key)
        return value

    def set(self, key: str, value):
        if not key:
            return
        expires_at = time.time() + self.ttl if self.ttl > 0 else 0
        self._data[key] = (value, expires_at)
        self._data.move_to_end(key)
        while len(self._data) > self.maxsize:
            self._data.popitem(last=False)


_SQL_CACHE = TTLCache(DB_SQL_CACHE_SIZE, DB_SQL_CACHE_TTL)
_SQL_RESULT_CACHE = TTLCache(DB_RESULT_CACHE_SIZE, DB_RESULT_CACHE_TTL)
_SUMMARY_CACHE = TTLCache(DB_SUMMARY_CACHE_SIZE, DB_SUMMARY_CACHE_TTL)


def _select_tables_for_query(user_query: str) -> list[str]:
    q = (user_query or "").lower()
    if not q:
        return TABLE_ORDER.copy()

    selected = set()

    # 直接表名命中
    for t in TABLE_ORDER:
        if t in q:
            selected.add(t)

    # 关键词命中
    for t, keywords in TABLE_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in q:
                selected.add(t)
                break

    if not selected:
        return TABLE_ORDER.copy()

    # 展开关联表
    related = set()
    for t in list(selected):
        related.update(TABLE_RELATED.get(t, set()))
    selected |= related

    return [t for t in TABLE_ORDER if t in selected]


def _build_db_spec(selected_tables: list[str]) -> str:
    tables = [t for t in TABLE_ORDER if t in set(selected_tables)]
    if not tables:
        tables = TABLE_ORDER

    lines = [
        "================ Enterprise DB Schema (Whitelisted) ================",
        "Only use the tables listed below. Do NOT access system tables.",
    ]

    for i, t in enumerate(tables, 1):
        schema = TABLE_SCHEMAS.get(t, t)
        lines.append(f"{i}) {schema}")

    relations = [
        rel for a, b, rel in TABLE_RELATIONS
        if a in tables and b in tables
    ]
    if relations:
        lines.append("")
        lines.append("---------------- Relationships ----------------")
        for rel in relations:
            lines.append(f"- {rel}")

    return "\n".join(lines)


def _truncate_result_text(result_text: str, max_chars: int) -> tuple[str, bool]:
    if not result_text:
        return "", False
    if len(result_text) <= max_chars:
        return result_text, False
    return result_text[:max_chars], True


def _is_simple_aggregate_sql(sql: str) -> bool:
    if not sql:
        return False
    s = sql.lower()
    if "group by" in s:
        return False
    return bool(_AGG_FUNC_PATTERN.search(sql))


def _extract_single_value(result_text: str) -> Optional[str]:
    try:
        data = ast.literal_eval(result_text)
        if isinstance(data, list) and data:
            row = data[0]
            if isinstance(row, (list, tuple)) and len(row) == 1:
                return str(row[0])
            if not isinstance(row, (list, tuple, dict)):
                return str(row)
    except Exception:
        return None
    return None


_LIMIT_HINT_PATTERN = re.compile(
    r"(limit\s+\d+|top\s+\d+|前\s*\d+|最近\s*\d+|只要\s*\d+|仅\s*\d+|\d+\s*条|\d+\s*行|\d+\s*个|\d+\s*条记录|\d+\s*个记录)",
    re.IGNORECASE,
)
_NO_LIMIT_HINT_PATTERN = re.compile(r"(全部|所有|全量|不限|完整|全部记录|所有记录)", re.IGNORECASE)


def _user_specified_limit(user_query: str) -> bool:
    q = (user_query or "").strip().lower()
    if not q:
        return False
    if _LIMIT_HINT_PATTERN.search(q):
        return True
    if _NO_LIMIT_HINT_PATTERN.search(q):
        return True
    return False


def _ensure_limit(sql: str, user_query: str, limit_value: int) -> str:
    if not sql:
        return sql
    if limit_value <= 0:
        return sql
    if re.search(r"\blimit\b|\bfetch\s+first\b|\btop\s+\d+", sql, re.IGNORECASE):
        return sql
    if _user_specified_limit(user_query):
        return sql
    return f"{sql} LIMIT {limit_value}"


_AGG_FUNC_PATTERN = re.compile(r"\b(count|sum|avg|min|max)\s*\(", re.IGNORECASE)


def _select_tables_for_query(user_query: str) -> list[str]:
    q = (user_query or "").lower()
    if not q:
        return TABLE_ORDER.copy()

    selected = set()

    # 直接表名命中
    for t in TABLE_ORDER:
        if t in q:
            selected.add(t)

    # 关键词命中
    for t, keywords in TABLE_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in q:
                selected.add(t)
                break

    if not selected:
        return TABLE_ORDER.copy()

    # 展开关联表
    related = set()
    for t in list(selected):
        related.update(TABLE_RELATED.get(t, set()))
    selected |= related

    return [t for t in TABLE_ORDER if t in selected]


def _build_db_spec(selected_tables: list[str]) -> str:
    tables = [t for t in TABLE_ORDER if t in set(selected_tables)]
    if not tables:
        tables = TABLE_ORDER

    lines = [
        "================ Enterprise DB Schema (Whitelisted) ================",
        "Only use the tables listed below. Do NOT access system tables.",
    ]

    for i, t in enumerate(tables, 1):
        schema = TABLE_SCHEMAS.get(t, t)
        lines.append(f"{i}) {schema}")

    relations = [
        rel for a, b, rel in TABLE_RELATIONS
        if a in tables and b in tables
    ]
    if relations:
        lines.append("")
        lines.append("---------------- Relationships ----------------")
        for rel in relations:
            lines.append(f"- {rel}")

    return "\n".join(lines)


def _truncate_result_text(result_text: str, max_chars: int) -> tuple[str, bool]:
    if not result_text:
        return "", False
    if len(result_text) <= max_chars:
        return result_text, False
    return result_text[:max_chars], True


def _is_simple_aggregate_sql(sql: str) -> bool:
    if not sql:
        return False
    s = sql.lower()
    if "group by" in s:
        return False
    return bool(_AGG_FUNC_PATTERN.search(sql))


def _extract_single_value(result_text: str) -> Optional[str]:
    try:
        data = ast.literal_eval(result_text)
        if isinstance(data, list) and data:
            row = data[0]
            if isinstance(row, (list, tuple)) and len(row) == 1:
                return str(row[0])
            if not isinstance(row, (list, tuple, dict)):
                return str(row)
    except Exception:
        return None
    return None


def _trim_prompt_text(value: Optional[str], max_chars: int) -> str:
    if not value:
        return ""
    text = str(value).strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


class DatabaseManager:
    def __init__(self):
        self.db: Optional[SQLDatabase] = None
        self._init_db_connection()

    def _init_db_connection(self):
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
        engine_args = {
            "pool_pre_ping": True,
            "pool_recycle": 3600,
            "pool_size": 5,
            "max_overflow": 10,
            "connect_args": {"connect_timeout": 15}
        }
        try:
            self.db = SQLDatabase.from_uri(DB_CONNECTION_STRING, engine_args=engine_args)
            self.db.run("SELECT 1")
            print("✅ [Database] 连接成功！")
        except Exception as e:
            print(f"❌ [Database] 连接失败: {e}")
            self.db = None

    def query_fast(
        self,
        db_name: str,
        user_query: str,
        model_type: str = "local",
        response_instruction: Optional[str] = None,
        history_context: str = "",
        summary_context: str = "",
        session_state: str = "",
        active_context_content: str = "",
        stop_checker: Optional[Callable[[], bool]] = None,
    ) -> Generator[Union[str, Dict[str, Any]], None, None]:
        """
        One-shot execution policy:
        - Generate SQL only once
        - Execute SQL only once
        - 不重试不二次查询
        - 支持 model_type (local/cloud)
        """
        is_local_backend = (model_type or "local").strip().lower() in {"", "local", "ollama"}

        def _status_event(message: str):
            if not DB_STATUS_EVENTS_ENABLED or not message:
                return None
            return {"type": "status", "message": message}

        def _should_stop() -> bool:
            try:
                return bool(stop_checker and stop_checker())
            except Exception:
                return False

        if _should_stop():
            return

        if not self.db:
            self._init_db_connection()
            if not self.db:
                yield "⚠️ 数据库连接失败。"
                return

        # 获取对应的 LLM 实例
        if _should_stop():
            return
        try:
            target_llm = get_llm_instance(model_type)
        except Exception as e:
            yield f"⚠️ 模型初始化失败 ({model_type}): {e}"
            return

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        history_cap = DB_LOCAL_HISTORY_CONTEXT_MAX_CHARS if is_local_backend else 1200
        summary_cap = DB_LOCAL_SUMMARY_CONTEXT_MAX_CHARS if is_local_backend else 1200
        session_cap = DB_LOCAL_SESSION_STATE_MAX_CHARS if is_local_backend else 1200
        active_cap = DB_LOCAL_ACTIVE_CONTEXT_MAX_CHARS if is_local_backend else 1000
        history_context = _trim_prompt_text(history_context, history_cap)
        summary_context = _trim_prompt_text(summary_context, summary_cap)
        session_state = _trim_prompt_text(session_state, session_cap)
        active_context_content = _trim_prompt_text(active_context_content, active_cap)

        selected_tables = _select_tables_for_query(user_query)
        db_spec = _build_db_spec(selected_tables) if DB_PROMPT_TABLE_FILTER else ENTERPRISE_DB_SPEC

        context_sections = []
        if session_state:
            context_sections.append(f"【会话状态】\n{session_state}")
        if summary_context:
            context_sections.append(f"【摘要上下文】\n{summary_context}")
        if history_context:
            context_sections.append(f"【近期对话】\n{history_context}")
        if active_context_content:
            context_sections.append(f"【当前附加上下文】\n{active_context_content}")
        context_block = "\n\n".join(context_sections).strip()

        sql_gen_prompt = f"""
你是一名数据分析助手，请将用户问题转换为 PostgreSQL SQL。
【当前时间】
{now}
【会话上下文】
{context_block or "（无）"}
【用户问题】
{user_query}
{db_spec}
{SQL_GENERATION_RULES}
请仅输出 SQL。
"""

        # 1) 只生成一次 SQL（带缓存）
        context_sig_source = f"{history_context}::{summary_context}::{session_state}::{active_context_content}"
        context_sig = hashlib.sha1(context_sig_source.encode("utf-8")).hexdigest()[:12]
        cache_key = f"{db_name}::{model_type}::{(user_query or '').strip()}::{context_sig}"
        raw_sql = _SQL_CACHE.get(cache_key)
        if not raw_sql:
            status = _status_event("正在生成 SQL...")
            if status:
                yield status
            if _should_stop():
                return
            try:
                if not HumanMessage:
                    yield "❌ HumanMessage 模块加载失败，无法构建提示词。"
                    return
                response = target_llm.invoke([HumanMessage(content=sql_gen_prompt)])
                raw_sql = _clean_sql(response.content)
            except Exception as e:
                yield f"Model generation error: {e}"
                return
            raw_sql = _ensure_limit(raw_sql, user_query, DB_AUTO_LIMIT)
        else:
            status = _status_event("命中 SQL 缓存，准备执行查询...")
            if status:
                yield status

        # 2) 安全校验 (SELECT 限制)
        if not _is_safe_readonly_sql(raw_sql):
            yield "🚫 SQL 校验拦截：仅允许 SELECT（或 WITH...SELECT）查询，禁止任何写操作。"
            return

        # 3) 表白名单严格校验
        is_valid_table, table_err_msg = _validate_table_whitelist(raw_sql)
        if not is_valid_table:
            print(f"🚫 表名校验拦截: {raw_sql}")
            yield f"🚫 {table_err_msg}"
            return

        if cache_key and raw_sql:
            _SQL_CACHE.set(cache_key, raw_sql)

        # 将本次执行 SQL 作为“来源”事件回传给上层，用于前端来源面板展示
        sql_text = (raw_sql or "").strip()
        if sql_text:
            yield {
                "type": "source",
                "source": {
                    "type": "sql",
                    "title": "SQL 查询语句",
                    "name": "SQL 查询语句",
                    "sql": sql_text,
                    "snippet": f"```sql\n{sql_text}\n```",
                },
            }

        # 4) 只执行一次 SQL（结果缓存）
        result_cache_key = f"{db_name}::{raw_sql}"
        query_result = _SQL_RESULT_CACHE.get(result_cache_key)
        if query_result is None:
            status = _status_event("正在执行数据库查询...")
            if status:
                yield status
            if _should_stop():
                return
            print(f"🔍 [DB] 执行 SQL (via {model_type}): {raw_sql}")
            try:
                query_result = self.db.run(raw_sql)
            except Exception as db_err:
                yield f"❌ 查询失败: {db_err}"
                return
            if query_result:
                _SQL_RESULT_CACHE.set(result_cache_key, query_result)

        if not query_result:
            yield "未查询到数据。"
            return

        if _is_simple_aggregate_sql(raw_sql):
            single_value = _extract_single_value(query_result)
            if single_value is not None:
                yield f"结果：{single_value}"
                return

        # 5) 成功后进行总结（只总结一次，带缓存）
        if _should_stop():
            return
        data_limit = min(DB_RESULT_PROMPT_MAX_CHARS, DB_LOCAL_RESULT_PROMPT_MAX_CHARS) if is_local_backend else DB_RESULT_PROMPT_MAX_CHARS
        data_text, truncated = _truncate_result_text(query_result, data_limit)
        truncate_note = "（数据已截断，仅供总结）" if truncated else ""
        response_pref = (response_instruction or "").strip()
        summary_context_parts = []
        if session_state:
            summary_context_parts.append(f"会话状态:\n{session_state}")
        if summary_context:
            summary_context_parts.append(f"摘要上下文:\n{summary_context}")
        if history_context:
            summary_context_parts.append(f"近期对话:\n{history_context}")
        if active_context_content:
            summary_context_parts.append(f"当前附加上下文:\n{active_context_content}")
        summary_context_text = "\n\n".join(summary_context_parts).strip()
        context_prefix = f"上下文:\n{summary_context_text}\n" if summary_context_text else ""
        summary_prompt = (
            f"用户问: {user_query}\n"
            f"{context_prefix}"
            f"SQL: {raw_sql}\n"
            f"数据{truncate_note}: {data_text}\n"
            "请简洁专业地回答。"
        )
        summary_prompt += (
            "\n\n回答规则:\n"
            "1) 只能基于“数据”中的事实回答，严禁编造任何数字、记录或结论。\n"
            "2) 如果数据不足以回答问题，请明确说“数据库结果不足以回答该问题”。\n"
            "3) 不要把上下文里的假设当成数据库事实。"
        )
        if response_pref:
            summary_prompt += f"\n\n请同时遵循以下输出偏好（仅影响表达，不改变事实与结论）：\n{response_pref}"

        summary_hash = hashlib.sha256(
            f"{user_query}::{raw_sql}::{data_text}::{response_pref}::{context_sig}".encode("utf-8")
        ).hexdigest()
        summary_cache_key = f"{db_name}::{summary_hash}"
        cached_summary = _SUMMARY_CACHE.get(summary_cache_key)
        if cached_summary:
            status = _status_event("命中总结缓存。")
            if status:
                yield status
            yield cached_summary
            return

        # 也使用流式传输进行摘要
        status = _status_event("正在整理查询结果...")
        if status:
            yield status
        summary_chunks = []
        stream_iter = None
        try:
            stream_iter = target_llm.stream([HumanMessage(content=summary_prompt)])
            for chunk in stream_iter:
                if _should_stop():
                    break
                if hasattr(chunk, "content"):
                    summary_chunks.append(chunk.content)
                    yield chunk.content
                elif isinstance(chunk, str):
                    summary_chunks.append(chunk)
                    yield chunk
        except Exception as e:
            yield f"总结生成失败: {e}"
            return

        finally:
            if stream_iter is not None:
                close_fn = getattr(stream_iter, "close", None)
                if callable(close_fn):
                    try:
                        close_fn()
                    except Exception:
                        pass

        if summary_chunks:
            _SUMMARY_CACHE.set(summary_cache_key, "".join(summary_chunks))

        return


db_manager = DatabaseManager()
