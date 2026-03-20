import os
import re
import threading
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from supabase_client import require_supabase
except Exception:
    require_supabase = None


_ERP_SCHEMA_LOCK = threading.Lock()
_ERP_UNAVAILABLE_TABLES: set[str] = set()
_ERP_UNSUPPORTED_COLUMNS: Dict[str, set[str]] = {}


def _remember_missing_table(table: str, error: Exception) -> bool:
    message = str(error or "")
    patterns = [
        rf"Could not find the table '([^']*{re.escape(table)}[^']*)' in the schema cache",
        rf"(?:relation|table)\s+['\"]?(?:public\.)?{re.escape(table)}['\"]?\s+does not exist",
    ]
    if not any(re.search(pattern, message, re.IGNORECASE) for pattern in patterns):
        return False
    with _ERP_SCHEMA_LOCK:
        _ERP_UNAVAILABLE_TABLES.add(table)
    return True


def _remember_missing_column(table: str, error: Exception) -> Optional[str]:
    message = str(error or "")
    patterns = [
        rf"Could not find the '([^']+)' column of '{re.escape(table)}' in the schema cache",
        rf"column\s+['\"]?(?:public\.)?{re.escape(table)}\.([A-Za-z0-9_]+)['\"]?\s+does not exist",
    ]
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if not match:
            continue
        column = str(match.group(1) or "").strip()
        if not column:
            continue
        with _ERP_SCHEMA_LOCK:
            _ERP_UNSUPPORTED_COLUMNS.setdefault(table, set()).add(column)
        return column
    return None


