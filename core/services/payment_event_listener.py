"""
Payment Event Listener - Handles payment events from customer backend
"""
import json
import logging
import asyncio
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import AsyncSessionLocal
from core.services.stripe_payment_service import StripePaymentService
from core.redis_client import redis_pool

logger = logging.getLogger(__name__)

class PaymentEventListener:
    """Listens for payment events and processes commission splits"""
    
    @staticmethod
    async def start_listener():
        """Start Redis subscriber for payment events"""
        redis_client = redis_pool.get_client()
        
        try:
            pubsub = redis_client.pubsub()
            await pubsub.subscribe("payment.events")
            
            logger.info("Payment event listener started")
            
            async for message in pubsub.listen():
                if message["type"] == "message":
                    await PaymentEventListener._process_payment_event(message["data"])
                    
        except Exception as e:
            logger.error(f"Payment listener error: {e}")
        finally:
            await redis_client.close()
    
    @staticmethod
    async def _process_payment_event(data: bytes):
        """Process incoming payment event"""
        try:
            event_data = json.loads(data.decode())
            
            if event_data["event"] == "payment.completed":
                async with AsyncSessionLocal() as db:
                    await StripePaymentService.process_successful_payment(
                        payment_intent_id=event_data.get("stripe_payment_intent_id"),
                        db=db
                    )
                    
                logger.info(f"Processed payment for job {event_data['job_id']}")
                
        except Exception as e:
            logger.error(f"Failed to process payment event: {e}")

# Background task to run listener
async def start_payment_listener():
    """Start the payment event listener as background task"""
    await PaymentEventListener.start_listener()