from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
import jwt
from datetime import datetime

router = APIRouter()
SECRET_KEY = "secret"
ALGORITHM = "HS256"

class SolveRequest(BaseModel):
    problem: str
    mode: str = "balanced"

class SolveResponse(BaseModel):
    answer: str
    confidence: float
    route: str
    n_used: int
    chains: List[dict]

def get_user_id(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload["user_id"]
    except:
        return None

def get_db():
    conn = sqlite3.connect("amre.db")
    conn.row_factory = sqlite3.Row
    return conn

@router.post("/")
def solve(request: SolveRequest, authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(401, "No token provided")
    
    token = authorization.replace("Bearer ", "")
    user_id = get_user_id(token)
    if not user_id:
        raise HTTPException(401, "Invalid token")
    
    answer = "5"
    confidence = 0.85
    n_used = 8
    
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            timestamp TEXT,
            problem TEXT,
            answer TEXT,
            confidence REAL,
            mode TEXT,
            n_used INTEGER
        )
    ''')
    c.execute(
        "INSERT INTO history (user_id, timestamp, problem, answer, confidence, mode, n_used) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, datetime.now().isoformat(), request.problem, answer, confidence, request.mode, n_used)
    )
    conn.commit()
    conn.close()
    
    return SolveResponse(
        answer=answer,
        confidence=confidence,
        route=request.mode,
        n_used=n_used,
        chains=[{"text": "Step 1: Subtract 5 from both sides\nStep 2: Divide both sides by 2\nStep 3: x = 5", "score": 0.9}]
    )
