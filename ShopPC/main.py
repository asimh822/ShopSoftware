import sys
import os
import socket
import subprocess
import threading
from datetime import date as _date
from PyQt6.QtWidgets import (
    QApplication, QDialog, QMainWindow,
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
    QStackedWidget, QFrame,
    QDoubleSpinBox, QSpinBox, QComboBox, QDateEdit, QLineEdit,
)
from PyQt6.QtCore import Qt, QObject, QEvent, QTimer
from PyQt6.QtGui import QFont

from database import init_db
from login import LoginDialog
from masters import MastersPage
from purchase import PurchasePage
from sales import SalePage
from ledger import LedgerPage
from expenses import ExpensesPage
from reports import ReportsPage
from whatsapp_page import WhatsAppPage
from settings_page import SettingsPage
from capital import CapitalPage
from balance_sheet import BalanceSheetPage

# ── API Server subprocess management ─────────────────────────────────────────

_api_proc: subprocess.Popen | None = None   # module-level handle


def _is_port_in_use(port: int) -> bool:
    """Return True if something is already listening on localhost:port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.connect(("127.0.0.1", port))
            return True
        except (ConnectionRefusedError, OSError):
            return False


def _start_api_server() -> None:
    """Launch api_server.py as a hidden background process.

    Skipped silently if port 5000 is already occupied (server already up).
    Works both in source mode (python main.py) and as a PyInstaller bundle.
    """
    global _api_proc

    if _is_port_in_use(5000):
        print("API server already running on port 5000 — skipping launch")
        return

    # Locate api_server.py — same folder as the running script / frozen exe
    base_dir = (
        os.path.dirname(sys.executable)
        if getattr(sys, "frozen", False)
        else os.path.dirname(os.path.abspath(__file__))
    )
    api_script = os.path.join(base_dir, "api_server.py")

    if not os.path.exists(api_script):
        print(f"WARNING: api_server.py not found at {api_script} — mobile app will not work")
        return

    # When frozen, sys.executable is the .exe, not python.exe.
    # Fall back to the python.exe on PATH.
    if getattr(sys, "frozen", False):
        import shutil
        python_exe = shutil.which("python") or shutil.which("python3") or sys.executable
    else:
        python_exe = sys.executable

    kwargs: dict = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    try:
        _api_proc = subprocess.Popen([python_exe, api_script], **kwargs)
        print("API server started on port 5000")
    except Exception as exc:
        print(f"WARNING: Could not start API server: {exc}")


def _stop_api_server() -> None:
    """Terminate the API server process if we own it."""
    global _api_proc
    if _api_proc is not None and _api_proc.poll() is None:
        _api_proc.terminate()
        try:
            _api_proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            _api_proc.kill()
        print("API server stopped.")
    _api_proc = None


# ─────────────────────────────────────────────────────────────────────────────

NAV_ITEMS = [
    ("Dashboard",   "dashboard"),
    ("Masters",     "masters"),
    ("Purchase",    "purchase"),
    ("Sales",       "sales"),
    ("Ledger",      "ledger"),
    ("Capital",     "capital"),
    ("Expenses",    "expenses"),
    ("Reports",     "reports"),
    ("Bal. Sheet",  "balance_sheet"),
    ("WhatsApp",    "whatsapp"),
    ("Settings",    "settings"),
]

SIDEBAR_W = 180
SIDEBAR_BG = "#000000"
SIDEBAR_HOVER = "#1a1a1a"
SIDEBAR_ACTIVE = "#2563eb"
HEADER_BG = "#000000"
HEADER_BORDER = "#1a1a1a"
CONTENT_BG = "#f1f5f9"


class EnterAsTabFilter(QObject):
    """Convert Return/Enter to Tab navigation for all input widgets.

    Rules:
    • QDoubleSpinBox / QSpinBox / QComboBox / QDateEdit  → focusNextChild()
    • QLineEdit  → focusNextChild()  UNLESS the widget has
      property("enterKeepDefault") == True  (used on IMEI search fields
      that need their own returnPressed handler).
    • QPushButton  → click()  (Enter activates a focused button, which
      Qt does not do by default outside of dialogs).
    """
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if isinstance(obj, (QDoubleSpinBox, QSpinBox, QComboBox, QDateEdit)):
                    obj.focusNextChild()
                    return True
                if isinstance(obj, QLineEdit):
                    if not obj.property("enterKeepDefault"):
                        obj.focusNextChild()
                        return True
                if isinstance(obj, QPushButton):
                    if obj.isEnabled() and obj.isVisible():
                        obj.click()
                        return True
        return False


class NavButton(QPushButton):
    def __init__(self, label: str, parent=None):
        super().__init__(label, parent)
        self.setCheckable(True)
        self.setFixedHeight(46)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self._apply_style(False)

    def _apply_style(self, active: bool):
        if active:
            bg = SIDEBAR_ACTIVE
            fg = "#ffffff"
            border = "border-left: 3px solid #93c5fd;"
        else:
            bg = SIDEBAR_BG
            fg = "#ffffff"
            border = "border-left: 3px solid transparent;"
        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg};
                color: {fg};
                {border}
                border-radius: 0px;
                text-align: left;
                padding-left: 20px;
                font-weight: bold;
                font-size: 12pt;
            }}
            QPushButton:hover {{
                background: {SIDEBAR_HOVER};
                color: #ffffff;
            }}
        """)

    def setActive(self, active: bool):
        self._apply_style(active)
        self.setChecked(active)


