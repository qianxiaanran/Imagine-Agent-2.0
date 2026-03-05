from __future__ import annotations

import hashlib
import json
import re
import threading
import os
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.engine import Connection

from deepseek_llm import ask_llm
from supabase_client import engine

router = APIRouter(prefix="/api/decision", tags=["Decision"])

_AI_REFRESH_SECONDS = max(60, int(os.getenv("DECISION_AI_REFRESH_SECONDS", str(30 * 60))))
_AI_CACHE_LOCK = threading.Lock()
_AI_CACHE: Dict[str, Dict[str, Any]] = {}
_AI_INFLIGHT: Dict[str, bool] = {}
_OVERVIEW_CACHE_SECONDS = max(10, int(os.getenv("DECISION_OVERVIEW_CACHE_SECONDS", "120")))
_OVERVIEW_CACHE_LOCK = threading.Lock()
_OVERVIEW_CACHE: Dict[str, Any] = {
    "payload": None,
    "generated_at": None,
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _to_float(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _pct(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _clamp_score(value: float) -> float:
    return max(0.0, min(100.0, round(value, 1)))


def _query_rows(conn: Connection, sql: str, params: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    result = conn.execute(text(sql), params or {})
    rows = result.mappings().all()
    return [dict(row) for row in rows]


def _query_one(conn: Connection, sql: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    rows = _query_rows(conn, sql, params)
    return rows[0] if rows else {}


def _clean_llm_json(raw: str) -> Dict[str, Any]:
    if not isinstance(raw, str):
        return {}
    text_value = raw.strip()
    if not text_value:
        return {}
    code_match = re.search(r"```json\s*([\s\S]*?)\s*```", text_value, flags=re.IGNORECASE)
    if code_match:
        text_value = code_match.group(1).strip()
    start = text_value.find("{")
    end = text_value.rfind("}")
    if start >= 0 and end > start:
        text_value = text_value[start : end + 1]
    try:
        parsed = json.loads(text_value)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalize_backend(value: str | None) -> str:
    backend = str(value or "local").strip().lower()
    if backend in {"cloud", "deepseek"}:
        return "cloud"
    return "local"


def _safe_list(raw: Any, max_items: int = 4) -> List[str]:
    if not isinstance(raw, list):
        return []
    values: List[str] = []
    for item in raw:
        text_value = str(item or "").strip()
        if text_value:
            values.append(text_value[:120])
        if len(values) >= max_items:
            break
    return values


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return _to_iso(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _fallback_ai_analysis(data: Dict[str, Any]) -> Dict[str, Any]:
    kpi_map = {item.get("key"): item for item in data.get("kpis", [])}
    sales_total = _to_float((kpi_map.get("sales_total") or {}).get("value"))
    margin_rate = _to_float((kpi_map.get("gross_margin_rate") or {}).get("value"))
    collection_rate = _to_float((kpi_map.get("collection_rate") or {}).get("value"))
    low_stock_count = _to_float((kpi_map.get("low_stock_sku") or {}).get("value"))

    summary = (
        f"当前销售规模约为 {sales_total:,.0f}，毛利率约 {margin_rate * 100:.1f}%，"
        f"回款率约 {collection_rate * 100:.1f}%。"
    )
    insights = [
        "销售与采购均有稳定流水，可用于月度经营复盘与预算滚动。",
        "回款质量与交付效率是当前利润兑现的关键环节。",
        f"低库存SKU数量为 {low_stock_count:,.0f}，需关注补货节奏与缺货风险。",
    ]
    actions = [
        "将未回款订单按客户分层，优先跟进金额高且账龄长的客户。",
        "按周滚动复盘低库存SKU与采购在途，建立销售-采购联动补货节奏。",
        "对高毛利且高销量产品设置优先排产/备货策略，提升盈利质量。",
    ]
    return {
        "summary": summary,
        "insights": insights,
        "actions": actions,
        "risk_outlook": "若回款与补货节奏不同步，未来一个经营周期内现金流与履约压力可能同步上升。",
    }


def _build_ai_context(data: Dict[str, Any]) -> Dict[str, Any]:
    kpi_map = {item.get("key"): item for item in data.get("kpis", [])}
    trend_rows = data.get("trends", [])
    recent_trend = trend_rows[-3:] if isinstance(trend_rows, list) else []
    warnings = data.get("warnings", [])
    return {
        "kpis": {
            "sales_total": _to_float((kpi_map.get("sales_total") or {}).get("value")),
            "purchase_total": _to_float((kpi_map.get("purchase_total") or {}).get("value")),
            "gross_margin_rate": _to_float((kpi_map.get("gross_margin_rate") or {}).get("value")),
            "collection_rate": _to_float((kpi_map.get("collection_rate") or {}).get("value")),
            "delivery_rate": _to_float((kpi_map.get("delivery_rate") or {}).get("value")),
            "inventory_turnover_proxy": _to_float((kpi_map.get("inventory_turnover_proxy") or {}).get("value")),
            "low_stock_sku": _to_int((kpi_map.get("low_stock_sku") or {}).get("value")),
        },
        "recent_trend": recent_trend,
        "warnings": warnings[:5] if isinstance(warnings, list) else [],
        "top_products": (data.get("top_products") or [])[:5],
    }


def _generate_ai_analysis(data: Dict[str, Any], backend: str) -> Dict[str, Any]:
    context_payload = _json_safe(_build_ai_context(data))
    prompt = (
        "你是进出口企业的经营分析顾问。请基于给定数据，输出管理层可执行的经营分析。\n"
        "要求：\n"
        "1) 只允许基于数据，不得编造。\n"
        "2) 用中文输出。\n"
        "3) 严格输出 JSON，不要任何额外文本。\n"
        "4) JSON 结构如下：\n"
        '{"summary":"", "insights":[""], "actions":[""], "risk_outlook":""}\n\n'
        f"经营数据：{json.dumps(context_payload, ensure_ascii=False)}"
    )

    raw = ask_llm(prompt, model_type=backend)
    parsed = _clean_llm_json(raw)
    if not parsed:
        return _fallback_ai_analysis(data)

    summary = str(parsed.get("summary") or "").strip()[:200]
    insights = _safe_list(parsed.get("insights"), max_items=4)
    actions = _safe_list(parsed.get("actions"), max_items=4)
    risk_outlook = str(parsed.get("risk_outlook") or "").strip()[:180]
    if not summary or not insights or not actions:
        return _fallback_ai_analysis(data)

    return {
        "summary": summary,
        "insights": insights,
        "actions": actions,
        "risk_outlook": risk_outlook or "请重点关注回款、库存与履约协同风险。",
    }


def _get_cached_ai_analysis(data: Dict[str, Any], backend: str, force_refresh: bool) -> Dict[str, Any]:
    context_payload = _json_safe(_build_ai_context(data))
    signature = hashlib.sha1(
        json.dumps(context_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    now = _utc_now()
    cache_key = backend

    with _AI_CACHE_LOCK:
        cached = _AI_CACHE.get(cache_key)
        if cached and not force_refresh:
            cached_signature = str(cached.get("signature") or "")
            cached_at = cached.get("generated_at")
            if isinstance(cached_at, datetime):
                age_seconds = int((now - cached_at).total_seconds())
                if age_seconds < _AI_REFRESH_SECONDS:
                    payload = dict(cached.get("payload") or {})
                    payload["generated_at"] = _to_iso(cached_at)
                    payload["expires_at"] = _to_iso(cached_at + timedelta(seconds=_AI_REFRESH_SECONDS))
                    payload["refresh_after_seconds"] = max(0, _AI_REFRESH_SECONDS - age_seconds)
                    payload["cached"] = True
                    payload["backend"] = backend
                    payload["cache_matched_signature"] = cached_signature == signature
                    return payload

        payload = _generate_ai_analysis(data, backend)
        _AI_CACHE[cache_key] = {
            "signature": signature,
            "payload": payload,
            "generated_at": now,
        }
        return {
            **payload,
            "generated_at": _to_iso(now),
            "expires_at": _to_iso(now + timedelta(seconds=_AI_REFRESH_SECONDS)),
            "refresh_after_seconds": _AI_REFRESH_SECONDS,
            "cached": False,
            "backend": backend,
            "cache_matched_signature": True,
        }


def _start_ai_refresh_async(data: Dict[str, Any], backend: str, signature: str):
    with _AI_CACHE_LOCK:
        if _AI_INFLIGHT.get(backend):
            return
        _AI_INFLIGHT[backend] = True

    snapshot = dict(data)

    def _worker():
        try:
            payload = _generate_ai_analysis(snapshot, backend)
        except Exception as exc:
            print(f"[Decision] Async AI analysis failed ({backend}): {exc}")
            payload = _fallback_ai_analysis(snapshot)
        finally:
            now = _utc_now()
            with _AI_CACHE_LOCK:
                _AI_CACHE[backend] = {
                    "signature": signature,
                    "payload": payload,
                    "generated_at": now,
                }
                _AI_INFLIGHT.pop(backend, None)

    threading.Thread(target=_worker, daemon=True).start()


def _get_ai_analysis_fast(data: Dict[str, Any], backend: str, force_refresh: bool) -> Dict[str, Any]:
    """
    Fast path for first load:
    - If cache exists and valid -> return cache.
    - If no cache and not forced -> return fallback immediately and refresh AI in background.
    - If forced -> block and compute latest AI.
    """
    context_payload = _json_safe(_build_ai_context(data))
    signature = hashlib.sha1(
        json.dumps(context_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    now = _utc_now()

    with _AI_CACHE_LOCK:
        cached = _AI_CACHE.get(backend)
        if cached and not force_refresh:
            cached_signature = str(cached.get("signature") or "")
            cached_at = cached.get("generated_at")
            if isinstance(cached_at, datetime):
                age_seconds = int((now - cached_at).total_seconds())
                if age_seconds < _AI_REFRESH_SECONDS:
                    payload = dict(cached.get("payload") or {})
                    payload["generated_at"] = _to_iso(cached_at)
                    payload["expires_at"] = _to_iso(cached_at + timedelta(seconds=_AI_REFRESH_SECONDS))
                    payload["refresh_after_seconds"] = max(0, _AI_REFRESH_SECONDS - age_seconds)
                    payload["cached"] = True
                    payload["backend"] = backend
                    payload["cache_matched_signature"] = cached_signature == signature
                    payload["pending"] = False
                    return payload

    if force_refresh:
        payload = _get_cached_ai_analysis(data, backend=backend, force_refresh=True)
        payload["pending"] = False
        return payload

    _start_ai_refresh_async(data, backend=backend, signature=signature)
    fallback = _fallback_ai_analysis(data)
    return {
        **fallback,
        "generated_at": _to_iso(now),
        "expires_at": _to_iso(now + timedelta(seconds=_AI_REFRESH_SECONDS)),
        "refresh_after_seconds": _AI_REFRESH_SECONDS,
        "cached": False,
        "backend": backend,
        "cache_matched_signature": False,
        "pending": True,
    }


def _collect_dashboard_data() -> Dict[str, Any]:
    now = _utc_now()
    with engine.begin() as conn:
        overview = _query_one(
            conn,
            """
            SELECT
              COALESCE(SUM(o.total_amount), 0) AS sales_total,
              COUNT(*) AS order_count,
              COALESCE(SUM(CASE WHEN o.payment_status = 'Paid' THEN o.total_amount ELSE 0 END), 0) AS paid_amount,
              COUNT(*) FILTER (WHERE o.payment_status = 'Paid') AS paid_orders,
              COALESCE(SUM(CASE WHEN o.delivery_status = 'Delivered' THEN o.total_amount ELSE 0 END), 0) AS delivered_amount,
              COUNT(*) FILTER (WHERE o.delivery_status = 'Delivered') AS delivered_orders,
              COUNT(*) FILTER (WHERE o.payment_status IN ('Pending', 'Unpaid', 'Partial')) AS at_risk_orders,
              COALESCE(SUM(CASE WHEN o.payment_status IN ('Pending', 'Unpaid', 'Partial') THEN o.total_amount ELSE 0 END), 0) AS at_risk_amount,
              COALESCE(SUM(CASE WHEN o.order_date >= CURRENT_DATE - INTERVAL '30 day' THEN o.total_amount ELSE 0 END), 0) AS sales_30d,
              COALESCE(SUM(CASE WHEN o.order_date >= CURRENT_DATE - INTERVAL '60 day' AND o.order_date < CURRENT_DATE - INTERVAL '30 day' THEN o.total_amount ELSE 0 END), 0) AS sales_prev_30d
            FROM public.orders o
            """
        )

        purchase_overview = _query_one(
            conn,
            """
            SELECT
              COALESCE(SUM(p.total_amount), 0) AS purchase_total,
              COUNT(*) AS purchase_count,
              COUNT(*) FILTER (WHERE p.status IN ('Pending', 'Processing')) AS open_purchase_count,
              COALESCE(SUM(CASE WHEN p.status IN ('Pending', 'Processing') THEN p.total_amount ELSE 0 END), 0) AS open_purchase_amount,
              COALESCE(SUM(CASE WHEN p.purchase_date >= CURRENT_DATE - INTERVAL '30 day' THEN p.total_amount ELSE 0 END), 0) AS purchase_30d,
              COALESCE(SUM(CASE WHEN p.purchase_date >= CURRENT_DATE - INTERVAL '60 day' AND p.purchase_date < CURRENT_DATE - INTERVAL '30 day' THEN p.total_amount ELSE 0 END), 0) AS purchase_prev_30d
            FROM public.purchases p
            """
        )

        inventory_overview = _query_one(
            conn,
            """
            SELECT
              COALESCE(SUM(i.quantity), 0) AS inventory_units,
              COUNT(*) AS inventory_lines,
              COUNT(*) FILTER (WHERE i.quantity <= COALESCE(p.min_stock, 0)) AS low_stock_lines,
              COALESCE(SUM(CASE WHEN i.quantity <= COALESCE(p.min_stock, 0) THEN i.quantity ELSE 0 END), 0) AS low_stock_units,
              COALESCE(SUM(i.quantity * COALESCE(p.purchase_price, 0)), 0) AS inventory_value
            FROM public.inventory i
            JOIN public.products p ON p.prod_id = i.prod_id
            """
        )

        sales_units = _query_one(
            conn,
            """
            SELECT
              COALESCE(SUM(CASE WHEN o.order_date >= CURRENT_DATE - INTERVAL '30 day' THEN oi.quantity ELSE 0 END), 0) AS sold_units_30d,
              COALESCE(SUM(CASE WHEN o.order_date >= CURRENT_DATE - INTERVAL '60 day' AND o.order_date < CURRENT_DATE - INTERVAL '30 day' THEN oi.quantity ELSE 0 END), 0) AS sold_units_prev_30d
            FROM public.order_items oi
            JOIN public.orders o ON o.order_id = oi.order_id
            """
        )

        employee_overview = _query_one(
            conn,
            """
            SELECT
              COUNT(*) AS total_employees,
              COUNT(*) FILTER (WHERE status = 'Active') AS active_employees,
              COALESCE(AVG(salary), 0) AS avg_salary
            FROM public.employees
            """
        )

        customer_supplier = _query_one(
            conn,
            """
            SELECT
              (SELECT COUNT(*) FROM public.customers) AS total_customers,
              (SELECT COUNT(*) FROM public.suppliers) AS total_suppliers,
              (SELECT COUNT(DISTINCT cust_id) FROM public.orders WHERE order_date >= CURRENT_DATE - INTERVAL '90 day') AS active_customers_90d,
              (SELECT COUNT(DISTINCT supp_id) FROM public.purchases WHERE purchase_date >= CURRENT_DATE - INTERVAL '90 day') AS active_suppliers_90d
            """
        )

        trend_rows = _query_rows(
            conn,
            """
            WITH months AS (
              SELECT date_trunc('month', CURRENT_DATE) - (gs * INTERVAL '1 month') AS month_start
              FROM generate_series(11, 0, -1) AS gs
            ),
            sales AS (
              SELECT date_trunc('month', order_date) AS month_start, SUM(total_amount) AS amount, COUNT(*) AS orders
              FROM public.orders
              WHERE order_date >= date_trunc('month', CURRENT_DATE) - INTERVAL '11 month'
              GROUP BY 1
            ),
            purchases AS (
              SELECT date_trunc('month', purchase_date) AS month_start, SUM(total_amount) AS amount, COUNT(*) AS orders
              FROM public.purchases
              WHERE purchase_date >= date_trunc('month', CURRENT_DATE) - INTERVAL '11 month'
              GROUP BY 1
            )
            SELECT
              TO_CHAR(m.month_start, 'YYYY-MM') AS month,
              COALESCE(s.amount, 0) AS sales_amount,
              COALESCE(s.orders, 0) AS sales_orders,
              COALESCE(p.amount, 0) AS purchase_amount,
              COALESCE(p.orders, 0) AS purchase_orders
            FROM months m
            LEFT JOIN sales s ON s.month_start = m.month_start
            LEFT JOIN purchases p ON p.month_start = m.month_start
            ORDER BY m.month_start
            """
        )

        payment_breakdown = _query_rows(
            conn,
            """
            SELECT payment_status AS status, COUNT(*) AS order_count, COALESCE(SUM(total_amount), 0) AS amount
            FROM public.orders
            GROUP BY payment_status
            ORDER BY amount DESC
            """
        )

        delivery_breakdown = _query_rows(
            conn,
            """
            SELECT delivery_status AS status, COUNT(*) AS order_count, COALESCE(SUM(total_amount), 0) AS amount
            FROM public.orders
            GROUP BY delivery_status
            ORDER BY amount DESC
            """
        )

        purchase_status_breakdown = _query_rows(
            conn,
            """
            SELECT status, COUNT(*) AS purchase_count, COALESCE(SUM(total_amount), 0) AS amount
            FROM public.purchases
            GROUP BY status
            ORDER BY amount DESC
            """
        )

        top_products = _query_rows(
            conn,
            """
            SELECT
              p.prod_name,
              p.category,
              COALESCE(SUM(oi.total_price), 0) AS revenue,
              COALESCE(SUM(oi.quantity), 0) AS sold_units
            FROM public.order_items oi
            JOIN public.products p ON p.prod_id = oi.prod_id
            JOIN public.orders o ON o.order_id = oi.order_id
            WHERE o.order_date >= CURRENT_DATE - INTERVAL '180 day'
            GROUP BY p.prod_id, p.prod_name, p.category
            ORDER BY revenue DESC
            LIMIT 8
            """
        )

        category_profit = _query_rows(
            conn,
            """
            SELECT
              p.category,
              COALESCE(SUM(oi.total_price), 0) AS sales_amount,
              COALESCE(SUM(oi.quantity * COALESCE(p.purchase_price, 0)), 0) AS cost_amount
            FROM public.order_items oi
            JOIN public.products p ON p.prod_id = oi.prod_id
            JOIN public.orders o ON o.order_id = oi.order_id
            WHERE o.order_date >= CURRENT_DATE - INTERVAL '180 day'
            GROUP BY p.category
            ORDER BY sales_amount DESC
            LIMIT 8
            """
        )

        warehouses = _query_rows(
            conn,
            """
            SELECT warehouse, COALESCE(SUM(quantity), 0) AS units, COUNT(*) AS line_count
            FROM public.inventory
            GROUP BY warehouse
            ORDER BY units DESC
            """
        )

        customer_risk = _query_rows(
            conn,
            """
            SELECT
              c.cust_name,
              COUNT(*) AS risk_order_count,
              COALESCE(SUM(o.total_amount), 0) AS risk_amount,
              MAX(o.order_date) AS latest_order_date
            FROM public.orders o
            JOIN public.customers c ON c.cust_id = o.cust_id
            WHERE o.payment_status IN ('Pending', 'Unpaid', 'Partial')
            GROUP BY c.cust_id, c.cust_name
            ORDER BY risk_amount DESC
            LIMIT 8
            """
        )

        low_stock_items = _query_rows(
            conn,
            """
            SELECT
              p.prod_name,
              p.category,
              COALESCE(SUM(i.quantity), 0) AS stock_qty,
              COALESCE(MAX(p.min_stock), 0) AS min_stock
            FROM public.inventory i
            JOIN public.products p ON p.prod_id = i.prod_id
            GROUP BY p.prod_id, p.prod_name, p.category
            HAVING COALESCE(SUM(i.quantity), 0) <= COALESCE(MAX(p.min_stock), 0)
            ORDER BY (COALESCE(MAX(p.min_stock), 0) - COALESCE(SUM(i.quantity), 0)) DESC
            LIMIT 8
            """
        )

        supplier_risk = _query_rows(
            conn,
            """
            SELECT
              s.supp_name,
              COUNT(*) AS open_purchase_count,
              COALESCE(SUM(p.total_amount), 0) AS open_amount
            FROM public.purchases p
            JOIN public.suppliers s ON s.supp_id = p.supp_id
            WHERE p.status IN ('Pending', 'Processing')
            GROUP BY s.supp_id, s.supp_name
            ORDER BY open_amount DESC
            LIMIT 8
            """
        )

    sales_total = _to_float(overview.get("sales_total"))
    purchase_total = _to_float(purchase_overview.get("purchase_total"))
    gross_profit = sales_total - purchase_total
    gross_margin_rate = _pct(gross_profit, sales_total)
    order_count = _to_int(overview.get("order_count"))
    paid_orders = _to_int(overview.get("paid_orders"))
    delivered_orders = _to_int(overview.get("delivered_orders"))
    at_risk_orders = _to_int(overview.get("at_risk_orders"))
    at_risk_amount = _to_float(overview.get("at_risk_amount"))
    paid_amount = _to_float(overview.get("paid_amount"))
    delivered_amount = _to_float(overview.get("delivered_amount"))

    purchase_count = _to_int(purchase_overview.get("purchase_count"))
    open_purchase_count = _to_int(purchase_overview.get("open_purchase_count"))
    open_purchase_amount = _to_float(purchase_overview.get("open_purchase_amount"))

    sales_30d = _to_float(overview.get("sales_30d"))
    sales_prev_30d = _to_float(overview.get("sales_prev_30d"))
    purchase_30d = _to_float(purchase_overview.get("purchase_30d"))
    purchase_prev_30d = _to_float(purchase_overview.get("purchase_prev_30d"))
    sales_growth_30d = _pct((sales_30d - sales_prev_30d), sales_prev_30d) if sales_prev_30d > 0 else 0.0
    purchase_growth_30d = _pct((purchase_30d - purchase_prev_30d), purchase_prev_30d) if purchase_prev_30d > 0 else 0.0

    inventory_units = _to_float(inventory_overview.get("inventory_units"))
    inventory_value = _to_float(inventory_overview.get("inventory_value"))
    low_stock_lines = _to_int(inventory_overview.get("low_stock_lines"))
    low_stock_units = _to_float(inventory_overview.get("low_stock_units"))

    sold_units_30d = _to_float(sales_units.get("sold_units_30d"))
    sold_units_prev_30d = _to_float(sales_units.get("sold_units_prev_30d"))
    inventory_turnover_proxy = _pct(sold_units_30d, inventory_units) if inventory_units > 0 else 0.0

    total_customers = _to_int(customer_supplier.get("total_customers"))
    active_customers_90d = _to_int(customer_supplier.get("active_customers_90d"))
    total_suppliers = _to_int(customer_supplier.get("total_suppliers"))
    active_suppliers_90d = _to_int(customer_supplier.get("active_suppliers_90d"))

    total_employees = _to_int(employee_overview.get("total_employees"))
    active_employees = _to_int(employee_overview.get("active_employees"))
    avg_salary = _to_float(employee_overview.get("avg_salary"))

    collection_rate = _pct(paid_amount, sales_total)
    delivery_rate = _pct(delivered_amount, sales_total)
    at_risk_order_ratio = _pct(at_risk_orders, order_count)
    open_purchase_ratio = _pct(open_purchase_count, purchase_count)
    low_stock_ratio = _pct(low_stock_lines, max(_to_int(inventory_overview.get("inventory_lines")), 1))
    customer_activity_rate = _pct(active_customers_90d, max(total_customers, 1))
    supplier_activity_rate = _pct(active_suppliers_90d, max(total_suppliers, 1))

    profit_score = _clamp_score(40 + gross_margin_rate * 260)
    operation_score = _clamp_score(35 + collection_rate * 35 + delivery_rate * 30)
    supply_score = _clamp_score(45 + supplier_activity_rate * 35 - open_purchase_ratio * 30)
    inventory_score = _clamp_score(55 + min(inventory_turnover_proxy, 2.5) * 12 - low_stock_ratio * 30)
    finance_score = _clamp_score(42 + collection_rate * 38 - at_risk_order_ratio * 32)
    growth_score = _clamp_score(55 + sales_growth_30d * 80 - abs(purchase_growth_30d - sales_growth_30d) * 35)

    capability_rows = [
        {"key": "profit", "label": "盈利能力", "score": profit_score, "desc": "毛利率与利润空间"},
        {"key": "operation", "label": "运营能力", "score": operation_score, "desc": "回款与履约协同表现"},
        {"key": "supply", "label": "供应能力", "score": supply_score, "desc": "采购状态与供应活跃度"},
        {"key": "inventory", "label": "存货能力", "score": inventory_score, "desc": "库存周转与低库存控制"},
        {"key": "finance", "label": "财务能力", "score": finance_score, "desc": "账款风险与现金兑现能力"},
        {"key": "growth", "label": "增长能力", "score": growth_score, "desc": "近两期销售增长与稳定性"},
    ]
    cockpit_score = round(sum(item["score"] for item in capability_rows) / max(len(capability_rows), 1), 1)

    warnings: List[Dict[str, Any]] = []
    if at_risk_order_ratio >= 0.35:
        warnings.append(
            {
                "level": "high",
                "module": "财务预警",
                "title": "应收风险订单占比较高",
                "description": f"风险订单占比 {at_risk_order_ratio * 100:.1f}%，涉及金额约 {at_risk_amount:,.0f}。",
                "metric": round(at_risk_order_ratio * 100, 2),
            }
        )
    if low_stock_lines > 0:
        warnings.append(
            {
                "level": "medium" if low_stock_ratio < 0.25 else "high",
                "module": "库存预警",
                "title": "低库存SKU需要补货排程",
                "description": f"低库存SKU {low_stock_lines} 项，低库存总量 {low_stock_units:,.0f}。",
                "metric": low_stock_lines,
            }
        )
    if open_purchase_ratio >= 0.3:
        warnings.append(
            {
                "level": "medium",
                "module": "供应预警",
                "title": "在途采购占比偏高",
                "description": f"未完成采购占比 {open_purchase_ratio * 100:.1f}%，金额约 {open_purchase_amount:,.0f}。",
                "metric": round(open_purchase_ratio * 100, 2),
            }
        )
    if sales_growth_30d < -0.1:
        warnings.append(
            {
                "level": "high",
                "module": "经营预警",
                "title": "近30日销售额出现回落",
                "description": f"相较前30日变动 {sales_growth_30d * 100:.1f}%，建议复盘重点客户和重点品类。",
                "metric": round(sales_growth_30d * 100, 2),
            }
        )
    if not warnings:
        warnings.append(
            {
                "level": "low",
                "module": "运行状态",
                "title": "关键指标处于可控区间",
                "description": "暂无高等级异常，请继续按周监控回款、交付和库存水位。",
                "metric": 0,
            }
        )

    risk_table: List[Dict[str, Any]] = []
    for row in customer_risk[:5]:
        risk_table.append(
            {
                "category": "客户回款",
                "name": row.get("cust_name") or "-",
                "value": _to_float(row.get("risk_amount")),
                "count": _to_int(row.get("risk_order_count")),
                "note": f"最近订单日期 {row.get('latest_order_date')}",
            }
        )
    for row in low_stock_items[:5]:
        risk_table.append(
            {
                "category": "库存缺口",
                "name": row.get("prod_name") or "-",
                "value": _to_float(row.get("stock_qty")),
                "count": _to_int(row.get("min_stock")),
                "note": "当前库存 / 最低库存",
            }
        )
    for row in supplier_risk[:5]:
        risk_table.append(
            {
                "category": "采购积压",
                "name": row.get("supp_name") or "-",
                "value": _to_float(row.get("open_amount")),
                "count": _to_int(row.get("open_purchase_count")),
                "note": "待完成采购金额与单量",
            }
        )

    kpis = [
        {
            "key": "sales_total",
            "label": "累计销售额",
            "value": sales_total,
            "unit": "CNY",
            "trend": sales_growth_30d,
            "target_progress": round(min(max(collection_rate, 0.0), 1.0), 4),
        },
        {
            "key": "purchase_total",
            "label": "累计采购额",
            "value": purchase_total,
            "unit": "CNY",
            "trend": purchase_growth_30d,
            "target_progress": round(1 - min(max(open_purchase_ratio, 0.0), 1.0), 4),
        },
        {
            "key": "gross_margin_rate",
            "label": "综合毛利率",
            "value": gross_margin_rate,
            "unit": "ratio",
            "trend": gross_margin_rate - 0.2,
            "target_progress": round(min(max(gross_margin_rate / 0.35, 0.0), 1.0), 4),
        },
        {
            "key": "collection_rate",
            "label": "回款率",
            "value": collection_rate,
            "unit": "ratio",
            "trend": collection_rate - 0.75,
            "target_progress": round(min(max(collection_rate, 0.0), 1.0), 4),
        },
        {
            "key": "delivery_rate",
            "label": "履约率",
            "value": delivery_rate,
            "unit": "ratio",
            "trend": delivery_rate - 0.78,
            "target_progress": round(min(max(delivery_rate, 0.0), 1.0), 4),
        },
        {
            "key": "inventory_turnover_proxy",
            "label": "库存周转(30日)",
            "value": inventory_turnover_proxy,
            "unit": "times",
            "trend": _pct((sold_units_30d - sold_units_prev_30d), sold_units_prev_30d) if sold_units_prev_30d > 0 else 0.0,
            "target_progress": round(min(max(inventory_turnover_proxy / 1.2, 0.0), 1.0), 4),
        },
        {
            "key": "low_stock_sku",
            "label": "低库存SKU",
            "value": low_stock_lines,
            "unit": "count",
            "trend": -low_stock_ratio,
            "target_progress": round(min(max(1 - low_stock_ratio, 0.0), 1.0), 4),
        },
        {
            "key": "active_customers_90d",
            "label": "90日活跃客户",
            "value": active_customers_90d,
            "unit": "count",
            "trend": customer_activity_rate - 0.5,
            "target_progress": round(min(max(customer_activity_rate, 0.0), 1.0), 4),
        },
    ]

    formatted_trends: List[Dict[str, Any]] = []
    for row in trend_rows:
        sales_amount_value = _to_float(row.get("sales_amount"))
        purchase_amount_value = _to_float(row.get("purchase_amount"))
        formatted_trends.append(
            {
                "month": row.get("month"),
                "sales_amount": sales_amount_value,
                "purchase_amount": purchase_amount_value,
                "net_amount": sales_amount_value - purchase_amount_value,
                "sales_orders": _to_int(row.get("sales_orders")),
                "purchase_orders": _to_int(row.get("purchase_orders")),
            }
        )

    category_profit_rows: List[Dict[str, Any]] = []
    for row in category_profit:
        sales_amount_value = _to_float(row.get("sales_amount"))
        cost_amount_value = _to_float(row.get("cost_amount"))
        margin_value = _pct((sales_amount_value - cost_amount_value), sales_amount_value)
        category_profit_rows.append(
            {
                "category": row.get("category") or "Unknown",
                "sales_amount": sales_amount_value,
                "cost_amount": cost_amount_value,
                "profit_amount": sales_amount_value - cost_amount_value,
                "margin_rate": margin_value,
            }
        )

    return {
        "generated_at": _to_iso(now),
        "refresh_interval_minutes": 30,
        "kpis": kpis,
        "cockpit": {
            "score": cockpit_score,
            "capabilities": capability_rows,
            "meta": {
                "sales_30d": sales_30d,
                "sales_prev_30d": sales_prev_30d,
                "purchase_30d": purchase_30d,
                "purchase_prev_30d": purchase_prev_30d,
                "inventory_units": inventory_units,
                "inventory_value": inventory_value,
                "active_employees": active_employees,
                "total_employees": total_employees,
                "avg_salary": avg_salary,
            },
        },
        "trends": formatted_trends,
        "breakdowns": {
            "payment": payment_breakdown,
            "delivery": delivery_breakdown,
            "purchase_status": purchase_status_breakdown,
        },
        "top_products": top_products,
        "category_profit": category_profit_rows,
        "warehouses": warehouses,
        "warnings": warnings,
        "risk_table": risk_table,
        "totals": {
            "order_count": order_count,
            "purchase_count": purchase_count,
            "paid_orders": paid_orders,
            "delivered_orders": delivered_orders,
            "at_risk_orders": at_risk_orders,
            "total_customers": total_customers,
            "total_suppliers": total_suppliers,
            "active_customers_90d": active_customers_90d,
            "active_suppliers_90d": active_suppliers_90d,
            "gross_profit": gross_profit,
        },
    }


def _get_cached_dashboard_data(force_refresh: bool = False) -> Dict[str, Any]:
    now = _utc_now()
    with _OVERVIEW_CACHE_LOCK:
        cached_payload = _OVERVIEW_CACHE.get("payload")
        cached_at = _OVERVIEW_CACHE.get("generated_at")
        if (
            (not force_refresh)
            and isinstance(cached_payload, dict)
            and isinstance(cached_at, datetime)
            and int((now - cached_at).total_seconds()) < _OVERVIEW_CACHE_SECONDS
        ):
            result = dict(cached_payload)
            result["cache"] = {
                "dashboard_cached": True,
                "dashboard_generated_at": _to_iso(cached_at),
                "dashboard_ttl_seconds": _OVERVIEW_CACHE_SECONDS,
            }
            return result

    fresh = _collect_dashboard_data()
    with _OVERVIEW_CACHE_LOCK:
        _OVERVIEW_CACHE["payload"] = fresh
        _OVERVIEW_CACHE["generated_at"] = now
    result = dict(fresh)
    result["cache"] = {
        "dashboard_cached": False,
        "dashboard_generated_at": _to_iso(now),
        "dashboard_ttl_seconds": _OVERVIEW_CACHE_SECONDS,
    }
    return result


def warmup_decision_cache():
    """
    Warm decision dashboard and AI cache on startup to reduce first-request latency.
    Runs in background thread from main.py startup hook.
    """
    try:
        backend = _normalize_backend(os.getenv("DECISION_WARMUP_AI_BACKEND", "local"))
        data = _get_cached_dashboard_data(force_refresh=True)
        _get_cached_ai_analysis(data, backend=backend, force_refresh=True)
        print(f"[Decision] warmup completed (backend={backend})")
    except Exception as exc:
        print(f"[Decision] warmup failed: {exc}")


@router.get("/overview")
def get_decision_overview(
    refresh_ai: bool = Query(default=False, description="Whether to force refresh AI analysis"),
    refresh_data: bool = Query(default=False, description="Whether to force refresh dashboard aggregates"),
    analysis_backend: str = Query(default="local", description="local | cloud"),
):
    backend = _normalize_backend(analysis_backend)
    try:
        data = _get_cached_dashboard_data(force_refresh=refresh_data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load dashboard data: {exc}") from exc

    ai_payload = _get_ai_analysis_fast(data, backend=backend, force_refresh=refresh_ai)
    return {
        **data,
        "ai_analysis": ai_payload,
    }


@router.get("/data")
def get_decision_data(
    refresh_data: bool = Query(default=False, description="Whether to force refresh dashboard aggregates"),
):
    try:
        return _get_cached_dashboard_data(force_refresh=refresh_data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load decision data: {exc}") from exc


@router.get("/ai")
def get_decision_ai(
    refresh_ai: bool = Query(default=False, description="Whether to force refresh AI analysis"),
    analysis_backend: str = Query(default="local", description="local | cloud"),
    refresh_data: bool = Query(default=False, description="Whether to refresh dashboard data before AI analysis"),
):
    backend = _normalize_backend(analysis_backend)
    try:
        data = _get_cached_dashboard_data(force_refresh=refresh_data)
        ai_payload = _get_ai_analysis_fast(data, backend=backend, force_refresh=refresh_ai)
        return {
            "ai_analysis": ai_payload,
            "data_generated_at": data.get("generated_at"),
            "cache": data.get("cache"),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load decision AI analysis: {exc}") from exc
