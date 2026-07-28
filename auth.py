import sqlite3
import os
import base64
import hashlib
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from functools import wraps
from pathlib import Path

from flask import redirect, session, url_for
from cryptography.fernet import Fernet, InvalidToken
from werkzeug.security import check_password_hash, generate_password_hash
from db_compat import get_connection, postgres_identifier, using_postgres


AUTH_DB_NAME = "pipeflow_server_auth.db"
VALID_ROLES = {"admin", "company_admin", "manager", "user"}
VALID_ACCOUNT_FIELD_TYPES = {"text", "number", "date", "textarea"}
VALID_BROADCAST_SEVERITIES = {"info", "success", "warning", "urgent"}
DEFAULT_ADMIN_TENANT = "PipeFlow Administration"


def auth_secret_material() -> str:
    return (
        os.environ.get("PIPEFLOW_SECRET_KEY")
        or os.environ.get("SECRET_KEY")
        or os.environ.get("DATABASE_URL")
        or "pipeflow-local-dev-secret-change-me"
    )


def phrase_cipher() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(auth_secret_material().encode("utf-8")).digest())
    return Fernet(key)


def encrypt_secret_phrase(phrase: str) -> str:
    phrase = (phrase or "").strip()
    if not phrase:
        return ""
    return phrase_cipher().encrypt(phrase.encode("utf-8")).decode("utf-8")


def decrypt_secret_phrase(encrypted_phrase: str) -> str:
    encrypted_phrase = (encrypted_phrase or "").strip()
    if not encrypted_phrase:
        return ""
    try:
        return phrase_cipher().decrypt(encrypted_phrase.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""


def migrate_plain_secret_phrases(connection):
    rows = connection.execute("""
        SELECT id, reset_phrase_plain, reset_phrase_encrypted
        FROM users
        WHERE COALESCE(reset_phrase_plain, '') != ''
    """).fetchall()
    for row in rows:
        encrypted = row["reset_phrase_encrypted"] if "reset_phrase_encrypted" in row.keys() else ""
        encrypted = encrypted or encrypt_secret_phrase(row["reset_phrase_plain"])
        connection.execute("""
            UPDATE users
            SET reset_phrase_encrypted = ?,
                reset_phrase_plain = NULL,
                last_updated = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (encrypted, row["id"]))



def server_data_root() -> Path:
    root = Path(os.environ.get("PIPEFLOW_DATA_DIR", Path(__file__).resolve().parent / "server_data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def auth_database_path() -> Path:
    return server_data_root() / AUTH_DB_NAME


def get_auth_connection():
    if using_postgres():
        return get_connection(schema="public")
    connection = sqlite3.connect(auth_database_path())
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def add_column_if_missing(connection, table_name, column_name, column_definition):
    if using_postgres():
        rows = connection.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = ?
            """,
            (table_name,),
        ).fetchall()
        existing_columns = [row["column_name"] for row in rows]
    else:
        rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        existing_columns = [row["name"] for row in rows]
    if column_name not in existing_columns:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")


def initialise_auth_database() -> None:
    connection = get_auth_connection()
    if using_postgres():
        connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                company TEXT,
                role TEXT DEFAULT 'user',
                reset_phrase_hash TEXT,
                reset_phrase_plain TEXT,
                reset_phrase_encrypted TEXT,
                is_active INTEGER DEFAULT 1,
                date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    else:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                company TEXT,
                role TEXT DEFAULT 'user',
                reset_phrase_hash TEXT,
                reset_phrase_plain TEXT,
                reset_phrase_encrypted TEXT,
                is_active INTEGER DEFAULT 1,
                date_created TEXT DEFAULT CURRENT_TIMESTAMP,
                last_updated TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL UNIQUE,
            country TEXT NOT NULL,
            company_contact TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            date_created TEXT DEFAULT CURRENT_TIMESTAMP,
            last_updated TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS account_field_definitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            field_key TEXT NOT NULL UNIQUE,
            field_label TEXT NOT NULL,
            field_type TEXT NOT NULL DEFAULT 'text',
            is_required INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            sort_order INTEGER DEFAULT 0,
            date_created TEXT DEFAULT CURRENT_TIMESTAMP,
            last_updated TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS admin_audit_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_user_id INTEGER,
            actor_name TEXT,
            actor_email TEXT,
            action_type TEXT NOT NULL,
            target_type TEXT,
            target_label TEXT,
            detail TEXT,
            date_created TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS broadcast_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'info',
            target_companies TEXT,
            start_at TEXT,
            stop_at TEXT,
            is_active INTEGER DEFAULT 1,
            date_created TEXT DEFAULT CURRENT_TIMESTAMP,
            last_updated TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS admin_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT,
            last_updated TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_name TEXT NOT NULL UNIQUE,
            company TEXT,
            created_by_user_id INTEGER,
            date_created TEXT DEFAULT CURRENT_TIMESTAMP,
            last_updated TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS team_memberships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL DEFAULT 'member',
            date_created TEXT DEFAULT CURRENT_TIMESTAMP,
            last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(team_id, user_id)
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS user_company_memberships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            company_name TEXT NOT NULL,
            date_created TEXT DEFAULT CURRENT_TIMESTAMP,
            last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, company_name)
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS team_invites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL,
            email TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'member',
            status TEXT NOT NULL DEFAULT 'pending',
            invited_by_user_id INTEGER,
            date_created TEXT DEFAULT CURRENT_TIMESTAMP,
            last_updated TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    add_column_if_missing(connection, "users", "reset_phrase_hash", "TEXT")
    add_column_if_missing(connection, "users", "reset_phrase_plain", "TEXT")
    add_column_if_missing(connection, "users", "reset_phrase_encrypted", "TEXT")
    add_column_if_missing(connection, "users", "company", "TEXT")
    add_column_if_missing(connection, "users", "team", "TEXT")
    add_column_if_missing(connection, "users", "workspace_schema", "TEXT")
    add_column_if_missing(connection, "users", "active_team_id", "INTEGER")
    add_column_if_missing(connection, "teams", "company", "TEXT")
    add_column_if_missing(connection, "broadcast_messages", "target_companies", "TEXT")
    add_column_if_missing(connection, "broadcast_messages", "start_at", "TEXT")
    add_column_if_missing(connection, "broadcast_messages", "stop_at", "TEXT")
    add_column_if_missing(connection, "team_memberships", "role", "TEXT DEFAULT 'member'")
    add_column_if_missing(connection, "team_invites", "status", "TEXT DEFAULT 'pending'")
    add_column_if_missing(connection, "user_company_memberships", "user_id", "INTEGER")
    add_column_if_missing(connection, "user_company_memberships", "company_name", "TEXT")
    add_column_if_missing(connection, "user_company_memberships", "date_created", "TEXT DEFAULT CURRENT_TIMESTAMP")
    add_column_if_missing(connection, "user_company_memberships", "last_updated", "TEXT DEFAULT CURRENT_TIMESTAMP")
    connection.execute(
        """
        INSERT INTO tenants (company_name, country, company_contact, is_active)
        SELECT ?, ?, ?, 1
        WHERE NOT EXISTS (SELECT 1 FROM tenants WHERE LOWER(company_name) = LOWER(?))
        """,
        (DEFAULT_ADMIN_TENANT, "United Kingdom", "Application Administrator", DEFAULT_ADMIN_TENANT),
    )
    existing_companies = connection.execute(
        """
        SELECT DISTINCT TRIM(company) AS company_name
        FROM users
        WHERE company IS NOT NULL
          AND TRIM(company) != ''
        """
    ).fetchall()
    for row in existing_companies:
        company_name = row["company_name"]
        connection.execute(
            """
            INSERT INTO tenants (company_name, country, company_contact, is_active)
            SELECT ?, ?, ?, 1
            WHERE NOT EXISTS (SELECT 1 FROM tenants WHERE LOWER(company_name) = LOWER(?))
            """,
            (company_name, "Not set", "Not set", company_name),
        )
    connection.execute(
        """
        UPDATE users
        SET company = ?
        WHERE company IS NULL
           OR TRIM(company) = ''
        """,
        (DEFAULT_ADMIN_TENANT,),
    )
    migrate_plain_secret_phrases(connection)
    connection.commit()
    connection.close()


