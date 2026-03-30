-- Enable required extensions for the main professor database
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- Create the RAG service database
SELECT 'CREATE DATABASE professor_rag OWNER professor'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'professor_rag')\gexec

-- Enable extensions in the RAG database
\c professor_rag
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
