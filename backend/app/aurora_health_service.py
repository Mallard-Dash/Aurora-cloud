import os
import json
import boto3
from typing import List, Optional
from datetime import datetime, date

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
from sqlalchemy import create_engine, Column, Integer, String, Float, Date, Text
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from dotenv import load_dotenv

# Ladda miljövariabler
load_dotenv()

# --- Konfiguration ---
# Databasen sparas lokalt i mappen där tjänsten körs
DATABASE_URL = "sqlite:///./health_data.db"
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
# Claude 3.5 Sonnet ID (som du angav)
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v2:0") 

# --- Database Setup (SQLite) ---
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- Databasmodeller ---
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

# Skapa tabeller automatiskt vid start
Base.metadata.create_all(bind=engine)

# --- API Schemas ---
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
    bedrock_runtime = boto3.client('bedrock-runtime', region_name=AWS_REGION)
except Exception as e:
    print(f"Varning: Kunde inte initiera AWS Bedrock klient. AI-funktionen kommer inte fungera. Fel: {e}")
    bedrock_runtime = None

app = FastAPI(title="Aurora Health API")

# CORS (Tillåter anrop från frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Endpoints ---

@app.post("/api/log", response_model=LogResponse)
def create_log(log: LogCreate, db: Session = Depends(get_db)):
    """Sparar daglig hälsodata"""
    db_log = DailyLog(
        weight=log.weight, waist=log.waist, pulse=log.pulse,
        sys_bp=log.sys_bp, dia_bp=log.dia_bp, steps=log.steps,
        stress_level=log.stress, notes=log.symptomNote,
        symptoms=",".join(log.symptoms) if log.symptoms else ""
    )
    db.add(db_log)
    db.commit()
    db.refresh(db_log)
    
    response = LogResponse.model_validate(db_log)
    response.symptoms = db_log.symptoms.split(",") if db_log.symptoms else []
    response.symptomNote = db_log.notes
    return response

@app.get("/api/history", response_model=List[LogResponse])
def get_history(limit: int = 30, db: Session = Depends(get_db)):
    """Hämtar historik"""
    logs = db.query(DailyLog).order_by(DailyLog.date.desc()).limit(limit).all()
    results = []
    for log in logs:
        pydantic_log = LogResponse.model_validate(log)
        pydantic_log.symptoms = log.symptoms.split(",") if log.symptoms else []
        pydantic_log.symptomNote = log.notes
        results.append(pydantic_log)
    return results

@app.post("/api/analyze")
def analyze_health(request: AnalysisRequest, db: Session = Depends(get_db)):
    """Skickar data till AWS Bedrock för analys"""
    if not bedrock_runtime:
        return {"analysis": "AWS Bedrock är inte konfigurerat på servern."}

    logs = db.query(DailyLog).order_by(DailyLog.date.desc()).limit(14).all()
    if not logs:
        return {"analysis": "För lite data för en analys. Logga några värden först!"}

    history_text = "\n".join([f"- {l.date}: BP {l.sys_bp}/{l.dia_bp}, Puls {l.pulse}, Stress {l.stress_level}, Anteckning: {l.notes}" for l in logs])
    
    prompt = f"""
    Agera som en professionell läkare och hälsocoach. Analysera följande data:
    
    DATA SENASTE 14 DAGARNA:
    {history_text}
    
    ANVÄNDARENS KONTEXT JUST NU:
    {request.context if request.context else 'Ingen specifik kontext.'}
    
    Uppgift:
    1. Identifiera trender (stress vs blodtryck etc).
    2. Ge lugnande och konkreta råd.
    3. Svara på svenska med bra formatering.
    """

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1500,
        "messages": [{"role": "user", "content": prompt}]
    })

    try:
        response = bedrock_runtime.invoke_model(modelId=BEDROCK_MODEL_ID, body=body)
        response_body = json.loads(response.get("body").read())
        return {"analysis": response_body.get("content")[0].get("text")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    # VIKTIGT: Lyssnar på port 8050 som Nginx förväntar sig
    uvicorn.run(app, host="0.0.0.0", port=8050)