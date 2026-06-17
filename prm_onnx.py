"""
PRM ONNX Backend — Skywork-o1-Open-PRM-Qwen-2.5-1.5B (int8)
Runs on CPU, ~1.6 GB. Always-available floor scorer.
"""
import os
import numpy as np
from typing import List, Optional

# Lazy-loaded globals
_session = None
_tokenizer = None
MODEL_REPO = os.environ.get("PRM_MODEL_REPO", "amruth1181/skywork-prm-1.5b-onnx-int8")


def _load_model():
    """Download from HF Hub and load ONNX model + tokenizer (once)."""
    global _session, _tokenizer

    if _session is not None:
        return

    from huggingface_hub import snapshot_download
    from transformers import AutoTokenizer
    import onnxruntime as ort

    # Download model files from HF Hub
    model_dir = snapshot_download(
        repo_id=MODEL_REPO,
        cache_dir="/data/models" if os.path.isdir("/data") else "./.cache/models"
    )

    # Load tokenizer
    _tokenizer = AutoTokenizer.from_pretrained(
        "Skywork/Skywork-o1-Open-PRM-Qwen-2.5-1.5B",
        trust_remote_code=True
    )

    # Load ONNX session
    onnx_path = os.path.join(model_dir, "model_quantized.onnx")
    if not os.path.exists(onnx_path):
        # Fallback: try unquantized
        onnx_path = os.path.join(model_dir, "model.onnx")

    sess_options = ort.SessionOptions()
    sess_options.intra_op_num_threads = 4  # per IMPLEMENTATION.md
    sess_options.inter_op_num_threads = 1
    sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

    _session = ort.InferenceSession(onnx_path, sess_options)
    print(f"✅ PRM ONNX model loaded from {model_dir}")


def score_steps(problem: str, steps: List[str]) -> List[float]:
    """
    Score each reasoning step using the PRM.
    Returns a list of floats (one per step), higher = better.

    Format follows Skywork PRM expected input:
      problem + step1 + step2 + ... (cumulative)
    Each step is scored in context of all previous steps.
    """
    _load_model()

    scores = []

    for i in range(len(steps)):
        # Build cumulative input: problem + steps up to i
        text = problem.strip() + "\n"
        for j in range(i + 1):
            text += f"Step {j+1}: {steps[j].strip()}\n"

        # Tokenize
        inputs = _tokenizer(
            text,
            return_tensors="np",
            truncation=True,
            max_length=2048,
            padding=True
        )

        # Run inference — one batched call per chain, NOT per token
        ort_inputs = {
            "input_ids": inputs["input_ids"].astype(np.int64),
            "attention_mask": inputs["attention_mask"].astype(np.int64),
        }

        try:
            outputs = _session.run(None, ort_inputs)
            # Output shape depends on model; typically logits for [negative, positive]
            logits = outputs[0]

            if logits.ndim == 2 and logits.shape[-1] >= 2:
                # Softmax to get P(correct)
                exp_logits = np.exp(logits[0] - np.max(logits[0]))
                probs = exp_logits / exp_logits.sum()
                score = float(probs[1])  # P(correct step)
            else:
                score = float(logits.flatten()[-1])

            scores.append(score)
        except Exception as e:
            print(f"⚠️ PRM scoring error at step {i+1}: {e}")
            scores.append(0.5)  # neutral fallback

    return scores


def get_step_badges(scores: List[float]) -> List[str]:
    """
    Assign color badges by percentile thresholds (IMPLEMENTATION.md §3.3):
      green  >= p40
      amber  p15–p40
      red    < p15
    Also marks argmin as 'weakest_link'.
    """
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
