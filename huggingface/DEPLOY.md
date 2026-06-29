# Hugging Face — deployment notes (AMRE Engine)

This project uses Hugging Face in **two** separate places. Keep them straight.

---

## 1. The engine = a Hugging Face **Space** (Docker SDK)

The repo root *is* the Space. Remote:

```
origin  https://huggingface.co/spaces/amruth1181/amre-engine-v2
```

### Files that MUST stay at the repo root (do not move into this folder)
| File | Why it must be at root |
|---|---|
| `README.md` | Holds the Space YAML frontmatter (`sdk: docker`, `app_port: 7860`). HF reads it from root to configure the Space. |
| `Dockerfile` | HF builds the container from the root Dockerfile (`COPY . .`, `CMD uvicorn app.main:app --port 7860`). |
| `requirements.txt` | Docker build context / dependency install. |
| `app/` package | The engine code (`app.main:app` is the entrypoint). `COPY . .` brings it in. |

The engine modules live in `app/`, the offline prep scripts in `scripts/`, and
tests in `tests/` (see root `README.md`). `README.md`, `Dockerfile`, and
`requirements.txt` MUST stay at the repo root or the Space build breaks. HF
*helper* files (model export script + docs) live in `huggingface/`.

### Deploy
Pushing to `origin main` rebuilds the Space automatically:
```
git push origin main
```
(`origin` also pushes to GitHub — see `git remote -v`.)

### Secrets (Space → Settings → Variables and secrets)
| Key | Purpose |
|---|---|
| `GEMINI_API_KEY` | Policy model (Gemini 2.5 Flash) via the Gemini API |
| `JWT_SECRET` | Signing key for session tokens (don't ship the default) |
| `COLAB_PRM_URL` | Optional — preferred 7B PRM tunnel; auto-fails over to the ONNX floor |
| `PRM_MODEL_REPO` | Optional override; defaults to `Skywork/Skywork-o1-Open-PRM-Qwen-2.5-1.5B` (public) |
| `PRM_QUANTIZE` | Optional; `1` (default) applies int8 dynamic quant, `0` runs fp32 |
| `DB_PATH` | Optional; defaults to `/data/amre.db` (persistent disk) when `/data` exists |

### Persistent storage
SQLite lives on the Space's persistent disk (`/data/amre.db`). Streamlit Cloud
storage is ephemeral — keep ALL persistence on the engine.

### Keep-alive
Add a scheduled `GET /health` every ~30 min so the pitch URL never cold-starts
(IMPLEMENTATION.md §5).

---

## 2. The PRM floor — pulled directly from Skywork (no upload)

`app/prm_local.py` loads the PRM at runtime with `transformers`
(`AutoModel.from_pretrained(..., trust_remote_code=True)`) and int8 dynamic
quantization on CPU:

```
Skywork/Skywork-o1-Open-PRM-Qwen-2.5-1.5B   (public; ~1.5B params)
```

The Skywork PRM has a **custom reward-head architecture** (`Qwen2RMConfig`) that
`optimum-cli` cannot export to ONNX, so we run it in native PyTorch. Because the
Skywork repo is public, the Space downloads it itself on first use — **there is
no model to build or upload, and no Colab step.** Override with `PRM_MODEL_REPO`
only if you mirror the weights elsewhere.

Verify it's really scoring (not on the 0.5 fallback) from the Space terminal:
```
python scripts/check_prm.py
```

The preferred 7B tier still runs on Colab GPU behind `COLAB_PRM_URL`, with
automatic failover to this floor.

---

## 3. Frontend (separate)
The Streamlit app deploys on Streamlit Community Cloud (or a separate HF Space,
Streamlit SDK) and talks to this engine over REST via `ENGINE_URL`.
