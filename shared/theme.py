"""
shared/theme.py
══════════════════════════════════════════════════════════════════════
BizTrack Suite — Shared CSS + UI Component Library
══════════════════════════════════════════════════════════════════════

Exports:
  apply_suite_css()       → inject full CSS into any page
  kpi_card(...)           → gold-accented KPI metric card
  section_header(title)   → gold-bar section divider
  page_header(title, sub) → full-width page heading with date
  stock_pill(qty, reorder)→ colour-coded stock badge HTML

All page modules call apply_suite_css() at the top of their render
function so the style is always available, even when a user lands
directly on a sub-page via Streamlit navigation.
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from shared.db import safe_int, safe_float


# ══════════════════════════════════════════════════════════════════════════════
# SUITE CSS
# ══════════════════════════════════════════════════════════════════════════════

def apply_suite_css():
    """
    Inject the unified BizTrack dark-theme CSS.
    Idempotent — safe to call multiple times per session.
    """
    st.html("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;500;600;700;800&family=DM+Sans:ital,wght@0,300;0,400;0,500;0,600;0,700;1,400&family=DM+Mono:wght@400;500&display=swap');

/* ── CSS Variables ── */
:root {
  --obsidian:    #080B0F;
  --deep:        #0D1117;
  --surface:     #111827;
  --surface2:    #1A2332;
  --border:      #1F2D3D;
  --border2:     #2D3F55;
  --gold:        #F5A623;
  --gold-dim:    #C4831A;
  --gold-glow:   rgba(245,166,35,0.15);
  --jade:        #00C896;
  --jade-dim:    rgba(0,200,150,0.12);
  --ruby:        #FF4D6D;
  --ruby-dim:    rgba(255,77,109,0.12);
  --text-primary:   #F0F4F8;
  --text-secondary: #8BA0B8;
  --text-muted:     #4A6080;
  --font-display: 'Syne', sans-serif;
  --font-body:    'DM Sans', sans-serif;
  --font-mono:    'DM Mono', monospace;
}

/* ── Base ── */
html, body, [class*="css"], .stApp {
  font-family: var(--font-body);
  background-color: var(--obsidian) !important;
  color: var(--text-primary) !important;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
  background-color: var(--deep) !important;
  border-right: 1px solid var(--border) !important;
}
[data-testid="stSidebarContent"] { padding: 0.5rem 0.75rem; }

/* ── Main content ── */
[data-testid="stAppViewContainer"] > .main { background: var(--obsidian); }
[data-testid="block-container"] { padding-top: 1.5rem !important; }

/* ── KPI Cards ── */
.kpi-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 1.125rem 1.25rem;
  margin-bottom: 0.75rem;
  transition: border-color 0.2s;
}
.kpi-card:hover { border-color: var(--border2); }
.kpi-header { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.4rem; }
.kpi-icon   { font-size: 1.1rem; }
.kpi-label  {
  font-size: 0.7rem; font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase; letter-spacing: 0.1em;
  font-family: var(--font-mono);
}
.kpi-value  {
  font-family: var(--font-display);
  font-size: 1.55rem; font-weight: 800;
  color: var(--text-primary); letter-spacing: -0.04em;
  line-height: 1.1;
}
.kpi-sub    { font-size: 0.78rem; color: var(--text-secondary); margin-top: 0.25rem; }
.kpi-positive { color: var(--jade) !important; }
.kpi-negative { color: var(--ruby) !important; }

/* ── Alert Styles ── */
.alert-critical {
  background: rgba(255,77,109,0.1);
  border: 1px solid rgba(255,77,109,0.3);
  border-radius: 10px; padding: 0.625rem 0.875rem;
  color: #FF4D6D; margin-bottom: 0.5rem; font-size: 0.875rem;
}
.alert-low {
  background: rgba(245,166,35,0.1);
  border: 1px solid rgba(245,166,35,0.3);
  border-radius: 10px; padding: 0.625rem 0.875rem;
  color: #F5A623; margin-bottom: 0.5rem; font-size: 0.875rem;
}
.alert-success {
  background: rgba(0,200,150,0.1);
  border: 1px solid rgba(0,200,150,0.3);
  border-radius: 10px; padding: 0.625rem 0.875rem;
  color: #00C896; margin-bottom: 0.5rem; font-size: 0.875rem;
}

/* ── Stock pills ── */
.stock-ok       { background:#0a2a1e; color:#00C896; border:1px solid #00C896; padding:2px 10px; border-radius:20px; font-size:0.75rem; font-weight:600; }
.stock-low      { background:#2a1e07; color:#F5A623; border:1px solid #F5A623; padding:2px 10px; border-radius:20px; font-size:0.75rem; font-weight:600; }
.stock-critical { background:#2a0a11; color:#FF4D6D; border:1px solid #FF4D6D; padding:2px 10px; border-radius:20px; font-size:0.75rem; font-weight:600; }

/* ── Pricing grid ── */
.pricing-grid { display:flex; gap:1rem; flex-wrap:wrap; justify-content:center; margin:1.5rem 0; }
.pricing-card {
  flex:1; min-width:220px; max-width:280px;
  background:var(--surface); border:1px solid var(--border);
  border-radius:18px; padding:1.5rem 1.25rem;
  position:relative; transition:border-color 0.2s;
}
.pricing-card:hover  { border-color:var(--border2); }
.pricing-card.featured { border-color:var(--gold); }
.pricing-badge {
  position:absolute; top:-12px; left:50%; transform:translateX(-50%);
  background:var(--gold); color:var(--obsidian);
  font-size:0.7rem; font-weight:700; padding:2px 12px;
  border-radius:20px; white-space:nowrap;
}
.pricing-plan-name { font-family:var(--font-display); font-size:1rem; font-weight:700; color:var(--text-primary); margin-bottom:0.5rem; }
.pricing-price { font-family:var(--font-display); font-size:2rem; font-weight:800; color:var(--gold); margin-bottom:0.25rem; }
.pricing-price span { font-size:1rem; font-weight:400; color:var(--text-secondary); }
.pricing-desc { font-size:0.78rem; color:var(--text-muted); margin-bottom:1rem; }
.pricing-features { list-style:none; padding:0; margin:0; }
.pricing-features li { font-size:0.83rem; color:var(--text-secondary); padding:0.25rem 0; }
.pricing-features li::before { content:"✓ "; color:var(--jade); font-weight:700; }

/* ── Landing page hero (login/signup) ── */
.lp-hero {
  text-align:center; padding:3rem 1.5rem 2rem;
  max-width:860px; margin:0 auto;
}
.lp-logo-wrap { display:inline-flex; align-items:center; gap:0.7rem; margin-bottom:1.25rem; }
.lp-logo-icon {
  width:52px; height:52px; border-radius:14px;
  background:linear-gradient(135deg,#F5A623,#C4831A);
  display:flex; align-items:center; justify-content:center;
  font-size:1.5rem;
  box-shadow:0 6px 24px rgba(245,166,35,0.4);
}
.lp-logo-text { font-family:var(--font-display); font-size:2.2rem; font-weight:800; color:var(--text-primary); letter-spacing:-0.05em; }
.lp-badge {
  display:inline-flex; align-items:center; gap:0.5rem;
  background:var(--surface); border:1px solid var(--border);
  border-radius:99px; padding:0.35rem 1rem;
  font-size:0.75rem; color:var(--text-secondary);
  margin-bottom:1.5rem;
}
.lp-badge span { color:var(--jade); font-size:0.5rem; }
.lp-headline {
  font-family:var(--font-display);
  font-size:clamp(2rem,5vw,3rem); font-weight:800;
  color:var(--text-primary); letter-spacing:-0.05em;
  line-height:1.1; margin-bottom:1rem;
}
.lp-headline span { color:var(--gold); }
.lp-sub { font-size:1rem; color:var(--text-secondary); max-width:540px; margin:0 auto 2rem; line-height:1.65; }

.lp-value-grid { display:flex; gap:1rem; flex-wrap:wrap; justify-content:center; margin-bottom:2rem; }
.lp-value-card {
  background:var(--surface); border:1px solid var(--border);
  border-radius:14px; padding:1.25rem; text-align:left;
  flex:1; min-width:190px; max-width:220px;
}
.lp-value-icon  { font-size:1.5rem; margin-bottom:0.5rem; }
.lp-value-title { font-weight:700; color:var(--text-primary); font-size:0.9rem; margin-bottom:0.3rem; }
.lp-value-desc  { font-size:0.78rem; color:var(--text-secondary); line-height:1.5; }

.lp-divider {
  display:flex; align-items:center; gap:1rem;
  color:var(--text-muted); font-size:0.8rem;
  margin:1.5rem auto 1.25rem; max-width:400px;
}
.lp-divider::before,.lp-divider::after {
  content:""; flex:1;
  border-top:1px solid var(--border);
}

.lp-trust-strip {
  display:flex; flex-wrap:wrap; justify-content:center;
  gap:1rem; padding:1.25rem 0 2rem;
  border-top:1px solid var(--border); margin-top:1.5rem;
}
.lp-trust-item { font-size:0.78rem; color:var(--text-muted); }
.lp-trust-item span { color:var(--jade); margin-right:0.3rem; }

/* ── Buttons ── */
.stButton button[kind="primary"]  { background:var(--gold) !important; color:#080B0F !important; font-weight:700 !important; border:none !important; }
.stButton button[kind="primary"]:hover { background:var(--gold-dim) !important; }

/* ── Tabs ── */
[data-testid="stTabs"] button[role="tab"]               { color:var(--text-muted) !important; font-size:0.875rem; }
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] { color:var(--gold) !important; border-bottom-color:var(--gold) !important; }

/* ── Forms + inputs ── */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stSelectbox"] > div { background:var(--surface) !important; color:var(--text-primary) !important; border-color:var(--border) !important; }

/* ── Dataframes ── */
[data-testid="stDataFrame"] { background:var(--surface); border:1px solid var(--border); border-radius:10px; overflow:hidden; }

/* ── Expanders ── */
[data-testid="stExpander"] { background:var(--surface); border:1px solid var(--border); border-radius:10px; }
[data-testid="stExpander"]:hover { border-color:var(--border2); }
</style>
""")


