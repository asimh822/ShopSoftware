from PyQt6.QtWidgets import QComboBox, QCompleter
from PyQt6.QtCore import Qt, QTimer


class SearchableComboBox(QComboBox):
    """
    Drop-in replacement for QComboBox with live MatchContains filtering.
    currentData(), setCurrentIndex(), addItem(), currentIndexChanged() all
    work identically to the standard combo. Enter key selects the highlighted
    item and advances focus (consistent with the app-wide Enter=Tab rule).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)

        completer = QCompleter(self)
        completer.setModel(self.model())
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.setCompleter(completer)
        completer.activated.connect(self._on_activated)

        # Explicitly style the popup so it is readable regardless of what
        # stylesheet the parent widget applies (parent dark styles can make
        # the popup text and background the same colour).
        completer.popup().setStyleSheet("""
            QAbstractItemView {
                background: #ffffff;
                color: #1e293b;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                font-size: 10pt;
            }
            QAbstractItemView::item { padding: 5px 10px; }
            QAbstractItemView::item:hover { background: #dbeafe; color: #1e40af; }
            QAbstractItemView::item:selected { background: #2563eb; color: #ffffff; }
        """)

        # Prevent the app-level Enter=Tab event filter from consuming Enter
        # while the completer popup is open — the completer must see it first.
        self.lineEdit().setProperty("enterKeepDefault", True)
        self.lineEdit().returnPressed.connect(self._on_return_pressed)

        # When Enter selects an item from the popup, QCompleter emits
        # activated() AND forwards the same key press to the line edit,
        # firing returnPressed too. Without this guard both handlers would
        # advance focus, skipping one field (e.g. Brand → Ref Price).
        self._activated_pending = False

    # ── Focus handling — auto-clear placeholder, restore on blur ─────────────

    def focusInEvent(self, event):
        super().focusInEvent(event)
        if self.currentData() is None:
            # Placeholder shown — clear it so the user can type straight away
            QTimer.singleShot(0, self.lineEdit().clear)
        else:
            # Real selection — select all so overtyping replaces it
            QTimer.singleShot(0, self.lineEdit().selectAll)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        # Small delay so a click on the popup is committed before we restore
        QTimer.singleShot(150, self._restore_display)

    def _restore_display(self):
        if self.hasFocus():
            return
        text = self.lineEdit().text().strip()
        # If the typed text doesn't exactly match any item, restore the line
        # edit to match whatever currentIndex holds (selection or placeholder).
        if self.findText(text, Qt.MatchFlag.MatchExactly) < 0:
            ci = self.currentIndex()
            display = (self.itemText(ci)
                       if 0 <= ci < self.count()
                       else (self.itemText(0) if self.count() > 0 else ""))
            self.lineEdit().setText(display)

    # ── Item selected from popup (Enter key or click) ─────────────────────────

    def _on_activated(self, text):
        idx = self.findText(text, Qt.MatchFlag.MatchExactly)
        if idx < 0:
            idx = self.findText(text)
        if idx >= 0:
            self.setCurrentIndex(idx)
        # Advance to next field after selection (Enter=Tab rule)
        self._activated_pending = True
        QTimer.singleShot(0, self._advance_after_activated)

    def _advance_after_activated(self):
        self._activated_pending = False
        self.focusNextChild()

    # ── Enter pressed when popup is NOT open ─────────────────────────────────

    def _on_return_pressed(self):
        if self._activated_pending:
            # This Enter was already handled by the completer popup
            # (activated fired); the forwarded key event must not advance
            # focus a second time.
            return
        text = self.lineEdit().text()
        idx = self.findText(text, Qt.MatchFlag.MatchExactly)
        if idx < 0:
            idx = self.findText(text, Qt.MatchFlag.MatchFixedString)
        if idx >= 0:
            self.setCurrentIndex(idx)
        self.focusNextChild()
