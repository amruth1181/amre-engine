import streamlit as st
import requests

st.set_page_config(page_title="My Progress", page_icon="📊", layout="wide")

st.title("📊 My Progress")

if "token" not in st.session_state:
    st.warning("Please login first")
    st.stop()

ENGINE_URL = "http://localhost:7860"

st.markdown("### Your Learning Dashboard")

try:
    response = requests.get(
        f"{ENGINE_URL}/history",
        headers={"Authorization": f"Bearer {st.session_state.token}"}
    )
    
    if response.status_code == 200:
        data = response.json()
        if data.get("history"):
            st.dataframe(data["history"])
        else:
            st.info("No history yet. Start solving problems!")
    else:
        st.info("History coming soon!")
except:
    st.info("History coming soon!")

st.markdown("---")
st.markdown("### 📈 Statistics (Coming Soon)")
st.markdown("- Problems solved: 0")
st.markdown("- Accuracy: 0%")
st.markdown("- Weakest topic: N/A")
