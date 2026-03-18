import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
client = AsyncIOMotorClient(MONGO_URI)
db = client.hisabbot_db

# Collections
inventory_col  = db.get_collection("inventory")   # {product, qty, price_per_unit, low_stock_threshold}
sales_col      = db.get_collection("sales")        # {customer, product, qty, unit_price, total, date}
customers_col  = db.get_collection("customers")    # {name, phone, address, total_credit, last_seen}
finance_col    = db.get_collection("finance")      # {customer, amount, type: 'invoice'/'payment', date}