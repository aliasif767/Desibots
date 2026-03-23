"""
HisabBot Agent Nodes — v6 (Specialized Query Builders)

Architecture:
  1. router_node         — detects ALL intents in the message (multi-intent support)
  2. dispatch_node       — splits into sub-tasks, runs specialized query builders in parallel
  3. query_executor_node — executes all plans against MongoDB
  4. responder_node      — formats combined results into Roman Urdu

Specialized query builders (only receive the schema they need):
  - stock_query_builder    (~400 tokens)
  - sales_query_builder    (~500 tokens)
  - customer_query_builder (~350 tokens)
  - finance_query_builder  (~350 tokens)
  - analytics_query_builder (~600 tokens) — for cross-collection reports
"""

import json
import os
import asyncio
from groq import AsyncGroq
from .db_executor import execute_plan

groq_client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
MODEL = "llama-3.3-70b-versatile"


# ─────────────────────────────────────────────────────────────────────────────
#  SHARED: Date placeholders (sent to every builder)
# ─────────────────────────────────────────────────────────────────────────────

DATE_RULES = """
=== DATE PLACEHOLDERS (Python resolves at runtime) ===
"__TODAY_START__"          = today 00:00 UTC
"__TODAY_END__"            = today 23:59 UTC
"__WEEK_START__"           = 7 days ago 00:00 UTC
"__MONTH_START__"          = 1st of current month
"__MONTH_END__"            = last moment of current month
"__YEAR_START__"           = 1st Jan current year
"__YEAR_END__"             = 31st Dec current year 23:59
"__PREV_MONTH_START__"     = 1st of last month
"__PREV_MONTH_END__"       = last moment of last month
"__PREV_YEAR_START__"      = 1st Jan last year
"__PREV_YEAR_END__"        = 31st Dec last year 23:59
"__MONTHS_AGO_N_START__"   = 1st of N months ago  (e.g. __MONTHS_AGO_2_START__)
"__MONTHS_AGO_N_END__"     = last moment of N months ago
"__DAYS_AGO_N__"           = N days ago  (e.g. __DAYS_AGO_30__)

RULES:
- "aaj" → $gte __TODAY_START__ AND $lte __TODAY_END__
- "is mahine" → $gte __MONTH_START__ AND $lte __MONTH_END__
- "pichle mahine" → $gte __PREV_MONTH_START__ AND $lte __PREV_MONTH_END__
- "pichle saal" → $gte __PREV_YEAR_START__ AND $lte __PREV_YEAR_END__
- "is saal" → $gte __YEAR_START__ AND $lte __YEAR_END__
- "abi tak" / "kabhi bhi" → NO date filter
- ALWAYS use BOTH $gte AND $lte. Never just one side.
"""

JSON_RULE = "Return ONLY a valid json object. No markdown. No explanation."


# ─────────────────────────────────────────────────────────────────────────────
#  NODE 1 — SMART ROUTER
#  Detects ALL intents in the message, extracts all entities
# ─────────────────────────────────────────────────────────────────────────────

ROUTER_PROMPT = f"""
You are the intent classifier for HisabBot, a wholesale business assistant.
Messages are in Roman Urdu (Urdu written in English letters).
{JSON_RULE}

A single message may contain MULTIPLE operations. Detect ALL of them.

=== INTENT TYPES ===
"stock_write"    → add/remove/update stock  (e.g. "stock mein 50 bag cheeni daal do 5000 per bag")
"stock_read"     → check stock levels       (e.g. "cheeni kitni bachi hai", "poora stock dikhao")
"sales_write"    → record a sale            (e.g. "ali ko 30 bag cheeni 3550 per bag diya")
"sales_read"     → view sales/profit report, customer bill/invoice (e.g. "aaj ki sale", "har product ka profit", "ali ka bill", "ali ki kharidari", "ali ka hisab", "invoice dikhao")
"customer_write" → add/update customer info (e.g. "ali ka number 03001234567")
"customer_read"  → view customer info/balance (e.g. "ali ka baaki", "ali ki detail")
"finance_write"  → record payment received  (e.g. "ali ne 5000 diye")
"finance_read"   → view payment history, total collections (e.g. "aaj kitna payment aaya", "ali ke payments", "is mahine ki collection")
"conversation"   → question about the conversation itself, what was said, summary of previous messages
  e.g. "pichle message mein kya kaha", "aapne kya bataya", "jo abhi kaha woh repeat karo",
       "mera last message kya tha", "kya hua pehle"
"unknown"        → cannot understand

=== PRICE CONTEXT ===
cost_price    = what dealer PAID to buy (stock purchase price)
selling_price = what dealer CHARGES the customer (sale price)
Stock messages → extract cost_price. Sale messages → extract selling_price.

=== OUTPUT FORMAT ===
{{
  "tasks": [
    {{
      "intent":   "<one of the intent types above>",
      "action":   "<short description>",
      "customer":   "<CLEAN name only, no location words — e.g. 'ali' not 'islamabad waly ali'>",
      "phone":      "<phone or null>",
      "address":    "<explicit address if stated — e.g. 'model town lahore'>",
      "qualifier":  "<location/city/descriptor used to identify WHICH customer — e.g. 'islamabad', 'lahore', 'purana'>",
      "amount":     <float or null>,
      "items": [
        {{
          "product":       "<lowercase>",
          "qty":           <int or null>,
          "cost_price":    <float or null>,
          "selling_price": <float or null>
        }}
      ]
    }}
  ]
}}

=== MULTI-INTENT EXAMPLES ===

"stock mein 50 bag cheeni 5000 per bag daal do aur ali ko 30 bag cheeni 5500 per bag de do"
→ tasks: [
    {{intent:"stock_write", action:"add stock", items:[{{product:"cheeni",qty:50,cost_price:5000}}]}},
    {{intent:"sales_write", action:"record sale", customer:"ali", items:[{{product:"cheeni",qty:30,selling_price:5500}}]}}
  ]

"ali ko 30 bag cheeni diya aur ali ne 50000 payment ki"
→ tasks: [
    {{intent:"sales_write", action:"record sale", customer:"ali", items:[{{product:"cheeni",qty:30}}]}},
    {{intent:"finance_write", action:"receive payment", customer:"ali", amount:50000}}
  ]

"cheeni ka stock batao aur aaj ki sale dikhao"
→ tasks: [
    {{intent:"stock_read", action:"check stock", items:[{{product:"cheeni"}}]}},
    {{intent:"sales_read", action:"daily sales report"}}
  ]

"ali ka bill dikhao" / "ali pai kitna bill hai" / "ali ka hisab" / "ali ki kharidari"
→ tasks: [{{intent:"sales_read", action:"customer bill", customer:"ali"}}]

"ali ka bill aur baaki"
→ tasks: [
    {{intent:"sales_read", action:"customer bill", customer:"ali"}},
    {{intent:"customer_read", action:"check balance", customer:"ali"}}
  ]

"ali ka baaki kitna hai aur ali ka number 0300 save karo"
→ tasks: [
    {{intent:"customer_read", action:"check balance", customer:"ali"}},
    {{intent:"customer_write", action:"update phone", customer:"ali", phone:"0300"}}
  ]


=== QUALIFIER EXTRACTION — ALL WORD ORDERS ===
Extract qualifier from ANY of these patterns. All mean customer="ali", qualifier="islamabad":
  "islamabad waly ali"          → customer:"ali",   qualifier:"islamabad"
  "ali islamabad waly"          → customer:"ali",   qualifier:"islamabad"
  "islamabad walay ali"         → customer:"ali",   qualifier:"islamabad"
  "ali jo islamabad mein hai"   → customer:"ali",   qualifier:"islamabad"
  "ali address islamabad"       → customer:"ali",   qualifier:"islamabad"
  "islamabad ali"               → customer:"ali",   qualifier:"islamabad"
  "ali islamabad"               → customer:"ali",   qualifier:"islamabad"
  "ali islamabad ka"            → customer:"ali",   qualifier:"islamabad"
  "islamabad ka ali"            → customer:"ali",   qualifier:"islamabad"
  "ali islamabad wala hai"      → customer:"ali",   qualifier:"islamabad"

More examples:
  "lahore waly ahmed"           → customer:"ahmed", qualifier:"lahore"
  "ahmed jo lahore mein rehta"  → customer:"ahmed", qualifier:"lahore"
  "pindi wala khan"             → customer:"khan",  qualifier:"pindi"
  "asif address karachi"        → customer:"asif",  qualifier:"karachi"
  "islamabad valy ali"          → customer:"ali",   qualifier:"islamabad"
  "ali islamabad valy"          → customer:"ali",   qualifier:"islamabad"

CRITICAL RULE: NEVER put city/location inside "customer" field.
  WRONG: {{"customer":"islamabad waly ali"}}
  RIGHT: {{"customer":"ali","qualifier":"islamabad"}}

FOLLOW-UP PRICE CORRECTION:
If history shows agent asked for missing price, and current message only provides a price:
- Reconstruct full sale from previous user message in history
- Apply new price to the missing item
- Generate complete sales_write with ALL items and ALL prices

Example:
  History — User: "asad ko 40 cheeni 6100, 40 daal de do"
             Agent: "Daal ki selling price nahi di. Aglay message mein price batain."
  Current:  "daal price 3000"
  Output:   {{intent:"sales_write", customer:"asad",
             items:[{{product:"cheeni",qty:40,selling_price:6100}},
                    {{product:"daal",qty:40,selling_price:3000}}]}}

Patterns that mean "this is a price follow-up":
  "daal price 3000" / "cheeni 6500 hai" / "woh 3000 tha" / "price 2800 rakho"

For STOCK follow-up (when previous was stock_write with missing cost_price):
  Extract only the item(s) that had missing price, use cost_price (not selling_price).
  Example:
    History — User: "500 cheeni 6000, 600 ghee, 500 aata stock add karo"
               Agent: "Ghee aur Aata ki cost price nahi di."
    Current:  "ghee 2000, aata 1800"
    Output:   {{intent:"stock_write", items:[{{product:"ghee",qty:600,cost_price:2000}},{{product:"aata",qty:500,cost_price:1800}}]}}
"""

