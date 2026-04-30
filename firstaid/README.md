# AI First Aid & Medical Scheduling Assistant

A full-stack application providing AI-powered emergency first aid guidance with real-time doctor appointment booking.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI + Uvicorn |
| AI / LLM | Groq API (LLaMA 3 70B) via LangChain |
| Database | MongoDB + Motor (async) |
| Frontend | Streamlit 1.35 |
| Containerization | Docker + Docker Compose |

---

## Project Structure

```
firstaid-project/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app entry point
│   │   ├── config.py            # Settings / env vars
│   │   ├── api/
│   │   │   └── routes.py        # API endpoints
│   │   ├── agents/
│   │   │   └── classifier.py    # Groq LLM classification + fallback
│   │   ├── db/
│   │   │   └── mongo.py         # MongoDB connection + DB seeding
│   │   ├── models/
│   │   │   └── schemas.py       # Pydantic request/response models
│   │   └── services/
│   │       ├── firstaid.py      # Main orchestration service
│   │       └── scheduling.py    # Doctor booking service
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── streamlit_app.py         # Streamlit frontend (single file)
├── requirements-streamlit.txt
├── Dockerfile.streamlit
├── .streamlit/
│   └── config.toml          # Theme + server settings
├── docker-compose.yml
└── README.md
```

---

## Quick Start

### Option A — Docker Compose (recommended)

```bash
# 1. Clone and enter project
cd firstaid-project

# 2. Set your Groq API key
echo "GROQ_API_KEY=your_key_here" > .env

# 3. Start everything
docker-compose up --build

# App available at:
# Streamlit UI → http://localhost:8501
# Backend API  → http://localhost:8000
# API docs     → http://localhost:8000/docs
```

### Option B — Manual Setup

**Backend**
```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and set your GROQ_API_KEY

# Start MongoDB (make sure it's running locally on port 27017)

# Run the API server
uvicorn app.main:app --reload --port 8000
```

**Streamlit frontend**
```bash
# From the project root
pip install -r requirements-streamlit.txt

# Make sure backend is running, then:
streamlit run streamlit_app.py
# → http://localhost:8501
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/emergency` | Assess emergency + get first aid + book doctor |
| POST | `/api/v1/book` | Directly book a doctor appointment |
| GET | `/api/v1/firstaid` | List all verified first aid records |
| GET | `/api/v1/firstaid/{type}` | Get first aid record by type |
| GET | `/health` | Health check |

### Example request

```bash
curl -X POST http://localhost:8000/api/v1/emergency \
  -H "Content-Type: application/json" \
  -d '{"query": "my toddler is choking"}'
```

### Example response (high acuity)

```json
{
  "source": "database",
  "emergency_type": "Choking",
  "subtype": "Infant",
  "acuity": "high",
  "steps": [
    { "step_number": 1, "instruction": "Place the baby face-down along your forearm..." },
    { "step_number": 2, "instruction": "Give 5 firm back blows..." }
  ],
  "image": "/images/choking/infant.png",
  "medical_followup": {
    "doctor_name": "Dr. Sarah Chen (Pediatrician)",
    "availability": "Available Now",
    "appointment_status": "Confirmed",
    "appointment_time": "2026-04-06T14:30:00",
    "location": "City General Hospital — 0.8 miles away"
  },
  "notes": "CALL 911 (OR YOUR LOCAL EMERGENCY NUMBER) IMMEDIATELY if the infant loses consciousness..."
}
```

---

## Agent Workflow

```
User Query
    │
    ▼
[1] LLM Classifier (Groq)
    → emergency_type, subtype, acuity
    │
    ▼
[2] MongoDB Lookup
    ├── Found  → verified steps + image (source: database)
    └── Not found → LLM fallback advice (source: llm)
    │
    ▼
[3] Doctor Scheduling
    → check availability → provisional booking
    │
    ▼
[4] Structured JSON Response
    → Frontend renders result card
```

---

## Acuity Rules

| Level | Conditions | Behavior |
|---|---|---|
| **High** | Choking, cardiac arrest, heavy bleeding, stroke, unconscious, severe allergic reaction | Red emergency banner + inline 911 reminder + emergency specialist booking |
| **Low** | Minor burns, sprains, bee stings, rashes, cuts | Standard guidance + GP or specialist booking |

---

## Getting a Groq API Key

1. Go to [https://console.groq.com](https://console.groq.com)
2. Sign up for a free account
3. Generate an API key
4. Add it to your `.env` file: `GROQ_API_KEY=your_key_here`

---

## Extending the Database

Add new first aid records to MongoDB using the structure:

```python
{
    "type": "fracture",
    "subtype": "wrist",
    "acuity": "low",
    "steps": [
        {"step_number": 1, "instruction": "Immobilize the wrist..."},
    ],
    "image": "/images/fracture/wrist.png",
    "notes": "Seek medical care promptly."
}
```

---

## Disclaimer

This application is for informational and educational purposes only. It is not a substitute for professional medical advice, diagnosis, or treatment. Always call emergency services (911/112) for life-threatening situations.
