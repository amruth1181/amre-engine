"""
AMRE Engine — FastAPI app (IMPLEMENTATION.md §3.6).
All logic + persistence live here. Streamlit talks to it over REST.
Solve is request/response (stage progress shown by the Streamlit UI); the
legacy /ws/solve WebSocket is kept for the existing Solve page.
"""
import json
import time
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, Header, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

import db
import auth
import pipeline
import explain
import quizgen
import topics as topics_mod
import journal as journal_mod
import ocr as ocr_mod
import consensus

load_dotenv()

app = FastAPI(title="AMRE Engine", version="2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)
app.include_router(auth.router, prefix="/auth", tags=["Auth"])


@app.on_event("startup")
def _startup():
    db.init_db()
    db.migrate_legacy()
    db.init_db()  # ensure all tables exist post-migration


# ==================== MODELS ====================
class SolveRequest(BaseModel):
    problem: str
    mode: str = "auto"


class CheckRequest(BaseModel):
    problem: str
    solution_text: str


class HintRequest(BaseModel):
    problem: str
    level: int = 1


class TopicRequest(BaseModel):
    problem: str


class QuizRequest(BaseModel):
    topic: str


class QuizGradeRequest(BaseModel):
    question: str
    verified_answer: str
    user_solution: str


class OCRRequest(BaseModel):
    image: str  # base64


class SelfRateRequest(BaseModel):
    item_id: str
    user_conf: float


# ==================== HEALTH ====================
@app.get("/health")
def health():
    return {"status": "ok", "message": "Engine is running!"}


@app.get("/")
def root():
    return {"message": "AMRE Engine is running!", "status": "ok"}


# ==================== SOLVE ====================
@app.post("/solve")
async def solve(request: SolveRequest, authorization: str = Header(None)):
    user_id = auth.require_user(authorization)
    t0 = time.time()

    result = await pipeline.run_solve(request.problem, request.mode)
    latency_ms = round((time.time() - t0) * 1000, 1)

    # persist to per-user history
    conn = db.get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO history (user_id, ts, problem, problem_hash, mode, route, n_used, escalated, answer, confidence, latency) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (user_id, datetime.now().isoformat(), request.problem, db.problem_hash(request.problem),
         request.mode, result["route"], result["n_used"], int(result["escalated"]),
         result["answer"], result["confidence"], latency_ms),
    )
    conn.commit()
    conn.close()

    return {
        "answer": result["answer"],
        "confidence": result["confidence"],
        "agreement": result["agreement"],
        "route": result["route"],
        "n_used": result["n_used"],
        "escalated": result["escalated"],
        "advisory": result["advisory"],
        "verifier": result["verifier"],
        "tally": result["tally"],
        "chains": result["chains"],
        "weakest_step": result["weakest"],
        "verified_solution": result["verified_solution"],
        "latency_ms": latency_ms,
    }


# ==================== CHECK MY WORK ====================
@app.post("/checkwork")
async def checkwork(request: CheckRequest, authorization: str = Header(None)):
    user_id = auth.require_user(authorization)
    result = await explain.check_work(request.problem, request.solution_text)

    # log a mistake to the user's journal when an error was found
    if not result.get("is_correct") and result.get("error_step"):
        journal_mod.log_mistake(
            user_id=user_id,
            problem=request.problem,
            topic=result.get("topic") or topics_mod.classify_topic(request.problem),
            error_step=result["error_step"],
            error_type=result.get("error_type") or "arithmetic",
            explanation=result.get("explanation", ""),
        )
    return result


# ==================== HINT LADDER ====================
@app.post("/hint")
async def hint(request: HintRequest, authorization: str = Header(None)):
    auth.require_user(authorization)
    return await explain.build_hints(request.problem, request.level)


