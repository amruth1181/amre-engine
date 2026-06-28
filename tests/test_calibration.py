"""Calibration behaviour (IMPLEMENTATION.md §3.4, §6)."""
import pickle

import numpy as np
from sklearn.isotonic import IsotonicRegression

from app import calibration


def test_identity_fallback_when_no_model(monkeypatch):
    # force the no-model path
    monkeypatch.setattr(calibration, "_model", None, raising=False)
    monkeypatch.setattr(calibration, "_loaded", True, raising=False)
    assert calibration.calibrate(0.8) == 0.8


def test_output_clamped_to_unit_interval(monkeypatch):
    monkeypatch.setattr(calibration, "_model", None, raising=False)
    monkeypatch.setattr(calibration, "_loaded", True, raising=False)
    assert calibration.calibrate(1.5) == 1.0
    assert calibration.calibrate(-0.2) == 0.0


def test_isotonic_is_monotonic(monkeypatch, tmp_path):
    # fit a real isotonic model and assert calibrate() is non-decreasing
    rng = np.random.default_rng(0)
    xs = rng.uniform(0.2, 1.0, 500)
    ys = (rng.uniform(0, 1, 500) < (0.2 + 0.75 * xs)).astype(int)
    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip").fit(xs, ys)

    monkeypatch.setattr(calibration, "_model", iso, raising=False)
    monkeypatch.setattr(calibration, "_loaded", True, raising=False)

    grid = [i / 20 for i in range(21)]
    preds = [calibration.calibrate(a) for a in grid]
    assert all(b >= a - 1e-9 for a, b in zip(preds, preds[1:])), "calibration must be monotonic"
