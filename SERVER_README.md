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


## Password Reset Email

Password reset links are sent by SMTP. Add these environment variables in Render:

- `PIPEFLOW_PUBLIC_URL`: the public Render URL, for example `https://bizimel.onrender.com`
- `PIPEFLOW_SMTP_HOST`: SMTP server host
- `PIPEFLOW_SMTP_PORT`: SMTP server port, usually `587`
- `PIPEFLOW_SMTP_USERNAME`: SMTP username
- `PIPEFLOW_SMTP_PASSWORD`: SMTP password or app password
- `PIPEFLOW_SMTP_FROM`: sender email address
- `PIPEFLOW_SMTP_TLS`: `1` for TLS, `0` to disable

If SMTP is not configured, the reset form will not email users and will show an administrator setup message.
