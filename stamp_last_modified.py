import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "united_mobile.db")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

tables = [
    "suppliers", "customers", "bank_accounts", "purchase_vouchers",
    "sale_vouchers", "sale_lines", "stock_items", "models", "brands",
    "payments", "journal_entries", "purchase_returns", "sale_returns",
    "bank_transactions", "cash_journal_lines", "expenses"
]

for table in tables:
    try:
        c.execute(f"UPDATE {table} SET last_modified = CURRENT_TIMESTAMP")
        print(f"Updated {table}: {c.rowcount} rows")
    except Exception as e:
        print(f"Skipped {table}: {e}")

conn.commit()
conn.close()
print("Done.")
