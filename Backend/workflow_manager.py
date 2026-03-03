from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from sqlalchemy import text

from supabase_client import engine, require_supabase

try:
    from database_manager import db_manager, DB_NAME as DEFAULT_DB_NAME
except Exception:
    db_manager = None
    DEFAULT_DB_NAME = "postgres"

try:
    from deepseek_llm import ask_llm
except Exception:
    ask_llm = None

try:
    from report_email_manager import generate_report_outline
except Exception:
    generate_report_outline = None

try:
    import share_manager
except Exception:
    share_manager = None

try:
    from history_manager import add_history_to_supabase
except Exception:
    add_history_to_supabase = None


SCENARIO_MONTHLY = "monthly_operating_analysis"

STEP_DB_QUERY = "db_query"
STEP_CONCLUSION = "generate_conclusion"
STEP_REPORT = "generate_report"
STEP_CONFIRM = "manual_confirm"
STEP_SHARE = "share_result"

STEP_DEFS = [
    {"key": STEP_DB_QUERY, "name": "查询数据库并提取关键事实", "order": 1},
    {"key": STEP_CONCLUSION, "name": "生成经营结论", "order": 2},
    {"key": STEP_REPORT, "name": "生成报告草案", "order": 3},
    {"key": STEP_CONFIRM, "name": "人工确认", "order": 4},
    {"key": STEP_SHARE, "name": "生成分享链接", "order": 5},
]

FINAL_STATUSES = {"done", "failed", "cancelled"}
STEP_RUNNING_STATUSES = {"pending", "running", "blocked"}

_SCHEMA_READY = False
_SCHEMA_LOCK = threading.Lock()
_RUN_LOCK = threading.Lock()
_RUNNING_JOBS: set[str] = set()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _json_value(value: Any) -> Any:
    if value is None:
        return {}
    if isinstance(value, (dict, list, str, int, float, bool)):
        return value
    return str(value)


def _append_history(user_id: str, session_id: str, role: str, content: str, func_type: str = "workflow") -> None:
    if not content:
        return
    try:
        if add_history_to_supabase:
            add_history_to_supabase(user_id, session_id, func_type, role, content)
            return
        sb = require_supabase()
        sb.table("history").insert(
            {
                "user_id": str(user_id),
                "session_id": str(session_id),
                "func_type": func_type,
                "role": role,
                "content": content,
            }
        ).execute()
    except Exception as e:
        print(f"[Workflow] history append failed: {e}")


