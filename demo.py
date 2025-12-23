#!/usr/bin/env python3
"""
Demo script to run the tax engine with sample data.

This script demonstrates the tax engine functionality using the sample data.
"""
import sys
from pathlib import Path

# Ensure src is in path if running directly
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.append(str(src_path))

from tax_engine.cli_demo import main

if __name__ == "__main__":
    main()
