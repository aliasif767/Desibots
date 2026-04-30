import json
import re
from typing import Optional
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from app.config import settings
from app.models.schemas import ClassificationResult

# ─────────────────────────────────────────────────────────────────────────────
# KNOWN DB CATALOGUE
# The LLM must map any natural language query onto one of these (type, subtype)
# pairs. This is the single source of truth — update here when DB grows.
# ─────────────────────────────────────────────────────────────────────────────
DB_CATALOGUE = [
    {"type": "choking",        "subtype": "infant",  "acuity": "high"},
    {"type": "choking",        "subtype": "adult",   "acuity": "high"},
    {"type": "choking",        "subtype": "disable",   "acuity": "high"},
     {"type": "choking",        "subtype": "pregent",   "acuity": "high"},
    {"type": "cardiac_arrest", "subtype": "adult",   "acuity": "high"},
    {"type": "bleeding",       "subtype": "severe",  "acuity": "high"},
    {"type": "burn",           "subtype": "minor",   "acuity": "low"},
    {"type": "sprain",         "subtype": "ankle",   "acuity": "low"},
]

# Serialise catalogue for prompt injection
_CATALOGUE_JSON = json.dumps(DB_CATALOGUE, indent=2)

# ─────────────────────────────────────────────────────────────────────────────
# CLASSIFICATION SYSTEM PROMPT
# Teaches the LLM to reason semantically then map to the catalogue.
# ─────────────────────────────────────────────────────────────────────────────
CLASSIFICATION_SYSTEM = f"""You are a medical emergency classifier for an AI first-aid system.

Your job is to read a user message — which may be informal, misspelled, vague, or in layman's terms —
and map it to the most appropriate entry in our verified first-aid database catalogue.

=== VERIFIED DATABASE CATALOGUE ===
{_CATALOGUE_JSON}
===================================

CLASSIFICATION RULES:

1. SEMANTIC UNDERSTANDING — do NOT match on exact words. Understand the meaning:
   - "something stuck in my throat", "can't breathe, swallowed object", "food is lodged" → choking
   - "heart stopped", "not breathing", "no pulse", "collapsed", "CPR needed" → cardiac_arrest
   - "heart attack", "chest pain", "crushing chest", "left arm pain" → cardiac_arrest (closest match)
   - "won't stop bleeding", "gushing blood", "deep gash", "cut artery" → bleeding / severe
   - "small burn", "touched hot pan", "minor scald", "slight burn" → burn / minor
   - "twisted ankle", "rolled my foot", "ankle hurts after fall" → sprain / ankle
   - "baby choking", "infant can't breathe", "toddler swallowed" → choking / infant
   - "adult choking", "grown man choking", "person at dinner choking" → choking / adult

2. SUBTYPE INFERENCE — infer subtype from context clues:
   - Age clues: "baby", "infant", "toddler", "newborn", "6-month-old" → infant
   - Age clues: "man", "woman", "adult", "person", "colleague", no age mentioned → adult
   - Severity clues: "a lot of blood", "won't stop", "spurting" → severe
   - Severity clues: "small", "minor", "slight", "a bit" → minor

3. ACUITY — follow the catalogue acuity for matched type/subtype exactly.
   If no catalogue match: high = life-threatening (airway, heart, major bleeding, unconscious), low = everything else.

4. NO CATALOGUE MATCH — if the situation genuinely does not match any catalogue entry
   (e.g. bee sting, seizure, eye injury, rash), still classify it with your best
   emergency_type in snake_case, an appropriate subtype or null, and correct acuity.
   The system will fall back to LLM advice for unmatched types.

5. LANGUAGE DETECTION — Identify the language the user is speaking. If the user is speaking in Roman Urdu (e.g. "mery bhai ko choking ho rahi hai"), return "roman urdu".

6. OUTPUT — respond ONLY with a valid JSON object, no markdown, no explanation:
{{"emergency_type": "snake_case_type", "subtype": "subtype_or_null", "acuity": "high_or_low", "language": "detected_language"}}

EXAMPLES:
User: "I have something stuck in my throat and I can't breathe"
Output: {{"emergency_type": "choking", "subtype": "adult", "acuity": "high"}}

User: "my 8 month old baby seems to have swallowed something small"
Output: {{"emergency_type": "choking", "subtype": "infant", "acuity": "high"}}

User: "the cut on my arm is bleeding really badly and won't stop"
Output: {{"emergency_type": "bleeding", "subtype": "severe", "acuity": "high"}}

User: "i accidentally touched the hot stove, slight burn on finger"
Output: {{"emergency_type": "burn", "subtype": "minor", "acuity": "low"}}

User: "my grandfather collapsed, he has no pulse"
Output: {{"emergency_type": "cardiac_arrest", "subtype": "adult", "acuity": "high"}}

User: "i rolled my foot while jogging, ankle is swollen"
Output: {{"emergency_type": "sprain", "subtype": "ankle", "acuity": "low"}}

User: "my friend got stung by a bee and is having trouble breathing"
Output: {{"emergency_type": "allergic_reaction", "subtype": "severe", "acuity": "high"}}
"""

