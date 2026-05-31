import sqlite3
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel,
    QDialog, QFormLayout, QLineEdit, QDoubleSpinBox,
    QComboBox, QDialogButtonBox, QMessageBox, QHeaderView,
    QAbstractItemView,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from database import (
    get_connection,
    db_salesmen, db_save_salesman, db_toggle_salesman, db_delete_salesman,
)
from widgets import SearchableComboBox


def _setup_uppercase_edit(edit):
    """Connect textChanged so the field always stays in UPPERCASE as the user types."""
    def to_upper(text):
        upper = text.upper()
        if text != upper:
            pos = edit.cursorPosition()
            edit.blockSignals(True)
            edit.setText(upper)
            edit.setCursorPosition(pos)
            edit.blockSignals(False)
    edit.textChanged.connect(to_upper)


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


def validate_phone(phone: str) -> bool:
    """Pakistan mobile: exactly 11 digits, starts with 03."""
    return len(phone) == 11 and phone.startswith("03") and phone.isdigit()


# ── Styles ────────────────────────────────────────────────────────────────────

TABLE_STYLE = """
    QTableWidget {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 6px;
        gridline-color: #f1f5f9;
        font-size: 10pt;
    }
    QTableWidget::item { padding: 6px 10px; }
    QTableWidget::item:selected { background: #dbeafe; color: #1e40af; }
    QTableWidget::item:alternate { background: #f8fafc; }
    QHeaderView::section {
        background: #f8fafc; color: #475569; font-weight: bold;
        font-size: 9pt; border: none;
        border-bottom: 1px solid #e2e8f0; padding: 8px 10px;
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
BTN_DANGER = """
    QPushButton { background:#fee2e2; color:#dc2626;
        border:1px solid #fca5a5; border-radius:5px; padding:6px 16px; font-size:10pt; }
    QPushButton:hover { background:#fecaca; }
    QPushButton:disabled { color:#fca5a5; border-color:#fecaca; }
"""
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
    QLabel { color:#334155; }
"""


def fmt_pkr(val):
    if val is None:
        return "0"
    return f"{float(val):,.0f}"


def make_table(headers: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setAlternatingRowColors(True)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    t.horizontalHeader().setStretchLastSection(True)
    t.setStyleSheet(TABLE_STYLE)
    return t


def _toolbar(*buttons) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(8)
    for b in buttons:
        row.addWidget(b)
    row.addStretch()
    return row


# ── DB helpers ────────────────────────────────────────────────────────────────

def db_brands():
    conn = get_connection()
    rows = conn.execute("SELECT id, name FROM brands ORDER BY name").fetchall()
    conn.close()
    return rows


def db_save_brand(name, brand_id=None):
    conn = get_connection()
    if brand_id:
        conn.execute("UPDATE brands SET name=? WHERE id=?", (name, brand_id))
    else:
        conn.execute("INSERT INTO brands (name) VALUES (?)", (name,))
    conn.commit()
    conn.close()


def db_delete_brand(brand_id):
    conn = get_connection()
    conn.execute("DELETE FROM brands WHERE id=?", (brand_id,))
    conn.commit()
    conn.close()


def db_models(brand_filter_id=None):
    conn = get_connection()
    if brand_filter_id:
        rows = conn.execute("""
            SELECT m.id, b.name AS brand_name, m.name, m.reference_price
            FROM models m JOIN brands b ON b.id = m.brand_id
            WHERE m.brand_id = ? ORDER BY b.name, m.name
        """, (brand_filter_id,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT m.id, b.name AS brand_name, m.name, m.reference_price
            FROM models m JOIN brands b ON b.id = m.brand_id
            ORDER BY b.name, m.name
        """).fetchall()
    conn.close()
    return rows


def db_save_model(brand_id, name, ref_price, model_id=None):
    conn = get_connection()
    if model_id:
        conn.execute(
            "UPDATE models SET brand_id=?, name=?, reference_price=? WHERE id=?",
            (brand_id, name, ref_price, model_id),
        )
    else:
        conn.execute(
            "INSERT INTO models (brand_id, name, reference_price) VALUES (?,?,?)",
            (brand_id, name, ref_price),
        )
    conn.commit()
    conn.close()


def db_delete_model(model_id):
    conn = get_connection()
    conn.execute("DELETE FROM models WHERE id=?", (model_id,))
    conn.commit()
    conn.close()


def db_suppliers():
    """Returns all real suppliers. Excludes id=0 (system 'Cash Purchase' record)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name, contact, opening_balance FROM suppliers"
        " WHERE id != 0 ORDER BY name"
    ).fetchall()
    conn.close()
    return rows


def db_save_supplier(name, contact, ob, supplier_id=None):
    conn = get_connection()
    if supplier_id:
        conn.execute(
            "UPDATE suppliers SET name=?, contact=?, opening_balance=? WHERE id=?",
            (name, contact, ob, supplier_id),
        )
    else:
        conn.execute(
            "INSERT INTO suppliers (name, contact, opening_balance) VALUES (?,?,?)",
            (name, contact, ob),
        )
    conn.commit()
    conn.close()


def db_delete_supplier(supplier_id):
    conn = get_connection()
    conn.execute("DELETE FROM suppliers WHERE id=?", (supplier_id,))
    conn.commit()
    conn.close()


def db_customers():
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name, contact, opening_balance FROM customers "
        "WHERE type='credit' ORDER BY name"
    ).fetchall()
    conn.close()
    return rows


def db_save_customer(name, contact, ob, customer_id=None):
    conn = get_connection()
    if customer_id:
        conn.execute(
            "UPDATE customers SET name=?, contact=?, opening_balance=? WHERE id=?",
            (name, contact, ob, customer_id),
        )
    else:
        conn.execute(
            "INSERT INTO customers (name, contact, type, opening_balance) VALUES (?,?,?,?)",
            (name, contact, "credit", ob),
        )
    conn.commit()
    conn.close()


def db_delete_customer(customer_id):
    conn = get_connection()
    conn.execute("DELETE FROM customers WHERE id=?", (customer_id,))
    conn.commit()
    conn.close()


# ── Dialogs ───────────────────────────────────────────────────────────────────

class BrandDialog(QDialog):
    def __init__(self, parent=None, name=""):
        super().__init__(parent)
        self.setWindowTitle("Brand")
        self.setFixedWidth(320)
        self.setStyleSheet(FORM_INPUT_STYLE)
        form = QFormLayout(self)
        form.setSpacing(12)
        form.setContentsMargins(20, 20, 20, 20)

        self.name_edit = QLineEdit(name.upper() if name else "")
        self.name_edit.setPlaceholderText("e.g. SAMSUNG")
        _setup_uppercase_edit(self.name_edit)
        form.addRow("Brand Name:", self.name_edit)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def _accept(self):
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Validation", "Brand name is required.")
            return
        self.accept()

    def get_data(self):
        return self.name_edit.text().strip().upper()


class ModelDialog(QDialog):
    def __init__(self, parent=None, brand_id=None, name="", ref_price=0.0):
        super().__init__(parent)
        self.setWindowTitle("Model")
        self.setFixedWidth(380)
        self.setStyleSheet(FORM_INPUT_STYLE)
        form = QFormLayout(self)
        form.setSpacing(12)
        form.setContentsMargins(20, 20, 20, 20)

        self.brand_combo = QComboBox()
        for b in db_brands():
            self.brand_combo.addItem(b["name"], b["id"])
        if brand_id is not None:
            idx = self.brand_combo.findData(brand_id)
            if idx >= 0:
                self.brand_combo.setCurrentIndex(idx)
        form.addRow("Brand:", self.brand_combo)

        self.name_edit = QLineEdit(name.upper() if name else "")
        self.name_edit.setPlaceholderText("e.g. A17 8+256")
        _setup_uppercase_edit(self.name_edit)
        form.addRow("Model Name:", self.name_edit)

        self.price_spin = QDoubleSpinBox()
        self.price_spin.setRange(0, 9_999_999)
        self.price_spin.setDecimals(0)
        self.price_spin.setSingleStep(500)
        self.price_spin.setGroupSeparatorShown(True)
        self.price_spin.setValue(ref_price or 0)
        self.price_spin.setPrefix("PKR ")
        form.addRow("Reference Price:", self.price_spin)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

        no_brands = self.brand_combo.count() == 0
        if no_brands:
            self.name_edit.setEnabled(False)
            self.price_spin.setEnabled(False)
            btns.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
            hint = QLabel("No brands exist — add a brand first.")
            hint.setStyleSheet("color:#dc2626; font-size:9pt;")
            form.addRow("", hint)

    def _accept(self):
        if self.brand_combo.count() == 0:
            QMessageBox.warning(self, "Validation", "Add a brand first.")
            return
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Validation", "Model name is required.")
            return
        self.accept()

    def get_data(self):
        return (
            self.brand_combo.currentData(),
            self.name_edit.text().strip().upper(),
            self.price_spin.value(),
        )


class SupplierDialog(QDialog):
    def __init__(self, parent=None, name="", contact="", ob=0.0):
        super().__init__(parent)
        self.setWindowTitle("Supplier")
        self.setFixedWidth(380)
        self.setStyleSheet(FORM_INPUT_STYLE)
        form = QFormLayout(self)
        form.setSpacing(12)
        form.setContentsMargins(20, 20, 20, 20)

        self.name_edit = QLineEdit(name.title() if name else "")
        self.name_edit.setPlaceholderText("Supplier / distributor name")
        _setup_titlecase_edit(self.name_edit)
        form.addRow("Name:", self.name_edit)

        self.contact_edit = QLineEdit(contact)
        self.contact_edit.setPlaceholderText("03XXXXXXXXX (11 digits)")
        self.contact_edit.setMaxLength(11)
        form.addRow("Contact:", self.contact_edit)

        self.ob_spin = QDoubleSpinBox()
        self.ob_spin.setRange(0, 99_999_999)
        self.ob_spin.setDecimals(0)
        self.ob_spin.setSingleStep(1000)
        self.ob_spin.setGroupSeparatorShown(True)
        self.ob_spin.setValue(ob or 0)
        self.ob_spin.setPrefix("PKR ")
        form.addRow("Opening Balance:", self.ob_spin)

        note = QLabel("Amount already owed to this supplier before using this system")
        note.setStyleSheet("color:#64748b; font-size:9pt;")
        note.setWordWrap(True)
        form.addRow("", note)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def _accept(self):
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Validation", "Supplier name is required.")
            return
        contact = self.contact_edit.text().strip()
        if contact and not validate_phone(contact):
            QMessageBox.warning(self, "Invalid Phone Number",
                "Phone number must start with 03 and be exactly 11 digits.\n"
                "Example: 03155344522")
            return
        self.accept()

    def get_data(self):
        return (
            self.name_edit.text().strip(),
            self.contact_edit.text().strip(),
            self.ob_spin.value(),
        )


class CustomerDialog(QDialog):
    def __init__(self, parent=None, name="", contact="", ob=0.0):
        super().__init__(parent)
        self.setWindowTitle("Credit Customer")
        self.setFixedWidth(380)
        self.setStyleSheet(FORM_INPUT_STYLE)
        form = QFormLayout(self)
        form.setSpacing(12)
        form.setContentsMargins(20, 20, 20, 20)

        self.name_edit = QLineEdit(name.title() if name else "")
        self.name_edit.setPlaceholderText("Customer / dealer name")
        _setup_titlecase_edit(self.name_edit)
        form.addRow("Name:", self.name_edit)

        self.contact_edit = QLineEdit(contact)
        self.contact_edit.setPlaceholderText("03XXXXXXXXX (11 digits)")
        self.contact_edit.setMaxLength(11)
        form.addRow("Contact:", self.contact_edit)

        self.ob_spin = QDoubleSpinBox()
        self.ob_spin.setRange(0, 99_999_999)
        self.ob_spin.setDecimals(0)
        self.ob_spin.setSingleStep(1000)
        self.ob_spin.setGroupSeparatorShown(True)
        self.ob_spin.setValue(ob or 0)
        self.ob_spin.setPrefix("PKR ")
        form.addRow("Opening Balance:", self.ob_spin)

        note = QLabel("Amount this customer already owes before using this system")
        note.setStyleSheet("color:#64748b; font-size:9pt;")
        note.setWordWrap(True)
        form.addRow("", note)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def _accept(self):
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Validation", "Customer name is required.")
            return
        contact = self.contact_edit.text().strip()
        if contact and not validate_phone(contact):
            QMessageBox.warning(self, "Invalid Phone Number",
                "Phone number must start with 03 and be exactly 11 digits.\n"
                "Example: 03155344522")
            return
        self.accept()

    def get_data(self):
        return (
            self.name_edit.text().strip(),
            self.contact_edit.text().strip(),
            self.ob_spin.value(),
        )


# ── Tabs ──────────────────────────────────────────────────────────────────────

class BrandsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.btn_add = QPushButton("+ Add Brand")
        self.btn_add.setStyleSheet(BTN_PRIMARY)
        self.btn_edit = QPushButton("Edit")
        self.btn_edit.setStyleSheet(BTN_SECONDARY)
        self.btn_edit.setEnabled(False)
        self.btn_del = QPushButton("Delete")
        self.btn_del.setStyleSheet(BTN_DANGER)
        self.btn_del.setEnabled(False)
        layout.addLayout(_toolbar(self.btn_add, self.btn_edit, self.btn_del))

        self.table = make_table(["Brand Name"])
        layout.addWidget(self.table)

        self.btn_add.clicked.connect(self._add)
        self.btn_edit.clicked.connect(self._edit)
        self.btn_del.clicked.connect(self._delete)
        self.table.itemSelectionChanged.connect(self._on_sel)
        self.table.doubleClicked.connect(self._edit)

        self.refresh()

    def refresh(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for r in db_brands():
            row = self.table.rowCount()
            self.table.insertRow(row)
            item = QTableWidgetItem(r["name"])
            item.setData(Qt.ItemDataRole.UserRole, r["id"])
            self.table.setItem(row, 0, item)
        self.table.setSortingEnabled(True)
        self._on_sel()

    def _current(self):
        row = self.table.currentRow()
        if row < 0 or not self.table.selectedItems():
            return None, None
        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole), item.text()

    def _on_sel(self):
        ok = bool(self.table.selectedItems())
        self.btn_edit.setEnabled(ok)
        self.btn_del.setEnabled(ok)

    def _add(self):
        dlg = BrandDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            db_save_brand(dlg.get_data())
            self.refresh()

    def _edit(self):
        bid, name = self._current()
        if bid is None:
            return
        dlg = BrandDialog(self, name=name)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            db_save_brand(dlg.get_data(), brand_id=bid)
            self.refresh()

    def _delete(self):
        bid, name = self._current()
        if bid is None:
            return
        if QMessageBox.question(
            self, "Delete Brand", f"Delete brand '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            db_delete_brand(bid)
            self.refresh()
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Cannot Delete",
                "Models exist under this brand. Delete those models first.")


class ModelsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(QLabel("Brand:"))
        self.brand_filter = SearchableComboBox()
        self.brand_filter.setMinimumWidth(160)
        top.addWidget(self.brand_filter)
        top.addStretch()
        self.btn_add = QPushButton("+ Add Model")
        self.btn_add.setStyleSheet(BTN_PRIMARY)
        self.btn_edit = QPushButton("Edit")
        self.btn_edit.setStyleSheet(BTN_SECONDARY)
        self.btn_edit.setEnabled(False)
        self.btn_del = QPushButton("Delete")
        self.btn_del.setStyleSheet(BTN_DANGER)
        self.btn_del.setEnabled(False)
        for b in (self.btn_add, self.btn_edit, self.btn_del):
            top.addWidget(b)
        layout.addLayout(top)

        self.table = make_table(["Brand", "Model Name", "Reference Price (PKR)"])
        layout.addWidget(self.table)

        self.btn_add.clicked.connect(self._add)
        self.btn_edit.clicked.connect(self._edit)
        self.btn_del.clicked.connect(self._delete)
        self.table.itemSelectionChanged.connect(self._on_sel)
        self.table.doubleClicked.connect(self._edit)
        self.brand_filter.currentIndexChanged.connect(self.refresh)

        self._reload_brand_filter()

    def _reload_brand_filter(self):
        current = self.brand_filter.currentData()
        self.brand_filter.blockSignals(True)
        self.brand_filter.clear()
        self.brand_filter.addItem("All Brands", None)
        for b in db_brands():
            self.brand_filter.addItem(b["name"], b["id"])
        idx = self.brand_filter.findData(current)
        self.brand_filter.setCurrentIndex(max(0, idx))
        self.brand_filter.blockSignals(False)
        self.refresh()

    def refresh(self):
        brand_id = self.brand_filter.currentData()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for r in db_models(brand_id):
            row = self.table.rowCount()
            self.table.insertRow(row)
            brand_item = QTableWidgetItem(r["brand_name"])
            brand_item.setData(Qt.ItemDataRole.UserRole, r["id"])
            self.table.setItem(row, 0, brand_item)
            self.table.setItem(row, 1, QTableWidgetItem(r["name"]))
            price_item = QTableWidgetItem(fmt_pkr(r["reference_price"]))
            price_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.table.setItem(row, 2, price_item)
        self.table.setSortingEnabled(True)
        self._on_sel()

    def _current_model(self):
        row = self.table.currentRow()
        if row < 0 or not self.table.selectedItems():
            return None
        model_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        conn = get_connection()
        r = conn.execute(
            "SELECT brand_id, name, reference_price FROM models WHERE id=?", (model_id,)
        ).fetchone()
        conn.close()
        return model_id, r["brand_id"], r["name"], r["reference_price"]

    def _on_sel(self):
        ok = bool(self.table.selectedItems())
        self.btn_edit.setEnabled(ok)
        self.btn_del.setEnabled(ok)

    def _add(self):
        dlg = ModelDialog(self, brand_id=self.brand_filter.currentData())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            db_save_model(*dlg.get_data())
            self.refresh()

    def _edit(self):
        data = self._current_model()
        if not data:
            return
        model_id, brand_id, name, ref_price = data
        dlg = ModelDialog(self, brand_id=brand_id, name=name, ref_price=ref_price or 0)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            db_save_model(*dlg.get_data(), model_id=model_id)
            self.refresh()

    def _delete(self):
        data = self._current_model()
        if not data:
            return
        model_id, _, name, _ = data
        if QMessageBox.question(
            self, "Delete Model", f"Delete model '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            db_delete_model(model_id)
            self.refresh()
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Cannot Delete",
                "Stock items exist for this model. Cannot delete.")


class SuppliersTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.btn_add = QPushButton("+ Add Supplier")
        self.btn_add.setStyleSheet(BTN_PRIMARY)
        self.btn_edit = QPushButton("Edit")
        self.btn_edit.setStyleSheet(BTN_SECONDARY)
        self.btn_edit.setEnabled(False)
        self.btn_del = QPushButton("Delete")
        self.btn_del.setStyleSheet(BTN_DANGER)
        self.btn_del.setEnabled(False)
        layout.addLayout(_toolbar(self.btn_add, self.btn_edit, self.btn_del))

        self.table = make_table(["Name", "Contact", "Opening Balance (PKR)"])
        layout.addWidget(self.table)

        self.btn_add.clicked.connect(self._add)
        self.btn_edit.clicked.connect(self._edit)
        self.btn_del.clicked.connect(self._delete)
        self.table.itemSelectionChanged.connect(self._on_sel)
        self.table.doubleClicked.connect(self._edit)

        self.refresh()

    def refresh(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for r in db_suppliers():
            row = self.table.rowCount()
            self.table.insertRow(row)
            name_item = QTableWidgetItem(r["name"])
            name_item.setData(Qt.ItemDataRole.UserRole, r["id"])
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, QTableWidgetItem(r["contact"] or ""))
            ob = QTableWidgetItem(fmt_pkr(r["opening_balance"]))
            ob.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 2, ob)
        self.table.setSortingEnabled(True)
        self._on_sel()

    def _current_id(self):
        row = self.table.currentRow()
        if row < 0 or not self.table.selectedItems():
            return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def _on_sel(self):
        ok = bool(self.table.selectedItems())
        self.btn_edit.setEnabled(ok)
        self.btn_del.setEnabled(ok)

    def _add(self):
        dlg = SupplierDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            db_save_supplier(*dlg.get_data())
            self.refresh()

    def _edit(self):
        sid = self._current_id()
        if sid is None:
            return
        conn = get_connection()
        r = conn.execute(
            "SELECT name, contact, opening_balance FROM suppliers WHERE id=?", (sid,)
        ).fetchone()
        conn.close()
        dlg = SupplierDialog(self, name=r["name"],
                             contact=r["contact"] or "",
                             ob=r["opening_balance"] or 0)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            db_save_supplier(*dlg.get_data(), supplier_id=sid)
            self.refresh()

    def _delete(self):
        sid = self._current_id()
        if sid is None:
            return
        name = self.table.item(self.table.currentRow(), 0).text()
        if QMessageBox.question(
            self, "Delete Supplier", f"Delete supplier '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            db_delete_supplier(sid)
            self.refresh()
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Cannot Delete",
                "Purchase records exist for this supplier. Cannot delete.")


class CustomersTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.btn_add = QPushButton("+ Add Customer")
        self.btn_add.setStyleSheet(BTN_PRIMARY)
        self.btn_edit = QPushButton("Edit")
        self.btn_edit.setStyleSheet(BTN_SECONDARY)
        self.btn_edit.setEnabled(False)
        self.btn_del = QPushButton("Delete")
        self.btn_del.setStyleSheet(BTN_DANGER)
        self.btn_del.setEnabled(False)
        layout.addLayout(_toolbar(self.btn_add, self.btn_edit, self.btn_del))

        note = QLabel(
            "Credit customers only — trade/dealer accounts with a running ledger. "
            "Cash customer details are entered directly on each sale."
        )
        note.setStyleSheet("color:#64748b; font-size:9pt;")
        note.setWordWrap(True)
        layout.addWidget(note)

        self.table = make_table(["Name", "Contact", "Opening Balance (PKR)"])
        layout.addWidget(self.table)

        self.btn_add.clicked.connect(self._add)
        self.btn_edit.clicked.connect(self._edit)
        self.btn_del.clicked.connect(self._delete)
        self.table.itemSelectionChanged.connect(self._on_sel)
        self.table.doubleClicked.connect(self._edit)

        self.refresh()

    def refresh(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for r in db_customers():
            row = self.table.rowCount()
            self.table.insertRow(row)
            name_item = QTableWidgetItem(r["name"])
            name_item.setData(Qt.ItemDataRole.UserRole, r["id"])
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, QTableWidgetItem(r["contact"] or ""))
            ob = QTableWidgetItem(fmt_pkr(r["opening_balance"]))
            ob.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 2, ob)
        self.table.setSortingEnabled(True)
        self._on_sel()

    def _current_id(self):
        row = self.table.currentRow()
        if row < 0 or not self.table.selectedItems():
            return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def _on_sel(self):
        ok = bool(self.table.selectedItems())
        self.btn_edit.setEnabled(ok)
        self.btn_del.setEnabled(ok)

    def _add(self):
        dlg = CustomerDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            db_save_customer(*dlg.get_data())
            self.refresh()

    def _edit(self):
        cid = self._current_id()
        if cid is None:
            return
        conn = get_connection()
        r = conn.execute(
            "SELECT name, contact, opening_balance FROM customers WHERE id=?", (cid,)
        ).fetchone()
        conn.close()
        dlg = CustomerDialog(self, name=r["name"],
                             contact=r["contact"] or "",
                             ob=r["opening_balance"] or 0)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            db_save_customer(*dlg.get_data(), customer_id=cid)
            self.refresh()

    def _delete(self):
        cid = self._current_id()
        if cid is None:
            return
        name = self.table.item(self.table.currentRow(), 0).text()
        if QMessageBox.question(
            self, "Delete Customer", f"Delete customer '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            db_delete_customer(cid)
            self.refresh()
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Cannot Delete",
                "Sale records exist for this customer. Cannot delete.")


# ── Salesman Dialog ───────────────────────────────────────────────────────────

class SalesmanDialog(QDialog):
    def __init__(self, parent=None, name="", pin=""):
        super().__init__(parent)
        self.setWindowTitle("Salesman")
        self.setFixedWidth(360)
        self.setStyleSheet(FORM_INPUT_STYLE)
        form = QFormLayout(self)
        form.setSpacing(12)
        form.setContentsMargins(20, 20, 20, 20)

        self.name_edit = QLineEdit(name.title() if name else "")
        self.name_edit.setPlaceholderText("e.g. Ahmed Khan")
        _setup_titlecase_edit(self.name_edit)
        form.addRow("Name:", self.name_edit)

        self.pin_edit = QLineEdit(pin)
        self.pin_edit.setPlaceholderText("4 digits, e.g. 1234")
        self.pin_edit.setMaxLength(4)
        self.pin_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("PIN (4 digits):", self.pin_edit)

        self.pin_confirm = QLineEdit()
        self.pin_confirm.setPlaceholderText("Re-enter PIN")
        self.pin_confirm.setMaxLength(4)
        self.pin_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Confirm PIN:", self.pin_confirm)

        hint = QLabel("PIN is used for mobile app login. Must be exactly 4 numeric digits.")
        hint.setStyleSheet("color:#64748b; font-size:9pt;")
        hint.setWordWrap(True)
        form.addRow("", hint)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def _accept(self):
        name = self.name_edit.text().strip()
        pin  = self.pin_edit.text().strip()
        conf = self.pin_confirm.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Name is required.")
            return
        if not pin.isdigit() or len(pin) != 4:
            QMessageBox.warning(self, "Validation", "PIN must be exactly 4 numeric digits.")
            return
        if pin != conf:
            QMessageBox.warning(self, "Validation", "PINs do not match.")
            return
        self.accept()

    def get_data(self):
        return (
            self.name_edit.text().strip(),
            self.pin_edit.text().strip(),
        )


# ── Salesman Tab ──────────────────────────────────────────────────────────────

class SalesmanTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.btn_add    = QPushButton("+ Add Salesman")
        self.btn_add.setStyleSheet(BTN_PRIMARY)
        self.btn_edit   = QPushButton("Edit")
        self.btn_edit.setStyleSheet(BTN_SECONDARY)
        self.btn_edit.setEnabled(False)
        self.btn_toggle = QPushButton("Toggle Status")
        self.btn_toggle.setStyleSheet(BTN_SECONDARY)
        self.btn_toggle.setEnabled(False)
        layout.addLayout(_toolbar(self.btn_add, self.btn_edit, self.btn_toggle))

        note = QLabel(
            "Inactive salesmen cannot log in on the mobile app and do not appear "
            "in the sale form dropdown. PIN is shown masked here."
        )
        note.setStyleSheet("color:#64748b; font-size:9pt;")
        note.setWordWrap(True)
        layout.addWidget(note)

        # Table: Name | PIN | Status
        self.table = make_table(["Name", "PIN", "Status"])
        layout.addWidget(self.table)

        self.btn_add.clicked.connect(self._add)
        self.btn_edit.clicked.connect(self._edit)
        self.btn_toggle.clicked.connect(self._toggle)
        self.table.itemSelectionChanged.connect(self._on_sel)
        self.table.doubleClicked.connect(self._edit)

        self.refresh()

    def refresh(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for r in db_salesmen():
            row = self.table.rowCount()
            self.table.insertRow(row)
            name_item = QTableWidgetItem(r["name"])
            name_item.setData(Qt.ItemDataRole.UserRole, r["id"])
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, QTableWidgetItem("****"))
            status = "Active" if r["active"] else "Inactive"
            s_item = QTableWidgetItem(status)
            s_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            s_item.setForeground(
                Qt.GlobalColor.darkGreen if r["active"] else Qt.GlobalColor.red
            )
            self.table.setItem(row, 2, s_item)
        self.table.setSortingEnabled(True)
        self._on_sel()

    def _current_id(self):
        row = self.table.currentRow()
        if row < 0 or not self.table.selectedItems():
            return None
        return self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def _on_sel(self):
        ok = bool(self.table.selectedItems())
        self.btn_edit.setEnabled(ok)
        self.btn_toggle.setEnabled(ok)

    def _add(self):
        dlg = SalesmanDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name, pin = dlg.get_data()
        err = db_save_salesman(name, pin)
        if err:
            QMessageBox.warning(self, "Error", err)
        else:
            self.refresh()

    def _edit(self):
        sid = self._current_id()
        if sid is None:
            return
        # Load current name (PIN shown empty — user must re-enter)
        row = self.table.currentRow()
        current_name = self.table.item(row, 0).text()
        dlg = SalesmanDialog(self, name=current_name, pin="")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name, pin = dlg.get_data()
        err = db_save_salesman(name, pin, salesman_id=sid)
        if err:
            QMessageBox.warning(self, "Error", err)
        else:
            self.refresh()

    def _toggle(self):
        sid = self._current_id()
        if sid is None:
            return
        row = self.table.currentRow()
        name = self.table.item(row, 0).text()
        current_status = self.table.item(row, 2).text()
        new_status = "Inactive" if current_status == "Active" else "Active"
        if QMessageBox.question(
            self, "Toggle Status",
            f"Change {name}'s status to {new_status}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        db_toggle_salesman(sid)
        self.refresh()


# ── Masters Page ──────────────────────────────────────────────────────────────

class MastersPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:#f1f5f9;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("Masters")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title.setStyleSheet("color:#1e293b;")
        layout.addWidget(title)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #e2e8f0; border-radius: 6px; background: #ffffff;
            }
            QTabBar::tab {
                background: #f8fafc; color: #64748b;
                border: 1px solid #e2e8f0; border-bottom: none;
                border-radius: 4px 4px 0 0;
                padding: 8px 20px; margin-right: 2px; font-size: 10pt;
            }
            QTabBar::tab:selected {
                background: #ffffff; color: #1e40af; font-weight: bold;
            }
            QTabBar::tab:hover:!selected { background: #f1f5f9; }
        """)

        self.brands_tab    = BrandsTab()
        self.models_tab    = ModelsTab()
        self.suppliers_tab = SuppliersTab()
        self.customers_tab = CustomersTab()
        self.salesman_tab  = SalesmanTab()

        self.tabs.addTab(self.brands_tab,    "Brands")
        self.tabs.addTab(self.models_tab,    "Models")
        self.tabs.addTab(self.suppliers_tab, "Suppliers")
        self.tabs.addTab(self.customers_tab, "Credit Customers")
        self.tabs.addTab(self.salesman_tab,  "Salesmen")

        self.tabs.currentChanged.connect(self._on_tab_change)

        layout.addWidget(self.tabs)

    def _on_tab_change(self, index):
        if index == 1:
            self.models_tab._reload_brand_filter()
        elif index == 4:
            self.salesman_tab.refresh()
