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
    InputDataError,
    load_all_events,
)
from .report import (
    EXIT_ERROR,
    add_year_argument,
    print_banner,
    print_bundle_result,
    print_evidence_summary,
    run_report,
)


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

    print_banner(args.year)

    try:
        events = load_all_events(args.input_dir)
    except InputDataError as e:
        print(f"Error: {e}")
        return EXIT_ERROR
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

    return run_report(
        events,
        year=args.year,
        pdf_prefix="tax_report",
        build_the_bundle=build_the_bundle,
        output_dir=args.output_dir,
        make_zip=not args.no_zip,
        with_evidence=args.year is not None,
    )


__all__ = ["main", "print_bundle_result", "print_evidence_summary"]


if __name__ == "__main__":
    raise SystemExit(main())
