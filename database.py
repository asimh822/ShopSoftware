import hashlib
import sqlite3
import os
from datetime import date, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "united_mobile.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
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

        CREATE TABLE IF NOT EXISTS deleted_vouchers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            voucher_number TEXT NOT NULL,
            voucher_type TEXT NOT NULL,
            voucher_date TEXT,
            amount REAL,
            party_name TEXT,
            deleted_by TEXT,
            deleted_at TEXT NOT NULL,
            reason TEXT,
            purge_after TEXT NOT NULL
        );
    """)

    _seed_settings(c)
    _run_migrations(conn)
    _ensure_columns(conn)
    conn.commit()
    from capital import migrate_capital_tables
    migrate_capital_tables(conn)
    if conn.execute("SELECT COUNT(*) FROM capital_accounts").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO capital_accounts (name, opening_balance) VALUES (?,?)",
            [("Asim Hussain", 3000000), ("Khurram Ansari", 1500000), ("Mumtaz Ahmad", 1500000)],
        )
    conn.execute("DELETE FROM deleted_vouchers WHERE purge_after < date('now')")
    conn.commit()
    conn.close()


def _seed_settings(c):
    import datetime as _dt
    _yr = _dt.date.today().year
    defaults = {
        "pin_hash": hashlib.sha256(b"119211").hexdigest(),
        # Owner PIN — gates Capital and Settings. Seeded once via INSERT OR IGNORE
        # below, so a later change to this value is never overwritten on startup.
        "owner_pin": "9211",
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


# ── Additive column helper ────────────────────────────────────────────────────

def ensure_column(conn, table: str, column: str, definition: str) -> None:
    """
    Idempotently add a column to an existing table.
    Safe to call every launch — acts only when the column is absent.

    SQLite ADD COLUMN limits (no full table rebuild needed unless these apply):
      - Cannot add a UNIQUE or PRIMARY KEY column.
      - DEFAULT must be a constant literal; CURRENT_TIMESTAMP is rejected on
        SQLite < 3.37.0 — use a string like '2000-01-01 00:00:01' instead.
      - Cannot drop or rename a column this way — use the rename-copy-drop
        pattern already used in _migrate_v7/_v8/_v9 for those cases.
    """
    existing = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _ensure_columns(conn) -> None:
    """
    Called once per startup after _run_migrations().
    Add one ensure_column() call here for each new column that hasn't yet been
    promoted to a numbered _migrate_vN(). Once a column has been in production
    long enough, move it into a migration and remove the call from here.
    """
    # No pending columns at this time.
    pass


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
       The runner applies every dict entry whose version > the stored
       db_version, so the dict is the single source of truth — there is no
       separate version constant to keep in sync.
    """
    # Register every migration here — key = target version number
    _MIGRATIONS: dict[int, callable] = {
        1: _migrate_v1,
        2: _migrate_v2,
        3: _migrate_v3,
        4: _migrate_v4,
        5: _migrate_v5,
        6: _migrate_v6,
        7: _migrate_v7,
        8: _migrate_v8,
        9: _migrate_v9,
        10: _migrate_v10,
        11: _migrate_v11,
        12: _migrate_v12,
        13: _migrate_v13,
        14: _migrate_v14,
        15: _migrate_v15,
        16: _migrate_v16,
        17: _migrate_v17,
        18: _migrate_v18,
        19: _migrate_v19,
        20: _migrate_v20,
        21: _migrate_v21,
        22: _migrate_v22,
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


def _migrate_v5(conn) -> None:
    """
    Version 5 — Fixed Assets and Committees tables.
    Do NOT add a conn.commit() here — _run_migrations() commits per version.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fixed_assets (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            name  TEXT NOT NULL,
            value REAL NOT NULL DEFAULT 0
        )
    """)


def _migrate_v6(conn) -> None:
    """
    Version 6 — Incentives Income account.
    A single system income account used as the Cr side of a JV when recording
    supplier incentives, rebates or margin adjustments. Its running balance is
    held directly on income_accounts.balance.
    Do NOT add a conn.commit() here — _run_migrations() commits per version.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS income_accounts (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            name    TEXT NOT NULL,
            balance REAL DEFAULT 0
        )
    """)
    # Seed the single 'Incentives Income' account (idempotent).
    conn.execute(
        "INSERT INTO income_accounts (name, balance) "
        "SELECT 'Incentives Income', 0 "
        "WHERE NOT EXISTS (SELECT 1 FROM income_accounts WHERE name='Incentives Income')"
    )


