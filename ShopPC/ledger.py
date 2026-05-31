import sqlite3
from collections import Counter
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QComboBox, QDateEdit,
    QDialog, QFormLayout, QDialogButtonBox, QDoubleSpinBox,
    QLineEdit, QMessageBox, QHeaderView, QAbstractItemView,
    QFrame, QButtonGroup, QRadioButton,
)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QFont, QColor, QBrush

from database import (
    get_connection, db_bank_accounts,
    db_save_bank_cp_cr, db_save_double_entry_jv,
)

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
BTN_PRIMARY = """
    QPushButton { background:#2563eb; color:white; border:none;
        border-radius:5px; padding:6px 16px; font-size:10pt; }
    QPushButton:hover { background:#1d4ed8; }
    QPushButton:disabled { background:#93c5fd; }
"""
BTN_GREEN = """
    QPushButton { background:#16a34a; color:white; border:none;
        border-radius:5px; padding:6px 16px; font-size:10pt; }
    QPushButton:hover { background:#15803d; }
    QPushButton:disabled { background:#86efac; }
"""
BTN_TOGGLE_ON = """
    QPushButton { background:#2563eb; color:white; border:none;
        padding:7px 20px; font-size:10pt; font-weight:bold; }
"""
BTN_TOGGLE_OFF = """
    QPushButton { background:#f1f5f9; color:#64748b;
        border:1px solid #cbd5e1; padding:7px 20px; font-size:10pt; }
    QPushButton:hover { background:#e2e8f0; color:#334155; }
"""
CARD_STYLE = "background:#ffffff; border:1px solid #e2e8f0; border-radius:8px; color:#1e293b;"


def fmt_pkr(val):
    if val is None:
        return "0"
    return f"{float(val):,.0f}"


def _to_iso(ddmmyyyy: str) -> str:
    try:
        d, m, y = ddmmyyyy.split("/")
        return f"{y}-{m}-{d}"
    except Exception:
        return "0000-00-00"


# ── DB helpers ────────────────────────────────────────────────────────────────

def db_parties_list(party_type: str):
    """id=0 is the system 'Cash Purchase' supplier — excluded from all party lists."""
    conn = get_connection()
    if party_type == "supplier":
        rows = conn.execute(
            "SELECT id, name FROM suppliers WHERE id != 0 ORDER BY name"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, name FROM customers WHERE type='credit' ORDER BY name"
        ).fetchall()
    conn.close()
    return rows


def db_party_info(party_type: str, party_id: int):
    conn = get_connection()
    table = "suppliers" if party_type == "supplier" else "customers"
    row = conn.execute(
        f"SELECT name, contact, opening_balance FROM {table} WHERE id=?", (party_id,)
    ).fetchone()
    conn.close()
    return row


def _payment_default_desc(ptype: str, party_type: str) -> str:
    """Return a sensible ledger description for a payment when no notes were entered."""
    if ptype == "CP":
        return "Payment to Supplier" if party_type == "supplier" else "Refund to Customer"
    else:  # CR
        return "Payment from Customer" if party_type == "customer" else "Supplier Refund"


def db_ledger_entries(party_type: str, party_id: int, from_iso=None, to_iso=None):
    """
    Returns a list of dicts: date, voucher, description, dr, cr, balance.
    First entry is always Opening Balance or Balance B/F.
    """
    conn = get_connection()

    # Opening balance
    table = "suppliers" if party_type == "supplier" else "customers"
    ob_row = conn.execute(
        f"SELECT opening_balance FROM {table} WHERE id=?", (party_id,)
    ).fetchone()
    ob = float(ob_row["opening_balance"] or 0) if ob_row else 0.0

    raw = []

    if party_type == "supplier":
        for r in conn.execute(
            "SELECT id, date, pv_number, total_amount "
            "FROM purchase_vouchers WHERE supplier_id=?",
            (party_id,),
        ):
            lines = conn.execute("""
                SELECT m.name AS model, pl.purchase_price
                FROM purchase_lines pl
                JOIN models m ON m.id = pl.model_id
                WHERE pl.pv_id=?
                ORDER BY pl.id
            """, (r[0],)).fetchall()
            counts = Counter((ln["model"], int(ln["purchase_price"])) for ln in lines)
            parts = [f"{qty}x{model}@{price}" for (model, price), qty in counts.items()]
            desc = ", ".join(parts) if parts else "Purchase"
            raw.append({"date": r[1], "voucher": r[2], "desc": desc,
                        "dr": float(r[3] or 0), "cr": 0.0})

        # Supplier payment directions — DO NOT CHANGE:
        #   CP (you pay supplier)          → CREDIT  (reduces what you owe them)
        #   CR (supplier pays / refunds you) → DEBIT  (increases the DR side of their account)
        for r in conn.execute(
            "SELECT date, voucher_number, notes, amount, type "
            "FROM payments WHERE party_type='supplier' AND party_id=?",
            (party_id,),
        ):
            desc = r[2] if r[2] else _payment_default_desc(r[4], "supplier")
            amt  = float(r[3] or 0)
            if r[4] == "CR":          # cash received FROM supplier → DEBIT
                raw.append({"date": r[0], "voucher": r[1], "desc": desc,
                            "dr": amt, "cr": 0.0})
            else:                     # CP cash paid TO supplier → CREDIT
                raw.append({"date": r[0], "voucher": r[1], "desc": desc,
                            "dr": 0.0, "cr": amt})

    else:  # customer
        for r in conn.execute(
            "SELECT sv.id, sv.date, sv.sv_number, sv.total_amount "
            "FROM sale_vouchers sv WHERE sv.customer_id=? AND sv.type='credit'",
            (party_id,),
        ):
            lines = conn.execute("""
                SELECT m.name AS model, sl.final_price
                FROM sale_lines sl
                JOIN models m ON m.id = sl.model_id
                WHERE sl.sv_id=?
                ORDER BY sl.id
            """, (r[0],)).fetchall()
            counts = Counter((ln["model"], int(ln["final_price"])) for ln in lines)
            parts = [f"{qty}x{model}@{price}" for (model, price), qty in counts.items()]
            desc = ", ".join(parts) if parts else "Sale on Credit"
            raw.append({"date": r[1], "voucher": r[2], "desc": desc,
                        "dr": float(r[3] or 0), "cr": 0.0})

        # Customer payment directions — DO NOT CHANGE:
        #   CR (cash received FROM customer)  → CREDIT  (reduces what they owe you)
        #   CP (cash paid TO customer)        → DEBIT   (increases what they owe you)
        for r in conn.execute(
            "SELECT date, voucher_number, notes, amount, type "
            "FROM payments WHERE party_type='customer' AND party_id=?",
            (party_id,),
        ):
            desc = r[2] if r[2] else _payment_default_desc(r[4], "customer")
            amt  = float(r[3] or 0)
            if r[4] == "CP":      # cash paid TO customer → DEBIT
                raw.append({"date": r[0], "voucher": r[1], "desc": desc,
                            "dr": amt, "cr": 0.0})
            else:                 # CR cash received FROM customer → CREDIT
                raw.append({"date": r[0], "voucher": r[1], "desc": desc,
                            "dr": 0.0, "cr": amt})

    # Journal entries apply to both
    for r in conn.execute(
        "SELECT date, jv_number, COALESCE(notes,'Journal Entry'), type, amount "
        "FROM journal_entries WHERE party_type=? AND party_id=?",
        (party_type, party_id),
    ):
        dr = float(r[4] or 0) if r[3] == "debit" else 0.0
        cr = float(r[4] or 0) if r[3] == "credit" else 0.0
        raw.append({"date": r[0], "voucher": r[1], "desc": r[2], "dr": dr, "cr": cr})

    conn.close()

    # Sort by ISO date then voucher number
    raw.sort(key=lambda e: (_to_iso(e["date"]), e["voucher"]))

    # Build final list with running balance
    if from_iso or to_iso:
        before = [e for e in raw
                  if from_iso and _to_iso(e["date"]) < from_iso]
        in_range = [e for e in raw
                    if (not from_iso or _to_iso(e["date"]) >= from_iso)
                    and (not to_iso or _to_iso(e["date"]) <= to_iso)]

        bf = ob + sum(e["dr"] - e["cr"] for e in before)
        result = [{"date": "", "voucher": "", "desc": "Balance B/F",
                   "dr": 0.0, "cr": 0.0, "balance": bf, "is_header": True}]
        running = bf
        for e in in_range:
            running += e["dr"] - e["cr"]
            result.append({**e, "balance": running, "is_header": False})
    else:
        result = [{"date": "", "voucher": "OB", "desc": "Opening Balance",
                   "dr": ob if ob >= 0 else 0.0,
                   "cr": 0.0 if ob >= 0 else -ob,
                   "balance": ob, "is_header": True}]
        running = ob
        for e in raw:
            running += e["dr"] - e["cr"]
            result.append({**e, "balance": running, "is_header": False})

    return result


