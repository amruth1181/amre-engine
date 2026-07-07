"""
Teacher / Class Dashboard (feature 1.3).
Teachers create classes, share a join code, and see aggregate weak topics + a
per-student breakdown, and assign topic quizzes. Students join with a code and
see their assignments. Makes AMRE sellable to schools (B2B).
"""
import pandas as pd
import streamlit as st

from lib import api

st.set_page_config(page_title="Teacher", page_icon="∈", layout="wide")
from lib import theme
theme.apply_theme()
st.title("∈  Teacher / Class Dashboard")

if not st.session_state.get("token"):
    st.warning("Please login first.")
    st.stop()

try:
    data = api.class_list()
except Exception as e:  # noqa: BLE001
    st.error(f"Could not load classes: {e}")
    st.stop()

teaching = data.get("teaching", [])
enrolled = data.get("enrolled", [])

tab_teacher, tab_student = st.tabs(["👩‍🏫 Teach", "🎒 Enrolled"])

# ---------------- teacher side ----------------
with tab_teacher:
    with st.form("create_class"):
        st.markdown("**Create a class**")
        name = st.text_input("Class name", placeholder="e.g. Grade 9 Algebra — Period 2")
        if st.form_submit_button("Create class", type="primary") and name.strip():
            res = api.class_create(name.strip())
            st.success(f"Created **{res['name']}** — share join code: `{res['join_code']}`")
            st.rerun()

    if not teaching:
        st.info("You aren't teaching any classes yet. Create one above to get a join code.")
    for cls in teaching:
        with st.expander(f"📘 {cls['name']}  ·  join code: `{cls['join_code']}`", expanded=True):
            try:
                dash = api.class_dashboard(cls["class_id"])
            except Exception as e:  # noqa: BLE001
                st.error(f"Could not load dashboard: {e}")
                continue
            if dash.get("error"):
                st.error(dash["error"])
                continue

            st.metric("Students", dash.get("student_count", 0))

            weak = dash.get("class_weak_topics", {})
            if weak:
                st.markdown("**Class weak topics** (aggregate mistakes)")
                st.bar_chart(pd.Series(weak, name="mistakes"))
            else:
                st.caption("No student mistakes logged yet.")

            students = dash.get("students", [])
            if students:
                st.markdown("**Per-student breakdown**")
                st.dataframe(pd.DataFrame(students), use_container_width=True, hide_index=True)

            # assign a topic quiz
            st.markdown("**Assign a topic quiz**")
            cola, colb = st.columns([3, 1])
            topic = cola.text_input("Topic", key=f"assign_topic_{cls['class_id']}",
                                    placeholder="e.g. quadratics")
            if colb.button("Assign", key=f"assign_btn_{cls['class_id']}") and topic.strip():
                api.class_assign(cls["class_id"], topic.strip().lower().replace(" ", "_"))
                st.success("Assigned.")
                st.rerun()
            assignments = dash.get("assignments", [])
            if assignments:
                st.caption("Assigned: " + ", ".join(a["title"] for a in assignments))

# ---------------- student side ----------------
with tab_student:
    with st.form("join_class"):
        st.markdown("**Join a class**")
        code = st.text_input("Join code", placeholder="6-character code from your teacher")
        if st.form_submit_button("Join", type="primary") and code.strip():
            res = api.class_join(code.strip())
            if res.get("error"):
                st.error(res["error"])
            else:
                st.success(f"Joined **{res['name']}**!")
                st.rerun()

    if not enrolled:
        st.info("You haven't joined any classes yet. Enter a join code above.")
    for cls in enrolled:
        st.markdown(f"#### 🎒 {cls['name']}")
        assignments = cls.get("assignments", [])
        if assignments:
            for a in assignments:
                st.markdown(f"- 📝 **{a['title']}** — [take the quiz](Quiz) on `{a['topic']}`")
        else:
            st.caption("No assignments yet.")
