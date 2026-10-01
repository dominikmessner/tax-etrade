"""
Evidence tracking for a single-year tax filing.

The Austrian moving average cost basis (Gleitender Durchschnittspreis) carried into
a tax year is built from every acquisition since the depot was last empty. A filing
for one year therefore needs two kinds of documents:

- **Primary evidence**: the documents behind the transactions of the filed year.
- **Supporting evidence**: the documents behind the earlier transactions that
  establish the opening average cost on 1 January of that year.

This module assigns a stable document number (Beleg-Nr.) to each document so the
tax report can cite it and the bundle can ship it under the same number.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from .models import EventType, ProcessedEvent

# Documents that hold many transactions (one row per transaction) rather than one.
TABULAR_SUFFIXES = {".xlsx", ".xls", ".csv"}


@dataclass
class EvidenceDocument:
    """A single source document referenced by the tax report."""

    number: str  # Beleg-Nr., e.g. "B-007"
    path: str  # path relative to the project root
    kind: str  # "RSU Release Confirmation", "ESPP Purchase History", ...
    first_date: date
    last_date: date
    event_count: int = 0
    is_primary: bool = False  # backs a transaction in the filed year
    is_supporting: bool = False  # backs an earlier transaction behind the opening cost
    references: list[str] = field(default_factory=list)  # row references used
    sheet: str | None = None  # worksheet name, for workbook sources
    rows: list[int] = field(default_factory=list)  # worksheet rows used, sorted
    primary_rows: list[int] = field(default_factory=list)  # rows belonging to the filed year

    @property
    def name(self) -> str:
        return Path(self.path).name

    @property
    def is_tabular(self) -> bool:
        return Path(self.path).suffix.lower() in TABULAR_SUFFIXES

    @property
    def exists(self) -> bool:
        return Path(self.path).exists()

    @property
    def date_range(self) -> str:
        if self.first_date == self.last_date:
            return self.first_date.isoformat()
        return f"{self.first_date.isoformat()} – {self.last_date.isoformat()}"

    @property
    def role(self) -> str:
        """Short role label. A workbook can hold rows of both kinds."""
        if self.is_primary and self.is_supporting:
            return "Primary+Supp."
        return "Primary" if self.is_primary else "Supporting"

    @property
    def role_long(self) -> str:
        """Role spelled out, for the report and the cover sheets."""
        if self.is_primary and self.is_supporting:
            return "Primary and supporting (holds rows of both kinds)"
        if self.is_primary:
            return "Primary evidence"
        return "Supporting evidence (opening cost basis)"


def _classify(path: str, event_type: EventType) -> str:
    """Describe a document by its location and the events it carries."""
    lowered = path.lower()
    if "/rsu/" in lowered:
        return "RSU Release Confirmation"
    if "/options/" in lowered:
        return "Stock Option Exercise Confirmation"
    if "/espp/" in lowered:
        return "ESPP Purchase History (Benefit History)"
    if "/orders/" in lowered:
        return "Sale Orders / Trade Confirmations"
    return f"{event_type.value} source document"


@dataclass
class EvidenceIndex:
    """
    All documents a single-year filing relies on, numbered for citation.

    Build it with :func:`build_evidence_index`, then look up a citation for a
    processed event with :meth:`citation_for`.
    """

    year: int
    documents: list[EvidenceDocument] = field(default_factory=list)
    opening_date: date | None = None  # first event date of the supporting chain
    missing: list[str] = field(default_factory=list)  # referenced but not on disk
    undocumented_events: int = 0  # events with no source document at all

    def by_path(self, path: str) -> EvidenceDocument | None:
        for doc in self.documents:
            if doc.path == path:
                return doc
        return None

    def number_for(self, event_or_path: "ProcessedEvent | str | None") -> str:
        """Beleg-Nr. for an event's document, or "" if it has none."""
        path = event_or_path
        if isinstance(event_or_path, ProcessedEvent):
            path = event_or_path.event.source_document
        if not path:
            return ""
        doc = self.by_path(str(path))
        return doc.number if doc else ""

    def citation_for(self, processed: ProcessedEvent) -> str:
        """Full citation for the report, e.g. "B-012" or "B-036, row 7"."""
        event = processed.event
        number = self.number_for(event.source_document)
        if not number:
            return "—"
        doc = self.by_path(str(event.source_document))
        if doc and doc.is_tabular and event.source_reference:
            return f"{number}, {event.source_reference}"
        return number

    @property
    def primary(self) -> list[EvidenceDocument]:
        """Documents backing a transaction of the filed year."""
        return [d for d in self.documents if d.is_primary]

    @property
    def supporting(self) -> list[EvidenceDocument]:
        """Documents backing an earlier transaction behind the opening cost basis.

        A workbook can appear in both lists, since its rows span several years.
        """
        return [d for d in self.documents if d.is_supporting]

    @property
    def both_roles(self) -> list[EvidenceDocument]:
        """Documents that serve both roles - workbooks spanning several years."""
        return [d for d in self.documents if d.is_primary and d.is_supporting]


