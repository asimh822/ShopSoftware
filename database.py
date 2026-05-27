import hashlib
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "united_mobile.db")

# Increment this whenever a new _migrate_vN function is added below.
CURRENT_DB_VERSION = 4


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS brands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand_id INTEGER REFERENCES brands(id),
            name TEXT NOT NULL,
            reference_price REAL
        );

        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            contact TEXT,
            opening_balance REAL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            contact TEXT,
            type TEXT CHECK(type IN ('credit', 'cash')),
            opening_balance REAL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS purchase_vouchers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pv_number TEXT UNIQUE NOT NULL,
            supplier_id INTEGER REFERENCES suppliers(id),
            date TEXT NOT NULL,
            total_amount REAL,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS purchase_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pv_id INTEGER REFERENCES purchase_vouchers(id),
            model_id INTEGER REFERENCES models(id),
            imei TEXT NOT NULL,
            purchase_price REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS stock_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id INTEGER REFERENCES models(id),
            imei TEXT UNIQUE NOT NULL,
            purchase_line_id INTEGER REFERENCES purchase_lines(id),
            purchase_price REAL NOT NULL,
            status TEXT CHECK(status IN ('in_stock', 'sold', 'returned')) DEFAULT 'in_stock',
            sold_line_id INTEGER REFERENCES sale_lines(id)
        );

        CREATE TABLE IF NOT EXISTS sale_vouchers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sv_number TEXT UNIQUE NOT NULL,
            type TEXT CHECK(type IN ('credit', 'cash')),
            customer_id INTEGER REFERENCES customers(id),
            cash_customer_name TEXT,
            cash_customer_contact TEXT,
            date TEXT NOT NULL,
            total_amount REAL,
            discount REAL DEFAULT 0,
            note TEXT,
            whatsapp_sent INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS sale_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sv_id INTEGER REFERENCES sale_vouchers(id),
            stock_item_id INTEGER REFERENCES stock_items(id),
            model_id INTEGER REFERENCES models(id),
            imei TEXT NOT NULL,
            reference_price REAL,
            discount REAL DEFAULT 0,
            final_price REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            voucher_number TEXT UNIQUE NOT NULL,
            party_type TEXT CHECK(party_type IN ('supplier', 'customer')),
            party_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            amount REAL NOT NULL,
            type TEXT CHECK(type IN ('CP', 'CR')),
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS journal_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            jv_number TEXT UNIQUE NOT NULL,
            party_type TEXT CHECK(party_type IN ('supplier', 'customer')),
            party_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            amount REAL NOT NULL,
            type TEXT CHECK(type IN ('debit', 'credit')),
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS bank_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            opening_balance REAL DEFAULT 0
        );
    """)

    _seed_settings(c)
    _run_migrations(conn)
    conn.commit()
    conn.close()


def _seed_settings(c):
    import datetime as _dt
    _yr = _dt.date.today().year
    defaults = {
        "pin_hash": hashlib.sha256(b"119211").hexdigest(),
        "shop_name": "United Mobile",
        "shop_address": "Shop 1-2, Rehma Commercial Center, Kutchery Road, Multan",
        "shop_contact": "0323-9637000",
        "whatsapp_template": (
            "Assalam o Alaikum {customer_name}, thank you for purchasing "
            "{model_name} from United Mobile Multan. IMEI: {imei}. "
            "For any queries please call 0323-9637000."
        ),
        "receipt_footer": "Thank you for your purchase!",
        "last_pv_number": "0",
        "last_sv_number": "0",
        "last_cp_number": "0",
        "last_cr_number": "0",
        "last_jv_number": "0",
        "last_sr_number": "0",
        "last_pr_number": "0",
        "bank_account_name": "",
        "bank_account_balance": "0",
        # Year End Closing
        "year_start_date": f"01/01/{_yr}",
        "year_end_date":   f"31/12/{_yr}",
        "cash_opening_balance": "0",
        # Auto Monthly Backup
        "last_auto_backup_month": "",
    }
    for key, value in defaults.items():
        c.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )


# ── Versioned migration system ────────────────────────────────────────────────

def _get_db_version(conn) -> int:
    """Read db_version from the settings table. Returns 0 if never set."""
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key='db_version'"
        ).fetchone()
        return int(row[0]) if row and row[0] else 0
    except Exception:
        return 0


def _run_migrations(conn) -> None:
    """
    Run every pending migration in version order.

    How it works:
    • Each migration is a function _migrate_vN(conn) that only adds/alters
      things — it never drops or truncates.
    • After a successful migration, db_version is updated and committed
      atomically with the migration changes.
    • On next startup the already-applied versions are skipped instantly.
    • Prints progress + final "Database is up to date — version N" line.

    To add a future migration:
    1. Write  def _migrate_v2(conn): ...  below
    2. Add it to the `_MIGRATIONS` dict: {2: _migrate_v2}
    3. Bump CURRENT_DB_VERSION to 2 at the top of this file.
    """
    # Register every migration here — key = target version number
    _MIGRATIONS: dict[int, callable] = {
        1: _migrate_v1,
        2: _migrate_v2,
        3: _migrate_v3,
        4: _migrate_v4,
    }

    current = _get_db_version(conn)

    for version in sorted(_MIGRATIONS.keys()):
        if version <= current:
            continue                        # already applied — skip
        print(f"Database: applying migration to version {version}...")
        _MIGRATIONS[version](conn)
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('db_version', ?)",
            (str(version),),
        )
        conn.commit()
        current = version

    print(f"Database is up to date - version {current}")


def _migrate_v1(conn) -> None:
    """
    Version 1 migrations — all additions made during initial development.
    Every operation is idempotent (IF NOT EXISTS / try-except on ALTER TABLE).
    Do NOT add a conn.commit() here — _run_migrations() commits per version.
    """
    c = conn.cursor()

    # ── sale_vouchers: payment method tracking columns ───────────────────────
    for col_name, col_def in [
        ("payment_method", "TEXT DEFAULT 'cash'"),
        ("cash_paid",      "REAL DEFAULT 0"),
        ("bank_account_id","INTEGER"),
        ("bank_amount",    "REAL DEFAULT 0"),
        ("bank_ref",       "TEXT"),
    ]:
        try:
            c.execute(f"ALTER TABLE sale_vouchers ADD COLUMN {col_name} {col_def}")
        except Exception:
            pass  # column already exists — safe to ignore

    # Backfill existing cash sales so the Cash in Hand figure doesn't change
    c.execute("""
        UPDATE sale_vouchers
        SET cash_paid = COALESCE(total_amount, 0)
        WHERE (payment_method IS NULL OR payment_method = 'cash')
          AND (cash_paid IS NULL OR cash_paid = 0)
          AND COALESCE(total_amount, 0) > 0
    """)

    # ── Migrate legacy single bank account (settings keys) → bank_accounts ──
    existing_count = c.execute("SELECT COUNT(*) FROM bank_accounts").fetchone()[0]
    if existing_count == 0:
        name_row = c.execute(
            "SELECT value FROM settings WHERE key='bank_account_name'"
        ).fetchone()
        bal_row = c.execute(
            "SELECT value FROM settings WHERE key='bank_account_balance'"
        ).fetchone()
        name_val = (name_row[0] if name_row else "") or ""
        bal_val = 0.0
        try:
            bal_val = float(bal_row[0]) if bal_row and bal_row[0] else 0.0
        except Exception:
            pass
        if name_val.strip():
            c.execute(
                "INSERT INTO bank_accounts (name, opening_balance) VALUES (?, ?)",
                (name_val.strip(), bal_val),
            )

    # ── sale_returns / sale_return_lines tables ───────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS sale_returns (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            sr_number  TEXT UNIQUE NOT NULL,
            sv_id      INTEGER REFERENCES sale_vouchers(id),
            date       TEXT NOT NULL,
            notes      TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS sale_return_lines (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            sr_id          INTEGER REFERENCES sale_returns(id),
            stock_item_id  INTEGER REFERENCES stock_items(id),
            model_id       INTEGER REFERENCES models(id),
            imei           TEXT NOT NULL,
            return_price   REAL NOT NULL
        )
    """)
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('last_sr_number', '0')")

    # ── sale_returns: add customer_id column ──────────────────────────────────
    try:
        c.execute(
            "ALTER TABLE sale_returns ADD COLUMN customer_id INTEGER REFERENCES customers(id)"
        )
    except Exception:
        pass  # already exists

    # ── purchase_returns / purchase_return_lines tables ───────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS purchase_returns (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            pr_number   TEXT UNIQUE NOT NULL,
            pv_id       INTEGER REFERENCES purchase_vouchers(id),
            supplier_id INTEGER REFERENCES suppliers(id),
            date        TEXT NOT NULL,
            notes       TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS purchase_return_lines (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            pr_id          INTEGER REFERENCES purchase_returns(id),
            stock_item_id  INTEGER REFERENCES stock_items(id),
            model_id       INTEGER REFERENCES models(id),
            imei           TEXT NOT NULL,
            return_price   REAL NOT NULL
        )
    """)
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('last_pr_number', '0')")

    # ── bank_transactions table ───────────────────────────────────────────────
    # CP = money INTO bank  (cash deposit or JV Dr Bank)
    # CR = money OUT of bank (cash withdrawal or JV Cr Bank)
    # source: 'cash_transfer' = actual cash movement, 'jv' = journal entry only
    c.execute("""
        CREATE TABLE IF NOT EXISTS bank_transactions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            voucher_number  TEXT UNIQUE NOT NULL,
            type            TEXT NOT NULL CHECK(type IN ('CP', 'CR')),
            bank_account_id INTEGER REFERENCES bank_accounts(id),
            source          TEXT NOT NULL DEFAULT 'cash_transfer',
            date            TEXT NOT NULL,
            amount          REAL NOT NULL,
            notes           TEXT
        )
    """)

    # ── Add source column to existing bank_transactions rows ─────────────────
    try:
        c.execute(
            "ALTER TABLE bank_transactions ADD COLUMN source TEXT NOT NULL DEFAULT 'cash_transfer'"
        )
    except Exception:
        pass  # already exists

    # ── cash_journal_lines — cash side of double-entry JV entries ─────────────
    # direction 'in'  = Dr Cash on JV → Cash in Hand ↑
    # direction 'out' = Cr Cash on JV → Cash in Hand ↓
    c.execute("""
        CREATE TABLE IF NOT EXISTS cash_journal_lines (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            jv_number  TEXT NOT NULL,
            date       TEXT NOT NULL,
            amount     REAL NOT NULL,
            direction  TEXT NOT NULL CHECK(direction IN ('in', 'out')),
            notes      TEXT
        )
    """)

    # ── salesmen table ───────────────────────────────────────────────────────────
    c.execute("""
        CREATE TABLE IF NOT EXISTS salesmen (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            pin          TEXT NOT NULL UNIQUE,
            active       INTEGER DEFAULT 1,
            created_date TEXT
        )
    """)

    # ── sale_vouchers: salesman_id column ─────────────────────────────────────
    try:
        c.execute(
            "ALTER TABLE sale_vouchers ADD COLUMN salesman_id INTEGER REFERENCES salesmen(id)"
        )
    except Exception:
        pass  # already exists

    # ── Data repair: stock_items where sold_line_id was never written ──────────
    # Older versions of db_save_sale() inserted sale_lines but did not update
    # stock_items.  Find every stock_item that has a sale_lines row but still
    # has sold_line_id=NULL and status='in_stock', and repair it atomically.
    c.execute("""
        UPDATE stock_items
        SET status      = 'sold',
            sold_line_id = (
                SELECT sl.id
                FROM   sale_lines sl
                WHERE  sl.stock_item_id = stock_items.id
                ORDER  BY sl.id
                LIMIT  1
            )
        WHERE sold_line_id IS NULL
          AND status = 'in_stock'
          AND EXISTS (
                SELECT 1 FROM sale_lines sl
                WHERE sl.stock_item_id = stock_items.id
          )
    """)
    # _run_migrations() commits after this function returns.


def _migrate_v2(conn) -> None:
    """
    Version 2 — Cash Purchase support.
    1. Adds columns to purchase_vouchers for buying from walk-in sellers.
    2. Inserts the system 'Cash Purchase' supplier with id=0 — this record is
       used as supplier_id for all cash purchases instead of NULL, so every
       purchase_voucher always has a valid supplier_id.  id=0 is filtered out
       of every user-facing supplier dropdown and ledger list.
    Do NOT add a conn.commit() here — _run_migrations() commits per version.
    """
    c = conn.cursor()
    for col_name, col_def in [
        ("purchase_type",   "TEXT DEFAULT 'supplier'"),
        ("egadget_ref",     "TEXT"),
        ("payment_method",  "TEXT"),
        ("cash_amount",     "REAL DEFAULT 0"),
        ("bank_amount",     "REAL DEFAULT 0"),
        ("bank_account_id", "INTEGER"),
        ("bank_ref",        "TEXT"),
    ]:
        try:
            c.execute(
                f"ALTER TABLE purchase_vouchers ADD COLUMN {col_name} {col_def}"
            )
        except Exception:
            pass  # column already exists — safe to ignore

    # NOTE: id=0 supplier INSERT was moved to _migrate_v3 so it runs as a
    # separate idempotent migration step on databases that already completed v2.


def _migrate_v3(conn) -> None:
    """
    Version 3 — Insert system 'Cash Purchase' supplier (id=0).
    Uses INSERT OR IGNORE so re-running is always safe.
    id=0 is excluded from every user-facing supplier dropdown and ledger query;
    it exists purely so that purchase_vouchers.supplier_id is never NULL.
    Do NOT add a conn.commit() here — _run_migrations() commits per version.
    """
    conn.execute("""
        INSERT OR IGNORE INTO suppliers (id, name, contact, opening_balance)
        VALUES (0, 'Cash Purchase', '', 0)
    """)


def _migrate_v4(conn) -> None:
    """
    Version 4 — Expenses module.
    Creates the expenses table and seeds the EXP number counter.
    Do NOT add a conn.commit() here — _run_migrations() commits per version.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            expense_number  TEXT UNIQUE NOT NULL,
            date            TEXT NOT NULL,
            category        TEXT NOT NULL,
            description     TEXT,
            amount          REAL NOT NULL,
            payment_method  TEXT CHECK(payment_method IN ('cash', 'bank')),
            bank_account_id INTEGER REFERENCES bank_accounts(id),
            bank_ref        TEXT
        )
    """)
    conn.execute(
        "INSERT OR IGNORE INTO settings (key, value) VALUES ('last_exp_number', '0')"
    )


# ── Expense helpers ───────────────────────────────────────────────────────────

EXPENSE_CATEGORIES = [
    "Rent",
    "Salaries",
    "Electricity",
    "Internet",
    "Travel",
    "Miscellaneous",
]


def db_save_expense(date_str: str, category: str, description: str,
                    amount: float, payment_method: str,
                    bank_account_id=None, bank_ref: str = "",
                    expense_id=None) -> dict:
    """
    Insert a new expense or update an existing one.
    On insert: auto-generates EXP-XXXX number, adjusts cash/bank balance.
    On update: reverses the old balance effect, applies the new one.
    Returns {'ok': True, 'expense_number': '...'} or {'ok': False, 'error': '...'}.
    """
    conn = get_connection()
    try:
        c = conn.cursor()

        if expense_id:
            # ── Edit mode — fetch old record to reverse its balance effect ────
            old = c.execute(
                "SELECT payment_method, bank_account_id, amount FROM expenses WHERE id=?",
                (expense_id,)
            ).fetchone()
            if not old:
                conn.close()
                return {'ok': False, 'error': 'Expense not found.'}

            # Reverse old bank transaction if it was a bank expense
            if old['payment_method'] == 'bank' and old['bank_account_id']:
                # Old entry was CR (bank ↓); to reverse, delete that bank_transaction row
                c.execute(
                    "DELETE FROM bank_transactions WHERE voucher_number=("
                    "  SELECT expense_number FROM expenses WHERE id=?)",
                    (expense_id,)
                )

            # Update the expense record
            c.execute("""
                UPDATE expenses
                SET date=?, category=?, description=?, amount=?,
                    payment_method=?, bank_account_id=?, bank_ref=?
                WHERE id=?
            """, (date_str, category, description or '', amount,
                  payment_method, bank_account_id, bank_ref or '', expense_id))

            # Fetch updated expense_number for bank re-entry
            exp_num = c.execute(
                "SELECT expense_number FROM expenses WHERE id=?", (expense_id,)
            ).fetchone()[0]

        else:
            # ── Insert mode — generate EXP number ────────────────────────────
            row = c.execute(
                "SELECT value FROM settings WHERE key='last_exp_number'"
            ).fetchone()
            n = int(row['value']) + 1 if row else 1
            c.execute(
                "UPDATE settings SET value=? WHERE key='last_exp_number'", (str(n),)
            )
            exp_num = f"EXP-{n:04d}"
            c.execute("""
                INSERT INTO expenses
                (expense_number, date, category, description, amount,
                 payment_method, bank_account_id, bank_ref)
                VALUES (?,?,?,?,?,?,?,?)
            """, (exp_num, date_str, category, description or '', amount,
                  payment_method, bank_account_id, bank_ref or ''))

        # ── Record bank outflow for bank expenses ─────────────────────────────
        # Uses expense_number as the voucher_number for traceability.
        # CR = money OUT of bank (expense paid from bank).
        if payment_method == 'bank' and bank_account_id:
            c.execute("""
                INSERT OR REPLACE INTO bank_transactions
                (voucher_number, type, bank_account_id, source, date, amount, notes)
                VALUES (?,?,?,?,?,?,?)
            """, (exp_num, 'CR', bank_account_id, 'expense',
                  date_str, amount,
                  f"Expense — {category}" + (f" ({description})" if description else '')))

        conn.commit()
        return {'ok': True, 'expense_number': exp_num}
    except Exception as e:
        conn.rollback()
        return {'ok': False, 'error': str(e)}
    finally:
        conn.close()


def db_delete_expense(expense_id: int) -> dict:
    """
    Delete an expense and reverse its balance effect.
    Returns {'ok': True} or {'ok': False, 'error': '...'}.
    """
    conn = get_connection()
    try:
        c = conn.cursor()
        row = c.execute(
            "SELECT expense_number, payment_method, bank_account_id FROM expenses WHERE id=?",
            (expense_id,)
        ).fetchone()
        if not row:
            conn.close()
            return {'ok': False, 'error': 'Expense not found.'}

        # Remove bank_transaction record if it was a bank expense
        if row['payment_method'] == 'bank' and row['bank_account_id']:
            c.execute(
                "DELETE FROM bank_transactions WHERE voucher_number=?",
                (row['expense_number'],)
            )

        c.execute("DELETE FROM expenses WHERE id=?", (expense_id,))
        conn.commit()
        return {'ok': True}
    except Exception as e:
        conn.rollback()
        return {'ok': False, 'error': str(e)}
    finally:
        conn.close()


def db_expenses(date_from: str = '', date_to: str = '',
                category: str = '', search: str = '') -> list:
    """
    Fetch expenses with optional filters.
    date_from / date_to: DD/MM/YYYY strings (empty = no bound).
    Returns list of dicts.
    """
    conn = get_connection()

    # Convert DD/MM/YYYY → YYYY-MM-DD for ISO comparison
    def _to_iso(ddmmyyyy: str) -> str:
        try:
            d, m, y = ddmmyyyy.strip().split('/')
            return f"{y}-{m}-{d}"
        except Exception:
            return ''

    def _date_expr(col: str) -> str:
        return (f"substr({col},7,4)||'-'||substr({col},4,2)||'-'||substr({col},1,2)")

    where = []
    params = []

    if date_from:
        iso = _to_iso(date_from)
        if iso:
            where.append(f"{_date_expr('date')} >= ?")
            params.append(iso)
    if date_to:
        iso = _to_iso(date_to)
        if iso:
            where.append(f"{_date_expr('date')} <= ?")
            params.append(iso)
    if category:
        where.append("category = ?")
        params.append(category)
    if search:
        where.append("description LIKE ?")
        params.append(f"%{search}%")

    sql = "SELECT e.*, ba.name AS bank_name FROM expenses e LEFT JOIN bank_accounts ba ON ba.id=e.bank_account_id"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY " + _date_expr('e.date') + " DESC, e.id DESC"

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def db_expense_by_id(expense_id: int) -> dict | None:
    """Fetch a single expense record by id."""
    conn = get_connection()
    row = conn.execute(
        "SELECT e.*, ba.name AS bank_name FROM expenses e "
        "LEFT JOIN bank_accounts ba ON ba.id=e.bank_account_id "
        "WHERE e.id=?",
        (expense_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def next_voucher_number(prefix: str, counter_key: str) -> str:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = ?", (counter_key,))
    row = c.fetchone()
    next_num = int(row["value"]) + 1 if row else 1
    c.execute(
        "UPDATE settings SET value = ? WHERE key = ?",
        (str(next_num), counter_key),
    )
    conn.commit()
    conn.close()
    return f"{prefix}-{next_num:04d}"


def get_setting(key: str) -> str | None:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = c.fetchone()
    conn.close()
    return row["value"] if row else None


def set_setting(key: str, value: str):
    conn = get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, value),
    )
    conn.commit()
    conn.close()


def _hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode()).hexdigest()


def check_pin(entered: str) -> bool:
    stored = get_setting("pin_hash")
    return stored is not None and _hash_pin(entered) == stored


def set_pin(new_pin: str):
    set_setting("pin_hash", _hash_pin(new_pin))


# ── Bank account helpers ──────────────────────────────────────────────────────

def db_bank_accounts():
    """Return all bank accounts as a list of plain dicts, ordered by name."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name, opening_balance FROM bank_accounts ORDER BY name"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def db_save_bank_account(name: str, opening_balance: float,
                          account_id: int | None = None):
    """Insert a new bank account or update an existing one."""
    conn = get_connection()
    if account_id:
        conn.execute(
            "UPDATE bank_accounts SET name=?, opening_balance=? WHERE id=?",
            (name, opening_balance, account_id),
        )
    else:
        conn.execute(
            "INSERT INTO bank_accounts (name, opening_balance) VALUES (?, ?)",
            (name, opening_balance),
        )
    conn.commit()
    conn.close()


