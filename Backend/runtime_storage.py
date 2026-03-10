from __future__ import annotations

import os
import shutil
import threading
import time
from pathlib import Path
from typing import Iterable


BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
RUNTIME_ROOT = Path(os.getenv("APP_RUNTIME_ROOT", str(PROJECT_ROOT / ".runtime"))).resolve()
RUNTIME_STATIC_ROOT = Path(os.getenv("APP_RUNTIME_STATIC_ROOT", str(RUNTIME_ROOT / "static"))).resolve()
RUNTIME_OCR_ROOT = Path(os.getenv("APP_RUNTIME_OCR_ROOT", str(RUNTIME_STATIC_ROOT / "ocr"))).resolve()
RUNTIME_TEMP_AUDIO_ROOT = Path(
    os.getenv("APP_RUNTIME_TEMP_AUDIO_ROOT", str(RUNTIME_STATIC_ROOT / "temp_audio"))
).resolve()
RUNTIME_AUDIT_ROOT = Path(os.getenv("APP_RUNTIME_AUDIT_ROOT", str(RUNTIME_ROOT / "audit"))).resolve()
RUNTIME_CACHE_ROOT = Path(os.getenv("APP_RUNTIME_CACHE_ROOT", str(RUNTIME_ROOT / "cache"))).resolve()
RUNTIME_PRESENTATION_ROOT = Path(
    os.getenv("APP_RUNTIME_PRESENTATION_ROOT", str(RUNTIME_ROOT / "presentation"))
).resolve()

SMS_TOKEN_CACHE_FILE = Path(
    os.getenv("APP_SMS_TOKEN_CACHE_FILE", str(RUNTIME_CACHE_ROOT / "sms_token_cache.json"))
).resolve()
PRESENTATION_TEMPLATE_REGISTRY_FILE = Path(
    os.getenv(
        "PRESENTON_TEMPLATE_REGISTRY_FILE",
        str(RUNTIME_PRESENTATION_ROOT / "presentation_templates.json"),
    )
).resolve()

RUNTIME_CLEANUP_INTERVAL_SECONDS = max(
    300,
    int(os.getenv("APP_RUNTIME_CLEANUP_INTERVAL_SECONDS", "3600")),
)
OCR_RUNTIME_TTL_SECONDS = max(
    3600,
    int(os.getenv("APP_RUNTIME_OCR_TTL_SECONDS", str(14 * 24 * 3600))),
)
TEMP_AUDIO_RUNTIME_TTL_SECONDS = max(
    3600,
    int(os.getenv("APP_RUNTIME_TEMP_AUDIO_TTL_SECONDS", str(7 * 24 * 3600))),
)
AUDIT_RUNTIME_TTL_SECONDS = max(
    3600,
    int(os.getenv("APP_RUNTIME_AUDIT_TTL_SECONDS", str(30 * 24 * 3600))),
)
CACHE_RUNTIME_TTL_SECONDS = max(
    3600,
    int(os.getenv("APP_RUNTIME_CACHE_TTL_SECONDS", str(30 * 24 * 3600))),
)
ROOT_TEMP_ARTIFACT_TTL_SECONDS = max(
    3600,
    int(os.getenv("APP_RUNTIME_ROOT_TEMP_TTL_SECONDS", str(3 * 24 * 3600))),
)

LEGACY_STATIC_ROOT = BACKEND_DIR / "static"
LEGACY_OCR_ROOT = LEGACY_STATIC_ROOT / "ocr"
LEGACY_TEMP_AUDIO_ROOT = LEGACY_STATIC_ROOT / "temp_audio"
LEGACY_AUDIT_ROOT = BACKEND_DIR / "storage" / "audit"
LEGACY_SMS_CACHE_FILES = (
    BACKEND_DIR / ".sms_token_cache.json",
    PROJECT_ROOT / ".sms_token_cache.json",
)
LEGACY_PRESENTATION_TEMPLATE_REGISTRY_FILE = BACKEND_DIR / "data" / "presentation_templates.json"

ROOT_TEMP_ARTIFACT_PREFIXES = (".tmp_", "tmp_", "_tmp_")
ROOT_TEMP_ARTIFACT_EXACT_NAMES = {
    "tmp_next_chunks",
    "test-results",
}

_RUNTIME_INIT_LOCK = threading.Lock()
_RUNTIME_INIT_DONE = False
_RUNTIME_MIGRATION_LOCK = threading.Lock()
_RUNTIME_MIGRATION_DONE = False
_RUNTIME_CLEANUP_THREAD_LOCK = threading.Lock()
_RUNTIME_CLEANUP_THREAD_STARTED = False


def _mkdir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_runtime_layout() -> None:
    global _RUNTIME_INIT_DONE
    if _RUNTIME_INIT_DONE:
        return
    with _RUNTIME_INIT_LOCK:
        if _RUNTIME_INIT_DONE:
            return
        for path in (
            RUNTIME_ROOT,
            RUNTIME_STATIC_ROOT,
            RUNTIME_OCR_ROOT,
            RUNTIME_TEMP_AUDIO_ROOT,
            RUNTIME_AUDIT_ROOT,
            RUNTIME_CACHE_ROOT,
            RUNTIME_PRESENTATION_ROOT,
        ):
            _mkdir(path)
        _RUNTIME_INIT_DONE = True


