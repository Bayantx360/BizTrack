"""
shared/auth.py
══════════════════════════════════════════════════════════════════════
BizTrack Suite — Unified Authentication & Subscription Engine
══════════════════════════════════════════════════════════════════════

Single source of truth for:
  • Password hashing + verification
  • User lookup and login (including admin shortcut)
  • Signup + trial/paid flow
  • Subscription active check
  • Session state initialisation + sign-out
  • Subscription guard (check_access) called by main router

All three page modules + suite_home.py import from here:
    from shared.auth import (
        init_session_state,
        login_user,
        signup_user,
        sign_out,
        check_access,
        get_user_by_email,
        is_subscription_active,
        SUITE_SESSION_KEYS,
    )
"""

from __future__ import annotations

from datetime import datetime, timedelta

import bcrypt
import streamlit as st

from shared.db import (
    db_fetch, db_insert, db_update,
    get_supabase,
    TBL_USERS,
    PAYMENT_DETAILS,
    gen_id, validate_email, parse_date, fmt_naira,
)

# ── Admin credentials (from secrets) ──────────────────────────────────────────
def _admin_email() -> str:
    return st.secrets["admin"]["email"]

def _admin_password() -> str:
    return st.secrets["admin"]["password"]

def _admin_biz_id() -> str:
    return st.secrets["admin"]["business_id"]


# ── All session keys the suite uses — for clean logout / page reset ────────────
SUITE_SESSION_KEYS = [
    "logged_in", "user", "current_page",
    # per-app transient state
    "cart", "sale_done", "pending_email", "pending_plan",
    "sale_feedback", "prod_page", "exp_page",
]


