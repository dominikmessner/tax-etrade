# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Stock options exercise support: `EXERCISE` events from exercise confirmation PDFs, with same-day sales recorded as `SELL`
- `--year` flag on `tax-engine` and `tax-demo` to report a single tax year
- `--input-dir` flag on `tax-engine`
- `tax-download-options` console script
- `TAX_ENGINE_HISTORY_START` environment variable to override the download start date
- Documentation of the cost basis used for ESPP and options (FMV) and of the non-deductibility of fees

### Changed

- Sell events use the execution date instead of the order date
- The engine can run with any subset of input sources; an ESPP file is no longer required
- `tax-engine`, `tax-demo` and `tax-download` exit non-zero on failure (no input, unknown year, PDF export failure)
- The portfolio cost is tracked as a running total and the moving average is derived from it, removing a small rounding drift between the displayed total and the value used in calculations
- E-Trade download scripts share one Playwright module; the spinner wait no longer relies on fixed sleeps
- CI tests Python 3.10 through 3.13

### Fixed

- Blank or `--` execution prices in `orders.xlsx` are skipped instead of crashing with `InvalidOperation`
- NaN/inf values in spreadsheet cells are rejected with a readable error
- Looking up an unknown year no longer inserts a bogus year-0 summary
- Per-sale calculation details in the PDF use the recorded average cost instead of a value back-derived from the rounded gain
- Lint and formatting regressions that had left CI red
- Test suite no longer contacts the ECB API

## [0.1.0] - 2026-02-05

### Added

- Initial release
- Austrian tax calculation using Moving Average Cost Basis method
- E-Trade integration for RSU and ESPP data download
- ECB exchange rate fetching for USD/EUR conversion
- PDF report generation
- RSU confirmation PDF parsing
- Interactive CLI for non-developers
