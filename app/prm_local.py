"""
Local PRM floor — Skywork-o1-Open-PRM-Qwen-2.5-1.5B in native PyTorch.

The Skywork PRM uses a custom architecture (Qwen2RMConfig / reward head) that
`optimum-cli` cannot export to ONNX, so we run it directly with transformers
(trust_remote_code) and apply int8 dynamic quantization on the Linear layers —
small + CPU-friendly, the always-available floor scorer.

Scoring follows Skywork's own inference recipe (model_utils/io_utils.py):
  problem + steps are tokenized with a "\n" step separator; the reward is read
  at the LAST token of each step (flag==1). The HF checkpoint exposes
  Qwen2ForRewardModel, whose forward POOLS to one reward per sequence, so we run
  the value head (v_head) over all hidden states ourselves to get per-token
  rewards, sigmoid them, and read one score per step.
"""
import math
import os
from typing import List

import numpy as np

# Skywork's official, public model repo — no upload/Colab needed; the Space
# downloads it at first use. Override with PRM_MODEL_REPO if you mirror it.
MODEL_REPO = os.environ.get("PRM_MODEL_REPO", "Skywork/Skywork-o1-Open-PRM-Qwen-2.5-1.5B")
STEP_TOKEN = "\n"
# int8 dynamic quantization is OFF by default: the quantized kernels crash on
# this model at inference ("ChooseQuantizationParams: min should be <= max").
# fp32 is stable. Set PRM_QUANTIZE=1 to opt back in if a future torch fixes it.
QUANTIZE = os.environ.get("PRM_QUANTIZE", "0") in ("1", "true", "True")
MAX_TOKENS = int(os.environ.get("PRM_MAX_TOKENS", "4096"))

# lazy globals
_model = None
_tokenizer = None
_step_token_id = None


def _load_model():
    """Load tokenizer + PRM (once), int8-quantized on CPU."""
    global _model, _tokenizer, _step_token_id
    if _model is not None:
        return

    import torch
    from transformers import AutoTokenizer, AutoModel

    torch.set_num_threads(int(os.environ.get("PRM_THREADS", "4")))
    cache_dir = "/data/models" if os.path.isdir("/data") else "./.cache/models"

    _tokenizer = AutoTokenizer.from_pretrained(
        MODEL_REPO, trust_remote_code=True, cache_dir=cache_dir
    )
    # NOTE: do NOT use low_cpu_mem_usage=True here. With this tied-weight custom
    # model (tie_word_embeddings=true), the meta-device incremental load leaves the
    # embeddings uninitialized -> NaN activations -> every step scores 0.5. A full
    # fp32 load (~9GB peak) fits the 16GB Space and loads the weights correctly.
    model = AutoModel.from_pretrained(
        MODEL_REPO, trust_remote_code=True, cache_dir=cache_dir,
        torch_dtype=torch.float32,
    ).eval()

    if QUANTIZE:
        try:
            model = torch.ao.quantization.quantize_dynamic(
                model, {torch.nn.Linear}, dtype=torch.qint8
            )
            print("✅ PRM loaded (Skywork 1.5B, int8 dynamic-quantized, CPU)")
        except Exception as e:  # noqa: BLE001 — fall back to fp32 if quant unsupported
            print(f"⚠️ int8 quantization failed ({e}); running fp32")
    else:
        print("✅ PRM loaded (Skywork 1.5B, fp32, CPU)")

    _model = model
    _step_token_id = _tokenizer.encode(STEP_TOKEN)[-1]


def _build_inputs(problem: str, steps: List[str]):
    """Tokenize problem + steps, flagging the last token of each step (Skywork recipe)."""
    bos = _tokenizer.bos_token or ""
    prompt_ids = _tokenizer.encode(bos + problem + "\n")
    input_ids = list(prompt_ids)
    reward_flags = [0] * len(prompt_ids)
    for step in steps:
        s = step.strip()
        step_ids = _tokenizer.encode(s) if s else []
        step_ids = step_ids + [_step_token_id]
        flags = [0] * len(step_ids)
        flags[-1] = 1  # reward is read at the step-end token
        input_ids.extend(step_ids)
        reward_flags.extend(flags)

    # guard against runaway length: trim from the LEFT of the prompt only,
    # so every step-end flag is preserved.
    if len(input_ids) > MAX_TOKENS:
        overflow = len(input_ids) - MAX_TOKENS
        input_ids = input_ids[overflow:]
        reward_flags = reward_flags[overflow:]
    return input_ids, reward_flags


