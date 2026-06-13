@echo off
set SRC=E:\ShopSoftware
set DST=E:\ShopSoftware(shop)

echo Creating folder...
if not exist "%DST%" mkdir "%DST%"

echo Copying Python source files...
copy "%SRC%\main.py"              "%DST%\"
copy "%SRC%\database.py"          "%DST%\"
copy "%SRC%\masters.py"           "%DST%\"
copy "%SRC%\purchase.py"          "%DST%\"
copy "%SRC%\sales.py"             "%DST%\"
copy "%SRC%\ledger.py"            "%DST%\"
copy "%SRC%\reports.py"           "%DST%\"
copy "%SRC%\expenses.py"          "%DST%\"
copy "%SRC%\receipt.py"           "%DST%\"
copy "%SRC%\whatsapp_handler.py"  "%DST%\"
copy "%SRC%\whatsapp_page.py"     "%DST%\"
copy "%SRC%\settings_page.py"     "%DST%\"
copy "%SRC%\api_server.py"        "%DST%\"

echo Copying assets and config...
copy "%SRC%\icon.ico"             "%DST%\"
copy "%SRC%\build.bat"            "%DST%\"
copy "%SRC%\installer.iss"        "%DST%\"
copy "%SRC%\create_update.bat"    "%DST%\"
copy "%SRC%\CLAUDE.md"            "%DST%\"

echo Copying mobile APK...
set APK_SRC=%SRC%\mobile_app\UnitedMobileApp\android\app\build\outputs\apk\release\unitedmobile.apk
if exist "%APK_SRC%" (
    copy "%APK_SRC%" "%DST%\"
    echo   unitedmobile.apk copied.
) else (
    echo   WARNING: APK not found - build it first with gradlew assembleRelease
)

echo.
echo ============================================================
echo  Done! Copied to: %DST%
echo  Files to deploy on shop PC:
echo    - All .py files  ^>  replace in shop software folder
echo    - unitedmobile.apk  ^>  install on Android phone
echo    - NOTE: database NOT copied ^(shop PC keeps its own data^)
echo ============================================================
pause
