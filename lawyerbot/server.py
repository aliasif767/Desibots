"""
LawBot FastAPI Backend
Wraps the existing RAG engine + Groq API into REST endpoints.
Run: uvicorn server:app --host 127.0.0.1 --port 8513
"""
import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from groq import Groq
from rag_engine import PakistanLawEngine
from email_service import send_appointment_confirmation, send_lawyer_notification

app = FastAPI(title="LawBot API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Initialize RAG engine at startup (one-time PDF ingestion) ─────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY") 
groq_client = Groq(api_key=GROQ_API_KEY)

law_engine = None

@app.on_event("startup")
async def startup():
    global law_engine
    law_engine = PakistanLawEngine()
    books_dir = os.path.join(os.path.dirname(__file__), "books")
    if not os.path.exists(books_dir):
        os.makedirs(books_dir)
        print("WARNING: 'books' folder is empty — put your Law PDF files there!")
    law_engine.ingest_pdfs(books_dir)
    print(f"LawBot RAG engine ready — {len(law_engine.all_chunks)} chunks indexed")


# ── Models ────────────────────────────────────────────────────────────────────
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatIn(BaseModel):
    query: str
    history: Optional[List[ChatMessage]] = []

class BookingRequest(BaseModel):
    name: str
    phone: str
    email: str
    notes: Optional[str] = None


def limit_tokens(text, max_words=800):
    """Simple word-based truncation to stay under Groq TPM limits."""
    words = text.split()
    if len(words) > max_words:
        return " ".join(words[:max_words]) + "... (truncated for brevity)"
    return text