class Sidebar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(SIDEBAR_W)
        self.setStyleSheet(f"background: {SIDEBAR_BG};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Logo / shop name
        logo = QLabel("United Mobile")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        logo.setStyleSheet("color: #ffffff; padding: 20px 0 8px 0;")
        logo.setFixedHeight(60)
        layout.addWidget(logo)

        sub = QLabel("EPOS System")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setFont(QFont("Segoe UI", 9))
        sub.setStyleSheet("color: #64748b; padding-bottom: 14px;")
        sub.setFixedHeight(28)
        layout.addWidget(sub)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #2e3f57;")
        layout.addWidget(sep)

        layout.addSpacing(8)

        self.buttons: dict[str, NavButton] = {}
        for label, key in NAV_ITEMS:
            btn = NavButton(label)
            self.buttons[key] = btn
            layout.addWidget(btn)

        layout.addStretch()

        version = QLabel("v1.0")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setStyleSheet("color: #475569; font-size: 10px; padding: 8px;")
        layout.addWidget(version)

    def set_active(self, key: str):
        for k, btn in self.buttons.items():
            btn.setActive(k == key)


class PlaceholderPage(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {CONTENT_BG};")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl = QLabel(title)
        lbl.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        lbl.setStyleSheet("color: #334155;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub = QLabel("Module coming soon")
        sub.setFont(QFont("Segoe UI", 11))
        sub.setStyleSheet("color: #94a3b8;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl)
        layout.addWidget(sub)


def _fmt_pkr(val):
    if val is None:
        return "0"
    return f"{float(val):,.0f}"


class DashboardPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {CONTENT_BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(20)

        title = QLabel("Dashboard")
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        title.setStyleSheet("color: #1e293b;")
        layout.addWidget(title)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(16)

        self._val_labels = {}
        card_defs = [
            ("cash_in_hand", "Cash in Hand",           "PKR", "#0891b2"),
            ("sales",        "Today's Sales",          "PKR", "#16a34a"),
            ("purchases",    "Today's Purchases",      "PKR", "#7c3aed"),
            ("customers",    "Customers Outstanding",  "PKR", "#d97706"),
            ("suppliers",    "Suppliers Outstanding",  "PKR", "#dc2626"),
        ]
        for key, label, unit, color in card_defs:
            card, val_lbl = self._make_card(label, unit, color)
            cards_row.addWidget(card)
            self._val_labels[key] = val_lbl

        bank_card = self._make_bank_card()
        cards_row.addWidget(bank_card)

        cap_card, self._capital_val_lbl = self._make_card("Total Capital", "PKR", "#8e44ad")
        cards_row.addWidget(cap_card)

        layout.addLayout(cards_row)

        # ── Today's Sales by Salesman ─────────────────────────────────────────
        sm_section = QWidget()
        sm_section.setStyleSheet("background:transparent;")
        sm_vl = QVBoxLayout(sm_section)
        sm_vl.setContentsMargins(0, 0, 0, 0)
        sm_vl.setSpacing(8)

        sm_title = QLabel("Today's Sales by Salesman")
        sm_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        sm_title.setStyleSheet("color:#1e293b;")
        sm_vl.addWidget(sm_title)

        from PyQt6.QtWidgets import QTableWidget, QHeaderView, QAbstractItemView
        self._sm_table = QTableWidget(0, 3)
        self._sm_table.setHorizontalHeaderLabels(["Salesman", "Units Sold", "Total Sales (PKR)"])
        self._sm_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._sm_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._sm_table.setAlternatingRowColors(True)
        self._sm_table.verticalHeader().setVisible(False)
        hdr = self._sm_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._sm_table.setMaximumHeight(200)
        self._sm_table.setStyleSheet("""
            QTableWidget {
                background:#ffffff; border:1px solid #e2e8f0;
                border-radius:8px; gridline-color:#f1f5f9; font-size:10pt;
            }
            QTableWidget::item { padding:6px 12px; }
            QTableWidget::item:alternate { background:#f8fafc; }
            QHeaderView::section {
                background:#f8fafc; color:#475569; font-weight:bold; font-size:9pt;
                border:none; border-bottom:1px solid #e2e8f0; padding:6px 12px;
            }
        """)
        sm_vl.addWidget(self._sm_table)
        layout.addWidget(sm_section)
        layout.addStretch()

    def _make_card(self, title: str, unit: str, color: str):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {color};
                border-radius: 10px;
            }}
        """)
        card.setFixedHeight(120)
        v = QVBoxLayout(card)
        v.setContentsMargins(18, 14, 18, 14)
        v.setSpacing(4)
        lbl = QLabel(title)
        lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        lbl.setStyleSheet("color: rgba(255,255,255,0.85); border: none;")
        lbl.setWordWrap(True)
        val = QLabel("—")
        val.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        val.setStyleSheet("color: #ffffff; border: none;")
        unit_lbl = QLabel(unit)
        unit_lbl.setFont(QFont("Segoe UI", 8))
        unit_lbl.setStyleSheet("color: rgba(255,255,255,0.7); border: none;")
        v.addWidget(lbl)
        v.addWidget(val)
        v.addWidget(unit_lbl)
        return card, val

    def _make_bank_card(self):
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background: #0284c7;
                border-radius: 10px;
            }
        """)
        card.setFixedHeight(120)
        v = QVBoxLayout(card)
        v.setContentsMargins(18, 10, 14, 12)
        v.setSpacing(2)

        title_lbl = QLabel("Total Bank Balance")
        title_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color: rgba(255,255,255,0.85); border: none;")
        v.addWidget(title_lbl)

        self._bank_acct_lbl = QLabel("Manage accounts in Settings")
        self._bank_acct_lbl.setFont(QFont("Segoe UI", 8))
        self._bank_acct_lbl.setStyleSheet("color: rgba(255,255,255,0.7); border: none;")
        v.addWidget(self._bank_acct_lbl)

        self._bank_val_lbl = QLabel("—")
        self._bank_val_lbl.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        self._bank_val_lbl.setStyleSheet("color: #ffffff; border: none;")
        v.addWidget(self._bank_val_lbl)

        unit_lbl = QLabel("PKR")
        unit_lbl.setFont(QFont("Segoe UI", 8))
        unit_lbl.setStyleSheet("color: rgba(255,255,255,0.7); border: none;")
        v.addWidget(unit_lbl)

        return card

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh()

    def _refresh(self):
        from database import get_connection
        try:
            conn = get_connection()
            today = _date.today().strftime("%d/%m/%Y")

            from database import db_cash_in_hand
            cash_in_hand = db_cash_in_hand()

            today_sales = conn.execute(
                "SELECT COALESCE(SUM(total_amount), 0) FROM sale_vouchers WHERE date=?",
                (today,),
            ).fetchone()[0]

            today_purchases = conn.execute(
                "SELECT COALESCE(SUM(total_amount), 0) FROM purchase_vouchers WHERE date=?",
                (today,),
            ).fetchone()[0]

            sup_outstanding = conn.execute("""
                SELECT
                    COALESCE((SELECT SUM(opening_balance) FROM suppliers WHERE id != 0), 0) +
                    COALESCE((SELECT SUM(total_amount) FROM purchase_vouchers WHERE supplier_id != 0), 0) -
                    COALESCE((SELECT SUM(amount) FROM payments WHERE party_type='supplier' AND type='CP'), 0) +
                    COALESCE((SELECT SUM(amount) FROM journal_entries WHERE party_type='supplier' AND type='debit'), 0) -
                    COALESCE((SELECT SUM(amount) FROM journal_entries WHERE party_type='supplier' AND type='credit'), 0)
            """).fetchone()[0]

            cust_outstanding = conn.execute("""
                SELECT
                    COALESCE((SELECT SUM(opening_balance) FROM customers WHERE type='credit'), 0) +
                    COALESCE((SELECT SUM(sv.total_amount) FROM sale_vouchers sv WHERE sv.type='credit'), 0) -
                    COALESCE((SELECT SUM(amount) FROM payments WHERE party_type='customer' AND type='CR'), 0) -
                    COALESCE((SELECT SUM(amount) FROM journal_entries WHERE party_type='customer' AND type='debit'), 0) +
                    COALESCE((SELECT SUM(amount) FROM journal_entries WHERE party_type='customer' AND type='credit'), 0)
            """).fetchone()[0]

            conn.close()

            self._val_labels["cash_in_hand"].setText(_fmt_pkr(cash_in_hand))
            self._val_labels["sales"].setText(_fmt_pkr(today_sales))
            self._val_labels["purchases"].setText(_fmt_pkr(today_purchases))
            self._val_labels["customers"].setText(_fmt_pkr(cust_outstanding))
            self._val_labels["suppliers"].setText(_fmt_pkr(sup_outstanding))

            # ── Salesman table ────────────────────────────────────────────────
            from database import db_today_sales_by_salesman
            sm_rows = db_today_sales_by_salesman(today)
            self._sm_table.setRowCount(0)
            for r in sm_rows:
                row_idx = self._sm_table.rowCount()
                self._sm_table.insertRow(row_idx)
                from PyQt6.QtWidgets import QTableWidgetItem
                from PyQt6.QtCore import Qt
                self._sm_table.setItem(row_idx, 0, QTableWidgetItem(r["name"]))
                units_item = QTableWidgetItem(str(r["units"]))
                units_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._sm_table.setItem(row_idx, 1, units_item)
                amt_item = QTableWidgetItem(_fmt_pkr(r["total_amount"]))
                amt_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                self._sm_table.setItem(row_idx, 2, amt_item)

            from database import db_bank_accounts, db_bank_total_balance
            bank_accounts = db_bank_accounts()
            if bank_accounts:
                names = ", ".join(a["name"] for a in bank_accounts[:2])
                if len(bank_accounts) > 2:
                    names += f" (+{len(bank_accounts) - 2} more)"
                self._bank_acct_lbl.setText(names)
            else:
                self._bank_acct_lbl.setText("Add accounts in Settings")
            self._bank_val_lbl.setText(_fmt_pkr(db_bank_total_balance()))

            from capital import get_total_capital, get_db
            _cconn = get_db()
            self._capital_val_lbl.setText(_fmt_pkr(get_total_capital(_cconn)))
            _cconn.close()
        except Exception:
            pass


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("United Mobile EPOS")
        self.setMinimumSize(1100, 680)
        self.resize(1280, 780)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = Sidebar()
        root.addWidget(self.sidebar)

        # Right side: header bar on top, content stack below
        right = QWidget()
        right.setStyleSheet(f"background: {CONTENT_BG};")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self._header_bar = self._make_header_bar()
        right_layout.addWidget(self._header_bar)

        self.stack = QStackedWidget()
        self.stack.setStyleSheet(f"background: {CONTENT_BG};")
        right_layout.addWidget(self.stack, stretch=1)

        # Notification bar — hidden by default, shown briefly after auto-backup
        self._notif_bar = self._make_notif_bar()
        right_layout.addWidget(self._notif_bar)

        root.addWidget(right, stretch=1)

        self._pages: dict[str, QWidget] = {}
        self._register_page("dashboard", DashboardPage())
        self._register_page("masters", MastersPage())
        self._register_page("purchase", PurchasePage())
        self._register_page("sales", SalePage())
        self._register_page("ledger", LedgerPage())
        self._register_page("capital", CapitalPage())
        self._register_page("expenses", ExpensesPage())
        self._register_page("reports", ReportsPage())
        self._register_page("balance_sheet", BalanceSheetPage())
        self._register_page("whatsapp", WhatsAppPage())
        self._register_page("settings", SettingsPage())

        for key, btn in self.sidebar.buttons.items():
            btn.clicked.connect(lambda checked, k=key: self._navigate(k))

        # Wire "Use in Sale" from IMEI Stock report → Sales form
        reports_page = self._pages.get("reports")
        if reports_page and hasattr(reports_page, "set_use_in_sale_cb"):
            reports_page.set_use_in_sale_cb(self._use_imei_in_sale)

        self._navigate("dashboard")

        # Kick off auto-backup 800 ms after the window is ready
        # (runs in a daemon thread so startup is never blocked)
        QTimer.singleShot(800, self._start_auto_backup)

    # ── Auto Monthly Backup ───────────────────────────────────────────────────

    def _make_notif_bar(self) -> QFrame:
        bar = QFrame()
        bar.setFixedHeight(36)
        bar.setStyleSheet(
            "background:#16a34a; border:none;"
        )
        hl = QHBoxLayout(bar)
        hl.setContentsMargins(20, 0, 20, 0)
        self._notif_label = QLabel("")
        self._notif_label.setFont(QFont("Segoe UI", 9))
        self._notif_label.setStyleSheet("color:#ffffff; background:transparent;")
        hl.addWidget(self._notif_label)
        hl.addStretch()
        bar.hide()
        return bar

    def _start_auto_backup(self):
        """Launch the backup check in a daemon thread; post result to UI on completion."""
        def _worker():
            try:
                from database import db_auto_backup_if_needed
                path = db_auto_backup_if_needed()
            except Exception:
                path = None
            if path:
                # QTimer.singleShot is thread-safe: schedules callback on the main thread
                QTimer.singleShot(0, lambda p=path: self._show_backup_notification(p))

        threading.Thread(target=_worker, daemon=True).start()

    def _show_backup_notification(self, backup_path: str):
        self._notif_label.setText(
            f"✅  Monthly backup saved to {backup_path}"
        )
        self._notif_bar.show()
        QTimer.singleShot(5000, self._notif_bar.hide)

    def _make_header_bar(self) -> QFrame:
        bar = QFrame()
        bar.setFixedHeight(52)
        bar.setStyleSheet(
            f"background: {HEADER_BG}; border-bottom: 2px solid {HEADER_BORDER};"
        )
        hl = QHBoxLayout(bar)
        hl.setContentsMargins(24, 0, 24, 0)
        hl.setSpacing(0)

        self._header_page_label = QLabel("Dashboard")
        self._header_page_label.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self._header_page_label.setStyleSheet("color: #ffffff; background: transparent;")
        hl.addWidget(self._header_page_label)

        hl.addStretch()

        shop_lbl = QLabel("United Mobile EPOS")
        shop_lbl.setFont(QFont("Segoe UI", 10))
        shop_lbl.setStyleSheet("color: #64748b; background: transparent;")
        hl.addWidget(shop_lbl)

        return bar

    def _register_page(self, key: str, page: QWidget):
        self._pages[key] = page
        self.stack.addWidget(page)

    def _navigate(self, key: str):
        self.sidebar.set_active(key)
        self.stack.setCurrentWidget(self._pages[key])
        label = dict(NAV_ITEMS).get(key, key.capitalize())
        self._header_page_label.setText(label)

    def _use_imei_in_sale(self, imei: str):
        sales_page = self._pages.get("sales")
        if sales_page:
            self._navigate("sales")
            sales_page.new_sale_with_imei(imei)

    def swap_page(self, key: str, widget: QWidget):
        old = self._pages.get(key)
        if old:
            self.stack.removeWidget(old)
            old.deleteLater()
        self._register_page(key, widget)
        self._navigate(key)

    def closeEvent(self, event):
        """Clean up the API server subprocess before the window closes."""
        _stop_api_server()
        event.accept()


def _auto_register_startup() -> None:
    """Register for Windows startup on the very first run after installation.

    Writes the registry key once, then marks 'startup_registered' = '1' in
    settings so the check is skipped on every subsequent launch.
    The user can toggle this off later from the Settings page.
    """
    if sys.platform != "win32":
        return
    from database import get_setting, set_setting
    if get_setting("startup_registered") == "1":
        return                       # already done — skip silently
    from startup import register_startup
    if register_startup():
        set_setting("startup_registered", "1")
        print("Auto-launch on Windows startup enabled.")


def main():
    init_db()
    _start_api_server()
    _auto_register_startup()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    _enter_filter = EnterAsTabFilter(app)
    app.installEventFilter(_enter_filter)
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet("""
        QWidget { color: #1e293b; }
        QMainWindow, QDialog { background: #f1f5f9; }
        QLabel { color: #1e293b; background: transparent; }

        QLineEdit {
            background: #ffffff; color: #1e293b;
            border: 1px solid #cbd5e1; border-radius: 4px; padding: 5px 8px;
        }
        QLineEdit:focus { border: 2px solid #2563eb; }
        QLineEdit:disabled { background: #f1f5f9; color: #94a3b8; border-color: #e2e8f0; }

        QTextEdit {
            background: #ffffff; color: #1e293b;
            border: 1px solid #cbd5e1; border-radius: 4px; padding: 4px 8px;
        }

        QDoubleSpinBox, QSpinBox {
            background: #ffffff; color: #1e293b;
            border: 1px solid #cbd5e1; border-radius: 4px; padding: 4px 8px;
        }
        QDoubleSpinBox:disabled, QSpinBox:disabled {
            background: #f1f5f9; color: #94a3b8; border-color: #e2e8f0;
        }

        QComboBox {
            background: #ffffff; color: #1e293b;
            border: 1px solid #cbd5e1; border-radius: 4px; padding: 5px 8px;
        }
        QComboBox:disabled { background: #f1f5f9; color: #94a3b8; border-color: #e2e8f0; }
        QComboBox QAbstractItemView {
            background: #ffffff; color: #1e293b;
            selection-background-color: #dbeafe; selection-color: #1e40af;
            border: 1px solid #e2e8f0; outline: none;
        }
        QComboBox::drop-down { border: none; }

        QDateEdit {
            background: #ffffff; color: #1e293b;
            border: 1px solid #cbd5e1; border-radius: 4px; padding: 5px 8px;
        }
        QDateEdit:disabled { background: #f1f5f9; color: #94a3b8; border-color: #e2e8f0; }
        QDateEdit QAbstractItemView {
            background: #ffffff; color: #1e293b;
            selection-background-color: #dbeafe; selection-color: #1e40af;
        }

        QPushButton {
            background: #f1f5f9; color: #334155;
            border: 1px solid #cbd5e1; border-radius: 5px; padding: 6px 16px;
        }
        QPushButton:hover { background: #e2e8f0; color: #1e293b; }
        QPushButton:disabled { color: #94a3b8; border-color: #e2e8f0; background: #f8fafc; }

        QTableWidget {
            background: #ffffff; color: #1e293b;
            gridline-color: #f1f5f9; border: 1px solid #e2e8f0;
        }
        QTableWidget::item { color: #1e293b; padding: 6px 10px; }
        QTableWidget::item:selected { background: #dbeafe; color: #1e40af; }
        QTableWidget::item:alternate { background: #f8fafc; }
        QTableWidget QTableCornerButton::section { background: #f8fafc; }

        QHeaderView::section {
            background: #f8fafc; color: #475569; font-weight: bold;
            font-size: 9pt; border: none;
            border-bottom: 1px solid #e2e8f0; padding: 8px 10px;
        }

        QTabWidget::pane {
            border: 1px solid #e2e8f0; border-radius: 6px; background: #ffffff;
        }
        QTabBar::tab {
            background: #f8fafc; color: #64748b;
            border: 1px solid #e2e8f0; border-bottom: none;
            border-radius: 4px 4px 0 0; padding: 8px 20px; margin-right: 2px;
        }
        QTabBar::tab:selected { background: #ffffff; color: #1e40af; font-weight: bold; }
        QTabBar::tab:hover:!selected { background: #f1f5f9; }

        QScrollBar:vertical {
            background: #f1f5f9; width: 8px; border-radius: 4px; margin: 0;
        }
        QScrollBar::handle:vertical {
            background: #cbd5e1; border-radius: 4px; min-height: 20px;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        QScrollBar:horizontal {
            background: #f1f5f9; height: 8px; border-radius: 4px; margin: 0;
        }
        QScrollBar::handle:horizontal {
            background: #cbd5e1; border-radius: 4px; min-width: 20px;
        }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

        QMessageBox { background: #ffffff; }
        QMessageBox QLabel { color: #1e293b; }
        QCalendarWidget { background: #ffffff; color: #1e293b; }
        QCalendarWidget QAbstractItemView {
            background: #ffffff; color: #1e293b;
            selection-background-color: #dbeafe;
        }
        QToolTip {
            background: #1e293b; color: #f8fafc;
            border: 1px solid #334155; padding: 4px 8px; border-radius: 4px;
        }
    """)

    login = LoginDialog()
    if login.exec() != QDialog.DialogCode.Accepted:
        sys.exit(0)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
