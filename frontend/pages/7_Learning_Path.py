"""
Topic Knowledge Graph / Learning Path (feature 1.5).
Shows the prerequisite map of math topics, highlights the student's weak topics,
and recommends which foundations to fix first (preventing blind drilling).
"""
import streamlit as st

from lib import api

st.set_page_config(page_title="Learning Path", page_icon="⊢", layout="wide")
from lib import theme
theme.apply_theme()
st.title("⊢  Your Learning Path")

if not st.session_state.get("token"):
    st.warning("Please login first.")
    st.stop()

st.caption("Math topics build on each other. If you keep missing a topic, the real fix is often "
           "a shaky prerequisite — so we point you to the foundations to shore up first.")

try:
    kg = api.knowledge_graph()
except Exception as e:  # noqa: BLE001
    st.error(f"Could not load your learning path: {e}")
    st.stop()

graph = kg.get("graph", {})
weak = set(kg.get("weak_topics", []))
rec = kg.get("recommended_foundations", [])
rec_set = set(rec)

# ---- recommendation banner ----
if rec:
    pretty = ", ".join(t.replace("_", " ").title() for t in rec)
    st.warning(f"🎯 **Fix these foundations first:** {pretty}")
elif weak:
    st.info("Your weak topics have no shakier prerequisites — keep drilling them directly.")
else:
    st.success("No mistakes logged yet — the graph below is your full roadmap.")

# ---- legend ----
st.markdown(":red[●] weak topic &nbsp;&nbsp; :orange[●] recommended foundation "
            "&nbsp;&nbsp; :grey[●] on track")

# ---- build the DAG (Graphviz DOT, rendered in-browser by Streamlit) ----
nodes = set(graph.keys())
for prereqs in graph.values():
    nodes.update(prereqs)

def color(n):
    if n in weak:
        return "lightcoral"
    if n in rec_set:
        return "gold"
    return "gainsboro"

lines = ["digraph G {", "rankdir=BT;", "bgcolor=transparent;",
         'node [style="filled,rounded", shape=box, fontname="Helvetica", fontsize=11];']
for n in sorted(nodes):
    label = n.replace("_", " ").title()
    lines.append(f'"{n}" [label="{label}", fillcolor="{color(n)}"];')
for topic, prereqs in graph.items():
    for p in prereqs:
        lines.append(f'"{p}" -> "{topic}";')
lines.append("}")

st.graphviz_chart("\n".join(lines), use_container_width=True)
st.caption("Arrows point from a prerequisite up to the topic that depends on it.")
