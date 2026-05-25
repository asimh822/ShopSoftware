"""
Thermal receipt printing.
Primary:  python-escpos Win32Raw (printer name stored in settings)
Fallback: win32print raw bytes
Final fallback: preview dialog
"""
import textwrap
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox, QLabel
from PyQt6.QtGui import QFont

from database import get_connection, get_setting

WIDTH = 42   # characters — standard 80 mm thermal at 12 cpi


# ── ESC/POS byte helpers ──────────────────────────────────────────────────────

_ESC = b"\x1b"
_GS  = b"\x1d"
INIT          = _ESC + b"@"
ALIGN_CENTER  = _ESC + b"a\x01"
ALIGN_LEFT    = _ESC + b"a\x00"
BOLD_ON       = _ESC + b"E\x01"
BOLD_OFF      = _ESC + b"E\x00"
DOUBLE_ON     = _ESC + b"!\x10"
DOUBLE_OFF    = _ESC + b"!\x00"
FEED          = b"\n"
CUT           = _GS  + b"V\x00"


def _center(text: str) -> str:
    return text.center(WIDTH)


def _right_align(label: str, value: str) -> str:
    gap = WIDTH - len(label) - len(value)
    if gap < 1:
        gap = 1
    return label + " " * gap + value


def _sep() -> str:
    return "-" * WIDTH


def fmt_pkr(val) -> str:
    if val is None:
        return "0"
    return f"{float(val):,.0f}"


# ── Build receipt text ────────────────────────────────────────────────────────

def build_receipt_text(sv_number, date_str, customer_name, lines,
                       discount, total, note, shop_name, shop_address,
                       shop_contact, footer_msg, salesman_name=None) -> str:
    """
    lines = [(brand, model_name, imei, final_price), ...]
    Returns the full receipt as a plain-text string.
    """
    lines_out = []

    lines_out.append(_center(shop_name))
    for addr_line in shop_address.split(","):
        lines_out.append(_center(addr_line.strip()))
    lines_out.append(_center(shop_contact))
    if salesman_name:
        lines_out.append(_center(f"Sold by: {salesman_name}"))
    lines_out.append(_sep())
    lines_out.append(f"Invoice: {sv_number}")
    lines_out.append(f"Date:    {date_str}")
    lines_out.append(f"Customer: {customer_name}")
    lines_out.append(_sep())
    lines_out.append(f"{'Item':<22}{'IMEI':>10}{'Price':>10}")
    lines_out.append(_sep())

    for brand, model, imei, price in lines:
        label = f"{brand} {model}"
        if len(label) > 22:
            label = label[:21] + "…"
        imei_short = imei[-5:] if len(imei) > 5 else imei
        lines_out.append(f"{label:<22}{imei_short:>10}{fmt_pkr(price):>10}")

    lines_out.append(_sep())

    if discount:
        lines_out.append(_right_align("Discount:", f"-{fmt_pkr(discount)}"))
    lines_out.append(_right_align("TOTAL:", f"PKR {fmt_pkr(total)}"))
    lines_out.append(_sep())

    if note:
        lines_out.append(note)
        lines_out.append(_sep())

    lines_out.append(_center(footer_msg or "Thank you for your purchase!"))
    lines_out.append("")
    lines_out.append("")

    return "\n".join(lines_out)


def build_receipt_bytes(text: str) -> bytes:
    raw = INIT + ALIGN_CENTER
    raw += BOLD_ON + DOUBLE_ON
    # Split text back into lines and add ESC/POS formatting
    raw = INIT
    lines = text.split("\n")
    header_done = False
    sep = _sep()
    in_header = True
    for line in lines:
        if line == sep:
            in_header = False
            raw += ALIGN_LEFT
            raw += line.encode("cp1252", errors="replace") + FEED
            continue
        if in_header:
            raw += ALIGN_CENTER + BOLD_ON
            raw += line.encode("cp1252", errors="replace") + FEED
            raw += BOLD_OFF + ALIGN_LEFT
        else:
            raw += line.encode("cp1252", errors="replace") + FEED
    raw += FEED + FEED + CUT
    return raw


# ── Fetch sale data from DB ───────────────────────────────────────────────────

def fetch_receipt_data(sv_id: int) -> dict | None:
    conn = get_connection()
    sv = conn.execute("""
        SELECT sv.sv_number, sv.date, sv.type, sv.total_amount, sv.discount, sv.note,
               COALESCE(c.name, sv.cash_customer_name) customer_name,
               sm.name salesman_name
        FROM sale_vouchers sv
        LEFT JOIN customers c ON c.id = sv.customer_id
        LEFT JOIN salesmen sm ON sm.id = sv.salesman_id
        WHERE sv.id = ?
    """, (sv_id,)).fetchone()
    if not sv:
        conn.close()
        return None
    lines = conn.execute("""
        SELECT b.name brand, m.name model, sl.imei, sl.final_price
        FROM sale_lines sl
        JOIN models m ON m.id = sl.model_id
        JOIN brands b ON b.id = m.brand_id
        WHERE sl.sv_id = ?
        ORDER BY sl.id
    """, (sv_id,)).fetchall()
    conn.close()
    return {
        "sv_number":    sv["sv_number"],
        "date":         sv["date"],
        "customer_name": sv["customer_name"] or "Walk-in",
        "total_amount": sv["total_amount"],
        "discount":     sv["discount"],
        "note":         sv["note"],
        "salesman_name": sv["salesman_name"],
        "lines": [(r["brand"], r["model"], r["imei"], r["final_price"]) for r in lines],
    }


