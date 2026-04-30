"""
PakOrderBot — Safe MongoDB Executor
Translates LLM-generated JSON plans into real Motor (async MongoDB) operations.
"""
import os, json
from datetime import datetime, timezone, timedelta
from typing import Any
import motor.motor_asyncio

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME   = "pakorderbot_db"

_client: motor.motor_asyncio.AsyncIOMotorClient | None = None

import contextvars
tenant_var = contextvars.ContextVar("tenant", default="default")

def _get_db():
    global _client
    if _client is None:
        _client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
    tenant_id = tenant_var.get()
    return _client[f"{DB_NAME}_{tenant_id}"]

ALLOWED_COLLECTIONS = {"menu", "orders", "customers", "analytics", "offers", "staff", "feedback"}
ALWAYS_BLOCKED      = {"$where", "$function", "deleteMany", "drop", "insertMany"}

def _now_utc():
    return datetime.now(timezone.utc)

DATE_PLACEHOLDERS = {
    "__TODAY_START__":     lambda: _now_utc().replace(hour=0, minute=0, second=0, microsecond=0),
    "__TODAY_END__":       lambda: _now_utc().replace(hour=23, minute=59, second=59, microsecond=999999),
    "__YESTERDAY_START__": lambda: (_now_utc()-timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0),
    "__YESTERDAY_END__":   lambda: (_now_utc()-timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=999999),
    "__WEEK_START__":      lambda: (_now_utc()-timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0),
    "__MONTH_START__":     lambda: _now_utc().replace(day=1, hour=0, minute=0, second=0, microsecond=0),
    "__HOUR_AGO__":        lambda: _now_utc()-timedelta(hours=1),
    "__2HOURS_AGO__":      lambda: _now_utc()-timedelta(hours=2),
    "__NOW__":             lambda: _now_utc(),   # exact current timestamp — use for status_updated_at
}

def _resolve_dates(obj: Any) -> Any:
    if isinstance(obj, str):   return DATE_PLACEHOLDERS[obj]() if obj in DATE_PLACEHOLDERS else obj
    if isinstance(obj, dict):  return {k: _resolve_dates(v) for k, v in obj.items()}
    if isinstance(obj, list):  return [_resolve_dates(i) for i in obj]
    return obj

def _serialise(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            # Keep _id when it's a plain string (aggregate group key, e.g. item name).
            # Drop _id only when it's a MongoDB ObjectId (bytes / bson type) or None.
            if k == "_id":
                if v is None:
                    continue                      # null group key — useless
                if isinstance(v, str):
                    out[k] = v                    # item name / status string — keep it
                    continue
                # ObjectId or any other type — skip (don't expose Mongo internals)
                continue
            if k == "password_hash": continue      # never expose password hashes
            out[k] = _serialise(v)
        return out
    if isinstance(obj, list):  return [_serialise(i) for i in obj]
    if isinstance(obj, datetime): return obj.isoformat()
    return obj

async def execute_plan(plan: dict) -> dict:
    if "operations" in plan:
        tm, ti, tu = 0, 0, 0
        for op in plan["operations"]:
            r = await execute_plan(op)
            if not r["ok"]: return r
            tm += r.get("modified",0); ti += r.get("inserted",0); tu += r.get("upserted",0)
        return {"ok":True,"results":[],"modified":tm,"inserted":ti,"upserted":tu}

    op  = plan.get("operation",""); col = plan.get("collection","")
    if col not in ALLOWED_COLLECTIONS:
        return {"ok":False,"error":f"Collection '{col}' not allowed."}
    for b in ALWAYS_BLOCKED:
        if b in json.dumps(plan):
            return {"ok":False,"error":f"Blocked operator: {b}"}

    db  = _get_db(); c = db[col]
    try:
        if op == "find":
            filt = _resolve_dates(plan.get("filter",{}))
            sort = plan.get("sort"); limit = plan.get("limit",50); proj = plan.get("projection")
            cur  = c.find(filt, proj) if proj else c.find(filt)
            if sort: cur = cur.sort([(k,v) for k,v in sort.items()])
            docs = await cur.limit(limit).to_list(length=limit)

            # FALLBACK: If menu is empty for this tenant, try the default tenant
            if not docs and col == "menu" and tenant_var.get() != "default":
                default_db = _client[f"{DB_NAME}_default"]
                cur = default_db[col].find(filt, proj) if proj else default_db[col].find(filt)
                if sort: cur = cur.sort([(k,v) for k,v in sort.items()])
                docs = await cur.limit(limit).to_list(length=limit)

            return {"ok":True,"results":_serialise(docs),"modified":0,"inserted":0,"upserted":0}

        elif op == "aggregate":
            pipeline = _resolve_dates(plan.get("pipeline",[]))
            docs = await c.aggregate(pipeline).to_list(length=None)
            return {"ok":True,"results":_serialise(docs),"modified":0,"inserted":0,"upserted":0}

        elif op == "count":
            filt  = _resolve_dates(plan.get("filter",{}))
            count = await c.count_documents(filt)
            return {"ok":True,"results":[{"count":count}],"modified":0,"inserted":0,"upserted":0}

        elif op == "insert_one":
            doc    = _resolve_dates(plan.get("document",{}))
            result = await c.insert_one(doc)
            return {"ok":True,"results":[],"modified":0,
                    "inserted":1 if result.inserted_id else 0,"upserted":0}

        elif op == "update_one":
            filt   = _resolve_dates(plan.get("filter",{}))
            update = _resolve_dates(plan.get("update",{}))
            upsert = plan.get("upsert",False)
            result = await c.update_one(filt, update, upsert=upsert)
            return {"ok":True,"results":[],"modified":result.modified_count,
                    "inserted":0,"upserted":1 if result.upserted_id else 0}

        elif op == "update_many":
            filt   = _resolve_dates(plan.get("filter",{}))
            update = _resolve_dates(plan.get("update",{}))
            result = await c.update_many(filt, update)
            return {"ok":True,"results":[],"modified":result.modified_count,"inserted":0,"upserted":0}

        else:
            return {"ok":False,"error":f"Unknown operation: {op}"}
    except Exception as e:
        return {"ok":False,"error":str(e)}