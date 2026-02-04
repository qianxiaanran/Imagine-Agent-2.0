import secrets
import hashlib
import json
from datetime import datetime, timedelta, timezone
from supabase_client import supabase
from history_manager import get_history


def generate_token():
    """生成 32 字节的安全随机 Token"""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """对 Token 进行 SHA256 哈希"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_share_link(user_id: str, session_id: str, title: str = None, days: int = 7):
    """
    创建分享链接并生成快照
    """
    try:
        # 1. 生成 Token 和 Hash
        token = generate_token()
        token_hash = hash_token(token)

        # 2. 计算过期时间
        expires_at = None
        if days > 0:
            expires_at = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()

        # 3. 获取当前会话历史作为快照
        # 注意：这里我们直接从 history 表拉取数据，确保存入的是当时的静态副本
        raw_history = get_history(user_id, session_id)

        # 简化数据，只存需要的字段
        snapshot_data = []
        for msg in raw_history:
            # 过滤掉不需要的元数据，只保留角色和内容
            if msg.get('role') in ['user', 'assistant', 'system', 'context', 'meta']:
                snapshot_data.append({
                    "role": msg.get('role'),
                    "content": msg.get('content'),
                    "created_at": msg.get('created_at'),
                    "func_type": msg.get('func_type')  # 保留 func_type 以便前端正确渲染 (如 ocr_context)
                })

        # 4. 存入 share_links 表
        link_res = supabase.table("share_links").insert({
            "session_id": str(session_id),
            "owner_user_id": str(user_id),
            "token_hash": token_hash,
            "title": title or "未命名会话",
            "expires_at": expires_at
        }).execute()

        if not link_res.data:
            return None

        share_id = link_res.data[0]['id']

        # 5. 存入 share_snapshots 表
        supabase.table("share_snapshots").insert({
            "share_link_id": share_id,
            "payload": json.dumps(snapshot_data)  # 存为 JSON 字符串或直接 jsonb
        }).execute()

        return token
    except Exception as e:
        print(f"Error creating share link: {e}")
        return None


def get_shared_content(token: str):
    """
    获取分享的内容 (公开访问)
    """
    try:
        token_hash = hash_token(token)

        # 1. 查找链接信息
        # 校验 revoked = false 且 (expires_at > now OR expires_at is null)
        # 注意：Supabase JS 客户端比较时间可能比较麻烦，这里我们先取出记录在代码里校验时间，或者使用 Postgres 过滤器
        res = supabase.table("share_links") \
            .select("*") \
            .eq("token_hash", token_hash) \
            .eq("revoked", False) \
            .execute()

        if not res.data:
            return {"error": "Invalid or revoked link"}

        link_info = res.data[0]

        # 2. 校验过期时间
        if link_info['expires_at']:
            expire_time = datetime.fromisoformat(link_info['expires_at'].replace('Z', '+00:00'))
            if datetime.now(timezone.utc) > expire_time:
                return {"error": "Link expired"}

        # 3. 异步更新 last_access_at (不等待结果)
        # 实际生产中建议用后台任务，这里简化直接调用
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            supabase.table("share_links").update({"last_access_at": now_iso}).eq("id", link_info['id']).execute()
        except:
            pass

        # 4. 获取快照内容
        snap_res = supabase.table("share_snapshots") \
            .select("payload, created_at") \
            .eq("share_link_id", link_info['id']) \
            .execute()

        if not snap_res.data:
            return {"error": "Snapshot not found"}

        snapshot = snap_res.data[0]

        # 5. 返回组合数据
        # 解析 payload JSON 字符串
        try:
            messages = json.loads(snapshot['payload']) if isinstance(snapshot['payload'], str) else snapshot['payload']
        except:
            messages = []

        return {
            "title": link_info['title'],
            "created_at": link_info['created_at'],  # 分享创建时间
            "snapshot_at": snapshot['created_at'],  # 快照时间
            "owner_id": link_info['owner_user_id'],  # 仅用于前端显示是否是"我"的，不泄露敏感信息
            "messages": messages
        }

    except Exception as e:
        print(f"Error fetching shared content: {e}")
        return {"error": "Internal server error"}


def revoke_share_link(user_id: str, share_id: int):
    """撤销分享链接 (仅拥有者)"""
    try:
        supabase.table("share_links") \
            .update({"revoked": True}) \
            .eq("id", share_id) \
            .eq("owner_user_id", str(user_id)) \
            .execute()
        return True
    except Exception as e:
        print(f"Error revoking share: {e}")
        return False