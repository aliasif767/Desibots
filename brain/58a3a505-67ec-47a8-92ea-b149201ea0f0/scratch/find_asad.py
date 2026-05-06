import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def find_asad():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    all_dbs = await client.list_database_names()
    tenant_dbs = [d for d in all_dbs if d.startswith("firstaid_db_")]
    
    for db_name in tenant_dbs:
        db = client[db_name]
        colls = await db.list_collection_names()
        if 'doctors' in colls:
            docs = await db.doctors.find({"doctor_name": {"$regex": "Asad", "$options": "i"}}).to_list(10)
            if docs:
                print(f"Found in {db_name}:")
                for d in docs:
                    print(f"  {d['doctor_name']} (Keys: {d.get('specialty_keys')})")

if __name__ == "__main__":
    asyncio.run(find_asad())
