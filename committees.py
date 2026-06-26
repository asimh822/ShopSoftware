from datetime import date

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QLineEdit, QDoubleSpinBox, QSpinBox,
    QComboBox, QHeaderView, QMessageBox, QWidget, QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from database import get_connection

BTN_PRIMARY = """
    QPushButton { background:#2563eb; color:white; border:none;
        border-radius:5px; padding:6px 18px; font-size:10pt; }
    QPushButton:hover { background:#1d4ed8; }
"""
BTN_SECONDARY = """
    QPushButton { background:#f1f5f9; color:#334155;
        border:1px solid #cbd5e1; border-radius:5px; padding:6px 14px; font-size:10pt; }
    QPushButton:hover { background:#e2e8f0; }
"""
BTN_DANGER = """
    QPushButton { background:#fee2e2; color:#dc2626; border:none;
        border-radius:4px; padding:3px 10px; font-size:9pt; }
    QPushButton:hover { background:#fecaca; }
"""
BTN_EDIT = """
    QPushButton { background:#dbeafe; color:#1d4ed8; border:none;
        border-radius:4px; padding:3px 10px; font-size:9pt; }
    QPushButton:hover { background:#bfdbfe; }
"""
TABLE_STYLE = """
    QTableWidget { background:#ffffff; border:1px solid #e2e8f0;
        border-radius:6px; gridline-color:#f1f5f9; font-size:10pt; }
    QTableWidget::item { padding:6px 10px; }
    QTableWidget::item:selected { background:#dbeafe; color:#1e40af; }
    QTableWidget::item:alternate { background:#f8fafc; }
    QHeaderView::section { background:#f8fafc; color:#475569; font-weight:bold; font-size:9pt;
        border:none; border-bottom:1px solid #e2e8f0; padding:8px 10px; }
"""

_MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def auto_months_paid(start_date_str: str) -> int:
    # "YYYY-MM" → number of complete months from start to today
    today = date.today()
    try:
        year, month = int(start_date_str[:4]), int(start_date_str[5:7])
    except (ValueError, IndexError):
        return 0
    months = (today.year - year) * 12 + (today.month - month)
    return max(0, months)


def committee_remaining(c: dict) -> float:
    remaining = c["total_amount"] - c["monthly_installment"] * c["months_paid"]
    return max(0.0, remaining)


def db_committees() -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name, total_amount, monthly_installment, start_date, months_paid "
        "FROM committees ORDER BY name"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def db_save_committee(name, total_amount, monthly_installment, start_date, months_paid, committee_id=None):
    conn = get_connection()
    if committee_id is None:
        conn.execute(
            "INSERT INTO committees (name, total_amount, monthly_installment, start_date, months_paid) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, total_amount, monthly_installment, start_date, months_paid)
        )
    else:
        conn.execute(
            "UPDATE committees SET name=?, total_amount=?, monthly_installment=?, "
            "start_date=?, months_paid=? WHERE id=?",
            (name, total_amount, monthly_installment, start_date, months_paid, committee_id)
        )
    conn.commit()
    conn.close()


def db_delete_committee(committee_id):
    conn = get_connection()
    conn.execute("DELETE FROM committees WHERE id=?", (committee_id,))
    conn.commit()
    conn.close()