# ── Print ─────────────────────────────────────────────────────────────────────

def print_receipt(sv_id: int, parent=None) -> bool:
    """Returns True if printed, False if fell back to preview dialog."""
    data = fetch_receipt_data(sv_id)
    if not data:
        return False

    text = build_receipt_text(
        sv_number     = data["sv_number"],
        date_str      = data["date"],
        customer_name = data["customer_name"],
        lines         = data["lines"],
        discount      = data["discount"],
        total         = data["total_amount"],
        note          = data["note"],
        shop_name     = get_setting("shop_name") or "United Mobile",
        shop_address  = get_setting("shop_address") or "",
        shop_contact  = get_setting("shop_contact") or "",
        footer_msg    = get_setting("receipt_footer") or "Thank you for your purchase!",
        salesman_name = data.get("salesman_name"),
    )

    printer_name = get_setting("thermal_printer") or ""

    # Try python-escpos Win32Raw
    if printer_name:
        try:
            from escpos.printer import Win32Raw
            p = Win32Raw(printer_name)
            p.text(text)
            p.cut()
            return True
        except Exception:
            pass

        # Try win32print raw fallback
        try:
            import win32print
            raw = build_receipt_bytes(text)
            hPrinter = win32print.OpenPrinter(printer_name)
            try:
                hJob = win32print.StartDocPrinter(hPrinter, 1, ("Receipt", None, "RAW"))
                win32print.StartPagePrinter(hPrinter)
                win32print.WritePrinter(hPrinter, raw)
                win32print.EndPagePrinter(hPrinter)
                win32print.EndDocPrinter(hPrinter)
            finally:
                win32print.ClosePrinter(hPrinter)
            return True
        except Exception:
            pass

    # Fallback: preview dialog
    _show_preview(text, data["sv_number"], parent)
    return False


def _show_preview(text: str, voucher_number: str, parent=None):
    dlg = QDialog(parent)
    dlg.setWindowTitle(f"Receipt Preview — {voucher_number}")
    dlg.resize(420, 540)
    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(12, 12, 12, 12)
    note = QLabel(
        "No printer configured. Set a printer name in Settings to enable direct printing."
    )
    note.setStyleSheet("color:#d97706; font-size:9pt;")
    note.setWordWrap(True)
    layout.addWidget(note)
    te = QTextEdit()
    te.setReadOnly(True)
    te.setFont(QFont("Courier New", 10))
    te.setPlainText(text)
    layout.addWidget(te)
    btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    btns.rejected.connect(dlg.reject)
    layout.addWidget(btns)
    dlg.exec()


# ── Return receipt builder ────────────────────────────────────────────────────

def build_return_receipt_text(voucher_num, return_type, date_str, party_name,
                               lines, total, notes,
                               shop_name, shop_address, shop_contact,
                               footer_msg) -> str:
    """
    Generic return receipt.
    lines = [(brand, model_name, imei, price), ...]
    return_type: 'PURCHASE RETURN' or 'SALES RETURN'
    """
    lines_out = []
    lines_out.append(_center(shop_name))
    for addr_line in shop_address.split(","):
        lines_out.append(_center(addr_line.strip()))
    lines_out.append(_center(shop_contact))
    lines_out.append(_sep())

    party_label = "Supplier:" if "PURCHASE" in return_type else "Customer:"
    lines_out.append(f"{return_type}: {voucher_num}")
    lines_out.append(f"Date:     {date_str}")
    lines_out.append(f"{party_label} {party_name}")
    lines_out.append(_sep())
    lines_out.append(f"{'Item':<22}{'IMEI':>10}{'Price':>10}")
    lines_out.append(_sep())

    for brand, model, imei, price in lines:
        label = f"{brand} {model}"
        if len(label) > 22:
            label = label[:21] + "…"
        imei_short = imei[-5:] if len(imei) > 5 else imei
        lines_out.append(f"{label:<22}{imei_short:>10}{fmt_pkr(price):>10}")

    lines_out.append(_sep())
    lines_out.append(_right_align("RETURN TOTAL:", f"PKR {fmt_pkr(total)}"))
    lines_out.append(_sep())

    if notes:
        lines_out.append(notes)
        lines_out.append(_sep())

    lines_out.append(_center(footer_msg or "Thank you!"))
    lines_out.append("")
    lines_out.append("")
    return "\n".join(lines_out)


