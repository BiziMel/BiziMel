import sqlite3
import os
from functools import wraps
from pathlib import Path

from flask import redirect, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash


AUTH_DB_NAME = "pipeflow_server_auth.db"


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
        cursor = connection.execute(
            """
            INSERT INTO users (email, password_hash, full_name)
            VALUES (?, ?, ?)
            """,
            (email, generate_password_hash(password), full_name),
        )
        connection.commit()
        return cursor.lastrowid, ""
    except sqlite3.IntegrityError:
        return None, "An account already exists for that email address."
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
