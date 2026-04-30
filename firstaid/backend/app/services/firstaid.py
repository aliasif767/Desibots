from app.db.mongo import get_db
from app.agents.classifier import (
    classify_emergency,
    classify_intent,
    generate_fallback_advice,
    answer_followup,
    translate_db_record,
    DB_CATALOGUE,
)
from app.services.scheduling import check_and_book
from app.models.schemas import FirstAidResponse, FirstAidStep, MedicalFollowup


async def process_emergency(query: str) -> FirstAidResponse:
    """
    Full orchestration pipeline:
    1. Semantically classify the query via LLM (maps to DB catalogue)
    2. Look up verified steps in MongoDB (type + subtype, then type-only fallback)
    3. Fall back to LLM-generated advice if no DB record found
    4. Book a matching doctor
    5. Return structured response
    """

    # STEP 1: Smart semantic classification
    classification = await classify_emergency(query)
    et    = classification.emergency_type   # already normalised snake_case
    sub   = classification.subtype          # already normalised or None
    acuity = classification.acuity
    language = classification.language

    # STEP 2: DB lookup — exact (type + subtype) → type-only → None
    db = get_db()
    record = None

    if sub:
        record = await db.firstaid.find_one({"type": et, "subtype": sub})

    if not record:
        record = await db.firstaid.find_one({"type": et})

    # STEP 3: Build response content
    source = "database" if record else "llm"
    steps  = None
    answer = None
    image  = None
    notes  = ""
    
    # Format initial display names (fallback or initial English)
    display_type = et.replace("_", " ").title()
    display_sub  = sub.title() if sub else None

    if record:
        raw_steps = record.get("steps", [])
        notes = record.get("notes", "")
        
        # Translate DB record (including Title/Subtype) if user spoke in a different language
        if language and language != "english":
            translated = await translate_db_record(
                type_name=display_type,
                subtype_name=display_sub,
                steps_dicts=raw_steps,
                notes=notes,
                target_language=language
            )
            display_type = translated.get("type", display_type)
            display_sub  = translated.get("subtype", display_sub)
            raw_steps    = translated.get("steps", raw_steps)
            notes        = translated.get("notes", notes)
            
        steps = [FirstAidStep(**s) for s in raw_steps]
        image = record.get("image")
        
        # Override acuity from verified DB record if available
        if record.get("acuity"):
            acuity = record["acuity"]
    else:
        answer = await generate_fallback_advice(query, acuity)
        if acuity == "high":
            notes = (
                "CALL 911 (OR YOUR LOCAL EMERGENCY NUMBER) IMMEDIATELY. "
                "This is AI-generated guidance — not a substitute for emergency services."
            )
        else:
            notes = (
                "This is general AI guidance based on medical knowledge. "
                "Always consult a qualified medical professional for proper diagnosis and treatment."
            )
        
        # If fallback LLM was used, ensure notes are also in user's language if possible
        # (Though FALLBACK_SYSTEM already handles most of the response text)

    # STEP 4: Doctor booking
    booking = await check_and_book(et, acuity)
    medical_followup = MedicalFollowup(
        doctor_name=booking.doctor_name,
        specialty=booking.specialty,
        availability=booking.availability,
        appointment_status=booking.appointment_status,
        appointment_time=booking.appointment_time,
        location=booking.location,
        available_days=booking.available_days,
    )

    # STEP 5: Final construction
    return FirstAidResponse(
        source=source,
        emergency_type=display_type,
        subtype=display_sub,
        acuity=acuity,
        steps=steps,
        answer=answer,
        image=image,
        medical_followup=medical_followup,
        notes=notes,
    )


async def process_chat_message(message: str, context: str = "") -> dict:
    """
    Smart chat handler that combines intent detection + appropriate response.
    Used by the /chat endpoint for the conversational interface.

    Returns:
        {
          "intent": str,
          "response_type": "emergency" | "followup" | "intent_only",
          "data": FirstAidResponse | str | None
        }
    """
    intent_result = await classify_intent(message, context)
    intent = intent_result.get("intent", "emergency")

    if intent == "followup":
        answer = await answer_followup(message, context)
        return {"intent": intent, "response_type": "followup", "data": answer}

    if intent in ("emergency",):
        data = await process_emergency(message)
        return {"intent": intent, "response_type": "emergency", "data": data}

    # For book / check_doctor / confirm / cancel — let the Streamlit layer handle
    return {"intent": intent, "response_type": "intent_only", "data": None}