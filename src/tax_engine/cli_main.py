"""
Austrian Tax Engine for E-Trade RSUs and ESPP

Calculates capital gains tax using the Austrian moving average cost basis method
(Gleitender Durchschnittspreis) for stocks acquired through RSU vesting and ESPP purchases.

Main entry point for the application.
"""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd

from tax_engine import (
    EventType,
    StockEvent,
    TaxEngine,
    load_rsu_events,
    prefetch_ecb_rates,
)


def load_events_from_excel() -> list[StockEvent]:
    """
    Load stock events from the BenefitHistory.xlsx file.
    """
    excel_path = Path("input/espp/BenefitHistory.xlsx")

    # Read the ESPP sheet
    # The user mentioned the sheet is named "ESPP"
    try:
        df = pd.read_excel(excel_path, sheet_name="ESPP")
    except ValueError:
        print("Warning: Sheet 'ESPP' not found, attempting to read the first sheet.")
        df = pd.read_excel(excel_path, sheet_name=0)

    events = []

    for _, row in df.iterrows():
        # Filter for Purchase events
        if row.get("Record Type") != "Purchase":
            continue

        # Parse date
        # Format in Excel is like "05-DEC-2022"
        raw_date = row["Purchase Date"]
        if hasattr(raw_date, "date"):
            event_date = raw_date.date()
        else:
            event_date = datetime.strptime(str(raw_date).strip(), "%d-%b-%Y").date()

        # Parse quantity
        shares = Decimal(str(row["Purchased Qty."]).replace(",", ""))

        # Parse price (FMV at purchase date)
        # Format is like "$37.56"
        price_str = str(row["Purchase Date FMV"]).replace("$", "").replace(",", "").strip()
        price_usd = Decimal(price_str)

        event = StockEvent(
            event_date=event_date,
            event_type=EventType.BUY,
            shares=shares,
            price_usd=price_usd,
            notes="ESPP Purchase",
        )
        events.append(event)

    # Sort events by date
    events.sort(key=lambda x: x.event_date)

    return events


def load_orders_from_excel() -> list[StockEvent]:
    """
    Load sell orders from the orders.xlsx file.
    """
    excel_path = Path("input/orders/orders.xlsx")
    if not excel_path.exists():
        print(f"Warning: {excel_path} not found. No sell orders loaded.")
        return []

    df = pd.read_excel(excel_path)
    events = []

    for i, (_, row) in enumerate(df.iterrows()):
        # Parse date
        raw_date = row["Order Date"]
        if hasattr(raw_date, "date"):
            event_date = raw_date.date()
        else:
            # Format is MM/DD/YYYY (e.g. 12/22/2019)
            try:
                event_date = datetime.strptime(str(raw_date).strip(), "%m/%d/%Y").date()
            except ValueError:
                # Try alternate format just in case
                try:
                    event_date = datetime.strptime(str(raw_date).strip(), "%Y-%m-%d").date()
                except ValueError:
                    print(f"Error parsing date: {raw_date}")
                    continue

        # Parse quantity
        # row index + 1 for 0-based index, +1 for header row
        printable_index = i + 2
        sold_qty_str = str(row["Sold Qty."]).replace(",", "").strip()
        if sold_qty_str == "--":
            print(f"Skipping row #{printable_index}: canceled order")
            continue

        try:
            shares = Decimal(sold_qty_str)
        except InvalidOperation:
            print(f"Error parsing quantity in row #{printable_index}: {sold_qty_str}")
            continue

        # Parse price
        price_str = str(row["Execution Price"]).replace("$", "").replace(",", "").strip()
        price_usd = Decimal(price_str)

        event = StockEvent(
            event_date=event_date,
            event_type=EventType.SELL,
            shares=shares,
            price_usd=price_usd,
            notes="Sell Order",
        )
        events.append(event)

    return events


def main() -> None:
    """Run the tax engine with actual data from Excel files."""
    print("Austrian Tax Engine for E-Trade RSUs and ESPP")
    print("Using Moving Average Cost Basis (Gleitender Durchschnittspreis)")
    print()

    # Load events from Excel file
    excel_path = Path("input/espp/BenefitHistory.xlsx")
    if not excel_path.exists():
        print(f"Error: {excel_path} not found")
        print("\nTo run the sample example, use: uv run tax-demo")
        return

    espp_events = load_events_from_excel()
    sell_events = load_orders_from_excel()
    rsu_events = load_rsu_events()

    # Combine and sort all events
    events = espp_events + sell_events + rsu_events

    # Sort by date, then by event type (BUY/VEST before SELL) to handle same-day transactions
    # We want VEST/BUY to happen before SELL so we have inventory to sell
    def event_sort_key(event: StockEvent) -> tuple[date, int]:
        # Priority: VEST/BUY = 0, SELL = 1
        type_priority = 1 if event.event_type == EventType.SELL else 0
        return (event.event_date, type_priority)

    events.sort(key=event_sort_key)

    # Pre-fetch all ECB rates in one API call (more efficient)
    prefetch_ecb_rates(events)

    # Create engine and process events
    engine = TaxEngine()
    engine.process_all(events)

    # Print results
    engine.print_ledger()
    engine.print_tax_summary()

    # Show current state
    print(f"\nCurrent Position: {engine.state.total_shares} shares")
    print(f"Current Avg Cost: €{engine.state.avg_cost_eur:,.4f}")
    print(f"Total Portfolio Cost: €{engine.state.total_portfolio_cost_eur:,.4f}")

    # Generate PDF report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pdf_path = f"tax_report_{timestamp}.pdf"
    print(f"Generating PDF report at: {pdf_path}...")
    engine.generate_pdf_report(pdf_path)
    print("PDF generation complete.")


if __name__ == "__main__":
    main()
