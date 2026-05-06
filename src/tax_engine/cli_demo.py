"""
Demo script to run the tax engine with sample data.

This script demonstrates the tax engine functionality using the sample data
that was previously in main.py. Use this to see the example calculations.
"""

import argparse
from datetime import datetime

from tax_engine import (
    TaxEngine,
    create_sample_events_with_ecb_rates,
    prefetch_ecb_rates,
)


def main() -> None:
    """Run the tax engine with sample data using ECB rates."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Austrian Tax Engine Demo with Sample Data"
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Filter output to a specific tax year (e.g., --year 2021)",
    )
    args = parser.parse_args()

    print("Austrian Tax Engine for E-Trade RSUs and ESPP")
    print("Using Moving Average Cost Basis (Gleitender Durchschnittspreis)")
    print("\n** DEMO MODE: Using sample data **")
    if args.year:
        print(f"Filtering to year: {args.year}")
    print()

    # Create events without FX rates - they'll be fetched from ECB
    events = create_sample_events_with_ecb_rates()

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

    # Print results
    engine.print_ledger(year=args.year)
    engine.print_tax_summary(year=args.year)

    # Show current state (only if not filtering by year)
    if not args.year:
        print(f"\nCurrent Position: {engine.state.total_shares} shares")
        print(f"Current Avg Cost: €{engine.state.avg_cost_eur:,.4f}")
        print(f"Total Portfolio Cost: €{engine.state.total_portfolio_cost_eur:,.4f}")

    # Generate PDF report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.year:
        pdf_path = f"tax_report_demo_{args.year}_{timestamp}.pdf"
    else:
        pdf_path = f"tax_report_demo_{timestamp}.pdf"
    print(f"\nGenerating PDF report at: {pdf_path}...")
    engine.generate_pdf_report(pdf_path, year=args.year)
    print("PDF generation complete.")


if __name__ == "__main__":
    main()
