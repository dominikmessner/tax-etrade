"""
Shared report flow used by the ``tax-engine`` and ``tax-demo`` commands.

Takes loaded events, resolves FX rates, runs the engine and emits the
console ledger, the yearly summary and the PDF report (or submission bundle).
"""

import argparse
from datetime import date, datetime
from pathlib import Path

from .bundle import BundleResult, build_bundle
from .ecb_rates import prefetch_ecb_rates
from .evidence import EvidenceIndex, build_evidence_index
from .models import StockEvent
from .tax_engine import TaxEngine

EXIT_OK = 0
EXIT_ERROR = 1


def add_year_argument(parser: argparse.ArgumentParser, example_year: int) -> None:
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help=f"Limit the report to a single tax year (e.g., --year {example_year})",
    )


def print_banner(year: int | None, extra_lines: tuple[str, ...] = ()) -> None:
    print("Austrian Tax Engine for E-Trade RSUs and ESPP")
    print("Using Moving Average Cost Basis (Gleitender Durchschnittspreis)")
    for line in extra_lines:
        print(line)
    if year is not None:
        print(f"Tax year: {year}")
    print()


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


def run_report(
    events: list[StockEvent],
    *,
    year: int | None,
    pdf_prefix: str,
    build_the_bundle: bool = False,
    output_dir: Path = Path("output"),
    make_zip: bool = True,
    with_evidence: bool = False,
) -> int:
    """
    Run the engine over ``events`` and produce console and PDF/bundle output.

    Returns a process exit code: non-zero if the requested year has no data or
    the PDF could not be written, so scripts and the menu wrappers can tell
    success from failure.
    """
    all_years = sorted({e.event_date.year for e in events})
    # When filing a single year, drop everything after it. Processing is
    # chronological, so later transactions cannot change that year's result - but a
    # problem in newer data (a sale that looks larger than the holding, say) would
    # otherwise abort a run for a year that is already closed.
    if year is not None:
        cutoff = date(year, 12, 31)
        dropped = [e for e in events if e.event_date > cutoff]
        events = [e for e in events if e.event_date <= cutoff]
        if dropped:
            print(
                f"Ignoring {len(dropped)} transaction(s) after {cutoff.isoformat()} "
                f"(not relevant to tax year {year})."
            )

    prefetch_ecb_rates(events)

    engine = TaxEngine()
    engine.process_all(events)

    if year is not None and year not in engine.yearly_summaries:
        available_years = sorted(set(engine.yearly_summaries) | set(all_years))
        print(f"\nError: No data found for year {year}")
        if available_years:
            print(f"Available years: {', '.join(map(str, available_years))}")
        else:
            print("No tax data available (no transactions processed)")
        return EXIT_ERROR

    evidence = (
        build_evidence_index(engine.processed_events, year)
        if year is not None and (with_evidence or build_the_bundle)
        else None
    )

    engine.print_ledger(year=year, evidence=evidence)
    engine.print_tax_summary(year=year)

    if year is not None:
        closing = engine.get_closing_position(year)
        print(f"Position on 31.12.{year}: {closing.total_shares} shares")
        print(f"Average cost carried into {year + 1}: €{closing.avg_cost_eur:,.4f}")
        print(f"Total cost basis: €{closing.total_portfolio_cost_eur:,.4f}")
    else:
        print(f"\nCurrent Position: {engine.state.total_shares} shares")
        print(f"Current Avg Cost: €{engine.state.avg_cost_eur:,.4f}")
        print(f"Total Portfolio Cost: €{engine.state.total_portfolio_cost_eur:,.4f}")

    if build_the_bundle and year is not None and evidence is not None:
        print_evidence_summary(evidence)
        print(f"\nBuilding submission bundle for {year}...")
        result = build_bundle(
            engine,
            year,
            evidence,
            output_dir=output_dir,
            make_zip=make_zip,
        )
        print_bundle_result(result)
        return EXIT_OK

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    year_part = f"_{year}" if year is not None else ""
    pdf_path = f"{pdf_prefix}{year_part}_{timestamp}.pdf"
    print(f"\nGenerating PDF report at: {pdf_path}...")
    if not engine.generate_pdf_report(pdf_path, year=year, evidence=evidence):
        print("PDF generation FAILED. See the messages above.")
        return EXIT_ERROR

    print("PDF generation complete.")
    return EXIT_OK