def _migrate_v7(conn) -> None:
    """
    Version 7 — Other Parties (personal loans / friend accounts).
    1. Creates the other_parties table.
    2. Relaxes the party_type CHECK on payments and journal_entries to also
       allow 'other', so the existing ledger code can record CP/CR and journal
       entries against these accounts unchanged. SQLite cannot ALTER a CHECK
       constraint, so each table is rebuilt in place, preserving all rows/ids.
    Do NOT add a conn.commit() here — _run_migrations() commits per version.
    """
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS other_parties (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            contact         TEXT,
            opening_balance REAL DEFAULT 0,
            notes           TEXT
        )
    """)

    # ── Relax payments.party_type CHECK → add 'other' ────────────────────────
    pay = c.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='payments'"
    ).fetchone()
    if pay and "'other'" not in pay[0]:
        c.execute("ALTER TABLE payments RENAME TO _payments_old")
        c.execute("""
            CREATE TABLE payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                voucher_number TEXT UNIQUE NOT NULL,
                party_type TEXT CHECK(party_type IN ('supplier', 'customer', 'other')),
                party_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                amount REAL NOT NULL,
                type TEXT CHECK(type IN ('CP', 'CR')),
                notes TEXT
            )
        """)
        c.execute(
            "INSERT INTO payments "
            "(id, voucher_number, party_type, party_id, date, amount, type, notes) "
            "SELECT id, voucher_number, party_type, party_id, date, amount, type, notes "
            "FROM _payments_old"
        )
        c.execute("DROP TABLE _payments_old")

    # ── Relax journal_entries.party_type CHECK → add 'other' ─────────────────
    je = c.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='journal_entries'"
    ).fetchone()
    if je and "'other'" not in je[0]:
        c.execute("ALTER TABLE journal_entries RENAME TO _je_old")
        c.execute("""
            CREATE TABLE journal_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                jv_number TEXT UNIQUE NOT NULL,
                party_type TEXT CHECK(party_type IN ('supplier', 'customer', 'other')),
                party_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                amount REAL NOT NULL,
                type TEXT CHECK(type IN ('debit', 'credit')),
                notes TEXT
            )
        """)
        c.execute(
            "INSERT INTO journal_entries "
            "(id, jv_number, party_type, party_id, date, amount, type, notes) "
            "SELECT id, jv_number, party_type, party_id, date, amount, type, notes "
            "FROM _je_old"
        )
        c.execute("DROP TABLE _je_old")


def _migrate_v8(conn) -> None:
    """
    Version 8 — Remove UNIQUE constraint from payments.voucher_number.
    Multi-line CP/CR vouchers share the same voucher_number across multiple rows.
    Idempotent: if UNIQUE is already absent the function returns immediately.
    Do NOT add conn.commit() here — _run_migrations() commits per version.
    """
    c = conn.cursor()
    row = c.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='payments'"
    ).fetchone()
    if row is None:
        return                          # payments table absent — nothing to do
    if "UNIQUE" not in row[0].upper():
        return                          # UNIQUE already removed — idempotent skip

    c.execute("ALTER TABLE payments RENAME TO _payments_v8_old")
    c.execute("""
        CREATE TABLE payments (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            voucher_number TEXT NOT NULL,
            party_type     TEXT CHECK(party_type IN ('supplier','customer','other')),
            party_id       INTEGER NOT NULL,
            date           TEXT NOT NULL,
            amount         REAL NOT NULL,
            type           TEXT CHECK(type IN ('CP','CR')),
            notes          TEXT
        )
    """)
    c.execute("""
        INSERT INTO payments
            (id, voucher_number, party_type, party_id, date, amount, type, notes)
        SELECT id, voucher_number, party_type, party_id, date, amount, type, notes
        FROM _payments_v8_old
    """)
    c.execute("DROP TABLE _payments_v8_old")


def _migrate_v9(conn) -> None:
    """
    Version 9 — Cross-party selling, salesman on purchase, and JV UNIQUE fix.
    - Adds supplier_as_customer_id to sale_vouchers
    - Adds customer_as_supplier_id and salesman_id to purchase_vouchers
    - Removes UNIQUE constraint from journal_entries.jv_number so that
      double-entry JVs (Dr+Cr both hitting journal_entries) no longer fail.
    Do NOT add conn.commit() here — _run_migrations() commits per version.
    """
    c = conn.cursor()

    try:
        c.execute(
            "ALTER TABLE sale_vouchers ADD COLUMN supplier_as_customer_id "
            "INTEGER REFERENCES suppliers(id)"
        )
    except Exception:
        pass

    try:
        c.execute(
            "ALTER TABLE purchase_vouchers ADD COLUMN customer_as_supplier_id "
            "INTEGER REFERENCES customers(id)"
        )
    except Exception:
        pass

    try:
        c.execute(
            "ALTER TABLE purchase_vouchers ADD COLUMN salesman_id "
            "INTEGER REFERENCES salesmen(id)"
        )
    except Exception:
        pass

    # Remove UNIQUE from journal_entries.jv_number — SQLite requires table rebuild
    je = c.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='journal_entries'"
    ).fetchone()
    if je and "jv_number TEXT UNIQUE" in (je[0] or ""):
        c.execute("ALTER TABLE journal_entries RENAME TO _je_v9_old")
        c.execute("""
            CREATE TABLE journal_entries (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                jv_number  TEXT NOT NULL,
                party_type TEXT CHECK(party_type IN ('supplier', 'customer', 'other')),
                party_id   INTEGER NOT NULL,
                date       TEXT NOT NULL,
                amount     REAL NOT NULL,
                type       TEXT CHECK(type IN ('debit', 'credit')),
                notes      TEXT
            )
        """)
        c.execute("""
            INSERT INTO journal_entries
                (id, jv_number, party_type, party_id, date, amount, type, notes)
            SELECT id, jv_number, party_type, party_id, date, amount, type, notes
            FROM _je_v9_old
        """)
        c.execute("DROP TABLE _je_v9_old")


def _migrate_v10(conn) -> None:
    """Version 10 — Add per-line reference column to payments table."""
    c = conn.cursor()
    try:
        c.execute("ALTER TABLE payments ADD COLUMN reference TEXT")
    except Exception:
        pass  # Column already exists


def _migrate_v14(conn) -> None:
    """
    Version 14 — Expense Categories + 'expense' party_type in payments/journal_entries.
    1. Creates expense_categories table and seeds default categories.
    2. Rebuilds payments to add 'expense' to party_type CHECK and add payment_method column.
    3. Rebuilds journal_entries to add 'expense' to party_type CHECK.
    All rebuilds are idempotent — skip if 'expense' is already in the constraint.
    Do NOT add conn.commit() here — _run_migrations() commits per version.
    """
    c = conn.cursor()

    # 1. Create and seed expense_categories
    c.execute("""
        CREATE TABLE IF NOT EXISTS expense_categories (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        )
    """)
    for cat in ["Rent", "Salaries", "Electricity", "Internet", "Travel", "Miscellaneous"]:
        c.execute(
            "INSERT INTO expense_categories (name) "
            "SELECT ? WHERE NOT EXISTS (SELECT 1 FROM expense_categories WHERE name=?)",
            (cat, cat),
        )

    # 2. Rebuild payments: add 'expense' to CHECK + add payment_method column
    pay = c.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='payments'"
    ).fetchone()
    if pay and "'expense'" not in pay[0]:
        c.execute("ALTER TABLE payments RENAME TO _payments_v14_old")
        c.execute("""
            CREATE TABLE payments (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                voucher_number TEXT NOT NULL,
                party_type     TEXT CHECK(party_type IN ('supplier','customer','other','expense')),
                party_id       INTEGER NOT NULL,
                date           TEXT NOT NULL,
                amount         REAL NOT NULL,
                type           TEXT CHECK(type IN ('CP','CR')),
                notes          TEXT,
                reference      TEXT,
                payment_method TEXT CHECK(payment_method IN ('cash','bank')) DEFAULT 'cash'
            )
        """)
        c.execute("""
            INSERT INTO payments
                (id, voucher_number, party_type, party_id, date, amount, type, notes, reference)
            SELECT id, voucher_number, party_type, party_id, date, amount, type, notes, reference
            FROM _payments_v14_old
        """)
        c.execute("DROP TABLE _payments_v14_old")

    # 3. Rebuild journal_entries: add 'expense' to party_type CHECK
    je = c.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='journal_entries'"
    ).fetchone()
    if je and "'expense'" not in je[0]:
        c.execute("ALTER TABLE journal_entries RENAME TO _je_v14_old")
        c.execute("""
            CREATE TABLE journal_entries (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                jv_number  TEXT NOT NULL,
                party_type TEXT CHECK(party_type IN ('supplier','customer','other','expense')),
                party_id   INTEGER NOT NULL,
                date       TEXT NOT NULL,
                amount     REAL NOT NULL,
                type       TEXT CHECK(type IN ('debit','credit')),
                notes      TEXT
            )
        """)
        c.execute("""
            INSERT INTO journal_entries
                (id, jv_number, party_type, party_id, date, amount, type, notes)
            SELECT id, jv_number, party_type, party_id, date, amount, type, notes
            FROM _je_v14_old
        """)
        c.execute("DROP TABLE _je_v14_old")


def _migrate_v15(conn) -> None:
    """
    Version 15 — Restore last_modified on payments and journal_entries.
    The v14 rebuild created new tables without the last_modified column that
    v11/v12 had added. Re-add the column, triggers, and backfill all rows.
    Do NOT add conn.commit() here — _run_migrations() commits per version.
    """
    c = conn.cursor()
    for table in ("payments", "journal_entries"):
        existing = [r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()]
        if "last_modified" not in existing:
            c.execute(
                f"ALTER TABLE {table} ADD COLUMN "
                f"last_modified TEXT DEFAULT '2000-01-01 00:00:01'"
            )
        c.execute(f"""
            CREATE TRIGGER IF NOT EXISTS {table}_last_modified_update
            AFTER UPDATE ON {table}
            BEGIN
                UPDATE {table} SET last_modified = CURRENT_TIMESTAMP
                WHERE id = NEW.id;
            END;
        """)
        c.execute(f"""
            CREATE TRIGGER IF NOT EXISTS {table}_last_modified_insert
            AFTER INSERT ON {table}
            BEGIN
                UPDATE {table} SET last_modified = CURRENT_TIMESTAMP
                WHERE id = NEW.id;
            END;
        """)
        c.execute(
            f"UPDATE {table} SET last_modified = CURRENT_TIMESTAMP "
            f"WHERE last_modified IS NULL OR last_modified = '2000-01-01 00:00:01'"
        )


def _migrate_v16(conn) -> None:
    """
    Version 16 — Multi-line Journal Voucher tables.
    journal_vouchers: header (jv_number, date, notes)
    journal_voucher_lines: per-line debits/credits for any party type.
    Legacy journal_entries rows remain untouched and read-only.
    Do NOT add conn.commit() here — _run_migrations() commits per version.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS journal_vouchers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            jv_number TEXT UNIQUE NOT NULL,
            date TEXT NOT NULL,
            notes TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS journal_voucher_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            jv_id INTEGER NOT NULL REFERENCES journal_vouchers(id),
            party_type TEXT NOT NULL,
            party_id INTEGER,
            debit REAL NOT NULL DEFAULT 0,
            credit REAL NOT NULL DEFAULT 0
        )
    """)


def _migrate_v17(conn) -> None:
    """Version 17 — Add reference column to journal_voucher_lines."""
    try:
        conn.execute("ALTER TABLE journal_voucher_lines ADD COLUMN reference TEXT")
        conn.commit()
    except Exception:
        pass  # column already exists


def _migrate_v18(conn) -> None:
    """
    Version 18 — Supabase sync support for journal_vouchers / journal_voucher_lines.
    These tables were added in v16 (JV redesign) but never got the last_modified
    column + triggers that every other Supabase-synced table has, so
    supabase_sync.py's "WHERE last_modified > ?" query silently failed for them
    on every sync (caught by run_sync()'s per-table try/except) — meaning JVs
    that move money to/from a bank account, supplier, customer, or cash never
    reached Supabase, and mobile owner balances drifted from desktop.
    Do NOT add conn.commit() here — _run_migrations() commits per version.
    """
    c = conn.cursor()

    for table in ["journal_vouchers", "journal_voucher_lines"]:
        try:
            c.execute(
                f"ALTER TABLE {table} ADD COLUMN "
                f"last_modified TEXT DEFAULT '2000-01-01 00:00:01'"
            )
        except Exception:
            pass  # column already exists

        c.execute(f"""
            CREATE TRIGGER IF NOT EXISTS {table}_last_modified_update
            AFTER UPDATE ON {table}
            BEGIN
                UPDATE {table} SET last_modified = CURRENT_TIMESTAMP
                WHERE id = NEW.id;
            END;
        """)

        c.execute(f"""
            CREATE TRIGGER IF NOT EXISTS {table}_last_modified_insert
            AFTER INSERT ON {table}
            BEGIN
                UPDATE {table} SET last_modified = CURRENT_TIMESTAMP
                WHERE id = NEW.id;
            END;
        """)

        # Backfill existing rows so the next sync pushes all past JVs too
        c.execute(
            f"UPDATE {table} SET last_modified = CURRENT_TIMESTAMP "
            f"WHERE last_modified IS NULL "
            f"   OR last_modified = '2000-01-01 00:00:01'"
        )


def _migrate_v19(conn) -> None:
    """
    Version 19 — Drop dead tables.
    • cash_journal_lines: the pre-v16 JV system stored the cash side of a JV
      here. The unified JV system (v16) writes cash lines to
      journal_voucher_lines with party_type='cash' instead; nothing has
      written to this table since, and the shop DB holds 0 rows. All read
      references were removed alongside this migration.
    • committees: the committee feature was removed from the UI in June 2026;
      committees.py is no longer imported anywhere and the table is empty.
    DROP TABLE also removes the tables' last_modified triggers automatically.
    Do NOT add conn.commit() here — _run_migrations() commits per version.
    """
    c = conn.cursor()
    # Safety net: never drop data. Both tables are expected to be empty; if a
    # row somehow exists, keep the table and let a human look at it.
    for table in ("cash_journal_lines", "committees"):
        try:
            rows = c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except Exception:
            continue  # table already absent
        if rows == 0:
            c.execute(f"DROP TABLE {table}")
        else:
            print(f"Database: v19 skipped dropping {table} — it has {rows} rows")


def _migrate_v20(conn) -> None:
    """
    Version 20 — Normalise payment fields left stale by voucher edits.

    Editing a cash purchase and assigning it a supplier converted it to a
    credit purchase but kept payment_method='cash' / cash_amount, which
    inflated both cash-in-hand and the supplier balance (652,800 across six
    vouchers on the shop DB; owner confirmed these are credit purchases).
    The edit dialog now clears these fields on conversion; this migration
    repairs rows written before that fix. Also relabels credit sales that
    carry payment_method='cash' with no money attached (same class of stale
    data from sale edits).
    Do NOT add conn.commit() here — _run_migrations() commits per version.
    """
    c = conn.cursor()
    c.execute("""
        UPDATE purchase_vouchers
        SET payment_method='', cash_amount=0, bank_amount=0,
            bank_account_id=NULL, bank_ref=''
        WHERE purchase_type='supplier'
          AND (COALESCE(payment_method,'') <> ''
               OR COALESCE(cash_amount,0) <> 0
               OR COALESCE(bank_amount,0) <> 0)
    """)
    c.execute("""
        DELETE FROM bank_transactions
        WHERE source='cash_purchase'
          AND voucher_number IN (
              SELECT pv_number FROM purchase_vouchers WHERE purchase_type='supplier')
    """)
    c.execute("""
        UPDATE sale_vouchers
        SET payment_method='credit'
        WHERE type='credit' AND payment_method='cash'
          AND COALESCE(cash_paid,0)=0 AND COALESCE(bank_amount,0)=0
    """)


def _migrate_v21(conn) -> None:
    """
    Version 21 — Propagate local deletions to Supabase.

    The sync is upsert-only, so deleting a synced voucher locally left a
    ghost row in Supabase forever, silently distorting the mobile owner
    figures. This adds a sync_deletions tombstone table plus an AFTER DELETE
    trigger on every synced table, so every deletion (from any code path,
    including future ones) is queued and pushed by supabase_sync.py on the
    next sync. Tombstones survive offline periods and are removed only after
    the remote delete succeeds.
    Do NOT add conn.commit() here — _run_migrations() commits per version.
    """
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS sync_deletions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT NOT NULL,
            row_id     INTEGER NOT NULL,
            deleted_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    synced_tables = [
        "suppliers", "customers", "bank_accounts", "purchase_vouchers",
        "sale_vouchers", "sale_lines", "stock_items", "models", "brands",
        "payments", "journal_entries", "journal_vouchers",
        "journal_voucher_lines", "purchase_returns", "sale_returns",
        "bank_transactions", "expenses",
    ]
    for table in synced_tables:
        c.execute(f"""
            CREATE TRIGGER IF NOT EXISTS {table}_sync_delete
            AFTER DELETE ON {table}
            BEGIN
                INSERT INTO sync_deletions (table_name, row_id)
                VALUES ('{table}', OLD.id);
            END;
        """)


def _migrate_v22(conn) -> None:
    """
    Version 22 — Fix incentive income lines recorded on the wrong side.

    Three early JVs (JV-0013/14/15, June 2026) recorded incentive income as
    a DEBIT of incentive_income (income should always be a credit), leaving
    those vouchers unbalanced (Dr Supplier + Dr Incentive Income). A negation
    hack in db_incentives_income_total() compensated while ALL lines were
    debits, but the first correctly-entered credit line (JV-0021) made every
    subsequent incentive REDUCE the reported income figure.
    Flips debit-side incentive lines to credit; the negation hack is removed
    from db_incentives_income_total() in the same change.
    Do NOT add conn.commit() here — _run_migrations() commits per version.
    """
    conn.execute("""
        UPDATE journal_voucher_lines
        SET credit = debit, debit = 0
        WHERE party_type='incentive_income' AND debit > 0 AND credit = 0
    """)


_SUPABASE_SYNC_TABLES = [
    "suppliers", "customers", "bank_accounts", "purchase_vouchers",
    "sale_vouchers", "sale_lines", "stock_items", "models", "brands",
    "payments", "journal_entries", "purchase_returns", "sale_returns",
    "bank_transactions", "expenses",
]


def _migrate_v11(conn) -> None:
    """
    Version 11 — Supabase sync support.
    Adds last_modified column to all sync-tracked tables and creates
    INSERT/UPDATE triggers to keep it current automatically.
    Also seeds the last_supabase_sync setting used by supabase_sync.py.

    NOTE: Uses string literal default '2000-01-01 00:00:01' instead of
    CURRENT_TIMESTAMP because SQLite < 3.37.0 rejects non-constant defaults
    in ALTER TABLE ADD COLUMN. _migrate_v12 backfills existing rows.
    Do NOT add conn.commit() here — _run_migrations() commits per version.
    """
    c = conn.cursor()

    for table in _SUPABASE_SYNC_TABLES:
        # String literal default works on all SQLite versions
        try:
            c.execute(
                f"ALTER TABLE {table} ADD COLUMN "
                f"last_modified TEXT DEFAULT '2000-01-01 00:00:01'"
            )
        except Exception:
            pass  # column already exists

        # UPDATE trigger
        c.execute(f"""
            CREATE TRIGGER IF NOT EXISTS {table}_last_modified_update
            AFTER UPDATE ON {table}
            BEGIN
                UPDATE {table} SET last_modified = CURRENT_TIMESTAMP
                WHERE id = NEW.id;
            END;
        """)

        # INSERT trigger
        c.execute(f"""
            CREATE TRIGGER IF NOT EXISTS {table}_last_modified_insert
            AFTER INSERT ON {table}
            BEGIN
                UPDATE {table} SET last_modified = CURRENT_TIMESTAMP
                WHERE id = NEW.id;
            END;
        """)

    # Seed the sync timestamp — ignored if already present
    c.execute(
        "INSERT OR IGNORE INTO settings (key, value) "
        "VALUES ('last_supabase_sync', '2000-01-01 00:00:00')"
    )


def _migrate_v12(conn) -> None:
    """
    Version 12 — Backfill last_modified on existing rows.
    On databases where v11 ran but the ADD COLUMN silently failed (SQLite < 3.37.0
    rejects CURRENT_TIMESTAMP as a default in ALTER TABLE), the column is missing.
    This migration adds it via a string literal (always works) then stamps all
    existing rows with CURRENT_TIMESTAMP so the next Supabase sync picks them up.
    Do NOT add conn.commit() here — _run_migrations() commits per version.
    """
    c = conn.cursor()

    for table in _SUPABASE_SYNC_TABLES:
        existing = [
            r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()
        ]
        if 'last_modified' not in existing:
            try:
                c.execute(
                    f"ALTER TABLE {table} ADD COLUMN "
                    f"last_modified TEXT DEFAULT '2000-01-01 00:00:01'"
                )
            except Exception as e:
                print(f"[migrate_v12] Cannot add last_modified to {table}: {e}")
                continue

        # Stamp every row that still has the placeholder (or NULL) so the
        # first Supabase sync sees them all as "changed since epoch".
        c.execute(
            f"UPDATE {table} SET last_modified = CURRENT_TIMESTAMP "
            f"WHERE last_modified IS NULL "
            f"   OR last_modified = '2000-01-01 00:00:01'"
        )


def _migrate_v13(conn) -> None:
    """
    Version 13 — Extend Supabase sync to bank_transactions and expenses.
    Adds last_modified column and INSERT/UPDATE triggers so the
    sync service picks up changes to these tables incrementally.
    Also backfills existing rows so the next sync pushes them all to Supabase.
    (cash_journal_lines was originally in this list; it is dropped in v19,
    so fresh databases no longer create it and it is skipped here.)
    Do NOT add conn.commit() here — _run_migrations() commits per version.
    """
    c = conn.cursor()

    for table in ["bank_transactions", "expenses"]:
        # String literal default — works on all SQLite versions (< 3.37.0 safe)
        try:
            c.execute(
                f"ALTER TABLE {table} ADD COLUMN "
                f"last_modified TEXT DEFAULT '2000-01-01 00:00:01'"
            )
        except Exception:
            pass  # column already exists

        # UPDATE trigger
        c.execute(f"""
            CREATE TRIGGER IF NOT EXISTS {table}_last_modified_update
            AFTER UPDATE ON {table}
            BEGIN
                UPDATE {table} SET last_modified = CURRENT_TIMESTAMP
                WHERE id = NEW.id;
            END;
        """)

        # INSERT trigger
        c.execute(f"""
            CREATE TRIGGER IF NOT EXISTS {table}_last_modified_insert
            AFTER INSERT ON {table}
            BEGIN
                UPDATE {table} SET last_modified = CURRENT_TIMESTAMP
                WHERE id = NEW.id;
            END;
        """)

        # Backfill existing rows so the first sync picks them all up
        c.execute(
            f"UPDATE {table} SET last_modified = CURRENT_TIMESTAMP "
            f"WHERE last_modified IS NULL "
            f"   OR last_modified = '2000-01-01 00:00:01'"
        )


def db_remove_stock_item(c, stock_item_id):
    """
    Take a stock item out of stock because its purchase line is being removed
    (purchase edit / purchase delete) or it is being returned to the supplier.

    A phone that was sold and later repurchased still has old sale_lines rows
    pointing at this stock_items row, so a plain DELETE violates the
    sale_lines.stock_item_id foreign key. For those, revert the row to its
    pre-repurchase state instead: status='sold', sold_line_id = its latest
    sale line, purchase_line_id/price = its previous purchase line.
    Accepts a cursor or a connection.
    """
    last_sale = c.execute(
        "SELECT id FROM sale_lines WHERE stock_item_id=? ORDER BY id DESC LIMIT 1",
        (stock_item_id,),
    ).fetchone()
    if not last_sale:
        c.execute("DELETE FROM stock_items WHERE id=?", (stock_item_id,))
        return

    row = c.execute(
        "SELECT imei, purchase_line_id FROM stock_items WHERE id=?",
        (stock_item_id,),
    ).fetchone()
    prev_pl = c.execute(
        "SELECT id, purchase_price FROM purchase_lines "
        "WHERE imei=? AND id <> COALESCE(?, -1) ORDER BY id DESC LIMIT 1",
        (row["imei"], row["purchase_line_id"]),
    ).fetchone()
    c.execute(
        "UPDATE stock_items SET status='sold', sold_line_id=?, "
        "purchase_line_id=?, purchase_price=COALESCE(?, purchase_price) "
        "WHERE id=?",
        (
            last_sale["id"],
            prev_pl["id"] if prev_pl else None,
            prev_pl["purchase_price"] if prev_pl else None,
            stock_item_id,
        ),
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


def db_expense_categories() -> list:
    """Return all expense category rows [{id, name}, ...] from expense_categories table."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, name FROM expense_categories ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def db_all_expenses_combined(from_iso: str = '', to_iso: str = '',
                              category: str = '') -> dict:
    """
    Combined expense data from both legacy 'expenses' table (EXP-XXXX) and
    new payments/journal_entries rows where party_type='expense'.

    Returns same structure as db_expenses_by_category():
        {"rows": [{category, count, total}], "detail": [...], "grand_total", "grand_count"}
    """
    def _de(col):
        return f"substr({col},7,4)||'-'||substr({col},4,2)||'-'||substr({col},1,2)"

    conn = get_connection()
    conds_e, params_e = [], []
    conds_p, params_p = ["p.party_type='expense'", "p.type='CP'"], []

    if from_iso:
        conds_e.append(f"{_de('e.date')} >= ?"); params_e.append(from_iso)
        conds_p.append(f"{_de('p.date')} >= ?"); params_p.append(from_iso)
    if to_iso:
        conds_e.append(f"{_de('e.date')} <= ?"); params_e.append(to_iso)
        conds_p.append(f"{_de('p.date')} <= ?"); params_p.append(to_iso)
    if category:
        conds_e.append("e.category = ?"); params_e.append(category)
        conds_p.append("ec.name = ?");    params_p.append(category)

    where_e = ("WHERE " + " AND ".join(conds_e)) if conds_e else ""
    where_p = ("WHERE " + " AND ".join(conds_p)) if conds_p else ""

    # Legacy rows
    legacy = conn.execute(f"""
        SELECT e.expense_number voucher_number, e.date,
               e.category, COALESCE(e.description,'') description,
               e.amount, COALESCE(e.payment_method,'cash') payment_method,
               COALESCE(ba.name,'') bank_name
        FROM expenses e
        LEFT JOIN bank_accounts ba ON ba.id = e.bank_account_id
        {where_e}
        ORDER BY {_de('e.date')}, e.id
    """, params_e).fetchall()

    # New CP payments rows
    new_cp = conn.execute(f"""
        SELECT p.voucher_number, p.date,
               COALESCE(ec.name, '?') category,
               COALESCE(p.reference, p.notes, '') description,
               p.amount, COALESCE(p.payment_method,'cash') payment_method,
               '' bank_name
        FROM payments p
        LEFT JOIN expense_categories ec ON ec.id = p.party_id
        {where_p}
        ORDER BY {_de('p.date')}, p.id
    """, params_p).fetchall()

    detail = []
    for r in legacy:
        detail.append({
            "expense_number": r["voucher_number"], "date": r["date"],
            "category": r["category"], "description": r["description"],
            "amount": float(r["amount"] or 0), "payment_method": r["payment_method"],
            "bank_name": r["bank_name"],
        })
    for r in new_cp:
        detail.append({
            "expense_number": r["voucher_number"], "date": r["date"],
            "category": r["category"], "description": r["description"],
            "amount": float(r["amount"] or 0), "payment_method": r["payment_method"],
            "bank_name": r["bank_name"],
        })

    # Sort combined detail by ISO date
    detail.sort(key=lambda d: (
        d["date"][6:10] + "-" + d["date"][3:5] + "-" + d["date"][0:2]
        if len(d["date"]) == 10 else d["date"]
    ))

    # Group by category
    from collections import defaultdict
    cat_map = defaultdict(lambda: {"count": 0, "total": 0.0})
    for d in detail:
        cat_map[d["category"]]["count"] += 1
        cat_map[d["category"]]["total"] += d["amount"]

    rows = sorted(
        [{"category": k, "count": v["count"], "total": v["total"]}
         for k, v in cat_map.items()],
        key=lambda r: r["total"], reverse=True,
    )
    grand_total = sum(r["total"] for r in rows)
    grand_count = sum(r["count"] for r in rows)

    conn.close()
    return {"rows": rows, "detail": detail,
            "grand_total": grand_total, "grand_count": grand_count}


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


