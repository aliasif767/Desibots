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
- "query_patients" → staff wants to view patient data
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

User: "Show all cardiologists"
{"intent": "query_doctors", "action": "find", "collection": "doctors", "query": {"specialty": {"$regex": "cardiolog", "$options": "i"}}, "data": {}, "pipeline": [], "response_hint": "List of cardiologists"}

User: "Add Dr. Khan, Neurologist, available 9am to 5pm, Monday to Friday"
{"intent": "add_doctor", "action": "insert", "collection": "doctors", "query": {}, "data": {"doctor_name": "Dr. Khan", "specialty": "Neurologist", "specialty_keys": ["stroke", "seizure", "default"], "availability_start": "09:00", "availability_end": "17:00", "available_days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "location": "Main Hospital", "status": "active"}, "pipeline": [], "response_hint": "New doctor Dr. Khan added successfully"}

User: "Put Dr. Sarah Chen on leave"
{"intent": "update_doctor", "action": "update", "collection": "doctors", "query": {"doctor_name": {"$regex": "sarah chen", "$options": "i"}}, "data": {"status": "on-leave"}, "pipeline": [], "response_hint": "Dr. Sarah Chen status updated to on-leave"}

User: "Show all patients who booked for burns"
{"intent": "query_patients", "action": "find", "collection": "appointments", "query": {"emergency_type": {"$regex": "burn", "$options": "i"}}, "data": {}, "pipeline": [], "response_hint": "Patients who booked for burn emergencies"}

User: "Cancel appointment for patient Ahmed"
{"intent": "update_appointment", "action": "update", "collection": "appointments", "query": {"patient.name": {"$regex": "ahmed", "$options": "i"}}, "data": {"status": "Cancelled"}, "pipeline": [], "response_hint": "Ahmed's appointment has been cancelled"}

User: "What specialties do we have?"
{"intent": "analytics", "action": "aggregate", "collection": "doctors", "query": {}, "data": {}, "pipeline": [{"$group": {"_id": "$specialty", "count": {"$sum": 1}}}], "response_hint": "Specialty breakdown of available doctors"}

IMPORTANT RULES:
- The user may write their prompt in English or Roman Urdu (e.g., "doctor add karo"). Understand the intent regardless of the language.
- For date queries, use TODAY_DATE as a placeholder — the system will replace it with today's date.
- For insert operations on doctors, DO NOT include a doctor_id in the data. The backend will generate it automatically.
- specialty_keys should map specialties to relevant emergency types.
- Always use $regex with $options "i" for name/text searches.
- For general chat, return intent "general" with action "none".
- You MUST output ONLY valid JSON. Do not add conversational text.
"""


RESPONSE_SYSTEM = """You are a helpful hospital staff AI assistant. Given the results of a database query, 
format a clear, professional response for the hospital staff member. 

Rules:
- If the original staff question was in Roman Urdu, you MUST reply in Roman Urdu (e.g., "Doctor add ho gaya hai").
- If the original staff question was in English, reply in English.
- Be concise but informative
- Use bullet points or numbered lists for multiple results
- Include relevant details (names, times, statuses)
- If no results found, say so clearly and suggest alternatives
- Use emojis sparingly for visual clarity (✅, 📋, 🏥, 👨‍⚕️, 📊)
- Format numbers and dates nicely
"""


async def process_staff_query(message: str, history: list = None, tenant_id: str = "default") -> str:
    """
    Main entry point for the Staff AI Agent.
    1. Classify intent and generate MongoDB operation via LLM
    2. Execute the operation against the database
    3. Format results into a human-readable response
    """
    db = get_user_db(tenant_id)
    shared_db = get_db()
    llm = _get_llm(temperature=0.0)

    # Build context from history
    context = ""
    if history:
        context = "\n".join([f"{m.get('role','user')}: {m.get('content','')}" for m in history[-5:]])

    # Step 1: Classify intent and generate action
    prompt = f"Conversation context:\n{context}\n\nStaff message: {message}" if context else f"Staff message: {message}"
    messages = [
        SystemMessage(content=STAFF_AGENT_SYSTEM),
        HumanMessage(content=prompt),
    ]

    try:
        response = await llm.ainvoke(messages)
        action_plan = _extract_json(response.content)
    except Exception as e:
        print(f"[StaffAgent] Classification failed: {e}")
        return "I'm sorry, I couldn't understand that request. Could you rephrase it? You can ask me to manage doctors, view patients, check appointments, or get analytics."

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
            # General chat — just use LLM to answer
            gen_llm = _get_llm(temperature=0.3)
            gen_msgs = [
                SystemMessage(content="You are a helpful hospital management AI assistant. Answer the staff's question concisely and professionally. If they speak in Roman Urdu, reply in Roman Urdu."),
                HumanMessage(content=message),
            ]
            gen_response = await gen_llm.ainvoke(gen_msgs)
            return gen_response.content.strip()

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
    format_llm = _get_llm(temperature=0.2)
    format_prompt = f"""Original staff question: {message}
Intent: {intent}
Action performed: {action} on {collection}
Response hint: {hint}
Raw results: {json.dumps(results, default=str, indent=2) if results else "No results found"}

Please format a clear, friendly response for the hospital staff member."""

    format_msgs = [
        SystemMessage(content=RESPONSE_SYSTEM),
        HumanMessage(content=format_prompt),
    ]

    try:
        format_response = await format_llm.ainvoke(format_msgs)
        return format_response.content.strip()
    except Exception as e:
        print(f"[StaffAgent] Response formatting failed: {e}")
        # Fallback: return raw results
        if results:
            return f"✅ {hint}\n\n```\n{json.dumps(results, default=str, indent=2)}\n```"
        return f"Operation completed: {hint}"
