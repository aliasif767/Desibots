"""
HisabBot Agent Nodes — v5 (Fully Dynamic, No Hardcoded Queries)

Flow:
  1. router_node      — LLM classifies message, extracts context
  2. query_builder_node — LLM generates complete MongoDB operation plan
  3. query_executor_node — executes plan via db_executor.py
  4. responder_node   — LLM formats results into clean Roman Urdu

tools.py is gone. No hardcoded queries anywhere.
"""

import json
import os
from groq import AsyncGroq
from .db_executor import execute_plan

groq_client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
MODEL = "llama-3.3-70b-versatile"


# ─────────────────────────────────────────────────────────────────────────────
#  NODE 1 — ROUTER
#  Classifies the message and extracts key context the query builder needs
# ─────────────────────────────────────────────────────────────────────────────

ROUTER_PROMPT = """
You are the intent classifier for HisabBot, a wholesale business assistant.
Messages are in Roman Urdu (Urdu written in English letters).

Your job: understand what the user wants and extract key facts.
Return ONLY a valid JSON object. No markdown. No explanation.

=== INTENT LIST ===
"write"  → user wants to CHANGE data (add stock, record sale, update customer, receive payment, set price)
"read"   → user wants to READ or QUERY data (check stock, view report, check balance, see history)
"unknown" → cannot understand

=== PRICE CONTEXT — CRITICAL ===
Two different prices exist in this business:
  cost_price    = what dealer PAID to buy the product (stock purchase price)
  selling_price = what the dealer CHARGES the customer (sale price)

When user adds stock with a price → that price is cost_price.
When user records a sale with a price → that price is selling_price.

=== OUTPUT FORMAT ===
{
  "intent":   "write" | "read" | "unknown",
  "action":   "<short description e.g. 'add stock', 'record sale', 'check balance', 'daily report'>",
  "entities": {
    "customer":      "<name lowercase or null>",
    "phone":         "<phone or null>",
    "address":       "<address or null>",
    "amount":        <float payment amount or null>,
    "items": [
      {
        "product":       "<product name lowercase>",
        "qty":           <integer or null>,
        "cost_price":    <float cost price per unit or null>,
        "selling_price": <float selling price per unit or null>
      }
    ]
  }
}

=== EXAMPLES ===
"50 bag cheeni add karo 3000 per bag"
→ intent=write, action="add stock", items=[{product:cheeni, qty:50, cost_price:3000}]

"ali ko 30 bag cheeni 3550 per bag diya"
→ intent=write, action="record sale", customer=ali, items=[{product:cheeni, qty:30, selling_price:3550}]

"ali ka baaki kitna hai"
→ intent=read, action="check customer balance", customer=ali

"aaj ki sale aur profit"
→ intent=read, action="daily sales and profit report"

"ali ne 5000 rupay diye"
→ intent=write, action="receive payment", customer=ali, amount=5000

"cheeni aur aata ka stock batao"
→ intent=read, action="check stock", items=[{product:cheeni},{product:aata}]
"""

async def router_node(state):
    res = await groq_client.chat.completions.create(
        messages=[
            {"role": "system", "content": ROUTER_PROMPT},
            {"role": "user",   "content": state["user_message"]}
        ],
        model=MODEL,
        response_format={"type": "json_object"},
        temperature=0.0
    )
    try:
        out = json.loads(res.choices[0].message.content)
    except Exception:
        out = {"intent": "unknown", "action": "", "entities": {}}

    if out.get("intent") not in ("write", "read", "unknown"):
        out["intent"] = "unknown"

    entities = out.get("entities", {})
    if not isinstance(entities.get("items"), list):
        entities["items"] = []

    return {
        "intent":       out.get("intent", "unknown"),
        "action":       out.get("action", ""),
        "entities":     entities,
        "extracted_intent": out
    }


# ─────────────────────────────────────────────────────────────────────────────
#  NODE 2 — QUERY BUILDER
#  LLM generates the complete MongoDB operation plan from user message + context
# ─────────────────────────────────────────────────────────────────────────────