def check_owner_pin(entered: str) -> bool:
    """Owner PIN gating Capital & Settings. Stored in plaintext under 'owner_pin'."""
    stored = get_setting("owner_pin")
    return stored is not None and entered == stored


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
    + JVL debit  (money IN via journal voucher)
    - JVL credit (money OUT via journal voucher)
    """
    conn = get_connection()
    result = conn.execute("""
        SELECT
            COALESCE((SELECT SUM(opening_balance) FROM bank_accounts), 0)
            + COALESCE((SELECT SUM(bank_amount) FROM sale_vouchers
                        WHERE bank_account_id IS NOT NULL AND bank_amount > 0), 0)
            + COALESCE((SELECT SUM(amount) FROM bank_transactions WHERE type='CP'), 0)
            - COALESCE((SELECT SUM(amount) FROM bank_transactions WHERE type='CR'), 0)
            + COALESCE((
                SELECT SUM(jvl.debit)
                FROM journal_voucher_lines jvl
                WHERE jvl.party_type = 'bank'
            ), 0)
            - COALESCE((
                SELECT SUM(jvl.credit)
                FROM journal_voucher_lines jvl
                WHERE jvl.party_type = 'bank'
            ), 0)
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


def db_jvl_legacy_equivalent(party_type: str, party_id) -> tuple:
    """
    Sum this party's journal_voucher_lines (the multi-line JV system) and
    translate the result into the legacy journal_entries sign convention
    (type='debit'/'credit'), so callers already doing `+ jv_dr - jv_cr` against
    journal_entries can add this in directly: jv_dr += dr; jv_cr += cr.

    journal_voucher_lines uses standard double-entry Dr/Cr. For a supplier
    (liability) Debit REDUCES the balance and Credit INCREASES it — the
    opposite of the legacy convention, so supplier is inverted here.
    Customer/other use the legacy convention directly (Debit increases what
    they owe, Credit decreases it), so no inversion.
    """
    conn = get_connection()
    row = conn.execute(
        "SELECT COALESCE(SUM(debit),0), COALESCE(SUM(credit),0) "
        "FROM journal_voucher_lines WHERE party_type=? AND party_id=?",
        (party_type, party_id),
    ).fetchone()
    conn.close()
    jvl_debit, jvl_credit = float(row[0] or 0), float(row[1] or 0)
    if party_type == "supplier":
        return jvl_credit, jvl_debit
    return jvl_debit, jvl_credit


