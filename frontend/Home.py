"""
AMRE — login + personalized landing (IMPLEMENTATION.md §3.7, §10).
Holds only a session token in st.session_state; all logic is on the engine.
"""
import requests
import streamlit as st

from lib import api

st.set_page_config(page_title="AMRE Tutor", page_icon="🎓", layout="wide")
from lib import theme
theme.apply_theme()

st.session_state.setdefault("token", None)
st.session_state.setdefault("user_id", None)
st.session_state.setdefault("username", None)

theme.hero("AMRE", "Adaptive Math Reasoning Engine")


def _do_auth(fn, username, password, success_msg=None):
    try:
        data = fn(username, password)
        st.session_state.token = data["token"]
        st.session_state.user_id = data["user_id"]
        st.session_state.username = username
        if success_msg:
            st.success(success_msg)
        st.rerun()
    except requests.HTTPError as e:
        st.error(f"{e.response.status_code}: {e.response.text}")
    except Exception as e:  # noqa: BLE001
        st.error(f"Connection error (is the engine running at {api.engine_url()}?): {e}")


# ---------------- logged out ----------------
if not st.session_state.token:
    st.caption(f"Engine: {api.engine_url()}")
    tab_login, tab_register = st.tabs(["Login", "Register"])

    with tab_login:
        u = st.text_input("Username", key="login_user")
        p = st.text_input("Password", type="password", key="login_pass")
        if st.button("Login", type="primary"):
            _do_auth(api.login, u, p)

    with tab_register:
        u = st.text_input("Username", key="reg_user")
        p = st.text_input("Password", type="password", key="reg_pass")
        if st.button("Register"):
            _do_auth(api.register, u, p, success_msg="Registered! Welcome.")

    st.stop()

# ---------------- logged in: personalized landing ----------------
name = st.session_state.username or f"user {st.session_state.user_id}"
st.success(f"Welcome back, **{name}** 👋")

# ---- gamification banner: streak / XP / level ----
try:
    g = api.gamify()
    b1, b2, b3 = st.columns(3)
    b1.metric("🔥 Day streak", g.get("streak", 0))
    b2.metric("⭐ XP", g.get("xp", 0))
    b3.metric("🎯 Level", g.get("level", 0))
    into = g.get("xp_into_level", 0)
    st.progress(min(1.0, into / 100.0),
                text=f"{g.get('xp_to_next', 100)} XP to level {g.get('level', 0) + 1}")
except Exception:  # noqa: BLE001
    pass

# pull the user's profile to surface their weakest topic + offer one-click practice
weakest_label = None
try:
    prof = api.journal().get("profile", {})
    weakest = prof.get("weakest_topics") or []
    if weakest:
        weakest_label = weakest[0].replace("_", " ").title()
        st.info(
            f"📌 Your weakest topic right now is **{weakest_label}** "
            f"({prof.get('total_mistakes', 0)} mistakes logged). "
            "Jump into targeted practice below."
        )
    else:
        st.info("No mistakes logged yet — solve a problem or check your work to start your profile.")
except Exception:  # noqa: BLE001
    st.caption("(Could not load your profile — the engine may be waking up.)")

st.markdown("### What would you like to do?")
c1, c2, c3, c4 = st.columns(4)
with c1:
    if st.button("🔢 Solve", use_container_width=True):
        st.switch_page("pages/1_Solve.py")
with c2:
    if st.button("📝 Check my work", use_container_width=True):
        st.switch_page("pages/2_Check_my_work.py")
with c3:
    if st.button("🧠 Quiz", use_container_width=True):
        st.switch_page("pages/3_Quiz.py")
with c4:
    if st.button("📊 My Progress", use_container_width=True):
        st.switch_page("pages/4_My_Progress.py")

if weakest_label and st.button(f"⚡ Practice my weakest topic ({weakest_label})", type="primary"):
    st.session_state["practice_now"] = True
    st.switch_page("pages/3_Quiz.py")

st.divider()
if st.button("Logout"):
    for k in ("token", "user_id", "username"):
        st.session_state[k] = None
    st.rerun()