def db_delete_bank_account(account_id: int) -> bool:
    """Delete a bank account. Returns False if it is referenced by any sale voucher."""
    conn = get_connection()
    used = conn.execute(
        "SELECT COUNT(*) FROM sale_vouchers WHERE bank_account_id=?",
        (account_id,)
    ).fetchone()[0]
    if used:
        conn.close()
        return False
    conn.execute("DELETE FROM bank_accounts WHERE id=?", (account_id,))
    conn.commit()
    conn.close()
    return True


def db_bank_total_balance() -> float:
    """
    Total bank balance:
      opening balances
    + bank portion of sales (bank_amount on sale_vouchers)
    + CP bank transactions  (cash deposited into bank)
    - CR bank transactions  (cash withdrawn from bank)
    """
    conn = get_connection()
    result = conn.execute("""
        SELECT
            COALESCE((SELECT SUM(opening_balance) FROM bank_accounts), 0)
            + COALESCE((SELECT SUM(bank_amount) FROM sale_vouchers
                        WHERE bank_account_id IS NOT NULL AND bank_amount > 0), 0)
            + COALESCE((SELECT SUM(amount) FROM bank_transactions WHERE type='CP'), 0)
            - COALESCE((SELECT SUM(amount) FROM bank_transactions WHERE type='CR'), 0)
    """).fetchone()[0]
    conn.close()
    return float(result or 0.0)