def _insert_party_journal_line(c, party_type: str, party_id, date_str: str,
                                debit: float, credit: float, notes: str) -> str:
    """
    Core of db_save_party_journal_line, taking an existing cursor `c` so the
    caller can include this in its own transaction. See db_save_party_journal_line.
    """
    row = c.execute(
        "SELECT value FROM settings WHERE key='last_jv_number'"
    ).fetchone()
    n = int(row["value"]) + 1 if row else 1
    c.execute("UPDATE settings SET value=? WHERE key='last_jv_number'", (str(n),))
    jv_number = f"JV-{n:04d}"
    c.execute(
        "INSERT INTO journal_vouchers (jv_number, date, notes) VALUES (?,?,?)",
        (jv_number, date_str, notes or ""),
    )
    jv_id = c.lastrowid
    c.execute(
        "INSERT INTO journal_voucher_lines "
        "(jv_id, party_type, party_id, debit, credit) VALUES (?,?,?,?,?)",
        (jv_id, party_type, party_id, float(debit or 0), float(credit or 0)),
    )
    return jv_number


def db_save_party_journal_line(party_type: str, party_id, date_str: str,
                                debit: float, credit: float, notes: str) -> str:
    """
    Record a single-sided subsidiary-ledger adjustment (e.g. a sales/purchase
    return's balance write-down) as a one-line entry in the new JV tables.
    Unlike db_save_journal_voucher, this does NOT require Dr == Cr — there is
    no natural contra account for these adjustments, matching the legacy
    journal_entries behaviour they replace.

    Standalone wrapper (own connection/commit). Call sites that already have
    an open cursor as part of a larger transaction should use
    _insert_party_journal_line(c, ...) directly instead, to keep the
    adjustment atomic with the rest of their save.
    """
    conn = get_connection()
    try:
        c = conn.cursor()
        jv_number = _insert_party_journal_line(
            c, party_type, party_id, date_str, debit, credit, notes
        )
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()
    return jv_number


