import streamlit as st
import requests

st.set_page_config(page_title="Solve", page_icon="🔢", layout="wide")

st.title("🔢 Solve a Math Problem")

if "token" not in st.session_state:
    st.warning("Please login first")
    st.stop()

ENGINE_URL = "http://localhost:7860"

st.markdown("### Enter your math problem")

problem = st.text_area("Problem:", height=100, placeholder="Example: Solve for x: 2x + 5 = 15")

mode = st.radio(
    "Mode:",
    ["Fast (Greedy)", "Balanced (Self-Consistency)", "Careful (PRM Weighted)"],
    horizontal=True
)

mode_map = {
    "Fast (Greedy)": "fast",
    "Balanced (Self-Consistency)": "balanced",
    "Careful (PRM Weighted)": "careful"
}

if st.button("🚀 Solve", type="primary"):
    if not problem:
        st.error("Please enter a problem")
    else:
        with st.spinner("Solving..."):
            try:
                response = requests.post(
                    f"{ENGINE_URL}/solve/",
                    json={"problem": problem, "mode": mode_map[mode]},
                    headers={"Authorization": f"Bearer {st.session_state.token}"}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Answer", data["answer"])
                    col2.metric("Confidence", f"{data['confidence']*100:.1f}%")
                    col3.metric("Samples Used", data["n_used"])
                    
                    st.markdown("---")
                    st.markdown("### 🧠 Reasoning Chains")
                    
                    for i, chain in enumerate(data["chains"]):
                        with st.expander(f"Chain {i+1}"):
                            st.write(chain["text"])
                            st.caption(f"Score: {chain['score']:.2f}")
                else:
                    st.error(f"Error: {response.text}")
            except Exception as e:
                st.error(f"Connection error: {e}")
