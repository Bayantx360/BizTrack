"""
shared/db.py
══════════════════════════════════════════════════════════════════════
BizTrack Suite — Unified Supabase Service Layer
══════════════════════════════════════════════════════════════════════

Single source of truth for:
  • Supabase client (one cached connection for the whole suite)
  • Generic CRUD helpers  (db_fetch, db_insert, db_update, db_delete)
  • Typed data loaders    (get_sales_df, get_products_df, get_expenses_df)
  • Cross-app analytics   (compute_kpis, compute_insights)
  • Payment helpers       (log_payment, get_payments_df)

All three page modules import from here:
    from shared.db import (
        get_supabase,
        db_fetch, db_insert, db_update, db_delete,
        get_sales_df, get_products_df, get_expenses_df,
        compute_kpis, compute_insights,
        log_payment, get_payments_df,
        TBL_USERS, TBL_PRODUCTS, TBL_SALES, TBL_EXPENSES,
        TBL_PAYMENTS, TBL_RESTOCK, TBL_SALE_ITEMS,
        PAYMENT_DETAILS,
    )
"""

from __future__ import annotations

import uuid
import re
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
from supabase import create_client, Client

# ── Table name constants ───────────────────────────────────────────────────────
TBL_USERS      = "users"
TBL_PRODUCTS   = "products"
TBL_SALES      = "sales"
TBL_EXPENSES   = "expenses"
TBL_PAYMENTS   = "payments"
TBL_RESTOCK    = "restock_log"
TBL_SALE_ITEMS = "sale_items"

# ── Plan / payment config ──────────────────────────────────────────────────────
PAYMENT_DETAILS = {
    "monthly_price":       1500,
    "yearly_price":        15000,
    "trial_days":          14,
    "flutterwave_monthly": "https://flutterwave.com/pay/e2jsc3ckyfya",
    "flutterwave_yearly":  "https://flutterwave.com/pay/ztzprecyyhg2",
}


# ══════════════════════════════════════════════════════════════════════════════
# SUPABASE CLIENT
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_resource(show_spinner=False)
def get_supabase() -> Client:
    """
    Return the authenticated Supabase client.
    Cached at the resource level — one connection for the entire server process,
    shared across all three app modules.
    """
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["service_key"]
    return create_client(url, key)


# ══════════════════════════════════════════════════════════════════════════════
# GENERIC CRUD HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def db_fetch(table: str, filters: dict = None) -> pd.DataFrame:
    """
    SELECT * FROM table WHERE filters (all AND equality).
    filters = {"column": "value"}
    Returns DataFrame, empty on error.
    """
    try:
        sb    = get_supabase()
        query = sb.table(table).select("*")
        if filters:
            for col, val in filters.items():
                query = query.eq(col, val)
        res = query.execute()
        return pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except Exception as e:
        st.error(f"❌ Error reading {table}: {e}")
        return pd.DataFrame()


def db_insert(table: str, row: dict) -> bool:
    """INSERT a single row dict into table. Returns True on success."""
    try:
        sb  = get_supabase()
        res = sb.table(table).insert(row).execute()
        st.cache_data.clear()
        return bool(res.data)
    except Exception as e:
        st.error(f"❌ Error inserting into {table}: {e}")
        return False


def db_update(table: str, id_col: str, id_val: str, updates: dict) -> bool:
    """UPDATE table SET updates WHERE id_col = id_val."""
    try:
        sb = get_supabase()
        sb.table(table).update(updates).eq(id_col, id_val).execute()
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"❌ Error updating {table}: {e}")
        return False


