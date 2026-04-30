import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from agent.auth import hash_password
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017")
client = AsyncIOMotorClient(MONGO_URI)

async def seed():
    print("🚀 PakOrderBot Staff Seeder")
    tenant_id = input("Enter Tenant ID (e.g., Asif): ").strip()
    username  = input("Enter Staff Username: ").strip()
    password  = input("Enter Staff Password: ").strip()

    if not tenant_id or not username or not password:
        print("❌ All fields are required!")
        return

    db_name = f"pakorderbot_db_{tenant_id}"
    db = client[db_name]

    # Check if exists
    existing = await db["staff"].find_one({"username": username})
    if existing:
        print(f"⚠️ Staff '{username}' already exists in {db_name}. Updating password...")
        await db["staff"].update_one(
            {"username": username}, 
            {"$set": {"password_hash": hash_password(password)}}
        )
    else:
        await db["staff"].insert_one({
            "username": username,
            "password_hash": hash_password(password),
            "role": "staff"
        })
        print(f"✅ Created staff account: {username}")

    print(f"✨ Seeded database: {db_name}")

if __name__ == "__main__":
    asyncio.run(seed())
