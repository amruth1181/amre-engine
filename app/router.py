"""
Router + difficulty estimator (IMPLEMENTATION.md §3.4).

Precedence:
  - user mode always wins on budget (fast / balanced / careful)
  - auto -> router decides via a cheap difficulty estimate, and may escalate
    (escalation itself lives in pipeline.run_solve: after N=8, if agreement<0.5
     double N up to the cap)
"""
import json
import os
from dataclasses import dataclass

# free-tier cap (see IMPLEMENTATION.md §0 warning); raise if a paid provider is used
N_CAP_FREE = 16
N_CAP_CAREFUL = 32

# fitted thresholds from scripts/fit_router_thresholds.py, if present (else hardcoded defaults)
_DEFAULTS = {
    "max_len_easy": 50,
    "max_len_medium": 150,
    "complex_keywords": ["integral", "derivative", "prove", "matrix", "combinatorics",
                         "probability", "quadratic", "logarithm", "sequence", "series"],
}
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PARAMS_PATH = os.environ.get("ROUTER_PARAMS_PATH", os.path.join(_REPO_ROOT, "router_params.json"))


def _load_params():
    if os.path.exists(_PARAMS_PATH):
        try:
            with open(_PARAMS_PATH) as f:
                p = json.load(f)
            return {**_DEFAULTS, **p}
        except Exception as e:  # noqa: BLE001
            print(f"⚠️ Failed to load router_params.json: {e} — using defaults")
    return _DEFAULTS


_PARAMS = _load_params()


@dataclass
class Route:
    strategy: str
    n: int
    temperature: float
    escalatable: bool = False
    advisory: str = ""


def difficulty(problem: str) -> str:
    """Cheap easy/medium/hard estimate from surface features.
    Thresholds come from router_params.json (fit_router_thresholds.py) when present."""
    prob_len = len(problem)
    has_latex = "$" in problem or "\\" in problem
    is_complex = any(kw in problem.lower() for kw in _PARAMS["complex_keywords"])
    if prob_len < _PARAMS["max_len_easy"] and not is_complex and not has_latex:
        return "easy"
    if prob_len < _PARAMS["max_len_medium"] and not is_complex:
        return "medium"
    return "hard"


def route(problem: str, mode: str = "auto") -> Route:
    """Map (problem, mode) -> Route. Manual modes only advise; auto may escalate."""
    if mode == "fast":
        return Route("greedy", 1, 0.0, advisory="Fast mode (greedy) may be unreliable on hard problems.")
    if mode == "balanced":
        return Route("prm_weighted_vote", 8, 0.8)
    if mode == "verify":
        # Check-my-work / hints need ONE reliable comparison answer, not a
        # consensus. Greedy (temperature 0, N=1) is the fastest option and is
        # DETERMINISTIC — a student re-checking the same work gets the same
        # verdict. The PRM localizes the student's error step separately.
        return Route("greedy", 1, 0.0)
    if mode == "careful":
        return Route("prm_weighted_vote", min(32, N_CAP_CAREFUL), 0.8)

    # auto
    diff = difficulty(problem)
    if diff == "easy":
        return Route("greedy", 1, 0.0)
    if diff == "medium":
        return Route("prm_weighted_vote", 8, 0.8, escalatable=True)
    return Route("prm_weighted_vote", min(16, N_CAP_FREE), 0.8, escalatable=True)


# ---- backward-compatible alias for the existing WebSocket handler ----
def route_problem(problem: str, mode: str = "balanced") -> Route:
    return route(problem, mode)
