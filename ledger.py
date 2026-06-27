import sqlite3
from collections import Counter
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QComboBox, QDateEdit,
    QDialog, QFormLayout, QDialogButtonBox, QDoubleSpinBox,
    QLineEdit, QMessageBox, QHeaderView, QAbstractItemView,
    QFrame, QButtonGroup, QRadioButton,
)
from PyQt6.QtCore import Qt, QDate, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QBrush, QShortcut, QKeySequence

from database import (
    get_connection, db_bank_accounts,
    db_save_bank_cp_cr, db_save_double_entry_jv,
    db_income_account,
    db_save_journal_voucher, db_load_journal_voucher,
    db_update_journal_voucher, db_delete_journal_voucher,
    db_load_journal_vouchers_list,
)
# Reuse the unified report export engine (reportlab PDF + csv, folder picker,
# <ReportName>_DDMMYYYY.<ext>) so ledger exports match every other report.
from reports import _do_export_pdf, _do_export_csv, _table_to_rows

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
    elif party_type == "other":
        rows = conn.execute(
            "SELECT id, name FROM other_parties ORDER BY name"
        ).fetchall()
    elif party_type == "expense":
        try:
            rows = conn.execute(
                "SELECT id, name FROM expense_categories ORDER BY name"
            ).fetchall()
        except Exception:
            rows = []
    else:
        rows = conn.execute(
            "SELECT id, name FROM customers WHERE type='credit' ORDER BY name"
        ).fetchall()
    conn.close()
    return rows


def db_party_info(party_type: str, party_id: int):
    conn = get_connection()
    table = {"supplier": "suppliers", "customer": "customers",
             "other": "other_parties"}.get(party_type, "customers")
    row = conn.execute(
        f"SELECT name, contact, opening_balance FROM {table} WHERE id=?", (party_id,)
    ).fetchone()
    conn.close()
    return row


