"""
Bulk model-price editor — opened by pressing the Ctrl key (alone) inside the
IMEI field of the Purchase and Sale forms.

Shows one row per model already added to the voucher: Model | Qty | Price |
Discount | Net Price. Discount and Net Price stay in sync with Price
(net = price - discount; entering a net fills the discount), so the price of
every IMEI of a model can be corrected in one go instead of line by line.
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QDoubleSpinBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

TABLE_STYLE = """
    QTableWidget {
        background:#ffffff; border:1px solid #e2e8f0;
        border-radius:6px; gridline-color:#f1f5f9; font-size:10pt;
    }
    QTableWidget::item { padding:6px 10px; }
    QHeaderView::section {
        background:#f8fafc; color:#475569; font-weight:bold; font-size:9pt;
        border:none; border-bottom:1px solid #e2e8f0; padding:8px 10px;
    }
    QDoubleSpinBox {
        background:#ffffff; color:#1e293b;
        border:1px solid #cbd5e1; border-radius:4px; padding:4px 8px; font-size:10pt;
    }
    QDoubleSpinBox:focus { border:2px solid #2563eb; }
"""
BTN_PRIMARY = """
    QPushButton { background:#2563eb; color:white; border:none;
        border-radius:5px; padding:6px 16px; font-size:10pt; }
    QPushButton:hover { background:#1d4ed8; }
"""
BTN_SECONDARY = """
    QPushButton { background:#f1f5f9; color:#334155;
        border:1px solid #cbd5e1; border-radius:5px; padding:6px 16px; font-size:10pt; }
    QPushButton:hover { background:#e2e8f0; }
"""


class BulkPriceDialog(QDialog):
    """
    rows: list of dicts — {"model_id", "label", "qty", "price", "net"}.
    Discount is derived (price - net). After exec() returns Accepted,
    result_prices() gives {model_id: new_net_price} for every row.
    """

    def __init__(self, rows, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Update Model Prices")
        self.setMinimumWidth(640)
        self.setStyleSheet(TABLE_STYLE)
        self._rows = rows
        self._spins = []      # [(model_id, price_spin, disc_spin, net_spin)]
        self._updating = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        hint = QLabel(
            "Enter a Discount (net is calculated) or type the Net Price "
            "directly (discount fills in). Applies to every IMEI of that model."
        )
        hint.setStyleSheet("color:#64748b; font-size:9pt;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.table = QTableWidget(len(rows), 5)
        self.table.setHorizontalHeaderLabels(
            ["Model", "Qty", "Price (PKR)", "Discount (PKR)", "Net Price (PKR)"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in (1, 2, 3, 4):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 50)
        for c in (2, 3, 4):
            self.table.setColumnWidth(c, 125)

        for r, row in enumerate(rows):
            name_item = QTableWidgetItem(row["label"])
            name_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            name_item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            self.table.setItem(r, 0, name_item)

            qty_item = QTableWidgetItem(str(row["qty"]))
            qty_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            qty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(r, 1, qty_item)

            price_spin = self._make_spin(row["price"])
            # Negative discount allowed: net above price shows as a negative
            # discount instead of being silently clamped.
            disc_spin = self._make_spin(
                (row["price"] or 0) - (row["net"] or 0), minimum=-9_999_999
            )
            net_spin = self._make_spin(row["net"])
            self.table.setCellWidget(r, 2, price_spin)
            self.table.setCellWidget(r, 3, disc_spin)
            self.table.setCellWidget(r, 4, net_spin)

            price_spin.valueChanged.connect(lambda _, i=r: self._recalc(i, "net"))
            disc_spin.valueChanged.connect(lambda _, i=r: self._recalc(i, "net"))
            net_spin.valueChanged.connect(lambda _, i=r: self._recalc(i, "disc"))
            self._spins.append((row["model_id"], price_spin, disc_spin, net_spin))

        self.table.setMinimumHeight(min(90 + 40 * len(rows), 420))
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet(BTN_SECONDARY)
        btn_cancel.setAutoDefault(False)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        btn_apply = QPushButton("Apply to Invoice")
        btn_apply.setStyleSheet(BTN_PRIMARY)
        btn_apply.setAutoDefault(False)
        btn_apply.clicked.connect(self.accept)
        btn_row.addWidget(btn_apply)
        layout.addLayout(btn_row)

        if self._spins:
            first_disc = self._spins[0][2]
            first_disc.setFocus()
            first_disc.selectAll()

    def _make_spin(self, value, minimum=0):
        s = QDoubleSpinBox()
        s.setRange(minimum, 9_999_999)
        s.setDecimals(0)
        s.setSingleStep(100)
        s.setGroupSeparatorShown(True)
        s.setValue(value or 0)
        # Enter = Tab, consistent with the rest of the app
        s.lineEdit().returnPressed.connect(s.focusNextChild)
        return s

    def _recalc(self, i, target):
        """Keep price/discount/net consistent: net = price - discount."""
        if self._updating:
            return
        self._updating = True
        _, price, disc, net = self._spins[i]
        if target == "net":
            net.setValue(max(0.0, price.value() - disc.value()))
        else:
            disc.setValue(price.value() - net.value())
        self._updating = False

    def result_prices(self):
        return {model_id: net.value() for model_id, _, _, net in self._spins}
