"""
expenses.py — Expenses module for United Mobile EPOS
Two tabs: Expenses List (with filter/edit/delete/export) and New Expense form.
"""

import csv
from datetime import date as _date

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QComboBox, QDateEdit,
    QHeaderView, QAbstractItemView, QFrame, QLineEdit,
    QMessageBox, QFileDialog, QTabWidget, QDoubleSpinBox,
    QTextEdit, QButtonGroup, QRadioButton, QFormLayout,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QFont, QColor, QBrush

from database import (
    get_connection, db_bank_accounts,
    db_save_expense, db_delete_expense,
    db_expenses, db_expense_by_id,
    EXPENSE_CATEGORIES,
)

# ── Styles ─────────────────────────────────────────────────────────────────────

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
        border-radius:5px; padding:6px 18px; font-size:10pt; }
    QPushButton:hover { background:#1d4ed8; }
    QPushButton:disabled { background:#93c5fd; }
"""
BTN_GREEN = """
    QPushButton { background:#16a34a; color:white; border:none;
        border-radius:5px; padding:8px 32px; font-size:11pt; font-weight:bold; }
    QPushButton:hover { background:#15803d; }
    QPushButton:disabled { background:#86efac; }
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
BTN_EDIT_SMALL = """
    QPushButton { background:#dbeafe; color:#1d4ed8; border:none;
        border-radius:4px; padding:3px 10px; font-size:9pt; }
    QPushButton:hover { background:#bfdbfe; }
"""
BTN_EXPORT = """
    QPushButton { background:#f1f5f9; color:#334155;
        border:1px solid #cbd5e1; border-radius:5px; padding:6px 14px; font-size:10pt; }
    QPushButton:hover { background:#e2e8f0; }
"""
TOGGLE_ON = """
    QPushButton { background:#2563eb; color:white; border:none;
        padding:7px 24px; font-size:10pt; font-weight:bold; }
"""
TOGGLE_OFF = """
    QPushButton { background:#f1f5f9; color:#64748b;
        border:1px solid #cbd5e1; padding:7px 24px; font-size:10pt; }
    QPushButton:hover { background:#e2e8f0; color:#334155; }
"""
CARD_STYLE = (
    "background:#ffffff; border:1px solid #e2e8f0; "
    "border-radius:8px; color:#1e293b;"
)
INPUT_STYLE = (
    "background:#ffffff; color:#1e293b; border:1px solid #cbd5e1; "
    "border-radius:4px; padding:5px 8px; font-size:10pt;"
)
COMBO_STYLE = (
    "QComboBox { background:#ffffff; color:#1e293b; border:1px solid #cbd5e1; "
    "border-radius:4px; padding:5px 8px; font-size:10pt; } "
    "QComboBox QAbstractItemView { background:#ffffff; color:#1e293b; "
    "selection-background-color:#dbeafe; }"
)


def _fmt(val):
    if val is None:
        return "0"
    return f"{float(val):,.0f}"


def _today_qdate() -> QDate:
    t = _date.today()
    return QDate(t.year, t.month, t.day)


def _first_of_month_qdate() -> QDate:
    t = _date.today()
    return QDate(t.year, t.month, 1)


def _qdate_to_str(qd: QDate) -> str:
    return qd.toString("dd/MM/yyyy")


# ── Expenses List Tab ──────────────────────────────────────────────────────────

class ExpensesListTab(QWidget):
    """Shows all expenses with filters, edit/delete actions, and CSV export."""

    def __init__(self, parent_page, parent=None):
        super().__init__(parent)
        self._parent_page = parent_page   # reference to ExpensesPage for edit callback
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # ── Filter bar ────────────────────────────────────────────────────────
        filter_frame = QFrame()
        filter_frame.setStyleSheet(CARD_STYLE)
        filter_frame.setFixedHeight(62)
        fl = QHBoxLayout(filter_frame)
        fl.setContentsMargins(14, 10, 14, 10)
        fl.setSpacing(10)

        fl.addWidget(QLabel("From:"))
        self._from_date = QDateEdit()
        self._from_date.setCalendarPopup(True)
        self._from_date.setDate(_first_of_month_qdate())
        self._from_date.setDisplayFormat("dd/MM/yyyy")
        self._from_date.setFixedWidth(110)
        fl.addWidget(self._from_date)

        fl.addWidget(QLabel("To:"))
        self._to_date = QDateEdit()
        self._to_date.setCalendarPopup(True)
        self._to_date.setDate(_today_qdate())
        self._to_date.setDisplayFormat("dd/MM/yyyy")
        self._to_date.setFixedWidth(110)
        fl.addWidget(self._to_date)

        fl.addWidget(QLabel("Category:"))
        self._cat_filter = QComboBox()
        self._cat_filter.setFixedWidth(140)
        self._cat_filter.setStyleSheet(COMBO_STYLE)
        self._cat_filter.addItem("All Categories", "")
        for cat in EXPENSE_CATEGORIES:
            self._cat_filter.addItem(cat, cat)
        fl.addWidget(self._cat_filter)

        fl.addWidget(QLabel("Search:"))
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Filter by description…")
        self._search_box.setFixedWidth(180)
        self._search_box.setStyleSheet(INPUT_STYLE)
        fl.addWidget(self._search_box)

        apply_btn = QPushButton("Apply")
        apply_btn.setStyleSheet(BTN_PRIMARY)
        apply_btn.setFixedWidth(80)
        apply_btn.clicked.connect(self.refresh)
        fl.addWidget(apply_btn)

        reset_btn = QPushButton("Reset")
        reset_btn.setStyleSheet(BTN_SECONDARY)
        reset_btn.setFixedWidth(70)
        reset_btn.clicked.connect(self._reset_filters)
        fl.addWidget(reset_btn)

        fl.addStretch()

        export_btn = QPushButton("⬇ Export CSV")
        export_btn.setStyleSheet(BTN_EXPORT)
        export_btn.clicked.connect(self._export_csv)
        fl.addWidget(export_btn)

        layout.addWidget(filter_frame)

        # ── Table ─────────────────────────────────────────────────────────────
        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels([
            "Date", "EXP #", "Category", "Description",
            "Amount (Rs.)", "Payment", "Actions",
        ])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Date
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # EXP#
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Category
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)           # Description
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Amount
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # Payment
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)  # Actions
        self._table.setStyleSheet(TABLE_STYLE)
        layout.addWidget(self._table, stretch=1)

        # ── Total bar ─────────────────────────────────────────────────────────
        total_frame = QFrame()
        total_frame.setStyleSheet(CARD_STYLE)
        total_frame.setFixedHeight(44)
        tl = QHBoxLayout(total_frame)
        tl.setContentsMargins(16, 0, 16, 0)
        tl.addStretch()
        self._total_lbl = QLabel("Total Expenses: Rs. 0")
        self._total_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self._total_lbl.setStyleSheet("color:#1e293b;")
        tl.addWidget(self._total_lbl)
        layout.addWidget(total_frame)

    def _reset_filters(self):
        self._from_date.setDate(_first_of_month_qdate())
        self._to_date.setDate(_today_qdate())
        self._cat_filter.setCurrentIndex(0)
        self._search_box.clear()
        self.refresh()

    def refresh(self):
        date_from = _qdate_to_str(self._from_date.date())
        date_to   = _qdate_to_str(self._to_date.date())
        category  = self._cat_filter.currentData() or ""
        search    = self._search_box.text().strip()

        rows = db_expenses(date_from, date_to, category, search)

        self._table.setRowCount(0)
        self._row_ids = []

        for row in rows:
            ri = self._table.rowCount()
            self._table.insertRow(ri)
            self._row_ids.append(row['id'])

            pay_lbl = "Cash"
            if row['payment_method'] == 'bank':
                bn = row.get('bank_name') or 'Bank'
                pay_lbl = f"Bank ({bn})"

            items = [
                row['date'],
                row['expense_number'],
                row['category'],
                row.get('description') or '',
                _fmt(row['amount']),
                pay_lbl,
            ]
            for ci, text in enumerate(items):
                item = QTableWidgetItem(text)
                if ci == 4:  # Amount — right-align
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                self._table.setItem(ri, ci, item)

            # ── Actions cell ──────────────────────────────────────────────────
            act_widget = QWidget()
            act_layout = QHBoxLayout(act_widget)
            act_layout.setContentsMargins(4, 2, 4, 2)
            act_layout.setSpacing(6)

            edit_btn = QPushButton("Edit")
            edit_btn.setStyleSheet(BTN_EDIT_SMALL)
            edit_btn.setFixedWidth(48)
            edit_btn.clicked.connect(lambda _, eid=row['id']: self._on_edit(eid))
            act_layout.addWidget(edit_btn)

            del_btn = QPushButton("Delete")
            del_btn.setStyleSheet(BTN_DANGER_SMALL)
            del_btn.setFixedWidth(56)
            del_btn.clicked.connect(lambda _, eid=row['id']: self._on_delete(eid))
            act_layout.addWidget(del_btn)

            self._table.setCellWidget(ri, 6, act_widget)
            self._table.setRowHeight(ri, 38)

        total = sum(r['amount'] for r in rows)
        self._total_lbl.setText(f"Total Expenses: Rs. {_fmt(total)}")

    def _on_edit(self, expense_id: int):
        """Load expense into the New Expense tab for editing."""
        self._parent_page.load_expense_for_edit(expense_id)

    def _on_delete(self, expense_id: int):
        row = db_expense_by_id(expense_id)
        if not row:
            return
        msg = (
            f"Delete expense {row['expense_number']}?\n\n"
            f"Category: {row['category']}\n"
            f"Amount: Rs. {_fmt(row['amount'])}\n\n"
            f"This will reverse the {"cash" if row['payment_method'] == 'cash' else 'bank'} "
            f"balance effect."
        )
        reply = QMessageBox.question(
            self, "Confirm Delete", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        result = db_delete_expense(expense_id)
        if result['ok']:
            self.refresh()
        else:
            QMessageBox.critical(self, "Error", result['error'])

    def _export_csv(self):
        date_from = _qdate_to_str(self._from_date.date())
        date_to   = _qdate_to_str(self._to_date.date())
        category  = self._cat_filter.currentData() or ""
        search    = self._search_box.text().strip()
        rows = db_expenses(date_from, date_to, category, search)

        if not rows:
            QMessageBox.information(self, "No Data", "No expenses to export.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Expenses CSV",
            f"Expenses_{date_from.replace('/', '')}_{date_to.replace('/', '')}.csv",
            "CSV Files (*.csv)",
        )
        if not path:
            return

        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "EXP #", "Category", "Description",
                             "Amount (Rs.)", "Payment Method", "Bank Account", "Bank Ref"])
            for r in rows:
                writer.writerow([
                    r['date'], r['expense_number'], r['category'],
                    r.get('description') or '',
                    r['amount'],
                    r['payment_method'],
                    r.get('bank_name') or '',
                    r.get('bank_ref') or '',
                ])
        QMessageBox.information(self, "Exported", f"Saved to:\n{path}")


# ── New Expense Tab ────────────────────────────────────────────────────────────

class NewExpenseTab(QWidget):
    """Form to create a new expense or edit an existing one."""

    def __init__(self, on_saved_cb, parent=None):
        super().__init__(parent)
        self._on_saved_cb = on_saved_cb   # called after successful save
        self._edit_id = None              # None = new expense, int = editing
        self._bank_accounts = []
        self._build_ui()
        self._load_bank_accounts()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 24, 40, 24)
        outer.setSpacing(0)

        # ── Mode label ────────────────────────────────────────────────────────
        self._mode_lbl = QLabel("New Expense")
        self._mode_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self._mode_lbl.setStyleSheet("color:#1e293b; margin-bottom:4px;")
        outer.addWidget(self._mode_lbl)

        outer.addSpacing(12)

        # ── Form card ─────────────────────────────────────────────────────────
        card = QFrame()
        card.setStyleSheet(CARD_STYLE)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 24, 28, 24)
        card_layout.setSpacing(16)

        # ── Date ──────────────────────────────────────────────────────────────
        row_date = QHBoxLayout()
        lbl_date = QLabel("Date *")
        lbl_date.setFixedWidth(130)
        lbl_date.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        row_date.addWidget(lbl_date)
        self._date_edit = QDateEdit()
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDate(_today_qdate())
        self._date_edit.setDisplayFormat("dd/MM/yyyy")
        self._date_edit.setFixedWidth(140)
        row_date.addWidget(self._date_edit)
        row_date.addStretch()
        card_layout.addLayout(row_date)

        # ── Category ──────────────────────────────────────────────────────────
        row_cat = QHBoxLayout()
        lbl_cat = QLabel("Category *")
        lbl_cat.setFixedWidth(130)
        lbl_cat.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        row_cat.addWidget(lbl_cat)
        self._cat_combo = QComboBox()
        self._cat_combo.setStyleSheet(COMBO_STYLE)
        self._cat_combo.setFixedWidth(200)
        for cat in EXPENSE_CATEGORIES:
            self._cat_combo.addItem(cat)
        row_cat.addWidget(self._cat_combo)
        row_cat.addStretch()
        card_layout.addLayout(row_cat)

        # ── Description ───────────────────────────────────────────────────────
        row_desc = QHBoxLayout()
        lbl_desc = QLabel("Description")
        lbl_desc.setFixedWidth(130)
        lbl_desc.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        lbl_desc.setAlignment(Qt.AlignmentFlag.AlignTop)
        row_desc.addWidget(lbl_desc)
        self._desc_edit = QLineEdit()
        self._desc_edit.setPlaceholderText("Optional — e.g. salesman name for salary")
        self._desc_edit.setStyleSheet(INPUT_STYLE)
        self._desc_edit.setFixedWidth(360)
        row_desc.addWidget(self._desc_edit)
        row_desc.addStretch()
        card_layout.addLayout(row_desc)

        # ── Amount ────────────────────────────────────────────────────────────
        row_amt = QHBoxLayout()
        lbl_amt = QLabel("Amount (Rs.) *")
        lbl_amt.setFixedWidth(130)
        lbl_amt.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        row_amt.addWidget(lbl_amt)
        self._amount_spin = QDoubleSpinBox()
        self._amount_spin.setRange(0, 99_999_999)
        self._amount_spin.setDecimals(0)
        self._amount_spin.setSingleStep(100)
        self._amount_spin.setGroupSeparatorShown(True)
        self._amount_spin.setFixedWidth(180)
        row_amt.addWidget(self._amount_spin)
        row_amt.addStretch()
        card_layout.addLayout(row_amt)

        # ── Payment Method toggle ─────────────────────────────────────────────
        row_pay = QHBoxLayout()
        lbl_pay = QLabel("Payment *")
        lbl_pay.setFixedWidth(130)
        lbl_pay.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        row_pay.addWidget(lbl_pay)

        self._cash_btn = QPushButton("Cash")
        self._cash_btn.setCheckable(True)
        self._cash_btn.setChecked(True)
        self._cash_btn.setFixedWidth(100)
        self._cash_btn.setStyleSheet(TOGGLE_ON)
        self._cash_btn.clicked.connect(lambda: self._set_payment('cash'))

        self._bank_btn = QPushButton("Bank Transfer")
        self._bank_btn.setCheckable(True)
        self._bank_btn.setFixedWidth(130)
        self._bank_btn.setStyleSheet(TOGGLE_OFF)
        self._bank_btn.clicked.connect(lambda: self._set_payment('bank'))

        row_pay.addWidget(self._cash_btn)
        row_pay.addWidget(self._bank_btn)
        row_pay.addStretch()
        card_layout.addLayout(row_pay)

        # ── Bank details (hidden when Cash selected) ──────────────────────────
        self._bank_details = QFrame()
        self._bank_details.setStyleSheet("background:transparent; border:none;")
        bd_layout = QVBoxLayout(self._bank_details)
        bd_layout.setContentsMargins(130, 0, 0, 0)
        bd_layout.setSpacing(10)

        row_ba = QHBoxLayout()
        lbl_ba = QLabel("Bank Account *")
        lbl_ba.setFixedWidth(130)
        lbl_ba.setFont(QFont("Segoe UI", 10))
        row_ba.addWidget(lbl_ba)
        self._bank_acct_combo = QComboBox()
        self._bank_acct_combo.setStyleSheet(COMBO_STYLE)
        self._bank_acct_combo.setFixedWidth(240)
        row_ba.addWidget(self._bank_acct_combo)
        row_ba.addStretch()
        bd_layout.addLayout(row_ba)

        row_ref = QHBoxLayout()
        lbl_ref = QLabel("Bank Reference")
        lbl_ref.setFixedWidth(130)
        lbl_ref.setFont(QFont("Segoe UI", 10))
        row_ref.addWidget(lbl_ref)
        self._bank_ref_edit = QLineEdit()
        self._bank_ref_edit.setPlaceholderText("Optional reference / transaction ID")
        self._bank_ref_edit.setStyleSheet(INPUT_STYLE)
        self._bank_ref_edit.setFixedWidth(240)
        row_ref.addWidget(self._bank_ref_edit)
        row_ref.addStretch()
        bd_layout.addLayout(row_ref)

        self._bank_details.hide()
        card_layout.addWidget(self._bank_details)

        # ── Separator ─────────────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#e2e8f0;")
        card_layout.addWidget(sep)

        # ── Save / Cancel row ─────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._cancel_btn = QPushButton("Cancel Edit")
        self._cancel_btn.setStyleSheet(BTN_SECONDARY)
        self._cancel_btn.hide()
        self._cancel_btn.clicked.connect(self._cancel_edit)
        btn_row.addWidget(self._cancel_btn)

        self._save_btn = QPushButton("Save Expense")
        self._save_btn.setStyleSheet(BTN_GREEN)
        self._save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self._save_btn)

        card_layout.addLayout(btn_row)

        outer.addWidget(card)
        outer.addStretch()

        self._payment_method = 'cash'

    # ── Payment toggle ─────────────────────────────────────────────────────────
    def _set_payment(self, method: str):
        self._payment_method = method
        if method == 'cash':
            self._cash_btn.setChecked(True)
            self._bank_btn.setChecked(False)
            self._cash_btn.setStyleSheet(TOGGLE_ON)
            self._bank_btn.setStyleSheet(TOGGLE_OFF)
            self._bank_details.hide()
        else:
            self._cash_btn.setChecked(False)
            self._bank_btn.setChecked(True)
            self._cash_btn.setStyleSheet(TOGGLE_OFF)
            self._bank_btn.setStyleSheet(TOGGLE_ON)
            self._bank_details.show()

    # ── Bank accounts ─────────────────────────────────────────────────────────
    def _load_bank_accounts(self):
        self._bank_accounts = db_bank_accounts()
        self._bank_acct_combo.clear()
        if not self._bank_accounts:
            self._bank_acct_combo.addItem("No bank accounts — add in Settings", -1)
        for acct in self._bank_accounts:
            self._bank_acct_combo.addItem(acct['name'], acct['id'])

    # ── Load for editing ──────────────────────────────────────────────────────
    def load_for_edit(self, expense_id: int):
        """Pre-fill the form with an existing expense for editing."""
        self._load_bank_accounts()
        row = db_expense_by_id(expense_id)
        if not row:
            QMessageBox.warning(self, "Not Found", "Expense record not found.")
            return

        self._edit_id = expense_id
        self._mode_lbl.setText(f"Edit Expense — {row['expense_number']}")
        self._save_btn.setText("Update Expense")
        self._cancel_btn.show()

        # Date
        parts = row['date'].split('/')
        if len(parts) == 3:
            self._date_edit.setDate(QDate(int(parts[2]), int(parts[1]), int(parts[0])))

        # Category
        idx = self._cat_combo.findText(row['category'])
        if idx >= 0:
            self._cat_combo.setCurrentIndex(idx)

        # Description & amount
        self._desc_edit.setText(row.get('description') or '')
        self._amount_spin.setValue(float(row['amount'] or 0))

        # Payment method
        pm = row.get('payment_method') or 'cash'
        self._set_payment(pm)

        # Bank account
        if pm == 'bank' and row.get('bank_account_id'):
            for i in range(self._bank_acct_combo.count()):
                if self._bank_acct_combo.itemData(i) == row['bank_account_id']:
                    self._bank_acct_combo.setCurrentIndex(i)
                    break
            self._bank_ref_edit.setText(row.get('bank_ref') or '')

    def _cancel_edit(self):
        self._reset_form()

    def _reset_form(self):
        self._edit_id = None
        self._mode_lbl.setText("New Expense")
        self._save_btn.setText("Save Expense")
        self._cancel_btn.hide()
        self._date_edit.setDate(_today_qdate())
        self._cat_combo.setCurrentIndex(0)
        self._desc_edit.clear()
        self._amount_spin.setValue(0)
        self._set_payment('cash')
        self._bank_ref_edit.clear()
        if self._bank_acct_combo.count():
            self._bank_acct_combo.setCurrentIndex(0)

    # ── Save ──────────────────────────────────────────────────────────────────
    def _on_save(self):
        # ── Validation ────────────────────────────────────────────────────────
        date_str = _qdate_to_str(self._date_edit.date())
        category = self._cat_combo.currentText()
        description = self._desc_edit.text().strip()
        amount = self._amount_spin.value()

        if amount <= 0:
            QMessageBox.warning(self, "Validation", "Amount must be greater than zero.")
            self._amount_spin.setFocus()
            return

        bank_account_id = None
        bank_ref = ''

        if self._payment_method == 'bank':
            if not self._bank_accounts:
                QMessageBox.warning(
                    self, "No Bank Accounts",
                    "No bank accounts configured. Add one in Settings first."
                )
                return
            bank_account_id = self._bank_acct_combo.currentData()
            if not bank_account_id or bank_account_id == -1:
                QMessageBox.warning(self, "Validation", "Select a bank account.")
                return
            bank_ref = self._bank_ref_edit.text().strip()

        result = db_save_expense(
            date_str=date_str,
            category=category,
            description=description,
            amount=amount,
            payment_method=self._payment_method,
            bank_account_id=bank_account_id,
            bank_ref=bank_ref,
            expense_id=self._edit_id,
        )

        if result['ok']:
            verb = "updated" if self._edit_id else "saved"
            QMessageBox.information(
                self, "Success",
                f"Expense {result['expense_number']} {verb} successfully."
            )
            self._reset_form()
            self._on_saved_cb()   # refresh the list tab
        else:
            QMessageBox.critical(self, "Error", result['error'])

    def showEvent(self, event):
        """Reload bank accounts each time the tab is shown (in case user added one)."""
        super().showEvent(event)
        if self._edit_id is None:
            self._load_bank_accounts()


