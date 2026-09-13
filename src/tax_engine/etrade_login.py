"""
Interactive login to E-Trade.

Opens a visible browser for the user to log in (including MFA) and stores the
resulting cookies/local storage in SESSION_FILE for the download scripts.

The browser is launched with a few settings that make it look like a regular
desktop Chrome rather than an automated one; without them E-Trade's login
page tends to refuse to load. See the README for the implications.
"""

import time

from playwright.sync_api import sync_playwright

from .etrade_common import SESSION_FILE, STOCKPLAN_BASE_URL

TARGET_URL = STOCKPLAN_BASE_URL + "benefitHistory"
LOGIN_TIMEOUT_MS = 300_000  # 5 minutes; MFA can take a while


def login() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",  # Hide automation flag
                "--disable-infobars",  # Remove "Chrome is being controlled" bar
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-extensions",
            ],
        )

        # Common browser context settings to appear more human
        context_options: dict[str, object] = {
            "viewport": {"width": 1920, "height": 1080},
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "locale": "en-US",
            "timezone_id": "America/New_York",
        }

        # Load existing session if available
        if SESSION_FILE.exists():
            print(f"Loading session from {SESSION_FILE}")
            context = browser.new_context(storage_state=str(SESSION_FILE), **context_options)  # pyright: ignore[reportArgumentType]
        else:
            print("Starting new session")
            context = browser.new_context(**context_options)  # pyright: ignore[reportArgumentType]

        # Remove webdriver property to avoid detection
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });

            // Override the plugins to appear more realistic
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });

            // Override languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
        """)

        page = context.new_page()

        print(f"Navigating to {TARGET_URL}")
        page.goto(TARGET_URL)

        # Check if we are redirected to login
        # The URL might change immediately, so we wait a bit or check current url
        time.sleep(2)

        if "login" in page.url:
            print("Login required. Please log in manually in the browser window.")
            print("Waiting for successful login...")

            try:
                page.wait_for_url(
                    lambda url: "stockplan" in url and "login" not in url,
                    timeout=LOGIN_TIMEOUT_MS,
                )
                print("Login detected!")
            except Exception:
                print("Timeout or error waiting for login.")
                browser.close()
                return

        print("Successfully on the Stock Plan page.")

        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(SESSION_FILE))
        print(f"Session saved to {SESSION_FILE}")

        # Keep browser open for a moment to see result
        time.sleep(2)
        browser.close()


if __name__ == "__main__":
    login()
