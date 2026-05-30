# Security Validation

Validated for the hosted enterprise build:

- Mandatory `PIPEFLOW_SECRET_KEY` for hosted startup.
- CSRF validation for state-changing requests.
- Hardened session cookie configuration.
- Security headers including CSP, frame protection and content-type protection.
- Tenant-scoped user visibility for Company Admin users.
- Application Admin-only access for tenant creation and application-level controls.
- Health storage endpoint no longer exposes user email or workspace schema.
- Safer handling for user-controlled redirect targets.
