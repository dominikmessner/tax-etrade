"""
Tests for the ESPP loader, load_all_events() and the tax-engine CLI entry point.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from tax_engine.cli_main import main as cli_main
from tax_engine.loaders import (
    ESPP_FILE,
    load_all_events,
    load_espp_events_from_excel,
)
from tax_engine.models import EventType, StockEvent


def _espp_row(**overrides: object) -> dict:  # type: ignore[type-arg]
    return {
        "Record Type": "Purchase",
        "Purchase Date": "05-DEC-2022",
        "Purchased Qty.": "105",
        "Purchase Date FMV": "$37.56",
        **overrides,
    }


def _write_espp(path: Path, rows: list[dict], sheet_name: str = "ESPP") -> None:  # type: ignore[type-arg]
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_excel(path, index=False, sheet_name=sheet_name)


class TestEsppLoader:
    def test_missing_file_returns_empty_list(self, tmp_path: Path, capsys) -> None:
        assert load_espp_events_from_excel(tmp_path / "nope.xlsx") == []
        assert "No ESPP purchases loaded" in capsys.readouterr().out

    def test_purchase_row_becomes_buy_event(self, tmp_path: Path) -> None:
        path = tmp_path / "BenefitHistory.xlsx"
        _write_espp(path, [_espp_row()])
        events = load_espp_events_from_excel(path)
        assert len(events) == 1
        assert events[0].event_type == EventType.BUY
        assert events[0].event_date == date(2022, 12, 5)
        assert events[0].shares == Decimal("105")
        assert events[0].price_usd == Decimal("37.56")

    def test_non_purchase_rows_ignored(self, tmp_path: Path) -> None:
        path = tmp_path / "BenefitHistory.xlsx"
        _write_espp(path, [_espp_row(**{"Record Type": "Grant"}), _espp_row()])
        assert len(load_espp_events_from_excel(path)) == 1

    @pytest.mark.parametrize("column", ["Purchase Date", "Purchased Qty.", "Purchase Date FMV"])
    @pytest.mark.parametrize("bad", ["--", "", None])
    def test_invalid_cells_skip_row(self, tmp_path: Path, column: str, bad: object) -> None:
        path = tmp_path / "BenefitHistory.xlsx"
        _write_espp(path, [_espp_row(**{column: bad}), _espp_row()])
        assert len(load_espp_events_from_excel(path)) == 1

    def test_falls_back_to_first_sheet(self, tmp_path: Path, capsys) -> None:
        path = tmp_path / "BenefitHistory.xlsx"
        _write_espp(path, [_espp_row()], sheet_name="Sheet1")
        assert len(load_espp_events_from_excel(path)) == 1
        assert "Sheet 'ESPP' not found" in capsys.readouterr().out


class TestLoadAllEvents:
    def test_empty_input_dir_returns_empty_list(self, tmp_path: Path) -> None:
        assert load_all_events(tmp_path) == []

    def test_espp_only(self, tmp_path: Path) -> None:
        _write_espp(tmp_path / ESPP_FILE, [_espp_row()])
        events = load_all_events(tmp_path)
        assert [e.event_type for e in events] == [EventType.BUY]

    def test_rsu_only_via_parser(self, tmp_path: Path) -> None:
        """A user with only RSU confirmations must get events without any ESPP file."""
        vest = StockEvent(date(2021, 5, 17), EventType.VEST, Decimal("63"), Decimal("46.68"))
        with patch("tax_engine.loaders.load_rsu_events", return_value=[vest]) as mock_rsu:
            events = load_all_events(tmp_path)
        mock_rsu.assert_called_once_with(tmp_path / "rsu")
        assert events == [vest]


class TestCliMain:
    def test_no_input_exits_nonzero_with_guidance(self, tmp_path: Path, capsys) -> None:
        with patch("sys.argv", ["tax-engine", "--input-dir", str(tmp_path)]):
            code = cli_main()
        out = capsys.readouterr().out
        assert code == 1
        assert "no transactions found" in out
        assert "BenefitHistory.xlsx" in out
        assert "rsu" in out

    def test_rsu_only_user_gets_report(self, tmp_path: Path, capsys, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        vest = StockEvent(
            date(2021, 5, 17), EventType.VEST, Decimal("63"), Decimal("46.68"), Decimal("0.82")
        )
        with (
            patch("sys.argv", ["tax-engine", "--input-dir", str(tmp_path)]),
            patch("tax_engine.loaders.load_rsu_events", return_value=[vest]),
            patch("tax_engine.tax_engine.TaxEngine.generate_pdf_report", return_value=True),
        ):
            code = cli_main()
        out = capsys.readouterr().out
        assert code == 0
        assert "2021-05-17" in out
        assert "PDF generation complete" in out

    def test_pdf_failure_exits_nonzero(self, tmp_path: Path, capsys) -> None:
        vest = StockEvent(
            date(2021, 5, 17), EventType.VEST, Decimal("63"), Decimal("46.68"), Decimal("0.82")
        )
        with (
            patch("sys.argv", ["tax-engine", "--input-dir", str(tmp_path)]),
            patch("tax_engine.loaders.load_rsu_events", return_value=[vest]),
            patch("tax_engine.tax_engine.TaxEngine.generate_pdf_report", return_value=False),
        ):
            code = cli_main()
        out = capsys.readouterr().out
        assert code == 1
        assert "PDF generation FAILED" in out
        assert "PDF generation complete" not in out

    def test_unknown_year_exits_nonzero(self, tmp_path: Path, capsys) -> None:
        vest = StockEvent(
            date(2021, 5, 17), EventType.VEST, Decimal("63"), Decimal("46.68"), Decimal("0.82")
        )
        with (
            patch("sys.argv", ["tax-engine", "--input-dir", str(tmp_path), "--year", "1999"]),
            patch("tax_engine.loaders.load_rsu_events", return_value=[vest]),
        ):
            code = cli_main()
        out = capsys.readouterr().out
        assert code == 1
        assert "No data found for year 1999" in out
        assert "Available years: 2021" in out
