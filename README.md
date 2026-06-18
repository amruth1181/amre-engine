---
title: AMRE Engine
emoji: 🧮
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# AMRE Engine — Adaptive Math Reasoning Engine

FastAPI backend for the Adaptive Math Reasoning Engine (AMRE).

The engine holds all logic + persistence. Stack: router → generation (OpenRouter
Qwen2.5-7B) → PRM scoring (Colab 7B with ONNX 1.5B failover) → PRM-weighted
consensus → isotonic calibration → per-user SQLite. See `IMPLEMENTATION.md`.

## Endpoints (all data endpoints derive `user_id` from the bearer token)

Auth
- `POST /auth/register {username, password}` → `{user_id, token}`
- `POST /auth/login {username, password}` → `{user_id, token}`

Solve & learning loop
- `POST /solve {problem, mode}` → `{answer, confidence, route, n_used, escalated, chains[], weakest_step, verified_solution, latency_ms}` (mode: `auto|fast|balanced|careful`)
- `POST /checkwork {problem, solution_text}` → `{steps[], scores[], badges[], error_step, error_type, explanation, verified_solution, confidence}`
- `POST /hint {problem, level}` → `{hint}` (level 1–4: concept → strategy → first step → full)
- `POST /topic {problem}` → `{topic, resources[], mini_lesson}`
- `POST /quiz {topic}` → `{quiz_id, questions:[{text, verified_answer}]}` (self-consistency-verified)
- `POST /quiz/grade {question, verified_answer, user_solution}` → `{correct, error_step?, explanation?}`
- `POST /ocr {image}` → `{latex}` (pix2tex; 503 if unavailable)
- `POST /selfrate {item_id, user_conf}` → `{ok}`

Per-user reads
- `GET /history` → recent solves
- `GET /journal` → mistake journal + error-type / weak-topic profile
- `GET /practice` → verified practice questions on the user's weakest topic
- `GET /health` — health check (also used by the keep-alive ping)
- `WS /ws/solve` — legacy streaming endpoint (kept for the current Solve page)

## Offline scripts
- `python fit_calibration.py --data runs.jsonl` — fit `calibration.pkl` (isotonic agreement→P(correct))
- `python preseed_demo.py` — seed demo users + history + journal for the pitch
- `python huggingface/export_prm_onnx.py` — export/quantize the Skywork 1.5B PRM to ONNX int8 (see `huggingface/DEPLOY.md`)

## Local run
```
pip install -r requirements.txt
uvicorn main:app --reload --port 7860
```
