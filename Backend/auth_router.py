from __future__ import annotations
import httpx
import mimetypes
import json
from typing import Optional, Dict, Any
from uuid import uuid4
import time
import os
from urllib.parse import parse_qs, quote, unquote, urlparse

from fastapi import APIRouter, HTTPException, Header, UploadFile, File, Query, Request, Response
from pydantic import BaseModel, Field, ConfigDict, AliasChoices

from supabase_client import require_supabase
from aliyun_sms_client import send_login_code, verify_login_code
from supabase_client import get_admin_supabase, get_anon_supabase
from admin_utils import safe_insert_profile, safe_update_profile
from datetime import datetime, timezone

router = APIRouter(prefix="/api/auth", tags=["Auth"])
user_router = APIRouter(prefix="/api/user", tags=["User"])

# =========================
# Storage 配置
# =========================
AVATAR_BUCKET = "avatars"
MAX_AVATAR_BYTES = 5 * 1024 * 1024  # Raise avatar limit to 5MB for better tolerance.
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}

# -----------------------------------------------------------------------------
# 短信登录令牌缓存（内存 + 磁盘）
# -----------------------------------------------------------------------------
SMS_TOKEN_TTL_SECONDS = 14 * 24 * 3600
SMS_TOKEN_CACHE_FILE = os.path.join(os.path.dirname(__file__), ".sms_token_cache.json")


def _load_token_cache_from_disk() -> Dict[str, Dict[str, Any]]:
    try:
        if not os.path.exists(SMS_TOKEN_CACHE_FILE):
            return {}
        with open(SMS_TOKEN_CACHE_FILE, "r", encoding="utf-8") as fp:
            raw = json.load(fp)
        if not isinstance(raw, dict):
            return {}

        now = time.time()
        cleaned: Dict[str, Dict[str, Any]] = {}
        for token, session in raw.items():
            if not isinstance(token, str) or not isinstance(session, dict):
                continue
            expires_at = float(session.get("expires_at") or 0)
            if expires_at <= now:
                continue
            user_id = str(session.get("user_id") or "").strip()
            phone = str(session.get("phone") or "").strip()
            email = str(session.get("email") or "").strip()
            if not user_id or not phone:
                continue
            cleaned[token] = {
                "user_id": user_id,
                "phone": phone,
                "email": email,
                "expires_at": expires_at,
            }
        return cleaned
    except Exception:
        return {}


_TOKEN_CACHE: Dict[str, Dict[str, Any]] = _load_token_cache_from_disk()


def _persist_token_cache() -> None:
    try:
        cache_dir = os.path.dirname(SMS_TOKEN_CACHE_FILE)
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)
        temp_file = f"{SMS_TOKEN_CACHE_FILE}.tmp"
        with open(temp_file, "w", encoding="utf-8") as fp:
            json.dump(_TOKEN_CACHE, fp, ensure_ascii=False)
        os.replace(temp_file, SMS_TOKEN_CACHE_FILE)
    except Exception as e:
        print(f"[Auth] Persist sms token cache failed: {e}")


def _purge_expired_token_cache(persist: bool = False) -> None:
    now = time.time()
    expired_tokens = [
        token for token, session in _TOKEN_CACHE.items()
        if float((session or {}).get("expires_at") or 0) <= now
    ]
    if not expired_tokens:
        return
    for token in expired_tokens:
        _TOKEN_CACHE.pop(token, None)
    if persist:
        _persist_token_cache()


def _get_sb_url_and_key(sb) -> tuple[str, str]:
    # 优先从 supabase client 对象里取（不同版本字段名可能不同）
    url = getattr(sb, "supabase_url", None) or getattr(sb, "_supabase_url", None) or ""
    key = getattr(sb, "supabase_key", None) or getattr(sb, "_supabase_key", None) or ""
    # 兜底从环境变量取（你 supabase_client 里通常也是从环境变量读）
    if not url:
        url = os.getenv("SUPABASE_URL", "") or os.getenv("SUPABASE_PROJECT_URL", "")
    if not key:
        # 此处必须使用匿名密钥（不是服务角色）。
        key = os.getenv("SUPABASE_ANON_KEY", "") or os.getenv("SUPABASE_KEY", "")
    if not url or not key:
        raise HTTPException(status_code=500, detail="后端缺少 SUPABASE_URL / SUPABASE_ANON_KEY 配置")
    return url.rstrip("/"), key


