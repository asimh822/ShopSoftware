@echo off
setlocal EnableDelayedExpansion

echo ============================================================
echo   United Mobile EPOS - Windows Build Script
echo   Builds dist\UnitedMobileEPOS\ ready for Inno Setup
echo ============================================================
echo.

REM ── Change to the folder where this script lives (ShopSoftware/) ─────────────
cd /d "%~dp0"

REM ── Verify Python is on PATH ──────────────────────────────────────────────────
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not on the PATH.
    echo        Install Python 3.11+ and make sure it is in your PATH.
    pause
    exit /b 1
)

REM ─────────────────────────────────────────────────────────────────────────────
REM  STEP 1 — Install / verify required packages
REM ─────────────────────────────────────────────────────────────────────────────
echo [1/3] Installing required Python packages...
echo.

pip install --quiet --upgrade ^
    pyinstaller ^
    PyQt6 ^
    flask ^
    flask-cors ^
    python-escpos ^
    pillow ^
    pywhatkit

if %errorlevel% neq 0 (
    echo.
    echo ERROR: pip install failed. Check your internet connection and try again.
    pause
    exit /b 1
)
echo       Packages OK.
echo.

REM ─────────────────────────────────────────────────────────────────────────────
REM  STEP 2 — Run PyInstaller
REM  --onedir   : one folder output, easier to push small updates later
REM  --windowed : no console window (staff only see the EPOS window)
REM  --noconfirm: overwrite previous dist\ without prompting
REM  --clean    : clear PyInstaller cache before building
REM ─────────────────────────────────────────────────────────────────────────────
echo [2/3] Running PyInstaller (first run takes 3-5 minutes)...
echo.

pyinstaller ^
    --name UnitedMobileEPOS ^
    --icon "icon.ico" ^
    --onedir ^
    --windowed ^
    --noconfirm ^
    --clean ^
    --distpath "dist" ^
    --workpath "build" ^
    --specpath "." ^
    --add-data "icon.ico;." ^
    --add-data "icon.png;." ^
    --add-data "CLAUDE.md;." ^
    --hidden-import PyQt6 ^
    --hidden-import PyQt6.sip ^
    --hidden-import PyQt6.QtCore ^
    --hidden-import PyQt6.QtWidgets ^
    --hidden-import PyQt6.QtGui ^
    --hidden-import PyQt6.QtPrintSupport ^
    --hidden-import flask ^
    --hidden-import flask_cors ^
    --hidden-import escpos ^
    --hidden-import escpos.printer ^
    --hidden-import pywhatkit ^
    --hidden-import sqlite3 ^
    --hidden-import winreg ^
    --hidden-import startup ^
    --collect-all PyQt6 ^
    main.py

if %errorlevel% neq 0 (
    echo.
    echo ============================================================
    echo   ERROR: PyInstaller build FAILED.
    echo   Check the output above for details.
    echo ============================================================
    pause
    exit /b 1
)

REM ─────────────────────────────────────────────────────────────────────────────
REM  STEP 3 — Copy extra files into the output folder
REM
REM  api_server.py is copied as a plain Python script so it can be launched
REM  as a subprocess by main.exe at runtime. Python must be installed on the
REM  shop PC for the mobile app to work (the desktop app runs standalone).
REM ─────────────────────────────────────────────────────────────────────────────
echo.
echo [3/3] Copying extra files to dist\UnitedMobileEPOS\...

copy /Y "api_server.py"      "dist\UnitedMobileEPOS\" >nul
copy /Y "database.py"        "dist\UnitedMobileEPOS\" >nul
copy /Y "masters.py"         "dist\UnitedMobileEPOS\" >nul
copy /Y "purchase.py"        "dist\UnitedMobileEPOS\" >nul
copy /Y "sales.py"           "dist\UnitedMobileEPOS\" >nul
copy /Y "ledger.py"          "dist\UnitedMobileEPOS\" >nul
copy /Y "reports.py"         "dist\UnitedMobileEPOS\" >nul
copy /Y "receipt.py"         "dist\UnitedMobileEPOS\" >nul
copy /Y "whatsapp_handler.py" "dist\UnitedMobileEPOS\" >nul
copy /Y "whatsapp_page.py"   "dist\UnitedMobileEPOS\" >nul
copy /Y "settings_page.py"   "dist\UnitedMobileEPOS\" >nul
copy /Y "login.py"           "dist\UnitedMobileEPOS\" >nul
copy /Y "startup.py"         "dist\UnitedMobileEPOS\" >nul

echo       Done.

REM ─────────────────────────────────────────────────────────────────────────────
REM  Summary
REM ─────────────────────────────────────────────────────────────────────────────
echo.
echo ============================================================
echo   Build complete -- output in dist\UnitedMobileEPOS\
echo ============================================================
echo.
echo   NEXT STEPS:
echo   1. Install Inno Setup 6 from https://jrsoftware.org/isinfo.php
echo   2. Open installer.iss in Inno Setup
echo   3. Click Compile  (Ctrl+F9)
echo   4. Output: installer\UnitedMobile_Setup_v1.0.exe
echo.
echo   NOTE: The mobile app API server (api_server.py) requires
echo         Python to be installed on the shop PC. The desktop
echo         EPOS app runs fully standalone without Python.
echo.
pause
