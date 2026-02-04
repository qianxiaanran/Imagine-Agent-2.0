from __future__ import annotations
import httpx
from typing import Optional, Dict, Any
from uuid import uuid4
import time
import os

from fastapi import APIRouter, HTTPException, Header, UploadFile, File
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
MAX_AVATAR_BYTES = 5 * 1024 * 1024  # 调整为 5MB 稍微宽容一点

# -----------------------------------------------------------------------------
# 内存缓存层
# -----------------------------------------------------------------------------
_TOKEN_CACHE: Dict[str, Dict[str, Any]] = {}


def _get_sb_url_and_key(sb) -> tuple[str, str]:
    # 优先从 supabase client 对象里取（不同版本字段名可能不同）
    url = getattr(sb, "supabase_url", None) or getattr(sb, "_supabase_url", None) or ""
    key = getattr(sb, "supabase_key", None) or getattr(sb, "_supabase_key", None) or ""
    # 兜底从环境变量取（你 supabase_client 里通常也是从环境变量读）
    if not url:
        url = os.getenv("SUPABASE_URL", "") or os.getenv("SUPABASE_PROJECT_URL", "")
    if not key:
        # 这里必须是 anon key（不是 service role 也行）
        key = os.getenv("SUPABASE_ANON_KEY", "") or os.getenv("SUPABASE_KEY", "")
    if not url or not key:
        raise HTTPException(status_code=500, detail="后端缺少 SUPABASE_URL / SUPABASE_ANON_KEY 配置")
    return url.rstrip("/"), key


def _update_user_metadata_via_gotrue(sb, jwt_token: str, data: dict) -> None:
    """
    调 Supabase GoTrue 更新 user_metadata：PUT /auth/v1/user
    需要：Authorization Bearer <jwt> + apikey(anon)
    """
    supabase_url, anon_key = _get_sb_url_and_key(sb)
    endpoint = f"{supabase_url}/auth/v1/user"

    headers = {
        "apikey": anon_key,
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json",
    }

    # 只更新 user_metadata：payload 使用 {"data": {...}}
    payload = {"data": data}

    try:
        r = httpx.put(endpoint, headers=headers, json=payload, timeout=10)
        if r.status_code >= 400:
            # 常见：401 = token 不是 Supabase JWT（比如你的 sms-token）
            detail = ""
            try:
                detail = r.json()
            except Exception:
                detail = r.text
            raise HTTPException(status_code=401 if r.status_code == 401 else 500,
                                detail=f"Supabase 更新失败({r.status_code}): {detail}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase 更新失败: {str(e)}")


def _cache_token(token: str, user_id: str, phone: str, email: str):
    """缓存 Token 与 真实 UserID 的映射关系"""
    _TOKEN_CACHE[token] = {
        "user_id": user_id,
        "phone": phone,
        "email": email,
        "expires_at": time.time() + (7 * 24 * 3600)
    }


def _get_session_from_token(token: str) -> Optional[Dict]:
    """??????????????"""
    if token in _TOKEN_CACHE:
        session = _TOKEN_CACHE[token]
        if session["expires_at"] > time.time():
            return session
        else:
            del _TOKEN_CACHE[token]
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
    """统一解析 user_id：JWT token 或自定义 sms-token"""
    if not token:
        raise HTTPException(status_code=401, detail="未登录")

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

    raise HTTPException(status_code=401, detail="无效的会话")


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
# API Models
# -----------------------------------------------------------------------------
class SendCodeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    phone: str = Field(validation_alias=AliasChoices("phone", "account"))


class LoginRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    phone: str = Field(validation_alias=AliasChoices("phone", "account"))
    password: Optional[str] = None
    code: Optional[str] = None


class RegisterRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    phone: str = Field(validation_alias=AliasChoices("phone", "account"))
    password: str
    code: Optional[str] = None


class UpdateProfileRequest(BaseModel):
    # username 前端会传，但系统不允许改：后端会忽略它（不写入）
    name: Optional[str] = None
    username: Optional[str] = None
    # avatar 只允许存 URL（来自 Storage）
    avatar: Optional[str] = None


class UpdatePasswordRequest(BaseModel):
    old_password: str = Field(..., description="原密码")
    password: str = Field(..., min_length=6, description="新密码")


