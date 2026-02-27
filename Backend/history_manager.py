from sqlalchemy import text

from supabase_client import engine, supabase


_HISTORY_ID_FIXED = False


def _ensure_history_id_autoincrement():
    """
    Self-heal local schema drift: some migrated databases may miss
    `history.id` default sequence, causing silent insert failures.
    """
    global _HISTORY_ID_FIXED
    if _HISTORY_ID_FIXED:
        return
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE SEQUENCE IF NOT EXISTS public.history_id_seq"))
            conn.execute(
                text(
                    "ALTER TABLE public.history "
                    "ALTER COLUMN id SET DEFAULT nextval('public.history_id_seq')"
                )
            )
            conn.execute(
                text(
                    "SELECT setval("
                    "'public.history_id_seq', "
                    "COALESCE((SELECT MAX(id) FROM public.history), 0) + 1, "
                    "false)"
                )
            )
        _HISTORY_ID_FIXED = True
    except Exception as e:
        print(f"[History] ensure history.id sequence failed: {e}")


def _count_history_rows(user_id):
    try:
        res = (
            supabase.table("history")
            .select("id", count="exact", head=True)
            .eq("user_id", str(user_id))
            .execute()
        )
        return int(res.count or 0)
    except Exception:
        return 0


def _relink_legacy_history_by_email(user_id):
    """
    If current user has no history, try to migrate legacy rows from profiles
    that share the same email but use an older user_id.
    """
    uid = str(user_id)
    try:
        prof_res = supabase.table("profiles").select("email").eq("id", uid).limit(1).execute()
        profile_rows = prof_res.data or []
        if not profile_rows:
            return 0

        email = (profile_rows[0].get("email") or "").strip().lower()
        if not email:
            return 0

        legacy_profiles = (
            supabase.table("profiles")
            .select("id")
            .eq("email", email)
            .neq("id", uid)
            .execute()
        )

        moved_rows = 0
        for row in (legacy_profiles.data or []):
            legacy_id = row.get("id")
            if not legacy_id:
                continue

            legacy_count = _count_history_rows(legacy_id)
            if legacy_count <= 0:
                continue

            supabase.table("history").update({"user_id": uid}).eq("user_id", str(legacy_id)).execute()
            supabase.table("session_titles").update({"user_id": uid}).eq("user_id", str(legacy_id)).execute()
            moved_rows += legacy_count

            print(f"[History] relinked legacy history {legacy_id} -> {uid}, rows={legacy_count}")

        return moved_rows
    except Exception as e:
        print(f"[History] relink failed: {e}")
        return 0


def add_history_to_supabase(user_id, session_id, func_type, role, content):
    try:
        _ensure_history_id_autoincrement()
        supabase.table("history").insert({
            "user_id": str(user_id),
            "session_id": str(session_id),
            "func_type": func_type,
            "role": role,
            "content": content
        }).execute()
        return True
    except Exception as e:
        print(f"Error logging history: {e}")
        return False


def save_context(user_id, session_id, content, func_type="context_save"):
    """保存上下文并自动命名"""
    try:
        role = "meta" if func_type == "session_meta" else "context"

        saved = add_history_to_supabase(
            user_id=user_id,
            session_id=session_id,
            func_type=func_type,
            role=role,
            content=content
        )
        if not saved:
            return False

        if role == "context":
            titles = {
                "voice_context": "会议记录",
                "ocr_context": "OCR 结果",
                "audit_context": "审计日志",
            }
            default_title = titles.get(func_type, "新聊天")
            rename_session(user_id, session_id, default_title)
        return True
    except Exception as e:
        print(f"Error saving context: {e}")
        return False


def get_history(user_id, session_id):
    """
    Retrieve messages of the specified session.
    """
    try:
        res = supabase.table("history") \
            .select("*") \
            .eq("session_id", session_id) \
            .eq("user_id", str(user_id)) \
            .order("created_at") \
            .execute()
        return res.data
    except Exception as e:
        print(f"Error fetching history: {e}")
        return []


def get_history_limited(user_id, session_id, limit=20):
    """
    Fetch recent history items with a hard limit to avoid large payloads.
    """
    try:
        res = supabase.table("history") \
            .select("role, content, created_at, func_type") \
            .eq("session_id", session_id) \
            .eq("user_id", str(user_id)) \
            .order("created_at", desc=True) \
            .limit(limit) \
            .execute()
        data = res.data or []
        return list(reversed(data))
    except Exception as e:
        print(f"Error fetching limited history: {e}")
        return []


