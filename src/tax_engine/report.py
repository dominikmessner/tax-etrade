"""
Shared report flow used by the ``tax-engine`` and ``tax-demo`` commands.

Takes loaded events, resolves FX rates, runs the engine and emits the
console ledger, the yearly summary and the PDF report.
"""

import argparse
from datetime import datetime

from .ecb_rates import prefetch_ecb_rates
from .models import StockEvent
from .tax_engine import TaxEngine

EXIT_OK = 0
EXIT_ERROR = 1


def add_year_argument(parser: argparse.ArgumentParser, example_year: int) -> None:
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help=f"Filter output to a specific tax year (e.g., --year {example_year})",
    )


def print_banner(year: int | None, extra_lines: tuple[str, ...] = ()) -> None:
    print("Austrian Tax Engine for E-Trade RSUs and ESPP")
    print("Using Moving Average Cost Basis (Gleitender Durchschnittspreis)")
    for line in extra_lines:
        print(line)
    if year is not None:
        print(f"Filtering to year: {year}")
    print()


def run_report(events: list[StockEvent], *, year: int | None, pdf_prefix: str) -> int:
    """
    Run the engine over ``events`` and produce console and PDF output.

    Returns a process exit code: non-zero if the requested year has no data or
    the PDF could not be written, so scripts and the menu wrappers can tell
    success from failure.
    """
    prefetch_ecb_rates(events)

    engine = TaxEngine()
    engine.process_all(events)

    if year is not None and year not in engine.yearly_summaries:
        available_years = sorted(engine.yearly_summaries)
        print(f"\nError: No data found for year {year}")
        if available_years:
            print(f"Available years: {', '.join(map(str, available_years))}")
        else:
            print("No tax data available (no transactions processed)")
        return EXIT_ERROR

    engine.print_ledger(year=year)
    engine.print_tax_summary(year=year)

    if year is None:
        print(f"\nCurrent Position: {engine.state.total_shares} shares")
        print(f"Current Avg Cost: €{engine.state.avg_cost_eur:,.4f}")
        print(f"Total Portfolio Cost: €{engine.state.total_portfolio_cost_eur:,.4f}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    year_part = f"_{year}" if year is not None else ""
    pdf_path = f"{pdf_prefix}{year_part}_{timestamp}.pdf"
    print(f"\nGenerating PDF report at: {pdf_path}...")
    if not engine.generate_pdf_report(pdf_path, year=year):
        print("PDF generation FAILED. See the messages above.")
        return EXIT_ERROR

    print("PDF generation complete.")
    return EXIT_OK
