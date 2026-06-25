# fix_reference_prices.py
# For United Mobile EPOS
# Place next to united_mobile.db and run: python fix_reference_prices.py

import sqlite3
import sys
import os


def fix_reference_prices(db_path):
    if not os.path.exists(db_path):
        print("ERROR: Database not found at: " + db_path)
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT m.id, m.name, b.name AS brand_name, m.reference_price
        FROM models m
        JOIN brands b ON b.id = m.brand_id
        WHERE m.reference_price IS NULL OR m.reference_price = 0
        ORDER BY b.name, m.name
    """)
    models_to_fix = cur.fetchall()

    if not models_to_fix:
        print("No models found with 0 or NULL reference_price. Nothing to do.")
        conn.close()
        return

    print("Found " + str(len(models_to_fix)) + " model(s) with 0 or NULL reference_price:\n")
    print("{:<20} {:<25} {:>15} {:>20} {:>10}".format(
        "Brand", "Model", "Old Ref Price", "Avg Purchase Price", "Action"))
    print("-" * 95)

    updated = []
    skipped = []

    for row in models_to_fix:
        model_id   = row["id"]
        model_name = row["name"]
        brand_name = row["brand_name"]
        old_price  = row["reference_price"]

        cur.execute("""
            SELECT AVG(purchase_price) AS avg_price, COUNT(*) AS item_count
            FROM stock_items
            WHERE model_id = ?
        """, (model_id,))
        result = cur.fetchone()
        avg_price  = result["avg_price"]
        item_count = result["item_count"]

        if avg_price is None or item_count == 0:
            print("{:<20} {:<25} {:>15} {:>20} {:>10}".format(
                brand_name, model_name, str(old_price), "No stock - SKIP", "SKIP"))
            skipped.append((brand_name, model_name))
        else:
            new_price = round(avg_price)
            print("{:<20} {:<25} {:>15} {:>20,} {:>10}".format(
                brand_name, model_name, str(old_price), new_price, "UPDATE"))
            updated.append((model_id, brand_name, model_name, new_price))

    if not updated:
        print("\nNo models could be updated (no stock items found for any).")
        conn.close()
        return

    print("\n" + str(len(updated)) + " model(s) will be updated. " + str(len(skipped)) + " skipped.")
    confirm = input("\nProceed with update? (yes/no): ").strip().lower()
    if confirm not in ("yes", "y"):
        print("Cancelled. No changes made.")
        conn.close()
        return

    for model_id, brand_name, model_name, new_price in updated:
        cur.execute(
            "UPDATE models SET reference_price = ? WHERE id = ?",
            (new_price, model_id)
        )

    conn.commit()
    print("\nDone. " + str(len(updated)) + " model(s) updated successfully.")

    if skipped:
        print("\nSkipped (no stock items - set manually in Masters):")
        for brand, model in skipped:
            print("  " + brand + " / " + model)

    conn.close()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(script_dir, "united_mobile.db")

    fix_reference_prices(db_path)
