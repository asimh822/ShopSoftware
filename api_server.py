"""
United Mobile EPOS — Flask API Server
Runs alongside the desktop app and connects to the same SQLite database.
Start with:  python api_server.py
Default port: 5000
"""

import os
import sqlite3
import threading
import time
import traceback
import uuid
from datetime import date as _date, timedelta
from functools import wraps

from flask import Flask, request, jsonify
from flask_cors import CORS

try:
    from supabase_sync import run_sync as _run_supabase_sync
    _SUPABASE_AVAILABLE = True
except ImportError:
    _SUPABASE_AVAILABLE = False

# ── Database path — same resolution as main.py / database.py ─────────────────
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "united_mobile.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


# ── Bootstrap: run all DB migrations, then ensure sessions table exists ──────
from database import init_db as _init_db
_init_db()


def _init_sessions():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            token        TEXT UNIQUE NOT NULL,
            salesman_id  INTEGER NOT NULL,
            created_date TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


_init_sessions()

# ── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)   # allow all origins — restrict in production if needed


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _validate_token(token: str):
    """Return salesman row if token is valid, else None."""
    if not token:
        return None
    conn = get_conn()
    row = conn.execute("""
        SELECT s.id, s.name, s.active
        FROM sessions ss
        JOIN salesmen s ON s.id = ss.salesman_id
        WHERE ss.token = ?
    """, (token,)).fetchone()
    conn.close()
    if row and row["active"]:
        return dict(row)
    return None