# ── Multi-line Journal Voucher helpers ───────────────────────────────────────

def _resolve_party_name(party_type: str, party_id, conn) -> str:
    """Return display name for a journal_voucher_line party."""
    if party_type == "cash":
        return "Cash in Hand"
    if party_type == "incentive_income":
        return "Incentive Income"
    if party_id is None:
        return party_type.title()
    tbl = {
        "supplier": "suppliers",
        "customer": "customers",
        "other": "other_parties",
        "bank": "bank_accounts",
        "expense": "expense_categories",
    }.get(party_type)
    if not tbl:
        return party_type.title()
    row = conn.execute(f"SELECT name FROM {tbl} WHERE id=?", (party_id,)).fetchone()
    return row["name"] if row else party_type.title()


def db_save_journal_voucher(date_str: str, notes: str, lines: list) -> str:
    """
    lines = [{"party_type": str, "party_id": int|None, "debit": float, "credit": float}, ...]
    Validates Dr == Cr, saves journal_vouchers + journal_voucher_lines.
    Returns jv_number.
    """
    total_dr = sum(float(l.get("debit") or 0) for l in lines)
    total_cr = sum(float(l.get("credit") or 0) for l in lines)
    if abs(total_dr - total_cr) > 0.01:
        raise ValueError(
            f"Journal Voucher does not balance — "
            f"Debit: {total_dr:,.0f}  Credit: {total_cr:,.0f}"
        )
    if total_dr == 0:
        raise ValueError("Journal Voucher must have at least one non-zero line.")
    conn = get_connection()
    try:
        c = conn.cursor()
        row = c.execute(
            "SELECT value FROM settings WHERE key='last_jv_number'"
        ).fetchone()
        n = int(row["value"]) + 1 if row else 1
        c.execute("UPDATE settings SET value=? WHERE key='last_jv_number'", (str(n),))
        jv_number = f"JV-{n:04d}"
        c.execute(
            "INSERT INTO journal_vouchers (jv_number, date, notes) VALUES (?,?,?)",
            (jv_number, date_str, notes or ""),
        )
        jv_id = c.lastrowid
        for line in lines:
            c.execute(
                "INSERT INTO journal_voucher_lines "
                "(jv_id, party_type, party_id, debit, credit, reference) VALUES (?,?,?,?,?,?)",
                (jv_id, line["party_type"], line.get("party_id"),
                 float(line.get("debit") or 0), float(line.get("credit") or 0),
                 line.get("reference") or ""),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()
    return jv_number


def db_load_journal_voucher(jv_id: int):
    """Returns (header_dict, [line_dicts]) or (None, []) if not found."""
    conn = get_connection()
    hdr = conn.execute(
        "SELECT id, jv_number, date, notes FROM journal_vouchers WHERE id=?",
        (jv_id,)
    ).fetchone()
    if not hdr:
        conn.close()
        return None, []
    lines = conn.execute(
        "SELECT id, party_type, party_id, debit, credit, reference "
        "FROM journal_voucher_lines WHERE jv_id=? ORDER BY id",
        (jv_id,)
    ).fetchall()
    line_list = []
    for ln in lines:
        name = _resolve_party_name(ln["party_type"], ln["party_id"], conn)
        line_list.append({
            "id": ln["id"],
            "party_type": ln["party_type"],
            "party_id": ln["party_id"],
            "party_name": name,
            "debit": float(ln["debit"] or 0),
            "credit": float(ln["credit"] or 0),
            "reference": ln["reference"] or "",
        })
    conn.close()
    return dict(hdr), line_list


def db_update_journal_voucher(jv_id: int, date_str: str, notes: str, lines: list):
    """Validates balance, deletes old lines and reinserts."""
    total_dr = sum(float(l.get("debit") or 0) for l in lines)
    total_cr = sum(float(l.get("credit") or 0) for l in lines)
    if abs(total_dr - total_cr) > 0.01:
        raise ValueError(
            f"Journal Voucher does not balance — "
            f"Debit: {total_dr:,.0f}  Credit: {total_cr:,.0f}"
        )
    if total_dr == 0:
        raise ValueError("Journal Voucher must have at least one non-zero line.")
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE journal_vouchers SET date=?, notes=? WHERE id=?",
            (date_str, notes or "", jv_id)
        )
        conn.execute("DELETE FROM journal_voucher_lines WHERE jv_id=?", (jv_id,))
        for line in lines:
            conn.execute(
                "INSERT INTO journal_voucher_lines "
                "(jv_id, party_type, party_id, debit, credit, reference) VALUES (?,?,?,?,?,?)",
                (jv_id, line["party_type"], line.get("party_id"),
                 float(line.get("debit") or 0), float(line.get("credit") or 0),
                 line.get("reference") or ""),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()


def db_delete_journal_voucher(jv_id: int):
    conn = get_connection()
    try:
        conn.execute("DELETE FROM journal_voucher_lines WHERE jv_id=?", (jv_id,))
        conn.execute("DELETE FROM journal_vouchers WHERE id=?", (jv_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()


def db_load_journal_vouchers_list(from_iso=None, to_iso=None):
    """
    Returns list of dicts sorted by date:
    id, jv_number, date, notes, line_count, total_dr, is_legacy.
    New-style JVs (journal_vouchers) are fully editable.
    Legacy (journal_entries) appear with is_legacy=True and line_count='—'.
    """
    conn = get_connection()

    def _de(col):
        return f"substr({col},7,4)||'-'||substr({col},4,2)||'-'||substr({col},1,2)"

    rows = []

    # New-style JVs
    q = """
        SELECT jv.id, jv.jv_number, jv.date, jv.notes,
               COUNT(jvl.id) AS line_count,
               COALESCE(SUM(jvl.debit), 0) AS total_dr
        FROM journal_vouchers jv
        LEFT JOIN journal_voucher_lines jvl ON jvl.jv_id = jv.id
    """
    conds, params = [], []
    de = _de("jv.date")
    if from_iso:
        conds.append(f"{de} >= ?")
        params.append(from_iso)
    if to_iso:
        conds.append(f"{de} <= ?")
        params.append(to_iso)
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += f" GROUP BY jv.id ORDER BY {de}, jv.jv_number"
    for r in conn.execute(q, params).fetchall():
        rows.append({
            "id": r["id"],
            "jv_number": r["jv_number"],
            "date": r["date"],
            "notes": r["notes"] or "",
            "line_count": r["line_count"],
            "total_dr": float(r["total_dr"]),
            "is_legacy": False,
        })

    # Legacy journal_entries (read-only)
    lq = """
        SELECT jv_number, date, COALESCE(notes,'') AS notes,
               COUNT(*) AS line_count, COALESCE(SUM(amount),0) AS total_dr
        FROM journal_entries
    """
    l_conds, l_params = [], []
    de2 = _de("date")
    if from_iso:
        l_conds.append(f"{de2} >= ?")
        l_params.append(from_iso)
    if to_iso:
        l_conds.append(f"{de2} <= ?")
        l_params.append(to_iso)
    if l_conds:
        lq += " WHERE " + " AND ".join(l_conds)
    lq += f" GROUP BY jv_number ORDER BY {de2}, jv_number"
    for r in conn.execute(lq, l_params).fetchall():
        rows.append({
            "id": None,
            "jv_number": r["jv_number"] + " (Legacy)",
            "date": r["date"],
            "notes": r["notes"],
            "line_count": "—",
            "total_dr": float(r["total_dr"]),
            "is_legacy": True,
        })

    conn.close()

    def _sort_key(r):
        d = r["date"]
        try:
            parts = d.split("/")
            return (f"{parts[2]}-{parts[1]}-{parts[0]}", r["jv_number"])
        except Exception:
            return ("0000-00-00", r["jv_number"])

    rows.sort(key=_sort_key)
    return rows


# ── Income account helpers ────────────────────────────────────────────────────

def db_income_account(name: str = "Incentives Income"):
    """Return the income account row {id, name, balance} or None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id, name, balance FROM income_accounts WHERE name=?", (name,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def db_incentives_income_total() -> float:
    """Total incentives income earned to date (income_accounts balance + JVL net credits)."""
    acct = db_income_account("Incentives Income")
    base = float(acct["balance"] or 0) if acct else 0.0
    conn = get_connection()
    row = conn.execute(
        "SELECT COALESCE(SUM(credit), 0) - COALESCE(SUM(debit), 0) "
        "FROM journal_voucher_lines WHERE party_type='incentive_income'"
    ).fetchone()
    conn.close()
    # Incentive income lines are always credits (migration v22 flipped the
    # early debit-side entries), so net credits + the legacy account balance
    # is the earned-to-date figure.
    return base + float(row[0] or 0)


def db_cash_in_hand() -> float:
    """
    Running cash in hand — the definitive formula used everywhere:
      + cash_opening_balance  (carried forward from year-end close; 0 on first year)
      + cash_paid on sales (cash portion of sale payments)
      + CR payments (cash received from customers / supplier refunds)
      - CP payments (cash paid to suppliers / customer refunds)
      - bank_transactions CP where source='cash_transfer'  (cash deposited into bank)
      + bank_transactions CR where source='cash_transfer'  (cash withdrawn from bank)
      + journal_voucher_lines Dr Cash  (party_type='cash' debit)
      - journal_voucher_lines Cr Cash  (party_type='cash' credit)
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
            - COALESCE((SELECT SUM(cash_amount) FROM purchase_vouchers
                        WHERE purchase_type='cash' AND cash_amount > 0), 0)
            - COALESCE((SELECT SUM(amount) FROM expenses
                        WHERE payment_method='cash'), 0)
            + COALESCE((SELECT SUM(debit) FROM journal_voucher_lines WHERE party_type='cash'), 0)
            - COALESCE((SELECT SUM(credit) FROM journal_voucher_lines WHERE party_type='cash'), 0)
    """).fetchone()[0]
    conn.close()
    return cash_ob + float(result or 0.0)


# ── Year End Closing helpers ──────────────────────────────────────────────────

def _party_closing_balance(conn, party_type: str, party_id: int) -> float:
    """
    Compute the running ledger balance for a supplier or customer using the
    same DR/CR logic as ledger.py — without importing it (avoids circular import).
    """
    table = {"supplier": "suppliers", "customer": "customers",
             "other": "other_parties"}.get(party_type, "customers")
    ob_row = conn.execute(
        f"SELECT opening_balance FROM {table} WHERE id=?", (party_id,)
    ).fetchone()
    ob = float(ob_row["opening_balance"] or 0) if ob_row else 0.0

    if party_type == "other":
        # No purchases/sales — only cash payments and journal entries.
        # Mirrors the supplier direction: CR received → balance ↑ (you owe more),
        # CP paid → balance ↓; positive balance = you owe them.
        cr = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM payments "
            "WHERE party_type='other' AND party_id=? AND type='CR'",
            (party_id,)
        ).fetchone()[0]
        cp = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM payments "
            "WHERE party_type='other' AND party_id=? AND type='CP'",
            (party_id,)
        ).fetchone()[0]
        jv_dr = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM journal_entries "
            "WHERE party_type='other' AND party_id=? AND type='debit'",
            (party_id,)
        ).fetchone()[0]
        jv_cr = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM journal_entries "
            "WHERE party_type='other' AND party_id=? AND type='credit'",
            (party_id,)
        ).fetchone()[0]
        jvl_dr = conn.execute(
            "SELECT COALESCE(SUM(debit),0) FROM journal_voucher_lines "
            "WHERE party_type='other' AND party_id=?", (party_id,)
        ).fetchone()[0]
        jvl_cr = conn.execute(
            "SELECT COALESCE(SUM(credit),0) FROM journal_voucher_lines "
            "WHERE party_type='other' AND party_id=?", (party_id,)
        ).fetchone()[0]
        return ob + float(cr) - float(cp) + float(jv_dr) - float(jv_cr) + float(jvl_dr) - float(jvl_cr)

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
        jvl_dr = conn.execute(
            "SELECT COALESCE(SUM(debit),0) FROM journal_voucher_lines "
            "WHERE party_type='supplier' AND party_id=?", (party_id,)
        ).fetchone()[0]
        jvl_cr = conn.execute(
            "SELECT COALESCE(SUM(credit),0) FROM journal_voucher_lines "
            "WHERE party_type='supplier' AND party_id=?", (party_id,)
        ).fetchone()[0]
        # Sales to this supplier reduce their balance (they owe us / we owe them less)
        sac = conn.execute(
            "SELECT COALESCE(SUM(total_amount), 0) FROM sale_vouchers "
            "WHERE supplier_as_customer_id=?",
            (party_id,)
        ).fetchone()[0]
        # NOTE: journal_voucher_lines uses standard double-entry Dr/Cr, where for a
        # supplier (liability) Debit REDUCES the balance and Credit INCREASES it —
        # the opposite of jv_dr/jv_cr above, which store the legacy convention
        # directly. See the JV form's own hint text: "Supplier: Debit = reduces
        # balance, Credit = increases balance".
        return ob + float(dr) + float(cr) - float(cp) + float(jv_dr) - float(jv_cr) - float(jvl_dr) + float(jvl_cr) - float(sac)

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
        jvl_dr = conn.execute(
            "SELECT COALESCE(SUM(debit),0) FROM journal_voucher_lines "
            "WHERE party_type='customer' AND party_id=?", (party_id,)
        ).fetchone()[0]
        jvl_cr = conn.execute(
            "SELECT COALESCE(SUM(credit),0) FROM journal_voucher_lines "
            "WHERE party_type='customer' AND party_id=?", (party_id,)
        ).fetchone()[0]
        # Purchases from this customer reduce their balance (we owe them / they owe us less)
        cas = conn.execute(
            "SELECT COALESCE(SUM(total_amount), 0) FROM purchase_vouchers "
            "WHERE customer_as_supplier_id=?",
            (party_id,)
        ).fetchone()[0]
        return ob + float(sales) + float(cp) - float(cr) + float(jv_dr) - float(jv_cr) + float(jvl_dr) - float(jvl_cr) - float(cas)


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
    jvl_dr = conn.execute(
        "SELECT COALESCE(SUM(debit),0) FROM journal_voucher_lines "
        "WHERE party_type='bank' AND party_id=?", (account_id,)
    ).fetchone()[0]
    jvl_cr = conn.execute(
        "SELECT COALESCE(SUM(credit),0) FROM journal_voucher_lines "
        "WHERE party_type='bank' AND party_id=?", (account_id,)
    ).fetchone()[0]
    conn.close()
    return ob + float(sales) + float(cp) - float(cr) + float(jvl_dr) - float(jvl_cr)


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

    # Compute supplier & customer closing balances over a single shared
    # connection (conn2), explicitly closed below.
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
    # ── 1. Archive ───────────────────────────────────────────────────────────
    # Online backup (not a raw file copy) so the archive is a consistent
    # snapshot including WAL contents — critical here, since transactions
    # are deleted right after this archive is written.
    db_backup_to(archive_path)

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

        # ── 2b2. Carry forward other-party (loan) balances ───────────────────
        try:
            others = c.execute("SELECT id FROM other_parties").fetchall()
            for op in others:
                bal = _party_closing_balance(conn, "other", op["id"])
                c.execute(
                    "UPDATE other_parties SET opening_balance=? WHERE id=?",
                    (round(bal, 2), op["id"])
                )
        except Exception:
            pass  # table absent on very old DBs — nothing to carry

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
            "journal_voucher_lines", "journal_vouchers",
            "bank_transactions",
            "expenses",
        ]:
            c.execute(f"DELETE FROM {tbl}")

        # ── 4b. Close income accounts to retained (reset for the new year) ────
        try:
            c.execute("UPDATE income_accounts SET balance = 0")
        except Exception:
            pass  # table absent on very old DBs

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


# ── Database Backup ───────────────────────────────────────────────────────────

def db_backup_to(dest_path: str) -> str:
    """
    Consistent point-in-time backup of the live database to dest_path.

    Uses sqlite3's online backup API instead of a raw file copy: the app runs
    in WAL mode, where recent commits sit in the -wal sidecar until a
    checkpoint, so copying just the .db file can silently miss the newest
    transactions (or catch a checkpoint mid-write). Connection.backup()
    snapshots main db + WAL contents even while other connections are open.

    Writes to '<dest_path>.tmp' first and renames into place on success, so a
    failure partway (disk full, unplugged USB drive) never leaves a truncated
    file that looks like a valid backup. Raises on failure — callers surface
    the error to the user.
    """
    tmp_path = dest_path + ".tmp"
    src = sqlite3.connect(DB_PATH)
    try:
        src.execute("PRAGMA busy_timeout=5000")
        dest = sqlite3.connect(tmp_path)
        try:
            src.backup(dest)
        finally:
            dest.close()
        os.replace(tmp_path, dest_path)
    except BaseException:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
    finally:
        src.close()
    return dest_path


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

    today = _dt.date.today()
    month_key = today.strftime("%m%Y")          # e.g. "052026"

    last = get_setting("last_auto_backup_month") or ""
    if last == month_key:
        return None                             # already done this month

    backups_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backups")
    os.makedirs(backups_dir, exist_ok=True)

    backup_name = f"UnitedMobile_Backup_{month_key}.db"
    backup_path = os.path.join(backups_dir, backup_name)

    db_backup_to(backup_path)
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


# ── Voucher Deletion ─────────────────────────────────────────────────────────

def confirm_owner_pin(parent_widget) -> bool:
    from PyQt6.QtWidgets import QInputDialog, QLineEdit
    pin, ok = QInputDialog.getText(
        parent_widget, "Owner PIN", "Enter Owner PIN:",
        QLineEdit.EchoMode.Password
    )
    if not ok or not pin.strip():
        return False
    return check_owner_pin(pin.strip())


def db_delete_sale_voucher(sv_id: int, deleted_by: str, reason: str):
    conn = get_connection()
    try:
        row = conn.execute("""
            SELECT sv.sv_number, sv.date, sv.total_amount,
                   COALESCE(c.name, sv.cash_customer_name, 'Cash') AS party_name,
                   sv.type, sv.payment_method,
                   sv.cash_paid, sv.bank_amount, sv.bank_account_id
            FROM sale_vouchers sv
            LEFT JOIN customers c ON c.id = sv.customer_id
            WHERE sv.id = ?
        """, (sv_id,)).fetchone()
        if not row:
            raise ValueError("Sale voucher not found")
        r = dict(row)

        lines = conn.execute("""
            SELECT sl.stock_item_id, sl.final_price, sv.customer_id, sv.type
            FROM sale_lines sl
            JOIN sale_vouchers sv ON sv.id = sl.sv_id
            WHERE sl.sv_id = ?
        """, (sv_id,)).fetchall()

        for line in lines:
            conn.execute(
                "UPDATE stock_items SET status='in_stock', sold_line_id=NULL WHERE id=?",
                (line["stock_item_id"],)
            )

        if r["type"] == "credit" and lines:
            total = r["total_amount"] or 0
            cust_id = lines[0]["customer_id"]
            conn.execute(
                "UPDATE customers SET opening_balance = opening_balance - ? WHERE id=?",
                (total, cust_id)
            )

        pm = r["payment_method"]
        total = r["total_amount"] or 0
        cash_amt = r["cash_paid"] or 0
        bank_amt = r["bank_amount"] or 0
        bank_acct_id = r["bank_account_id"]
        if pm == "cash":
            conn.execute(
                "UPDATE settings SET value = CAST(CAST(value AS REAL) - ? AS TEXT) WHERE key='cash_opening_balance'",
                (total,)
            )
        elif pm == "bank":
            if bank_acct_id:
                conn.execute(
                    "UPDATE bank_accounts SET opening_balance = opening_balance - ? WHERE id=?",
                    (total, bank_acct_id)
                )
        elif pm == "split":
            conn.execute(
                "UPDATE settings SET value = CAST(CAST(value AS REAL) - ? AS TEXT) WHERE key='cash_opening_balance'",
                (cash_amt,)
            )
            if bank_acct_id:
                conn.execute(
                    "UPDATE bank_accounts SET opening_balance = opening_balance - ? WHERE id=?",
                    (bank_amt, bank_acct_id)
                )

        conn.execute("DELETE FROM sale_lines WHERE sv_id=?", (sv_id,))
        conn.execute("DELETE FROM sale_vouchers WHERE id=?", (sv_id,))

        purge_after = (date.today() + timedelta(days=15)).strftime("%Y-%m-%d")
        conn.execute("""
            INSERT INTO deleted_vouchers
                (voucher_number, voucher_type, voucher_date, amount, party_name,
                 deleted_by, deleted_at, reason, purge_after)
            VALUES (?,?,?,?,?,?,date('now'),?,?)
        """, (r["sv_number"], "sale", r["date"], r["total_amount"],
              r["party_name"], deleted_by, reason, purge_after))

        conn.commit()
    finally:
        conn.close()


def db_delete_purchase_voucher(pv_id: int, deleted_by: str, reason: str):
    conn = get_connection()
    try:
        row = conn.execute("""
            SELECT pv.pv_number, pv.date, pv.total_amount,
                   pv.purchase_type, pv.cash_amount, pv.bank_amount, pv.bank_account_id,
                   s.name AS party_name
            FROM purchase_vouchers pv
            LEFT JOIN suppliers s ON s.id = pv.supplier_id
            WHERE pv.id = ?
        """, (pv_id,)).fetchone()
        if not row:
            raise ValueError("Purchase voucher not found")
        r = dict(row)

        lines = conn.execute("""
            SELECT si.id AS stock_item_id, si.status, si.imei,
                   pl.purchase_price, pv.supplier_id
            FROM purchase_lines pl
            JOIN purchase_vouchers pv ON pv.id = pl.pv_id
            LEFT JOIN stock_items si ON si.purchase_line_id = pl.id
            WHERE pl.pv_id = ?
        """, (pv_id,)).fetchall()

        sold_imeis = [line["imei"] for line in lines if line["status"] == "sold"]
        if sold_imeis:
            imei_list = "\n".join(f"- {imei}" for imei in sold_imeis)
            raise ValueError(
                f"Cannot delete {r['pv_number']}. The following IMEIs have already been "
                f"sold — delete the sale vouchers first:\n{imei_list}"
            )

        for line in lines:
            if line["stock_item_id"]:
                db_remove_stock_item(conn, line["stock_item_id"])

        if lines:
            total = r["total_amount"] or 0
            sup_id = lines[0]["supplier_id"]
            if sup_id:
                conn.execute(
                    "UPDATE suppliers SET opening_balance = opening_balance - ? WHERE id=?",
                    (total, sup_id)
                )

        # Reverse cash/bank outflow recorded at purchase time
        ptype = (r.get("purchase_type") or "").strip().lower()
        if ptype == "cash":
            cash_amt = float(r.get("cash_amount") or 0)
            bank_amt = float(r.get("bank_amount") or 0)
            bank_acct_id = r.get("bank_account_id")
            if cash_amt > 0:
                conn.execute(
                    "UPDATE settings SET value = CAST(CAST(value AS REAL) + ? AS TEXT) "
                    "WHERE key='cash_opening_balance'",
                    (cash_amt,)
                )
            if bank_amt > 0 and bank_acct_id:
                conn.execute(
                    "UPDATE bank_accounts SET opening_balance = opening_balance + ? WHERE id=?",
                    (bank_amt, bank_acct_id)
                )
                conn.execute(
                    "DELETE FROM bank_transactions WHERE voucher_number=?",
                    (r["pv_number"],)
                )

        conn.execute("DELETE FROM purchase_lines WHERE pv_id=?", (pv_id,))
        conn.execute("DELETE FROM purchase_vouchers WHERE id=?", (pv_id,))

        purge_after = (date.today() + timedelta(days=15)).strftime("%Y-%m-%d")
        conn.execute("""
            INSERT INTO deleted_vouchers
                (voucher_number, voucher_type, voucher_date, amount, party_name,
                 deleted_by, deleted_at, reason, purge_after)
            VALUES (?,?,?,?,?,?,date('now'),?,?)
        """, (r["pv_number"], "purchase", r["date"], r["total_amount"],
              r["party_name"], deleted_by, reason, purge_after))

        conn.commit()
    finally:
        conn.close()


def db_delete_sale_return(sr_id: int, deleted_by: str, reason: str):
    conn = get_connection()
    try:
        row = conn.execute("""
            SELECT sr.sr_number, sr.date, c.name AS party_name, sr.customer_id
            FROM sale_returns sr
            LEFT JOIN customers c ON c.id = sr.customer_id
            WHERE sr.id = ?
        """, (sr_id,)).fetchone()
        if not row:
            raise ValueError("Sale return not found")
        r = dict(row)

        lines = conn.execute(
            "SELECT stock_item_id, return_price FROM sale_return_lines WHERE sr_id=?",
            (sr_id,)
        ).fetchall()

        total = sum((line["return_price"] or 0) for line in lines)

        for line in lines:
            conn.execute(
                "UPDATE stock_items SET status='sold' WHERE id=?",
                (line["stock_item_id"],)
            )

        if r["customer_id"]:
            conn.execute(
                "UPDATE customers SET opening_balance = opening_balance + ? WHERE id=?",
                (total, r["customer_id"])
            )

        conn.execute("DELETE FROM sale_return_lines WHERE sr_id=?", (sr_id,))
        conn.execute("DELETE FROM sale_returns WHERE id=?", (sr_id,))

        purge_after = (date.today() + timedelta(days=15)).strftime("%Y-%m-%d")
        conn.execute("""
            INSERT INTO deleted_vouchers
                (voucher_number, voucher_type, voucher_date, amount, party_name,
                 deleted_by, deleted_at, reason, purge_after)
            VALUES (?,?,?,?,?,?,date('now'),?,?)
        """, (r["sr_number"], "sale_return", r["date"], total,
              r["party_name"], deleted_by, reason, purge_after))

        conn.commit()
    finally:
        conn.close()


def db_delete_purchase_return(pr_id: int, deleted_by: str, reason: str):
    conn = get_connection()
    try:
        row = conn.execute("""
            SELECT pr.pr_number, pr.date, s.name AS party_name, pr.supplier_id
            FROM purchase_returns pr
            LEFT JOIN suppliers s ON s.id = pr.supplier_id
            WHERE pr.id = ?
        """, (pr_id,)).fetchone()
        if not row:
            raise ValueError("Purchase return not found")
        r = dict(row)

        lines = conn.execute("""
            SELECT prl.stock_item_id, prl.model_id, prl.imei, prl.return_price
            FROM purchase_return_lines prl
            WHERE prl.pr_id = ?
        """, (pr_id,)).fetchall()

        total = sum((line["return_price"] or 0) for line in lines)

        # Restore stock items using data from the return lines
        for line in lines:
            conn.execute("""
                INSERT INTO stock_items (model_id, imei, purchase_price, status)
                VALUES (?, ?, ?, 'in_stock')
            """, (line["model_id"], line["imei"], line["return_price"] or 0))

        if r["supplier_id"]:
            conn.execute(
                "UPDATE suppliers SET opening_balance = opening_balance + ? WHERE id=?",
                (total, r["supplier_id"])
            )

        conn.execute("DELETE FROM purchase_return_lines WHERE pr_id=?", (pr_id,))
        conn.execute("DELETE FROM purchase_returns WHERE id=?", (pr_id,))

        purge_after = (date.today() + timedelta(days=15)).strftime("%Y-%m-%d")
        conn.execute("""
            INSERT INTO deleted_vouchers
                (voucher_number, voucher_type, voucher_date, amount, party_name,
                 deleted_by, deleted_at, reason, purge_after)
            VALUES (?,?,?,?,?,?,date('now'),?,?)
        """, (r["pr_number"], "purchase_return", r["date"], total,
              r["party_name"], deleted_by, reason, purge_after))

        conn.commit()
    finally:
        conn.close()


def prompt_and_delete_voucher(parent_widget, voucher_type: str, voucher_id: int,
                               voucher_number: str, deleted_by: str) -> bool:
    from PyQt6.QtWidgets import QInputDialog, QMessageBox, QLineEdit

    if not confirm_owner_pin(parent_widget):
        QMessageBox.warning(parent_widget, "Access Denied", "Incorrect Owner PIN.")
        return False

    reason, ok = QInputDialog.getText(
        parent_widget, "Delete Reason",
        f"Reason for deleting {voucher_number}:"
    )
    if not ok or not reason.strip():
        return False

    reply = QMessageBox.question(
        parent_widget, "Confirm Delete",
        f"Permanently delete {voucher_number}?\n\nThis cannot be undone.",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    if reply != QMessageBox.StandardButton.Yes:
        return False

    try:
        if voucher_type == "sale":
            db_delete_sale_voucher(voucher_id, deleted_by, reason.strip())
        elif voucher_type == "purchase":
            db_delete_purchase_voucher(voucher_id, deleted_by, reason.strip())
        elif voucher_type == "sale_return":
            db_delete_sale_return(voucher_id, deleted_by, reason.strip())
        elif voucher_type == "purchase_return":
            db_delete_purchase_return(voucher_id, deleted_by, reason.strip())
        else:
            raise ValueError(f"Unknown voucher_type: {voucher_type}")
        QMessageBox.information(parent_widget, "Deleted", f"{voucher_number} deleted successfully.")
        return True
    except Exception as e:
        QMessageBox.critical(parent_widget, "Error", f"Delete failed:\n{e}")
        return False


if __name__ == "__main__":
    init_db()
    print(f"Database initialised at: {DB_PATH}")
