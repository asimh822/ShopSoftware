import csv
import os
import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QComboBox, QDateEdit,
    QHeaderView, QAbstractItemView, QFrame, QTabWidget,
    QFileDialog, QMessageBox, QLineEdit, QApplication,
    QScrollArea, QTableView, QStyledItemDelegate,
)
from PyQt6.QtCore import (
    Qt, QDate, QTimer, QThread, QEvent, QModelIndex,
    QAbstractTableModel, QSortFilterProxyModel, pyqtSignal,
)
from PyQt6.QtGui import QFont, QBrush, QColor, QPainter

from database import (
    get_connection, db_incentives_income_total, get_setting,
    db_cash_in_hand, db_bank_accounts, db_bank_account_closing_balance,
    _party_closing_balance, EXPENSE_CATEGORIES,
    db_expense_categories, db_all_expenses_combined,
)

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


# ── Unified report export (PDF + CSV) ──────────────────────────────────────────
# Every report tab exposes a _export_payload() returning:
#   (report_name, title, headers, rows, right_cols)
# and places two consistently-styled buttons (Export PDF / Export CSV) top-right.
# Files are written to a user-picked folder as <ReportName>_DDMMYYYY.<ext>.

def _pick_export_path(report_name, ext, parent):
    """Folder picker → full path <ReportName>_DDMMYYYY.<ext>, or None if cancelled."""
    folder = QFileDialog.getExistingDirectory(parent, "Select Export Folder")
    if not folder:
        return None
    today = datetime.date.today().strftime("%d%m%Y")
    safe = report_name.replace(" ", "_")
    return os.path.join(folder, f"{safe}_{today}.{ext}")


def _export_csv(report_name, headers, rows, parent=None):
    """Write headers + rows to <folder>/<ReportName>_DDMMYYYY.csv."""
    path = _pick_export_path(report_name, "csv", parent)
    if not path:
        return
    try:
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for r in rows:
                writer.writerow(r)
        QMessageBox.information(parent, "Exported", f"Saved to:\n{path}")
    except Exception as e:
        QMessageBox.critical(parent, "Export Failed", str(e))


def _export_pdf(report_name, title, headers, rows, parent=None, right_cols=None):
    """Render headers + rows to a clean PDF: shop name, title, date, then a table."""
    try:
        from reportlab.lib.pagesizes import A4, landscape as _landscape
        from reportlab.lib import colors
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        )
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    except ImportError:
        QMessageBox.critical(
            parent, "Missing Library",
            "reportlab is not installed.\n\nInstall it with:\n  pip install reportlab"
        )
        return

    path = _pick_export_path(report_name, "pdf", parent)
    if not path:
        return

    right_cols = right_cols or set()
    pagesize = _landscape(A4) if len(headers) >= 6 else A4
    shop = get_setting("shop_name") or "United Mobile"
    today = datetime.date.today().strftime("%d/%m/%Y")

    title_ps = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=14,
                              alignment=TA_CENTER, leading=18)
    sub_ps   = ParagraphStyle("s", fontName="Helvetica", fontSize=10,
                              alignment=TA_CENTER, leading=14,
                              textColor=colors.HexColor("#475569"))
    cell_ps  = ParagraphStyle("c", fontName="Helvetica", fontSize=8, leading=10)
    cellr_ps = ParagraphStyle("cr", fontName="Helvetica", fontSize=8, leading=10,
                              alignment=TA_RIGHT)
    head_ps  = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=8, leading=10,
                              textColor=colors.white)

    story = [
        Paragraph(shop, title_ps),
        Paragraph(title, sub_ps),
        Paragraph(f"Date: {today}", sub_ps),
        Spacer(1, 10),
    ]

    data = [[Paragraph(str(h), head_ps) for h in headers]]
    for r in rows:
        cells = []
        for ci, val in enumerate(r):
            ps = cellr_ps if ci in right_cols else cell_ps
            cells.append(Paragraph("" if val is None else str(val), ps))
        data.append(cells)

    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#f8fafc")]),
    ]))
    story.append(t)

    doc = SimpleDocTemplate(
        path, pagesize=pagesize,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
    )
    try:
        doc.build(story)
    except Exception as e:
        QMessageBox.critical(parent, "Export Failed", str(e))
        return
    QMessageBox.information(parent, "PDF Exported", f"Saved to:\n{path}")


def _table_to_rows(table):
    """Extract (headers, rows) from a populated QTableWidget for export."""
    headers = [
        (table.horizontalHeaderItem(c).text() if table.horizontalHeaderItem(c) else "")
        for c in range(table.columnCount())
    ]
    rows = [
        [(table.item(r, c).text() if table.item(r, c) else "")
         for c in range(table.columnCount())]
        for r in range(table.rowCount())
    ]
    return headers, rows


def _do_export_pdf(widget):
    name, title, headers, rows, right_cols = widget._export_payload()
    _export_pdf(name, title, headers, rows, widget, right_cols)


def _do_export_csv(widget):
    name, _title, headers, rows, _right = widget._export_payload()
    _export_csv(name, headers, rows, widget)


def _make_export_buttons(widget):
    """Two consistently-styled export buttons wired to widget._export_payload()."""
    btn_pdf = QPushButton("Export PDF")
    btn_pdf.setStyleSheet(BTN_SECONDARY)
    btn_pdf.clicked.connect(lambda: _do_export_pdf(widget))
    btn_csv = QPushButton("Export CSV")
    btn_csv.setStyleSheet(BTN_SECONDARY)
    btn_csv.clicked.connect(lambda: _do_export_csv(widget))
    return btn_pdf, btn_csv


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
               COALESCE(c.name, sv.cash_customer_name,
                        sup.name || ' (Supplier)', '—') customer,
               sv.type, COUNT(sl.id) items, sv.total_amount, sv.discount,
               COALESCE(sm.name, '—') salesman
        FROM sale_vouchers sv
        LEFT JOIN customers c ON c.id = sv.customer_id
        LEFT JOIN suppliers sup ON sup.id = sv.supplier_as_customer_id
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
               COALESCE(s.name, c.name || ' (Customer)', 'Cash Purchase') supplier,
               COUNT(pl.id) items, pv.total_amount,
               COALESCE(pv.purchase_type, 'supplier') purchase_type,
               COALESCE(pv.egadget_ref, '') egadget_ref
        FROM purchase_vouchers pv
        LEFT JOIN suppliers s ON s.id = pv.supplier_id AND pv.supplier_id != 0
        LEFT JOIN customers c ON c.id = pv.customer_as_supplier_id
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