def require_auth(f):
    """Decorator: validates Authorization header token for protected routes."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        token = auth.removeprefix("Bearer ").strip() if auth else ""
        salesman = _validate_token(token)
        if not salesman:
            return jsonify({"success": False, "error": "Unauthorized — invalid or missing token"}), 401
        request.salesman = salesman
        return f(*args, **kwargs)
    return decorated


def _fmt_pkr(val):
    if val is None:
        return 0.0
    return round(float(val), 2)


# ═════════════════════════════════════════════════════════════════════════════
# PUBLIC ENDPOINTS (no auth)
# ═════════════════════════════════════════════════════════════════════════════

@app.route("/api/ping", methods=["GET"])
def api_ping():
    """Public health-check endpoint — no auth required."""
    return jsonify({"success": True, "message": "United Mobile EPOS API is running"})


@app.route("/api/health", methods=["GET"])
def api_health():
    """Public health endpoint — no auth required. Used by mobile app Test Connection."""
    return jsonify({"status": "ok", "message": "United Mobile API is running"})


@app.route("/api/login", methods=["POST"])
def api_login():
    """
    POST { pin: "1234" }
    Returns { success, token, salesman: { id, name } }
    """
    data = request.get_json(force=True, silent=True) or {}
    pin = str(data.get("pin", "")).strip()

    if not pin:
        return jsonify({"success": False, "error": "PIN is required"}), 400

    conn = get_conn()
    salesman = conn.execute(
        "SELECT id, name FROM salesmen WHERE pin=? AND active=1", (pin,)
    ).fetchone()

    if not salesman:
        conn.close()
        return jsonify({"success": False, "error": "Invalid PIN"})

    token = str(uuid.uuid4())
    today = _date.today().strftime("%d/%m/%Y")

    # Prune sessions older than 30 days so the table can't grow unbounded.
    cutoff_iso = (_date.today() - timedelta(days=30)).strftime("%Y-%m-%d")
    conn.execute(
        "DELETE FROM sessions WHERE "
        "substr(created_date,7,4)||'-'||substr(created_date,4,2)||'-'||substr(created_date,1,2) < ?",
        (cutoff_iso,),
    )

    conn.execute(
        "INSERT INTO sessions (token, salesman_id, created_date) VALUES (?,?,?)",
        (token, salesman["id"], today),
    )
    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "token": token,
        "salesman": {
            "id": salesman["id"],
            "name": salesman["name"],
        },
    })


# ═════════════════════════════════════════════════════════════════════════════
# STOCK
# Returns flat list: { stock: [{ brand, model, model_id, imei, reference_price }] }
# ═════════════════════════════════════════════════════════════════════════════

@app.route("/api/stock", methods=["GET"])
@require_auth
def api_stock():
    search = (request.args.get("search") or "").strip()
    conn = get_conn()

    sql = """
        SELECT b.name brand, m.name model, m.id model_id,
               TRIM(si.imei) imei, m.reference_price
        FROM stock_items si
        JOIN models m ON m.id = si.model_id
        JOIN brands b ON b.id = m.brand_id
        WHERE si.status = 'in_stock'
    """
    params = []
    if search:
        like_contains = f"%{search}%"
        like_suffix   = f"%{search}"
        sql += " AND (b.name LIKE ? OR m.name LIKE ? OR TRIM(si.imei) LIKE ?)"
        params.extend([like_contains, like_contains, like_suffix])
    sql += " ORDER BY b.name, m.name, TRIM(si.imei)"

    print(f"[DEBUG /api/stock] search={repr(search)!r}  SQL={sql.strip()[:120]}  params={params}")
    rows = conn.execute(sql, params).fetchall()
    print(f"[DEBUG /api/stock] rows returned: {len(rows)}")
    conn.close()

    stock_list = [
        {
            "brand": r["brand"],
            "model": r["model"],
            "model_id": r["model_id"],
            "imei": r["imei"],
            "reference_price": _fmt_pkr(r["reference_price"]),
        }
        for r in rows
    ]
    print(f"[DEBUG /api/stock] sample (first 3): {stock_list[:3]}")

    return jsonify({
        "success": True,
        "stock": stock_list,
    })


# ═════════════════════════════════════════════════════════════════════════════
# IMEI SEARCH
# Returns: { results: [{ imei, brand, model, reference_price, stock_item_id, model_id }] }
# ═════════════════════════════════════════════════════════════════════════════

@app.route("/api/imei/search", methods=["GET"])
@require_auth
def api_imei_search():
    digits = (request.args.get("digits") or "").strip()
    if not digits:
        return jsonify({"success": False, "error": "digits param required"}), 400

    conn = get_conn()
    rows = conn.execute("""
        SELECT TRIM(si.imei) imei, b.name brand, m.name model,
               m.reference_price, si.id stock_item_id, m.id model_id,
               si.purchase_price
        FROM stock_items si
        JOIN models m ON m.id = si.model_id
        JOIN brands b ON b.id = m.brand_id
        WHERE TRIM(si.imei) LIKE ? AND si.status = 'in_stock'
        ORDER BY TRIM(si.imei)
        LIMIT 10
    """, (f"%{digits}",)).fetchall()
    conn.close()

    return jsonify({
        "success": True,
        "results": [
            {
                "imei": r["imei"],
                "brand": r["brand"],
                "model": r["model"],
                "reference_price": _fmt_pkr(r["reference_price"]),
                "purchase_price": _fmt_pkr(r["purchase_price"]),
                "stock_item_id": r["stock_item_id"],
                "model_id": r["model_id"],
            }
            for r in rows
        ],
    })


# ═════════════════════════════════════════════════════════════════════════════
# CUSTOMERS SEARCH
# Returns: { found: true, customer: { id, name, balance } } for credit
#          { found: true, customer: { id: null, name, balance: null } } for cash
#          { found: false }
# ═════════════════════════════════════════════════════════════════════════════

@app.route("/api/customers/search", methods=["GET"])
@require_auth
def api_customers_search():
    phone = (request.args.get("phone") or "").strip()
    if not phone:
        return jsonify({"success": False, "error": "phone param required"}), 400

    conn = get_conn()

    # ── 1. Check credit customers first ───────────────────────────────────────
    customer = conn.execute(
        "SELECT id, name, contact, opening_balance FROM customers WHERE contact=? AND type='credit'",
        (phone,)
    ).fetchone()

    if customer:
        bal_row = conn.execute("""
            SELECT
                COALESCE(c.opening_balance, 0)
                + COALESCE((SELECT SUM(sv.total_amount) FROM sale_vouchers sv WHERE sv.customer_id=c.id AND sv.type='credit'), 0)
                - COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.party_type='customer' AND p.party_id=c.id AND p.type='CR'), 0)
                + COALESCE((SELECT SUM(je.amount) FROM journal_entries je WHERE je.party_type='customer' AND je.party_id=c.id AND je.type='debit'), 0)
                - COALESCE((SELECT SUM(je.amount) FROM journal_entries je WHERE je.party_type='customer' AND je.party_id=c.id AND je.type='credit'), 0)
                AS balance
            FROM customers c WHERE c.id=?
        """, (customer["id"],)).fetchone()
        balance = _fmt_pkr(bal_row["balance"]) if bal_row else 0.0

        # Last purchase for this credit customer
        last = conn.execute("""
            SELECT sv.date, b.name brand, m.name model, sl.final_price
            FROM sale_vouchers sv
            JOIN sale_lines sl ON sl.sv_id = sv.id
            JOIN models m ON m.id = sl.model_id
            JOIN brands b ON b.id = m.brand_id
            WHERE sv.customer_id = ?
            ORDER BY sv.id DESC LIMIT 1
        """, (customer["id"],)).fetchone()
        conn.close()

        last_sale = None
        if last:
            last_sale = {
                "model": f"{last['brand']} {last['model']}",
                "date": last["date"],
                "amount": _fmt_pkr(last["final_price"]),
            }

        return jsonify({
            "success": True,
            "found": True,
            "customer": {
                "id": customer["id"],
                "name": customer["name"],
                "contact": customer["contact"],
                "balance": balance,
                "last_sale": last_sale,
            },
        })

    # ── 2. Not a credit customer — check past cash sales by this phone ────────
    cash_row = conn.execute("""
        SELECT sv.cash_customer_name, b.name brand, m.name model,
               sl.final_price, sv.date
        FROM sale_vouchers sv
        JOIN sale_lines sl ON sl.sv_id = sv.id
        JOIN models m ON m.id = sl.model_id
        JOIN brands b ON b.id = m.brand_id
        WHERE sv.type = 'cash' AND sv.cash_customer_contact = ?
        ORDER BY sv.id DESC LIMIT 1
    """, (phone,)).fetchone()
    conn.close()

    if cash_row:
        return jsonify({
            "success": True,
            "found": True,
            "customer": {
                "id": None,
                "name": cash_row["cash_customer_name"],
                "contact": phone,
                "balance": None,
                "last_sale": {
                    "model": f"{cash_row['brand']} {cash_row['model']}",
                    "date": cash_row["date"],
                    "amount": _fmt_pkr(cash_row["final_price"]),
                },
            },
        })

    return jsonify({"success": True, "found": False})


# ═════════════════════════════════════════════════════════════════════════════
# SUPPLIERS
# Returns: { suppliers: [{ id, name, contact, balance }] }
# ═════════════════════════════════════════════════════════════════════════════

@app.route("/api/suppliers", methods=["GET"])
@require_auth
def api_suppliers():
    conn = get_conn()
    rows = conn.execute("""
        SELECT s.id, s.name, s.contact,
               COALESCE(s.opening_balance, 0)
               + COALESCE((SELECT SUM(pv.total_amount) FROM purchase_vouchers pv WHERE pv.supplier_id=s.id), 0)
               - COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.party_type='supplier' AND p.party_id=s.id AND p.type='CP'), 0)
               + COALESCE((SELECT SUM(je.amount) FROM journal_entries je WHERE je.party_type='supplier' AND je.party_id=s.id AND je.type='debit'), 0)
               - COALESCE((SELECT SUM(je.amount) FROM journal_entries je WHERE je.party_type='supplier' AND je.party_id=s.id AND je.type='credit'), 0)
               AS balance
        FROM suppliers s
        ORDER BY s.name
    """).fetchall()
    conn.close()
    return jsonify({
        "success": True,
        "suppliers": [
            {"id": r["id"], "name": r["name"],
             "contact": r["contact"] or "", "balance": _fmt_pkr(r["balance"])}
            for r in rows
        ],
    })


# ═════════════════════════════════════════════════════════════════════════════
# CUSTOMERS LIST (credit customers only)
# Returns: { customers: [{ id, name, contact, balance }] }
# ═════════════════════════════════════════════════════════════════════════════

@app.route("/api/customers/list", methods=["GET"])
@require_auth
def api_customers_list():
    conn = get_conn()
    rows = conn.execute("""
        SELECT c.id, c.name, c.contact,
               COALESCE(c.opening_balance, 0)
               + COALESCE((SELECT SUM(sv.total_amount) FROM sale_vouchers sv WHERE sv.customer_id=c.id AND sv.type='credit'), 0)
               - COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.party_type='customer' AND p.party_id=c.id AND p.type='CR'), 0)
               + COALESCE((SELECT SUM(je.amount) FROM journal_entries je WHERE je.party_type='customer' AND je.party_id=c.id AND je.type='debit'), 0)
               - COALESCE((SELECT SUM(je.amount) FROM journal_entries je WHERE je.party_type='customer' AND je.party_id=c.id AND je.type='credit'), 0)
               AS balance
        FROM customers c
        WHERE c.type = 'credit'
        ORDER BY c.name
    """).fetchall()
    conn.close()
    return jsonify({
        "success": True,
        "customers": [
            {
                "id": r["id"],
                "name": r["name"],
                "contact": r["contact"] or "",
                "balance": _fmt_pkr(r["balance"]),
            }
            for r in rows
        ],
    })


# ═════════════════════════════════════════════════════════════════════════════
# BRANDS + MODELS
# Returns: { brands: [{ id, name, models: [{ id, name, reference_price }] }] }
# ═════════════════════════════════════════════════════════════════════════════

@app.route("/api/brands", methods=["GET"])
@require_auth
def api_brands():
    conn = get_conn()
    brands_rows = conn.execute("SELECT id, name FROM brands ORDER BY name").fetchall()
    result = []
    for b in brands_rows:
        models = conn.execute(
            "SELECT id, name, reference_price FROM models WHERE brand_id=? ORDER BY name",
            (b["id"],)
        ).fetchall()
        result.append({
            "id": b["id"],
            "name": b["name"],
            "models": [
                {"id": m["id"], "name": m["name"],
                 "reference_price": None if m["reference_price"] is None else _fmt_pkr(m["reference_price"])}
                for m in models
            ],
        })
    conn.close()
    return jsonify({"success": True, "brands": result})


# ═════════════════════════════════════════════════════════════════════════════
# POST /api/sale
# Payload: { type, date, salesman_id, customer_id?, cash_customer_name?,
#            cash_customer_contact?, discount, lines: [{imei, stock_item_id,
#            model_id, reference_price, final_price, discount}] }
# Returns: { success, sv_number }
# ═════════════════════════════════════════════════════════════════════════════

@app.route("/api/sale", methods=["POST"])
@require_auth
def api_sale():
    data = request.get_json(force=True, silent=True) or {}

    salesman_id           = data.get("salesman_id")
    sale_type             = data.get("type", "cash")
    customer_id           = data.get("customer_id")
    cash_customer_name    = (data.get("cash_customer_name") or "").strip().title()
    cash_customer_contact = (data.get("cash_customer_contact") or "").strip()
    date_str              = (data.get("date") or _date.today().strftime("%d/%m/%Y")).strip()
    note                  = (data.get("note") or "").strip()
    overall_discount      = float(data.get("discount") or 0)
    lines                 = data.get("lines") or []
    _pm = data.get("payment_method")
    payment_method        = _pm.strip() if _pm and _pm.strip() else None
    cash_paid             = float(data.get("cash_amount") or 0)
    bank_amount           = float(data.get("bank_amount") or 0)
    bank_ref              = (data.get("bank_ref") or "").strip()
    bank_account_id       = data.get("bank_account_id") or None

    if not lines:
        return jsonify({"success": False, "error": "At least one item is required"}), 400

    # Rule 1: validate IMEI format
    bad_imeis = [str(l.get("imei", "")).strip() for l in lines
                 if not (len(str(l.get("imei", "")).strip()) == 15
                         and str(l.get("imei", "")).strip().isdigit())]
    if bad_imeis:
        return jsonify({"success": False,
                        "error": f"IMEI must be exactly 15 digits: {', '.join(bad_imeis)}"}), 400

    # Rule 2: validate phone for cash sales
    if sale_type == "cash" and cash_customer_contact:
        if not (len(cash_customer_contact) == 11
                and cash_customer_contact.startswith("03")
                and cash_customer_contact.isdigit()):
            return jsonify({"success": False,
                            "error": "cash_customer_contact must be 11 digits starting with 03"}), 400

    conn = get_conn()
    try:
        c = conn.cursor()

        # Validate all IMEIs are in stock
        failed_imeis = []
        line_details = []
        for line in lines:
            imei        = str(line.get("imei", "")).strip()
            final_price = float(line.get("final_price") or 0)
            ref_price   = float(line.get("reference_price") or 0)
            line_disc   = float(line.get("discount") or 0)

            row = c.execute(
                "SELECT si.id, si.model_id FROM stock_items si "
                "WHERE TRIM(si.imei)=? AND si.status='in_stock'",
                (imei,)
            ).fetchone()
            if not row:
                failed_imeis.append(imei)
            else:
                line_details.append((row["id"], row["model_id"], imei,
                                     ref_price, line_disc, final_price))

        if failed_imeis:
            conn.close()
            return jsonify({
                "success": False,
                "error": f"These IMEIs are not available in stock: {', '.join(failed_imeis)}"
            }), 400

        # Generate SV number
        row = c.execute("SELECT value FROM settings WHERE key='last_sv_number'").fetchone()
        n = int(row["value"]) + 1 if row else 1
        c.execute("UPDATE settings SET value=? WHERE key='last_sv_number'", (str(n),))
        sv_number = f"SV-{n:04d}"

        subtotal     = sum(d[5] for d in line_details)
        total_amount = max(0.0, subtotal - overall_discount)

        c.execute("""
            INSERT INTO sale_vouchers
            (sv_number, type, customer_id, cash_customer_name, cash_customer_contact,
             date, total_amount, discount, note, whatsapp_sent, salesman_id,
             payment_method, cash_paid, bank_account_id, bank_amount, bank_ref)
            VALUES (?,?,?,?,?,?,?,?,?,0,?,?,?,?,?,?)
        """, (sv_number, sale_type, customer_id,
              cash_customer_name or None, cash_customer_contact or None,
              date_str, total_amount, overall_discount, note, salesman_id,
              payment_method, cash_paid, bank_account_id, bank_amount, bank_ref))
        sv_id = c.lastrowid

        for stock_item_id, model_id, imei, ref_price, line_disc, final_price in line_details:
            c.execute("""
                INSERT INTO sale_lines
                (sv_id, stock_item_id, model_id, imei, reference_price, discount, final_price)
                VALUES (?,?,?,?,?,?,?)
            """, (sv_id, stock_item_id, model_id, imei, ref_price, line_disc, final_price))
            sl_id = c.lastrowid
            c.execute(
                "UPDATE stock_items SET status='sold', sold_line_id=? WHERE id=?",
                (sl_id, stock_item_id)
            )

        conn.commit()
        conn.close()

        # Print thermal receipt on the shop PC. Never fails the API response —
        # the sale is already committed; we just surface print issues to the client.
        print_warning = None
        try:
            from receipt import print_receipt_headless
            ok, err = print_receipt_headless(sv_id)
            if not ok:
                print_warning = err
            print(f"[api_sale] receipt sv_id={sv_id} ok={ok} err={err!r}")
        except Exception as e:
            print_warning = str(e)
            print(f"[api_sale] receipt crash: {e}")

        return jsonify({"success": True, "sv_number": sv_number,
                        "print_warning": print_warning})

    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"success": False, "error": str(e)}), 500


# ═════════════════════════════════════════════════════════════════════════════
# POST /api/purchase
#
# Supplier purchase payload:
#   { purchase_type:"supplier", supplier_id, date, salesman_id, notes?,
#     lines: [{ imei, model_id, purchase_price }] }
#
# Cash purchase payload (walk-in seller, no supplier):
#   { purchase_type:"cash", egadget_ref, date, salesman_id,
#     payment_method:"cash"|"bank"|"split",
#     cash_amount, bank_amount, bank_account_id, bank_ref?,
#     lines: [{ imei, model_id, purchase_price }] }
#
# Returns: { success, pv_number }
# ═════════════════════════════════════════════════════════════════════════════

@app.route("/api/purchase", methods=["POST"])
@require_auth
def api_purchase():
    data = request.get_json(force=True, silent=True) or {}

    purchase_type = (data.get("purchase_type") or "supplier").strip().lower()
    salesman_id   = data.get("salesman_id")
    date_str      = (data.get("date") or _date.today().strftime("%d/%m/%Y")).strip()
    notes         = (data.get("notes") or "").strip()
    lines         = data.get("lines") or []

    if not lines:
        return jsonify({"success": False, "error": "At least one item is required"}), 400

    # Rule 1: validate IMEI format
    bad_imeis = [str(l.get("imei", "")).strip() for l in lines
                 if not (len(str(l.get("imei", "")).strip()) == 15
                         and str(l.get("imei", "")).strip().isdigit())]
    if bad_imeis:
        return jsonify({"success": False,
                        "error": f"IMEI must be exactly 15 digits: {', '.join(bad_imeis)}"}), 400

    # ── Validate by purchase type ─────────────────────────────────────────────
    if purchase_type == "supplier":
        supplier_id    = data.get("supplier_id")
        egadget_ref    = ""
        payment_method = ""
        cash_amount    = 0.0
        bank_amount    = 0.0
        bank_account_id = None
        bank_ref       = ""
        if not supplier_id:
            return jsonify({"success": False, "error": "supplier_id is required"}), 400

    elif purchase_type == "cash":
        supplier_id    = 0   # system 'Cash Purchase' supplier — id=0, never NULL
        egadget_ref    = (data.get("egadget_ref") or "").strip()
        payment_method = (data.get("payment_method") or "cash").strip().lower()
        cash_amount    = float(data.get("cash_amount") or 0)
        bank_amount    = float(data.get("bank_amount") or 0)
        bank_account_id = data.get("bank_account_id")
        bank_ref       = (data.get("bank_ref") or "").strip()

        if payment_method not in ("cash", "bank", "split"):
            return jsonify({"success": False,
                            "error": "payment_method must be cash, bank, or split"}), 400
        if payment_method in ("bank", "split") and not bank_account_id:
            return jsonify({"success": False,
                            "error": "bank_account_id is required for bank/split payments"}), 400
        # Split total validation
        if payment_method == "split":
            total_check = sum(float(ln.get("purchase_price") or 0) for ln in lines)
            if abs((cash_amount + bank_amount) - total_check) > 1:
                return jsonify({"success": False,
                    "error": f"Split: cash + bank ({cash_amount + bank_amount:.0f}) "
                             f"must equal total ({total_check:.0f})"}), 400
    else:
        return jsonify({"success": False,
                        "error": f"Invalid purchase_type: {purchase_type}"}), 400

    conn = get_conn()
    try:
        c = conn.cursor()

        # Validate no IMEI already in_stock (allow re-purchase of sold/returned)
        duplicate_imeis = []
        for line in lines:
            imei = str(line.get("imei", "")).strip()
            existing = c.execute(
                "SELECT id FROM stock_items WHERE TRIM(imei)=? AND status='in_stock'",
                (imei,)
            ).fetchone()
            if existing:
                duplicate_imeis.append(imei)

        if duplicate_imeis:
            conn.close()
            return jsonify({
                "success": False,
                "error": f"Already in stock: {', '.join(duplicate_imeis)}"
            }), 400

        # Generate PV number
        row = c.execute("SELECT value FROM settings WHERE key='last_pv_number'").fetchone()
        n = int(row["value"]) + 1 if row else 1
        c.execute("UPDATE settings SET value=? WHERE key='last_pv_number'", (str(n),))
        pv_number = f"PV-{n:04d}"

        total_amount = sum(float(ln.get("purchase_price") or 0) for ln in lines)

        # For cash/cash payment, cash_amount = full total
        if purchase_type == "cash" and payment_method == "cash":
            cash_amount = total_amount

        # Insert purchase voucher with all columns
        c.execute("""
            INSERT INTO purchase_vouchers
            (pv_number, supplier_id, date, total_amount, notes, salesman_id,
             purchase_type, egadget_ref, payment_method,
             cash_amount, bank_amount, bank_account_id, bank_ref)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (pv_number, supplier_id, date_str, total_amount, notes, salesman_id,
              purchase_type, egadget_ref, payment_method,
              cash_amount, bank_amount, bank_account_id, bank_ref))
        pv_id = c.lastrowid

        for line in lines:
            imei           = str(line.get("imei", "")).strip()
            model_id       = line.get("model_id")
            purchase_price = float(line.get("purchase_price") or 0)

            c.execute("""
                INSERT INTO purchase_lines
                (pv_id, model_id, imei, purchase_price)
                VALUES (?,?,?,?)
            """, (pv_id, model_id, imei, purchase_price))
            pl_id = c.lastrowid

            c.execute("""
                INSERT INTO stock_items
                (model_id, imei, purchase_line_id, purchase_price, status)
                VALUES (?,?,?,?,'in_stock')
            """, (model_id, imei, pl_id, purchase_price))

        # Cash purchase with bank payment — record bank outflow
        if purchase_type == "cash" and bank_amount > 0 and bank_account_id:
            c.execute("""
                INSERT INTO bank_transactions
                (voucher_number, type, bank_account_id, source, date, amount, notes)
                VALUES (?,?,?,?,?,?,?)
            """, (pv_number, "CR", bank_account_id, "cash_purchase",
                  date_str, float(bank_amount),
                  f"Cash Purchase — {pv_number} — {egadget_ref}"))

        conn.commit()
        conn.close()
        return jsonify({"success": True, "pv_number": pv_number})

    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"success": False, "error": str(e)}), 500


