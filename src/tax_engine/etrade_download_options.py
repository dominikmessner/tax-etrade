"""
Download stock options exercise confirmation PDFs from E-Trade.

Uses the Stock Plan Confirmations page with the "Stock Options" (G) benefit
type filter.
"""

from pathlib import Path

from .etrade_common import download_confirmations

OUTPUT_DIR = Path("input/options")


def download_options_confirmations() -> None:
    download_confirmations(
        benefit_type="G",
        output_dir=OUTPUT_DIR,
        filename_prefix="Options_Confirmation",
        label="options",
    )


if __name__ == "__main__":
    download_options_confirmations()
