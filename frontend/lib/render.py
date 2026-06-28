"""
Rendering helpers (IMPLEMENTATION.md §3.7).

render_solution(): per-step colored PRM badge + LaTeX, with a sanitize/try-except
so a malformed step degrades to st.code instead of blanking the page.
"""
import re

import streamlit as st

_BAND_COLOR = {"green": "green", "amber": "orange", "red": "red"}


def sanitize_latex(s: str) -> str:
    """Best-effort cleanup: normalize \\( \\) / $$ delimiters and balance braces."""
    s = s.strip()
    s = s.replace("\\(", "").replace("\\)", "").replace("$$", "").replace("$", "")
    # balance curly braces so st.latex doesn't choke on a stray brace
    opens = s.count("{")
    closes = s.count("}")
    if opens > closes:
        s += "}" * (opens - closes)
    elif closes > opens:
        s = "{" * (closes - opens) + s
    return s


def _looks_mathy(s: str) -> bool:
    return bool(re.search(r"[=+\-*/^\\]|\\frac|\\sqrt|\d", s))


def render_step(idx: int, step: str, score=None, badge: str = "amber"):
    band = (badge or "amber").split("|")[0]
    color = _BAND_COLOR.get(band, "orange")
    weak = "weakest_link" in (badge or "")
    label = f":{color}[●] **Step {idx + 1}**"
    if score is not None:
        label += f" · PRM {score:.2f}"
    if weak:
        label += " · :red[⚠️ weakest link]"
    st.markdown(label)
    if step.strip():
        try:
            if _looks_mathy(step):
                st.latex(sanitize_latex(step))
            else:
                st.markdown(step)
        except Exception:  # noqa: BLE001 — never let one bad step blank the page
            st.code(step)


def render_solution(steps, scores=None, badges=None):
    scores = scores or []
    badges = badges or []
    for i, step in enumerate(steps):
        render_step(
            i, step,
            score=scores[i] if i < len(scores) else None,
            badge=badges[i] if i < len(badges) else "amber",
        )


def confidence_gauge(confidence: float, label: str = "Calibrated confidence"):
    st.metric(label, f"{confidence * 100:.0f}%")
    st.progress(min(1.0, max(0.0, float(confidence))))
