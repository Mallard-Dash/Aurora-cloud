import os
import json
import boto3
import logging
import psutil
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from .dependencies import get_current_user, User

router = APIRouter(prefix="/api/borealis", tags=["Borealis AI"])
logger = logging.getLogger(__name__)

# AWS Setup
REGION = os.getenv("BEDROCK_REGION", "us-east-1")
bedrock = boto3.client(service_name="bedrock-runtime", region_name=REGION)
MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

def get_system_context():
    """Hämtar systemstatus för att ge AI:n grounding"""
    try:
        cpu = psutil.cpu_percent(interval=0.1)
        ram = psutil.virtual_memory().percent
        disk = psutil.disk_usage('/').percent
        uptime_s = psutil.boot_time()
        import time
        uptime_days = round((time.time() - uptime_s) / 86400, 1)
        return f"SYSTEM STATUS -> CPU: {cpu}%, RAM: {ram}%, DISK: {disk}%, UPTIME: {uptime_days} days."
    except:
        return "SYSTEM STATUS -> Unknown (Error reading stats)"

@router.post("/chat")
async def chat_endpoint(req: ChatRequest, user: User = Depends(get_current_user)):
    try:
        # 1. Hämta live-data från servern
        system_stats = get_system_context()
        
        # 2. Skapa System Prompt med kontext
        base_prompt = (
            f"You are Borealis, an integrated AI for the Aurora Server Portal. "
            f"Current Server Telemetry: [{system_stats}]. "
            f"User is {user.username}. Answer technical questions about this server briefly."
        )

        # 3. Payload till Claude 3
        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1000,
            "system": base_prompt,
            "messages": [{"role": "user", "content": req.message}]
        }

        response = bedrock.invoke_model(
            modelId=MODEL_ID,
            body=json.dumps(payload)
        )

        result_body = json.loads(response.get("body").read())
        ai_reply = result_body["content"][0]["text"]

        return {"response": ai_reply, "session_id": req.session_id or "new"}

    except Exception as e:
        logger.error(f"Borealis Error: {str(e)}")
        return {"response": f"⚠ AI Error: {str(e)}", "session_id": req.session_id}
