from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QLineEdit, QDoubleSpinBox, QHeaderView,
    QMessageBox, QWidget, QSizePolicy
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


def db_fixed_assets() -> list:
    conn = get_connection()
    rows = conn.execute("SELECT id, name, value FROM fixed_assets ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def db_save_fixed_asset(name, value, asset_id=None):
    conn = get_connection()
    if asset_id is None:
        conn.execute("INSERT INTO fixed_assets (name, value) VALUES (?, ?)", (name, value))
    else:
        conn.execute("UPDATE fixed_assets SET name=?, value=? WHERE id=?", (name, value, asset_id))
    conn.commit()
    conn.close()


def db_delete_fixed_asset(asset_id):
    conn = get_connection()
    conn.execute("DELETE FROM fixed_assets WHERE id=?", (asset_id,))
    conn.commit()
    conn.close()


class _AssetDialog(QDialog):
    def __init__(self, parent=None, asset=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Fixed Asset" if asset else "Add Fixed Asset")
        self.setMinimumWidth(340)
        self.setModal(True)
        self._asset = asset

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        lbl_name = QLabel("Asset Name")
        lbl_name.setFont(QFont("Segoe UI", 10))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Laptop")
        self.name_edit.setMinimumHeight(32)
        self.name_edit.textChanged.connect(self._title_case)
        if asset:
            self.name_edit.setText(asset["name"])

        lbl_value = QLabel("Value (PKR)")
        lbl_value.setFont(QFont("Segoe UI", 10))
        self.value_spin = QDoubleSpinBox()
        self.value_spin.setRange(0, 999_999_999)
        self.value_spin.setDecimals(0)
        self.value_spin.setGroupSeparatorShown(True)
        self.value_spin.setMinimumHeight(32)
        if asset:
            self.value_spin.setValue(asset["value"])

        layout.addWidget(lbl_name)
        layout.addWidget(self.name_edit)
        layout.addWidget(lbl_value)
        layout.addWidget(self.value_spin)

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

    def _title_case(self, text):
        self.name_edit.blockSignals(True)
        cursor = self.name_edit.cursorPosition()
        self.name_edit.setText(text.title())
        self.name_edit.setCursorPosition(cursor)
        self.name_edit.blockSignals(False)

    def _save(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Asset name is required.")
            return
        value = self.value_spin.value()
        asset_id = self._asset["id"] if self._asset else None
        db_save_fixed_asset(name, value, asset_id)
        self.accept()


class FixedAssetsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fixed Assets")
        self.setMinimumSize(600, 420)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        title_row = QHBoxLayout()
        title_lbl = QLabel("Fixed Assets")
        title_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title_row.addWidget(title_lbl)
        title_row.addStretch()
        btn_add = QPushButton("+ Add Fixed Asset")
        btn_add.setStyleSheet(BTN_PRIMARY)
        btn_add.clicked.connect(self._add)
        title_row.addWidget(btn_add)
        layout.addLayout(title_row)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Asset Name", "Value (PKR)", "Edit", "Delete"])
        self.table.setStyleSheet(TABLE_STYLE)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table)

        self.total_lbl = QLabel()
        self.total_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.total_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.total_lbl)

        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        btn_close = QPushButton("Close")
        btn_close.setStyleSheet(BTN_SECONDARY)
        btn_close.clicked.connect(self.accept)
        bottom_row.addWidget(btn_close)
        layout.addLayout(bottom_row)

        self._load()

    def _load(self):
        assets = db_fixed_assets()
        self.table.setRowCount(0)
        total = 0.0
        for asset in assets:
            row = self.table.rowCount()
            self.table.insertRow(row)

            name_item = QTableWidgetItem(asset["name"])
            self.table.setItem(row, 0, name_item)

            value_item = QTableWidgetItem(f"Rs. {asset['value']:,.0f}")
            value_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 1, value_item)

            btn_edit = QPushButton("Edit")
            btn_edit.setStyleSheet(BTN_EDIT)
            btn_edit.clicked.connect(lambda checked, a=asset: self._edit(a))
            cell_edit = QWidget()
            edit_layout = QHBoxLayout(cell_edit)
            edit_layout.addWidget(btn_edit)
            edit_layout.setContentsMargins(4, 2, 4, 2)
            self.table.setCellWidget(row, 2, cell_edit)

            btn_del = QPushButton("Delete")
            btn_del.setStyleSheet(BTN_DANGER)
            btn_del.clicked.connect(lambda checked, a=asset: self._delete(a))
            cell_del = QWidget()
            del_layout = QHBoxLayout(cell_del)
            del_layout.addWidget(btn_del)
            del_layout.setContentsMargins(4, 2, 4, 2)
            self.table.setCellWidget(row, 3, cell_del)

            total += asset["value"]

        self.total_lbl.setText(f"Total Fixed Assets: Rs. {total:,.0f}")

    def _add(self):
        dlg = _AssetDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load()

    def _edit(self, asset):
        dlg = _AssetDialog(self, asset=asset)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load()

    def _delete(self, asset):
        reply = QMessageBox.question(
            self, "Confirm Delete",
            "Delete this fixed asset?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            db_delete_fixed_asset(asset["id"])
            self._load()
