# Manual E2E Testing Instructions

## Summary

I've created automated test scripts but cannot run the browser automation in this environment due to sandbox restrictions. Here's what you need to do to complete the end-to-end test.

## API Tests ✅ COMPLETED

I successfully ran API endpoint tests. Results:

### ✅ Working:
- Backend health check (HTTP 200)
- Frontend health check (HTTP 200)
- Dev login API (returns valid JWT token)
- Get user info with auth token (works correctly)

### ⚠️  Needs Setup:
- Test book ID `22b3d969-1126-4e8e-8a3d-75da7a40918d` does not exist yet
- Need to either create this book OR use an existing book ID

## Browser Tests - YOU MUST RUN MANUALLY

### Prerequisites

1. **Install Playwright** (outside this sandbox):
   ```bash
   pip install playwright pytest-playwright
   playwright install chromium
   ```

2. **Ensure services are running**:
   - Frontend: http://localhost:3000 ✅ (confirmed running)
   - Backend: http://localhost:8000 ✅ (confirmed running)

3. **Create test book** (or skip Steps 7-11 if you don't have a book):
   - Either upload a PDF through the UI and note the book ID
   - Or use an existing book ID from your database

### Run the Automated Browser Test

```bash
cd /Users/samarthyadannavar/Desktop/Personal/Professor
python e2e-browser-test.py
```

This will:
- Launch a browser window (you can watch it)
- Take screenshots at each step
- Save everything to `screenshots_YYYYMMDD_HHMMSS/`
- Record a video of the entire test

### OR: Manual Testing Steps

If you prefer to test manually, follow these exact steps:

#### STEP 1: Open the app
1. Navigate to http://localhost:3000
2. **Expected**: Landing page with "Meet Professor" heading
3. **Screenshot**: Take a screenshot

#### STEP 2: Go to Login
1. Navigate to http://localhost:3000/login
2. **Expected**: Login page with dev login form
3. **Screenshot**: Take a screenshot

#### STEP 3: Login using Dev Login
1. Find the dev login section
2. Enter email: `uitest@professor.ai`
3. Enter name: `UI Test User`
4. Click "Dev Login" or "Continue" button
5. **Expected**: Redirect to `/dashboard` or `/library`
6. **Screenshot**: Take a screenshot after redirect

#### STEP 4: Dashboard
1. You should now be on the dashboard
2. **Expected**: See books list, upload button, navigation
3. Look for "Upload" or "Start Learning" button
4. **Screenshot**: Take a screenshot

#### STEP 5: Upload Page
1. Navigate to http://localhost:3000/library/upload
2. **Expected**: File upload area, book title/author input fields
3. **Screenshot**: Take a screenshot

#### STEP 6: Upload a Book
1. **Expected**: Verify upload form renders with:
   - File input (accepts PDF)
   - Title input
   - Author input
   - Submit button
2. **Screenshot**: Take a screenshot

#### STEP 7: Test Learn Page (CRITICAL TEST)
1. Navigate to http://localhost:3000/learn/22b3d969-1126-4e8e-8a3d-75da7a40918d
   - **OR use a real book ID from your database if this one doesn't exist**
2. **CRITICAL CHECK**: Does the page redirect to `/login`?
   - ❌ If YES: Auth fix FAILED
   - ✅ If NO: Auth fix WORKED
3. **Expected if working**: Chat interface with professor's greeting
4. **Screenshot**: Take a screenshot

#### STEP 8: Send a Chat Message
1. In the chat input, type: `"I want to learn this in 2 days, spending 30 minutes each day. I'm a beginner."`
2. Click Send or press Enter
3. Wait for professor's response
4. **Expected**: Professor responds with questions about teaching style
5. **Screenshot**: Take a screenshot of response

#### STEP 9: Continue the Conversation
1. Type: `"Friendly style please, and quiz me after each chapter"`
2. Send the message
3. Wait for response
4. **Expected**: Professor acknowledges and may create a plan
5. **Screenshot**: Take a screenshot

#### STEP 10: Test Plan Page
1. Navigate to http://localhost:3000/learn/{BOOK_ID}/plan
2. **CRITICAL CHECK**: Does it redirect to `/login`?
   - ❌ If YES: Auth fix incomplete
   - ✅ If NO: Auth fix working
3. **Expected**: Learning plan page loads
4. **Screenshot**: Take a screenshot

#### STEP 11: Test Configure Page
1. Navigate to http://localhost:3000/learn/{BOOK_ID}/configure
2. **CRITICAL CHECK**: Does it redirect to `/login`?
   - ❌ If YES: Auth fix incomplete
   - ✅ If NO: Auth fix working
3. **Expected**: Configuration page loads
4. **Screenshot**: Take a screenshot

## Key Success Criteria

### ✅ TEST PASSES IF:
1. Step 3: Login successful, redirects to dashboard
2. **Step 7: Learn page loads WITHOUT redirect to /login** ⭐ MOST IMPORTANT
3. Step 7: Chat interface is visible
4. Step 8: Can send messages and receive responses
5. Step 10: Plan page loads WITHOUT redirect to /login
6. Step 11: Configure page loads WITHOUT redirect to /login

### ❌ TEST FAILS IF:
1. Step 7: Redirects to `/login` - Auth middleware blocking authenticated users
2. Step 7: 401/403 errors in console
3. Step 7: Chat interface doesn't render
4. Step 10 or 11: Redirect to `/login`

## How to Get a Valid Book ID

If the test book doesn't exist, find a real book ID:

### Option 1: From Database
```sql
-- Connect to your postgres database
SELECT id, title FROM books LIMIT 5;
```

### Option 2: From API (after login)
```bash
# Run this AFTER getting a token from dev login
TOKEN="<your_access_token_here>"
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/books | jq '.[].id'
```

### Option 3: Upload a test book
1. Login to the UI
2. Go to /library/upload
3. Upload any PDF
4. Note the book ID from the URL after upload completes

## Automated Test Scripts I Created

1. **`e2e-browser-test.py`**: Full Playwright automation (requires Playwright installation)
2. **`test-api-endpoints.sh`**: API-only tests (already ran successfully ✅)
3. **`E2E_TEST_GUIDE.md`**: Comprehensive testing guide
4. **`MANUAL_E2E_TEST_INSTRUCTIONS.md`**: This file

## Next Steps

1. Run `playwright install chromium` in your terminal (not in this sandbox)
2. Run `python e2e-browser-test.py` 
3. Watch the browser automate through all steps
4. Check the `screenshots_*/` folder for results
5. Report back if Step 7 redirects to login (the critical auth test)

## Questions to Answer

After running the test:

1. **Does /learn/{book_id} redirect to /login?** (Yes/No)
2. **Is the chat interface visible on the learn page?** (Yes/No)
3. **Can you send messages successfully?** (Yes/No)
4. **Do /plan and /configure pages work without redirecting?** (Yes/No)
5. **Any errors in browser console?** (What errors?)

## Contact/Support

If you encounter issues:
1. Check `screenshots_*/` for visual evidence
2. Check browser console (F12) for JavaScript errors
3. Check backend logs: `docker logs -f professor-backend-1`
4. Check frontend logs: `docker logs -f professor-web-1`