def relevant_events(
    processed_events: list[ProcessedEvent], year: int
) -> tuple[list[ProcessedEvent], list[ProcessedEvent]]:
    """
    Split the ledger into the events of ``year`` and the earlier events that
    still matter for it.

    Earlier events matter back to the last point where the depot was empty:
    once the position hits zero the average cost resets, so nothing before that
    influences the filed year.
    """
    in_year = [pe for pe in processed_events if pe.event.event_date.year == year]

    before = [pe for pe in processed_events if pe.event.event_date.year < year]
    # Walk back to the last moment the depot was empty - everything after it
    # contributes to the opening average cost.
    start = 0
    for i, pe in enumerate(before):
        if pe.total_shares_after == Decimal("0"):
            start = i + 1
    return before[start:], in_year


def build_evidence_index(
    processed_events: list[ProcessedEvent], year: int, start_number: int = 1
) -> EvidenceIndex:
    """
    Collect and number every document the ``year`` filing relies on.

    Documents are numbered chronologically by their earliest transaction, so the
    Beleg-Nr. order matches the order of the ledger. Tabular sources (the ESPP
    and orders workbooks) are numbered last because they span many dates.
    """
    supporting_events, year_events = relevant_events(processed_events, year)
    index = EvidenceIndex(year=year)
    if supporting_events:
        index.opening_date = supporting_events[0].event.event_date

    # Gather documents, remembering whether they back a transaction in the filed year.
    collected: dict[str, EvidenceDocument] = {}
    for processed, is_primary in [(pe, False) for pe in supporting_events] + [
        (pe, True) for pe in year_events
    ]:
        event = processed.event
        if not event.source_document:
            index.undocumented_events += 1
            continue
        path = event.source_document
        doc = collected.get(path)
        if doc is None:
            doc = EvidenceDocument(
                number="",
                path=path,
                kind=_classify(path, event.event_type),
                first_date=event.event_date,
                last_date=event.event_date,
            )
            collected[path] = doc
        doc.first_date = min(doc.first_date, event.event_date)
        doc.last_date = max(doc.last_date, event.event_date)
        doc.event_count += 1
        doc.is_primary = doc.is_primary or is_primary
        doc.is_supporting = doc.is_supporting or not is_primary
        if event.source_reference and event.source_reference not in doc.references:
            doc.references.append(event.source_reference)
        if event.source_sheet and doc.sheet is None:
            doc.sheet = event.source_sheet
        if event.source_row is not None:
            if event.source_row not in doc.rows:
                doc.rows.append(event.source_row)
            if is_primary and event.source_row not in doc.primary_rows:
                doc.primary_rows.append(event.source_row)

    # Single-transaction documents first (chronologically), workbooks last.
    single = sorted(
        (d for d in collected.values() if not d.is_tabular),
        key=lambda d: (d.first_date, d.name),
    )
    tabular = sorted(
        (d for d in collected.values() if d.is_tabular), key=lambda d: (d.first_date, d.name)
    )

    for offset, doc in enumerate(single + tabular, start=start_number):
        doc.number = f"B-{offset:03d}"
        doc.rows.sort()
        doc.primary_rows.sort()
        if not doc.exists:
            index.missing.append(doc.path)

    index.documents = single + tabular
    return index
