"""
import_opening_stock.py
=======================
United Mobile EPOS — Opening Stock Import
Option B: Dummy supplier (OPENING STOCK), no supplier balance impact.

What this script does:
  1. Clears all transaction tables (stock, purchases, sales, ledger, etc.)
  2. Keeps masters intact (brands, models, suppliers, customers, salesmen, settings)
  3. Creates a dummy supplier "OPENING STOCK" if not already present
  4. Creates a single PV (PV-0001) against that supplier for all stock
  5. Inserts all 234 IMEIs as stock_items with status = in_stock
  6. Does NOT touch supplier opening_balance — zero balance impact

Run from the ShopSoftware folder:
  python import_opening_stock.py

The script will ask for confirmation before making any changes.
A backup is created automatically before any writes.
"""

import sqlite3
import os
import shutil
from datetime import datetime

# ── CONFIG ────────────────────────────────────────────────────────────────────
DB_PATH = "united_mobile.db"          # adjust if needed
DUMMY_SUPPLIER_NAME = "OPENING STOCK"
PV_DATE = "25/05/2026"                # date on the stock report
# ─────────────────────────────────────────────────────────────────────────────

# ── STOCK DATA ────────────────────────────────────────────────────────────────
# Parsed from Current Stock & Valuation Statement 25/05/2026
# Format: (brand, model, imei, purchase_price)
# purchase_price = value / qty  (per-unit cost from the report)