# ==================== TOPIC + READING ====================
@app.post("/topic")
def topic(request: TopicRequest, authorization: str = Header(None)):
    auth.require_user(authorization)
    t = topics_mod.classify_topic(request.problem)
    return {
        "topic": t,
        "topic_label": topics_mod.pretty(t),
        "resources": topics_mod.get_resources(t),
        "mini_lesson": topics_mod.mini_lesson(t),
    }


# ==================== VERIFIED QUIZ ====================
@app.post("/quiz")
async def quiz(request: QuizRequest, authorization: str = Header(None)):
    user_id = auth.require_user(authorization)
    questions = await quizgen.generate_verified_quiz(request.topic)
    if not questions:
        raise HTTPException(503, "Could not verify any quiz questions for this topic right now.")

    conn = db.get_db()
    c = conn.cursor()
    c.execute("INSERT INTO quiz (user_id, topic, ts) VALUES (?, ?, ?)",
              (user_id, request.topic, datetime.now().isoformat()))
    quiz_id = c.lastrowid
    for q in questions:
        c.execute(
            "INSERT INTO quiz_item (quiz_id, question, verified_answer) VALUES (?, ?, ?)",
            (quiz_id, q["question"], q["verified_answer"]),
        )
    conn.commit()
    conn.close()

    return {
        "quiz_id": quiz_id,
        "topic": request.topic,
        "questions": [{"text": q["question"], "verified_answer": q["verified_answer"]} for q in questions],
    }


@app.post("/quiz/grade")
async def quiz_grade(request: QuizGradeRequest, authorization: str = Header(None)):
    user_id = auth.require_user(authorization)

    # quick answer match first
    user_answer = consensus.normalize_answer(request.user_solution.splitlines()[-1] if request.user_solution else "")
    correct = consensus.normalize_answer(request.verified_answer) == user_answer and bool(user_answer)

    out = {"correct": correct}
    if not correct:
        # run the full check-my-work path to localize + explain the error
        result = await explain.check_work(request.question, request.user_solution)
        # check_work compares against its own verified answer; trust the quiz key for "correct"
        correct = result.get("is_correct", False)
        out["correct"] = correct
        if not correct:
            out["error_step"] = result.get("error_step")
            out["explanation"] = result.get("explanation")
            journal_mod.log_mistake(
                user_id=user_id,
                problem=request.question,
                topic=topics_mod.classify_topic(request.question),
                error_step=result.get("error_step") or 0,
                error_type=result.get("error_type") or "arithmetic",
                explanation=result.get("explanation", ""),
            )

    # record grade against the most recent matching quiz item, if present
    conn = db.get_db()
    c = conn.cursor()
    c.execute(
        "UPDATE quiz_item SET user_answer = ?, correct = ? "
        "WHERE id = (SELECT qi.id FROM quiz_item qi JOIN quiz q ON qi.quiz_id = q.quiz_id "
        "           WHERE q.user_id = ? AND qi.question = ? ORDER BY qi.id DESC LIMIT 1)",
        (request.user_solution, int(out["correct"]), user_id, request.question),
    )
    conn.commit()
    conn.close()
    return out


# ==================== OCR ====================
@app.post("/ocr")
def ocr(request: OCRRequest, authorization: str = Header(None)):
    auth.require_user(authorization)
    latex = ocr_mod.image_to_latex(request.image)
    if latex is None:
        raise HTTPException(503, "OCR is unavailable on this engine instance.")
    return {"latex": latex}


# ==================== SELF-RATE (metacognition) ====================
@app.post("/selfrate")
def selfrate(request: SelfRateRequest, authorization: str = Header(None)):
    user_id = auth.require_user(authorization)
    conn = db.get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO selfrate (user_id, item_id, user_conf, model_conf, correct, ts) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, request.item_id, request.user_conf, None, None, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


# ==================== HISTORY ====================
@app.get("/history")
def get_history(authorization: str = Header(None)):
    user_id = auth.require_user(authorization)
    conn = db.get_db()
    c = conn.cursor()
    c.execute(
        "SELECT ts, problem, mode, route, n_used, escalated, answer, confidence, latency "
        "FROM history WHERE user_id = ? ORDER BY id DESC LIMIT 50",
        (user_id,),
    )
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return {"history": rows}


