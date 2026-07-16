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
    QLineEdit,
)
from PyQt6.QtCore import Qt, QRegularExpression
from PyQt6.QtGui import QFont, QRegularExpressionValidator

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
    QLineEdit {
        background:#ffffff; color:#1e293b;
        border:1px solid #cbd5e1; border-radius:4px; padding:4px 8px; font-size:10pt;
    }
    QLineEdit:focus { border:2px solid #2563eb; }
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


def _fmt(val):
    return f"{float(val or 0):,.0f}"


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
        self._edits = []      # [(model_id, price_edit, disc_edit, net_edit)]
        self._values = []     # [{"price": float, "disc": float, "net": float}]
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
        self.table.horizontalHeaderItem(0).setTextAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        # Keep the table itself out of the focus chain so Enter/Tab moves
        # straight from one amount field to the next.
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.setTabKeyNavigation(False)
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

            price = float(row["price"] or 0)
            net = float(row["net"] or 0)
            # Negative discount allowed: net above price shows as a negative
            # discount instead of being silently clamped.
            disc = price - net
            self._values.append({"price": price, "disc": disc, "net": net})

            price_edit = self._make_amount_edit(price)
            disc_edit = self._make_amount_edit(disc)
            net_edit = self._make_amount_edit(net)
            self.table.setCellWidget(r, 2, price_edit)
            self.table.setCellWidget(r, 3, disc_edit)
            self.table.setCellWidget(r, 4, net_edit)

            price_edit.textChanged.connect(lambda _, i=r: self._on_edited(i, "price"))
            disc_edit.textChanged.connect(lambda _, i=r: self._on_edited(i, "disc"))
            net_edit.textChanged.connect(lambda _, i=r: self._on_edited(i, "net"))
            # Restore clean comma formatting (and revert any half-typed /
            # cleared field to its last valid value) once the cell is left.
            for e in (price_edit, disc_edit, net_edit):
                e.editingFinished.connect(lambda i=r: self._reformat_row(i))
            self._edits.append((row["model_id"], price_edit, disc_edit, net_edit))

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

        if self._edits:
            first_disc = self._edits[0][2]
            first_disc.setFocus()
            first_disc.selectAll()

    def _make_amount_edit(self, value):
        e = QLineEdit(_fmt(value))
        e.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        # Numeric-only typing guard: digits with optional commas, optional
        # leading minus (negative discounts), optional decimal part.
        e.setValidator(QRegularExpressionValidator(
            QRegularExpression(r"^-?[\d,]*\.?\d*$"), e
        ))
        # Enter = Tab, consistent with the rest of the app
        e.returnPressed.connect(e.focusNextChild)
        return e

    @staticmethod
    def _parse(edit):
        """Comma-tolerant float parse; None while empty/half-typed."""
        text = edit.text().replace(",", "").strip()
        if not text or text in ("-", ".", "-."):
            return None
        try:
            return float(text)
        except ValueError:
            return None

    def _on_edited(self, i, field):
        """Keep price/discount/net consistent: net = price - discount."""
        if self._updating:
            return
        _, price_edit, disc_edit, net_edit = self._edits[i]
        val = self._parse({"price": price_edit, "disc": disc_edit,
                           "net": net_edit}[field])
        if val is None:
            return  # keep last valid values; _reformat_row restores on leave
        self._updating = True
        vals = self._values[i]
        vals[field] = val
        if field in ("price", "disc"):
            vals["net"] = max(0.0, vals["price"] - vals["disc"])
            net_edit.setText(_fmt(vals["net"]))
        else:
            vals["disc"] = vals["price"] - vals["net"]
            disc_edit.setText(_fmt(vals["disc"]))
        self._updating = False

    def _reformat_row(self, i):
        if self._updating:
            return
        self._updating = True
        _, price_edit, disc_edit, net_edit = self._edits[i]
        vals = self._values[i]
        price_edit.setText(_fmt(vals["price"]))
        disc_edit.setText(_fmt(vals["disc"]))
        net_edit.setText(_fmt(vals["net"]))
        self._updating = False

    def result_prices(self):
        return {model_id: vals["net"]
                for (model_id, *_), vals in zip(self._edits, self._values)}
