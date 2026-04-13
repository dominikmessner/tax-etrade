import contextlib
import os
import time
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright

SESSION_FILE = "input/etrade_session.json"
TARGET_URL = "https://us.etrade.com/etx/sp/stockplan#/myAccount/orders"
OUTPUT_DIR = Path("input/orders")
OUTPUT_FILE = OUTPUT_DIR / "orders.xlsx"


def _get_execution_date(row, order_date: str, page) -> str:  # type: ignore[no-untyped-def]
    """Click the row to expand its detail, read execution dates from Order History,
    verify they all fall on the same calendar date, and return that date string.
    Falls back to order_date if anything goes wrong.

    HTML structure (from DevTools inspection):
      div[data-test-id="orders.ordertbl.odrhistoryexpand"]
        button[aria-expanded]   ← collapse/expand toggle
        div.collapse.in
          table[role="table"]
            tbody[role="rowgroup"]
              tr[role="row"]
                td.text-left[role="cell"]  ← "Order Placed" / "Order Executed"
                td.text-left[role="cell"]  ← "11/17/2025 09:30:00 AM ET"
                td.text-left[role="cell"]  ← sale quantity
                td.text-left[role="cell"]  ← price
    """
    # Click the expand chevron in the first cell of the row
    try:
        row.locator("td").first.click()
    except Exception as e:
        print(f"  WARNING: Could not click row to expand detail: {e}")
        return order_date

    # Wait for the Order History div to become visible
    order_history_div = page.locator('div[data-test-id="orders.ordertbl.odrhistoryexpand"]')
    try:
        order_history_div.wait_for(state="visible", timeout=5000)
    except Exception as e:
        print(f"  WARNING: Order History section did not appear: {e}")
        with contextlib.suppress(Exception):
            row.locator("td").first.click()
        return order_date

    # Find all "Order Executed" cells inside the Order History table
    try:
        executed_cells = (
            order_history_div.locator('td[role="cell"]').filter(has_text="Order Executed").all()
        )
    except Exception as e:
        print(f"  WARNING: Could not find Order Executed cells: {e}")
        with contextlib.suppress(Exception):
            row.locator("td").first.click()
        return order_date

    if not executed_cells:
        print(
            f"  WARNING: No 'Order Executed' entries found for order dated {order_date}, using Order Date."
        )
        with contextlib.suppress(Exception):
            row.locator("td").first.click()
        return order_date

    # Extract the date part (MM/DD/YYYY) from the adjacent "Date & Time" cell
    exec_dates: list[str] = []
    for exec_cell in executed_cells:
        try:
            # Date & Time is the immediately following sibling td
            date_text = exec_cell.locator("xpath=following-sibling::td[1]").inner_text().strip()
            # Format: "12/08/2025 02:52:41 PM ET" — take only the date part
            exec_dates.append(date_text.split()[0])
        except Exception as e:
            print(f"  WARNING: Could not read execution date cell: {e}")

    # Collapse the detail row again
    with contextlib.suppress(Exception):
        row.locator("td").first.click()

    if not exec_dates:
        print(
            f"  WARNING: Could not parse any execution dates for order {order_date}, using Order Date."
        )
        return order_date

    unique_dates = set(exec_dates)
    if len(unique_dates) > 1:
        print(
            f"  WARNING: Order placed on {order_date} has executions on MULTIPLE dates: "
            f"{sorted(unique_dates)}. Using the first execution date. "
            f"This order may need manual review."
        )

    return exec_dates[0]


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
        for i, row in enumerate(rows):
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
            order_date = cells[2].inner_text().strip()
            sold_qty = cells[8].inner_text().strip()
            exec_price = cells[9].inner_text().strip()

            print(
                f"  Row {i + 1}: {benefit_type} {order_date} qty={sold_qty} — fetching execution date..."
            )
            execution_date = _get_execution_date(row, order_date, page)

            if execution_date != order_date:
                print(f"    Order Date: {order_date}  →  Execution Date: {execution_date}")

            data.append(
                {
                    "Execution Date": execution_date,
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
