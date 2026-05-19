"""
pages/sales.py
══════════════════════════════════════════════════════════════════════
BizTrack Suite — Sales Management App
══════════════════════════════════════════════════════════════════════

Pages contained in this module:
  • Dashboard      — KPI cards, 30-day revenue chart, top products
  • Record Sale    — multi-item cart, negotiated prices, PDF receipt
  • Sales History  — date filter, edit, void with stock reconciliation

Cross-app links:
  • Low-stock alert on the dashboard links to Inventory app
  • Dashboard net profit card pulls expenses via shared.db.compute_kpis
"""

import io
import urllib.parse
from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from shared.db import (
    get_sales_df, get_products_df, get_expenses_df,
    compute_kpis,
    db_fetch, db_insert, db_update, db_delete,
    TBL_SALES, TBL_SALE_ITEMS, TBL_PRODUCTS,
    gen_id, fmt_naira, safe_float, safe_int,
)
from shared.theme import apply_suite_css, kpi_card, section_header, page_header


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

def page_dashboard():
    apply_suite_css()
    user        = st.session_state.user
    business_id = user["business_id"]
    now         = datetime.now()
    hour        = now.hour
    greeting    = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
    first_name  = user.get("full_name", "there").split()[0]

    st.markdown(f"""
<div style="
  background:linear-gradient(135deg,#0D1117 0%,#111827 100%);
  border:1px solid #1F2D3D; border-radius:18px;
  padding:1.75rem 2rem; margin-bottom:1.5rem;
  position:relative; overflow:hidden;
">
<div style="position:absolute;top:-40px;right:-40px;width:200px;height:200px;
  border-radius:50%;background:rgba(245,166,35,0.06);"></div>
<div style="font-size:0.7rem;color:#4A6080;text-transform:uppercase;
  letter-spacing:0.12em;font-weight:600;margin-bottom:0.4rem;
  font-family:'DM Mono',monospace;">{now.strftime("%A, %d %B %Y")}</div>
<div style="font-family:'Syne',sans-serif;font-size:1.55rem;font-weight:800;
  color:#F0F4F8;letter-spacing:-0.04em;margin-bottom:0.25rem;">
  {greeting}, {first_name} 👋</div>
<div style="font-size:0.875rem;color:#4A6080;">
  Here's your business snapshot for
  <strong style="color:#8BA0B8;">{user.get("business_name","your business")}</strong>
</div>
</div>
    """, unsafe_allow_html=True)

    with st.spinner("Loading your data…"):
        sales_df    = get_sales_df(business_id)
        products_df = get_products_df(business_id)
        expenses_df = get_expenses_df(business_id)
        kpis        = compute_kpis(sales_df, expenses_df)

    # Low-stock count (cross-app bridge to Inventory)
    if not products_df.empty:
        low_count = len(products_df[products_df["stock_quantity"] <= products_df["reorder_level"]])
    else:
        low_count = 0

    growth = kpis["week_growth"]
    c1, c2 = st.columns(2)
    with c1:
        kpi_card("Today's Revenue", fmt_naira(kpis["today_revenue"]),
                 f"{kpis['today_txn']} transactions today", icon="💰")
    with c2:
        kpi_card("This Week", fmt_naira(kpis["week_revenue"]),
                 f"{'▲' if growth >= 0 else '▼'} {abs(growth):.1f}% vs last week",
                 positive=(growth >= 0), icon="📈")
    c3, c4 = st.columns(2)
    with c3:
        kpi_card("Net Profit (Month)", fmt_naira(kpis["net_profit"]),
                 f"After ₦{kpis['month_expenses']:,.0f} expenses",
                 positive=(kpis["net_profit"] >= 0), icon="📊")
    with c4:
        kpi_card("Low Stock Alerts", str(low_count),
                 "Products need restocking" if low_count > 0 else "All products stocked",
                 positive=(low_count == 0),
                 icon="⚠️" if low_count > 0 else "✅")
        if low_count > 0:
            if st.button("→ Go to Inventory", key="dash_goto_inv", use_container_width=True):
                st.session_state.current_page = "inventory"
                st.rerun()

    # ── Charts ──
    if not sales_df.empty:
        with st.expander("📈 Revenue Trend — Last 30 Days", expanded=True):
          col_left, col_right = st.columns([3, 2])

          with col_left:
            section_header("Revenue Trend — Last 30 Days")
            trend_df = sales_df.copy()
            last30   = trend_df[trend_df["sale_date"] >= (now - timedelta(days=30))]
            daily    = last30.groupby(last30["sale_date"].dt.date)["total_amount"].sum().reset_index()
            daily.columns = ["date", "total_amount"]
            all_dates = pd.date_range(end=now.date(), periods=30, freq="D").date
            daily = (
                daily.set_index("date")
                .reindex(all_dates, fill_value=0)
                .reset_index()
                .rename(columns={"index": "date"})
            )
            daily["date_str"] = pd.to_datetime(daily["date"]).dt.strftime("%d %b")
            avg_rev = daily["total_amount"].mean()
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=daily["date_str"], y=daily["total_amount"],
                marker_color=["#F5A623" if v >= avg_rev else "#6366f1" for v in daily["total_amount"]],
                hovertemplate="%{x}<br>₦%{y:,.0f}<extra></extra>",
            ))
            fig.add_hline(y=avg_rev, line_dash="dot", line_color="#00C896", line_width=1.5,
                          annotation_text=f"Avg ₦{avg_rev:,.0f}",
                          annotation_position="top right",
                          annotation_font_size=11, annotation_font_color="#00C896")
            fig.update_layout(
                margin=dict(l=0, r=0, t=20, b=0),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                yaxis=dict(tickprefix="₦", gridcolor="rgba(255,255,255,0.06)",
                           tickfont=dict(size=11), tickformat=",.0f"),
                xaxis=dict(type="category", tickangle=-45, tickfont=dict(size=10),
                           gridcolor="rgba(0,0,0,0)", nticks=10),
                height=240, bargap=0.25, showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True)
            st.caption("■ Gold = above average  ■ Purple = below average")

          with col_right:
            section_header("Sales by Payment Method")
            pm_df = sales_df.groupby("payment_method")["total_amount"].sum().reset_index()
            if not pm_df.empty:
                fig2 = px.pie(pm_df, values="total_amount", names="payment_method",
                              color_discrete_sequence=["#6366f1","#10b981","#f59e0b","#ef4444"],
                              hole=0.55)
                fig2.update_layout(
                    margin=dict(l=0, r=0, t=10, b=0),
                    paper_bgcolor="rgba(0,0,0,0)", height=280,
                    legend=dict(orientation="h", y=-0.1),
                )
                st.plotly_chart(fig2, use_container_width=True)

        with st.expander("🏆 Top Selling Products", expanded=True):
            section_header("Top Selling Products (by Revenue)")
            top_df = (
                sales_df.groupby("product_name")["total_amount"]
                .sum().reset_index()
                .sort_values("total_amount", ascending=True)
                .tail(8)
            )
            if not top_df.empty:
                fig3 = px.bar(top_df, x="total_amount", y="product_name", orientation="h",
                              labels={"total_amount": "Revenue (₦)", "product_name": ""},
                              color_discrete_sequence=["#6366f1"])
                fig3.update_layout(
                    margin=dict(l=0, r=0, t=10, b=0),
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    xaxis=dict(tickprefix="₦", gridcolor="#1F2D3D"), height=300,
                )
                st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("📭 No sales yet. Record your first sale to see analytics here.")

    # ── Low-Stock Alerts ──
    if not products_df.empty:
        low_stock = products_df[products_df["stock_quantity"] <= products_df["reorder_level"]]
        if not low_stock.empty:
            section_header("⚠️ Low Stock Alerts")
            for _, row in low_stock.iterrows():
                qty = safe_int(row["stock_quantity"])
                css = "alert-critical" if qty <= 0 else "alert-low"
                st.markdown(
                    f'<div class="{css}">🔔 <strong>{row["product_name"]}</strong> — '
                    f'{qty} units left (reorder level: {safe_int(row["reorder_level"])})</div>',
                    unsafe_allow_html=True,
                )


