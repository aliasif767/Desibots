import random
from datetime import datetime, timedelta
from app.models.schemas import BookingResponse
from app.db.mongo import get_db

SPECIALTY_MAP = {
    "choking":            "Pediatrician",
    "cardiac_arrest":     "Cardiologist",
    "heart_attack":       "Cardiologist",
    "bleeding":           "Emergency Medicine",
    "burn":               "Dermatologist",
    "sprain":             "Orthopedic Specialist",
    "fracture":           "Orthopedic Specialist",
    "bee_sting":          "Allergist / Immunologist",
    "allergic_reaction":  "Allergist / Immunologist",
    "stroke":             "Neurologist",
    "seizure":            "Neurologist",
    "default":            "General Practitioner",
}

SEED_DOCTORS = [
    {
        "doctor_id": "doc_001",
        "doctor_name": "Dr. Sarah Chen",
        "specialty": "Cardiologist",
        "specialty_keys": ["cardiac_arrest", "heart_attack", "default"],
        "availability": "Available Now",
        "appointment_status": "Ready to Book",
        "location": "City General Hospital — 1.2 miles away",
        "next_slot": (datetime.utcnow() + timedelta(minutes=20)).isoformat(),
        "availability_start": "08:00",
        "availability_end": "16:00",
        "available_days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
        "contact_phone": "+92-300-1234567",
        "contact_email": "sarah.chen@hospital.pk",
        "status": "active",
        "created_at": datetime.utcnow().isoformat(),
    },
    {
        "doctor_id": "doc_002",
        "doctor_name": "Dr. James Okafor",
        "specialty": "Emergency Medicine",
        "specialty_keys": ["bleeding", "burn", "fracture", "default"],
        "availability": "Available in 15 mins",
        "appointment_status": "Ready to Book",
        "location": "MedFirst Urgent Care — 0.8 miles away",
        "next_slot": (datetime.utcnow() + timedelta(minutes=15)).isoformat(),
        "availability_start": "07:00",
        "availability_end": "19:00",
        "available_days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
        "contact_phone": "+92-300-2345678",
        "contact_email": "james.okafor@medfirst.pk",
        "status": "active",
        "created_at": datetime.utcnow().isoformat(),
    },
    {
        "doctor_id": "doc_003",
        "doctor_name": "Dr. Amina Raza",
        "specialty": "Allergist / Immunologist",
        "specialty_keys": ["bee_sting", "allergic_reaction", "default"],
        "availability": "Available in 30 mins",
        "appointment_status": "Ready to Book",
        "location": "HealthPoint Clinic — 2.0 miles away",
        "next_slot": (datetime.utcnow() + timedelta(minutes=30)).isoformat(),
        "availability_start": "09:00",
        "availability_end": "17:00",
        "available_days": ["Mon", "Wed", "Fri"],
        "contact_phone": "+92-300-3456789",
        "contact_email": "amina.raza@healthpoint.pk",
        "status": "active",
        "created_at": datetime.utcnow().isoformat(),
    },
    {
        "doctor_id": "doc_004",
        "doctor_name": "Dr. Carlos Mendez",
        "specialty": "Neurologist",
        "specialty_keys": ["stroke", "seizure", "default"],
        "availability": "Available Now",
        "appointment_status": "Ready to Book",
        "location": "Downtown Medical Center — 1.5 miles away",
        "next_slot": (datetime.utcnow() + timedelta(minutes=10)).isoformat(),
        "availability_start": "10:00",
        "availability_end": "18:00",
        "available_days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
        "contact_phone": "+92-300-4567890",
        "contact_email": "carlos.mendez@downtown.pk",
        "status": "active",
        "created_at": datetime.utcnow().isoformat(),
    },
    {
        "doctor_id": "doc_005",
        "doctor_name": "Dr. Priya Sharma",
        "specialty": "Pediatrician",
        "specialty_keys": ["choking", "default"],
        "availability": "Available Now",
        "appointment_status": "Ready to Book",
        "location": "Children's Health Clinic — 1.0 miles away",
        "next_slot": (datetime.utcnow() + timedelta(minutes=5)).isoformat(),
        "availability_start": "08:00",
        "availability_end": "14:00",
        "available_days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
        "contact_phone": "+92-300-5678901",
        "contact_email": "priya.sharma@childhealth.pk",
        "status": "active",
        "created_at": datetime.utcnow().isoformat(),
    },
    {
        "doctor_id": "doc_006",
        "doctor_name": "Dr. Michael Torres",
        "specialty": "Orthopedic Specialist",
        "specialty_keys": ["sprain", "fracture", "default"],
        "availability": "Available in 1 hour",
        "appointment_status": "Ready to Book",
        "location": "BoneAndJoint Clinic — 3.0 miles away",
        "next_slot": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
        "availability_start": "09:00",
        "availability_end": "17:00",
        "available_days": ["Tue", "Thu", "Sat"],
        "contact_phone": "+92-300-6789012",
        "contact_email": "michael.torres@boneandjoint.pk",
        "status": "active",
        "created_at": datetime.utcnow().isoformat(),
    },
]


