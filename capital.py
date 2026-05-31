"""
capital.py — Capital Accounts Module for United Mobile EPOS
Handles investor capital tracking with contributions and withdrawals.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QDialog, QFormLayout,
    QLineEdit, QComboBox, QDateEdit, QTextEdit, QMessageBox,
    QHeaderView, QFrame, QSplitter, QAbstractItemView
)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QFont, QColor
import sqlite3
from datetime import date


# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────

def fmt(amount):
    """Format number as Rs. with commas."""
    return f"Rs. {amount:,.0f}"


def title_case(text):
    return text.title()


def get_db():
    conn = sqlite3.connect("united_mobile.db")
    conn.row_factory = sqlite3.Row
    return conn


def next_voucher(conn, key, prefix):
    cur = conn.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cur.fetchone()
    num = int(row["value"]) + 1 if row else 1
    conn.execute(
        "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=?",
        (key, str(num).zfill(4), str(num).zfill(4))
    )
    return f"{prefix}-{str(num).zfill(4)}"


# ─────────────────────────────────────────────
#  DB Migration — called from database.py
# ─────────────────────────────────────────────

def migrate_capital_tables(conn):
    """Create capital tables if they don't exist. Safe to call multiple times."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS capital_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            contact TEXT,
            opening_balance REAL DEFAULT 0,
            created_date TEXT
        );

        CREATE TABLE IF NOT EXISTS capital_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ca_number TEXT UNIQUE NOT NULL,
            capital_account_id INTEGER REFERENCES capital_accounts(id),
            date TEXT NOT NULL,
            amount REAL NOT NULL,
            type TEXT CHECK(type IN ('contribution','withdrawal','opening','adjustment')),
            payment_method TEXT CHECK(payment_method IN ('cash','bank')),
            bank_account_id INTEGER REFERENCES bank_accounts(id),
            notes TEXT
        );
    """)
    conn.commit()


# ─────────────────────────────────────────────
#  Balance Calculations
# ─────────────────────────────────────────────

def get_capital_balance(conn, capital_account_id):
    """Current balance = opening_balance + contributions - withdrawals + adjustments."""
    row = conn.execute(
        "SELECT opening_balance FROM capital_accounts WHERE id=?",
        (capital_account_id,)
    ).fetchone()
    if not row:
        return 0
    balance = row["opening_balance"]

    txns = conn.execute(
        "SELECT type, amount FROM capital_transactions WHERE capital_account_id=?",
        (capital_account_id,)
    ).fetchall()
    for t in txns:
        if t["type"] in ("contribution", "opening"):
            balance += t["amount"]
        elif t["type"] == "withdrawal":
            balance -= t["amount"]
        elif t["type"] == "adjustment":
            balance += t["amount"]   # can be negative for debit adjustments
    return balance


def get_total_capital(conn):
    accounts = conn.execute("SELECT id FROM capital_accounts").fetchall()
    return sum(get_capital_balance(conn, a["id"]) for a in accounts)


# ─────────────────────────────────────────────
#  Add / Edit Investor Dialog
# ─────────────────────────────────────────────

class InvestorDialog(QDialog):
    def __init__(self, parent=None, investor=None):
        super().__init__(parent)
        self.investor = investor
        self.setWindowTitle("Add Investor" if not investor else "Edit Investor")
        self.setMinimumWidth(380)
        self.setModal(True)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(10)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Investor name")
        self.name_edit.textChanged.connect(
            lambda t: self.name_edit.setText(title_case(t)) if t != title_case(t) else None
        )

        self.contact_edit = QLineEdit()
        self.contact_edit.setPlaceholderText("03XXXXXXXXX (optional)")
        self.contact_edit.setMaxLength(11)

        self.opening_edit = QLineEdit()
        self.opening_edit.setPlaceholderText("0")

        form.addRow("Name *", self.name_edit)
        form.addRow("Contact", self.contact_edit)
        form.addRow("Opening Balance", self.opening_edit)

        if self.investor:
            self.name_edit.setText(self.investor["name"])
            self.contact_edit.setText(self.investor["contact"] or "")
            self.opening_edit.setText(str(self.investor["opening_balance"] or 0))
            self.opening_edit.setEnabled(False)  # don't allow changing opening balance after creation

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.setFixedHeight(36)
        save_btn.setStyleSheet("background:#1a7f5a;color:white;border-radius:4px;font-weight:bold;")
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(36)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _save(self):
        name = self.name_edit.text().strip()
        contact = self.contact_edit.text().strip()
        opening_text = self.opening_edit.text().strip() or "0"

        if not name:
            QMessageBox.warning(self, "Validation", "Name is required.")
            return

        if contact and (len(contact) != 11 or not contact.startswith("03")):
            QMessageBox.warning(self, "Validation", "Contact must be 11 digits starting with 03.")
            return

        try:
            opening = float(opening_text.replace(",", ""))
        except ValueError:
            QMessageBox.warning(self, "Validation", "Opening balance must be a number.")
            return

        self.result_data = {
            "name": name,
            "contact": contact or None,
            "opening_balance": opening
        }
        self.accept()


# ─────────────────────────────────────────────
#  Contribution / Withdrawal Dialog
# ─────────────────────────────────────────────

class TransactionDialog(QDialog):
    def __init__(self, parent=None, txn_type="contribution", investor_name=""):
        super().__init__(parent)
        self.txn_type = txn_type
        self.setWindowTitle(
            f"New Contribution — {investor_name}" if txn_type == "contribution"
            else f"New Withdrawal — {investor_name}"
        )
        self.setMinimumWidth(400)
        self.setModal(True)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        # Type label
        label = QLabel(
            "💰 Recording Capital Contribution" if self.txn_type == "contribution"
            else "💸 Recording Capital Withdrawal"
        )
        label.setStyleSheet(
            "color:#1a7f5a;font-weight:bold;font-size:13px;" if self.txn_type == "contribution"
            else "color:#c0392b;font-weight:bold;font-size:13px;"
        )
        layout.addWidget(label)

        form = QFormLayout()
        form.setSpacing(10)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("dd/MM/yyyy")

        self.amount_edit = QLineEdit()
        self.amount_edit.setPlaceholderText("Amount in PKR")

        self.method_combo = QComboBox()
        self.method_combo.addItems(["Cash", "Bank"])
        self.method_combo.currentTextChanged.connect(self._toggle_bank)

        self.bank_combo = QComboBox()
        self.bank_combo.setEnabled(False)
        self._load_banks()

        self.notes_edit = QLineEdit()
        self.notes_edit.setPlaceholderText("Optional notes")

        form.addRow("Date *", self.date_edit)
        form.addRow("Amount *", self.amount_edit)
        form.addRow("Payment Method *", self.method_combo)
        form.addRow("Bank Account", self.bank_combo)
        form.addRow("Notes", self.notes_edit)

        layout.addLayout(form)

        # Cash book effect note
        effect_text = (
            "Effect: Cash IN (investor brings cash) or Bank IN (investor transfers)"
            if self.txn_type == "contribution"
            else "Effect: Cash OUT (cash given back) or Bank OUT (bank transfer out)"
        )
        note = QLabel(effect_text)
        note.setStyleSheet("color:#666;font-size:11px;")
        note.setWordWrap(True)
        layout.addWidget(note)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.setFixedHeight(36)
        color = "#1a7f5a" if self.txn_type == "contribution" else "#c0392b"
        save_btn.setStyleSheet(f"background:{color};color:white;border-radius:4px;font-weight:bold;")
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(36)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _load_banks(self):
        self.bank_combo.clear()
        self.bank_combo.addItem("Select bank...", None)
        conn = get_db()
        banks = conn.execute("SELECT id, name FROM bank_accounts").fetchall()
        conn.close()
        for b in banks:
            self.bank_combo.addItem(b["name"], b["id"])

    def _toggle_bank(self, text):
        self.bank_combo.setEnabled(text == "Bank")

    def _save(self):
        try:
            amount = float(self.amount_edit.text().strip().replace(",", ""))
            if amount <= 0:
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "Validation", "Please enter a valid positive amount.")
            return

        method = self.method_combo.currentText().lower()
        bank_id = self.bank_combo.currentData()

        if method == "bank" and not bank_id:
            QMessageBox.warning(self, "Validation", "Please select a bank account.")
            return

        d = self.date_edit.date()
        date_str = f"{d.year()}-{str(d.month()).zfill(2)}-{str(d.day()).zfill(2)}"

        self.result_data = {
            "date": date_str,
            "amount": amount,
            "payment_method": method,
            "bank_account_id": bank_id if method == "bank" else None,
            "notes": self.notes_edit.text().strip() or None
        }
        self.accept()


# ─────────────────────────────────────────────
#  Opening Stock Adjustment Dialog
# ─────────────────────────────────────────────

class OpeningStockAdjustDialog(QDialog):
    """
    One-time wizard to zero out the dummy 'Opening Stock' supplier
    by splitting its balance equally across capital investors.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Adjust Opening Stock Against Capital")
        self.setMinimumWidth(500)
        self.setModal(True)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        title = QLabel("Opening Stock → Capital Adjustment")
        title.setStyleSheet("font-size:15px;font-weight:bold;color:#1a3a5c;")
        layout.addWidget(title)

        info = QLabel(
            "This will post a journal entry to the Opening Stock supplier, reducing its "
            "balance to zero. Capital account balances are not affected."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#555;font-size:12px;")
        layout.addWidget(info)

        conn = get_db()

        # Find opening stock supplier
        supplier = conn.execute(
            "SELECT id, name, opening_balance FROM suppliers WHERE name LIKE '%OPENING STOCK%' OR name LIKE '%Opening Stock%'"
        ).fetchone()

        # Calculate supplier current balance
        self.supplier_id = None
        self.stock_balance = 0

        if supplier:
            self.supplier_id = supplier["id"]
            ob = supplier["opening_balance"] or 0
            # Add purchases made under this supplier
            pv_total = conn.execute(
                "SELECT COALESCE(SUM(total_amount),0) as t FROM purchase_vouchers WHERE supplier_id=?",
                (supplier["id"],)
            ).fetchone()["t"]
            # Subtract payments made
            payments = conn.execute(
                "SELECT COALESCE(SUM(amount),0) as t FROM payments WHERE party_type='supplier' AND party_id=?",
                (supplier["id"],)
            ).fetchone()["t"]
            self.stock_balance = ob + pv_total - payments

        # Load investors and recover each one's TRUE intended contribution.
        # Intended = opening_balance + any prior adjustment/opening-inventory
        # transactions that were already posted by a previous run of this dialog.
        # This prevents double-counting if the dialog is re-opened.
        investors = conn.execute(
            "SELECT id, name, opening_balance FROM capital_accounts ORDER BY id"
        ).fetchall()

        self.investors = list(investors)
        self.intended = {}     # inv_id → intended total contribution
        for inv in self.investors:
            inv_id = inv["id"]
            ob = float(inv["opening_balance"] or 0)
            prev = float(conn.execute(
                """SELECT COALESCE(SUM(amount), 0) FROM capital_transactions
                   WHERE capital_account_id = ?
                     AND (type = 'adjustment'
                          OR notes LIKE 'Opening inventory%')""",
                (inv_id,)
            ).fetchone()[0])
            self.intended[inv_id] = ob + prev

        conn.close()

        total_intended = sum(self.intended.values())

        # Proportional splits based on intended contributions
        self.investor_splits = []
        for inv in self.investors:
            intended = self.intended[inv["id"]]
            stock_share = (
                self.stock_balance * intended / total_intended
                if total_intended > 0 else 0
            )
            cash_remaining = max(0.0, intended - stock_share)
            self.investor_splits.append((inv, stock_share, cash_remaining))

        # Summary
        frame = QFrame()
        frame.setStyleSheet("background:#f0f7ff;border:1px solid #b0d0f0;border-radius:6px;padding:10px;")
        fl = QVBoxLayout(frame)

        if supplier:
            fl.addWidget(QLabel(f"Opening Stock balance: <b>{fmt(self.stock_balance)}</b>"))
            fl.addWidget(QLabel(""))
            fl.addWidget(QLabel("<b>Capital breakdown after adjustment:</b>"))
            for inv, stock_share, cash_remaining in self.investor_splits:
                fl.addWidget(QLabel(
                    f"  {inv['name']}:  "
                    f"Stock {fmt(stock_share)}  +  Cash {fmt(cash_remaining)}  "
                    f"=  {fmt(stock_share + cash_remaining)}"
                ))
            fl.addWidget(QLabel(""))
            fl.addWidget(QLabel(
                "Each investor's opening balance is reset to zero and re-entered as\n"
                "two transactions (stock share + cash remainder). Totals stay the same.\n"
                "The Opening Stock supplier is zeroed via a journal entry."
            ))
        else:
            fl.addWidget(QLabel("⚠️ No 'Opening Stock' supplier found."))

        layout.addWidget(frame)

        if not supplier:
            layout.addWidget(QLabel("Cannot proceed — no Opening Stock supplier found."))
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.reject)
            layout.addWidget(close_btn)
            return

        btn_row = QHBoxLayout()
        confirm_btn = QPushButton("✓ Apply Adjustment")
        confirm_btn.setFixedHeight(36)
        confirm_btn.setStyleSheet("background:#1a7f5a;color:white;border-radius:4px;font-weight:bold;")
        confirm_btn.clicked.connect(self._apply)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(36)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(confirm_btn)
        layout.addLayout(btn_row)

    def _apply(self):
        conn = get_db()
        today = date.today().strftime("%Y-%m-%d")
        try:
            # Recalculate live supplier balance at apply time
            s_ob = float(conn.execute(
                "SELECT COALESCE(opening_balance,0) FROM suppliers WHERE id=?",
                (self.supplier_id,)
            ).fetchone()[0])
            pv_total = float(conn.execute(
                "SELECT COALESCE(SUM(total_amount),0) FROM purchase_vouchers WHERE supplier_id=?",
                (self.supplier_id,)
            ).fetchone()[0])
            cp = float(conn.execute(
                "SELECT COALESCE(SUM(amount),0) FROM payments "
                "WHERE party_type='supplier' AND party_id=? AND type='CP'",
                (self.supplier_id,)
            ).fetchone()[0])
            cr = float(conn.execute(
                "SELECT COALESCE(SUM(amount),0) FROM payments "
                "WHERE party_type='supplier' AND party_id=? AND type='CR'",
                (self.supplier_id,)
            ).fetchone()[0])
            jv_dr = float(conn.execute(
                "SELECT COALESCE(SUM(amount),0) FROM journal_entries "
                "WHERE party_type='supplier' AND party_id=? AND type='debit'",
                (self.supplier_id,)
            ).fetchone()[0])
            jv_cr = float(conn.execute(
                "SELECT COALESCE(SUM(amount),0) FROM journal_entries "
                "WHERE party_type='supplier' AND party_id=? AND type='credit'",
                (self.supplier_id,)
            ).fetchone()[0])
            balance = s_ob + pv_total + cr - cp + jv_dr - jv_cr

            if balance <= 0:
                QMessageBox.information(self, "Already Done",
                    "Opening Stock balance is already zero — no adjustment needed.")
                conn.close()
                self.accept()
                return

            # ── Capital: clean up any prior runs, then re-enter as two transactions ──
            # Using self.intended (recovered in _build) ensures the total never
            # changes regardless of how many times this dialog has been applied.
            for inv, stock_share, cash_remaining in self.investor_splits:
                inv_id = inv["id"]

                # Remove transactions previously posted by this dialog so we
                # never double-count on a second run.
                conn.execute(
                    """DELETE FROM capital_transactions
                       WHERE capital_account_id = ?
                         AND (type = 'adjustment'
                              OR notes LIKE 'Opening inventory%')""",
                    (inv_id,)
                )

                # Reset opening_balance to zero; the transactions below carry
                # the full intended amount.
                conn.execute(
                    "UPDATE capital_accounts SET opening_balance = 0 WHERE id=?",
                    (inv_id,)
                )

                if stock_share > 0.005:
                    ca_num = next_voucher(conn, "last_ca_number", "CA")
                    conn.execute(
                        "INSERT INTO capital_transactions "
                        "(ca_number, capital_account_id, date, amount, type, payment_method, notes) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (ca_num, inv_id, today, round(stock_share, 2),
                         "opening", None, "Opening inventory — stock contribution")
                    )
                if cash_remaining > 0.005:
                    ca_num = next_voucher(conn, "last_ca_number", "CA")
                    conn.execute(
                        "INSERT INTO capital_transactions "
                        "(ca_number, capital_account_id, date, amount, type, payment_method, notes) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (ca_num, inv_id, today, round(cash_remaining, 2),
                         "contribution", None, "Opening inventory — cash contribution")
                    )

            # ── Supplier: zero via journal entry (visible in supplier ledger) ──
            jv_num = next_voucher(conn, "last_jv_number", "JV")
            conn.execute(
                "INSERT INTO journal_entries "
                "(jv_number, party_type, party_id, date, amount, type, notes) "
                "VALUES (?,?,?,?,?,?,?)",
                (jv_num, "supplier", self.supplier_id, today, balance, "credit",
                 "Opening stock written off — transferred to investor capital accounts")
            )

            conn.commit()
            QMessageBox.information(self, "Done",
                f"Adjustment complete.\n\n"
                f"• Opening Stock supplier zeroed (JV {jv_num})\n"
                f"• Each investor's capital re-entered as stock share + cash remainder\n"
                f"• Total capital for each investor is unchanged")
            self.accept()
        except Exception as e:
            conn.rollback()
            QMessageBox.critical(self, "Error", str(e))
        finally:
            conn.close()