async def router_node(state):
    # Build messages: system + last 2 history turns + current message
    history = state.get("conversation_history") or []
    # Keep max last 4 messages (2 exchanges) as context
    prior = history[-4:] if len(history) > 4 else history

    messages = [{"role": "system", "content": ROUTER_PROMPT}]
    if prior:
        # Add history as context so agent understands follow-up messages
        history_text = "\n".join(
            f"{'User' if h['role']=='user' else 'Agent'}: {h['content']}"
            for h in prior
        )
        messages.append({
            "role": "user",
            "content": f"=== PREVIOUS CONVERSATION (for context only) ===\n{history_text}\n=== END CONTEXT ===\n\nNew message: {state['user_message']}"
        })
    else:
        messages.append({"role": "user", "content": state["user_message"]})

    res = await groq_client.chat.completions.create(
        messages=messages,
        model=MODEL,
        response_format={"type": "json_object"},
        temperature=0.0
    )
    try:
        out = json.loads(res.choices[0].message.content)
    except Exception:
        out = {"tasks": [{"intent": "unknown", "action": "", "items": []}]}

    tasks = out.get("tasks", [])
    if not isinstance(tasks, list) or not tasks:
        tasks = [{"intent": "unknown", "action": "", "items": []}]

    # Validate intents
    valid_intents = {
        "stock_write","stock_read","sales_write","sales_read",
        "customer_write","customer_read","finance_write","finance_read",
        "conversation","unknown"
    }
    for task in tasks:
        if task.get("intent") not in valid_intents:
            task["intent"] = "unknown"

    # ── Normalise every task ─────────────────────────────────────────────────
    import re as _re

    # Pakistani cities + common descriptors used to distinguish same-name customers
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

    def _extract_qualifier(name: str):
        """
        Split "ali islamabad waly" / "islamabad waly ali" / "ali address islamabad" etc.
        into (base_name, qualifier). Handles all word-orders and spelling variants.
        Returns (name, None) if no qualifier found.
        """
        # Step 1: strip trailing function words that follow the customer pattern
        # e.g. "ali islamabad waly ko" -> "ali islamabad waly"
        FUNC_WORDS = r'(?:\s+(?:ko|ne|ka|ki|ke|se|sy|par|per|nay|nai|nein))+\s*$'
        name = _re.sub(FUNC_WORDS, '', name.strip(), flags=_re.I)

        # Step 2: collapse multiple spaces
        n = ' '.join(name.lower().split())

        # Pattern A: <city> waly/walay/wala/wali <name>
        mA = _re.match(r'^(.+?)\s+(?:waly|walay|wala|wali|valy|valay|vala|vale|wale|waale)\s+(.+)$', n, _re.I)
        if mA:
            return mA.group(2).strip(), mA.group(1).strip()

        # Pattern B: <name> <city> waly/walay/wala/wali
        mB = _re.match(r'^(.+?)\s+(.+?)\s+(?:waly|walay|wala|wali|valy|valay|vala|vale|wale|waale)$', n, _re.I)
        if mB:
            return mB.group(1).strip(), mB.group(2).strip()

        # Pattern C: <name> waly/wala <city>   (rare but happens)
        mC = _re.match(r'^(.+?)\s+(?:waly|walay|wala|wali|valy|valay|vala|vale|wale|waale)\s+(.+)$', n, _re.I)
        if mC:
            return mC.group(1).strip(), mC.group(2).strip()

        # Pattern D: <name> address <city>
        mD = _re.match(r'^(.+?)\s+address\s+(.+)$', n, _re.I)
        if mD:
            return mD.group(1).strip(), mD.group(2).strip()

        # Pattern E: <name> jo <city> mein / <name> <city> ka / <name> <city> ki
        mE = _re.match(r'^(.+?)\s+(?:jo\s+)?(.+?)\s+(?:mein|ka|ki|ke|se|sy)$', n, _re.I)
        if mE:
            possible_city = mE.group(2).strip()
            if any(c in possible_city for c in CITY_WORDS):
                return mE.group(1).strip(), possible_city

        # Pattern F: known city word at start or end (bare, no waly suffix)
        words = n.split()
        if len(words) >= 2:
            # city at start: "islamabad ali"
            for i in range(1, len(words)):
                prefix = " ".join(words[:i])
                suffix = " ".join(words[i:])
                if any(c == prefix or c in prefix for c in CITY_WORDS):
                    return suffix, prefix
            # city at end: "ali islamabad"
            for i in range(len(words)-1, 0, -1):
                suffix = " ".join(words[i:])
                prefix = " ".join(words[:i])
                if any(c == suffix or c in suffix for c in CITY_WORDS):
                    return prefix, suffix

        return name, None

    for task in tasks:
        if not isinstance(task.get("items"), list):
            task["items"] = []

        # If LLM extracted a qualifier, only trust it if it looks like a real place/descriptor
        # Reject junk values like "waly", "walay", "ko", "ne" etc.
        JUNK_QUALIFIERS = {"waly","walay","wala","wali","valy","valay","vala","vale","wale",
                           "ko","ne","ka","ki","ke","se","sy","par","per","nay","nai","jo"}
        existing_q = (task.get("qualifier") or "").lower().strip()
        if existing_q and existing_q not in JUNK_QUALIFIERS:
            # Good qualifier from LLM — also set as address hint
            if not task.get("address"):
                task["address"] = existing_q
            continue

        # Try Python patterns on the customer field
        raw_customer = (task.get("customer") or "").strip()
        if not raw_customer:
            continue

        base_name, qualifier = _extract_qualifier(raw_customer)
        if qualifier and qualifier.lower() not in JUNK_QUALIFIERS:
            task["customer"]  = base_name
            task["qualifier"] = qualifier
            if not task.get("address"):
                task["address"] = qualifier
        elif not qualifier and existing_q in JUNK_QUALIFIERS:
            # LLM set a junk qualifier — clear it
            task["qualifier"] = None

    return {
        "tasks":            tasks,
        "intent":           tasks[0].get("intent", "unknown"),
        "action":           tasks[0].get("action", ""),
        "entities":         tasks[0],
        "extracted_intent": out
    }


# ─────────────────────────────────────────────────────────────────────────────
#  SPECIALIZED QUERY BUILDERS — small focused prompts
# ─────────────────────────────────────────────────────────────────────────────

# ── STOCK ──────────────────────────────────────────────────────────────────

STOCK_SCHEMA = """
Collection: inventory
Fields: product (string lowercase), qty (int), cost_price (float), low_stock_threshold (int default 5)
Example: {product:"cheeni", qty:200, cost_price:5000}
"""

STOCK_WRITE_PROMPT = f"""
You are a MongoDB query generator for HisabBot stock management.
{JSON_RULE}

{STOCK_SCHEMA}
{DATE_RULES}

Operations:
- Add/restock: update_one inventory, filter={{product}}, update={{$inc:{{qty:N}}, $set:{{cost_price:X}}}}, upsert:true
- Remove/damage: update_one inventory, filter={{product}}, update={{$inc:{{qty:-N}}}}
- Set price only: update_one inventory, filter={{product}}, update={{$set:{{cost_price:X}}}}, upsert:true
- Multi-product: use "operations" array with one update_one per product

RULES:
- product names MUST be lowercase in filter
- Only $set cost_price if explicitly provided
- Never delete records

OUTPUT (single): {{"operation":"update_one","collection":"inventory","filter":{{...}},"update":{{...}},"upsert":true}}
OUTPUT (multi):  {{"operations":[...], "description":"..."}}
"""

STOCK_READ_PROMPT = f"""
You are a MongoDB query generator for HisabBot stock queries.
{JSON_RULE}

{STOCK_SCHEMA}
{DATE_RULES}

IMPORTANT: Always use aggregate with $addFields to show 0 for negative stock:
  {{"$addFields": {{"qty": {{"$max": ["$qty", 0]}}}}}}

EXAMPLES:
"cheeni kitni hai":
{{"operation":"aggregate","collection":"inventory","pipeline":[
  {{"$match":{{"product":"cheeni"}}}},
  {{"$addFields":{{"qty":{{"$max":["$qty",0]}}}}}}
]}}

"poora stock / sab items":
{{"operation":"aggregate","collection":"inventory","pipeline":[
  {{"$addFields":{{"qty":{{"$max":["$qty",0]}}}}}},
  {{"$sort":{{"product":1}}}}
]}}

"kam stock / khatam hone wale items":
{{"operation":"aggregate","collection":"inventory","pipeline":[
  {{"$addFields":{{"qty":{{"$max":["$qty",0]}},"threshold":{{"$ifNull":["$low_stock_threshold",5]}}}}}},
  {{"$match":{{"$expr":{{"$lte":["$qty","$threshold"]}}}}}},
  {{"$sort":{{"qty":1}}}}
]}}
"""

async def stock_query_builder(task: dict, user_message: str) -> dict:
    intent = task.get("intent","")
    prompt = STOCK_WRITE_PROMPT if intent == "stock_write" else STOCK_READ_PROMPT

    items   = task.get("items", [])
    context = (
        f"User message: \"{user_message}\"\n"
        f"Action: {task.get('action','')}\n"
        f"Items: {json.dumps(items)}\n"
        f"Generate the MongoDB plan."
    )
    res = await groq_client.chat.completions.create(
        messages=[{"role":"system","content":prompt},{"role":"user","content":context}],
        model=MODEL, response_format={"type":"json_object"}, temperature=0.0
    )
    try:    return json.loads(res.choices[0].message.content)
    except: return {"operation":"unsupported"}


# ── SALES ──────────────────────────────────────────────────────────────────

SALES_SCHEMA = """
Collection: sales
Fields: customer (string lowercase), product (string lowercase), qty (int),
        selling_price (float), cost_price (float),
        sale_total (float = selling_price*qty), cost_total (float = cost_price*qty),
        profit (float = sale_total-cost_total), date (datetime)
Collection: inventory
Fields: product (string lowercase), qty (int), cost_price (float)
"""

SALES_WRITE_PROMPT = f"""
You are a MongoDB query generator for HisabBot sales recording.
{JSON_RULE}

{SALES_SCHEMA}
{DATE_RULES}

For EVERY sale, generate a multi-step "operations" array with exactly 3 steps.
Use EXACTLY the numbers from ENRICHED ITEMS. All strings LOWERCASE.

REQUIRED OUTPUT FORMAT:
{{
  "operations": [
    {{
      "operation": "update_one",
      "collection": "inventory",
      "filter": {{"product": "<product>"}},
      "update": {{"$inc": {{"qty": -<qty>}}}}
    }},
    {{
      "operation": "insert_one",
      "collection": "sales",
      "document": {{
        "customer": "<customer>",
        "product": "<product>",
        "qty": <qty>,
        "selling_price": <selling_price>,
        "cost_price": <cost_price or null>,
        "sale_total": <sale_total>,
        "cost_total": <cost_total or null>,
        "profit": <profit or null>,
        "date": "__TODAY_START__"
      }}
    }},
    {{
      "operation": "update_one",
      "collection": "customers",
      "filter": <see CUSTOMER FILTER RULES below>,
      "update": {{
        "$inc": {{"total_credit": <sum of all sale_totals>}},
        "$set": {{"last_seen": "__TODAY_START__"}},
        "$setOnInsert": {{"name": "<customer>", "phone": <phone or null>, "address": <address or null>, "join_date": "__TODAY_START__"}}
      }},
      "upsert": true
    }}
  ],
  "description": "record sale"
}}

CUSTOMER FILTER RULES — very important to avoid mixing up customers with same name:
- If context has _customer_filter with address → filter: {{"name":"<n>","address":"<addr>"}}
- If context has _customer_filter with phone   → filter: {{"name":"<n>","phone":"<phone>"}}
- If only name available                       → filter: {{"name":"<n>"}} only

ADDRESS IN $setOnInsert — always store address when creating new customer:
- If address provided: "$setOnInsert": {{"name":"<n>","address":"<addr>","phone":<phone or null>,"join_date":"__TODAY_START__"}}
- Never put "address": null if address was given — store it so future queries identify the right customer

SALES DOCUMENT — also store customer_address:
- Add "customer_address": <address or null> to the sales insert document

For MULTIPLE products to the SAME customer: one inventory+sales step per product,
ONE final customer update with the SUM of all sale_totals.
collection values must always be exactly: "inventory", "sales", or "customers"
"""

