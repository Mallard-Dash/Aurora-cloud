import os
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Body
from fastapi.responses import FileResponse
from pydantic import BaseModel
from .dependencies import get_current_user, User

router = APIRouter(prefix="/api/storage", tags=["Storage"])

# Konfig
STORAGE_ROOT = Path("/srv/aurora/storage")
QUOTA_LIMIT = 30 * 1024 * 1024 * 1024 # 30 GB

def get_user_dir(username: str) -> Path:
    """Säkerställer att användarens mapp finns och returnerar sökvägen."""
    user_path = STORAGE_ROOT / username
    if not user_path.exists():
        user_path.mkdir(parents=True, exist_ok=True)
    return user_path

def calculate_usage(path: Path) -> int:
    """Räknar total storlek rekursivt."""
    total = 0
    for p in path.rglob('*'):
        if p.is_file():
            total += p.stat().st_size
    return total

def safe_path(user_root: Path, relative_path: str) -> Path:
    """Förhindrar Path Traversal (../) attacker."""
    # Normalisera och ta bort inledande slashes
    rel = relative_path.lstrip("/")
    if rel == "" or rel == ".":
        return user_root
    
    target = (user_root / rel).resolve()
    
    # Kontrollera att target fortfarande ligger inuti user_root
    if not str(target).startswith(str(user_root.resolve())):
        raise HTTPException(status_code=403, detail="Åtkomst nekad: Utanför din mapp")
    
    return target

class FileInfo(BaseModel):
    name: str
    type: str # 'file' eller 'dir'
    size: int
    modified: float
    path: str

class QuotaInfo(BaseModel):
    used: int
    limit: int
    percent: float

@router.get("/list")
async def list_files(path: str = "", user: User = Depends(get_current_user)):
    root = get_user_dir(user.username)
    target = safe_path(root, path)
    
    if not target.exists():
        raise HTTPException(404, "Mappen finns inte")
    
    items = []
    # Sortera: Mappar först, sen filer
    try:
        for entry in sorted(target.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            items.append(FileInfo(
                name=entry.name,
                type="dir" if entry.is_dir() else "file",
                size=entry.stat().st_size if entry.is_file() else 0,
                modified=entry.stat().st_mtime,
                path=str(entry.relative_to(root))
            ))
    except PermissionError:
        raise HTTPException(403, "Ingen behörighet")

    return items

@router.get("/quota", response_model=QuotaInfo)
async def get_quota(user: User = Depends(get_current_user)):
    root = get_user_dir(user.username)
    used = calculate_usage(root)
    percent = (used / QUOTA_LIMIT) * 100
    return QuotaInfo(used=used, limit=QUOTA_LIMIT, percent=round(percent, 1))

@router.post("/upload")
async def upload_file(
    path: str = Form(""),
    files: List[UploadFile] = File(...),
    user: User = Depends(get_current_user)
):
    root = get_user_dir(user.username)
    target_dir = safe_path(root, path)
    
    # Kolla quota innan start (grov uppskattning)
    current_usage = calculate_usage(root)
    if current_usage >= QUOTA_LIMIT:
        raise HTTPException(413, "Lagringsutrymmet är fullt (30GB)")

    saved_files = []
    for file in files:
        file_path = target_dir / file.filename
        
        # Enkel streaming skrivning
        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            saved_files.append(file.filename)
        except Exception as e:
            return {"error": str(e)}
        finally:
            file.file.close()
            
    return {"message": f"Laddade upp {len(saved_files)} filer", "files": saved_files}

@router.post("/mkdir")
async def create_folder(path: str = Body(..., embed=True), user: User = Depends(get_current_user)):
    # path kommer in som "current_path/new_folder_name"
    root = get_user_dir(user.username)
    target = safe_path(root, path)
    if target.exists():
        raise HTTPException(409, "Mappen finns redan")
    target.mkdir()
    return {"message": "Mapp skapad"}

@router.post("/delete")
async def delete_item(path: str = Body(..., embed=True), user: User = Depends(get_current_user)):
    root = get_user_dir(user.username)
    target = safe_path(root, path)
    
    if not target.exists():
        raise HTTPException(404, "Hittades inte")
    
    if target == root:
        raise HTTPException(403, "Kan inte radera rotmappen")

    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    
    return {"message": "Raderad"}

@router.get("/download")
async def download_file(path: str, user: User = Depends(get_current_user)):
    root = get_user_dir(user.username)
    target = safe_path(root, path)
    if not target.is_file():
        raise HTTPException(404, "Filen hittades inte")
    
    return FileResponse(path=target, filename=target.name)
