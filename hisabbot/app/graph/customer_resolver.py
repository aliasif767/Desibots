"""
HisabBot — Customer Identity Resolver.

Handles the critical problem of multiple customers sharing the same name.
Resolves the correct customer document using name + address + phone.

Public API:
  resolve_and_pin_customer(task)       → used by dispatcher before any write/read
  replace_customer_ops_in_plan(...)    → used by executor to inject Python-built filter
  apply_pinned_filter(plan, filter)    → used by executor for finance/customer writes
"""

from .db_executor import execute_plan


# ─────────────────────────────────────────────────────────────────────────────
#  ADDRESS MATCHING
# ─────────────────────────────────────────────────────────────────────────────

def _address_match(addr1: str, addr2: str) -> bool:
    """
    Check if two address strings refer to the same place.
    Handles: exact match, substring ("lahore" vs "lahore, model town"),
    and >50% word overlap.
    """
    if not addr1 or not addr2:
        return False
    a1 = addr1.lower().strip()
    a2 = addr2.lower().strip()
    if a1 == a2:
        return True
    if a1 in a2 or a2 in a1:
        return True
    words1  = set(a1.split())
    words2  = set(a2.split())
    if not words1 or not words2:
        return False
    overlap = len(words1 & words2) / min(len(words1), len(words2))
    return overlap >= 0.5


# ─────────────────────────────────────────────────────────────────────────────
#  CORE IDENTITY RESOLUTION
# ─────────────────────────────────────────────────────────────────────────────

async def _resolve_customer_identity(
    name: str,
    address: str = None,
    phone: str = None,
) -> dict:
    """
    Resolve the correct customer document given name + optional address/phone.

    Strategy:
      1. Find all customers with this name.
      2. One found  → use it (update address if given and missing).
      3. Address given, multiple found → match by address.
         Match  → use  |  No match → create new  |  Multi-match → clarify.
      4. Phone given, multiple found → match by phone.
      5. Multiple, nothing to distinguish → ask for clarification.

    Returns one of:
      {"action": "use",    "customer": doc}
      {"action": "create", "name": n, "address": addr}
      {"action": "clarify","options": [...]}
      {"action": "new"}
    """
    name    = (name    or "").lower().strip()
    address = (address or "").lower().strip()
    phone   = (phone   or "").strip()

    result   = await execute_plan({
        "operation": "find", "collection": "customers",
        "filter": {"name": name}, "limit": 20,
    })
    existing = result.get("results", []) if result.get("ok") else []

    if not existing:
        return {"action": "create", "name": name, "address": address, "phone": phone}

    if len(existing) == 1:
        c             = existing[0]
        existing_addr = (c.get("address") or "").lower().strip()

        if not address:
            return {"action": "use", "customer": c}
        if existing_addr and _address_match(existing_addr, address):
            return {"action": "use", "customer": c}
        if existing_addr and not _address_match(existing_addr, address):
            return {"action": "create", "name": name, "address": address, "phone": phone}
        # Existing had no address — adopt the new one
        return {"action": "use", "customer": c, "update_address": address}

    # Multiple customers with this name
    if address:
        matches = [
            c for c in existing
            if _address_match((c.get("address") or "").lower(), address)
        ]
        if len(matches) == 1:
            return {"action": "use", "customer": matches[0]}
        if len(matches) == 0:
            return {"action": "create", "name": name, "address": address, "phone": phone}
        return {"action": "clarify", "options": matches}

    if phone:
        phone_matches = [c for c in existing if c.get("phone") == phone]
        if len(phone_matches) == 1:
            return {"action": "use", "customer": phone_matches[0]}

    return {"action": "clarify", "options": existing}


# ─────────────────────────────────────────────────────────────────────────────
#  PUBLIC: HIGH-LEVEL RESOLVER USED BY DISPATCHER
# ─────────────────────────────────────────────────────────────────────────────

