"""
HisabBot — Router Node (Node 1).

Classifies the user's message into one or more intents, extracts all entities
(customer, items, amounts, address/qualifier), and normalises qualifier fields
so same-name customer disambiguation works correctly downstream.
"""

import json
import re as _re
from .config import groq_client, MODEL
from .prompts.router_prompt import ROUTER_PROMPT


# ── Pakistani cities + descriptors used to identify "which Ali" ──────────────
CITY_WORDS = {
    "sialkot","sailkot","lahore","karachi","islamabad","rawalpindi","pindi",
    "faisalabad","multan","peshawar","quetta","gujranwala","sargodha",
    "hyderabad","abbottabad","bahawalpur","sukkur","larkana",
    "gujrat","sheikhupura","rahim yar khan","sahiwal","okara","jhang",
    "market","purana","naya","bada","chota","chhota","upar","neeche","pehlay",
    "kala","safed","chowk","qasbati","mandi","bandar","sher","raja",
    "g9","g10","g11","f6","f7","f8","dha","gulberg","johar","defence",
    "model town","clifton","pechs","nazimabad","korangi","landhi",
    "cantonment","cantt","saddar",
}

JUNK_QUALIFIERS = {
    "waly","walay","wala","wali","valy","valay","vala","vale","wale",
    "ko","ne","ka","ki","ke","se","sy","par","per","nay","nai","jo",
}

VALID_INTENTS = {
    "stock_write","stock_read","sales_write","sales_read",
    "customer_write","customer_read","finance_write","finance_read",
    "conversation","unknown",
}


def _extract_qualifier(name: str):
    """
    Parse "ali islamabad waly" / "islamabad waly ali" / "ali address islamabad"
    etc. into (base_name, qualifier).

    Handles all word-orders and common spelling variants of waly/wala/valy.
    Returns (original_name, None) if no location qualifier is found.
    """
    # Strip trailing Urdu function words: "ali islamabad waly ko" → "ali islamabad waly"
    FUNC_WORDS = r'(?:\s+(?:ko|ne|ka|ki|ke|se|sy|par|per|nay|nai|nein))+\s*$'
    name = _re.sub(FUNC_WORDS, '', name.strip(), flags=_re.I)
    n    = ' '.join(name.lower().split())

    WALY = r'(?:waly|walay|wala|wali|valy|valay|vala|vale|wale|waale)'

    # Pattern A: <city> waly <name>   e.g. "islamabad waly ali"
    mA = _re.match(rf'^(.+?)\s+{WALY}\s+(.+)$', n, _re.I)
    if mA:
        return mA.group(2).strip(), mA.group(1).strip()

    # Pattern B: <name> <city> waly   e.g. "ali islamabad waly"
    mB = _re.match(rf'^(.+?)\s+(.+?)\s+{WALY}$', n, _re.I)
    if mB:
        return mB.group(1).strip(), mB.group(2).strip()

    # Pattern C: <name> waly <city>   e.g. "ali waly islamabad"  (rare)
    mC = _re.match(rf'^(.+?)\s+{WALY}\s+(.+)$', n, _re.I)
    if mC:
        return mC.group(1).strip(), mC.group(2).strip()

    # Pattern D: <name> address <city>
    mD = _re.match(r'^(.+?)\s+address\s+(.+)$', n, _re.I)
    if mD:
        return mD.group(1).strip(), mD.group(2).strip()

    # Pattern E: <name> jo <city> mein / <name> <city> ka
    mE = _re.match(r'^(.+?)\s+(?:jo\s+)?(.+?)\s+(?:mein|ka|ki|ke|se|sy)$', n, _re.I)
    if mE:
        possible_city = mE.group(2).strip()
        if any(c in possible_city for c in CITY_WORDS):
            return mE.group(1).strip(), possible_city

    # Pattern F: known city word bare at start or end
    words = n.split()
    if len(words) >= 2:
        for i in range(1, len(words)):
            prefix = " ".join(words[:i])
            suffix = " ".join(words[i:])
            if any(c == prefix or c in prefix for c in CITY_WORDS):
                return suffix, prefix
        for i in range(len(words) - 1, 0, -1):
            suffix = " ".join(words[i:])
            prefix = " ".join(words[:i])
            if any(c == suffix or c in suffix for c in CITY_WORDS):
                return prefix, suffix

    return name, None


def _normalise_tasks(tasks: list) -> list:
    """
    Post-process LLM task list:
      - Ensure items is always a list.
      - Validate and clean qualifier fields.
      - Extract qualifier from customer name if LLM missed it.
    """
    for task in tasks:
        if not isinstance(task.get("items"), list):
            task["items"] = []

        existing_q   = (task.get("qualifier") or "").lower().strip()
        raw_customer = (task.get("customer")  or "").strip()

        # LLM gave a good qualifier — propagate to address if not already set
        if existing_q and existing_q not in JUNK_QUALIFIERS:
            if not task.get("address"):
                task["address"] = existing_q
            continue

        # Try Python patterns on the raw customer string
        if not raw_customer:
            continue

        base_name, qualifier = _extract_qualifier(raw_customer)
        if qualifier and qualifier.lower() not in JUNK_QUALIFIERS:
            task["customer"]  = base_name
            task["qualifier"] = qualifier
            if not task.get("address"):
                task["address"] = qualifier
        elif not qualifier and existing_q in JUNK_QUALIFIERS:
            task["qualifier"] = None   # clear junk value from LLM

    return tasks


# ─────────────────────────────────────────────────────────────────────────────
#  ROUTER NODE
# ─────────────────────────────────────────────────────────────────────────────

async def router_node(state: dict) -> dict:
    """
    LangGraph node — classifies the user message into task(s) with intent + entities.

    Passes the last 4 conversation turns as context so follow-up messages
    (e.g. "daal price 3000" after a prior sale) are handled correctly.
    """
    history = state.get("conversation_history") or []
    prior   = history[-4:] if len(history) > 4 else history

    messages = [{"role": "system", "content": ROUTER_PROMPT}]
    if prior:
        history_text = "\n".join(
            f"{'User' if h['role'] == 'user' else 'Agent'}: {h['content']}"
            for h in prior
        )
        messages.append({
            "role": "user",
            "content": (
                f"=== PREVIOUS CONVERSATION (for context only) ===\n"
                f"{history_text}\n"
                f"=== END CONTEXT ===\n\n"
                f"New message: {state['user_message']}"
            ),
        })
    else:
        messages.append({"role": "user", "content": state["user_message"]})

    res = await groq_client.chat.completions.create(
        messages=messages,
        model=MODEL,
        response_format={"type": "json_object"},
        temperature=0.0,
    )

    try:
        out = json.loads(res.choices[0].message.content)
    except Exception:
        out = {"tasks": [{"intent": "unknown", "action": "", "items": []}]}

    tasks = out.get("tasks", [])
    if not isinstance(tasks, list) or not tasks:
        tasks = [{"intent": "unknown", "action": "", "items": []}]

    # Validate intents — reject anything not in the allowed set
    for task in tasks:
        if task.get("intent") not in VALID_INTENTS:
            task["intent"] = "unknown"

    tasks = _normalise_tasks(tasks)

    return {
        "tasks":            tasks,
        "intent":           tasks[0].get("intent", "unknown"),
        "action":           tasks[0].get("action", ""),
        "entities":         tasks[0],
        "extracted_intent": out,
    }