# ═════════════════════════════════════════════════════════════════════════════
# GET /api/salesman/today
# Returns: { success, units_sold, total_amount,
#            sales: [{ id, sv_number, type, customer_name, items, total_amount }] }
# ═════════════════════════════════════════════════════════════════════════════

@app.route("/api/salesman/today", methods=["GET"])
@require_auth
def api_salesman_today():
    salesman_id = request.args.get("salesman_id")
    if not salesman_id:
        return jsonify({"success": False, "error": "salesman_id param required"}), 400

    today = _date.today().strftime("%d/%m/%Y")
    conn = get_conn()

    sales_rows = conn.execute("""
        SELECT sv.id, sv.sv_number, sv.type, sv.total_amount, sv.date,
               COALESCE(c.name, sv.cash_customer_name, 'Walk-in') customer_name,
               sv.cash_customer_name,
               COUNT(sl.id) item_count
        FROM sale_vouchers sv
        LEFT JOIN customers c ON c.id = sv.customer_id
        LEFT JOIN sale_lines sl ON sl.sv_id = sv.id
        WHERE sv.salesman_id=? AND sv.date=?
        GROUP BY sv.id
        ORDER BY sv.id DESC
    """, (salesman_id, today)).fetchall()
    conn.close()

    units_sold   = sum(r["item_count"] for r in sales_rows)
    total_amount = sum(r["total_amount"] or 0 for r in sales_rows)

    return jsonify({
        "success": True,
        "today": today,
        "units_sold": units_sold,
        "total_amount": _fmt_pkr(total_amount),
        "sales": [
            {
                "id": r["id"],
                "sv_number": r["sv_number"],
                "type": r["type"],
                "customer_name": r["customer_name"],
                "cash_customer_name": r["cash_customer_name"],
                "items": r["item_count"],
                "total_amount": _fmt_pkr(r["total_amount"]),
            }
            for r in sales_rows
        ],
    })


