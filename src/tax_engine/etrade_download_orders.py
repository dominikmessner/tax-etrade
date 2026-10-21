"""
Download the sell-order history from E-Trade into input/orders/orders.xlsx.

For every order the detail row is expanded to read the actual execution
date, which is what the tax engine needs (the order date can be weeks
earlier for limit orders).
"""

import contextlib
from pathlib import Path

import pandas as pd
from playwright.sync_api import Locator, Page

from .etrade_common import (
    SessionError,
    apply_history_filter,
    click_view_all,
    stockplan_page,
)

OUTPUT_DIR = Path("input/orders")
OUTPUT_FILE = OUTPUT_DIR / "orders.xlsx"

ORDER_HISTORY_SELECTOR = 'div[data-test-id="orders.ordertbl.odrhistoryexpand"]'
DETAIL_TIMEOUT_MS = 5_000

# 0-based column indices in the orders table.
COL_BENEFIT_TYPE = 1
COL_ORDER_DATE = 2
COL_SOLD_QTY = 8
COL_EXEC_PRICE = 9
MIN_CELLS_PER_ROW = 10


def _toggle_detail(row: Locator) -> None:
    """The first cell of a row carries the expand/collapse chevron."""
    row.locator("td").first.click()


def _collapse_detail(row: Locator, page: Page) -> None:
    """Collapse the detail panel only if it is actually open, so we never flip it open."""
    detail = page.locator(ORDER_HISTORY_SELECTOR)
    with contextlib.suppress(Exception):
        if detail.count() and detail.first.is_visible():
            _toggle_detail(row)


def _get_execution_date(row: Locator, order_date: str, page: Page) -> str:
    """
    Expand the row, read the execution date(s) from its Order History panel,
    collapse it again and return the date string (MM/DD/YYYY).

    Falls back to ``order_date`` if anything goes wrong.

    HTML structure (from DevTools inspection):
      div[data-test-id="orders.ordertbl.odrhistoryexpand"]
        button[aria-expanded]
        div.collapse.in
          table[role="table"] tbody tr[role="row"]
            td.text-left[role="cell"]  <- "Order Placed" / "Order Executed"
            td.text-left[role="cell"]  <- "11/17/2025 09:30:00 AM ET"
    """
    try:
        _toggle_detail(row)
    except Exception as e:
        print(f"  WARNING: Could not click row to expand detail: {e}")
        return order_date

    order_history_div = page.locator(ORDER_HISTORY_SELECTOR)
    try:
        order_history_div.wait_for(state="visible", timeout=DETAIL_TIMEOUT_MS)
        executed_cells = (
            order_history_div.locator('td[role="cell"]').filter(has_text="Order Executed").all()
        )
    except Exception as e:
        print(f"  WARNING: Order History section unavailable: {e}")
        _collapse_detail(row, page)
        return order_date

    exec_dates: list[str] = []
    for exec_cell in executed_cells:
        try:
            # Date & Time is the immediately following sibling td,
            # e.g. "12/08/2025 02:52:41 PM ET" — keep only the date part.
            date_text = exec_cell.locator("xpath=following-sibling::td[1]").inner_text().strip()
            exec_dates.append(date_text.split()[0])
        except Exception as e:
            print(f"  WARNING: Could not read execution date cell: {e}")

    _collapse_detail(row, page)

    if not exec_dates:
        print(
            f"  WARNING: No execution dates found for order dated {order_date}, using Order Date."
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
    try:
        with stockplan_page(
            "orders", ready=lambda p: p.locator('[data-test-id="orders.year"]')
        ) as page:
            apply_history_filter(
                page,
                year_select=page.locator('[data-test-id="orders.year"]').get_by_label("Year"),
            )
            click_view_all(page)

            print("Scraping table data...")
            rows = page.locator("table[role='table'] tbody tr").all()
            print(f"Found {len(rows)} rows.")

            data = []
            for i, row in enumerate(rows):
                cells = row.locator("td").all()
                if len(cells) < MIN_CELLS_PER_ROW:
                    continue

                benefit_type = cells[COL_BENEFIT_TYPE].inner_text().strip()
                order_date = cells[COL_ORDER_DATE].inner_text().strip()
                sold_qty = cells[COL_SOLD_QTY].inner_text().strip()
                exec_price = cells[COL_EXEC_PRICE].inner_text().strip()

                print(
                    f"  Row {i + 1}: {benefit_type} {order_date} qty={sold_qty} "
                    "— fetching execution date..."
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
            if not data:
                print("No data found.")
                return

            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(data).to_excel(OUTPUT_FILE, index=False)
            print(f"Saved orders to {OUTPUT_FILE}")
    except SessionError as e:
        print(e)


if __name__ == "__main__":
    download_orders()
