"""
HisabBot Report Engine — Direct MongoDB Queries
Bypasses the LLM agent entirely. Queries MongoDB directly for accurate report data.
Works as a standalone module called from Streamlit (sync wrapper around async Motor queries).
"""
import os
import asyncio
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
LOW_STOCK_THRESHOLD = 5


# ── Sync MongoDB client (for Streamlit — not async) ───────────────────────────
def _get_db():
    client = MongoClient(MONGO_URI)
    return client["hisabbot_db"]


# ── Date helpers ──────────────────────────────────────────────────────────────
def _now():
    return datetime.now(timezone.utc)

def _today_start():
    n = _now()
    return n.replace(hour=0, minute=0, second=0, microsecond=0)

def _today_end():
    n = _now()
    return n.replace(hour=23, minute=59, second=59, microsecond=999999)

def _week_start():
    return (_now() - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)

def _month_start():
    n = _now()
    return n.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

def _month_end():
    n = _now()
    if n.month == 12:
        nxt = datetime(n.year+1, 1, 1, tzinfo=timezone.utc)
    else:
        nxt = datetime(n.year, n.month+1, 1, tzinfo=timezone.utc)
    return nxt - timedelta(microseconds=1)

def _fmt(val):
    """Format number as Rs X,XXX"""
    if val is None: return "Rs 0"
    try:
        v = float(val)
        return f"Rs {v:,.0f}" if v == int(v) else f"Rs {v:,.2f}"
    except: return "Rs 0"

def _fmt_n(val):
    if val is None: return "0"
    try: return f"{int(val):,}"
    except: return "0"


# ── Core data fetchers ────────────────────────────────────────────────────────

def fetch_sales_summary(date_start, date_end=None):
    """Total qty, revenue, cost, profit for a date range."""
    db = _get_db()
    match = {"date": {"$gte": date_start}}
    if date_end:
        match["date"]["$lte"] = date_end

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id":           None,
            "total_qty":     {"$sum": "$qty"},
            "total_revenue": {"$sum": "$sale_total"},
            "total_cost":    {"$sum": "$cost_total"},
            "total_profit":  {"$sum": "$profit"},
            "total_orders":  {"$sum": 1},
        }}
    ]
    result = list(db["sales"].aggregate(pipeline))
    if not result:
        return None
    r = result[0]
    return {
        "total_qty":     r.get("total_qty", 0),
        "total_revenue": r.get("total_revenue") or 0,
        "total_cost":    r.get("total_cost") or 0,
        "total_profit":  r.get("total_profit") or 0,
        "total_orders":  r.get("total_orders", 0),
    }


def fetch_top_products(date_start, date_end=None, limit=5):
    """Top products by revenue with profit breakdown."""
    db = _get_db()
    match = {"date": {"$gte": date_start}}
    if date_end:
        match["date"]["$lte"] = date_end

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id":     "$product",
            "qty":     {"$sum": "$qty"},
            "revenue": {"$sum": "$sale_total"},
            "profit":  {"$sum": "$profit"},
        }},
        {"$sort": {"revenue": -1}},
        {"$limit": limit},
    ]
    return list(db["sales"].aggregate(pipeline))


def fetch_stock_status():
    """All products with qty (clamped to 0) and cost price."""
    db = _get_db()
    pipeline = [
        {"$addFields": {"qty": {"$max": ["$qty", 0]}}},
        {"$sort": {"product": 1}},
    ]
    return list(db["inventory"].aggregate(pipeline))


def fetch_low_stock():
    """Products at or below low_stock_threshold."""
    db = _get_db()
    pipeline = [
        {"$addFields": {
            "qty":       {"$max": ["$qty", 0]},
            "threshold": {"$ifNull": ["$low_stock_threshold", LOW_STOCK_THRESHOLD]}
        }},
        {"$match": {"$expr": {"$lte": ["$qty", "$threshold"]}}},
        {"$sort": {"qty": 1}},
    ]
    return list(db["inventory"].aggregate(pipeline))


