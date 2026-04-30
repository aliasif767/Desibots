"""
WhatsApp Multi-Bot Dispatcher
==============================
Single WhatsApp number routes messages to all Desibots bots.

Commands (case-insensitive):
  /hisabbot    → HisabBot  (Finance & Accounting)    :8511
  /sehatbot    → SehatBot  (First Aid & Medical)     :8510
  /pakorderbot → PakOrderBot (Food Ordering)         :8512
  /lawyerbot   → LawyerBot (Pakistan Legal)          :8513
  /help        → Show available bots
  /status      → Show currently active bot

All other messages are forwarded to the currently active bot.
Default bot is HisabBot.
"""

import os
import httpx
import logging
from datetime import datetime
from fastapi import APIRouter, Request, Response
from twilio.twiml.messaging_response import MessagingResponse

router = APIRouter(tags=["whatsapp-dispatcher"])
logger = logging.getLogger(__name__)

# ── Bot registry ──────────────────────────────────────────────────────────────
# Each bot entry: url, description, call_fn (async function to call)
BOT_REGISTRY = {
    "hisabbot": {
        "name":        "💰 HisabBot",
        "description": "Finance, accounting & business reports",
        "url":         os.getenv("HISABBOT_URL", "http://127.0.0.1:8511"),
        "type":        "hisabbot",
    },
    "sehatbot": {
        "name":        "🏥 SehatBot",
        "description": "First aid, medical help & doctor booking",
        "url":         os.getenv("SEHATBOT_URL", "http://127.0.0.1:8510"),
        "type":        "sehatbot",
    },
    "pakorderbot": {
        "name":        "🍔 PakOrderBot",
        "description": "Food ordering & restaurant management",
        "url":         os.getenv("PAKORDERBOT_URL", "http://127.0.0.1:8512"),
        "type":        "pakorderbot",
    },
    "lawyerbot": {
        "name":        "⚖️ LawyerBot",
        "description": "Pakistan legal advice & lawyer booking",
        "url":         os.getenv("LAWYERBOT_URL", "http://127.0.0.1:8513"),
        "type":        "lawyerbot",
    },
}

DEFAULT_BOT = "hisabbot"

# ── MongoDB session store ───────────────────────────────────────────────────
from app.db.session import client
db_main = client["desibots_main"]
sessions_col = db_main["whatsapp_sessions"]

async def get_session(phone: str):
    session = await sessions_col.find_one({"phone_number": phone})
    if not session:
        session = {
            "phone_number": phone,
            "active_bot":   DEFAULT_BOT,
            "history":      [],
        }
        await sessions_col.insert_one(session)
    return session

async def save_session(session: dict):
    await sessions_col.replace_one({"phone_number": session["phone_number"]}, session)

# ── Help text ─────────────────────────────────────────────────────────────────
def _help_text() -> str:
    lines = ["🤖 *Desibots — Multi-Bot Hub*\n"]
    lines.append("Type a command to switch bots:\n")
    for cmd, info in BOT_REGISTRY.items():
        lines.append(f"  /{cmd}\n  {info['name']} — {info['description']}\n")
    lines.append("\n📌 Other commands:\n  /status — show active bot\n  /help   — show this menu")
    return "\n".join(lines)

def _status_text(active: str) -> str:
    info = BOT_REGISTRY.get(active, {})
    return (
        f"✅ Active bot: {info.get('name', active)}\n"
        f"📝 {info.get('description', '')}\n\n"
        f"Type /help to see all available bots."
    )

def _switched_text(bot_key: str) -> str:
    info = BOT_REGISTRY[bot_key]
    return (
        f"✅ Switched to {info['name']}!\n"
        f"📝 {info['description']}\n\n"
        f"You can now send your message. Type /help for other bots."
    )

# ── Bot-specific HTTP callers ─────────────────────────────────────────────────