# ✨ [新增] 忘记密码/重置密码请求模型
class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    phone: str = Field(validation_alias=AliasChoices("phone", "account"))
    code: str = Field(..., description="验证码")
    password: str = Field(..., min_length=6, description="新密码")


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@router.post("/send_code")
def api_send_code(req: SendCodeRequest):
    ok = send_login_code(req.phone)
    if not ok:
        raise HTTPException(status_code=500, detail="短信发送失败")
    return {"success": True, "status": "success"}


@router.post("/register")
def api_register(req: RegisterRequest):
    # 1️⃣ 校验验证码
    if not req.code:
        raise HTTPException(status_code=400, detail="缺少验证码 code")

    if not verify_login_code(req.phone, req.code):
        raise HTTPException(status_code=401, detail="验证码错误")

    email = _get_email_from_phone(req.phone)

    sb_admin = get_admin_supabase()
    sb_anon = get_anon_supabase()

    try:
        # 2️⃣ 创建用户（Admin API）
        sb_admin.auth.admin.create_user({
            "email": email,
            "password": req.password,
            "email_confirm": True,
            "user_metadata": {
                "phone": req.phone,
                "name": f"User_{req.phone[-4:]}",
                "username": f"User_{req.phone[-4:]}",  # 只初始化一次
                "register_method": "sms"
            }
        })

    except Exception as e:
        err = str(e)
        # 用户已存在 → 继续走登录
        if "already" not in err.lower() and "exist" not in err.lower():
            raise HTTPException(status_code=400, detail=f"注册失败: {err}")

    # 3️⃣ 登录（Anon API）
    try:
        login_res = sb_anon.auth.sign_in_with_password({
            "email": email,
            "password": req.password
        })

        return {
            "success": True,
            "token": login_res.session.access_token,
            "refresh_token": _session_value(login_res.session, "refresh_token"),
            "expires_at": _session_value(login_res.session, "expires_at"),
            "user": {
                "id": login_res.user.id,
                "phone": req.phone,
                "email": email,
                "name": login_res.user.user_metadata.get("name"),
                "username": login_res.user.user_metadata.get("username"),
            }
        }

    except Exception as e:
        raise HTTPException(status_code=401, detail=f"登录失败: {str(e)}")


@router.post("/login")
def api_login(req: LoginRequest):
    sb = require_supabase()
    email = _get_email_from_phone(req.phone)

    # A. 密码登录
    if req.password:
        try:
            auth_res = sb.auth.sign_in_with_password({
                "email": email,
                "password": req.password
            })
            meta = auth_res.user.user_metadata or {}
            # 确保 username 不为空
            if not meta.get("username"):
                meta["username"] = meta.get("name") or f"User_{req.phone[-4:]}"
                try:
                    sb.auth.admin.update_user_by_id(auth_res.user.id, {"user_metadata": meta})
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
                raise HTTPException(status_code=403, detail="账号未验证")
            raise HTTPException(status_code=401, detail="账号或密码错误")

    # B. 验证码登录
    if req.code:
        if not verify_login_code(req.phone, req.code):
            raise HTTPException(status_code=401, detail="验证码错误")

        token = f"sms-token-{uuid4()}"
        real_user = _find_or_create_user_by_phone(sb, req.phone)

        if real_user:
            user_id = real_user.id
            u_meta = getattr(real_user, "user_metadata", {}) or {}
            user_name = u_meta.get("name", f"User_{req.phone[-4:]}")
            user_email = real_user.email or email

            # 确保 username 初始化
            if not u_meta.get("username"):
                u_meta["username"] = user_name
                try:
                    sb.auth.admin.update_user_by_id(user_id, {"user_metadata": u_meta})
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


# ✨ [新增] 忘记密码重置接口
@router.post("/reset_password")
def api_reset_password(req: ResetPasswordRequest):
    """
    忘记密码流程：验证手机号+验证码，然后强制重置密码
    """
    # 1. 验证验证码
    if not verify_login_code(req.phone, req.code):
        raise HTTPException(status_code=401, detail="验证码错误或已过期")

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
        raise HTTPException(status_code=404, detail="该手机号尚未注册")

    # 3. 强制更新密码
    try:
        sb_admin.auth.admin.update_user_by_id(user_id, {
            "password": req.password
        })
        return {"success": True, "message": "密码重置成功，请重新登录"}
    except Exception as e:
        print(f"❌ Reset password failed: {e}")
        raise HTTPException(status_code=500, detail="重置密码失败，请稍后重试")


