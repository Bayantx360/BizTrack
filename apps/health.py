"""
pages/health.py
══════════════════════════════════════════════════════════════════════
BizTrack Suite — Business Health App
══════════════════════════════════════════════════════════════════════

Pages contained in this module:
  • Expenses       — log, view, edit, delete expenses with charts
  • Insights       — monthly trends, product analysis, export
  • Admin Panel    — platform management (admin role only)

Cross-app links:
  • compute_kpis pulls both sales + expenses → net profit card
  • compute_insights pulls sales + products → stockout, slow movers
"""

from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from shared.db import (
    get_sales_df, get_products_df, get_expenses_df,
    compute_kpis, compute_insights,
    db_fetch, db_insert, db_update, db_delete,
    get_payments_df, log_payment,
    TBL_USERS, TBL_EXPENSES, TBL_PAYMENTS,
    PAYMENT_DETAILS,
    gen_id, fmt_naira, safe_float, safe_int, parse_date,
)
from shared.theme import (
    apply_suite_css, kpi_card, section_header, page_header,
)


# ══════════════════════════════════════════════════════════════════════════════
# EXPENSES
# ══════════════════════════════════════════════════════════════════════════════

def page_expenses():
    apply_suite_css()
    user        = st.session_state.user
    business_id = user["business_id"]

    page_header("💸 Expense Tracker", "Log and monitor your business expenses")

    tab1, tab2 = st.tabs(["📋 View Expenses", "➕ Log Expense"])

    # ══════════════════════
    # Tab 1 — View
    # ══════════════════════
    with tab1:
        expenses_df = get_expenses_df(business_id)
        if expenses_df.empty:
            st.info("No expenses logged yet.")
        else:
            col1, col2 = st.columns(2)
            start_date = col1.date_input("From", value=(datetime.now() - timedelta(days=30)).date())
            end_date   = col2.date_input("To",   value=datetime.now().date())

            filtered = expenses_df[
                (expenses_df["expense_date"].dt.date >= start_date) &
                (expenses_df["expense_date"].dt.date <= end_date)
            ]

            c1, c2, c3 = st.columns(3)
            with c1:
                kpi_card("Total Expenses", fmt_naira(filtered["amount"].sum()),
                         "In selected period", icon="💸")
            with c2:
                kpi_card("Transactions", str(len(filtered)), "Expense entries", icon="🧾")
            with c3:
                avg = filtered["amount"].mean() if not filtered.empty else 0
                kpi_card("Average Expense", fmt_naira(avg), "Per entry", icon="📊")

            if not filtered.empty:
                # Category breakdown chart
                cat_breakdown = (
                    filtered.groupby("category")["amount"]
                    .sum().reset_index()
                    .sort_values("amount", ascending=False)
                )
                if not cat_breakdown.empty:
                    with st.expander("📊 Expenses by Category", expanded=True):
                        fig = px.bar(
                            cat_breakdown, x="category", y="amount",
                            labels={"amount": "Amount (₦)", "category": "Category"},
                            color_discrete_sequence=["#ef4444"],
                        )
                        fig.update_layout(
                            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                            margin=dict(l=0, r=0, t=10, b=0), height=280,
                        )
                        st.plotly_chart(fig, use_container_width=True)

                # Search
                exp_search = st.text_input("🔍 Search expenses", key="exp_search",
                                           placeholder="Filter by description…")
                if exp_search:
                    filtered = filtered[
                        filtered["description"].str.contains(exp_search, case=False, na=False)
                    ]

                # Pagination
                EXP_PAGE  = 20
                exp_pages = max(1, -(-len(filtered) // EXP_PAGE))
                if "exp_page" not in st.session_state:
                    st.session_state.exp_page = 1
                exp_pg     = st.session_state.exp_page
                page_slice = filtered.sort_values("expense_date", ascending=False)
                page_slice = page_slice.iloc[(exp_pg-1)*EXP_PAGE: exp_pg*EXP_PAGE]

                st.caption(f"Showing {len(page_slice)} of {len(filtered)} entries  •  Page {exp_pg} of {exp_pages}")
                st.markdown("---")

                for _, r in page_slice.iterrows():
                    exp_id = r["expense_id"]
                    with st.expander(
                        f"**{r['description']}** | {r['category']} | "
                        f"{fmt_naira(r['amount'])} | "
                        f"{r['expense_date'].strftime('%d %b %Y') if pd.notna(r['expense_date']) else ''}",
                        expanded=False,
                    ):
                        _EXP_CATS = ["Rent","Utilities","Salaries","Supplies","Transport",
                                     "Marketing","Maintenance","Taxes","Miscellaneous"]
                        with st.form(f"edit_exp_{exp_id}"):
                            ef1, ef2   = st.columns(2)
                            new_name   = ef1.text_input("Description", value=r["description"])
                            cat_idx    = _EXP_CATS.index(r["category"]) if r["category"] in _EXP_CATS else 0
                            new_cat    = ef2.selectbox("Category", _EXP_CATS, index=cat_idx)
                            new_amt    = ef1.number_input("Amount (₦)", value=safe_float(r["amount"]),
                                                          min_value=0.0, step=100.0)
                            new_date   = ef2.date_input(
                                "Date",
                                value=r["expense_date"].date() if pd.notna(r["expense_date"]) else datetime.now().date(),
                            )
                            save_exp   = st.form_submit_button("💾 Save Changes", type="primary")

                        if save_exp:
                            ok = db_update(TBL_EXPENSES, "expense_id", exp_id, {
                                "description": new_name.strip(),
                                "category":     new_cat,
                                "amount":       new_amt,
                                "expense_date": str(new_date),
                            })
                            st.session_state[f"exp_msg_{exp_id}"] = (
                                "✅ Expense updated." if ok else "❌ Failed to update."
                            )
                            st.rerun()

                        if f"exp_msg_{exp_id}" in st.session_state:
                            msg = st.session_state.pop(f"exp_msg_{exp_id}")
                            (st.success if msg.startswith("✅") else st.error)(msg)

                        confirm_key = f"confirm_del_exp_{exp_id}"
                        if not st.session_state.get(confirm_key, False):
                            if st.button("🗑️ Delete this expense", key=f"del_exp_{exp_id}"):
                                st.session_state[confirm_key] = True
                                st.rerun()
                        else:
                            st.warning("⚠️ Delete this expense permanently?")
                            ce1, ce2 = st.columns(2)
                            if ce1.button("✅ Yes, delete", key=f"yes_del_exp_{exp_id}", type="primary"):
                                ok = db_delete(TBL_EXPENSES, "expense_id", exp_id)
                                st.session_state.pop(confirm_key, None)
                                st.session_state["exp_del_msg"] = (
                                    "✅ Expense deleted." if ok else "❌ Failed to delete."
                                )
                                st.rerun()
                            if ce2.button("❌ Cancel", key=f"no_del_exp_{exp_id}"):
                                st.session_state.pop(confirm_key, None)
                                st.rerun()

                        if "exp_del_msg" in st.session_state:
                            msg = st.session_state.pop("exp_del_msg")
                            (st.success if msg.startswith("✅") else st.error)(msg)

                if exp_pages > 1:
                    st.markdown("---")
                    ep1, ep2, ep3 = st.columns([1, 3, 1])
                    if ep1.button("◀ Prev", disabled=(exp_pg <= 1), key="exp_prev"):
                        st.session_state.exp_page = max(1, exp_pg-1); st.rerun()
                    ep2.markdown(
                        f"<div style='text-align:center;padding-top:0.5rem;color:#8BA0B8;'>"
                        f"Page {exp_pg} of {exp_pages}</div>",
                        unsafe_allow_html=True,
                    )
                    if ep3.button("Next ▶", disabled=(exp_pg >= exp_pages), key="exp_next"):
                        st.session_state.exp_page = min(exp_pages, exp_pg+1); st.rerun()

    # ══════════════════════
    # Tab 2 — Log Expense
    # ══════════════════════
    with tab2:
        with st.form("log_expense_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            exp_name   = col1.text_input("Description *", placeholder="e.g. Generator fuel")
            category   = col2.selectbox("Category", [
                "Rent","Utilities","Salaries","Supplies","Transport",
                "Marketing","Maintenance","Taxes","Miscellaneous",
            ])
            amount       = col1.number_input("Amount (₦) *", min_value=0.0, step=100.0)
            expense_date = col2.date_input("Date", value=datetime.now().date())
            submitted    = st.form_submit_button("Log Expense", use_container_width=True, type="primary")

        if submitted:
            if not exp_name or amount <= 0:
                st.error("Please fill in description and a valid amount.")
            else:
                ok = db_insert(TBL_EXPENSES, {
                    "expense_id":   gen_id("EXP"),
                    "business_id":  business_id,
                    "description": exp_name.strip(),
                    "category":     category,
                    "amount":       amount,
                    "expense_date": str(expense_date),
                    "recorded_by":  user.get("full_name", user.get("email", "")),
                })
                if ok:
                    st.success(f"✅ Expense logged: {exp_name} — {fmt_naira(amount)}")
                    st.rerun()
                else:
                    st.error("Failed to log expense.")


# ══════════════════════════════════════════════════════════════════════════════
# INSIGHTS
# ══════════════════════════════════════════════════════════════════════════════

def page_insights():
    apply_suite_css()
    user        = st.session_state.user
    business_id = user["business_id"]

    page_header("🧠 Business Insights", "Data-driven intelligence for smarter decisions")

    with st.spinner("Crunching your numbers…"):
        sales_df    = get_sales_df(business_id)
        products_df = get_products_df(business_id)
        expenses_df = get_expenses_df(business_id)
        insights    = compute_insights(sales_df, products_df, expenses_df)
        kpis        = compute_kpis(sales_df, expenses_df)

    if sales_df.empty:
        st.info("📭 No data yet. Record some sales to unlock insights.")
        return

    # ── Summary KPIs ──
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Avg Daily Revenue", fmt_naira(insights["avg_daily_revenue"]),
                 "Based on all recorded days", icon="📅")
    with c2:
        kpi_card("Best Sales Day", insights.get("best_day","N/A"),
                 "Highest revenue weekday", icon="🏆")
    with c3:
        kpi_card("Slowest Day", insights.get("worst_day","N/A"),
                 "Lowest revenue weekday", icon="🐢")
    with c4:
        best = (insights["top_products_revenue"].iloc[0]["product_name"]
                if not insights["top_products_revenue"].empty else "N/A")
        kpi_card("Best Seller", best, "By total revenue", icon="⭐")

    # ── Net Profit Banner ──
    net = kpis["net_profit"]
    banner_color = "#0a2a1e" if net >= 0 else "#2a0a11"
    border_color = "#00C896" if net >= 0 else "#FF4D6D"
    text_color   = "#00C896" if net >= 0 else "#FF4D6D"
    st.markdown(f"""
<div style="background:{banner_color};border:1px solid {border_color};
border-radius:12px;padding:1rem 1.25rem;margin:1rem 0;
display:flex;align-items:center;justify-content:space-between;">
  <div>
    <div style="font-size:0.7rem;color:#8BA0B8;text-transform:uppercase;
    letter-spacing:0.1em;font-family:'DM Mono',monospace;margin-bottom:0.25rem;">
      Net Profit This Month</div>
    <div style="font-family:'Syne',sans-serif;font-size:1.8rem;font-weight:800;
    color:{text_color};letter-spacing:-0.04em;">{fmt_naira(net)}</div>
  </div>
  <div style="text-align:right;font-size:0.82rem;color:#8BA0B8;">
    Revenue: {fmt_naira(kpis['month_revenue'])}<br>
    Gross Profit: {fmt_naira(kpis['month_profit'])}<br>
    Expenses: {fmt_naira(kpis['month_expenses'])}
  </div>
</div>
    """, unsafe_allow_html=True)

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["📈 Trends", "🏆 Products", "📦 Inventory", "📅 Weekday", "📊 Export"]
    )

    # ══════════════════════
    # Tab 1 — Monthly Trends
    # ══════════════════════
    with tab1:
        section_header("Monthly Performance Comparison")

        if not sales_df.empty:
            ms = sales_df.copy()
            ms["year"]        = ms["sale_date"].dt.year
            ms["month_label"] = ms["sale_date"].dt.strftime("%b %Y")
            ms["month_sort"]  = ms["sale_date"].dt.to_period("M")

            available_years = sorted(ms["year"].unique().tolist(), reverse=True)
            tf1, tf2, tf3   = st.columns(3)
            selected_year   = tf1.selectbox("Year", ["All years"] + [str(y) for y in available_years],
                                            key="ins_year")
            metric_choice   = tf2.selectbox("Metric",
                                            ["Revenue & Profit","Revenue only","Profit only",
                                             "All (Revenue, Cost, Profit)"],
                                            key="ins_metric")
            num_months      = tf3.slider("Last N months", min_value=3, max_value=24,
                                         value=12, key="ins_months")

            if selected_year != "All years":
                ms = ms[ms["year"] == int(selected_year)]

            monthly = (
                ms.groupby(["month_sort","month_label"])
                .agg(
                    revenue  =("total_amount","sum"),
                    cost     =("cost_total","sum"),
                    profit   =("gross_profit","sum"),
                    txn_count=("sale_id","count"),
                )
                .reset_index()
                .sort_values("month_sort")
            )

            if not expenses_df.empty:
                ex = expenses_df.copy()
                ex["month_sort"] = ex["expense_date"].dt.to_period("M")
                monthly_exp = (
                    ex.groupby("month_sort")["amount"].sum()
                    .reset_index().rename(columns={"amount":"expenses"})
                )
                monthly = monthly.merge(monthly_exp, on="month_sort", how="left")
                monthly["expenses"]   = monthly["expenses"].fillna(0)
                monthly["net_profit"] = monthly["profit"] - monthly["expenses"]
            else:
                monthly["expenses"]   = 0
                monthly["net_profit"] = monthly["profit"]

            monthly = monthly.tail(num_months)

            if monthly.empty:
                st.info("No data for the selected filters.")
            else:
                best_rev_row  = monthly.loc[monthly["revenue"].idxmax()]
                best_prof_row = monthly.loc[monthly["net_profit"].idxmax()]
                mom_growth    = 0
                if len(monthly) >= 2:
                    last_rev = monthly.iloc[-1]["revenue"]
                    prev_rev = monthly.iloc[-2]["revenue"]
                    if prev_rev:
                        mom_growth = (last_rev - prev_rev) / prev_rev * 100

                sk1, sk2, sk3, sk4 = st.columns(4)
                with sk1:
                    kpi_card("Best Month (Revenue)", best_rev_row["month_label"],
                             fmt_naira(best_rev_row["revenue"]), icon="🏆")
                with sk2:
                    kpi_card("Best Month (Profit)", best_prof_row["month_label"],
                             fmt_naira(best_prof_row["net_profit"]), icon="💎")
                with sk3:
                    kpi_card("Latest Month Growth",
                             f"{'▲' if mom_growth >= 0 else '▼'} {abs(mom_growth):.1f}%",
                             "vs previous month", positive=(mom_growth >= 0), icon="📈")
                with sk4:
                    kpi_card("Period Total", fmt_naira(monthly["revenue"].sum()),
                             f"{int(monthly['txn_count'].sum())} transactions", icon="📊")

                st.markdown("---")

                x_labels = monthly["month_label"].tolist()
                fig = go.Figure()
                if metric_choice in ["Revenue & Profit","Revenue only","All (Revenue, Cost, Profit)"]:
                    fig.add_trace(go.Bar(name="Revenue", x=x_labels, y=monthly["revenue"],
                                        marker_color="#6366f1",
                                        hovertemplate="%{x}<br>Revenue: ₦%{y:,.0f}<extra></extra>"))
                if metric_choice == "All (Revenue, Cost, Profit)":
                    fig.add_trace(go.Bar(name="Cost", x=x_labels, y=monthly["cost"],
                                        marker_color="#ef4444",
                                        hovertemplate="%{x}<br>Cost: ₦%{y:,.0f}<extra></extra>"))
                if metric_choice in ["Revenue & Profit","Profit only","All (Revenue, Cost, Profit)"]:
                    fig.add_trace(go.Bar(name="Net Profit", x=x_labels, y=monthly["net_profit"],
                                        marker_color="#00C896",
                                        hovertemplate="%{x}<br>Net Profit: ₦%{y:,.0f}<extra></extra>"))
                fig.update_layout(
                    barmode="group",
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=0, r=0, t=20, b=0), height=320,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                xanchor="right", x=1, font=dict(size=11)),
                    xaxis=dict(type="category", tickangle=-45, tickfont=dict(size=10),
                               gridcolor="rgba(0,0,0,0)"),
                    yaxis=dict(tickprefix="₦", tickformat=",.0f",
                               gridcolor="rgba(255,255,255,0.06)", tickfont=dict(size=11)),
                    bargap=0.2, bargroupgap=0.05,
                )
                with st.expander("📈 Monthly Performance Chart", expanded=True):
                    st.plotly_chart(fig, use_container_width=True)

                with st.expander("📋 View monthly breakdown table"):
                    dm = monthly[["month_label","revenue","cost","profit",
                                  "expenses","net_profit","txn_count"]].copy()
                    dm.columns = ["Month","Revenue","Cost","Gross Profit",
                                  "Expenses","Net Profit","Transactions"]
                    for col in ["Revenue","Cost","Gross Profit","Expenses","Net Profit"]:
                        dm[col] = dm[col].apply(fmt_naira)
                    st.dataframe(dm, use_container_width=True, hide_index=True)

        # Category performance
        st.markdown("---")
        section_header("Category Performance")
        if not insights["category_revenue"].empty:
            with st.expander("🗂️ Revenue by Category", expanded=True):
                cat_fig = px.bar(
                    insights["category_revenue"].sort_values("total_amount"),
                    x="total_amount", y="category", orientation="h",
                    labels={"total_amount":"Revenue (₦)","category":""},
                    color_discrete_sequence=["#F5A623"],
                )
                cat_fig.update_layout(
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=0, r=0, t=10, b=0),
                    height=max(200, len(insights["category_revenue"]) * 45),
                    xaxis=dict(tickprefix="₦", tickformat=",.0f",
                               gridcolor="rgba(255,255,255,0.06)"),
                )
                st.plotly_chart(cat_fig, use_container_width=True)
        else:
            st.info("No category data yet.")

    # ══════════════════════
    # Tab 2 — Products
    # ══════════════════════
    with tab2:
        with st.expander("🏆 Top Products by Revenue", expanded=True):
            col_l, col_r = st.columns(2)
            with col_l:
                section_header("By Revenue")
                if not insights["top_products_revenue"].empty:
                    fig = px.bar(
                        insights["top_products_revenue"].sort_values("total_amount"),
                        x="total_amount", y="product_name", orientation="h",
                        labels={"total_amount":"Revenue (₦)","product_name":""},
                        color_discrete_sequence=["#6366f1"],
                    )
                    fig.update_layout(
                        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                        margin=dict(l=0, r=0, t=10, b=0), height=350,
                        xaxis=dict(tickprefix="₦"),
                    )
                    st.plotly_chart(fig, use_container_width=True)

            with col_r:
                section_header("By Quantity Sold")
                if not insights["top_products_qty"].empty:
                    fig2 = px.bar(
                        insights["top_products_qty"].sort_values("quantity"),
                        x="quantity", y="product_name", orientation="h",
                        labels={"quantity":"Units Sold","product_name":""},
                        color_discrete_sequence=["#10b981"],
                    )
                    fig2.update_layout(
                        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                        margin=dict(l=0, r=0, t=10, b=0), height=350,
                    )
                    st.plotly_chart(fig2, use_container_width=True)

        section_header("⚠️ Slow-Moving Products (Last 30 Days)")
        if not insights["slow_movers"].empty:
            st.dataframe(
                insights["slow_movers"].rename(
                    columns={"product_name":"Product","quantity":"Units Sold (30d)"}
                ),
                use_container_width=True,
            )
        else:
            st.markdown('<div class="alert-success">✅ All products are selling at healthy rates.</div>',
                        unsafe_allow_html=True)

    # ══════════════════════
    # Tab 3 — Inventory
    # ══════════════════════
    with tab3:
        section_header("🔴 Low Stock Products")
        if not insights["low_stock"].empty:
            for _, r in insights["low_stock"].iterrows():
                qty = safe_int(r["stock_quantity"])
                css = "alert-critical" if qty <= 0 else "alert-low"
                st.markdown(
                    f'<div class="{css}">⚠️ <strong>{r["product_name"]}</strong> '
                    f'— {qty} units left (reorder at {safe_int(r["reorder_level"])})</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.markdown('<div class="alert-success">✅ All products have sufficient stock.</div>',
                        unsafe_allow_html=True)

        section_header("📅 Projected Stockout Dates")
        if not insights["stockout_projection"].empty:
            proj = insights["stockout_projection"].copy()
            proj["stockout_date"] = proj["days_until_stockout"].apply(
                lambda d: (datetime.now() + timedelta(days=d)).strftime("%d %b %Y")
            )
            proj["urgency"] = proj["days_until_stockout"].apply(
                lambda d: "🔴 Critical" if d <= 3 else ("🟡 Soon" if d <= 7 else "🟢 OK")
            )
            st.dataframe(
                proj[["product_name","stock_quantity","avg_daily_sales",
                      "days_until_stockout","stockout_date","urgency"]]
                .rename(columns={
                    "product_name":       "Product",
                    "stock_quantity":     "Current Stock",
                    "avg_daily_sales":    "Avg Daily Sales",
                    "days_until_stockout":"Days Left",
                    "stockout_date":      "Est. Stockout Date",
                    "urgency":            "Status",
                }),
                use_container_width=True,
            )
        else:
            st.info("Not enough sales history to project stockout dates.")

    # ══════════════════════
    # Tab 4 — Weekday
    # ══════════════════════
    with tab4:
        section_header("Revenue by Day of Week")
        if not insights["weekday_performance"].empty:
            with st.expander("📅 Weekday Revenue Chart", expanded=True):
                wd     = insights["weekday_performance"]
                colors = [
                    "#ef4444" if r == wd["revenue"].min()
                    else ("#10b981" if r == wd["revenue"].max() else "#6366f1")
                    for r in wd["revenue"]
                ]
                fig = go.Figure(go.Bar(
                    x=wd["weekday"], y=wd["revenue"],
                    marker_color=colors,
                    text=[fmt_naira(v) for v in wd["revenue"]],
                    textposition="outside",
                ))
                fig.update_layout(
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=0, r=0, t=10, b=0),
                    yaxis=dict(tickprefix="₦", gridcolor="rgba(255,255,255,0.06)"),
                    height=350,
                )
                st.plotly_chart(fig, use_container_width=True)

            if insights["best_day"] and insights["worst_day"]:
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(
                        f'<div class="alert-success">🏆 <strong>Best day:</strong> '
                        f'{insights["best_day"]} — schedule more staff and stock up.</div>',
                        unsafe_allow_html=True,
                    )
                with col2:
                    st.markdown(
                        f'<div class="alert-low">💡 <strong>Slowest day:</strong> '
                        f'{insights["worst_day"]} — consider promotions or discounts.</div>',
                        unsafe_allow_html=True,
                    )

    # ══════════════════════
    # Tab 5 — Export
    # ══════════════════════
    with tab5:
        section_header("📥 Download Your Data")
        col1, col2, col3 = st.columns(3)
        with col1:
            if not sales_df.empty:
                st.download_button("⬇️ Download Sales CSV",
                                   data=sales_df.to_csv(index=False).encode("utf-8"),
                                   file_name="sales_export.csv", mime="text/csv",
                                   use_container_width=True)
        with col2:
            products_df = get_products_df(business_id)
            if not products_df.empty:
                st.download_button("⬇️ Download Products CSV",
                                   data=products_df.to_csv(index=False).encode("utf-8"),
                                   file_name="products_export.csv", mime="text/csv",
                                   use_container_width=True)
        with col3:
            if not expenses_df.empty:
                st.download_button("⬇️ Download Expenses CSV",
                                   data=expenses_df.to_csv(index=False).encode("utf-8"),
                                   file_name="expenses_export.csv", mime="text/csv",
                                   use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN PANEL
# ══════════════════════════════════════════════════════════════════════════════

def page_admin():
    apply_suite_css()
    user = st.session_state.user
    if user.get("role") != "admin":
        st.error("⛔ Access denied.")
        return

    page_header("🛡️ Admin Panel", "BizTrack platform management")

    users_df = db_fetch(TBL_USERS)
    if users_df.empty:
        st.info("No users found.")
        return

    # Platform stats
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Total Businesses", str(len(users_df)), "Registered accounts", icon="🏢")
    with c2:
        active = len(users_df[users_df["plan_status"] == "active"])
        kpi_card("Active Subscriptions", str(active), "Paying or trial users", icon="✅")
    with c3:
        pending = len(users_df[users_df["plan_status"] == "pending_payment"])
        kpi_card("Pending Payment", str(pending), "Awaiting manual activation", icon="⏳")
    with c4:
        monthly_rev = (len(users_df[(users_df["plan_type"] == "monthly") &
                                    (users_df["plan_status"] == "active")]) *
                       PAYMENT_DETAILS["monthly_price"])
        yearly_rev  = (len(users_df[(users_df["plan_type"] == "yearly") &
                                    (users_df["plan_status"] == "active")]) *
                       (PAYMENT_DETAILS["yearly_price"] / 12))
        kpi_card("Est. MRR", fmt_naira(monthly_rev + yearly_rev),
                 "From active paid plans", icon="📈")

    # Revenue ledger KPIs
    payments_df = get_payments_df()
    if not payments_df.empty:
        now_dt      = datetime.now()
        month_start = datetime(now_dt.year, now_dt.month, 1)
        year_start  = datetime(now_dt.year, 1, 1)

        total_collected = payments_df["amount"].sum()
        month_collected = payments_df[payments_df["payment_date"] >= month_start]["amount"].sum()
        year_collected  = payments_df[payments_df["payment_date"] >= year_start]["amount"].sum()
        total_txns      = len(payments_df)

        st.markdown("---")
        st.markdown("#### 💰 Platform Revenue — Actual Collected")
        r1, r2, r3, r4 = st.columns(4)
        with r1: kpi_card("All-Time Revenue",  fmt_naira(total_collected), f"{total_txns} payments", icon="💰")
        with r2: kpi_card("This Month",        fmt_naira(month_collected), now_dt.strftime("%B %Y"), icon="📅")
        with r3: kpi_card("This Year",         fmt_naira(year_collected),  str(now_dt.year),         icon="🗓️")
        with r4:
            avg = total_collected / total_txns if total_txns else 0
            kpi_card("Avg. per Payment", fmt_naira(avg), "Across all activations", icon="🧾")
    else:
        st.info("💡 No payment records yet.")

    st.markdown("---")
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "⏳ Pending Activation", "✅ Active Users", "📈 MRR & Growth",
        "🚨 Churn Alerts", "🔑 Password Resets", "👥 All Users", "⛔ Deactivated",
    ])

    # ── Pending ──
    with tab1:
        pending_df = users_df[users_df["plan_status"] == "pending_payment"]
        if pending_df.empty:
            st.success("No pending activations.")
        else:
            for _, u in pending_df.iterrows():
                with st.container():
                    col1, col2, col3 = st.columns([3,2,2])
                    with col1:
                        st.markdown(f"**{u['business_name']}** — {u['full_name']}")
                        st.caption(f"📧 {u['email']} | Plan: {u['plan_type']} | Signed up: {u['created_at']}")
                    with col2:
                        plan   = u["plan_type"]
                        days   = 30 if plan == "monthly" else 365
                        end_dt = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
                        if st.button("✅ Activate", key=f"act_{u['user_id']}"):
                            ok = db_update(TBL_USERS, "user_id", u["user_id"], {
                                "plan_status":        "active",
                                "subscription_start": datetime.now().strftime("%Y-%m-%d"),
                                "subscription_end":   end_dt,
                            })
                            if ok:
                                pay_amount = (PAYMENT_DETAILS["yearly_price"]
                                              if plan == "yearly"
                                              else PAYMENT_DETAILS["monthly_price"])
                                log_payment(u["user_id"], u["business_name"],
                                            u["email"], plan, pay_amount, "Initial activation")
                                st.success(f"✅ {u['business_name']} activated until {end_dt}")
                                st.rerun()
                    with col3:
                        cdk = f"confirm_del_user_{u['user_id']}"
                        if not st.session_state.get(cdk, False):
                            if st.button("🗑️ Delete", key=f"del_u_{u['user_id']}"):
                                st.session_state[cdk] = True; st.rerun()
                        else:
                            st.warning("Delete this user?")
                            if st.button("✅ Confirm", key=f"yes_del_u_{u['user_id']}", type="primary"):
                                db_delete(TBL_USERS, "user_id", u["user_id"])
                                st.session_state.pop(cdk, None); st.rerun()
                            if st.button("❌ Cancel", key=f"no_del_u_{u['user_id']}"):
                                st.session_state.pop(cdk, None); st.rerun()
                    st.markdown("---")

    # ── Active ──
    with tab2:
        active_df = users_df[users_df["plan_status"] == "active"]
        if active_df.empty:
            st.info("No active users.")
        else:
            for _, u in active_df.iterrows():
                col1, col2, col3 = st.columns([3,2,2])
                with col1:
                    st.markdown(f"**{u['business_name']}** — {u['full_name']}")
                    st.caption(f"📧 {u['email']} | {u['plan_type']} | Expires: {u.get('subscription_end','?')}")
                with col2:
                    ext_days  = 365 if u.get("plan_type") == "yearly" else 30
                    ext_label = "1 year" if ext_days == 365 else "30 days"
                    if st.button(f"🔁 Renew ({ext_label})", key=f"ext_{u['user_id']}"):
                        curr_end = parse_date(u.get("subscription_end",""))
                        base     = curr_end if (curr_end and curr_end > datetime.now()) else datetime.now()
                        new_end  = (base + timedelta(days=ext_days)).strftime("%Y-%m-%d")
                        db_update(TBL_USERS, "user_id", u["user_id"], {"subscription_end": new_end})
                        pay_amount = (PAYMENT_DETAILS["yearly_price"] if ext_days == 365
                                      else PAYMENT_DETAILS["monthly_price"])
                        log_payment(u["user_id"], u["business_name"], u["email"],
                                    u.get("plan_type","monthly"), pay_amount, "Renewal")
                        st.success(f"✅ Renewed to {new_end}"); st.rerun()
                with col3:
                    if st.button("⛔ Deactivate", key=f"deact_{u['user_id']}"):
                        db_update(TBL_USERS, "user_id", u["user_id"], {"plan_status": "expired"})
                        st.rerun()
                st.markdown("---")

    # ── MRR & Growth ──
    with tab3:
        if not payments_df.empty:
            section_header("Monthly Revenue Growth")
            with st.expander("💰 Platform MRR Chart", expanded=True):
                payments_df["month"] = payments_df["payment_date"].dt.to_period("M")
                mrr = (payments_df.groupby("month")["amount"].sum()
                       .reset_index()
                       .sort_values("month"))
                mrr["month_label"] = mrr["month"].astype(str)
                fig = go.Figure(go.Bar(
                    x=mrr["month_label"], y=mrr["amount"],
                    marker_color="#F5A623",
                    hovertemplate="%{x}<br>₦%{y:,.0f}<extra></extra>",
                ))
                fig.update_layout(
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=0, r=0, t=20, b=0),
                    yaxis=dict(tickprefix="₦", gridcolor="rgba(255,255,255,0.06)"),
                    xaxis=dict(type="category", tickangle=-45),
                    height=300,
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No payment data yet.")

    # ── Churn Alerts ──
    with tab4:
        section_header("🚨 Subscriptions Expiring Soon (Next 7 Days)")
        active_df = users_df[users_df["plan_status"] == "active"].copy()
        if not active_df.empty:
            soon = []
            for _, u in active_df.iterrows():
                end = parse_date(u.get("subscription_end",""))
                if end:
                    days_left = (end - datetime.now()).days
                    if 0 <= days_left <= 7:
                        soon.append({**u.to_dict(), "days_left": days_left})
            if soon:
                for s in sorted(soon, key=lambda x: x["days_left"]):
                    css = "alert-critical" if s["days_left"] <= 2 else "alert-low"
                    st.markdown(
                        f'<div class="{css}">⚠️ <strong>{s["business_name"]}</strong> '
                        f'({s["email"]}) — expires in <strong>{s["days_left"]} day(s)</strong></div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.markdown('<div class="alert-success">✅ No subscriptions expiring in the next 7 days.</div>',
                            unsafe_allow_html=True)
        else:
            st.info("No active users.")

    # ── Password Resets ──
    with tab5:
        section_header("🔑 Pending Password Reset Requests")
        if not users_df.empty:
            reset_df = users_df[users_df.get("password_reset_requested","no") == "yes"] \
                       if "password_reset_requested" in users_df.columns else pd.DataFrame()
            if reset_df.empty:
                st.success("No pending password reset requests.")
            else:
                for _, u in reset_df.iterrows():
                    col1, col2 = st.columns([3,2])
                    with col1:
                        st.markdown(f"**{u['business_name']}** — {u['email']}")
                        st.caption(f"Requested: {u.get('reset_requested_at','?')}")
                    with col2:
                        new_pw_key = f"new_pw_{u['user_id']}"
                        new_pw = st.text_input("New temporary password",
                                               key=new_pw_key, type="password")
                        if st.button("✅ Reset", key=f"do_reset_{u['user_id']}"):
                            if new_pw and len(new_pw) >= 6:
                                import bcrypt as _bcrypt
                                hashed = _bcrypt.hashpw(new_pw.encode(), _bcrypt.gensalt()).decode()
                                db_update(TBL_USERS, "user_id", u["user_id"], {
                                    "password_hash":            hashed,
                                    "must_change_password":     "yes",
                                    "password_reset_requested": "no",
                                    "reset_requested_at":       None,
                                })
                                st.success(f"✅ Password reset for {u['email']}. They must change it on next login.")
                                st.rerun()
                            else:
                                st.error("Password must be at least 6 characters.")
                    st.markdown("---")

    # ── All Users ──
    with tab6:
        section_header("👥 All Registered Users")
        display_cols = [c for c in ["business_name","full_name","email","plan_type",
                                    "plan_status","subscription_end","created_at"]
                        if c in users_df.columns]
        st.dataframe(users_df[display_cols].rename(columns={
            "business_name":   "Business",
            "full_name":       "Name",
            "email":           "Email",
            "plan_type":       "Plan",
            "plan_status":     "Status",
            "subscription_end":"Expires",
            "created_at":      "Joined",
        }), use_container_width=True)

    # ── Deactivated ──
    with tab7:
        deact_df = users_df[users_df["plan_status"] == "expired"]
        if deact_df.empty:
            st.info("No deactivated users.")
        else:
            for _, u in deact_df.iterrows():
                col1, col2 = st.columns([3,2])
                with col1:
                    st.markdown(f"**{u['business_name']}** — {u['email']}")
                    st.caption(f"Plan: {u['plan_type']} | Expired: {u.get('subscription_end','?')}")
                with col2:
                    plan   = u.get("plan_type","monthly")
                    days   = 365 if plan == "yearly" else 30
                    end_dt = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
                    if st.button("🔁 Reactivate", key=f"react_{u['user_id']}"):
                        db_update(TBL_USERS, "user_id", u["user_id"], {
                            "plan_status":        "active",
                            "subscription_start": datetime.now().strftime("%Y-%m-%d"),
                            "subscription_end":   end_dt,
                        })
                        log_payment(u["user_id"], u["business_name"], u["email"],
                                    plan, PAYMENT_DETAILS["monthly_price"], "Reactivation")
                        st.success(f"✅ {u['business_name']} reactivated until {end_dt}")
                        st.rerun()
                st.markdown("---")
