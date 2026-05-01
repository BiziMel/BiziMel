from db_compat import get_connection, using_postgres

DB_NAME = "pipeflow.db"


def get_database_path():
    from db_compat import sqlite_database_path
    return sqlite_database_path()


def get_db_connection():
    return get_connection()


def add_column_if_missing(cursor, table_name, column_name, column_definition):
    if using_postgres():
        rows = cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = %s
            """,
            (table_name,),
        ).fetchall()
        existing_columns = [row["column_name"] for row in rows]
        if column_name not in existing_columns:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")
        return

    cursor.execute(f"PRAGMA table_info({table_name})")
    existing_columns = [column[1] for column in cursor.fetchall()]

    if column_name not in existing_columns:
        cursor.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
        )


def initialise_database():
    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_name TEXT NOT NULL,
            account_tier TEXT,
            industry TEXT,
            business_unit TEXT,
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
        CREATE TABLE IF NOT EXISTS contacts (
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
        CREATE TABLE IF NOT EXISTS outreach (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fy TEXT,
            quarter TEXT,
            account_id INTEGER,
            contact_id INTEGER,
            campaign TEXT,
            sales_play TEXT,
            activity_date TEXT,
            activity_time TEXT,
            activity_type TEXT,
            subject TEXT,
            notes TEXT,
            outcome TEXT,
            next_action TEXT,
            next_action_date TEXT,
            next_action_time TEXT,
            task_status TEXT DEFAULT 'Not Started',
            assigned_to TEXT,
            date_created TEXT DEFAULT CURRENT_TIMESTAMP,
            last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(account_id) REFERENCES accounts(id),
            FOREIGN KEY(contact_id) REFERENCES contacts(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS account_partners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            partner_id INTEGER,
            partner_name TEXT NOT NULL,
            partner_role TEXT,
            involvement_status TEXT,
            relationship_owner TEXT,
            next_action TEXT,
            notes TEXT,
            date_created TEXT DEFAULT CURRENT_TIMESTAMP,
            last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(account_id) REFERENCES accounts(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS partners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            partner_name TEXT NOT NULL UNIQUE,
            partner_type TEXT,
            website TEXT,
            country TEXT,
            city TEXT,
            relationship_owner TEXT,
            notes TEXT,
            date_created TEXT DEFAULT CURRENT_TIMESTAMP,
            last_updated TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS partner_contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            partner_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            job_title TEXT,
            partner_contact_role TEXT,
            coverage_area TEXT,
            relationship_owner TEXT,
            email TEXT,
            phone TEXT,
            location TEXT,
            linkedin TEXT,
            relationship_status TEXT,
            next_action TEXT,
            notes TEXT,
            date_created TEXT DEFAULT CURRENT_TIMESTAMP,
            last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(partner_id) REFERENCES partners(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS account_custom_values (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            field_key TEXT NOT NULL,
            field_value TEXT,
            date_created TEXT DEFAULT CURRENT_TIMESTAMP,
            last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(account_id) REFERENCES accounts(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS timeline_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            related_type TEXT NOT NULL,
            related_id INTEGER NOT NULL,
            entry_type TEXT,
            entry_text TEXT,
            created_by TEXT,
            date_created TEXT DEFAULT CURRENT_TIMESTAMP,
            last_updated TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_profile (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT,
            team TEXT,
            job_title TEXT,
            date_created TEXT DEFAULT CURRENT_TIMESTAMP,
            last_updated TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Safe migrations for account custom values
    add_column_if_missing(cursor, "account_custom_values", "account_id", "INTEGER")
    add_column_if_missing(cursor, "account_custom_values", "field_key", "TEXT")
    add_column_if_missing(cursor, "account_custom_values", "field_value", "TEXT")
    add_column_if_missing(cursor, "account_custom_values", "date_created", "TEXT DEFAULT CURRENT_TIMESTAMP")
    add_column_if_missing(cursor, "account_custom_values", "last_updated", "TEXT DEFAULT CURRENT_TIMESTAMP")

    # Safe migrations for accounts
    add_column_if_missing(cursor, "accounts", "business_unit", "TEXT")
    add_column_if_missing(cursor, "accounts", "account_tier", "TEXT")

    # Safe migrations for outreach
    add_column_if_missing(cursor, "outreach", "fy", "TEXT")
    add_column_if_missing(cursor, "outreach", "quarter", "TEXT")
    add_column_if_missing(cursor, "outreach", "campaign", "TEXT")
    add_column_if_missing(cursor, "outreach", "sales_play", "TEXT")
    add_column_if_missing(cursor, "outreach", "activity_time", "TEXT")
    add_column_if_missing(cursor, "outreach", "next_action_time", "TEXT")
    add_column_if_missing(cursor, "outreach", "task_status", "TEXT DEFAULT 'Not Started'")
    add_column_if_missing(cursor, "outreach", "assigned_to", "TEXT")

    # Safe migrations for account partners
    add_column_if_missing(cursor, "account_partners", "partner_id", "INTEGER")
    add_column_if_missing(cursor, "account_partners", "account_id", "INTEGER")
    add_column_if_missing(cursor, "account_partners", "partner_name", "TEXT")
    add_column_if_missing(cursor, "account_partners", "partner_role", "TEXT")
    add_column_if_missing(cursor, "account_partners", "involvement_status", "TEXT")
    add_column_if_missing(cursor, "account_partners", "relationship_owner", "TEXT")
    add_column_if_missing(cursor, "account_partners", "next_action", "TEXT")
    add_column_if_missing(cursor, "account_partners", "notes", "TEXT")
    add_column_if_missing(cursor, "account_partners", "date_created", "TEXT DEFAULT CURRENT_TIMESTAMP")
    add_column_if_missing(cursor, "account_partners", "last_updated", "TEXT DEFAULT CURRENT_TIMESTAMP")

    # Safe migrations for partner organisations
    add_column_if_missing(cursor, "partners", "partner_name", "TEXT")
    add_column_if_missing(cursor, "partners", "partner_type", "TEXT")
    add_column_if_missing(cursor, "partners", "website", "TEXT")
    add_column_if_missing(cursor, "partners", "country", "TEXT")
    add_column_if_missing(cursor, "partners", "city", "TEXT")
    add_column_if_missing(cursor, "partners", "relationship_owner", "TEXT")
    add_column_if_missing(cursor, "partners", "notes", "TEXT")
    add_column_if_missing(cursor, "partners", "date_created", "TEXT DEFAULT CURRENT_TIMESTAMP")
    add_column_if_missing(cursor, "partners", "last_updated", "TEXT DEFAULT CURRENT_TIMESTAMP")

    # Safe migrations for partner contacts
    add_column_if_missing(cursor, "partner_contacts", "partner_id", "INTEGER")
    add_column_if_missing(cursor, "partner_contacts", "name", "TEXT")
    add_column_if_missing(cursor, "partner_contacts", "job_title", "TEXT")
    add_column_if_missing(cursor, "partner_contacts", "partner_contact_role", "TEXT")
    add_column_if_missing(cursor, "partner_contacts", "coverage_area", "TEXT")
    add_column_if_missing(cursor, "partner_contacts", "relationship_owner", "TEXT")
    add_column_if_missing(cursor, "partner_contacts", "email", "TEXT")
    add_column_if_missing(cursor, "partner_contacts", "phone", "TEXT")
    add_column_if_missing(cursor, "partner_contacts", "location", "TEXT")
    add_column_if_missing(cursor, "partner_contacts", "linkedin", "TEXT")
    add_column_if_missing(cursor, "partner_contacts", "relationship_status", "TEXT")
    add_column_if_missing(cursor, "partner_contacts", "next_action", "TEXT")
    add_column_if_missing(cursor, "partner_contacts", "notes", "TEXT")
    add_column_if_missing(cursor, "partner_contacts", "date_created", "TEXT DEFAULT CURRENT_TIMESTAMP")
    add_column_if_missing(cursor, "partner_contacts", "last_updated", "TEXT DEFAULT CURRENT_TIMESTAMP")

    cursor.execute("""
        INSERT OR IGNORE INTO partners (partner_name)
        SELECT DISTINCT TRIM(partner_name)
        FROM account_partners
        WHERE partner_name IS NOT NULL
          AND TRIM(partner_name) != ''
    """)

    cursor.execute("""
        UPDATE account_partners
        SET partner_id = (
            SELECT partners.id
            FROM partners
            WHERE partners.partner_name = account_partners.partner_name
        )
        WHERE partner_id IS NULL
          AND partner_name IS NOT NULL
          AND TRIM(partner_name) != ''
    """)

    # Safe migrations for timeline
    add_column_if_missing(cursor, "timeline_entries", "related_type", "TEXT")
    add_column_if_missing(cursor, "timeline_entries", "related_id", "INTEGER")
    add_column_if_missing(cursor, "timeline_entries", "entry_type", "TEXT")
    add_column_if_missing(cursor, "timeline_entries", "entry_text", "TEXT")
    add_column_if_missing(cursor, "timeline_entries", "created_by", "TEXT")
    add_column_if_missing(cursor, "timeline_entries", "date_created", "TEXT DEFAULT CURRENT_TIMESTAMP")
    add_column_if_missing(cursor, "timeline_entries", "last_updated", "TEXT DEFAULT CURRENT_TIMESTAMP")

    # Safe migrations for user profile
    add_column_if_missing(cursor, "user_profile", "full_name", "TEXT")
    add_column_if_missing(cursor, "user_profile", "team", "TEXT")
    add_column_if_missing(cursor, "user_profile", "job_title", "TEXT")
    add_column_if_missing(cursor, "user_profile", "date_created", "TEXT DEFAULT CURRENT_TIMESTAMP")
    add_column_if_missing(cursor, "user_profile", "last_updated", "TEXT DEFAULT CURRENT_TIMESTAMP")

    cursor.execute("""
        INSERT INTO user_profile (
            id,
            full_name,
            team,
            job_title
        )
        SELECT
            1,
            '',
            '',
            ''
        WHERE NOT EXISTS (
            SELECT 1 FROM user_profile WHERE id = 1
        )
    """)

    connection.commit()
    connection.close()