def _update_user_metadata_via_gotrue(sb, jwt_token: str, data: dict) -> None:
    """
    Call Supabase GoTrue to update user_metadata: PUT /auth/v1/user
    Requires: Authorization Bearer <jwt> + apikey(anon)
    """
    supabase_url, anon_key = _get_sb_url_and_key(sb)
    endpoint = f"{supabase_url}/auth/v1/user"

    headers = {
        "apikey": anon_key,
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json",
    }

    # 仅更新 user_metadata：负载格式为 {"data": {...}}
    payload = {"data": data}

    try:
        r = httpx.put(endpoint, headers=headers, json=payload, timeout=10)
        if r.status_code >= 400:
            # 常见情况：401 表示令牌不是 Supabase JWT（例如 sms-token）。
            detail = ""
            try:
                detail = r.json()
            except Exception:
                detail = r.text
            raise HTTPException(status_code=401 if r.status_code == 401 else 500,
                                detail=f"Supabase update failed ({r.status_code}): {detail}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase update failed: {str(e)}")


def _cache_token(token: str, user_id: str, phone: str, email: str):
    """Cache mapping between temporary token and real user identity."""
    _purge_expired_token_cache()
    _TOKEN_CACHE[token] = {
        "user_id": user_id,
        "phone": phone,
        "email": email,
        "expires_at": time.time() + SMS_TOKEN_TTL_SECONDS
    }
    _persist_token_cache()


def _get_session_from_token(token: str) -> Optional[Dict]:
    """Return cached session mapping by token."""
    session = _TOKEN_CACHE.get(token)
    if session:
        if float(session.get("expires_at") or 0) > time.time():
            return session
        _TOKEN_CACHE.pop(token, None)
        _persist_token_cache()
    return None


def _sync_profile(user, role: Optional[str] = None):
    try:
        sb = require_supabase()
        now = datetime.now(timezone.utc).isoformat()
        app_meta = getattr(user, "app_metadata", {}) or {}
        user_meta = getattr(user, "user_metadata", {}) or {}
        payload = {
            "id": user.id,
            "email": user.email,
            "role": (role or app_meta.get("role") or "user"),
            "status": "active",
            "department": user_meta.get("department"),
            "job_title": user_meta.get("job_title"),
            "updated_at": now,
        }
        exists = sb.table("profiles").select("id").eq("id", user.id).limit(1).execute()
        if not exists.data:
            payload["created_at"] = now
            safe_insert_profile(payload)
        else:
            safe_update_profile(user.id, payload)
        return payload
    except Exception:
        return None


# -----------------------------------------------------------------------------
# 工具函数
# -----------------------------------------------------------------------------
def _bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    s = authorization.strip()
    if s.lower().startswith("bearer "):
        return s[7:].strip() or None
    return s or None


def _get_email_from_phone(phone: str) -> str:
    # 保持与注册时一致的邮箱生成逻辑
    return f"{phone}@flowus.cn"


def _session_value(session, key: str):
    if not session:
        return None
    if isinstance(session, dict):
        return session.get(key)
    return getattr(session, key, None)


def _find_user_by_loop(sb, target_email: str, target_phone: str):
    try:
        page = 1
        while True:
            response = sb.auth.admin.list_users(page=page, per_page=50)
            users = response.users if hasattr(response, "users") else response

            if not users:
                break

            for user in users:
                u_email = (getattr(user, "email", "") or "").lower()
                if u_email == target_email:
                    return user

                u_meta = getattr(user, "user_metadata", {}) or {}
                meta_phone = str(u_meta.get("phone", "")).strip()
                if meta_phone and meta_phone == target_phone:
                    return user

                u_phone = getattr(user, "phone", "") or ""
                u_phone_clean = u_phone.replace("+86", "").strip()
                if u_phone_clean and u_phone_clean == target_phone:
                    return user

            if len(users) < 50:
                break
            page += 1
    except Exception as e:
        print(f"Error searching user loop: {e}")
    return None


