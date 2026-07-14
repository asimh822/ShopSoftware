import sqlite3
from datetime import date as _date
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QComboBox, QLineEdit,
    QDoubleSpinBox, QDateEdit, QDialog, QDialogButtonBox,
    QMessageBox, QHeaderView, QAbstractItemView, QFrame, QTextEdit,
    QStackedWidget, QCheckBox, QTabWidget, QListWidget, QListWidgetItem,
)
from PyQt6.QtCore import Qt, QDate, QPoint, QTimer, QEvent, pyqtSignal
from PyQt6.QtGui import QFont, QBrush, QColor, QShortcut, QKeySequence

from database import get_connection, _insert_party_journal_line, db_remove_stock_item
from widgets import SearchableComboBox

# ── Shared styles (mirrors masters.py) ───────────────────────────────────────

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
BTN_DANGER_SMALL = """
    QPushButton { background:#fee2e2; color:#dc2626; border:none;
        border-radius:4px; padding:3px 10px; font-size:9pt; }
    QPushButton:hover { background:#fecaca; }
"""
CARD_STYLE = "background:#ffffff; border:1px solid #e2e8f0; border-radius:8px; color:#1e293b;"
STATUS_OK   = "color:#16a34a; font-size:9pt; font-weight:bold;"
STATUS_ERR  = "color:#dc2626; font-size:9pt;"
STATUS_INFO = "color:#64748b; font-size:9pt;"
STATUS_WARN = "color:#d97706; font-size:9pt;"
FORM_INPUT_STYLE = """
    QLineEdit {
        background:#ffffff; color:#1e293b;
        border:1px solid #cbd5e1; border-radius:4px; padding:5px 8px; font-size:10pt;
    }
    QLineEdit:focus { border:2px solid #2563eb; }
    QLineEdit:disabled { background:#f1f5f9; color:#94a3b8; border-color:#e2e8f0; }
    QDoubleSpinBox {
        background:#ffffff; color:#1e293b;
        border:1px solid #cbd5e1; border-radius:4px; padding:4px 8px; font-size:10pt;
    }
    QDoubleSpinBox:disabled { background:#f1f5f9; color:#94a3b8; border-color:#e2e8f0; }
    QComboBox {
        background:#ffffff; color:#1e293b;
        border:1px solid #cbd5e1; border-radius:4px; padding:5px 8px; font-size:10pt;
    }
    QComboBox QAbstractItemView {
        background:#ffffff; color:#1e293b;
        selection-background-color:#dbeafe; selection-color:#1e40af;
    }
    QComboBox:disabled { background:#f1f5f9; color:#94a3b8; border-color:#e2e8f0; }
"""


def fmt_pkr(val):
    if val is None:
        return "0"
    return f"{float(val):,.0f}"


def _apply_toggle_style(btn, active: bool, pos: str):
    """Apply pill-button toggle style. pos: 'left' | 'mid' | 'right'"""
    if pos == "left":
        radius = "border-radius:5px 0 0 5px;"
        border  = ""
    elif pos == "right":
        radius = "border-radius:0 5px 5px 0; border-left:none;"
        border  = ""
    else:
        radius = "border-radius:0; border-left:none;"
        border  = ""
    if active:
        btn.setStyleSheet(
            f"QPushButton {{ background:#2563eb; color:white; border:none;"
            f" padding:5px 16px; font-size:10pt; font-weight:bold; {radius} }}"
        )
    else:
        btn.setStyleSheet(
            f"QPushButton {{ background:#f1f5f9; color:#64748b;"
            f" border:1px solid #cbd5e1; padding:5px 16px; font-size:10pt; {radius} }}"
            f"QPushButton:hover {{ background:#e2e8f0; color:#334155; }}"
        )


def _make_table(headers):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setAlternatingRowColors(True)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setStretchLastSection(False)
    t.setStyleSheet(TABLE_STYLE)
    return t


# ── DB helpers ────────────────────────────────────────────────────────────────

def db_suppliers_list():
    """Returns all real suppliers. Excludes id=0 (system 'Cash Purchase' record)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name FROM suppliers WHERE id != 0 ORDER BY name"
    ).fetchall()
    conn.close()
    return rows


def db_credit_customers_for_purchase():
    """Returns credit customers who can act as purchase suppliers (buying back from them)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name FROM customers WHERE type='credit' ORDER BY name"
    ).fetchall()
    conn.close()
    return rows


def db_supplier_balance(supplier_id):
    """Return outstanding balance for a single supplier (amount you owe them)."""
    conn = get_connection()
    row = conn.execute("""
        SELECT COALESCE(s.opening_balance, 0)
               + COALESCE((SELECT SUM(pv.total_amount) FROM purchase_vouchers pv WHERE pv.supplier_id=s.id), 0)
               - COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.party_type='supplier' AND p.party_id=s.id AND p.type='CP'), 0)
               + COALESCE((SELECT SUM(je.amount) FROM journal_entries je WHERE je.party_type='supplier' AND je.party_id=s.id AND je.type='debit'), 0)
               - COALESCE((SELECT SUM(je.amount) FROM journal_entries je WHERE je.party_type='supplier' AND je.party_id=s.id AND je.type='credit'), 0)
               AS balance
        FROM suppliers s WHERE s.id=?
    """, (supplier_id,)).fetchone()
    conn.close()
    return row["balance"] if row else 0


def db_brands_list():
    conn = get_connection()
    rows = conn.execute("SELECT id, name FROM brands ORDER BY name").fetchall()
    conn.close()
    return rows


def db_models_for_brand(brand_id):
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name, reference_price FROM models WHERE brand_id=? ORDER BY name",
        (brand_id,),
    ).fetchall()
    conn.close()
    return rows


def db_imei_in_stock(imei):
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM stock_items WHERE imei=? AND status='in_stock'", (imei,)
    ).fetchone()
    conn.close()
    return row is not None


