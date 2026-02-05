import os
import shutil
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

SESSION_FILE = "input/etrade_session.json"
TARGET_URL = "https://us.etrade.com/etx/sp/stockplan#/myAccount/benefitHistory"
DOWNLOAD_DIR = Path("input/espp")
TARGET_FILENAME = "BenefitHistory.xlsx"

def backup_existing_file(file_path: Path):
    if file_path.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = file_path.with_name(f"{file_path.stem}_{timestamp}{file_path.suffix}")
        print(f"Backing up existing file to {backup_path}")
        shutil.move(str(file_path), str(backup_path))

def download_benefit_history():
    if not os.path.exists(SESSION_FILE):
        print(f"Session file {SESSION_FILE} not found. Please run etrade_login.py first.")
        return

    with sync_playwright() as p:
        # Headless=False is useful to see what's happening, but can be set to True later
        browser = p.chromium.launch(headless=False)

        try:
            context = browser.new_context(storage_state=SESSION_FILE)
        except Exception as e:
            print(f"Error loading session: {e}")
            print("Please run etrade_login.py to create a new session.")
            return

        page = context.new_page()

        print(f"Navigating to {TARGET_URL}")
        page.goto(TARGET_URL)

        # Wait for the page to load and check if we are logged in
        # We wait for the Download button to be visible as a sign of successful load
        try:
            # Wait for URL to be correct (not login)
            page.wait_for_url(lambda url: "stockplan" in url and "login" not in url, timeout=10000)
            # Wait for the specific element we need
            page.get_by_role("button", name="Download").wait_for(timeout=10000)
        except Exception:
            print("Login session might be expired, invalid, or page took too long to load.")
            print("Please run etrade_login.py again.")
            browser.close()
            return

        print("Downloading Benefit History...")

        try:
            # Click Download button
            page.get_by_role("button", name="Download").click()

            # Click Download Expanded and wait for download
            with page.expect_download() as download_info:
                page.get_by_role("menuitem", name="Download Expanded").click()

            download = download_info.value
            print(f"Download started: {download.suggested_filename}")

            # Prepare target path
            DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
            target_path = DOWNLOAD_DIR / TARGET_FILENAME

            # Backup existing file
            backup_existing_file(target_path)

            # Save new file
            download.save_as(target_path)
            print(f"Successfully saved to {target_path}")

        except Exception as e:
            print(f"Error during download: {e}")

        # Give it a second before closing
        page.wait_for_timeout(2000)
        browser.close()

if __name__ == "__main__":
    download_benefit_history()
