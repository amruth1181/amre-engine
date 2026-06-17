from fastapi import FastAPI, APIRouter, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
import hashlib
import jwt
from datetime import datetime, timedelta
import random
import os
import asyncio
import json
from dotenv import load_dotenv


# Load env variables at startup
load_dotenv()

# ==================== CONFIG ====================
SECRET_KEY = os.environ.get("JWT_SECRET", "secret")
DB_PATH = os.environ.get("DB_PATH", "./amre.db") # Default to local SQLite file for convenience
ALGORITHM = "HS256"


# ==================== DATABASE ====================
def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password_hash TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
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
    conn.commit()
    return conn

def hash_password(password: str):
    return hashlib.sha256(password.encode()).hexdigest()

def create_token(user_id: int):
    return jwt.encode({"user_id": user_id, "exp": datetime.now() + timedelta(days=7)}, SECRET_KEY, algorithm=ALGORITHM)

def get_user_id(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload["user_id"]
    except Exception as e:
        print(f"❌ JWT Decode failed: {e}")
        return None


# ==================== MOCK AI SOLVER ====================
def solve_problem(problem: str) -> dict:
    """Mock solver that returns intelligent-looking responses"""
    
    # Simple pattern matching for common problems
    problem_lower = problem.lower()
    
    # Linear equations: 2x + 5 = 15
    if "x" in problem_lower and "=" in problem_lower:
        # Try to extract numbers
        import re
        numbers = re.findall(r'\d+', problem)
        
        if len(numbers) >= 2:
            # Simple linear equation solver
            try:
                # 2x + 5 = 15 -> x = (15-5)/2 = 5
                if "+" in problem_lower or "-" in problem_lower:
                    left = problem.split("=")[0]
                    right = problem.split("=")[1]
                    
                    # Extract coefficient of x
                    x_match = re.search(r'(\d*)[xX]\s*([+-])\s*(\d+)', left)
                    if x_match:
                        coef = int(x_match.group(1)) if x_match.group(1) else 1
                        sign = x_match.group(2)
                        const = int(x_match.group(3))
                        right_val = int(right.strip())
                        
                        if sign == '+':
                            x = (right_val - const) / coef
                        else:
                            x = (right_val + const) / coef
                        
                        answer = str(int(x)) if x.is_integer() else str(round(x, 2))
                        confidence = 0.92
                        steps = f"Step 1: Move constants to the right side\nStep 2: Divide both sides by {coef}\nStep 3: x = {answer}"
                        
                        return {
                            "answer": answer,
                            "chains": [{"text": steps, "score": 0.92}],
                            "confidence": 0.92
                        }
            except:
                pass
    
    # Quadratic equations
    if "x²" in problem_lower or "x^2" in problem_lower:
        return {
            "answer": "x = -2 or x = -3",
            "chains": [{"text": "Step 1: Factor the quadratic\nStep 2: (x+2)(x+3) = 0\nStep 3: x = -2 or x = -3", "score": 0.88}],
            "confidence": 0.88
        }
    
    # Fractions
    if "/" in problem_lower and ("+" in problem_lower or "-" in problem_lower):
        return {
            "answer": "11/12",
            "chains": [{"text": "Step 1: Find common denominator (12)\nStep 2: Convert both fractions\nStep 3: Add numerators", "score": 0.85}],
            "confidence": 0.85
        }
    
    # Default: generic algebra
    return {
        "answer": "5",
        "chains": [{"text": "Step 1: Simplify the equation\nStep 2: Isolate the variable\nStep 3: Solve for the variable", "score": 0.80}],
        "confidence": 0.80
    }

# ==================== AUTH ROUTER ====================
auth_router = APIRouter()

class UserCreate(BaseModel):
    username: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

@auth_router.post("/register")
def register(user: UserCreate):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM users WHERE username = ?", (user.username,))
    if cursor.fetchone():
        raise HTTPException(400, "Username already exists")
    
    hashed = hash_password(user.password)
    cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (user.username, hashed))
    conn.commit()
    user_id = cursor.lastrowid
    conn.close()
    
    return {"user_id": user_id, "token": create_token(user_id)}

