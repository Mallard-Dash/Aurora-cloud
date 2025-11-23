import docker
import os
import json
from typing import List, Dict, Optional
from fastapi import HTTPException

DOCKER_SOCKET = os.getenv("DOCKER_SOCKET_PATH", "/var/run/docker.sock")
TEMPLATES_FILE = os.path.join(os.path.dirname(__file__), "templates.json")

def get_client():
    try:
        if DOCKER_SOCKET and DOCKER_SOCKET != "/var/run/docker.sock":
            return docker.DockerClient(base_url=f"unix://{DOCKER_SOCKET}")
        return docker.from_env()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Docker Daemon not reachable: {str(e)}")

def get_templates() -> List[Dict]:
    try:
        with open(TEMPLATES_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def list_containers() -> List[Dict]:
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

def create_container(name: str, template_name: str):
    templates = get_templates()
    template = next((t for t in templates if t["name"] == template_name), None)
    
    if not template:
        raise HTTPException(status_code=400, detail="Template not found")

    client = get_client()
    
    try:
        # Basic security: Drop capabilities if needed, here we keep it simple but safe
        container = client.containers.run(
            template["image"],
            command=template["command"],
            name=name,
            detach=True,
            ports={f"{p}/tcp": None for p in template.get("ports", []) or []} # Random host ports
        )
        return container.id
    except docker.errors.APIError as e:
        raise HTTPException(status_code=409, detail=f"Docker Error: {str(e)}")

def perform_action(container_id: str, action: str):
    client = get_client()
    try:
        container = client.containers.get(container_id)
        if action == "start":
            container.start()
        elif action == "stop":
            container.stop()
        elif action == "delete":
            container.remove(force=True)
        else:
            raise HTTPException(status_code=400, detail="Invalid action")
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="Container not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))