# ─────────────────────────────────────────────────────────────────────────────
# FALLBACK ADVICE PROMPT
# Used when no DB record matches — LLM generates safe first-aid advice.
# ─────────────────────────────────────────────────────────────────────────────
FALLBACK_SYSTEM = """You are a calm, professional AI First Aid Assistant providing guidance
for a situation not covered in our verified medical database.

Rules:
- If acuity is "high": your FIRST sentence must be exactly:
  "CALL 911 (OR YOUR LOCAL EMERGENCY NUMBER) IMMEDIATELY."
- Give clear, numbered first-aid steps (max 6 steps).
- Use plain language — no medical jargon.
- Be direct and reassuring.
- End with: "This is general guidance. Always seek professional medical care."
- Do NOT invent procedures you are not confident about. Say "keep the person calm and wait for help" if unsure.
- Very Important: ALWAYS reply in the exact language the user used to ask the question. If the user asks in Roman Urdu (e.g. "mery bhai ko heartattack..."), you MUST respond in Roman Urdu.
"""


# ─────────────────────────────────────────────────────────────────────────────
# FOLLOW-UP INTENT PROMPT
# Detects if a follow-up message is a question or a booking/availability request
# ─────────────────────────────────────────────────────────────────────────────
INTENT_SYSTEM = """You are an intent classifier for an AI first-aid chat assistant.

Given the user's message and optional conversation context, classify the intent into ONE of:
- "emergency"        → user is describing a new medical situation or asking first-aid advice
- "check_doctor"     → user wants to find/check availability of a doctor
- "book"             → user wants to book an appointment
- "confirm"          → user is confirming a previous action (yes / ok / confirm / proceed)
- "cancel"           → user is cancelling (no / cancel / stop)
- "followup"         → user is asking a follow-up medical question about the current topic
- "my_appointments"  → user wants to see their appointment history or past bookings
- "symptom_check"    → user wants a preliminary symptom assessment before deciding
- "nearest_hospital" → user is asking about nearby hospitals, clinics, or medical facilities

Respond ONLY with a JSON object:
{"intent": "one_of_the_above", "confidence": 0.0_to_1.0}
"""


def get_llm(temperature: float = 0.0):
    return ChatGroq(
        api_key=settings.GROQ_API_KEY,
        model_name=settings.GROQ_MODEL,
        temperature=temperature,
    )


