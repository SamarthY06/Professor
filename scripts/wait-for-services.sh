#!/bin/bash
set -e

echo "Waiting for services to be ready..."

MAX_ATTEMPTS=60
SLEEP_INTERVAL=2

# Wait for backend
echo "Checking backend..."
for i in $(seq 1 $MAX_ATTEMPTS); do
  if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo "Backend is ready!"
    break
  fi
  if [ "$i" -eq "$MAX_ATTEMPTS" ]; then
    echo "Backend did not become ready in time"
    exit 1
  fi
  sleep $SLEEP_INTERVAL
done

# Wait for frontend
echo "Checking frontend..."
for i in $(seq 1 $MAX_ATTEMPTS); do
  if curl -sf http://localhost:3000 > /dev/null 2>&1; then
    echo "Frontend is ready!"
    break
  fi
  if [ "$i" -eq "$MAX_ATTEMPTS" ]; then
    echo "Frontend did not become ready in time"
    exit 1
  fi
  sleep $SLEEP_INTERVAL
done

echo "All services are ready!"