# ══════════════════════════════════════════════════════════════════════════════
# UI COMPONENT HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def kpi_card(label: str, value, sub: str = "",
             positive: bool | None = None, icon: str = ""):
    """Gold-accented KPI metric card."""
    sub_class = ""
    if positive is True:
        sub_class = "kpi-positive"
    elif positive is False:
        sub_class = "kpi-negative"
    icon_html = f'<div class="kpi-icon">{icon}</div>' if icon else ""
    st.markdown(f"""
<div class="kpi-card">
  <div class="kpi-header">
    {icon_html}
    <div class="kpi-label">{label}</div>
  </div>
  <div class="kpi-value">{value}</div>
  {f'<div class="kpi-sub {sub_class}">{sub}</div>' if sub else ""}
</div>
    """, unsafe_allow_html=True)


def section_header(title: str):
    """Gold vertical-bar section divider."""
    st.markdown(f"""
<div style="
  font-family:'Syne',sans-serif;
  font-size:0.95rem; font-weight:700;
  color:#F0F4F8; letter-spacing:-0.01em;
  margin:1.75rem 0 0.875rem 0;
  padding-bottom:0.5rem;
  border-bottom:1px solid #1F2D3D;
  display:flex; align-items:center; gap:0.5rem;
">
  <span style="
    display:inline-block; width:3px; height:16px;
    background:#F5A623; border-radius:2px; flex-shrink:0;
  "></span>
  {title}
</div>
    """, unsafe_allow_html=True)