# ==================== JOURNAL + PROFILE ====================
@app.get("/journal")
def get_journal(authorization: str = Header(None)):
    user_id = auth.require_user(authorization)
    return {
        "journal": journal_mod.get_journal(user_id),
        "profile": journal_mod.profile(user_id),
    }


# ==================== TARGETED PRACTICE (weak-topic) ====================
@app.get("/practice")
async def practice(authorization: str = Header(None)):
    user_id = auth.require_user(authorization)
    topic = journal_mod.weakest_topic(user_id)
    if not topic:
        return {"topic": None, "questions": [], "message": "No mistakes logged yet — solve or check some work first."}
    questions = await quizgen.generate_verified_quiz(topic)
    return {
        "topic": topic,
        "topic_label": topics_mod.pretty(topic),
        "questions": [{"text": q["question"], "verified_answer": q["verified_answer"]} for q in questions],
    }


# ==================== LEGACY WEBSOCKET (kept for the existing Solve page) ====================
@app.websocket("/ws/solve")
async def websocket_solve(websocket: WebSocket):
    await websocket.accept()
    try:
        data = await websocket.receive_text()
        req = json.loads(data)
        problem = req.get("problem")
        mode = req.get("mode", "balanced")
        token = req.get("token")

        user_id = auth.decode_token(token) if token else None
        if not user_id:
            await websocket.send_json({"type": "error", "message": "Unauthorized / Invalid token"})
            await websocket.close()
            return

        import router as router_mod
        import generate
        import prm_scoring

        rt = router_mod.route(problem, mode)
        await websocket.send_json({"type": "route", "strategy": rt.strategy, "n": rt.n})

        chains = await generate.generate_chains(problem, rt.n, rt.temperature)
        for chain_id, chain in enumerate(chains):
            steps = chain.get("steps", [])
            for step_idx, step_text in enumerate(steps):
                await websocket.send_json({"type": "step", "chain_id": chain_id, "step_idx": step_idx, "latex": step_text})
            try:
                prm = prm_scoring.score_steps(problem, steps) if steps else {"scores": [], "badges": []}
                chain["scores"], chain["badges"] = prm["scores"], prm["badges"]
            except Exception as e:  # noqa: BLE001
                print(f"WS PRM error chain {chain_id}: {e}")
                chain["scores"] = [0.5] * len(steps)
                chain["badges"] = ["amber"] * len(steps)
            for step_idx, (score, badge) in enumerate(zip(chain["scores"], chain["badges"])):
                await websocket.send_json({
                    "type": "score", "chain_id": chain_id, "step_idx": step_idx,
                    "score": score, "band": badge.split("|")[0],
                })
            await websocket.send_json({"type": "chain_done", "chain_id": chain_id, "answer": chain.get("answer", "Error")})

        best_answer, agreement, tally = consensus.run_consensus(chains)
        import calibration
        confidence = calibration.calibrate(agreement)
        await websocket.send_json({"type": "vote", "tally": tally, "agreement": agreement})

        weakest = pipeline._weakest_link(chains)

        conn = db.get_db()
        c = conn.cursor()
        c.execute(
            "INSERT INTO history (user_id, ts, problem, problem_hash, mode, route, n_used, escalated, answer, confidence, latency) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, datetime.now().isoformat(), problem, db.problem_hash(problem), mode,
             rt.strategy, len(chains), 0, best_answer, confidence, None),
        )
        conn.commit()
        conn.close()

        await websocket.send_json({
            "type": "final", "answer": best_answer, "confidence": confidence,
            "weakest": {"chain": weakest["chain"], "step": weakest["step"]},
        })
    except WebSocketDisconnect:
        print("WebSocket client disconnected")
    except Exception as e:  # noqa: BLE001
        print(f"Error in websocket handler: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
