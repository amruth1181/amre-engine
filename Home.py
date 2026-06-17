import streamlit as st
import requests

st.set_page_config(page_title="AMRE Tutor", page_icon="🎓", layout="wide")

ENGINE_URL = "http://localhost:7860"

if "token" not in st.session_state:
    st.session_state.token = None
    st.session_state.user_id = None

st.title("🎓 AMRE — Adaptive Math Reasoning Engine")

if not st.session_state.token:
    st.markdown("### Login or Register")
    
    tab1, tab2 = st.tabs(["Login", "Register"])
    
    with tab1:
        username = st.text_input("Username", key="login_user")
        password = st.text_input("Password", type="password", key="login_pass")
        if st.button("Login"):
            try:
                resp = requests.post(
                    f"{ENGINE_URL}/auth/login",
                    json={"username": username, "password": password}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    st.session_state.token = data["token"]
                    st.session_state.user_id = data["user_id"]
                    st.rerun()
                else:
                    st.error(f"Error: {resp.text}")
            except Exception as e:
                st.error(f"Connection error: {e}")
    
    with tab2:
        username = st.text_input("Username", key="reg_user")
        password = st.text_input("Password", type="password", key="reg_pass")
        if st.button("Register"):
            try:
                resp = requests.post(
                    f"{ENGINE_URL}/auth/register",
                    json={"username": username, "password": password}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    st.session_state.token = data["token"]
                    st.session_state.user_id = data["user_id"]
                    st.success("Registered! Welcome!")
                    st.rerun()
                else:
                    st.error(f"Error: {resp.text}")
            except Exception as e:
                st.error(f"Connection error: {e}")
else:
    st.success(f"✅ Welcome! (User ID: {st.session_state.user_id})")
    
    st.markdown("### 📚 Choose an Option")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🔢 Solve", use_container_width=True):
            st.switch_page("pages/1_Solve.py")
    
    with col2:
        if st.button("📝 Check My Work", use_container_width=True):
            st.switch_page("pages/2_Check_my_work.py")
    
    with col3:
        if st.button("📊 My Progress", use_container_width=True):
            st.switch_page("pages/3_My_Progress.py")
    
    if st.button("Logout"):
        st.session_state.token = None
        st.session_state.user_id = None
        st.rerun()
