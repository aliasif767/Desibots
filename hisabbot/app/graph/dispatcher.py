"""
HisabBot — Dispatcher Node (Node 2).

Routes each task to its specialised query builder, running them in parallel.
Also owns:
  - Product name normalisation (fuzzy match before any builder runs)
  - Bill/invoice plan construction (Python-built, bypasses LLM)
  - Stock/sales pre-validation (missing price, stock shortage)
  - Customer identity resolution for sales/customer/finance writes
"""

import asyncio
from .builders.stock_builder    import stock_query_builder
from .builders.sales_builder    import (
    sales_query_builder, fetch_inventory, enrich_items,
    _fuzzy_match_product, _get_all_inventory_products,
)
from .builders.customer_builder import customer_query_builder
from .builders.finance_builder  import finance_query_builder
from .customer_resolver import (
    resolve_and_pin_customer,
    _resolve_customer_identity,
)


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


# ─────────────────────────────────────────────────────────────────────────────
#  INTERNAL: Build plan for a single task
# ─────────────────────────────────────────────────────────────────────────────

async def _build_plan_for_task(task: dict, user_message: str) -> dict:
    """Select the right builder for a task and return a MongoDB execution plan."""
    intent  = task.get("intent", "unknown")
    builder = INTENT_TO_BUILDER.get(intent)

    # ── STOCK ────────────────────────────────────────────────────────────────
    if builder == "stock":
        if intent == "stock_write":
            items = task.get("items", [])
            if items:
                missing = [
                    (i.get("product") or "?").title()
                    for i in items if not i.get("cost_price")
                ]
                if missing:
                    has_price = [i for i in items if i.get("cost_price")]
                    no_price  = [(i.get("product") or "?").title() for i in items if not i.get("cost_price")]
                    if has_price and no_price:
                        # Add the priced items, ask for the rest
                        plan = await stock_query_builder({**task, "items": has_price}, user_message)
                        plan["__stock_missing_price__"] = no_price
                        return plan
                    return {
                        "operation":   "missing_cost_price",
                        "products":    missing,
                        "description": f"cost price missing for: {', '.join(missing)}",
                    }
        return await stock_query_builder(task, user_message)

    # ── SALES ────────────────────────────────────────────────────────────────
    elif builder == "sales":

        # ── Bill/invoice — Python-built plan, no LLM ────────────────────────
        if intent == "sales_read":
            action_lower  = (task.get("action") or "").lower()
            bill_keywords = ("bill", "invoice", "hisab", "kharidari")
            if any(kw in action_lower for kw in bill_keywords) and task.get("customer"):
                cust_name = task.get("customer", "").lower().strip()
                res = await resolve_and_pin_customer(task)
                if res["status"] == "clarify":
                    return {"operation": "customer_ambiguous_payment", "response": res["response"]}
                if res["status"] == "not_found":
                    return {"operation": "customer_not_found",
                            "customer": cust_name, "description": res["response"]}
                bill_filter = {"customer": res.get("name", cust_name)}
                if res.get("address"):
                    bill_filter["customer_address"] = res["address"]
                return {
                    "operation":  "aggregate",
                    "collection": "sales",
                    "pipeline": [
                        {"$match": bill_filter},
                        {"$project": {
                            "date": 1, "product": 1, "qty": 1,
                            "selling_price": 1, "sale_total": 1,
                            "customer_address": 1,
                        }},
                        {"$sort": {"date": -1}},
                    ],
                }

        # ── Sales write — enrich, validate, resolve customer ─────────────────
        if intent == "sales_write":
            items = task.get("items", [])
            if items:
                inv_data = await fetch_inventory(items)
                enriched = enrich_items(items, inv_data)

                # Missing selling price?
                missing_price = [
                    item.get("product", "").title()
                    for item in enriched if not item.get("selling_price")
                ]
                if missing_price:
                    return {
                        "operation":   "missing_price",
                        "products":    missing_price,
                        "description": f"selling price missing for: {', '.join(missing_price)}",
                    }

                # Hard stock check
                errors = []
                for item in enriched:
                    product   = item.get("product", "")
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
                    return {"operation": "stock_error", "errors": errors,
                            "description": "insufficient stock"}

                # Customer identity resolution
                cust_name  = (task.get("customer") or "").lower().strip()
                cust_addr  = (task.get("address")  or "").lower().strip()
                cust_phone = (task.get("phone")    or "").strip()

                if cust_name:
                    resolution = await _resolve_customer_identity(
                        name=cust_name, address=cust_addr, phone=cust_phone
                    )

                    if resolution["action"] == "clarify":
                        options = [
                            f"{i}. {cust_name.title()} — "
                            f"{c.get('address') or 'address nahi'} | "
                            f"{c.get('phone') or 'number nahi'} | "
                            f"Baaki: Rs {c.get('total_credit', 0) or 0:,.0f}"
                            for i, c in enumerate(resolution["options"], 1)
                        ]
                        return {
                            "operation":   "customer_ambiguous",
                            "customer":    cust_name,
                            "qualifier":   cust_addr or "?",
                            "options":     options,
                            "description": "multiple customers with same name",
                        }

                    elif resolution["action"] == "create":
                        new_addr  = cust_addr or None
                        new_phone = cust_phone or None
                        cust_filter = {"name": cust_name}
                        if new_addr:
                            cust_filter["address"] = new_addr
                        task["_python_customer_upsert"] = {
                            "operation":  "update_one",
                            "collection": "customers",
                            "filter":     cust_filter,
                            "update": {
                                "$set":         {"last_seen": "__TODAY_START__"},
                                "$setOnInsert": {
                                    "name":      cust_name,
                                    "address":   new_addr,
                                    "phone":     new_phone,
                                    "join_date": "__TODAY_START__",
                                },
                            },
                            "upsert": True,
                        }
                        task["address"] = new_addr
                        task["phone"]   = new_phone

                    elif resolution["action"] == "use":
                        matched      = resolution["customer"]
                        matched_addr = matched.get("address") or cust_addr
                        cust_filter  = {"name": matched.get("name", cust_name)}
                        if matched_addr:
                            cust_filter["address"] = matched_addr
                        task["customer"] = matched.get("name", cust_name)
                        task["phone"]    = cust_phone or matched.get("phone")
                        task["address"]  = matched_addr
                        task["_python_customer_upsert"] = {
                            "operation":  "update_one",
                            "collection": "customers",
                            "filter":     cust_filter,
                            "update": {
                                "$set":         {"last_seen": "__TODAY_START__"},
                                "$setOnInsert": {
                                    "name":      matched.get("name", cust_name),
                                    "address":   matched_addr,
                                    "phone":     cust_phone or matched.get("phone"),
                                    "join_date": "__TODAY_START__",
                                },
                            },
                            "upsert": True,
                        }
                        if resolution.get("update_address") and not matched.get("address"):
                            task["_python_customer_upsert"]["update"]["$set"]["address"] = cust_addr

                task["items"] = enriched
                return await sales_query_builder(task, user_message, enriched_items=enriched)

        return await sales_query_builder(task, user_message)

    # ── CUSTOMER ─────────────────────────────────────────────────────────────
    elif builder == "customer":
        if intent == "customer_read" and task.get("customer"):
            res = await resolve_and_pin_customer(task)
            if res["status"] == "clarify":
                return {"operation": "customer_ambiguous_payment", "response": res["response"]}
            if res["status"] == "not_found":
                return {"operation": "customer_not_found",
                        "customer": task.get("customer", "?"),
                        "description": res["response"]}
            if res["status"] == "ok":
                task["customer"]       = res["name"]
                task["_pinned_filter"] = res["filter"]
                task["address"]        = res["address"]

        elif intent == "customer_write" and task.get("customer"):
            res = await resolve_and_pin_customer(task)
            if res["status"] == "clarify":
                return {"operation": "customer_ambiguous_payment", "response": res["response"]}
            if res["status"] == "ok":
                task["_pinned_filter"] = res["filter"]

        return await customer_query_builder(task, user_message)

    # ── FINANCE ──────────────────────────────────────────────────────────────
    elif builder == "finance":
        if intent == "finance_write":
            amount = task.get("amount") or 0
            if task.get("customer") and amount:
                res = await resolve_and_pin_customer(task)
                if res["status"] == "clarify":
                    return {"operation": "customer_ambiguous_payment", "response": res["response"]}
                if res["status"] == "not_found":
                    return {"operation": "customer_not_found",
                            "customer": task.get("customer", "?"),
                            "description": res["response"]}
                doc            = res["customer"]
                current_credit = doc.get("total_credit", 0) or 0
                task["current_credit"] = current_credit
                task["remaining"]      = max(0, current_credit - amount)
                task["customer"]       = res["name"]
                task["_pinned_filter"] = res["filter"]
                task["address"]        = res["address"]
                task["phone"]          = res["phone"]

        return await finance_query_builder(task, user_message)

    return {"operation": "unsupported"}


