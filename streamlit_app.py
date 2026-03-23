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

/* ══ REPORT STYLES ══════════════════════════════════════════════════════════ */
.report-card{background:#0f1218;border:1px solid #1c2030;border-radius:14px;padding:22px 26px;margin-bottom:18px;position:relative;overflow:hidden;}
.report-card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,#34d399,#60a5fa,#a78bfa);opacity:0.5;}
.report-header{font-size:11px;font-family:'JetBrains Mono',monospace;color:#4b5563;letter-spacing:0.1em;margin-bottom:10px;text-transform:uppercase;}
.report-title{font-size:22px;font-weight:700;color:#f1f5f9;margin-bottom:3px;letter-spacing:-0.02em;}
.report-sub{font-size:12px;color:#4b5563;margin-bottom:0;}
.section-hd{font-size:10px;font-family:'JetBrains Mono',monospace;color:#34d399;letter-spacing:0.12em;
  margin:20px 0 12px;padding-bottom:6px;border-bottom:1px solid #1c2030;text-transform:uppercase;display:flex;align-items:center;gap:6px;}
.report-body{font-size:14px;color:#d1d5db;line-height:1.8;}

/* KPI Grid */
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:4px;}
.kpi-card{background:#080a0f;border:1px solid #1c2030;border-radius:10px;padding:14px 16px;text-align:center;}
.kpi-label{font-size:9px;font-family:'JetBrains Mono',monospace;color:#4b5563;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:6px;}
.kpi-value{font-size:20px;font-weight:700;letter-spacing:-0.02em;}
.kpi-green{color:#34d399;}.kpi-blue{color:#60a5fa;}.kpi-purple{color:#a78bfa;}.kpi-yellow{color:#fbbf24;}.kpi-red{color:#f87171;}

/* Data table */
.rpt-table{width:100%;border-collapse:collapse;font-size:13px;}
.rpt-table th{font-family:'JetBrains Mono',monospace;font-size:9px;color:#4b5563;letter-spacing:0.08em;
  text-transform:uppercase;padding:6px 10px;border-bottom:1px solid #1c2030;text-align:left;font-weight:500;}
.rpt-table td{padding:9px 10px;border-bottom:1px solid #0f1218;color:#d1d5db;vertical-align:top;}
.rpt-table tr:last-child td{border-bottom:none;}
.rpt-table tr:hover td{background:#0a0c10;}
.rank-badge{display:inline-flex;align-items:center;justify-content:center;width:20px;height:20px;
  border-radius:50%;font-size:10px;font-weight:700;font-family:'JetBrains Mono',monospace;margin-right:6px;}
.rank-1{background:#fbbf24;color:#000;}.rank-2{background:#9ca3af;color:#000;}.rank-3{background:#b45309;color:#fff;}
.rank-other{background:#1c2030;color:#6b7280;}

/* Bubble alerts */
.alert-bubble{display:inline-flex;align-items:center;gap:6px;background:#2d0a0a;border:1px solid #7f1d1d;
  border-radius:20px;padding:5px 12px;font-size:12px;color:#f87171;font-weight:500;margin:3px 4px 3px 0;}
.ok-bubble{display:inline-flex;align-items:center;gap:6px;background:#052e20;border:1px solid #065f46;
  border-radius:20px;padding:5px 12px;font-size:12px;color:#34d399;font-weight:500;margin:3px 4px 3px 0;}
.warn-bubble{display:inline-flex;align-items:center;gap:6px;background:#1c1408;border:1px solid #92400e;
  border-radius:20px;padding:5px 12px;font-size:12px;color:#fbbf24;font-weight:500;margin:3px 4px 3px 0;}

/* Stock row */
.stock-row{display:flex;align-items:center;justify-content:space-between;padding:8px 12px;
  border-radius:8px;margin-bottom:5px;background:#080a0f;border:1px solid #1c2030;}
.stock-row.low{border-color:#7f1d1d;background:#120606;}
.stock-bar-wrap{background:#1c2030;border-radius:4px;height:4px;width:80px;display:inline-block;margin-left:8px;vertical-align:middle;}
.stock-bar{height:4px;border-radius:4px;}

/* Profit / Loss pill */
.profit-pill{display:inline-block;padding:2px 10px;border-radius:12px;font-size:11px;font-weight:600;font-family:'JetBrains Mono',monospace;}
.profit-up{background:#052e20;color:#34d399;border:1px solid #065f46;}
.profit-dn{background:#2d0a0a;color:#f87171;border:1px solid #7f1d1d;}

/* Customer card */
.cust-card{background:#080a0f;border:1px solid #1c2030;border-radius:10px;padding:12px 16px;margin-bottom:8px;}
.cust-name{font-size:14px;font-weight:600;color:#f1f5f9;margin-bottom:3px;}
.cust-addr{font-size:11px;color:#4b5563;margin-bottom:8px;font-family:'JetBrains Mono',monospace;}
.cust-meta{display:flex;flex-wrap:wrap;gap:8px;}
.meta-chip{background:#111827;border:1px solid #1f2937;border-radius:6px;padding:3px 10px;font-size:11px;color:#9ca3af;}

/* Section subtitle */
.sec-sub{font-size:11px;color:#4b5563;margin-bottom:14px;line-height:1.5;}

/* Coming soon */
.coming-soon{text-align:center;padding:50px 20px;}
.cs-icon{font-size:48px;margin-bottom:16px;}
.cs-title{font-size:18px;font-weight:600;color:#f1f5f9;margin-bottom:8px;}
.cs-msg{font-size:14px;color:#4b5563;margin-bottom:12px;}
.cs-time{font-size:13px;color:#34d399;font-family:'JetBrains Mono',monospace;}

/* Tips */
.tip-box{background:#0a1a12;border:1px solid #065f46;border-radius:8px;padding:12px 16px;margin-top:10px;display:flex;gap:10px;}
.tip-num{font-size:18px;color:#34d399;line-height:1;}
.tip-text{font-size:13px;color:#9ca3af;line-height:1.7;}

/* Finance payment row */
.pay-row{display:flex;align-items:center;justify-content:space-between;
  padding:9px 12px;border-radius:8px;margin-bottom:5px;background:#080a0f;border:1px solid #1c2030;}
.pending-row{border-color:#92400e;background:#100a02;}
.pending-amount{font-size:14px;font-weight:700;color:#fbbf24;}
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
    # Build history from last 4 stored messages (2 user + 2 bot = 2 exchanges)
    recent = st.session_state.messages[-4:] if len(st.session_state.messages) >= 4 else st.session_state.messages
    history = []
    for m in recent:
        role    = "user" if m["role"] == "user" else "assistant"
        content = m["content"]
        if content and not m.get("is_error"):
            history.append({"role": role, "content": content})

    payload = {"message": msg, "history": history}

    try:
        r = requests.post(f"{st.session_state.api_url}/chat", json=payload, timeout=60)
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
        border = "#374151" if empty else "#1c2030"
        st.markdown(f"""
        <div class="report-card" style="border-color:{border};">
          <div class="section-hd">{title}</div>
          <div class="sec-sub">{subtitle}</div>
          <div class="report-body">{body_html}</div>
        </div>""", unsafe_allow_html=True)

    def profit_color(val):
        if val is None: return "#6b7280"
        return "#34d399" if float(val) >= 0 else "#f87171"

    def fmt_profit(val):
        if val is None: return "N/A"
        v = float(val)
        cls = "profit-up" if v >= 0 else "profit-dn"
        label = "▲" if v >= 0 else "▼"
        return f'<span class="profit-pill {cls}">{label} {_fmt(abs(v))}</span>'

    def rank_badge(i):
        cls = {1:"rank-1",2:"rank-2",3:"rank-3"}.get(i,"rank-other")
        return f'<span class="rank-badge {cls}">{i}</span>'

    

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

        # ══ 1. SALES SUMMARY KPI GRID ════════════════════════════════════════
        sales = data.get("sales")
        if sales:
            s = sales
            profit_val = s.get("total_profit") or 0
            pf_cls = "kpi-green" if float(profit_val) >= 0 else "kpi-red"
            pf_prefix = "▲" if float(profit_val) >= 0 else "▼"
            margin = 0
            rev = s.get("total_revenue") or 0
            if rev:
                margin = round((float(profit_val) / float(rev)) * 100, 1)

            kpi_html = f"""
            <div class="kpi-grid">
              <div class="kpi-card">
                <div class="kpi-label">Total Orders</div>
                <div class="kpi-value kpi-blue">{_fmt_n(s.get('total_orders'))}</div>
              </div>
              <div class="kpi-card">
                <div class="kpi-label">Units Biki</div>
                <div class="kpi-value kpi-purple">{_fmt_n(s.get('total_qty'))}</div>
              </div>
              <div class="kpi-card">
                <div class="kpi-label">Kul Wasool</div>
                <div class="kpi-value kpi-yellow">{_fmt(s.get('total_revenue'))}</div>
              </div>
              <div class="kpi-card">
                <div class="kpi-label">Kul Lagat</div>
                <div class="kpi-value" style="color:#9ca3af;">{_fmt(s.get('total_cost'))}</div>
              </div>
              <div class="kpi-card">
                <div class="kpi-label">Net Profit</div>
                <div class="kpi-value {pf_cls}">{pf_prefix} {_fmt(abs(float(profit_val)))}</div>
              </div>
              <div class="kpi-card">
                <div class="kpi-label">Margin %</div>
                <div class="kpi-value {'kpi-green' if margin >= 0 else 'kpi-red'}">{margin}%</div>
              </div>
            </div>"""
            section("💰 Sales Summary", f"Is period ki kul sales, revenue aur net profit overview", kpi_html)
        else:
            section("💰 Sales Summary", "Total sales, revenue aur profit", "Is period mein koi sale nahi hui.", empty=True)

        # ══ 2. TOP PRODUCTS TABLE ════════════════════════════════════════════
        prods = data.get("top_products", [])
        if prods:
            rows_html = ""
            for i, p in enumerate(prods, 1):
                name    = (p.get("_id") or "?").title()
                qty     = p.get("qty") or 0
                rev     = p.get("revenue") or 0
                profit  = p.get("profit")
                rows_html += f"""
                <tr>
                  <td style="width:30px;">{rank_badge(i)}</td>
                  <td><span style="font-weight:600;color:#f1f5f9;">{name}</span></td>
                  <td style="color:#a78bfa;">{_fmt_n(qty)} units</td>
                  <td style="color:#fbbf24;">{_fmt(rev)}</td>
                  <td>{fmt_profit(profit)}</td>
                </tr>"""
            body = f"""
            <table class="rpt-table">
              <thead><tr>
                <th>#</th><th>Product Name</th><th>Quantity</th>
                <th>Revenue</th><th>Profit / Loss</th>
              </tr></thead>
              <tbody>{rows_html}</tbody>
            </table>"""
            section("🏆 Top Products", "Sabse zyada bikne wale products — quantity, revenue aur profit breakdown", body)
        else:
            section("🏆 Top Products", "Sabse zyada bikne wale products", "Koi product data nahi mila.", empty=True)

        # ══ 3. STOCK STATUS ══════════════════════════════════════════════════
        stock = data.get("stock", [])
        if stock:
            low_set = {i.get("product") for i in data.get("low_stock", [])}
            rows_html = ""
            for item in stock:
                name    = (item.get("product") or "?").title()
                qty     = max(0, item.get("qty") or 0)
                cp      = item.get("cost_price")
                cp_s    = _fmt(cp) if cp else "—"
                thr     = item.get("low_stock_threshold") or LOW_STOCK_THRESHOLD
                is_low  = qty <= thr
                stock_val = _fmt(float(cp) * qty) if cp and qty else "—"
                row_cls = "stock-row low" if is_low else "stock-row"
                # mini bar: max out at 100 units visually
                bar_pct = min(100, int((qty / max(thr * 3, 1)) * 100))
                bar_col = "#f87171" if is_low else "#34d399"
                badge   = '<span class="alert-bubble">⚠ Stock Low</span>' if is_low else '<span class="ok-bubble">✓ OK</span>'
                rows_html += f"""
                <div class="{row_cls}">
                  <div style="flex:1;">
                    <span style="font-weight:600;color:#f1f5f9;">{name}</span>
                    {badge}
                    <div class="stock-bar-wrap"><div class="stock-bar" style="width:{bar_pct}%;background:{bar_col};"></div></div>
                  </div>
                  <div style="text-align:right;white-space:nowrap;margin-left:12px;">
                    <div style="font-family:'JetBrains Mono',monospace;font-size:15px;font-weight:700;color:{'#f87171' if is_low else '#f1f5f9'};">{_fmt_n(qty)} <span style="font-size:10px;color:#4b5563;">units</span></div>
                    <div style="font-size:11px;color:#4b5563;">Cost: {cp_s} &nbsp;·&nbsp; Value: {stock_val}</div>
                  </div>
                </div>"""
            section("📦 Stock Status", "Har product ki current inventory — qty, cost price aur estimated value", rows_html)
        else:
            section("📦 Stock Status", "Har product ki current inventory", "Inventory khali hai.", empty=True)

        # ══ 4. LOW STOCK ALERTS ══════════════════════════════════════════════
        low = data.get("low_stock", [])
        if low:
            bubbles = ""
            for item in low:
                name = (item.get("product") or "?").title()
                qty  = max(0, item.get("qty") or 0)
                thr  = item.get("threshold") or item.get("low_stock_threshold") or 5
                if qty == 0:
                    bubbles += f'<span class="alert-bubble" style="background:#3d0000;border-color:#b91c1c;">🚨 {name}: OUT OF STOCK</span>'
                else:
                    bubbles += f'<span class="alert-bubble">⚠ {name}: {_fmt_n(qty)} baca (min: {thr})</span>'
            section("🚨 Low Stock Alerts", f"{len(low)} item(s) critical level par hain — foran reorder karein", bubbles)
        else:
            section("🚨 Low Stock Alerts", "Stock alert status", '<span class="ok-bubble">✅ Sab items ka stock theek hai — koi alert nahi</span>')

        # ══ 5. FINANCE — PAYMENTS RECEIVED (per customer) ══════════════════
        pays         = data.get("payments")
        pays_detail  = data.get("payments_detail", [])
        pending      = data.get("pending", [])

        # Build per-customer payment cards
        if pays_detail:
            grand_total = sum(c.get("total") or 0 for c in pays_detail)
            grand_count = sum(c.get("count") or 0 for c in pays_detail)
            pay_body = f"""
            <div class="pay-row" style="border-color:#065f46;background:#031a0f;margin-bottom:16px;">
              <span style="font-family:'JetBrains Mono',monospace;font-size:10px;color:#34d399;letter-spacing:0.1em;">
                ✓ TOTAL PAYMENTS RECEIVED &nbsp;·&nbsp; {grand_count} TRANSACTIONS
              </span>
              <span style="font-size:17px;font-weight:700;color:#34d399;">{_fmt(grand_total)}</span>
            </div>"""
            for c in pays_detail:
                cname    = (c.get("_id") or "Unknown").title()
                addr     = c.get("address") or "—"
                phone    = c.get("phone") or "—"
                total    = c.get("total") or 0
                count    = c.get("count") or 0
                last_pay = c.get("last_pay")
                last_s   = last_pay.strftime("%d %b, %I:%M %p") if last_pay else "—"
                pay_body += f"""
            <div class="cust-card" style="border-color:#065f46;margin-bottom:8px;">
              <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                <div style="flex:1;">
                  <div class="cust-name">💚 {cname}</div>
                  <div class="cust-addr">📍 {addr} &nbsp;·&nbsp; 📞 {phone}</div>
                  <div class="cust-meta" style="margin-top:6px;">
                    <span class="meta-chip">🔁 {_fmt_n(count)} {'payment' if count == 1 else 'payments'}</span>
                    <span class="meta-chip">🕐 {last_s}</span>
                  </div>
                </div>
                <div style="font-size:20px;font-weight:700;color:#34d399;white-space:nowrap;margin-left:20px;padding-top:2px;">{_fmt(total)}</div>
              </div>
            </div>"""
        elif pays:
            pay_body = f"""
            <div class="pay-row" style="border-color:#065f46;background:#031a0f;">
              <span style="color:#9ca3af;">Total Payments Received ({_fmt_n(pays.get('count'))} transactions)</span>
              <span style="font-size:15px;font-weight:700;color:#34d399;">{_fmt(pays.get('total'))}</span>
            </div>"""
        else:
            pay_body = '<span style="color:#4b5563;">Is period mein koi payment nahi aaya.</span>'

        section("💚 Payments Received", "Is period mein customers ne jo payments diye — naam, address aur amount", pay_body, empty=not pays_detail and not pays)

        # ══ 5b. OUTSTANDING BALANCE (per customer) ═══════════════════════════
        if pending:
            total_pending = sum(c.get("total_credit", 0) or 0 for c in pending)
            pend_body = f"""
            <div style="padding:8px 12px;background:#1c0a00;border:1px solid #92400e;border-radius:8px;
              display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
              <span style="font-family:'JetBrains Mono',monospace;font-size:10px;color:#92400e;letter-spacing:0.1em;">
                ⚠ {len(pending)} CUSTOMERS KA BAAKI HAI
              </span>
              <span style="font-size:15px;font-weight:700;color:#fbbf24;">{_fmt(total_pending)}</span>
            </div>"""
            for c in pending:
                cname  = (c.get("name") or "?").title()
                addr   = (c.get("address") or c.get("area") or "—")
                phone  = (c.get("phone") or c.get("contact") or "—")
                credit = c.get("total_credit") or 0
                urg_col = "#f87171" if credit > 50000 else ("#fbbf24" if credit > 10000 else "#fcd34d")
                urg_brd = "#7f1d1d" if credit > 50000 else ("#92400e" if credit > 10000 else "#78350f")
                urg_bg  = "#1c0606" if credit > 50000 else ("#100a02" if credit > 10000 else "#0d0900")
                pend_body += f"""
            <div class="cust-card" style="border-color:{urg_brd};background:{urg_bg};margin-bottom:8px;">
              <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                <div style="flex:1;">
                  <div class="cust-name">🔴 {cname}</div>
                  <div class="cust-addr">📍 {addr} &nbsp;·&nbsp; 📞 {phone}</div>
                  <div class="cust-meta" style="margin-top:6px;">
                    <span class="meta-chip" style="border-color:{urg_brd};color:{urg_col};">⚠ Baaki: {_fmt(credit)}</span>
                  </div>
                </div>
                <div style="font-size:20px;font-weight:700;color:{urg_col};white-space:nowrap;margin-left:20px;padding-top:2px;">{_fmt(credit)}</div>
              </div>
            </div>"""
            section("🔴 Outstanding Balance", "Jo customers abhi tak payment nahi diye — baaki rakam", pend_body)
        else:
            section("🔴 Outstanding Balance", "Outstanding payments status", '<span class="ok-bubble">✓ Koi outstanding balance nahi — sab ka hisab saaf hai</span>')

        # ══ 6. TOP CUSTOMERS TABLE (weekly/monthly) ══════════════════════════
        customers = data.get("top_customers", [])
        if customers:
            rows_html = ""
            for i, c in enumerate(customers, 1):
                name   = (c.get("_id") or "?").title()
                spent  = c.get("spent") or 0
                orders = c.get("orders") or 0
                profit = c.get("profit")
                # derive address/phone from pending list if available
                cinfo  = next((x for x in pending if (x.get("name") or "").lower() == name.lower()), {})
                addr   = (cinfo.get("address") or cinfo.get("area") or "—")
                phone  = (cinfo.get("phone") or cinfo.get("contact") or "—")
                rows_html += f"""
                <tr>
                  <td style="width:30px;">{rank_badge(i)}</td>
                  <td>
                    <div style="font-weight:600;color:#f1f5f9;">{name}</div>
                    <div style="font-size:10px;color:#4b5563;margin-top:2px;">📍 {addr} &nbsp;·&nbsp; 📞 {phone}</div>
                  </td>
                  <td style="color:#fbbf24;">{_fmt(spent)}</td>
                  <td style="color:#60a5fa;">{_fmt_n(orders)} orders</td>
                  <td>{fmt_profit(profit)}</td>
                </tr>"""
            body = f"""
            <table class="rpt-table">
              <thead><tr>
                <th>#</th><th>Customer</th><th>Total Spend</th>
                <th>Orders</th><th>Profit Contribution</th>
              </tr></thead>
              <tbody>{rows_html}</tbody>
            </table>"""
            section("👥 Top Customers", "Sabse zyada kharidari karne wale customers — spend, orders aur profit breakdown", body)

        # ══ 7. PRODUCT PROFIT / LOSS TABLE (weekly/monthly) ═════════════════
        pp = data.get("product_profit", [])
        if pp:
            rows_html = ""
            for p in pp:
                name   = (p.get("_id") or "?").title()
                qty    = p.get("qty") or 0
                rev    = p.get("revenue") or 0
                cost   = p.get("cost") or 0
                profit = p.get("profit") or 0
                margin = round((profit / rev * 100), 1) if rev else 0
                m_col  = "#34d399" if margin >= 0 else "#f87171"
                rows_html += f"""
                <tr>
                  <td style="font-weight:600;color:#f1f5f9;">{name}</td>
                  <td style="color:#a78bfa;">{_fmt_n(qty)} units</td>
                  <td style="color:#fbbf24;">{_fmt(rev)}</td>
                  <td style="color:#9ca3af;">{_fmt(cost)}</td>
                  <td>{fmt_profit(profit)}</td>
                  <td style="color:{m_col};font-family:'JetBrains Mono',monospace;">{margin}%</td>
                </tr>"""
            body = f"""
            <table class="rpt-table">
              <thead><tr>
                <th>Product</th><th>Qty Sold</th><th>Revenue</th>
                <th>Cost</th><th>Profit / Loss</th><th>Margin</th>
              </tr></thead>
              <tbody>{rows_html}</tbody>
            </table>"""
            section("📈 Profit & Loss — Per Product", "Har product ka munafa ya nuqsan — revenue, cost aur margin breakdown", body)

        # ══ 8. INVENTORY VALUE (monthly only) ════════════════════════════════
        sv = data.get("stock_value")
        if sv:
            body = f"""
            <div class="kpi-grid" style="grid-template-columns:repeat(3,1fr);">
              <div class="kpi-card">
                <div class="kpi-label">Total Products</div>
                <div class="kpi-value kpi-blue">{_fmt_n(sv.get('total_items'))}</div>
              </div>
              <div class="kpi-card">
                <div class="kpi-label">Total Units</div>
                <div class="kpi-value kpi-purple">{_fmt_n(sv.get('total_units'))}</div>
              </div>
              <div class="kpi-card">
                <div class="kpi-label">Stock Value</div>
                <div class="kpi-value kpi-yellow">{_fmt(sv.get('total_value'))}</div>
              </div>
            </div>"""
            section("🏪 Inventory Value", "Stock ki kul qeemat at cost price — warehouse value estimate", body)

       

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