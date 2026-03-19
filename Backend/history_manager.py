from sqlalchemy import text

from datetime import datetime

from supabase_client import engine, supabase


_HISTORY_ID_FIXED = False
_SESSION_LIST_INDEXES_FIXED = False
_SESSION_LIST_LIMIT = 500
_HISTORY_PAGE_LIMIT_DEFAULT = 40
_HISTORY_PAGE_LIMIT_MAX = 100


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


def _ensure_session_list_indexes():
    global _SESSION_LIST_INDEXES_FIXED
    if _SESSION_LIST_INDEXES_FIXED:
        return
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_history_user_session_created_at "
                    "ON public.history (user_id, session_id, created_at DESC)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_history_user_created_at "
                    "ON public.history (user_id, created_at DESC)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_session_titles_user_session "
                    "ON public.session_titles (user_id, session_id)"
                )
            )
        _SESSION_LIST_INDEXES_FIXED = True
    except Exception as e:
        print(f"[History] ensure session list indexes failed: {e}")


def _normalize_session_date(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    try:
        return value.isoformat()
    except Exception:
        return str(value)


def _normalize_history_page_limit(limit):
    try:
        value = int(limit or _HISTORY_PAGE_LIMIT_DEFAULT)
    except Exception:
        value = _HISTORY_PAGE_LIMIT_DEFAULT
    return max(1, min(value, _HISTORY_PAGE_LIMIT_MAX))


def _derive_session_title(role, content):
    raw_content = str(content or "").replace("\n", " ").strip()
    if not raw_content:
        return "新聊天"
    prefix = "[记录] " if str(role or "").strip().lower() == "context" else ""
    return f"{prefix}{raw_content[:30]}..."


def _fetch_latest_session_rows(user_id):
    _ensure_session_list_indexes()
    try:
        with engine.begin() as conn:
            result = conn.execute(
                text(
                    """
                    SELECT
                        latest.session_id,
                        latest.content AS latest_content,
                        latest.created_at,
                        latest.role AS latest_role,
                        seed.content AS seed_content,
                        seed.role AS seed_role
                    FROM (
                        SELECT DISTINCT ON (h.session_id)
                            h.session_id,
                            h.content,
                            h.created_at,
                            h.role
                        FROM public.history AS h
                        WHERE h.user_id = :user_id
                          AND h.role IN ('user', 'assistant', 'context')
                        ORDER BY h.session_id, h.created_at DESC
                    ) AS latest
                    LEFT JOIN LATERAL (
                        SELECT
                            h2.content,
                            h2.role
                        FROM public.history AS h2
                        WHERE h2.user_id = :user_id
                          AND h2.session_id = latest.session_id
                          AND h2.role IN ('user', 'context')
                        ORDER BY h2.created_at ASC
                        LIMIT 1
                    ) AS seed ON TRUE
                    ORDER BY latest.created_at DESC
                    LIMIT :limit
                    """
                ),
                {"user_id": str(user_id), "limit": _SESSION_LIST_LIMIT},
            )
            return [dict(row) for row in result.mappings().all()]
    except Exception as e:
        print(f"[History] fetch latest sessions failed: {e}")
        return []


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


def add_history_turn_to_supabase(user_id, session_id, func_type, user_content, assistant_content):
    """Insert a user/assistant turn and return the persisted history ids."""
    try:
        _ensure_history_id_autoincrement()
        with engine.begin() as conn:
            result = conn.execute(
                text(
                    """
                    INSERT INTO public.history (user_id, session_id, func_type, role, content)
                    VALUES
                        (:user_id, :session_id, :func_type, 'user', :user_content),
                        (:user_id, :session_id, :func_type, 'assistant', :assistant_content)
                    RETURNING id, role
                    """
                ),
                {
                    "user_id": str(user_id),
                    "session_id": str(session_id),
                    "func_type": func_type,
                    "user_content": "" if user_content is None else str(user_content),
                    "assistant_content": "" if assistant_content is None else str(assistant_content),
                },
            )
            id_map = {}
            for row in result.mappings().all():
                role = str(row.get("role") or "").strip().lower()
                row_id = row.get("id")
                if role and row_id is not None:
                    id_map[role] = int(row_id)
            return {
                "user_id": id_map.get("user"),
                "assistant_id": id_map.get("assistant"),
            }
    except Exception as e:
        print(f"Error logging history turn: {e}")
        return None


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


def get_history_context_bundle(user_id, session_id):
    """Fetch supporting context/meta records used to restore workspace state."""
    try:
        with engine.begin() as conn:
            result = conn.execute(
                text(
                    """
                    SELECT id, role, content, created_at, func_type
                    FROM public.history
                    WHERE session_id = :session_id
                      AND user_id = :user_id
                      AND role IN ('context', 'meta')
                    ORDER BY id ASC
                    """
                ),
                {"session_id": str(session_id), "user_id": str(user_id)},
            )
            return [dict(row) for row in result.mappings().all()]
    except Exception as e:
        print(f"Error fetching history context bundle: {e}")
        return []


def get_history_page(user_id, session_id, limit=40, before_id=None, include_context=False):
    """
    Fetch chat messages by page for long sessions.
    Returns messages in ascending order for direct frontend consumption.
    """
    page_limit = _normalize_history_page_limit(limit)
    params = {
        "session_id": str(session_id),
        "user_id": str(user_id),
        "limit": page_limit + 1,
    }
    before_clause = ""
    if before_id not in (None, ""):
        try:
            params["before_id"] = int(before_id)
            before_clause = "AND id < :before_id"
        except Exception:
            before_clause = ""

    try:
        with engine.begin() as conn:
            result = conn.execute(
                text(
                    f"""
                    SELECT id, role, content, created_at, func_type
                    FROM public.history
                    WHERE session_id = :session_id
                      AND user_id = :user_id
                      AND role IN ('user', 'assistant')
                      {before_clause}
                    ORDER BY id DESC
                    LIMIT :limit
                    """
                ),
                params,
            )
            rows = [dict(row) for row in result.mappings().all()]
    except Exception as e:
        print(f"Error fetching history page: {e}")
        rows = []

    has_more = len(rows) > page_limit
    page_rows = rows[:page_limit]
    next_before_id = page_rows[-1].get("id") if has_more and page_rows else None
    context_items = []
    if include_context and before_id in (None, ""):
        context_items = get_history_context_bundle(user_id, session_id)

    return {
        "items": list(reversed(page_rows)),
        "context_items": context_items,
        "limit": page_limit,
        "has_more": has_more,
        "next_before_id": next_before_id,
    }


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
    使用“每个会话最新一条”查询替代大量历史扫描，避免高消息量用户侧栏退化。
    """
    try:
        custom_titles = {}
        t_res = supabase.table("session_titles").select("session_id, title").eq("user_id", str(user_id)).execute()
        for row in (t_res.data or []):
            sid = row.get('session_id')
            title = row.get('title')
            if sid:
                custom_titles[sid] = title

        latest_rows = _fetch_latest_session_rows(user_id)

        if not (t_res.data or []) and not latest_rows:
            moved = _relink_legacy_history_by_email(user_id)
            if moved > 0:
                custom_titles = {}
                t_res = supabase.table("session_titles").select("session_id, title").eq("user_id", str(user_id)).execute()
                for row in (t_res.data or []):
                    sid = row.get('session_id')
                    title = row.get('title')
                    if sid:
                        custom_titles[sid] = title
                latest_rows = _fetch_latest_session_rows(user_id)

        sessions = []
        seen_sessions = set()

        for row in latest_rows:
            sid = row.get('session_id')
            if not sid or sid in seen_sessions:
                continue
            seen_sessions.add(sid)
            title = custom_titles.get(sid)
            if not title:
                seed_content = row.get("seed_content")
                seed_role = row.get("seed_role")
                if seed_content:
                    title = _derive_session_title(seed_role, seed_content)
                else:
                    title = _derive_session_title(row.get("latest_role"), row.get("latest_content"))
            sessions.append({
                "id": sid,
                "title": title,
                "date": _normalize_session_date(row.get("created_at"))
            })

        for sid, title in custom_titles.items():
            if sid not in seen_sessions:
                sessions.append({
                    "id": sid,
                    "title": title,
                    "date": ""
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