def _find_or_create_user_by_phone(sb, phone: str):
    target_email = _get_email_from_phone(phone).lower().strip()
    target_phone = phone.strip()

    found_user = _find_user_by_loop(sb, target_email, target_phone)
    if found_user:
        return found_user

    try:
        random_pwd = f"SmsLogin@{uuid4().hex[:8]}"
        new_user = sb.auth.admin.create_user({
            "email": target_email,
            "password": random_pwd,
            "email_confirm": True,
            "user_metadata": {
                "phone": phone,
                "name": f"User_{phone[-4:]}",
                "login_method": "sms_auto_register"
            }
        })
        return new_user

    except Exception as e:
        err_msg = str(e).lower()
        if "register" in err_msg or "exist" in err_msg:
            retry_user = _find_user_by_loop(sb, target_email, target_phone)
            if retry_user:
                return retry_user
        print(f"Error auto-registering user: {e}")
        return None


def _resolve_user_id(sb, token: Optional[str]) -> str:
    """Resolve user_id from JWT token or custom sms-token."""
    if not token:
        raise HTTPException(status_code=401, detail="Not logged in")

    # JWT Token（密码登录）
    if len(token) > 100:
        try:
            user_res = sb.auth.get_user(token)
            if user_res and user_res.user:
                return user_res.user.id
        except Exception:
            pass

    # 自定义 Token（验证码登录）
    session = _get_session_from_token(token)
    if session:
        return session["user_id"]

    raise HTTPException(status_code=401, detail="Invalid session")


def _guess_ext(filename: str, content_type: str) -> str:
    ext = os.path.splitext(filename or "")[1].lower()
    if ext in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return ext if ext != ".jpeg" else ".jpg"
    ct = (content_type or "").lower()
    if ct == "image/png":
        return ".png"
    if ct in {"image/jpg", "image/jpeg"}:
        return ".jpg"
    if ct == "image/webp":
        return ".webp"
    if ct == "image/gif":
        return ".gif"
    return ".png"


def _extract_public_url(res: Any) -> str:
    # supabase-py 不同版本返回可能是 dict 或 str
    if isinstance(res, str):
        return res
    if isinstance(res, dict):
        return res.get("publicUrl") or res.get("publicURL") or res.get("public_url") or ""
    return ""


def _request_base_url(request: Request) -> str:
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "http").split(",")[0].strip()
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc).split(",")[0].strip()
    if not host:
        host = request.url.netloc
    return f"{proto}://{host}".rstrip("/")


def _is_loopback_host(hostname: str) -> bool:
    host = (hostname or "").strip().lower()
    if not host:
        return False
    if host in LOOPBACK_HOSTS:
        return True
    return host.startswith("127.")


