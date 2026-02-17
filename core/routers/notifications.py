from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from core.notifications_websocket import notifications_manager
from core.database import get_db
from core.utils.security import decode_token
from core.models import Notification
from core.schemas import NotificationResponse
from core.dependencies import get_current_customer, get_current_driver
from typing import Tuple, List
from uuid import UUID

router = APIRouter(tags=["Notifications"])


# ───────────────────────────────────────────────────────────────────────────
# Helper
# ───────────────────────────────────────────────────────────────────────────
async def get_user_from_token_simple(token: str) -> Tuple[str, str]:
    """Decode token and return (user_id, role)."""
    payload = decode_token(token)
    if not payload:
        return None, None
    return payload.get("sub"), payload.get("role")


# ───────────────────────────────────────────────────────────────────────────
# WebSocket endpoints  (mounted at /api/server/...)
# ───────────────────────────────────────────────────────────────────────────
@router.websocket("/server/customer/notifications")
async def customer_notifications_ws(websocket: WebSocket, token: str = Query(...)):
    """Live notifications for customers.
    Connect: ws://host/api/server/customer/notifications?token=...
    """
    user_id, role = await get_user_from_token_simple(token)
    if not user_id or role != "customer":
        await websocket.accept()
        await websocket.close(code=4003)
        return

    await notifications_manager.connect("customer", user_id, websocket)
    try:
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        notifications_manager.disconnect("customer", user_id, websocket)
    except Exception:
        notifications_manager.disconnect("customer", user_id, websocket)


@router.websocket("/server/driver/notifications")
async def driver_notifications_ws(websocket: WebSocket, token: str = Query(...)):
    """Live notifications for drivers.
    Connect: ws://host/api/server/driver/notifications?token=...
    """
    user_id, role = await get_user_from_token_simple(token)
    if not user_id or role != "driver":
        await websocket.accept()
        await websocket.close(code=4003)
        return

    await notifications_manager.connect("driver", user_id, websocket)
    try:
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        notifications_manager.disconnect("driver", user_id, websocket)
    except Exception:
        notifications_manager.disconnect("driver", user_id, websocket)


# ───────────────────────────────────────────────────────────────────────────
# HTTP endpoints  (mounted at /api/customer/notifications etc.)
# ───────────────────────────────────────────────────────────────────────────
@router.get("/customer/notifications", response_model=List[NotificationResponse])
async def get_customer_notifications(
    current_customer=Depends(get_current_customer),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Notification)
        .where(Notification.user_type == "customer", Notification.user_id == current_customer.id)
        .order_by(Notification.created_at.desc())
    )
    return result.scalars().all()


@router.get("/driver/notifications", response_model=List[NotificationResponse])
async def get_driver_notifications(
    current_driver=Depends(get_current_driver),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Notification)
        .where(Notification.user_type == "driver", Notification.user_id == current_driver.id)
        .order_by(Notification.created_at.desc())
    )
    return result.scalars().all()


@router.put("/customer/notifications/{note_id}/read", response_model=dict)
async def mark_customer_notification_read(
    note_id: UUID,
    current_customer=Depends(get_current_customer),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Notification).where(Notification.id == note_id, Notification.user_id == current_customer.id)
    )
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail="Notification not found")
    note.is_read = True
    db.add(note)
    await db.commit()
    
    # Push "remove" event via WebSocket
    try:
        await notifications_manager.send_notification(
            "customer",
            str(current_customer.id),
            {"type": "notification_read", "id": str(note_id), "action": "remove"}
        )
    except Exception:
        pass
    
    return {"success": True}


@router.put("/driver/notifications/{note_id}/read", response_model=dict)
async def mark_driver_notification_read(
    note_id: UUID,
    current_driver=Depends(get_current_driver),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Notification).where(Notification.id == note_id, Notification.user_id == current_driver.id)
    )
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail="Notification not found")
    note.is_read = True
    db.add(note)
    await db.commit()
    
    # Push "remove" event via WebSocket
    try:
        await notifications_manager.send_notification(
            "driver",
            str(current_driver.id),
            {"type": "notification_read", "id": str(note_id), "action": "remove"}
        )
    except Exception:
        pass
    
    return {"success": True}
