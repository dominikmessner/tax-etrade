# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Single-year filing: `--year 2025` limits the calculation and the report to one
  tax year and builds a submission bundle under `output/Steuerakt_2025/`
- Submission bundle: every source document behind the filed year, numbered
  (Beleg-Nr.), plus a merged `Steuerakt_<year>_komplett.pdf`, a CSV index and a ZIP
- Report cites the Beleg-Nr. of each transaction's source document, and gained an
  opening position on 1 January, a closing position on 31 December, an appendix
  deriving the opening average cost, and a document index
- Printable extracts of the worksheet rows actually used from the ESPP and orders
  workbooks, marking which rows belong to the filed year
- `--no-bundle`, `--output-dir`, `--no-zip` and `--input-dir` flags; menu entry 4 in the
  double-click runner scripts asks for a year and builds the bundle
- Stock options exercise support: `EXERCISE` events from exercise confirmation PDFs, with same-day sales recorded as `SELL`
- `tax-download-options` console script
- `TAX_ENGINE_HISTORY_START` environment variable to override the download start date
- Documentation of the cost basis used for ESPP and options (FMV) and of the non-deductibility of fees

### Changed

- Transactions after the filed year are ignored, so a problem in newer data cannot
  abort a run for a year that is already closed
- Events carry the document, sheet and row they were parsed from
- Sell events use the execution date instead of the order date
- The engine can run with any subset of input sources; an ESPP file is no longer required
- `tax-engine` and `tax-demo` exit non-zero on failure (no input, unknown year, unreadable sell order, PDF export failure)
- `tax-download` and the individual `tax-download-*` commands exit non-zero when the session is missing or expired, or any file fails to download; `tax-download` still runs the remaining steps after a failure
- E-Trade download scripts share one Playwright module; the spinner wait no longer relies on fixed sleeps
- CI tests Python 3.10 through 3.13

### Fixed

- A sell order in `orders.xlsx` with an unreadable date, quantity or execution price now stops the run with an error listing every affected row, instead of crashing with a bare `InvalidOperation` (or, for dates and quantities, being silently skipped). Canceled (`--` quantity) and zero-quantity orders are still skipped
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
