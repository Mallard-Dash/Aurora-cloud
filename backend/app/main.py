"""
Aurora-cloud Portal - FastAPI Backend
Main application entry point with all API routes
"""
import os
import sqlite3
import subprocess
import psutil
import asyncio
import json
import pty
import fcntl
import struct
import termios
import signal
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
from pathlib import Path

from fastapi import FastAPI, HTTPException, Depends, WebSocket, UploadFile, File, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import HTTPBearer
from starlette.authentication import AuthCredentials, SimpleUser
from starlette.requests import Request
from pydantic import BaseModel
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from jose import JWTError, jwt
from passlib.context import CryptContext
from prometheus_client import Counter, Gauge, generate_latest
from ptyprocess import PtyProcessUnicode
import logging

from .models import Base, User, FileRecord

# ============================================================================
# Configuration
# ============================================================================

proc = PtyProcessUnicode.spawn(["/bin/bash"])
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////tmp/portal.db")
STORAGE_PATH = os.getenv("STORAGE_PATH", "/tmp/storage")
SECRET_KEY = os.getenv("SECRET_KEY", "change_me_in_production_12345")
ROOT_PASSWORD = os.getenv("ROOT_PASSWORD", "ChangeMeNow!")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# ============================================================================
# Logging
# ============================================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================================
# Security & Hashing
# ============================================================================
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
security = HTTPBearer()


def hash_password(password: str) -> str:
    # Bcrypt has a 72-byte limit on password length
    return pwd_context.hash(password[:72])


