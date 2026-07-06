"""
Core test-time-scaling solve pipeline (IMPLEMENTATION.md §0, §3.4, §3.5).

   route -> generate N chains -> PRM-score each chain's steps
         -> PRM-weighted consensus vote -> isotonic calibration
         -> (auto only) escalate if agreement < 0.5

Shared by /solve, /checkwork (verified solution), /hint, and the quiz generator.
Non-streaming request/response — stage progress is surfaced by the Streamlit
`st.status` UI, not a token stream.
"""
import asyncio
from typing import Dict, Any, List

from . import generate
from . import prm_scoring
from . import consensus
from . import calibration
from . import router as router_mod

ESCALATION_AGREEMENT_THRESHOLD = 0.5


def _score_chains(problem: str, chains: List[Dict[str, Any]]) -> str:
    """Attach PRM scores/badges to every chain in place, in ONE batched PRM pass.
    Returns the verifier tag used."""
    steps_list = [chain.get("steps", []) for chain in chains]
    if not any(steps_list):
        for chain in chains:
            chain["scores"], chain["badges"] = [], []
        return "1.5b-torch"
    try:
        prm = prm_scoring.score_steps_batch(problem, steps_list)
        for chain, sc, bd in zip(chains, prm["scores"], prm["badges"]):
            chain["scores"], chain["badges"] = sc, bd
        return prm.get("verifier", "1.5b-torch")
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ PRM batch scoring failed: {e}")
        for chain in chains:
            n = len(chain.get("steps", []))
            chain["scores"] = [0.5] * n
            chain["badges"] = ["amber"] * n
        return "1.5b-torch"


def _weakest_link(chains: List[Dict[str, Any]]) -> Dict[str, int]:
    """Global weakest step across all chains (chain index + step index)."""
    weakest = {"chain": 0, "step": 0}
    min_score = 2.0
    for ci, chain in enumerate(chains):
        for si, s in enumerate(chain.get("scores", [])):
            if s < min_score:
                min_score = s
                weakest = {"chain": ci, "step": si}
    return weakest


async def run_solve(problem: str, mode: str = "auto", score_chains: bool = True) -> Dict[str, Any]:
    """Full solve. Returns answer, calibrated confidence, route, chains, escalation flag,
    weakest step, verifier tag, and the representative verified solution text.

    score_chains=False skips PRM-scoring the generated chains — used by the greedy
    'verify' route (check-my-work / hints), where a single chain is the answer
    regardless of its PRM score, so scoring it would be dead work. Consensus and
    the representative-chain pick both degrade gracefully to unscored chains."""
    rt = router_mod.route(problem, mode)

    chains = await generate.generate_chains(problem, rt.n, rt.temperature)
    verifier = _score_chains(problem, chains) if score_chains else "unscored"

    best_answer, agreement, tally = consensus.run_consensus(chains)
    escalated = False

    # Escalation (auto only): low agreement -> generate more chains up to the cap.
    if rt.escalatable and agreement < ESCALATION_AGREEMENT_THRESHOLD:
        target = min(rt.n * 2, router_mod.N_CAP_FREE)
        extra = target - rt.n
        if extra > 0:
            more = await generate.generate_chains(problem, extra, rt.temperature)
            if score_chains:
                _score_chains(problem, more)
            chains.extend(more)
            best_answer, agreement, tally = consensus.run_consensus(chains)
            escalated = True

    confidence = calibration.calibrate(agreement)

    # Representative verified solution = the highest-weight chain matching the winning answer.
    verified_chain = _representative_chain(chains, best_answer)

    return {
        "answer": best_answer,
        "confidence": confidence,
        "agreement": agreement,
        "route": rt.strategy,
        "n_used": len(chains),
        "escalated": escalated,
        "advisory": rt.advisory,
        "verifier": verifier,
        "tally": tally,
        "chains": chains,
        "weakest": _weakest_link(chains),
        "verified_solution": verified_chain.get("text", "") if verified_chain else "",
        "verified_steps": verified_chain.get("steps", []) if verified_chain else [],
    }


def _representative_chain(chains: List[Dict[str, Any]], best_answer: str) -> Dict[str, Any]:
    norm_best = consensus.normalize_answer(best_answer)
    best, best_w = None, -1.0
    for chain in chains:
        if consensus.normalize_answer(chain.get("answer", "")) != norm_best:
            continue
        scores = chain.get("scores", [])
        w = min(scores) if scores else 0.0
        if w > best_w:
            best_w, best = w, chain
    if best is None:
        # fall back to any chain
        best = chains[0] if chains else None
    return best


def run_solve_sync(problem: str, mode: str = "auto") -> Dict[str, Any]:
    """Convenience sync wrapper for scripts/tests."""
    return asyncio.run(run_solve(problem, mode))
