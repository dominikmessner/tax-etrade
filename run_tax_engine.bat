@echo off
cd /d "%~dp0"

echo ==========================================
echo    Austrian Tax Engine - Setup ^& Run
echo ==========================================
echo Working directory: %CD%

REM Check that pyproject.toml exists
if not exist "pyproject.toml" (
    echo ERROR: pyproject.toml not found in %CD%
    echo.
    echo Make sure you extracted the ENTIRE project folder and are
    echo running this script from inside the tax-engine directory.
    pause
    exit /b 1
)

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
echo 3. Calculate Tax (all years)
echo 4. Calculate One Tax Year + Document Bundle
echo 5. Run Demo
echo 6. Exit
echo ==========================================
set /p choice="Select an option (1-6): "

if "%choice%"=="1" (
    echo Running Login...
    .venv\Scripts\tax-login
    pause
    goto menu
)
if "%choice%"=="2" (
    echo Downloading Data...
    .venv\Scripts\tax-download
    pause
    goto menu
)
if "%choice%"=="3" (
    echo Calculating Tax...
    .venv\Scripts\tax-engine
    pause
    goto menu
)
if "%choice%"=="4" (
    set /p tax_year="Which tax year? (e.g. 2025): "
    call :run_year
    pause
    goto menu
)
if "%choice%"=="5" (
    echo Running Demo...
    .venv\Scripts\tax-demo
    pause
    goto menu
)
if "%choice%"=="6" (
    exit /b 0
)

echo Invalid option.
pause
goto menu

REM Runs one tax year in a subroutine so %tax_year% is expanded after it is read
REM (inside the if-block above it would still hold its old value).
:run_year
echo Calculating tax year %tax_year% and building the document bundle...
.venv\Scripts\tax-engine --year %tax_year%
echo.
echo The bundle is in: output\Steuerakt_%tax_year%\
exit /b 0
