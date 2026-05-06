import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = "pakorderbot_db_default"

async def cleanup():
    print(f"Connecting to {MONGO_URI}...")
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    col = db["feedback"]

    # Update all 'mehman' to 'Anonymous Guest'
    print("Updating 'mehman' feedback entries...")
    result = await col.update_many(
        {"customer_name": "mehman"},
        {"$set": {"customer_name": "Anonymous Guest"}}
    )
    
    print(f"Matched {result.matched_count} documents.")
    print(f"Modified {result.modified_count} documents.")
    
    client.close()
    print("Done!")

if __name__ == "__main__":
    asyncio.run(cleanup())
