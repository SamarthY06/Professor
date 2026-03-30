#!/usr/bin/env python3
"""
End-to-End Browser Test for Professor App
Tests the complete user journey through the web UI.

Requirements:
  pip install playwright pytest-playwright
  playwright install chromium

Usage:
  python e2e-browser-test.py
"""

import asyncio
import sys
from playwright.async_api import async_playwright, Page, expect
from datetime import datetime


class E2ETest:
    def __init__(self):
        self.base_url = "http://localhost:3000"
        self.api_url = "http://localhost:8000"
        self.test_email = "uitest@professor.ai"
        self.test_name = "UI Test User"
        self.test_book_id = "22b3d969-1126-4e8e-8a3d-75da7a40918d"
        self.screenshots_dir = f"screenshots_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
    def log(self, step: int, message: str):
        """Log a test step"""
        print(f"\n{'='*80}")
        print(f"STEP {step}: {message}")
        print(f"{'='*80}\n")
        
    async def take_screenshot(self, page: Page, step: int, name: str):
        """Take and save a screenshot"""
        import os
        os.makedirs(self.screenshots_dir, exist_ok=True)
        filename = f"{self.screenshots_dir}/step_{step:02d}_{name}.png"
        await page.screenshot(path=filename, full_page=True)
        print(f"📸 Screenshot saved: {filename}")
        
    async def describe_page(self, page: Page):
        """Describe what's visible on the current page"""
        url = page.url
        title = await page.title()
        print(f"Current URL: {url}")
        print(f"Page Title: {title}")
        
        # Check for common elements
        has_login_form = await page.locator('form').count() > 0
        has_buttons = await page.locator('button').count()
        has_inputs = await page.locator('input').count()
        has_error = await page.locator('[role="alert"]').count() > 0
        
        print(f"Forms: {'Yes' if has_login_form else 'No'}")
        print(f"Buttons: {has_buttons}")
        print(f"Input fields: {has_inputs}")
        print(f"Error messages: {'Yes' if has_error else 'No'}")
        
        # Get visible text
        body_text = await page.locator('body').text_content()
        if body_text:
            # Print first 500 chars of visible text
            preview = body_text.strip()[:500]
            print(f"\nVisible text preview:\n{preview}...")
            
    async def run_test(self):
        """Run the complete end-to-end test"""
        async with async_playwright() as p:
            # Launch browser in headed mode so you can watch
            browser = await p.chromium.launch(headless=False, slow_mo=500)
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                record_video_dir=f"{self.screenshots_dir}/videos"
            )
            page = await context.new_page()
            
            try:
                # STEP 1: Open the app
                self.log(1, "Open the app")
                await page.goto(self.base_url)
                await page.wait_for_load_state('networkidle')
                await self.describe_page(page)
                await self.take_screenshot(page, 1, "landing_page")
                
                # STEP 2: Go to Login
                self.log(2, "Navigate to Login Page")
                await page.goto(f"{self.base_url}/login")
                await page.wait_for_load_state('networkidle')
                await self.describe_page(page)
                await self.take_screenshot(page, 2, "login_page")
                
                # STEP 3: Login using Dev Login
                self.log(3, "Login using Dev Login")
                
                # Look for dev login inputs
                email_input = page.locator('input[type="email"]').first
                name_input = page.locator('input[placeholder*="name" i], input[name*="name" i]').first
                
                # Check if inputs exist
                email_count = await page.locator('input[type="email"]').count()
                print(f"Found {email_count} email inputs")
                
                if email_count == 0:
                    print("❌ ERROR: No email input found on login page!")
                    await self.take_screenshot(page, 3, "login_error_no_input")
                else:
                    # Fill in dev login
                    await email_input.fill(self.test_email)
                    print(f"✓ Filled email: {self.test_email}")
                    
                    name_count = await page.locator('input').count()
                    print(f"Total inputs found: {name_count}")
                    
                    # Try to find name input
                    if await name_input.count() > 0:
                        await name_input.fill(self.test_name)
                        print(f"✓ Filled name: {self.test_name}")
                    
                    # Find and click the dev login button
                    dev_button = page.locator('button:has-text("Dev Login"), button:has-text("Continue"), button[type="submit"]').first
                    await self.take_screenshot(page, 3, "before_login_click")
                    
                    await dev_button.click()
                    print("✓ Clicked login button")
                    
                    # Wait for navigation
                    await page.wait_for_load_state('networkidle', timeout=10000)
                    await self.describe_page(page)
                    await self.take_screenshot(page, 3, "after_login")
                    
                    # Verify we're on dashboard
                    if "/dashboard" in page.url or "/library" in page.url:
                        print("✅ Successfully logged in and redirected to dashboard")
                    else:
                        print(f"⚠️  Warning: Expected redirect to /dashboard, but at {page.url}")
                
                # STEP 4: Dashboard
                self.log(4, "Dashboard")
                await self.describe_page(page)
                await self.take_screenshot(page, 4, "dashboard")
                
                # Look for upload/start learning button
                upload_buttons = await page.locator('button:has-text("Upload"), a:has-text("Upload"), button:has-text("Start Learning"), a[href*="upload"]').count()
                print(f"Upload/Start buttons found: {upload_buttons}")
                
                if upload_buttons > 0:
                    upload_btn = page.locator('button:has-text("Upload"), a:has-text("Upload"), button:has-text("Start Learning"), a[href*="upload"]').first
                    await upload_btn.click()
                    await page.wait_for_load_state('networkidle')
                    print("✓ Clicked upload button")
                
                # STEP 5: Upload Page
                self.log(5, "Upload Page")
                await page.goto(f"{self.base_url}/library/upload")
                await page.wait_for_load_state('networkidle')
                await self.describe_page(page)
                await self.take_screenshot(page, 5, "upload_page")
                
                # STEP 6: Upload a Book (verification only)
                self.log(6, "Verify Upload Form")
                file_inputs = await page.locator('input[type="file"]').count()
                title_inputs = await page.locator('input[placeholder*="title" i], input[name*="title" i]').count()
                author_inputs = await page.locator('input[placeholder*="author" i], input[name*="author" i]').count()
                
                print(f"File inputs: {file_inputs}")
                print(f"Title inputs: {title_inputs}")
                print(f"Author inputs: {author_inputs}")
                
                if file_inputs > 0:
                    print("✅ Upload form rendered correctly with file input")
                else:
                    print("❌ ERROR: No file input found on upload page")
                
                await self.take_screenshot(page, 6, "upload_form")
                
                # STEP 7: Test Learn Page with Existing Book (CRITICAL TEST)
                self.log(7, "Test Learn Page with Existing Book (CRITICAL)")
                learn_url = f"{self.base_url}/learn/{self.test_book_id}"
                print(f"Navigating to: {learn_url}")
                
                await page.goto(learn_url)
                await page.wait_for_load_state('networkidle', timeout=15000)
                
                current_url = page.url
                print(f"Current URL after navigation: {current_url}")
                
                if "/login" in current_url:
                    print("❌ CRITICAL FAILURE: Redirected to /login - Auth fix did NOT work!")
                    await self.take_screenshot(page, 7, "FAILED_redirected_to_login")
                elif "/learn/" in current_url:
                    print("✅ SUCCESS: Learn page loaded without redirect to login!")
                    await self.describe_page(page)
                    
                    # Look for chat interface
                    chat_messages = await page.locator('[class*="message"], [class*="chat"]').count()
                    chat_input = await page.locator('textarea, input[placeholder*="message" i], input[placeholder*="type" i]').count()
                    
                    print(f"Chat messages visible: {chat_messages}")
                    print(f"Chat input found: {chat_input}")
                    
                    if chat_input > 0:
                        print("✅ Chat interface is present")
                    else:
                        print("⚠️  Warning: No chat input found")
                    
                    await self.take_screenshot(page, 7, "learn_page_SUCCESS")
                else:
                    print(f"⚠️  Warning: Unexpected URL: {current_url}")
                    await self.take_screenshot(page, 7, "learn_page_unexpected")
                
                # STEP 8: Send a Chat Message
                self.log(8, "Send a Chat Message")
                
                chat_input = page.locator('textarea, input[type="text"]').last
                chat_input_count = await page.locator('textarea, input[type="text"]').count()
                
                if chat_input_count > 0:
                    message = "I want to learn this in 2 days, spending 30 minutes each day. I'm a beginner."
                    await chat_input.fill(message)
                    print(f"✓ Typed message: {message}")
                    
                    # Find send button
                    send_button = page.locator('button[type="submit"], button:has-text("Send")').last
                    await self.take_screenshot(page, 8, "before_send")
                    
                    await send_button.click()
                    print("✓ Clicked send button")
                    
                    # Wait for response (with longer timeout)
                    await page.wait_for_timeout(3000)
                    await self.describe_page(page)
                    await self.take_screenshot(page, 8, "after_first_message")
                else:
                    print("❌ ERROR: No chat input found to send message")
                    await self.take_screenshot(page, 8, "no_chat_input")
                
                # STEP 9: Continue the Conversation
                self.log(9, "Continue the Conversation")
                
                # Wait a bit for professor to respond
                await page.wait_for_timeout(5000)
                
                if chat_input_count > 0:
                    chat_input = page.locator('textarea, input[type="text"]').last
                    followup = "Friendly style please, and quiz me after each chapter"
                    await chat_input.fill(followup)
                    print(f"✓ Typed follow-up: {followup}")
                    
                    send_button = page.locator('button[type="submit"], button:has-text("Send")').last
                    await send_button.click()
                    print("✓ Clicked send button")
                    
                    await page.wait_for_timeout(3000)
                    await self.describe_page(page)
                    await self.take_screenshot(page, 9, "after_second_message")
                
                # STEP 10: Test Plan Page
                self.log(10, "Test Plan Page")
                plan_url = f"{self.base_url}/learn/{self.test_book_id}/plan"
                print(f"Navigating to: {plan_url}")
                
                await page.goto(plan_url)
                await page.wait_for_load_state('networkidle')
                
                current_url = page.url
                print(f"Current URL: {current_url}")
                
                if "/login" in current_url:
                    print("❌ FAILURE: Plan page redirected to /login")
                    await self.take_screenshot(page, 10, "plan_FAILED_redirect")
                else:
                    print("✅ SUCCESS: Plan page loaded without redirect")
                    await self.describe_page(page)
                    await self.take_screenshot(page, 10, "plan_page")
                
                # STEP 11: Test Configure Page
                self.log(11, "Test Configure Page")
                config_url = f"{self.base_url}/learn/{self.test_book_id}/configure"
                print(f"Navigating to: {config_url}")
                
                await page.goto(config_url)
                await page.wait_for_load_state('networkidle')
                
                current_url = page.url
                print(f"Current URL: {current_url}")
                
                if "/login" in current_url:
                    print("❌ FAILURE: Configure page redirected to /login")
                    await self.take_screenshot(page, 11, "configure_FAILED_redirect")
                else:
                    print("✅ SUCCESS: Configure page loaded without redirect")
                    await self.describe_page(page)
                    await self.take_screenshot(page, 11, "configure_page")
                
                print("\n" + "="*80)
                print("TEST COMPLETE!")
                print(f"Screenshots saved to: {self.screenshots_dir}/")
                print("="*80)
                
                # Keep browser open for 10 seconds so you can review
                await page.wait_for_timeout(10000)
                
            except Exception as e:
                print(f"\n❌ TEST FAILED WITH ERROR: {str(e)}")
                await self.take_screenshot(page, 99, "ERROR")
                raise
            finally:
                await context.close()
                await browser.close()


async def main():
    test = E2ETest()
    await test.run_test()


if __name__ == "__main__":
    print("="*80)
    print("Professor App - End-to-End Browser Test")
    print("="*80)
    print("\nMake sure:")
    print("  1. Frontend is running at http://localhost:3000")
    print("  2. Backend is running at http://localhost:8000")
    print("  3. You have installed: pip install playwright pytest-playwright")
    print("  4. You have run: playwright install chromium")
    print("\nStarting test in 3 seconds...\n")
    
    import time
    time.sleep(3)
    
    try:
        asyncio.run(main())
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)
