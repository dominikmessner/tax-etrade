import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pdfplumber

from .models import EventType, StockEvent


def parse_rsu_pdf(pdf_path: Path) -> StockEvent | None:
    """
    Parse a single RSU confirmation PDF and return a StockEvent.
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            # Usually the content is on the first page
            if not pdf.pages:
                return None
            text = pdf.pages[0].extract_text()

            if not text:
                return None

            # Extract Release Date
            # Example: Release Date 05-15-2021
            date_match = re.search(r"Release Date\s+(\d{2}-\d{2}-\d{4})", text)
            if not date_match:
                print(f"Warning: Could not find Release Date in {pdf_path.name}")
                return None

            date_str = date_match.group(1)
            event_date = datetime.strptime(date_str, "%m-%d-%Y").date()

            # Debug
            # print(f"Parsed {pdf_path.name}: {event_date}")

            # Extract Shares Released
            # Example: Shares Released 63.0000
            shares_match = re.search(r"Shares Released\s+([\d\.]+)", text)
            if not shares_match:
                print(f"Warning: Could not find Shares Released in {pdf_path.name}")
                return None

            shares = Decimal(shares_match.group(1))

            # Extract Market Value Per Share
            # Example: Market Value Per Share $46.680000
            price_match = re.search(r"Market Value Per Share\s+\$?([\d\.]+)", text)
            if not price_match:
                print(f"Warning: Could not find Market Value Per Share in {pdf_path.name}")
                return None

            price_usd = Decimal(price_match.group(1))

            return StockEvent(
                event_date=event_date,
                event_type=EventType.VEST,
                shares=shares,
                price_usd=price_usd,
                notes=f"RSU Vest ({pdf_path.name})",
            )

    except Exception as e:
        print(f"Error parsing {pdf_path.name}: {e}")
        return None


def load_rsu_events(rsu_dir: Path = Path("input/rsu")) -> list[StockEvent]:
    """
    Load all RSU events from PDFs in the specified directory.
    """
    if not rsu_dir.exists():
        print(f"Warning: {rsu_dir} does not exist. No RSU events loaded.")
        return []

    events = []
    pdf_files = list(rsu_dir.glob("*.pdf"))

    print(f"Found {len(pdf_files)} RSU confirmation PDFs.")

    for pdf_file in pdf_files:
        event = parse_rsu_pdf(pdf_file)
        if event:
            events.append(event)

    return events
