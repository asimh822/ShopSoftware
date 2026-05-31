# CLAUDE.md — United Mobile EPOS System
# Updated: May 2026 — Full current state

---

## Project Overview

A desktop EPOS (Electronic Point of Sale) system for **United Mobile**, a mobile phone retail
shop in Multan, Pakistan. Replaces an existing VB6 + MS Access + Crystal Reports setup.
Includes a Flask API server and React Native Android app for salesmen.

---

## Shop Details

- **Name:** United Mobile
- **Address:** Shop 1-2, Rehma Commercial Center, Kutchery Road, Multan
- **Contact:** 0323-9637000
- **Business:** Mobile phone retail — buys from wholesalers on credit, sells to walk-in
  cash customers and trade/dealer credit customers

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python |
| Database | SQLite — single file: united_mobile.db |
| UI Framework | PyQt6 |
| Thermal Printing | python-escpos |
| WhatsApp | whatsapp-web.py |
| API Server | Flask + Flask-CORS (port 5000) |
| Mobile App | React Native CLI (Android) |
| Platform | Windows, offline-first (except WhatsApp and mobile app) |

---

## File Structure

```
ShopSoftware/
├── main.py               # PyQt6 app entry point and main window
├── database.py           # DB setup, table creation, migrations
├── masters.py            # Brands, Models, Suppliers, Customers, Salesmen
├── purchase.py           # Purchase form and purchase returns
├── sales.py              # Sales form and sales returns
├── ledger.py             # Ledger — Suppliers, Customers, Bank tabs
├── reports.py            # All reports including Cash Book
├── receipt.py            # Thermal receipt printing
├── whatsapp_handler.py   # WhatsApp sending via whatsapp-web.py
├── whatsapp_page.py      # WhatsApp settings and connection UI
├── settings_page.py      # Settings, PIN, backup, bank accounts, year end
├── api_server.py         # Flask API server for mobile app
├── CLAUDE.md             # This file
├── united_mobile.db      # SQLite database — entire system
├── backups/              # Auto and manual database backups
└── mobile_app/
    └── UnitedMobileApp/  # React Native Android app
```

---

## Complete Database Schema

```sql
CREATE TABLE brands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL  -- stored UPPERCASE
);

CREATE TABLE models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id INTEGER REFERENCES brands(id),
    name TEXT NOT NULL,           -- stored UPPERCASE e.g. "A17 8+256"
    reference_price REAL
);

CREATE TABLE suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,           -- Title Case
    contact TEXT,                 -- 11 digits starting with 03
    opening_balance REAL DEFAULT 0
);

CREATE TABLE customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,           -- Title Case
    contact TEXT,                 -- 11 digits starting with 03
    type TEXT CHECK(type IN ('credit','cash')),
    opening_balance REAL DEFAULT 0
);

CREATE TABLE salesmen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,           -- Title Case
    pin TEXT NOT NULL,            -- 4 digits, unique
    active INTEGER DEFAULT 1,
    created_date TEXT
);

CREATE TABLE bank_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    opening_balance REAL DEFAULT 0
);

CREATE TABLE stock_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id INTEGER REFERENCES models(id),
    imei TEXT UNIQUE NOT NULL,    -- exactly 15 digits
    purchase_line_id INTEGER REFERENCES purchase_lines(id),
    purchase_price REAL NOT NULL,
    status TEXT CHECK(status IN ('in_stock','sold','returned')) DEFAULT 'in_stock',
    sold_line_id INTEGER REFERENCES sale_lines(id)
);

CREATE TABLE purchase_vouchers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pv_number TEXT UNIQUE NOT NULL,
    supplier_id INTEGER REFERENCES suppliers(id),
    date TEXT NOT NULL,
    total_amount REAL,
    notes TEXT,
    salesman_id INTEGER REFERENCES salesmen(id)
);

CREATE TABLE purchase_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pv_id INTEGER REFERENCES purchase_vouchers(id),
    model_id INTEGER REFERENCES models(id),
    imei TEXT NOT NULL,
    purchase_price REAL NOT NULL
);

CREATE TABLE sale_vouchers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sv_number TEXT UNIQUE NOT NULL,
    type TEXT CHECK(type IN ('credit','cash')),
    customer_id INTEGER REFERENCES customers(id),
    cash_customer_name TEXT,
    cash_customer_contact TEXT,
    date TEXT NOT NULL,
    total_amount REAL,
    discount REAL DEFAULT 0,
    note TEXT,
    whatsapp_sent INTEGER DEFAULT 0,
    salesman_id INTEGER REFERENCES salesmen(id),
    payment_method TEXT CHECK(payment_method IN ('cash','bank','split')),
    cash_amount REAL DEFAULT 0,
    bank_amount REAL DEFAULT 0
);

CREATE TABLE sale_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sv_id INTEGER REFERENCES sale_vouchers(id),
    stock_item_id INTEGER REFERENCES stock_items(id),
    model_id INTEGER REFERENCES models(id),
    imei TEXT NOT NULL,
    reference_price REAL,
    discount REAL DEFAULT 0,
    final_price REAL NOT NULL
);

CREATE TABLE payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    voucher_number TEXT UNIQUE NOT NULL,
    party_type TEXT CHECK(party_type IN ('supplier','customer','bank')),
    party_id INTEGER,
    date TEXT NOT NULL,
    amount REAL NOT NULL,
    type TEXT CHECK(type IN ('CP','CR')),
    notes TEXT,
    payment_method TEXT CHECK(payment_method IN ('cash','bank'))
);

CREATE TABLE journal_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    jv_number TEXT UNIQUE NOT NULL,
    dr_party_type TEXT,           -- supplier / customer / bank / cash
    dr_party_id INTEGER,
    cr_party_type TEXT,
    cr_party_id INTEGER,
    date TEXT NOT NULL,
    amount REAL NOT NULL,         -- Dr must equal Cr
    notes TEXT
);

CREATE TABLE purchase_returns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pr_number TEXT UNIQUE NOT NULL,
    supplier_id INTEGER REFERENCES suppliers(id),
    date TEXT NOT NULL,
    total_amount REAL,
    notes TEXT
);

CREATE TABLE purchase_return_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pr_id INTEGER REFERENCES purchase_returns(id),
    stock_item_id INTEGER REFERENCES stock_items(id),
    model_id INTEGER REFERENCES models(id),
    imei TEXT NOT NULL,
    purchase_price REAL
);

CREATE TABLE sale_returns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sr_number TEXT UNIQUE NOT NULL,
    customer_id INTEGER REFERENCES customers(id),
    date TEXT NOT NULL,
    total_amount REAL,
    notes TEXT
);

CREATE TABLE sale_return_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sr_id INTEGER REFERENCES sale_returns(id),
    stock_item_id INTEGER REFERENCES stock_items(id),
    model_id INTEGER REFERENCES models(id),
    imei TEXT NOT NULL,
    sale_price REAL
);

CREATE TABLE sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token TEXT UNIQUE NOT NULL,
    salesman_id INTEGER REFERENCES salesmen(id),
    created_date TEXT
);

CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
-- Keys used: shop_name, shop_address, shop_contact, whatsapp_template,
-- last_pv_number, last_sv_number, last_cp_number, last_cr_number,
-- last_jv_number, last_pr_number, last_sr_number,
-- bank_opening_balance, cash_opening_balance,
-- last_backup_date, financial_year_start, financial_year_end, app_pin
```

