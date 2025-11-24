from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
from typing import List
import os
import shutil
from datetime import datetime

router = APIRouter(prefix="/api/storage", tags=["storage"])

# --- KONFIGURATION: ABSOLUT SÖKVÄG ---
# Detta garanterar att vi alltid hamnar rätt, oavsett var du startar servern ifrån
STORAGE_ROOT = "/home/aurora/storage"

# Se till att rotmappen finns
os.makedirs(STORAGE_ROOT, exist_ok=True)

def get_safe_path(path_str: str):
    # Säkerhetsfunktion för att hindra folk från att skriva "../" och komma åt systemfiler
    if not path_str or path_str == "." or path_str == "/":
        return STORAGE_ROOT

    # Ta bort inledande slash om den finns
    clean_path = path_str.lstrip("/")
    full_path = os.path.abspath(os.path.join(STORAGE_ROOT, clean_path))

    # Säkerhetskoll: Sökvägen MÅSTE börja med STORAGE_ROOT
    if not full_path.startswith(STORAGE_ROOT):
        return STORAGE_ROOT

    return full_path

@router.get("/list")
def list_files(path: str = ""):
    target_dir = get_safe_path(path)

    if not os.path.exists(target_dir):
        return {"files": []}

    items = []
    try:
        for entry in os.scandir(target_dir):
            items.append({
                "name": entry.name,
                "type": "dir" if entry.is_dir() else "file",
                "size": entry.stat().st_size if entry.is_file() else 0,
                "modified": datetime.fromtimestamp(entry.stat().st_mtime).isoformat()
            })
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")

    return {"files": items}

@router.post("/upload")
async def upload_file(path: str = Form(""), files: List[UploadFile] = File(...)):
    target_dir = get_safe_path(path)
    os.makedirs(target_dir, exist_ok=True)

    saved_files = []
    for file in files:
        file_path = os.path.join(target_dir, file.filename)
        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            saved_files.append(file.filename)
        except Exception as e:
            print(f"Upload error: {e}")

    return {"message": "Upload successful", "saved": saved_files}

@router.get("/quota")
def get_quota():
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(STORAGE_ROOT):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)

    # Hårdkodad gräns på 30GB för demo
    return {"used": total_size, "limit": 30 * 1024 * 1024 * 1024}

@router.post("/delete")
async def delete_item(payload: dict):
    path = payload.get("path")
    if not path:
         raise HTTPException(status_code=400, detail="Path required")

    target = get_safe_path(path)

    if not os.path.exists(target):
        raise HTTPException(status_code=404, detail="Not found")

    if os.path.isfile(target):
        os.remove(target)
    elif os.path.isdir(target):
        shutil.rmtree(target)

    return {"message": "Deleted"}