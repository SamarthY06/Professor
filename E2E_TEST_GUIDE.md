# End-to-End Testing Guide for Professor App

## Overview

This guide explains how to run end-to-end tests for the Professor web application to verify the complete user journey works correctly.

## Prerequisites

1. **Backend running**: `http://localhost:8000`
2. **Frontend running**: `http://localhost:3000`
3. **Test book exists**: Book ID `22b3d969-1126-4e8e-8a3d-75da7a40918d` should be in the database

## Option 1: Full Browser UI Test (Recommended)

This test automates a real browser and follows the exact user journey step-by-step.

### Installation

```bash
# Install Playwright
pip install playwright pytest-playwright

# Install browser binaries
playwright install chromium
```

### Run the Test

```bash
python e2e-browser-test.py
```

### What It Tests

The script will:

1. ✅ Open http://localhost:3000
2. ✅ Navigate to /login
3. ✅ Fill in dev login (email: uitest@professor.ai)
4. ✅ Click login and verify redirect to /dashboard
5. ✅ View dashboard and find upload button
6. ✅ Navigate to /library/upload
7. ✅ **CRITICAL TEST**: Navigate to /learn/{book_id} and verify NO redirect to /login
8. ✅ Send a chat message in the learn interface
9. ✅ Continue the conversation
10. ✅ Test /learn/{book_id}/plan (should NOT redirect to /login)
11. ✅ Test /learn/{book_id}/configure (should NOT redirect to /login)

### Screenshots

All screenshots are saved to `screenshots_YYYYMMDD_HHMMSS/` directory with names like:
- `step_01_landing_page.png`
- `step_07_learn_page_SUCCESS.png` (or `FAILED_redirected_to_login.png`)
- etc.

### Video Recording

A video of the entire test run is saved to the screenshots directory.

## Option 2: API Endpoint Test (Quick Check)

This test verifies the backend APIs work correctly without browser automation.

### Run the Test

```bash
./test-api-endpoints.sh
```

### What It Tests

1. Backend health check
2. Frontend health check  
3. Dev login API
4. Get user info with auth token
5. Get books list
6. Get specific book by ID
7. Get learning session

## Expected Results

### ✅ Success Criteria

**Step 7 (CRITICAL)**: When navigating to `/learn/{book_id}`, the page should:
- Load the chat interface
- Show professor's greeting message
- Display chat input field
- **NOT** redirect to `/login`

If Step 7 redirects to login, the auth fix has failed.

### ❌ Failure Scenarios

1. **Redirect to /login on learn page**: Auth middleware is not allowing authenticated users
2. **No chat interface**: Learn page components not rendering
3. **401/403 errors**: Token not being sent or validated properly
4. **404 errors**: Book doesn't exist or routing is broken

## Debugging

### Check Frontend Logs

```bash
# If running in Docker
docker logs -f professor-web-1

# If running with npm
# Check the terminal where you ran `npm run dev`
```

### Check Backend Logs

```bash
# If running in Docker
docker logs -f professor-backend-1

# If running with uvicorn
# Check the terminal where you ran the backend
```

### Check Browser Console

During the Playwright test (which runs in headed mode), you can:
1. Watch the browser window as it automates
2. Check console for errors (F12 Developer Tools)
3. Pause the test by adding `await page.pause()` in the script

### Manual Testing

If automated tests fail, manually test:

1. Open http://localhost:3000/login in your browser
2. Use dev login with email: `uitest@professor.ai`
3. After login, manually navigate to: http://localhost:3000/learn/22b3d969-1126-4e8e-8a3d-75da7a40918d
4. Check if you see the chat interface or get redirected to /login

## Common Issues

### Issue: "Test book not found"

**Solution**: Create a test book first or use a different book ID that exists in your database.

```sql
-- Check existing books
SELECT id, title FROM books LIMIT 10;
```

### Issue: "Browser not found"

**Solution**: Install Playwright browsers:
```bash
playwright install chromium
```

### Issue: "Connection refused to localhost:3000"

**Solution**: Make sure frontend is running:
```bash
cd web
npm run dev
```

### Issue: "Connection refused to localhost:8000"

**Solution**: Make sure backend is running:
```bash
cd backend
uvicorn app.main:app --reload
# OR
docker-compose up backend
```

## Test Data

### Dev Login Credentials
- **Email**: `uitest@professor.ai`
- **Name**: `UI Test User`

### Test Book ID
- **ID**: `22b3d969-1126-4e8e-8a3d-75da7a40918d`

## CI/CD Integration

To run these tests in GitHub Actions or other CI:

```yaml
- name: Install Playwright
  run: |
    pip install playwright pytest-playwright
    playwright install chromium --with-deps

- name: Run E2E Tests
  run: python e2e-browser-test.py
  
- name: Upload Screenshots
  if: always()
  uses: actions/upload-artifact@v3
  with:
    name: e2e-screenshots
    path: screenshots_*/
```

## Next Steps

After all tests pass:

1. Test with real book uploads
2. Test quiz functionality
3. Test progress tracking
4. Test chapter navigation
5. Load testing with multiple concurrent users

## Support

If tests fail consistently:
1. Check the screenshots in `screenshots_*/`
2. Review backend/frontend logs
3. Verify database state
4. Check that all environment variables are set correctly