# ═════════════════════════════════════════════════════════════════════════════
# GET /api/cash_in_hand
# Returns: { success, cash_in_hand: <amount> }
# Formula mirrors db_cash_book() in reports.py — all-time version (no date filter).
# ═════════════════════════════════════════════════════════════════════════════

@app.route("/api/cash_in_hand", methods=["GET"])
@require_auth
def api_cash_in_hand():
    print("[api] GET /api/cash_in_hand — hit")
    try:
        conn = get_conn()

        def _q(sql):
            return float(conn.execute(sql).fetchone()[0] or 0)

        ob_row = conn.execute(
            "SELECT value FROM settings WHERE key='cash_opening_balance'"
        ).fetchone()
        cash_ob = float(ob_row[0]) if ob_row and ob_row[0] else 0.0

        cash_in_hand = (
            cash_ob
            + _q("SELECT COALESCE(SUM(cash_paid),0) FROM sale_vouchers WHERE cash_paid>0")
            + _q("SELECT COALESCE(SUM(amount),0) FROM payments WHERE type='CR'")
            - _q("SELECT COALESCE(SUM(amount),0) FROM payments WHERE type='CP'")
            - _q("SELECT COALESCE(SUM(amount),0) FROM bank_transactions WHERE type='CP' AND source='cash_transfer'")
            + _q("SELECT COALESCE(SUM(amount),0) FROM bank_transactions WHERE type='CR' AND source='cash_transfer'")
            + _q("SELECT COALESCE(SUM(amount),0) FROM cash_journal_lines WHERE direction='in'")
            - _q("SELECT COALESCE(SUM(amount),0) FROM cash_journal_lines WHERE direction='out'")
            - _q("SELECT COALESCE(SUM(cash_amount),0) FROM purchase_vouchers WHERE purchase_type='cash' AND cash_amount>0")
            - _q("SELECT COALESCE(SUM(amount),0) FROM expenses WHERE payment_method='cash'")
        )

        conn.close()
        result = round(cash_in_hand, 2)
        print(f"[api] /api/cash_in_hand -> {result}")
        return jsonify({"success": True, "cash_in_hand": result})
    except Exception as exc:
        print(f"[api] /api/cash_in_hand ERROR: {exc}")
        return jsonify({"success": False, "error": str(exc)}), 500


