"""
Calibration (IMPLEMENTATION.md §3.4).
Isotonic mapping  agreement -> P(correct), fit offline by fit_calibration.py
into calibration.pkl. At runtime we load the model and map raw consensus
agreement to a calibrated confidence. Falls back to identity if no model is
present, so the engine always returns *something* sane.
"""
import os
import pickle

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CAL_PATH = os.environ.get("CALIBRATION_PATH", os.path.join(_REPO_ROOT, "calibration.pkl"))
_model = None
_loaded = False


def _load():
    global _model, _loaded
    if _loaded:
        return
    _loaded = True
    if os.path.exists(_CAL_PATH):
        try:
            with open(_CAL_PATH, "rb") as f:
                _model = pickle.load(f)
            print(f"✅ Calibration model loaded from {_CAL_PATH}")
        except Exception as e:  # noqa: BLE001
            print(f"⚠️ Failed to load calibration model: {e} — using identity")
            _model = None
    else:
        print("ℹ️ No calibration.pkl found — confidence == raw agreement (identity)")


def calibrate(agreement: float) -> float:
    """Map a raw consensus agreement (0..1) to a calibrated P(correct)."""
    _load()
    a = max(0.0, min(1.0, float(agreement)))
    if _model is None:
        return a
    try:
        # sklearn IsotonicRegression exposes .predict
        val = float(_model.predict([a])[0])
        return max(0.0, min(1.0, val))
    except Exception:  # noqa: BLE001
        return a


def is_fitted() -> bool:
    _load()
    return _model is not None