@user_router.get("/profile")
def get_profile(
        phone: Optional[str] = None,
        x_user_phone: Optional[str] = Header(default=None),
        authorization: Optional[str] = Header(default=None),
):
    sb = require_supabase()
    token = _bearer_token(authorization)

    if token:
        # A. JWT Token
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
                    return {
                        "id": u.id,
                        "phone": metadata.get("phone"),
                        "email": u.email,
                        "name": default_name,
                        "username": metadata.get("username", default_name),
                        "plan": metadata.get("plan", "Enterprise"),
                        "avatar": metadata.get("avatar", "S"),
                        "role": role,
                        "status": status,
                        "department": (profile or {}).get("department"),
                        "job_title": (profile or {}).get("job_title"),
                    }
            except Exception:
                pass

        # B. 自定义 Token
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
                    return {
                        "id": u.user.id,
                        "phone": metadata.get("phone", session["phone"]),
                        "email": u.user.email,
                        "name": metadata.get("name", default_name),
                        "username": metadata.get("username", default_name),
                        "plan": metadata.get("plan", "Enterprise"),
                        "avatar": metadata.get("avatar", "S"),
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

    return {"phone": None, "nickname": "???", "avatar": None}


@user_router.post("/avatar")
async def upload_avatar(
        file: UploadFile = File(...),
        authorization: Optional[str] = Header(default=None)
):
    """
    🔥 最终正确版：
    - 使用 service_role client 写 Storage（绕过 RLS）
    - 仍然用 token 解析真实 user_id
    """
    # ✅ 关键修改：这里必须是 admin client
    sb = get_admin_supabase()

    # ⚠️ 解析 user_id 仍然走原逻辑（JWT / sms-token 都支持）
    token = _bearer_token(authorization)
    user_id = _resolve_user_id(sb, token)

    ct = (file.content_type or "").lower()
    if not ct.startswith("image/"):
        raise HTTPException(status_code=415, detail="只允许上传图片文件")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="空文件")
    if len(data) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=413, detail="头像过大（最大 5MB）")

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
            "avatar_url": public_url,
            "path": object_path
        }

    except Exception as e:
        print(f"Upload avatar error: {e}")
        raise HTTPException(status_code=500, detail=f"头像上传失败: {str(e)}")


@user_router.put("/profile")
def update_profile(
        req: UpdateProfileRequest,
        authorization: Optional[str] = Header(default=None)
):
    """
    更新用户信息：只更新 name / avatar(URL)
    """
    sb = require_supabase()
    token = _bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="未登录")

    # 只允许更新的字段
    updates = {}
    if req.name is not None:
        updates["name"] = req.name
    if req.avatar is not None:
        updates["avatar"] = req.avatar  # Storage URL

    if not updates:
        return {"success": True, "message": "Nothing to update"}

    # 重要：只有 Supabase JWT 才能调用 /auth/v1/user
    if len(token) <= 100:
        raise HTTPException(status_code=401,
                            detail="当前 token 不是 Supabase JWT（疑似短信自定义 token），无法更新资料。请使用密码登录或让短信登录返回 JWT。")

    # 直接走 GoTrue REST，更新 user_metadata
    _update_user_metadata_via_gotrue(sb, token, updates)
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

    # 1. 鉴权：获取 user_id
    user_id = _resolve_user_id(sb_admin, token)

    # 2. 获取用户邮箱以便验证旧密码
    try:
        user_res = sb_admin.auth.admin.get_user_by_id(user_id)
        if not user_res or not user_res.user:
            raise Exception("User not found")
        email = user_res.user.email
    except Exception:
        raise HTTPException(status_code=404, detail="无法获取用户信息")

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
        print(f"❌ 验证旧密码失败: {e}")
        raise HTTPException(status_code=400, detail="原密码错误，请检查后重试")

    # 4. 修改新密码
    try:
        # 使用 admin 权限直接修改指定用户的密码
        sb_admin.auth.admin.update_user_by_id(user_id, {
            "password": req.password
        })
        return {"success": True, "message": "密码修改成功"}
    except Exception as e:
        print(f"❌ 修改密码失败: {e}")
        raise HTTPException(status_code=500, detail=f"密码修改失败: {str(e)}")
