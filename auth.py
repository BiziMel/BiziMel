import sqlite3
import os
from functools import wraps
from pathlib import Path

from flask import redirect, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from db_compat import get_connection, using_postgres


AUTH_DB_NAME = "pipeflow_server_auth.db"
VALID_ROLES = {"admin", "manager", "user"}
VALID_ACCOUNT_FIELD_TYPES = {"text", "number", "date", "textarea"}



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
                role TEXT DEFAULT 'user',
                reset_phrase_hash TEXT,
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
                role TEXT DEFAULT 'user',
                reset_phrase_hash TEXT,
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
    add_column_if_missing(connection, "users", "reset_phrase_hash", "TEXT")
    connection.commit()
    connection.close()


def normalise_email(email: str) -> str:
    return (email or "").strip().lower()


def create_user(email: str, password: str, full_name: str, reset_phrase: str = ""):
    email = normalise_email(email)
    full_name = (full_name or "").strip()
    reset_phrase = (reset_phrase or "").strip()
    if not email or not password or not full_name or not reset_phrase:
        return None, "All fields are required."
    if len(reset_phrase) < 12:
        return None, "Secret reset phrase must be at least 12 characters."

    connection = get_auth_connection()
    try:
        existing_count = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        role = "admin" if existing_count == 0 else "user"
        if using_postgres():
            cursor = connection.execute(
                """
                INSERT INTO users (email, password_hash, full_name, role, reset_phrase_hash)
                VALUES (?, ?, ?, ?, ?)
                RETURNING id
                """,
                (email, generate_password_hash(password), full_name, role, generate_password_hash(reset_phrase)),
            )
            row = cursor.fetchone()
            user_id = row["id"]
        else:
            cursor = connection.execute(
                """
                INSERT INTO users (email, password_hash, full_name, role, reset_phrase_hash)
                VALUES (?, ?, ?, ?, ?)
                """,
                (email, generate_password_hash(password), full_name, role, generate_password_hash(reset_phrase)),
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
        SELECT id, email, full_name, role
        FROM users
        WHERE id = ?
          AND is_active = 1
        """,
        (user_id,),
    ).fetchone()
    connection.close()
    return user


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
        if user["role"] != "admin":
            return redirect(url_for("home"))
        return view(*args, **kwargs)

    return wrapped


def list_users():
    connection = get_auth_connection()
    users = connection.execute(
        """
        SELECT id, email, full_name, role, is_active, date_created, last_updated
        FROM users
        ORDER BY full_name, email
        """
    ).fetchall()
    connection.close()
    return users


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



def get_user_for_admin(user_id: int):
    connection = get_auth_connection()
    user = connection.execute(
        """
        SELECT id, email, full_name, role, is_active
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
