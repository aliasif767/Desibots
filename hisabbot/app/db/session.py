import os
import contextvars
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
client = AsyncIOMotorClient(MONGO_URI)

# Use contextvars so agent code doesn't need tenant_id passed everywhere
tenant_var = contextvars.ContextVar("tenant", default="default")

def get_db():
    tenant_id = tenant_var.get()
    return client[f"hisabbot_{tenant_id}"]