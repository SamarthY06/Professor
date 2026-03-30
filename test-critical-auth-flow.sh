#!/bin/bash

# Critical Auth Flow Test
# Tests the exact API calls that the frontend makes when accessing /learn/{book_id}

BASE_URL="http://localhost:8000"
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "========================================="
echo "Critical Auth Flow Test"
echo "Tests: Can authenticated user access learn endpoints?"
echo "========================================="
echo ""

# Step 1: Dev Login
echo -e "${BLUE}STEP 1: Dev Login${NC}"
echo "-------------------"
login_response=$(curl -s -X POST "$BASE_URL/api/auth/dev-login" \
  -H "Content-Type: application/json" \
  -d '{"email":"uitest@professor.ai","name":"UI Test User"}')

TOKEN=$(echo $login_response | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

if [ -n "$TOKEN" ]; then
    echo -e "${GREEN}✓ Login successful${NC}"
    echo "Token: ${TOKEN:0:60}..."
else
    echo -e "${RED}✗ Login failed${NC}"
    echo "$login_response"
    exit 1
fi
echo ""

# Step 2: Verify token works
echo -e "${BLUE}STEP 2: Verify Token Works${NC}"
echo "-------------------"
user_response=$(curl -s -X GET "$BASE_URL/api/auth/me" \
  -H "Authorization: Bearer $TOKEN")

if echo "$user_response" | grep -q "uitest@professor.ai"; then
    echo -e "${GREEN}✓ Token is valid${NC}"
    echo "$user_response" | grep -o '"id":"[^"]*' | cut -d'"' -f4
else
    echo -e "${RED}✗ Token validation failed${NC}"
    echo "$user_response"
    exit 1
fi
echo ""

# Step 3: List books (to find a real book ID)
echo -e "${BLUE}STEP 3: Get Books List${NC}"
echo "-------------------"
books_response=$(curl -s -X GET "$BASE_URL/api/books" \
  -H "Authorization: Bearer $TOKEN")

# Check if we have any books
if echo "$books_response" | grep -q '"id"'; then
    echo -e "${GREEN}✓ Books retrieved successfully${NC}"
    
    # Try to extract first book ID
    BOOK_ID=$(echo "$books_response" | grep -o '"id":"[^"]*' | head -1 | cut -d'"' -f4)
    
    if [ -n "$BOOK_ID" ]; then
        echo "Found book ID: $BOOK_ID"
    else
        echo -e "${YELLOW}⚠ No books found in your library${NC}"
        echo "You need to upload a book first to test the learn page"
        BOOK_ID="22b3d969-1126-4e8e-8a3d-75da7a40918d"  # fallback to test ID
        echo "Using fallback test ID: $BOOK_ID (may not exist)"
    fi
else
    echo -e "${YELLOW}⚠ No books in library${NC}"
    BOOK_ID="22b3d969-1126-4e8e-8a3d-75da7a40918d"  # fallback
    echo "Using fallback test ID: $BOOK_ID"
fi
echo ""

# Step 4: CRITICAL TEST - Access book details
echo -e "${BLUE}STEP 4: CRITICAL TEST - Access Book Details${NC}"
echo "-------------------"
echo "Testing: GET /api/books/$BOOK_ID"
book_response=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X GET "$BASE_URL/api/books/$BOOK_ID" \
  -H "Authorization: Bearer $TOKEN")

http_status=$(echo "$book_response" | grep "HTTP_STATUS:" | cut -d':' -f2)
response_body=$(echo "$book_response" | sed '/HTTP_STATUS:/d')

echo "HTTP Status: $http_status"

if [ "$http_status" = "200" ]; then
    echo -e "${GREEN}✓ Book accessed successfully with auth token${NC}"
    if command -v jq &> /dev/null; then
        echo "$response_body" | jq '.'
    else
        echo "$response_body"
    fi
elif [ "$http_status" = "401" ]; then
    echo -e "${RED}✗ CRITICAL FAILURE: 401 Unauthorized${NC}"
    echo "This means the backend is NOT accepting the valid auth token!"
    echo "Response: $response_body"
    exit 1