def db_delete(table: str, id_col: str, id_val: str) -> bool:
    """DELETE FROM table WHERE id_col = id_val."""
    try:
        sb = get_supabase()
        sb.table(table).delete().eq(id_col, id_val).execute()
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"❌ Error deleting from {table}: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# PAYMENT HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def log_payment(user_id: str, business_name: str, email: str,
                plan_type: str, amount: float, note: str = "") -> bool:
    """Insert a payment record into the platform revenue ledger."""
    try:
        return db_insert(TBL_PAYMENTS, {
            "payment_id":    gen_id("PAY"),
            "user_id":       user_id,
            "business_name": business_name,
            "email":         email,
            "plan_type":     plan_type,
            "amount":        amount,
            "payment_date":  datetime.now().isoformat(),
            "note":          note,
        })
    except Exception:
        return False


@st.cache_data(ttl=30, show_spinner=False)
def get_payments_df() -> pd.DataFrame:
    """Read payments table with typed columns. Returns empty DataFrame on error."""
    try:
        df = db_fetch(TBL_PAYMENTS)
        if df.empty:
            return pd.DataFrame()
        df["amount"]       = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
        df["payment_date"] = pd.to_datetime(
            df["payment_date"], errors="coerce", utc=True
        ).dt.tz_localize(None)
        return df
    except Exception:
        return pd.DataFrame()


# ══════════════════════════════════════════════════════════════════════════════
# TYPED DATA LOADERS
# Cached per business_id with a short TTL so all three apps stay in sync.
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=30, show_spinner=False)
def get_sales_df(business_id: str) -> pd.DataFrame:
    """Return typed sales DataFrame for this business."""
    df = db_fetch(TBL_SALES, {"business_id": business_id})
    if df.empty:
        return pd.DataFrame()
    df["sale_date"]    = pd.to_datetime(
        df["sale_date"], errors="coerce", utc=True
    ).dt.tz_localize(None)
    df["total_amount"] = pd.to_numeric(df["total_amount"], errors="coerce").fillna(0)
    df["gross_profit"] = pd.to_numeric(df["gross_profit"], errors="coerce").fillna(0)
    df["quantity"]     = pd.to_numeric(df["quantity"],     errors="coerce").fillna(0)
    df["cost_total"]   = pd.to_numeric(df["cost_total"],   errors="coerce").fillna(0)
    return df


@st.cache_data(ttl=30, show_spinner=False)
def get_products_df(business_id: str) -> pd.DataFrame:
    """Return typed products DataFrame for this business."""
    df = db_fetch(TBL_PRODUCTS, {"business_id": business_id})
    if df.empty:
        return pd.DataFrame()
    df["selling_price"]  = pd.to_numeric(df["selling_price"],  errors="coerce").fillna(0)
    df["cost_price"]     = pd.to_numeric(df["cost_price"],     errors="coerce").fillna(0)
    df["stock_quantity"] = pd.to_numeric(df["stock_quantity"], errors="coerce").fillna(0)
    df["reorder_level"]  = pd.to_numeric(df["reorder_level"],  errors="coerce").fillna(0)
    return df


@st.cache_data(ttl=30, show_spinner=False)
def get_expenses_df(business_id: str) -> pd.DataFrame:
    """Return typed expenses DataFrame for this business."""
    df = db_fetch(TBL_EXPENSES, {"business_id": business_id})
    if df.empty:
        return pd.DataFrame()
    df["amount"]       = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
    df["expense_date"] = pd.to_datetime(
        df["expense_date"], errors="coerce", utc=True
    ).dt.tz_localize(None)
    return df


# ══════════════════════════════════════════════════════════════════════════════
# CROSS-APP ANALYTICS
# Used by both the Sales app (dashboard KPIs) and the Business Health app.
# ══════════════════════════════════════════════════════════════════════════════

