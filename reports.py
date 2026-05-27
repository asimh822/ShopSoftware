import csv
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QComboBox, QDateEdit,
    QHeaderView, QAbstractItemView, QFrame, QTabWidget,
    QFileDialog, QMessageBox, QLineEdit, QApplication,
    QScrollArea,
)
from PyQt6.QtCore import Qt, QDate, QTimer
from PyQt6.QtGui import QFont, QBrush, QColor

from database import get_connection

# ── Shared styles ─────────────────────────────────────────────────────────────

TABLE_STYLE = """
    QTableWidget {
        background:#ffffff; border:1px solid #e2e8f0;
        border-radius:6px; gridline-color:#f1f5f9; font-size:10pt;
    }
    QTableWidget::item { padding:6px 10px; }
    QTableWidget::item:selected { background:#dbeafe; color:#1e40af; }
    QTableWidget::item:alternate { background:#f8fafc; }
    QHeaderView::section {
        background:#f8fafc; color:#475569; font-weight:bold; font-size:9pt;
        border:none; border-bottom:1px solid #e2e8f0; padding:8px 10px;
    }
"""
BTN_PRIMARY = """
    QPushButton { background:#2563eb; color:white; border:none;
        border-radius:5px; padding:6px 16px; font-size:10pt; }
    QPushButton:hover { background:#1d4ed8; }
    QPushButton:disabled { background:#93c5fd; }
"""
BTN_SECONDARY = """
    QPushButton { background:#f1f5f9; color:#334155;
        border:1px solid #cbd5e1; border-radius:5px; padding:6px 16px; font-size:10pt; }
    QPushButton:hover { background:#e2e8f0; }
    QPushButton:disabled { color:#94a3b8; }
"""
BTN_TOGGLE_ON = """
    QPushButton { background:#2563eb; color:white; border:none;
        padding:6px 18px; font-size:10pt; font-weight:bold; }
"""
BTN_TOGGLE_OFF = """
    QPushButton { background:#f1f5f9; color:#64748b;
        border:1px solid #cbd5e1; padding:6px 18px; font-size:10pt; }
    QPushButton:hover { background:#e2e8f0; color:#334155; }
"""
CARD_STYLE = "background:#ffffff; border:1px solid #e2e8f0; border-radius:8px; color:#1e293b;"
TOTAL_STYLE = "color:#1e293b; font-size:10pt; font-weight:bold;"
BTN_COPY_SMALL = """
    QPushButton { background:#e0f2fe; color:#0284c7; border:none;
        border-radius:4px; padding:3px 8px; font-size:9pt; }
    QPushButton:hover { background:#bae6fd; }
"""
BTN_USE_SMALL = """
    QPushButton { background:#dcfce7; color:#15803d; border:none;
        border-radius:4px; padding:3px 8px; font-size:9pt; }
    QPushButton:hover { background:#bbf7d0; }
"""


def fmt_pkr(val):
    if val is None:
        return "0"
    return f"{float(val):,.0f}"


def _make_table(headers):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setAlternatingRowColors(True)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    t.horizontalHeader().setStretchLastSection(True)
    t.setStyleSheet(TABLE_STYLE)
    return t


def _filter_card(*widgets) -> QFrame:
    card = QFrame()
    card.setStyleSheet(CARD_STYLE)
    row = QHBoxLayout(card)
    row.setContentsMargins(12, 10, 12, 10)
    row.setSpacing(10)
    for w in widgets:
        if w is None:
            row.addStretch()
        else:
            row.addWidget(w)
    return card


def _date_expr(col):
    return f"substr({col},7,4)||'-'||substr({col},4,2)||'-'||substr({col},1,2)"


def _export_table_csv(table: QTableWidget, default_name: str, parent=None):
    path, _ = QFileDialog.getSaveFileName(
        parent, "Export CSV", default_name, "CSV Files (*.csv)"
    )
    if not path:
        return
    try:
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            headers = [
                table.horizontalHeaderItem(c).text()
                for c in range(table.columnCount())
            ]
            writer.writerow(headers)
            for row in range(table.rowCount()):
                writer.writerow([
                    (table.item(row, col).text() if table.item(row, col) else "")
                    for col in range(table.columnCount())
                ])
        QMessageBox.information(parent, "Exported", f"Saved to:\n{path}")
    except Exception as e:
        QMessageBox.critical(parent, "Export Failed", str(e))


# ── DB helpers ────────────────────────────────────────────────────────────────

def db_brands_list():
    conn = get_connection()
    rows = conn.execute("SELECT id, name FROM brands ORDER BY name").fetchall()
    conn.close()
    return rows


def db_models_list(brand_id=None):
    conn = get_connection()
    if brand_id:
        rows = conn.execute(
            "SELECT id, name FROM models WHERE brand_id=? ORDER BY name", (brand_id,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT id, name FROM models ORDER BY name").fetchall()
    conn.close()
    return rows


def db_suppliers_list():
    """Returns all real suppliers. Excludes id=0 (system 'Cash Purchase' record)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name FROM suppliers WHERE id != 0 ORDER BY name"
    ).fetchall()
    conn.close()
    return rows


def db_stock_report_grouped(brand_id=None):
    """Returns [(brand, model, qty), ...] for in-stock items, ordered by brand then model."""
    conds, params = ["si.status='in_stock'"], []
    if brand_id:
        conds.append("m.brand_id=?")
        params.append(brand_id)
    where = "WHERE " + " AND ".join(conds)
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT b.name brand, m.name model, COUNT(si.id) qty
        FROM stock_items si
        JOIN models m ON m.id = si.model_id
        JOIN brands b ON b.id = m.brand_id
        {where}
        GROUP BY si.model_id
        ORDER BY b.name, m.name
    """, params).fetchall()
    conn.close()
    return rows


def db_stock_valuation(brand_id=None):
    conds, params = ["si.status='in_stock'"], []
    if brand_id:
        conds.append("m.brand_id=?")
        params.append(brand_id)
    where = "WHERE " + " AND ".join(conds)
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT b.name brand, m.name model,
               COUNT(si.id) units, SUM(si.purchase_price) total_value
        FROM stock_items si
        JOIN models m ON m.id = si.model_id
        JOIN brands b ON b.id = m.brand_id
        {where}
        GROUP BY si.model_id
        ORDER BY b.name, m.name
    """, params).fetchall()
    conn.close()
    return rows


def db_stock_imei_report(search_text=None):
    """Individual in-stock IMEIs with purchase info and supplier, for the IMEI Stock report tab."""
    conds, params = ["si.status='in_stock'"], []
    if search_text:
        like = f"%{search_text}%"
        conds.append(
            "(b.name LIKE ? OR m.name LIKE ? OR TRIM(si.imei) LIKE ? OR s.name LIKE ?)"
        )
        params.extend([like, like, like, like])
    where = "WHERE " + " AND ".join(conds)
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT b.name brand, m.name model, TRIM(si.imei) imei,
               COALESCE(s.name, '—') supplier,
               COALESCE(pv.date, '') purchase_date, si.purchase_price
        FROM stock_items si
        JOIN models m ON m.id = si.model_id
        JOIN brands b ON b.id = m.brand_id
        LEFT JOIN purchase_lines pl ON pl.id = si.purchase_line_id
        LEFT JOIN purchase_vouchers pv ON pv.id = pl.pv_id
        LEFT JOIN suppliers s ON s.id = pv.supplier_id
        {where}
        ORDER BY b.name, m.name, TRIM(si.imei)
    """, params).fetchall()
    conn.close()
    return rows