async def _call_hisabbot(url: str, message: str, history: list) -> str:
    """POST /chat  →  { reply }"""
    async with httpx.AsyncClient(timeout=30) as client_http:
        r = await client_http.post(f"{url}/chat", json={
            "message": message,
            "history": history,
        })
        r.raise_for_status()
        data = r.json()
        return data.get("reply", "HisabBot se jawab nahi mila.")

async def _call_sehatbot(url: str, message: str, history: list) -> str:
    """POST /api/v1/chat  →  { intent, response_type, data: { FirstAidResponse } }"""
    ctx = " ".join([h["content"] for h in history[-4:]])
    try:
        async with httpx.AsyncClient(timeout=30) as client_http:
            r = await client_http.post(f"{url}/api/v1/chat", json={
                "message": message,
                "context": ctx,
            })
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.error(f"Error calling SehatBot: {e}")
        return "⚠️ SehatBot is currently busy. Please try again in a moment."

    if not isinstance(data, dict):
        return str(data)

    # 1. Extract from wrapper if present
    bot_response = data
    if "response_type" in data and "data" in data:
        resp_type = data["response_type"]
        bot_data = data["data"]
        
        if resp_type == "followup":
            return bot_data if isinstance(bot_data, str) else str(bot_data)
        
        if resp_type == "emergency" and isinstance(bot_data, dict):
            bot_response = bot_data
        else:
            # Fallback for intent_only or other types
            return str(bot_data) if bot_data else "I'm not sure how to help with that. Try /help."

    # 2. Professional Formatting for FirstAidResponse
    if isinstance(bot_response, dict) and ("emergency_type" in bot_response or "steps" in bot_response):
        et = bot_response.get("emergency_type", "Medical Issue").replace("_", " ").title()
        sub = bot_response.get("subtype")
        acuity = bot_response.get("acuity", "medium").upper()
        
        priority_emoji = "🚨" if acuity == "HIGH" else "⚠️" if acuity == "MEDIUM" else "ℹ️"
        header = f"{priority_emoji} *SEHATBOT: {et}*"
        if sub:
            header += f" ({sub.title()})"
        header += f"\n*Priority:* {acuity}\n"
        
        sections = [header]
        
        # Summary/Answer
        answer = bot_response.get("answer")
        if answer:
            sections.append(f"📝 {answer}")
        
        # Actionable Steps
        steps = bot_response.get("steps")
        if steps:
            sections.append("\n✅ *Immediate Action Steps:*")
            for s in steps:
                num = s.get("step_number", "")
                instr = s.get("instruction", "")
                sections.append(f"{num}. {instr}")
        
        # Medical Follow-up / Doctor
        mf = bot_response.get("medical_followup")
        if mf and isinstance(mf, dict) and mf.get("doctor_name"):
            sections.append("\n👨‍⚕️ *Recommended Specialist:*")
            name = mf.get("doctor_name")
            spec = mf.get("specialty", "General Physician")
            loc = mf.get("location", "")
            time = mf.get("appointment_time")
            
            sections.append(f"• *{name}* ({spec})")
            if loc: sections.append(f"• {loc}")
            
            if time:
                try:
                    # Parse ISO format (e.g. 2026-04-07T09:04:02)
                    dt_obj = datetime.fromisoformat(time.replace("Z", "+00:00"))
                    time_str = dt_obj.strftime("%I:%M %p, %d %b")
                    sections.append(f"• Next Slot: {time_str}")
                except:
                    pass
            
            status = mf.get("appointment_status")
            if status == "Ready to Book":
                sections.append("\n_Type 'book' if you want me to schedule this for you._")
        
        # Notes / Warnings
        notes = bot_response.get("notes")
        if notes:
            sections.append(f"\n📌 *Note:* {notes}")
            
        return "\n".join(sections)

    # 3. Fallback for simple key-value responses
    for key in ("answer", "reply", "response", "message", "result"):
        if data.get(key):
            val = data[key]
            return val if isinstance(val, str) else str(val)

    return "I processed your request but couldn't format the response. Please try rephrasing."


