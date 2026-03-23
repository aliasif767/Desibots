from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
from app.graph.workflow import hisabbot_agent

app = FastAPI(title="HisabBot API", version="3.0")

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