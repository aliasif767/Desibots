from fastapi import APIRouter, HTTPException, Header, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from app.models.schemas import EmergencyQuery, FirstAidResponse, BookingRequest, BookingResponse
from app.services.firstaid import process_emergency, process_chat_message
from app.services.scheduling import check_and_book, get_available_doctors
from app.db.mongo import get_db, get_user_db
from app.services.email_service import send_appointment_confirmation, send_hospital_notification
from datetime import datetime

router = APIRouter()


# ── Emergency assessment ───────────────────────────────────────────────────────
@router.post("/emergency", response_model=FirstAidResponse,
             summary="Assess emergency and get first aid guidance")
async def assess_emergency(body: EmergencyQuery):
    try:
        return await process_emergency(body.query)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# ── Smart chat endpoint ────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    context: Optional[str] = ""

@router.post("/chat", summary="Smart chat — intent detection + emergency or follow-up response")
async def chat(body: ChatRequest):
    try:
        return await process_chat_message(body.message, body.context or "")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")


# ── Doctor availability ────────────────────────────────────────────────────────
@router.get("/doctors/available",
            summary="Check available doctors for a given emergency type")
async def doctors_available(type: str = "general", query: Optional[str] = None, x_tenant_id: str = Header(default="default")):
    try:
        doctors = await get_available_doctors(type, x_tenant_id, search_query=query)
        return {"emergency_type": type, "count": len(doctors), "doctors": doctors}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Appointment booking ────────────────────────────────────────────────────────
class AppointmentRequest(BaseModel):
    doctor_id: str
    emergency_type: str
    name: str
    phone: str
    email: str
    notes: Optional[str] = None


@router.post("/appointments", summary="Book appointment and store patient info in DB")
async def book_appointment(body: AppointmentRequest, bg_tasks: BackgroundTasks, x_tenant_id: str = Header(default="default")):
    db = get_user_db(x_tenant_id)

    doctor_record = await db.doctors.find_one({"doctor_id": body.doctor_id})

    # Fallback to shared DB if doctor not in tenant DB
    if not doctor_record:
        shared = get_db()
        doctor_record = await shared.doctors.find_one({"doctor_id": body.doctor_id})

    appointment = {
        "doctor_id": body.doctor_id,
        "doctor_name": doctor_record["doctor_name"] if doctor_record else "Dr. Sarah Chen (Cardiologist)",
        "location": doctor_record["location"] if doctor_record else "City General Hospital",
        "specialty": doctor_record["specialty"] if doctor_record else "General Medicine",
        "emergency_type": body.emergency_type,
        "patient": {
            "name": body.name,
            "phone": body.phone,
            "email": body.email,
            "notes": body.notes,
        },
        "status": "Confirmed",
        "booked_at": datetime.utcnow().isoformat(),
        "appointment_time": (
            doctor_record.get("next_slot", datetime.utcnow().isoformat())
            if doctor_record else datetime.utcnow().isoformat()
        ),
    }

    result = await db.appointments.insert_one(appointment)

    # Send confirmation emails in background
    bg_tasks.add_task(
        send_appointment_confirmation,
        patient_email=body.email,
        appointment_details={
            "doctor_name": appointment["doctor_name"],
            "specialty": appointment["specialty"],
            "location": appointment["location"],
            "appointment_time": appointment["appointment_time"],
            "emergency_type": appointment["emergency_type"],
            "patient_name": body.name,
            "patient_phone": body.phone
        }
    )

    bg_tasks.add_task(
        send_hospital_notification,
        appointment_details={
            "doctor_name": appointment["doctor_name"],
            "specialty": appointment["specialty"],
            "appointment_time": appointment["appointment_time"],
            "emergency_type": appointment["emergency_type"],
            "patient_name": body.name,
            "patient_phone": body.phone,
            "patient_email": body.email
        }
    )

    return {
        "doctor_name": appointment["doctor_name"],
        "location": appointment["location"],
        "appointment_time": appointment["appointment_time"],
        "appointment_status": "Confirmed",
        "availability": "Scheduled",
        "patient": appointment["patient"],
        "appointment_id": str(result.inserted_id),
    }


# ── Hospital dashboard — all appointments ──────────────────────────────────────
@router.get("/appointments", summary="Hospital dashboard — view all booked appointments")
async def list_appointments(status: Optional[str] = None, x_tenant_id: str = Header(default="default")):
    db = get_user_db(x_tenant_id)
    query = {"status": status} if status else {}
    records = await db.appointments.find(query, {"_id": 0}).sort("booked_at", -1).to_list(200)
    return {"count": len(records), "appointments": records}


# ── Patient appointment history ────────────────────────────────────────────────
@router.get("/patient/my-appointments", summary="Patient views their own appointments")
async def patient_appointments(
    email: str,
    x_tenant_id: str = Header(default="default"),
):
    db = get_user_db(x_tenant_id)
    appointments = await db.appointments.find(
        {"patient.email": email},
        {"_id": 0}
    ).sort("booked_at", -1).to_list(50)

    return {"count": len(appointments), "appointments": appointments}


# ── Symptom pre-assessment ─────────────────────────────────────────────────────
class SymptomCheckRequest(BaseModel):
    symptoms: str

@router.post("/patient/symptom-check", summary="AI symptom pre-assessment")
async def symptom_check(body: SymptomCheckRequest):
    """
    Uses the existing emergency classification + fallback pipeline to assess symptoms.
    Returns the assessment without booking — patient can then choose to book.
    """
    try:
        result = await process_emergency(body.symptoms)
        return {
            "assessment": {
                "emergency_type": result.emergency_type,
                "subtype": result.subtype,
                "acuity": result.acuity,
                "source": result.source,
                "steps": [s.dict() for s in result.steps] if result.steps else None,
                "answer": result.answer,
                "notes": result.notes,
                "recommended_specialist": result.medical_followup.specialty,
                "doctor_available": result.medical_followup.doctor_name,
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Symptom assessment error: {str(e)}")


# ── Legacy quick book ──────────────────────────────────────────────────────────
@router.post("/book", response_model=BookingResponse, summary="Quick book by emergency type")
async def quick_book(body: BookingRequest, x_tenant_id: str = Header(default="default")):
    try:
        return await check_and_book(body.emergency_type, body.acuity, x_tenant_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── First aid records ──────────────────────────────────────────────────────────
@router.get("/firstaid", summary="List all verified first aid records")
async def list_firstaid():
    db = get_db()
    records = await db.firstaid.find({}, {"_id": 0}).to_list(100)
    return {"count": len(records), "records": records}


@router.get("/firstaid/{emergency_type}", summary="Get first aid record by type")
async def get_firstaid(emergency_type: str, subtype: str = None):
    db = get_db()
    query = {"type": emergency_type.lower()}
    if subtype:
        query["subtype"] = subtype.lower()
    record = await db.firstaid.find_one(query, {"_id": 0})
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    return record