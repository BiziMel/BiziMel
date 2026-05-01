import os
import re
import sqlite3
from pathlib import Path

try:
    import psycopg
    from psycopg.rows import dict_row
except ModuleNotFoundError:  # Local SQLite mode does not need psycopg.
    psycopg = None
    dict_row = None

from flask import has_request_context, session

DB_NAME = "pipeflow.db"
USER_TABLES = {
    "accounts",
    "contacts",
    "outreach",
    "account_partners",
    "partners",
    "partner_contacts",
    "timeline_entries",
    "user_profile",
}


def using_postgres():
    return bool(os.environ.get("DATABASE_URL"))


def sqlite_data_root():
    return Path(os.environ.get("PIPEFLOW_DATA_DIR", Path(__file__).resolve().parent / "server_data"))


def sqlite_database_path():
    data_root = sqlite_data_root()
    if has_request_context() and session.get("user_id"):
        app_folder = data_root / "users" / str(session["user_id"])
    else:
        app_folder = data_root / "system"
    app_folder.mkdir(parents=True, exist_ok=True)
    return app_folder / DB_NAME


def postgres_identifier(value):
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", str(value or "system"))
    if not cleaned or cleaned[0].isdigit():
        cleaned = f"user_{cleaned}"
    return cleaned.lower()


def current_user_schema():
    if has_request_context():
        user_email = session.get("user_email")
        if user_email:
            return postgres_identifier(f"workspace_{user_email}")
        user_id = session.get("user_id")
        if user_id:
            return postgres_identifier(f"workspace_user_{user_id}")
    return postgres_identifier("system")


def translate_sql(sql):
    translated = sql
    translated = translated.replace("?", "%s")
    translated = translated.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
    translated = translated.replace("TEXT DEFAULT CURRENT_TIMESTAMP", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    translated = translated.replace("INSERT OR IGNORE INTO", "INSERT INTO")
    translated = translated.replace("IFNULL(", "COALESCE(")
    translated = translated.replace("datetime('now', '-1 hour')", "(CURRENT_TIMESTAMP - INTERVAL '1 hour')")
    translated = translated.replace("datetime('now')", "CURRENT_TIMESTAMP")
    translated = translated.replace("date('now', '+7 days')", "(CURRENT_DATE + INTERVAL '7 days')")
    translated = translated.replace("date('now')", "CURRENT_DATE")
    return translated


def insert_table_name(sql):
    match = re.match(r"\s*INSERT\s+INTO\s+([a-zA-Z_][a-zA-Z0-9_]*)", sql, flags=re.IGNORECASE)
    if match:
        return match.group(1).lower()
    return None


class HybridRow:
    def __init__(self, data):
        self.data = dict(data)
        self.values = list(self.data.values())

    def __getitem__(self, key):
        if isinstance(key, int):
            return self.values[key]
        return self.data[key]

    def keys(self):
        return self.data.keys()

    def items(self):
        return self.data.items()

    def __iter__(self):
        return iter(self.values)

    def __repr__(self):
        return repr(self.data)


def hybrid(row):
    if row is None:
        return None
    if isinstance(row, HybridRow):
        return row
    if isinstance(row, dict):
        return HybridRow(row)
    return row


class PgCursorAdapter:
    def __init__(self, cursor, lastrowid=None):
        self.cursor = cursor
        self.lastrowid = lastrowid

    def fetchone(self):
        return hybrid(self.cursor.fetchone())

    def fetchall(self):
        return [hybrid(row) for row in self.cursor.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())

    def __getitem__(self, index):
        row = self.fetchone()
        if row is None:
            raise IndexError(index)
        if isinstance(row, dict):
            return list(row.values())[index]
        return row[index]


class PgConnectionAdapter:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, params=None):
        params = tuple(params or ())
        translated = translate_sql(sql)
        if re.search(r"\binsert\s+into\s+partners\s*\(partner_name\)[\s\S]+\bselect\b", translated, flags=re.IGNORECASE) and "on conflict" not in translated.lower():
            translated = translated.rstrip().rstrip(";") + " ON CONFLICT (partner_name) DO NOTHING"
        table = insert_table_name(translated)
        wants_lastrowid = table in USER_TABLES or table == "users"
        if wants_lastrowid and " returning " not in translated.lower() and not re.search(r"\binsert\s+into[\s\S]+\bselect\b", translated, flags=re.IGNORECASE):
            translated = translated.rstrip().rstrip(";") + " RETURNING id"

        cursor = self.connection.execute(translated, params)
        lastrowid = None
        if wants_lastrowid and cursor.description:
            row = cursor.fetchone()
            row = hybrid(row)
            if row is not None:
                lastrowid = row["id"] if hasattr(row, "keys") and "id" in row.keys() else row[0]
        return PgCursorAdapter(cursor, lastrowid)

    def cursor(self):
        return self

    def commit(self):
        self.connection.commit()

    def close(self):
        self.connection.close()


