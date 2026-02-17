"""
Test Database Connection

Run this BEFORE encryption to verify database is accessible.
"""

import asyncio
from core.database import AsyncSessionLocal
from sqlalchemy import text

async def test_connection():
    print("Testing database connection...")
    
    try:
        async with AsyncSessionLocal() as db:
            # Simple query to test connection
            result = await db.execute(text("SELECT 1"))
            print("✅ Database connection successful!")
            return True
    
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("\nPossible solutions for CLOUD database:")
        print("1. Check .env file has correct DATABASE_URL")
        print("2. Verify cloud database is running (check cloud provider dashboard)")
        print("3. Check firewall/security group allows your IP")
        print("4. Verify SSL settings if required")
        print("5. Check database credentials are correct")
        return False

if __name__ == "__main__":
    asyncio.run(test_connection())
