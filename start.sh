#!/bin/bash

# Professor Startup Script
# This script helps set up and start the entire system

set -e

echo "=========================================="
echo "Professor - AI Learning Assistant"
echo "=========================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${BLUE}ℹ $1${NC}"; }
success() { echo -e "${GREEN}✓ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠ $1${NC}"; }
error() { echo -e "${RED}✗ $1${NC}"; }

# Check Docker is installed
if ! command -v docker &> /dev/null; then
    error "Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    error "Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

success "Docker and Docker Compose found"

# ===================================
# Step 1: Environment Setup
# ===================================
echo ""
info "Step 1: Checking environment files..."

# Backend environment
if [ ! -f backend/.env ]; then
    if [ -f backend/env.template ]; then
        warn "No backend/.env found. Creating from template..."
        cp backend/env.template backend/.env
        warn "IMPORTANT: Edit backend/.env and set your credentials!"
        warn "Required: JWT_SECRET_KEY, ENCRYPTION_KEY, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET"
    else
        error "No backend/env.template found!"
        exit 1
    fi
else
    success "Backend .env exists"
fi

# Frontend environment
if [ ! -f web/.env.local ]; then
    if [ -f web/env.template ]; then
        warn "No web/.env.local found. Creating from template..."
        cp web/env.template web/.env.local
        warn "IMPORTANT: Edit web/.env.local and set NEXT_PUBLIC_GOOGLE_CLIENT_ID"
    elif [ -f web/setup-env.sh ]; then
        warn "Running web/setup-env.sh..."
        cd web && ./setup-env.sh && cd ..
    else
        error "No web environment setup found!"
    fi
else
    success "Frontend .env.local exists"
fi

# ===================================
# Step 2: Create data directories
# ===================================
echo ""
info "Step 2: Creating data directories..."

mkdir -p data/postgres
mkdir -p data/redis
mkdir -p data/pdfs
mkdir -p data/logs
mkdir -p data/cache
mkdir -p temporal/dynamicconfig

# Create Temporal dynamic config if not exists
if [ ! -f temporal/dynamicconfig/development.yaml ]; then
    cat > temporal/dynamicconfig/development.yaml << 'EOF'
# Temporal Dynamic Configuration
frontend.enableClientVersionCheck:
  - value: true
    constraints: {}
EOF
fi

success "Data directories created"

# ===================================
# Step 3: Start Services
# ===================================
echo ""
info "Step 3: Starting Docker services..."

docker-compose up -d

echo ""
info "Waiting for services to be ready..."
sleep 10

# ===================================
# Step 4: Run Database Migrations
# ===================================
echo ""
info "Step 4: Running database migrations..."

# Wait for postgres to be ready
MAX_RETRIES=30
RETRY=0
until docker-compose exec -T postgres pg_isready -U professor -d professor > /dev/null 2>&1; do
    RETRY=$((RETRY+1))
    if [ $RETRY -eq $MAX_RETRIES ]; then
        error "PostgreSQL failed to start after $MAX_RETRIES attempts"
        exit 1
    fi
    echo "Waiting for PostgreSQL... ($RETRY/$MAX_RETRIES)"
    sleep 2
done

success "PostgreSQL is ready"

# Run migrations
docker-compose exec -T backend alembic upgrade head || {
    warn "Migration may have already run or there was an issue"
}

# ===================================
# Step 5: Verify Services
# ===================================
echo ""
info "Step 5: Verifying services..."

# Check backend
if curl -s http://localhost:8000/health | grep -q "healthy"; then
    success "Backend is running at http://localhost:8000"
else
    warn "Backend may still be starting up..."
fi

# Check frontend
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    success "Frontend is running at http://localhost:3000"
else
    warn "Frontend is starting up (may take a minute for first build)..."
fi

# Check Temporal UI
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8080 | grep -q "200"; then
    success "Temporal UI is running at http://localhost:8080"
else
    warn "Temporal UI may still be starting..."
fi

# ===================================
# Final Summary
# ===================================
echo ""
echo "=========================================="
echo "Startup Complete!"
echo "=========================================="
echo ""
echo "Services:"
echo "  • Frontend:    http://localhost:3000"
echo "  • Backend API: http://localhost:8000"
echo "  • API Docs:    http://localhost:8000/docs"
echo "  • Temporal UI: http://localhost:8080"
echo ""
echo "Next Steps:"
echo "  1. Edit backend/.env with your credentials"
echo "  2. Edit web/.env.local with your Google Client ID"
echo "  3. Restart with: docker-compose restart"
echo "  4. Run tests: ./test_scenarios.sh"
echo ""
echo "Useful Commands:"
echo "  • View logs:       docker-compose logs -f"
echo "  • Stop services:   docker-compose down"
echo "  • Rebuild:         docker-compose up -d --build"
echo ""
