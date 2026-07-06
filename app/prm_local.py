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
from typing import List, Tuple

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
# bf16 matmul has no hardware acceleration on x86 CPUs (HF Spaces) or Apple
# Silicon and is often 2-4x slower than fp32. Default to fp32; the NaN that
# motivated bf16 came from *mixed* precision, which we now avoid by casting the
# whole model to one dtype consistently. Set PRM_DTYPE=bf16 to opt back in.
PRM_DTYPE = os.environ.get("PRM_DTYPE", "fp32").lower()
# rows per PRM forward pass — bounds activation memory when batch-scoring N chains
PRM_BATCH = int(os.environ.get("PRM_BATCH", "8"))

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
    # Load in the model's NATIVE bfloat16 (config torch_dtype=bfloat16). Forcing
    # fp32 left some internal buffers in bf16 while activations were fp32 -> mixed
    # precision -> NaN hidden states (every step scored 0.5). bf16 keeps everything
    # consistent and halves the RAM. Eager attention avoids the SDPA-on-CPU path.
    load_dtype = torch.bfloat16 if PRM_DTYPE in ("bf16", "bfloat16") else torch.float32
    try:
        model = AutoModel.from_pretrained(
            MODEL_REPO, trust_remote_code=True, cache_dir=cache_dir,
            torch_dtype=load_dtype, attn_implementation="eager",
        ).eval()
    except Exception as e:  # noqa: BLE001 — custom model may not accept the kwarg
        print(f"⚠️ eager attn_implementation not accepted ({e}); loading default")
        model = AutoModel.from_pretrained(
            MODEL_REPO, trust_remote_code=True, cache_dir=cache_dir,
            torch_dtype=load_dtype,
        ).eval()

    # Cast ALL params + buffers to one dtype. Forcing only activations to fp32
    # while buffers stayed bf16 previously produced NaN hidden states (every step
    # scored 0.5). Casting the whole model keeps precision consistent.
    model = model.to(load_dtype)

    if QUANTIZE:
        try:
            model = torch.ao.quantization.quantize_dynamic(
                model, {torch.nn.Linear}, dtype=torch.qint8
            )
            print("✅ PRM loaded (Skywork 1.5B, int8 dynamic-quantized, CPU)")
        except Exception as e:  # noqa: BLE001 — fall back if quant unsupported
            print(f"⚠️ int8 quantization failed ({e}); running unquantized")
    else:
        print(f"✅ PRM loaded (Skywork 1.5B, dtype={next(model.parameters()).dtype}, "
              f"transformers={__import__('transformers').__version__}, CPU)")

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
        # everything stays under no_grad; move to a plain python list of floats
        rewards = torch.sigmoid(per_token).detach().cpu().tolist()

    idxs = [i for i, f in enumerate(reward_flags) if f == 1]
    # sanitize: clamp to [0,1] and replace any NaN/inf so the JSON response is valid
    scores = []
    for i in idxs:
        v = rewards[i] if i < len(rewards) else 0.5
        scores.append(min(1.0, max(0.0, v)) if math.isfinite(v) else 0.5)

    # one score per step; pad defensively if anything got truncated
    if len(scores) < len(steps):
        scores += [0.5] * (len(steps) - len(scores))
    return scores[: len(steps)]


def score_steps_batch(items: List[Tuple[str, List[str]]]) -> List[List[float]]:
    """Score several (problem, steps) items in ONE padded forward pass per chunk.

    Numerically identical to calling score_steps() on each item: causal attention +
    right-padding means the padded tail tokens never influence real positions, and
    each token's reward is read at its own step-end flag. But on CPU this is far
    cheaper than N separate passes (one BLAS dispatch, one graph). Chunked to
    PRM_BATCH rows to bound activation memory on small Spaces.
    """
    if not items:
        return []
    _load_model()
    import torch

    out: List[List[float]] = []
    for start in range(0, len(items), PRM_BATCH):
        chunk = items[start:start + PRM_BATCH]

        # build (input_ids, reward_flags, n_steps) per row; empty rows -> no steps
        built = []
        for problem, steps in chunk:
            if not steps:
                built.append(([], [], 0))
                continue
            ids, flags = _build_inputs(problem, steps)
            built.append((ids, flags, len(steps)))

        max_len = max((len(ids) for ids, _, _ in built), default=0)
        if max_len == 0:
            out.extend([[] for _ in chunk])
            continue

        pad_id = _tokenizer.pad_token_id
        if pad_id is None:
            pad_id = _tokenizer.eos_token_id or 0

        batch_ids, batch_mask = [], []
        for ids, _flags, _n in built:
            padlen = max_len - len(ids)
            batch_ids.append(ids + [pad_id] * padlen)          # right-pad
            batch_mask.append([1] * len(ids) + [0] * padlen)   # mask out the pads
        ids_t = torch.tensor(batch_ids, dtype=torch.long)
        mask_t = torch.tensor(batch_mask, dtype=torch.long)

        with torch.no_grad():
            model_out = _model(input_ids=ids_t, attention_mask=mask_t,
                               use_cache=False, output_hidden_states=True)
            hidden = model_out.hidden_states[-1] if getattr(model_out, "hidden_states", None) else None
            if hidden is None:  # fallback: call the base transformer directly
                base = getattr(_model, "model", None) or getattr(_model, "transformer", None)
                hidden = base(input_ids=ids_t, attention_mask=mask_t, use_cache=False).last_hidden_state
            vhead = (getattr(_model, "v_head", None) or getattr(_model, "value_head", None)
                     or getattr(_model, "score", None))
            per_token = torch.sigmoid(vhead(hidden).squeeze(-1))  # [batch, seq]
            per_token = per_token.detach().cpu().tolist()

        for row, (ids, flags, n_steps) in enumerate(built):
            if not ids:
                out.append([])
                continue
            rewards = per_token[row]
            idxs = [i for i, f in enumerate(flags) if f == 1]
            scores = []
            for i in idxs:
                v = rewards[i] if i < len(rewards) else 0.5
                scores.append(min(1.0, max(0.0, v)) if math.isfinite(v) else 0.5)
            if len(scores) < n_steps:
                scores += [0.5] * (n_steps - len(scores))
            out.append(scores[:n_steps])
    return out


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