def compute_kpis(sales_df: pd.DataFrame, expenses_df: pd.DataFrame) -> dict:
    """
    Return a dict of key performance metrics spanning sales + expenses.
    Called by:  pages/sales.py  (dashboard KPI cards)
                pages/health.py (KPI summary + net profit)
    """
    now   = datetime.now()
    today = now.date()

    kpis = {
        "today_revenue":   0, "week_revenue":    0, "month_revenue":  0,
        "today_profit":    0, "week_profit":     0, "month_profit":   0,
        "today_txn":       0, "week_txn":        0, "month_txn":      0,
        "week_growth":     0, "month_expenses":  0, "net_profit":     0,
        "year_revenue":    0, "year_profit":     0, "year_txn":       0,
        "alltime_revenue": 0, "alltime_profit":  0, "alltime_txn":    0,
        "avg_daily_revenue": 0,
    }

    if sales_df.empty:
        return kpis

    df = sales_df.dropna(subset=["sale_date"])

    today_df  = df[df["sale_date"].dt.date == today]
    week_df   = df[df["sale_date"] >= (now - timedelta(days=7))]
    month_df  = df[df["sale_date"] >= (now - timedelta(days=30))]
    prev_week = df[
        (df["sale_date"] >= (now - timedelta(days=14))) &
        (df["sale_date"] <  (now - timedelta(days=7)))
    ]

    kpis["today_revenue"]  = today_df["total_amount"].sum()
    kpis["week_revenue"]   = week_df["total_amount"].sum()
    kpis["month_revenue"]  = month_df["total_amount"].sum()
    kpis["today_profit"]   = today_df["gross_profit"].sum()
    kpis["week_profit"]    = week_df["gross_profit"].sum()
    kpis["month_profit"]   = month_df["gross_profit"].sum()
    kpis["today_txn"]      = len(today_df)
    kpis["week_txn"]       = len(week_df)
    kpis["month_txn"]      = len(month_df)

    prev_rev = prev_week["total_amount"].sum()
    curr_rev = kpis["week_revenue"]
    if prev_rev > 0:
        kpis["week_growth"] = ((curr_rev - prev_rev) / prev_rev) * 100

    if not expenses_df.empty:
        m_exp = expenses_df[expenses_df["expense_date"] >= (now - timedelta(days=30))]
        kpis["month_expenses"] = m_exp["amount"].sum()
    kpis["net_profit"] = kpis["month_profit"] - kpis["month_expenses"]

    year_start = datetime(now.year, 1, 1)
    year_df    = df[df["sale_date"] >= year_start]
    kpis["year_revenue"] = year_df["total_amount"].sum()
    kpis["year_profit"]  = year_df["gross_profit"].sum()
    kpis["year_txn"]     = len(year_df)

    kpis["alltime_revenue"] = df["total_amount"].sum()
    kpis["alltime_profit"]  = df["gross_profit"].sum()
    kpis["alltime_txn"]     = len(df)

    active_days = df["sale_date"].dt.date.nunique()
    kpis["avg_daily_revenue"] = (
        kpis["alltime_revenue"] / active_days if active_days > 0 else 0
    )

    return kpis


