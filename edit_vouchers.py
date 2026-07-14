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
    QListWidget, QListWidgetItem, QCheckBox, QScrollArea,
)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QFont, QBrush, QColor, QDoubleValidator

from database import get_connection, db_bank_accounts, db_remove_stock_item

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
               b.id AS brand_id, b.name AS brand_name, m.name AS model_name
        FROM purchase_lines pl
        JOIN models m ON m.id = pl.model_id
        JOIN brands b ON b.id = m.brand_id
        LEFT JOIN stock_items si ON si.purchase_line_id = pl.id
        WHERE pl.pv_id=?
        ORDER BY pl.id
    """, (pv_id,)).fetchall()]
    conn.close()
    return pv, lines


def _db_brands_list():
    conn = get_connection()
    rows = [dict(r) for r in conn.execute(
        "SELECT id, name FROM brands ORDER BY name"
    ).fetchall()]
    conn.close()
    return rows


def _db_models_for_brand(brand_id):
    conn = get_connection()
    rows = [dict(r) for r in conn.execute(
        "SELECT id, name FROM models WHERE brand_id=? ORDER BY name", (brand_id,)
    ).fetchall()]
    conn.close()
    return rows


def db_lookup_payment(voucher_number):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM payments WHERE voucher_number=?", (voucher_number,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def db_lookup_payment_by_id(payment_id):
    """Look up a payments row by its own primary key — unambiguous even when
    several parties share the same voucher_number on a multi-line CP/CR."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM payments WHERE id=?", (payment_id,)
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

        # For cash sales, cash_paid must equal the net total
        if payment_method == "cash":
            cash_paid = total_amount

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


def db_update_purchase(pv_id, date_str, supplier_id, notes, lines, customer_as_supplier_id=None):
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
                    db_remove_stock_item(c, old["stock_item_id"])
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
        new_ptype = "supplier" if (supplier_id or customer_as_supplier_id) else "cash"
        if new_ptype == "supplier":
            # A supplier/credit purchase carries no direct payment on the
            # voucher. Stale cash/bank fields left over from a former cash
            # purchase would inflate BOTH cash-in-hand and the supplier's
            # balance, so clear them and drop the bank outflow row (if any).
            c.execute(
                "UPDATE purchase_vouchers SET date=?, supplier_id=?, notes=?, total_amount=?, "
                "customer_as_supplier_id=?, purchase_type=?, payment_method='', "
                "cash_amount=0, bank_amount=0, bank_account_id=NULL, bank_ref='' WHERE id=?",
                (date_str, supplier_id, notes or "", total, customer_as_supplier_id, new_ptype, pv_id),
            )
            c.execute(
                "DELETE FROM bank_transactions WHERE source='cash_purchase' AND "
                "voucher_number=(SELECT pv_number FROM purchase_vouchers WHERE id=?)",
                (pv_id,),
            )
        else:
            # Cash purchase: keep the payment method but re-align the paid
            # amounts with the (possibly changed) voucher total.
            pv_row = c.execute(
                "SELECT pv_number, payment_method, bank_amount FROM purchase_vouchers WHERE id=?",
                (pv_id,),
            ).fetchone()
            pm = (pv_row["payment_method"] or "cash").strip() or "cash"
            if pm == "bank":
                new_cash, new_bank = 0.0, total
            elif pm == "split":
                new_bank = min(float(pv_row["bank_amount"] or 0), total)
                new_cash = total - new_bank
            else:
                new_cash, new_bank = total, 0.0
            c.execute(
                "UPDATE purchase_vouchers SET date=?, supplier_id=?, notes=?, total_amount=?, "
                "customer_as_supplier_id=?, purchase_type=?, cash_amount=?, bank_amount=? "
                "WHERE id=?",
                (date_str, supplier_id, notes or "", total, customer_as_supplier_id,
                 new_ptype, new_cash, new_bank, pv_id),
            )
            if new_bank > 0:
                c.execute(
                    "UPDATE bank_transactions SET amount=?, date=? "
                    "WHERE source='cash_purchase' AND voucher_number=?",
                    (new_bank, date_str, pv_row["pv_number"]),
                )
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()


