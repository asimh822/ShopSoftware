"""
edit_vouchers.py — Edit dialogs and DB update functions for all voucher types.
Item 9 of the 9-point change set.
"""

import sqlite3
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QComboBox, QLineEdit,
    QDoubleSpinBox, QDateEdit, QMessageBox, QHeaderView,
    QAbstractItemView, QFrame, QStackedWidget, QDialogButtonBox,
    QListWidget, QListWidgetItem, QCheckBox,
)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QFont, QBrush, QColor, QDoubleValidator

from database import get_connection, db_bank_accounts

# ── Shared styles ──────────────────────────────────────────────────────────────

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
FORM_INPUT_STYLE = """
    QLineEdit {
        background:#ffffff; color:#1e293b;
        border:1px solid #cbd5e1; border-radius:4px; padding:5px 8px; font-size:10pt;
    }
    QLineEdit:focus { border:2px solid #2563eb; }
    QLineEdit:disabled { background:#f1f5f9; color:#94a3b8; }
    QDoubleSpinBox {
        background:#ffffff; color:#1e293b;
        border:1px solid #cbd5e1; border-radius:4px; padding:4px 8px; font-size:10pt;
    }
    QComboBox {
        background:#ffffff; color:#1e293b;
        border:1px solid #cbd5e1; border-radius:4px; padding:5px 8px; font-size:10pt;
    }
    QComboBox QAbstractItemView {
        background:#ffffff; color:#1e293b;
        selection-background-color:#dbeafe; selection-color:#1e40af;
    }
    QComboBox:disabled { background:#f1f5f9; color:#94a3b8; }
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
    t.setStyleSheet(TABLE_STYLE)
    return t


# ── DB: load helpers ───────────────────────────────────────────────────────────

def db_load_sale_for_edit(sv_id):
    conn = get_connection()
    sv = dict(conn.execute("SELECT * FROM sale_vouchers WHERE id=?", (sv_id,)).fetchone())
    lines = [dict(r) for r in conn.execute("""
        SELECT sl.id, sl.stock_item_id, sl.model_id, sl.imei,
               sl.reference_price, sl.final_price,
               b.name AS brand_name, m.name AS model_name
        FROM sale_lines sl
        JOIN models m ON m.id = sl.model_id
        JOIN brands b ON b.id = m.brand_id
        WHERE sl.sv_id=?
        ORDER BY sl.id
    """, (sv_id,)).fetchall()]
    cust = None
    if sv.get("customer_id"):
        row = conn.execute(
            "SELECT name, contact FROM customers WHERE id=?", (sv["customer_id"],)
        ).fetchone()
        if row:
            cust = dict(row)
    conn.close()
    return sv, lines, cust


def db_load_purchase_for_edit(pv_id):
    conn = get_connection()
    pv = dict(conn.execute("SELECT * FROM purchase_vouchers WHERE id=?", (pv_id,)).fetchone())
    lines = [dict(r) for r in conn.execute("""
        SELECT pl.id AS pl_id, pl.model_id, pl.imei, pl.purchase_price,
               COALESCE(si.id, 0) AS stock_item_id,
               COALESCE(si.status, 'unknown') AS stock_status,
               b.name AS brand_name, m.name AS model_name
        FROM purchase_lines pl
        JOIN models m ON m.id = pl.model_id
        JOIN brands b ON b.id = m.brand_id
        LEFT JOIN stock_items si ON si.purchase_line_id = pl.id
        WHERE pl.pv_id=?
        ORDER BY pl.id
    """, (pv_id,)).fetchall()]
    conn.close()
    return pv, lines


def db_lookup_payment(voucher_number):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM payments WHERE voucher_number=?", (voucher_number,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def db_lookup_journal_entry(jv_number, party_type=None, party_id=None):
    """Return journal_entries row for this jv_number (optionally filtered by party)."""
    conn = get_connection()
    if party_type and party_id:
        row = conn.execute(
            "SELECT * FROM journal_entries WHERE jv_number=? AND party_type=? AND party_id=?",
            (jv_number, party_type, party_id),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM journal_entries WHERE jv_number=?", (jv_number,)
        ).fetchone()
    conn.close()
    return dict(row) if row else None


def db_load_sr_for_edit(sr_id):
    conn = get_connection()
    row = conn.execute("""
        SELECT sr.id, sr.sr_number, sr.date, sr.notes, sr.customer_id,
               COALESCE(c.name, '—') AS customer_name,
               COUNT(srl.id) AS item_count,
               COALESCE(SUM(srl.return_price), 0) AS return_amount
        FROM sale_returns sr
        LEFT JOIN customers c ON c.id = sr.customer_id
        LEFT JOIN sale_return_lines srl ON srl.sr_id = sr.id
        WHERE sr.id=?
        GROUP BY sr.id
    """, (sr_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def db_load_pr_for_edit(pr_id):
    conn = get_connection()
    row = conn.execute("""
        SELECT pr.id, pr.pr_number, pr.date, pr.notes, pr.supplier_id,
               COALESCE(s.name, '—') AS supplier_name,
               COUNT(prl.id) AS item_count,
               COALESCE(SUM(prl.return_price), 0) AS return_amount
        FROM purchase_returns pr
        LEFT JOIN suppliers s ON s.id = pr.supplier_id
        LEFT JOIN purchase_return_lines prl ON prl.pr_id = pr.id
        WHERE pr.id=?
        GROUP BY pr.id
    """, (pr_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ── DB: update functions ───────────────────────────────────────────────────────

def db_update_sale(sv_id, date_str, sale_type, customer_id, cash_name, cash_contact,
                   note, overall_discount, lines, payment_method, cash_paid,
                   bank_account_id, bank_amount, bank_ref):
    """
    lines = [(stock_item_id, model_id, imei, ref_price, final_price), ...]
    Clean-replaces all sale_lines. Adjusts stock_items accordingly.
    Ledger balances recompute automatically (reads from sale_vouchers).
    """
    conn = get_connection()
    try:
        c = conn.cursor()
        # Revert old sale_lines' stock_items to in_stock
        c.execute("""
            UPDATE stock_items SET status='in_stock', sold_line_id=NULL
            WHERE sold_line_id IN (SELECT id FROM sale_lines WHERE sv_id=?)
        """, (sv_id,))
        c.execute("DELETE FROM sale_lines WHERE sv_id=?", (sv_id,))

        subtotal = sum(fp for _, _, _, _, fp in lines)
        total_amount = subtotal - (overall_discount or 0)

        for stock_item_id, model_id, imei, ref_price, final_price in lines:
            per_disc = (ref_price or 0) - final_price
            c.execute("""
                INSERT INTO sale_lines
                (sv_id, stock_item_id, model_id, imei, reference_price, discount, final_price)
                VALUES (?,?,?,?,?,?,?)
            """, (sv_id, stock_item_id, model_id, imei, ref_price, per_disc, final_price))
            sl_id = c.lastrowid
            c.execute(
                "UPDATE stock_items SET status='sold', sold_line_id=? WHERE id=?",
                (sl_id, stock_item_id),
            )

        c.execute("""
            UPDATE sale_vouchers
            SET date=?, type=?, customer_id=?, cash_customer_name=?,
                cash_customer_contact=?, total_amount=?, discount=?, note=?,
                payment_method=?, cash_paid=?, bank_account_id=?, bank_amount=?, bank_ref=?
            WHERE id=?
        """, (date_str, sale_type, customer_id, cash_name, cash_contact,
              total_amount, overall_discount or 0, note or "",
              payment_method, cash_paid, bank_account_id, bank_amount, bank_ref or "",
              sv_id))
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()


def db_update_purchase(pv_id, date_str, supplier_id, notes, lines):
    """
    lines = [(model_id, imei, purchase_price), ...]
    Handles add/remove/price-change vs existing purchase_lines.
    Raises ValueError if a removed IMEI has already been sold.
    """
    conn = get_connection()
    try:
        c = conn.cursor()
        old_rows = c.execute("""
            SELECT pl.id AS pl_id, pl.imei, pl.model_id, pl.purchase_price,
                   COALESCE(si.id, 0) AS stock_item_id,
                   COALESCE(si.status, 'unknown') AS stock_status
            FROM purchase_lines pl
            LEFT JOIN stock_items si ON si.purchase_line_id = pl.id
            WHERE pl.pv_id=?
        """, (pv_id,)).fetchall()

        old_by_imei = {r["imei"]: dict(r) for r in old_rows}
        new_imei_set = {imei for _, imei, _ in lines}

        # Remove lines no longer in the new set
        for imei, old in old_by_imei.items():
            if imei not in new_imei_set:
                if old["stock_item_id"] and old["stock_status"] == "sold":
                    raise ValueError(
                        f"Cannot remove IMEI {imei} — it has already been sold.\n"
                        "Process a Sales Return first."
                    )
                if old["stock_item_id"]:
                    c.execute("DELETE FROM stock_items WHERE id=?", (old["stock_item_id"],))
                c.execute("DELETE FROM purchase_lines WHERE id=?", (old["pl_id"],))

        # Add or update lines
        for model_id, imei, price in lines:
            if imei in old_by_imei:
                # Update price
                c.execute(
                    "UPDATE purchase_lines SET purchase_price=?, model_id=? WHERE pv_id=? AND imei=?",
                    (price, model_id, pv_id, imei),
                )
                si_id = old_by_imei[imei]["stock_item_id"]
                if si_id:
                    c.execute(
                        "UPDATE stock_items SET purchase_price=?, model_id=? WHERE id=?",
                        (price, model_id, si_id),
                    )
            else:
                # New line
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
                    c.execute(
                        "UPDATE stock_items SET model_id=?, purchase_line_id=?, "
                        "purchase_price=?, status='in_stock', sold_line_id=NULL WHERE id=?",
                        (model_id, pl_id, price, existing["id"]),
                    )
                else:
                    c.execute(
                        "INSERT INTO stock_items "
                        "(model_id, imei, purchase_line_id, purchase_price, status) "
                        "VALUES (?,?,?,?,'in_stock')",
                        (model_id, imei, pl_id, price),
                    )

        total = sum(p for _, _, p in lines)
        c.execute(
            "UPDATE purchase_vouchers SET date=?, supplier_id=?, notes=?, total_amount=? "
            "WHERE id=?",
            (date_str, supplier_id, notes or "", total, pv_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()


def db_update_payment(payment_id, date_str, amount, notes):
    """Update a payments record. Ledger recomputes automatically."""
    conn = get_connection()
    conn.execute(
        "UPDATE payments SET date=?, amount=?, notes=? WHERE id=?",
        (date_str, amount, notes or "", payment_id),
    )
    conn.commit()
    conn.close()


def db_delete_payment(payment_id):
    """Permanently delete a CP or CR payment record."""
    conn = get_connection()
    conn.execute("DELETE FROM payments WHERE id=?", (payment_id,))
    conn.commit()
    conn.close()


def db_lookup_bank_transaction(voucher_number):
    """Look up a bank_transactions row by voucher number (includes bank account name)."""
    conn = get_connection()
    row = conn.execute("""
        SELECT bt.*, COALESCE(ba.name, '') AS bank_name
        FROM bank_transactions bt
        LEFT JOIN bank_accounts ba ON ba.id = bt.bank_account_id
        WHERE bt.voucher_number = ?
    """, (voucher_number,)).fetchone()
    conn.close()
    return dict(row) if row else None


def db_update_bank_transaction(tx_id, date_str, amount, notes):
    """Update date, amount and notes on a bank_transactions row."""
    conn = get_connection()
    conn.execute(
        "UPDATE bank_transactions SET date=?, amount=?, notes=? WHERE id=?",
        (date_str, amount, notes or "", tx_id),
    )
    conn.commit()
    conn.close()


def db_delete_bank_transaction(tx_id):
    """Permanently delete a bank_transactions row."""
    conn = get_connection()
    conn.execute("DELETE FROM bank_transactions WHERE id=?", (tx_id,))
    conn.commit()
    conn.close()


def db_update_journal_entry(je_id, date_str, amount, entry_type, notes):
    """Update a single-party journal_entries row."""
    conn = get_connection()
    conn.execute(
        "UPDATE journal_entries SET date=?, amount=?, type=?, notes=? WHERE id=?",
        (date_str, amount, entry_type, notes or "", je_id),
    )
    conn.commit()
    conn.close()


def db_update_sale_return(sr_id, date_str, notes):
    conn = get_connection()
    conn.execute(
        "UPDATE sale_returns SET date=?, notes=? WHERE id=?",
        (date_str, notes or "", sr_id),
    )
    conn.commit()
    conn.close()


def db_update_purchase_return(pr_id, date_str, notes):
    conn = get_connection()
    conn.execute(
        "UPDATE purchase_returns SET date=?, notes=? WHERE id=?",
        (date_str, notes or "", pr_id),
    )
    conn.commit()
    conn.close()


# ── Internal IMEI picker (for adding to a sale during edit) ───────────────────

class _ImeiPickerDialog(QDialog):
    """Search in-stock IMEIs to add to a sale during edit."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add IMEI to Sale")
        self.setMinimumWidth(520)
        self.resize(520, 380)
        self._result = None

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        row = QHBoxLayout()
        lbl = QLabel("IMEI digits:")
        lbl.setMinimumWidth(80)
        row.addWidget(lbl)
        self._inp = QLineEdit()
        self._inp.setPlaceholderText("Type at least 3 digits…")
        self._inp.returnPressed.connect(self._search)
        row.addWidget(self._inp, stretch=1)
        btn = QPushButton("Search")
        btn.setStyleSheet(BTN_SECONDARY)
        btn.clicked.connect(self._search)
        row.addWidget(btn)
        layout.addLayout(row)

        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.doubleClicked.connect(self._accept_selected)
        layout.addWidget(self._list, stretch=1)

        self._status = QLabel("Type digits and press Search.")
        self._status.setStyleSheet("color:#64748b; font-size:9pt;")
        layout.addWidget(self._status)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._accept_selected)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _search(self):
        from sales import db_imei_lookup
        prefix = self._inp.text().strip()
        if len(prefix) < 3:
            self._status.setText("Type at least 3 digits.")
            return
        results = db_imei_lookup(prefix)
        self._list.clear()
        if not results:
            self._status.setText("No in-stock IMEI found for those digits.")
            return
        self._status.setText(f"{len(results)} match(es) found.")
        for r in results:
            item = QListWidgetItem(
                f"{r['imei']}  —  {r['brand_name']} {r['model_name']}"
                f"  (Ref: PKR {fmt_pkr(r['reference_price'])})"
            )
            item.setData(Qt.ItemDataRole.UserRole, r)
            self._list.addItem(item)
        if self._list.count() == 1:
            self._list.setCurrentRow(0)

    def _accept_selected(self):
        item = self._list.currentItem()
        if not item:
            QMessageBox.warning(self, "Select", "Select an IMEI from the list.")
            return
        self._result = item.data(Qt.ItemDataRole.UserRole)
        self.accept()

    def picked(self):
        return self._result


