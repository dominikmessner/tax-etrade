"""
Shared Playwright plumbing for the E-Trade Stock Plan download scripts.

All scrapers open the same site with the same saved session, apply the same
"Custom" date filter and wait for the same loading spinner; this module holds
that logic once so selector fixes land in one place.
"""

import re
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Locator, Page, sync_playwright

SESSION_FILE = Path("input/etrade_session.json")
STOCKPLAN_BASE_URL = "https://us.etrade.com/etx/sp/stockplan#/myAccount/"

# E-Trade's "Custom" year filter needs an explicit start date (MM/DD/YY).
HISTORY_START = "01/01/19"

SPINNER_SELECTOR = ".spinner-overlay-spinner"
PAGE_LOAD_TIMEOUT_MS = 10_000
SPINNER_TIMEOUT_MS = 30_000
# Pause between PDF downloads so we do not hammer E-Trade's document service.
REQUEST_DELAY_SECONDS = 5

DOWNLOAD_BUTTON_SELECTOR = '[data-test-id="Stockplanconfig.transactiontable.download"]'
BENEFIT_TYPE_SELECTOR = '[data-test-id="stockplanconf.benefittype"]'
APPLY_FILTER_SELECTOR = '[data-test-id="Filter applybtn"]'


class DownloadError(RuntimeError):
    """A download step did not fetch everything it was supposed to."""


class SessionError(DownloadError):
    """The saved E-Trade session is missing, invalid or expired."""


def run_download(step: Callable[[], None]) -> int:
    """Run a download step as a console command and return its exit code."""
    try:
        step()
    except Exception as e:
        print(f"Download failed: {e}")
        return 1
    return 0


