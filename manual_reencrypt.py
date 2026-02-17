import asyncio
from sqlalchemy import select
from core.database import get_db
from core.models import Driver, Admin
from core.utils.field_encryption import encrypt_phone, encrypt_email, encrypt_field, encrypt_address

# MANUAL DATA MAPPING
# Add your actual driver/admin data here
DRIVER_DATA = {
    # "driver_id": {"phone": "+919059658735", "email": "driver@example.com", "name": "Driver Name", "address": "Address"},
}

ADMIN_DATA = {
    # "admin_id": {"phone": "+919876543210"},
}

async def manual_reencrypt():
    async for db in get_db():
        # Update Drivers
        if DRIVER_DATA:
            for driver_id, data in DRIVER_DATA.items():
                result = await db.execute(select(Driver).where(Driver.id == driver_id))
                driver = result.scalar_one_or_none()
                
                if driver:
                    driver.phone_number = encrypt_phone(data["phone"])
                    if "email" in data:
                        driver.email = encrypt_email(data["email"])
                    if "name" in data:
                        driver.full_name = encrypt_field(data["name"])
                    if "address" in data:
                        driver.address = encrypt_address(data["address"])
                    
                    print(f"✅ Updated driver {driver_id}: {data['phone']}")
                else:
                    print(f"❌ Driver {driver_id} not found")
        
        # Update Admins
        if ADMIN_DATA:
            for admin_id, data in ADMIN_DATA.items():
                result = await db.execute(select(Admin).where(Admin.id == admin_id))
                admin = result.scalar_one_or_none()
                
                if admin:
                    admin.phone_number = encrypt_phone(data["phone"])
                    print(f"✅ Updated admin {admin_id}: {data['phone']}")
                else:
                    print(f"❌ Admin {admin_id} not found")
        
        await db.commit()
        print("\n✅ Manual re-encryption complete!")
        break

async def list_all_ids():
    """Helper to list all driver/admin IDs"""
    async for db in get_db():
        result = await db.execute(select(Driver))
        drivers = result.scalars().all()
        
        print("DRIVERS:")
        for driver in drivers:
            print(f"  ID: {driver.id}")
            print(f"  Encrypted phone: {driver.phone_number[:30]}...")
            print()
        
        result = await db.execute(select(Admin))
        admins = result.scalars().all()
        
        print("\nADMINS:")
        for admin in admins:
            print(f"  ID: {admin.id}")
            print(f"  Encrypted phone: {admin.phone_number[:30]}...")
            print()
        
        break

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        print("Listing all IDs...\n")
        asyncio.run(list_all_ids())
    else:
        if not DRIVER_DATA and not ADMIN_DATA:
            print("⚠️  No data provided!")
            print("\n1. Run: python manual_reencrypt.py list")
            print("2. Edit this file and add data to DRIVER_DATA and ADMIN_DATA")
            print("3. Run: python manual_reencrypt.py")
        else:
            asyncio.run(manual_reencrypt())
