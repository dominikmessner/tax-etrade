"""
Builds a submission bundle for a single tax year.

The bundle is a self-contained folder (plus a ZIP of it) holding:

- the tax report for the year, in which every transaction cites a Beleg-Nr.;
- every source document behind those transactions, filed under that Beleg-Nr.;
- for workbook sources (ESPP benefit history, sale orders) a printable extract of
  exactly the rows used, alongside the untouched original file;
- a document index as CSV;
- one merged PDF ("Steuerakt") containing the report and all documents in order,
  which is the single file to hand to the Finanzamt.
"""

import csv
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from html import escape
from pathlib import Path
from types import TracebackType
from typing import Any

import pandas as pd

from .evidence import EvidenceDocument, EvidenceIndex

# Shared styling for the small helper documents (separators, extracts, cover).
_BASE_CSS = """
body { font-family: sans-serif; margin: 0; padding: 0; color: #222; }
h1 { font-size: 22px; margin: 0 0 4px 0; }
h2 { font-size: 15px; margin: 0 0 16px 0; color: #555; font-weight: normal; }
table { border-collapse: collapse; width: 100%; font-size: 9px; }
th, td { border: 1px solid #ccc; padding: 3px 5px; text-align: left; vertical-align: top; }
th { background-color: #f2f2f2; }
tr.primary td { background-color: #fdf3c8; }
td.role { white-space: nowrap; font-weight: bold; }
.beleg-no { font-family: monospace; font-size: 40px; font-weight: bold; letter-spacing: 2px; }
.sep { border-top: 3px solid #333; margin: 18px 0; }
.meta { font-size: 12px; line-height: 1.7; }
.meta dt { font-weight: bold; float: left; width: 150px; clear: left; }
.meta dd { margin-left: 160px; margin-bottom: 4px; }
.muted { color: #666; font-size: 11px; }
"""


@dataclass
class BundleResult:
    """Everything the bundle build produced."""

    year: int
    directory: Path
    report_pdf: Path
    merged_pdf: Path | None = None
    zip_file: Path | None = None
    index_csv: Path | None = None
    documents: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class _PdfRenderer:
    """Renders HTML snippets to PDF, reusing a single browser for the whole bundle."""

    def __init__(self) -> None:
        # Typed loosely so the module imports without Playwright installed.
        self._playwright: Any = None
        self._browser: Any = None

    def __enter__(self) -> "_PdfRenderer":
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        try:
            try:
                self._browser = self._playwright.chromium.launch()
            except Exception as exc:
                print(f"Error launching browser: {exc}")
                print("Attempting to install browsers...")
                import subprocess
                import sys

                subprocess.run(
                    [sys.executable, "-m", "playwright", "install", "chromium"], check=True
                )
                self._browser = self._playwright.chromium.launch()
        except Exception:
            self._playwright.stop()
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()

    def render(self, html: str, out_path: Path, landscape: bool = False) -> None:
        assert self._browser is not None, "renderer not started"
        page = self._browser.new_page()
        try:
            page.set_content(html)
            page.pdf(
                path=str(out_path),
                format="A4",
                landscape=landscape,
                margin={"top": "1.5cm", "bottom": "1.5cm", "left": "1.5cm", "right": "1.5cm"},
            )
        finally:
            page.close()


def _safe_name(name: str) -> str:
    """Make a file name safe across platforms."""
    keep = "-_.() "
    cleaned = "".join(c if c.isalnum() or c in keep else "_" for c in name)
    return cleaned.strip().replace(" ", "_") or "document"