def page_header(title: str, subtitle: str = ""):
    """Full-width page heading with current date."""
    now_str = datetime.now().strftime("%A, %d %B %Y")
    st.markdown(f"""
<div style="
  display:flex; justify-content:space-between; align-items:flex-start;
  margin-bottom:1.5rem; padding-bottom:1rem;
  border-bottom:1px solid #1F2D3D;
">
  <div>
    <div style="
      font-family:'Syne',sans-serif;
      font-size:1.6rem; font-weight:800;
      color:#F0F4F8; letter-spacing:-0.04em;
      line-height:1.1; margin-bottom:0.25rem;
    ">{title}</div>
    {f'<div style="font-size:0.85rem;color:#4A6080;">{subtitle}</div>' if subtitle else ""}
  </div>
  <div style="
    font-size:0.75rem; color:#4A6080; text-align:right;
    font-family:'DM Mono',monospace; margin-top:0.35rem;
  ">{now_str}</div>
</div>
    """, unsafe_allow_html=True)


def stock_pill(qty, reorder) -> str:
    """Return colour-coded stock badge HTML string."""
    qty     = safe_int(qty)
    reorder = safe_int(reorder)
    if qty <= 0:
        return '<span class="stock-critical">Out of Stock</span>'
    elif qty <= reorder:
        return f'<span class="stock-low">Low — {qty} left</span>'
    else:
        return f'<span class="stock-ok">{qty} in stock</span>'
