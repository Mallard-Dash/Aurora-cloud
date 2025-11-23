import time
from collections import defaultdict
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from .auth import verify_password, create_access_token, get_current_user, ADMIN_USERNAME, admin_hash
from .schemas import LoginRequest, Token, ContainerInfo, CreateContainerRequest, OperationResponse
from .docker_service import list_containers, create_container, perform_action, get_templates

app = FastAPI(title="Aurora Docker Manager")

# CORS - Allow the frontend to talk to this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate Limiting (In-Memory)
request_counts = defaultdict(list)
MAX_REQUESTS_PER_HOUR = 50 # Slightly generous for dev

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.method == "POST" and "create" in request.url.path:
        client_ip = request.client.host
        now = time.time()
        # Clean old requests
        request_counts[client_ip] = [t for t in request_counts[client_ip] if now - t < 3600]
        
        if len(request_counts[client_ip]) >= MAX_REQUESTS_PER_HOUR:
            raise HTTPException(status_code=429, detail="Rate limit exceeded for container creation")
        
        request_counts[client_ip].append(now)
        
    response = await call_next(request)
    return response

@app.post("/api/login", response_model=Token)
async def login(req: LoginRequest):
    if req.username != ADMIN_USERNAME or not verify_password(req.password, admin_hash):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    
    access_token = create_access_token(data={"sub": req.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/containers", dependencies=[Depends(get_current_user)])
async def get_containers():
    return list_containers()

@app.get("/api/templates", dependencies=[Depends(get_current_user)])
async def get_available_templates():
    return get_templates()

@app.post("/api/containers/create", status_code=202, dependencies=[Depends(get_current_user)])
async def create_new_container(req: CreateContainerRequest):
    cid = create_container(req.name, req.template)
    return {"message": "Container created successfully", "container_id": cid}

@app.post("/api/containers/{container_id}/start", dependencies=[Depends(get_current_user)])
async def start_container_endpoint(container_id: str):
    perform_action(container_id, "start")
    return {"message": "Container started"}

@app.post("/api/containers/{container_id}/stop", dependencies=[Depends(get_current_user)])
async def stop_container_endpoint(container_id: str):
    perform_action(container_id, "stop")
    return {"message": "Container stopped"}

@app.delete("/api/containers/{container_id}", dependencies=[Depends(get_current_user)])
async def delete_container_endpoint(container_id: str):
    perform_action(container_id, "delete")
    return {"message": "Container deleted"}