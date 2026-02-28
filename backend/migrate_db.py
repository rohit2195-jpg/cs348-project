"""
migrate_db.py — One-time migration to add alpaca_order_id to order_history.
Run this once from the same directory as your my_database.db file:
    python migrate_db.py
"""

import sqlite3
import os

DB_PATH = "my_database.db"

if not os.path.exists(DB_PATH):
    print(f"❌ Database not found at '{DB_PATH}'. Make sure you run this from the same folder as your DB.")
    exit(1)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Check if the column already exists
cursor.execute("PRAGMA table_info(order_history)")
columns = [row[1] for row in cursor.fetchall()]

if "alpaca_order_id" in columns:
    print("✅ Column 'alpaca_order_id' already exists. Nothing to do.")
else:
    print("➕ Adding 'alpaca_order_id' column to order_history...")
    cursor.execute("ALTER TABLE order_history ADD COLUMN alpaca_order_id VARCHAR(64)")
    conn.commit()
    print("✅ Migration complete. Column added successfully.")

# Show current pending orders so you can verify state
cursor.execute("SELECT id, symbol, quantity, trade_type, status, alpaca_order_id FROM order_history WHERE status = 'pending'")
rows = cursor.fetchall()

if rows:
    print(f"\n⚠️  Found {len(rows)} pending order(s) with no alpaca_order_id:")
    print(f"  {'ID':<6} {'Symbol':<8} {'Qty':<6} {'Type':<6} {'Status':<10} {'Alpaca ID'}")
    print("  " + "-" * 60)
    for row in rows:
        print(f"  {row[0]:<6} {row[1]:<8} {row[2]:<6} {row[3]:<6} {row[4]:<10} {row[5] or '(none)'}")
    print("\n💡 These orders have no Alpaca ID stored, so the background settler can't sync them.")
    print("   You may need to manually check Alpaca's dashboard and cancel or re-submit them.")
else:
    print("\n✅ No pending orders found. Your DB is clean.")

conn.close()