def db_update_payment(payment_id, date_str, amount, reference,
                      party_type=None, party_id=None):
    """Update a payments record. Ledger recomputes automatically."""
    conn = get_connection()
    if party_type is not None:
        conn.execute(
            "UPDATE payments SET date=?, amount=?, reference=?, "
            "party_type=?, party_id=? WHERE id=?",
            (date_str, amount, reference or "", party_type, party_id, payment_id),
        )
    else:
        conn.execute(
            "UPDATE payments SET date=?, amount=?, reference=? WHERE id=?",
            (date_str, amount, reference or "", payment_id),
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
        self._imei_edit.setMaxLength(15)
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
        if len(imei) != 15 or not imei.isdigit():
            QMessageBox.warning(self, "Invalid IMEI",
                "IMEI must be exactly 15 digits (numbers only).")
            self._imei_edit.setFocus()
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
        self._sv_id = sv_id
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
        btn_delete = QPushButton("🗑 Delete")
        btn_delete.setStyleSheet("""
            QPushButton { background:#fee2e2; color:#dc2626; border:1px solid #fca5a5;
                border-radius:5px; padding:6px 16px; font-size:10pt; }
            QPushButton:hover { background:#fecaca; }
        """)
        btn_delete.clicked.connect(self._delete_and_close)
        top.addWidget(btn_delete)
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
            price_edit.setStyleSheet("QLineEdit { padding:3px 6px; font-size:12pt; font-weight:bold; border:1px solid #cbd5e1; border-radius:4px; background:#ffffff; color:#1e293b; }")
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
            "ref_price": float(r["reference_price"] or 0),
            "final_price": float(r["reference_price"] or 0),
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

    def _delete_and_close(self):
        from database import prompt_and_delete_voucher
        deleted = prompt_and_delete_voucher(
            self, "sale", self._sv_id, self._sv["sv_number"], "Owner"
        )
        if deleted:
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
                "model_id":      r["model_id"],
                "brand_id":      r["brand_id"],
                "brand_name":    r["brand_name"],
                "model_name":    r["model_name"],
                "imei":          r["imei"],
                "purchase_price": float(r["purchase_price"] or 0),
                "stock_status":  r["stock_status"],
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
        btn_delete = QPushButton("🗑 Delete")
        btn_delete.setStyleSheet("""
            QPushButton { background:#fee2e2; color:#dc2626; border:1px solid #fca5a5;
                border-radius:5px; padding:6px 16px; font-size:10pt; }
            QPushButton:hover { background:#fecaca; }
        """)
        btn_delete.clicked.connect(self._delete_and_close)
        top.addWidget(btn_delete)
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

        from purchase import db_suppliers_list, db_credit_customers_for_purchase
        sc = QVBoxLayout()
        sc.addWidget(QLabel("Supplier *"))
        self.supplier_combo = QComboBox()
        self.supplier_combo.setMinimumWidth(200)
        self.supplier_combo.addItem("— Select Supplier —", None)
        for s in db_suppliers_list():
            self.supplier_combo.addItem(s["name"], {"type": "supplier", "id": s["id"]})
            if s["id"] == pv.get("supplier_id"):
                self.supplier_combo.setCurrentIndex(self.supplier_combo.count() - 1)
        _cust_for_pur = list(db_credit_customers_for_purchase())
        if _cust_for_pur:
            _sep_idx = self.supplier_combo.count()
            self.supplier_combo.addItem("── Credit Customers ──", None)
            self.supplier_combo.model().item(_sep_idx).setEnabled(False)
            for cc in _cust_for_pur:
                self.supplier_combo.addItem(cc["name"], {"type": "customer", "id": cc["id"]})
                if pv.get("customer_as_supplier_id") and cc["id"] == pv.get("customer_as_supplier_id"):
                    self.supplier_combo.setCurrentIndex(self.supplier_combo.count() - 1)
        sc.addWidget(self.supplier_combo)
        self.supplier_balance_lbl = QLabel("")
        self.supplier_balance_lbl.setStyleSheet("color:#475569; font-size:9pt;")
        sc.addWidget(self.supplier_balance_lbl)
        self.supplier_combo.currentIndexChanged.connect(self._update_supplier_balance)
        self._update_supplier_balance()
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
        self.lines_table.setColumnWidth(0, 150)
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

    def _populate_model_combo(self, combo, brand_id, current_model_id=None):
        combo.clear()
        for m in _db_models_for_brand(brand_id):
            combo.addItem(m["name"], m["id"])
            if current_model_id and m["id"] == current_model_id:
                combo.setCurrentIndex(combo.count() - 1)

    def _on_brand_changed(self, brand_combo, model_combo):
        brand_id = brand_combo.currentData()
        if brand_id:
            self._populate_model_combo(model_combo, brand_id)

    def _rebuild_lines_table(self):
        self.lines_table.setSortingEnabled(False)
        self.lines_table.setRowCount(0)
        brands = _db_brands_list()
        brand_name_to_id = {b["name"]: b["id"] for b in brands}
        total = 0.0
        for i, ln in enumerate(self._lines):
            row = self.lines_table.rowCount()
            self.lines_table.insertRow(row)

            # Brand combo
            brand_id = ln.get("brand_id") or brand_name_to_id.get(ln.get("brand_name"))
            brand_combo = QComboBox()
            brand_combo.setStyleSheet(
                "QComboBox { background:#ffffff; color:#1e293b; border:1px solid #cbd5e1;"
                " border-radius:4px; padding:3px 6px; font-size:10pt; }"
                "QComboBox QAbstractItemView { background:#ffffff; color:#1e293b;"
                " selection-background-color:#dbeafe; selection-color:#1e40af; }"
            )
            for b in brands:
                brand_combo.addItem(b["name"], b["id"])
                if b["id"] == brand_id:
                    brand_combo.setCurrentIndex(brand_combo.count() - 1)

            # Model combo
            model_combo = QComboBox()
            model_combo.setStyleSheet(
                "QComboBox { background:#ffffff; color:#1e293b; border:1px solid #cbd5e1;"
                " border-radius:4px; padding:3px 6px; font-size:10pt; }"
                "QComboBox QAbstractItemView { background:#ffffff; color:#1e293b;"
                " selection-background-color:#dbeafe; selection-color:#1e40af; }"
            )
            if brand_id:
                self._populate_model_combo(model_combo, brand_id, ln.get("model_id"))

            brand_combo.currentIndexChanged.connect(
                lambda _, bc=brand_combo, mc=model_combo: self._on_brand_changed(bc, mc)
            )

            self.lines_table.setCellWidget(row, 0, brand_combo)
            self.lines_table.setCellWidget(row, 1, model_combo)
            self.lines_table.setItem(row, 2, QTableWidgetItem(ln["imei"]))

            price_edit = QLineEdit(str(int(ln["purchase_price"])))
            price_edit.setFixedWidth(178)
            price_edit.setStyleSheet("QLineEdit { padding:3px 6px; font-size:12pt; font-weight:bold; border:1px solid #cbd5e1; border-radius:4px; background:#ffffff; color:#1e293b; }")
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

    def _update_supplier_balance(self):
        sup_data = self.supplier_combo.currentData()
        if not isinstance(sup_data, dict):
            self.supplier_balance_lbl.setText("")
            return
        if sup_data.get("type") == "supplier":
            from purchase import db_supplier_balance
            bal = db_supplier_balance(sup_data["id"])
            self.supplier_balance_lbl.setText(f"Balance: Rs. {bal:,.0f}")
        else:
            self.supplier_balance_lbl.setText("")

    def _save(self):
        ptype = (self._pv.get("purchase_type") or "").strip().lower()
        is_cash_purchase = ptype == "cash" or not self._pv.get("supplier_id")

        sup_data = self.supplier_combo.currentData()
        user_selected_supplier = isinstance(sup_data, dict)

        # Require a supplier selection only for non-cash purchases where nothing
        # is chosen — cash purchases may be saved without selecting one.
        if not is_cash_purchase and not user_selected_supplier:
            QMessageBox.warning(self, "Missing", "Select a supplier.")
            return
        if not self._lines:
            QMessageBox.warning(self, "Missing", "Add at least one IMEI line.")
            return

        date_str = self.date_edit.date().toString("dd/MM/yyyy")
        if user_selected_supplier:
            # User explicitly picked something — honour it even on cash purchases.
            if sup_data.get("type") == "customer":
                supplier_id = None
                customer_as_supplier_id = sup_data["id"]
            else:
                supplier_id = sup_data["id"]
                customer_as_supplier_id = None
        else:
            # No selection made; keep whatever was originally recorded.
            supplier_id = self._pv.get("supplier_id")
            customer_as_supplier_id = None
        notes = self.notes_edit.text().strip()
        db_lines = []
        for i, ln in enumerate(self._lines):
            model_combo = self.lines_table.cellWidget(i, 1)
            model_id = model_combo.currentData() if model_combo else ln["model_id"]
            db_lines.append((model_id, ln["imei"], ln["purchase_price"]))

        try:
            db_update_purchase(self._pv_id, date_str, supplier_id, notes, db_lines,
                               customer_as_supplier_id=customer_as_supplier_id)
        except ValueError as ex:
            QMessageBox.warning(self, "Cannot Save", str(ex))
            return
        except Exception as ex:
            QMessageBox.critical(self, "Save Error", str(ex))
            return
        QMessageBox.information(self, "Saved", f"Purchase {self._pv['pv_number']} updated.")
        self.accept()

    def _delete_and_close(self):
        from database import prompt_and_delete_voucher
        deleted = prompt_and_delete_voucher(
            self, "purchase", self._pv_id, self._pv["pv_number"], "Owner"
        )
        if deleted:
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
        self.resize(520, 380)
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

        # ── Party Type ──────────────────────────────────────────────────────
        g_pt = QHBoxLayout()
        g_pt.setSpacing(10)
        lbl_pt = QLabel("Party Type:")
        lbl_pt.setFixedWidth(110)
        g_pt.addWidget(lbl_pt)
        self.party_type_combo = QComboBox()
        for _label, _key in [("Supplier", "supplier"), ("Customer", "customer"),
                              ("Expense",  "expense"),  ("Other Party", "other")]:
            self.party_type_combo.addItem(_label, _key)
        cur_ptype = payment_dict.get("party_type", "supplier")
        for i in range(self.party_type_combo.count()):
            if self.party_type_combo.itemData(i) == cur_ptype:
                self.party_type_combo.setCurrentIndex(i)
                break
        self.party_type_combo.setMinimumWidth(160)
        g_pt.addWidget(self.party_type_combo)
        g_pt.addStretch()
        layout.addLayout(g_pt)

        # ── Party Name ──────────────────────────────────────────────────────
        g_pn = QHBoxLayout()
        g_pn.setSpacing(10)
        lbl_pn = QLabel("Party:")
        lbl_pn.setFixedWidth(110)
        g_pn.addWidget(lbl_pn)
        self.party_name_combo = QComboBox()
        self.party_name_combo.setMinimumWidth(240)
        g_pn.addWidget(self.party_name_combo)
        g_pn.addStretch()
        layout.addLayout(g_pn)

        self._refresh_party_names(select_id=payment_dict.get("party_id"))
        self.party_type_combo.currentIndexChanged.connect(
            lambda _: self._refresh_party_names()
        )

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
        lbl_n = QLabel("Reference No.:")
        lbl_n.setFixedWidth(110)
        g3.addWidget(lbl_n)
        self.ref_edit = QLineEdit(payment_dict.get("reference") or "")
        self.ref_edit.setPlaceholderText("Optional")
        g3.addWidget(self.ref_edit)
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

    def _load_party_names(self, party_type: str):
        conn = get_connection()
        if party_type == "supplier":
            rows = conn.execute(
                "SELECT id, name FROM suppliers WHERE id != 0 ORDER BY name"
            ).fetchall()
        elif party_type == "customer":
            rows = conn.execute(
                "SELECT id, name FROM customers ORDER BY name"
            ).fetchall()
        elif party_type == "expense":
            rows = conn.execute(
                "SELECT id, name FROM expense_categories ORDER BY name"
            ).fetchall()
        elif party_type == "other":
            rows = conn.execute(
                "SELECT id, name FROM other_parties ORDER BY name"
            ).fetchall()
        else:
            rows = []
        conn.close()
        return [(r["id"], r["name"]) for r in rows]

    def _refresh_party_names(self, select_id=None):
        ptype   = self.party_type_combo.currentData()
        parties = self._load_party_names(ptype)
        label   = {"supplier": "Supplier", "customer": "Customer",
                   "expense": "Category", "other": "Party"}.get(ptype, "Party")
        self.party_name_combo.blockSignals(True)
        self.party_name_combo.clear()
        self.party_name_combo.addItem(f"— Select {label} —", None)
        for pid, pname in parties:
            self.party_name_combo.addItem(pname, pid)
        if select_id is not None:
            for i in range(self.party_name_combo.count()):
                if self.party_name_combo.itemData(i) == select_id:
                    self.party_name_combo.setCurrentIndex(i)
                    break
        self.party_name_combo.blockSignals(False)

    def _save(self):
        date_str   = self.date_edit.date().toString("dd/MM/yyyy")
        amount     = self.amount_spin.value()
        reference  = self.ref_edit.text().strip()
        party_type = self.party_type_combo.currentData()
        party_id   = self.party_name_combo.currentData()
        if party_id is None:
            QMessageBox.warning(self, "Validation", "Please select a party.")
            return
        try:
            db_update_payment(self._pay["id"], date_str, amount, reference,
                              party_type, party_id)
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

# ── JV multi-line form helpers ────────────────────────────────────────────────

_JV_PARTY_TYPES = [
    ("Supplier",         "supplier"),
    ("Customer",         "customer"),
    ("Bank",             "bank"),
    ("Cash in Hand",     "cash"),
    ("Expense",          "expense"),
    ("Incentive Income", "incentive_income"),
]


def _fill_jv_party_combo(party_combo: QComboBox, type_key: str, selected_id=None):
    """Populate party sub-combo based on selected party type."""
    party_combo.blockSignals(True)
    party_combo.clear()
    if type_key == "cash":
        party_combo.addItem("Cash in Hand", None)
        party_combo.setEnabled(False)
    elif type_key == "bank":
        party_combo.setEnabled(True)
        party_combo.addItem("— Select Bank —", None)
        for a in db_bank_accounts():
            party_combo.addItem(a["name"], a["id"])
            if selected_id is not None and a["id"] == selected_id:
                party_combo.setCurrentIndex(party_combo.count() - 1)
    elif type_key == "supplier":
        party_combo.setEnabled(True)
        party_combo.addItem("— Select Supplier —", None)
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, name FROM suppliers WHERE id != 0 ORDER BY name"
        ).fetchall()
        conn.close()
        for r in rows:
            party_combo.addItem(r["name"], r["id"])
            if selected_id is not None and r["id"] == selected_id:
                party_combo.setCurrentIndex(party_combo.count() - 1)
    elif type_key == "customer":
        party_combo.setEnabled(True)
        party_combo.addItem("— Select Customer —", None)
        conn = get_connection()
        rows = conn.execute(
            "SELECT id, name FROM customers WHERE type='credit' ORDER BY name"
        ).fetchall()
        conn.close()
        for r in rows:
            party_combo.addItem(r["name"], r["id"])
            if selected_id is not None and r["id"] == selected_id:
                party_combo.setCurrentIndex(party_combo.count() - 1)
    elif type_key == "expense":
        party_combo.setEnabled(True)
        party_combo.addItem("— Select Expense —", None)
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT id, name FROM expense_categories ORDER BY name"
            ).fetchall()
        except Exception:
            rows = []
        conn.close()
        for r in rows:
            party_combo.addItem(r["name"], r["id"])
            if selected_id is not None and r["id"] == selected_id:
                party_combo.setCurrentIndex(party_combo.count() - 1)
    elif type_key == "incentive_income":
        party_combo.addItem("Incentive Income", None)
        party_combo.setEnabled(False)
    else:
        party_combo.setEnabled(False)
    party_combo.blockSignals(False)


