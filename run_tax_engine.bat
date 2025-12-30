@echo off
cd /d "%~dp0"

echo ==========================================
echo    Austrian Tax Engine - Setup & Run
echo ==========================================

REM 1. Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python is not installed or not in PATH.
    echo Please install Python from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

REM 2. Create Virtual Environment
if not exist ".venv" (
    echo Creating Python virtual environment...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo Error creating virtual environment.
        pause
        exit /b 1
    )
)

REM Define paths
set PYTHON_BIN=.venv\Scripts\python.exe
set PIP_BIN=.venv\Scripts\pip.exe
set PLAYWRIGHT_BIN=.venv\Scripts\playwright.exe

REM 3. Install Dependencies
echo Checking/Installing dependencies...
"%PYTHON_BIN%" -m pip install --upgrade pip setuptools wheel
"%PYTHON_BIN%" -m pip install -e .
if %errorlevel% neq 0 (
    echo Error installing dependencies.
    pause
    exit /b 1
)

REM 4. Install Playwright Browsers
echo Checking Playwright browsers...
"%PLAYWRIGHT_BIN%" install chromium
if %errorlevel% neq 0 (
    echo Error installing Playwright browsers.
    pause
    exit /b 1
)

:menu
cls
echo ==========================================
echo    Austrian Tax Engine for E-Trade
echo ==========================================
echo 1. Login to E-Trade (Required first)
echo 2. Download All Data (ESPP, Orders, RSU)
echo 3. Calculate Tax
echo 4. Run Demo
echo 5. Exit
echo ==========================================
set /p choice="Select an option (1-5): "

if "%choice%"=="1" (
    echo Running Login...
    .venv\Scripts\tax-login
    pause
    goto menu
)
if "%choice%"=="2" (
    echo Downloading Data...
    .venv\Scripts\tax-download-all
    pause
    goto menu
)
if "%choice%"=="3" (
    echo Calculating Tax...
    .venv\Scripts\tax-calc
    pause
    goto menu
)
if "%choice%"=="4" (
    echo Running Demo...
    .venv\Scripts\tax-demo
    pause
    goto menu
)
if "%choice%"=="5" (
    exit /b 0
)

echo Invalid option.
pause
goto menu