SCHEMA = """
=== DATABASE SCHEMA ===

Collection: inventory
Purpose: tracks stock levels and purchase prices
Fields:
  product       (string, lowercase)  — product name e.g. "cheeni", "aata", "daal"
  qty           (int)                — current stock quantity
  cost_price    (float)              — price dealer paid per unit (purchase price)
  low_stock_threshold (int, default 5) — alert level

Collection: sales
Purpose: records every sale transaction
Fields:
  customer      (string, lowercase)  — customer name
  product       (string, lowercase)  — product sold
  qty           (int)                — quantity sold
  selling_price (float)              — price charged to customer per unit
  cost_price    (float)              — purchase price per unit (for profit calc)
  sale_total    (float)              — selling_price * qty
  cost_total    (float)              — cost_price * qty
  profit        (float)              — sale_total - cost_total
  date          (datetime)           — when sale happened

Collection: customers
Purpose: customer contact info and outstanding balance
Fields:
  name          (string, lowercase)  — customer name
  phone         (string)             — phone number
  address       (string)             — address
  total_credit  (float)              — total amount customer owes (increases on sale, decreases on payment)
  last_seen     (datetime)

Collection: finance
Purpose: payment and invoice records
Fields:
  customer      (string, lowercase)
  amount        (float)
  type          (string)             — "payment" or "invoice"
  date          (datetime)
"""

DATE_PLACEHOLDERS = """
=== DATE PLACEHOLDERS (use EXACTLY as written — Python resolves them at runtime) ===

CURRENT PERIOD:
  "__TODAY_START__"             = today 00:00 UTC
  "__TODAY_END__"               = today 23:59 UTC
  "__WEEK_START__"              = 7 days ago 00:00 UTC
  "__MONTH_START__"             = 1st of current month 00:00 UTC
  "__MONTH_END__"               = last moment of current month
  "__YEAR_START__"              = 1st Jan current year 00:00 UTC
  "__YEAR_END__"                = 31st Dec current year 23:59 UTC
  "__PREV_YEAR_START__"         = 1st Jan last year 00:00 UTC
  "__PREV_YEAR_END__"           = 31st Dec last year 23:59 UTC

PREVIOUS EXACT CALENDAR MONTHS (use these for "pichle mahine", "last month", "ek mahine pehle"):
  "__PREV_MONTH_START__"        = 1st of last month 00:00 UTC
  "__PREV_MONTH_END__"          = last moment of last month

N MONTHS AGO — exact calendar month boundaries:
  "__MONTHS_AGO_2_START__"      = 1st of 2 months ago
  "__MONTHS_AGO_2_END__"        = last moment of 2 months ago
  "__MONTHS_AGO_3_START__"      = 1st of 3 months ago
  (replace 2/3 with any number)

GENERAL DAY OFFSET:
  "__DAYS_AGO_30__"             = exactly 30 days ago (use for approximate ranges, not "last month")
  "__DAYS_AGO_7__"              = 7 days ago

=== CRITICAL DATE RULES ===
1. "pichle mahine" / "last month" / "ek mahine pehle" → ALWAYS use BOTH:
     $gte: "__PREV_MONTH_START__"  AND  $lte: "__PREV_MONTH_END__"
   NEVER use just $gte alone — that would include current month data too.

2. "2 mahine pehle" / "2 months ago" → use:
     $gte: "__MONTHS_AGO_2_START__"  AND  $lte: "__MONTHS_AGO_2_END__"

3. "is mahine" / "this month" / "current month" → use:
     $gte: "__MONTH_START__"  AND  $lte: "__MONTH_END__"

4. "aaj" / "today" → use:
     $gte: "__TODAY_START__"  AND  $lte: "__TODAY_END__"

5. ALWAYS use BOTH $gte and $lte for any time range query — never just one side.

6. "pichle saal" / "last year" / "ek saal pehle" / "2025 mein" → use:
     $gte: "__PREV_YEAR_START__"  AND  $lte: "__PREV_YEAR_END__"
   NEVER use __YEAR_START__ for "pichle saal" — that is 2026 (current year), NOT 2025.
   NEVER use __YEAR_START__ without $lte — open-ended queries match all future data too.

7. "is saal" / "this year" / "2026 mein" → use:
     $gte: "__YEAR_START__"  AND  $lte: "__YEAR_END__"

8. "abi tak" / "abhi tak" / "total ever" / "sab time" → NO date filter at all.
   Do NOT add any $match on date. Query all records without date restriction.

9. If query asks for loss only (nuqsan) → add filter: {"profit": {"$lt": 0}}
   If query asks for profit only (munafa) → add filter: {"profit": {"$gt": 0}}
   If asks total including both → no profit filter, just sum all.

10. EMPTY RESULT HANDLING: If no matching records found, the result will be empty [].
    The responder will handle empty results — do not add fake data.
"""