def _print_return_raw(text: str, printer_name: str, voucher_num: str, parent=None) -> bool:
    """Attempt physical printing; falls back to preview. Returns True if printed."""
    if printer_name:
        try:
            from escpos.printer import Win32Raw
            p = Win32Raw(printer_name)
            p.text(text)
            p.cut()
            return True
        except Exception:
            pass
        try:
            import win32print
            raw = build_receipt_bytes(text)
            hPrinter = win32print.OpenPrinter(printer_name)
            try:
                win32print.StartDocPrinter(hPrinter, 1, ("Return Receipt", None, "RAW"))
                win32print.StartPagePrinter(hPrinter)
                win32print.WritePrinter(hPrinter, raw)
                win32print.EndPagePrinter(hPrinter)
                win32print.EndDocPrinter(hPrinter)
            finally:
                win32print.ClosePrinter(hPrinter)
            return True
        except Exception:
            pass
    _show_preview(text, voucher_num, parent)
    return False


# ── Purchase Return receipt ───────────────────────────────────────────────────

def fetch_purchase_return_data(pr_id: int) -> dict | None:
    conn = get_connection()
    pr = conn.execute("""
        SELECT pr.pr_number, pr.date, pr.notes,
               s.name AS supplier_name
        FROM purchase_returns pr
        JOIN suppliers s ON s.id = pr.supplier_id
        WHERE pr.id = ?
    """, (pr_id,)).fetchone()
    if not pr:
        conn.close()
        return None
    lines = conn.execute("""
        SELECT b.name brand, m.name model, prl.imei, prl.return_price
        FROM purchase_return_lines prl
        JOIN models m ON m.id = prl.model_id
        JOIN brands b ON b.id = m.brand_id
        WHERE prl.pr_id = ?
        ORDER BY prl.id
    """, (pr_id,)).fetchall()
    conn.close()
    return {
        "pr_number": pr["pr_number"],
        "date": pr["date"],
        "supplier_name": pr["supplier_name"],
        "notes": pr["notes"] or "",
        "lines": [(r["brand"], r["model"], r["imei"], r["return_price"]) for r in lines],
    }


def print_purchase_return_receipt(pr_id: int, parent=None) -> bool:
    data = fetch_purchase_return_data(pr_id)
    if not data:
        return False
    total = sum(p for _, _, _, p in data["lines"])
    text = build_return_receipt_text(
        voucher_num  = data["pr_number"],
        return_type  = "PURCHASE RETURN",
        date_str     = data["date"],
        party_name   = data["supplier_name"],
        lines        = data["lines"],
        total        = total,
        notes        = data["notes"],
        shop_name    = get_setting("shop_name") or "United Mobile",
        shop_address = get_setting("shop_address") or "",
        shop_contact = get_setting("shop_contact") or "",
        footer_msg   = get_setting("receipt_footer") or "Thank you!",
    )
    return _print_return_raw(text, get_setting("thermal_printer") or "",
                             data["pr_number"], parent)


# ── Sales Return receipt ──────────────────────────────────────────────────────

def fetch_sale_return_data(sr_id: int) -> dict | None:
    conn = get_connection()
    sr = conn.execute("""
        SELECT sr.sr_number, sr.date, sr.notes,
               COALESCE(c.name, '—') AS customer_name
        FROM sale_returns sr
        LEFT JOIN customers c ON c.id = sr.customer_id
        WHERE sr.id = ?
    """, (sr_id,)).fetchone()
    if not sr:
        conn.close()
        return None
    lines = conn.execute("""
        SELECT b.name brand, m.name model, srl.imei, srl.return_price
        FROM sale_return_lines srl
        JOIN models m ON m.id = srl.model_id
        JOIN brands b ON b.id = m.brand_id
        WHERE srl.sr_id = ?
        ORDER BY srl.id
    """, (sr_id,)).fetchall()
    conn.close()
    return {
        "sr_number": sr["sr_number"],
        "date": sr["date"],
        "customer_name": sr["customer_name"],
        "notes": sr["notes"] or "",
        "lines": [(r["brand"], r["model"], r["imei"], r["return_price"]) for r in lines],
    }


def print_sale_return_receipt(sr_id: int, parent=None) -> bool:
    data = fetch_sale_return_data(sr_id)
    if not data:
        return False
    total = sum(p for _, _, _, p in data["lines"])
    text = build_return_receipt_text(
        voucher_num  = data["sr_number"],
        return_type  = "SALES RETURN",
        date_str     = data["date"],
        party_name   = data["customer_name"],
        lines        = data["lines"],
        total        = total,
        notes        = data["notes"],
        shop_name    = get_setting("shop_name") or "United Mobile",
        shop_address = get_setting("shop_address") or "",
        shop_contact = get_setting("shop_contact") or "",
        footer_msg   = get_setting("receipt_footer") or "Thank you!",
    )
    return _print_return_raw(text, get_setting("thermal_printer") or "",
                             data["sr_number"], parent)