def db_imei_exists_active(imei):
    """Returns True if IMEI already exists as in_stock or sold."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM stock_items WHERE imei=? AND status IN ('in_stock', 'sold')", (imei,)
    ).fetchone()
    conn.close()
    return row is not None


def db_save_purchase(date_str, supplier_id, notes, lines,
                      purchase_type="supplier", egadget_ref="",
                      payment_method="", cash_amount=0.0, bank_amount=0.0,
                      bank_account_id=None, bank_ref="",
                      customer_as_supplier_id=None):
    """
    lines = [(model_id, imei, price), ...]  Returns pv_number.
    For cash purchases: supplier_id=0 (system record), egadget_ref required.
    Bank outflow (if bank_amount > 0) is recorded in bank_transactions.
    """
    conn = get_connection()
    try:
        c = conn.cursor()
        row = c.execute(
            "SELECT value FROM settings WHERE key='last_pv_number'"
        ).fetchone()
        n = int(row["value"]) + 1 if row else 1
        c.execute("UPDATE settings SET value=? WHERE key='last_pv_number'", (str(n),))
        pv_number = f"PV-{n:04d}"

        total = sum(price for _, _, price in lines)
        c.execute(
            "INSERT INTO purchase_vouchers "
            "(pv_number, supplier_id, date, total_amount, notes, "
            " purchase_type, egadget_ref, payment_method, "
            " cash_amount, bank_amount, bank_account_id, bank_ref, "
            " customer_as_supplier_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pv_number, supplier_id, date_str, total, notes or "",
             purchase_type, egadget_ref or "", payment_method or "",
             float(cash_amount or 0), float(bank_amount or 0),
             bank_account_id, bank_ref or "",
             customer_as_supplier_id),
        )
        pv_id = c.lastrowid

        for model_id, imei, price in lines:
            c.execute(
                "INSERT INTO purchase_lines (pv_id, model_id, imei, purchase_price) "
                "VALUES (?,?,?,?)",
                (pv_id, model_id, imei, price),
            )
            pl_id = c.lastrowid
            existing = c.execute(
                "SELECT id FROM stock_items WHERE imei=?", (imei,)
            ).fetchone()
            if existing:
                # Phone was previously sold and is being repurchased — reset the record
                c.execute(
                    "UPDATE stock_items SET model_id=?, purchase_line_id=?, purchase_price=?, "
                    "status='in_stock', sold_line_id=NULL WHERE id=?",
                    (model_id, pl_id, price, existing["id"]),
                )
            else:
                c.execute(
                    "INSERT INTO stock_items (model_id, imei, purchase_line_id, purchase_price, status) "
                    "VALUES (?,?,?,?,'in_stock')",
                    (model_id, imei, pl_id, price),
                )

        # Cash purchase paid (partly) by bank — record the bank outflow
        if purchase_type == "cash" and bank_amount and bank_amount > 0 and bank_account_id:
            c.execute(
                "INSERT INTO bank_transactions "
                "(voucher_number, type, bank_account_id, source, date, amount, notes) "
                "VALUES (?,?,?,?,?,?,?)",
                (pv_number, "CR", bank_account_id, "cash_purchase",
                 date_str, float(bank_amount),
                 f"Cash Purchase — {pv_number}"),
            )

        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()
    return pv_number


def _date_expr():
    return "substr(pv.date,7,4)||'-'||substr(pv.date,4,2)||'-'||substr(pv.date,1,2)"


def db_load_purchases(from_iso=None, to_iso=None, supplier_id=None,
                       purchase_type_filter=None):
    conds, params = [], []
    de = _date_expr()
    if from_iso:
        conds.append(f"{de} >= ?")
        params.append(from_iso)
    if to_iso:
        conds.append(f"{de} <= ?")
        params.append(to_iso)
    if supplier_id:
        conds.append("pv.supplier_id = ?")
        params.append(supplier_id)
    if purchase_type_filter == "supplier":
        conds.append("COALESCE(pv.purchase_type,'supplier') = 'supplier'")
    elif purchase_type_filter == "cash":
        conds.append("pv.purchase_type = 'cash'")
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    sql = f"""
        SELECT pv.id, pv.pv_number, pv.date,
               COALESCE(s.name, 'Cash Purchase') AS supplier_name,
               COUNT(pl.id) AS item_count, pv.total_amount, pv.notes,
               COALESCE(pv.purchase_type, 'supplier') AS purchase_type,
               COALESCE(pv.egadget_ref, '') AS egadget_ref
        FROM purchase_vouchers pv
        LEFT JOIN suppliers s ON s.id = pv.supplier_id
        LEFT JOIN purchase_lines pl ON pl.pv_id = pv.id
        {where}
        GROUP BY pv.id
        ORDER BY pv.id DESC
    """
    conn = get_connection()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


def db_load_purchase_lines(pv_id):
    conn = get_connection()
    rows = conn.execute("""
        SELECT b.name AS brand_name, m.name AS model_name, pl.imei, pl.purchase_price
        FROM purchase_lines pl
        JOIN models m ON m.id = pl.model_id
        JOIN brands b ON b.id = m.brand_id
        WHERE pl.pv_id = ?
        ORDER BY pl.id
    """, (pv_id,)).fetchall()
    conn.close()
    return rows


# ── Purchase Return DB helpers ────────────────────────────────────────────────

def db_imei_instock_for_return(suffix: str):
    """Search in-stock IMEIs with supplier info — used for purchase return IMEI lookup."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT si.id AS stock_item_id, TRIM(si.imei) AS imei,
               b.name AS brand_name, m.name AS model_name, m.id AS model_id,
               si.purchase_price,
               COALESCE(pv.date, '') AS purchase_date,
               COALESCE(pv.supplier_id, 0) AS supplier_id,
               COALESCE(s.name, 'Unknown') AS supplier_name
        FROM stock_items si
        JOIN models m ON m.id = si.model_id
        JOIN brands b ON b.id = m.brand_id
        LEFT JOIN purchase_lines pl ON pl.id = si.purchase_line_id
        LEFT JOIN purchase_vouchers pv ON pv.id = pl.pv_id
        LEFT JOIN suppliers s ON s.id = pv.supplier_id
        WHERE TRIM(si.imei) LIKE ? AND si.status = 'in_stock'
        ORDER BY TRIM(si.imei)
    """, ("%" + suffix.strip(),)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

#

def db_save_purchase_return(date_str, supplier_id, lines, notes):
    """
    lines = [(stock_item_id, model_id, imei, return_price), ...]
    Returns (pr_number, pr_id).
    Stock items are DELETED from stock.
    Supplier balance reduced via journal credit.
    """
    conn = get_connection()
    try:
        c = conn.cursor()
        row = c.execute(
            "SELECT value FROM settings WHERE key='last_pr_number'"
        ).fetchone()
        n = int(row["value"]) + 1 if row else 1
        c.execute("UPDATE settings SET value=? WHERE key='last_pr_number'", (str(n),))
        pr_number = f"PR-{n:04d}"

        c.execute(
            "INSERT INTO purchase_returns (pr_number, pv_id, supplier_id, date, notes) "
            "VALUES (?,?,?,?,?)",
            (pr_number, None, supplier_id, date_str, notes or ""),
        )
        pr_id = c.lastrowid

        total_return = 0.0
        for stock_item_id, model_id, imei, return_price in lines:
            # Store line WITHOUT stock_item_id — we are about to delete that record
            c.execute(
                "INSERT INTO purchase_return_lines "
                "(pr_id, stock_item_id, model_id, imei, return_price) VALUES (?,?,?,?,?)",
                (pr_id, None, model_id, imei, return_price),
            )
            # Remove the phone from stock (reverts to 'sold' state if it has
            # sale history — see db_remove_stock_item)
            db_remove_stock_item(c, stock_item_id)
            total_return += return_price

        # Reduce supplier balance — journal credit means we owe them less
        _insert_party_journal_line(
            c, "supplier", supplier_id, date_str,
            debit=total_return, credit=0,
            notes=f"Purchase Return — {pr_number}",
        )

        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()
    return pr_number, pr_id


def db_load_purchase_returns(from_iso=None, to_iso=None):
    """Load all purchase returns with optional date range filters."""
    conds, params = [], []
    de = "substr(pr.date,7,4)||'-'||substr(pr.date,4,2)||'-'||substr(pr.date,1,2)"
    if from_iso:
        conds.append(f"{de} >= ?")
        params.append(from_iso)
    if to_iso:
        conds.append(f"{de} <= ?")
        params.append(to_iso)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    sql = f"""
        SELECT pr.id, pr.pr_number, pr.date, pr.notes,
               s.name AS supplier_name,
               COUNT(prl.id) AS item_count,
               COALESCE(SUM(prl.return_price), 0) AS return_amount
        FROM purchase_returns pr
        JOIN suppliers s ON s.id = pr.supplier_id
        LEFT JOIN purchase_return_lines prl ON prl.pr_id = pr.id
        {where}
        GROUP BY pr.id
        ORDER BY pr.id DESC
    """
    conn = get_connection()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Purchase Return IMEI Dropdown ────────────────────────────────────────────

class PurchaseReturnImeiDropdown(QWidget):
    """Floating live-search dropdown for in-stock IMEIs (purchase return use)."""
    imei_chosen = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet(
            "background:#2563eb; border:2px solid #2563eb; border-radius:4px;"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        self._list = QListWidget()
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.setStyleSheet("""
            QListWidget {
                background:#ffffff; border:none;
                font-size:10pt; font-family:"Consolas","Courier New",monospace;
            }
            QListWidget::item { padding:6px 14px; border-bottom:1px solid #f1f5f9; }
            QListWidget::item:hover { background:#dbeafe; color:#1e40af; }
            QListWidget::item:selected { background:#2563eb; color:#ffffff; }
        """)
        self._list.itemClicked.connect(self._on_click)
        layout.addWidget(self._list)

    def _on_click(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        if data:
            self.imei_chosen.emit(data)
        self.hide()

    def show_below(self, anchor: QWidget, results: list):
        self._list.clear()
        if not results:
            it = QListWidgetItem("  No in-stock IMEI found")
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            it.setForeground(QBrush(QColor("#94a3b8")))
            self._list.addItem(it)
        else:
            for r in results:
                text = (f"  {r['imei']}    {r['brand_name']} {r['model_name']}"
                        f"    {r['supplier_name']}    PKR {fmt_pkr(r['purchase_price'])}")
                it = QListWidgetItem(text)
                it.setData(Qt.ItemDataRole.UserRole, r)
                self._list.addItem(it)
        pos = anchor.mapToGlobal(QPoint(0, anchor.height()))
        self.move(pos)
        visible_rows = min(max(len(results), 1), 8)
        self.resize(max(anchor.width(), 620), visible_rows * 34 + 2)
        self.show()

    def move_selection(self, delta: int):
        count = self._list.count()
        if count == 0:
            return
        current = self._list.currentRow()
        new_row = 0 if current < 0 and delta > 0 else max(0, min((current + delta), count - 1))
        item = self._list.item(new_row)
        if item and item.data(Qt.ItemDataRole.UserRole):
            self._list.setCurrentRow(new_row)

    def confirm_selection(self):
        item = self._list.currentItem()
        if item and item.data(Qt.ItemDataRole.UserRole):
            self._on_click(item)
            return
        for i in range(self._list.count()):
            it = self._list.item(i)
            if it and it.data(Qt.ItemDataRole.UserRole):
                self._on_click(it)
                return
        self.hide()


# ── Purchase Return Form ──────────────────────────────────────────────────────

class PurchaseReturnForm(QWidget):
    def __init__(self, on_save, on_cancel, parent=None):
        super().__init__(parent)
        self._on_save = on_save
        self._on_cancel = on_cancel
        # (stock_item_id, model_id, brand, model, imei, purchase_date, purchase_price)
        self._lines = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        self.setStyleSheet(FORM_INPUT_STYLE)

        # ── Header card ───────────────────────────────────────────────────────
        header = QFrame()
        header.setStyleSheet(CARD_STYLE)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(12, 8, 12, 8)
        hl.setSpacing(8)

        hl.addWidget(QLabel("Return Date:"))
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setMinimumWidth(130)
        hl.addWidget(self.date_edit)

        hl.addSpacing(8)
        hl.addWidget(QLabel("Supplier *:"))
        self.supplier_combo = SearchableComboBox()
        self.supplier_combo.setMinimumWidth(200)
        self.supplier_combo.addItem("— Select Supplier —", None)
        for s in db_suppliers_list():
            self.supplier_combo.addItem(s["name"], s["id"])
        self.supplier_combo.currentIndexChanged.connect(self._on_supplier_changed)
        hl.addWidget(self.supplier_combo)

        hl.addSpacing(8)
        hl.addWidget(QLabel("Notes (optional):"))
        self.notes_edit = QLineEdit()
        self.notes_edit.setPlaceholderText("Reason for return")
        self.notes_edit.setMinimumWidth(220)
        hl.addWidget(self.notes_edit)

        hl.addStretch()
        layout.addWidget(header)

        # ── IMEI lookup card ──────────────────────────────────────────────────
        lookup_card = QFrame()
        lookup_card.setStyleSheet(CARD_STYLE)
        ll = QVBoxLayout(lookup_card)
        ll.setContentsMargins(16, 12, 16, 12)
        ll.setSpacing(8)

        search_row = QHBoxLayout()
        search_row.setSpacing(10)
        search_row.addWidget(QLabel("IMEI (last digits):"))
        self.imei_input = QLineEdit()
        self.imei_input.setPlaceholderText(
            "Type last 5+ digits — matching in-stock phones appear"
        )
        self.imei_input.setMinimumWidth(280)
        self.imei_input.setEnabled(False)
        self.imei_input.setProperty("enterKeepDefault", True)
        self.imei_input.textChanged.connect(self._on_imei_changed)
        self.imei_input.returnPressed.connect(self._imei_enter)
        search_row.addWidget(self.imei_input)
        search_row.addStretch()
        ll.addLayout(search_row)

        self._imei_dropdown = PurchaseReturnImeiDropdown(self)
        self._imei_dropdown.imei_chosen.connect(self._on_imei_selected)
        self.imei_input.installEventFilter(self)

        self.lookup_status = QLabel("Select a supplier first, then search by IMEI.")
        self.lookup_status.setStyleSheet(STATUS_INFO)
        ll.addWidget(self.lookup_status)
        layout.addWidget(lookup_card)

        # ── Lines table ───────────────────────────────────────────────────────
        self.lines_table = _make_table(
            ["#", "Brand", "Model", "IMEI", "Purchase Date", "Purchase Price (PKR)", ""]
        )
        _lh = self.lines_table.horizontalHeader()
        _lh.setStretchLastSection(False)
        _lh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)       # #
        _lh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)     # Brand
        _lh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)     # Model
        _lh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # IMEI
        _lh.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)       # Purchase Date
        _lh.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)       # Purchase Price
        _lh.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)       # Remove btn
        self.lines_table.setColumnWidth(0, 35)
        self.lines_table.setColumnWidth(4, 110)
        self.lines_table.setColumnWidth(5, 160)
        self.lines_table.setColumnWidth(6, 80)
        layout.addWidget(self.lines_table, stretch=1)

        # ── Pinned footer strip ───────────────────────────────────────────────
        footer_strip = QHBoxLayout()
        footer_strip.setSpacing(8)
        self.total_label = QLabel("Return Total: PKR 0")
        self.total_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.total_label.setStyleSheet("color:#dc2626;")
        footer_strip.addWidget(self.total_label)
        footer_strip.addStretch()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet(BTN_SECONDARY)
        btn_cancel.clicked.connect(on_cancel)
        self.btn_save = QPushButton("Save Return  [F9]")
        self.btn_save.setStyleSheet(BTN_PRIMARY)
        self.btn_save.setEnabled(False)
        self.btn_save.clicked.connect(self._save)
        QShortcut(QKeySequence("F9"), self).activated.connect(self.btn_save.click)
        footer_strip.addWidget(btn_cancel)
        footer_strip.addWidget(self.btn_save)
        layout.addLayout(footer_strip)

    # ── Supplier / IMEI events ────────────────────────────────────────────────

    def _on_supplier_changed(self):
        has = self.supplier_combo.currentData() is not None
        self.imei_input.setEnabled(has)
        if has:
            self.lookup_status.setText(
                "Type last 5+ digits of IMEI to find in-stock phones."
            )
            self.lookup_status.setStyleSheet(STATUS_INFO)
            self.imei_input.setFocus()
        else:
            self.imei_input.clear()
            self._imei_dropdown.hide()
            self.lookup_status.setText("Select a supplier first.")
            self.lookup_status.setStyleSheet(STATUS_INFO)

    def _on_imei_changed(self, text):
        text = text.strip()
        if len(text) < 5:
            self._imei_dropdown.hide()
            self.lookup_status.setText(
                f"Type {5 - len(text)} more digit(s)…" if text else "Type last 5+ digits of IMEI."
            )
            self.lookup_status.setStyleSheet(STATUS_INFO)
            return
        results = db_imei_instock_for_return(text)
        self._imei_dropdown.show_below(self.imei_input, results)
        if results:
            self.lookup_status.setText(
                f"{len(results)} phone(s) found — select from the dropdown."
            )
            self.lookup_status.setStyleSheet(STATUS_INFO)
        else:
            self.lookup_status.setText("No in-stock phone found for these digits.")
            self.lookup_status.setStyleSheet(STATUS_ERR)

    def _imei_enter(self):
        if self._imei_dropdown.isVisible():
            self._imei_dropdown.confirm_selection()

    def _on_imei_selected(self, data: dict):
        self.imei_input.blockSignals(True)
        self.imei_input.setText(data["imei"])
        self.imei_input.blockSignals(False)
        self._imei_dropdown.hide()

        supplier_id   = self.supplier_combo.currentData()
        supplier_name = self.supplier_combo.currentText()
        imei          = data["imei"]

        if any(l[4] == imei for l in self._lines):
            self.lookup_status.setText(f"IMEI {imei} is already in the return list.")
            self.lookup_status.setStyleSheet(STATUS_WARN)
            self.imei_input.clear()
            return

        actual_sid  = data.get("supplier_id", 0)
        actual_name = data.get("supplier_name", "Unknown")

        if actual_sid != supplier_id:
            QMessageBox.warning(
                self, "Wrong Supplier",
                f"This IMEI was purchased from {actual_name} — "
                f"cannot return to {supplier_name}."
            )
            self.lookup_status.setText("IMEI belongs to a different supplier.")
            self.lookup_status.setStyleSheet(STATUS_ERR)
            self.imei_input.clear()
            return

        self._lines.append((
            data["stock_item_id"], data["model_id"],
            data["brand_name"], data["model_name"],
            imei, data["purchase_date"], data["purchase_price"],
        ))
        self._refresh_lines_table()
        self.imei_input.clear()
        self.imei_input.setFocus()
        self.lookup_status.setText(
            f"✓ Added: {data['brand_name']} {data['model_name']} — {imei}"
        )
        self.lookup_status.setStyleSheet(STATUS_OK)

    # ── Lines table ───────────────────────────────────────────────────────────

    def _refresh_lines_table(self):
        self.lines_table.setRowCount(0)
        total = 0
        for idx, (sid, mid, brand, model, imei, pdate, price) in enumerate(self._lines):
            r = self.lines_table.rowCount()
            self.lines_table.insertRow(r)
            num = QTableWidgetItem(str(idx + 1))
            num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.lines_table.setItem(r, 0, num)
            self.lines_table.setItem(r, 1, QTableWidgetItem(brand))
            self.lines_table.setItem(r, 2, QTableWidgetItem(model))
            self.lines_table.setItem(r, 3, QTableWidgetItem(imei))
            self.lines_table.setItem(r, 4, QTableWidgetItem(pdate or "—"))
            p_item = QTableWidgetItem(fmt_pkr(price))
            p_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.lines_table.setItem(r, 5, p_item)
            del_btn = QPushButton("Remove")
            del_btn.setStyleSheet(BTN_DANGER_SMALL)
            del_btn.clicked.connect(lambda _, i=idx: self._remove_line(i))
            self.lines_table.setCellWidget(r, 6, del_btn)
            total += price
        self.total_label.setText(f"Return Total: PKR {fmt_pkr(total)}")
        self.btn_save.setEnabled(bool(self._lines))

    def _remove_line(self, idx):
        self._lines.pop(idx)
        self._refresh_lines_table()

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save(self):
        supplier_id = self.supplier_combo.currentData()
        if not supplier_id:
            QMessageBox.warning(self, "Missing", "Please select a supplier.")
            return
        if not self._lines:
            QMessageBox.warning(self, "Missing", "Add at least one IMEI to return.")
            return

        date_str = self.date_edit.date().toString("dd/MM/yyyy")
        notes    = self.notes_edit.text().strip()
        db_lines = [(sid, mid, imei, price)
                    for sid, mid, _, _, imei, _, price in self._lines]

        try:
            pr_number, pr_id = db_save_purchase_return(
                date_str, supplier_id, db_lines, notes
            )
        except Exception as ex:
            QMessageBox.critical(self, "Save Error", str(ex))
            return

        try:
            from receipt import print_purchase_return_receipt
            print_purchase_return_receipt(pr_id, parent=self)
        except Exception:
            pass

        total = sum(price for _, _, _, _, _, _, price in self._lines)
        QMessageBox.information(
            self, "Saved",
            f"Purchase return {pr_number} saved.\n"
            f"{len(self._lines)} item(s) removed from stock.\n"
            f"Supplier balance reduced by PKR {fmt_pkr(total)}."
        )
        self._on_save(pr_number)

    def eventFilter(self, obj, event):
        if obj is self.imei_input:
            if event.type() == QEvent.Type.KeyPress and self._imei_dropdown.isVisible():
                key = event.key()
                if key == Qt.Key.Key_Down:
                    self._imei_dropdown.move_selection(1); return True
                if key == Qt.Key.Key_Up:
                    self._imei_dropdown.move_selection(-1); return True
                if key == Qt.Key.Key_Escape:
                    self._imei_dropdown.hide(); return True
            elif event.type() == QEvent.Type.FocusOut:
                QTimer.singleShot(120, lambda: (
                    self._imei_dropdown.hide()
                    if not self.imei_input.hasFocus() else None
                ))
        return super().eventFilter(obj, event)

    def hideEvent(self, event):
        self._imei_dropdown.hide()
        super().hideEvent(event)


# ── Purchase Return List View ──────────────────────────────────────────────────

class PurchaseReturnListView(QWidget):
    def __init__(self, on_new, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        top = QHBoxLayout()
        title = QLabel("Purchase Returns")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title.setStyleSheet("color:#1e293b;")
        top.addWidget(title)
        top.addStretch()
        self.btn_edit_pr = QPushButton("✏ Edit")
        self.btn_edit_pr.setStyleSheet(BTN_SECONDARY)
        self.btn_edit_pr.setEnabled(False)
        self.btn_edit_pr.clicked.connect(self._edit_selected)
        top.addWidget(self.btn_edit_pr)
        self.btn_delete_pr = QPushButton("🗑 Delete")
        self.btn_delete_pr.setStyleSheet("""
            QPushButton { background:#fee2e2; color:#dc2626; border:1px solid #fca5a5;
                border-radius:5px; padding:6px 16px; font-size:10pt; }
            QPushButton:hover { background:#fecaca; }
            QPushButton:disabled { background:#f1f5f9; color:#94a3b8; border-color:#e2e8f0; }
        """)
        self.btn_delete_pr.setEnabled(False)
        self.btn_delete_pr.clicked.connect(self._delete_selected)
        top.addWidget(self.btn_delete_pr)
        btn_new = QPushButton("+ New Return")
        btn_new.setStyleSheet(BTN_PRIMARY)
        btn_new.clicked.connect(on_new)
        top.addWidget(btn_new)
        layout.addLayout(top)

        # Filter bar
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

        btn_search = QPushButton("Search")
        btn_search.setStyleSheet(BTN_SECONDARY)
        btn_search.clicked.connect(self.refresh)
        fl.addWidget(btn_search)

        btn_clear = QPushButton("Clear")
        btn_clear.setStyleSheet(BTN_SECONDARY)
        btn_clear.clicked.connect(self._clear_filters)
        fl.addWidget(btn_clear)

        fl.addStretch()
        layout.addWidget(filter_card)

        self.table = _make_table(
            ["PR Number", "Date", "Supplier", "Items", "Return Amount (PKR)", "Notes"]
        )
        hdr = self.table.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)   # Supplier stretches
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)      # Items
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)      # Return Amount (PKR)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)    # Notes stretches
        self.table.setColumnWidth(3, 55)
        self.table.setColumnWidth(4, 150)
        self.table.doubleClicked.connect(self._edit_selected)
        self.table.itemSelectionChanged.connect(
            lambda: self.btn_edit_pr.setEnabled(self.table.currentRow() >= 0)
        )
        self.table.itemSelectionChanged.connect(
            lambda: self.btn_delete_pr.setEnabled(self.table.currentRow() >= 0)
        )
        layout.addWidget(self.table, stretch=1)

        self.refresh()

    def refresh(self):
        from_iso = self.from_date.date().toString("yyyy-MM-dd")
        to_iso = self.to_date.date().toString("yyyy-MM-dd")
        rows = db_load_purchase_returns(from_iso, to_iso)

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for r in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            pr_item = QTableWidgetItem(r["pr_number"])
            pr_item.setData(Qt.ItemDataRole.UserRole, dict(r))
            self.table.setItem(row, 0, pr_item)
            self.table.setItem(row, 1, QTableWidgetItem(r["date"]))
            self.table.setItem(row, 2, QTableWidgetItem(r["supplier_name"]))
            cnt = QTableWidgetItem(str(r["item_count"]))
            cnt.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 3, cnt)
            amt = QTableWidgetItem(fmt_pkr(r["return_amount"]))
            amt.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.table.setItem(row, 4, amt)
            self.table.setItem(row, 5, QTableWidgetItem(r["notes"] or "—"))
        self.table.setSortingEnabled(True)
        self.btn_edit_pr.setEnabled(False)

    def _clear_filters(self):
        self.from_date.setDate(QDate.currentDate().addMonths(-1))
        self.to_date.setDate(QDate.currentDate())
        self.refresh()

    def _edit_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return
        pr = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        from edit_vouchers import SimpleReturnEditDialog
        dlg = SimpleReturnEditDialog(
            "purchase_return", pr["id"], pr["pr_number"], pr["date"], pr["notes"], self
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _delete_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return
        pr = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        from database import prompt_and_delete_voucher
        deleted = prompt_and_delete_voucher(
            self, "purchase_return", pr["id"], pr["pr_number"], "Owner"
        )
        if deleted:
            self.refresh()


# ── Purchase Detail Dialog ────────────────────────────────────────────────────

class PurchaseDetailDialog(QDialog):
    def __init__(self, pv_row, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Purchase — {pv_row['pv_number']}")
        self.setMinimumWidth(640)
        self.resize(680, 460)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        info = QFrame()
        info.setStyleSheet(CARD_STYLE)
        info_layout = QHBoxLayout(info)
        info_layout.setContentsMargins(16, 12, 16, 12)
        ptype = pv_row.get("purchase_type", "supplier") or "supplier"
        if ptype == "cash":
            egadget = pv_row.get("egadget_ref", "") or ""
            party_label = "Type"
            party_value = f"Cash Purchase" + (f" — Ref: {egadget}" if egadget else "")
        else:
            party_label = "Supplier"
            party_value = pv_row["supplier_name"]
        for label, value in [
            ("PV Number", pv_row["pv_number"]),
            ("Date", pv_row["date"]),
            (party_label, party_value),
            ("Total", f"PKR {fmt_pkr(pv_row['total_amount'])}"),
        ]:
            col = QVBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet("color:#64748b; font-size:9pt;")
            val = QLabel(value)
            val.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            col.addWidget(lbl)
            col.addWidget(val)
            info_layout.addLayout(col)
        if pv_row["notes"]:
            col = QVBoxLayout()
            lbl = QLabel("Notes")
            lbl.setStyleSheet("color:#64748b; font-size:9pt;")
            val = QLabel(pv_row["notes"])
            col.addWidget(lbl)
            col.addWidget(val)
            info_layout.addLayout(col)
        info_layout.addStretch()
        layout.addWidget(info)

        table = _make_table(["Brand", "Model", "IMEI", "Purchase Price (PKR)"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        for r in db_load_purchase_lines(pv_row["id"]):
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(r["brand_name"]))
            table.setItem(row, 1, QTableWidgetItem(r["model_name"]))
            table.setItem(row, 2, QTableWidgetItem(r["imei"]))
            p = QTableWidgetItem(fmt_pkr(r["purchase_price"]))
            p.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row, 3, p)
        layout.addWidget(table)

        btn_delete = QPushButton("🗑 Delete Voucher")
        btn_delete.setStyleSheet("""
            QPushButton { background:#fee2e2; color:#dc2626; border:1px solid #fca5a5;
                border-radius:5px; padding:6px 14px; }
            QPushButton:hover { background:#fecaca; }
        """)
        btn_delete.clicked.connect(lambda: self._delete_and_close(pv_row))
        layout.addWidget(btn_delete)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _delete_and_close(self, pv_row):
        from database import prompt_and_delete_voucher
        deleted = prompt_and_delete_voucher(
            self, "purchase", pv_row["id"], pv_row["pv_number"], "Owner"
        )
        if deleted:
            self.accept()


# ── Purchase Form ─────────────────────────────────────────────────────────────

class PurchaseForm(QWidget):
    def __init__(self, on_save, on_cancel, parent=None):
        super().__init__(parent)
        self._on_save = on_save
        self._on_cancel = on_cancel
        self._lines = []          # [(model_id, brand_name, model_name, imei, net_price)]
        self._current_model_id = None
        self._updating_price = False
        self._purchase_type = "supplier"   # 'supplier' | 'cash'
        self._pay_method    = "cash"       # 'cash' | 'bank' | 'split'
        self._total         = 0.0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        self.setStyleSheet(FORM_INPUT_STYLE)

        # ── Header card ──────────────────────────────────────────────────────
        header_card = QFrame()
        header_card.setStyleSheet(CARD_STYLE)
        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(12, 8, 12, 8)
        header_layout.setSpacing(16)

        # Purchase type toggle (first item in header)
        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(0)
        self._btn_supplier_type = QPushButton("Supplier Purchase")
        self._btn_supplier_type.setFixedHeight(30)
        self._btn_cash_type = QPushButton("Cash Purchase")
        self._btn_cash_type.setFixedHeight(30)
        _apply_toggle_style(self._btn_supplier_type, True,  "left")
        _apply_toggle_style(self._btn_cash_type,     False, "right")
        self._btn_supplier_type.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_cash_type.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn_supplier_type.clicked.connect(lambda: self._set_purchase_type("supplier"))
        self._btn_cash_type.clicked.connect(    lambda: self._set_purchase_type("cash"))
        toggle_row.addWidget(self._btn_supplier_type)
        toggle_row.addWidget(self._btn_cash_type)
        header_layout.addLayout(toggle_row)
        header_layout.addSpacing(12)

        # Date
        header_layout.addWidget(QLabel("Date:"))
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setFixedWidth(108)
        header_layout.addWidget(self.date_edit)

        # Supplier (wrapped in a QWidget so it can be hidden for cash purchases)
        self._sup_widget = QWidget()
        _sup_h = QHBoxLayout(self._sup_widget)
        _sup_h.setContentsMargins(0, 0, 0, 0)
        _sup_h.setSpacing(6)
        _sup_lbl = QLabel("Supplier *:")
        _sup_lbl.setStyleSheet("color:#dc2626; font-weight:bold;")
        _sup_h.addWidget(_sup_lbl)
        self.supplier_combo = SearchableComboBox()
        self.supplier_combo.setMinimumWidth(200)
        self.supplier_combo.addItem("— Select Supplier —", None)
        for s in db_suppliers_list():
            self.supplier_combo.addItem(s["name"], {"type": "supplier", "id": s["id"]})
        _cust_for_pur = db_credit_customers_for_purchase()
        if _cust_for_pur:
            _sep_idx = self.supplier_combo.count()
            self.supplier_combo.addItem("── Credit Customers ──", None)
            self.supplier_combo.model().item(_sep_idx).setEnabled(False)
            for cc in _cust_for_pur:
                self.supplier_combo.addItem(cc['name'], {"type": "customer", "id": cc["id"]})
        _sup_h.addWidget(self.supplier_combo)
        header_layout.addWidget(self._sup_widget)
        self.supplier_balance_lbl = QLabel("")
        self.supplier_balance_lbl.setStyleSheet(STATUS_INFO)
        header_layout.addWidget(self.supplier_balance_lbl)
        self.supplier_combo.currentIndexChanged.connect(self._on_supplier_changed)

        # Notes
        header_layout.addWidget(QLabel("Notes:"))
        self.notes_edit = QLineEdit()
        self.notes_edit.setPlaceholderText("Optional notes")
        self.notes_edit.setMinimumWidth(160)
        self.notes_edit.returnPressed.connect(lambda: self.notes_edit.focusNextChild())
        header_layout.addWidget(self.notes_edit)
        header_layout.setStretchFactor(self.notes_edit, 1)
        layout.addWidget(header_card)

        # ── Add line card ─────────────────────────────────────────────────────
        add_card = QFrame()
        add_card.setStyleSheet(CARD_STYLE)
        add_v = QVBoxLayout(add_card)
        add_v.setContentsMargins(16, 12, 16, 12)
        add_v.setSpacing(8)

        # Row 1: Brand, Model, Ref Price, Discount, Net Price
        row1 = QHBoxLayout()
        row1.setSpacing(10)

        row1.addWidget(QLabel("Brand:"))
        self.brand_combo = SearchableComboBox()
        self.brand_combo.setMinimumWidth(130)
        self.brand_combo.addItem("— Brand —", None)
        for b in db_brands_list():
            self.brand_combo.addItem(b["name"], b["id"])
        self.brand_combo.currentIndexChanged.connect(self._on_brand_change)
        row1.addWidget(self.brand_combo)

        row1.addWidget(QLabel("Model:"))
        self.model_combo = SearchableComboBox()
        self.model_combo.setMinimumWidth(160)
        self.model_combo.addItem("— Model —", None)
        self.model_combo.currentIndexChanged.connect(self._on_model_change)
        row1.addWidget(self.model_combo)

        row1.addWidget(QLabel("Ref Price:"))
        self.price_spin = QDoubleSpinBox()
        self.price_spin.setRange(0, 9_999_999)
        self.price_spin.setDecimals(0)
        self.price_spin.setSingleStep(500)
        self.price_spin.setGroupSeparatorShown(True)
        self.price_spin.setMinimumWidth(110)
        self.price_spin.valueChanged.connect(self._on_ref_price_changed)
        self.price_spin.lineEdit().returnPressed.connect(
            lambda: self.price_spin.focusNextChild())
        row1.addWidget(self.price_spin)

        row1.addWidget(QLabel("Discount:"))
        self.discount_spin = QDoubleSpinBox()
        self.discount_spin.setRange(0, 9_999_999)
        self.discount_spin.setDecimals(0)
        self.discount_spin.setSingleStep(100)
        self.discount_spin.setGroupSeparatorShown(True)
        self.discount_spin.setMinimumWidth(100)
        self.discount_spin.valueChanged.connect(self._on_discount_changed)
        self.discount_spin.lineEdit().returnPressed.connect(
            lambda: self.discount_spin.focusNextChild())
        row1.addWidget(self.discount_spin)

        row1.addWidget(QLabel("Net Price:"))
        self.net_price_spin = QDoubleSpinBox()
        self.net_price_spin.setRange(0, 9_999_999)
        self.net_price_spin.setDecimals(0)
        self.net_price_spin.setSingleStep(500)
        self.net_price_spin.setGroupSeparatorShown(True)
        self.net_price_spin.setMinimumWidth(110)
        self.net_price_spin.valueChanged.connect(self._on_net_price_changed)
        self.net_price_spin.lineEdit().returnPressed.connect(
            lambda: self.net_price_spin.focusNextChild())
        row1.addWidget(self.net_price_spin)

        row1.addStretch()
        add_v.addLayout(row1)

        # Row 2: IMEI and Add button
        row2 = QHBoxLayout()
        row2.setSpacing(10)
        row2.addWidget(QLabel("IMEI (15 digits):"))
        self.imei_edit = QLineEdit()
        self.imei_edit.setPlaceholderText("Enter 15-digit IMEI")
        self.imei_edit.setMaxLength(15)
        self.imei_edit.setMinimumWidth(200)
        self.imei_edit.setProperty("enterKeepDefault", True)
        self.imei_edit.returnPressed.connect(self._add_line)
        row2.addWidget(self.imei_edit, stretch=1)

        self.btn_add_line = QPushButton("+ Add IMEI")
        self.btn_add_line.setStyleSheet(BTN_PRIMARY)
        self.btn_add_line.clicked.connect(self._add_line)
        row2.addWidget(self.btn_add_line)
        add_v.addLayout(row2)

        layout.addWidget(add_card)

        # Disable add-line controls if no brands exist
        no_brands = self.brand_combo.count() <= 1
        if no_brands:
            self.model_combo.setEnabled(False)
            self.price_spin.setEnabled(False)
            self.discount_spin.setEnabled(False)
            self.net_price_spin.setEnabled(False)
            self.imei_edit.setEnabled(False)
            self.btn_add_line.setEnabled(False)

        # ── Lines table ───────────────────────────────────────────────────────
        self.lines_table = _make_table(["#", "Brand", "Model", "IMEI", "Price (PKR)", ""])
        _lh = self.lines_table.horizontalHeader()
        _lh.setStretchLastSection(False)
        _lh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)       # #
        _lh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)     # Brand
        _lh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)     # Model
        _lh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # IMEI
        _lh.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)       # Price (PKR)
        _lh.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)       # Remove btn
        self.lines_table.setColumnWidth(0, 35)
        self.lines_table.setColumnWidth(4, 130)
        self.lines_table.setColumnWidth(5, 80)
        layout.addWidget(self.lines_table, stretch=1)

        # ── Footer card ───────────────────────────────────────────────────────
        footer_card = QFrame()
        footer_card.setStyleSheet(CARD_STYLE)
        footer_v = QVBoxLayout(footer_card)
        footer_v.setContentsMargins(12, 8, 12, 8)
        footer_v.setSpacing(4)

        # Payment row — visible only for cash purchases
        self._pm_row_widget = QWidget()
        _pm_inner = QHBoxLayout(self._pm_row_widget)
        _pm_inner.setContentsMargins(0, 0, 0, 0)
        _pm_inner.setSpacing(6)
        _pm_lbl = QLabel("Payment *:")
        _pm_lbl.setStyleSheet("font-weight:bold;")
        _pm_inner.addWidget(_pm_lbl)
        _pm_inner.addSpacing(4)
        self._pay_btn_cash  = QPushButton("Cash")
        self._pay_btn_bank  = QPushButton("Bank Transfer")
        self._pay_btn_split = QPushButton("Split")
        for b in (self._pay_btn_cash, self._pay_btn_bank, self._pay_btn_split):
            b.setFixedHeight(30)
        _apply_toggle_style(self._pay_btn_cash,  True,  "left")
        _apply_toggle_style(self._pay_btn_bank,  False, "mid")
        _apply_toggle_style(self._pay_btn_split, False, "right")
        self._pay_btn_cash.clicked.connect( lambda: self._set_pay_method("cash"))
        self._pay_btn_bank.clicked.connect( lambda: self._set_pay_method("bank"))
        self._pay_btn_split.clicked.connect(lambda: self._set_pay_method("split"))
        _pm_inner.addWidget(self._pay_btn_cash)
        _pm_inner.addWidget(self._pay_btn_bank)
        _pm_inner.addWidget(self._pay_btn_split)
        _pm_inner.addSpacing(8)

        # Inline payment detail stack
        self._pay_stack = QStackedWidget()

        # Page 0 — Cash (empty)
        self._pay_stack.addWidget(QWidget())

        # Page 1 — Bank Transfer
        pg_bank = QWidget()
        pg_bank_h = QHBoxLayout(pg_bank)
        pg_bank_h.setContentsMargins(0, 0, 0, 0)
        pg_bank_h.setSpacing(6)
        pg_bank_h.addWidget(QLabel("Account:"))
        self.pay_bank_combo = QComboBox()
        self.pay_bank_combo.setMinimumWidth(160)
        self._populate_bank_combo(self.pay_bank_combo)
        pg_bank_h.addWidget(self.pay_bank_combo)
        pg_bank_h.addWidget(QLabel("Ref:"))
        self.pay_bank_ref_edit = QLineEdit()
        self.pay_bank_ref_edit.setPlaceholderText("Transfer reference number")
        self.pay_bank_ref_edit.setMinimumWidth(120)
        self.pay_bank_ref_edit.returnPressed.connect(
            lambda: self.pay_bank_ref_edit.focusNextChild())
        pg_bank_h.addWidget(self.pay_bank_ref_edit)
        self._pay_stack.addWidget(pg_bank)

        # Page 2 — Split
        pg_split = QWidget()
        pg_split_h = QHBoxLayout(pg_split)
        pg_split_h.setContentsMargins(0, 0, 0, 0)
        pg_split_h.setSpacing(6)
        pg_split_h.addWidget(QLabel("Cash:"))
        self.split_cash_spin = QDoubleSpinBox()
        self.split_cash_spin.setRange(0, 9_999_999)
        self.split_cash_spin.setDecimals(0)
        self.split_cash_spin.setSingleStep(1000)
        self.split_cash_spin.setGroupSeparatorShown(True)
        self.split_cash_spin.setFixedWidth(90)
        self.split_cash_spin.valueChanged.connect(self._on_split_cash_changed)
        self.split_cash_spin.lineEdit().returnPressed.connect(
            lambda: self.split_cash_spin.focusNextChild())
        pg_split_h.addWidget(self.split_cash_spin)
        pg_split_h.addWidget(QLabel("Bank:"))
        self.split_bank_spin = QDoubleSpinBox()
        self.split_bank_spin.setRange(0, 9_999_999)
        self.split_bank_spin.setDecimals(0)
        self.split_bank_spin.setSingleStep(1000)
        self.split_bank_spin.setGroupSeparatorShown(True)
        self.split_bank_spin.setFixedWidth(90)
        self.split_bank_spin.lineEdit().returnPressed.connect(
            lambda: self.split_bank_spin.focusNextChild())
        pg_split_h.addWidget(self.split_bank_spin)
        pg_split_h.addWidget(QLabel("Acct:"))
        self.split_bank_combo = QComboBox()
        self.split_bank_combo.setMinimumWidth(140)
        self._populate_bank_combo(self.split_bank_combo)
        pg_split_h.addWidget(self.split_bank_combo)
        pg_split_h.addWidget(QLabel("Ref:"))
        self.split_ref_edit = QLineEdit()
        self.split_ref_edit.setPlaceholderText("Bank ref (optional)")
        self.split_ref_edit.setMinimumWidth(90)
        self.split_ref_edit.returnPressed.connect(
            lambda: self.split_ref_edit.focusNextChild())
        pg_split_h.addWidget(self.split_ref_edit)
        self._pay_stack.addWidget(pg_split)

        _pm_inner.addWidget(self._pay_stack)
        _pm_inner.addStretch()
        footer_v.addWidget(self._pm_row_widget)
        self._pm_row_widget.setVisible(False)

        # Action row: total + buttons
        action_strip = QHBoxLayout()
        action_strip.setSpacing(8)
        self.total_label = QLabel("Total: PKR 0")
        self.total_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.total_label.setStyleSheet("color:#1d4ed8;")
        action_strip.addWidget(self.total_label)
        action_strip.addStretch()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet(BTN_SECONDARY)
        btn_cancel.clicked.connect(on_cancel)
        self.btn_save = QPushButton("Save Purchase  [F9]")
        self.btn_save.setStyleSheet(BTN_PRIMARY)
        self.btn_save.clicked.connect(self._save)
        QShortcut(QKeySequence("F9"), self).activated.connect(self.btn_save.click)
        action_strip.addWidget(btn_cancel)
        action_strip.addWidget(self.btn_save)
        footer_v.addLayout(action_strip)

        layout.addWidget(footer_card)

    # ── Purchase type / payment method helpers ────────────────────────────────

    def _populate_bank_combo(self, combo: QComboBox):
        from database import db_bank_accounts
        combo.clear()
        accounts = db_bank_accounts()
        if not accounts:
            combo.addItem("— No bank accounts (add in Settings) —", None)
        else:
            combo.addItem("— Select Account —", None)
            for a in accounts:
                combo.addItem(a["name"], a["id"])

    def _set_purchase_type(self, ptype: str):
        self._purchase_type = ptype
        _apply_toggle_style(self._btn_supplier_type, ptype == "supplier", "left")
        _apply_toggle_style(self._btn_cash_type,     ptype == "cash",     "right")
        self._sup_widget.setVisible(ptype == "supplier")
        self.supplier_balance_lbl.setVisible(ptype == "supplier")
        self._pm_row_widget.setVisible(ptype == "cash")
        if ptype == "supplier":
            QTimer.singleShot(0, self.supplier_combo.setFocus)
        else:
            QTimer.singleShot(0, self.imei_edit.setFocus)

    def _set_pay_method(self, method: str):
        self._pay_method = method
        _apply_toggle_style(self._pay_btn_cash,  method == "cash",  "left")
        _apply_toggle_style(self._pay_btn_bank,  method == "bank",  "mid")
        _apply_toggle_style(self._pay_btn_split, method == "split", "right")
        self._pay_stack.setCurrentIndex({"cash": 0, "bank": 1, "split": 2}.get(method, 0))
        if method == "split":
            self.split_cash_spin.setValue(0)
            self.split_bank_spin.setValue(self._total)

    def _on_split_cash_changed(self, val):
        bank = max(0.0, self._total - val)
        self.split_bank_spin.blockSignals(True)
        self.split_bank_spin.setValue(bank)
        self.split_bank_spin.blockSignals(False)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_supplier_changed(self):
        data = self.supplier_combo.currentData()
        if data is None:
            self.supplier_balance_lbl.setText("")
        elif data["type"] == "supplier":
            bal = db_supplier_balance(data["id"])
            self.supplier_balance_lbl.setText(f"Outstanding: Rs. {fmt_pkr(bal)}")
        else:
            conn = get_connection()
            row = conn.execute("""
                SELECT COALESCE(c.opening_balance, 0)
                       + COALESCE((SELECT SUM(sv.total_amount) FROM sale_vouchers sv WHERE sv.customer_id = c.id), 0)
                       - COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.party_type='customer' AND p.party_id = c.id AND p.type='CR'), 0)
                       AS balance
                FROM customers c WHERE c.id = ?
            """, (data["id"],)).fetchone()
            conn.close()
            bal = row["balance"] if row else 0
            self.supplier_balance_lbl.setText(f"Customer Balance: Rs. {fmt_pkr(bal)}")

    def _on_brand_change(self):
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self.model_combo.addItem("— Model —", None)
        brand_id = self.brand_combo.currentData()
        if brand_id is not None:
            for m in db_models_for_brand(brand_id):
                self.model_combo.addItem(m["name"], (m["id"], m["reference_price"]))
        self.model_combo.blockSignals(False)
        self._current_model_id = None
        self._updating_price = True
        self.price_spin.setValue(0)
        self.discount_spin.setValue(0)
        self.net_price_spin.setValue(0)
        self._updating_price = False
        has_models = self.model_combo.count() > 1
        self.model_combo.setEnabled(brand_id is not None)
        self.price_spin.setEnabled(has_models)
        self.discount_spin.setEnabled(has_models)
        self.net_price_spin.setEnabled(has_models)
        self.imei_edit.setEnabled(has_models)
        self.btn_add_line.setEnabled(has_models)

    def _on_model_change(self):
        data = self.model_combo.currentData()
        if data is None:
            self._current_model_id = None
            self._updating_price = True
            self.price_spin.setValue(0)
            self.discount_spin.setValue(0)
            self.net_price_spin.setValue(0)
            self._updating_price = False
        else:
            model_id, ref_price = data
            self._current_model_id = model_id
            self._updating_price = True
            self.price_spin.setValue(ref_price or 0)
            self.discount_spin.setValue(0)
            self.net_price_spin.setValue(ref_price or 0)
            self._updating_price = False

    def _on_ref_price_changed(self, value):
        if self._updating_price:
            return
        self._updating_price = True
        self.net_price_spin.setValue(max(0.0, value - self.discount_spin.value()))
        self._updating_price = False

    def _on_discount_changed(self, value):
        if self._updating_price:
            return
        self._updating_price = True
        self.net_price_spin.setValue(max(0.0, self.price_spin.value() - value))
        self._updating_price = False

    def _on_net_price_changed(self, value):
        if self._updating_price:
            return
        self._updating_price = True
        self.discount_spin.setValue(max(0.0, self.price_spin.value() - value))
        self._updating_price = False

    def _add_line(self):
        if self._current_model_id is None:
            QMessageBox.warning(self, "Missing", "Select a brand and model first.")
            return
        imei = self.imei_edit.text().strip()
        if not imei:
            QMessageBox.warning(self, "Missing", "Enter an IMEI.")
            self.imei_edit.setFocus()
            return
        if len(imei) != 15 or not imei.isdigit():
            QMessageBox.warning(self, "Invalid IMEI",
                "IMEI must be exactly 15 digits (numbers only).")
            self.imei_edit.selectAll()
            self.imei_edit.setFocus()
            return
        if any(l[3] == imei for l in self._lines):
            QMessageBox.warning(self, "Duplicate", f"IMEI {imei} already in this purchase.")
            self.imei_edit.selectAll()
            self.imei_edit.setFocus()
            return
        if db_imei_in_stock(imei):
            QMessageBox.warning(self, "Duplicate IMEI",
                f"IMEI {imei} is currently in stock.\n"
                "Cannot add a phone that is already in your inventory.")
            self.imei_edit.selectAll()
            self.imei_edit.setFocus()
            return

        brand_name = self.brand_combo.currentText()
        model_name = self.model_combo.currentText()
        price = self.net_price_spin.value()
        self._lines.append((self._current_model_id, brand_name, model_name, imei, price))
        self._refresh_lines_table()
        self.imei_edit.clear()
        self.imei_edit.setFocus()

    def _refresh_lines_table(self):
        self.lines_table.setRowCount(0)
        total = 0
        for idx, (model_id, brand, model, imei, price) in enumerate(self._lines):
            r = self.lines_table.rowCount()
            self.lines_table.insertRow(r)
            num = QTableWidgetItem(str(idx + 1))
            num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.lines_table.setItem(r, 0, num)
            self.lines_table.setItem(r, 1, QTableWidgetItem(brand))
            self.lines_table.setItem(r, 2, QTableWidgetItem(model))
            self.lines_table.setItem(r, 3, QTableWidgetItem(imei))
            price_item = QTableWidgetItem(fmt_pkr(price))
            price_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.lines_table.setItem(r, 4, price_item)
            del_btn = QPushButton("Remove")
            del_btn.setStyleSheet(BTN_DANGER_SMALL)
            del_btn.clicked.connect(lambda _, i=idx: self._remove_line(i))
            self.lines_table.setCellWidget(r, 5, del_btn)
            total += price
        self._total = total
        self.total_label.setText(f"Total: PKR {fmt_pkr(total)}")

    def _remove_line(self, idx):
        self._lines.pop(idx)
        self._refresh_lines_table()

    def _save(self):
        if not self._lines:
            QMessageBox.warning(self, "Missing", "Add at least one IMEI line.")
            return

        date_str = self.date_edit.date().toString("dd/MM/yyyy")
        notes    = self.notes_edit.text().strip()
        db_lines = [(m, imei, price) for m, _, _, imei, price in self._lines]
        total    = sum(price for _, _, price in db_lines)

        if self._purchase_type == "supplier":
            # ── Supplier purchase ─────────────────────────────────────────
            _sup_data = self.supplier_combo.currentData()
            if _sup_data is None:
                QMessageBox.warning(self, "Missing", "Please select a supplier.")
                return
            if _sup_data["type"] == "supplier":
                supplier_id = _sup_data["id"]
                customer_as_supplier_id = None
            else:
                supplier_id = None
                customer_as_supplier_id = _sup_data["id"]
            try:
                pv_number = db_save_purchase(date_str, supplier_id, notes, db_lines,
                                             customer_as_supplier_id=customer_as_supplier_id)
            except sqlite3.IntegrityError as e:
                QMessageBox.critical(self, "Save Error", f"Failed to save: {e}")
                return
            QMessageBox.information(self, "Saved",
                                    f"Purchase {pv_number} saved successfully.")

        else:
            # ── Cash purchase ─────────────────────────────────────────────
            pm = self._pay_method
            if pm == "cash":
                cash_amount    = total
                bank_amount    = 0.0
                bank_account_id = None
                bank_ref       = ""
            elif pm == "bank":
                if self.pay_bank_combo.currentData() is None:
                    QMessageBox.warning(self, "Missing",
                        "Please select a bank account for bank transfer.")
                    return
                cash_amount    = 0.0
                bank_amount    = total
                bank_account_id = self.pay_bank_combo.currentData()
                bank_ref       = self.pay_bank_ref_edit.text().strip()
            else:  # split
                if self.split_bank_combo.currentData() is None:
                    QMessageBox.warning(self, "Missing",
                        "Please select a bank account for split payment.")
                    return
                cash_amount    = self.split_cash_spin.value()
                bank_amount    = self.split_bank_spin.value()
                bank_account_id = self.split_bank_combo.currentData()
                bank_ref       = self.split_ref_edit.text().strip()
                if abs((cash_amount + bank_amount) - total) > 0.01:
                    QMessageBox.warning(self, "Split Validation",
                        f"Cash (PKR {fmt_pkr(cash_amount)}) + "
                        f"Bank (PKR {fmt_pkr(bank_amount)}) = "
                        f"PKR {fmt_pkr(cash_amount + bank_amount)}\n"
                        f"but purchase total is PKR {fmt_pkr(total)}.\n"
                        "The two amounts must equal the total.")
                    return

            try:
                pv_number = db_save_purchase(
                    date_str, 0, notes, db_lines,
                    purchase_type="cash",
                    egadget_ref="",
                    payment_method=pm,
                    cash_amount=cash_amount,
                    bank_amount=bank_amount,
                    bank_account_id=bank_account_id,
                    bank_ref=bank_ref,
                )
            except sqlite3.IntegrityError as e:
                QMessageBox.critical(self, "Save Error", f"Failed to save: {e}")
                return

            # Print cash purchase receipt
            try:
                from receipt import print_cash_purchase_receipt
                print_cash_purchase_receipt(pv_number, parent=self)
            except Exception:
                pass

            QMessageBox.information(self, "Saved",
                f"Cash Purchase {pv_number} saved.\n"
                f"Total: PKR {fmt_pkr(total)}")

        self._on_save(pv_number)


# ── Purchase List View ────────────────────────────────────────────────────────

class PurchaseListView(QWidget):
    def __init__(self, on_new, parent=None):
        super().__init__(parent)
        self._on_new = on_new

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        top = QHBoxLayout()
        top.addStretch()
        top.addWidget(QLabel("Go to Voucher:"))
        self._goto_edit = QLineEdit()
        self._goto_edit.setPlaceholderText("PV-0001")
        self._goto_edit.setMaximumWidth(110)
        self._goto_edit.returnPressed.connect(self._goto_voucher)
        top.addWidget(self._goto_edit)
        btn_goto = QPushButton("Open")
        btn_goto.setStyleSheet(BTN_SECONDARY)
        btn_goto.clicked.connect(self._goto_voucher)
        top.addWidget(btn_goto)
        self.btn_edit = QPushButton("✏ Edit")
        self.btn_edit.setStyleSheet(BTN_SECONDARY)
        self.btn_edit.setEnabled(False)
        self.btn_edit.clicked.connect(self._edit_selected)
        top.addWidget(self.btn_edit)
        self.btn_delete_pv = QPushButton("🗑 Delete")
        self.btn_delete_pv.setStyleSheet("""
            QPushButton { background:#fee2e2; color:#dc2626; border:1px solid #fca5a5;
                border-radius:5px; padding:6px 16px; font-size:10pt; }
            QPushButton:hover { background:#fecaca; }
            QPushButton:disabled { background:#f1f5f9; color:#94a3b8; border-color:#e2e8f0; }
        """)
        self.btn_delete_pv.setEnabled(False)
        self.btn_delete_pv.clicked.connect(self._delete_selected)
        top.addWidget(self.btn_delete_pv)
        btn_new = QPushButton("+ New Purchase")
        btn_new.setStyleSheet(BTN_PRIMARY)
        btn_new.clicked.connect(on_new)
        top.addWidget(btn_new)
        layout.addLayout(top)

        # Filter bar
        filter_card = QFrame()
        filter_card.setStyleSheet(CARD_STYLE)
        fl = QHBoxLayout(filter_card)
        fl.setContentsMargins(12, 10, 12, 10)
        fl.setSpacing(10)

        fl.addWidget(QLabel("From:"))
        self.from_date = QDateEdit(QDate.currentDate())
        self.from_date.setDisplayFormat("dd/MM/yyyy")
        self.from_date.setCalendarPopup(True)
        fl.addWidget(self.from_date)

        fl.addWidget(QLabel("To:"))
        self.to_date = QDateEdit(QDate.currentDate())
        self.to_date.setDisplayFormat("dd/MM/yyyy")
        self.to_date.setCalendarPopup(True)
        fl.addWidget(self.to_date)

        btn_today = QPushButton("Today")
        btn_today.setStyleSheet(BTN_SECONDARY)
        btn_today.clicked.connect(self._set_today)
        fl.addWidget(btn_today)

        btn_yesterday = QPushButton("Yesterday")
        btn_yesterday.setStyleSheet(BTN_SECONDARY)
        btn_yesterday.clicked.connect(self._set_yesterday)
        fl.addWidget(btn_yesterday)

        fl.addWidget(QLabel("Supplier:"))
        self.sup_filter = QComboBox()
        self.sup_filter.setMinimumWidth(160)
        self.sup_filter.addItem("All Suppliers", None)
        for s in db_suppliers_list():
            self.sup_filter.addItem(s["name"], s["id"])
        fl.addWidget(self.sup_filter)

        fl.addWidget(QLabel("Type:"))
        self.type_filter = QComboBox()
        self.type_filter.setMinimumWidth(130)
        self.type_filter.addItem("All Types",     None)
        self.type_filter.addItem("Supplier Only", "supplier")
        self.type_filter.addItem("Cash Purchase", "cash")
        fl.addWidget(self.type_filter)

        btn_search = QPushButton("Search")
        btn_search.setStyleSheet(BTN_SECONDARY)
        btn_search.clicked.connect(self.refresh)
        fl.addWidget(btn_search)

        btn_clear = QPushButton("Clear")
        btn_clear.setStyleSheet(BTN_SECONDARY)
        btn_clear.clicked.connect(self._clear_filters)
        fl.addWidget(btn_clear)

        fl.addStretch()
        layout.addWidget(filter_card)

        # Table
        self.table = _make_table(
            ["PV Number", "Date", "Supplier", "Items", "Total Amount (PKR)", "Notes"]
        )
        hdr = self.table.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)   # Supplier stretches
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)      # Items
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)      # Total Amount (PKR)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)    # Notes stretches
        self.table.setColumnWidth(3, 55)
        self.table.setColumnWidth(4, 150)
        self.table.doubleClicked.connect(self._edit_selected)
        self.table.itemSelectionChanged.connect(
            lambda: self.btn_edit.setEnabled(self.table.currentRow() >= 0)
        )
        self.table.itemSelectionChanged.connect(
            lambda: self.btn_delete_pv.setEnabled(self.table.currentRow() >= 0)
        )
        layout.addWidget(self.table, stretch=1)

        self.refresh()

    def refresh(self):
        from_iso = self.from_date.date().toString("yyyy-MM-dd")
        to_iso   = self.to_date.date().toString("yyyy-MM-dd")
        sup_id   = self.sup_filter.currentData()
        type_f   = self.type_filter.currentData()
        rows = db_load_purchases(from_iso, to_iso, sup_id, type_f)

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for r in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            pv_item = QTableWidgetItem(r["pv_number"])
            pv_item.setData(Qt.ItemDataRole.UserRole, dict(r))
            self.table.setItem(row, 0, pv_item)
            self.table.setItem(row, 1, QTableWidgetItem(r["date"]))
            # Supplier column: show "Cash — {egadget_ref}" for cash purchases
            ptype = r["purchase_type"] if "purchase_type" in r.keys() else "supplier"
            if ptype == "cash":
                ref = r["egadget_ref"] if "egadget_ref" in r.keys() else ""
                sup_display = f"Cash — {ref}" if ref else "Cash Purchase"
            else:
                sup_display = r["supplier_name"]
            self.table.setItem(row, 2, QTableWidgetItem(sup_display))
            cnt = QTableWidgetItem(str(r["item_count"]))
            cnt.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 3, cnt)
            amt = QTableWidgetItem(fmt_pkr(r["total_amount"]))
            amt.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 4, amt)
            self.table.setItem(row, 5, QTableWidgetItem(r["notes"] or ""))
        self.table.setSortingEnabled(True)
        self.btn_edit.setEnabled(False)

    def _clear_filters(self):
        self.from_date.setDate(QDate.currentDate().addMonths(-1))
        self.to_date.setDate(QDate.currentDate())
        self.sup_filter.setCurrentIndex(0)
        self.type_filter.setCurrentIndex(0)
        self.refresh()

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

    def _goto_voucher(self):
        raw = self._goto_edit.text().strip().upper()
        if not raw:
            return
        import re
        if not re.match(r'^[A-Z]+-\d+$', raw):
            QMessageBox.warning(self, "Invalid Format",
                "Please enter a full voucher number, e.g. PV-0001")
            return
        conn = get_connection()
        row = conn.execute(
            "SELECT id FROM purchase_vouchers WHERE UPPER(pv_number)=?", (raw,)
        ).fetchone()
        conn.close()
        if not row:
            QMessageBox.warning(self, "Not Found", f"Voucher {raw} not found.")
            return
        from edit_vouchers import PurchaseEditDialog
        dlg = PurchaseEditDialog(row["id"], self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
        self._goto_edit.clear()

    def _edit_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return
        pv_row = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        from edit_vouchers import PurchaseEditDialog
        dlg = PurchaseEditDialog(pv_row["id"], self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _view_detail(self):
        row = self.table.currentRow()
        if row < 0:
            return
        pv_row = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        dlg = PurchaseDetailDialog(pv_row, self)
        dlg.exec()

    def _delete_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return
        pv_row = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        from database import prompt_and_delete_voucher
        deleted = prompt_and_delete_voucher(
            self, "purchase", pv_row["id"], pv_row["pv_number"], "Owner"
        )
        if deleted:
            self.refresh()


# ── Purchase Page ─────────────────────────────────────────────────────────────

class PurchasePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:#f1f5f9;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._tabs = QTabWidget()
        outer.addWidget(self._tabs)

        # ── Purchases tab ──────────────────────────────────────────────────────
        purchases_container = QWidget()
        purchases_container.setStyleSheet("background:#f1f5f9;")
        purchases_layout = QVBoxLayout(purchases_container)
        purchases_layout.setContentsMargins(0, 0, 0, 0)
        purchases_layout.setSpacing(0)

        self._stack = QStackedWidget()
        purchases_layout.addWidget(self._stack)

        self._list_view = PurchaseListView(on_new=self._show_form)
        self._stack.addWidget(self._list_view)
        self._form: PurchaseForm | None = None

        # ── Returns tab ────────────────────────────────────────────────────────
        returns_container = QWidget()
        returns_container.setStyleSheet("background:#f1f5f9;")
        returns_layout = QVBoxLayout(returns_container)
        returns_layout.setContentsMargins(0, 0, 0, 0)
        returns_layout.setSpacing(0)

        self._returns_stack = QStackedWidget()
        returns_layout.addWidget(self._returns_stack)

        self._return_list_view = PurchaseReturnListView(on_new=self._show_return_form)
        self._returns_stack.addWidget(self._return_list_view)
        self._return_form: PurchaseReturnForm | None = None

        self._tabs.addTab(purchases_container, "Purchases")
        self._tabs.addTab(returns_container, "Returns")

    # ── Purchases tab methods ──────────────────────────────────────────────────

    def _show_form(self):
        self._form = PurchaseForm(
            on_save=self._on_saved,
            on_cancel=self._show_list,
        )
        self._stack.addWidget(self._form)
        self._stack.setCurrentWidget(self._form)

    def _on_saved(self, pv_number):
        self._show_list()

    def _show_list(self):
        self._stack.setCurrentWidget(self._list_view)
        self._list_view.refresh()
        if self._form is not None:
            self._stack.removeWidget(self._form)
            self._form.deleteLater()
            self._form = None

    # ── Returns tab methods ────────────────────────────────────────────────────

    def _show_return_form(self):
        self._return_form = PurchaseReturnForm(
            on_save=self._on_return_saved,
            on_cancel=self._show_return_list,
        )
        self._returns_stack.addWidget(self._return_form)
        self._returns_stack.setCurrentWidget(self._return_form)

    def _on_return_saved(self, pr_number):
        self._show_return_list()

    def _show_return_list(self):
        self._returns_stack.setCurrentWidget(self._return_list_view)
        self._return_list_view.refresh()
        if self._return_form is not None:
            self._returns_stack.removeWidget(self._return_form)
            self._return_form.deleteLater()
            self._return_form = None