# ── Expenses Page (top-level widget registered in main.py) ────────────────────

class ExpensesPage(QWidget):
    """Main Expenses page — two tabs: Expenses List | New Expense."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:#f1f5f9;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet("""
            QTabWidget::pane {
                border:1px solid #e2e8f0; border-radius:0px; background:#f1f5f9;
            }
            QTabBar::tab {
                background:#f8fafc; color:#64748b;
                border:1px solid #e2e8f0; border-bottom:none;
                border-radius:4px 4px 0 0; padding:8px 24px; margin-right:2px;
                font-size:10pt;
            }
            QTabBar::tab:selected { background:#ffffff; color:#1e40af; font-weight:bold; }
            QTabBar::tab:hover:!selected { background:#f1f5f9; }
        """)

        self._list_tab = ExpensesListTab(parent_page=self)
        self._new_tab  = NewExpenseTab(on_saved_cb=self._after_save)

        self._tabs.addTab(self._list_tab, "Expenses List")
        self._tabs.addTab(self._new_tab,  "New Expense")

        layout.addWidget(self._tabs)

    def _after_save(self):
        """Called by NewExpenseTab after a successful save — refresh the list."""
        self._list_tab.refresh()

    def load_expense_for_edit(self, expense_id: int):
        """Called from the list tab Edit button — switches to New Expense tab in edit mode."""
        self._tabs.setCurrentWidget(self._new_tab)
        self._new_tab.load_for_edit(expense_id)

    def showEvent(self, event):
        """Refresh the list every time the page becomes visible."""
        super().showEvent(event)
        self._list_tab.refresh()
