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

## Endpoints

- `GET /health` — Health check
- `POST /auth/register` — Register a new user
- `POST /auth/login` — Login and get token
- `POST /solve` — Solve a math problem (requires auth)
- `GET /history` — Get user's solve history (requires auth)
