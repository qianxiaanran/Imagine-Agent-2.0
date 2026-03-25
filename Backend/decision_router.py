from __future__ import annotations

import hashlib
import json
import re
import threading
import os
from decimal import Decimal
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.engine import Connection

from deepseek_llm import ask_llm
from supabase_client import engine

router = APIRouter(prefix="/api/decision", tags=["Decision"])

_AI_REFRESH_SECONDS = max(60, int(os.getenv("DECISION_AI_REFRESH_SECONDS", str(30 * 60))))
_AI_CACHE_MAX_ENTRIES = max(4, int(os.getenv("DECISION_AI_CACHE_MAX_ENTRIES", "12")))
_AI_CACHE_LOCK = threading.Lock()
_AI_CACHE: Dict[str, Dict[str, Any]] = {}
_AI_INFLIGHT: Dict[str, bool] = {}
_OVERVIEW_CACHE_SECONDS = max(10, int(os.getenv("DECISION_OVERVIEW_CACHE_SECONDS", "120")))
_PREAGG_REFRESH_SECONDS = max(60, int(os.getenv("DECISION_PREAGG_REFRESH_SECONDS", "180")))
_PREAGG_MAX_STALE_SECONDS = max(
    _PREAGG_REFRESH_SECONDS,
    int(os.getenv("DECISION_PREAGG_MAX_STALE_SECONDS", str(_PREAGG_REFRESH_SECONDS * 5))),
)
_PREAGG_CACHE_LOCK = threading.Lock()
_PREAGG_CACHE: Dict[str, Any] = {
    "payload": None,
    "generated_at": None,
    "refreshing": False,
    "last_error": None,
}
_RISK_PAYMENT_STATUSES = ("Pending", "Unpaid", "Partial")
_TREND_GRANULARITY_OPTIONS = ("week", "month", "quarter")
_OBJECT_GROUP_ORDER = ("customer", "sku", "receivable", "inventory")
_OBJECT_GROUP_LABELS = {
    "customer": "客户",
    "sku": "SKU",
    "receivable": "回款项",
    "inventory": "库存对象",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _make_ai_cache_signature(data: Dict[str, Any]) -> str:
    context_payload = _json_safe(_build_ai_context(data))
    return hashlib.sha1(
        json.dumps(context_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _make_ai_cache_key(backend: str, signature: str) -> str:
    return f"{backend}:{signature}"


def _prune_ai_cache_locked() -> None:
    if len(_AI_CACHE) <= _AI_CACHE_MAX_ENTRIES:
        return
    ordered_items = sorted(
        _AI_CACHE.items(),
        key=lambda item: item[1].get("generated_at") or datetime.min.replace(tzinfo=timezone.utc),
    )
    for cache_key, _ in ordered_items[: max(0, len(_AI_CACHE) - _AI_CACHE_MAX_ENTRIES)]:
        _AI_CACHE.pop(cache_key, None)


def _with_preaggregation_meta(
    payload: Dict[str, Any],
    generated_at: datetime,
    *,
    dashboard_cached: bool,
    stale: bool,
    pending_refresh: bool,
    last_error: str | None,
) -> Dict[str, Any]:
    result = dict(payload or {})
    cache_meta = dict(result.get("cache") or {})
    age_seconds = max(0, int((_utc_now() - generated_at).total_seconds()))
    cache_meta.update(
        {
            "dashboard_cached": dashboard_cached,
            "dashboard_generated_at": _to_iso(generated_at),
            "dashboard_ttl_seconds": _OVERVIEW_CACHE_SECONDS,
            "preaggregation_enabled": True,
            "preaggregation_generated_at": _to_iso(generated_at),
            "preaggregation_age_seconds": age_seconds,
            "preaggregation_refresh_seconds": _PREAGG_REFRESH_SECONDS,
            "preaggregation_max_stale_seconds": _PREAGG_MAX_STALE_SECONDS,
            "preaggregation_stale": stale,
            "preaggregation_pending_refresh": pending_refresh,
        }
    )
    if last_error:
        cache_meta["preaggregation_last_error"] = last_error
    result["cache"] = cache_meta
    return result


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
    backend = str(value or "cloud").strip().lower()
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
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _normalize_trend_granularity(value: str | None) -> str:
    normalized = str(value or "month").strip().lower()
    if normalized in _TREND_GRANULARITY_OPTIONS:
        return normalized
    return "month"


def _format_drilldown_number(value: Any, unit: str | None = None) -> str:
    numeric = _to_float(value)
    if unit == "CNY":
        return f"{numeric:,.0f}"
    if unit == "ratio":
        return f"{numeric * 100:.1f}%"
    if unit == "count":
        return f"{int(round(numeric)):,d}"
    return str(value or "-")


def _normalize_evidence_items(raw: Any, fallback: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(raw, list):
        return fallback
    items: List[Dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()[:40]
        if not label:
            continue
        value = item.get("value")
        unit = str(item.get("unit") or "").strip()[:16]
        description = str(item.get("description") or item.get("note") or "").strip()[:120]
        items.append(
            {
                "label": label,
                "value": value,
                "unit": unit,
                "description": description,
                "display_value": str(item.get("display_value") or _format_drilldown_number(value, unit))[:60],
            }
        )
        if len(items) >= 6:
            break
    return items or fallback


def _build_ai_evidence_data(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    kpi_map = {item.get("key"): item for item in data.get("kpis", [])}
    cockpit_meta = (data.get("cockpit") or {}).get("meta") if isinstance(data.get("cockpit"), dict) else {}
    totals = data.get("totals") if isinstance(data.get("totals"), dict) else {}
    warnings = data.get("warnings") if isinstance(data.get("warnings"), list) else []

    evidence_rows = [
        {
            "label": "近30日销售额",
            "value": _to_float((cockpit_meta or {}).get("sales_30d")),
            "unit": "CNY",
            "description": "订单表近30日销售金额汇总",
        },
        {
            "label": "回款率",
            "value": _to_float((kpi_map.get("collection_rate") or {}).get("value")),
            "unit": "ratio",
            "description": "已回款金额 / 累计销售额",
        },
        {
            "label": "风险订单数",
            "value": _to_int((totals or {}).get("at_risk_orders")),
            "unit": "count",
            "description": "付款状态为 Pending / Unpaid / Partial 的订单数量",
        },
        {
            "label": "低库存SKU",
            "value": _to_int((kpi_map.get("low_stock_sku") or {}).get("value")),
            "unit": "count",
            "description": "库存量低于或等于安全库存的 SKU 数量",
        },
        {
            "label": "库存估值",
            "value": _to_float((cockpit_meta or {}).get("inventory_value")),
            "unit": "CNY",
            "description": "当前库存数量 × 采购单价估算",
        },
        {
            "label": "预警条数",
            "value": len(warnings),
            "unit": "count",
            "description": "当前规则生成的经营预警数量",
        },
    ]
    for row in evidence_rows:
        row["display_value"] = _format_drilldown_number(row.get("value"), row.get("unit"))
    return evidence_rows


def _finalize_ai_analysis_payload(payload: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    evidence_fallback = _build_ai_evidence_data(data)
    summary = str(payload.get("core_conclusion") or payload.get("summary") or "").strip()[:220]
    risk_reasons = _safe_list(payload.get("risk_reasons"), max_items=4) or _safe_list(payload.get("insights"), max_items=4)
    suggested_actions = _safe_list(payload.get("suggested_actions"), max_items=4) or _safe_list(payload.get("actions"), max_items=4)
    risk_outlook = str(payload.get("risk_outlook") or "").strip()[:180]

    if not summary:
        summary = str((evidence_fallback[0] or {}).get("description") or "暂无 AI 分析结果。")
    if not risk_reasons:
        risk_reasons = _safe_list(payload.get("insights"), max_items=4)
    if not suggested_actions:
        suggested_actions = _safe_list(payload.get("actions"), max_items=4)

    evidence_data = _normalize_evidence_items(payload.get("evidence_data"), evidence_fallback)
    normalized = {
        "summary": summary,
        "core_conclusion": summary,
        "insights": risk_reasons,
        "risk_reasons": risk_reasons,
        "actions": suggested_actions,
        "suggested_actions": suggested_actions,
        "risk_outlook": risk_outlook or "请重点关注回款、库存与履约协同风险。",
        "evidence_data": evidence_data,
    }
    return normalized


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
    payload = {
        "summary": summary,
        "insights": insights,
        "actions": actions,
        "risk_outlook": "若回款与补货节奏不同步，未来一个经营周期内现金流与履约压力可能同步上升。",
        "evidence_data": _build_ai_evidence_data(data),
    }
    return _finalize_ai_analysis_payload(payload, data)


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
        '{"core_conclusion":"", "risk_reasons":[""], "suggested_actions":[""], "risk_outlook":"", "evidence_data":[{"label":"","value":"","unit":"","description":""}]}\n\n'
        f"经营数据：{json.dumps(context_payload, ensure_ascii=False)}"
    )

    raw = ask_llm(prompt, model_type=backend)
    parsed = _clean_llm_json(raw)
    if not parsed:
        return _fallback_ai_analysis(data)

    normalized = _finalize_ai_analysis_payload(parsed, data)
    if not normalized.get("core_conclusion") or not normalized.get("risk_reasons") or not normalized.get("suggested_actions"):
        return _fallback_ai_analysis(data)
    return normalized


def _get_cached_ai_analysis(data: Dict[str, Any], backend: str, force_refresh: bool) -> Dict[str, Any]:
    signature = _make_ai_cache_signature(data)
    now = _utc_now()
    cache_key = _make_ai_cache_key(backend, signature)

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
        _prune_ai_cache_locked()
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
    cache_key = _make_ai_cache_key(backend, signature)
    with _AI_CACHE_LOCK:
        if _AI_INFLIGHT.get(cache_key):
            return
        _AI_INFLIGHT[cache_key] = True

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
                _AI_CACHE[cache_key] = {
                    "signature": signature,
                    "payload": payload,
                    "generated_at": now,
                }
                _prune_ai_cache_locked()
                _AI_INFLIGHT.pop(cache_key, None)

    threading.Thread(target=_worker, daemon=True).start()


def _get_ai_analysis_fast(data: Dict[str, Any], backend: str, force_refresh: bool) -> Dict[str, Any]:
    """
    Fast path for first load:
    - If cache exists and valid -> return cache.
    - If no cache and not forced -> return fallback immediately and refresh AI in background.
    - If forced -> block and compute latest AI.
    """
    signature = _make_ai_cache_signature(data)
    now = _utc_now()
    cache_key = _make_ai_cache_key(backend, signature)

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


def _query_trend_rows_by_granularity(conn: Connection, granularity: str) -> List[Dict[str, Any]]:
    normalized = _normalize_trend_granularity(granularity)
    if normalized == "week":
        return _query_rows(
            conn,
            """
            WITH periods AS (
              SELECT date_trunc('week', CURRENT_DATE) - (gs * INTERVAL '1 week') AS period_start
              FROM generate_series(11, 0, -1) AS gs
            ),
            sales AS (
              SELECT date_trunc('week', order_date) AS period_start, SUM(total_amount) AS amount, COUNT(*) AS orders
              FROM public.orders
              WHERE order_date >= date_trunc('week', CURRENT_DATE) - INTERVAL '11 week'
              GROUP BY 1
            ),
            purchases AS (
              SELECT date_trunc('week', purchase_date) AS period_start, SUM(total_amount) AS amount, COUNT(*) AS orders
              FROM public.purchases
              WHERE purchase_date >= date_trunc('week', CURRENT_DATE) - INTERVAL '11 week'
              GROUP BY 1
            )
            SELECT
              (TO_CHAR(p.period_start, 'IYYY') || '-W' || TO_CHAR(p.period_start, 'IW')) AS bucket,
              (TO_CHAR(p.period_start, 'MM-DD') || ' 周') AS label,
              p.period_start::date AS period_start,
              (p.period_start + INTERVAL '6 day')::date AS period_end,
              COALESCE(s.amount, 0) AS sales_amount,
              COALESCE(s.orders, 0) AS sales_orders,
              COALESCE(pr.amount, 0) AS purchase_amount,
              COALESCE(pr.orders, 0) AS purchase_orders
            FROM periods p
            LEFT JOIN sales s ON s.period_start = p.period_start
            LEFT JOIN purchases pr ON pr.period_start = p.period_start
            ORDER BY p.period_start
            """
        )
    if normalized == "quarter":
        return _query_rows(
            conn,
            """
            WITH periods AS (
              SELECT date_trunc('quarter', CURRENT_DATE) - (gs * INTERVAL '3 month') AS period_start
              FROM generate_series(7, 0, -1) AS gs
            ),
            sales AS (
              SELECT date_trunc('quarter', order_date) AS period_start, SUM(total_amount) AS amount, COUNT(*) AS orders
              FROM public.orders
              WHERE order_date >= date_trunc('quarter', CURRENT_DATE) - INTERVAL '21 month'
              GROUP BY 1
            ),
            purchases AS (
              SELECT date_trunc('quarter', purchase_date) AS period_start, SUM(total_amount) AS amount, COUNT(*) AS orders
              FROM public.purchases
              WHERE purchase_date >= date_trunc('quarter', CURRENT_DATE) - INTERVAL '21 month'
              GROUP BY 1
            )
            SELECT
              (EXTRACT(YEAR FROM p.period_start)::int || '-Q' || EXTRACT(QUARTER FROM p.period_start)::int) AS bucket,
              (EXTRACT(YEAR FROM p.period_start)::int || '年Q' || EXTRACT(QUARTER FROM p.period_start)::int) AS label,
              p.period_start::date AS period_start,
              (p.period_start + INTERVAL '3 month' - INTERVAL '1 day')::date AS period_end,
              COALESCE(s.amount, 0) AS sales_amount,
              COALESCE(s.orders, 0) AS sales_orders,
              COALESCE(pr.amount, 0) AS purchase_amount,
              COALESCE(pr.orders, 0) AS purchase_orders
            FROM periods p
            LEFT JOIN sales s ON s.period_start = p.period_start
            LEFT JOIN purchases pr ON pr.period_start = p.period_start
            ORDER BY p.period_start
            """
        )
    return _query_rows(
        conn,
        """
        WITH periods AS (
          SELECT date_trunc('month', CURRENT_DATE) - (gs * INTERVAL '1 month') AS period_start
          FROM generate_series(11, 0, -1) AS gs
        ),
        sales AS (
          SELECT date_trunc('month', order_date) AS period_start, SUM(total_amount) AS amount, COUNT(*) AS orders
          FROM public.orders
          WHERE order_date >= date_trunc('month', CURRENT_DATE) - INTERVAL '11 month'
          GROUP BY 1
        ),
        purchases AS (
          SELECT date_trunc('month', purchase_date) AS period_start, SUM(total_amount) AS amount, COUNT(*) AS orders
          FROM public.purchases
          WHERE purchase_date >= date_trunc('month', CURRENT_DATE) - INTERVAL '11 month'
          GROUP BY 1
        )
        SELECT
          TO_CHAR(p.period_start, 'YYYY-MM') AS bucket,
          TO_CHAR(p.period_start, 'YYYY-MM') AS label,
          p.period_start::date AS period_start,
          (p.period_start + INTERVAL '1 month' - INTERVAL '1 day')::date AS period_end,
          COALESCE(s.amount, 0) AS sales_amount,
          COALESCE(s.orders, 0) AS sales_orders,
          COALESCE(pr.amount, 0) AS purchase_amount,
          COALESCE(pr.orders, 0) AS purchase_orders
        FROM periods p
        LEFT JOIN sales s ON s.period_start = p.period_start
        LEFT JOIN purchases pr ON pr.period_start = p.period_start
        ORDER BY p.period_start
        """
    )


def _format_trend_rows(rows: List[Dict[str, Any]], granularity: str) -> List[Dict[str, Any]]:
    normalized = _normalize_trend_granularity(granularity)
    output: List[Dict[str, Any]] = []
    for row in rows:
        sales_amount_value = _to_float(row.get("sales_amount"))
        purchase_amount_value = _to_float(row.get("purchase_amount"))
        item = {
            "granularity": normalized,
            "bucket": row.get("bucket"),
            "label": row.get("label") or row.get("bucket"),
            "period_start": row.get("period_start"),
            "period_end": row.get("period_end"),
            "sales_amount": sales_amount_value,
            "purchase_amount": purchase_amount_value,
            "net_amount": sales_amount_value - purchase_amount_value,
            "sales_orders": _to_int(row.get("sales_orders")),
            "purchase_orders": _to_int(row.get("purchase_orders")),
        }
        if normalized == "month":
            item["month"] = row.get("bucket")
        output.append(item)
    return output


def _resolve_period_range(granularity: str, bucket: str) -> Tuple[datetime, datetime, str]:
    normalized = _normalize_trend_granularity(granularity)
    raw_bucket = str(bucket or "").strip()
    if normalized == "week":
        match = re.match(r"^(\d{4})-W(\d{2})$", raw_bucket)
        if not match:
            raise HTTPException(status_code=400, detail="Invalid week bucket")
        year = int(match.group(1))
        week = int(match.group(2))
        start = datetime.fromisocalendar(year, week, 1).replace(tzinfo=timezone.utc)
        end = start + timedelta(days=7)
        return start, end, f"{year}年第{week}周"
    if normalized == "quarter":
        match = re.match(r"^(\d{4})-Q([1-4])$", raw_bucket)
        if not match:
            raise HTTPException(status_code=400, detail="Invalid quarter bucket")
        year = int(match.group(1))
        quarter = int(match.group(2))
        month = (quarter - 1) * 3 + 1
        start = datetime(year, month, 1, tzinfo=timezone.utc)
        if quarter == 4:
            end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            end = datetime(year, month + 3, 1, tzinfo=timezone.utc)
        return start, end, f"{year}年Q{quarter}"
    match = re.match(r"^(\d{4})-(\d{1,2})$", raw_bucket)
    if not match:
        raise HTTPException(status_code=400, detail="Invalid month bucket")
    year = int(match.group(1))
    month = int(match.group(2))
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return start, end, f"{year}年{month}月"


def _make_object_item(
    *,
    object_type: str,
    object_id: Any,
    name: Any,
    subtitle: Any = "",
    primary_value: Any = 0,
    primary_unit: str = "",
    primary_label: str = "",
    secondary_value: Any = "",
    secondary_unit: str = "",
    secondary_label: str = "",
    meta: Any = "",
    note: Any = "",
) -> Dict[str, Any]:
    return {
        "id": object_id,
        "object_type": object_type,
        "name": str(name or "-"),
        "subtitle": str(subtitle or ""),
        "primary_value": primary_value,
        "primary_unit": primary_unit,
        "primary_label": primary_label,
        "secondary_value": secondary_value,
        "secondary_unit": secondary_unit,
        "secondary_label": secondary_label,
        "meta": str(meta or ""),
        "note": str(note or ""),
    }


def _build_where_clause(conditions: List[str]) -> str:
    normalized = [str(item).strip() for item in conditions if str(item).strip()]
    return (" AND " + " AND ".join(normalized)) if normalized else ""


def _query_drilldown_customers(
    conn: Connection,
    *,
    order_conditions: Optional[List[str]] = None,
    join_clause: str = "",
    params: Optional[Dict[str, Any]] = None,
    limit: int = 8,
) -> List[Dict[str, Any]]:
    sql = f"""
        SELECT
          c.cust_id AS cust_id,
          c.cust_name AS cust_name,
          COUNT(DISTINCT o.order_id) AS order_count,
          COALESCE(SUM(o.total_amount), 0) AS total_amount,
          COALESCE(SUM(CASE WHEN o.payment_status IN ('Pending', 'Unpaid', 'Partial') THEN o.total_amount ELSE 0 END), 0) AS receivable_amount,
          MAX(o.order_date) AS latest_order_date
        FROM public.orders o
        JOIN public.customers c ON c.cust_id = o.cust_id
        {join_clause}
        WHERE 1=1 {_build_where_clause(order_conditions or [])}
        GROUP BY c.cust_id, c.cust_name
        ORDER BY total_amount DESC, order_count DESC, receivable_amount DESC
        LIMIT :limit
    """
    rows = _query_rows(conn, sql, {**(params or {}), "limit": limit})
    return [
        _make_object_item(
            object_type="customer",
            object_id=row.get("cust_id"),
            name=row.get("cust_name"),
            subtitle="客户",
            primary_value=_to_float(row.get("total_amount")),
            primary_unit="CNY",
            primary_label="销售额",
            secondary_value=_to_int(row.get("order_count")),
            secondary_unit="count",
            secondary_label="订单数",
            meta=f"风险回款 { _format_drilldown_number(row.get('receivable_amount'), 'CNY') }",
            note=f"最近订单 {row.get('latest_order_date') or '-'}",
        )
        for row in rows
    ]


def _query_drilldown_skus(
    conn: Connection,
    *,
    order_conditions: Optional[List[str]] = None,
    product_conditions: Optional[List[str]] = None,
    params: Optional[Dict[str, Any]] = None,
    limit: int = 8,
) -> List[Dict[str, Any]]:
    sql = f"""
        SELECT
          p.prod_id AS prod_id,
          p.prod_name AS prod_name,
          p.category AS category,
          COALESCE(SUM(oi.total_price), 0) AS revenue,
          COALESCE(SUM(oi.quantity), 0) AS sold_units
        FROM public.order_items oi
        JOIN public.orders o ON o.order_id = oi.order_id
        JOIN public.products p ON p.prod_id = oi.prod_id
        WHERE 1=1
          {_build_where_clause(order_conditions or [])}
          {_build_where_clause(product_conditions or [])}
        GROUP BY p.prod_id, p.prod_name, p.category
        ORDER BY revenue DESC, sold_units DESC
        LIMIT :limit
    """
    rows = _query_rows(conn, sql, {**(params or {}), "limit": limit})
    return [
        _make_object_item(
            object_type="sku",
            object_id=row.get("prod_id"),
            name=row.get("prod_name"),
            subtitle=row.get("category") or "未分类",
            primary_value=_to_float(row.get("revenue")),
            primary_unit="CNY",
            primary_label="销售额",
            secondary_value=_to_int(row.get("sold_units")),
            secondary_unit="count",
            secondary_label="销量",
            note="来自销售订单明细",
        )
        for row in rows
    ]


def _query_drilldown_receivables(
    conn: Connection,
    *,
    order_conditions: Optional[List[str]] = None,
    params: Optional[Dict[str, Any]] = None,
    limit: int = 8,
    at_risk_only: bool = False,
) -> List[Dict[str, Any]]:
    conditions = list(order_conditions or [])
    if at_risk_only:
        conditions.append("o.payment_status IN ('Pending', 'Unpaid', 'Partial')")
    sql = f"""
        SELECT
          o.order_id AS order_id,
          o.order_no AS order_no,
          c.cust_name AS cust_name,
          o.total_amount AS total_amount,
          o.payment_status AS payment_status,
          o.delivery_status AS delivery_status,
          o.order_date AS order_date
        FROM public.orders o
        JOIN public.customers c ON c.cust_id = o.cust_id
        WHERE 1=1 {_build_where_clause(conditions)}
        ORDER BY o.total_amount DESC, o.order_date DESC
        LIMIT :limit
    """
    rows = _query_rows(conn, sql, {**(params or {}), "limit": limit})
    return [
        _make_object_item(
            object_type="receivable",
            object_id=row.get("order_id"),
            name=row.get("order_no") or row.get("order_id"),
            subtitle=row.get("cust_name") or "客户",
            primary_value=_to_float(row.get("total_amount")),
            primary_unit="CNY",
            primary_label="订单金额",
            secondary_value=f"{row.get('payment_status') or '-'} / {row.get('delivery_status') or '-'}",
            secondary_unit="text",
            secondary_label="状态",
            note=f"订单日期 {row.get('order_date') or '-'}",
        )
        for row in rows
    ]


def _query_drilldown_inventory(
    conn: Connection,
    *,
    warehouse: Optional[str] = None,
    category: Optional[str] = None,
    product_name: Optional[str] = None,
    prefer_low_stock: bool = False,
    limit: int = 8,
) -> List[Dict[str, Any]]:
    conditions: List[str] = []
    params: Dict[str, Any] = {"limit": limit}
    if warehouse:
        conditions.append("i.warehouse = :warehouse")
        params["warehouse"] = warehouse
    if category:
        conditions.append("p.category = :category")
        params["category"] = category
    if product_name:
        conditions.append("p.prod_name = :prod_name")
        params["prod_name"] = product_name

    having_sql = ""
    order_sql = "inventory_value DESC, quantity DESC"
    if prefer_low_stock:
        having_sql = "HAVING COALESCE(SUM(i.quantity), 0) <= COALESCE(MAX(p.min_stock), 0)"
        order_sql = "(COALESCE(MAX(p.min_stock), 0) - COALESCE(SUM(i.quantity), 0)) DESC, quantity ASC"

    sql = f"""
        SELECT
          p.prod_id AS prod_id,
          p.prod_name AS prod_name,
          p.category AS category,
          COALESCE(SUM(i.quantity), 0) AS quantity,
          COUNT(DISTINCT i.warehouse) AS warehouse_count,
          COALESCE(MAX(p.min_stock), 0) AS min_stock,
          COALESCE(SUM(i.quantity * COALESCE(p.purchase_price, 0)), 0) AS inventory_value
        FROM public.inventory i
        JOIN public.products p ON p.prod_id = i.prod_id
        WHERE 1=1 {_build_where_clause(conditions)}
        GROUP BY p.prod_id, p.prod_name, p.category
        {having_sql}
        ORDER BY {order_sql}
        LIMIT :limit
    """
    rows = _query_rows(conn, sql, params)
    return [
        _make_object_item(
            object_type="inventory",
            object_id=row.get("prod_id"),
            name=row.get("prod_name"),
            subtitle=row.get("category") or "库存对象",
            primary_value=_to_float(row.get("quantity")),
            primary_unit="count",
            primary_label="库存件数",
            secondary_value=_to_int(row.get("min_stock")),
            secondary_unit="count",
            secondary_label="安全库存",
            meta=f"{_to_int(row.get('warehouse_count'))} 个仓库",
            note=f"库存估值 {_format_drilldown_number(row.get('inventory_value'), 'CNY')}",
        )
        for row in rows
    ]


def _build_empty_object_groups() -> Dict[str, List[Dict[str, Any]]]:
    return {key: [] for key in _OBJECT_GROUP_ORDER}


def _normalize_drilldown_source(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    allowed_sources = {"trend", "payment", "delivery", "purchase", "risk", "product", "warehouse", "category"}
    if normalized not in allowed_sources:
        raise HTTPException(status_code=400, detail="Unsupported drilldown source")
    return normalized


def _normalize_optional_text(value: Any) -> Optional[str]:
    text_value = str(value or "").strip()
    return text_value or None


def _normalize_drilldown_limit(value: int | None) -> int:
    try:
        numeric = int(value or 8)
    except Exception:
        numeric = 8
    return max(4, min(20, numeric))


def _query_drilldown_inventory_from_orders(
    conn: Connection,
    *,
    order_conditions: Optional[List[str]] = None,
    product_conditions: Optional[List[str]] = None,
    params: Optional[Dict[str, Any]] = None,
    limit: int = 8,
    prefer_low_stock: bool = False,
) -> List[Dict[str, Any]]:
    scoped_conditions = list(order_conditions or []) + list(product_conditions or [])
    having_sql = ""
    order_sql = "inventory_value DESC, quantity DESC"
    if prefer_low_stock:
        having_sql = "HAVING COALESCE(SUM(i.quantity), 0) <= COALESCE(MAX(p.min_stock), 0)"
        order_sql = "(COALESCE(MAX(p.min_stock), 0) - COALESCE(SUM(i.quantity), 0)) DESC, quantity ASC"

    sql = f"""
        WITH scoped_products AS (
          SELECT DISTINCT p.prod_id, p.prod_name, p.category
          FROM public.order_items oi
          JOIN public.orders o ON o.order_id = oi.order_id
          JOIN public.products p ON p.prod_id = oi.prod_id
          WHERE 1=1 {_build_where_clause(scoped_conditions)}
        )
        SELECT
          sp.prod_id AS prod_id,
          sp.prod_name AS prod_name,
          sp.category AS category,
          COALESCE(SUM(i.quantity), 0) AS quantity,
          COUNT(DISTINCT i.warehouse) AS warehouse_count,
          COALESCE(MAX(p.min_stock), 0) AS min_stock,
          COALESCE(SUM(i.quantity * COALESCE(p.purchase_price, 0)), 0) AS inventory_value
        FROM scoped_products sp
        JOIN public.products p ON p.prod_id = sp.prod_id
        LEFT JOIN public.inventory i ON i.prod_id = sp.prod_id
        GROUP BY sp.prod_id, sp.prod_name, sp.category
        {having_sql}
        ORDER BY {order_sql}
        LIMIT :limit
    """
    rows = _query_rows(conn, sql, {**(params or {}), "limit": limit})
    return [
        _make_object_item(
            object_type="inventory",
            object_id=row.get("prod_id"),
            name=row.get("prod_name"),
            subtitle=row.get("category") or "库存对象",
            primary_value=_to_float(row.get("quantity")),
            primary_unit="count",
            primary_label="库存件数",
            secondary_value=_to_int(row.get("min_stock")),
            secondary_unit="count",
            secondary_label="安全库存",
            meta=f"{_to_int(row.get('warehouse_count'))} 个仓库",
            note=f"库存估值 {_format_drilldown_number(row.get('inventory_value'), 'CNY')}",
        )
        for row in rows
    ]


def _build_drilldown_response(
    *,
    source: str,
    granularity: str = "month",
    bucket: str | None = None,
    status: str | None = None,
    category: str | None = None,
    name: str | None = None,
    limit: int = 8,
) -> Dict[str, Any]:
    normalized_source = _normalize_drilldown_source(source)
    normalized_granularity = _normalize_trend_granularity(granularity)
    normalized_status = _normalize_optional_text(status)
    normalized_category = _normalize_optional_text(category)
    normalized_name = _normalize_optional_text(name)
    normalized_limit = _normalize_drilldown_limit(limit)

    object_groups = _build_empty_object_groups()
    title = "经营明细下钻"
    metric_description = "点击图表后查看关联的客户、SKU、回款项与库存对象。"
    default_group = "customer"
    context: Dict[str, Any] = {
        "source": normalized_source,
        "granularity": normalized_granularity,
        "bucket": bucket or "",
        "status": normalized_status or "",
        "category": normalized_category or "",
        "name": normalized_name or "",
    }

    with engine.begin() as conn:
        if normalized_source == "trend":
            if not bucket:
                raise HTTPException(status_code=400, detail="Missing trend bucket")
            period_start, period_end, period_label = _resolve_period_range(normalized_granularity, bucket)
            params = {"period_start": period_start.date(), "period_end": period_end.date()}
            order_conditions = ["o.order_date >= :period_start", "o.order_date < :period_end"]
            object_groups["customer"] = _query_drilldown_customers(conn, order_conditions=order_conditions, params=params, limit=normalized_limit)
            object_groups["sku"] = _query_drilldown_skus(conn, order_conditions=order_conditions, params=params, limit=normalized_limit)
            object_groups["receivable"] = _query_drilldown_receivables(conn, order_conditions=order_conditions, params=params, limit=normalized_limit)
            object_groups["inventory"] = _query_drilldown_inventory_from_orders(
                conn,
                order_conditions=order_conditions,
                params=params,
                limit=normalized_limit,
            )
            title = f"{period_label} 经营明细"
            metric_description = f"统计口径：按{normalized_granularity}汇总订单与采购金额，当前展示 {period_label} 的客户、SKU、回款项与库存对象。"
            context.update({"period_start": str(period_start.date()), "period_end": str(period_end.date()), "label": period_label})

        elif normalized_source == "payment":
            if not normalized_status:
                raise HTTPException(status_code=400, detail="Missing payment status")
            params = {"status": normalized_status}
            order_conditions = ["o.payment_status = :status"]
            object_groups["customer"] = _query_drilldown_customers(conn, order_conditions=order_conditions, params=params, limit=normalized_limit)
            object_groups["sku"] = _query_drilldown_skus(conn, order_conditions=order_conditions, params=params, limit=normalized_limit)
            object_groups["receivable"] = _query_drilldown_receivables(conn, order_conditions=order_conditions, params=params, limit=normalized_limit)
            object_groups["inventory"] = _query_drilldown_inventory_from_orders(
                conn,
                order_conditions=order_conditions,
                params=params,
                limit=normalized_limit,
                prefer_low_stock=normalized_status in _RISK_PAYMENT_STATUSES,
            )
            title = f"回款结构 · {normalized_status}"
            metric_description = "统计口径：按订单金额汇总付款状态，点击后查看对应状态下的客户、SKU、回款项与库存对象。"
            default_group = "receivable" if normalized_status in _RISK_PAYMENT_STATUSES else "customer"

        elif normalized_source == "delivery":
            if not normalized_status:
                raise HTTPException(status_code=400, detail="Missing delivery status")
            params = {"status": normalized_status}
            order_conditions = ["o.delivery_status = :status"]
            object_groups["customer"] = _query_drilldown_customers(conn, order_conditions=order_conditions, params=params, limit=normalized_limit)
            object_groups["sku"] = _query_drilldown_skus(conn, order_conditions=order_conditions, params=params, limit=normalized_limit)
            object_groups["receivable"] = _query_drilldown_receivables(conn, order_conditions=order_conditions, params=params, limit=normalized_limit)
            object_groups["inventory"] = _query_drilldown_inventory_from_orders(
                conn,
                order_conditions=order_conditions,
                params=params,
                limit=normalized_limit,
            )
            title = f"履约结构 · {normalized_status}"
            metric_description = "统计口径：按订单金额汇总交付状态，点击后查看该履约状态关联的客户、SKU、回款项与库存对象。"

        elif normalized_source == "purchase":
            if not normalized_status:
                raise HTTPException(status_code=400, detail="Missing purchase status")
            object_groups["inventory"] = _query_drilldown_inventory(
                conn,
                prefer_low_stock=normalized_status in {"Pending", "Processing"},
                limit=normalized_limit,
            )
            title = f"采购状态 · {normalized_status}"
            metric_description = "统计口径：按采购单金额汇总采购状态。由于当前缺少采购明细行，优先展示关联库存对象用于补货与积压判断。"
            default_group = "inventory"

        elif normalized_source == "product":
            if not normalized_name:
                raise HTTPException(status_code=400, detail="Missing product name")
            params = {"prod_name": normalized_name}
            product_order_conditions = [
                "EXISTS (SELECT 1 FROM public.order_items oi JOIN public.products p ON p.prod_id = oi.prod_id WHERE oi.order_id = o.order_id AND p.prod_name = :prod_name)"
            ]
            product_conditions = ["p.prod_name = :prod_name"]
            object_groups["customer"] = _query_drilldown_customers(
                conn,
                order_conditions=product_order_conditions,
                params=params,
                limit=normalized_limit,
            )
            object_groups["sku"] = _query_drilldown_skus(
                conn,
                product_conditions=product_conditions,
                params=params,
                limit=normalized_limit,
            )
            object_groups["receivable"] = _query_drilldown_receivables(
                conn,
                order_conditions=product_order_conditions,
                params=params,
                limit=normalized_limit,
            )
            object_groups["inventory"] = _query_drilldown_inventory(conn, product_name=normalized_name, limit=normalized_limit)
            title = f"商品销售 · {normalized_name}"
            metric_description = "统计口径：基于近180日商品销售额，点击商品后查看其关联客户、SKU、回款项与库存对象。"
            default_group = "sku"

        elif normalized_source == "warehouse":
            warehouse_name = normalized_name or normalized_category
            if not warehouse_name:
                raise HTTPException(status_code=400, detail="Missing warehouse name")
            params = {"warehouse_name": warehouse_name}
            warehouse_order_conditions = [
                "EXISTS (SELECT 1 FROM public.order_items oi JOIN public.inventory i ON i.prod_id = oi.prod_id WHERE oi.order_id = o.order_id AND i.warehouse = :warehouse_name)"
            ]
            object_groups["customer"] = _query_drilldown_customers(
                conn,
                order_conditions=warehouse_order_conditions,
                params=params,
                limit=normalized_limit,
            )
            object_groups["receivable"] = _query_drilldown_receivables(
                conn,
                order_conditions=warehouse_order_conditions,
                params=params,
                limit=normalized_limit,
            )
            object_groups["inventory"] = _query_drilldown_inventory(conn, warehouse=warehouse_name, limit=normalized_limit)
            title = f"仓库库存 · {warehouse_name}"
            metric_description = "统计口径：按当前仓库库存快照统计件数与明细行数，并展示该仓库商品关联的客户、回款项和库存对象。"
            default_group = "inventory"
            context["name"] = warehouse_name

        elif normalized_source == "category":
            if not normalized_category:
                raise HTTPException(status_code=400, detail="Missing product category")
            params = {"category_name": normalized_category}
            category_order_conditions = [
                "EXISTS (SELECT 1 FROM public.order_items oi JOIN public.products p ON p.prod_id = oi.prod_id WHERE oi.order_id = o.order_id AND p.category = :category_name)"
            ]
            category_product_conditions = ["p.category = :category_name"]
            object_groups["customer"] = _query_drilldown_customers(
                conn,
                order_conditions=category_order_conditions,
                params=params,
                limit=normalized_limit,
            )
            object_groups["sku"] = _query_drilldown_skus(
                conn,
                product_conditions=category_product_conditions,
                params=params,
                limit=normalized_limit,
            )
            object_groups["receivable"] = _query_drilldown_receivables(
                conn,
                order_conditions=category_order_conditions,
                params=params,
                limit=normalized_limit,
            )
            object_groups["inventory"] = _query_drilldown_inventory(conn, category=normalized_category, limit=normalized_limit)
            title = f"品类盈利 · {normalized_category}"
            metric_description = "统计口径：按品类汇总近180日销售额、成本额和利润，点击后查看该品类关联的客户、SKU、回款项与库存对象。"
            default_group = "sku"

        elif normalized_source == "risk":
            if not normalized_category:
                raise HTTPException(status_code=400, detail="Missing risk category")
            title = f"风险对象 · {normalized_category}"
            if normalized_category == "客户回款":
                params: Dict[str, Any] = {}
                order_conditions = ["o.payment_status IN ('Pending', 'Unpaid', 'Partial')"]
                sku_order_conditions = ["o.payment_status IN ('Pending', 'Unpaid', 'Partial')"]
                receivable_conditions = ["o.payment_status IN ('Pending', 'Unpaid', 'Partial')"]
                if normalized_name:
                    order_conditions.append("c.cust_name = :risk_name")
                    sku_order_conditions.append(
                        "o.cust_id IN (SELECT cust_id FROM public.customers WHERE cust_name = :risk_name)"
                    )
                    receivable_conditions.append("c.cust_name = :risk_name")
                    params["risk_name"] = normalized_name
                object_groups["customer"] = _query_drilldown_customers(
                    conn,
                    order_conditions=order_conditions,
                    params=params,
                    limit=normalized_limit,
                )
                object_groups["sku"] = _query_drilldown_skus(
                    conn,
                    order_conditions=sku_order_conditions,
                    params=params,
                    limit=normalized_limit,
                )
                object_groups["receivable"] = _query_drilldown_receivables(
                    conn,
                    order_conditions=receivable_conditions,
                    params=params,
                    limit=normalized_limit,
                    at_risk_only=True,
                )
                object_groups["inventory"] = _query_drilldown_inventory_from_orders(
                    conn,
                    order_conditions=["o.payment_status IN ('Pending', 'Unpaid', 'Partial')"],
                    params=params,
                    limit=normalized_limit,
                )
                metric_description = "统计口径：客户回款风险按未回款/部分回款订单金额汇总，支持下钻查看客户、SKU、回款项与库存对象。"
                default_group = "customer" if not normalized_name else "receivable"
            elif normalized_category == "库存缺口":
                params = {"prod_name": normalized_name} if normalized_name else {}
                product_order_conditions = (
                    [
                        "EXISTS (SELECT 1 FROM public.order_items oi JOIN public.products p ON p.prod_id = oi.prod_id WHERE oi.order_id = o.order_id AND p.prod_name = :prod_name)"
                    ]
                    if normalized_name
                    else []
                )
                product_conditions = ["p.prod_name = :prod_name"] if normalized_name else []
                object_groups["customer"] = _query_drilldown_customers(
                    conn,
                    order_conditions=product_order_conditions,
                    params=params,
                    limit=normalized_limit,
                ) if normalized_name else []
                object_groups["sku"] = _query_drilldown_skus(
                    conn,
                    product_conditions=product_conditions,
                    params=params,
                    limit=normalized_limit,
                ) if normalized_name else []
                object_groups["receivable"] = _query_drilldown_receivables(
                    conn,
                    order_conditions=product_order_conditions,
                    params=params,
                    limit=normalized_limit,
                ) if normalized_name else []
                object_groups["inventory"] = _query_drilldown_inventory(
                    conn,
                    product_name=normalized_name,
                    prefer_low_stock=True,
                    limit=normalized_limit,
                )
                metric_description = "统计口径：库存缺口按当前库存与安全库存差值识别，支持下钻查看缺口商品及其关联客户、SKU、回款项与库存对象。"
                default_group = "inventory"
            else:
                object_groups["inventory"] = _query_drilldown_inventory(conn, limit=normalized_limit)
                metric_description = "统计口径：采购积压按未完成采购金额与单量识别。当前优先展示库存对象，辅助判断积压与去化压力。"
                default_group = "inventory"

        else:
            raise HTTPException(status_code=400, detail="Unsupported drilldown source")

    return {
        "title": title,
        "metric_description": metric_description,
        "default_group": default_group,
        "context": context,
        "group_labels": [{"key": key, "label": _OBJECT_GROUP_LABELS.get(key, key)} for key in _OBJECT_GROUP_ORDER],
        "object_groups": object_groups,
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

        monthly_trend_rows = _query_trend_rows_by_granularity(conn, "month")
        weekly_trend_rows = _query_trend_rows_by_granularity(conn, "week")
        quarterly_trend_rows = _query_trend_rows_by_granularity(conn, "quarter")

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

    formatted_trends = _format_trend_rows(monthly_trend_rows, "month")
    trends_by_granularity = {
        "month": formatted_trends,
        "week": _format_trend_rows(weekly_trend_rows, "week"),
        "quarter": _format_trend_rows(quarterly_trend_rows, "quarter"),
    }

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
        "trends_by_granularity": trends_by_granularity,
        "trend_granularity_options": [
            {"key": "week", "label": "按周"},
            {"key": "month", "label": "按月"},
            {"key": "quarter", "label": "按季"},
        ],
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


def _store_preaggregated_snapshot(payload: Dict[str, Any], generated_at: datetime) -> None:
    with _PREAGG_CACHE_LOCK:
        _PREAGG_CACHE["payload"] = payload
        _PREAGG_CACHE["generated_at"] = generated_at
        _PREAGG_CACHE["refreshing"] = False
        _PREAGG_CACHE["last_error"] = None


def _refresh_preaggregated_snapshot() -> Dict[str, Any]:
    payload = _collect_dashboard_data()
    generated_at = _utc_now()
    _store_preaggregated_snapshot(payload, generated_at)
    return _with_preaggregation_meta(
        payload,
        generated_at,
        dashboard_cached=False,
        stale=False,
        pending_refresh=False,
        last_error=None,
    )


def _start_preaggregated_refresh_async() -> bool:
    with _PREAGG_CACHE_LOCK:
        if _PREAGG_CACHE.get("refreshing"):
            return False
        _PREAGG_CACHE["refreshing"] = True

    def _worker():
        try:
            payload = _collect_dashboard_data()
            generated_at = _utc_now()
        except Exception as exc:
            print(f"[Decision] preaggregation refresh failed: {exc}")
            with _PREAGG_CACHE_LOCK:
                _PREAGG_CACHE["refreshing"] = False
                _PREAGG_CACHE["last_error"] = str(exc)
            return

        with _PREAGG_CACHE_LOCK:
            _PREAGG_CACHE["payload"] = payload
            _PREAGG_CACHE["generated_at"] = generated_at
            _PREAGG_CACHE["refreshing"] = False
            _PREAGG_CACHE["last_error"] = None

    threading.Thread(target=_worker, daemon=True, name="decision-preagg-refresh").start()
    return True


def _get_cached_dashboard_data(force_refresh: bool = False) -> Dict[str, Any]:
    cached_payload: Dict[str, Any] | None = None
    cached_at: datetime | None = None
    pending_refresh = False
    last_error: str | None = None

    with _PREAGG_CACHE_LOCK:
        payload = _PREAGG_CACHE.get("payload")
        generated_at = _PREAGG_CACHE.get("generated_at")
        refreshing = bool(_PREAGG_CACHE.get("refreshing"))
        cached_error = _PREAGG_CACHE.get("last_error")
        if isinstance(payload, dict) and isinstance(generated_at, datetime):
            cached_payload = dict(payload)
            cached_at = generated_at
            last_error = str(cached_error) if cached_error else None
            age_seconds = max(0, int((_utc_now() - generated_at).total_seconds()))
            if (not force_refresh) and age_seconds < _PREAGG_REFRESH_SECONDS:
                return _with_preaggregation_meta(
                    cached_payload,
                    cached_at,
                    dashboard_cached=True,
                    stale=False,
                    pending_refresh=refreshing,
                    last_error=last_error,
                )
            if (not force_refresh) and age_seconds < _PREAGG_MAX_STALE_SECONDS:
                pending_refresh = True

    if cached_payload is not None and cached_at is not None and pending_refresh:
        _start_preaggregated_refresh_async()
        return _with_preaggregation_meta(
            cached_payload,
            cached_at,
            dashboard_cached=True,
            stale=True,
            pending_refresh=True,
            last_error=last_error,
        )

    return _refresh_preaggregated_snapshot()


def warmup_decision_cache():
    """
    Warm decision dashboard and AI cache on startup to reduce first-request latency.
    Runs in background thread from main.py startup hook.
    """
    try:
        backend = _normalize_backend(os.getenv("DECISION_WARMUP_AI_BACKEND", "cloud"))
        data = _get_cached_dashboard_data(force_refresh=True)
        _get_cached_ai_analysis(data, backend=backend, force_refresh=True)
        print(f"[Decision] warmup completed (backend={backend})")
    except Exception as exc:
        print(f"[Decision] warmup failed: {exc}")


@router.get("/drilldown")
def get_decision_drilldown(
    source: str = Query(description="trend | payment | delivery | purchase | risk | product | warehouse | category"),
    granularity: str = Query(default="month", description="week | month | quarter"),
    bucket: str | None = Query(default=None, description="Trend bucket, e.g. 2026-03 / 2026-W12 / 2026-Q1"),
    status: str | None = Query(default=None, description="Status for payment / delivery / purchase drilldown"),
    category: str | None = Query(default=None, description="Risk or product category"),
    name: str | None = Query(default=None, description="Product, warehouse, or risk object name"),
    limit: int = Query(default=8, ge=1, le=20, description="Rows per object group"),
):
    try:
        return _build_drilldown_response(
            source=source,
            granularity=granularity,
            bucket=bucket,
            status=status,
            category=category,
            name=name,
            limit=limit,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load decision drilldown: {exc}") from exc


@router.get("/overview")
def get_decision_overview(
    refresh_ai: bool = Query(default=False, description="Whether to force refresh AI analysis"),
    refresh_data: bool = Query(default=False, description="Whether to force refresh dashboard aggregates"),
    analysis_backend: str = Query(default="cloud", description="local | cloud"),
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
    analysis_backend: str = Query(default="cloud", description="local | cloud"),
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
