import streamlit as st
import asyncio
import websockets
import json

st.set_page_config(page_title="Solve", page_icon="🔢", layout="wide")

st.title("🔢 Solve a Math Problem (WebSocket Stream)")

if "token" not in st.session_state:
    st.warning("Please login first")
    st.stop()

ENGINE_URL = "http://localhost:7860"
# Replace http/https with ws/wss for the WebSocket endpoint
WS_URL = ENGINE_URL.replace("http://", "ws://").replace("https://", "wss://") + "/ws/solve"

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

def render_step_by_step(chains_data, container):
    """
    Renders all currently tracked reasoning chains and their PRM scores in a unified container.
    """
    with container:
        st.markdown("### 🧠 Live Candidate Reasoning Chains")
        for chain_id, data in sorted(chains_data.items()):
            status_symbol = "⏳ Running..."
            if data["done"]:
                status_symbol = f"✅ Done (Answer: {data['answer']})"
                
            with st.expander(f"Chain {chain_id + 1} — {status_symbol}", expanded=True):
                for idx, step in enumerate(data["steps"]):
                    score_info = ""
                    color = "orange" # default amber
                    
                    if idx < len(data["scores"]):
                        score, band = data["scores"][idx]
                        score_info = f" (PRM Score: {score:.2f})"
                        if band == "green":
                            color = "green"
                        elif band == "red":
                            color = "red"
                            
                    st.markdown(f":{color}[●] **Step {idx+1}**{score_info}")
                    if step.strip():
                        try:
                            st.latex(step)
                        except Exception:
                            st.code(step)

async def run_websocket_solver(problem_text, selected_mode, auth_token):
    status_placeholder = st.empty()
    chains_placeholder = st.empty()
    vote_placeholder = st.empty()
    final_placeholder = st.empty()
    
    chains_data = {} # chain_id -> {"steps": [], "scores": [], "done": False, "answer": None}
    
    status_placeholder.info("🔌 Connecting to solver engine...")
    
    try:
        async with websockets.connect(WS_URL) as ws:
            # Send request
            await ws.send(json.dumps({
                "problem": problem_text,
                "mode": selected_mode,
                "token": auth_token
            }))
            
            async for msg in ws:
                event = json.loads(msg)
                e_type = event.get("type")
                
                if e_type == "route":
                    strategy = event.get("strategy")
                    n = event.get("n")
                    status_placeholder.success(
                        f"🎯 Route determined: {strategy.upper()} (generating {n} candidate chains)"
                    )
                    
                elif e_type == "step":
                    chain_id = event.get("chain_id")
                    step_idx = event.get("step_idx")
                    latex = event.get("latex")
                    
                    if chain_id not in chains_data:
                        chains_data[chain_id] = {"steps": [], "scores": [], "done": False, "answer": None}
                        
                    while len(chains_data[chain_id]["steps"]) <= step_idx:
                        chains_data[chain_id]["steps"].append("")
                    chains_data[chain_id]["steps"][step_idx] = latex
                    
                    render_step_by_step(chains_data, chains_placeholder)
                    
                elif e_type == "score":
                    chain_id = event.get("chain_id")
                    step_idx = event.get("step_idx")
                    score = event.get("score")
                    band = event.get("band")
                    
                    if chain_id not in chains_data:
                        chains_data[chain_id] = {"steps": [], "scores": [], "done": False, "answer": None}
                        
                    while len(chains_data[chain_id]["scores"]) <= step_idx:
                        chains_data[chain_id]["scores"].append((0.5, "amber"))
                    chains_data[chain_id]["scores"][step_idx] = (score, band)
                    
                    render_step_by_step(chains_data, chains_placeholder)
                    
                elif e_type == "chain_done":
                    chain_id = event.get("chain_id")
                    answer = event.get("answer")
                    
                    if chain_id not in chains_data:
                        chains_data[chain_id] = {"steps": [], "scores": [], "done": False, "answer": None}
                        
                    chains_data[chain_id]["done"] = True
                    chains_data[chain_id]["answer"] = answer
                    
                    render_step_by_step(chains_data, chains_placeholder)
                    
                elif e_type == "vote":
                    tally = event.get("tally", {})
                    agreement = event.get("agreement", 0.0)
                    
                    with vote_placeholder:
                        st.markdown("### 📊 Vote Convergence & Distribution")
                        st.write(f"Consensus Agreement: **{agreement * 100:.1f}%**")
                        # Format for cleaner bar display
                        st.bar_chart(tally)
                        
                elif e_type == "final":
                    answer = event.get("answer")
                    confidence = event.get("confidence")
                    weakest = event.get("weakest", {})
                    
                    status_placeholder.success("✅ Problem solving complete!")
                    
                    with final_placeholder:
                        st.markdown("---")
                        st.markdown("### 🏁 Final Solver Verdict")
                        
                        col1, col2, col3 = st.columns(3)
                        col1.metric("Selected Answer", answer)
                        col2.metric("Calibrated Confidence", f"{confidence*100:.1f}%")
                        col3.metric("Weakest Link", f"Chain {weakest.get('chain', 0)+1}, Step {weakest.get('step', 0)+1}")
                        
                        st.balloons()
                    break
                    
                elif e_type == "error":
                    status_placeholder.error(f"❌ Error: {event.get('message')}")
                    break
                    
    except Exception as e:
        status_placeholder.error(f"❌ Connection or protocol error: {e}")

if st.button("🚀 Solve", type="primary"):
    if not problem:
        st.error("Please enter a problem")
    else:
        # Run the async WebSocket handler inside the Streamlit context
        asyncio.run(run_websocket_solver(problem, mode_map[mode], st.session_state.token))
