from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings
import uuid
from datetime import datetime

class Database:
    client: AsyncIOMotorClient = None
    db = None

db_instance = Database()

async def connect_db():
    db_instance.client = AsyncIOMotorClient(settings.MONGODB_URL)
    db_instance.db = db_instance.client[settings.MONGODB_DB]
    await seed_database()
    # Import here to avoid circular import
    from app.services.scheduling import seed_doctors
    await seed_doctors()
    print(f"Connected to MongoDB: {settings.MONGODB_DB}")

async def close_db():
    if db_instance.client:
        db_instance.client.close()
        print("MongoDB connection closed")

def get_db():
    return db_instance.db

def get_user_db(tenant_id: str = "default"):
    safe_tenant = str(tenant_id).replace(".", "_").replace("@", "_").replace(" ", "_")
    return db_instance.client[f"{settings.MONGODB_DB}_{safe_tenant}"]

def generate_doctor_id():
    """Generate a unique doctor ID."""
    return f"doc_{uuid.uuid4().hex[:8]}"

async def seed_database():
    """Seed initial first aid records if collection is empty."""
    db = db_instance.db
    count = await db.firstaid.count_documents({})
    if count > 0:
        return

    records = [
        {
            "type": "choking",
            "subtype": "infant",
            "acuity": "high",
            "steps": [
                {"step_number": 1, "instruction": "Place the baby face-down along your forearm, supporting the head."},
                {"step_number": 2, "instruction": "Give 5 firm back blows between the shoulder blades with the heel of your hand."},
                {"step_number": 3, "instruction": "Turn baby face-up on your other forearm, supporting the head lower than the chest."},
                {"step_number": 4, "instruction": "Give 5 gentle chest thrusts using two fingers on the center of the chest."},
                {"step_number": 5, "instruction": "Repeat back blows and chest thrusts until object is expelled or baby loses consciousness."},
            ],
            "image": "/images/choking/infant.jpeg",
            "notes": "CALL 911 (OR YOUR LOCAL EMERGENCY NUMBER) IMMEDIATELY if the infant loses consciousness or object is not expelled within 1 minute."
        },
        {
    "type": "choking",
    "subtype": "wheelchair",
    "acuity": "high",
    "steps": [
      {"step_number": 1, "instruction": "Position the wheelchair against a wall and lock the brakes."},
      {"step_number": 2, "instruction": "If possible, lean the casualty forward and give 5 back blows between the shoulder blades."},
      {"step_number": 3, "instruction": "Give 5 abdominal thrusts (or chest thrusts if necessary) using correct hand placement."},
      {"step_number": 4, "instruction": "Repeat back blows and thrusts until the object is expelled or casualty becomes unconscious."}
    ],
    "image": "/images/choking/wheelchair.jpeg",
    "notes": "CALL 911 if the object is not expelled or the casualty becomes unconscious. Remove the casualty from wheelchair if needed for CPR."
  }, {
    "type": "choking",
    "subtype": "large_or_pregnant",
    "acuity": "high",
    "steps": [
      {"step_number": 1, "instruction": "Give 5 back blows between the shoulder blades using the heel of your hand."},
      {"step_number": 2, "instruction": "Place your fist on the lower half of the breastbone and perform chest thrusts."},
      {"step_number": 3, "instruction": "Repeat back blows and chest thrusts until the object is expelled or casualty becomes unconscious."}
    ],
    "image": "/images/choking/large_or_pregnant.jpeg",
    "notes": "CALL 911 immediately if the object is not expelled or the casualty becomes unconscious."
  },
        {
            "type": "choking",
            "subtype": "adult",
            "acuity": "high",
            "steps": [
                {"step_number": 1, "instruction": "Ask 'Are you choking?' — if they cannot speak, cough, or breathe, act immediately."},
                {"step_number": 2, "instruction": "Stand behind the person and wrap your arms around their waist."},
                {"step_number": 3, "instruction": "Make a fist and place it just above the navel, below the ribcage."},
                {"step_number": 4, "instruction": "Grasp your fist with the other hand and deliver 5 sharp upward thrusts (Heimlich maneuver)."},
                {"step_number": 5, "instruction": "Repeat until the object is expelled or the person becomes unconscious."},
            ],
            "image": "/images/choking/adult.jpeg",
            "notes": "CALL 911 (OR YOUR LOCAL EMERGENCY NUMBER) IMMEDIATELY. If unconscious, begin CPR."
        },
        # ================= HEART ATTACK =================
    {
        "type": "cardiac_arrest",
        "subtype": "adult",
        "acuity": "high",
        "symptoms": [
            "chest pain",
            "shortness of breath",
            "pain in arm/jaw",
            "sweating",
            "nausea"
        ],
        "steps": [
            {"step_number": 1, "instruction": "Ask where the pain is and if they had it before."},
            {"step_number": 2, "instruction": "Call emergency services (1122)."},
            {"step_number": 3, "instruction": "Keep person in semi-sitting position and calm."},
            {"step_number": 4, "instruction": "Assist with prescribed nitroglycerin if available."},
            {"step_number": 5, "instruction": "Give aspirin (if no allergy) and let them chew it."},
            {"step_number": 6, "instruction": "Monitor breathing and condition."},
            {"step_number": 7, "instruction": "If unconscious and not breathing, start CPR."}
        ],
        "donts": [
            "Do not leave the person alone",
            "Do not allow walking",
            "Do not delay emergency call"
        ],
        "image": "/images/heart_attack.jpeg",
        "notes": "This is life-threatening. Act immediately."
    },

    # ================= BLEEDING =================
    {
        "type": "bleeding",
        "subtype": "external",
        "acuity": "high",
        "symptoms": [
            "visible blood",
            "continuous bleeding",
            "deep wound"
        ],
        "steps": [
            {"step_number": 1, "instruction": "Ensure safety and wear gloves if possible."},
            {"step_number": 2, "instruction": "Apply firm direct pressure using cloth or bandage."},
            {"step_number": 3, "instruction": "Keep pressure steady until bleeding slows."},
            {"step_number": 4, "instruction": "Elevate injured area if no fracture suspected."},
            {"step_number": 5, "instruction": "Apply bandage and do not remove soaked layers."},
            {"step_number": 6, "instruction": "Call emergency if bleeding is severe."}
        ],
        "donts": [
            "Do not remove deeply embedded objects",
            "Do not use dirty cloth",
            "Do not stop pressure too early"
        ],
        "image": "/images/bleeding.jpeg",
        "notes": "Severe bleeding can lead to shock quickly."
    },

    # ================= BURNS =================
    {
        "type": "burn",
        "subtype": "thermal",
        "acuity": "medium",
        "symptoms": [
            "red skin",
            "blisters",
            "pain",
            "charred skin"
        ],
        "steps": [
            {"step_number": 1, "instruction": "Remove from heat source."},
            {"step_number": 2, "instruction": "Cool burn with running water for 20 minutes."},
            {"step_number": 3, "instruction": "Remove tight items like rings."},
            {"step_number": 4, "instruction": "Cover with sterile non-stick dressing."},
            {"step_number": 5, "instruction": "Seek medical help for severe burns."}
        ],
        "donts": [
            "Do not apply ice",
            "Do not apply oil or butter",
            "Do not burst blisters"
        ],
        "image": "/images/burn.jpeg",
        "notes": "Large or deep burns are medical emergencies."
    },

    # ================= FRACTURE =================
    {
        "type": "fracture",
        "subtype": "general",
        "acuity": "high",
        "symptoms": [
            "severe pain",
            "swelling",
            "deformity",
            "inability to move limb"
        ],
        "steps": [
            {"step_number": 1, "instruction": "Keep the person still and do not move unnecessarily."},
            {"step_number": 2, "instruction": "Immobilize the injured area."},
            {"step_number": 3, "instruction": "Apply splint to support limb."},
            {"step_number": 4, "instruction": "Control bleeding if present."},
            {"step_number": 5, "instruction": "Apply cold pack wrapped in cloth."},
            {"step_number": 6, "instruction": "Call emergency services for severe cases."}
        ],
        "donts": [
            "Do not try to realign bone",
            "Do not move injured limb",
            "Do not give food or drink"
        ],
        "image": "/images/fracture.jpeg",
        "notes": "Spinal injuries require extreme care."
    }
        
    ]

    await db.firstaid.insert_many(records)
    print(f"Seeded {len(records)} first aid records.")