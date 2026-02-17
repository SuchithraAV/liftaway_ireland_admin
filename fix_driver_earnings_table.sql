-- Add missing columns to driver_earnings table
ALTER TABLE driver_earnings 
ADD COLUMN IF NOT EXISTS total_job_amount DECIMAL(10, 2),
ADD COLUMN IF NOT EXISTS platform_fee DECIMAL(10, 2);

-- Add missing columns to payments table
ALTER TABLE payments 
ADD COLUMN IF NOT EXISTS total_amount DECIMAL(10, 2),
ADD COLUMN IF NOT EXISTS driver_amount DECIMAL(10, 2),
ADD COLUMN IF NOT EXISTS platform_fee DECIMAL(10, 2);

-- Verify the columns were added to driver_earnings
SELECT 'driver_earnings' as table_name, column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'driver_earnings' 
ORDER BY ordinal_position;

-- Verify the columns were added to payments
SELECT 'payments' as table_name, column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'payments' 
ORDER BY ordinal_position;