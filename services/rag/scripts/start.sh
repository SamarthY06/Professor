#!/bin/bash
set -e

echo "Starting RAG Service..."

# Wait for PostgreSQL
echo "Waiting for PostgreSQL..."
while ! nc -z ${POSTGRES_HOST:-postgres} ${POSTGRES_PORT:-5432}; do
  sleep 1
done
echo "PostgreSQL is ready!"

# Wait for Qdrant
echo "Waiting for Qdrant..."
while ! nc -z ${QDRANT_HOST:-qdrant} ${QDRANT_PORT:-6333}; do
  sleep 1
done
echo "Qdrant is ready!"

# Wait for Temporal
echo "Waiting for Temporal..."
while ! nc -z ${TEMPORAL_HOST:-temporal} ${TEMPORAL_PORT:-7233}; do
  sleep 1
done
echo "Temporal is ready!"

# Initialize database
echo "Initializing database..."
python scripts/init_db.py

# Start the application
echo "Starting FastAPI application..."
exec uvicorn main:app --host 0.0.0.0 --port 8000
