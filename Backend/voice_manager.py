import requests
import base64
import datetime
import os
import json
import time
import io
import ipaddress
import math
import tempfile
from urllib.parse import urlparse
from config import BAIDU_API_KEY, BAIDU_SECRET_KEY

try:
    from pydub import AudioSegment
except Exception as e:  # pragma: no cover - optional runtime dependency guard
    AudioSegment = None
    PYDUB_IMPORT_ERROR = e
else:
    PYDUB_IMPORT_ERROR = None

# ----------------------------------------------------
# Baidu ASR Token 缓存
# ----------------------------------------------------
BAIDU_ASR_TOKEN = None
BAIDU_ASR_TOKEN_TIME = None
NON_PUBLIC_AUDIO_HOSTS = {"localhost", "::1", "0.0.0.0", "host.docker.internal"}
ASR_CHUNK_SECONDS = max(15, int(os.getenv("BAIDU_ASR_CHUNK_SECONDS", "50")))
ASR_CHUNK_MAX_COUNT = max(1, int(os.getenv("BAIDU_ASR_MAX_CHUNKS", "180")))


def get_baidu_token():
    """
    使用 AK，SK 生成鉴权签名（Access Token）
    :return: access_token，或是None(如果错误)
    """
    global BAIDU_ASR_TOKEN, BAIDU_ASR_TOKEN_TIME

    # 有缓存且未过期（28 天内）
    if BAIDU_ASR_TOKEN and BAIDU_ASR_TOKEN_TIME:
        if (datetime.datetime.now() - BAIDU_ASR_TOKEN_TIME).days < 28:
            return BAIDU_ASR_TOKEN

    url = "https://aip.baidubce.com/oauth/2.0/token"
    params = {
        "grant_type": "client_credentials",
        "client_id": BAIDU_API_KEY,
        "client_secret": BAIDU_SECRET_KEY
    }

    try:
        resp = requests.post(url, params=params, timeout=5).json()
        token = resp.get("access_token")
        if token:
            BAIDU_ASR_TOKEN = token
            BAIDU_ASR_TOKEN_TIME = datetime.datetime.now()
        else:
            print(f"❌ [Baidu Auth Error] Token获取失败: {resp}")
        return str(token)
    except Exception as e:
        print(f"❌ [Baidu Network Error] Token请求异常: {e}")
        return None


def get_format_from_filename(filename: str) -> str:
    """根据文件名推断百度ASR支持的格式"""
    if not filename:
        return "wav"
    ext = filename.lower().split('.')[-1]
    # 百度音频文件转写支持: mp3, wav, pcm, m4a, amr
    if ext in ["m4a", "aac"]:
        return "m4a"
    if ext in ["mp3"]:
        return "mp3"
    if ext in ["amr"]:
        return "amr"
    if ext in ["pcm"]:
        return "pcm"
    return "wav"


