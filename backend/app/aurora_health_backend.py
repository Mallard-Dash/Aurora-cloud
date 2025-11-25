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

# Vi behöver veta vem som är inloggad
from .dependencies import get_current_user, User

load_dotenv()

router = APIRouter(prefix="/api/health-service", tags=["Aurora Health AI"])

# --- Config ---
# Vi försöker spara databasen persistent
DB_PATH = "/var/aurora_data/aurora_health.db"
if not os.path.exists(os.path.dirname(DB_PATH)):
    DB_PATH = "./aurora_health.db"

DATABASE_URL = f"sqlite:///{DB_PATH}"
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v2:0") 

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- Models ---
class DailyLog(Base):
    __tablename__ = "daily_logs"
    id = Column(Integer, primary_key=True, index=True)
    owner = Column(String, index=True) # <-- Separerar användardata
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

class UserProfile(Base):
    __tablename__ = "user_profile"
    id = Column(Integer, primary_key=True, index=True)
    owner = Column(String, unique=True, index=True) # <-- En profil per användare
    name = Column(String, default="User")
    age = Column(Integer, nullable=True)
    gender = Column(String, nullable=True)
    history = Column(Text, nullable=True)
    lifestyle = Column(Text, nullable=True)
    medication = Column(Text, nullable=True)

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
    owner: str
    model_config = ConfigDict(from_attributes=True)

class ProfileModel(BaseModel):
    name: str
    age: Optional[int] = None
    gender: Optional[str] = "Other"
    history: Optional[str] = ""
    lifestyle: Optional[str] = ""
    medication: Optional[str] = ""
    model_config = ConfigDict(from_attributes=True)

class AnalysisRequest(BaseModel):
    context: Optional[str] = None

# --- AWS Client ---
try:
    bedrock_runtime = boto3.client('bedrock-runtime', region_name=AWS_REGION)
except Exception as e:
    print(f"⚠️ Aurora Health: AWS Init Failed. {e}")
    bedrock_runtime = None

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Endpoints ---

@router.get("/profile", response_model=ProfileModel)
def get_profile(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # Hämta ENDAST den inloggade användarens profil
    profile = db.query(UserProfile).filter(UserProfile.owner == user.username).first()
    if not profile:
        return ProfileModel(name=user.username, age=0, gender="", history="", lifestyle="", medication="")
    return profile

@router.post("/profile", response_model=ProfileModel)
def update_profile(profile_data: ProfileModel, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    profile = db.query(UserProfile).filter(UserProfile.owner == user.username).first()
    if not profile:
        profile = UserProfile(owner=user.username)
        db.add(profile)
    
    profile.name = profile_data.name
    profile.age = profile_data.age
    profile.gender = profile_data.gender
    profile.history = profile_data.history
    profile.lifestyle = profile_data.lifestyle
    profile.medication = profile_data.medication
    
    db.commit()
    db.refresh(profile)
    return profile

@router.post("/log", response_model=LogResponse)
def create_log(log: LogCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db_log = DailyLog(
        owner=user.username, # Koppla loggen till användaren
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
def get_history(limit: int = 30, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # Hämta ENDAST loggar för denna användare
    logs = db.query(DailyLog).filter(DailyLog.owner == user.username).order_by(DailyLog.date.desc()).limit(limit).all()
    results = []
    for log in logs:
        res = LogResponse.model_validate(log)
        res.symptoms = log.symptoms.split(",") if log.symptoms else []
        res.symptomNote = log.notes
        results.append(res)
    return results

@router.post("/analyze")
def analyze_health(request: AnalysisRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not bedrock_runtime:
        return {"analysis": "AI service unavailable (Missing AWS Credentials)."}

    profile = db.query(UserProfile).filter(UserProfile.owner == user.username).first()
    profile_text = "Unknown Profile"
    if profile:
        profile_text = f"{profile.age} years, {profile.gender}. History: {profile.history}. Meds: {profile.medication}"

    logs = db.query(DailyLog).filter(DailyLog.owner == user.username).order_by(DailyLog.date.desc()).limit(14).all()
    if not logs:
        return {"analysis": "Not enough data logged yet."}

    history_text = "\n".join([f"- {l.date}: BP {l.sys_bp}/{l.dia_bp}, Pulse {l.pulse}, Stress {l.stress_level}, Note: {l.notes}" for l in logs])
    
    prompt = f"""
    You are an expert medical AI consultant.
    
    USER PROFILE ({user.username}):
    {profile_text}
    
    DATA (LAST 14 DAYS):
    {history_text}
    
    CONTEXT:
    {request.context or 'None.'}
    
    TASK:
    1. Analyze trends specifically for this user.
    2. Provide personalized advice.
    3. Respond in English, professional yet supportive.
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