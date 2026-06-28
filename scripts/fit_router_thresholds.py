"""
fit_router_thresholds.py (IMPLEMENTATION.md §4).

Calibrates the cheap difficulty estimator used by the router from labeled
problems and writes router_params.json (loaded by app/router.py at runtime).
≥80% regime accuracy is fine — escalation catches the misses.

Regimes (spec): GSM8K -> easy, MATH L1–3 -> medium, MATH L4–5 -> hard
(~200+ at L4–5); AIME is an extreme anchor only, not its own regime.

Input:
  --data labeled.jsonl   each line {"problem": str, "regime": "easy|medium|hard"}

If no data is given, a small built-in sample is used so the pipeline still
produces a valid router_params.json (refit on real data before the pitch).

Usage:
  python scripts/fit_router_thresholds.py --data runs/regime_labeled.jsonl
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# keep these in sync with the runtime default in app/router.py
COMPLEX_KEYWORDS = [
    "integral", "derivative", "prove", "matrix", "combinatorics",
    "probability", "quadratic", "logarithm", "sequence", "series",
]
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH = os.path.join(_REPO_ROOT, "router_params.json")


def features(problem):
    return {
        "len": len(problem),
        "complex": any(k in problem.lower() for k in COMPLEX_KEYWORDS),
        "latex": ("$" in problem or "\\" in problem),
    }


def classify(f, max_len_easy, max_len_medium):
    if f["len"] < max_len_easy and not f["complex"] and not f["latex"]:
        return "easy"
    if f["len"] < max_len_medium and not f["complex"]:
        return "medium"
    return "hard"


def load(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def sample():
    return [
        {"problem": "What is 25% of 80?", "regime": "easy"},
        {"problem": "Solve for x: 2x + 5 = 15", "regime": "easy"},
        {"problem": "A bag has 3 red and 2 blue balls. What is P(red)?", "regime": "medium"},
        {"problem": "Factor the quadratic x^2 + 5x + 6 and state its roots.", "regime": "medium"},
        {"problem": "Prove that the integral of x^2 from 0 to 1 equals 1/3 using Riemann sums.", "regime": "hard"},
        {"problem": "Find the number of permutations via combinatorics for arranging 7 distinct books.", "regime": "hard"},
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=None, help="jsonl of {problem, regime}")
    ap.add_argument("--out", default=OUT_PATH)
    args = ap.parse_args()

    if args.data and os.path.exists(args.data):
        rows = load(args.data)
        print(f"Loaded {len(rows)} labeled problems from {args.data}")
    else:
        rows = sample()
        print("⚠️ No --data given — fitting on a tiny built-in SAMPLE. Refit before the pitch.")

    feats = [(features(r["problem"]), r["regime"]) for r in rows]
    lens = sorted({f["len"] for f, _ in feats} | {50, 150})

    # grid-search the two length cutoffs to maximize regime accuracy
    best = (0.0, 50, 150)
    for e in lens:
        for m in lens:
            if m <= e:
                continue
            acc = sum(classify(f, e, m) == r for f, r in feats) / len(feats)
            if acc > best[0]:
                best = (acc, e, m)

    acc, max_len_easy, max_len_medium = best
    params = {
        "max_len_easy": max_len_easy,
        "max_len_medium": max_len_medium,
        "complex_keywords": COMPLEX_KEYWORDS,
        "regime_accuracy": round(acc, 3),
        "n_train": len(feats),
    }
    with open(args.out, "w") as f:
        json.dump(params, f, indent=2)

    print(f"✅ Wrote {args.out}")
    print(json.dumps(params, indent=2))
    if acc < 0.80:
        print("⚠️ regime accuracy < 80% — gather more labeled data (escalation still backstops).")


if __name__ == "__main__":
    main()