class SQLiteConnectionAdapter:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, params=None):
        return self.connection.execute(sql, tuple(params or ()))

    def cursor(self):
        return self.connection.cursor()

    def commit(self):
        self.connection.commit()

    def close(self):
        self.connection.close()


def sqlite_connection():
    connection = sqlite3.connect(sqlite_database_path())
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 5000")
    return SQLiteConnectionAdapter(connection)


def postgres_connection(schema=None):
    if psycopg is None:
        raise RuntimeError("DATABASE_URL is set but psycopg is not installed.")
    connection = psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)
    schema = schema or current_user_schema()
    with connection.cursor() as cursor:
        cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        cursor.execute(f'SET search_path TO "{schema}", public')
        cursor.execute("""
            CREATE OR REPLACE FUNCTION julianday(value text)
            RETURNS double precision
            LANGUAGE sql
            IMMUTABLE
            AS $$ SELECT EXTRACT(EPOCH FROM value::timestamp) / 86400.0 $$
        """)
        cursor.execute("""
            CREATE OR REPLACE FUNCTION strftime(format text, value text)
            RETURNS text
            LANGUAGE plpgsql
            IMMUTABLE
            AS $$
            BEGIN
                IF format = '%w' THEN
                    RETURN EXTRACT(DOW FROM value::date)::int::text;
                ELSIF format = '%Y-%m' THEN
                    RETURN to_char(value::date, 'YYYY-MM');
                END IF;
                RETURN to_char(value::timestamp, format);
            END;
            $$
        """)
        cursor.execute("""
            CREATE OR REPLACE FUNCTION date(value text, modifier text)
            RETURNS date
            LANGUAGE plpgsql
            IMMUTABLE
            AS $$
            DECLARE
                amount integer;
            BEGIN
                IF value = 'now' THEN
                    IF modifier LIKE '+% days' THEN
                        amount := split_part(substring(modifier from 2), ' ', 1)::integer;
                        RETURN CURRENT_DATE + amount;
                    ELSIF modifier LIKE '-% days' THEN
                        amount := split_part(substring(modifier from 2), ' ', 1)::integer;
                        RETURN CURRENT_DATE - amount;
                    END IF;
                    RETURN CURRENT_DATE;
                END IF;
                IF modifier LIKE '+% days' THEN
                    amount := split_part(substring(modifier from 2), ' ', 1)::integer;
                    RETURN value::date + amount;
                ELSIF modifier LIKE '-% days' THEN
                    amount := split_part(substring(modifier from 2), ' ', 1)::integer;
                    RETURN value::date - amount;
                END IF;
                RETURN value::date;
            END;
            $$
        """)
    connection.commit()
    return PgConnectionAdapter(connection)


def get_connection(schema=None):
    if using_postgres():
        return postgres_connection(schema=schema)
    return sqlite_connection()
