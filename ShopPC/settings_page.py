import os
import shutil
from datetime import date as _date

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QFormLayout, QFrame, QMessageBox,
    QGroupBox, QScrollArea, QFileDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QDialog, QDialogButtonBox, QDoubleSpinBox, QDateEdit, QCheckBox,
    QSizePolicy, QComboBox,
)
from PyQt6.QtCore import Qt, QRegularExpression, QDate
from PyQt6.QtGui import QFont, QRegularExpressionValidator

from database import (
    get_setting, set_setting, check_pin, set_pin, DB_PATH,
    db_bank_accounts, db_save_bank_account, db_delete_bank_account,
    db_year_end_summary, db_perform_year_end_close,
)

BTN_PRIMARY = """
    QPushButton { background:#2563eb; color:white; border:none;
        border-radius:5px; padding:7px 20px; font-size:10pt; }
    QPushButton:hover { background:#1d4ed8; }
"""
BTN_SECONDARY = """
    QPushButton { background:#f1f5f9; color:#334155;
        border:1px solid #cbd5e1; border-radius:5px; padding:7px 16px; font-size:10pt; }
    QPushButton:hover { background:#e2e8f0; }
"""
CARD_STYLE = "background:#ffffff; border:1px solid #e2e8f0; border-radius:8px; color:#1e293b;"
GROUP_STYLE = """
    QGroupBox {
        font-weight: bold; font-size: 10pt; color: #1e293b;
        border: 1px solid #e2e8f0; border-radius: 6px;
        margin-top: 8px; padding-top: 12px;
        background: #ffffff;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 12px; top: 2px;
        padding: 0 6px;
        background: #ffffff;
    }
"""
INPUT_STYLE = """
    QLineEdit, QTextEdit {
        border: 1px solid #cbd5e1; border-radius: 5px;
        padding: 6px 10px; font-size: 10pt; background: #ffffff;
    }
    QLineEdit:focus, QTextEdit:focus { border-color: #2563eb; }
"""


def _fmt_pkr(val) -> str:
    if val is None:
        return "0"
    return f"{float(val):,.0f}"


# ── Year End Close: confirmation + archive dialog ─────────────────────────────

