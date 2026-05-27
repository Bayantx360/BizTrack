"""
suite_home.py
══════════════════════════════════════════════════════════════════════
BizTrack Suite — Main Entry Point
══════════════════════════════════════════════════════════════════════

Responsibilities:
  1. Initialise session state
  2. Render auth pages (login, signup, forgot password)
  3. Render the sidebar navigation (app switcher + page links)
  4. Route to the correct page module based on session state
  5. Gate every authenticated page behind check_access()

"""

from datetime import datetime

import streamlit as st

st.set_page_config(
    page_title="BizTrack-OS",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Shared imports ─────────────────────────────────────────────────────────────
from shared.auth import (
    init_session_state, login_user, signup_user,
    sign_out, check_access,
    get_user_by_email, is_subscription_active,
    hash_password,
    SUITE_SESSION_KEYS,
)
from shared.db import (
    db_update, TBL_USERS,
    PAYMENT_DETAILS, validate_email,
    gen_id,
)
from shared.theme import apply_suite_css

# ── Page module imports ────────────────────────────────────────────────────────
from apps.sales     import page_dashboard, page_record_sale, page_sales_history
from apps.inventory import page_products
from apps.health    import page_expenses, page_insights, page_admin


# ══════════════════════════════════════════════════════════════════════════════
# ROUTING TABLE
# key → (display label, emoji, app_module, render_function)
# ══════════════════════════════════════════════════════════════════════════════
PAGES = {
    # Sales Management
    "dashboard":     ("Dashboard",     "🏠", "sales",     page_dashboard),
    "record_sale":   ("Record Sale",   "🛒", "sales",     page_record_sale),
    "sales_history": ("Sales History", "📋", "sales",     page_sales_history),
    # Inventory Management
    "inventory":     ("Inventory",     "📦", "inventory", page_products),
    # Business Health
    "expenses":      ("Expenses",      "💸", "health",    page_expenses),
    "insights":      ("Insights",      "🧠", "health",    page_insights),
    # Admin (conditionally shown)
    "admin":         ("Admin Panel",   "🛡️", "health",    page_admin),
}

APP_META = {
    "sales":     {"label": "Sales Management",     "icon": "💰", "color": "#6366f1"},
    "inventory": {"label": "Inventory Management", "icon": "📦", "color": "#f59e0b"},
    "health":    {"label": "Business Health",      "icon": "🧠", "color": "#10b981"},
}

# Pages grouped by app — controls sidebar rendering order
APP_PAGES = {
    "sales":     ["dashboard", "record_sale", "sales_history"],
    "inventory": ["inventory"],
    "health":    ["expenses", "insights"],
}


# ══════════════════════════════════════════════════════════════════════════════
# AUTH PAGES
# ══════════════════════════════════════════════════════════════════════════════

def page_login():
    apply_suite_css()
    st.markdown("""
<div class="lp-hero">
  <div class="lp-logo-wrap">
    <div class="lp-logo-icon">📊</div>
  </div>
  <div class="lp-logo-text">BizTrack-OS</div><br>
  <div class="lp-badge"><span>●</span> All-in-one business suite</div>
  <div class="lp-headline">Run your business<br><span>smarter, and more efficiently</span></div>
  <div class="lp-sub">
    Sales · Inventory · Business Health — three powerful tool,
    one unified platform built for Entrepreneurs & Businesses
  </div>
  <div class="lp-value-grid">
    <div class="lp-value-card">
      <div class="lp-value-icon">💰</div>
      <div class="lp-value-title">Sales Management</div>
      <div class="lp-value-desc">Record sales with multi-item carts,
        instant PDF receipts and WhatsApp sharing.</div>
    </div>
    <div class="lp-value-card">
      <div class="lp-value-icon">📦</div>
      <div class="lp-value-title">Inventory Control</div>
      <div class="lp-value-desc">Live stock levels, reorder alerts and
        automatic stockout projections.</div>
    </div>
    <div class="lp-value-card">
      <div class="lp-value-icon">🧠</div>
      <div class="lp-value-title">Business Health</div>
      <div class="lp-value-desc">Profit/loss, expenses, trend charts and
        AI-powered insights — all in one view.</div>
    </div>
  </div>
</div>
    """, unsafe_allow_html=True)

    _, form_col, _ = st.columns([1, 1.4, 1])
    with form_col:
        st.markdown('<div class="lp-divider">Sign in to your account</div>',
                    unsafe_allow_html=True)
        with st.form("login_form"):
            email    = st.text_input("Email address", placeholder="you@example.com")
            password = st.text_input("Password", type="password", placeholder="••••••••")
            submit   = st.form_submit_button("Sign In →", type="primary",
                                             width='stretch')
        if submit:
            if not email or not password:
                st.error("Please enter both email and password.")
            else:
                ok, user, msg = login_user(email.strip().lower(), password)
                if ok:
                    # Check forced password change
                    if user.get("must_change_password") == "yes":
                        st.session_state.force_pw_change_user = user
                        st.session_state.current_page         = "force_password_change"
                        st.rerun()
                    else:
                        st.session_state.logged_in    = True
                        st.session_state.user         = user
                        st.session_state.current_page = "dashboard"
                        st.rerun()
                else:
                    st.error(msg)

        st.markdown("---")
        c1, c2 = st.columns(2)
        if c1.button("Create account", width='stretch', type="primary"):
            st.session_state.current_page = "signup"; st.rerun()
        if c2.button("Forgot password?", width='stretch', type="primary"):
            st.session_state.current_page = "forgot_password"; st.rerun()

        st.markdown("""
<div class="lp-trust-strip">
  <span class="lp-trust-item"><span>🔒</span> Bank-level encryption</span>
  <span class="lp-trust-item"><span>☁️</span> Cloud-backed daily</span>
  <span class="lp-trust-item"><span>📱</span> Works on mobile</span>
  <span class="lp-trust-item"><span>🏣</span> Built for all SMEs</span>
</div>

<div style="
  margin-top:2rem;
  padding-top:1.25rem;
  border-top:1px solid #1F2D3D;
  text-align:center;
">
  <div style="font-size:0.72rem;color:#4A6080;margin-bottom:0.75rem;
    font-family:'DM Mono',monospace;letter-spacing:0.05em;">
    Connect With Us
  </div>
  <div style="display:flex;justify-content:center;gap:1.25rem;flex-wrap:wrap;">
    <a href="https://wa.me/+2348136362633"
       target="_blank"
       style="display:inline-flex;align-items:center;gap:0.4rem;
         background:#0a2a1e;border:1px solid #00C896;
         color:#00C896;border-radius:99px;
         padding:0.4rem 1rem;font-size:0.78rem;font-weight:600;
         text-decoration:none;transition:opacity 0.2s;">
      <span>💬</span> WhatsApp
    </a>
    <a href="https://twitter.com/Bayantx360"
       target="_blank"
       style="display:inline-flex;align-items:center;gap:0.4rem;
         background:#0a1525;border:1px solid #1d9bf0;
         color:#1d9bf0;border-radius:99px;
         padding:0.4rem 1rem;font-size:0.78rem;font-weight:600;
         text-decoration:none;transition:opacity 0.2s;">
      <span>𝕏</span> Twitter
    </a>
    <a href="mailto:Bayantx360@gmail.com"
       style="display:inline-flex;align-items:center;gap:0.4rem;
         background:#1a1025;border:1px solid #F5A623;
         color:#F5A623;border-radius:99px;
         padding:0.4rem 1rem;font-size:0.78rem;font-weight:600;
         text-decoration:none;transition:opacity 0.2s;">
      <span>📧</span> Email
    </a>
  </div>
  <div style="margin-top:1.25rem;font-size:0.68rem;color:#2D3F55;">
    © 2026 BizTrack-OS: Powered by Bayantx360 · All rights reserved
  </div>
</div>
        """, unsafe_allow_html=True)


def page_signup():
    apply_suite_css()
    _, col, _ = st.columns([1, 1.6, 1])
    with col:
        st.markdown("""
<div style="text-align:center;margin-bottom:1.5rem;">
  <div style="font-family:'Syne',sans-serif;font-size:1.6rem;font-weight:800;
    color:#F0F4F8;letter-spacing:-0.04em;">Create your account</div>
  <div style="font-size:0.85rem;color:#4A6080;margin-top:0.3rem;">
    Start with a 14-day free trial. No credit card required.</div>
</div>
        """, unsafe_allow_html=True)

        with st.form("signup_form"):
            biz_name  = st.text_input("Business Name *",  placeholder="e.g. BigBay Gadget")
            full_name = st.text_input("Your Full Name *",  placeholder="e.g. Emeka Atanda Salisu")
            phone     = st.text_input("Phone Number *",    placeholder="e.g. 08012345678")
            email     = st.text_input("Email Address *",   placeholder="you@example.com")
            password  = st.text_input("Password *",        type="password",
                                      placeholder="At least 6 characters")
            st.markdown("##### Choose a plan")
            plan_type = st.radio(
                "Plan",
                options=["trial", "monthly", "yearly"],
                format_func=lambda p: {
                    "trial":   f"🎁 Free Trial — 14 days, no payment needed",
                    "monthly": f"📅 Monthly — ₦{PAYMENT_DETAILS['monthly_price']:,}/month",
                    "yearly":  f"🏆 Yearly — ₦{PAYMENT_DETAILS['yearly_price']:,}/year (save ₦3,000)",
                }[p],
                horizontal=False,
            )
            submit = st.form_submit_button("Create Account →", type="primary",
                                           width='stretch')

        if submit:
            if not all([biz_name, full_name, phone, email, password]):
                st.error("Please fill in all required fields.")
            else:
                with st.spinner("Creating your account…"):
                    ok, msg = signup_user(biz_name.strip(), full_name.strip(),
                                          email.strip().lower(), phone.strip(), password, plan_type)
                if ok:
                    if plan_type == "trial":
                        user_obj = get_user_by_email(email.strip().lower())
                        if user_obj:
                            st.session_state.logged_in    = True
                            st.session_state.user         = user_obj
                            st.session_state.current_page = "dashboard"
                            st.rerun()
                    else:
                        user_obj = get_user_by_email(email.strip().lower())
                        if user_obj:
                            st.session_state.logged_in    = True
                            st.session_state.user         = user_obj
                        st.session_state.pending_email = email.strip().lower()
                        st.session_state.pending_plan  = plan_type
                        st.session_state.current_page  = "pending_payment"
                        st.rerun()
                else:
                    st.error(msg)

        st.markdown("---")
        if st.button("← Already have an account? Sign in", width='stretch'):
            st.session_state.current_page = "login"; st.rerun()


def page_forgot_password():
    apply_suite_css()
    _, col, _ = st.columns([1, 1.4, 1])
    with col:
        st.markdown("""
<div style="text-align:center;margin-bottom:1.5rem;">
  <div style="font-size:2.5rem;">🔑</div>
  <div style="font-family:'Syne',sans-serif;font-size:1.4rem;font-weight:800;
    color:#F0F4F8;">Reset your password</div>
  <div style="font-size:0.85rem;color:#4A6080;margin-top:0.3rem;">
    Your admin will set a temporary password for you.</div>
</div>
        """, unsafe_allow_html=True)

        with st.form("forgot_form"):
            email  = st.text_input("Email address", placeholder="you@example.com")
            submit = st.form_submit_button("Request Reset", type="primary",
                                           width='stretch')
        if submit:
            if not email:
                st.error("Please enter your email address.")
            else:
                user = get_user_by_email(email.strip().lower())
                if user:
                    db_update(TBL_USERS, "user_id", user["user_id"], {
                        "password_reset_requested": "yes",
                        "reset_requested_at":       datetime.now().isoformat(),
                    })
                    st.success(
                        "✅ Reset request submitted. Your admin will provide a temporary "
                        "password to complete your Reset shortly."
                    )
                else:
                    st.info("If that email is registered, a reset request has been submitted.")

        st.markdown("---")
        if st.button("← Back to Sign In", width='stretch'):
            st.session_state.current_page = "login"; st.rerun()


def page_force_password_change():
    """Shown when must_change_password == 'yes' (after an admin reset)."""
    apply_suite_css()
    user = st.session_state.get("force_pw_change_user", {})
    _, col, _ = st.columns([1, 1.4, 1])
    with col:
        st.markdown("""
<div style="text-align:center;margin-bottom:1.5rem;">
  <div style="font-size:2rem;">🔐</div>
  <div style="font-family:'Syne',sans-serif;font-size:1.4rem;font-weight:800;color:#F0F4F8;">
    Set a new password</div>
  <div style="font-size:0.85rem;color:#4A6080;margin-top:0.3rem;">
    🔐Your password reset is being processed safely. Please choose a new one before continuing.</div>
</div>
        """, unsafe_allow_html=True)
        with st.form("force_pw_form"):
            new_pw  = st.text_input("New password",     type="password", placeholder="At least 6 characters")
            conf_pw = st.text_input("Confirm password", type="password", placeholder="Repeat new password")
            submit  = st.form_submit_button("Update Password →", type="primary",
                                            width='stretch')
        if submit:
            if len(new_pw) < 6:
                st.error("Password must be at least 6 characters.")
            elif new_pw != conf_pw:
                st.error("Passwords do not match.")
            elif not user:
                st.error("Session expired. Please log in again.")
                st.session_state.current_page = "login"; st.rerun()
            else:
                db_update(TBL_USERS, "user_id", user["user_id"], {
                    "password_hash":        hash_password(new_pw),
                    "must_change_password": "no",
                })
                st.session_state.logged_in    = True
                st.session_state.user         = {**user, "must_change_password": "no"}
                st.session_state.current_page = "dashboard"
                st.session_state.pop("force_pw_change_user", None)
                st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR NAVIGATION
# ══════════════════════════════════════════════════════════════════════════════

def render_sidebar():
    user         = st.session_state.get("user", {})
    current_page = st.session_state.get("current_page", "dashboard")
    is_admin     = user.get("role") == "admin"

    with st.sidebar:
        # ── Logo ──
        st.markdown("""
<div style="display:flex;align-items:center;gap:0.6rem;padding:0.75rem 0 1.25rem;">
  <div style="
    width:40px;height:40px;border-radius:10px;
    background:linear-gradient(135deg,#F5A623,#C4831A);
    display:flex;align-items:center;justify-content:center;
    font-size:1.2rem;box-shadow:0 4px 16px rgba(245,166,35,0.3);
    flex-shrink:0;
  ">📊</div>
  <div>
    <div style="font-family:'Syne',sans-serif;font-size:1.1rem;font-weight:800;
      color:#F0F4F8;letter-spacing:-0.03em;line-height:1;">BizTrack-OS</div>
    <div style="font-size:0.65rem;color:#4A6080;font-family:'DM Mono',monospace;
      letter-spacing:0.05em;">SUITE</div>
  </div>
</div>
        """, unsafe_allow_html=True)

        # ── Business info ──
        biz_name  = user.get("business_name","")
        plan_type = user.get("plan_type","").capitalize()
        plan_end  = user.get("subscription_end","")
        try:
            end_dt    = datetime.strptime(str(plan_end)[:10], "%Y-%m-%d")
            days_left = (end_dt - datetime.now()).days
            expiry_str = f"Expires {end_dt.strftime('%d %b %Y')}"
            if days_left <= 7 and not is_admin:
                expiry_str = f"⚠️ {days_left}d left"
        except Exception:
            expiry_str = ""

        st.markdown(f"""
<div style="background:#111827;border:1px solid #1F2D3D;border-radius:10px;
  padding:0.75rem 0.875rem;margin-bottom:1rem;">
  <div style="font-size:0.78rem;font-weight:700;color:#F0F4F8;
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
    margin-bottom:0.2rem;">{biz_name}</div>
  <div style="font-size:0.68rem;color:#4A6080;font-family:'DM Mono',monospace;">
    {plan_type} {'· ' + expiry_str if expiry_str else ''}</div>
</div>
        """, unsafe_allow_html=True)

        # ── App switcher + page links ──
        pages_to_show = {**APP_PAGES}
        if is_admin:
            pages_to_show["health"] = ["expenses", "insights", "admin"]

        for app_key, page_keys in pages_to_show.items():
            meta = APP_META[app_key]
            st.markdown(f"""
<div style="display:flex;align-items:center;gap:0.4rem;
  margin:0.875rem 0 0.375rem;
  padding-bottom:0.35rem;border-bottom:1px solid #1F2D3D;">
  <span style="font-size:0.9rem;">{meta['icon']}</span>
  <span style="font-size:0.65rem;font-weight:700;color:#4A6080;
    text-transform:uppercase;letter-spacing:0.12em;
    font-family:'DM Mono',monospace;">{meta['label']}</span>
</div>
            """, unsafe_allow_html=True)

            for page_key in page_keys:
                label, emoji, _, _ = PAGES[page_key]
                is_active           = current_page == page_key
                btn_style = (
                    "background:rgba(245,166,35,0.12);border:1px solid rgba(245,166,35,0.3);"
                    "color:#F5A623;"
                    if is_active else
                    "background:transparent;border:1px solid transparent;color:#8BA0B8;"
                )
                btn_html = f"""
<button onclick="window.parent.postMessage({{type:'streamlit:setComponentValue',
  value:'{page_key}'}}, '*')"
  style="width:100%;text-align:left;padding:0.45rem 0.7rem;
    border-radius:8px;cursor:pointer;font-size:0.82rem;font-weight:600;
    margin-bottom:3px;transition:all 0.15s;{btn_style}">
  {emoji} {label}
</button>
                """
                # Use native Streamlit buttons for reliable routing
                btn_clicked = st.button(
                    f"{emoji} {label}",
                    key=f"nav_{page_key}",
                    width='stretch',
                    type="primary" if is_active else "secondary",
                )
                if btn_clicked:
                    st.session_state.current_page = page_key
                    st.rerun()

        # ── Sign out ──
        st.markdown("<div style='margin-top:1.5rem;'></div>", unsafe_allow_html=True)
        st.markdown("---")
        if st.button("⎋ Sign Out", width='stretch'):
            sign_out()
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ROUTER
# ══════════════════════════════════════════════════════════════════════════════

def main():
    init_session_state()

    current_page = st.session_state.get("current_page", "login")
    logged_in    = st.session_state.get("logged_in", False)

    # ── Unauthenticated routes ─────────────────────────────────────────────────
    if not logged_in:
        route_map = {
            "login":           page_login,
            "signup":          page_signup,
            "forgot_password": page_forgot_password,
            "force_password_change": page_force_password_change,
            "pending_payment": lambda: __import__(
                "shared.auth", fromlist=["_page_pending_payment"]
            )._page_pending_payment(st.session_state.get("user", {})),
        }
        fn = route_map.get(current_page, page_login)
        fn()
        return

    # ── Authenticated routes ───────────────────────────────────────────────────
    render_sidebar()

    # Subscription guard — exits early if pending / expired
    if not check_access():
        return

    # Dispatch to page render function
    page_entry = PAGES.get(current_page)
    if page_entry:
        _, _, _, render_fn = page_entry
        render_fn()
    else:
        # Fallback to dashboard
        st.session_state.current_page = "dashboard"
        page_dashboard()


if __name__ == "__main__":
    # ── Branded splash to mask the initial Streamlit render flash ──
    if not st.session_state.get("_splash_done"):
        splash = st.empty()
        splash.markdown("""
<style>
.splash-wrap {
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    height: 80vh; gap: 1rem;
}
.splash-icon {
    width: 72px; height: 72px; border-radius: 18px;
    background: linear-gradient(135deg, #F5A623, #C4831A);
    display: flex; align-items: center; justify-content: center;
    font-size: 2rem;
    box-shadow: 0 8px 32px rgba(245,166,35,0.35);
}
.splash-title {
    font-family: 'Syne', sans-serif;
    font-size: 1.8rem; font-weight: 800;
    color: #F0F4F8; letter-spacing: -0.03em;
}
.splash-sub {
    font-size: 0.8rem; color: #4A6080;
    font-family: 'DM Mono', monospace;
    letter-spacing: 0.1em; text-transform: uppercase;
}
</style>
<div class="splash-wrap">
  <div class="splash-icon">📊</div>
  <div class="splash-title">BizTrack-OS</div>
  <div class="splash-sub">Loading your suite…</div>
</div>
        """, unsafe_allow_html=True)
        st.session_state["_splash_done"] = True
        st.rerun()
    else:
        main()
