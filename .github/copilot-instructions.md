# Copilot Instructions for Tax Engine

## Project Overview

This is an **Austrian Tax Engine** that calculates capital gains tax using the **Moving Average Cost Basis method** (Gleitender Durchschnittspreis) required by Austrian tax law. It processes stock transactions from E-Trade (RSU vesting, ESPP purchases, and sales).

## Running Commands

- **Always use `uv run`** to execute Python commands (not `pip`, `python`, or `python3`)
- Run tests: `uv run pytest tests/ -v`
- Run the app: `uv run python main.py`

## Architecture Notes

- **models.py**: Data classes (`StockEvent`, `ProcessedEvent`, `YearlyTaxSummary`, `TaxEngineState`)
- **tax_engine.py**: Core calculation logic using moving average cost basis
- **ecb_rates.py**: Fetches USD/EUR rates from the ECB Data Portal; `prefetch_ecb_rates()` pins rates on events
- **loaders.py**: Turns downloaded Excel/PDF files into `StockEvent`s; every loader takes a path and returns `[]` if it is missing
- **rsu_parser.py** / **options_parser.py**: Parse confirmation PDFs
- **report.py**: Shared ledger/summary/PDF flow used by `cli_main.py` and `cli_demo.py`
- **etrade_common.py**: Shared Playwright plumbing for the `etrade_download_*.py` scrapers
- **sample_data.py**: Creates sample events for testing/demo

## Conventions

- All money and share amounts are `Decimal`; quantize with `MONEY_PRECISION` and `ROUND_HALF_UP`
- Tests must not touch the network; pytest turns `LazyFxRateWarning` into an error
- CLI `main()` functions return an exit code

## Key Tax Rules (Austrian Law)

- **Rule A**: Moving average recalculated on every acquisition (VEST/BUY)
- **Rule B**: Selling doesn't change the average cost, only reduces quantity
- **Rule C**: Cannot sell more shares than currently held (depot check)
- **KESt Rate**: 27.5% on capital gains
- Losses can offset gains within the same year but cannot be carried forward
