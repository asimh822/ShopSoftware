# United Mobile EPOS — Developer Guide

**System:** United Mobile, Shop 1-2, Rehma Commercial Center, Kutchery Road, Multan  
**Contact:** 0323-9637000  
**Tech stack:** Python + PyQt6 (desktop) · Flask (API) · React Native 0.73.6 (Android)  
**Last updated:** May 2026

---

## Contents

1. [Making changes to the source code](#1-making-changes-to-the-source-code)
2. [Building a new Windows installer](#2-building-a-new-windows-installer)
3. [Pushing a small update (no full reinstall)](#3-pushing-a-small-update-no-full-reinstall)
4. [Building the Android APK](#4-building-the-android-apk)
5. [Database — backup, restore and transfer](#5-database--backup-restore-and-transfer)
6. [Connecting phones to the shop PC](#6-connecting-phones-to-the-shop-pc)
7. [File map — what each file does](#7-file-map--what-each-file-does)
8. [Adding a database migration](#8-adding-a-database-migration)
9. [Troubleshooting common issues](#9-troubleshooting-common-issues)

---

## 1. Making Changes to the Source Code

All business logic lives in plain `.py` files in the `ShopSoftware\` folder.
No compilation step is required for development.

### Edit and test cycle

```
ShopSoftware\
├── main.py            ← app entry point, window layout, sidebar
├── database.py        ← all SQLite queries and migrations
├── masters.py         ← Brands, Models, Suppliers, Customers, Salesmen
├── purchase.py        ← Purchase form and purchase returns
├── sales.py           ← Sales form and sales returns
├── ledger.py          ← Ledger: Suppliers / Customers / Bank tabs
├── reports.py         ← All reports including Cash Book
├── receipt.py         ← Thermal receipt printing
├── settings_page.py   ← Settings page UI
├── login.py           ← PIN login screen
├── whatsapp_handler.py← WhatsApp message sending logic
├── whatsapp_page.py   ← WhatsApp settings UI
├── startup.py         ← Windows registry startup management
└── api_server.py      ← Flask API for the Android app
```

**Step 1 — Open the file you want to change**

Use any text editor. VS Code is recommended:

```
code E:\ShopSoftware
```

**Step 2 — Run the app to test your change**

```
cd E:\ShopSoftware
python main.py
```

The app starts, shows the PIN screen, then the main window.
Changes are live immediately — just close and rerun `python main.py`.

**Step 3 — No build needed for development**

You do NOT need to run `build.bat` for day-to-day development.
Only run build.bat when you want to create a packaged installer for the shop PC.

### Useful development tips

- The database file is `E:\ShopSoftware\united_mobile.db` during development.  
  The installed version uses `C:\UnitedMobile\united_mobile.db`.
- If the app crashes on start, run `python main.py` in a terminal to see the error.
- The API server starts automatically when `python main.py` runs.  
  To test the API separately: `python api_server.py`
- All amounts are PKR. All dates are DD/MM/YYYY. All brand/model names auto-uppercase.

---

## 2. Building a New Windows Installer

Do this when you want to deploy a new version to the shop PC as a full installer.

### Prerequisites

- Python 3.11+ on PATH
- Internet connection (first run downloads packages)
- Inno Setup 6 — download free from **https://jrsoftware.org/isinfo.php**

### Step 1 — Run the build script

Open Command Prompt in `E:\ShopSoftware\` and run:

```
build.bat
```

What it does:
1. Installs/upgrades: `pyinstaller`, `PyQt6`, `flask`, `flask-cors`, `python-escpos`, `pillow`, `pywhatkit`
2. Runs PyInstaller — bundles `main.py` into `dist\UnitedMobileEPOS\UnitedMobileEPOS.exe`
3. Copies all 18 `.py` files into `dist\UnitedMobileEPOS\`

First run takes 3–5 minutes. Output: `dist\UnitedMobileEPOS\`

### Step 2 — Compile the installer

1. Open **Inno Setup Compiler**
2. File → Open → select `E:\ShopSoftware\installer.iss`
3. Press **Ctrl+F9** (or Build → Compile)
4. Output: `E:\ShopSoftware\installer\UnitedMobile_Setup_v1.0.exe`

### Step 3 — Deploy to the shop PC

1. Copy `UnitedMobile_Setup_v1.0.exe` to a USB drive
2. On the shop PC: plug in USB, double-click the `.exe`, click through the wizard
3. Installs to `C:\UnitedMobile\`
4. Creates desktop shortcut + Start menu entry
5. Wizard offers to launch the app on the last page — tick and click Finish

### What the installer does automatically

- Installs everything to `C:\UnitedMobile\`
- Creates `C:\UnitedMobile\backups\` folder
- Adds desktop and Start menu shortcuts with the app icon
- On first launch, the app registers itself for Windows startup (staff see PIN screen on login)
- On uninstall: prompts to keep or delete `united_mobile.db` and the backups folder

---

## 3. Pushing a Small Update (No Full Reinstall)

When you change one or more `.py` files and want to push the fix to the shop PC
**without** rebuilding the full installer — use the update package.

This works because the installed app runs the `.py` files directly (they sit alongside
the `.exe` in `C:\UnitedMobile\`).

### Step 1 — Create the update package

On your development PC:

```
cd E:\ShopSoftware
create_update.bat
```

This creates `UnitedMobile_Update_DDMMYYYY.zip` (today's date) containing:
- All 18 `.py` source files
- `CLAUDE.md`
- `update.bat` (the script the shop PC runs)

### Step 2 — Transfer to shop PC

1. Copy the `.zip` file to a USB drive
2. Take the USB to the shop PC

### Step 3 — Apply the update on the shop PC

1. Close United Mobile EPOS on the shop PC
2. Insert USB, copy the zip to the Desktop (or anywhere convenient)
3. Right-click the zip → **Extract All** → Extract
4. Open the extracted folder
5. Double-click **`update.bat`**
6. The script copies all `.py` files to `C:\UnitedMobile\`
7. When it says "Update complete", close the window

### Step 4 — Restart the app

Double-click the United Mobile EPOS desktop shortcut.
The new code is now running.

> **Note:** If the update added a new database column or table, the migration system
> handles it automatically on startup. The shop will see:
> `"Database: applying migration to version N..."`

---

## 4. Building the Android APK

Full instructions are in:

```
mobile_app\UnitedMobileApp\BUILD_APK.md
```

### Quick summary

**Prerequisites (install once):**
- Node.js 18 LTS from https://nodejs.org
- JDK 17 from https://adoptium.net
- Android Studio from https://developer.android.com/studio
- `ANDROID_HOME` environment variable set to the Android SDK folder

**Build commands:**

```
cd E:\ShopSoftware\mobile_app\UnitedMobileApp
npm install
cd android
gradlew assembleRelease
```

**APK location after build:**

```
android\app\build\outputs\apk\release\app-release.apk
```

**Install on phone:**

```
adb install -r app-release.apk
```

Or copy the APK to the phone via USB and tap to install
(enable "Install from unknown sources" in phone Settings if prompted).

---

## 5. Database — Backup, Restore and Transfer

### Database file location

| Environment | Path |
|---|---|
| Development PC | `E:\ShopSoftware\united_mobile.db` |
| Installed (shop PC) | `C:\UnitedMobile\united_mobile.db` |

The entire system — all sales, purchases, stock, customers, suppliers, settings —
is in this single SQLite file.

### Manual backup (from the app)

Settings → **Backup Database** → choose a folder → saves `UnitedMobile_Backup_DDMMYYYY.db`

### Auto monthly backup

The app automatically backs up to `C:\UnitedMobile\backups\UnitedMobile_Backup_MMYYYY.db`
on the first startup of each new month.

### Transfer to a new PC

1. Copy `C:\UnitedMobile\united_mobile.db` from the old PC to a USB
2. Install the app on the new PC using the installer
3. Copy `united_mobile.db` from the USB to `C:\UnitedMobile\`
   (overwrite the empty database the installer created)
4. Launch the app — it will auto-migrate the schema if needed

### Restore from backup

1. Close the app on the shop PC
2. Copy the backup `.db` file to `C:\UnitedMobile\`
3. Rename it to `united_mobile.db` (overwriting the current file)
4. Relaunch the app

### Schema version

The app uses a versioned migration system. On every startup it prints:

```
Database is up to date - version 1
```

If an older database is loaded, it prints each migration it applies:

```
Database: applying migration to version 2...
Database is up to date - version 2
```

No data is ever deleted during migration — only new columns/tables are added.

---

## 6. Connecting Phones to the Shop PC

The Android app communicates with the shop PC over the local Wi-Fi network.
The PC runs a Flask API server on port 5000, which starts automatically when
the EPOS desktop app opens.

### Step 1 — Find the shop PC's IP address

On the shop PC, open **CMD** and type:

```
ipconfig
```

Look for **"Wireless LAN adapter Wi-Fi"** (if on Wi-Fi) or
**"Ethernet adapter"** (if on a network cable) and note the **IPv4 Address**:

```
IPv4 Address. . . . . . . . . . . : 192.168.1.5
```

### Step 2 — Connect the phone

1. Make sure the phone is on the **same Wi-Fi network** as the shop PC
2. Open the **United Mobile** app on the phone
3. If it shows "Cannot connect" — tap **Change Server**
4. Enter: `http://192.168.1.5:5000`   *(use your actual IP)*
5. Tap **Test Connection** — should show "Connected ✓"

### Step 3 — If the connection fails

**Check 1 — Is the EPOS app running on the PC?**
The API server only runs when the desktop app is open.

**Check 2 — Windows Firewall**
The firewall may be blocking port 5000. Fix:
1. Open **Windows Defender Firewall** → Advanced settings
2. Inbound Rules → New Rule
3. Rule type: Port → TCP → Specific port: `5000`
4. Action: Allow the connection
5. Name: `United Mobile EPOS API`

**Check 3 — Same network?**
Both devices must be on the same Wi-Fi router.
Phone on mobile data → won't work. Phone must use the shop Wi-Fi.

**Check 4 — IP changed?**
Router DHCP can assign a new IP after a reboot.
Check `ipconfig` again and update the phone's server URL.

### Tip — set a fixed IP for the shop PC

To avoid re-entering the IP every time the router reboots, set a static IP
on the shop PC (or reserve the DHCP address in the router settings).

---

## 7. File Map — What Each File Does

| File | Purpose |
|---|---|
| `main.py` | Entry point. PyQt6 app, main window, sidebar nav, dashboard, auto-starts API server |
| `database.py` | Every SQLite query. Schema creation and versioned migrations |
| `masters.py` | CRUD for Brands, Models, Suppliers, Customers, Salesmen |
| `purchase.py` | Purchase form (new purchases + purchase returns) |
| `sales.py` | Sales form (new sales + sales returns) |
| `ledger.py` | Ledger page: CP/CR payments, JV journal entries, bank tab |
| `reports.py` | Stock Summary, IMEI Stock, Valuation, Sales, Purchases, Profit, Cash Book |
| `receipt.py` | Thermal receipt builder and printer driver |
| `login.py` | PIN login dialog |
| `settings_page.py` | Settings UI: shop info, PIN, backup, bank accounts, year-end, startup toggle |
| `startup.py` | Windows registry helpers: add/remove app from startup |
| `whatsapp_handler.py` | Sends WhatsApp messages via pywhatkit |
| `whatsapp_page.py` | WhatsApp settings and connection UI |
| `api_server.py` | Flask API server for the Android app (port 5000) |
| `make_icon.py` | Run once to generate `icon.ico` and `icon.png` (Pillow) |
| `build.bat` | Builds the PyInstaller bundle → `dist\UnitedMobileEPOS\` |
| `installer.iss` | Inno Setup script → compiles to `UnitedMobile_Setup_v1.0.exe` |
| `create_update.bat` | Creates a dated `.zip` update package for pushing to the shop PC |
| `DEV_GUIDE.md` | This file |
| `CLAUDE.md` | Full system specification (AI-readable) |
| `united_mobile.db` | SQLite database — the entire data store |
| `backups\` | Auto and manual database backups |
| `mobile_app\UnitedMobileApp\` | React Native Android app source |
| `mobile_app\UnitedMobileApp\BUILD_APK.md` | Step-by-step APK build instructions |

---

## 8. Adding a Database Migration

When you add a new column or table to the schema, use the migration system
so that existing databases on the shop PC upgrade automatically.

### Example: adding a `notes` column to `customers`

**Step 1 — Write the migration function** in `database.py`:

```python
def _migrate_v2(conn) -> None:
    """Version 2: add notes column to customers table."""
    c = conn.cursor()
    try:
        c.execute("ALTER TABLE customers ADD COLUMN notes TEXT DEFAULT ''")
    except Exception:
        pass  # column already exists — safe to ignore
```

**Step 2 — Register it** in `_run_migrations()` in `database.py`:

```python
_MIGRATIONS: dict[int, callable] = {
    1: _migrate_v1,
    2: _migrate_v2,   # ← add this line
}
```

**Step 3 — Bump the version constant** at the top of `database.py`:

```python
CURRENT_DB_VERSION = 2   # was 1
```

**That's it.** On the next startup the console shows:

```
Database: applying migration to version 2...
Database is up to date - version 2
```

Rules for migration functions:
- **Never** `DROP TABLE`, `DROP COLUMN`, or `DELETE FROM`
- Always wrap `ALTER TABLE` in `try/except` (column might already exist)
- Use `CREATE TABLE IF NOT EXISTS` for new tables
- `INSERT OR IGNORE` for new seed data

---

## 9. Troubleshooting Common Issues

### Desktop app won't start

```
python main.py
```

Run from the terminal and read the traceback. Common causes:
- Missing package: `pip install <package-name>`
- Database locked: close any other running instance of the app
- Syntax error in a `.py` file: read the traceback for the file and line number

### App starts but shows blank/white screen

Usually a crash during page initialisation. Run from terminal to see the error.

### API server doesn't start

```
python api_server.py
```

Run directly and check for errors. Usually:
- Port 5000 already in use: another process has it. Find and kill it, or change the port in `api_server.py`.
- Missing flask: `pip install flask flask-cors`

### PyInstaller build fails

Common fixes:
- `pip install --upgrade pyinstaller` — update to latest
- Delete `build\` and `dist\` folders, run `build.bat` again
- If a specific module fails, add `--hidden-import <module>` to the PyInstaller command in `build.bat`

### Inno Setup compile error: "Source file not found"

Run `build.bat` first to create `dist\UnitedMobileEPOS\` before compiling `installer.iss`.

### App does not auto-start after installation

Check Settings → System Startup → ensure the checkbox is ticked.  
If it shows "Not registered", tick the checkbox to register it.  
The registry key is: `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\UnitedMobileEPOS`

### Database migration message on startup

```
Database: applying migration to version N...
```

This is normal and expected when a new version of the app is run against an older database.
It only runs once. Data is never lost.

### Android app "ECONNREFUSED" / "Network Error"

1. Confirm the desktop EPOS app is running on the shop PC
2. Run `ipconfig` on the PC and check the IP hasn't changed
3. Update the server URL in the phone app (Change Server)
4. Check Windows Firewall allows TCP port 5000
5. Confirm both devices are on the same Wi-Fi

### Year End Closing — "An error occurred"

Always take a **manual backup** (Settings → Backup Database) before running Year End.  
If the close fails, the database is NOT modified — safe to try again after fixing the issue.

---

*End of Developer Guide*