@contextmanager
def stockplan_page(section: str, ready: Callable[[Page], Locator]) -> Iterator[Page]:
    """
    Open ``STOCKPLAN_BASE_URL + section`` in a visible Chromium using the saved
    session and yield the page once ``ready(page)`` is attached.

    Raises SessionError if there is no session or the site bounced us to login.
    The browser is always closed on exit.
    """
    if not SESSION_FILE.exists():
        raise SessionError(f"Session file {SESSION_FILE} not found. Please run tax-login first.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        try:
            try:
                context = browser.new_context(storage_state=str(SESSION_FILE))
            except Exception as e:
                raise SessionError(f"Error loading session: {e}. Please run tax-login.") from e

            page = context.new_page()
            url = STOCKPLAN_BASE_URL + section
            print(f"Navigating to {url}")
            page.goto(url)

            try:
                page.wait_for_url(
                    lambda u: section in u and "login" not in u, timeout=PAGE_LOAD_TIMEOUT_MS
                )
                ready(page).wait_for(timeout=PAGE_LOAD_TIMEOUT_MS)
            except Exception as e:
                raise SessionError(
                    "Login session might be expired or the page failed to load. "
                    "Please run tax-login again."
                ) from e

            yield page
        finally:
            browser.close()


def wait_for_spinner(page: Page, timeout_ms: int = SPINNER_TIMEOUT_MS) -> None:
    """Block until every loading spinner on the page is hidden."""
    try:
        page.wait_for_function(
            "sel => Array.from(document.querySelectorAll(sel))"
            ".every(e => getComputedStyle(e).display === 'none')",
            arg=SPINNER_SELECTOR,
            timeout=timeout_ms,
        )
    except Exception:
        print(f"  WARNING: loading spinner still visible after {timeout_ms // 1000}s; continuing.")


def apply_history_filter(
    page: Page,
    *,
    year_select: Locator,
    benefit_type: str | None = None,
) -> None:
    """Select the "Custom" year range from ``HISTORY_START`` and apply it."""
    print("Setting filters...")
    year_select.select_option("Custom")

    start_date_input = page.get_by_role("textbox", name="Start date (format: MM/DD/YY)")
    start_date_input.click()
    start_date_input.dblclick()  # select any existing text so fill() replaces it
    start_date_input.fill(HISTORY_START)

    if benefit_type is not None:
        page.locator(BENEFIT_TYPE_SELECTOR).get_by_label("Benefit Type").select_option(benefit_type)

    page.locator(APPLY_FILTER_SELECTOR).click()
    wait_for_spinner(page)


def click_view_all(page: Page) -> None:
    """Expand a paginated table to show every row, if the button is present."""
    view_all_btn = page.get_by_role("button", name="View All", exact=True)
    try:
        if view_all_btn.count() == 0 or not view_all_btn.first.is_visible():
            return
        print("Clicking 'View All'...")
        view_all_btn.first.click()
        wait_for_spinner(page)
        page.wait_for_load_state("networkidle", timeout=PAGE_LOAD_TIMEOUT_MS)
    except Exception as e:
        print(f"  WARNING: 'View All' did not complete cleanly: {e}")


def download_confirmations(
    *,
    benefit_type: str,
    output_dir: Path,
    filename_prefix: str,
    label: str,
) -> None:
    """
    Download every confirmation PDF of ``benefit_type`` from the Stock Plan
    Confirmations page into ``output_dir``.

    Files are named ``{prefix}_{YYYY-MM-DD}_{cId}.pdf`` and skipped if already
    present, so the script is safe to re-run. Every row is attempted; if any
    fails, DownloadError is raised at the end.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    with stockplan_page(
        "stockPlanConfirmations", ready=lambda p: p.locator(BENEFIT_TYPE_SELECTOR)
    ) as page:
        apply_history_filter(page, year_select=page.get_by_label("Year"), benefit_type=benefit_type)
        click_view_all(page)

        print(f"Scanning for {label} documents...")
        rows = page.locator("tr").filter(has=page.locator(DOWNLOAD_BUTTON_SELECTOR)).all()
        print(f"Found {len(rows)} potential documents.")

        failures = 0
        for i, row in enumerate(rows):
            try:
                _download_row(page, row, output_dir, filename_prefix)
            except Exception as e:
                failures += 1
                print(f"Error processing row {i}: {e}")

    if failures:
        raise DownloadError(
            f"{failures} of {len(rows)} {label} confirmation(s) could not be downloaded"
        )


def _download_row(page: Page, row: Locator, output_dir: Path, filename_prefix: str) -> None:
    row_text = row.inner_text()
    date_match = re.search(r"(\d{2}/\d{2}/\d{4})", row_text)
    if not date_match:
        raise DownloadError(f"no date found in row {row_text[:80]!r}")

    try:
        formatted_date = datetime.strptime(date_match.group(1), "%m/%d/%Y").strftime("%Y-%m-%d")
    except ValueError as e:
        raise DownloadError(f"unparseable date {date_match.group(1)!r}") from e

    print(f"Checking confirmation for {formatted_date}...")

    # Clicking the download icon opens the PDF in a popup; its URL carries the
    # document id (cId) we use to build a stable filename.
    with page.expect_popup() as popup_info:
        row.locator(DOWNLOAD_BUTTON_SELECTOR).click()
    popup = popup_info.value
    try:
        popup.wait_for_load_state()
        pdf_url = popup.url

        c_id = parse_qs(urlparse(pdf_url).query).get("cId", [""])[0]
        if not c_id:
            print(f"Could not extract cId from URL: {pdf_url}. Using timestamp fallback.")
            c_id = str(int(time.time()))

        file_path = output_dir / f"{filename_prefix}_{formatted_date}_{c_id}.pdf"
        if file_path.exists():
            print(f"File {file_path.name} already exists. Skipping.")
            return

        print(f"Downloading {file_path.name}...")
        # Fetch via the browser context so the session cookies are sent.
        response = page.context.request.get(pdf_url)
        if not response.ok:
            raise DownloadError(f"{file_path.name}: HTTP {response.status} {response.status_text}")
        file_path.write_bytes(response.body())
        print(f"Saved to {file_path}")
    finally:
        popup.close()
        time.sleep(REQUEST_DELAY_SECONDS)
