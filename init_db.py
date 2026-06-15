import sqlite3

connection = sqlite3.connect("pipeflow.db")

cursor = connection.cursor()

cursor.execute("DROP TABLE IF EXISTS outreach")
cursor.execute("DROP TABLE IF EXISTS contacts")
cursor.execute("DROP TABLE IF EXISTS accounts")

cursor.execute("""
CREATE TABLE accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_name TEXT NOT NULL,
    industry TEXT,
    country TEXT,
    city TEXT,
    website TEXT,
    pipeline_target REAL,
    notes TEXT,
    date_created TEXT DEFAULT CURRENT_TIMESTAMP,
    last_updated TEXT DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER,
    category TEXT,
    photo TEXT,
    name TEXT,
    job_title TEXT,
    org_dept TEXT,
    responsibilities TEXT,
    email TEXT,
    phone TEXT,
    location TEXT,
    linkedin TEXT,
    bmc_relationship TEXT,
    characteristics TEXT,
    background TEXT,
    personal_interests TEXT,
    personal_win TEXT,
    education TEXT,
    social_media TEXT,
    additional_notes TEXT,
    date_created TEXT DEFAULT CURRENT_TIMESTAMP,
    last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(account_id) REFERENCES accounts(id)
)
""")

cursor.execute("""
CREATE TABLE outreach (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fy TEXT,
    quarter TEXT,
    account_id INTEGER,
    contact_id INTEGER,
    activity_date TEXT,
    activity_time TEXT,
    activity_type TEXT,
    subject TEXT,
    notes TEXT,
    outcome TEXT,
    scheduled_meeting_date TEXT,
    scheduled_meeting_time TEXT,
    next_action TEXT,
    next_action_date TEXT,
    next_action_time TEXT,
    date_created TEXT DEFAULT CURRENT_TIMESTAMP,
    last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(account_id) REFERENCES accounts(id),
    FOREIGN KEY(contact_id) REFERENCES contacts(id)
)
""")

connection.commit()
connection.close()

print("PipeFlow database rebuilt with accounts, contacts and outreach tables")
