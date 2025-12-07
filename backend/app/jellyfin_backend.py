import docker
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from .dependencies import get_current_user, User

# Initiera router
router = APIRouter(prefix="/api/jellyfin", tags=["Media Center"])
logger = logging.getLogger(__name__)

# INSTÄLLNINGAR
CONTAINER_NAME = "aurora-media"  # Namnet på din container i Docker
# Den URL du vill att användaren ska skickas till. 
# Om du kör lokalt via IP, använd IP:n. Om du kör via domän, använd den.
PUBLIC_URL = "http://100.69.68.70:8096" 

class MediaStatus(BaseModel):
    status: str       # "running", "exited", "missing"
    url: str
    is_active: bool

def get_docker_client():
    try:
        return docker.from_env()
    except Exception as e:
        raise HTTPException(status_code=503, detail="Docker service unavailable")

@router.get("/status", response_model=MediaStatus)
def get_jellyfin_status(user: User = Depends(get_current_user)):
    """Kollar om Jellyfin är igång"""
    client = get_docker_client()
    try:
        container = client.containers.get(CONTAINER_NAME)
        state = container.status  # 'running' eller 'exited' osv.
        
        return {
            "status": state,
            "url": PUBLIC_URL,
            "is_active": (state == "running")
        }
    except docker.errors.NotFound:
        return {"status": "missing", "url": PUBLIC_URL, "is_active": False}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/power/{action}")
def control_jellyfin(action: str, user: User = Depends(get_current_user)):
    """Starta eller stoppa Jellyfin (kräver admin/vincent)"""
    
    # En enkel säkerhetskoll så inte vem som helst stänger av filmerna
    if not user.is_admin and user.username != "vincent":
        raise HTTPException(status_code=403, detail="Access denied: Media Control Restricted")

    client = get_docker_client()
    try:
        container = client.containers.get(CONTAINER_NAME)
        
        if action == "start":
            container.start()
            return {"message": "Jellyfin starting..."}
        elif action == "stop":
            container.stop()
            return {"message": "Jellyfin stopping..."}
        elif action == "restart":
            container.restart()
            return {"message": "Jellyfin restarting..."}
        else:
            raise HTTPException(status_code=400, detail="Invalid action")
            
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="Jellyfin container not found on server")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))