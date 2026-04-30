import asyncio
import sys
import os
from fastapi import FastAPI, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from app.graph.workflow import hisabbot_agent

# Add parent directory to path so report_engine can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from report_engine import (
    build_daily_report, build_weekly_report, build_monthly_report, is_report_due
)

app = FastAPI(title="HisabBot API", version="3.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

from app.db.session import tenant_var
@app.middleware("http")
async def tenant_middleware(request: Request, call_next):
    tenant = request.headers.get("x-tenant-id", "default")
    tenant_var.set(tenant)
    return await call_next(request)

from app.api.voice import router as voice_router
from app.api.whatsapp import router as whatsapp_router
from app.api.whatsapp_dispatcher import router as dispatcher_router

app.include_router(voice_router)
app.include_router(whatsapp_router)       # legacy: POST /whatsapp (hisabbot only)
app.include_router(dispatcher_router)     # new:    POST /wa     (all bots dispatcher)

class HistoryMessage(BaseModel):
    role:    str   # "user" or "assistant"
    content: str

class ChatIn(BaseModel):
    message: str
    history: Optional[List[HistoryMessage]] = []   # last N turns from frontend

@app.post("/chat")
async def chat(request: ChatIn):
    # Convert history to plain dicts and keep last 4 turns (2 user + 2 assistant)
    history = [{"role": h.role, "content": h.content} for h in (request.history or [])][-4:]
    result = await hisabbot_agent.ainvoke({
        "user_message":         request.message,
        "conversation_history": history,
    })
    return {
        "reply":  result["final_response"],
        "intent": result.get("extracted_intent", {})
    }

@app.get("/health")
async def health():
    return {"status": "ok", "agent": "HisabBot v3"}


# ── Report endpoints ─────────────────────────────────────────────────────────
# report_engine uses sync pymongo, so we run in a threadpool to avoid blocking

def _serialize_report(data):
    """Make report data JSON-serializable (handle datetime, ObjectId, etc.)."""
    import json
    from datetime import datetime as dt
    from bson import ObjectId

    def default(o):
        if isinstance(o, dt):
            return o.isoformat()
        if isinstance(o, ObjectId):
            return str(o)
        return str(o)

    # Round-trip through json to handle all non-serializable types
    return json.loads(json.dumps(data, default=default))


@app.get("/report/daily")
async def report_daily(x_tenant_id: str = Header(default="default")):
    data = await asyncio.to_thread(build_daily_report, x_tenant_id)
    return _serialize_report(data)

@app.get("/report/weekly")
async def report_weekly(x_tenant_id: str = Header(default="default")):
    data = await asyncio.to_thread(build_weekly_report, x_tenant_id)
    return _serialize_report(data)

@app.get("/report/monthly")
async def report_monthly(x_tenant_id: str = Header(default="default")):
    data = await asyncio.to_thread(build_monthly_report, x_tenant_id)
    return _serialize_report(data)

@app.get("/report/schedule")
async def report_schedule():
    daily_due, daily_msg = is_report_due("daily")
    weekly_due, weekly_msg = is_report_due("weekly")
    monthly_due, monthly_msg = is_report_due("monthly")
    return {
        "daily":   {"due": daily_due,   "message": daily_msg},
        "weekly":  {"due": weekly_due,  "message": weekly_msg},
        "monthly": {"due": monthly_due, "message": monthly_msg},
    }