def db_expenses_by_category(from_iso: str, to_iso: str, category: str = "") -> dict:
    """
    Returns expense totals grouped by category for a date range.

    Parameters
    ----------
    from_iso, to_iso : str   e.g. "2026-01-01"
    category         : str   empty = all categories

    Returns
    -------
    {
      "rows": [{"category": str, "count": int, "total": float}, ...],
      "grand_total": float,
      "grand_count": int,
    }
    """
    de = "substr(e.date,7,4)||'-'||substr(e.date,4,2)||'-'||substr(e.date,1,2)"
    conds  = [f"{de} >= ?", f"{de} <= ?"]
    params = [from_iso, to_iso]
    if category:
        conds.append("e.category = ?")
        params.append(category)
    where = "WHERE " + " AND ".join(conds)

    conn = get_connection()
    rows = conn.execute(f"""
        SELECT e.category,
               COUNT(*)       AS cnt,
               SUM(e.amount)  AS total
        FROM expenses e
        {where}
        GROUP BY e.category
        ORDER BY total DESC
    """, params).fetchall()

    detail = conn.execute(f"""
        SELECT e.expense_number, e.date, e.category,
               COALESCE(e.description,'') AS description,
               e.amount, e.payment_method,
               COALESCE(ba.name,'') AS bank_name
        FROM expenses e
        LEFT JOIN bank_accounts ba ON ba.id = e.bank_account_id
        {where}
        ORDER BY {de}, e.expense_number
    """, params).fetchall()

    conn.close()

    grouped = [{"category": r["category"],
                "count":    int(r["cnt"]),
                "total":    float(r["total"] or 0)} for r in rows]
    grand_total = sum(g["total"] for g in grouped)
    grand_count = sum(g["count"] for g in grouped)

    return {
        "rows":        grouped,
        "detail":      [dict(d) for d in detail],
        "grand_total": grand_total,
        "grand_count": grand_count,
    }


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
        - _q(f"SELECT COALESCE(SUM(e.amount),0) FROM expenses e"
             f" WHERE e.payment_method='cash'"
             f" AND {_de('e.date')}<?", (iso,))
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
               p.notes,
               COALESCE(s.name, c.name, op.name, ec.name, '?') party_name
        FROM payments p
        LEFT JOIN suppliers s      ON p.party_type='supplier' AND s.id=p.party_id
        LEFT JOIN customers c      ON p.party_type='customer' AND c.id=p.party_id
        LEFT JOIN other_parties op ON p.party_type='other'    AND op.id=p.party_id
        LEFT JOIN expense_categories ec ON p.party_type='expense' AND ec.id=p.party_id
        WHERE {de_p}=?
        ORDER BY p.voucher_number
    """, (iso,)).fetchall()

    for p in payments:
        name  = p["party_name"]
        amt   = float(p["amount"] or 0)
        ptype = p["party_type"]
        if p["type"] == "CP":
            if ptype == "expense":
                desc = f"Expense — {name}"
                if p["notes"]:
                    desc += f" ({p['notes']})"
            else:
                desc = f"Payment — {name}"
            rows.append({"date": p["date"], "voucher": p["voucher_number"],
                         "description": desc,
                         "cash_in": 0.0, "cash_out": amt})
        else:  # CR
            if ptype == "expense":
                desc = f"Expense Refund — {name}"
            else:
                desc = f"Receipt — {name}"
            rows.append({"date": p["date"], "voucher": p["voucher_number"],
                         "description": desc,
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
               LOWER(COALESCE(pv.payment_method, 'cash')) payment_method,
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
            # Bank-only purchase — no cash movement; excluded from Cash Book
            continue
        else:  # split — only the cash portion is a cash movement
            rows.append({"date": date, "voucher": pv_no,
                         "description": f"Cash Purchase (Split-Cash) — {ref}",
                         "cash_in": 0.0, "cash_out": camnt})

    # 5. Expenses
    de_e = _de("e.date")
    exp_rows = conn.execute(f"""
        SELECT e.expense_number, e.date, e.category,
               COALESCE(e.description, '') AS description,
               e.amount, LOWER(COALESCE(e.payment_method, 'cash')) AS payment_method,
               COALESCE(ba.name, 'Bank') AS bank_name
        FROM expenses e
        LEFT JOIN bank_accounts ba ON ba.id = e.bank_account_id
        WHERE {de_e}=?
        ORDER BY e.expense_number
    """, (iso,)).fetchall()

    for ex in exp_rows:
        desc_part = f" ({ex['description']})" if ex['description'] else ''
        pm        = ex['payment_method']
        cat       = ex['category']
        amt       = float(ex['amount'] or 0)
        bname     = ex['bank_name']
        exp_no    = ex['expense_number']
        date      = ex['date']

        if pm == 'cash':
            rows.append({"date": date, "voucher": exp_no,
                         "description": f"Expense — {cat}{desc_part} (Cash)",
                         "cash_in": 0.0, "cash_out": amt})
        else:  # bank — no cash movement; excluded from Cash Book
            continue

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

        btn_pdf, btn_csv = _make_export_buttons(self)
        layout.addWidget(_filter_card(
            QLabel("Brand:"), self.brand_combo,
            btn_search, None, btn_pdf, btn_csv,
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

    def _export_payload(self):
        rows = db_stock_report_grouped(self.brand_combo.currentData())
        data = [[r["brand"], r["model"], str(r["qty"])] for r in rows]
        return ("Stock_Summary", "Stock Summary",
                ["Brand", "Model", "Quantity"], data, {2})


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

        btn_pdf, btn_csv = _make_export_buttons(self)
        layout.addWidget(_filter_card(
            QLabel("Brand:"), self.brand_combo,
            btn_search, None, btn_pdf, btn_csv,
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

    def _export_payload(self):
        rows = db_stock_valuation(self.brand_combo.currentData())
        data = [[r["brand"], r["model"], str(r["units"] or 0), fmt_pkr(r["total_value"])]
                for r in rows]
        return ("Stock_Valuation", "Stock Valuation",
                ["Brand", "Model", "Units", "Value (PKR)"], data, {2, 3})


# ── Tab 3: Sales Report ───────────────────────────────────────────────────────

class SalesReportTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._loaded = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.from_date = QDateEdit(QDate.currentDate())
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

        btn_today = QPushButton("Today")
        btn_today.setStyleSheet(BTN_SECONDARY)
        btn_today.clicked.connect(self._set_today)

        btn_yesterday = QPushButton("Yesterday")
        btn_yesterday.setStyleSheet(BTN_SECONDARY)
        btn_yesterday.clicked.connect(self._set_yesterday)

        btn_search = QPushButton("Search")
        btn_search.setStyleSheet(BTN_SECONDARY)
        btn_search.clicked.connect(self.refresh)

        btn_pdf, btn_csv = _make_export_buttons(self)
        layout.addWidget(_filter_card(
            QLabel("From:"), self.from_date,
            QLabel("To:"), self.to_date,
            QLabel("Type:"), self.type_combo,
            QLabel("Salesman:"), self.salesman_combo,
            btn_today, btn_yesterday, btn_search, None, btn_pdf, btn_csv,
        ))

        self.table = _make_table(
            ["Date", "SV Number", "Customer", "Salesman", "Type", "Items",
             "Total (PKR)", "Discount (PKR)"]
        )
        layout.addWidget(self.table, stretch=1)

        self.footer = QLabel("")
        self.footer.setStyleSheet(TOTAL_STYLE)
        layout.addWidget(self.footer)

    def _set_today(self):
        today = QDate.currentDate()
        self.from_date.setDate(today)
        self.to_date.setDate(today)
        self.refresh()

    def _set_yesterday(self):
        yesterday = QDate.currentDate().addDays(-1)
        self.from_date.setDate(yesterday)
        self.to_date.setDate(yesterday)
        self.refresh()

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

    def _export_payload(self):
        headers, rows = _table_to_rows(self.table)
        return ("Sales_Report", "Sales Report", headers, rows, {6, 7})


# ── Tab 4: Purchase Report ────────────────────────────────────────────────────

class PurchaseReportTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._loaded = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.from_date = QDateEdit(QDate.currentDate())
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

        btn_today = QPushButton("Today")
        btn_today.setStyleSheet(BTN_SECONDARY)
        btn_today.clicked.connect(self._set_today)

        btn_yesterday = QPushButton("Yesterday")
        btn_yesterday.setStyleSheet(BTN_SECONDARY)
        btn_yesterday.clicked.connect(self._set_yesterday)

        btn_search = QPushButton("Search")
        btn_search.setStyleSheet(BTN_SECONDARY)
        btn_search.clicked.connect(self.refresh)

        btn_pdf, btn_csv = _make_export_buttons(self)
        layout.addWidget(_filter_card(
            QLabel("From:"), self.from_date,
            QLabel("To:"), self.to_date,
            QLabel("Supplier:"), self.sup_combo,
            QLabel("Type:"), self.type_combo,
            btn_today, btn_yesterday, btn_search, None, btn_pdf, btn_csv,
        ))

        self.table = _make_table(
            ["Date", "PV Number", "Supplier / Type", "Items", "Total Amount (PKR)"]
        )
        layout.addWidget(self.table, stretch=1)

        self.footer = QLabel("")
        self.footer.setStyleSheet(TOTAL_STYLE)
        layout.addWidget(self.footer)

    def _set_today(self):
        today = QDate.currentDate()
        self.from_date.setDate(today)
        self.to_date.setDate(today)
        self.refresh()

    def _set_yesterday(self):
        yesterday = QDate.currentDate().addDays(-1)
        self.from_date.setDate(yesterday)
        self.to_date.setDate(yesterday)
        self.refresh()

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

    def _export_payload(self):
        headers, rows = _table_to_rows(self.table)
        return ("Purchases_Report", "Purchases Report", headers, rows, {4})


# ── Tab 5: Profit Report ──────────────────────────────────────────────────────

def _profit_summary_card(title: str) -> tuple:
    """Return (QFrame card, value QLabel) for one profit summary metric."""
    card = QFrame()
    card.setStyleSheet(
        "background:#ffffff; border:1px solid #e2e8f0; border-radius:8px;"
    )
    vl = QVBoxLayout(card)
    vl.setContentsMargins(14, 10, 14, 10)
    vl.setSpacing(4)
    lbl_title = QLabel(title)
    lbl_title.setStyleSheet("color:#64748b; font-size:9pt; border:none;")
    lbl_val = QLabel("Rs. 0")
    lbl_val.setStyleSheet("color:#1e293b; font-size:11pt; font-weight:bold; border:none;")
    vl.addWidget(lbl_title)
    vl.addWidget(lbl_val)
    return card, lbl_val


def _other_income_card() -> tuple:
    """
    Summary card for the 'Other Income' P&L section. Carries a distinct section
    header ('OTHER INCOME') above the 'Incentives Income' line item so the figure
    is clearly grouped as Other Income rather than trading profit.
    Returns (QFrame card, value QLabel).
    """
    card = QFrame()
    card.setStyleSheet(
        "background:#ffffff; border:1px solid #e2e8f0; border-radius:8px;"
    )
    vl = QVBoxLayout(card)
    vl.setContentsMargins(14, 10, 14, 10)
    vl.setSpacing(2)
    lbl_section = QLabel("OTHER INCOME")
    lbl_section.setStyleSheet(
        "color:#0369a1; font-size:7pt; font-weight:bold; letter-spacing:1px; border:none;"
    )
    lbl_item = QLabel("Incentives Income")
    lbl_item.setStyleSheet("color:#64748b; font-size:9pt; border:none;")
    lbl_val = QLabel("Rs. 0")
    lbl_val.setStyleSheet("color:#1e293b; font-size:11pt; font-weight:bold; border:none;")
    vl.addWidget(lbl_section)
    vl.addWidget(lbl_item)
    vl.addWidget(lbl_val)
    return card, lbl_val


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

        btn_pdf, btn_csv = _make_export_buttons(self)
        layout.addWidget(_filter_card(
            QLabel("Date Sold From:"), self.from_date,
            QLabel("To:"), self.to_date,
            btn_search, None, btn_pdf, btn_csv,
        ))

        # ── Summary cards row ─────────────────────────────────────────────
        cards_row = QHBoxLayout()
        cards_row.setSpacing(10)

        c1, self._lbl_revenue  = _profit_summary_card("Sales Revenue")
        c2, self._lbl_cost     = _profit_summary_card("Purchase Cost")
        c3, self._lbl_gross    = _profit_summary_card("Gross Profit")
        c4, self._lbl_incentive = _other_income_card()
        c5, self._lbl_expenses = _profit_summary_card("Total Expenses")
        c6, self._lbl_net      = _profit_summary_card("Net Profit")

        for c in (c1, c2, c3, c4, c5, c6):
            cards_row.addWidget(c)

        layout.addLayout(cards_row)

        # ── Daily breakdown table ─────────────────────────────────────────
        daily_lbl = QLabel("Daily Breakdown")
        daily_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        daily_lbl.setStyleSheet("color:#475569;")
        layout.addWidget(daily_lbl)

        self.daily_table = _make_table(
            ["Date", "Units Sold", "Purchase Cost (PKR)",
             "Sale Value (PKR)", "Gross Profit (PKR)", "Margin %"]
        )
        self.daily_table.setMaximumHeight(200)
        layout.addWidget(self.daily_table)

        # ── Detail table ──────────────────────────────────────────────────
        detail_lbl = QLabel("Per-IMEI Detail")
        detail_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        detail_lbl.setStyleSheet("color:#475569;")
        layout.addWidget(detail_lbl)

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
        to_iso   = self.to_date.date().toString("yyyy-MM-dd")
        rows = db_profit_report(from_iso, to_iso)

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        total_revenue = 0.0
        total_cost    = 0.0
        total_profit  = 0.0

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
            total_revenue += float(r["final_price"]    or 0)
            total_cost    += float(r["purchase_price"] or 0)
            total_profit  += float(r["profit"]         or 0)

        self.table.setSortingEnabled(True)

        # ── Daily breakdown table ─────────────────────────────────────────
        from collections import defaultdict
        daily: dict = defaultdict(lambda: {"units": 0, "cost": 0.0, "revenue": 0.0, "profit": 0.0})
        for r in rows:
            d = r["date_sold"] or "Unknown"
            daily[d]["units"]   += 1
            daily[d]["cost"]    += float(r["purchase_price"] or 0)
            daily[d]["revenue"] += float(r["final_price"] or 0)
            daily[d]["profit"]  += float(r["profit"] or 0)

        self.daily_table.setSortingEnabled(False)
        self.daily_table.setRowCount(0)
        for date_key in sorted(daily.keys(), reverse=True):
            d = daily[date_key]
            margin = (d["profit"] / d["revenue"] * 100) if d["revenue"] else 0.0
            drow = self.daily_table.rowCount()
            self.daily_table.insertRow(drow)
            self.daily_table.setItem(drow, 0, QTableWidgetItem(date_key))
            units_item = QTableWidgetItem(str(d["units"]))
            units_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.daily_table.setItem(drow, 1, units_item)
            for col, val in [(2, d["cost"]), (3, d["revenue"]), (4, d["profit"])]:
                item = QTableWidgetItem(fmt_pkr(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if col == 4:
                    item.setForeground(QBrush(QColor("#16a34a") if d["profit"] >= 0 else QColor("#dc2626")))
                    item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                self.daily_table.setItem(drow, col, item)
            margin_item = QTableWidgetItem(f"{margin:.1f}%")
            margin_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.daily_table.setItem(drow, 5, margin_item)
        self.daily_table.setSortingEnabled(True)

        # ── Expenses for the same date range (legacy + new CP payments) ──────
        conn = get_connection()
        de_e = "substr(e.date,7,4)||'-'||substr(e.date,4,2)||'-'||substr(e.date,1,2)"
        de_p = "substr(p.date,7,4)||'-'||substr(p.date,4,2)||'-'||substr(p.date,1,2)"
        legacy_exp = float(conn.execute(
            f"SELECT COALESCE(SUM(e.amount),0) FROM expenses e"
            f" WHERE {de_e} >= ? AND {de_e} <= ?",
            (from_iso, to_iso),
        ).fetchone()[0] or 0)
        new_exp = float(conn.execute(
            f"SELECT COALESCE(SUM(p.amount),0) FROM payments p"
            f" WHERE p.party_type='expense' AND p.type='CP'"
            f" AND {de_p} >= ? AND {de_p} <= ?",
            (from_iso, to_iso),
        ).fetchone()[0] or 0)
        total_expenses = legacy_exp + new_exp
        conn.close()

        # ── Incentives income earned to date (running income account balance) ──
        incentives = db_incentives_income_total()

        net_profit = total_profit + incentives - total_expenses

        # ── Update summary cards ──────────────────────────────────────────
        def _color_val(lbl: QLabel, amount: float, neutral: bool = False):
            if neutral:
                color = "#1e293b"
            else:
                color = "#16a34a" if amount >= 0 else "#dc2626"
            lbl.setStyleSheet(
                f"color:{color}; font-size:11pt; font-weight:bold; border:none;"
            )
            lbl.setText(f"Rs. {fmt_pkr(amount)}")

        _color_val(self._lbl_revenue,   total_revenue,  neutral=True)
        _color_val(self._lbl_cost,      total_cost,     neutral=True)
        _color_val(self._lbl_gross,     total_profit)
        _color_val(self._lbl_incentive, incentives,     neutral=True)
        _color_val(self._lbl_expenses,  total_expenses, neutral=True)
        _color_val(self._lbl_net,       net_profit)

        # ── Footer ───────────────────────────────────────────────────────
        n = len(rows)
        profit_color = "#16a34a" if total_profit >= 0 else "#dc2626"
        self.footer.setText(
            f"{n} item{'s' if n != 1 else ''} sold    |    "
            f"<span style='color:{profit_color};'>Gross Profit: Rs. {fmt_pkr(total_profit)}</span>"
            f"    |    "
            f"Other Income (Incentives): Rs. {fmt_pkr(incentives)}"
            f"    |    "
            f"Expenses: Rs. {fmt_pkr(total_expenses)}"
            f"    |    "
            f"<span style='color:{'#16a34a' if net_profit >= 0 else '#dc2626'};'>"
            f"Net Profit: Rs. {fmt_pkr(net_profit)}</span>"
        )
        self.footer.setTextFormat(Qt.TextFormat.RichText)

    def _export_payload(self):
        headers, rows = _table_to_rows(self.table)
        # Append the summary figures (shown as cards on screen) as trailing rows.
        blank = ["", "", "", "", "", "", ""]
        summary = [
            ["", "", "", "", "", "Sales Revenue",     self._lbl_revenue.text()],
            ["", "", "", "", "", "Purchase Cost",     self._lbl_cost.text()],
            ["", "", "", "", "", "Gross Profit",      self._lbl_gross.text()],
            ["", "", "", "", "", "Other Income (Incentives Income)", self._lbl_incentive.text()],
            ["", "", "", "", "", "Total Expenses",    self._lbl_expenses.text()],
            ["", "", "", "", "", "Net Profit",        self._lbl_net.text()],
        ]
        return ("Profit_Report", "Profit Report", headers,
                rows + [blank] + summary, {4, 5, 6})


# ── Tab 6: IMEI Stock (flat table: Brand | Model | IMEI | Supplier | Date | Price | Use) ──

# QTableView selectors share QTableWidget's styling rules (QTableWidget subclasses
# QTableView), so mirror the existing look by retargeting the selector name.
TABLE_VIEW_STYLE = TABLE_STYLE.replace("QTableWidget", "QTableView")


class _ImeiLoadWorker(QThread):
    """Loads all in-stock IMEI rows off the UI thread so a large dataset
    never freezes the window. Emits plain tuples (safe across threads)."""
    loaded = pyqtSignal(list)

    def run(self):
        rows = db_stock_imei_report(None)   # load everything once; filter in memory
        data = [
            (r["brand"], r["model"], r["imei"], r["supplier"],
             r["purchase_date"], r["purchase_price"])
            for r in rows
        ]
        self.loaded.emit(data)


class ImeiStockModel(QAbstractTableModel):
    """Virtual data model — holds the full dataset in memory and feeds only the
    rows the QTableView asks for (visible ones), so total record count no longer
    drives rendering cost. Search filters the in-memory copy and resets the view."""

    HEADERS = ["Brand", "Model", "IMEI", "Supplier",
               "Purchase Date", "Purchase Price (PKR)", ""]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all = []     # full dataset: list of (brand, model, imei, supplier, date, price)
        self._rows = []    # currently visible (post-filter) subset
        self._filter = ""

    # ── Qt model interface ──
    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else 7

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        r = self._rows[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 5:
                return fmt_pkr(r[5])
            if col == 6:
                return None          # button column — painted by the delegate
            return r[col]
        if role == Qt.ItemDataRole.TextAlignmentRole and col == 5:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ToolTipRole and col == 2:
            return "Double-click to copy IMEI"
        if role == Qt.ItemDataRole.UserRole:
            return r[2]              # IMEI for this row
        return None

    # ── data plumbing ──
    def set_source(self, rows):
        self._all = list(rows)
        self._apply()

    def set_filter(self, text):
        self._filter = (text or "").strip().lower()
        self._apply()

    def _apply(self):
        self.beginResetModel()
        t = self._filter
        if not t:
            self._rows = list(self._all)
        else:
            # Same fields the old SQL search matched: brand, model, IMEI, supplier.
            self._rows = [
                r for r in self._all
                if t in (r[0] or "").lower()
                or t in (r[1] or "").lower()
                or t in (r[2] or "").lower()
                or t in (r[3] or "").lower()
            ]
        self.endResetModel()

    def imei_at(self, row):
        if 0 <= row < len(self._rows):
            return self._rows[row][2]
        return None

    def displayed_rows(self):
        return self._rows

    def total_units(self):
        return len(self._rows)


class _UseButtonDelegate(QStyledItemDelegate):
    """Paints a 'Use in Sale' button into the cell and emits clicked(index) when
    pressed. Done as a delegate (not a real QPushButton per row) so the view stays
    virtual — no widget is created for off-screen rows."""
    clicked = pyqtSignal(QModelIndex)

    def paint(self, painter, option, index):
        rect = option.rect.adjusted(6, 5, -6, -5)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#dcfce7"))      # matches BTN_USE_SMALL
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(QColor("#15803d"))
        f = painter.font()
        f.setPointSize(9)
        painter.setFont(f)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Use in Sale")
        painter.restore()

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.Type.MouseButtonRelease:
            if option.rect.contains(event.position().toPoint()):
                self.clicked.emit(index)
                return True
        return False


class ImeiStockTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._use_in_sale_cb = None
        self._load_worker = None

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
        # Filtering is now in-memory and instant, so apply on every keystroke.
        self.search_input.textChanged.connect(self._apply_filter)
        fl.addWidget(self.search_input)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.setStyleSheet(BTN_SECONDARY)
        btn_refresh.clicked.connect(self.refresh)
        fl.addWidget(btn_refresh)

        fl.addStretch()

        btn_pdf, btn_csv = _make_export_buttons(self)
        fl.addWidget(btn_pdf)
        fl.addWidget(btn_csv)

        layout.addWidget(filter_card)

        self.copy_status = QLabel("")
        self.copy_status.setStyleSheet("color:#16a34a; font-size:9pt;")
        layout.addWidget(self.copy_status)

        self._copy_timer = QTimer(self)
        self._copy_timer.setSingleShot(True)
        self._copy_timer.timeout.connect(lambda: self.copy_status.setText(""))

        # 7 columns: Brand | Model | IMEI | Supplier | Purchase Date | Purchase Price | Use in Sale
        # Virtual view: QAbstractTableModel feeds rows on demand, QSortFilterProxyModel
        # keeps header-click sorting working, QTableView renders only visible rows.
        self.model = ImeiStockModel(self)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)   # IMEI stretches
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(6, 100)
        self.table.setStyleSheet(TABLE_VIEW_STYLE)
        self.table.doubleClicked.connect(self._on_double_click)

        self._use_delegate = _UseButtonDelegate(self.table)
        self._use_delegate.clicked.connect(self._on_use_clicked)
        self.table.setItemDelegateForColumn(6, self._use_delegate)

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
        # Load the full dataset once, off the UI thread, with a brief indicator.
        if self._load_worker is not None and self._load_worker.isRunning():
            return
        self.footer.setText("Loading IMEI stock…")
        worker = _ImeiLoadWorker(self)
        worker.loaded.connect(self._on_loaded)
        worker.finished.connect(self._on_worker_finished)
        self._load_worker = worker
        worker.start()

    def _on_loaded(self, data):
        self.model.set_source(data)
        # Re-apply any active search term to the freshly loaded data.
        self.model.set_filter(self.search_input.text())
        self._update_footer()

    def _on_worker_finished(self):
        self._load_worker = None

    def _apply_filter(self, _text=None):
        self.model.set_filter(self.search_input.text())
        self._update_footer()

    def _update_footer(self):
        self.footer.setText(f"Total Units in Stock: {self.model.total_units()}")

    def _on_double_click(self, index):
        """Double-click any cell on a data row to copy that row's IMEI."""
        src = self.proxy.mapToSource(index)
        imei = self.model.imei_at(src.row())
        if imei:
            self._copy_imei(imei)

    def _on_use_clicked(self, index):
        src = self.proxy.mapToSource(index)
        imei = self.model.imei_at(src.row())
        if imei:
            self._use_in_sale(imei)

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

    def _export_payload(self):
        headers = list(ImeiStockModel.HEADERS[:6])   # drop the action column
        rows = [
            [r[0], r[1], r[2], r[3], r[4], fmt_pkr(r[5])]
            for r in self.model.displayed_rows()
        ]
        return ("IMEI_Stock", "IMEI Stock", headers, rows, {5})


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

        btn_pdf, btn_csv = _make_export_buttons(self)
        fl.addWidget(btn_pdf)
        fl.addWidget(btn_csv)

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

    def _export_payload(self):
        headers, rows = _table_to_rows(self.table)
        date_str = self.date_edit.date().toString("dd/MM/yyyy")
        return ("Cash_Book", f"Cash Book — {date_str}", headers, rows, {3, 4})


