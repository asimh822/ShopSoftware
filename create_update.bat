@echo off
setlocal EnableDelayedExpansion

echo ============================================================
echo   United Mobile EPOS - Create Update Package
echo ============================================================
echo.

REM Change to the folder that contains this script (ShopSoftware\)
cd /d "%~dp0"

REM ── Get today's date in DDMMYYYY (locale-independent via PowerShell) ─────────
for /f "tokens=*" %%a in ('powershell -NoLogo -NonInteractive -Command "Get-Date -Format ddMMyyyy"') do set TODAY=%%a

set UPDATE_FOLDER=UnitedMobile_Update_%TODAY%
set UPDATE_ZIP=UnitedMobile_Update_%TODAY%.zip

echo Package name : %UPDATE_FOLDER%
echo.

REM ── Create a fresh update folder ──────────────────────────────────────────────
if exist "%UPDATE_FOLDER%" (
    echo Removing old %UPDATE_FOLDER%...
    rmdir /s /q "%UPDATE_FOLDER%"
)
mkdir "%UPDATE_FOLDER%"

REM ── Copy all Python source files ──────────────────────────────────────────────
echo [1/3] Copying source files...

for %%f in (*.py) do (
    copy /Y "%%f" "%UPDATE_FOLDER%\" >nul
    echo       %%f
)
copy /Y CLAUDE.md "%UPDATE_FOLDER%\" >nul
echo       CLAUDE.md
echo.

REM ── Generate update.bat inside the folder ────────────────────────────────────
REM    Using PowerShell to avoid batch-in-batch escaping issues.
REM    The generated update.bat is what the shop PC runs after extracting the zip.
echo [2/3] Creating update.bat...

powershell -NoLogo -NonInteractive -Command "$lines = '@echo off', 'setlocal', '', 'echo ============================================================', 'echo   United Mobile EPOS - Apply Update', 'echo ============================================================', 'echo.', 'echo Checking install directory...', 'if not exist C:\UnitedMobile\ (', '    echo ERROR: C:\UnitedMobile\ not found.', '    echo Is United Mobile EPOS installed on this PC?', '    pause', '    exit /b 1', ')', '', 'echo Copying updated Python files to C:\UnitedMobile\...', 'echo.', 'copy /Y *.py C:\UnitedMobile\', 'copy /Y CLAUDE.md C:\UnitedMobile\', 'echo.', 'echo ============================================================', 'echo   Update complete -- please restart the application', 'echo ============================================================', 'echo.', 'pause'; $lines | Set-Content -Path '%UPDATE_FOLDER%\update.bat' -Encoding ASCII"

if %errorlevel% neq 0 (
    echo ERROR: Could not create update.bat
    pause
    exit /b 1
)
echo       update.bat created.
echo.

REM ── Zip the update folder ─────────────────────────────────────────────────────
echo [3/3] Creating zip archive...

if exist "%UPDATE_ZIP%" del /f /q "%UPDATE_ZIP%"

powershell -NoLogo -NonInteractive -Command "Compress-Archive -Path '%UPDATE_FOLDER%' -DestinationPath '%UPDATE_ZIP%' -Force"

if %errorlevel% neq 0 (
    echo.
    echo ERROR: Could not create zip file.
    echo The unzipped folder has been left in place: %UPDATE_FOLDER%
    pause
    exit /b 1
)

REM ── Clean up the temporary unzipped folder ─────────────────────────────────────
rmdir /s /q "%UPDATE_FOLDER%"

REM ── Done ──────────────────────────────────────────────────────────────────────
echo.
echo ============================================================
echo   Update package created -- %UPDATE_ZIP%
echo   Copy the zip to a USB and run update.bat on the shop PC
echo ============================================================
echo.
echo   HOW TO APPLY THE UPDATE ON THE SHOP PC:
echo   1. Copy %UPDATE_ZIP% to a USB drive
echo   2. On the shop PC: insert USB, right-click the zip, Extract All
echo   3. Open the extracted folder
echo   4. Double-click update.bat
echo   5. Restart United Mobile EPOS
echo.
pause
