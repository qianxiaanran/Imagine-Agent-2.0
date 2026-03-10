import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from history_manager import get_history, get_history_limited
from supabase_client import engine, supabase

_SCHEMA_READY = False
_SCHEMA_LOCK = Lock()
_LAST_ERROR = ""
SHARE_SNAPSHOT_HEAD_MESSAGES = 8
SHARE_SNAPSHOT_TAIL_MESSAGES = 80
SHARE_SNAPSHOT_MAX_CONTENT_CHARS = 5000


def _set_last_error(message: str) -> None:
    global _LAST_ERROR
    _LAST_ERROR = str(message or "").strip()


def get_last_error() -> str:
    return _LAST_ERROR


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _ensure_share_schema() -> bool:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return True

    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return True

        try:
            with engine.begin() as conn:
                # 保持表定义与现有架构兼容。
                conn.execute(
                    text(
                        """
                        create table if not exists public.share_links (
                          id bigint primary key,
                          session_id text not null,
                          owner_user_id text not null,
                          token_hash text not null,
                          title text,
                          expires_at timestamptz,
                          revoked boolean not null default false,
                          created_at timestamptz not null default now(),
                          last_access_at timestamptz
                        );
                        """
                    )
                )
                conn.execute(
                    text(
                        """
                        alter table public.share_links
                        alter column session_id type text using session_id::text;
                        """
                    )
                )
                conn.execute(
                    text(
                        """
                        alter table public.share_links
                        alter column owner_user_id type text using owner_user_id::text;
                        """
                    )
                )
                conn.execute(
                    text(
                        """
                        create table if not exists public.share_snapshots (
                          id bigint primary key,
                          share_link_id bigint not null,
                          payload jsonb not null,
                          created_at timestamptz not null default now()
                        );
                        """
                    )
                )

                conn.execute(text("create sequence if not exists public.share_links_id_seq;"))
                conn.execute(text("create sequence if not exists public.share_snapshots_id_seq;"))

                conn.execute(
                    text(
                        """
                        alter table public.share_links
                        alter column id set default nextval('public.share_links_id_seq');
                        """
                    )
                )
                conn.execute(
                    text(
                        """
                        alter table public.share_snapshots
                        alter column id set default nextval('public.share_snapshots_id_seq');
                        """
                    )
                )

                conn.execute(
                    text(
                        """
                        alter sequence public.share_links_id_seq
                        owned by public.share_links.id;
                        """
                    )
                )
                conn.execute(
                    text(
                        """
                        alter sequence public.share_snapshots_id_seq
                        owned by public.share_snapshots.id;
                        """
                    )
                )

                conn.execute(
                    text(
                        """
                        select setval(
                          'public.share_links_id_seq',
                          coalesce((select max(id) from public.share_links), 0) + 1,
                          false
                        );
                        """
                    )
                )
                conn.execute(
                    text(
                        """
                        select setval(
                          'public.share_snapshots_id_seq',
                          coalesce((select max(id) from public.share_snapshots), 0) + 1,
                          false
                        );
                        """
                    )
                )

                conn.execute(
                    text(
                        """
                        create unique index if not exists share_links_token_hash_uq
                        on public.share_links(token_hash);
                        """
                    )
                )
                conn.execute(
                    text(
                        """
                        create index if not exists share_snapshots_share_link_id_idx
                        on public.share_snapshots(share_link_id);
                        """
                    )
                )

                conn.execute(
                    text(
                        """
                        do $$
                        begin
                          if not exists (
                            select 1
                            from pg_constraint
                            where conname = 'share_snapshots_share_link_id_fkey'
                          ) then
                            alter table public.share_snapshots
                            add constraint share_snapshots_share_link_id_fkey
                            foreign key (share_link_id)
                            references public.share_links(id)
                            on delete cascade;
                          end if;
                        end
                        $$;
                        """
                    )
                )

            _SCHEMA_READY = True
            return True
        except Exception as exc:
            _set_last_error(f"Share schema init failed: {exc}")
            return False


def _normalize_days(days: Any) -> int:
    try:
        value = int(days)
    except Exception:
        value = 7
    if value < 0:
        return 0
    if value > 3650:
        return 3650
    return value


def _truncate_share_content(value: Any) -> str:
    text = str(value or "")
    if len(text) <= SHARE_SNAPSHOT_MAX_CONTENT_CHARS:
        return text
    return text[:SHARE_SNAPSHOT_MAX_CONTENT_CHARS] + "\n\n[内容已为分享快照截断]"


