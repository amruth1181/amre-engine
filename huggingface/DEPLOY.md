# Hugging Face — deployment notes (AMRE Engine)

This project uses Hugging Face in **two** separate places. Keep them straight.

---

## 1. The engine = a Hugging Face **Space** (Docker SDK)

The repo root *is* the Space. Remote:

```
origin  https://huggingface.co/spaces/amruth1181/amre-engine
```

### Files that MUST stay at the repo root (do not move into this folder)
| File | Why it must be at root |
|---|---|
| `README.md` | Holds the Space YAML frontmatter (`sdk: docker`, `app_port: 7860`). HF reads it from root to configure the Space. |
| `Dockerfile` | HF builds the container from the root Dockerfile (`COPY . .`, `CMD uvicorn main:app --port 7860`). |
| `*.py`, `requirements.txt` | They are the Docker build context / app entrypoint. |

Moving any of these breaks the build. That is why only HF *helper* files
(model export script + docs) live in `huggingface/`.

### Deploy
Pushing to `origin main` rebuilds the Space automatically:
```
git push origin main
```
(`origin` also pushes to GitHub — see `git remote -v`.)

### Secrets (Space → Settings → Variables and secrets)
| Key | Purpose |
|---|---|
| `OPENROUTER_API_KEY` | Policy model (Qwen2.5-7B) via OpenRouter |
| `JWT_SECRET` | Signing key for session tokens (don't ship the default) |
| `COLAB_PRM_URL` | Optional — preferred 7B PRM tunnel; auto-fails over to the ONNX floor |
| `PRM_MODEL_REPO` | Optional override; defaults to `amruth1181/skywork-prm-1.5b-onnx-int8` |
| `DB_PATH` | Optional; defaults to `/data/amre.db` (persistent disk) when `/data` exists |

### Persistent storage
SQLite lives on the Space's persistent disk (`/data/amre.db`). Streamlit Cloud
storage is ephemeral — keep ALL persistence on the engine.

### Keep-alive
Add a scheduled `GET /health` every ~30 min so the pitch URL never cold-starts
(IMPLEMENTATION.md §5).

---

## 2. The PRM = a Hugging Face **model** repo

`prm_onnx.py` downloads the quantized PRM at runtime via `snapshot_download`:

```
amruth1181/skywork-prm-1.5b-onnx-int8   (int8 ONNX, ~1.6 GB)
```

Base model: `Skywork/Skywork-o1-Open-PRM-Qwen-2.5-1.5B`.

### Build & upload the model
Run `huggingface/export_prm_onnx.py` (export → `quantize_dynamic` int8 → benchmark),
then upload the produced folder:

```python
from huggingface_hub import HfApi
api = HfApi()
api.create_repo(repo_id="amruth1181/skywork-prm-1.5b-onnx-int8", repo_type="model", exist_ok=True)
api.upload_folder(folder_path="./skywork-prm-onnx-int8",
                  repo_id="amruth1181/skywork-prm-1.5b-onnx-int8", repo_type="model")
```

See `MODEL_CARD.md` for the model card to drop into that repo.

---

## 3. Frontend (separate)
The Streamlit app deploys on Streamlit Community Cloud (or a separate HF Space,
Streamlit SDK) and talks to this engine over REST via `ENGINE_URL`.