SALES_READ_PROMPT = f"""
You are a MongoDB query generator for HisabBot sales reports.
{JSON_RULE}

{SALES_SCHEMA}
{DATE_RULES}

EXAMPLES:
"aaj ki sale aur profit":
{{"operation":"aggregate","collection":"sales","pipeline":[
  {{"$match":{{"date":{{"$gte":"__TODAY_START__","$lte":"__TODAY_END__"}}}}}},
  {{"$group":{{"_id":null,"total_qty":{{"$sum":"$qty"}},"total_revenue":{{"$sum":"$sale_total"}},
    "total_cost":{{"$sum":"$cost_total"}},"total_profit":{{"$sum":"$profit"}}}}}}
]}}

"har product ka profit":
{{"operation":"aggregate","collection":"sales","pipeline":[
  {{"$group":{{"_id":"$product","qty":{{"$sum":"$qty"}},"revenue":{{"$sum":"$sale_total"}},"profit":{{"$sum":"$profit"}}}}}},
  {{"$sort":{{"profit":-1}}}}
]}}

"ali ka bill / invoice / hisab / kharidari" (NO date filter — show ALL purchases):
{{"operation":"aggregate","collection":"sales","pipeline":[
  {{"$match":{{"customer":"ali"}}}},
  {{"$project":{{
    "date":1,"product":1,"qty":1,
    "selling_price":1,"sale_total":1
  }}}},
  {{"$sort":{{"date":-1}}}}
]}}

IMPORTANT BILL RULES:
- Bill/invoice/hisab/kharidari queries MUST NOT have any date filter — show all records
- Always project: date, product, qty, selling_price, sale_total
- Sort by date descending so newest first
- Use customer name from context (lowercase)
- If address/qualifier given, add customer_address filter too:
  {{"$match":{{"customer":"ali","customer_address":"lahore"}}}}

"kaunsa product sabse zyada bika":
{{"operation":"aggregate","collection":"sales","pipeline":[
  {{"$group":{{"_id":"$product","total_qty":{{"$sum":"$qty"}},"profit":{{"$sum":"$profit"}}}}}},
  {{"$sort":{{"total_qty":-1}}}},{{"$limit":10}}
]}}

"abi tak total munafa":
{{"operation":"aggregate","collection":"sales","pipeline":[
  {{"$group":{{"_id":null,"total_profit":{{"$sum":"$profit"}},"total_revenue":{{"$sum":"$sale_total"}},
    "total_cost":{{"$sum":"$cost_total"}},"total_qty":{{"$sum":"$qty"}}}}}}
]}}
"""

async def sales_query_builder(task: dict, user_message: str, enriched_items: list = None) -> dict:
    intent = task.get("intent","")
    prompt = SALES_WRITE_PROMPT if intent == "sales_write" else SALES_READ_PROMPT

    context_parts = [
        f"User message: \"{user_message}\"",
        f"Action: {task.get('action','')}",
        f"Customer: {task.get('customer','')}",
        f"Phone: {task.get('phone','') or 'null'}",
        f"Address: {task.get('address','') or 'null'}",
    ]

    # Pass the resolved customer filter so LLM uses the right filter in DB ops
    customer_filter = task.get("_customer_filter")
    if customer_filter:
        context_parts.append(f"_customer_filter (use this in customer update filter): {json.dumps(customer_filter)}")

    if task.get("_new_customer"):
        context_parts.append("NOTE: This is a NEW customer — use $setOnInsert to store name, address, phone, join_date.")

    if enriched_items:
        context_parts.append("=== ENRICHED ITEMS — use these EXACT numbers ===")
        for it in enriched_items:
            context_parts.append(f"  {json.dumps(it)}")
    else:
        context_parts.append(f"Items: {json.dumps(task.get('items',[]))}")

    context_parts.append("Generate the MongoDB plan.")
    context = "\n".join(context_parts)

    res = await groq_client.chat.completions.create(
        messages=[{"role":"system","content":prompt},{"role":"user","content":context}],
        model=MODEL, response_format={"type":"json_object"}, temperature=0.0
    )
    try:    return json.loads(res.choices[0].message.content)
    except: return {"operation":"unsupported"}


# ── CUSTOMER ───────────────────────────────────────────────────────────────

CUSTOMER_SCHEMA = """
Collection: customers
Fields: name (string lowercase), phone (string), address (string),
        total_credit (float — amount owed, increases on sale, decreases on payment),
        last_seen (datetime), join_date (datetime)
Collection: sales  (for purchase history)
Fields: customer, product, qty, selling_price, sale_total, date
"""

CUSTOMER_WRITE_PROMPT = f"""
You are a MongoDB query generator for HisabBot customer management.
{JSON_RULE}

{CUSTOMER_SCHEMA}
{DATE_RULES}

Operations:
- Add/update customer: update_one customers, filter={{name}}, upsert:true
  update: {{"$set":{{provided fields,"last_seen":"__TODAY_START__"}},
             "$setOnInsert":{{"name":customer,"total_credit":0,"join_date":"__TODAY_START__"}}}}
- All customer name strings must be LOWERCASE
"""

CUSTOMER_READ_PROMPT = f"""
You are a MongoDB query generator for HisabBot customer queries.
{JSON_RULE}

{CUSTOMER_SCHEMA}
{DATE_RULES}

EXAMPLES:
"ali ka baaki" → {{"operation":"find","collection":"customers","filter":{{"name":"ali"}}}}
"ali ki detail" → {{"operation":"find","collection":"customers","filter":{{"name":"ali"}}}}
"kaunse customers ka baaki hai" → {{"operation":"find","collection":"customers","filter":{{"total_credit":{{"$gt":0}}}},"sort":{{"total_credit":-1}}}}
"ali ne kya kharida" → {{"operation":"find","collection":"sales","filter":{{"customer":"ali"}},"sort":{{"date":-1}},"limit":20}}
"top customers" → {{"operation":"aggregate","collection":"customers","pipeline":[
  {{"$sort":{{"total_credit":-1}}}},{{"$limit":10}}
]}}
"""

async def customer_query_builder(task: dict, user_message: str) -> dict:
    intent = task.get("intent","")
    prompt = CUSTOMER_WRITE_PROMPT if intent == "customer_write" else CUSTOMER_READ_PROMPT

    context = (
        f"User message: \"{user_message}\"\n"
        f"Action: {task.get('action','')}\n"
        f"Customer: {task.get('customer','')} | Phone: {task.get('phone','')} | Address: {task.get('address','')}\n"
        f"Generate the MongoDB plan."
    )
    res = await groq_client.chat.completions.create(
        messages=[{"role":"system","content":prompt},{"role":"user","content":context}],
        model=MODEL, response_format={"type":"json_object"}, temperature=0.0
    )
    try:    return json.loads(res.choices[0].message.content)
    except: return {"operation":"unsupported"}


# ── FINANCE ────────────────────────────────────────────────────────────────

FINANCE_SCHEMA = """
Collection: finance
Fields: customer (string lowercase), customer_address (string), amount (float), type (string: "payment" or "invoice"), date (datetime)
  — customer_address: stored so payments can be traced to the correct customer when multiple share the same name
Collection: customers
Fields: name (string lowercase), total_credit (float), phone, address, last_seen
"""

FINANCE_WRITE_PROMPT = f"""
You are a MongoDB query generator for HisabBot payment recording.
{JSON_RULE}

{FINANCE_SCHEMA}
{DATE_RULES}

For payment received: ALWAYS generate exactly this two-step format.
collection values must be exactly "customers" or "finance" — never empty.

REQUIRED OUTPUT FORMAT:
{{
  "operations": [
    {{
      "operation": "update_one",
      "collection": "customers",
      "filter": {{"name": "<customer_name_lowercase>"}},
      "update": {{
        "$inc": {{"total_credit": -<amount>}},
        "$set": {{"last_seen": "__TODAY_START__"}}
      }}
    }},
    {{
      "operation": "insert_one",
      "collection": "finance",
      "document": {{
        "customer":          "<customer_name_lowercase>",
        "customer_address":  "<address from context or null>",
        "amount":            <amount>,
        "type":              "payment",
        "date":              "__TODAY_START__"
      }}
    }}
  ],
  "description": "receive payment"
}}

Customer name MUST be lowercase. Amount must be a number (not string).
Always include customer_address — use the address from context if provided, otherwise null.
This is critical for identifying which Ali/Ahmed paid when multiple customers share the same name.
"""

FINANCE_READ_PROMPT = f"""
You are a MongoDB query generator for HisabBot finance queries.
{JSON_RULE}

{FINANCE_SCHEMA}
{DATE_RULES}

EXAMPLES:
"ali ke payments" (single Ali exists):
{{"operation":"find","collection":"finance","filter":{{"customer":"ali","type":"payment"}},"sort":{{"date":-1}}}}

"islamabad waly ali ke payments" (multiple Alis, address filter needed):
{{"operation":"find","collection":"finance","filter":{{"customer":"ali","customer_address":"islamabad","type":"payment"}},"sort":{{"date":-1}}}}

"ali ka baaki / outstanding balance":
{{"operation":"find","collection":"customers","filter":{{"name":"ali"}}}}

"aaj ki total collection / aaj kitna payment aaya":
{{"operation":"aggregate","collection":"finance","pipeline":[
  {{"$match":{{"type":"payment","date":{{"$gte":"__TODAY_START__","$lte":"__TODAY_END__"}}}}}},
  {{"$group":{{"_id":null,"total":{{"$sum":"$amount"}},"count":{{"$sum":1}}}}}}
]}}

"is mahine ki total payments / mahine mein kitna aaya":
{{"operation":"aggregate","collection":"finance","pipeline":[
  {{"$match":{{"type":"payment","date":{{"$gte":"__MONTH_START__","$lte":"__MONTH_END__"}}}}}},
  {{"$group":{{"_id":"$customer","total":{{"$sum":"$amount"}}}}}},{{"$sort":{{"total":-1}}}}
]}}

"finance update / sab ka baaki / all outstanding balances":
{{"operation":"find","collection":"customers","filter":{{"total_credit":{{"$gt":0}}}},"sort":{{"total_credit":-1}}}}

RULES:
- collection must always be exactly "finance" or "customers" — never empty
- For balance queries → use "customers" collection, total_credit field
- For payment history → use "finance" collection, type:"payment"
- Return ONLY real data from DB — never generate sample/example data
"""

