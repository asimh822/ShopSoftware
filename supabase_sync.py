import os
import sys
import sqlite3
import requests
import json
from datetime import datetime

SUPABASE_URL = "https://amoojyfprkxlfonfokuq.supabase.co"

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_key() -> str:
    """
    The service key grants full admin access to the Supabase project, so it
    is never committed to source control. It is read from supabase_key.txt
    next to this script (gitignored; copy it along when deploying), falling
    back to the SUPABASE_SERVICE_KEY environment variable.
    """
    key_file = os.path.join(_BASE_DIR, "supabase_key.txt")
    try:
        with open(key_file, encoding="utf-8") as f:
            key = f.read().strip()
            if key:
                return key
    except OSError:
        pass
    return os.environ.get("SUPABASE_SERVICE_KEY", "")


SUPABASE_KEY = _load_key()

DB_PATH = os.path.join(_BASE_DIR, "united_mobile.db")


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
    "expenses",
]


# Remote deletes must remove child rows before their parents — Supabase
# enforces journal_voucher_lines.jv_id → journal_vouchers.id.
DELETE_ORDER = [
    "journal_voucher_lines",
    "journal_vouchers",
    "sale_lines",
    "sale_returns",
    "purchase_returns",
    "sale_vouchers",
    "stock_items",
    "purchase_vouchers",
    "payments",
    "journal_entries",
    "bank_transactions",
    "expenses",
    "models",
    "brands",
    "suppliers",
    "customers",
    "bank_accounts",
]


def push_deletions():
    """
    Push queued local deletions (sync_deletions tombstones, written by the
    AFTER DELETE triggers from db migration v21) to Supabase. A tombstone is
    removed only after the remote delete succeeds, so deletions survive
    offline periods and are retried on the next sync. Deleting a row that
    never reached Supabase is a harmless no-op.
    Returns (deleted_count, errors).
    """
    conn = _get_conn()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT id, table_name, row_id FROM sync_deletions ORDER BY id"
        ).fetchall()]
    except Exception:
        conn.close()
        return 0, []  # tombstone table absent — DB not migrated to v21 yet
    if not rows:
        conn.close()
        return 0, []

    by_table = {}
    for r in rows:
        by_table.setdefault(r["table_name"], []).append(r)

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Prefer": "return=minimal",
    }
    deleted = 0
    errors = []
    order = DELETE_ORDER + [t for t in by_table if t not in DELETE_ORDER]
    for table in order:
        entries = by_table.get(table)
        if not entries:
            continue
        for i in range(0, len(entries), 100):
            chunk = entries[i:i + 100]
            ids = ",".join(str(e["row_id"]) for e in chunk)
            try:
                resp = requests.delete(
                    f"{SUPABASE_URL}/rest/v1/{table}?id=in.({ids})",
                    headers=headers, timeout=30,
                )
            except Exception as e:
                errors.append(f"{table}: delete request failed ({e})")
                continue
            if resp.status_code in (200, 204):
                conn.executemany(
                    "DELETE FROM sync_deletions WHERE id=?",
                    [(e["id"],) for e in chunk],
                )
                conn.commit()
                deleted += len(chunk)
            else:
                errors.append(
                    f"{table}: delete failed ({resp.status_code}) {resp.text[:100]}"
                )
    conn.close()
    return deleted, errors


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
    # timeout matters: without it a network stall hangs the sync thread
    # forever and no sync ever runs again until the app is restarted
    response = requests.post(url, headers=headers, data=json.dumps(rows), timeout=60)
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
        return {"total_rows": 0, "tables_synced": [], "errors": ["SUPABASE_SERVICE_KEY not set"]}
    print(f"[Supabase Sync] Starting sync at {datetime.now().strftime('%H:%M:%S')}")
    since = get_last_sync_time()
    sync_time = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    total_rows = 0
    synced_tables = []
    errors = []

    # Push deletions FIRST so a row that was deleted and later re-created
    # with the same id ends up present (delete, then upsert re-adds it).
    deleted_rows, delete_errors = push_deletions()
    if deleted_rows:
        print(f"[Supabase Sync] Propagated {deleted_rows} deletion(s) to Supabase.")
        synced_tables.append(f"deletions({deleted_rows})")
    for e in delete_errors:
        print(f"[Supabase Sync] Deletion error: {e}")

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
        # Deletion failures do NOT block the watermark: their tombstones stay
        # in sync_deletions and are retried automatically on the next sync.
        update_last_sync_time(sync_time)
    all_errors = delete_errors + errors
    summary = ', '.join(synced_tables) if synced_tables else 'none'
    if all_errors:
        summary += " | ERRORS: " + "; ".join(all_errors)
    log_sync_to_supabase(summary, total_rows + deleted_rows)
    print(
        f"[Supabase Sync] Done. {total_rows} rows pushed, "
        f"{deleted_rows} deletions propagated."
    )
    return {"total_rows": total_rows, "deleted_rows": deleted_rows,
            "tables_synced": synced_tables, "errors": all_errors}


if __name__ == "__main__":
    _result = run_sync()
    print("SYNC_RESULT:" + json.dumps(_result))
    sys.exit(1 if _result["errors"] else 0)
