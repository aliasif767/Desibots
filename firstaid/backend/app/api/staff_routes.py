"""
Staff API Routes — Hospital Management Panel

All endpoints are prefixed with /staff and require staff/admin role
(enforced by the x-tenant-role header injected by the main backend proxy).
"""

from fastapi import APIRouter, HTTPException, Header, Request
from typing import Optional
from datetime import datetime, timedelta
from app.db.mongo import get_db, get_user_db, generate_doctor_id
from app.models.schemas import DoctorCreate, DoctorUpdate, AppointmentStatusUpdate, StaffChatRequest
from app.agents.staff_agent import process_staff_query

from pydantic import BaseModel
import hashlib
import hmac
import base64
import os

router = APIRouter()

class SeedStaffRequest(BaseModel):
    username: str
    password: str

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    key  = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260_000)
    return base64.b64encode(salt + key).decode()

def verify_password(password: str, stored_hash: str) -> bool:
    try:
        raw  = base64.b64decode(stored_hash.encode())
        salt = raw[:16]
        key  = raw[16:]
        check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260_000)
        return hmac.compare_digest(key, check)
    except Exception:
        return False

@router.post("/auth/login")
async def login(data: SeedStaffRequest, x_tenant_id: str = Header(default="default")):
    db = get_user_db(x_tenant_id)
    user = await db.staff.find_one({"username": data.username})
    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Since firstaid uses x-tenant-role header for proxy, 
    # we don't strictly need a JWT here if only accessed through main dashboard,
    # but we'll return a dummy token or success message to satisfy the frontend.
    return {"message": "Login successful", "username": data.username, "role": "staff"}

@router.post("/seed-staff")
async def seed_staff(data: SeedStaffRequest, x_tenant_id: str = Header(default="default")):
    db = get_user_db(x_tenant_id)
    # Also check shared db for existing staff if needed, but usually staff is per tenant
    if await db.staff.find_one({"username": data.username}):
        raise HTTPException(status_code=400, detail="Staff already exists")
    
    await db.staff.insert_one({
        "username": data.username,
        "password_hash": hash_password(data.password),
        "role": "staff",
        "created_at": datetime.utcnow().isoformat()
    })
    return {"message": f"Staff account created for {data.username}"}


# ── Role Guard ─────────────────────────────────────────────────────────────────
def _check_staff_role(role: str):
    if role not in ("staff", "admin"):
        raise HTTPException(status_code=403, detail="Staff or Admin access required")


# ══════════════════════════════════════════════════════════════════
# DOCTOR MANAGEMENT
# ══════════════════════════════════════════════════════════════════

@router.get("/doctors", summary="List all doctors with optional filters")
async def list_doctors(
    specialty: Optional[str] = None,
    status: Optional[str] = None,
    x_tenant_id: str = Header(default="default"),
    x_tenant_role: str = Header(default="user"),
):
    _check_staff_role(x_tenant_role)
    db = get_user_db(x_tenant_id)

    query = {}
    if specialty:
        query["specialty"] = {"$regex": specialty, "$options": "i"}
    if status:
        query["status"] = status

    doctors = await db.doctors.find(query, {"_id": 0}).sort("doctor_name", 1).to_list(100)

    # Also check shared db for seed doctors if tenant db has none
    if not doctors:
        from app.db.mongo import get_db as get_shared_db
        shared = get_shared_db()
        doctors = await shared.doctors.find(query, {"_id": 0}).sort("doctor_name", 1).to_list(100)

    return {"count": len(doctors), "doctors": doctors}


@router.post("/doctors", summary="Add a new doctor")
async def add_doctor(
    body: DoctorCreate,
    x_tenant_id: str = Header(default="default"),
    x_tenant_role: str = Header(default="user"),
):
    _check_staff_role(x_tenant_role)
    db = get_user_db(x_tenant_id)

    doc = body.dict()
    doc["doctor_id"] = generate_doctor_id()
    doc["created_at"] = datetime.utcnow().isoformat()
    doc["updated_at"] = datetime.utcnow().isoformat()
    doc["next_slot"] = (datetime.utcnow() + timedelta(minutes=30)).isoformat()
    doc["availability"] = f"Available ({doc['availability_start']} - {doc['availability_end']})"
    doc["appointment_status"] = "Ready to Book"

    await db.doctors.insert_one(doc)
    doc.pop("_id", None)

    return {"message": f"Doctor {doc['doctor_name']} added successfully", "doctor": doc}


