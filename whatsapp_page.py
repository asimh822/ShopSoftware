from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QFrame, QMessageBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from whatsapp_handler import (
    get_pending_whatsapp_sales, send_sale_whatsapp, mark_sent_manual
)

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
        border-radius:5px; padding:6px 14px; font-size:10pt; }
    QPushButton:hover { background:#1d4ed8; }
"""
BTN_GREEN = """
    QPushButton { background:#16a34a; color:white; border:none;
        border-radius:5px; padding:6px 14px; font-size:10pt; }
    QPushButton:hover { background:#15803d; }
"""
BTN_SECONDARY = """
    QPushButton { background:#f1f5f9; color:#334155;
        border:1px solid #cbd5e1; border-radius:5px; padding:6px 14px; font-size:10pt; }
    QPushButton:hover { background:#e2e8f0; }
"""
BTN_SMALL = """
    QPushButton { background:#2563eb; color:white; border:none;
        border-radius:4px; padding:3px 10px; font-size:9pt; }
    QPushButton:hover { background:#1d4ed8; }
"""
BTN_SMALL_GREEN = """
    QPushButton { background:#16a34a; color:white; border:none;
        border-radius:4px; padding:3px 10px; font-size:9pt; }
    QPushButton:hover { background:#15803d; }
"""
CARD_STYLE = "background:#ffffff; border:1px solid #e2e8f0; border-radius:8px; color:#1e293b;"


class WhatsAppPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:#f1f5f9;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Title
        title = QLabel("WhatsApp")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title.setStyleSheet("color:#1e293b;")
        layout.addWidget(title)

        # Info card
        info = QFrame()
        info.setStyleSheet(CARD_STYLE)
        il = QVBoxLayout(info)
        il.setContentsMargins(20, 14, 20, 14)
        il.setSpacing(6)

        h = QLabel("How WhatsApp sending works")
        h.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        h.setStyleSheet("color:#1e293b;")
        il.addWidget(h)

        for line in [
            "• Cash sales automatically trigger a WhatsApp message to the customer.",
            "• If <b>pywhatkit</b> is installed, messages are sent automatically via WhatsApp Web.",
            "• Otherwise a wa.me link opens in your browser — click Send there.",
            "• Unsent messages appear in the table below. Use the buttons to retry or mark as sent.",
            "• Install pywhatkit:  <code>pip install pywhatkit</code>",
        ]:
            lbl = QLabel(line)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setStyleSheet("color:#475569; font-size:9pt;")
            il.addWidget(lbl)

        layout.addWidget(info)

        # Pending section
        pending_title = QHBoxLayout()
        pt = QLabel("Pending / Unsent Messages")
        pt.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        pt.setStyleSheet("color:#1e293b;")
        pending_title.addWidget(pt)
        pending_title.addStretch()
        btn_refresh = QPushButton("Refresh")
        btn_refresh.setStyleSheet(BTN_SECONDARY)
        btn_refresh.clicked.connect(self.refresh)
        pending_title.addWidget(btn_refresh)
        layout.addLayout(pending_title)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["SV Number", "Date", "Customer", "Contact", "Items", "Send", "Mark Sent"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet(TABLE_STYLE)
        layout.addWidget(self.table, stretch=1)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color:#64748b; font-size:9pt;")
        layout.addWidget(self.status_label)

        self.refresh()

    def refresh(self):
        rows = get_pending_whatsapp_sales()
        self.table.setRowCount(0)

        for r in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            sv_item = QTableWidgetItem(r["sv_number"])
            sv_item.setData(Qt.ItemDataRole.UserRole, r["id"])
            self.table.setItem(row, 0, sv_item)
            self.table.setItem(row, 1, QTableWidgetItem(r["date"]))
            self.table.setItem(row, 2, QTableWidgetItem(r["cash_customer_name"] or "—"))
            self.table.setItem(row, 3, QTableWidgetItem(r["cash_customer_contact"] or "—"))
            cnt = QTableWidgetItem(str(r["items"]))
            cnt.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 4, cnt)

            btn_send = QPushButton("Send")
            btn_send.setStyleSheet(BTN_SMALL)
            sv_id = r["id"]
            btn_send.clicked.connect(lambda _, sid=sv_id: self._send(sid))
            self.table.setCellWidget(row, 5, btn_send)

            btn_mark = QPushButton("Mark Sent")
            btn_mark.setStyleSheet(BTN_SMALL_GREEN)
            btn_mark.clicked.connect(lambda _, sid=sv_id: self._mark(sid))
            self.table.setCellWidget(row, 6, btn_mark)

        n = len(rows)
        self.status_label.setText(
            f"{n} pending message{'s' if n != 1 else ''}"
            if n > 0 else "All WhatsApp messages sent."
        )

    def _send(self, sv_id: int):
        success, msg = send_sale_whatsapp(sv_id)
        QMessageBox.information(self, "WhatsApp", msg)
        self.refresh()

    def _mark(self, sv_id: int):
        mark_sent_manual(sv_id)
        self.refresh()
