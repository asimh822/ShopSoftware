from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QDateEdit, QSizePolicy, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QFont, QColor
import datetime

from database import get_connection, db_cash_in_hand, db_bank_total_balance, get_setting


def _fmt(amount: float) -> str:
    return f"Rs. {int(round(amount)):,}"


def _party_balance(conn, party_type: str, party_id: int) -> float:
    table = "suppliers" if party_type == "supplier" else "customers"
    ob_row = conn.execute(
        f"SELECT opening_balance FROM {table} WHERE id=?", (party_id,)
    ).fetchone()
    ob = float(ob_row["opening_balance"] or 0) if ob_row else 0.0

    if party_type == "supplier":
        purchases = conn.execute(
            "SELECT COALESCE(SUM(total_amount),0) FROM purchase_vouchers WHERE supplier_id=?",
            (party_id,)
        ).fetchone()[0]
        cp = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM payments "
            "WHERE party_type='supplier' AND party_id=? AND type='CP'",
            (party_id,)
        ).fetchone()[0]
        cr = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM payments "
            "WHERE party_type='supplier' AND party_id=? AND type='CR'",
            (party_id,)
        ).fetchone()[0]
        jv_dr = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM journal_entries "
            "WHERE party_type='supplier' AND party_id=? AND type='debit'",
            (party_id,)
        ).fetchone()[0]
        jv_cr = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM journal_entries "
            "WHERE party_type='supplier' AND party_id=? AND type='credit'",
            (party_id,)
        ).fetchone()[0]
        return ob + float(purchases) + float(cr) - float(cp) + float(jv_dr) - float(jv_cr)
    else:
        sales = conn.execute(
            "SELECT COALESCE(SUM(total_amount),0) FROM sale_vouchers "
            "WHERE customer_id=? AND type='credit'",
            (party_id,)
        ).fetchone()[0]
        cp = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM payments "
            "WHERE party_type='customer' AND party_id=? AND type='CP'",
            (party_id,)
        ).fetchone()[0]
        cr = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM payments "
            "WHERE party_type='customer' AND party_id=? AND type='CR'",
            (party_id,)
        ).fetchone()[0]
        jv_dr = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM journal_entries "
            "WHERE party_type='customer' AND party_id=? AND type='debit'",
            (party_id,)
        ).fetchone()[0]
        jv_cr = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM journal_entries "
            "WHERE party_type='customer' AND party_id=? AND type='credit'",
            (party_id,)
        ).fetchone()[0]
        return ob + float(sales) + float(cp) - float(cr) + float(jv_dr) - float(jv_cr)