def db_salesmen_for_filter():
    """All salesmen (active + inactive) for the sales report filter dropdown."""
    conn = get_connection()
    rows = conn.execute("SELECT id, name FROM salesmen ORDER BY name").fetchall()
    conn.close()
    return rows


def db_sales_report(from_iso=None, to_iso=None, sale_type=None, salesman_id=None):
    de = _date_expr("sv.date")
    conds, params = [], []
    if from_iso:
        conds.append(f"{de} >= ?")
        params.append(from_iso)
    if to_iso:
        conds.append(f"{de} <= ?")
        params.append(to_iso)
    if sale_type:
        conds.append("sv.type=?")
        params.append(sale_type)
    if salesman_id:
        conds.append("sv.salesman_id=?")
        params.append(salesman_id)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT sv.date, sv.sv_number,
               COALESCE(c.name, sv.cash_customer_name) customer,
               sv.type, COUNT(sl.id) items, sv.total_amount, sv.discount,
               COALESCE(sm.name, '—') salesman
        FROM sale_vouchers sv
        LEFT JOIN customers c ON c.id = sv.customer_id
        LEFT JOIN sale_lines sl ON sl.sv_id = sv.id
        LEFT JOIN salesmen sm ON sm.id = sv.salesman_id
        {where}
        GROUP BY sv.id
        ORDER BY {de} DESC
    """, params).fetchall()
    conn.close()
    return rows


def db_purchase_report(from_iso=None, to_iso=None, supplier_id=None,
                         purchase_type_filter=None):
    de = _date_expr("pv.date")
    conds, params = [], []
    if from_iso:
        conds.append(f"{de} >= ?")
        params.append(from_iso)
    if to_iso:
        conds.append(f"{de} <= ?")
        params.append(to_iso)
    if supplier_id:
        conds.append("pv.supplier_id=?")
        params.append(supplier_id)
    if purchase_type_filter == "supplier":
        conds.append("COALESCE(pv.purchase_type,'supplier') = 'supplier'")
    elif purchase_type_filter == "cash":
        conds.append("pv.purchase_type = 'cash'")
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT pv.date, pv.pv_number,
               COALESCE(s.name, 'Cash Purchase') supplier,
               COUNT(pl.id) items, pv.total_amount,
               COALESCE(pv.purchase_type, 'supplier') purchase_type,
               COALESCE(pv.egadget_ref, '') egadget_ref
        FROM purchase_vouchers pv
        LEFT JOIN suppliers s ON s.id = pv.supplier_id
        LEFT JOIN purchase_lines pl ON pl.pv_id = pv.id
        {where}
        GROUP BY pv.id
        ORDER BY {de} DESC
    """, params).fetchall()
    conn.close()
    return rows