async def finance_query_builder(task: dict, user_message: str) -> dict:
    intent = task.get("intent","")
    prompt = FINANCE_WRITE_PROMPT if intent == "finance_write" else FINANCE_READ_PROMPT

    pinned = task.get("_pinned_filter")
    context = (
        f"User message: \"{user_message}\"\n"
        f"Action: {task.get('action','')}\n"
        f"Customer: {task.get('customer','')} | Amount: {task.get('amount','')}\n"
        f"Address: {task.get('address','') or 'null'}\n"
        + (f"_pinned_filter (use EXACTLY this in customer update filter): {json.dumps(pinned)}\n"
           if pinned else "")
        + "Generate the MongoDB plan."
    )
    res = await groq_client.chat.completions.create(
        messages=[{"role":"system","content":prompt},{"role":"user","content":context}],
        model=MODEL, response_format={"type":"json_object"}, temperature=0.0
    )
    try:    return json.loads(res.choices[0].message.content)
    except: return {"operation":"unsupported"}


# ─────────────────────────────────────────────────────────────────────────────
#  PRE-FETCH inventory for sales (Python arithmetic — no LLM math)
# ─────────────────────────────────────────────────────────────────────────────

# ── Product name fuzzy matcher ───────────────────────────────────────────────
# Cached inventory product list — refreshed per request
_inventory_cache: list = []

def _levenshtein(a: str, b: str) -> int:
    """Compute edit distance between two strings."""
    if a == b: return 0
    if not a: return len(b)
    if not b: return len(a)
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            temp = dp[j]
            dp[j] = prev if a[i-1]==b[j-1] else 1 + min(prev, dp[j], dp[j-1])
            prev = temp
    return dp[n]

def _phonetic_urdu(s: str) -> str:
    """
    Collapse common Urdu Roman spelling variations to a canonical form.
    Treats vowel variants, double letters, and common substitutions as equivalent.

    Examples:
      cheeni / chini / chene / cheeni  → all become "chni"
      daal / dal / dael                → all become "dl"
      sooji / suji / soji              → all become "sj"
      ghee / ghi / ghee                → all become "gh"
      aata / atta / ata                → all become "t"
    """
    s = s.lower().strip()
    # Normalize common letter equivalents first
    s = s.replace("ph", "f")           # phone → fone
    s = s.replace("kh", "k")
    s = s.replace("ch", "c")
    s = s.replace("sh", "x")
    s = s.replace("ee", "i")           # cheeni → chini
    s = s.replace("aa", "a")           # daal → dal
    s = s.replace("oo", "u")           # noodles → nudles
    s = s.replace("ae", "a")           # chawal → chawal
    # Remove all vowels — consonant skeleton comparison
    import re as _re
    s = _re.sub(r'[aeiou]', '', s)
    # Collapse repeated consonants: "ll" → "l", "nn" → "n"
    s = _re.sub(r'(.)+', r'', s)
    return s


def _fuzzy_match_product(typed: str, known_products: list, threshold: float = 0.72) -> str | None:
    """
    Find the closest matching product name from inventory.
    Uses three methods in order:
      1. Exact match
      2. Levenshtein edit distance (catches simple typos)
      3. Phonetic consonant-skeleton comparison (catches vowel substitutions)

    Examples:
      "chenni" → "cheeni"   edit dist 2, sim 0.80 ✓
      "chini"  → "cheeni"   phonetic both → "cn" ✓
      "dal"    → "daal"     edit dist 1, prefix boost → 0.85 ✓
      "suji"   → "sooji"    phonetic both → "sj" ✓
      "meda"   → "maida"    phonetic both → "md" ✓
      "ghi"    → no match   too different ✓
      "oil"    → no match   different language ✓
    """
    typed = typed.lower().strip()
    if not typed or not known_products:
        return None

    # 1. Exact match
    if typed in known_products:
        return typed

    best_product = None
    best_score   = 0.0

    typed_phonetic = _phonetic_urdu(typed)

    for prod in known_products:
        prod_l = prod.lower()

        # 2. Levenshtein similarity
        max_len = max(len(typed), len(prod_l))
        if max_len == 0: continue
        dist = _levenshtein(typed, prod_l)
        sim  = 1.0 - dist / max_len

        # Prefix/substring boost
        if prod_l.startswith(typed) or typed.startswith(prod_l):
            sim = max(sim, 0.85)
        if prod_l in typed or typed in prod_l:
            sim = max(sim, 0.80)

        # 3. Phonetic similarity boost
        prod_phonetic = _phonetic_urdu(prod_l)
        if typed_phonetic and prod_phonetic:
            ph_max = max(len(typed_phonetic), len(prod_phonetic))
            if ph_max > 0:
                ph_dist = _levenshtein(typed_phonetic, prod_phonetic)
                ph_sim  = 1.0 - ph_dist / ph_max
                # If phonetic match is strong, boost the overall score
                if ph_sim >= 0.80:
                    sim = max(sim, 0.80)
                elif ph_sim >= 0.65:
                    sim = max(sim, sim + 0.05)

        if sim > best_score:
            best_score   = sim
            best_product = prod

    return best_product if best_score >= threshold else None


async def _get_all_inventory_products() -> list:
    """Fetch all product names from inventory (for fuzzy matching)."""
    result = await execute_plan({
        "operation": "find", "collection": "inventory",
        "filter": {}, "limit": 200
    })
    if result["ok"] and result["results"]:
        return [doc.get("product","").lower() for doc in result["results"] if doc.get("product")]
    return []


async def _normalize_product_names(items: list) -> tuple[list, dict]:
    """
    For each item in the list, check if the product name matches an existing
    inventory product (fuzzy). If a close match is found, replace the product
    name with the canonical DB name.

    Returns: (normalized_items, corrections_dict)
    corrections_dict: {"chenni": "cheeni"} — for transparency in responses
    """
    known = await _get_all_inventory_products()
    if not known:
        return items, {}

    corrections = {}
    normalized  = []
    for item in items:
        typed = (item.get("product") or "").lower().strip()
        if not typed:
            normalized.append(item); continue

        if typed in known:
            normalized.append(item); continue  # exact match, no change

        matched = _fuzzy_match_product(typed, known)
        if matched and matched != typed:
            corrections[typed] = matched
            item = dict(item)
            item["product"] = matched
        normalized.append(item)

    return normalized, corrections


async def _fetch_inventory(items: list) -> dict:
    inventory = {}
    for item in items:
        product = (item.get("product") or "").lower().strip()
        if not product:
            continue
        result = await execute_plan({
            "operation": "find", "collection": "inventory",
            "filter": {"product": product}, "limit": 1
        })
        if result["ok"] and result["results"]:
            doc = result["results"][0]
            inventory[product] = {"qty": doc.get("qty",0), "cost_price": doc.get("cost_price")}
        else:
            inventory[product] = {"qty": 0, "cost_price": None}
    return inventory


def _enrich_items(items: list, inv_data: dict) -> list:
    enriched = []
    for item in items:
        product  = (item.get("product") or "").lower().strip()
        inv      = inv_data.get(product, {})
        real_cp  = inv.get("cost_price")
        avail    = inv.get("qty", 0)
        sp       = item.get("selling_price")
        qty      = item.get("qty") or 0

        sale_total = round(sp * qty, 2)                      if sp                        else None
        cost_total = round(real_cp * qty, 2)                 if real_cp                   else None
        profit     = round(sale_total - cost_total, 2)       if sale_total and cost_total else None

        enriched.append({
            **item,
            "product":       product,
            "cost_price":    real_cp,
            "sale_total":    sale_total,
            "cost_total":    cost_total,
            "profit":        profit,
            "available_qty": avail,
        })
    return enriched


# ─────────────────────────────────────────────────────────────────────────────
#  CUSTOMER IDENTITY RESOLVER
#  Resolves which customer to use when name + address/qualifier is given
# ─────────────────────────────────────────────────────────────────────────────

def _apply_pinned_filter(plan: dict, pinned_filter: dict) -> dict:
    """
    Replace the filter in any customers update_one with the pinned address-based filter.
    Used for finance_write and customer_write to prevent wrong-Ali payments.
    """
    def fix_op(op: dict) -> dict:
        if op.get("collection") == "customers" and op.get("operation") in ("update_one","update_many"):
            op = dict(op)
            op["filter"] = pinned_filter
        return op

    if "operations" in plan:
        return {**plan, "operations": [fix_op(op) for op in plan["operations"]]}
    return fix_op(plan)


def _replace_customer_ops_in_plan(plan: dict, python_cust_upsert: dict) -> dict:
    """
    Replace any LLM-generated customer update_one operations in the plan
    with the Python-built one that has the exact address-based filter.
    This prevents the LLM from using filter:{name:X} which would match
    a different customer with the same name.
    """
    def is_customer_update(op: dict) -> bool:
        return (
            op.get("collection") == "customers" and
            op.get("operation") in ("update_one", "update_many")
        )

    # Multi-step plan
    if "operations" in plan:
        new_ops = []
        customer_replaced = False
        for op in plan["operations"]:
            if is_customer_update(op) and not customer_replaced:
                # Replace with Python-built upsert, but preserve $inc total_credit
                merged = dict(python_cust_upsert)
                # Carry over the $inc from LLM op if present
                llm_update = op.get("update", {})
                if "$inc" in llm_update:
                    merged_update = dict(merged.get("update", {}))
                    merged_update["$inc"] = llm_update["$inc"]
                    merged["update"] = merged_update
                new_ops.append(merged)
                customer_replaced = True
            else:
                new_ops.append(op)
        # If no customer op was in plan, append ours at the end
        if not customer_replaced:
            new_ops.append(python_cust_upsert)
        plan = dict(plan)
        plan["operations"] = new_ops
        return plan

    # Single-step plan that IS a customer update — replace entirely
    if is_customer_update(plan):
        merged = dict(python_cust_upsert)
        if "$inc" in plan.get("update", {}):
            merged_update = dict(merged.get("update", {}))
            merged_update["$inc"] = plan["update"]["$inc"]
            merged["update"] = merged_update
        return merged

    return plan