# ═════════════════════════════════════════════════════════════════════════════
# GET /api/salesmen
# Returns: { success, salesmen: [{ id, name }] }  — active salesmen only
# ═════════════════════════════════════════════════════════════════════════════

@app.route("/api/salesmen", methods=["GET"])
@require_auth
def api_salesmen():
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, name FROM salesmen WHERE active=1 ORDER BY name"
    ).fetchall()
    conn.close()
    return jsonify({
        "success": True,
        "salesmen": [{"id": r["id"], "name": r["name"]} for r in rows],
    })


# ═════════════════════════════════════════════════════════════════════════════
# GET /api/bank-account
# Returns: { success, accounts: [{ id, name }] }
# ═════════════════════════════════════════════════════════════════════════════

@app.route("/api/bank-account", methods=["GET"])
@require_auth
def api_bank_account():
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, name FROM bank_accounts ORDER BY name"
    ).fetchall()
    conn.close()
    return jsonify({
        "success": True,
        "accounts": [{"id": r["id"], "name": r["name"]} for r in rows],
    })


# ═════════════════════════════════════════════════════════════════════════════
# OWNER HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def _verify_owner_pin() -> bool:
    """Return True if X-Owner-Pin header matches the stored owner_pin setting."""
    pin = request.headers.get("X-Owner-Pin", "").strip()
    if not pin:
        return False
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key='owner_pin'").fetchone()
    conn.close()
    return bool(row and row["value"] == pin)


