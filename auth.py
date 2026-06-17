from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime, timedelta
import sqlite3
import bcrypt
import jwt
import os

router = APIRouter()
SECRET_KEY = "secret"
ALGORITHM = "HS256"

class UserCreate(BaseModel):
    username: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

def get_db():
    conn = sqlite3.connect("amre.db")
    conn.row_factory = sqlite3.Row
    return conn

def create_token(user_id: int):
    return jwt.encode({"user_id": user_id, "exp": datetime.now() + timedelta(days=7)}, SECRET_KEY, algorithm=ALGORITHM)

@router.post("/register")
def register(user: UserCreate):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM users WHERE username = ?", (user.username,))
    if cursor.fetchone():
        raise HTTPException(400, "Username already exists")
    
    hashed = bcrypt.hashpw(user.password.encode(), bcrypt.gensalt()).decode()
    cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (user.username, hashed))
    conn.commit()
    user_id = cursor.lastrowid
    conn.close()
    
    return {"user_id": user_id, "token": create_token(user_id)}

@router.post("/login")
def login(user: UserLogin):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, password_hash FROM users WHERE username = ?", (user.username,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(401, "Invalid credentials")
    
    if not bcrypt.checkpw(user.password.encode(), row["password_hash"].encode()):
        raise HTTPException(401, "Invalid credentials")
    
    return {"user_id": row["id"], "token": create_token(row["id"])}