---

## General Rules (apply everywhere)

- Amounts: PKR with comma formatting. Display as **Rs.** in reports.
- Dates: DD/MM/YYYY
- Phone numbers: exactly 11 digits starting with 03. Validated everywhere.
- Brand and Model names: always UPPERCASE. Auto-convert as user types.
- All other names: Title Case. Auto-convert as user types.
- Enter key = Tab key throughout entire app. No exceptions.
- IMEI: exactly 15 digits. Max 15 characters in field.

---

## Purchase Module

- Date auto today, editable. Supplier dropdown. Brand → Model cascading.
- Reference price loads automatically, overridable per purchase.
- Discount and Net Price at batch level (not per IMEI row).
- IMEI entry one at a time, 15 digits.
  - Block if status = in_stock. Allow if status = sold (repurchase).
- Salesman dropdown mandatory.
- On save: PV-XXXX created, stock_items created (in_stock), supplier balance UP.

**Purchase Return:**
- Select supplier, enter IMEIs via dropdown search.
- Validates each IMEI was purchased FROM selected supplier.
- On save: stock_items DELETED permanently, supplier balance DOWN, PR-XXXX created.

---

## Sales Module

- Salesman dropdown mandatory (active only).
- Sale type: Cash or Credit.

**Cash:** Contact first → 11-digit validation → auto-lookup → name auto-fill or manual.
**Credit:** Searchable customer dropdown (credit customers only).

**IMEI search:** Type digits → dropdown list → select by mouse or keyboard.
Single result selectable same as multiple results.

**Payment method:** Cash / Bank Transfer (account + ref) / Split (cash + bank must equal total).

**On save:** SV-XXXX, stock → sold, balances updated, receipt printed, WhatsApp if ticked.

**Sales Return:**
- Select customer, enter IMEIs, validates sold to that customer.
- On save: stock → in_stock (resellable), customer balance DOWN, SR-XXXX.

---

## Ledger

Three tabs: Suppliers | Customers | Bank

**CP (Cash Payment):** Party = Supplier / Customer / Bank
- Supplier: balance DOWN. Customer: balance DOWN. Bank: cash→bank, cash DOWN, bank UP.

