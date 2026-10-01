"""
Austrian Tax Engine for E-Trade RSUs and ESPP

Calculates capital gains tax using the Austrian moving average cost basis method
(Gleitender Durchschnittspreis) for stocks acquired through RSU vesting and ESPP purchases.

Main entry point for the application.
"""

import argparse
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
from tax_engine.bundle import BundleResult, build_bundle
from tax_engine.evidence import EvidenceIndex, build_evidence_index
from tax_engine.options_parser import load_options_events


def load_events_from_excel() -> list[StockEvent]:
    """
    Load stock events from the BenefitHistory.xlsx file.
    """
    excel_path = Path("input/espp/BenefitHistory.xlsx")

    # Read the ESPP sheet
    # The user mentioned the sheet is named "ESPP"
    # sheet_name is recorded on each event so the bundle can quote the right sheet;
    # None means "the first sheet", the same fallback used here.
    sheet_name: str | None = "ESPP"
    try:
        df = pd.read_excel(excel_path, sheet_name="ESPP")
    except ValueError:
        print("Warning: Sheet 'ESPP' not found, attempting to read the first sheet.")
        df = pd.read_excel(excel_path, sheet_name=0)
        sheet_name = None

    events = []

    for i, (_, row) in enumerate(df.iterrows()):
        row_num = i + 2  # Excel row number (1-based + header)

        # Filter for Purchase events
        if row.get("Record Type") != "Purchase":
            continue

        try:
            # Parse date
            # Format in Excel is like "05-DEC-2022"
            raw_date = row["Purchase Date"]
            if pd.isna(raw_date):
                print(f"Warning: Empty purchase date in row {row_num}, skipping.")
                continue
            if hasattr(raw_date, "date"):
                event_date = raw_date.date()
            else:
                event_date = datetime.strptime(str(raw_date).strip(), "%d-%b-%Y").date()

            # Parse quantity
            qty_str = str(row["Purchased Qty."]).replace(",", "").strip()
            if pd.isna(row["Purchased Qty."]) or qty_str in ("", "--", "N/A"):
                print(f"Warning: Invalid quantity in row {row_num}, skipping.")
                continue
            shares = Decimal(qty_str)

            # Parse price (FMV at purchase date)
            # Format is like "$37.56"
            price_raw = row["Purchase Date FMV"]
            if pd.isna(price_raw):
                print(f"Warning: Empty price in row {row_num}, skipping.")
                continue
            price_str = str(price_raw).replace("$", "").replace(",", "").strip()
            if price_str in ("", "--", "N/A"):
                print(f"Warning: Invalid price '{price_raw}' in row {row_num}, skipping.")
                continue
            price_usd = Decimal(price_str)

        except (ValueError, InvalidOperation) as e:
            print(f"Error parsing ESPP row {row_num}: {e}")
            continue

        event = StockEvent(
            event_date=event_date,
            event_type=EventType.BUY,
            shares=shares,
            price_usd=price_usd,
            notes="ESPP Purchase",
            source_document=excel_path.as_posix(),
            source_reference=(
                f"sheet '{sheet_name}', row {row_num}" if sheet_name else f"row {row_num}"
            ),
            source_sheet=sheet_name,
            source_row=row_num,
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
        # Excel row number (1-based + header)
        row_num = i + 2

        # Parse date
        # Prefer Execution Date (actual trade date) over Order Date (when order was placed).
        # Older downloads may only have Order Date — fall back gracefully.
        raw_date = row.get("Execution Date") if "Execution Date" in row.index else None
        if raw_date is None or pd.isna(raw_date):
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

        # Skip Stock Options rows — same-day sales are already captured from
        # the options confirmation PDFs via load_options_stock_events()
        benefit_type = str(row.get("Benefit Type", "")).strip()
        if benefit_type == "Stock Options":
            continue

        # Parse quantity
        printable_index = row_num
        sold_qty_str = str(row["Sold Qty."]).replace(",", "").strip()
        if sold_qty_str == "--":
            print(f"Skipping row #{printable_index}: canceled order")
            continue

        try:
            shares = Decimal(sold_qty_str)
        except InvalidOperation:
            print(f"Error parsing quantity in row #{printable_index}: {sold_qty_str}")
            continue
        if shares <= 0:
            print(f"Skipping row #{printable_index}: zero quantity")
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
            source_document=excel_path.as_posix(),
            source_reference=f"row {row_num}",
            # The workbook has a single sheet; leaving it unset means "the first
            # sheet", which is what the loader itself reads.
            source_row=row_num,
        )
        events.append(event)

    return events


