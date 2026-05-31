"""
WhatsApp message sending.
Primary:  pywhatkit.sendwhatmsg_instantly()  (opens WhatsApp Web, sends automatically)
Fallback: open wa.me URL in browser          (user clicks Send manually)
Either way, whatsapp_sent flag is updated in DB after success or manual send.
"""
import re
import webbrowser
from urllib.parse import quote

from database import get_connection, get_setting


def _clean_phone(raw: str) -> str | None:
    """Convert any Pakistani number to +92XXXXXXXXXX format."""
    digits = re.sub(r"\D", "", raw or "")
    if not digits:
        return None
    if digits.startswith("92") and len(digits) >= 12:
        return "+" + digits
    if digits.startswith("0") and len(digits) == 11:
        return "+92" + digits[1:]
    if len(digits) == 10:          # omitted leading 0
        return "+92" + digits
    return "+" + digits            # best-effort


def _format_message(template: str, **kwargs) -> str:
    msg = template
    for key, value in kwargs.items():
        msg = msg.replace("{" + key + "}", str(value or ""))
    return msg


def _mark_sent(sv_id: int):
    conn = get_connection()
    conn.execute("UPDATE sale_vouchers SET whatsapp_sent=1 WHERE id=?", (sv_id,))
    conn.commit()
    conn.close()


def fetch_whatsapp_data(sv_id: int) -> dict | None:
    conn = get_connection()
    sv = conn.execute("""
        SELECT sv_number, date, cash_customer_name, cash_customer_contact
        FROM sale_vouchers WHERE id=? AND type='cash'
    """, (sv_id,)).fetchone()
    if not sv:
        conn.close()
        return None
    lines = conn.execute("""
        SELECT b.name brand, m.name model, sl.imei
        FROM sale_lines sl
        JOIN models m ON m.id = sl.model_id
        JOIN brands b ON b.id = m.brand_id
        WHERE sl.sv_id = ?
        ORDER BY sl.id
    """, (sv_id,)).fetchall()
    conn.close()
    return {
        "sv_number": sv["sv_number"],
        "date": sv["date"],
        "customer_name": sv["cash_customer_name"] or "Customer",
        "contact": sv["cash_customer_contact"] or "",
        "lines": [(r["brand"] + " " + r["model"], r["imei"]) for r in lines],
    }


def send_sale_whatsapp(sv_id: int) -> tuple[bool, str]:
    """
    Send WhatsApp messages for a cash sale.
    Returns (success, message) where success=True means auto-sent,
    success=False means opened in browser for manual send.
    """
    data = fetch_whatsapp_data(sv_id)
    if not data:
        return False, "Not a cash sale or sale not found."

    phone = _clean_phone(data["contact"])
    if not phone:
        return False, "No contact number recorded for this sale."

    template = get_setting("whatsapp_template") or (
        "Assalam o Alaikum {customer_name}, thank you for purchasing "
        "{model_name} from {shop_name}. IMEI: {imei}. "
        "For queries call {shop_contact}."
    )
    shop_name    = get_setting("shop_name") or "United Mobile"
    shop_contact = get_setting("shop_contact") or ""

    # Build one message per IMEI (or combine if only one)
    messages = []
    for model_name, imei in data["lines"]:
        msg = _format_message(
            template,
            customer_name=data["customer_name"],
            model_name=model_name,
            imei=imei,
            shop_name=shop_name,
            shop_contact=shop_contact,
            date=data["date"],
        )
        messages.append(msg)

    combined = "\n".join(messages)

    # Try pywhatkit (auto-sends via WhatsApp Web)
    try:
        import pywhatkit
        for msg in messages:
            pywhatkit.sendwhatmsg_instantly(
                phone_no=phone,
                message=msg,
                wait_time=12,
                tab_close=True,
                close_time=3,
            )
        _mark_sent(sv_id)
        return True, f"WhatsApp sent to {phone}"
    except ImportError:
        pass
    except Exception as ex:
        # pywhatkit failed — fall through to browser fallback
        pass

    # Browser fallback: open wa.me with pre-filled message
    url = f"https://wa.me/{phone.lstrip('+')}?text={quote(combined)}"
    webbrowser.open(url)
    # Don't mark as sent automatically — user needs to press Send in browser
    return False, f"Opened WhatsApp in browser for {phone}. Click Send, then mark as sent."


def get_pending_whatsapp_sales() -> list:
    """Return cash sales where WhatsApp was not sent yet."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT sv.id, sv.sv_number, sv.date,
               sv.cash_customer_name, sv.cash_customer_contact,
               COUNT(sl.id) items
        FROM sale_vouchers sv
        LEFT JOIN sale_lines sl ON sl.sv_id = sv.id
        WHERE sv.type='cash' AND sv.whatsapp_sent=0
        GROUP BY sv.id
        ORDER BY sv.id DESC
    """).fetchall()
    conn.close()
    return rows


def mark_sent_manual(sv_id: int):
    _mark_sent(sv_id)
