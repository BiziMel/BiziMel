# PipeFlow Server

PipeFlow Server is the hosted, multi-user version of PipeFlow.

## What Changed

- Users create a PipeFlow Server profile with email, password and full name.
- Each user gets a separate private PipeFlow database under `server_data/users/<user_id>/pipeflow.db`.
- The login database is stored at `server_data/pipeflow_server_auth.db`.
- Existing PipeFlow screens, reports and exports run against the signed-in user's private database.
- The app runs on `PORT` for hosted environments.

This first server version keeps SQLite because it can run without a paid database service. For a larger team, the next step would be PostgreSQL with row-level ownership.

## Local Run

```bash
python3 -m pip install -r requirements.txt
PIPEFLOW_NO_BROWSER=1 PORT=5070 python3 app.py
```

Open:

```text
http://localhost:5070
```

Create a profile, then use PipeFlow normally.

## Deployment Notes

Set these environment variables on the host:

- `PORT`: provided by the host, for example Render
- `PIPEFLOW_SECRET_KEY`: a long random secret string
- `PIPEFLOW_NO_BROWSER=1`
- `PIPEFLOW_DATA_DIR`: persistent folder for the auth database and per-user PipeFlow databases
- `PG_BIBLE_TEMPLATE_PATH`: optional path to the PG Bible template file if exports are enabled

The host must provide persistent storage for the `server_data` folder, otherwise user data will be lost when the app restarts or redeploys.

On Render free web services, `/tmp` is temporary. This is useful for a first launch test, but not for long-term storage. For real use, add a Render disk and set `PIPEFLOW_DATA_DIR` to that mounted disk path.

## Privacy Model

PipeFlow Server uses one application with one login database, but each user has a separate PipeFlow database file. This keeps accounts, contacts, outreach, partners, tasks, reports and PG Bible exports isolated by user.

## Current Limitation

This is suitable for a small hosted proof of concept. For production team use, move the data layer to PostgreSQL and enforce ownership with database-level constraints and route-level checks.


## Password Reset

PipeFlow Server uses a no-email password reset flow. During registration, each user creates a secret reset phrase. The phrase is hashed and is never stored as plain text.

If a user forgets their password, they enter their email, secret reset phrase and new password. If the phrase matches, the password is reset. Admins can still reset passwords manually from Profile Administration.


## Supabase/Postgres Persistence

When `DATABASE_URL` is set, PipeFlow Server stores authentication in Supabase/Postgres and creates a private Postgres schema for each user workspace. This keeps Admin profile management separate from user PipeFlow data.

Required Render variable:

- `DATABASE_URL`: Supabase Session pooler connection string

With Supabase enabled, `PIPEFLOW_DATA_DIR` is no longer used for primary application data. It can remain set harmlessly for local fallback behavior.
