"""
Test script for payment split logic
"""

from decimal import Decimal
from core.services.payment_split import PaymentSplitService

def test_payment_split():
    """Test payment split calculations"""
    
    print("=== Payment Split Logic Test ===\n")
    
    # Test cases
    test_amounts = [
        Decimal("100.00"),  # £100.00
        Decimal("50.00"),   # £50.00
        Decimal("25.50"),   # £25.50
        Decimal("199.99"),  # £199.99
        Decimal("1.00"),    # £1.00
    ]
    
    for amount in test_amounts:
        print(f"Testing amount: £{amount}")
        
        try:
            split = PaymentSplitService.calculate_split(amount)
            
            print(f"  Total Amount:   £{split['total_amount']}")
            print(f"  Driver Share:   £{split['driver_amount']} (80%)")
            print(f"  Platform Fee:   £{split['platform_fee']} (20%)")
            
            # Verify split adds up
            is_valid = PaymentSplitService.validate_split(
                split['total_amount'],
                split['driver_amount'], 
                split['platform_fee']
            )
            print(f"  Split Valid:    {is_valid}")
            
            # Calculate percentages
            driver_percent = (split['driver_amount'] / split['total_amount']) * 100
            platform_percent = (split['platform_fee'] / split['total_amount']) * 100
            
            print(f"  Driver %:       {driver_percent:.2f}%")
            print(f"  Platform %:     {platform_percent:.2f}%")
            print()
            
        except Exception as e:
            print(f"  ERROR: {e}\n")

if __name__ == "__main__":
    test_payment_split()