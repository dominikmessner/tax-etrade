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
- **ecb_rates.py**: Fetches USD/EUR rates from ECB Statistical Data Warehouse
- **rsu_parser.py**: Parses RSU confirmation PDFs using regex
- **sample_data.py**: Creates sample events for testing/demo

## Key Tax Rules (Austrian Law)

- **Rule A**: Moving average recalculated on every acquisition (VEST/BUY)
- **Rule B**: Selling doesn't change the average cost, only reduces quantity  
- **Rule C**: Cannot sell more shares than currently held (depot check)
- **KESt Rate**: 27.5% on capital gains
- Losses can offset gains within the same year but cannot be carried forward
