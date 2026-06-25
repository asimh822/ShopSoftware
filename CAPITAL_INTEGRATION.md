# Capital Module — Integration Guide
# United Mobile EPOS — May 2026

## Files Provided
- capital.py  →  Drop into ShopSoftware/ folder

---

## Step 1 — database.py
Add this near the end of your DB setup function (wherever you create tables):

```python
from capital import migrate_capital_tables

# At end of setup_database() or create_tables():
migrate_capital_tables(conn)
```

---

## Step 2 — main.py (Add Capital tab to navigation)

Find where you create your sidebar navigation buttons (Ledger, Reports etc.)
and add a Capital button:

```python
from capital import CapitalPage

# In your sidebar button list, add after Ledger:
capital_btn = QPushButton("Capital")
capital_btn.clicked.connect(lambda: self.show_page("capital"))
self.sidebar_layout.addWidget(capital_btn)

# In your page stack / show_page method:
self.capital_page = CapitalPage()
self.stacked_widget.addWidget(self.capital_page)

# In show_page():
elif page == "capital":
    self.stacked_widget.setCurrentWidget(self.capital_page)
```

---

## Step 3 — Seed the 3 investors (run once in Python console or add to DB directly)

```python
import sqlite3
from datetime import date

conn = sqlite3.connect("united_mobile.db")
conn.execute("""
    INSERT INTO capital_accounts(name, contact, opening_balance, created_date)
    VALUES
    ('Asim Hussain',  NULL, 3000000, ?),
    ('Khurram Ansari', NULL, 1500000, ?),
    ('Mumtaz Ahmad',   NULL, 1500000, ?)
""", (date.today().isoformat(),) * 3)
conn.commit()
conn.close()
print("Investors seeded.")
```

OR simply use the UI → + Add Investor button after launching the app.

---

## Step 4 — Opening Stock Adjustment (ONE TIME ONLY)

1. Open the app → go to Capital page
2. Click "⚖ Adjust Opening Stock" button
3. Review the split (Rs. 4,746,880 ÷ 3 = Rs. 1,582,293 each)
4. Click "Apply Adjustment"

This will:
- Set the Opening Stock supplier balance to zero
- Add adjustment transactions to each investor's capital account
- No cash/bank is affected (it's a pure reclassification)

---

## Step 5 — Dashboard (optional but recommended)

In your dashboard widget, add a Capital summary card:

```python
from capital import get_total_capital, get_db

conn = get_db()
total_capital = get_total_capital(conn)
conn.close()

# Display as a card same as Cash/Bank cards
capital_card = self._make_card("Total Capital", total_capital, "#8e44ad")
```

---

## How Contributions / Withdrawals Work

| Action | Effect on Books |
|---|---|
| Contribution (Cash) | Investor capital UP, Cash balance UP |
| Contribution (Bank) | Investor capital UP, Bank account balance UP |
| Withdrawal (Cash) | Investor capital DOWN, Cash balance DOWN |
| Withdrawal (Bank) | Investor capital DOWN, Bank account balance DOWN |

Voucher numbers: CA-0001, CA-0002 etc. (stored in settings as last_ca_number)

---

## New DB Tables Added

### capital_accounts
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| name | TEXT | Title Case |
| contact | TEXT | Optional |
| opening_balance | REAL | Fixed at creation |
| created_date | TEXT | ISO date |

### capital_transactions
| Column | Type | Notes |
|---|---|---|
| id | INTEGER PK | |
| ca_number | TEXT UNIQUE | CA-XXXX |
| capital_account_id | INTEGER FK | → capital_accounts |
| date | TEXT | ISO date |
| amount | REAL | Always positive |
| type | TEXT | contribution / withdrawal / opening / adjustment |
| payment_method | TEXT | cash / bank / NULL (for adjustments) |
| bank_account_id | INTEGER FK | → bank_accounts (if bank) |
| notes | TEXT | Optional |

---

## Notes

- Removing an investor is only allowed if their balance = 0
- Opening balance cannot be changed after creation (use an adjustment transaction instead)
- The Opening Stock adjustment is safe to run — it only touches the supplier's opening_balance
  field and adds capital_transactions rows. No stock_items are touched.
- Year End closing: carry forward capital_accounts and their balances (like suppliers/customers)
