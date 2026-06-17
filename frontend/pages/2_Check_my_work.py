import streamlit as st

st.set_page_config(page_title="Check My Work", page_icon="📝", layout="wide")

st.title("📝 Check My Work")

if "token" not in st.session_state:
    st.warning("Please login first")
    st.stop()

st.markdown("### Paste your solution for review")

problem = st.text_area("Problem:", height=80, placeholder="What problem were you solving?")
solution = st.text_area("Your Solution:", height=200, placeholder="Show your step-by-step work here...")

if st.button("🔍 Check Work", type="primary"):
    if not problem or not solution:
        st.error("Please enter both the problem and your solution")
    else:
        with st.spinner("Analyzing your work..."):
            st.info("🔧 This feature is being built. Check back soon!")
