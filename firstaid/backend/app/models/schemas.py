from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime

class EmergencyQuery(BaseModel):
    query: str = Field(..., min_length=3, max_length=500, description="User's emergency description")

class FirstAidStep(BaseModel):
    step_number: int
    instruction: str


class Symptom(BaseModel):
    name: str


class MedicalFollowup(BaseModel):
    doctor_name: str
    specialty: Optional[str] = None
    availability: str
    appointment_status: Literal["Confirmed", "Pending User Confirmation", "No Doctors Available", "Ready to Book"]
    appointment_time: Optional[datetime] = None
    location: Optional[str] = None
    available_days: Optional[List[str]] = None

class FirstAidResponse(BaseModel):
    source: Literal["database", "llm"]
    emergency_type: str
    subtype: Optional[str] = None
    acuity: Literal["high", "medium", "low"]
    symptoms: Optional[List[str]] = None  
    steps: Optional[List[FirstAidStep]] = None
    answer: Optional[str] = None
    image: Optional[str] = None
    medical_followup: MedicalFollowup
    notes: str

class ClassificationResult(BaseModel):
    emergency_type: str
    subtype: Optional[str] = None
    acuity: Literal["high", "medium", "low"]
    language: Optional[str] = "english"

class BookingRequest(BaseModel):
    emergency_type: str
    acuity: Literal["high", "medium", "low"]
    patient_name: Optional[str] = "Anonymous"
    location: Optional[str] = None

class BookingResponse(BaseModel):
    doctor_name: str
    specialty: str
    availability: str
    appointment_status: str
    appointment_time: Optional[datetime] = None
    location: Optional[str] = None
    available_days: Optional[List[str]] = None


# ═══════════════════════════════════════════════════════════════════
# STAFF PANEL SCHEMAS
# ═══════════════════════════════════════════════════════════════════

class DoctorCreate(BaseModel):
    doctor_name: str = Field(..., min_length=2, max_length=100)
    specialty: str = Field(..., min_length=2, max_length=80)
    specialty_keys: Optional[List[str]] = Field(default=["default"])
    availability_start: str = Field(default="09:00", description="HH:MM format")
    availability_end: str = Field(default="17:00", description="HH:MM format")
    available_days: List[str] = Field(default=["Mon", "Tue", "Wed", "Thu", "Fri"])
    location: str = Field(default="Main Hospital")
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    status: Literal["active", "on-leave", "inactive"] = "active"


class DoctorUpdate(BaseModel):
    doctor_name: Optional[str] = None
    specialty: Optional[str] = None
    specialty_keys: Optional[List[str]] = None
    availability_start: Optional[str] = None
    availability_end: Optional[str] = None
    available_days: Optional[List[str]] = None
    location: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    status: Optional[Literal["active", "on-leave", "inactive"]] = None


class AppointmentStatusUpdate(BaseModel):
    status: Literal["Confirmed", "In Progress", "Completed", "Cancelled", "No Show"]


class StaffChatRequest(BaseModel):
    message: str
    history: Optional[List[dict]] = []