_JV_TYPE_LABELS = {key: label for label, key in _JV_PARTY_TYPES}


def _jv_balance_text(lines):
    """Return (text, style) for the balance indicator from line dicts."""
    total_dr = sum(float(l["debit"] or 0) for l in lines)
    total_cr = sum(float(l["credit"] or 0) for l in lines)
    if total_dr == 0 and total_cr == 0:
        return "Add journal lines above", "color:#94a3b8;"
    if abs(total_dr - total_cr) < 0.01:
        return (f"✓ Balanced   Dr = Cr = PKR {total_dr:,.0f}",
                "color:#16a34a; font-weight:bold;")
    diff = total_dr - total_cr
    side = "Dr" if diff > 0 else "Cr"
    return (
        f"✗ Not Balanced   Dr {total_dr:,.0f}  Cr {total_cr:,.0f}  "
        f"({side} over by {abs(diff):,.0f})",
        "color:#dc2626; font-weight:bold;"
    )


def _build_jv_form_body(dialog, outer, title_text, prefill_hdr=None, prefill_lines=None):
    """
    Builds the shared JV form body into `outer` (QVBoxLayout) — sales-style
    entry: fill the entry bar at the top, Enter moves through the fields to
    the Add Line button, and the line drops into the grid below. Double-click
    a grid row to load it back into the bar for correction.
    Returns (date_edit, jv_lines, bal_lbl, refresh_fn). jv_lines is a plain
    list of line dicts (party_type, party_id, party_name, debit, credit,
    reference) — mutate it and call refresh_fn to update the grid.
    """
    title_lbl = QLabel(title_text)
    title_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
    title_lbl.setStyleSheet("color:#1e293b;")
    outer.addWidget(title_lbl)

    top = QHBoxLayout()
    top.addWidget(QLabel("Date:"))
    date_edit = QDateEdit(QDate.currentDate())
    date_edit.setDisplayFormat("dd/MM/yyyy")
    date_edit.setCalendarPopup(True)
    date_edit.setMinimumWidth(130)
    if prefill_hdr and prefill_hdr.get("date"):
        d = prefill_hdr["date"].split("/")
        date_edit.setDate(QDate(int(d[2]), int(d[1]), int(d[0])))
    top.addWidget(date_edit)
    top.addStretch()
    outer.addLayout(top)

    # ── Entry bar — one line at a time, like the sales/purchase forms ────────
    entry_card = QFrame()
    entry_card.setStyleSheet(CARD_STYLE)
    ec = QVBoxLayout(entry_card)
    ec.setContentsMargins(12, 8, 12, 10)
    ec.setSpacing(2)

    lbl_row = QHBoxLayout()
    lbl_row.setSpacing(6)
    for txt, w, style in [
        ("Party Type",      120,  "color:#475569; font-weight:bold; font-size:9pt;"),
        ("Party / Account", None, "color:#475569; font-weight:bold; font-size:9pt;"),
        ("Debit (PKR)",     110,  "color:#dc2626; font-weight:bold; font-size:9pt;"),
        ("Credit (PKR)",    110,  "color:#16a34a; font-weight:bold; font-size:9pt;"),
        ("Reference",       150,  "color:#475569; font-weight:bold; font-size:9pt;"),
    ]:
        lbl = QLabel(txt)
        lbl.setStyleSheet(style)
        if w:
            lbl.setFixedWidth(w)
        lbl_row.addWidget(lbl, 0 if w else 1)
    lbl_row.addSpacing(104)          # over the Add Line button
    ec.addLayout(lbl_row)

    fld_row = QHBoxLayout()
    fld_row.setSpacing(6)

    type_combo = QComboBox()
    type_combo.setFixedWidth(120)
    for label, key in _JV_PARTY_TYPES:
        type_combo.addItem(label, key)

    party_combo = QComboBox()
    party_combo.setMinimumWidth(160)

    dr_edit = QLineEdit()
    dr_edit.setPlaceholderText("0")
    dr_edit.setFixedWidth(110)
    dr_edit.setValidator(QDoubleValidator(0, 99_999_999, 0))

    cr_edit = QLineEdit()
    cr_edit.setPlaceholderText("0")
    cr_edit.setFixedWidth(110)
    cr_edit.setValidator(QDoubleValidator(0, 99_999_999, 0))

    ref_edit = QLineEdit()
    ref_edit.setPlaceholderText("Optional")
    ref_edit.setFixedWidth(150)

    btn_add = QPushButton("Add Line  ↵")
    btn_add.setStyleSheet(BTN_PRIMARY)
    btn_add.setFixedWidth(104)

    fld_row.addWidget(type_combo)
    fld_row.addWidget(party_combo, stretch=1)
    fld_row.addWidget(dr_edit)
    fld_row.addWidget(cr_edit)
    fld_row.addWidget(ref_edit)
    fld_row.addWidget(btn_add)
    ec.addLayout(fld_row)
    outer.addWidget(entry_card)

    _fill_jv_party_combo(party_combo, type_combo.currentData())
    type_combo.currentIndexChanged.connect(
        lambda _: _fill_jv_party_combo(party_combo, type_combo.currentData())
    )

    # Dr and Cr are mutually exclusive on a line
    def _on_dr_changed(text):
        if text.strip() and text.strip() != "0":
            cr_edit.blockSignals(True)
            cr_edit.clear()
            cr_edit.setEnabled(False)
            cr_edit.blockSignals(False)
        else:
            cr_edit.setEnabled(True)

    def _on_cr_changed(text):
        if text.strip() and text.strip() != "0":
            dr_edit.blockSignals(True)
            dr_edit.clear()
            dr_edit.setEnabled(False)
            dr_edit.blockSignals(False)
        else:
            dr_edit.setEnabled(True)

    dr_edit.textChanged.connect(_on_dr_changed)
    cr_edit.textChanged.connect(_on_cr_changed)

    # ── Lines grid ────────────────────────────────────────────────────────────
    table = QTableWidget(0, 7)
    table.setHorizontalHeaderLabels(
        ["#", "Party Type", "Party / Account", "Debit (PKR)",
         "Credit (PKR)", "Reference", ""])
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.setStyleSheet(TABLE_STYLE)
    th = table.horizontalHeader()
    th.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
    th.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
    th.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
    th.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
    th.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
    th.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
    th.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
    table.setColumnWidth(0, 35)
    table.setColumnWidth(1, 120)
    table.setColumnWidth(3, 110)
    table.setColumnWidth(4, 110)
    table.setColumnWidth(6, 40)
    table.setMinimumHeight(180)
    outer.addWidget(table, stretch=1)

    jv_lines = []

    bal_lbl = QLabel("Add journal lines above")
    bal_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
    bal_lbl.setStyleSheet("color:#94a3b8;")

    def _refresh():
        table.setRowCount(0)
        for idx, ln in enumerate(jv_lines):
            r = table.rowCount()
            table.insertRow(r)
            table.setItem(r, 0, QTableWidgetItem(str(idx + 1)))
            table.setItem(r, 1, QTableWidgetItem(
                _JV_TYPE_LABELS.get(ln["party_type"], ln["party_type"])))
            table.setItem(r, 2, QTableWidgetItem(ln.get("party_name") or ""))
            dr_item = QTableWidgetItem(f"{ln['debit']:,.0f}" if ln["debit"] else "")
            dr_item.setForeground(QColor("#dc2626"))
            table.setItem(r, 3, dr_item)
            cr_item = QTableWidgetItem(f"{ln['credit']:,.0f}" if ln["credit"] else "")
            cr_item.setForeground(QColor("#16a34a"))
            table.setItem(r, 4, cr_item)
            table.setItem(r, 5, QTableWidgetItem(ln.get("reference") or ""))
            btn_rm = QPushButton("✕")
            btn_rm.setStyleSheet(
                "QPushButton { background:#fee2e2; color:#dc2626; border:none; "
                "border-radius:4px; } QPushButton:hover { background:#fecaca; }")
            btn_rm.clicked.connect(lambda _, i=idx: _remove_line(i))
            table.setCellWidget(r, 6, btn_rm)
        txt, style = _jv_balance_text(jv_lines)
        bal_lbl.setText(txt)
        bal_lbl.setStyleSheet(style)

    def _remove_line(idx):
        if 0 <= idx < len(jv_lines):
            jv_lines.pop(idx)
            _refresh()

    def _reset_entry():
        party_combo.setCurrentIndex(0)
        dr_edit.blockSignals(True)
        cr_edit.blockSignals(True)
        dr_edit.clear()
        cr_edit.clear()
        dr_edit.setEnabled(True)
        cr_edit.setEnabled(True)
        dr_edit.blockSignals(False)
        cr_edit.blockSignals(False)
        ref_edit.clear()

    _no_party_types = ("cash", "incentive_income")

    def _add_line():
        type_key = type_combo.currentData()
        party_id = party_combo.currentData()
        try:
            dr = float(dr_edit.text() or 0)
        except ValueError:
            dr = 0.0
        try:
            cr = float(cr_edit.text() or 0)
        except ValueError:
            cr = 0.0
        if type_key not in _no_party_types and party_id is None:
            QMessageBox.warning(dialog, "Missing", "Select a party / account first.")
            party_combo.setFocus()
            return
        if dr == 0 and cr == 0:
            QMessageBox.warning(dialog, "Missing",
                                "Enter either a Debit or a Credit amount.")
            dr_edit.setFocus()
            return
        jv_lines.append({
            "party_type": type_key,
            "party_id": None if type_key in _no_party_types else party_id,
            "party_name": party_combo.currentText(),
            "debit": dr,
            "credit": cr,
            "reference": ref_edit.text().strip(),
        })
        _refresh()
        _reset_entry()
        party_combo.setFocus()

    btn_add.clicked.connect(_add_line)

    def _edit_line(row, _col):
        if not (0 <= row < len(jv_lines)):
            return
        ln = jv_lines.pop(row)
        _refresh()
        for i in range(type_combo.count()):
            if type_combo.itemData(i) == ln["party_type"]:
                type_combo.setCurrentIndex(i)
                break
        _fill_jv_party_combo(party_combo, ln["party_type"], ln["party_id"])
        dr_edit.setText(str(int(ln["debit"])) if ln["debit"] else "")
        cr_edit.setText(str(int(ln["credit"])) if ln["credit"] else "")
        ref_edit.setText(ln.get("reference") or "")
        (cr_edit if ln["credit"] else dr_edit).setFocus()

    table.cellDoubleClicked.connect(_edit_line)

    outer.addWidget(bal_lbl)

    hint_lbl = QLabel(
        "Double-click a line to edit it.   |   "
        "Supplier: Debit = reduces balance (you pay them) ↓, Credit = increases balance (you owe more) ↑   |   "
        "Customer: Debit = increases balance (they owe more) ↑, Credit = reduces balance (they pay you) ↓   |   "
        "Bank: Debit = money IN ↑, Credit = money OUT ↓"
    )
    hint_lbl.setStyleSheet("color:#94a3b8; font-size:9pt;")
    hint_lbl.setWordWrap(True)
    outer.addWidget(hint_lbl)

    if prefill_lines:
        for ln in prefill_lines:
            jv_lines.append({
                "party_type": ln["party_type"],
                "party_id": ln["party_id"],
                "party_name": ln.get("party_name") or "",
                "debit": float(ln["debit"] or 0),
                "credit": float(ln["credit"] or 0),
                "reference": ln.get("reference") or "",
            })
    _refresh()

    return date_edit, jv_lines, bal_lbl, _refresh