# ── Tab 8: Customer Insights ──────────────────────────────────────────────────

# Price-range buckets — (label, min_price_or_None, max_price_or_None)
_PRICE_RANGES = [
    ("All Prices",           None,   None),
    ("Under Rs. 20,000",     None,  20000),
    ("Rs. 20,000 – 30,000", 20000,  30000),
    ("Rs. 30,000 – 40,000", 30000,  40000),
    ("Rs. 40,000 – 50,000", 40000,  50000),
    ("Rs. 50,000 – 75,000", 50000,  75000),
    ("Rs. 75,000 – 100,000",75000, 100000),
    ("Above Rs. 100,000",  100000,   None),
]


def db_customer_insights(from_iso=None, to_iso=None, brand_name=None,
                          price_min=None, price_max=None, search=None):
    """
    Returns one row per unique cash_customer_contact:
      - Most recent cash sale for that contact number
      - If that sale has multiple items, the highest-priced item is used
    All filter parameters apply to this 'representative' purchase.

    Columns returned: cash_customer_name, cash_customer_contact,
                      model_name, brand_name, final_price, date, iso_date
    """
    de_sv = _date_expr("sv.date")

    # Build the outer WHERE clauses and params
    conds, params = [], []
    if from_iso:
        conds.append("ri.iso_date >= ?")
        params.append(from_iso)
    if to_iso:
        conds.append("ri.iso_date <= ?")
        params.append(to_iso)
    if brand_name:
        conds.append("ri.brand_name = ?")
        params.append(brand_name)
    if price_min is not None:
        conds.append("ri.final_price >= ?")
        params.append(price_min)
    if price_max is not None:
        conds.append("ri.final_price < ?")
        params.append(price_max)
    if search:
        like = f"%{search}%"
        conds.append("(ri.cash_customer_name LIKE ? OR ri.cash_customer_contact LIKE ?)")
        params += [like, like]

    where = ("WHERE " + " AND ".join(conds)) if conds else ""

    sql = f"""
    WITH ranked_sales AS (
        -- For each unique contact, rank sales newest-first (ISO date DESC, then id DESC)
        SELECT
            sv.id          AS sv_id,
            sv.date,
            {de_sv}        AS iso_date,
            sv.cash_customer_name,
            sv.cash_customer_contact,
            ROW_NUMBER() OVER (
                PARTITION BY sv.cash_customer_contact
                ORDER BY {de_sv} DESC, sv.id DESC
            ) AS rn
        FROM sale_vouchers sv
        WHERE sv.type = 'cash'
          AND sv.cash_customer_contact IS NOT NULL
          AND TRIM(sv.cash_customer_contact) != ''
    ),
    latest_sale AS (
        -- Keep only the most recent sale per contact
        SELECT sv_id, date, iso_date, cash_customer_name, cash_customer_contact
        FROM ranked_sales
        WHERE rn = 1
    ),
    ranked_items AS (
        -- For each latest sale, rank its items highest-price-first
        SELECT
            ls.cash_customer_contact,
            ls.cash_customer_name,
            ls.date,
            ls.iso_date,
            m.name    AS model_name,
            b.name    AS brand_name,
            sl.final_price,
            ROW_NUMBER() OVER (
                PARTITION BY ls.sv_id
                ORDER BY sl.final_price DESC, sl.id DESC
            ) AS item_rn
        FROM latest_sale ls
        JOIN sale_lines sl ON sl.sv_id  = ls.sv_id
        JOIN models     m  ON m.id      = sl.model_id
        JOIN brands     b  ON b.id      = m.brand_id
    ),
    ri AS (
        SELECT cash_customer_contact, cash_customer_name,
               date, iso_date, model_name, brand_name, final_price
        FROM ranked_items
        WHERE item_rn = 1
    )
    SELECT
        ri.cash_customer_name,
        ri.cash_customer_contact,
        ri.model_name,
        ri.brand_name,
        ri.final_price,
        ri.date,
        ri.iso_date
    FROM ri
    {where}
    ORDER BY ri.iso_date DESC, ri.cash_customer_contact
    """

    conn = get_connection()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


