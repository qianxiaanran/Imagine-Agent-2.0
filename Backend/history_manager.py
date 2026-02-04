from supabase_client import supabase


def add_history_to_supabase(user_id, session_id, func_type, role, content):
    """写入历史记录"""
    try:
        supabase.table("history").insert({
            "user_id": str(user_id),
            "session_id": str(session_id),
            "func_type": func_type,
            "role": role,
            "content": content
        }).execute()
    except Exception as e:
        print(f"Error logging history: {e}")


def save_context(user_id, session_id, content, func_type="context_save"):
    """保存上下文并自动命名"""
    try:
        role = "meta" if func_type == "session_meta" else "context"

        add_history_to_supabase(
            user_id=user_id,
            session_id=session_id,
            func_type=func_type,
            role=role,
            content=content
        )

        if role == "context":
            titles = {
                "voice_context": "会议录音转写",
                "ocr_context": "文档识别结果",
                "audit_context": "智能审单记录"
            }
            default_title = titles.get(func_type, "新对话")
            rename_session(user_id, session_id, default_title)
        return True
    except Exception as e:
        print(f"Error saving context: {e}")
        return False


def get_history(user_id, session_id):
    """
    获取指定会话的消息记录。
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
            .select("role, content, created_at") \
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
    获取用户的最近会话列表。
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

        sessions = []
        seen_sessions = set()

        # 3. 遍历消息，构建基础会话列表
        for row in (res.data or []):
            sid = row.get('session_id')
            if not sid:
                continue
            if sid in seen_sessions:
                continue

            # 只要是用户发过的、或者是系统上下文、或者是有标题的，都属于有效会话
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
    """物理删除或隐藏会话"""
    try:
        supabase.table("history").delete().eq("session_id", session_id).eq("user_id", str(user_id)).execute()
        supabase.table("session_titles").delete().eq("session_id", session_id).eq("user_id", str(user_id)).execute()
        return True
    except Exception as e:
        print(f"Error deleting session: {e}")
        return False


def rename_session(user_id, session_id, new_title):
    """重命名会话"""
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