# ── Cash / Bank transaction helpers ──────────────────────────────────────────

def db_save_bank_cp_cr(tx_type: str, bank_account_id: int,
                        date_str: str, amount: float, notes: str) -> str:
    """
    Standalone cash↔bank transfer voucher.
      CP: cash deposit    → Cash in Hand ↓, Bank ↑
      CR: cash withdrawal → Bank ↓, Cash in Hand ↑
    Auto-generates a CP-XXXX or CR-XXXX voucher number.
    """
    counter_key = "last_cp_number" if tx_type == "CP" else "last_cr_number"
    conn = get_connection()
    try:
        c = conn.cursor()
        row = c.execute("SELECT value FROM settings WHERE key=?", (counter_key,)).fetchone()
        n = int(row["value"]) + 1 if row else 1
        c.execute("UPDATE settings SET value=? WHERE key=?", (str(n), counter_key))
        voucher_number = f"{tx_type}-{n:04d}"
        c.execute(
            "INSERT INTO bank_transactions "
            "(voucher_number, type, bank_account_id, source, date, amount, notes) "
            "VALUES (?,?,?,?,?,?,?)",
            (voucher_number, tx_type, bank_account_id, "cash_transfer",
             date_str, amount, notes or ""),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()
    return voucher_number


def _jv_side(c, jv_number: str, date_str: str, notes: str,
             acct_type: str, acct_id, amount: float, is_debit: bool):
    """Insert one side of a double-entry JV into the appropriate table."""
    if acct_type == "supplier":
        # Dr Supplier → credit entry (liability ↓)
        # Cr Supplier → debit entry  (liability ↑)
        jt = "credit" if is_debit else "debit"
        c.execute(
            "INSERT INTO journal_entries "
            "(jv_number, party_type, party_id, date, amount, type, notes) "
            "VALUES (?,?,?,?,?,?,?)",
            (jv_number, "supplier", acct_id, date_str, amount, jt, notes),
        )
    elif acct_type == "customer":
        # Dr Customer → debit entry  (receivable ↑ — unusual)
        # Cr Customer → credit entry (receivable ↓ — customer pays)
        jt = "debit" if is_debit else "credit"
        c.execute(
            "INSERT INTO journal_entries "
            "(jv_number, party_type, party_id, date, amount, type, notes) "
            "VALUES (?,?,?,?,?,?,?)",
            (jv_number, "customer", acct_id, date_str, amount, jt, notes),
        )
    elif acct_type == "bank":
        # Dr Bank → CP (bank ↑)
        # Cr Bank → CR (bank ↓)
        bt = "CP" if is_debit else "CR"
        c.execute(
            "INSERT INTO bank_transactions "
            "(voucher_number, type, bank_account_id, source, date, amount, notes) "
            "VALUES (?,?,?,?,?,?,?)",
            (jv_number, bt, acct_id, "jv", date_str, amount, notes),
        )
    elif acct_type == "cash":
        direction = "in" if is_debit else "out"
        c.execute(
            "INSERT INTO cash_journal_lines (jv_number, date, amount, direction, notes) "
            "VALUES (?,?,?,?,?)",
            (jv_number, date_str, amount, direction, notes),
        )


def db_save_double_entry_jv(date_str: str, notes: str,
                              dr_type: str, dr_id,
                              cr_type: str, cr_id,
                              amount: float) -> str:
    """
    Save a double-entry Journal Voucher. Both sides recorded atomically.
    acct_type: 'supplier' | 'customer' | 'bank' | 'cash'
    Returns the JV number.
    """
    conn = get_connection()
    try:
        c = conn.cursor()
        row = c.execute(
            "SELECT value FROM settings WHERE key='last_jv_number'"
        ).fetchone()
        n = int(row["value"]) + 1 if row else 1
        c.execute("UPDATE settings SET value=? WHERE key='last_jv_number'", (str(n),))
        jv_number = f"JV-{n:04d}"
        _jv_side(c, jv_number, date_str, notes, dr_type, dr_id, amount, is_debit=True)
        _jv_side(c, jv_number, date_str, notes, cr_type, cr_id, amount, is_debit=False)
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()
    return jv_number


def db_cash_in_hand() -> float:
    """
    Running cash in hand — the definitive formula used everywhere:
      + cash_opening_balance  (carried forward from year-end close; 0 on first year)
      + cash_paid on sales (cash portion of sale payments)
      + CR payments (cash received from customers / supplier refunds)
      - CP payments (cash paid to suppliers / customer refunds)
      - bank_transactions CP where source='cash_transfer'  (cash deposited into bank)
      + bank_transactions CR where source='cash_transfer'  (cash withdrawn from bank)
      + cash_journal_lines direction='in'   (Dr Cash in JV)
      - cash_journal_lines direction='out'  (Cr Cash in JV)
    """
    conn = get_connection()
    ob_row = conn.execute(
        "SELECT value FROM settings WHERE key='cash_opening_balance'"
    ).fetchone()
    cash_ob = float(ob_row[0]) if ob_row and ob_row[0] else 0.0
    result = conn.execute("""
        SELECT
            COALESCE((SELECT SUM(cash_paid) FROM sale_vouchers WHERE cash_paid > 0), 0)
            + COALESCE((SELECT SUM(amount) FROM payments WHERE type='CR'), 0)
            - COALESCE((SELECT SUM(amount) FROM payments WHERE type='CP'), 0)
            - COALESCE((SELECT SUM(amount) FROM bank_transactions
                        WHERE type='CP' AND source='cash_transfer'), 0)
            + COALESCE((SELECT SUM(amount) FROM bank_transactions
                        WHERE type='CR' AND source='cash_transfer'), 0)
            + COALESCE((SELECT SUM(amount) FROM cash_journal_lines WHERE direction='in'), 0)
            - COALESCE((SELECT SUM(amount) FROM cash_journal_lines WHERE direction='out'), 0)
            - COALESCE((SELECT SUM(cash_amount) FROM purchase_vouchers
                        WHERE purchase_type='cash' AND cash_amount > 0), 0)
            - COALESCE((SELECT SUM(amount) FROM expenses
                        WHERE payment_method='cash'), 0)
    """).fetchone()[0]
    conn.close()
    return cash_ob + float(result or 0.0)


# ── Year End Closing helpers ──────────────────────────────────────────────────

def _party_closing_balance(conn, party_type: str, party_id: int) -> float:
    """
    Compute the running ledger balance for a supplier or customer using the
    same DR/CR logic as ledger.py — without importing it (avoids circular import).
    """
    table = "suppliers" if party_type == "supplier" else "customers"
    ob_row = conn.execute(
        f"SELECT opening_balance FROM {table} WHERE id=?", (party_id,)
    ).fetchone()
    ob = float(ob_row["opening_balance"] or 0) if ob_row else 0.0

    if party_type == "supplier":
        # Purchases → DR (increases what you owe)
        dr = conn.execute(
            "SELECT COALESCE(SUM(total_amount), 0) FROM purchase_vouchers WHERE supplier_id=?",
            (party_id,)
        ).fetchone()[0]
        # CP → CR (reduces what you owe); CR → DR (supplier refund, unusual)
        cp = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM payments "
            "WHERE party_type='supplier' AND party_id=? AND type='CP'",
            (party_id,)
        ).fetchone()[0]
        cr = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM payments "
            "WHERE party_type='supplier' AND party_id=? AND type='CR'",
            (party_id,)
        ).fetchone()[0]
        jv_dr = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM journal_entries "
            "WHERE party_type='supplier' AND party_id=? AND type='debit'",
            (party_id,)
        ).fetchone()[0]
        jv_cr = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM journal_entries "
            "WHERE party_type='supplier' AND party_id=? AND type='credit'",
            (party_id,)
        ).fetchone()[0]
        return ob + float(dr) + float(cr) - float(cp) + float(jv_dr) - float(jv_cr)

    else:  # customer
        # Credit sales → DR (customer owes more)
        sales = conn.execute(
            "SELECT COALESCE(SUM(total_amount), 0) FROM sale_vouchers "
            "WHERE customer_id=? AND type='credit'",
            (party_id,)
        ).fetchone()[0]
        # CR → CR (customer pays, reduces balance); CP → DR (refund, increases balance)
        cr = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM payments "
            "WHERE party_type='customer' AND party_id=? AND type='CR'",
            (party_id,)
        ).fetchone()[0]
        cp = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM payments "
            "WHERE party_type='customer' AND party_id=? AND type='CP'",
            (party_id,)
        ).fetchone()[0]
        jv_dr = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM journal_entries "
            "WHERE party_type='customer' AND party_id=? AND type='debit'",
            (party_id,)
        ).fetchone()[0]
        jv_cr = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM journal_entries "
            "WHERE party_type='customer' AND party_id=? AND type='credit'",
            (party_id,)
        ).fetchone()[0]
        return ob + float(sales) + float(cp) - float(cr) + float(jv_dr) - float(jv_cr)


