"""
Check-my-work + hint ladder (IMPLEMENTATION.md §9.1, §9.2).
Calls POST /checkwork to localize the error against a verified solution, and
POST /hint for the progressive hint ladder.
"""
import streamlit as st

from lib import api, render

st.set_page_config(page_title="Check My Work", page_icon="📝", layout="wide")
from lib import theme
theme.apply_theme()
st.title("📝 Check My Work")

if not st.session_state.get("token"):
    st.warning("Please login first.")
    st.stop()

problem = st.text_area("Problem", height=80, key="cw_problem",
                       placeholder="What problem were you solving?")
solution = st.text_area("Your solution (number steps as 'Step 1:', 'Step 2:' …)", height=200,
                        key="cw_solution", placeholder="Step 1: ...\nStep 2: ...\nFinal Answer: ...")

if st.button("🔍 Check my work", type="primary"):
    if not problem.strip() or not solution.strip():
        st.error("Enter both the problem and your solution.")
        st.stop()
    try:
        with st.spinner("Analyzing your work against a verified solution…"):
            res = api.checkwork(problem, solution)
    except Exception as e:  # noqa: BLE001
        st.error(f"Check failed: {e}")
        st.stop()

    if res.get("is_correct"):
        st.success(res.get("explanation", "Correct — your reasoning checks out!"))
    else:
        es = res.get("error_step")
        st.error(f"❌ First problem at **Step {es}**"
                 + (f" · likely a *{res['error_type']}* error" if res.get("error_type") else ""))
        if res.get("explanation"):
            st.markdown(res["explanation"])

    view = st.radio("View", ["🔀 Diff view", "📋 List view"], horizontal=True, key="cw_view")
    if view.startswith("🔀"):
        render.render_diff(
            res.get("steps", []), res.get("scores", []), res.get("badges", []),
            res.get("verified_steps", []), res.get("error_step"),
        )
    else:
        st.markdown("### Your steps (PRM-scored)")
        render.render_solution(res.get("steps", []), res.get("scores", []), res.get("badges", []))

    if res.get("verified_solution"):
        with st.expander("See the engine's full verified solution"):
            st.markdown(res["verified_solution"])
    st.caption(f"Verified answer: {res.get('verified_answer', '—')} · "
               f"confidence {res.get('confidence', 0) * 100:.0f}%")

st.divider()
st.markdown("### 💡 Stuck? Climb the hint ladder")
st.caption("L1 concept → L2 strategy → L3 first step → L4 full solution")
level = st.select_slider("Hint level", options=[1, 2, 3, 4], value=1)
if st.button("Get hint"):
    if not problem.strip():
        st.error("Enter the problem first.")
    else:
        try:
            with st.spinner("Building hint…"):
                h = api.hint(problem, int(level))
            st.info(h.get("hint", "(no hint)"))
        except Exception as e:  # noqa: BLE001
            st.error(f"Hint failed: {e}")