async def _resolve_customer_identity(name: str, address: str = None, phone: str = None) -> dict:
    """
    Resolve the correct customer document given name + optional address/phone.

    Strategy:
      1. Search all customers with this name
      2. If only one exists → use it (regardless of address)
      3. If address given → try to match against existing addresses
         - Match found → use that customer
         - No match → this is a NEW customer with a new address → create new
      4. If multiple exist, no address → ask for clarification

    Returns:
      {"action": "use",    "customer": doc}               — use existing customer
      {"action": "create", "name": n, "address": addr}    — create new customer
      {"action": "clarify","options": [...]}               — multiple, need clarification
      {"action": "new"}                                    — no existing, create fresh
    """
    name    = (name or "").lower().strip()
    address = (address or "").lower().strip()
    phone   = (phone or "").strip()

    # Fetch all customers with this name
    result = await execute_plan({
        "operation": "find", "collection": "customers",
        "filter": {"name": name}, "limit": 20
    })
    existing = result.get("results", []) if result.get("ok") else []

    # No existing customer with this name → create new
    if not existing:
        return {"action": "create", "name": name, "address": address, "phone": phone}

    # Only one customer with this name
    if len(existing) == 1:
        c = existing[0]
        existing_addr = (c.get("address") or "").lower().strip()

        # No address given → use the one customer we have
        if not address:
            return {"action": "use", "customer": c}

        # Address given and matches existing → same customer
        if existing_addr and _address_match(existing_addr, address):
            return {"action": "use", "customer": c}

        # Address given but different → new customer (same name, different location)
        if existing_addr and not _address_match(existing_addr, address):
            return {"action": "create", "name": name, "address": address, "phone": phone}

        # Existing has no address → update it and use
        return {"action": "use", "customer": c, "update_address": address}

    # Multiple customers with this name
    if address:
        # Try to find a match by address
        matches = [c for c in existing if _address_match((c.get("address") or "").lower(), address)]

        if len(matches) == 1:
            return {"action": "use", "customer": matches[0]}
        elif len(matches) == 0:
            # No address match → new customer
            return {"action": "create", "name": name, "address": address, "phone": phone}
        else:
            # Multiple address matches → clarify
            return {"action": "clarify", "options": matches}

    if phone:
        # Try phone match
        phone_matches = [c for c in existing if c.get("phone") == phone]
        if len(phone_matches) == 1:
            return {"action": "use", "customer": phone_matches[0]}

    # Multiple customers, no way to distinguish → ask for clarification
    return {"action": "clarify", "options": existing}


def _address_match(addr1: str, addr2: str) -> bool:
    """Check if two addresses refer to the same place (partial match)."""
    if not addr1 or not addr2:
        return False
    a1 = addr1.lower().strip()
    a2 = addr2.lower().strip()
    if a1 == a2:
        return True
    # Check if either contains the other (handles "lahore" vs "lahore, model town")
    if a1 in a2 or a2 in a1:
        return True
    # Word overlap — if >50% of words match
    words1 = set(a1.split())
    words2 = set(a2.split())
    if not words1 or not words2:
        return False
    overlap = len(words1 & words2) / min(len(words1), len(words2))
    return overlap >= 0.5


# ─────────────────────────────────────────────────────────────────────────────
#  NODE 2 — DISPATCH NODE
#  Routes each task to its specialized builder, runs them in parallel
# ─────────────────────────────────────────────────────────────────────────────

INTENT_TO_BUILDER = {
    "stock_write":    "stock",
    "stock_read":     "stock",
    "sales_write":    "sales",
    "sales_read":     "sales",
    "customer_write": "customer",
    "customer_read":  "customer",
    "finance_write":  "finance",
    "finance_read":   "finance",
}

async def _resolve_and_pin_customer(task: dict) -> dict:
    """
    Shared customer resolver for ALL operations that need to identify a specific customer.
    Used by: finance_write (payment), customer_read (balance check), customer_write, finance_read.

    Reads name + address + phone + qualifier from the task, runs _resolve_customer_identity(),
    and returns one of:
      {"status": "ok",      "customer": doc, "filter": {...}}  — exact match found
      {"status": "clarify", "response": str}                   — multiple, return this message
      {"status": "not_found","response": str}                  — no customer exists
    """
    name      = (task.get("customer") or "").lower().strip()
    address   = (task.get("address")  or "").lower().strip() or None
    phone     = (task.get("phone")    or "").strip()         or None
    qualifier = (task.get("qualifier") or "").lower().strip() or None

    # Use qualifier as address hint if address not explicitly set
    effective_address = address or qualifier

    if not name:
        return {"status": "not_found", "response": "Customer ka naam nahi diya."}

    resolution = await _resolve_customer_identity(
        name=name, address=effective_address, phone=phone
    )

    # _resolve_customer_identity returns {"action": "use/create/clarify/new"}
    # Map to status-based API used by callers
    action = resolution.get("action", "")

    if action == "new" or (action == "create" and not resolution.get("customer")):
        # No existing customer found at all
        hint = f" ({effective_address})" if effective_address else ""
        return {
            "status": "not_found",
            "response": (
                f"{name.title()}{hint} ka koi record nahi mila database mein.\n"
                f"Pehle customer add karein ya sahi naam check karein."
            )
        }

    if action == "clarify":
        customers = resolution.get("customers", []) or resolution.get("options", [])
        if not customers:
            hint = f" ({effective_address})" if effective_address else ""
            return {"status": "not_found",
                    "response": f"{name.title()}{hint} ka koi record nahi mila."}
        options = []
        for i, c in enumerate(customers, 1):
            addr   = c.get("address") or "address nahi"
            ph     = c.get("phone")   or "number nahi"
            credit = c.get("total_credit", 0) or 0
            options.append(f"{i}. {name.title()} — {addr} | {ph} | Baaki: Rs {credit:,.0f}")
        opts_text = "\n".join(options)
        return {
            "status": "clarify",
            "response": (
                f"'{name.title()}' naam ke multiple customers hain.\n"
                f"Kaunsa wala?\n\n{opts_text}\n\n"
                f"Address ya phone number ke saath batain, e.g.:\n"
                f"  '{name} islamabad wala ne 200000 diye'"
            )
        }

    if action not in ("use", "create"):
        # Unexpected action — treat as not found
        return {"status": "not_found",
                "response": f"{name.title()} ka record nahi mila."}

    # action == "use" or "create" with existing customer
    matched = resolution.get("customer")
    if not matched:
        # create action means new customer doesn't exist yet — treat as not_found for reads
        hint = f" ({effective_address})" if effective_address else ""
        return {
            "status": "not_found",
            "response": (
                f"{name.title()}{hint} ka koi record nahi mila database mein.\n"
                f"Pehle customer add karein ya sahi naam check karein."
            )
        }
    matched_addr = matched.get("address") or effective_address

    # Build pinned filter using address so the right customer is always updated
    pinned_filter = {"name": matched.get("name", name)}
    if matched_addr:
        pinned_filter["address"] = matched_addr

    return {
        "status":   "ok",
        "customer": matched,
        "filter":   pinned_filter,
        "name":     matched.get("name", name),
        "address":  matched_addr,
        "phone":    phone or matched.get("phone"),
    }