QUERY_BUILDER_PROMPT = """
You are a MongoDB query generator for HisabBot.
You receive: (a) the user's original message, (b) extracted intent/entities from the router.
Generate the MongoDB operation plan to fulfill the request.
Return ONLY a valid json object. No markdown. No explanation.

""" + SCHEMA + DATE_PLACEHOLDERS + """

=== OPERATION TYPES ===

READ:
  find      → collection.find(filter, projection).sort().limit()
  aggregate → collection.aggregate(pipeline)
  count     → collection.count_documents(filter)

WRITE:
  insert_one  → insert a single document
  update_one  → update one document (with upsert:true for create-or-update)
  update_many → update multiple documents

MULTI-STEP (use "operations" array when task needs multiple DB calls):
  e.g. recording a sale requires:
    1. check inventory (find)
    2. deduct stock (update_one)
    3. insert sale record (insert_one)
    4. update customer credit (update_one with upsert)

=== OUTPUT FORMAT — single operation ===
{
  "operation":  "find | aggregate | count | insert_one | update_one | update_many",
  "collection": "inventory | sales | customers | finance",
  "filter":     {...},          // for find, count, update_one, update_many
  "update":     {...},          // for update_one, update_many — use $set, $inc etc.
  "upsert":     true/false,     // for update_one only
  "document":   {...},          // for insert_one
  "pipeline":   [...],          // for aggregate
  "sort":       {"field": -1},  // for find
  "limit":      20,             // for find
  "description": "what this does"
}

=== OUTPUT FORMAT — multi-step ===
{
  "operations": [
    { ...step1... },
    { ...step2... },
    { ...step3... }
  ],
  "description": "what the full operation does"
}

=== WRITE RULES — READ CAREFULLY ===
1. For sale transactions: ALWAYS multi-step:
   Step 1 — find inventory to confirm stock and get cost_price
   Step 2 — update_one inventory: {$inc: {qty: -N}}
   Step 3 — insert_one sales: include all fields (customer, product, qty,
             selling_price, cost_price, sale_total, cost_total, profit, date)
             All values pre-computed — use them exactly as given in ENRICHED ITEMS.
             For date use "__TODAY_START__"
   Step 4 — update_one customers (HANDLES BOTH NEW AND EXISTING CUSTOMERS):
             filter:  {"name": customer_name}
             update:  {
               "$inc":         {"total_credit": sale_total},
               "$set":         {"last_seen": "__TODAY_START__"},
               "$setOnInsert": {"name": customer_name, "phone": null, "address": null, "join_date": "__TODAY_START__"}
             }
             upsert: true
             IMPORTANT: $setOnInsert fields are ONLY written when creating a NEW customer document.
             For existing customers, only $inc and $set apply. This auto-registers new customers.

2. For add stock: update_one inventory with upsert:true
   {$inc: {qty: N}, $set: {cost_price: X}}  — only $set cost_price if provided

3. For receive payment: TWO steps:
   Step 1 — update_one customers: {$inc: {total_credit: -amount}, $set: {last_seen: "__TODAY_START__"}}
   Step 2 — insert_one finance: {customer, amount, type:"payment", date:"__TODAY_START__"}

4. For add/update customer: update_one customers with upsert:true
   update: {$set: {provided fields}, $setOnInsert: {name: customer_name, total_credit: 0, join_date: "__TODAY_START__"}}

5. For set cost price only: update_one inventory, $set cost_price, upsert:true

6. For invoice/bill: aggregate on sales collection for today's records for that customer

7. All string values in filters must be LOWERCASE (products and customers stored lowercase)

8. Never use deleteOne, deleteMany, drop, insertMany, $where, $function

=== READ EXAMPLES ===

"aaj ki sale aur profit":
{
  "operation": "aggregate",
  "collection": "sales",
  "pipeline": [
    {"$match": {"date": {"$gte": "__TODAY_START__"}}},
    {"$group": {"_id": null,
      "total_qty": {"$sum": "$qty"},
      "total_revenue": {"$sum": "$sale_total"},
      "total_cost": {"$sum": "$cost_total"},
      "total_profit": {"$sum": "$profit"}
    }}
  ]
}

"har product ka aaj profit":
{
  "operation": "aggregate",
  "collection": "sales",
  "pipeline": [
    {"$match": {"date": {"$gte": "__TODAY_START__"}}},
    {"$group": {"_id": "$product", "qty": {"$sum": "$qty"},
      "revenue": {"$sum": "$sale_total"}, "profit": {"$sum": "$profit"}}},
    {"$sort": {"profit": -1}}
  ]
}

"ali ka baaki":
{"operation": "find", "collection": "customers", "filter": {"name": "ali"}}

"kaunsa product sabse zyada bikta hai":
{
  "operation": "aggregate",
  "collection": "sales",
  "pipeline": [
    {"$group": {"_id": "$product", "total_qty": {"$sum": "$qty"}}},
    {"$sort": {"total_qty": -1}},
    {"$limit": 5}
  ]
}

"pichle mahine / ek mahine pehle kaunsa product sabse zyada profit hua":
{
  "operation": "aggregate",
  "collection": "sales",
  "pipeline": [
    {"$match": {"date": {"$gte": "__PREV_MONTH_START__", "$lte": "__PREV_MONTH_END__"}}},
    {"$group": {"_id": "$product", "total_qty": {"$sum": "$qty"},
      "total_profit": {"$sum": "$profit"}, "total_revenue": {"$sum": "$sale_total"}}},
    {"$sort": {"total_profit": -1}}
  ]
}

"is mahine ki total sale aur profit":
{
  "operation": "aggregate",
  "collection": "sales",
  "pipeline": [
    {"$match": {"date": {"$gte": "__MONTH_START__", "$lte": "__MONTH_END__"}}},
    {"$group": {"_id": null,
      "total_qty": {"$sum": "$qty"},
      "total_revenue": {"$sum": "$sale_total"},
      "total_cost": {"$sum": "$cost_total"},
      "total_profit": {"$sum": "$profit"}
    }}
  ]
}

"2 mahine pehle kaunsa product zyada bika":
{
  "operation": "aggregate",
  "collection": "sales",
  "pipeline": [
    {"$match": {"date": {"$gte": "__MONTHS_AGO_2_START__", "$lte": "__MONTHS_AGO_2_END__"}}},
    {"$group": {"_id": "$product", "total_qty": {"$sum": "$qty"}, "total_profit": {"$sum": "$profit"}}},
    {"$sort": {"total_qty": -1}}
  ]
}

"abi tak total loss kitna hua / total nuqsan":
{
  "operation": "aggregate",
  "collection": "sales",
  "pipeline": [
    {"$match": {"profit": {"$lt": 0}}},
    {"$group": {"_id": null, "total_loss": {"$sum": "$profit"}, "loss_count": {"$sum": 1}}}
  ]
}

"abi tak total munafa / overall profit ever":
{
  "operation": "aggregate",
  "collection": "sales",
  "pipeline": [
    {"$group": {"_id": null,
      "total_profit": {"$sum": "$profit"},
      "total_revenue": {"$sum": "$sale_total"},
      "total_cost": {"$sum": "$cost_total"},
      "total_qty": {"$sum": "$qty"}
    }}
  ]
}

"pichle saal / last year / 2025 mein kaunsa product zyada bika":
{
  "operation": "aggregate",
  "collection": "sales",
  "pipeline": [
    {"$match": {"date": {"$gte": "__PREV_YEAR_START__", "$lte": "__PREV_YEAR_END__"}}},
    {"$group": {"_id": "$product", "total_qty": {"$sum": "$qty"}, "total_profit": {"$sum": "$profit"}}},
    {"$sort": {"total_profit": -1}}
  ]
}

"is saal / 2026 mein total sale":
{
  "operation": "aggregate",
  "collection": "sales",
  "pipeline": [
    {"$match": {"date": {"$gte": "__YEAR_START__", "$lte": "__YEAR_END__"}}},
    {"$group": {"_id": null,
      "total_qty": {"$sum": "$qty"},
      "total_revenue": {"$sum": "$sale_total"},
      "total_profit": {"$sum": "$profit"}
    }}
  ]
}

=== WRITE EXAMPLES ===

"50 bag cheeni add karo 3000 per bag":
{
  "operation": "update_one",
  "collection": "inventory",
  "filter": {"product": "cheeni"},
  "update": {"$inc": {"qty": 50}, "$set": {"cost_price": 3000}},
  "upsert": true
}

"ali ko 30 bag cheeni 3550 per bag diya" (assuming cost_price=3000 from router context):
{
  "operations": [
    {
      "operation": "update_one",
      "collection": "inventory",
      "filter": {"product": "cheeni"},
      "update": {"$inc": {"qty": -30}}
    },
    {
      "operation": "insert_one",
      "collection": "sales",
      "document": {
        "customer": "ali", "product": "cheeni", "qty": 30,
        "selling_price": 3550, "cost_price": 3000,
        "sale_total": 106500, "cost_total": 90000, "profit": 16500,
        "date": "__TODAY_START__"
      }
    },
    {
      "operation": "update_one",
      "collection": "customers",
      "filter": {"name": "ali"},
      "update": {
        "$inc":         {"total_credit": 106500},
        "$set":         {"last_seen": "__TODAY_START__"},
        "$setOnInsert": {"name": "ali", "phone": null, "address": null, "join_date": "__TODAY_START__"}
      },
      "upsert": true
    }
  ]
}

"ali ne 5000 rupay diye":
{
  "operations": [
    {
      "operation": "update_one",
      "collection": "customers",
      "filter": {"name": "ali"},
      "update": {"$inc": {"total_credit": -5000}}
    },
    {
      "operation": "insert_one",
      "collection": "finance",
      "document": {"customer": "ali", "amount": 5000, "type": "payment", "date": "__TODAY_START__"}
    }
  ]
}
"""