def db_profit_report(from_iso=None, to_iso=None):
    de = _date_expr("sv.date")
    conds, params = ["si.status='sold'", "si.sold_line_id IS NOT NULL"], []
    if from_iso:
        conds.append(f"{de} >= ?")
        params.append(from_iso)
    if to_iso:
        conds.append(f"{de} <= ?")
        params.append(to_iso)
    where = "WHERE " + " AND ".join(conds)
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT sv.date date_sold, b.name brand, m.name model,
               si.imei, si.purchase_price, sl.final_price,
               (sl.final_price - si.purchase_price) profit
        FROM stock_items si
        JOIN models m ON m.id = si.model_id
        JOIN brands b ON b.id = m.brand_id
        JOIN sale_lines sl ON sl.id = si.sold_line_id
        JOIN sale_vouchers sv ON sv.id = sl.sv_id
        {where}
        ORDER BY {de} DESC
    """, params).fetchall()
    conn.close()
    return rows


def db_cash_book(date_str: str) -> dict:
    """
    Returns cash book data for a single date (DD/MM/YYYY).

    Returned dict keys:
        opening_cash, opening_bank,
        rows  — list of dicts: {date, voucher, description, cash_in, cash_out}
        total_cash_in, total_cash_out,
        total_bank_in, total_bank_out,
        closing_cash, closing_bank
    """
    dd, mm, yyyy = date_str.split("/")
    iso = f"{yyyy}-{mm}-{dd}"

    conn = get_connection()

    def _de(col):
        return f"substr({col},7,4)||'-'||substr({col},4,2)||'-'||substr({col},1,2)"

    def _q(sql, params=()):
        return float(conn.execute(sql, params).fetchone()[0] or 0)

    de_sv  = _de("sv.date")
    de_p   = _de("p.date")
    de_bt  = _de("bt.date")
    de_cjl = _de("cjl.date")

    # ── Opening Cash — all cash movements BEFORE iso ──────────────────────
    ob_row = conn.execute(
        "SELECT value FROM settings WHERE key='cash_opening_balance'"
    ).fetchone()
    cash_ob = float(ob_row[0]) if ob_row and ob_row[0] else 0.0

    de_pv = _de("pv.date")
    opening_cash = (
        cash_ob
        + _q(f"SELECT COALESCE(SUM(sv.cash_paid),0) FROM sale_vouchers sv"
             f" WHERE sv.cash_paid>0 AND {de_sv}<?", (iso,))
        + _q(f"SELECT COALESCE(SUM(p.amount),0) FROM payments p"
             f" WHERE p.type='CR' AND {de_p}<?", (iso,))
        - _q(f"SELECT COALESCE(SUM(p.amount),0) FROM payments p"
             f" WHERE p.type='CP' AND {de_p}<?", (iso,))
        - _q(f"SELECT COALESCE(SUM(bt.amount),0) FROM bank_transactions bt"
             f" WHERE bt.type='CP' AND bt.source='cash_transfer' AND {de_bt}<?", (iso,))
        + _q(f"SELECT COALESCE(SUM(bt.amount),0) FROM bank_transactions bt"
             f" WHERE bt.type='CR' AND bt.source='cash_transfer' AND {de_bt}<?", (iso,))
        + _q(f"SELECT COALESCE(SUM(cjl.amount),0) FROM cash_journal_lines cjl"
             f" WHERE cjl.direction='in' AND {de_cjl}<?", (iso,))
        - _q(f"SELECT COALESCE(SUM(cjl.amount),0) FROM cash_journal_lines cjl"
             f" WHERE cjl.direction='out' AND {de_cjl}<?", (iso,))
        - _q(f"SELECT COALESCE(SUM(pv.cash_amount),0) FROM purchase_vouchers pv"
             f" WHERE pv.purchase_type='cash' AND pv.cash_amount>0 AND {de_pv}<?", (iso,))
    )

    # ── Opening Bank — all bank movements BEFORE iso ──────────────────────
    bank_ob = _q("SELECT COALESCE(SUM(opening_balance),0) FROM bank_accounts")
    opening_bank = (
        bank_ob
        + _q(f"SELECT COALESCE(SUM(sv.bank_amount),0) FROM sale_vouchers sv"
             f" WHERE sv.bank_amount>0 AND {de_sv}<?", (iso,))
        + _q(f"SELECT COALESCE(SUM(bt.amount),0) FROM bank_transactions bt"
             f" WHERE bt.type='CP' AND {de_bt}<?", (iso,))
        - _q(f"SELECT COALESCE(SUM(bt.amount),0) FROM bank_transactions bt"
             f" WHERE bt.type='CR' AND {de_bt}<?", (iso,))
    )

    # ── Today's transaction rows ──────────────────────────────────────────
    rows = []

    # 1. Sale vouchers — cash / bank / split only (credit sales skip)
    sales = conn.execute(f"""
        SELECT sv.date, sv.sv_number, sv.payment_method,
               COALESCE(c.name, sv.cash_customer_name, 'Walk-in') customer,
               sv.total_amount, sv.cash_paid, sv.bank_amount
        FROM sale_vouchers sv
        LEFT JOIN customers c ON c.id = sv.customer_id
        WHERE {de_sv}=? AND sv.payment_method IN ('cash','bank','split')
        ORDER BY sv.sv_number
    """, (iso,)).fetchall()

    for s in sales:
        pm    = s["payment_method"]
        total = float(s["total_amount"] or 0)
        cash  = float(s["cash_paid"]   or 0)
        bank  = float(s["bank_amount"] or 0)
        cust  = s["customer"] or "Walk-in"
        sv_no = s["sv_number"]
        date  = s["date"]

        if pm == "cash":
            rows.append({"date": date, "voucher": sv_no,
                         "description": f"Cash Sale — {cust}",
                         "cash_in": cash, "cash_out": 0.0})

        elif pm == "bank":
            # Gross method: full amount in, full amount out to bank (net = 0)
            rows.append({"date": date, "voucher": sv_no,
                         "description": f"Bank Sale (Rcvd) — {cust}",
                         "cash_in": total, "cash_out": 0.0})
            rows.append({"date": date, "voucher": sv_no,
                         "description": f"Bank Sale (Dep) — {cust}",
                         "cash_in": 0.0, "cash_out": total})

        elif pm == "split":
            # Gross: full amount in, bank portion out (net = cash portion)
            rows.append({"date": date, "voucher": sv_no,
                         "description": f"Split Sale — {cust}",
                         "cash_in": total, "cash_out": bank})

    # 2. Payments (CP = cash out, CR = cash in)
    payments = conn.execute(f"""
        SELECT p.date, p.voucher_number, p.type, p.amount, p.party_type,
               COALESCE(s.name, c.name, '?') party_name
        FROM payments p
        LEFT JOIN suppliers s ON p.party_type='supplier' AND s.id=p.party_id
        LEFT JOIN customers c ON p.party_type='customer' AND c.id=p.party_id
        WHERE {de_p}=?
        ORDER BY p.voucher_number
    """, (iso,)).fetchall()

    for p in payments:
        name = p["party_name"]
        amt  = float(p["amount"] or 0)
        if p["type"] == "CP":
            rows.append({"date": p["date"], "voucher": p["voucher_number"],
                         "description": f"Payment — {name}",
                         "cash_in": 0.0, "cash_out": amt})
        else:  # CR
            rows.append({"date": p["date"], "voucher": p["voucher_number"],
                         "description": f"Receipt — {name}",
                         "cash_in": amt, "cash_out": 0.0})

    # 3. Bank transfers (source='cash_transfer' only — JV-only entries excluded)
    bank_txns = conn.execute(f"""
        SELECT bt.date, bt.voucher_number, bt.type, bt.amount,
               COALESCE(ba.name, 'Bank') bank_name
        FROM bank_transactions bt
        LEFT JOIN bank_accounts ba ON ba.id = bt.bank_account_id
        WHERE {de_bt}=? AND bt.source='cash_transfer'
        ORDER BY bt.voucher_number
    """, (iso,)).fetchall()

    for bt in bank_txns:
        bname = bt["bank_name"]
        amt   = float(bt["amount"] or 0)
        if bt["type"] == "CP":   # cash deposited → Cash Out
            rows.append({"date": bt["date"], "voucher": bt["voucher_number"],
                         "description": f"Cash Deposit → {bname}",
                         "cash_in": 0.0, "cash_out": amt})
        else:                    # CR = cash withdrawn → Cash In
            rows.append({"date": bt["date"], "voucher": bt["voucher_number"],
                         "description": f"Cash Withdrawal ← {bname}",
                         "cash_in": amt, "cash_out": 0.0})

    # 4. Cash purchases — walk-in seller purchases (no supplier)
    cash_purch = conn.execute(f"""
        SELECT pv.date, pv.pv_number,
               COALESCE(pv.payment_method, 'cash') payment_method,
               COALESCE(pv.egadget_ref, '') egadget_ref,
               COALESCE(pv.total_amount, 0) total_amount,
               COALESCE(pv.cash_amount,  0) cash_amount,
               COALESCE(pv.bank_amount,  0) bank_amount,
               COALESCE(ba.name, 'Bank') bank_name
        FROM purchase_vouchers pv
        LEFT JOIN bank_accounts ba ON ba.id = pv.bank_account_id
        WHERE pv.purchase_type = 'cash' AND {de_pv}=?
        ORDER BY pv.pv_number
    """, (iso,)).fetchall()

    for cp in cash_purch:
        pm    = cp["payment_method"]
        total = float(cp["total_amount"] or 0)
        camnt = float(cp["cash_amount"]  or 0)
        bamnt = float(cp["bank_amount"]  or 0)
        ref   = cp["egadget_ref"] or cp["pv_number"]
        pv_no = cp["pv_number"]
        date  = cp["date"]
        bname = cp["bank_name"]

        if pm == "cash":
            rows.append({"date": date, "voucher": pv_no,
                         "description": f"Cash Purchase (Cash) — {ref}",
                         "cash_in": 0.0, "cash_out": total})
        elif pm == "bank":
            # Bank paid out — no cash movement; show informational row
            rows.append({"date": date, "voucher": pv_no,
                         "description": f"Cash Purchase (Bank/{bname}) — {ref}",
                         "cash_in": 0.0, "cash_out": 0.0})
        else:  # split
            rows.append({"date": date, "voucher": pv_no,
                         "description": f"Cash Purchase (Split-Cash) — {ref}",
                         "cash_in": 0.0, "cash_out": camnt})
            rows.append({"date": date, "voucher": pv_no,
                         "description": f"Cash Purchase (Split-Bank/{bname}) — {ref}",
                         "cash_in": 0.0, "cash_out": 0.0})

    # Keep rows in voucher-number order
    rows.sort(key=lambda r: r["voucher"])

    # ── Totals ────────────────────────────────────────────────────────────
    total_cash_in  = sum(r["cash_in"]  for r in rows)
    total_cash_out = sum(r["cash_out"] for r in rows)

    # Bank in today: bank portion of sales + all bank CP transactions
    total_bank_in = (
        _q(f"SELECT COALESCE(SUM(sv.bank_amount),0) FROM sale_vouchers sv"
           f" WHERE sv.bank_amount>0 AND {de_sv}=?", (iso,))
        + _q(f"SELECT COALESCE(SUM(bt.amount),0) FROM bank_transactions bt"
             f" WHERE bt.type='CP' AND {de_bt}=?", (iso,))
    )
    total_bank_out = _q(
        f"SELECT COALESCE(SUM(bt.amount),0) FROM bank_transactions bt"
        f" WHERE bt.type='CR' AND {de_bt}=?", (iso,)
    )

    closing_cash = opening_cash + total_cash_in  - total_cash_out
    closing_bank = opening_bank + total_bank_in  - total_bank_out

    conn.close()
    return {
        "opening_cash":  opening_cash,
        "opening_bank":  opening_bank,
        "rows":          rows,
        "total_cash_in": total_cash_in,
        "total_cash_out": total_cash_out,
        "total_bank_in": total_bank_in,
        "total_bank_out": total_bank_out,
        "closing_cash":  closing_cash,
        "closing_bank":  closing_bank,
    }


# ── Tab 1: Stock Report ───────────────────────────────────────────────────────

class StockReportTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._loaded = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.brand_combo = QComboBox()
        self.brand_combo.setMinimumWidth(150)
        self.brand_combo.addItem("All Brands", None)
        for b in db_brands_list():
            self.brand_combo.addItem(b["name"], b["id"])

        btn_search = QPushButton("Search")
        btn_search.setStyleSheet(BTN_SECONDARY)
        btn_search.clicked.connect(self.refresh)

        layout.addWidget(_filter_card(
            QLabel("Brand:"), self.brand_combo,
            btn_search, None,
        ))

        # ── 3-column scroll grid ──────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet("background:#f1f5f9;")

        self._grid_host = QWidget()
        self._grid_host.setStyleSheet("background:#f1f5f9;")
        grid_hl = QHBoxLayout(self._grid_host)
        grid_hl.setContentsMargins(0, 0, 0, 0)
        grid_hl.setSpacing(12)

        self._col_layouts = []
        for _ in range(3):
            col_w = QWidget()
            col_w.setObjectName("colCard")
            col_w.setStyleSheet(
                "QWidget#colCard { background:#ffffff; border:1px solid #e2e8f0;"
                " border-radius:8px; }"
            )
            col_vl = QVBoxLayout(col_w)
            col_vl.setContentsMargins(0, 0, 0, 8)
            col_vl.setSpacing(0)
            col_vl.setAlignment(Qt.AlignmentFlag.AlignTop)
            self._col_layouts.append(col_vl)
            grid_hl.addWidget(col_w, stretch=1)

        self._scroll.setWidget(self._grid_host)
        layout.addWidget(self._scroll, stretch=1)

        self.footer = QLabel("")
        self.footer.setStyleSheet(TOTAL_STYLE)
        layout.addWidget(self.footer)

    def ensure_loaded(self):
        if not self._loaded:
            self.refresh()
            self._loaded = True

    def refresh(self):
        # Clear all 3 columns
        for col_vl in self._col_layouts:
            while col_vl.count():
                item = col_vl.takeAt(0)
                w = item.widget()
                if w:
                    w.setParent(None)
                    w.deleteLater()

        rows = db_stock_report_grouped(self.brand_combo.currentData())

        # Group by brand, preserving order
        brands: dict[str, list] = {}
        for r in rows:
            brands.setdefault(r["brand"], []).append(r)

        BRAND_HDR_STYLE = (
            "background:#dbeafe; color:#1e40af; font-size:10pt; font-weight:bold;"
            " padding:8px 10px; border:none;"
        )

        total_units = 0

        for brand_idx, (brand, brand_rows) in enumerate(brands.items()):
            col_vl = self._col_layouts[brand_idx % 3]

            # Brand header — include total units for this brand
            brand_total = sum(r["qty"] for r in brand_rows)
            hdr = QLabel(f"{brand.upper()} ({brand_total})")
            hdr.setStyleSheet(BRAND_HDR_STYLE)
            hdr.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            col_vl.addWidget(hdr)

            # Per-model rows
            for row_idx, r in enumerate(brand_rows):
                row_bg = "#ffffff" if row_idx % 2 == 0 else "#f8fafc"
                row_w = QFrame()
                row_w.setStyleSheet(f"QFrame {{ background:{row_bg}; border:none; }}")
                row_hl = QHBoxLayout(row_w)
                row_hl.setContentsMargins(20, 4, 10, 4)
                row_hl.setSpacing(8)

                model_lbl = QLabel(r["model"])
                model_lbl.setStyleSheet(
                    "color:#1e293b; font-size:10pt; background:transparent; border:none;"
                )
                qty_lbl = QLabel(str(r["qty"]))
                qty_lbl.setAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                qty_lbl.setStyleSheet(
                    "color:#1e40af; font-weight:bold; font-size:10pt;"
                    " background:transparent; border:none;"
                )

                row_hl.addWidget(model_lbl, stretch=1)
                row_hl.addWidget(qty_lbl)
                col_vl.addWidget(row_w)
                total_units += r["qty"]

        n = len(rows)
        self.footer.setText(
            f"{n} model{'s' if n != 1 else ''} in stock    |    Total Units: {total_units}"
        )


# ── Tab 2: Stock Valuation ────────────────────────────────────────────────────

class StockValuationTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._loaded = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Filter bar — same as Stock Summary
        self.brand_combo = QComboBox()
        self.brand_combo.setMinimumWidth(150)
        self.brand_combo.addItem("All Brands", None)
        for b in db_brands_list():
            self.brand_combo.addItem(b["name"], b["id"])

        btn_search = QPushButton("Search")
        btn_search.setStyleSheet(BTN_SECONDARY)
        btn_search.clicked.connect(self.refresh)

        layout.addWidget(_filter_card(
            QLabel("Brand:"), self.brand_combo,
            btn_search, None,
        ))

        # 3-column scroll grid — identical structure to StockReportTab
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet("background:#f1f5f9;")

        self._grid_host = QWidget()
        self._grid_host.setStyleSheet("background:#f1f5f9;")
        grid_hl = QHBoxLayout(self._grid_host)
        grid_hl.setContentsMargins(0, 0, 0, 0)
        grid_hl.setSpacing(12)

        self._col_layouts = []
        for _ in range(3):
            col_w = QWidget()
            col_w.setObjectName("colCard")
            col_w.setStyleSheet(
                "QWidget#colCard { background:#ffffff; border:1px solid #e2e8f0;"
                " border-radius:8px; }"
            )
            col_vl = QVBoxLayout(col_w)
            col_vl.setContentsMargins(0, 0, 0, 8)
            col_vl.setSpacing(0)
            col_vl.setAlignment(Qt.AlignmentFlag.AlignTop)
            self._col_layouts.append(col_vl)
            grid_hl.addWidget(col_w, stretch=1)

        self._scroll.setWidget(self._grid_host)
        layout.addWidget(self._scroll, stretch=1)

        self.footer = QLabel("")
        self.footer.setStyleSheet(TOTAL_STYLE)
        layout.addWidget(self.footer)

    def ensure_loaded(self):
        if not self._loaded:
            self.refresh()
            self._loaded = True

    def refresh(self):
        # Clear all 3 columns
        for col_vl in self._col_layouts:
            while col_vl.count():
                item = col_vl.takeAt(0)
                w = item.widget()
                if w:
                    w.setParent(None)
                    w.deleteLater()

        rows = db_stock_valuation(self.brand_combo.currentData())

        # Group by brand
        brands: dict[str, list] = {}
        for r in rows:
            brands.setdefault(r["brand"], []).append(r)

        BRAND_HDR_STYLE = (
            "background:#dbeafe; color:#1e40af; font-size:10pt; font-weight:bold;"
            " padding:8px 10px; border:none;"
        )

        total_units = 0
        total_value = 0.0

        for brand_idx, (brand, brand_rows) in enumerate(brands.items()):
            col_vl = self._col_layouts[brand_idx % 3]

            brand_units = sum(r["units"] or 0 for r in brand_rows)
            brand_value = sum(r["total_value"] or 0 for r in brand_rows)

            hdr = QLabel(
                f"{brand.upper()} ({brand_units} units)"
                f"  —  PKR {fmt_pkr(brand_value)}"
            )
            hdr.setStyleSheet(BRAND_HDR_STYLE)
            hdr.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            col_vl.addWidget(hdr)

            for row_idx, r in enumerate(brand_rows):
                row_bg = "#ffffff" if row_idx % 2 == 0 else "#f8fafc"
                row_w = QFrame()
                row_w.setStyleSheet(f"QFrame {{ background:{row_bg}; border:none; }}")
                row_hl = QHBoxLayout(row_w)
                row_hl.setContentsMargins(20, 4, 10, 4)
                row_hl.setSpacing(8)

                model_lbl = QLabel(r["model"])
                model_lbl.setStyleSheet(
                    "color:#1e293b; font-size:10pt; background:transparent; border:none;"
                )

                qty_lbl = QLabel(str(r["units"] or 0))
                qty_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                qty_lbl.setFixedWidth(28)
                qty_lbl.setStyleSheet(
                    "color:#1e40af; font-weight:bold; font-size:10pt;"
                    " background:transparent; border:none;"
                )

                val_lbl = QLabel(f"PKR {fmt_pkr(r['total_value'])}")
                val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                val_lbl.setStyleSheet(
                    "color:#334155; font-size:10pt; background:transparent; border:none;"
                )

                row_hl.addWidget(model_lbl, stretch=1)
                row_hl.addWidget(qty_lbl)
                row_hl.addWidget(val_lbl)
                col_vl.addWidget(row_w)

                total_units += r["units"] or 0
                total_value += r["total_value"] or 0

        self.footer.setText(
            f"Total Units: {total_units}    |    "
            f"Total Stock Value: PKR {fmt_pkr(total_value)}"
        )


# ── Tab 3: Sales Report ───────────────────────────────────────────────────────

class SalesReportTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._loaded = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.from_date = QDateEdit(QDate.currentDate().addMonths(-1))
        self.from_date.setDisplayFormat("dd/MM/yyyy")
        self.from_date.setCalendarPopup(True)

        self.to_date = QDateEdit(QDate.currentDate())
        self.to_date.setDisplayFormat("dd/MM/yyyy")
        self.to_date.setCalendarPopup(True)

        self.type_combo = QComboBox()
        self.type_combo.addItem("All Types", None)
        self.type_combo.addItem("Cash", "cash")
        self.type_combo.addItem("Credit", "credit")

        self.salesman_combo = QComboBox()
        self.salesman_combo.setMinimumWidth(150)
        self.salesman_combo.addItem("All Salesmen", None)
        for sm in db_salesmen_for_filter():
            self.salesman_combo.addItem(sm["name"], sm["id"])

        btn_search = QPushButton("Search")
        btn_search.setStyleSheet(BTN_SECONDARY)
        btn_search.clicked.connect(self.refresh)

        layout.addWidget(_filter_card(
            QLabel("From:"), self.from_date,
            QLabel("To:"), self.to_date,
            QLabel("Type:"), self.type_combo,
            QLabel("Salesman:"), self.salesman_combo,
            btn_search, None,
        ))

        self.table = _make_table(
            ["Date", "SV Number", "Customer", "Salesman", "Type", "Items",
             "Total (PKR)", "Discount (PKR)"]
        )
        layout.addWidget(self.table, stretch=1)

        self.footer = QLabel("")
        self.footer.setStyleSheet(TOTAL_STYLE)
        layout.addWidget(self.footer)

    def ensure_loaded(self):
        if not self._loaded:
            self.refresh()
            self._loaded = True

    def refresh(self):
        from_iso = self.from_date.date().toString("yyyy-MM-dd")
        to_iso = self.to_date.date().toString("yyyy-MM-dd")
        rows = db_sales_report(
            from_iso, to_iso,
            self.type_combo.currentData(),
            self.salesman_combo.currentData(),
        )
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        grand_total = 0.0
        for r in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(r["date"]))
            self.table.setItem(row, 1, QTableWidgetItem(r["sv_number"]))
            self.table.setItem(row, 2, QTableWidgetItem(r["customer"] or "—"))
            self.table.setItem(row, 3, QTableWidgetItem(r["salesman"] or "—"))
            t = QTableWidgetItem(r["type"].capitalize())
            t.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 4, t)
            cnt = QTableWidgetItem(str(r["items"]))
            cnt.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 5, cnt)
            for col, val in [(6, r["total_amount"]), (7, r["discount"])]:
                item = QTableWidgetItem(fmt_pkr(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, col, item)
            grand_total += r["total_amount"] or 0
        self.table.setSortingEnabled(True)
        n = len(rows)
        self.footer.setText(
            f"{n} sale{'s' if n != 1 else ''}    |    Grand Total: PKR {fmt_pkr(grand_total)}"
        )


# ── Tab 4: Purchase Report ────────────────────────────────────────────────────

class PurchaseReportTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._loaded = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.from_date = QDateEdit(QDate.currentDate().addMonths(-1))
        self.from_date.setDisplayFormat("dd/MM/yyyy")
        self.from_date.setCalendarPopup(True)

        self.to_date = QDateEdit(QDate.currentDate())
        self.to_date.setDisplayFormat("dd/MM/yyyy")
        self.to_date.setCalendarPopup(True)

        self.sup_combo = QComboBox()
        self.sup_combo.setMinimumWidth(160)
        self.sup_combo.addItem("All Suppliers", None)
        for s in db_suppliers_list():
            self.sup_combo.addItem(s["name"], s["id"])

        self.type_combo = QComboBox()
        self.type_combo.setMinimumWidth(130)
        self.type_combo.addItem("All Types",     None)
        self.type_combo.addItem("Supplier Only", "supplier")
        self.type_combo.addItem("Cash Purchase", "cash")

        btn_search = QPushButton("Search")
        btn_search.setStyleSheet(BTN_SECONDARY)
        btn_search.clicked.connect(self.refresh)

        layout.addWidget(_filter_card(
            QLabel("From:"), self.from_date,
            QLabel("To:"), self.to_date,
            QLabel("Supplier:"), self.sup_combo,
            QLabel("Type:"), self.type_combo,
            btn_search, None,
        ))

        self.table = _make_table(
            ["Date", "PV Number", "Supplier / Type", "Items", "Total Amount (PKR)"]
        )
        layout.addWidget(self.table, stretch=1)

        self.footer = QLabel("")
        self.footer.setStyleSheet(TOTAL_STYLE)
        layout.addWidget(self.footer)

    def ensure_loaded(self):
        if not self._loaded:
            self.refresh()
            self._loaded = True

    def refresh(self):
        from_iso = self.from_date.date().toString("yyyy-MM-dd")
        to_iso   = self.to_date.date().toString("yyyy-MM-dd")
        rows = db_purchase_report(
            from_iso, to_iso,
            self.sup_combo.currentData(),
            self.type_combo.currentData(),
        )
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        grand_total = 0.0
        for r in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(r["date"]))
            self.table.setItem(row, 1, QTableWidgetItem(r["pv_number"]))
            # Supplier / Type column
            ptype = r["purchase_type"] if "purchase_type" in r.keys() else "supplier"
            if ptype == "cash":
                ref = r["egadget_ref"] if "egadget_ref" in r.keys() else ""
                sup_display = f"Cash — {ref}" if ref else "Cash Purchase"
            else:
                sup_display = r["supplier"]
            self.table.setItem(row, 2, QTableWidgetItem(sup_display))
            cnt = QTableWidgetItem(str(r["items"]))
            cnt.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 3, cnt)
            amt = QTableWidgetItem(fmt_pkr(r["total_amount"]))
            amt.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 4, amt)
            grand_total += r["total_amount"] or 0
        self.table.setSortingEnabled(True)
        n = len(rows)
        self.footer.setText(
            f"{n} purchase{'s' if n != 1 else ''}    |    Grand Total: PKR {fmt_pkr(grand_total)}"
        )


# ── Tab 5: Profit Report ──────────────────────────────────────────────────────

class ProfitReportTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._loaded = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.from_date = QDateEdit(QDate.currentDate().addMonths(-1))
        self.from_date.setDisplayFormat("dd/MM/yyyy")
        self.from_date.setCalendarPopup(True)

        self.to_date = QDateEdit(QDate.currentDate())
        self.to_date.setDisplayFormat("dd/MM/yyyy")
        self.to_date.setCalendarPopup(True)

        btn_search = QPushButton("Search")
        btn_search.setStyleSheet(BTN_SECONDARY)
        btn_search.clicked.connect(self.refresh)

        layout.addWidget(_filter_card(
            QLabel("Date Sold From:"), self.from_date,
            QLabel("To:"), self.to_date,
            btn_search, None,
        ))

        self.table = _make_table(
            ["Date Sold", "Brand", "Model", "IMEI",
             "Purchase Price (PKR)", "Sale Price (PKR)", "Profit (PKR)"]
        )
        layout.addWidget(self.table, stretch=1)

        self.footer = QLabel("")
        self.footer.setStyleSheet(TOTAL_STYLE)
        layout.addWidget(self.footer)

    def ensure_loaded(self):
        if not self._loaded:
            self.refresh()
            self._loaded = True

    def refresh(self):
        from_iso = self.from_date.date().toString("yyyy-MM-dd")
        to_iso = self.to_date.date().toString("yyyy-MM-dd")
        rows = db_profit_report(from_iso, to_iso)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        total_profit = 0.0
        for r in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(r["date_sold"]))
            self.table.setItem(row, 1, QTableWidgetItem(r["brand"]))
            self.table.setItem(row, 2, QTableWidgetItem(r["model"]))
            self.table.setItem(row, 3, QTableWidgetItem(r["imei"]))
            for col, val in [
                (4, r["purchase_price"]), (5, r["final_price"]), (6, r["profit"])
            ]:
                item = QTableWidgetItem(fmt_pkr(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if col == 6:
                    profit = r["profit"] or 0
                    item.setForeground(
                        QBrush(QColor("#16a34a") if profit >= 0 else QColor("#dc2626"))
                    )
                    item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                self.table.setItem(row, col, item)
            total_profit += r["profit"] or 0
        self.table.setSortingEnabled(True)
        n = len(rows)
        profit_color = "#16a34a" if total_profit >= 0 else "#dc2626"
        self.footer.setText(
            f"{n} item{'s' if n != 1 else ''} sold    |    "
            f"<span style='color:{profit_color};'>Total Profit: PKR {fmt_pkr(total_profit)}</span>"
        )
        self.footer.setTextFormat(Qt.TextFormat.RichText)


# ── Tab 6: IMEI Stock (flat table: Brand | Model | IMEI | Supplier | Date | Price | Use) ──

class ImeiStockTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._use_in_sale_cb = None
        self._loaded = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Filter bar
        filter_card = QFrame()
        filter_card.setStyleSheet(CARD_STYLE)
        fl = QHBoxLayout(filter_card)
        fl.setContentsMargins(12, 10, 12, 10)
        fl.setSpacing(10)

        fl.addWidget(QLabel("Search (Brand / Model / IMEI / Supplier):"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Type to filter...")
        self.search_input.setMinimumWidth(240)
        self.search_input.textChanged.connect(self.refresh)
        fl.addWidget(self.search_input)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.setStyleSheet(BTN_SECONDARY)
        btn_refresh.clicked.connect(self.refresh)
        fl.addWidget(btn_refresh)

        fl.addStretch()

        btn_export = QPushButton("Export CSV")
        btn_export.setStyleSheet(BTN_PRIMARY)
        btn_export.clicked.connect(self._export)
        fl.addWidget(btn_export)

        layout.addWidget(filter_card)

        self.copy_status = QLabel("")
        self.copy_status.setStyleSheet("color:#16a34a; font-size:9pt;")
        layout.addWidget(self.copy_status)

        self._copy_timer = QTimer(self)
        self._copy_timer.setSingleShot(True)
        self._copy_timer.timeout.connect(lambda: self.copy_status.setText(""))

        # 7 columns: Brand | Model | IMEI | Supplier | Purchase Date | Purchase Price | Use in Sale
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Brand", "Model", "IMEI", "Supplier", "Purchase Date", "Purchase Price (PKR)", ""]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)   # IMEI stretches
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(6, 100)
        self.table.setStyleSheet(TABLE_STYLE)
        self.table.cellDoubleClicked.connect(self._on_cell_double_click)
        layout.addWidget(self.table, stretch=1)

        self.footer = QLabel("")
        self.footer.setStyleSheet(TOTAL_STYLE)
        layout.addWidget(self.footer)

    def set_use_in_sale_cb(self, cb):
        self._use_in_sale_cb = cb

    def ensure_loaded(self):
        # Always re-query so newly sold IMEIs drop off immediately on tab-switch
        self.refresh()

    def refresh(self):
        search = self.search_input.text().strip()
        rows = db_stock_imei_report(search if search else None)

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        total_units = 0

        for r in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            imei = r["imei"]

            self.table.setItem(row, 0, QTableWidgetItem(r["brand"]))
            self.table.setItem(row, 1, QTableWidgetItem(r["model"]))

            imei_item = QTableWidgetItem(imei)
            imei_item.setData(Qt.ItemDataRole.UserRole, imei)
            imei_item.setToolTip("Double-click to copy IMEI")
            self.table.setItem(row, 2, imei_item)

            self.table.setItem(row, 3, QTableWidgetItem(r["supplier"]))
            self.table.setItem(row, 4, QTableWidgetItem(r["purchase_date"]))

            price_item = QTableWidgetItem(fmt_pkr(r["purchase_price"]))
            price_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.table.setItem(row, 5, price_item)

            btn_use = QPushButton("Use in Sale")
            btn_use.setStyleSheet(BTN_USE_SMALL)
            btn_use.clicked.connect(lambda _, i=imei: self._use_in_sale(i))
            self.table.setCellWidget(row, 6, btn_use)

            total_units += 1

        self.table.setSortingEnabled(True)
        self.footer.setText(f"Total Units in Stock: {total_units}")

    def _on_cell_double_click(self, row, col):
        """Double-click any cell on a data row to copy that row's IMEI."""
        item = self.table.item(row, 2)   # IMEI is always col 2
        if item:
            imei = item.data(Qt.ItemDataRole.UserRole)
            if imei:
                self._copy_imei(imei)

    def _copy_imei(self, imei: str):
        QApplication.clipboard().setText(imei)
        self.copy_status.setText(f"Copied: {imei}")
        self._copy_timer.start(2500)

    def _use_in_sale(self, imei: str):
        if self._use_in_sale_cb:
            self._use_in_sale_cb(imei)
        else:
            self._copy_imei(imei)
            self.copy_status.setText(
                f"IMEI {imei} copied — navigate to Sales and paste in the IMEI field."
            )
            self._copy_timer.start(4000)

    def _export(self):
        _export_table_csv(self.table, "imei_stock_report.csv", self)