STOCK = [
    # DIGIT
    ("DIGIT", "C2 2.0",    "351958690035294", 1907.00),
    ("DIGIT", "D1 2.4",    "354678680039836", 2325.00),
    # E TACHI
    ("E TACHI", "IPRO MAX", "357546931601711", 3600.00),
    ("E TACHI", "IPRO MAX", "357546931800792", 3600.00),
    # HMD
    ("HMD", "AURA2 4+2",   "359212530028461", 23250.00),
    # HONOR
    ("HONOR", "X5C+ 4+128", "861486083196906", 25461.00),
    ("HONOR", "X5C+ 4+128", "861486087098280", 25461.00),
    ("HONOR", "X8D 8+256",  "862380088217180", 66500.00),
    ("HONOR", "X8D 8+256",  "862380088070027", 66500.00),
    # INFINIX
    ("INFINIX", "HT60 PRO+",  "356131892969554", 60873.33),
    ("INFINIX", "HT60 PRO+",  "356131892623763", 60873.33),
    ("INFINIX", "HT60 PRO+",  "356131892586762", 60873.34),
    ("INFINIX", "I N EDGE",   "354909390149569", 72666.67),
    ("INFINIX", "I N EDGE",   "354909390149270", 72666.67),
    ("INFINIX", "I N EDGE",   "354909390107195", 72666.66),
    ("INFINIX", "NT60 8+256", "357230480080078", 80000.00),
    # ITEL
    ("ITEL", "2165PRO",       "356143780017149", 2305.00),
    ("ITEL", "A100C 2+64",    "354921657637285", 18530.00),
    ("ITEL", "A100C 2+64",    "354921651624677", 18530.00),
    ("ITEL", "A100C 2+64",    "354921651624685", 18530.00),
    ("ITEL", "A100C 2+64",    "354921651622309", 18530.00),
    ("ITEL", "A100C 2+64",    "354921651624974", 18530.00),
    ("ITEL", "A100C 4+128",   "355900610788814", 25945.00),
    ("ITEL", "A100C 4+128",   "355900610581490", 25945.00),
    ("ITEL", "A100C 4+128",   "355900610580559", 25945.00),
    ("ITEL", "A100C 4+64",    "354921651850470", 20385.00),
    ("ITEL", "A100C 4+64",    "354921651888033", 20385.00),
    ("ITEL", "A100C 4+64",    "354921651851668", 20385.00),
    ("ITEL", "A100C 4+64",    "354921651850660", 20385.00),
    ("ITEL", "A100C 4+64",    "354921651887670", 20385.00),
    ("ITEL", "CITY200 4+",    "354786341594840", 28000.00),
    ("ITEL", "FLIP1",         "350063002308520", 3780.00),
    ("ITEL", "IT2181",        "352448960215601", 2350.00),
    ("ITEL", "IT2181",        "352448961007239", 2350.00),
    ("ITEL", "IT2181",        "352448961006819", 2350.00),
    ("ITEL", "IT2181",        "352448960955651", 2350.00),
    ("ITEL", "IT2181",        "352448960992456", 2350.00),
    ("ITEL", "IT2181",        "352448960549892", 2350.00),
    ("ITEL", "IT2181",        "352448960955602", 2350.00),
    ("ITEL", "IT2181",        "352448960992308", 2350.00),
    ("ITEL", "IT2181",        "352448960978539", 2350.00),
    ("ITEL", "IT5032",        "352378650712361", 2800.00),
    ("ITEL", "IT5032",        "352378650815420", 2800.00),
    ("ITEL", "IT5032",        "352378650816022", 2800.00),
    ("ITEL", "IT5032",        "352378650815933", 2800.00),
    ("ITEL", "IT5032",        "352378650818929", 2800.00),
    ("ITEL", "IT5032",        "352378650815537", 2800.00),
    ("ITEL", "M450",          "351224840385174", 3280.00),
    ("ITEL", "M450",          "351224840389101", 3280.00),
    ("ITEL", "M450",          "351224840387964", 3280.00),
    ("ITEL", "M450",          "351224840378914", 3280.00),
    ("ITEL", "M450",          "351224840378849", 3280.00),
    ("ITEL", "M450",          "351224840387758", 3280.00),
    ("ITEL", "M450",          "351224840387188", 3280.00),
    ("ITEL", "M450",          "351224840258041", 3280.00),
    ("ITEL", "M450",          "351224840379086", 3280.00),
    ("ITEL", "M450",          "351224840379581", 3280.00),
    ("ITEL", "MAGIC4",        "351909960320544", 3200.00),
    ("ITEL", "MAGIC4",        "351909960318183", 3200.00),
    ("ITEL", "NEO RX60+",     "359555841174444", 4100.00),
    ("ITEL", "NEO X30+",      "355185431761147", 4300.00),
    ("ITEL", "P700",          "353495880221739", 3440.00),
    ("ITEL", "P700",          "353495882195675", 3440.00),
    # MI (Xiaomi)
    ("MI", "13 8+128",        "862410076847563", 36000.00),
    ("MI", "15 8+128",        "866566079791649", 43600.00),
    ("MI", "15C 6+128",       "860767082444103", 35000.00),
    ("MI", "15C 6+128",       "860767083159908", 35000.00),
    ("MI", "15C 6+128",       "860767083238025", 35000.00),
    ("MI", "A5 4+128MI",      "867857074044806", 29425.00),
    ("MI", "A5 4+128MI",      "867857074042909", 29425.00),
    ("MI", "A5 4+46",         "869460073313906", 26000.00),
    ("MI", "A5 4+46",         "869460073397040", 26000.00),
    ("MI", "A5 4+46",         "869460073391282", 26000.00),
    ("MI", "C75 8+256",       "869674075097206", 33000.00),
    ("MI", "C75 8+256",       "869674075201527", 33000.00),
    # NOKIA
    ("NOKIA", "105 CLASSI",   "357545610312723", 2879.00),
    ("NOKIA", "105 CLASSI",   "357545610331343", 2879.00),
    ("NOKIA", "N 110",        "352624554123118", 4799.00),
    ("NOKIA", "N 110",        "352624554123001", 4799.00),
    ("NOKIA", "N 110",        "352624554273061", 4799.00),
    ("NOKIA", "N 110",        "352624554344565", 4799.00),
    ("NOKIA", "N 110",        "352624554325416", 4799.00),
    ("NOKIA", "N 110",        "352624554307083", 4799.00),
    ("NOKIA", "N 110",        "352624554319906", 4799.00),
    ("NOKIA", "N106",         "350221240863595", 3969.33),
    ("NOKIA", "N106",         "350221240947653", 3969.33),
    ("NOKIA", "N106",         "350221241258878", 3969.33),
    ("NOKIA", "N106",         "350221241533007", 3969.33),
    ("NOKIA", "N106",         "350221241538915", 3969.33),
    ("NOKIA", "N106",         "350221241193703", 3969.33),
    ("NOKIA", "N106",         "350221241296472", 3969.33),
    ("NOKIA", "N106",         "350221241205200", 3969.33),
    ("NOKIA", "N106",         "350221241304318", 3969.33),
    ("NOKIA", "N106",         "350221241230869", 3969.33),
    ("NOKIA", "N106",         "350221241325529", 3969.33),
    ("NOKIA", "N106",         "350221241185949", 3969.33),
    ("NOKIA", "N106",         "350221241213808", 3969.33),
    ("NOKIA", "N106",         "350221241303864", 3969.33),
    ("NOKIA", "N106",         "350221241249117", 3969.33),
    ("NOKIA", "N106",         "350221241299989", 3969.33),
    ("NOKIA", "N106",         "350221241244019", 3969.33),
    ("NOKIA", "N106",         "350221241315413", 3969.33),
    ("NOKIA", "N106",         "350221241283991", 3969.33),
    ("NOKIA", "N106",         "350221241159050", 3969.33),
    ("NOKIA", "N106",         "350221241327962", 3969.37),  # rounding final unit
    # OPPO
    ("OPPO", "A6K 6+128",    "862571081057199", 49107.50),
    ("OPPO", "A6K 6+128",    "862571080199695", 49107.50),
    ("OPPO", "A6S 8+256",    "867348080066157", 68391.00),
    ("OPPO", "A6S PRO",      "865219080535537", 92351.00),
    ("OPPO", "A6X 4+64",     "867305082930111", 30500.00),
    ("OPPO", "R12F 5G",      "860556070551718", 57000.00),
    # PHILIPS
    ("PHILIPS", "FUN101",    "860757070176320", 3515.00),
    ("PHILIPS", "FUN101",    "860757070139740", 3515.00),
    # Q MOBILE
    ("Q MOBILE", "Q CLASSIC","355307930888656", 2340.00),
    ("Q MOBILE", "Q CLASSIC","355307930800552", 2340.00),
    ("Q MOBILE", "Q6303",    "357162180023480", 3150.00),
    ("Q MOBILE", "Q6303",    "357162180034420", 3150.00),
    ("Q MOBILE", "QPRIME",   "357619450122862", 2880.00),
    ("Q MOBILE", "QPRIME",   "357619450123605", 2880.00),
    # REALME
    ("REALME", "60X 4+64",   "866699079912137", 25650.00),
    ("REALME", "C71 8+128",  "860695074741535", 40740.00),
    ("REALME", "NT70 4+128R","866863083356133", 32570.00),
    # SAMSUNG
    ("SAMSUNG", "A06 4+128", "350719580778273", 25280.00),
    ("SAMSUNG", "A07 4+128", "350401996001463", 32000.00),
    ("SAMSUNG", "A07 4+128", "350401995649940", 32000.00),
    ("SAMSUNG", "A07 6+128", "356912764525693", 37500.00),
    ("SAMSUNG", "A17 8+256", "350343554950295", 59250.00),
    ("SAMSUNG", "A17 8+256", "350343556207314", 59250.00),
    ("SAMSUNG", "S A16 U",   "352345775509565", 35000.00),
    # SEGO
    ("SEGO", "SG NT70 4+6",  "359562360040105", 19420.00),
    ("SEGO", "SG NT70 4+6",  "359562360279406", 19420.00),
    # TABS
    ("TABS", "VISTA 3+64",   "350206280027789", 25000.00),
    ("TABS", "VISTA 4+128",  "359138670003065", 33000.00),
    ("TABS", "VISTA 4+128",  "359138670020366", 33000.00),
    # TECNO
    ("TECNO", "CAM50 8+",       "353816200292573", 75000.00),
    ("TECNO", "CAM50 PRO",      "355878970283842", 83587.00),
    ("TECNO", "CAM50 PRO",      "355878970048039", 83587.00),
    ("TECNO", "GO3 4+128",      "357786961801233", 30345.00),
    ("TECNO", "GO3 4+128",      "357786961801555", 30345.00),
    ("TECNO", "GO3 4+128",      "357786961802496", 30345.00),
    ("TECNO", "GO3 4+128",      "357786961424895", 30345.00),
    ("TECNO", "GO3 4+64",       "357786966718358", 25528.00),
    ("TECNO", "GO3 4+64",       "357786960968397", 25528.00),
    ("TECNO", "GO3 4+64",       "357786960980970", 25528.00),
    ("TECNO", "GO3 4+64",       "357786961269514", 25528.00),
    ("TECNO", "SP40 PRO+",      "352530120673173", 58958.50),
    ("TECNO", "SP40 PRO+",      "352530120603105", 58958.50),
    ("TECNO", "SP50 6+128",     "350986940223718", 44000.00),
    ("TECNO", "SP50 6+128",     "350986940436583", 44000.00),
    # USED
    ("USED", "I HT50I U",       "359880720236241", 27000.00),
    ("USED", "I NT40 PRO",      "350790291351007", 50000.00),
    ("USED", "MI 10 8+128",     "860211041822711", 89000.00),
    ("USED", "O A17",           "868127062737491", 8000.00),
    ("USED", "O A5 PRO",        "866176071256912", 39000.00),
    ("USED", "O A5 U",          "868671076995215", 25250.00),
    ("USED", "O A5 U",          "868671079340310", 25250.00),
    ("USED", "R 13 U",          "862410077772042", 25000.00),
    ("USED", "R 13C",           "861798078271688", 21500.00),
    ("USED", "R 14C",           "863955072924948", 25000.00),
    ("USED", "R C65 8+256",     "866999070295031", 32000.00),
    ("USED", "R NT14 PRO",      "863763072282329", 57250.00),
    ("USED", "R NT14 PRO",      "863763071434749", 57250.00),
    ("USED", "R NT50",          "867008072398956", 15500.00),
    ("USED", "RL C85",          "867501080085474", 42500.00),
    ("USED", "S A07",           "351738744971599", 21000.00),
    ("USED", "S A12 4+64",      "359184980242340", 11000.00),
    ("USED", "S A17",           "350343554051607", 46000.00),
    ("USED", "S A25",           "353204669168057", 42000.00),
    ("USED", "T 40PRO+",        "352530120564141", 47000.00),
    ("USED", "T CAM30",         "357450681004764", 42000.00),
    ("USED", "T CAM40",         "353317841853071", 56000.00),
    ("USED", "T SP GO",         "354262302815046", 18000.00),
    ("USED", "T SP10 PRO U",    "111111111643421", 23000.00),
    ("USED", "T SP40",          "358459361904911", 27250.00),
    ("USED", "T SP40",          "358459360222133", 27250.00),
    ("USED", "V 23E",           "864083059114372", 27000.00),
    ("USED", "V V50LITE",       "860560079269371", 66000.00),
    ("USED", "V V60 LITE",      "863608087460511", 75000.00),
    ("USED", "V Y04",           "860814071834017", 24666.67),
    ("USED", "V Y04",           "868385074686573", 24666.67),
    ("USED", "V Y04",           "861780089697333", 24666.66),
    ("USED", "V Y17S",          "861439067149755", 21500.00),
    ("USED", "V Y17S",          "867038066825458", 21500.00),
    ("USED", "V Y200 U",        "863316079156994", 43200.00),
    ("USED", "V Y29 U",         "860331076823655", 41500.00),
    ("USED", "V Y29 U",         "860331077240776", 41500.00),
    ("USED", "V Y36",           "869703069511094", 33000.00),
    ("USED", "V Y400",          "869908076987613", 55000.00),
    ("USED", "V40 U",           "866897074118334", 51000.00),
    ("USED", "Y27 6+128U",      "861118069039491", 33000.00),
    # VILLAON
    ("VILLAON", "V200S",        "352134842125644", 1875.00),
    ("VILLAON", "V200S",        "352134842135585", 1875.00),
    ("VILLAON", "V200S",        "352134842135767", 1875.00),
    ("VILLAON", "V200S",        "352134842152713", 1875.00),
    ("VILLAON", "V200S",        "352134842138589", 1875.00),
    ("VILLAON", "V200S",        "352134842123680", 1875.00),
    ("VILLAON", "V200S",        "352134842125560", 1875.00),
    ("VILLAON", "V200S",        "352134842130099", 1875.00),
    ("VILLAON", "V200S",        "352134842135551", 1875.00),
    # VIVO
    ("VIVO", "V70FE 8+256",     "860812084736575", 119000.00),
    ("VIVO", "Y05 4+128",       "869479086814098", 38971.43),
    ("VIVO", "Y05 4+128",       "869479086806912", 38971.43),
    ("VIVO", "Y05 4+128",       "869479086805914", 38971.43),
    ("VIVO", "Y05 4+128",       "869479086806813", 38971.43),
    ("VIVO", "Y05 4+128",       "869479087143695", 38971.43),
    ("VIVO", "Y05 4+128",       "869479086808199", 38971.43),
    ("VIVO", "Y05 4+128",       "869479086806953", 38971.42),
    ("VIVO", "Y05 4+64",        "861257086333139", 35545.45),
    ("VIVO", "Y05 4+64",        "861257086329475", 35545.45),
    ("VIVO", "Y05 4+64",        "861257086315110", 35545.45),
    ("VIVO", "Y05 4+64",        "861257086377672", 35545.45),
    ("VIVO", "Y05 4+64",        "861257086376757", 35545.45),
    ("VIVO", "Y05 4+64",        "861257086707951", 35545.45),
    ("VIVO", "Y05 4+64",        "861257086223256", 35545.45),
    ("VIVO", "Y05 4+64",        "861257086219254", 35545.45),
    ("VIVO", "Y05 4+64",        "861257086223777", 35545.45),
    ("VIVO", "Y05 4+64",        "861257086225079", 35545.45),
    ("VIVO", "Y05 4+64",        "861257086222514", 35545.55),  # rounding
    ("VIVO", "Y31D 6+128",      "866702089446540", 58000.00),
    ("VIVO", "Y31D 8+128",      "861640089577333", 63300.00),
    ("VIVO", "Y31D 8+256",      "866814089599853", 63000.00),
    # VOICE
    ("VOICE", "FLEXI V",        "357997620032322", 1950.00),
    ("VOICE", "FLEXI V",        "357997620034286", 1950.00),
    ("VOICE", "FLEXI V",        "357997620034724", 1950.00),
    ("VOICE", "FLEXI V",        "357997620037388", 1950.00),
    ("VOICE", "FLEXI V",        "357997620070686", 1950.00),
    ("VOICE", "FLEXI V",        "357997620071783", 1950.00),
    ("VOICE", "FLEXI V",        "357997620071809", 1950.00),
    ("VOICE", "FLEXI V",        "357997620072005", 1950.00),
    ("VOICE", "FLEXI V",        "357997620072047", 1950.00),
    # ZTE
    ("ZTE", "A35E 2+64",        "863787087570550", 17400.00),
    ("ZTE", "A35E 2+64",        "863787087571632", 17400.00),
    ("ZTE", "A36 4+64",         "869727083659639", 20300.00),
    ("ZTE", "V60D 8+256",       "862213076879127", 29000.00),
]

