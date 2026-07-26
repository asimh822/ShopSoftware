"""
WhatsApp message sending.
Primary:  pywhatkit.sendwhatmsg_instantly()  (opens WhatsApp Web, sends automatically)
Fallback: open wa.me URL in browser          (user clicks Send manually)
Either way, whatsapp_sent flag is updated in DB after success or manual send.

Backlog drip campaign (send_backlog_batch): clears old unsent sales at a
capped rate — max wa_daily_limit customers per day, one message per customer,
random gaps between sends — so WhatsApp never sees a bulk-send pattern.
"""
import datetime
import random
import re
import time
import webbrowser
from urllib.parse import quote

from database import get_connection, get_setting, set_setting


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


# ── Backlog drip campaign ─────────────────────────────────────────────────────

DEFAULT_BACKLOG_TEMPLATE = (
    "Assalam o Alaikum {customer_name}! This is {shop_name}, Multan. "
    "Thank you for purchasing {model_name} (IMEI: {imei}) from us. "
    "Please save this number — for any query or after-sales support "
    "call {shop_contact}."
)


def _skip_numbers() -> set:
    """Digit-only numbers that must never receive campaign messages
    (the shop's own numbers used for test/walk-in entries)."""
    raw = get_setting("wa_skip_numbers") or ""
    nums = {re.sub(r"\D", "", part) for part in raw.split(",") if part.strip()}
    shop = re.sub(r"\D", "", get_setting("shop_contact") or "")
    if shop:
        nums.add(shop)
    return nums