async def _fetch_inventory_for_sale(items: list) -> dict:
    """Pre-fetch cost_price and available qty from inventory for each product."""
    inventory = {}
    for item in items:
        product = (item.get("product") or "").lower().strip()
        if not product:
            continue
        result = await execute_plan({
            "operation": "find",
            "collection": "inventory",
            "filter": {"product": product},
            "limit": 1
        })
        if result["ok"] and result["results"]:
            doc = result["results"][0]
            inventory[product] = {
                "qty":        doc.get("qty", 0),
                "cost_price": doc.get("cost_price"),
            }
        else:
            inventory[product] = {"qty": 0, "cost_price": None}
    return inventory


async def query_builder_node(state):
    """
    Two-pass node:
      Pass 1 (Python): for sale operations, fetch real cost_price from inventory
                       and compute sale_total, cost_total, profit in Python
      Pass 2 (LLM):    build the MongoDB plan using the pre-computed numbers
    """
    action   = state.get("action", "")
    intent   = state.get("intent", "")
    entities = state.get("entities", {})
    items    = entities.get("items", [])

    inventory_context = ""
    is_sale = intent == "write" and any(
        kw in action.lower()
        for kw in ("sale", "sell", "becha", "diya", "de dia", "record")
    )

    if is_sale and items:
        inv_data = await _fetch_inventory_for_sale(items)

        enriched_items = []
        for item in items:
            product   = (item.get("product") or "").lower().strip()
            inv       = inv_data.get(product, {})
            real_cp   = inv.get("cost_price")      # actual cost_price from DB
            avail_qty = inv.get("qty", 0)
            sp        = item.get("selling_price")
            qty       = item.get("qty") or 0

            # All arithmetic done here in Python — LLM only writes the plan
            sale_total = round(sp * qty, 2)                        if sp                        else None
            cost_total = round(real_cp * qty, 2)                   if real_cp                   else None
            profit     = round(sale_total - cost_total, 2)         if sale_total and cost_total else None

            enriched_items.append({
                **item,
                "cost_price":    real_cp,
                "sale_total":    sale_total,
                "cost_total":    cost_total,
                "profit":        profit,
                "available_qty": avail_qty,
            })

        entities = {**entities, "items": enriched_items}

        lines = ["=== INVENTORY DATA (fetched from DB) ==="]
        for p, v in inv_data.items():
            cp_str = f"Rs {v['cost_price']}" if v["cost_price"] else "NOT SET in inventory"
            lines.append(f"  {p}: available={v['qty']} units | cost_price={cp_str}")
        lines.append("")
        lines.append("=== ENRICHED ITEMS — use these EXACT numbers in the plan, do not recompute ===")
        for it in enriched_items:
            lines.append(f"  {json.dumps(it)}")
        inventory_context = "\n".join(lines) + "\n\n"

    context = (
        f"User message: \"{state['user_message']}\"\n\n"
        f"Router extracted:\n"
        f"  intent:   {intent}\n"
        f"  action:   {action}\n"
        f"  entities: {json.dumps(entities, ensure_ascii=False)}\n\n"
        + inventory_context
        + "Generate the MongoDB operation plan."
    )

    res = await groq_client.chat.completions.create(
        messages=[
            {"role": "system", "content": QUERY_BUILDER_PROMPT},
            {"role": "user",   "content": context}
        ],
        model=MODEL,
        response_format={"type": "json_object"},
        temperature=0.0
    )
    try:
        plan = json.loads(res.choices[0].message.content)
    except Exception:
        plan = {"operation": "unsupported"}

    return {"query_plan": plan}