def _separator_html(doc: EvidenceDocument, year: int) -> str:
    """A one-page cover sheet placed in front of each document in the merged PDF."""
    if doc.is_primary and doc.is_supporting:
        role = (
            f"Primary evidence for {year}, and supporting evidence for the cost "
            f"basis carried into {year}"
        )
    elif doc.is_primary:
        role = f"Primary evidence for tax year {year}"
    else:
        role = f"Supporting evidence — establishes the cost basis carried into {year}"
    rows = ""
    if doc.rows:
        shown = ", ".join(str(r) for r in doc.rows)
        sheet = f"sheet '{doc.sheet}', " if doc.sheet else ""
        rows = f"<dt>Rows used</dt><dd>{escape(sheet)}row(s) {escape(shown)}</dd>"
    return f"""<html><head><meta charset='utf-8'><style>{_BASE_CSS}
    body {{ padding: 60px 40px; }}</style></head><body>
    <div class='beleg-no'>{escape(doc.number)}</div>
    <div class='sep'></div>
    <h1>{escape(doc.name)}</h1>
    <h2>{escape(doc.kind)}</h2>
    <dl class='meta'>
      <dt>Beleg-Nr.</dt><dd>{escape(doc.number)}</dd>
      <dt>Tax year</dt><dd>{year}</dd>
      <dt>Role</dt><dd>{escape(role)}</dd>
      <dt>Transaction date(s)</dt><dd>{escape(doc.date_range)}</dd>
      <dt>Transactions</dt><dd>{doc.event_count}</dd>
      {rows}
      <dt>Original path</dt><dd>{escape(doc.path)}</dd>
    </dl>
    <p class='muted'>Referenced under this number in the transaction ledger of the
    tax report for {year}.</p>
    </body></html>"""


def _workbook_extract_html(doc: EvidenceDocument, year: int) -> str | None:
    """
    Render the rows of a workbook that were actually used, as a printable table.

    Returns None if the workbook cannot be read.
    """
    path = Path(doc.path)
    try:
        df = pd.read_excel(path, sheet_name=doc.sheet) if doc.sheet else pd.read_excel(path)
    except Exception as exc:  # noqa: BLE001 - surfaced as a bundle warning
        print(f"  Warning: could not read {path} for the extract: {exc}")
        return None

    # Worksheet row N (1-based, header on row 1) is dataframe index N - 2.
    wanted = [r for r in doc.rows if 0 <= r - 2 < len(df)]
    if not wanted:
        return None
    subset = df.iloc[[r - 2 for r in wanted]]

    # Drop columns that are empty for every selected row - the benefit history
    # workbook has dozens of columns that do not apply to purchase rows.
    subset = subset.dropna(axis=1, how="all")

    header = "".join(f"<th>{escape(str(c))}</th>" for c in subset.columns)
    body = []
    for excel_row, (_, row) in zip(wanted, subset.iterrows(), strict=True):
        is_primary = excel_row in doc.primary_rows
        # The role is spelled out as text as well as shaded, so the extract stays
        # unambiguous when printed in black and white.
        css = "primary" if is_primary else ""
        role = str(year) if is_primary else "earlier"
        cells = "".join(f"<td>{escape('' if pd.isna(v) else str(v))}</td>" for v in row.to_numpy())
        body.append(
            f"<tr class='{css}'><td>{excel_row}</td><td class='role'>{role}</td>{cells}</tr>"
        )

    sheet_note = f" · sheet &quot;{escape(doc.sheet)}&quot;" if doc.sheet else ""
    return f"""<html><head><meta charset='utf-8'><style>{_BASE_CSS}
    body {{ padding: 10px; }}</style></head><body>
    <h1>{escape(doc.number)} — {escape(doc.name)} (extract)</h1>
    <h2>{escape(doc.kind)}{sheet_note} · rows used for tax year {year}</h2>
    <table>
      <thead><tr><th>Row</th><th>Tax year</th>{header}</tr></thead>
      <tbody>{"".join(body)}</tbody>
    </table>
    <p class='muted'>Only the rows referenced by this tax report are shown; the row
    numbers match the original worksheet. Rows marked &quot;{year}&quot; are
    transactions of the filed year; rows marked &quot;earlier&quot; are earlier
    transactions that establish the cost basis carried into {year}. The unmodified
    original workbook is included in the bundle under <code>source_data/</code>.</p>
    </body></html>"""


