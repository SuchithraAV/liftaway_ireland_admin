import redis.asyncio as redis
from typing import List, Dict, Optional
from uuid import UUID
import json
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from config import settings
from core.utils.dijkstra import calculate_travel_distance
from core.utils.dijkstra import calculate_travel_distance

class AllocationQueue:
    def __init__(self):
        self.redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    
    async def get_driver_location(self, driver_id: UUID) -> Optional[Dict[str, float]]:
        '''Get driver location from Redis'''
        key = f"driver:location:{driver_id}"
        location_data = await self.redis_client.get(key)
        
        if location_data:
            return json.loads(location_data)
        return None
    
    async def set_driver_location(self, driver_id: UUID, lat: float, lng: float):
        '''Store driver location in Redis with expiry'''
        key = f"driver:location:{driver_id}"
        location_data = json.dumps({"lat": lat, "lng": lng, "updated_at": datetime.utcnow().isoformat()})
        await self.redis_client.setex(key, settings.REDIS_LOCATION_EXPIRE, location_data)
    
    async def calculate_nearest_drivers(
        self,
        customer_lat: float,
        customer_lng: float,
        driver_ids: List[UUID]
    ) -> List[Dict]:
        '''
        Calculate distances to all drivers using Dijkstra
        Returns sorted list of drivers by distance
        '''
        driver_distances = []
        
        for driver_id in driver_ids:
            location = await self.get_driver_location(driver_id)
            
            if location:
                distance = calculate_travel_distance(
                    customer_lat, customer_lng,
                    location['lat'], location['lng']
                )
                
                driver_distances.append({
                    "driver_id": str(driver_id),
                    "distance_km": distance,
                    "lat": location['lat'],
                    "lng": location['lng']
                })
        
        # Sort by distance
        driver_distances.sort(key=lambda x: x['distance_km'])
        return driver_distances
    
    async def create_allocation_queue(self, booking_id: UUID, driver_list: List[Dict]):
        '''Store allocation queue in Redis'''
        key = f"booking:queue:{booking_id}"
        queue_data = json.dumps({
            "drivers": driver_list,
            "current_index": 0,
            "created_at": datetime.utcnow().isoformat()
        })
        await self.redis_client.setex(key, 3600, queue_data)  # 1 hour expiry
    
    async def get_allocation_queue(self, booking_id: UUID) -> Optional[Dict]:
        '''Retrieve allocation queue from Redis'''
        key = f"booking:queue:{booking_id}"
        queue_data = await self.redis_client.get(key)
        
        if queue_data:
            return json.loads(queue_data)
        return None
    
    async def update_queue_index(self, booking_id: UUID, new_index: int):
        '''Update current index in allocation queue'''
        queue = await self.get_allocation_queue(booking_id)
        if queue:
            queue['current_index'] = new_index
            key = f"booking:queue:{booking_id}"
            await self.redis_client.setex(key, 3600, json.dumps(queue))
    
    async def get_next_driver(self, booking_id: UUID) -> Optional[str]:
        '''Get next driver from queue'''
        queue = await self.get_allocation_queue(booking_id)
        
        if not queue:
            return None
        
        current_index = queue['current_index']
        drivers = queue['drivers']
        
        if current_index >= len(drivers):
            return None  # No more drivers
        
        next_driver = drivers[current_index]['driver_id']
        await self.update_queue_index(booking_id, current_index + 1)
        
        return next_driver
    
    async def set_driver_notified(self, booking_id: UUID, driver_id: UUID):
        '''Mark driver as notified with timeout'''
        key = f"booking:notified:{booking_id}:{driver_id}"
        await self.redis_client.setex(
            key,
            settings.TECHNICIAN_ACCEPT_TIMEOUT_SECONDS,
            "notified"
        )
    
    async def is_driver_notified(self, booking_id: UUID, driver_id: UUID) -> bool:
        '''Check if driver is currently notified'''
        key = f"booking:notified:{booking_id}:{driver_id}"
        return await self.redis_client.exists(key) > 0
    
    async def clear_booking_allocation(self, booking_id: UUID):
        '''Clear all allocation data for a booking'''
        queue_key = f"booking:queue:{booking_id}"
        await self.redis_client.delete(queue_key)
        
        # Clear notification keys
        keys = await self.redis_client.keys(f"booking:notified:{booking_id}:*")
        if keys:
            await self.redis_client.delete(*keys)
    
    async def close(self):
        await self.redis_client.close()

