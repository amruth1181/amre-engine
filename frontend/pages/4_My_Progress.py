"""
My-Progress dashboard (IMPLEMENTATION.md §3.7, §9.6, §10).
Per-user view built from GET /history and GET /journal: solve history,
error-type breakdown, weak-topic profile, and the mistake journal.
"""
import pandas as pd
import streamlit as st

from lib import api

st.set_page_config(page_title="My Progress", page_icon="📊", layout="wide")
st.title("📊 My Progress")

if not st.session_state.get("token"):
    st.warning("Please login first.")
    st.stop()

try:
    hist = api.history().get("history", [])
    jdata = api.journal()
    journal = jdata.get("journal", [])
    profile = jdata.get("profile", {})
except Exception as e:  # noqa: BLE001
    st.error(f"Could not load your data: {e}")
    st.stop()

# ---- headline metrics ----
c1, c2, c3 = st.columns(3)
c1.metric("Problems solved", len(hist))
c2.metric("Mistakes logged", profile.get("total_mistakes", 0))
weakest = profile.get("weakest_topics") or []
c3.metric("Weakest topic", weakest[0].replace("_", " ").title() if weakest else "—")

# ---- gamification: streak / XP / level / badges ----
st.markdown("### 🏆 Achievements")
try:
    g = api.gamify()
    a1, a2, a3 = st.columns(3)
    a1.metric("🔥 Day streak", g.get("streak", 0))
    a2.metric("⭐ XP", g.get("xp", 0))
    a3.metric("🎯 Level", g.get("level", 0))
    into = g.get("xp_into_level", 0)
    st.progress(min(1.0, into / 100.0),
                text=f"{g.get('xp_to_next', 100)} XP to level {g.get('level', 0) + 1}")
    badges = g.get("badges", [])
    if badges:
        st.markdown(" &nbsp; ".join(f"🎖️ **{b['badge']}**" for b in badges))
    else:
        st.caption("No badges yet — earn XP by solving, checking work, and taking quizzes.")
except Exception:  # noqa: BLE001
    st.caption("(Achievements unavailable right now.)")

# ---- error-type breakdown ("70% of your misses are sign errors") ----
st.markdown("### Error-type breakdown")
breakdown = profile.get("error_breakdown", {})
if breakdown:
    df = pd.DataFrame(
        [{"error_type": k, "count": v["count"], "pct": v["pct"]} for k, v in breakdown.items()]
    ).set_index("error_type")
    top = max(breakdown.items(), key=lambda kv: kv[1]["count"])
    st.caption(f"💡 {top[1]['pct']:.0f}% of your misses are **{top[0]}** errors.")
    st.bar_chart(df["count"])
else:
    st.info("No mistakes logged yet — check some work or take a quiz to build your profile.")

# ---- topic distribution ----
topic_counts = profile.get("topic_counts", {})
if topic_counts:
    st.markdown("### Mistakes by topic")
    st.bar_chart(pd.Series(topic_counts, name="count"))

# ---- solve history ----
st.markdown("### Recent solves")
if hist:
    hdf = pd.DataFrame(hist)
    cols = [c for c in ["ts", "problem", "mode", "route", "n_used", "answer", "confidence", "latency"]
            if c in hdf.columns]
    st.dataframe(hdf[cols], use_container_width=True, hide_index=True)
    if "confidence" in hdf.columns and len(hdf) > 1:
        st.markdown("#### Confidence over time")
        st.line_chart(hdf.sort_values("ts")["confidence"].reset_index(drop=True))
else:
    st.info("No solves yet — head to the Solve page!")

# ---- mistake journal ----
st.markdown("### 📓 Mistake journal")
if journal:
    jdf = pd.DataFrame(journal)
    cols = [c for c in ["ts", "topic", "error_type", "error_step", "problem", "explanation"]
            if c in jdf.columns]
    st.dataframe(jdf[cols], use_container_width=True, hide_index=True)
else:
    st.caption("Your journal is empty.")

# ---- study-sheet PDF export (§9.9) ----
st.markdown("### 📄 Study sheet")
st.caption("Download a revision PDF: your mistakes + explanations + reading material + recent quiz.")
if st.button("Generate study sheet"):
    try:
        with st.spinner("Building your study sheet…"):
            st.session_state["study_pdf"] = api.studysheet()
    except Exception as e:  # noqa: BLE001
        st.error(f"Could not generate study sheet: {e}")
if st.session_state.get("study_pdf"):
    st.download_button(
        "⬇️ Download study sheet (PDF)",
        data=st.session_state["study_pdf"],
        file_name="amre_study_sheet.pdf",
        mime="application/pdf",
    )
