import os, asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends, Header, Request, Form, Response
from fastapi.middleware.cors import CORSMiddleware
from twilio.twiml.messaging_response import MessagingResponse
from pydantic import BaseModel

from agent.graph.workflow import pakorderbot_agent
from agent.auth import create_token, verify_token, hash_password, verify_password
from agent.graph.db_executor import tenant_var

app = FastAPI(title="PakOrderBot API", version="2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.middleware("http")
async def tenant_middleware(request: Request, call_next):
    tenant = request.headers.get("x-tenant-id", "default")
    tenant_var.set(tenant)
    return await call_next(request)


class HistoryMessage(BaseModel):
    role:    str
    content: str

class ChatIn(BaseModel):
    message:     str
    history:     Optional[List[HistoryMessage]] = []   # full history from frontend
    conv_stage:  Optional[str]  = ""
    order_draft: Optional[dict] = {}

class LoginIn(BaseModel):
    username: str
    password: str


def _get_role(request: Request, authorization: Optional[str] = Header(default=None)) -> str:
    # 1. Prioritize header from proxy (internal trusted)
    role_header = request.headers.get("x-tenant-role")
    if role_header: return role_header

    # 2. Fallback to JWT (direct access)
    if not authorization or not authorization.startswith("Bearer "):
        return "customer"
    payload = verify_token(authorization.split(" ",1)[1])
    return payload.get("role","customer") if payload else "customer"

def _require_staff(request: Request, authorization: Optional[str] = Header(default=None)) -> dict:
    # 1. Prioritize header from proxy (internal trusted)
    role_header = (request.headers.get("x-tenant-role") or "").lower()
    user_header = request.headers.get("x-tenant-username")
    
    print(f"DEBUG: _require_staff - Role-Header: '{role_header}', User: '{user_header}'")
    
    if role_header in ["staff", "admin"]:
        return {"sub": user_header or "proxy_staff", "role": role_header}

    # 2. Fallback to JWT (direct access)
    if not authorization or not authorization.startswith("Bearer "):
        print(f"DEBUG: Rejecting - No valid role header or auth bearer.")
        raise HTTPException(status_code=401, detail="Authentication required")
    
    payload = verify_token(authorization.split(" ",1)[1])
    if payload and payload.get("role", "").lower() in ["staff", "admin"]:
        return payload
        
    actual_role = payload.get("role") if payload else role_header
    print(f"DEBUG: Rejecting - Actual Role: '{actual_role}'")
    raise HTTPException(status_code=403, detail=f"Staff access required. your role: {actual_role}")


@app.post("/auth/login")
async def login(data: LoginIn):
    from agent.graph.db_executor import _get_db
    db   = _get_db()
    user = await db["staff"].find_one({"username": data.username})
    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Username ya password galat hai")
    token = create_token(username=data.username, role="staff")
    return {"token":token,"username":data.username,"role":"staff","message":f"Welcome, {data.username}!"}

@app.post("/auth/verify")
async def verify_jwt(payload: dict = Depends(_require_staff)):
    return {"valid":True,"username":payload.get("sub"),"role":"staff"}

@app.post("/seed-staff")
async def seed_staff(data: LoginIn):
    from agent.graph.db_executor import _get_db
    db = _get_db()
    if await db["staff"].find_one({"username": data.username}):
        raise HTTPException(status_code=400, detail="Username already exists")
    await db["staff"].insert_one({
        "username": data.username,
        "password_hash": hash_password(data.password),
        "role": "staff",
    })
    return {"message": f"Staff account '{data.username}' created."}


@app.post("/whatsapp")
async def whatsapp_webhook(Body: str = Form(...), From: str = Form(...)):
    """Receives WhatsApp texts from Twilio and responds with TwiML."""
    from agent.graph.db_executor import _get_db
    db = _get_db()
    
    # Use From as the session ID (e.g. 'whatsapp:+14155238886')
    session_id = From
    session = await db["whatsapp_sessions"].find_one({"session_id": session_id})
    if not session:
        session = {"session_id": session_id, "history": [], "conv_stage": "", "order_draft": {}}
        
    history = session.get("history", [])
    conv_stage = session.get("conv_stage", "")
    order_draft = session.get("order_draft", {})
    
    # Provide the unified agent interface just like /chat
    result = await pakorderbot_agent.ainvoke({
        "user_message":         Body,
        "conversation_history": history,
        "user_role":            "customer",
        "conv_stage":           conv_stage,
        "order_draft":          order_draft,
    })
    
    # Append the user message and bot reply to history
    history.append({"role": "user", "content": Body})
    history.append({"role": "assistant", "content": result["final_response"]})
    
    # Keep history bounded (e.g., last 20 messages)
    if len(history) > 20: history = history[-20:]
    
    # Update DB manually
    await db["whatsapp_sessions"].update_one(
        {"session_id": session_id},
        {"$set": {
            "history": history,
            "conv_stage": result.get("conv_stage", ""),
            "order_draft": result.get("order_draft", {}),
            "updated_at": datetime.now(timezone.utc)
        }},
        upsert=True
    )
    
    # Return as Twilio XML form
    resp = MessagingResponse()
    resp.message(result["final_response"])
    return Response(content=str(resp), media_type="application/xml")


@app.post("/chat")
async def chat(request: ChatIn, role: str = Depends(_get_role)):
    # Use full history from frontend — no trimming server-side
    history = [{"role":h.role,"content":h.content} for h in (request.history or [])]
    result = await pakorderbot_agent.ainvoke({
        "user_message":         request.message,
        "conversation_history": history,
        "user_role":            role,
        "conv_stage":           request.conv_stage  or "",
        "order_draft":          request.order_draft or {},
    })
    return {
        "reply":       result["final_response"],
        "intent":      result.get("extracted_intent", {}),
        "conv_stage":  result.get("conv_stage",  ""),
        "order_draft": result.get("order_draft", {}),
        "res_type":    result.get("res_type"),
        "res_data":    result.get("res_data"),
    }





@app.get("/health")
async def health():
    return {"status":"ok","agent":"PakOrderBot v2"}

@app.get("/order-status/{order_id}")
async def order_status(order_id: str):
    """
    Customer tracker polls this every 10 seconds.
    Returns real DB status + status_updated_at as unix float.
    This is the single source of truth for both staff and customer timers.
    """
    from agent.graph.db_executor import _get_db
    import math
    db  = _get_db()
    doc = await db["orders"].find_one(
        {"order_id": order_id},
        {"status": 1, "status_updated_at": 1, "created_at": 1, "_id": 0}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Order not found")
    # Use status_updated_at if available, else created_at
    ts_dt  = doc.get("status_updated_at") or doc.get("created_at")
    ts_val = ts_dt.timestamp() if ts_dt and hasattr(ts_dt, "timestamp") else None
    return {
        "order_id":  order_id,
        "status":    doc.get("status", "received"),
        "status_ts": ts_val,   # unix float — JS uses Date.now()/1000 to compare
    }

# ── STAFF DASHBOARD DATA ENDPOINTS ──────────────────────────────────────────

@app.get("/staff/orders/live")
async def get_live_orders(payload: dict = Depends(_require_staff)):
    """Fetch all pending orders (Received/Preparing/Ready) for the live board."""
    from agent.graph.db_executor import execute_plan
    r = await execute_plan({
        "operation": "find",
        "collection": "orders",
        "filter": {"status": {"$in": ["received", "preparing", "ready"]}},
        "sort": {"created_at": 1},
        "limit": 100
    })
    return {"orders": r.get("results", [])}

@app.patch("/staff/orders/{order_id}/status")
async def update_order_status(order_id: str, data: dict, payload: dict = Depends(_require_staff)):
    """Update order status manually from the dashboard."""
    from agent.graph.db_executor import _get_db
    db = _get_db()
    new_status = data.get("status")
    if not new_status: raise HTTPException(status_code=400, detail="Status required")
    
    result = await db["orders"].update_one(
        {"order_id": order_id},
        {"$set": {
            "status": new_status, 
            "status_updated_at": datetime.now(timezone.utc),
            "auto_at": datetime.now(timezone.utc) # Mark when automation should check this
        }}
    )
    if result.matched_count == 0: raise HTTPException(status_code=404, detail="Order not found")
    try:
        t_id = tenant_var.get()
        print(f"DEBUG: Order {order_id} status updated to {new_status} (Tenant: {t_id})")
    except:
        print(f"DEBUG: Order {order_id} status updated to {new_status} (Tenant: unknown)")
    return {"message": f"Order {order_id} pushed to {new_status}"}

@app.get("/staff/feedback")
async def get_all_feedback(payload: dict = Depends(_require_staff)):
    """Fetch all feedback for the dashboard."""
    from agent.graph.db_executor import _get_db
    db = _get_db()
    docs = await db["feedback"].find({}, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
    return {"feedback": docs}

@app.get("/staff/orders/history")
async def get_order_history(search: Optional[str] = None, status: Optional[str] = None, payload: dict = Depends(_require_staff)):
    """Searchable order history."""
    from agent.graph.db_executor import _get_db
    db = _get_db()
    filt = {}
    if status and status != "all": filt["status"] = status
    if search:
        filt["$or"] = [
            {"order_id": {"$regex": search, "$options": "i"}},
            {"customer_name": {"$regex": search, "$options": "i"}},
            {"customer_phone": {"$regex": search, "$options": "i"}}
        ]
    
    docs = await db["orders"].find(filt).sort("created_at", -1).limit(100).to_list(100)
    from agent.graph.db_executor import _serialise
    return {"orders": _serialise(docs)}

@app.get("/staff/menu/all")
async def get_staff_menu(payload: dict = Depends(_require_staff)):
    """Get full menu including disabled items."""
    from agent.graph.db_executor import execute_plan
    r = await execute_plan({
        "operation": "find",
        "collection": "menu",
        "filter": {},
        "sort": {"category": 1},
        "limit": 200
    })
    return {"menu": r.get("results", [])}

@app.post("/staff/menu")
async def upsert_menu_item(item: dict, payload: dict = Depends(_require_staff)):
    from agent.graph.db_executor import _get_db
    db = _get_db()
    name = item.get("name", "").lower().strip()
    if not name: raise HTTPException(status_code=400, detail="Item name required")
    
    # Prep times etc should be ints
    item["prep_time"] = int(item.get("prep_time", 20))
    item["price"] = float(item.get("price", 0))
    item["name"] = name
    
    await db["menu"].update_one({"name": name}, {"$set": item}, upsert=True)
    return {"message": f"Item '{name}' saved."}

@app.delete("/staff/menu/{name}")
async def delete_menu_item(name: str, payload: dict = Depends(_require_staff)):
    from agent.graph.db_executor import _get_db
    db = _get_db()
    await db["menu"].delete_one({"name": name.lower()})
    return {"message": "Deleted"}

@app.get("/staff/offers")
async def get_offers(payload: dict = Depends(_require_staff)):
    from agent.graph.db_executor import execute_plan
    r = await execute_plan({"operation": "find", "collection": "offers", "limit": 50})
    return {"offers": r.get("results", [])}

@app.post("/staff/offers")
async def upsert_offer(offer: dict, payload: dict = Depends(_require_staff)):
    from agent.graph.db_executor import _get_db
    db = _get_db()
    title = offer.get("title", "").strip()
    if not title: raise HTTPException(status_code=400, detail="Offer title required")
    await db["offers"].update_one({"title": title}, {"$set": offer}, upsert=True)
    return {"message": "Offer saved"}

# ── ANALYTICS ───────────────────────────────────────────────────────────────

@app.get("/staff/analytics/summary")
async def get_analytics_summary(payload: dict = Depends(_require_staff)):
    from agent.graph.db_executor import _get_db
    db = _get_db()
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # 7-day revenue aggregation
    pipeline = [
        {"$match": {"created_at": {"$gte": today_start - timedelta(days=7)}, "status": {"$ne": "cancelled"}}},
        {"$group": {
            "_id": None,
            "total_revenue": {"$sum": "$total_amount"},
            "total_orders": {"$sum": 1},
            "avg_order": {"$avg": "$total_amount"}
        }}
    ]
    res = await db["orders"].aggregate(pipeline).to_list(1)
    summary = res[0] if res else {"total_revenue": 0, "total_orders": 0, "avg_order": 0}
    
    # Today stats
    today_orders = await db["orders"].count_documents({"created_at": {"$gte": today_start}, "status": {"$ne": "cancelled"}})
    
    return {
        "summary": summary,
        "today_orders": today_orders,
        "generated_at": now.isoformat()
    }

@app.get("/staff/analytics/revenue-chart")
async def get_revenue_chart(days: int = 7, payload: dict = Depends(_require_staff)):
    from agent.graph.db_executor import _get_db
    db = _get_db()
    start = (datetime.now(timezone.utc) - timedelta(days=days)).replace(hour=0, minute=0, second=0)
    
    pipeline = [
        {"$match": {"created_at": {"$gte": start}, "status": {"$ne": "cancelled"}}},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
            "revenue": {"$sum": "$total_amount"},
            "orders": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]
    docs = await db["orders"].aggregate(pipeline).to_list(length=days+1)
    return {"data": [{"date": d["_id"], "revenue": d["revenue"], "orders": d["orders"]} for d in docs]}

@app.get("/staff/analytics/categories")
async def get_category_stats(payload: dict = Depends(_require_staff)):
    from agent.graph.db_executor import _get_db
    db = _get_db()
    pipeline = [
        {"$match": {"status": {"$ne": "cancelled"}}},
        {"$unwind": "$items"},
        {"$group": {
            "_id": "$items.category",
            "revenue": {"$sum": "$items.subtotal"},
            "count": {"$sum": "$items.qty"}
        }},
        {"$sort": {"revenue": -1}}
    ]
    docs = await db["orders"].aggregate(pipeline).to_list(100)
    return {"data": [{"category": d["_id"] or "Other", "revenue": d["revenue"], "count": d["count"]} for d in docs]}

@app.post("/staff/chat")
async def staff_chat(data: dict, payload: dict = Depends(_require_staff)):
    history_in = data.get("history", [])
    history = []
    for h in history_in:
        r = "assistant" if h.get("role") == "bot" else h.get("role", "user")
        history.append({"role": r, "content": h.get("content", "")})
        
    result = await pakorderbot_agent.ainvoke({
        "user_message":         data.get("message", ""),
        "conversation_history": history,
        "user_role":            "staff",
        "conv_stage":           "",
        "order_draft":          {},
    })
    return {
        "reply":    result["final_response"],
        "intent":   result.get("extracted_intent",{}),
        "operator": payload.get("sub"),
    }

# ── AUTOMATION WORKER ───────────────────────────────────────────────────────

async def auto_advance_worker():
    """Background task to simulate the automated order lifecycle."""
    print("[Automation] Starting order advancement loop...")
    from agent.graph.db_executor import _client, DB_NAME, _get_db
    
    # ── Fast Mode Timings (Seconds) ──────────────────────────
    PREP_SEC    = 45   # preparing -> ready
    PICKUP_SEC  = 30   # ready -> dispatched
    DELIVERY_SEC = 90  # dispatched -> delivered
    
    while True:
        try:
            # Ensure DB connection exists
            if not _client: 
                try: _get_db()
                except: pass
            
            if _client:
                # 1. Discover all tenant databases
                db_list_resp = await _client.admin.list_databases()
                target_dbs = [d["name"] for d in db_list_resp["databases"] if d["name"].startswith(DB_NAME)]
                
                for db_name in target_dbs:
                    db  = _client[db_name]
                    now = datetime.now(timezone.utc)
                    
                    # ── Stage 1: Preparing -> Ready ────────────────────
                    prep_orders = await db["orders"].find({"status":"preparing"}).to_list(100)
                    for order in prep_orders:
                        ts = order.get("status_updated_at")
                        if ts and (now - ts).total_seconds() > PREP_SEC:
                            await db["orders"].update_one(
                                {"_id": order["_id"]}, 
                                {"$set": {"status":"ready", "status_updated_at": now}}
                            )
                            print(f"[Auto][{db_name}] Order {order.get('order_id')} is READY")

                    # ── Stage 2: Ready -> Dispatched ───────────────────
                    ready_orders = await db["orders"].find({"status":"ready"}).to_list(100)
                    for order in ready_orders:
                        ts = order.get("status_updated_at")
                        if ts and (now - ts).total_seconds() > PICKUP_SEC:
                            await db["orders"].update_one(
                                {"_id": order["_id"]}, 
                                {"$set": {"status":"dispatched", "status_updated_at": now}}
                            )
                            print(f"[Auto][{db_name}] Order {order.get('order_id')} DISPATCHED")

                    # ── Stage 3: Dispatched -> Delivered ───────────────
                    disp_orders = await db["orders"].find({"status":"dispatched"}).to_list(100)
                    for order in disp_orders:
                        ts = order.get("status_updated_at")
                        if ts and (now - ts).total_seconds() > DELIVERY_SEC:
                            await db["orders"].update_one(
                                {"_id": order["_id"]}, 
                                {"$set": {"status":"delivered", "status_updated_at": now}}
                            )
                            print(f"[Auto][{db_name}] Order {order.get('order_id')} DELIVERED")

        except Exception as e:
            # Silent fail for automation to avoid log spam, but print occasionally
            pass
            
        await asyncio.sleep(15) # Pulse every 15 seconds

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(auto_advance_worker())