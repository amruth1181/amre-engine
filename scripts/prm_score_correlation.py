"""
prm_score_correlation.py (IMPLEMENTATION.md §4).

Measures how well the deployed 1.5B ONNX PRM floor tracks the preferred 7B
Math-PRM, so we know whether the floor's badges are trustworthy. Computes the
Spearman rank correlation ρ between paired step scores and prints the pitch
verdict:

    ρ ≥ 0.80  -> show badges normally
    0.60–0.80 -> show badges as "indicative"
    ρ < 0.60  -> weights-only (don't surface per-step colors)

Two input modes:
  --pairs scores.jsonl   each line {"score_7b": float, "score_1p5b": float}
                         (use this offline from a cached run — the cheap path)
  --chains chains.jsonl  each line {"problem": str, "steps": [str, ...]}
                         scores every step live with BOTH backends
                         (needs COLAB_PRM_URL for the 7B + the ONNX floor)

Usage:
  python scripts/prm_score_correlation.py --pairs runs/prm_pairs.jsonl
  python scripts/prm_score_correlation.py --chains runs/math_chains.jsonl
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _rankdata(a):
    """Average-rank of a 1-D array (ties share the mean rank). Avoids a scipy dep."""
    a = np.asarray(a, dtype=float)
    order = a.argsort()
    ranks = np.empty(len(a), dtype=float)
    ranks[order] = np.arange(1, len(a) + 1)
    # average tied ranks
    _, inv, counts = np.unique(a, return_inverse=True, return_counts=True)
    sums = np.zeros(len(counts))
    np.add.at(sums, inv, ranks)
    return (sums / counts)[inv]


def spearman(x, y):
    rx, ry = _rankdata(x), _rankdata(y)
    rx, ry = rx - rx.mean(), ry - ry.mean()
    denom = np.sqrt((rx ** 2).sum() * (ry ** 2).sum())
    return float((rx * ry).sum() / denom) if denom else 0.0


def load_pairs(path):
    s7, s15 = [], []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            s7.append(float(r["score_7b"]))
            s15.append(float(r["score_1p5b"]))
    return s7, s15


def score_chains(path):
    """Score each chain's steps with both PRMs and pair them up step-by-step."""
    from app import prm_local
    from app.prm_scoring import ColabPRM

    colab = ColabPRM()
    if not colab.healthy():
        print("⚠️ Colab 7B PRM unreachable (set COLAB_PRM_URL). Cannot pair live — "
              "use --pairs with cached 7B scores instead.")
        sys.exit(2)

    s7, s15 = [], []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            problem, steps = r["problem"], r["steps"]
            if not steps:
                continue
            a = colab.score_steps(problem, steps)
            b = prm_local.score_steps(problem, steps)
            n = min(len(a), len(b))
            s7.extend(a[:n])
            s15.extend(b[:n])
    return s7, s15


def verdict(rho):
    if rho >= 0.80:
        return "ρ ≥ 0.80 → show per-step badges NORMALLY."
    if rho >= 0.60:
        return "0.60 ≤ ρ < 0.80 → label per-step badges as INDICATIVE."
    return "ρ < 0.60 → WEIGHTS-ONLY; do not surface per-step colors from the floor."


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", help="jsonl of {score_7b, score_1p5b}")
    ap.add_argument("--chains", help="jsonl of {problem, steps[]} to score live with both PRMs")
    args = ap.parse_args()

    if args.pairs and os.path.exists(args.pairs):
        s7, s15 = load_pairs(args.pairs)
    elif args.chains and os.path.exists(args.chains):
        s7, s15 = score_chains(args.chains)
    else:
        ap.error("provide --pairs <file> or --chains <file>")

    if len(s7) < 10:
        print(f"⚠️ only {len(s7)} paired scores — ρ will be noisy (spec wants ~200 chains).")

    rho = spearman(s7, s15)
    print(f"paired step scores: {len(s7)}")
    print(f"Spearman ρ (7B vs 1.5B): {rho:.3f}")
    print(verdict(rho))


if __name__ == "__main__":
    main()
