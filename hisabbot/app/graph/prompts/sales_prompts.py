"""HisabBot — Sales query-builder prompts."""
from ..config import JSON_RULE, DATE_RULES,groq_client

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
        "$inc": {{"total_credit": <calculated single number sum of all sale_totals>}},
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
DO NOT use math expressions (e.g. 100+200) in the JSON; provide the final calculated number.
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