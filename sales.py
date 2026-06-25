import sqlite3
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QComboBox, QLineEdit,
    QDoubleSpinBox, QDateEdit, QDialog, QDialogButtonBox,
    QMessageBox, QHeaderView, QAbstractItemView, QFrame,
    QStackedWidget, QListWidget, QListWidgetItem, QCheckBox, QTabWidget,
    QScrollArea,
)
from PyQt6.QtCore import Qt, QDate, QTimer, QPoint, QEvent, pyqtSignal
from PyQt6.QtGui import QFont, QBrush, QColor, QPainter, QPixmap

from database import get_connection, db_bank_accounts, db_active_salesmen
from widgets import SearchableComboBox


def validate_phone(phone: str) -> bool:
    """Pakistan mobile: exactly 11 digits, starts with 03."""
    return len(phone) == 11 and phone.startswith("03") and phone.isdigit()


# ── Styles ────────────────────────────────────────────────────────────────────

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
BTN_TOGGLE_ON = """
    QPushButton { background:#2563eb; color:white; border:none;
        padding:7px 24px; font-size:10pt; font-weight:bold; }
"""
BTN_TOGGLE_OFF = """
    QPushButton { background:#f1f5f9; color:#64748b;
        border:1px solid #cbd5e1; padding:7px 24px; font-size:10pt; }
    QPushButton:hover { background:#e2e8f0; color:#334155; }
"""
CARD_STYLE = "background:#ffffff; border:1px solid #e2e8f0; border-radius:8px; color:#1e293b;"
STATUS_OK  = "color:#16a34a; font-size:9pt; font-weight:bold;"
STATUS_ERR = "color:#dc2626; font-size:9pt;"
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


def _setup_titlecase_edit(edit):
    """Connect textChanged so the field stays in Title Case as the user types."""
    def to_title(text):
        titled = text.title()
        if text != titled:
            pos = edit.cursorPosition()
            edit.blockSignals(True)
            edit.setText(titled)
            edit.setCursorPosition(pos)
            edit.blockSignals(False)
    edit.textChanged.connect(to_title)


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
    t.horizontalHeader().setStretchLastSection(False)
    t.setStyleSheet(TABLE_STYLE)
    return t


# ── DB helpers ────────────────────────────────────────────────────────────────

def db_customers_list():
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name, contact FROM customers WHERE type='credit' ORDER BY name"
    ).fetchall()
    conn.close()
    return rows


