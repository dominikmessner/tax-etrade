"""
Download RSU release confirmation PDFs from E-Trade.

Uses the Stock Plan Confirmations page with the "Restricted Stock" (RS)
benefit type filter.
"""

from pathlib import Path

from .etrade_common import download_confirmations

OUTPUT_DIR = Path("input/rsu")


def download_rsu_confirmations() -> None:
    download_confirmations(
        benefit_type="RS",
        output_dir=OUTPUT_DIR,
        filename_prefix="RSU_Confirmation",
        label="RSU",
    )


if __name__ == "__main__":
    download_rsu_confirmations()
