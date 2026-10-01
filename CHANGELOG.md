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
- `--no-bundle`, `--output-dir` and `--no-zip` flags; menu entry 4 in the
  double-click runner scripts asks for a year and builds the bundle

### Changed

- Transactions after the filed year are ignored, so a problem in newer data cannot
  abort a run for a year that is already closed
- Events carry the document, sheet and row they were parsed from

## [0.1.0] - 2026-02-05

### Added

- Initial release
- Austrian tax calculation using Moving Average Cost Basis method
- E-Trade integration for RSU and ESPP data download
- ECB exchange rate fetching for USD/EUR conversion
- PDF report generation
- RSU confirmation PDF parsing
- Interactive CLI for non-developers
