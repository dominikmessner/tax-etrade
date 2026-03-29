"""
Parser for E-Trade stock options exercise confirmation PDFs.

Extracts exercise date, shares, FMV (Exercise Market Value), strike price,
and sale price (for same-day sales) from the PDF table.
"""

import contextlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pdfplumber


@dataclass
class OptionsExercise:
    """Data extracted from a single options exercise confirmation PDF."""

    exercise_date: date
    exercise_type: str  # "Cash Exercise" or "Same-Day Sale"
    shares_exercised: Decimal
    fmv_usd: Decimal  # Exercise Market Value — used as cost basis
    grant_price_usd: Decimal  # Strike price — for documentation
    sale_price_usd: Decimal | None  # Only present for Same-Day Sale
    shares_sold: Decimal | None  # Only present for Same-Day Sale
    order_number: str
    source_file: str


def _parse_usd(value: str) -> Decimal | None:
    """Parse a dollar string like '$45.47' or '$1,178.80' to Decimal."""
    cleaned = value.replace("$", "").replace(",", "").strip()
    # Strip trailing parenthetical e.g. "$589.40 (Tax Rate / Taxable Gain)"
    cleaned = cleaned.split("(")[0].strip()
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def parse_options_pdf(pdf_path: Path) -> OptionsExercise | None:
    """
    Parse a single options exercise confirmation PDF.

    Returns an OptionsExercise dataclass or None if parsing fails.
    """
    try:
        pdf_context = pdfplumber.open(pdf_path)
    except Exception as e:
        print(f"Warning: Could not open {pdf_path.name}: {e}")
        return None

    with pdf_context as pdf:
        if not pdf.pages:
            print(f"Warning: No pages in {pdf_path.name}")
            return None

        page = pdf.pages[0]
        full_text = page.extract_text() or ""

        # Extract exercise date from text (format: MM/DD/YYYY after "Exercise Date:")
        date_match = re.search(r"Exercise Date:\s*(\d{2}/\d{2}/\d{4})", full_text)
        if not date_match:
            print(f"Warning: Could not find exercise date in {pdf_path.name}")
            return None
        exercise_date = datetime.strptime(date_match.group(1), "%m/%d/%Y").date()

        # Extract exercise type
        type_match = re.search(r"Exercise Type:\s*(.+?)(?:\s+Registration:|\n)", full_text)
        exercise_type = type_match.group(1).strip() if type_match else "Unknown"

        # Extract order number
        order_match = re.search(r"Order Number\s+(\d+)", full_text)
        order_number = order_match.group(1) if order_match else ""

        # Parse the exercise details table
        table_data: dict[str, str] = {}
        for table in page.extract_tables():
            for row in table:
                if row and len(row) >= 2 and row[0] and row[1]:
                    key = row[0].strip()
                    val = row[1].strip()
                    table_data[key] = val

        # Extract key fields from table
        fmv_str = table_data.get("Exercise Market Value", "")
        fmv_usd = _parse_usd(fmv_str)
        if fmv_usd is None:
            print(f"Warning: Could not parse Exercise Market Value '{fmv_str}' in {pdf_path.name}")
            return None

        grant_price_str = table_data.get("Grant Price", "")
        grant_price_usd = _parse_usd(grant_price_str) or Decimal("0")

        shares_str = table_data.get("Shares Exercised", "").replace(",", "")
        try:
            shares_exercised = Decimal(shares_str)
        except InvalidOperation:
            print(f"Warning: Could not parse Shares Exercised '{shares_str}' in {pdf_path.name}")
            return None

        # Same-day sale fields
        sale_price_usd: Decimal | None = None
        shares_sold: Decimal | None = None

        sale_price_str = table_data.get("Sale Price", "")
        if sale_price_str:
            sale_price_usd = _parse_usd(sale_price_str)

        shares_sold_str = table_data.get("Shares Sold", "").replace(",", "")
        if shares_sold_str:
            with contextlib.suppress(InvalidOperation):
                shares_sold = Decimal(shares_sold_str)

        return OptionsExercise(
            exercise_date=exercise_date,
            exercise_type=exercise_type,
            shares_exercised=shares_exercised,
            fmv_usd=fmv_usd,
            grant_price_usd=grant_price_usd,
            sale_price_usd=sale_price_usd,
            shares_sold=shares_sold,
            order_number=order_number,
            source_file=pdf_path.name,
        )


def load_options_events(options_dir: Path = Path("input/options")) -> list["OptionsExercise"]:
    """
    Load all options exercise confirmations from the given directory.

    Returns a list of OptionsExercise objects sorted by exercise date.
    """
    if not options_dir.exists():
        return []

    pdf_files = sorted(options_dir.glob("*.pdf"))
    if not pdf_files:
        return []

    print(f"Found {len(pdf_files)} options confirmation PDF(s).")

    exercises: list[OptionsExercise] = []
    for pdf_path in pdf_files:
        result = parse_options_pdf(pdf_path)
        if result:
            exercises.append(result)
            print(
                f"  {result.exercise_date} | {result.exercise_type} | "
                f"{result.shares_exercised} shares | FMV ${result.fmv_usd} | "
                f"Strike ${result.grant_price_usd}"
            )
        else:
            print(f"  Warning: Failed to parse {pdf_path.name}")

    exercises.sort(key=lambda e: e.exercise_date)
    return exercises
