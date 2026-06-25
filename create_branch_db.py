"""
create_branch_db.py — one-off utility (NOT part of the main app).

Creates a clean database for a new branch of United Mobile.

It produces `united_mobile_branch.db` in this folder with:
  • The FULL schema — every table/index/trigger copied exactly from the live
    united_mobile.db (read from its sqlite_master, so it always matches the
    real database including any migration-added columns/tables).
  • Brands and Models — copied over (the product catalogue is shared).
  • Settings — copied over as a reference starting point (the branch owner
    updates shop name/address/contact, opening balances and voucher counters
    manually after setup).
  • Everything else EMPTY — no salesmen, suppliers, customers, stock,
    transactions, vouchers or balances.

After running, copy `united_mobile_branch.db` to the branch PC and rename it
to `united_mobile.db`.

Usage:
    python create_branch_db.py
"""

import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE_DB = os.path.join(HERE, "united_mobile.db")
BRANCH_DB = os.path.join(HERE, "united_mobile_branch.db")

# Only these tables have their data carried over to the new branch.
COPY_TABLES = ["brands", "models", "settings"]


def main() -> int:
    # ── Safety checks ────────────────────────────────────────────────────────
    if not os.path.exists(SOURCE_DB):
        print(f"ERROR: source database not found:\n  {SOURCE_DB}")
        print("Run this script from the project folder that contains united_mobile.db.")
        return 1

    if os.path.exists(BRANCH_DB):
        print(f"ERROR: {os.path.basename(BRANCH_DB)} already exists:\n  {BRANCH_DB}")
        print("Delete or move it first, then re-run this script.")
        return 1

    # ── Build the branch database ────────────────────────────────────────────
    conn = sqlite3.connect(BRANCH_DB)
    try:
        # Foreign keys stay OFF during build so creation/copy order can't trip
        # referential checks. The app turns them back on at runtime.
        conn.execute("ATTACH DATABASE ? AS src", (SOURCE_DB,))

        # 1) Recreate the full schema exactly as it exists in the source DB.
        #    Tables first, then indexes, then triggers/views. sqlite internal
        #    objects (sqlite_sequence, auto-indexes) are skipped — they are
        #    recreated automatically as needed.
        schema_rows = conn.execute("""
            SELECT type, name, sql FROM src.sqlite_master
            WHERE sql IS NOT NULL
              AND name NOT LIKE 'sqlite_%'
            ORDER BY CASE type
                        WHEN 'table'   THEN 1
                        WHEN 'index'   THEN 2
                        WHEN 'trigger' THEN 3
                        WHEN 'view'    THEN 4
                        ELSE 5
                     END
        """).fetchall()

        table_count = 0
        for obj_type, name, sql in schema_rows:
            conn.execute(sql)
            if obj_type == "table":
                table_count += 1

        # 2) Copy catalogue + settings data. Everything else is left empty.
        copied = {}
        for table in COPY_TABLES:
            # Insert with explicit columns so it works regardless of column
            # ordering. SELECT * is safe here because schema is identical.
            conn.execute(f"INSERT INTO main.{table} SELECT * FROM src.{table}")
            copied[table] = conn.execute(
                f"SELECT COUNT(*) FROM main.{table}"
            ).fetchone()[0]

        conn.commit()
        conn.execute("DETACH DATABASE src")
    except Exception as exc:
        conn.rollback()
        conn.close()
        # Don't leave a half-built file behind.
        if os.path.exists(BRANCH_DB):
            os.remove(BRANCH_DB)
        print(f"ERROR: failed to build branch database: {exc}")
        return 1
    finally:
        try:
            conn.close()
        except Exception:
            pass

    # ── Confirmation ─────────────────────────────────────────────────────────
    print("=" * 60)
    print("  Branch database created successfully.")
    print("=" * 60)
    print(f"  File:     {BRANCH_DB}")
    print(f"  Schema:   {table_count} tables (copied exactly from united_mobile.db)")
    print(f"  Brands:   {copied['brands']} copied")
    print(f"  Models:   {copied['models']} copied")
    print(f"  Settings: {copied['settings']} copied (reference - update manually)")
    print("  All other tables are EMPTY (no salesmen, suppliers, customers,")
    print("  stock, transactions, vouchers or balances).")
    print("-" * 60)
    print("  Next steps on the branch PC:")
    print("    1. Copy united_mobile_branch.db to the branch PC.")
    print("    2. Rename it to united_mobile.db.")
    print("    3. In the app, review Settings: shop name/address/contact,")
    print("       bank/cash opening balances, and voucher number counters.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
