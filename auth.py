import sqlite3
import os
from functools import wraps
from pathlib import Path

from flask import redirect, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash


AUTH_DB_NAME = "pipeflow_server_auth.db"
VALID_ROLES = {"admin", "manager", "user"}


def server_data_root() -> Path:
    root = Path(os.environ.get("PIPEFLOW_DATA_DIR", Path(__file__).resolve().parent / "server_data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def auth_database_path() -> Path:
    return server_data_root() / AUTH_DB_NAME


def get_auth_connection():
    connection = sqlite3.connect(auth_database_path())
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def add_column_if_missing(connection, table_name, column_name, column_definition):
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    existing_columns = [row["name"] for row in rows]
    if column_name not in existing_columns:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")


def initialise_auth_database() -> None:
    connection = get_auth_connection()
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
        cursor = connection.execute(
            """
            INSERT INTO users (email, password_hash, full_name, role, reset_phrase_hash)
            VALUES (?, ?, ?, ?, ?)
            """,
            (email, generate_password_hash(password), full_name, role, generate_password_hash(reset_phrase)),
        )
        connection.commit()
        return cursor.lastrowid, ""
    except sqlite3.IntegrityError:
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