def fetch_payments(date_start, date_end=None):
    """Total payments received in a period."""
    db = _get_db()
    match = {"type": "payment", "date": {"$gte": date_start}}
    if date_end:
        match["date"]["$lte"] = date_end

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id":         None,
            "total":       {"$sum": "$amount"},
            "count":       {"$sum": 1},
        }}
    ]
    result = list(db["finance"].aggregate(pipeline))
    return result[0] if result else None


def fetch_payments_by_customer(date_start, date_end=None, limit=20):
    """Per-customer payment breakdown.
    Reads customer, customer_address directly from finance docs — no join needed.
    """
    db = _get_db()
    match = {"type": "payment", "date": {"$gte": date_start}}
    if date_end:
        match["date"]["$lte"] = date_end

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id":      "$customer",
            "total":    {"$sum": "$amount"},
            "count":    {"$sum": 1},
            "last_pay": {"$max": "$date"},
            "address":  {"$last": "$customer_address"},
            "phone":    {"$last": "$phone"},
        }},
        {"$addFields": {
            "address": {"$ifNull": ["$address", "—"]},
            "phone":   {"$ifNull": ["$phone",   "—"]},
        }},
        {"$sort": {"total": -1}},
        {"$limit": limit},
    ]
    return list(db["finance"].aggregate(pipeline))


def fetch_pending_credit(limit=10):
    """Customers with outstanding balance, sorted by amount."""
    db = _get_db()
    return list(
        db["customers"]
        .find({"total_credit": {"$gt": 0}})
        .sort("total_credit", -1)
        .limit(limit)
    )


def fetch_top_customers(date_start, date_end=None, limit=5):
    """Top customers by purchase amount in a period."""
    db = _get_db()
    match = {"date": {"$gte": date_start}}
    if date_end:
        match["date"]["$lte"] = date_end

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id":    "$customer",
            "spent":  {"$sum": "$sale_total"},
            "orders": {"$sum": 1},
            "profit": {"$sum": "$profit"},
        }},
        {"$sort": {"spent": -1}},
        {"$limit": limit},
    ]
    return list(db["sales"].aggregate(pipeline))


def fetch_product_profit(date_start, date_end=None):
    """Per-product profit breakdown."""
    db = _get_db()
    match = {"date": {"$gte": date_start}}
    if date_end:
        match["date"]["$lte"] = date_end

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id":     "$product",
            "qty":     {"$sum": "$qty"},
            "revenue": {"$sum": "$sale_total"},
            "cost":    {"$sum": "$cost_total"},
            "profit":  {"$sum": "$profit"},
        }},
        {"$sort": {"profit": -1}},
    ]
    return list(db["sales"].aggregate(pipeline))


def fetch_total_stock_value():
    """Total inventory value at cost price."""
    db = _get_db()
    pipeline = [
        {"$match": {"cost_price": {"$ne": None}, "qty": {"$gt": 0}}},
        {"$group": {
            "_id":         None,
            "total_value": {"$sum": {"$multiply": ["$qty", "$cost_price"]}},
            "total_items": {"$sum": 1},
            "total_units": {"$sum": "$qty"},
        }}
    ]
    result = list(db["inventory"].aggregate(pipeline))
    return result[0] if result else None


# ── Report builders ───────────────────────────────────────────────────────────

def build_daily_report():
    now  = datetime.now()
    ts   = _today_start()
    te   = _today_end()

    sales       = fetch_sales_summary(ts, te)
    prods       = fetch_top_products(ts, te, limit=5)
    stock       = fetch_stock_status()
    low         = fetch_low_stock()
    pays        = fetch_payments(ts, te)
    pays_detail = fetch_payments_by_customer(ts, te)
    pending     = fetch_pending_credit(limit=8)

    return {
        "period":           "daily",
        "generated_at":     now.strftime("%d %B %Y, %I:%M %p"),
        "date_label":       now.strftime("%d %B %Y"),
        "sales":            sales,
        "top_products":     prods,
        "stock":            stock,
        "low_stock":        low,
        "payments":         pays,
        "payments_detail":  pays_detail,
        "pending":          pending,
    }


