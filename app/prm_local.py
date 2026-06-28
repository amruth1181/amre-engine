"""
Local PRM floor — Skywork-o1-Open-PRM-Qwen-2.5-1.5B in native PyTorch.

The Skywork PRM uses a custom architecture (Qwen2RMConfig / reward head) that
`optimum-cli` cannot export to ONNX, so we run it directly with transformers
(trust_remote_code) and apply int8 dynamic quantization on the Linear layers —
small + CPU-friendly, the always-available floor scorer.

Scoring follows Skywork's own inference recipe (model_utils/io_utils.py):
  problem + steps are tokenized with a "\n" step separator; the reward is read
  at the LAST token of each step (flag==1); model(..., return_probs=True)
  returns per-token probabilities. We return one score per step.
"""
import os
from typing import List

import numpy as np

# Skywork's official, public model repo — no upload/Colab needed; the Space
# downloads it at first use. Override with PRM_MODEL_REPO if you mirror it.
MODEL_REPO = os.environ.get("PRM_MODEL_REPO", "Skywork/Skywork-o1-Open-PRM-Qwen-2.5-1.5B")
STEP_TOKEN = "\n"
QUANTIZE = os.environ.get("PRM_QUANTIZE", "1") not in ("0", "false", "False")
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
    model = AutoModel.from_pretrained(
        MODEL_REPO, trust_remote_code=True, cache_dir=cache_dir, torch_dtype=torch.float32
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
        out = _model(input_ids=ids, attention_mask=mask, return_probs=True)
    # Skywork forward returns (..., rewards); rewards = per-token probabilities
    if isinstance(out, (tuple, list)):
        rewards = out[-1]
    elif torch.is_tensor(out):
        rewards = out
    else:  # ModelOutput-like
        rewards = getattr(out, "rewards", None)
        if rewards is None:
            rewards = getattr(out, "logits")
    rewards = rewards[0]  # batch index 0

    idxs = [i for i, f in enumerate(reward_flags) if f == 1]
    scores = [float(rewards[i]) for i in idxs]

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