# ── Internal IMEI-line adder for purchase edit ────────────────────────────────

class _PurchaseLineAddDialog(QDialog):
    """Add a new brand/model/IMEI/price line to a purchase during edit."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Purchase Line")
        self.setFixedWidth(420)
        self._result = None
        self.setStyleSheet(FORM_INPUT_STYLE)

        from purchase import db_brands_list, db_models_for_brand
        self._db_models_for_brand = db_models_for_brand

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        g = QHBoxLayout()
        g.addWidget(QLabel("Brand:"))
        self._brand_combo = QComboBox()
        self._brand_combo.setMinimumWidth(140)
        self._brand_combo.addItem("— Brand —", None)
        for b in db_brands_list():
            self._brand_combo.addItem(b["name"], b["id"])
        self._brand_combo.currentIndexChanged.connect(self._on_brand)
        g.addWidget(self._brand_combo)
        layout.addLayout(g)

        g2 = QHBoxLayout()
        g2.addWidget(QLabel("Model:"))
        self._model_combo = QComboBox()
        self._model_combo.setMinimumWidth(160)
        self._model_combo.addItem("— Model —", None)
        self._model_combo.currentIndexChanged.connect(self._on_model)
        g2.addWidget(self._model_combo)
        layout.addLayout(g2)

        g3 = QHBoxLayout()
        g3.addWidget(QLabel("IMEI:"))
        self._imei_edit = QLineEdit()
        self._imei_edit.setMaxLength(20)
        self._imei_edit.setPlaceholderText("15-digit IMEI")
        g3.addWidget(self._imei_edit)
        layout.addLayout(g3)

        g4 = QHBoxLayout()
        g4.addWidget(QLabel("Purchase Price (PKR):"))
        self._price_spin = QDoubleSpinBox()
        self._price_spin.setRange(0, 9_999_999)
        self._price_spin.setDecimals(0)
        self._price_spin.setSingleStep(500)
        g4.addWidget(self._price_spin)
        layout.addLayout(g4)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._validate_and_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_brand(self):
        bid = self._brand_combo.currentData()
        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        self._model_combo.addItem("— Model —", None)
        if bid:
            for m in self._db_models_for_brand(bid):
                self._model_combo.addItem(m["name"], m["id"])
        self._model_combo.blockSignals(False)
        self._price_spin.setValue(0)

    def _on_model(self):
        mid = self._model_combo.currentData()
        if not mid:
            return
        conn = get_connection()
        row = conn.execute(
            "SELECT reference_price FROM models WHERE id=?", (mid,)
        ).fetchone()
        conn.close()
        if row and row["reference_price"]:
            self._price_spin.setValue(float(row["reference_price"]))

    def _validate_and_accept(self):
        if not self._brand_combo.currentData():
            QMessageBox.warning(self, "Missing", "Select a brand.")
            return
        if not self._model_combo.currentData():
            QMessageBox.warning(self, "Missing", "Select a model.")
            return
        imei = self._imei_edit.text().strip()
        if not imei:
            QMessageBox.warning(self, "Missing", "Enter IMEI.")
            return
        if self._price_spin.value() <= 0:
            QMessageBox.warning(self, "Missing", "Enter purchase price.")
            return
        # Check IMEI not already in stock
        conn = get_connection()
        existing = conn.execute(
            "SELECT status FROM stock_items WHERE imei=?", (imei,)
        ).fetchone()
        conn.close()
        if existing and existing["status"] == "in_stock":
            QMessageBox.warning(self, "Duplicate",
                f"IMEI {imei} is already in stock.")
            return
        brand_name = self._brand_combo.currentText()
        model_name = self._model_combo.currentText()
        self._result = {
            "model_id": self._model_combo.currentData(),
            "brand_name": brand_name,
            "model_name": model_name,
            "imei": imei,
            "purchase_price": self._price_spin.value(),
        }
        self.accept()

    def picked(self):
        return self._result


# ── Sale Edit Dialog ───────────────────────────────────────────────────────────

class SaleEditDialog(QDialog):
    """Full edit dialog for a sale voucher."""

    def __init__(self, sv_id, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        sv, lines, cust = db_load_sale_for_edit(sv_id)
        self._sv = sv

        # Internal lines list: list of dicts
        self._lines = [
            {
                "stock_item_id": r["stock_item_id"],
                "model_id": r["model_id"],
                "brand_name": r["brand_name"],
                "model_name": r["model_name"],
                "imei": r["imei"],
                "ref_price": float(r["reference_price"] or 0),
                "final_price": float(r["final_price"] or 0),
            }
            for r in lines
        ]

        self.setWindowTitle(f"Edit Sale — {sv['sv_number']}")
        self.setMinimumWidth(960)
        self.resize(960, 720)
        self.setStyleSheet(FORM_INPUT_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)

        # ── Title bar ─────────────────────────────────────────────────────────
        top = QHBoxLayout()
        lbl = QLabel(f"Edit Sale — {sv['sv_number']}")
        lbl.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        lbl.setStyleSheet("color:#1e293b;")
        top.addWidget(lbl)
        top.addStretch()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet(BTN_SECONDARY)
        btn_cancel.clicked.connect(self.reject)
        self.btn_save = QPushButton("Save Changes")
        self.btn_save.setStyleSheet(BTN_PRIMARY)
        self.btn_save.clicked.connect(self._save)
        top.addWidget(btn_cancel)
        top.addWidget(self.btn_save)
        root.addLayout(top)

        # ── Header card ───────────────────────────────────────────────────────
        hdr = QFrame()
        hdr.setStyleSheet(CARD_STYLE)
        hl = QVBoxLayout(hdr)
        hl.setContentsMargins(14, 10, 14, 10)
        hl.setSpacing(8)

        row1 = QHBoxLayout()
        row1.setSpacing(14)

        dc = QVBoxLayout()
        dc.addWidget(QLabel("Date"))
        self.date_edit = QDateEdit()
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setMinimumWidth(130)
        # Parse existing date DD/MM/YYYY
        d_parts = sv["date"].split("/")
        self.date_edit.setDate(QDate(int(d_parts[2]), int(d_parts[1]), int(d_parts[0])))
        dc.addWidget(self.date_edit)
        row1.addLayout(dc)

        # Sale type toggle
        self._sale_type = sv["type"]
        tc = QVBoxLayout()
        tc.addWidget(QLabel("Sale Type"))
        trow = QHBoxLayout()
        trow.setSpacing(0)
        self.btn_cash = QPushButton("Cash")
        self.btn_cash.setFixedHeight(30)
        self.btn_credit = QPushButton("Credit")
        self.btn_credit.setFixedHeight(30)
        self.btn_cash.setStyleSheet(
            (BTN_TOGGLE_ON if self._sale_type == "cash" else BTN_TOGGLE_OFF)
            + "QPushButton{border-radius:5px 0 0 5px;}"
        )
        self.btn_credit.setStyleSheet(
            (BTN_TOGGLE_ON if self._sale_type == "credit" else BTN_TOGGLE_OFF)
            + "QPushButton{border-radius:0 5px 5px 0; border-left:none;}"
        )
        self.btn_cash.clicked.connect(lambda: self._set_type("cash"))
        self.btn_credit.clicked.connect(lambda: self._set_type("credit"))
        trow.addWidget(self.btn_cash)
        trow.addWidget(self.btn_credit)
        tc.addLayout(trow)
        row1.addLayout(tc)

        nc = QVBoxLayout()
        nc.addWidget(QLabel("Note"))
        self.note_edit = QLineEdit(sv.get("note") or "")
        self.note_edit.setMinimumWidth(200)
        nc.addWidget(self.note_edit)
        row1.addLayout(nc)
        row1.addStretch()
        hl.addLayout(row1)

        # Customer section (stacked)
        self.customer_stack = QStackedWidget()
        self.customer_stack.setFixedHeight(50)

        # Cash page
        cash_w = QFrame()
        cash_row = QHBoxLayout(cash_w)
        cash_row.setContentsMargins(0, 0, 0, 0)
        cash_row.setSpacing(10)
        cash_row.addWidget(QLabel("Contact:"))
        self.cash_contact = QLineEdit(sv.get("cash_customer_contact") or "")
        self.cash_contact.setMaxLength(11)
        self.cash_contact.setMinimumWidth(140)
        cash_row.addWidget(self.cash_contact)
        cash_row.addWidget(QLabel("Name:"))
        self.cash_name = QLineEdit(sv.get("cash_customer_name") or "")
        self.cash_name.setMinimumWidth(160)
        cash_row.addWidget(self.cash_name)
        cash_row.addStretch()
        self.customer_stack.addWidget(cash_w)

        # Credit page
        credit_w = QFrame()
        credit_row = QHBoxLayout(credit_w)
        credit_row.setContentsMargins(0, 0, 0, 0)
        credit_row.setSpacing(10)
        credit_row.addWidget(QLabel("Customer:"))
        self.credit_combo = QComboBox()
        self.credit_combo.setMinimumWidth(220)
        from sales import db_customers_list
        self.credit_combo.addItem("— Select Customer —", None)
        for c in db_customers_list():
            self.credit_combo.addItem(c["name"], c["id"])
            if sv.get("customer_id") and c["id"] == sv["customer_id"]:
                self.credit_combo.setCurrentIndex(self.credit_combo.count() - 1)
        credit_row.addWidget(self.credit_combo)
        credit_row.addStretch()
        self.customer_stack.addWidget(credit_w)

        hl.addWidget(self.customer_stack)
        self.customer_stack.setCurrentIndex(0 if self._sale_type == "cash" else 1)
        root.addWidget(hdr)

        # ── Lines table ───────────────────────────────────────────────────────
        lines_hdr = QHBoxLayout()
        lines_lbl = QLabel("Sale Lines")
        lines_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        lines_lbl.setStyleSheet("color:#1e293b;")
        lines_hdr.addWidget(lines_lbl)
        lines_hdr.addStretch()
        btn_add_imei = QPushButton("+ Add IMEI")
        btn_add_imei.setStyleSheet(BTN_SECONDARY)
        btn_add_imei.clicked.connect(self._add_imei)
        lines_hdr.addWidget(btn_add_imei)
        root.addLayout(lines_hdr)

        self.lines_table = QTableWidget(0, 6)
        self.lines_table.setHorizontalHeaderLabels(
            ["Brand", "Model", "IMEI", "Ref Price (PKR)", "Final Price (PKR)", ""]
        )
        self.lines_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.lines_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.lines_table.setAlternatingRowColors(True)
        self.lines_table.verticalHeader().setVisible(False)
        hh = self.lines_table.horizontalHeader()
        hh.setStretchLastSection(False)
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)    # Brand
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Model — fills spare width
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)    # IMEI
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)    # Ref Price
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)    # Final Price
        hh.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)    # Remove
        self.lines_table.setColumnWidth(0, 90)
        self.lines_table.setColumnWidth(2, 160)
        self.lines_table.setColumnWidth(3, 150)
        self.lines_table.setColumnWidth(4, 170)
        self.lines_table.setColumnWidth(5, 90)
        self.lines_table.setStyleSheet(TABLE_STYLE)
        self.lines_table.verticalHeader().setDefaultSectionSize(38)
        self.lines_table.setMinimumHeight(200)
        root.addWidget(self.lines_table, stretch=1)
        # NOTE: total_lbl must be created BEFORE _rebuild_lines_table() is
        # called, because _rebuild_lines_table() → _update_total() references
        # self.total_lbl.  The layout is added to root afterwards so the visual
        # order (table → footer) is preserved.
        foot_row = QHBoxLayout()
        foot_row.addStretch()
        foot_row.addWidget(QLabel("Overall Discount (PKR):"))
        self.discount_spin = QDoubleSpinBox()
        self.discount_spin.setRange(0, 9_999_999)
        self.discount_spin.setDecimals(0)
        self.discount_spin.setSingleStep(100)
        self.discount_spin.setValue(float(sv.get("discount") or 0))
        self.discount_spin.valueChanged.connect(self._update_total)
        foot_row.addWidget(self.discount_spin)
        self.total_lbl = QLabel("")
        self.total_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.total_lbl.setStyleSheet("color:#1e293b; padding-left:20px;")
        foot_row.addWidget(self.total_lbl)

        self._rebuild_lines_table()   # safe — total_lbl now exists

        root.addLayout(foot_row)

        # ── Payment section (cash sales only) ─────────────────────────────────
        self.pay_card = QFrame()
        self.pay_card.setStyleSheet(CARD_STYLE)
        pay_layout = QVBoxLayout(self.pay_card)
        pay_layout.setContentsMargins(14, 10, 14, 10)
        pay_layout.setSpacing(8)

        pay_title = QLabel("Payment")
        pay_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        pay_layout.addWidget(pay_title)

        pay_toggle_row = QHBoxLayout()
        pay_toggle_row.setSpacing(0)
        self._payment_mode = sv.get("payment_method") or "cash"
        self.pay_btn_cash  = QPushButton("Cash")
        self.pay_btn_cash.setFixedHeight(28)
        self.pay_btn_bank  = QPushButton("Bank Transfer")
        self.pay_btn_bank.setFixedHeight(28)
        self.pay_btn_split = QPushButton("Split")
        self.pay_btn_split.setFixedHeight(28)
        for btn, mode in [(self.pay_btn_cash, "cash"),
                          (self.pay_btn_bank, "bank"),
                          (self.pay_btn_split, "split")]:
            is_on = (mode == self._payment_mode)
            btn.setStyleSheet(BTN_TOGGLE_ON if is_on else BTN_TOGGLE_OFF)
        self.pay_btn_cash.setStyleSheet(
            self.pay_btn_cash.styleSheet() + "QPushButton{border-radius:5px 0 0 5px;}"
        )
        self.pay_btn_split.setStyleSheet(
            self.pay_btn_split.styleSheet() + "QPushButton{border-radius:0 5px 5px 0; border-left:none;}"
        )
        self.pay_btn_bank.setStyleSheet(
            self.pay_btn_bank.styleSheet() + "QPushButton{border-left:none;}"
        )
        self.pay_btn_cash.clicked.connect(lambda: self._set_payment_mode("cash"))
        self.pay_btn_bank.clicked.connect(lambda: self._set_payment_mode("bank"))
        self.pay_btn_split.clicked.connect(lambda: self._set_payment_mode("split"))
        pay_toggle_row.addWidget(self.pay_btn_cash)
        pay_toggle_row.addWidget(self.pay_btn_bank)
        pay_toggle_row.addWidget(self.pay_btn_split)
        pay_toggle_row.addStretch()
        pay_layout.addLayout(pay_toggle_row)

        self.pay_stack = QStackedWidget()
        self.pay_stack.setFixedHeight(52)

        # Cash page
        cash_pay_w = QFrame()
        cpl = QHBoxLayout(cash_pay_w)
        cpl.setContentsMargins(0, 4, 0, 4)
        cpl.setSpacing(10)
        cpl.addWidget(QLabel("Cash Received (PKR):"))
        self.pay_cash_spin = QDoubleSpinBox()
        self.pay_cash_spin.setRange(0, 9_999_999)
        self.pay_cash_spin.setDecimals(0)
        self.pay_cash_spin.setMinimumWidth(150)
        self.pay_cash_spin.setValue(float(sv.get("cash_paid") or 0))
        cpl.addWidget(self.pay_cash_spin)
        cpl.addStretch()
        self.pay_stack.addWidget(cash_pay_w)

        # Bank page
        bank_pay_w = QFrame()
        bpl = QHBoxLayout(bank_pay_w)
        bpl.setContentsMargins(0, 4, 0, 4)
        bpl.setSpacing(10)
        bpl.addWidget(QLabel("Bank Account:"))
        self.pay_bank_combo = QComboBox()
        self.pay_bank_combo.setMinimumWidth(200)
        for acc in db_bank_accounts():
            self.pay_bank_combo.addItem(acc["name"], acc["id"])
            if sv.get("bank_account_id") == acc["id"]:
                self.pay_bank_combo.setCurrentIndex(self.pay_bank_combo.count() - 1)
        bpl.addWidget(self.pay_bank_combo)
        bpl.addWidget(QLabel("Ref:"))
        self.pay_bank_ref = QLineEdit(sv.get("bank_ref") or "")
        self.pay_bank_ref.setMinimumWidth(160)
        self.pay_bank_ref.setPlaceholderText("Transaction / cheque ref")
        bpl.addWidget(self.pay_bank_ref)
        bpl.addStretch()
        self.pay_stack.addWidget(bank_pay_w)

        # Split page
        split_pay_w = QFrame()
        spl = QHBoxLayout(split_pay_w)
        spl.setContentsMargins(0, 4, 0, 4)
        spl.setSpacing(10)
        spl.addWidget(QLabel("Cash (PKR):"))
        self.pay_split_cash_spin = QDoubleSpinBox()
        self.pay_split_cash_spin.setRange(0, 9_999_999)
        self.pay_split_cash_spin.setDecimals(0)
        self.pay_split_cash_spin.setMinimumWidth(140)
        self.pay_split_cash_spin.setValue(float(sv.get("cash_paid") or 0))
        spl.addWidget(self.pay_split_cash_spin)
        spl.addWidget(QLabel("Bank Account:"))
        self.pay_split_bank_combo = QComboBox()
        self.pay_split_bank_combo.setMinimumWidth(180)
        for acc in db_bank_accounts():
            self.pay_split_bank_combo.addItem(acc["name"], acc["id"])
            if sv.get("bank_account_id") == acc["id"]:
                self.pay_split_bank_combo.setCurrentIndex(
                    self.pay_split_bank_combo.count() - 1
                )
        spl.addWidget(self.pay_split_bank_combo)
        spl.addWidget(QLabel("Ref:"))
        self.pay_split_bank_ref = QLineEdit(sv.get("bank_ref") or "")
        self.pay_split_bank_ref.setMinimumWidth(140)
        self.pay_split_bank_ref.setPlaceholderText("Transaction / cheque ref")
        spl.addWidget(self.pay_split_bank_ref)
        spl.addStretch()
        self.pay_stack.addWidget(split_pay_w)

        pay_layout.addWidget(self.pay_stack)
        root.addWidget(self.pay_card)

        # Show/hide pay card based on type
        self._set_type(self._sale_type)

        # Set payment stack page
        page_map = {"cash": 0, "bank": 1, "split": 2}
        self.pay_stack.setCurrentIndex(page_map.get(self._payment_mode, 0))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_type(self, t):
        self._sale_type = t
        self.btn_cash.setStyleSheet(
            (BTN_TOGGLE_ON if t == "cash" else BTN_TOGGLE_OFF)
            + "QPushButton{border-radius:5px 0 0 5px;}"
        )
        self.btn_credit.setStyleSheet(
            (BTN_TOGGLE_ON if t == "credit" else BTN_TOGGLE_OFF)
            + "QPushButton{border-radius:0 5px 5px 0; border-left:none;}"
        )
        self.customer_stack.setCurrentIndex(0 if t == "cash" else 1)
        self.pay_card.setVisible(t != "credit")

    def _set_payment_mode(self, mode):
        self._payment_mode = mode
        page_map = {"cash": 0, "bank": 1, "split": 2}
        self.pay_stack.setCurrentIndex(page_map.get(mode, 0))
        for btn, m in [(self.pay_btn_cash, "cash"),
                       (self.pay_btn_bank, "bank"),
                       (self.pay_btn_split, "split")]:
            is_on = (m == mode)
            style = BTN_TOGGLE_ON if is_on else BTN_TOGGLE_OFF
            if m == "cash":
                style += "QPushButton{border-radius:5px 0 0 5px;}"
            elif m == "split":
                style += "QPushButton{border-radius:0 5px 5px 0; border-left:none;}"
            else:
                style += "QPushButton{border-left:none;}"
            btn.setStyleSheet(style)

    def _get_total(self):
        return sum(ln["final_price"] for ln in self._lines) - self.discount_spin.value()

    def _update_total(self):
        self.total_lbl.setText(f"TOTAL: PKR {fmt_pkr(self._get_total())}")

    def _rebuild_lines_table(self):
        self.lines_table.setSortingEnabled(False)
        self.lines_table.setRowCount(0)
        for i, ln in enumerate(self._lines):
            row = self.lines_table.rowCount()
            self.lines_table.insertRow(row)
            self.lines_table.setItem(row, 0, QTableWidgetItem(ln["brand_name"]))
            self.lines_table.setItem(row, 1, QTableWidgetItem(ln["model_name"]))
            self.lines_table.setItem(row, 2, QTableWidgetItem(ln["imei"]))
            ref_item = QTableWidgetItem(fmt_pkr(ln["ref_price"]))
            ref_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.lines_table.setItem(row, 3, ref_item)

            price_edit = QLineEdit(str(int(ln["final_price"])))
            price_edit.setFixedWidth(168)
            price_edit.setStyleSheet("QLineEdit { padding:3px 6px; font-size:10pt; border:1px solid #cbd5e1; border-radius:4px; background:#ffffff; color:#1e293b; }")
            price_edit.setValidator(QDoubleValidator(0, 9_999_999, 0))
            price_edit.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            price_edit.textChanged.connect(lambda text, idx=i: self._on_price_change(idx, text))
            self.lines_table.setCellWidget(row, 4, price_edit)

            btn_rm = QPushButton("Remove")
            btn_rm.setFixedWidth(88)
            btn_rm.setStyleSheet(BTN_DANGER_SMALL)
            btn_rm.clicked.connect(lambda checked, idx=i: self._remove_line(idx))
            self.lines_table.setCellWidget(row, 5, btn_rm)

        self._update_total()

    def _on_price_change(self, idx, text):
        if idx < len(self._lines):
            try:
                self._lines[idx]["final_price"] = float(text) if text.strip() else 0.0
            except ValueError:
                self._lines[idx]["final_price"] = 0.0
            self._update_total()

    def _remove_line(self, idx):
        if idx < len(self._lines):
            imei = self._lines[idx]["imei"]
            ans = QMessageBox.question(
                self, "Remove Line",
                f"Remove IMEI {imei} from this sale?\n"
                "The phone will be returned to stock.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return
            self._lines.pop(idx)
            self._rebuild_lines_table()

    def _add_imei(self):
        dlg = _ImeiPickerDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        r = dlg.picked()
        if not r:
            return
        # Check not already in lines
        for ln in self._lines:
            if ln["imei"] == r["imei"]:
                QMessageBox.warning(self, "Duplicate", f"IMEI {r['imei']} already in this sale.")
                return
        self._lines.append({
            "stock_item_id": r["id"],
            "model_id": r["model_id"],
            "brand_name": r["brand_name"],
            "model_name": r["model_name"],
            "imei": r["imei"],
            "ref_price": float(r.get("reference_price") or 0),
            "final_price": float(r.get("reference_price") or 0),
        })
        self._rebuild_lines_table()
        # Scroll to last row so user sees the new line
        self.lines_table.scrollToBottom()

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save(self):
        if not self._lines:
            QMessageBox.warning(self, "Missing", "Sale must have at least one IMEI line.")
            return

        date_str = self.date_edit.date().toString("dd/MM/yyyy")
        note = self.note_edit.text().strip()
        overall_discount = self.discount_spin.value()

        if self._sale_type == "credit":
            customer_id = self.credit_combo.currentData()
            if not customer_id:
                QMessageBox.warning(self, "Missing", "Select a credit customer.")
                return
            cash_name = cash_contact = None
            pay_method = "credit"
            pay_cash = 0.0
            pay_bank_id = None
            pay_bank_amt = 0.0
            pay_bank_ref = ""
        else:
            customer_id = None
            cash_contact = self.cash_contact.text().strip()
            cash_name = self.cash_name.text().strip()
            if not cash_contact:
                QMessageBox.warning(self, "Missing", "Contact number is required.")
                return
            if not cash_name:
                QMessageBox.warning(self, "Missing", "Customer name is required.")
                return

            if self._payment_mode == "cash":
                pay_method = "cash"
                pay_cash = self.pay_cash_spin.value()
                pay_bank_id = None
                pay_bank_amt = 0.0
                pay_bank_ref = ""
            elif self._payment_mode == "bank":
                pay_bank_id = self.pay_bank_combo.currentData()
                if not pay_bank_id:
                    QMessageBox.warning(self, "Payment", "Select a bank account.")
                    return
                pay_method = "bank"
                pay_cash = 0.0
                pay_bank_amt = self._get_total()
                pay_bank_ref = self.pay_bank_ref.text().strip()
            else:  # split
                pay_bank_id = self.pay_split_bank_combo.currentData()
                if not pay_bank_id:
                    QMessageBox.warning(self, "Payment", "Select a bank account for split.")
                    return
                pay_cash = self.pay_split_cash_spin.value()
                pay_bank_amt = self._get_total() - pay_cash
                if pay_bank_amt < 0:
                    QMessageBox.warning(self, "Payment", "Cash amount exceeds total.")
                    return
                pay_method = "split"
                pay_bank_ref = self.pay_split_bank_ref.text().strip()

        db_lines = [
            (ln["stock_item_id"], ln["model_id"], ln["imei"], ln["ref_price"], ln["final_price"])
            for ln in self._lines
        ]
        try:
            db_update_sale(
                self._sv_id, date_str, self._sale_type, customer_id,
                cash_name, cash_contact, note, overall_discount, db_lines,
                pay_method, pay_cash, pay_bank_id, pay_bank_amt, pay_bank_ref,
            )
        except Exception as ex:
            QMessageBox.critical(self, "Save Error", str(ex))
            return
        QMessageBox.information(self, "Saved", f"Sale {self._sv['sv_number']} updated.")
        self.accept()


# ── Purchase Edit Dialog ───────────────────────────────────────────────────────

class PurchaseEditDialog(QDialog):
    """Full edit dialog for a purchase voucher."""

    def __init__(self, pv_id, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self._pv_id = pv_id
        pv, lines = db_load_purchase_for_edit(pv_id)
        self._pv = pv

        self._lines = [
            {
                "model_id": r["model_id"],
                "brand_name": r["brand_name"],
                "model_name": r["model_name"],
                "imei": r["imei"],
                "purchase_price": float(r["purchase_price"] or 0),
                "stock_status": r["stock_status"],
            }
            for r in lines
        ]

        self.setWindowTitle(f"Edit Purchase — {pv['pv_number']}")
        self.setMinimumWidth(960)
        self.resize(960, 640)
        self.setStyleSheet(FORM_INPUT_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)

        # Title bar
        top = QHBoxLayout()
        lbl = QLabel(f"Edit Purchase — {pv['pv_number']}")
        lbl.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        lbl.setStyleSheet("color:#1e293b;")
        top.addWidget(lbl)
        top.addStretch()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet(BTN_SECONDARY)
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("Save Changes")
        btn_save.setStyleSheet(BTN_PRIMARY)
        btn_save.clicked.connect(self._save)
        top.addWidget(btn_cancel)
        top.addWidget(btn_save)
        root.addLayout(top)

        # Header card
        hdr = QFrame()
        hdr.setStyleSheet(CARD_STYLE)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(14, 10, 14, 10)
        hl.setSpacing(14)

        dc = QVBoxLayout()
        dc.addWidget(QLabel("Date"))
        self.date_edit = QDateEdit()
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setMinimumWidth(130)
        d_parts = pv["date"].split("/")
        self.date_edit.setDate(QDate(int(d_parts[2]), int(d_parts[1]), int(d_parts[0])))
        dc.addWidget(self.date_edit)
        hl.addLayout(dc)

        from purchase import db_suppliers_list
        sc = QVBoxLayout()
        sc.addWidget(QLabel("Supplier *"))
        self.supplier_combo = QComboBox()
        self.supplier_combo.setMinimumWidth(200)
        self.supplier_combo.addItem("— Select Supplier —", None)
        for s in db_suppliers_list():
            self.supplier_combo.addItem(s["name"], s["id"])
            if s["id"] == pv["supplier_id"]:
                self.supplier_combo.setCurrentIndex(self.supplier_combo.count() - 1)
        sc.addWidget(self.supplier_combo)
        hl.addLayout(sc)

        nc = QVBoxLayout()
        nc.addWidget(QLabel("Notes"))
        self.notes_edit = QLineEdit(pv.get("notes") or "")
        self.notes_edit.setMinimumWidth(200)
        nc.addWidget(self.notes_edit)
        hl.addLayout(nc)
        hl.addStretch()
        root.addWidget(hdr)

        # Lines table
        lt = QHBoxLayout()
        lt_lbl = QLabel("Purchase Lines")
        lt_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        lt.addWidget(lt_lbl)
        lt.addStretch()
        btn_add = QPushButton("+ Add Line")
        btn_add.setStyleSheet(BTN_SECONDARY)
        btn_add.clicked.connect(self._add_line)
        lt.addWidget(btn_add)
        root.addLayout(lt)

        self.lines_table = QTableWidget(0, 5)
        self.lines_table.setHorizontalHeaderLabels(
            ["Brand", "Model", "IMEI", "Purchase Price (PKR)", ""]
        )
        self.lines_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.lines_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.lines_table.setAlternatingRowColors(True)
        self.lines_table.verticalHeader().setVisible(False)
        hh = self.lines_table.horizontalHeader()
        hh.setStretchLastSection(False)
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)    # Brand
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Model — fills spare width
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)    # IMEI
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)    # Purchase Price
        hh.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)    # Remove
        self.lines_table.setColumnWidth(0, 90)
        self.lines_table.setColumnWidth(2, 160)
        self.lines_table.setColumnWidth(3, 180)   # Purchase Price — QLineEdit
        self.lines_table.setColumnWidth(4, 90)    # Remove button
        self.lines_table.setStyleSheet(TABLE_STYLE)
        self.lines_table.verticalHeader().setDefaultSectionSize(38)
        self.lines_table.setMinimumHeight(200)
        root.addWidget(self.lines_table)

        # Total
        tot_row = QHBoxLayout()
        tot_row.addStretch()
        self.total_lbl = QLabel("")
        self.total_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.total_lbl.setStyleSheet("color:#1e293b;")
        tot_row.addWidget(self.total_lbl)
        root.addLayout(tot_row)

        self._rebuild_lines_table()

    def _rebuild_lines_table(self):
        self.lines_table.setSortingEnabled(False)
        self.lines_table.setRowCount(0)
        total = 0.0
        for i, ln in enumerate(self._lines):
            row = self.lines_table.rowCount()
            self.lines_table.insertRow(row)
            self.lines_table.setItem(row, 0, QTableWidgetItem(ln["brand_name"]))
            self.lines_table.setItem(row, 1, QTableWidgetItem(ln["model_name"]))
            self.lines_table.setItem(row, 2, QTableWidgetItem(ln["imei"]))

            price_edit = QLineEdit(str(int(ln["purchase_price"])))
            price_edit.setFixedWidth(178)
            price_edit.setStyleSheet("QLineEdit { padding:3px 6px; font-size:10pt; border:1px solid #cbd5e1; border-radius:4px; background:#ffffff; color:#1e293b; }")
            price_edit.setValidator(QDoubleValidator(0, 9_999_999, 0))
            price_edit.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            price_edit.textChanged.connect(lambda text, idx=i: self._on_price_change(idx, text))
            self.lines_table.setCellWidget(row, 3, price_edit)

            is_sold = ln.get("stock_status") == "sold"
            btn_rm = QPushButton("Remove")
            btn_rm.setFixedWidth(88)
            btn_rm.setStyleSheet(BTN_DANGER_SMALL)
            btn_rm.setEnabled(not is_sold)
            if is_sold:
                btn_rm.setToolTip("Cannot remove — already sold")
            btn_rm.clicked.connect(lambda checked, idx=i: self._remove_line(idx))
            self.lines_table.setCellWidget(row, 4, btn_rm)

            total += ln["purchase_price"]

        self.total_lbl.setText(f"TOTAL: PKR {fmt_pkr(total)}")

    def _on_price_change(self, idx, text):
        if idx < len(self._lines):
            try:
                self._lines[idx]["purchase_price"] = float(text) if text.strip() else 0.0
            except ValueError:
                self._lines[idx]["purchase_price"] = 0.0
            total = sum(ln["purchase_price"] for ln in self._lines)
            self.total_lbl.setText(f"TOTAL: PKR {fmt_pkr(total)}")

    def _remove_line(self, idx):
        if idx >= len(self._lines):
            return
        ln = self._lines[idx]
        if ln.get("stock_status") == "sold":
            QMessageBox.warning(self, "Cannot Remove",
                f"IMEI {ln['imei']} has already been sold. Process a Sales Return first.")
            return
        ans = QMessageBox.question(
            self, "Remove Line",
            f"Remove IMEI {ln['imei']} from this purchase?\nThe stock item will be deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        self._lines.pop(idx)
        self._rebuild_lines_table()

    def _add_line(self):
        dlg = _PurchaseLineAddDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        r = dlg.picked()
        if not r:
            return
        for ln in self._lines:
            if ln["imei"] == r["imei"]:
                QMessageBox.warning(self, "Duplicate", f"IMEI {r['imei']} already in this purchase.")
                return
        self._lines.append({
            "model_id": r["model_id"],
            "brand_name": r["brand_name"],
            "model_name": r["model_name"],
            "imei": r["imei"],
            "purchase_price": r["purchase_price"],
            "stock_status": "in_stock",
        })
        self._rebuild_lines_table()

    def _save(self):
        if self.supplier_combo.currentData() is None:
            QMessageBox.warning(self, "Missing", "Select a supplier.")
            return
        if not self._lines:
            QMessageBox.warning(self, "Missing", "Add at least one IMEI line.")
            return

        date_str = self.date_edit.date().toString("dd/MM/yyyy")
        supplier_id = self.supplier_combo.currentData()
        notes = self.notes_edit.text().strip()
        db_lines = [(ln["model_id"], ln["imei"], ln["purchase_price"]) for ln in self._lines]

        try:
            db_update_purchase(self._pv_id, date_str, supplier_id, notes, db_lines)
        except ValueError as ex:
            QMessageBox.warning(self, "Cannot Save", str(ex))
            return
        except Exception as ex:
            QMessageBox.critical(self, "Save Error", str(ex))
            return
        QMessageBox.information(self, "Saved", f"Purchase {self._pv['pv_number']} updated.")
        self.accept()


# ── Payment Edit Dialog (CR / CP) ─────────────────────────────────────────────

class PaymentEditDialog(QDialog):
    """Edit or delete a CR or CP payment record."""

    # Custom result code so the caller knows a delete happened
    DELETED = 2

    def __init__(self, payment_dict, parent=None):
        super().__init__(parent)
        self._pay = payment_dict
        vtype = payment_dict["type"]
        vnum  = payment_dict["voucher_number"]
        self.setWindowTitle(f"Edit Payment — {vnum}")
        self.setMinimumWidth(500)
        self.resize(520, 240)
        self.setStyleSheet(FORM_INPUT_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        lbl = QLabel(f"Edit {vtype} — {vnum}")
        lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        lbl.setStyleSheet("color:#1e293b;")
        layout.addWidget(lbl)

        g = QHBoxLayout()
        g.setSpacing(10)
        lbl_d = QLabel("Date:")
        lbl_d.setFixedWidth(110)
        g.addWidget(lbl_d)
        self.date_edit = QDateEdit()
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setMinimumWidth(140)
        d = payment_dict["date"].split("/")
        self.date_edit.setDate(QDate(int(d[2]), int(d[1]), int(d[0])))
        g.addWidget(self.date_edit)
        g.addStretch()
        layout.addLayout(g)

        g2 = QHBoxLayout()
        g2.setSpacing(10)
        lbl_a = QLabel("Amount (PKR):")
        lbl_a.setFixedWidth(110)
        g2.addWidget(lbl_a)
        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setRange(0.01, 9_999_999)
        self.amount_spin.setDecimals(0)
        self.amount_spin.setSingleStep(1000)
        self.amount_spin.setMinimumWidth(160)
        self.amount_spin.setValue(float(payment_dict["amount"]))
        g2.addWidget(self.amount_spin)
        g2.addStretch()
        layout.addLayout(g2)

        g3 = QHBoxLayout()
        g3.setSpacing(10)
        lbl_n = QLabel("Notes:")
        lbl_n.setFixedWidth(110)
        g3.addWidget(lbl_n)
        self.notes_edit = QLineEdit(payment_dict.get("notes") or "")
        g3.addWidget(self.notes_edit)
        layout.addLayout(g3)

        # ── Button row: Delete (left) | Cancel + Save (right) ────────────────
        btn_row = QHBoxLayout()

        btn_delete = QPushButton("🗑 Delete")
        btn_delete.setStyleSheet("""
            QPushButton { background:#fee2e2; color:#dc2626; border:1px solid #fca5a5;
                border-radius:5px; padding:6px 16px; font-size:10pt; }
            QPushButton:hover { background:#fecaca; }
        """)
        btn_delete.clicked.connect(self._delete)
        btn_row.addWidget(btn_delete)

        btn_row.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet(BTN_SECONDARY)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_save = QPushButton("Save")
        btn_save.setStyleSheet(BTN_PRIMARY)
        btn_save.clicked.connect(self._save)
        btn_row.addWidget(btn_save)

        layout.addLayout(btn_row)

    def _save(self):
        date_str = self.date_edit.date().toString("dd/MM/yyyy")
        amount = self.amount_spin.value()
        notes = self.notes_edit.text().strip()
        try:
            db_update_payment(self._pay["id"], date_str, amount, notes)
        except Exception as ex:
            QMessageBox.critical(self, "Error", str(ex))
            return
        QMessageBox.information(self, "Saved", f"{self._pay['voucher_number']} updated.")
        self.accept()

    def _delete(self):
        vnum = self._pay["voucher_number"]
        amt  = float(self._pay["amount"])
        ans = QMessageBox.warning(
            self, "Delete Payment",
            f"Delete {vnum} (PKR {amt:,.0f})?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        try:
            db_delete_payment(self._pay["id"])
        except Exception as ex:
            QMessageBox.critical(self, "Error", str(ex))
            return
        self.done(PaymentEditDialog.DELETED)


# ── Bank Transaction Edit Dialog ──────────────────────────────────────────────

class BankTransactionEditDialog(QDialog):
    """Edit or delete a bank CP/CR transaction (cash deposit or withdrawal)."""

    DELETED = 2

    def __init__(self, tx_dict, parent=None):
        super().__init__(parent)
        self._tx = tx_dict
        vnum  = tx_dict["voucher_number"]
        vtype = tx_dict["type"]
        direction = "Cash Deposit (CP)" if vtype == "CP" else "Cash Withdrawal (CR)"
        self.setWindowTitle(f"Edit Bank Transaction — {vnum}")
        self.setMinimumWidth(500)
        self.resize(520, 270)
        self.setStyleSheet(FORM_INPUT_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        lbl = QLabel(f"Edit {direction} — {vnum}")
        lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        lbl.setStyleSheet("color:#1e293b;")
        layout.addWidget(lbl)

        bank_row = QHBoxLayout()
        bank_row.setSpacing(10)
        lbl_b = QLabel("Bank Account:")
        lbl_b.setFixedWidth(120)
        bank_row.addWidget(lbl_b)
        bank_name_lbl = QLabel(tx_dict.get("bank_name") or "—")
        bank_name_lbl.setStyleSheet("color:#475569;")
        bank_row.addWidget(bank_name_lbl)
        bank_row.addStretch()
        layout.addLayout(bank_row)

        date_row = QHBoxLayout()
        date_row.setSpacing(10)
        lbl_d = QLabel("Date:")
        lbl_d.setFixedWidth(120)
        date_row.addWidget(lbl_d)
        self.date_edit = QDateEdit()
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setMinimumWidth(140)
        d = tx_dict["date"].split("/")
        self.date_edit.setDate(QDate(int(d[2]), int(d[1]), int(d[0])))
        date_row.addWidget(self.date_edit)
        date_row.addStretch()
        layout.addLayout(date_row)

        amt_row = QHBoxLayout()
        amt_row.setSpacing(10)
        lbl_a = QLabel("Amount (PKR):")
        lbl_a.setFixedWidth(120)
        amt_row.addWidget(lbl_a)
        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setRange(0.01, 9_999_999)
        self.amount_spin.setDecimals(0)
        self.amount_spin.setSingleStep(1000)
        self.amount_spin.setMinimumWidth(160)
        self.amount_spin.setValue(float(tx_dict["amount"]))
        amt_row.addWidget(self.amount_spin)
        amt_row.addStretch()
        layout.addLayout(amt_row)

        notes_row = QHBoxLayout()
        notes_row.setSpacing(10)
        lbl_n = QLabel("Notes:")
        lbl_n.setFixedWidth(120)
        notes_row.addWidget(lbl_n)
        self.notes_edit = QLineEdit(tx_dict.get("notes") or "")
        notes_row.addWidget(self.notes_edit)
        layout.addLayout(notes_row)

        btn_row = QHBoxLayout()
        btn_delete = QPushButton("🗑 Delete")
        btn_delete.setStyleSheet("""
            QPushButton { background:#fee2e2; color:#dc2626; border:1px solid #fca5a5;
                border-radius:5px; padding:6px 16px; font-size:10pt; }
            QPushButton:hover { background:#fecaca; }
        """)
        btn_delete.clicked.connect(self._delete)
        btn_row.addWidget(btn_delete)
        btn_row.addStretch()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet(BTN_SECONDARY)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        btn_save = QPushButton("Save")
        btn_save.setStyleSheet(BTN_PRIMARY)
        btn_save.clicked.connect(self._save)
        btn_row.addWidget(btn_save)
        layout.addLayout(btn_row)

    def _save(self):
        date_str = self.date_edit.date().toString("dd/MM/yyyy")
        amount   = self.amount_spin.value()
        notes    = self.notes_edit.text().strip()
        try:
            db_update_bank_transaction(self._tx["id"], date_str, amount, notes)
        except Exception as ex:
            QMessageBox.critical(self, "Error", str(ex))
            return
        QMessageBox.information(self, "Saved", f"{self._tx['voucher_number']} updated.")
        self.accept()

    def _delete(self):
        vnum = self._tx["voucher_number"]
        amt  = float(self._tx["amount"])
        ans = QMessageBox.warning(
            self, "Delete Transaction",
            f"Delete {vnum} (PKR {amt:,.0f})?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        try:
            db_delete_bank_transaction(self._tx["id"])
        except Exception as ex:
            QMessageBox.critical(self, "Error", str(ex))
            return
        self.done(BankTransactionEditDialog.DELETED)


# ── Journal Entry Edit Dialog (single-party JV) ───────────────────────────────

class JVEditDialog(QDialog):
    """Edit a single-party journal entry (JV from the per-party journal button)."""

    def __init__(self, je_dict, parent=None):
        super().__init__(parent)
        self._je = je_dict
        vnum = je_dict["jv_number"]
        self.setWindowTitle(f"Edit Journal Entry — {vnum}")
        self.setMinimumWidth(500)
        self.resize(520, 280)
        self.setStyleSheet(FORM_INPUT_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        lbl = QLabel(f"Edit JV — {vnum}")
        lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        lbl.setStyleSheet("color:#1e293b;")
        layout.addWidget(lbl)

        g = QHBoxLayout()
        g.setSpacing(10)
        lbl_d = QLabel("Date:")
        lbl_d.setFixedWidth(110)
        g.addWidget(lbl_d)
        self.date_edit = QDateEdit()
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setMinimumWidth(140)
        d = je_dict["date"].split("/")
        self.date_edit.setDate(QDate(int(d[2]), int(d[1]), int(d[0])))
        g.addWidget(self.date_edit)
        g.addStretch()
        layout.addLayout(g)

        g2 = QHBoxLayout()
        g2.setSpacing(10)
        lbl_a = QLabel("Amount (PKR):")
        lbl_a.setFixedWidth(110)
        g2.addWidget(lbl_a)
        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setRange(0.01, 9_999_999)
        self.amount_spin.setDecimals(0)
        self.amount_spin.setSingleStep(1000)
        self.amount_spin.setMinimumWidth(160)
        self.amount_spin.setValue(float(je_dict["amount"]))
        g2.addWidget(self.amount_spin)
        g2.addStretch()
        layout.addLayout(g2)

        g3 = QHBoxLayout()
        g3.setSpacing(10)
        lbl_t = QLabel("Type:")
        lbl_t.setFixedWidth(110)
        g3.addWidget(lbl_t)
        self.type_combo = QComboBox()
        self.type_combo.setMinimumWidth(140)
        self.type_combo.addItem("Debit", "debit")
        self.type_combo.addItem("Credit", "credit")
        if je_dict["type"] == "credit":
            self.type_combo.setCurrentIndex(1)
        g3.addWidget(self.type_combo)
        g3.addStretch()
        layout.addLayout(g3)

        g4 = QHBoxLayout()
        g4.setSpacing(10)
        lbl_n = QLabel("Notes:")
        lbl_n.setFixedWidth(110)
        g4.addWidget(lbl_n)
        self.notes_edit = QLineEdit(je_dict.get("notes") or "")
        g4.addWidget(self.notes_edit)
        layout.addLayout(g4)

        info = QLabel("⚠ This edits the journal entry for this party only.")
        info.setStyleSheet("color:#d97706; font-size:9pt;")
        layout.addWidget(info)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _save(self):
        date_str = self.date_edit.date().toString("dd/MM/yyyy")
        amount = self.amount_spin.value()
        entry_type = self.type_combo.currentData()
        notes = self.notes_edit.text().strip()
        try:
            db_update_journal_entry(self._je["id"], date_str, amount, entry_type, notes)
        except Exception as ex:
            QMessageBox.critical(self, "Error", str(ex))
            return
        QMessageBox.information(self, "Saved", f"{self._je['jv_number']} updated.")
        self.accept()


# ── Simple Return Edit Dialog (date + notes only) ─────────────────────────────

class SimpleReturnEditDialog(QDialog):
    """Edit date and notes on a Sale Return or Purchase Return."""

    def __init__(self, record_type, record_id, number, date_str, notes, parent=None):
        """
        record_type: 'sale_return' | 'purchase_return'
        """
        super().__init__(parent)
        self._type = record_type
        self._id = record_id
        self.setWindowTitle(f"Edit {number}")
        self.setMinimumWidth(480)
        self.resize(500, 240)
        self.setStyleSheet(FORM_INPUT_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        lbl = QLabel(f"Edit — {number}")
        lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        lbl.setStyleSheet("color:#1e293b;")
        layout.addWidget(lbl)

        note = QLabel("Note: Only date and notes can be edited on a return.\n"
                       "To change the returned items, delete and re-enter.")
        note.setStyleSheet("color:#64748b; font-size:9pt;")
        note.setWordWrap(True)
        layout.addWidget(note)

        g = QHBoxLayout()
        g.setSpacing(10)
        lbl_d = QLabel("Date:")
        lbl_d.setFixedWidth(80)
        g.addWidget(lbl_d)
        self.date_edit = QDateEdit()
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setMinimumWidth(140)
        d = date_str.split("/")
        self.date_edit.setDate(QDate(int(d[2]), int(d[1]), int(d[0])))
        g.addWidget(self.date_edit)
        g.addStretch()
        layout.addLayout(g)

        g2 = QHBoxLayout()
        g2.setSpacing(10)
        lbl_n = QLabel("Notes:")
        lbl_n.setFixedWidth(80)
        g2.addWidget(lbl_n)
        self.notes_edit = QLineEdit(notes or "")
        g2.addWidget(self.notes_edit)
        layout.addLayout(g2)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _save(self):
        date_str = self.date_edit.date().toString("dd/MM/yyyy")
        notes = self.notes_edit.text().strip()
        try:
            if self._type == "sale_return":
                db_update_sale_return(self._id, date_str, notes)
            else:
                db_update_purchase_return(self._id, date_str, notes)
        except Exception as ex:
            QMessageBox.critical(self, "Error", str(ex))
            return
        self.accept()