def _payment_default_desc(ptype: str, party_type: str) -> str:
    """Return a sensible ledger description for a payment when no notes were entered."""
    if party_type == "other":
        return "Payment to Party" if ptype == "CP" else "Receipt from Party"
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
    table = {"supplier": "suppliers", "customer": "customers",
             "other": "other_parties"}.get(party_type, "customers")
    ob_row = conn.execute(
        f"SELECT opening_balance FROM {table} WHERE id=?", (party_id,)
    ).fetchone()
    ob = float(ob_row["opening_balance"] or 0) if ob_row else 0.0

    raw = []

    if party_type == "other":
        # Other parties have no purchases/sales — only cash CP/CR vouchers.
        # Direction mirrors the supplier side:
        #   CR (cash received from them)  → DEBIT  (you owe them more)
        #   CP (cash paid to them)        → CREDIT (you owe them less)
        for r in conn.execute(
            "SELECT date, voucher_number, notes, amount, type "
            "FROM payments WHERE party_type='other' AND party_id=?",
            (party_id,),
        ):
            desc = r[2] if r[2] else _payment_default_desc(r[4], "other")
            amt  = float(r[3] or 0)
            if r[4] == "CR":
                raw.append({"date": r[0], "voucher": r[1], "desc": desc,
                            "dr": amt, "cr": 0.0})
            else:
                raw.append({"date": r[0], "voucher": r[1], "desc": desc,
                            "dr": 0.0, "cr": amt})

    elif party_type == "supplier":
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

        # Sales to this supplier — CREDIT (reduces balance / they owe us)
        for r in conn.execute(
            "SELECT sv.id, sv.date, sv.sv_number, sv.total_amount "
            "FROM sale_vouchers sv WHERE sv.supplier_as_customer_id=?",
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
            desc = "Sale: " + ", ".join(parts) if parts else "Sale to Supplier"
            raw.append({"date": r[1], "voucher": r[2], "desc": desc,
                        "dr": 0.0, "cr": float(r[3] or 0)})

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

        # Purchases from this customer — CREDIT (reduces balance / we owe them)
        for r in conn.execute(
            "SELECT pv.date, pv.pv_number, pv.total_amount "
            "FROM purchase_vouchers pv WHERE pv.customer_as_supplier_id=?",
            (party_id,),
        ):
            raw.append({"date": r[0], "voucher": r[1],
                        "desc": "Purchase from Customer", "dr": 0.0,
                        "cr": float(r[2] or 0)})

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

    # Legacy journal_entries
    for r in conn.execute(
        "SELECT date, jv_number, COALESCE(notes,'Journal Entry'), type, amount "
        "FROM journal_entries WHERE party_type=? AND party_id=?",
        (party_type, party_id),
    ):
        dr = float(r[4] or 0) if r[3] == "debit" else 0.0
        cr = float(r[4] or 0) if r[3] == "credit" else 0.0
        raw.append({"date": r[0], "voucher": r[1], "desc": r[2], "dr": dr, "cr": cr})

    # New-style journal_voucher_lines
    for r in conn.execute("""
        SELECT jv.date, jv.jv_number, COALESCE(jv.notes,'Journal Entry') AS notes,
               jvl.debit, jvl.credit
        FROM journal_voucher_lines jvl
        JOIN journal_vouchers jv ON jv.id = jvl.jv_id
        WHERE jvl.party_type=? AND jvl.party_id=?
    """, (party_type, party_id)):
        raw.append({"date": r["date"], "voucher": r["jv_number"],
                    "desc": r["notes"],
                    "dr": float(r["debit"] or 0), "cr": float(r["credit"] or 0)})

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


def db_save_multi_cp_cr(ptype: str, date_str: str, lines: list) -> str:
    """
    Save a multi-line CP or CR voucher.

    ptype  = 'CP' | 'CR'
    lines  = [(party_type, party_id, amount, reference), ...]
             party_type ∈ {'supplier', 'customer', 'other', 'bank'}
             For 'bank' lines party_id is the bank_account_id — the row goes
             into bank_transactions (cash_transfer), not payments.
             reference is a free-text string stored per line (can be empty).

    A single voucher number is generated and shared by every line.
    Rolls back the entire transaction on any error.
    """
    counter_key = "last_cp_number" if ptype == "CP" else "last_cr_number"
    conn = get_connection()
    try:
        c = conn.cursor()
        row = c.execute("SELECT value FROM settings WHERE key=?", (counter_key,)).fetchone()
        n = int(row["value"]) + 1 if row else 1
        c.execute("UPDATE settings SET value=? WHERE key=?", (str(n), counter_key))
        voucher = f"{ptype}-{n:04d}"

        for party_type, party_id, amount, reference in lines:
            if party_type == "bank":
                c.execute(
                    "INSERT INTO bank_transactions "
                    "(voucher_number, type, bank_account_id, source, date, amount, notes) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (voucher, ptype, party_id, "cash_transfer",
                     date_str, float(amount), reference or ""),
                )
            else:
                c.execute(
                    "INSERT INTO payments "
                    "(voucher_number, party_type, party_id, date, amount, type, notes, reference) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (voucher, party_type, party_id,
                     date_str, float(amount), ptype, "", reference or ""),
                )

        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()
    return voucher


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

    # New-style journal_voucher_lines for this bank account
    for r in conn.execute("""
        SELECT jv.date, jv.jv_number, COALESCE(jv.notes,'Journal Entry') AS notes,
               jvl.debit, jvl.credit
        FROM journal_voucher_lines jvl
        JOIN journal_vouchers jv ON jv.id = jvl.jv_id
        WHERE jvl.party_type='bank' AND jvl.party_id=?
    """, (bank_account_id,)):
        raw.append({"date": r["date"], "voucher": r["jv_number"],
                    "desc": r["notes"],
                    "dr": float(r["debit"] or 0), "cr": float(r["credit"] or 0)})

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
        self._party_type = party_type
        # Supplier → always CP (you pay).  Customer → always CR (they pay).
        # Other party (personal loan) → direction is chosen below.
        ptype = "CP" if party_type == "supplier" else "CR"
        if party_type == "supplier":
            verb = f"Payment to {party_name}"
        elif party_type == "other":
            verb = f"Cash Voucher — {party_name}"
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

        # Direction selector — only for Other Parties (both directions valid).
        self._dir_group = None
        if party_type == "other":
            self.radio_cp = QRadioButton("Payment to them (cash out)")
            self.radio_cr = QRadioButton("Receipt from them (cash in)")
            self.radio_cp.setChecked(True)
            self._dir_group = QButtonGroup(self)
            self._dir_group.addButton(self.radio_cp)
            self._dir_group.addButton(self.radio_cr)
            form.addRow("Direction:", self.radio_cp)
            form.addRow("", self.radio_cr)

        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setRange(0.01, 99_999_999)
        self.amount_spin.setDecimals(0)
        self.amount_spin.setSingleStep(1000)
        self.amount_spin.setGroupSeparatorShown(True)
        self.amount_spin.setPrefix("PKR ")
        self.amount_spin.lineEdit().returnPressed.connect(
            lambda: self.amount_spin.focusNextChild())
        form.addRow("Amount:", self.amount_spin)

        self.notes_edit = QLineEdit()
        self.notes_edit.setPlaceholderText("Optional notes")
        self.notes_edit.returnPressed.connect(lambda: self.notes_edit.focusNextChild())
        form.addRow("Notes:", self.notes_edit)

        if party_type == "other":
            note = QLabel("Cash only  •  Voucher numbered automatically (CP / CR)")
        else:
            note = QLabel(f"Voucher type: {ptype}  •  Will be numbered automatically")
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
        if self._party_type == "other":
            ptype = "CP" if self.radio_cp.isChecked() else "CR"
        else:
            ptype = self._ptype
        return (
            self.date_edit.date().toString("dd/MM/yyyy"),
            self.amount_spin.value(),
            ptype,
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
        elif party_type == "other":
            dr_label = "Debit (increases what you owe them)"
            cr_label = "Credit (reduces what you owe them)"
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
        self.amount_spin.lineEdit().returnPressed.connect(
            lambda: self.amount_spin.focusNextChild())
        form.addRow("Amount:", self.amount_spin)

        self.notes_edit = QLineEdit()
        self.notes_edit.setPlaceholderText("Reason / description")
        self.notes_edit.returnPressed.connect(lambda: self.notes_edit.focusNextChild())
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


class _AmountSpinBox(QDoubleSpinBox):
    """
    Amount spinbox with two-Enter UX:
      1st Enter — commits the typed value (standard spinbox behaviour)
      2nd Enter — emits new_row_requested so the dialog adds another line
    """
    new_row_requested = pyqtSignal()

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.lineEdit().isModified():
                super().keyPressEvent(event)   # first Enter: commit value
            else:
                self.new_row_requested.emit()  # second Enter: new row
        else:
            super().keyPressEvent(event)


class MultiLineCpCrDialog(QDialog):
    """
    Multi-line Cash Payment (CP) or Cash Receipt (CR) voucher.

    Multiple parties can be included in one voucher; all lines share a single
    CP-XXXX / CR-XXXX number.  Party types per line:
      Supplier / Customer / Other → saved to payments table
      Bank                        → saved to bank_transactions (cash transfer)
    """

    _PARTY_LABELS = [
        ("Supplier", "supplier"),
        ("Customer", "customer"),
        ("Other",    "other"),
        ("Expense",  "expense"),
        ("Bank",     "bank"),
    ]

    def __init__(self, ptype: str, parent=None):
        super().__init__(parent)
        self._ptype   = ptype    # 'CP' | 'CR'
        self._voucher = None     # set after successful save

        self.setWindowTitle(
            "Cash Payment Voucher (CP)" if ptype == "CP"
            else "Cash Receipt Voucher (CR)"
        )
        self.setMinimumWidth(740)
        self.resize(780, 520)

        # Pre-load all party lists once to avoid DB hits on every row
        self._cache: dict[str, list] = {
            "supplier": db_parties_list("supplier"),
            "customer": db_parties_list("customer"),
            "other":    db_parties_list("other"),
            "expense":  db_parties_list("expense"),
            "bank":     [(a["id"], a["name"]) for a in db_bank_accounts()],
        }

        # Voucher number preview (peek without incrementing)
        counter_key = "last_cp_number" if ptype == "CP" else "last_cr_number"
        conn = get_connection()
        peek = conn.execute(
            "SELECT value FROM settings WHERE key=?", (counter_key,)
        ).fetchone()
        conn.close()
        n = int(peek["value"]) + 1 if peek else 1
        voucher_preview = f"{ptype}-{n:04d}"

        # ── Layout ───────────────────────────────────────────────────────────
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # ── Header card ──────────────────────────────────────────────────────
        hdr = QFrame()
        hdr.setStyleSheet(CARD_STYLE)
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(14, 10, 14, 10)
        hl.setSpacing(12)

        hl.addWidget(QLabel("Voucher:"))
        vno = QLabel(f"<b>{voucher_preview}</b>")
        vno.setStyleSheet("color:#2563eb; font-size:11pt;")
        hl.addWidget(vno)

        hl.addSpacing(12)
        hl.addWidget(QLabel("Date:"))
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setMinimumWidth(120)
        hl.addWidget(self.date_edit)

        hl.addStretch()

        layout.addWidget(hdr)

        # ── Lines table ──────────────────────────────────────────────────────
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["#", "Party Type", "Party Name", "Reference No.", "Amount (PKR)", ""]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(TABLE_STYLE)
        lh = self.table.horizontalHeader()
        lh.setStretchLastSection(False)
        lh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        lh.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        lh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        lh.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        lh.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        lh.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(1, 128)
        self.table.setColumnWidth(3, 160)
        self.table.setColumnWidth(4, 160)
        self.table.setColumnWidth(5, 56)
        self.table.verticalHeader().setDefaultSectionSize(38)
        layout.addWidget(self.table, stretch=1)

        # ── Add line button ───────────────────────────────────────────────────
        add_row = QHBoxLayout()
        btn_add = QPushButton("+ Add Line")
        btn_add.setStyleSheet(BTN_SECONDARY)
        btn_add.clicked.connect(self._add_row)
        add_row.addWidget(btn_add)
        add_row.addStretch()
        layout.addLayout(add_row)

        # ── Footer ───────────────────────────────────────────────────────────
        foot = QHBoxLayout()
        self._total_lbl = QLabel("Total: PKR 0")
        self._total_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self._total_lbl.setStyleSheet("color:#1d4ed8;")
        foot.addWidget(self._total_lbl)
        foot.addStretch()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet(BTN_SECONDARY)
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("Save  [F9]")
        btn_save.setStyleSheet(BTN_PRIMARY)
        btn_save.clicked.connect(self._save)
        QShortcut(QKeySequence("F9"), self).activated.connect(self._save)
        foot.addWidget(btn_cancel)
        foot.addWidget(btn_save)
        layout.addLayout(foot)

        # Internal state: (type_combo, name_combo, amount_spin) per row
        self._rows: list[tuple] = []

        self._add_row()   # start with one empty line
        # CR defaults to Customer as the most common receipt scenario
        if ptype == "CR" and self._rows:
            tc, nc, _, _ = self._rows[0]
            tc.setCurrentIndex(1)  # Customer is index 1
            self._refresh_names(tc, nc)

    # ── Row helpers ───────────────────────────────────────────────────────────

    def _add_row(self):
        r = self.table.rowCount()
        self.table.insertRow(r)

        num = QTableWidgetItem(str(r + 1))
        num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        num.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self.table.setItem(r, 0, num)

        type_combo = QComboBox()
        for label, key in self._PARTY_LABELS:
            type_combo.addItem(label, key)

        name_combo = QComboBox()

        ref_edit = QLineEdit()
        ref_edit.setPlaceholderText("Optional")
        ref_edit.returnPressed.connect(lambda re=ref_edit: re.focusNextChild())

        amount_spin = _AmountSpinBox()
        amount_spin.setRange(0.01, 99_999_999)
        amount_spin.setDecimals(0)
        amount_spin.setSingleStep(1000)
        amount_spin.setGroupSeparatorShown(True)
        amount_spin.setValue(0)
        amount_spin.valueChanged.connect(self._update_total)
        amount_spin.new_row_requested.connect(self._add_row)

        rem_btn = QPushButton("✕")
        rem_btn.setStyleSheet(
            "QPushButton{background:#fee2e2;color:#dc2626;border:none;"
            "border-radius:4px;padding:2px 10px;font-size:11pt;font-weight:bold;}"
            "QPushButton:hover{background:#fecaca;}"
        )

        self.table.setCellWidget(r, 1, type_combo)
        self.table.setCellWidget(r, 2, name_combo)
        self.table.setCellWidget(r, 3, ref_edit)
        self.table.setCellWidget(r, 4, amount_spin)
        self.table.setCellWidget(r, 5, rem_btn)

        self._rows.append((type_combo, name_combo, ref_edit, amount_spin))

        # Use widget identity in closures — avoids stale index captures
        type_combo.currentIndexChanged.connect(
            lambda _: self._refresh_names(type_combo, name_combo)
        )
        rem_btn.clicked.connect(lambda: self._remove_row(type_combo))

        self._refresh_names(type_combo, name_combo)

    def _refresh_names(self, type_combo: QComboBox, name_combo: QComboBox):
        ptype   = type_combo.currentData()
        parties = self._cache.get(ptype, [])
        name_combo.blockSignals(True)
        name_combo.clear()
        if ptype == "bank":
            if parties:
                name_combo.addItem("— Select Bank Account —", None)
                for pid, pname in parties:
                    name_combo.addItem(pname, pid)
            else:
                name_combo.addItem("— No accounts (add in Settings) —", None)
        elif ptype == "expense":
            lbl = "Category"
            if parties:
                name_combo.addItem("— Select Category —", None)
                for p in parties:
                    name_combo.addItem(p["name"], p["id"])
            else:
                name_combo.addItem("— No categories found —", None)
        else:
            lbl = {"supplier": "Supplier", "customer": "Customer", "other": "Party"}[ptype]
            if parties:
                name_combo.addItem(f"— Select {lbl} —", None)
                for p in parties:
                    name_combo.addItem(p["name"], p["id"])
            else:
                name_combo.addItem(f"— No {lbl.lower()}s found —", None)
        name_combo.blockSignals(False)

    def _remove_row(self, type_combo: QComboBox):
        if len(self._rows) <= 1:
            QMessageBox.information(self, "Info", "At least one line is required.")
            return
        idx = next(
            (i for i, (tc, _, _, _) in enumerate(self._rows) if tc is type_combo), -1
        )
        if idx == -1:
            return
        for r in range(self.table.rowCount()):
            if self.table.cellWidget(r, 1) is type_combo:
                self.table.removeRow(r)
                break
        self._rows.pop(idx)
        for i in range(self.table.rowCount()):
            item = self.table.item(i, 0)
            if item:
                item.setText(str(i + 1))
        self._update_total()

    def _update_total(self):
        total = sum(s.value() for _, _, _, s in self._rows)
        self._total_lbl.setText(f"Total: PKR {fmt_pkr(total)}")

    # ── Save ─────────────────────────────────────────────────────────────────

    def _save(self):
        date_str = self.date_edit.date().toString("dd/MM/yyyy")
        lines: list = []
        for i, (tc, nc, ref_edit, spin) in enumerate(self._rows):
            party_id = nc.currentData()
            amount   = spin.value()
            reference = ref_edit.text().strip()
            if party_id is None:
                QMessageBox.warning(
                    self, "Validation", f"Row {i + 1}: please select a party."
                )
                return
            if amount <= 0:
                QMessageBox.warning(
                    self, "Validation",
                    f"Row {i + 1}: amount must be greater than zero."
                )
                return
            lines.append((tc.currentData(), party_id, amount, reference))

        try:
            self._voucher = db_save_multi_cp_cr(self._ptype, date_str, lines)
        except Exception as ex:
            QMessageBox.critical(self, "Error", f"Failed to save: {ex}")
            return
        self.accept()

    def get_voucher(self) -> str:
        return self._voucher or ""


# Legacy aliases kept so any external reference still resolves.
CashReceiptDialog = MultiLineCpCrDialog
CashPaymentDialog = MultiLineCpCrDialog


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
    # Income account — used as the Cr side when recording supplier incentives.
    inc = db_income_account("Incentives Income")
    if inc:
        combo.addItem("Incentives Income", {"type": "income", "id": inc["id"]})
    conn = get_connection()
    suppliers = conn.execute(
        "SELECT id, name FROM suppliers WHERE id != 0 ORDER BY name"
    ).fetchall()
    customers = conn.execute(
        "SELECT id, name FROM customers WHERE type='credit' ORDER BY name"
    ).fetchall()
    try:
        categories = conn.execute(
            "SELECT id, name FROM expense_categories ORDER BY name"
        ).fetchall()
    except Exception:
        categories = []
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
    if categories:
        idx = combo.count()
        combo.addItem("── Expenses ──", None)
        combo.model().item(idx).setEnabled(False)
        for r in categories:
            combo.addItem(r["name"], {"type": "expense", "id": r["id"]})


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
        self.notes_edit.returnPressed.connect(lambda: self.notes_edit.focusNextChild())
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
        self.dr_spin.lineEdit().returnPressed.connect(
            lambda: self.dr_spin.focusNextChild())
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
        self.cr_spin.lineEdit().returnPressed.connect(
            lambda: self.cr_spin.focusNextChild())
        cr_col.addWidget(self.cr_spin)
        grid.addLayout(cr_col)

        layout.addWidget(grid_frame)

        # Examples help text
        eg = QLabel(
            "Examples:  Bank transfer to supplier → Dr Supplier / Cr Bank\n"
            "           Customer pays via bank   → Dr Bank / Cr Customer\n"
            "           Supplier rebate (cash)   → Dr Cash / Cr Supplier\n"
            "           Supplier incentive       → Dr Supplier / Cr Incentives Income\n"
            "           Expense paid from bank   → Dr Rent / Cr Bank"
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
        self.from_date = QDateEdit(QDate.currentDate().addMonths(-1))
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

        # ── Export buttons (top-right, consistent with all other reports) ─────
        btn_pdf = QPushButton("Export PDF")
        btn_pdf.setStyleSheet(BTN_SECONDARY)
        btn_pdf.clicked.connect(self._export_pdf_clicked)
        cl.addWidget(btn_pdf)
        btn_csv = QPushButton("Export CSV")
        btn_csv.setStyleSheet(BTN_SECONDARY)
        btn_csv.clicked.connect(self._export_csv_clicked)
        cl.addWidget(btn_csv)

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

    # ── Export ────────────────────────────────────────────────────────────────
    def _export_pdf_clicked(self):
        if self.bank_combo.currentData() is None:
            QMessageBox.information(self, "Export", "Select a bank account first.")
            return
        _do_export_pdf(self)

    def _export_csv_clicked(self):
        if self.bank_combo.currentData() is None:
            QMessageBox.information(self, "Export", "Select a bank account first.")
            return
        _do_export_csv(self)

    def _export_payload(self):
        headers, rows = _table_to_rows(self.table)
        acc_name = self.bank_combo.currentText()
        name = f"Bank_Ledger_{acc_name}"
        title = f"Bank Ledger — {acc_name}"
        bal = self._closing_lbl.text().strip()
        if bal:
            title += f"   ({bal})"
        # Right-align Debit (IN), Credit (OUT), Balance columns.
        return (name, title, headers, rows, {3, 4, 5})

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


# ── JV List Widget ────────────────────────────────────────────────────────────

class JVListWidget(QWidget):
    """Shows all journal vouchers (new + legacy) with filter bar and actions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(10)

        # ── Filter bar ────────────────────────────────────────────────────────
        ctrl = QFrame()
        ctrl.setStyleSheet(CARD_STYLE)
        cl = QHBoxLayout(ctrl)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(8)

        cl.addWidget(QLabel("From:"))
        self.from_date = QDateEdit(QDate.currentDate().addMonths(-1))
        self.from_date.setDisplayFormat("dd/MM/yyyy")
        self.from_date.setCalendarPopup(True)
        cl.addWidget(self.from_date)

        cl.addWidget(QLabel("To:"))
        self.to_date = QDateEdit(QDate.currentDate())
        self.to_date.setDisplayFormat("dd/MM/yyyy")
        self.to_date.setCalendarPopup(True)
        cl.addWidget(self.to_date)

        btn_today = QPushButton("Today")
        btn_today.setStyleSheet(BTN_SECONDARY)
        btn_today.clicked.connect(self._set_today)
        cl.addWidget(btn_today)

        btn_yesterday = QPushButton("Yesterday")
        btn_yesterday.setStyleSheet(BTN_SECONDARY)
        btn_yesterday.clicked.connect(self._set_yesterday)
        cl.addWidget(btn_yesterday)

        btn_search = QPushButton("Search")
        btn_search.setStyleSheet(BTN_SECONDARY)
        btn_search.clicked.connect(self._load)
        cl.addWidget(btn_search)

        btn_all = QPushButton("All")
        btn_all.setStyleSheet(BTN_SECONDARY)
        btn_all.clicked.connect(self._load_all)
        cl.addWidget(btn_all)

        cl.addStretch()

        self.btn_new = QPushButton("+ New JV")
        self.btn_new.setStyleSheet(BTN_PRIMARY)
        self.btn_new.clicked.connect(self._new_jv)
        cl.addWidget(self.btn_new)

        layout.addWidget(ctrl)

        # ── Table ─────────────────────────────────────────────────────────────
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["JV Number", "Date", "Lines", "Total Dr (PKR)"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet(TABLE_STYLE)
        self.table.doubleClicked.connect(self._edit_row)
        layout.addWidget(self.table, stretch=1)

        # ── Footer ────────────────────────────────────────────────────────────
        footer = QHBoxLayout()
        self._footer_lbl = QLabel("")
        self._footer_lbl.setStyleSheet("color:#475569; font-size:9pt;")
        footer.addWidget(self._footer_lbl)
        footer.addStretch()
        layout.addLayout(footer)

        self._load_all()

    def _set_today(self):
        today = QDate.currentDate()
        self.from_date.setDate(today)
        self.to_date.setDate(today)
        self._load()

    def _set_yesterday(self):
        yesterday = QDate.currentDate().addDays(-1)
        self.from_date.setDate(yesterday)
        self.to_date.setDate(yesterday)
        self._load()

    def _load(self):
        from_iso = self.from_date.date().toString("yyyy-MM-dd")
        to_iso   = self.to_date.date().toString("yyyy-MM-dd")
        self._populate(db_load_journal_vouchers_list(from_iso, to_iso))

    def _load_all(self):
        self._populate(db_load_journal_vouchers_list())

    def _populate(self, rows):
        self._rows = rows
        self.table.setRowCount(0)
        LEGACY_BG = QBrush(QColor("#fef9c3"))
        for r in rows:
            i = self.table.rowCount()
            self.table.insertRow(i)
            lc = str(r["line_count"]) if r["line_count"] != "—" else "—"
            cells = [
                r["jv_number"],
                r["date"],
                lc,
                fmt_pkr(r["total_dr"]),
            ]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == 3:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                if r["is_legacy"]:
                    item.setBackground(LEGACY_BG)
                    item.setForeground(QBrush(QColor("#92400e")))
                self.table.setItem(i, col, item)
        count = len(rows)
        total = sum(r["total_dr"] for r in rows)
        self._footer_lbl.setText(
            f"{count} voucher{'s' if count != 1 else ''}  •  "
            f"Total Dr: Rs. {fmt_pkr(total)}"
        )

    def _new_jv(self):
        from edit_vouchers import JVFormDialog
        dlg = JVFormDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load_all()

    def _edit_row(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._rows):
            return
        r = self._rows[row]
        from edit_vouchers import JVEditDialog
        dlg = JVEditDialog(r["id"], r["is_legacy"], r.get("jv_number", ""), self)
        result = dlg.exec()
        if result in (QDialog.DialogCode.Accepted,):
            self._load_all()

    def refresh(self):
        self._load_all()


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
        self.btn_other = QPushButton("Other Parties")
        self.btn_other.setFixedHeight(32)
        self.btn_bank = QPushButton("Bank")
        self.btn_bank.setFixedHeight(32)
        _style_toggle(self.btn_sup,   True,  "left")
        _style_toggle(self.btn_cust,  False, "mid")
        _style_toggle(self.btn_other, False, "mid")
        _style_toggle(self.btn_bank,  False, "right")
        for _b in (self.btn_sup, self.btn_cust, self.btn_other, self.btn_bank):
            _b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_sup.clicked.connect(lambda: self._set_party_type("supplier"))
        self.btn_cust.clicked.connect(lambda: self._set_party_type("customer"))
        self.btn_other.clicked.connect(lambda: self._set_party_type("other"))
        self.btn_bank.clicked.connect(lambda: self._set_party_type("bank"))
        tl.addWidget(self.btn_sup)
        tl.addWidget(self.btn_cust)
        tl.addWidget(self.btn_other)
        tl.addWidget(self.btn_bank)
        tl.addStretch()
        layout.addWidget(type_card)

        # ── Party controls (hidden when Bank) ─────────────────────────────────
        self.ctrl_card = QFrame()
        self.ctrl_card.setStyleSheet(CARD_STYLE)
        cl = QHBoxLayout(self.ctrl_card)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(10)

        lbl_party = QLabel("Party:")
        lbl_party.setFixedWidth(36)
        cl.addWidget(lbl_party)
        self.party_combo = QComboBox()
        self.party_combo.setMinimumWidth(200)
        self.party_combo.currentIndexChanged.connect(self._on_party_change)
        cl.addWidget(self.party_combo)
        cl.addSpacing(8)
        lbl_from = QLabel("From:")
        lbl_from.setFixedWidth(38)
        cl.addWidget(lbl_from)
        self.from_date = QDateEdit(QDate.currentDate().addMonths(-1))
        self.from_date.setDisplayFormat("dd/MM/yyyy")
        self.from_date.setCalendarPopup(True)
        self.from_date.setMinimumWidth(120)
        cl.addWidget(self.from_date)
        lbl_to = QLabel("To:")
        lbl_to.setFixedWidth(24)
        cl.addWidget(lbl_to)
        self.to_date = QDateEdit(QDate.currentDate())
        self.to_date.setDisplayFormat("dd/MM/yyyy")
        self.to_date.setCalendarPopup(True)
        self.to_date.setMinimumWidth(120)
        cl.addWidget(self.to_date)
        cl.addSpacing(8)
        btn_search = QPushButton("Search")
        btn_search.setStyleSheet(BTN_SECONDARY)
        btn_search.setMinimumWidth(80)
        btn_search.clicked.connect(self._search)
        cl.addWidget(btn_search)
        btn_all = QPushButton("All")
        btn_all.setStyleSheet(BTN_SECONDARY)
        btn_all.setMinimumWidth(60)
        btn_all.clicked.connect(self._show_all)
        cl.addWidget(btn_all)
        cl.addStretch()
        btn_pdf = QPushButton("Export PDF")
        btn_pdf.setStyleSheet(BTN_SECONDARY)
        btn_pdf.setMinimumWidth(100)
        btn_pdf.clicked.connect(self._export_pdf_clicked)
        cl.addWidget(btn_pdf)
        btn_csv = QPushButton("Export CSV")
        btn_csv.setStyleSheet(BTN_SECONDARY)
        btn_csv.setMinimumWidth(100)
        btn_csv.clicked.connect(self._export_csv_clicked)
        cl.addWidget(btn_csv)

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
        _style_toggle(self.btn_sup,   ptype == "supplier", "left")
        _style_toggle(self.btn_cust,  ptype == "customer", "mid")
        _style_toggle(self.btn_other, ptype == "other",    "mid")
        _style_toggle(self.btn_bank,  ptype == "bank",     "right")

        is_bank  = ptype == "bank"
        is_party = not is_bank

        self.ctrl_card.setVisible(is_party)
        self.info_card.setVisible(False)
        self.table.setVisible(is_party)
        self.closing_label.setVisible(is_party)
        self._bank_widget.setVisible(is_bank)

        if is_bank:
            self._bank_widget.refresh()
            QTimer.singleShot(0, self._bank_widget.setFocus)
        else:
            self._load_party_combo()
            QTimer.singleShot(0, self.party_combo.setFocus)

    def _load_party_combo(self):
        self.party_combo.blockSignals(True)
        self.party_combo.clear()
        label = {"supplier": "— Select Supplier —",
                 "other": "— Select Party —"}.get(
                     self._party_type, "— Select Customer —")
        self.party_combo.addItem(label, None)
        for p in db_parties_list(self._party_type):
            self.party_combo.addItem(p["name"], p["id"])
        self.party_combo.blockSignals(False)
        self._party_id   = None
        self._party_name = ""
        self.info_card.setVisible(False)
        self.table.setRowCount(0)
        self.closing_label.setText("")

    # ── Party selection ───────────────────────────────────────────────────────

    def _on_party_change(self):
        pid = self.party_combo.currentData()
        if pid is None:
            self._party_id = None
            self.info_card.setVisible(False)
            self.table.setRowCount(0)
            self.closing_label.setText("")
            return
        self._party_id   = pid
        self._party_name = self.party_combo.currentText()
        self._update_info_card()
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

    # ── Export ────────────────────────────────────────────────────────────────
    def _export_pdf_clicked(self):
        if self._party_id is None:
            QMessageBox.information(self, "Export", "Select a party first.")
            return
        _do_export_pdf(self)

    def _export_csv_clicked(self):
        if self._party_id is None:
            QMessageBox.information(self, "Export", "Select a party first.")
            return
        _do_export_csv(self)

    def _export_payload(self):
        headers = ["Date", "Voucher", "Description", "Debit (PKR)", "Credit (PKR)", "Balance (PKR)"]
        rows = [
            [
                e.get("date", ""),
                e.get("voucher", ""),
                e.get("desc", ""),
                fmt_pkr(e["dr"]) if e.get("dr") else "",
                fmt_pkr(e["cr"]) if e.get("cr") else "",
                fmt_pkr(e["balance"]),
            ]
            for e in getattr(self, "_entries_asc", [])
        ]
        ptype_label = {"supplier": "Supplier", "customer": "Customer",
                       "other": "Other_Party"}.get(self._party_type, "Customer")
        name = f"{ptype_label}_Ledger_{self._party_name}"
        title = f"{ptype_label.replace('_', ' ')} Ledger — {self._party_name}"
        bal = self.closing_label.text().strip()
        if bal:
            title += f"   ({bal})"
        return (name, title, headers, rows, {3, 4, 5})

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
            # Check if this is a new-style JV in journal_vouchers first
            from edit_vouchers import JVEditDialog as _JVEditDialog
            conn = get_connection()
            jv_row = conn.execute(
                "SELECT id FROM journal_vouchers WHERE jv_number=?", (voucher,)
            ).fetchone()
            conn.close()
            if jv_row:
                dlg = _JVEditDialog(jv_row["id"], False, voucher, self)
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    self._load_ledger()
            else:
                # Legacy journal_entry
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
                dlg = _JVEditDialog(None, True, voucher, self)
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    self._load_ledger()

        else:
            # SV / PV / SR / PR rows — tell user to go to the relevant page
            QMessageBox.information(self, "Edit Voucher",
                f"To edit {voucher}, open the "
                f"{'Sales' if voucher.startswith('SV') else 'Purchase'} page "
                f"and use the ✏ Edit button.")

    def _populate_table(self, entries):
        self._entries_asc = list(entries)   # kept in ascending order for export
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.table.setWordWrap(True)
        HEADER_BG = QBrush(QColor("#f0f9ff"))
        DR_COLOR  = QColor("#dc2626")
        CR_COLOR  = QColor("#16a34a")
        BAL_FONT  = QFont("Segoe UI", 10, QFont.Weight.Bold)
        closing_balance = entries[-1]["balance"] if entries else 0.0
        for e in reversed(entries):   # display newest first
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
        self.table.resizeRowsToContents()
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
        dlg = MultiLineCpCrDialog("CR", self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        voucher = dlg.get_voucher()
        self._load_ledger()
        if hasattr(self, "_bank_widget"):
            self._bank_widget.refresh()
        QMessageBox.information(self, "Saved", f"Cash receipt {voucher} saved.")

    def _standalone_cp(self):
        dlg = MultiLineCpCrDialog("CP", self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        voucher = dlg.get_voucher()
        self._load_ledger()
        if hasattr(self, "_bank_widget"):
            self._bank_widget.refresh()
        QMessageBox.information(self, "Saved", f"Cash payment {voucher} saved.")

    def _standalone_jv(self):
        from edit_vouchers import JVFormDialog
        dlg = JVFormDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        # Refresh whichever view is active
        if self._party_type == "bank":
            self._bank_widget.refresh()
        else:
            self._load_ledger()
