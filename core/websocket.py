from fastapi import WebSocket, WebSocketDisconnect
from typing import List, Dict
import json
import logging

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        # Store connections by user role
        self.active_connections: Dict[str, List[WebSocket]] = {
            "admin": [],
            "driver": [],
            "customer": []
        }

    async def connect(self, websocket: WebSocket, role: str):
        await websocket.accept()
        if role in self.active_connections:
            self.active_connections[role].append(websocket)
            logger.info(f"WebSocket connected for role: {role}")

    def disconnect(self, websocket: WebSocket, role: str):
        if role in self.active_connections and websocket in self.active_connections[role]:
            self.active_connections[role].remove(websocket)
            logger.info(f"WebSocket disconnected for role: {role}")

    async def send_to_role(self, role: str, message: dict):
        """Send message to all connections of a specific role"""
        if role not in self.active_connections:
            return
        
        disconnected = []
        for connection in self.active_connections[role]:
            try:
                await connection.send_text(json.dumps(message))
            except:
                disconnected.append(connection)
        
        # Remove disconnected connections
        for conn in disconnected:
            self.active_connections[role].remove(conn)

    async def broadcast_booking_update(self, booking_data: dict, event_type: str):
        """Broadcast booking updates to admin, drivers, and customers"""
        message = {
            "type": event_type,
            "data": booking_data,
            "timestamp": booking_data.get("updated_at")
        }
        
        # Send to all user types for real-time updates
        await self.send_to_role("admin", message)
        await self.send_to_role("driver", message)
        await self.send_to_role("customer", message)

manager = ConnectionManager()