def _calc_cash_in_hand(conn) -> float:
    """Compute running cash in hand — mirrors database.py db_cash_in_hand()."""
    ob_row = conn.execute(
        "SELECT value FROM settings WHERE key='cash_opening_balance'"
    ).fetchone()
    cash_ob = float(ob_row[0]) if ob_row and ob_row[0] else 0.0

    def _q(sql):
        return float(conn.execute(sql).fetchone()[0] or 0)

    return (
        cash_ob
        + _q("SELECT COALESCE(SUM(cash_paid),0) FROM sale_vouchers WHERE cash_paid>0")
        + _q("SELECT COALESCE(SUM(amount),0) FROM payments WHERE type='CR'")
        - _q("SELECT COALESCE(SUM(amount),0) FROM payments WHERE type='CP'")
        - _q("SELECT COALESCE(SUM(amount),0) FROM bank_transactions WHERE type='CP' AND source='cash_transfer'")
        + _q("SELECT COALESCE(SUM(amount),0) FROM bank_transactions WHERE type='CR' AND source='cash_transfer'")
        + _q("SELECT COALESCE(SUM(amount),0) FROM cash_journal_lines WHERE direction='in'")
        - _q("SELECT COALESCE(SUM(amount),0) FROM cash_journal_lines WHERE direction='out'")
        - _q("SELECT COALESCE(SUM(cash_amount),0) FROM purchase_vouchers WHERE purchase_type='cash' AND cash_amount>0")
        - _q("SELECT COALESCE(SUM(amount),0) FROM expenses WHERE payment_method='cash'")
    )