def _iter_existing(paths: Iterable[Path]) -> Iterable[Path]:
    for path in paths:
        try:
            if path.exists():
                yield path
        except Exception:
            continue


def _move_path(source: Path, target: Path) -> None:
    if not source.exists():
        return
    _mkdir(target.parent)
    if source.is_dir():
        _mkdir(target)
        for child in list(source.iterdir()):
            _move_path(child, target / child.name)
        try:
            source.rmdir()
        except OSError:
            pass
        return

    if target.exists():
        try:
            source.unlink()
        except OSError:
            pass
        return

    shutil.move(str(source), str(target))


def migrate_legacy_runtime_files() -> None:
    global _RUNTIME_MIGRATION_DONE
    ensure_runtime_layout()
    if _RUNTIME_MIGRATION_DONE:
        return
    with _RUNTIME_MIGRATION_LOCK:
        if _RUNTIME_MIGRATION_DONE:
            return
        _move_path(LEGACY_OCR_ROOT, RUNTIME_OCR_ROOT)
        _move_path(LEGACY_TEMP_AUDIO_ROOT, RUNTIME_TEMP_AUDIO_ROOT)
        _move_path(LEGACY_AUDIT_ROOT, RUNTIME_AUDIT_ROOT)
        for legacy_file in _iter_existing(LEGACY_SMS_CACHE_FILES):
            _move_path(legacy_file, SMS_TOKEN_CACHE_FILE)
        if LEGACY_PRESENTATION_TEMPLATE_REGISTRY_FILE.exists():
            _move_path(LEGACY_PRESENTATION_TEMPLATE_REGISTRY_FILE, PRESENTATION_TEMPLATE_REGISTRY_FILE)
            try:
                LEGACY_PRESENTATION_TEMPLATE_REGISTRY_FILE.parent.rmdir()
            except OSError:
                pass
        _RUNTIME_MIGRATION_DONE = True


def build_static_api_url(*parts: str) -> str:
    normalized = [str(part or "").strip().replace("\\", "/").strip("/") for part in parts if str(part or "").strip()]
    if not normalized:
        return "/api/static"
    return "/api/static/" + "/".join(normalized)


def _safe_unlink(path: Path) -> None:
    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.exists():
            path.unlink()
    except Exception:
        pass


def _cleanup_expired_tree(root: Path, ttl_seconds: int, *, recursive: bool = True) -> int:
    if ttl_seconds <= 0 or not root.exists():
        return 0
    now = time.time()
    removed = 0
    candidates = list(root.rglob("*")) if recursive else list(root.iterdir())
    for path in sorted(candidates, key=lambda item: len(item.parts), reverse=True):
        try:
            if not path.exists():
                continue
            age = now - path.stat().st_mtime
            if age < ttl_seconds:
                continue
            if path.is_dir():
                try:
                    next(path.iterdir())
                    continue
                except StopIteration:
                    path.rmdir()
                    removed += 1
                    continue
            path.unlink()
            removed += 1
        except Exception:
            continue
    return removed


def cleanup_project_temp_artifacts(ttl_seconds: int = ROOT_TEMP_ARTIFACT_TTL_SECONDS) -> int:
    if ttl_seconds <= 0:
        return 0
    now = time.time()
    removed = 0
    for path in PROJECT_ROOT.iterdir():
        name = path.name
        is_temp_name = name in ROOT_TEMP_ARTIFACT_EXACT_NAMES or any(
            name.startswith(prefix) for prefix in ROOT_TEMP_ARTIFACT_PREFIXES
        )
        if not is_temp_name:
            continue
        try:
            age = now - path.stat().st_mtime
        except Exception:
            continue
        if age < ttl_seconds:
            continue
        _safe_unlink(path)
        removed += 1
    return removed


def cleanup_runtime_files() -> int:
    ensure_runtime_layout()
    removed = 0
    removed += _cleanup_expired_tree(RUNTIME_OCR_ROOT, OCR_RUNTIME_TTL_SECONDS)
    removed += _cleanup_expired_tree(RUNTIME_TEMP_AUDIO_ROOT, TEMP_AUDIO_RUNTIME_TTL_SECONDS)
    removed += _cleanup_expired_tree(RUNTIME_AUDIT_ROOT, AUDIT_RUNTIME_TTL_SECONDS)
    removed += _cleanup_expired_tree(RUNTIME_CACHE_ROOT, CACHE_RUNTIME_TTL_SECONDS)
    removed += cleanup_project_temp_artifacts()
    return removed


def start_runtime_cleanup_loop() -> None:
    global _RUNTIME_CLEANUP_THREAD_STARTED
    ensure_runtime_layout()
    with _RUNTIME_CLEANUP_THREAD_LOCK:
        if _RUNTIME_CLEANUP_THREAD_STARTED:
            return
        _RUNTIME_CLEANUP_THREAD_STARTED = True

    def _runner() -> None:
        while True:
            try:
                cleanup_runtime_files()
            except Exception:
                pass
            time.sleep(RUNTIME_CLEANUP_INTERVAL_SECONDS)

    thread = threading.Thread(
        target=_runner,
        name="runtime-cleanup",
        daemon=True,
    )
    thread.start()
