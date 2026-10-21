"""
Tests for load_orders_from_excel() in loaders.py.

Key behaviour under test:
- Uses Execution Date (actual trade date) when present
- Falls back to Order Date when Execution Date column is absent (old downloads)
- Falls back to Order Date when Execution Date cell is NaN/empty
- Skips cancelled orders (Sold Qty. == "--")
- Skips zero-quantity rows
- Skips rows without a usable execution price instead of crashing
- Skips Stock Options rows (handled separately via options PDFs)
- Returns an empty list when the file is missing
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from tax_engine.loaders import load_orders_from_excel
from tax_engine.models import EventType


@pytest.fixture()
def orders_file(tmp_path: Path) -> Path:
    return tmp_path / "orders.xlsx"


def _load(orders_file: Path, rows: list[dict]) -> list:  # type: ignore[type-arg]
    pd.DataFrame(rows).to_excel(orders_file, index=False)
    return load_orders_from_excel(orders_file)


def _base_row(**overrides: object) -> dict:  # type: ignore[type-arg]
    return {
        "Order Date": "12/08/2025",
        "Sold Qty.": "86",
        "Execution Price": "$44.83",
        "Benefit Type": "Restricted Stock",
        **overrides,
    }


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

    def test_iso_date_format_accepted(self, orders_file: Path) -> None:
        events = _load(orders_file, [_base_row(**{"Order Date": "2023-11-09"})])
        assert events[0].event_date == date(2023, 11, 9)

    def test_unparseable_date_row_is_skipped(self, orders_file: Path, capsys) -> None:
        events = _load(orders_file, [_base_row(**{"Order Date": "next tuesday"}), _base_row()])
        assert len(events) == 1
        assert "Error parsing date" in capsys.readouterr().out


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

    @pytest.mark.parametrize("bad_price", ["--", "", None, "N/A"])
    def test_skips_rows_without_execution_price(
        self, orders_file: Path, bad_price: object, capsys
    ) -> None:
        """A blank or placeholder price must skip the row, not raise InvalidOperation."""
        events = _load(
            orders_file,
            [_base_row(**{"Execution Price": bad_price}), _base_row()],
        )
        assert len(events) == 1
        assert "no execution price" in capsys.readouterr().out

    def test_missing_file_returns_empty_list(self, tmp_path: Path, capsys) -> None:
        events = load_orders_from_excel(tmp_path / "does-not-exist.xlsx")
        assert events == []
        assert "No sell orders loaded" in capsys.readouterr().out


class TestParsedValues:
    def test_event_type_is_sell(self, orders_file: Path) -> None:
        events = _load(orders_file, [_base_row()])
        assert events[0].event_type == EventType.SELL

    def test_price_parsed_correctly(self, orders_file: Path) -> None:
        events = _load(orders_file, [_base_row(**{"Execution Price": "$44.83"})])
        assert events[0].price_usd == Decimal("44.83")

    def test_quantity_parsed_correctly(self, orders_file: Path) -> None:
        events = _load(orders_file, [_base_row(**{"Sold Qty.": "1,086"})])
        assert events[0].shares == Decimal("1086")

    def test_multiple_rows_all_loaded(self, orders_file: Path) -> None:
        rows = [
            _base_row(**{"Execution Date": "12/08/2025", "Sold Qty.": "100"}),
            _base_row(**{"Execution Date": "12/09/2025", "Sold Qty.": "50"}),
        ]
        events = _load(orders_file, rows)
        assert len(events) == 2
        assert events[0].event_date == date(2025, 12, 8)
        assert events[1].event_date == date(2025, 12, 9)