def build_weekly_report():
    now  = datetime.now()
    ts   = _week_start()
    te   = _today_end()

    sales       = fetch_sales_summary(ts, te)
    prods       = fetch_top_products(ts, te, limit=5)
    customers   = fetch_top_customers(ts, te, limit=5)
    stock       = fetch_stock_status()
    low         = fetch_low_stock()
    pays        = fetch_payments(ts, te)
    pays_detail = fetch_payments_by_customer(ts, te)
    pending     = fetch_pending_credit(limit=8)
    pprofit     = fetch_product_profit(ts, te)

    return {
        "period":           "weekly",
        "generated_at":     now.strftime("%d %B %Y, %I:%M %p"),
        "date_label":       f"Pichle 7 din ({ts.strftime('%d %b')} — {now.strftime('%d %b %Y')})",
        "sales":            sales,
        "top_products":     prods,
        "top_customers":    customers,
        "stock":            stock,
        "low_stock":        low,
        "payments":         pays,
        "payments_detail":  pays_detail,
        "pending":          pending,
        "product_profit":   pprofit,
    }


def build_monthly_report():
    now  = datetime.now()
    ts   = _month_start()
    te   = _month_end()

    sales       = fetch_sales_summary(ts, te)
    prods       = fetch_top_products(ts, te, limit=5)
    customers   = fetch_top_customers(ts, te, limit=5)
    stock       = fetch_stock_status()
    low         = fetch_low_stock()
    pays        = fetch_payments(ts, te)
    pays_detail = fetch_payments_by_customer(ts, te)
    pending     = fetch_pending_credit(limit=10)
    pprofit     = fetch_product_profit(ts, te)
    stk_val     = fetch_total_stock_value()

    return {
        "period":           "monthly",
        "generated_at":     now.strftime("%d %B %Y, %I:%M %p"),
        "date_label":       now.strftime("%B %Y"),
        "sales":            sales,
        "top_products":     prods,
        "top_customers":    customers,
        "stock":            stock,
        "low_stock":        low,
        "payments":         pays,
        "payments_detail":  pays_detail,
        "pending":          pending,
        "product_profit":   pprofit,
        "stock_value":      stk_val,
    }


# ── Schedule checker ──────────────────────────────────────────────────────────

def is_report_due(period: str):
    now = datetime.now()
    h, wd, day = now.hour, now.weekday(), now.day

    if period == "daily":
        if h >= 21:
            return True, f"Aaj ka report ready hai — {now.strftime('%d %b, %I:%M %p')}"
        due  = now.replace(hour=21, minute=0, second=0)
        diff = due - now
        hrs  = diff.seconds // 3600
        mins = (diff.seconds % 3600) // 60
        return False, f"Daily report aaj raat 9:00 PM par aayega — {hrs}h {mins}m baaki"

    elif period == "weekly":
        if wd == 6 and h >= 12:
            return True, f"Is hafte ka report ready hai — {now.strftime('%d %b, %I:%M %p')}"
        days_to_sunday = (6 - wd) % 7 or 7
        if wd == 6:
            due  = now.replace(hour=12, minute=0, second=0)
            diff = due - now
            hrs  = diff.seconds // 3600
            mins = (diff.seconds % 3600) // 60
            msg  = f"Weekly report aaj 12:00 PM par aayega — {hrs}h {mins}m baaki"
        else:
            msg = f"Weekly report Sunday 12:00 PM par aayega — {days_to_sunday} din baaki"
        return False, msg

    elif period == "monthly":
        if day >= 28 and h >= 13:
            return True, f"Is mahine ka report ready hai — {now.strftime('%d %b, %I:%M %p')}"
        if day < 28:
            msg = f"Monthly report {now.strftime('%B')} ki 28 tarikh 1:00 PM par aayega — {28-day} din baaki"
        else:
            due  = now.replace(hour=13, minute=0, second=0)
            diff = due - now
            hrs  = diff.seconds // 3600
            mins = (diff.seconds % 3600) // 60
            msg  = f"Monthly report aaj 1:00 PM par aayega — {hrs}h {mins}m baaki"
        return False, msg

    return False, "Schedule maloom nahi."