class CustomerInsightsTab(QWidget):
    """
    Tab 8 — Customer Insights.

    Shows cash customers (one row per unique phone number) with their most
    recent purchase.  Filters: brand, price range, date range, free-text search.
    Exports to CSV with date-stamped filename.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loaded = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # ── Filter card ───────────────────────────────────────────────────────
        filter_card = QFrame()
        filter_card.setStyleSheet(CARD_STYLE)
        fc_layout = QVBoxLayout(filter_card)
        fc_layout.setContentsMargins(12, 10, 12, 10)
        fc_layout.setSpacing(8)

        # Row 1: date range + search
        row1 = QHBoxLayout()
        row1.setSpacing(10)

        row1.addWidget(QLabel("From:"))
        self.from_date = QDateEdit(QDate.currentDate().addYears(-1))
        self.from_date.setDisplayFormat("dd/MM/yyyy")
        self.from_date.setCalendarPopup(True)
        row1.addWidget(self.from_date)

        row1.addWidget(QLabel("To:"))
        self.to_date = QDateEdit(QDate.currentDate())
        self.to_date.setDisplayFormat("dd/MM/yyyy")
        self.to_date.setCalendarPopup(True)
        row1.addWidget(self.to_date)

        row1.addSpacing(10)
        row1.addWidget(QLabel("Search:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Name or phone number…")
        self.search_edit.setMinimumWidth(200)
        self.search_edit.returnPressed.connect(self.refresh)
        row1.addWidget(self.search_edit)

        row1.addStretch()

        # Export CSV — top right of filter card
        self.btn_export = QPushButton("⬇ Export CSV")
        self.btn_export.setStyleSheet(BTN_PRIMARY)
        self.btn_export.clicked.connect(self._export)
        row1.addWidget(self.btn_export)

        fc_layout.addLayout(row1)

        # Row 2: brand + price range + Apply + Reset
        row2 = QHBoxLayout()
        row2.setSpacing(10)

        row2.addWidget(QLabel("Brand:"))
        self.brand_combo = QComboBox()
        self.brand_combo.setMinimumWidth(150)
        self.brand_combo.addItem("All Brands", None)
        for b in db_brands_list():
            self.brand_combo.addItem(b["name"], b["name"])
        row2.addWidget(self.brand_combo)

        row2.addWidget(QLabel("Price Range:"))
        self.price_combo = QComboBox()
        self.price_combo.setMinimumWidth(200)
        for label, pmin, pmax in _PRICE_RANGES:
            self.price_combo.addItem(label, (pmin, pmax))
        row2.addWidget(self.price_combo)

        row2.addStretch()

        btn_apply = QPushButton("Apply Filters")
        btn_apply.setStyleSheet(BTN_SECONDARY)
        btn_apply.clicked.connect(self.refresh)
        row2.addWidget(btn_apply)

        btn_reset = QPushButton("Reset")
        btn_reset.setStyleSheet(BTN_SECONDARY)
        btn_reset.clicked.connect(self._reset)
        row2.addWidget(btn_reset)

        fc_layout.addLayout(row2)
        layout.addWidget(filter_card)

        # ── Results table ─────────────────────────────────────────────────────
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "#", "Customer Name", "Contact Number",
            "Last Model Bought", "Brand", "Sale Price (Rs.)", "Date of Purchase",
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)            # #
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)          # Name
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents) # Contact
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)          # Model
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents) # Brand
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents) # Price
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents) # Date
        hdr.setStretchLastSection(False)
        self.table.setColumnWidth(0, 42)
        self.table.setStyleSheet(TABLE_STYLE)
        layout.addWidget(self.table, stretch=1)

        # ── Footer: count ─────────────────────────────────────────────────────
        self.footer = QLabel("")
        self.footer.setStyleSheet(TOTAL_STYLE)
        layout.addWidget(self.footer)

    # ── Lazy load ─────────────────────────────────────────────────────────────
    def ensure_loaded(self):
        if not self._loaded:
            self.refresh()
            self._loaded = True

    # ── Reset filters ─────────────────────────────────────────────────────────
    def _reset(self):
        self.from_date.setDate(QDate.currentDate().addYears(-1))
        self.to_date.setDate(QDate.currentDate())
        self.brand_combo.setCurrentIndex(0)
        self.price_combo.setCurrentIndex(0)
        self.search_edit.clear()
        self.refresh()

    # ── Query and populate ────────────────────────────────────────────────────
    def refresh(self):
        from_iso = self.from_date.date().toString("yyyy-MM-dd")
        to_iso   = self.to_date.date().toString("yyyy-MM-dd")
        brand    = self.brand_combo.currentData()      # None or brand name str
        price_rng = self.price_combo.currentData()     # (min, max) tuple
        price_min, price_max = price_rng if price_rng else (None, None)
        search   = self.search_edit.text().strip() or None

        rows = db_customer_insights(
            from_iso=from_iso,
            to_iso=to_iso,
            brand_name=brand,
            price_min=price_min,
            price_max=price_max,
            search=search,
        )

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        for idx, r in enumerate(rows, start=1):
            row = self.table.rowCount()
            self.table.insertRow(row)

            # # (sequence number)
            num = QTableWidgetItem(str(idx))
            num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, num)

            self.table.setItem(row, 1,
                QTableWidgetItem(r["cash_customer_name"] or "—"))
            self.table.setItem(row, 2,
                QTableWidgetItem(r["cash_customer_contact"] or "—"))
            self.table.setItem(row, 3,
                QTableWidgetItem(r["model_name"] or "—"))
            self.table.setItem(row, 4,
                QTableWidgetItem(r["brand_name"] or "—"))

            price_item = QTableWidgetItem(fmt_pkr(r["final_price"]))
            price_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 5, price_item)

            self.table.setItem(row, 6,
                QTableWidgetItem(r["date"] or "—"))

        self.table.setSortingEnabled(True)

        n = len(rows)
        if n == 0:
            # Check whether there are ANY cash sales at all
            conn = get_connection()
            any_cash = conn.execute(
                "SELECT 1 FROM sale_vouchers WHERE type='cash' LIMIT 1"
            ).fetchone()
            conn.close()
            if any_cash:
                self.footer.setText("No customers found matching the selected filters.")
            else:
                self.footer.setText("No cash sales recorded yet.")
        else:
            self.footer.setText(
                f"{n} customer{'s' if n != 1 else ''} found"
            )

    # ── CSV export ────────────────────────────────────────────────────────────
    def _export(self):
        from datetime import date as _dt_date
        today = _dt_date.today().strftime("%d%m%Y")
        _export_table_csv(self.table, f"CustomerInsights_{today}.csv", self)


# ── Tab 9: Expenses by Category ───────────────────────────────────────────────
# Categories come from the single source of truth: database.EXPENSE_CATEGORIES.


class ExpensesReportTab(QWidget):
    """
    Shows expenses grouped by category for a date range.
    Summary table: Category | Count | Total Amount.
    Expandable detail section below (all individual rows for the period).
    CSV export.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loaded = False
        self._detail_data = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # ── Filter card ──────────────────────────────────────────────────
        filter_card = QFrame()
        filter_card.setStyleSheet(CARD_STYLE)
        fl = QHBoxLayout(filter_card)
        fl.setContentsMargins(12, 10, 12, 10)
        fl.setSpacing(10)

        fl.addWidget(QLabel("From:"))
        self.from_date = QDateEdit(QDate.currentDate().addMonths(-1))
        self.from_date.setDisplayFormat("dd/MM/yyyy")
        self.from_date.setCalendarPopup(True)
        fl.addWidget(self.from_date)

        fl.addWidget(QLabel("To:"))
        self.to_date = QDateEdit(QDate.currentDate())
        self.to_date.setDisplayFormat("dd/MM/yyyy")
        self.to_date.setCalendarPopup(True)
        fl.addWidget(self.to_date)

        fl.addWidget(QLabel("Category:"))
        self.cat_combo = QComboBox()
        self.cat_combo.addItem("All Categories", "")
        for c in EXPENSE_CATEGORIES:
            self.cat_combo.addItem(c, c)
        for ec in db_expense_categories():
            if ec["name"] not in EXPENSE_CATEGORIES:
                self.cat_combo.addItem(ec["name"], ec["name"])
        self.cat_combo.setMinimumWidth(140)
        fl.addWidget(self.cat_combo)

        btn_search = QPushButton("Search")
        btn_search.setStyleSheet(BTN_SECONDARY)
        btn_search.clicked.connect(self.refresh)
        fl.addWidget(btn_search)

        fl.addStretch()

        btn_export = QPushButton("⬇ Export CSV")
        btn_export.setStyleSheet(BTN_PRIMARY)
        btn_export.clicked.connect(self._export)
        fl.addWidget(btn_export)

        layout.addWidget(filter_card)

        # ── Summary table (by category) ──────────────────────────────────
        self.summary_table = _make_table(["Category", "No. of Expenses", "Total Amount (Rs.)"])
        self.summary_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.summary_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.summary_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self.summary_table.horizontalHeader().setStretchLastSection(False)
        self.summary_table.setMaximumHeight(260)
        layout.addWidget(self.summary_table)

        # ── Total footer ─────────────────────────────────────────────────
        self.footer = QLabel("")
        self.footer.setStyleSheet(TOTAL_STYLE)
        layout.addWidget(self.footer)

        # ── Detail table (all individual expenses) ────────────────────────
        detail_label = QLabel("Individual Expenses")
        detail_label.setStyleSheet("color:#475569; font-size:9pt; font-weight:bold;")
        layout.addWidget(detail_label)

        self.detail_table = _make_table(
            ["Date", "Expense #", "Category", "Description",
             "Amount (Rs.)", "Payment", "Bank"]
        )
        hdr = self.detail_table.horizontalHeader()
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        hdr.setStretchLastSection(False)
        layout.addWidget(self.detail_table, stretch=1)

    def ensure_loaded(self):
        if not self._loaded:
            self.refresh()
            self._loaded = True

    def refresh(self):
        from_iso = self.from_date.date().toString("yyyy-MM-dd")
        to_iso   = self.to_date.date().toString("yyyy-MM-dd")
        category = self.cat_combo.currentData()

        data = db_all_expenses_combined(from_iso, to_iso, category)

        # ── Populate summary table ────────────────────────────────────────
        self.summary_table.setSortingEnabled(False)
        self.summary_table.setRowCount(0)

        max_total = max((r["total"] for r in data["rows"]), default=1) or 1

        for r in data["rows"]:
            row = self.summary_table.rowCount()
            self.summary_table.insertRow(row)

            # Category name with a subtle bar indicator
            pct   = int(r["total"] / max_total * 100)
            bar   = "█" * (pct // 10) + "░" * (10 - pct // 10)
            cat_item = QTableWidgetItem(f"{r['category']}  {bar}")
            cat_item.setForeground(QBrush(QColor("#1e293b")))
            self.summary_table.setItem(row, 0, cat_item)

            cnt_item = QTableWidgetItem(str(r["count"]))
            cnt_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.summary_table.setItem(row, 1, cnt_item)

            amt_item = QTableWidgetItem(fmt_pkr(r["total"]))
            amt_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            amt_item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            self.summary_table.setItem(row, 2, amt_item)

        self.summary_table.setSortingEnabled(True)

        # Footer
        n = data["grand_count"]
        t = data["grand_total"]
        self.footer.setText(
            f"{n} expense{'s' if n != 1 else ''}    |    "
            f"Grand Total:  Rs. {fmt_pkr(t)}"
        )

        # ── Populate detail table ─────────────────────────────────────────
        self.detail_table.setSortingEnabled(False)
        self.detail_table.setRowCount(0)
        self._detail_data = data["detail"]

        for d in data["detail"]:
            row = self.detail_table.rowCount()
            self.detail_table.insertRow(row)
            self.detail_table.setItem(row, 0, QTableWidgetItem(d["date"]))
            self.detail_table.setItem(row, 1, QTableWidgetItem(d["expense_number"]))
            self.detail_table.setItem(row, 2, QTableWidgetItem(d["category"]))
            self.detail_table.setItem(row, 3, QTableWidgetItem(d["description"]))
            amt = QTableWidgetItem(fmt_pkr(d["amount"]))
            amt.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.detail_table.setItem(row, 4, amt)
            self.detail_table.setItem(row, 5, QTableWidgetItem(
                d["payment_method"].capitalize()
            ))
            self.detail_table.setItem(row, 6, QTableWidgetItem(d["bank_name"]))

        self.detail_table.setSortingEnabled(True)

    def _export(self):
        from_iso = self.from_date.date().toString("yyyy-MM-dd")
        to_iso   = self.to_date.date().toString("yyyy-MM-dd")
        default  = f"Expenses_{from_iso}_to_{to_iso}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Expenses", default, "CSV Files (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(
                    ["Date", "Expense #", "Category", "Description",
                     "Amount", "Payment Method", "Bank"]
                )
                for d in self._detail_data:
                    writer.writerow([
                        d["date"], d["expense_number"], d["category"],
                        d["description"], d["amount"],
                        d["payment_method"], d["bank_name"],
                    ])
            QMessageBox.information(self, "Exported", f"Saved to:\n{path}")
        except Exception as ex:
            QMessageBox.warning(self, "Export Error", str(ex))


