# Austrian Tax Engine for E-Trade RSUs and ESPP

Calculates capital gains tax using the Austrian moving average cost basis method (Gleitender Durchschnittspreis) for stocks acquired through RSU vesting and ESPP purchases.

> ⚠️ **DISCLAIMER**: This software is provided "as is", without warranty of any kind. **Use at your own risk.** The calculations are based on my understanding of Austrian tax law and may contain errors. This tool is not a substitute for professional tax advice. Always verify the results with a qualified tax advisor (Steuerberater) before filing your tax return. The author(s) assume no liability for any financial losses, penalties, or other damages arising from the use of this software.

## Easy Start (Mac Users)

If you are not a developer, you can simply use the provided script:

1.  Double-click the `run_tax_engine.command` file in this folder.
2.  It will automatically set up Python, install dependencies, and open a menu.
3.  Follow the menu options to Login, Download Data, and Calculate Tax.

*Note: The first time you run it, you might need to right-click and select "Open" if macOS warns about an unidentified developer, or allow it in System Settings.*

## Easy Start (Windows Users)

If you are not a developer, you can simply use the provided script:

1.  Double-click the `run_tax_engine.bat` file in this folder.
2.  It will automatically set up Python, install dependencies, and open a menu.
3.  Follow the menu options to Login, Download Data, and Calculate Tax.

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
    ```

### 4. Run Analysis
Once your data is in the `input/` directory:

```bash
uv run main.py
```

It will generate a pdf file tax_report_*.pdf

## How It Works

For a detailed explanation of the tax calculation methodology, including the moving average cost basis formula, currency conversion, and practical examples, see the [Tax Calculation Method](docs/TAX_CALCULATION_METHOD.md) documentation.
