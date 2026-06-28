"""
PRM Scoring with Failover (IMPLEMENTATION.md §3.3)
Tries Colab 7B PRM first, falls back to the local Skywork 1.5B PyTorch floor.
"""
import os
import time
import requests
from typing import List, Optional

from . import prm_local

# ==================== COLAB PRM (7B, preferred) ====================
COLAB_PRM_URL = os.environ.get("COLAB_PRM_URL", "")  # e.g. https://xxxx.trycloudflare.com
COLAB_TIMEOUT = 3  # seconds, per IMPLEMENTATION.md
_colab_healthy = True
_colab_last_check = 0.0
HEALTH_INTERVAL = 60  # re-probe every 60 seconds


class ColabPRM:
    """Qwen2.5-Math-PRM-7B on Colab via cloudflared tunnel."""

    @staticmethod
    def healthy() -> bool:
        global _colab_healthy, _colab_last_check

        if not COLAB_PRM_URL:
            return False

        now = time.time()
        if now - _colab_last_check < HEALTH_INTERVAL:
            return _colab_healthy

        # Re-probe health
        try:
            r = requests.get(f"{COLAB_PRM_URL}/health", timeout=2)
            _colab_healthy = r.status_code == 200
        except Exception:
            _colab_healthy = False

        _colab_last_check = now
        return _colab_healthy

    @staticmethod
    def mark_down():
        global _colab_healthy, _colab_last_check
        _colab_healthy = False
        _colab_last_check = time.time()

    @staticmethod
    def score_steps(problem: str, steps: List[str]) -> List[float]:
        """POST /score to Colab PRM endpoint."""
        r = requests.post(
            f"{COLAB_PRM_URL}/score",
            json={"problem": problem, "steps": steps},
            timeout=COLAB_TIMEOUT
        )
        r.raise_for_status()
        return r.json()["scores"]


# ==================== UNIFIED INTERFACE ====================
colab = ColabPRM()


def score_steps(problem: str, steps: List[str]) -> dict:
    """
    Score steps with failover:
      1. Try Colab 7B PRM (preferred, higher quality)
      2. Fall back to ONNX 1.5B (floor, always available)

    Returns:
        {
            "scores": [float, ...],
            "badges": [str, ...],
            "weakest_step": int,
            "verifier": "7b-research" | "1.5b-torch"
        }
    """
    verifier = "1.5b-torch"  # default
    scores = []

    # Try Colab 7B first
    if colab.healthy():
        try:
            scores = colab.score_steps(problem, steps)
            verifier = "7b-research"
        except (requests.Timeout, requests.ConnectionError, Exception) as e:
            print(f"⚠️ Colab PRM failed, falling back to local floor: {e}")
            colab.mark_down()
            scores = []

    # Fallback to the local Skywork 1.5B floor
    if not scores:
        scores = prm_local.score_steps(problem, steps)
        verifier = "1.5b-torch"

    # Compute badges and weakest step
    badges = prm_local.get_step_badges(scores)
    weakest_step = int(min(range(len(scores)), key=lambda i: scores[i])) if scores else 0

    return {
        "scores": scores,
        "badges": badges,
        "weakest_step": weakest_step,
        "verifier": verifier,
    }
