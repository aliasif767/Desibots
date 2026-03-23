"""
HisabBot Dynamic MongoDB Executor — v5 (fully dynamic, no hardcoded queries)

Handles ALL operations: reads AND writes.
The LLM generates every query. This module validates and executes safely.

Write operations allowed:
  - insert_one:  single document insert
  - update_one:  update with filter + update doc
  - update_many: update multiple documents

Read operations allowed:
  - find, aggregate, count

Safety rules:
  - Allowed collections only
  - Write ops require explicit "operation" field — no silent mutations
  - Result size capped at 200
  - Dangerous operators ($where, $function, system commands) always blocked
"""

from datetime import datetime, timezone, timedelta
from bson import ObjectId
from app.db.session import db

ALLOWED_COLLECTIONS = {"inventory", "sales", "customers", "finance"}

# Operators that should NEVER appear anywhere (injection / js execution)
ALWAYS_BLOCKED = {
    "$where", "$function", "$accumulator",
    "dropCollection", "drop", "dropIndex", "createIndex",
    "deleteOne", "deleteMany",   # deletes blocked — dealer should never lose records
    "insertMany",                # use insert_one only, one at a time
}

# Write operators only allowed inside update_one / update_many "update" field
WRITE_OPERATORS = {
    "$set", "$unset", "$inc", "$push", "$pull", "$pop",
    "$addToSet", "$rename", "$currentDate", "$mul", "$setOnInsert"
}


def _month_start(now, months_back: int) -> datetime:
    """Return the 1st day of the month that is months_back months before now."""
    month = now.month - months_back
    year  = now.year
    while month <= 0:
        month += 12
        year  -= 1
    return datetime(year, month, 1, 0, 0, 0, tzinfo=timezone.utc)