# ─────────────────────────────────────────────────────────────────────────────
#  NODE 3 — QUERY EXECUTOR
#  Runs the plan against MongoDB via db_executor.py
# ─────────────────────────────────────────────────────────────────────────────

async def query_executor_node(state):
    plan = state.get("query_plan", {})

    # Log the plan so we can debug date issues
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("hisabbot")
    logger.info(f"QUERY PLAN: {json.dumps(plan, ensure_ascii=False, default=str)}")

    if plan.get("operation") == "unsupported":
        return {"db_result": "ERROR: Is sawaal ka jawab database se nahi ho sakta."}

    result = await execute_plan(plan)

    if not result["ok"]:
        return {"db_result": f"ERROR: {result['error']}"}

    # Build a summary string for the responder
    results  = result.get("results", [])
    modified = result.get("modified", 0)
    inserted = result.get("inserted", 0)
    upserted = result.get("upserted", 0)

    if results:
        return {"db_result": json.dumps(results, ensure_ascii=False, default=str)}

    # Write operation with no results to return — build a status summary
    parts = []
    if inserted: parts.append(f"inserted:{inserted}")
    if modified: parts.append(f"modified:{modified}")
    if upserted: parts.append(f"new_customer_registered:{upserted}")
    desc = plan.get("description") or state.get("action") or "operation"
    summary = f"OK:{desc}:" + ",".join(parts) if parts else f"OK:{desc}"
    return {"db_result": summary}


