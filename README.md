# Austrian Tax Engine for E-Trade RSUs and ESPP

Calculates capital gains tax using the Austrian moving average cost basis method (Gleitender Durchschnittspreis) for stocks acquired through RSU vesting and ESPP purchases.

## Quick Start

## 1. Setup environment

```bash
brew install uv
uv sync
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
    uv run tax-download-all
    ```
    This will guide you through login and automatically download all required files (ESPP history, Orders, and RSU confirmations).

    Alternatively, you can run individual tasks:
    ```bash
    uv run tax-login
    uv run tax-espp
    uv run tax-orders
    uv run tax-rsu
    ```

### 4. Run Analysis
Once your data is in the `input/` directory:

```bash
uv run main.py
```

It will generate a pdf file tax_report_*.pdf
