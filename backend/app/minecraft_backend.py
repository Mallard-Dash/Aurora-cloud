import subprocess
import logging
import asyncio
import os
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from .dependencies import get_current_user, User

router = APIRouter(prefix="/api/minecraft", tags=["Minecraft"])
logger = logging.getLogger(__name__)

# VIKTIGT: Kontrollera att dessa stämmer
MC_DIR = Path("/srv/minecraft") 
MC_JAR = "server.jar"
SCREEN_NAME = "mc-server"
JAVA_CMD = ["java", "-Xmx4G", "-Xms2G", "-jar", MC_JAR, "nogui"]

class MCStatus(BaseModel):
    running: bool
    online_players: int
    max_players: int
    version: str

class CommandReq(BaseModel):
    command: str

def is_server_running():
    try:
        res = subprocess.run(["screen", "-ls"], capture_output=True, text=True)
        return SCREEN_NAME in res.stdout
    except:
        return False

async def get_player_count():
    try:
        from mcstatus import JavaServer
        server = await asyncio.to_thread(JavaServer.lookup, "127.0.0.1")
        status = await asyncio.to_thread(server.status)
        return status.players.online, status.players.max, status.version.name
    except:
        return 0, 20, "Unknown"

@router.get("/status", response_model=MCStatus)
async def get_status(u: User = Depends(get_current_user)):
    running = is_server_running()
    p, m, v = 0, 20, "Offline"
    if running:
        p, m, v = await get_player_count()
    return MCStatus(running=running, online_players=p, max_players=m, version=str(v))

@router.post("/start")
async def start_server(u: User = Depends(get_current_user)):
    if is_server_running(): return {"message": "Already running"}
    subprocess.Popen(["screen", "-dmS", SCREEN_NAME] + JAVA_CMD, cwd=MC_DIR)
    return {"message": "Started"}

@router.post("/stop")
async def stop_server(u: User = Depends(get_current_user)):
    if not is_server_running(): return {"message": "Not running"}
    subprocess.run(["screen", "-S", SCREEN_NAME, "-X", "stuff", "stop\n"])
    return {"message": "Stopping"}

@router.post("/command")
async def send_command(req: CommandReq, u: User = Depends(get_current_user)):
    """Skickar kommando till screen sessionen"""
    if not is_server_running():
        raise HTTPException(400, "Server offline")
    
    # Säkra inputs lite grann
    cmd = req.command.strip()
    subprocess.run(["screen", "-S", SCREEN_NAME, "-X", "stuff", f"{cmd}\n"])
    return {"status": "sent", "command": cmd}

@router.get("/logs")
async def get_logs(u: User = Depends(get_current_user)):
    """Läser de sista 50 raderna från logs/latest.log"""
    log_file = MC_DIR / "logs" / "latest.log"
    if not log_file.exists():
        return {"logs": ["Log file not found."]}
    
    try:
        # Läs sista 50 raderna med tail
        res = subprocess.run(["tail", "-n", "50", str(log_file)], capture_output=True, text=True)
        lines = res.stdout.splitlines()
        return {"logs": lines}
    except Exception as e:
        return {"logs": [f"Error reading logs: {str(e)}"]}
