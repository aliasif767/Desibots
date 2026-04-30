

import streamlit as st
import requests
from datetime import datetime
import os

# ═══════════════════════════════════════════════════════════════════════════════
#  PAGE CONFIG
#  Sets browser tab title, icon, layout width, and sidebar default state.
#  Must be the FIRST Streamlit call in the script.
# ═══════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="MediAssist AI — First Aid",
    page_icon="🏥",
    layout="centered",
    initial_sidebar_state="expanded",
)

# ═══════════════════════════════════════════════════════════════════════════════
#  CONSTANTS
#  API_URL     — base path for all REST calls to FastAPI backend
#  BACKEND_BASE — origin used to build absolute image URLs
#                 e.g. "/images/choking/infant.jpeg" → "http://localhost:8000/images/..."
# ═══════════════════════════════════════════════════════════════════════════════
API_URL      = os.environ.get("FIRSTAID_API_URL", "http://localhost:8510/api/v1")
BACKEND_BASE = os.environ.get("FIRSTAID_BACKEND_BASE", "http://localhost:8510")

# ═══════════════════════════════════════════════════════════════════════════════
#  GLOBAL CSS
#
#  Design system: Clinical-luxury dark theme
#  — Google Fonts: "DM Serif Display" (headings) + "DM Sans" (body)
#  — Color palette: deep navy (#0B1628) bg, crimson (#C8374A) accent,
#    slate (#1E2D45) surfaces, warm white (#F0EDE8) text
#  — Typography scale: 11px caption → 13px body → 15px label → 20px title
#  — All components use CSS custom properties (variables) for consistency
#  — Animations: fade-in-up on bubbles, pulse on live indicators
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:ital,opsz,wght@0,9..40,300;0,9..40,400;0,9..40,500;0,9..40,600;1,9..40,300&display=swap" rel="stylesheet">

<style>
/* ── Design tokens ─────────────────────────────────────────────────────────── */
:root {
    --bg:           #0B1628;
    --surface:      #111f35;
    --surface-2:    #162843;
    --surface-3:    #1E3454;
    --border:       rgba(255,255,255,0.07);
    --border-strong:rgba(255,255,255,0.13);
    --accent:       #C8374A;
    --accent-soft:  rgba(200,55,74,0.15);
    --accent-glow:  rgba(200,55,74,0.25);
    --green:        #2ECC8F;
    --green-soft:   rgba(46,204,143,0.12);
    --amber:        #F5A623;
    --amber-soft:   rgba(245,166,35,0.12);
    --blue:         #4A9EFF;
    --blue-soft:    rgba(74,158,255,0.12);
    --text-primary: #F0EDE8;
    --text-secondary:#A8B8CC;
    --text-muted:   #5A7090;
    --font-display: 'DM Serif Display', Georgia, serif;
    --font-body:    'DM Sans', system-ui, sans-serif;
    --radius-sm:    6px;
    --radius-md:    10px;
    --radius-lg:    16px;
    --shadow-sm:    0 1px 4px rgba(0,0,0,0.3);
    --shadow-md:    0 4px 16px rgba(0,0,0,0.4);
    --shadow-lg:    0 8px 32px rgba(0,0,0,0.5);
}

/* ── Base resets ───────────────────────────────────────────────────────────── */
html, body, [class*="css"] {
    font-family: var(--font-body) !important;
    background-color: var(--bg) !important;
    color: var(--text-primary) !important;
}
.block-container {
    padding-top: 0.5rem !important;
    padding-bottom: 6rem !important;
    max-width: 780px !important;
}
#MainMenu, footer, header { visibility: hidden; }

/* ── Scrollbar styling ─────────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--surface-3); border-radius: 4px; }

/* ── Animations ────────────────────────────────────────────────────────────── */
@keyframes fadeUp {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
}
@keyframes pulse-dot {
    0%, 100% { opacity: 1; transform: scale(1); }
    50%       { opacity: 0.5; transform: scale(0.85); }
}