# ══════════════════════════════════════════════════════════════════════════════
# RECORD SALE
# ══════════════════════════════════════════════════════════════════════════════

def page_record_sale():
    apply_suite_css()
    user        = st.session_state.user
    business_id = user["business_id"]

    page_header("🛒 Record a Sale", "Build a cart, apply discounts, print receipt")

    products_df = get_products_df(business_id)
    if products_df.empty:
        st.warning("No products found. Please add products in the Inventory app first.")
        if st.button("→ Go to Inventory"):
            st.session_state.current_page = "inventory"
            st.rerun()
        return

    if "cart"      not in st.session_state: st.session_state.cart      = []
    if "sale_done" not in st.session_state: st.session_state.sale_done = None

    col1, col2 = st.columns([3, 2], gap="large")

    # ── LEFT: Build cart ──
    with col1:
        section_header("🛍️ Build Cart")
        in_stock = products_df[products_df["stock_quantity"] > 0]
        if in_stock.empty:
            st.warning("All products are out of stock.")
        else:
            prod_names      = in_stock["product_name"].tolist()
            sel_name        = st.selectbox("Product", prod_names, key="cart_prod")
            sel_prod_row    = in_stock[in_stock["product_name"] == sel_name].iloc[0]
            original_price  = safe_float(sel_prod_row["selling_price"])
            avail_qty       = int(sel_prod_row["stock_quantity"])
            already_in_cart = sum(
                i["quantity"] for i in st.session_state.cart
                if i["product_id"] == sel_prod_row["product_id"]
            )
            remaining = avail_qty - already_in_cart
            st.caption(
                f"📦 Listed price: **{fmt_naira(original_price)}** "
                f"&nbsp;|&nbsp; 🏷️ Available: **{remaining} units**"
            )

            with st.form("add_to_cart", clear_on_submit=True):
                ac1, ac2     = st.columns(2)
                sel_qty      = ac1.number_input("Quantity", min_value=1,
                                                max_value=max(1, remaining), value=1, step=1)
                sel_price    = ac2.number_input("Selling Price (₦)", min_value=0.0,
                                                value=float(original_price), step=500.0,
                                                help="Change to override listed price")
                if sel_price > original_price:
                    st.warning(f"⚠️ Above listed price ({fmt_naira(original_price)}). Confirm?")
                add_btn = st.form_submit_button("➕ Add to Cart", type="primary",
                                                use_container_width=True)

            if add_btn:
                prod_row      = in_stock[in_stock["product_name"] == sel_name].iloc[0]
                unit_price    = safe_float(prod_row["selling_price"])
                cost_price    = safe_float(prod_row["cost_price"])
                negotiated    = float(sel_price)
                disc_amt      = max(0, round((unit_price - negotiated) * sel_qty, 2))
                line_total    = round(negotiated * sel_qty, 2)
                cost_total    = round(cost_price * sel_qty, 2)

                if sel_qty > remaining:
                    st.error(f"Only {remaining} units available for {sel_name}.")
                else:
                    merged = False
                    for item in st.session_state.cart:
                        if (item["product_id"] == prod_row["product_id"] and
                                item["negotiated_price"] == negotiated):
                            item["quantity"]    += int(sel_qty)
                            item["disc_amt"]     = max(0, round((unit_price - negotiated) * item["quantity"], 2))
                            item["line_total"]   = round(negotiated * item["quantity"], 2)
                            item["cost_total"]   = round(cost_price  * item["quantity"], 2)
                            item["gross_profit"] = round(item["line_total"] - item["cost_total"], 2)
                            item["discount_amt"] = item["disc_amt"]
                            merged = True
                            break
                    if not merged:
                        st.session_state.cart.append({
                            "product_id":       prod_row["product_id"],
                            "product_name":     sel_name,
                            "quantity":         int(sel_qty),
                            "unit_price":       unit_price,
                            "negotiated_price": negotiated,
                            "cost_price":       cost_price,
                            "discount_pct":     0.0,
                            "discount_amt":     disc_amt,
                            "line_total":       line_total,
                            "cost_total":       cost_total,
                            "gross_profit":     round(line_total - cost_total, 2),
                        })
                    st.session_state.sale_done = None
                    st.rerun()

        # ── Cart display ──
        if not st.session_state.cart:
            st.info("Cart is empty. Add products above.")
        else:
            st.markdown("---")
            section_header("🧾 Cart Items")
            grand_total    = 0
            total_discount = 0
            total_cost     = 0
            total_profit   = 0

            for idx, item in enumerate(st.session_state.cart):
                ic1, ic2 = st.columns([4, 1])
                with ic1:
                    neg = item.get("negotiated_price", item["unit_price"])
                    if neg < item["unit_price"]:
                        price_str = (f"~~{fmt_naira(item['unit_price'])}~~ → "
                                     f"**{fmt_naira(neg)}** (-{fmt_naira(item['discount_amt'])})")
                    else:
                        price_str = fmt_naira(item["unit_price"])
                    st.markdown(
                        f"**{item['product_name']}** × {item['quantity']} "
                        f"@ {price_str}  \n**Line total: {fmt_naira(item['line_total'])}**"
                    )
                with ic2:
                    if st.button("🗑️", key=f"rm_{idx}", help="Remove"):
                        st.session_state.cart.pop(idx)
                        st.rerun()
                grand_total    += item["line_total"]
                total_discount += item["discount_amt"]
                total_cost     += item["cost_total"]
                total_profit   += item["gross_profit"]
                st.markdown("---")

            st.markdown(f"""
<div class="kpi-card">
  <div class="kpi-label">Cart Summary</div>
  <div style="display:flex;gap:2rem;flex-wrap:wrap;margin-top:0.75rem;">
    <div><div class="kpi-label">Items</div>
         <div style="font-weight:700;font-size:1.1rem;color:#f1f5f9">{len(st.session_state.cart)}</div></div>
    <div><div class="kpi-label">Discount Given</div>
         <div style="font-weight:700;font-size:1.1rem;color:#ef4444">{fmt_naira(total_discount)}</div></div>
    <div><div class="kpi-label">Grand Total</div>
         <div style="font-weight:700;font-size:1.4rem;color:#00C896">{fmt_naira(grand_total)}</div></div>
    <div><div class="kpi-label">Gross Profit</div>
         <div style="font-weight:700;font-size:1.1rem;color:#6366f1">{fmt_naira(total_profit)}</div></div>
  </div>
</div>
            """, unsafe_allow_html=True)

    # ── RIGHT: Checkout + receipt ──
    with col2:
        section_header("💳 Checkout")

        if st.session_state.cart:
            with st.form("checkout_form"):
                customer_name  = st.text_input("Customer Name (optional)", placeholder="e.g. Emeka Obi")
                payment_method = st.selectbox("Payment Method",
                                              ["Cash","Bank Transfer","POS","Mobile Money"])
                sale_note      = st.text_input("Note (optional)", placeholder="e.g. Bulk order")
                total_display  = fmt_naira(sum(i["line_total"] for i in st.session_state.cart))
                confirm_sale   = st.form_submit_button(
                    f"✅ Record Sale — {total_display}",
                    type="primary", use_container_width=True,
                )

            if confirm_sale:
                sale_id    = gen_id("SL")
                sale_time  = datetime.now().isoformat()
                cart       = st.session_state.cart
                grand_total    = sum(i["line_total"]   for i in cart)
                total_discount = sum(i["discount_amt"] for i in cart)
                total_cost     = sum(i["cost_total"]   for i in cart)
                total_profit   = sum(i["gross_profit"] for i in cart)

                sale_ok = db_insert(TBL_SALES, {
                    "sale_id":        sale_id,
                    "business_id":    business_id,
                    "product_id":     cart[0]["product_id"],
                    "product_name":   ", ".join(i["product_name"] for i in cart),
                    "quantity":       sum(i["quantity"] for i in cart),
                    "unit_price":     cart[0]["unit_price"],
                    "total_amount":   grand_total,
                    "cost_total":     total_cost,
                    "gross_profit":   total_profit,
                    "payment_method": payment_method,
                    "sale_date":      sale_time,
                    "customer_name":  customer_name.strip(),
                    "discount_total": total_discount,
                    "item_count":     len(cart),
                })

                if sale_ok:
                    for item in cart:
                        db_insert(TBL_SALE_ITEMS, {
                            "item_id":      gen_id("ITM"),
                            "sale_id":      sale_id,
                            "business_id":  business_id,
                            "product_id":   item["product_id"],
                            "product_name": item["product_name"],
                            "quantity":     item["quantity"],
                            "unit_price":   item["unit_price"],
                            "discount_pct": item["discount_pct"],
                            "discount_amt": item["discount_amt"],
                            "line_total":   item["line_total"],
                            "cost_total":   item["cost_total"],
                            "gross_profit": item["gross_profit"],
                        })
                    # Deduct stock
                    live_products = get_products_df(business_id)
                    for item in cart:
                        if not live_products.empty:
                            pr = live_products[live_products["product_id"] == item["product_id"]]
                            if not pr.empty:
                                new_stock = int(pr.iloc[0]["stock_quantity"]) - item["quantity"]
                                db_update(TBL_PRODUCTS, "product_id", item["product_id"],
                                          {"stock_quantity": max(0, new_stock)})

                    st.session_state.sale_done = {
                        "sale_id":       sale_id,
                        "sale_time":     sale_time,
                        "customer_name": customer_name.strip(),
                        "payment":       payment_method,
                        "note":          sale_note.strip(),
                        "items":         cart,
                        "grand_total":   grand_total,
                        "discount":      total_discount,
                        "profit":        total_profit,
                        "business_name": user.get("business_name", ""),
                    }
                    st.session_state.cart = []
                    st.rerun()
                else:
                    st.error("Failed to record sale. Please try again.")

            if st.button("🗑️ Clear Cart", use_container_width=True):
                st.session_state.cart      = []
                st.session_state.sale_done = None
                st.rerun()
        else:
            st.info("Add items to the cart to checkout.")

        # ── Receipt ──
        if st.session_state.get("sale_done"):
            rd = st.session_state.sale_done
            st.markdown("---")
            section_header("🧾 Receipt")

            lines = [f"{'='*38}", f"  {rd['business_name'].upper()}",
                     f"  {datetime.fromisoformat(rd['sale_time']).strftime('%d %b %Y  %H:%M')}",
                     f"  Sale ID: {rd['sale_id']}"]
            if rd["customer_name"]:
                lines.append(f"  Customer: {rd['customer_name']}")
            lines.append(f"{'='*38}")
            for item in rd["items"]:
                neg = item.get("negotiated_price", item["unit_price"])
                lines.append(f"  {item['product_name'][:20]:<20}")
                lines.append(f"  {item['quantity']} x {fmt_naira(neg)} = {fmt_naira(item['line_total'])}")
            lines += [f"{'-'*38}", f"  TOTAL:  {fmt_naira(rd['grand_total'])}",
                      f"  Payment: {rd['payment']}"]
            if rd["note"]:
                lines.append(f"  Note: {rd['note']}")
            lines += [f"{'='*38}", "  Thank you for your purchase!", f"{'='*38}"]
            st.code("\n".join(lines), language=None)

            # PDF Receipt
            try:
                from reportlab.lib.pagesizes import A6
                from reportlab.lib import colors
                from reportlab.lib.units import mm
                from reportlab.platypus import (SimpleDocTemplate, Paragraph,
                                                Spacer, HRFlowable, Table, TableStyle)
                from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

                buf  = io.BytesIO()
                doc  = SimpleDocTemplate(buf, pagesize=A6,
                                         leftMargin=10*mm, rightMargin=10*mm,
                                         topMargin=8*mm,  bottomMargin=8*mm)
                styl = getSampleStyleSheet()
                bc   = ParagraphStyle("bc", parent=styl["Normal"], fontName="Helvetica-Bold",
                                      fontSize=11, alignment=TA_CENTER, spaceAfter=2)
                nc   = ParagraphStyle("nc", parent=styl["Normal"], fontSize=8,
                                      alignment=TA_CENTER, spaceAfter=1)

                story = [
                    Paragraph(rd["business_name"].upper(), bc),
                    Paragraph(datetime.fromisoformat(rd["sale_time"]).strftime("%d %b %Y  %H:%M"), nc),
                    Paragraph(f"Sale ID: {rd['sale_id']}", nc),
                ]
                if rd["customer_name"]:
                    story.append(Paragraph(f"Customer: {rd['customer_name']}", nc))
                story.append(HRFlowable(width="100%", thickness=1, color=colors.black))
                story.append(Spacer(1, 3*mm))

                tdata = [["Item","Qty","Price","Total"]]
                for item in rd["items"]:
                    neg = item.get("negotiated_price", item["unit_price"])
                    tdata.append([item["product_name"][:18], str(item["quantity"]),
                                  f"₦{neg:,.0f}", f"₦{item['line_total']:,.0f}"])
                t = Table(tdata, colWidths=[45*mm, 10*mm, 22*mm, 22*mm])
                t.setStyle(TableStyle([
                    ("FONTNAME",  (0,0), (-1,0),  "Helvetica-Bold"),
                    ("FONTSIZE",  (0,0), (-1,-1),  8),
                    ("ALIGN",     (1,0), (-1,-1),  "RIGHT"),
                    ("LINEBELOW", (0,0), (-1,0),   0.5, colors.black),
                    ("ROWBACKGROUNDS", (0,1), (-1,-1),
                     [colors.white, colors.Color(0.95,0.95,0.95)]),
                    ("BOTTOMPADDING", (0,0), (-1,-1), 3),
                ]))
                story += [t, Spacer(1,3*mm),
                           HRFlowable(width="100%", thickness=0.5, color=colors.grey),
                           Paragraph(f"<b>TOTAL: ₦{rd['grand_total']:,.0f}</b>", bc),
                           Paragraph(f"Payment: {rd['payment']}", nc)]
                if rd["note"]:
                    story.append(Paragraph(f"Note: {rd['note']}", nc))
                story += [Spacer(1,4*mm),
                           HRFlowable(width="100%", thickness=1, color=colors.black),
                           Paragraph("Thank you for your purchase!", nc)]
                doc.build(story)
                pdf_bytes = buf.getvalue()
                fname = (f"receipt_{rd['sale_id']}_"
                         f"{datetime.fromisoformat(rd['sale_time']).strftime('%Y%m%d_%H%M')}.pdf")
                st.download_button("📄 Download PDF Receipt", data=pdf_bytes,
                                   file_name=fname, mime="application/pdf",
                                   use_container_width=True, type="primary")

                item_lines = ", ".join(
                    f"{i['product_name']} x{i['quantity']}" for i in rd["items"]
                )
                wa_text = (
                    f"Receipt from {rd['business_name']}\n"
                    f"Date: {datetime.fromisoformat(rd['sale_time']).strftime('%d %b %Y %H:%M')}\n"
                    f"Items: {item_lines}\n"
                    f"Total: \u20a6{rd['grand_total']:,.0f}\nPayment: {rd['payment']}\nThank you!"
                )
                wa_url = f"https://wa.me/?text={urllib.parse.quote(wa_text)}"
                st.markdown(
                    f"""<a href="{wa_url}" target="_blank"
                        style="display:block;text-align:center;background:#25D366;
                               color:white;padding:0.6rem;border-radius:8px;
                               font-weight:600;text-decoration:none;margin-top:0.5rem;">
                        💬 Share via WhatsApp</a>""",
                    unsafe_allow_html=True,
                )
            except ImportError:
                st.warning("Install reportlab for PDF receipts: pip install reportlab")

    # ── Today's Sales ──
    st.markdown("---")
    section_header("Today's Sales")
    today       = datetime.now().date()
    sales_df    = get_sales_df(business_id)
    today_sales = (sales_df[sales_df["sale_date"].dt.date == today]
                   if not sales_df.empty else pd.DataFrame())
    kpi_card("Today's Revenue",
             fmt_naira(today_sales["total_amount"].sum() if not today_sales.empty else 0),
             f"{len(today_sales)} transactions today", icon="💰")
    if not today_sales.empty:
        st.markdown("**Recent transactions:**")
        for _, r in today_sales.sort_values("sale_date", ascending=False).head(5).iterrows():
            st.markdown(f"• **{r['product_name']}** = {fmt_naira(r['total_amount'])} _{r['payment_method']}_")


