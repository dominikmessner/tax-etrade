"""
Download the ESPP Benefit History spreadsheet from E-Trade.
"""

import shutil
from datetime import datetime
from pathlib import Path

from .etrade_common import SessionError, stockplan_page

DOWNLOAD_DIR = Path("input/espp")
TARGET_FILENAME = "BenefitHistory.xlsx"


def backup_existing_file(file_path: Path) -> None:
    if file_path.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = file_path.with_name(f"{file_path.stem}_{timestamp}{file_path.suffix}")
        print(f"Backing up existing file to {backup_path}")
        shutil.move(str(file_path), str(backup_path))


def download_benefit_history() -> None:
    try:
        with stockplan_page(
            "benefitHistory", ready=lambda p: p.get_by_role("button", name="Download")
        ) as page:
            print("Downloading Benefit History...")
            try:
                page.get_by_role("button", name="Download").click()
                with page.expect_download() as download_info:
                    page.get_by_role("menuitem", name="Download Expanded").click()
                download = download_info.value
                print(f"Download started: {download.suggested_filename}")

                DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
                target_path = DOWNLOAD_DIR / TARGET_FILENAME
                backup_existing_file(target_path)
                download.save_as(target_path)
                print(f"Successfully saved to {target_path}")
            except Exception as e:
                print(f"Error during download: {e}")

            page.wait_for_timeout(2000)
    except SessionError as e:
        print(e)


if __name__ == "__main__":
    download_benefit_history()
