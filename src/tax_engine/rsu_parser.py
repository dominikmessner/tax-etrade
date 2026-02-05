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
            # Use flexible whitespace matching (\s+) to handle variations in PDF extraction
            date_match = re.search(r"Release\s+Date\s+(\d{2}-\d{2}-\d{4})", text)
            if not date_match:
                print(f"Warning: Could not find Release Date in {pdf_path.name}")
                return None

            date_str = date_match.group(1)
            try:
                event_date = datetime.strptime(date_str, "%m-%d-%Y").date()
            except ValueError as e:
                print(f"Warning: Invalid date format '{date_str}' in {pdf_path.name}: {e}")
                return None

            # Extract Shares Released
            # Example: Shares Released 63.0000 (may include commas for large numbers)
            shares_match = re.search(r"Shares\s+Released\s+([\d,\.]+)", text)
            if not shares_match:
                print(f"Warning: Could not find Shares Released in {pdf_path.name}")
                return None

            shares_str = shares_match.group(1).replace(",", "")
            try:
                shares = Decimal(shares_str)
                if shares <= 0:
                    print(f"Warning: Invalid shares value {shares} in {pdf_path.name}")
                    return None
            except Exception as e:
                print(f"Warning: Could not parse shares '{shares_str}' in {pdf_path.name}: {e}")
                return None

            # Extract Market Value Per Share
            # Example: Market Value Per Share $46.680000
            price_match = re.search(r"Market\s+Value\s+Per\s+Share\s+\$?([\d,\.]+)", text)
            if not price_match:
                print(f"Warning: Could not find Market Value Per Share in {pdf_path.name}")
                return None

            price_str = price_match.group(1).replace(",", "")
            try:
                price_usd = Decimal(price_str)
                if price_usd <= 0:
                    print(f"Warning: Invalid price value {price_usd} in {pdf_path.name}")
                    return None
            except Exception as e:
                print(f"Warning: Could not parse price '{price_str}' in {pdf_path.name}: {e}")
                return None

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
