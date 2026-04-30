"""
HisabBot — Stock query builder.
Generates MongoDB plans for stock_read and stock_write intents.
"""

import json
from ..config import groq_client, MODEL
from ..prompts.stock_prompts import STOCK_WRITE_PROMPT, STOCK_READ_PROMPT


async def stock_query_builder(task: dict, user_message: str) -> dict:
    intent = task.get("intent", "")
    prompt = STOCK_WRITE_PROMPT if intent == "stock_write" else STOCK_READ_PROMPT

    items   = task.get("items", [])
    context = (
        f"User message: \"{user_message}\"\n"
        f"Action: {task.get('action', '')}\n"
        f"Items: {json.dumps(items)}\n"
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