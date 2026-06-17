import sys
import os
import socket
import subprocess
import threading
from datetime import date as _date
from PyQt6.QtWidgets import (
    QApplication, QDialog, QMainWindow,
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
    QStackedWidget, QFrame, QGridLayout,
    QDoubleSpinBox, QSpinBox, QComboBox, QDateEdit, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QTextEdit,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from PyQt6.QtCore import Qt, QObject, QEvent, QTimer, QRegularExpression, QDate
from PyQt6.QtGui import QFont, QColor, QRegularExpressionValidator

from database import init_db, check_pin, check_owner_pin
from login import LoginDialog, _DIGIT_STYLE, _OK_STYLE, _BACK_STYLE
from masters import MastersPage
from purchase import PurchasePage
from sales import SalePage
from ledger import LedgerPage
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
    ("Dashboard",        "dashboard"),
    ("Masters",          "masters"),
    ("Purchase",         "purchase"),
    ("Sales",            "sales"),
    ("Vouchers",         "vouchers"),
    ("Ledger",           "ledger"),
    ("Capital",          "capital"),
    ("Reports",          "reports"),
    ("Bal. Sheet",       "balance_sheet"),
    ("WhatsApp",         "whatsapp"),
    ("Settings",         "settings"),
]

SIDEBAR_W = 180
SIDEBAR_BG = "#1a3c40"
SIDEBAR_HOVER = "#22505a"
SIDEBAR_ACTIVE = "#2563eb"
HEADER_BG = "#1a3c40"
HEADER_BORDER = "#22505a"
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


class _IdleResetFilter(QObject):
    """Reset the idle timer on any mouse movement, button press, or key press."""
    def __init__(self, on_activity, parent=None):
        super().__init__(parent)
        self._on_activity = on_activity

    def eventFilter(self, obj, event):
        if event.type() in (
            QEvent.Type.MouseMove,
            QEvent.Type.MouseButtonPress,
            QEvent.Type.KeyPress,
        ):
            self._on_activity()
        return False


class NavButton(QPushButton):
    def __init__(self, label: str, parent=None):
        super().__init__(label, parent)
        self.setCheckable(True)
        self.setFixedHeight(46)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
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
        logo.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        logo.setStyleSheet("color: #ffffff; padding: 8px 0 2px 0;")
        logo.setFixedHeight(36)
        layout.addWidget(logo)

        sub = QLabel("EPOS System")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setFont(QFont("Segoe UI", 8))
        sub.setStyleSheet("color: #64748b; padding-bottom: 4px;")
        sub.setFixedHeight(18)
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

        layout.addSpacing(4)

        # Action buttons — open dialogs (not nav pages)
        self.duplicate_print_btn = NavButton("Duplicate Print")
        self.duplicate_print_btn.setCheckable(False)
        layout.addWidget(self.duplicate_print_btn)

        self.imei_lookup_btn = NavButton("IMEI Lookup")
        self.imei_lookup_btn.setCheckable(False)
        layout.addWidget(self.imei_lookup_btn)

        self.lock_btn = NavButton("Lock")
        self.lock_btn.setCheckable(False)
        layout.addWidget(self.lock_btn)

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
        ]
        for key, label, unit, color in card_defs:
            card, val_lbl = self._make_card(label, unit, color)
            cards_row.addWidget(card)
            self._val_labels[key] = val_lbl

        bank_card = self._make_bank_card()
        cards_row.addWidget(bank_card)

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

    def _set_card_value(self, label, value, base_size: int = 22):
        """Set a card's value text and shrink the font once the integer
        portion reaches 7 digits (>= 1,000,000) so it stays inside the card."""
        text = _fmt_pkr(value)
        digit_count = sum(c.isdigit() for c in text)
        if digit_count >= 9:        # 100,000,000+
            size = max(12, base_size - 8)
        elif digit_count >= 7:      # 1,000,000+
            size = max(14, base_size - 4)
        else:
            size = base_size
        label.setFont(QFont("Segoe UI", size, QFont.Weight.Bold))
        label.setText(text)

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

            cust_outstanding = conn.execute("""
                SELECT
                    COALESCE((SELECT SUM(opening_balance) FROM customers WHERE type='credit'), 0) +
                    COALESCE((SELECT SUM(sv.total_amount) FROM sale_vouchers sv WHERE sv.type='credit'), 0) -
                    COALESCE((SELECT SUM(amount) FROM payments WHERE party_type='customer' AND type='CR'), 0) -
                    COALESCE((SELECT SUM(amount) FROM journal_entries WHERE party_type='customer' AND type='debit'), 0) +
                    COALESCE((SELECT SUM(amount) FROM journal_entries WHERE party_type='customer' AND type='credit'), 0)
            """).fetchone()[0]

            conn.close()

            self._set_card_value(self._val_labels["cash_in_hand"], cash_in_hand, base_size=22)
            self._set_card_value(self._val_labels["sales"], today_sales, base_size=22)
            self._set_card_value(self._val_labels["purchases"], today_purchases, base_size=22)
            self._set_card_value(self._val_labels["customers"], cust_outstanding, base_size=22)

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
            self._set_card_value(self._bank_val_lbl, db_bank_total_balance(), base_size=20)

        except Exception as e:
            print(f"Dashboard refresh error: {e}")