def _build_snapshot(raw_history: List[Dict[str, Any]], total_count: Optional[int] = None) -> List[Dict[str, Any]]:
    snapshot_data: List[Dict[str, Any]] = []
    allowed_roles = {"user", "assistant", "system", "context", "meta"}
    for msg in raw_history or []:
        role = msg.get("role")
        if role not in allowed_roles:
            continue
        snapshot_data.append(
            {
                "role": role,
                "content": _truncate_share_content(msg.get("content")),
                "created_at": msg.get("created_at"),
                "func_type": msg.get("func_type"),
            }
        )
    if total_count and total_count > len(snapshot_data):
        omitted = max(int(total_count) - len(snapshot_data), 0)
        if omitted > 0:
            insert_at = min(SHARE_SNAPSHOT_HEAD_MESSAGES, len(snapshot_data))
            snapshot_data.insert(
                insert_at,
                {
                    "role": "assistant",
                    "content": f"为控制分享快照体积，已省略中间约 {omitted} 条历史消息。",
                    "created_at": None,
                    "func_type": "share_truncated_notice",
                },
            )
    return snapshot_data


def _normalize_snapshot_payload(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return [payload]
    if not isinstance(payload, str):
        return []

    raw = payload.strip()
    if not raw:
        return []

    try:
        first = json.loads(raw)
    except Exception:
        return []

    if isinstance(first, list):
        return first
    if isinstance(first, dict):
        return [first]
    if isinstance(first, str):
        try:
            second = json.loads(first)
            if isinstance(second, list):
                return second
            if isinstance(second, dict):
                return [second]
        except Exception:
            return []
    return []


def _infer_owner_user_id(session_id: str) -> str:
    try:
        res = (
            supabase.table("history")
            .select("user_id")
            .eq("session_id", str(session_id))
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if getattr(res, "data", None):
            owner = str(res.data[0].get("user_id") or "").strip()
            if owner and owner.lower() != "anonymous":
                return owner
    except Exception:
        pass
    return ""


def _fetch_share_history_rows(
    owner_user_id: str,
    session_id: str,
    *,
    limit: int,
    desc: bool,
) -> List[Dict[str, Any]]:
    query = (
        supabase.table("history")
        .select("role, content, created_at, func_type")
        .eq("session_id", str(session_id))
    )
    normalized_owner = str(owner_user_id or "").strip()
    if normalized_owner and normalized_owner.lower() != "anonymous":
        query = query.eq("user_id", normalized_owner)
    response = query.order("created_at", desc=desc).limit(limit).execute()
    rows = response.data or []
    if desc:
        rows = list(reversed(rows))
    return rows


def _count_history_for_share(owner_user_id: str, session_id: str) -> int:
    try:
        query = (
            supabase.table("history")
            .select("id", count="exact", head=True)
            .eq("session_id", str(session_id))
        )
        normalized_owner = str(owner_user_id or "").strip()
        if normalized_owner and normalized_owner.lower() != "anonymous":
            query = query.eq("user_id", normalized_owner)
        response = query.execute()
        return int(getattr(response, "count", 0) or 0)
    except Exception:
        return 0


def _merge_share_history_rows(head_rows: List[Dict[str, Any]], tail_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen = set()
    for item in (head_rows or []) + (tail_rows or []):
        dedup_key = (
            str(item.get("created_at") or ""),
            str(item.get("role") or ""),
            str(item.get("func_type") or ""),
            str(item.get("content") or "")[:128],
        )
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        merged.append(item)
    return merged


def _load_history_for_share(owner_user_id: str, session_id: str) -> tuple[List[Dict[str, Any]], int]:
    try:
        total_count = _count_history_for_share(owner_user_id, session_id)
        head_rows = _fetch_share_history_rows(
            owner_user_id,
            session_id,
            limit=SHARE_SNAPSHOT_HEAD_MESSAGES,
            desc=False,
        )
        if total_count <= SHARE_SNAPSHOT_HEAD_MESSAGES:
            return head_rows, total_count or len(head_rows)

        tail_rows = _fetch_share_history_rows(
            owner_user_id,
            session_id,
            limit=SHARE_SNAPSHOT_TAIL_MESSAGES,
            desc=True,
        )
        merged = _merge_share_history_rows(head_rows, tail_rows)
        return merged, total_count or len(merged)
    except Exception:
        pass

    rows = get_history_limited(str(owner_user_id), str(session_id), limit=SHARE_SNAPSHOT_TAIL_MESSAGES) or []
    if rows:
        return rows, len(rows)

    rows = get_history(str(owner_user_id), str(session_id)) or []
    return rows, len(rows)


def create_share_link(user_id: str, session_id: str, title: Optional[str] = None, days: int = 7):
    if not _ensure_share_schema():
        return None

    try:
        token = generate_token()
        token_hash = hash_token(token)
        ttl_days = _normalize_days(days)
        expires_at = None
        if ttl_days > 0:
            expires_at = (datetime.now(timezone.utc) + timedelta(days=ttl_days)).isoformat()

        normalized_title = (title or "").strip()[:200] or "Untitled Session"
        owner_user_id = str(user_id or "").strip()
        if not owner_user_id or owner_user_id.lower() == "anonymous":
            owner_user_id = _infer_owner_user_id(str(session_id)) or owner_user_id or "anonymous"

        raw_history, total_history_count = _load_history_for_share(owner_user_id, str(session_id))
        snapshot_data = _build_snapshot(raw_history, total_count=total_history_count)

        link_payload = {
            "session_id": str(session_id),
            "owner_user_id": owner_user_id,
            "token_hash": token_hash,
            "title": normalized_title,
            "expires_at": expires_at,
        }
        link_res = supabase.table("share_links").insert(link_payload).execute()

        share_id = None
        if getattr(link_res, "data", None):
            share_id = link_res.data[0].get("id")
        if not share_id:
            lookup = (
                supabase.table("share_links")
                .select("id")
                .eq("token_hash", token_hash)
                .order("id", desc=True)
                .limit(1)
                .execute()
            )
            if getattr(lookup, "data", None):
                share_id = lookup.data[0].get("id")
        if not share_id:
            raise RuntimeError("Failed to resolve created share link id")

        try:
            supabase.table("share_snapshots").insert(
                {"share_link_id": share_id, "payload": snapshot_data}
            ).execute()
        except Exception:
            supabase.table("share_links").delete().eq("id", share_id).execute()
            raise

        _set_last_error("")
        return token
    except Exception as exc:
        _set_last_error(str(exc))
        print(f"Error creating share link: {exc}")
        return None


def get_shared_content(token: str):
    if not _ensure_share_schema():
        return {"error": get_last_error() or "Share schema initialization failed"}

    try:
        token_hash = hash_token(token)
        res = (
            supabase.table("share_links")
            .select("*")
            .eq("token_hash", token_hash)
            .eq("revoked", False)
            .limit(1)
            .execute()
        )
        if not res.data:
            return {"error": "Invalid or revoked link"}

        link_info = res.data[0]
        expires_at = link_info.get("expires_at")
        if expires_at:
            expire_time = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > expire_time:
                return {"error": "Link expired"}

        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            supabase.table("share_links").update({"last_access_at": now_iso}).eq(
                "id", link_info["id"]
            ).execute()
        except Exception:
            pass

        snap_res = (
            supabase.table("share_snapshots")
            .select("payload, created_at")
            .eq("share_link_id", link_info["id"])
            .order("id", desc=True)
            .limit(1)
            .execute()
        )
        if not snap_res.data:
            return {"error": "Snapshot not found"}

        snapshot = snap_res.data[0]
        payload = snapshot.get("payload", [])
        messages = _normalize_snapshot_payload(payload)

        _set_last_error("")
        return {
            "title": link_info.get("title"),
            "created_at": link_info.get("created_at"),
            "snapshot_at": snapshot.get("created_at"),
            "owner_id": link_info.get("owner_user_id"),
            "messages": messages,
        }
    except Exception as exc:
        _set_last_error(str(exc))
        print(f"Error fetching shared content: {exc}")
        return {"error": "Internal server error"}


def revoke_share_link(user_id: str, share_id: int):
    if not _ensure_share_schema():
        return False
    try:
        (
            supabase.table("share_links")
            .update({"revoked": True})
            .eq("id", share_id)
            .eq("owner_user_id", str(user_id))
            .execute()
        )
        _set_last_error("")
        return True
    except Exception as exc:
        _set_last_error(str(exc))
        print(f"Error revoking share: {exc}")
        return False
