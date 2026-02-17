"""
Standalone test script for payment split logic (no dependencies)
"""

from decimal import Decimal, ROUND_HALF_UP

def calculate_split(total_amount: Decimal, platform_percent: float = 20.0):
    """Calculate payment split between driver and platform"""
    if total_amount <= 0:
        raise ValueError("Total amount must be positive")
    
    # Calculate platform fee (20% of total)
    platform_fee = (total_amount * Decimal(str(platform_percent)) / 100).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )
    
    # Calculate driver amount (80% of total)
    driver_amount = total_amount - platform_fee
    
    return {
        "total_amount": total_amount,
        "driver_amount": driver_amount,
        "platform_fee": platform_fee
    }

def validate_split(total_amount: Decimal, driver_amount: Decimal, platform_fee: Decimal):
    """Validate that split amounts add up to total"""
    return driver_amount + platform_fee == total_amount

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
        Decimal("33.33"),   # £33.33 (test rounding)
    ]
    
    for amount in test_amounts:
        print(f"Testing amount: £{amount}")
        
        try:
            split = calculate_split(amount)
            
            print(f"  Total Amount:   £{split['total_amount']}")
            print(f"  Driver Share:   £{split['driver_amount']} (80%)")
            print(f"  Platform Fee:   £{split['platform_fee']} (20%)")
            
            # Verify split adds up
            is_valid = validate_split(
                split['total_amount'],
                split['driver_amount'], 
                split['platform_fee']
            )
            print(f"  Split Valid:    {is_valid}")
            
            # Calculate actual percentages
            driver_percent = (split['driver_amount'] / split['total_amount']) * 100
            platform_percent = (split['platform_fee'] / split['total_amount']) * 100
            
            print(f"  Driver %:       {driver_percent:.2f}%")
            print(f"  Platform %:     {platform_percent:.2f}%")
            
            # Verify percentages are close to expected (80/20)
            driver_diff = abs(float(driver_percent) - 80.0)
            platform_diff = abs(float(platform_percent) - 20.0)
            
            if driver_diff > 0.1 or platform_diff > 0.1:
                print(f"  WARNING: Percentages deviate from expected 80/20 split")
            else:
                print(f"  OK: Percentages are within expected range")
            
            print()
            
        except Exception as e:
            print(f"  ERROR: {e}\n")

if __name__ == "__main__":
    test_payment_split()