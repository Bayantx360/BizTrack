"""
pages/inventory.py
══════════════════════════════════════════════════════════════════════
BizTrack Suite — Inventory Management App
══════════════════════════════════════════════════════════════════════

Pages contained in this module:
  • Products        — catalogue, search, edit, delete with pagination
  • Add Product     — new product form with live margin preview
  • Restock         — add units to existing product + audit log
  • Restock History — searchable restock log table

Cross-app links:
  • Stockout projections pull live sales velocity via shared.db.compute_insights
  • Low-stock summary banner links back to Sales dashboard
"""

from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from shared.db import (
    get_products_df, get_sales_df, get_expenses_df,
    compute_insights,
    db_fetch, db_insert, db_update, db_delete,
    TBL_PRODUCTS, TBL_RESTOCK,
    gen_id, fmt_naira, safe_float, safe_int,
)
from shared.theme import (
    apply_suite_css, kpi_card, section_header, page_header, stock_pill,
)


def page_products():
    """Products catalogue — view, edit, delete, restock, history."""
    apply_suite_css()
    user        = st.session_state.user
    business_id = user["business_id"]

    page_header("📦 Inventory Management", "Add, edit and manage your products")

    tab1, tab2, tab3, tab4 = st.tabs(
        ["📋 All Products", "➕ Add Product", "🔄 Restock", "📜 Restock History"]
    )

    # ══════════════════════════════════════
    # Tab 1 — All Products
    # ══════════════════════════════════════
    with tab1:
        products_df = get_products_df(business_id)
        if products_df.empty:
            st.info("No products yet. Add your first product in the 'Add Product' tab.")
        else:
            # Summary KPIs
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                kpi_card("Total Products", str(len(products_df)), "In your catalog", icon="📦")
            with c2:
                total_sell_val = (products_df["stock_quantity"] * products_df["selling_price"]).sum()
                kpi_card("Inventory Value", fmt_naira(total_sell_val), "At selling price", icon="🏷️")
            with c3:
                total_cost_val = (products_df["stock_quantity"] * products_df["cost_price"]).sum()
                kpi_card("Inventory Cost", fmt_naira(total_cost_val), "At cost price", icon="🏦")
            with c4:
                low_count = len(products_df[products_df["stock_quantity"] <= products_df["reorder_level"]])
                kpi_card("Low Stock", str(low_count), "Need restocking",
                         positive=(low_count == 0), icon="⚠️" if low_count > 0 else "✅")

            st.markdown("---")

            # Search + category filter
            search_q     = st.text_input("🔍 Search products", key="prod_search",
                                         placeholder="Type product name…")
            cats         = ["All"] + sorted(products_df["category"].dropna().unique().tolist())
            selected_cat = st.selectbox("Filter by category", cats)

            disp = products_df if selected_cat == "All" else products_df[products_df["category"] == selected_cat]
            if search_q:
                disp = disp[disp["product_name"].str.contains(search_q, case=False, na=False)]

            # Pagination
            PAGE_SIZE   = 15
            total_pages = max(1, -(-len(disp) // PAGE_SIZE))
            if "prod_page" not in st.session_state:
                st.session_state.prod_page = 1
            if (st.session_state.get("_last_prod_search") != search_q or
                    st.session_state.get("_last_prod_cat") != selected_cat):
                st.session_state.prod_page = 1
            st.session_state["_last_prod_search"] = search_q
            st.session_state["_last_prod_cat"]    = selected_cat

            pg       = st.session_state.prod_page
            disp_page = disp.iloc[(pg-1)*PAGE_SIZE: pg*PAGE_SIZE]
            st.caption(f"Showing {len(disp_page)} of {len(disp)} products  •  Page {pg} of {total_pages}")

            for _, row in disp_page.iterrows():
                with st.expander(
                    f"**{row['product_name']}** | {row['category']} | "
                    f"Stock: {int(row['stock_quantity'])} | {fmt_naira(row['selling_price'])}",
                    expanded=False,
                ):
                    ec1, ec2, ec3 = st.columns(3)
                    with ec1:
                        st.markdown(f"**Cost Price:** {fmt_naira(row['cost_price'])}")
                        st.markdown(f"**Selling Price (per {row.get('base_unit','unit')}):** {fmt_naira(row['selling_price'])}")
                        upp = safe_int(row.get('units_per_pack', 1))
                        if upp > 1:
                            sub_price = safe_float(row.get('selling_price_sub', 0))
                            st.markdown(f"**Selling Price (per {row.get('sub_unit','unit')}):** {fmt_naira(sub_price)}")
                        margin = safe_float(row["selling_price"]) - safe_float(row["cost_price"])
                        st.markdown(f"**Margin/unit:** {fmt_naira(margin)}")
                    with ec2:
                        upp = safe_int(row.get('units_per_pack', 1))
                        base = row.get('base_unit','unit')
                        sub  = row.get('sub_unit','unit')
                        stock_display = (
                            f"{int(row['stock_quantity'])} {base}s"
                            if upp <= 1 else
                            f"{int(row['stock_quantity'])} {base}s ({int(row['stock_quantity']) * upp} {sub}s)"
                        )
                        st.markdown(f"**Stock:** {stock_display}")
                        st.markdown(f"**Pack size:** {upp} {sub}s per {base}" if upp > 1 else f"**Unit:** {base}")
                        st.markdown(f"**Reorder Level:** {int(row['reorder_level'])} {base}s")
                        st.markdown(f"**Category:** {row['category']}")
                    with ec3:
                        st.markdown(stock_pill(row["stock_quantity"], row["reorder_level"]),
                                    unsafe_allow_html=True)

                    with st.form(f"edit_{row['product_id']}"):
                        st.markdown("**Edit Product**")
                        f1, f2      = st.columns(2)
                        new_name    = f1.text_input("Product Name",    value=row["product_name"])
                        new_cat     = f2.text_input("Category",        value=row["category"])
                        new_cost    = f1.number_input("Cost Price",    value=safe_float(row["cost_price"]),
                                                      min_value=0.0, step=50.0)
                        new_sell    = f2.number_input(
                            f"Selling Price (per {row.get('base_unit','unit')})",
                            value=safe_float(row["selling_price"]), min_value=0.0, step=50.0,
                        )
                        new_reorder = f1.number_input("Reorder Level", value=safe_int(row["reorder_level"]),
                                                      min_value=0, step=1)
                        new_upp     = f2.number_input(
                            "Units per Pack (1 = no splitting)",
                            value=safe_int(row.get("units_per_pack", 1)), min_value=1, step=1,
                        )
                        new_base    = f1.text_input("Base Unit",  value=row.get("base_unit","unit"),
                                                    help="e.g. carton, bag, crate, bottle")
                        new_sub     = f2.text_input("Sub Unit",   value=row.get("sub_unit","unit"),
                                                    help="e.g. piece, kg, bottle, sachet")
                        new_sub_price = f1.number_input(
                            f"Selling Price per sub unit",
                            value=safe_float(row.get("selling_price_sub", 0)),
                            min_value=0.0, step=50.0,
                            help="Leave 0 if you don't sell in sub units",
                        ) if new_upp > 1 else 0.0
                        save = st.form_submit_button("💾 Save Changes", type="primary")

                    if save:
                        ok = db_update(TBL_PRODUCTS, "product_id", row["product_id"], {
                            "product_name":      new_name,
                            "category":          new_cat,
                            "cost_price":        new_cost,
                            "selling_price":     new_sell,
                            "reorder_level":     new_reorder,
                            "units_per_pack":    new_upp,
                            "base_unit":         new_base.strip() or "unit",
                            "sub_unit":          new_sub.strip()  or "unit",
                            "selling_price_sub": new_sub_price,
                        })
                        (st.success("Product updated!") if ok else st.error("Update failed."))
                        st.rerun()

                    confirm_key = f"confirm_del_{row['product_id']}"
                    if not st.session_state.get(confirm_key, False):
                        if st.button(f"🗑️ Delete {row['product_name']}", key=f"del_{row['product_id']}"):
                            st.session_state[confirm_key] = True
                            st.rerun()
                    else:
                        st.warning(f"⚠️ Delete **{row['product_name']}**? This cannot be undone.")
                        cy, cn = st.columns(2)
                        if cy.button("✅ Yes, delete", key=f"yes_del_{row['product_id']}", type="primary"):
                            ok = db_delete(TBL_PRODUCTS, "product_id", row["product_id"])
                            st.session_state.pop(confirm_key, None)
                            st.session_state["prod_del_msg"] = (
                                f"✅ {row['product_name']} deleted." if ok
                                else "❌ Failed to delete product."
                            )
                            st.rerun()
                        if cn.button("❌ Cancel", key=f"no_del_{row['product_id']}"):
                            st.session_state.pop(confirm_key, None)
                            st.rerun()

            if "prod_del_msg" in st.session_state:
                msg = st.session_state.pop("prod_del_msg")
                (st.success if msg.startswith("✅") else st.error)(msg)

            if total_pages > 1:
                st.markdown("---")
                pc1, pc2, pc3 = st.columns([1, 3, 1])
                if pc1.button("◀ Prev", disabled=(pg <= 1), key="prod_prev"):
                    st.session_state.prod_page = max(1, pg-1); st.rerun()
                pc2.markdown(f"<div style='text-align:center;padding-top:0.5rem;color:#8BA0B8;'>Page {pg} of {total_pages}</div>",
                             unsafe_allow_html=True)
                if pc3.button("Next ▶", disabled=(pg >= total_pages), key="prod_next"):
                    st.session_state.prod_page = min(total_pages, pg+1); st.rerun()

        # ── Stockout Projection (bottom of tab 1) ──
        st.markdown("---")
        section_header("📅 Stockout Projections")
        sales_df    = get_sales_df(business_id)
        expenses_df = get_expenses_df(business_id)
        insights    = compute_insights(sales_df, products_df if not products_df.empty
                                       else get_products_df(business_id), expenses_df)

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

    # ══════════════════════════════════════
    # Tab 2 — Add Product
    # ══════════════════════════════════════
    with tab2:
        with st.form("add_product_form", clear_on_submit=True):
            st.markdown("#### New Product Details")
            f1, f2      = st.columns(2)
            prod_name   = f1.text_input("Product Name *",   placeholder="e.g. Indomie Chicken 70g")
            category    = f2.text_input("Category *",       placeholder="e.g. Noodles, Beverages")
            cost_price  = f1.number_input("Cost Price (₦) *",  min_value=0.0, step=50.0,
                                          help="What you paid per unit/pack")
            stock_qty   = f2.number_input("Opening Stock *",   min_value=0, step=1,
                                          help="Enter in base units e.g. number of cartons")
            reorder_lvl = f1.number_input("Reorder Level *",   min_value=0, step=1)

            st.markdown("##### Unit & Pricing Setup")
            st.caption("Leave Units per Pack as 1 if this product is not sold in smaller units.")
            u1, u2, u3  = st.columns(3)
            base_unit   = u1.text_input("Base Unit *",  value="unit",
                                        help="How stock is counted e.g. carton, bag, crate")
            sub_unit    = u2.text_input("Sub Unit",     value="unit",
                                        help="Smallest sellable unit e.g. piece, bottle, kg")
            units_per_pack = u3.number_input("Units per Pack", min_value=1, step=1, value=1,
                                             help="How many sub units in one base unit")

            p1, p2      = st.columns(2)
            sell_price  = p1.number_input(
                f"Selling Price per base unit (₦) *",
                min_value=0.0, step=50.0,
                help="Price when selling a full carton/bag/crate"
            )
            sell_price_sub = p2.number_input(
                f"Selling Price per sub unit (₦)",
                min_value=0.0, step=50.0,
                help="Price per piece/bottle/kg. Leave 0 if not applicable",
            ) if units_per_pack > 1 else 0.0

            if cost_price > 0 and sell_price > 0:
                margin     = sell_price - cost_price
                margin_pct = (margin / sell_price) * 100
                st.info(
                    f"💡 Margin per {base_unit}: **{fmt_naira(margin)}** ({margin_pct:.1f}%)"
                    + (f"  |  Per {sub_unit}: **{fmt_naira(sell_price_sub - cost_price/units_per_pack):.0f}**"
                       if units_per_pack > 1 and sell_price_sub > 0 else "")
                )

            submitted = st.form_submit_button("➕ Add Product", use_container_width=True, type="primary")

        if submitted:
            if not all([prod_name, category]) or sell_price <= 0:
                st.error("Please fill all required fields and ensure selling price > 0.")
            else:
                ok = db_insert(TBL_PRODUCTS, {
                    "product_id":        gen_id("PRD"),
                    "business_id":       business_id,
                    "product_name":      prod_name.strip(),
                    "category":          category.strip(),
                    "cost_price":        cost_price,
                    "selling_price":     sell_price,
                    "selling_price_sub": sell_price_sub,
                    "stock_quantity":    stock_qty,
                    "reorder_level":     reorder_lvl,
                    "base_unit":         base_unit.strip() or "unit",
                    "sub_unit":          sub_unit.strip()  or "unit",
                    "units_per_pack":    units_per_pack,
                    "created_at":        datetime.now().isoformat(),
                })
                if ok:
                    st.success(f"✅ '{prod_name}' added to your inventory!")
                    st.rerun()
                else:
                    st.error("Failed to add product. Please try again.")

    # ══════════════════════════════════════
    # Tab 3 — Restock
    # ══════════════════════════════════════
    with tab3:
        products_df = get_products_df(business_id)
        if products_df.empty:
            st.info("No products found. Add products first.")
        else:
            st.markdown("#### Add Stock to Existing Product")
            with st.form("restock_form", clear_on_submit=True):
                product_options = {
                    f"{r['product_name']} (Current: {int(r['stock_quantity'])} units)": r
                    for _, r in products_df.iterrows()
                }
                selected_label   = st.selectbox("Select product", list(product_options.keys()))
                selected_product = product_options[selected_label]
                add_qty          = st.number_input("Units to add", min_value=1, step=1, value=10)
                restock_note     = st.text_input("Note (optional)",
                                                 placeholder="e.g. Weekly supplier delivery")
                submitted        = st.form_submit_button("🔄 Update Stock",
                                                         use_container_width=True, type="primary")

            if submitted:
                new_qty = int(selected_product["stock_quantity"]) + add_qty
                ok      = db_update(TBL_PRODUCTS, "product_id",
                                    selected_product["product_id"], {"stock_quantity": new_qty})
                if ok:
                    db_insert(TBL_RESTOCK, {
                        "restock_id":   gen_id("RST"),
                        "business_id":  business_id,
                        "product_id":   selected_product["product_id"],
                        "product_name": selected_product["product_name"],
                        "qty_added":    add_qty,
                        "qty_before":   int(selected_product["stock_quantity"]),
                        "qty_after":    new_qty,
                        "note":         restock_note.strip() if restock_note else "",
                        "recorded_by":  user.get("full_name", user.get("email", "")),
                        "restock_date": datetime.now().isoformat(),
                    })
                    st.success(
                        f"✅ Stock updated! {selected_product['product_name']}: "
                        f"{int(selected_product['stock_quantity'])} → {new_qty} units"
                    )
                    st.rerun()
                else:
                    st.error("Failed to update stock.")

    # ══════════════════════════════════════
    # Tab 4 — Restock History
    # ══════════════════════════════════════
    with tab4:
        section_header("📜 Restock History")
        restock_df = db_fetch(TBL_RESTOCK, {"business_id": business_id})
        if restock_df.empty:
            st.info("No restock history yet. Every restock will be logged here automatically.")
        else:
            restock_df["restock_date"] = pd.to_datetime(
                restock_df["restock_date"], errors="coerce", utc=True
            ).dt.tz_localize(None)
            restock_df = restock_df.sort_values("restock_date", ascending=False)

            search_rst = st.text_input("🔍 Search by product name", key="restock_search",
                                       placeholder="Type to filter…")
            if search_rst:
                restock_df = restock_df[
                    restock_df["product_name"].str.contains(search_rst, case=False, na=False)
                ]

            display_cols = [c for c in
                            ["restock_date","product_name","qty_before","qty_added",
                             "qty_after","note","recorded_by"]
                            if c in restock_df.columns]
            st.dataframe(
                restock_df[display_cols].rename(columns={
                    "restock_date": "Date",
                    "product_name": "Product",
                    "qty_before":   "Stock Before",
                    "qty_added":    "Units Added",
                    "qty_after":    "Stock After",
                    "note":         "Note",
                    "recorded_by":  "Recorded By",
                }),
                use_container_width=True,
                  )
