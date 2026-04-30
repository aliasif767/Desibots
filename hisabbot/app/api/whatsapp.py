from fastapi import APIRouter, Request, Response
from twilio.twiml.messaging_response import MessagingResponse
from app.graph.workflow import hisabbot_agent
import logging

router = APIRouter(tags=["whatsapp"])

# Simple in-memory session store: {phone_number: [history]}
# In production, use Redis or a database.
whatsapp_sessions = {}


async def _handle_whatsapp(request: Request):
    """Shared handler for both /whatsapp and /whatsapp/webhook."""
    form_data = await request.form()
    incoming_msg = form_data.get("Body", "").strip()
    sender_number = form_data.get("From", "")

    logging.info(f"WhatsApp message from {sender_number}: {incoming_msg}")

    if not incoming_msg:
        return Response(content=str(MessagingResponse()), media_type="application/xml")

    # Get or initialize session history
    if sender_number not in whatsapp_sessions:
        whatsapp_sessions[sender_number] = []

    history = whatsapp_sessions[sender_number][-4:]  # Keep last 4 turns

    try:
        result = await hisabbot_agent.ainvoke({
            "user_message": incoming_msg,
            "conversation_history": history,
        })

        reply = result.get("final_response", "I'm sorry, I couldn't process that.")

        # Update session history
        whatsapp_sessions[sender_number].append({"role": "user", "content": incoming_msg})
        whatsapp_sessions[sender_number].append({"role": "assistant", "content": reply})

        # Trim history to keep it manageable
        if len(whatsapp_sessions[sender_number]) > 10:
            whatsapp_sessions[sender_number] = whatsapp_sessions[sender_number][-10:]

        twiml_resp = MessagingResponse()
        twiml_resp.message(reply)
        return Response(content=str(twiml_resp), media_type="application/xml")

    except Exception as e:
        logging.error(f"Error in WhatsApp webhook: {e}")
        twiml_resp = MessagingResponse()
        twiml_resp.message("Sorry, I encountered an error. Please try again later.")
        return Response(content=str(twiml_resp), media_type="application/xml")


# Twilio sandbox sends to /whatsapp (no trailing path)
@router.post("/whatsapp")
async def whatsapp_root(request: Request):
    return await _handle_whatsapp(request)


# Also keep /whatsapp/webhook for backward compatibility
@router.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request):
    return await _handle_whatsapp(request)