def normalise_email(email: str) -> str:
    return (email or "").strip().lower()


def user_count() -> int:
    connection = get_auth_connection()
    row = connection.execute("SELECT COUNT(*) AS total FROM users").fetchone()
    connection.close()
    return int(row["total"] if hasattr(row, "keys") else row[0])


def normalise_company_name(company_name: str) -> str:
    return " ".join((company_name or "").strip().split())


def is_application_admin(user):
    return bool(user and user["role"] == "admin")


def is_company_admin(user):
    return bool(user and user["role"] == "company_admin")


def same_company(left, right):
    if not left or not right:
        return False
    left_company = left["company"] if "company" in left.keys() and left["company"] else ""
    right_company = right["company"] if "company" in right.keys() and right["company"] else ""
    left_key = normalise_company_name(left_company).lower()
    right_companies = user_company_names(right, include_primary=True)
    return bool(left_key and left_key in {company.lower() for company in right_companies})


def user_company_names(user_or_id, include_primary: bool = True):
    if not user_or_id:
        return []
    user_id = user_or_id
    primary_company = ""
    if hasattr(user_or_id, "keys"):
        user_id = user_or_id["id"]
        primary_company = user_or_id["company"] if "company" in user_or_id.keys() and user_or_id["company"] else ""
    elif isinstance(user_or_id, dict):
        user_id = user_or_id.get("id")
        primary_company = user_or_id.get("company") or ""

    companies = []
    if include_primary:
        primary_company = normalise_company_name(primary_company)
        if primary_company:
            companies.append(primary_company)
    if not user_id:
        return companies

    connection = get_auth_connection()
    rows = connection.execute("""
        SELECT company_name
        FROM user_company_memberships
        WHERE user_id = ?
        ORDER BY company_name
    """, (user_id,)).fetchall()
    connection.close()
    seen = {company.casefold() for company in companies}
    for row in rows:
        company = normalise_company_name(row["company_name"])
        key = company.casefold()
        if company and key not in seen:
            companies.append(company)
            seen.add(key)
    return companies


def user_company_label(user):
    companies = user_company_names(user, include_primary=True)
    return ", ".join(companies) if companies else ""


def set_user_company_memberships(user_id: int, companies):
    user = get_user_for_admin(user_id)
    if not user:
        return "User was not found."
    if user["role"] != "admin":
        companies = [user["company"] if "company" in user.keys() else ""]
    cleaned = normalise_broadcast_companies(companies)
    primary_company = normalise_company_name(user["company"] if "company" in user.keys() else "")
    if primary_company and primary_company not in cleaned:
        cleaned.insert(0, primary_company)
    if not cleaned:
        return "Select at least one company."
    invalid = [company for company in cleaned if not tenant_exists(company)]
    if invalid:
        return "Select valid configured companies only."

    connection = get_auth_connection()
    connection.execute("DELETE FROM user_company_memberships WHERE user_id = ?", (user_id,))
    for company in cleaned:
        connection.execute("""
            INSERT OR IGNORE INTO user_company_memberships (user_id, company_name)
            VALUES (?, ?)
        """, (user_id, company))
    connection.commit()
    connection.close()
    return ""


def tenant_exists(company_name: str) -> bool:
    company_name = normalise_company_name(company_name)
    if not company_name:
        return False
    connection = get_auth_connection()
    row = connection.execute(
        """
        SELECT id
        FROM tenants
        WHERE LOWER(company_name) = LOWER(?)
          AND is_active = 1
        """,
        (company_name,),
    ).fetchone()
    connection.close()
    return bool(row)


def list_tenants(actor=None, active_only: bool = True):
    connection = get_auth_connection()
    params = []
    query = """
        SELECT *
        FROM tenants
        WHERE 1 = 1
    """
    if active_only:
        query += " AND is_active = 1"
    if actor and not is_application_admin(actor):
        query += " AND LOWER(company_name) = LOWER(?)"
        params.append(actor["company"] if "company" in actor.keys() and actor["company"] else "")
    query += " ORDER BY company_name"
    rows = connection.execute(query, params).fetchall()
    connection.close()
    return rows


