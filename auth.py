import sqlite3
import os
import secrets
from datetime import datetime, timedelta, timezone
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


def initialise_auth_database() -> None:
    connection = get_auth_connection()
    connection.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            is_active INTEGER DEFAULT 1,
            date_created TEXT DEFAULT CURRENT_TIMESTAMP,
            last_updated TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            used_at TEXT,
            date_created TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    connection.commit()
    connection.close()


def normalise_email(email: str) -> str:
    return (email or "").strip().lower()


def create_user(email: str, password: str, full_name: str):
    email = normalise_email(email)
    full_name = (full_name or "").strip()
    if not email or not password or not full_name:
        return None, "All fields are required."

    connection = get_auth_connection()
    try:
        existing_count = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        role = "admin" if existing_count == 0 else "user"
        cursor = connection.execute(
            """
            INSERT INTO users (email, password_hash, full_name, role)
            VALUES (?, ?, ?, ?)
            """,
            (email, generate_password_hash(password), full_name, role),
        )
        connection.commit()
        return cursor.lastrowid, ""
    except sqlite3.IntegrityError:
        return None, "An account already exists for that email address."
    finally:
        connection.close()


def find_active_user_by_email(email: str):
    connection = get_auth_connection()
    user = connection.execute(
        """
        SELECT id, email, full_name, role
        FROM users
        WHERE email = ?
          AND is_active = 1
        """,
        (normalise_email(email),),
    ).fetchone()
    connection.close()
    return user


def create_password_reset_token(email: str):
    user = find_active_user_by_email(email)
    if not user:
        return None

    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    connection = get_auth_connection()
    connection.execute(
        """
        INSERT INTO password_reset_tokens (user_id, token, expires_at)
        VALUES (?, ?, ?)
        """,
        (user["id"], token, expires_at),
    )
    connection.commit()
    connection.close()
    return token


def get_valid_password_reset_token(token: str):
    token = (token or "").strip()
    if not token:
        return None

    connection = get_auth_connection()
    row = connection.execute(
        """
        SELECT password_reset_tokens.*, users.email, users.full_name
        FROM password_reset_tokens
        JOIN users ON users.id = password_reset_tokens.user_id
        WHERE password_reset_tokens.token = ?
          AND password_reset_tokens.used_at IS NULL
          AND users.is_active = 1
        """,
        (token,),
    ).fetchone()
    connection.close()

    if not row:
        return None

    expires_at = datetime.fromisoformat(row["expires_at"])
    if expires_at < datetime.now(timezone.utc):
        return None

    return row


def reset_password_with_token(token: str, password: str):
    row = get_valid_password_reset_token(token)
    if not row:
        return "This reset link has expired or has already been used."

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
        (generate_password_hash(password), row["user_id"]),
    )
    connection.execute(
        """
        UPDATE password_reset_tokens
        SET used_at = CURRENT_TIMESTAMP
        WHERE token = ?
        """,
        (token,),
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