class YearEndCloseDialog(QDialog):
    """
    Shows the closing summary, collects the archive folder, requires the
    irreversible-action checkbox, then lets the user proceed.
    """

    def __init__(self, summary: dict, year_label: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Year End Closing — Confirmation Required")
        self.setMinimumWidth(660)
        self.resize(680, 780)
        self._archive_folder = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        # ── Title ──────────────────────────────────────────────────────────
        title = QLabel(f"Year End Closing — {year_label}")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet("color:#1e293b;")
        root.addWidget(title)

        # ── Scrollable summary body ────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background:#f8fafc;")

        body = QWidget()
        body.setStyleSheet("background:#f8fafc;")
        bv = QVBoxLayout(body)
        bv.setContentsMargins(0, 0, 0, 0)
        bv.setSpacing(10)

        # Key metrics card
        metrics_card = QFrame()
        metrics_card.setStyleSheet(
            "QFrame{background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;}"
        )
        mv = QVBoxLayout(metrics_card)
        mv.setContentsMargins(16, 12, 16, 12)
        mv.setSpacing(6)

        hdr_lbl = QLabel("Closing Summary")
        hdr_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        hdr_lbl.setStyleSheet("color:#1e293b;")
        mv.addWidget(hdr_lbl)

        for label, value, color in [
            ("Total Sales (Year)",      f"PKR {_fmt_pkr(summary['total_sales'])}",     "#16a34a"),
            ("Total Purchases (Year)",  f"PKR {_fmt_pkr(summary['total_purchases'])}", "#dc2626"),
            ("Cash in Hand",            f"PKR {_fmt_pkr(summary['cash_in_hand'])}",    "#0891b2"),
            ("Stock Units in Hand",     str(summary['stock_units']),                   "#7c3aed"),
        ]:
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet("color:#475569; font-size:10pt;")
            val = QLabel(value)
            val.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            val.setStyleSheet(f"color:{color};")
            row.addWidget(lbl)
            row.addStretch()
            row.addWidget(val)
            mv.addLayout(row)

        bv.addWidget(metrics_card)

        # Per-party balance cards
        def _party_card(heading, parties, balance_color_fn):
            if not parties:
                return
            card = QFrame()
            card.setStyleSheet(
                "QFrame{background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;}"
            )
            cv = QVBoxLayout(card)
            cv.setContentsMargins(16, 10, 16, 10)
            cv.setSpacing(4)
            h = QLabel(heading)
            h.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            h.setStyleSheet("color:#334155;")
            cv.addWidget(h)
            for p in parties:
                row = QHBoxLayout()
                row.setContentsMargins(8, 0, 0, 0)
                name_lbl = QLabel(p["name"])
                name_lbl.setStyleSheet("color:#475569; font-size:10pt;")
                bal = p["balance"]
                bal_lbl = QLabel(f"PKR {_fmt_pkr(abs(bal))}")
                bal_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                bal_lbl.setStyleSheet(f"color:{balance_color_fn(bal)};")
                row.addWidget(name_lbl)
                row.addStretch()
                row.addWidget(bal_lbl)
                cv.addLayout(row)
            bv.addWidget(card)

        _party_card(
            "Supplier Closing Balances (what you owe)",
            summary["supplier_balances"],
            lambda b: "#dc2626" if b > 0 else "#16a34a",
        )
        _party_card(
            "Customer Closing Balances (what they owe you)",
            summary["customer_balances"],
            lambda b: "#16a34a" if b > 0 else "#64748b",
        )
        _party_card(
            "Bank Account Balances",
            summary["bank_balances"],
            lambda b: "#0891b2",
        )

        bv.addStretch()
        scroll.setWidget(body)
        root.addWidget(scroll, stretch=1)

        # ── Archive folder picker ──────────────────────────────────────────
        folder_card = QFrame()
        folder_card.setStyleSheet(
            "QFrame{background:#ffffff;border:1px solid #e2e8f0;border-radius:6px;}"
        )
        fl = QHBoxLayout(folder_card)
        fl.setContentsMargins(12, 10, 12, 10)
        fl.setSpacing(8)
        fl.addWidget(QLabel("Archive Folder:"))
        self._folder_label = QLabel("No folder selected")
        self._folder_label.setStyleSheet("color:#94a3b8; font-size:9pt;")
        self._folder_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        fl.addWidget(self._folder_label, stretch=1)
        btn_folder = QPushButton("Choose…")
        btn_folder.setStyleSheet(BTN_SECONDARY)
        btn_folder.clicked.connect(self._pick_folder)
        fl.addWidget(btn_folder)
        root.addWidget(folder_card)

        # ── Irreversible-action warning ────────────────────────────────────
        warn_frame = QFrame()
        warn_frame.setStyleSheet(
            "QFrame{background:#fff7ed;border:1px solid #fed7aa;border-radius:6px;}"
        )
        wv = QVBoxLayout(warn_frame)
        wv.setContentsMargins(14, 10, 14, 10)
        wv.setSpacing(6)

        warn_title = QLabel("⚠   THIS CANNOT BE UNDONE")
        warn_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        warn_title.setStyleSheet(
            "color:#c2410c; background:transparent; border:none;"
        )
        wv.addWidget(warn_title)

        warn_body = QLabel(
            "All transaction history will be permanently erased from the main database.\n"
            "Please ensure you have taken a manual backup before proceeding.\n"
            "The archive file is a separate read-only copy and cannot undo this action."
        )
        warn_body.setStyleSheet(
            "color:#92400e; font-size:9pt; background:transparent; border:none;"
        )
        warn_body.setWordWrap(True)
        wv.addWidget(warn_body)

        self._confirm_check = QCheckBox(
            "I understand this is permanent and I have taken a manual backup"
        )
        self._confirm_check.setStyleSheet(
            "color:#c2410c; font-size:9pt; background:transparent; border:none;"
        )
        self._confirm_check.stateChanged.connect(self._refresh_btn)
        wv.addWidget(self._confirm_check)
        root.addWidget(warn_frame)

        # ── Buttons ────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setStyleSheet(BTN_SECONDARY)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        btn_row.addStretch()
        self._btn_close = QPushButton("Close Year & Archive →")
        self._btn_close.setStyleSheet("""
            QPushButton {
                background:#dc2626; color:white; border:none;
                border-radius:5px; padding:8px 22px;
                font-size:10pt; font-weight:bold;
            }
            QPushButton:hover    { background:#b91c1c; }
            QPushButton:disabled { background:#fca5a5; color:#ffffff; }
        """)
        self._btn_close.setEnabled(False)
        self._btn_close.clicked.connect(self.accept)
        btn_row.addWidget(self._btn_close)
        root.addLayout(btn_row)

    # ── helpers ──────────────────────────────────────────────────────────────

    def _pick_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose Archive Folder", "")
        if folder:
            self._archive_folder = folder
            self._folder_label.setText(folder)
            self._folder_label.setStyleSheet("color:#1e293b; font-size:9pt;")
        self._refresh_btn()

    def _refresh_btn(self):
        self._btn_close.setEnabled(
            self._confirm_check.isChecked() and bool(self._archive_folder)
        )

    def archive_folder(self) -> str:
        return self._archive_folder


class SettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:#f1f5f9;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background:#f1f5f9;")
        outer.addWidget(scroll)

        container = QWidget()
        container.setStyleSheet("background:#f1f5f9;")
        scroll.setWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(16)

        # Title
        title_row = QHBoxLayout()
        title = QLabel("Settings")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title.setStyleSheet("color:#1e293b;")
        title_row.addWidget(title)
        title_row.addStretch()
        btn_save = QPushButton("Save All Settings")
        btn_save.setStyleSheet(BTN_PRIMARY)
        btn_save.clicked.connect(self._save)
        title_row.addWidget(btn_save)
        layout.addLayout(title_row)

        # ── Shop Information ──────────────────────────────────────────────────
        shop_group = QGroupBox("Shop Information")
        shop_group.setStyleSheet(GROUP_STYLE)
        sf = QFormLayout(shop_group)
        sf.setSpacing(10)
        sf.setContentsMargins(16, 16, 16, 16)

        self.shop_name = QLineEdit(get_setting("shop_name") or "")
        self.shop_name.setStyleSheet(INPUT_STYLE)
        self.shop_name.returnPressed.connect(lambda: self.shop_name.focusNextChild())
        sf.addRow("Shop Name:", self.shop_name)

        self.shop_address = QLineEdit(get_setting("shop_address") or "")
        self.shop_address.setStyleSheet(INPUT_STYLE)
        self.shop_address.returnPressed.connect(lambda: self.shop_address.focusNextChild())
        sf.addRow("Address:", self.shop_address)

        self.shop_contact = QLineEdit(get_setting("shop_contact") or "")
        self.shop_contact.setStyleSheet(INPUT_STYLE)
        self.shop_contact.returnPressed.connect(lambda: self.shop_contact.focusNextChild())
        sf.addRow("Contact:", self.shop_contact)

        layout.addWidget(shop_group)

        # ── Thermal Receipt ───────────────────────────────────────────────────
        receipt_group = QGroupBox("Thermal Receipt")
        receipt_group.setStyleSheet(GROUP_STYLE)
        rf = QFormLayout(receipt_group)
        rf.setSpacing(10)
        rf.setContentsMargins(16, 16, 16, 16)

        # ── Connection mode: USB/Local vs Network ─────────────────────────────
        self.printer_mode = QComboBox()
        self.printer_mode.addItem("USB / Local (connected to this PC)", "usb")
        self.printer_mode.addItem("Network (LAN / WiFi)", "network")
        saved_mode = (get_setting("printer_mode") or "usb").strip().lower()
        self.printer_mode.setCurrentIndex(1 if saved_mode == "network" else 0)
        self.printer_mode.currentIndexChanged.connect(self._on_printer_mode_changed)
        rf.addRow("Connection:", self.printer_mode)

        self.printer_name = QLineEdit(get_setting("thermal_printer") or "")
        self.printer_name.setStyleSheet(INPUT_STYLE)
        self.printer_name.setPlaceholderText(
            "e.g. Blackcopper BC-85AC — use Pick Printer to detect automatically"
        )
        self.printer_name.returnPressed.connect(lambda: self.printer_name.focusNextChild())

        # Printer name field + Pick Printer button on the same row
        printer_row = QHBoxLayout()
        printer_row.setSpacing(8)
        printer_row.addWidget(self.printer_name)
        btn_pick = QPushButton("Pick Printer")
        btn_pick.setStyleSheet(BTN_SECONDARY)
        btn_pick.setFixedWidth(110)
        btn_pick.clicked.connect(self._pick_printer)
        printer_row.addWidget(btn_pick)
        self._usb_row_label = QLabel("Printer Name:")
        rf.addRow(self._usb_row_label, printer_row)
        self._usb_row_widget = printer_row

        printer_note = QLabel(
            "Click 'Pick Printer' to see all installed Windows printers and select yours. "
            "Leave blank to show a receipt preview instead of printing."
        )
        printer_note.setStyleSheet("color:#64748b; font-size:9pt;")
        printer_note.setWordWrap(True)
        self._usb_note = printer_note
        rf.addRow("", printer_note)

        # ── Network printer fields (IP + port) — shown only in Network mode ────
        net_row = QHBoxLayout()
        net_row.setSpacing(8)
        self.printer_ip = QLineEdit(get_setting("printer_ip") or "")
        self.printer_ip.setStyleSheet(INPUT_STYLE)
        self.printer_ip.setPlaceholderText("192.168.1.50")
        self.printer_ip.returnPressed.connect(lambda: self.printer_ip.focusNextChild())
        net_row.addWidget(self.printer_ip, stretch=1)
        net_row.addWidget(QLabel("Port:"))
        self.printer_port = QLineEdit(get_setting("printer_port") or "9100")
        self.printer_port.setStyleSheet(INPUT_STYLE)
        self.printer_port.setPlaceholderText("9100")
        self.printer_port.setFixedWidth(80)
        self.printer_port.returnPressed.connect(lambda: self.printer_port.focusNextChild())
        net_row.addWidget(self.printer_port)
        self._net_row_label = QLabel("Printer IP:")
        rf.addRow(self._net_row_label, net_row)
        self._net_row_widget = net_row

        net_note = QLabel(
            "Enter the thermal printer's IP address and port (most network "
            "printers use 9100). The printer must be on the same network as this PC."
        )
        net_note.setStyleSheet("color:#64748b; font-size:9pt;")
        net_note.setWordWrap(True)
        self._net_note = net_note
        rf.addRow("", net_note)

        # Set initial visibility based on saved mode
        self._on_printer_mode_changed()

        self.receipt_footer = QLineEdit(get_setting("receipt_footer") or "")
        self.receipt_footer.setStyleSheet(INPUT_STYLE)
        self.receipt_footer.setPlaceholderText("Printed at the bottom of every receipt")
        self.receipt_footer.returnPressed.connect(lambda: self.receipt_footer.focusNextChild())
        rf.addRow("Receipt Footer:", self.receipt_footer)

        btn_test_print = QPushButton("Test Print")
        btn_test_print.setStyleSheet(BTN_SECONDARY)
        btn_test_print.clicked.connect(self._test_print)
        rf.addRow("", btn_test_print)

        layout.addWidget(receipt_group)

        # ── WhatsApp ──────────────────────────────────────────────────────────
        wa_group = QGroupBox("WhatsApp")
        wa_group.setStyleSheet(GROUP_STYLE)
        wf = QVBoxLayout(wa_group)
        wf.setContentsMargins(16, 16, 16, 16)
        wf.setSpacing(8)

        owner_row = QHBoxLayout()
        owner_row.addWidget(QLabel("Owner Number:"))
        self.owner_whatsapp = QLineEdit(get_setting("owner_whatsapp") or "")
        self.owner_whatsapp.setStyleSheet(INPUT_STYLE)
        self.owner_whatsapp.setPlaceholderText("03XXXXXXXXX  — receives daily digest")
        self.owner_whatsapp.setMaxLength(11)
        self.owner_whatsapp.returnPressed.connect(
            lambda: self.owner_whatsapp.focusNextChild()
        )
        owner_row.addWidget(self.owner_whatsapp, stretch=1)
        wf.addLayout(owner_row)

        var_note = QLabel(
            "Sale template variables: {customer_name} {model_name} {imei} "
            "{shop_name} {shop_contact} {date}"
        )
        var_note.setStyleSheet("color:#64748b; font-size:9pt;")
        var_note.setWordWrap(True)
        wf.addWidget(var_note)

        self.wa_template = QTextEdit()
        self.wa_template.setStyleSheet(INPUT_STYLE)
        self.wa_template.setFixedHeight(100)
        self.wa_template.setPlainText(get_setting("whatsapp_template") or "")
        wf.addWidget(self.wa_template)

        wa_lib_note = QLabel(
            "Auto-sending requires:  pip install pywhatkit\n"
            "Without it, messages open in your browser for manual sending."
        )
        wa_lib_note.setStyleSheet("color:#64748b; font-size:9pt;")
        wf.addWidget(wa_lib_note)

        layout.addWidget(wa_group)

        # ── Security / PIN ────────────────────────────────────────────────────
        pin_group = QGroupBox("Security — Change PIN")
        pin_group.setStyleSheet(GROUP_STYLE)
        pf = QFormLayout(pin_group)
        pf.setSpacing(10)
        pf.setContentsMargins(16, 16, 16, 16)

        digits_only = QRegularExpressionValidator(QRegularExpression(r"\d{0,6}"))

        self.pin_current = QLineEdit()
        self.pin_current.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_current.setPlaceholderText("Current PIN")
        self.pin_current.setMaxLength(6)
        self.pin_current.setValidator(digits_only)
        self.pin_current.setStyleSheet(INPUT_STYLE)
        self.pin_current.returnPressed.connect(lambda: self.pin_current.focusNextChild())
        pf.addRow("Current PIN:", self.pin_current)

        self.pin_new = QLineEdit()
        self.pin_new.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_new.setPlaceholderText("4–6 digits")
        self.pin_new.setMaxLength(6)
        self.pin_new.setValidator(digits_only)
        self.pin_new.setStyleSheet(INPUT_STYLE)
        self.pin_new.returnPressed.connect(lambda: self.pin_new.focusNextChild())
        pf.addRow("New PIN:", self.pin_new)

        self.pin_confirm = QLineEdit()
        self.pin_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_confirm.setPlaceholderText("Repeat new PIN")
        self.pin_confirm.setMaxLength(6)
        self.pin_confirm.setValidator(digits_only)
        self.pin_confirm.setStyleSheet(INPUT_STYLE)
        self.pin_confirm.returnPressed.connect(lambda: self.pin_confirm.focusNextChild())
        pf.addRow("Confirm PIN:", self.pin_confirm)

        pin_note = QLabel("PIN must be 4–6 digits. Default PIN on first run is 0000.")
        pin_note.setStyleSheet("color:#64748b; font-size:9pt;")
        pin_note.setWordWrap(True)
        pf.addRow("", pin_note)

        btn_change_pin = QPushButton("Change PIN")
        btn_change_pin.setStyleSheet(BTN_PRIMARY)
        btn_change_pin.clicked.connect(self._change_pin)
        pf.addRow("", btn_change_pin)

        layout.addWidget(pin_group)

        # ── Data Backup ───────────────────────────────────────────────────────
        backup_group = QGroupBox("Data Backup")
        backup_group.setStyleSheet(GROUP_STYLE)
        bv = QVBoxLayout(backup_group)
        bv.setContentsMargins(16, 16, 16, 16)
        bv.setSpacing(10)

        backup_note = QLabel(
            "Creates a copy of the database in a folder you choose. "
            "File name: UnitedMobile_Backup_DDMMYYYY.db"
        )
        backup_note.setStyleSheet("color:#64748b; font-size:9pt;")
        backup_note.setWordWrap(True)
        bv.addWidget(backup_note)

        btn_backup = QPushButton("Backup Database")
        btn_backup.setStyleSheet(BTN_SECONDARY)
        btn_backup.setFixedWidth(200)
        btn_backup.clicked.connect(self._backup)
        bv.addWidget(btn_backup)

        layout.addWidget(backup_group)

        # ── Bank Accounts ─────────────────────────────────────────────────────
        bank_group = QGroupBox("Bank Accounts")
        bank_group.setStyleSheet(GROUP_STYLE)
        bk = QVBoxLayout(bank_group)
        bk.setContentsMargins(16, 16, 16, 16)
        bk.setSpacing(10)

        bank_note = QLabel(
            "Add bank accounts used to receive payments. "
            "These appear in the Payment Method selector when making a sale."
        )
        bank_note.setStyleSheet("color:#64748b; font-size:9pt;")
        bank_note.setWordWrap(True)
        bk.addWidget(bank_note)

        self._bank_table = QTableWidget(0, 3)
        self._bank_table.setHorizontalHeaderLabels(["Account Name", "Opening Balance (PKR)", ""])
        self._bank_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._bank_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._bank_table.verticalHeader().setVisible(False)
        self._bank_table.verticalHeader().setDefaultSectionSize(40)
        self._bank_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._bank_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._bank_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._bank_table.setColumnWidth(2, 170)
        self._bank_table.setMinimumHeight(120)
        self._bank_table.setMaximumHeight(300)
        self._bank_table.setSizeAdjustPolicy(
            QAbstractItemView.SizeAdjustPolicy.AdjustToContents
        )
        self._bank_table.setStyleSheet("""
            QTableWidget { background:#ffffff; border:1px solid #e2e8f0; border-radius:6px;
                           gridline-color:#f1f5f9; font-size:10pt; }
            QTableWidget::item { padding:4px 10px; }
            QHeaderView::section { background:#f8fafc; color:#475569; font-weight:bold;
                font-size:9pt; border:none; border-bottom:1px solid #e2e8f0; padding:8px 10px; }
        """)
        bk.addWidget(self._bank_table)

        btn_add_bank = QPushButton("+ Add Bank Account")
        btn_add_bank.setStyleSheet(BTN_PRIMARY)
        btn_add_bank.setFixedWidth(180)
        btn_add_bank.clicked.connect(self._add_bank_account)
        bk.addWidget(btn_add_bank)

        layout.addWidget(bank_group)
        self._refresh_bank_table()

        # ── Opening Balances ──────────────────────────────────────────────────
        ob_group = QGroupBox("Opening Balances")
        ob_group.setStyleSheet(GROUP_STYLE)
        obf = QFormLayout(ob_group)
        obf.setSpacing(10)
        obf.setContentsMargins(16, 16, 16, 16)

        ob_note = QLabel(
            "Set the starting cash in hand and bank balances for the business. "
            "Bank account opening balances can also be edited individually in the "
            "Bank Accounts section above."
        )
        ob_note.setStyleSheet("color:#64748b; font-size:9pt;")
        ob_note.setWordWrap(True)
        obf.addRow(ob_note)

        self._cash_ob_spin = QDoubleSpinBox()
        self._cash_ob_spin.setRange(0, 999_999_999)
        self._cash_ob_spin.setDecimals(0)
        self._cash_ob_spin.setSingleStep(1000)
        self._cash_ob_spin.setGroupSeparatorShown(True)
        try:
            self._cash_ob_spin.setValue(float(get_setting("cash_opening_balance") or 0))
        except Exception:
            self._cash_ob_spin.setValue(0)
        obf.addRow("Cash in Hand Opening Balance (PKR):", self._cash_ob_spin)

        btn_save_ob = QPushButton("Save Opening Balances")
        btn_save_ob.setStyleSheet(BTN_PRIMARY)
        btn_save_ob.setFixedWidth(200)
        btn_save_ob.clicked.connect(self._save_opening_balances)
        obf.addRow("", btn_save_ob)

        layout.addWidget(ob_group)

        # ── Fixed Assets ──────────────────────────────────────────────────────
        fa_group = QGroupBox("Fixed Assets")
        fa_group.setStyleSheet(GROUP_STYLE)
        fav = QVBoxLayout(fa_group)
        fav.setContentsMargins(16, 16, 16, 16)
        fav.setSpacing(10)
        fa_note = QLabel(
            "Record physical assets owned by the shop (furniture, equipment, etc.). "
            "These appear on the Balance Sheet under Fixed Assets."
        )
        fa_note.setStyleSheet("color:#64748b; font-size:9pt;")
        fa_note.setWordWrap(True)
        fav.addWidget(fa_note)
        btn_fa = QPushButton("Manage Fixed Assets")
        btn_fa.setStyleSheet(BTN_SECONDARY)
        btn_fa.setFixedWidth(200)
        btn_fa.clicked.connect(self._open_fixed_assets)
        fav.addWidget(btn_fa)
        layout.addWidget(fa_group)

        # ── Committees ────────────────────────────────────────────────────────
        com_group = QGroupBox("Committees (Comety)")
        com_group.setStyleSheet(GROUP_STYLE)
        comv = QVBoxLayout(com_group)
        comv.setContentsMargins(16, 16, 16, 16)
        comv.setSpacing(10)
        com_note = QLabel(
            "Track committee (comety) obligations. Remaining balances appear "
            "on the Balance Sheet as liabilities."
        )
        com_note.setStyleSheet("color:#64748b; font-size:9pt;")
        com_note.setWordWrap(True)
        comv.addWidget(com_note)
        btn_com = QPushButton("Manage Committees")
        btn_com.setStyleSheet(BTN_SECONDARY)
        btn_com.setFixedWidth(200)
        btn_com.clicked.connect(self._open_committees)
        comv.addWidget(btn_com)
        layout.addWidget(com_group)

        # ── Year End Closing ──────────────────────────────────────────────────
        ye_group = QGroupBox("Year End Closing")
        ye_group.setStyleSheet(GROUP_STYLE)
        yev = QVBoxLayout(ye_group)
        yev.setContentsMargins(16, 16, 16, 16)
        yev.setSpacing(10)

        ye_note = QLabel(
            "Archive all transactions for the year, carry forward closing balances "
            "as opening balances, and start a fresh financial year."
        )
        ye_note.setStyleSheet("color:#64748b; font-size:9pt;")
        ye_note.setWordWrap(True)
        yev.addWidget(ye_note)

        # Financial year date range
        yr_row = QHBoxLayout()
        yr_row.setSpacing(8)
        yr_row.addWidget(QLabel("Financial Year:"))

        self._ye_start = QDateEdit()
        self._ye_start.setDisplayFormat("dd/MM/yyyy")
        self._ye_start.setCalendarPopup(True)
        self._ye_start.setMinimumWidth(120)
        self._ye_end = QDateEdit()
        self._ye_end.setDisplayFormat("dd/MM/yyyy")
        self._ye_end.setCalendarPopup(True)
        self._ye_end.setMinimumWidth(120)

        # Load saved dates
        s_str = get_setting("year_start_date") or ""
        e_str = get_setting("year_end_date") or ""
        try:
            sp = s_str.split("/")
            self._ye_start.setDate(QDate(int(sp[2]), int(sp[1]), int(sp[0])))
        except Exception:
            self._ye_start.setDate(QDate.currentDate().addDays(
                -(QDate.currentDate().dayOfYear() - 1)
            ))
        try:
            ep = e_str.split("/")
            self._ye_end.setDate(QDate(int(ep[2]), int(ep[1]), int(ep[0])))
        except Exception:
            self._ye_end.setDate(QDate(QDate.currentDate().year(), 12, 31))

        yr_row.addWidget(self._ye_start)
        yr_row.addWidget(QLabel("to"))
        yr_row.addWidget(self._ye_end)

        btn_save_yr = QPushButton("Save Dates")
        btn_save_yr.setStyleSheet(BTN_SECONDARY)
        btn_save_yr.setFixedWidth(100)
        btn_save_yr.clicked.connect(self._save_year_dates)
        yr_row.addWidget(btn_save_yr)
        yr_row.addStretch()
        yev.addLayout(yr_row)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#e2e8f0;")
        yev.addWidget(sep)

        # Warning notice
        ye_warn = QLabel(
            "⚠  Before closing: go to Backup Database above and save a manual backup first."
        )
        ye_warn.setStyleSheet(
            "color:#c2410c; font-size:9pt; font-weight:bold;"
        )
        ye_warn.setWordWrap(True)
        yev.addWidget(ye_warn)

        btn_close_yr = QPushButton("Review Summary & Close Year →")
        btn_close_yr.setStyleSheet("""
            QPushButton {
                background:#dc2626; color:white; border:none;
                border-radius:5px; padding:8px 20px; font-size:10pt; font-weight:bold;
            }
            QPushButton:hover { background:#b91c1c; }
        """)
        btn_close_yr.setFixedWidth(280)
        btn_close_yr.clicked.connect(self._close_year)
        yev.addWidget(btn_close_yr)

        layout.addWidget(ye_group)

        # ── System Startup ────────────────────────────────────────────────────
        startup_group = QGroupBox("System Startup")
        startup_group.setStyleSheet(GROUP_STYLE)
        sv = QVBoxLayout(startup_group)
        sv.setContentsMargins(16, 16, 16, 16)
        sv.setSpacing(10)

        startup_note = QLabel(
            "When enabled, United Mobile EPOS launches automatically every time "
            "this Windows account logs in. Staff see the PIN screen immediately "
            "with no extra steps."
        )
        startup_note.setStyleSheet("color:#64748b; font-size:9pt;")
        startup_note.setWordWrap(True)
        sv.addWidget(startup_note)

        from startup import is_startup_registered
        self._startup_chk = QCheckBox("Launch United Mobile EPOS automatically on Windows startup")
        self._startup_chk.setChecked(is_startup_registered())
        self._startup_chk.stateChanged.connect(self._toggle_startup)
        sv.addWidget(self._startup_chk)

        self._startup_status = QLabel("")
        self._startup_status.setStyleSheet("color:#64748b; font-size:9pt;")
        sv.addWidget(self._startup_status)
        self._refresh_startup_status()

        layout.addWidget(startup_group)

        layout.addStretch()

    def _on_printer_mode_changed(self):
        """Show only the fields relevant to the selected connection mode."""
        is_network = self.printer_mode.currentData() == "network"
        # USB row (printer name + Pick) + its note
        self._usb_row_label.setVisible(not is_network)
        for i in range(self._usb_row_widget.count()):
            w = self._usb_row_widget.itemAt(i).widget()
            if w:
                w.setVisible(not is_network)
        self._usb_note.setVisible(not is_network)
        # Network row (IP + port) + its note
        self._net_row_label.setVisible(is_network)
        for i in range(self._net_row_widget.count()):
            w = self._net_row_widget.itemAt(i).widget()
            if w:
                w.setVisible(is_network)
        self._net_note.setVisible(is_network)

    def _save(self):
        set_setting("shop_name",       self.shop_name.text().strip())
        set_setting("shop_address",    self.shop_address.text().strip())
        set_setting("shop_contact",    self.shop_contact.text().strip())
        set_setting("thermal_printer", self.printer_name.text().strip())
        set_setting("receipt_footer",  self.receipt_footer.text().strip())
        set_setting("whatsapp_template", self.wa_template.toPlainText().strip())
        set_setting("owner_whatsapp",    self.owner_whatsapp.text().strip())

        # Printer connection mode
        set_setting("printer_mode", self.printer_mode.currentData() or "usb")
        set_setting("printer_ip",   self.printer_ip.text().strip())
        port = self.printer_port.text().strip() or "9100"
        set_setting("printer_port", port)

        QMessageBox.information(self, "Saved", "Settings saved successfully.")

    def _change_pin(self):
        current = self.pin_current.text()
        new = self.pin_new.text()
        confirm = self.pin_confirm.text()
        if not current or not new or not confirm:
            QMessageBox.warning(self, "Validation", "All three PIN fields are required.")
            return
        if len(new) < 4:
            QMessageBox.warning(self, "Validation", "New PIN must be at least 4 digits.")
            return
        if new != confirm:
            QMessageBox.warning(self, "Validation", "New PIN and confirmation do not match.")
            return
        if not check_pin(current):
            QMessageBox.warning(self, "Incorrect PIN", "Current PIN is incorrect.")
            self.pin_current.clear()
            self.pin_current.setFocus()
            return
        set_pin(new)
        self.pin_current.clear()
        self.pin_new.clear()
        self.pin_confirm.clear()
        QMessageBox.information(self, "PIN Changed", "PIN changed successfully.")

    def _backup(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose Backup Folder", "")
        if not folder:
            return
        today = _date.today().strftime("%d%m%Y")
        backup_name = f"UnitedMobile_Backup_{today}.db"
        backup_path = os.path.join(folder, backup_name)
        try:
            shutil.copy2(DB_PATH, backup_path)
            QMessageBox.information(self, "Backup Saved", f"Backup saved to:\n{backup_path}")
        except Exception as e:
            QMessageBox.critical(self, "Backup Failed", f"Could not save backup:\n{e}")

    # ── Bank account management ───────────────────────────────────────────────

    def _refresh_bank_table(self):
        accounts = db_bank_accounts()
        self._bank_table.setRowCount(0)
        for acc in accounts:
            r = self._bank_table.rowCount()
            self._bank_table.insertRow(r)
            self._bank_table.setItem(r, 0, QTableWidgetItem(acc["name"]))
            bal_item = QTableWidgetItem(f"{acc['opening_balance']:,.0f}")
            bal_item.setTextAlignment(0x0082)  # AlignRight | AlignVCenter
            self._bank_table.setItem(r, 1, bal_item)

            btn_row = QWidget()
            btn_layout = QHBoxLayout(btn_row)
            btn_layout.setContentsMargins(6, 4, 6, 4)
            btn_layout.setSpacing(6)

            btn_edit = QPushButton("Edit")
            btn_edit.setStyleSheet(BTN_SECONDARY)
            btn_edit.setFixedHeight(30)
            btn_edit.clicked.connect(lambda _, a=acc: self._edit_bank_account(a))

            btn_del = QPushButton("Delete")
            btn_del.setStyleSheet("""
                QPushButton { background:#fee2e2; color:#dc2626; border:none;
                    border-radius:4px; padding:4px 10px; font-size:9pt; }
                QPushButton:hover { background:#fecaca; }
            """)
            btn_del.setFixedHeight(30)
            btn_del.clicked.connect(lambda _, aid=acc["id"]: self._delete_bank_account(aid))

            btn_layout.addWidget(btn_edit)
            btn_layout.addWidget(btn_del)
            self._bank_table.setCellWidget(r, 2, btn_row)

    def _bank_account_dialog(self, title, name="", opening_balance=0.0):
        """Shared add/edit dialog. Returns (name, balance) or None on cancel."""
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumWidth(340)
        outer = QVBoxLayout(dlg)
        outer.setContentsMargins(20, 20, 20, 16)
        outer.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        name_edit = QLineEdit(name)
        name_edit.setPlaceholderText("e.g. MCB Current Account")
        name_edit.returnPressed.connect(lambda: name_edit.focusNextChild())
        form.addRow("Account Name:", name_edit)

        bal_spin = QDoubleSpinBox()
        bal_spin.setRange(0, 999_999_999)
        bal_spin.setDecimals(0)
        bal_spin.setSingleStep(1000)
        bal_spin.setGroupSeparatorShown(True)
        bal_spin.setValue(opening_balance)
        form.addRow("Opening Balance (PKR):", bal_spin)

        outer.addLayout(form)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        outer.addWidget(btns)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            n = name_edit.text().strip()
            if not n:
                QMessageBox.warning(self, "Validation", "Account name cannot be empty.")
                return None
            return n, bal_spin.value()
        return None

    def _add_bank_account(self):
        result = self._bank_account_dialog("Add Bank Account")
        if result:
            name, bal = result
            db_save_bank_account(name, bal)
            self._refresh_bank_table()

    def _edit_bank_account(self, acc):
        result = self._bank_account_dialog(
            "Edit Bank Account", acc["name"], acc["opening_balance"]
        )
        if result:
            name, bal = result
            db_save_bank_account(name, bal, account_id=acc["id"])
            self._refresh_bank_table()

    def _delete_bank_account(self, account_id):
        reply = QMessageBox.question(
            self, "Delete Account",
            "Delete this bank account?\n\nAccounts used in existing sales cannot be deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            if db_delete_bank_account(account_id):
                self._refresh_bank_table()
            else:
                QMessageBox.warning(
                    self, "Cannot Delete",
                    "This account is used in one or more sales and cannot be deleted."
                )

    # ── Year End Closing ──────────────────────────────────────────────────────

    def _save_year_dates(self):
        s = self._ye_start.date().toString("dd/MM/yyyy")
        e = self._ye_end.date().toString("dd/MM/yyyy")
        set_setting("year_start_date", s)
        set_setting("year_end_date",   e)
        QMessageBox.information(self, "Saved", f"Financial year set to:\n{s}  →  {e}")

    def _close_year(self):
        # Save dates first
        s_date = self._ye_start.date()
        e_date = self._ye_end.date()
        if s_date >= e_date:
            QMessageBox.warning(
                self, "Invalid Dates",
                "Year end date must be after year start date."
            )
            return

        s_str = s_date.toString("dd/MM/yyyy")
        e_str = e_date.toString("dd/MM/yyyy")
        set_setting("year_start_date", s_str)
        set_setting("year_end_date",   e_str)

        year_label = f"{s_str} to {e_str}"
        # ISO format for DB queries
        s_iso = s_date.toString("yyyy-MM-dd")
        e_iso = e_date.toString("yyyy-MM-dd")

        # Gather summary data (may take a moment with many parties)
        try:
            summary = db_year_end_summary(s_iso, e_iso)
        except Exception as ex:
            QMessageBox.critical(self, "Error", f"Could not load summary:\n{ex}")
            return

        dlg = YearEndCloseDialog(summary, year_label, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        # Generate archive filename using the year-end year
        archive_year = str(e_date.year())
        archive_name = f"UnitedMobile_Archive_{archive_year}.db"
        archive_path = os.path.join(dlg.archive_folder(), archive_name)

        # Check if archive already exists
        if os.path.exists(archive_path):
            ans = QMessageBox.question(
                self, "File Exists",
                f"{archive_name} already exists in that folder.\nOverwrite?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return

        try:
            db_perform_year_end_close(archive_path)
        except Exception as ex:
            QMessageBox.critical(
                self, "Year End Failed",
                f"An error occurred during year end closing:\n{ex}\n\n"
                "The database has NOT been modified. Your archive copy may still have been saved."
            )
            return

        # Advance the financial year dates by 1 year
        new_start = s_date.addYears(1)
        new_end   = e_date.addYears(1)
        self._ye_start.setDate(new_start)
        self._ye_end.setDate(new_end)
        set_setting("year_start_date", new_start.toString("dd/MM/yyyy"))
        set_setting("year_end_date",   new_end.toString("dd/MM/yyyy"))

        QMessageBox.information(
            self, "Year End Complete",
            f"✅ Year End Closing completed successfully.\n\n"
            f"Archive saved to:\n{archive_path}\n\n"
            f"New financial year: {new_start.toString('dd/MM/yyyy')} to {new_end.toString('dd/MM/yyyy')}\n\n"
            f"All voucher sequences have been reset to 0001.\n"
            f"Closing balances have been carried forward as opening balances."
        )

    # ── Windows Startup ───────────────────────────────────────────────────────

    def _refresh_startup_status(self):
        from startup import is_startup_registered
        if is_startup_registered():
            self._startup_status.setText("✅  Registered — app will launch automatically on login.")
            self._startup_status.setStyleSheet("color:#16a34a; font-size:9pt;")
        else:
            self._startup_status.setText("⬜  Not registered — app must be started manually.")
            self._startup_status.setStyleSheet("color:#64748b; font-size:9pt;")

    def _toggle_startup(self, state):
        from startup import register_startup, unregister_startup
        from database import set_setting
        import sys
        if sys.platform != "win32":
            QMessageBox.information(
                self, "Not Supported",
                "Windows startup registration is only available on Windows."
            )
            return
        if state == 2:   # Qt.CheckState.Checked
            ok = register_startup()
            if ok:
                set_setting("startup_registered", "1")
                QMessageBox.information(
                    self, "Startup Enabled",
                    "United Mobile EPOS will now launch automatically\n"
                    "every time this Windows account logs in."
                )
            else:
                QMessageBox.warning(
                    self, "Failed",
                    "Could not write to the Windows registry.\n"
                    "Try running the app as Administrator once."
                )
                self._startup_chk.blockSignals(True)
                self._startup_chk.setChecked(False)
                self._startup_chk.blockSignals(False)
        else:
            unregister_startup()
            set_setting("startup_registered", "0")
            QMessageBox.information(
                self, "Startup Disabled",
                "Auto-launch has been disabled.\n"
                "You will need to open the app manually."
            )
        self._refresh_startup_status()

    def _save_opening_balances(self):
        set_setting("cash_opening_balance", str(int(self._cash_ob_spin.value())))
        QMessageBox.information(self, "Saved", "Cash opening balance saved.")

    def _open_fixed_assets(self):
        from fixed_assets import FixedAssetsDialog
        FixedAssetsDialog(self).exec()

    def _open_committees(self):
        from committees import CommitteesDialog
        CommitteesDialog(self).exec()

    def _pick_printer(self):
        """Show a dialog listing all installed Windows printers; click one to select it."""
        from receipt import list_windows_printers
        printers = list_windows_printers()

        if not printers:
            QMessageBox.warning(self, "No Printers Found",
                "No printers were detected on this Windows account.\n\n"
                "Make sure the Blackcopper BC-85AC is installed in\n"
                "Windows Settings → Bluetooth & devices → Printers & scanners.")
            return

        from PyQt6.QtWidgets import (
            QDialog, QVBoxLayout, QListWidget, QListWidgetItem, QDialogButtonBox, QLabel
        )
        dlg = QDialog(self)
        dlg.setWindowTitle("Pick Thermal Printer")
        dlg.setMinimumWidth(420)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(10)
        v.addWidget(QLabel("Double-click a printer to select it, then click Save All Settings:"))
        lst = QListWidget()
        lst.setStyleSheet("""
            QListWidget { border:1px solid #cbd5e1; border-radius:4px; font-size:10pt; }
            QListWidget::item { padding:7px 12px; }
            QListWidget::item:hover { background:#dbeafe; }
            QListWidget::item:selected { background:#2563eb; color:white; }
        """)
        for name in printers:
            item = QListWidgetItem(name)
            lst.addItem(item)
            # Pre-select if it already matches
            if name == self.printer_name.text().strip():
                lst.setCurrentItem(item)

        def _pick(item):
            self.printer_name.setText(item.text())
            dlg.accept()

        lst.itemDoubleClicked.connect(_pick)
        v.addWidget(lst)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(lambda: _pick(lst.currentItem()) if lst.currentItem() else dlg.reject())
        btns.rejected.connect(dlg.reject)
        v.addWidget(btns)
        dlg.exec()

    def _test_print(self):
        from receipt import (
            build_receipt_text, _print_raw, _show_preview, _print_target_ready,
        )
        # Persist the current printer config first so the test uses exactly
        # what's on screen (mode/IP/port/name), then print fresh.
        set_setting("printer_mode", self.printer_mode.currentData() or "usb")
        set_setting("printer_ip",   self.printer_ip.text().strip())
        set_setting("printer_port", self.printer_port.text().strip() or "9100")
        set_setting("thermal_printer", self.printer_name.text().strip())

        text = build_receipt_text(
            sv_number     = "SV-TEST",
            date_str      = "30/05/2026",
            customer_name = "Test Customer",
            lines         = [("SAMSUNG", "A17 8+256", "356789012345670", 59500)],
            discount      = 500,
            total         = 59000,
            note          = "",
            shop_name     = self.shop_name.text().strip() or "United Mobile",
            shop_address  = self.shop_address.text().strip() or "Kutchery Road, Multan",
            shop_contact  = self.shop_contact.text().strip() or "0323-9637000",
            footer_msg    = self.receipt_footer.text().strip() or "Thank you for your purchase!",
        )
        printer = self.printer_name.text().strip()
        if _print_target_ready(printer):
            try:
                _print_raw(printer, text)
                QMessageBox.information(self, "Test Print",
                    "Test receipt sent successfully.")
                return
            except Exception as e:
                QMessageBox.warning(self, "Test Print Failed", str(e))
                return
        # Nothing configured — show preview
        _show_preview(text, "SV-TEST", self)
