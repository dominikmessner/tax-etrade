import os
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright

SESSION_FILE = "input/etrade_session.json"
TARGET_URL = "https://us.etrade.com/etx/sp/stockplan#/myAccount/stockPlanConfirmations"
OUTPUT_DIR = Path("input/rsu")


def download_rsu_confirmations() -> None:
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

        # Wait for page load
        try:
            page.wait_for_url(
                lambda url: "stockPlanConfirmations" in url and "login" not in url, timeout=10000
            )
            page.locator('[data-test-id="stockplanconf.benefittype"]').wait_for(timeout=10000)
        except Exception:
            print("Login session might be expired or page load failed.")
            browser.close()
            return

        print("Setting filters...")
        # Select Custom Year
        page.get_by_label("Year").select_option("Custom")

        # Set Start Date
        start_date_input = page.get_by_role("textbox", name="Start date (format: MM/DD/YY)")
        start_date_input.click()
        start_date_input.dblclick()
        start_date_input.fill("12/22/19")

        # Select Benefit Type = RS (Restricted Stock)
        page.locator('[data-test-id="stockplanconf.benefittype"]').get_by_label(
            "Benefit Type"
        ).select_option("RS")

        # Click Apply
        page.locator('[data-test-id="Filter applybtn"]').click()

        # Wait for results
        time.sleep(2)

        # Click View All if available
        try:
            view_all_btn = page.get_by_role("button", name="View All", exact=True)
            if view_all_btn.is_visible():
                print("Clicking 'View All'...")
                view_all_btn.click()
                time.sleep(3)
        except Exception:
            pass

        print("Scanning for documents...")

        # Find all rows
        # We need to be careful to get the actual data rows.
        # Based on previous scripts, we can look for rows that have the download button.
        rows = (
            page.locator("tr")
            .filter(has=page.locator('[data-test-id="Stockplanconfig.transactiontable.download"]'))
            .all()
        )

        print(f"Found {len(rows)} potential documents.")

        for i, row in enumerate(rows):
            try:
                # Extract date from the first cell or text
                # The row text usually starts with the date, e.g. "11/15/2021 Restricted Stock ..."
                row_text = row.inner_text()
                # Try to find a date pattern MM/DD/YYYY
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

                # Click download to get the URL (and cId)
                with page.expect_popup() as popup_info:
                    row.locator(
                        '[data-test-id="Stockplanconfig.transactiontable.download"]'
                    ).click()

                popup = popup_info.value
                popup.wait_for_load_state()

                # The popup should be the PDF url
                pdf_url = popup.url

                # Extract cId from URL
                parsed_url = urlparse(pdf_url)
                query_params = parse_qs(parsed_url.query)
                c_id = query_params.get("cId", [""])[0]

                if not c_id:
                    print(f"Could not extract cId from URL: {pdf_url}. Using timestamp fallback.")
                    c_id = str(int(time.time()))

                # Construct filename with cId
                filename = f"RSU_Confirmation_{formatted_date}_{c_id}.pdf"
                file_path = OUTPUT_DIR / filename

                if file_path.exists():
                    print(f"File {filename} already exists. Skipping.")
                    popup.close()
                    continue

                print(f"Downloading {filename}...")

                # Download the file using the context request (preserves cookies)
                response = page.context.request.get(pdf_url)

                if response.ok:
                    with open(file_path, "wb") as f:
                        f.write(response.body())
                    print(f"Saved to {file_path}")
                else:
                    print(f"Failed to download PDF: {response.status} {response.status_text}")

                popup.close()

                # Sleep a bit to be nice to the server
                time.sleep(1)

            except Exception as e:
                print(f"Error processing row {i}: {e}")

        browser.close()


if __name__ == "__main__":
    download_rsu_confirmations()
