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
"sales_read"     → view sales/profit report (e.g. "aaj ki sale", "har product ka profit")
"customer_write" → add/update customer info (e.g. "ali ka number 03001234567")
"customer_read"  → view customer info/balance (e.g. "ali ka baaki", "ali ki detail")
"finance_write"  → record payment received  (e.g. "ali ne 5000 diye")
"finance_read"   → view payment history / generate invoice (e.g. "ali ka bill banao")
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
      "customer": "<name lowercase or null>",
      "phone":    "<phone or null>",
      "address":  "<address or null>",
      "amount":   <float or null>,
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

"ali ka baaki kitna hai aur ali ka number 0300 save karo"
→ tasks: [
    {{intent:"customer_read", action:"check balance", customer:"ali"}},
    {{intent:"customer_write", action:"update phone", customer:"ali", phone:"0300"}}
  ]
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
        out = {"tasks": [{"intent": "unknown", "action": "", "items": []}]}

    tasks = out.get("tasks", [])
    if not isinstance(tasks, list) or not tasks:
        tasks = [{"intent": "unknown", "action": "", "items": []}]

    # Normalise items in each task
    for task in tasks:
        if not isinstance(task.get("items"), list):
            task["items"] = []

    return {
        "tasks":            tasks,
        "intent":           tasks[0].get("intent", "unknown"),  # for state compat
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
      "filter": {{"name": "<customer>"}},
      "update": {{
        "$inc": {{"total_credit": <sale_total>}},
        "$set": {{"last_seen": "__TODAY_START__"}},
        "$setOnInsert": {{"name": "<customer>", "phone": null, "address": null, "join_date": "__TODAY_START__"}}
      }},
      "upsert": true
    }}
  ],
  "description": "record sale"
}}

For MULTIPLE products to the SAME customer: repeat the 3 steps for each product.
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

"ali ka bill / invoice":
{{"operation":"aggregate","collection":"sales","pipeline":[
  {{"$match":{{"customer":"ali","date":{{"$gte":"__TODAY_START__","$lte":"__TODAY_END__"}}}}}},
  {{"$sort":{{"date":-1}}}}
]}}

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
    ]
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
Fields: customer (string lowercase), amount (float), type (string: "payment" or "invoice"), date (datetime)
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
        "customer": "<customer_name_lowercase>",
        "amount": <amount>,
        "type": "payment",
        "date": "__TODAY_START__"
      }}
    }}
  ],
  "description": "receive payment"
}}

Customer name MUST be lowercase. Amount must be a number (not string).
"""

FINANCE_READ_PROMPT = f"""
You are a MongoDB query generator for HisabBot finance queries.
{JSON_RULE}

{FINANCE_SCHEMA}
{DATE_RULES}