def db_bank_account_closing_balance(account_id: int) -> float:
    """Compute the current balance for a single bank account."""
    conn = get_connection()
    ba = conn.execute(
        "SELECT opening_balance FROM bank_accounts WHERE id=?", (account_id,)
    ).fetchone()
    ob = float(ba["opening_balance"] or 0) if ba else 0.0
    sales = conn.execute(
        "SELECT COALESCE(SUM(bank_amount), 0) FROM sale_vouchers "
        "WHERE bank_account_id=? AND bank_amount > 0",
        (account_id,)
    ).fetchone()[0]
    cp = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM bank_transactions "
        "WHERE bank_account_id=? AND type='CP'",
        (account_id,)
    ).fetchone()[0]
    cr = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM bank_transactions "
        "WHERE bank_account_id=? AND type='CR'",
        (account_id,)
    ).fetchone()[0]
    conn.close()
    return ob + float(sales) + float(cp) - float(cr)


def db_year_end_summary(year_start_iso: str, year_end_iso: str) -> dict:
    """
    Return all data needed for the Year End Closing summary dialog.
    year_start_iso / year_end_iso: 'YYYY-MM-DD'
    """
    def _de(col):
        return (
            f"substr({col},7,4)||'-'||substr({col},4,2)||'-'||substr({col},1,2)"
        )

    conn = get_connection()

    # Sales total for the year
    de_sv = _de("date")
    total_sales = conn.execute(
        f"SELECT COALESCE(SUM(total_amount),0) FROM sale_vouchers "
        f"WHERE {de_sv} >= ? AND {de_sv} <= ?",
        (year_start_iso, year_end_iso)
    ).fetchone()[0]

    # Purchases total for the year
    de_pv = _de("date")
    total_purchases = conn.execute(
        f"SELECT COALESCE(SUM(total_amount),0) FROM purchase_vouchers "
        f"WHERE {de_pv} >= ? AND {de_pv} <= ?",
        (year_start_iso, year_end_iso)
    ).fetchone()[0]

    # Units in stock
    stock_units = conn.execute(
        "SELECT COUNT(*) FROM stock_items WHERE status='in_stock'"
    ).fetchone()[0]

    suppliers = conn.execute(
        "SELECT id, name FROM suppliers WHERE id != 0 ORDER BY name"
    ).fetchall()
    customers = conn.execute(
        "SELECT id, name FROM customers WHERE type='credit' ORDER BY name"
    ).fetchall()
    bank_accounts = conn.execute(
        "SELECT id, name FROM bank_accounts ORDER BY name"
    ).fetchall()
    conn.close()

    supplier_balances = [
        {"name": s["name"],
         "balance": _party_closing_balance(get_connection(), "supplier", s["id"])}
        for s in suppliers
    ]
    # Close each temp connection used above properly — use a single conn instead
    conn2 = get_connection()
    supplier_balances = [
        {"name": s["name"],
         "balance": _party_closing_balance(conn2, "supplier", s["id"])}
        for s in suppliers
    ]
    customer_balances = [
        {"name": c["name"],
         "balance": _party_closing_balance(conn2, "customer", c["id"])}
        for c in customers
    ]
    conn2.close()

    bank_balances = [
        {"id": ba["id"], "name": ba["name"],
         "balance": db_bank_account_closing_balance(ba["id"])}
        for ba in bank_accounts
    ]

    return {
        "total_sales":        float(total_sales or 0),
        "total_purchases":    float(total_purchases or 0),
        "cash_in_hand":       db_cash_in_hand(),
        "stock_units":        int(stock_units or 0),
        "supplier_balances":  supplier_balances,
        "customer_balances":  customer_balances,
        "bank_balances":      bank_balances,
    }


