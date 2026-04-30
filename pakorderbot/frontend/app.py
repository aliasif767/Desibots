"""
PakOrderBot — Customer Chat Interface
Run: cd frontend && streamlit run app.py
"""
import streamlit as st
import streamlit.components.v1 as components
import requests, html, re, os, time, json
from datetime import datetime

st.set_page_config(page_title="PakOrderBot", page_icon="🍛", layout="wide",
                   initial_sidebar_state="expanded")

try:    _DEFAULT_API = st.secrets["API_URL"]
except: _DEFAULT_API = os.getenv("API_URL", "http://127.0.0.1:8512")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&family=Outfit:wght@300;400;500;600&display=swap');
html,body,[class*="css"]{font-family:'Outfit',sans-serif;}
#MainMenu,footer,header{visibility:hidden;}
.stApp{background:#0a0f0d;}
section[data-testid="stSidebar"]{background:#0d1410 !important;border-right:1px solid #1a2e22;}
.user-msg{display:flex;justify-content:flex-end;padding:4px 0;}
.bot-msg{display:flex;justify-content:flex-start;padding:4px 0;}
.user-bubble{background:#1a2e1a;border:1px solid #2d6a2d;border-radius:18px 18px 4px 18px;
  padding:10px 16px;max-width:72%;color:#d4f0d4;font-size:14px;line-height:1.6;word-break:break-word;white-space:pre-wrap;}
.bot-bubble{background:#111c14;border:1px solid #1a2e22;border-radius:18px 18px 18px 4px;
  padding:10px 16px;max-width:80%;color:#f0f5f0;font-size:14px;line-height:1.6;word-break:break-word;white-space:pre-wrap;}
.bot-bubble.err{background:#1c0a0a;border-color:#7f1d1d;color:#fca5a5;}
.msg-meta{font-size:11px;color:#2d4a2d;margin-top:3px;font-family:'JetBrains Mono',monospace;padding:0 4px;}
.user-meta{text-align:right;}
.badge{display:inline-block;font-family:'JetBrains Mono',monospace;font-size:10px;padding:2px 8px;border-radius:20px;margin-top:4px;}
.b-order{background:#052e20;color:#34d399;border:1px solid #065f46;}
.b-menu{background:#1c1408;color:#fbbf24;border:1px solid #92400e;}
.b-track{background:#0c1a2e;color:#60a5fa;border:1px solid #1e40af;}
.b-conv{background:#1a1a2e;color:#a78bfa;border:1px solid #4c1d95;}
.stTextInput>div>div>input{background:#111c14 !important;border:1px solid #1a2e22 !important;
  color:#f0f5f0 !important;border-radius:12px !important;font-size:14px !important;padding:10px 16px !important;}
.stTextInput>div>div>input:focus{border-color:#2d6a2d !important;}
.stButton>button{background:#111c14 !important;border:1px solid #1a2e22 !important;
  color:#6b9e6b !important;border-radius:10px !important;font-size:13px !important;transition:all 0.15s !important;}
.stButton>button:hover{border-color:#34d399 !important;color:#34d399 !important;background:#052e20 !important;}
hr{border-color:#1a2e22 !important;}
::-webkit-scrollbar{width:3px;}
::-webkit-scrollbar-thumb{background:#1a2e22;border-radius:2px;}
</style>""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────
for k, v in [
    ("messages",      []),
    ("history",       []),
    ("conv_stage",    ""),
    ("order_draft",   {}),
    ("api_url",       _DEFAULT_API),
    ("pending_msg",   None),
    ("total",         0),
    ("orders_placed", 0),
    ("live_orders",   []),
    ("show_tracker",  False),
    ("is_loading",    False),
]:
    if k not in st.session_state:
        st.session_state[k] = v

# ── Helpers ───────────────────────────────────────────────────────────────────
def strip_html(t): return re.sub(r'<[^>]*>', '', str(t)).strip()
def esc(t):        return html.escape(strip_html(str(t))).replace('\n', '<br>')

def health():
    try: return requests.get(f"{st.session_state.api_url}/health", timeout=3).status_code == 200
    except: return False

def call_api(msg):
    try:
        r = requests.post(
            f"{st.session_state.api_url}/chat",
            json={"message": msg, "history": st.session_state.history,
                  "conv_stage": st.session_state.conv_stage,
                  "order_draft": st.session_state.order_draft},
            timeout=60)
        r.raise_for_status()
        data = r.json()
        st.session_state.conv_stage  = data.get("conv_stage", "")
        st.session_state.order_draft = data.get("order_draft", {})
        return data
    except requests.exceptions.ConnectionError:
        return {"error": f"Server offline ({st.session_state.api_url})"}
    except requests.exceptions.Timeout:
        return {"error": "Timeout — server ne 60s mein jawab nahi diya"}
    except Exception as e:
        try:    detail = r.json().get("detail", str(e))
        except: detail = str(e)
        return {"error": f"Kuch masla aaya: {detail}"}

def add_msg(role, content, intent="", is_error=False):
    clean = strip_html(content) if role == "bot" else content
    st.session_state.messages.append({
        "role": role, "content": clean,
        "time": datetime.now().strftime("%H:%M:%S"),
        "intent": intent, "is_error": is_error})
    if not is_error:
        st.session_state.history.append(
            {"role": "user" if role == "user" else "assistant", "content": clean})
    st.session_state.total += 1

def intent_badge(intent):
    m = {"order_place":("b-order","order"), "menu_read":("b-menu","menu"),
         "offers_read":("b-menu","offers"), "order_track":("b-track","track"),
         "order_cancel":("b-menu","cancel"), "conversation":("b-conv","chat"),
         "feedback_write":("b-track","feedback"), "popular_items":("b-menu","popular")}
    cls, lbl = m.get(intent, ("b-conv", intent or "chat"))
    return f'<span class="badge {cls}">{lbl}</span>'

def _parse_order(reply_text, api_result=None):
    """
    Extract order info from confirmed order reply.
    Times come from DB via polling — placed_at is stored but the tracker
    drives itself from real DB status_updated_at, not placed_at.
    """
    oid_m   = re.search(r'Order\s*ID\s*[:#\s]+#?(PKT-\w+)', reply_text, re.IGNORECASE)
    eta_m   = re.search(r'ETA\s*[~:\s]*~?\s*(\d+)\s*min', reply_text, re.IGNORECASE)
    total_m = re.search(r'TOTAL\s+Rs\s+([\d,]+)', reply_text, re.IGNORECASE)
    items = []
    for line in reply_text.splitlines():
        m = re.match(r'\s{1,6}(\d+)x\s+(.+?)\s{2,}Rs\s+[\d,]+', line)
        if m:
            items.append(f"{m.group(1)}x {re.sub(r'  +', ' ', m.group(2)).strip().title()}")
    if not oid_m:
        return None

    eta_total     = int(eta_m.group(1)) if eta_m else 30
    delivery_time = 10                           # fixed delivery leg
    prep_time     = max(5, eta_total - delivery_time)

    return {
        "order_id":      oid_m.group(1),
        "prep_time":     prep_time,       # cooking phase (minutes) — same as staff view
        "delivery_time": delivery_time,   # riding phase (minutes)  — same as staff view
        "eta_minutes":   eta_total,
        "items_str":     ", ".join(items) if items else "—",
        "total":         total_m.group(1) if total_m else "—",
        "placed_at":     time.time(),     # kept for fallback only
        "dismissed":     False,
        "db_status":     "received",      # will be updated by polling
        "status_ts":     None,            # when DB status last changed (unix float)
    }


def _poll_order_status(api_url: str, order_id: str) -> dict | None:
    """
    Poll /order-status/<order_id> and return
    {"status": "...", "status_ts": <unix float>} or None on failure.
    """
    try:
        r = requests.get(f"{api_url}/order-status/{order_id}", timeout=5)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def _make_tracker_html(orders_data, api_url=""):
    """
    DB-driven tracker widget.
    Polls /order-status/<id> every 10s to get real status + status_updated_at.
    Timer starts from status_updated_at in the DB — exactly when staff
    clicked Start Prep — matching the staff panel timers exactly.

    Status flow and durations (must match staff panel exactly):
      received   → waiting for staff action (no timer)
      preparing  → prep_time minutes (from menu item max)
      ready      → 2 minutes (auto-dispatched by staff panel)
      dispatched → delivery_time minutes (10 min fixed)
      delivered  → done
    """
    import json as _json
    orders_json = _json.dumps([
        {
            "order_id":      o["order_id"],
            "prep_time":     o.get("prep_time", 20),
            "delivery_time": o.get("delivery_time", 10),
            "eta_minutes":   o["eta_minutes"],
            "items_str":     o["items_str"],
            "total":         o["total"],
            "db_status":     o.get("db_status", "received"),
            "status_ts":     o.get("status_ts"),
        }
        for o in orders_data
    ])

    api_url_json = _json.dumps(api_url)
    POLL_MS = 10000

    js_code = (
        "const ORDERS = " + orders_json + ";\n"
        "const API_URL = " + api_url_json + ";\n"
        """
/* State per order */
const state = {};
ORDERS.forEach(o => {
  state[o.order_id] = {
    status:   o.db_status   || "received",
    statusTs: o.status_ts   || null,
    prepSec:  (o.prep_time  || 20) * 60,
    delivSec: (o.delivery_time || 10) * 60,
    eta:      o.eta_minutes || 30,
  };
});

function pad(n){ return String(Math.floor(Math.max(0,n))).padStart(2,'0'); }

/* Poll DB for real status */
function pollAll() {
  if (!API_URL) return;
  ORDERS.forEach(o => {
    fetch(API_URL + "/order-status/" + o.order_id)
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (!d) return;
        const s = state[o.order_id];
        if (d.status !== s.status || d.status_ts !== s.statusTs) {
          s.status   = d.status;
          s.statusTs = d.status_ts;
        }
      })
      .catch(() => {});
  });
}
pollAll();
""" + "setInterval(pollAll, " + str(POLL_MS) + ");\n" + """

function renderCard(o) {
  const s        = state[o.order_id];
  const status   = s.status;
  const nowSec   = Date.now() / 1000;
  const elapsed  = s.statusTs ? Math.max(0, nowSec - s.statusTs) : 0;

  let remaining = 0, phaseLabel = "", overallPct = 0, stage = "";
  const totalSec = s.prepSec + s.delivSec;

  if (status === "received") {
    stage      = "waiting";
    phaseLabel = "Restaurant confirm kar raha hai...";
    overallPct = 2;
    remaining  = s.eta * 60;   // show full ETA so customer knows wait time
  } else if (status === "preparing") {
    stage      = "preparing";
    remaining  = Math.max(0, s.prepSec - elapsed);
    overallPct = Math.min(99, (elapsed / totalSec) * 100);
    phaseLabel = "khana tayar ho raha hai";
  } else if (status === "ready") {
    stage      = "preparing";
    remaining  = Math.max(0, 120 - elapsed);
    overallPct = Math.min(99, (s.prepSec / totalSec) * 100);
    phaseLabel = "Khana ready! Dispatch ho raha hai...";
  } else if (status === "dispatched") {
    stage      = "onway";
    remaining  = Math.max(0, s.delivSec - elapsed);
    overallPct = Math.min(99, ((s.prepSec + elapsed) / totalSec) * 100);
    phaseLabel = "order raste mein hai!";
  } else {
    stage      = "delivered";
    remaining  = 0;
    overallPct = 100;
  }

  const rm = Math.floor(remaining / 60);
  const rs = Math.floor(remaining % 60);

  let vehLeft;
  if (status === "received" || status === "preparing" || status === "ready") {
    vehLeft = 10;
  } else if (status === "delivered") {
    vehLeft = 82;
  } else {
    const dPct = Math.min(100, (elapsed / s.delivSec) * 100);
    vehLeft = 10 + (dPct / 100) * 72;
  }

  const chefIcon   = "👨‍🍳";
  const scootIcon  = "🛵";
  const icon = (status === "dispatched") ? scootIcon : chefIcon;

  function pill(label, key) {
    let cls = "";
    if (stage === key) cls = "active";
    else if ((key==="preparing" && (stage==="onway"||stage==="delivered")) ||
             (key==="onway" && stage==="delivered")) cls = "donep";
    return '<span class="pill ' + cls + '">' + label + '</span>';
  }

  let body;
  if (status === "delivered") {
    body = '<div class="donetxt">Order Pahunch Gaya!</div>' +
           '<div class="donesub">Aapka khana deliver ho gaya. Maza karein!</div>';
  } else if (status === "received") {
    body = '<div class="countdown">' + pad(rm) + ':' + pad(rs) + '</div>' +
           '<div class="etalabel">' + phaseLabel + ' &middot; ~' + o.eta_minutes + ' min total</div>' +
           '<div class="progwrap"><div class="progfill" style="width:2%"></div></div>' +
           '<div class="road">' +
             '<div class="dashes"></div>' +
             '<span class="shopico">🏪</span>' +
             '<span class="veh" style="left:10%">' + chefIcon + '</span>' +
             '<span class="homeico">🏠</span>' +
           '</div>' +
           '<div class="pills">' +
             pill("Tayari Ho Raha","preparing") +
             pill("Raste Mein","onway") +
             pill("Pahunch Gaya","delivered") +
           '</div>';
  } else {
    body =
      '<div class="countdown">' + pad(rm) + ':' + pad(rs) + '</div>' +
      '<div class="etalabel">' + phaseLabel + ' &middot; ~' + o.eta_minutes + ' min total</div>' +
      '<div class="progwrap"><div class="progfill" style="width:' + overallPct.toFixed(1) + '%"></div></div>' +
      '<div class="road">' +
        '<div class="dashes"></div>' +
        '<span class="shopico">🏪</span>' +
        '<span class="veh" style="left:' + vehLeft.toFixed(1) + '%">' + icon + '</span>' +
        '<span class="homeico">🏠</span>' +
      '</div>' +
      '<div class="pills">' +
        pill("Tayari Ho Raha","preparing") +
        pill("Raste Mein","onway") +
        pill("Pahunch Gaya","delivered") +
      '</div>';
  }

  return '<div class="card' + (status==="delivered" ? " done" : "") + '">' +
    '<div class="oid">#' + o.order_id + '</div>' +
    '<div class="items">' + o.items_str + '</div>' +
    '<div class="tot">Rs ' + o.total + '</div>' +
    body + '</div>';
}

function tick() {
  document.getElementById("root").innerHTML = ORDERS.map(renderCard).join("");
}
tick();
setInterval(tick, 1000);
"""
    )

    html_out = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'><style>"
        "@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Outfit:wght@400;500&display=swap');"
        "*{box-sizing:border-box;margin:0;padding:0;}"
        "body{background:transparent;font-family:'Outfit',sans-serif;padding:2px 4px;}"
        "#root{display:flex;flex-wrap:wrap;gap:14px;}"
        ".card{background:#0d1a10;border:1px solid #1a3a20;border-radius:16px;padding:16px 18px;flex:1;min-width:220px;max-width:400px;}"
        ".card.done{background:#052e20;border-color:#065f46;}"
        ".oid{font-family:'JetBrains Mono',monospace;font-size:11px;color:#2d6a2d;letter-spacing:.1em;margin-bottom:3px;}"
        ".items{font-size:12px;color:#4a7a4a;margin-bottom:4px;line-height:1.6;}"
        ".tot{font-size:12px;color:#6b9e6b;margin-bottom:12px;}"
        ".countdown{font-family:'JetBrains Mono',monospace;font-size:34px;font-weight:600;color:#34d399;letter-spacing:.04em;}"
        ".etalabel{font-size:11px;color:#2d4a2d;margin-top:2px;margin-bottom:10px;}"
        ".waitlbl{font-size:13px;color:#4a7a4a;margin-bottom:12px;padding:8px 0;}"
        ".progwrap{height:5px;background:#1a3020;border-radius:3px;margin:10px 0 6px;overflow:hidden;}"
        ".progfill{height:100%;border-radius:3px;background:linear-gradient(90deg,#065f46,#34d399);transition:width 1s linear;}"
        ".road{background:#0a1a0c;border:1px solid #1a3020;border-radius:8px;height:44px;margin:12px 0 8px;position:relative;overflow:hidden;}"
        ".dashes{position:absolute;top:50%;left:0;right:0;height:2px;transform:translateY(-50%);"
        "background:repeating-linear-gradient(90deg,#2d4a2d 0,#2d4a2d 14px,transparent 14px,transparent 28px);}"
        ".shopico{position:absolute;left:6px;top:50%;transform:translateY(-50%);font-size:16px;}"
        ".homeico{position:absolute;right:6px;top:50%;transform:translateY(-50%);font-size:16px;}"
        ".veh{position:absolute;top:50%;transform:translateY(-50%);font-size:22px;transition:left 1s linear;line-height:1;}"
        ".pills{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px;}"
        ".pill{font-size:10px;font-family:'JetBrains Mono',monospace;padding:3px 10px;border-radius:20px;"
        "border:1px solid #1a3020;color:#2d4a2d;background:#0a1a0c;}"
        ".pill.active{border-color:#34d399;color:#34d399;background:#052e20;}"
        ".pill.donep{border-color:#065f46;color:#059669;background:#022c20;}"
        ".donetxt{font-size:15px;font-weight:600;color:#34d399;margin-bottom:6px;}"
        ".donesub{font-size:12px;color:#2d6a2d;}"
        "</style></head><body>"
        "<div id='root'></div>"
        "<script>" + js_code + "</script>"
        "</body></html>"
    )
    return html_out




# ── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("<div style='font-size:20px;font-weight:600;color:#f0f5f0;padding-bottom:4px;'>🍛 PakOrderBot</div>", unsafe_allow_html=True)
    st.markdown("<div style='font-size:12px;color:#2d4a2d;margin-bottom:10px;'>Customer Chat</div>", unsafe_allow_html=True)

    ok = health()
    status_txt = "● Online" if ok else "● Offline"
    dot_color  = "#34d399" if ok else "#f87171"
    st.markdown(f"<div style='font-size:12px;font-family:JetBrains Mono,monospace;color:{dot_color};margin-bottom:14px;'>{status_txt}</div>", unsafe_allow_html=True)

    if st.session_state.conv_stage:
        stage_labels = {
            "await_more":    "🛒 Cart review",
            "modifying":     "✏️ Modifying cart",
            "await_name":    "📝 Naam darj karein",
            "await_phone":   "📱 Phone darj karein",
            "await_address": "📍 Address darj karein",
            "await_confirm": "✅ Confirm karein",
        }
        lbl = stage_labels.get(st.session_state.conv_stage, st.session_state.conv_stage)
        st.markdown(f"<div style='background:#052e20;border:1px solid #2d6a2d;border-radius:8px;padding:6px 10px;font-size:12px;color:#34d399;margin-bottom:12px;'>{lbl}</div>", unsafe_allow_html=True)

    live_count = sum(1 for o in st.session_state.live_orders if not o.get("dismissed"))
    if live_count > 0:
        st.markdown("---")
        btn_lbl = f"🛵 Live Tracker  ({live_count} order{'s' if live_count > 1 else ''})"
        if st.button(btn_lbl, use_container_width=True):
            st.session_state.show_tracker = not st.session_state.show_tracker
            st.rerun()
        hint = "▲ tap to hide" if st.session_state.show_tracker else "▼ tap to show"
        st.markdown(f"<div style='font-size:10px;color:#2d6a2d;text-align:center;margin-top:-4px;'>{hint}</div>", unsafe_allow_html=True)

    

    st.markdown("<div style='font-size:11px;color:#2d4a2d;font-family:JetBrains Mono,monospace;letter-spacing:.08em;margin-bottom:8px;'>QUICK ACTIONS</div>", unsafe_allow_html=True)
    for lbl, pmsg in [("🍽️ Menu","menu dikhao"),("🎉 Offers","koi offers ya deals hain?"),("📋 Track","mera order track karo"),("⭐ Feedback","feedback dena chahta hoon")]:
        if st.button(lbl, use_container_width=True):
            st.session_state.pending_msg = pmsg; st.rerun()

    st.markdown("---")
    if st.button("🗑️ Clear Chat", use_container_width=True):
        for k in ("messages", "history", "live_orders"):
            st.session_state[k] = []
        st.session_state.conv_stage   = ""
        st.session_state.order_draft  = {}
        st.session_state.total        = 0
        st.session_state.show_tracker = False
        st.rerun()

    st.markdown(f"<div style='font-size:10px;color:#1a2e22;margin-top:8px;'>Messages: {st.session_state.total}</div>", unsafe_allow_html=True)


# ── LIVE TRACKER WIDGET ───────────────────────────────────────────────────────
active_orders = [o for o in st.session_state.live_orders if not o.get("dismissed")]

if active_orders and st.session_state.show_tracker:
    # Sync DB status into session state before rendering
    for i, o in enumerate(st.session_state.live_orders):
        if o.get("dismissed"): continue
        polled = _poll_order_status(st.session_state.api_url, o["order_id"])
        if polled:
            st.session_state.live_orders[i]["db_status"] = polled.get("status", o.get("db_status","received"))
            st.session_state.live_orders[i]["status_ts"] = polled.get("status_ts")
            # Auto-dismiss delivered orders after showing 30s
            if polled.get("status") == "delivered" and not o.get("deliver_noted"):
                st.session_state.live_orders[i]["deliver_noted"] = True

    # Re-read active orders with updated status
    active_orders = [o for o in st.session_state.live_orders if not o.get("dismissed")]
    tracker_html  = _make_tracker_html(active_orders, api_url=st.session_state.api_url)
    card_height   = 310 if len(active_orders) == 1 else 330
    components.html(tracker_html, height=card_height, scrolling=False)

    # Dismiss buttons
    dcols = st.columns(min(len(active_orders), 4))
    for ci, order in enumerate(active_orders):
        idx = next(i for i, o in enumerate(st.session_state.live_orders)
                   if o["order_id"] == order["order_id"])
        elapsed = (time.time() - order["placed_at"]) / 60.0
        with dcols[ci % len(dcols)]:
            if st.button(f"✕ #{order['order_id']}", key=f"dis_{idx}", use_container_width=True):
                st.session_state.live_orders[idx]["dismissed"] = True
                st.rerun()

    st.markdown("<hr style='border-color:#1a2e22;margin:14px 0;'>", unsafe_allow_html=True)


# ── CHAT AREA ─────────────────────────────────────────────────────────────────
st.markdown(
    "<div style='padding:8px 0 16px;border-bottom:1px solid #1a2e22;margin-bottom:16px;'>"
    "<span style='font-family:JetBrains Mono,monospace;font-size:12px;color:#2d4a2d;'>customer chat</span>"
    "</div>", unsafe_allow_html=True)

if not st.session_state.messages:
    st.markdown("""<div style='text-align:center;padding:40px 0;'>
        <div style='font-size:32px;margin-bottom:12px;'>🍛</div>
        <div style='font-size:18px;font-weight:500;color:#f0f5f0;margin-bottom:8px;'>PakOrderBot mein khush aamdeed!</div>
        <div style='font-size:14px;color:#2d4a2d;'>Menu: "menu dikhao"<br>Order: "2 chicken biryani order karo"<br>Deals: "koi offers hain?"</div>
    </div>""", unsafe_allow_html=True)

for msg in st.session_state.messages:
    role = msg["role"]; content = msg["content"]
    t = msg.get("time",""); intent = msg.get("intent",""); is_err = msg.get("is_error",False)
    if role == "user":
        st.markdown(
            f'<div class="user-msg"><div>'
            f'<div class="user-bubble">{esc(content)}</div>'
            f'<div class="msg-meta user-meta">{t}</div>'
            f'</div></div>', unsafe_allow_html=True)
    else:
        ec  = " err" if is_err else ""
        bdg = intent_badge(intent) if intent and not is_err else ""
        st.markdown(
            f'<div class="bot-msg"><div>'
            f'<div class="bot-bubble{ec}">{esc(content)}</div>'
            f'<div class="msg-meta">{t} {bdg}</div>'
            f'</div></div>', unsafe_allow_html=True)

# ── Input ─────────────────────────────────────────────────────────────────────
with st.form("chat_form", clear_on_submit=True):
    ic, bc = st.columns([9, 1])
    with ic:
        user_input = st.text_input("m", placeholder="Roman Urdu mein likhein...",
                                   label_visibility="collapsed")
    with bc:
        sent = st.form_submit_button("↑", use_container_width=True)

if st.session_state.pending_msg:
    user_input = st.session_state.pending_msg
    st.session_state.pending_msg = None
    sent = True

if sent and user_input and user_input.strip():
    msg = user_input.strip()
    add_msg("user", msg)
    st.session_state.is_loading = True
    with st.spinner("..."):
        result = call_api(msg)
    st.session_state.is_loading = False

    if "error" in result:
        add_msg("bot", result["error"], is_error=True)
    else:
        reply = result.get("reply", "Jawab nahi mila.")
        iobj  = result.get("intent", {})
        istr  = (iobj.get("tasks", [{}])[0].get("intent", "")
                 if isinstance(iobj, dict) and iobj.get("tasks") else "")

        # Detect confirmed order → register in tracker
        is_confirmed = (
            istr == "order_place"
            or "ORDER CONFIRMED" in reply.upper()
            or ("PKT-" in reply and "Order receive ho gaya" in reply)
        )
        if is_confirmed:
            st.session_state.orders_placed += 1
            entry = _parse_order(reply, result)
            if entry:
                existing = {o["order_id"] for o in st.session_state.live_orders}
                if entry["order_id"] not in existing:
                    st.session_state.live_orders.append(entry)
                    st.session_state.show_tracker = True  # auto-open

        add_msg("bot", reply, intent=istr)
    st.rerun()