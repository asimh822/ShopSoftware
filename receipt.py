"""
Thermal receipt printing — Blackcopper BC-85AC and other ESC/POS printers.
Primary:  win32print raw ESC/POS bytes (pywin32)
Fallback: python-escpos Win32Raw
Final:    preview dialog (sale is always saved regardless)
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

def _credit_previous_balance(data: dict):
    """Outstanding balance a credit customer owed BEFORE this sale.

    The current outstanding (read from the customers ledger at print time)
    already includes this invoice, so subtract the invoice total to get the
    previous balance. Returns None for cash sales or when no customer is set.
    """
    if data.get("type") != "credit" or not data.get("customer_id"):
        return None
    from sales import db_customer_balance
    outstanding_now = db_customer_balance(data["customer_id"])
    return outstanding_now - (data.get("total_amount") or 0)


def build_receipt_text(sv_number, date_str, customer_name, lines,
                       discount, total, note, shop_name, shop_address,
                       shop_contact, footer_msg, salesman_name=None,
                       sale_type=None, previous_balance=None) -> str:
    """
    lines = [(brand, model_name, imei, final_price), ...]
    Returns the full receipt as a plain-text string.

    For credit sales, pass sale_type="credit" and previous_balance to print
    the customer's running balance (Previous Balance / Invoice Total /
    Total Outstanding) below the TOTAL line.
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

    # Credit sales: show the customer's running balance.
    # Invoice Total is omitted here — it's already the TOTAL line above.
    if sale_type == "credit" and previous_balance is not None:
        total_outstanding = previous_balance + (total or 0)
        lines_out.append(_right_align("Previous Balance:", f"Rs. {fmt_pkr(previous_balance)}"))
        lines_out.append(_right_align("Total Outstanding:", f"Rs. {fmt_pkr(total_outstanding)}"))

    lines_out.append(_sep())

    if note:
        lines_out.append(note)
        lines_out.append(_sep())

    lines_out.append(_center(footer_msg or "Thank you for your purchase!"))
    lines_out.append("")
    lines_out.append("")

    return "\n".join(lines_out)


def build_receipt_bytes(text: str) -> bytes:
    """Convert plain receipt text to ESC/POS byte stream for direct raw printing."""
    raw = INIT
    sep = _sep()
    in_header = True
    for line in text.split("\n"):
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


def list_windows_printers() -> list[str]:
    """Return names of all printers installed on this Windows machine."""
    try:
        import win32print
        printers = win32print.EnumPrinters(
            win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        )
        return sorted(p[2] for p in printers)
    except Exception:
        return []


def _send_raw_win32print(printer_name: str, raw: bytes) -> None:
    """Send raw bytes to a Windows printer via win32print. Raises on failure."""
    import win32print
    hPrinter = win32print.OpenPrinter(printer_name)
    try:
        win32print.StartDocPrinter(hPrinter, 1, ("Receipt", None, "RAW"))
        win32print.StartPagePrinter(hPrinter)
        win32print.WritePrinter(hPrinter, raw)
        win32print.EndPagePrinter(hPrinter)
        win32print.EndDocPrinter(hPrinter)
    finally:
        win32print.ClosePrinter(hPrinter)


def _printer_mode() -> str:
    """Connection mode: 'usb' (default) or 'network'. Read fresh on every print."""
    return (get_setting("printer_mode") or "usb").strip().lower()


def _print_target_ready(printer_name: str) -> bool:
    """True if a print can be attempted: network mode (uses IP/port) needs no
    Windows printer name; USB mode needs a printer name selected."""
    if _printer_mode() == "network":
        return True
    return bool(printer_name)


def _send_raw_network(raw: bytes) -> None:
    """Send raw ESC/POS bytes to a network thermal printer over TCP (e.g. port
    9100). Raises RuntimeError with a clear message on any failure."""
    import socket

    ip = (get_setting("printer_ip") or "").strip()
    port_str = (get_setting("printer_port") or "9100").strip()
    if not ip:
        raise RuntimeError(
            "Network printing is selected but no printer IP address is set.\n\n"
            "Set the IP in Settings → Printer Connection, or switch back to USB mode."
        )
    try:
        port = int(port_str)
    except ValueError:
        port = 9100

    try:
        with socket.create_connection((ip, port), timeout=5) as sock:
            sock.sendall(raw)
    except Exception as e:
        raise RuntimeError(
            f"Network print failed — could not reach printer at {ip}:{port}.\n"
            f"({e})\n\n"
            "Check that the IP/port in Settings → Printer Connection are correct, "
            "the printer is powered on and on the same network, or switch back to "
            "USB mode."
        )


