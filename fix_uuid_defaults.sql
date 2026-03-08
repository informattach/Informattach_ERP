-- Enable the UUID extension if not already enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Make sure the 'sources' table automatically generates a UUID for the 'id' column
ALTER TABLE sources ALTER COLUMN id SET DEFAULT uuid_generate_v4();

-- Make sure the 'listings' table automatically generates a UUID for the 'id' column
ALTER TABLE listings ALTER COLUMN id SET DEFAULT uuid_generate_v4();

-- And the core_products table just in case
ALTER TABLE core_products ALTER COLUMN id SET DEFAULT uuid_generate_v4();
