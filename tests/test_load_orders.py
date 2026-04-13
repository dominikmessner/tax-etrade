"""
Tests for load_orders_from_excel() in cli_main.py.

Key behaviour under test:
- Uses Execution Date (actual trade date) when present
- Falls back to Order Date when Execution Date column is absent (old downloads)
- Falls back to Order Date when Execution Date cell is NaN/empty
- Skips cancelled orders (Sold Qty. == "--")
- Skips zero-quantity rows
- Skips Stock Options rows (handled separately via options PDFs)
"""

from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from tax_engine.cli_main import load_orders_from_excel
from tax_engine.models import EventType


def _make_excel(rows: list[dict]) -> bytes:
    """Serialise a list of dicts to an in-memory xlsx file."""
    buf = BytesIO()
    pd.DataFrame(rows).to_excel(buf, index=False)
    return buf.getvalue()


@pytest.fixture()  # type: ignore[misc]
def orders_file(tmp_path: Path) -> Path:
    orders_dir = tmp_path / "input" / "orders"
    orders_dir.mkdir(parents=True)
    return orders_dir / "orders.xlsx"


def _load(orders_file: Path, rows: list[dict]) -> list:  # type: ignore[type-arg]
    """Write rows to orders_file, patch away filesystem/excel access, run loader."""
    orders_file.write_bytes(_make_excel(rows))
    df = pd.read_excel(orders_file)
    with (
        patch("tax_engine.cli_main.pd.read_excel", return_value=df),
        patch("tax_engine.cli_main.Path") as mock_path,
    ):
        mock_path.return_value.exists.return_value = True
        return load_orders_from_excel()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _base_row(**overrides: object) -> dict:  # type: ignore[type-arg]
    return {
        "Order Date": "12/08/2025",
        "Sold Qty.": "86",
        "Execution Price": "$44.83",
        "Benefit Type": "Restricted Stock",
        **overrides,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestExecutionDatePreference:
    def test_uses_execution_date_when_present(self, orders_file: Path) -> None:
        """When Execution Date column exists it should be used as event_date."""
        events = _load(orders_file, [_base_row(**{"Execution Date": "12/10/2025"})])
        assert len(events) == 1
        assert events[0].event_date == date(2025, 12, 10)

    def test_uses_order_date_when_execution_date_column_absent(self, orders_file: Path) -> None:
        """Old downloads without Execution Date column fall back to Order Date."""
        events = _load(orders_file, [_base_row()])
        assert len(events) == 1
        assert events[0].event_date == date(2025, 12, 8)

    def test_falls_back_to_order_date_when_execution_date_is_nan(self, orders_file: Path) -> None:
        """If Execution Date column exists but cell is empty/NaN, fall back to Order Date."""
        events = _load(orders_file, [_base_row(**{"Execution Date": None})])
        assert len(events) == 1
        assert events[0].event_date == date(2025, 12, 8)

    def test_limit_order_uses_execution_date(self, orders_file: Path) -> None:
        """Limit orders: execution date weeks after order date — execution date wins."""
        events = _load(
            orders_file,
            [_base_row(**{"Order Date": "10/06/2023", "Execution Date": "11/09/2023"})],
        )
        assert len(events) == 1
        assert events[0].event_date == date(2023, 11, 9)


class TestRowFiltering:
    def test_skips_cancelled_orders(self, orders_file: Path) -> None:
        events = _load(orders_file, [_base_row(**{"Sold Qty.": "--"})])
        assert events == []

    def test_skips_zero_quantity(self, orders_file: Path) -> None:
        events = _load(orders_file, [_base_row(**{"Sold Qty.": "0"})])
        assert events == []

    def test_skips_stock_options_rows(self, orders_file: Path) -> None:
        """Stock Options are handled via options PDFs; orders.xlsx entries must be ignored."""
        events = _load(
            orders_file, [_base_row(**{"Benefit Type": "Stock Options", "Sold Qty.": "780"})]
        )
        assert events == []


class TestParsedValues:
    def test_event_type_is_sell(self, orders_file: Path) -> None:
        events = _load(orders_file, [_base_row()])
        assert events[0].event_type == EventType.SELL

    def test_price_parsed_correctly(self, orders_file: Path) -> None:
        events = _load(orders_file, [_base_row(**{"Execution Price": "$44.83"})])
        assert events[0].price_usd == Decimal("44.83")

    def test_quantity_parsed_correctly(self, orders_file: Path) -> None:
        events = _load(orders_file, [_base_row(**{"Sold Qty.": "86"})])
        assert events[0].shares == Decimal("86")

    def test_multiple_rows_all_loaded(self, orders_file: Path) -> None:
        rows = [
            _base_row(**{"Execution Date": "12/08/2025", "Sold Qty.": "100"}),
            _base_row(**{"Execution Date": "12/09/2025", "Sold Qty.": "50"}),
        ]
        events = _load(orders_file, rows)
        assert len(events) == 2
        assert events[0].event_date == date(2025, 12, 8)
        assert events[1].event_date == date(2025, 12, 9)