def _extract_avatar_path(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    raw = value.strip()
    if not raw:
        return ""

    if "/api/auth/avatar/proxy" in raw:
        parsed_proxy = urlparse(raw)
        q_path = parse_qs(parsed_proxy.query or "").get("path", [""])[0]
        return unquote(q_path or "").strip().lstrip("/")

    if "://" not in raw:
        direct = raw.lstrip("/")
        if not direct:
            return ""
        if "/" not in direct and "." not in direct and len(direct) <= 3:
            # 例如“U”/“JD”后备缩写，不是存储对象路径
            return ""
        return direct

    parsed = urlparse(raw)
    p = parsed.path or ""
    markers = (
        f"/storage/v1/object/public/{AVATAR_BUCKET}/",
        f"/storage/v1/object/sign/{AVATAR_BUCKET}/",
        f"/storage/v1/object/authenticated/{AVATAR_BUCKET}/",
    )
    for marker in markers:
        idx = p.find(marker)
        if idx >= 0:
            return p[idx + len(marker):].lstrip("/")
    return ""


def _build_avatar_proxy_url(request: Request, object_path: str) -> str:
    clean_path = (object_path or "").strip().lstrip("/")
    if not clean_path:
        return ""
    return f"{_request_base_url(request)}/api/auth/avatar/proxy?path={quote(clean_path, safe='/')}"


def _normalize_avatar_for_client(avatar_value: Any, request: Request) -> Any:
    if not isinstance(avatar_value, str):
        return avatar_value
    raw = avatar_value.strip()
    if not raw:
        return raw

    object_path = _extract_avatar_path(raw)
    if not object_path:
        return raw

    parsed = urlparse(raw)
    is_proxy_route = "/api/auth/avatar/proxy" in raw
    if (
        parsed.scheme in {"http", "https"}
        and parsed.hostname
        and not _is_loopback_host(parsed.hostname)
        and not is_proxy_route
    ):
        return raw

    proxy_url = _build_avatar_proxy_url(request, object_path)
    return proxy_url or raw


def _build_signed_url(storage, path: str, expires_in: int = 60 * 60) -> str:
    """bucket 非 public 时，返回短期签名 URL 作为兜底"""
    try:
        signed = storage.create_signed_url(path, expires_in)
        if isinstance(signed, dict):
            return signed.get("signedURL") or signed.get("signed_url") or signed.get("signedUrl") or ""
        return str(signed or "")
    except Exception:
        return ""


# -----------------------------------------------------------------------------
# API模型
# -----------------------------------------------------------------------------
class SendCodeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    phone: str = Field(validation_alias=AliasChoices("phone", "account"))


class LoginRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    phone: str = Field(validation_alias=AliasChoices("phone", "account"))
    password: Optional[str] = None
    code: Optional[str] = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., min_length=10, description="Supabase refresh token")


class RegisterRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    phone: str = Field(validation_alias=AliasChoices("phone", "account"))
    password: str
    code: Optional[str] = None


class UpdateProfileRequest(BaseModel):
    # username 前端会传，但系统不允许改：后端会忽略它（不写入）
    name: Optional[str] = None
    username: Optional[str] = None
    # 头像仅存储 URL（来自存储）
    avatar: Optional[str] = None


class UpdatePasswordRequest(BaseModel):
    old_password: str = Field(..., description="Old password")
    password: str = Field(..., min_length=6, description="New password")


# ✨ [新增] 忘记密码/重置密码请求模型
class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    phone: str = Field(validation_alias=AliasChoices("phone", "account"))
    code: str = Field(..., description="Verification code")
    password: str = Field(..., min_length=6, description="New password")


# -----------------------------------------------------------------------------
# 路线
# -----------------------------------------------------------------------------
@router.post("/send_code")
def api_send_code(req: SendCodeRequest):
    ok = send_login_code(req.phone)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to send SMS code")
    return {"success": True, "status": "success"}


@router.post("/register")
def api_register(req: RegisterRequest):
    phone = str(req.phone or "").strip()
    code = str(req.code or "").strip()
    password = str(req.password or "")

    if not phone:
        raise HTTPException(status_code=400, detail="Phone is required")
    if not code:
        raise HTTPException(status_code=400, detail="Missing verification code")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    if not verify_login_code(phone, code):
        raise HTTPException(status_code=401, detail="Invalid verification code")

    email = _get_email_from_phone(phone)
    sb_admin = get_admin_supabase()
    sb_anon = get_anon_supabase()
    create_error = None

    try:
        sb_admin.auth.admin.create_user({
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {
                "phone": phone,
                "name": f"User_{phone[-4:]}",
                "username": f"User_{phone[-4:]}",
                "register_method": "sms"
            }
        })
    except Exception as e:
        err = str(e)
        err_lower = err.lower()
        duplicate_markers = [
            "already",
            "exist",
            "already registered",
            "duplicate",
            "users_email_key",
            "email_exists",
        ]
        is_duplicate = any(marker in err_lower for marker in duplicate_markers)
        if not is_duplicate:
            print(f"[Auth][register] create_user failed | phone={phone} | email={email} | err={err}")
            raise HTTPException(status_code=400, detail=f"Register failed: {err}")
        create_error = err

    try:
        login_res = sb_anon.auth.sign_in_with_password({
            "email": email,
            "password": password
        })

        return {
            "success": True,
            "token": login_res.session.access_token,
            "refresh_token": _session_value(login_res.session, "refresh_token"),
            "expires_at": _session_value(login_res.session, "expires_at"),
            "user": {
                "id": login_res.user.id,
                "phone": phone,
                "email": email,
                "name": login_res.user.user_metadata.get("name"),
                "username": login_res.user.user_metadata.get("username"),
            }
        }

    except Exception as e:
        err = str(e)
        print(f"[Auth][register] sign_in failed | phone={phone} | email={email} | err={err}")
        if create_error:
            raise HTTPException(status_code=409, detail="This phone is already registered. Please login or reset password.")
        raise HTTPException(status_code=401, detail=f"Login failed: {err}")