EXPECTED_COUNT = 234
EXPECTED_VALUE = 5728020.50


def backup_db(db_path):
    ts = datetime.now().strftime("%d%m%Y_%H%M%S")
    backup_path = f"united_mobile_pre_import_{ts}.db"
    shutil.copy2(db_path, backup_path)
    print(f"  ✓ Backup created: {backup_path}")
    return backup_path


def clear_transactions(cur):
    """Delete all transaction data but keep masters."""
    tables = [
        "sale_return_lines", "sale_returns",
        "purchase_return_lines", "purchase_returns",
        "sale_lines", "sale_vouchers",
        "purchase_lines", "purchase_vouchers",
        "stock_items",
        "payments",
        "journal_entries",
        "sessions",
    ]
    for t in tables:
        cur.execute(f"DELETE FROM {t}")
        print(f"  Cleared: {t}")

    # Reset voucher sequences in settings
    seq_keys = [
        "last_pv_number", "last_sv_number",
        "last_cp_number", "last_cr_number",
        "last_jv_number", "last_pr_number", "last_sr_number",
    ]
    for k in seq_keys:
        cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, "0"))
    print("  Reset voucher sequences to 0")


def get_or_create_brand(cur, brand_name):
    brand_upper = brand_name.upper()
    cur.execute("SELECT id FROM brands WHERE name = ?", (brand_upper,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("INSERT INTO brands (name) VALUES (?)", (brand_upper,))
    return cur.lastrowid


def get_or_create_model(cur, brand_id, model_name):
    model_upper = model_name.upper()
    cur.execute("SELECT id FROM models WHERE brand_id = ? AND name = ?", (brand_id, model_upper))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        "INSERT INTO models (brand_id, name, reference_price) VALUES (?, ?, ?)",
        (brand_id, model_upper, None)
    )
    return cur.lastrowid


def get_or_create_dummy_supplier(cur):
    cur.execute("SELECT id FROM suppliers WHERE name = ?", (DUMMY_SUPPLIER_NAME,))
    row = cur.fetchone()
    if row:
        print(f"  Found existing dummy supplier: {DUMMY_SUPPLIER_NAME} (id={row[0]})")
        return row[0]
    cur.execute(
        "INSERT INTO suppliers (name, contact, opening_balance) VALUES (?, ?, ?)",
        (DUMMY_SUPPLIER_NAME, None, 0)
    )
    sid = cur.lastrowid
    print(f"  Created dummy supplier: {DUMMY_SUPPLIER_NAME} (id={sid})")
    return sid


def run_import():
    print("\n" + "=" * 60)
    print("  United Mobile — Opening Stock Import (Option B)")
    print("=" * 60)

    # Validate data
    if len(STOCK) != EXPECTED_COUNT:
        print(f"\n⚠  WARNING: STOCK list has {len(STOCK)} items, expected {EXPECTED_COUNT}")

    actual_value = sum(p for _, _, _, p in STOCK)
    diff = abs(actual_value - EXPECTED_VALUE)
    if diff > 1.0:
        print(f"\n⚠  WARNING: Total value {actual_value:,.2f} differs from expected "
              f"{EXPECTED_VALUE:,.2f} by {diff:.2f} (rounding differences are OK if < 10)")

    print(f"\n  Items to import : {len(STOCK)}")
    print(f"  Total value     : Rs. {actual_value:,.2f}")
    print(f"  Report value    : Rs. {EXPECTED_VALUE:,.2f}")
    print(f"  Difference      : Rs. {diff:.2f}")
    print(f"  Database        : {os.path.abspath(DB_PATH)}")

    print("\n  This will:")
    print("  • DELETE all purchases, sales, ledger, stock data")
    print("  • KEEP brands, models, suppliers, customers, salesmen, settings")
    print("  • CREATE dummy supplier 'OPENING STOCK' (no balance impact)")
    print("  • INSERT all 234 IMEIs as opening stock")
    print("  • RESET all voucher sequences to 0001")

    ans = input("\n  Type YES to continue, anything else to abort: ").strip()
    if ans != "YES":
        print("  Aborted. No changes made.")
        return

    if not os.path.exists(DB_PATH):
        print(f"\n  ERROR: Database not found at {DB_PATH}")
        return

    print("\n  Creating backup...")
    backup_db(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = OFF")  # safe to disable during bulk import
    cur = conn.cursor()

    try:
        print("\n  Clearing transaction tables...")
        clear_transactions(cur)

        print("\n  Setting up dummy supplier...")
        supplier_id = get_or_create_dummy_supplier(cur)

        # Create PV-0001 for all stock
        pv_total = sum(p for _, _, _, p in STOCK)
        cur.execute(
            """INSERT INTO purchase_vouchers
               (pv_number, supplier_id, date, total_amount, notes)
               VALUES (?, ?, ?, ?, ?)""",
            ("PV-0001", supplier_id, PV_DATE, pv_total,
             "Opening stock import — 25/05/2026")
        )
        pv_id = cur.lastrowid
        cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('last_pv_number', '1')")
        print(f"  Created PV-0001 (id={pv_id}), total Rs. {pv_total:,.2f}")

        print("\n  Importing stock items...")
        ok = 0
        skipped = []

        for brand_name, model_name, imei, price in STOCK:
            # Validate IMEI length
            if len(imei) != 15 or not imei.isdigit():
                skipped.append((imei, "invalid IMEI"))
                continue

            brand_id = get_or_create_brand(cur, brand_name)
            model_id = get_or_create_model(cur, brand_id, model_name)

            # Insert purchase line
            cur.execute(
                """INSERT INTO purchase_lines (pv_id, model_id, imei, purchase_price)
                   VALUES (?, ?, ?, ?)""",
                (pv_id, model_id, imei, price)
            )
            pl_id = cur.lastrowid

            # Insert stock item
            cur.execute(
                """INSERT INTO stock_items
                   (model_id, imei, purchase_line_id, purchase_price, status)
                   VALUES (?, ?, ?, ?, 'in_stock')""",
                (model_id, imei, pl_id, price)
            )
            ok += 1

        conn.commit()

        print(f"\n{'=' * 60}")
        print(f"  ✓ Import complete!")
        print(f"  ✓ Items imported : {ok}")
        if skipped:
            print(f"  ⚠ Skipped        : {len(skipped)}")
            for imei, reason in skipped:
                print(f"    - {imei}: {reason}")
        print(f"  ✓ Supplier balance: Rs. 0.00 (no impact — Option B)")
        print(f"{'=' * 60}\n")

    except Exception as e:
        conn.rollback()
        print(f"\n  ERROR: {e}")
        print("  All changes rolled back. Database unchanged.")
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.close()


if __name__ == "__main__":
    run_import()
