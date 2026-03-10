import base64
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import Header, HTTPException

from supabase_client import get_admin_supabase, require_supabase
from runtime_storage import (
    SMS_TOKEN_CACHE_FILE as RUNTIME_SMS_TOKEN_CACHE_FILE,
    ensure_runtime_layout,
    migrate_legacy_runtime_files,
)


ROLE_ADMIN = "admin"
ROLE_AUDITOR = "auditor"
ROLE_KB_ADMIN = "kb_admin"
ROLE_USER = "user"

ROLE_ALIASES = {
    "administrator": ROLE_ADMIN,
    "superadmin": ROLE_ADMIN,
}

ADMIN_ROLES = {ROLE_ADMIN}
AUDIT_ROLES = {ROLE_ADMIN, ROLE_AUDITOR}
KB_ROLES = {ROLE_ADMIN, ROLE_KB_ADMIN}
ensure_runtime_layout()
migrate_legacy_runtime_files()
SMS_TOKEN_CACHE_FILE = str(RUNTIME_SMS_TOKEN_CACHE_FILE)


def _bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    s = authorization.strip()
    if s.lower().startswith("bearer "):
        return s[7:].strip() or None
    return s or None


def _decode_jwt_payload(token: str) -> Dict[str, Any]:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload_b64 = parts[1]
        padding = "=" * (-len(payload_b64) % 4)
        payload_bytes = base64.urlsafe_b64decode(payload_b64 + padding)
        return json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        return {}


def _get_token_iat(token: str) -> Optional[int]:
    payload = _decode_jwt_payload(token)
    iat = payload.get("iat")
    return int(iat) if isinstance(iat, (int, float, str)) and str(iat).isdigit() else None


def _normalize_role(role: Optional[str]) -> str:
    if not role:
        return ROLE_USER
    role = str(role).strip().lower()
    return ROLE_ALIASES.get(role, role)


def _fetch_profile(user_id: str) -> Optional[Dict[str, Any]]:
    try:
        sb = require_supabase()
        res = sb.table("profiles").select("*").eq("id", user_id).limit(1).execute()
        if res.data:
            return res.data[0]
    except Exception:
        return None
    return None


def _prune_missing_column_error(err: Exception, payload: Dict[str, Any]) -> bool:
    """Remove missing columns from payload based on Supabase error message."""
    msg = str(err)
    match = re.search(r'column "([^"]+)" does not exist', msg)
    if not match:
        return False
    col = match.group(1)
    if col in payload:
        payload.pop(col, None)
        return True
    return False


def _safe_profile_write(action: str, payload: Dict[str, Any], user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    sb = require_supabase()
    data = dict(payload)
    max_attempts = max(1, len(data) + 1)
    for _ in range(max_attempts):
        try:
            if action == "insert":
                sb.table("profiles").insert(data).execute()
            elif action == "update":
                if not user_id:
                    raise ValueError("user_id required for update")
                sb.table("profiles").update(data).eq("id", user_id).execute()
            else:
                sb.table("profiles").upsert(data).execute()
            return data
        except Exception as e:
            if _prune_missing_column_error(e, data):
                continue
            return None
    return None


def safe_upsert_profile(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return _safe_profile_write("upsert", payload)


def safe_insert_profile(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return _safe_profile_write("insert", payload)


def safe_update_profile(user_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return _safe_profile_write("update", payload, user_id=user_id)


def _ensure_profile(user: Any, role: Optional[str] = None) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    app_meta = getattr(user, "app_metadata", {}) or {}
    user_meta = getattr(user, "user_metadata", {}) or {}
    existing = _fetch_profile(user.id)
    app_role_raw = role if role is not None else app_meta.get("role")
    has_explicit_role = role is not None or app_meta.get("role") not in (None, "")
    existing_role = _normalize_role((existing or {}).get("role"))
    role_value = _normalize_role(app_role_raw) if has_explicit_role else (existing_role or ROLE_USER)
    payload = {
        "id": user.id,
        "email": user.email,
        "role": role_value or ROLE_USER,
        "status": "active",
        "department": user_meta.get("department"),
        "job_title": user_meta.get("job_title"),
        "updated_at": now,
    }
    if not existing:
        payload["created_at"] = now
        saved = safe_insert_profile(payload)
        return saved or payload
    saved = safe_update_profile(user.id, payload)
    return {**existing, **(saved or payload)}


def _get_user_from_token(token: str):
    sb_admin = get_admin_supabase()
    user_res = sb_admin.auth.get_user(token)
    if not user_res or not user_res.user:
        raise HTTPException(status_code=401, detail="Invalid session")
    return user_res.user


def _get_sms_session_from_cache(token: str) -> Optional[Dict[str, Any]]:
    if not token or not token.startswith("sms-token-"):
        return None
    try:
        if not os.path.exists(SMS_TOKEN_CACHE_FILE):
            return None
        with open(SMS_TOKEN_CACHE_FILE, "r", encoding="utf-8") as fp:
            cache = json.load(fp)
        if not isinstance(cache, dict):
            return None
        session = cache.get(token)
        if not isinstance(session, dict):
            return None
        expires_at = float(session.get("expires_at") or 0)
        if expires_at <= time.time():
            return None
        user_id = str(session.get("user_id") or "").strip()
        if not user_id:
            return None
        return {"user_id": user_id}
    except Exception:
        return None


def require_active_user(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    token = _bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")

    # JWT token (密码登录)
    if len(token) >= 100:
        user = _get_user_from_token(token)
    else:
        # sms-token (验证码登录)
        sms_session = _get_sms_session_from_cache(token)
        if not sms_session:
            raise HTTPException(status_code=401, detail="Invalid session")
        sb_admin = get_admin_supabase()
        try:
            user_res = sb_admin.auth.admin.get_user_by_id(sms_session["user_id"])
            if not user_res or not user_res.user:
                raise HTTPException(status_code=401, detail="Invalid session")
            user = user_res.user
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid session")

    profile = _ensure_profile(user)
    if profile.get("status") == "disabled":
        raise HTTPException(status_code=403, detail="Account disabled")
    force_logout_at = profile.get("force_logout_at")
    if force_logout_at:
        iat = _get_token_iat(token)
        if iat:
            try:
                logout_ts = datetime.fromisoformat(str(force_logout_at).replace("Z", "+00:00")).timestamp()
                if iat < int(logout_ts):
                    raise HTTPException(status_code=401, detail="Session expired")
            except HTTPException:
                raise
            except Exception:
                pass
    app_meta = getattr(user, "app_metadata", {}) or {}
    raw_role = app_meta.get("role")
    role = _normalize_role(raw_role)
    if raw_role in (None, "") and profile.get("role"):
        role = _normalize_role(profile.get("role"))
    return {"user_id": user.id, "role": role, "profile": profile}


def require_role(allowed_roles: List[str]):
    def _inner(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
        ctx = require_active_user(authorization)
        role = _normalize_role(ctx.get("role"))
        if role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        ctx["role"] = role
        return ctx
    return _inner


def log_admin_action(actor_id: str, action: str, target_id: Optional[str], payload: Optional[Dict[str, Any]] = None) -> None:
    try:
        sb = require_supabase()
        sb.table("admin_audit_logs").insert({
            "actor_id": actor_id,
            "action": action,
            "target_id": target_id,
            "payload": payload or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception:
        pass
