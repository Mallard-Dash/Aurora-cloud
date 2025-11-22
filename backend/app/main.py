import logging
import os
import shutil
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

from .borealis_backend import router as borealis_router
from .minecraft_backend import router as minecraft_router
from .system_backend import router as system_router
from .storage_backend import router as storage_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Aurora-cloud Portal")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(borealis_router)
app.include_router(minecraft_router)
app.include_router(system_router)
app.include_router(storage_router)

@app.on_event("startup")
async def startup_event():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Seed default admin if missing
        ROOT_PW = os.getenv("ROOT_PASSWORD", "admin")
        ROOT_HASH = get_password_hash(ROOT_PW)
        if not db.query(User).filter(User.username == "aurora").first():
            logger.info("Creating default admin user: aurora")
            db.add(User(username="aurora", password_hash=ROOT_HASH, is_admin=True))
        db.commit()
        Path(STORAGE_PATH).mkdir(parents=True, exist_ok=True)
    finally:
        db.close()

# --- AUTH MODELLER ---
class LoginReq(BaseModel):
    username: str
    password: str

class ChangePasswordReq(BaseModel):
    old_password: str
    new_password: str

# --- AUTH ENDPOINTS ---
@app.post("/api/auth/login")
async def login(req: LoginReq, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect credentials")
    token = create_access_token({"sub": user.username})
    return {"access_token": token, "token_type": "bearer"}

@app.post("/api/auth/change-password")
async def change_password(req: ChangePasswordReq, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # 1. Verifiera gamla lösenordet
    if not verify_password(req.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Det gamla lösenordet är fel.")
    
    # 2. Sätt nytt
    current_user.password_hash = get_password_hash(req.new_password)
    db.commit()
    return {"message": "Lösenord uppdaterat"}

@app.get("/api/user/me")
async def read_users_me(current_user: User = Depends(get_current_user)):
    return {"username": current_user.username, "is_admin": current_user.is_admin}

# --- STORAGE QUOTA ENDPOINT ---
# Vi lägger den här för enkelhetens skull, eller i storage_backend om du föredrar.
# Men eftersom storage_backend redan är mountad, lägger vi en hjälpare här som frontend kan anropa om vi vill,
# ELLER så uppdaterar vi storage_backend. Vi kör en override här för snabb fix.
@app.get("/api/storage/quota")
async def get_storage_quota(user: User = Depends(get_current_user)):
    total_size = 0
    # Räkna storlek rekursivt
    for dirpath, dirnames, filenames in os.walk(STORAGE_PATH):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            # skip if broken link
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)
    
    limit = 30 * 1024 * 1024 * 1024 # 30 GB
    return {
        "used": total_size,
        "limit": limit,
        "percent": min(100, (total_size / limit) * 100)
    }

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type="text/plain")

@app.get("/")
async def root():
    return {"status": "Aurora System Online", "version": "Final"}
