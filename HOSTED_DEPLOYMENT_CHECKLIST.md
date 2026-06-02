# Hosted Deployment Checklist

1. Deploy this package to the hosted Python web service.
2. Confirm `PIPEFLOW_SECRET_KEY` or `SECRET_KEY` is configured. The app can derive a fallback from `DATABASE_URL`, but an explicit secret remains preferred.
3. Confirm `DATABASE_URL` is configured for the hosted database.
4. Confirm `PIPEFLOW_NO_BROWSER=1`.
5. Start with `gunicorn app:app`.
6. Open `/health/version` after deployment and confirm version `2.0` and build `2026-06-02-v2.0-enterprise-regression-r8`.
7. Bootstrap the first Application Admin profile.
8. Create tenants from Admin > Tenant before adding company users.
