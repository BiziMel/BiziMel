# Hosted Deployment Checklist

## Nightly Outreach scheduler

The nightly review is a dedicated Render background worker, not a request-time feature of the web service. In Render, sync the Blueprint or create the `pipeflow-nightly-scheduler` worker defined in `render.yaml`, then deploy both services. The worker must use the same `DATABASE_URL` as the web service and these environment values:

```text
PIPEFLOW_NIGHTLY_SCHEDULER=1
PIPEFLOW_DISABLE_INPROCESS_SCHEDULER=1
PIPEFLOW_REQUIRE_SHARED_DATABASE=1
PIPEFLOW_TIMEZONE=Europe/London
```

The worker and web service must have the exact same `DATABASE_URL`. Render's `sync: false` means this value must be entered for both services; it is not automatically copied between them. The worker now stops loudly if the shared database value is missing instead of silently writing scheduler history to a private SQLite database.

Confirm the worker log contains `Dedicated nightly Outreach scheduler worker started` with `database_backend=postgres` and recurring `scheduler heartbeat` messages. The web service endpoint `/health/version` reports the last claimed run date and status; the Admin scheduler history shows the completed or failed run for the last 30 days. A message saying no runs are recorded means the worker has not been created, is stopped, has a different `DATABASE_URL`, or has not yet completed its first due run.

1. Deploy this package to the hosted Python web service.
2. Confirm `PIPEFLOW_SECRET_KEY` or `SECRET_KEY` is configured. The app can derive a fallback from `DATABASE_URL`, but an explicit secret remains preferred.
3. Confirm `DATABASE_URL` is configured for the hosted database.
4. Start with `gunicorn app:app`.
5. Confirm `PIPEFLOW_NIGHTLY_SCHEDULER=1` and `PIPEFLOW_TIMEZONE=Europe/London` are present. They are included in `render.yaml`.
6. Deploy the `pipeflow-nightly-scheduler` Render worker from `render.yaml`. It runs `scheduler_worker.py` continuously and is the authoritative 23:00 scheduler process.
7. Keep `PIPEFLOW_NIGHTLY_SCHEDULER=1` on the web service as the guarded fallback watchdog, with `PIPEFLOW_TIMEZONE=Europe/London`.
8. Open `/health/version` after deployment and confirm version `2.10.0`, build `2026-09-18-v2.10.0-scheduler-readable-errors-r8`, `nightly_scheduler_mode=dedicated_worker_expected`, and the latest run date/status. PostgreSQL deployments default the guarded web fallback on unless `PIPEFLOW_NIGHTLY_SCHEDULER=0` is explicitly set.
9. Bootstrap the first Application Admin profile.
10. Create tenants from Admin > Tenant and configure each accepted work email suffix including `@` (for example `@example.com`) before inviting company users.
11. Check Admin > Permissions & Controls for Profile Requests. Unmatched email domains remain pending until an Application Admin assigns a company and approves or rejects the request.
12. Create a test user from Admin, record the one-time generated temporary password, and confirm the account is held on Complete First Login until the user replaces it and sets a private secret phrase.
13. After the first 23:00 run, confirm that Application Admins do not see a Nightly schedule review warning dialog. If one appears, inspect the Render worker logs for `Nightly Outreach schedule`, then use Confirm to acknowledge that specific failed run. A stale Running run is automatically recoverable after 15 minutes.
14. Open Admin > Permissions & Controls and verify the read-only Nightly Scheduler History table records the run for the last 30-day period.
15. Open Admin > Deleted Records and verify deletion summaries show record type, record ID, primary fields, actor, reason and timestamp.
