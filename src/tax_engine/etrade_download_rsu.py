"""
Download RSU release confirmation PDFs from E-Trade.

Uses the Stock Plan Confirmations page with the "Restricted Stock" (RS)
benefit type filter.
"""

from pathlib import Path

from .etrade_common import download_confirmations, run_download

OUTPUT_DIR = Path("input/rsu")


def download_rsu_confirmations() -> None:
    download_confirmations(
        benefit_type="RS",
        output_dir=OUTPUT_DIR,
        filename_prefix="RSU_Confirmation",
        label="RSU",
    )


def main() -> int:
    return run_download(download_rsu_confirmations)


if __name__ == "__main__":
    raise SystemExit(main())