# ── Reports Page ──────────────────────────────────────────────────────────────

# ── Closing Balances ──────────────────────────────────────────────────────────

def db_closing_balances() -> dict:
    """
    Gather every account's current closing balance for the Closing Balances report.
      Receivables  — each credit customer (positive = they owe you)
      Payables     — each supplier (positive = you owe them); id=0 / OPENING STOCK excluded
      Other Parties— each loan/personal account with balance + direction
      Bank Accounts— each bank with current balance
      Cash in Hand — current cash balance
      Incentives   — total accumulated income
    """
    conn = get_connection()

    customers = conn.execute(
        "SELECT id, name FROM customers WHERE type='credit' ORDER BY name"
    ).fetchall()
    receivables = [
        {"name": c["name"], "balance": _party_closing_balance(conn, "customer", c["id"])}
        for c in customers
    ]

    suppliers = conn.execute(
        "SELECT id, name FROM suppliers WHERE id != 0 ORDER BY name"
    ).fetchall()
    payables = []
    for s in suppliers:
        if "OPENING STOCK" in s["name"].upper():
            continue
        payables.append({"name": s["name"],
                         "balance": _party_closing_balance(conn, "supplier", s["id"])})

    others = []
    try:
        rows = conn.execute("SELECT id, name FROM other_parties ORDER BY name").fetchall()
        for op in rows:
            bal = _party_closing_balance(conn, "other", op["id"])
            direction = "Payable" if bal > 0 else ("Receivable" if bal < 0 else "-")
            others.append({"name": op["name"], "balance": bal, "direction": direction})
    except Exception:
        pass  # other_parties table absent on very old DBs

    conn.close()

    banks = [
        {"name": ba["name"], "balance": db_bank_account_closing_balance(ba["id"])}
        for ba in db_bank_accounts()
    ]

    return {
        "receivables":       receivables,
        "receivables_total": sum(r["balance"] for r in receivables),
        "payables":          payables,
        "payables_total":    sum(p["balance"] for p in payables),
        "others":            others,
        "others_total":      sum(o["balance"] for o in others),
        "banks":             banks,
        "banks_total":       sum(b["balance"] for b in banks),
        "cash":              db_cash_in_hand(),
        "incentives":        db_incentives_income_total(),
    }


