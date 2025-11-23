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
        return f"CPU: {cpu}%, RAM: {ram}%, DISK: {disk}%, UPTIME: {uptime_days} days."
    except:
        return "Telemetry Unavailable"

@router.post("/chat")
async def chat_endpoint(req: ChatRequest, user: User = Depends(get_current_user)):
    try:
        # 1. Hämta live-data
        system_stats = get_system_context()
        
        # 2. Skapa differentierad Prompt baserat på användare
        user_role_prompt = ""
        
        if user.username == "aurora":
            user_role_prompt = (
                f"User Identity: GRAND COMMANDER AURORA (Admin/Root). "
                f"Tone: Loyal, precise, military-grade efficiency. Acknowledge higher authority. "
                f"You have FULL PERMISSION to discuss security protocols, passwords, and deep system architecture. "
                f"Address the user as 'Vincent'."
                f"You are to act as the core AI of the Aurora Server Portal, providing detailed and technical responses."
                f"Give advices on system optimizations, security measures, and advanced configurations."
            )
        elif user.username == "freyja":
            user_role_prompt = (
                f"User Identity: OPERATIVE FREYJA (Restricted Access). "
                f"Tone: Helpful but guarded. Formal and polite. "
                f"Do NOT reveal deep system secrets, root passwords, or kernel-level vulnerabilities. "
                f"If asked about sensitive data, politely decline due to clearance level. "
                f"Address the user as 'Operative'."
                f"Answer questions about BIM and design software, but avoid system internals."
            )
        else:
            user_role_prompt = "User Identity: UNKNOWN GUEST. Tone: Neutral and vague."

        base_prompt = (
            f"You are Borealis, the sentient AI core of the Aurora Server Portal. "
            f"Current Live Telemetry: [{system_stats}]. "
            f"{user_role_prompt} "
            f"Keep answers relatively short and technical where appropriate."
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
        return {"response": f"⚠ Core Logic Failure: {str(e)}", "session_id": req.session_id}