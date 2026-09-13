"""
Austrian Tax Engine for E-Trade RSUs and ESPP

Calculates capital gains tax using the Austrian moving average cost basis method
(Gleitender Durchschnittspreis) for stocks acquired through RSU vesting and ESPP purchases.

Main entry point for the application.
"""

import argparse
from pathlib import Path

from .loaders import (
    DEFAULT_INPUT_DIR,
    ESPP_FILE,
    OPTIONS_DIR,
    ORDERS_FILE,
    RSU_DIR,
    load_all_events,
)
from .report import EXIT_ERROR, add_year_argument, print_banner, run_report


def main() -> int:
    """Run the tax engine with actual data from the downloaded E-Trade files."""
    parser = argparse.ArgumentParser(description="Austrian Tax Engine for E-Trade RSUs and ESPP")
    add_year_argument(parser, example_year=2025)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help=f"Directory containing the downloaded E-Trade files (default: {DEFAULT_INPUT_DIR})",
    )
    args = parser.parse_args()

    print_banner(args.year)

    events = load_all_events(args.input_dir)
    if not events:
        print(f"Error: no transactions found under {args.input_dir}/")
        print("Expected at least one of:")
        expected = [
            (str(args.input_dir / ESPP_FILE), "ESPP purchases"),
            (str(args.input_dir / ORDERS_FILE), "sell orders"),
            (f"{args.input_dir / RSU_DIR}/*.pdf", "RSU confirmations"),
            (f"{args.input_dir / OPTIONS_DIR}/*.pdf", "options confirmations"),
        ]
        width = max(len(path) for path, _ in expected)
        for path, description in expected:
            print(f"  {path:<{width}}  ({description})")
        print("\nRun `tax-download` to fetch them, or `tax-demo` to see sample output.")
        return EXIT_ERROR

    return run_report(events, year=args.year, pdf_prefix="tax_report")


if __name__ == "__main__":
    raise SystemExit(main())