@router.put("/doctors/{doctor_id}", summary="Update a doctor's information")
async def update_doctor(
    doctor_id: str,
    body: DoctorUpdate,
    x_tenant_id: str = Header(default="default"),
    x_tenant_role: str = Header(default="user"),
):
    _check_staff_role(x_tenant_role)
    db = get_user_db(x_tenant_id)

    update_data = {k: v for k, v in body.dict().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    update_data["updated_at"] = datetime.utcnow().isoformat()

    # Recalculate availability string if time changed
    if "availability_start" in update_data or "availability_end" in update_data:
        existing = await db.doctors.find_one({"doctor_id": doctor_id})
        if not existing:
            # Try shared db
            from app.db.mongo import get_db as get_shared_db
            shared = get_shared_db()
            existing = await shared.doctors.find_one({"doctor_id": doctor_id})
        if existing:
            start = update_data.get("availability_start", existing.get("availability_start", "09:00"))
            end = update_data.get("availability_end", existing.get("availability_end", "17:00"))
            update_data["availability"] = f"Available ({start} - {end})"

    result = await db.doctors.update_one(
        {"doctor_id": doctor_id},
        {"$set": update_data}
    )

    # Also try updating in shared db if not found in tenant db
    if result.matched_count == 0:
        from app.db.mongo import get_db as get_shared_db
        shared = get_shared_db()
        result = await shared.doctors.update_one(
            {"doctor_id": doctor_id},
            {"$set": update_data}
        )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Doctor not found")

    return {"message": "Doctor updated successfully", "modified": result.modified_count}


@router.delete("/doctors/{doctor_id}", summary="Remove a doctor")
async def delete_doctor(
    doctor_id: str,
    x_tenant_id: str = Header(default="default"),
    x_tenant_role: str = Header(default="user"),
):
    _check_staff_role(x_tenant_role)
    db = get_user_db(x_tenant_id)

    result = await db.doctors.delete_one({"doctor_id": doctor_id})

    if result.deleted_count == 0:
        # Try shared db
        from app.db.mongo import get_db as get_shared_db
        shared = get_shared_db()
        result = await shared.doctors.delete_one({"doctor_id": doctor_id})

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Doctor not found")

    return {"message": "Doctor removed successfully"}


# ══════════════════════════════════════════════════════════════════
# PATIENT DATA
# ══════════════════════════════════════════════════════════════════

@router.get("/patients", summary="List all patients from appointment records")
async def list_patients(
    search: Optional[str] = None,
    emergency_type: Optional[str] = None,
    x_tenant_id: str = Header(default="default"),
    x_tenant_role: str = Header(default="user"),
):
    _check_staff_role(x_tenant_role)
    db = get_user_db(x_tenant_id)

    pipeline = [
        {"$group": {
            "_id": "$patient.email",
            "name": {"$first": "$patient.name"},
            "phone": {"$first": "$patient.phone"},
            "email": {"$first": "$patient.email"},
            "total_appointments": {"$sum": 1},
            "last_visit": {"$max": "$booked_at"},
            "emergency_types": {"$addToSet": "$emergency_type"},
            "appointments": {"$push": {
                "doctor_name": "$doctor_name",
                "specialty": "$specialty",
                "emergency_type": "$emergency_type",
                "status": "$status",
                "booked_at": "$booked_at",
                "appointment_time": "$appointment_time",
            }},
        }},
        {"$sort": {"last_visit": -1}},
    ]

    # Add search filter
    if search:
        pipeline.insert(0, {"$match": {
            "$or": [
                {"patient.name": {"$regex": search, "$options": "i"}},
                {"patient.email": {"$regex": search, "$options": "i"}},
                {"patient.phone": {"$regex": search, "$options": "i"}},
            ]
        }})

    if emergency_type:
        pipeline.insert(0, {"$match": {"emergency_type": {"$regex": emergency_type, "$options": "i"}}})

    patients = await db.appointments.aggregate(pipeline).to_list(200)
    return {"count": len(patients), "patients": patients}


@router.get("/patients/{email}", summary="Get patient detail with full appointment history")
async def get_patient(
    email: str,
    x_tenant_id: str = Header(default="default"),
    x_tenant_role: str = Header(default="user"),
):
    _check_staff_role(x_tenant_role)
    db = get_user_db(x_tenant_id)

    appointments = await db.appointments.find(
        {"patient.email": email},
        {"_id": 0}
    ).sort("booked_at", -1).to_list(50)

    if not appointments:
        raise HTTPException(status_code=404, detail="Patient not found")

    patient = appointments[0].get("patient", {})
    return {
        "patient": patient,
        "total_appointments": len(appointments),
        "appointments": appointments,
    }


# ══════════════════════════════════════════════════════════════════
# APPOINTMENT MANAGEMENT
# ══════════════════════════════════════════════════════════════════

@router.get("/appointments", summary="List all appointments with filters")
async def list_appointments(
    status: Optional[str] = None,
    doctor_id: Optional[str] = None,
    date: Optional[str] = None,
    x_tenant_id: str = Header(default="default"),
    x_tenant_role: str = Header(default="user"),
):
    _check_staff_role(x_tenant_role)
    db = get_user_db(x_tenant_id)

    query = {}
    if status:
        query["status"] = status
    if doctor_id:
        query["doctor_id"] = doctor_id
    if date:
        query["booked_at"] = {"$regex": f"^{date}"}

    appointments = await db.appointments.find(query, {"_id": 0}).sort("booked_at", -1).to_list(200)
    return {"count": len(appointments), "appointments": appointments}


@router.patch("/appointments/{appointment_id}/status", summary="Update appointment status")
async def update_appointment_status(
    appointment_id: str,
    body: AppointmentStatusUpdate,
    x_tenant_id: str = Header(default="default"),
    x_tenant_role: str = Header(default="user"),
):
    _check_staff_role(x_tenant_role)
    db = get_user_db(x_tenant_id)

    from bson import ObjectId
    try:
        oid = ObjectId(appointment_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid appointment ID")

    result = await db.appointments.update_one(
        {"_id": oid},
        {"$set": {"status": body.status, "updated_at": datetime.utcnow().isoformat()}}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Appointment not found")

    return {"message": f"Appointment status updated to {body.status}"}


# ══════════════════════════════════════════════════════════════════
# ANALYTICS
# ══════════════════════════════════════════════════════════════════

@router.get("/analytics/summary", summary="KPI summary for dashboard")
async def analytics_summary(
    x_tenant_id: str = Header(default="default"),
    x_tenant_role: str = Header(default="user"),
):
    _check_staff_role(x_tenant_role)
    db = get_user_db(x_tenant_id)

    today = datetime.utcnow().strftime("%Y-%m-%d")

    total_appointments = await db.appointments.count_documents({})
    today_appointments = await db.appointments.count_documents({"booked_at": {"$regex": f"^{today}"}})
    confirmed = await db.appointments.count_documents({"status": "Confirmed"})
    completed = await db.appointments.count_documents({"status": "Completed"})
    cancelled = await db.appointments.count_documents({"status": "Cancelled"})

    # Count unique patients
    patient_emails = await db.appointments.distinct("patient.email")
    total_patients = len(patient_emails)

    # Count active doctors (check both tenant and shared)
    active_doctors = await db.doctors.count_documents({"status": "active"})
    if active_doctors == 0:
        from app.db.mongo import get_db as get_shared_db
        shared = get_shared_db()
        active_doctors = await shared.doctors.count_documents({"status": "active"})

    completion_rate = round((completed / total_appointments * 100), 1) if total_appointments > 0 else 0

    return {
        "summary": {
            "total_appointments": total_appointments,
            "today_appointments": today_appointments,
            "total_patients": total_patients,
            "active_doctors": active_doctors,
            "confirmed": confirmed,
            "completed": completed,
            "cancelled": cancelled,
            "completion_rate": completion_rate,
        }
    }


@router.get("/analytics/trends", summary="Weekly appointment trend data")
async def analytics_trends(
    x_tenant_id: str = Header(default="default"),
    x_tenant_role: str = Header(default="user"),
):
    _check_staff_role(x_tenant_role)
    db = get_user_db(x_tenant_id)

    # Generate last 7 days of data
    trends = []
    for i in range(6, -1, -1):
        day = datetime.utcnow() - timedelta(days=i)
        day_str = day.strftime("%Y-%m-%d")
        label = day.strftime("%b %d")
        count = await db.appointments.count_documents({"booked_at": {"$regex": f"^{day_str}"}})
        trends.append({"date": label, "appointments": count})

    # Specialty breakdown
    specialty_data = await db.appointments.aggregate([
        {"$group": {"_id": "$specialty", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 6},
    ]).to_list(10)

    specialties = [{"name": s["_id"] or "General", "value": s["count"]} for s in specialty_data]

    return {"trends": trends, "specialties": specialties}


# ══════════════════════════════════════════════════════════════════
# STAFF AI CHAT
# ══════════════════════════════════════════════════════════════════

@router.post("/chat", summary="Staff AI Copilot — dynamic query agent")
async def staff_chat(
    body: StaffChatRequest,
    x_tenant_id: str = Header(default="default"),
    x_tenant_role: str = Header(default="user"),
):
    _check_staff_role(x_tenant_role)

    try:
        reply = await process_staff_query(body.message, body.history, x_tenant_id)
        return {"reply": reply}
    except Exception as e:
        print(f"[StaffChat] Error: {e}")
        return {"reply": f"I encountered an error processing your request. Please try again. Error: {str(e)}"}
