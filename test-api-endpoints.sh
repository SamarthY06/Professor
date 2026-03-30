#!/bin/bash

# Test API endpoints without browser automation
# This tests the backend APIs that the frontend would call

BASE_URL="http://localhost:8000"
FRONTEND_URL="http://localhost:3000"

echo "========================================="
echo "Professor App - API Endpoint Test"
echo "========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test 1: Health check
echo "TEST 1: Health Check"
echo "---------------------"
response=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health" 2>/dev/null)
if [ "$response" = "200" ]; then
    echo -e "${GREEN}✓ Backend is running${NC}"
else
    echo -e "${RED}✗ Backend health check failed (HTTP $response)${NC}"
fi
echo ""

# Test 2: Frontend check
echo "TEST 2: Frontend Check"
echo "---------------------"
response=$(curl -s -o /dev/null -w "%{http_code}" "$FRONTEND_URL" 2>/dev/null)
if [ "$response" = "200" ]; then
    echo -e "${GREEN}✓ Frontend is running${NC}"
else
    echo -e "${RED}✗ Frontend health check failed (HTTP $response)${NC}"
fi
echo ""

# Test 3: Dev Login
echo "TEST 3: Dev Login"
echo "---------------------"
login_response=$(curl -s -X POST "$BASE_URL/api/auth/dev-login" \
  -H "Content-Type: application/json" \
  -d '{"email":"uitest@professor.ai","name":"UI Test User"}')

echo "Response: $login_response"

# Extract token
TOKEN=$(echo $login_response | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

if [ -n "$TOKEN" ]; then
    echo -e "${GREEN}✓ Dev login successful${NC}"
    echo "Token: ${TOKEN:0:50}..."
else
    echo -e "${RED}✗ Dev login failed${NC}"
fi
echo ""

# Test 4: Get user info
if [ -n "$TOKEN" ]; then
    echo "TEST 4: Get User Info (with auth)"
    echo "---------------------"
    user_response=$(curl -s -X GET "$BASE_URL/api/auth/me" \
      -H "Authorization: Bearer $TOKEN")
    
    echo "Response: $user_response"
    
    if echo "$user_response" | grep -q "uitest@professor.ai"; then
        echo -e "${GREEN}✓ Auth token works${NC}"
        USER_ID=$(echo $user_response | grep -o '"id":"[^"]*' | cut -d'"' -f4)
        echo "User ID: $USER_ID"
    else
        echo -e "${RED}✗ Failed to get user info${NC}"
    fi
    echo ""
fi

# Test 5: Get books
if [ -n "$TOKEN" ]; then
    echo "TEST 5: Get Books"
    echo "---------------------"
    books_response=$(curl -s -X GET "$BASE_URL/api/books" \
      -H "Authorization: Bearer $TOKEN")
    
    # Pretty print if jq is available
    if command -v jq &> /dev/null; then
        echo "$books_response" | jq '.'
    else
        echo "$books_response"
    fi
    
    if echo "$books_response" | grep -q "22b3d969-1126-4e8e-8a3d-75da7a40918d"; then
        echo -e "${GREEN}✓ Test book exists${NC}"
    else
        echo -e "${YELLOW}⚠ Test book not found (this is OK if it hasn't been created yet)${NC}"
    fi
    echo ""
fi

# Test 6: Get specific book
if [ -n "$TOKEN" ]; then
    echo "TEST 6: Get Specific Book"
    echo "---------------------"
    BOOK_ID="22b3d969-1126-4e8e-8a3d-75da7a40918d"
    book_response=$(curl -s -X GET "$BASE_URL/api/books/$BOOK_ID" \
      -H "Authorization: Bearer $TOKEN")
    
    if command -v jq &> /dev/null; then
        echo "$book_response" | jq '.'
    else
        echo "$book_response"
    fi
    
    if echo "$book_response" | grep -q "\"id\""; then
        echo -e "${GREEN}✓ Book retrieved successfully${NC}"
    else
        echo -e "${YELLOW}⚠ Book not found (HTTP response above)${NC}"
    fi
    echo ""
fi

# Test 7: Get learning session
if [ -n "$TOKEN" ]; then
    echo "TEST 7: Get Learning Session for Book"
    echo "---------------------"
    BOOK_ID="22b3d969-1126-4e8e-8a3d-75da7a40918d"
    session_response=$(curl -s -X GET "$BASE_URL/api/learning/$BOOK_ID/session" \
      -H "Authorization: Bearer $TOKEN")
    
    if command -v jq &> /dev/null; then
        echo "$session_response" | jq '.'
    else
        echo "$session_response"
    fi
    echo ""
fi

echo "========================================="
echo "Test Complete!"
echo "========================================="
echo ""
echo "To run the full browser UI test:"
echo "  1. pip install playwright pytest-playwright"
echo "  2. playwright install chromium"
echo "  3. python e2e-browser-test.py"
echo ""