def get_backlog_contacts() -> list:
    """
    Unique customers with an unsent cash sale, oldest first.
    One entry per contact number; the voucher kept is the customer's most
    recent one (its model/IMEI go in the message). Shop numbers excluded.
    """
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, sv_number, date, cash_customer_name AS name,
               cash_customer_contact AS contact
        FROM sale_vouchers
        WHERE type='cash' AND COALESCE(whatsapp_sent,0)=0
          AND cash_customer_contact IS NOT NULL
          AND LENGTH(cash_customer_contact)=11
        ORDER BY id DESC
    """).fetchall()
    conn.close()
    skip = _skip_numbers()
    seen, newest_first = set(), []
    for r in rows:                      # newest voucher wins the dedup
        digits = re.sub(r"\D", "", r["contact"])
        if digits in skip or digits in seen:
            continue
        seen.add(digits)
        newest_first.append({"id": r["id"], "sv_number": r["sv_number"],
                             "date": r["date"], "name": r["name"],
                             "contact": digits})
    return list(reversed(newest_first))  # drip oldest customers first


def _mark_contact_sent(contact_digits: str):
    """Mark every unsent cash voucher of this contact as sent — the customer
    got their one campaign message; never message them again for old sales."""
    conn = get_connection()
    conn.execute("""
        UPDATE sale_vouchers SET whatsapp_sent=1
        WHERE type='cash' AND COALESCE(whatsapp_sent,0)=0
          AND REPLACE(REPLACE(REPLACE(cash_customer_contact,'-',''),' ',''),'+','')=?
    """, (contact_digits,))
    conn.commit()
    conn.close()


def drip_quota_left() -> int:
    """How many campaign messages may still be sent today."""
    limit = int(get_setting("wa_daily_limit") or 10)
    today = datetime.date.today().isoformat()
    if (get_setting("wa_drip_date") or "") != today:
        return limit
    return max(0, limit - int(get_setting("wa_drip_count") or 0))


def _bump_drip_count():
    today = datetime.date.today().isoformat()
    if (get_setting("wa_drip_date") or "") != today:
        set_setting("wa_drip_date", today)
        set_setting("wa_drip_count", "1")
    else:
        set_setting("wa_drip_count",
                    str(int(get_setting("wa_drip_count") or 0) + 1))


def send_backlog_batch(progress_cb=None, should_stop=None) -> tuple[int, str]:
    """
    Send today's drip batch: up to drip_quota_left() unique customers,
    one personalised message each, random 25–55 s gap between sends.

    progress_cb(done, total, name) — optional, called after each send.
    should_stop() -> bool          — optional, checked before each send.

    Returns (sent_count, status_message). Aborts on the first send failure
    so a broken WhatsApp Web session can't burn through the quota.
    Real-time sale messages do NOT count against this quota.
    """
    try:
        import pywhatkit
    except ImportError:
        return 0, ("pywhatkit is not installed — the batch needs auto-send. "
                   "Run:  pip install pywhatkit")

    quota = drip_quota_left()
    if quota <= 0:
        return 0, "Daily limit already reached — next batch available tomorrow."

    batch = get_backlog_contacts()[:quota]
    if not batch:
        return 0, "Backlog is clear — nothing to send."

    template = get_setting("whatsapp_backlog_template") or DEFAULT_BACKLOG_TEMPLATE
    shop_name    = get_setting("shop_name") or "United Mobile"
    shop_contact = get_setting("shop_contact") or ""

    sent = 0
    for i, cust in enumerate(batch):
        if should_stop and should_stop():
            break
        data = fetch_whatsapp_data(cust["id"])
        if not data or not data["lines"]:
            _mark_contact_sent(cust["contact"])   # unusable voucher — skip forever
            continue
        model_name, imei = data["lines"][0]
        if len(data["lines"]) > 1:
            model_name += f" (+{len(data['lines']) - 1} more)"
        msg = _format_message(
            template,
            customer_name=data["customer_name"],
            model_name=model_name,
            imei=imei,
            shop_name=shop_name,
            shop_contact=shop_contact,
            date=data["date"],
        )
        phone = _clean_phone(cust["contact"])
        try:
            pywhatkit.sendwhatmsg_instantly(
                phone_no=phone, message=msg,
                wait_time=15, tab_close=True, close_time=4,
            )
        except Exception as ex:
            return sent, (f"Stopped after {sent} send(s): sending to {phone} "
                          f"failed ({ex}). Check WhatsApp Web login and retry.")
        _mark_contact_sent(cust["contact"])
        _bump_drip_count()
        sent += 1
        if progress_cb:
            progress_cb(sent, len(batch), data["customer_name"])
        if i < len(batch) - 1:
            time.sleep(random.uniform(25, 55))

    left = drip_quota_left()
    return sent, (f"Done — {sent} customer(s) messaged today. "
                  f"{len(get_backlog_contacts())} still in backlog, "
                  f"{left} more allowed today.")


def send_digest_whatsapp(digest: dict) -> tuple[bool, str]:
    """
    Send the owner daily digest as a WhatsApp message to the number stored
    in settings under key 'owner_whatsapp'.

    digest — dict returned by build_daily_digest() from reports.py.
    Returns (success, status_message).
    """
    raw_number = get_setting("owner_whatsapp") or ""
    phone = _clean_phone(raw_number)
    if not phone:
        return False, "Owner WhatsApp number not set. Add it in Settings → WhatsApp."

    shop_name = get_setting("shop_name") or "United Mobile"

    def _pkr(val):
        try:
            return f"{float(val):,.0f}"
        except Exception:
            return "0"

    lines = [
        f"*{shop_name} — Daily Close*",
        f"Date: {digest.get('date', '')}",
        "",
        f"Sales: {digest.get('sales_count', 0)} vouchers | Rs. {_pkr(digest.get('sales_total', 0))}",
        f"Gross Profit: Rs. {_pkr(digest.get('gross_profit', 0))}",
        f"Net Cash: Rs. {_pkr(digest.get('net_cash', 0))}",
        f"Net Bank: Rs. {_pkr(digest.get('net_bank', 0))}",
    ]

    credit_given = digest.get("credit_given", 0)
    credit_coll  = digest.get("credit_collected", 0)
    if credit_given or credit_coll:
        lines.append(
            f"Credit Given: Rs. {_pkr(credit_given)}  |  Collected: Rs. {_pkr(credit_coll)}"
        )

    expenses = digest.get("expenses_cash", 0)
    if expenses:
        lines.append(f"Cash Expenses: Rs. {_pkr(expenses)}")

    below = digest.get("below_cost_count", 0)
    if below:
        lines.append(f"⚠ {below} item(s) sold below cost")

    big_disc = digest.get("biggest_discount", 0)
    if big_disc:
        lines.append(f"Biggest Discount: Rs. {_pkr(big_disc)}")

    msg = "\n".join(lines)

    try:
        import pywhatkit
        pywhatkit.sendwhatmsg_instantly(
            phone_no=phone,
            message=msg,
            wait_time=12,
            tab_close=True,
            close_time=3,
        )
        return True, f"Daily digest sent to {phone}"
    except ImportError:
        pass
    except Exception:
        pass

    url = f"https://wa.me/{phone.lstrip('+')}?text={quote(msg)}"
    webbrowser.open(url)
    return False, f"Opened WhatsApp in browser for {phone}. Click Send."
