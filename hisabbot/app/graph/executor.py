"""
HisabBot — Query Executor Node (Node 3).

Executes every MongoDB plan produced by the dispatcher.
Handles special plan types (missing_price, stock_error, customer_ambiguous, etc.)
without touching the LLM, then assembles a single db_result string for the responder.
"""

import json
import logging

from .db_executor import execute_plan
from .customer_resolver import apply_pinned_filter, replace_customer_ops_in_plan

logger = logging.getLogger("hisabbot")

READ_INTENTS    = {"stock_read", "sales_read", "customer_read", "finance_read"}
SPECIAL_PREFIXES = (
    "EMPTY_RESULT:", "ERROR:", "PAYMENT_OK:", "STOCK_ERROR:",
    "MISSING_PRICE:", "MISSING_COST_PRICE:", "CUSTOMER_AMBIGUOUS:", "STOCK_KHATAM:",
)


# ─────────────────────────────────────────────────────────────────────────────
#  INTERNAL: Handle special plan types before hitting the DB
# ─────────────────────────────────────────────────────────────────────────────

def _handle_special_plan(plan: dict, intent: str, action: str) -> str | None:
    """
    Check if the plan is a sentinel (non-DB) plan type.
    Returns a result string if handled, or None if it should go to the DB.
    """
    op = plan.get("operation", "")

    if op == "unsupported":
        return "ERROR: Is operation ka support nahi hai."

    if op == "missing_price":
        return "MISSING_PRICE:" + ", ".join(plan.get("products", []))

    if op == "missing_cost_price":
        return "MISSING_COST_PRICE:" + ", ".join(plan.get("products", []))

    if op == "stock_error":
        return "STOCK_ERROR:" + " | ".join(plan.get("errors", ["Stock nahi hai."]))

    if op == "customer_ambiguous_payment":
        return f"CUSTOMER_AMBIGUOUS:{plan.get('response', '')}"

    if op == "customer_ambiguous":
        name      = (plan.get("customer", "") or "?").title()
        opts_text = "\n".join(plan.get("options", []))
        return f"CUSTOMER_AMBIGUOUS:{name}|{opts_text}"

    if op == "customer_not_found":
        customer = plan.get("customer", "")
        return f"ERROR: {customer.title()} ka record nahi mila. Pehle customer add karein."

    return None   # normal DB plan


# ─────────────────────────────────────────────────────────────────────────────
#  INTERNAL: Post-execution stock fetch for stock_write confirmation
# ─────────────────────────────────────────────────────────────────────────────

async def _fetch_stock_after_update(plan: dict) -> list:
    """After a stock_write, re-fetch updated quantities for each product."""
    products_to_fetch = []
    for op in plan.get("operations", [plan]):
        f_val = op.get("filter", {})
        if f_val.get("product") and op.get("collection") == "inventory":
            products_to_fetch.append(f_val["product"])

    stock_after = []
    for product in set(products_to_fetch):
        res = await execute_plan({
            "operation": "find", "collection": "inventory",
            "filter": {"product": product}, "limit": 1,
        })
        if res["ok"] and res["results"]:
            doc     = res["results"][0]
            raw_qty = doc.get("qty", 0)
            stock_after.append({
                "product":    doc.get("product", product),
                "qty":        max(0, raw_qty) if isinstance(raw_qty, (int, float)) else 0,
                "cost_price": doc.get("cost_price"),
                "negative":   raw_qty < 0,
            })
    return stock_after


# ─────────────────────────────────────────────────────────────────────────────
#  INTERNAL: Serialise a single all_results list → db_result string
# ─────────────────────────────────────────────────────────────────────────────

def _serialise_results(all_results: list) -> str:
    """Collapse the list of per-task results into one db_result string."""
    if len(all_results) == 1:
        entry    = all_results[0]
        r        = entry["result"]
        intent_e = entry.get("intent", "")
        action_e = entry.get("action", "")

        if isinstance(r, str) and any(r.startswith(p) for p in SPECIAL_PREFIXES):
            return r
        if intent_e in READ_INTENTS and (r == [] or r == "" or r is None):
            return f"EMPTY_RESULT:{action_e}"
        if isinstance(r, list) and len(r) == 0 and intent_e in READ_INTENTS:
            return f"EMPTY_RESULT:{action_e}"
        if isinstance(r, list):
            return json.dumps(r, ensure_ascii=False, default=str)
        if isinstance(r, dict):
            r = dict(r)
            smp  = entry.get("stock_missing_price", [])
            corr = entry.get("product_corrections", {})
            if smp:  r["missing_price_products"] = smp
            if corr: r["product_corrections"]     = corr
            return json.dumps(r, ensure_ascii=False, default=str)
        return str(r)

    # Multi-task — tag empty reads explicitly
    tagged = []
    for entry in all_results:
        r_val    = entry.get("result")
        intent_e = entry.get("intent", "")
        action_e = entry.get("action", "")
        if intent_e in READ_INTENTS and (r_val == [] or r_val == "" or r_val is None):
            entry = {**entry, "result": f"EMPTY_RESULT:{action_e}"}
        tagged.append(entry)
    return json.dumps(tagged, ensure_ascii=False, default=str)


