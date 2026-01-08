#!/usr/bin/env python3
"""Re-sync Strava activities to capture calories from detailed API."""

import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from daily_diary.clients.strava import StravaClient
from daily_diary.services.database import AnalyticsDB

db_path = Path(__file__).parent.parent / "data" / "analytics.db"

if not db_path.exists():
    print(f"Database not found at {db_path}")
    exit(1)

print("Fetching recent Strava activities (with detailed data for calories)...")
print("This may take a moment as we fetch details for each activity...\n")

client = StravaClient()
if not client.is_configured:
    print("Strava not configured. Check your .env file.")
    exit(1)

# Fetch last 30 days of activities with details
activities = client.get_recent_activities(days=30, fetch_details=True)
print(f"\nFound {len(activities)} activities from Strava")

# Show what we got
print("\nActivity summary:")
for a in activities:
    cal_str = f"{a.calories_burned:.0f} cal" if a.calories_burned else "no calories"
    print(f"  {a.start_time.date() if a.start_time else '?'}: {a.name[:40]} - {cal_str}")

if not activities:
    print("No activities found.")
    exit(0)

# Update database
print("\nUpdating database...")
with AnalyticsDB() as db:
    updated = 0
    for activity in activities:
        if activity.calories_burned and activity.activity_id:
            # Update existing activity with calories
            result = db.conn.execute("""
                UPDATE activities 
                SET calories_burned = ?
                WHERE external_id = ? AND source = 'strava'
            """, [activity.calories_burned, activity.activity_id])
            if result.rowcount > 0:
                updated += 1
    
    db.conn.commit()
    print(f"\nUpdated {updated} activities with calorie data.")

# Show current state
print("\nCurrent activities with calories in database:")
conn = sqlite3.connect(db_path)
cursor = conn.execute("""
    SELECT entry_date, name, duration_minutes, calories_burned, source
    FROM activities
    WHERE calories_burned IS NOT NULL AND calories_burned > 0
    ORDER BY entry_date DESC
    LIMIT 15
""")
for row in cursor:
    print(f"  {row[0]}: {row[1][:40]} - {row[2]:.0f}min - {row[3]:.0f} cal ({row[4]})")

conn.close()
print("\nDone!")
