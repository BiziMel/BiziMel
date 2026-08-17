# Hosted Deployment Checklist

1. Deploy this package to the hosted Python web service.
2. Confirm `PIPEFLOW_SECRET_KEY` or `SECRET_KEY` is configured. The app can derive a fallback from `DATABASE_URL`, but an explicit secret remains preferred.
3. Confirm `DATABASE_URL` is configured for the hosted database.
4. Start with `gunicorn app:app`.
5. Open `/health/version` after deployment and confirm version `2.8.0` and build `2026-08-17-v2.8.0-ordered-bulk-rescheduling-r1`.
6. Bootstrap the first Application Admin profile.
7. Create tenants from Admin > Tenant before adding company users.
