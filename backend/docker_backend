from fastapi import APIRouter, HTTPException
from typing import List, Dict
import docker
import os
import json

# Initiera Router
router = APIRouter(prefix="/api/docker", tags=["docker"])

# --- DOCKER LOGIK (Från din gamla service-fil) ---
DOCKER_SOCKET = os.getenv("DOCKER_SOCKET_PATH", "/var/run/docker.sock")
TEMPLATES_FILE = os.path.join(os.path.dirname(__file__), "templates.json")

def get_client():
    try:
        return docker.from_env()
    except Exception as e:
        print(f"Docker connection failed: {e}")
        raise HTTPException(status_code=503, detail="Docker daemon unreachable")

def get_templates_data():
    try:
        with open(TEMPLATES_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

# --- ENDPOINTS ---

@router.get("/containers")
def list_containers():
    client = get_client()
    containers = client.containers.list(all=True)
    result = []
    for c in containers:
        result.append({
            "id": c.id,
            "short_id": c.short_id,
            "name": c.name,
            "status": c.status,
            "image": str(c.image.tags[0]) if c.image.tags else "none",
            "created": c.attrs['Created']
        })
    return result

@router.get("/templates")
def get_templates():
    return get_templates_data()

@router.post("/containers/create")
def create_container_endpoint(payload: Dict):
    name = payload.get("name")
    template_name = payload.get("template")
    
    templates = get_templates_data()
    template = next((t for t in templates if t["name"] == template_name), None)
    
    if not template:
        raise HTTPException(status_code=400, detail="Template not found")

    client = get_client()
    try:
        container = client.containers.run(
            template["image"],
            command=template.get("command"),
            name=name,
            detach=True,
            ports={f"{p}/tcp": None for p in template.get("ports", []) or []}
        )
        return {"id": container.id, "message": "Container created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/containers/{container_id}/{action}")
def container_action(container_id: str, action: str):
    client = get_client()
    try:
        container = client.containers.get(container_id)
        if action == "start":
            container.start()
        elif action == "stop":
            container.stop()
        else:
            raise HTTPException(status_code=400, detail="Invalid action")
        return {"message": f"Container {action}ed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/containers/{container_id}")
def delete_container(container_id: str):
    client = get_client()
    try:
        container = client.containers.get(container_id)
        container.remove(force=True)
        return {"message": "Container deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))