def load_options_stock_events() -> list[StockEvent]:
    """
    Convert options exercise confirmations into StockEvent objects.

    Each exercise creates an EXERCISE event (acquisition at FMV).
    Same-day sales additionally create a SELL event at the sale price.
    """
    exercises = load_options_events()
    events: list[StockEvent] = []

    for ex in exercises:
        # EXERCISE event: acquire shares at FMV (Exercise Market Value)
        # This is the cost basis for Austrian capital gains purposes.
        exercise_event = StockEvent(
            event_date=ex.exercise_date,
            event_type=EventType.EXERCISE,
            shares=ex.shares_exercised,
            price_usd=ex.fmv_usd,
            notes=f"Options Exercise (strike ${ex.grant_price_usd}, {ex.exercise_type})",
            source_document=ex.source_path or f"input/options/{ex.source_file}",
            source_reference="Exercise Confirmation",
        )
        events.append(exercise_event)

        # Same-day sale: also add a SELL event at the sale price
        if ex.exercise_type == "Same-Day Sale" and ex.sale_price_usd and ex.shares_sold:
            sell_event = StockEvent(
                event_date=ex.exercise_date,
                event_type=EventType.SELL,
                shares=ex.shares_sold,
                price_usd=ex.sale_price_usd,
                notes=f"Options Same-Day Sale (order {ex.order_number})",
                source_document=ex.source_path or f"input/options/{ex.source_file}",
                source_reference=f"Same-Day Sale, order {ex.order_number}",
            )
            events.append(sell_event)

    return events


