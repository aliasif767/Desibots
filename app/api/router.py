from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.graph.workflow import hisabbot_agent

router = APIRouter()

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    reply: str
    intent_extracted: dict

@router.post("/chat", response_model=ChatResponse)
async def chat_with_bot(request: ChatRequest):
    try:
        initial_state = {"user_message": request.message}
        final_state = await hisabbot_agent.ainvoke(initial_state)

        return {
            "reply": final_state["final_response"],
            "intent_extracted": final_state.get("extracted_intent", {})
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))