# ══════════════════════════════════════════════════════════════════════════════
# SALES HISTORY
# ══════════════════════════════════════════════════════════════════════════════

def page_sales_history():
    apply_suite_css()
    user        = st.session_state.user
    business_id = user["business_id"]

    page_header("📋 Sales History", "View, edit or void past transactions")

    if st.session_state.get("sale_feedback"):
        msg = st.session_state.pop("sale_feedback")
        (st.success if msg.startswith("✅") else st.error)(msg)

    sales_df = get_sales_df(business_id)
    if sales_df.empty:
        st.info("📭 No sales recorded yet.")
        return

    # ── Filters ──
    col1, col2, col3 = st.columns(3)
    start_date = col1.date_input("From", value=(datetime.now() - timedelta(days=30)).date())
    end_date   = col2.date_input("To",   value=datetime.now().date())
    search_q   = col3.text_input("🔍 Search", placeholder="Product or customer name…")

    filtered = sales_df[
        (sales_df["sale_date"].dt.date >= start_date) &
        (sales_df["sale_date"].dt.date <= end_date)
    ]
    if search_q:
        filtered = filtered[
            filtered["product_name"].str.contains(search_q, case=False, na=False) |
            filtered["customer_name"].str.contains(search_q, case=False, na=False)
        ]
    filtered = filtered.sort_values("sale_date", ascending=False)

    # ── Period KPIs ──
    c1, c2, c3, c4 = st.columns(4)
    with c1: kpi_card("Total Revenue",  fmt_naira(filtered["total_amount"].sum()), f"{len(filtered)} transactions", icon="💰")
    with c2: kpi_card("Total Profit",   fmt_naira(filtered["gross_profit"].sum()),  "Gross profit",                 icon="📈")
    with c3: kpi_card("Avg Sale Value", fmt_naira(filtered["total_amount"].mean() if not filtered.empty else 0), "Per transaction", icon="📊")
    with c4:
        disc = filtered["discount_total"].sum() if "discount_total" in filtered.columns else 0
        kpi_card("Total Discounts", fmt_naira(disc), "Given in period", positive=(disc == 0), icon="🏷️")

    st.markdown("---")

    # ── Pagination ──
    PAGE_SIZE   = 20
    total_pages = max(1, -(-len(filtered) // PAGE_SIZE))
    if "sales_hist_page" not in st.session_state:
        st.session_state.sales_hist_page = 1
    pg       = st.session_state.sales_hist_page
    page_df  = filtered.iloc[(pg-1)*PAGE_SIZE: pg*PAGE_SIZE]
    st.caption(f"Showing {len(page_df)} of {len(filtered)} records  •  Page {pg} of {total_pages}")

    for _, r in page_df.iterrows():
        sale_id = r["sale_id"]
        with st.expander(
            f"**{r['product_name'][:40]}** | {fmt_naira(r['total_amount'])} | "
            f"{r['payment_method']} | {r['sale_date'].strftime('%d %b %Y %H:%M') if pd.notna(r['sale_date']) else ''}",
            expanded=False,
        ):
            dc1, dc2 = st.columns(2)
            dc1.markdown(f"**Sale ID:** `{sale_id}`")
            dc1.markdown(f"**Customer:** {r.get('customer_name','—') or '—'}")
            dc2.markdown(f"**Gross Profit:** {fmt_naira(r['gross_profit'])}")
            dc2.markdown(f"**Items:** {int(r.get('item_count', 1))}")

            with st.form(f"edit_sale_{sale_id}"):
                ef1, ef2 = st.columns(2)
                new_pm   = ef1.selectbox("Payment Method",
                                         ["Cash","Bank Transfer","POS","Mobile Money"],
                                         index=["Cash","Bank Transfer","POS","Mobile Money"].index(r["payment_method"])
                                         if r["payment_method"] in ["Cash","Bank Transfer","POS","Mobile Money"] else 0)
                new_amt  = ef2.number_input("Total Amount (₦)", value=safe_float(r["total_amount"]),
                                             min_value=0.0, step=100.0)
                save = st.form_submit_button("💾 Save Changes", type="primary")

            if save:
                ok = db_update(TBL_SALES, "sale_id", sale_id,
                               {"payment_method": new_pm, "total_amount": new_amt})
                st.session_state.sale_feedback = (
                    "✅ Sale updated." if ok else "❌ Update failed."
                )
                st.rerun()

            void_key = f"void_{sale_id}"
            if not st.session_state.get(void_key, False):
                if st.button("🗑️ Void Sale", key=f"del_sale_{sale_id}",
                             help="Void this sale and restore stock"):
                    st.session_state[void_key] = True
                    st.rerun()
            else:
                st.warning("⚠️ Void this sale? Stock will be restored.")
                vc1, vc2 = st.columns(2)
                if vc1.button("✅ Yes, void", key=f"yes_void_{sale_id}", type="primary"):
                    # Restore stock for each line item
                    items_df = db_fetch(TBL_SALE_ITEMS,
                                        {"sale_id": sale_id, "business_id": business_id})
                    live     = get_products_df(business_id)
                    if not items_df.empty and not live.empty:
                        for _, item in items_df.iterrows():
                            pr = live[live["product_id"] == item["product_id"]]
                            if not pr.empty:
                                restored = int(pr.iloc[0]["stock_quantity"]) + int(item["quantity"])
                                db_update(TBL_PRODUCTS, "product_id", item["product_id"],
                                          {"stock_quantity": restored})
                    ok = db_delete(TBL_SALES, "sale_id", sale_id)
                    if not items_df.empty:
                        db_delete(TBL_SALE_ITEMS, "sale_id", sale_id)
                    st.session_state.pop(void_key, None)
                    st.session_state.sale_feedback = (
                        "✅ Sale voided and stock restored." if ok else "❌ Failed to void."
                    )
                    st.rerun()
                if vc2.button("❌ Cancel", key=f"no_void_{sale_id}"):
                    st.session_state.pop(void_key, None)
                    st.rerun()

    if total_pages > 1:
        st.markdown("---")
        pc1, pc2, pc3 = st.columns([1, 3, 1])
        if pc1.button("◀ Prev", disabled=(pg <= 1), key="sh_prev"):
            st.session_state.sales_hist_page = max(1, pg-1); st.rerun()
        pc2.markdown(f"<div style='text-align:center;padding-top:0.5rem;color:#8BA0B8;'>Page {pg} of {total_pages}</div>",
                     unsafe_allow_html=True)
        if pc3.button("Next ▶", disabled=(pg >= total_pages), key="sh_next"):
            st.session_state.sales_hist_page = min(total_pages, pg+1); st.rerun()