async def _build_plan_for_task(task: dict, user_message: str) -> dict:
    """Build a MongoDB plan for a single task using the right specialized builder."""
    intent  = task.get("intent","unknown")
    builder = INTENT_TO_BUILDER.get(intent)

    if builder == "stock":
        if intent == "stock_write":
            items = task.get("items", [])
            if items:
                # ── MISSING COST PRICE CHECK ──────────────────────────────
                missing_price = [
                    (item.get("product") or "?").title()
                    for item in items
                    if not item.get("cost_price")
                ]
                if missing_price:
                    # Split: items with price vs items without
                    has_price  = [i for i in items if i.get("cost_price")]
                    no_price   = [(i.get("product") or "?").title() for i in items if not i.get("cost_price")]

                    if has_price and no_price:
                        # Partial — add what we can, ask for the rest
                        partial_task = {**task, "items": has_price}
                        plan = await stock_query_builder(partial_task, user_message)
                        plan["__stock_missing_price__"] = no_price
                        return plan
                    else:
                        # All missing price
                        return {
                            "operation":   "missing_cost_price",
                            "products":    missing_price,
                            "description": f"cost price missing for: {', '.join(missing_price)}"
                        }
        return await stock_query_builder(task, user_message)

    elif builder == "sales":
        if intent == "sales_read":
            action_lower = (task.get("action") or "").lower()
            bill_keywords = ("bill", "invoice", "hisab", "kharidari")
            if any(kw in action_lower for kw in bill_keywords) and task.get("customer"):
                # Bill/invoice — Python builds this directly, no LLM needed
                # No date filter — show ALL purchases for this customer
                cust_name = task.get("customer","").lower().strip()
                # Resolve customer identity to get the right filter
                res = await _resolve_and_pin_customer(task)
                if res["status"] == "clarify":
                    return {"operation": "customer_ambiguous_payment", "response": res["response"]}
                if res["status"] == "not_found":
                    return {"operation": "customer_not_found",
                            "customer": cust_name, "description": res["response"]}
                # Build filter — use address if available to distinguish same-name customers
                bill_filter = {"customer": res.get("name", cust_name)}
                matched_addr = res.get("address")
                if matched_addr:
                    bill_filter["customer_address"] = matched_addr
                plan = {
                    "operation": "aggregate",
                    "collection": "sales",
                    "pipeline": [
                        {"$match": bill_filter},
                        {"$project": {
                            "date": 1, "product": 1, "qty": 1,
                            "selling_price": 1, "sale_total": 1,
                            "customer_address": 1
                        }},
                        {"$sort": {"date": -1}}
                    ]
                }
                return plan

        if intent == "sales_write":
            items = task.get("items", [])
            if items:
                inv_data = await _fetch_inventory(items)
                enriched = _enrich_items(items, inv_data)

                # ── MISSING PRICE CHECK — ask before proceeding ───────────
                missing_price = [
                    item.get("product","").title()
                    for item in enriched
                    if not item.get("selling_price")
                ]
                if missing_price:
                    products_list = ", ".join(missing_price)
                    return {
                        "operation":   "missing_price",
                        "products":    missing_price,
                        "description": f"selling price missing for: {products_list}"
                    }

                # ── HARD STOCK VALIDATION — Python enforces this, not LLM ──
                errors = []
                for item in enriched:
                    product   = item.get("product","")
                    qty       = item.get("qty") or 0
                    available = max(0, item.get("available_qty") or 0)
                    if qty > available:
                        shortage = qty - available
                        errors.append(
                            f"ERROR: {product.title()} ka stock kam hai. "
                            f"Maujood: {available} units. "
                            f"Maanga gaya: {qty} units. "
                            f"Kum: {shortage} units."
                        )

                if errors:
                    # Return error plan — executor will surface this to responder
                    return {
                        "operation":   "stock_error",
                        "errors":      errors,
                        "description": "insufficient stock"
                    }

                # ── CUSTOMER IDENTITY RESOLUTION ────────────────────────
                cust_name  = (task.get("customer") or "").lower().strip()
                cust_addr  = (task.get("address")  or "").lower().strip()
                cust_phone = (task.get("phone")    or "").strip()

                if cust_name:
                    resolution = await _resolve_customer_identity(
                        name=cust_name, address=cust_addr, phone=cust_phone
                    )

                    if resolution["action"] == "clarify":
                        options = []
                        for i, c in enumerate(resolution["options"], 1):
                            addr   = c.get("address") or "address nahi"
                            phone_ = c.get("phone")   or "number nahi"
                            credit = c.get("total_credit", 0) or 0
                            options.append(
                                f"{i}. {cust_name.title()} — {addr} | {phone_} | Baaki: Rs {credit:,.0f}"
                            )
                        return {
                            "operation":   "customer_ambiguous",
                            "customer":    cust_name,
                            "qualifier":   cust_addr or "?",
                            "options":     options,
                            "description": "multiple customers with same name, need clarification"
                        }

                    elif resolution["action"] == "create":
                        # NEW customer — Python builds the customer upsert, NOT the LLM
                        # Use a unique filter: name + address so it never matches existing
                        new_addr  = cust_addr or None
                        new_phone = cust_phone or None
                        cust_filter = {"name": cust_name}
                        if new_addr:
                            cust_filter["address"] = new_addr

                        task["_python_customer_upsert"] = {
                            "operation":  "update_one",
                            "collection": "customers",
                            "filter":     cust_filter,
                            "update": {
                                "$set":         {"last_seen": "__TODAY_START__"},
                                "$setOnInsert": {
                                    "name":         cust_name,
                                    "address":      new_addr,
                                    "phone":        new_phone,
                                    "join_date":    "__TODAY_START__"
                                }
                            },
                            "upsert": True
                        }
                        task["address"] = new_addr
                        task["phone"]   = new_phone

                    elif resolution["action"] == "use":
                        matched  = resolution["customer"]
                        matched_addr = matched.get("address") or cust_addr
                        # Build exact filter using address to pin to the right customer
                        cust_filter = {"name": matched.get("name", cust_name)}
                        if matched_addr:
                            cust_filter["address"] = matched_addr

                        task["customer"] = matched.get("name", cust_name)
                        task["phone"]    = cust_phone or matched.get("phone")
                        task["address"]  = matched_addr

                        task["_python_customer_upsert"] = {
                            "operation":  "update_one",
                            "collection": "customers",
                            "filter":     cust_filter,
                            "update": {
                                "$set":         {"last_seen": "__TODAY_START__"},
                                "$setOnInsert": {
                                    "name":      matched.get("name", cust_name),
                                    "address":   matched_addr,
                                    "phone":     cust_phone or matched.get("phone"),
                                    "join_date": "__TODAY_START__"
                                }
                            },
                            "upsert": True
                        }
                        # Update address on existing customer if they had none
                        if resolution.get("update_address") and not matched.get("address"):
                            task["_python_customer_upsert"]["update"]["$set"]["address"] = cust_addr

                task["items"] = enriched
                return await sales_query_builder(task, user_message, enriched_items=enriched)
        return await sales_query_builder(task, user_message)

    elif builder == "customer":
        if intent == "customer_read" and task.get("customer"):
            # Resolve which customer using address — prevents showing wrong Ali's balance
            res = await _resolve_and_pin_customer(task)
            if res["status"] == "clarify":
                return {"operation": "customer_ambiguous_payment",
                        "response": res["response"]}
            if res["status"] == "not_found":
                return {"operation": "customer_not_found",
                        "customer": task.get("customer","?"),
                        "description": res["response"]}
            if res["status"] == "ok":
                # Pin the customer name and filter so LLM uses the right record
                task["customer"]       = res["name"]
                task["_pinned_filter"] = res["filter"]
                task["address"]        = res["address"]

        elif intent == "customer_write" and task.get("customer"):
            # For writes, still resolve to detect conflicts
            res = await _resolve_and_pin_customer(task)
            if res["status"] == "clarify":
                return {"operation": "customer_ambiguous_payment",
                        "response": res["response"]}
            if res["status"] == "ok":
                task["_pinned_filter"] = res["filter"]

        return await customer_query_builder(task, user_message)

    elif builder == "finance":
        if intent == "finance_write":
            amount = task.get("amount") or 0
            if task.get("customer") and amount:
                # ── Resolve the correct customer using address/qualifier ────────
                res = await _resolve_and_pin_customer(task)

                if res["status"] == "clarify":
                    return {"operation": "customer_ambiguous_payment",
                            "response": res["response"]}

                if res["status"] == "not_found":
                    return {"operation": "customer_not_found",
                            "customer": task.get("customer","?"),
                            "description": res["response"]}

                # Exact match — use real balance from the pinned customer doc
                doc            = res["customer"]
                current_credit = doc.get("total_credit", 0) or 0
                remaining      = max(0, current_credit - amount)
                task["current_credit"] = current_credit
                task["remaining"]      = remaining
                task["customer"]       = res["name"]        # normalised name from DB
                task["_pinned_filter"] = res["filter"]       # address-pinned filter
                task["address"]        = res["address"]
                task["phone"]          = res["phone"]

        return await finance_query_builder(task, user_message)

    else:
        return {"operation": "unsupported"}


async def query_builder_node(state):
    """
    Dispatch all tasks to specialized builders in parallel.
    Each builder only receives the schema it needs — no wasted tokens.
    History is injected so follow-up corrections work correctly.
    """
    tasks        = state.get("tasks", [])
    user_message = state["user_message"]
    history      = state.get("conversation_history") or []

    # Build history context string (last 4 messages = 2 exchanges)
    prior = history[-4:] if len(history) > 4 else history
    if prior:
        history_lines = [
            f"{'User' if h['role']=='user' else 'Agent'}: {h['content']}"
            for h in prior
        ]
        # Append context to user_message for specialized builders
        user_message_with_context = (
            "=== RECENT CONVERSATION (for context) ===\n" +
            "\n".join(history_lines) +
            "\n=== END ===\n\n" +
            f"Current message: {user_message}"
        )
    else:
        user_message_with_context = user_message

    if not tasks:
        return {"query_plan": {"operation": "unsupported"}, "all_plans": []}

    # ── Product name normalization — runs ONCE for ALL tasks before any builder ──
    # Fetch real inventory product names once, then fix misspellings in every task.
    # This covers reads (stock_read, sales_read) AND writes (stock_write, sales_write).
    # e.g. "chenni" → "cheeni", "dal" → "daal", "ghee" → "ghee" (exact, unchanged)
    known_products = await _get_all_inventory_products()
    all_corrections = {}

    if known_products:
        for task in tasks:
            items = task.get("items") or []
            fixed_items = []
            for item in items:
                typed = (item.get("product") or "").lower().strip()
                if not typed:
                    fixed_items.append(item); continue
                if typed in known_products:
                    fixed_items.append(item); continue
                matched = _fuzzy_match_product(typed, known_products)
                if matched and matched != typed:
                    all_corrections[typed] = matched
                    item = dict(item)
                    item["product"] = matched
                fixed_items.append(item)
            task["items"] = fixed_items

            # Also fix single product fields used in read queries
            if task.get("product"):
                typed = task["product"].lower().strip()
                if typed not in known_products:
                    matched = _fuzzy_match_product(typed, known_products)
                    if matched and matched != typed:
                        all_corrections[typed] = matched
                        task["product"] = matched

        if all_corrections:
            # Store on first task so executor can surface them to responder
            tasks[0]["_product_corrections"] = {
                **tasks[0].get("_product_corrections", {}),
                **all_corrections
            }
            # Also patch the user_message_with_context so LLM query builders
            # generate the corrected product name in their MongoDB filters
            corr_note = "NOTE: These product spellings were auto-corrected: " +                 ", ".join(f"'{k}' → '{v}'" for k,v in all_corrections.items())
            user_message_with_context = corr_note + "\n" + user_message_with_context

    # Run all specialized builders in parallel, passing history context
    plans = await asyncio.gather(*[
        _build_plan_for_task(task, user_message_with_context)
        for task in tasks
    ])

    # Tag each plan with its task description for the responder
    tagged_plans = []
    for task, plan in zip(tasks, plans):
        tagged_plans.append({
            "intent":  task.get("intent",""),
            "action":  task.get("action",""),
            "plan":    plan
        })

    # query_plan = first plan (for single-task compat), all_plans for multi
    return {
        "query_plan": plans[0] if plans else {"operation":"unsupported"},
        "all_plans":  tagged_plans
    }


# ─────────────────────────────────────────────────────────────────────────────
#  NODE 3 — QUERY EXECUTOR
#  Executes all plans sequentially, collects all results
# ─────────────────────────────────────────────────────────────────────────────

