import sys

import pytest


def main() -> None:
    """Run all tests using pytest."""
    # Pass command line arguments to pytest, or default to current directory
    args = sys.argv[1:] if len(sys.argv) > 1 else ["tests"]
    sys.exit(pytest.main(args))


if __name__ == "__main__":
    main()
