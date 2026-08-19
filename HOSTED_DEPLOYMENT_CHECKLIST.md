# Hosted Deployment Checklist

1. Deploy this package to the hosted Python web service.
2. Confirm `PIPEFLOW_SECRET_KEY` or `SECRET_KEY` is configured. The app can derive a fallback from `DATABASE_URL`, but an explicit secret remains preferred.
3. Confirm `DATABASE_URL` is configured for the hosted database.
4. Start with `gunicorn app:app`.
5. Confirm `PIPEFLOW_NIGHTLY_SCHEDULER=1` and `PIPEFLOW_TIMEZONE=Europe/London` are present. They are included in `render.yaml`.
6. Keep at least one live web-service instance available so the in-service scheduler can run at 23:00.
7. Open `/health/version` after deployment and confirm version `2.8.1` and build `2026-08-19-v2.8.1-nightly-schedule-reflow-r2`.
8. Bootstrap the first Application Admin profile.
9. Create tenants from Admin > Tenant before adding company users.
10. After the first 23:00 run, confirm that administrators do not see a Nightly schedule review warning dialog. If one appears, inspect the Render service logs for `Nightly Outreach schedule`.
