import os
from pymongo import MongoClient
from bson import ObjectId

# Database Configuration
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = "pakorderbot_db_default"  # Default tenant database

def seed_custom_menu():
    print(f"Connecting to MongoDB at {MONGO_URI}...")
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    menu_collection = db["menu"]

    items = [
        {
            "_id": ObjectId("69c37b5c9ebb62c8951b1f45"),
            "name": "gulab jamun",
            "category": "dessert",
            "price": 60,
            "available": True,
            "description": "Soft milk dumplings in sugar syrup",
            "prep_time": 5
        },
        {
            "_id": ObjectId("69c37b5c9ebb62c8951b1f46"),
            "name": "kheer",
            "category": "dessert",
            "price": 70,
            "available": True,
            "description": "Creamy rice pudding",
            "prep_time": 5
        },
        {
            "_id": ObjectId("69c37b5c9ebb62c8951b1f47"),
            "name": "ice cream",
            "category": "dessert",
            "price": 65,
            "available": True,
            "description": "Vanilla / chocolate scoop",
            "prep_time": 2
        },
        {
            "_id": ObjectId("69c392b1c875b6792f0c0073"),
            "name": "jalebe",
            "category": "dessert",
            "price": 80,
            "available": True,
            "description": "Crispy fried batter soaked in sweet syrup",
            "prep_time": 10
        },
        {
            "_id": ObjectId("69ca0592c875b6792f0c0080"),
            "name": "paratay",
            "category": "side",
            "price": 45,
            "available": True,
            "description": "soft",
            "prep_time": 20
        },
        {
            "_id": ObjectId("69cbad64c875b6792f0c0091"),
            "name": "sohan khalva",
            "category": "dessert",
            "price": 170,
            "available": True,
            "description": "Traditional sohan khalva",
            "prep_time": 20
        }
    ]

    print(f"Upserting {len(items)} items into {DB_NAME}.menu...")
    
    for item in items:
        # Using update_one with upsert=True to avoid duplicates and update existing ones
        menu_collection.update_one(
            {"_id": item["_id"]},
            {"$set": item},
            upsert=True
        )

    print("Seeding completed successfully!")
    client.close()

if __name__ == "__main__":
    try:
        seed_custom_menu()
    except Exception as e:
        print(f"Error seeding menu: {e}")
