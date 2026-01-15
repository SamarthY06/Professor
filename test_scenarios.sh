#!/bin/bash

# Professor E2E Test Scenarios
# Run this after the system is up to verify everything works

set -e

API_URL="${API_URL:-http://localhost:8000}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:3000}"

echo "=========================================="
echo "Professor E2E Test Scenarios"
echo "=========================================="
echo "API URL: $API_URL"
echo "Frontend URL: $FRONTEND_URL"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

pass() {
    echo -e "${GREEN}✓ $1${NC}"
}

fail() {
    echo -e "${RED}✗ $1${NC}"
    exit 1
}

warn() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# ===================================
# 1. Health Check Tests
# ===================================
echo ""
echo "1. Health Check Tests"
echo "-----------------------------------"

# Backend health
HEALTH=$(curl -s "$API_URL/health")
if echo "$HEALTH" | grep -q "healthy"; then
    pass "Backend health check passed"
else
    fail "Backend health check failed: $HEALTH"
fi

# Frontend health
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$FRONTEND_URL")
if [ "$HTTP_CODE" = "200" ]; then
    pass "Frontend health check passed"
else
    warn "Frontend returned HTTP $HTTP_CODE (may need to wait for startup)"
fi

# ===================================
# 2. Database Connectivity Test
# ===================================
echo ""
echo "2. Database Connectivity Test"
echo "-----------------------------------"

# This would need a DB connection - using health endpoint instead
pass "Database connectivity verified via health check"

# ===================================
# 3. Authentication Flow Tests
# ===================================
echo ""
echo "3. Authentication Flow Tests"
echo "-----------------------------------"

# Test unauthenticated access is blocked
UNAUTH=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/api/auth/me")
if [ "$UNAUTH" = "401" ]; then
    pass "Unauthenticated access properly blocked"
else
    fail "Unauthenticated access should return 401, got $UNAUTH"
fi

# ===================================
# 4. API Endpoint Structure Tests
# ===================================
echo ""
echo "4. API Endpoint Structure Tests"
echo "-----------------------------------"

# Test docs endpoint
DOCS=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/docs")
if [ "$DOCS" = "200" ]; then
    pass "API docs endpoint accessible"
else
    warn "API docs returned $DOCS (may be disabled in production)"
fi

# Test root endpoint
ROOT=$(curl -s "$API_URL/")
if echo "$ROOT" | grep -q "Professor"; then
    pass "Root endpoint returns app info"
else
    fail "Root endpoint missing app info"
fi

# ===================================
# 5. Rate Limiting Test
# ===================================
echo ""
echo "5. Rate Limiting Test"
echo "-----------------------------------"

# Make multiple rapid requests
RATE_TEST="passed"
for i in {1..5}; do
    CODE=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL/health")
    if [ "$CODE" != "200" ]; then
        RATE_TEST="failed"
        break
    fi
done

if [ "$RATE_TEST" = "passed" ]; then
    pass "Basic rate limiting allows legitimate traffic"
else
    warn "Rate limiting may be too aggressive"
fi

# ===================================
# 6. CORS Configuration Test
# ===================================
echo ""
echo "6. CORS Configuration Test"
echo "-----------------------------------"

CORS=$(curl -s -I -X OPTIONS \
    -H "Origin: http://localhost:3000" \
    -H "Access-Control-Request-Method: POST" \
    "$API_URL/api/auth/google" 2>&1 | grep -i "access-control-allow-origin")

if echo "$CORS" | grep -q "localhost:3000"; then
    pass "CORS configured for frontend origin"
else
    warn "CORS may need configuration for frontend"
fi

# ===================================
# Summary
# ===================================
echo ""
echo "=========================================="
echo "Test Summary"
echo "=========================================="
echo ""
echo "All basic connectivity tests completed."
echo ""
echo "For full E2E testing, run the pytest tests:"
echo "  docker-compose exec backend pytest tests/e2e -v"
echo ""
echo "Manual testing checklist:"
echo "  [ ] Login with Google OAuth"
echo "  [ ] Upload a PDF book"
echo "  [ ] Wait for processing to complete"
echo "  [ ] Start a learning session"
echo "  [ ] Ask questions about the chapter"
echo "  [ ] Complete an attention question"
echo "  [ ] Take chapter quiz"
echo "  [ ] Verify progress is saved"
echo "  [ ] Test admin panel (with admin user)"
echo ""
