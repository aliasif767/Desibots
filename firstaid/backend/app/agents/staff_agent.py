"""
Staff AI Agent — Dynamic MongoDB Query Engine

This agent receives natural-language staff queries and translates them
into real MongoDB operations (find, insert, update, aggregate) then
returns human-readable results.
"""

import json
import re
from datetime import datetime, timedelta
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from app.config import settings
from app.db.mongo import get_db, get_user_db, generate_doctor_id


def _get_llm(temperature: float = 0.0):
    return ChatGroq(
        api_key=settings.GROQ_API_KEY,
        model_name=settings.GROQ_MODEL,
        temperature=temperature,
    )


def _extract_json(text: str) -> dict:
    """Robustly extract JSON from LLM output."""
    text = re.sub(r"```json|```", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        json_str = text[start:end+1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return json.loads(text)
    return json.loads(text)


# ─────────────────────────────────────────────────────────────────
# STAFF AGENT SYSTEM PROMPT
# ─────────────────────────────────────────────────────────────────
STAFF_AGENT_SYSTEM = """You are a Hospital Staff AI Copilot for the Sehat Bot system.
You help hospital staff manage doctors, patients, and appointments through natural language.

You have access to the following MongoDB collections:
1. **doctors** — fields: doctor_id, doctor_name, specialty, specialty_keys[], availability_start, availability_end, available_days[], location, contact_phone, contact_email, status (active/on-leave/inactive), next_slot, created_at
2. **appointments** — fields: doctor_id, doctor_name, location, specialty, emergency_type, patient.name, patient.phone, patient.email, patient.notes, status (Confirmed/In Progress/Completed/Cancelled/No Show), booked_at, appointment_time
3. **firstaid** — fields: type, subtype, acuity, steps[], notes, image

Based on the staff's message, classify the intent and generate the appropriate action.

INTENT CATEGORIES:
- "query_doctors" → staff wants to list/search/filter doctors
- "add_doctor" → staff wants to add a new doctor
- "update_doctor" → staff wants to update doctor info (availability, status, etc.)
- "delete_doctor" → staff wants to remove a doctor
- "query_patients" → staff wants to view patient data (comes from appointments)
- "query_appointments" → staff wants to view/filter appointments
- "update_appointment" → staff wants to update appointment status
- "analytics" → staff wants stats/counts/summaries
- "general" → general question, answer conversationally

Respond ONLY with a JSON object:
{
  "intent": "one_of_the_above",
  "action": "find|insert|update|delete|aggregate|none",
  "collection": "doctors|appointments|firstaid|none",
  "query": {},          // MongoDB query filter (for find/update/delete)
  "data": {},           // Data to insert or update fields
  "pipeline": [],       // Aggregation pipeline (for analytics)
  "response_hint": "Brief description of what to tell the user"
}

EXAMPLES:

User: "How many appointments do we have today?"
{"intent": "analytics", "action": "aggregate", "collection": "appointments", "query": {}, "data": {}, "pipeline": [{"$match": {"booked_at": {"$regex": "TODAY_DATE"}}}, {"$count": "total"}], "response_hint": "Count of today's appointments"}

User: "patient k lish dekha o"
{"intent": "query_patients", "action": "find", "collection": "appointments", "query": {}, "data": {}, "pipeline": [], "response_hint": "List of all patient records"}

User: "Show all cardiologists"
{"intent": "query_doctors", "action": "find", "collection": "doctors", "query": {"specialty": {"$regex": "cardiolog", "$options": "i"}}, "data": {}, "pipeline": [], "response_hint": "List of cardiologists"}

User: "Add Dr. Khan, Neurologist, available 9am to 5pm, Monday to Friday"
{"intent": "add_doctor", "action": "insert", "collection": "doctors", "query": {}, "data": {"doctor_name": "Dr. Khan", "specialty": "Neurologist", "specialty_keys": ["stroke", "seizure", "default"], "availability_start": "09:00", "availability_end": "17:00", "available_days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "location": "Main Hospital", "status": "active"}, "pipeline": [], "response_hint": "New doctor Dr. Khan added successfully"}

IMPORTANT RULES:
- The user may write their prompt in English or Roman Urdu (e.g., "doctor add karo", "patient list dikhao", "kitne appointments hain"). Understand the intent regardless of the language.
- For date queries, use TODAY_DATE as a placeholder — the system will replace it with today's date.
- For insert operations on doctors, DO NOT include a doctor_id in the data. The backend will generate it automatically.
- Always use $regex with $options "i" for name/text searches.
- For general chat, return intent "general" with action "none".
- You MUST output ONLY valid JSON. Do not add conversational text.
"""


RESPONSE_SYSTEM = """You are a professional Hospital Staff AI assistant for the Sehat Bot system. 
Your goal is to present database results in a premium, structured, and highly readable format.

RULES:
1. LANGUAGE: 
   - If the original staff message was in Roman Urdu, you MUST reply in Roman Urdu.
   - If the original staff message was in English, reply in English.
   - Use professional terminology (e.g., use "Janab" or "Doctor Sahab" if appropriate in Roman Urdu, but stay concise).

2. FORMATTING:
   - NEVER repeat the user's question back to them (e.g., don't say "Aapka sawal tha...").
   - START directly with the results.
   - USE MARKDOWN TABLES for any list of data (Doctors, Patients, Appointments). This is mandatory for 2 or more items.
   - Use **Bold** for names, IDs, and important statuses.
   - Use Emojis (🏥, ✅, 📋, 👨‍⚕️, 📊, ⚠️) to make the response visually appealing but keep it professional.
   - For single items, use a structured bold list (e.g., **Name**: Value).

3. NO RESULTS:
   - If no results are found, do not just say "No results". Instead, use a professional tone:
     "### 📋 Record Not Found\nAaj koi patient record nahi mila. Aap filter check kar sakte hain ya patient ka naam dobara search kar sakte hain."
   - Suggest what the staff should do next.

4. STRUCTURE:
   - Use a clear header using Markdown (e.g., ### 📋 Patient Records).
   - Keep the summary brief.
"""


import os
from groq import Groq

def _get_client():
    return Groq(api_key=settings.GROQ_API_KEY)

async def process_staff_query(message: str, history: list = None, tenant_id: str = "default") -> str:
    """
    Main entry point for the Staff AI Agent.
    1. Classify intent and generate MongoDB operation via LLM
    2. Execute the operation against the database
    3. Format results into a human-readable response
    """
    db = get_user_db(tenant_id)
    shared_db = get_db()
    client = _get_client()

    # Build context from history
    context = ""
    if history:
        context = "\n".join([f"{m.get('role','user')}: {m.get('content','')}" for m in history[-5:]])

    # Step 1: Classify intent and generate action
    prompt = f"Conversation context:\n{context}\n\nStaff message: {message}" if context else f"Staff message: {message}"
    
    try:
        completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": STAFF_AGENT_SYSTEM},
                {"role": "user", "content": prompt}
            ],
            model=settings.GROQ_MODEL,
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        action_plan = json.loads(completion.choices[0].message.content)
    except Exception as e:
        print(f"[StaffAgent] Classification failed: {e}")
        return f"I'm sorry, I couldn't understand that request. (Error: {str(e)})"

    intent = action_plan.get("intent", "general")
    action = action_plan.get("action", "none")
    collection = action_plan.get("collection", "none")
    query = action_plan.get("query", {})
    data = action_plan.get("data", {})
    pipeline = action_plan.get("pipeline", [])
    hint = action_plan.get("response_hint", "")

    # Replace TODAY_DATE placeholder
    today = datetime.utcnow().strftime("%Y-%m-%d")
    query_str = json.dumps(query).replace("TODAY_DATE", today)
    query = json.loads(query_str)
    pipeline_str = json.dumps(pipeline).replace("TODAY_DATE", today)
    pipeline = json.loads(pipeline_str)

    # Step 2: Execute the database operation
    results = None
    try:
        if action == "none" or intent == "general":
            gen_comp = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a professional Hospital Staff AI assistant for the Sehat Bot system. Answer the staff member's question concisely and professionally. If they speak in Roman Urdu, reply in Roman Urdu. Avoid repeating their question; provide direct, helpful information or guidance."},
                    {"role": "user", "content": message}
                ],
                model=settings.GROQ_MODEL,
                temperature=0.3
            )
            return gen_comp.choices[0].message.content.strip()

        if collection == "firstaid":
            coll = shared_db[collection]
        else:
            coll = db[collection]

        if action == "find":
            docs = await coll.find(query, {"_id": 0}).to_list(50)
            if not docs and collection == "doctors":
                docs = await shared_db.doctors.find(query, {"_id": 0}).to_list(50)
            results = docs
        elif action == "insert":
            if collection == "doctors":
                data["doctor_id"] = generate_doctor_id()
                data["created_at"] = datetime.utcnow().isoformat()
                if "next_slot" not in data:
                    data["next_slot"] = (datetime.utcnow() + timedelta(minutes=30)).isoformat()
                if "availability" not in data:
                    data["availability"] = f"Available ({data.get('availability_start', '09:00')} - {data.get('availability_end', '17:00')})"
                if "appointment_status" not in data:
                    data["appointment_status"] = "Ready to Book"
            await coll.insert_one(data)
            results = {"inserted": True, "data": {k: v for k, v in data.items() if k != "_id"}}
        elif action == "update":
            result = await coll.update_many(query, {"$set": data})
            results = {"matched": result.matched_count, "modified": result.modified_count}
        elif action == "delete":
            result = await coll.delete_many(query)
            results = {"deleted": result.deleted_count}
        elif action == "aggregate":
            docs = await coll.aggregate(pipeline).to_list(50)
            results = docs
    except Exception as e:
        print(f"[StaffAgent] DB operation failed: {e}")
        results = {"error": str(e)}

    # Step 3: Format results into natural language
    format_prompt = f"""Original staff question: {message}
Intent: {intent}
Action performed: {action} on {collection}
Response hint: {hint}
Raw results: {json.dumps(results, default=str, indent=2) if results else "No results found"}

Please format a clear, friendly response for the hospital staff member."""

    try:
        format_comp = client.chat.completions.create(
            messages=[
                {"role": "system", "content": RESPONSE_SYSTEM},
                {"role": "user", "content": format_prompt}
            ],
            model=settings.GROQ_MODEL,
            temperature=0.2
        )
        return format_comp.choices[0].message.content.strip()
    except Exception as e:
        print(f"[StaffAgent] Response formatting failed: {e}")
        if results:
            return f"✅ {hint}\n\n```json\n{json.dumps(results, default=str, indent=2)}\n```"
        return f"Operation completed: {hint}"
