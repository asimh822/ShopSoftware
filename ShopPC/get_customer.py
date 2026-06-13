import sqlite3
conn = sqlite3.connect("united_mobile.db")
c = conn.cursor()
# Get cash customers who have a contact number stored
c.execute("SELECT cash_customer_contact, cash_customer_name FROM sale_vouchers WHERE type='cash' AND cash_customer_contact IS NOT NULL AND cash_customer_contact != '' LIMIT 3")
for r in c.fetchall():
    print(r)
conn.close()
