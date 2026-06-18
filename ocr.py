"""
OCR (IMPLEMENTATION.md §3.8) — pix2tex (LaTeX-OCR) on the engine.
Lazy import so a missing/heavy dependency never blocks engine startup; the user
edits the LaTeX before solving, so OCR is best-effort.
"""
import base64
import io
from typing import Optional

_model = None
_load_failed = False


def _get_model():
    global _model, _load_failed
    if _model is not None or _load_failed:
        return _model
    try:
        from pix2tex.cli import LatexOCR  # heavy import
        _model = LatexOCR()
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ pix2tex unavailable: {e}")
        _load_failed = True
        _model = None
    return _model


def image_to_latex(image_b64: str) -> Optional[str]:
    """Decode a base64 image and return recognized LaTeX, or None if unavailable."""
    model = _get_model()
    if model is None:
        return None
    try:
        from PIL import Image
        raw = base64.b64decode(image_b64.split(",")[-1])
        img = Image.open(io.BytesIO(raw))
        return model(img)
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ OCR failed: {e}")
        return None
