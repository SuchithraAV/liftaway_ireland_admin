"""
Payment Split Service - Handles platform commission logic
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Tuple
from config import settings
import logging

logger = logging.getLogger(__name__)

class PaymentSplitService:
    """Service to handle payment splitting between driver and platform"""
    
    @staticmethod
    def calculate_split(total_amount: Decimal) -> Dict[str, Decimal]:
        """
        Calculate payment split between driver and platform
        
        Args:
            total_amount: Total job cost (e.g., 100 GBP)
            
        Returns:
            Dict with driver_amount, platform_fee, and total_amount
        """
        if total_amount <= 0:
            raise ValueError("Total amount must be positive")
        
        # Platform commission percentage from config (default 20%)
        platform_percent = Decimal(str(settings.PLATFORM_FEE_PERCENT))
        
        # Calculate platform fee (20% of total)
        platform_fee = (total_amount * platform_percent / 100).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        
        # Calculate driver amount (80% of total)
        driver_amount = total_amount - platform_fee
        
        # Ensure amounts add up correctly
        if driver_amount + platform_fee != total_amount:
            # Adjust driver amount to ensure exact total
            driver_amount = total_amount - platform_fee
        
        logger.info(f"Payment split: Total={total_amount}, Driver={driver_amount}, Platform={platform_fee}")
        
        return {
            "total_amount": total_amount,
            "driver_amount": driver_amount,
            "platform_fee": platform_fee
        }
    
    @staticmethod
    def validate_split(total_amount: Decimal, driver_amount: Decimal, platform_fee: Decimal) -> bool:
        """
        Validate that split amounts add up to total
        
        Returns:
            True if valid, False otherwise
        """
        return driver_amount + platform_fee == total_amount