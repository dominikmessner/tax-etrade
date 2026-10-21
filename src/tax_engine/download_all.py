"""
Run the complete E-Trade download sequence: login, then every data source.

Each download step is independent; a failure in one is reported and the
remaining steps still run.
"""

import sys
from collections.abc import Callable

from .etrade_download_espp import download_benefit_history
from .etrade_download_options import download_options_confirmations
from .etrade_download_orders import download_orders
from .etrade_download_rsu import download_rsu_confirmations
from .etrade_login import login

DOWNLOAD_STEPS: list[tuple[str, Callable[[], None]]] = [
    ("Download ESPP History", download_benefit_history),
    ("Download Orders History", download_orders),
    ("Download RSU Confirmations", download_rsu_confirmations),
    ("Download Options Confirmations", download_options_confirmations),
]


def main() -> int:
    print("Starting full download process...")

    print("\n=== Step 1: Login ===")
    try:
        login()
    except Exception as e:
        print(f"Login failed: {e}")
        return 1

    failures = 0
    for number, (title, step) in enumerate(DOWNLOAD_STEPS, start=2):
        print(f"\n=== Step {number}: {title} ===")
        try:
            step()
        except Exception as e:
            failures += 1
            print(f"{title} failed: {e}")

    if failures:
        print(f"\nCompleted with {failures} failed step(s). See the messages above.")
        return 1
    print("\nAll tasks completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
