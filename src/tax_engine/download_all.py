import sys

from tax_engine.etrade_download_espp import download_benefit_history
from tax_engine.etrade_download_orders import download_orders
from tax_engine.etrade_download_rsu import download_rsu_confirmations
from tax_engine.etrade_login import login


def main():
    print("Starting full download process...")

    print("\n=== Step 1: Login ===")
    try:
        login()
    except Exception as e:
        print(f"Login failed: {e}")
        sys.exit(1)

    print("\n=== Step 2: Download ESPP History ===")
    try:
        download_benefit_history()
    except Exception as e:
        print(f"ESPP download failed: {e}")
        # We might want to continue or exit depending on severity.
        # Usually if one fails, others might still work if session is valid.

    print("\n=== Step 3: Download Orders History ===")
    try:
        download_orders()
    except Exception as e:
        print(f"Orders download failed: {e}")

    print("\n=== Step 4: Download RSU Confirmations ===")
    try:
        download_rsu_confirmations()
    except Exception as e:
        print(f"RSU download failed: {e}")

    print("\nAll tasks completed.")

if __name__ == "__main__":
    main()
