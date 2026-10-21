# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `--year 2025` calculates and reports a single tax year and builds a submission
  bundle in `output/Steuerakt_2025/`: every source document, numbered, merged into
  one PDF, plus a CSV index and a ZIP
- The report shows the opening and closing position of the year and refers to each
  transaction's source document by its number
- `--no-bundle`, `--output-dir`, `--no-zip` and `--input-dir` options; menu entry 4
  builds the bundle for a year you enter
- Stock options support, including same-day sales, and a `tax-download-options` command

### Changed

- Sales use the execution date instead of the order date
- An ESPP file is no longer required; any combination of ESPP, RSU, options and sales works
- Commands exit with an error code when something fails, e.g. no input data, an
  expired E-Trade login, a failed download or a failed PDF export

### Fixed

- A sale with a missing price, date or quantity stops the run with a list of the
  affected rows instead of crashing or being left out of the report
- The per-sale details in the PDF show the exact average cost used for the calculation

## [0.1.0] - 2026-02-05

### Added

- Initial release
- Austrian tax calculation using Moving Average Cost Basis method
- E-Trade integration for RSU and ESPP data download
- ECB exchange rate fetching for USD/EUR conversion
- PDF report generation
- RSU confirmation PDF parsing
- Interactive CLI for non-developers