# ─────────────────────────────────────────────────────────────────────────────
#  NODE 4 — RESPONDER
#  LLM formats DB results into clean Roman Urdu
# ─────────────────────────────────────────────────────────────────────────────

RESPONDER_PROMPT = """
You are HisabBot, a wholesale business assistant. Convert DB results to clean Roman Urdu.

=== FIELD TRANSLATIONS ===
name / customer / product → product ya customer ka naam
qty / total_qty           → units
cost_price                → lagat (per unit)
selling_price             → selling rate (per unit)
sale_total / total_revenue → wasool (total amdani)
cost_total / total_cost   → total lagat
profit / total_profit     → munafa (if positive) OR nuqsan (if negative — show as positive number with "nuqsan" label)
total_credit              → baaki
count                     → tadaad
modified / inserted       → changes saved

=== PROFIT vs LOSS RULES ===
Per-record level:
- profit > 0  → "Munafa: Rs X"
- profit < 0  → "Nuqsan: Rs X" (absolute value, no minus sign)
- profit = 0  → "Koi munafa/nuqsan nahi"
- profit = null → "Munafa maloom nahi (cost price set nahi tha)"

Summary/aggregate level (total_profit field):
- total_profit > 0  → "Kul munafa: Rs X"
- total_profit < 0  → "Kul nuqsan: Rs X" (absolute value)
- total_profit = 0  → "Na koi munafa, na koi nuqsan"
- total_loss field  → show as "Kul nuqsan: Rs X" (absolute value)

EMPTY RESULT RULES (when DB returns [] empty array):
- User asked about loss → "Alhamdulillah, abhi tak koi nuqsan nahi hua."
- User asked about profit in a time range → "Is waqt mein koi sale nahi mili."
- User asked about last year → "Pichle saal ka koi record nahi mila database mein."
- User asked about a specific product → "Is product ki koi sale nahi mili us waqt mein."
- General empty → "Koi record nahi mila."

NEVER say "Koi munafa nahi, koi nuqsan nahi" for an empty result — that implies zero total,
but empty means no data at all. Use the EMPTY RESULT RULES above instead.

YEAR LABEL RULE — VERY IMPORTANT:
- NEVER write a year (2025, 2026 etc.) in your response unless the DB result explicitly contains a date field.
- Do NOT copy the year from the user's question into the response as if it is confirmed data.
- If user asks "pichle saal" and DB returns empty → say "Pichle saal ka koi record nahi mila."
- If user asks "pichle saal" and DB returns data → say "Pichle saal ki detail:" (no year number unless DB has it).
- The DB stores dates — if you need to mention a year, read it from the data, do not assume it.

=== RULES ===
1. Roman Urdu ONLY. No Urdu script. No full English sentences.
2. Answer ONLY what was asked — look at the user message.
3. One record = one line. Keep it short and dense.
4. Money: always "Rs X" — exact numbers, no rounding.
5. No filler phrases. No "umeed hai", "theek hai bhai".
6. No escape characters. Real line breaks only.
7. No dashes like — or –.
8. For write confirmations (OK:...): confirm briefly what was done. 1-2 lines max.
9. NEVER show profit/munafa in sale confirmations — that is internal data. Only show: customer, product, qty, rate, total.
   Profit is ONLY shown when user explicitly asks for a report or profit query.
9. For errors: say clearly what went wrong in 1 line.
10. For empty results: say what was not found.

=== OUTPUT PATTERNS ===

Write confirmation (OK:add stock:...):
  50 Cheeni stock mein add ho gaya. Total: 250 units.

Write confirmation (OK:record sale:...):
  Sale record ho gayi. Ali ko 30 Cheeni @ Rs 3,550/unit diya. Total: Rs 106,500.
  (If new_customer_registered is in the result, add on next line: "Ali naya customer register ho gaya.")
  Do NOT mention munafa/profit in sale confirmations. Profit is internal data.

Write confirmation (OK:receive payment:...):
  Rs 5,000 payment Ali se mil gayi.

Report totals:
  Aaj ki sale:
    750 units bike
    Wasool: Rs 1,602,500
    Lagat: Rs 1,590,000
    Munafa: Rs 12,500

Per-product list:
  Daal: 500 units | Munafa: Rs 10,000
  Cheeni: 50 units | Munafa: Rs 2,500

Customer balance:
  Ali par Rs 50,000 baaki hai.

Stock list:
  Cheeni: 200 units | Lagat: Rs 3,000/unit
  Aata: 150 units

Top products:
  Sabse zyada bika: Daal (500 units)
  Uske baad: Cheeni (50 units)
"""

async def responder_node(state):
    db_result = (state.get("db_result") or "").strip()

    if not db_result:
        return {"final_response": "Koi result nahi mila."}

    if db_result.startswith("ERROR:"):
        return {"final_response": db_result.replace("ERROR:", "").strip()}

    # Pretty-print JSON for easier LLM reading
    try:
        parsed = json.loads(db_result)
        formatted = json.dumps(parsed, indent=2, ensure_ascii=False, default=str)
    except Exception:
        formatted = db_result  # OK:... write confirmation — not JSON

    res = await groq_client.chat.completions.create(
        messages=[
            {"role": "system", "content": RESPONDER_PROMPT},
            {"role": "user", "content": (
                f"User ne poocha: \"{state['user_message']}\"\n\n"
                f"DB result:\n{formatted}"
            )}
        ],
        model=MODEL,
        temperature=0.0
    )
    return {"final_response": res.choices[0].message.content}