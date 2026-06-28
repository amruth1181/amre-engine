"""
Thin REST client for the AMRE engine (IMPLEMENTATION.md §3.7).

Reads ENGINE_URL from st.secrets (falls back to env / localhost) and attaches
the session token from st.session_state to every authenticated call. No model
is ever loaded here — all logic lives on the engine.
"""
import os

import requests
import streamlit as st


def engine_url() -> str:
    try:
        return st.secrets["ENGINE_URL"]
    except Exception:  # noqa: BLE001 — secrets may be absent in local dev
        return os.environ.get("ENGINE_URL", "http://localhost:7860")


def _headers() -> dict:
    token = st.session_state.get("token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def _post(path: str, payload: dict, timeout: int = 180) -> dict:
    r = requests.post(f"{engine_url()}{path}", json=payload, headers=_headers(), timeout=timeout)
    r.raise_for_status()
    return r.json()


def _get(path: str, timeout: int = 60) -> dict:
    r = requests.get(f"{engine_url()}{path}", headers=_headers(), timeout=timeout)
    r.raise_for_status()
    return r.json()


# ---- auth (no token needed) ----
def register(username: str, password: str) -> dict:
    r = requests.post(f"{engine_url()}/auth/register",
                      json={"username": username, "password": password}, timeout=30)
    r.raise_for_status()
    return r.json()


def login(username: str, password: str) -> dict:
    r = requests.post(f"{engine_url()}/auth/login",
                      json={"username": username, "password": password}, timeout=30)
    r.raise_for_status()
    return r.json()


# ---- solve & learning loop ----
def solve(problem: str, mode: str = "auto") -> dict:
    return _post("/solve", {"problem": problem, "mode": mode})


def checkwork(problem: str, solution_text: str) -> dict:
    return _post("/checkwork", {"problem": problem, "solution_text": solution_text})


def hint(problem: str, level: int) -> dict:
    return _post("/hint", {"problem": problem, "level": level})


def topic(problem: str) -> dict:
    return _post("/topic", {"problem": problem})


def quiz(topic_name: str) -> dict:
    return _post("/quiz", {"topic": topic_name})


def quiz_grade(question: str, verified_answer: str, user_solution: str) -> dict:
    return _post("/quiz/grade", {"question": question, "verified_answer": verified_answer,
                                 "user_solution": user_solution})


def ocr(image_b64: str) -> dict:
    return _post("/ocr", {"image": image_b64})


def selfrate(item_id: str, user_conf: float) -> dict:
    return _post("/selfrate", {"item_id": item_id, "user_conf": user_conf})


# ---- per-user reads ----
def history() -> dict:
    return _get("/history")


def journal() -> dict:
    return _get("/journal")


def practice() -> dict:
    return _get("/practice")


def studysheet() -> bytes:
    """Fetch the per-user study-sheet PDF as raw bytes (§9.9)."""
    r = requests.get(f"{engine_url()}/studysheet", headers=_headers(), timeout=90)
    r.raise_for_status()
    return r.content


def healthy() -> bool:
    try:
        return _get("/health").get("status") == "ok"
    except Exception:  # noqa: BLE001
        return False
