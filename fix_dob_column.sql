-- Revert DOB column back to date type (it should NOT be encrypted)
-- First drop the column, then recreate it
ALTER TABLE drivers DROP COLUMN dob;
ALTER TABLE drivers ADD COLUMN dob TIMESTAMP;
