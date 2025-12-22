import os
import time
from playwright.sync_api import sync_playwright

SESSION_FILE = "input/etrade_session.json"
TARGET_URL = "https://us.etrade.com/etx/sp/stockplan#/myAccount/benefitHistory"

def login():
    with sync_playwright() as p:
        # Launch browser in headful mode so user can interact
        browser = p.chromium.launch(headless=False)
        
        # Load existing session if available
        if os.path.exists(SESSION_FILE):
            print(f"Loading session from {SESSION_FILE}")
            context = browser.new_context(storage_state=SESSION_FILE)
        else:
            print("Starting new session")
            context = browser.new_context()
            
        page = context.new_page()
        
        print(f"Navigating to {TARGET_URL}")
        page.goto(TARGET_URL)
        
        # Check if we are redirected to login
        # The URL might change immediately, so we wait a bit or check current url
        time.sleep(2)
        
        if "login" in page.url:
            print("Login required. Please log in manually in the browser window.")
            print("Waiting for successful login...")
            
            # Wait until we are back at the target URL or a similar authenticated page
            # We use a timeout of 0 (infinite) or a very large number because MFA might take time
            try:
                page.wait_for_url(lambda url: "stockplan" in url and "login" not in url, timeout=300000) # 5 minutes timeout
                print("Login detected!")
            except Exception as e:
                print("Timeout or error waiting for login.")
                browser.close()
                return

        print("Successfully on the Stock Plan page.")
        
        # Save the session state
        context.storage_state(path=SESSION_FILE)
        print(f"Session saved to {SESSION_FILE}")
        
        # Keep browser open for a moment to see result
        time.sleep(2)
        browser.close()

if __name__ == "__main__":
    login()
