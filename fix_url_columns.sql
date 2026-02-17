-- Check current column sizes
SELECT column_name, character_maximum_length 
FROM information_schema.columns 
WHERE table_name IN ('driver_documents', 'driver_vehicles') 
AND column_name LIKE '%url%';

-- Fix driver_documents table
ALTER TABLE driver_documents 
ALTER COLUMN id_photo_url TYPE VARCHAR(500),
ALTER COLUMN selfie_photo_url TYPE VARCHAR(500),
ALTER COLUMN license_front_url TYPE VARCHAR(500),
ALTER COLUMN license_back_url TYPE VARCHAR(500),
ALTER COLUMN driver_photo_url TYPE VARCHAR(500);

-- Fix driver_vehicles table
ALTER TABLE driver_vehicles 
ALTER COLUMN vehicle_photo_url TYPE VARCHAR(500),
ALTER COLUMN rc_book_pic_url TYPE VARCHAR(500),
ALTER COLUMN pollution_cert_pic_url TYPE VARCHAR(500);