def _calc_bank_account_balance(conn, account_id: int) -> float:
    """Compute current balance for one bank account.

    Formula:
      opening_balance
      + sale_vouchers.bank_amount  (bank/split sales paid into this account)
      + payments CP (party=bank)   (cash deposited to bank via ledger)
      - payments CR (party=bank)   (cash withdrawn from bank via ledger)
      + journal_entries debit      (bank DR in JV = bank receives)
      - journal_entries credit     (bank CR in JV = bank pays)
    """
    ba = conn.execute(
        "SELECT opening_balance FROM bank_accounts WHERE id=?", (account_id,)
    ).fetchone()
    ob = float(ba["opening_balance"] or 0) if ba else 0.0

    sales = float(conn.execute(
        "SELECT COALESCE(SUM(bank_amount),0) FROM sale_vouchers "
        "WHERE bank_account_id=? AND bank_amount>0",
        (account_id,)
    ).fetchone()[0] or 0)

    cp = float(conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM payments "
        "WHERE party_type='bank' AND party_id=? AND type='CP'",
        (account_id,)
    ).fetchone()[0] or 0)

    cr = float(conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM payments "
        "WHERE party_type='bank' AND party_id=? AND type='CR'",
        (account_id,)
    ).fetchone()[0] or 0)

    jv_dr = float(conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM journal_entries "
        "WHERE party_type='bank' AND party_id=? AND type='debit'",
        (account_id,)
    ).fetchone()[0] or 0)

    jv_cr = float(conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM journal_entries "
        "WHERE party_type='bank' AND party_id=? AND type='credit'",
        (account_id,)
    ).fetchone()[0] or 0)

    return ob + sales + cp - cr + jv_dr - jv_cr


def _date_iso_to_dmy(iso_date):
    """Convert 'YYYY-MM-DD' → 'DD/MM/YYYY'. Returns None for falsy input."""
    if not iso_date:
        return None
    return f"{iso_date[8:10]}/{iso_date[5:7]}/{iso_date[:4]}"


# SQL expression: convert DD/MM/YYYY column to ISO YYYY-MM-DD for MAX() ordering
_DATE_TO_ISO = "substr(date,7,4)||'-'||substr(date,4,2)||'-'||substr(date,1,2)"


# ═════════════════════════════════════════════════════════════════════════════
# OWNER ENDPOINTS — X-Owner-Pin header required (no salesman token needed)
# ═════════════════════════════════════════════════════════════════════════════

@app.route("/api/owner/dashboard", methods=["GET"])
def api_owner_dashboard():
    if not _verify_owner_pin():
        return jsonify({"error": "Invalid PIN"}), 401

    today = _date.today().strftime("%d/%m/%Y")
    conn = get_conn()
    try:
        today_sales = float(conn.execute(
            "SELECT COALESCE(SUM(total_amount),0) FROM sale_vouchers WHERE date=?",
            (today,)
        ).fetchone()[0] or 0)

        today_purchases = float(conn.execute(
            "SELECT COALESCE(SUM(total_amount),0) FROM purchase_vouchers WHERE date=?",
            (today,)
        ).fetchone()[0] or 0)

        cash_in_hand = _calc_cash_in_hand(conn)

        bank_rows = conn.execute("SELECT id FROM bank_accounts").fetchall()
        bank_total = sum(_calc_bank_account_balance(conn, r["id"]) for r in bank_rows)

        today_profit = float(conn.execute("""
            SELECT COALESCE(SUM(sl.final_price - si.purchase_price), 0)
            FROM sale_lines sl
            JOIN sale_vouchers sv ON sv.id = sl.sv_id
            JOIN stock_items si ON si.id = sl.stock_item_id
            WHERE sv.date = ?
        """, (today,)).fetchone()[0] or 0)

        return jsonify({
            "today_sales_total":     round(today_sales, 2),
            "today_purchases_total": round(today_purchases, 2),
            "cash_in_hand":          round(cash_in_hand, 2),
            "bank_total":            round(bank_total, 2),
            "today_profit":          round(today_profit, 2),
        })
    finally:
        conn.close()


