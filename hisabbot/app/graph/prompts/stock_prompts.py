"""HisabBot — Stock query-builder prompts."""
from ..config import JSON_RULE, DATE_RULES,groq_client

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