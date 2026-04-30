"""
HisabBot — Customer query builder.
Generates MongoDB plans for customer_read and customer_write intents.
"""

import json
from ..config import groq_client, MODEL
from ..prompts.customer_prompts import CUSTOMER_WRITE_PROMPT, CUSTOMER_READ_PROMPT


async def customer_query_builder(task: dict, user_message: str) -> dict:
    intent = task.get("intent", "")
    prompt = CUSTOMER_WRITE_PROMPT if intent == "customer_write" else CUSTOMER_READ_PROMPT

    context = (
        f"User message: \"{user_message}\"\n"
        f"Action: {task.get('action', '')}\n"
        f"Customer: {task.get('customer', '')} "
        f"| Phone: {task.get('phone', '')} "
        f"| Address: {task.get('address', '')}\n"
        f"Generate the MongoDB plan."
    )
    res = await groq_client.chat.completions.create(
        messages=[{"role": "system", "content": prompt},
                  {"role": "user",   "content": context}],
        model=MODEL,
        response_format={"type": "json_object"},
        temperature=0.0,
    )
    try:
        return json.loads(res.choices[0].message.content)
    except Exception:
        return {"operation": "unsupported"}