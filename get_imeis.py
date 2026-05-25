import sqlite3
conn = sqlite3.connect("united_mobile.db")
c = conn.cursor()
c.execute("SELECT s.imei, m.name, b.name FROM stock_items s JOIN models m ON s.model_id=m.id JOIN brands b ON m.brand_id=b.id WHERE s.status='in_stock' LIMIT 5")
for r in c.fetchall():
    print(r)
conn.close()