def _print_raw(printer_name: str, text: str) -> None:
    """
    Send receipt text to the thermal printer using the configured connection mode.
    Network mode:  raw ESC/POS bytes over TCP/IP (IP + port from settings).
    USB/Local mode:
      Primary:  win32print with ESC/POS bytes (works with any RAW-capable driver).
      Fallback: python-escpos Win32Raw.
    Raises an exception with a clear message if printing fails.
    """
    raw = build_receipt_bytes(text)

    # Routed fresh every call — switching mode in Settings needs no restart.
    if _printer_mode() == "network":
        _send_raw_network(raw)
        return

    errors = []

    # ── Primary: win32print direct RAW ───────────────────────────────────────
    try:
        _send_raw_win32print(printer_name, raw)
        return
    except ImportError:
        errors.append("win32print not installed — run: pip install pywin32")
    except Exception as e:
        errors.append(f"win32print: {e}")

    # ── Fallback: python-escpos Win32Raw ──────────────────────────────────────
    try:
        from escpos.printer import Win32Raw
        p = Win32Raw(printer_name)
        p._raw(raw)
        return
    except ImportError:
        errors.append("python-escpos not installed — run: pip install python-escpos")
    except Exception as e:
        errors.append(f"python-escpos: {e}")

    raise RuntimeError(
        f"Could not print to '{printer_name}'.\n\n"
        + "\n".join(f"• {e}" for e in errors)
        + "\n\nCheck Settings → Thermal Receipt and use 'Pick Printer' to select the correct name."
    )


# ── Fetch sale data from DB ───────────────────────────────────────────────────

