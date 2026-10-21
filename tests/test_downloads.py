"""
Tests for the exit codes of the E-Trade download commands.

No browser is started: a missing session file is detected before Playwright
launches, which is enough to exercise the failure paths.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from tax_engine import download_all, etrade_common
from tax_engine.etrade_common import DownloadError, SessionError, run_download
from tax_engine.etrade_download_espp import main as espp_main
from tax_engine.etrade_download_options import main as options_main
from tax_engine.etrade_download_orders import main as orders_main
from tax_engine.etrade_download_rsu import main as rsu_main


@pytest.fixture()
def no_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(etrade_common, "SESSION_FILE", tmp_path / "missing.json")


class TestRunDownload:
    def test_success_returns_zero(self) -> None:
        assert run_download(lambda: None) == 0

    def test_failure_returns_one_and_reports(self, capsys: pytest.CaptureFixture[str]) -> None:
        def step() -> None:
            raise DownloadError("3 of 5 RSU confirmation(s) could not be downloaded")

        assert run_download(step) == 1
        assert "3 of 5 RSU confirmation(s)" in capsys.readouterr().out


@pytest.mark.usefixtures("no_session")
class TestMissingSession:
    @pytest.mark.parametrize("command", [espp_main, orders_main, rsu_main, options_main])
    def test_each_command_exits_nonzero(
        self, command: object, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert callable(command)
        assert command() == 1
        assert "Please run tax-login" in capsys.readouterr().out

    def test_session_error_is_raised_not_printed(self) -> None:
        with pytest.raises(SessionError):
            etrade_common.download_confirmations(
                benefit_type="RS",
                output_dir=Path("input/rsu"),
                filename_prefix="RSU_Confirmation",
                label="RSU",
            )

    def test_download_all_exits_nonzero(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch.object(download_all, "login"):
            assert download_all.main() == 1
        out = capsys.readouterr().out
        assert "Completed with 4 failed step(s)" in out
        assert "All tasks completed" not in out


class TestDownloadAll:
    def test_all_steps_succeed(self, capsys: pytest.CaptureFixture[str]) -> None:
        steps = [("A", lambda: None), ("B", lambda: None)]
        with (
            patch.object(download_all, "login"),
            patch.object(download_all, "DOWNLOAD_STEPS", steps),
        ):
            assert download_all.main() == 0
        assert "All tasks completed" in capsys.readouterr().out

    def test_one_failed_step_still_runs_the_rest(self, capsys: pytest.CaptureFixture[str]) -> None:
        ran: list[str] = []

        def fail() -> None:
            ran.append("A")
            raise DownloadError("boom")

        steps = [("A", fail), ("B", lambda: ran.append("B"))]
        with (
            patch.object(download_all, "login"),
            patch.object(download_all, "DOWNLOAD_STEPS", steps),
        ):
            assert download_all.main() == 1
        assert ran == ["A", "B"]
        assert "A failed: boom" in capsys.readouterr().out

    def test_login_failure_exits_nonzero(self) -> None:
        with patch.object(download_all, "login", side_effect=RuntimeError("no browser")):
            assert download_all.main() == 1
