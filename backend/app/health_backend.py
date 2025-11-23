import subprocess
import os
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from .dependencies import get_current_user, User

router = APIRouter(prefix="/api/health", tags=["Health & Logs"])

# Konfiguration för logg-sökvägar (Anpassa efter din server)
LOG_PATHS = {
    "nginx_access": "/var/log/nginx/access.log",
    "nginx_error": "/var/log/nginx/error.log",
    "api": "app.log" # Exempel, om du loggar till fil
}

class LogEntry(BaseModel):
    timestamp: str
    source: str
    message: str

class LogRequest(BaseModel):
    lines: int = 50
    filter_text: Optional[str] = None

def read_file_tail(filepath: str, lines: int, filter_text: str = None) -> List[str]:
    """Läser slutet av en fil säkert"""
    if not os.path.exists(filepath):
        return [f"Log file not found: {filepath}"]
    
    cmd = ["tail", "-n", str(lines), filepath]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        output = result.stdout.splitlines()
        
        if filter_text:
            output = [line for line in output if filter_text.lower() in line.lower()]
            
        return output
    except Exception as e:
        return [f"Error reading file: {str(e)}"]

def get_journalctl_logs(service: str = None, lines: int = 50, filter_text: str = None) -> List[str]:
    """Hämtar systemloggar via journalctl"""
    cmd = ["journalctl", "-n", str(lines), "--no-pager", "--output", "short"]
    if service:
        cmd.extend(["-u", service])
    
    try:
        # OBS: Kräver att användaren som kör python har rättigheter till journalctl
        result = subprocess.run(cmd, capture_output=True, text=True)
        output = result.stdout.splitlines()
        
        if filter_text:
            output = [line for line in output if filter_text.lower() in line.lower()]
            
        return output
    except Exception as e:
        return [f"Error running journalctl: {str(e)}"]

def get_docker_logs(container_name: str, lines: int = 50) -> List[str]:
    """Hämtar loggar från en docker container"""
    cmd = ["docker", "logs", "--tail", str(lines), container_name]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        # Docker logs kommer ofta på stderr
        output = (result.stdout + result.stderr).splitlines()
        return output
    except Exception as e:
        return [f"Error reading docker logs: {str(e)}"]

@router.get("/logs/{source}")
async def get_logs(source: str, lines: int = 50, filter: str = "", user: User = Depends(get_current_user)):
    """
    Hämtar loggar baserat på källa.
    Källor: 'system', 'nginx', 'docker', 'api'
    """
    filter_text = filter if filter.strip() != "" else None
    
    if source == "system":
        return {"logs": get_journalctl_logs(lines=lines, filter_text=filter_text)}
    
    elif source == "nginx":
        # Kombinera access och error loggar
        access = read_file_tail(LOG_PATHS["nginx_access"], lines // 2, filter_text)
        error = read_file_tail(LOG_PATHS["nginx_error"], lines // 2, filter_text)
        return {"logs": access + error}
    
    elif source == "docker":
        # Exempel: Hämta alla containrar eller en specifik (här 'aurora-core' som exempel)
        # I en riktig app, lista containrar och låt användaren välja
        try:
            ps = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True)
            containers = ps.stdout.splitlines()
            all_logs = []
            for c in containers:
                all_logs.append(f"--- Container: {c} ---")
                all_logs.extend(get_docker_logs(c, lines=10))
            return {"logs": all_logs}
        except:
            return {"logs": ["Could not list docker containers"]}

    elif source == "api":
        # Om API:et loggar till fil
        return {"logs": read_file_tail("main.log", lines, filter_text)}

    else:
        raise HTTPException(404, "Unknown log source")