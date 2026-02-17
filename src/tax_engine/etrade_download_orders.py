import os
import time
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright

SESSION_FILE = "input/etrade_session.json"
TARGET_URL = "https://us.etrade.com/etx/sp/stockplan#/myAccount/orders"
OUTPUT_DIR = Path("input/orders")
OUTPUT_FILE = OUTPUT_DIR / "orders.xlsx"


def download_orders() -> None:
    if not os.path.exists(SESSION_FILE):
        print(f"Session file {SESSION_FILE} not found. Please run etrade_login.py first.")
        return

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
            page.wait_for_url(lambda url: "orders" in url and "login" not in url, timeout=10000)
            page.locator('[data-test-id="orders.year"]').wait_for(timeout=10000)
        except Exception:
            print("Login session might be expired or page load failed.")
            browser.close()
            return

        print("Setting filters...")
        # Select Custom Year
        page.locator('[data-test-id="orders.year"]').get_by_label("Year").select_option("Custom")

        # Set Start Date
        # We need to be careful with date pickers. The user suggested clicking/dblclicking/filling.
        start_date_input = page.get_by_role("textbox", name="Start date (format: MM/DD/YY)")
        start_date_input.click()
        start_date_input.dblclick()  # Select all existing text
        start_date_input.fill("01/01/19")

        # Click Apply
        page.locator('[data-test-id="Filter applybtn"]').click()

        # Wait for results to update
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
                # Wait for table to expand.
                # We can wait for the "Viewing X of X" text or just a static wait for now.
                time.sleep(3)
        except Exception as e:
            print(f"View All button not found or not clickable: {e}")

        print("Scraping table data...")

        # Extract data
        rows = page.locator("table[role='table'] tbody tr").all()
        print(f"Found {len(rows)} rows.")

        data = []
        for row in rows:
            # Skip if it's not a data row (e.g. if there are spacer rows, though the HTML showed spTableRow)
            # The HTML shows class="spTableRow"

            cells = row.locator("td").all()
            if len(cells) < 10:
                continue

            # Indices (0-based from locator list):
            # Benefit Type: 1
            # Order Date: 2
            # Sold Qty: 8
            # Execution Price: 9

            benefit_type = cells[1].inner_text().strip()
            if "Stock Options" in benefit_type:
                print(f"Skipping Stock Options order on {cells[2].inner_text().strip()}")
                continue

            order_date = cells[2].inner_text().strip()
            sold_qty = cells[8].inner_text().strip()
            exec_price = cells[9].inner_text().strip()

            # Only keep rows that have valid data (e.g. Sold Qty > 0)
            # But maybe we want all orders. The user asked for "Sell orders".
            # Let's just grab everything for now and filter later if needed.

            data.append(
                {
                    "Order Date": order_date,
                    "Sold Qty.": sold_qty,
                    "Execution Price": exec_price,
                    "Benefit Type": benefit_type,
                }
            )

        print(f"Extracted {len(data)} records.")

        if data:
            df = pd.DataFrame(data)
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            df.to_excel(OUTPUT_FILE, index=False)
            print(f"Saved orders to {OUTPUT_FILE}")
        else:
            print("No data found.")

        browser.close()


if __name__ == "__main__":
    download_orders()
