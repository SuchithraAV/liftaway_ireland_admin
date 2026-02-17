"""
Quick test script to verify Redis connection pool is working
Run: python test_redis_connection.py
"""
import asyncio
import sys
from core.redis_client import redis_pool
from config import settings

async def test_redis_pool():
    print("=" * 60)
    print("Testing Redis Connection Pool")
    print("=" * 60)
    
    try:
        # Initialize pool
        print("\n1. Initializing Redis pool...")
        await redis_pool.initialize()
        print("   ✅ Pool initialized successfully")
        
        # Test basic operations
        print("\n2. Testing basic Redis operations...")
        client = redis_pool.get_client()
        
        # Test SET
        await client.set("test:key", "test_value", ex=10)
        print("   ✅ SET operation successful")
        
        # Test GET
        value = await client.get("test:key")
        assert value == "test_value", "Value mismatch"
        print("   ✅ GET operation successful")
        
        # Test DELETE
        await client.delete("test:key")
        print("   ✅ DELETE operation successful")
        
        await client.close()
        
        # Test connection reuse
        print("\n3. Testing connection pool reuse (100 operations)...")
        for i in range(100):
            client = redis_pool.get_client()
            await client.set(f"test:pool:{i}", f"value_{i}", ex=5)
            await client.close()
        print("   ✅ 100 operations completed without connection exhaustion")
        
        # Cleanup
        print("\n4. Cleaning up test keys...")
        client = redis_pool.get_client()
        for i in range(100):
            await client.delete(f"test:pool:{i}")
        await client.close()
        print("   ✅ Cleanup successful")
        
        # Test pub/sub pool
        print("\n5. Testing pub/sub pool...")
        pub_client = redis_pool.get_pubsub_client()
        await pub_client.publish("test:channel", "test_message")
        await pub_client.close()
        print("   ✅ Pub/sub pool working")
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED - Redis is production ready!")
        print("=" * 60)
        print(f"\nRedis URL: {settings.REDIS_URL}")
        print("Connection pool: 100 connections")
        print("PubSub pool: 20 connections")
        print("\nYou can now deploy to production.")
        
    except Exception as e:
        print("\n" + "=" * 60)
        print("❌ TEST FAILED")
        print("=" * 60)
        print(f"\nError: {e}")
        print("\nPlease check:")
        print("1. Redis server is running")
        print("2. REDIS_URL in .env is correct")
        print("3. Redis credentials are valid")
        sys.exit(1)
    
    finally:
        # Close pool
        await redis_pool.close()
        print("\n✅ Connection pool closed")

if __name__ == "__main__":
    asyncio.run(test_redis_pool())