class ERPAdapter(ABC):
    provider_name = "base"

    def __init__(self, user_id: Optional[str] = None):
        self.user_id = user_id or "anonymous"

    @abstractmethod
    def fetch_context(self, fields: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def writeback_audit_action(
        self,
        job_id: str,
        action: str,
        operator_id: str,
        result: Optional[Dict[str, Any]] = None,
        comment: Optional[str] = None,
    ) -> Dict[str, Any]:
        raise NotImplementedError


class SupabaseERPAdapter(ERPAdapter):
    provider_name = "mock"

    def _safe_float(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).replace(",", "").strip()
        if not text:
            return None
        try:
            return float(text)
        except Exception:
            return None

    def _safe_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        text = str(value).strip().lower()
        return text in {"1", "true", "yes", "y", "on", "black", "blacklist", "blocked"}

    def _safe_text(self, value: Any) -> str:
        return str(value or "").strip()

    def _query_first(self, table: str, filters: Dict[str, Any], columns: str = "*") -> Optional[Dict[str, Any]]:
        if not require_supabase:
            return None
        with _ERP_SCHEMA_LOCK:
            if table in _ERP_UNAVAILABLE_TABLES:
                return None
            unsupported_columns = set(_ERP_UNSUPPORTED_COLUMNS.get(table) or set())
        active_filters = {
            key: value
            for key, value in (filters or {}).items()
            if value not in (None, "") and key not in unsupported_columns
        }
        if not active_filters:
            return None
        while True:
            try:
                sb = require_supabase()
                query = sb.table(table).select(columns)
                for key, value in active_filters.items():
                    query = query.eq(key, value)
                resp = query.limit(1).execute()
                data = resp.data or []
                return data[0] if data else None
            except Exception as e:
                if _remember_missing_table(table, e):
                    return None
                missing_column = _remember_missing_column(table, e)
                if missing_column:
                    next_filters = {
                        key: value
                        for key, value in active_filters.items()
                        if key != missing_column
                    }
                    if next_filters != active_filters and next_filters:
                        active_filters = next_filters
                        continue
                return None

    def _insert_action_row(self, payload: Dict[str, Any]) -> bool:
        if not require_supabase:
            return False
        for table in ["audit_erp_actions", "erp_audit_actions"]:
            try:
                sb = require_supabase()
                sb.table(table).insert(payload).execute()
                return True
            except Exception:
                continue
        return False

    def _extract_number(self, row: Optional[Dict[str, Any]], keys: List[str]) -> Optional[float]:
        if not isinstance(row, dict):
            return None
        for key in keys:
            if key in row:
                value = self._safe_float(row.get(key))
                if value is not None:
                    return value
        return None

    def _extract_text(self, row: Optional[Dict[str, Any]], keys: List[str]) -> Optional[str]:
        if not isinstance(row, dict):
            return None
        for key in keys:
            if key in row:
                text = self._safe_text(row.get(key))
                if text:
                    return text
        return None

    def _find_record_by_keys(self, table: str, key_candidates: List[str], value: Optional[str]) -> Optional[Dict[str, Any]]:
        value = self._safe_text(value)
        if not value:
            return None
        with _ERP_SCHEMA_LOCK:
            if table in _ERP_UNAVAILABLE_TABLES:
                return None
            unsupported_columns = set(_ERP_UNSUPPORTED_COLUMNS.get(table) or set())
        for key in key_candidates:
            if key in unsupported_columns:
                continue
            row = self._query_first(table, {key: value})
            if row:
                return row
        return None

    def fetch_context(self, fields: Dict[str, Any]) -> Dict[str, Any]:
        contract_no = self._safe_text(fields.get("contract_no"))
        invoice_no = self._safe_text(fields.get("invoice_no"))
        vendor = self._safe_text(fields.get("vendor") or fields.get("payee"))

        contract_row = None
        for table in ["erp_contracts", "contracts", "purchase_orders"]:
            contract_row = self._find_record_by_keys(
                table,
                ["contract_no", "contract_number", "contract_code", "po_no", "po_number"],
                contract_no,
            )
            if contract_row:
                break

        invoice_row = None
        for table in ["erp_invoices", "invoices"]:
            invoice_row = self._find_record_by_keys(table, ["invoice_no", "invoice_number", "bill_no"], invoice_no)
            if invoice_row:
                break

        vendor_row = None
        for table in ["erp_vendors", "vendors", "suppliers"]:
            vendor_row = self._find_record_by_keys(
                table,
                ["vendor", "vendor_name", "supplier_name", "name", "payee"],
                vendor,
            )
            if vendor_row:
                break

        contract_amount = self._extract_number(contract_row, ["contract_amount", "amount", "total_amount", "contract_total"])
        po_amount = self._extract_number(contract_row, ["po_amount", "po_total", "amount", "total_amount"])
        paid_amount = self._extract_number(contract_row, ["paid_amount", "paid_total", "already_paid", "settled_amount"])
        budget_remaining = self._extract_number(contract_row, ["budget_remaining", "remaining_budget", "budget_balance", "remaining_amount"])

        expected_vendor = self._extract_text(contract_row, ["vendor", "vendor_name", "supplier_name", "payee"])
        if not expected_vendor:
            expected_vendor = self._extract_text(invoice_row, ["vendor", "vendor_name", "supplier_name", "payee"])

        vendor_status = self._extract_text(vendor_row, ["vendor_status", "status", "risk_level", "state"]) or "unknown"
        blacklist_hit = self._safe_bool(vendor_row.get("blacklist_hit") if isinstance(vendor_row, dict) else None)
        if not blacklist_hit and isinstance(vendor_row, dict):
            blacklist_hit = self._safe_bool(
                vendor_row.get("is_blacklisted")
                or vendor_row.get("blacklisted")
                or vendor_row.get("in_blacklist")
            )

        invoice_exists = bool(invoice_row)

        return {
            "provider": self.provider_name,
            "contract_no": contract_no or None,
            "invoice_no": invoice_no or None,
            "contract_amount": contract_amount,
            "po_amount": po_amount,
            "paid_amount": paid_amount,
            "budget_remaining": budget_remaining,
            "vendor_status": vendor_status,
            "blacklist_hit": bool(blacklist_hit),
            "expected_vendor": expected_vendor,
            "invoice_exists": bool(invoice_exists),
            "existing_invoice_nos": [invoice_no] if invoice_exists and invoice_no else [],
            "raw_refs": {
                "contract": contract_row or {},
                "invoice": invoice_row or {},
                "vendor": vendor_row or {},
            },
        }

    def writeback_audit_action(
        self,
        job_id: str,
        action: str,
        operator_id: str,
        result: Optional[Dict[str, Any]] = None,
        comment: Optional[str] = None,
    ) -> Dict[str, Any]:
        trace_id = f"ERP-{self.provider_name.upper()}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        payload = {
            "trace_id": trace_id,
            "job_id": job_id,
            "action": action,
            "operator_id": operator_id,
            "comment": comment,
            "provider": self.provider_name,
            "risk_level": (result or {}).get("risk_level"),
            "audit_score": (result or {}).get("audit_score"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        stored = self._insert_action_row(payload)
        return {
            "trace_id": trace_id,
            "provider": self.provider_name,
            "action": action,
            "status": "synced" if stored else "queued",
            "stored": stored,
        }


class YonyouERPAdapter(SupabaseERPAdapter):
    provider_name = "yonyou"


class KingdeeERPAdapter(SupabaseERPAdapter):
    provider_name = "kingdee"


class SAPERPAdapter(SupabaseERPAdapter):
    provider_name = "sap"


def get_erp_adapter(provider: Optional[str] = None, user_id: Optional[str] = None) -> ERPAdapter:
    resolved = (provider or os.getenv("AUDIT_ERP_PROVIDER", "mock")).strip().lower()
    mapping = {
        "mock": SupabaseERPAdapter,
        "local": SupabaseERPAdapter,
        "yonyou": YonyouERPAdapter,
        "kingdee": KingdeeERPAdapter,
        "sap": SAPERPAdapter,
    }
    adapter_cls = mapping.get(resolved, SupabaseERPAdapter)
    return adapter_cls(user_id=user_id)


def get_supported_erp_providers() -> List[str]:
    return ["mock", "yonyou", "kingdee", "sap"]
