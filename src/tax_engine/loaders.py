"""
Loaders that turn downloaded E-Trade files into StockEvent objects.

Every loader takes an explicit path and returns an empty list when the file
or directory is missing, so users who only have one kind of benefit (for
example RSUs but no ESPP) can still run the engine.
"""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

from .models import EventType, StockEvent
from .options_parser import load_options_events
from .rsu_parser import load_rsu_events

DEFAULT_INPUT_DIR = Path("input")

# Paths relative to the input directory, as written by the download scripts.
ESPP_FILE = Path("espp") / "BenefitHistory.xlsx"
ORDERS_FILE = Path("orders") / "orders.xlsx"
RSU_DIR = Path("rsu")
OPTIONS_DIR = Path("options")

_MISSING_CELL_MARKERS = ("", "--", "N/A", "nan", "None")


def _is_blank(raw: object) -> bool:
    """True for None, NaN/NaT and empty strings as read from a spreadsheet."""
    if raw is None:
        return True
    if isinstance(raw, str):
        return raw.strip() == ""
    if isinstance(raw, float):
        return raw != raw  # NaN
    return raw is pd.NaT


def _clean_number(raw: object) -> str:
    """Strip currency symbols and thousands separators from a spreadsheet cell."""
    return str(raw).replace("$", "").replace(",", "").strip()


def _parse_decimal(raw: object) -> Decimal | None:
    """Parse a spreadsheet cell to a finite Decimal, or None if it is blank/invalid."""
    if _is_blank(raw):
        return None
    cleaned = _clean_number(raw)
    if cleaned in _MISSING_CELL_MARKERS:
        return None
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def _parse_date(raw: object, formats: tuple[str, ...]) -> date | None:
    """Parse a spreadsheet cell to a date, accepting pandas timestamps or strings."""
    if _is_blank(raw):
        return None
    if hasattr(raw, "date"):
        parsed: date = raw.date()
        return parsed
    text = str(raw).strip()
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def load_espp_events_from_excel(excel_path: Path) -> list[StockEvent]:
    """
    Load ESPP purchase events from the BenefitHistory.xlsx file.

    The cost basis used is the fair market value on the purchase date, not the
    discounted price paid; see docs/TAX_CALCULATION_METHOD.md for why.
    """
    if not excel_path.exists():
        print(f"Warning: {excel_path} not found. No ESPP purchases loaded.")
        return []

    try:
        df = pd.read_excel(excel_path, sheet_name="ESPP")
    except ValueError:
        print("Warning: Sheet 'ESPP' not found, attempting to read the first sheet.")
        df = pd.read_excel(excel_path, sheet_name=0)

    events: list[StockEvent] = []

    for i, (_, row) in enumerate(df.iterrows()):
        row_num = i + 2  # Excel row number (1-based + header)

        if row.get("Record Type") != "Purchase":
            continue

        event_date = _parse_date(row.get("Purchase Date"), ("%d-%b-%Y",))
        if event_date is None:
            print(f"Warning: Missing or invalid purchase date in row {row_num}, skipping.")
            continue

        shares = _parse_decimal(row.get("Purchased Qty."))
        if shares is None or shares <= 0:
            print(f"Warning: Invalid quantity in row {row_num}, skipping.")
            continue

        price_usd = _parse_decimal(row.get("Purchase Date FMV"))
        if price_usd is None or price_usd <= 0:
            print(f"Warning: Invalid price in row {row_num}, skipping.")
            continue

        events.append(
            StockEvent(
                event_date=event_date,
                event_type=EventType.BUY,
                shares=shares,
                price_usd=price_usd,
                notes="ESPP Purchase",
            )
        )

    return events


def load_orders_from_excel(excel_path: Path) -> list[StockEvent]:
    """Load sell orders from the orders.xlsx file."""
    if not excel_path.exists():
        print(f"Warning: {excel_path} not found. No sell orders loaded.")
        return []

    df = pd.read_excel(excel_path)
    events: list[StockEvent] = []

    for i, (_, row) in enumerate(df.iterrows()):
        row_num = i + 2  # Excel row number (1-based + header)

        # Stock Options rows are covered by the options confirmation PDFs
        # (see load_options_stock_events), so skip them here.
        if str(row.get("Benefit Type", "")).strip() == "Stock Options":
            continue

        # Prefer Execution Date (actual trade date) over Order Date (when the
        # order was placed). Older downloads may only have Order Date.
        raw_date = row.get("Execution Date") if "Execution Date" in row.index else None
        if _is_blank(raw_date):
            raw_date = row.get("Order Date")
        event_date = _parse_date(raw_date, ("%m/%d/%Y", "%Y-%m-%d"))
        if event_date is None:
            print(f"Error parsing date in row #{row_num}: {raw_date!r}")
            continue

        raw_qty = row.get("Sold Qty.")
        if _clean_number(raw_qty) == "--":
            print(f"Skipping row #{row_num}: canceled order")
            continue
        shares = _parse_decimal(raw_qty)
        if shares is None:
            print(f"Error parsing quantity in row #{row_num}: {raw_qty!r}")
            continue
        if shares <= 0:
            print(f"Skipping row #{row_num}: zero quantity")
            continue

        raw_price = row.get("Execution Price")
        price_usd = _parse_decimal(raw_price)
        if price_usd is None or price_usd <= 0:
            print(f"Skipping row #{row_num}: no execution price ({raw_price!r})")
            continue

        events.append(
            StockEvent(
                event_date=event_date,
                event_type=EventType.SELL,
                shares=shares,
                price_usd=price_usd,
                notes="Sell Order",
            )
        )

    return events


def load_options_stock_events(options_dir: Path) -> list[StockEvent]:
    """
    Convert options exercise confirmations into StockEvent objects.

    Each exercise creates an EXERCISE event (acquisition at FMV).
    Same-day sales additionally create a SELL event at the sale price.
    """
    events: list[StockEvent] = []

    for ex in load_options_events(options_dir):
        events.append(
            StockEvent(
                event_date=ex.exercise_date,
                event_type=EventType.EXERCISE,
                shares=ex.shares_exercised,
                price_usd=ex.fmv_usd,
                notes=f"Options Exercise (strike ${ex.grant_price_usd}, {ex.exercise_type})",
            )
        )

        if ex.exercise_type == "Same-Day Sale" and ex.sale_price_usd and ex.shares_sold:
            events.append(
                StockEvent(
                    event_date=ex.exercise_date,
                    event_type=EventType.SELL,
                    shares=ex.shares_sold,
                    price_usd=ex.sale_price_usd,
                    notes=f"Options Same-Day Sale (order {ex.order_number})",
                )
            )

    return events


def load_all_events(input_dir: Path = DEFAULT_INPUT_DIR) -> list[StockEvent]:
    """Load every supported event type found under ``input_dir``."""
    return (
        load_espp_events_from_excel(input_dir / ESPP_FILE)
        + load_orders_from_excel(input_dir / ORDERS_FILE)
        + load_rsu_events(input_dir / RSU_DIR)
        + load_options_stock_events(input_dir / OPTIONS_DIR)
    )