def is_public_audio_url(speech_url: str) -> bool:
    """百度长语音转写要求传入公网可访问的 HTTP(S) 音频 URL。"""
    raw = str(speech_url or "").strip()
    if not raw:
        return False

    try:
        parsed = urlparse(raw)
    except Exception:
        return False

    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False

    host = parsed.hostname.strip().lower()
    if not host:
        return False
    if host in NON_PUBLIC_AUDIO_HOSTS or host.endswith(".local"):
        return False
    if host.startswith("127."):
        return False

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True

    return not (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def should_fallback_to_chunked_transcription(error_text: str) -> bool:
    msg = str(error_text or "").strip().lower()
    if not msg:
        return True

    hard_fail_markers = ("token", "access token", "oauth", "network", "timeout", "超时")
    if any(marker in msg for marker in hard_fail_markers):
        return False

    soft_fail_markers = (
        "speech url",
        "url format",
        "download",
        "格式",
        "format",
        "unsupported",
        "不支持",
    )
    return any(marker in msg for marker in soft_fail_markers)


# ----------------------------------------------------
# 长语音/录音文件转写 (异步 API)
# 文档: https://ai.baidu.com/ai-doc/SPEECH/
# ----------------------------------------------------

def create_transcription_task(speech_url: str, format: str = "wav", pid: int = 80001, rate: int = 16000):
    """
    步骤1: 创建音频转写任务
    :param speech_url: 公网可访问的音频URL (百度云BOS或自有服务器)
    :param format: 音频格式 ["mp3", "wav", "pcm", "m4a", "amr"]
    :param pid: 语言模型 (80001: 中文极速版, 1737: 英文)
    :param rate: 采样率 (固定 16000)
    :return: task_id (str) or None
    """
    token = get_baidu_token()
    if not token:
        raise Exception("无法获取百度 Token")

    url = "https://aip.baidubce.com/rpc/2.0/aasr/v1/create"
    params = {"access_token": token}

    payload = {
        "speech_url": speech_url,
        "format": format,
        "pid": pid,
        "rate": rate
    }

    try:
        headers = {'Content-Type': 'application/json'}
        resp = requests.post(url, params=params, json=payload, headers=headers, timeout=10)
        data = resp.json()

        if data.get("error_code"):
            raise Exception(f"创建任务失败: {data.get('error_msg')} (Code: {data.get('error_code')})")

        return data.get("task_id")
    except Exception as e:
        print(f"❌ [Baidu Create Task Error]: {e}")
        raise e


def query_transcription_task(task_id: str):
    """
    步骤2: 查询任务结果
    """
    token = get_baidu_token()
    url = "https://aip.baidubce.com/rpc/2.0/aasr/v1/query"
    params = {"access_token": token}

    payload = {
        "task_ids": [task_id]
    }

    try:
        headers = {'Content-Type': 'application/json'}
        resp = requests.post(url, params=params, json=payload, headers=headers, timeout=10)
        data = resp.json()

        if data.get("error_code"):
            # 注意：如果是查询不存在的任务等错误，这里会抛出
            raise Exception(f"查询任务失败: {data.get('error_msg')}")

        tasks_info = data.get("tasks_info", [])
        if not tasks_info:
            return None

        return tasks_info[0]  # 返回第一个任务的信息
    except Exception as e:
        print(f"❌ [Baidu Query Task Error]: {e}")
        raise e


def transcribe_audio_via_url(speech_url: str, format: str = "wav") -> str:
    """
    [高层封装] 提交 URL 并轮询等待结果
    注意：这会阻塞线程直到转写完成（或超时）
    """
    try:
        # 1. 创建任务
        print(f"🚀 [Baidu ASR] 提交任务: {speech_url} ({format})")
        task_id = create_transcription_task(speech_url, format=format)
        if not task_id:
            return "❌ 创建转写任务失败，未返回 Task ID"

        print(f"⏳ [Baidu ASR] 任务创建成功 ID: {task_id}，开始轮询结果...")

        # 2. 轮询结果 (设置最大重试次数，防止无限等待)
        # 会议纪要可能很长，假设最长等待 10 分钟 (600秒)
        # 初始轮询间隔 2s，后续可以拉长
        max_retries = 200
        for i in range(max_retries):
            task_info = query_transcription_task(task_id)
            if not task_info:
                time.sleep(2)
                continue

            status = task_info.get("task_status")

            if status == "Success":
                # 转写成功，提取文本
                task_result = task_info.get("task_result", {})
                result_lines = task_result.get("result", [])
                full_text = "\n".join(result_lines)
                print(f"✅ [Baidu ASR] 转写完成 (耗时: {i * 2}s approx)")
                return full_text

            elif status == "Failure":
                err_msg = task_info.get("task_result", {}).get("err_msg", "未知错误")
                return f"❌ 转写任务失败: {err_msg}"

            elif status in ["Created", "Running"]:
                # 继续等待
                sleep_time = 2 if i < 10 else 5  # 前10次每2秒查一次，之后每5秒查一次
                time.sleep(sleep_time)
            else:
                return f"❌ 未知任务状态: {status}"

        return "❌ 转写超时 (10分钟未完成)，请稍后查询。"

    except Exception as e:
        return f"❌ 转写流程异常: {str(e)}"


def _load_audio_segment(audio_bytes: bytes, filename: str = None):
    if AudioSegment is None:
        raise RuntimeError(f"缺少 pydub/ffmpeg 运行环境: {PYDUB_IMPORT_ERROR}")
    if not audio_bytes:
        raise RuntimeError("音频文件为空")

    suffix = os.path.splitext(filename or "")[-1] or ".wav"
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(audio_bytes)
            temp_path = temp_file.name
        return AudioSegment.from_file(temp_path)
    except Exception as e:
        raise RuntimeError(f"加载音频文件失败: {e}") from e
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def transcribe_audio_via_chunks(audio_bytes: bytes, filename: str = None) -> str:
    """
    本地加载音频并切成多个 wav 片段，逐段调用百度短语音识别。
    适用于本地部署、长音频且无法提供公网可访问 URL 的场景。
    """
    audio = _load_audio_segment(audio_bytes, filename)
    audio = audio.set_frame_rate(16000).set_channels(1)

    total_ms = len(audio)
    if total_ms <= 0:
        return ""

    chunk_ms = ASR_CHUNK_SECONDS * 1000
    total_chunks = math.ceil(total_ms / chunk_ms)
    if total_chunks > ASR_CHUNK_MAX_COUNT:
        raise RuntimeError(
            f"音频过长，预计需要 {total_chunks} 个分片，超过限制 {ASR_CHUNK_MAX_COUNT}。"
        )

    print(
        f"🔁 [Baidu Chunk ASR] 使用本地分片转写: "
        f"duration={total_ms / 1000:.1f}s, chunks={total_chunks}, chunk_size={ASR_CHUNK_SECONDS}s"
    )

    result_parts = []
    for idx, start_ms in enumerate(range(0, total_ms, chunk_ms), start=1):
        end_ms = min(start_ms + chunk_ms, total_ms)
        chunk = audio[start_ms:end_ms]
        if len(chunk) < 300:
            continue

        chunk_buffer = io.BytesIO()
        chunk.export(chunk_buffer, format="wav")
        chunk_bytes = chunk_buffer.getvalue()
        print(f"🎙️ [Baidu Chunk ASR] 分片 {idx}/{total_chunks}: {start_ms / 1000:.1f}s - {end_ms / 1000:.1f}s")

        text = baidu_asr_from_bytes(chunk_bytes, filename=f"chunk_{idx}.wav")
        clean_text = str(text or "").strip()
        if not clean_text:
            continue
        if clean_text.startswith("❌"):
            raise RuntimeError(f"分片 {idx} 识别失败: {clean_text}")
        result_parts.append(clean_text)

    return "\n".join(result_parts).strip()


# ----------------------------------------------------
# ✨ [修改] 短语音/实时语音识别：字节流 → 百度 ASR (Server API)
# ----------------------------------------------------
def baidu_asr_from_bytes(wav_bytes: bytes, filename: str = None):
    """
    直接上传音频二进制数据进行识别（适用于 60s 内的短语音/实时录音）
    """
    token = get_baidu_token()
    if not token:
        return "❌ 无法获取百度 Token"

    file_fmt = get_format_from_filename(filename)
    # Server API (短语音) 对格式支持较少 (pcm, wav, amr)，如果是 m4a 可能需要转码，这里假设前端录音是 wav
    if file_fmt not in ['pcm', 'wav', 'amr']:
        print(f"⚠️ [Baidu Short ASR] 格式 {file_fmt} 可能不支持，建议使用 wav/pcm")
        # 尝试强行识别，或者由前端保证录音为 wav

    # base64 编码
    speech_base64 = base64.b64encode(wav_bytes).decode("utf-8")
    url = "https://vop.baidu.com/server_api"

    # dev_pid: 1537 = 普通话(支持简单的英文), 80001 = 极速版(仅支持PCM/WAV/AMR, 16k)
    # 这里使用 1537 兼容性较好
    payload_dict = {
        "format": file_fmt,
        "rate": 16000,
        "channel": 1,
        "cuid": "dashboard_user_" + str(int(time.time())),
        "token": token,
        "dev_pid": 1537,
        "speech": speech_base64,
        "len": len(wav_bytes)
    }

    try:
        print(f"🎙️ [Baidu Short ASR] 发送识别请求 (大小: {len(wav_bytes)} bytes)...")
        resp = requests.post(url, json=payload_dict, timeout=30).json()

        if resp.get("err_no") == 0:
            result_list = resp.get("result", [])
            text = "".join(result_list)
            print(f"✅ [Baidu Short ASR] 识别成功: {text[:20]}...")
            return text
        else:
            err_msg = resp.get('err_msg')
            err_no = resp.get('err_no')
            print(f"❌ [Baidu Short ASR] 识别失败 ({err_no}): {err_msg}")
            return f"❌ 识别失败: {err_msg}"

    except Exception as e:
        print(f"❌ [Baidu Short ASR] 网络/系统异常: {e}")
        return f"❌ 识别异常: {str(e)}"
