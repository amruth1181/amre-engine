"""
Solve page (IMPLEMENTATION.md §3.7, §3.8).

Request/response to POST /solve with st.status stage progress (replaces the old
WebSocket stream). Optional OCR: upload/snap an image -> editable LaTeX -> solve.
"""
import base64

import requests
import streamlit as st

from lib import api, render

st.set_page_config(page_title="Solve", page_icon="🔢", layout="wide")
from lib import theme
theme.apply_theme()
st.title("🔢 Solve a Math Problem")

if not st.session_state.get("token"):
    st.warning("Please login first.")
    st.stop()

MODES = {
    "Auto (router decides)": "auto",
    "Fast (greedy, 1 sample)": "fast",
    "Balanced (8 samples)": "balanced",
    "Careful (32 samples)": "careful",
}

# ---- optional OCR ----
with st.expander("📷 Scan a problem from an image (OCR)"):
    img = st.file_uploader("Upload an image", type=["png", "jpg", "jpeg"])
    cam = st.camera_input("…or take a photo")
    src = cam or img
    if src is not None and st.button("Extract LaTeX"):
        try:
            b64 = base64.b64encode(src.getvalue()).decode()
            latex = api.ocr(b64).get("latex", "")
            st.session_state["solve_problem"] = latex
            st.success("Extracted — review/edit it below before solving.")
        except requests.HTTPError as e:
            st.error("OCR unavailable on this engine instance." if e.response.status_code == 503
                     else f"OCR error: {e.response.text}")
        except Exception as e:  # noqa: BLE001
            st.error(f"OCR error: {e}")

problem = st.text_area("Problem", height=110, key="solve_problem",
                       placeholder="Example: Solve for x: 2x + 5 = 15")
mode_label = st.radio("Mode", list(MODES.keys()), horizontal=True)
use_prm = st.toggle(
    "🔬 Verify steps with the PRM",
    value=False,  # default OFF for speed; flip ON to showcase per-step verification
    help="ON: PRM scores each step and weights the vote (the test-time-compute demo) — slower on CPU. "
         "OFF: faster — just the answer + explanation with a plain majority vote (no per-step scores). "
         "Fast/greedy mode gains nothing from the PRM, so turn it off there.",
)
st.caption("✅ PRM on = per-step confidence + weighted vote (slower) · ⚡ PRM off = faster, answer + explanation only")

if st.button("🚀 Solve", type="primary"):
    if not problem.strip():
        st.error("Please enter a problem.")
        st.stop()

    try:
        with st.status("Solving…", expanded=True) as status:
            status.write("Routing → generating samples…" + ("" if use_prm else " (PRM off — fast)"))
            res = api.solve(problem, MODES[mode_label], use_prm)
            status.write(
                f"Generated {res['n_used']} samples · scored steps · voted"
                + (" · escalated 🔼" if res.get("escalated") else "")
            )
            status.update(label="Done ✅", state="complete")
    except Exception as e:  # noqa: BLE001
        st.error(f"Solve failed: {e}")
        st.stop()

    # ---- verdict ----
    c1, c2, c3 = st.columns(3)
    c1.metric("Answer", res.get("answer", "—"))
    with c2:
        render.confidence_gauge(res.get("confidence", 0.0))
    c3.metric("Route", f"{res.get('route', '?')} · N={res.get('n_used', '?')}")

    meta = []
    if res.get("verifier") and res["verifier"] != "unscored":
        meta.append(f"scored by **{res['verifier']}**")
    elif not use_prm:
        meta.append("PRM off · plain majority vote")
    if res.get("agreement") is not None:
        meta.append(f"agreement {res['agreement'] * 100:.0f}%")
    if res.get("advisory"):
        meta.append(res["advisory"])
    if meta:
        st.caption(" · ".join(meta))

    # ---- verified solution (representative chain, color-coded) ----
    chains = res.get("chains", [])
    weak = res.get("weakest_step", {}) or {}
    if chains:
        wc = weak.get("chain", 0)
        rep = chains[wc] if wc < len(chains) else chains[0]
        st.markdown("### ✅ Verified solution")
        render.render_solution(rep.get("steps", []), rep.get("scores", []), rep.get("badges", []))
        if rep.get("steps") and rep.get("scores"):
            st.caption(f"Weakest link: step {weak.get('step', 0) + 1}")

        with st.expander(f"See all {len(chains)} candidate chains"):
            for i, ch in enumerate(chains):
                st.markdown(f"**Chain {i + 1}** → answer `{ch.get('answer', '?')}`")
                render.render_solution(ch.get("steps", []), ch.get("scores", []), ch.get("badges", []))
                st.divider()