async def seed_doctors():
    """Seed doctor records into MongoDB if not already seeded."""
    db = get_db()
    count = await db.doctors.count_documents({})
    if count == 0:
        await db.doctors.insert_many(SEED_DOCTORS)
        print(f"Seeded {len(SEED_DOCTORS)} doctors.")


async def get_available_doctors(emergency_type: str, tenant_id: str = "default", search_query: str = None) -> list:
    """
    Query MongoDB for doctors matching the emergency type or a specific search query.
    Falls back to default doctors if no specialty match found.
    """
    from app.db.mongo import get_user_db, get_db
    import re
    
    et = emergency_type.lower().replace(" ", "_")
    db = get_user_db(tenant_id)
    shared_db = get_db()
    
    docs = []

    # 1. If search_query provided, search by name or specialty
    if search_query and search_query.strip():
        sq_low = search_query.lower()
        # Check if user wants to see ALL doctors (English or Roman Urdu)
        if any(w in sq_low for w in ["all", "sary", "sab", "list", "show", "dekha", "available", "availability", "doctors"]):
            docs = await db.doctors.find({"status": "active"}, {"_id": 0}).to_list(50)
            if not docs:
                docs = await shared_db.doctors.find({"status": "active"}, {"_id": 0}).to_list(50)
            return docs

        # Remove common stop words from query to improve regex matching
        clean_query = re.sub(r'(?i)\b(book|appointment|with|for|a|an|the|dr\.?|k|sat|karna|hai|me|my)\b', '', search_query).strip()
        words = [w for w in clean_query.split() if len(w) >= 2] # Changed to >= 2
        
        if words:
            # Join words with OR operator for regex
            regex_pattern = "|".join(re.escape(w) for w in words)
            search_filter = {
                "$or": [
                    {"doctor_name": {"$regex": regex_pattern, "$options": "i"}},
                    {"specialty": {"$regex": regex_pattern, "$options": "i"}},
                    {"location": {"$regex": regex_pattern, "$options": "i"}}
                ],
                "status": "active"
            }
            # Check tenant DB
            docs = await db.doctors.find(search_filter, {"_id": 0}).to_list(50)
            
            # Fallback to shared DB for search query
            if not docs:
                docs = await shared_db.doctors.find(search_filter, {"_id": 0}).to_list(50)
                
            if docs:
                return docs
            else:
                # If a specific search was made and NO matching doctor found, return empty
                # so the frontend can display a professional "not found" message.
                return []

    # 2. Try specialty match first in tenant DB
    docs = await db.doctors.find(
        {"specialty_keys": et, "status": "active"},
        {"_id": 0}
    ).to_list(50)

    # Fallback to default pool in tenant DB
    if not docs:
        docs = await db.doctors.find(
            {
                "$or": [
                    {"specialty_keys": "default"},
                    {"specialty_keys": {"$size": 0}},
                    {"specialty_keys": {"$exists": False}}
                ],
                "status": "active"
            },
            {"_id": 0}
        ).to_list(50)

    # Fallback to shared DB if tenant DB has no matches
    if not docs:
        docs = await shared_db.doctors.find(
            {"specialty_keys": et, "status": "active"},
            {"_id": 0}
        ).to_list(50)

    if not docs:
        docs = await shared_db.doctors.find(
            {
                "$or": [
                    {"specialty_keys": "default"},
                    {"specialty_keys": {"$size": 0}},
                    {"specialty_keys": {"$exists": False}}
                ],
                "status": "active"
            },
            {"_id": 0}
        ).to_list(50)

    return docs


async def check_and_book(emergency_type: str, acuity: str, tenant_id: str = "default") -> BookingResponse:
    """
    Find the best available doctor and return booking response.
    Used by the legacy /book endpoint.
    """
    docs = await get_available_doctors(emergency_type, tenant_id)
    doc  = docs[0] if docs else SEED_DOCTORS[0]

    return BookingResponse(
        doctor_name=doc["doctor_name"],
        specialty=doc["specialty"],
        availability=doc["availability"],
        appointment_status=doc["appointment_status"],
        appointment_time=datetime.fromisoformat(doc["next_slot"]) if doc.get("next_slot") else None,
        location=doc["location"],
        available_days=doc.get("available_days"),
    )