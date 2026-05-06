import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")

async def cleanup_all():
    client = AsyncIOMotorClient(MONGO_URI)
    dbs = await client.list_database_names()
    
    for db_name in dbs:
        if db_name.startswith("pakorderbot_db"):
            db = client[db_name]
            cols = await db.list_collection_names()
            if "feedback" in cols:
                print(f"Cleaning up feedback in {db_name}...")
                result = await db["feedback"].update_many(
                    {"customer_name": "mehman"},
                    {"$set": {"customer_name": "Anonymous Guest"}}
                )
                print(f"  Matched {result.matched_count}, Modified {result.modified_count}")

    client.close()
    print("Done!")

if __name__ == "__main__":
    asyncio.run(cleanup_all())
