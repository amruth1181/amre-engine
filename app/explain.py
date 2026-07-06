"""
Check-my-work + error localization + hint ladder (IMPLEMENTATION.md §9.1, §9.2).

Check-my-work:
  segment user steps -> PRM-score them -> engine solves for a *verified* solution
  -> locate the error step (PRM weakest link, cross-checked against the verified
     answer so a fully-correct attempt is not falsely flagged)
  -> grounded explanation from (problem + verified_solution + error_step).

Hint ladder: pure slicing of the already-computed verified solution.
  L1 concept · L2 strategy · L3 first correct step · L4 full solution.
"""
import asyncio
import re
from typing import Dict, Any, List, Optional

from . import segment
from . import prm_scoring
from . import generate
from . import consensus
from . import topics as topics_mod
from . import pipeline

# error-type buckets (IMPLEMENTATION.md §9.6)
ERROR_TYPES = ["sign", "arithmetic", "concept", "formula", "incomplete"]


def classify_error_type(error_step_text: str, explanation: str) -> str:
    """Heuristic classification of an error into one of ERROR_TYPES."""
    blob = f"{error_step_text} {explanation}".lower()
    if any(k in blob for k in ["sign", "negative", "positive", "flipped the", "minus", "plus/minus"]):
        return "sign"
    if any(k in blob for k in ["formula", "wrong rule", "incorrect rule", "should use", "theorem"]):
        return "formula"
    if any(k in blob for k in ["concept", "misunderstood", "definition", "approach", "method"]):
        return "concept"
    if any(k in blob for k in ["incomplete", "did not finish", "missing step", "stopped", "forgot to"]):
        return "incomplete"
    if any(k in blob for k in ["arithmetic", "calculation", "compute", "add", "subtract", "multiply", "divide", "miscalculat"]):
        return "arithmetic"
    return "arithmetic"


def _score_user_steps(problem: str, steps: List[str]):
    """Blocking PRM scoring of the student's steps. Runs in a worker thread so its
    CPU pass overlaps the verification solve's network I/O (torch releases the GIL
    during matmul, so this genuinely runs concurrently)."""
    try:
        prm = prm_scoring.score_steps(problem, steps)
        return prm["scores"], prm["badges"]
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ check_work PRM failed: {e}")
        return [0.5] * len(steps), ["amber"] * len(steps)


async def check_work(problem: str, solution_text: str,
                     known_answer: Optional[str] = None) -> Dict[str, Any]:
    """Localize the student's error and explain it, grounded in a verified answer.

    known_answer: when the correct answer is already known (e.g. the quiz key), we
    skip the verification solve entirely and compare against it."""
    steps = segment.segment_steps(solution_text)
    if not steps:
        # treat the whole thing as one step rather than failing outright
        steps = [solution_text.strip()] if solution_text.strip() else []
    if not steps:
        return {
            "steps": [], "scores": [], "badges": [], "error_step": None,
            "explanation": "No reasoning steps were detected. Number your work as 'Step 1:', 'Step 2:' …",
            "verified_solution": "", "verified_answer": "", "confidence": 0.0,
            "is_correct": False, "error_type": None,
        }

    # Score the student's steps (PRM). When we also need a verified answer, run the
    # greedy solve CONCURRENTLY so the PRM pass hides behind the LLM call.
    if known_answer is not None:
        scores, badges = await asyncio.to_thread(_score_user_steps, problem, steps)
        verified_answer, verified_solution, confidence, verified_steps = known_answer, "", 1.0, []
    else:
        (scores, badges), solved = await asyncio.gather(
            asyncio.to_thread(_score_user_steps, problem, steps),
            pipeline.run_solve(problem, mode="verify", score_chains=False),
        )
        verified_answer = solved["answer"]
        verified_solution = solved["verified_solution"]
        verified_steps = solved.get("verified_steps", [])
        confidence = solved["confidence"]

    # Did the student arrive at the verified answer?
    user_answer = segment.extract_answer(solution_text)
    is_correct = (
        consensus.normalize_answer(user_answer) == consensus.normalize_answer(verified_answer)
        and bool(user_answer)
    )

    if is_correct:
        return {
            "steps": steps, "scores": scores, "badges": badges,
            "error_step": None,
            "explanation": "Your answer matches the verified solution. Nice work — your reasoning checks out.",
            "verified_solution": verified_solution, "verified_answer": verified_answer,
            "verified_steps": verified_steps,
            "confidence": confidence, "is_correct": True, "error_type": None,
        }

    # Error step = PRM weakest link (confirms; never overrides the verified path)
    error_idx = int(min(range(len(scores)), key=lambda i: scores[i])) if scores else 0

    explanation = await generate.explain_error(problem, steps, error_idx)
    error_type = classify_error_type(steps[error_idx], explanation)

    return {
        "steps": steps,
        "scores": scores,
        "badges": badges,
        "error_step": error_idx + 1,  # 1-indexed for display
        "explanation": explanation,
        "verified_solution": verified_solution,
        "verified_answer": verified_answer,
        "verified_steps": verified_steps,
        "confidence": confidence,
        "is_correct": False,
        "error_type": error_type,
        "topic": topics_mod.classify_topic(problem),
    }


async def build_hints(problem: str, level: int) -> Dict[str, Any]:
    """Hint ladder by slicing the verified solution. level in 1..4."""
    level = max(1, min(4, int(level)))
    # Greedy verify route — the hint ladder only slices one verified solution
    solved = await pipeline.run_solve(problem, mode="verify", score_chains=False)
    steps: List[str] = solved.get("verified_steps", []) or []
    topic = topics_mod.classify_topic(problem)

    if level == 1:
        hint = f"Concept: this is a {topics_mod.pretty(topic)} problem. {topics_mod.mini_lesson(topic)}"
    elif level == 2:
        if steps:
            first = re.sub(r"\s+", " ", steps[0]).strip()
            hint = f"Strategy: start by '{first[:160]}'. Plan the remaining steps from there."
        else:
            hint = "Strategy: identify what is given, what is asked, and the rule that links them."
    elif level == 3:
        hint = f"First step: {steps[0]}" if steps else "Begin by isolating the key quantity."
    else:  # level 4 — full solution
        hint = solved.get("verified_solution") or "\n".join(f"Step {i+1}: {s}" for i, s in enumerate(steps))

    return {"hint": hint, "level": level, "topic": topic}