# ─────────────────────────────────────────────────────────────────────────────
#  EXECUTOR NODE (LangGraph Node 3)
# ─────────────────────────────────────────────────────────────────────────────

async def query_executor_node(state: dict) -> dict:
    """
    Execute every plan from the dispatcher sequentially.
    Patches customer filters, extracts corrections, and assembles db_result.
    """
    all_plans = state.get("all_plans") or []
    if not all_plans:
        plan      = state.get("query_plan", {})
        all_plans = [{"intent": state.get("intent", ""), "action": state.get("action", ""), "plan": plan}]

    all_results = []

    for tagged in all_plans:
        plan   = tagged.get("plan", {})
        intent = tagged.get("intent", "")
        action = tagged.get("action", "")

        logger.info(f"EXECUTING [{intent}] {action}: {json.dumps(plan, default=str)[:200]}")

        # ── Handle sentinel plans (no DB call needed) ─────────────────────
        special = _handle_special_plan(plan, intent, action)
        if special is not None:
            all_results.append({"intent": intent, "action": action, "result": special})
            continue

        # ── Collect metadata before mutating the plan ─────────────────────
        product_corrections = {}
        for t in (state.get("tasks") or []):
            if t.get("_product_corrections"):
                product_corrections.update(t["_product_corrections"])

        stock_missing_price = plan.pop("__stock_missing_price__", [])

        # Inject Python-built customer upsert (sales_write)
        python_cust_upsert = plan.pop("_python_customer_upsert", None)
        if python_cust_upsert and intent == "sales_write":
            plan = replace_customer_ops_in_plan(plan, python_cust_upsert)

        # Inject pinned address filter (finance_write, customer_write)
        pinned_filter = next(
            (t["_pinned_filter"] for t in (state.get("tasks") or [])
             if t.get("intent") == intent and t.get("_pinned_filter")),
            None,
        )
        if pinned_filter and intent in ("finance_write", "customer_write"):
            plan = apply_pinned_filter(plan, pinned_filter)

        # ── Execute against MongoDB ───────────────────────────────────────
        result = await execute_plan(plan)

        if not result["ok"]:
            all_results.append({"intent": intent, "action": action,
                                 "result": f"ERROR: {result['error']}"})
            continue

        results  = result.get("results", [])
        modified = result.get("modified", 0)
        inserted = result.get("inserted", 0)
        upserted = result.get("upserted", 0)

        # Empty read → tag immediately, never pass to LLM
        if results == [] and intent in READ_INTENTS:
            all_results.append({"intent": intent, "action": action,
                                 "result": f"EMPTY_RESULT:{action}"})
            continue

        if results:
            entry = {"intent": intent, "action": action, "result": results}
            if product_corrections:
                entry["product_corrections"] = product_corrections
            all_results.append(entry)
            continue

        # Write result — build a summary string
        parts = []
        if inserted: parts.append(f"inserted:{inserted}")
        if modified: parts.append(f"modified:{modified}")
        if upserted: parts.append(f"new_customer_registered:{upserted}")

        if intent == "stock_write":
            stock_after = await _fetch_stock_after_update(plan)
            entry = {"intent": intent, "action": action,
                     "result": {"status": "OK", "stock_updated": stock_after}}
            if stock_missing_price:
                entry["stock_missing_price"] = stock_missing_price
            all_results.append(entry)

        elif intent == "finance_write":
            tagged_task = next(
                (t for t in (state.get("tasks") or [])
                 if t.get("intent") == intent and t.get("action") == action),
                {},
            )
            if tagged_task.get("remaining") is not None:
                customer  = (tagged_task.get("customer") or "").title()
                address   = (tagged_task.get("address")  or "").strip()
                amount    = tagged_task.get("amount", 0)
                remaining = tagged_task.get("remaining", 0)
                summary   = (
                    f"PAYMENT_OK:customer={customer},"
                    f"address={address},"
                    f"amount={amount},"
                    f"remaining={remaining}"
                )
            else:
                summary = f"OK:{action}:" + ",".join(parts) if parts else f"OK:{action}"
            all_results.append({"intent": intent, "action": action, "result": summary})

        elif intent == "sales_write":
            tagged_task = next(
                (t for t in (state.get("tasks") or [])
                 if t.get("intent") == intent and t.get("action") == action),
                {},
            )
            items    = tagged_task.get("items", [])
            customer = (tagged_task.get("customer") or "").title()

            entry = {"intent": intent, "action": action,
                     "result": {"status": "OK", "sales_recorded": {"customer": customer, "items": items}}}
            if upserted:
                entry["result"]["new_customer_registered"] = True
            if product_corrections:
                entry["product_corrections"] = product_corrections
            all_results.append(entry)

        else:
            summary = f"OK:{action}:" + ",".join(parts) if parts else f"OK:{action}"
            all_results.append({"intent": intent, "action": action, "result": summary})

    return {"db_result": _serialise_results(all_results)}