def fetch_receipt_data(sv_id: int) -> dict | None:
    conn = get_connection()
    sv = conn.execute("""
        SELECT sv.sv_number, sv.date, sv.type, sv.customer_id,
               sv.total_amount, sv.discount, sv.note,
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
        "type":         sv["type"],
        "customer_id":  sv["customer_id"],
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
        sale_type        = data.get("type"),
        previous_balance = _credit_previous_balance(data),
    )

    printer_name = get_setting("thermal_printer") or ""

    if _print_target_ready(printer_name):
        try:
            _print_raw(printer_name, text)
            return True
        except Exception as e:
            # Show the error — then fall through to preview so the sale isn't lost
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                parent, "Printer Error",
                f"{e}\n\nShowing receipt preview — your sale has been saved."
            )

    _show_preview(text, data["sv_number"], parent)
    return False


def print_receipt_headless(sv_id: int, printer_name: str | None = None) -> tuple[bool, str]:
    """
    Print a sale receipt without any Qt UI — safe to call from the Flask server
    (no QApplication, no display). Returns (success, error_message).
    """
    data = fetch_receipt_data(sv_id)
    if not data:
        return False, "Sale not found"

    printer_name = printer_name or get_setting("thermal_printer") or ""
    if not _print_target_ready(printer_name):
        return False, "No thermal_printer setting configured"

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
        sale_type        = data.get("type"),
        previous_balance = _credit_previous_balance(data),
    )

    try:
        _print_raw(printer_name, text)
        return True, ""
    except Exception as e:
        return False, str(e)


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
    if _print_target_ready(printer_name):
        try:
            _print_raw(printer_name, text)
            return True
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(parent, "Printer Error",
                f"{e}\n\nShowing receipt preview instead.")
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


# ── Cash Purchase receipt ─────────────────────────────────────────────────────

def fetch_cash_purchase_data(pv_number: str) -> dict | None:
    conn = get_connection()
    pv = conn.execute("""
        SELECT pv.id, pv.pv_number, pv.date,
               COALESCE(pv.total_amount, 0) total_amount,
               COALESCE(pv.notes, '') notes,
               COALESCE(pv.egadget_ref, '') egadget_ref,
               COALESCE(pv.payment_method, 'cash') payment_method,
               COALESCE(pv.cash_amount, 0) cash_amount,
               COALESCE(pv.bank_amount, 0) bank_amount,
               COALESCE(pv.bank_ref, '') bank_ref,
               COALESCE(ba.name, '') bank_name
        FROM purchase_vouchers pv
        LEFT JOIN bank_accounts ba ON ba.id = pv.bank_account_id
        WHERE pv.pv_number = ? AND pv.purchase_type = 'cash'
    """, (pv_number,)).fetchone()
    if not pv:
        conn.close()
        return None
    lines = conn.execute("""
        SELECT b.name brand, m.name model, pl.imei, pl.purchase_price
        FROM purchase_lines pl
        JOIN models m ON m.id = pl.model_id
        JOIN brands b ON b.id = m.brand_id
        WHERE pl.pv_id = ?
        ORDER BY pl.id
    """, (pv["id"],)).fetchall()
    conn.close()
    return {
        "pv_number":      pv["pv_number"],
        "date":           pv["date"],
        "total_amount":   float(pv["total_amount"]),
        "notes":          pv["notes"],
        "egadget_ref":    pv["egadget_ref"],
        "payment_method": pv["payment_method"],
        "cash_amount":    float(pv["cash_amount"]),
        "bank_amount":    float(pv["bank_amount"]),
        "bank_ref":       pv["bank_ref"],
        "bank_name":      pv["bank_name"],
        "lines": [(r["brand"], r["model"], r["imei"], r["purchase_price"]) for r in lines],
    }


def build_cash_purchase_receipt_text(data: dict, shop_name: str, shop_address: str,
                                      shop_contact: str, footer_msg: str) -> str:
    lines_out = []
    lines_out.append(_center(shop_name))
    for addr_line in shop_address.split(","):
        lines_out.append(_center(addr_line.strip()))
    lines_out.append(_center(shop_contact))
    lines_out.append(_sep())

    lines_out.append("CASH PURCHASE VOUCHER")
    lines_out.append(f"PV No:      {data['pv_number']}")
    lines_out.append(f"Date:       {data['date']}")
    lines_out.append(f"eGadget Ref: {data['egadget_ref']}")

    pm = data["payment_method"]
    if pm == "cash":
        lines_out.append(f"Payment:    Cash — PKR {fmt_pkr(data['total_amount'])}")
    elif pm == "bank":
        lines_out.append(f"Payment:    Bank Transfer — PKR {fmt_pkr(data['bank_amount'])}")
        if data["bank_name"]:
            lines_out.append(f"Account:    {data['bank_name']}")
        if data["bank_ref"]:
            lines_out.append(f"Bank Ref:   {data['bank_ref']}")
    else:  # split
        lines_out.append(f"Payment:    Split")
        lines_out.append(f"  Cash:     PKR {fmt_pkr(data['cash_amount'])}")
        lines_out.append(f"  Bank:     PKR {fmt_pkr(data['bank_amount'])}")
        if data["bank_name"]:
            lines_out.append(f"  Account:  {data['bank_name']}")
        if data["bank_ref"]:
            lines_out.append(f"  Bank Ref: {data['bank_ref']}")

    lines_out.append(_sep())
    lines_out.append(f"{'Item':<22}{'IMEI':>10}{'Price':>10}")
    lines_out.append(_sep())

    for brand, model, imei, price in data["lines"]:
        label = f"{brand} {model}"
        if len(label) > 22:
            label = label[:21] + "…"
        imei_short = imei[-5:] if len(imei) > 5 else imei
        lines_out.append(f"{label:<22}{imei_short:>10}{fmt_pkr(price):>10}")

    lines_out.append(_sep())
    lines_out.append(_right_align("TOTAL:", f"PKR {fmt_pkr(data['total_amount'])}"))
    lines_out.append(_sep())

    if data["notes"]:
        lines_out.append(data["notes"])
        lines_out.append(_sep())

    lines_out.append(_center(footer_msg or "Thank you!"))
    lines_out.append("")
    lines_out.append("")
    return "\n".join(lines_out)


def print_cash_purchase_receipt(pv_number: str, parent=None) -> bool:
    """Print a cash purchase voucher receipt. Returns True if printed."""
    data = fetch_cash_purchase_data(pv_number)
    if not data:
        return False
    text = build_cash_purchase_receipt_text(
        data,
        shop_name    = get_setting("shop_name") or "United Mobile",
        shop_address = get_setting("shop_address") or "",
        shop_contact = get_setting("shop_contact") or "",
        footer_msg   = get_setting("receipt_footer") or "Thank you!",
    )
    printer_name = get_setting("thermal_printer") or ""
    if _print_target_ready(printer_name):
        try:
            _print_raw(printer_name, text)
            return True
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(parent, "Printer Error",
                f"{e}\n\nShowing receipt preview instead.")
    _show_preview(text, pv_number, parent)
    return False