def _cover_html(year: int, evidence: EvidenceIndex, report_name: str, generated: datetime) -> str:
    """Front page of the merged Steuerakt."""
    primary = len(evidence.primary)
    supporting = len(evidence.supporting)
    both = len(evidence.both_roles)
    overlap = f", {both} of them both" if both else ""
    rows = "".join(
        f"<tr><td>{escape(d.number)}</td><td>{escape(d.name)}</td>"
        f"<td>{escape(d.kind)}</td><td>{escape(d.date_range)}</td>"
        f"<td>{escape(d.role)}</td></tr>"
        for d in evidence.documents
    )
    return f"""<html><head><meta charset='utf-8'><style>{_BASE_CSS}
    body {{ padding: 40px; }} h1 {{ font-size: 26px; }}</style></head><body>
    <h1>Kapitalvermögen — Steuerakt {year}</h1>
    <h2>Capital gains documentation for tax year {year}, Austria (KESt / E1kv)</h2>
    <dl class='meta'>
      <dt>Tax year</dt><dd>01.01.{year} – 31.12.{year}</dd>
      <dt>Compiled on</dt><dd>{generated.strftime("%d.%m.%Y %H:%M")}</dd>
      <dt>Contents</dt><dd>{escape(report_name)} + {len(evidence.documents)} documents</dd>
      <dt>Documents</dt><dd>{primary} covering {year} transactions, {supporting}
        covering the opening cost basis{overlap}</dd>
      <dt>Method</dt><dd>Gleitender Durchschnittspreis (moving average cost basis)</dd>
    </dl>
    <div class='sep'></div>
    <p class='muted'>This file contains the tax report followed by every source
    document it relies on, each preceded by a cover sheet carrying its Beleg-Nr.
    The ledger in the report cites these numbers.</p>
    <table>
      <thead><tr><th>Beleg-Nr.</th><th>Document</th><th>Type</th><th>Date(s)</th>
      <th>Role</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
    </body></html>"""


def _readme_text(year: int, result: BundleResult, evidence: EvidenceIndex) -> str:
    lines = [
        f"Steuerakt {year} — capital gains from RSU / ESPP / stock options",
        "=" * 64,
        "",
        f"Compiled on {datetime.now().strftime('%d.%m.%Y %H:%M')}.",
        "",
        "Contents",
        "--------",
        f"  {result.report_pdf.name}",
        f"      Tax report for {year}. Opening position on 01.01.{year}, every",
        f"      {year} transaction, the gain/loss calculation per sale, the",
        "      FinanzOnline Kennzahlen (994 / 892), and two appendices:",
        "      how the opening cost basis arose, and the document index.",
        "",
    ]
    if result.merged_pdf:
        lines += [
            f"  {result.merged_pdf.name}",
            "      THE FILE TO SUBMIT: the report plus every document below,",
            "      merged in Beleg-Nr. order, each behind a cover sheet.",
            "",
        ]
    lines += [
        "  belege/",
        f"      The {len(evidence.documents)} source documents, named by Beleg-Nr.",
        "      Workbook sources appear as an extract of the rows actually used.",
        "",
        "  source_data/",
        "      The unmodified original workbooks, for verification.",
        "",
    ]
    if result.index_csv:
        lines += [
            f"  {result.index_csv.name}",
            "      The document index as CSV.",
            "",
        ]
    lines += [
        "Why documents from earlier years are included",
        "---------------------------------------------",
        "Austrian law requires the moving average cost basis (Gleitender",
        f"Durchschnittspreis). The gain on a {year} sale is the sale price minus",
        "the average cost of the whole holding, which was built up by earlier",
        "acquisitions. The documents marked 'Supporting' prove that average cost;",
        "they are not taxed in this report. They go back to the last date the",
        "depot was empty, because at that point the average cost resets.",
        "",
    ]
    if evidence.missing:
        lines += ["MISSING DOCUMENTS", "-----------------"]
        lines += [f"  - {m}" for m in evidence.missing]
        lines += [""]
    if evidence.undocumented_events:
        lines += [
            "WARNING",
            "-------",
            f"  {evidence.undocumented_events} transaction(s) have no source document",
            "  recorded and are therefore not covered by the index.",
            "",
        ]
    lines += [
        "Disclaimer",
        "----------",
        "Generated automatically. Verify with a Steuerberater before filing.",
        "",
    ]
    return "\n".join(lines)


