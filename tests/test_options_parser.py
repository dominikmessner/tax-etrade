"""
Unit tests for the stock options PDF parser.

Uses mocked pdfplumber to test parsing logic without real PDF files.
Covers both Cash Exercise and Same-Day Sale confirmation formats.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from tax_engine.options_parser import load_options_events, parse_options_pdf

# =============================================================================
# Helpers
# =============================================================================


def _make_mock_pdf(text: str, tables: list[list[list[str]]]) -> MagicMock:
    """Create a mock pdfplumber PDF with the given text and tables."""
    mock_page = MagicMock()
    mock_page.extract_text.return_value = text
    mock_page.extract_tables.return_value = tables

    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page]
    mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
    mock_pdf.__exit__ = MagicMock(return_value=False)
    return mock_pdf


CASH_EXERCISE_TEXT = """
E*TRADE Securities LLC

Stock Option Exercise Confirmation

Exercise Date: 03/15/2022
Exercise Type: Cash Exercise         Registration: Individual
Order Number 11111111

This confirmation is for your records.
"""

CASH_EXERCISE_TABLES = [
    [
        ["Shares Exercised", "100"],
        ["Grant Price", "$10.00"],
        ["Exercise Market Value", "$50.00"],
    ]
]

SAME_DAY_SALE_TEXT = """
E*TRADE Securities LLC

Stock Option Exercise Confirmation

Exercise Date: 06/01/2023
Exercise Type: Same-Day Sale         Registration: Individual
Order Number 22222222

