#!/bin/bash

# Ensure we are in the directory of the script
cd "$(dirname "$0")"

echo "=========================================="
echo "   Austrian Tax Engine - Setup & Run"
echo "=========================================="

# 1. Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed."
    echo "Please install Python 3 from https://www.python.org/downloads/"
    echo "or run 'brew install python' if you have Homebrew."
    read -p "Press Enter to exit..."
    exit 1
fi

# 2. Create Virtual Environment if missing
if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment (.venv)..."
    python3 -m venv .venv
    if [ $? -ne 0 ]; then
        echo "Error creating virtual environment."
        read -p "Press Enter to exit..."
        exit 1
    fi
fi

# Define paths to venv executables
PYTHON_BIN=".venv/bin/python3"
PLAYWRIGHT_BIN=".venv/bin/playwright"

# 3. Install Dependencies (using venv python directly)
echo "Checking/Installing dependencies..."
"$PYTHON_BIN" -m pip install --upgrade pip setuptools wheel
"$PYTHON_BIN" -m pip install -e .
if [ $? -ne 0 ]; then
    echo "Error installing dependencies."
    read -p "Press Enter to exit..."
    exit 1
fi

# 4. Install Playwright Browsers
echo "Checking Playwright browsers..."
"$PLAYWRIGHT_BIN" install chromium
if [ $? -ne 0 ]; then
    echo "Error installing Playwright browsers."
    read -p "Press Enter to exit..."
    exit 1
fi

# 5. Main Menu Loop
while true; do
    clear
    echo "=========================================="
    echo "   Austrian Tax Engine for E-Trade"
    echo "=========================================="
    echo "1. Login to E-Trade (Required first)"
    echo "2. Download All Data (ESPP, Orders, RSU)"
    echo "3. Calculate Tax"
    echo "4. Run Demo"
    echo "5. Exit"
    echo "=========================================="
    read -p "Select an option (1-5): " choice

    case $choice in
        1)
            echo "------------------------------------------"
            echo "Running Login..."
            echo "A browser window will open. Please log in."
            echo "------------------------------------------"
            .venv/bin/tax-login
            echo ""
            read -p "Press Enter to return to menu..."
            ;;
        2)
            echo "------------------------------------------"
            echo "Downloading Data..."
            echo "------------------------------------------"
            .venv/bin/tax-download
            echo ""
            read -p "Press Enter to return to menu..."
            ;;
        3)
            echo "------------------------------------------"
            echo "Calculating Tax..."
            echo "------------------------------------------"
            .venv/bin/tax-engine
            echo ""
            read -p "Press Enter to return to menu..."
            ;;
        4)
            echo "------------------------------------------"
            echo "Running Demo..."
            echo "------------------------------------------"
            .venv/bin/tax-demo
            echo ""
            read -p "Press Enter to return to menu..."
            ;;
        5)
            echo "Exiting..."
            exit 0
            ;;
        *)
            echo "Invalid option."
            read -p "Press Enter to continue..."
            ;;
    esac
done
