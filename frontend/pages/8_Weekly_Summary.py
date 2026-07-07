"""
Weekly Summary + in-app alerts (additive, read-only).
A supportive-coach weekly check-in built from GET /wellness: streak + reviews-due
alerts at the top, then an AI-written summary of the week's activity. Reads only —
touches none of the Solve / Check / Quiz flows.
"""
import streamlit as st

from lib import api

st.set_page_config(page_title="Weekly Summary", page_icon="∑", layout="wide")
from lib import theme
theme.apply_theme()
st.title("∑  Your Week")

if not st.session_state.get("token"):
    st.warning("Please login first.")
    st.stop()

st.caption("A weekly check-in from your study coach — your streak, what's due, and how your week went. "
           "This is encouragement, not a grade.")

if st.button("🔄 Refresh"):
    st.session_state.pop("wellness_data", None)

# fetch once per visit (cache in session so Refresh is explicit)
if "wellness_data" not in st.session_state:
    try:
        with st.spinner("Gathering your week…"):
            st.session_state["wellness_data"] = api.wellness()
    except Exception as e:  # noqa: BLE001
        st.error(f"Could not load your weekly summary (the engine may be waking up — try Refresh): {e}")
        st.stop()

data = st.session_state["wellness_data"]
alerts = data.get("alerts", {})
stats = data.get("stats", {})

# ---- in-app alerts ----
st.markdown("### 🔔 Alerts")
a1, a2, a3 = st.columns(3)
a1.metric("🔥 Day streak", alerts.get("streak", 0))
a2.metric("∮ Reviews due", alerts.get("cards_due", 0))
a3.metric("⭐ XP · Level", f"{alerts.get('xp', 0)} · L{alerts.get('level', 0)}")

cards_due = alerts.get("cards_due", 0)
streak = alerts.get("streak", 0)
if cards_due:
    st.warning(f"∮ You have **{cards_due}** review(s) due — clear them to keep your streak.")
    if st.button("Go to Review →"):
        st.switch_page("pages/5_Review.py")
if streak:
    st.success(f"🔥 You're on a **{streak}-day streak** — keep it alive!")

st.divider()

# ---- weekly coach summary ----
st.markdown("### ∑ This week")
st.info(data.get("summary", "No summary available yet."))

s1, s2, s3, s4 = st.columns(4)
s1.metric("📅 Days studied", stats.get("days_studied", 0))
s2.metric("∫ Problems solved", stats.get("problems_solved", 0))
s3.metric("≟ Mistakes caught", stats.get("mistakes_caught", 0))
s4.metric("🏆 Strongest day", stats.get("strongest_day") or "—")

top_topic = stats.get("top_topic")
if top_topic:
    st.caption(f"⊢ Topic to focus on next: **{top_topic}** — try a targeted quiz or review.")