def db_perform_year_end_close(archive_path: str):
    """
    Full Year End Closing procedure (atomic):
      1. Copy current DB to archive_path (full backup for auditing)
      2. Carry forward supplier/customer/bank/cash closing balances as new opening balances
      3. Clear all transaction tables in correct FK order
      4. Keep only in_stock items (prior-year sold/returned items are removed)
      5. Reset all voucher number sequences to 0
    """
    import shutil

    # ── 1. Archive ───────────────────────────────────────────────────────────
    shutil.copy2(DB_PATH, archive_path)

    conn = get_connection()
    c = conn.cursor()
    try:
        # ── 2a. Carry forward supplier balances ──────────────────────────────
        # id=0 is the system 'Cash Purchase' supplier — no balance to carry.
        suppliers = c.execute("SELECT id FROM suppliers WHERE id != 0").fetchall()
        for sup in suppliers:
            bal = _party_closing_balance(conn, "supplier", sup["id"])
            c.execute(
                "UPDATE suppliers SET opening_balance=? WHERE id=?",
                (round(bal, 2), sup["id"])
            )

        # ── 2b. Carry forward customer balances ──────────────────────────────
        customers = c.execute(
            "SELECT id FROM customers WHERE type='credit'"
        ).fetchall()
        for cust in customers:
            bal = _party_closing_balance(conn, "customer", cust["id"])
            c.execute(
                "UPDATE customers SET opening_balance=? WHERE id=?",
                (round(bal, 2), cust["id"])
            )

        # ── 2c. Carry forward bank account balances ──────────────────────────
        bank_accounts = c.execute("SELECT id FROM bank_accounts").fetchall()
        for ba in bank_accounts:
            bal = db_bank_account_closing_balance(ba["id"])
            c.execute(
                "UPDATE bank_accounts SET opening_balance=? WHERE id=?",
                (round(bal, 2), ba["id"])
            )

        # ── 2d. Carry forward cash in hand ───────────────────────────────────
        cash_bal = db_cash_in_hand()
        c.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('cash_opening_balance', ?)",
            (str(round(cash_bal, 2)),)
        )

        # ── 3. Clear FK back-references before deleting parent rows ──────────
        c.execute("UPDATE stock_items SET sold_line_id    = NULL")
        c.execute("UPDATE stock_items SET purchase_line_id = NULL")

        # ── 4. Delete transactions in safe dependency order ──────────────────
        for tbl in [
            "sale_return_lines", "sale_returns",
            "purchase_return_lines", "purchase_returns",
            "sale_lines", "sale_vouchers",
            "purchase_lines", "purchase_vouchers",
            "payments", "journal_entries",
            "bank_transactions", "cash_journal_lines",
            "expenses",
        ]:
            c.execute(f"DELETE FROM {tbl}")

        # ── 5. Remove sold/returned stock items (their vouchers are gone) ─────
        c.execute("DELETE FROM stock_items WHERE status != 'in_stock'")

        # ── 6. Reset voucher sequences ───────────────────────────────────────
        for key in [
            "last_pv_number", "last_sv_number",
            "last_cp_number", "last_cr_number",
            "last_jv_number", "last_sr_number", "last_pr_number",
            "last_exp_number",
        ]:
            c.execute("UPDATE settings SET value='0' WHERE key=?", (key,))

        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise

    conn.close()


