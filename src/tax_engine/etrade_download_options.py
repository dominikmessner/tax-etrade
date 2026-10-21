"""
Download stock options exercise confirmation PDFs from E-Trade.

Uses the Stock Plan Confirmations page with the "Stock Options" (G) benefit
type filter.
"""

from pathlib import Path

from .etrade_common import download_confirmations, run_download

OUTPUT_DIR = Path("input/options")


def download_options_confirmations() -> None:
    download_confirmations(
        benefit_type="G",
        output_dir=OUTPUT_DIR,
        filename_prefix="Options_Confirmation",
        label="options",
    )


def main() -> int:
    return run_download(download_options_confirmations)


if __name__ == "__main__":
    raise SystemExit(main())
