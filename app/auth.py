"""
Auth & users (IMPLEMENTATION.md §3.9).
Passwords hashed with bcrypt; a signed JWT is the opaque session token.
All data endpoints derive user_id from the token — never trust a client id.
"""
import os
from datetime import datetime, timedelta

import bcrypt
import jwt
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from . import db

SECRET_KEY = os.environ.get("JWT_SECRET", "change-me-in-prod")
ALGORITHM = "HS256"

router = APIRouter()


class UserCreate(BaseModel):
    username: str
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, pw_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), pw_hash.encode())
    except (ValueError, TypeError):
        return False


def create_token(user_id: int) -> str:
    return jwt.encode(
        {"user_id": user_id, "exp": datetime.utcnow() + timedelta(days=7)},
        SECRET_KEY, algorithm=ALGORITHM,
    )


def decode_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload["user_id"]
    except Exception as e:  # noqa: BLE001
        print(f"❌ JWT decode failed: {e}")
        return None


def require_user(authorization: str) -> int:
    """Extract and validate the bearer token, returning user_id or raising 401."""
    if not authorization:
        raise HTTPException(401, "No token provided")
    token = authorization.replace("Bearer ", "").strip()
    user_id = decode_token(token)
    if not user_id:
        raise HTTPException(401, "Invalid token")
    return user_id


@router.post("/register")
def register(user: UserCreate):
    conn = db.get_db()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE username = ?", (user.username,))
    if c.fetchone():
        conn.close()
        raise HTTPException(400, "Username already exists")
    c.execute(
        "INSERT INTO users (username, pw_hash) VALUES (?, ?)",
        (user.username, hash_password(user.password)),
    )
    conn.commit()
    user_id = c.lastrowid
    conn.close()
    return {"user_id": user_id, "token": create_token(user_id)}


@router.post("/login")
def login(user: UserLogin):
    conn = db.get_db()
    c = conn.cursor()
    c.execute("SELECT user_id, pw_hash FROM users WHERE username = ?", (user.username,))
    row = c.fetchone()
    conn.close()
    if not row or not verify_password(user.password, row["pw_hash"]):
        raise HTTPException(401, "Invalid credentials")
    return {"user_id": row["user_id"], "token": create_token(row["user_id"])}
