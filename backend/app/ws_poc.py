# backend/app/ws_poc.py
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

router = APIRouter()
log = logging.getLogger("backend.ws_poc")

def validate_token(token: str) -> bool:
    if not token:
        return False
    return len(token) >= 8

def extract_token_from_ws(websocket: WebSocket) -> str | None:
    auth = websocket.headers.get("authorization")
    if auth:
        parts = auth.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1]
    qp = websocket.query_params.get("token")
    if qp:
        return qp
    return None

@router.websocket("/ws/terminal")
async def ws_terminal(websocket: WebSocket):
    token = extract_token_from_ws(websocket)
    if not validate_token(token):
        log.warning("WS connect rejected, invalid token; remote=%s", websocket.client)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    log.info("WS connected (PoC) remote=%s", websocket.client)
    try:
        await websocket.send_text("\x1b[32m*** Aurora PoC terminal (echo mode). Auth OK. ***\x1b[0m\r\n")
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
            except Exception:
                await websocket.send_text(data)
                continue

            t = msg.get("type")
            if t == "input":
                await websocket.send_text(msg.get("data", ""))
            elif t == "resize":
                cols = msg.get("cols"); rows = msg.get("rows")
                await websocket.send_text(f"\r\n\x1b[90m*** Resize {cols}x{rows} ***\x1b[0m\r\n")
            elif t == "ping":
                await websocket.send_text(json.dumps({"type":"pong"}))
            else:
                await websocket.send_text(f"\r\n\x1b[33m*** Unknown type: {t} ***\x1b[0m\r\n")
    except WebSocketDisconnect:
        log.info("WS disconnected remote=%s", websocket.client)
    except Exception as e:
        log.exception("WS loop error: %s", e)
        try:
            await websocket.close()
        except Exception:
            pass
