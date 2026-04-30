"""
HisabBot — Responder Node (Node 4).

Converts raw DB results into clean Roman Urdu responses.
Handles all special-prefix strings (PAYMENT_OK, STOCK_ERROR, EMPTY_RESULT, etc.)
directly in Python — never sends these to the LLM to prevent hallucination.
Only structured read results (lists / dicts) go to the LLM for formatting.
"""

import json
import re as _re
from .config import groq_client, MODEL
from .prompts.responder_prompt import RESPONDER_PROMPT


# ── Empty-result message map (action keyword → helpful Roman Urdu message) ───
EMPTY_MESSAGES = {
    "check stock": (
        "Abhi inventory mein koi item record nahi hai.\n"
        "Stock add karne ke liye likhen, e.g.:\n"
        "  '200 bags cheeni price 5000 stock mein add karo'"
    ),
    "daily sales": (
        "Aaj abhi tak koi sale record nahi ki gayi.\n"
        "Sale record karne ke liye likhen, e.g.:\n"
        "  'ali ko 50 bags cheeni price 6000 de do'"
    ),
    "daily sales report": (
        "Aaj abhi tak koi sale record nahi ki gayi.\n"
        "Sale record karne ke liye likhen, e.g.:\n"
        "  'ali ko 50 bags cheeni price 6000 de do'"
    ),
    "sales report": (
        "Is period mein koi sale record nahi mili.\n"
        "Pehle kuch sales record karen, phir report dekhen."
    ),
    "daily sales and profit": (
        "Aaj abhi tak koi sale record nahi ki gayi.\n"
        "Sale record karne ke liye likhen, e.g.:\n"
        "  'ali ko 50 bags cheeni price 6000 de do'"
    ),
    "check customer balance": (
        "Is naam ka koi customer database mein nahi mila.\n"
        "Naya customer add karne ke liye likhen, e.g.:\n"
        "  'ali add karo number 0300-1234567 address lahore'"
    ),
    "check balance": (
        "Koi customer record nahi mila.\n"
        "Customer add karne ke liye unka naam aur number den."
    ),
    "customer info": (
        "Is naam ka koi customer database mein nahi mila.\n"
        "Pehle customer add karen ya sahi naam check karen."
    ),
    "payment history": (
        "Is customer ka koi payment record nahi mila.\n"
        "Payment record karne ke liye likhen, e.g.:\n"
        "  'ali ne 5000 rupay diye'"
    ),
    "generate invoice": (
        "Is customer ka koi purchase record nahi mila.\n"
        "Pehle sales record karen, phir bill check karen."
    ),
    "customer bill": (
        "Is customer ka koi purchase record nahi mila.\n"
        "Pehle sales record karen, phir bill check karen."
    ),
    "view bill": (
        "Is customer ka koi purchase record nahi mila.\n"
        "Pehle sales record karen, phir bill check karen."
    ),
    "check bill": (
        "Is customer ka koi purchase record nahi mila.\n"
        "Pehle sales record karen, phir bill check karen."
    ),
    "customer invoice": (
        "Is customer ka koi purchase record nahi mila.\n"
        "Pehle sales record karen, phir bill check karen."
    ),
    "finance report": (
        "Koi payment ya finance record nahi mila.\n"
        "Payments record karne ke baad yahan history dikhe gi."
    ),
    "top products": (
        "Abhi tak koi sale record nahi ki gayi.\n"
        "Jab sales honi shuru hongi, top products yahan dikhen ge."
    ),
    "top customers": (
        "Abhi tak koi sale record nahi ki gayi.\n"
        "Jab sales honi shuru hongi, top customers yahan dikhen ge."
    ),
    "profit report": (
        "Abhi tak koi sale record nahi, isliye profit bhi nahi.\n"
        "Sales record karne ke baad profit report dekh sakte hain."
    ),
    "loss report": (
        "Alhamdulillah! Database mein koi nuqsan record nahi mila.\n"
        "Sab sales abhi tak profitable hain."
    ),
    "kaunsa product": (
        "Abhi tak koi sale record nahi ki gayi.\n"
        "Product comparison tab hoga jab kuch sales ho jayen."
    ),
}