def create_tenant(company_name: str, country: str, company_contact: str):
    company_name = normalise_company_name(company_name)
    country = (country or "").strip()
    company_contact = (company_contact or "").strip()
    if not company_name or not country or not company_contact:
        return "Company Name, Country and Company contact are required."
    connection = get_auth_connection()
    try:
        connection.execute(
            """
            INSERT INTO tenants (company_name, country, company_contact, is_active)
            VALUES (?, ?, ?, 1)
            """,
            (company_name, country, company_contact),
        )
        connection.commit()
        return ""
    except Exception as exc:
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            return "A tenant already exists for that company name."
        raise
    finally:
        connection.close()


def update_tenant(tenant_id: int, country: str, company_contact: str, is_active: bool, actor=None):
    country = (country or "").strip()
    company_contact = (company_contact or "").strip()
    if not country or not company_contact:
        return "Country and primary company contact are required."
    connection = get_auth_connection()
    tenant = connection.execute("SELECT * FROM tenants WHERE id = ?", (tenant_id,)).fetchone()
    if not tenant:
        connection.close()
        return "Tenant could not be found."
    if actor and not is_application_admin(actor):
        actor_company = actor["company"] if "company" in actor.keys() else ""
        if normalise_company_name(actor_company).lower() != normalise_company_name(tenant["company_name"]).lower():
            connection.close()
            return "You can only update your own company tenant."
    connection.execute(
        """
        UPDATE tenants
        SET country = ?,
            company_contact = ?,
            is_active = ?,
            last_updated = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (country, company_contact, 1 if is_active else 0, tenant_id),
    )
    connection.commit()
    connection.close()
    return ""


def get_tenant_by_name(company_name: str):
    company_name = normalise_company_name(company_name)
    connection = get_auth_connection()
    row = connection.execute(
        """
        SELECT *
        FROM tenants
        WHERE LOWER(company_name) = LOWER(?)
        """,
        (company_name,),
    ).fetchone()
    connection.close()
    return row


def create_user(email: str, password: str, full_name: str, reset_phrase: str = "", company: str = ""):
    email = normalise_email(email)
    full_name = (full_name or "").strip()
    reset_phrase = (reset_phrase or "").strip()
    company = normalise_company_name(company)
    if not email or not password or not full_name or not reset_phrase:
        return None, "All fields are required."
    if len(reset_phrase) < 12:
        return None, "Secret reset phrase must be at least 12 characters."

    connection = get_auth_connection()
    try:
        existing_count = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        role = "admin" if existing_count == 0 else "user"
        if existing_count == 0 and not company:
            company = DEFAULT_ADMIN_TENANT
        if not company or not tenant_exists(company):
            return None, "Select a valid tenant before creating a user profile."
        if using_postgres():
            cursor = connection.execute(
                """
                INSERT INTO users (email, password_hash, full_name, company, role, reset_phrase_hash, reset_phrase_plain, reset_phrase_encrypted)
                VALUES (?, ?, ?, ?, ?, ?, NULL, ?)
                RETURNING id
                """,
                (email, generate_password_hash(password), full_name, company, role, generate_password_hash(reset_phrase), encrypt_secret_phrase(reset_phrase)),
            )
            row = cursor.fetchone()
            user_id = row["id"]
        else:
            cursor = connection.execute(
                """
                INSERT INTO users (email, password_hash, full_name, company, role, reset_phrase_hash, reset_phrase_plain, reset_phrase_encrypted)
                VALUES (?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (email, generate_password_hash(password), full_name, company, role, generate_password_hash(reset_phrase), encrypt_secret_phrase(reset_phrase)),
            )
            user_id = cursor.lastrowid
        connection.commit()
        return user_id, ""
    except Exception as exc:
        if "unique" not in str(exc).lower() and "duplicate" not in str(exc).lower():
            raise
        return None, "An account already exists for that email address."
    finally:
        connection.close()


def verify_reset_phrase(email: str, reset_phrase: str):
    reset_phrase = (reset_phrase or "").strip()
    if not reset_phrase:
        return None

    connection = get_auth_connection()
    user = connection.execute(
        """
        SELECT id, email, full_name, reset_phrase_hash
        FROM users
        WHERE email = ?
          AND is_active = 1
        """,
        (normalise_email(email),),
    ).fetchone()
    connection.close()

    if user and user["reset_phrase_hash"] and check_password_hash(user["reset_phrase_hash"], reset_phrase):
        return user
    return None


def reset_password_with_phrase(email: str, reset_phrase: str, password: str):
    user = verify_reset_phrase(email, reset_phrase)
    if not user:
        return "Email or secret phrase was not recognised."

    password = (password or "").strip()
    if len(password) < 8:
        return "Password must be at least 8 characters."

    connection = get_auth_connection()
    connection.execute(
        """
        UPDATE users
        SET password_hash = ?,
            last_updated = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (generate_password_hash(password), user["id"]),
    )
    connection.commit()
    connection.close()
    return ""


def update_current_user_secret_phrase(user_id: int, new_phrase: str, confirm_phrase: str):
    new_phrase = (new_phrase or "").strip()
    confirm_phrase = (confirm_phrase or "").strip()
    if not new_phrase or not confirm_phrase:
        return "Enter and confirm your new secret phrase."
    if len(new_phrase) < 12:
        return "Secret phrase must be at least 12 characters."
    if new_phrase != confirm_phrase:
        return "Secret phrase confirmation does not match."

    connection = get_auth_connection()
    try:
        user = connection.execute(
            "SELECT id FROM users WHERE id = ? AND is_active = 1",
            (user_id,),
        ).fetchone()
        if not user:
            return "Your profile could not be found."
        connection.execute(
            """
            UPDATE users
            SET reset_phrase_hash = ?,
                reset_phrase_plain = NULL,
                reset_phrase_encrypted = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (generate_password_hash(new_phrase), encrypt_secret_phrase(new_phrase), user_id),
        )
        connection.commit()
        return ""
    finally:
        connection.close()


def reveal_user_secret_phrase(user_id: int):
    connection = get_auth_connection()
    try:
        row = connection.execute(
            """
            SELECT id, reset_phrase_plain, reset_phrase_encrypted
            FROM users
            WHERE id = ?
              AND is_active = 1
            """,
            (user_id,),
        ).fetchone()
        if not row:
            return ""
        decrypted = decrypt_secret_phrase(row["reset_phrase_encrypted"] if "reset_phrase_encrypted" in row.keys() else "")
        if decrypted:
            return decrypted
        legacy_plain = row["reset_phrase_plain"] if "reset_phrase_plain" in row.keys() else ""
        if legacy_plain:
            encrypted = encrypt_secret_phrase(legacy_plain)
            connection.execute("""
                UPDATE users
                SET reset_phrase_encrypted = ?,
                    reset_phrase_plain = NULL,
                    last_updated = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (encrypted, user_id))
            connection.commit()
            return legacy_plain
        return ""
    finally:
        connection.close()


def authenticate_user(email: str, password: str):
    connection = get_auth_connection()
    user = connection.execute(
        """
        SELECT *
        FROM users
        WHERE email = ?
          AND is_active = 1
        """,
        (normalise_email(email),),
    ).fetchone()
    connection.close()

    if user and check_password_hash(user["password_hash"], password):
        return user
    return None


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None

    connection = get_auth_connection()
    user = connection.execute(
        """
        SELECT id, email, full_name, company, team, role, workspace_schema, active_team_id
        FROM users
        WHERE id = ?
          AND is_active = 1
          AND company IS NOT NULL
          AND TRIM(company) != ''
        """,
        (user_id,),
    ).fetchone()
    connection.close()
    return user


def ensure_default_team_for_user(user):
    if not user:
        return None
    connection = get_auth_connection()
    active_team_id = user["active_team_id"] if "active_team_id" in user.keys() else None
    if active_team_id:
        membership = connection.execute(
            "SELECT team_id FROM team_memberships WHERE team_id = ? AND user_id = ?",
            (active_team_id, user["id"]),
        ).fetchone()
        if membership:
            connection.close()
            return active_team_id

    team_name = user["team"] or f"{user['full_name']} Team"
    if using_postgres():
        row = connection.execute(
            """
            INSERT INTO teams (team_name, company, created_by_user_id)
            VALUES (?, ?, ?)
            ON CONFLICT (team_name) DO UPDATE SET team_name = EXCLUDED.team_name
            RETURNING id
            """,
            (team_name, user["company"] if "company" in user.keys() else "", user["id"]),
        ).fetchone()
        team_id = row["id"]
    else:
        connection.execute(
            "INSERT OR IGNORE INTO teams (team_name, company, created_by_user_id) VALUES (?, ?, ?)",
            (team_name, user["company"] if "company" in user.keys() else "", user["id"]),
        )
        team_id = connection.execute("SELECT id FROM teams WHERE team_name = ?", (team_name,)).fetchone()["id"]
    membership_role = "admin" if user["role"] in ("admin", "company_admin") else "member"
    if using_postgres():
        connection.execute(
            """
            INSERT INTO team_memberships (team_id, user_id, role)
            VALUES (?, ?, ?)
            ON CONFLICT (team_id, user_id) DO UPDATE SET role = EXCLUDED.role
            """,
            (team_id, user["id"], membership_role),
        )
    else:
        connection.execute(
            "INSERT OR IGNORE INTO team_memberships (team_id, user_id, role) VALUES (?, ?, ?)",
            (team_id, user["id"], membership_role),
        )
    connection.execute(
        "UPDATE users SET active_team_id = ?, last_updated = CURRENT_TIMESTAMP WHERE id = ?",
        (team_id, user["id"]),
    )
    connection.commit()
    connection.close()
    return team_id


def active_team_for_user(user):
    team_id = ensure_default_team_for_user(user)
    if not team_id:
        return None
    connection = get_auth_connection()
    team = connection.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
    connection.close()
    return team


def create_team(team_name, company, actor=None):
    team_name = (team_name or "").strip()
    company = normalise_company_name(company)
    if not team_name or not company:
        return None, "Team name and company are required."
    if not tenant_exists(company):
        return None, "Select a valid tenant for the team."
    connection = get_auth_connection()
    if using_postgres():
        row = connection.execute("""
            INSERT INTO teams (team_name, company, created_by_user_id)
            VALUES (?, ?, ?)
            ON CONFLICT (team_name) DO UPDATE SET company = EXCLUDED.company
            RETURNING id
        """, (team_name, company, actor["id"] if actor else None)).fetchone()
        team_id = row["id"]
    else:
        connection.execute("""
            INSERT OR IGNORE INTO teams (team_name, company, created_by_user_id)
            VALUES (?, ?, ?)
        """, (team_name, company, actor["id"] if actor else None))
        connection.execute("""
            UPDATE teams
            SET company = COALESCE(NULLIF(company, ''), ?),
                last_updated = CURRENT_TIMESTAMP
            WHERE team_name = ?
        """, (company, team_name))
        team_id = connection.execute("SELECT id FROM teams WHERE team_name = ?", (team_name,)).fetchone()["id"]
    connection.commit()
    connection.close()
    return team_id, ""


def list_teams(actor=None, company=None):
    connection = get_auth_connection()
    params = []
    where = []
    if actor and not is_application_admin(actor):
        where.append("LOWER(COALESCE(company, '')) = LOWER(?)")
        params.append(actor["company"] if "company" in actor.keys() and actor["company"] else "")
    elif company:
        where.append("LOWER(COALESCE(company, '')) = LOWER(?)")
        params.append(normalise_company_name(company))
    where_sql = "WHERE " + " AND ".join(where) if where else ""
    rows = connection.execute(f"""
        SELECT *
        FROM teams
        {where_sql}
        ORDER BY company, team_name
    """, params).fetchall()
    connection.close()
    return rows


def user_team_ids(user_id):
    connection = get_auth_connection()
    rows = connection.execute("""
        SELECT team_id
        FROM team_memberships
        WHERE user_id = ?
        ORDER BY team_id
    """, (user_id,)).fetchall()
    connection.close()
    return [str(row["team_id"]) for row in rows]


def set_user_team_memberships(user_id, team_ids, membership_role="member"):
    team_ids = [str(team_id) for team_id in team_ids or [] if str(team_id or "").isdigit()]
    connection = get_auth_connection()
    user = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        connection.close()
        return "User was not found."
    valid_rows = []
    if team_ids:
        placeholders = ",".join("?" for _ in team_ids)
        company_names = user_company_names(user, include_primary=True)
        company_placeholders = ",".join("?" for _ in company_names) if company_names else "?"
        valid_rows = connection.execute(f"""
            SELECT id, team_name
            FROM teams
            WHERE id IN ({placeholders})
              AND LOWER(COALESCE(company, '')) IN ({",".join("LOWER(?)" for _ in (company_names or [""]))})
        """, (*team_ids, *(company_names or [""]))).fetchall()
    valid_ids = [str(row["id"]) for row in valid_rows]
    connection.execute("DELETE FROM team_memberships WHERE user_id = ?", (user_id,))
    for team_id in valid_ids:
        connection.execute("""
            INSERT OR IGNORE INTO team_memberships (team_id, user_id, role)
            VALUES (?, ?, ?)
        """, (team_id, user_id, membership_role))
    connection.execute("""
        UPDATE users
        SET active_team_id = ?,
            team = ?,
            last_updated = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (valid_ids[0] if valid_ids else None, valid_rows[0]["team_name"] if valid_rows else "", user_id))
    connection.commit()
    connection.close()
    return ""


def manager_team_members(user):
    if not user or user["role"] != "manager":
        return []
    connection = get_auth_connection()
    team_rows = connection.execute("""
        SELECT team_id
        FROM team_memberships
        WHERE user_id = ?
          AND role IN ('manager', 'admin')
    """, (user["id"],)).fetchall()
    team_ids = [str(row["team_id"]) for row in team_rows]
    if not team_ids:
        connection.close()
        return []
    placeholders = ",".join("?" for _ in team_ids)
    members = connection.execute(f"""
        SELECT DISTINCT users.id, users.email, users.full_name, users.company, users.team, users.role, users.workspace_schema, users.active_team_id
        FROM team_memberships
        JOIN users ON users.id = team_memberships.user_id
        WHERE team_memberships.team_id IN ({placeholders})
          AND users.is_active = 1
          AND LOWER(users.company) = LOWER(?)
        ORDER BY users.full_name, users.email
    """, (*team_ids, user["company"] or "")).fetchall()
    connection.close()
    for member in members:
        ensure_user_workspace_schema(member)
    return members


def list_active_team_members(user):
    team_id = ensure_default_team_for_user(user)
    if not team_id:
        return []
    connection = get_auth_connection()
    members = connection.execute(
        """
        SELECT users.id, users.email, users.full_name, users.company, users.team, users.workspace_schema, team_memberships.role
        FROM team_memberships
        JOIN users ON users.id = team_memberships.user_id
        WHERE team_memberships.team_id = ?
          AND users.is_active = 1
          AND LOWER(users.company) = LOWER(?)
        ORDER BY users.full_name, users.email
        """,
        (team_id, user["company"] if "company" in user.keys() and user["company"] else ""),
    ).fetchall()
    connection.close()
    return members


def list_active_team_invites(user):
    team_id = ensure_default_team_for_user(user)
    if not team_id:
        return []
    connection = get_auth_connection()
    invites = connection.execute(
        """
        SELECT *
        FROM team_invites
        WHERE team_id = ?
        ORDER BY date_created DESC, id DESC
        """,
        (team_id,),
    ).fetchall()
    connection.close()
    return invites


def create_team_invite(user, email, role="member"):
    team_id = ensure_default_team_for_user(user)
    email = normalise_email(email)
    role = role if role in {"admin", "member"} else "member"
    if not team_id or not email:
        return "Email is required."
    membership = None
    connection = get_auth_connection()
    if user:
        membership = connection.execute(
            "SELECT role FROM team_memberships WHERE team_id = ? AND user_id = ?",
            (team_id, user["id"]),
        ).fetchone()
    if not membership or membership["role"] != "admin":
        connection.close()
        return "Only team admins can invite users."
    connection.execute(
        """
        INSERT INTO team_invites (team_id, email, role, invited_by_user_id)
        VALUES (?, ?, ?, ?)
        """,
        (team_id, email, role, user["id"]),
    )
    connection.commit()
    connection.close()
    return ""


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            return redirect(url_for("login"))
        if user["role"] not in ("admin", "company_admin"):
            return redirect(url_for("home"))
        return view(*args, **kwargs)

    return wrapped


def ensure_user_workspace_schema(user):
    if not user:
        return ""
    if "workspace_schema" in user.keys() and user["workspace_schema"]:
        return user["workspace_schema"]
    schema = postgres_identifier(f"workspace_{user['email']}")
    connection = get_auth_connection()
    connection.execute(
        """
        UPDATE users
        SET workspace_schema = ?,
            last_updated = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (schema, user["id"]),
    )
    connection.commit()
    connection.close()
    return schema


def list_users(actor=None):
    connection = get_auth_connection()
    params = []
    company_clause = ""
    if actor and not is_application_admin(actor):
        company_clause = """
        WHERE (
            LOWER(company) = LOWER(?)
            OR id IN (
                SELECT user_id
                FROM user_company_memberships
                WHERE LOWER(company_name) = LOWER(?)
            )
        )
        """
        params.append(actor["company"] if "company" in actor.keys() and actor["company"] else "")
        params.append(actor["company"] if "company" in actor.keys() and actor["company"] else "")
    users = connection.execute(
        f"""
        SELECT id, email, full_name, company, team, role, is_active, workspace_schema, date_created, last_updated
        FROM users
        {company_clause}
        ORDER BY full_name, email
        """,
        params,
    ).fetchall()
    connection.close()
    for user in users:
        ensure_user_workspace_schema(user)
    connection = get_auth_connection()
    users = connection.execute(
        f"""
        SELECT id, email, full_name, company, team, role, is_active, workspace_schema, date_created, last_updated
        FROM users
        {company_clause}
        ORDER BY full_name, email
        """,
        params,
    ).fetchall()
    connection.close()
    return enrich_user_rows(users)


def list_assignable_users(actor=None):
    actor = actor or current_user()
    connection = get_auth_connection()
    params = []
    company_clause = ""
    if actor:
        company_clause = """
          AND (
                LOWER(company) = LOWER(?)
             OR id IN (
                    SELECT user_id
                    FROM user_company_memberships
                    WHERE LOWER(company_name) = LOWER(?)
                )
          )
        """
        params.append(actor["company"] if "company" in actor.keys() and actor["company"] else "")
        params.append(actor["company"] if "company" in actor.keys() and actor["company"] else "")
    users = connection.execute(
        f"""
        SELECT id, email, full_name, company, team, role, is_active, workspace_schema, date_created, last_updated
        FROM users
        WHERE is_active = 1
          AND company IS NOT NULL
          AND TRIM(company) != ''
          {company_clause}
        ORDER BY full_name, email
        """,
        params,
    ).fetchall()
    connection.close()
    for user in users:
        ensure_user_workspace_schema(user)
    connection = get_auth_connection()
    users = connection.execute(
        f"""
        SELECT id, email, full_name, company, team, role, is_active, workspace_schema, date_created, last_updated
        FROM users
        WHERE is_active = 1
          AND company IS NOT NULL
          AND TRIM(company) != ''
          {company_clause}
        ORDER BY full_name, email
        """,
        params,
    ).fetchall()
    connection.close()
    return enrich_user_rows(users)


def enrich_user_rows(users):
    enriched = []
    for user in users:
        item = dict(user)
        item["company_memberships"] = user_company_names(item, include_primary=True)
        item["company_membership_label"] = ", ".join(item["company_memberships"]) or item.get("company", "")
        enriched.append(item)
    return enriched


def set_user_active(user_id: int, is_active: bool):
    connection = get_auth_connection()
    connection.execute(
        """
        UPDATE users
        SET is_active = ?,
            last_updated = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (1 if is_active else 0, user_id),
    )
    connection.commit()
    connection.close()


def reset_user_password(user_id: int, password: str):
    password = (password or "").strip()
    if len(password) < 8:
        return "Password must be at least 8 characters."

    connection = get_auth_connection()
    connection.execute(
        """
        UPDATE users
        SET password_hash = ?,
            last_updated = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (generate_password_hash(password), user_id),
    )
    connection.commit()
    connection.close()
    return ""


def set_user_role(user_id: int, role: str):
    role = (role or "").strip().lower()
    if role not in VALID_ROLES:
        return "Choose a valid role."

    connection = get_auth_connection()
    connection.execute(
        """
        UPDATE users
        SET role = ?,
            last_updated = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (role, user_id),
    )
    connection.commit()
    connection.close()
    return ""



def account_field_key(label: str) -> str:
    import re
    key = re.sub(r"[^a-zA-Z0-9]+", "_", (label or "").strip().lower()).strip("_")
    if not key:
        key = "custom_field"
    if key[0].isdigit():
        key = f"field_{key}"
    return key[:40]


def list_account_field_definitions(active_only: bool = False):
    connection = get_auth_connection()
    query = """
        SELECT *
        FROM account_field_definitions
    """
    params = []
    if active_only:
        query += " WHERE is_active = ?"
        params.append(1)
    query += " ORDER BY sort_order, field_label"
    fields = connection.execute(query, params).fetchall()
    connection.close()
    return fields


def create_account_field_definition(label: str, field_type: str, is_required: bool):
    label = (label or "").strip()
    field_type = (field_type or "text").strip().lower()
    if not label:
        return "Field label is required."
    if field_type not in VALID_ACCOUNT_FIELD_TYPES:
        return "Choose a valid field type."

    connection = get_auth_connection()
    try:
        base_key = account_field_key(label)
        field_key = base_key
        suffix = 2
        while connection.execute(
            "SELECT id FROM account_field_definitions WHERE field_key = ?",
            (field_key,),
        ).fetchone():
            field_key = f"{base_key[:35]}_{suffix}"
            suffix += 1

        row = connection.execute("SELECT COALESCE(MAX(sort_order), 0) + 10 AS next_order FROM account_field_definitions").fetchone()
        sort_order = row["next_order"] if row else 10
        connection.execute(
            """
            INSERT INTO account_field_definitions (
                field_key,
                field_label,
                field_type,
                is_required,
                is_active,
                sort_order
            )
            VALUES (?, ?, ?, ?, 1, ?)
            """,
            (field_key, label, field_type, 1 if is_required else 0, sort_order),
        )
        connection.commit()
        return ""
    except Exception as exc:
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            return "A field with that label already exists."
        raise
    finally:
        connection.close()


def update_account_field_definition(field_id: int, label: str, field_type: str, is_required: bool, sort_order: str):
    label = (label or "").strip()
    field_type = (field_type or "text").strip().lower()
    if not label:
        return "Field label is required."
    if field_type not in VALID_ACCOUNT_FIELD_TYPES:
        return "Choose a valid field type."
    try:
        sort_value = int(sort_order or 0)
    except ValueError:
        sort_value = 0

    connection = get_auth_connection()
    connection.execute(
        """
        UPDATE account_field_definitions
        SET field_label = ?,
            field_type = ?,
            is_required = ?,
            sort_order = ?,
            last_updated = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (label, field_type, 1 if is_required else 0, sort_value, field_id),
    )
    connection.commit()
    connection.close()
    return ""


def set_account_field_active(field_id: int, is_active: bool):
    connection = get_auth_connection()
    connection.execute(
        """
        UPDATE account_field_definitions
        SET is_active = ?,
            last_updated = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (1 if is_active else 0, field_id),
    )
    connection.commit()
    connection.close()


def normalise_broadcast_severity(severity: str) -> str:
    severity = (severity or "info").strip().lower()
    return severity if severity in VALID_BROADCAST_SEVERITIES else "info"


def normalise_broadcast_datetime(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M")
    except ValueError:
        return ""
    return parsed.strftime("%Y-%m-%dT%H:%M")


def normalise_broadcast_companies(companies):
    if isinstance(companies, str):
        raw_values = [companies]
    else:
        raw_values = list(companies or [])
    cleaned = []
    seen = set()
    for company in raw_values:
        company_name = normalise_company_name(company)
        key = company_name.casefold()
        if company_name and key not in seen:
            cleaned.append(company_name)
            seen.add(key)
    return cleaned


def encode_broadcast_companies(companies):
    cleaned = normalise_broadcast_companies(companies)
    return json.dumps(cleaned)


def decode_broadcast_companies(value):
    value = (value or "").strip()
    if not value:
        return []
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        decoded = [part.strip() for part in value.split(",")]
    return normalise_broadcast_companies(decoded)


def broadcast_visible_to_company(row, company):
    target_companies = decode_broadcast_companies(row["target_companies"] if "target_companies" in row.keys() else "")
    if not target_companies:
        return True
    company_key = normalise_company_name(company).casefold()
    return bool(company_key and company_key in {item.casefold() for item in target_companies})


def broadcast_timezone():
    timezone_name = os.environ.get("PIPEFLOW_TIMEZONE", "Europe/London")
    try:
        return ZoneInfo(timezone_name)
    except Exception:
        return ZoneInfo("Europe/London")


def current_broadcast_key() -> str:
    return datetime.now(broadcast_timezone()).strftime("%Y-%m-%dT%H:%M")


def cleanup_duplicate_broadcast_messages(connection):
    rows = connection.execute(
        """
        SELECT *
        FROM broadcast_messages
        ORDER BY id ASC
        """
    ).fetchall()
    seen = set()
    duplicate_ids = []
    for row in rows:
        key = (
            row["title"],
            row["message"],
            row["severity"],
            row["start_at"] if "start_at" in row.keys() else "",
            row["stop_at"] if "stop_at" in row.keys() else "",
        )
        if key in seen:
            duplicate_ids.append(row["id"])
        else:
            seen.add(key)

    for duplicate_id in duplicate_ids:
        connection.execute("DELETE FROM broadcast_messages WHERE id = ?", (duplicate_id,))
    if duplicate_ids:
        connection.commit()


def cleanup_expired_broadcast_messages(connection=None):
    close_connection = connection is None
    if connection is None:
        connection = get_auth_connection()
    now_key = current_broadcast_key()
    connection.execute(
        """
        DELETE FROM broadcast_messages
        WHERE stop_at IS NOT NULL
          AND stop_at != ''
          AND stop_at < ?
        """,
        (now_key,),
    )
    connection.commit()
    cleanup_duplicate_broadcast_messages(connection)
    if close_connection:
        connection.close()


def list_broadcast_messages(active_only: bool = False, actor=None, company: str = ""):
    connection = get_auth_connection()
    cleanup_expired_broadcast_messages(connection)
    query = """
        SELECT *
        FROM broadcast_messages
    """
    params = []
    if active_only:
        now_key = current_broadcast_key()
        query += """
            WHERE is_active = ?
              AND start_at <= ?
              AND stop_at >= ?
        """
        params.extend([1, now_key, now_key])
    query += """
        ORDER BY
            is_active DESC,
            CASE severity
                WHEN 'urgent' THEN 1
                WHEN 'warning' THEN 2
                WHEN 'info' THEN 3
                WHEN 'success' THEN 4
                ELSE 5
            END,
            start_at ASC,
            last_updated DESC,
            date_created DESC,
            id DESC
    """
    rows = connection.execute(query, params).fetchall()
    connection.close()
    if actor and is_application_admin(actor) and not active_only:
        return rows
    target_company = company
    actor_companies = []
    if actor and "company" in actor.keys():
        actor_companies = user_company_names(actor, include_primary=True)
        target_company = actor["company"]
    if actor_companies:
        return [
            row
            for row in rows
            if not decode_broadcast_companies(row["target_companies"] if "target_companies" in row.keys() else "")
            or any(broadcast_visible_to_company(row, company_name) for company_name in actor_companies)
        ]
    if target_company:
        return [row for row in rows if broadcast_visible_to_company(row, target_company)]
    if active_only:
        # Before sign-in the app cannot know a user's company. Only global
        # broadcasts are safe to show on the login page.
        return [row for row in rows if not decode_broadcast_companies(row["target_companies"] if "target_companies" in row.keys() else "")]
    return rows


def get_broadcast_message(message_id: int):
    connection = get_auth_connection()
    cleanup_expired_broadcast_messages(connection)
    row = connection.execute(
        """
        SELECT *
        FROM broadcast_messages
        WHERE id = ?
        """,
        (message_id,),
    ).fetchone()
    connection.close()
    return row


def validate_broadcast_schedule(start_at: str, stop_at: str):
    start_at = normalise_broadcast_datetime(start_at)
    stop_at = normalise_broadcast_datetime(stop_at)
    if not start_at or not stop_at:
        return "", "", "Start and stop date/time are required."
    if stop_at <= start_at:
        return start_at, stop_at, "Stop date/time must be after the start date/time."
    return start_at, stop_at, ""


def create_broadcast_message(title: str, message: str, severity: str, start_at: str, stop_at: str, is_active: bool, target_companies=None):
    title = (title or "").strip()
    message = (message or "").strip()
    severity = normalise_broadcast_severity(severity)
    start_at, stop_at, error = validate_broadcast_schedule(start_at, stop_at)
    if not title or not message:
        return "Broadcast title and message are required."
    if error:
        return error
    target_companies = normalise_broadcast_companies(target_companies)
    target_companies_value = encode_broadcast_companies(target_companies)

    connection = get_auth_connection()
    cleanup_expired_broadcast_messages(connection)
    existing = connection.execute(
        """
        SELECT id
        FROM broadcast_messages
        WHERE title = ?
          AND message = ?
          AND severity = ?
          AND COALESCE(target_companies, '') = ?
          AND start_at = ?
          AND stop_at = ?
        LIMIT 1
        """,
        (title, message, severity, target_companies_value, start_at, stop_at),
    ).fetchone()
    if existing:
        connection.execute(
            """
            UPDATE broadcast_messages
            SET is_active = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (1 if is_active else 0, existing["id"]),
        )
        connection.commit()
        connection.close()
        return ""

    connection.execute(
        """
        INSERT INTO broadcast_messages (title, message, severity, target_companies, start_at, stop_at, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (title, message, severity, target_companies_value, start_at, stop_at, 1 if is_active else 0),
    )
    connection.commit()
    connection.close()
    return ""


def update_broadcast_message(message_id: int, title: str, message: str, severity: str, start_at: str, stop_at: str, is_active: bool, target_companies=None):
    title = (title or "").strip()
    message = (message or "").strip()
    severity = normalise_broadcast_severity(severity)
    start_at, stop_at, error = validate_broadcast_schedule(start_at, stop_at)
    if not title or not message:
        return "Broadcast title and message are required."
    if error:
        return error
    target_companies = normalise_broadcast_companies(target_companies)

    connection = get_auth_connection()
    cleanup_expired_broadcast_messages(connection)
    connection.execute(
        """
        UPDATE broadcast_messages
        SET title = ?,
            message = ?,
            severity = ?,
            target_companies = ?,
            start_at = ?,
            stop_at = ?,
            is_active = ?,
            last_updated = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (title, message, severity, encode_broadcast_companies(target_companies), start_at, stop_at, 1 if is_active else 0, message_id),
    )
    connection.commit()
    connection.close()
    return ""


def set_broadcast_message_active(message_id: int, is_active: bool):
    connection = get_auth_connection()
    cleanup_expired_broadcast_messages(connection)
    connection.execute(
        """
        UPDATE broadcast_messages
        SET is_active = ?,
            last_updated = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (1 if is_active else 0, message_id),
    )
    connection.commit()
    connection.close()


def delete_broadcast_message(message_id: int):
    connection = get_auth_connection()
    connection.execute("DELETE FROM broadcast_messages WHERE id = ?", (message_id,))
    connection.commit()
    connection.close()


def get_user_for_admin(user_id: int):
    connection = get_auth_connection()
    user = connection.execute(
        """
        SELECT id, email, full_name, company, team, role, is_active, workspace_schema
        FROM users
        WHERE id = ?
        """,
        (user_id,),
    ).fetchone()
    connection.close()
    return user


def get_account_field_definition(field_id: int):
    connection = get_auth_connection()
    field = connection.execute(
        """
        SELECT *
        FROM account_field_definitions
        WHERE id = ?
        """,
        (field_id,),
    ).fetchone()
    connection.close()
    return field


def log_admin_audit(actor, action_type: str, target_type: str = "", target_label: str = "", detail: str = ""):
    connection = get_auth_connection()
    connection.execute(
        """
        INSERT INTO admin_audit_entries (
            actor_user_id,
            actor_name,
            actor_email,
            action_type,
            target_type,
            target_label,
            detail
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            actor["id"] if actor else None,
            actor["full_name"] if actor else "System",
            actor["email"] if actor else "",
            action_type,
            target_type,
            target_label,
            detail,
        ),
    )
    connection.commit()
    connection.close()


def list_admin_audit_entries(limit: int = 50):
    connection = get_auth_connection()
    rows = connection.execute(
        """
        SELECT *
        FROM admin_audit_entries
        ORDER BY date_created DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    connection.close()
    return rows


def get_admin_setting(setting_key: str, default: str = ""):
    connection = get_auth_connection()
    row = connection.execute(
        """
        SELECT setting_value
        FROM admin_settings
        WHERE setting_key = ?
        """,
        (setting_key,),
    ).fetchone()
    connection.close()
    return row["setting_value"] if row else default


def set_admin_setting(setting_key: str, setting_value: str):
    connection = get_auth_connection()
    existing = connection.execute(
        "SELECT setting_key FROM admin_settings WHERE setting_key = ?",
        (setting_key,),
    ).fetchone()
    if existing:
        connection.execute(
            """
            UPDATE admin_settings
            SET setting_value = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE setting_key = ?
            """,
            (setting_value, setting_key),
        )
    else:
        connection.execute(
            """
            INSERT INTO admin_settings (setting_key, setting_value)
            VALUES (?, ?)
            """,
            (setting_key, setting_value),
        )
    connection.commit()
    connection.close()


def audit_retention_enabled():
    return get_admin_setting("audit_retention_enabled", "0") == "1"


def cleanup_admin_audit_entries_older_than(cutoff):
    connection = get_auth_connection()
    connection.execute(
        """
        DELETE FROM admin_audit_entries
        WHERE date_created < ?
        """,
        (cutoff,),
    )
    connection.commit()
    connection.close()



def update_user_identity(user_id: int, email: str, full_name: str, team: str, company: str):
    email = normalise_email(email)
    full_name = (full_name or "").strip()
    team = (team or "").strip()
    company = normalise_company_name(company)
    if not email or not full_name or not company:
        return "Name, email and tenant are required."
    if not tenant_exists(company):
        return "Select a valid tenant."

    user = get_user_for_admin(user_id)
    if not user:
        return "User was not found."
    workspace_schema = user["workspace_schema"] if "workspace_schema" in user.keys() and user["workspace_schema"] else postgres_identifier(f"workspace_{user['email']}")

    connection = get_auth_connection()
    try:
        connection.execute(
            """
            UPDATE users
            SET email = ?,
                full_name = ?,
                company = ?,
                team = ?,
                workspace_schema = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (email, full_name, company, team, workspace_schema, user_id),
        )
        connection.commit()
        return ""
    except Exception as exc:
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            return "Another profile already uses that email address."
        raise
    finally:
        connection.close()
