import os
import sys
import sqlite3
import requests
import json
from datetime import datetime

# SUPABASE_SERVICE_KEY must be set as a Windows environment variable on the
# shop PC (System Properties > Environment Variables) — it grants full admin
# access to the Supabase project and must never be committed to source control.
# A key was previously hardcoded here; treat it as compromised and rotate it
# in the Supabase dashboard, then set the env var to the new value.
SUPABASE_URL = "https://amoojyfprkxlfonfokuq.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "united_mobile.db")


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


TABLES = [
    "suppliers",
    "customers",
    "bank_accounts",
    "purchase_vouchers",
    "sale_vouchers",
    "sale_lines",
    "stock_items",
    "models",
    "brands",
    "payments",
    "journal_entries",
    "journal_vouchers",
    "journal_voucher_lines",
    "purchase_returns",
    "sale_returns",
    "bank_transactions",
    "cash_journal_lines",
    "expenses",
]


def get_last_sync_time():
    conn = _get_conn()
    row = conn.execute(
        "SELECT value FROM settings WHERE key = 'last_supabase_sync'"
    ).fetchone()
    conn.close()
    return row[0] if row else '2000-01-01 00:00:00'


def update_last_sync_time(sync_time):
    conn = _get_conn()
    conn.execute(
        "UPDATE settings SET value = ? WHERE key = 'last_supabase_sync'",
        (sync_time,)
    )
    conn.commit()
    conn.close()


def fetch_changed_rows(table, since):
    conn = _get_conn()
    rows = [dict(row) for row in conn.execute(
        f"SELECT * FROM {table} WHERE last_modified > ?", (since,)
    ).fetchall()]
    conn.close()
    return rows


def upsert_to_supabase(table, rows):
    if not rows:
        return 0
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    # Normalise last_modified to ISO 8601 for Supabase timestamps
    for row in rows:
        if row.get('last_modified'):
            row['last_modified'] = row['last_modified'].replace(' ', 'T') + 'Z'
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    response = requests.post(url, headers=headers, data=json.dumps(rows))
    if response.status_code not in (200, 201):
        raise RuntimeError(
            f"Upsert failed ({response.status_code}): {response.text[:200]}"
        )
    return len(rows)


def log_sync_to_supabase(tables_synced, rows_pushed):
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    url = f"{SUPABASE_URL}/rest/v1/sync_log"
    data = {
        "synced_at": datetime.utcnow().isoformat() + 'Z',
        "tables_synced": tables_synced,
        "rows_pushed": rows_pushed,
    }
    try:
        requests.post(url, headers=headers, data=json.dumps(data), timeout=10)
    except Exception as e:
        print(f"[Supabase Sync] Failed to write sync_log: {e}")


def run_sync():
    if not SUPABASE_KEY:
        print("[Supabase Sync] SUPABASE_SERVICE_KEY env var not set — sync skipped.")
        return
    print(f"[Supabase Sync] Starting sync at {datetime.now().strftime('%H:%M:%S')}")
    since = get_last_sync_time()
    sync_time = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    total_rows = 0
    synced_tables = []
    errors = []

    for table in TABLES:
        try:
            rows = fetch_changed_rows(table, since)
            pushed = upsert_to_supabase(table, rows)
            if pushed > 0:
                synced_tables.append(f"{table}({pushed})")
                total_rows += pushed
        except Exception as e:
            print(f"[Supabase Sync] Error syncing {table}: {e}")
            errors.append(f"{table}: {e}")

    # Only advance the watermark when every table succeeded. Advancing it
    # unconditionally would mean a table that errored this run (e.g. a
    # missing column, a transient network failure) has its changed rows
    # permanently skipped on every future sync, since fetch_changed_rows
    # only picks up rows newer than the watermark. Re-upserting already-
    # synced tables on the next run is harmless (merge-duplicates).
    if errors:
        print(
            f"[Supabase Sync] {len(errors)} table(s) failed — watermark NOT "
            f"advanced, all tables will be retried next sync."
        )
    else:
        update_last_sync_time(sync_time)
    summary = ', '.join(synced_tables) if synced_tables else 'none'
    if errors:
        summary += " | ERRORS: " + "; ".join(errors)
    log_sync_to_supabase(summary, total_rows)
    print(
        f"[Supabase Sync] Done. {total_rows} rows pushed "
        f"across {len(synced_tables)} tables."
    )
    return {"total_rows": total_rows, "tables_synced": synced_tables, "errors": errors}


if __name__ == "__main__":
    _result = run_sync()
    print("SYNC_RESULT:" + json.dumps(_result))
    sys.exit(1 if _result["errors"] else 0)
