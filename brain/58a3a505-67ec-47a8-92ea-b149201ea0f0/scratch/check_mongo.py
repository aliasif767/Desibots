import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os

async def check_db():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["firstaid_db"]
    
    # Check all collections
    collections = await db.list_collection_names()
    print(f"Collections in firstaid_db: {collections}")
    
    for coll_name in collections:
        count = await db[coll_name].count_documents({})
        print(f"Collection {coll_name} has {count} documents.")
        if count > 0:
            docs = await db[coll_name].find().to_list(1)
            print(f"Sample from {coll_name}: {docs[0]}")

    # Also check tenant DBs
    all_dbs = await client.list_database_names()
    tenant_dbs = [d for d in all_dbs if d.startswith("firstaid_db_")]
    print(f"Tenant DBs: {tenant_dbs}")
    
    for t_db_name in tenant_dbs:
        t_db = client[t_db_name]
        t_colls = await t_db.list_collection_names()
        print(f"Collections in {t_db_name}: {t_colls}")
        for c in t_colls:
            cnt = await t_db[c].count_documents({})
            print(f"  {c}: {cnt}")

if __name__ == "__main__":
    asyncio.run(check_db())