# ── Chat Endpoint with Intent Detection ──────────────────────────────────────
@app.post("/chat")
async def chat(request: ChatIn, bg_tasks: BackgroundTasks):
    if law_engine is None or law_engine.index is None:
        return {"response": "Law engine is not ready. Please ensure PDF books are in the 'books' folder.", "sources": []}

    # 1. Detect Intent (Booking vs Query)
    conversation_history_text = "\n".join([f"{h.role}: {h.content}" for h in (request.history or [])[-4:]])
    intent_prompt = f"""
    Classify the user's latest message into ONE category: "booking" or "legal_query".
    The user may speak in English, Urdu, or Roman Urdu. Understand the meaning regardless of language.
    
    - "booking": user wants to meet a lawyer, schedule a consultation, book an appointment (e.g., 'appointment book karna hai', 'lawyer se milna hai'), or is providing details (name, phone, email) as part of an ongoing booking conversation.
    - "legal_query": user is asking about laws, sections, rights, or general legal information.
    
    Conversation History:
    {conversation_history_text}
    
    User Latest Message: "{request.query}"
    
    Respond with ONLY the word "booking" or "legal_query".
    """
    
    try:
        intent_check = groq_client.chat.completions.create(
            messages=[{"role": "system", "content": "You are a helpful intent classifier."}, 
                      {"role": "user", "content": intent_prompt}],
            model="llama-3.1-8b-instant",
            temperature=0.0
        )
        intent = intent_check.choices[0].message.content.lower().strip()
    except Exception:
        intent = "legal_query" # Fallback to RAG if classification fails

    # 2. Handle Booking Intent
    if "booking" in intent:
        import json
        messages_for_extraction = [{"role": "system", "content": '''You are an extraction assistant. Extract booking details from the conversation.
Return ONLY a valid JSON object with keys: "name", "phone", "email", "notes", and "reply".
If a detail is missing, set its value to null.
For "reply": Write a friendly message responding to the user. If any required details (name, phone, email) are missing, ask for them. If all details are present, confirm that the appointment is successfully booked.
CRITICAL LANGUAGE RULE: The "reply" MUST be in the exact same language as the user's latest message. If they speak English, reply in English. If they speak Roman Urdu (e.g., 'appointment book karna hai'), reply in Roman Urdu.
Do not include any other text besides the JSON.
'''}]
        for h in (request.history or [])[-6:]:
            messages_for_extraction.append({"role": h.role, "content": h.content})
        messages_for_extraction.append({"role": "user", "content": request.query})
        
        try:
            extract_completion = groq_client.chat.completions.create(
                messages=messages_for_extraction,
                model="llama-3.1-8b-instant",
                temperature=0.0,
                response_format={"type": "json_object"}
            )
            details = json.loads(extract_completion.choices[0].message.content)
            name = details.get("name")
            phone = details.get("phone")
            email = details.get("email")
            notes = details.get("notes") or request.query
            reply_msg = details.get("reply")
            
            if name and phone and email:
                bg_tasks.add_task(
                    send_appointment_confirmation,
                    user_email=email,
                    booking_details={"name": name, "phone": phone, "email": email, "notes": notes}
                )
                bg_tasks.add_task(
                    send_lawyer_notification,
                    booking_details={"name": name, "phone": phone, "email": email, "notes": notes}
                )
                
                # Fallback in case LLM didn't generate a proper reply
                final_reply = reply_msg if reply_msg else f"Your appointment has been successfully booked, {name}! We have sent a confirmation to {email} and will contact you at {phone} shortly."
                
                return {
                    "response": final_reply,
                    "sources": [],
                    "intent": "booking"
                }
            else:
                # Fallback for missing fields if LLM fails to generate reply
                if not reply_msg:
                    missing = []
                    if not name: missing.append("your full name")
                    if not phone: missing.append("your phone number")
                    if not email: missing.append("your email address")
                    reply_msg = f"I can help you book an appointment! Please provide {', '.join(missing)} so I can schedule it for you."
                
                return {
                    "response": reply_msg,
                    "sources": [],
                    "intent": "booking"
                }
        except Exception as e:
            return {
                "response": "I can help you book an appointment! Please provide your full name, phone number, and email address.",
                "sources": [],
                "intent": "booking"
            }

    # 3. RAG search
    context_chunks = law_engine.search(request.query, top_k=2)

    # 4. Build context
    formatted_chunks = []
    for c in context_chunks:
        clean_text = limit_tokens(c["text"])
        formatted_chunks.append(f"FROM {c['metadata']['source']}:\n{clean_text}")

    context_text = "\n\n".join(formatted_chunks)

    # 5. Build messages
    system_prompt = (
        "You are a friendly and expert Pakistani Legal Assistant. Your goal is to explain "
        "complex legal matters to a client who does not have a legal background. Use very "
        "simple, everyday language and avoid difficult legal jargon.\n\n"
        "LANGUAGE RULE: Detect the user's language. If the user asks in English, respond in English. "
        "If the user asks in Roman Urdu (Urdu written in English script) or Urdu script, you MUST "
        "respond in simple Roman Urdu (Urdu written in English alphabets) so they can understand "
        "easily. Use common Urdu words that are easy for a layman.\n\n"
        "Imagine you are a lawyer talking to a client in a way they can easily understand. "
        "Answer strictly using the provided context. If the user expresses a desire for "
        "professional representation or a specific appointment, advise them to use the booking form."
    )
    user_content = (
        f"CONTEXT:\n{context_text}\n\n"
        f"QUESTION: {request.query}\n\n"
        f"FORMAT (Respond in the SAME language as the detected user language):\n"
        f"1. SIMPLE SUMMARY: A very easy explanation in 2-3 sentences (no jargon).\n"
        f"2. THE LAW: Mention relevant Sections/Articles but explain them like you are talking to a friend.\n"
        f"3. STEPS TO TAKE: Simple, actionable advice for the client.\n"
        f"4. DISCLAIMER"
    )

    messages = [{"role": "system", "content": system_prompt}]
    for h in (request.history or [])[-4:]:
        messages.append({"role": h.role, "content": h.content})
    messages.append({"role": "user", "content": user_content})

    # 6. Call Groq for Legal Advice
    try:
        completion = groq_client.chat.completions.create(
            messages=messages,
            model="llama-3.1-8b-instant",
            temperature=0.1
        )
        response = completion.choices[0].message.content
    except Exception as e:
        if "rate_limit" in str(e).lower():
            response = "Rate limit exceeded. Try asking a more specific question."
        else:
            response = f"API Error: {str(e)}"

    # 7. Format sources
    sources = [
        {"source": c["metadata"]["source"], "preview": c["text"][:300]}
        for c in context_chunks
    ]

    return {"response": response, "sources": sources, "intent": "legal_query"}


@app.get("/health")
async def health():
    chunks = len(law_engine.all_chunks) if law_engine else 0
    return {"status": "ok", "agent": "LawBot v1", "chunks_indexed": chunks}


@app.post("/appointments")
async def book_appointment(body: BookingRequest, bg_tasks: BackgroundTasks):
    """
    Handle legal consultation bookings.
    Sends emails to both user and lawyer.
    """
    try:
        # 1. Trigger confirmation email to user
        bg_tasks.add_task(
            send_appointment_confirmation,
            user_email=body.email,
            booking_details=body.dict()
        )

        # 2. Trigger notification email to lawyer
        bg_tasks.add_task(
            send_lawyer_notification,
            booking_details=body.dict()
        )

        return {
            "status": "success",
            "message": "Appointment booked successfully",
            "details": {
                "name": body.name,
                "email": body.email
            }
        }
    except Exception as e:
        return {"status": "error", "message": f"Booking failed: {str(e)}"}