@auth_router.post("/login")
def login(user: UserLogin):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, password_hash FROM users WHERE username = ?", (user.username,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(401, "Invalid credentials")
    
    if hash_password(user.password) != row["password_hash"]:
        raise HTTPException(401, "Invalid credentials")
    
    return {"user_id": row["id"], "token": create_token(row["id"])}

# ==================== SOLVE ROUTER ====================
solve_router = APIRouter()

class SolveRequest(BaseModel):
    problem: str
    mode: str = "balanced"

class SolveResponse(BaseModel):
    answer: str
    confidence: float
    route: str
    n_used: int
    chains: List[dict]

class CheckRequest(BaseModel):
    problem: str
    solution_text: str

@solve_router.post("/")
def solve(request: SolveRequest, authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(401, "No token provided")
    
    token = authorization.replace("Bearer ", "")
    user_id = get_user_id(token)
    if not user_id:
        raise HTTPException(401, "Invalid token")
    
    # Get solution from mock solver
    result = solve_problem(request.problem)
    
    answer = result.get("answer", "5")
    confidence = result.get("confidence", 0.85)
    chains = result.get("chains", [{"text": "Solving...", "score": 0.80}])
    n_used = 8
    
    # Save to history
    conn = get_db()
    c = conn.cursor()
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
        chains=chains
    )