def bs_data() -> dict:
    conn = get_connection()

    fixed_assets = []
    try:
        rows = conn.execute(
            "SELECT name, value FROM fixed_assets ORDER BY name"
        ).fetchall()
        fixed_assets = [{"name": r["name"], "value": float(r["value"] or 0)} for r in rows]
    except Exception:
        pass
    total_fixed = sum(a["value"] for a in fixed_assets)

    stock = conn.execute(
        "SELECT COALESCE(SUM(purchase_price),0) FROM stock_items WHERE status='in_stock'"
    ).fetchone()[0]
    stock = float(stock or 0)

    customers = conn.execute(
        "SELECT id, name FROM customers WHERE type='credit' ORDER BY name"
    ).fetchall()
    receivables = []
    for c in customers:
        bal = _party_balance(conn, "customer", c["id"])
        if bal > 0:
            receivables.append({"name": c["name"], "balance": bal})
    total_recv = sum(r["balance"] for r in receivables)

    cash = db_cash_in_hand()
    bank = db_bank_total_balance()
    total_current = stock + total_recv + cash + bank
    total_assets = total_fixed + total_current

    suppliers = conn.execute(
        "SELECT id, name FROM suppliers WHERE id != 0 ORDER BY name"
    ).fetchall()
    payables = []
    for s in suppliers:
        if s["name"].upper().strip() == "OPENING STOCK" or "OPENING STOCK" in s["name"].upper():
            continue
        bal = _party_balance(conn, "supplier", s["id"])
        if bal > 0:
            payables.append({"name": s["name"], "balance": bal})
    total_payables = sum(p["balance"] for p in payables)

    committee_items = []
    total_committees = 0.0
    try:
        rows = conn.execute(
            "SELECT name, remaining FROM committees ORDER BY name"
        ).fetchall()
        committee_items = [{"name": r["name"], "remaining": float(r["remaining"] or 0)} for r in rows]
        total_committees = sum(ci["remaining"] for ci in committee_items)
    except Exception:
        pass

    total_liabilities = total_payables + total_committees

    capital_items = []
    try:
        from capital import get_capital_balance
        accounts = conn.execute(
            "SELECT id, name FROM capital_accounts ORDER BY name"
        ).fetchall()
        for a in accounts:
            try:
                bal = get_capital_balance(conn, a["id"])
            except Exception:
                ob_row = conn.execute(
                    "SELECT opening_balance FROM capital_accounts WHERE id=?", (a["id"],)
                ).fetchone()
                bal = float(ob_row["opening_balance"] or 0) if ob_row else 0.0
            capital_items.append({"name": a["name"], "balance": bal})
    except Exception:
        try:
            accounts = conn.execute(
                "SELECT id, name, opening_balance FROM capital_accounts ORDER BY name"
            ).fetchall()
            capital_items = [
                {"name": a["name"], "balance": float(a["opening_balance"] or 0)}
                for a in accounts
            ]
        except Exception:
            pass

    total_capital = sum(ci["balance"] for ci in capital_items)
    retained = total_assets - total_liabilities - total_capital
    check = total_liabilities + total_capital + retained

    conn.close()
    return {
        "fixed_assets":      fixed_assets,
        "total_fixed":       total_fixed,
        "stock":             stock,
        "receivables":       receivables,
        "total_recv":        total_recv,
        "cash":              cash,
        "bank":              bank,
        "total_current":     total_current,
        "total_assets":      total_assets,
        "payables":          payables,
        "total_payables":    total_payables,
        "committee_items":   committee_items,
        "total_committees":  total_committees,
        "total_liabilities": total_liabilities,
        "capital_items":     capital_items,
        "total_capital":     total_capital,
        "retained":          retained,
        "check":             check,
    }


class BalanceSheetPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = {}
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        top = QFrame()
        top.setFixedHeight(60)
        top.setStyleSheet("background:white;border-bottom:1px solid #e2e8f0;")
        top_lyt = QHBoxLayout(top)
        top_lyt.setContentsMargins(24, 0, 24, 0)
        top_lyt.setSpacing(12)

        title_lbl = QLabel("Balance Sheet")
        f = QFont()
        f.setBold(True)
        f.setPointSize(14)
        title_lbl.setFont(f)
        top_lyt.addWidget(title_lbl)
        top_lyt.addStretch()

        as_at_lbl = QLabel("As at:")
        as_at_lbl.setStyleSheet("color:#64748b;font-size:13px;")
        self._date_edit = QDateEdit()
        self._date_edit.setDate(QDate.currentDate())
        self._date_edit.setDisplayFormat("dd/MM/yyyy")
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setFixedHeight(32)
        self._date_edit.setFixedWidth(130)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedHeight(32)
        refresh_btn.setStyleSheet(
            "background:#2c6e85;color:white;border-radius:4px;padding:0 14px;font-weight:bold;"
        )
        refresh_btn.clicked.connect(self._refresh)

        export_btn = QPushButton("Export PDF")
        export_btn.setFixedHeight(32)
        export_btn.setStyleSheet(
            "background:#1e293b;color:white;border-radius:4px;padding:0 14px;font-weight:bold;"
        )
        export_btn.clicked.connect(self._export_pdf)

        top_lyt.addWidget(as_at_lbl)
        top_lyt.addWidget(self._date_edit)
        top_lyt.addWidget(refresh_btn)
        top_lyt.addWidget(export_btn)
        root.addWidget(top)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("QScrollArea{border:none;background:#f8fafc;}")
        root.addWidget(self._scroll)

        self._content = QWidget()
        self._content.setStyleSheet("background:#f8fafc;")
        self._scroll.setWidget(self._content)

        self._content_lyt = QVBoxLayout(self._content)
        self._content_lyt.setContentsMargins(40, 32, 40, 32)
        self._content_lyt.setSpacing(0)
        self._content_lyt.addStretch()

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh()

    def _refresh(self):
        self._data = bs_data()
        self._render()

    def _clear_content(self):
        while self._content_lyt.count():
            item = self._content_lyt.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _add_section(self, lyt, text: str, color: str):
        frame = QFrame()
        frame.setStyleSheet(f"background:{color};border-radius:4px;")
        inner = QHBoxLayout(frame)
        inner.setContentsMargins(16, 10, 16, 10)
        lbl = QLabel(text)
        f = QFont()
        f.setBold(True)
        f.setPointSize(11)
        lbl.setFont(f)
        lbl.setStyleSheet("color:white;background:transparent;")
        inner.addWidget(lbl)
        inner.addStretch()
        lyt.addWidget(frame)

    def _add_item(self, lyt, label: str, amount, indent: bool = False,
                  bold: bool = False, bg: str = None,
                  label_color: str = None, amount_color: str = None):
        frame = QFrame()
        style = ""
        if bg:
            style += f"background:{bg};"
        frame.setStyleSheet(style if style else "background:transparent;")

        inner = QHBoxLayout(frame)
        left_pad = 40 if indent else 16
        inner.setContentsMargins(left_pad, 6, 16, 6)
        inner.setSpacing(8)

        lbl = QLabel(label)
        f = QFont()
        if bold:
            f.setBold(True)
        lbl.setFont(f)
        lbl_style = "background:transparent;"
        if label_color:
            lbl_style += f"color:{label_color};"
        lbl.setStyleSheet(lbl_style)

        amt_lbl = QLabel(_fmt(amount) if isinstance(amount, (int, float)) else str(amount))
        amt_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        af = QFont()
        if bold:
            af.setBold(True)
        amt_lbl.setFont(af)
        amt_style = "background:transparent;"
        if amount_color:
            amt_style += f"color:{amount_color};"
        amt_lbl.setStyleSheet(amt_style)
        amt_lbl.setFixedWidth(160)

        inner.addWidget(lbl)
        inner.addStretch()
        inner.addWidget(amt_lbl)
        lyt.addWidget(frame)

    def _add_sep(self, lyt, thick: bool = False):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        h = 2 if thick else 1
        line.setFixedHeight(h)
        line.setStyleSheet(f"background:#cbd5e1;border:none;min-height:{h}px;max-height:{h}px;")
        lyt.addWidget(line)

    def _add_gap(self, lyt, px: int = 8):
        spacer = QWidget()
        spacer.setFixedHeight(px)
        spacer.setStyleSheet("background:transparent;")
        lyt.addWidget(spacer)

    def _add_grand_total(self, lyt, label: str, amount: float, bg: str):
        frame = QFrame()
        frame.setStyleSheet(f"background:{bg};border-radius:4px;")
        inner = QHBoxLayout(frame)
        inner.setContentsMargins(16, 10, 16, 10)
        lbl = QLabel(label)
        f = QFont()
        f.setBold(True)
        f.setPointSize(11)
        lbl.setFont(f)
        lbl.setStyleSheet("color:white;background:transparent;")
        amt_lbl = QLabel(_fmt(amount))
        af = QFont()
        af.setBold(True)
        af.setPointSize(11)
        amt_lbl.setFont(af)
        amt_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        amt_lbl.setStyleSheet("color:white;background:transparent;")
        amt_lbl.setFixedWidth(160)
        inner.addWidget(lbl)
        inner.addStretch()
        inner.addWidget(amt_lbl)
        lyt.addWidget(frame)

    def _render(self):
        self._clear_content()
        d = self._data
        lyt = self._content_lyt

        self._add_section(lyt, "ASSETS", "#2c6e85")
        self._add_gap(lyt, 6)

        if d["fixed_assets"]:
            fa_lbl = QLabel("Fixed Assets")
            ff = QFont()
            ff.setBold(True)
            fa_lbl.setFont(ff)
            fa_lbl.setContentsMargins(16, 6, 16, 2)
            fa_lbl.setStyleSheet("background:transparent;color:#1e293b;")
            lyt.addWidget(fa_lbl)
            for fa in d["fixed_assets"]:
                self._add_item(lyt, fa["name"], fa["value"], indent=True)
            self._add_item(lyt, "Total Fixed Assets", d["total_fixed"],
                           bold=True, bg="#e5f0f5")
            self._add_gap(lyt, 10)

        ca_lbl = QLabel("Current Assets")
        cf = QFont()
        cf.setBold(True)
        ca_lbl.setFont(cf)
        ca_lbl.setContentsMargins(16, 6, 16, 2)
        ca_lbl.setStyleSheet("background:transparent;color:#1e293b;")
        lyt.addWidget(ca_lbl)

        self._add_item(lyt, "Stock (at Cost)", d["stock"], indent=True)
        self._add_item(lyt, "Trade Receivables", d["total_recv"], indent=True)
        self._add_item(lyt, "Cash in Hand", d["cash"], indent=True)
        self._add_item(lyt, "Bank Balance", d["bank"], indent=True)
        self._add_item(lyt, "Total Current Assets", d["total_current"],
                       bold=True, bg="#e5f0f5")

        self._add_gap(lyt, 10)
        self._add_grand_total(lyt, "TOTAL ASSETS", d["total_assets"], "#2c6e85")

        self._add_gap(lyt, 16)
        self._add_sep(lyt, thick=True)
        self._add_gap(lyt, 16)

        self._add_section(lyt, "LIABILITIES", "#8b3535")
        self._add_gap(lyt, 6)

        tp_lbl = QLabel("Trade Payables")
        tpf = QFont()
        tpf.setBold(True)
        tp_lbl.setFont(tpf)
        tp_lbl.setContentsMargins(16, 6, 16, 2)
        tp_lbl.setStyleSheet("background:transparent;color:#1e293b;")
        lyt.addWidget(tp_lbl)
        for p in d["payables"]:
            self._add_item(lyt, p["name"], p["balance"], indent=True)
        self._add_item(lyt, "Total Trade Payables", d["total_payables"],
                       bold=True, bg="#f0e5e5")

        if d["committee_items"]:
            self._add_gap(lyt, 10)
            cm_lbl = QLabel("Committees")
            cmf = QFont()
            cmf.setBold(True)
            cm_lbl.setFont(cmf)
            cm_lbl.setContentsMargins(16, 6, 16, 2)
            cm_lbl.setStyleSheet("background:transparent;color:#1e293b;")
            lyt.addWidget(cm_lbl)
            for ci in d["committee_items"]:
                self._add_item(lyt, ci["name"], ci["remaining"], indent=True)
            self._add_item(lyt, "Total Committees", d["total_committees"],
                           bold=True, bg="#f0e5e5")

        self._add_gap(lyt, 10)
        self._add_grand_total(lyt, "TOTAL LIABILITIES", d["total_liabilities"], "#8b3535")

        self._add_gap(lyt, 16)
        self._add_sep(lyt, thick=True)
        self._add_gap(lyt, 16)

        self._add_section(lyt, "CAPITAL", "#5e3878")
        self._add_gap(lyt, 6)
        for ci in d["capital_items"]:
            self._add_item(lyt, ci["name"], ci["balance"], indent=True)
        self._add_grand_total(lyt, "TOTAL CAPITAL", d["total_capital"], "#5e3878")

        self._add_gap(lyt, 16)
        self._add_sep(lyt, thick=True)
        self._add_gap(lyt, 16)

        retained = d["retained"]
        if retained >= 0:
            self._add_item(lyt, "Retained Profit", retained,
                           bold=True, label_color="#2d7a4f", amount_color="#2d7a4f")
        else:
            self._add_item(lyt, "Retained Loss", retained,
                           bold=True, label_color="#8b3535", amount_color="#8b3535")

        self._add_gap(lyt, 16)
        self._add_sep(lyt, thick=True)
        self._add_gap(lyt, 8)

        self._add_grand_total(
            lyt,
            "TOTAL LIABILITIES + CAPITAL + RETAINED",
            d["check"],
            "#1e293b"
        )

        check_lbl = QLabel("(Balances)")
        check_lbl.setStyleSheet("color:#94a3b8;font-size:11px;background:transparent;")
        check_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        check_lbl.setContentsMargins(0, 4, 16, 0)
        lyt.addWidget(check_lbl)

        lyt.addStretch()

    def _export_pdf(self):
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib import colors
            from reportlab.lib.units import cm
            from reportlab.platypus import (
                SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
            )
            from reportlab.lib.styles import ParagraphStyle
            from reportlab.lib.enums import TA_RIGHT, TA_LEFT, TA_CENTER
        except ImportError:
            QMessageBox.critical(
                self, "Missing Library",
                "reportlab is not installed.\n\nInstall it with:\n  pip install reportlab"
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Balance Sheet PDF", "BalanceSheet.pdf", "PDF Files (*.pdf)"
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"

        d = self._data
        date_str = self._date_edit.date().toString("dd/MM/yyyy")
        shop_name = get_setting("shop_name") or "United Mobile"

        doc = SimpleDocTemplate(
            path,
            pagesize=A4,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )

        W = A4[0] - 4 * cm
        COL_LABEL = W - 4 * cm
        COL_AMT = 4 * cm

        def _ps(name, size=10, bold=False, color=colors.black,
                alignment=TA_LEFT, left_indent=0):
            return ParagraphStyle(
                name,
                fontName="Helvetica-Bold" if bold else "Helvetica",
                fontSize=size,
                textColor=color,
                alignment=alignment,
                leftIndent=left_indent,
                spaceAfter=0,
                spaceBefore=0,
                leading=size + 4,
            )

        normal = _ps("normal")
        normal_r = _ps("normal_r", alignment=TA_RIGHT)
        bold_s = _ps("bold_s", bold=True)
        bold_r = _ps("bold_r", bold=True, alignment=TA_RIGHT)
        indent_s = _ps("indent_s", left_indent=18)
        section_s = _ps("section_s", size=11, bold=True, color=colors.white)
        grand_s = _ps("grand_s", size=11, bold=True, color=colors.white)
        grand_r = _ps("grand_r", size=11, bold=True, color=colors.white, alignment=TA_RIGHT)
        header_s = _ps("header_s", size=13, bold=True, alignment=TA_CENTER)
        sub_header_s = _ps("sub_h", size=10, alignment=TA_CENTER)

        def _row(label_para, amount, label_style=normal, amount_style=normal_r,
                 bg=None, min_row_h=18):
            amt_text = _fmt(amount) if isinstance(amount, (int, float)) else str(amount)
            t = Table(
                [[Paragraph(label_para, label_style),
                  Paragraph(amt_text, amount_style)]],
                colWidths=[COL_LABEL, COL_AMT],
                rowHeights=[min_row_h],
            )
            ts = [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (0, 0), 6),
                ("RIGHTPADDING", (1, 0), (1, 0), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
            if bg:
                ts.append(("BACKGROUND", (0, 0), (-1, -1), bg))
            t.setStyle(TableStyle(ts))
            return t

        def _section_row(text, bg_hex):
            bg = colors.HexColor(bg_hex)
            t = Table(
                [[Paragraph(text, section_s), ""]],
                colWidths=[COL_LABEL, COL_AMT],
                rowHeights=[22],
            )
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("SPAN", (0, 0), (-1, -1)),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            return t

        def _grand_row(label, amount, bg_hex):
            bg = colors.HexColor(bg_hex)
            amt_text = _fmt(amount)
            t = Table(
                [[Paragraph(label, grand_s), Paragraph(amt_text, grand_r)]],
                colWidths=[COL_LABEL, COL_AMT],
                rowHeights=[22],
            )
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (0, 0), 10),
                ("RIGHTPADDING", (1, 0), (1, 0), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            return t

        def _subtotal_row(label, amount):
            return _row(label, amount,
                        label_style=bold_s, amount_style=bold_r,
                        bg=None, min_row_h=18)

        def _indent_row(label, amount):
            return _row("    " + label, amount,
                        label_style=indent_s, amount_style=normal_r)

        def _bold_bg_row(label, amount, bg_hex):
            return _row(label, amount,
                        label_style=bold_s, amount_style=bold_r,
                        bg=colors.HexColor(bg_hex), min_row_h=18)

        def _cat_row(label):
            t = Table(
                [[Paragraph(label, bold_s), ""]],
                colWidths=[COL_LABEL, COL_AMT],
                rowHeights=[16],
            )
            t.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]))
            return t

        story = []

        story.append(Paragraph(shop_name, header_s))
        story.append(Paragraph("Statement of Financial Position", sub_header_s))
        story.append(Paragraph(f"As at {date_str}", sub_header_s))
        story.append(Spacer(1, 14))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1e293b")))
        story.append(Spacer(1, 8))

        story.append(_section_row("ASSETS", "#2c6e85"))
        story.append(Spacer(1, 4))

        if d["fixed_assets"]:
            story.append(_cat_row("Fixed Assets"))
            for fa in d["fixed_assets"]:
                story.append(_indent_row(fa["name"], fa["value"]))
            story.append(_bold_bg_row("Total Fixed Assets", d["total_fixed"], "#e5f0f5"))
            story.append(Spacer(1, 6))

        story.append(_cat_row("Current Assets"))
        story.append(_indent_row("Stock (at Cost)", d["stock"]))
        story.append(_indent_row("Trade Receivables", d["total_recv"]))
        story.append(_indent_row("Cash in Hand", d["cash"]))
        story.append(_indent_row("Bank Balance", d["bank"]))
        story.append(_bold_bg_row("Total Current Assets", d["total_current"], "#e5f0f5"))
        story.append(Spacer(1, 6))
        story.append(_grand_row("TOTAL ASSETS", d["total_assets"], "#2c6e85"))

        story.append(Spacer(1, 10))
        story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#64748b")))
        story.append(Spacer(1, 10))

        story.append(_section_row("LIABILITIES", "#8b3535"))
        story.append(Spacer(1, 4))
        story.append(_cat_row("Trade Payables"))
        for p in d["payables"]:
            story.append(_indent_row(p["name"], p["balance"]))
        story.append(_bold_bg_row("Total Trade Payables", d["total_payables"], "#f0e5e5"))

        if d["committee_items"]:
            story.append(Spacer(1, 6))
            story.append(_cat_row("Committees"))
            for ci in d["committee_items"]:
                story.append(_indent_row(ci["name"], ci["remaining"]))
            story.append(_bold_bg_row("Total Committees", d["total_committees"], "#f0e5e5"))

        story.append(Spacer(1, 6))
        story.append(_grand_row("TOTAL LIABILITIES", d["total_liabilities"], "#8b3535"))

        story.append(Spacer(1, 10))
        story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#64748b")))
        story.append(Spacer(1, 10))

        story.append(_section_row("CAPITAL", "#5e3878"))
        story.append(Spacer(1, 4))
        for ci in d["capital_items"]:
            story.append(_indent_row(ci["name"], ci["balance"]))
        story.append(_grand_row("TOTAL CAPITAL", d["total_capital"], "#5e3878"))

        story.append(Spacer(1, 10))
        story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#64748b")))
        story.append(Spacer(1, 10))

        retained = d["retained"]
        if retained >= 0:
            ret_color = colors.HexColor("#2d7a4f")
            ret_label = "Retained Profit"
        else:
            ret_color = colors.HexColor("#8b3535")
            ret_label = "Retained Loss"

        ret_ps_l = _ps("ret_l", bold=True, color=ret_color)
        ret_ps_r = _ps("ret_r", bold=True, color=ret_color, alignment=TA_RIGHT)
        story.append(_row(ret_label, retained, label_style=ret_ps_l, amount_style=ret_ps_r))

        story.append(Spacer(1, 10))
        story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#64748b")))
        story.append(Spacer(1, 6))
        story.append(_grand_row(
            "TOTAL LIABILITIES + CAPITAL + RETAINED",
            d["check"],
            "#1e293b"
        ))
        story.append(Spacer(1, 4))

        check_note_ps = _ps("check_note", size=8, color=colors.HexColor("#94a3b8"),
                             alignment=TA_RIGHT)
        story.append(Paragraph("(Balances)", check_note_ps))

        doc.build(story)
        QMessageBox.information(self, "PDF Exported", f"Saved to:\n{path}")