# ══════════════════════════════════════════════════════════════════════════════
# SESSION STATE HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def init_session_state():
    """Seed required session state keys on first run."""
    defaults = {
        "logged_in":    False,
        "current_page": "login",
        "user":         {},
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def sign_out():
    """Clear all suite session state and return to login."""
    for key in SUITE_SESSION_KEYS:
        st.session_state.pop(key, None)
    st.session_state.logged_in    = False
    st.session_state.current_page = "login"
    st.session_state.user         = {}


# ══════════════════════════════════════════════════════════════════════════════
# PASSWORD HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def check_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════════
# USER LOOKUP
# ══════════════════════════════════════════════════════════════════════════════

def get_user_by_email(email: str):
    """Return user dict or None."""
    try:
        sb  = get_supabase()
        res = sb.table(TBL_USERS).select("*").ilike("email", email).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        st.error(f"Error fetching user: {e}")
        return None


def is_subscription_active(user: dict) -> bool:
    """Check if user has an active, non-expired subscription."""
    if user.get("plan_status") != "active":
        return False
    end = parse_date(user.get("subscription_end", ""))
    if end is None:
        return False
    return datetime.now() <= end


# ══════════════════════════════════════════════════════════════════════════════
# LOGIN
# ══════════════════════════════════════════════════════════════════════════════

def login_user(email: str, password: str):
    """
    Validate credentials. Returns (success, user_dict, message).
    Admin login is handled separately via secrets.
    """
    # Admin shortcut — credentials come from st.secrets, never from the DB
    if email.lower() == _admin_email().lower() and password == _admin_password():
        admin_user = {
            "user_id":           "ADMIN",
            "business_id":       _admin_biz_id(),
            "business_name":     "BizTrack Admin",
            "full_name":         "Administrator",
            "email":             _admin_email(),
            "role":              "admin",
            "plan_status":       "active",
            "subscription_end":  (datetime.now() + timedelta(days=3650)).strftime("%Y-%m-%d"),
            "must_change_password": "no",
        }
        return True, admin_user, "Welcome, Admin!"

    user = get_user_by_email(email)
    if not user:
        return False, None, "No account found with that email."
    if not check_password(password, str(user.get("password_hash", ""))):
        return False, None, "Incorrect password."
    return True, user, "Login successful."


# ══════════════════════════════════════════════════════════════════════════════
# SIGNUP
# ══════════════════════════════════════════════════════════════════════════════

def signup_user(business_name, full_name, email, password, plan_type):
    """
    Create a new user account. Returns (success, message).
    Trial → active immediately. Paid plans → pending_payment.
    """
    if not validate_email(email):
        return False, "Please enter a valid email address."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    if get_user_by_email(email):
        return False, "An account with this email already exists."

    user_id     = gen_id("USR")
    business_id = gen_id("BIZ")
    now         = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if plan_type == "trial":
        status = "active"
        start  = datetime.now().strftime("%Y-%m-%d")
        end    = (datetime.now() + timedelta(days=PAYMENT_DETAILS["trial_days"])).strftime("%Y-%m-%d")
    else:
        status = "pending_payment"
        start  = ""
        end    = ""

    success = db_insert(TBL_USERS, {
        "user_id":                  user_id,
        "business_id":              business_id,
        "business_name":            business_name,
        "full_name":                full_name,
        "email":                    email,
        "password_hash":            hash_password(password),
        "role":                     "owner",
        "plan_type":                plan_type,
        "plan_status":              status,
        "subscription_start":       start if start else None,
        "subscription_end":         end   if end   else None,
        "created_at":               now,
        "password_reset_requested": "no",
        "reset_requested_at":       None,
        "must_change_password":     "no",
    })
    if success:
        return True, "Account created successfully."
    return False, "Failed to create account. Please try again."


# ══════════════════════════════════════════════════════════════════════════════
# SUBSCRIPTION GUARD
# ══════════════════════════════════════════════════════════════════════════════

def check_access() -> bool:
    """
    Call at the top of every authenticated page render.
    Returns True if the user may proceed.
    Handles pending_payment and expired states inline.
    """
    from shared.theme import apply_suite_css  # lazy import to avoid circular
    user = st.session_state.get("user", {})
    role = user.get("role", "")

    # Admin always has access
    if role == "admin":
        return True

    status = user.get("plan_status", "")

    if status == "pending_payment":
        _page_pending_payment(user)
        return False

    if status == "expired":
        _page_expired(user)
        return False

    if not is_subscription_active(user):
        db_update(TBL_USERS, "user_id", user["user_id"], {"plan_status": "expired"})
        st.session_state.user["plan_status"] = "expired"
        st.rerun()

    return True


# ── Inline guard screens ───────────────────────────────────────────────────────

def _page_pending_payment(user: dict):
    plan   = user.get("plan_type") or st.session_state.get("pending_plan", "monthly")
    email  = user.get("email")    or st.session_state.get("pending_email", "")
    amount = (PAYMENT_DETAILS["yearly_price"]
              if plan == "yearly" else PAYMENT_DETAILS["monthly_price"])
    fw_link = (PAYMENT_DETAILS["flutterwave_yearly"]
               if plan == "yearly" else PAYMENT_DETAILS["flutterwave_monthly"])
    savings_note = " — save ₦3,000!" if plan == "yearly" else ""

    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown(
            "<div style='text-align:center;font-size:2rem;font-weight:800;"
            "color:#F0F4F8;margin-bottom:0.25rem;'>📊 BizTrack</div>",
            unsafe_allow_html=True,
        )
        st.markdown("---")
        st.markdown("<div style='text-align:center;font-size:2.5rem;'>🎉</div>",
                    unsafe_allow_html=True)
        st.markdown(
            "<div style='text-align:center;font-size:1.4rem;font-weight:800;"
            "color:#10B981;margin-bottom:0.25rem;'>Account created!</div>",
            unsafe_allow_html=True)
        st.markdown(
            "<div style='text-align:center;color:#8BA0B8;font-size:0.9rem;"
            "margin-bottom:1rem;'>Complete your payment to activate full access.</div>",
            unsafe_allow_html=True)

        with st.container(border=True):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Plan**")
                st.markdown("**Amount**")
                st.markdown("**Email**")
            with c2:
                st.markdown(f":{plan.capitalize()}{savings_note}")
                st.markdown(f"**₦{amount:,}**")
                st.markdown(f"`{email}`")

        st.caption("🔒 Make secure payment via Card/Bank Transfer. Activated within 24 hours.")
        st.link_button(
            f"💳 Pay ₦{amount:,} via Flutterwave 👉→",
            url=fw_link, width='stretch', type="primary",
        )
        st.caption("Already paid? Your account will be activated shortly✅️.")
        if st.button("← Back and Sign In", width='content', type="primary"):
            sign_out()
            st.rerun()
        #st.caption("Already paid? Your account will be activated shortly✅️.")


def _page_expired(user: dict):
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown("""
<div style="text-align:center;">
<div style="font-size:2.5rem;margin-bottom:0.5rem;">⏰</div>
<div style="font-size:1.4rem;font-weight:800;color:#F0F4F8;margin-bottom:0.5rem;">
Subscription Expired</div>
<div style="color:#8BA0B8;font-size:0.9rem;margin-bottom:1.5rem;">
Your access period has ended. Renew to continue using BizTrack.</div>
</div>
        """, unsafe_allow_html=True)
        with st.container(border=True):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("Monthly")
                st.markdown("Yearly")
            with c2:
                st.markdown(f"**₦{PAYMENT_DETAILS['monthly_price']:,}/mo**")
                st.markdown(f"**₦{PAYMENT_DETAILS['yearly_price']:,}/yr** — save ₦3,000")
        st.link_button(
            f"💳 Renew Monthly — ₦{PAYMENT_DETAILS['monthly_price']:,}",
            url=PAYMENT_DETAILS["flutterwave_monthly"],
            use_container_width=True, type="primary",
        )
        st.link_button(
            f"🏆 Renew Yearly — ₦{PAYMENT_DETAILS['yearly_price']:,} (best value)",
            url=PAYMENT_DETAILS["flutterwave_yearly"],
            use_container_width=True,
        )
        if st.button("Sign Out", width='stretch'):
            sign_out()
            st.rerun()