async def query_executor_node(state):
    import logging
    logger = logging.getLogger("hisabbot")

    all_plans = state.get("all_plans") or []
    if not all_plans:
        # Fallback: single plan
        plan = state.get("query_plan", {})
        all_plans = [{"intent": state.get("intent",""), "action": state.get("action",""), "plan": plan}]

    all_results = []

    for tagged in all_plans:
        plan   = tagged.get("plan", {})
        intent = tagged.get("intent","")
        action = tagged.get("action","")

        logger.info(f"EXECUTING [{intent}] {action}: {json.dumps(plan, default=str)[:200]}")
        logger.info(f"  all_plans count={len(all_plans)}, intent={intent!r}")

        if plan.get("operation") == "unsupported":
            all_results.append({"intent": intent, "action": action,
                                 "result": "ERROR: Is operation ka support nahi hai."})
            continue

        if plan.get("operation") == "missing_price":
            products = plan.get("products", [])
            products_str = ", ".join(products)
            all_results.append({"intent": intent, "action": action,
                "result": f"MISSING_PRICE:{products_str}"})
            continue

        if plan.get("operation") == "missing_cost_price":
            products = plan.get("products", [])
            products_str = ", ".join(products)
            all_results.append({"intent": intent, "action": action,
                "result": f"MISSING_COST_PRICE:{products_str}"})
            continue

        if plan.get("operation") == "stock_error":
            # Hard stock validation failed — surface all errors clearly
            error_lines = plan.get("errors", ["Stock nahi hai."])
            all_results.append({"intent": intent, "action": action,
                                 "result": "STOCK_ERROR:" + " | ".join(error_lines)})
            continue

        if plan.get("operation") == "customer_ambiguous_payment":
            all_results.append({"intent": intent, "action": action,
                "result": f"CUSTOMER_AMBIGUOUS:{plan.get('response','')}"})
            continue

        if plan.get("operation") == "customer_ambiguous":
            name    = (plan.get("customer","") or "?").title()
            qual    = plan.get("qualifier","")
            options = plan.get("options", [])
            opts_text = "\n".join(options)
            all_results.append({"intent": intent, "action": action,
                "result": f"CUSTOMER_AMBIGUOUS:{name}|{opts_text}"})
            continue

        if plan.get("operation") == "customer_not_found":
            customer = plan.get("customer","")
            all_results.append({"intent": intent, "action": action,
                                 "result": f"ERROR: {customer.title()} ka record nahi mila. Pehle customer add karein."})
            continue

        # ── Extract product correction notes ────────────────────────────────
        product_corrections = {}
        for t in (state.get("tasks") or []):
            if t.get("_product_corrections"):
                product_corrections.update(t["_product_corrections"])

        # ── Extract stock missing price warnings ─────────────────────────
        stock_missing_price = plan.pop("__stock_missing_price__", [])

        # ── Replace LLM customer ops with Python-built ones (sales) ─────
        python_cust_upsert = plan.pop("_python_customer_upsert", None)
        if python_cust_upsert and intent == "sales_write":
            plan = _replace_customer_ops_in_plan(plan, python_cust_upsert)

        # ── Replace LLM customer filter with pinned one (finance/customer)
        pinned_filter = None
        # Retrieve pinned filter from the original task
        for t in (state.get("tasks") or []):
            if t.get("intent") == intent and t.get("_pinned_filter"):
                pinned_filter = t["_pinned_filter"]
                break
        if pinned_filter and intent in ("finance_write", "customer_write"):
            plan = _apply_pinned_filter(plan, pinned_filter)

        result = await execute_plan(plan)

        if not result["ok"]:
            all_results.append({"intent": intent, "action": action,
                                 "result": f"ERROR: {result['error']}"})
            continue

        results  = result.get("results", [])
        modified = result.get("modified", 0)
        inserted = result.get("inserted", 0)
        upserted = result.get("upserted", 0)

        read_intents = {"stock_read","sales_read","customer_read","finance_read"}

        # Read query returned empty → tag immediately, never send to LLM
        if results == [] and intent in read_intents:
            all_results.append({
                "intent": intent, "action": action,
                "result": f"EMPTY_RESULT:{action}"
            })
            continue

        if results:
            entry = {"intent": intent, "action": action, "result": results}
            if product_corrections:
                entry["product_corrections"] = product_corrections
            all_results.append(entry)
        else:
            parts = []
            if inserted: parts.append(f"inserted:{inserted}")
            if modified: parts.append(f"modified:{modified}")
            if upserted: parts.append(f"new_customer_registered:{upserted}")

            # For stock writes: fetch updated quantities so responder can show real numbers
            if intent == "stock_write":
                # Collect product names from the plan
                products_to_fetch = []
                ops = plan.get("operations", [plan])
                for op in ops:
                    f_val = op.get("filter", {})
                    if f_val.get("product") and op.get("collection") == "inventory":
                        products_to_fetch.append(f_val["product"])

                stock_after = []
                for product in set(products_to_fetch):
                    fetch_result = await execute_plan({
                        "operation": "find", "collection": "inventory",
                        "filter": {"product": product}, "limit": 1
                    })
                    if fetch_result["ok"] and fetch_result["results"]:
                        doc = fetch_result["results"][0]
                        raw_qty = doc.get("qty", 0)
                        # Clamp to 0 — negative means oversold, treat as empty
                        actual_qty = max(0, raw_qty) if isinstance(raw_qty, (int, float)) else 0
                        stock_after.append({
                            "product":    doc.get("product", product),
                            "qty":        actual_qty,
                            "cost_price": doc.get("cost_price"),
                            "negative":   raw_qty < 0,   # flag for responder
                        })

                entry = {
                    "intent": intent, "action": action,
                    "result": {"status": "OK", "stock_updated": stock_after}
                }
                if stock_missing_price:
                    entry["stock_missing_price"] = stock_missing_price
                all_results.append(entry)
            else:
                # For finance_write, include real balance data computed before the plan ran
                tagged_task = next(
                    (t for t in (state.get("tasks") or [])
                     if t.get("intent") == intent and t.get("action") == action),
                    {}
                )
                if intent == "finance_write" and tagged_task.get("remaining") is not None:
                    customer  = (tagged_task.get("customer") or "").title()
                    address   = (tagged_task.get("address")  or "").strip()
                    amount    = tagged_task.get("amount", 0)
                    remaining = tagged_task.get("remaining", 0)
                    summary = (
                        f"PAYMENT_OK:customer={customer},"
                        f"address={address},"
                        f"amount={amount},"
                        f"remaining={remaining}"
                    )
                else:
                    summary = f"OK:{action}:" + ",".join(parts) if parts else f"OK:{action}"
                all_results.append({"intent": intent, "action": action, "result": summary})

    # Combine into single db_result string
    read_intents = {"stock_read", "sales_read", "customer_read", "finance_read"}

    if len(all_results) == 1:
        entry  = all_results[0]
        r      = entry["result"]
        intent_e = entry.get("intent","")
        action_e = entry.get("action","")

        # Pass special strings through unchanged
        special_prefixes = ("EMPTY_RESULT:","ERROR:","PAYMENT_OK:","STOCK_ERROR:",
                            "MISSING_PRICE:","CUSTOMER_AMBIGUOUS:","STOCK_KHATAM:")
        if isinstance(r, str) and any(r.startswith(p) for p in special_prefixes):
            db_result = r

        # Read query returned empty list → explicit EMPTY flag, never pass to LLM
        elif intent_e in read_intents and (r == [] or r == "" or r is None):
            db_result = f"EMPTY_RESULT:{action_e}"

        elif isinstance(r, list) and len(r) == 0 and intent_e in read_intents:
            db_result = f"EMPTY_RESULT:{action_e}"

        elif isinstance(r, list):
            db_result = json.dumps(r, ensure_ascii=False, default=str)

        elif isinstance(r, dict):
            r = dict(r)
            smp  = entry.get("stock_missing_price", [])
            corr = entry.get("product_corrections", {})
            if smp:  r["missing_price_products"] = smp
            if corr: r["product_corrections"]     = corr
            db_result = json.dumps(r, ensure_ascii=False, default=str)

        else:
            db_result = str(r)

    else:
        # Multi-task: tag empty read results explicitly
        tagged = []
        for entry in all_results:
            r_val    = entry.get("result")
            intent_e = entry.get("intent","")
            action_e = entry.get("action","")
            if intent_e in read_intents and (r_val == [] or r_val == "" or r_val is None):
                entry = dict(entry)
                entry["result"] = f"EMPTY_RESULT:{action_e}"
            tagged.append(entry)
        db_result = json.dumps(tagged, ensure_ascii=False, default=str)

    return {"db_result": db_result}


# ─────────────────────────────────────────────────────────────────────────────
#  NODE 4 — RESPONDER
# ─────────────────────────────────────────────────────────────────────────────

RESPONDER_PROMPT = """
You are HisabBot, a wholesale business assistant. Convert DB results to clean Roman Urdu.

=== STRICT RULES — READ BEFORE ANSWERING ===
DATA INTEGRITY (most important):
1. ONLY report numbers, names, products that are EXPLICITLY in the DB result.
2. NEVER use data from training, conversation history, or the user's question.
3. Null/missing field → write "maloom nahi", never guess.
4. Empty [] → write the appropriate empty message, never invent.
5. Never say "records mil gaye" or "data available hai" — show the ACTUAL data.
6. Never summarize without showing the numbers.

TONE:
- Warm and professional, like a trusted business assistant.
- Direct answers first, no preamble like "Ji zaroor" or "Bilkul".
- For empty results: be helpful, suggest the next step.
- For successful operations: confirm briefly and clearly.
- Never say "database mein" in normal responses — just give the answer.

FORMAT:
- Roman Urdu only. No Urdu script.
- Numbers: Rs X,XXX format. Exact — no rounding.
- One item per line for lists.
- No bullet symbols (•) — use spaces and dashes for alignment.

=== FIELD TRANSLATIONS ===
name / customer / product → naam
qty / total_qty           → units
cost_price                → lagat (per unit)
selling_price             → selling rate (per unit)
sale_total / total_revenue → wasool
cost_total / total_cost   → total lagat
profit / total_profit     → munafa (positive) OR nuqsan (negative — show absolute value)
total_credit              → baaki
count / loss_count        → tadaad
modified / inserted       → saved

=== PROFIT/LOSS ===
- profit > 0  → "Munafa: Rs X"
- profit < 0  → "Nuqsan: Rs X" (absolute value, no minus)
- profit = 0  → "Koi munafa/nuqsan nahi"
- profit null → "Munafa maloom nahi (cost price nahi tha)"
- total_profit > 0 → "Kul munafa: Rs X"
- total_profit < 0 → "Kul nuqsan: Rs X"
- Empty result + nuqsan asked → "Alhamdulillah, koi nuqsan nahi hua."
- Empty result + pichle saal  → "Pichle saal ka koi record nahi mila."
- Empty result general        → give a helpful message with next steps (see EMPTY RESULT RULES)

=== MULTI-TASK RESULTS ===
When result is an array of tasks, handle each separately in order.
Show each result on its own line/section. Use the "action" field as context.

=== RULES ===
1. Roman Urdu ONLY. No Urdu script. No English sentences.
2. Answer what was asked. One record = one line.
3. Money: always "Rs X". Exact numbers, no rounding.
4. No filler. No "umeed hai", "theek hai bhai".
5. No escape characters. Real newlines only.
6. No dashes — or – in output.
7. Sale confirmations: NEVER show profit. Only customer, product, qty, rate, total.
8. If new_customer_registered in result: add "X naya customer register ho gaya."
9. Year numbers: only write if DB result explicitly has a date field. Never invent.
10. NEVER output HTML tags like <div>, <br>, <span> etc. Plain text only.
11. NEVER output CSS class names or any web code.
12. PRODUCT CORRECTIONS: If result has "product_corrections" dict like {"chenni":"cheeni"},
    add a note at the end: "(Note: 'chenni' ko 'cheeni' samjha gaya)"
    Keep it brief, one line. This helps owner know the spelling was auto-corrected.
12. CRITICAL — NEVER HALLUCINATE DATA: Only report what is in the DB result.
    If result is [] (empty array) → the Python handler will respond, not you.
    If result has no matching customer → say "X ka koi record nahi mila."
    NEVER make up payment amounts, balances, or names not present in the result.
    NEVER say "Koi record nahi mila." — use descriptive messages only.
13. Finance/balance queries with empty result:
    [] on customers → "Is naam ka customer register nahi hai."
    [] on finance   → "Koi payment transaction record nahi mila."

=== PATTERNS ===

STOCK ADDED (result has stock_updated array):
Format as a clean table. One product per line:

Stock update ho gaya:
  Cheeni    : 350 units  | Cost: Rs 10,000/bag
  Daal      : 700 units  | Cost: Rs 6,000/bag
  Chawal    : 600 units  | Cost: nahi diya

Rules for stock table:
- Product name: title case, padded to align
- qty: show from "qty" field in stock_updated (already clamped to 0 minimum)
- If "negative": true for a product → show "0 units  [STOCK KHATAM]"
- Cost: show if cost_price is not null, else write "nahi diya"
- No blank lines between products
- After table, show any zero/negative stock warnings
- If result has "missing_price_products" array → add this after the table:
  "⚠ In items ki cost price nahi di — aglay message mein batain:
    Aata price XXXX, Ghee price XXXX"

STOCK ERROR (result starts with "STOCK_ERROR:"):
Parse each error after the colon. Format as:
  Sale nahi ho saki — stock kam hai:
  Cheeni : maujood 650 units, maanga 655, kum 5 units
  Ghee   : maujood 0 units, maanga 100, kum 100 units
  Pehle stock bharein, phir sale record karein.

SALE DONE:
Sale record ho gayi:
  Ali       : 30 Cheeni   @ Rs 3,550/unit  = Rs 106,500
  (If new customer): Ali naya customer register ho gaya.

PAYMENT RECEIVED:
Rs 5,000 Ali se mili. Remaining baaki: Rs X.

STOCK CHECK:
Cheeni  : 200 units  | Rs 5,000/unit
Aata    :   0 units  | Rs 1,500/unit  [STOCK KHATAM]
Daal    :   3 units  | Rs 6,000/unit  [LOW STOCK]

Rules for stock display:
- qty <= 0  → show "0 units [STOCK KHATAM]"
- qty <= low_stock_threshold (usually 5) → show "[LOW STOCK]"
- qty > threshold → no badge

SALES REPORT:
Aaj ki sale:
  Units sold : 750
  Wasool     : Rs 1,602,500
  Lagat      : Rs 1,590,000
  Munafa     : Rs 12,500

PER-PRODUCT:
  Daal   : 500 units | Rs 935,000 | Munafa: Rs 10,000
  Cheeni :  50 units | Rs 177,500 | Munafa: Rs 2,500

CUSTOMER BALANCE:
Ali par Rs 50,000 baaki hai.

CUSTOMER BILL / INVOICE (sales_read with bill/invoice/hisab action):
Format as a clean itemized bill. Show EVERY row from results individually.
Do NOT group or sum — show each sale line separately as the dealer recorded it.

Ali ka Bill:
  Tarikh        Product     Qty    Rate/Unit    Total
  ─────────────────────────────────────────────────────
  23-Mar-2026   Cheeni       30    Rs 3,550     Rs 106,500
  22-Mar-2026   Daal         50    Rs 1,800     Rs  90,000
  20-Mar-2026   Cheeni       20    Rs 3,500     Rs  70,000
  ─────────────────────────────────────────────────────
  Kul Kharidari: 3 transactions  |  Total: Rs 266,500

Rules for bill format:
- Show ALL rows from DB result, one per line
- Use "date" field for Tarikh — format as DD-Mon-YYYY
- "product" → title case
- "qty" → number
- "selling_price" → Rs X,XXX/unit
- "sale_total" → Rs X,XXX (right column)
- At bottom: count of rows + grand total (sum of all sale_total)
- If result is empty: "Ali ka koi purchase record nahi mila."
- After the bill table, show outstanding balance if available in result
"""

