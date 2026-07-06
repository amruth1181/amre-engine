"""
Rendering helpers (IMPLEMENTATION.md §3.7).

render_solution(): per-step colored PRM badge + LaTeX, with a normalize/try-except
so a malformed step degrades to st.code instead of blanking the page.
"""
import streamlit as st

_BAND_COLOR = {"green": "green", "amber": "orange", "red": "red"}


def normalize_math(s: str) -> str:
    r"""Convert \( \) and \[ \] delimiters to $ / $$ so Streamlit's KaTeX renders
    them inline within prose. $...$ and $$...$$ already pass through st.markdown,
    so a step like "subtract 5 to get $2x = 10$" renders text + math correctly."""
    s = s.strip()
    s = s.replace("\\(", "$").replace("\\)", "$")
    s = s.replace("\\[", "$$").replace("\\]", "$$")
    return s


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
            st.markdown(normalize_math(step))
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


def render_diff(student_steps, scores=None, badges=None, verified_steps=None, error_step=None):
    """Side-by-side diff: the student's steps (PRM color-coded) on the left, the
    engine's verified steps on the right, with the first-divergence step flagged."""
    scores = scores or []
    badges = badges or []
    verified_steps = verified_steps or []
    left, right = st.columns(2)
    with left:
        st.markdown("#### 🧑‍🎓 Your steps")
        for i, step in enumerate(student_steps):
            if error_step and (i + 1) == error_step:
                st.markdown(":red[**⬇ first divergence**]")
            render_step(
                i, step,
                score=scores[i] if i < len(scores) else None,
                badge=badges[i] if i < len(badges) else "amber",
            )
    with right:
        st.markdown("#### ✅ Verified solution")
        if verified_steps:
            for i, step in enumerate(verified_steps):
                st.markdown(f":green[●] **Step {i + 1}**")
                if step.strip():
                    try:
                        st.markdown(normalize_math(step))
                    except Exception:  # noqa: BLE001
                        st.code(step)
        else:
            st.caption("(No verified steps available for this problem.)")


def confidence_gauge(confidence: float, label: str = "Calibrated confidence"):
    st.metric(label, f"{confidence * 100:.0f}%")
    st.progress(min(1.0, max(0.0, float(confidence))))
