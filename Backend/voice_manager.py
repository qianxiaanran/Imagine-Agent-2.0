import requests
import base64
import datetime
import os
import json
import time
from config import BAIDU_API_KEY, BAIDU_SECRET_KEY

# ----------------------------------------------------
# Baidu ASR Token 缓存
# ----------------------------------------------------
BAIDU_ASR_TOKEN = None
BAIDU_ASR_TOKEN_TIME = None


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
        resp = requests.post(url, json=payload_dict, timeout=10).json()

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