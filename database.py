from motor.motor_asyncio import AsyncIOMotorClient
from config import get_settings

settings = get_settings()

class Database:
    client: AsyncIOMotorClient = None
    
db = Database()

async def get_database():
    return db.client[settings.database_name]

async def connect_to_mongo():
    """Connect to MongoDB and initialize database structure"""
    db.client = AsyncIOMotorClient(settings.mongodb_url)
    print(f"🔄 Connecting to MongoDB...")
    
    # Test connection
    try:
        await db.client.admin.command('ping')
        print(f"✅ Connected to MongoDB successfully")
    except Exception as e:
        print(f"❌ Failed to connect to MongoDB: {e}")
        raise
    
    # Get database
    database = db.client[settings.database_name]
    
    # Ensure collections exist by checking and creating if needed
    existing_collections = await database.list_collection_names()
    
    required_collections = ["users", "stories", "refresh_tokens"]
    for collection_name in required_collections:
        if collection_name not in existing_collections:
            await database.create_collection(collection_name)
            print(f"📦 Created collection: {collection_name}")
    
    # Create indexes for better performance
    try:
        # Users indexes
        await database.users.create_index("username", unique=True)
        
        # Stories indexes
        await database.stories.create_index("author_id")
        await database.stories.create_index("status")
        await database.stories.create_index([("published_at", -1)])
        
        # Refresh tokens indexes
        await database.refresh_tokens.create_index("username")
        await database.refresh_tokens.create_index("token", unique=True)
        
        print(f"✅ Database '{settings.database_name}' initialized with collections and indexes")
    except Exception as e:
        # Indexes might already exist, that's okay
        print(f"ℹ️ Indexes setup: {e}")

async def close_mongo_connection():
    db.client.close()
    print("🔌 Closed MongoDB connection")
