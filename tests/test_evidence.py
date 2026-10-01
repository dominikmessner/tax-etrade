"""
Tests for the single-year evidence index.

Key behaviour under test:
- Which earlier transactions a filed year still depends on (the depot-empty reset)
- Beleg-Nr. assignment: chronological, workbooks last
- Citations for single-document and row-based sources
- Primary / supporting classification, including documents that are both
"""

from datetime import date
from decimal import Decimal

import pytest

from tax_engine.evidence import build_evidence_index, relevant_events
from tax_engine.models import EventType, StockEvent
from tax_engine.tax_engine import TaxEngine

RSU_2023 = "input/rsu/RSU_Confirmation_2023-06-05_1.pdf"
RSU_2024 = "input/rsu/RSU_Confirmation_2024-06-05_2.pdf"
ESPP = "input/espp/BenefitHistory.xlsx"
ORDERS = "input/orders/orders.xlsx"


def _vest(day: date, shares: str, price: str, document: str) -> StockEvent:
    return StockEvent(
        event_date=day,
        event_type=EventType.VEST,
        shares=Decimal(shares),
        price_usd=Decimal(price),
        fx_rate=Decimal("0.90"),
        source_document=document,
        source_reference="Release Confirmation",
    )


def _buy(day: date, shares: str, price: str, row: int) -> StockEvent:
    return StockEvent(
        event_date=day,
        event_type=EventType.BUY,
        shares=Decimal(shares),
        price_usd=Decimal(price),
        fx_rate=Decimal("0.90"),
        source_document=ESPP,
        source_reference=f"sheet 'ESPP', row {row}",
        source_sheet="ESPP",
        source_row=row,
    )


def _sell(day: date, shares: str, price: str, row: int) -> StockEvent:
    return StockEvent(
        event_date=day,
        event_type=EventType.SELL,
        shares=Decimal(shares),
        price_usd=Decimal(price),
        fx_rate=Decimal("0.90"),
        source_document=ORDERS,
        source_reference=f"row {row}",
        source_row=row,
    )


@pytest.fixture
def engine_across_years() -> TaxEngine:
    """Acquisitions in 2023 and 2024, then a sale in 2025."""
    engine = TaxEngine()
    engine.process_all(
        [
            _vest(date(2023, 6, 5), "100", "50.00", RSU_2023),
            _buy(date(2023, 12, 5), "50", "40.00", 4),
            _vest(date(2024, 6, 5), "60", "60.00", RSU_2024),
            _buy(date(2025, 6, 5), "20", "55.00", 2),
            _sell(date(2025, 7, 1), "30", "70.00", 10),
        ]
    )
    return engine


class TestRelevantEvents:
    """Which earlier transactions a filed year still depends on."""

    def test_splits_year_from_earlier(self, engine_across_years):
        supporting, in_year = relevant_events(engine_across_years.processed_events, 2025)

        assert [pe.event.event_date.year for pe in supporting] == [2023, 2023, 2024]
        assert [pe.event.event_date.year for pe in in_year] == [2025, 2025]

    def test_stops_at_last_empty_depot(self):
        """Acquisitions before the depot last hit zero do not affect the year."""
        engine = TaxEngine()
        engine.process_all(
            [
                _vest(date(2022, 1, 10), "100", "50.00", RSU_2023),
                _sell(date(2022, 6, 1), "100", "60.00", 30),  # depot back to zero
                _vest(date(2024, 3, 1), "40", "45.00", RSU_2024),
                _sell(date(2025, 4, 1), "10", "80.00", 11),
            ]
        )

        supporting, _ = relevant_events(engine.processed_events, 2025)

        # Only the 2024 vest survives; the 2022 pair is cut off by the reset.
        assert [pe.event.event_date for pe in supporting] == [date(2024, 3, 1)]

    def test_no_earlier_events(self):
        engine = TaxEngine()
        engine.process_all(
            [
                _vest(date(2025, 1, 10), "100", "50.00", RSU_2023),
                _sell(date(2025, 6, 1), "10", "60.00", 5),
            ]
        )

        supporting, in_year = relevant_events(engine.processed_events, 2025)

        assert supporting == []
        assert len(in_year) == 2


