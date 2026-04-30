from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from app.api.routes import router
from app.api.staff_routes import router as staff_router
from app.db.mongo import connect_db, close_db

app = FastAPI(
    title="AI First Aid & Medical Scheduling API",
    description="Emergency first aid guidance with doctor booking integration",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_event_handler("startup", connect_db)
app.add_event_handler("shutdown", close_db)

app.include_router(router, prefix="/api/v1")
app.include_router(staff_router, prefix="/staff")

# main.py lives in backend/app/ — images/ is right next to it
IMAGES_DIR = Path(__file__).resolve().parent / "images"
print(f"Serving images from: {IMAGES_DIR}")

app.mount("/images", StaticFiles(directory=str(IMAGES_DIR)), name="images")

@app.get("/health")
async def health():
    return {"status": "ok", "service": "AI First Aid Assistant", "version": "2.0.0"}