@router.post("/login")
def api_login(req: LoginRequest):
    # 避免在登录期间改变共享管理客户端身份验证状态。
    sb_anon = get_anon_supabase(fresh=True)
    sb_admin = get_admin_supabase(fresh=True)
    email = _get_email_from_phone(req.phone)

    # A. 密码登录
    if req.password:
        try:
            auth_res = sb_anon.auth.sign_in_with_password({
                "email": email,
                "password": req.password
            })
            meta = auth_res.user.user_metadata or {}
            # 确保用户名不为空
            if not meta.get("username"):
                meta["username"] = meta.get("name") or f"User_{req.phone[-4:]}"
                try:
                    sb_admin.auth.admin.update_user_by_id(auth_res.user.id, {"user_metadata": meta})
                except Exception:
                    pass

            return {
                "success": True,
                "status": "success",
                "token": auth_res.session.access_token,
                "refresh_token": _session_value(auth_res.session, "refresh_token"),
                "expires_at": _session_value(auth_res.session, "expires_at"),
                "user": {
                    "id": auth_res.user.id,
                    "phone": meta.get("phone", req.phone),
                    "email": auth_res.user.email,
                    "name": meta.get("name"),
                    "username": meta.get("username"),
                    "avatar": meta.get("avatar"),
                }
            }
        except Exception as e:
            if "Email not confirmed" in str(e):
                raise HTTPException(status_code=403, detail="Email not confirmed")
            raise HTTPException(status_code=401, detail="Invalid account or password")

    # B. 验证码登录
    if req.code:
        if not verify_login_code(req.phone, req.code):
            raise HTTPException(status_code=401, detail="Invalid verification code")

        token = f"sms-token-{uuid4()}"
        real_user = _find_or_create_user_by_phone(sb_admin, req.phone)

        if real_user:
            user_id = real_user.id
            u_meta = getattr(real_user, "user_metadata", {}) or {}
            user_name = u_meta.get("name", f"User_{req.phone[-4:]}")
            user_email = real_user.email or email

            # 确保用户名已初始化
            if not u_meta.get("username"):
                u_meta["username"] = user_name
                try:
                    sb_admin.auth.admin.update_user_by_id(user_id, {"user_metadata": u_meta})
                except Exception:
                    pass
        else:
            user_id = f"temp-{req.phone}"
            user_name = f"User_{req.phone[-4:]}"
            user_email = email

        _cache_token(token, user_id, req.phone, user_email)

        return {
            "success": True,
            "status": "success",
            "token": token,
            "user": {
                "id": user_id,
                "phone": req.phone,
                "login_method": "sms",
                "email": user_email,
                "name": user_name
            }
        }

    raise HTTPException(status_code=400, detail="参数错误")


