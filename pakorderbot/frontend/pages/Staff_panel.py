"""
PakOrderBot — Staff Panel v3  (Full Fix + Rich Analytics)
==========================================================
Fixes applied:
  ✅  Menu delete / disable — direct MongoDB via report_engine (no LLM flakiness)
  ✅  Offers — items field displayed, disable/enable via direct DB, not staff_chat
  ✅  Analytics — full Plotly charts: revenue trend, hourly heatmap, status pie,
                  top items bar, category breakdown, KPI scorecards, daily comparison
  ✅  Offer creation — items saved and displayed correctly
  ✅  All write ops that were silently failing now use direct DB calls as fallback
"""

import streamlit as st
import requests, os, re, html, json
from datetime import datetime, timedelta, timezone

# ── Report / DB engine ────────────────────────────────────────────────────────
def _load_report_engine():
    try:
        import sys, os as _os
        sys.path.insert(0, _os.path.dirname(__file__))
        from report_engine import (
            fetch_order_summary, fetch_status_breakdown, fetch_top_items,
            fetch_recent_orders, fetch_pending_orders, fetch_hourly_orders,
            fetch_menu, build_daily_report, build_weekly_report, _fmt, _fmt_n,
            _get_db,
        )
        return True, {
            "fetch_order_summary":    fetch_order_summary,
            "fetch_status_breakdown": fetch_status_breakdown,
            "fetch_top_items":        fetch_top_items,
            "fetch_recent_orders":    fetch_recent_orders,
            "fetch_pending_orders":   fetch_pending_orders,
            "fetch_hourly_orders":    fetch_hourly_orders,
            "fetch_menu":             fetch_menu,
            "build_daily_report":     build_daily_report,
            "build_weekly_report":    build_weekly_report,
            "_fmt":                   _fmt,
            "_fmt_n":                 _fmt_n,
            "_get_db":                _get_db,
        }
    except Exception as e:
        return False, str(e)

_RE_OK, _RE = _load_report_engine()

st.set_page_config(page_title="Staff Panel — PakOrderBot", page_icon="👨‍🍳", layout="wide")

try:    _DEFAULT_API = st.secrets["API_URL"]
except: _DEFAULT_API = os.getenv("API_URL", "http://127.0.0.1:8000")


