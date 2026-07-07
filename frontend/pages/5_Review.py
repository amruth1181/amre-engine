"""
Spaced Repetition Review (feature 1.1).
Surfaces problems due today (SM-2), lets the student re-attempt and check, then
self-rate recall (Again / Hard / Good / Easy) to reschedule the next review.
"""
import streamlit as st

from lib import api, render

st.set_page_config(page_title="Review", page_icon="🔁", layout="wide")
from lib import theme
theme.apply_theme()
st.title("🔁 Spaced Repetition Review")

if not st.session_state.get("token"):
    st.warning("Please login first.")
    st.stop()

st.caption("Weak problems resurface on a schedule (SM-2 algorithm). Re-solve, check your work, "
           "then rate how well you recalled it — the interval grows as you succeed.")

try:
    cards = api.review_due().get("cards", [])
except Exception as e:  # noqa: BLE001
    st.error(f"Could not load your review queue: {e}")
    st.stop()

if not cards:
    st.success("🎉 Nothing due for review right now. Log a few mistakes and check back tomorrow!")
    st.stop()

idx = st.session_state.get("rev_idx", 0)
if idx >= len(cards):
    st.session_state["rev_idx"] = 0
    idx = 0
card = cards[idx]

st.info(f"{len(cards)} card(s) due today · showing card {idx + 1} of {len(cards)}")
st.markdown(f"**Topic:** {str(card.get('topic', '')).replace('_', ' ').title() or '—'}")
st.markdown(f"### {card['problem']}")

with st.expander("✍️ Attempt it and check your work", expanded=True):
    sol = st.text_area("Your solution (number steps as 'Step 1:', 'Step 2:' …)",
                       height=160, key=f"rev_sol_{card['id']}")
    if st.button("🔍 Check", key=f"rev_check_{card['id']}"):
        if sol.strip():
            with st.spinner("Checking against a verified solution…"):
                res = api.checkwork(card["problem"], sol)
            if res.get("is_correct"):
                st.success("Correct — nice recall!")
            else:
                st.error(f"First problem at Step {res.get('error_step')}.")
            render.render_diff(res.get("steps", []), res.get("scores", []), res.get("badges", []),
                               res.get("verified_steps", []), res.get("error_step"))
        else:
            st.warning("Enter your solution first.")

st.markdown("#### How well did you recall this?")
cols = st.columns(4)
for col, (label, quality, hint) in zip(cols, [
    ("😵 Again", 1, "forgot"), ("😓 Hard", 3, "struggled"),
    ("🙂 Good", 4, "got it"), ("😎 Easy", 5, "instant"),
]):
    if col.button(label, key=f"rev_{quality}_{card['id']}", use_container_width=True, help=hint):
        try:
            r = api.review_grade(card["id"], quality)
            nxt = r.get("interval", "?")
            st.success(f"Scheduled — next review in {nxt} day(s).")
        except Exception as e:  # noqa: BLE001
            st.error(f"Could not save: {e}")
        st.session_state["rev_idx"] = idx + 1
        st.rerun()