@solve_router.post("/checkwork")
async def checkwork(request: CheckRequest, authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(401, "No token provided")
    
    token = authorization.replace("Bearer ", "")
    user_id = get_user_id(token)
    if not user_id:
        raise HTTPException(401, "Invalid token")
        
    import segment
    import prm_scoring
    import generate
    
    # 1. Segment user solution text into steps
    steps = segment.segment_steps(request.solution_text)
    if not steps:
        raise HTTPException(400, "Could not identify distinct reasoning steps in your solution.")
        
    # 2. Score these steps
    scores = []
    badges = []
    try:
        prm_res = prm_scoring.score_steps(request.problem, steps)
        scores = prm_res["scores"]
        badges = prm_res["badges"]
    except Exception as e:
        print(f"Error scoring checkwork: {e}")
        scores = [0.5] * len(steps)
        badges = ["amber"] * len(steps)
        
    # 3. Locate the error step (weakest link)
    error_step_idx = 0
    if scores:
        error_step_idx = int(min(range(len(scores)), key=lambda i: scores[i]))
        
    # 4. Generate the tutor explanation using OpenRouter
    explanation = await generate.explain_error(request.problem, steps, error_step_idx)
    
    return {
        "steps": steps,
        "scores": scores,
        "badges": badges,
        "error_step": error_step_idx + 1,  # 1-indexed for the user display
        "explanation": explanation
    }
# ==================== HISTORY ROUTER ====================
history_router = APIRouter()

@history_router.get("/")
def get_history(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(401, "No token provided")
    
    token = authorization.replace("Bearer ", "")
    user_id = get_user_id(token)
    if not user_id:
        raise HTTPException(401, "Invalid token")
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT timestamp, problem, answer, confidence, mode, n_used FROM history WHERE user_id = ? ORDER BY id DESC LIMIT 20", (user_id,))
    rows = c.fetchall()
    conn.close()
    
    history = []
    for row in rows:
        history.append({
            "timestamp": row["timestamp"],
            "problem": row["problem"],
            "answer": row["answer"],
            "confidence": row["confidence"],
            "mode": row["mode"],
            "n_used": row["n_used"]
        })
    return {"history": history}

# ==================== MAIN APP ====================
app = FastAPI(title="AMRE Engine", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/auth", tags=["Auth"])
app.include_router(solve_router, prefix="/solve", tags=["Solve"])
app.include_router(history_router, prefix="/history", tags=["History"])

@app.get("/health")
def health():
    return {"status": "ok", "message": "Engine is running!"}

@app.get("/")
def root():
    return {"message": "AMRE Engine is running!", "status": "ok"}

@app.websocket("/ws/solve")
async def websocket_solve(websocket: WebSocket):
    await websocket.accept()
    try:
        # 1. Receive request parameters
        data = await websocket.receive_text()
        request = json.loads(data)
        
        problem = request.get("problem")
        mode = request.get("mode", "balanced")
        token = request.get("token")
        
        # 2. Authenticate
        user_id = None
        if token:
            user_id = get_user_id(token)
            
        if not user_id:
            await websocket.send_json({"type": "error", "message": "Unauthorized / Invalid token"})
            await websocket.close()
            return
            
        # 3. Route problem (select strategy, n, temperature)
        import router
        route_info = router.route_problem(problem, mode)
        await websocket.send_json({
            "type": "route",
            "strategy": route_info.strategy,
            "n": route_info.n
        })
        
        # 4. Generate candidate chains
        import generate
        import prm_scoring
        import httpx
        
        chains = []
        limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
        
        async with httpx.AsyncClient(limits=limits) as client:
            tasks = [
                generate.generate_single_chain(client, problem, route_info.temperature)
                for _ in range(route_info.n)
            ]
            
            # Execute concurrently and stream events as they complete
            for chain_id, future in enumerate(asyncio.as_completed(tasks)):
                chain = await future
                steps = chain.get("steps", [])
                
                # Stream individual steps
                for step_idx, step_text in enumerate(steps):
                    await websocket.send_json({
                        "type": "step",
                        "chain_id": chain_id,
                        "step_idx": step_idx,
                        "latex": step_text
                    })
                
                # Score steps using PRM
                if steps:
                    try:
                        prm_res = prm_scoring.score_steps(problem, steps)
                        chain["scores"] = prm_res["scores"]
                        chain["badges"] = prm_res["badges"]
                        
                        # Stream scores
                        for step_idx, (score, badge) in enumerate(zip(prm_res["scores"], prm_res["badges"])):
                            band = badge.split("|")[0]  # strip any suffixes like |weakest_link
                            await websocket.send_json({
                                "type": "score",
                                "chain_id": chain_id,
                                "step_idx": step_idx,
                                "score": score,
                                "band": band
                            })
                    except Exception as e:
                        print(f"Error scoring chain {chain_id}: {e}")
                        chain["scores"] = [0.5] * len(steps)
                        chain["badges"] = ["amber"] * len(steps)
                        
                        for step_idx in range(len(steps)):
                            await websocket.send_json({
                                "type": "score",
                                "chain_id": chain_id,
                                "step_idx": step_idx,
                                "score": 0.5,
                                "band": "amber"
                            })
                else:
                    chain["scores"] = []
                    chain["badges"] = []
                    
                await websocket.send_json({
                    "type": "chain_done",
                    "chain_id": chain_id,
                    "answer": chain.get("answer", "Error")
                })
                
                chains.append(chain)
                
        # 5. Consensus & voting
        import consensus
        best_answer, confidence, tally = consensus.run_consensus(chains)
        
        # Stream vote tally
        await websocket.send_json({
            "type": "vote",
            "tally": tally,
            "agreement": confidence
        })
        
        # Find weakest step across all reasoning chains
        weakest_chain_id = 0
        weakest_step_idx = 0
        min_score = 1.0
        
        for chain_idx, chain in enumerate(chains):
            for step_idx, score in enumerate(chain.get("scores", [])):
                if score < min_score:
                    min_score = score
                    weakest_chain_id = chain_idx
                    weakest_step_idx = step_idx
                    
        # Save solving event to history database
        conn = get_db()
        c = conn.cursor()
        c.execute(
            "INSERT INTO history (user_id, timestamp, problem, answer, confidence, mode, n_used) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, datetime.now().isoformat(), problem, best_answer, confidence, mode, route_info.n)
        )
        conn.commit()
        conn.close()
        
        # Send final payload
        await websocket.send_json({
            "type": "final",
            "answer": best_answer,
            "confidence": confidence,
            "weakest": {
                "chain": weakest_chain_id,
                "step": weakest_step_idx
            }
        })
        
    except WebSocketDisconnect:
        print("WebSocket client disconnected")
    except Exception as e:
        print(f"Error in websocket handler: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
            pass

