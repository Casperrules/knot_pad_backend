"""
Database initialization script
Ensures database, collections, and indexes exist
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from config import get_settings

settings = get_settings()


async def init_database():
    """Initialize database with collections and indexes"""
    print("🔄 Connecting to MongoDB...")
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client[settings.database_name]
    
    try:
        # Test connection
        await client.admin.command('ping')
        print("✅ Connected to MongoDB successfully")
        
        # Get list of existing collections
        existing_collections = await db.list_collection_names()
        print(f"📋 Existing collections: {existing_collections}")
        
        # Define collections needed
        required_collections = {
            "users": {
                "indexes": [
                    ("username", 1, {"unique": True}),
                    ("created_at", -1),
                ]
            },
            "stories": {
                "indexes": [
                    ("author_id", 1),
                    ("status", 1),
                    ("created_at", -1),
                    ("published_at", -1),
                    ("tags", 1),
                ]
            },
            "refresh_tokens": {
                "indexes": [
                    ("username", 1),
                    ("token", 1, {"unique": True}),
                    ("expires_at", 1),
                    ("last_used_at", -1),
                ]
            }
        }
        
        # Create collections and indexes
        for collection_name, config in required_collections.items():
            if collection_name not in existing_collections:
                print(f"📦 Creating collection: {collection_name}")
                await db.create_collection(collection_name)
            else:
                print(f"✓ Collection exists: {collection_name}")
            
            # Create indexes
            collection = db[collection_name]
            print(f"🔧 Setting up indexes for {collection_name}...")
            
            for index_config in config["indexes"]:
                field = index_config[0]
                direction = index_config[1]
                options = index_config[2] if len(index_config) > 2 else {}
                
                try:
                    await collection.create_index(
                        [(field, direction)],
                        **options
                    )
                    print(f"  ✓ Index created: {field}")
                except Exception as e:
                    if "already exists" in str(e).lower():
                        print(f"  ✓ Index exists: {field}")
                    else:
                        print(f"  ⚠ Index warning for {field}: {e}")
        
        # Check if admin user exists
        admin_user = await db.users.find_one({"username": settings.admin_username})
        if not admin_user:
            print(f"👤 Admin user '{settings.admin_username}' will be created on first app startup")
        else:
            print(f"✓ Admin user exists: {settings.admin_username}")
        
        print("\n✅ Database initialization complete!")
        print(f"📊 Database: {settings.database_name}")
        print(f"📦 Collections: {', '.join(required_collections.keys())}")
        
    except Exception as e:
        print(f"❌ Error during initialization: {e}")
        raise
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(init_database())