def get_user_sessions(user_id):
    """
    Retrieve recent sessions for the user.
    优化点：
    1. 增加健壮性，确保即使消息记录很多，会话也不会消失。
    2. 兼容 Python 3.10 (修复 f-string 中不能使用反斜杠的问题)。
    """
    try:
        # 1. 获取该用户所有的自定义标题
        custom_titles = {}
        t_res = supabase.table("session_titles").select("session_id, title").eq("user_id", str(user_id)).execute()
        for row in (t_res.data or []):
            sid = row.get('session_id')
            title = row.get('title')
            if sid:
                custom_titles[sid] = title

        # 2. 查询最近的消息记录
        res = supabase.table("history") \
            .select("session_id, content, created_at, role") \
            .eq("user_id", str(user_id)) \
            .order("created_at", desc=True) \
            .limit(4000) \
            .execute()

        # If current account has no history, try to merge legacy rows that
        # belong to another profile id with the same email.
        if not (t_res.data or []) and not (res.data or []):
            moved = _relink_legacy_history_by_email(user_id)
            if moved > 0:
                custom_titles = {}
                t_res = supabase.table("session_titles").select("session_id, title").eq("user_id", str(user_id)).execute()
                for row in (t_res.data or []):
                    sid = row.get('session_id')
                    title = row.get('title')
                    if sid:
                        custom_titles[sid] = title

                res = supabase.table("history") \
                    .select("session_id, content, created_at, role") \
                    .eq("user_id", str(user_id)) \
                    .order("created_at", desc=True) \
                    .limit(4000) \
                    .execute()

        sessions = []
        seen_sessions = set()

        # 3. 遍历消息，构建基础会话列表
        for row in (res.data or []):
            sid = row.get('session_id')
            if not sid:
                continue
            if sid in seen_sessions:
                continue

            # 只要是用户发过的、或者是系统上下文或者是有标题的，都属于有效会话
            role = row.get('role')
            is_valid = role in ['user', 'context'] or sid in custom_titles

            if is_valid:
                seen_sessions.add(sid)
                title = custom_titles.get(sid)

                if not title:
                    # ✨ 兼容性修复：在 Python 3.10 中，不能在 f-string 的 {} 内直接写 \n
                    prefix = "[记录] " if role == 'context' else ""
                    raw_content = row.get('content') or ""
                    clean_content = str(raw_content)[:30].replace('\n', ' ')
                    title = f"{prefix}{clean_content}..."

                created_at = row.get('created_at')
                if created_at is None:
                    created_at = ""
                elif not isinstance(created_at, str):
                    try:
                        created_at = created_at.isoformat()
                    except Exception:
                        created_at = str(created_at)

                sessions.append({
                    "id": sid,
                    "title": title,
                    "date": created_at
                })

        # 3.1 兜底：如果因为角色过滤导致会话为空，允许用任意角色填充
        if not sessions and (res.data or []):
            for row in (res.data or []):
                sid = row.get('session_id')
                if not sid or sid in seen_sessions:
                    continue
                seen_sessions.add(sid)
                title = custom_titles.get(sid)
                if not title:
                    raw_content = row.get('content') or ""
                    clean_content = str(raw_content)[:30].replace('\n', ' ')
                    title = f"{clean_content}..."
                created_at = row.get('created_at')
                if created_at is None:
                    created_at = ""
                elif not isinstance(created_at, str):
                    try:
                        created_at = created_at.isoformat()
                    except Exception:
                        created_at = str(created_at)
                sessions.append({
                    "id": sid,
                    "title": title,
                    "date": created_at
                })

        # 4. 兜底逻辑：拉取有标题但没在最近消息中出现的旧会话
        for sid, title in custom_titles.items():
            if sid not in seen_sessions:
                sessions.append({
                    "id": sid,
                    "title": title,
                    "date": "2024-01-01T00:00:00"
                })

        sessions.sort(key=lambda x: x.get('date') or "", reverse=True)
        return sessions
    except Exception as e:
        print(f"Error fetching sessions: {e}")
        return []


def delete_session(user_id, session_id):
    """Delete one session and its title rows."""
    try:
        supabase.table("history").delete().eq("session_id", session_id).eq("user_id", str(user_id)).execute()
        supabase.table("session_titles").delete().eq("session_id", session_id).eq("user_id", str(user_id)).execute()
        return True
    except Exception as e:
        print(f"Error deleting session: {e}")
        return False


def rename_session(user_id, session_id, new_title):
    """Rename session title."""
    try:
        supabase.table("session_titles").upsert({
            "session_id": str(session_id),
            "user_id": str(user_id),
            "title": new_title
        }).execute()
        return True
    except Exception as e:
        print(f"Error renaming session: {e}")
        return False