# ── Tab 7: Cash Book ──────────────────────────────────────────────────────────

class CashBookTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._loaded = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # ── Filter bar ────────────────────────────────────────────────────
        filter_card = QFrame()
        filter_card.setStyleSheet(CARD_STYLE)
        fl = QHBoxLayout(filter_card)
        fl.setContentsMargins(12, 8, 12, 8)
        fl.setSpacing(8)

        fl.addWidget(QLabel("Date:"))
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        self.date_edit.setCalendarPopup(True)
        self.date_edit.dateChanged.connect(self.refresh)
        fl.addWidget(self.date_edit)

        # Today + Yesterday buttons — same style, same fixed width, side by side
        for label, delta in [("Today", 0), ("Yesterday", -1)]:
            btn = QPushButton(label)
            btn.setStyleSheet(BTN_SECONDARY)
            btn.setFixedWidth(82)
            d = delta  # capture for lambda
            btn.clicked.connect(
                lambda checked=False, dd=d: self.date_edit.setDate(
                    QDate.currentDate().addDays(dd)
                )
            )
            fl.addWidget(btn)

        fl.addStretch()

        btn_export = QPushButton("⬇ Export CSV")
        btn_export.setStyleSheet(BTN_PRIMARY)
        btn_export.clicked.connect(self._export)
        fl.addWidget(btn_export)

        layout.addWidget(filter_card)

        # ── Compact summary rows (Change 2 & 3) ──────────────────────────
        # Two plain single-line labels replacing the large card grid.
        # Format: Cash: Opening Rs.X | In Rs.X | Out Rs.X | Closing **Rs.X**
        self._cash_summary_lbl = QLabel()
        self._cash_summary_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._cash_summary_lbl.setStyleSheet(
            "background:#f0fdf4; border-radius:6px; padding:5px 14px; font-size:10pt;"
        )
        self._bank_summary_lbl = QLabel()
        self._bank_summary_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._bank_summary_lbl.setStyleSheet(
            "background:#fefce8; border-radius:6px; padding:5px 14px; font-size:10pt;"
        )
        layout.addWidget(self._cash_summary_lbl)
        layout.addWidget(self._bank_summary_lbl)

        # ── Detail table ─────────────────────────────────────────────────
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Date", "Voucher", "Description", "Cash In (Rs.)", "Cash Out (Rs.)"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)   # Description stretches
        hdr.setStretchLastSection(False)
        self.table.setStyleSheet(TABLE_STYLE)
        layout.addWidget(self.table, stretch=1)

        # Footer
        self.footer = QLabel("")
        self.footer.setStyleSheet(TOTAL_STYLE)
        layout.addWidget(self.footer)

    # ── helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _fmt_summary(icon, label, color, opening, cash_in, cash_out, closing):
        """Build the compact single-line HTML summary for cash or bank."""
        return (
            f"<span style='color:{color}; font-weight:bold;'>{icon} {label}:</span>"
            f"&nbsp;&nbsp;Opening Rs.{fmt_pkr(opening)}"
            f"&nbsp;&nbsp;|&nbsp;&nbsp;In Rs.{fmt_pkr(cash_in)}"
            f"&nbsp;&nbsp;|&nbsp;&nbsp;Out Rs.{fmt_pkr(cash_out)}"
            f"&nbsp;&nbsp;|&nbsp;&nbsp;Closing <b>Rs.{fmt_pkr(closing)}</b>"
        )

    def ensure_loaded(self):
        if not self._loaded:
            self.refresh()
            self._loaded = True

    def refresh(self):
        date_str = self.date_edit.date().toString("dd/MM/yyyy")
        data = db_cash_book(date_str)

        # Compact summary lines
        self._cash_summary_lbl.setText(self._fmt_summary(
            "💵", "Cash", "#15803d",
            data["opening_cash"], data["total_cash_in"],
            data["total_cash_out"], data["closing_cash"],
        ))
        self._bank_summary_lbl.setText(self._fmt_summary(
            "🏦", "Bank", "#92400e",
            data["opening_bank"], data["total_bank_in"],
            data["total_bank_out"], data["closing_bank"],
        ))

        # Populate table
        rows = data["rows"]
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        for r in rows:
            row_idx = self.table.rowCount()
            self.table.insertRow(row_idx)

            self.table.setItem(row_idx, 0, QTableWidgetItem(r["date"]))
            self.table.setItem(row_idx, 1, QTableWidgetItem(r["voucher"]))
            self.table.setItem(row_idx, 2, QTableWidgetItem(r["description"]))

            # Cash In — green, only show if > 0
            ci = r["cash_in"]
            ci_item = QTableWidgetItem(fmt_pkr(ci) if ci else "")
            ci_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if ci:
                ci_item.setForeground(QBrush(QColor("#16a34a")))
                ci_item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            self.table.setItem(row_idx, 3, ci_item)

            # Cash Out — red, only show if > 0
            co = r["cash_out"]
            co_item = QTableWidgetItem(fmt_pkr(co) if co else "")
            co_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if co:
                co_item.setForeground(QBrush(QColor("#dc2626")))
                co_item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            self.table.setItem(row_idx, 4, co_item)

        self.table.setSortingEnabled(True)

        n = len(rows)
        net = data["closing_cash"] - data["opening_cash"]
        net_color = "#16a34a" if net >= 0 else "#dc2626"
        self.footer.setText(
            f"{n} transaction{'s' if n != 1 else ''}    |    "
            f"<span style='color:{net_color};'>Net Cash: Rs. {fmt_pkr(net)}</span>"
        )
        self.footer.setTextFormat(Qt.TextFormat.RichText)

    def _export(self):
        date_str = self.date_edit.date().toString("dd_MM_yyyy")
        _export_table_csv(self.table, f"cash_book_{date_str}.csv", self)


