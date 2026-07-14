-- One-time Supabase schema cleanup — July 2026
-- Paste this into the Supabase dashboard SQL editor (project amoojyfprkxlfonfokuq)
-- and click Run. Safe to run more than once.

-- 1. Drop the dead table. The unified JV system (db v16+) stores cash lines
--    in journal_voucher_lines with party_type='cash'; nothing writes here
--    anymore, and local db migration v19 dropped it from SQLite too.
DROP TABLE IF EXISTS cash_journal_lines;

-- 2. purchase_returns / sale_returns: remote tables were created from an old
--    local schema. Without these columns the first real return entered at the
--    shop would fail to sync (unknown column in upsert payload).
ALTER TABLE purchase_returns ADD COLUMN IF NOT EXISTS pv_id bigint;
ALTER TABLE purchase_returns ADD COLUMN IF NOT EXISTS notes text;
ALTER TABLE sale_returns     ADD COLUMN IF NOT EXISTS sv_id bigint;
ALTER TABLE sale_returns     ADD COLUMN IF NOT EXISTS notes text;
