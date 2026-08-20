import os
import re
import sqlite3
import time
from pathlib import Path

try:
    import psycopg
    from psycopg.rows import dict_row
except ModuleNotFoundError:  # Local SQLite mode does not need psycopg.
    psycopg = None
    dict_row = None

from flask import has_request_context, session

DB_NAME = "pipeflow.db"
_POSTGRES_READY_SCHEMAS = set()
_POSTGRES_BOOTSTRAPPED = False
USER_TABLES = {
    "accounts",
    "contacts",
    "outreach",
    "outreach_recipients",
    "account_partners",
    "partners",
    "partner_contacts",
    "partner_contact_accounts",
    "sales_plays",
    "sales_play_assets",
    "account_sales_plays",
    "account_org_charts",
    "account_org_chart_people",
    "account_org_chart_connectors",
    "timeline_entries",
    "audit_entries",
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
        workspace_schema = session.get("workspace_schema")
        if workspace_schema:
            return postgres_identifier(workspace_schema)
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
    translated = re.sub(r"date\('now',\s*'\+(\d+) days'\)", r"(CURRENT_DATE + INTERVAL '\1 days')", translated, flags=re.IGNORECASE)
    translated = re.sub(r"date\('now',\s*'-(\d+) days'\)", r"(CURRENT_DATE - INTERVAL '\1 days')", translated, flags=re.IGNORECASE)
    translated = translated.replace("date('now', '+7 days')", "(CURRENT_DATE + INTERVAL '7 days')")
    translated = translated.replace("date('now')", "CURRENT_DATE")
    translated = re.sub(r"strftime\s*\(\s*'%w'\s*,\s*([^)]+)\)", r"CAST(pipeflow_strftime('%w', \1) AS INTEGER)", translated, flags=re.IGNORECASE)
    translated = re.sub(r"\bdatetime\s*\(", "pipeflow_datetime(", translated, flags=re.IGNORECASE)
    translated = re.sub(r"\bstrftime\s*\(", "pipeflow_strftime(", translated, flags=re.IGNORECASE)
    translated = re.sub(r"\bjulianday\s*\(", "pipeflow_julianday(", translated, flags=re.IGNORECASE)
    translated = re.sub(r"\bdate\s*\(", "pipeflow_date(", translated, flags=re.IGNORECASE)
    return translated


def insert_table_name(sql):
    match = re.match(r"\s*INSERT\s+INTO\s+([a-zA-Z_][a-zA-Z0-9_]*)", sql, flags=re.IGNORECASE)
    if match:
        return match.group(1).lower()
    return None


def insert_ignore_table_name(sql):
    match = re.match(r"\s*INSERT\s+OR\s+IGNORE\s+INTO\s+([a-zA-Z_][a-zA-Z0-9_]*)", sql, flags=re.IGNORECASE)
    if match:
        return match.group(1).lower()
    return None


def transient_database_error(exc):
    text = str(exc).lower()
    return any(
        marker in text
        for marker in (
            "database is locked",
            "database table is locked",
            "could not serialize access",
            "deadlock detected",
            "connection reset",
            "connection failed",
            "connection refused",
            "connection timeout",
            "timeout expired",
            "could not connect",
            "server closed the connection unexpectedly",
            "ssl connection has been closed unexpectedly",
            "the connection is closed",
            "consuming input failed",
            "terminating connection",
            "current transaction is aborted",
            "infailedsqltransaction",
        )
    )


def execute_with_retry(operation, rollback=None, attempts=3):
    delay = 0.08
    last_error = None
    for attempt in range(attempts):
        try:
            return operation()
        except Exception as exc:
            last_error = exc
            if not transient_database_error(exc) or attempt == attempts - 1:
                if rollback and transient_database_error(exc):
                    try:
                        rollback()
                    except Exception:
                        pass
                raise
            if rollback:
                try:
                    rollback()
                except Exception:
                    pass
            time.sleep(delay)
            delay *= 2
    raise last_error


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

    @property
    def rowcount(self):
        return self.cursor.rowcount

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
        ignore_table = insert_ignore_table_name(sql)
        translated = translate_sql(sql)
        if ignore_table and " on conflict " not in translated.lower():
            conflict_targets = {
                "partners": "(partner_name)",
                "teams": "(team_name)",
                "team_memberships": "(team_id, user_id)",
                "account_shared_users": "(account_id, user_id)",
                "outreach_recipients": "(outreach_id, contact_id, partner_contact_id)",
                "partner_contact_accounts": "(partner_contact_id, account_id)",
                "sales_plays": "(sales_play_title)",
                "account_sales_plays": "(account_id, sales_play_id)",
            }
            target = conflict_targets.get(ignore_table)
            if target:
                translated = translated.rstrip().rstrip(";") + f" ON CONFLICT {target} DO NOTHING"
        if re.search(r"\binsert\s+into\s+partners\s*\(partner_name\)[\s\S]+\bselect\b", translated, flags=re.IGNORECASE) and "on conflict" not in translated.lower():
            translated = translated.rstrip().rstrip(";") + " ON CONFLICT (partner_name) DO NOTHING"
        table = insert_table_name(translated)
        wants_lastrowid = table in USER_TABLES or table == "users"
        auto_returning = False
        if wants_lastrowid and " returning " not in translated.lower() and not re.search(r"\binsert\s+into[\s\S]+\bselect\b", translated, flags=re.IGNORECASE):
            translated = translated.rstrip().rstrip(";") + " RETURNING id"
            auto_returning = True

        cursor = execute_with_retry(
            lambda: self.connection.execute(translated, params),
            rollback=self.connection.rollback,
        )
        lastrowid = None
        if auto_returning and cursor.description:
            row = cursor.fetchone()
            row = hybrid(row)
            if row is not None:
                lastrowid = row["id"] if hasattr(row, "keys") and "id" in row.keys() else row[0]
        return PgCursorAdapter(cursor, lastrowid)

    def cursor(self):
        return self

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def close(self):
        self.connection.close()


class SQLiteConnectionAdapter:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, params=None):
        return execute_with_retry(lambda: self.connection.execute(sql, tuple(params or ())))

    def cursor(self):
        return self.connection.cursor()

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

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
    connection = execute_with_retry(
        lambda: psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row),
        attempts=3,
    )
    schema = schema or current_user_schema()
    with connection.cursor() as cursor:
        cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        cursor.execute(f'SET search_path TO "{schema}", public')
        cursor.execute("""
            CREATE OR REPLACE FUNCTION pipeflow_julianday(value text)
            RETURNS double precision
            LANGUAGE plpgsql
            STABLE
            AS $$
            BEGIN
                IF value = 'now' THEN
                    RETURN EXTRACT(EPOCH FROM CURRENT_TIMESTAMP) / 86400.0;
                END IF;
                IF NULLIF(value, '') IS NULL THEN
                    RETURN NULL;
                END IF;
                RETURN EXTRACT(EPOCH FROM value::timestamp) / 86400.0;
            END;
            $$
        """)
        cursor.execute("""
            CREATE OR REPLACE FUNCTION pipeflow_julianday(value timestamp)
            RETURNS double precision
            LANGUAGE sql
            IMMUTABLE
            AS $$ SELECT EXTRACT(EPOCH FROM value) / 86400.0 $$
        """)
        cursor.execute("""
            CREATE OR REPLACE FUNCTION pipeflow_julianday(value date)
            RETURNS double precision
            LANGUAGE sql
            IMMUTABLE
            AS $$ SELECT EXTRACT(EPOCH FROM value::timestamp) / 86400.0 $$
        """)
        cursor.execute("""
            CREATE OR REPLACE FUNCTION pipeflow_strftime(format text, value text)
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
            CREATE OR REPLACE FUNCTION pipeflow_strftime(format text, value timestamp)
            RETURNS text
            LANGUAGE plpgsql
            IMMUTABLE
            AS $$
            BEGIN
                IF format = '%w' THEN
                    RETURN EXTRACT(DOW FROM value)::int::text;
                ELSIF format = '%Y-%m' THEN
                    RETURN to_char(value, 'YYYY-MM');
                END IF;
                RETURN to_char(value, format);
            END;
            $$
        """)
        cursor.execute("""
            CREATE OR REPLACE FUNCTION pipeflow_strftime(format text, value date)
            RETURNS text
            LANGUAGE plpgsql
            IMMUTABLE
            AS $$
            BEGIN
                IF format = '%w' THEN
                    RETURN EXTRACT(DOW FROM value)::int::text;
                ELSIF format = '%Y-%m' THEN
                    RETURN to_char(value, 'YYYY-MM');
                END IF;
                RETURN to_char(value, format);
            END;
            $$
        """)
        cursor.execute("""
            CREATE OR REPLACE FUNCTION pipeflow_datetime(value text)
            RETURNS timestamp
            LANGUAGE plpgsql
            STABLE
            AS $$
            BEGIN
                IF value = 'now' THEN
                    RETURN CURRENT_TIMESTAMP;
                END IF;
                IF NULLIF(value, '') IS NULL THEN
                    RETURN NULL;
                END IF;
                RETURN value::timestamp;
            END;
            $$
        """)
        cursor.execute("""
            CREATE OR REPLACE FUNCTION pipeflow_datetime(value timestamp)
            RETURNS timestamp
            LANGUAGE sql
            IMMUTABLE
            AS $$ SELECT value $$
        """)
        cursor.execute("""
            CREATE OR REPLACE FUNCTION pipeflow_datetime(value date)
            RETURNS timestamp
            LANGUAGE sql
            IMMUTABLE
            AS $$ SELECT value::timestamp $$
        """)
        cursor.execute("""
            CREATE OR REPLACE FUNCTION pipeflow_datetime(value text, modifier text)
            RETURNS timestamp
            LANGUAGE plpgsql
            STABLE
            AS $$
            DECLARE
                amount integer;
                base_value timestamp;
            BEGIN
                IF value = 'now' THEN
                    base_value := CURRENT_TIMESTAMP;
                ELSIF NULLIF(value, '') IS NULL THEN
                    RETURN NULL;
                ELSE
                    base_value := value::timestamp;
                END IF;

                IF modifier LIKE '+% hour' OR modifier LIKE '+% hours' THEN
                    amount := split_part(substring(modifier from 2), ' ', 1)::integer;
                    RETURN base_value + (amount * INTERVAL '1 hour');
                ELSIF modifier LIKE '-% hour' OR modifier LIKE '-% hours' THEN
                    amount := split_part(substring(modifier from 2), ' ', 1)::integer;
                    RETURN base_value - (amount * INTERVAL '1 hour');
                ELSIF modifier LIKE '+% days' THEN
                    amount := split_part(substring(modifier from 2), ' ', 1)::integer;
                    RETURN base_value + (amount * INTERVAL '1 day');
                ELSIF modifier LIKE '-% days' THEN
                    amount := split_part(substring(modifier from 2), ' ', 1)::integer;
                    RETURN base_value - (amount * INTERVAL '1 day');
                END IF;
                RETURN base_value;
            END;
            $$
        """)
        cursor.execute("""
            CREATE OR REPLACE FUNCTION pipeflow_date(value text)
            RETURNS date
            LANGUAGE plpgsql
            IMMUTABLE
            AS $$
            BEGIN
                IF value = 'now' THEN
                    RETURN CURRENT_DATE;
                END IF;
                IF NULLIF(value, '') IS NULL THEN
                    RETURN NULL;
                END IF;
                RETURN value::date;
            END;
            $$
        """)
        cursor.execute("""
            CREATE OR REPLACE FUNCTION pipeflow_date(value timestamp)
            RETURNS date
            LANGUAGE sql
            IMMUTABLE
            AS $$ SELECT value::date $$
        """)
        cursor.execute("""
            CREATE OR REPLACE FUNCTION pipeflow_date(value date)
            RETURNS date
            LANGUAGE sql
            IMMUTABLE
            AS $$ SELECT value $$
        """)
        cursor.execute("""
            CREATE OR REPLACE FUNCTION pipeflow_date(value text, modifier text)
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
                IF NULLIF(value, '') IS NULL THEN
                    RETURN NULL;
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
        cursor.execute("""
            CREATE OR REPLACE FUNCTION pipeflow_date(value timestamp, modifier text)
            RETURNS date
            LANGUAGE plpgsql
            IMMUTABLE
            AS $$
            DECLARE
                amount integer;
                base_date date;
            BEGIN
                base_date := value::date;
                IF modifier LIKE '+% days' THEN
                    amount := split_part(substring(modifier from 2), ' ', 1)::integer;
                    RETURN base_date + amount;
                ELSIF modifier LIKE '-% days' THEN
                    amount := split_part(substring(modifier from 2), ' ', 1)::integer;
                    RETURN base_date - amount;
                END IF;
                RETURN base_date;
            END;
            $$
        """)
    connection.commit()
    return PgConnectionAdapter(connection)


_bootstrap_postgres_connection = postgres_connection


def postgres_connection(schema=None):
    global _POSTGRES_BOOTSTRAPPED
    if psycopg is None:
        raise RuntimeError("DATABASE_URL is set but psycopg is not installed.")

    schema = schema or current_user_schema()
    if not _POSTGRES_BOOTSTRAPPED:
        connection = _bootstrap_postgres_connection(schema=schema)
        _POSTGRES_BOOTSTRAPPED = True
        _POSTGRES_READY_SCHEMAS.add(schema)
        return connection

    connection = execute_with_retry(
        lambda: psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row),
        attempts=3,
    )
    with connection.cursor() as cursor:
        if schema not in _POSTGRES_READY_SCHEMAS:
            cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            _POSTGRES_READY_SCHEMAS.add(schema)
        cursor.execute(f'SET search_path TO "{schema}", public')
    connection.commit()
    return PgConnectionAdapter(connection)


def get_connection(schema=None):
    if using_postgres():
        return postgres_connection(schema=schema)
    return sqlite_connection()
