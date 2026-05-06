import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")

async def search():
    client = AsyncIOMotorClient(MONGO_URI)
    dbs = await client.list_database_names()
    
    for db_name in dbs:
        if db_name.startswith("pakorderbot_db"):
            db = client[db_name]
            cols = await db.list_collection_names()
            if "feedback" in cols:
                count = await db["feedback"].count_documents({})
                print(f"Found 'feedback' in {db_name} with {count} records.")
                if count > 0:
                    sample = await db["feedback"].find().limit(1).to_list(1)
                    print(f"  Sample: {sample}")
            if "offers" in cols:
                count = await db["offers"].count_documents({})
                print(f"Found 'offers' in {db_name} with {count} records.")

    client.close()

if __name__ == "__main__":
    asyncio.run(search())