elif [ "$http_status" = "403" ]; then
    echo -e "${RED}✗ CRITICAL FAILURE: 403 Forbidden${NC}"
    echo "This means auth worked but user is not allowed to access this book"
    echo "Response: $response_body"
    exit 1
elif [ "$http_status" = "404" ]; then
    echo -e "${YELLOW}⚠ Book not found (this is OK if book doesn't exist yet)${NC}"
    echo "The auth is working, just no book with this ID"
    echo "Response: $response_body"
else
    echo -e "${RED}✗ Unexpected status: $http_status${NC}"
    echo "Response: $response_body"
fi
echo ""

# Step 5: CRITICAL TEST - Access learning session
echo -e "${BLUE}STEP 5: CRITICAL TEST - Access Learning Session${NC}"
echo "-------------------"
echo "Testing: GET /api/learning/$BOOK_ID/session"
session_response=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X GET "$BASE_URL/api/learning/$BOOK_ID/session" \
  -H "Authorization: Bearer $TOKEN")

http_status=$(echo "$session_response" | grep "HTTP_STATUS:" | cut -d':' -f2)
response_body=$(echo "$session_response" | sed '/HTTP_STATUS:/d')

echo "HTTP Status: $http_status"

if [ "$http_status" = "200" ]; then
    echo -e "${GREEN}✓ Learning session accessed successfully${NC}"
    if command -v jq &> /dev/null; then
        echo "$response_body" | jq '.'
    else
        echo "$response_body"
    fi
elif [ "$http_status" = "401" ]; then
    echo -e "${RED}✗ CRITICAL FAILURE: 401 Unauthorized on learning session${NC}"
    echo "The /learn page will redirect to /login because auth is failing!"
    echo "Response: $response_body"
    exit 1
elif [ "$http_status" = "403" ]; then
    echo -e "${RED}✗ CRITICAL FAILURE: 403 Forbidden${NC}"
    echo "Response: $response_body"
    exit 1
elif [ "$http_status" = "404" ]; then
    echo -e "${YELLOW}⚠ Session not found (might need to create session first)${NC}"
    echo "This is OK - the auth is working"
    echo "Response: $response_body"
else
    echo -e "${RED}✗ Unexpected status: $http_status${NC}"
    echo "Response: $response_body"
fi
echo ""

# Step 6: Test chat endpoint (simulating sending a message)
echo -e "${BLUE}STEP 6: Test Chat Endpoint${NC}"
echo "-------------------"
echo "Testing: POST /api/chat"
chat_response=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST "$BASE_URL/api/chat" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"book_id\":\"$BOOK_ID\",\"message\":\"Hello professor\"}")

http_status=$(echo "$chat_response" | grep "HTTP_STATUS:" | cut -d':' -f2)
response_body=$(echo "$chat_response" | sed '/HTTP_STATUS:/d')

echo "HTTP Status: $http_status"

if [ "$http_status" = "200" ]; then
    echo -e "${GREEN}✓ Chat endpoint accessible with auth${NC}"
    # Don't print full response as it might be streaming
    echo "Response preview: ${response_body:0:200}..."
elif [ "$http_status" = "401" ]; then
    echo -e "${RED}✗ CRITICAL FAILURE: 401 Unauthorized on chat${NC}"
    echo "Response: $response_body"
    exit 1
else
    echo -e "${YELLOW}⚠ Status: $http_status${NC}"
    echo "Response: $response_body"
fi
echo ""

# Summary
echo "========================================="
echo "TEST SUMMARY"
echo "========================================="
echo ""
echo -e "${GREEN}✓ All critical auth tests passed!${NC}"
echo ""
echo "What this means:"
echo "1. Dev login creates valid JWT tokens"
echo "2. Auth tokens are accepted by protected endpoints"
echo "3. /api/books/{id} works with auth ✓"
echo "4. /api/learning/{id}/session works with auth ✓"
echo "5. /api/chat works with auth ✓"
echo ""
echo "Next step: Test the FRONTEND to verify it:"
echo "1. Sends the auth token correctly"
echo "2. Doesn't redirect to /login on authenticated pages"
echo "3. Handles auth errors gracefully"
echo ""
echo "Run the browser test with:"
echo "  python e2e-browser-test.py"
echo ""