def verify_password(plain_password: str, hashed_password: str) -> bool:
    # Bcrypt has a 72-byte limit on password length
    return pwd_context.verify(plain_password[:72], hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# ============================================================================
# Database Setup
# ============================================================================
# Convert SQLite URI for SQLAlchemy if needed
if DATABASE_URL.startswith("sqlite://"):
    db_path = DATABASE_URL.replace("sqlite://", "")
    sql_db_url = f"sqlite:///{db_path.lstrip('/')}"
else:
    sql_db_url = DATABASE_URL

# Ensure database directory exists for SQLite
if "sqlite" in sql_db_url:
    db_file_path = Path(sql_db_url.replace("sqlite:///", ""))
    db_file_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    sql_db_url,
    connect_args={"check_same_thread": False} if "sqlite" in sql_db_url else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables (will be created when app starts via startup_event)
try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    logger.warning(f"Could not create tables on startup: {e}")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================================
# Prometheus Metrics
# ============================================================================
login_attempts = Counter('login_attempts_total', 'Total login attempts', ['status'])
file_uploads = Counter('file_uploads_total', 'Total file uploads')
file_downloads = Counter('file_downloads_total', 'Total file downloads')
minecraft_starts = Counter('minecraft_starts_total', 'Total Minecraft start commands')
minecraft_stops = Counter('minecraft_stops_total', 'Total Minecraft stop commands')

cpu_load = Gauge('cpu_load_percent', 'CPU load percentage')
ram_used_gb = Gauge('ram_used_gb', 'RAM used in GB')
ram_total_gb = Gauge('ram_total_gb', 'Total RAM in GB')
disk_used_gb = Gauge('disk_used_gb', 'Disk used in GB')
disk_total_gb = Gauge('disk_total_gb', 'Total disk in GB')
cpu_temp_c = Gauge('cpu_temp_celsius', 'CPU temperature in Celsius')
uptime_seconds = Gauge('uptime_seconds', 'System uptime in seconds')

# ============================================================================
# Pydantic Models (Request/Response)
# ============================================================================


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    username: str
    full_name: Optional[str]
    email: Optional[str]
    is_admin: bool

    class Config:
        orm_mode = True

class FileInfo(BaseModel):
    name: str
    type: str  # 'file' or 'folder'
    size: int
    lastModified: str


class MetricsResponse(BaseModel):
    uptime: int
    cpu_load: float
    ram_used_gb: float
    ram_total_gb: float
    disk_used_gb: float
    disk_total_gb: float
    temp_c: float


class MinecraftStatus(BaseModel):
    status: str  # 'running' or 'stopped'
    version: str
    players: int
    uptime_h: int


# ============================================================================
# Dependency: Get Current User
# ============================================================================
async def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
) -> User:
    try:
        # Get token from Authorization header
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Invalid authorization header")
        
        token = auth_header[7:]  # Remove "Bearer " prefix
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# ============================================================================
# FastAPI App
# ============================================================================
app = FastAPI(title="Aurora-cloud Portal API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Initialization & Seeding
# ============================================================================
@app.on_event("startup")
async def startup_event():
    db = SessionLocal()
    try:
        root_user = db.query(User).filter(User.username == "root").first()
        if not root_user:
            logger.info("Creating root user...")
            root_user = User(
                username="root",
                full_name="Root User",
                email="root@localhost",
                password_hash=hash_password(ROOT_PASSWORD),
                is_admin=True
            )
            db.add(root_user)
            db.commit()
            logger.info("Root user created successfully")
        Path(STORAGE_PATH).mkdir(parents=True, exist_ok=True)
        logger.info(f"Storage path ready: {STORAGE_PATH}")
    except Exception:
        logger.exception("Startup event failed")
        raise
    finally:
        db.close()



# ============================================================================
# Authentication Endpoints
# ============================================================================
@app.post("/api/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    """
    Login endpoint - returns JWT access token
    """
    user = db.query(User).filter(User.username == request.username).first()
    
    if not user or not verify_password(request.password, user.password_hash):
        login_attempts.labels(status="failed").inc()
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    login_attempts.labels(status="success").inc()
    access_token = create_access_token(data={"sub": user.username})
    return LoginResponse(access_token=access_token)


@app.get("/api/user/me", response_model=UserResponse)
async def get_user_profile(current_user: User = Depends(get_current_user)):
    """
    Get current user profile
    """
    return UserResponse.from_orm(current_user)


# ============================================================================
# System Metrics Endpoints
# ============================================================================
@app.get("/api/metrics", response_model=MetricsResponse)
async def get_metrics(current_user: User = Depends(get_current_user)):
    """
    Get system metrics (CPU, RAM, disk, uptime, temperature)
    """
    try:
        # Uptime
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = int((datetime.now() - boot_time).total_seconds())
        
        # CPU
        cpu_percent = psutil.cpu_percent(interval=None)
        
        # RAM
        ram = psutil.virtual_memory()
        ram_used = ram.used / (1024 ** 3)  # Convert to GB
        ram_total = ram.total / (1024 ** 3)
        
        # Disk
        disk = psutil.disk_usage("/")
        disk_used = disk.used / (1024 ** 3)
        disk_total = disk.total / (1024 ** 3)
        
        # Temperature (try to get CPU temperature)
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                # Get the first available temperature
                first_temp_key = list(temps.keys())[0]
                temp_c = temps[first_temp_key][0].current
            else:
                temp_c = 0.0
        except (AttributeError, IndexError):
            temp_c = 0.0
        
        # Update Prometheus metrics
        cpu_load.set(cpu_percent)
        ram_used_gb.set(ram_used)
        ram_total_gb.set(ram_total)
        disk_used_gb.set(disk_used)
        disk_total_gb.set(disk_total)
        cpu_temp_c.set(temp_c)
        uptime_seconds.set(uptime)
        
        return MetricsResponse(
            uptime=uptime,
            cpu_load=cpu_percent / 100.0,  # Return as decimal
            ram_used_gb=ram_used,
            ram_total_gb=ram_total,
            disk_used_gb=disk_used,
            disk_total_gb=disk_total,
            temp_c=temp_c
        )
    except Exception as e:
        logger.error(f"Error fetching metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch metrics")


# ============================================================================
# File Management Endpoints
# ============================================================================
def get_user_storage_path(username: str) -> Path:
    """Get the storage path for a specific user"""
    return Path(STORAGE_PATH) / username


@app.get("/api/files")
async def list_files(
    path: str = "/",
    current_user: User = Depends(get_current_user)
):
    """
    List files in user's storage directory
    """
    try:
        user_storage = get_user_storage_path(current_user.username)
        user_storage.mkdir(parents=True, exist_ok=True)
        
        # Resolve the full path
        from pathlib import Path
        full_path = (user_storage / path.lstrip("/")).resolve()
        if os.path.commonpath([str(full_path), str(user_storage)]) != str(user_storage):
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Security: ensure path is within user storage
        if not str(full_path).startswith(str(user_storage)):
            raise HTTPException(status_code=403, detail="Access denied")
        
        if not full_path.exists():
            raise HTTPException(status_code=404, detail="Path not found")
        
        files = []
        for item in full_path.iterdir():
            stat = item.stat()
            files.append(FileInfo(
                name=item.name,
                type="folder" if item.is_dir() else "file",
                size=stat.st_size if item.is_file() else 0,
                lastModified=datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d")
            ))
        
        return files
    except Exception as e:
        logger.error(f"Error listing files: {e}")
        raise HTTPException(status_code=500, detail="Failed to list files")


@app.post("/api/files/upload")
async def upload_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    try:
        MAX_FILE_SIZE = 100 * 1024 * 1024 * 1024  # 100 GB top-level quota (server-enforced separately)

        user_storage = get_user_storage_path(current_user.username)
        user_storage.mkdir(parents=True, exist_ok=True)

        safe_filename = Path(file.filename).name
        file_path = user_storage / safe_filename

        # stream write in chunks
        size = 0
        with open(file_path, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)  # 1MB chunks
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_FILE_SIZE:
                    f.close()
                    file_path.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail="File too large")
                f.write(chunk)

        file_uploads.inc()
        return {"filename": safe_filename, "size": size}
    except Exception as e:
        logger.exception("Error uploading file")
        raise HTTPException(status_code=500, detail="Failed to upload file")



@app.get("/api/files/download")
async def download_file(
    path: str,
    current_user: User = Depends(get_current_user)
):
    """
    Download a file from user's storage
    """
    try:
        user_storage = get_user_storage_path(current_user.username)
        file_path = (user_storage / path.lstrip("/")).resolve()
        
        # Security: ensure path is within user storage
        if not str(file_path).startswith(str(user_storage)):
            raise HTTPException(status_code=403, detail="Access denied")
        
        if not file_path.exists() or file_path.is_dir():
            raise HTTPException(status_code=404, detail="File not found")
        
        file_downloads.inc()
        return FileResponse(file_path, filename=file_path.name)
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        raise HTTPException(status_code=500, detail="Failed to download file")


@app.delete("/api/files")
async def delete_file(
    path: str,
    current_user: User = Depends(get_current_user)
):
    """
    Delete a file or folder from user's storage
    """
    try:
        user_storage = get_user_storage_path(current_user.username)
        target_path = (user_storage / path.lstrip("/")).resolve()
        
        # Security: ensure path is within user storage
        if not str(target_path).startswith(str(user_storage)):
            raise HTTPException(status_code=403, detail="Access denied")
        
        if not target_path.exists():
            raise HTTPException(status_code=404, detail="Path not found")
        
        if target_path.is_file():
            target_path.unlink()
        else:
            import shutil
            shutil.rmtree(target_path)
        
        return {"message": "Deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting file: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete file")


# ============================================================================
# Minecraft Control Endpoints
# ============================================================================
def get_minecraft_status() -> MinecraftStatus:
    """
    Get Minecraft server status
    For now, returns mock data. Can be extended to check Docker container or systemd service.
    """
    # TODO: Implement actual Minecraft status check
    # This could check:
    # 1. Docker container status (if using Docker)
    # 2. systemd service status (if using host-managed)
    # 3. Query the Minecraft server directly
    
    return MinecraftStatus(
        status="stopped",
        version="1.20.4",
        players=0,
        uptime_h=0
    )


@app.get("/api/minecraft/status", response_model=MinecraftStatus)
async def minecraft_status(current_user: User = Depends(get_current_user)):
    """
    Get Minecraft server status
    """
    try:
        return get_minecraft_status()
    except Exception as e:
        logger.error(f"Error fetching Minecraft status: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch Minecraft status")


@app.post("/api/minecraft/start")
async def minecraft_start(current_user: User = Depends(get_current_user)):
    """
    Start Minecraft server (admin only)
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # TODO: Implement actual Minecraft start
        # Example for systemd:
        # subprocess.run(["systemctl", "start", "mc-server"], check=True)
        # Example for Docker:
        # docker_client.containers.get("mc-server").start()
        
        minecraft_starts.inc()
        return {"message": "Minecraft server started"}
    except Exception as e:
        logger.error(f"Error starting Minecraft: {e}")
        raise HTTPException(status_code=500, detail="Failed to start Minecraft server")


@app.post("/api/minecraft/stop")
async def minecraft_stop(current_user: User = Depends(get_current_user)):
    """
    Stop Minecraft server (admin only)
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        # TODO: Implement actual Minecraft stop
        minecraft_stops.inc()
        return {"message": "Minecraft server stopped"}
    except Exception as e:
        logger.error(f"Error stopping Minecraft: {e}")
        raise HTTPException(status_code=500, detail="Failed to stop Minecraft server")


# ============================================================================
# Executive Commands Endpoint
# ============================================================================
class ExecRequest(BaseModel):
    cmd: str


# Allowlist of safe commands
SAFE_COMMANDS = [
    "ls",
    "pwd",
    "whoami",
    "df",
    "du",
    "uptime",
    "ps",
    "top",
    "free",
    "uname",
]


@app.post("/api/exec")
async def execute_command(
    request: ExecRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Execute a safe system command (admin only, restricted allowlist)
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        cmd = request.cmd.strip()
        
        # Check if command starts with an allowed command
        allowed = any(cmd.startswith(safe_cmd) for safe_cmd in SAFE_COMMANDS)
        if not allowed:
            raise HTTPException(
                status_code=403,
                detail=f"Command not allowed. Allowed commands: {', '.join(SAFE_COMMANDS)}"
            )
        
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        return {
            "command": cmd,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Command timeout")
    except Exception as e:
        logger.error(f"Error executing command: {e}")
        raise HTTPException(status_code=500, detail="Failed to execute command")


# ============================================================================
# Interactive Terminal (WebSocket)
# ============================================================================

# Store active terminal processes globally (username -> process info)
active_terminals: Dict[str, Dict] = {}


async def get_current_user_ws(websocket: WebSocket, db: Session) -> User:
    """
    Authenticate WebSocket connection using token from query parameter
    """
    try:
        token = websocket.query_params.get("token")
        if not token:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="No token provided")
            return None
        
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
            return None
        
        user = db.query(User).filter(User.username == username).first()
        if user is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="User not found")
            return None
        
        return user
    except JWTError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
        return None


# Terminal-PTY WebSocket (lägg i main.py)
import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ptyprocess import PtyProcessUnicode

router = APIRouter()

# Kommando att starta i pty
SHELL_CMD = ["/bin/bash"]

@router.websocket("/ws/terminal")
async def terminal_ws(websocket: WebSocket):
    """
    WebSocket-Endpoint som spawnar en lokal PTY och kopplar den till websocketen.
    Förväntar sig att frontend skickar JSON-meddelanden:
      { "type": "input", "data": "<text>" }        -> skickas till PTY
      { "type": "resize", "cols": N, "rows": M }    -> justerar winsize
    Men accepterar även rå text (som input).
    """
    await websocket.accept()
    proc = None

    try:
        # Starta lokal PTY-process
        proc = PtyProcessUnicode.spawn(SHELL_CMD)
    except Exception as e:
        await websocket.send_text(f"[pty-error] Failed to spawn shell: {e}\n")
        await websocket.close()
        return

    async def pty_reader():
        try:
            # Läs från PTY i bakgrundstrådar (blocking read flyttas ut från async-loop)
            while proc.isalive():
                try:
                    data = await asyncio.to_thread(proc.read, 1024)
                except EOFError:
                    break
                if not data:
                    # väntar/loopar vidare
                    await asyncio.sleep(0.01)
                    continue
                # Skicka data till klienten (text)
                try:
                    await websocket.send_text(data)
                except Exception:
                    # websocket stängd/kunde inte skicka
                    break
        except Exception as e:
            try:
                await websocket.send_text(f"\n[pty-reader-error] {e}\n")
            except Exception:
                pass

    async def ws_reader():
        try:
            while True:
                msg = await websocket.receive_text()
                # Försök tolka som JSON, annars behandla som rå input
                parsed = None
                try:
                    parsed = json.loads(msg)
                except Exception:
                    parsed = None

                if isinstance(parsed, dict) and parsed.get("type") == "resize":
                    cols = int(parsed.get("cols", 80))
                    rows = int(parsed.get("rows", 24))
                    # setwinsize tar rows, cols (synchronous) -> kör i thread
                    await asyncio.to_thread(proc.setwinsize, rows, cols)
                elif isinstance(parsed, dict) and parsed.get("type") == "input":
                    data = parsed.get("data", "")
                    # skriv till pty i tråd
                    await asyncio.to_thread(proc.write, data)
                else:
                    # fallback: skicka rå text till pty
                    await asyncio.to_thread(proc.write, msg)
        except WebSocketDisconnect:
            # klienten stängde förbindelsen
            return
        except Exception:
            # websocket kan vara stängd; tyst avsluta
            return

    # Kör båda tasks parallellt; när en kraschar så avbryts den andra
    try:
        await asyncio.gather(pty_reader(), ws_reader())
    finally:
        # cleanup
        try:
            if proc and proc.isalive():
                try:
                    proc.terminate()
                except Exception:
                    pass
                # Ge processen en liten stund att dö ordentligt
                await asyncio.sleep(0.1)
                if proc.isalive():
                    try:
                        proc.kill(signal=None)
                    except Exception:
                        pass
        except Exception:
            pass

        try:
            await websocket.close()
        except Exception:
            pass



def set_winsize(fd: int, rows: int, cols: int):
    """Set the window size of the PTY"""
    try:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack('HHHH', rows, cols, 0, 0))
    except Exception as e:
        logger.warning(f"Failed to set terminal window size: {e}")


async def read_pty_output(proc_fd: int, user_key: str):
    """
    Async generator to read PTY output
    """
    import select
    loop = asyncio.get_event_loop()
    
    
    while user_key in active_terminals:
        try:
            # Use select to check if data is available (non-blocking)
            rlist, _, _ = select.select([proc_fd], [], [], 0.1)
            if rlist:
                data = os.read(proc_fd, 1024)
                if data:
                    yield data.decode('utf-8', errors='ignore')
                else:
                    break
            else:
                await asyncio.sleep(0.01)
        except OSError:
            break
        except Exception as e:
            logger.error(f"Error reading PTY output: {e}")
            break


@app.websocket("/api/terminal")
async def websocket_terminal(websocket: WebSocket):
    """
    WebSocket endpoint for interactive terminal
    Supports: command input/output, window resizing
    """
    db = SessionLocal()
    user = None
    user_key = None
    process = None
    
    try:
        await websocket.accept()
        
        # Authenticate user
        user = await get_current_user_ws(websocket, db)
        if not user:
            return
        
        user_key = f"{user.username}_{id(websocket)}"
        
        logger.info(f"Terminal session started for user: {user.username}")
        
        # Start shell process with PTY
        try:
            import subprocess
            
            # Start bash with stdin/stdout/stderr as pipes, will use PTY approach
            process = await asyncio.create_subprocess_exec(
                "/bin/bash",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=2**16  # 64KB buffer
            )
            
            if process:
                active_terminals[user_key] = {
                    "process": process,
                    "websocket": websocket
                }
                
                # Send initial welcome message
                await websocket.send_text("Welcome to Aurora-cloud Terminal\nType 'exit' to disconnect.\n$ ")
                
                # Create tasks for bidirectional communication
                read_task = asyncio.create_task(read_from_websocket_process(websocket, process, user_key))
                write_task = asyncio.create_task(write_to_websocket_process(websocket, process, user_key))
                
                # Wait for either task to complete (connection close or error)
                done, pending = await asyncio.wait(
                    [read_task, write_task],
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Cleanup
                for task in pending:
                    task.cancel()
                
        except Exception as e:
            logger.error(f"Error starting terminal: {e}")
            await websocket.send_text(f"\nError: {str(e)}\n")
    
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    
    finally:
        # Cleanup
        if user_key and user_key in active_terminals:
            term_info = active_terminals[user_key]
            proc = term_info.get("process")
            if proc and not proc.returncode:
                try:
                    proc.terminate()
                    await asyncio.sleep(0.5)
                    if not proc.returncode:
                        proc.kill()
                except:
                    pass
            
            del active_terminals[user_key]
        
        try:
            await websocket.close()
        except:
            pass
        
        logger.info(f"Terminal session ended for user: {user.username if user else 'unknown'}")
        db.close()


async def read_from_websocket_process(websocket: WebSocket, process: asyncio.subprocess.Process, user_key: str):
    """
    Read commands from WebSocket and write to subprocess stdin
    """
    try:
        while user_key in active_terminals:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                
                # Write command to process stdin
                if process.stdin and not process.stdin.is_closing():
                    process.stdin.write(data.encode('utf-8'))
                    await process.stdin.drain()
            
            except asyncio.TimeoutError:
                await asyncio.sleep(0.01)
            except Exception as e:
                logger.error(f"Error reading from WebSocket: {e}")
                break
    
    except Exception as e:
        logger.error(f"WebSocket read error: {e}")
    
    finally:
        if process.stdin and not process.stdin.is_closing():
            process.stdin.close()


async def write_to_websocket_process(websocket: WebSocket, process: asyncio.subprocess.Process, user_key: str):
    """
    Read output from subprocess stdout and send to WebSocket
    """
    try:
        while user_key in active_terminals:
            try:
                if process.stdout:
                    # Read data from stdout
                    data = await asyncio.wait_for(
                        process.stdout.read(4096),
                        timeout=1.0
                    )
                    
                    if data:
                        await websocket.send_text(data.decode('utf-8', errors='ignore'))
                    else:
                        # Process closed stdout
                        break
                else:
                    await asyncio.sleep(0.01)
            
            except asyncio.TimeoutError:
                await asyncio.sleep(0.01)
            except Exception as e:
                logger.error(f"Error writing to WebSocket: {e}")
                break
    
    except Exception as e:
        logger.error(f"WebSocket write error: {e}")


async def read_from_websocket(websocket: WebSocket, master_fd: int, user_key: str):
    """
    Read commands from WebSocket and write to PTY
    """
    try:
        while user_key in active_terminals:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                
                # Handle special messages (resize, etc.)
                if data.startswith("RESIZE:"):
                    try:
                        _, rows, cols = data.split(":")
                        set_winsize(master_fd, int(rows), int(cols))
                    except:
                        pass
                else:
                    # Write command to PTY
                    os.write(master_fd, data.encode('utf-8'))
            
            except asyncio.TimeoutError:
                await asyncio.sleep(0.01)
            except Exception as e:
                logger.error(f"Error reading from WebSocket: {e}")
                break
    
    except Exception as e:
        logger.error(f"WebSocket read error: {e}")


async def write_to_websocket(websocket: WebSocket, master_fd: int, user_key: str):
    """
    Read output from PTY and send to WebSocket
    """
    import select
    
    try:
        while user_key in active_terminals:
            try:
                # Non-blocking read from PTY
                rlist, _, _ = select.select([master_fd], [], [], 0.1)
                if rlist:
                    try:
                        data = os.read(master_fd, 4096)
                        if data:
                            await websocket.send_text(data.decode('utf-8', errors='ignore'))
                        else:
                            break
                    except OSError:
                        break
                else:
                    await asyncio.sleep(0.01)
            
            except Exception as e:
                logger.error(f"Error writing to WebSocket: {e}")
                break
    
    except Exception as e:
        logger.error(f"WebSocket write error: {e}")


# ============================================================================
# Prometheus Metrics Endpoint
# ============================================================================
@app.get("/metrics")
async def get_prometheus_metrics():
    """
    Expose Prometheus-compatible metrics
    """
    from fastapi.responses import Response
    return Response(generate_latest(), media_type="text/plain")


# ============================================================================
# Health Check
# ============================================================================
@app.get("/health")
async def health_check():
    """
    Health check endpoint
    """
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


# ============================================================================
# Root Endpoint
# ============================================================================
@app.get("/")
async def root():
    """
    Root endpoint with API info
    """
    return {
        "name": "Aurora-cloud Portal API",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc"
    }