class _CommitteeDialog(QDialog):
    def __init__(self, parent=None, committee=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Committee" if committee else "Add Committee")
        self.setMinimumWidth(400)
        self.setModal(True)
        self._committee = committee

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        # Name
        lbl_name = QLabel("Name")
        lbl_name.setFont(QFont("Segoe UI", 10))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Gold Committee")
        self.name_edit.setMinimumHeight(32)
        self.name_edit.textChanged.connect(self._title_case)

        # Total Amount
        lbl_total = QLabel("Total Amount (PKR)")
        lbl_total.setFont(QFont("Segoe UI", 10))
        self.total_spin = QDoubleSpinBox()
        self.total_spin.setRange(0, 99_999_999)
        self.total_spin.setDecimals(0)
        self.total_spin.setGroupSeparatorShown(True)
        self.total_spin.setMinimumHeight(32)

        # Monthly Installment
        lbl_monthly = QLabel("Monthly Installment (PKR)")
        lbl_monthly.setFont(QFont("Segoe UI", 10))
        self.monthly_spin = QDoubleSpinBox()
        self.monthly_spin.setRange(0, 9_999_999)
        self.monthly_spin.setDecimals(0)
        self.monthly_spin.setGroupSeparatorShown(True)
        self.monthly_spin.setMinimumHeight(32)

        # Start Date — month combo + year spinbox side by side
        lbl_start = QLabel("Start Date")
        lbl_start.setFont(QFont("Segoe UI", 10))
        start_row = QHBoxLayout()
        self.month_combo = QComboBox()
        self.month_combo.addItems(_MONTH_NAMES)
        self.month_combo.setMinimumHeight(32)
        self.year_spin = QSpinBox()
        self.year_spin.setRange(2020, 2035)
        self.year_spin.setMinimumHeight(32)
        today = date.today()
        self.month_combo.setCurrentIndex(today.month - 1)
        self.year_spin.setValue(today.year)
        start_row.addWidget(self.month_combo)
        start_row.addWidget(self.year_spin)

        # Months Paid + Auto-Calculate button
        lbl_months = QLabel("Months Paid")
        lbl_months.setFont(QFont("Segoe UI", 10))
        months_row = QHBoxLayout()
        self.months_spin = QSpinBox()
        self.months_spin.setRange(0, 999)
        self.months_spin.setMinimumHeight(32)
        btn_auto = QPushButton("Auto-Calculate")
        btn_auto.setStyleSheet(BTN_SECONDARY)
        btn_auto.clicked.connect(self._auto_months)
        months_row.addWidget(self.months_spin)
        months_row.addWidget(btn_auto)

        # Live remaining label
        self.remaining_lbl = QLabel()
        self.remaining_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.remaining_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)

        layout.addWidget(lbl_name)
        layout.addWidget(self.name_edit)
        layout.addWidget(lbl_total)
        layout.addWidget(self.total_spin)
        layout.addWidget(lbl_monthly)
        layout.addWidget(self.monthly_spin)
        layout.addWidget(lbl_start)
        layout.addLayout(start_row)
        layout.addWidget(lbl_months)
        layout.addLayout(months_row)
        layout.addWidget(self.remaining_lbl)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet(BTN_SECONDARY)
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("Save")
        btn_save.setStyleSheet(BTN_PRIMARY)
        btn_save.clicked.connect(self._save)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_save)
        layout.addLayout(btn_row)

        # Connect signals for live remaining update
        self.total_spin.valueChanged.connect(self._update_remaining)
        self.monthly_spin.valueChanged.connect(self._update_remaining)
        self.months_spin.valueChanged.connect(self._update_remaining)

        if committee:
            self.name_edit.setText(committee["name"])
            self.total_spin.setValue(committee["total_amount"])
            self.monthly_spin.setValue(committee["monthly_installment"])
            # Parse stored "YYYY-MM"
            try:
                yr, mo = int(committee["start_date"][:4]), int(committee["start_date"][5:7])
                self.month_combo.setCurrentIndex(mo - 1)
                self.year_spin.setValue(yr)
            except (ValueError, IndexError):
                pass
            self.months_spin.setValue(committee["months_paid"])

        self._update_remaining()

    def _title_case(self, text):
        self.name_edit.blockSignals(True)
        cursor = self.name_edit.cursorPosition()
        self.name_edit.setText(text.title())
        self.name_edit.setCursorPosition(cursor)
        self.name_edit.blockSignals(False)

    def _get_start_date_str(self) -> str:
        month = self.month_combo.currentIndex() + 1
        year = self.year_spin.value()
        return f"{year:04d}-{month:02d}"

    def _auto_months(self):
        start = self._get_start_date_str()
        self.months_spin.setValue(auto_months_paid(start))

    def _update_remaining(self):
        total = self.total_spin.value()
        monthly = self.monthly_spin.value()
        months = self.months_spin.value()
        remaining = max(0.0, total - monthly * months)
        self.remaining_lbl.setText(f"Remaining: Rs. {remaining:,.0f}")

    def _save(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Name is required.")
            return
        total = self.total_spin.value()
        monthly = self.monthly_spin.value()
        start = self._get_start_date_str()
        months = self.months_spin.value()
        committee_id = self._committee["id"] if self._committee else None
        db_save_committee(name, total, monthly, start, months, committee_id)
        self.accept()


class CommitteesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Committees (Comety)")
        self.setMinimumSize(860, 440)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        title_row = QHBoxLayout()
        title_row.addStretch()
        btn_add = QPushButton("+ Add Committee")
        btn_add.setStyleSheet(BTN_PRIMARY)
        btn_add.clicked.connect(self._add)
        title_row.addWidget(btn_add)
        layout.addLayout(title_row)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Name", "Total (PKR)", "Monthly (PKR)", "Start",
            "Months Paid", "Remaining (PKR)", "Edit", "Delete"
        ])
        self.table.setStyleSheet(TABLE_STYLE)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in [1, 2, 3, 4, 5, 6, 7]:
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table)

        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        btn_close = QPushButton("Close")
        btn_close.setStyleSheet(BTN_SECONDARY)
        btn_close.clicked.connect(self.accept)
        bottom_row.addWidget(btn_close)
        layout.addLayout(bottom_row)

        self._load()

    def _load(self):
        committees = db_committees()
        self.table.setRowCount(0)
        for c in committees:
            row = self.table.rowCount()
            self.table.insertRow(row)

            self.table.setItem(row, 0, QTableWidgetItem(c["name"]))

            total_item = QTableWidgetItem(f"Rs. {c['total_amount']:,.0f}")
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 1, total_item)

            monthly_item = QTableWidgetItem(f"Rs. {c['monthly_installment']:,.0f}")
            monthly_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 2, monthly_item)

            # Display start date as "MM/YYYY"
            try:
                yr, mo = c["start_date"][:4], c["start_date"][5:7]
                start_display = f"{mo}/{yr}"
            except (IndexError, TypeError):
                start_display = c["start_date"]
            self.table.setItem(row, 3, QTableWidgetItem(start_display))

            months_item = QTableWidgetItem(str(c["months_paid"]))
            months_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 4, months_item)

            remaining = committee_remaining(c)
            rem_item = QTableWidgetItem(f"Rs. {remaining:,.0f}")
            rem_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 5, rem_item)

            btn_edit = QPushButton("Edit")
            btn_edit.setStyleSheet(BTN_EDIT)
            btn_edit.clicked.connect(lambda checked, com=c: self._edit(com))
            cell_edit = QWidget()
            edit_layout = QHBoxLayout(cell_edit)
            edit_layout.addWidget(btn_edit)
            edit_layout.setContentsMargins(4, 2, 4, 2)
            self.table.setCellWidget(row, 6, cell_edit)

            btn_del = QPushButton("Delete")
            btn_del.setStyleSheet(BTN_DANGER)
            btn_del.clicked.connect(lambda checked, com=c: self._delete(com))
            cell_del = QWidget()
            del_layout = QHBoxLayout(cell_del)
            del_layout.addWidget(btn_del)
            del_layout.setContentsMargins(4, 2, 4, 2)
            self.table.setCellWidget(row, 7, cell_del)

    def _add(self):
        dlg = _CommitteeDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load()

    def _edit(self, committee):
        dlg = _CommitteeDialog(self, committee=committee)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load()

    def _delete(self, committee):
        reply = QMessageBox.question(
            self, "Confirm Delete",
            "Delete this committee?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            db_delete_committee(committee["id"])
            self._load()
