# Austrian Tax Engine for E-Trade RSUs and ESPP

Calculates capital gains tax using the Austrian moving average cost basis method (Gleitender Durchschnittspreis) for stocks acquired through RSU vesting and ESPP purchases.

> ⚠️ **DISCLAIMER**: This software is provided "as is", without warranty of any kind. **Use at your own risk.** The calculations are based on my understanding of Austrian tax law and may contain errors. This tool is not a substitute for professional tax advice. Always verify the results with a qualified tax advisor (Steuerberater) before filing your tax return. The author(s) assume no liability for any financial losses, penalties, or other damages arising from the use of this software.

## Easy Start (Mac Users)

If you are not a developer, you can simply use the provided script:

1.  **Download the entire project** as a ZIP from GitHub (click "Code" → "Download ZIP") and extract it.
2.  Double-click the `run_tax_engine.command` file inside the extracted folder.
3.  It will automatically set up Python, install dependencies, and open a menu.
4.  Follow the menu options to Login, Download Data, and Calculate Tax.

*Note: The first time you run it, you might need to right-click and select "Open" if macOS warns about an unidentified developer, or allow it in System Settings.*

## Easy Start (Windows Users)

If you are not a developer, you can simply use the provided script:

1.  **Download the entire project** as a ZIP from GitHub (click "Code" → "Download ZIP") and extract it.
2.  Double-click the `run_tax_engine.bat` file inside the extracted folder.
3.  It will automatically set up Python, install dependencies, and open a menu.
4.  Follow the menu options to Login, Download Data, and Calculate Tax.

## Easy Start (Linux Users)

If you are not a developer, you can use the same script as Mac users:

1.  **Download the entire project** as a ZIP from GitHub (click "Code" → "Download ZIP") and extract it.
2.  Open a terminal in the extracted folder and run:
    ```bash
    chmod +x run_tax_engine.command
    ./run_tax_engine.command
    ```
3.  It will automatically set up Python, install dependencies, and open a menu.
4.  Follow the menu options to Login, Download Data, and Calculate Tax.

## Easy Start (Devcontainer)

In Visual Studio Code, open this workspace using the Dev Containers extension to run it inside the provided development container.

The container includes a lightweight desktop (fluxbox) and a Chromium browser installed via Playwright (will be installed after creating the container).

Security note: The container runs with elevated privileges so Playwright's Chromium can run correctly. This isolates the container's browser from your host browser but is not a hardened sandbox - do not rely on it as an unescapable security boundary for untrusted code.

Access the desktop:
- Open in a browser at http://localhost:6080
- Or connect with a VNC client on port 5901 (port may vary; check the VS Code "Ports" tab)

Start the download assistant (it opens the browser inside the container):
```bash
uv run tax-download
```

Use the assistant to log in to E-Trade and download the required files (ESPP history, Orders, RSU confirmations).

## Developer Quick Start

### 1. Setup environment

```bash
brew install uv
uv sync --all-extras
uv run pre-commit install
```

### 2. Run Demo
To see the tax engine in action with sample data:

```bash
uv run demo.py
```

### 3. Fetch Your Data
To automate downloading transaction history from E-Trade:

1.  **Install Playwright browsers** (first time only):
    ```bash
    uv run playwright install chromium
    ```

2.  **Run the download assistant**:
    ```bash
    uv run tax-download
    ```
    This will guide you through login and automatically download all required files (ESPP history, Orders, and RSU confirmations).

    Alternatively, you can run individual tasks:
    ```bash
    uv run tax-login
    uv run tax-download-espp
    uv run tax-download-orders
    uv run tax-download-rsu
    uv run tax-download-options
    ```

    The download scripts fetch history from 1 January 2019 onwards. If your plan is older, set `TAX_ENGINE_HISTORY_START` (format `MM/DD/YY`) before running them.

    The downloads land in `input/`:

    | Path | Contents | Required |
    |------|----------|----------|
    | `input/espp/BenefitHistory.xlsx` | ESPP purchases | only if you have ESPP |
    | `input/orders/orders.xlsx` | Sell orders | only if you sold shares |
    | `input/rsu/*.pdf` | RSU release confirmations | only if you have RSUs |
    | `input/options/*.pdf` | Options exercise confirmations | only if you have options |
    | `input/etrade_session.json` | Your logged-in E-Trade session (cookies) | created by `tax-login` |

    Any combination works; the engine simply skips sources that are not present.

### 4. Run Analysis
Once your data is in the `input/` directory:

```bash
uv run main.py                     # all years
uv run main.py --year 2025         # one tax year
uv run main.py --input-dir ~/data  # data somewhere else
```

It will print the ledger and yearly summary and write `tax_report_*.pdf`. The command exits with a non-zero status if no transactions were found, the requested year has no data, or the PDF could not be written.

## Filing in FinanzOnline

The tax report output includes the values you need for your Austrian tax return (Formulars E1 / E1kv):

| Kennzahl | Description | Value to enter |
|----------|-------------|----------------|
| **994**  | Realized gains from capital assets (Einkünfte aus Kapitalvermögen) | Total gains for the year |
| **892**  | Realized losses from capital assets (Verluste aus Kapitalvermögen) | Total losses for the year (as a negative number) |

These Kennzahlen are shown in both the console output and the generated PDF report.

## About the E-Trade login

`tax-login` opens a real, visible Chromium window for you to sign in (including MFA); the tool never sees your password. Be aware of two things:

- The browser is launched with settings that make it present as an ordinary desktop Chrome (for example hiding the `navigator.webdriver` flag), because E-Trade otherwise refuses to load the login page in an automated browser. Automated access may be restricted by E-Trade's terms of use; you are responsible for deciding whether to use it.
- The session is stored in `input/etrade_session.json`. That file grants access to your brokerage account for as long as the session is valid. It is excluded from git by `.gitignore`; do not copy it anywhere else and delete it when you are done.

## How It Works

For a detailed explanation of the tax calculation methodology, including the moving average cost basis formula, currency conversion, and practical examples, see the [Tax Calculation Method](docs/TAX_CALCULATION_METHOD.md) documentation.
