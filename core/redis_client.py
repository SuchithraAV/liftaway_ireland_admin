import redis.asyncio as redis
from config import settings
import logging

logger = logging.getLogger(__name__)

class RedisPool:
    def __init__(self):
        self.pool = None
        self.pubsub_pool = None
    
    async def initialize(self):
        """Initialize Redis connection pools"""
        try:
            self.pool = redis.ConnectionPool.from_url(
                settings.REDIS_URL,
                max_connections=500,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30
            )
            
            self.pubsub_pool = redis.ConnectionPool.from_url(
                settings.REDIS_URL,
                max_connections=50,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
                retry_on_timeout=True
            )
            
            # Test connection and fix MISCONF error
            client = self.get_client()
            try:
                await client.ping()
                logger.info("Redis connection pool initialized successfully")
            except redis.ResponseError as e:
                if "MISCONF" in str(e):
                    logger.warning("Redis MISCONF error detected, attempting auto-fix...")
                    try:
                        await client.config_set("stop-writes-on-bgsave-error", "no")
                        await client.ping()
                        logger.info("Redis MISCONF error fixed automatically")
                    except Exception as fix_error:
                        logger.error(f"Failed to auto-fix Redis: {fix_error}")
                        logger.error("Run: redis-cli CONFIG SET stop-writes-on-bgsave-error no")
                        raise
                else:
                    raise
            finally:
                await client.close()
        except Exception as e:
            logger.error(f"Failed to initialize Redis pool: {e}")
            logger.error("See FIX_REDIS_ERROR.md for solutions")
            raise
    
    def get_client(self) -> redis.Redis:
        """Get Redis client from pool"""
        if not self.pool:
            raise RuntimeError("Redis pool not initialized")
        return redis.Redis(connection_pool=self.pool)
    
    def get_pubsub_client(self) -> redis.Redis:
        """Get Redis client for pub/sub from separate pool"""
        if not self.pubsub_pool:
            raise RuntimeError("Redis pubsub pool not initialized")
        return redis.Redis(connection_pool=self.pubsub_pool)
    
    async def close(self):
        """Close all Redis connections"""
        try:
            if self.pool:
                await self.pool.disconnect()
            if self.pubsub_pool:
                await self.pubsub_pool.disconnect()
            logger.info("Redis pools closed")
        except Exception as e:
            logger.error(f"Error closing Redis pools: {e}")

redis_pool = RedisPool()