# ── Auto Monthly Backup ───────────────────────────────────────────────────────

def db_auto_backup_if_needed() -> str | None:
    """
    Call once at startup (in a background thread).
    If the current calendar month has no backup yet:
      - Creates a 'backups' sub-folder next to the DB (if absent)
      - Copies the DB there as UnitedMobile_Backup_MMYYYY.db
      - Records the month in settings so it won't repeat this month
      - Returns the full path of the new backup file
    Returns None if a backup for this month already exists.
    """
    import datetime as _dt
    import shutil

    today = _dt.date.today()
    month_key = today.strftime("%m%Y")          # e.g. "052026"

    last = get_setting("last_auto_backup_month") or ""
    if last == month_key:
        return None                             # already done this month

    backups_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backups")
    os.makedirs(backups_dir, exist_ok=True)

    backup_name = f"UnitedMobile_Backup_{month_key}.db"
    backup_path = os.path.join(backups_dir, backup_name)

    shutil.copy2(DB_PATH, backup_path)
    set_setting("last_auto_backup_month", month_key)
    return backup_path


# ── Salesman helpers ──────────────────────────────────────────────────────────

def db_salesmen():
    """All salesmen (active and inactive), ordered by name."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name, pin, active, created_date FROM salesmen ORDER BY name"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def db_active_salesmen():
    """Active salesmen only — for dropdowns on the sale form."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name FROM salesmen WHERE active=1 ORDER BY name"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def db_save_salesman(name: str, pin: str, salesman_id=None):
    """
    Insert or update a salesman.
    PIN must be exactly 4 digits and unique across all salesmen.
    Returns None on success, or an error-message string on failure.
    """
    import datetime as _dt
    conn = get_connection()
    try:
        if salesman_id:
            dup = conn.execute(
                "SELECT id FROM salesmen WHERE pin=? AND id!=?", (pin, salesman_id)
            ).fetchone()
            if dup:
                return "This PIN is already assigned to another salesman."
            conn.execute(
                "UPDATE salesmen SET name=?, pin=? WHERE id=?", (name, pin, salesman_id)
            )
        else:
            dup = conn.execute("SELECT id FROM salesmen WHERE pin=?", (pin,)).fetchone()
            if dup:
                return "This PIN is already assigned to another salesman."
            today = _dt.date.today().strftime("%d/%m/%Y")
            conn.execute(
                "INSERT INTO salesmen (name, pin, active, created_date) VALUES (?,?,1,?)",
                (name, pin, today),
            )
        conn.commit()
        return None
    except Exception as e:
        conn.rollback()
        return str(e)
    finally:
        conn.close()


