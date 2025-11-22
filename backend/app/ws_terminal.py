"""
ws_terminal.py
WebSocket "terminal" router for Aurora-cloud.

Simple behavior:
- Validate token query param. Accepts "demo" (for debugging) or settings.WS_TOKEN / settings.SECRET_KEY.
- Accepts JSON messages from client with shape: {"type": "input", "data": "ls\n"}
- Runs each incoming input as a separate shell command via: bash -lc "<data>"
- Returns JSON messages to client with shape: {"type": "output", "data": "<command output>"} or {"type":"error","data":"..."}
- Gracefully handles disconnects and invalid messages.

Note: This is intentionally simple to avoid PTY complexity and circular imports.
"""

import json
import asyncio
import shlex
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

# Import settings (keep secrets/config in settings to avoid circular imports)
try:
    from backend.app import settings
except Exception:
    # Fallback: try direct import path if package layout different
    try:
        import settings  # type: ignore
    except Exception:
        settings = None  # type: ignore

router = APIRouter()
logger = logging.getLogger("ws_terminal")
logger.setLevel(logging.INFO)


def _get_setting(name: str) -> Optional[str]:
    if settings is None:
        return None
    return getattr(settings, name, None)


async def validate_ws_token(token: Optional[str]) -> bool:
    """Return True if token is acceptable."""
    if not token:
        return False

    # Allow quick debug token
    if token == "demo":
        return True

    # Compare with settings if available
    secret = _get_setting("SECRET_KEY") or _get_setting("WS_TOKEN")
    if secret and token == secret:
        return True

    # TODO: place for JWT validation if you later want real auth
    return False


async def run_command(command: str, timeout: float = 10.0) -> dict:
    """
    Run a shell command and return a dict with stdout/stderr/returncode.
    Uses bash -lc to interpret pipes, redirects, etc.
    """
    # Sanitize (we still pass to shell via -c, so don't try to escape everything)
    cmd = ["bash", "-lc", command]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {"returncode": -1, "stdout": "", "stderr": "Command timed out"}

        stdout_text = stdout.decode(errors="ignore") if stdout else ""
        stderr_text = stderr.decode(errors="ignore") if stderr else ""
        return {"returncode": proc.returncode, "stdout": stdout_text, "stderr": stderr_text}
    except Exception as exc:
        return {"returncode": -1, "stdout": "", "stderr": f"Failed to run command: {exc}"}


@router.websocket("/ws/terminal")
async def terminal_ws(websocket: WebSocket):
    """
    WebSocket endpoint for the terminal.
    Expects token as query param: /ws/terminal?token=...
    """
    # Validate token before accepting (prevent handshake accept returning 403 by refusing)
    token = websocket.query_params.get("token")
    if not await validate_ws_token(token):
        # Reject by closing immediately (client receives 403/handshake failure)
        # We try to close politely if accepted handshake happened. Some proxies return 403 at handshake-level;
        # here we simply do not accept the connection.
        try:
            # try close gracefully if we got this far
            await websocket.close(code=1008)
        except Exception:
            # swallow
            pass
        logger.warning("WebSocket connection refused due to invalid token.")
        return

    # Accept the connection
    await websocket.accept()
    logger.info("WebSocket terminal connected. token=%s", token)

    try:
        while True:
            msg_text = await websocket.receive_text()
            # Expect JSON, but tolerate raw strings (treat as input)
            try:
                payload = json.loads(msg_text)
            except Exception:
                # If not JSON, treat whole message as input
                payload = {"type": "input", "data": msg_text}

            if not isinstance(payload, dict):
                await websocket.send_text(json.dumps({"type": "error", "data": "Invalid payload"}))
                continue

            msg_type = payload.get("type")
            if msg_type == "input":
                data = payload.get("data", "")
                # Normalize: strip trailing nulls but keep newline if present
                if not isinstance(data, str):
                    await websocket.send_text(json.dumps({"type": "error", "data": "Input must be a string"}))
                    continue

                # If it's just a newline, ignore
                if data.strip() == "":
                    await websocket.send_text(json.dumps({"type": "output", "data": ""}))
                    continue

                # Run the command and send back output
                # Run as a single-shot command via bash -lc. This supports pipes and redirects.
                result = await run_command(data, timeout=15.0)

                # Compose result message. Send both stdout and stderr.
                out = result.get("stdout", "")
                err = result.get("stderr", "")
                rc = result.get("returncode", 0)

                # Build a friendly output block
                combined = ""
                if out:
                    combined += out
                if err:
                    if combined and not combined.endswith("\n"):
                        combined += "\n"
                    combined += f"[stderr]\n{err}"
                if combined == "":
                    combined = f"[exit {rc}]"

                await websocket.send_text(json.dumps({"type": "output", "data": combined, "rc": rc}))
            elif msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
            else:
                await websocket.send_text(json.dumps({"type": "error", "data": f"Unknown message type: {msg_type}"}))

    except WebSocketDisconnect:
        logger.info("WebSocket terminal disconnected.")
    except Exception as exc:
        logger.exception("Unhandled error in ws terminal: %s", exc)
        try:
            await websocket.send_text(json.dumps({"type": "error", "data": f"Server error: {exc}"}))
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass
