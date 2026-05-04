# PipeFlow PG Manager Server

PipeFlow PG Manager Server is the hosted, multi-user version of PipeFlow.

## Current Hosted Model

- Users register with email, password, full name and a private reset phrase.
- Supabase/Postgres is the intended hosted database.
- Authentication data is stored centrally.
- Each user gets a private workspace schema for their PipeFlow data.
- Accounts, contacts, partners, outreach, tasks, reports and PG Bible exports are isolated by user workspace.
- Admin users can manage profiles, permissions, broadcasts and password resets.

## Render Configuration

Use a Python web service.

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
gunicorn app:app
```

Required environment variables:

```text
PIPEFLOW_NO_BROWSER=1
PIPEFLOW_SECRET_KEY=<long random secret>
DATABASE_URL=<Supabase session pooler connection string>
```

Optional environment variables:

```text
PG_BIBLE_TEMPLATE_PATH=<path to uploaded PG Bible template>
PIPEFLOW_DATA_DIR=/tmp/pipeflow-server-data
```

`PG_BIBLE_TEMPLATE_PATH` is optional because the project includes:

```text
pg_bible_templates/PG Bible FY27.xlsx
```

`PIPEFLOW_DATA_DIR` is only used for local SQLite fallback and temporary export files when Supabase is enabled.

## Supabase Connection

Use the Supabase session pooler connection string for `DATABASE_URL`.

Check the deployed app after setting it:

```text
/health/storage
```

Expected hosted result:

```text
backend=supabase_postgres
database_url_configured=true
```

If it shows `temporary_sqlite`, Render is not receiving `DATABASE_URL`.

## Local Run

```bash
python3 -m pip install -r requirements.txt
PIPEFLOW_NO_BROWSER=1 PORT=5070 python3 app.py
```

Open:

```text
http://localhost:5070
```

## Smoke Test

Before packaging or uploading a new build, run:

```bash
python3 smoke_test.py
```

The smoke test creates a temporary profile and checks:

- login and registration
- dashboard
- accounts, contacts, partners and outreach pages
- task update
- reports
- CSV exports
- PG Bible Excel export

It does not touch real user data.

## Upload Guidance

Do not upload these folders or files to GitHub/Render:

```text
server_data
__pycache__
build
dist
*.db
*.sqlite
*.sqlite3
*.pyc
```

The `vendor` folder is not required for Render because dependencies are installed from `requirements.txt`.

## Password Reset

PipeFlow uses a no-email password reset flow.

During registration, each user creates a secret reset phrase. The phrase is hashed and is never stored as plain text.

If a user forgets their password, they enter their email, secret reset phrase and new password. If the phrase matches, the password is reset.

Admins can also reset passwords from Profile Administration.

## Operational Notes

- UptimeRobot can keep the free Render service warm.
- Reports are designed to avoid database-specific date calculations where possible.
- PG Bible export uses the bundled template and writes a single Excel sheet named after the user profile.
- Database indexes are created automatically during workspace initialisation.
