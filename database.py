from db_compat import get_connection, using_postgres, current_user_schema, sqlite_database_path

_INITIALISED_DATABASES = set()

DB_NAME = "pipeflow.db"


def get_database_path():
    return sqlite_database_path()


def database_initialisation_key():
    if using_postgres():
        return f"postgres:{current_user_schema()}"
    return f"sqlite:{sqlite_database_path()}"


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


def create_index_if_missing(cursor, index_name, table_name, columns):
    column_sql = ", ".join(columns)
    cursor.execute(
        f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({column_sql})"
    )


def initialise_database(force=False):
    cache_key = database_initialisation_key()
    if not force and cache_key in _INITIALISED_DATABASES:
        return

    connection = get_db_connection()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_name TEXT NOT NULL,
            pg_bible_order INTEGER,
            account_tier TEXT,
            industry TEXT,
            business_unit TEXT,
            country TEXT,
            city TEXT,
            website TEXT,
            pipeline_target REAL,
            current_pipeline REAL,
            nbm_target TEXT,
            sales_play TEXT,
            owner_user_id INTEGER,
            owner_name TEXT,
            owner_email TEXT,
            notes TEXT,
            date_created TEXT DEFAULT CURRENT_TIMESTAMP,
            last_updated TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS account_shared_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            full_name TEXT,
            email TEXT,
            workspace_schema TEXT,
            date_created TEXT DEFAULT CURRENT_TIMESTAMP,
            last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(account_id, user_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dashboard_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT,
            last_updated TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pg_action_updates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL UNIQUE,
            completed_discovery_meeting TEXT,
            next_action_override TEXT,
            date_created TEXT DEFAULT CURRENT_TIMESTAMP,
            last_updated TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pg_action_contact_updates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            contact_id INTEGER NOT NULL UNIQUE,
            completed_discovery_meeting TEXT,
            next_action_override TEXT,
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
            campaign_start_date TEXT,
            campaign_end_date TEXT,
            campaign_tasks_per_week INTEGER,
            campaign_total_tasks INTEGER,
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
            partner_manager TEXT,
            bmc_partner_manager TEXT,
            relationship_owner TEXT,
            submitted_by_user_id INTEGER,
            submitted_by_email TEXT,
            submitted_by_name TEXT,
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
            account_id INTEGER,
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
            work_day_start TEXT,
            work_day_end TEXT,
            non_working_start_date TEXT,
            non_working_end_date TEXT,
            date_created TEXT DEFAULT CURRENT_TIMESTAMP,
            last_updated TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS non_working_blocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            reason TEXT,
            date_created TEXT DEFAULT CURRENT_TIMESTAMP,
            last_updated TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,
            entity_id INTEGER,
            action_type TEXT NOT NULL,
            field_name TEXT,
            field_label TEXT,
            value_from TEXT,
            value_to TEXT,
            actor_user_id INTEGER,
            actor_name TEXT,
            actor_email TEXT,
            date_created TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Safe migrations for account custom values
    add_column_if_missing(cursor, "account_custom_values", "team_id", "INTEGER DEFAULT 1")
    add_column_if_missing(cursor, "account_custom_values", "account_id", "INTEGER")
    add_column_if_missing(cursor, "account_custom_values", "field_key", "TEXT")
    add_column_if_missing(cursor, "account_custom_values", "field_value", "TEXT")
    add_column_if_missing(cursor, "account_custom_values", "date_created", "TEXT DEFAULT CURRENT_TIMESTAMP")
    add_column_if_missing(cursor, "account_custom_values", "last_updated", "TEXT DEFAULT CURRENT_TIMESTAMP")

    # Safe migrations for accounts
    add_column_if_missing(cursor, "accounts", "team_id", "INTEGER DEFAULT 1")
    add_column_if_missing(cursor, "accounts", "business_unit", "TEXT")
    add_column_if_missing(cursor, "accounts", "account_tier", "TEXT")
    add_column_if_missing(cursor, "accounts", "pg_bible_order", "INTEGER")
    add_column_if_missing(cursor, "accounts", "current_pipeline", "REAL")
    add_column_if_missing(cursor, "accounts", "nbm_target", "TEXT")
    add_column_if_missing(cursor, "accounts", "sales_play", "TEXT")
    add_column_if_missing(cursor, "accounts", "owner_user_id", "INTEGER")
    add_column_if_missing(cursor, "accounts", "owner_name", "TEXT")
    add_column_if_missing(cursor, "accounts", "owner_email", "TEXT")

    # Safe migrations for dashboard settings and PG action dashboard overrides
    add_column_if_missing(cursor, "dashboard_settings", "setting_key", "TEXT")
    add_column_if_missing(cursor, "dashboard_settings", "setting_value", "TEXT")
    add_column_if_missing(cursor, "dashboard_settings", "last_updated", "TEXT DEFAULT CURRENT_TIMESTAMP")
    add_column_if_missing(cursor, "pg_action_updates", "account_id", "INTEGER")
    add_column_if_missing(cursor, "pg_action_updates", "completed_discovery_meeting", "TEXT")
    add_column_if_missing(cursor, "pg_action_updates", "next_action_override", "TEXT")
    add_column_if_missing(cursor, "pg_action_updates", "date_created", "TEXT DEFAULT CURRENT_TIMESTAMP")
    add_column_if_missing(cursor, "pg_action_updates", "last_updated", "TEXT DEFAULT CURRENT_TIMESTAMP")
    add_column_if_missing(cursor, "pg_action_contact_updates", "account_id", "INTEGER")
    add_column_if_missing(cursor, "pg_action_contact_updates", "contact_id", "INTEGER")
    add_column_if_missing(cursor, "pg_action_contact_updates", "completed_discovery_meeting", "TEXT")
    add_column_if_missing(cursor, "pg_action_contact_updates", "next_action_override", "TEXT")
    add_column_if_missing(cursor, "pg_action_contact_updates", "date_created", "TEXT DEFAULT CURRENT_TIMESTAMP")
    add_column_if_missing(cursor, "pg_action_contact_updates", "last_updated", "TEXT DEFAULT CURRENT_TIMESTAMP")

    # Safe migrations for account sharing permissions
    add_column_if_missing(cursor, "account_shared_users", "account_id", "INTEGER")
    add_column_if_missing(cursor, "account_shared_users", "user_id", "INTEGER")
    add_column_if_missing(cursor, "account_shared_users", "full_name", "TEXT")
    add_column_if_missing(cursor, "account_shared_users", "email", "TEXT")
    add_column_if_missing(cursor, "account_shared_users", "workspace_schema", "TEXT")
    add_column_if_missing(cursor, "account_shared_users", "date_created", "TEXT DEFAULT CURRENT_TIMESTAMP")
    add_column_if_missing(cursor, "account_shared_users", "last_updated", "TEXT DEFAULT CURRENT_TIMESTAMP")

    # Safe migrations for contacts
    add_column_if_missing(cursor, "contacts", "team_id", "INTEGER DEFAULT 1")

    # Safe migrations for outreach
    add_column_if_missing(cursor, "outreach", "team_id", "INTEGER DEFAULT 1")
    add_column_if_missing(cursor, "outreach", "fy", "TEXT")
    add_column_if_missing(cursor, "outreach", "quarter", "TEXT")
    add_column_if_missing(cursor, "outreach", "campaign", "TEXT")
    add_column_if_missing(cursor, "outreach", "sales_play", "TEXT")
    add_column_if_missing(cursor, "outreach", "campaign_start_date", "TEXT")
    add_column_if_missing(cursor, "outreach", "campaign_end_date", "TEXT")
    add_column_if_missing(cursor, "outreach", "campaign_tasks_per_week", "INTEGER")
    add_column_if_missing(cursor, "outreach", "campaign_total_tasks", "INTEGER")
    add_column_if_missing(cursor, "outreach", "activity_time", "TEXT")
    add_column_if_missing(cursor, "outreach", "next_action_time", "TEXT")
    add_column_if_missing(cursor, "outreach", "task_status", "TEXT DEFAULT 'Not Started'")
    add_column_if_missing(cursor, "outreach", "assigned_to", "TEXT")

    # Safe migrations for account partners
    add_column_if_missing(cursor, "account_partners", "team_id", "INTEGER DEFAULT 1")
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
    add_column_if_missing(cursor, "partners", "team_id", "INTEGER DEFAULT 1")
    add_column_if_missing(cursor, "partners", "partner_name", "TEXT")
    add_column_if_missing(cursor, "partners", "partner_type", "TEXT")
    add_column_if_missing(cursor, "partners", "website", "TEXT")
    add_column_if_missing(cursor, "partners", "country", "TEXT")
    add_column_if_missing(cursor, "partners", "city", "TEXT")
    add_column_if_missing(cursor, "partners", "partner_manager", "TEXT")
    add_column_if_missing(cursor, "partners", "bmc_partner_manager", "TEXT")
    add_column_if_missing(cursor, "partners", "relationship_owner", "TEXT")
    add_column_if_missing(cursor, "partners", "submitted_by_user_id", "INTEGER")
    add_column_if_missing(cursor, "partners", "submitted_by_email", "TEXT")
    add_column_if_missing(cursor, "partners", "submitted_by_name", "TEXT")
    add_column_if_missing(cursor, "partners", "notes", "TEXT")
    add_column_if_missing(cursor, "partners", "date_created", "TEXT DEFAULT CURRENT_TIMESTAMP")
    add_column_if_missing(cursor, "partners", "last_updated", "TEXT DEFAULT CURRENT_TIMESTAMP")

    # Safe migrations for partner contacts
    add_column_if_missing(cursor, "partner_contacts", "team_id", "INTEGER DEFAULT 1")
    add_column_if_missing(cursor, "partner_contacts", "partner_id", "INTEGER")
    add_column_if_missing(cursor, "partner_contacts", "name", "TEXT")
    add_column_if_missing(cursor, "partner_contacts", "job_title", "TEXT")
    add_column_if_missing(cursor, "partner_contacts", "partner_contact_role", "TEXT")
    add_column_if_missing(cursor, "partner_contacts", "coverage_area", "TEXT")
    add_column_if_missing(cursor, "partner_contacts", "account_id", "INTEGER")
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
    add_column_if_missing(cursor, "timeline_entries", "team_id", "INTEGER DEFAULT 1")
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
    add_column_if_missing(cursor, "user_profile", "work_day_start", "TEXT")
    add_column_if_missing(cursor, "user_profile", "work_day_end", "TEXT")
    add_column_if_missing(cursor, "user_profile", "non_working_start_date", "TEXT")
    add_column_if_missing(cursor, "user_profile", "non_working_end_date", "TEXT")
    add_column_if_missing(cursor, "user_profile", "date_created", "TEXT DEFAULT CURRENT_TIMESTAMP")
    add_column_if_missing(cursor, "user_profile", "last_updated", "TEXT DEFAULT CURRENT_TIMESTAMP")

    # Safe migrations for non-working blocks
    add_column_if_missing(cursor, "non_working_blocks", "start_date", "TEXT")
    add_column_if_missing(cursor, "non_working_blocks", "end_date", "TEXT")
    add_column_if_missing(cursor, "non_working_blocks", "reason", "TEXT")
    add_column_if_missing(cursor, "non_working_blocks", "date_created", "TEXT DEFAULT CURRENT_TIMESTAMP")
    add_column_if_missing(cursor, "non_working_blocks", "last_updated", "TEXT DEFAULT CURRENT_TIMESTAMP")

    # Safe migrations for structured audit entries
    add_column_if_missing(cursor, "audit_entries", "team_id", "INTEGER DEFAULT 1")
    add_column_if_missing(cursor, "audit_entries", "entity_type", "TEXT")
    add_column_if_missing(cursor, "audit_entries", "entity_id", "INTEGER")
    add_column_if_missing(cursor, "audit_entries", "action_type", "TEXT")
    add_column_if_missing(cursor, "audit_entries", "field_name", "TEXT")
    add_column_if_missing(cursor, "audit_entries", "field_label", "TEXT")
    add_column_if_missing(cursor, "audit_entries", "value_from", "TEXT")
    add_column_if_missing(cursor, "audit_entries", "value_to", "TEXT")
    add_column_if_missing(cursor, "audit_entries", "actor_user_id", "INTEGER")
    add_column_if_missing(cursor, "audit_entries", "actor_name", "TEXT")
    add_column_if_missing(cursor, "audit_entries", "actor_email", "TEXT")
    add_column_if_missing(cursor, "audit_entries", "date_created", "TEXT DEFAULT CURRENT_TIMESTAMP")

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

    index_definitions = [
        ("idx_accounts_pg_bible_order", "accounts", ["pg_bible_order", "account_name"]),
        ("idx_accounts_tier", "accounts", ["account_tier"]),
        ("idx_accounts_owner", "accounts", ["owner_user_id"]),
        ("idx_accounts_nbm_target", "accounts", ["nbm_target"]),
        ("idx_account_shared_users_account", "account_shared_users", ["account_id"]),
        ("idx_account_shared_users_user", "account_shared_users", ["user_id"]),
        ("idx_pg_action_updates_account", "pg_action_updates", ["account_id"]),
        ("idx_pg_action_contact_updates_account", "pg_action_contact_updates", ["account_id"]),
        ("idx_pg_action_contact_updates_contact", "pg_action_contact_updates", ["contact_id"]),
        ("idx_contacts_account", "contacts", ["account_id"]),
        ("idx_contacts_category", "contacts", ["category"]),
        ("idx_outreach_account", "outreach", ["account_id"]),
        ("idx_outreach_contact", "outreach", ["contact_id"]),
        ("idx_outreach_activity_date", "outreach", ["activity_date"]),
        ("idx_outreach_next_action_date", "outreach", ["next_action_date"]),
        ("idx_outreach_task_status", "outreach", ["task_status"]),
        ("idx_outreach_campaign", "outreach", ["campaign"]),
        ("idx_outreach_sales_play", "outreach", ["sales_play"]),
        ("idx_account_partners_account", "account_partners", ["account_id"]),
        ("idx_account_partners_partner", "account_partners", ["partner_id"]),
        ("idx_partner_contacts_partner", "partner_contacts", ["partner_id"]),
        ("idx_timeline_related", "timeline_entries", ["related_type", "related_id"]),
        ("idx_account_custom_values_account", "account_custom_values", ["account_id"]),
        ("idx_audit_entity", "audit_entries", ["entity_type", "entity_id"]),
        ("idx_non_working_blocks_dates", "non_working_blocks", ["start_date", "end_date"]),
    ]
    for index_name, table_name, columns in index_definitions:
        create_index_if_missing(cursor, index_name, table_name, columns)

    connection.commit()
    connection.close()
    _INITIALISED_DATABASES.add(cache_key)
