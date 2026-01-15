-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- The main schema will be created via Alembic migrations
-- This file just ensures extensions are available