def db_search_sales_for_reprint(query: str) -> list[dict]:
    """Find sale vouchers for the Duplicate Print dialog.

    The query is matched two ways and the results combined:
      • As a voucher number — a bare number (e.g. "45") is auto-prefixed and
        zero-padded to "SV-0045"; the full form "SV-0045" works too.
      • As the last digits of an IMEI (when the query is all digits).

    Returns one row per matching sale voucher, newest first.
    """
    import re
    from database import get_connection
    q = query.strip()
    if not q:
        return []
    base = """
        SELECT sv.id, sv.sv_number, sv.date,
               COALESCE(c.name, sv.cash_customer_name, 'Walk-in') AS customer_name,
               sv.total_amount,
               (SELECT COUNT(*) FROM sale_lines sl2 WHERE sl2.sv_id = sv.id) AS item_count
        FROM sale_vouchers sv
        LEFT JOIN customers c ON c.id = sv.customer_id
    """
    # Normalize a voucher-number candidate: "45", "SV45", "sv-0045" → "SV-0045"
    voucher_number = None
    m = re.fullmatch(r"(?:sv-?)?(\d+)", q, re.IGNORECASE)
    if m:
        voucher_number = f"SV-{int(m.group(1)):04d}"

    conn = get_connection()
    found: dict[int, dict] = {}   # keyed by sv.id to dedupe across both searches

    if voucher_number is not None:
        for r in conn.execute(
            base + " WHERE UPPER(TRIM(sv.sv_number)) = UPPER(TRIM(?))",
            (voucher_number,),
        ).fetchall():
            found[r["id"]] = dict(r)

    if q.isdigit():
        for r in conn.execute(
            base + """ WHERE sv.id IN (
                SELECT sl.sv_id FROM sale_lines sl WHERE TRIM(sl.imei) LIKE ?
            )""",
            ("%" + q,),
        ).fetchall():
            found[r["id"]] = dict(r)

    conn.close()
    return sorted(found.values(), key=lambda r: r["id"], reverse=True)


