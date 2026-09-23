import asyncio
from beanie import init_beanie, PydanticObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from db.mongo_models import Source
import os
from dotenv import load_dotenv

load_dotenv()

async def main():
    client = AsyncIOMotorClient(os.getenv('MONGO_URI'), tlsAllowInvalidCertificates=True)
    await init_beanie(database=client.feedtoread, document_models=[Source])
    source = Source(userId=PydanticObjectId(), sourceName='Marques Brownlee', sourceType='YOUTUBE', isActive=True)
    await source.insert()
    print('Inserted Marques Brownlee')

asyncio.run(main())