/* ── App header bar ────────────────────────────────────────────────────────── */
.app-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: var(--surface);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-lg);
    padding: 16px 22px;
    margin-bottom: 1.5rem;
    box-shadow: var(--shadow-md);
}
.app-header-left { display: flex; align-items: center; gap: 14px; }
.app-logo {
    width: 44px; height: 44px; border-radius: 12px;
    background: linear-gradient(135deg, var(--accent) 0%, #8B1A28 100%);
    display: flex; align-items: center; justify-content: center;
    box-shadow: 0 0 20px var(--accent-glow);
    flex-shrink: 0;
}
.app-title {
    font-family: var(--font-display) !important;
    font-size: 20px !important;
    font-weight: 400 !important;
    color: var(--text-primary) !important;
    margin: 0 !important;
    line-height: 1.2;
    letter-spacing: -0.01em;
}
.app-subtitle {
    font-size: 11.5px;
    color: var(--text-muted);
    margin: 3px 0 0;
    letter-spacing: 0.02em;
    font-weight: 400;
}
.status-pill {
    display: flex; align-items: center; gap: 7px;
    background: var(--green-soft);
    border: 1px solid rgba(46,204,143,0.25);
    border-radius: 20px; padding: 6px 14px;
    font-size: 11.5px; font-weight: 500; color: var(--green);
    letter-spacing: 0.02em;
}
.status-dot {
    width: 7px; height: 7px; border-radius: 50%;
    background: var(--green);
    animation: pulse-dot 2s ease-in-out infinite;
}

/* ── Chat message rows ─────────────────────────────────────────────────────── */
.msg-row {
    display: flex;
    gap: 12px;
    margin-bottom: 1.2rem;
    align-items: flex-start;
    animation: fadeUp 0.3s ease both;
}
.msg-row.user { flex-direction: row-reverse; }

/* ── Avatars ───────────────────────────────────────────────────────────────── */
.avatar {
    width: 36px; height: 36px; border-radius: 10px; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    font-size: 13px; font-weight: 600;
}
.avatar-bot {
    background: linear-gradient(135deg, var(--accent), #8B1A28);
    color: #fff; font-size: 18px;
    box-shadow: 0 2px 10px var(--accent-glow);
}
.avatar-user {
    background: var(--surface-3);
    color: var(--text-secondary);
    border: 1px solid var(--border-strong);
    font-size: 11px; letter-spacing: -0.02em;
}

/* ── Chat bubbles ──────────────────────────────────────────────────────────── */
.bubble {
    max-width: 86%;
    padding: 14px 18px;
    border-radius: var(--radius-lg);
    font-size: 13.5px;
    line-height: 1.7;
    font-weight: 400;
}
.bubble-bot {
    background: var(--surface);
    color: var(--text-primary);
    border: 1px solid var(--border);
    border-top-left-radius: 4px;
    box-shadow: var(--shadow-sm);
}
.bubble-user {
    background: var(--surface-3);
    color: var(--text-primary);
    border: 1px solid var(--border-strong);
    border-top-right-radius: 4px;
}

/* ── Emergency alert banner ────────────────────────────────────────────────── */
.e-banner {
    background: rgba(200,55,74,0.1);
    border: 1px solid rgba(200,55,74,0.4);
    border-radius: var(--radius-md);
    padding: 12px 16px;
    margin-bottom: 14px;
    display: flex; gap: 12px; align-items: flex-start;
}
.e-banner strong {
    display: block; font-size: 12.5px; font-weight: 600;
    color: #FF6B7A; margin-bottom: 3px; letter-spacing: 0.01em;
}
.e-banner span { font-size: 12px; color: #C87A83; font-weight: 400; }

/* ── Emergency type header ─────────────────────────────────────────────────── */
.et-header { margin-bottom: 14px; }
.et-title {
    font-family: var(--font-display) !important;
    font-size: 18px !important;
    font-weight: 400 !important;
    color: var(--text-primary) !important;
    letter-spacing: -0.01em;
    margin: 0 0 5px !important;
    line-height: 1.25;
}
.et-source { font-size: 11px; color: var(--text-muted); font-weight: 400; margin-bottom: 8px; }
.badges { display: flex; gap: 5px; flex-wrap: wrap; }

/* ── Badges ────────────────────────────────────────────────────────────────── */
.badge {
    font-size: 10px; font-weight: 600;
    padding: 3px 9px; border-radius: 20px;
    display: inline-flex; align-items: center; gap: 4px;
    letter-spacing: 0.04em; text-transform: uppercase;
}
.b-high { background: var(--accent-soft); color: #FF8090; border: 1px solid rgba(200,55,74,0.3); }
.b-low  { background: var(--green-soft);  color: var(--green); border: 1px solid rgba(46,204,143,0.3); }
.b-db   { background: var(--blue-soft);   color: var(--blue);  border: 1px solid rgba(74,158,255,0.3); }
.b-llm  { background: var(--amber-soft);  color: var(--amber); border: 1px solid rgba(245,166,35,0.3); }

/* ── Divider ───────────────────────────────────────────────────────────────── */
.divider { border: none; border-top: 1px solid var(--border); margin: 12px 0; }

/* ── Step list ─────────────────────────────────────────────────────────────── */
.step-list { list-style: none; padding: 0; margin: 4px 0 10px; }
.step-item { display: flex; gap: 12px; margin-bottom: 12px; align-items: flex-start; }
.step-num {
    min-width: 26px; height: 26px; border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-size: 11px; font-weight: 700; flex-shrink: 0; margin-top: 2px;
}
.sn-high { background: var(--accent-soft); color: #FF8090; border: 1px solid rgba(200,55,74,0.25); }
.sn-low  { background: var(--green-soft);  color: var(--green); border: 1px solid rgba(46,204,143,0.25); }
.step-text { font-size: 13.5px; color: var(--text-primary); line-height: 1.65; font-weight: 400; }
.step-alert { font-size: 11px; color: #FF6B7A; margin-top: 5px; font-weight: 500; letter-spacing: 0.01em; }

/* ── Notes callout ─────────────────────────────────────────────────────────── */
.note-high {
    background: rgba(200,55,74,0.08);
    border-left: 3px solid var(--accent);
    border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
    padding: 10px 14px; margin-top: 12px;
    font-size: 12px; color: #C87A83; line-height: 1.6; font-weight: 400;
}
.note-low {
    background: var(--amber-soft);
    border-left: 3px solid var(--amber);
    border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
    padding: 10px 14px; margin-top: 12px;
    font-size: 12px; color: #C4934A; line-height: 1.6; font-weight: 400;
}

/* ── First aid image ───────────────────────────────────────────────────────── */
.firstaid-img-wrap {
    margin: 14px 0 4px;
    border-radius: var(--radius-md);
    overflow: hidden;
    border: 1px solid var(--border-strong);
    box-shadow: var(--shadow-md);
}
.firstaid-img-wrap img { width: 100%; display: block; }
.img-caption { font-size: 10.5px; color: var(--text-muted); margin-top: 5px; font-weight: 400; }

/* ── AI answer text ────────────────────────────────────────────────────────── */
.ai-answer {
    font-size: 13.5px; line-height: 1.75;
    color: var(--text-primary); white-space: pre-wrap; padding: 4px 0;
}

/* ── Follow-up hint ────────────────────────────────────────────────────────── */
.followup-hint {
    font-size: 11.5px; color: var(--text-muted); margin-top: 10px;
    font-style: italic;
}
.followup-hint b { color: var(--blue); font-style: normal; font-weight: 500; }

/* ── Doctor card ───────────────────────────────────────────────────────────── */
.doc-card {
    background: var(--surface-2);
    border: 1px solid var(--border-strong);
    border-radius: var(--radius-md);
    padding: 14px 16px; margin-top: 10px;
}
.doc-card-label {
    font-size: 10px; font-weight: 600; color: var(--blue);
    text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 10px;
}
.doc-row { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.doc-avatar {
    width: 42px; height: 42px; border-radius: 12px;
    background: linear-gradient(135deg, var(--blue), #1A5FAA);
    color: #fff; display: flex; align-items: center; justify-content: center;
    font-size: 13px; font-weight: 700; flex-shrink: 0;
    box-shadow: 0 2px 10px rgba(74,158,255,0.25);
}
.doc-name { font-size: 13.5px; font-weight: 500; color: var(--text-primary); line-height: 1.3; }
.doc-loc  { font-size: 11.5px; color: var(--text-muted); margin-top: 2px; }
.doc-meta { display: grid; grid-template-columns: 1fr 1fr; gap: 7px; }
.doc-meta-item {
    background: var(--surface-3); border-radius: var(--radius-sm);
    padding: 8px 10px; border: 1px solid var(--border);
}
.doc-meta-label { font-size: 10px; color: var(--text-muted); margin-bottom: 3px; letter-spacing: 0.03em; }
.doc-meta-val   { font-size: 12.5px; font-weight: 500; }
.dv-green { color: var(--green); }
.dv-blue  { color: var(--blue); }
.dv-full  { grid-column: 1 / -1; }
.book-cta {
    font-size: 11.5px; color: var(--blue); margin-top: 10px;
    padding: 8px 12px; background: var(--blue-soft);
    border-radius: var(--radius-sm); border: 1px solid rgba(74,158,255,0.2);
}
.book-cta b { font-weight: 600; }

/* ── Confirmed card ────────────────────────────────────────────────────────── */
.confirmed-card {
    background: var(--green-soft);
    border: 1px solid rgba(46,204,143,0.3);
    border-radius: var(--radius-md);
    padding: 16px 18px;
}
.confirmed-title {
    font-size: 13px; font-weight: 600; color: var(--green);
    margin-bottom: 12px; display: flex; align-items: center; gap: 8px;
}
.confirmed-detail {
    font-size: 12.5px; color: var(--text-secondary); line-height: 2.0;
}
.confirmed-detail b { color: var(--text-primary); font-weight: 500; }
.confirmed-footer { font-size: 11px; color: var(--text-muted); margin-top: 10px; font-style: italic; }

/* ── Streamlit input overrides ─────────────────────────────────────────────── */
div[data-testid="stTextInput"] input {
    background: var(--surface) !important;
    border: 1px solid var(--border-strong) !important;
    border-radius: var(--radius-md) !important;
    color: var(--text-primary) !important;
    font-family: var(--font-body) !important;
    font-size: 13.5px !important;
    padding: 10px 14px !important;
    caret-color: var(--accent) !important;
}
div[data-testid="stTextInput"] input:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 3px var(--accent-soft) !important;
    outline: none !important;
}
div[data-testid="stTextInput"] input::placeholder { color: var(--text-muted) !important; }

/* ── Streamlit button overrides ────────────────────────────────────────────── */
div[data-testid="stButton"] button[kind="primary"] {
    background: linear-gradient(135deg, var(--accent), #A02535) !important;
    border: none !important;
    border-radius: var(--radius-md) !important;
    color: #fff !important;
    font-family: var(--font-body) !important;
    font-size: 13px !important;
    font-weight: 600 !important;
    padding: 10px 16px !important;
    box-shadow: 0 2px 8px var(--accent-glow) !important;
    letter-spacing: 0.01em !important;
    transition: opacity 0.15s ease !important;
}
div[data-testid="stButton"] button[kind="primary"]:hover { opacity: 0.88 !important; }
div[data-testid="stButton"] button[kind="secondary"],
div[data-testid="stButton"] button:not([kind]) {
    background: var(--surface-2) !important;
    border: 1px solid var(--border-strong) !important;
    border-radius: var(--radius-sm) !important;
    color: var(--text-secondary) !important;
    font-family: var(--font-body) !important;
    font-size: 12px !important;
    font-weight: 400 !important;
    transition: background 0.15s ease, color 0.15s ease !important;
}
div[data-testid="stButton"] button:not([kind]):hover {
    background: var(--surface-3) !important;
    color: var(--text-primary) !important;
}

/* ── Sidebar overrides ─────────────────────────────────────────────────────── */
[data-testid="stSidebar"] { background: var(--surface) !important; border-right: 1px solid var(--border) !important; }
[data-testid="stSidebar"] * { color: var(--text-secondary) !important; }
[data-testid="stSidebar"] h3 {
    font-family: var(--font-display) !important;
    font-size: 17px !important; font-weight: 400 !important;
    color: var(--text-primary) !important;
}
[data-testid="stSidebar"] hr { border-color: var(--border) !important; margin: 12px 0 !important; }

/* ── Welcome card ──────────────────────────────────────────────────────────── */
.welcome-title {
    font-family: var(--font-display) !important;
    font-size: 20px !important; font-weight: 400 !important;
    color: var(--text-primary) !important;
    line-height: 1.25; margin-bottom: 10px; letter-spacing: -0.01em;
}
.welcome-body { font-size: 13.5px; color: var(--text-secondary); line-height: 1.7; margin-bottom: 14px; }
.capability-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 12px 0 16px; }
.cap-item {
    background: var(--surface-2); border: 1px solid var(--border);
    border-radius: var(--radius-sm); padding: 10px 12px;
    font-size: 12px; color: var(--text-secondary); line-height: 1.5;
}
.cap-item b { display: block; color: var(--text-primary); font-weight: 500; margin-bottom: 2px; font-size: 12.5px; }
.welcome-example {
    font-size: 12px; color: var(--text-muted); font-style: italic;
    background: var(--surface-2); border-radius: var(--radius-sm);
    padding: 9px 13px; border-left: 2px solid var(--accent);
}
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  SESSION STATE INITIALIZATION
#
#  Streamlit reruns the entire script on every interaction.
#  st.session_state persists values across reruns within the same session.
#  We use `defaults` dict to avoid overwriting existing state on rerun.
# ═══════════════════════════════════════════════════════════════════════════════
defaults = {
    "messages":       [],    # [{role: "user"|"assistant", content: str, html: str}]
    "booking_state":  None,  # None | "ask_name" | "ask_phone" | "ask_email" | "confirm"
    "booking_info":   {},    # {name: str, phone: str, email: str}
    "pending_doctor": None,  # doctor dict from /doctors/available
    "last_emergency": None,  # last classified emergency_type string
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ═══════════════════════════════════════════════════════════════════════════════
#  API LAYER
#
#  Three thin wrapper functions that call the FastAPI backend.
#  All network errors are caught by callers — these functions raise on HTTP errors.
#
#  api_assess(query)
#    POST /api/v1/emergency
#    Body: { "query": str }
#    Returns: FirstAidResponse JSON (source, emergency_type, acuity, steps, etc.)
#
#  api_check_doctor(emergency_type)
#    GET /api/v1/doctors/available?type=<emergency_type>
#    Returns: { count, doctors: [...] }
#
#  api_book_appointment(doctor_id, patient, emergency_type)
#    POST /api/v1/appointments
#    Body: { doctor_id, emergency_type, name, phone, email }
#    Returns: appointment confirmation with doctor details and appointment_id
# ═══════════════════════════════════════════════════════════════════════════════
def api_assess(query: str) -> dict:
    r = requests.post(f"{API_URL}/emergency", json={"query": query}, timeout=30)
    r.raise_for_status()
    return r.json()

def api_check_doctor(emergency_type: str):
    try:
        r = requests.get(f"{API_URL}/doctors/available",
                         params={"type": emergency_type}, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def api_book_appointment(doctor_id: str, patient: dict, emergency_type: str):
    try:
        r = requests.post(f"{API_URL}/appointments", json={
            "doctor_id": doctor_id,
            "emergency_type": emergency_type,
            **patient
        }, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
#  INTENT DETECTION
#
#  Lightweight keyword-based intent classifier.
#  Runs BEFORE sending to the backend — avoids unnecessary API calls for
#  booking/doctor queries that don't need LLM classification.
#
#  Priority order (first match wins):
#    1. book         — user wants to book appointment
#    2. check_doctor — user wants to see available doctors
#    3. confirm      — user is confirming a pending action
#    4. cancel       — user is cancelling a pending action
#    5. emergency    — default: treat as medical query → send to LLM pipeline
# ═══════════════════════════════════════════════════════════════════════════════
def detect_intent(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ["book", "appointment", "schedule", "reserve"]):
        return "book"
    if any(w in t for w in ["doctor", "available", "availability", "specialist", "find doctor"]):
        return "check_doctor"
    if any(w in t for w in ["yes", "confirm", "sure", "ok", "okay", "proceed", "go ahead", "correct"]):
        return "confirm"
    if any(w in t for w in ["no", "cancel", "skip", "stop", "abort"]):
        return "cancel"
    return "emergency"


# ═══════════════════════════════════════════════════════════════════════════════
#  HTML BUILDER UTILITIES
#  get_initials(name) — extracts 2-letter initials for doctor avatar
#  fmt_time(iso)      — formats ISO datetime string to human-readable label
# ═══════════════════════════════════════════════════════════════════════════════
def get_initials(name: str) -> str:
    clean = name.replace("Dr. ", "").replace("(", "").split()
    return "".join(p[0].upper() for p in clean[:2])

def fmt_time(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%b %d, %Y — %I:%M %p")
    except Exception:
        return iso


# ═══════════════════════════════════════════════════════════════════════════════
#  EMERGENCY RESPONSE CARD HTML
#
#  Builds the rich HTML card shown in the bot bubble for emergency queries.
#  Called after a successful POST /api/v1/emergency response.
#
#  Sections rendered (in order):
#  1. Emergency banner    — only for high-acuity (life-threatening) cases
#  2. Emergency type header — display title, source label, acuity+source badges
#  3. Horizontal divider
#  4a. Step list          — if source="database" (verified MongoDB record)
#  4b. AI answer text     — if source="llm" (Groq LLM fallback advice)
#  5. First-aid image     — if image path returned by API (served as static)
#  6. Notes callout       — always shown (DB notes or AI disclaimer)
#  7. Follow-up hint      — nudges user toward doctor search or follow-up
# ═══════════════════════════════════════════════════════════════════════════════
def emergency_html(data: dict) -> str:
    is_high = data.get("acuity") == "high"
    is_db   = data.get("source") == "database"
    et      = data.get("emergency_type", "")
    sub     = data.get("subtype", "")
    steps   = data.get("steps") or []
    answer  = data.get("answer", "")
    notes   = data.get("notes", "")
    image   = data.get("image", "")

    html = ""

    # 1. High-acuity emergency banner
    if is_high:
        html += """
        <div class="e-banner">
          <span style="font-size:20px;flex-shrink:0;line-height:1">🚨</span>
          <div>
            <strong>CALL 911 (OR YOUR LOCAL EMERGENCY NUMBER) IMMEDIATELY</strong>
            <span>Contact emergency services first — administer first aid while help is on the way.</span>
          </div>
        </div>"""

    # 2. Header — title, source label, badges
    acuity_badge = '<span class="badge b-high">● High Acuity</span>' if is_high else '<span class="badge b-low">● Low Acuity</span>'
    source_badge = '<span class="badge b-db">✓ Verified DB</span>'   if is_db   else '<span class="badge b-llm">⚡ AI Guidance</span>'
    title        = f"{et}{' — ' + sub if sub else ''}"
    source_label = "Verified medical database" if is_db else "AI-generated guidance (Groq LLM)"

    html += f"""
    <div class="et-header">
      <div class="et-title">{title}</div>
      <div class="et-source">{source_label}</div>
      <div class="badges">{acuity_badge}{source_badge}</div>
    </div>
    <div class="divider"></div>"""

    # 4a. Verified step list
    if is_db and steps:
        html += '<ul class="step-list">'
        for i, s in enumerate(steps):
            is_last = i == len(steps) - 1
            n_cls   = "sn-high" if is_high else "sn-low"
            alert   = '<div class="step-alert">⚠ If person loses consciousness — call emergency services immediately.</div>' if is_high and is_last else ""
            html += f"""
            <li class="step-item">
              <div class="step-num {n_cls}">{s["step_number"]}</div>
              <div class="step-text">{s["instruction"]}{alert}</div>
            </li>"""
        html += '</ul>'

    # 4b. LLM fallback advice
    elif answer:
        html += f'<div class="ai-answer">{answer}</div>'

    # 5. First-aid illustration
    # MongoDB stores "/images/choking/infant.jpeg"
    # FastAPI serves backend/app/images/ at the /images route
    # BACKEND_BASE + image path = full accessible URL
    if image:
        image_url = f"{BACKEND_BASE}{image}"
        html += f"""
        <div class="firstaid-img-wrap">
          <img src="{image_url}" alt="First aid illustration — {et}" />
        </div>
        <div class="img-caption">📷 Illustrated first aid reference</div>"""

    # 6. Notes callout
    if notes:
        note_cls = "note-high" if is_high else "note-low"
        html += f'<div class="{note_cls}">{notes}</div>'

    # 7. Follow-up prompt
    html += '<div class="divider"></div>'
    html += '<div class="followup-hint">Ask a follow-up, or say <b>"check doctor availability"</b> to find a nearby specialist.</div>'

    return html


# ═══════════════════════════════════════════════════════════════════════════════
#  DOCTOR AVAILABILITY CARD HTML
#
#  Renders a structured card for the best available doctor for this emergency.
#  Called after GET /api/v1/doctors/available returns results.
#  Doctor matching: MongoDB doctors have specialty_keys arrays (e.g. ["choking",
#  "default"]). Backend queries by emergency_type, falls back to "default" pool.
# ═══════════════════════════════════════════════════════════════════════════════
def doctor_html(doc: dict, show_book: bool = True) -> str:
    name     = doc.get("doctor_name", "Doctor")
    avail    = doc.get("availability", "")
    status   = doc.get("appointment_status", "")
    location = doc.get("location", "")
    appt     = doc.get("appointment_time")
    initials = get_initials(name)

    slot_row = f"""
    <div class="doc-meta-item dv-full">
      <div class="doc-meta-label">Next Available Slot</div>
      <div class="doc-meta-val dv-blue">{fmt_time(appt)}</div>
    </div>""" if appt else ""

    book_section = """
    <div class="book-cta">
      Say <b>"book appointment"</b> to reserve this slot — I'll collect your details.
    </div>""" if show_book else ""

    return f"""
    <div class="doc-card">
      <div class="doc-card-label">Recommended Specialist</div>
      <div class="doc-row">
        <div class="doc-avatar">{initials}</div>
        <div>
          <div class="doc-name">{name}</div>
          <div class="doc-loc">📍 {location}</div>
        </div>
      </div>
      <div class="doc-meta">
        <div class="doc-meta-item">
          <div class="doc-meta-label">Availability</div>
          <div class="doc-meta-val dv-green">{avail}</div>
        </div>
        <div class="doc-meta-item">
          <div class="doc-meta-label">Booking Status</div>
          <div class="doc-meta-val dv-blue">{status}</div>
        </div>
        {slot_row}
      </div>
      {book_section}
    </div>"""


# ═══════════════════════════════════════════════════════════════════════════════
#  APPOINTMENT CONFIRMATION CARD HTML
#
#  Shown after successful POST /api/v1/appointments.
#  The backend inserts the appointment into MongoDB appointments collection
#  and returns confirmed doctor details, appointment_time, and appointment_id.
# ═══════════════════════════════════════════════════════════════════════════════
def confirmed_html(booking: dict, patient: dict) -> str:
    name     = booking.get("doctor_name", "Doctor")
    location = booking.get("location", "")
    appt     = booking.get("appointment_time", "")
    initials = get_initials(name)

    return f"""
    <div class="confirmed-card">
      <div class="confirmed-title"><span>✅</span> Appointment Confirmed</div>
      <div class="doc-row" style="margin-bottom:10px">
        <div class="doc-avatar" style="background:linear-gradient(135deg,#2ECC8F,#1A8F5F)">{initials}</div>
        <div>
          <div class="doc-name">{name}</div>
          <div class="doc-loc">📍 {location}</div>
        </div>
      </div>
      <div class="divider"></div>
      <div class="confirmed-detail">
        <b>Patient</b>&nbsp;&nbsp; {patient.get("name", "")}<br>
        <b>Phone</b>&nbsp;&nbsp;&nbsp;&nbsp; {patient.get("phone", "")}<br>
        <b>Email</b>&nbsp;&nbsp;&nbsp;&nbsp; {patient.get("email", "")}<br>
        <b>Scheduled</b> {fmt_time(appt) if appt else "To be confirmed"}
      </div>
      <div class="confirmed-footer">
        📋 Your details have been saved. The hospital team will contact you shortly to confirm.
      </div>
    </div>"""


# ═══════════════════════════════════════════════════════════════════════════════
#  CHAT HELPERS
#  bot_say  — appends assistant message (text or HTML) to message history
#  user_say — appends user message to message history
# ═══════════════════════════════════════════════════════════════════════════════
def bot_say(text: str = "", html: str = ""):
    st.session_state.messages.append({"role": "assistant", "content": text, "html": html})

def user_say(text: str):
    st.session_state.messages.append({"role": "user", "content": text, "html": ""})


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN INPUT HANDLER
#
#  Central dispatcher called on every user message submission.
#  Streamlit reruns the entire script on each interaction — this function
#  acts as the controller that decides what happens next.
#
#  Flow A: Booking state machine (multi-step form collected via chat)
#    booking_state: None → ask_name → ask_phone → ask_email → confirm → None
#    Each step reads the text, stores it in booking_info, advances state.
#    On "confirm" → calls api_book_appointment → renders confirmation card.
#
#  Flow B: Intent routing (when not in a booking flow)
#    "book"         → enter booking flow (or check doctors first)
#    "check_doctor" → GET available doctors, cache in pending_doctor
#    "emergency"    → POST to /api/v1/emergency, render full response card
# ═══════════════════════════════════════════════════════════════════════════════
def handle_input(text: str):
    user_say(text)
    bs = st.session_state.booking_state

    # ── A. Booking state machine ──────────────────────────────────────────────
    if bs == "ask_name":
        st.session_state.booking_info["name"] = text.strip()
        st.session_state.booking_state = "ask_phone"
        bot_say("📞 What is your **phone number**?")
        return

    if bs == "ask_phone":
        st.session_state.booking_info["phone"] = text.strip()
        st.session_state.booking_state = "ask_email"
        bot_say("📧 And your **email address**?")
        return

    if bs == "ask_email":
        st.session_state.booking_info["email"] = text.strip()
        st.session_state.booking_state = "confirm"
        info = st.session_state.booking_info
        doc  = st.session_state.pending_doctor or {}
        bot_say(
            f"Please review your details:\n\n"
            f"👤 Name: {info.get('name')}\n"
            f"📞 Phone: {info.get('phone')}\n"
            f"📧 Email: {info.get('email')}\n"
            f"🩺 Doctor: {doc.get('doctor_name', '')}\n\n"
            f"Type **confirm** to book, or **cancel** to abort."
        )
        return

    if bs == "confirm":
        intent = detect_intent(text)
        if intent == "confirm":
            doc     = st.session_state.pending_doctor or {}
            patient = st.session_state.booking_info
            result  = api_book_appointment(
                doctor_id=doc.get("doctor_id", "mock_001"),
                patient=patient,
                emergency_type=st.session_state.last_emergency or "general"
            )
            booking = result if result else doc
            bot_say(html=confirmed_html(booking, patient))
        else:
            bot_say("❌ Booking cancelled. Feel free to ask anything else.")
        st.session_state.booking_state  = None
        st.session_state.booking_info   = {}
        st.session_state.pending_doctor = None
        return

    # ── B. Intent routing ─────────────────────────────────────────────────────
    intent = detect_intent(text)

    if intent == "book":
        doc = st.session_state.pending_doctor
        if not doc:
            bot_say("Let me check doctor availability for your condition first...")
            intent = "check_doctor"
        else:
            st.session_state.booking_state = "ask_name"
            bot_say(f"Let's book an appointment with **{doc.get('doctor_name', '')}**.\n\n👤 What is your **full name**?")
            return

    if intent == "check_doctor":
        et     = st.session_state.last_emergency or "general"
        result = api_check_doctor(et)
        docs   = (result or {}).get("doctors", [])
        doc    = docs[0] if docs else {
            "doctor_name":        "Dr. Sarah Chen (Cardiologist)",
            "availability":       "Available Now",
            "appointment_status": "Ready to Book",
            "location":           "City General Hospital — 1.2 miles away",
            "appointment_time":   "2026-04-07T10:00:00",
            "doctor_id":          "mock_001",
        }
        st.session_state.pending_doctor = doc
        bot_say(html=doctor_html(doc, show_book=True))
        return

    # Emergency / follow-up query → LLM classification pipeline
    try:
        data = api_assess(text)
        et   = data.get("emergency_type", "").lower().replace(" ", "_")
        st.session_state.last_emergency = et
        bot_say(html=emergency_html(data))
    except requests.exceptions.ConnectionError:
        bot_say("⚠️ Cannot reach the backend. Please ensure FastAPI is running on port 8000.")
    except Exception as e:
        bot_say(f"Something went wrong: {str(e)}")


# ═══════════════════════════════════════════════════════════════════════════════
#  SIDEBAR
#  — Quick scenario buttons pre-fill common emergency queries
#  — Usage guide for available voice commands
#  — Clear conversation button resets all session_state keys
# ═══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("### 🏥 MediAssist AI")
    st.markdown("---")
    st.markdown(
        '<p style="font-size:10px;font-weight:600;letter-spacing:0.1em;'
        'text-transform:uppercase;color:#5A7090;margin-bottom:8px">Quick Scenarios</p>',
        unsafe_allow_html=True
    )
   
    

    st.markdown("---")
    st.markdown(
        '<p style="font-size:10px;font-weight:600;letter-spacing:0.1em;'
        'text-transform:uppercase;color:#5A7090;margin-bottom:8px">You Can Say</p>',
        unsafe_allow_html=True
    )
    st.markdown("""
<div style="font-size:12px;line-height:2.1;color:#5A7090">
  <i>"What do I do for a heart attack?"</i><br>
  <i>"Check doctor availability"</i><br>
  <i>"Book an appointment"</i><br>
  <i>"Is CPR safe for children?"</i>
</div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    if st.button("🗑️  Clear Conversation", use_container_width=True):
        for k, v in defaults.items():
            st.session_state[k] = v
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
#  APP HEADER
#  Top bar: logo + title + subtitle + live status indicator
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<div class="app-header">
  <div class="app-header-left">
    <div class="app-logo">
      <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
        <rect x="9.5" y="1"   width="3" height="20" rx="1.5" fill="white"/>
        <rect x="1"   y="9.5" width="20" height="3"  rx="1.5" fill="white"/>
      </svg>
    </div>
    <div>
      <div class="app-title">MediAssist AI</div>
      <div class="app-subtitle">Emergency Guidance &nbsp;·&nbsp; Doctor Search &nbsp;·&nbsp; Appointment Booking</div>
    </div>
  </div>
  <div class="status-pill">
    <div class="status-dot"></div>
    Live
  </div>
</div>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  WELCOME MESSAGE
#  Shown only when the message history is empty (first load / after clear).
#  Uses a 2×2 capability grid and an example query prompt.
# ═══════════════════════════════════════════════════════════════════════════════
if not st.session_state.messages:
    bot_say(html="""
    <div>
      <div class="welcome-title">Hello — I'm your AI First Aid Assistant.</div>
      <div class="welcome-body">
        Describe any medical emergency and I'll give you verified, step-by-step
        first aid guidance, connect you with an available specialist, and help
        you book an appointment — all in one conversation.
      </div>
      <div class="capability-grid">
        <div class="cap-item"><b>🚑 First Aid Steps</b>Verified, step-by-step guidance for any emergency</div>
        <div class="cap-item"><b>🔍 Doctor Search</b>Find available specialists matched to your condition</div>
        <div class="cap-item"><b>📅 Appointment Booking</b>Book and confirm in under 60 seconds</div>
        <div class="cap-item"><b>💬 Follow-up Q&amp;A</b>Ask anything — powered by LLM</div>
      </div>
      <div class="welcome-example">
        Try: <i>"Someone near me is having a heart attack, what do I do?"</i>
      </div>
    </div>
    """)


# ═══════════════════════════════════════════════════════════════════════════════
#  MESSAGE RENDERING LOOP
#
#  Iterates through st.session_state.messages and renders each bubble.
#  — User messages: right-aligned dark bubble, plain text
#  — Bot messages:  left-aligned surface bubble, raw HTML via unsafe_allow_html
#
#  Streamlit re-renders ALL messages on each rerun (no virtual DOM diffing).
#  This is why animation is applied via CSS (fadeUp) rather than JS — CSS
#  animations re-trigger on element re-insertion during rerun.
# ═══════════════════════════════════════════════════════════════════════════════
for msg in st.session_state.messages:
    is_user    = msg["role"] == "user"
    html_c     = msg.get("html", "")
    text_c     = msg.get("content", "")
    row_cls    = "msg-row user" if is_user else "msg-row"
    bubble_cls = "bubble bubble-user" if is_user else "bubble bubble-bot"
    avatar_cls = "avatar avatar-user" if is_user else "avatar avatar-bot"
    avatar_lbl = "You" if is_user else "🏥"

    inner = html_c if (html_c and not is_user) else f'<div style="white-space:pre-wrap;font-size:13.5px">{text_c}</div>'

    st.markdown(f"""
    <div class="{row_cls}">
      <div class="{avatar_cls}">{avatar_lbl}</div>
      <div class="{bubble_cls}">{inner}</div>
    </div>
    """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  INPUT ROW
#
#  st.columns([6,1]) — 6:1 ratio gives text field dominant width.
#  key="chat_input"  — Streamlit tracks this widget by key across reruns.
#  On send: handle_input() appends messages, st.rerun() refreshes the view.
#  st.rerun() causes a full script re-execution which re-renders the updated
#  messages list — this is the standard Streamlit chat update pattern.
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("<div style='height:1.2rem'></div>", unsafe_allow_html=True)
col1, col2 = st.columns([6, 1])
with col1:
    user_input = st.text_input(
        label="message",
        placeholder="Describe the emergency or ask a medical question…",
        label_visibility="collapsed",
        key="chat_input",
    )
with col2:
    send = st.button("Send ➤", use_container_width=True, type="primary")

if send and user_input.strip():
    handle_input(user_input.strip())
    st.rerun()