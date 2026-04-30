"""
PakOrderBot Report Engine — Direct MongoDB queries for Streamlit dashboard.
Bypasses the LLM agent. Uses pymongo (sync) for simplicity in Streamlit.
"""
import os
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient

def _get_mongo_uri():
    try:
        import streamlit as st
        return st.secrets.get("MONGO_URI", None) or os.getenv("MONGO_URI", "mongodb://localhost:27017")
    except Exception:
        return os.getenv("MONGO_URI", "mongodb://localhost:27017")

def _get_db(tenant_id="default"):
    client = MongoClient(_get_mongo_uri())
    return client[f"pakorderbot_db_{tenant_id}"]


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

def _fmt(val):
    if val is None: return "Rs 0"
    try:
        v = float(val)
        return f"Rs {v:,.0f}"
    except: return "Rs 0"

def _fmt_n(val):
    if val is None: return "0"
    try: return f"{int(val):,}"
    except: return "0"


# ── Fetchers ──────────────────────────────────────────────────────────────────

def fetch_order_summary(date_start, date_end=None, tenant_id="default"):
    db    = _get_db(tenant_id)
    match = {"created_at": {"$gte": date_start}}
    if date_end: match["created_at"]["$lte"] = date_end

    pipeline = [
        {"$match": {**match, "status": {"$ne": "cancelled"}}},
        {"$group": {
            "_id":           None,
            "total_orders":  {"$sum": 1},
            "total_revenue": {"$sum": "$total_amount"},
            "avg_order":     {"$avg": "$total_amount"},
        }}
    ]
    r = list(db["orders"].aggregate(pipeline))
    return r[0] if r else None


def fetch_status_breakdown(date_start, date_end=None, tenant_id="default"):
    db    = _get_db(tenant_id)
    match = {"created_at": {"$gte": date_start}}
    if date_end: match["created_at"]["$lte"] = date_end
    pipeline = [
        {"$match": match},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}}
    ]
    return {doc["_id"]: doc["count"] for doc in db["orders"].aggregate(pipeline)}


def fetch_top_items(date_start, date_end=None, limit=10, tenant_id="default"):
    db    = _get_db(tenant_id)
    match = {"created_at": {"$gte": date_start}, "status": {"$ne": "cancelled"}}
    if date_end: match["created_at"]["$lte"] = date_end
    pipeline = [
        {"$match": match},
        {"$unwind": "$items"},
        {"$group": {
            "_id":       "$items.name",
            "total_qty": {"$sum": "$items.qty"},
            "revenue":   {"$sum": "$items.subtotal"}
        }},
        {"$sort": {"total_qty": -1}},
        {"$limit": limit}
    ]
    return list(db["orders"].aggregate(pipeline))


def fetch_recent_orders(limit=20, tenant_id="default"):
    db = _get_db(tenant_id)
    return list(
        db["orders"].find({}, {"_id": 0})
        .sort("created_at", -1)
        .limit(limit)
    )


def fetch_pending_orders(tenant_id="default"):
    db = _get_db(tenant_id)
    return list(
        db["orders"]
        .find({"status": {"$in": ["received", "preparing"]}}, {"_id": 0})
        .sort("created_at", 1)
    )


def fetch_hourly_orders(date_start, date_end=None, tenant_id="default"):
    db    = _get_db(tenant_id)
    match = {"created_at": {"$gte": date_start}, "status": {"$ne": "cancelled"}}
    if date_end: match["created_at"]["$lte"] = date_end
    pipeline = [
        {"$match": match},
        {"$group": {
            "_id":     {"$hour": "$created_at"},
            "orders":  {"$sum": 1},
            "revenue": {"$sum": "$total_amount"}
        }},
        {"$sort": {"_id": 1}}
    ]
    return list(db["orders"].aggregate(pipeline))


def fetch_menu(tenant_id="default"):
    db = _get_db(tenant_id)
    return list(db["menu"].find({}, {"_id": 0}).sort("category", 1))


def build_daily_report(tenant_id="default"):
    now = datetime.now()
    ts  = _today_start()
    te  = _today_end()
    return {
        "period":          "daily",
        "generated_at":    now.strftime("%d %B %Y, %I:%M %p"),
        "date_label":      now.strftime("%d %B %Y"),
        "summary":         fetch_order_summary(ts, te, tenant_id),
        "status_breakdown":fetch_status_breakdown(ts, te, tenant_id),
        "top_items":       fetch_top_items(ts, te, limit=10, tenant_id=tenant_id),
        "recent_orders":   fetch_recent_orders(20, tenant_id),
        "pending_orders":  fetch_pending_orders(tenant_id),
        "hourly":          fetch_hourly_orders(ts, te, tenant_id),
    }


def build_weekly_report(tenant_id="default"):
    now = datetime.now()
    ts  = _week_start()
    te  = _today_end()
    return {
        "period":          "weekly",
        "generated_at":    now.strftime("%d %B %Y, %I:%M %p"),
        "date_label":      f"Pichle 7 din ({ts.strftime('%d %b')} — {now.strftime('%d %b %Y')})",
        "summary":         fetch_order_summary(ts, te, tenant_id),
        "status_breakdown":fetch_status_breakdown(ts, te, tenant_id),
        "top_items":       fetch_top_items(ts, te, limit=10, tenant_id=tenant_id),
        "recent_orders":   fetch_recent_orders(50, tenant_id),
        "hourly":          fetch_hourly_orders(ts, te, tenant_id),
    }