def db_save_payment(party_type, party_id, date_str, amount, ptype, notes):
    """ptype = 'CP' (to supplier) or 'CR' (from customer)."""
    counter_key = "last_cp_number" if ptype == "CP" else "last_cr_number"
    conn = get_connection()
    try:
        c = conn.cursor()
        row = c.execute(
            "SELECT value FROM settings WHERE key=?", (counter_key,)
        ).fetchone()
        n = int(row["value"]) + 1 if row else 1
        c.execute("UPDATE settings SET value=? WHERE key=?", (str(n), counter_key))
        voucher_number = f"{ptype}-{n:04d}"
        c.execute(
            "INSERT INTO payments (voucher_number, party_type, party_id, date, amount, type, notes) "
            "VALUES (?,?,?,?,?,?,?)",
            (voucher_number, party_type, party_id, date_str, amount, ptype, notes or ""),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()
    return voucher_number


def db_save_journal(party_type, party_id, date_str, amount, entry_type, notes):
    """entry_type = 'debit' or 'credit'."""
    conn = get_connection()
    try:
        c = conn.cursor()
        row = c.execute(
            "SELECT value FROM settings WHERE key='last_jv_number'"
        ).fetchone()
        n = int(row["value"]) + 1 if row else 1
        c.execute("UPDATE settings SET value=? WHERE key='last_jv_number'", (str(n),))
        jv_number = f"JV-{n:04d}"
        c.execute(
            "INSERT INTO journal_entries "
            "(jv_number, party_type, party_id, date, amount, type, notes) "
            "VALUES (?,?,?,?,?,?,?)",
            (jv_number, party_type, party_id, date_str, amount, entry_type, notes or ""),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()
    return jv_number


def db_bank_ledger_entries(bank_account_id: int, from_iso=None, to_iso=None):
    """
    Running statement for one bank account.
    Debit column = money IN (balance ↑).  Credit column = money OUT (balance ↓).
    Sources:
      - opening_balance from bank_accounts
      - bank_amount on sale_vouchers  (customer paid via this bank)
      - bank_transactions CP  (money in: cash deposit OR JV Dr Bank)
      - bank_transactions CR  (money out: cash withdrawal OR JV Cr Bank)
    """
    conn = get_connection()
    ob_row = conn.execute(
        "SELECT opening_balance FROM bank_accounts WHERE id=?", (bank_account_id,)
    ).fetchone()
    ob = float(ob_row["opening_balance"] or 0) if ob_row else 0.0

    raw = []

    # Sale payments via bank
    for r in conn.execute("""
        SELECT sv.date, sv.sv_number,
               COALESCE(c.name, sv.cash_customer_name, 'Customer') AS cust,
               sv.bank_amount
        FROM sale_vouchers sv
        LEFT JOIN customers c ON c.id = sv.customer_id
        WHERE sv.bank_account_id=? AND sv.bank_amount > 0
    """, (bank_account_id,)):
        raw.append({"date": r["date"], "voucher": r["sv_number"],
                    "desc": f"Sale — {r['cust']}",
                    "dr": float(r["bank_amount"]), "cr": 0.0})

    # Bank transactions (CP=in, CR=out)
    for r in conn.execute("""
        SELECT date, voucher_number, type, amount, notes, source
        FROM bank_transactions WHERE bank_account_id=?
    """, (bank_account_id,)):
        source = r["source"] or "cash_transfer"
        if r["notes"] and r["notes"].strip():
            desc = r["notes"]
        elif r["type"] == "CP":
            desc = "Cash Deposit" if source == "cash_transfer" else "Journal Entry"
        else:
            desc = "Cash Withdrawal" if source == "cash_transfer" else "Journal Entry"
        if r["type"] == "CP":
            raw.append({"date": r["date"], "voucher": r["voucher_number"],
                        "desc": desc, "dr": float(r["amount"]), "cr": 0.0})
        else:
            raw.append({"date": r["date"], "voucher": r["voucher_number"],
                        "desc": desc, "dr": 0.0, "cr": float(r["amount"])})

    conn.close()

    raw.sort(key=lambda e: (_to_iso(e["date"]), e["voucher"]))

    if from_iso or to_iso:
        before = [e for e in raw if from_iso and _to_iso(e["date"]) < from_iso]
        in_range = [e for e in raw
                    if (not from_iso or _to_iso(e["date"]) >= from_iso)
                    and (not to_iso or _to_iso(e["date"]) <= to_iso)]
        bf = ob + sum(e["dr"] - e["cr"] for e in before)
        result = [{"date": "", "voucher": "", "desc": "Balance B/F",
                   "dr": 0.0, "cr": 0.0, "balance": bf, "is_header": True}]
        running = bf
        for e in in_range:
            running += e["dr"] - e["cr"]
            result.append({**e, "balance": running, "is_header": False})
    else:
        result = [{"date": "", "voucher": "OB", "desc": "Opening Balance",
                   "dr": ob if ob >= 0 else 0.0,
                   "cr": 0.0 if ob >= 0 else -ob,
                   "balance": ob, "is_header": True}]
        running = ob
        for e in raw:
            running += e["dr"] - e["cr"]
            result.append({**e, "balance": running, "is_header": False})

    return result


# ── Payment Dialog ────────────────────────────────────────────────────────────

class PaymentDialog(QDialog):
    def __init__(self, party_type, party_name, parent=None):
        super().__init__(parent)
        ptype = "CP" if party_type == "supplier" else "CR"
        if party_type == "supplier":
            verb = f"Payment to {party_name}"
        else:
            verb = f"Payment from {party_name}"
        self.setWindowTitle(verb)
        self.setFixedWidth(380)
        self._ptype = ptype

        form = QFormLayout(self)
        form.setSpacing(12)
        form.setContentsMargins(20, 20, 20, 20)

        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        self.date_edit.setCalendarPopup(True)
        form.addRow("Date:", self.date_edit)

        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setRange(0.01, 99_999_999)
        self.amount_spin.setDecimals(0)
        self.amount_spin.setSingleStep(1000)
        self.amount_spin.setGroupSeparatorShown(True)
        self.amount_spin.setPrefix("PKR ")
        form.addRow("Amount:", self.amount_spin)

        self.notes_edit = QLineEdit()
        self.notes_edit.setPlaceholderText("Optional notes")
        form.addRow("Notes:", self.notes_edit)

        note = QLabel(
            f"Voucher type: {ptype}  •  Will be numbered automatically"
        )
        note.setStyleSheet("color:#64748b; font-size:9pt;")
        form.addRow("", note)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def _accept(self):
        if self.amount_spin.value() <= 0:
            QMessageBox.warning(self, "Validation", "Amount must be greater than zero.")
            return
        self.accept()

    def get_data(self):
        return (
            self.date_edit.date().toString("dd/MM/yyyy"),
            self.amount_spin.value(),
            self._ptype,
            self.notes_edit.text().strip(),
        )


# ── Journal Dialog ────────────────────────────────────────────────────────────

class JournalDialog(QDialog):
    def __init__(self, party_type, party_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Journal Entry — {party_name}")
        self.setFixedWidth(400)

        form = QFormLayout(self)
        form.setSpacing(12)
        form.setContentsMargins(20, 20, 20, 20)

        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        self.date_edit.setCalendarPopup(True)
        form.addRow("Date:", self.date_edit)

        # Direction radio buttons
        if party_type == "supplier":
            dr_label = "Debit (increases what you owe)"
            cr_label = "Credit (e.g. rebate — reduces what you owe)"
        else:
            dr_label = "Debit (increases what they owe)"
            cr_label = "Credit (reduces what they owe)"

        self.radio_dr = QRadioButton(dr_label)
        self.radio_cr = QRadioButton(cr_label)
        self.radio_cr.setChecked(True)
        form.addRow("Direction:", self.radio_dr)
        form.addRow("", self.radio_cr)

        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setRange(0.01, 99_999_999)
        self.amount_spin.setDecimals(0)
        self.amount_spin.setSingleStep(500)
        self.amount_spin.setGroupSeparatorShown(True)
        self.amount_spin.setPrefix("PKR ")
        form.addRow("Amount:", self.amount_spin)

        self.notes_edit = QLineEdit()
        self.notes_edit.setPlaceholderText("Reason / description")
        form.addRow("Notes:", self.notes_edit)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def _accept(self):
        if self.amount_spin.value() <= 0:
            QMessageBox.warning(self, "Validation", "Amount must be greater than zero.")
            return
        self.accept()

    def get_data(self):
        entry_type = "debit" if self.radio_dr.isChecked() else "credit"
        return (
            self.date_edit.date().toString("dd/MM/yyyy"),
            self.amount_spin.value(),
            entry_type,
            self.notes_edit.text().strip(),
        )


# ── Standalone Voucher Dialogs ────────────────────────────────────────────────

def _style_toggle(btn, active: bool, pos: str):
    """Apply toggle style to a pill button. pos: 'left'|'mid'|'right'"""
    if pos == "left":
        radius = "border-radius: 5px 0 0 5px;"
        border = ""
    elif pos == "right":
        radius = "border-radius: 0 5px 5px 0; border-left: none;"
        border = ""
    else:
        radius = "border-radius: 0; border-left: none;"
        border = ""
    base = BTN_TOGGLE_ON if active else BTN_TOGGLE_OFF
    btn.setStyleSheet(base + f"QPushButton {{ {radius} {border} }}")


def _make_three_way_toggle(label_a, label_b, label_c):
    """Returns (layout, btn_a, btn_b, btn_c) with btn_a active."""
    row = QHBoxLayout()
    row.setSpacing(0)
    btn_a = QPushButton(label_a)
    btn_a.setFixedHeight(30)
    btn_b = QPushButton(label_b)
    btn_b.setFixedHeight(30)
    btn_c = QPushButton(label_c)
    btn_c.setFixedHeight(30)
    _style_toggle(btn_a, True,  "left")
    _style_toggle(btn_b, False, "mid")
    _style_toggle(btn_c, False, "right")
    row.addWidget(btn_a)
    row.addWidget(btn_b)
    row.addWidget(btn_c)
    row.addStretch()
    return row, btn_a, btn_b, btn_c


class CashReceiptDialog(QDialog):
    """
    CR voucher — cash / bank coming IN.
    Supplier:  refund received from supplier  (reduces what they owe you)
    Customer:  payment received from customer (reduces what they owe you)
    Bank:      cash withdrawal from bank      (Bank ↓, Cash in Hand ↑)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cash Receipt Voucher (CR)")
        self.setMinimumWidth(460)
        self._party_type = "supplier"

        form = QFormLayout(self)
        form.setSpacing(12)
        form.setContentsMargins(20, 20, 20, 20)

        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        self.date_edit.setCalendarPopup(True)
        form.addRow("Date:", self.date_edit)

        type_row, self._btn_sup, self._btn_cust, self._btn_bank = _make_three_way_toggle(
            "Supplier", "Customer", "Bank"
        )
        self._btn_sup.clicked.connect(lambda: self._set_party_type("supplier"))
        self._btn_cust.clicked.connect(lambda: self._set_party_type("customer"))
        self._btn_bank.clicked.connect(lambda: self._set_party_type("bank"))
        form.addRow("Party Type:", type_row)

        self._hint_lbl = QLabel("")
        self._hint_lbl.setStyleSheet("color:#64748b; font-size:9pt;")
        form.addRow("", self._hint_lbl)

        # Party combo (hidden for Bank)
        self.party_combo = QComboBox()
        self.party_combo.setMinimumWidth(220)
        self._party_lbl = QLabel("Party:")
        form.addRow(self._party_lbl, self.party_combo)

        # Bank account combo (shown for Bank)
        self.bank_combo = QComboBox()
        self.bank_combo.setMinimumWidth(220)
        self._bank_lbl = QLabel("Bank Account:")
        form.addRow(self._bank_lbl, self.bank_combo)

        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setRange(0.01, 99_999_999)
        self.amount_spin.setDecimals(0)
        self.amount_spin.setSingleStep(1000)
        self.amount_spin.setGroupSeparatorShown(True)
        self.amount_spin.setPrefix("PKR ")
        form.addRow("Amount:", self.amount_spin)

        self.notes_edit = QLineEdit()
        self.notes_edit.setPlaceholderText("Reference, details, etc.")
        form.addRow("Notes:", self.notes_edit)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

        self._reload_party_combo()
        self._reload_bank_combo()
        self._set_party_type("supplier")

    def _set_party_type(self, ptype):
        self._party_type = ptype
        _style_toggle(self._btn_sup,  ptype == "supplier",  "left")
        _style_toggle(self._btn_cust, ptype == "customer",  "mid")
        _style_toggle(self._btn_bank, ptype == "bank",      "right")
        is_bank = ptype == "bank"
        self._party_lbl.setVisible(not is_bank)
        self.party_combo.setVisible(not is_bank)
        self._bank_lbl.setVisible(is_bank)
        self.bank_combo.setVisible(is_bank)
        if is_bank:
            self._hint_lbl.setText("Cash Withdrawal: money moves from Bank → Cash in Hand")
        elif ptype == "supplier":
            self._hint_lbl.setText("Refund received from supplier (reduces their balance)")
        else:
            self._hint_lbl.setText("Payment received from customer (reduces their balance)")
        if not is_bank:
            self._reload_party_combo()

    def _reload_party_combo(self):
        self.party_combo.clear()
        parties = db_parties_list(self._party_type)
        ph = (f"— Select {'Supplier' if self._party_type == 'supplier' else 'Customer'} —"
              if parties else f"— No {'suppliers' if self._party_type == 'supplier' else 'credit customers'} found —")
        self.party_combo.addItem(ph, None)
        for p in parties:
            self.party_combo.addItem(p["name"], p["id"])

    def _reload_bank_combo(self):
        self.bank_combo.clear()
        accounts = db_bank_accounts()
        if not accounts:
            self.bank_combo.addItem("— No bank accounts (add in Settings) —", None)
        else:
            self.bank_combo.addItem("— Select Account —", None)
            for a in accounts:
                self.bank_combo.addItem(a["name"], a["id"])

    def _accept(self):
        if self._party_type == "bank":
            if self.bank_combo.currentData() is None:
                QMessageBox.warning(self, "Validation", "Please select a bank account.")
                return
        else:
            if self.party_combo.currentData() is None:
                lbl = "supplier" if self._party_type == "supplier" else "customer"
                QMessageBox.warning(self, "Validation", f"Please select a {lbl}.")
                return
        if self.amount_spin.value() <= 0:
            QMessageBox.warning(self, "Validation", "Amount must be greater than zero.")
            return
        self.accept()

    def get_data(self):
        """Returns (party_type, party_id, date_str, amount, voucher_type, notes)"""
        date_str = self.date_edit.date().toString("dd/MM/yyyy")
        amount   = self.amount_spin.value()
        notes    = self.notes_edit.text().strip()
        if self._party_type == "bank":
            return ("bank", self.bank_combo.currentData(), date_str, amount, "CR", notes)
        return (
            self._party_type,
            self.party_combo.currentData(),
            date_str, amount, "CR", notes,
        )


class CashPaymentDialog(QDialog):
    """
    CP voucher — cash / bank going OUT.
    Supplier:  payment to supplier          (reduces what you owe them)
    Customer:  refund given to customer     (reduces what they owe you)
    Bank:      cash deposit into bank       (Cash in Hand ↓, Bank ↑)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cash Payment Voucher (CP)")
        self.setMinimumWidth(460)
        self._party_type = "supplier"

        form = QFormLayout(self)
        form.setSpacing(12)
        form.setContentsMargins(20, 20, 20, 20)

        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        self.date_edit.setCalendarPopup(True)
        form.addRow("Date:", self.date_edit)

        type_row, self._btn_sup, self._btn_cust, self._btn_bank = _make_three_way_toggle(
            "Supplier", "Customer", "Bank"
        )
        self._btn_sup.clicked.connect(lambda: self._set_party_type("supplier"))
        self._btn_cust.clicked.connect(lambda: self._set_party_type("customer"))
        self._btn_bank.clicked.connect(lambda: self._set_party_type("bank"))
        form.addRow("Party Type:", type_row)

        self._hint_lbl = QLabel("")
        self._hint_lbl.setStyleSheet("color:#64748b; font-size:9pt;")
        form.addRow("", self._hint_lbl)

        self.party_combo = QComboBox()
        self.party_combo.setMinimumWidth(220)
        self._party_lbl = QLabel("Party:")
        form.addRow(self._party_lbl, self.party_combo)

        self.bank_combo = QComboBox()
        self.bank_combo.setMinimumWidth(220)
        self._bank_lbl = QLabel("Bank Account:")
        form.addRow(self._bank_lbl, self.bank_combo)

        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setRange(0.01, 99_999_999)
        self.amount_spin.setDecimals(0)
        self.amount_spin.setSingleStep(1000)
        self.amount_spin.setGroupSeparatorShown(True)
        self.amount_spin.setPrefix("PKR ")
        form.addRow("Amount:", self.amount_spin)

        self.notes_edit = QLineEdit()
        self.notes_edit.setPlaceholderText("Reference, details, etc.")
        form.addRow("Notes:", self.notes_edit)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

        self._reload_party_combo()
        self._reload_bank_combo()
        self._set_party_type("supplier")

    def _set_party_type(self, ptype):
        self._party_type = ptype
        _style_toggle(self._btn_sup,  ptype == "supplier",  "left")
        _style_toggle(self._btn_cust, ptype == "customer",  "mid")
        _style_toggle(self._btn_bank, ptype == "bank",      "right")
        is_bank = ptype == "bank"
        self._party_lbl.setVisible(not is_bank)
        self.party_combo.setVisible(not is_bank)
        self._bank_lbl.setVisible(is_bank)
        self.bank_combo.setVisible(is_bank)
        if is_bank:
            self._hint_lbl.setText("Cash Deposit: money moves from Cash in Hand → Bank")
        elif ptype == "supplier":
            self._hint_lbl.setText("Payment to supplier (reduces what you owe them)")
        else:
            self._hint_lbl.setText("Refund to customer (reduces what they owe you)")
        if not is_bank:
            self._reload_party_combo()

    def _reload_party_combo(self):
        self.party_combo.clear()
        parties = db_parties_list(self._party_type)
        ph = (f"— Select {'Supplier' if self._party_type == 'supplier' else 'Customer'} —"
              if parties else f"— No {'suppliers' if self._party_type == 'supplier' else 'credit customers'} found —")
        self.party_combo.addItem(ph, None)
        for p in parties:
            self.party_combo.addItem(p["name"], p["id"])

    def _reload_bank_combo(self):
        self.bank_combo.clear()
        accounts = db_bank_accounts()
        if not accounts:
            self.bank_combo.addItem("— No bank accounts (add in Settings) —", None)
        else:
            self.bank_combo.addItem("— Select Account —", None)
            for a in accounts:
                self.bank_combo.addItem(a["name"], a["id"])

    def _accept(self):
        if self._party_type == "bank":
            if self.bank_combo.currentData() is None:
                QMessageBox.warning(self, "Validation", "Please select a bank account.")
                return
        else:
            if self.party_combo.currentData() is None:
                lbl = "supplier" if self._party_type == "supplier" else "customer"
                QMessageBox.warning(self, "Validation", f"Please select a {lbl}.")
                return
        if self.amount_spin.value() <= 0:
            QMessageBox.warning(self, "Validation", "Amount must be greater than zero.")
            return
        self.accept()

    def get_data(self):
        date_str = self.date_edit.date().toString("dd/MM/yyyy")
        amount   = self.amount_spin.value()
        notes    = self.notes_edit.text().strip()
        if self._party_type == "bank":
            return ("bank", self.bank_combo.currentData(), date_str, amount, "CP", notes)
        return (
            self._party_type,
            self.party_combo.currentData(),
            date_str, amount, "CP", notes,
        )


def _build_accounts_combo(combo: QComboBox):
    """
    Fill combo with all accounts for double-entry JV.
    UserRole data: dict {'type': ..., 'id': ...} or None for separators/placeholder.
    """
    combo.clear()
    combo.addItem("— Select Account —", None)
    combo.addItem("Cash in Hand", {"type": "cash", "id": None})
    accounts = db_bank_accounts()
    for a in accounts:
        combo.addItem(f"Bank — {a['name']}", {"type": "bank", "id": a["id"]})
    conn = get_connection()
    suppliers = conn.execute(
        "SELECT id, name FROM suppliers WHERE id != 0 ORDER BY name"
    ).fetchall()
    customers = conn.execute(
        "SELECT id, name FROM customers WHERE type='credit' ORDER BY name"
    ).fetchall()
    conn.close()
    if suppliers:
        idx = combo.count()
        combo.addItem("── Suppliers ──", None)
        combo.model().item(idx).setEnabled(False)
        for r in suppliers:
            combo.addItem(r["name"], {"type": "supplier", "id": r["id"]})
    if customers:
        idx = combo.count()
        combo.addItem("── Credit Customers ──", None)
        combo.model().item(idx).setEnabled(False)
        for r in customers:
            combo.addItem(r["name"], {"type": "customer", "id": r["id"]})


class DoubleEntryJournalDialog(QDialog):
    """
    Proper double-entry journal voucher.
    Debit side and Credit side must have equal amounts before saving.

    Accounting logic applied on save:
      Dr Supplier  → reduces supplier balance   (credit entry in supplier ledger)
      Cr Customer  → reduces customer balance   (credit entry in customer ledger)
      Dr Bank      → bank balance increases     (bank_transactions CP)
      Cr Bank      → bank balance decreases     (bank_transactions CR)
      Dr Cash      → cash in hand increases     (cash_journal_lines 'in')
      Cr Cash      → cash in hand decreases     (cash_journal_lines 'out')
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Journal Voucher (JV) — Double Entry")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # ── Date and Notes ────────────────────────────────────────────────────
        top = QFormLayout()
        top.setSpacing(10)

        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        self.date_edit.setCalendarPopup(True)
        top.addRow("Date:", self.date_edit)

        self.notes_edit = QLineEdit()
        self.notes_edit.setPlaceholderText("Description / reason (required)")
        top.addRow("Description:", self.notes_edit)

        layout.addLayout(top)

        # ── Double entry grid ─────────────────────────────────────────────────
        grid_frame = QFrame()
        grid_frame.setStyleSheet(
            "QFrame { background:#f8fafc; border:1px solid #e2e8f0; border-radius:6px; }"
        )
        grid = QHBoxLayout(grid_frame)
        grid.setContentsMargins(16, 14, 16, 14)
        grid.setSpacing(24)

        # Debit side
        dr_col = QVBoxLayout()
        dr_title = QLabel("DEBIT (Dr)")
        dr_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        dr_title.setStyleSheet("color:#dc2626;")
        dr_col.addWidget(dr_title)
        dr_hint = QLabel("Account whose balance increases\nor bank/cash that receives money")
        dr_hint.setStyleSheet("color:#94a3b8; font-size:8pt;")
        dr_col.addWidget(dr_hint)
        self.dr_combo = QComboBox()
        self.dr_combo.setMinimumWidth(200)
        _build_accounts_combo(self.dr_combo)
        dr_col.addWidget(self.dr_combo)
        self.dr_spin = QDoubleSpinBox()
        self.dr_spin.setRange(0, 99_999_999)
        self.dr_spin.setDecimals(0)
        self.dr_spin.setSingleStep(1000)
        self.dr_spin.setGroupSeparatorShown(True)
        self.dr_spin.setPrefix("PKR ")
        self.dr_spin.valueChanged.connect(self._update_balance_lbl)
        dr_col.addWidget(self.dr_spin)
        grid.addLayout(dr_col)

        # Balance indicator
        bal_col = QVBoxLayout()
        bal_col.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._bal_lbl = QLabel("=")
        self._bal_lbl.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        self._bal_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._bal_lbl.setStyleSheet("color:#94a3b8;")
        bal_col.addWidget(self._bal_lbl)
        grid.addLayout(bal_col)

        # Credit side
        cr_col = QVBoxLayout()
        cr_title = QLabel("CREDIT (Cr)")
        cr_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        cr_title.setStyleSheet("color:#16a34a;")
        cr_col.addWidget(cr_title)
        cr_hint = QLabel("Account whose balance decreases\nor bank/cash that pays out money")
        cr_hint.setStyleSheet("color:#94a3b8; font-size:8pt;")
        cr_col.addWidget(cr_hint)
        self.cr_combo = QComboBox()
        self.cr_combo.setMinimumWidth(200)
        _build_accounts_combo(self.cr_combo)
        cr_col.addWidget(self.cr_combo)
        self.cr_spin = QDoubleSpinBox()
        self.cr_spin.setRange(0, 99_999_999)
        self.cr_spin.setDecimals(0)
        self.cr_spin.setSingleStep(1000)
        self.cr_spin.setGroupSeparatorShown(True)
        self.cr_spin.setPrefix("PKR ")
        self.cr_spin.valueChanged.connect(self._update_balance_lbl)
        cr_col.addWidget(self.cr_spin)
        grid.addLayout(cr_col)

        layout.addWidget(grid_frame)

        # Examples help text
        eg = QLabel(
            "Examples:  Bank transfer to supplier → Dr Supplier / Cr Bank\n"
            "           Customer pays via bank   → Dr Bank / Cr Customer\n"
            "           Supplier rebate (cash)   → Dr Cash / Cr Supplier"
        )
        eg.setStyleSheet("color:#64748b; font-size:9pt;")
        layout.addWidget(eg)

        info = QLabel("Voucher type: JV  •  Numbered automatically (JV-XXXX)")
        info.setStyleSheet("color:#94a3b8; font-size:9pt;")
        layout.addWidget(info)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _update_balance_lbl(self):
        dr = self.dr_spin.value()
        cr = self.cr_spin.value()
        if dr == 0 and cr == 0:
            self._bal_lbl.setText("=")
            self._bal_lbl.setStyleSheet("color:#94a3b8;")
        elif dr == cr:
            self._bal_lbl.setText("✓")
            self._bal_lbl.setStyleSheet("color:#16a34a;")
        else:
            diff = abs(dr - cr)
            self._bal_lbl.setText(f"≠\n{fmt_pkr(diff)}\noff")
            self._bal_lbl.setStyleSheet("color:#dc2626; font-size:12pt;")

    def _accept(self):
        if not self.notes_edit.text().strip():
            QMessageBox.warning(self, "Validation", "Description is required.")
            return
        dr_data = self.dr_combo.currentData()
        cr_data = self.cr_combo.currentData()
        if dr_data is None:
            QMessageBox.warning(self, "Validation", "Please select the Debit account.")
            return
        if cr_data is None:
            QMessageBox.warning(self, "Validation", "Please select the Credit account.")
            return
        dr_val = self.dr_spin.value()
        cr_val = self.cr_spin.value()
        if dr_val <= 0:
            QMessageBox.warning(self, "Validation", "Debit amount must be greater than zero.")
            return
        if dr_val != cr_val:
            QMessageBox.critical(
                self, "Amounts Do Not Balance",
                "Debit and Credit amounts must be equal — transaction cannot be saved.\n\n"
                f"Debit: PKR {fmt_pkr(dr_val)}   Credit: PKR {fmt_pkr(cr_val)}\n"
                f"Difference: PKR {fmt_pkr(abs(dr_val - cr_val))}"
            )
            return
        if dr_data == cr_data:
            QMessageBox.warning(self, "Validation",
                "Debit and Credit accounts cannot be the same.")
            return
        self.accept()

    def get_data(self):
        dr_data = self.dr_combo.currentData()
        cr_data = self.cr_combo.currentData()
        return (
            self.date_edit.date().toString("dd/MM/yyyy"),
            self.notes_edit.text().strip(),
            dr_data["type"], dr_data["id"],
            cr_data["type"], cr_data["id"],
            self.dr_spin.value(),
        )


# ── Bank Ledger Widget ────────────────────────────────────────────────────────

class BankLedgerWidget(QWidget):
    """Running statement for a bank account — mirrors supplier/customer ledger style."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(10)

        # ── Control card ──────────────────────────────────────────────────────
        ctrl = QFrame()
        ctrl.setStyleSheet(CARD_STYLE)
        cl = QHBoxLayout(ctrl)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(10)

        cl.addWidget(QLabel("Account:"))
        self.bank_combo = QComboBox()
        self.bank_combo.setMinimumWidth(200)
        self.bank_combo.currentIndexChanged.connect(self._on_account_change)
        cl.addWidget(self.bank_combo)

        cl.addWidget(QLabel("From:"))
        self.from_date = QDateEdit(QDate.currentDate().addMonths(-3))
        self.from_date.setDisplayFormat("dd/MM/yyyy")
        self.from_date.setCalendarPopup(True)
        cl.addWidget(self.from_date)

        cl.addWidget(QLabel("To:"))
        self.to_date = QDateEdit(QDate.currentDate())
        self.to_date.setDisplayFormat("dd/MM/yyyy")
        self.to_date.setCalendarPopup(True)
        cl.addWidget(self.to_date)

        btn_search = QPushButton("Search")
        btn_search.setStyleSheet(BTN_SECONDARY)
        btn_search.clicked.connect(self._search)
        cl.addWidget(btn_search)

        btn_all = QPushButton("All")
        btn_all.setStyleSheet(BTN_SECONDARY)
        btn_all.clicked.connect(self._show_all)
        cl.addWidget(btn_all)

        cl.addStretch()
        layout.addWidget(ctrl)

        # ── Balance card ──────────────────────────────────────────────────────
        self.bal_card = QFrame()
        self.bal_card.setStyleSheet(CARD_STYLE)
        self.bal_card.setVisible(False)
        bl = QHBoxLayout(self.bal_card)
        bl.setContentsMargins(20, 12, 20, 12)

        bal_info = QVBoxLayout()
        lbl_title = QLabel("Current Bank Balance")
        lbl_title.setStyleSheet("color:#64748b; font-size:9pt;")
        self._bal_lbl = QLabel("PKR 0")
        self._bal_lbl.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        bal_info.addWidget(lbl_title)
        bal_info.addWidget(self._bal_lbl)
        bl.addLayout(bal_info)
        bl.addStretch()

        layout.addWidget(self.bal_card)

        # ── Table ─────────────────────────────────────────────────────────────
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Date", "Voucher", "Description", "Debit (IN)", "Credit (OUT)", "Balance (PKR)"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.table.setStyleSheet(TABLE_STYLE)
        self.table.doubleClicked.connect(self._edit_bank_entry)
        layout.addWidget(self.table, stretch=1)

        # ── Footer ────────────────────────────────────────────────────────────
        footer = QHBoxLayout()
        footer.addStretch()
        self._closing_lbl = QLabel("")
        self._closing_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self._closing_lbl.setStyleSheet("color:#1e293b;")
        footer.addWidget(self._closing_lbl)
        layout.addLayout(footer)

        self._reload_bank_combo()

    def _reload_bank_combo(self):
        self.bank_combo.blockSignals(True)
        self.bank_combo.clear()
        accounts = db_bank_accounts()
        if not accounts:
            self.bank_combo.addItem("— No bank accounts (add in Settings) —", None)
        else:
            self.bank_combo.addItem("— Select Account —", None)
            for a in accounts:
                self.bank_combo.addItem(a["name"], a["id"])
            if len(accounts) == 1:
                self.bank_combo.setCurrentIndex(1)
        self.bank_combo.blockSignals(False)
        self._on_account_change()

    def _on_account_change(self):
        acc_id = self.bank_combo.currentData()
        self.bal_card.setVisible(acc_id is not None)
        self.table.setRowCount(0)
        self._closing_lbl.setText("")
        if acc_id is not None:
            self._load(acc_id)

    def _search(self):
        acc_id = self.bank_combo.currentData()
        if acc_id is None:
            return
        from_iso = self.from_date.date().toString("yyyy-MM-dd")
        to_iso   = self.to_date.date().toString("yyyy-MM-dd")
        self._load(acc_id, from_iso, to_iso)

    def _show_all(self):
        acc_id = self.bank_combo.currentData()
        if acc_id is not None:
            self._load(acc_id)

    def _load(self, bank_account_id, from_iso=None, to_iso=None):
        entries = db_bank_ledger_entries(bank_account_id, from_iso, to_iso)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)

        HEADER_BG = QBrush(QColor("#f0f9ff"))
        DR_COLOR  = QColor("#16a34a")   # money IN = green
        CR_COLOR  = QColor("#dc2626")   # money OUT = red
        BAL_FONT  = QFont("Segoe UI", 10, QFont.Weight.Bold)

        closing = 0.0
        for e in entries:
            row = self.table.rowCount()
            self.table.insertRow(row)
            is_hdr = e.get("is_header", False)
            cells = [
                e.get("date", ""),
                e.get("voucher", ""),
                e.get("desc", ""),
                fmt_pkr(e["dr"]) if e["dr"] else "",
                fmt_pkr(e["cr"]) if e["cr"] else "",
                fmt_pkr(e["balance"]),
            ]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col in (3, 4, 5):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                if is_hdr:
                    item.setBackground(HEADER_BG)
                    item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                if col == 3 and text:
                    item.setForeground(QBrush(DR_COLOR))
                if col == 4 and text:
                    item.setForeground(QBrush(CR_COLOR))
                if col == 5:
                    item.setFont(BAL_FONT)
                    bal = e["balance"]
                    item.setForeground(QBrush(
                        DR_COLOR if bal > 0 else (CR_COLOR if bal < 0 else QColor("#475569"))
                    ))
                self.table.setItem(row, col, item)
            closing = e["balance"]

        self._bal_lbl.setText(f"PKR {fmt_pkr(closing)}")
        bal_color = "#16a34a" if closing >= 0 else "#dc2626"
        self._bal_lbl.setStyleSheet(f"color:{bal_color}; font-size:16pt; font-weight:bold;")
        if entries:
            self._closing_lbl.setText(
                f"Closing Balance:  PKR {fmt_pkr(abs(closing))}  "
                f"{'DR' if closing >= 0 else 'CR'}"
            )
        else:
            self._closing_lbl.setText("")

    def _edit_bank_entry(self):
        """Double-click on a bank ledger row — opens edit dialog for CP/CR entries."""
        row = self.table.currentRow()
        if row < 0:
            return
        voucher_item = self.table.item(row, 1)
        if not voucher_item:
            return
        voucher = voucher_item.text().strip()
        if not voucher or voucher in ("OB", ""):
            return

        from edit_vouchers import (
            BankTransactionEditDialog, db_lookup_bank_transaction,
        )

        if voucher.startswith("CP-") or voucher.startswith("CR-"):
            tx = db_lookup_bank_transaction(voucher)
            if not tx:
                QMessageBox.information(self, "Not Found",
                    f"Bank transaction {voucher} not found.")
                return
            if tx.get("source") == "jv":
                QMessageBox.information(self, "Journal Entry",
                    f"{voucher} was created as part of a Journal Voucher.\n"
                    "Edit it from the Journal Voucher (JV) dialog on the Ledger page.")
                return
            dlg = BankTransactionEditDialog(tx, self)
            result = dlg.exec()
            if result in (QDialog.DialogCode.Accepted, BankTransactionEditDialog.DELETED):
                self._reload_bank_combo()
        elif voucher.startswith("JV-"):
            QMessageBox.information(self, "Journal Voucher",
                f"{voucher} is a Journal Voucher entry.\n"
                "Use the + Journal Voucher button to create new entries.")
        elif voucher.startswith("SV-"):
            QMessageBox.information(self, "Sale Record",
                f"{voucher} is a sale payment. Edit it from the Sales page.")
        # Other prefixes: silently ignore

    def refresh(self):
        """Called when switching to bank view — re-loads bank accounts list."""
        self._reload_bank_combo()


# ── Ledger Page ───────────────────────────────────────────────────────────────

class LedgerPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:#f1f5f9;")
        self._party_type = "supplier"
        self._party_id   = None
        self._party_name = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)

        title = QLabel("Ledger")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title.setStyleSheet("color:#1e293b;")
        layout.addWidget(title)

        # ── Standalone voucher buttons — always visible ───────────────────────
        actions_card = QFrame()
        actions_card.setStyleSheet(CARD_STYLE)
        al = QHBoxLayout(actions_card)
        al.setContentsMargins(12, 8, 12, 8)
        al.setSpacing(8)
        lbl_rec = QLabel("Record:")
        lbl_rec.setStyleSheet("color:#64748b; font-size:9pt; font-weight:bold;")
        al.addWidget(lbl_rec)
        btn_cr = QPushButton("+ Cash Receipt (CR)")
        btn_cr.setStyleSheet(BTN_GREEN)
        btn_cr.setToolTip("Cash or bank withdrawal received (Supplier refund / Customer payment / Bank withdrawal)")
        btn_cr.clicked.connect(self._standalone_cr)
        al.addWidget(btn_cr)
        btn_cp = QPushButton("+ Cash Payment (CP)")
        btn_cp.setStyleSheet(BTN_PRIMARY)
        btn_cp.setToolTip("Cash or bank deposit paid out (Supplier payment / Customer refund / Bank deposit)")
        btn_cp.clicked.connect(self._standalone_cp)
        al.addWidget(btn_cp)
        btn_jv = QPushButton("+ Journal Voucher (JV)")
        btn_jv.setStyleSheet(BTN_SECONDARY)
        btn_jv.setToolTip("Double-entry journal entry (bank transfer, rebate, adjustment)")
        btn_jv.clicked.connect(self._standalone_jv)
        al.addWidget(btn_jv)
        al.addStretch()
        layout.addWidget(actions_card)

        # ── Party type toggle (Suppliers | Customers | Bank) ──────────────────
        type_card = QFrame()
        type_card.setStyleSheet(CARD_STYLE)
        tl = QHBoxLayout(type_card)
        tl.setContentsMargins(12, 8, 12, 8)
        tl.setSpacing(0)
        self.btn_sup  = QPushButton("Suppliers")
        self.btn_sup.setFixedHeight(32)
        self.btn_cust = QPushButton("Customers")
        self.btn_cust.setFixedHeight(32)
        self.btn_bank = QPushButton("Bank")
        self.btn_bank.setFixedHeight(32)
        _style_toggle(self.btn_sup,  True,  "left")
        _style_toggle(self.btn_cust, False, "mid")
        _style_toggle(self.btn_bank, False, "right")
        self.btn_sup.clicked.connect(lambda: self._set_party_type("supplier"))
        self.btn_cust.clicked.connect(lambda: self._set_party_type("customer"))
        self.btn_bank.clicked.connect(lambda: self._set_party_type("bank"))
        tl.addWidget(self.btn_sup)
        tl.addWidget(self.btn_cust)
        tl.addWidget(self.btn_bank)
        tl.addStretch()
        layout.addWidget(type_card)

        # ── Party controls (hidden when Bank) ─────────────────────────────────
        self.ctrl_card = QFrame()
        self.ctrl_card.setStyleSheet(CARD_STYLE)
        cl = QHBoxLayout(self.ctrl_card)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(10)
        cl.addWidget(QLabel("Party:"))
        self.party_combo = QComboBox()
        self.party_combo.setMinimumWidth(190)
        self.party_combo.currentIndexChanged.connect(self._on_party_change)
        cl.addWidget(self.party_combo)
        cl.addWidget(QLabel("From:"))
        self.from_date = QDateEdit(QDate.currentDate().addMonths(-3))
        self.from_date.setDisplayFormat("dd/MM/yyyy")
        self.from_date.setCalendarPopup(True)
        cl.addWidget(self.from_date)
        cl.addWidget(QLabel("To:"))
        self.to_date = QDateEdit(QDate.currentDate())
        self.to_date.setDisplayFormat("dd/MM/yyyy")
        self.to_date.setCalendarPopup(True)
        cl.addWidget(self.to_date)
        btn_search = QPushButton("Search")
        btn_search.setStyleSheet(BTN_SECONDARY)
        btn_search.clicked.connect(self._search)
        cl.addWidget(btn_search)
        btn_all = QPushButton("All")
        btn_all.setStyleSheet(BTN_SECONDARY)
        btn_all.clicked.connect(self._show_all)
        cl.addWidget(btn_all)
        cl.addStretch()
        self.btn_payment = QPushButton("+ Payment")
        self.btn_payment.setStyleSheet(BTN_GREEN)
        self.btn_payment.setEnabled(False)
        self.btn_payment.clicked.connect(self._add_payment)
        cl.addWidget(self.btn_payment)
        self.btn_journal = QPushButton("+ Journal Entry")
        self.btn_journal.setStyleSheet(BTN_SECONDARY)
        self.btn_journal.setEnabled(False)
        self.btn_journal.clicked.connect(self._add_journal)
        cl.addWidget(self.btn_journal)
        layout.addWidget(self.ctrl_card)

        # ── Party info card ───────────────────────────────────────────────────
        self.info_card = QFrame()
        self.info_card.setStyleSheet(CARD_STYLE)
        self.info_card.setVisible(False)
        il = QHBoxLayout(self.info_card)
        il.setContentsMargins(20, 12, 20, 12)
        il.setSpacing(40)
        name_col = QVBoxLayout()
        name_col.setSpacing(2)
        self._lbl_name_title = QLabel("Name")
        self._lbl_name_title.setStyleSheet("color:#64748b; font-size:9pt;")
        self._lbl_name = QLabel("")
        self._lbl_name.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self._lbl_name.setMinimumWidth(180)
        name_col.addWidget(self._lbl_name_title)
        name_col.addWidget(self._lbl_name)
        il.addLayout(name_col)
        contact_col = QVBoxLayout()
        contact_col.setSpacing(2)
        lbl_ct = QLabel("Contact")
        lbl_ct.setStyleSheet("color:#64748b; font-size:9pt;")
        self._lbl_contact = QLabel("")
        self._lbl_contact.setFont(QFont("Segoe UI", 10))
        self._lbl_contact.setMinimumWidth(130)
        contact_col.addWidget(lbl_ct)
        contact_col.addWidget(self._lbl_contact)
        il.addLayout(contact_col)
        il.addStretch()
        balance_col = QVBoxLayout()
        balance_col.setSpacing(2)
        self._lbl_bal_title = QLabel("Current Balance")
        self._lbl_bal_title.setStyleSheet("color:#64748b; font-size:9pt;")
        self._lbl_balance = QLabel("PKR 0")
        self._lbl_balance.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self._lbl_balance.setMinimumWidth(220)
        balance_col.addWidget(self._lbl_bal_title)
        balance_col.addWidget(self._lbl_balance)
        il.addLayout(balance_col)
        layout.addWidget(self.info_card)

        # ── Party ledger table ────────────────────────────────────────────────
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Date", "Voucher", "Description", "Debit (PKR)", "Credit (PKR)", "Balance (PKR)"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet(TABLE_STYLE)
        self.table.doubleClicked.connect(self._edit_ledger_entry)
        layout.addWidget(self.table, stretch=1)

        footer = QHBoxLayout()
        footer.addStretch()
        self.closing_label = QLabel("")
        self.closing_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.closing_label.setStyleSheet("color:#1e293b;")
        footer.addWidget(self.closing_label)
        layout.addLayout(footer)

        # ── Bank ledger widget (shown instead of party table when Bank) ───────
        self._bank_widget = BankLedgerWidget(self)
        self._bank_widget.setVisible(False)
        layout.addWidget(self._bank_widget, stretch=1)

        self._load_party_combo()

    # ── Party type toggle ─────────────────────────────────────────────────────

    def _set_party_type(self, ptype):
        self._party_type = ptype
        _style_toggle(self.btn_sup,  ptype == "supplier", "left")
        _style_toggle(self.btn_cust, ptype == "customer", "mid")
        _style_toggle(self.btn_bank, ptype == "bank",     "right")

        is_bank = ptype == "bank"
        self.ctrl_card.setVisible(not is_bank)
        self.info_card.setVisible(False)
        self.table.setVisible(not is_bank)
        self.closing_label.setVisible(not is_bank)
        self._bank_widget.setVisible(is_bank)

        if is_bank:
            self._bank_widget.refresh()
        else:
            self._load_party_combo()

    def _load_party_combo(self):
        self.party_combo.blockSignals(True)
        self.party_combo.clear()
        label = ("— Select Supplier —" if self._party_type == "supplier"
                 else "— Select Customer —")
        self.party_combo.addItem(label, None)
        for p in db_parties_list(self._party_type):
            self.party_combo.addItem(p["name"], p["id"])
        self.party_combo.blockSignals(False)
        self._party_id   = None
        self._party_name = ""
        self.info_card.setVisible(False)
        self.btn_payment.setEnabled(False)
        self.btn_journal.setEnabled(False)
        self.table.setRowCount(0)
        self.closing_label.setText("")

    # ── Party selection ───────────────────────────────────────────────────────

    def _on_party_change(self):
        pid = self.party_combo.currentData()
        if pid is None:
            self._party_id = None
            self.info_card.setVisible(False)
            self.btn_payment.setEnabled(False)
            self.btn_journal.setEnabled(False)
            self.table.setRowCount(0)
            self.closing_label.setText("")
            return
        self._party_id   = pid
        self._party_name = self.party_combo.currentText()
        self._update_info_card()
        self.btn_payment.setEnabled(True)
        self.btn_journal.setEnabled(True)
        self._load_ledger()

    def _update_info_card(self):
        if self._party_id is None:
            return
        info = db_party_info(self._party_type, self._party_id)
        if not info:
            return
        self._lbl_name.setText(info["name"])
        self._lbl_contact.setText(info["contact"] or "—")
        self.info_card.setVisible(True)

    # ── Load party ledger ─────────────────────────────────────────────────────

    def _load_ledger(self, from_iso=None, to_iso=None):
        if self._party_id is None:
            return
        entries = db_ledger_entries(self._party_type, self._party_id, from_iso, to_iso)
        self._populate_table(entries)

    def _search(self):
        from_iso = self.from_date.date().toString("yyyy-MM-dd")
        to_iso   = self.to_date.date().toString("yyyy-MM-dd")
        self._load_ledger(from_iso, to_iso)

    def _show_all(self):
        self._load_ledger()

    def _edit_ledger_entry(self):
        """Double-click on a ledger row — opens edit dialog for CP/CR/JV entries."""
        row = self.table.currentRow()
        if row < 0:
            return
        voucher_item = self.table.item(row, 1)
        if not voucher_item:
            return
        voucher = voucher_item.text().strip()
        if not voucher or voucher in ("OB", ""):
            return  # header / opening balance row

        from edit_vouchers import PaymentEditDialog, JVEditDialog, db_lookup_payment, db_lookup_journal_entry

        if voucher.startswith("CP-") or voucher.startswith("CR-"):
            pay = db_lookup_payment(voucher)
            if not pay:
                QMessageBox.information(self, "Not Found",
                    f"Payment record {voucher} not found.")
                return
            dlg = PaymentEditDialog(pay, self)
            result = dlg.exec()
            if result in (QDialog.DialogCode.Accepted, PaymentEditDialog.DELETED):
                self._update_info_card()
                self._load_ledger()

        elif voucher.startswith("JV-"):
            je = db_lookup_journal_entry(
                voucher,
                party_type=self._party_type,
                party_id=self._party_id,
            )
            if not je:
                QMessageBox.information(self, "Not Found",
                    f"Journal entry {voucher} not found for this party.\n"
                    "System-generated JVs (from sale/purchase returns) cannot be edited here.")
                return
            dlg = JVEditDialog(je, self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self._load_ledger()

        else:
            # SV / PV / SR / PR rows — tell user to go to the relevant page
            QMessageBox.information(self, "Edit Voucher",
                f"To edit {voucher}, open the "
                f"{'Sales' if voucher.startswith('SV') else 'Purchase'} page "
                f"and use the ✏ Edit button.")

    def _populate_table(self, entries):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.table.setWordWrap(True)
        HEADER_BG = QBrush(QColor("#f0f9ff"))
        DR_COLOR  = QColor("#dc2626")
        CR_COLOR  = QColor("#16a34a")
        BAL_FONT  = QFont("Segoe UI", 10, QFont.Weight.Bold)
        closing_balance = 0.0
        for e in entries:
            row = self.table.rowCount()
            self.table.insertRow(row)
            is_hdr = e.get("is_header", False)
            cells = [
                e.get("date", ""),
                e.get("voucher", ""),
                e.get("desc", ""),
                fmt_pkr(e["dr"]) if e["dr"] else "",
                fmt_pkr(e["cr"]) if e["cr"] else "",
                fmt_pkr(e["balance"]),
            ]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col in (3, 4, 5):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                if is_hdr:
                    item.setBackground(HEADER_BG)
                    item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                if col == 3 and text:
                    item.setForeground(QBrush(DR_COLOR))
                if col == 4 and text:
                    item.setForeground(QBrush(CR_COLOR))
                if col == 5:
                    item.setFont(BAL_FONT)
                    bal = e["balance"]
                    item.setForeground(QBrush(
                        DR_COLOR if bal > 0 else (CR_COLOR if bal < 0 else QColor("#475569"))
                    ))
                self.table.setItem(row, col, item)
            closing_balance = e["balance"]
        self.table.resizeRowsToContents()
        self._lbl_balance.setText(f"PKR {fmt_pkr(closing_balance)}")
        bal_color = "#dc2626" if closing_balance > 0 else "#16a34a"
        self._lbl_balance.setStyleSheet(f"color:{bal_color};")
        if entries:
            dr_cr = "DR" if closing_balance > 0 else "CR"
            self.closing_label.setText(
                f"Closing Balance:  PKR {fmt_pkr(abs(closing_balance))}  {dr_cr}"
            )
        else:
            self.closing_label.setText("")

    # ── Inline payment / journal for specific party ───────────────────────────

    def _add_payment(self):
        if self._party_id is None:
            return
        dlg = PaymentDialog(self._party_type, self._party_name, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        date_str, amount, ptype, notes = dlg.get_data()
        try:
            voucher = db_save_payment(
                self._party_type, self._party_id, date_str, amount, ptype, notes
            )
        except Exception as ex:
            QMessageBox.critical(self, "Error", str(ex))
            return
        QMessageBox.information(self, "Saved", f"Payment recorded as {voucher}.")
        self._update_info_card()
        self._load_ledger()

    def _add_journal(self):
        if self._party_id is None:
            return
        dlg = JournalDialog(self._party_type, self._party_name, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        date_str, amount, entry_type, notes = dlg.get_data()
        try:
            jv = db_save_journal(
                self._party_type, self._party_id, date_str, amount, entry_type, notes
            )
        except Exception as ex:
            QMessageBox.critical(self, "Error", str(ex))
            return
        QMessageBox.information(self, "Saved", f"Journal entry recorded as {jv}.")
        self._load_ledger()

    # ── Standalone voucher actions ────────────────────────────────────────────

    def _standalone_cr(self):
        dlg = CashReceiptDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        party_type, party_id, date_str, amount, ptype, notes = dlg.get_data()
        try:
            if party_type == "bank":
                voucher = db_save_bank_cp_cr("CR", party_id, date_str, amount, notes)
                if self._party_type == "bank":
                    self._bank_widget.refresh()
            else:
                voucher = db_save_payment(party_type, party_id, date_str, amount, ptype, notes)
                self._load_ledger()
        except Exception as ex:
            QMessageBox.critical(self, "Error", str(ex))
            return
        QMessageBox.information(self, "Saved", f"Cash receipt recorded as {voucher}.")

    def _standalone_cp(self):
        dlg = CashPaymentDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        party_type, party_id, date_str, amount, ptype, notes = dlg.get_data()
        try:
            if party_type == "bank":
                voucher = db_save_bank_cp_cr("CP", party_id, date_str, amount, notes)
                if self._party_type == "bank":
                    self._bank_widget.refresh()
            else:
                voucher = db_save_payment(party_type, party_id, date_str, amount, ptype, notes)
                self._load_ledger()
        except Exception as ex:
            QMessageBox.critical(self, "Error", str(ex))
            return
        QMessageBox.information(self, "Saved", f"Cash payment recorded as {voucher}.")

    def _standalone_jv(self):
        dlg = DoubleEntryJournalDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        date_str, notes, dr_type, dr_id, cr_type, cr_id, amount = dlg.get_data()
        try:
            jv = db_save_double_entry_jv(
                date_str, notes, dr_type, dr_id, cr_type, cr_id, amount
            )
        except Exception as ex:
            QMessageBox.critical(self, "Error", str(ex))
            return
        QMessageBox.information(
            self, "Saved",
            f"Journal Voucher {jv} saved.\n\n"
            f"Dr: {dr_type.capitalize()}  →  Cr: {cr_type.capitalize()}\n"
            f"Amount: PKR {fmt_pkr(amount)}"
        )
        # Refresh whichever view is active
        if self._party_type == "bank":
            self._bank_widget.refresh()
        else:
            self._load_ledger()