def _empty_message(action: str, user_msg: str) -> str:
    """Return the best empty-result message for a given action/user message."""
    action_l  = action.lower()
    user_msg_l = user_msg.lower()
    for key, val in EMPTY_MESSAGES.items():
        if key in action_l or key in user_msg_l:
            return val
    return (
        "Is query ke liye koi record nahi mila database mein.\n"
        "Pehle data enter karen, phir dobara check karen."
    )


def _format_payment_ok(db_result: str) -> str:
    """Parse PAYMENT_OK:... string and return a formatted confirmation."""
    params = {}
    for part in db_result.replace("PAYMENT_OK:", "").split(","):
        if "=" in part:
            k, _, v = part.partition("=")
            params[k.strip()] = v.strip()

    customer  = params.get("customer", "?")
    address   = params.get("address", "").strip()
    amount    = params.get("amount", "?")
    remaining = params.get("remaining", "0")

    try:
        amt_fmt = f"Rs {float(amount):,.0f}"
        rem_fmt = f"Rs {float(remaining):,.0f}"
        rem_val = float(remaining)
    except Exception:
        amt_fmt = f"Rs {amount}"
        rem_fmt = f"Rs {remaining}"
        rem_val = 1  # assume nonzero if parse fails

    addr_part = f" ({address})" if address else ""
    rem_line  = "Ab koi baaki nahi." if rem_val <= 0 else f"Remaining baaki: {rem_fmt}"
    return f"{customer}{addr_part} se {amt_fmt} payment mil gayi.\n{rem_line}"


def _format_stock_error(db_result: str) -> str:
    """Parse STOCK_ERROR:... string and return clean Roman Urdu lines."""
    errors = db_result.replace("STOCK_ERROR:", "").strip().split(" | ")
    lines  = ["Sale nahi ho saki — stock kam hai:"]
    for err in errors:
        lines.append(f"  {err.replace('ERROR:', '').strip()}")
    lines.append("Pehle stock bharein, phir sale record karein.")
    return "\n".join(lines)


def _format_customer_ambiguous(db_result: str) -> str:
    """Parse CUSTOMER_AMBIGUOUS:... string and return a clarification prompt."""
    rest         = db_result.replace("CUSTOMER_AMBIGUOUS:", "")
    pipe         = rest.find("|")
    name         = rest[:pipe] if pipe != -1 else rest
    options_text = rest[pipe + 1:] if pipe != -1 else ""
    return (
        f"'{name}' naam ke multiple customers hain.\n"
        f"Kaunsa wala matlab hai?\n\n"
        f"{options_text}\n\n"
        f"Address ya phone number ke saath batain, e.g.:\n"
        f"  '{name.lower()} lahore wala ko sale karo'"
    )


def _format_missing_price(db_result: str, is_cost: bool) -> str:
    """Format MISSING_PRICE / MISSING_COST_PRICE responses."""
    prefix    = "MISSING_COST_PRICE:" if is_cost else "MISSING_PRICE:"
    price_lbl = "cost price (khareed qeemat)" if is_cost else "selling price"
    products  = db_result.replace(prefix, "").strip()
    prod_list = [p.strip() for p in products.split(",") if p.strip()]

    if len(prod_list) == 1:
        p = prod_list[0]
        return (
            f"{p} ki {price_lbl} nahi di.\n"
            f"Aglay message mein price batain, e.g.:\n"
            f"  '{p.lower()} price {'5000' if is_cost else '3000'}'"
        )
    items_str = "\n".join(f"  - {p}" for p in prod_list)
    examples  = ", ".join(f"{p.lower()} price XXXX" for p in prod_list)
    return (
        f"In items ki {price_lbl} nahi di:\n{items_str}\n\n"
        f"Aglay message mein prices batain, e.g.:\n"
        f"  '{examples}'"
    )


# ─────────────────────────────────────────────────────────────────────────────
#  RESPONDER NODE (LangGraph Node 4)
# ─────────────────────────────────────────────────────────────────────────────

