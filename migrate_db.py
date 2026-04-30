import sqlite3
from database import get_database_path

connection = sqlite3.connect(get_database_path())
cursor = connection.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS timeline_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    related_type TEXT NOT NULL,
    related_id INTEGER NOT NULL,
    entry_type TEXT,
    entry_text TEXT NOT NULL,
    created_by TEXT,
    date_created TEXT DEFAULT CURRENT_TIMESTAMP
)
""")

connection.commit()
connection.close()

print("Migration complete: timeline_entries table ready.")
