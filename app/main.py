from fastapi import FastAPI
from pydantic import BaseModel
from app.graph.workflow import hisabbot_agent

app = FastAPI(title="HisabBot API", version="2.0")

class ChatIn(BaseModel):
    message: str

@app.post("/chat")
async def chat(request: ChatIn):
    result = await hisabbot_agent.ainvoke({"user_message": request.message})
    return {
        "reply": result["final_response"],
        "intent": result.get("extracted_intent", {})
    }

@app.get("/health")
async def health():
    return {"status": "ok", "agent": "HisabBot v2"}