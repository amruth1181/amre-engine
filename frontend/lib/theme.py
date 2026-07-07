"""
Dark LaTeX Academia theme (shared across all pages).

Deep-navy background with a faint graph-paper grid, warm gold accents, and
elegant serif (EB Garamond / Spectral) typography for a scholarly, "math
enthusiast" feel. Call `apply_theme()` right after st.set_page_config on every
page; use `hero()` for the landing title.
"""
import streamlit as st

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,600;0,700;1,400&family=Spectral:wght@300;400;500;600&family=JetBrains+Mono&display=swap');

:root{
  --navy:#0E1428; --navy2:#17223B; --navy3:#0c1220;
  --gold:#E8B04B; --gold-soft:#F0C979; --ink:#E7EAF3; --muted:#9AA6C0;
}

/* faint graph-paper backdrop */
[data-testid="stAppViewContainer"]{
  background-color:var(--navy);
  background-image:
    linear-gradient(rgba(232,176,75,.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(232,176,75,.035) 1px, transparent 1px);
  background-size:30px 30px;
}
[data-testid="stHeader"]{background:transparent;}
[data-testid="stSidebar"]{
  background:linear-gradient(180deg,#101a30,#0b1120);
  border-right:1px solid rgba(232,176,75,.16);
}
[data-testid="stSidebar"] *{font-family:'EB Garamond',serif;}

/* typography */
html,body,p,li,label,span,div,.stMarkdown,.stTextInput,.stTextArea,.stSelectbox{
  font-family:'Spectral',Georgia,serif;
}
h1,h2,h3,h4{
  font-family:'EB Garamond','Times New Roman',serif !important;
  color:var(--gold) !important; letter-spacing:.3px; font-weight:700;
}
h1{font-size:2.5rem;} h2{font-size:1.9rem;} h3{font-size:1.45rem;}
a{color:var(--gold) !important; text-decoration:none;}
a:hover{color:var(--gold-soft) !important;}

/* buttons: gold-outline, glow on hover */
.stButton>button,.stDownloadButton>button{
  font-family:'EB Garamond',serif; font-size:1.02rem;
  background:rgba(232,176,75,.06); color:var(--gold);
  border:1px solid rgba(232,176,75,.45); border-radius:10px;
  transition:all .16s ease;
}
.stButton>button:hover,.stDownloadButton>button:hover{
  background:rgba(232,176,75,.14); border-color:var(--gold);
  color:var(--gold-soft); box-shadow:0 0 20px rgba(232,176,75,.16);
}
.stButton>button[kind="primary"]{
  background:linear-gradient(180deg,#ecb85a,#d29a34); color:#1a1206;
  border:none; font-weight:600;
}
.stButton>button[kind="primary"]:hover{box-shadow:0 0 24px rgba(232,176,75,.35); color:#1a1206;}

/* metrics as gold-edged cards */
[data-testid="stMetric"]{
  background:rgba(23,34,59,.55); border:1px solid rgba(232,176,75,.20);
  border-radius:12px; padding:12px 16px;
}
[data-testid="stMetricValue"]{color:var(--gold) !important; font-family:'EB Garamond',serif;}
[data-testid="stMetricLabel"]{color:var(--muted) !important;}

/* inputs */
.stTextInput input,.stTextArea textarea,.stSelectbox div[data-baseweb="select"]>div{
  background:rgba(12,18,32,.85) !important; color:var(--ink) !important;
  border:1px solid rgba(232,176,75,.22) !important; border-radius:8px !important;
}
.stTextInput input:focus,.stTextArea textarea:focus{border-color:var(--gold) !important;}

/* expanders, tabs, dataframes, code */
[data-testid="stExpander"]{
  border:1px solid rgba(232,176,75,.16); border-radius:12px;
  background:rgba(23,34,59,.35);
}
.stTabs [data-baseweb="tab-list"]{gap:4px;}
.stTabs [data-baseweb="tab"]{font-family:'EB Garamond',serif; font-size:1.05rem;}
.stTabs [aria-selected="true"]{color:var(--gold) !important;}
code,pre,.stCode{font-family:'JetBrains Mono',monospace !important;}
[data-testid="stProgress"] div[role="progressbar"]>div{background:var(--gold) !important;}

/* hero landing block */
.amre-hero{text-align:center; padding:26px 0 10px 0; position:relative;}
.amre-hero .sigma{
  font-family:'EB Garamond',serif; font-size:110px; line-height:1;
  color:rgba(232,176,75,.14); position:absolute; left:50%; top:-14px;
  transform:translateX(-50%); pointer-events:none;
}
.amre-hero .title{
  font-family:'EB Garamond',serif; font-weight:700; font-size:3rem;
  color:var(--gold); margin:0; position:relative;
}
.amre-hero .sub{
  font-family:'Spectral',serif; font-style:italic; color:var(--muted);
  font-size:1.2rem; margin-top:4px;
}
.amre-hero .rule{
  width:120px; height:2px; margin:14px auto 0 auto;
  background:linear-gradient(90deg,transparent,var(--gold),transparent);
}
</style>
"""


def apply_theme() -> None:
    """Inject the Dark LaTeX Academia CSS. Call once per page, after set_page_config."""
    st.markdown(_CSS, unsafe_allow_html=True)


def hero(title: str = "AMRE", subtitle: str = "Adaptive Math Reasoning Engine") -> None:
    """A centered serif hero title with a faint Σ watermark and a gold rule."""
    st.markdown(
        f'<div class="amre-hero"><div class="sigma">&Sigma;</div>'
        f'<div class="title">{title}</div><div class="sub">{subtitle}</div>'
        f'<div class="rule"></div></div>',
        unsafe_allow_html=True,
    )