async def resolve_and_pin_customer(task: dict) -> dict:
    """
    Resolve the correct customer for any operation (read or write).
    Uses address/qualifier from the task to disambiguate same-name customers.

    Returns one of:
      {"status": "ok",        "customer": doc, "filter": {...}, "name": ..., "address": ...}
      {"status": "clarify",   "response": str}
      {"status": "not_found", "response": str}
    """
    name      = (task.get("customer")  or "").lower().strip()
    address   = (task.get("address")   or "").lower().strip() or None
    phone     = (task.get("phone")     or "").strip()         or None
    qualifier = (task.get("qualifier") or "").lower().strip() or None

    effective_address = address or qualifier

    if not name:
        return {"status": "not_found", "response": "Customer ka naam nahi diya."}

    resolution = await _resolve_customer_identity(
        name=name, address=effective_address, phone=phone
    )
    action = resolution.get("action", "")

    # ── No customer found ────────────────────────────────────────────────────
    if action == "new" or (action == "create" and not resolution.get("customer")):
        hint = f" ({effective_address})" if effective_address else ""
        return {
            "status": "not_found",
            "response": (
                f"{name.title()}{hint} ka koi record nahi mila database mein.\n"
                f"Pehle customer add karein ya sahi naam check karein."
            ),
        }

    # ── Ambiguous — multiple customers match ─────────────────────────────────
    if action == "clarify":
        customers = resolution.get("customers") or resolution.get("options") or []
        if not customers:
            hint = f" ({effective_address})" if effective_address else ""
            return {"status": "not_found",
                    "response": f"{name.title()}{hint} ka koi record nahi mila."}
        options = []
        for i, c in enumerate(customers, 1):
            addr   = c.get("address") or "address nahi"
            ph     = c.get("phone")   or "number nahi"
            credit = c.get("total_credit", 0) or 0
            options.append(f"{i}. {name.title()} — {addr} | {ph} | Baaki: Rs {credit:,.0f}")
        return {
            "status": "clarify",
            "response": (
                f"'{name.title()}' naam ke multiple customers hain.\n"
                f"Kaunsa wala?\n\n" + "\n".join(options) + "\n\n"
                f"Address ya phone number ke saath batain, e.g.:\n"
                f"  '{name} islamabad wala ne 200000 diye'"
            ),
        }

    if action not in ("use", "create"):
        return {"status": "not_found",
                "response": f"{name.title()} ka record nahi mila."}

    # ── Matched customer ─────────────────────────────────────────────────────
    matched = resolution.get("customer")
    if not matched:
        hint = f" ({effective_address})" if effective_address else ""
        return {
            "status": "not_found",
            "response": (
                f"{name.title()}{hint} ka koi record nahi mila database mein.\n"
                f"Pehle customer add karein ya sahi naam check karein."
            ),
        }

    matched_addr  = matched.get("address") or effective_address
    pinned_filter = {"name": matched.get("name", name)}
    if matched_addr:
        pinned_filter["address"] = matched_addr

    return {
        "status":   "ok",
        "customer": matched,
        "filter":   pinned_filter,
        "name":     matched.get("name", name),
        "address":  matched_addr,
        "phone":    phone or matched.get("phone"),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  PLAN PATCHING — used by executor to inject Python-built filters
# ─────────────────────────────────────────────────────────────────────────────

def apply_pinned_filter(plan: dict, pinned_filter: dict) -> dict:
    """
    Overwrite the filter on every customers update_one/update_many in the plan
    with the Python-resolved address-based filter.
    Prevents the LLM from using filter:{name:X} which could match the wrong Ali.
    """
    def fix_op(op: dict) -> dict:
        if (op.get("collection") == "customers" and
                op.get("operation") in ("update_one", "update_many")):
            op = dict(op)
            op["filter"] = pinned_filter
        return op

    if "operations" in plan:
        return {**plan, "operations": [fix_op(op) for op in plan["operations"]]}
    return fix_op(plan)


def replace_customer_ops_in_plan(plan: dict, python_cust_upsert: dict) -> dict:
    """
    Replace LLM-generated customer update_one ops with the Python-built one.
    Preserves the $inc total_credit value from the LLM op.
    If no customer op exists in the plan, appends the Python one at the end.
    """
    def is_customer_update(op: dict) -> bool:
        return (op.get("collection") == "customers" and
                op.get("operation") in ("update_one", "update_many"))

    def merge_with_inc(base: dict, llm_op: dict) -> dict:
        merged = dict(base)
        llm_update = llm_op.get("update", {})
        if "$inc" in llm_update:
            merged_update = dict(merged.get("update", {}))
            merged_update["$inc"] = llm_update["$inc"]
            merged["update"] = merged_update
        return merged

    if "operations" in plan:
        new_ops           = []
        customer_replaced = False
        for op in plan["operations"]:
            if is_customer_update(op) and not customer_replaced:
                new_ops.append(merge_with_inc(python_cust_upsert, op))
                customer_replaced = True
            else:
                new_ops.append(op)
        if not customer_replaced:
            new_ops.append(python_cust_upsert)
        return {**plan, "operations": new_ops}

    if is_customer_update(plan):
        return merge_with_inc(python_cust_upsert, plan)

    return plan