"""
Run this ONCE on the Shop PC after deploying the updated files.

What it does:
  1. Deletes all rows from Supabase for the listed tables (a clean slate).
  2. Pushes cash_opening_balance from local settings to Supabase settings table.
  3. Resets last_supabase_sync in the local SQLite DB to epoch so the next
     app startup pushes EVERY local row to Supabase.

Usage (from ShopSoftware folder on Shop PC):
    python reset_supabase_and_sync.py
"""

import os
import json
import sqlite3
import requests

# Read credentials from supabase_sync.py — key is stored there, not repeated here
from supabase_sync import SUPABASE_URL, SUPABASE_KEY

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "united_mobile.db")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Prefer": "return=minimal",
}

ID_TABLES = [
    "sale_lines",
    "sale_vouchers",
    "purchase_vouchers",
    "stock_items",
    "payments",
    "journal_entries",
    "purchase_returns",
    "sale_returns",
    "expenses",
    "bank_transactions",
    "cash_journal_lines",
    "suppliers",
    "customers",
    "bank_accounts",
    "models",
    "brands",
]

print("=" * 55)
print("Step 1 — Truncating Supabase tables")
print("=" * 55)

for table in ID_TABLES:
    r = requests.delete(f"{SUPABASE_URL}/rest/v1/{table}?id=gte.0", headers=HEADERS)
    status = "OK" if r.status_code in (200, 204) else f"ERROR {r.status_code}: {r.text[:80]}"
    print(f"  {table:<25} {status}")

# sync_log may use id or synced_at
r = requests.delete(f"{SUPABASE_URL}/rest/v1/sync_log?id=gte.0", headers=HEADERS)
if r.status_code in (200, 204):
    print(f"  {'sync_log':<25} OK")
else:
    r2 = requests.delete(
        f"{SUPABASE_URL}/rest/v1/sync_log?synced_at=gte.2000-01-01T00:00:00Z",
        headers=HEADERS,
    )
    status2 = "OK" if r2.status_code in (200, 204) else f"ERROR {r2.status_code}: {r2.text[:80]}"
    print(f"  {'sync_log':<25} {status2}")

print()
print("=" * 55)
print("Step 2 — Syncing cash_opening_balance to Supabase")
print("=" * 55)

conn = sqlite3.connect(DB_PATH)
ob_row = conn.execute(
    "SELECT value FROM settings WHERE key='cash_opening_balance'"
).fetchone()
cash_ob = ob_row[0] if ob_row else "0"

upsert_headers = {**HEADERS, "Content-Type": "application/json",
                  "Prefer": "resolution=merge-duplicates"}
r = requests.post(
    f"{SUPABASE_URL}/rest/v1/settings",
    headers=upsert_headers,
    data=json.dumps([{"key": "cash_opening_balance", "value": cash_ob}]),
)
status = "OK" if r.status_code in (200, 201) else f"ERROR {r.status_code}: {r.text[:80]}"
print(f"  cash_opening_balance = {cash_ob}   {status}")

print()
print("=" * 55)
print("Step 3 — Resetting last_supabase_sync in local DB")
print("=" * 55)

conn.execute(
    "UPDATE settings SET value = '2000-01-01 00:00:00' WHERE key = 'last_supabase_sync'"
)
conn.commit()
conn.close()
print("  last_supabase_sync reset to 2000-01-01 00:00:00")

print()
print("Done. Start the EPOS app — it will push all data to Supabase on startup.")
