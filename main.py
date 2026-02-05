#!/usr/bin/env python3
"""
Austrian Tax Engine for E-Trade RSUs and ESPP

Calculates capital gains tax using the Austrian moving average cost basis method
(Gleitender Durchschnittspreis) for stocks acquired through RSU vesting and ESPP purchases.

Main entry point for the application.
"""

import sys
from pathlib import Path

# Ensure src is in path if running directly
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.append(str(src_path))

from tax_engine.cli_main import main

if __name__ == "__main__":
    main()