class DuplicatePrintDialog(QDialog):
    """Compact dialog to reprint a sale receipt by voucher number or IMEI digits."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Duplicate Print")
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        lbl = QLabel(
            "Enter a voucher number (e.g. 45 or SV-0045) or the last few digits "
            "of an IMEI:"
        )
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("45,  SV-0045,  or IMEI digits")
        # Let Enter trigger the search instead of tab-navigating away
        self._input.setProperty("enterKeepDefault", True)
        self._input.returnPressed.connect(self._search)
        row.addWidget(self._input, stretch=1)
        find_btn = QPushButton("Find")
        find_btn.clicked.connect(self._search)
        row.addWidget(find_btn)
        layout.addLayout(row)

        self._status = QLabel("")
        self._status.setStyleSheet("color:#64748b; font-size:9pt;")
        layout.addWidget(self._status)

        self._list = QListWidget()
        self._list.setMinimumHeight(150)
        self._list.itemDoubleClicked.connect(lambda _it: self._print_selected())
        self._list.hide()
        layout.addWidget(self._list)

        self._print_btn = QPushButton("Print Selected")
        self._print_btn.clicked.connect(self._print_selected)
        self._print_btn.hide()
        layout.addWidget(self._print_btn)

    def _search(self):
        q = self._input.text().strip()
        if not q:
            self._status.setText("Type a voucher number or IMEI digits.")
            return
        matches = db_search_sales_for_reprint(q)
        if not matches:
            self._list.hide()
            self._print_btn.hide()
            self._status.setText("")
            QMessageBox.information(self, "Not Found", f"No sale found for '{q}'.")
            return
        if len(matches) == 1:
            self._do_print(matches[0])
            return
        # Multiple matches — let the user pick one
        self._status.setText(f"{len(matches)} matches found — pick one to print:")
        self._list.clear()
        for m in matches:
            item = QListWidgetItem(
                f"{m['sv_number']}   ·   {m['date']}   ·   {m['customer_name']}"
                f"   ·   PKR {_fmt_pkr(m['total_amount'])}   ({m['item_count']} item(s))"
            )
            item.setData(Qt.ItemDataRole.UserRole, m)
            self._list.addItem(item)
        self._list.setCurrentRow(0)
        self._list.show()
        self._print_btn.show()

    def _print_selected(self):
        item = self._list.currentItem()
        if not item:
            QMessageBox.warning(self, "Select", "Select a voucher from the list first.")
            return
        self._do_print(item.data(Qt.ItemDataRole.UserRole))

    def _do_print(self, match: dict):
        from receipt import print_receipt
        print_receipt(match["id"], parent=self)
        self.accept()


def db_imei_lookup_candidates(digits: str) -> list[str]:
    """Distinct full IMEIs containing the given digits (any position).

    Searches every table that stores an IMEI so the lookup works even for
    purchase-returned items (no stock_items row) or older data.
    """
    from database import get_connection
    d = digits.strip()
    if len(d) < 5 or not d.isdigit():
        return []
    conn = get_connection()
    rows = conn.execute("""
        SELECT DISTINCT imei FROM (
            SELECT TRIM(imei) AS imei FROM purchase_lines
            UNION
            SELECT TRIM(imei) AS imei FROM sale_lines
            UNION
            SELECT TRIM(imei) AS imei FROM stock_items
        )
        WHERE imei LIKE ?
        ORDER BY imei
    """, ("%" + d + "%",)).fetchall()
    conn.close()
    return [r["imei"] for r in rows]


def db_imei_full_history(imei: str) -> dict | None:
    """Full purchase + sale history for one exact IMEI, or None if not found.

    Purchase and sale are the most recent of each (an IMEI can be repurchased
    after being sold). stock_status reflects the current stock_items state.
    """
    from database import get_connection
    conn = get_connection()
    purchase = conn.execute("""
        SELECT pv.date AS date,
               COALESCE(s.name, 'Cash Purchase') AS supplier_name,
               pl.purchase_price AS purchase_price,
               pv.pv_number AS pv_number,
               b.name AS brand_name, m.name AS model_name
        FROM purchase_lines pl
        JOIN purchase_vouchers pv ON pv.id = pl.pv_id
        LEFT JOIN suppliers s ON s.id = pv.supplier_id
        LEFT JOIN models m ON m.id = pl.model_id
        LEFT JOIN brands b ON b.id = m.brand_id
        WHERE TRIM(pl.imei) = ?
        ORDER BY pv.id DESC
        LIMIT 1
    """, (imei,)).fetchone()

    sale = conn.execute("""
        SELECT sv.date AS date, sv.type AS sale_type,
               c.name AS customer_name,
               sv.cash_customer_name AS cash_name,
               sv.cash_customer_contact AS cash_contact,
               sl.final_price AS final_price,
               sv.sv_number AS sv_number,
               sm.name AS salesman_name
        FROM sale_lines sl
        JOIN sale_vouchers sv ON sv.id = sl.sv_id
        LEFT JOIN customers c ON c.id = sv.customer_id
        LEFT JOIN salesmen sm ON sm.id = sv.salesman_id
        WHERE TRIM(sl.imei) = ?
        ORDER BY sv.id DESC
        LIMIT 1
    """, (imei,)).fetchone()

    stock = conn.execute(
        "SELECT status FROM stock_items WHERE TRIM(imei) = ?", (imei,)
    ).fetchone()
    conn.close()

    if not purchase and not sale and not stock:
        return None
    return {
        "imei": imei,
        "purchase": dict(purchase) if purchase else None,
        "sale": dict(sale) if sale else None,
        "stock_status": stock["status"] if stock else None,
    }


class ImeiLookupDialog(QDialog):
    """Look up the full purchase + sale history of an IMEI by any 5+ digits."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("IMEI Lookup")
        self.setMinimumWidth(480)
        self.resize(520, 480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        lbl = QLabel("Enter at least 5 digits of the IMEI (any part):")
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("e.g. 12345")
        self._input.setMaxLength(15)
        self._input.setProperty("enterKeepDefault", True)
        self._input.returnPressed.connect(self._search)
        row.addWidget(self._input, stretch=1)
        find_btn = QPushButton("Search")
        find_btn.clicked.connect(self._search)
        row.addWidget(find_btn)
        layout.addLayout(row)

        self._status = QLabel("")
        self._status.setStyleSheet("color:#64748b; font-size:9pt;")
        layout.addWidget(self._status)

        # Candidate picker — shown only when multiple IMEIs match
        self._list = QListWidget()
        self._list.setMaximumHeight(120)
        self._list.itemClicked.connect(
            lambda it: self._show_history(it.data(Qt.ItemDataRole.UserRole))
        )
        self._list.hide()
        layout.addWidget(self._list)

        self._result = QTextEdit()
        self._result.setReadOnly(True)
        self._result.setStyleSheet(
            "QTextEdit { background:#ffffff; color:#1e293b; border:1px solid #e2e8f0; "
            "border-radius:6px; font-size:11pt; }"
        )
        layout.addWidget(self._result, stretch=1)

    def _search(self):
        digits = self._input.text().strip()
        self._list.hide()
        self._result.clear()
        if len(digits) < 5 or not digits.isdigit():
            self._status.setText("Enter at least 5 digits (numbers only).")
            return
        candidates = db_imei_lookup_candidates(digits)
        if not candidates:
            self._status.setText("")
            self._result.setPlainText("IMEI not found.")
            return
        if len(candidates) == 1:
            self._status.setText("")
            self._show_history(candidates[0])
            return
        # Multiple matches — let the user pick
        self._status.setText(f"{len(candidates)} IMEIs match — select one:")
        self._list.clear()
        for imei in candidates:
            item = QListWidgetItem(imei)
            item.setData(Qt.ItemDataRole.UserRole, imei)
            self._list.addItem(item)
        self._list.show()

    def _show_history(self, imei: str):
        hist = db_imei_full_history(imei)
        if not hist:
            self._result.setPlainText("IMEI not found.")
            return

        out = [f"IMEI: {imei}", ""]

        p = hist["purchase"]
        out.append("── Purchase Info ──")
        if p:
            out.append(f"Date of Purchase : {p['date']}")
            out.append(f"Brand            : {p['brand_name'] or '—'}")
            out.append(f"Model            : {p['model_name'] or '—'}")
            out.append(f"Supplier         : {p['supplier_name']}")
            out.append(f"Purchase Price   : Rs. {_fmt_pkr(p['purchase_price'])}")
            out.append(f"PV Number        : {p['pv_number']}")
        else:
            out.append("(no purchase record found)")
        out.append("")

        s = hist["sale"]
        if s:
            if s["sale_type"] == "cash":
                cust = s["cash_name"] or "Walk-in"
                if s["cash_contact"]:
                    cust += f" ({s['cash_contact']})"
            else:
                cust = s["customer_name"] or "—"
            out.append("── Sale Info ──")
            out.append(f"Date of Sale     : {s['date']}")
            out.append(f"Customer         : {cust}")
            out.append(f"Final Sale Price : Rs. {_fmt_pkr(s['final_price'])}")
            out.append(f"SV Number        : {s['sv_number']}")
            out.append(f"Salesman         : {s['salesman_name'] or '—'}")
        else:
            out.append("── Sale Info ──")
            out.append("Not Yet Sold — Currently In Stock")

        self._result.setPlainText("\n".join(out))


class LockOverlay(QWidget):
    """Opaque full-window lock screen.

    Covers the entire app (sidebar + all content) with a centred PIN entry so
    nothing behind it is visible. Calls on_unlock() when the correct PIN is
    entered. This is a LOCK, not a logout — the app keeps running behind it.
    """

    def __init__(self, parent, on_unlock):
        super().__init__(parent)
        self._on_unlock = on_unlock
        self._pin = ""
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Fully opaque background matching the app, so no content shows through.
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(self.backgroundRole(), QColor("#f8fafc"))
        self.setPalette(pal)

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 40)
        root.addStretch()

        brand = QLabel("United Mobile — Locked")
        brand.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        brand.setStyleSheet("color:#1e293b; background:transparent;")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(brand)

        root.addSpacing(4)
        sub = QLabel("Enter PIN to unlock")
        sub.setFont(QFont("Segoe UI", 11))
        sub.setStyleSheet("color:#64748b; background:transparent;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(sub)

        root.addSpacing(24)

        # PIN dot indicators (supports 4–6 digit PINs)
        dots_row = QHBoxLayout()
        dots_row.setSpacing(14)
        dots_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._dots: list[QLabel] = []
        for _ in range(6):
            dot = QLabel("○")
            dot.setFont(QFont("Segoe UI", 22))
            dot.setStyleSheet("color:#cbd5e1; background:transparent;")
            dot.setFixedWidth(32)
            dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            dots_row.addWidget(dot)
            self._dots.append(dot)
        root.addLayout(dots_row)

        self._err = QLabel("")
        self._err.setStyleSheet("color:#dc2626; font-size:9pt; background:transparent;")
        self._err.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._err.setFixedHeight(20)
        root.addWidget(self._err)

        root.addSpacing(16)

        # Keypad — phone layout: 1 2 3 / 4 5 6 / 7 8 9 / ⌫ 0 ✓
        grid = QGridLayout()
        grid.setSpacing(14)
        grid.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rows = [("1", "2", "3"), ("4", "5", "6"), ("7", "8", "9"), ("⌫", "0", "✓")]
        for r, keys in enumerate(rows):
            for c, key in enumerate(keys):
                btn = QPushButton(key)
                btn.setFixedSize(72, 72)
                btn.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
                btn.setAutoDefault(False)
                btn.setDefault(False)
                if key == "✓":
                    btn.setStyleSheet(_OK_STYLE)
                    btn.clicked.connect(self._submit)
                elif key == "⌫":
                    btn.setStyleSheet(_BACK_STYLE)
                    btn.clicked.connect(self._backspace)
                else:
                    btn.setStyleSheet(_DIGIT_STYLE)
                    btn.clicked.connect(lambda _, k=key: self._digit(k))
                grid.addWidget(btn, r, c)

        grid_wrap = QHBoxLayout()
        grid_wrap.addStretch()
        grid_wrap.addLayout(grid)
        grid_wrap.addStretch()
        root.addLayout(grid_wrap)

        root.addStretch()

    def reset(self):
        self._pin = ""
        self._err.setText("")
        self._refresh_dots()

    def _digit(self, d: str):
        if len(self._pin) < 6:
            self._pin += d
            self._refresh_dots()
            self._err.setText("")
            # Auto-unlock the moment the entered digits match the stored PIN
            if check_pin(self._pin):
                self._unlock()

    def _backspace(self):
        if self._pin:
            self._pin = self._pin[:-1]
            self._refresh_dots()
            self._err.setText("")

    def _submit(self):
        if not self._pin:
            return
        if check_pin(self._pin):
            self._unlock()
        else:
            self._pin = ""
            self._refresh_dots()
            self._err.setText("Incorrect PIN. Please try again.")

    def _unlock(self):
        self.reset()
        self._on_unlock()

    def _refresh_dots(self):
        for i, dot in enumerate(self._dots):
            filled = i < len(self._pin)
            dot.setText("●" if filled else "○")
            dot.setStyleSheet(
                ("color:#2563eb;" if filled else "color:#cbd5e1;")
                + " font-size:22pt; background:transparent;"
            )

    def keyPressEvent(self, event):
        key = event.text()
        if key.isdigit():
            self._digit(key)
        elif event.key() == Qt.Key.Key_Backspace:
            self._backspace()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._submit()
        # All other keys (e.g. Escape) are swallowed so the lock can't be bypassed


class OwnerPinDialog(QDialog):
    """Modal owner-PIN gate for the Capital and Settings screens.

    A 4-digit input box with a Confirm button. Auto-submits on the 4th digit,
    shows 'Incorrect PIN' and clears on a wrong entry, allows unlimited retries.
    accept() fires only on the correct owner PIN (see database.check_owner_pin).
    This is separate from the app lock/logoff PIN (check_pin).
    """

    def __init__(self, parent=None, target_name="this section"):
        super().__init__(parent)
        self.setWindowTitle("Owner PIN Required")
        self.setModal(True)
        self.setFixedWidth(320)

        lyt = QVBoxLayout(self)
        lyt.setContentsMargins(24, 20, 24, 20)
        lyt.setSpacing(12)

        title = QLabel("Owner PIN")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lyt.addWidget(title)

        sub = QLabel(f"Enter the owner PIN to open {target_name}.")
        sub.setStyleSheet("color:#64748b; font-size:9pt;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setWordWrap(True)
        lyt.addWidget(sub)

        self._input = QLineEdit()
        self._input.setEchoMode(QLineEdit.EchoMode.Password)
        self._input.setMaxLength(4)
        self._input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._input.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        # Digits only (0–4 of them); allows leading zeros, unlike QIntValidator.
        self._input.setValidator(
            QRegularExpressionValidator(QRegularExpression(r"[0-9]{0,4}"), self)
        )
        self._input.setPlaceholderText("• • • •")
        self._input.textChanged.connect(self._on_text)
        lyt.addWidget(self._input)

        self._err = QLabel("")
        self._err.setStyleSheet("color:#dc2626; font-size:9pt;")
        self._err.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._err.setFixedHeight(16)
        lyt.addWidget(self._err)

        confirm = QPushButton("Confirm")
        confirm.setStyleSheet(_OK_STYLE)
        confirm.setFixedHeight(40)
        confirm.setAutoDefault(False)
        confirm.setDefault(False)
        confirm.clicked.connect(self._submit)
        lyt.addWidget(confirm)

        self._input.setFocus()

    def _on_text(self, text: str):
        self._err.setText("")
        if len(text) == 4:          # auto-submit once 4 digits are entered
            self._submit()

    def _submit(self):
        if check_owner_pin(self._input.text()):
            self.accept()
        else:
            self._input.clear()
            self._err.setText("Incorrect PIN")


class VouchersPage(QWidget):
    """Vouchers page — CP, CR, JV tabs with date filters, party filter, list, and footer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {CONTENT_BG};")
        from ledger import BTN_PRIMARY, BTN_GREEN, BTN_SECONDARY, CARD_STYLE, TABLE_STYLE
        self._CARD = CARD_STYLE
        self._TABLE = TABLE_STYLE
        self._BS = BTN_SECONDARY

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        # ── Title row + Go to Voucher ─────────────────────────────────────────
        top = QHBoxLayout()
        title = QLabel("Vouchers")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title.setStyleSheet("color:#1e293b;")
        top.addWidget(title)
        top.addStretch()
        top.addWidget(QLabel("Go to:"))
        self._goto_edit = QLineEdit()
        self._goto_edit.setPlaceholderText("CP-0001 / CR-0001 / JV-0001")
        self._goto_edit.setFixedWidth(200)
        self._goto_edit.returnPressed.connect(self._goto_voucher)
        top.addWidget(self._goto_edit)
        btn_goto = QPushButton("Open")
        btn_goto.setStyleSheet(BTN_SECONDARY)
        btn_goto.clicked.connect(self._goto_voucher)
        top.addWidget(btn_goto)
        layout.addLayout(top)

        # ── Tabs ─────────────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._cp_tab = self._build_cp_cr_tab("CP", BTN_PRIMARY)
        self._cr_tab = self._build_cp_cr_tab("CR", BTN_GREEN)
        self._jv_tab = self._build_jv_tab()
        self._tabs.addTab(self._cp_tab["widget"], "Cash Payments (CP)")
        self._tabs.addTab(self._cr_tab["widget"], "Cash Receipts (CR)")
        self._tabs.addTab(self._jv_tab["widget"], "Journal Vouchers (JV)")
        layout.addWidget(self._tabs, stretch=1)

    # ── Table factory ─────────────────────────────────────────────────────────

    def _make_table(self, headers):
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setAlternatingRowColors(True)
        t.verticalHeader().setVisible(False)
        t.setStyleSheet(self._TABLE)
        return t

    # ── Tab builders ──────────────────────────────────────────────────────────

    def _build_cp_cr_tab(self, ptype, btn_new_style):
        widget = QWidget()
        widget.setStyleSheet(f"background: {CONTENT_BG};")
        vbox = QVBoxLayout(widget)
        vbox.setContentsMargins(0, 10, 0, 0)
        vbox.setSpacing(10)

        # Filter card
        card = QFrame()
        card.setStyleSheet(self._CARD)
        fl = QHBoxLayout(card)
        fl.setContentsMargins(12, 10, 12, 10)
        fl.setSpacing(10)

        fl.addWidget(QLabel("From:"))
        from_date = QDateEdit(QDate.currentDate())
        from_date.setDisplayFormat("dd/MM/yyyy")
        from_date.setCalendarPopup(True)
        from_date.setMinimumWidth(110)
        fl.addWidget(from_date)

        fl.addWidget(QLabel("To:"))
        to_date = QDateEdit(QDate.currentDate())
        to_date.setDisplayFormat("dd/MM/yyyy")
        to_date.setCalendarPopup(True)
        to_date.setMinimumWidth(110)
        fl.addWidget(to_date)

        fl.addWidget(QLabel("Party:"))
        party_combo = QComboBox()
        party_combo.setMinimumWidth(190)
        party_combo.addItem("— All —", None)
        from database import get_connection as _gc
        _conn = _gc()
        for r in _conn.execute("SELECT id, name FROM suppliers WHERE id!=0 ORDER BY name"):
            party_combo.addItem(f"[Supplier] {r['name']}", {"ptype": "supplier", "pid": r["id"]})
        for r in _conn.execute("SELECT id, name FROM customers ORDER BY name"):
            party_combo.addItem(f"[Customer] {r['name']}", {"ptype": "customer", "pid": r["id"]})
        _conn.close()
        fl.addWidget(party_combo)

        fl.addSpacing(6)
        for label in ("Today", "Yesterday", "Search", "Clear"):
            b = QPushButton(label)
            b.setStyleSheet(self._BS)
            fl.addWidget(b)
            if label == "Today":
                btn_today = b
            elif label == "Yesterday":
                btn_yesterday = b
            elif label == "Search":
                btn_search = b
            else:
                btn_clear = b

        fl.addStretch()
        btn_new = QPushButton(f"+ New {ptype}")
        btn_new.setStyleSheet(btn_new_style)
        fl.addWidget(btn_new)
        vbox.addWidget(card)

        # Table
        table = self._make_table(["#", "Date", "Voucher", "Party Type", "Party Name", "Amount (PKR)"])
        hdr = table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        hdr.setStretchLastSection(False)
        table.setColumnWidth(0, 40)
        table.setColumnWidth(1, 110)
        table.setColumnWidth(2, 100)
        table.setColumnWidth(3, 100)
        table.setColumnWidth(5, 130)
        vbox.addWidget(table, stretch=1)

        # Footer
        footer = QLabel("Total Vouchers: 0   |   Total Amount: Rs. 0")
        footer.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        footer.setStyleSheet("color:#1e293b; padding:4px 2px;")
        vbox.addWidget(footer)

        state = {
            "widget": widget, "ptype": ptype,
            "from_date": from_date, "to_date": to_date,
            "party_combo": party_combo, "table": table, "footer": footer,
        }

        btn_today.clicked.connect(lambda: (
            from_date.setDate(QDate.currentDate()),
            to_date.setDate(QDate.currentDate()),
            self._refresh_cp_cr(state),
        ))
        btn_yesterday.clicked.connect(lambda: (
            from_date.setDate(QDate.currentDate().addDays(-1)),
            to_date.setDate(QDate.currentDate().addDays(-1)),
            self._refresh_cp_cr(state),
        ))
        btn_search.clicked.connect(lambda: self._refresh_cp_cr(state))
        btn_clear.clicked.connect(lambda: (
            from_date.setDate(QDate.currentDate()),
            to_date.setDate(QDate.currentDate()),
            party_combo.setCurrentIndex(0),
            self._refresh_cp_cr(state),
        ))
        btn_new.clicked.connect(lambda: self._new_cp_or_cr(state))
        table.doubleClicked.connect(lambda _idx, s=state: self._edit_cp_cr_row(s))

        return state

    def _build_jv_tab(self):
        widget = QWidget()
        widget.setStyleSheet(f"background: {CONTENT_BG};")
        vbox = QVBoxLayout(widget)
        vbox.setContentsMargins(0, 10, 0, 0)
        vbox.setSpacing(10)

        card = QFrame()
        card.setStyleSheet(self._CARD)
        fl = QHBoxLayout(card)
        fl.setContentsMargins(12, 10, 12, 10)
        fl.setSpacing(10)

        fl.addWidget(QLabel("From:"))
        from_date = QDateEdit(QDate.currentDate())
        from_date.setDisplayFormat("dd/MM/yyyy")
        from_date.setCalendarPopup(True)
        from_date.setMinimumWidth(110)
        fl.addWidget(from_date)

        fl.addWidget(QLabel("To:"))
        to_date = QDateEdit(QDate.currentDate())
        to_date.setDisplayFormat("dd/MM/yyyy")
        to_date.setCalendarPopup(True)
        to_date.setMinimumWidth(110)
        fl.addWidget(to_date)

        fl.addSpacing(6)
        for label in ("Today", "Yesterday", "Search", "Clear"):
            b = QPushButton(label)
            b.setStyleSheet(self._BS)
            fl.addWidget(b)
            if label == "Today":
                btn_today = b
            elif label == "Yesterday":
                btn_yesterday = b
            elif label == "Search":
                btn_search = b
            else:
                btn_clear = b

        fl.addStretch()
        btn_new = QPushButton("+ New JV")
        btn_new.setStyleSheet(self._BS)
        fl.addWidget(btn_new)
        vbox.addWidget(card)

        table = self._make_table(["#", "Date", "Voucher", "Dr Party", "Cr Party", "Amount (PKR)"])
        hdr = table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        hdr.setStretchLastSection(False)
        table.setColumnWidth(0, 40)
        table.setColumnWidth(1, 110)
        table.setColumnWidth(2, 100)
        table.setColumnWidth(5, 130)
        vbox.addWidget(table, stretch=1)

        footer = QLabel("Total Vouchers: 0   |   Total Amount: Rs. 0")
        footer.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        footer.setStyleSheet("color:#1e293b; padding:4px 2px;")
        vbox.addWidget(footer)

        state = {
            "widget": widget,
            "from_date": from_date, "to_date": to_date,
            "table": table, "footer": footer,
        }

        btn_today.clicked.connect(lambda: (
            from_date.setDate(QDate.currentDate()),
            to_date.setDate(QDate.currentDate()),
            self._refresh_jv(state),
        ))
        btn_yesterday.clicked.connect(lambda: (
            from_date.setDate(QDate.currentDate().addDays(-1)),
            to_date.setDate(QDate.currentDate().addDays(-1)),
            self._refresh_jv(state),
        ))
        btn_search.clicked.connect(lambda: self._refresh_jv(state))
        btn_clear.clicked.connect(lambda: (
            from_date.setDate(QDate.currentDate()),
            to_date.setDate(QDate.currentDate()),
            self._refresh_jv(state),
        ))
        btn_new.clicked.connect(self._new_jv)
        table.doubleClicked.connect(lambda _idx, s=state: self._edit_jv_row(s))

        return state

    # ── Refresh ───────────────────────────────────────────────────────────────

    def _refresh_cp_cr(self, state):
        from database import get_connection
        ptype = state["ptype"]
        from_iso = state["from_date"].date().toString("yyyy-MM-dd")
        to_iso   = state["to_date"].date().toString("yyyy-MM-dd")
        party_data = state["party_combo"].currentData()

        params = [from_iso, to_iso, ptype]
        extra = ""
        if party_data is not None:
            extra = " AND p.party_type=? AND p.party_id=?"
            params += [party_data["ptype"], party_data["pid"]]

        sql = f"""
            SELECT p.id, p.date, p.voucher_number, p.party_type,
                   COALESCE(s.name, c.name, op.name, '') AS party_name,
                   p.amount
            FROM payments p
            LEFT JOIN suppliers s  ON s.id=p.party_id  AND p.party_type='supplier'
            LEFT JOIN customers c  ON c.id=p.party_id  AND p.party_type='customer'
            LEFT JOIN other_parties op ON op.id=p.party_id AND p.party_type='other'
            WHERE substr(p.date,7,4)||'-'||substr(p.date,4,2)||'-'||substr(p.date,1,2)
                  BETWEEN ? AND ?
              AND p.type=?{extra}
            ORDER BY p.id DESC
        """
        conn = get_connection()
        rows = conn.execute(sql, params).fetchall()
        conn.close()

        table = state["table"]
        table.setRowCount(0)
        total = 0.0
        for i, r in enumerate(rows):
            row = table.rowCount()
            table.insertRow(row)
            pt_label = r["party_type"].capitalize() if r["party_type"] else ""
            for col, val in enumerate([
                str(i + 1), r["date"], r["voucher_number"],
                pt_label, r["party_name"] or "",
                f"{float(r['amount']):,.0f}",
            ]):
                item = QTableWidgetItem(str(val))
                if col == 5:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, r["id"])
                table.setItem(row, col, item)
            total += float(r["amount"])

        state["footer"].setText(
            f"Total Vouchers: {len(rows)}   |   Total Amount: Rs. {total:,.0f}"
        )

    def _refresh_jv(self, state):
        from database import get_connection
        from_iso = state["from_date"].date().toString("yyyy-MM-dd")
        to_iso   = state["to_date"].date().toString("yyyy-MM-dd")

        sql = """
            SELECT d.jv_number, d.date,
                   COALESCE(sd.name, cd.name, opd.name, 'Cash/Bank') AS dr_party,
                   COALESCE(sc.name, cc.name, opc.name, 'Cash/Bank') AS cr_party,
                   d.amount
            FROM journal_entries d
            LEFT JOIN journal_entries c
                   ON c.jv_number=d.jv_number AND c.type='credit'
            LEFT JOIN suppliers  sd  ON sd.id=d.party_id  AND d.party_type='supplier'
            LEFT JOIN customers  cd  ON cd.id=d.party_id  AND d.party_type='customer'
            LEFT JOIN other_parties opd ON opd.id=d.party_id AND d.party_type='other'
            LEFT JOIN suppliers  sc  ON sc.id=c.party_id  AND c.party_type='supplier'
            LEFT JOIN customers  cc  ON cc.id=c.party_id  AND c.party_type='customer'
            LEFT JOIN other_parties opc ON opc.id=c.party_id AND c.party_type='other'
            WHERE d.type='debit'
              AND substr(d.date,7,4)||'-'||substr(d.date,4,2)||'-'||substr(d.date,1,2)
                  BETWEEN ? AND ?
            ORDER BY d.id DESC
        """
        conn = get_connection()
        rows = conn.execute(sql, [from_iso, to_iso]).fetchall()
        conn.close()

        table = state["table"]
        table.setRowCount(0)
        total = 0.0
        for i, r in enumerate(rows):
            row = table.rowCount()
            table.insertRow(row)
            for col, val in enumerate([
                str(i + 1), r["date"], r["jv_number"],
                r["dr_party"], r["cr_party"],
                f"{float(r['amount']):,.0f}",
            ]):
                item = QTableWidgetItem(str(val))
                if col == 5:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, r["jv_number"])
                table.setItem(row, col, item)
            total += float(r["amount"])

        state["footer"].setText(
            f"Total Vouchers: {len(rows)}   |   Total Amount: Rs. {total:,.0f}"
        )

    def refresh(self):
        self._refresh_cp_cr(self._cp_tab)
        self._refresh_cp_cr(self._cr_tab)
        self._refresh_jv(self._jv_tab)

    # ── New voucher ───────────────────────────────────────────────────────────

    def _new_cp_or_cr(self, state):
        from ledger import MultiLineCpCrDialog
        ptype = state["ptype"]
        dlg = MultiLineCpCrDialog(ptype, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        label = "Cash Payment" if ptype == "CP" else "Cash Receipt"
        QMessageBox.information(self, "Saved", f"{label} {dlg.get_voucher()} saved.")
        self._refresh_cp_cr(state)

    def _new_jv(self):
        from ledger import DoubleEntryJournalDialog
        from database import db_save_double_entry_jv
        dlg = DoubleEntryJournalDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        date_str, notes, dr_type, dr_id, cr_type, cr_id, amount = dlg.get_data()
        try:
            jv = db_save_double_entry_jv(date_str, notes, dr_type, dr_id, cr_type, cr_id, amount)
        except Exception as ex:
            QMessageBox.critical(self, "Error", str(ex))
            return
        QMessageBox.information(self, "Saved", f"Journal Voucher {jv} saved.")
        self._refresh_jv(self._jv_tab)

    # ── Edit on double-click ──────────────────────────────────────────────────

    def _edit_cp_cr_row(self, state):
        table = state["table"]
        row = table.currentRow()
        if row < 0:
            return
        pay_id = table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        from database import get_connection
        conn = get_connection()
        r = conn.execute("SELECT * FROM payments WHERE id=?", (pay_id,)).fetchone()
        conn.close()
        if not r:
            return
        from edit_vouchers import PaymentEditDialog
        dlg = PaymentEditDialog(dict(r), self)
        result = dlg.exec()
        if result in (QDialog.DialogCode.Accepted, PaymentEditDialog.DELETED):
            self._refresh_cp_cr(state)

    def _edit_jv_row(self, state):
        table = state["table"]
        row = table.currentRow()
        if row < 0:
            return
        jv_number = table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        from edit_vouchers import JVEditDialog, db_lookup_journal_entry
        je = db_lookup_journal_entry(jv_number)
        if not je:
            return
        dlg = JVEditDialog(je, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh_jv(state)

    # ── Go to voucher ─────────────────────────────────────────────────────────

    def _goto_voucher(self):
        import re
        raw = self._goto_edit.text().strip().upper()
        if not raw:
            return
        if not re.match(r'^[A-Z]+-\d+$', raw):
            QMessageBox.warning(self, "Invalid Format",
                "Please enter a full voucher number, e.g. CP-0001")
            return
        from edit_vouchers import (
            PaymentEditDialog, JVEditDialog,
            db_lookup_payment, db_lookup_journal_entry,
        )
        opened = False
        if raw.startswith("CP-") or raw.startswith("CR-"):
            pay = db_lookup_payment(raw)
            if pay:
                dlg = PaymentEditDialog(pay, self)
                result = dlg.exec()
                if result in (QDialog.DialogCode.Accepted, PaymentEditDialog.DELETED):
                    self.refresh()
                opened = True
        elif raw.startswith("JV-"):
            je = db_lookup_journal_entry(raw)
            if je:
                dlg = JVEditDialog(je, self)
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    self.refresh()
                opened = True
        if not opened:
            QMessageBox.warning(self, "Not Found", f"Voucher {raw} not found.")
        self._goto_edit.clear()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("United Mobile EPOS")
        self.setMinimumSize(1100, 680)
        self.resize(1280, 780)

        central = QWidget()
        self.setCentralWidget(central)
        self._central = central
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
        self._current_key = "dashboard"   # tracks the open page for the owner-PIN gate

        # Notification bar — hidden by default, shown briefly after auto-backup
        self._notif_bar = self._make_notif_bar()
        right_layout.addWidget(self._notif_bar)

        root.addWidget(right, stretch=1)

        self._pages: dict[str, QWidget] = {}
        self._register_page("dashboard", DashboardPage())
        self._register_page("masters", MastersPage())
        self._register_page("purchase", PurchasePage())
        self._register_page("sales", SalePage())
        self._register_page("vouchers", VouchersPage())
        self._register_page("ledger", LedgerPage())
        self._register_page("capital", CapitalPage())
        self._register_page("reports", ReportsPage())
        self._register_page("balance_sheet", BalanceSheetPage())
        self._register_page("whatsapp", WhatsAppPage())
        self._register_page("settings", SettingsPage())

        for key, btn in self.sidebar.buttons.items():
            btn.clicked.connect(lambda checked, k=key: self._navigate(k))

        self.sidebar.duplicate_print_btn.clicked.connect(self._open_duplicate_print)
        self.sidebar.imei_lookup_btn.clicked.connect(self._open_imei_lookup)
        self.sidebar.lock_btn.clicked.connect(self._lock)

        # Lock overlay — child of central so it can cover sidebar + content.
        # Created last so it sits on top of all siblings; hidden until locked.
        self._lock_overlay = LockOverlay(central, on_unlock=self._unlock)
        self._lock_overlay.hide()

        # Wire "Use in Sale" from IMEI Stock report → Sales form
        reports_page = self._pages.get("reports")
        if reports_page and hasattr(reports_page, "set_use_in_sale_cb"):
            reports_page.set_use_in_sale_cb(self._use_imei_in_sale)

        self._navigate("dashboard")

        # Kick off auto-backup 800 ms after the window is ready
        # (runs in a daemon thread so startup is never blocked)
        QTimer.singleShot(800, self._start_auto_backup)

        # Auto-lock after 5 minutes of inactivity
        self._idle_timer = QTimer(self)
        self._idle_timer.setInterval(5 * 60 * 1000)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._auto_lock)
        self._idle_timer.start()
        self._idle_filter = _IdleResetFilter(self._reset_idle_timer, self)
        QApplication.instance().installEventFilter(self._idle_filter)

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

    # Sidebar pages that require the owner PIN before opening.
    _OWNER_PROTECTED = {"capital", "settings"}

    def _navigate(self, key: str):
        label = dict(NAV_ITEMS).get(key, key.capitalize())
        if key in self._OWNER_PROTECTED:
            dlg = OwnerPinDialog(self, target_name=label)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                # Wrong PIN or cancelled — stay put; restore the sidebar highlight.
                self.sidebar.set_active(self._current_key)
                return
        self.sidebar.set_active(key)
        self.stack.setCurrentWidget(self._pages[key])
        self._header_page_label.setText(label)
        self._current_key = key

        # Refresh pages that need live data when navigated to
        page = self._pages.get(key)
        if key == "vouchers" and page and hasattr(page, "refresh"):
            page.refresh()

    def _open_duplicate_print(self):
        DuplicatePrintDialog(self).exec()

    def _open_imei_lookup(self):
        ImeiLookupDialog(self).exec()

    def _reset_idle_timer(self):
        if getattr(self, "_idle_timer", None):
            self._idle_timer.start()

    def _auto_lock(self):
        if QApplication.activeModalWidget() is not None:
            self._idle_timer.start()
            return
        if getattr(self, "_lock_overlay", None) and not self._lock_overlay.isVisible():
            self._lock()

    def _lock(self):
        """Cover the whole window with the PIN overlay. The app keeps running."""
        self._lock_overlay.setGeometry(self._central.rect())
        self._lock_overlay.reset()
        self._lock_overlay.show()
        self._lock_overlay.raise_()
        self._lock_overlay.setFocus()

    def _unlock(self):
        """Correct PIN entered — hide the overlay and return to the dashboard."""
        self._lock_overlay.hide()
        self._navigate("dashboard")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Keep the lock overlay covering the entire window while it's visible.
        if getattr(self, "_lock_overlay", None) and self._lock_overlay.isVisible():
            self._lock_overlay.setGeometry(self._central.rect())

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

        /* Inline table-cell editors (double-click to edit a cell): slightly
           larger than the 10pt display font and bold, so they are easy to read
           and type. Reverts to normal cell styling once the edit is committed.
           Applies to every editable cell in every table app-wide. */
        QAbstractItemView QLineEdit,
        QAbstractItemView QDoubleSpinBox,
        QAbstractItemView QSpinBox {
            font-size: 12pt; font-weight: bold;
            color: #1e293b; background: #ffffff;
            border: 2px solid #2563eb; border-radius: 3px; padding: 1px 4px;
        }

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
