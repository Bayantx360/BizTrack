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
                        # ── Basic Info ──
                        st.markdown("**🏷️ Basic Information**")
                        ef1, ef2    = st.columns(2)
                        new_name    = ef1.text_input("Product Name", value=row["product_name"])
                        new_cat     = ef2.text_input("Category",     value=row["category"])
                        ef3, ef4    = st.columns(2)
                        new_cost    = ef3.number_input("Cost Price (₦)", value=safe_float(row["cost_price"]),
                                                       min_value=0.0, step=50.0)
                        new_reorder = ef4.number_input("Reorder Level",  value=safe_int(row["reorder_level"]),
                                                       min_value=0, step=1)

                        st.markdown("---")

                        # ── Pack Section ──
                        st.markdown("**📦 Pack Details**")
                        pp1, pp2, pp3 = st.columns(3)
                        new_base    = pp1.text_input("Pack Unit",
                                                     value=row.get("base_unit","unit") or "unit",
                                                     help="e.g. carton, bag, crate")
                        new_upp     = pp2.number_input("Units per Pack",
                                                       value=safe_int(row.get("units_per_pack",1)) or 1,
                                                       min_value=1, step=1)
                        new_sell    = st.number_input(
                            f"Selling Price per Pack — {row.get('base_unit','unit')} (₦)",
                            value=safe_float(row["selling_price"]), min_value=0.0, step=50.0,
                        )
                        if new_cost > 0 and new_sell > 0:
                            pm = new_sell - new_cost
                            st.caption(f"Pack margin: {fmt_naira(pm)} ({pm/new_sell*100:.1f}%)")

                        st.markdown("---")

                        # ── Unit Section ──
                        st.markdown("**🔢 Unit Details**")
                        new_sub     = st.text_input("Unit Name",
                                                    value=row.get("sub_unit","unit") or "unit",
                                                    help="e.g. piece, bottle, kg, sachet")
                        suggested   = round(new_sell / new_upp, 2) if new_upp > 1 and new_sell > 0 else new_sell
                        new_sub_price = st.number_input(
                            f"Selling Price per Unit — {row.get('sub_unit','unit')} (₦)",
                            value=safe_float(row.get("selling_price_sub", suggested)),
                            min_value=0.0, step=50.0,
                            help=f"Suggested: {fmt_naira(suggested)} (pack ÷ {new_upp})" if new_upp > 1 else "",
                        )
                        if new_upp > 1 and new_sub_price > 0 and new_cost > 0:
                            um = new_sub_price - (new_cost / new_upp)
                            st.caption(
                                f"Unit margin: {fmt_naira(um)} | "
                                f"Selling all {new_upp} units = {fmt_naira(new_sub_price * new_upp)} "
                                f"vs pack {fmt_naira(new_sell)}"
                            )

                        save = st.form_submit_button("💾 Save Changes", type="primary",
                                                     use_container_width=True)

                    if save:
                        ok = db_update(TBL_PRODUCTS, "product_id", row["product_id"], {
                            "product_name":      new_name.strip(),
                            "category":          new_cat.strip(),
                            "cost_price":        new_cost,
                            "selling_price":     new_sell,
                            "reorder_level":     new_reorder,
                            "units_per_pack":    int(new_upp),
                            "base_unit":         new_base.strip() or "unit",
                            "sub_unit":          new_sub.strip()  or "unit",
                            "selling_price_sub": new_sub_price,
                        })
                        (st.success("✅ Product updated!") if ok else st.error("❌ Update failed."))
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

            # ── Basic Info ───────────────────────────────────────
            st.markdown("#### 🏷️ Basic Information")
            f1, f2      = st.columns(2)
            prod_name   = f1.text_input("Product Name *", placeholder="e.g. Coca-Cola")
            category    = f2.text_input("Category *",     placeholder="e.g. Beverages")
            f3, f4      = st.columns(2)
            cost_price  = f3.number_input("Cost Price (₦) *", min_value=0.0, step=50.0,
                                          help="What you paid per pack/unit when buying")
            reorder_lvl = f4.number_input("Reorder Level *",  min_value=0, step=1,
                                          help="Alert me when stock falls to this level")

            st.markdown("---")

            # ── Pack Section ─────────────────────────────────────
            st.markdown("#### 📦 Pack (Bulk) Details")
            st.caption("This is how you BUY the product — e.g. by carton, bag, crate.")
            p1, p2, p3  = st.columns(3)
            base_unit      = p1.text_input("Pack Unit *", value="unit",
                                           help="e.g. carton, bag, crate, dozen")
            units_per_pack = p2.number_input("Units per Pack *", min_value=1, step=1, value=1,
                                             help="How many pieces/bottles/kg in one pack")
            stock_qty      = p3.number_input("Opening Stock *", min_value=0, step=1,
                                             help="How many packs you currently have")
            sell_price     = st.number_input(
                "Selling Price per Pack (₦) *",
                min_value=0.0, step=50.0,
                help="Price charged when selling a full pack/carton/bag",
            )
            if cost_price > 0 and sell_price > 0:
                pack_margin     = sell_price - cost_price
                pack_margin_pct = (pack_margin / sell_price) * 100
                color = "green" if pack_margin >= 0 else "red"
                st.markdown(
                    f"💡 Pack margin: **{fmt_naira(pack_margin)}** ({pack_margin_pct:.1f}%)",
                )

            st.markdown("---")

            # ── Unit Section ─────────────────────────────────────
            st.markdown("#### 🔢 Unit (Individual) Details")
            st.caption(
                "This is how you SELL individually — e.g. per piece, bottle, kg. "
                "If you only sell in packs, leave Units per Pack as 1 above and set "
                "selling price per unit same as pack price."
            )
            sub_unit       = st.text_input("Unit Name *", value="unit",
                                           help="e.g. piece, bottle, sachet, kg")

            # Suggest unit price based on pack price ÷ units_per_pack
            suggested_unit_price = round(sell_price / units_per_pack, 2) if (
                units_per_pack > 1 and sell_price > 0
            ) else sell_price
            sell_price_sub = st.number_input(
                "Selling Price per Unit (₦) *",
                min_value=0.0, step=50.0,
                value=float(suggested_unit_price),
                help=(
                    f"Suggested: {fmt_naira(suggested_unit_price)} (pack price ÷ {units_per_pack}). "
                    f"You can set higher for unit-sale profit."
                ) if units_per_pack > 1 else "Price per individual item",
            )
            if units_per_pack > 1 and sell_price_sub > 0 and cost_price > 0:
                unit_cost   = cost_price / units_per_pack
                unit_margin = sell_price_sub - unit_cost
                unit_margin_pct = (unit_margin / sell_price_sub * 100) if sell_price_sub else 0
                st.markdown(
                    f"💡 Unit margin: **{fmt_naira(unit_margin)}** ({unit_margin_pct:.1f}%) "
                    f"| Selling {units_per_pack} units = **{fmt_naira(sell_price_sub * units_per_pack)}** "
                    f"vs pack price **{fmt_naira(sell_price)}**"
                )

            submitted = st.form_submit_button("➕ Add Product", use_container_width=True, type="primary")

        if submitted:
            if not all([prod_name.strip(), category.strip()]) or sell_price <= 0:
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
                    "units_per_pack":    int(units_per_pack),
                    "created_at":        datetime.now().isoformat(),
                })
                if ok:
                    st.success(
                        f"✅ '{prod_name}' added! "
                        f"Pack: {fmt_naira(sell_price)} per {base_unit} | "
                        f"Unit: {fmt_naira(sell_price_sub)} per {sub_unit}"
                    )
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
            st.markdown("#### 🔄 Restock a Product")

            # Product selector outside form for reactive reference card
            product_options = {
                f"{r['product_name']} ({r.get('base_unit','unit')}s)": r
                for _, r in products_df.iterrows()
            }
            selected_label   = st.selectbox("Select product to restock",
                                            list(product_options.keys()))
            selected_product = product_options[selected_label]

            cur_cost      = safe_float(selected_product["cost_price"])
            cur_sell_pack = safe_float(selected_product["selling_price"])
            cur_sell_unit = safe_float(selected_product.get("selling_price_sub", 0))
            cur_stock     = safe_float(selected_product["stock_quantity"])
            base_unit     = selected_product.get("base_unit", "unit") or "unit"
            sub_unit      = selected_product.get("sub_unit",  "unit") or "unit"
            upp           = safe_int(selected_product.get("units_per_pack", 1)) or 1

            # Current prices reference card
            stock_str = (
                f"{cur_stock:.0f} {base_unit}s ({cur_stock * upp:.0f} {sub_unit}s)"
                if upp > 1 else f"{cur_stock:.0f} {base_unit}s"
            )
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("Cost Price", fmt_naira(cur_cost), help=f"Per {base_unit}")
            with c2:
                st.metric("Sell / Pack", fmt_naira(cur_sell_pack), help=f"Per {base_unit}")
            with c3:
                st.metric("Sell / Unit", fmt_naira(cur_sell_unit), help=f"Per {sub_unit}")
            with c4:
                st.metric("Current Stock", stock_str)

            st.markdown("---")

            # ── Delivery fields (outside form for reactivity) ──
            st.markdown("**📥 New Delivery**")
            rd1, rd2 = st.columns(2)
            add_qty      = rd1.number_input(
                f"Packs Received ({base_unit}s) *",
                min_value=1, step=1, value=10,
                key="restock_add_qty",
                help=f"Number of {base_unit}s received from supplier",
            )
            restock_note = rd2.text_input(
                "Supplier / Note",
                placeholder="e.g. Alhaji Musa delivery",
                key="restock_note",
            )

            st.markdown("---")

            # ── Price update (outside form so checkbox reacts immediately) ──
            st.markdown("**💰 Update Prices**")
            update_prices = st.checkbox(
                "Supplier prices have changed — update now",
                value=False,
                key="restock_update_prices",
                help="Tick this if cost or selling prices changed with this delivery",
            )

            if update_prices:
                st.caption("Pre-filled with current prices. Edit only what changed.")

                new_cost = st.number_input(
                    f"New Cost Price per {base_unit} (₦)",
                    min_value=0.0, step=50.0, value=float(cur_cost),
                    key="restock_new_cost",
                )
                if new_cost != cur_cost and cur_cost > 0:
                    diff = new_cost - cur_cost
                    pct  = diff / cur_cost * 100
                    icon = "📈 Cost UP" if diff > 0 else "📉 Cost DOWN"
                    st.caption(f"{icon} by {fmt_naira(abs(diff))} ({abs(pct):.1f}%)")

                st.markdown("**Pack Selling Price**")
                new_sell_pack = st.number_input(
                    f"New Selling Price per {base_unit} (₦)",
                    min_value=0.0, step=50.0, value=float(cur_sell_pack),
                    key="restock_new_sell_pack",
                )
                if new_cost > 0 and new_sell_pack > 0:
                    pm = new_sell_pack - new_cost
                    st.caption(
                        f"New pack margin: {fmt_naira(pm)} ({pm/new_sell_pack*100:.1f}%)"
                    )

                st.markdown("**Unit Selling Price**")
                suggested_unit = round(new_sell_pack / upp, 2) if upp > 1 else new_sell_pack
                new_sell_unit  = st.number_input(
                    f"New Selling Price per {sub_unit} (₦)",
                    min_value=0.0, step=50.0,
                    value=float(cur_sell_unit) if cur_sell_unit > 0 else float(suggested_unit),
                    key="restock_new_sell_unit",
                    help=f"Suggested: {fmt_naira(suggested_unit)}" if upp > 1 else "",
                )
                if upp > 1 and new_sell_unit > 0 and new_cost > 0:
                    um = new_sell_unit - (new_cost / upp)
                    st.caption(
                        f"New unit margin: {fmt_naira(um)} | "
                        f"All {upp} units = {fmt_naira(new_sell_unit * upp)} "
                        f"vs pack {fmt_naira(new_sell_pack)}"
                    )
            else:
                new_cost      = cur_cost
                new_sell_pack = cur_sell_pack
                new_sell_unit = cur_sell_unit

            st.markdown("---")

            # ── Submit button only inside the form ──
            with st.form("restock_form", clear_on_submit=True):
                submitted = st.form_submit_button(
                    "🔄 Confirm Restock", use_container_width=True, type="primary"
                )

            if submitted:
                new_qty = int(round(cur_stock + add_qty))
                updates = {"stock_quantity": new_qty}
                if update_prices:
                    updates["cost_price"]        = new_cost
                    updates["selling_price"]     = new_sell_pack
                    updates["selling_price_sub"] = new_sell_unit

                ok = db_update(TBL_PRODUCTS, "product_id",
                               selected_product["product_id"], updates)
                if ok:
                    db_insert(TBL_RESTOCK, {
                        "restock_id":     gen_id("RST"),
                        "business_id":    business_id,
                        "product_id":     selected_product["product_id"],
                        "product_name":   selected_product["product_name"],
                        "qty_added":      add_qty,
                        "qty_before":     cur_stock,
                        "qty_after":      new_qty,
                        "note":           restock_note.strip() if restock_note else "",
                        "recorded_by":    user.get("full_name", user.get("email", "")),
                        "restock_date":   datetime.now().isoformat(),
                        "old_cost_price": cur_cost,
                        "new_cost_price": new_cost      if update_prices else None,
                        "old_sell_pack":  cur_sell_pack,
                        "new_sell_pack":  new_sell_pack if update_prices else None,
                        "old_sell_unit":  cur_sell_unit,
                        "new_sell_unit":  new_sell_unit if update_prices else None,
                        "prices_updated": update_prices,
                    })
                    msg = (
                        f"✅ Restocked! {selected_product['product_name']}: "
                        f"{cur_stock:.0f} → {new_qty:.0f} {base_unit}s"
                    )
                    if update_prices:
                        msg += (
                            f" | Prices updated — Cost: {fmt_naira(new_cost)}, "
                            f"Pack: {fmt_naira(new_sell_pack)}, "
                            f"Unit: {fmt_naira(new_sell_unit)}"
                        )
                    st.success(msg)
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