class ClosingBalancesTab(QWidget):
    """All account closing balances in one place, grouped with per-group totals."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loaded = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        header = QHBoxLayout()
        self._date_lbl = QLabel("")
        self._date_lbl.setStyleSheet("color:#1e293b; font-size:12pt; font-weight:bold;")
        header.addWidget(self._date_lbl)
        header.addStretch()
        btn_refresh = QPushButton("Refresh")
        btn_refresh.setStyleSheet(BTN_SECONDARY)
        btn_refresh.clicked.connect(self.refresh)
        header.addWidget(btn_refresh)
        btn_pdf, btn_csv = _make_export_buttons(self)
        header.addWidget(btn_pdf)
        header.addWidget(btn_csv)
        layout.addLayout(header)

        self.table = _make_table(["Account", "Type", "Balance (PKR)"])
        layout.addWidget(self.table, stretch=1)

    def ensure_loaded(self):
        if not self._loaded:
            self.refresh()
            self._loaded = True

    def refresh(self):
        import datetime as _dt
        today = _dt.date.today().strftime("%d/%m/%Y")
        self._date_lbl.setText(f"Closing Balances  —  as at {today}")

        d = db_closing_balances()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        def _section(title):
            row = self.table.rowCount()
            self.table.insertRow(row)
            item = QTableWidgetItem(title)
            item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            item.setBackground(QBrush(QColor("#cbd5e1")))
            item.setForeground(QBrush(QColor("#1e293b")))
            self.table.setItem(row, 0, item)
            self.table.setSpan(row, 0, 1, 3)

        def _item(name, typ, bal, total=False):
            row = self.table.rowCount()
            self.table.insertRow(row)
            name_item = QTableWidgetItem(name)
            type_item = QTableWidgetItem(typ)
            bal_item = QTableWidgetItem(fmt_pkr(bal))
            bal_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            bal_item.setForeground(
                QBrush(QColor("#16a34a") if bal >= 0 else QColor("#dc2626"))
            )
            if total:
                bold = QFont("Segoe UI", 10, QFont.Weight.Bold)
                for it in (name_item, type_item, bal_item):
                    it.setFont(bold)
                    it.setBackground(QBrush(QColor("#f1f5f9")))
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, type_item)
            self.table.setItem(row, 2, bal_item)

        _section("RECEIVABLES — Credit Customers")
        for r in d["receivables"]:
            _item(r["name"], "Receivable", r["balance"])
        _item("Total Receivables", "", d["receivables_total"], total=True)

        _section("PAYABLES — Suppliers")
        for p in d["payables"]:
            _item(p["name"], "Payable", p["balance"])
        _item("Total Payables", "", d["payables_total"], total=True)

        if d["others"]:
            _section("OTHER PARTIES")
            for o in d["others"]:
                _item(o["name"], o["direction"], o["balance"])
            _item("Total Other Parties", "", d["others_total"], total=True)

        _section("BANK ACCOUNTS")
        for b in d["banks"]:
            _item(b["name"], "Bank", b["balance"])
        _item("Total Bank", "", d["banks_total"], total=True)

        _section("CASH IN HAND")
        _item("Cash in Hand", "Cash", d["cash"], total=True)

        _section("INCENTIVES INCOME")
        _item("Incentives Income (accumulated)", "Income", d["incentives"], total=True)

    def _export_payload(self):
        if not self._loaded:
            self.refresh()
            self._loaded = True
        headers, rows = _table_to_rows(self.table)
        today = datetime.date.today().strftime("%d/%m/%Y")
        return ("Closing_Balances", f"Closing Balances — as at {today}",
                headers, rows, {2})


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
        self._tab_customers  = CustomerInsightsTab()
        self._tab_expenses   = ExpensesReportTab()
        self._tab_closing    = ClosingBalancesTab()

        self.tabs.addTab(self._tab_stock,      "Stock Summary")
        self.tabs.addTab(self._tab_imei_stock, "IMEI Stock")
        self.tabs.addTab(self._tab_valuation,  "Stock Valuation")
        self.tabs.addTab(self._tab_sales,      "Sales")
        self.tabs.addTab(self._tab_purchases,  "Purchases")
        self.tabs.addTab(self._tab_profit,     "Profit")
        self.tabs.addTab(self._tab_cashbook,   "Cash Book")
        self.tabs.addTab(self._tab_customers,  "Customer Insights")
        self.tabs.addTab(self._tab_expenses,   "Expenses")
        self.tabs.addTab(self._tab_closing,    "Closing Balances")

        self.tabs.currentChanged.connect(self._on_tab_change)
        layout.addWidget(self.tabs)

    def set_use_in_sale_cb(self, cb):
        self._tab_imei_stock.set_use_in_sale_cb(cb)

    def _on_tab_change(self, index):
        tab = self.tabs.widget(index)
        if hasattr(tab, "ensure_loaded"):
            tab.ensure_loaded()
