"""
Download stock options exercise confirmation PDFs from E-Trade.

Uses the Stock Plan Confirmations page with the "Stock Options" (G) benefit type filter.
"""

import os
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright

SESSION_FILE = "input/etrade_session.json"
TARGET_URL = "https://us.etrade.com/etx/sp/stockplan#/myAccount/stockPlanConfirmations"
OUTPUT_DIR = Path("input/options")


def download_options_confirmations() -> None:
    if not os.path.exists(SESSION_FILE):
        print(f"Session file {SESSION_FILE} not found. Please run etrade_login.py first.")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)

        try:
            context = browser.new_context(storage_state=SESSION_FILE)
        except Exception as e:
            print(f"Error loading session: {e}")
            return

        page = context.new_page()
        print(f"Navigating to {TARGET_URL}")
        page.goto(TARGET_URL)

        try:
            page.wait_for_url(
                lambda url: "stockPlanConfirmations" in url and "login" not in url, timeout=10000
            )
            page.locator('[data-test-id="stockplanconf.benefittype"]').wait_for(timeout=10000)
        except Exception:
            print("Login session might be expired or page load failed.")
            browser.close()
            return

        print("Setting filters (Stock Options, from 2019)...")
        page.get_by_label("Year").select_option("Custom")

        start_date_input = page.get_by_role("textbox", name="Start date (format: MM/DD/YY)")
        start_date_input.click()
        start_date_input.dblclick()
        start_date_input.fill("01/01/19")

        # Select "Stock Options" benefit type (value = "G")
        page.locator('[data-test-id="stockplanconf.benefittype"]').get_by_label(
            "Benefit Type"
        ).select_option("G")

        page.locator('[data-test-id="Filter applybtn"]').click()

        # Wait for spinner to disappear
        for _ in range(30):
            displays = page.locator(".spinner-overlay-spinner").evaluate_all(
                "elements => elements.map(e => window.getComputedStyle(e).display)"
            )
            if all(d == "none" for d in displays):
                break
            time.sleep(1)

        # Click View All if available
        try:
            view_all_btn = page.get_by_role("button", name="View All", exact=True)
            if view_all_btn.is_visible():
                print("Clicking 'View All'...")
                view_all_btn.click()
                time.sleep(3)
        except Exception:
            pass

        # Find rows with download buttons
        rows = (
            page.locator("tr")
            .filter(has=page.locator('[data-test-id="Stockplanconfig.transactiontable.download"]'))
            .all()
        )

        print(f"Found {len(rows)} options confirmation(s).")

        for i, row in enumerate(rows):
            try:
                row_text = row.inner_text()
                date_match = re.search(r"(\d{2}/\d{2}/\d{4})", row_text)

                if not date_match:
                    print(f"Could not find date in row {i}, skipping.")
                    continue

                date_str = date_match.group(1)
                try:
                    date_obj = datetime.strptime(date_str, "%m/%d/%Y")
                    formatted_date = date_obj.strftime("%Y-%m-%d")
                except ValueError:
                    print(f"Error parsing date {date_str}, skipping.")
                    continue

                print(f"Checking confirmation for {formatted_date}...")

                with page.expect_popup() as popup_info:
                    row.locator(
                        '[data-test-id="Stockplanconfig.transactiontable.download"]'
                    ).click()

                popup = popup_info.value
                popup.wait_for_load_state()

                pdf_url = popup.url

                parsed_url = urlparse(pdf_url)
                query_params = parse_qs(parsed_url.query)
                c_id = query_params.get("cId", [""])[0]

                if not c_id:
                    c_id = str(int(time.time()))

                filename = f"Options_Confirmation_{formatted_date}_{c_id}.pdf"
                file_path = OUTPUT_DIR / filename

                if file_path.exists():
                    print(f"File {filename} already exists. Skipping.")
                    popup.close()
                    time.sleep(5)
                    continue

                print(f"Downloading {filename}...")

                response = page.context.request.get(pdf_url)

                if response.ok:
                    with open(file_path, "wb") as f:
                        f.write(response.body())
                    print(f"Saved to {file_path}")
                else:
                    print(f"Failed to download PDF: {response.status} {response.status_text}")

                popup.close()
                time.sleep(5)

            except Exception as e:
                print(f"Error processing row {i}: {e}")

        browser.close()


if __name__ == "__main__":
    download_options_confirmations()
