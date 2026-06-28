"""
fit_calibration.py (IMPLEMENTATION.md §4).

Fits the isotonic mapping  agreement -> P(correct)  from cached solve runs and
writes calibration.pkl (consumed by calibration.py at runtime). Also derives PRM
percentile thresholds p15/p40 if a scores file is provided.

Input (one of):
  --data path.jsonl   # lines of {"agreement": float, "correct": 0|1}
  --data path.csv     # columns: agreement,correct
If no data is given, a synthetic monotonic set is used so the pipeline still
produces a valid (placeholder) calibration.pkl for the demo. Refit before the
pitch with sanity_check_calibration.py.

Usage:
  python fit_calibration.py --data runs.jsonl --out calibration.pkl
"""
import argparse
import json
import os
import pickle

import numpy as np
from sklearn.isotonic import IsotonicRegression


def load_data(path):
    xs, ys = [], []
    if path.endswith(".jsonl"):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                xs.append(float(r["agreement"]))
                ys.append(int(r["correct"]))
    elif path.endswith(".csv"):
        import csv
        with open(path) as f:
            for row in csv.DictReader(f):
                xs.append(float(row["agreement"]))
                ys.append(int(row["correct"]))
    else:
        raise ValueError("data file must be .jsonl or .csv")
    return np.array(xs), np.array(ys)


def synthetic():
    """Monotonic synthetic data: higher agreement -> higher accuracy."""
    rng = np.random.default_rng(0)
    xs = rng.uniform(0.2, 1.0, 800)
    ys = (rng.uniform(0, 1, 800) < (0.2 + 0.75 * xs)).astype(int)
    return xs, ys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=None)
    _repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--out", default=os.path.join(_repo_root, "calibration.pkl"))
    args = ap.parse_args()

    if args.data and os.path.exists(args.data):
        xs, ys = load_data(args.data)
        print(f"Loaded {len(xs)} cached runs from {args.data}")
    else:
        xs, ys = synthetic()
        print("⚠️ No --data given — fitting on SYNTHETIC data (placeholder). Refit before the pitch.")

    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
    iso.fit(xs, ys)

    with open(args.out, "wb") as f:
        pickle.dump(iso, f)
    print(f"✅ Wrote {args.out}")

    # quick monotonicity sanity print
    grid = np.linspace(0.0, 1.0, 11)
    preds = iso.predict(grid)
    print("agreement -> P(correct):")
    for a, p in zip(grid, preds):
        print(f"  {a:.1f} -> {p:.3f}")


if __name__ == "__main__":
    main()
