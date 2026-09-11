# Hosted Deployment Checklist

1. Deploy this package to the hosted Python web service.
2. Confirm `PIPEFLOW_SECRET_KEY` or `SECRET_KEY` is configured. The app can derive a fallback from `DATABASE_URL`, but an explicit secret remains preferred.
3. Confirm `DATABASE_URL` is configured for the hosted database.
4. Start with `gunicorn app:app`.
5. Confirm `PIPEFLOW_NIGHTLY_SCHEDULER=1` and `PIPEFLOW_TIMEZONE=Europe/London` are present. They are included in `render.yaml`.
6. Keep at least one live web-service instance available so the in-service scheduler can run at 23:00.
7. Open `/health/version` after deployment and confirm version `2.9.2`, build `2026-09-11-v2.9.2-postgres-session-fix-r3`, and that both scheduler values are `True`.
8. Bootstrap the first Application Admin profile.
9. Create tenants from Admin > Tenant and configure each accepted work email suffix including `@` (for example `@example.com`) before inviting company users.
10. Check Admin > Permissions & Controls for Profile Requests. Unmatched email domains remain pending until an Application Admin assigns a company and approves or rejects the request.
11. Create a test user from Admin, record the one-time generated temporary password, and confirm the account is held on Complete First Login until the user replaces it and sets a private secret phrase.
12. After the first 23:00 run, confirm that Application Admins do not see a Nightly schedule review warning dialog. If one appears, inspect the Render service logs for `Nightly Outreach schedule`, then use Confirm to acknowledge that specific failed run.
13. Open Admin > Permissions & Controls and verify the read-only Nightly Scheduler History table records the run for the last 30-day period.
