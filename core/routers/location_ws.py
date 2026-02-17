from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
import json
import redis.asyncio as redis
from config import settings
from core.redis_client import redis_pool
from core.utils.security import decode_token
import asyncio
import logging
from sqlalchemy import select
from uuid import UUID
from core.database import AsyncSessionLocal
from core.models import Issue

router = APIRouter()

logger = logging.getLogger(__name__)


async def _store_location_in_redis(issue_id: str, driver_id: str, lat: float, lng: float):
    key = f"driver:location:issue:{issue_id}"
    data = json.dumps({"driver_id": str(driver_id), "lat": float(lat), "lng": float(lng), "updated_at": __import__('datetime').datetime.utcnow().isoformat()})
    logger.debug(f"Redis store: key={key}")
    
    client = redis_pool.get_client()
    try:
        await client.setex(key, 10, data)
        logger.debug(f"Redis setex succeeded for key={key}")
    except redis.RedisError as e:
        logger.exception(f"Redis setex failed for key={key}: {e}")
        raise
    finally:
        await client.close()


def _extract_token(access_key: str, websocket: WebSocket) -> str:
    # Prefer explicit query param, otherwise look for Authorization header
    if access_key:
        return access_key
    try:
        auth = websocket.headers.get("authorization")
        if auth:
            # Support both 'Bearer <token>' and raw token
            parts = auth.split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                return parts[1]
            return auth
    except Exception:
        pass
    return None


@router.websocket("/driver/location/{issue_id}")
async def driver_location_ws(websocket: WebSocket, issue_id: str, access_key: str = Query(None)):
    """Driver WebSocket: drivers send location updates.

    Requires query param: access_key=<JWT> with role 'driver'.
    e.g. ws://.../api/driver/location/<issue_id>?access_key=driver-secret
    """
    # Extract token from query param or Authorization header
    token = _extract_token(access_key, websocket)
    # Validate: accept static key or JWT with role 'driver'
    authorized = False
    if token and token == settings.DRIVER_WS_KEY:
        authorized = True
    else:
        try:
            payload = decode_token(token) if token else None
            if payload and payload.get("role") == "driver":
                authorized = True
        except Exception as e:
            logger.debug(f"driver token decode error: {e}")

    if not authorized:
        # log reason and reject handshake
        logger.warning(f"Unauthorized driver websocket attempt for issue={issue_id} headers={dict(websocket.headers)} query_access_key={access_key}")
        # close without accepting to reject handshake
        await websocket.close(code=1008)
        return

    # Check issue status in DB - if issue is already completed, send a one-off message and close
    try:
        from core.database import AsyncSessionLocal as _AsyncSessionLocal
        async with _AsyncSessionLocal() as db:
            result = await db.execute(select(Issue).where(Issue.id == UUID(issue_id)))
            issue = result.scalar_one_or_none()
            if issue is not None and issue.status == "completed":
                # If an issue is completed, delete any cached driver location in Redis
                try:
                    client = redis_pool.get_client()
                    key_to_del = f"driver:location:issue:{issue_id}"
                    try:
                        await client.delete(key_to_del)
                        logger.debug(f"Deleted redis key for completed issue: {key_to_del}")
                    except redis.RedisError:
                        logger.exception(f"Failed to delete redis key {key_to_del} for completed issue")
                    finally:
                        await client.close()
                except Exception:
                    logger.exception("Failed to initialize redis client to delete key for completed issue")

                # Accept connection briefly to send a friendly message, then close
                await websocket.accept()
                await websocket.send_text(json.dumps({"error": "issue_already_completed", "message": "Issue is already completed"}))
                await websocket.close(code=4001)
                return
            if issue is None:
                # Issue not found — accept, inform client, then close
                await websocket.accept()
                await websocket.send_text(json.dumps({"error": "issue_not_found", "message": "Issue not found"}))
                await websocket.close(code=4004)
                return
    except Exception:
        # DB lookup failed; log and continue to accept connection — driver can still send locations
        logger.exception(f"Failed to lookup issue status for issue={issue_id}")

    await websocket.accept()
    try:
        while True:
            # Accept connection then validate token
            text = await websocket.receive_text()
            try:
                payload = json.loads(text)
            except Exception:
                await websocket.send_text(json.dumps({"error": "invalid_json"}))
                continue

            driver_id = payload.get("driver_id")
            lat = payload.get("lat")
            lng = payload.get("lng")

            if driver_id is None or lat is None or lng is None:
                await websocket.send_text(json.dumps({"error": "missing_fields"}))
                continue

            # store in redis
            try:
                await _store_location_in_redis(issue_id, driver_id, lat, lng)
            except Exception:
                # If Redis fails, forward the error to the driver and continue
                await websocket.send_text(json.dumps({"error": "redis_error"}))
                logger.warning(f"Failed to store location for issue={issue_id} driver={driver_id}")
                continue
            await websocket.send_text(json.dumps({"success": True}))

    except WebSocketDisconnect:
        return


@router.websocket("/customer/location/{issue_id}")
async def customer_view_ws(websocket: WebSocket, issue_id: str, access_key: str = Query(None)):
    """Customer WebSocket: subscribers receive latest driver location every 60s.

    Requires query param: access_key=<JWT> with role 'customer'.
    Client must provide customer access key as query param.
    Example: ws://.../api/customer/location/<issue_id>?access_key=customer-secret
    """
    # Extract token from query param or Authorization header
    token = _extract_token(access_key, websocket)

    # Validate access_key: accept either a static key or a JWT with role 'customer'
    authorized = False
    if token and token == settings.CUSTOMER_WS_KEY:
        authorized = True
    else:
        try:
            payload = decode_token(token) if token else None
            if payload and payload.get("role") == "customer":
                authorized = True
        except Exception as e:
            logger.debug(f"customer token decode error: {e}")

    if not authorized:
        logger.warning(f"Unauthorized customer websocket attempt for issue={issue_id} headers={dict(websocket.headers)} query_access_key={access_key}")
        await websocket.close(code=1008)
        return

    await websocket.accept()
    key = f"driver:location:issue:{issue_id}"
    client = redis_pool.get_client()

    try:
        while True:
            # Read latest location from Redis with error recovery
            try:
                logger.debug(f"Redis get: key={key}")
                data = await client.get(key)
                logger.debug(f"Redis get result for key={key}: {data}")
                
                if data:
                    await websocket.send_text(json.dumps({"location": json.loads(data)}))
                else:
                    await websocket.send_text(json.dumps({"location": None}))
            except redis.RedisError as e:
                logger.error(f"Redis get failed for key={key}: {e}")
                await websocket.send_text(json.dumps({"location": None, "error": "temporary_error"}))
            except Exception as e:
                logger.error(f"Unexpected error in customer location WS: {e}")

            # Wait 10 seconds before next update
            await asyncio.sleep(10)

    except WebSocketDisconnect:
        return
    finally:
        try:
            await client.close()
        except Exception:
            pass