def db_suppliers_for_sale():
    """Returns all suppliers for use as credit customers in a sale."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name FROM suppliers WHERE id != 0 ORDER BY name"
    ).fetchall()
    conn.close()
    return rows


def db_customer_balance(customer_id):
    """Return outstanding balance for a single credit customer (amount they owe)."""
    conn = get_connection()
    row = conn.execute("""
        SELECT COALESCE(c.opening_balance, 0)
               + COALESCE((SELECT SUM(sv.total_amount) FROM sale_vouchers sv WHERE sv.customer_id=c.id AND sv.type='credit'), 0)
               - COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.party_type='customer' AND p.party_id=c.id AND p.type='CR'), 0)
               + COALESCE((SELECT SUM(je.amount) FROM journal_entries je WHERE je.party_type='customer' AND je.party_id=c.id AND je.type='debit'), 0)
               - COALESCE((SELECT SUM(je.amount) FROM journal_entries je WHERE je.party_type='customer' AND je.party_id=c.id AND je.type='credit'), 0)
               AS balance
        FROM customers c WHERE c.id=?
    """, (customer_id,)).fetchone()
    conn.close()
    return row["balance"] if row else 0


def db_lookup_cash_customer(contact: str):
    """Return the most recent cash sale info for this phone number, or None."""
    conn = get_connection()
    row = conn.execute("""
        SELECT sv.cash_customer_name, sv.date, sv.total_amount,
               GROUP_CONCAT(b.name || ' ' || m.name, ', ') AS models
        FROM sale_vouchers sv
        JOIN sale_lines sl ON sl.sv_id = sv.id
        JOIN models m ON m.id = sl.model_id
        JOIN brands b ON b.id = m.brand_id
        WHERE sv.type = 'cash' AND sv.cash_customer_contact = ?
        GROUP BY sv.id
        ORDER BY sv.id DESC
        LIMIT 1
    """, (contact,)).fetchone()
    conn.close()
    return dict(row) if row else None


def db_imei_lookup(suffix):
    conn = get_connection()
    rows = conn.execute("""
        SELECT si.id, TRIM(si.imei) AS imei, b.name AS brand_name, m.name AS model_name,
               m.reference_price, m.id AS model_id, si.purchase_price
        FROM stock_items si
        JOIN models m ON m.id = si.model_id
        JOIN brands b ON b.id = m.brand_id
        WHERE TRIM(si.imei) LIKE ? AND si.status = 'in_stock'
        ORDER BY TRIM(si.imei)
    """, ("%" + suffix.strip(),)).fetchall()
    conn.close()
    return rows


def db_imei_browse_all():
    """Return all in-stock IMEIs for manual browsing."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT si.id, TRIM(si.imei) AS imei, b.name AS brand_name, m.name AS model_name,
               m.reference_price, m.id AS model_id, si.purchase_price
        FROM stock_items si
        JOIN models m ON m.id = si.model_id
        JOIN brands b ON b.id = m.brand_id
        WHERE si.status = 'in_stock'
        ORDER BY b.name, m.name, TRIM(si.imei)
    """).fetchall()
    conn.close()
    return rows


def db_save_sale(date_str, sale_type, customer_id, cash_name, cash_contact,
                 note, overall_discount, lines,
                 payment_method="cash", cash_paid=0.0,
                 bank_account_id=None, bank_amount=0.0, bank_ref="",
                 salesman_id=None, supplier_as_customer_id=None):
    """
    lines = [(stock_item_id, model_id, imei, ref_price, final_price), ...]
    Returns (sv_number, sv_id).
    """
    conn = get_connection()
    try:
        c = conn.cursor()
        row = c.execute(
            "SELECT value FROM settings WHERE key='last_sv_number'"
        ).fetchone()
        n = int(row["value"]) + 1 if row else 1
        c.execute("UPDATE settings SET value=? WHERE key='last_sv_number'", (str(n),))
        sv_number = f"SV-{n:04d}"

        subtotal = sum(fp for _, _, _, _, fp in lines)
        total_amount = subtotal - (overall_discount or 0)

        c.execute("""
            INSERT INTO sale_vouchers
            (sv_number, type, customer_id, cash_customer_name, cash_customer_contact,
             date, total_amount, discount, note, whatsapp_sent,
             payment_method, cash_paid, bank_account_id, bank_amount, bank_ref,
             salesman_id, supplier_as_customer_id)
            VALUES (?,?,?,?,?,?,?,?,?,0,?,?,?,?,?,?,?)
        """, (sv_number, sale_type, customer_id, cash_name, cash_contact,
              date_str, total_amount, overall_discount or 0, note or "",
              payment_method, cash_paid, bank_account_id, bank_amount, bank_ref or "",
              salesman_id, supplier_as_customer_id))
        sv_id = c.lastrowid

        for stock_item_id, model_id, imei, ref_price, final_price in lines:
            per_line_disc = (ref_price or 0) - final_price
            c.execute("""
                INSERT INTO sale_lines
                (sv_id, stock_item_id, model_id, imei, reference_price, discount, final_price)
                VALUES (?,?,?,?,?,?,?)
            """, (sv_id, stock_item_id, model_id, imei, ref_price, per_line_disc, final_price))
            sl_id = c.lastrowid
            c.execute(
                "UPDATE stock_items SET status='sold', sold_line_id=? WHERE id=?",
                (sl_id, stock_item_id),
            )

        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()
    return sv_number, sv_id


def _date_expr():
    return "substr(sv.date,7,4)||'-'||substr(sv.date,4,2)||'-'||substr(sv.date,1,2)"


def db_load_sales(from_iso=None, to_iso=None, sale_type=None):
    conds, params = [], []
    de = _date_expr()
    if from_iso:
        conds.append(f"{de} >= ?")
        params.append(from_iso)
    if to_iso:
        conds.append(f"{de} <= ?")
        params.append(to_iso)
    if sale_type:
        conds.append("sv.type = ?")
        params.append(sale_type)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    sql = f"""
        SELECT sv.id, sv.sv_number, sv.date, sv.type,
               COALESCE(c.name, sup_c.name, sv.cash_customer_name) AS customer_name,
               COUNT(sl.id) AS item_count,
               sv.total_amount, sv.discount, sv.note
        FROM sale_vouchers sv
        LEFT JOIN customers c ON c.id = sv.customer_id
        LEFT JOIN suppliers sup_c ON sup_c.id = sv.supplier_as_customer_id
        LEFT JOIN sale_lines sl ON sl.sv_id = sv.id
        {where}
        GROUP BY sv.id
        ORDER BY sv.id DESC
    """
    conn = get_connection()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


def db_sold_imei_lookup(suffix: str):
    """Search sold IMEIs for sale return — returns sale/customer info.

    Joins via sale_lines.stock_item_id rather than stock_items.sold_line_id
    so that records where sold_line_id was not written (data written by an
    older version of the app) are still found correctly.  The sale_lines row
    is authoritative proof that a sale happened.
    """
    conn = get_connection()
    rows = conn.execute("""
        SELECT si.id AS stock_item_id, TRIM(si.imei) AS imei,
               b.name AS brand_name, m.name AS model_name, m.id AS model_id,
               sl.final_price AS sale_price, sv.date AS sale_date,
               sl.sv_id,
               COALESCE(sv.customer_id, 0) AS customer_id,
               COALESCE(c.name, sv.cash_customer_name, '—') AS customer_name
        FROM stock_items si
        JOIN models m ON m.id = si.model_id
        JOIN brands b ON b.id = m.brand_id
        JOIN sale_lines sl ON sl.stock_item_id = si.id
        JOIN sale_vouchers sv ON sv.id = sl.sv_id
        LEFT JOIN customers c ON c.id = sv.customer_id
        WHERE TRIM(si.imei) LIKE ?
          AND (si.status = 'sold'
               OR (si.status = 'in_stock' AND si.sold_line_id IS NULL
                   AND sl.id IS NOT NULL))
        ORDER BY TRIM(si.imei)
    """, ("%" + suffix.strip(),)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def db_load_sale_lines(sv_id):
    conn = get_connection()
    rows = conn.execute("""
        SELECT b.name AS brand_name, m.name AS model_name,
               sl.imei, sl.reference_price, sl.final_price, sl.discount
        FROM sale_lines sl
        JOIN models m ON m.id = sl.model_id
        JOIN brands b ON b.id = m.brand_id
        WHERE sl.sv_id = ?
        ORDER BY sl.id
    """, (sv_id,)).fetchall()
    conn.close()
    return rows


# ── Sale Return DB helpers ─────────────────────────────────────────────────────

def db_lookup_sv_for_return(sv_number: str):
    """Lookup a sale voucher by number for return processing. Returns dict or None."""
    conn = get_connection()
    row = conn.execute("""
        SELECT sv.id, sv.sv_number, sv.date, sv.type, sv.total_amount,
               COALESCE(c.name, sv.cash_customer_name) AS customer_name,
               sv.customer_id
        FROM sale_vouchers sv
        LEFT JOIN customers c ON c.id = sv.customer_id
        WHERE UPPER(TRIM(sv.sv_number)) = UPPER(TRIM(?))
    """, (sv_number,)).fetchone()
    conn.close()
    return dict(row) if row else None


def db_sv_returnable_lines(sv_id: int):
    """Return all sale lines for an SV with the current stock_items status."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT sl.stock_item_id, sl.model_id, sl.imei, sl.final_price,
               b.name AS brand_name, m.name AS model_name,
               si.status AS stock_status
        FROM sale_lines sl
        JOIN models m ON m.id = sl.model_id
        JOIN brands b ON b.id = m.brand_id
        JOIN stock_items si ON si.id = sl.stock_item_id
        WHERE sl.sv_id = ?
        ORDER BY sl.id
    """, (sv_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def db_save_sale_return(date_str, customer_id, lines, notes):
    """
    lines = [(stock_item_id, model_id, imei, return_price), ...]
    Returns (sr_number, sr_id).
    Stock status → 'in_stock', sold_line_id cleared.
    Credit customers: JV credit entry reduces their balance.
    """
    conn = get_connection()
    try:
        c = conn.cursor()
        row = c.execute(
            "SELECT value FROM settings WHERE key='last_sr_number'"
        ).fetchone()
        n = int(row["value"]) + 1 if row else 1
        c.execute("UPDATE settings SET value=? WHERE key='last_sr_number'", (str(n),))
        sr_number = f"SR-{n:04d}"

        c.execute(
            "INSERT INTO sale_returns (sr_number, sv_id, customer_id, date, notes) "
            "VALUES (?,?,?,?,?)",
            (sr_number, None, customer_id, date_str, notes or ""),
        )
        sr_id = c.lastrowid

        total_return = 0.0
        for stock_item_id, model_id, imei, return_price in lines:
            c.execute(
                "INSERT INTO sale_return_lines "
                "(sr_id, stock_item_id, model_id, imei, return_price) VALUES (?,?,?,?,?)",
                (sr_id, stock_item_id, model_id, imei, return_price),
            )
            c.execute(
                "UPDATE stock_items SET status='in_stock', sold_line_id=NULL WHERE id=?",
                (stock_item_id,),
            )
            total_return += return_price

        # Credit customer: reduce their ledger balance via a journal credit entry
        if customer_id:
            jv_row = c.execute(
                "SELECT value FROM settings WHERE key='last_jv_number'"
            ).fetchone()
            jv_n = int(jv_row["value"]) + 1 if jv_row else 1
            c.execute(
                "UPDATE settings SET value=? WHERE key='last_jv_number'", (str(jv_n),)
            )
            jv_number = f"JV-{jv_n:04d}"
            c.execute(
                "INSERT INTO journal_entries "
                "(jv_number, party_type, party_id, date, amount, type, notes) "
                "VALUES (?,?,?,?,?,?,?)",
                (jv_number, "customer", customer_id, date_str, total_return,
                 "credit", f"Sales Return — {sr_number}"),
            )

        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()
    return sr_number, sr_id


def db_load_sale_returns(from_iso=None, to_iso=None):
    """Load all sale returns with optional date range filters."""
    conds, params = [], []
    de = "substr(sr.date,7,4)||'-'||substr(sr.date,4,2)||'-'||substr(sr.date,1,2)"
    if from_iso:
        conds.append(f"{de} >= ?")
        params.append(from_iso)
    if to_iso:
        conds.append(f"{de} <= ?")
        params.append(to_iso)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    sql = f"""
        SELECT sr.id, sr.sr_number, sr.date, sr.notes,
               COALESCE(c.name, '—') AS customer_name,
               COUNT(srl.id) AS item_count,
               COALESCE(SUM(srl.return_price), 0) AS return_amount
        FROM sale_returns sr
        LEFT JOIN customers c ON c.id = sr.customer_id
        LEFT JOIN sale_return_lines srl ON srl.sr_id = sr.id
        {where}
        GROUP BY sr.id
        ORDER BY sr.id DESC
    """
    conn = get_connection()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── IMEI Dropdown ─────────────────────────────────────────────────────────────

class ImeiDropdown(QWidget):
    """Live search dropdown that appears below the IMEI input field."""
    imei_chosen = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet("background: #2563eb; border: 2px solid #2563eb; border-radius: 4px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)

        self._list = QListWidget()
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.setStyleSheet("""
            QListWidget {
                background: #ffffff; border: none;
                font-size: 10pt; font-family: "Consolas", "Courier New", monospace;
                outline: none;
            }
            QListWidget::item { padding: 6px 14px; border-bottom: 1px solid #f1f5f9; }
            QListWidget::item:hover { background: #dbeafe; color: #1e40af; }
            QListWidget::item:selected { background: #2563eb; color: #ffffff; }
            QListWidget::item:selected:hover { background: #1d4ed8; color: #ffffff; }
            QListWidget::item:selected:!active { background: #2563eb; color: #ffffff; }
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
            it = QListWidgetItem("  No matching IMEI in stock")
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            it.setForeground(QBrush(QColor("#94a3b8")))
            self._list.addItem(it)
        else:
            for r in results:
                text = f"  {r['imei']}    {r['brand_name']} {r['model_name']}    PKR {fmt_pkr(r['reference_price'])}"
                it = QListWidgetItem(text)
                it.setData(Qt.ItemDataRole.UserRole, dict(r))
                self._list.addItem(it)

        pos = anchor.mapToGlobal(QPoint(0, anchor.height()))
        self.move(pos)
        visible_rows = min(max(len(results), 1), 8)
        self.resize(max(anchor.width(), 540), visible_rows * 34 + 2)
        self.show()

    def move_selection(self, delta: int):
        """Move highlighted row up (-1) or down (+1), skipping non-selectable rows."""
        count = self._list.count()
        if count == 0:
            return
        current = self._list.currentRow()
        if current < 0:
            new_row = 0 if delta > 0 else count - 1
        else:
            new_row = max(0, min(current + delta, count - 1))
        item = self._list.item(new_row)
        if item and item.data(Qt.ItemDataRole.UserRole):
            self._list.setCurrentRow(new_row)
            self._list.scrollToItem(item)

    def get_selected_data(self):
        """Return data of the currently highlighted row, or None."""
        item = self._list.currentItem()
        if item:
            return item.data(Qt.ItemDataRole.UserRole)
        return None

    def confirm_selection(self):
        """Confirm highlighted item, or first selectable item if nothing highlighted."""
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

    def select_first(self) -> bool:
        """Click the first selectable item. Returns True if one was selected."""
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole):
                self._on_click(item)
                return True
        return False


# ── IMEI Select Dialog ────────────────────────────────────────────────────────

class ImeiSelectDialog(QDialog):
    def __init__(self, results, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Browse Stock")
        self.setMinimumWidth(620)
        self.resize(680, 480)
        self._selected = None
        self._all_results = [dict(r) for r in results]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Search bar
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Search:"))
        self._search = QLineEdit()
        self._search.setPlaceholderText("Type brand, model or IMEI…")
        self._search.setStyleSheet(
            "border:1px solid #cbd5e1; border-radius:5px; padding:5px 10px; font-size:10pt;"
        )
        self._search.textChanged.connect(self._filter_table)
        search_row.addWidget(self._search)
        layout.addLayout(search_row)

        self._count_lbl = QLabel(f"{len(results)} items in stock")
        self._count_lbl.setStyleSheet("color:#64748b; font-size:9pt;")
        layout.addWidget(self._count_lbl)

        self.table = _make_table(["IMEI", "Brand", "Model", "Ref Price (PKR)"])
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 155)
        self.table.setColumnWidth(1, 110)
        self.table.setColumnWidth(3, 140)
        for r in self._all_results:
            row = self.table.rowCount()
            self.table.insertRow(row)
            item = QTableWidgetItem(r["imei"])
            item.setData(Qt.ItemDataRole.UserRole, r)
            self.table.setItem(row, 0, item)
            self.table.setItem(row, 1, QTableWidgetItem(r["brand_name"]))
            self.table.setItem(row, 2, QTableWidgetItem(r["model_name"]))
            p = QTableWidgetItem(fmt_pkr(r["reference_price"]))
            p.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 3, p)
        self.table.doubleClicked.connect(self._pick)
        layout.addWidget(self.table)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._pick)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self._search.setFocus()

    def _filter_table(self, text):
        needle = text.strip().lower()
        visible = 0
        for row in range(self.table.rowCount()):
            if needle == "":
                self.table.setRowHidden(row, False)
                visible += 1
            else:
                imei  = (self.table.item(row, 0).text() or "").lower()
                brand = (self.table.item(row, 1).text() or "").lower()
                model = (self.table.item(row, 2).text() or "").lower()
                match = needle in imei or needle in brand or needle in model
                self.table.setRowHidden(row, not match)
                if match:
                    visible += 1
        self._count_lbl.setText(f"{visible} item(s) shown")

    def _pick(self):
        row = self.table.currentRow()
        if row < 0 or self.table.isRowHidden(row):
            QMessageBox.warning(self, "Select", "Select a row first.")
            return
        self._selected = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        self.accept()

    def get_selected(self):
        return self._selected


# ── Sale Detail Dialog ────────────────────────────────────────────────────────

class SaleDetailDialog(QDialog):
    def __init__(self, sv_row, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Sale — {sv_row['sv_number']}")
        self.setMinimumWidth(680)
        self.resize(720, 500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        info = QFrame()
        info.setStyleSheet(CARD_STYLE)
        info_row = QHBoxLayout(info)
        info_row.setContentsMargins(16, 12, 16, 12)
        ctype = sv_row["type"].capitalize()
        for lbl, val in [
            ("SV Number", sv_row["sv_number"]),
            ("Date", sv_row["date"]),
            ("Type", ctype),
            ("Customer", sv_row["customer_name"] or "—"),
            ("Total", f"PKR {fmt_pkr(sv_row['total_amount'])}"),
        ]:
            col = QVBoxLayout()
            l = QLabel(lbl)
            l.setStyleSheet("color:#64748b; font-size:9pt;")
            v = QLabel(str(val))
            v.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            col.addWidget(l)
            col.addWidget(v)
            info_row.addLayout(col)
        if sv_row["discount"]:
            col = QVBoxLayout()
            l = QLabel("Discount")
            l.setStyleSheet("color:#64748b; font-size:9pt;")
            v = QLabel(f"PKR {fmt_pkr(sv_row['discount'])}")
            v.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            v.setStyleSheet("color:#dc2626;")
            col.addWidget(l)
            col.addWidget(v)
            info_row.addLayout(col)
        info_row.addStretch()
        layout.addWidget(info)

        table = _make_table(
            ["Brand", "Model", "IMEI", "Ref Price (PKR)", "Final Price (PKR)", "Disc (PKR)"]
        )
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        for r in db_load_sale_lines(sv_row["id"]):
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(r["brand_name"]))
            table.setItem(row, 1, QTableWidgetItem(r["model_name"]))
            table.setItem(row, 2, QTableWidgetItem(r["imei"]))
            for col, v in [(3, r["reference_price"]), (4, r["final_price"]), (5, r["discount"])]:
                item = QTableWidgetItem(fmt_pkr(v))
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                table.setItem(row, col, item)
        layout.addWidget(table)

        if sv_row["note"]:
            note_lbl = QLabel(f"Note: {sv_row['note']}")
            note_lbl.setStyleSheet("color:#64748b; font-size:9pt;")
            layout.addWidget(note_lbl)

        btn_delete = QPushButton("🗑 Delete Voucher")
        btn_delete.setStyleSheet("""
            QPushButton { background:#fee2e2; color:#dc2626; border:1px solid #fca5a5;
                border-radius:5px; padding:6px 14px; }
            QPushButton:hover { background:#fecaca; }
        """)
        btn_delete.clicked.connect(lambda: self._delete_and_close(sv_row))
        layout.addWidget(btn_delete)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _delete_and_close(self, sv_row):
        from database import prompt_and_delete_voucher
        deleted = prompt_and_delete_voucher(
            self, "sale", sv_row["id"], sv_row["sv_number"], "Owner"
        )
        if deleted:
            self.accept()


# ── Contact field that blocks focus-out when the number is partially entered ──

class ContactLineEdit(QLineEdit):
    """Blocks tabbing away while the field contains a non-empty, invalid number."""

    def focusOutEvent(self, event):
        text = self.text().strip()
        if text and not validate_phone(text):
            QTimer.singleShot(0, self.setFocus)
        super().focusOutEvent(event)


# ── Sale Form ─────────────────────────────────────────────────────────────────

class SaleForm(QWidget):
    def __init__(self, on_save, on_cancel, parent=None):
        super().__init__(parent)
        self._on_save = on_save
        self._on_cancel = on_cancel
        self._lines = []      # (stock_item_id, model_id, brand, model, imei, ref_price, final_price, purchase_price)
        self._staged = None   # (stock_item_id, model_id, brand, model, imei, ref_price, purchase_price)

        self.setStyleSheet(FORM_INPUT_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # ── Header card ──────────────────────────────────────────────────────
        header = QFrame()
        header.setStyleSheet(CARD_STYLE)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(12, 8, 12, 8)
        hl.setSpacing(8)

        hl.addWidget(QLabel("Date:"))
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setFixedWidth(108)
        hl.addWidget(self.date_edit)

        hl.addSpacing(8)
        hl.addWidget(QLabel("Sale Type:"))
        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(0)
        self.btn_cash = QPushButton("Cash")
        self.btn_cash.setFixedHeight(30)
        self.btn_cash.setStyleSheet(
            BTN_TOGGLE_ON + "QPushButton { border-radius: 5px 0 0 5px; }"
        )
        self.btn_credit = QPushButton("Credit")
        self.btn_credit.setFixedHeight(30)
        self.btn_credit.setStyleSheet(
            BTN_TOGGLE_OFF + "QPushButton { border-radius: 0 5px 5px 0; "
            "border-left: none; }"
        )
        self.btn_cash.clicked.connect(lambda: self._set_type("cash"))
        self.btn_credit.clicked.connect(lambda: self._set_type("credit"))
        toggle_row.addWidget(self.btn_cash)
        toggle_row.addWidget(self.btn_credit)
        hl.addLayout(toggle_row)

        hl.addSpacing(8)
        sal_lbl = QLabel("Salesman *:")
        sal_lbl.setStyleSheet("color:#dc2626; font-weight:bold;")
        hl.addWidget(sal_lbl)
        self.salesman_combo = SearchableComboBox()
        self.salesman_combo.setMinimumWidth(100)
        self.salesman_combo.setMaximumWidth(130)
        _salesmen = db_active_salesmen()
        if _salesmen:
            for sm in _salesmen:
                self.salesman_combo.addItem(sm["name"], sm["id"])
            self.salesman_combo.setCurrentIndex(0)
        else:
            self.salesman_combo.addItem("— No salesmen —", None)
            self.salesman_combo.setToolTip(
                "No active salesmen — add one in Masters → Salesmen first."
            )
        hl.addWidget(self.salesman_combo)

        hl.addSpacing(8)
        # Customer section — stacked (cash / credit)
        self._sale_type = "cash"
        self.customer_stack = QStackedWidget()

        # Cash page — contact number first, name second
        cash_widget = QWidget()
        cash_row = QHBoxLayout(cash_widget)
        cash_row.setContentsMargins(0, 0, 0, 0)
        cash_row.setSpacing(12)

        self.cash_contact = ContactLineEdit()
        self.cash_contact.setPlaceholderText("03XXXXXXXXX")
        self.cash_contact.setMaxLength(11)
        self.cash_contact.setFixedWidth(105)
        self.cash_contact.textChanged.connect(self._on_cash_contact_changed)
        self.cash_contact.returnPressed.connect(lambda: self.cash_contact.focusNextChild())
        cash_row.addWidget(self.cash_contact)

        self.contact_status_lbl = QLabel("")
        self.contact_status_lbl.setMinimumWidth(24)
        cash_row.addWidget(self.contact_status_lbl)

        cash_row.addWidget(QLabel("Name *:"))
        self.cash_name = QLineEdit()
        self.cash_name.setPlaceholderText("Auto-filled or enter name")
        self.cash_name.setMinimumWidth(180)
        self.cash_name.setEnabled(False)
        self.cash_name.returnPressed.connect(lambda: self.cash_name.focusNextChild())
        _setup_titlecase_edit(self.cash_name)
        cash_row.addWidget(self.cash_name)

        # WhatsApp icon — green circle with phone glyph, no external file needed
        _wa_px = QPixmap(22, 22)
        _wa_px.fill(Qt.GlobalColor.transparent)
        _wa_p = QPainter(_wa_px)
        _wa_p.setRenderHint(QPainter.RenderHint.Antialiasing)
        _wa_p.setBrush(QBrush(QColor("#25D366")))
        _wa_p.setPen(Qt.PenStyle.NoPen)
        _wa_p.drawEllipse(0, 0, 21, 21)
        _wa_p.setPen(QColor("white"))
        _wa_p.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        _wa_p.drawText(_wa_px.rect(), Qt.AlignmentFlag.AlignCenter, "✆")
        _wa_p.end()
        _wa_lbl = QLabel()
        _wa_lbl.setPixmap(_wa_px)
        _wa_lbl.setToolTip("Send WhatsApp on save")
        cash_row.addWidget(_wa_lbl)
        self.chk_whatsapp = QCheckBox()
        self.chk_whatsapp.setChecked(False)
        self.chk_whatsapp.setToolTip("Send WhatsApp on save")
        cash_row.addWidget(self.chk_whatsapp)

        cash_row.addStretch()
        self.customer_stack.addWidget(cash_widget)

        # Credit page
        credit_widget = QWidget()
        credit_row = QHBoxLayout(credit_widget)
        credit_row.setContentsMargins(0, 0, 0, 0)
        credit_row.setSpacing(12)
        credit_row.addWidget(QLabel("Credit Customer *"))
        self.credit_combo = SearchableComboBox()
        self.credit_combo.setMinimumWidth(220)
        self.credit_combo.addItem("— Select Customer —", None)
        for c in db_customers_list():
            self.credit_combo.addItem(c["name"], {"type": "customer", "id": c["id"]})
        _sups_for_sale = db_suppliers_for_sale()
        if _sups_for_sale:
            _sep_idx = self.credit_combo.count()
            self.credit_combo.addItem("── Suppliers ──", None)
            self.credit_combo.model().item(_sep_idx).setEnabled(False)
            for s in _sups_for_sale:
                self.credit_combo.addItem(s['name'], {"type": "supplier", "id": s["id"]})
        credit_row.addWidget(self.credit_combo)
        self.credit_balance_lbl = QLabel("")
        self.credit_balance_lbl.setStyleSheet(STATUS_INFO)
        credit_row.addWidget(self.credit_balance_lbl)
        self.credit_combo.currentIndexChanged.connect(self._on_credit_customer_changed)
        credit_row.addStretch()
        self.customer_stack.addWidget(credit_widget)

        # Disable Credit toggle if no credit customers or suppliers exist
        if self.credit_combo.count() <= 1:
            self.btn_credit.setEnabled(False)
            self.btn_credit.setToolTip("No credit customers — add one in Masters first.")

        hl.addWidget(self.customer_stack)
        hl.addStretch()
        layout.addWidget(header)

        # ── IMEI lookup card ──────────────────────────────────────────────────
        lookup_card = QFrame()
        lookup_card.setStyleSheet(CARD_STYLE)
        ll = QVBoxLayout(lookup_card)
        ll.setContentsMargins(16, 12, 16, 12)
        ll.setSpacing(8)

        imei_row = QHBoxLayout()
        imei_row.setSpacing(8)
        self.imei_input = QLineEdit()
        self.imei_input.setPlaceholderText("Type 5+ digits to search…")
        self.imei_input.setFixedWidth(148)
        self.imei_input.setProperty("enterKeepDefault", True)
        self.imei_input.textChanged.connect(self._on_imei_changed)
        self.imei_input.returnPressed.connect(self._imei_enter)
        imei_row.addWidget(self.imei_input)

        self._imei_dropdown = ImeiDropdown(self)
        self._imei_dropdown.imei_chosen.connect(self._on_dropdown_select)
        self.imei_input.installEventFilter(self)

        btn_browse = QPushButton("Browse All Stock")
        btn_browse.setStyleSheet(BTN_SECONDARY)
        btn_browse.setToolTip("Pick any in-stock phone manually")
        btn_browse.clicked.connect(self._imei_browse)
        imei_row.addWidget(btn_browse)

        self.lookup_status = QLabel("")
        self.lookup_status.setStyleSheet(STATUS_INFO)
        imei_row.addWidget(self.lookup_status)

        self.price_label = QLabel("Price (PKR):")
        self.price_label.setVisible(False)
        imei_row.addWidget(self.price_label)

        self.price_spin = QDoubleSpinBox()
        self.price_spin.setRange(0, 9_999_999)
        self.price_spin.setDecimals(0)
        self.price_spin.setSingleStep(500)
        self.price_spin.setGroupSeparatorShown(True)
        self.price_spin.setFixedWidth(120)
        self.price_spin.setVisible(False)
        self.price_spin.returnPressed = None
        self.price_spin.valueChanged.connect(self._check_staged_price)
        imei_row.addWidget(self.price_spin)

        self.price_warn_lbl = QLabel("")
        self.price_warn_lbl.setStyleSheet(STATUS_WARN)
        imei_row.addWidget(self.price_warn_lbl)

        self.btn_add_line = QPushButton("+ Add")
        self.btn_add_line.setStyleSheet(BTN_PRIMARY)
        self.btn_add_line.setVisible(False)
        self.btn_add_line.clicked.connect(self._add_line)
        imei_row.addWidget(self.btn_add_line)

        imei_row.addStretch()
        ll.addLayout(imei_row)
        layout.addWidget(lookup_card)

        # ── Lines table ───────────────────────────────────────────────────────
        self.lines_table = _make_table(
            ["#", "Brand", "Model", "IMEI", "Ref Price (PKR)", "Final Price (PKR)", "Disc", "Warning", ""]
        )
        _lh = self.lines_table.horizontalHeader()
        _lh.setStretchLastSection(False)
        _lh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)            # #
        _lh.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)            # Brand
        _lh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)          # Model
        _lh.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)            # IMEI
        _lh.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)            # Ref Price
        _lh.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)            # Final Price
        _lh.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)            # Disc
        _lh.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents) # Warning
        _lh.setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)            # Remove btn
        self.lines_table.setColumnWidth(0, 35)
        self.lines_table.setColumnWidth(1, 110)
        self.lines_table.setColumnWidth(3, 155)
        self.lines_table.setColumnWidth(4, 130)
        self.lines_table.setColumnWidth(5, 140)
        self.lines_table.setColumnWidth(6, 90)
        self.lines_table.setColumnWidth(8, 80)
        self.lines_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked |
            QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        self.lines_table.cellChanged.connect(self._on_price_cell_changed)
        layout.addWidget(self.lines_table, stretch=1)

        # ── Pinned footer ─────────────────────────────────────────────────────
        self._payment_mode = "cash"

        self.payment_card = QFrame()
        self.payment_card.setStyleSheet(CARD_STYLE)
        footer_vbox = QVBoxLayout(self.payment_card)
        footer_vbox.setContentsMargins(12, 8, 12, 8)
        footer_vbox.setSpacing(4)

        # Row 1: always-visible bar
        footer_strip = QHBoxLayout()
        footer_strip.setSpacing(8)

        footer_strip.addWidget(QLabel("Overall Discount (PKR):"))
        self.discount_spin = QDoubleSpinBox()
        self.discount_spin.setRange(0, 9_999_999)
        self.discount_spin.setDecimals(0)
        self.discount_spin.setSingleStep(100)
        self.discount_spin.setGroupSeparatorShown(True)
        self.discount_spin.setMinimumWidth(120)
        self.discount_spin.valueChanged.connect(self._update_total)
        self.discount_spin.lineEdit().returnPressed.connect(
            lambda: self.discount_spin.focusNextChild())
        footer_strip.addWidget(self.discount_spin)

        self.total_label = QLabel("TOTAL: Rs. 0")
        self.total_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.total_label.setStyleSheet("color:#1d4ed8;")
        footer_strip.addWidget(self.total_label)

        footer_strip.addSpacing(16)

        pm_toggle = QHBoxLayout()
        pm_toggle.setSpacing(0)
        self.btn_pay_cash = QPushButton("Cash")
        self.btn_pay_cash.setFixedHeight(28)
        self.btn_pay_cash.setStyleSheet(
            BTN_TOGGLE_ON + "QPushButton { border-radius: 5px 0 0 5px; font-size:9pt; padding:4px 16px; }"
        )
        self.btn_pay_bank = QPushButton("Bank Transfer")
        self.btn_pay_bank.setFixedHeight(28)
        self.btn_pay_bank.setStyleSheet(
            BTN_TOGGLE_OFF + "QPushButton { border-radius: 0; border-left: none; font-size:9pt; padding:4px 16px; }"
        )
        self.btn_pay_split = QPushButton("Split")
        self.btn_pay_split.setFixedHeight(28)
        self.btn_pay_split.setStyleSheet(
            BTN_TOGGLE_OFF + "QPushButton { border-radius: 0 5px 5px 0; border-left: none; font-size:9pt; padding:4px 16px; }"
        )
        self.btn_pay_cash.clicked.connect(lambda: self._set_payment_mode("cash"))
        self.btn_pay_bank.clicked.connect(lambda: self._set_payment_mode("bank"))
        self.btn_pay_split.clicked.connect(lambda: self._set_payment_mode("split"))
        pm_toggle.addWidget(self.btn_pay_cash)
        pm_toggle.addWidget(self.btn_pay_bank)
        pm_toggle.addWidget(self.btn_pay_split)
        footer_strip.addLayout(pm_toggle)

        footer_strip.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet(BTN_SECONDARY)
        btn_cancel.clicked.connect(on_cancel)
        self.btn_save = QPushButton("Save Sale")
        self.btn_save.setStyleSheet(BTN_PRIMARY)
        self.btn_save.clicked.connect(self._save)
        footer_strip.addWidget(btn_cancel)
        footer_strip.addWidget(self.btn_save)

        footer_vbox.addLayout(footer_strip)

        # Row 2: payment method details — shown only for Bank / Split
        self._pm_detail = QFrame()
        pm_detail_row = QHBoxLayout(self._pm_detail)
        pm_detail_row.setContentsMargins(0, 2, 0, 0)
        pm_detail_row.setSpacing(8)

        self._pm_stack = QStackedWidget()
        self._pm_stack.setFixedHeight(36)

        # Page 0 — Cash (detail row hidden, this page never shown)
        self._pm_stack.addWidget(QWidget())

        # Page 1 — Bank Transfer
        bank_pm_widget = QWidget()
        bank_pm_row = QHBoxLayout(bank_pm_widget)
        bank_pm_row.setContentsMargins(0, 0, 0, 0)
        bank_pm_row.setSpacing(12)
        bank_pm_row.addWidget(QLabel("Account:"))
        self.pay_bank_combo = QComboBox()
        self.pay_bank_combo.setMinimumWidth(180)
        self._populate_bank_combo(self.pay_bank_combo)
        bank_pm_row.addWidget(self.pay_bank_combo)
        bank_pm_row.addWidget(QLabel("Reference No:"))
        self.pay_bank_ref = QLineEdit()
        self.pay_bank_ref.setPlaceholderText("Optional")
        self.pay_bank_ref.setMinimumWidth(140)
        self.pay_bank_ref.returnPressed.connect(lambda: self.pay_bank_ref.focusNextChild())
        bank_pm_row.addWidget(self.pay_bank_ref)
        bank_pm_row.addStretch()
        self._pm_stack.addWidget(bank_pm_widget)

        # Page 2 — Split
        split_pm_widget = QWidget()
        split_pm_row = QHBoxLayout(split_pm_widget)
        split_pm_row.setContentsMargins(0, 0, 0, 0)
        split_pm_row.setSpacing(12)
        split_pm_row.addWidget(QLabel("Cash:"))
        self.pay_split_cash_spin = QDoubleSpinBox()
        self.pay_split_cash_spin.setRange(0, 9_999_999)
        self.pay_split_cash_spin.setDecimals(0)
        self.pay_split_cash_spin.setSingleStep(500)
        self.pay_split_cash_spin.setGroupSeparatorShown(True)
        self.pay_split_cash_spin.setMinimumWidth(120)
        self.pay_split_cash_spin.valueChanged.connect(self._update_split_bank_lbl)
        self.pay_split_cash_spin.lineEdit().returnPressed.connect(
            lambda: self.pay_split_cash_spin.focusNextChild())
        split_pm_row.addWidget(self.pay_split_cash_spin)
        split_pm_row.addWidget(QLabel("Bank:"))
        self.pay_split_bank_combo = QComboBox()
        self.pay_split_bank_combo.setMinimumWidth(180)
        self._populate_bank_combo(self.pay_split_bank_combo)
        split_pm_row.addWidget(self.pay_split_bank_combo)
        split_pm_row.addWidget(QLabel("Ref:"))
        self.pay_split_bank_ref = QLineEdit()
        self.pay_split_bank_ref.setPlaceholderText("Optional")
        self.pay_split_bank_ref.setMinimumWidth(100)
        self.pay_split_bank_ref.returnPressed.connect(
            lambda: self.pay_split_bank_ref.focusNextChild())
        split_pm_row.addWidget(self.pay_split_bank_ref)
        self.pay_split_bank_lbl = QLabel("Bank: PKR 0")
        self.pay_split_bank_lbl.setStyleSheet("color:#1d4ed8; font-size:9pt; font-weight:bold;")
        split_pm_row.addWidget(self.pay_split_bank_lbl)
        split_pm_row.addStretch()
        self._pm_stack.addWidget(split_pm_widget)

        pm_detail_row.addWidget(self._pm_stack)
        pm_detail_row.addStretch()
        self._pm_detail.setVisible(False)
        footer_vbox.addWidget(self._pm_detail)

        layout.addWidget(self.payment_card)

    # ── Bank account combo helper ─────────────────────────────────────────────

    def _populate_bank_combo(self, combo):
        combo.clear()
        combo.addItem("— Select Account —", None)
        for acc in db_bank_accounts():
            combo.addItem(acc["name"], acc["id"])
        if combo.count() <= 1:
            combo.setEnabled(False)
            combo.setToolTip("No bank accounts — add one in Settings first.")
        else:
            combo.setEnabled(True)
            combo.setToolTip("")

    # ── Credit customer balance ───────────────────────────────────────────────

    def _on_credit_customer_changed(self):
        data = self.credit_combo.currentData()
        if data is None:
            self.credit_balance_lbl.setText("")
        elif data["type"] == "customer":
            bal = db_customer_balance(data["id"])
            self.credit_balance_lbl.setText(f"Balance: Rs. {fmt_pkr(bal)}")
        else:
            conn = get_connection()
            row = conn.execute("""
                SELECT COALESCE(s.opening_balance, 0)
                       + COALESCE((SELECT SUM(pv.total_amount) FROM purchase_vouchers pv WHERE pv.supplier_id = s.id), 0)
                       - COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.party_type='supplier' AND p.party_id = s.id AND p.type='CP'), 0)
                       AS balance
                FROM suppliers s WHERE s.id = ?
            """, (data["id"],)).fetchone()
            conn.close()
            bal = row["balance"] if row else 0
            self.credit_balance_lbl.setText(f"Supplier Balance: Rs. {fmt_pkr(bal)}")

    # ── Type toggle ───────────────────────────────────────────────────────────

    def _set_type(self, sale_type):
        self._sale_type = sale_type
        if sale_type == "cash":
            self.btn_cash.setStyleSheet(
                BTN_TOGGLE_ON + "QPushButton { border-radius: 5px 0 0 5px; }"
            )
            self.btn_credit.setStyleSheet(
                BTN_TOGGLE_OFF + "QPushButton { border-radius: 0 5px 5px 0; border-left: none; }"
            )
            self.customer_stack.setCurrentIndex(0)
            self.payment_card.setVisible(True)
        else:
            self.btn_credit.setStyleSheet(
                BTN_TOGGLE_ON + "QPushButton { border-radius: 0 5px 5px 0; border-left: none; }"
            )
            self.btn_cash.setStyleSheet(
                BTN_TOGGLE_OFF + "QPushButton { border-radius: 5px 0 0 5px; }"
            )
            self.customer_stack.setCurrentIndex(1)
            self.payment_card.setVisible(False)

    # ── Payment mode toggle ───────────────────────────────────────────────────

    def _set_payment_mode(self, mode):
        self._payment_mode = mode
        on  = BTN_TOGGLE_ON  + "QPushButton { font-size:9pt; padding:4px 16px; "
        off = BTN_TOGGLE_OFF + "QPushButton { font-size:9pt; padding:4px 16px; "
        self.btn_pay_cash.setStyleSheet(
            (on  + "border-radius: 5px 0 0 5px; }") if mode == "cash"
            else (off + "border-radius: 5px 0 0 5px; }")
        )
        self.btn_pay_bank.setStyleSheet(
            (on  + "border-radius: 0; border-left: none; }") if mode == "bank"
            else (off + "border-radius: 0; border-left: none; }")
        )
        self.btn_pay_split.setStyleSheet(
            (on  + "border-radius: 0 5px 5px 0; border-left: none; }") if mode == "split"
            else (off + "border-radius: 0 5px 5px 0; border-left: none; }")
        )
        if mode == "cash":
            self._pm_stack.setCurrentIndex(0)
            self._pm_detail.setVisible(False)
        elif mode == "bank":
            self._pm_stack.setCurrentIndex(1)
            self._pm_detail.setVisible(True)
        else:
            self._pm_stack.setCurrentIndex(2)
            self._pm_detail.setVisible(True)
            self._update_split_bank_lbl()

    def _update_split_bank_lbl(self):
        total = self._get_total()
        cash = self.pay_split_cash_spin.value()
        bank = max(0.0, total - cash)
        self.pay_split_bank_lbl.setText(f"Bank: PKR {fmt_pkr(bank)}")

    # ── Cash customer phone check ─────────────────────────────────────────────

    def _on_cash_contact_changed(self, text):
        text = text.strip()

        if not text:
            self.contact_status_lbl.setText("")
            self.cash_name.setEnabled(False)
            self.cash_name.clear()
            return

        if not validate_phone(text):
            self.contact_status_lbl.setText("")
            self.cash_name.setEnabled(False)
            self.cash_name.clear()
            return

        # Valid number
        self.contact_status_lbl.setText("✓")
        self.contact_status_lbl.setStyleSheet(STATUS_OK)
        self.cash_name.setEnabled(True)

        info = db_lookup_cash_customer(text)
        if info and info.get("cash_customer_name"):
            self.cash_name.setText(info["cash_customer_name"])
            msg = (
                f"Welcome back, {info['cash_customer_name']}!\n\n"
                f"Last visit:    {info['date']}\n"
                f"Last purchase: {info['models']}\n"
                f"Amount paid:   PKR {fmt_pkr(info['total_amount'])}"
            )
            QMessageBox.information(self, "Returning Customer", msg)
        else:
            self.cash_name.clear()
            self.cash_name.setFocus()

    # ── IMEI lookup ───────────────────────────────────────────────────────────

    def _on_imei_changed(self, text):
        text = text.strip()
        if len(text) < 5:
            self._imei_dropdown.hide()
            if not text:
                self._clear_staged("Type the last 5 digits of the IMEI to search", STATUS_INFO)
            else:
                self._clear_staged(
                    f"Type {5 - len(text)} more digit(s)…", STATUS_INFO
                )
            return
        already = {l[4] for l in self._lines}
        results = [r for r in db_imei_lookup(text) if r["imei"] not in already]
        if len(results) == 0:
            self._imei_dropdown.show_below(self.imei_input, [])
            self._clear_staged("No in-stock phone found for these digits", STATUS_ERR)
        elif len(results) == 1:
            # Show single result in dropdown — same UX as multiple results
            self._imei_dropdown.show_below(self.imei_input, results)
            self._clear_staged(
                "1 phone matches — click or press Enter to select",
                STATUS_WARN,
            )
        else:
            self._imei_dropdown.show_below(self.imei_input, results)
            self._clear_staged(
                f"{len(results)} phones match — use ↑↓ to pick, Enter to confirm",
                STATUS_WARN,
            )

    def _imei_enter(self):
        if self._imei_dropdown.isVisible():
            self._imei_dropdown.confirm_selection()
            return
        text = self.imei_input.text().strip()
        if not text:
            self._imei_browse()
            return
        already = {l[4] for l in self._lines}
        results = [r for r in db_imei_lookup(text) if r["imei"] not in already]
        if len(results) == 0:
            self._clear_staged("No in-stock phone found — try Browse All Stock", STATUS_ERR)
        elif len(results) == 1:
            self._stage(results[0])
        else:
            dlg = ImeiSelectDialog(results, self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self._stage(dlg.get_selected())

    def _on_dropdown_select(self, data: dict):
        self.imei_input.blockSignals(True)
        self.imei_input.setText(data["imei"])
        self.imei_input.blockSignals(False)
        self._stage(data)

    def _imei_browse(self):
        already = {l[4] for l in self._lines}
        results = [r for r in db_imei_browse_all() if r["imei"] not in already]
        if not results:
            QMessageBox.information(self, "No Stock", "No phones currently in stock.")
            return
        dlg = ImeiSelectDialog(results, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            selected = dlg.get_selected()
            if selected:
                self.imei_input.setText(selected["imei"])
                self._stage(selected)

    def prefill_imei(self, imei: str):
        """Pre-fill IMEI from external caller (e.g. stock report Use in Sale)."""
        self.imei_input.setText(imei.strip())

    def _stage(self, r):
        # Pre-fill price with same-model existing price if already in invoice
        existing_price = next(
            (line[6] for line in self._lines if line[1] == r["model_id"]),
            None,
        )
        self._staged = (r["id"], r["model_id"], r["brand_name"],
                        r["model_name"], r["imei"], r["reference_price"],
                        r["purchase_price"])
        self.lookup_status.setText(
            f"Found: {r['brand_name']} {r['model_name']}  ·  IMEI: {r['imei']}  "
            f"·  Ref: PKR {fmt_pkr(r['reference_price'])}"
        )
        self.lookup_status.setStyleSheet(STATUS_OK)
        price = existing_price if existing_price is not None else (r["reference_price"] or 0)
        self.price_spin.setValue(price)
        self.price_label.setVisible(True)
        self.price_spin.setVisible(True)
        self.btn_add_line.setVisible(True)
        self._check_staged_price()
        self.price_spin.setFocus()
        self.price_spin.selectAll()

    def _clear_staged(self, msg="", style=STATUS_INFO):
        self._staged = None
        self.lookup_status.setText(msg)
        self.lookup_status.setStyleSheet(style)
        self.price_label.setVisible(False)
        self.price_spin.setVisible(False)
        self.price_warn_lbl.setText("")
        self.btn_add_line.setVisible(False)

    # ── Below-cost staging check ──────────────────────────────────────────────

    def _check_staged_price(self):
        if self._staged is None:
            self.price_warn_lbl.setText("")
            return
        pp = self._staged[6]
        if pp is not None and self.price_spin.value() < pp:
            self.price_warn_lbl.setText(
                f"⚠ Selling below cost — Purchase price: Rs. {fmt_pkr(pp)}"
            )
        else:
            self.price_warn_lbl.setText("")

    # ── Line management ───────────────────────────────────────────────────────

    def _add_line(self):
        if self._staged is None:
            return
        stock_id, model_id, brand, model, imei, ref_price, purchase_price = self._staged
        final_price = self.price_spin.value()

        # Check not already in this sale
        if any(l[4] == imei for l in self._lines):
            QMessageBox.warning(self, "Duplicate", f"IMEI {imei} already added to this sale.")
            return

        self._lines.append((stock_id, model_id, brand, model, imei, ref_price, final_price, purchase_price))

        # Sync all existing lines of the same model to this price
        for i in range(len(self._lines)):
            if self._lines[i][1] == model_id:
                sid, mid, b, m, im, ref, _, pp = self._lines[i]
                self._lines[i] = (sid, mid, b, m, im, ref, final_price, pp)

        self._refresh_lines_table()
        self._imei_dropdown.hide()
        self.imei_input.clear()
        self._clear_staged()
        self.imei_input.setFocus()

    def _refresh_lines_table(self):
        self.lines_table.blockSignals(True)
        self.lines_table.setRowCount(0)
        for idx, (sid, mid, brand, model, imei, ref, final, pp) in enumerate(self._lines):
            r = self.lines_table.rowCount()
            self.lines_table.insertRow(r)

            num = QTableWidgetItem(str(idx + 1))
            num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            num.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.lines_table.setItem(r, 0, num)

            for col, text in [(1, brand), (2, model), (3, imei)]:
                it = QTableWidgetItem(text)
                it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.lines_table.setItem(r, col, it)

            ref_item = QTableWidgetItem(fmt_pkr(ref))
            ref_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            ref_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.lines_table.setItem(r, 4, ref_item)

            # Final Price — editable so user can adjust in-table; sync on change
            price_item = QTableWidgetItem(fmt_pkr(final))
            price_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            price_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable
            )
            self.lines_table.setItem(r, 5, price_item)

            disc = (ref or 0) - final
            disc_item = QTableWidgetItem(fmt_pkr(disc) if disc else "—")
            disc_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            disc_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            if disc > 0:
                disc_item.setForeground(Qt.GlobalColor.red)
            self.lines_table.setItem(r, 6, disc_item)

            # Warning column (col 7)
            warn_item = QTableWidgetItem()
            warn_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            if pp is not None and final < pp:
                warn_item.setText(f"⚠ Selling below cost — Purchase price: Rs. {fmt_pkr(pp)}")
                warn_item.setForeground(QBrush(QColor("#d97706")))
                warn_item.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            self.lines_table.setItem(r, 7, warn_item)

            del_btn = QPushButton("Remove")
            del_btn.setStyleSheet(BTN_DANGER_SMALL)
            del_btn.clicked.connect(lambda _, i=idx: self._remove_line(i))
            self.lines_table.setCellWidget(r, 8, del_btn)

        self.lines_table.blockSignals(False)
        self._update_total()

    def _on_price_cell_changed(self, row, col):
        """Sync final price across all lines with the same model when col 5 is edited."""
        if col != 5 or row >= len(self._lines):
            return
        item = self.lines_table.item(row, col)
        if item is None:
            return
        text = item.text().replace(",", "").strip()
        try:
            new_price = float(text)
            if new_price < 0:
                raise ValueError
        except ValueError:
            self.lines_table.blockSignals(True)
            item.setText(fmt_pkr(self._lines[row][6]))
            self.lines_table.blockSignals(False)
            return
        model_id = self._lines[row][1]
        for i in range(len(self._lines)):
            if self._lines[i][1] == model_id:
                sid, mid, b, m, im, ref, _, pp = self._lines[i]
                self._lines[i] = (sid, mid, b, m, im, ref, new_price, pp)
        self._refresh_lines_table()

    def _remove_line(self, idx):
        self._lines.pop(idx)
        self._refresh_lines_table()

    def _get_total(self):
        subtotal = sum(l[6] for l in self._lines)
        return subtotal - self.discount_spin.value()

    def _update_total(self):
        total = self._get_total()
        self.total_label.setText(f"TOTAL: Rs. {fmt_pkr(total)}")
        if self._payment_mode == "split":
            self._update_split_bank_lbl()

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save(self):
        if not self._lines:
            QMessageBox.warning(self, "Missing", "Add at least one IMEI line.")
            return

        # ── Salesman validation ───────────────────────────────────────────────
        salesman_id = self.salesman_combo.currentData()
        if salesman_id is None:
            QMessageBox.warning(self, "Missing",
                "Please select a salesman before saving.")
            self.salesman_combo.setFocus()
            return

        supplier_as_customer_id = None
        if self._sale_type == "credit":
            _cdata = self.credit_combo.currentData()
            if _cdata is None:
                QMessageBox.warning(self, "Missing", "Select a credit customer.")
                return
            if _cdata["type"] == "customer":
                customer_id = _cdata["id"]
            else:
                customer_id = None
                supplier_as_customer_id = _cdata["id"]
            cash_name = cash_contact = None
        else:
            cash_contact = self.cash_contact.text().strip()
            cash_name = self.cash_name.text().strip().title()
            if not cash_contact:
                QMessageBox.warning(self, "Missing",
                    "Contact number is required for cash sales.")
                self.cash_contact.setFocus()
                return
            if not validate_phone(cash_contact):
                QMessageBox.warning(self, "Invalid Phone Number",
                    "Contact must start with 03 and be exactly 11 digits.\n"
                    "Example: 03155344522")
                self.cash_contact.setFocus()
                return
            if not cash_name:
                QMessageBox.warning(self, "Missing",
                    "Customer name is required for cash sales.")
                self.cash_name.setFocus()
                return
            customer_id = None

        date_str = self.date_edit.date().toString("dd/MM/yyyy")
        note = ""
        overall_discount = self.discount_spin.value()
        db_lines = [(s, m, imei, ref, final) for s, m, _, _, imei, ref, final, _pp in self._lines]

        # ── Below-cost confirmation ───────────────────────────────────────────
        below_cost = any(pp is not None and final < pp
                         for _, _, _, _, _, _, final, pp in self._lines)
        if below_cost:
            dlg = QMessageBox(self)
            dlg.setWindowTitle("Below Cost Warning")
            dlg.setText(
                "One or more items are being sold below purchase price.\n"
                "Do you want to continue?"
            )
            dlg.setIcon(QMessageBox.Icon.Warning)
            btn_continue = dlg.addButton("Continue", QMessageBox.ButtonRole.AcceptRole)
            dlg.addButton("Go Back", QMessageBox.ButtonRole.RejectRole)
            dlg.exec()
            if dlg.clickedButton() != btn_continue:
                return

        # ── Resolve payment method ────────────────────────────────────────────
        if self._sale_type == "credit":
            pay_method = "credit"
            pay_cash = 0.0
            pay_bank_id = None
            pay_bank_amt = 0.0
            pay_bank_ref = ""
        elif self._payment_mode == "cash":
            pay_method = "cash"
            pay_cash = self._get_total()
            pay_bank_id = None
            pay_bank_amt = 0.0
            pay_bank_ref = ""
        elif self._payment_mode == "bank":
            pay_bank_id = self.pay_bank_combo.currentData()
            if not pay_bank_id:
                QMessageBox.warning(self, "Payment", "Select a bank account for the bank transfer.")
                return
            pay_method = "bank"
            pay_cash = 0.0
            pay_bank_amt = self._get_total()
            pay_bank_ref = self.pay_bank_ref.text().strip()
        else:  # split
            pay_bank_id = self.pay_split_bank_combo.currentData()
            if not pay_bank_id:
                QMessageBox.warning(self, "Payment", "Select a bank account for the split payment.")
                return
            total = self._get_total()
            pay_cash = self.pay_split_cash_spin.value()
            pay_bank_amt = total - pay_cash
            if pay_bank_amt < 0:
                QMessageBox.warning(self, "Payment",
                    "Cash amount exceeds the invoice total.")
                return
            pay_method = "split"
            pay_bank_ref = self.pay_split_bank_ref.text().strip()

        try:
            sv_number, sv_id = db_save_sale(
                date_str, self._sale_type, customer_id,
                cash_name, cash_contact, note, overall_discount, db_lines,
                payment_method=pay_method, cash_paid=pay_cash,
                bank_account_id=pay_bank_id, bank_amount=pay_bank_amt,
                bank_ref=pay_bank_ref,
                salesman_id=salesman_id,
                supplier_as_customer_id=supplier_as_customer_id,
            )
        except sqlite3.IntegrityError as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save: {e}")
            return

        # Print thermal receipt
        try:
            from receipt import print_receipt
            print_receipt(sv_id, parent=self)
        except Exception:
            pass

        # WhatsApp for cash sales — only if checkbox is ticked
        if self._sale_type == "cash" and self.chk_whatsapp.isChecked():
            try:
                from whatsapp_handler import send_sale_whatsapp
                success, wa_msg = send_sale_whatsapp(sv_id)
                if not success and "Opened" in wa_msg:
                    QMessageBox.information(self, "WhatsApp", wa_msg)
            except Exception:
                pass

        QMessageBox.information(self, "Saved", f"Sale {sv_number} saved successfully.")
        self._on_save(sv_number, sv_id)

    def eventFilter(self, obj, event):
        if obj is self.imei_input:
            if event.type() == QEvent.Type.KeyPress:
                if self._imei_dropdown.isVisible():
                    key = event.key()
                    if key == Qt.Key.Key_Down:
                        self._imei_dropdown.move_selection(1)
                        return True
                    elif key == Qt.Key.Key_Up:
                        self._imei_dropdown.move_selection(-1)
                        return True
                    elif key == Qt.Key.Key_Escape:
                        self._imei_dropdown.hide()
                        return True
            elif event.type() == QEvent.Type.FocusOut:
                # Small delay so a click on the dropdown is processed before it hides
                QTimer.singleShot(120, lambda: (
                    self._imei_dropdown.hide()
                    if not self.imei_input.hasFocus() else None
                ))
        return super().eventFilter(obj, event)

    def hideEvent(self, event):
        self._imei_dropdown.hide()
        super().hideEvent(event)


# ── Sale List View ────────────────────────────────────────────────────────────

class SaleListView(QWidget):
    def __init__(self, on_new, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        top = QHBoxLayout()
        title = QLabel("Sales")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title.setStyleSheet("color:#1e293b;")
        top.addWidget(title)
        top.addStretch()
        top.addWidget(QLabel("Go to Voucher:"))
        self._goto_edit = QLineEdit()
        self._goto_edit.setPlaceholderText("SV-0001")
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
        self.btn_delete_sv = QPushButton("🗑 Delete")
        self.btn_delete_sv.setStyleSheet("""
            QPushButton { background:#fee2e2; color:#dc2626; border:1px solid #fca5a5;
                border-radius:5px; padding:6px 16px; font-size:10pt; }
            QPushButton:hover { background:#fecaca; }
            QPushButton:disabled { background:#f1f5f9; color:#94a3b8; border-color:#e2e8f0; }
        """)
        self.btn_delete_sv.setEnabled(False)
        self.btn_delete_sv.clicked.connect(self._delete_selected)
        top.addWidget(self.btn_delete_sv)
        btn_new = QPushButton("+ New Sale")
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

        fl.addWidget(QLabel("Type:"))
        self.type_filter = QComboBox()
        self.type_filter.addItem("All", None)
        self.type_filter.addItem("Cash", "cash")
        self.type_filter.addItem("Credit", "credit")
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

        self.table = _make_table(
            ["SV Number", "Date", "Type", "Customer", "Items", "Total (PKR)", "Discount (PKR)"]
        )
        hdr = self.table.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)   # Customer stretches
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)      # Items
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)      # Total (PKR)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)      # Discount (PKR)
        self.table.setColumnWidth(4, 55)
        self.table.setColumnWidth(5, 130)
        self.table.setColumnWidth(6, 130)
        self.table.doubleClicked.connect(self._edit_selected)
        self.table.itemSelectionChanged.connect(
            lambda: self.btn_edit.setEnabled(self.table.currentRow() >= 0)
        )
        self.table.itemSelectionChanged.connect(
            lambda: self.btn_delete_sv.setEnabled(self.table.currentRow() >= 0)
        )
        layout.addWidget(self.table, stretch=1)

        # Footer summary
        footer_row = QHBoxLayout()
        footer_row.addStretch()
        self._footer_qty_lbl = QLabel("")
        self._footer_qty_lbl.setStyleSheet(
            "color:#475569; font-size:10pt; font-weight:bold; padding:4px 16px;"
        )
        self._footer_val_lbl = QLabel("")
        self._footer_val_lbl.setStyleSheet(
            "color:#1e293b; font-size:11pt; font-weight:bold; padding:4px 16px;"
        )
        footer_row.addWidget(self._footer_qty_lbl)
        footer_row.addWidget(self._footer_val_lbl)
        layout.addLayout(footer_row)

        self.refresh()

    def refresh(self):
        from_iso = self.from_date.date().toString("yyyy-MM-dd")
        to_iso = self.to_date.date().toString("yyyy-MM-dd")
        sale_type = self.type_filter.currentData()
        rows = db_load_sales(from_iso, to_iso, sale_type)

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        total_qty = 0
        total_val = 0.0
        for r in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            sv_item = QTableWidgetItem(r["sv_number"])
            sv_item.setData(Qt.ItemDataRole.UserRole, dict(r))
            self.table.setItem(row, 0, sv_item)
            self.table.setItem(row, 1, QTableWidgetItem(r["date"]))
            type_item = QTableWidgetItem(r["type"].capitalize())
            type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, type_item)
            self.table.setItem(row, 3, QTableWidgetItem(r["customer_name"] or "—"))
            cnt = QTableWidgetItem(str(r["item_count"]))
            cnt.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 4, cnt)
            for col, val in [(5, r["total_amount"]), (6, r["discount"])]:
                item = QTableWidgetItem(fmt_pkr(val))
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                self.table.setItem(row, col, item)
            total_qty += int(r["item_count"] or 0)
            total_val += float(r["total_amount"] or 0)
        self.table.setSortingEnabled(True)
        self.btn_edit.setEnabled(False)

        n = len(rows)
        self._footer_qty_lbl.setText(
            f"{n} voucher{'s' if n != 1 else ''}    {total_qty} item{'s' if total_qty != 1 else ''}"
        )
        self._footer_val_lbl.setText(f"Total: Rs. {fmt_pkr(total_val)}")

    def _clear_filters(self):
        self.from_date.setDate(QDate.currentDate().addMonths(-1))
        self.to_date.setDate(QDate.currentDate())
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
                "Please enter a full voucher number, e.g. SV-0001")
            return
        conn = get_connection()
        row = conn.execute(
            "SELECT id FROM sale_vouchers WHERE UPPER(sv_number)=?", (raw,)
        ).fetchone()
        conn.close()
        if not row:
            QMessageBox.warning(self, "Not Found", f"Voucher {raw} not found.")
            return
        from edit_vouchers import SaleEditDialog
        dlg = SaleEditDialog(row["id"], self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
        self._goto_edit.clear()

    def _edit_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return
        sv_row = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        from edit_vouchers import SaleEditDialog
        dlg = SaleEditDialog(sv_row["id"], self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _view_detail(self):
        row = self.table.currentRow()
        if row < 0:
            return
        sv_row = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        SaleDetailDialog(sv_row, self).exec()

    def _delete_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return
        sv = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        from database import prompt_and_delete_voucher
        deleted = prompt_and_delete_voucher(
            self, "sale", sv["id"], sv["sv_number"], "Owner"
        )
        if deleted:
            self.refresh()


# ── Sold IMEI Dropdown ────────────────────────────────────────────────────────

class SoldImeiDropdown(QWidget):
    """Floating live-search dropdown for sold IMEIs (sales return use)."""
    imei_chosen = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet(
            "background:#dc2626; border:2px solid #dc2626; border-radius:4px;"
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
            QListWidget::item:hover { background:#fee2e2; color:#dc2626; }
            QListWidget::item:selected { background:#dc2626; color:#ffffff; }
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
            it = QListWidgetItem("  No sold IMEI found")
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            it.setForeground(QBrush(QColor("#94a3b8")))
            self._list.addItem(it)
        else:
            for r in results:
                text = (f"  {r['imei']}    {r['brand_name']} {r['model_name']}"
                        f"    {r['customer_name']}    PKR {fmt_pkr(r['sale_price'])}")
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
        new_row = 0 if current < 0 and delta > 0 else max(0, min(current + delta, count - 1))
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


# ── Sale Return Form ──────────────────────────────────────────────────────────

class SaleReturnForm(QWidget):
    def __init__(self, on_save, on_cancel, parent=None):
        super().__init__(parent)
        self._on_save = on_save
        self._on_cancel = on_cancel
        # (stock_item_id, model_id, brand, model, imei, sale_date, sale_price)
        self._lines = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        self.setStyleSheet(FORM_INPUT_STYLE)

        # ── Title bar ─────────────────────────────────────────────────────────
        top = QHBoxLayout()
        title = QLabel("New Sales Return")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title.setStyleSheet("color:#1e293b;")
        top.addWidget(title)
        top.addStretch()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet(BTN_SECONDARY)
        btn_cancel.clicked.connect(on_cancel)
        self.btn_save = QPushButton("Save Return")
        self.btn_save.setStyleSheet(BTN_PRIMARY)
        self.btn_save.setEnabled(False)
        self.btn_save.clicked.connect(self._save)
        top.addWidget(btn_cancel)
        top.addWidget(self.btn_save)
        layout.addLayout(top)

        # ── Header card ───────────────────────────────────────────────────────
        header = QFrame()
        header.setStyleSheet(CARD_STYLE)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 12, 16, 12)
        hl.setSpacing(16)

        dc = QVBoxLayout()
        dc.addWidget(QLabel("Return Date"))
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setMinimumWidth(130)
        dc.addWidget(self.date_edit)
        hl.addLayout(dc)

        cc = QVBoxLayout()
        cc.addWidget(QLabel("Credit Customer *"))
        self.customer_combo = QComboBox()
        self.customer_combo.setMinimumWidth(220)
        self.customer_combo.addItem("— Select Customer —", None)
        for c in db_customers_list():
            self.customer_combo.addItem(c["name"], c["id"])
        self.customer_combo.currentIndexChanged.connect(self._on_customer_changed)
        cc.addWidget(self.customer_combo)
        hl.addLayout(cc)

        nc = QVBoxLayout()
        nc.addWidget(QLabel("Notes (optional)"))
        self.notes_edit = QLineEdit()
        self.notes_edit.setPlaceholderText("Reason for return")
        self.notes_edit.setMinimumWidth(220)
        nc.addWidget(self.notes_edit)
        hl.addLayout(nc)

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
            "Type last 5+ digits — matching sold phones appear"
        )
        self.imei_input.setMinimumWidth(280)
        self.imei_input.setEnabled(False)
        self.imei_input.setProperty("enterKeepDefault", True)
        self.imei_input.textChanged.connect(self._on_imei_changed)
        self.imei_input.returnPressed.connect(self._imei_enter)
        search_row.addWidget(self.imei_input)
        search_row.addStretch()
        ll.addLayout(search_row)

        self._imei_dropdown = SoldImeiDropdown(self)
        self._imei_dropdown.imei_chosen.connect(self._on_imei_selected)
        self.imei_input.installEventFilter(self)

        self.lookup_status = QLabel("Select a customer first, then search by IMEI.")
        self.lookup_status.setStyleSheet(STATUS_INFO)
        ll.addWidget(self.lookup_status)
        layout.addWidget(lookup_card)

        # ── Lines table ───────────────────────────────────────────────────────
        self.lines_table = _make_table(
            ["#", "Brand", "Model", "IMEI", "Sale Date", "Sale Price (PKR)", ""]
        )
        _lh = self.lines_table.horizontalHeader()
        _lh.setStretchLastSection(False)
        _lh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)       # #
        _lh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)     # Brand
        _lh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)     # Model
        _lh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # IMEI
        _lh.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)       # Sale Date
        _lh.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)       # Sale Price
        _lh.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)       # Remove btn
        self.lines_table.setColumnWidth(0, 35)
        self.lines_table.setColumnWidth(4, 100)
        self.lines_table.setColumnWidth(5, 140)
        self.lines_table.setColumnWidth(6, 80)
        layout.addWidget(self.lines_table, stretch=1)

        # ── Footer ────────────────────────────────────────────────────────────
        footer = QHBoxLayout()
        footer.addStretch()
        self.total_label = QLabel("Return Total: PKR 0")
        self.total_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.total_label.setStyleSheet("color:#dc2626;")
        footer.addWidget(self.total_label)
        layout.addLayout(footer)

    # ── Customer / IMEI events ────────────────────────────────────────────────

    def _on_customer_changed(self):
        has = self.customer_combo.currentData() is not None
        self.imei_input.setEnabled(has)
        if has:
            self.lookup_status.setText(
                "Type last 5+ digits of IMEI to find sold phones."
            )
            self.lookup_status.setStyleSheet(STATUS_INFO)
            self.imei_input.setFocus()
        else:
            self.imei_input.clear()
            self._imei_dropdown.hide()
            self.lookup_status.setText("Select a customer first.")
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
        results = db_sold_imei_lookup(text)
        self._imei_dropdown.show_below(self.imei_input, results)
        if results:
            self.lookup_status.setText(
                f"{len(results)} sold phone(s) found — select from the dropdown."
            )
            self.lookup_status.setStyleSheet(STATUS_INFO)
        else:
            self.lookup_status.setText("No sold phone found for these digits.")
            self.lookup_status.setStyleSheet(STATUS_ERR)

    def _imei_enter(self):
        if self._imei_dropdown.isVisible():
            self._imei_dropdown.confirm_selection()

    def _on_imei_selected(self, data: dict):
        self.imei_input.blockSignals(True)
        self.imei_input.setText(data["imei"])
        self.imei_input.blockSignals(False)
        self._imei_dropdown.hide()

        customer_id   = self.customer_combo.currentData()
        customer_name = self.customer_combo.currentText()
        imei          = data["imei"]

        if any(l[4] == imei for l in self._lines):
            self.lookup_status.setText(f"IMEI {imei} is already in the return list.")
            self.lookup_status.setStyleSheet(STATUS_WARN)
            self.imei_input.clear()
            return

        actual_cid  = data.get("customer_id", 0)
        actual_name = data.get("customer_name", "Unknown")

        if actual_cid != customer_id:
            QMessageBox.warning(
                self, "Wrong Customer",
                f"This IMEI was sold to {actual_name} — "
                f"cannot return to {customer_name}."
            )
            self.lookup_status.setText("IMEI was sold to a different customer.")
            self.lookup_status.setStyleSheet(STATUS_ERR)
            self.imei_input.clear()
            return

        self._lines.append((
            data["stock_item_id"], data["model_id"],
            data["brand_name"], data["model_name"],
            imei, data["sale_date"], data["sale_price"],
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
        for idx, (sid, mid, brand, model, imei, sdate, price) in enumerate(self._lines):
            r = self.lines_table.rowCount()
            self.lines_table.insertRow(r)
            num = QTableWidgetItem(str(idx + 1))
            num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.lines_table.setItem(r, 0, num)
            self.lines_table.setItem(r, 1, QTableWidgetItem(brand))
            self.lines_table.setItem(r, 2, QTableWidgetItem(model))
            self.lines_table.setItem(r, 3, QTableWidgetItem(imei))
            self.lines_table.setItem(r, 4, QTableWidgetItem(sdate or "—"))
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
        customer_id = self.customer_combo.currentData()
        if not customer_id:
            QMessageBox.warning(self, "Missing", "Please select a credit customer.")
            return
        if not self._lines:
            QMessageBox.warning(self, "Missing", "Add at least one IMEI to return.")
            return

        date_str = self.date_edit.date().toString("dd/MM/yyyy")
        notes    = self.notes_edit.text().strip()
        db_lines = [(sid, mid, imei, price)
                    for sid, mid, _, _, imei, _, price in self._lines]

        try:
            sr_number, sr_id = db_save_sale_return(date_str, customer_id, db_lines, notes)
        except Exception as ex:
            QMessageBox.critical(self, "Save Error", str(ex))
            return

        try:
            from receipt import print_sale_return_receipt
            print_sale_return_receipt(sr_id, parent=self)
        except Exception:
            pass

        total = sum(price for _, _, _, _, _, _, price in self._lines)
        QMessageBox.information(
            self, "Saved",
            f"Sales return {sr_number} saved.\n"
            f"{len(self._lines)} item(s) returned to stock.\n"
            f"Customer balance reduced by PKR {fmt_pkr(total)}."
        )
        self._on_save(sr_number)

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


# ── Sale Return List View ──────────────────────────────────────────────────────

class SaleReturnListView(QWidget):
    def __init__(self, on_new, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        top = QHBoxLayout()
        title = QLabel("Sales Returns")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title.setStyleSheet("color:#1e293b;")
        top.addWidget(title)
        top.addStretch()
        self.btn_edit_sr = QPushButton("✏ Edit")
        self.btn_edit_sr.setStyleSheet(BTN_SECONDARY)
        self.btn_edit_sr.setEnabled(False)
        self.btn_edit_sr.clicked.connect(self._edit_selected)
        top.addWidget(self.btn_edit_sr)
        self.btn_delete_sr = QPushButton("🗑 Delete")
        self.btn_delete_sr.setStyleSheet("""
            QPushButton { background:#fee2e2; color:#dc2626; border:1px solid #fca5a5;
                border-radius:5px; padding:6px 16px; font-size:10pt; }
            QPushButton:hover { background:#fecaca; }
            QPushButton:disabled { background:#f1f5f9; color:#94a3b8; border-color:#e2e8f0; }
        """)
        self.btn_delete_sr.setEnabled(False)
        self.btn_delete_sr.clicked.connect(self._delete_selected)
        top.addWidget(self.btn_delete_sr)
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
            ["SR Number", "Date", "Customer", "Items", "Return Amount (PKR)", "Notes"]
        )
        hdr = self.table.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)   # Customer stretches
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)      # Items
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)      # Return Amount (PKR)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)    # Notes stretches
        self.table.setColumnWidth(3, 55)
        self.table.setColumnWidth(4, 150)
        self.table.doubleClicked.connect(self._edit_selected)
        self.table.itemSelectionChanged.connect(
            lambda: self.btn_edit_sr.setEnabled(self.table.currentRow() >= 0)
        )
        self.table.itemSelectionChanged.connect(
            lambda: self.btn_delete_sr.setEnabled(self.table.currentRow() >= 0)
        )
        layout.addWidget(self.table, stretch=1)

        self.refresh()

    def refresh(self):
        from_iso = self.from_date.date().toString("yyyy-MM-dd")
        to_iso = self.to_date.date().toString("yyyy-MM-dd")
        rows = db_load_sale_returns(from_iso, to_iso)

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for r in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            sr_item = QTableWidgetItem(r["sr_number"])
            sr_item.setData(Qt.ItemDataRole.UserRole, dict(r))
            self.table.setItem(row, 0, sr_item)
            self.table.setItem(row, 1, QTableWidgetItem(r["date"]))
            self.table.setItem(row, 2, QTableWidgetItem(r["customer_name"] or "—"))
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
        self.btn_edit_sr.setEnabled(False)

    def _clear_filters(self):
        self.from_date.setDate(QDate.currentDate().addMonths(-1))
        self.to_date.setDate(QDate.currentDate())
        self.refresh()

    def _edit_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return
        sr = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        from edit_vouchers import SimpleReturnEditDialog
        dlg = SimpleReturnEditDialog(
            "sale_return", sr["id"], sr["sr_number"], sr["date"], sr["notes"], self
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _delete_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return
        sr = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        from database import prompt_and_delete_voucher
        deleted = prompt_and_delete_voucher(
            self, "sale_return", sr["id"], sr["sr_number"], "Owner"
        )
        if deleted:
            self.refresh()


# ── Sale Page ─────────────────────────────────────────────────────────────────

class SalePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:#f1f5f9;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._tabs = QTabWidget()
        outer.addWidget(self._tabs)

        # ── Sales tab ──────────────────────────────────────────────────────────
        sales_container = QWidget()
        sales_container.setStyleSheet("background:#f1f5f9;")
        sales_layout = QVBoxLayout(sales_container)
        sales_layout.setContentsMargins(0, 0, 0, 0)
        sales_layout.setSpacing(0)

        self._stack = QStackedWidget()
        sales_layout.addWidget(self._stack)

        self._list_view = SaleListView(on_new=self._show_form)
        self._stack.addWidget(self._list_view)
        self._form = None

        # ── Returns tab ────────────────────────────────────────────────────────
        returns_container = QWidget()
        returns_container.setStyleSheet("background:#f1f5f9;")
        returns_layout = QVBoxLayout(returns_container)
        returns_layout.setContentsMargins(0, 0, 0, 0)
        returns_layout.setSpacing(0)

        self._returns_stack = QStackedWidget()
        returns_layout.addWidget(self._returns_stack)

        self._return_list_view = SaleReturnListView(on_new=self._show_return_form)
        self._returns_stack.addWidget(self._return_list_view)
        self._return_form = None

        self._tabs.addTab(sales_container, "Sales")
        self._tabs.addTab(returns_container, "Returns")

    # ── Sales tab methods ──────────────────────────────────────────────────────

    def _show_form(self):
        self._form = SaleForm(on_save=self._on_saved, on_cancel=self._show_list)
        self._stack.addWidget(self._form)
        self._stack.setCurrentWidget(self._form)

    def new_sale_with_imei(self, imei: str):
        """Open (or reuse) the sale form and pre-fill the given IMEI."""
        self._tabs.setCurrentIndex(0)
        if self._form is None:
            self._show_form()
        else:
            self._stack.setCurrentWidget(self._form)
        if self._form:
            self._form.prefill_imei(imei)

    def _on_saved(self, sv_number, sv_id):
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
        self._return_form = SaleReturnForm(
            on_save=self._on_return_saved,
            on_cancel=self._show_return_list,
        )
        self._returns_stack.addWidget(self._return_form)
        self._returns_stack.setCurrentWidget(self._return_form)

    def _on_return_saved(self, sr_number):
        self._show_return_list()

    def _show_return_list(self):
        self._returns_stack.setCurrentWidget(self._return_list_view)
        self._return_list_view.refresh()
        if self._return_form is not None:
            self._returns_stack.removeWidget(self._return_form)
            self._return_form.deleteLater()
            self._return_form = None