# ─────────────────────────────────────────────
#  Main Capital Page
# ─────────────────────────────────────────────

class CapitalPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()
        self._load_investors()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # ── Header ──
        header_row = QHBoxLayout()
        title = QLabel("Capital Accounts")
        title.setStyleSheet("font-size:20px;font-weight:bold;color:#1a3a5c;")
        header_row.addWidget(title)
        header_row.addStretch()

        self._adj_btn = QPushButton("Adjust Opening Stock")
        self._adj_btn.setFixedHeight(34)
        self._adj_btn.setStyleSheet("background:#e67e22;color:white;border-radius:4px;padding:0 12px;font-weight:bold;")
        self._adj_btn.clicked.connect(self._opening_stock_adjust)
        self._adj_btn.setToolTip("One-time: zero out dummy Opening Stock supplier balance")
        adj_btn = self._adj_btn

        add_btn = QPushButton("+ Add Investor")
        add_btn.setFixedHeight(34)
        add_btn.setStyleSheet("background:#1a7f5a;color:white;border-radius:4px;padding:0 12px;font-weight:bold;")
        add_btn.clicked.connect(self._add_investor)

        header_row.addWidget(adj_btn)
        header_row.addWidget(add_btn)
        layout.addLayout(header_row)

        # ── Total Capital Summary ──
        self.total_label = QLabel("Total Capital: Rs. 0")
        self.total_label.setStyleSheet(
            "background:#1a3a5c;color:white;padding:10px 16px;"
            "border-radius:6px;font-size:14px;font-weight:bold;"
        )
        layout.addWidget(self.total_label)

        # ── Splitter: investor list (left) | transactions (right) ──
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: investor list
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        inv_label = QLabel("Investors")
        inv_label.setStyleSheet("font-weight:bold;font-size:13px;color:#333;")
        left_layout.addWidget(inv_label)

        self.investor_table = QTableWidget()
        self.investor_table.setColumnCount(3)
        self.investor_table.setHorizontalHeaderLabels(["Name", "Contact", "Balance"])
        self.investor_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.investor_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.investor_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.investor_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.investor_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.investor_table.verticalHeader().setVisible(False)
        self.investor_table.setAlternatingRowColors(True)
        self.investor_table.itemSelectionChanged.connect(self._investor_selected)
        left_layout.addWidget(self.investor_table)

        # Action buttons below investor list
        inv_btn_row = QHBoxLayout()
        self.contrib_btn = QPushButton("+ Contribution")
        self.contrib_btn.setFixedHeight(32)
        self.contrib_btn.setEnabled(False)
        self.contrib_btn.setStyleSheet("background:#1a7f5a;color:white;border-radius:4px;")
        self.contrib_btn.clicked.connect(self._add_contribution)

        self.withdraw_btn = QPushButton("- Withdrawal")
        self.withdraw_btn.setFixedHeight(32)
        self.withdraw_btn.setEnabled(False)
        self.withdraw_btn.setStyleSheet("background:#c0392b;color:white;border-radius:4px;")
        self.withdraw_btn.clicked.connect(self._add_withdrawal)

        self.edit_btn = QPushButton("✎ Edit")
        self.edit_btn.setFixedHeight(32)
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self._edit_investor)

        self.delete_btn = QPushButton("🗑 Remove")
        self.delete_btn.setFixedHeight(32)
        self.delete_btn.setEnabled(False)
        self.delete_btn.setStyleSheet("color:#c0392b;")
        self.delete_btn.clicked.connect(self._delete_investor)

        inv_btn_row.addWidget(self.contrib_btn)
        inv_btn_row.addWidget(self.withdraw_btn)
        inv_btn_row.addWidget(self.edit_btn)
        inv_btn_row.addWidget(self.delete_btn)
        left_layout.addLayout(inv_btn_row)

        # Right: transaction history
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self.txn_header = QLabel("Select an investor to view transactions")
        self.txn_header.setStyleSheet("font-weight:bold;font-size:13px;color:#333;")
        right_layout.addWidget(self.txn_header)

        self.txn_table = QTableWidget()
        self.txn_table.setColumnCount(5)
        self.txn_table.setHorizontalHeaderLabels(["Voucher", "Date", "Type", "Amount", "Notes"])
        self.txn_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.txn_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.txn_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.txn_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.txn_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.txn_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.txn_table.verticalHeader().setVisible(False)
        self.txn_table.setAlternatingRowColors(True)
        right_layout.addWidget(self.txn_table)

        # Running balance label
        self.balance_label = QLabel("")
        self.balance_label.setStyleSheet(
            "background:#f0f7ff;border:1px solid #b0d0f0;border-radius:4px;"
            "padding:8px 12px;font-weight:bold;font-size:13px;"
        )
        right_layout.addWidget(self.balance_label)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([380, 620])
        layout.addWidget(splitter)

        self.selected_investor_id = None

    # ── Data Loading ──

    def _load_investors(self):
        conn = get_db()
        investors = conn.execute("SELECT * FROM capital_accounts ORDER BY name").fetchall()
        total = 0

        self.investor_table.setRowCount(len(investors))
        self._investor_ids = []

        for i, inv in enumerate(investors):
            bal = get_capital_balance(conn, inv["id"])
            total += bal
            self._investor_ids.append(inv["id"])

            name_item = QTableWidgetItem(inv["name"])
            contact_item = QTableWidgetItem(inv["contact"] or "—")
            bal_item = QTableWidgetItem(fmt(bal))
            bal_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            bal_item.setForeground(QColor("#1a7f5a") if bal >= 0 else QColor("#c0392b"))

            self.investor_table.setItem(i, 0, name_item)
            self.investor_table.setItem(i, 1, contact_item)
            self.investor_table.setItem(i, 2, bal_item)

        # Check whether the Opening Stock supplier still has a balance.
        # If already zero, disable the adjust button permanently.
        supplier = conn.execute(
            "SELECT id, opening_balance FROM suppliers "
            "WHERE UPPER(name) LIKE '%OPENING STOCK%'"
        ).fetchone()
        conn.close()

        if supplier is not None:
            sup_id = supplier["id"]
            conn2 = get_db()
            pv_total = float(conn2.execute(
                "SELECT COALESCE(SUM(total_amount),0) FROM purchase_vouchers WHERE supplier_id=?",
                (sup_id,)
            ).fetchone()[0])
            cp = float(conn2.execute(
                "SELECT COALESCE(SUM(amount),0) FROM payments "
                "WHERE party_type='supplier' AND party_id=? AND type='CP'",
                (sup_id,)
            ).fetchone()[0])
            jv_cr = float(conn2.execute(
                "SELECT COALESCE(SUM(amount),0) FROM journal_entries "
                "WHERE party_type='supplier' AND party_id=? AND type='credit'",
                (sup_id,)
            ).fetchone()[0])
            conn2.close()
            ob = float(supplier["opening_balance"] or 0)
            sup_balance = ob + pv_total - cp - jv_cr
        else:
            sup_balance = 0.0

        already_done = abs(sup_balance) < 0.01
        self._adj_btn.setEnabled(not already_done)
        if already_done:
            self._adj_btn.setText("Opening Stock: Already Adjusted")
            self._adj_btn.setStyleSheet(
                "background:#95a5a6;color:white;border-radius:4px;"
                "padding:0 12px;font-weight:bold;"
            )
            self._adj_btn.setToolTip("Opening Stock supplier balance is already zero.")
        else:
            self._adj_btn.setText("Adjust Opening Stock")
            self._adj_btn.setStyleSheet(
                "background:#e67e22;color:white;border-radius:4px;"
                "padding:0 12px;font-weight:bold;"
            )
            self._adj_btn.setToolTip("One-time: zero out dummy Opening Stock supplier balance")

        self.total_label.setText(f"Total Capital: {fmt(total)}")

    def _investor_selected(self):
        rows = self.investor_table.selectedItems()
        if not rows:
            self.selected_investor_id = None
            self.contrib_btn.setEnabled(False)
            self.withdraw_btn.setEnabled(False)
            self.edit_btn.setEnabled(False)
            self.delete_btn.setEnabled(False)
            return

        row = self.investor_table.currentRow()
        self.selected_investor_id = self._investor_ids[row]
        name = self.investor_table.item(row, 0).text()
        self.txn_header.setText(f"Transactions — {name}")

        self.contrib_btn.setEnabled(True)
        self.withdraw_btn.setEnabled(True)
        self.edit_btn.setEnabled(True)
        self.delete_btn.setEnabled(True)

        self._load_transactions(self.selected_investor_id)

    def _load_transactions(self, capital_account_id):
        conn = get_db()
        inv = conn.execute(
            "SELECT opening_balance FROM capital_accounts WHERE id=?",
            (capital_account_id,)
        ).fetchone()
        opening = inv["opening_balance"] or 0

        txns = conn.execute(
            """SELECT ct.*, ba.name as bank_name
               FROM capital_transactions ct
               LEFT JOIN bank_accounts ba ON ba.id = ct.bank_account_id
               WHERE ct.capital_account_id=?
               ORDER BY ct.date, ct.id""",
            (capital_account_id,)
        ).fetchall()
        conn.close()

        rows = []
        # Opening balance row
        if opening != 0:
            rows.append(("OB", "—", "Opening", opening, "Opening balance"))

        for t in txns:
            d = t["date"]
            try:
                parts = d.split("-")
                d = f"{parts[2]}/{parts[1]}/{parts[0]}"
            except Exception:
                pass
            signed = t["amount"] if t["type"] in ("contribution","opening","adjustment") else -t["amount"]
            rows.append((t["ca_number"], d, t["type"].title(), signed, t["notes"] or ""))

        self.txn_table.setRowCount(len(rows))
        running = 0
        for i, (vno, dt, typ, amt, notes) in enumerate(rows):
            running += amt
            vitem = QTableWidgetItem(vno)
            ditem = QTableWidgetItem(dt)
            titem = QTableWidgetItem(typ)
            aitem = QTableWidgetItem(fmt(abs(amt)))
            aitem.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if amt >= 0:
                aitem.setForeground(QColor("#1a7f5a"))
            else:
                aitem.setForeground(QColor("#c0392b"))
                titem.setForeground(QColor("#c0392b"))
            nitem = QTableWidgetItem(notes)

            self.txn_table.setItem(i, 0, vitem)
            self.txn_table.setItem(i, 1, ditem)
            self.txn_table.setItem(i, 2, titem)
            self.txn_table.setItem(i, 3, aitem)
            self.txn_table.setItem(i, 4, nitem)

        self.balance_label.setText(f"Current Balance: {fmt(running)}")

    # ── Actions ──

    def _add_investor(self):
        dlg = InvestorDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            d = dlg.result_data
            conn = get_db()
            migrate_capital_tables(conn)
            conn.execute(
                "INSERT INTO capital_accounts(name,contact,opening_balance,created_date) VALUES(?,?,?,?)",
                (d["name"], d["contact"], d["opening_balance"], date.today().isoformat())
            )
            conn.commit()
            conn.close()
            self._load_investors()

    def _edit_investor(self):
        if not self.selected_investor_id:
            return
        conn = get_db()
        inv = conn.execute(
            "SELECT * FROM capital_accounts WHERE id=?", (self.selected_investor_id,)
        ).fetchone()
        conn.close()

        dlg = InvestorDialog(self, investor=inv)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            d = dlg.result_data
            conn = get_db()
            conn.execute(
                "UPDATE capital_accounts SET name=?, contact=? WHERE id=?",
                (d["name"], d["contact"], self.selected_investor_id)
            )
            conn.commit()
            conn.close()
            self._load_investors()

    def _delete_investor(self):
        if not self.selected_investor_id:
            return
        conn = get_db()
        bal = get_capital_balance(conn, self.selected_investor_id)
        txn_count = conn.execute(
            "SELECT COUNT(*) as c FROM capital_transactions WHERE capital_account_id=?",
            (self.selected_investor_id,)
        ).fetchone()["c"]
        conn.close()

        if bal != 0:
            QMessageBox.warning(self, "Cannot Remove",
                f"Investor balance must be zero before removal.\nCurrent balance: {fmt(bal)}")
            return

        if txn_count > 0:
            reply = QMessageBox.question(self, "Confirm",
                "This investor has transactions. Are you sure you want to remove them?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return

        conn = get_db()
        conn.execute("DELETE FROM capital_transactions WHERE capital_account_id=?",
                     (self.selected_investor_id,))
        conn.execute("DELETE FROM capital_accounts WHERE id=?", (self.selected_investor_id,))
        conn.commit()
        conn.close()
        self.selected_investor_id = None
        self.txn_table.setRowCount(0)
        self.balance_label.setText("")
        self._load_investors()

    def _add_contribution(self):
        if not self.selected_investor_id:
            return
        row = self.investor_table.currentRow()
        name = self.investor_table.item(row, 0).text()
        dlg = TransactionDialog(self, "contribution", name)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._save_transaction("contribution", dlg.result_data)

    def _add_withdrawal(self):
        if not self.selected_investor_id:
            return
        row = self.investor_table.currentRow()
        name = self.investor_table.item(row, 0).text()
        dlg = TransactionDialog(self, "withdrawal", name)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._save_transaction("withdrawal", dlg.result_data)

    def _save_transaction(self, txn_type, data):
        conn = get_db()
        try:
            ca_num = next_voucher(conn, "last_ca_number", "CA")
            conn.execute(
                """INSERT INTO capital_transactions
                   (ca_number, capital_account_id, date, amount, type, payment_method, bank_account_id, notes)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (ca_num, self.selected_investor_id, data["date"], data["amount"],
                 txn_type, data["payment_method"], data["bank_account_id"], data["notes"])
            )

            # ── Affect cash/bank balance ──
            method = data["payment_method"]
            amount = data["amount"]

            if txn_type == "contribution":
                # Investor puts money IN → cash or bank goes UP
                if method == "cash":
                    # Increase cash opening balance (simplest approach — add to settings cash)
                    self._adjust_cash(conn, +amount)
                else:
                    self._adjust_bank(conn, data["bank_account_id"], +amount)
            else:
                # Withdrawal → cash or bank goes DOWN
                if method == "cash":
                    self._adjust_cash(conn, -amount)
                else:
                    self._adjust_bank(conn, data["bank_account_id"], -amount)

            conn.commit()
            self._load_investors()
            self._load_transactions(self.selected_investor_id)
        except Exception as e:
            conn.rollback()
            QMessageBox.critical(self, "Error", str(e))
        finally:
            conn.close()

    def _adjust_cash(self, conn, delta):
        """Adjust cash opening balance in settings by delta."""
        row = conn.execute("SELECT value FROM settings WHERE key='cash_opening_balance'").fetchone()
        current = float(row["value"]) if row else 0
        new_val = current + delta
        conn.execute(
            "INSERT INTO settings(key,value) VALUES('cash_opening_balance',?) "
            "ON CONFLICT(key) DO UPDATE SET value=?",
            (str(new_val), str(new_val))
        )

    def _adjust_bank(self, conn, bank_id, delta):
        """Adjust bank account opening balance by delta."""
        conn.execute(
            "UPDATE bank_accounts SET opening_balance = opening_balance + ? WHERE id=?",
            (delta, bank_id)
        )

    def _opening_stock_adjust(self):
        conn = get_db()
        investors = conn.execute("SELECT id FROM capital_accounts").fetchall()
        conn.close()
        if not investors:
            QMessageBox.warning(self, "No Investors",
                "Please add investors first before running the Opening Stock adjustment.")
            return
        dlg = OpeningStockAdjustDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load_investors()
