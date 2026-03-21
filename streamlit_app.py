import streamlit as st
import requests
import html
import re
from datetime import datetime
from report_engine import build_daily_report, build_weekly_report, build_monthly_report, is_report_due, _fmt, _fmt_n

st.set_page_config(page_title="HisabBot", page_icon="🧾", layout="wide", initial_sidebar_state="expanded")

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&family=Outfit:wght@300;400;500;600&display=swap');
html,body,[class*="css"]{font-family:'Outfit',sans-serif;}
#MainMenu,footer,header{visibility:hidden;}
.stApp{background:#0a0c10;}
section[data-testid="stSidebar"]{background:#0f1218 !important;border-right:1px solid #1c2030;}

.user-msg{display:flex;justify-content:flex-end;padding:4px 0;}
.bot-msg {display:flex;justify-content:flex-start;padding:4px 0;}
.user-bubble{background:#1e1b4b;border:1px solid #4338ca;border-radius:18px 18px 4px 18px;
  padding:10px 16px;max-width:72%;color:#e0e7ff;font-size:14px;line-height:1.6;word-break:break-word;white-space:pre-wrap;}
.bot-bubble{background:#111827;border:1px solid #1f2937;border-radius:18px 18px 18px 4px;
  padding:10px 16px;max-width:72%;color:#f1f5f9;font-size:14px;line-height:1.6;word-break:break-word;white-space:pre-wrap;}
.bot-bubble.err{background:#1c0a0a;border-color:#7f1d1d;color:#fca5a5;}
.msg-meta{font-size:11px;color:#374151;margin-top:3px;font-family:'JetBrains Mono',monospace;padding:0 4px;}
.user-meta{text-align:right;}
.badge{display:inline-block;font-family:'JetBrains Mono',monospace;font-size:10px;padding:2px 8px;border-radius:20px;margin-top:4px;}
.bw{background:#1e1040;color:#a78bfa;border:1px solid #5b21b6;}
.br{background:#052e20;color:#34d399;border:1px solid #065f46;}
.bu{background:#1c1408;color:#fbbf24;border:1px solid #92400e;}
.stat-box{background:#0a0c10;border:1px solid #1c2030;border-radius:10px;padding:12px 14px;margin-bottom:8px;}
.stat-lbl{font-size:10px;color:#4b5563;font-family:'JetBrains Mono',monospace;letter-spacing:0.08em;}
.stat-num{font-size:22px;font-weight:600;margin-top:2px;}
.sg{color:#34d399;}.sp{color:#a78bfa;}.sb{color:#60a5fa;}
.debug-entry{background:#0a0c10;border-left:2px solid #1f2937;border-radius:0 6px 6px 0;
  padding:6px 10px;margin-bottom:5px;font-family:'JetBrains Mono',monospace;font-size:11px;color:#6b7280;}
.debug-preview{margin-top:2px;color:#4b5563;font-size:10px;}
hr{border-color:#1c2030 !important;}
.stTextInput>div>div>input{background:#111827 !important;border:1px solid #1f2937 !important;
  color:#f1f5f9 !important;border-radius:12px !important;font-size:14px !important;padding:10px 16px !important;}
.stTextInput>div>div>input:focus{border-color:#4338ca !important;}
.stTextInput>div>div>input::placeholder{color:#4b5563 !important;}
.stButton>button{background:#111827 !important;border:1px solid #1f2937 !important;
  color:#9ca3af !important;border-radius:10px !important;font-size:13px !important;transition:all 0.15s !important;}
.stButton>button:hover{border-color:#34d399 !important;color:#34d399 !important;background:#052e20 !important;}

/* Report styles */
.report-card{background:#0f1218;border:1px solid #1c2030;border-radius:12px;padding:20px 24px;margin-bottom:16px;}
.report-header{font-size:13px;font-family:'JetBrains Mono',monospace;color:#4b5563;letter-spacing:0.08em;margin-bottom:12px;}
.report-title{font-size:20px;font-weight:600;color:#f1f5f9;margin-bottom:4px;}
.report-sub{font-size:12px;color:#4b5563;margin-bottom:16px;}
.section-hd{font-size:11px;font-family:'JetBrains Mono',monospace;color:#34d399;letter-spacing:0.1em;
  margin:18px 0 8px;padding-bottom:4px;border-bottom:1px solid #1c2030;}
.report-body{font-size:14px;color:#d1d5db;line-height:1.8;white-space:pre-wrap;}
.coming-soon{text-align:center;padding:50px 20px;}
.cs-icon{font-size:48px;margin-bottom:16px;}
.cs-title{font-size:18px;font-weight:600;color:#f1f5f9;margin-bottom:8px;}
.cs-msg{font-size:14px;color:#4b5563;margin-bottom:12px;}
.cs-time{font-size:13px;color:#34d399;font-family:'JetBrains Mono',monospace;}
.tip-box{background:#0a1a12;border:1px solid #065f46;border-radius:8px;padding:12px 16px;margin-top:12px;}
.tip-hd{font-size:10px;color:#34d399;font-family:'JetBrains Mono',monospace;letter-spacing:0.08em;margin-bottom:6px;}
.tip-text{font-size:13px;color:#9ca3af;line-height:1.7;}
::-webkit-scrollbar{width:3px;}
::-webkit-scrollbar-thumb{background:#1c2030;border-radius:2px;}
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────
for k, v in [("messages",[]),("total",0),("writes",0),("reads",0),
              ("api_url","http://127.0.0.1:8000"),("status",None),("pending",None),
              ("page","chat"),("report_data",None),("report_type",None)]:
    if k not in st.session_state:
        st.session_state[k] = v

# ── Helpers ───────────────────────────────────────────────────────────────────
def strip_html(t):
    s = str(t)
    s = re.sub(r'<[^>]*>', '', s)
    s = re.sub(r'</\w+>', '', s)
    return s.strip()

def esc(t):
    s = strip_html(str(t))
    s = html.escape(s)
    s = s.replace('\n', '<br>')
    return s

def call_api(msg):
    try:
        r = requests.post(f"{st.session_state.api_url}/chat", json={"message": msg}, timeout=60)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        return {"error": f"Server offline. FastAPI chal raha hai? ({st.session_state.api_url})"}
    except requests.exceptions.Timeout:
        return {"error": "Timeout — agent ne 60 seconds mein jawab nahi diya."}
    except Exception as e:
        try: detail = r.json().get("detail", str(e))
        except: detail = str(e)
        return {"error": f"Error: {detail}"}

def health():
    try: return requests.get(f"{st.session_state.api_url}/health", timeout=3).status_code == 200
    except: return False

def add_msg(role, content, intent="", is_error=False):
    clean = strip_html(content) if role == "bot" else content
    st.session_state.messages.append({
        "role": role, "content": clean,
        "time": datetime.now().strftime("%H:%M:%S"),
        "intent": intent, "is_error": is_error
    })
    st.session_state.total += 1

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("<div style='font-size:20px;font-weight:600;color:#f1f5f9;padding-bottom:4px;'>🧾 HisabBot</div>", unsafe_allow_html=True)
    st.markdown("<div style='font-size:12px;color:#4b5563;margin-bottom:16px;'>Wholesale Business Agent</div>", unsafe_allow_html=True)

    # Page navigation
    st.markdown("<div style='font-size:12px;font-weight:500;color:#9ca3af;margin-bottom:8px;'>Navigation</div>", unsafe_allow_html=True)
    col_n1, col_n2 = st.columns(2)
    with col_n1:
        if st.button("💬 Chat", use_container_width=True, key="nav_chat"):
            st.session_state.page = "chat"
            st.rerun()
    with col_n2:
        if st.button("📊 Report", use_container_width=True, key="nav_report"):
            st.session_state.page = "report"
            st.rerun()

    

    if st.session_state.page == "chat":
        st.markdown("<div style='font-size:12px;font-weight:500;color:#9ca3af;margin-bottom:8px;'>Session Stats</div>", unsafe_allow_html=True)
        st.markdown(f"""
        <div class="stat-box"><div class="stat-lbl">TOTAL MESSAGES</div><div class="stat-num sb">{st.session_state.total}</div></div>
        <div class="stat-box"><div class="stat-lbl">WRITE OPS</div><div class="stat-num sp">{st.session_state.writes}</div></div>
        <div class="stat-box"><div class="stat-lbl">READ QUERIES</div><div class="stat-num sg">{st.session_state.reads}</div></div>
        """, unsafe_allow_html=True)
        st.markdown("---")
        st.markdown("<div style='font-size:12px;font-weight:500;color:#9ca3af;margin-bottom:8px;'>Quick Commands</div>", unsafe_allow_html=True)
        cmds = [
            ("📦 Stock check",   "poora stock batao"),
            ("📊 Aaj ki sale",   "aaj ki total sale batao"),
            ("💰 Aaj ka profit", "aaj ka munafa kitna hua"),
            ("👥 Customers",     "kaunse customers ka baaki hai"),
            ("📈 Is mahine",     "is mahine ki total sale aur profit"),
            ("🔍 Top product",   "kaunsa product sabse zyada bikta hai"),
        ]
        for label, cmd in cmds:
            if st.button(label, key=f"q{label}", use_container_width=True):
                st.session_state.pending = cmd
                st.rerun()
        st.markdown("---")
        if st.button("🗑️ Clear Chat", use_container_width=True):
            for k in ["messages","total","writes","reads"]:
                st.session_state[k] = [] if k=="messages" else 0
            st.rerun()

    else:  # report page sidebar
        st.markdown("<div style='font-size:12px;font-weight:500;color:#9ca3af;margin-bottom:8px;'>Business Reports</div>", unsafe_allow_html=True)

        now = datetime.now()
        # Schedule info
        daily_due,  daily_msg  = is_report_due("daily")
        weekly_due, weekly_msg = is_report_due("weekly")
        monthly_due,monthly_msg= is_report_due("monthly")

        def sched_dot(due): return "🟢" if due else "🔴"

        st.markdown(f"""
        <div class="stat-box">
          <div class="stat-lbl">DAILY REPORT</div>
          <div style='font-size:13px;color:#d1d5db;margin-top:4px;'>{sched_dot(daily_due)} 9:00 PM daily</div>
        </div>
        <div class="stat-box">
          <div class="stat-lbl">WEEKLY REPORT</div>
          <div style='font-size:13px;color:#d1d5db;margin-top:4px;'>{sched_dot(weekly_due)} Sunday 12:00 PM</div>
        </div>
        <div class="stat-box">
          <div class="stat-lbl">MONTHLY REPORT</div>
          <div style='font-size:13px;color:#d1d5db;margin-top:4px;'>{sched_dot(monthly_due)} 28th 1:00 PM</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("---")
        # Force-generate buttons (always available for manual check)
        st.markdown("<div style='font-size:11px;color:#4b5563;margin-bottom:8px;font-family:JetBrains Mono,monospace;'>GENERATE NOW</div>", unsafe_allow_html=True)
        if st.button("📅 Daily Report",   use_container_width=True, key="gen_daily"):
            st.session_state.report_type = "daily"
            st.session_state.report_data = None
        if st.button("📆 Weekly Report",  use_container_width=True, key="gen_weekly"):
            st.session_state.report_type = "weekly"
            st.session_state.report_data = None
        if st.button("🗓️ Monthly Report", use_container_width=True, key="gen_monthly"):
            st.session_state.report_type = "monthly"
            st.session_state.report_data = None

    st.markdown("<div style='margin-top:8px;font-size:10px;color:#1f2937;font-family:JetBrains Mono,monospace;line-height:1.8;'>v6 · LangGraph · MongoDB<br>Groq llama-3.3-70b</div>", unsafe_allow_html=True)


# ── CHAT PAGE ─────────────────────────────────────────────────────────────────
if st.session_state.page == "chat":
    main_col, debug_col = st.columns([3, 1])

    with main_col:
        st.markdown("""
        <div style='display:flex;align-items:center;gap:10px;padding:10px 0 14px;border-bottom:1px solid #1c2030;margin-bottom:12px;'>
            <div style='width:8px;height:8px;border-radius:50%;background:#34d399;box-shadow:0 0 6px #34d399;'></div>
            <span style='font-family:JetBrains Mono,monospace;font-size:12px;color:#4b5563;'>hisabbot-agent &nbsp;·&nbsp; Roman Urdu</span>
        </div>
        """, unsafe_allow_html=True)

        if not st.session_state.messages:
            st.markdown("""
            <div style='text-align:center;padding:60px 20px;color:#1f2937;'>
                <div style='font-size:52px;margin-bottom:12px;'>🧾</div>
                <div style='font-size:16px;color:#374151;font-weight:500;'>HisabBot ready hai</div>
                <div style='font-size:13px;color:#1f2937;margin-top:6px;'>Roman Urdu mein apna sawaal ya hukum likhein</div>
            </div>""", unsafe_allow_html=True)
        else:
            all_html = []
            for msg in st.session_state.messages:
                role     = msg["role"]
                content  = esc(msg["content"])
                ts       = msg.get("time","")
                intent   = msg.get("intent","")
                is_error = msg.get("is_error",False)
                if role == "user":
                    all_html.append(
                        f'<div class="user-msg"><div>'
                        f'<div class="user-bubble">{content}</div>'
                        f'<div class="msg-meta user-meta">{ts}</div>'
                        f'</div></div>'
                    )
                else:
                    bclass = "bot-bubble err" if is_error else "bot-bubble"
                    badge  = ""
                    if intent and not is_error:
                        bc    = {"write":"bw","read":"br","unknown":"bu"}.get(intent,"br")
                        badge = f'<div><span class="badge {bc}">{intent}</span></div>'
                    all_html.append(
                        f'<div class="bot-msg"><div>'
                        f'<div class="{bclass}">{content}</div>'
                        f'{badge}'
                        f'<div class="msg-meta">{ts}</div>'
                        f'</div></div>'
                    )
            st.markdown("".join(all_html), unsafe_allow_html=True)

        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
        st.markdown("---")

        with st.form("f", clear_on_submit=True):
            ic, bc = st.columns([9,1])
            with ic:
                user_input = st.text_input("m", placeholder="Roman Urdu mein likhein...  (e.g. ali ko 50 bag cheeni 3550 per bag diya)", label_visibility="collapsed")
            with bc:
                sent = st.form_submit_button("↑ Send", use_container_width=True)

        if st.session_state.pending:
            user_input = st.session_state.pending
            st.session_state.pending = None
            sent = True

        if sent and user_input and user_input.strip():
            msg = user_input.strip()
            add_msg("user", msg)
            with st.spinner("Agent soch raha hai..."):
                result = call_api(msg)
            if "error" in result:
                add_msg("bot", result["error"], is_error=True)
            else:
                reply = result.get("reply","Koi jawab nahi mila.")
                iobj  = result.get("intent",{})
                istr  = iobj.get("intent","") if isinstance(iobj,dict) else ""
                if istr == "write": st.session_state.writes += 1
                elif istr == "read": st.session_state.reads += 1
                add_msg("bot", reply, intent=istr)
            st.rerun()

    with debug_col:
        st.markdown("<div style='font-family:JetBrains Mono,monospace;font-size:10px;color:#374151;padding:10px 0 14px;border-bottom:1px solid #1c2030;margin-bottom:12px;letter-spacing:0.08em;'>DEBUG PANEL</div>", unsafe_allow_html=True)
        msgs = st.session_state.messages
        if not msgs:
            st.markdown('<div style="font-size:12px;color:#1f2937;text-align:center;padding:16px 0;">No messages</div>', unsafe_allow_html=True)
        else:
            for msg in reversed(msgs):
                if msg["role"]=="bot" and not msg.get("is_error") and msg.get("intent"):
                    intent = msg["intent"]
                    bc = {"write":"bw","read":"br","unknown":"bu"}.get(intent,"br")
                    st.markdown(f'<div style="margin-bottom:14px;"><div style="font-size:10px;color:#374151;font-family:JetBrains Mono,monospace;letter-spacing:0.06em;margin-bottom:5px;">LAST INTENT</div><span class="badge {bc}" style="font-size:12px;padding:4px 12px;">{intent}</span></div>', unsafe_allow_html=True)
                    break
            st.markdown("<div style='font-size:10px;color:#374151;font-family:JetBrains Mono,monospace;letter-spacing:0.06em;margin-bottom:8px;'>MESSAGE LOG</div>", unsafe_allow_html=True)
            for msg in reversed(msgs[-12:]):
                role     = msg["role"]
                is_error = msg.get("is_error",False)
                ts       = msg.get("time","")
                preview  = esc(msg["content"][:55]+("..." if len(msg["content"])>55 else ""))
                if is_error: lbl,col="ERR","#7f1d1d"
                elif role=="user": lbl,col="USR","#5b21b6"
                else: lbl,col="BOT","#065f46"
                lbl_c={"ERR":"#f87171","USR":"#a78bfa","BOT":"#34d399"}[lbl]
                st.markdown(f'<div class="debug-entry" style="border-left-color:{col};"><span style="color:{lbl_c};font-weight:600;">{lbl}</span><span style="color:#374151;margin-left:6px;">{ts}</span><div class="debug-preview">{preview}</div></div>', unsafe_allow_html=True)


# ── REPORT PAGE ─────────────────────────────────────────────────────────────────
else:
    now   = datetime.now()
    rtype = st.session_state.get("report_type", "daily")

    st.markdown(f"""
    <div style='display:flex;align-items:center;gap:10px;padding:10px 0 14px;border-bottom:1px solid #1c2030;margin-bottom:20px;'>
        <div style='width:8px;height:8px;border-radius:50%;background:#a78bfa;box-shadow:0 0 6px #a78bfa;'></div>
        <span style='font-family:JetBrains Mono,monospace;font-size:12px;color:#4b5563;'>business report &nbsp;·&nbsp; {now.strftime("%d %B %Y")}</span>
    </div>
    """, unsafe_allow_html=True)

    t1, t2, t3 = st.tabs(["📅 Daily", "📆 Weekly", "🗓️ Monthly"])

    # ── Shared section renderer ───────────────────────────────────────────────
    def section(title, subtitle, body_html, empty=False):
        border = "#374151" if empty else "#065f46"
        st.markdown(f"""
        <div class="report-card" style="border-color:{border};">
          <div class="section-hd">{title}</div>
          <div style='font-size:11px;color:#4b5563;margin-bottom:10px;'>{subtitle}</div>
          <div class="report-body">{body_html}</div>
        </div>""", unsafe_allow_html=True)

    def profit_color(val):
        if val is None: return "#6b7280"
        return "#34d399" if float(val) >= 0 else "#f87171"

    def fmt_profit(val):
        if val is None: return "N/A"
        v = float(val)
        label = "Munafa" if v >= 0 else "Nuqsan"
        color  = "#34d399" if v >= 0 else "#f87171"
        return f'<span style="color:{color};">{label}: {_fmt(abs(v))}</span>'


    # ── Main render function ──────────────────────────────────────────────────
    def render_report(period, build_fn):
        due, sched_msg = is_report_due(period)

        if not due and st.session_state.report_type != period:
            st.markdown(f"""
            <div class="coming-soon">
                <div class="cs-icon">⏳</div>
                <div class="cs-title">Report abhi tayar nahi hai</div>
                <div class="cs-msg">{sched_msg}</div>
                <div class="cs-time">{now.strftime("%A, %d %B %Y — %I:%M %p")}</div>
            </div>""", unsafe_allow_html=True)
            if st.button(f"🔄 Abhi generate karo", key=f"force_{period}"):
                st.session_state.report_type = period
                st.session_state.report_data = None
                st.rerun()
            return

        if st.session_state.report_type == period and st.session_state.report_data is None:
            with st.spinner(f"{period.title()} report tayar ho rahi hai..."):
                try:
                    st.session_state.report_data = build_fn()
                except Exception as e:
                    st.error(f"Report generate nahi ho saki: {e}")
                    return

        data = st.session_state.report_data if st.session_state.report_type == period else None
        if not data:
            if st.button(f"📊 {period.title()} Report Generate Karo", key=f"gen2_{period}", use_container_width=True):
                st.session_state.report_type = period
                st.session_state.report_data = None
                st.rerun()
            return

        # ── Report header ─────────────────────────────────────────────────────
        period_ur = {"daily":"Roz ka","weekly":"Hafte ka","monthly":"Mahine ka"}.get(period, period)
        st.markdown(f"""
        <div class="report-card">
          <div class="report-header">HISABBOT · {period.upper()} REPORT</div>
          <div class="report-title">{period_ur} Business Report</div>
          <div class="report-sub">{data.get("date_label","")} &nbsp;·&nbsp; Generated: {data.get("generated_at","")}</div>
        </div>""", unsafe_allow_html=True)

        # ── 1. Sales Summary ──────────────────────────────────────────────────
        sales = data.get("sales")
        if sales:
            s = sales
            pf = fmt_profit(s.get("total_profit"))
            body = (
                f"Kul orders     : {_fmt_n(s.get('total_orders'))} transactions<br>"
                f"Units biki     : {_fmt_n(s.get('total_qty'))}<br>"
                f"Total wasool   : {_fmt(s.get('total_revenue'))}<br>"
                f"Total lagat    : {_fmt(s.get('total_cost'))}<br>"
                f"{pf}"
            )
        else:
            body = "Is period mein koi sale nahi hui."
        section("💰 Sales Summary", "Total sales, revenue aur profit", body, empty=not sales)

        # ── 2. Top Products ───────────────────────────────────────────────────
        prods = data.get("top_products", [])
        if prods:
            rows = []
            for i, p in enumerate(prods, 1):
                name = (p.get("_id") or "?").title()
                rows.append(
                    f"{i}. {name}: {_fmt_n(p.get('qty'))} units | "
                    f"Wasool: {_fmt(p.get('revenue'))} | "
                    f"{fmt_profit(p.get('profit'))}"
                )
            body = "<br>".join(rows)
        else:
            body = "Koi product data nahi mila."
        section("🏆 Top Products", "Sabse zyada bikne wale products", body, empty=not prods)

        # ── 3. Stock Status ───────────────────────────────────────────────────
        stock = data.get("stock", [])
        if stock:
            rows = []
            for item in stock:
                name = (item.get("product") or "?").title()
                qty  = max(0, item.get("qty") or 0)
                cp   = item.get("cost_price")
                cp_s = _fmt(cp) if cp else "price nahi"
                low  = qty <= (item.get("low_stock_threshold") or LOW_STOCK_THRESHOLD)
                flag = ' <span style="color:#f87171;">[LOW]</span>' if low else ""
                rows.append(f"{name}: {_fmt_n(qty)} units | {cp_s}{flag}")
            body = "<br>".join(rows)
        else:
            body = "Inventory khali hai."
        section("📦 Stock Status", "Har product ki current inventory", body, empty=not stock)

        # ── 4. Low Stock Alert ────────────────────────────────────────────────
        low = data.get("low_stock", [])
        if low:
            rows = []
            for item in low:
                name = (item.get("product") or "?").title()
                qty  = max(0, item.get("qty") or 0)
                thr  = item.get("threshold") or item.get("low_stock_threshold") or 5
                rows.append(f'<span style="color:#f87171;">⚠ {name}: {_fmt_n(qty)} units bacha hai (threshold: {thr})</span>')
            body = "<br>".join(rows)
        else:
            body = '<span style="color:#34d399;">✓ Sab items ka stock theek hai.</span>'
        section("⚠️ Low Stock Alert", "Jo items khatam hone wale hain", body, empty=not low)

        # ── 5. Payments ───────────────────────────────────────────────────────
        pays = data.get("payments")
        if pays:
            body = (
                f"Payments received : {_fmt_n(pays.get('count'))}<br>"
                f"Total amount      : {_fmt(pays.get('total'))}"
            )
        else:
            body = "Is period mein koi payment nahi aaya."
        section("💳 Payments Received", "Customers se mili payments", body, empty=not pays)

        # ── 6. Outstanding Balance ────────────────────────────────────────────
        pending = data.get("pending", [])
        if pending:
            total_pending = sum(c.get("total_credit",0) or 0 for c in pending)
            rows = [f"Kul baaki: {_fmt(total_pending)} ({len(pending)} customers)<br>"]
            for c in pending:
                name = (c.get("name") or "?").title()
                rows.append(f"{name}: {_fmt(c.get('total_credit'))}")
            body = "<br>".join(rows)
        else:
            body = '<span style="color:#34d399;">✓ Sab ka hisab saaf hai, koi baaki nahi.</span>'
        section("📋 Outstanding Balance", "Jinke payments baaki hain", body, empty=not pending)

        # ── 7. Top Customers (weekly/monthly only) ────────────────────────────
        customers = data.get("top_customers", [])
        if customers:
            rows = []
            for i, c in enumerate(customers, 1):
                name = (c.get("_id") or "?").title()
                rows.append(
                    f"{i}. {name}: {_fmt(c.get('spent'))} | "
                    f"{_fmt_n(c.get('orders'))} orders | "
                    f"{fmt_profit(c.get('profit'))}"
                )
            body = "<br>".join(rows)
            section("👥 Top Customers", "Sabse zyada kharidari karne wale", body)

        # ── 8. Per-product profit (weekly/monthly) ────────────────────────────
        pp = data.get("product_profit", [])
        if pp:
            rows = []
            for p in pp:
                name = (p.get("_id") or "?").title()
                rows.append(
                    f"{name}: {_fmt_n(p.get('qty'))} units | "
                    f"Wasool: {_fmt(p.get('revenue'))} | "
                    f"{fmt_profit(p.get('profit'))}"
                )
            body = "<br>".join(rows)
            section("📈 Product-wise Profit/Loss", "Har item ka munafa ya nuqsan", body)

        # ── 9. Stock value (monthly only) ─────────────────────────────────────
        sv = data.get("stock_value")
        if sv:
            body = (
                f"Total products  : {_fmt_n(sv.get('total_items'))}<br>"
                f"Total units     : {_fmt_n(sv.get('total_units'))}<br>"
                f"Total value     : {_fmt(sv.get('total_value'))}"
            )
            section("🏪 Inventory Value", "Stock ki kul qeemat (cost price par)", body)

       

        # ── Refresh ───────────────────────────────────────────────────────────
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        _, col_r = st.columns([3,1])
        with col_r:
            if st.button("🔄 Refresh Report", use_container_width=True, key=f"refresh_{period}"):
                st.session_state.report_type = period
                st.session_state.report_data = None
                st.rerun()

    LOW_STOCK_THRESHOLD = 5

    with t1:
        render_report("daily",   build_daily_report)
    with t2:
        render_report("weekly",  build_weekly_report)
    with t3:
        render_report("monthly", build_monthly_report)