async def responder_node(state):
    # Handle conversation questions directly from history — no DB needed
    tasks  = state.get("tasks") or []
    intent = tasks[0].get("intent","") if tasks else state.get("intent","")

    if intent == "conversation":
        history = state.get("conversation_history") or []
        user_msg = state.get("user_message","")
        if not history:
            return {"final_response": "Abhi tak koi conversation nahi hui. Yeh pehla message hai."}
        # Build a readable summary of last exchange
        last_turns = history[-4:]
        lines = []
        for h in last_turns:
            role    = "Aapne kaha" if h["role"] == "user" else "Maine kaha"
            content = h["content"][:300] + ("..." if len(h["content"]) > 300 else "")
            lines.append(f"{role}: {content}")
        summary = "\n".join(lines)
        # Use LLM to answer the specific question about the conversation
        res = await groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": (
                    "You are HisabBot. The user is asking about the recent conversation. "
                    "Answer in Roman Urdu (Urdu words in English letters). "
                    "Be concise and direct. Only refer to what is in the conversation history provided."
                )},
                {"role": "user", "content": (
                    f"Recent conversation:\n{summary}\n\nUser is asking: {user_msg}"
                )}
            ],
            model=MODEL,
            temperature=0.0
        )
        return {"final_response": res.choices[0].message.content}

    db_result = (state.get("db_result") or "").strip()

    if not db_result:
        user_msg = state.get("user_message","").lower()
        if any(w in user_msg for w in ["stock","inventory"]):
            msg = "Abhi inventory mein koi item record nahi hai.\nStock add karne ke liye likhen, e.g.:\n  '200 bags cheeni price 5000 add karo'"
        elif any(w in user_msg for w in ["sale","bika","profit","munafa"]):
            msg = "Abhi tak koi sale record nahi ki gayi.\nSales record honi shuru hongi to yahan dikhen gi."
        elif any(w in user_msg for w in ["customer","baaki","payment"]):
            msg = "Koi record nahi mila.\nPehle data enter karen, phir dobara check karen."
        else:
            msg = "Koi record nahi mila.\nPehle data enter karen, phir dobara check karen."
        return {"final_response": msg}

    if db_result.startswith("ERROR:"):
        return {"final_response": db_result.replace("ERROR:","").strip()}

    # Handle EMPTY_RESULT directly — never send to LLM to prevent hallucination
    if db_result.startswith("EMPTY_RESULT:"):
        action = db_result.replace("EMPTY_RESULT:","").strip().lower()
        user_msg = state.get("user_message","")

        # Context-aware, helpful empty messages with next-step suggestions
        empty_map = {
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

        msg = None
        for key, val in empty_map.items():
            if key in action or key in user_msg.lower():
                msg = val
                break

        if not msg:
            msg = (
                f"Is query ke liye koi record nahi mila database mein.\n"
                f"Pehle data enter karen, phir dobara check karen."
            )
        return {"final_response": msg}

    if db_result.startswith("CUSTOMER_AMBIGUOUS:"):
        rest  = db_result.replace("CUSTOMER_AMBIGUOUS:","")
        pipe  = rest.find("|")
        name  = rest[:pipe] if pipe != -1 else rest
        options_text = rest[pipe+1:] if pipe != -1 else ""
        return {"final_response": (
            f"'{name}' naam ke multiple customers hain.\n"
            f"Kaunsa wala matlab hai?\n\n"
            f"{options_text}\n\n"
            f"Address ya phone number ke saath batain, e.g.:\n"
            f"  '{name.lower()} lahore wala ko sale karo'"
        )}

    if db_result.startswith("MISSING_COST_PRICE:"):
        products  = db_result.replace("MISSING_COST_PRICE:","").strip()
        prod_list = [p.strip() for p in products.split(",") if p.strip()]
        if len(prod_list) == 1:
            p = prod_list[0]
            return {"final_response": (
                f"{p} ki cost price (khareed qeemat) nahi di.\n"
                f"Aglay message mein price batain, e.g.:\n"
                f"  '{p.lower()} price 5000'"
            )}
        else:
            items_str = "\n".join(f"  - {p}" for p in prod_list)
            examples  = ", ".join(f"{p.lower()} price XXXX" for p in prod_list)
            return {"final_response": (
                f"In items ki cost price (khareed qeemat) nahi di:\n{items_str}\n\n"
                f"Aglay message mein prices batain, e.g.:\n"
                f"  '{examples}'"
            )}

    if db_result.startswith("MISSING_PRICE:"):
        products  = db_result.replace("MISSING_PRICE:","").strip()
        prod_list = [p.strip() for p in products.split(",") if p.strip()]
        if len(prod_list) == 1:
            p = prod_list[0]
            return {"final_response": (
                f"{p} ki selling price nahi di.\n"
                f"Aglay message mein price batain, e.g.:\n"
                f"  '{p.lower()} price 3000'"
            )}
        else:
            items_str = "\n".join(f"  - {p}" for p in prod_list)
            examples  = ", ".join(f"{p.lower()} price XXXX" for p in prod_list)
            return {"final_response": (
                f"In items ki selling price nahi di:\n{items_str}\n\n"
                f"Aglay message mein prices batain, e.g.:\n"
                f"  '{examples}'"
            )}

    if db_result.startswith("PAYMENT_OK:"):
        # Format payment confirmation directly without LLM
        # "PAYMENT_OK:customer=Ali,amount=30000,remaining=10000"
        import re
        params = {}
        for part in db_result.replace("PAYMENT_OK:","").split(","):
            if "=" in part:
                k,_,v = part.partition("=")
                params[k.strip()] = v.strip()
        customer  = params.get("customer","?")
        address   = params.get("address","").strip()
        amount    = params.get("amount","?")
        remaining = params.get("remaining","0")
        try:
            amt_fmt = f"Rs {float(amount):,.0f}"
            rem_fmt = f"Rs {float(remaining):,.0f}"
        except Exception:
            amt_fmt = f"Rs {amount}"
            rem_fmt = f"Rs {remaining}"
        # Show address to confirm which customer paid
        addr_part = f" ({address})" if address else ""
        if float(remaining) <= 0:
            rem_line = "Ab koi baaki nahi."
        else:
            rem_line = f"Remaining baaki: {rem_fmt}"
        return {"final_response": f"{customer}{addr_part} se {amt_fmt} payment mil gayi.\n{rem_line}"}

    if db_result.startswith("STOCK_ERROR:"):
        # Format stock shortage errors cleanly without LLM
        errors = db_result.replace("STOCK_ERROR:","").strip().split(" | ")
        lines = ["Sale nahi ho saki — stock kam hai:"]
        for err in errors:
            # "ERROR: Cheeni ka stock kam hai. Maujood: 650 units. Maanga gaya: 655 units. Kum: 5 units."
            clean = err.replace("ERROR:","").strip()
            lines.append(f"  {clean}")
        lines.append("Pehle stock bharein, phir sale record karein.")
        return {"final_response": "\n".join(lines)}

    try:
        parsed    = json.loads(db_result)
        formatted = json.dumps(parsed, indent=2, ensure_ascii=False, default=str)
    except Exception:
        formatted = db_result

    res = await groq_client.chat.completions.create(
        messages=[
            {"role": "system", "content": RESPONDER_PROMPT},
            {"role": "user",   "content": (
                f"User ne kaha: \"{state['user_message']}\"\n\n"
                f"=== DATABASE RESULT (ONLY use data from here) ===\n"
                f"{formatted}\n"
                f"=== END OF DATABASE RESULT ===\n\n"
                f"Format this data in Roman Urdu. "
                f"Do NOT add any numbers or names not present in the database result above."
            )}
        ],
        model=MODEL,
        temperature=0.0
    )
    response = res.choices[0].message.content
    # Final safety: strip any HTML that might have crept in
    import re as _re
    response = _re.sub(r"<[^>]*>", "", response).strip()
    return {"final_response": response}