def compute_insights(sales_df, products_df, expenses_df) -> dict:
    """
    Return structured insights dict.
    Called by:  pages/health.py  (insights + export tabs)
                pages/inventory.py (low_stock, stockout_projection)
    """
    insights = {
        "top_products_revenue":  pd.DataFrame(),
        "top_products_qty":      pd.DataFrame(),
        "slow_movers":           pd.DataFrame(),
        "daily_trend":           pd.DataFrame(),
        "weekday_performance":   pd.DataFrame(),
        "category_revenue":      pd.DataFrame(),
        "low_stock":             pd.DataFrame(),
        "stockout_projection":   pd.DataFrame(),
        "payment_split":         pd.DataFrame(),
        "avg_daily_revenue":     0,
        "best_day":              "",
        "worst_day":             "",
    }

    if sales_df.empty:
        return insights

    df = sales_df.dropna(subset=["sale_date"]).copy()

    # Top products by revenue
    insights["top_products_revenue"] = (
        df.groupby("product_name")["total_amount"]
        .sum().reset_index()
        .sort_values("total_amount", ascending=False)
        .head(10)
    )

    # Top products by quantity
    insights["top_products_qty"] = (
        df.groupby("product_name")["quantity"]
        .sum().reset_index()
        .sort_values("quantity", ascending=False)
        .head(10)
    )

    # Daily trend
    df["date"] = df["sale_date"].dt.date
    daily = (
        df.groupby("date")["total_amount"]
        .sum().reset_index().sort_values("date")
    )
    insights["daily_trend"]       = daily
    insights["avg_daily_revenue"] = daily["total_amount"].mean() if not daily.empty else 0

    # Weekday performance
    df["weekday"] = df["sale_date"].dt.day_name()
    wd_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    wd = (
        df.groupby("weekday")["total_amount"]
        .sum().reindex(wd_order, fill_value=0).reset_index()
    )
    wd.columns = ["weekday", "revenue"]
    insights["weekday_performance"] = wd
    if not wd.empty:
        insights["best_day"]  = wd.loc[wd["revenue"].idxmax(), "weekday"]
        insights["worst_day"] = wd.loc[wd["revenue"].idxmin(), "weekday"]

    # Category revenue
    if "category" in df.columns:
        insights["category_revenue"] = (
            df.groupby("category")["total_amount"]
            .sum().reset_index()
            .sort_values("total_amount", ascending=False)
        )

    # Payment split
    if "payment_method" in df.columns:
        insights["payment_split"] = (
            df.groupby("payment_method")["total_amount"].sum().reset_index()
        )

    # Slow movers (last 30 days, below half the average)
    last30 = df[df["sale_date"] >= (datetime.now() - timedelta(days=30))]
    if not last30.empty:
        prod_sales = last30.groupby("product_name")["quantity"].sum().reset_index()
        avg_qty    = prod_sales["quantity"].mean()
        insights["slow_movers"] = (
            prod_sales[prod_sales["quantity"] < avg_qty * 0.5]
            .sort_values("quantity")
        )

    # Low stock + stockout projection
    if not products_df.empty:
        insights["low_stock"] = products_df[
            products_df["stock_quantity"] <= products_df["reorder_level"]
        ][["product_name","stock_quantity","reorder_level","category"]].copy()

        proj_rows = []
        for _, prod in products_df.iterrows():
            prod_sales_df = df[df["product_name"] == prod["product_name"]]
            if not prod_sales_df.empty:
                days_range  = max((df["sale_date"].max() - df["sale_date"].min()).days, 1)
                avg_per_day = prod_sales_df["quantity"].sum() / days_range
                if avg_per_day > 0:
                    days_left = prod["stock_quantity"] / avg_per_day
                    proj_rows.append({
                        "product_name":        prod["product_name"],
                        "stock_quantity":       prod["stock_quantity"],
                        "days_until_stockout":  round(days_left, 1),
                        "avg_daily_sales":      round(avg_per_day, 2),
                    })
        if proj_rows:
            insights["stockout_projection"] = (
                pd.DataFrame(proj_rows).sort_values("days_until_stockout")
            )

    return insights


# ══════════════════════════════════════════════════════════════════════════════
# UTILITY HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def gen_id(prefix: str = "") -> str:
    """Generate a short unique ID with an optional prefix."""
    return f"{prefix}{uuid.uuid4().hex[:10].upper()}"


def fmt_naira(amount) -> str:
    """Format a number as Nigerian Naira."""
    try:
        return f"₦{float(amount):,.2f}"
    except Exception:
        return "₦0.00"


def safe_float(val, default: float = 0.0) -> float:
    try:
        return float(val)
    except Exception:
        return default


def safe_int(val, default: int = 0) -> int:
    try:
        return int(val)
    except Exception:
        return default


def parse_date(val):
    """Parse a date string to datetime. Returns None on failure."""
    try:
        from dateutil import parser as dateparser
        return dateparser.parse(str(val))
    except Exception:
        return None


def validate_email(email: str) -> bool:
    return bool(re.match(r"^[\w\.-]+@[\w\.-]+\.\w{2,}$", email))
