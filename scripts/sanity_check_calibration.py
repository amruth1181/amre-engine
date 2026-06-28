"""
sanity_check_calibration.py (IMPLEMENTATION.md §4).

Runs ~100 problems through the REAL production solve path, bins the calibrated
confidence against actual correctness, and accepts the calibration if every
populated bin has |predicted − actual| < 5pp. Otherwise it tells you to refit
(scripts/fit_calibration.py) on real cached runs.

Note (spec): AIME (n≈30) is too small for the hard regime — treat hard-bin
confidence as extrapolative, not validated.

Input:
  --data problems.jsonl   each line {"problem": str, "gold": str}
  --mode auto|balanced|careful   solve mode to validate (default: balanced)

Usage:
  python scripts/sanity_check_calibration.py --data runs/labeled_100.jsonl
"""
import argparse
import asyncio
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import pipeline, consensus  # noqa: E402

TOL_PP = 5.0  # acceptance tolerance, percentage points per bin
BINS = [(0.0, 0.5), (0.5, 0.7), (0.7, 0.85), (0.85, 1.0001)]


def load(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


async def run(rows, mode):
    preds, correct = [], []
    for i, r in enumerate(rows):
        res = await pipeline.run_solve(r["problem"], mode)
        ok = consensus.normalize_answer(res["answer"]) == consensus.normalize_answer(str(r["gold"]))
        preds.append(res["confidence"])
        correct.append(1 if ok else 0)
        print(f"  [{i+1}/{len(rows)}] conf={res['confidence']:.2f} {'✓' if ok else '✗'}")
    return np.array(preds), np.array(correct)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="jsonl of {problem, gold}")
    ap.add_argument("--mode", default="balanced", choices=["auto", "balanced", "careful"])
    args = ap.parse_args()

    rows = load(args.data)
    print(f"Validating calibration on {len(rows)} problems (mode={args.mode})…")
    preds, correct = asyncio.run(run(rows, args.mode))

    print("\nbin            n   pred_conf  actual_acc   |Δ|pp")
    worst = 0.0
    for lo, hi in BINS:
        mask = (preds >= lo) & (preds < hi)
        n = int(mask.sum())
        if n == 0:
            print(f"[{lo:.2f},{hi:.2f})   0        —          —        —")
            continue
        pred_conf = float(preds[mask].mean())
        actual = float(correct[mask].mean())
        delta = abs(pred_conf - actual) * 100
        worst = max(worst, delta)
        flag = "" if delta < TOL_PP else "  <-- off"
        print(f"[{lo:.2f},{hi:.2f})  {n:>3}    {pred_conf:6.3f}    {actual:6.3f}   {delta:6.1f}{flag}")

    print(f"\nworst bin error: {worst:.1f}pp (tolerance {TOL_PP}pp)")
    if worst < TOL_PP:
        print("✅ ACCEPT — calibration is within tolerance.")
    else:
        print("❌ REFIT — run scripts/fit_calibration.py on real cached runs, then re-check.")
        sys.exit(1)


if __name__ == "__main__":
    main()