async def responder_node(state: dict) -> dict:
    """
    Convert the db_result into a clean Roman Urdu response.
    Special prefix strings are handled in Python.
    Structured data (lists/dicts) are sent to the LLM with RESPONDER_PROMPT.
    """
    tasks    = state.get("tasks") or []
    intent   = tasks[0].get("intent", "") if tasks else state.get("intent", "")
    user_msg = state.get("user_message", "")

    # ── Conversation recap — no DB involved ──────────────────────────────────
    if intent == "conversation":
        history = state.get("conversation_history") or []
        if not history:
            return {"final_response": "Abhi tak koi conversation nahi hui. Yeh pehla message hai."}
        last_turns = history[-4:]
        lines = [
            f"{'Aapne kaha' if h['role'] == 'user' else 'Maine kaha'}: "
            f"{h['content'][:300]}{'...' if len(h['content']) > 300 else ''}"
            for h in last_turns
        ]
        res = await groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": (
                    "You are HisabBot. The user is asking about the recent conversation. "
                    "Answer in Roman Urdu (Urdu words in English letters). "
                    "Be concise and direct. Only refer to what is in the conversation history provided."
                )},
                {"role": "user", "content": (
                    f"Recent conversation:\n{chr(10).join(lines)}\n\nUser is asking: {user_msg}"
                )},
            ],
            model=MODEL,
            temperature=0.0,
        )
        return {"final_response": res.choices[0].message.content}

    # ── No db_result at all ──────────────────────────────────────────────────
    db_result = (state.get("db_result") or "").strip()
    if not db_result:
        user_lower = user_msg.lower()
        if any(w in user_lower for w in ["stock", "inventory"]):
            msg = "Abhi inventory mein koi item record nahi hai.\nStock add karne ke liye likhen, e.g.:\n  '200 bags cheeni price 5000 add karo'"
        elif any(w in user_lower for w in ["sale", "bika", "profit", "munafa"]):
            msg = "Abhi tak koi sale record nahi ki gayi.\nSales record honi shuru hongi to yahan dikhen gi."
        else:
            msg = "Koi record nahi mila.\nPehle data enter karen, phir dobara check karen."
        return {"final_response": msg}

    # ── Special-prefix handlers (all Python, no LLM) ─────────────────────────
    if db_result.startswith("ERROR:"):
        return {"final_response": db_result.replace("ERROR:", "").strip()}

    if db_result.startswith("EMPTY_RESULT:"):
        action = db_result.replace("EMPTY_RESULT:", "").strip()
        return {"final_response": _empty_message(action, user_msg)}

    if db_result.startswith("CUSTOMER_AMBIGUOUS:"):
        return {"final_response": _format_customer_ambiguous(db_result)}

    if db_result.startswith("MISSING_COST_PRICE:"):
        return {"final_response": _format_missing_price(db_result, is_cost=True)}

    if db_result.startswith("MISSING_PRICE:"):
        return {"final_response": _format_missing_price(db_result, is_cost=False)}

    if db_result.startswith("PAYMENT_OK:"):
        return {"final_response": _format_payment_ok(db_result)}

    if db_result.startswith("STOCK_ERROR:"):
        return {"final_response": _format_stock_error(db_result)}

    # ── Structured data → LLM formatter ─────────────────────────────────────
    try:
        parsed    = json.loads(db_result)
        formatted = json.dumps(parsed, indent=2, ensure_ascii=False, default=str)
    except Exception:
        formatted = db_result

    res = await groq_client.chat.completions.create(
        messages=[
            {"role": "system", "content": RESPONDER_PROMPT},
            {"role": "user", "content": (
                f"User ne kaha: \"{user_msg}\"\n\n"
                f"=== DATABASE RESULT (ONLY use data from here) ===\n"
                f"{formatted}\n"
                f"=== END OF DATABASE RESULT ===\n\n"
                f"Format this data in Roman Urdu. "
                f"Do NOT add any numbers or names not present in the database result above."
            )},
        ],
        model=MODEL,
        temperature=0.0,
    )
    response = res.choices[0].message.content
    response = _re.sub(r"<[^>]*>", "", response).strip()
    return {"final_response": response}