@app.route("/api/owner/today-sales", methods=["GET"])
def api_owner_today_sales():
    if not _verify_owner_pin():
        return jsonify({"error": "Invalid PIN"}), 401

    today = _date.today().strftime("%d/%m/%Y")
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT b.name brand, m.name model,
                   COUNT(*) quantity, COALESCE(SUM(sl.final_price), 0) revenue
            FROM sale_lines sl
            JOIN sale_vouchers sv ON sv.id = sl.sv_id
            JOIN models m ON m.id = sl.model_id
            JOIN brands b ON b.id = m.brand_id
            WHERE sv.date = ?
            GROUP BY b.name, m.name
            ORDER BY b.name, m.name
        """, (today,)).fetchall()

        brands_map = {}
        for r in rows:
            brand = r["brand"]
            if brand not in brands_map:
                brands_map[brand] = {
                    "brand": brand,
                    "models": [],
                    "brand_total_qty": 0,
                    "brand_total_revenue": 0.0,
                }
            rev = round(float(r["revenue"]), 2)
            brands_map[brand]["models"].append({
                "model": r["model"],
                "quantity": r["quantity"],
                "revenue": rev,
            })
            brands_map[brand]["brand_total_qty"] += r["quantity"]
            brands_map[brand]["brand_total_revenue"] = round(
                brands_map[brand]["brand_total_revenue"] + rev, 2
            )

        brands_list = list(brands_map.values())
        grand_qty     = sum(b["brand_total_qty"] for b in brands_list)
        grand_revenue = round(sum(b["brand_total_revenue"] for b in brands_list), 2)

        return jsonify({
            "brands": brands_list,
            "grand_total_qty": grand_qty,
            "grand_total_revenue": grand_revenue,
        })
    finally:
        conn.close()


@app.route("/api/owner/balances", methods=["GET"])
def api_owner_balances():
    if not _verify_owner_pin():
        return jsonify({"error": "Invalid PIN"}), 401

    conn = get_conn()
    try:
        # ── Suppliers (we owe them) ───────────────────────────────────────────
        sup_rows = conn.execute(
            "SELECT id, name, opening_balance FROM suppliers WHERE id != 0 ORDER BY name"
        ).fetchall()
        suppliers = []
        for s in sup_rows:
            ob = float(s["opening_balance"] or 0)
            pv = float(conn.execute(
                "SELECT COALESCE(SUM(total_amount),0) FROM purchase_vouchers WHERE supplier_id=?",
                (s["id"],)
            ).fetchone()[0] or 0)
            pr = float(conn.execute(
                "SELECT COALESCE(SUM(prl.return_price),0) "
                "FROM purchase_return_lines prl "
                "JOIN purchase_returns pr ON pr.id=prl.pr_id "
                "WHERE pr.supplier_id=?",
                (s["id"],)
            ).fetchone()[0] or 0)
            cp = float(conn.execute(
                "SELECT COALESCE(SUM(amount),0) FROM payments "
                "WHERE party_type='supplier' AND party_id=? AND type='CP'",
                (s["id"],)
            ).fetchone()[0] or 0)
            balance = ob + pv - pr - cp
            if abs(balance) < 0.01:
                continue
            last_iso = conn.execute(f"""
                SELECT MAX({_DATE_TO_ISO}) FROM (
                    SELECT date FROM purchase_vouchers WHERE supplier_id=?
                    UNION ALL SELECT date FROM purchase_returns WHERE supplier_id=?
                    UNION ALL SELECT date FROM payments
                              WHERE party_type='supplier' AND party_id=?
                )
            """, (s["id"], s["id"], s["id"])).fetchone()[0]
            suppliers.append({
                "id": s["id"],
                "name": s["name"],
                "balance": round(balance, 2),
                "last_transaction": _date_iso_to_dmy(last_iso),
            })

        # ── Customers (they owe us) ───────────────────────────────────────────
        cust_rows = conn.execute(
            "SELECT id, name, opening_balance FROM customers WHERE type='credit' ORDER BY name"
        ).fetchall()
        customers = []
        for c in cust_rows:
            ob = float(c["opening_balance"] or 0)
            sv = float(conn.execute(
                "SELECT COALESCE(SUM(total_amount),0) FROM sale_vouchers "
                "WHERE customer_id=? AND type='credit'",
                (c["id"],)
            ).fetchone()[0] or 0)
            sr = float(conn.execute(
                "SELECT COALESCE(SUM(srl.return_price),0) "
                "FROM sale_return_lines srl "
                "JOIN sale_returns sr ON sr.id=srl.sr_id "
                "WHERE sr.customer_id=?",
                (c["id"],)
            ).fetchone()[0] or 0)
            cr = float(conn.execute(
                "SELECT COALESCE(SUM(amount),0) FROM payments "
                "WHERE party_type='customer' AND party_id=? AND type='CR'",
                (c["id"],)
            ).fetchone()[0] or 0)
            balance = ob + sv - sr - cr
            if abs(balance) < 0.01:
                continue
            last_iso = conn.execute(f"""
                SELECT MAX({_DATE_TO_ISO}) FROM (
                    SELECT date FROM sale_vouchers WHERE customer_id=?
                    UNION ALL SELECT date FROM sale_returns WHERE customer_id=?
                    UNION ALL SELECT date FROM payments
                              WHERE party_type='customer' AND party_id=?
                )
            """, (c["id"], c["id"], c["id"])).fetchone()[0]
            customers.append({
                "id": c["id"],
                "name": c["name"],
                "balance": round(balance, 2),
                "last_transaction": _date_iso_to_dmy(last_iso),
            })

        # ── Bank accounts (ALL) ───────────────────────────────────────────────
        bank_rows = conn.execute(
            "SELECT id, name FROM bank_accounts ORDER BY name"
        ).fetchall()
        bank_accounts_list = []
        for ba in bank_rows:
            balance = _calc_bank_account_balance(conn, ba["id"])
            # Last transaction: payments + direct bank sales + journal entries
            last_iso = conn.execute(f"""
                SELECT MAX({_DATE_TO_ISO}) FROM (
                    SELECT date FROM payments WHERE party_type='bank' AND party_id=?
                    UNION ALL SELECT date FROM sale_vouchers
                              WHERE bank_account_id=? AND bank_amount > 0
                    UNION ALL SELECT date FROM journal_entries
                              WHERE party_type='bank' AND party_id=?
                )
            """, (ba["id"], ba["id"], ba["id"])).fetchone()[0]
            bank_accounts_list.append({
                "id": ba["id"],
                "name": ba["name"],
                "balance": round(balance, 2),
                "last_transaction": _date_iso_to_dmy(last_iso),
            })

        cash_in_hand = _calc_cash_in_hand(conn)

        return jsonify({
            "suppliers":     suppliers,
            "customers":     customers,
            "bank_accounts": bank_accounts_list,
            "cash_in_hand":  round(cash_in_hand, 2),
        })

    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500

    finally:
        conn.close()


# ═════════════════════════════════════════════════════════════════════════════
# Run
# ═════════════════════════════════════════════════════════════════════════════

def _sync_loop():
    """Background thread: sync to Supabase 30 s after startup, then every hour."""
    time.sleep(30)
    _run_supabase_sync()
    while True:
        time.sleep(3600)
        _run_supabase_sync()


if __name__ == "__main__":
    print("=" * 54)
    print("  United Mobile EPOS — API Server")
    print(f"  Database : {DB_PATH}")
    print("  Listening: http://0.0.0.0:5000")
    print("=" * 54)

    if _SUPABASE_AVAILABLE:
        _t = threading.Thread(target=_sync_loop, daemon=True)
        _t.start()
        print("  Supabase : sync thread started (first run in 30 s)")
    else:
        print("  Supabase : supabase_sync.py not found — sync disabled")

    app.run(host="0.0.0.0", port=5000, debug=False)
