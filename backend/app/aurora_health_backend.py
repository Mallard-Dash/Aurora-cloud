import os
import json
import boto3
from typing import List, Optional
from datetime import datetime, date

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import create_engine, Column, Integer, String, Float, Date, Text
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from dotenv import load_dotenv

# Ladda env
load_dotenv()

# --- Router Setup ---
# VIKTIGT: Prefixet här matchar exakt vad frontend anropar (/api/health-service)
router = APIRouter(prefix="/api/health-service", tags=["Aurora Health AI"])

# --- Konfiguration ---
# Vi sparar databasen i samma mapp som appen
DATABASE_URL = "sqlite:///./aurora_health.db"
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v2:0") 

# --- Database Setup ---
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- Modeller ---
class DailyLog(Base):
    __tablename__ = "daily_logs"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, default=date.today)
    weight = Column(Float, nullable=True)
    waist = Column(Float, nullable=True)
    pulse = Column(Integer, nullable=True)
    sys_bp = Column(Integer, nullable=True)
    dia_bp = Column(Integer, nullable=True)
    steps = Column(Integer, nullable=True)
    stress_level = Column(Integer, nullable=True)
    symptoms = Column(String, nullable=True)
    notes = Column(Text, nullable=True)

# Skapa tabell
Base.metadata.create_all(bind=engine)

# --- Schemas ---
class LogCreate(BaseModel):
    weight: Optional[float] = None
    waist: Optional[float] = None
    pulse: Optional[int] = None
    sys_bp: Optional[int] = None
    dia_bp: Optional[int] = None
    steps: Optional[int] = None
    stress: Optional[int] = None
    symptoms: List[str] = []
    symptomNote: Optional[str] = None

class LogResponse(LogCreate):
    id: int
    date: date
    model_config = ConfigDict(from_attributes=True)

class AnalysisRequest(BaseModel):
    context: Optional[str] = None

# --- AWS Klient ---
try:
    # Försöker hämta klienten. Den lånar credentials från main-appens miljö.
    bedrock_runtime = boto3.client('bedrock-runtime', region_name=AWS_REGION)
except Exception as e:
    print(f"⚠️ Aurora Health: Kunde inte initiera AWS. {e}")
    bedrock_runtime = None

# --- Dependency ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Endpoints ---

@router.post("/log", response_model=LogResponse)
def create_log(log: LogCreate, db: Session = Depends(get_db)):
    db_log = DailyLog(
        weight=log.weight, waist=log.waist, pulse=log.pulse,
        sys_bp=log.sys_bp, dia_bp=log.dia_bp, steps=log.steps,
        stress_level=log.stress, notes=log.symptomNote,
        symptoms=",".join(log.symptoms) if log.symptoms else ""
    )
    db.add(db_log)
    db.commit()
    db.refresh(db_log)
    
    res = LogResponse.model_validate(db_log)
    res.symptoms = db_log.symptoms.split(",") if db_log.symptoms else []
    res.symptomNote = db_log.notes
    return res

@router.get("/history", response_model=List[LogResponse])
def get_history(limit: int = 30, db: Session = Depends(get_db)):
    logs = db.query(DailyLog).order_by(DailyLog.date.desc()).limit(limit).all()
    results = []
    for log in logs:
        res = LogResponse.model_validate(log)
        res.symptoms = log.symptoms.split(",") if log.symptoms else []
        res.symptomNote = log.notes
        results.append(res)
    return results

@router.post("/analyze")
def analyze_health(request: AnalysisRequest, db: Session = Depends(get_db)):
    if not bedrock_runtime:
        return {"analysis": "AI-tjänsten är inte aktiv (Saknar AWS-credentials i main app)."}

    logs = db.query(DailyLog).order_by(DailyLog.date.desc()).limit(14).all()
    if not logs:
        return {"analysis": "Logga lite mer data först!"}

    history_text = "\n".join([f"- {l.date}: BP {l.sys_bp}/{l.dia_bp}, Puls {l.pulse}, Stress {l.stress_level}, Notis: {l.notes}" for l in logs])
    
    prompt = f"""
    Analysera denna hälsodata (Senaste 14 dagar):
    {history_text}
    
    Patientkontext: {request.context or 'Ingen'}
    
    Ge kortfattade, lugnande och konkreta råd på svenska. Identifiera trender.
    """

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": prompt}]
    })

    try:
        response = bedrock_runtime.invoke_model(modelId=BEDROCK_MODEL_ID, body=body)
        result = json.loads(response.get("body").read())
        return {"analysis": result["content"][0]["text"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Error: {str(e)}")