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

FastAPI backend for the Adaptive Math Reasoning Engine (AMRE). The engine holds
**all logic + persistence**; the Streamlit frontend only holds a session token
and calls the engine over REST. See `IMPLEMENTATION.md` for the full design.

**Core solve pipeline:** router → generation → PRM step-scoring → PRM-weighted
consensus vote → isotonic calibration → per-user store.

- **Generation** — switchable, OpenAI-compatible provider (`app/generate.py`):
  **Groq** (`llama-3.3-70b-versatile`, default) ⇄ **Cerebras** (`gpt-oss-120b`),
  chosen at startup by `LLM_PROVIDER`. Only the base URL, key, and model id
  differ. Retries transient 429/5xx with backoff; falls back to a deterministic
  mock bank when no key is set (so tests/offline dev still run).
- **PRM floor** (`app/prm_local.py`) — `Skywork-o1-Open-PRM-Qwen-2.5-1.5B` run in
  **native PyTorch** (its custom reward-head architecture can't be ONNX-exported).
  `transformers` is **pinned to 4.44.2** — Skywork's vendored modeling code targets
  ~4.44 and emits NaNs on newer versions. The official Skywork repo is public, so
  the Space downloads it on first use (no model upload). Optional **Colab 7B PRM**
  runs behind a health-checked failover to this floor.
- **Consensus** (`app/consensus.py`) — answer normalization + PRM-weighted vote.
- **Calibration** (`app/calibration.py`) — isotonic `agreement → P(correct)`; the
  confidence shown is calibrated, never the raw (saturating) PRM score.
- **Persistence** (`app/db.py`) — **Turso / libSQL** (hosted, SQLite-compatible)
  when `TURSO_DATABASE_URL` is set, so per-user data survives Space restarts;
  falls back to local `sqlite3` otherwise.

## Endpoints

All data endpoints derive `user_id` from the bearer token — never a client-sent id.

**Auth**
- `POST /auth/register {username, password}` → `{user_id, token}`
- `POST /auth/login {username, password}` → `{user_id, token}`

**Solve & core learning loop**
- `POST /solve {problem, mode, use_prm?}` → `{answer, confidence, agreement, route, n_used, escalated, verifier, chains[], weakest_step, verified_solution, latency_ms}` (mode: `auto|fast|balanced|careful`; `use_prm` toggles per-step scoring)
- `POST /checkwork {problem, solution_text}` → `{steps[], scores[], badges[], error_step, error_type, explanation, verified_solution, verified_steps[], confidence}`
- `POST /hint {problem, level}` → `{hint}` (level 1–4: concept → strategy → first step → full)
- `POST /topic {problem}` → `{topic, resources[], mini_lesson}`
- `POST /quiz {topic}` → `{quiz_id, questions:[{text, verified_answer}]}` (self-consistency-verified)
- `POST /quiz/grade {question, verified_answer, user_solution}` → `{correct, error_step?, explanation?}`
- `POST /ocr {image}` → `{latex}` (pix2tex; 503 if unavailable)
- `POST /selfrate {item_id, user_conf}` → `{ok}` (confidence metacognition)

**Spaced repetition (SM-2, `app/srs.py`)**
- `GET  /review/due` → `{cards[]}` — mistakes due for review
- `POST /review/grade {card_id, quality}` → updates the SM-2 schedule

**Teacher / classroom (`app/classes.py`)**
- `POST /class/create {name}` → `{class_id, join_code}`
- `POST /class/join {join_code}` · `GET /class/list`
- `GET  /class/{class_id}/dashboard` — aggregate weak topics + per-student breakdown
- `POST /class/{class_id}/assign {topic}` — assign a topic quiz

**Progress, gamification & wellness**
- `GET /history` · `GET /journal` (mistake journal + weak-topic profile) · `GET /practice`
- `GET /gamify` → `{xp, level, streak, badges[], …}` (`app/gamify.py`)
- `GET /wellness` → 7-day activity summary + a short LLM coach note (`app/wellness.py`)
- `GET /knowledge-graph` → topic-mastery graph for the Learning Path
- `GET /studysheet` → per-user revision **PDF** (fpdf2; mistakes + reading + quiz)
- `GET /health` — health check / keep-alive ping
- `WS  /ws/solve` — legacy streaming endpoint (unused by the frontend)

## Frontend (`frontend/`, Streamlit)

Multipage app with a dark **"LaTeX Academia"** theme (`lib/theme.py`). Pages:
`Home` (login + gamified landing) · `1_Solve` · `2_Check_my_work` · `3_Quiz` ·
`4_My_Progress` · `5_Review` · `6_Teacher` · `7_Learning_Path` · `8_Weekly_Summary`.
`lib/api.py` is the REST client (reads `ENGINE_URL` from `st.secrets`); no model
is ever loaded in the frontend.

## Layout
```
app/         FastAPI engine package (solve pipeline + learning loop + persistence)
scripts/     offline prep + diagnostics (run from the repo root)
tests/       pytest suite
frontend/    Streamlit app (Home + pages/ + lib/ + .streamlit/)
huggingface/ HF deploy notes
```

## Environment / secrets
| Var | Purpose |
|---|---|
| `GROQ_API_KEY` / `CEREBRAS_API_KEY` | generation key(s) |
| `LLM_PROVIDER` | `groq` (default) or `cerebras`; `LLM_BASE_URL` / `LLM_MODEL` override the URL/model id |
| `JWT_SECRET` | session-token signing key |
| `TURSO_DATABASE_URL` / `TURSO_AUTH_TOKEN` | persistent DB (else local sqlite) |
| `COLAB_PRM_URL` | optional 7B PRM tunnel (auto-fails over to the 1.5B floor) |
| `PRM_MODEL_REPO` | PRM repo (default `Skywork/Skywork-o1-Open-PRM-Qwen-2.5-1.5B`) |
| `PRM_QUANTIZE` | `0` (default, fp32) / `1` (int8) |

## Offline scripts (run from the repo root)
- `python scripts/fit_calibration.py --data runs.jsonl` — fit `calibration.pkl` (isotonic agreement→P(correct))
- `python scripts/fit_router_thresholds.py --data regimes.jsonl` — fit `router_params.json`
- `python scripts/prm_score_correlation.py --pairs pairs.jsonl` — Spearman ρ, 1.5B floor vs 7B PRM
- `python scripts/sanity_check_calibration.py --data labeled.jsonl` — validate calibration
- `python scripts/preseed_demo.py` — seed demo users + history + journal
- `python scripts/check_prm.py` — diagnose whether the PRM is producing real (non-0.5) scores

`calibration.pkl` and `router_params.json` are gitignored build artifacts; the
engine falls back to identity calibration / hardcoded thresholds if they're absent.

## Local run
```
pip install -r requirements.txt
uvicorn app.main:app --reload --port 7860     # engine on :7860
pytest -q                                      # run the test suite

# frontend (separate shell)
pip install -r frontend/requirements.txt
streamlit run frontend/Home.py                 # set ENGINE_URL in frontend/.streamlit/secrets.toml
```

## Deploy
- **Engine** → HF Space (Docker, CPU 16 GB): `amruth1181/amre-engine-v3`. `torch`
  is installed CPU-only in the `Dockerfile` (the default CUDA wheel breaks the free
  Space). Push to the Space remote to rebuild.
- **Frontend** → Streamlit Community Cloud (main file `frontend/Home.py`; secret
  `ENGINE_URL = https://amruth1181-amre-engine-v3.hf.space`).
