from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict, Iterable, Tuple

from supabase import create_client


def _bucket_get(bucket: Any, key: str, default: Any = None) -> Any:
    if isinstance(bucket, dict):
        return bucket.get(key, default)
    return getattr(bucket, key, default)


def _iter_files(client: Any, bucket_name: str, prefix: str = "") -> Iterable[Tuple[str, Dict[str, Any]]]:
    offset = 0
    while True:
        entries = client.storage.from_(bucket_name).list(prefix, {"limit": 1000, "offset": offset})
        if not entries:
            break

        for entry in entries:
            name = entry.get("name")
            if not name:
                continue
            full_path = f"{prefix}/{name}" if prefix else name
            if entry.get("id") is None:
                yield from _iter_files(client, bucket_name, full_path)
            else:
                yield full_path, entry

        if len(entries) < 1000:
            break
        offset += 1000


def _ensure_bucket(local_client: Any, remote_bucket: Any, local_bucket_ids: set[str]) -> str:
    bucket_id = _bucket_get(remote_bucket, "id")
    bucket_name = _bucket_get(remote_bucket, "name") or bucket_id
    if not bucket_id:
        raise ValueError("remote bucket missing id")

    if bucket_id in local_bucket_ids:
        return bucket_id

    options: Dict[str, Any] = {}
    public = _bucket_get(remote_bucket, "public")
    if public is not None:
        options["public"] = bool(public)

    file_size_limit = _bucket_get(remote_bucket, "file_size_limit")
    if file_size_limit is not None:
        options["file_size_limit"] = file_size_limit

    allowed_mime_types = _bucket_get(remote_bucket, "allowed_mime_types")
    if allowed_mime_types:
        options["allowed_mime_types"] = allowed_mime_types

    if options:
        local_client.storage.create_bucket(bucket_id, bucket_name, options)
    else:
        local_client.storage.create_bucket(bucket_id, bucket_name)

    local_bucket_ids.add(bucket_id)
    return bucket_id


def migrate_storage(
    remote_url: str,
    remote_service_role_key: str,
    local_url: str,
    local_service_role_key: str,
) -> tuple[int, int, int]:
    remote = create_client(remote_url, remote_service_role_key)
    local = create_client(local_url, local_service_role_key)

    remote_buckets = remote.storage.list_buckets() or []
    local_buckets = local.storage.list_buckets() or []
    local_bucket_ids = {str(_bucket_get(b, "id")) for b in local_buckets if _bucket_get(b, "id")}

    bucket_count = 0
    file_count = 0
    failed_count = 0

    for remote_bucket in remote_buckets:
        bucket_id = _ensure_bucket(local, remote_bucket, local_bucket_ids)
        bucket_count += 1

        for file_path, file_info in _iter_files(remote, bucket_id):
            try:
                data = remote.storage.from_(bucket_id).download(file_path)
                metadata = file_info.get("metadata") or {}
                mimetype = metadata.get("mimetype")
                file_options: Dict[str, Any] = {"upsert": "true"}
                if mimetype:
                    file_options["content-type"] = mimetype
                local.storage.from_(bucket_id).upload(file_path, data, file_options)
                file_count += 1
            except Exception as exc:  # noqa: BLE001
                failed_count += 1
                print(f"[WARN] failed to sync {bucket_id}/{file_path}: {exc}")

    return bucket_count, file_count, failed_count


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Supabase Storage buckets/files from remote to local.")
    parser.add_argument("--remote-url", required=True)
    parser.add_argument("--remote-service-role-key", required=True)
    parser.add_argument("--local-url", default="http://127.0.0.1:54321")
    parser.add_argument(
        "--local-service-role-key",
        default=os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""),
    )
    args = parser.parse_args()

    if not args.local_service_role_key:
        print("[ERROR] missing local service role key. Set SUPABASE_SERVICE_ROLE_KEY or pass --local-service-role-key.")
        return 1

    try:
        buckets, files, failures = migrate_storage(
            remote_url=args.remote_url,
            remote_service_role_key=args.remote_service_role_key,
            local_url=args.local_url,
            local_service_role_key=args.local_service_role_key,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] storage migration failed: {exc}")
        return 1

    print(f"[OK] buckets synced: {buckets}")
    print(f"[OK] files synced: {files}")
    print(f"[OK] failed files: {failures}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
