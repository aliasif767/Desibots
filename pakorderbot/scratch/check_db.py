import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")

async def check():
    client = AsyncIOMotorClient(MONGO_URI)
    dbs = await client.list_database_names()
    print(f"Databases: {dbs}")
    
    # Try to find pakorderbot_db_default
    target_db = "pakorderbot_db_default"
    if target_db in dbs:
        db = client[target_db]
        cols = await db.list_collection_names()
        print(f"Collections in {target_db}: {cols}")
        if "feedback" in cols:
            sample = await db["feedback"].find().limit(5).to_list(5)
            print(f"Sample feedback: {sample}")
    else:
        print(f"{target_db} not found.")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(check())