@router.post("/refresh")
def api_refresh(req: RefreshTokenRequest):
    refresh_token = str(req.refresh_token or "").strip()
    if not refresh_token:
        raise HTTPException(status_code=400, detail="Missing refresh token")

    sb_anon = get_anon_supabase(fresh=True)
    supabase_url, anon_key = _get_sb_url_and_key(sb_anon)
    endpoint = f"{supabase_url}/auth/v1/token?grant_type=refresh_token"

    try:
        resp = httpx.post(
            endpoint,
            headers={
                "apikey": anon_key,
                "Content-Type": "application/json",
            },
            json={"refresh_token": refresh_token},
            timeout=10,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Refresh request failed: {str(e)}")

    body: Dict[str, Any]
    try:
        body = resp.json()
    except Exception:
        body = {}

    if resp.status_code >= 400:
        detail = body.get("error_description") or body.get("msg") or "Invalid refresh token"
        err_code = body.get("error_code") or body.get("code")
        print(f"[Auth][refresh] failed | status={resp.status_code} | error_code={err_code} | detail={detail}")
        raise HTTPException(status_code=401, detail=detail)

    access_token = str(body.get("access_token") or "").strip()
    if not access_token:
        raise HTTPException(status_code=500, detail="Refresh succeeded but access token missing")

    next_refresh_token = str(body.get("refresh_token") or refresh_token).strip()
    user = body.get("user") or {}
    user_meta = user.get("user_metadata") if isinstance(user, dict) else {}

    return {
        "success": True,
        "token": access_token,
        "refresh_token": next_refresh_token,
        "expires_at": body.get("expires_at"),
        "user": {
            "id": user.get("id") if isinstance(user, dict) else None,
            "phone": (user_meta or {}).get("phone"),
            "email": user.get("email") if isinstance(user, dict) else None,
            "name": (user_meta or {}).get("name"),
            "username": (user_meta or {}).get("username"),
            "avatar": (user_meta or {}).get("avatar"),
        },
    }


# ✨ [新增] 忘记密码重置接口
@router.post("/reset_password")
def api_reset_password(req: ResetPasswordRequest):
    """
    忘记密码流程：验证手机号+验证码，然后强制重置密码
    """
    # 1. 验证验证码
    if not verify_login_code(req.phone, req.code):
        raise HTTPException(status_code=401, detail="Invalid or expired verification code")

    sb_admin = get_admin_supabase()

    # 2. 查找用户
    email = _get_email_from_phone(req.phone)
    target_email = email.lower().strip()
    target_phone = req.phone.strip()

    user_id = None

    # 尝试查找用户
    user = _find_user_by_loop(sb_admin, target_email, target_phone)
    if user:
        user_id = user.id

    if not user_id:
        raise HTTPException(status_code=404, detail="This phone number is not registered")

    # 3. 强制更新密码
    try:
        sb_admin.auth.admin.update_user_by_id(user_id, {
            "password": req.password
        })
        return {"success": True, "message": "密码重置成功，请重新登录"}
    except Exception as e:
        print(f"[ResetPassword] failed: {e}")
        raise HTTPException(status_code=500, detail="重置密码失败，请稍后重试")


@user_router.get("/profile")
def get_profile(
        request: Request,
        phone: Optional[str] = None,
        x_user_phone: Optional[str] = Header(default=None),
        authorization: Optional[str] = Header(default=None),
):
    sb = require_supabase()
    token = _bearer_token(authorization)
    jwt_error: Optional[Exception] = None

    if token:
        # A. JWT 令牌
        if len(token) > 100:
            try:
                user_res = sb.auth.get_user(token)
                if user_res and user_res.user:
                    u = user_res.user
                    metadata = u.user_metadata or {}
                    default_name = metadata.get("name", "User")
                    app_meta = u.app_metadata or {}
                    role = app_meta.get("role", "user")
                    profile = _sync_profile(u, role)
                    status = (profile or {}).get("status", "active")
                    avatar = _normalize_avatar_for_client(metadata.get("avatar", "S"), request)
                    return {
                        "id": u.id,
                        "phone": metadata.get("phone"),
                        "email": u.email,
                        "name": default_name,
                        "username": metadata.get("username", default_name),
                        "plan": metadata.get("plan", "Enterprise"),
                        "avatar": avatar,
                        "role": role,
                        "status": status,
                        "department": (profile or {}).get("department"),
                        "job_title": (profile or {}).get("job_title"),
                    }
            except Exception as e:
                jwt_error = e

        # B. 自定义代币
        session = _get_session_from_token(token)
        if session:
            try:
                u = sb.auth.admin.get_user_by_id(session["user_id"])
                if u and u.user:
                    metadata = u.user.user_metadata or {}
                    default_name = f"User_{session['phone'][-4:]}"
                    app_meta = u.user.app_metadata or {}
                    role = app_meta.get("role", "user")
                    profile = _sync_profile(u.user, role)
                    status = (profile or {}).get("status", "active")
                    avatar = _normalize_avatar_for_client(metadata.get("avatar", "S"), request)
                    return {
                        "id": u.user.id,
                        "phone": metadata.get("phone", session["phone"]),
                        "email": u.user.email,
                        "name": metadata.get("name", default_name),
                        "username": metadata.get("username", default_name),
                        "plan": metadata.get("plan", "Enterprise"),
                        "avatar": avatar,
                        "role": role,
                        "status": status,
                        "department": (profile or {}).get("department"),
                        "job_title": (profile or {}).get("job_title"),
                    }
            except Exception:
                return {
                    "id": session["user_id"],
                    "phone": session["phone"],
                    "name": f"User_{session['phone'][-4:]}",
                    "username": f"User_{session['phone'][-4:]}",
                    "email": session["email"],
                    "plan": "Enterprise",
                    "avatar": "S"
                }

        # 携带了 token 但既不是有效 JWT，也不是可解析的 sms-token，明确返回 401。
        if jwt_error:
            raise HTTPException(status_code=401, detail="Invalid session")
        raise HTTPException(status_code=401, detail="Invalid session")

    return {"phone": None, "nickname": "Guest", "avatar": None}


@router.get("/avatar/proxy")
def avatar_proxy(path: str = Query(..., description="Storage object path in avatars bucket")):
    clean_path = unquote(str(path or "")).strip().lstrip("/")
    if not clean_path:
        raise HTTPException(status_code=400, detail="Missing avatar path")
    if ".." in clean_path:
        raise HTTPException(status_code=400, detail="Invalid avatar path")

    sb = get_admin_supabase()
    storage = sb.storage.from_(AVATAR_BUCKET)
    try:
        blob = storage.download(clean_path)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Avatar not found: {str(e)}")

    if hasattr(blob, "data"):
        blob = getattr(blob, "data")
    if isinstance(blob, str):
        blob = blob.encode("utf-8", errors="ignore")
    if not isinstance(blob, (bytes, bytearray)):
        raise HTTPException(status_code=502, detail="Avatar storage returned invalid payload")

    media_type = mimetypes.guess_type(clean_path)[0] or "application/octet-stream"
    headers = {"Cache-Control": "public, max-age=300"}
    return Response(content=bytes(blob), media_type=media_type, headers=headers)


@user_router.post("/avatar")
async def upload_avatar(
        request: Request,
        file: UploadFile = File(...),
        authorization: Optional[str] = Header(default=None)
):
    """
    🔥 最终正确版：
    - Write Storage via service_role client (bypass RLS)
    - 仍然用 token 解析真实 user_id
    """
    # ✅ 关键修改：这里必须是 admin client
    sb = get_admin_supabase()

    # ⚠️ 解析 user_id 仍然走原逻辑（JWT / sms-token 都支持）
    token = _bearer_token(authorization)
    user_id = _resolve_user_id(sb, token)

    ct = (file.content_type or "").lower()
    if not ct.startswith("image/"):
        raise HTTPException(status_code=415, detail="Only image files are allowed")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=413, detail="Avatar too large (max 5MB)")

    # 1️⃣ 文件后缀
    ext = _guess_ext(file.filename or "", ct)

    # 2️⃣ 固定路径（避免垃圾文件）
    object_path = f"{user_id}/avatar{ext}"

    try:
        storage = sb.storage.from_(AVATAR_BUCKET)

        # 3️⃣ 上传（Upsert 覆盖）
        storage.upload(
            path=object_path,
            file=data,
            file_options={
                "content-type": str(ct),
                "cache-control": "3600",
                "upsert": "true"
            },
        )

        # 4️⃣ 获取访问 URL
        public_res = storage.get_public_url(object_path)
        public_url = _extract_public_url(public_res)

        if not public_url:
            public_url = _build_signed_url(
                storage,
                object_path,
                expires_in=60 * 60 * 24 * 365
            )

        if not public_url:
            raise Exception("无法获取头像访问链接")

        return {
            "success": True,
            "avatar_url": _build_avatar_proxy_url(request, object_path) or public_url,
            "public_url": public_url,
            "path": object_path
        }

    except Exception as e:
        print(f"Upload avatar error: {e}")
        raise HTTPException(status_code=500, detail=f"Avatar upload failed: {str(e)}")