# ─────────────────────────────────────────────────────────────────────────────
#  DISPATCHER NODE (LangGraph Node 2)
# ─────────────────────────────────────────────────────────────────────────────

async def query_builder_node(state: dict) -> dict:
    """
    Dispatch all tasks to their specialised builders in parallel.
    Injects conversation history so follow-up corrections work correctly.
    Normalises product names via fuzzy matching before any builder runs.
    """
    tasks        = state.get("tasks", [])
    user_message = state["user_message"]
    history      = state.get("conversation_history") or []

    # Build history context string (last 4 messages = 2 exchanges)
    prior = history[-4:] if len(history) > 4 else history
    if prior:
        history_lines = [
            f"{'User' if h['role'] == 'user' else 'Agent'}: {h['content']}"
            for h in prior
        ]
        user_message_with_context = (
            "=== RECENT CONVERSATION (for context) ===\n" +
            "\n".join(history_lines) +
            "\n=== END ===\n\n" +
            f"Current message: {user_message}"
        )
    else:
        user_message_with_context = user_message

    if not tasks:
        return {"query_plan": {"operation": "unsupported"}, "all_plans": []}

    # ── Product name normalisation — runs ONCE for all tasks ─────────────────
    known_products  = await _get_all_inventory_products()
    all_corrections = {}

    if known_products:
        for task in tasks:
            fixed_items = []
            for item in (task.get("items") or []):
                typed = (item.get("product") or "").lower().strip()
                if not typed or typed in known_products:
                    fixed_items.append(item)
                    continue
                matched = _fuzzy_match_product(typed, known_products)
                if matched and matched != typed:
                    all_corrections[typed] = matched
                    item = {**item, "product": matched}
                fixed_items.append(item)
            task["items"] = fixed_items

            # Fix single product field used in read queries
            if task.get("product"):
                typed = task["product"].lower().strip()
                if typed not in known_products:
                    matched = _fuzzy_match_product(typed, known_products)
                    if matched and matched != typed:
                        all_corrections[typed] = matched
                        task["product"] = matched

        if all_corrections:
            tasks[0]["_product_corrections"] = {
                **tasks[0].get("_product_corrections", {}),
                **all_corrections,
            }
            corr_note = "NOTE: These product spellings were auto-corrected: " + \
                ", ".join(f"'{k}' → '{v}'" for k, v in all_corrections.items())
            user_message_with_context = corr_note + "\n" + user_message_with_context

    # ── Run all builders in parallel ─────────────────────────────────────────
    plans = await asyncio.gather(*[
        _build_plan_for_task(task, user_message_with_context)
        for task in tasks
    ])

    tagged_plans = [
        {"intent": task.get("intent", ""), "action": task.get("action", ""), "plan": plan}
        for task, plan in zip(tasks, plans)
    ]

    return {
        "query_plan": plans[0] if plans else {"operation": "unsupported"},
        "all_plans":  tagged_plans,
    }