def _ensure_schema() -> bool:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return True
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return True
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        create table if not exists public.workflow_jobs (
                          id bigint primary key generated always as identity,
                          job_id text not null unique,
                          user_id text not null,
                          session_id text not null,
                          name text not null,
                          scenario text not null,
                          status text not null default 'pending',
                          current_step integer not null default 0,
                          model_backend text not null default 'local',
                          requires_confirmation boolean not null default false,
                          confirmed_at timestamptz,
                          confirmed_by text,
                          input_json jsonb not null default '{}'::jsonb,
                          result_json jsonb not null default '{}'::jsonb,
                          error text,
                          started_at timestamptz,
                          finished_at timestamptz,
                          created_at timestamptz not null default now(),
                          updated_at timestamptz not null default now()
                        );
                        """
                    )
                )
                conn.execute(
                    text(
                        """
                        create table if not exists public.workflow_steps (
                          id bigint primary key generated always as identity,
                          job_id text not null references public.workflow_jobs(job_id) on delete cascade,
                          step_key text not null,
                          step_name text not null,
                          step_order integer not null,
                          status text not null default 'pending',
                          needs_confirmation boolean not null default false,
                          confirmed_at timestamptz,
                          confirmed_by text,
                          input_json jsonb not null default '{}'::jsonb,
                          output_json jsonb not null default '{}'::jsonb,
                          artifact_url text,
                          error text,
                          started_at timestamptz,
                          finished_at timestamptz,
                          duration_ms integer,
                          created_at timestamptz not null default now(),
                          updated_at timestamptz not null default now(),
                          unique (job_id, step_key)
                        );
                        """
                    )
                )
                conn.execute(
                    text(
                        "create index if not exists workflow_jobs_user_idx on public.workflow_jobs(user_id, created_at desc)"
                    )
                )
                conn.execute(
                    text(
                        "create index if not exists workflow_jobs_status_idx on public.workflow_jobs(status, created_at desc)"
                    )
                )
                conn.execute(
                    text(
                        "create index if not exists workflow_steps_job_idx on public.workflow_steps(job_id, step_order)"
                    )
                )
            _SCHEMA_READY = True
            return True
        except Exception as e:
            print(f"[Workflow] schema init failed: {e}")
            return False


def _update_job(job_id: str, payload: Dict[str, Any]) -> None:
    if not payload:
        return
    payload = {**payload, "updated_at": _now_iso()}
    sb = require_supabase()
    sb.table("workflow_jobs").update(payload).eq("job_id", job_id).execute()


def _update_step(
    job_id: str,
    step_key: str,
    payload: Dict[str, Any],
) -> None:
    if not payload:
        return
    payload = {**payload, "updated_at": _now_iso()}
    sb = require_supabase()
    sb.table("workflow_steps").update(payload).eq("job_id", job_id).eq("step_key", step_key).execute()


def _mark_step_running(job_id: str, step_key: str, step_order: int, input_json: Optional[Dict[str, Any]] = None) -> float:
    started_at = _now_iso()
    _update_step(
        job_id,
        step_key,
        {
            "status": "running",
            "started_at": started_at,
            "finished_at": None,
            "duration_ms": None,
            "error": None,
            "input_json": _json_value(input_json or {}),
        },
    )
    _update_job(job_id, {"status": "running", "current_step": step_order, "error": None})
    return time.time()


def _mark_step_done(
    job_id: str,
    step_key: str,
    step_order: int,
    started_ts: float,
    output_json: Optional[Dict[str, Any]] = None,
    artifact_url: Optional[str] = None,
) -> None:
    finished_at = _now_iso()
    duration_ms = int(max(0, (time.time() - started_ts) * 1000))
    _update_step(
        job_id,
        step_key,
        {
            "status": "done",
            "finished_at": finished_at,
            "duration_ms": duration_ms,
            "output_json": _json_value(output_json or {}),
            "artifact_url": artifact_url,
            "error": None,
        },
    )
    _update_job(job_id, {"current_step": step_order})


def _mark_step_blocked(
    job_id: str,
    step_key: str,
    step_order: int,
    started_ts: float,
    output_json: Optional[Dict[str, Any]] = None,
) -> None:
    finished_at = _now_iso()
    duration_ms = int(max(0, (time.time() - started_ts) * 1000))
    _update_step(
        job_id,
        step_key,
        {
            "status": "blocked",
            "needs_confirmation": True,
            "finished_at": finished_at,
            "duration_ms": duration_ms,
            "output_json": _json_value(output_json or {}),
            "error": None,
        },
    )
    _update_job(
        job_id,
        {
            "status": "blocked",
            "current_step": step_order,
            "requires_confirmation": True,
            "error": None,
        },
    )


def _mark_job_failed(job_id: str, step_key: str, step_order: int, started_ts: float, error: str) -> None:
    finished_at = _now_iso()
    duration_ms = int(max(0, (time.time() - started_ts) * 1000))
    _update_step(
        job_id,
        step_key,
        {
            "status": "failed",
            "finished_at": finished_at,
            "duration_ms": duration_ms,
            "error": error[:1000],
        },
    )
    _update_job(
        job_id,
        {
            "status": "failed",
            "current_step": step_order,
            "error": error[:1000],
            "finished_at": finished_at,
            "requires_confirmation": False,
        },
    )


def _fetch_job(job_id: str) -> Optional[Dict[str, Any]]:
    sb = require_supabase()
    res = sb.table("workflow_jobs").select("*").eq("job_id", job_id).limit(1).execute()
    rows = res.data or []
    if not rows:
        return None
    return rows[0]


def _fetch_steps(job_id: str) -> List[Dict[str, Any]]:
    sb = require_supabase()
    res = sb.table("workflow_steps").select("*").eq("job_id", job_id).order("step_order").execute()
    return res.data or []


def _merge_job_payload(job: Dict[str, Any], steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "job_id": job.get("job_id"),
        "user_id": job.get("user_id"),
        "session_id": job.get("session_id"),
        "name": job.get("name"),
        "scenario": job.get("scenario"),
        "status": job.get("status"),
        "current_step": job.get("current_step"),
        "requires_confirmation": bool(job.get("requires_confirmation")),
        "model_backend": job.get("model_backend"),
        "input_json": job.get("input_json") or {},
        "result_json": job.get("result_json") or {},
        "error": job.get("error"),
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "steps": steps,
    }


def get_workflow_job(job_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if not _ensure_schema():
        return None
    job = _fetch_job(job_id)
    if not job:
        return None
    if user_id and str(job.get("user_id")) != str(user_id):
        return None
    steps = _fetch_steps(job_id)
    return _merge_job_payload(job, steps)


def list_workflow_jobs(user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    if not _ensure_schema():
        return []
    sb = require_supabase()
    res = (
        sb.table("workflow_jobs")
        .select("*")
        .eq("user_id", str(user_id))
        .order("created_at", desc=True)
        .limit(max(1, min(int(limit or 20), 100)))
        .execute()
    )
    jobs = res.data or []
    out: List[Dict[str, Any]] = []
    for job in jobs:
        out.append(
            {
                "job_id": job.get("job_id"),
                "session_id": job.get("session_id"),
                "name": job.get("name"),
                "scenario": job.get("scenario"),
                "status": job.get("status"),
                "current_step": job.get("current_step"),
                "requires_confirmation": bool(job.get("requires_confirmation")),
                "created_at": job.get("created_at"),
                "updated_at": job.get("updated_at"),
            }
        )
    return out


def _try_parse_json_block(raw_text: str) -> Any:
    if not raw_text:
        return raw_text
    text = str(raw_text).strip()
    if text.startswith("```"):
        text = text.replace("```json", "").replace("```", "").strip()
    if "{" not in text or "}" not in text:
        return raw_text
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return raw_text
    try:
        return json.loads(text[start : end + 1])
    except Exception:
        return raw_text


def _run_db_query_step(query: str, model_backend: str) -> Tuple[str, str]:
    if not db_manager:
        raise RuntimeError("Database manager unavailable")
    summary_parts: List[str] = []
    sql_text = ""
    stream = db_manager.query_fast(
        db_name=DEFAULT_DB_NAME,
        user_query=query,
        model_type=model_backend or "local",
    )
    for event in stream:
        if isinstance(event, dict):
            source = event.get("source") if event.get("type") == "source" else None
            if isinstance(source, dict) and source.get("type") == "sql":
                sql_text = str(source.get("sql") or "").strip()
            continue
        text_chunk = str(event or "")
        if text_chunk:
            summary_parts.append(text_chunk)
    summary_text = "".join(summary_parts).strip()
    if not summary_text:
        summary_text = "数据库查询已执行，但未生成可展示的总结。"
    return summary_text, sql_text


def _run_conclusion_step(query: str, db_summary: str, sql_text: str, model_backend: str) -> str:
    if not ask_llm:
        return db_summary
    prompt = (
        "你是企业经营分析助手。请基于给定数据库结果，产出管理层可读的结论。\n"
        "输出要求:\n"
        "1) 先给一句话总览结论。\n"
        "2) 给出 3-5 条关键发现。\n"
        "3) 给出 2-3 条可执行建议。\n"
        "4) 不要编造数据库未提供的数据。\n\n"
        f"用户任务: {query}\n"
        f"SQL: {sql_text or '（无）'}\n"
        f"数据库总结: {db_summary}\n"
    )
    result = ask_llm(prompt, model_type=model_backend or "local")
    cleaned = str(result or "").strip()
    return cleaned or db_summary


def _run_report_step(topic: str, key_points: str) -> Any:
    if not generate_report_outline:
        return key_points
    raw = generate_report_outline(
        topic=topic or "月度经营分析",
        scene="企业经营分析",
        audience="管理层",
        length="详细",
        key_points=key_points[:4000],
    )
    parsed = _try_parse_json_block(raw)
    return parsed


def _finalize_job_success(job_id: str, result_payload: Dict[str, Any]) -> None:
    _update_job(
        job_id,
        {
            "status": "done",
            "result_json": _json_value(result_payload),
            "requires_confirmation": False,
            "finished_at": _now_iso(),
            "error": None,
        },
    )


def _set_job_running_flag(job_id: str) -> bool:
    with _RUN_LOCK:
        if job_id in _RUNNING_JOBS:
            return False
        _RUNNING_JOBS.add(job_id)
        return True


def _clear_job_running_flag(job_id: str) -> None:
    with _RUN_LOCK:
        _RUNNING_JOBS.discard(job_id)


def _spawn_background(job_id: str, runner) -> None:
    if not _set_job_running_flag(job_id):
        return

    def _wrapped():
        try:
            runner()
        finally:
            _clear_job_running_flag(job_id)

    threading.Thread(target=_wrapped, daemon=True).start()


def _workflow_run_main(job_id: str) -> None:
    job = _fetch_job(job_id)
    if not job:
        return
    user_id = str(job.get("user_id") or "anonymous")
    session_id = str(job.get("session_id") or "")
    model_backend = str(job.get("model_backend") or "local")
    input_json = job.get("input_json") or {}
    query = str(input_json.get("query") or "请做本月经营分析并给出改进建议。")
    topic = str(input_json.get("topic") or "月度经营分析")

    _update_job(job_id, {"status": "running", "started_at": _now_iso(), "finished_at": None, "error": None})

    # Step 1: DB query
    step_started = _mark_step_running(job_id, STEP_DB_QUERY, 1, {"query": query})
    try:
        db_summary, sql_text = _run_db_query_step(query, model_backend)
        _mark_step_done(
            job_id,
            STEP_DB_QUERY,
            1,
            step_started,
            output_json={"summary": db_summary, "sql": sql_text},
        )
        _append_history(user_id, session_id, "assistant", f"[Workflow][数据库分析]\n{db_summary}")
    except Exception as e:
        _mark_job_failed(job_id, STEP_DB_QUERY, 1, step_started, str(e))
        return

    # Step 2: conclusion
    step_started = _mark_step_running(job_id, STEP_CONCLUSION, 2, {"query": query})
    try:
        conclusion = _run_conclusion_step(query, db_summary, sql_text, model_backend)
        _mark_step_done(job_id, STEP_CONCLUSION, 2, step_started, output_json={"conclusion": conclusion})
        _append_history(user_id, session_id, "assistant", f"[Workflow][经营结论]\n{conclusion}")
    except Exception as e:
        _mark_job_failed(job_id, STEP_CONCLUSION, 2, step_started, str(e))
        return

    # Step 3: report draft
    step_started = _mark_step_running(
        job_id,
        STEP_REPORT,
        3,
        {"topic": topic, "query": query},
    )
    try:
        report_draft = _run_report_step(topic, conclusion)
        _mark_step_done(job_id, STEP_REPORT, 3, step_started, output_json={"report_draft": report_draft})
        _append_history(user_id, session_id, "assistant", f"[Workflow][报告草案]\n{report_draft}")
    except Exception as e:
        _mark_job_failed(job_id, STEP_REPORT, 3, step_started, str(e))
        return

    # Step 4: manual confirmation (blocked)
    step_started = _mark_step_running(job_id, STEP_CONFIRM, 4, {"required": True})
    _mark_step_blocked(
        job_id,
        STEP_CONFIRM,
        4,
        step_started,
        output_json={"message": "请人工确认后继续生成分享链接。"},
    )
    _update_job(
        job_id,
        {
            "result_json": {
                "db_summary": db_summary,
                "sql": sql_text,
                "conclusion": conclusion,
                "report_draft": report_draft,
            }
        },
    )


def _workflow_run_share(job_id: str) -> None:
    job = _fetch_job(job_id)
    if not job:
        return
    user_id = str(job.get("user_id") or "anonymous")
    session_id = str(job.get("session_id") or "")
    input_json = job.get("input_json") or {}
    title = str(input_json.get("title") or "月度经营分析")

    step_started = _mark_step_running(job_id, STEP_SHARE, 5, {"title": title})
    try:
        if not share_manager:
            raise RuntimeError("Share manager unavailable")
        token = share_manager.create_share_link(user_id, session_id, f"{title} · 工作流", 7)
        if not token:
            raise RuntimeError(share_manager.get_last_error() or "Failed to create share link")
        share_url = f"/share/{token}"
        _mark_step_done(
            job_id,
            STEP_SHARE,
            5,
            step_started,
            output_json={"token": token, "share_url": share_url},
            artifact_url=share_url,
        )

        current_result = job.get("result_json") or {}
        if not isinstance(current_result, dict):
            current_result = {"raw": current_result}
        current_result["share"] = {"token": token, "share_url": share_url}
        _finalize_job_success(job_id, current_result)
        _append_history(user_id, session_id, "assistant", f"[Workflow][分享链接]\n{share_url}")
    except Exception as e:
        _mark_job_failed(job_id, STEP_SHARE, 5, step_started, str(e))


def start_monthly_analysis(
    user_id: str,
    session_id: Optional[str],
    query: str,
    model_backend: str = "local",
    topic: Optional[str] = None,
    title: Optional[str] = None,
) -> Dict[str, Any]:
    if not _ensure_schema():
        raise RuntimeError("Workflow schema not ready")
    sb = require_supabase()

    job_id = uuid4().hex
    resolved_session_id = (session_id or "").strip() or f"workflow-{job_id[:12]}"
    normalized_user_id = str(user_id or "anonymous").strip() or "anonymous"
    normalized_query = str(query or "").strip() or "请分析本月经营情况并给出改进建议。"
    normalized_topic = str(topic or "月度经营分析").strip() or "月度经营分析"
    normalized_title = str(title or normalized_topic).strip() or normalized_topic
    normalized_backend = str(model_backend or "local").strip().lower() or "local"

    _append_history(normalized_user_id, resolved_session_id, "user", f"[Workflow][任务发起]\n{normalized_query}")

    job_payload = {
        "job_id": job_id,
        "user_id": normalized_user_id,
        "session_id": resolved_session_id,
        "name": normalized_title,
        "scenario": SCENARIO_MONTHLY,
        "status": "pending",
        "current_step": 0,
        "model_backend": normalized_backend,
        "requires_confirmation": False,
        "input_json": {"query": normalized_query, "topic": normalized_topic, "title": normalized_title},
        "result_json": {},
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    sb.table("workflow_jobs").insert(job_payload).execute()

    step_rows = []
    now_iso = _now_iso()
    for step in STEP_DEFS:
        step_rows.append(
            {
                "job_id": job_id,
                "step_key": step["key"],
                "step_name": step["name"],
                "step_order": step["order"],
                "status": "pending",
                "needs_confirmation": step["key"] == STEP_CONFIRM,
                "input_json": {},
                "output_json": {},
                "created_at": now_iso,
                "updated_at": now_iso,
            }
        )
    sb.table("workflow_steps").insert(step_rows).execute()

    _spawn_background(job_id, lambda: _workflow_run_main(job_id))
    data = get_workflow_job(job_id, normalized_user_id) or {"job_id": job_id}
    return data


def confirm_workflow_job(job_id: str, user_id: str, action: str, comment: Optional[str] = None) -> Dict[str, Any]:
    if not _ensure_schema():
        raise RuntimeError("Workflow schema not ready")
    job = _fetch_job(job_id)
    if not job:
        raise RuntimeError("Workflow job not found")
    if str(job.get("user_id")) != str(user_id):
        raise RuntimeError("No permission to confirm this workflow")
    if str(job.get("status")) != "blocked":
        raise RuntimeError("Workflow is not waiting for confirmation")

    normalized_action = str(action or "").strip().lower()
    if normalized_action not in {"approved", "rejected"}:
        raise RuntimeError("Unsupported confirmation action")

    now_iso = _now_iso()
    step_update = {
        "confirmed_at": now_iso,
        "confirmed_by": str(user_id),
        "output_json": {"action": normalized_action, "comment": comment or ""},
    }
    if normalized_action == "approved":
        step_update["status"] = "done"
    else:
        step_update["status"] = "failed"
        step_update["error"] = "Rejected by reviewer"

    _update_step(job_id, STEP_CONFIRM, step_update)

    if normalized_action == "rejected":
        _update_job(
            job_id,
            {
                "status": "failed",
                "requires_confirmation": False,
                "confirmed_at": now_iso,
                "confirmed_by": str(user_id),
                "error": "Workflow rejected by reviewer",
                "finished_at": now_iso,
            },
        )
        return get_workflow_job(job_id, user_id) or {}

    _update_job(
        job_id,
        {
            "status": "running",
            "requires_confirmation": False,
            "confirmed_at": now_iso,
            "confirmed_by": str(user_id),
            "error": None,
        },
    )
    _spawn_background(job_id, lambda: _workflow_run_share(job_id))
    return get_workflow_job(job_id, user_id) or {}


def retry_workflow_job(job_id: str, user_id: str) -> Dict[str, Any]:
    if not _ensure_schema():
        raise RuntimeError("Workflow schema not ready")
    job = _fetch_job(job_id)
    if not job:
        raise RuntimeError("Workflow job not found")
    if str(job.get("user_id")) != str(user_id):
        raise RuntimeError("No permission to retry this workflow")
    if str(job.get("status")) not in {"failed", "cancelled"}:
        raise RuntimeError("Only failed/cancelled workflows can be retried")

    now_iso = _now_iso()
    sb = require_supabase()
    sb.table("workflow_steps").update(
        {
            "status": "pending",
            "error": None,
            "started_at": None,
            "finished_at": None,
            "duration_ms": None,
            "output_json": {},
            "artifact_url": None,
            "confirmed_at": None,
            "confirmed_by": None,
            "updated_at": now_iso,
        }
    ).eq("job_id", job_id).execute()

    _update_job(
        job_id,
        {
            "status": "pending",
            "current_step": 0,
            "requires_confirmation": False,
            "confirmed_at": None,
            "confirmed_by": None,
            "error": None,
            "finished_at": None,
            "result_json": {},
        },
    )
    _spawn_background(job_id, lambda: _workflow_run_main(job_id))
    return get_workflow_job(job_id, user_id) or {}