# ── Reports Page ──────────────────────────────────────────────────────────────

class ReportsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:#f1f5f9;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title = QLabel("Reports")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title.setStyleSheet("color:#1e293b;")
        layout.addWidget(title)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border:1px solid #e2e8f0; border-radius:6px; background:#ffffff;
            }
            QTabBar::tab {
                background:#f8fafc; color:#64748b;
                border:1px solid #e2e8f0; border-bottom:none;
                border-radius:4px 4px 0 0;
                padding:7px 16px; margin-right:2px; font-size:10pt;
            }
            QTabBar::tab:selected {
                background:#ffffff; color:#1e40af; font-weight:bold;
            }
            QTabBar::tab:hover:!selected { background:#f1f5f9; }
        """)

        self._tab_stock      = StockReportTab()
        self._tab_imei_stock = ImeiStockTab()
        self._tab_valuation  = StockValuationTab()
        self._tab_sales      = SalesReportTab()
        self._tab_purchases  = PurchaseReportTab()
        self._tab_profit     = ProfitReportTab()
        self._tab_cashbook   = CashBookTab()

        self.tabs.addTab(self._tab_stock,      "Stock Summary")
        self.tabs.addTab(self._tab_imei_stock, "IMEI Stock")
        self.tabs.addTab(self._tab_valuation,  "Stock Valuation")
        self.tabs.addTab(self._tab_sales,      "Sales")
        self.tabs.addTab(self._tab_purchases,  "Purchases")
        self.tabs.addTab(self._tab_profit,     "Profit")
        self.tabs.addTab(self._tab_cashbook,   "Cash Book")

        self.tabs.currentChanged.connect(self._on_tab_change)
        layout.addWidget(self.tabs)

    def set_use_in_sale_cb(self, cb):
        self._tab_imei_stock.set_use_in_sale_cb(cb)

    def _on_tab_change(self, index):
        tab = self.tabs.widget(index)
        if hasattr(tab, "ensure_loaded"):
            tab.ensure_loaded()