class TestNumbering:
    """Beleg-Nr. assignment."""

    def test_chronological_with_workbooks_last(self, engine_across_years):
        index = build_evidence_index(engine_across_years.processed_events, 2025)

        assert [(d.number, d.name) for d in index.documents] == [
            ("B-001", "RSU_Confirmation_2023-06-05_1.pdf"),
            ("B-002", "RSU_Confirmation_2024-06-05_2.pdf"),
            ("B-003", "BenefitHistory.xlsx"),
            ("B-004", "orders.xlsx"),
        ]

    def test_start_number_is_honoured(self, engine_across_years):
        index = build_evidence_index(engine_across_years.processed_events, 2025, start_number=10)

        assert index.documents[0].number == "B-010"

    def test_document_kinds(self, engine_across_years):
        index = build_evidence_index(engine_across_years.processed_events, 2025)
        kinds = {d.name: d.kind for d in index.documents}

        assert kinds["RSU_Confirmation_2023-06-05_1.pdf"] == "RSU Release Confirmation"
        assert kinds["BenefitHistory.xlsx"] == "ESPP Purchase History (Benefit History)"
        assert kinds["orders.xlsx"] == "Sale Orders / Trade Confirmations"


class TestRoles:
    """Primary vs supporting classification."""

    def test_earlier_document_is_supporting_only(self, engine_across_years):
        index = build_evidence_index(engine_across_years.processed_events, 2025)
        doc = index.by_path(RSU_2023)

        assert doc.is_supporting
        assert not doc.is_primary
        assert doc.role == "Supporting"

    def test_workbook_spanning_years_is_both(self, engine_across_years):
        index = build_evidence_index(engine_across_years.processed_events, 2025)
        doc = index.by_path(ESPP)

        assert doc.is_primary
        assert doc.is_supporting
        assert doc.role == "Primary+Supp."
        assert doc in index.both_roles
        # Both lists contain it, so they overlap rather than partition.
        assert doc in index.primary
        assert doc in index.supporting

    def test_rows_recorded_and_sorted(self, engine_across_years):
        index = build_evidence_index(engine_across_years.processed_events, 2025)
        doc = index.by_path(ESPP)

        assert doc.rows == [2, 4]
        assert doc.primary_rows == [2]  # only the 2025 purchase
        assert doc.sheet == "ESPP"


class TestCitations:
    """What the report prints in its Beleg column."""

    def test_single_document_cites_number_only(self, engine_across_years):
        index = build_evidence_index(engine_across_years.processed_events, 2025)
        vest = next(
            pe
            for pe in engine_across_years.processed_events
            if pe.event.source_document == RSU_2023
        )

        assert index.citation_for(vest) == "B-001"

    def test_workbook_cites_number_and_row(self, engine_across_years):
        index = build_evidence_index(engine_across_years.processed_events, 2025)
        sale = next(
            pe
            for pe in engine_across_years.processed_events
            if pe.event.event_type == EventType.SELL
        )

        assert index.citation_for(sale) == "B-004, row 10"

    def test_event_without_document(self):
        engine = TaxEngine()
        engine.process_all(
            [
                StockEvent(
                    event_date=date(2025, 1, 5),
                    event_type=EventType.VEST,
                    shares=Decimal("10"),
                    price_usd=Decimal("50.00"),
                    fx_rate=Decimal("0.90"),
                ),
            ]
        )
        index = build_evidence_index(engine.processed_events, 2025)

        assert index.documents == []
        assert index.undocumented_events == 1
        assert index.citation_for(engine.processed_events[0]) == "—"


class TestMissingDocuments:
    """Referenced files that are not on disk are reported, not silently dropped."""

    def test_missing_file_is_listed(self, tmp_path):
        absent = tmp_path / "input" / "rsu" / "gone.pdf"
        present = tmp_path / "input" / "rsu" / "here.pdf"
        present.parent.mkdir(parents=True)
        present.write_bytes(b"%PDF-1.4\n")

        engine = TaxEngine()
        engine.process_all(
            [
                _vest(date(2025, 1, 10), "100", "50.00", present.as_posix()),
                _vest(date(2025, 2, 10), "100", "50.00", absent.as_posix()),
            ]
        )
        index = build_evidence_index(engine.processed_events, 2025)

        assert index.missing == [absent.as_posix()]