def db_toggle_salesman(salesman_id: int):
    """Toggle a salesman's active / inactive status."""
    conn = get_connection()
    conn.execute("UPDATE salesmen SET active = 1 - active WHERE id=?", (salesman_id,))
    conn.commit()
    conn.close()


def db_delete_salesman(salesman_id: int):
    """Delete a salesman record (raise IntegrityError if referenced by sales)."""
    conn = get_connection()
    conn.execute("DELETE FROM salesmen WHERE id=?", (salesman_id,))
    conn.commit()
    conn.close()


def db_today_sales_by_salesman(today_str: str) -> list:
    """
    Returns one row per ACTIVE salesman with today's aggregated sales stats.
    today_str: DD/MM/YYYY
    Row keys: id, name, units (phones sold), total_amount
    Salesmen with zero sales today are still included.
    """
    conn = get_connection()
    rows = conn.execute("""
        SELECT sm.id, sm.name,
               COALESCE((
                   SELECT COUNT(sl.id)
                   FROM sale_vouchers sv
                   JOIN sale_lines sl ON sl.sv_id = sv.id
                   WHERE sv.salesman_id = sm.id AND sv.date = ?
               ), 0) AS units,
               COALESCE((
                   SELECT SUM(sv.total_amount)
                   FROM sale_vouchers sv
                   WHERE sv.salesman_id = sm.id AND sv.date = ?
               ), 0) AS total_amount
        FROM salesmen sm
        WHERE sm.active = 1
        ORDER BY sm.name
    """, (today_str, today_str)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    init_db()
    print(f"Database initialised at: {DB_PATH}")