# ══════════════════════════════════════════════════════════════════════════════
#  CSS
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&family=Outfit:wght@300;400;500;600;700&display=swap');
html,body,[class*="css"]{font-family:'Outfit',sans-serif;}
#MainMenu,footer,header{visibility:hidden;}
.stApp{background:#08090f;}
section[data-testid="stSidebar"]{background:#0c0d18 !important;border-right:1px solid #16192e;}

/* Bubbles */
.staff-bubble{background:#0d1025;border:1px solid #1a1e32;border-radius:18px 18px 18px 4px;
  padding:10px 16px;max-width:80%;color:#e8ecff;font-size:14px;line-height:1.6;white-space:pre-wrap;word-break:break-word;}
.user-sbubble{background:#12163a;border:1px solid #2d3563;border-radius:18px 18px 4px 18px;
  padding:10px 16px;max-width:72%;color:#c5ccf5;font-size:14px;line-height:1.6;white-space:pre-wrap;}
.err-bubble{background:#1c0a0a !important;border-color:#7f1d1d !important;color:#fca5a5 !important;}
.smeta{font-size:11px;color:#2d3563;margin-top:3px;font-family:'JetBrains Mono',monospace;}

/* KPI */
.kpi-row{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:18px;}
.kpi-box{flex:1;min-width:130px;background:#0d1025;border:1px solid #1a1e32;border-radius:12px;padding:16px 18px;}
.kpi-lbl{font-size:9px;font-family:'JetBrains Mono',monospace;color:#4c5ee8;letter-spacing:.12em;
  text-transform:uppercase;margin-bottom:6px;}
.kpi-num{font-size:26px;font-weight:700;letter-spacing:-.02em;}
.kpi-delta{font-size:11px;margin-top:4px;font-family:'JetBrains Mono',monospace;}
.sv-blue{color:#60a5fa;}.sv-green{color:#34d399;}.sv-yellow{color:#fbbf24;}
.sv-purple{color:#a78bfa;}.sv-red{color:#f87171;}.sv-cyan{color:#22d3ee;}

/* Status badges */
.order-status{font-size:11px;font-family:'JetBrains Mono',monospace;padding:2px 10px;border-radius:20px;display:inline-block;}
.s-received{background:#0c1a2e;color:#60a5fa;border:1px solid #1e40af;}
.s-preparing{background:#1c0a00;color:#fbbf24;border:1px solid #92400e;}
.s-ready{background:#052e20;color:#34d399;border:1px solid #065f46;}
.s-dispatched{background:#1a0d2e;color:#a78bfa;border:1px solid #5b21b6;}
.s-delivered{background:#0a1a0a;color:#6b9e6b;border:1px solid #2d6a2d;}
.s-cancelled{background:#1c0a0a;color:#f87171;border:1px solid #7f1d1d;}

/* Table */
.data-tbl{width:100%;border-collapse:collapse;font-size:13px;}
.data-tbl th{font-family:'JetBrains Mono',monospace;font-size:9px;color:#4c5ee8;letter-spacing:.1em;
  text-transform:uppercase;padding:8px 12px;border-bottom:2px solid #1a1e32;text-align:left;}
.data-tbl td{padding:9px 12px;border-bottom:1px solid #0d1025;color:#c5ccf5;vertical-align:middle;}
.data-tbl tr:hover td{background:#0d1025;}

/* Section header */
.sec-hdr{font-family:'JetBrains Mono',monospace;font-size:11px;color:#2d3563;
  padding-bottom:10px;border-bottom:1px solid #1a1e32;margin-bottom:18px;letter-spacing:.06em;}

/* Offer card */
.offer-card{background:#0d1025;border:1px solid #1a1e32;border-radius:12px;padding:16px 20px;margin-bottom:12px;}
.offer-card.active{border-color:#065f46;}
.offer-card.inactive{border-color:#374151;opacity:.7;}

/* Feedback card */
.fb-card{background:#0d1025;border:1px solid #1a1e32;border-radius:10px;padding:14px 18px;margin-bottom:10px;}

/* Inputs */
.stTextInput>div>div>input{background:#0d1025 !important;border:1px solid #1a1e32 !important;
  color:#e8ecff !important;border-radius:10px !important;font-size:14px !important;}
.stTextInput>div>div>input:focus{border-color:#4c5ee8 !important;}
.stButton>button{background:#0d1025 !important;border:1px solid #1a1e32 !important;
  color:#7b8cf0 !important;border-radius:10px !important;font-size:13px !important;transition:all .15s !important;}
.stButton>button:hover{border-color:#4c5ee8 !important;color:#a5b0ff !important;background:#12163a !important;}
.stSelectbox>div>div{background:#0d1025 !important;border:1px solid #1a1e32 !important;color:#e8ecff !important;}
hr{border-color:#16192e !important;}
::-webkit-scrollbar{width:3px;}
::-webkit-scrollbar-thumb{background:#1a1e32;border-radius:2px;}

/* Chart container */
.chart-box{background:#0d1025;border:1px solid #1a1e32;border-radius:12px;padding:16px 20px;margin-bottom:16px;}
.chart-title{font-family:'JetBrains Mono',monospace;font-size:10px;color:#4c5ee8;
  letter-spacing:.1em;text-transform:uppercase;margin-bottom:10px;}

/* Metric delta */
.delta-up{color:#34d399;font-size:12px;}
.delta-dn{color:#f87171;font-size:12px;}
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  Session state
# ══════════════════════════════════════════════════════════════════════════════
for k, v in [
    ("staff_token", None), ("staff_user", None), ("staff_msgs", []),
    ("api_url", _DEFAULT_API), ("staff_tab", "orders"), ("tenant_id", "default")
]:
    if k not in st.session_state:
        st.session_state[k] = v


# ══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════════════
def strip_html(t): return re.sub(r'<[^>]*>', '', str(t)).strip()
def esc(t):        return html.escape(strip_html(str(t))).replace('\n', '<br>')

def _headers():
    h = {}
    if st.session_state.staff_token:
        h["Authorization"] = f"Bearer {st.session_state.staff_token}"
    if st.session_state.get("tenant_id"):
        h["x-tenant-id"] = st.session_state.tenant_id
    return h

def _api(path, method="get", json_data=None, timeout=60):
    try:
        url = f"{st.session_state.api_url}{path}"
        r   = (requests.get(url, headers=_headers(), timeout=timeout) if method == "get"
               else requests.post(url, headers=_headers(), json=json_data, timeout=timeout))
        return r.json(), r.status_code
    except requests.exceptions.ConnectionError:
        return {"error": "Server offline"}, 0
    except Exception as e:
        return {"error": str(e)}, 0

def staff_chat(msg, history=None):
    h    = history or st.session_state.staff_msgs[-6:]
    hist = [{"role": "user" if m["role"] == "user" else "assistant", "content": m["content"]}
            for m in h if m.get("content") and not m.get("is_error")]
    data, _ = _api("/staff/chat", "post", {"message": msg, "history": hist, "conv_stage": "", "order_draft": {}})
    return data

def add_msg(role, content, is_error=False):
    clean = strip_html(content) if role == "bot" else content
    st.session_state.staff_msgs.append({
        "role": role, "content": clean,
        "time": datetime.now().strftime("%H:%M:%S"), "is_error": is_error,
    })

def verify_token():
    if not st.session_state.staff_token: return False
    data, code = _api("/auth/verify", "post", {})
    return code == 200 and data.get("valid")

def _stars(rating):
    r = max(0, min(5, int(rating or 0)))
    return "★" * r + "☆" * (5 - r)

# ── Direct DB write helpers (bypass LLM for reliability) ──────────────────────
def _db_update_menu(name, update_doc):
    """Direct pymongo update for menu item."""
    if not _RE_OK: return False
    try:
        db = _RE["_get_db"](st.session_state.get("tenant_id", "default"))
        result = db["menu"].update_one({"name": name.lower()}, {"$set": update_doc})
        return result.modified_count > 0 or result.matched_count > 0
    except Exception as e:
        st.error(f"DB error: {e}")
        return False

def _db_delete_menu(name):
    """Direct pymongo delete for menu item."""
    if not _RE_OK: return False
    try:
        db = _RE["_get_db"](st.session_state.get("tenant_id", "default"))
        result = db["menu"].delete_one({"name": name.lower()})
        return result.deleted_count > 0
    except Exception as e:
        st.error(f"DB error: {e}")
        return False

def _db_insert_offer(doc):
    if not _RE_OK: return False
    try:
        db = _RE["_get_db"](st.session_state.get("tenant_id", "default"))
        db["offers"].insert_one(doc)
        return True
    except Exception as e:
        st.error(f"DB error: {e}")
        return False

def _db_update_offer(title, update_doc):
    if not _RE_OK: return False
    try:
        db = _RE["_get_db"](st.session_state.get("tenant_id", "default"))
        result = db["offers"].update_one(
            {"title": {"$regex": f"^{re.escape(title)}$", "$options": "i"}},
            {"$set": update_doc}
        )
        return result.modified_count > 0 or result.matched_count > 0
    except Exception as e:
        st.error(f"DB error: {e}")
        return False

def _db_fetch_offers():
    if not _RE_OK: return []
    try:
        db = _RE["_get_db"](st.session_state.get("tenant_id", "default"))
        return list(db["offers"].find({}, {"_id": 0}).sort("active", -1))
    except Exception:
        return []

def _db_fetch_menu_all():
    """Fetch ALL menu items (including unavailable) for management."""
    if not _RE_OK: return []
    try:
        db = _RE["_get_db"](st.session_state.get("tenant_id", "default"))
        return list(db["menu"].find({}, {"_id": 0}).sort("category", 1))
    except Exception:
        return []

def _db_fetch_feedback():
    """Fetch all feedback directly from DB, newest first."""
    if not _RE_OK: return []
    try:
        db = _RE["_get_db"](st.session_state.get("tenant_id", "default"))
        return list(db["feedback"].find({}, {"_id": 0}).sort("created_at", -1).limit(200))
    except Exception:
        return []

def _db_delete_feedback(customer_name, created_at):
    """Delete a single feedback record."""
    if not _RE_OK: return False
    try:
        db = _RE["_get_db"](st.session_state.get("tenant_id", "default"))
        filt = {}
        if customer_name: filt["customer_name"] = customer_name
        if created_at:    filt["created_at"]    = created_at
        result = db["feedback"].delete_one(filt)
        return result.deleted_count > 0
    except Exception:
        return False


def _db_fetch_daily_revenue(days=30):
    """Fetch daily revenue for the last N days."""
    if not _RE_OK: return []
    try:
        db   = _RE["_get_db"](st.session_state.get("tenant_id", "default"))
        from datetime import datetime, timezone, timedelta
        start = (datetime.now(timezone.utc) - timedelta(days=days)).replace(
            hour=0, minute=0, second=0, microsecond=0)
        pipeline = [
            {"$match": {"created_at": {"$gte": start}, "status": {"$ne": "cancelled"}}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                "orders":  {"$sum": 1},
                "revenue": {"$sum": "$total_amount"},
            }},
            {"$sort": {"_id": 1}},
        ]
        return list(db["orders"].aggregate(pipeline))
    except Exception:
        return []

def _db_fetch_category_revenue(date_start, date_end=None):
    """Revenue by menu category."""
    if not _RE_OK: return []
    try:
        db   = _RE["_get_db"](st.session_state.get("tenant_id", "default"))
        match = {"created_at": {"$gte": date_start}, "status": {"$ne": "cancelled"}}
        if date_end: match["created_at"]["$lte"] = date_end
        pipeline = [
            {"$match": match},
            {"$unwind": "$items"},
            {"$lookup": {
                "from": "menu",
                "localField": "items.name",
                "foreignField": "name",
                "as": "menu_info"
            }},
            {"$unwind": {"path": "$menu_info", "preserveNullAndEmpty": True}},
            {"$group": {
                "_id":     {"$ifNull": ["$menu_info.category", "other"]},
                "revenue": {"$sum": "$items.subtotal"},
                "qty":     {"$sum": "$items.qty"},
            }},
            {"$sort": {"revenue": -1}},
        ]
        return list(db["orders"].aggregate(pipeline))
    except Exception:
        return []

def _db_fetch_payment_breakdown(date_start, date_end=None):
    if not _RE_OK: return []
    try:
        db    = _RE["_get_db"](st.session_state.get("tenant_id", "default"))
        match = {"created_at": {"$gte": date_start}, "status": {"$ne": "cancelled"}}
        if date_end: match["created_at"]["$lte"] = date_end
        pipeline = [
            {"$match": match},
            {"$group": {"_id": "$payment_method", "count": {"$sum": 1}, "revenue": {"$sum": "$total_amount"}}},
            {"$sort": {"revenue": -1}},
        ]
        return list(db["orders"].aggregate(pipeline))
    except Exception:
        return []

STATUS_CSS   = {"received":"s-received","preparing":"s-preparing","ready":"s-ready",
                "dispatched":"s-dispatched","delivered":"s-delivered","cancelled":"s-cancelled"}
STATUS_EMOJI = {"received":"📥","preparing":"👨‍🍳","ready":"✅","dispatched":"🚗",
                "delivered":"✓","cancelled":"❌"}


# ══════════════════════════════════════════════════════════════════════════════
#  LOGIN
# ══════════════════════════════════════════════════════════════════════════════
if not st.session_state.staff_token or not verify_token():
    st.session_state.staff_token = None
    _, col2, _ = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div style='text-align:center;padding:48px 0 28px;'>
            <div style='font-size:44px;margin-bottom:10px;'>👨‍🍳</div>
            <div style='font-size:24px;font-weight:700;color:#e8ecff;margin-bottom:4px;'>Staff Login</div>
            <div style='font-size:13px;color:#2d3563;'>PakOrderBot — Restaurant Management</div>
        </div>""", unsafe_allow_html=True)
        with st.form("login_form"):
            tenant_id = st.text_input("Tenant ID", placeholder="tenant ID likhein (e.g., Asif)")
            username  = st.text_input("Username", placeholder="username likhein")
            password  = st.text_input("Password", type="password", placeholder="password")
            api_input = st.text_input("API URL", value=st.session_state.api_url)
            submitted = st.form_submit_button("🔐 Login", use_container_width=True)
        if submitted:
            if api_input: st.session_state.api_url = api_input
            # Use the entered tenant_id temporarily for login
            st.session_state.tenant_id = tenant_id or username
            data, code = _api("/auth/login", "post", {"username": username, "password": password})
            if code == 200 and data.get("token"):
                st.session_state.staff_token = data["token"]
                st.session_state.staff_user  = data.get("username", "Staff")
                st.success(f"✅ {data.get('message', 'Login successful!')}")
                st.rerun()
            else:
                st.session_state.tenant_id = "default" # Revert if failed
                st.error(f"❌ {data.get('detail', data.get('error', 'Login failed'))}")
    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
#  SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown(
        f"<div style='font-size:17px;font-weight:700;color:#e8ecff;padding-bottom:2px;'>👨‍🍳 Staff Panel</div>"
        f"<div style='font-size:12px;color:#4c5ee8;margin-bottom:14px;font-family:JetBrains Mono,monospace;"
        f"'>● {st.session_state.staff_user}</div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    TABS = [
        ("📋", "Live Orders",    "orders"),
        ("📜", "Order History",  "history"),
        ("🍛", "Menu",           "menu"),
        ("🎉", "Offers",         "offers"),
        ("⭐", "Feedback",       "feedback"),
        ("📊", "Analytics",      "analytics"),
        ("💬", "AI Chat",        "chat"),
    ]
    for icon, label, key in TABS:
        if st.button(f"{icon}  {label}", use_container_width=True, key=f"tab_{key}"):
            st.session_state.staff_tab = key
            st.rerun()
    st.markdown("---")
    if st.button("🚪 Logout", use_container_width=True):
        for k in ("staff_token","staff_user","staff_msgs"):
            st.session_state[k] = None if k != "staff_msgs" else []
        st.session_state.tenant_id = "default"
        st.rerun()
    st.markdown(
        "<div style='font-size:10px;color:#16192e;font-family:JetBrains Mono,monospace;"
        "margin-top:12px;line-height:1.8;'>PakOrderBot v3<br>Staff Panel</div>",
        unsafe_allow_html=True,
    )

tab = st.session_state.staff_tab


# ══════════════════════════════════════════════════════════════════════════════
#  LIVE ORDERS — helpers
# ══════════════════════════════════════════════════════════════════════════════

def _db_update_order_status(order_id: str, new_status: str) -> bool:
    """Direct pymongo update — no LLM, instant."""
    if not _RE_OK: return False
    try:
        db = _RE["_get_db"](st.session_state.get("tenant_id", "default"))
        r  = db["orders"].update_one(
            {"order_id": order_id},
            {"$set": {"status": new_status, "status_updated_at": datetime.now(timezone.utc)}},
        )
        return r.matched_count > 0
    except Exception as e:
        st.error(f"DB error: {e}")
        return False

def _db_fetch_pending_sorted() -> list:
    """All active orders sorted oldest-first (FIFO)."""
    if not _RE_OK: return []
    try:
        db = _RE["_get_db"](st.session_state.get("tenant_id", "default"))
        return list(
            db["orders"]
            .find({"status": {"$in": ["received", "preparing", "ready"]}}, {"_id": 0})
            .sort("created_at", 1)   # ← FIFO: first come, first served
        )
    except Exception:
        return []

def _seconds_since(dt_val) -> int:
    """Seconds elapsed since a datetime value (aware or naive)."""
    if dt_val is None: return 0
    try:
        now = datetime.now(timezone.utc)
        if hasattr(dt_val, "tzinfo") and dt_val.tzinfo is None:
            dt_val = dt_val.replace(tzinfo=timezone.utc)
        return max(0, int((now - dt_val).total_seconds()))
    except Exception:
        return 0

# ── Auto-advance: if a DB row has been in "preparing" long enough, push it ──
def _auto_advance_orders(orders: list):
    """
    Server-side auto-advance:
      preparing  →  ready      after prep_time minutes
      ready      →  dispatched after 2 minutes
    We store status_updated_at in DB; compare against it here.
    """
    if not _RE_OK: return
    db = _RE["_get_db"](st.session_state.get("tenant_id", "default"))
    for o in orders:
        status  = o.get("status")
        oid     = o.get("order_id", "")
        updated = o.get("status_updated_at") or o.get("created_at")
        elapsed = _seconds_since(updated)

        # prep_time in minutes → get max across items
        prep_secs = max((i.get("prep_time", 20) for i in o.get("items", [])), default=20) * 60

        if status == "preparing" and elapsed >= prep_secs:
            db["orders"].update_one(
                {"order_id": oid},
                {"$set": {"status": "ready", "status_updated_at": datetime.now(timezone.utc)}},
            )
        elif status == "ready" and elapsed >= 120:   # 2 minutes
            db["orders"].update_one(
                {"order_id": oid},
                {"$set": {"status": "dispatched", "status_updated_at": datetime.now(timezone.utc)}},
            )
        elif status == "dispatched" and elapsed >= 600:  # 10 minutes delivery time
            db["orders"].update_one(
                {"order_id": oid},
                {"$set": {"status": "delivered", "status_updated_at": datetime.now(timezone.utc)}},
            )

# ══════════════════════════════════════════════════════════════════════════════
#  TAB: LIVE ORDERS
# ══════════════════════════════════════════════════════════════════════════════
if tab == "orders":
    import streamlit.components.v1 as _components
    import json as _json

    st.markdown("<div class='sec-hdr'>📋  LIVE ORDERS  ·  FIFO queue · live timers</div>",
                unsafe_allow_html=True)

    if not _RE_OK:
        st.error(f"Report engine error: {_RE}"); st.stop()

    # Auto-advance: fetch ALL active including dispatched (for delivered transition)
    if _RE_OK:
        try:
            _db_all_active = list(
                _RE["_get_db"](st.session_state.get("tenant_id", "default"))["orders"]
                .find({"status": {"$in": ["received","preparing","ready","dispatched"]}}, {"_id":0})
                .sort("created_at", 1)
            )
            _auto_advance_orders(_db_all_active)
        except Exception:
            pass
    pending = _db_fetch_pending_sorted()   # received / preparing / ready only

    received  = sum(1 for o in pending if o.get("status") == "received")
    preparing = sum(1 for o in pending if o.get("status") == "preparing")
    ready_cnt = sum(1 for o in pending if o.get("status") == "ready")

    col_ref, _ = st.columns([1, 7])
    with col_ref:
        if st.button("🔄 Refresh", use_container_width=True, key="ord_refresh"): st.rerun()

    st.markdown(f"""
    <div class="kpi-row">
      <div class="kpi-box"><div class="kpi-lbl">Total</div><div class="kpi-num sv-blue">{len(pending)}</div></div>
      <div class="kpi-box"><div class="kpi-lbl">📥 New</div><div class="kpi-num sv-yellow">{received}</div></div>
      <div class="kpi-box"><div class="kpi-lbl">👨‍🍳 Prep</div><div class="kpi-num sv-purple">{preparing}</div></div>
      <div class="kpi-box"><div class="kpi-lbl">✅ Ready</div><div class="kpi-num sv-green">{ready_cnt}</div></div>
    </div>""", unsafe_allow_html=True)

    if not pending:
        st.markdown("<div style='color:#2d3563;font-size:14px;padding:40px 0;text-align:center;'>✅ Queue khali hai.</div>", unsafe_allow_html=True)
    else:
        STATUS_BORDER = {"received":"#1e40af","preparing":"#92400e","ready":"#065f46","dispatched":"#5b21b6"}
        STATUS_BG     = {"received":"#05091a","preparing":"#0d0603","ready":"#020f07","dispatched":"#07040f"}
        STATUS_EMOJI  = {"received":"📥","preparing":"👨‍🍳","ready":"✅","dispatched":"🚗"}

        # Build timer data for JS (display only — no clicks)
        timer_data = []
        for o in pending:
            oid       = o.get("order_id","?")
            status    = o.get("status","received")
            items_list= o.get("items",[])
            prep_secs = max((i.get("prep_time",20) for i in items_list), default=20) * 60
            upd       = o.get("status_updated_at") or o.get("created_at")
            elapsed   = _seconds_since(upd)
            if status == "preparing":    remaining = max(0, prep_secs - elapsed)
            elif status == "ready":      remaining = max(0, 60 - elapsed)
            elif status == "dispatched": remaining = max(0, 300 - elapsed)
            else:                        remaining = 0
            timer_data.append({"oid":oid,"status":status,"remaining":remaining,
                                "prep_secs":prep_secs,"ready_secs":60,"disp_secs":300})

        timer_json = _json.dumps(timer_data)

        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

        # ── Per-order cards with embedded live timer ─────────────────────────
        for idx, o in enumerate(pending):
            oid        = o.get("order_id","?")
            status     = o.get("status","received")
            items_list = o.get("items",[])
            items_s    = " · ".join(
                "%dx %s" % (i.get('qty',1), i.get('name','').title()) for i in items_list)
            total      = o.get("total_amount",0)
            name       = (o.get("customer_name") or "Mehman").title()
            phone      = (o.get("customer_phone") or "—")
            addr       = (o.get("customer_address") or "—")
            payment    = (o.get("payment_method") or "cash").title()
            notes      = o.get("notes","") or ""
            created    = o.get("created_at","")
            created_ts = created.strftime("%H:%M") if hasattr(created,"strftime") else str(created)[:5]
            wait_mins  = int(_seconds_since(o.get("created_at")) / 60)
            prep_mins  = max((i.get("prep_time",20) for i in items_list), default=20)
            prep_secs  = prep_mins * 60

            bc  = STATUS_BORDER.get(status,"#1a1e32")
            bgc = STATUS_BG.get(status,"#0d1025")
            sem = STATUS_EMOJI.get(status,"")

            upd     = o.get("status_updated_at") or o.get("created_at")
            elapsed = _seconds_since(upd)
            if   status == "preparing":   remaining = max(0, prep_secs - elapsed)
            elif status == "ready":       remaining = max(0, 60 - elapsed)
            elif status == "dispatched":  remaining = max(0, 300 - elapsed)
            else:                         remaining = 0

            if   status == "preparing":   phase_total = prep_secs
            elif status == "ready":       phase_total = 60
            elif status == "dispatched":  phase_total = 300
            else:                         phase_total = 1

            pct_done = round(min(100, (1 - remaining/phase_total)*100) if phase_total > 0 else 0, 1)
            wait_txt = (" · ⏳%dm" % wait_mins) if wait_mins else ""
            notes_html = ("<div style='margin-top:6px;font-size:11px;color:#4c5ee8;'>📝 %s</div>" % html.escape(notes)) if notes else ""

            # ── Compact info card (HTML) ───────────────────────────────────
            st.markdown(
                "<div style='background:%s;border:1px solid %s;border-radius:10px 10px 0 0;"
                "padding:10px 14px 10px;border-bottom:none;'>"
                "<div style='display:flex;align-items:center;gap:8px;margin-bottom:8px;'>"
                "<span style='font-family:JetBrains Mono,monospace;font-size:12px;font-weight:700;color:#7b8cf0;'>#%s</span>"
                "<span style='font-size:10px;font-family:JetBrains Mono,monospace;padding:1px 8px;border-radius:12px;"
                "background:%s;border:1px solid %s;color:#e8ecff;'>%s %s</span>"
                "<span style='margin-left:auto;font-size:11px;color:#374151;font-family:JetBrains Mono,monospace;'>%s%s</span>"
                "</div>"
                "<div style='display:grid;grid-template-columns:1fr 1fr;gap:3px 16px;font-size:12px;'>"
                "<div><span style='color:#4c5ee8;'>🛒</span> <span style='color:#c5ccf5;'>%s</span></div>"
                "<div><span style='color:#4c5ee8;'>👤</span> <span style='color:#c5ccf5;'>%s</span></div>"
                "<div><span style='color:#fbbf24;font-weight:600;'>Rs %s</span>"
                "<span style='color:#374151;'> · </span><span style='color:#c5ccf5;'>%s</span>"
                "<span style='color:#374151;'> · </span><span style='color:#c5ccf5;'>⏱%dmin</span></div>"
                "<div><span style='color:#4c5ee8;'>📱</span> <span style='color:#c5ccf5;'>%s</span>"
                "<span style='color:#374151;'> · </span><span style='color:#4c5ee8;'>📍</span>"
                "<span style='color:#c5ccf5;'> %s</span></div>"
                "</div>%s</div>" % (
                    bgc, bc, oid, bgc, bc, sem, status.upper(),
                    created_ts, wait_txt,
                    html.escape(items_s), html.escape(name),
                    f"{total:,.0f}", payment, prep_mins,
                    html.escape(phone), html.escape(addr), notes_html
                ), unsafe_allow_html=True)

            # ── Animated status bar with embedded JS timer ─────────────────
            prep_active  = (status == "preparing")
            ready_active = (status == "ready")
            disp_active  = (status == "dispatched")
            done         = (status == "delivered")

            # Button styles
            def bstyle(active, past):
                if active: return {"bg":"#1c0a00","color":"#fbbf24","border":"#92400e","anim":"py"} if status=="preparing" else ({"bg":"#052e20","color":"#34d399","border":"#065f46","anim":"pg"} if status=="ready" else {"bg":"#1a0d2e","color":"#a78bfa","border":"#5b21b6","anim":"pp"})
                if past:   return {"bg":"#070910","color":"#1e2240","border":"#13162a","anim":""}
                return      {"bg":"#0a0c18","color":"#2d3563","border":"#13162a","anim":""}

            # Delivered cell: bright red when order is delivered
            if done:
                dvs = {"bg":"#1c0505","color":"#f87171","border":"#7f1d1d","anim":"pdv"}
            else:
                dvs = {"bg":"#0a0c18","color":"#374151","border":"#13162a","anim":""}

            ps  = bstyle(prep_active,  status in ("ready","dispatched","delivered"))
            rs  = bstyle(ready_active, status in ("dispatched","delivered"))
            ds  = bstyle(disp_active,  status == "delivered")
            dvs = bstyle(done,         False)

            timer_id = "t%s%d" % (oid.replace("-",""), idx)
            rem_m = remaining // 60
            rem_s = remaining % 60
            timer_txt = "%02d:%02d" % (rem_m, rem_s)

            def prog_pct(which_active, which_past, pct):
                if which_active: return str(pct) + "%"
                if which_past:   return "100%"
                return "0%"

            if prep_active:    active_prog = "pp" + timer_id
            elif ready_active: active_prog = "rp" + timer_id
            elif disp_active:  active_prog = "dp" + timer_id
            else:              active_prog = ""

            # Labels — NO spinner, timer only on active non-dispatch cells
            prep_lbl  = ('👨‍🍳 <span id="tm%s">%s</span>' % (timer_id, timer_txt)) if prep_active  else "👨‍🍳 Preparing"
            ready_lbl = ('✅ <span id="rm%s">%s</span>'   % (timer_id, timer_txt)) if ready_active else "✅ Ready"
            # Dispatch: show timer span only if time remaining > 0; hide it when expired
            if disp_active:
                disp_lbl = '🚗 <span id="dm%s">%s</span>' % (timer_id, timer_txt)
            else:
                disp_lbl = "🚗 Dispatch"

            # JS: countdown + progress bar + dispatch-done behaviour
            timer_js = ""
            if status in ("preparing", "ready"):
                # Simple countdown + progress bar, no end-state needed
                active_el = ("tm" if prep_active else "rm") + timer_id
                timer_js = (
                    "<script>var R%(id)s=%(rem)d,T%(id)s=%(tot)d;"
                    "setInterval(function(){"
                    "if(R%(id)s>0)R%(id)s--;"
                    "var m=Math.floor(R%(id)s/60),s=R%(id)s%%60;"
                    "var t=document.getElementById('%(el)s');"
                    "if(t)t.textContent=(m<10?'0':'')+m+':'+(s<10?'0':'')+s;"
                    "var p=Math.min(100,(1-R%(id)s/T%(id)s)*100);"
                    "var b=document.getElementById('%(prog)s');"
                    "if(b)b.style.width=p.toFixed(1)+'%%';"
                    "},1000);</script>"
                ) % {"id": timer_id, "rem": remaining, "tot": phase_total,
                     "el": active_el, "prog": active_prog}

            elif disp_active:
                # Dispatch: when timer hits 0 → hide timer span, stop glow on dispatch cell,
                # start glow on delivered cell
                timer_js = (
                    "<script>var R%(id)s=%(rem)d,T%(id)s=%(tot)d;"
                    "var _iv%(id)s=setInterval(function(){"
                    "  if(R%(id)s>0){R%(id)s--;}"
                    "  else{"
                    "    clearInterval(_iv%(id)s);"
                    "    var sp=document.getElementById('dm%(id)s');"
                    "    if(sp){sp.style.display='none';}"
                    "    var dc=document.getElementById('dcell%(id)s');"
                    "    if(dc){dc.style.animation='none';}"
                    "    var dv=document.getElementById('dvcell%(id)s');"
                    "    if(dv){dv.style.animation='pdv 1.5s infinite';}"
                    "    return;"
                    "  }"
                    "  var m=Math.floor(R%(id)s/60),s=R%(id)s%%60;"
                    "  var t=document.getElementById('dm%(id)s');"
                    "  if(t)t.textContent=(m<10?'0':'')+m+':'+(s<10?'0':'')+s;"
                    "  var p=Math.min(100,(1-R%(id)s/T%(id)s)*100);"
                    "  var b=document.getElementById('%(prog)s');"
                    "  if(b)b.style.width=p.toFixed(1)+'%%';"
                    "},1000);</script>"
                ) % {"id": timer_id, "rem": remaining, "tot": phase_total,
                     "prog": active_prog}

            # Delivered cell style: if dispatch just finished (remaining==0), start glowing
            dv_extra_anim = "animation:pdv 1.5s infinite;" if (disp_active and remaining == 0) else ""
            dc_anim = ("animation:%s 2s infinite;" % ds["anim"]) if ds["anim"] else ""

            html_widget = (
                "<style>"
                "@keyframes py{0%%,100%%{box-shadow:0 0 0 0 rgba(251,191,36,.4);}50%%{box-shadow:0 0 8px 4px rgba(251,191,36,.12);}}"
                "@keyframes pg{0%%,100%%{box-shadow:0 0 0 0 rgba(52,211,153,.4);}50%%{box-shadow:0 0 8px 4px rgba(52,211,153,.12);}}"
                "@keyframes pp{0%%,100%%{box-shadow:0 0 0 0 rgba(167,139,250,.4);}50%%{box-shadow:0 0 8px 4px rgba(167,139,250,.12);}}"
                "@keyframes pdv{0%%,100%%{box-shadow:0 0 0 0 rgba(248,113,113,.6);}50%%{box-shadow:0 0 10px 5px rgba(248,113,113,.2);}}"
                ".bcell{flex:1;display:flex;flex-direction:column;border-right:1px solid #13162a;}"
                ".bcell:last-child{border-right:none;}"
                ".blbl{padding:9px 4px 7px;text-align:center;font-size:13px;display:flex;align-items:center;"
                "justify-content:center;gap:4px;font-family:Outfit,sans-serif;font-weight:500;}"
                ".pbar{height:3px;}"
                "</style>"
                "<div style='display:flex;border:1px solid %s;border-top:none;border-radius:0 0 10px 10px;overflow:hidden;'>"
                # PREPARING
                "<div class='bcell'>"
                "<div class='blbl' style='background:%s;color:%s;%s'>%s</div>"
                "<div class='pbar' id='pp%s' style='background:linear-gradient(90deg,#92400e,#fbbf24);width:%s'></div>"
                "</div>"
                # READY
                "<div class='bcell'>"
                "<div class='blbl' style='background:%s;color:%s;%s'>%s</div>"
                "<div class='pbar' id='rp%s' style='background:linear-gradient(90deg,#065f46,#34d399);width:%s'></div>"
                "</div>"
                # DISPATCH — id on cell for JS to kill animation
                "<div class='bcell' id='dcell%s'>"
                "<div class='blbl' style='background:%s;color:%s;%s'>%s</div>"
                "<div class='pbar' id='dp%s' style='background:linear-gradient(90deg,#5b21b6,#a78bfa);width:%s'></div>"
                "</div>"
                # DELIVERED — id on cell for JS to start animation
                "<div class='bcell' id='dvcell%s'>"
                "<div class='blbl' style='background:%s;color:%s;%s'>✓ Delivered</div>"
                "<div class='pbar' style='background:#2d3563;width:%s'></div>"
                "</div>"
                "</div>"
                "%s"
            ) % (
                bc,
                ps["bg"], ps["color"],
                ("animation:%s 2s infinite;" % ps["anim"]) if ps["anim"] else "",
                prep_lbl,
                timer_id, prog_pct(prep_active, status in ("ready","dispatched","delivered"), pct_done),
                rs["bg"], rs["color"],
                ("animation:%s 2s infinite;" % rs["anim"]) if rs["anim"] else "",
                ready_lbl,
                timer_id, prog_pct(ready_active, status in ("dispatched","delivered"), pct_done),
                timer_id,
                ds["bg"], ds["color"], dc_anim,
                disp_lbl,
                timer_id, prog_pct(disp_active, status == "delivered", pct_done),
                timer_id,
                dvs["bg"], dvs["color"], dv_extra_anim,
                "100%" if done else "0%",
                timer_js,
            )

            _components.html(html_widget, height=50)

            # ── Real Streamlit buttons for actual DB updates ───────────────
            b1, b2, b3, b4 = st.columns([1,1,1,1])
            with b1:
                if st.button("▶ Start Prep", key="prep_%s" % oid,
                             disabled=status != "received", use_container_width=False):
                    if _db_update_order_status(oid, "preparing"): st.rerun()
            

            st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  TAB: ORDER HISTORY
# ══════════════════════════════════════════════════════════════════════════════
elif tab == "history":
    st.markdown("<div class='sec-hdr'>📜  ORDER HISTORY  ·  search & filter</div>", unsafe_allow_html=True)
    if not _RE_OK:
        st.error(f"Report engine error: {_RE}"); st.stop()

    fc1,fc2,fc3 = st.columns([2,2,1])
    with fc1: search = st.text_input("🔍 Search", key="order_search_inp", placeholder="PKT-XXXX or name or phone")
    with fc2: status_filter = st.selectbox("Status", ["all","received","preparing","ready","dispatched","delivered","cancelled"])
    with fc3: limit = st.selectbox("Show", [20,50,100], index=0)

    if st.button("🔄 Refresh", use_container_width=False): st.rerun()

    all_orders = _RE["fetch_recent_orders"](limit)
    filtered   = all_orders
    if status_filter != "all":
        filtered = [o for o in filtered if o.get("status") == status_filter]
    if search.strip():
        s = search.strip().lower()
        filtered = [o for o in filtered if
                    s in (o.get("order_id") or "").lower() or
                    s in (o.get("customer_name") or "").lower() or
                    s in (o.get("customer_phone") or "").lower()]

    st.markdown(f"<div style='font-size:12px;color:#4c5ee8;margin-bottom:12px;'>{len(filtered)} orders</div>", unsafe_allow_html=True)

    if not filtered:
        st.markdown("<div style='color:#2d3563;padding:20px 0;'>Koi order nahi mila.</div>", unsafe_allow_html=True)
    else:
        rows_html = "".join(f"""
        <tr>
          <td style='font-family:JetBrains Mono,monospace;color:#4c5ee8;'>{o.get('order_id','?')}</td>
          <td>{(o.get('customer_name') or 'Mehman').title()}</td>
          <td style='color:#6b7280;'>{o.get('customer_phone','—')}</td>
          <td>{", ".join(f"{i.get('qty',1)}x {i.get('name','').title()}" for i in o.get('items',[]))}</td>
          <td style='color:#fbbf24;'>Rs {o.get('total_amount',0):,.0f}</td>
          <td><span class='order-status {STATUS_CSS.get(o.get("status","received"),"s-received")}'>
            {STATUS_EMOJI.get(o.get("status","received"),"")} {o.get("status","?").title()}
          </span></td>
          <td style='color:#2d3563;font-family:JetBrains Mono,monospace;font-size:11px;'>
            {o.get('created_at','').strftime('%d %b %H:%M') if hasattr(o.get('created_at',''),'strftime') else str(o.get('created_at',''))[:16]}
          </td>
        </tr>""" for o in filtered)
        st.markdown(f"""
        <table class='data-tbl'>
          <thead><tr><th>Order ID</th><th>Customer</th><th>Phone</th>
          <th>Items</th><th>Total</th><th>Status</th><th>Time</th></tr></thead>
          <tbody>{rows_html}</tbody>
        </table>""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  TAB: MENU MANAGEMENT  (FIXED — direct DB for toggle/delete)
# ══════════════════════════════════════════════════════════════════════════════
elif tab == "menu":
    st.markdown("<div class='sec-hdr'>🍛  MENU MANAGEMENT  ·  add · edit · toggle · delete</div>", unsafe_allow_html=True)

    # ── Add item form ──────────────────────────────────────────────────────────
    with st.expander("➕ Naya Item Add Karein", expanded=False):
        with st.form("menu_form"):
            c1,c2 = st.columns(2)
            with c1:
                item_name   = st.text_input("Item Name (lowercase) *", placeholder="e.g. mutton karahi")
                category    = st.selectbox("Category", ["main course","starter","side","drink","dessert"])
                price       = st.number_input("Price (Rs)", min_value=0, value=200, step=10)
            with c2:
                description = st.text_input("Description", placeholder="Short description")
                prep_time   = st.number_input("Prep Time (min)", min_value=1, value=20)
                available   = st.checkbox("Available", value=True)
            sub_menu = st.form_submit_button("💾 Add Item", use_container_width=True)

        if sub_menu and item_name.strip():
            if _RE_OK:
                try:
                    db   = _RE["_get_db"](st.session_state.get("tenant_id", "default"))
                    name = item_name.lower().strip()
                    if db["menu"].find_one({"name": name}):
                        # Update existing
                        db["menu"].update_one({"name": name}, {"$set": {
                            "category": category, "price": price,
                            "description": description, "prep_time": prep_time, "available": available,
                        }})
                        st.success(f"✅ '{name}' update ho gaya!")
                    else:
                        db["menu"].insert_one({
                            "name": name, "category": category, "price": price,
                            "description": description, "prep_time": prep_time, "available": available,
                        })
                        st.success(f"✅ '{name}' menu mein add ho gaya!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

    # ── Category filter ────────────────────────────────────────────────────────
    all_items  = _db_fetch_menu_all()
    cats_all   = sorted({it.get("category","other") for it in all_items})
    show_avail = st.checkbox("Sirf available items dikhao", value=False)
    cat_filter = st.selectbox("Category filter", ["all"] + cats_all, key="cat_f")

    display_items = all_items
    if show_avail:   display_items = [i for i in display_items if i.get("available")]
    if cat_filter != "all": display_items = [i for i in display_items if i.get("category") == cat_filter]

    total_items = len(display_items)
    avail_count = sum(1 for i in display_items if i.get("available"))
    st.markdown(f"<div style='font-size:12px;color:#4c5ee8;margin:8px 0;'>"
                f"{total_items} items &nbsp;·&nbsp; <span style='color:#34d399;'>{avail_count} available</span>"
                f" &nbsp;·&nbsp; <span style='color:#f87171;'>{total_items - avail_count} disabled</span></div>",
                unsafe_allow_html=True)

    # ── Group by category ──────────────────────────────────────────────────────
    cats = {}
    for it in display_items:
        cats.setdefault(it.get("category","other"), []).append(it)

    EMOJI_MAP = {"main course":"🍛","starter":"🥙","side":"🫓","drink":"🥤","dessert":"🍮"}

    for cat, items in cats.items():
        st.markdown(
            f"<div style='font-size:10px;color:#4c5ee8;font-family:JetBrains Mono,monospace;"
            f"letter-spacing:.1em;margin:16px 0 8px;'>{EMOJI_MAP.get(cat,'🍴')}  {cat.upper()} ({len(items)})</div>",
            unsafe_allow_html=True,
        )
        for item in items:
            iname  = item.get("name","")
            pr     = item.get("price",0)
            avail  = item.get("available", True)
            pt     = item.get("prep_time",0)
            desc   = item.get("description","")
            key_s  = f"{iname}_{cat}"

            c1,c2,c3,c4,c5 = st.columns([3,1,1,1,1])
            with c1:
                av_badge = "✅" if avail else "❌"
                col_txt  = "#e8ecff" if avail else "#6b7280"
                st.markdown(
                    f"<div style='font-size:13px;color:{col_txt};padding-top:8px;'>"
                    f"{av_badge} <strong>{iname.title()}</strong>"
                    f"<span style='font-size:11px;color:#2d3563;margin-left:8px;'>{pt} min · {desc[:45]}</span>"
                    f"</div>", unsafe_allow_html=True,
                )
            with c2:
                st.markdown(f"<div style='font-size:14px;color:#fbbf24;padding-top:8px;'>Rs {pr:,.0f}</div>", unsafe_allow_html=True)
            with c3:
                # Inline price update
                new_p = st.number_input("", min_value=0, value=int(pr), step=10,
                                        key=f"p_{key_s}", label_visibility="collapsed")
                if new_p != pr:
                    if st.button("💾", key=f"savep_{key_s}", use_container_width=True, help="Save new price"):
                        if _db_update_menu(iname, {"price": new_p}):
                            st.success("✅ Price updated!")
                        else:
                            st.error("Price update nahi ho saka.")
                        st.rerun()
            with c4:
                # Toggle available — DIRECT DB
                tog_lbl = "🔴 Disable" if avail else "🟢 Enable"
                if st.button(tog_lbl, key=f"tog_{key_s}", use_container_width=True):
                    ok = _db_update_menu(iname, {"available": not avail})
                    if ok:
                        st.success(f"✅ '{iname.title()}' {'disabled' if avail else 'enabled'}!")
                    else:
                        st.error("Update nahi ho saka.")
                    st.rerun()
            with c5:
                # Delete — DIRECT DB
                if st.button("🗑️ Del", key=f"del_{key_s}", use_container_width=True, help="Delete permanently"):
                    ok = _db_delete_menu(iname)
                    if ok:
                        st.success(f"✅ '{iname.title()}' delete ho gaya!")
                    else:
                        st.error("Delete nahi ho saka.")
                    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
#  TAB: OFFERS MANAGEMENT  (FIXED — direct DB, items shown properly)
# ══════════════════════════════════════════════════════════════════════════════
elif tab == "offers":
    st.markdown("<div class='sec-hdr'>🎉  OFFERS & DEALS  ·  create and manage promotions</div>", unsafe_allow_html=True)

    # ── Load all menu items for the items multi-select ─────────────────────────
    menu_names = [it["name"].title() for it in _db_fetch_menu_all()]

    # ── Add offer form ─────────────────────────────────────────────────────────
    with st.expander("➕ Naya Offer / Deal Add Karein", expanded=False):
        with st.form("offer_form"):
            c1,c2 = st.columns(2)
            with c1:
                o_title       = st.text_input("Offer Title *", placeholder="e.g. Friday Special")
                o_description = st.text_input("Description *", placeholder="e.g. Biryani ke saath Raita free")
                o_discount    = st.number_input("Discount % (0 = none)", min_value=0, max_value=100, value=0)
            with c2:
                o_deal_price  = st.number_input("Deal Price Rs (0 = none)", min_value=0, value=0, step=10)
                o_valid_until = st.text_input("Valid Until (optional)", placeholder="e.g. 31 Dec 2025")
                # Multi-select from actual menu items
                o_items       = st.multiselect("Items Included (menu se select karein)", options=menu_names,
                                               placeholder="Menu items chunein...",
                                               help="Is deal mein kaunse menu items shamil hain")
            if o_items:
                st.caption(f"✅ Selected items: {chr(44).join(i.lower() for i in o_items)}")
            sub_offer = st.form_submit_button("💾 Add Offer", use_container_width=True)

        if sub_offer and o_title.strip():
            # Ensure items is truly the multiselect result (not title leaking in)
            clean_items = [i.lower().strip() for i in o_items
                           if i.lower().strip() != o_title.lower().strip()]
            doc = {
                "title":       o_title.strip(),
                "description": o_description.strip(),
                "active":      True,
                "created_at":  datetime.now(timezone.utc),
                "items":       clean_items,
            }
            if o_discount > 0:   doc["discount_pct"] = float(o_discount)
            if o_deal_price > 0: doc["deal_price"]   = float(o_deal_price)
            if o_valid_until.strip(): doc["valid_until"] = o_valid_until.strip()

            if _db_insert_offer(doc):
                st.success(f"✅ Offer '{o_title}' add ho gaya! Items: {', '.join(clean_items) if clean_items else 'none selected'}")
                st.rerun()
            else:
                st.error("Offer save nahi ho saka.")

    # ── Load & display offers ──────────────────────────────────────────────────
    offers          = _db_fetch_offers()
    active_offers   = [o for o in offers if o.get("active", True)]
    inactive_offers = [o for o in offers if not o.get("active", True)]

    # ── Active offers ──────────────────────────────────────────────────────────
    st.markdown(f"<div style='font-size:13px;color:#34d399;margin:16px 0 10px;'>🟢 Active Offers ({len(active_offers)})</div>",
                unsafe_allow_html=True)
    if not active_offers:
        st.markdown("<div style='color:#2d3563;font-size:13px;'>Koi active offer nahi hai.</div>", unsafe_allow_html=True)

    for idx, o in enumerate(active_offers):
        o_title_display = o.get("title","Untitled")
        o_items_list    = o.get("items", [])
        items_display   = ", ".join(i.title() for i in o_items_list) if o_items_list else "—"

        with st.expander(f"🔥 {o_title_display.upper()}  ·  {(o.get('description') or '')[:55]}"):
            d1,d2 = st.columns(2)
            with d1:
                st.markdown(f"**📝 Description:** {o.get('description','')}")
                if o.get("discount_pct"): st.markdown(f"**💰 Discount:** {o['discount_pct']}% OFF")
                if o.get("deal_price"):   st.markdown(f"**💰 Deal Price:** Rs {o['deal_price']:,.0f}")
                # ✅ FIX: items now shown from direct DB field
                st.markdown(f"**🍛 Items Included:** {items_display}")
            with d2:
                if o.get("valid_until"): st.markdown(f"**⏰ Valid Until:** {o['valid_until']}")
                created = o.get("created_at","")
                if hasattr(created,"strftime"):
                    st.markdown(f"**📅 Created:** {created.strftime('%d %b %Y')}")

            btn_col1, btn_col2 = st.columns([1,3])
            with btn_col1:
                # ✅ FIX: direct DB update, not staff_chat
                if st.button("🔴 Disable", key=f"dis_{o_title_display}_{idx}", use_container_width=True):
                    if _db_update_offer(o_title_display, {"active": False}):
                        st.success(f"✅ '{o_title_display}' disabled!")
                    else:
                        st.error("Disable nahi ho saka.")
                    st.rerun()

    # ── Inactive offers ────────────────────────────────────────────────────────
    if inactive_offers:
        st.markdown(f"<div style='font-size:13px;color:#6b7280;margin:16px 0 10px;'>🔴 Inactive Offers ({len(inactive_offers)})</div>",
                    unsafe_allow_html=True)
        for idx, o in enumerate(inactive_offers):
            o_title_display = o.get("title","Untitled")
            o_items_list    = o.get("items",[])
            items_display   = ", ".join(i.title() for i in o_items_list) if o_items_list else "—"

            with st.expander(f"💤 {o_title_display.upper()}  ·  {o.get('description','')[:55]}"):
                st.markdown(f"**📝 Description:** {o.get('description','')}")
                st.markdown(f"**🍛 Items:** {items_display}")
                if o.get("discount_pct"): st.markdown(f"**💰 Discount:** {o['discount_pct']}%")
                if o.get("deal_price"):   st.markdown(f"**💰 Deal Price:** Rs {o['deal_price']:,.0f}")

                btn_col1, _ = st.columns([1,3])
                with btn_col1:
                    if st.button("🟢 Enable", key=f"en_{o_title_display}_{idx}", use_container_width=True):
                        if _db_update_offer(o_title_display, {"active": True}):
                            st.success(f"✅ '{o_title_display}' enabled!")
                        else:
                            st.error("Enable nahi ho saka.")
                        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
#  TAB: CUSTOMER FEEDBACK
# ══════════════════════════════════════════════════════════════════════════════
elif tab == "feedback":
    st.markdown("<div class='sec-hdr'>⭐  CUSTOMER FEEDBACK  ·  ratings & reviews</div>", unsafe_allow_html=True)

    # Prefer direct DB; fall back to API endpoint
    feedbacks = _db_fetch_feedback()
    if not feedbacks:
        fb_data, fb_code = _api("/feedback")
        feedbacks = fb_data.get("feedback", []) if fb_code == 200 else []

    col_ref2, _ = st.columns([1, 7])
    with col_ref2:
        if st.button("🔄 Refresh", use_container_width=True, key="fb_refresh"): st.rerun()

    if feedbacks:
        ratings    = [f.get("rating", 0) for f in feedbacks if f.get("rating")]
        avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0
        five_star  = sum(1 for r in ratings if r == 5)
        low_star   = sum(1 for r in ratings if r <= 2)

        st.markdown(f"""
        <div class="kpi-row">
          <div class="kpi-box"><div class="kpi-lbl">Total Reviews</div><div class="kpi-num sv-blue">{len(feedbacks)}</div></div>
          <div class="kpi-box"><div class="kpi-lbl">Avg Rating</div><div class="kpi-num sv-yellow">{avg_rating} ⭐</div></div>
          <div class="kpi-box"><div class="kpi-lbl">5-Star</div><div class="kpi-num sv-green">{five_star}</div></div>
          <div class="kpi-box"><div class="kpi-lbl">Low (≤2⭐)</div><div class="kpi-num sv-red">{low_star}</div></div>
        </div>""", unsafe_allow_html=True)

        try:
            import plotly.graph_objects as go
            rating_counts = [sum(1 for r in ratings if r == s) for s in [5, 4, 3, 2, 1]]
            fig_rat = go.Figure(go.Bar(
                x=rating_counts,
                y=["⭐⭐⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐", "⭐⭐", "⭐"],
                orientation="h",
                marker_color=["#34d399", "#60a5fa", "#fbbf24", "#fb923c", "#f87171"],
                text=rating_counts, textposition="outside",
            ))
            fig_rat.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#c5ccf5", size=12),
                margin=dict(l=10, r=10, t=10, b=10), height=200,
                xaxis=dict(showgrid=False, visible=False),
                yaxis=dict(showgrid=False),
                showlegend=False,
            )
            st.plotly_chart(fig_rat, use_container_width=True, config={"displayModeBar": False})
        except ImportError:
            pass

    fc1, fc2 = st.columns([2, 2])
    with fc1: rating_filter = st.selectbox("Filter by rating", ["all", "5 ⭐", "4 ⭐", "3 ⭐", "2 ⭐", "1 ⭐", "No rating"])
    with fc2: sort_fb = st.selectbox("Sort by", ["Newest first", "Oldest first", "Highest rating", "Lowest rating"])

    if not feedbacks:
        st.markdown(
            "<div style='text-align:center;padding:40px 0;color:#2d3563;font-size:14px;'>"
            "Abhi tak koi feedback nahi aaya.<br>"
            "<span style='font-size:12px;'>Customers chatbot se feedback de sakte hain.</span>"
            "</div>", unsafe_allow_html=True)
    else:
        show = list(feedbacks)

        if rating_filter == "No rating":
            show = [f for f in show if not f.get("rating")]
        elif rating_filter != "all":
            r_val = int(rating_filter[0])
            show = [f for f in show if f.get("rating") == r_val]

        if sort_fb == "Oldest first":
            show = list(reversed(show))
        elif sort_fb == "Highest rating":
            show = sorted(show, key=lambda f: f.get("rating", 0) or 0, reverse=True)
        elif sort_fb == "Lowest rating":
            show = sorted(show, key=lambda f: f.get("rating", 0) or 0)

        st.markdown(f"<div style='font-size:12px;color:#4c5ee8;margin-bottom:12px;'>{len(show)} reviews</div>",
                    unsafe_allow_html=True)

        for fi, fb in enumerate(show):
            rating   = fb.get("rating", 0) or 0
            stars    = _stars(rating)
            # ✅ Field is "message" (new schema) — fallback to old field names
            comment  = (fb.get("message") or fb.get("comment") or fb.get("text") or fb.get("feedback") or "—").strip()
            cname    = (fb.get("customer_name") or fb.get("name") or "Anonymous").title()
            cphone   = fb.get("customer_phone") or fb.get("phone") or ""
            order_id = fb.get("order_id") or ""
            ts       = fb.get("created_at") or ""
            ts_str   = ts.strftime("%d %b %Y, %H:%M") if hasattr(ts, "strftime") else str(ts)[:16] if ts else ""

            border_col = "#065f46" if rating >= 4 else ("#7f1d1d" if 0 < rating <= 2 else "#1a1e32")
            st.markdown(f"""
            <div class="fb-card" style="border-color:{border_col};">
              <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;">
                <div style="color:#fbbf24;font-size:18px;">{stars if rating else "☆☆☆☆☆"}</div>
                {f'<div style="font-size:11px;color:#4c5ee8;font-family:JetBrains Mono,monospace;">{rating}/5</div>' if rating else ''}
              </div>
              <div style="font-size:14px;color:#c5ccf5;line-height:1.6;background:#080a14;border-radius:8px;padding:10px 14px;margin-bottom:8px;">
                {html.escape(comment)}
              </div>
              <div style="font-size:11px;color:#2d3563;font-family:JetBrains Mono,monospace;line-height:2;">
                👤 {html.escape(cname)}
                {f"  📱 {html.escape(cphone)}" if cphone else ""}
                {f"  📋 #{html.escape(order_id)}" if order_id else ""}
                {f"  🕐 {ts_str}" if ts_str else ""}
              </div>
            </div>""", unsafe_allow_html=True)

            if st.button(f"🗑️ Delete", key=f"fb_del_{fi}_{cname}_{ts_str}"):
                if _db_delete_feedback(fb.get("customer_name"), fb.get("created_at")):
                    st.success("✅ Feedback delete ho gaya.")
                    st.rerun()
                else:
                    st.error("Delete nahi ho saka.")


# ══════════════════════════════════════════════════════════════════════════════
#  TAB: ANALYTICS — FULL RICH DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
elif tab == "analytics":
    st.markdown("<div class='sec-hdr'>📊  ANALYTICS DASHBOARD  ·  revenue · orders · trends · insights</div>", unsafe_allow_html=True)

    if not _RE_OK:
        st.error(f"Report engine load nahi ho saka: {_RE}"); st.stop()

    try:
        import plotly.graph_objects as go
        import plotly.express as px
        import pandas as pd
        _PLOTLY = True
    except ImportError:
        _PLOTLY = False
        st.warning("⚠️ Plotly install nahi hai. `pip install plotly` karein zyada charts ke liye.")

    # ── Period picker ──────────────────────────────────────────────────────────
    period = st.radio("Report Period:", ["📅 Aaj", "📆 Is Hafta (7 din)", "🗓️ Is Mahine"],
                      horizontal=True, key="analytics_period")

    col_gen, _ = st.columns([1,5])
    with col_gen:
        gen_btn = st.button("📊 Report Banao", use_container_width=True, key="gen_report")

    if gen_btn or st.session_state.get("_report_loaded"):
        st.session_state["_report_loaded"] = True

        with st.spinner("Data load ho raha hai..."):
            from datetime import datetime, timezone, timedelta

            def _now_utc(): return datetime.now(timezone.utc)
            def _ts():      n=_now_utc(); return n.replace(hour=0,minute=0,second=0,microsecond=0)
            def _te():      n=_now_utc(); return n.replace(hour=23,minute=59,second=59,microsecond=999999)
            def _ws():      return (_now_utc()-timedelta(days=7)).replace(hour=0,minute=0,second=0,microsecond=0)
            def _ms():      n=_now_utc(); return n.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
            # Previous period for comparison
            def _prev_ts(): n=_now_utc()-timedelta(days=1); return n.replace(hour=0,minute=0,second=0,microsecond=0)
            def _prev_ws(): return (_now_utc()-timedelta(days=14)).replace(hour=0,minute=0,second=0,microsecond=0)
            def _prev_ms(): n=_now_utc(); lm=n.replace(day=1)-timedelta(days=1); return lm.replace(day=1,hour=0,minute=0,second=0,microsecond=0)

            if "Aaj" in period:
                ts, te       = _ts(), _te()
                prev_ts, prev_te = _prev_ts(), _ts()
                period_label = datetime.now().strftime("%d %B %Y")
                period_days  = 1
            elif "Hafta" in period:
                ts, te       = _ws(), _te()
                prev_ts, prev_te = _prev_ws(), _ws()
                period_label = f"Pichle 7 din — {datetime.now().strftime('%d %b %Y')}"
                period_days  = 7
            else:
                ts, te       = _ms(), _te()
                prev_ts, prev_te = _prev_ms(), _ms()
                period_label = datetime.now().strftime("%B %Y")
                period_days  = 30

            fe = _RE
            summary      = fe["fetch_order_summary"](ts, te)
            prev_summary = fe["fetch_order_summary"](prev_ts, prev_te)
            breakdown    = fe["fetch_status_breakdown"](ts, te)
            top_items    = fe["fetch_top_items"](ts, te, limit=10)
            hourly       = fe["fetch_hourly_orders"](ts, te)
            daily_rev    = _db_fetch_daily_revenue(days=max(period_days*2, 14))
            cat_rev      = _db_fetch_category_revenue(ts, te)
            pay_bkdn     = _db_fetch_payment_breakdown(ts, te)

        # ── Header ─────────────────────────────────────────────────────────────
        st.markdown(
            f"<div style='font-size:13px;color:#4c5ee8;font-family:JetBrains Mono,monospace;"
            f"margin-bottom:16px;'>📅 PERIOD: {period_label}</div>",
            unsafe_allow_html=True
        )

        # ── KPI Scorecards with delta ───────────────────────────────────────────
        tot_ord  = (summary or {}).get("total_orders", 0) or 0
        tot_rev  = (summary or {}).get("total_revenue", 0) or 0
        avg_ord  = (summary or {}).get("avg_order", 0) or 0
        prev_ord = (prev_summary or {}).get("total_orders", 0) or 0
        prev_rev = (prev_summary or {}).get("total_revenue", 0) or 0
        prev_avg = (prev_summary or {}).get("avg_order", 0) or 0

        def _delta_html(curr, prev, prefix=""):
            if prev == 0: return ""
            pct = ((curr - prev) / prev) * 100
            arrow = "▲" if pct >= 0 else "▼"
            col   = "#34d399" if pct >= 0 else "#f87171"
            return f"<div style='font-size:11px;color:{col};margin-top:4px;'>{arrow} {abs(pct):.1f}% prev period</div>"

        cancelled_count = breakdown.get("cancelled", 0)
        delivered_count = breakdown.get("delivered", 0) + breakdown.get("dispatched", 0)

        st.markdown(f"""
        <div class="kpi-row">
          <div class="kpi-box">
            <div class="kpi-lbl">Total Orders</div>
            <div class="kpi-num sv-blue">{tot_ord:,}</div>
            {_delta_html(tot_ord, prev_ord)}
          </div>
          <div class="kpi-box">
            <div class="kpi-lbl">Total Revenue</div>
            <div class="kpi-num sv-green">Rs {tot_rev:,.0f}</div>
            {_delta_html(tot_rev, prev_rev)}
          </div>
          <div class="kpi-box">
            <div class="kpi-lbl">Avg Order Value</div>
            <div class="kpi-num sv-yellow">Rs {avg_ord:,.0f}</div>
            {_delta_html(avg_ord, prev_avg)}
          </div>
          <div class="kpi-box">
            <div class="kpi-lbl">Delivered / Dispatched</div>
            <div class="kpi-num sv-purple">{delivered_count:,}</div>
          </div>
          <div class="kpi-box">
            <div class="kpi-lbl">Cancelled</div>
            <div class="kpi-num sv-red">{cancelled_count:,}</div>
          </div>
        </div>""", unsafe_allow_html=True)

        if not _PLOTLY:
            # ── Fallback text tables ───────────────────────────────────────────
            if top_items:
                st.markdown("### 🏆 Top Items")
                rows = "".join(f"<tr><td style='color:#4c5ee8;'>{i+1}</td><td style='color:#e8ecff;font-weight:600;'>{(it.get('_id') or '').title()}</td><td style='color:#a78bfa;'>{it.get('total_qty',0)} units</td><td style='color:#fbbf24;'>Rs {it.get('revenue',0):,.0f}</td></tr>" for i,it in enumerate(top_items))
                st.markdown(f"<table class='data-tbl'><thead><tr><th>#</th><th>Item</th><th>Qty</th><th>Revenue</th></tr></thead><tbody>{rows}</tbody></table>", unsafe_allow_html=True)
        else:
            # ══════════════════════════════════════════════════════════════════
            #  PLOTLY CHARTS
            # ══════════════════════════════════════════════════════════════════

            CHART_LAYOUT = dict(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#c5ccf5", size=12),
                margin=dict(l=10,r=10,t=40,b=10),
                legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#c5ccf5")),
                xaxis=dict(gridcolor="#1a1e32", showgrid=True, zeroline=False),
                # yaxis NOT here — each chart sets its own to avoid duplicate-kwarg conflict
            )
            _Y = dict(gridcolor="#1a1e32", showgrid=True, zeroline=False)  # default yaxis

            # ── Row 1: Revenue trend + Status pie ─────────────────────────────
            row1_l, row1_r = st.columns([3,2])

            with row1_l:
                st.markdown("<div class='chart-title'>📈 REVENUE TREND (last 30 days)</div>", unsafe_allow_html=True)
                if daily_rev:
                    df_dr = pd.DataFrame(daily_rev).rename(columns={"_id":"Date","revenue":"Revenue","orders":"Orders"})
                    fig_rev = go.Figure()
                    fig_rev.add_trace(go.Scatter(
                        x=df_dr["Date"], y=df_dr["Revenue"],
                        mode="lines+markers",
                        line=dict(color="#4c5ee8", width=2),
                        marker=dict(color="#60a5fa", size=5),
                        fill="tozeroy", fillcolor="rgba(76,94,232,0.12)",
                        name="Revenue",
                    ))
                    fig_rev.add_trace(go.Bar(
                        x=df_dr["Date"], y=df_dr["Orders"],
                        name="Orders", marker_color="rgba(167,139,250,0.3)",
                        yaxis="y2",
                    ))
                    fig_rev.update_layout(
                        **CHART_LAYOUT, height=280,
                        title=dict(text="", x=0),
                        yaxis=dict(title="Revenue (Rs)", gridcolor="#1a1e32", zeroline=False,
                                   title_font=dict(color="#60a5fa"), tickfont=dict(color="#60a5fa")),
                        yaxis2=dict(overlaying="y", side="right", showgrid=False,
                                    title="Orders", gridcolor="#1a1e32", zeroline=False,
                                    title_font=dict(color="#a78bfa"), tickfont=dict(color="#a78bfa")),
                        hovermode="x unified",
                    )
                    st.plotly_chart(fig_rev, use_container_width=True, config={"displayModeBar": False})
                else:
                    st.info("Revenue data nahi mili.")

            with row1_r:
                st.markdown("<div class='chart-title'>🥧 ORDER STATUS BREAKDOWN</div>", unsafe_allow_html=True)
                if breakdown:
                    STATUS_COLORS = {
                        "received":"#60a5fa","preparing":"#fbbf24","ready":"#34d399",
                        "dispatched":"#a78bfa","delivered":"#800757","cancelled":"#f87171",
                    }
                    labels = list(breakdown.keys())
                    values = list(breakdown.values())
                    colors = [STATUS_COLORS.get(l,"#4c5ee8") for l in labels]
                    fig_pie = go.Figure(go.Pie(
                        labels=[f"{STATUS_EMOJI.get(l,'')} {l.title()}" for l in labels],
                        values=values, hole=0.52,
                        marker=dict(colors=colors, line=dict(color="#08090f", width=2)),
                        textinfo="percent+label", textfont_size=11,
                    ))
                    fig_pie.update_layout(**{**CHART_LAYOUT, "height":280, "showlegend":False,
                                             "margin":dict(l=0,r=0,t=20,b=0)})
                    st.plotly_chart(fig_pie, use_container_width=True, config={"displayModeBar": False})
                else:
                    st.info("Status data nahi mili.")

            # ── Row 2: Top items bar + Hourly heatmap ──────────────────────────
            row2_l, row2_r = st.columns([2,3])

            with row2_l:
                st.markdown("<div class='chart-title'>🏆 TOP SELLING ITEMS</div>", unsafe_allow_html=True)
                if top_items:
                    df_ti  = pd.DataFrame(top_items).rename(columns={"_id":"Item","total_qty":"Qty","revenue":"Revenue"})
                    df_ti["Item"] = df_ti["Item"].str.title()
                    df_ti  = df_ti.sort_values("Qty")
                    fig_ti = go.Figure(go.Bar(
                        y=df_ti["Item"], x=df_ti["Qty"],
                        orientation="h",
                        marker=dict(
                            color=df_ti["Qty"],
                            colorscale=[[0,"#1a1e32"],[0.5,"#4c5ee8"],[1,"#60a5fa"]],
                            showscale=False,
                        ),
                        text=df_ti["Qty"], textposition="outside",
                        hovertemplate="<b>%{y}</b><br>Qty: %{x}<br>Revenue: Rs %{customdata:,.0f}<extra></extra>",
                        customdata=df_ti["Revenue"],
                    ))
                    fig_ti.update_layout(**CHART_LAYOUT, height=max(280, len(top_items)*35))
                    fig_ti.update_xaxes(showgrid=False, visible=False)
                    fig_ti.update_yaxes(showgrid=False, tickfont=dict(size=12))
                    st.plotly_chart(fig_ti, use_container_width=True, config={"displayModeBar": False})
                else:
                    st.info("Top items data nahi mili.")

            with row2_r:
                st.markdown("<div class='chart-title'>⏰ HOURLY ORDERS & REVENUE</div>", unsafe_allow_html=True)
                if hourly:
                    df_h = pd.DataFrame(hourly).rename(columns={"_id":"Hour","orders":"Orders","revenue":"Revenue"})
                    # Fill missing hours with 0
                    all_hours = list(range(0,24))
                    hour_map  = {row["Hour"]: row for _,row in df_h.iterrows()}
                    df_full   = pd.DataFrame([
                        {"Hour":h, "Orders":hour_map[h]["Orders"] if h in hour_map else 0,
                         "Revenue":hour_map[h]["Revenue"] if h in hour_map else 0}
                        for h in all_hours
                    ])
                    df_full["Label"] = df_full["Hour"].apply(lambda h: f"{h:02d}:00")

                    fig_h = go.Figure()
                    fig_h.add_trace(go.Bar(
                        x=df_full["Label"], y=df_full["Orders"],
                        name="Orders", marker_color="#4c5ee8",
                        hovertemplate="<b>%{x}</b><br>Orders: %{y}<extra></extra>",
                    ))
                    fig_h.add_trace(go.Scatter(
                        x=df_full["Label"], y=df_full["Revenue"],
                        name="Revenue (Rs)", mode="lines+markers",
                        line=dict(color="#fbbf24", width=2),
                        marker=dict(size=5),
                        yaxis="y2",
                        hovertemplate="<b>%{x}</b><br>Revenue: Rs %{y:,.0f}<extra></extra>",
                    ))
                    fig_h.update_layout(
                        **{**CHART_LAYOUT,
                           "legend": dict(orientation="h", y=1.08,
                                         bgcolor="rgba(0,0,0,0)", font=dict(color="#c5ccf5"))},
                        height=300,
                        yaxis=dict(title="Orders", gridcolor="#1a1e32", zeroline=False,
                                   title_font=dict(color="#60a5fa"), tickfont=dict(color="#60a5fa")),
                        yaxis2=dict(overlaying="y", side="right", showgrid=False,
                                    title="Revenue (Rs)", zeroline=False,
                                    title_font=dict(color="#fbbf24"), tickfont=dict(color="#fbbf24")),
                        barmode="group", hovermode="x unified",
                    )
                    st.plotly_chart(fig_h, use_container_width=True, config={"displayModeBar": False})

                    # Peak hour insight
                    if not df_full.empty:
                        peak_row = df_full.loc[df_full["Orders"].idxmax()]
                        if peak_row["Orders"] > 0:
                            st.markdown(
                                f"<div style='font-size:12px;color:#34d399;font-family:JetBrains Mono,monospace;"
                                f"margin-top:6px;'>🔥 Peak hour: {peak_row['Label']} — {int(peak_row['Orders'])} orders</div>",
                                unsafe_allow_html=True
                            )
                else:
                    st.info("Hourly data nahi mila.")

            # ── Row 3: Category revenue + Payment methods ──────────────────────
            row3_l, row3_r = st.columns([1,1])

            with row3_l:
                st.markdown("<div class='chart-title'>🍽️ REVENUE BY CATEGORY</div>", unsafe_allow_html=True)
                if cat_rev:
                    df_cat = pd.DataFrame(cat_rev).rename(columns={"_id":"Category","revenue":"Revenue","qty":"Qty"})
                    df_cat["Category"] = df_cat["Category"].str.title()
                    CAT_COLORS = ["#4c5ee8","#34d399","#fbbf24","#a78bfa","#f87171","#22d3ee"]
                    fig_cat = go.Figure(go.Bar(
                        x=df_cat["Category"], y=df_cat["Revenue"],
                        marker_color=CAT_COLORS[:len(df_cat)],
                        text=[f"Rs {r:,.0f}" for r in df_cat["Revenue"]],
                        textposition="outside",
                    ))
                    fig_cat.update_layout(**CHART_LAYOUT, height=260)
                    fig_cat.update_xaxes(showgrid=False)
                    fig_cat.update_yaxes(showgrid=True, gridcolor="#1a1e32", visible=False)
                    st.plotly_chart(fig_cat, use_container_width=True, config={"displayModeBar": False})
                else:
                    st.info("Category data nahi mila.")

            with row3_r:
                st.markdown("<div class='chart-title'>💳 PAYMENT METHODS</div>", unsafe_allow_html=True)
                if pay_bkdn:
                    PAY_LABELS = {"cash":"Cash","easypaisa":"EasyPaisa","jazzcash":"JazzCash","card":"Card"}
                    PAY_COLORS = ["#4c5ee8","#34d399","#fbbf24","#a78bfa"]
                    df_pay = pd.DataFrame(pay_bkdn).rename(columns={"_id":"Method","count":"Orders","revenue":"Revenue"})
                    df_pay["Method"] = df_pay["Method"].apply(lambda x: PAY_LABELS.get(str(x).lower(), str(x).title()))
                    fig_pay = go.Figure(go.Pie(
                        labels=df_pay["Method"], values=df_pay["Orders"],
                        hole=0.45,
                        marker=dict(colors=PAY_COLORS[:len(df_pay)], line=dict(color="#08090f",width=2)),
                        textinfo="percent+label", textfont_size=11,
                    ))
                    fig_pay.update_layout(**{**CHART_LAYOUT,"height":260,"showlegend":False,
                                            "margin":dict(l=0,r=0,t=20,b=0)})
                    st.plotly_chart(fig_pay, use_container_width=True, config={"displayModeBar": False})
                else:
                    st.info("Payment data nahi mila.")

            # ── Revenue vs orders top items table ─────────────────────────────
            if top_items:
                st.markdown("<div class='chart-title' style='margin-top:16px;'>📋 TOP ITEMS — DETAILED TABLE</div>",
                            unsafe_allow_html=True)
                total_rev_items = sum(it.get("revenue",0) for it in top_items) or 1
                rows_html = "".join(f"""
                <tr>
                  <td style='font-family:JetBrains Mono,monospace;color:#4c5ee8;text-align:center;'>{i+1}</td>
                  <td style='color:#e8ecff;font-weight:600;'>{(it.get('_id') or '').title()}</td>
                  <td style='color:#a78bfa;text-align:center;'>{it.get('total_qty',0):,}</td>
                  <td style='color:#fbbf24;text-align:right;'>Rs {it.get('revenue',0):,.0f}</td>
                  <td style='text-align:center;'>
                    <div style='background:#1a1e32;border-radius:4px;height:6px;width:100%;'>
                      <div style='background:#4c5ee8;border-radius:4px;height:6px;width:{min(100,it.get("revenue",0)/total_rev_items*100):.1f}%;'></div>
                    </div>
                  </td>
                  <td style='color:#34d399;text-align:center;'>{it.get("revenue",0)/total_rev_items*100:.1f}%</td>
                </tr>""" for i, it in enumerate(top_items))
                st.markdown(f"""
                <table class='data-tbl'>
                  <thead><tr>
                    <th style='text-align:center;'>#</th>
                    <th>Item</th>
                    <th style='text-align:center;'>Qty Sold</th>
                    <th style='text-align:right;'>Revenue</th>
                    <th>Share</th>
                    <th style='text-align:center;'>%</th>
                  </tr></thead>
                  <tbody>{rows_html}</tbody>
                </table>""", unsafe_allow_html=True)

        # ── Business insights ──────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("<div class='chart-title'>💡 BUSINESS INSIGHTS</div>", unsafe_allow_html=True)

        insights = []
        if tot_ord > 0:
            cancel_rate = cancelled_count / (tot_ord) * 100
            if cancel_rate > 15:
                insights.append(f"⚠️  Cancellation rate zyada hai: **{cancel_rate:.1f}%** — wajah check karein.")
            elif cancel_rate < 5:
                insights.append(f"✅ Cancellation rate bohat achha hai: **{cancel_rate:.1f}%**")

            if avg_ord > 0 and prev_avg > 0:
                aov_change = ((avg_ord - prev_avg) / prev_avg) * 100
                if aov_change > 10:
                    insights.append(f"📈 Avg order value **{aov_change:.1f}%** up hai — upselling kaam kar raha hai!")
                elif aov_change < -10:
                    insights.append(f"📉 Avg order value **{abs(aov_change):.1f}%** down hai — combo deals try karein.")

        if top_items:
            top1 = (top_items[0].get("_id") or "").title()
            insights.append(f"🏆 Best seller: **{top1}** — yeh hamesha available rakhein.")

        if hourly:
            peak_h = max(hourly, key=lambda h: h.get("orders",0))
            insights.append(f"⏰ Peak time **{int(peak_h['_id']):02d}:00 — {int(peak_h['_id'])+1:02d}:00** — is waqt staff zyada rakhen.")

        if not insights:
            insights.append("📊 Zyada data ke liye orders badhate rahein.")

        for ins in insights:
            st.markdown(f"<div style='background:#0d1025;border:1px solid #1a1e32;border-radius:8px;"
                        f"padding:10px 16px;font-size:13px;color:#c5ccf5;margin-bottom:8px;'>{ins}</div>",
                        unsafe_allow_html=True)

    else:
        st.markdown(
            "<div style='text-align:center;padding:48px 0;color:#2d3563;font-size:14px;'>"
            "📊 'Report Banao' button dabaein report dekhne ke liye.</div>",
            unsafe_allow_html=True
        )


# ══════════════════════════════════════════════════════════════════════════════
#  TAB: AI CHAT
# ══════════════════════════════════════════════════════════════════════════════
elif tab == "chat":
    st.markdown("<div class='sec-hdr'>💬  AI ASSISTANT  ·  staff chat with PakOrderBot</div>", unsafe_allow_html=True)

    st.markdown("""
    <div style='background:#0d1025;border:1px solid #1a1e32;border-radius:10px;padding:10px 16px;
        margin-bottom:16px;font-size:12px;color:#4c5ee8;line-height:1.8;'>
      💡 <strong>Quick commands:</strong><br>
      "aaj ke orders dikhao" &nbsp;·&nbsp; "chicken biryani ki price 400 karo" &nbsp;·&nbsp;
      "PKT-XXXX dispatched kar do" &nbsp;·&nbsp; "is hafte ke top items" &nbsp;·&nbsp;
      "seekh kebab band karo" &nbsp;·&nbsp; "naya offer: Friday special, 20% off"
    </div>""", unsafe_allow_html=True)

    if not st.session_state.staff_msgs:
        st.markdown("<div style='text-align:center;padding:30px 0;color:#2d3563;font-size:14px;'>Staff assistant tayar hai.</div>", unsafe_allow_html=True)
    else:
        for msg in st.session_state.staff_msgs:
            role   = msg["role"]
            cont   = msg["content"]
            t      = msg.get("time","")
            is_err = msg.get("is_error",False)
            if role == "user":
                st.markdown(
                    f"<div style='display:flex;justify-content:flex-end;padding:4px 0;'>"
                    f"<div><div class='user-sbubble'>{esc(cont)}</div>"
                    f"<div class='smeta' style='text-align:right;'>{t}</div></div></div>",
                    unsafe_allow_html=True,
                )
            else:
                ec = " err-bubble" if is_err else ""
                st.markdown(
                    f"<div style='display:flex;padding:4px 0;'>"
                    f"<div><div class='staff-bubble{ec}'>{esc(cont)}</div>"
                    f"<div class='smeta'>{t}</div></div></div>",
                    unsafe_allow_html=True,
                )

    with st.form("staff_chat_form", clear_on_submit=True):
        ic,bc = st.columns([9,1])
        with ic: user_input = st.text_input("q", placeholder="Staff query likhein...", label_visibility="collapsed")
        with bc: sent = st.form_submit_button("↑", use_container_width=True)

    if sent and user_input and user_input.strip():
        msg = user_input.strip()
        add_msg("user", msg)
        with st.spinner("..."):
            result = staff_chat(msg)
        if "error" in result:
            add_msg("bot", result["error"], is_error=True)
        else:
            add_msg("bot", result.get("reply","Jawab nahi mila."))
        st.rerun()

    if st.button("🗑️ Clear Chat", key="clear_staff_chat"):
        st.session_state.staff_msgs = []
        st.rerun()