@user_router.put("/profile")
def update_profile(
        req: UpdateProfileRequest,
        request: Request,
        authorization: Optional[str] = Header(default=None)
):
    """
    更新用户信息：只更新 name / avatar(URL)
    """
    sb_admin = get_admin_supabase()
    token = _bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Not logged in")

    # 只允许更新的字段
    updates = {}
    if req.name is not None:
        updates["name"] = req.name
    if req.avatar is not None:
        updates["avatar"] = _normalize_avatar_for_client(req.avatar, request)  # Storage URL / proxy URL

    if not updates:
        return {"success": True, "message": "Nothing to update"}

    # 从 Supabase JWT 或自定义短信令牌解析 user_id。
    user_id = _resolve_user_id(sb_admin, token)

    # 使用管理 API 修补 user_metadata，因此两种令牌类型都受支持。
    try:
        user_res = sb_admin.auth.admin.get_user_by_id(user_id)
        current_meta = {}
        if user_res and getattr(user_res, "user", None):
            current_meta = getattr(user_res.user, "user_metadata", {}) or {}

        merged_meta = {**current_meta, **updates}
        if not merged_meta.get("username"):
            merged_meta["username"] = merged_meta.get("name") or f"User_{user_id[-4:]}"

        sb_admin.auth.admin.update_user_by_id(user_id, {"user_metadata": merged_meta})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update profile metadata: {str(e)}")

    return {"success": True}


