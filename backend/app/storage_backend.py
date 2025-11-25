import os
import shutil
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from typing import List
from pydantic import BaseModel
from .dependencies import get_current_user, User, STORAGE_PATH

router = APIRouter(prefix="/api/storage", tags=["storage"])

class FileItem(BaseModel):
    name: str
    type: str # 'file' or 'dir'
    size: int

class FileList(BaseModel):
    files: List[FileItem]

class DeleteReq(BaseModel):
    path: str

def secure_path(user_path: str):
    # Prevent directory traversal
    safe = os.path.normpath(os.path.join(STORAGE_PATH, user_path.lstrip('/')))
    if not safe.startswith(STORAGE_PATH):
        raise HTTPException(status_code=403, detail="Access denied")
    return safe

@router.get("/list")
def list_files(path: str = "", user: User = Depends(get_current_user)):
    target = secure_path(path)
    if not os.path.exists(target):
        return {"files": []}
    
    items = []
    try:
        for entry in os.scandir(target):
            items.append({
                "name": entry.name,
                "type": "dir" if entry.is_dir() else "file",
                "size": entry.stat().st_size
            })
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")
        
    return {"files": items}

@router.post("/upload")
def upload_files(path: str = "", files: List[UploadFile] = File(...), user: User = Depends(get_current_user)):
    target_dir = secure_path(path)
    os.makedirs(target_dir, exist_ok=True)
    
    for file in files:
        dest = os.path.join(target_dir, file.filename)
        with open(dest, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
    return {"message": f"Uploaded {len(files)} files"}

# HÄR ÄR FIXEN FÖR NEDLADDNING
@router.get("/download")
def download_file(path: str, user: User = Depends(get_current_user)):
    target = secure_path(path)
    if not os.path.exists(target) or not os.path.isfile(target):
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(target, filename=os.path.basename(target))

@router.post("/delete")
def delete_item(req: DeleteReq, user: User = Depends(get_current_user)):
    target = secure_path(req.path)
    if not os.path.exists(target):
        raise HTTPException(status_code=404, detail="Not found")
        
    if os.path.isdir(target):
        shutil.rmtree(target)
    else:
        os.remove(target)
        
    return {"message": "Deleted"}