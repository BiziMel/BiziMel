# PipeFlow PG Manager Server

PipeFlow PG Manager Server is the hosted, multi-user version of PipeFlow.

## Current Hosted Model

- Users register with email, password, full name and a private reset phrase.
- Supabase/Postgres is the intended hosted database.
- Authentication data is stored centrally.
- Each user gets a private workspace schema for their PipeFlow data.
- Accounts, contacts, partners, outreach, tasks, reports and PG Bible exports are isolated by user workspace.
- Outreach Tasks is the combined workspace for outreach, shared account access and task assignment.
- Account owners can share full account packages with one or more active users. The originator keeps access after sharing.
- Task assignment is saved only when the user clicks `Save Assignment`.
- Tasks can only be assigned to users who already have access to the related account.
- Account owners can revoke sharing permissions. Revoked users have assigned outreach tasks returned to the account owner.
- Account ownership can be reassigned from the edit account form. On hosted Postgres, the account package is copied to the new owner when the account is saved.
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
PORT=5070 python3 app.py
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
- release notes and core routing integrity

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
