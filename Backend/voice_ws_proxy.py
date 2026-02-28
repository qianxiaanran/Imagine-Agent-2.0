import json
import asyncio
import websockets
import logging
import uuid
import ssl
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

# 尝试从 config.py 导入配置
try:
    import config
    BAIDU_APP_ID = config.BAIDU_APP_ID
    BAIDU_API_KEY = config.BAIDU_API_KEY
    BAIDU_DEV_PID = getattr(config, 'DEV_PID', 15372)
except Exception as e:
    BAIDU_API_KEY = None
    BAIDU_APP_ID = None
    BAIDU_DEV_PID = 15372
    print("❌ [Config Error] 无法导入 config.py:", e)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voice_ws_proxy")

router = APIRouter()

BAIDU_ASR_URI = "wss://vop.baidu.com/realtime_asr"


# ---------------------------------------------------------------------------
# 安全发送
# ---------------------------------------------------------------------------
async def safe_send(ws: WebSocket, data: str):
    """确保在连接状态下发送文本消息"""
    if ws.client_state == WebSocketState.CONNECTED:
        try:
            await ws.send_text(data)
        except WebSocketDisconnect:
            logger.warning("⚠ safe_send: 前端已断开，无法发送消息")
        except Exception as e:
            logger.warning(f"⚠ safe_send 异常: {e}")
    else:
        logger.info("⚠ safe_send 跳过：WebSocket 已关闭或正在关闭")


# ---------------------------------------------------------------------------
# 最终修复版 safe_close（永不报 RuntimeError）
# ---------------------------------------------------------------------------
async def safe_close(ws: WebSocket):
    """
    确保 close 调用绝对安全：
    - 仅当 state == CONNECTED 才调用 close()
    - 避免在 CLOSING / DISCONNECTED 状态下重复 close
    """

    state = ws.client_state

    if state == WebSocketState.CONNECTED:
        try:
            await ws.close()
        except (WebSocketDisconnect, RuntimeError):
            pass
        except Exception as e:
            logger.warning(f"⚠ safe_close 关闭异常: {e}")

    else:
        # CLOSING / DISCONNECTED → 不允许 close，否则会触发 RuntimeError
        logger.info(f"safe_close 跳过（当前状态: {state})")


# ---------------------------------------------------------------------------
# 百度 ASR WebSocket 代理
# ---------------------------------------------------------------------------
async def baidu_asr_proxy(client_ws: WebSocket):

    await client_ws.accept()
    logger.info("🌐 前端 WebSocket 已连接")

    # 配置检查
    if not BAIDU_APP_ID or not BAIDU_API_KEY:
        msg = "后端缺少百度 APP_ID 或 API_KEY"
        logger.error(msg)
        await safe_send(client_ws, json.dumps({"type": "ERROR", "err_msg": msg}))
        await safe_close(client_ws)
        return

    session_sn = str(uuid.uuid4())

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    baidu_ws = None

    try:
        baidu_ws = await websockets.connect(
            f"{BAIDU_ASR_URI}?sn={session_sn}",
            ssl=ssl_context,
            ping_interval=None,
        )

        # 发送 START 帧
        start_frame = {
            "type": "START",
            "data": {
                "appid": int(BAIDU_APP_ID),
                "appkey": BAIDU_API_KEY,
                "dev_pid": int(BAIDU_DEV_PID),
                "format": "pcm",
                "sample": 16000,
                "cuid": "dashboard_ws_client"
            }
        }

        await baidu_ws.send(json.dumps(start_frame))
        logger.info("📨 已发送 START 帧")

        # 等待百度握手
        try:
            handshake = await asyncio.wait_for(baidu_ws.recv(), timeout=10)
            handshake_data = json.loads(handshake)

            if handshake_data.get("err_no") != 0:
                err = handshake_data.get("err_msg")
                logger.error(f"百度握手失败: {err}")

                await safe_send(client_ws, json.dumps({"type": "ERROR", "err_msg": err}))
                await safe_close(client_ws)
                return

            logger.info("🤝 百度握手成功")

        except asyncio.TimeoutError:
            msg = "百度握手超时"
            logger.error(msg)
            await safe_send(client_ws, json.dumps({"type": "ERROR", "err_msg": msg}))
            await safe_close(client_ws)
            return

        # ---------------------------------------
        # 任务 A：百度 → 前端
        # ---------------------------------------
        async def from_baidu():
            try:
                async for msg in baidu_ws:
                    d = json.loads(msg)
                    if d.get("type") != "HEARTBEAT":
                        await safe_send(client_ws, json.dumps(d))
            except Exception as e:
                logger.error(f"百度通道异常: {e}")

        # ---------------------------------------
        # 任务 B：前端 → 百度
        # ---------------------------------------
        async def from_client():
            try:
                while True:
                    recv = await client_ws.receive()

                    if recv.get("bytes"):
                        await baidu_ws.send(recv["bytes"])

                    elif recv.get("text"):
                        obj = json.loads(recv["text"])
                        if obj.get("type") == "FINISH":
                            await baidu_ws.send(json.dumps({"type": "FINISH"}))
                            logger.info("▶ 前端发送 FINISH")

            except WebSocketDisconnect:
                logger.info("❌ 前端断开")
                try:
                    await baidu_ws.send(json.dumps({"type": "CANCEL"}))
                except:
                    pass

        t1 = asyncio.create_task(from_baidu())
        t2 = asyncio.create_task(from_client())

        await asyncio.wait([t1, t2], return_when=asyncio.FIRST_COMPLETED)

    except Exception as e:
        logger.error(f"代理异常: {e}")
        await safe_send(client_ws, json.dumps({"type": "ERROR", "err_msg": str(e)}))

    finally:

        # 关闭百度 websocket
        if baidu_ws:
            try:
                await baidu_ws.close()
            except:
                pass

        # 永不报错的安全关闭
        await safe_close(client_ws)

        logger.info("🔚 WebSocket 会话结束")


# ---------------------------------------------------------------------------
# FastAPI WebSocket 路由
# ---------------------------------------------------------------------------
@router.websocket("/transcribe")
async def websocket_endpoint(websocket: WebSocket):
    logger.info("📥 WebSocket /api/ws/transcribe 被调用")
    await baidu_asr_proxy(websocket)
