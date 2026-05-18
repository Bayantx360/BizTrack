# ============================================================
#  app.py — Entry point: config, routing, main()
#  All logic lives in dedicated modules.
# ============================================================

import streamlit as st
from styles import inject_styles, inject_sidebar_toggle
from sidebar import render_sidebar, check_access

# ── Page imports from views/ (NOT pages/ — avoids Streamlit multipage conflict) ──
from views.page_login         import page_login
from views.page_signup        import page_signup
from views.page_pending       import page_pending_payment
from views.page_forgot        import page_forgot_password
from views.page_change_pw     import page_change_password
from views.page_dashboard     import page_dashboard
from views.page_record_sale   import page_record_sale
from views.page_sales_history import page_sales_history
from views.page_products      import page_products
from views.page_expenses      import page_expenses
from views.page_insights      import page_insights
from views.page_admin         import page_admin

# ── Streamlit page config (must be first st call) ──
st.set_page_config(
    page_title="BizPulse — SME Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main():
    inject_styles()
    inject_sidebar_toggle()

    if "user" not in st.session_state:
        st.session_state.user = None

    user = st.session_state.user

    # Unauthenticated routes
    if user is None:
        page = st.session_state.get("auth_page", "login")
        if   page == "login":    page_login()
        elif page == "signup":   page_signup()
        elif page == "forgot":   page_forgot_password()
        elif page == "pending":  page_pending_payment()
        return

    # Force password change
    if user.get("must_change_password") == "yes":
        page_change_password(forced=True)
        return

    # Pending payment
    if user.get("plan_status") == "pending_payment":
        page_pending_payment()
        return

    # Authenticated
    render_sidebar()
    if not check_access():
        return

    page = st.session_state.get("current_page", "dashboard")

    if   page == "dashboard":       page_dashboard()
    elif page == "record_sale":     page_record_sale()
    elif page == "sales_history":   page_sales_history()
    elif page == "products":        page_products()
    elif page == "expenses":        page_expenses()
    elif page == "insights":        page_insights()
    elif page == "admin":           page_admin()
    elif page == "change_password": page_change_password(forced=False)
    else:
        page_dashboard()


if __name__ == "__main__":
    main()
