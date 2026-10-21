"""
Demo script to run the tax engine with sample data.

Demonstrates the tax engine using the built-in sample events, with FX rates
fetched from the ECB.
"""

import argparse

from .report import add_year_argument, print_banner, run_report
from .sample_data import create_sample_events_with_ecb_rates


def main() -> int:
    """Run the tax engine with sample data using ECB rates."""
    parser = argparse.ArgumentParser(description="Austrian Tax Engine Demo with Sample Data")
    add_year_argument(parser, example_year=2021)
    args = parser.parse_args()

    print_banner(args.year, extra_lines=("\n** DEMO MODE: Using sample data **",))

    events = create_sample_events_with_ecb_rates()
    return run_report(events, year=args.year, pdf_prefix="tax_report_demo")


if __name__ == "__main__":
    raise SystemExit(main())
