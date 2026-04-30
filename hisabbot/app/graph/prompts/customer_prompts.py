"""HisabBot — Customer query-builder prompts."""
from ..config import JSON_RULE, DATE_RULES,groq_client

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