def _month_end(now, months_back: int) -> datetime:
    """Return the last moment of the month that is months_back months before now."""
    start = _month_start(now, months_back)
    # First day of NEXT month minus 1 microsecond
    if start.month == 12:
        next_month = datetime(start.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        next_month = datetime(start.year, start.month + 1, 1, tzinfo=timezone.utc)
    return next_month - timedelta(microseconds=1)


def _resolve_dates(obj):
    """
    Replace date placeholder strings with real datetime objects.

    Current period placeholders:
      __TODAY_START__          → today 00:00 UTC
      __TODAY_END__            → today 23:59:59 UTC
      __WEEK_START__           → 7 days ago 00:00 UTC
      __MONTH_START__          → 1st of current month 00:00 UTC
      __MONTH_END__            → last moment of current month
      __YEAR_START__           → 1st Jan current year 00:00 UTC

    Past period placeholders (exact calendar months, not just N*30 days):
      __PREV_MONTH_START__     → 1st of last month 00:00 UTC
      __PREV_MONTH_END__       → last moment of last month
      __MONTHS_AGO_N_START__   → 1st of month N months ago  (e.g. __MONTHS_AGO_2_START__)
      __MONTHS_AGO_N_END__     → last moment of month N months ago

    General day offset:
      __DAYS_AGO_N__           → exactly N days ago 00:00 UTC  (e.g. __DAYS_AGO_30__)
    """
    now = datetime.now(timezone.utc)
    if isinstance(obj, str):
        s = obj.strip()

        # ── Current period ────────────────────────────────────────────────────
        if s == "__TODAY_START__":
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        if s == "__TODAY_END__":
            return now.replace(hour=23, minute=59, second=59, microsecond=999999)
        if s == "__WEEK_START__":
            return (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        if s == "__MONTH_START__":
            return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if s == "__MONTH_END__":
            return _month_end(now, 0)
        if s == "__YEAR_START__":
            return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        if s == "__YEAR_END__":
            return now.replace(month=12, day=31, hour=23, minute=59, second=59, microsecond=999999)
        if s == "__PREV_YEAR_START__":
            return datetime(now.year - 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        if s == "__PREV_YEAR_END__":
            return datetime(now.year - 1, 12, 31, 23, 59, 59, 999999, tzinfo=timezone.utc)

        # ── Previous exact calendar month ─────────────────────────────────────
        if s == "__PREV_MONTH_START__":
            return _month_start(now, 1)
        if s == "__PREV_MONTH_END__":
            return _month_end(now, 1)

        # ── N months ago — exact calendar month boundaries ────────────────────
        if s.startswith("__MONTHS_AGO_") and s.endswith("_START__"):
            try:
                n = int(s[13:-8])   # __MONTHS_AGO_2_START__ → 2
                return _month_start(now, n)
            except ValueError: pass
        if s.startswith("__MONTHS_AGO_") and s.endswith("_END__"):
            try:
                n = int(s[13:-6])   # __MONTHS_AGO_2_END__ → 2
                return _month_end(now, n)
            except ValueError: pass

        # ── N days ago (general offset) ───────────────────────────────────────
        if s.startswith("__DAYS_AGO_") and s.endswith("__"):
            try:
                n = int(s[11:-2])
                return (now - timedelta(days=n)).replace(hour=0, minute=0, second=0, microsecond=0)
            except ValueError: pass

        return obj

    if isinstance(obj, dict):  return {k: _resolve_dates(v) for k, v in obj.items()}
    if isinstance(obj, list):  return [_resolve_dates(i) for i in obj]
    return obj


def _block_dangerous(obj, inside_update_field=False):
    """
    Recursively scan for always-blocked operators.
    Write operators ($set, $inc etc.) are only allowed inside the 'update' field of
    update_one/update_many — this function is called with inside_update_field=True there.
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ALWAYS_BLOCKED:
                raise ValueError(f"Operator '{k}' is not allowed.")
            if not inside_update_field and k in WRITE_OPERATORS:
                raise ValueError(
                    f"Write operator '{k}' is only allowed inside the 'update' field "
                    f"of update_one or update_many operations."
                )
            _block_dangerous(v, inside_update_field=inside_update_field)
    elif isinstance(obj, list):
        for item in obj:
            _block_dangerous(item, inside_update_field=inside_update_field)


def _serialise(docs: list) -> list:
    """
    Convert MongoDB documents to plain JSON-serialisable dicts.
    _id:
      ObjectId / None → skipped
      string / other  → kept as "name" (grouped field in $group results)
    """
    out = []
    for doc in docs:
        clean = {}
        for k, v in doc.items():
            if k == "_id":
                if isinstance(v, ObjectId) or v is None:
                    continue
                clean["name"] = v
                continue
            if isinstance(v, datetime):
                clean[k] = v.strftime("%d-%b-%Y %H:%M")
            elif isinstance(v, ObjectId):
                clean[k] = str(v)
            else:
                clean[k] = v
        out.append(clean)
    return out


async def execute_plan(plan: dict) -> dict:
    """
    Execute a single operation plan.

    READ plans:
      {"operation": "find",      "collection": "...", "filter": {}, "sort": {}, "limit": 20}
      {"operation": "aggregate", "collection": "...", "pipeline": [...]}
      {"operation": "count",     "collection": "...", "filter": {}}

    WRITE plans:
      {"operation": "insert_one",  "collection": "...", "document": {...}}
      {"operation": "update_one",  "collection": "...", "filter": {}, "update": {...}, "upsert": true/false}
      {"operation": "update_many", "collection": "...", "filter": {}, "update": {...}}

    Multi-step (e.g. sale = deduct inventory + insert sale + update customer credit):
      {"operations": [ plan1, plan2, plan3 ]}

    Returns:
      {"ok": true,  "results": [...], "modified": N, "inserted": N}
      {"ok": false, "error": "..."}
    """
    # ── Multi-step plan ──────────────────────────────────────────────────────
    if "operations" in plan:
        results  = []
        modified = 0
        inserted = 0
        for step in plan["operations"]:
            r = await execute_plan(step)
            if not r["ok"]:
                return r   # abort on first failure
            results.extend(r.get("results", []))
            modified += r.get("modified", 0)
            inserted += r.get("inserted", 0)
        return {"ok": True, "results": results, "modified": modified, "inserted": inserted}

    # ── Single-step plan ─────────────────────────────────────────────────────
    operation  = (plan.get("operation") or "").lower()
    collection = (plan.get("collection") or "").lower()

    if collection not in ALLOWED_COLLECTIONS:
        return {"ok": False, "error": f"Collection '{collection}' not allowed. Use: {sorted(ALLOWED_COLLECTIONS)}"}

    # Resolve date placeholders
    plan = _resolve_dates(plan)

    # Security scan — always-blocked operators
    try:
        if operation in ("update_one", "update_many"):
            # Scan filter normally, scan update field with write-operators allowed
            _block_dangerous(plan.get("filter", {}))
            _block_dangerous(plan.get("update", {}), inside_update_field=True)
        else:
            _block_dangerous(plan)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    col = db.get_collection(collection)

    try:
        # ── READ ──────────────────────────────────────────────────────────────
        if operation == "find":
            filt  = plan.get("filter", {})
            proj  = plan.get("projection") or None
            sort  = plan.get("sort")
            limit = min(int(plan.get("limit", 50)), 200)
            cur   = col.find(filt, proj)
            if sort: cur = cur.sort(list(sort.items()))
            cur     = cur.limit(limit)
            results = await cur.to_list(length=limit)
            return {"ok": True, "results": _serialise(results)}

        elif operation == "aggregate":
            pipeline = plan.get("pipeline", [])
            if not pipeline:
                return {"ok": False, "error": "Aggregate needs a non-empty pipeline."}
            if not any("$limit" in s for s in pipeline):
                pipeline.append({"$limit": 200})
            results = await col.aggregate(pipeline).to_list(length=200)
            return {"ok": True, "results": _serialise(results)}

        elif operation == "count":
            n = await col.count_documents(plan.get("filter", {}))
            return {"ok": True, "results": [{"count": n}]}

        # ── WRITE ─────────────────────────────────────────────────────────────
        elif operation == "insert_one":
            doc = plan.get("document", {})
            if not doc:
                return {"ok": False, "error": "insert_one needs a 'document' field."}
            # Auto-add timestamp if collection tracks dates
            if collection in ("sales", "finance") and "date" not in doc:
                doc["date"] = datetime.now(timezone.utc)
            result = await col.insert_one(doc)
            return {"ok": True, "results": [], "inserted": 1,
                    "inserted_id": str(result.inserted_id)}

        elif operation in ("update_one", "update_many"):
            filt   = plan.get("filter", {})
            update = plan.get("update", {})
            upsert = bool(plan.get("upsert", False))
            if not update:
                return {"ok": False, "error": f"{operation} needs an 'update' field."}

            # Safety fix: if $inc targets total_credit on customers collection,
            # first ensure the field is numeric (not null) to prevent MongoDB error 14.
            # We do this by running a $set: {total_credit: 0} on docs where it is null/missing.
            if collection == "customers" and "$inc" in update:
                inc_fields = update["$inc"]
                if "total_credit" in inc_fields:
                    inc_val = inc_fields["total_credit"]
                    # Guard: if the increment value itself is null/None, skip to avoid error
                    if inc_val is None:
                        return {"ok": False,
                                "error": "total_credit increment value is null — selling price was not provided"}
                    # Initialize null/missing total_credit to 0 before incrementing
                    # This runs even on docs that don't exist yet (upsert safety)
                    await col.update_many(
                        {"$or": [
                            {**filt, "total_credit": None},
                            {**filt, "total_credit": {"$exists": False}}
                        ]},
                        {"$set": {"total_credit": 0}}
                    )

            if operation == "update_one":
                r = await col.update_one(filt, update, upsert=upsert)
            else:
                r = await col.update_many(filt, update, upsert=upsert)
            return {"ok": True, "results": [],
                    "modified": r.modified_count,
                    "matched":  r.matched_count,
                    "upserted": 1 if r.upserted_id else 0}

        else:
            return {"ok": False, "error": f"Unknown operation '{operation}'."}

    except Exception as e:
        return {"ok": False, "error": f"DB error: {str(e)}"}