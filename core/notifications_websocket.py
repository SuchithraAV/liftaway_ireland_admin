from fastapi import WebSocket
from typing import Dict, List
import json
import logging
import asyncio
from datetime import datetime
import redis.asyncio as redis
from config import settings
from core.redis_client import redis_pool

logger = logging.getLogger(__name__)


class NotificationsConnectionManager:
    """
    Manages WebSocket connections for live notifications with Redis pub/sub.
    Keeps connections per user id and user type (customer/driver).
    Uses Redis pub/sub to broadcast notifications across all service instances.
    Notifications are cleared from Redis immediately after delivery (no storage).
    """

    def __init__(self, redis_url: str = None):
        # store as {('customer', 'user_id'): [websocket, ...], ('driver', 'user_id'): [...]}
        self.connections: Dict[tuple, List[WebSocket]] = {}
        # Use Redis from settings
        self.redis_url = redis_url or settings.REDIS_URL
        self._subscriber_task = None
        self._pubsub = None
        self._redis_client = None
        self._running = False

    async def start_subscriber(self, redis_url: str = None):
        """Start the Redis subscriber to listen for notifications from other services."""
        # Use Redis URL from settings if not provided
        if redis_url:
            self.redis_url = redis_url
        if not self.redis_url:
            self.redis_url = settings.REDIS_URL
        
        if self._running:
            return
        
        self._running = True
        self._subscriber_task = asyncio.create_task(self._subscribe_loop())
        logger.info("Notifications Redis subscriber started")

    async def _subscribe_loop(self):
        """Subscribe to Redis channel and forward notifications to local WebSocket clients."""
        while self._running:
            try:
                self._redis_client = redis_pool.get_pubsub_client()
                self._pubsub = self._redis_client.pubsub()
                await self._pubsub.subscribe("notifications:broadcast")
                logger.info("Subscribed to notifications:broadcast channel")
                
                async for message in self._pubsub.listen():
                    if not self._running:
                        break
                    if message["type"] == "message":
                        try:
                            data = json.loads(message["data"])
                            user_type = data.get("user_type")
                            user_id = data.get("user_id")
                            notification = data.get("notification")
                            
                            if user_type and user_id and notification:
                                await self._send_to_local_connections(user_type, user_id, notification)
                        except json.JSONDecodeError:
                            logger.error(f"Invalid JSON in Redis message: {message['data']}")
                        except Exception as e:
                            logger.error(f"Error processing Redis message: {e}")
            except asyncio.CancelledError:
                break
            except redis.RedisError as e:
                logger.error(f"Redis subscriber error: {e}")
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Unexpected subscriber error: {e}")
                await asyncio.sleep(2)
            finally:
                if self._pubsub:
                    try:
                        await self._pubsub.unsubscribe("notifications:broadcast")
                        await self._pubsub.close()
                    except Exception:
                        pass
                if self._redis_client:
                    try:
                        await self._redis_client.close()
                    except Exception:
                        pass

    async def stop_subscriber(self):
        """Stop the Redis subscriber."""
        self._running = False
        if self._subscriber_task:
            self._subscriber_task.cancel()
            try:
                await self._subscriber_task
            except asyncio.CancelledError:
                pass
        logger.info("Notifications Redis subscriber stopped")

    async def connect(self, user_type: str, user_id: str, websocket: WebSocket):
        await websocket.accept()
        key = (user_type, user_id)
        if key not in self.connections:
            self.connections[key] = []
        self.connections[key].append(websocket)
        logger.info(f"Notifications WS connected: {user_type} {user_id}")

    def disconnect(self, user_type: str, user_id: str, websocket: WebSocket):
        key = (user_type, user_id)
        if key in self.connections:
            if websocket in self.connections[key]:
                self.connections[key].remove(websocket)
            if not self.connections[key]:
                del self.connections[key]
            logger.info(f"Notifications WS disconnected: {user_type} {user_id}")

    async def _send_to_local_connections(self, user_type: str, user_id: str, notification: dict):
        """Send notification to local WebSocket connections only (no Redis publish)."""
        key = (user_type, user_id)
        if key not in self.connections:
            return
        
        payload = json.dumps({
            "type": "notification",
            "notification": notification,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        disconnected = []
        for ws in list(self.connections.get(key, [])):
            try:
                await ws.send_text(payload)
                logger.info(f"Delivered notification to {user_type} {user_id} via WebSocket")
            except Exception as e:
                logger.error(f"Failed to send notification to {user_type} {user_id}: {e}")
                disconnected.append(ws)

        # cleanup disconnected sockets
        for ws in disconnected:
            try:
                self.connections[key].remove(ws)
            except Exception:
                pass

    async def send_notification(self, user_type: str, user_id: str, notification: dict):
        """
        Send notification to user via Redis pub/sub (broadcasts to all service instances).
        Also sends to local connections directly.
        """
        # First, send to local connections
        await self._send_to_local_connections(user_type, user_id, notification)
        
        # Then publish to Redis for other service instances
        if self.redis_url:
            pub_client = None
            try:
                pub_client = redis_pool.get_pubsub_client()
                await pub_client.publish("notifications:broadcast", json.dumps({
                    "user_type": user_type,
                    "user_id": user_id,
                    "notification": notification
                }))
                logger.debug(f"Published notification to Redis for {user_type} {user_id}")
            except redis.RedisError as e:
                logger.error(f"Failed to publish notification to Redis: {e}")
            except Exception as e:
                logger.error(f"Unexpected error publishing notification: {e}")
            finally:
                if pub_client:
                    try:
                        await pub_client.close()
                    except Exception:
                        pass


# single global instance (uses Redis from settings)
notifications_manager = NotificationsConnectionManager(settings.REDIS_URL)