async def _call_pakorderbot(url: str, message: str, history: list) -> str:
    """POST /chat  →  { reply }"""
    async with httpx.AsyncClient(timeout=30) as client_http:
        r = await client_http.post(f"{url}/chat", json={
            "message": message,
            "history": history,
        })
        r.raise_for_status()
        data = r.json()
        return data.get("reply", "PakOrderBot se jawab nahi mila.")


async def _call_lawyerbot(url: str, message: str, history: list) -> str:
    """POST /chat  →  { response }"""
    # LawyerBot uses 'query' not 'message'
    hw = [{"role": h["role"], "content": h["content"]} for h in history[-4:]]
    async with httpx.AsyncClient(timeout=30) as client_http:
        r = await client_http.post(f"{url}/chat", json={
            "query":   message,
            "history": hw,
        })
        r.raise_for_status()
        data = r.json()
        return data.get("response", "LawyerBot se jawab nahi mila.")


BOT_CALLERS = {
    "hisabbot":    _call_hisabbot,
    "sehatbot":    _call_sehatbot,
    "pakorderbot": _call_pakorderbot,
    "lawyerbot":   _call_lawyerbot,
}

# ── Main dispatcher logic ─────────────────────────────────────────────────────

async def dispatch(phone: str, message: str) -> str:
    """
    Handles routing logic:
    1. If message is a /command → switch bot or show help/status
    2. Otherwise → forward to active bot
    """
    session = await get_session(phone)
    text    = message.strip()

    # ── Command handling ─────────────────────────────────────────────────
    if text.startswith("/"):
        cmd = text[1:].lower().split()[0]  # e.g. "/hisabbot hello" → "hisabbot"

        if cmd == "help":
            return _help_text()

        if cmd == "status":
            return _status_text(session["active_bot"])

        if cmd in BOT_REGISTRY:
            session["active_bot"] = cmd
            session["history"]    = []  # reset history on bot switch
            await save_session(session)
            return _switched_text(cmd)

        # Unknown command — show help
        return (
            f"❓ Unknown command: /{cmd}\n\n"
            + _help_text()
        )

    # ── Forward to active bot ─────────────────────────────────────────────
    active   = session["active_bot"]
    bot_info = BOT_REGISTRY[active]
    caller   = BOT_CALLERS[active]
    history  = session["history"]

    try:
        reply = await caller(bot_info["url"], text, history)
    except httpx.ConnectError:
        reply = (
            f"⚠️ {bot_info['name']} is currently offline.\n"
            f"Please try again later or switch to another bot (/help)."
        )
    except httpx.TimeoutException:
        reply = f"⏳ {bot_info['name']} timed out. Please try again."
    except Exception as e:
        logger.error(f"Error calling {active}: {e}")
        reply = f"❌ Error: {bot_info['name']} encountered a problem. Try again."

    # Update history
    history.append({"role": "user",      "content": text})
    history.append({"role": "assistant", "content": reply})
    if len(history) > 20:
        history = history[-20:]
    session["history"] = history
    await save_session(session)

    return reply


# ── FastAPI route ─────────────────────────────────────────────────────────────

@router.post("/wa")
@router.post("/wa/webhook")
async def whatsapp_dispatcher_webhook(request: Request):
    """
    Unified WhatsApp webhook — receives all Twilio messages and
    routes them to the correct Desibot based on active session.
    Set this as your Twilio sandbox webhook URL:
        https://<ngrok>/wa
    """
    form_data    = await request.form()
    incoming_msg = form_data.get("Body", "").strip()
    sender       = form_data.get("From", "")

    logger.info(f"[Dispatcher] From={sender} Msg={incoming_msg[:80]}")

    if not incoming_msg:
        return Response(content=str(MessagingResponse()), media_type="application/xml")

    reply = await dispatch(sender, incoming_msg)

    twiml = MessagingResponse()
    twiml.message(reply)
    return Response(content=str(twiml), media_type="application/xml")
