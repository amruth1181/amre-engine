"""
Verified quiz generator (IMPLEMENTATION.md §9.3) — the unique piece.

LLM over-generates candidate questions -> the engine solves each with the
self-consistency pipeline -> keep only questions whose solution is confident
(agreement >= AGREEMENT_MIN) -> ship up to SHIP_COUNT. Self-consistency is
used here as *content QC*: we only quiz on problems the engine can confidently
answer, and the verified answer becomes the grading key.

Cached by topic to avoid re-paying generation cost.
"""
import asyncio
import time
from typing import Dict, Any, List

from . import generate
from . import pipeline

OVERGEN = 12          # how many candidates to author
SHIP_COUNT = 5        # how many verified questions to ship
AGREEMENT_MIN = 0.75  # self-consistency threshold for "verified"
SOLVE_MODE = "balanced"

_cache: Dict[str, Dict[str, Any]] = {}
_CACHE_TTL = 60 * 60  # 1h


async def _verify_question(question: str) -> Dict[str, Any]:
    solved = await pipeline.run_solve(question, mode=SOLVE_MODE)
    return {
        "question": question,
        "verified_answer": solved["answer"],
        "agreement": solved["agreement"],
        "confidence": solved["confidence"],
    }


async def generate_verified_quiz(topic: str, ship: int = SHIP_COUNT) -> List[Dict[str, str]]:
    """Return a list of {question, verified_answer} that passed verification."""
    cached = _cache.get(topic)
    if cached and (time.time() - cached["ts"] < _CACHE_TTL):
        return cached["questions"][:ship]

    candidates = await generate.generate_quiz_questions(topic, OVERGEN)
    if not candidates:
        return []

    # verify candidates concurrently; keep the confident ones
    results = await asyncio.gather(*[_verify_question(q) for q in candidates], return_exceptions=True)
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
