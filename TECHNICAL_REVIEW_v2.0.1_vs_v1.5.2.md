# PipeFlow Technical Review: v2.0.1 Against Solution Design v1.5.2

Review date: 2026-06-03
Reviewed design: `PipeFlow_Solution_Design_v1.5.2.docx`
Reviewed implementation: PipeFlow hosted enterprise package `v2.0.1`

## Executive Summary

The current implementation remains aligned with the v1.5.2 design at the architectural level: Flask server-rendered routes, SQLite/Supabase compatibility, hosted Render deployment, account/contact/outreach/partner/PG Progress/reporting workflows, account sharing, admin controls and audit-led governance are still the core product shape.

The main differences are feature evolution since v1.5.2, especially tenant administration, stronger hosted security, richer AI/Execution Insights, multi-contact outreach, due-date bulk editing and time-aware task status. One functional gap was found and fixed in v2.0.1: overdue follow-up counts were not using one consistent rule across the dashboard, account AI Insights and task reports.

## Differences From v1.5.2

### Release and Administration

- v1.5.2 described release grouping by major and minor families such as `1.5`. The current implementation uses release entries for `2.0.1`, `2.0`, `1.4`, `1.3`, `1.2`, `1.1` and `1.0` in a latest-first release notes view.
- v1.5.2 described admins managing profiles, permissions, broadcasts and audit settings. The current implementation adds explicit Application Admin and Company Admin roles, tenant creation, tenant-scoped user management and company-bounded sharing/assignment controls.
- v1.5.2 described the first hosted enterprise profile as an initial admin only implicitly. The current User Guide now states that the first hosted enterprise profile becomes the initial Application Admin and later profiles are created from Admin.

### Security and Tenancy

- v1.5.2 documented per-user workspace schemas and server-side access checks. The current implementation extends this with mandatory company tenants, tenant registry pages, company-scoped admin controls and same-company assignment/share lists.
- v1.5.2 documented secure sessions and profile-level password reset by secret phrase. Current 2.0 adds CSRF validation, security headers, hardened session cookie settings and safer redirect handling.

### Dashboard and AI Insights

- v1.5.2 documented the Insights Dashboard as weekly command metrics, outcome breakdown, wrap-up and execution learning. Current 2.0.1 uses a command centre plus Execution Insights, combining AI Insight account/contact/partner signals and Campaign Learning patterns.
- Current 2.0.1 insight criteria prioritise executive coverage and PG success outcomes. NBM Booked is weighted as the strongest success signal, followed by Discovery Booked and executive meeting outcomes.
- v1.5.2 did not define one precise overdue rule. Before 2.0.1, current code had multiple overdue definitions: date-only dashboard counts, time-aware account AI counts and inconsistent closed-status filtering. v2.0.1 now uses one shared rule: open task, valid Activity Due Date, due time defaulting to end of day when blank, and due datetime before current application time.
- v2.0.1 excludes Closed, Completed and Cancelled tasks from overdue counts, active execution counts, AI Insights, account health and task SLA reporting.

### Outreach and Campaign Logic

- v1.5.2 documented campaign generation, non-working-date avoidance and VITO-first behavior. Current implementation still supports those behaviours and adds time-slot scheduling inside working hours, duplicate slot avoidance, bulk due-date updates and task table due-date controls.
- v1.5.2 stated later email-style activity uses Follow-up or Email. Current 2.0 release notes say later email-style generated steps use Follow-up with a follow-up email subject.
- Current implementation supports multi-contact outreach association on manual tasks, including add, edit, view and delete cleanup paths, which is an evolution beyond the v1.5.2 wording.

### Reporting and PG Bible

- v1.5.2 documented account, contact, outreach, task, partner and PG Bible reporting. Current implementation remains aligned and adds stronger task SLA reporting by assignee.
- v1.5.2 documented Outreach Reports latest outreach and outcome exports. The current dashboard removed redundant latest outreach from the main dashboard, but report routes remain the reporting location.
- v2.0.1 aligns Task Reports overdue calculations with Dashboard and AI Insights.

### User Guidance

- v1.5.2 documented the product shape in a standalone design document. Current implementation uses in-app guide sections rendered from `USER_GUIDE_SECTIONS`, plus page-specific guidance from `PAGE_INSTRUCTIONS`.
- v2.0.1 updates the guide to explain time-aware overdue counts, AI Insight refresh behavior, closed/completed/cancelled exclusion and current 2.0.1 release behavior.

## Resolved Issue in v2.0.1

AI Insights could show overdue follow-ups that did not match the dashboard Overdue Actions card because the app was calculating overdue work through separate definitions. The fix centralizes overdue status through shared helpers and applies them to:

- Dashboard Overdue Actions and Follow-ups Due.
- Account AI Insights and account health.
- Accounts list and account detail metrics.
- Campaign Learning overdue scoring.
- Task Reports and SLA by assignee.

## Residual Notes

- The solution design should be revised for the 2.0 family because tenant administration, Application Admin versus Company Admin, CSRF/security headers, multi-contact outreach and Execution Insights are now first-class behaviours.
- The current package folder name still contains `v2.0_2026-06-02_enterprise_r8_full`; internal runtime metadata now reports `2.0.1`.
- Generated release zips should be rebuilt after deployment validation so the archive filename also reflects 2.0.1.
