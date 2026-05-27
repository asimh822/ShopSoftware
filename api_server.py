"""
United Mobile EPOS — Flask API Server
Runs alongside the desktop app and connects to the same SQLite database.
Start with:  python api_server.py
Default port: 5000
"""

import os
import sqlite3
import uuid
from datetime import date as _date
from functools import wraps

from flask import Flask, request, jsonify
from flask_cors import CORS

# ── Database path — same resolution as main.py / database.py ─────────────────
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "united_mobile.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


# ── Bootstrap: create sessions table if it doesn't exist ─────────────────────
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
               m.reference_price, si.id stock_item_id, m.id model_id
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
                - COALESCE((SELECT SUM(je.amount) FROM journal_entries je WHERE je.party_type='customer' AND je.party_id=c.id AND je.type='debit'), 0)
                + COALESCE((SELECT SUM(je.amount) FROM journal_entries je WHERE je.party_type='customer' AND je.party_id=c.id AND je.type='credit'), 0)
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
               - COALESCE((SELECT SUM(je.amount) FROM journal_entries je WHERE je.party_type='customer' AND je.party_id=c.id AND je.type='debit'), 0)
               + COALESCE((SELECT SUM(je.amount) FROM journal_entries je WHERE je.party_type='customer' AND je.party_id=c.id AND je.type='credit'), 0)
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
                 "reference_price": _fmt_pkr(m["reference_price"])}
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
    cash_customer_name    = (data.get("cash_customer_name") or "").strip()
    cash_customer_contact = (data.get("cash_customer_contact") or "").strip()
    date_str              = (data.get("date") or _date.today().strftime("%d/%m/%Y")).strip()
    note                  = (data.get("note") or "").strip()
    overall_discount      = float(data.get("discount") or 0)
    lines                 = data.get("lines") or []
    payment_method        = (data.get("payment_method") or "cash").strip()
    cash_paid             = float(data.get("cash_amount") or 0)
    bank_amount           = float(data.get("bank_amount") or 0)
    bank_ref              = (data.get("bank_ref") or "").strip()
    bank_account_id       = data.get("bank_account_id") or None

    if not lines:
        return jsonify({"success": False, "error": "At least one item is required"}), 400

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
        return jsonify({"success": True, "sv_number": sv_number})

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

        if not egadget_ref:
            return jsonify({"success": False,
                            "error": "egadget_ref is required for cash purchases"}), 400
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
            (pv_number, supplier_id, date, total_amount, notes,
             purchase_type, egadget_ref, payment_method,
             cash_amount, bank_amount, bank_account_id, bank_ref)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (pv_number, supplier_id, date_str, total_amount, notes,
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
# Run
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 54)
    print("  United Mobile EPOS — API Server")
    print(f"  Database : {DB_PATH}")
    print("  Listening: http://0.0.0.0:5000")
    print("=" * 54)
    app.run(host="0.0.0.0", port=5000, debug=False)
