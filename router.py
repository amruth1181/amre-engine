"""
Router + difficulty estimator (IMPLEMENTATION.md §3.4).

Precedence:
  - user mode always wins on budget (fast / balanced / careful)
  - auto -> router decides via a cheap difficulty estimate, and may escalate
    (escalation itself lives in pipeline.run_solve: after N=8, if agreement<0.5
     double N up to the cap)
"""
from dataclasses import dataclass

# free-tier cap (see IMPLEMENTATION.md §0 warning); raise if a paid provider is used
N_CAP_FREE = 16
N_CAP_CAREFUL = 32


@dataclass
class Route:
    strategy: str
    n: int
    temperature: float
    escalatable: bool = False
    advisory: str = ""


def difficulty(problem: str) -> str:
    """Cheap easy/medium/hard estimate from surface features.
    Replaced by fit_router_thresholds.py output (router_params.json) when available."""
    prob_len = len(problem)
    has_latex = "$" in problem or "\\" in problem
    is_complex = any(
        kw in problem.lower()
        for kw in ["integral", "derivative", "prove", "matrix", "combinatorics",
                   "probability", "quadratic", "logarithm", "sequence", "series"]
    )
    if prob_len < 50 and not is_complex and not has_latex:
        return "easy"
    if prob_len < 150 and not is_complex:
        return "medium"
    return "hard"


def route(problem: str, mode: str = "auto") -> Route:
    """Map (problem, mode) -> Route. Manual modes only advise; auto may escalate."""
    if mode == "fast":
        return Route("greedy", 1, 0.0, advisory="Fast mode (greedy) may be unreliable on hard problems.")
    if mode == "balanced":
        return Route("prm_weighted_vote", 8, 0.8)
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
