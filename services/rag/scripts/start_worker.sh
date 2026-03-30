#!/bin/bash
set -e

echo "Starting Temporal Worker..."

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
sleep 5  # Give Temporal a bit more time to fully initialize
echo "Temporal is ready!"

# Start the worker
echo "Starting worker..."
exec python -m temporal_worker.worker
