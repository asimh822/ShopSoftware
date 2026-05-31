from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from database import check_pin

PIN_MAX_LEN = 6

_DIGIT_STYLE = """
    QPushButton {
        background: #f8fafc;
        color: #1e293b;
        border: 1.5px solid #e2e8f0;
        border-radius: 36px;
        font-size: 20pt;
        font-weight: bold;
    }
    QPushButton:hover  { background: #e2e8f0; border-color: #cbd5e1; }
    QPushButton:pressed { background: #cbd5e1; }
"""
_OK_STYLE = """
    QPushButton {
        background: #2563eb;
        color: white;
        border: none;
        border-radius: 36px;
        font-size: 18pt;
        font-weight: bold;
    }
    QPushButton:hover  { background: #1d4ed8; }
    QPushButton:pressed { background: #1e40af; }
"""
_BACK_STYLE = """
    QPushButton {
        background: #fee2e2;
        color: #dc2626;
        border: none;
        border-radius: 36px;
        font-size: 16pt;
        font-weight: bold;
    }
    QPushButton:hover  { background: #fecaca; }
    QPushButton:pressed { background: #fca5a5; }
"""


class LoginDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("United Mobile EPOS")
        self.setFixedSize(360, 560)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.MSWindowsFixedSizeDialogHint
        )
        self.setStyleSheet("background: #f8fafc;")
        self._pin = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 36, 36, 32)
        layout.setSpacing(0)

        # Shop name
        brand = QLabel("United Mobile")
        brand.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        brand.setStyleSheet("color: #1e293b;")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(brand)

        layout.addSpacing(4)

        sub = QLabel("Enter PIN to continue")
        sub.setFont(QFont("Segoe UI", 10))
        sub.setStyleSheet("color: #64748b;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sub)

        layout.addSpacing(28)

        # PIN dot indicators
        dots_row = QHBoxLayout()
        dots_row.setSpacing(14)
        dots_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._dots: list[QLabel] = []
        for _ in range(PIN_MAX_LEN):
            dot = QLabel("○")
            dot.setFont(QFont("Segoe UI", 22))
            dot.setStyleSheet("color: #cbd5e1;")
            dot.setFixedWidth(32)
            dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            dots_row.addWidget(dot)
            self._dots.append(dot)
        layout.addLayout(dots_row)

        layout.addSpacing(4)

        self._err = QLabel("")
        self._err.setStyleSheet("color: #dc2626; font-size: 9pt;")
        self._err.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._err.setFixedHeight(20)
        layout.addWidget(self._err)

        layout.addSpacing(20)

        # Dialpad — phone layout: 1 2 3 / 4 5 6 / 7 8 9 / ⌫ 0 ✓
        BTN_SIZE = 72
        grid = QGridLayout()
        grid.setSpacing(14)
        grid.setAlignment(Qt.AlignmentFlag.AlignCenter)

        rows = [("1", "2", "3"), ("4", "5", "6"), ("7", "8", "9"), ("⌫", "0", "✓")]
        for r, keys in enumerate(rows):
            for c, key in enumerate(keys):
                btn = QPushButton(key)
                btn.setFixedSize(BTN_SIZE, BTN_SIZE)
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

        layout.addLayout(grid)

    def _digit(self, d: str):
        if len(self._pin) < PIN_MAX_LEN:
            self._pin += d
            self._refresh_dots()
            self._err.setText("")
            # Auto-proceed the moment the entered digits match the stored PIN
            if check_pin(self._pin):
                self.accept()
                return

    def _backspace(self):
        if self._pin:
            self._pin = self._pin[:-1]
            self._refresh_dots()
            self._err.setText("")

    def _submit(self):
        if not self._pin:
            return
        if check_pin(self._pin):
            self.accept()
        else:
            self._pin = ""
            self._refresh_dots()
            self._err.setText("Incorrect PIN. Please try again.")

    def _refresh_dots(self):
        for i, dot in enumerate(self._dots):
            if i < len(self._pin):
                dot.setText("●")
                dot.setStyleSheet("color: #2563eb; font-size: 22pt;")
            else:
                dot.setText("○")
                dot.setStyleSheet("color: #cbd5e1; font-size: 22pt;")

    def keyPressEvent(self, event):
        key = event.text()
        if key.isdigit():
            self._digit(key)
        elif event.key() == Qt.Key.Key_Backspace:
            self._backspace()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._submit()
        # Escape intentionally suppressed to prevent bypassing login
