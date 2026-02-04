import time
import uuid
import asyncio
from typing import Dict, Any

# 引入 Supabase 客户端
from supabase_client import require_supabase, supabase
# 引入百度转写逻辑
from voice_manager import transcribe_audio_via_url, get_format_from_filename

# 配置
STORAGE_BUCKET = 'voice_uploads'

# 任务状态存储
TRANSCRIPTION_TASKS: Dict[str, Dict[str, Any]] = {}


# ------------------------------------------------------------------------
# 🚀 极速模式：核心处理逻辑
# ------------------------------------------------------------------------
async def run_transcription_pipeline(task_id: str, remote_file_path: str, original_filename: str):
    """
    全链路不落地文件：
    1. 后端根据 Supabase 路径生成 Signed URL
    2. 后端把 URL 扔给百度 ASR
    3. 轮询等待结果
    """
    print(f"🎬 [极速转写] Task ID: {task_id} | 文件: {remote_file_path}")

    try:
        supabase_client = require_supabase()

        # 1. 生成 Signed URL (有效期设置为 3 小时)
        print(f"🔗 [Supabase] 正在生成访问链接...")
        signed_url_resp = supabase_client.storage.from_(STORAGE_BUCKET).create_signed_url(remote_file_path, 3600 * 3)

        # 兼容不同版本 supabase-py 的返回值
        if isinstance(signed_url_resp, dict) and 'signedURL' in signed_url_resp:
            audio_url = signed_url_resp['signedURL']
        elif isinstance(signed_url_resp, str):
            audio_url = signed_url_resp
        else:
            audio_url = str(signed_url_resp)

        print(f"🚀 [Baidu ASR] 提交 URL: {audio_url[:80]}...")

        # 2. 提交给百度 (直接透传 URL)
        file_fmt = get_format_from_filename(original_filename)
        result_text = await asyncio.to_thread(transcribe_audio_via_url, audio_url, format=file_fmt)

        # 3. 更新状态
        if "❌" in result_text and "失败" in result_text:
            TRANSCRIPTION_TASKS[task_id]["status"] = "failed"
            TRANSCRIPTION_TASKS[task_id]["result"] = result_text
            print(f"❌ [任务失败] {result_text}")
        else:
            TRANSCRIPTION_TASKS[task_id]["status"] = "completed"
            TRANSCRIPTION_TASKS[task_id]["result"] = result_text
            print(f"✅ [任务完成] 转写成功")

    except Exception as e:
        print(f"❌ [致命错误] Pipeline 异常: {e}")
        TRANSCRIPTION_TASKS[task_id]["status"] = "failed"
        TRANSCRIPTION_TASKS[task_id]["result"] = f"处理异常: {str(e)}"


# ------------------------------------------------------------------------
# 🔌 对外接口 (API 调用入口)
# ------------------------------------------------------------------------
async def submit_supabase_task(file_path: str, original_name: str) -> str:
    """
    接收前端传来的 Supabase 路径 (如 "temp/123.wav")，启动后台任务
    """
    task_id = str(uuid.uuid4())

    TRANSCRIPTION_TASKS[task_id] = {
        "status": "processing",
        "created_at": time.time(),
        "filename": original_name,
        "file_path": file_path  # ✨ 记录路径以便后续查询
    }

    asyncio.create_task(run_transcription_pipeline(task_id, file_path, original_name))
    return task_id


def get_task_result(task_id: str):
    task = TRANSCRIPTION_TASKS.get(task_id)
    if not task: return {"status": "not_found"}
    return task


# ✨ 新增：上传文件流到 Supabase (用于处理直接上传的文件)
async def upload_bytes_to_supabase(file_bytes: bytes, filename: str, content_type: str) -> str:
    try:
        # 生成唯一路径，避免覆盖
        unique_name = f"{uuid.uuid4()}_{filename}"
        path = f"uploads/{unique_name}"

        supabase.storage.from_(STORAGE_BUCKET).upload(
            path=path,
            file=file_bytes,
            file_options={"content-type": content_type}
        )
        return path
    except Exception as e:
        print(f"❌ Upload to Supabase failed: {e}")
        return None


# ✨ 新增：获取文件的播放链接 (Signed URL)
def get_file_signed_url(file_path: str, expire=3600):
    try:
        if not file_path: return None
        res = supabase.storage.from_(STORAGE_BUCKET).create_signed_url(file_path, expire)
        # 兼容不同版本返回值
        if isinstance(res, dict) and 'signedURL' in res:
            return res['signedURL']
        elif isinstance(res, str):
            return res
        return str(res)
    except Exception as e:
        print(f"❌ Get Signed URL failed: {e}")
        return None


# 修改：处理直接上传的文件任务
async def submit_file_task(file) -> str:
    # 1. 先读取文件内容并上传到 Supabase
    content = await file.read()
    path = await upload_bytes_to_supabase(content, file.filename, file.content_type)

    if not path:
        raise Exception("Failed to upload file to storage")

    # 2. 提交转写任务
    return await submit_supabase_task(path, file.filename)