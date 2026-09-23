"""
mongo_db.py — Async MongoDB connection via Beanie + Motor.
Called during FastAPI startup to initialise the connection to Atlas.
"""
import os
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from dotenv import load_dotenv

load_dotenv()

_client: AsyncIOMotorClient | None = None


async def init_mongo(document_models: list):
    """Connect to MongoDB Atlas and initialise Beanie with the given document models."""
    global _client
    

    mongo_uri = os.environ.get("MONGO_URI", "mongodb://127.0.0.1:27017/feedtoread")
    _client = AsyncIOMotorClient(mongo_uri)

    # Extract the database name from the URI
    try:
        db_name = mongo_uri.split("/")[-1].split("?")[0] or "feedtoread"
    except Exception:
        db_name = "feedtoread"

    if not db_name:
        db_name = "feedtoread"

    await init_beanie(database=_client[db_name], document_models=document_models)
    print(f"[MongoDB] Connected to Atlas — database: '{db_name}'")


async def close_mongo():
    """Gracefully close the MongoDB connection."""
    global _client
    if _client:
        _client.close()
        print("[MongoDB] Connection closed.")