def main() -> None:
    """Run the tax engine with actual data from Excel files."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Austrian Tax Engine for E-Trade RSUs and ESPP")
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Limit the report to a single tax year (e.g., --year 2025)",
    )
    parser.add_argument(
        "--bundle",
        dest="bundle",
        action="store_true",
        default=None,
        help="Build the submission bundle (report + every source document, "
        "numbered and merged into one PDF). On by default when --year is given.",
    )
    parser.add_argument(
        "--no-bundle",
        dest="bundle",
        action="store_false",
        help="Only print the report and write a single PDF, without the document bundle.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Where to write the submission bundle (default: ./output)",
    )
    parser.add_argument(
        "--no-zip",
        action="store_true",
        help="Do not create a ZIP archive of the bundle folder.",
    )
    args = parser.parse_args()

    # A bundle documents one tax year, so it needs --year.
    build_the_bundle = args.bundle if args.bundle is not None else args.year is not None
    if build_the_bundle and args.year is None:
        parser.error("--bundle requires --year (a bundle documents a single tax year)")

    print("Austrian Tax Engine for E-Trade RSUs and ESPP")
    print("Using Moving Average Cost Basis (Gleitender Durchschnittspreis)")
    if args.year:
        print(f"Tax year: {args.year}")
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
    options_events = load_options_stock_events()

    # Combine and sort all events
    events = espp_events + sell_events + rsu_events + options_events

    # When filing a single year, drop everything after it. Processing is
    # chronological, so later transactions cannot change that year's result - but a
    # problem in newer data (a sale that looks larger than the holding, say) would
    # otherwise abort a run for a year that is already closed.
    if args.year is not None:
        cutoff = date(args.year, 12, 31)
        dropped = [e for e in events if e.event_date > cutoff]
        events = [e for e in events if e.event_date <= cutoff]
        if dropped:
            print(
                f"Ignoring {len(dropped)} transaction(s) after {cutoff.isoformat()} "
                f"(not relevant to tax year {args.year})."
            )

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

    # Validate year filter if provided
    if args.year:
        if args.year not in engine.yearly_summaries:
            available_years = sorted(engine.yearly_summaries.keys())
            print(f"\nError: No data found for year {args.year}")
            if available_years:
                print(f"Available years: {', '.join(map(str, available_years))}")
            else:
                print("No tax data available (no sales transactions processed)")
            return

    # Index the documents behind this year's transactions so the report can cite them
    evidence = build_evidence_index(engine.processed_events, args.year) if args.year else None

    # Print results
    engine.print_ledger(year=args.year, evidence=evidence)
    engine.print_tax_summary(year=args.year)

    if args.year:
        closing = engine.get_closing_position(args.year)
        print(f"Position on 31.12.{args.year}: {closing.total_shares} shares")
        print(f"Average cost carried into {args.year + 1}: €{closing.avg_cost_eur:,.4f}")
        print(f"Total cost basis: €{closing.total_portfolio_cost_eur:,.4f}")
    else:
        print(f"\nCurrent Position: {engine.state.total_shares} shares")
        print(f"Current Avg Cost: €{engine.state.avg_cost_eur:,.4f}")
        print(f"Total Portfolio Cost: €{engine.state.total_portfolio_cost_eur:,.4f}")

    if build_the_bundle and evidence is not None:
        print_evidence_summary(evidence)
        print(f"\nBuilding submission bundle for {args.year}...")
        result = build_bundle(
            engine,
            args.year,
            evidence,
            output_dir=args.output_dir,
            make_zip=not args.no_zip,
        )
        print_bundle_result(result)
        return

    # Generate PDF report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.year:
        pdf_path = f"tax_report_{args.year}_{timestamp}.pdf"
    else:
        pdf_path = f"tax_report_{timestamp}.pdf"
    print(f"\nGenerating PDF report at: {pdf_path}...")
    engine.generate_pdf_report(pdf_path, year=args.year, evidence=evidence)
    print("PDF generation complete.")


def print_evidence_summary(evidence: EvidenceIndex) -> None:
    """List the documents the filed year relies on."""
    print("\n" + "=" * 100)
    print(f"DOCUMENT INDEX (BELEGVERZEICHNIS) - {evidence.year}")
    print("=" * 100)
    print(f"{'Beleg':<8} {'Document':<48} {'Date(s)':<25} {'Tx':>4} {'Role':<12}")
    print("-" * 100)
    for doc in evidence.documents:
        print(
            f"{doc.number:<8} {doc.name[:47]:<48} {doc.date_range:<25} "
            f"{doc.event_count:>4} {doc.role:<12}"
        )
    print("-" * 100)
    both = len(evidence.both_roles)
    overlap = f" ({both} of them cover both)" if both else ""
    print(
        f"{len(evidence.documents)} document(s) in total: "
        f"{len(evidence.primary)} cover {evidence.year} transactions, "
        f"{len(evidence.supporting)} cover the opening cost basis{overlap}."
    )
    for missing in evidence.missing:
        print(f"  WARNING: referenced document not found on disk: {missing}")
    if evidence.undocumented_events:
        print(f"  WARNING: {evidence.undocumented_events} transaction(s) have no source document.")
    print("=" * 100)


def print_bundle_result(result: BundleResult) -> None:
    """Report where the bundle landed."""
    print("\n" + "=" * 100)
    print(f"SUBMISSION BUNDLE - {result.year}")
    print("=" * 100)
    print(f"Folder:        {result.directory}")
    print(f"Tax report:    {result.report_pdf}")
    if result.merged_pdf:
        print(f"Submit this:   {result.merged_pdf}")
    if result.index_csv:
        print(f"Index (CSV):   {result.index_csv}")
    if result.zip_file:
        print(f"ZIP archive:   {result.zip_file}")
    print(f"Documents:     {len(result.documents)} filed under belege/")
    for warning in result.warnings:
        print(f"  WARNING: {warning}")
    print("=" * 100)


if __name__ == "__main__":
    main()