def _write_index_csv(path: Path, evidence: EvidenceIndex, filed_names: dict[str, str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(
            [
                "Beleg-Nr.",
                "File in bundle",
                "Original document",
                "Type",
                "Date(s)",
                "Transactions",
                "Rows used",
                "Role",
            ]
        )
        for doc in evidence.documents:
            writer.writerow(
                [
                    doc.number,
                    filed_names.get(doc.path, ""),
                    doc.path,
                    doc.kind,
                    doc.date_range,
                    doc.event_count,
                    ", ".join(str(r) for r in doc.rows),
                    doc.role_long,
                ]
            )


def _merge_pdfs(parts: list[Path], out_path: Path) -> list[str]:
    """Concatenate PDFs into one file. Returns warnings for parts that failed."""
    import pypdfium2 as pdfium

    warnings: list[str] = []
    merged = pdfium.PdfDocument.new()
    sources = []  # keep alive until saved
    for part in parts:
        try:
            src = pdfium.PdfDocument(str(part))
            merged.import_pages(src)
            sources.append(src)
        except Exception as exc:  # noqa: BLE001 - one bad file must not kill the bundle
            warnings.append(f"Could not merge {part.name}: {exc}")
    with out_path.open("wb") as handle:
        merged.save(handle)
    return warnings


def build_bundle(
    engine: "object",
    year: int,
    evidence: EvidenceIndex,
    output_dir: Path = Path("output"),
    make_zip: bool = True,
) -> BundleResult:
    """
    Build the submission bundle for ``year``.

    Args:
        engine: A :class:`~tax_engine.tax_engine.TaxEngine` whose events have been
            processed. Typed loosely to avoid a circular import.
        year: The tax year being filed.
        evidence: The document index for that year.
        output_dir: Where the bundle folder is created.
        make_zip: Also produce a ZIP next to the folder.
    """
    stamp = datetime.now()
    bundle_dir = output_dir / f"Steuerakt_{year}"
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    belege_dir = bundle_dir / "belege"
    data_dir = bundle_dir / "source_data"
    belege_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True)

    report_pdf = bundle_dir / f"00_Steuerbericht_{year}.pdf"
    result = BundleResult(year=year, directory=bundle_dir, report_pdf=report_pdf)
    result.warnings.extend(f"Referenced document not found: {m}" for m in evidence.missing)
    if evidence.undocumented_events:
        result.warnings.append(
            f"{evidence.undocumented_events} transaction(s) have no source document."
        )

    filed_names: dict[str, str] = {}
    merge_parts: list[Path] = []
    scratch = bundle_dir / ".separators"
    scratch.mkdir()

    with _PdfRenderer() as renderer:
        # 1. The tax report itself.
        print(f"  Rendering {report_pdf.name} ...")
        renderer.render(
            engine.generate_html_content(year=year, evidence=evidence),  # type: ignore[attr-defined]
            report_pdf,
        )

        # 2. Cover page for the merged Steuerakt.
        cover = scratch / "cover.pdf"
        renderer.render(_cover_html(year, evidence, report_pdf.name, stamp), cover)
        merge_parts.append(cover)
        merge_parts.append(report_pdf)

        # 3. One filed document per Beleg-Nr.
        for doc in evidence.documents:
            source = Path(doc.path)
            if doc.is_tabular:
                # Keep the original workbook, and file a printable extract of the
                # rows the calculation actually used.
                if source.exists():
                    shutil.copy2(source, data_dir / source.name)
                extract_html = _workbook_extract_html(doc, year)
                target = belege_dir / f"{doc.number}_{_safe_name(source.stem)}_extract.pdf"
                if extract_html is None:
                    result.warnings.append(
                        f"{doc.number}: could not build an extract of {source.name}."
                    )
                    continue
                print(f"  Rendering {target.name} ...")
                renderer.render(extract_html, target, landscape=True)
            else:
                if not source.exists():
                    continue
                target = belege_dir / f"{doc.number}_{_safe_name(source.name)}"
                shutil.copy2(source, target)

            filed_names[doc.path] = target.name
            result.documents.append(target)

            separator = scratch / f"{doc.number}_sep.pdf"
            renderer.render(_separator_html(doc, year), separator)
            merge_parts.extend([separator, target])

    # 4. Index + readme.
    result.index_csv = bundle_dir / f"Belegverzeichnis_{year}.csv"
    _write_index_csv(result.index_csv, evidence, filed_names)

    # 5. One merged PDF to submit.
    merged = bundle_dir / f"Steuerakt_{year}_komplett.pdf"
    print(f"  Merging {len(merge_parts)} PDF files into {merged.name} ...")
    merge_warnings = _merge_pdfs([p for p in merge_parts if p.exists()], merged)
    result.warnings.extend(merge_warnings)
    result.merged_pdf = merged if merged.exists() else None

    shutil.rmtree(scratch, ignore_errors=True)
    (bundle_dir / "README.txt").write_text(_readme_text(year, result, evidence), encoding="utf-8")

    # 6. ZIP for e-mailing / uploading.
    if make_zip:
        archive = shutil.make_archive(str(bundle_dir), "zip", root_dir=bundle_dir)
        result.zip_file = Path(archive)

    return result


__all__ = ["BundleResult", "build_bundle"]
