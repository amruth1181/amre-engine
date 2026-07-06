"""
Verified quiz generator (IMPLEMENTATION.md §9.3) — the unique piece.

LLM over-generates candidate questions -> we sample a few reasoning chains per
candidate and keep only questions whose answer is *self-consistent* (>= AGREEMENT_MIN
of the chains agree) -> ship up to SHIP_COUNT. The agreeing answer becomes the
grading key.

Self-consistency here is *content QC* — we only quiz on problems the engine
answers confidently. Crucially this needs the ANSWER agreement, not PRM step
scores, so we skip the (CPU-heavy) verifier entirely: on the free CPU Space,
PRM-scoring 12 candidates x 8 chains was ~96 forward passes and timed out.
Cached by topic to avoid re-paying generation cost.
"""
import asyncio
import time
from typing import Dict, Any, List

from . import generate
from . import consensus

OVERGEN = 8            # candidates to author (ONE LLM call authors all of them)
SHIP_COUNT = 5         # verified questions to ship
QUIZ_N = 5             # self-consistency chains per candidate (no PRM — QC only)
AGREEMENT_MIN = 0.6    # keep a question if >= 60% of its chains agree on the answer
QUIZ_CONCURRENCY = 6   # cap concurrent candidate-solves so we don't storm Groq's rate limit

_cache: Dict[str, Dict[str, Any]] = {}
_CACHE_TTL = 60 * 60  # 1h


async def _verify_question(question: str, sem: asyncio.Semaphore) -> Dict[str, Any]:
    """Self-consistency QC WITHOUT the PRM: sample QUIZ_N chains and take the
    majority answer + its agreement. The quiz needs a confident verified answer,
    not per-step PRM scores, so the verifier is skipped (that was the timeout)."""
    async with sem:
        chains = await generate.generate_chains(question, QUIZ_N, temperature=0.8)
    # unweighted vote: with no PRM scores, consensus agreement = fraction of
    # chains that landed on the winning answer — exactly the self-consistency QC.
    best, agreement, _ = consensus.run_consensus(chains)
    return {"question": question, "verified_answer": best, "agreement": agreement}


async def generate_verified_quiz(topic: str, ship: int = SHIP_COUNT) -> List[Dict[str, str]]:
    """Return a list of {question, verified_answer} that passed verification."""
    cached = _cache.get(topic)
    if cached and (time.time() - cached["ts"] < _CACHE_TTL):
        return cached["questions"][:ship]

    candidates = await generate.generate_quiz_questions(topic, OVERGEN)
    if not candidates:
        return []

    # verify candidates concurrently (bounded), keep the self-consistent ones
    sem = asyncio.Semaphore(QUIZ_CONCURRENCY)
    results = await asyncio.gather(
        *[_verify_question(q, sem) for q in candidates], return_exceptions=True
    )
    verified: List[Dict[str, str]] = []
    for r in results:
        if isinstance(r, Exception):
            continue
        if r["agreement"] >= AGREEMENT_MIN and r["verified_answer"] not in ("", "Error"):
            verified.append({"question": r["question"], "verified_answer": r["verified_answer"]})
        if len(verified) >= ship:
            break

    _cache[topic] = {"ts": time.time(), "questions": verified}
    return verified[:ship]