def score_steps(problem: str, steps: List[str]) -> List[float]:
    """Return one reward (0..1) per step. Higher = the step looks more correct."""
    if not steps:
        return []
    _load_model()
    import torch

    input_ids, reward_flags = _build_inputs(problem, steps)
    ids = torch.tensor([input_ids], dtype=torch.long)
    mask = torch.ones_like(ids)

    with torch.no_grad():
        # use_cache=False skips the model's DynamicCache.from_legacy_cache() path,
        # which newer transformers removed (Skywork code targets transformers ~4.44).
        # output_hidden_states=True so we can apply the value head to EVERY token:
        # Qwen2ForRewardModel.forward POOLS to a single reward (out.logits is
        # [batch], one number for the whole sequence), but a PRM needs a per-step
        # score, so we run v_head over all positions ourselves.
        out = _model(input_ids=ids, attention_mask=mask,
                     use_cache=False, output_hidden_states=True)

        hidden = out.hidden_states[-1] if getattr(out, "hidden_states", None) else None
        if hidden is None:  # fallback: call the base transformer directly
            base = getattr(_model, "model", None) or getattr(_model, "transformer", None)
            hidden = base(input_ids=ids, attention_mask=mask, use_cache=False).last_hidden_state

        vhead = (getattr(_model, "v_head", None) or getattr(_model, "value_head", None)
                 or getattr(_model, "score", None))
        per_token = vhead(hidden).squeeze(-1)[0]   # [seq] raw per-token reward
        _raw = per_token.detach().float()
        _dbg = (f"hidden={tuple(hidden.shape)} vhead_out={tuple(per_token.shape)} "
                f"raw_min={float(_raw.min()):.4f} raw_max={float(_raw.max()):.4f} "
                f"nan_or_inf={bool(torch.isnan(_raw).any() or torch.isinf(_raw).any())}")
        # everything stays under no_grad; move to a plain python list of floats
        rewards = torch.sigmoid(per_token).detach().cpu().tolist()

    idxs = [i for i, f in enumerate(reward_flags) if f == 1]
    # sanitize: clamp to [0,1] and replace any NaN/inf so the JSON response is valid
    scores = []
    for i in idxs:
        v = rewards[i] if i < len(rewards) else 0.5
        scores.append(min(1.0, max(0.0, v)) if math.isfinite(v) else 0.5)

    print(f"[PRM-DEBUG] n_steps={len(steps)} seq_len={len(rewards)} idxs={idxs} "
          f"{_dbg} scores={[round(s, 4) for s in scores]}")

    # one score per step; pad defensively if anything got truncated
    if len(scores) < len(steps):
        scores += [0.5] * (len(steps) - len(scores))
    return scores[: len(steps)]


def get_step_badges(scores: List[float]) -> List[str]:
    """Color badges by percentile thresholds (IMPLEMENTATION.md §3.3):
      green >= p40 · amber p15–p40 · red < p15 · argmin marked weakest_link."""
    if not scores:
        return []

    sorted_scores = sorted(scores)
    n = len(sorted_scores)
    p15 = sorted_scores[max(0, int(n * 0.15))]
    p40 = sorted_scores[max(0, int(n * 0.40))]
    weakest_idx = int(np.argmin(scores))

    badges = []
    for i, s in enumerate(scores):
        if s < p15:
            badge = "red"
        elif s < p40:
            badge = "amber"
        else:
            badge = "green"
        if i == weakest_idx:
            badge += "|weakest_link"
        badges.append(badge)
    return badges
