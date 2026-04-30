"""
HisabBot — Finance query builder.
Generates MongoDB plans for finance_read and finance_write intents.
"""

import json
from ..config import groq_client, MODEL
from ..prompts.finance_prompts import FINANCE_WRITE_PROMPT, FINANCE_READ_PROMPT


async def finance_query_builder(task: dict, user_message: str) -> dict:
    intent = task.get("intent", "")
    prompt = FINANCE_WRITE_PROMPT if intent == "finance_write" else FINANCE_READ_PROMPT

    pinned  = task.get("_pinned_filter")
    context = (
        f"User message: \"{user_message}\"\n"
        f"Action: {task.get('action', '')}\n"
        f"Customer: {task.get('customer', '')} | Amount: {task.get('amount', '')}\n"
        f"Address: {task.get('address', '') or 'null'}\n"
        + (
            f"_pinned_filter (use EXACTLY this in customer update filter): {json.dumps(pinned)}\n"
            if pinned else ""
        )
        + "Generate the MongoDB plan."
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