**CR (Cash Receipt):** Party = Supplier / Customer / Bank
- Supplier: balance DOWN. Customer: balance DOWN. Bank: bank→cash, bank DOWN, cash UP.

**JV (Journal Voucher):** Double entry, Dr = Cr required.
- Accounts: Bank, Cash in Hand, any Supplier, any Customer.
- Affects both party ledgers and bank/cash balances.

---

## Reports

- **Stock Summary:** 3-column grid, brand heading with total units, model + qty.
- **IMEI Stock:** All in_stock IMEIs, supplier column, double-click copy, Use in Sale button.
- **Stock Valuation:** 3-column grid, brand (units + value), model + qty + value.
- **Sales:** Date range, salesman filter, export CSV.
- **Purchases:** Date range, export CSV.
- **Profit:** Per IMEI sold, purchase vs sale price.
- **Cash Book:** Today/Yesterday buttons, compact summary (Cash + Bank lines),
  two columns (Cash In / Cash Out), description states (Cash) or (Bank), JV excluded.

**Cash Book transaction rules:**
- Cash sale → Cash In = full (Cash)
- Bank sale → Cash In = full (Bank) + Cash Out = full (Bank)
- Split sale → Cash In = full (Split) + Cash Out = bank portion (Split)
- Customer pays cash → Cash In (Cash)
- Customer pays bank → Cash In + Cash Out (Bank)
- Pay supplier cash → Cash Out (Cash)
- Pay supplier bank → Cash In + Cash Out (Bank)
- Cash deposit → Cash Out
- Cash withdrawal → Cash In
- JV → excluded

---

## WhatsApp

- Cash sales only. Optional checkbox (default checked).
- whatsapp-web.py, QR scan once, session saved.
- Template editable in Settings. Variables: {customer_name} {model_name} {imei} {shop_contact} {date}

---

## Year End Closing

- Archive all transactions to UnitedMobile_Archive_YYYY.db
- Carry forward: supplier/customer/bank/cash balances, all unsold stock
- Clear all transactions, reset all voucher sequences to 0001

---

## Backup

- Auto monthly: background thread on startup, backups/ folder, UnitedMobile_Backup_MMYYYY.db
- Manual: Settings button, folder picker, UnitedMobile_Backup_DDMMYYYY.db

---

## Thermal Receipt

```
      UNITED MOBILE
  Kutchery Road, Multan
    0323-9637000
  Sold by: [Salesman Name]
--------------------------------
Invoice: SV-0001  Date: DD/MM/YYYY
Customer: Name
--------------------------------
Model     IMEI(last 5)    Price
A17 8+256    11111       59,500
--------------------------------
Discount:                  -500
TOTAL:                   59,000
--------------------------------
Payment: Cash
[Note]
--------------------------------
  Thank you for your purchase!
```

---

## Flask API (api_server.py) — Port 5000

**Public:**
- GET /api/health — {status: ok}
- POST /api/login — {pin} → {success, token, salesman_id, salesman_name}

**Protected (Authorization header required):**
- GET /api/stock?search= — in_stock grouped by brand/model
- GET /api/imei/search?digits= — LIKE digits%, in_stock, max 10
- GET /api/customers/search?phone= — exact match + last purchase
- GET /api/customers/list — all credit customers for dropdown
- GET /api/suppliers — all suppliers
- GET /api/brands — brands with models and prices
- POST /api/sale — create sale, validate IMEIs, update stock/balances
- POST /api/purchase — create purchase, validate no in_stock duplicates
- GET /api/salesman/today?salesman_id= — today's sales for salesman

401 on invalid token → app redirects to Login.

---

## React Native App (mobile_app/UnitedMobileApp/)

**Screens:** Setup | Login | Home | New Sale | New Purchase | Stock Check | My Today

**Key behaviours:**
- Setup: URL entry, Test Connection hits /api/health
- Login: 4-digit keypad, auto-submit at 4 digits
- Home: 4 tiles, salesman name in header (must not overlap tiles)
- New Sale Cash: contact FIRST → auto-lookup → name. WhatsApp checkbox.
- New Sale Credit: customer dropdown from /api/customers/list
- New Purchase: supplier dropdown, brand→model, IMEI validation
- Stock Check: grouped, expandable, pull to refresh
- My Today: salesman's own sales only

**Connection:** Local Wi-Fi only. Same network = works. PC IP via ipconfig.
URL: http://192.168.x.x:5000. Windows Firewall must allow TCP 5000.

---

## Pending Items (May 2026)

1. Mobile: Home icon/name overlap fix
2. Mobile: Cash sale contact-first flow
3. Mobile: Credit sale customer dropdown
4. Mobile: Stock Check no data fix
5. Mobile: Purchase supplier dropdown fix
6. Desktop: Enter = Tab everywhere
7. Desktop: Cash Book compact layout + Rs. + Yesterday button
