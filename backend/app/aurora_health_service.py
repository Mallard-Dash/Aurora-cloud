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

# Ladda miljövariabler (från .env fil eller Docker environment)
load_dotenv()

# --- Konfiguration ---
DATABASE_URL = "sqlite:///./health_data.db"
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v2:0") 

# --- Database Setup ---
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
    symptoms = Column(String, nullable=True) # Sparas som kommaseparerad sträng
    notes = Column(Text, nullable=True)

# Skapa tabeller om de inte finns
Base.metadata.create_all(bind=engine)

# --- Pydantic Schemas (För API Validering) ---
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

# --- AWS Klient Initiering ---
try:
    bedrock_runtime = boto3.client(
        'bedrock-runtime', 
        region_name=AWS_REGION
        # Nycklar hämtas automatiskt från environment variables (Docker/System)
    )
    print("✅ AWS Bedrock klient initierad.")
except Exception as e:
    print(f"⚠️ Varning: Kunde inte initiera AWS Bedrock. AI-funktioner inaktiverade. Fel: {e}")
    bedrock_runtime = None

app = FastAPI(title="Aurora Health API")

# CORS Setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency för databaskoppling
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- API ENDPOINTS ---

@app.get("/")
def health_check():
    """Enkel check för att se att containern lever"""
    return {"status": "Aurora Health Service is Online", "ai_status": "Active" if bedrock_runtime else "Inactive"}

# VIKTIGT: Inget "api/" prefix här. Nginx har redan tagit bort det.
@app.post("/log", response_model=LogResponse)
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
    
    # Konvertera tillbaka databas-objekt till Pydantic-respons
    response = LogResponse.model_validate(db_log)
    response.symptoms = db_log.symptoms.split(",") if db_log.symptoms else []
    response.symptomNote = db_log.notes
    return response

@app.get("/history", response_model=List[LogResponse])
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

@app.post("/analyze")
def analyze_health(request: AnalysisRequest, db: Session = Depends(get_db)):
    """AI-Analys via AWS Bedrock"""
    if not bedrock_runtime:
        return {"analysis": "⚠️ AI-modulen är offline (saknar AWS-nycklar)."}

    # Hämta de senaste 14 dagarna för analys
    logs = db.query(DailyLog).order_by(DailyLog.date.desc()).limit(14).all()
    
    if not logs:
        return {"analysis": "Det finns för lite data loggad för att göra en analys. Lägg in dagens värden först!"}

    # Bygg en textsträng av historiken
    history_text = "\n".join([
        f"- {l.date}: BP {l.sys_bp}/{l.dia_bp}, Puls {l.pulse}, Stress {l.stress_level}/10, Vikt {l.weight}, Notis: {l.notes}" 
        for l in logs
    ])
    
    prompt = f"""
    Du är en erfaren läkare och hälsocoach. Analysera följande hälsodata för en patient:

    DATA SENASTE 14 DAGARNA:
    {history_text}

    PATIENTENS STATUS JUST NU:
    {request.context if request.context else 'Ingen specifik kommentar.'}

    Ditt uppdrag:
    1. Leta efter trender (t.ex. koppling mellan stress och puls/blodtryck).
    2. Ge 2-3 konkreta, korta råd baserat på datan.
    3. Håll tonen professionell, lugnande och stöttande. Svara på svenska.
    """

    payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": prompt}]
    }

    try:
        response = bedrock_runtime.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            body=json.dumps(payload)
        )
        response_body = json.loads(response.get("body").read())
        return {"analysis": response_body["content"][0]["text"]}
    except Exception as e:
        print(f"AWS Bedrock Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Kunde inte generera AI-analys just nu.")

if __name__ == "__main__":
    import uvicorn
    # Lyssnar på alla interfaces (0.0.0.0) för Docker-kompatibilitet
    uvicorn.run(app, host="0.0.0.0", port=8050)