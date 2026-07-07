"""
Quiz page (IMPLEMENTATION.md §9.3, §9.4, §9.8).

Verified quiz: pick a topic (or auto-target the weakest one) -> POST /quiz
(self-consistency-verified questions) -> answer -> POST /quiz/grade. Captures
self-confidence before grading for the metacognition track (POST /selfrate).
"""
import streamlit as st

from lib import api

st.set_page_config(page_title="Quiz", page_icon="🧠", layout="wide")
from lib import theme
theme.apply_theme()
st.title("🧠 Verified Quiz")

if not st.session_state.get("token"):
    st.warning("Please login first.")
    st.stop()

TOPICS = [
    "linear_equations", "quadratics", "fractions_ratios", "probability",
    "geometry", "calculus_derivatives", "calculus_integrals", "exponents_logs",
    "trigonometry", "combinatorics", "number_theory", "statistics",
]


def _load_quiz(topic_name=None, use_practice=False):
    try:
        with st.spinner("Generating & verifying questions (self-consistency QC)…"):
            data = api.practice() if use_practice else api.quiz(topic_name)
        qs = data.get("questions", [])
        if not qs:
            st.warning(data.get("message", "No verified questions came back — try another topic."))
            return
        st.session_state["quiz_qs"] = qs
        st.session_state["quiz_topic"] = data.get("topic", topic_name)
        st.session_state["quiz_results"] = {}
    except Exception as e:  # noqa: BLE001
        st.error(f"Could not load quiz: {e}")


# auto-launch weak-topic practice if arriving from the Home button
if st.session_state.pop("practice_now", False):
    _load_quiz(use_practice=True)

col1, col2 = st.columns([3, 1])
with col1:
    topic = st.selectbox("Topic", TOPICS, format_func=lambda t: t.replace("_", " ").title())
with col2:
    st.write("")
    st.write("")
    if st.button("Generate quiz", type="primary", use_container_width=True):
        _load_quiz(topic)

if st.button("⚡ Quiz me on my weakest topic"):
    _load_quiz(use_practice=True)

qs = st.session_state.get("quiz_qs")
if not qs:
    st.info("Pick a topic and generate a quiz to begin.")
    st.stop()

st.success(f"Quiz on **{(st.session_state.get('quiz_topic') or '').replace('_', ' ').title()}** "
           f"· {len(qs)} verified questions")

for i, q in enumerate(qs):
    st.markdown(f"#### Q{i + 1}. {q['text']}")
    conf = st.slider(f"How confident are you? (Q{i + 1})", 0, 100, 50, key=f"conf_{i}") / 100.0
    ans = st.text_area(f"Your solution (Q{i + 1})", key=f"ans_{i}", height=120,
                       placeholder="Step 1: ...\nFinal Answer: ...")
    if st.button(f"Submit Q{i + 1}", key=f"submit_{i}"):
        try:
            # metacognition: record self-confidence before the verdict
            api.selfrate(item_id=f"{st.session_state.get('quiz_topic')}#{i}", user_conf=conf)
            res = api.quiz_grade(q["text"], q["verified_answer"], ans)
            st.session_state["quiz_results"][i] = res
        except Exception as e:  # noqa: BLE001
            st.error(f"Grading failed: {e}")

    res = st.session_state.get("quiz_results", {}).get(i)
    if res is not None:
        if res.get("correct"):
            st.success("✅ Correct!")
        else:
            msg = "❌ Not quite."
            if res.get("error_step"):
                msg += f" First slip at step {res['error_step']}."
            st.error(msg)
            if res.get("explanation"):
                st.markdown(res["explanation"])
        st.caption(f"Verified answer: {q['verified_answer']}")
    st.divider()