# ✨ [新增] 修改密码接口
@user_router.put("/password")
def update_password(
        req: UpdatePasswordRequest,
        authorization: Optional[str] = Header(default=None)
):
    """
    修改用户密码，需要验证旧密码
    """
    sb_admin = get_admin_supabase()  # 使用 admin client 确保权限
    token = _bearer_token(authorization)

    # 1. 认证：解析user_id
    user_id = _resolve_user_id(sb_admin, token)

    # 2. 获取用户邮箱以便验证旧密码
    try:
        user_res = sb_admin.auth.admin.get_user_by_id(user_id)
        if not user_res or not user_res.user:
            raise Exception("User not found")
        email = user_res.user.email
    except Exception:
        raise HTTPException(status_code=404, detail="Unable to fetch user info")

    # 3. 验证旧密码
    # 注意：使用 Anon Client 来模拟用户登录，以验证密码正确性
    # 这样做可以避免直接处理哈希对比，利用 Supabase Auth 自身的逻辑
    sb_anon = get_anon_supabase()

    try:
        # 尝试使用旧密码登录
        login_res = sb_anon.auth.sign_in_with_password({
            "email": email,
            "password": req.old_password
        })
        if not login_res.user:
            raise Exception("Login failed")
    except Exception as e:
        print(f"[Password] old password verification failed: {e}")
        raise HTTPException(status_code=400, detail="原密码错误，请检查后重试")

    # 4. 修改新密码
    try:
        # 使用 admin 权限直接修改指定用户的密码
        sb_admin.auth.admin.update_user_by_id(user_id, {
            "password": req.password
        })
        return {"success": True, "message": "密码修改成功"}
    except Exception as e:
        print(f"[Password] update failed: {e}")
        raise HTTPException(status_code=500, detail=f"密码修改失败: {str(e)}")

@router.post("/check_account")
def api_check_account(req: SendCodeRequest):
    """Check whether a phone/account is already registered."""
    sb_admin = get_admin_supabase()
    target_email = _get_email_from_phone(req.phone).lower().strip()
    target_phone = req.phone.strip()

    user = _find_user_by_loop(sb_admin, target_email, target_phone)
    registered = user is not None

    return {
        "success": True,
        "registered": registered,
        "reason": "Already registered" if registered else "This phone number is not registered"
    }