def _extract_json(text: str) -> dict:
    """Robustly extract the full JSON object from LLM output."""
    # Strip markdown fences
    text = re.sub(r"```json|```", "", text).strip()
    # Find the outer-most balanced curly braces
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        json_str = text[start:end+1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # Fallback to the original text if slicing failed for some reason
            return json.loads(text)
    return json.loads(text)


async def classify_emergency(query: str) -> ClassificationResult:
    """
    Semantically classify a free-text emergency query into a structured
    (emergency_type, subtype, acuity) triple using the Groq LLM.

    The LLM is given the full DB catalogue so it maps to real entries
    rather than inventing its own type names.
    """
    llm = get_llm(temperature=0.0)
    messages = [
        SystemMessage(content=CLASSIFICATION_SYSTEM),
        HumanMessage(content=f"User message: {query}"),
    ]
    try:
        response = await llm.ainvoke(messages)
        data = _extract_json(response.content)
    except Exception as e:
        print(f"Classification failed: {str(e)}")
        data = {"emergency_type": "unknown", "subtype": None, "acuity": "low", "language": "english"}

    # Normalise: snake_case type, lowercase subtype, strip None strings
    data["emergency_type"] = data.get("emergency_type", "unknown")
    if data["emergency_type"] is None:
        data["emergency_type"] = "unknown"
    data["emergency_type"] = data["emergency_type"].lower().replace(" ", "_")
    
    subtype = data.get("subtype")
    data["subtype"] = subtype.lower() if subtype and subtype not in ("null", "none", "") else None
    
    acuity = data.get("acuity", "low")
    data["acuity"] = acuity.lower() if acuity else "low"
    
    language = data.get("language", "english")
    data["language"] = language.lower() if language else "english"

    return ClassificationResult(**data)


async def classify_intent(message: str, context: str = "") -> dict:
    """
    Classify whether a follow-up message is a new emergency, a doctor check,
    a booking request, or a follow-up question.
    """
    llm = get_llm(temperature=0.0)
    prompt = f"Context: {context}\nUser message: {message}" if context else f"User message: {message}"
    messages = [
        SystemMessage(content=INTENT_SYSTEM),
        HumanMessage(content=prompt),
    ]
    try:
        response = await llm.ainvoke(messages)
        return _extract_json(response.content)
    except Exception as e:
        print(f"Intent classification failed: {str(e)}")
        return {"intent": "emergency", "confidence": 0.5}


async def generate_fallback_advice(query: str, acuity: str) -> str:
    """
    Generate first-aid advice using LLM when no DB record matches.
    Used as a safe fallback with appropriate disclaimers.
    """
    llm = get_llm(temperature=0.1)
    prompt = f"Acuity: {acuity}\nSituation: {query}"
    messages = [
        SystemMessage(content=FALLBACK_SYSTEM),
        HumanMessage(content=prompt),
    ]
    try:
        response = await llm.ainvoke(messages)
        return response.content.strip()
    except Exception as e:
        print(f"Fallback generation failed: {str(e)}")
        return "I am currently unable to analyze this situation due to an AI processing issue. Please call emergency services if this is urgent."


async def answer_followup(question: str, emergency_context: str) -> str:
    """
    Answer a follow-up medical question in the context of the current emergency.
    """
    llm = get_llm(temperature=0.2)
    system = """You are an AI first-aid assistant. The user is asking a follow-up question
about a medical emergency that is already being handled. Answer clearly and concisely.
Use plain language. If you are unsure, say so and advise the user to consult a professional.
End with a reminder to keep emergency services involved if the situation is serious.
- Very Important: ALWAYS reply in the exact language the user used to ask the question. If the user asks in Roman Urdu (e.g. "mery bhai ko heartattack..."), you MUST respond in Roman Urdu."""

    prompt = f"Emergency context: {emergency_context}\n\nFollow-up question: {question}"
    messages = [
        SystemMessage(content=system),
        HumanMessage(content=prompt),
    ]
    try:
        response = await llm.ainvoke(messages)
        return response.content.strip()
    except Exception as e:
        print(f"Follow up answering failed: {str(e)}")
        return "I am currently unable to provide a response due to an AI processing issue. Please consult a medical professional."


TRANSLATE_SYSTEM = """You are a medical translator. Translate the given medical emergency information into the target language.

RULES:
1. Keep the JSON structure exactly as provided.
2. Only translate the values for "type", "subtype", "instruction", and "notes".
3. Keep "step_number" as is.
4. If the target language is "roman urdu", use clear, common Roman Urdu (e.g., "dil ka dora" for cardiac arrest, "sakht khoon nikalna" for severe bleeding).

Output ONLY a JSON object:
{"type": "...", "subtype": "...", "steps": [{"step_number": 1, "instruction": "..."}], "notes": "..."}"""

async def translate_db_record(
    type_name: str,
    subtype_name: Optional[str],
    steps_dicts: list,
    notes: str,
    target_language: str
) -> dict:
    """
    Translates a full DB record (Title, Subtype, Steps, Notes) into the target language.
    """
    if target_language == "english":
        return {
            "type": type_name,
            "subtype": subtype_name,
            "steps": steps_dicts,
            "notes": notes
        }

    llm = get_llm(temperature=0.0)
    import json
    payload = {
        "type": type_name,
        "subtype": subtype_name,
        "steps": steps_dicts,
        "notes": notes
    }
    prompt = f"Target language: {target_language}\nData to translate: {json.dumps(payload)}"
    
    messages = [
        SystemMessage(content=TRANSLATE_SYSTEM),
        HumanMessage(content=prompt),
    ]
    try:
        response = await llm.ainvoke(messages)
        data = _extract_json(response.content)
        return data
    except Exception as e:
        print(f"Translation failed: {str(e)}")
        return {
            "type": type_name,
            "subtype": subtype_name,
            "steps": steps_dicts,
            "notes": notes
        }