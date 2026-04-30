"""
HisabBot — Sales query builder + inventory enrichment helpers.

Responsibilities:
  - sales_query_builder : generates MongoDB plans for sales_read / sales_write
  - _fetch_inventory    : pre-fetches inventory qty + cost_price for items
  - _enrich_items       : calculates sale_total, cost_total, profit from real DB data
  - Fuzzy product-name matching (levenshtein + phonetic Urdu)
"""

import json
import re as _re
from ..config import groq_client, MODEL
from ..prompts.sales_prompts import SALES_WRITE_PROMPT, SALES_READ_PROMPT
from ..db_executor import execute_plan


# ─────────────────────────────────────────────────────────────────────────────
#  FUZZY PRODUCT NAME MATCHING
# ─────────────────────────────────────────────────────────────────────────────

_inventory_cache: list = []


def _levenshtein(a: str, b: str) -> int:
    """Compute edit distance between two strings."""
    if a == b:   return 0
    if not a:    return len(b)
    if not b:    return len(a)
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev  = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            temp  = dp[j]
            dp[j] = prev if a[i-1] == b[j-1] else 1 + min(prev, dp[j], dp[j-1])
            prev  = temp
    return dp[n]


def _phonetic_urdu(s: str) -> str:
    """
    Collapse common Urdu Roman spelling variants to a canonical consonant skeleton.
    Examples: cheeni/chini → "chni", daal/dal → "dl", sooji/suji → "sj"
    """
    s = s.lower().strip()
    s = s.replace("ph", "f")
    s = s.replace("kh", "k")
    s = s.replace("ch", "c")
    s = s.replace("sh", "x")
    s = s.replace("ee", "i")
    s = s.replace("aa", "a")
    s = s.replace("oo", "u")
    s = s.replace("ae", "a")
    s = _re.sub(r'[aeiou]', '', s)
    s = _re.sub(r'(.)+', r'', s)
    return s


def _fuzzy_match_product(typed: str, known_products: list, threshold: float = 0.72) -> str | None:
    """
    Find the closest inventory product name using:
      1. Exact match
      2. Levenshtein edit distance (typos)
      3. Phonetic consonant-skeleton (vowel substitutions)
    """
    typed = typed.lower().strip()
    if not typed or not known_products:
        return None
    if typed in known_products:
        return typed

    best_product = None
    best_score   = 0.0
    typed_phonetic = _phonetic_urdu(typed)

    for prod in known_products:
        prod_l = prod.lower()
        max_len = max(len(typed), len(prod_l))
        if max_len == 0:
            continue

        dist = _levenshtein(typed, prod_l)
        sim  = 1.0 - dist / max_len

        if prod_l.startswith(typed) or typed.startswith(prod_l):
            sim = max(sim, 0.85)
        if prod_l in typed or typed in prod_l:
            sim = max(sim, 0.80)

        prod_phonetic = _phonetic_urdu(prod_l)
        if typed_phonetic and prod_phonetic:
            ph_max = max(len(typed_phonetic), len(prod_phonetic))
            if ph_max > 0:
                ph_dist = _levenshtein(typed_phonetic, prod_phonetic)
                ph_sim  = 1.0 - ph_dist / ph_max
                if ph_sim >= 0.80:
                    sim = max(sim, 0.80)
                elif ph_sim >= 0.65:
                    sim = max(sim, sim + 0.05)

        if sim > best_score:
            best_score   = sim
            best_product = prod

    return best_product if best_score >= threshold else None


async def _get_all_inventory_products() -> list:
    """Fetch all product names from inventory (used for fuzzy matching)."""
    result = await execute_plan({
        "operation": "find", "collection": "inventory",
        "filter": {}, "limit": 200,
    })
    if result["ok"] and result["results"]:
        return [doc.get("product", "").lower() for doc in result["results"] if doc.get("product")]
    return []


async def _normalize_product_names(items: list) -> tuple[list, dict]:
    """
    Check each item's product name against inventory (fuzzy).
    If a close match exists, replace with the canonical DB name.

    Returns: (normalized_items, corrections_dict)
    corrections_dict example: {"chenni": "cheeni"}
    """
    known = await _get_all_inventory_products()
    if not known:
        return items, {}

    corrections = {}
    normalized  = []
    for item in items:
        typed = (item.get("product") or "").lower().strip()
        if not typed:
            normalized.append(item)
            continue
        if typed in known:
            normalized.append(item)
            continue

        matched = _fuzzy_match_product(typed, known)
        if matched and matched != typed:
            corrections[typed] = matched
            item = dict(item)
            item["product"] = matched
        normalized.append(item)

    return normalized, corrections


# ─────────────────────────────────────────────────────────────────────────────
#  INVENTORY PRE-FETCH & ITEM ENRICHMENT
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_inventory(items: list) -> dict:
    """Fetch qty and cost_price for each item from inventory."""
    inventory = {}
    for item in items:
        product = (item.get("product") or "").lower().strip()
        if not product:
            continue
        result = await execute_plan({
            "operation": "find", "collection": "inventory",
            "filter": {"product": product}, "limit": 1,
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


def enrich_items(items: list, inv_data: dict) -> list:
    """
    Calculate sale_total, cost_total, profit for each item using real DB cost prices.
    Attaches available_qty so stock validation can run without a second DB call.
    """
    enriched = []
    for item in items:
        product    = (item.get("product") or "").lower().strip()
        inv        = inv_data.get(product, {})
        real_cp    = inv.get("cost_price")
        avail      = inv.get("qty", 0)
        sp         = item.get("selling_price")
        qty        = item.get("qty") or 0

        sale_total = round(sp * qty, 2)                         if sp                        else None
        cost_total = round(real_cp * qty, 2)                    if real_cp                   else None
        profit     = round(sale_total - cost_total, 2)          if sale_total and cost_total else None

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
#  SALES QUERY BUILDER
# ─────────────────────────────────────────────────────────────────────────────

async def sales_query_builder(
    task: dict,
    user_message: str,
    enriched_items: list = None,
) -> dict:
    intent = task.get("intent", "")
    prompt = SALES_WRITE_PROMPT if intent == "sales_write" else SALES_READ_PROMPT

    context_parts = [
        f"User message: \"{user_message}\"",
        f"Action: {task.get('action', '')}",
        f"Customer: {task.get('customer', '')}",
        f"Phone: {task.get('phone', '') or 'null'}",
        f"Address: {task.get('address', '') or 'null'}",
    ]

    customer_filter = task.get("_customer_filter")
    if customer_filter:
        context_parts.append(
            f"_customer_filter (use this in customer update filter): {json.dumps(customer_filter)}"
        )

    if task.get("_new_customer"):
        context_parts.append(
            "NOTE: This is a NEW customer — use $setOnInsert to store name, address, phone, join_date."
        )

    if enriched_items:
        context_parts.append("=== ENRICHED ITEMS — use these EXACT numbers ===")
        for it in enriched_items:
            context_parts.append(f"  {json.dumps(it)}")
    else:
        context_parts.append(f"Items: {json.dumps(task.get('items', []))}")

    context_parts.append("Generate the MongoDB plan.")
    context = "\n".join(context_parts)

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