class JVFormDialog(QDialog):
    """Create a new multi-line Journal Voucher."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Journal Voucher")
        self.setMinimumWidth(720)
        self.setMinimumHeight(500)
        self.setStyleSheet(FORM_INPUT_STYLE)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(10)

        self._date_edit, self._jv_lines, self._bal_lbl, _ = \
            _build_jv_form_body(self, outer, "New Journal Voucher")

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        outer.addWidget(btns)

    def _save(self):
        if not self._jv_lines:
            QMessageBox.warning(self, "Validation",
                                "Add at least one journal line first.")
            return
        date_str = self._date_edit.date().toString("dd/MM/yyyy")
        try:
            from database import db_save_journal_voucher
            jv_num = db_save_journal_voucher(date_str, "", list(self._jv_lines))
        except ValueError as ex:
            QMessageBox.warning(self, "Validation", str(ex))
            return
        except Exception as ex:
            QMessageBox.critical(self, "Error", str(ex))
            return
        QMessageBox.information(self, "Saved", f"Journal Voucher {jv_num} saved.")
        self.accept()


class JVEditDialog(QDialog):
    """
    View / edit a journal voucher.
    is_legacy=True  → read-only summary (journal_entries row, cannot be edited).
    is_legacy=False → full editable form backed by journal_vouchers.
    """
    DELETED = 2

    def __init__(self, jv_id, is_legacy, jv_number, parent=None):
        super().__init__(parent)
        self._jv_id = jv_id
        self._is_legacy = is_legacy
        self._jv_number = jv_number
        self.setStyleSheet(FORM_INPUT_STYLE)
        if is_legacy:
            self._build_legacy_ui()
        else:
            self._build_edit_ui()

    def _build_legacy_ui(self):
        self.setWindowTitle(f"Journal Voucher — {self._jv_number} (Legacy)")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)
        lbl = QLabel(f"Journal Voucher — {self._jv_number}")
        lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        lbl.setStyleSheet("color:#1e293b;")
        layout.addWidget(lbl)
        info = QLabel(
            "This is a legacy journal entry recorded before the multi-line JV system.\n"
            "It is read-only and cannot be edited or deleted.\n\n"
            "Legacy entries remain for historical accuracy."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            "color:#92400e; background:#fef9c3; padding:12px; border-radius:6px;"
        )
        layout.addWidget(info)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _build_edit_ui(self):
        self.setWindowTitle(f"Edit Journal Voucher — {self._jv_number}")
        self.setMinimumWidth(720)
        self.setMinimumHeight(500)

        from database import db_load_journal_voucher
        hdr, lines = db_load_journal_voucher(self._jv_id)
        if not hdr:
            layout = QVBoxLayout(self)
            layout.addWidget(QLabel("Journal voucher not found."))
            btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            btns.rejected.connect(self.reject)
            layout.addWidget(btns)
            return

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(10)

        self._date_edit, self._jv_lines, self._bal_lbl, _ = \
            _build_jv_form_body(
                self, outer,
                f"Edit — {self._jv_number}",
                prefill_hdr=hdr,
                prefill_lines=lines,
            )

        btn_row = QHBoxLayout()
        btn_delete = QPushButton("Delete JV")
        btn_delete.setStyleSheet("""
            QPushButton { background:#fee2e2; color:#dc2626; border:1px solid #fca5a5;
                border-radius:5px; padding:6px 14px; }
            QPushButton:hover { background:#fecaca; }
        """)
        btn_delete.clicked.connect(self._delete)
        btn_row.addWidget(btn_delete)
        btn_row.addStretch()
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        btn_row.addWidget(btns)
        outer.addLayout(btn_row)

    def _save(self):
        if not self._jv_lines:
            QMessageBox.warning(self, "Validation",
                                "Add at least one journal line first.")
            return
        date_str = self._date_edit.date().toString("dd/MM/yyyy")
        try:
            from database import db_update_journal_voucher
            db_update_journal_voucher(self._jv_id, date_str, "",
                                      list(self._jv_lines))
        except ValueError as ex:
            QMessageBox.warning(self, "Validation", str(ex))
            return
        except Exception as ex:
            QMessageBox.critical(self, "Error", str(ex))
            return
        QMessageBox.information(self, "Saved", f"{self._jv_number} updated.")
        self.accept()

    def _delete(self):
        reply = QMessageBox.question(
            self, "Delete Journal Voucher",
            f"Delete {self._jv_number}?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            from database import db_delete_journal_voucher
            db_delete_journal_voucher(self._jv_id)
        except Exception as ex:
            QMessageBox.critical(self, "Error", str(ex))
            return
        self.done(self.DELETED)


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
        self._number = number
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

        btn_row = QHBoxLayout()
        btn_delete = QPushButton("🗑 Delete")
        btn_delete.setStyleSheet("""
            QPushButton { background:#fee2e2; color:#dc2626; border:1px solid #fca5a5;
                border-radius:5px; padding:6px 14px; }
            QPushButton:hover { background:#fecaca; }
        """)
        btn_delete.clicked.connect(self._delete_and_close)
        btn_row.addWidget(btn_delete)
        btn_row.addStretch()
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        btn_row.addWidget(btns)
        layout.addLayout(btn_row)

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

    def _delete_and_close(self):
        from database import prompt_and_delete_voucher
        deleted = prompt_and_delete_voucher(
            self, self._type, self._id, self._number, "Owner"
        )
        if deleted:
            self.accept()
