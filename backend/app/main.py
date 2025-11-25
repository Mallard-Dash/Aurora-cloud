import logging
import os
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy.orm import Session
from prometheus_client import generate_latest
from pydantic import BaseModel

# Import Models & Deps
from .models import Base, User
from .dependencies import (
    engine, SessionLocal, get_db, get_current_user, 
    create_access_token, get_password_hash, verify_password, 
    SECRET_KEY, ALGORITHM, STORAGE_PATH
)

# Import Routers
from .borealis_backend import router as borealis_router
from .minecraft_backend import router as minecraft_router
from .system_backend import router as system_router
from .storage_backend import router as storage_router
from .health_backend import router as health_logs_router
from .docker_backend import router as docker_router
from .aurora_health_backend import router as aurora_health_router 

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Aurora Cloud Portal")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all routers
app.include_router(borealis_router)
app.include_router(minecraft_router)
app.include_router(system_router)
app.include_router(storage_router)
app.include_router(health_logs_router)
app.include_router(docker_router)
app.include_router(aurora_health_router)

@app.on_event("startup")
async def startup_event():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        DEFAULT_PW = "default123"
        hashed_pw = get_password_hash(DEFAULT_PW)

        if not db.query(User).filter(User.username == "aurora").first():
            logger.info("Creating default admin user: aurora")
            db.add(User(username="aurora", email="aurora@aurora-cloud.local", password_hash=hashed_pw, is_admin=True))
        
        if not db.query(User).filter(User.username == "freyja").first():
            logger.info("Creating standard user: freyja")
            db.add(User(username="freyja", email="freyja@aurora-cloud.local", password_hash=hashed_pw, is_admin=False))

        db.commit()
        Path(STORAGE_PATH).mkdir(parents=True, exist_ok=True)
    finally:
        db.close()

class LoginReq(BaseModel):
    username: str
    password: str

class ChangePasswordReq(BaseModel):
    old_password: str
    new_password: str

class UpdateUserReq(BaseModel):
    new_username: str
    new_email: str

@app.post("/api/auth/login")
async def login(req: LoginReq, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect credentials")
    token = create_access_token({"sub": user.username})
    return {"access_token": token, "token_type": "bearer"}

@app.post("/api/auth/change-password")
async def change_password(req: ChangePasswordReq, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not verify_password(req.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect old password.")
    current_user.password_hash = get_password_hash(req.new_password)
    db.commit()
    return {"message": "Password updated"}

@app.post("/api/auth/update-profile")
async def update_user_profile(req: UpdateUserReq, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Kontrollera om namnet redan är taget av någon annan
    existing = db.query(User).filter(User.username == req.new_username).first()
    if existing and existing.id != current_user.id:
        raise HTTPException(status_code=400, detail="Username already taken.")
    
    current_user.username = req.new_username
    # Vi lägger till email om modellen stöder det, annars ignorera eller lägg till kolumn i models.py
    if hasattr(current_user, "email"):
        current_user.email = req.new_email
        
    db.commit()
    
    # Utfärda ny token eftersom identiteten ändrats
    new_token = create_access_token({"sub": current_user.username})
    return {"message": "Profile updated", "access_token": new_token}

@app.get("/api/user/me")
async def read_users_me(current_user: User = Depends(get_current_user)):
    email = getattr(current_user, "email", "")
    return {"username": current_user.username, "email": email, "is_admin": current_user.is_admin}

@app.get("/api/storage/quota")
async def get_storage_quota(user: User = Depends(get_current_user)):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(STORAGE_PATH):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)
    limit = 30 * 1024 * 1024 * 1024 
    percent = min(100, (total_size / limit) * 100) if limit > 0 else 0
    return { "used": total_size, "limit": limit, "percent": percent }

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type="text/plain")

@app.get("/")
async def root():
    return {"status": "Aurora System Online", "version": "English Edition"}