This confirmation is for your records.
"""

SAME_DAY_SALE_TABLES = [
    [
        ["Shares Exercised", "200"],
        ["Grant Price", "$10.00"],
        ["Exercise Market Value", "$60.00"],
        ["Sale Price", "$62.00"],
        ["Shares Sold", "200"],
    ]
]


# =============================================================================
# parse_options_pdf — Cash Exercise
# =============================================================================


class TestParseOptionsExerciseCash:
    """Tests for parsing Cash Exercise confirmation PDFs."""

    def test_parse_cash_exercise_date(self):
        """Exercise date is correctly extracted."""
        mock_pdf = _make_mock_pdf(CASH_EXERCISE_TEXT, CASH_EXERCISE_TABLES)
        with patch("pdfplumber.open", return_value=mock_pdf):
            result = parse_options_pdf(Path("cash_exercise.pdf"))

        assert result is not None
        assert result.exercise_date == date(2022, 3, 15)

    def test_parse_cash_exercise_type(self):
        """Exercise type is 'Cash Exercise'."""
        mock_pdf = _make_mock_pdf(CASH_EXERCISE_TEXT, CASH_EXERCISE_TABLES)
        with patch("pdfplumber.open", return_value=mock_pdf):
            result = parse_options_pdf(Path("cash_exercise.pdf"))

        assert result.exercise_type == "Cash Exercise"

    def test_parse_cash_exercise_shares(self):
        """Shares exercised are correctly extracted."""
        mock_pdf = _make_mock_pdf(CASH_EXERCISE_TEXT, CASH_EXERCISE_TABLES)
        with patch("pdfplumber.open", return_value=mock_pdf):
            result = parse_options_pdf(Path("cash_exercise.pdf"))

        assert result.shares_exercised == Decimal("100")

    def test_parse_cash_exercise_fmv(self):
        """FMV (Exercise Market Value) is the cost basis."""
        mock_pdf = _make_mock_pdf(CASH_EXERCISE_TEXT, CASH_EXERCISE_TABLES)
        with patch("pdfplumber.open", return_value=mock_pdf):
            result = parse_options_pdf(Path("cash_exercise.pdf"))

        assert result.fmv_usd == Decimal("50.00")

    def test_parse_cash_exercise_grant_price(self):
        """Strike (grant) price is correctly extracted."""
        mock_pdf = _make_mock_pdf(CASH_EXERCISE_TEXT, CASH_EXERCISE_TABLES)
        with patch("pdfplumber.open", return_value=mock_pdf):
            result = parse_options_pdf(Path("cash_exercise.pdf"))

        assert result.grant_price_usd == Decimal("10.00")

    def test_parse_cash_exercise_no_sale_fields(self):
        """Cash exercise has no sale price or shares sold."""
        mock_pdf = _make_mock_pdf(CASH_EXERCISE_TEXT, CASH_EXERCISE_TABLES)
        with patch("pdfplumber.open", return_value=mock_pdf):
            result = parse_options_pdf(Path("cash_exercise.pdf"))

        assert result.sale_price_usd is None
        assert result.shares_sold is None

    def test_parse_cash_exercise_order_number(self):
        """Order number is extracted from the text."""
        mock_pdf = _make_mock_pdf(CASH_EXERCISE_TEXT, CASH_EXERCISE_TABLES)
        with patch("pdfplumber.open", return_value=mock_pdf):
            result = parse_options_pdf(Path("cash_exercise.pdf"))

        assert result.order_number == "11111111"

    def test_parse_cash_exercise_source_file(self):
        """Source file name is stored on the result."""
        mock_pdf = _make_mock_pdf(CASH_EXERCISE_TEXT, CASH_EXERCISE_TABLES)
        with patch("pdfplumber.open", return_value=mock_pdf):
            result = parse_options_pdf(Path("cash_exercise.pdf"))

        assert result.source_file == "cash_exercise.pdf"


# =============================================================================
# parse_options_pdf — Same-Day Sale
# =============================================================================


class TestParseOptionsSameDaySale:
    """Tests for parsing Same-Day Sale confirmation PDFs."""

    def test_parse_same_day_sale_type(self):
        """Exercise type is 'Same-Day Sale'."""
        mock_pdf = _make_mock_pdf(SAME_DAY_SALE_TEXT, SAME_DAY_SALE_TABLES)
        with patch("pdfplumber.open", return_value=mock_pdf):
            result = parse_options_pdf(Path("same_day_sale.pdf"))

        assert result is not None
        assert result.exercise_type == "Same-Day Sale"

    def test_parse_same_day_sale_shares(self):
        """Shares exercised and sold are both extracted."""
        mock_pdf = _make_mock_pdf(SAME_DAY_SALE_TEXT, SAME_DAY_SALE_TABLES)
        with patch("pdfplumber.open", return_value=mock_pdf):
            result = parse_options_pdf(Path("same_day_sale.pdf"))

        assert result.shares_exercised == Decimal("200")
        assert result.shares_sold == Decimal("200")

    def test_parse_same_day_sale_price(self):
        """Sale price is extracted for same-day sales."""
        mock_pdf = _make_mock_pdf(SAME_DAY_SALE_TEXT, SAME_DAY_SALE_TABLES)
        with patch("pdfplumber.open", return_value=mock_pdf):
            result = parse_options_pdf(Path("same_day_sale.pdf"))

        assert result.sale_price_usd == Decimal("62.00")

    def test_parse_same_day_sale_fmv(self):
        """FMV at exercise is correctly extracted as cost basis."""
        mock_pdf = _make_mock_pdf(SAME_DAY_SALE_TEXT, SAME_DAY_SALE_TABLES)
        with patch("pdfplumber.open", return_value=mock_pdf):
            result = parse_options_pdf(Path("same_day_sale.pdf"))

        assert result.fmv_usd == Decimal("60.00")


# =============================================================================
# parse_options_pdf — Missing / invalid data
# =============================================================================


class TestParseOptionsPdfInvalidCases:
    """Tests for graceful handling of missing or malformed data."""

    def test_parse_pdf_no_pages_returns_none(self):
        """PDF with no pages returns None."""
        mock_pdf = MagicMock()
        mock_pdf.pages = []
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)

        with patch("pdfplumber.open", return_value=mock_pdf):
            result = parse_options_pdf(Path("empty.pdf"))

        assert result is None

    def test_parse_pdf_missing_exercise_date_returns_none(self):
        """PDF without 'Exercise Date:' returns None."""
        text = "No date here at all.\n"
        mock_pdf = _make_mock_pdf(text, CASH_EXERCISE_TABLES)
        with patch("pdfplumber.open", return_value=mock_pdf):
            result = parse_options_pdf(Path("no_date.pdf"))

        assert result is None

    def test_parse_pdf_missing_fmv_returns_none(self):
        """PDF without Exercise Market Value returns None."""
        tables_without_fmv = [
            [
                ["Shares Exercised", "100"],
                ["Grant Price", "$10.00"],
                # No "Exercise Market Value" row
            ]
        ]
        mock_pdf = _make_mock_pdf(CASH_EXERCISE_TEXT, tables_without_fmv)
        with patch("pdfplumber.open", return_value=mock_pdf):
            result = parse_options_pdf(Path("no_fmv.pdf"))

        assert result is None

    def test_parse_pdf_missing_shares_returns_none(self):
        """PDF without Shares Exercised returns None."""
        tables_without_shares = [
            [
                ["Grant Price", "$10.00"],
                ["Exercise Market Value", "$50.00"],
                # No "Shares Exercised" row
            ]
        ]
        mock_pdf = _make_mock_pdf(CASH_EXERCISE_TEXT, tables_without_shares)
        with patch("pdfplumber.open", return_value=mock_pdf):
            result = parse_options_pdf(Path("no_shares.pdf"))

        assert result is None

    def test_parse_pdf_null_text_returns_none(self):
        """PDF with null text extraction returns None (no exercise date)."""
        mock_pdf = _make_mock_pdf(None, [])
        with patch("pdfplumber.open", return_value=mock_pdf):
            result = parse_options_pdf(Path("null_text.pdf"))

        assert result is None

    def test_parse_pdf_dollar_amounts_with_commas(self):
        """Dollar values with thousands separators are parsed correctly."""
        tables = [
            [
                ["Shares Exercised", "1,000"],
                ["Grant Price", "$10.00"],
                ["Exercise Market Value", "$1,234.56"],
            ]
        ]
        mock_pdf = _make_mock_pdf(CASH_EXERCISE_TEXT, tables)
        with patch("pdfplumber.open", return_value=mock_pdf):
            result = parse_options_pdf(Path("large_exercise.pdf"))

        assert result is not None
        assert result.shares_exercised == Decimal("1000")
        assert result.fmv_usd == Decimal("1234.56")


# =============================================================================
# load_options_events
# =============================================================================


class TestLoadOptionsEvents:
    """Tests for the load_options_events directory loader."""

    def test_load_nonexistent_directory_returns_empty(self, tmp_path):
        """Non-existent directory returns empty list without error."""
        result = load_options_events(tmp_path / "does_not_exist")
        assert result == []

    def test_load_empty_directory_returns_empty(self, tmp_path):
        """Empty directory returns empty list."""
        options_dir = tmp_path / "options"
        options_dir.mkdir()
        result = load_options_events(options_dir)
        assert result == []

    def test_load_skips_non_pdf_files(self, tmp_path):
        """Non-PDF files in the directory are ignored."""
        options_dir = tmp_path / "options"
        options_dir.mkdir()
        (options_dir / "notes.txt").write_text("irrelevant")

        result = load_options_events(options_dir)
        assert result == []

    def test_load_multiple_pdfs_sorted_by_date(self, tmp_path):
        """Multiple PDFs are loaded and sorted by exercise date."""
        options_dir = tmp_path / "options"
        options_dir.mkdir()
        (options_dir / "a.pdf").write_bytes(b"%PDF-1.4")
        (options_dir / "b.pdf").write_bytes(b"%PDF-1.4")

        # Return different dates depending on filename
        def mock_open(path):
            if "a.pdf" in str(path):
                text = SAME_DAY_SALE_TEXT  # 2023-06-01
                tables = SAME_DAY_SALE_TABLES
            else:
                text = CASH_EXERCISE_TEXT  # 2022-03-15
                tables = CASH_EXERCISE_TABLES
            return _make_mock_pdf(text, tables)

        with patch("pdfplumber.open", side_effect=mock_open):
            result = load_options_events(options_dir)

        assert len(result) == 2
        assert result[0].exercise_date == date(2022, 3, 15)  # cash exercise first
        assert result[1].exercise_date == date(2023, 6, 1)  # same-day sale second

    def test_load_handles_parsing_failure_gracefully(self, tmp_path):
        """A failed parse of one PDF doesn't prevent loading others."""
        options_dir = tmp_path / "options"
        options_dir.mkdir()
        (options_dir / "valid.pdf").write_bytes(b"%PDF-1.4")
        (options_dir / "corrupt.pdf").write_bytes(b"%PDF-1.4")

        def mock_open(path):
            if "corrupt" in str(path):
                raise Exception("Corrupted PDF")
            return _make_mock_pdf(CASH_EXERCISE_TEXT, CASH_EXERCISE_TABLES)

        with patch("pdfplumber.open", side_effect=mock_open):
            result = load_options_events(options_dir)

        assert len(result) == 1
        assert result[0].exercise_date == date(2022, 3, 15)
