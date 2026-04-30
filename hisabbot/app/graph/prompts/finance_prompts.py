"""HisabBot — Finance query-builder prompts."""
from ..config import JSON_RULE, DATE_RULES

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