EXAMPLES:
"ali ke payments / ali ka payment history":
{{"operation":"find","collection":"finance","filter":{{"customer":"ali","type":"payment"}},"sort":{{"date":-1}}}}

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

    context = (
        f"User message: \"{user_message}\"\n"
        f"Action: {task.get('action','')}\n"
        f"Customer: {task.get('customer','')} | Amount: {task.get('amount','')}\n"
        f"Generate the MongoDB plan."
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

async def _build_plan_for_task(task: dict, user_message: str) -> dict:
    """Build a MongoDB plan for a single task using the right specialized builder."""
    intent  = task.get("intent","unknown")
    builder = INTENT_TO_BUILDER.get(intent)

    if builder == "stock":
        return await stock_query_builder(task, user_message)

    elif builder == "sales":
        if intent == "sales_write":
            items = task.get("items", [])
            if items:
                inv_data = await _fetch_inventory(items)
                enriched = _enrich_items(items, inv_data)

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

                task["items"] = enriched
                return await sales_query_builder(task, user_message, enriched_items=enriched)
        return await sales_query_builder(task, user_message)

    elif builder == "customer":
        return await customer_query_builder(task, user_message)

    elif builder == "finance":
        if intent == "finance_write":
            # Validate customer exists and get current balance before payment
            customer = (task.get("customer") or "").lower().strip()
            amount   = task.get("amount") or 0
            if customer and amount:
                check = await execute_plan({
                    "operation": "find", "collection": "customers",
                    "filter": {"name": customer}, "limit": 1
                })
                if check["ok"] and check["results"]:
                    doc            = check["results"][0]
                    current_credit = doc.get("total_credit", 0) or 0
                    remaining      = max(0, current_credit - amount)
                    # Inject real balance data so responder can show it
                    task["current_credit"] = current_credit
                    task["remaining"]      = remaining
                elif check["ok"] and not check["results"]:
                    return {
                        "operation":   "customer_not_found",
                        "customer":    customer,
                        "description": f"{customer} ka record nahi mila"
                    }
        return await finance_query_builder(task, user_message)

    else:
        return {"operation": "unsupported"}


async def query_builder_node(state):
    """
    Dispatch all tasks to specialized builders in parallel.
    Each builder only receives the schema it needs — no wasted tokens.
    """
    tasks        = state.get("tasks", [])
    user_message = state["user_message"]

    if not tasks:
        return {"query_plan": {"operation": "unsupported"}, "all_plans": []}

    # Run all specialized builders in parallel
    plans = await asyncio.gather(*[
        _build_plan_for_task(task, user_message)
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

        if plan.get("operation") == "unsupported":
            all_results.append({"intent": intent, "action": action,
                                 "result": "ERROR: Is operation ka support nahi hai."})
            continue

        if plan.get("operation") == "stock_error":
            # Hard stock validation failed — surface all errors clearly
            error_lines = plan.get("errors", ["Stock nahi hai."])
            all_results.append({"intent": intent, "action": action,
                                 "result": "STOCK_ERROR:" + " | ".join(error_lines)})
            continue

        if plan.get("operation") == "customer_not_found":
            customer = plan.get("customer","")
            all_results.append({"intent": intent, "action": action,
                                 "result": f"ERROR: {customer.title()} ka record nahi mila. Pehle customer add karein."})
            continue

        result = await execute_plan(plan)

        if not result["ok"]:
            all_results.append({"intent": intent, "action": action,
                                 "result": f"ERROR: {result['error']}"})
            continue

        results  = result.get("results", [])
        modified = result.get("modified", 0)
        inserted = result.get("inserted", 0)
        upserted = result.get("upserted", 0)

        if results:
            all_results.append({
                "intent": intent, "action": action,
                "result": results
            })
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

                all_results.append({
                    "intent": intent, "action": action,
                    "result": {"status": "OK", "stock_updated": stock_after}
                })
            else:
                # For finance_write, include real balance data computed before the plan ran
                tagged_task = next(
                    (t for t in (state.get("tasks") or [])
                     if t.get("intent") == intent and t.get("action") == action),
                    {}
                )
                if intent == "finance_write" and tagged_task.get("remaining") is not None:
                    customer  = (tagged_task.get("customer") or "").title()
                    amount    = tagged_task.get("amount", 0)
                    remaining = tagged_task.get("remaining", 0)
                    summary = (
                        f"PAYMENT_OK:customer={customer},"
                        f"amount={amount},"
                        f"remaining={remaining}"
                    )
                else:
                    summary = f"OK:{action}:" + ",".join(parts) if parts else f"OK:{action}"
                all_results.append({"intent": intent, "action": action, "result": summary})

    # Combine into single db_result string
    if len(all_results) == 1:
        r = all_results[0]["result"]
        db_result = json.dumps(r, ensure_ascii=False, default=str) if isinstance(r, list) else str(r)
    else:
        db_result = json.dumps(all_results, ensure_ascii=False, default=str)

    return {"db_result": db_result}


# ─────────────────────────────────────────────────────────────────────────────
#  NODE 4 — RESPONDER
# ─────────────────────────────────────────────────────────────────────────────

RESPONDER_PROMPT = """
You are HisabBot, a wholesale business assistant. Convert DB results to clean Roman Urdu.

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
- Empty result general        → "Koi record nahi mila."

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
12. CRITICAL — NEVER HALLUCINATE DATA: Only report what is in the DB result.
    If result is [] (empty array) → say "Koi record nahi mila."
    If result has no matching customer → say "X ka koi record nahi mila."
    NEVER make up payment amounts, balances, or names not present in the result.
13. Finance/balance queries with empty result:
    [] on customers → "Is naam ka customer nahi mila."
    [] on finance   → "Koi payment record nahi mila."

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
- If "negative": true for a product → show "0 units  [STOCK KHATAM - aur stock daalna hoga]"
- Cost: show if cost_price is not null, else write "nahi diya"
- No blank lines between products
- After table, list any negative/zero stock products as warnings:
  "⚠ Aata ka stock khatam ho gaya. Pehle ki sales se -200 deficit hai."

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
"""

async def responder_node(state):
    db_result = (state.get("db_result") or "").strip()

    if not db_result:
        return {"final_response": "Koi result nahi mila."}

    if db_result.startswith("ERROR:"):
        return {"final_response": db_result.replace("ERROR:","").strip()}

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
        amount    = params.get("amount","?")
        remaining = params.get("remaining","0")
        try:
            amt_fmt = f"Rs {float(amount):,.0f}"
            rem_fmt = f"Rs {float(remaining):,.0f}"
        except Exception:
            amt_fmt = f"Rs {amount}"
            rem_fmt = f"Rs {remaining}"
        if float(remaining) <= 0:
            rem_line = "Ab koi baaki nahi."
        else:
            rem_line = f"Remaining baaki: {rem_fmt}"
        return {"final_response": f"{customer} se {amt_fmt} payment mil gayi.\n{rem_line}"}

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
                f"DB results:\n{formatted}"
            )}
        ],
        model=MODEL,
        temperature=0.0
    )
    return {"final_response": res.choices[0].message.content}