#!/usr/bin/env python3
"""One-time script to sync meal totals from meals table to daily_summary."""

import sqlite3
from pathlib import Path

# Find the database
db_path = Path(__file__).parent.parent / "data" / "analytics.db"

if not db_path.exists():
    print(f"Database not found at {db_path}")
    exit(1)

print(f"Connecting to {db_path}")
conn = sqlite3.connect(db_path)

# Check for duplicates first
print("\nChecking for duplicate entries...")
cursor = conn.execute("""
    SELECT entry_date, COUNT(*) as cnt 
    FROM daily_summary 
    GROUP BY entry_date 
    HAVING cnt > 1
    ORDER BY cnt DESC
    LIMIT 10
""")
duplicates = cursor.fetchall()

if duplicates:
    print(f"Found {len(duplicates)} dates with duplicates!")
    for row in duplicates:
        print(f"  {row[0]}: {row[1]} copies")
    
    print("\nRemoving duplicates (keeping one per date)...")
    # Delete duplicates by keeping only the row with the earliest rowid
    conn.execute("""
        DELETE FROM daily_summary 
        WHERE rowid NOT IN (
            SELECT MIN(rowid) 
            FROM daily_summary 
            GROUP BY entry_date
        )
    """)
    conn.commit()
    print("Duplicates removed.")

# Now run the update
print("\nSyncing meal totals to daily_summary...")
conn.execute("""
    UPDATE daily_summary
    SET 
        meal_count = (SELECT COUNT(*) FROM meals WHERE meals.entry_date = daily_summary.entry_date),
        total_calories = (SELECT COALESCE(SUM(calories), 0) FROM meals WHERE meals.entry_date = daily_summary.entry_date),
        total_protein_g = (SELECT COALESCE(SUM(protein_g), 0) FROM meals WHERE meals.entry_date = daily_summary.entry_date),
        total_carbs_g = (SELECT COALESCE(SUM(carbs_g), 0) FROM meals WHERE meals.entry_date = daily_summary.entry_date),
        total_fat_g = (SELECT COALESCE(SUM(fat_g), 0) FROM meals WHERE meals.entry_date = daily_summary.entry_date),
        total_fiber_g = (SELECT COALESCE(SUM(fiber_g), 0) FROM meals WHERE meals.entry_date = daily_summary.entry_date),
        updated_at = datetime('now')
""")
conn.commit()

# Show results
print("\nUpdated! Here are the last 10 days:")
cursor = conn.execute("""
    SELECT entry_date, meal_count, total_calories 
    FROM daily_summary 
    ORDER BY entry_date DESC 
    LIMIT 10
""")
for row in cursor:
    print(f"  {row[0]}: {row[1]} meals, {row[2]:.0f} calories")

conn.close()
print("\nDone!")
