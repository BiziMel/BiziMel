import sys
import os
from pathlib import Path
import csv
import io
import re
import traceback
import json
import secrets
import hashlib
from datetime import date, datetime, time, timedelta
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Flask, render_template, request, redirect, url_for, Response, send_file, session, abort
from werkzeug.utils import secure_filename
from auth import authenticate_user, create_user, current_user, initialise_auth_database, login_required, admin_required, list_users, reset_user_password, set_user_active, set_user_role, reset_password_with_phrase, update_current_user_secret_phrase, list_account_field_definitions, create_account_field_definition, update_account_field_definition, set_account_field_active, list_admin_audit_entries, log_admin_audit, get_user_for_admin, get_account_field_definition, ensure_user_workspace_schema, update_user_identity, list_broadcast_messages, create_broadcast_message, update_broadcast_message, set_broadcast_message_active, get_broadcast_message, delete_broadcast_message, active_team_for_user, list_active_team_members, list_active_team_invites, create_team_invite, list_assignable_users, audit_retention_enabled, set_admin_setting, cleanup_admin_audit_entries_older_than, get_auth_connection, is_application_admin, is_company_admin, same_company, list_tenants, create_tenant, update_tenant, user_count
from database import get_db_connection, initialise_database
from dropdown_values import DROPDOWN_VALUES
from db_compat import using_postgres, current_user_schema, get_connection as get_schema_connection, execute_with_retry


APP_VERSION = "2.3.3"
APP_RELEASE_DATE = "2026-06-15"
APP_BUILD = "2026-06-15-v2.3.3-pg-progress-partner-multi-account-r1"

CSRF_SESSION_KEY = "_csrf_token"
LOGIN_ATTEMPTS = {}
RESET_ATTEMPTS = {}
RATE_LIMIT_WINDOW_SECONDS = 15 * 60
MAX_AUTH_ATTEMPTS = 8

try:
    APP_TIMEZONE = ZoneInfo(os.environ.get("PIPEFLOW_TIMEZONE", "Europe/London"))
except ZoneInfoNotFoundError:
    APP_TIMEZONE = ZoneInfo("UTC")

RELEASE_NOTES = [
    {
        "version": "2.3.3",
        "release_date": "2026-06-15",
        "title": "Contact-level PG RAG and partner multi-account relationships",
        "new": [],
        "enhanced": [
            "Partner contacts can now support multiple customer accounts through a supported-account selection panel.",
            "Partner relationship tables on partner, account and report views are generated from partner contact supported-account data.",
        ],
        "fixed": [
            "Changed PG Progress account RAG to aggregate from active contact RAG only, while each contact keeps its own red, amber or green status.",
            "Inactive contacts no longer contribute to account-level PG Progress RAG status.",
            "Kept scheduled meeting date/time hidden unless a meeting outcome is selected.",
            "Removed visible partner account relationship add fields from the partner form and replaced them with a status table.",
        ],
    },
    {
        "version": "2.3.2",
        "release_date": "2026-06-15",
        "title": "PG Progress alignment, outreach assignment and partner relationship cleanup",
        "new": [],
        "enhanced": [
            "Changed account Partner Involvement into a table sourced from partner contacts linked to the account, showing account, partner account, partner contact and relationship status.",
            "PG Progress partner rows now show partner contact names with job titles and group partner activity by partner account.",
            "Boxed the Execution Insights page content and reduced viewport margins so daily guidance sits within the screen more cleanly.",
        ],
        "fixed": [
            "Moved PG Progress action headings into each grouped account/sales-play table so headings align to the visible columns.",
            "Extended PG Progress RAG scoring to use Discovery Meeting and NBM Meeting dropdown values as well as outreach outcomes.",
            "Removed unassigned choices from outreach creation, campaign generation and reassignment flows, defaulting new tasks to the signed-in user.",
            "Merged scheduled meeting date and time into one datetime field and only shows it for meeting outcomes.",
            "Centred table headings, enlarged and centred RAG dots, and differentiated PG Progress job title colour from contact names.",
        ],
    },
    {
        "version": "2.3.1",
        "release_date": "2026-06-15",
        "title": "PG Progress table restoration and dot-only RAG display",
        "new": [],
        "enhanced": [
            "Changed every PG Progress RAG presentation to a small filled colour dot with no text label.",
            "Simplified PG Progress contact rows to show only contact name and job title.",
            "Suppressed empty Business Org grouping rows unless the row is partner activity.",
        ],
        "fixed": [
            "Restored the PG Progress action table columns for the editable dropdowns plus the Last 7 Days Activity and Next Planned Actions columns.",
        ],
    },
    {
        "version": "2.3.0",
        "release_date": "2026-06-15",
        "title": "Execution insight clarity and grouped PG Progress RAG view",
        "new": [
            "Changed PG Progress into a grouped view by account, business org and sales play.",
            "Added PG Progress RAG status for accounts based on outreach response outcomes.",
        ],
        "enhanced": [
            "Execution Insights now names account, contact and outreach subjects for untouched accounts, no-contact accounts, overdue outreach and no-response campaign activity.",
            "PG PLAN now displays PG RAG instead of NBM target numbers while keeping the PG Bible export mapping unchanged.",
        ],
        "fixed": [
            "Removed the NBM target number column from the PG Progress action view without changing PG Bible output.",
        ],
    },
    {
        "version": "2.2.4",
        "release_date": "2026-06-15",
        "title": "Admin table layout, account-specific Daily Focus and default account ownership",
        "new": [],
        "enhanced": [
            "Expanded Daily Focus into more account-specific rows that explain why each account needs attention and how the action should drive booked meetings or new-business progress.",
            "Defaulted the Add Account owner dropdown to the signed-in user while preserving reassignment to another eligible user.",
            "Improved Admin user permissions table spacing so profile details, roles and access controls fit without overlapping.",
        ],
        "fixed": [
            "Changed Admin user permissions created dates to numeric dd-mm-yyyy display.",
            "Shortened Admin user access buttons into compact two-line labels to avoid cramped table controls.",
        ],
    },
    {
        "version": "2.2.3",
        "release_date": "2026-06-12",
        "title": "Org chart drag recovery, richer insights, durable report metrics and profile phrase control",
        "new": [
            "Added user-owned secret phrase changes from the signed-in Profile page.",
        ],
        "enhanced": [
            "Expanded Execution Insights with more company, contact, relationship and campaign learning rows.",
            "Reworked Account, Contact and Outreach report breakdowns into native metric sections that render without external chart scripts.",
            "Changed Admin user permissions from cards to a table with clickable user rows that open editable profile controls.",
            "Daily Focus now falls back to actual account names from the workspace when no due-action or success account is available.",
        ],
        "fixed": [
            "Fixed the org chart tile drag regression by adding pointer-based drag support for profile and canvas tiles.",
        ],
    },
    {
        "version": "2.2.2",
        "release_date": "2026-06-08",
        "title": "Insights focus, report resilience, org chart placement and account logos",
        "new": [
            "Added JPG and PNG customer logo upload and replacement on account records.",
            "Show customer logos beside account names on the account page and account table.",
        ],
        "enhanced": [
            "Improved Account, Contact and Outreach report summary cards with clearer visual hierarchy and live data.",
            "Updated Daily Focus guidance to name the referenced accounts and use cleaner meeting/action pluralisation.",
            "Added multi-contact outreach badges so the first contact is shown with a +x count for additional recipients.",
            "Changed the user profile secret phrase reveal into a dialog that remains open until dismissed.",
        ],
        "fixed": [
            "Removed Outcome Breakdown from the Insights page.",
            "Hardened Contact Reports by forcing schema readiness before loading the report or export.",
            "Fixed org chart drag behaviour so a dragged contact is hidden from the left tray immediately and restored only if the drag is abandoned.",
            "Fixed org chart staged relationship comparisons for newly placed tiles so connector lines render as soon as tiles are linked.",
            "Kept org chart snapping to an invisible row and column grid while removing the visible grid background.",
        ],
    },
    {
        "version": "2.2.1",
        "release_date": "2026-06-08",
        "title": "Login, reporting polish, org chart stability and account/contact field fixes",
        "new": [
            "Added separate Office and Mobile phone fields for contacts.",
            "Added own-profile secret phrase reveal for phrases stored from this release onward.",
        ],
        "enhanced": [
            "Improved Account, Contact and Outreach report metrics into clearer visual summary cards.",
            "Moved report filters below metrics and above report tables.",
            "Changed account owner selection to a tenancy-scoped user dropdown on account create and edit.",
            "Merged Next 24 Hours guidance into the Execution Insights section as the lead focus paragraph.",
            "Standardised displayed dates and times toward dd-Mmm-yyyy and 24-hour hh:mm formats across updated report and dashboard views.",
            "Improved database commit resilience around new account creation.",
        ],
        "fixed": [
            "Fixed login Bad Request handling caused by stale or missing security tokens.",
            "Fixed the critical internal server error path when saving a new account.",
            "Removed the org chart Arrange Chart button and retained grid-based placement without a visible grid.",
            "Fixed org chart tray hiding and relationship line rendering for newly placed and moved tiles.",
            "Removed the Build Campaign button from Execution Insights.",
        ],
    },
    {
        "version": "2.2.0",
        "release_date": "2026-06-08",
        "title": "Reports simplification, richer insights, org chart cleanup and PG Bible mapping",
        "new": [],
        "enhanced": [
            "Enhanced Outreach Reports into a single accurate outreach activity view that defaults to the last 7 days and supports wider date filtering.",
            "Enhanced Account and Contact Reports with visible metric cards above the charts and detail tables.",
            "Enhanced Execution Insights, Weekly Wrap Up and Next 24 Hours with richer account, contact, activity and PG week guidance.",
            "Enhanced tenant administration so the primary contact is selected from users in a dropdown.",
            "Enhanced PG Progress and PG Bible next action mapping so multi-contact outreach appears for every selected person.",
            "Replaced the PG Bible template with the May 2026 workbook mapping.",
        ],
        "fixed": [
            "Fixed org chart connectors so linked tiles render as plain relationship lines rather than arrows.",
            "Fixed org chart tile removal so each tile has a compact X control in the top-right corner.",
            "Removed the unnecessary moved-profile staging section from the org chart labels area.",
            "Removed duplicate Task Reports navigation and redirects the old task report routes to Outreach Reports.",
        ],
    },
    {
        "version": "2.1.6",
        "release_date": "2026-06-05",
        "title": "Dashboard drill-through, tenant administration and resilience improvements",
        "new": [],
        "enhanced": [
            "Enhanced Admin tenancy so Application Admins and Company Admins can maintain tenant status and primary contact details.",
            "Enhanced Weekly Wrap Up and Next 24 Hours guidance so each shows the applicable date or date range.",
            "Enhanced Insights Dashboard metrics so cards open the matching filtered data view.",
            "Enhanced database execution resilience with transient retry handling and reduced dashboard write commits.",
            "Enhanced Reports latest outreach so it shows all outreach from the user's current working week.",
        ],
        "fixed": [
            "Fixed the dashboard broadcast ticker to scroll upward one full message at a time.",
            "Fixed Outreach task row colouring so rows stay white until due date/time has expired, then turn red.",
            "Fixed org chart relationship rendering so linked tiles draw visible connector lines in every border direction.",
            "Fixed org chart tile initials, tile text fit and export/print framing.",
        ],
    },
    {
        "version": "2.1.5",
        "release_date": "2026-06-05",
        "title": "Outreach lifecycle hardening, org chart readability and richer execution guidance",
        "new": [
            "Added the 10-day Completed outreach reopen window before records are automatically moved to the system-only Closed status.",
            "Added system closure handling so Closed records can be viewed and reported but cannot be modified or manually selected from status dropdowns.",
        ],
        "enhanced": [
            "Enhanced Weekly Wrap Up into a conversational paragraph with the covered date range and a Friday 15:00 refresh point.",
            "Enhanced Next 24 Hours focus with Discovery, NBM, executive-route and Lead-to-contact conversion signals.",
            "Enhanced Execution Insights with activity outcome, activity type, age-open and comment-quality guidance by account and contact engagement.",
            "Enhanced org chart arrangement, tile sizing and export/print output for cleaner hierarchy pillars and readable tiles.",
        ],
        "fixed": [
            "Fixed bulk Outreach delete handling so dependent cleanup does not leave PostgreSQL transactions in an aborted state.",
            "Fixed org chart tray behaviour so a contact appears either in the available list or on the chart pane, not both.",
            "Fixed org chart relationship lines for side-by-side and border-linked tiles.",
            "Removed Activity Start Date from the Outreach table because the full activity detail remains available inside the record.",
        ],
    },
    {
        "version": "2.1.3",
        "release_date": "2026-06-04",
        "title": "Execution Insights restoration and weekly strategic guidance",
        "new": [
            "Added Weekly Wrap Up guidance, refreshed each Friday from the past week's execution and success signals.",
            "Added Next 24 Hours guidance, refreshed daily from midnight to direct deliberate PG focus for the next day.",
        ],
        "enhanced": [
            "Rebuilt Execution Insights so current accounts, contacts, outreach, overdue work, outcomes and campaign learning generate practical PG guidance.",
            "Hardened dashboard insight generation so one learning query cannot blank the full Insights Dashboard.",
            "Enhanced the org chart with fixed-size snap tiles, relationship lines, staged tray removal and print/PDF or PNG export controls.",
            "Enhanced the org chart with an Arrange Chart control for cleaner hierarchy pillars and readable row alignment.",
            "Enhanced Outreach Tasks so the activity title is the first column and opens the outreach form directly.",
            "Enhanced the Outreach Tasks table to fit the page more cleanly, with due date and assignment moved to the end columns and a sticky bulk action bar.",
            "Enhanced Weekly Wrap Up and Next 24 Hours guidance into conversational paragraphs instead of bullet lists.",
        ],
        "fixed": [
            "Fixed the Severity 1 dashboard regression where Execution Insights could be replaced by the dashboard refresh fallback message.",
            "Fixed bulk Outreach delete and table due-date update handling so stale cleanup or logging records do not produce an internal server error.",
            "Fixed Release Notes 2.1.3 formatting so it renders in the correct release structure.",
            "Fixed Outreach add and edit forms so only contacts for the selected account are rendered into the page.",
            "Fixed Activity Type dropdowns on Outreach create and amend forms so dynamic partner values such as Partner: Capgemini (GOSI) no longer appear.",
            "Changed Activity Outcome from No Response Yet to No Response while preserving compatibility with existing records.",
            "Renamed Week Ahead Focus to Next 24 Hours, changed it to a daily refresh and kept Weekly Wrap Up closed until opened.",
        ],
    },
    {
        "version": "2.1.2",
        "release_date": "2026-06-04",
        "title": "Enterprise dashboard restoration, single-pane org chart and PG contact activity rules",
        "new": [],
        "enhanced": [
            "Enhanced the account org chart into a single-pane drag-and-drop canvas with border-based relationship placement and organisation labels.",
            "Enhanced Outreach contact selection styling so multi-contact checkboxes and names are aligned and easier to scan.",
            "Enhanced PG Progress and PG Bible outputs so contacts with no open outreach and no activity in more than 30 days are hidden until new activity is created.",
            "Enhanced PG Progress and PG Bible next action fields so contacts with no open activity show No next action set.",
        ],
        "fixed": [
            "Fixed the Insights Dashboard fallback path so command-centre metrics, outcome breakdown and execution insights continue to populate if one dashboard query fails.",
            "Fixed account table Org Chart labelling and added a clearer visual separation between Org Chart and Website links.",
            "Fixed org chart profile tiles to remove source/contact-type labels and show only name, role and organisation/business unit when populated.",
        ],
    },
    {
        "version": "2.1.1",
        "release_date": "2026-06-03",
        "title": "Enterprise outreach contact filtering and campaign scheduling fixes",
        "new": [],
        "enhanced": [
            "Preserved PipeFlow PG Manager branding for the hosted enterprise build.",
            "Enhanced campaign scheduling so VITO is the first touch per contact and later steps can vary based on learned successful activity patterns.",
            "Enhanced BMC Relationship with the Lead value everywhere the shared relationship dropdown is used.",
            "Enhanced account pages with a contact table showing uploaded photos and linked contact names.",
            "Enhanced partner selection on account pages with persistent checkboxes and selected partner tiles.",
            "Enhanced contact records so photos can be uploaded or replaced, viewed on contact/account/org chart surfaces and printed in a visual contact sheet.",
        ],
        "fixed": [
            "Fixed Outreach creation and edit forms so the contact picker only shows contacts associated to the selected account.",
            "Fixed Campaign Builder contact selection so only contacts associated to the selected account are visible and selectable.",
            "Fixed campaign generation so tasks created on the submit date are not scheduled earlier than the campaign submit time.",
            "Fixed dashboard metric cards so command-centre values render as zero rather than blank if a refresh path returns an empty value.",
        ],
    },
    {
        "version": "2.0.1",
        "release_date": "2026-06-03",
        "title": "Accurate refreshed AI insights and current user guidance",
        "new": [
            "Added a technical review note comparing the current 2.0.1 implementation with the previously documented 1.5.2 solution design.",
        ],
        "enhanced": [
            "Enhanced dashboard, account, task-report and campaign-learning overdue calculations so every page refresh recalculates from current data and the configured application timezone.",
            "Enhanced AI Insight and Campaign Learning criteria so executive coverage, Discovery Booked and NBM Booked outcomes are prioritised as pipeline generation success signals.",
            "Enhanced the User Guide so dashboard, Outreach Tasks, Reports and Release Notes guidance reflects the 2.0.1 workflow.",
            "Enhanced version metadata, deployment health output and deployment checklist references for the 2.0.1 release.",
        ],
        "fixed": [
            "Fixed AI Insights showing a different number of overdue follow-ups than the dashboard Overdue Actions card by using one shared overdue action rule.",
            "Fixed cancelled outreach tasks being counted as active overdue work in several dashboard and reporting queries.",
        ],
    },
    {
        "version": "2.0",
        "release_date": "2026-05-29",
        "title": "Tenant registry and company-scoped administration",
        "new": [
            "Added Application Admin-only Tenant administration for creating company tenancies with Company Name, Country and Company contact.",
            "Added Company Admin access for administrators who manage users, data and permissions only inside their associated tenant.",
        ],
        "enhanced": [
            "Enhanced active navigation tabs so Insights Dashboard and every primary app tab use the same active-tab colour behaviour.",
            "Enhanced Outreach task RAG status so future tasks remain green, tasks turn amber only on their due date, and tasks turn red one second after the due date and time expires in the application timezone.",
            "Enhanced Outreach contact selection into a closed checkbox dropdown that supports multiple contacts and click-outside closing.",
            "Enhanced Outreach contact details so every selected contact appears as a separate row in a framed details panel below the contact field.",
            "Enhanced Outreach forms so an account must be selected before contacts are presented, and only contacts associated with that selected account are available.",
            "Enhanced Outreach Tasks so users can update individual activity due dates directly from the table.",
            "Enhanced Outreach Tasks with bulk due-date updates for selected outreach activities.",
            "Enhanced the Outreach Tasks table spacing so due-date controls are collapsed by default and the table uses a wider scrollable layout to avoid field overlap.",
            "Moved Release Notes into the header action stack directly below User Guide.",
            "Enhanced user administration so tenant assignment is selected from preconfigured companies rather than typed as free text.",
            "Enhanced tenancy security so every user must have a tenant and company admins only see their own company in company controls.",
            "Enhanced sharing and assignment user lists so they remain inside the signed-in user's company tenancy.",
            "Enhanced Admin permission guidance to explain Application Admin and Company Admin responsibilities.",
            "Enhanced hosted security with CSRF validation, hardened session cookies, security headers, mandatory deployment secret configuration and safer redirect handling.",
        ],
        "fixed": [
            "Restored multi-contact association on manual Outreach tasks, including add, edit, view and delete cleanup paths.",
            "Restored Outreach activity outcomes for NBM Booked, Discovery Booked and Exec Meeting Booked.",
            "Fixed intermittent bulk Outreach delete server errors by using one explicit bulk action route and skipping stale selected task IDs safely.",
            "Fixed hosted Outreach delete resilience by refreshing the tenant schema safely before single or bulk delete cleanup runs.",
            "Fixed Role and Access updates so Application Admins can amend any user type, including their own administrator profile and other Application Admins.",
        ],
    },
    {
        "version": "1.4",
        "release_date": "2026-05-14",
        "title": "Partner activity, contact org charts and outreach scheduling refinement",
        "new": [
            "Added partner activity into PG Progress as a separate partner row when activity has occurred against an account.",
            "Added admin contact archiving for inactive contacts by date range from Admin with CSV export support from reports.",
            "Added editable account contact org charts so customer and partner contacts can be mapped by business organisation, department and reporting relationship.",
        ],
        "enhanced": [
            "Enhanced Outreach so account partners are clearly identified in the activity selection and only appear when linked to the selected account.",
            "Enhanced create outreach and campaign pages so the Open contact button is compact and only appears after a contact is selected.",
            "Enhanced Outreach Tasks so the contact job title appears on its own row beneath the contact name.",
            "Enhanced outreach activity values so White Paper and Webinar also includes Consensus.",
            "Enhanced outreach outcomes with Webinar Attended and Consensus Viewed.",
            "Enhanced PG Progress so partner activity is labelled clearly against the associated account.",
            "Enhanced PG Progress so the discovery contact cell is limited to company, business/org, department, contact name and job title.",
            "Enhanced account org charts with drag-and-drop row placement so users can arrange people horizontally as peers or vertically by hierarchy without relationship dropdowns.",
            "Enhanced manual Outreach scheduling so non-working dates and times warn on save and allow the user to confirm or return to the field.",
        ],
        "fixed": [
            "Restored a single PipeFlow logo in the header.",
            "Cleaned PG Progress so the discovery contact cell shows only the person name and job title without extra contact detail clutter.",
        ],
    },
    {
        "version": "1.3",
        "release_date": "2026-05-13",
        "title": "Partner activity, contact archiving and outreach execution cleanup",
        "new": [
            "Added partner activity into PG Progress so recent partner updates against an account appear alongside other account activity.",
            "Added admin contact archiving for inactive contacts by date range from Admin, with CSV export also available from Contact Reports.",
            "Added admin bulk contact deletion from Admin so admins can select and permanently delete contact records from a dedicated page.",
            "Added Partner Reports to show partner account coverage, engagement status and partner contact coverage.",
            "Added account org charts so customer and partner contacts can be viewed by business organisation or unmapped group.",
        ],
        "enhanced": [
            "Enhanced partner contacts so they can be edited directly from the partner record.",
            "Enhanced partner contact tiles by removing the separate LinkedIn button and keeping the tile focused on the editable contact record.",
            "Enhanced partner forms by removing next action fields from partner contacts and account relationships.",
            "Enhanced outreach activity type selection so account partners appear as selectable partner activities only when linked to the selected account.",
            "Enhanced create contact so Account Business Unit or Org only appears when the selected account has a value.",
            "Enhanced standalone outreach creation so Account is placed before Sales Play or Initiative and sales play suggestions only show plays previously used on the selected account.",
            "Enhanced Outreach Tasks with light green, amber and red due-date row shading as due dates approach or expire.",
            "Enhanced Campaign Builder contact selection from tiles into a table that only presents contacts associated to the selected account.",
            "Enhanced closed, completed and cancelled outreach tasks so they can no longer be modified or reassigned.",
            "Enhanced outreach and campaign creation with compact Open buttons that appear only after a contact is selected.",
            "Enhanced Accounts so Account Tier is the primary ordering field and PG Plan number is shown beneath it.",
            "Enhanced tables so blank Business Org values are not displayed.",
            "Enhanced Outreach forms and task rows so contact job title, phone, email and LinkedIn appear as system fields.",
            "Enhanced AI Insight and Campaign Learning so activity updates, human behaviour and account behaviour influence recommended engagement moves instead of replaying raw notes.",
            "Enhanced contacts with an Active or Inactive status.",
            "Enhanced Contacts with compact filters for account, contact name and status.",
            "Enhanced PG Progress with Business Org context, Exec First and NBM Completed columns, wider layout and cleaner Last 7 Days activity text.",
            "Enhanced PG Progress so partner activity appears as its own partner row and Yes or No fields also support N/A.",
            "Enhanced Admin contact archiving so admins open a dedicated archive page from Admin, filter inactive contacts by date range, select records and export CSV.",
            "Enhanced Outreach partner activity selection so account partners are clearly labelled and only available for the selected account.",
            "Enhanced Outreach creation and editing so partner contacts linked to the selected account can be selected as outreach recipients while the activity remains associated to the account.",
            "Enhanced PG Progress so outreach activity raised against linked partner contacts appears as partner activity against the associated account.",
            "Enhanced Profile data deletion so profile fields are cleared without deleting account-owned workspace records.",
        ],
        "fixed": [
            "Removed partner role capture where partner type already explains the partner category.",
            "Improved form tabbing flow by keeping key fields ordered left to right and top to bottom in updated forms.",
            "Fixed Contact Reports table spacing to reduce cramped and overlapping text.",
            "Fixed Contacts table layout so the table uses the full page width and far-right columns remain visible.",
            "Fixed PG Actions table alignment so the wider PG Progress fields fit the page more cleanly.",
            "Fixed Edit Outreach so partner activity options are loaded correctly and the edit page opens without an internal server error.",
        ],
    },
    {
        "version": "1.2",
        "release_date": "2026-05-13",
        "title": "Outreach task table presentation improvements",
        "new": [],
        "enhanced": [
            "Enhanced the Outreach Tasks table so due date, due time and task status display in a cleaner compact layout.",
            "Enhanced Outreach Activity forms so the contact selector only shows contacts associated to the selected account.",
            "Enhanced Campaign Builder so multiple contact selection is constrained to contacts associated with the selected account.",
            "Enhanced Insights Dashboard so execution guidance focuses on Campaign Learning success and failure indicators plus AI Insight engagement recommendations from account and contact context.",
            "Enhanced the Accounts page with a cleaner streamlined table layout for PG order, account detail, health, coverage, pipeline and location.",
            "Enhanced campaign autoscheduling so the first email step is VITO and later email-style steps use the single Follow-up activity type with the subject describing the follow-up channel.",
            "Enhanced Outreach and Campaign Builder cleanup by requiring FY and Quarter before save, removing duplicate follow-up activity values, flattening Outreach task grouping, moving account sharing to Accounts and compacting Outreach filters.",
        ],
        "fixed": [
            "Fixed Outreach Tasks table grouping so records display as a flat sortable table and open sorted by Activity Due Date from earliest to latest.",
        ],
    },
    {
        "version": "1.1",
        "release_date": "2026-05-08",
        "title": "Outreach ownership, sharing and task assignment controls",
        "new": [],
        "enhanced": [
            "Enhanced Outreach Tasks so task-level reassignment now requires an explicit Save Assignment button before the database is updated.",
            "Enhanced account collaboration so the account originator keeps visibility when an account package is shared with other users.",
            "Enhanced account sharing rules so tasks can only be assigned to users who already have access to the related account.",
            "Enhanced account ownership so each account records an owner by default and the edit account form can transfer ownership to another active user.",
            "Enhanced sharing management so account owners can revoke shared access and assigned outreach tasks are returned to the account owner.",
            "Enhanced task responsibility reporting so SLA-style task measures are grouped by assigned user.",
            "Enhanced Outreach filters with a compact status menu for All Open, All Closed, All and individual statuses including Cancelled.",
            "Enhanced Outreach sharing controls so account sharing fields are smaller and easier to scan.",
            "Enhanced the User Guide so account ownership, sharing, assignment and status filtering instructions reflect the current workflow.",
            "Enhanced the User Guide with more detailed navigation guidance and clearer admin-only access explanations.",
            "Enhanced broadcasts so login messages and dashboard ticker items are ordered by urgency, with a more compact login page presentation.",
            "Enhanced audit management so all audit trails are consolidated on the Audit page, grouped by month, filterable by date and user, exportable to CSV by admins and governed by an audited 6-month retention toggle.",
            "Enhanced admin navigation by moving Audit into Admin as an admin-only sub tab with clearer admin-only explanation.",
            "Enhanced admin navigation with a Broadcast Messages sub tab so admins can jump directly to broadcast configuration.",
            "Enhanced audit auto-delete controls so admins clearly see and select Auto-delete On or Auto-delete Off.",
            "Enhanced the Audit user filter so user suggestions display full names only while still matching underlying audit email fields.",
            "Enhanced dashboard development with the PG Progress tab for the PG Goals dashboard build.",
            "Enhanced account records with NBM Target and Account Sales Play or Initiative fields to support PG Goals dashboard mapping.",
            "Enhanced the main dashboard by removing the embedded tasks table so task work remains focused in Outreach Tasks.",
            "Enhanced PG Progress so target numbering maps to Account PG Bible Order and PG Actions includes last 7 days outreach activity updates by account.",
            "Enhanced PG Progress and made it available to all signed-in users.",
            "Enhanced Outreach so Sales Play or Initiative is now the campaign grouping field and the separate Campaign Name field is no longer shown on forms, dashboards or reports.",
            "Enhanced Outreach Tasks so Activity Update is mandatory before saving, Notes is retained as read-only system metadata and follow-on creation opens a clean new task form.",
            "Enhanced PG Progress last 7 days activity so each activity update is shown on its own line with the submitted date.",
            "Enhanced PG Progress so the PG Sales Play or Initiative column maps to Outreach task Sales Play or Initiative values for each account.",
            "Enhanced PG Progress last 7 days activity display so valid activity updates render cleanly and empty accounts stay blank.",
            "Enhanced Campaign Builder so generated outreach tasks leave Activity Update blank for the user to complete before saving.",
            "Enhanced PG Progress so Next Action and Notes is now a read-only view of scheduled Outreach task subjects due in the next 7 days.",
            "Enhanced the main dashboard into Insights Dashboard with needs-attention signals merged into Execution Insights, outcome breakdown moved under the top metrics and redundant latest outreach removed.",
            "Enhanced PG Progress activity rules so Last 7 Days Activity shows only completed activity updates and scheduled actions include overdue open work plus the next 7 days.",
            "Enhanced Outreach task pages by simplifying the table, reordering key fields and renaming Content and Thought Leadership activity to White Paper / Webinar.",
            "Enhanced Outreach Reports so Monthly Meeting Conversion is shown as meetings booked each month.",
            "Enhanced Outreach so Activity Update is only mandatory when a task is being completed, closed or cancelled.",
            "Enhanced account partner linking so multiple partner organisations can be associated to an account at once.",
            "Enhanced PG Bible mapping so NBM Target and Related NBM Target use the account PG Bible Order.",
            "Enhanced Outreach Tasks so the task table uses one row per task and shows Activity Start Date in its own column.",
            "Improved grouped table colour hierarchy so top-level groups use the darkest shade, nested groups step down progressively and detail rows remain light.",
            "Improved Release Notes ordering so the latest release always appears first.",
            "Improved profile audit entries so profile changes display clear field labels in the audit trail.",
            "Enhanced on-page instructions across PipeFlow so every page now gives clearer guidance about what to do, what matters and what to check before saving.",
            "Enhanced the Edit Outreach button so the edit form opens correctly with non-working date guidance available.",
            "Enhanced the audit auto-delete off control so saving the off state is explicit and visibly confirmed.",
            "Enhanced PG Progress hosted database compatibility so recent activity date filtering works correctly on Supabase Postgres.",
        ],
        "fixed": [
            "Fixed the Outreach Tasks table so the assignment field is clearly labelled and the Save and Edit buttons stack cleanly in the task row.",
            "Fixed the Outreach Tasks assignment controls so Save and Edit sit side by side beneath the assigned user field.",
        ],
    },
    {
        "version": "1.0",
        "release_date": "2026-05-07",
        "title": "Initial PipeFlow PG Manager release",
        "new": [
            "Introduced the hosted PipeFlow PG Manager application with private user profiles, sign in, registration and profile-level data separation.",
            "Added core workspace modules for Dashboard, Accounts, Contacts, Partners, Outreach, Tasks, Reports, Global Search, Profile and Audit.",
            "Added account tiering, PG Bible ordering and FY PG target tracking from account Pipeline Target USD ACV values.",
            "Added Campaign Builder for one sales play per campaign, with campaign generation across multiple contacts on the selected account.",
            "Added campaign learning signals that use historic outcomes, sales play, account industry, account details and selected contact data to guide generated outreach.",
            "Added profile working hours and non-working date configuration to guide campaign auto-scheduling.",
            "Added Shared Outreach and Team foundations so users can review team follow-up ownership and reassign shared outreach tasks.",
            "Added partner organisation tracking, partner contacts and account-partner relationship mapping.",
            "Added admin permissions, user management, broadcast messages and visible broadcast ticker messaging.",
            "Added full audit trail capture for workspace record changes, including date and time, user, field, old value and new value.",
            "Added PG Bible export support and report exports for accounts, contacts, outreach and tasks.",
        ],
        "enhanced": [
            "Refined the Dashboard into a pipeline generation command centre with FY PG target, weekly execution metrics, execution insights and task visibility.",
            "Aligned Dashboard Tasks with the Outreach table layout so task and outreach records have a consistent structure.",
            "Improved Outreach ordering by account, sales play and earliest activity due date while keeping the table ungrouped on the Dashboard.",
            "Made Activity Due Date visually prominent in Outreach and Dashboard task views.",
            "Improved Outreach completion so users must add an Activity Update before closing work.",
            "Improved follow-on activity flow so completed outreach opens a prefilled new outreach form instead of silently creating the next task.",
            "Improved Outreach filters with multi-select status filtering and a default All Open view.",
            "Improved auto-scheduling so generated campaign tasks avoid non-working dates, stay inside working hours and avoid duplicate time slots.",
            "Improved non-working date management so users can configure multiple unavailable date blocks while weekends are excluded by default.",
            "Improved Shared Outreach privacy so other users' full names only appear in assignment and share dropdowns.",
            "Improved account collaboration so users can share a full account package, including account details, contacts and outreach tasks, with another team member.",
            "Improved Release Notes with an accordion layout so older entries can stay collapsed as the product history grows.",
            "Improved table usability by making primary record fields act as obvious edit buttons.",
            "Improved Campaign Builder so users can only build campaigns against accounts that already have contacts, while still supporting multiple selected contacts.",
            "Improved contact creation by showing the selected account business unit or organisation.",
            "Improved account, contact, partner, outreach and task table readability to keep content inside page margins.",
            "Improved edit flows with clear save and cancel options, plus complete-only and complete-with-follow-on options for outreach tasks.",
        ],
        "fixed": [
            "Resolved duplicate-route and endpoint risks by validating route integrity during release checks.",
            "Resolved SQLite and Supabase/Postgres compatibility issues, including date/time SQL translation problems.",
            "Resolved persistence issues by moving hosted data storage to Supabase/Postgres instead of temporary SQLite.",
            "Resolved PG Bible export configuration and report route failures identified during hosted testing.",
            "Resolved recurring malformed SQL and indentation risks through compile and smoke-test validation.",
            "Resolved overly large or unclear delete controls by only showing bulk delete actions after records are selected.",
            "Resolved Outreach campaign generation issues where dates could start before the configured campaign start date.",
            "Resolved dashboard and Outreach table layout problems where tables could overflow or become too compressed.",
        ],
    }
]

USER_GUIDE_SECTIONS = [
    {
        "slug": "getting-started",
        "title": "Getting Started",
        "summary": "Set up your profile, understand navigation and get your first workspace ready.",
        "access": "All signed-in users can use the standard navigation. Admin appears only for Application Admin and Company Admin users, and Audit is available inside Admin as an admin-only sub tab.",
        "navigation": [
            "Use the top navigation from left to right as your normal workflow: Dashboard, Outreach Tasks, Accounts, Contacts, Partners, Reports, Profile and Release Notes.",
            "Use the User Guide link in the top right whenever you need help without leaving the application structure.",
            "Use the global search field in the header when you know the account, contact, partner, campaign or outreach text you want to find.",
            "Use Sign Out as the final navigation option when you have finished working.",
        ],
        "steps": [
            "The first hosted enterprise profile is registered as the initial Application Admin. After that, profiles are created by an administrator from Admin.",
            "Sign in with the email address assigned to your tenant user profile.",
            "Open Profile and confirm your full name, team, job title and working hours.",
            "Add any non-working date blocks so generated campaigns avoid those days.",
            "Create accounts first, add contacts to those accounts, then create outreach tasks or generate campaigns.",
            "Review Dashboard and Reports regularly to check execution progress and accountability.",
        ],
        "tips": [
            "Your workspace data is private unless you explicitly share an account through Outreach Tasks.",
            "Use the global search field when you know the account, contact, partner or outreach text you are looking for.",
            "If a menu item is missing, it is normally because your profile does not have permission for that function.",
            "Every user must belong to a company tenant before they can use the application.",
        ],
    },
    {
        "slug": "dashboard",
        "title": "Dashboard",
        "summary": "Use the dashboard as your weekly pipeline execution command centre.",
        "navigation": [
            "Dashboard is the first tab and should be your starting point each day.",
            "Click a dashboard task to open the editable outreach task when more detail is needed.",
            "Use dashboard metrics to decide whether to move into Accounts, Outreach Tasks or Reports next.",
        ],
        "steps": [
            "Review the command centre metrics for this week.",
            "Use Overdue Actions to see open outreach tasks whose Activity Due Date and due time have passed.",
            "Use Follow-ups Due to see open follow-ups due through the next 7 days, including overdue work.",
            "Use PG Success This Week to track Discovery Booked, NBM Booked, Exec Meeting Booked and legacy Meeting Booked outcomes.",
            "Use the pipeline target card to see total PG target ACV across your accounts.",
            "Open Weekly Wrap Up below the metrics to review the latest Friday-generated success and risk summary.",
            "Open Next 24 Hours below the metrics to review the daily strategic focus for the immediate work window.",
            "Work active outreach tasks directly from the dashboard task table.",
            "Use Execution Insights to decide which account, campaign or sales play needs attention next.",
            "Update task status and due dates as work progresses so the dashboard stays accurate.",
        ],
        "tips": [
            "Untouched accounts are accounts with no active campaign or outreach tasks.",
            "Completed, Closed and Cancelled work is removed from active execution views, overdue counts and AI Insights; Completed work can still be reopened for 10 days.",
            "AI Insights are recalculated on every dashboard refresh from current account, contact, partner, outreach, outcome and due-date data.",
            "Insights prioritise executive coverage and PG conversion. NBM Booked is treated as the strongest success signal, followed by Discovery Booked and executive meeting outcomes.",
            "Weekly Wrap Up is refreshed each Friday from 15:00 and covers the previous 7 days.",
            "Next 24 Hours is refreshed daily from midnight and overwrites the previous focus guidance.",
            "Overdue logic is time-aware. A blank due time is treated as end of day.",
            "Pipeline generated value should be treated as a source-system metric when it belongs in SFDC rather than PipeFlow.",
        ],
    },
    {
        "slug": "accounts",
        "title": "Accounts",
        "summary": "Create account records that drive pipeline tracking, contact mapping and PG Bible output.",
        "access": "All users can manage accounts in their workspace. Only the account owner can share that account, revoke access or view account sharing assignments.",
        "navigation": [
            "Open Accounts from the navigation when you need to create, cleanse or review account planning data.",
            "Click the account name in the table to open the account record.",
            "Use the Back to Accounts button from an account record to return to the list.",
        ],
        "steps": [
            "Add an account with account name, business organisation, industry, geography and website.",
            "Set Account Tier to 1, 2 or 3 for prioritisation.",
            "Set PG Bible Order when the account must appear in a specific sequence in exports.",
            "Enter Pipeline Target USD ACV so the Dashboard can calculate total PG target value.",
            "Review or reassign the Account Owner on the edit account form when ownership changes.",
            "Open an account record to review contacts, partner involvement, outreach history and timeline entries.",
            "Use Org Chart from the account table or account record to build a single-pane stakeholder map for that account.",
            "Drag each account contact onto the org chart pane once. Drop on the top, bottom, left or right border of another tile to create the hierarchy and draw the relationship arrow.",
            "Add organisation or business-unit labels directly on the org chart pane when a chart needs free-text grouping.",
            "Use Account Sharing on the account record to review and revoke access if you own the account.",
        ],
        "tips": [
            "Use business organisation to distinguish large accounts with multiple internal groups.",
            "Keep PG Bible order numeric and unique for your most important accounts.",
            "Org chart tiles show the contact photo, name, role and organisation or business unit when populated.",
            "The org chart only offers contacts associated to the selected account, and each contact can appear on the chart once.",
            "Changing ownership is stronger than sharing because ownership rights move to the new owner.",
        ],
    },
    {
        "slug": "contacts",
        "title": "Contacts",
        "summary": "Capture stakeholder detail for account coverage and campaign targeting.",
        "navigation": [
            "Open Contacts when you need to add, review or clean stakeholder information.",
            "Click the contact name to open the contact record.",
            "Use the account link from a contact when you need to return to the wider account context.",
        ],
        "steps": [
            "Add contacts from the Contacts page or from an account context.",
            "Select the account before entering stakeholder details.",
            "Capture job title, organisation, relationship, responsibilities and personal context where known.",
            "Upload or replace the contact photo from the contact edit form when a current profile image is available.",
            "Print a contact from the contact record when you need a visual contact sheet; blank fields are excluded from the print output.",
            "Use contact data to make campaign recommendations more accurate over time.",
            "Keep contact records current when a stakeholder changes role, leaves or becomes more important to the sales play.",
        ],
        "tips": [
            "Accounts must have at least one contact before Campaign Builder can generate a campaign.",
            "BMC Relationship includes Lead for stakeholders who are leading the account, opportunity or sales motion.",
            "Richer contact notes improve future sales play recommendations.",
            "Do not store sensitive personal data that is not relevant to legitimate business outreach.",
        ],
    },
    {
        "slug": "outreach",
        "title": "Outreach Tasks",
        "summary": "Track campaign touchpoints, task status, outcomes, account sharing, assignment and next activity updates.",
        "access": "All users can work their own outreach tasks. Only account owners can share accounts, revoke account access or see account sharing assignments.",
        "navigation": [
            "Open Outreach Tasks when you need to filter, update, assign or review outreach execution.",
            "Use Campaign Builder from the Outreach Tasks page when you want PipeFlow to generate a sequence.",
            "Click Edit Outreach on a row to open the task form.",
            "Use Clear Filters if the table does not show the tasks you expect.",
        ],
        "steps": [
            "Use Add Outreach for one-off activity or Campaign Builder for generated sequences.",
            "Select the account first so the Contacts dropdown only shows customer and partner contacts associated to that account.",
            "Use the Share Full Account panel to copy an account package to one or more users and record their access.",
            "Group outreach by account and campaign to understand execution context.",
            "Use the Assigned To dropdown in each row and click Save Assignment to commit task ownership.",
            "Use the compact status filter to show All Open, All Closed, All or specific statuses.",
            "Add an Activity Update before closing or completing an outreach task.",
            "Use Complete and Create Follow-on when the current task is done but another task is needed.",
        ],
        "tips": [
            "The due date is the Activity Due Date, based on the next action date.",
            "The Contacts dropdown supports multiple contacts; the first selected contact remains the primary report contact while all selected recipients are retained against the outreach task.",
            "Due-date colouring is time-aware: future work is green, work due today is amber, and overdue open work is red after the due date and time have passed.",
            "Tasks can only be assigned to users who have access to the related account.",
            "Completed, Closed and Cancelled outreach is hidden unless you explicitly filter for it. Completed records can be reopened for 10 days before the system moves them to Closed.",
            "If a user is missing from the assignment dropdown, check that the account has been shared with them first and that they belong to the same company tenant.",
        ],
    },
    {
        "slug": "campaign-builder",
        "title": "Campaign Builder",
        "summary": "Generate four-week outreach campaigns from a single sales play.",
        "navigation": [
            "Open Campaign Builder from the Outreach Tasks page.",
            "Return to Outreach Tasks after generation to review the created task rows.",
            "Use Reports later to compare campaign activity and outcomes.",
        ],
        "steps": [
            "Choose an account that already has contacts.",
            "Select one or more contacts for the campaign.",
            "Enter one sales play only.",
            "Set PG Week, campaign start and campaign end dates.",
            "Set the total outreach task quantity and how many times per week activities should occur.",
            "Generate the campaign to create outreach tasks across the selected contacts.",
            "Review the generated dates and assignee before beginning execution.",
        ],
        "tips": [
            "Generated campaigns avoid weekends and your configured non-working dates.",
            "Tasks are placed inside your working hours and avoid duplicate time slots where possible.",
            "Generated campaign tasks will not start earlier than the campaign submit time.",
            "The first email-style touch per contact is VITO. Later email-style tasks are generated as Email or Follow-up activity based on learned success patterns so the sequence is less repetitive.",
            "Campaign learning favours historic success signals, with NBM Booked carrying the strongest weighting and Discovery Booked also treated as a key PG success outcome.",
            "If no account appears, add at least one contact to the account first.",
        ],
    },
    {
        "slug": "shared-outreach",
        "title": "Sharing and Assignment",
        "summary": "Share full accounts and reassign outreach tasks from the Outreach Tasks page while preserving privacy.",
        "access": "Only the account owner can share, revoke or see account sharing assignments. Task assignees can see and update tasks only when they have access to the related account.",
        "navigation": [
            "Use Outreach Tasks for sharing and assignment. There is no separate Shared Outreach tab.",
            "Use the Share Full Account panel to grant access.",
            "Use Manage Existing Sharing or the Account Sharing panel on an account record to revoke access.",
        ],
        "steps": [
            "Open Outreach Tasks from the top navigation.",
            "Use Share Full Account to copy an account, contacts, outreach tasks and account details to one or more users.",
            "Use Sharing Permissions to revoke access when a user no longer needs the account.",
            "Use the Assigned To dropdown and Save Assignment button in the task table to reassign work.",
            "Review active follow-up tasks grouped by customer and campaign.",
            "If access is revoked, tasks assigned to that user return to the account owner.",
        ],
        "tips": [
            "Other users' full names are only displayed in Outreach Tasks assignment and share dropdowns when tenancy rules allow them to be visible.",
            "Sharing and assignment remain inside the company tenant; users in another company cannot be selected.",
            "Sharing copies the full account package into the selected user's workspace while the originator retains their own access.",
            "Revoking an account share moves any tasks assigned to that user back to the account owner.",
            "Use sharing for collaboration. Use ownership reassignment only when responsibility for the account itself changes.",
        ],
    },
    {
        "slug": "partners",
        "title": "Partners",
        "summary": "Track partner organisations, partner contacts and account involvement.",
        "navigation": [
            "Open Partners when you need to manage partner organisations and their contacts.",
            "Click the partner name to open the partner record.",
            "Use account mappings inside the partner record to connect a partner to customer accounts.",
        ],
        "steps": [
            "Create partner organisations with type, location, website, managers and notes.",
            "Add partner contacts who work for the partner organisation.",
            "Map partner contacts and partner involvement to accounts where they help progress opportunities.",
            "Review partner metrics and account links from the partner record.",
            "Keep partner manager and BMC partner manager fields current so ownership is clear.",
        ],
        "tips": [
            "Partner contacts are separate from account contacts and use partner-specific role fields.",
            "Use partner notes to capture channel context and next actions.",
            "Partner account mappings help explain who is helping sell into a customer account.",
        ],
    },
    {
        "slug": "reports",
        "title": "Reports and PG Bible",
        "summary": "Review execution data and export account, contact, outreach and PG Bible outputs.",
        "navigation": [
            "Open Reports from the main navigation, then select the report type you need.",
            "Use Back to Reports from report pages to return to the report menu.",
            "Use exports when you need to review or share data outside PipeFlow.",
        ],
        "steps": [
            "Open Reports from the top navigation.",
            "Use Account Reports to review account coverage and target values.",
            "Use Contact Reports to review stakeholder coverage.",
            "Use Outreach Reports to review activity volume, outcomes, due dates and ownership. It defaults to the last 7 days and can be widened with filters.",
            "Export PG Bible when you need the formatted workbook output.",
            "Use filters before exporting when the report supports narrowing by date, account, status or assignee.",
        ],
        "tips": [
            "Reports reflect the same fields used across account, contact and outreach views.",
            "PG Bible uses account target and ordering fields configured in the account form.",
            "PG Progress and PG Bible hide contacts with no active engagement for more than 30 days when they also have no open outreach.",
            "If a contact has no open activity but remains visible, the next activity field shows No next action set.",
            "PG Progress and PG Bible include open next actions from multi-contact outreach for every selected contact.",
        ],
    },
    {
        "slug": "profile",
        "title": "Profile and Scheduling",
        "summary": "Configure user details, working hours and non-working dates.",
        "navigation": [
            "Open Profile from the main navigation when your user details or scheduling availability changes.",
            "Use the non-working date section to add multiple unavailable blocks.",
            "Return to Outreach or Campaign Builder after updating scheduling settings.",
        ],
        "steps": [
            "Set full name, team and job title.",
            "Set work day start and end times.",
            "Add multiple non-working date blocks for holidays, travel or unavailable periods.",
            "Delete outdated non-working blocks when they no longer apply.",
            "Review these settings before using Campaign Builder because auto-scheduling uses them.",
        ],
        "tips": [
            "Saturday and Sunday are non-working by default for auto-scheduling.",
            "Manual scheduling can still override warnings for non-working dates or times.",
            "Your full name is used in assignment fields, audit entries and ownership records.",
        ],
    },
    {
        "slug": "admin",
        "title": "Admin",
        "summary": "Manage tenants, users, permissions and broadcasts when signed in as an administrator.",
        "access": "Admin forms are visible to Application Admin and Company Admin users. Application Admins manage all tenants and application controls. Company Admins manage only users and permissions inside their own company.",
        "navigation": [
            "Admin appears near the end of the navigation only for users with administration access.",
            "Use Admin for user creation, tenant assignment, role changes, access changes and profile administration.",
            "Application Admins use the Tenant sub tab to create company tenancies before users are assigned to that company.",
            "Application Admins use the Broadcast Messages sub tab inside Admin to create, pause, edit or delete user messages.",
            "Use the Audit Trail sub tab inside Admin to review administrative and data-change history.",
        ],
        "steps": [
            "Open Admin from the top navigation when available.",
            "As an Application Admin, open Tenant and create the company tenancy with Company Name, Country and Company contact.",
            "Return to Permissions & Controls and use Create User Profile to create users against a preconfigured company tenant.",
            "For Application Admins, choose any configured tenant from the Company dropdown when creating or editing a user profile.",
            "For Company Admins, the Company dropdown contains only their own company and cannot be used to move a user to another tenant.",
            "Use Role to assign User, Manager, Company Admin or Application Admin. Only Application Admins can assign Application Admin.",
            "Review user profiles and update tenant, role, team or email when required.",
            "Deactivate users who should no longer access PipeFlow.",
            "Create broadcast messages with start and stop times for login and dashboard announcements when signed in as an Application Admin.",
            "Use admin password reset only after confirming the request with the user.",
        ],
        "tips": [
            "Admin actions are recorded in the admin audit trail.",
            "Application Admin should be limited to a small trusted group so there is no single point of failure.",
            "Company Admins cannot see another tenant, another tenant's users or another tenant's company values.",
            "Only admins can access Admin, including its Audit Trail sub tab.",
            "If a user cannot see an admin form, check their role before troubleshooting the page.",
        ],
    },
    {
        "slug": "audit-release-notes",
        "title": "Audit and Release Notes",
        "summary": "Review change history and understand what has changed between releases.",
        "access": "Audit is an admin-only sub tab inside Admin. Release Notes are visible to all users so everyone can understand what changed.",
        "navigation": [
            "Open Admin from the navigation, then use the Audit Trail sub tab.",
            "Open Release Notes from the navigation to see product changes.",
            "Use the accordion controls to expand older release entries when needed.",
        ],
        "steps": [
            "Open Audit as an admin to review structured workspace changes.",
            "Review date/time, user, action, record, field, old value and new value.",
            "Open Release Notes to see changes grouped by version.",
            "Use the accordion layout to keep older releases collapsed while the latest release stays open.",
            "Use release categories to understand whether a change is New, Enhanced or Fixed.",
        ],
        "tips": [
            "Release Notes always display latest to earliest.",
            "Profile changes use readable field labels in the audit trail.",
            "Audit is for accountability and investigation, not everyday task management.",
        ],
    },
]


for vendor_base in (
    Path(getattr(sys, "_MEIPASS", Path(__file__).parent)),
    Path(__file__).parent,
    Path(sys.executable).resolve().parent.parent / "Resources",
):
    local_vendor = vendor_base / "vendor"
    if local_vendor.exists():
        vendor_path = str(local_vendor)
        if vendor_path not in sys.path:
            sys.path.insert(0, vendor_path)


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = Path(__file__).parent

    return Path(base_path) / relative_path


app = Flask(
    __name__,
    template_folder=resource_path("templates"),
    static_folder=resource_path("static")
)
def configured_secret_key():
    explicit_secret = os.environ.get("PIPEFLOW_SECRET_KEY") or os.environ.get("SECRET_KEY")
    if explicit_secret:
        return explicit_secret

    database_url = os.environ.get("DATABASE_URL", "")
    if database_url:
        return hashlib.sha256(f"pipeflow-session:{database_url}".encode("utf-8")).hexdigest()

    render_identity = os.environ.get("RENDER_SERVICE_ID") or os.environ.get("RENDER_INSTANCE_ID")
    if render_identity:
        return hashlib.sha256(f"pipeflow-render-session:{render_identity}".encode("utf-8")).hexdigest()

    if os.environ.get("RENDER"):
        return secrets.token_urlsafe(64)

    return "pipeflow-local-dev-secret-change-me"


app.config["SECRET_KEY"] = configured_secret_key()
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get(
    "PIPEFLOW_COOKIE_SECURE",
    "1" if using_postgres() or os.environ.get("RENDER") else "0",
) == "1"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=12)

initialise_auth_database()


def csrf_token():
    token = session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def validate_csrf_token():
    expected = session.get(CSRF_SESSION_KEY)
    submitted = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    if not expected or not submitted or not secrets.compare_digest(expected, submitted):
        abort(400, description="Invalid or missing security token.")


def csrf_token_is_valid():
    expected = session.get(CSRF_SESSION_KEY)
    submitted = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    return bool(expected and submitted and secrets.compare_digest(expected, submitted))


def format_display_date(value, month_name=True):
    if not value:
        return ""
    if isinstance(value, datetime):
        parsed = value.date()
    elif isinstance(value, date):
        parsed = value
    else:
        text = str(value).strip()
        parsed = None
        for fmt, width in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%dT%H:%M", 16), ("%Y-%m-%d", 10)):
            try:
                parsed = datetime.strptime(text[:width], fmt).date()
                break
            except ValueError:
                continue
        if parsed is None:
            return text
    return parsed.strftime("%d-%b-%Y" if month_name else "%d-%m-%Y")


def format_display_time(value):
    if not value:
        return ""
    text = str(value).strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text[:len(fmt)], fmt).strftime("%H:%M")
        except ValueError:
            continue
    return text


def combined_contact_phone(office_phone="", mobile_phone="", legacy_phone=""):
    parts = []
    if office_phone:
        parts.append(f"Office: {office_phone}")
    if mobile_phone:
        parts.append(f"Mobile: {mobile_phone}")
    return "; ".join(parts) or (legacy_phone or "")


def commit_with_retry(connection):
    execute_with_retry(lambda: connection.commit(), rollback=lambda: connection.rollback())


def safe_redirect_target(target, fallback_endpoint="home"):
    fallback = url_for(fallback_endpoint)
    target = (target or fallback).strip()
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc or not target.startswith("/") or target.startswith("//"):
        return fallback
    return target


def redirect_with_query(target, **params):
    target = safe_redirect_target(target)
    parsed = urlparse(target)
    query_items = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query_items.update({key: value for key, value in params.items() if value is not None})
    return redirect(urlunparse(("", "", parsed.path, parsed.params, urlencode(query_items), parsed.fragment)))


def save_contact_photo(upload, existing_photo=""):
    if not upload or not upload.filename:
        return existing_photo or ""
    extension = Path(upload.filename).suffix.lower()
    if extension not in {".png", ".jpg", ".jpeg"}:
        return existing_photo or ""
    filename = secure_filename(f"{secrets.token_hex(12)}{extension}")
    photo_dir = Path(resource_path("static")) / "contact_photos"
    photo_dir.mkdir(parents=True, exist_ok=True)
    upload.save(photo_dir / filename)
    return url_for("static", filename=f"contact_photos/{filename}")


def save_account_logo(upload, existing_logo=""):
    if not upload or not upload.filename:
        return existing_logo or ""
    extension = Path(upload.filename).suffix.lower()
    if extension not in {".png", ".jpg", ".jpeg"}:
        return existing_logo or ""
    filename = secure_filename(f"{secrets.token_hex(12)}{extension}")
    logo_dir = Path(resource_path("static")) / "account_logos"
    logo_dir.mkdir(parents=True, exist_ok=True)
    upload.save(logo_dir / filename)
    return url_for("static", filename=f"account_logos/{filename}")


def pluralise(count, singular, plural=None):
    return singular if int(count or 0) == 1 else (plural or f"{singular}s")


def report_bar_rows(rows, value_key="total", percent_key="percent"):
    rows = [dict(row) for row in rows or []]
    max_value = max((float(row.get(value_key) or 0) for row in rows), default=0)
    for row in rows:
        value = float(row.get(value_key) or 0)
        row[percent_key] = int(round((value / max_value) * 100)) if max_value else 0
    return rows


def rate_limit_key(prefix, identifier):
    return f"{prefix}:{request.remote_addr or 'unknown'}:{(identifier or '').strip().lower()}"


def rate_limit_exceeded(bucket, key):
    now = datetime.utcnow()
    attempts = [stamp for stamp in bucket.get(key, []) if (now - stamp).total_seconds() < RATE_LIMIT_WINDOW_SECONDS]
    attempts.append(now)
    bucket[key] = attempts
    return len(attempts) > MAX_AUTH_ATTEMPTS


@app.context_processor
def inject_dropdown_values():
    return {
        "dropdown_values": DROPDOWN_VALUES,
        "current_user": current_user(),
        "app_name": "PipeFlow PG Manager",
        "app_version": APP_VERSION,
        "app_release_date": APP_RELEASE_DATE,
        "page_instructions": page_instructions_for_endpoint(request.endpoint),
        "csrf_token": csrf_token,
    }


app.jinja_env.filters["display_date"] = format_display_date
app.jinja_env.filters["display_time"] = format_display_time


PAGE_INSTRUCTIONS = {
    "home": {
        "title": "How to Use This Page",
        "items": [
            "Start with the command centre metrics to see what needs attention this week.",
            "Use Overdue Actions and Execution Insights together; both refresh from current open-task due dates and due times.",
            "Treat PG Success as Discovery Booked, NBM Booked, Exec Meeting Booked or legacy Meeting Booked, with NBM Booked weighted highest in insights.",
            "Review execution insights for suggested next actions across accounts, campaigns and sales plays.",
            "Use the top navigation to move into Outreach Tasks, Accounts, Contacts, Partners, Reports, Profile or Release Notes.",
        ],
    },
    "outreach": {
        "title": "Outreach Tasks Guidance",
        "items": [
            "Only account owners can share accounts, revoke account sharing or see account sharing assignments.",
            "Use the filters to focus active work. All Open excludes Completed, Closed and Cancelled records.",
            "Completed records can be reopened and updated for 10 days from completion. After that, PipeFlow moves them to the system-only Closed status.",
            "Use Save Assignment after changing the assignee. The selected user must already have access to the account.",
            "Open the task to complete it, add a mandatory Activity Update or create a follow-on task.",
        ],
    },
    "accounts": {
        "title": "Accounts Guidance",
        "items": [
            "Use accounts for PG planning data that is not already managed in SFDC, including PG Bible order and FY target ACV.",
            "Open the account name to edit or review contacts, partner involvement, outreach history, sharing and timeline.",
            "Bulk delete only appears after records are selected so accidental deletion is less likely.",
        ],
    },
    "add_account": {
        "title": "Add Account Guidance",
        "items": [
            "The creator becomes the account owner by default.",
            "Set PG Bible Order when the account must appear in a specific export sequence.",
            "Enter Pipeline Target USD ACV so dashboard PG target totals and PG Bible exports remain accurate.",
        ],
    },
    "edit_account": {
        "title": "Edit Account Guidance",
        "items": [
            "Changing Account Owner transfers ownership rights when you save.",
            "Only the owner can share or revoke sharing for this account.",
            "Use Cancel if you need to leave without committing changes.",
        ],
    },
    "view_account": {
        "title": "Account Review Guidance",
        "items": [
            "Use this page to confirm account detail, coverage, partner involvement and audit history before planning outreach.",
            "If you are the owner, the Account Sharing panel shows who has access and lets you revoke access.",
            "Revoking access returns any tasks assigned to that user back to the account owner.",
        ],
    },
    "contacts": {
        "title": "Contacts Guidance",
        "items": [
            "Use contacts to capture stakeholder context that improves future campaign and sales play recommendations.",
            "Open the contact name to review or update the record quickly.",
            "Accounts need at least one contact before Campaign Builder can generate a campaign.",
        ],
    },
    "add_contact": {
        "title": "Add Contact Guidance",
        "items": [
            "Select the account first so the contact is mapped to the right business unit or organisation.",
            "Capture job role, relationship strength and useful personal context where known.",
            "Good contact data improves campaign recommendations over time.",
        ],
    },
    "edit_contact": {
        "title": "Edit Contact Guidance",
        "items": [
            "Update stakeholder details when role, relationship or responsibilities change.",
            "Use Save to commit changes or Cancel to leave the record untouched.",
            "Keep personal context concise and relevant to business outreach.",
        ],
    },
    "view_contact": {
        "title": "Contact Review Guidance",
        "items": [
            "Review account mapping, relationship context and timeline before creating outreach.",
            "Use Edit Contact when stakeholder responsibility or relationship quality changes.",
            "Timeline entries help explain how the relationship has developed.",
        ],
    },
    "partners": {
        "title": "Partners Guidance",
        "items": [
            "Use partners for organisations supporting account progression, such as GOSI, resellers, partners and hyperscalers.",
            "Open a partner to manage its contacts and account relationships.",
            "Partner contacts are separate from account contacts and use partner-specific role fields.",
        ],
    },
    "view_partner": {
        "title": "Partner Review Guidance",
        "items": [
            "Use this page to manage partner organisation details, partner contacts and account mappings.",
            "Map partner contacts to the specific customer accounts they support.",
            "Keep partner next actions current when they are helping progress an account.",
        ],
    },
    "add_outreach": {
        "title": "Add Outreach Guidance",
        "items": [
            "Use one record per outreach task or next action.",
            "Activity Start Date is maintained inside the activity record. Activity Due Date is shown on the Outreach table because it drives next-action execution.",
            "Leave Activity Update blank until there is a real update to record.",
        ],
    },
    "edit_outreach": {
        "title": "Edit Outreach Guidance",
        "items": [
            "Add an Activity Update before completing or closing a task.",
            "Save applies all selected values on the Outreach amend form.",
            "Complete and Create Follow-on saves the current task as completed, then opens a new outreach form for the next step.",
        ],
    },
    "view_outreach": {
        "title": "Outreach Review Guidance",
        "items": [
            "Review the full task detail, contact, account, due date and activity update history.",
            "Use Edit Outreach when the task needs a status, outcome or due date change.",
            "Timeline entries help explain progress over time.",
        ],
    },
    "campaign_builder": {
        "title": "Campaign Builder Guidance",
        "items": [
            "Campaigns use one sales play only and can be generated for multiple contacts on the selected account.",
            "Campaign start date cannot be earlier than today and generated tasks stay on or after the configured start date.",
            "Auto-scheduling avoids weekends, configured non-working dates and duplicate time slots where possible.",
        ],
    },
    "reports": {
        "title": "Reports Guidance",
        "items": [
            "Use reports to review account coverage, contacts, outreach execution and PG Bible export readiness.",
            "Exports reflect the current fields used across the application.",
            "PG Bible export uses the May 2026 template mapping stored on the server.",
        ],
    },
    "account_reports": {
        "title": "Account Reports Guidance",
        "items": [
            "Review tiering, target ACV, business organisation and account coverage.",
            "Use exports when you need to reconcile PipeFlow planning data outside the app.",
            "Keep PG Bible Order and Pipeline Target values current for accurate reporting.",
        ],
    },
    "contact_reports": {
        "title": "Contact Reports Guidance",
        "items": [
            "Review stakeholder coverage by account, role and relationship quality.",
            "Use this report to spot accounts with weak or missing contact coverage.",
            "Export when contact data needs offline review.",
        ],
    },
    "outreach_reports": {
        "title": "Outreach Reports Guidance",
        "items": [
            "Review all outreach activity in one table. The report opens on the last 7 days by default.",
            "Use filters to widen the date range or narrow reporting by account, outcome or activity type.",
            "Compare Discovery Booked, NBM Booked and executive meeting outcomes to improve future campaign recommendations.",
        ],
    },
    "task_reports": {
        "title": "Task Reports Guidance",
        "items": [
            "Task Reports have been removed as a duplicate view.",
            "Use Outreach Reports for task ownership, due dates, status and outcomes.",
        ],
    },
    "profile": {
        "title": "Profile Guidance",
        "items": [
            "Keep your full name accurate because it appears in assignment fields and audit records.",
            "Set work day start and end times so generated campaigns schedule inside your normal day.",
            "Add non-working date blocks for holidays, travel or unavailable periods.",
        ],
    },
    "admin_permissions": {
        "title": "Admin Guidance",
        "items": [
            "This page is only visible to Application Admin and Company Admin users. Non-admin users do not see Admin in the navigation.",
            "Use Create User Profile to add users to the correct company tenant.",
            "Application Admins can select any configured tenant. Company Admins only see their own company.",
            "Use user permissions to manage role, active users and profile details.",
            "Application Admins use Tenant to create company tenancies and broadcasts to publish timed messages on login and the dashboard.",
            "Admin actions are recorded in the admin audit trail.",
        ],
    },
    "admin_tenants": {
        "title": "Tenant Guidance",
        "items": [
            "Tenant administration is only available to Application Admin users.",
            "Create the company tenant before assigning user profiles to that company.",
            "Company Name is the tenancy boundary used by company-scoped administration, sharing and assignment controls.",
            "Select the primary company contact from the available user list.",
        ],
    },
    "admin_users": {
        "title": "Profile Administration Guidance",
        "items": [
            "This admin form is only available to users with administration permission.",
            "Use this page to manage user identity, tenant, role and active status.",
            "Deactivate users who should no longer access PipeFlow.",
            "Password resets should only be used after confirming the user request.",
        ],
    },
    "audit_trail": {
        "title": "Audit Guidance",
        "items": [
            "Audit is an admin-only sub tab inside Admin and is hidden from non-admin users.",
            "Use audit records to understand who changed what, when it changed and the values before and after.",
            "Profile and permission changes include field labels for easier reading.",
            "Use the newest entries first when investigating recent behaviour.",
        ],
    },
    "global_search": {
        "title": "Search Guidance",
        "items": [
            "Search across accounts, contacts, partners, outreach and timeline text.",
            "Use specific account, contact, campaign or partner names for best results.",
            "Open the matching record from the result list to review or edit it.",
        ],
    },
    "release_notes": {
        "title": "Release Notes Guidance",
        "items": [
            "Release notes show latest to earliest.",
            "Open a release to review New, Enhanced and Fixed changes.",
            "Version 2.1.6 adds tenant maintenance, dashboard metric drill-through, upward broadcasts, simpler overdue task colouring and resilience improvements.",
        ],
    },
    "user_guide": {
        "title": "User Guide Guidance",
        "items": [
            "Use this guide when you need workflow instructions or definitions.",
            "Select a topic from the side menu to focus on one part of PipeFlow.",
            "The guide reflects the current hosted workflow.",
        ],
    },
    "user_guide_section": {
        "title": "User Guide Guidance",
        "items": [
            "Review the selected guide topic for step-by-step workflow notes.",
            "Use the side menu to move between related topics.",
            "Return to the app page when you are ready to apply the guidance.",
        ],
    },
    "team_page": {
        "title": "Team Guidance",
        "items": [
            "Team administration is only visible to users with the required admin access.",
            "Admins can invite users to the active team.",
            "Invitations are created in-app and acknowledged before moving to Outreach Tasks.",
            "Shared account access is managed from Outreach Tasks and account pages.",
        ],
    },
    "tasks": {
        "title": "Tasks Guidance",
        "items": [
            "Tasks are managed through the dashboard and Outreach Tasks page.",
            "Use status and due date updates to keep accountability current.",
            "Completed, Closed and Cancelled work is hidden from active views by default; Closed is system-only after the 10-day Completed reopen window expires.",
        ],
    },
    "login": {
        "title": "Sign In Guidance",
        "items": [
            "Use your registered email and password to access your private PipeFlow workspace.",
            "Broadcast messages from admins appear here when active.",
            "Use reset password if you know your secret reset phrase.",
        ],
    },
    "register": {
        "title": "Registration Guidance",
        "items": [
            "Register with your work email, full name and password.",
            "Choose a secret reset phrase you can remember because it is required for secure password reset.",
            "Your profile creates a private workspace for your PipeFlow data.",
        ],
    },
    "forgot_password": {
        "title": "Password Reset Guidance",
        "items": [
            "Use this page when you need to reset your password without email.",
            "You must know the secret reset phrase created during registration.",
            "If you cannot remember the phrase, ask an administrator for help.",
        ],
    },
    "reset_password": {
        "title": "Reset Password Guidance",
        "items": [
            "Enter your email, reset phrase and new password.",
            "The reset phrase is checked securely and is not shown to administrators.",
            "After reset, sign in with the new password.",
        ],
    },
}


def page_instructions_for_endpoint(endpoint):
    if not endpoint or endpoint.startswith("export_") or endpoint.startswith("health"):
        return None
    if endpoint in PAGE_INSTRUCTIONS:
        return PAGE_INSTRUCTIONS[endpoint]
    return {
        "title": "Page Guidance",
        "items": [
            "Review the page details before making changes.",
            "Use Save to commit updates or Cancel and Back buttons to leave without changing data.",
            "Use the User Guide link if you need more detail about the workflow.",
        ],
    }


@app.before_request
def require_login_and_prepare_database():
    public_endpoints = {"login", "register", "forgot_password", "reset_password", "release_notes", "user_guide", "user_guide_section", "version_health", "storage_health", "static"}
    if request.endpoint in public_endpoints:
        return None

    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        validate_csrf_token()

    if not session.get("user_id"):
        return redirect(url_for("login"))

    user = current_user()
    if not user:
        session.clear()
        return redirect(url_for("login", message="Your profile is inactive or could not be found."))
    if not user["company"]:
        session.clear()
        return redirect(url_for("login", message="Your profile must be assigned to a tenant before you can sign in."))

    initialise_database()
    return None


@app.after_request
def apply_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    response.headers.setdefault("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'")
    if request.is_secure or app.config.get("SESSION_COOKIE_SECURE"):
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response





@app.route("/health/version")
def version_health():
    from db_compat import translate_sql
    sample = "datetime(next_action_date || ' ' || COALESCE(NULLIF(next_action_time, ''), '23:59:59')) < datetime(?)"
    lines = [
        f"pipeflow_version={APP_VERSION}",
        f"pipeflow_release_date={APP_RELEASE_DATE}",
        f"pipeflow_server_build={APP_BUILD}",
        f"database_url_configured={str(bool(os.environ.get('DATABASE_URL'))).lower()}",
        f"translation_check={translate_sql(sample)}",
    ]
    return Response("\n".join(lines), mimetype="text/plain")


@app.route("/health/storage")
def storage_health():
    backend = "supabase_postgres" if using_postgres() else "temporary_sqlite"
    lines = [
        f"backend={backend}",
        f"database_url_configured={str(bool(os.environ.get('DATABASE_URL'))).lower()}",
        f"authenticated={str(bool(session.get('user_id'))).lower()}",
    ]
    return Response("\n".join(lines), mimetype="text/plain")


@app.route("/release-notes")
def release_notes():
    sorted_release_notes = sorted(
        RELEASE_NOTES,
        key=lambda release: (
            release.get("release_date", ""),
            release.get("version", ""),
        ),
        reverse=True
    )
    return render_template(
        "release_notes.html",
        release_notes=sorted_release_notes,
        current_version=APP_VERSION,
        current_release_date=APP_RELEASE_DATE,
    )


@app.route("/user-guide")
def user_guide():
    return render_template(
        "user_guide.html",
        guide_sections=USER_GUIDE_SECTIONS,
        selected_section=None,
    )


@app.route("/user-guide/<section_slug>")
def user_guide_section(section_slug):
    selected_section = None
    selected_section = next(
        (section for section in USER_GUIDE_SECTIONS if section["slug"] == section_slug),
        None
    )
    if not selected_section:
        return redirect(url_for("user_guide"))
    return render_template(
        "user_guide.html",
        guide_sections=USER_GUIDE_SECTIONS,
        selected_section=selected_section,
    )


@app.route("/login", methods=("GET", "POST"))
def login():
    error = ""
    message = request.args.get("message", "")
    if request.method == "POST":
        email = request.form.get("email", "")
        if rate_limit_exceeded(LOGIN_ATTEMPTS, rate_limit_key("login", email)):
            return render_template("login.html", error="Too many sign-in attempts. Please wait and try again.", message=message, broadcast_messages=list_broadcast_messages(active_only=True)), 429
        user = authenticate_user(email, request.form.get("password", ""))
        if user:
            session.clear()
            csrf_token()
            session["user_id"] = user["id"]
            session["user_email"] = user["email"]
            session["user_name"] = user["full_name"]
            session["workspace_schema"] = ensure_user_workspace_schema(user)
            initialise_database()
            connection = get_db_connection()
            connection.execute(
                """
                UPDATE user_profile
                SET full_name = ?,
                    last_updated = CURRENT_TIMESTAMP
                WHERE id = 1
                """,
                (user["full_name"],),
            )
            commit_with_retry(connection)
            connection.close()
            return redirect(url_for("home"))
        error = "Email or password was not recognised."

    return render_template("login.html", error=error, message=message, broadcast_messages=list_broadcast_messages(active_only=True))


@app.route("/forgot-password", methods=("GET", "POST"))
def forgot_password():
    error = ""
    if request.method == "POST":
        email = request.form.get("email", "")
        if rate_limit_exceeded(RESET_ATTEMPTS, rate_limit_key("reset", email)):
            return render_template("forgot_password.html", error="Too many reset attempts. Please wait and try again."), 429
        reset_phrase = request.form.get("reset_phrase", "")
        password = request.form.get("password", "")
        error = reset_password_with_phrase(email, reset_phrase, password)
        if not error:
            return redirect(url_for("login", message="Password reset. Please sign in."))

    return render_template("forgot_password.html", error=error)


@app.route("/reset-password", methods=("GET", "POST"))
def reset_password():
    return redirect(url_for("forgot_password"))


@app.route("/register", methods=("GET", "POST"))
def register():
    error = ""
    if user_count() > 0:
        return redirect(url_for("login", message="Profiles are created by an administrator. Ask your company administrator for access."))
    if request.method == "POST":
        user_id, error = create_user(
            request.form.get("email", ""),
            request.form.get("password", ""),
            request.form.get("full_name", ""),
            request.form.get("reset_phrase", ""),
        )
        if user_id:
            session.clear()
            session["user_id"] = user_id
            session["user_email"] = request.form.get("email", "").strip().lower()
            session["user_name"] = request.form.get("full_name", "").strip()
            session["workspace_schema"] = ensure_user_workspace_schema(get_user_for_admin(user_id))
            initialise_database()
            connection = get_db_connection()
            connection.execute(
                """
                UPDATE user_profile
                SET full_name = ?,
                    last_updated = CURRENT_TIMESTAMP
                WHERE id = 1
                """,
                (session["user_name"],),
            )
            connection.commit()
            connection.close()
            return redirect(url_for("home"))

    return render_template("register.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def render_admin_permissions():
    actor = current_user()
    return render_template(
        "admin_permissions.html",
        users=list_users(actor),
        tenant_options=list_tenants(actor, active_only=True),
        is_app_admin=is_application_admin(actor),
        broadcast_messages=list_broadcast_messages(active_only=False),
        audit_retention_enabled=audit_retention_enabled(),
        message=request.args.get("message", ""),
        error=request.args.get("error", "")
    )


def current_admin_can_manage_user(target_user):
    actor = current_user()
    if not actor or not target_user:
        return False
    if is_application_admin(actor):
        return True
    return is_company_admin(actor) and same_company(actor, target_user)


def require_application_admin_redirect():
    if is_application_admin(current_user()):
        return None
    return redirect(url_for("admin_users", error="Only application administrators can change application-level settings."))


@app.route("/admin/users")
@admin_required
def admin_users():
    return redirect(url_for(
        "admin_permissions",
        message=request.args.get("message", ""),
        error=request.args.get("error", "")
    ))


@app.route("/admin/permissions")
@admin_required
def admin_permissions():
    return render_admin_permissions()


@app.route("/admin/tenants", methods=("GET", "POST"))
@admin_required
def admin_tenants():
    actor = current_user()
    message = request.args.get("message", "")
    error = request.args.get("error", "")
    if request.method == "POST":
        if not is_application_admin(actor):
            return redirect(url_for("admin_tenants", error="Only application administrators can create new tenants."))
        error = create_tenant(
            request.form.get("company_name", ""),
            request.form.get("country", ""),
            request.form.get("company_contact", ""),
        )
        if not error:
            log_admin_audit(
                current_user(),
                "Tenant created",
                "Tenant",
                request.form.get("company_name", ""),
                f"Country: {request.form.get('country', '')}; Company contact: {request.form.get('company_contact', '')}"
            )
            return redirect(url_for("admin_tenants", message="Tenant created."))
    return render_template(
        "admin_tenants.html",
        tenants=list_tenants(actor=actor, active_only=False),
        tenant_user_options=list_users(actor),
        can_create_tenant=is_application_admin(actor),
        can_edit_tenants=is_application_admin(actor) or is_company_admin(actor),
        message=message,
        error=error,
    )


@app.route("/admin/tenants/<int:tenant_id>/update", methods=("POST",))
@admin_required
def admin_update_tenant(tenant_id):
    actor = current_user()
    error = update_tenant(
        tenant_id,
        request.form.get("country", ""),
        request.form.get("company_contact", ""),
        bool(request.form.get("is_active")),
        actor=actor,
    )
    if error:
        return redirect(url_for("admin_tenants", error=error))
    log_admin_audit(
        actor,
        "Tenant updated",
        "Tenant",
        request.form.get("company_name", f"Tenant {tenant_id}"),
        f"Country: {request.form.get('country', '')}; Company contact: {request.form.get('company_contact', '')}; Active: {bool(request.form.get('is_active'))}."
    )
    return redirect(url_for("admin_tenants", message="Tenant updated."))


@app.route("/admin/users/create", methods=("POST",))
@admin_required
def admin_create_user():
    actor = current_user()
    requested_company = request.form.get("company", "")
    company = requested_company if is_application_admin(actor) else actor["company"]
    user_id, error = create_user(
        request.form.get("email", ""),
        request.form.get("password", ""),
        request.form.get("full_name", ""),
        request.form.get("reset_phrase", ""),
        company,
    )
    if error:
        return redirect(url_for("admin_users", error=error))
    role = request.form.get("role", "user")
    if role == "admin" and not is_application_admin(actor):
        role = "user"
    role_error = set_user_role(user_id, role)
    if role_error:
        return redirect(url_for("admin_users", error=role_error))
    log_admin_audit(
        actor,
        "User created",
        "User",
        request.form.get("email", "").strip().lower(),
        f"Company: {company}; Role: {role}."
    )
    return redirect(url_for("admin_users", message="User profile created."))


@app.route("/admin/broadcasts/add", methods=("POST",))
@admin_required
def admin_add_broadcast():
    guard = require_application_admin_redirect()
    if guard:
        return guard
    error = create_broadcast_message(
        request.form.get("title", ""),
        request.form.get("message", ""),
        request.form.get("severity", "info"),
        request.form.get("start_at", ""),
        request.form.get("stop_at", ""),
        bool(request.form.get("is_active"))
    )
    if error:
        return redirect(url_for("admin_users", error=error))
    return redirect(url_for("admin_users", message="Broadcast message added."))


@app.route("/admin/broadcasts/<int:message_id>/update", methods=("POST",))
@admin_required
def admin_update_broadcast(message_id):
    guard = require_application_admin_redirect()
    if guard:
        return guard
    error = update_broadcast_message(
        message_id,
        request.form.get("title", ""),
        request.form.get("message", ""),
        request.form.get("severity", "info"),
        request.form.get("start_at", ""),
        request.form.get("stop_at", ""),
        bool(request.form.get("is_active"))
    )
    if error:
        return redirect(url_for("admin_users", error=error))
    return redirect(url_for("admin_users", message="Broadcast message updated."))


@app.route("/admin/broadcasts/<int:message_id>/deactivate", methods=("POST",))
@admin_required
def admin_deactivate_broadcast(message_id):
    guard = require_application_admin_redirect()
    if guard:
        return guard
    set_broadcast_message_active(message_id, False)
    return redirect(url_for("admin_users", message="Broadcast message hidden."))


@app.route("/admin/broadcasts/<int:message_id>/reactivate", methods=("POST",))
@admin_required
def admin_reactivate_broadcast(message_id):
    guard = require_application_admin_redirect()
    if guard:
        return guard
    set_broadcast_message_active(message_id, True)
    return redirect(url_for("admin_users", message="Broadcast message restored."))


@app.route("/admin/broadcasts/<int:message_id>/delete", methods=("POST",))
@admin_required
def admin_delete_broadcast(message_id):
    guard = require_application_admin_redirect()
    if guard:
        return guard
    delete_broadcast_message(message_id)
    return redirect(url_for("admin_users", message="Broadcast message deleted."))


@app.route("/admin/audit-retention", methods=("POST",))
@admin_required
def admin_update_audit_retention():
    guard = require_application_admin_redirect()
    if guard:
        return guard
    enabled = request.form.get("audit_retention_enabled") == "1"
    set_admin_setting("audit_retention_enabled", "1" if enabled else "0")
    log_admin_audit(
        current_user(),
        "Audit retention setting updated",
        "Admin setting",
        "Audit auto-delete",
        f"Audit auto-delete older than 6 months set to {'Auto-delete On' if enabled else 'Auto-delete Off'}."
    )
    if enabled:
        cleanup_audit_retention()
    return redirect(url_for("admin_users", message=f"Audit auto-delete is now {'Auto-delete On' if enabled else 'Auto-delete Off'}."))


@app.route("/admin/account-fields/add", methods=("POST",))
@admin_required
def admin_add_account_field():
    guard = require_application_admin_redirect()
    if guard:
        return guard
    error = create_account_field_definition(
        request.form.get("field_label", ""),
        request.form.get("field_type", "text"),
        bool(request.form.get("is_required"))
    )
    if error:
        return redirect(url_for("admin_users", error=error))
    log_admin_audit(
        current_user(),
        "Account field added",
        "Account field",
        request.form.get("field_label", ""),
        f"Type: {request.form.get('field_type', 'text')}; Required: {'Yes' if request.form.get('is_required') else 'No'}"
    )
    return redirect(url_for("admin_users", message="Account field added."))


@app.route("/admin/account-fields/<int:field_id>/update", methods=("POST",))
@admin_required
def admin_update_account_field(field_id):
    guard = require_application_admin_redirect()
    if guard:
        return guard
    before = get_account_field_definition(field_id)
    error = update_account_field_definition(
        field_id,
        request.form.get("field_label", ""),
        request.form.get("field_type", "text"),
        bool(request.form.get("is_required")),
        request.form.get("sort_order", "0")
    )
    if error:
        return redirect(url_for("admin_users", error=error))
    before_label = before["field_label"] if before else "Unknown field"
    detail = (
        f"Label: {before_label} to {request.form.get('field_label', '')}; "
        f"Type: {request.form.get('field_type', 'text')}; "
        f"Required: {'Yes' if request.form.get('is_required') else 'No'}; "
        f"Order: {request.form.get('sort_order', '0')}"
    )
    log_admin_audit(current_user(), "Account field updated", "Account field", request.form.get("field_label", ""), detail)
    return redirect(url_for("admin_users", message="Account field updated."))


@app.route("/admin/account-fields/<int:field_id>/deactivate", methods=("POST",))
@admin_required
def admin_deactivate_account_field(field_id):
    guard = require_application_admin_redirect()
    if guard:
        return guard
    field = get_account_field_definition(field_id)
    set_account_field_active(field_id, False)
    log_admin_audit(
        current_user(),
        "Account field removed",
        "Account field",
        field["field_label"] if field else f"Field {field_id}",
        "Field hidden from account forms. Existing values are retained."
    )
    return redirect(url_for("admin_users", message="Account field removed from account forms."))


@app.route("/admin/account-fields/<int:field_id>/reactivate", methods=("POST",))
@admin_required
def admin_reactivate_account_field(field_id):
    guard = require_application_admin_redirect()
    if guard:
        return guard
    field = get_account_field_definition(field_id)
    set_account_field_active(field_id, True)
    log_admin_audit(
        current_user(),
        "Account field restored",
        "Account field",
        field["field_label"] if field else f"Field {field_id}",
        "Field restored to account forms."
    )
    return redirect(url_for("admin_users", message="Account field restored to account forms."))


@app.route("/admin/users/<int:user_id>/identity", methods=("POST",))
@admin_required
def admin_update_user_identity(user_id):
    user = get_user_for_admin(user_id)
    if not user:
        return redirect(url_for("admin_users", error="Profile was not found."))
    actor = current_user()
    if not current_admin_can_manage_user(user):
        return redirect(url_for("admin_users", error="You can only manage users in your company."))
    old_email = user["email"]
    old_name = user["full_name"]
    old_team = user["team"] if "team" in user.keys() and user["team"] else ""
    old_company = user["company"] if "company" in user.keys() and user["company"] else ""
    new_email = request.form.get("email", "")
    new_name = request.form.get("full_name", "")
    new_team = request.form.get("team", "")
    new_company = request.form.get("company", old_company) if is_application_admin(actor) else old_company
    error = update_user_identity(user_id, new_email, new_name, new_team, new_company)
    if error:
        return redirect(url_for("admin_users", error=error))

    changes = []
    if old_name != new_name.strip():
        changes.append(f"Name changed from {old_name} to {new_name.strip()}")
    if old_email != new_email.strip().lower():
        changes.append(f"Email changed from {old_email} to {new_email.strip().lower()}")
    if old_team != new_team.strip():
        changes.append(f"Team changed from {old_team or 'Not set'} to {new_team.strip() or 'Not set'}")
    if old_company != new_company.strip():
        changes.append(f"Company changed from {old_company or 'Not set'} to {new_company.strip() or 'Not set'}")
    log_admin_audit(
        current_user(),
        "Profile details updated",
        "User",
        new_email.strip().lower(),
        "; ".join(changes) if changes else "Profile details saved with no visible changes."
    )
    return redirect(url_for("admin_users", message="Profile details updated."))


@app.route("/admin/users/<int:user_id>/deactivate", methods=("POST",))
@admin_required
def admin_deactivate_user(user_id):
    if user_id == session.get("user_id"):
        return redirect(url_for("admin_users", error="You cannot deactivate your own admin profile."))
    user = get_user_for_admin(user_id)
    if not current_admin_can_manage_user(user):
        return redirect(url_for("admin_users", error="You can only manage users in your company."))
    set_user_active(user_id, False)
    log_admin_audit(
        current_user(),
        "Profile deactivated",
        "User",
        user["email"] if user else f"User {user_id}",
        "User sign-in access was paused."
    )
    return redirect(url_for("admin_users", message="Profile deactivated."))


@app.route("/admin/users/<int:user_id>/reactivate", methods=("POST",))
@admin_required
def admin_reactivate_user(user_id):
    user = get_user_for_admin(user_id)
    if not current_admin_can_manage_user(user):
        return redirect(url_for("admin_users", error="You can only manage users in your company."))
    set_user_active(user_id, True)
    log_admin_audit(
        current_user(),
        "Profile reactivated",
        "User",
        user["email"] if user else f"User {user_id}",
        "User sign-in access was restored."
    )
    return redirect(url_for("admin_users", message="Profile reactivated."))


@app.route("/admin/users/<int:user_id>/role", methods=("POST",))
@admin_required
def admin_update_user_role(user_id):
    user = get_user_for_admin(user_id)
    actor = current_user()
    if not current_admin_can_manage_user(user):
        return redirect(url_for("admin_users", error="You can only manage users in your company."))
    old_role = user["role"] if user else "unknown"
    new_role = request.form.get("role", "")
    if not is_application_admin(actor) and new_role == "admin":
        return redirect(url_for("admin_users", error="Only application administrators can assign Application Admin access."))
    error = set_user_role(user_id, new_role)
    if error:
        return redirect(url_for("admin_users", error=error))
    log_admin_audit(
        current_user(),
        "Role updated",
        "User",
        user["email"] if user else f"User {user_id}",
        f"Role changed from {old_role} to {new_role}."
    )
    return redirect(url_for("admin_users", message="Role updated."))


@app.route("/admin/users/<int:user_id>/reset-password", methods=("POST",))
@admin_required
def admin_reset_user_password(user_id):
    user = get_user_for_admin(user_id)
    if not current_admin_can_manage_user(user):
        return redirect(url_for("admin_users", error="You can only manage users in your company."))
    error = reset_user_password(user_id, request.form.get("password", ""))
    if error:
        return redirect(url_for("admin_users", error=error))
    log_admin_audit(
        current_user(),
        "Password reset",
        "User",
        user["email"] if user else f"User {user_id}",
        "Admin reset this user's password."
    )
    return redirect(url_for("admin_users", message="Password reset."))


def add_timeline_entry(connection, related_type, related_id, entry_type, entry_text, created_by="Melissa"):
    connection.execute("""
        INSERT INTO timeline_entries (
            related_type,
            related_id,
            entry_type,
            entry_text,
            created_by
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        related_type,
        related_id,
        entry_type,
        entry_text,
        created_by
    ))


def audit_actor():
    user = current_user()
    if not user:
        return {"id": None, "name": session.get("user_name", ""), "email": session.get("user_email", "")}
    return {
        "id": user["id"],
        "name": user["full_name"],
        "email": user["email"],
    }


def audit_entry(connection, entity_type, entity_id, action_type, field_name="", field_label="", value_from="", value_to=""):
    actor = audit_actor()
    connection.execute(
        """
        INSERT INTO audit_entries (
            entity_type,
            entity_id,
            action_type,
            field_name,
            field_label,
            value_from,
            value_to,
            actor_user_id,
            actor_name,
            actor_email
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entity_type,
            entity_id,
            action_type,
            field_name,
            field_label,
            "" if value_from is None else str(value_from),
            "" if value_to is None else str(value_to),
            actor["id"],
            actor["name"],
            actor["email"],
        ),
    )


def audit_record_create(connection, entity_type, entity_id, values, labels=None):
    labels = labels or {}
    for field_name, value in values.items():
        if value not in (None, ""):
            audit_entry(
                connection,
                entity_type,
                entity_id,
                "Create",
                field_name,
                labels.get(field_name, field_name),
                "",
                value,
            )


def audit_record_update(connection, entity_type, entity_id, existing_record, new_values, labels=None):
    labels = labels or {}
    for field_name, new_value in new_values.items():
        old_value = existing_record[field_name] if existing_record and existing_record[field_name] is not None else ""
        new_value = new_value if new_value is not None else ""
        if str(old_value) != str(new_value):
            audit_entry(
                connection,
                entity_type,
                entity_id,
                "Update",
                field_name,
                labels.get(field_name, field_name),
                old_value,
                new_value,
            )


def audit_record_delete(connection, entity_type, entity_id, label=""):
    audit_entry(connection, entity_type, entity_id, "Delete", "record", "Record", label, "")


def current_user_can_delete_partner(partner):
    user = current_user()
    if not user or not partner:
        return False
    if user["role"] == "admin":
        return True
    submitted_by_user_id = partner["submitted_by_user_id"] if "submitted_by_user_id" in partner.keys() else None
    submitted_by_email = partner["submitted_by_email"] if "submitted_by_email" in partner.keys() else None
    return (
        submitted_by_user_id == user["id"]
        or (submitted_by_email and submitted_by_email == user["email"])
    )


def delete_current_profile_workspace_data(connection):
    admin_owner = next((user for user in list_users() if user["role"] == "admin" and user["is_active"]), None)
    if admin_owner:
        connection.execute("""
            UPDATE accounts
            SET owner_user_id = ?,
                owner_name = ?,
                owner_email = ?,
                last_updated = CURRENT_TIMESTAMP
        """, (
            admin_owner["id"],
            admin_owner["full_name"],
            admin_owner["email"],
        ))

    connection.execute(
        """
        UPDATE user_profile
        SET full_name = '',
            email = '',
            team = '',
            job_title = '',
            last_updated = CURRENT_TIMESTAMP
        WHERE id = 1
        """
    )


def selected_record_ids(field_name="selected_ids"):
    ids = []
    for value in request.form.getlist(field_name):
        try:
            ids.append(int(value))
        except (TypeError, ValueError):
            continue
    return ids


def delete_account_records(connection, account_ids):
    for account_id in account_ids:
        account = connection.execute("SELECT account_name FROM accounts WHERE id = ?", (account_id,)).fetchone()
        audit_record_delete(connection, "account", account_id, account["account_name"] if account else "")
        connection.execute("DELETE FROM timeline_entries WHERE related_type = 'account' AND related_id = ?", (account_id,))
        connection.execute("DELETE FROM timeline_entries WHERE related_type = 'contact' AND related_id IN (SELECT id FROM contacts WHERE account_id = ?)", (account_id,))
        connection.execute("DELETE FROM timeline_entries WHERE related_type = 'outreach' AND related_id IN (SELECT id FROM outreach WHERE account_id = ?)", (account_id,))
        connection.execute("DELETE FROM account_partners WHERE account_id = ?", (account_id,))
        connection.execute("DELETE FROM partner_contact_accounts WHERE account_id = ?", (account_id,))
        connection.execute("DELETE FROM account_custom_values WHERE account_id = ?", (account_id,))
        connection.execute("DELETE FROM outreach_recipients WHERE outreach_id IN (SELECT id FROM outreach WHERE account_id = ?)", (account_id,))
        connection.execute("UPDATE partner_contacts SET account_id = NULL WHERE account_id = ?", (account_id,))
        connection.execute("DELETE FROM outreach WHERE account_id = ?", (account_id,))
        connection.execute("DELETE FROM contacts WHERE account_id = ?", (account_id,))
        connection.execute("DELETE FROM accounts WHERE id = ?", (account_id,))


def delete_contact_records(connection, contact_ids):
    for contact_id in contact_ids:
        contact = connection.execute("SELECT name FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        audit_record_delete(connection, "contact", contact_id, contact["name"] if contact else "")
        connection.execute("DELETE FROM timeline_entries WHERE related_type = 'contact' AND related_id = ?", (contact_id,))
        connection.execute("DELETE FROM outreach_recipients WHERE contact_id = ?", (contact_id,))
        connection.execute("DELETE FROM outreach WHERE contact_id = ?", (contact_id,))
        connection.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))


def delete_outreach_records(connection, outreach_ids):
    deleted_count = 0
    for outreach_id in outreach_ids:
        outreach = connection.execute("SELECT subject FROM outreach WHERE id = ?", (outreach_id,)).fetchone()
        if not outreach:
            continue
        audit_record_delete(connection, "outreach", outreach_id, outreach["subject"] if outreach else "")
        connection.execute(
            "DELETE FROM timeline_entries WHERE related_type = 'outreach' AND related_id = ?",
            (outreach_id,),
        )
        connection.execute(
            "DELETE FROM outreach_recipients WHERE outreach_id = ?",
            (outreach_id,),
        )
        connection.execute("DELETE FROM outreach WHERE id = ?", (outreach_id,))
        deleted_count += 1
    return deleted_count


def delete_partner_records(connection, partner_ids):
    for partner_id in partner_ids:
        partner = connection.execute("SELECT * FROM partners WHERE id = ?", (partner_id,)).fetchone()
        if not current_user_can_delete_partner(partner):
            continue
        audit_record_delete(connection, "partner", partner_id, partner["partner_name"] if partner else "")
        connection.execute("DELETE FROM account_partners WHERE partner_id = ?", (partner_id,))
        connection.execute("DELETE FROM partner_contact_accounts WHERE partner_id = ?", (partner_id,))
        connection.execute("DELETE FROM partner_contacts WHERE partner_id = ?", (partner_id,))
        connection.execute("DELETE FROM partners WHERE id = ?", (partner_id,))


def build_change_log(existing_record, new_values, labels):
    changes = []

    for field_name, new_value in new_values.items():
        old_value = existing_record[field_name] if existing_record[field_name] is not None else ""
        new_value = new_value if new_value is not None else ""

        if str(old_value) != str(new_value):
            label = labels.get(field_name, field_name)
            changes.append(f"{label} changed from '{old_value}' to '{new_value}'")

    return changes


def account_custom_field_payload(active_only=True):
    return [dict(field) for field in list_account_field_definitions(active_only=active_only)]


def load_account_custom_values(connection, account_id):
    rows = connection.execute(
        """
        SELECT field_key, field_value
        FROM account_custom_values
        WHERE account_id = ?
        """,
        (account_id,),
    ).fetchall()
    return {row["field_key"]: row["field_value"] for row in rows}


def save_account_custom_values(connection, account_id, fields, form):
    for field in fields:
        field_key = field["field_key"]
        value = (form.get(f"custom_{field_key}") or "").strip()
        existing = connection.execute(
            """
            SELECT id
            FROM account_custom_values
            WHERE account_id = ?
              AND field_key = ?
            """,
            (account_id, field_key),
        ).fetchone()
        if existing:
            connection.execute(
                """
                UPDATE account_custom_values
                SET field_value = ?,
                    last_updated = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (value, existing["id"]),
            )
        else:
            connection.execute(
                """
                INSERT INTO account_custom_values (account_id, field_key, field_value)
                VALUES (?, ?, ?)
                """,
                (account_id, field_key, value),
            )


def build_custom_field_changes(fields, old_values, form):
    changes = []
    for field in fields:
        key = field["field_key"]
        old_value = old_values.get(key) or ""
        new_value = (form.get(f"custom_{key}") or "").strip()
        if str(old_value) != str(new_value):
            changes.append(f"{field['field_label']} changed from '{old_value}' to '{new_value}'")
    return changes


def get_or_create_partner(connection, partner_name):
    partner_name = (partner_name or "").strip()

    if not partner_name:
        return None

    partner = connection.execute("""
        SELECT *
        FROM partners
        WHERE LOWER(partner_name) = LOWER(?)
    """, (partner_name,)).fetchone()

    if partner:
        return partner["id"]

    actor = audit_actor()
    cursor = connection.execute("""
        INSERT INTO partners (
            partner_name,
            submitted_by_user_id,
            submitted_by_email,
            submitted_by_name
        )
        VALUES (?, ?, ?, ?)
    """, (partner_name, actor["id"], actor["email"], actor["name"]))

    return cursor.lastrowid


def normalise_partner_website(website):
    website = (website or "").strip()
    if not website:
        return ""
    if re.match(r"^(https?://|www\.)[A-Za-z0-9][A-Za-z0-9.-]*(\.[A-Za-z]{2,})(/.*)?$", website):
        return website
    return None


def calculate_account_health(contact_count, outreach_count, meeting_count, overdue_followups, latest_outreach_date):
    if contact_count < 2:
        return {
            "label": "Low Contact Count",
            "colour": "red",
            "reason": "Fewer than 2 contacts"
        }

    if overdue_followups > 0:
        return {
            "label": "Overdue Follow-ups",
            "colour": "amber",
            "reason": f"{overdue_followups} overdue follow-up(s)"
        }

    if outreach_count > 0 and meeting_count == 0:
        return {
            "label": "No Meetings Booked",
            "colour": "amber",
            "reason": "Outreach exists but no meetings booked"
        }

    if outreach_count == 0 or latest_outreach_date is None:
        return {
            "label": "No Recent Outreach",
            "colour": "yellow",
            "reason": "No outreach activity recorded"
        }

    return {
        "label": "Good",
        "colour": "green",
        "reason": "Recent activity and relationship depth look healthy"
    }


def campaign_step_templates():
    return [
        {
            "campaign": "VITO",
            "activity_type": "VITO",
            "subject_prefix": "VITO outreach",
            "next_action": "Send VITO-led message",
            "time": "09:00"
        },
        {
            "campaign": "LinkedIn",
            "activity_type": "LinkedIn",
            "subject_prefix": "LinkedIn outreach",
            "next_action": "Send LinkedIn connection or follow-up message",
            "time": "10:00"
        },
        {
            "campaign": "White Paper / Webinar / Consensus",
            "activity_type": "White Paper / Webinar / Consensus",
            "subject_prefix": "Content share",
            "next_action": "Share relevant content or thought leadership",
            "time": "11:00"
        },
        {
            "campaign": "Phone",
            "activity_type": "Phone",
            "subject_prefix": "Phone outreach",
            "next_action": "Call contact and progress the sales play",
            "time": "14:00"
        },
        {
            "campaign": "Events",
            "activity_type": "Events",
            "subject_prefix": "Event search and attendance trigger",
            "next_action": "Search for relevant events to attend or reference",
            "time": "15:00"
        }
    ]


def normalise_match_text(value):
    return (value or "").strip().lower()


def build_campaign_success_context(connection, account_id, contact_ids, sales_play):
    account = connection.execute("""
        SELECT account_name, industry, business_unit, account_tier, country, city
        FROM accounts
        WHERE id = ?
    """, (account_id,)).fetchone()

    if contact_ids:
        placeholders = ",".join("?" for _ in contact_ids)
        selected_contacts = connection.execute(f"""
            SELECT category, bmc_relationship, job_title, org_dept,
                   responsibilities, characteristics, background,
                   personal_interests, personal_win, education, social_media,
                   additional_notes
            FROM contacts
            WHERE id IN ({placeholders})
        """, contact_ids).fetchall()
    else:
        selected_contacts = []

    industry = normalise_match_text(account["industry"] if account else "")
    business_unit = normalise_match_text(account["business_unit"] if account else "")
    account_tier = normalise_match_text(account["account_tier"] if account else "")
    sales_play_text = normalise_match_text(sales_play)
    contact_values = set()
    contact_text = []
    for contact in selected_contacts:
        for field in (
            "category",
            "bmc_relationship",
            "job_title",
            "org_dept",
            "responsibilities",
            "characteristics",
            "background",
            "personal_interests",
            "personal_win",
            "education",
            "social_media",
            "additional_notes",
        ):
            value = normalise_match_text(contact[field])
            if value:
                contact_values.add(value)
                contact_text.extend(value.split())

    contact_keywords = {
        word for word in contact_text
        if len(word) >= 5
    }

    historical_rows = connection.execute("""
        SELECT
            outreach.activity_type,
            outreach.sales_play,
            outreach.outcome,
            outreach.task_status,
            accounts.industry,
            accounts.business_unit,
            accounts.account_tier,
            contacts.category,
            contacts.status,
            contacts.bmc_relationship,
            contacts.job_title,
            contacts.org_dept,
            contacts.responsibilities,
            contacts.characteristics,
            contacts.background,
            contacts.personal_interests,
            contacts.personal_win,
            contacts.education,
            contacts.social_media,
            contacts.additional_notes
        FROM outreach
        LEFT JOIN accounts ON outreach.account_id = accounts.id
        LEFT JOIN contacts ON outreach.contact_id = contacts.id
        WHERE outreach.activity_type IS NOT NULL
          AND outreach.activity_type != ''
          AND outreach.outcome IS NOT NULL
          AND outreach.outcome != ''
    """).fetchall()

    template_by_type = {
        template["activity_type"]: template
        for template in campaign_step_templates()
    }
    scores = {activity_type: 0 for activity_type in template_by_type}
    evidence = {activity_type: {"positive": 0, "meeting": 0, "matched": 0} for activity_type in template_by_type}

    for row in historical_rows:
        activity_type = row["activity_type"]
        if activity_type not in scores:
            continue

        row_score = 1
        if normalise_match_text(row["sales_play"]) == sales_play_text:
            row_score += 8
        if industry and normalise_match_text(row["industry"]) == industry:
            row_score += 4
        if business_unit and normalise_match_text(row["business_unit"]) == business_unit:
            row_score += 3
        if account_tier and normalise_match_text(row["account_tier"]) == account_tier:
            row_score += 2

        row_contact_values = {
            normalise_match_text(row[field])
            for field in (
                "category",
                "bmc_relationship",
                "job_title",
                "org_dept",
            )
            if normalise_match_text(row[field])
        }
        row_contact_text = " ".join(
            normalise_match_text(row[field])
            for field in (
                "responsibilities",
                "characteristics",
                "background",
                "personal_interests",
                "personal_win",
                "education",
                "social_media",
                "additional_notes",
            )
            if normalise_match_text(row[field])
        )
        if contact_values.intersection(row_contact_values):
            row_score += 4
        if contact_keywords and contact_keywords.intersection(set(row_contact_text.split())):
            row_score += 2

        if row["outcome"] in POSITIVE_OUTCOMES:
            row_score += 8
            evidence[activity_type]["positive"] += 1
        if is_pg_success_outcome(row["outcome"], activity_type):
            row_score += 5
            evidence[activity_type]["meeting"] += 1
        if row["outcome"] in NEGATIVE_OUTCOMES:
            row_score -= 4

        if row_score > 1:
            evidence[activity_type]["matched"] += 1
        scores[activity_type] += row_score

    ranked_templates = sorted(
        campaign_step_templates(),
        key=lambda template: (-scores.get(template["activity_type"], 0), template["activity_type"])
    )
    top_templates = [
        template for template in ranked_templates
        if scores.get(template["activity_type"], 0) > 0
    ] or campaign_step_templates()

    strongest = top_templates[0]["activity_type"] if top_templates else "standard sequence"
    matched_rows = sum(item["matched"] for item in evidence.values())
    if matched_rows:
        summary = (
            f"Historic learning used: {matched_rows} matching signal(s). "
            f"Strongest activity for this context: {strongest}. "
            f"Context considered: sales play, industry, account tier, business org, contact role, relationship and personal notes."
        )
    else:
        summary = (
            "Historic learning used: no matching prior outcomes yet. "
            "Using the standard PipeFlow activity sequence and this campaign will train future recommendations."
        )

    return {
        "account": account,
        "templates": top_templates,
        "summary": summary,
        "scores": scores,
    }


def evenly_spaced_dates(start_date, end_date, task_count):
    days = (end_date - start_date).days
    if task_count <= 1 or days <= 0:
        return [start_date]

    dates = []
    used = set()
    for index in range(task_count):
        offset = round((days * index) / (task_count - 1))
        candidate = start_date + timedelta(days=offset)
        while candidate in used and candidate < end_date:
            candidate += timedelta(days=1)
        while candidate in used and candidate > start_date:
            candidate -= timedelta(days=1)
        used.add(candidate)
        dates.append(candidate)
    return sorted(dates)


def parse_time_value(value, fallback):
    try:
        return datetime.strptime(value or fallback, "%H:%M").time()
    except ValueError:
        return datetime.strptime(fallback, "%H:%M").time()


def parse_non_working_blocks(rows):
    blocks = []
    for row in rows or []:
        try:
            start = datetime.strptime(row["start_date"], "%Y-%m-%d").date()
            end = datetime.strptime(row["end_date"], "%Y-%m-%d").date()
        except (KeyError, TypeError, ValueError):
            continue
        if end < start:
            start, end = end, start
        blocks.append((start, end))
    return blocks


def legacy_profile_non_working_block(profile):
    if not profile:
        return []
    try:
        start = datetime.strptime(profile["non_working_start_date"], "%Y-%m-%d").date() if profile["non_working_start_date"] else None
        end = datetime.strptime(profile["non_working_end_date"], "%Y-%m-%d").date() if profile["non_working_end_date"] else None
    except (KeyError, TypeError, ValueError):
        return []
    if not start:
        return []
    end = end or start
    if end < start:
        start, end = end, start
    return [(start, end)]


def is_non_working_date(action_date, profile=None, non_working_blocks=None):
    if action_date.weekday() >= 5:
        return True
    blocks = list(non_working_blocks or []) + legacy_profile_non_working_block(profile)
    for start, end in blocks:
        if start <= action_date <= end:
            return True
    return False


def next_working_date(action_date, campaign_start, campaign_end, profile=None, non_working_blocks=None):
    candidate = action_date
    while candidate <= campaign_end and is_non_working_date(candidate, profile, non_working_blocks):
        candidate += timedelta(days=1)
    if candidate <= campaign_end:
        return candidate
    candidate = action_date
    while candidate >= campaign_start and is_non_working_date(candidate, profile, non_working_blocks):
        candidate -= timedelta(days=1)
    if candidate >= campaign_start:
        return candidate
    return action_date


def available_campaign_time(action_date, preferred_time, profile=None, reserved_slots=None, earliest_time=None):
    reserved_slots = reserved_slots or set()
    start_time = parse_time_value(profile["work_day_start"] if profile and profile["work_day_start"] else "", "09:00")
    end_time = parse_time_value(profile["work_day_end"] if profile and profile["work_day_end"] else "", "17:00")
    preferred = parse_time_value(preferred_time, "09:00")
    earliest = earliest_time if earliest_time else start_time
    current_dt = datetime.combine(action_date, max(start_time, earliest, min(preferred, end_time)))
    end_dt = datetime.combine(action_date, end_time)
    while current_dt <= end_dt:
        slot = (action_date.isoformat(), current_dt.strftime("%H:%M"))
        if slot not in reserved_slots:
            reserved_slots.add(slot)
            return current_dt.strftime("%H:%M")
        current_dt += timedelta(minutes=15)
    fallback = datetime.combine(action_date, max(start_time, earliest))
    slot = (action_date.isoformat(), fallback.strftime("%H:%M"))
    reserved_slots.add(slot)
    return fallback.strftime("%H:%M")


def build_campaign_schedule(campaign_start, campaign_end, total_tasks, times_per_week, templates=None, profile=None, reserved_slots=None, non_working_blocks=None, submitted_at=None):
    templates = templates or campaign_step_templates()
    total_tasks = max(1, int(total_tasks or 1))
    times_per_week = max(1, min(int(times_per_week or 1), 7))
    schedule = []
    initial_vito_template = next(
        (template for template in campaign_step_templates() if template["activity_type"] == "VITO"),
        {
            "campaign": "VITO",
            "activity_type": "VITO",
            "subject_prefix": "VITO outreach",
            "next_action": "Send VITO-led message",
            "time": "09:00",
        },
    )

    for index, action_date in enumerate(evenly_spaced_dates(campaign_start, campaign_end, total_tasks)):
        if action_date < campaign_start:
            action_date = campaign_start
        if action_date > campaign_end:
            action_date = campaign_end
        action_date = next_working_date(action_date, campaign_start, campaign_end, profile, non_working_blocks)
        if index == 0:
            template = dict(initial_vito_template)
        else:
            template = dict(templates[(index - 1) % len(templates)])
            if template.get("activity_type") == "VITO":
                template["campaign"] = "Follow-up"
                template["activity_type"] = "Follow-up"
                template["subject_prefix"] = "Follow-up email"
                template["next_action"] = "Send follow-up email"
                template["time"] = template.get("time") or "09:00"
        template["action_date"] = action_date
        earliest_time = submitted_at.time() if submitted_at and action_date == submitted_at.date() else None
        template["time"] = available_campaign_time(
            action_date,
            template.get("time", "09:00"),
            profile,
            reserved_slots,
            earliest_time=earliest_time,
        )
        template["times_per_week"] = times_per_week
        schedule.append(template)

    return schedule


def build_pg_campaign_steps(pg_week_start):
    return build_campaign_schedule(pg_week_start - timedelta(days=28), pg_week_start - timedelta(days=1), 8, 2)


POSITIVE_OUTCOMES = (
    "Positive Response",
    "Meeting Booked",
    "NBM Booked",
    "Discovery Booked",
    "Exec Meeting Booked",
    "Referral Made",
    "Follow-up Required",
)

PG_SUCCESS_OUTCOMES = (
    "Discovery Booked",
    "NBM Booked",
    "Exec Meeting Booked",
    "Meeting Booked",
)

SCHEDULED_MEETING_OUTCOMES = PG_SUCCESS_OUTCOMES

PRIMARY_PG_SUCCESS_OUTCOMES = (
    "Discovery Booked",
    "NBM Booked",
)

NBM_SUCCESS_OUTCOMES = (
    "NBM Booked",
)

EXECUTIVE_CONTACT_CATEGORIES = (
    "Executive",
)

EXECUTIVE_RELATIONSHIPS = (
    "Executive Buyer",
    "Executive Assistant",
)

EXECUTIVE_TITLE_KEYWORDS = (
    "chief",
    "ceo",
    "cfo",
    "cio",
    "cto",
    "ciso",
    "coo",
    "cro",
    "cdo",
    "vp",
    "vice president",
    "evp",
    "svp",
    "president",
    "executive",
    "director",
    "general manager",
    "managing director",
    "head of",
)

NEGATIVE_OUTCOMES = (
    "Negative Response",
    "Not Relevant",
)

SYSTEM_LOCKED_TASK_STATUSES = (
    "Closed",
    "Cancelled",
)

INACTIVE_TASK_STATUSES = (
    "Closed",
    "Completed",
    "Cancelled",
)

COMPLETED_REOPEN_DAYS = 10


def is_closed_task_status(status):
    return (status or "").strip() in INACTIVE_TASK_STATUSES


def is_system_locked_task_status(status):
    return (status or "").strip() in SYSTEM_LOCKED_TASK_STATUSES


def normalise_task_status(status, allow_closed=False):
    status = (status or "Not Started").strip()
    allowed = set(DROPDOWN_VALUES["task_statuses"])
    if allow_closed:
        allowed.add("Closed")
    if status == "Closed" and not allow_closed:
        return "Completed"
    return status if status in allowed else "Not Started"


def parse_app_datetime(value):
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:26] if "%f" in fmt else text[:19] if fmt.endswith("%S") else text[:10], fmt)
        except (TypeError, ValueError):
            continue
    return None


def completed_reopen_deadline(outreach_item):
    if not outreach_item or (outreach_item["task_status"] or "") != "Completed":
        return None
    completed_at = outreach_item["completed_at"] if "completed_at" in outreach_item.keys() else ""
    if not completed_at:
        completed_at = outreach_item["last_updated"] if "last_updated" in outreach_item.keys() else ""
    completed_dt = parse_app_datetime(completed_at)
    return completed_dt + timedelta(days=COMPLETED_REOPEN_DAYS) if completed_dt else None


def task_can_be_modified(outreach_item, now=None):
    if not outreach_item:
        return False
    status = (outreach_item["task_status"] or "").strip()
    if is_system_locked_task_status(status):
        return False
    if status != "Completed":
        return True
    deadline = completed_reopen_deadline(outreach_item)
    return bool(deadline and (now or current_app_datetime()) < deadline)


def task_lock_message(outreach_item):
    status = (outreach_item["task_status"] or "").strip() if outreach_item else "Closed"
    if status == "Completed":
        return "This task is Completed and its 10-day reopen window has expired, so it can only be viewed and reported."
    if status == "Closed":
        return "This task is Closed by the system and can only be viewed and reported."
    if status == "Cancelled":
        return "This task is Cancelled and can no longer be modified or reassigned."
    return f"This task is {status} and can no longer be modified or reassigned."


def completed_status_timestamp(existing_record, new_status):
    current_status = (existing_record["task_status"] or "").strip() if existing_record else ""
    existing_completed_at = existing_record["completed_at"] if existing_record and "completed_at" in existing_record.keys() else ""
    if new_status == "Completed":
        return existing_completed_at or app_datetime_key()
    if current_status == "Completed" and new_status != "Completed":
        return ""
    return existing_completed_at or ""


def close_expired_completed_outreach(connection, now=None):
    now = now or current_app_datetime()
    expired = []
    rows = connection.execute("""
        SELECT *
        FROM outreach
        WHERE COALESCE(task_status, '') = 'Completed'
    """).fetchall()
    for row in rows:
        deadline = completed_reopen_deadline(row)
        if deadline and deadline <= now:
            expired.append(row)
    for row in expired:
        connection.execute("""
            UPDATE outreach
            SET task_status = 'Closed',
                last_updated = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (row["id"],))
    return len(expired)


def normalise_outreach_outcome(outcome):
    outcome = (outcome or "").strip()
    return "No Response" if outcome == "No Response Yet" else outcome


def current_app_datetime():
    return datetime.now(APP_TIMEZONE).replace(tzinfo=None)


def app_datetime_key(value=None):
    value = value or current_app_datetime()
    return value.strftime("%Y-%m-%d %H:%M:%S")


def task_due_datetime(next_action_date, next_action_time):
    if not next_action_date:
        return None
    try:
        due_date = datetime.strptime(str(next_action_date), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    due_time_value = parse_due_time(next_action_time)
    if due_time_value is None:
        return None
    return datetime.combine(due_date, due_time_value)


def is_overdue_task(next_action_date, next_action_time, task_status, now=None):
    if is_closed_task_status(task_status):
        return False
    due_at = task_due_datetime(next_action_date, next_action_time)
    return bool(due_at and due_at < (now or current_app_datetime()))


def open_task_sql(alias="outreach"):
    placeholders = ",".join("?" for _ in INACTIVE_TASK_STATUSES)
    return f"COALESCE({alias}.task_status, '') NOT IN ({placeholders})"


def open_task_params():
    return tuple(INACTIVE_TASK_STATUSES)


def overdue_task_sql(alias="outreach"):
    return (
        f"{alias}.next_action_date IS NOT NULL "
        f"AND {alias}.next_action_date != '' "
        f"AND datetime("
        f"{alias}.next_action_date || ' ' || "
        f"COALESCE(NULLIF({alias}.next_action_time, ''), '23:59:59')"
        f") < datetime(?) "
        f"AND {open_task_sql(alias)}"
    )


def overdue_task_params(now=None):
    return (app_datetime_key(now), *open_task_params())


def is_pg_success_outcome(outcome, activity_type=""):
    return (outcome or "").strip() in PG_SUCCESS_OUTCOMES or (activity_type or "").strip() == "Meeting"


def outcome_requires_scheduled_meeting(outcome):
    return (outcome or "").strip() in SCHEDULED_MEETING_OUTCOMES


def split_scheduled_meeting_datetime(value):
    value = str(value or "").strip()
    if not value:
        return "", ""
    if "T" in value:
        date_part, time_part = value.split("T", 1)
    else:
        parts = value.split(" ", 1)
        date_part = parts[0]
        time_part = parts[1] if len(parts) > 1 else ""
    return date_part[:10], time_part[:5]


def scheduled_meeting_datetime_value(date_value="", time_value=""):
    date_value = str(date_value or "").strip()
    time_value = str(time_value or "").strip()
    if date_value and time_value:
        return f"{date_value}T{time_value[:5]}"
    return date_value


def default_outreach_assignee():
    user = current_user()
    if user and user["full_name"]:
        return user["full_name"]
    return "Melissa"


def is_primary_pg_success_outcome(outcome):
    return (outcome or "").strip() in PRIMARY_PG_SUCCESS_OUTCOMES


def is_nbm_success_outcome(outcome):
    return (outcome or "").strip() in NBM_SUCCESS_OUTCOMES


def is_executive_contact(category="", bmc_relationship="", job_title=""):
    category = (category or "").strip()
    relationship = (bmc_relationship or "").strip()
    title = (job_title or "").strip().lower()
    return (
        category in EXECUTIVE_CONTACT_CATEGORIES
        or relationship in EXECUTIVE_RELATIONSHIPS
        or any(keyword in title for keyword in EXECUTIVE_TITLE_KEYWORDS)
    )


def score_learning_row(row):
    return (
        (row["nbm_total"] or 0) * 8
        + (row["primary_pg_success_total"] or 0) * 6
        + (row["executive_success_total"] or 0) * 5
        + (row["meeting_total"] or 0) * 4
        + (row["positive_total"] or 0) * 3
        + (row["completed_total"] or 0)
        - (row["negative_total"] or 0) * 2
        - (row["overdue_total"] or 0)
    )


def add_learning_score(rows):
    scored_rows = []

    for row in rows:
        scored_row = dict(row)
        scored_row["score"] = score_learning_row(row)
        scored_row["positive_rate"] = (
            round(((row["positive_total"] or 0) / row["total"]) * 100)
            if row["total"]
            else 0
        )
        scored_rows.append(scored_row)

    scored_rows.sort(
        key=lambda row: (
            row["score"],
            row["nbm_total"] or 0,
            row["primary_pg_success_total"] or 0,
            row["executive_success_total"] or 0,
            row["meeting_total"] or 0,
            row["positive_total"] or 0,
            row["total"] or 0,
        ),
        reverse=True
    )

    return scored_rows


def build_execution_insights(ai_insights, learning_insights):
    combined = []
    for insight in ai_insights:
        title = str(insight.get("title") or insight.get("type") or "Account needs attention").strip()
        message = str(insight.get("message") or "Review this account and update the next best PG action.").strip()
        action = str(insight.get("action") or message).strip()
        combined.append({
            "source": "AI Insight",
            "category": insight.get("type", "Insight") or "Insight",
            "title": title,
            "message": message,
            "action": action,
            "evidence": insight.get("evidence") or message,
            "link": insight.get("link", url_for("home")),
            "priority": insight.get("severity", "medium"),
        })

    for insight in learning_insights:
        title = str(insight.get("title") or insight.get("signal") or "Campaign learning needs data").strip()
        message = str(insight.get("message") or "Add outcomes to campaign touchpoints so PipeFlow can identify what converts to Discovery and NBM bookings.").strip()
        action = str(insight.get("action") or "Update campaign outcomes and focus the next move on an executive route.").strip()
        combined.append({
            "source": "Campaign Learning",
            "category": insight.get("signal", "Learning") or "Learning",
            "title": title,
            "message": message,
            "action": action,
            "evidence": insight.get("evidence") or message,
            "link": insight.get("link", url_for("campaign_builder")),
            "priority": "learning",
        })

    combined = [
        insight for insight in combined
        if insight["title"] or insight["message"] or insight["action"]
    ]

    priority_order = {
        "high": 1,
        "medium": 2,
        "learning": 3,
        "positive": 4,
    }
    combined.sort(key=lambda item: priority_order.get(item["priority"], 5))
    return combined[:10]


def build_attention_insights(needs_attention_accounts):
    attention_insights = []
    for account in needs_attention_accounts:
        attention_insights.append({
            "source": "Needs Attention",
            "category": account.get("health_label", "Account Health"),
            "title": account.get("account_name", "Account needs attention"),
            "message": account.get("health_reason", ""),
            "action": "Open the account and resolve the health risk before it blocks pipeline progress.",
            "link": url_for("view_account", account_id=account["id"]),
            "priority": "high",
        })
    return attention_insights


def compact_join(values, limit=3):
    cleaned = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        key = text.casefold()
        if text and key not in seen:
            cleaned.append(text)
            seen.add(key)
        if len(cleaned) >= limit:
            break
    return ", ".join(cleaned)


def behaviour_signal_from_notes(notes):
    text = " ".join(str(note or "") for note in notes).lower()
    if not text.strip():
        return "Use a short value-led touchpoint and record the response so future recommendations can improve."
    if any(word in text for word in ("busy", "no time", "later", "chase", "follow up", "follow-up")):
        return "Use a concise follow-up with one specific ask and offer two meeting slots to reduce effort for the contact."
    if any(word in text for word in ("referred", "referral", "introduced", "intro", "colleague", "team")):
        return "Work through the warm route that has already appeared, reference the introduction and ask for the next stakeholder."
    if any(word in text for word in ("budget", "cost", "commercial", "procurement", "business case")):
        return "Lead with business value, quantified impact and procurement-ready proof rather than product detail."
    if any(word in text for word in ("technical", "architecture", "security", "integration", "data")):
        return "Use a technical proof point and invite the contact into a focused discovery around risk, integration or operating model."
    if any(word in text for word in ("event", "webinar", "white paper", "consensus", "content")):
        return "Follow the content signal quickly with a tailored point of view and a direct meeting ask while interest is warm."
    if any(word in text for word in ("negative", "not relevant", "no interest", "closed")):
        return "Change route before repeating the same message, either through a different stakeholder, partner or business trigger."
    return "Use the most recent human response as the opener, keep the message specific, and ask for one clear next step."


def deduplicate_execution_insights(insights):
    unique_insights = []
    seen = set()

    for insight in insights:
        key = (
            str(insight.get("title", "")).strip().casefold(),
            str(insight.get("message", "")).strip().casefold(),
            str(insight.get("link", "")).strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        unique_insights.append(insight)

    return unique_insights


def dashboard_scalar(connection, sql, params=(), default=0):
    try:
        row = connection.execute(sql, params).fetchone()
        if row is None:
            return default
        return row[0] if not isinstance(row, dict) else next(iter(row.values()), default)
    except Exception:
        traceback.print_exc()
        return default


def dashboard_rows(connection, sql, params=()):
    try:
        return connection.execute(sql, params).fetchall()
    except Exception:
        traceback.print_exc()
        return []


def build_dashboard_strategy_insights(connection, metric_values, account_health_rows=None, learning_insights=None):
    account_health_rows = account_health_rows or []
    learning_insights = learning_insights or []
    insights = []
    overdue_count = int(metric_values.get("this_week_overdue") or 0)
    due_count = int(metric_values.get("this_week_due") or 0)
    success_count = int(metric_values.get("this_week_meetings_booked") or 0)
    untouched_count = int(metric_values.get("this_week_untouched_accounts") or 0)

    untouched_accounts = dashboard_rows(connection, """
        SELECT
            accounts.id,
            accounts.account_name,
            COALESCE(accounts.pipeline_target, 0) AS pipeline_target,
            COALESCE(accounts.sales_play, '') AS sales_play,
            COUNT(outreach.id) AS outreach_total
        FROM accounts
        LEFT JOIN outreach ON outreach.account_id = accounts.id
        GROUP BY accounts.id, accounts.account_name, accounts.pipeline_target, accounts.sales_play
        HAVING COUNT(outreach.id) = 0
        ORDER BY pipeline_target DESC, accounts.account_name
        LIMIT 4
    """)
    for row in untouched_accounts:
        insights.append({
            "source": "Daily Focus",
            "category": "Account Activity",
            "title": f"{row['account_name']} has no outreach activity",
            "evidence": f"Account: {row['account_name']}. Sales play: {row['sales_play'] or 'not entered'}. Pipeline target: ${float(row['pipeline_target'] or 0):,.0f}.",
            "message": "This account cannot create campaign learning or meeting conversion until the first focused action is created.",
            "action": f"Create a dated outreach task for {row['account_name']} with a clear Discovery or NBM meeting ask tied to the account sales play.",
            "link": url_for("add_outreach", account_id=row["id"]),
            "priority": "high",
        })

    no_contact_accounts = dashboard_rows(connection, """
        SELECT
            accounts.id,
            accounts.account_name,
            COALESCE(accounts.pipeline_target, 0) AS pipeline_target
        FROM accounts
        LEFT JOIN contacts
          ON contacts.account_id = accounts.id
         AND COALESCE(contacts.status, 'Active') = 'Active'
        GROUP BY accounts.id, accounts.account_name, accounts.pipeline_target
        HAVING COUNT(contacts.id) = 0
        ORDER BY pipeline_target DESC, accounts.account_name
        LIMIT 4
    """)
    for row in no_contact_accounts:
        insights.append({
            "source": "Daily Focus",
            "category": "Contact Activity",
            "title": f"{row['account_name']} has no active contacts",
            "evidence": f"Account: {row['account_name']}. Active contacts: 0. Pipeline target: ${float(row['pipeline_target'] or 0):,.0f}.",
            "message": "No contact coverage means there is no person to progress toward Discovery, NBM or executive meetings.",
            "action": f"Add at least one executive buyer, assistant or senior stakeholder for {row['account_name']}, then create the first meeting-led outreach task.",
            "link": url_for("view_account", account_id=row["id"]),
            "priority": "high",
        })

    overdue_outreach = dashboard_rows(connection, f"""
        SELECT
            outreach.id,
            outreach.subject,
            outreach.next_action,
            outreach.next_action_date,
            outreach.next_action_time,
            accounts.account_name,
            COALESCE(contacts.name, partner_contacts.name) AS contact_name,
            COALESCE(contacts.job_title, partner_contacts.job_title) AS contact_title
        FROM outreach
        LEFT JOIN accounts ON outreach.account_id = accounts.id
        LEFT JOIN contacts ON outreach.contact_id = contacts.id
        LEFT JOIN partner_contacts ON outreach.partner_contact_id = partner_contacts.id
        WHERE {overdue_task_sql("outreach")}
        ORDER BY outreach.next_action_date ASC, outreach.next_action_time ASC, outreach.id DESC
        LIMIT 6
    """, overdue_task_params())
    for row in overdue_outreach:
        contact_label = ", ".join(part for part in [row["contact_name"], row["contact_title"]] if part) or "No contact assigned"
        insight_link = url_for("view_outreach", outreach_id=row["id"])
        insights.append({
            "source": "Daily Focus",
            "category": "Overdue Outreach",
            "title": f"{row['account_name'] or 'Unknown account'} overdue: {row['subject'] or 'No subject'}",
            "evidence": f"Account: {row['account_name'] or 'Unknown account'}. Contact: {contact_label}. Subject: {row['subject'] or 'No subject'}. Due: {display_date(row['next_action_date'])} {row['next_action_time'] or ''}.",
            "message": "This specific overdue activity is blocking momentum because the next meeting-led step has not been completed or rescheduled.",
            "action": f"Open the outreach item, update the outcome, and reset '{row['next_action'] or row['subject'] or 'the next action'}' toward a Discovery or NBM meeting.",
            "link": insight_link,
            "priority": "high",
        })

    campaign_gaps = dashboard_rows(connection, """
        SELECT
            outreach.id,
            outreach.subject,
            outreach.sales_play,
            outreach.outcome,
            outreach.activity_type,
            accounts.account_name,
            COALESCE(contacts.name, partner_contacts.name) AS contact_name,
            COALESCE(contacts.job_title, partner_contacts.job_title) AS contact_title
        FROM outreach
        LEFT JOIN accounts ON outreach.account_id = accounts.id
        LEFT JOIN contacts ON outreach.contact_id = contacts.id
        LEFT JOIN partner_contacts ON outreach.partner_contact_id = partner_contacts.id
        WHERE COALESCE(outreach.outcome, '') IN ('', 'No Response', 'No Response Yet')
        ORDER BY outreach.last_updated DESC, outreach.id DESC
        LIMIT 6
    """)
    for row in campaign_gaps:
        contact_label = ", ".join(part for part in [row["contact_name"], row["contact_title"]] if part) or "No contact assigned"
        insights.append({
            "source": "Daily Focus",
            "category": "Campaign Activity",
            "title": f"{row['account_name'] or 'Unknown account'} campaign has no response signal",
            "evidence": f"Account: {row['account_name'] or 'Unknown account'}. Contact: {contact_label}. Outreach subject: {row['subject'] or 'No subject'}. Sales play: {row['sales_play'] or 'not entered'}.",
            "message": "The campaign has activity but no useful response signal, so PipeFlow cannot tell whether the route is working.",
            "action": "Change the message, stakeholder route or ask, then record a clear response outcome so the campaign can learn what books meetings.",
            "link": url_for("view_outreach", outreach_id=row["id"]),
            "priority": "medium",
        })

    if overdue_count:
        insights.append({
            "source": "Execution Guidance",
            "category": "Execution Drag",
            "title": f"Clear {overdue_count} overdue action(s) before adding new noise",
            "message": "Open overdue work is the strongest sign that campaign momentum is slipping. Protect the active PG motion before building more tasks.",
            "action": "Work overdue actions first, update the outcome or next action, then reset the next touchpoint toward Discovery Booked or NBM Booked.",
            "link": url_for("outreach"),
            "priority": "high",
        })

    if success_count:
        insights.append({
            "source": "Execution Guidance",
            "category": "Scale What Works",
            "title": f"{success_count} PG success outcome(s) landed this week",
            "message": "Discovery, NBM and executive meeting bookings are the clearest signals of successful PG motion.",
            "action": "Review which account, contact route and sales play produced the booking, then reuse that pattern on similar executive stakeholders.",
            "link": url_for("reports"),
            "priority": "positive",
        })

    executive_gap_count = sum(1 for row in account_health_rows if (row["executive_contact_count"] or 0) == 0)
    conversion_gap_count = sum(
        1 for row in account_health_rows
        if (row["outreach_count"] or 0) > 0 and (row["primary_pg_success_count"] or 0) == 0
    )

    if executive_gap_count:
        insights.append({
            "source": "Execution Guidance",
            "category": "Executive Coverage",
            "title": f"{executive_gap_count} account(s) need an executive route",
            "message": "PG success is strongest when the path reaches an executive buyer, assistant, sponsor or senior owner.",
            "action": "Prioritise mapping executive contacts before increasing activity volume, then make the next ask specific to Discovery or NBM.",
            "link": url_for("accounts"),
            "priority": "high",
        })

    if conversion_gap_count:
        insights.append({
            "source": "Execution Guidance",
            "category": "PG Conversion",
            "title": f"{conversion_gap_count} active account(s) have activity but no Discovery or NBM",
            "message": "Activity without a PG success outcome usually means the route, stakeholder level or ask needs to change.",
            "action": "Stop repeating the same motion; switch to an executive route, partner route or sharper Discovery/NBM meeting ask.",
            "link": url_for("outreach"),
            "priority": "medium",
        })

    if untouched_count:
        insights.append({
            "source": "Execution Guidance",
            "category": "Coverage Gap",
            "title": f"{untouched_count} account(s) have no active campaign or outreach",
            "message": "Untouched accounts do not create PG learning and can leave target coverage exposed.",
            "action": "Choose the highest-value untouched accounts, map the executive path, then build a focused campaign rather than spreading effort thinly.",
            "link": url_for("campaign_builder"),
            "priority": "medium",
        })

    if due_count and not overdue_count:
        insights.append({
            "source": "Execution Guidance",
            "category": "This Week Execution",
            "title": f"{due_count} open action(s) are due this week",
            "message": "The current week has executable work without overdue drag showing in the command centre.",
            "action": "Complete the highest-value account actions first and record outcomes immediately so campaign learning can sharpen.",
            "link": url_for("tasks"),
            "priority": "medium",
        })

    for learning in learning_insights[:5]:
        insights.append({
            "source": "Campaign Learning",
            "category": learning.get("signal", "Learning"),
            "title": learning.get("title", "Campaign pattern detected"),
            "message": learning.get("message", "PipeFlow has found a pattern in the current campaign data."),
            "action": learning.get("action", "Apply the pattern to the next executive-facing touchpoint and record the outcome."),
            "link": learning.get("link", url_for("campaign_builder")),
            "priority": "learning",
        })

    if not insights:
        insights.append({
            "source": "Execution Guidance",
            "category": "Build PG Learning",
            "title": "Start building measurable PG execution data",
            "message": "PipeFlow needs accounts, contacts, outreach tasks and outcomes to learn which campaign routes convert.",
            "action": "Add account contacts, prioritise executive stakeholders, build a focused campaign and record Discovery Booked or NBM Booked outcomes.",
            "link": url_for("accounts"),
            "priority": "medium",
        })

    return insights[:12]


def dashboard_guidance_week_key(today):
    return today.strftime("%Y-W%W")


def display_date(value):
    if isinstance(value, date):
        return value.strftime("%d %b %Y")
    parsed = parse_app_datetime(value)
    return parsed.strftime("%d %b %Y") if parsed else str(value or "")


def format_dashboard_guidance(title, lead, bullets, subtitle=""):
    cleaned_bullets = [str(item).strip() for item in bullets if str(item or "").strip()]
    if not cleaned_bullets:
        cleaned_bullets = ["Keep account, contact, outreach and outcome data current so PipeFlow can sharpen its recommendations."]
    paragraphs = [str(lead or "").strip(), *cleaned_bullets]
    paragraphs = [paragraph for paragraph in paragraphs if paragraph]
    body = "\n\n".join(paragraphs)
    return {
        "title": title,
        "subtitle": subtitle,
        "lead": lead,
        "bullets": cleaned_bullets[:12],
        "paragraphs": paragraphs[:14],
        "body": body,
    }


def active_pg_week_broadcast():
    try:
        broadcasts = list_broadcast_messages(active_only=True)
    except Exception:
        traceback.print_exc()
        return None
    for broadcast in broadcasts:
        text = f"{broadcast['title'] or ''} {broadcast['message'] or ''}".lower()
        if "pg week" in text or "pipeline generation week" in text:
            return broadcast
    return None


def generate_weekly_wrap_up(connection, period_start, period_end, metric_values, execution_insights):
    week_successes = dashboard_rows(connection, """
        SELECT accounts.account_name, outreach.sales_play, outreach.outcome, outreach.activity_type
        FROM outreach
        LEFT JOIN accounts ON outreach.account_id = accounts.id
        WHERE outreach.activity_date >= ?
          AND outreach.activity_date <= ?
          AND (
                outreach.outcome IN ('Discovery Booked', 'NBM Booked', 'Exec Meeting Booked', 'Meeting Booked')
             OR outreach.activity_type = 'Meeting'
          )
        ORDER BY outreach.activity_date DESC, outreach.id DESC
        LIMIT 5
    """, (period_start.isoformat(), period_end.isoformat()))
    closed_count = metric_values.get("this_week_completed", 0)
    overdue_count = metric_values.get("this_week_overdue", 0)
    success_count = metric_values.get("this_week_meetings_booked", 0)
    success_accounts = compact_join([row["account_name"] for row in week_successes if row["account_name"]], 3)
    period_label = f"{display_date(period_start)} to {display_date(period_end)}"
    pg_week = active_pg_week_broadcast()
    bullets = [
        f"Between {period_label}, PipeFlow can see {success_count} Discovery, NBM or executive meeting success outcome(s), and {closed_count} outreach task(s) were completed or closed.",
    ]
    if success_accounts:
        bullets.append(f"The clearest progress came through {success_accounts}. That is where the route, stakeholder level and sales play deserve a quick look before you repeat the pattern elsewhere.")
    if overdue_count:
        bullets.append(f"There are still {overdue_count} overdue action(s). The week has had useful movement, but not all of it has converted into clean forward momentum yet.")
    else:
        bullets.append("There are no overdue actions showing in the command centre, which means the next improvement is less about recovery and more about choosing the right executive route.")
    if pg_week:
        bullets.append("Because PG week is active, the best use of momentum is calls, VITOs and LinkedIn outreach at pace. The goal is not activity for its own sake; it is to schedule Discovery meetings or NBM meetings for future dates while the campaign energy is high.")
    for insight in execution_insights[:2]:
        bullets.append(f"I would also pay attention to this: {insight.get('action', '')}")
    return format_dashboard_guidance(
        f"Weekly Wrap Up - {period_label}",
        f"Here is the weekly wrap-up for {period_label}.",
        bullets,
        subtitle=period_label,
    )


def generate_next_24_hours_focus(connection, today, metric_values, execution_insights):
    tomorrow = today + timedelta(days=1)
    upcoming_rows = dashboard_rows(connection, f"""
        SELECT
            accounts.account_name,
            outreach.activity_type,
            outreach.outcome,
            outreach.next_action,
            outreach.next_action_date,
            outreach.next_action_time,
            COUNT(*) OVER (PARTITION BY accounts.account_name) AS account_total
        FROM outreach
        LEFT JOIN accounts ON outreach.account_id = accounts.id
        WHERE outreach.next_action_date >= ?
          AND outreach.next_action_date <= ?
          AND {open_task_sql("outreach")}
        ORDER BY outreach.next_action_date, outreach.next_action_time, accounts.account_name
        LIMIT 8
    """, (today.isoformat(), tomorrow.isoformat(), *open_task_params()))
    upcoming_count = dashboard_scalar(connection, f"""
        SELECT COUNT(*)
        FROM outreach
        WHERE next_action_date >= ?
          AND next_action_date <= ?
          AND {open_task_sql("outreach")}
    """, (today.isoformat(), tomorrow.isoformat(), *open_task_params()), 0)
    overdue_count = metric_values.get("this_week_overdue", 0)
    untouched_count = metric_values.get("this_week_untouched_accounts", 0)
    success_rows = dashboard_rows(connection, """
        SELECT outcome, COUNT(*) AS total
        FROM outreach
        WHERE outcome IN ('NBM Booked', 'Discovery Booked', 'Exec Meeting Booked', 'Meeting Booked')
        GROUP BY outcome
    """)
    success_total = sum(int(row["total"] or 0) for row in success_rows)
    success_summary = (
        ", ".join(f"{row['total']} {row['outcome']}" for row in success_rows)
        or "no booked meeting outcomes yet"
    )
    success_account_rows = dashboard_rows(connection, """
        SELECT
            accounts.account_name,
            COUNT(*) AS total
        FROM outreach
        LEFT JOIN accounts ON outreach.account_id = accounts.id
        WHERE outreach.outcome IN ('NBM Booked', 'Discovery Booked', 'Exec Meeting Booked', 'Meeting Booked')
        GROUP BY accounts.account_name
        HAVING accounts.account_name IS NOT NULL
        ORDER BY total DESC, accounts.account_name
        LIMIT 3
    """)
    success_accounts = ", ".join(row["account_name"] for row in success_account_rows if row["account_name"])
    focus_accounts = []
    seen_accounts = set()
    for row in upcoming_rows:
        account_name = row["account_name"] or "Unknown account"
        if account_name not in seen_accounts:
            seen_accounts.add(account_name)
            focus_accounts.append(account_name)
    if not focus_accounts:
        focus_accounts = [row["account_name"] for row in success_account_rows if row["account_name"]]
    if not focus_accounts:
        focus_accounts = [
            row["account_name"]
            for row in dashboard_rows(connection, f"""
                SELECT
                    accounts.account_name,
                    COUNT(outreach.id) AS open_actions,
                    COALESCE(accounts.pipeline_target, 0) AS pipeline_target
                FROM accounts
                LEFT JOIN outreach
                  ON outreach.account_id = accounts.id
                 AND {open_task_sql("outreach")}
                GROUP BY accounts.id, accounts.account_name, accounts.pipeline_target
                ORDER BY open_actions DESC, pipeline_target DESC, accounts.account_name
                LIMIT 4
            """, open_task_params())
            if row["account_name"]
        ]
    focus_account_text = ", ".join(focus_accounts[:4]) if focus_accounts else "the accounts with the strongest executive route or overdue risk"
    lead_count = dashboard_scalar(connection, """
        SELECT COUNT(*)
        FROM contacts
        WHERE COALESCE(bmc_relationship, '') = 'Lead'
          AND COALESCE(status, 'Active') = 'Active'
    """, default=0)
    executive_count = dashboard_scalar(connection, """
        SELECT COUNT(*)
        FROM contacts
        WHERE COALESCE(status, 'Active') = 'Active'
          AND (
                COALESCE(category, '') = 'Executive'
             OR COALESCE(bmc_relationship, '') IN ('Executive Buyer', 'Executive Assistant')
             OR lower(COALESCE(job_title, '')) LIKE '%chief%'
             OR lower(COALESCE(job_title, '')) LIKE '%vp%'
             OR lower(COALESCE(job_title, '')) LIKE '%vice president%'
             OR lower(COALESCE(job_title, '')) LIKE '%executive%'
             OR lower(COALESCE(job_title, '')) LIKE '%director%'
             OR lower(COALESCE(job_title, '')) LIKE '%head of%'
          )
    """, default=0)
    overdue_account_rows = dashboard_rows(connection, f"""
        SELECT
            accounts.account_name,
            COUNT(outreach.id) AS overdue_actions,
            MIN(outreach.next_action_date) AS oldest_due_date,
            MAX(COALESCE(outreach.next_action, outreach.subject, '')) AS action_hint
        FROM outreach
        LEFT JOIN accounts ON outreach.account_id = accounts.id
        WHERE {overdue_task_sql("outreach")}
        GROUP BY accounts.account_name
        HAVING accounts.account_name IS NOT NULL
        ORDER BY overdue_actions DESC, oldest_due_date ASC, accounts.account_name
        LIMIT 4
    """, overdue_task_params())
    conversion_gap_rows = dashboard_rows(connection, """
        SELECT
            accounts.account_name,
            COUNT(outreach.id) AS activity_count,
            COALESCE(accounts.pipeline_target, 0) AS pipeline_target,
            MAX(COALESCE(outreach.sales_play, accounts.sales_play, '')) AS sales_play
        FROM accounts
        JOIN outreach ON outreach.account_id = accounts.id
        GROUP BY accounts.id, accounts.account_name, accounts.pipeline_target
        HAVING SUM(CASE WHEN outreach.outcome IN ('Discovery Booked', 'NBM Booked', 'Exec Meeting Booked', 'Meeting Booked') THEN 1 ELSE 0 END) = 0
        ORDER BY activity_count DESC, pipeline_target DESC, accounts.account_name
        LIMIT 4
    """)
    executive_gap_rows = dashboard_rows(connection, """
        SELECT
            accounts.account_name,
            COALESCE(accounts.pipeline_target, 0) AS pipeline_target,
            COUNT(contacts.id) AS contact_count
        FROM accounts
        LEFT JOIN contacts ON contacts.account_id = accounts.id
          AND COALESCE(contacts.status, 'Active') = 'Active'
          AND (
                COALESCE(contacts.category, '') = 'Executive'
             OR COALESCE(contacts.bmc_relationship, '') IN ('Executive Buyer', 'Executive Assistant')
             OR lower(COALESCE(contacts.job_title, '')) LIKE '%chief%'
             OR lower(COALESCE(contacts.job_title, '')) LIKE '%vp%'
             OR lower(COALESCE(contacts.job_title, '')) LIKE '%vice president%'
             OR lower(COALESCE(contacts.job_title, '')) LIKE '%executive%'
             OR lower(COALESCE(contacts.job_title, '')) LIKE '%director%'
             OR lower(COALESCE(contacts.job_title, '')) LIKE '%head of%'
          )
        GROUP BY accounts.id, accounts.account_name, accounts.pipeline_target
        HAVING COUNT(contacts.id) = 0
        ORDER BY pipeline_target DESC, accounts.account_name
        LIMIT 4
    """)
    untouched_account_rows = dashboard_rows(connection, f"""
        SELECT
            accounts.account_name,
            COALESCE(accounts.pipeline_target, 0) AS pipeline_target,
            COALESCE(accounts.sales_play, '') AS sales_play,
            COUNT(outreach.id) AS open_actions
        FROM accounts
        LEFT JOIN outreach
          ON outreach.account_id = accounts.id
         AND {open_task_sql("outreach")}
        GROUP BY accounts.id, accounts.account_name, accounts.pipeline_target, accounts.sales_play
        HAVING COUNT(outreach.id) = 0
        ORDER BY pipeline_target DESC, accounts.account_name
        LIMIT 4
    """, open_task_params())
    pg_week = active_pg_week_broadcast()
    bullets = []
    for row in upcoming_rows[:5]:
        account_name = row["account_name"] or "Unknown account"
        due_time = row["next_action_time"] or "time not set"
        action_hint = row["next_action"] or row["activity_type"] or "complete the open action"
        bullets.append(
            f"{account_name}: complete the due action on {display_date(row['next_action_date'])} at {due_time}. "
            f"Use '{action_hint}' to ask for a Discovery Meeting or NBM Meeting, because this account is already in today's work queue and can move quickest toward booked meetings."
        )
    for row in overdue_account_rows[:3]:
        account_name = row["account_name"] or "Unknown account"
        action_hint = row["action_hint"] or "reset the next action"
        bullets.append(
            f"{account_name}: clear {row['overdue_actions']} overdue {pluralise(row['overdue_actions'], 'action')} before adding new activity. "
            f"The oldest due date is {display_date(row['oldest_due_date'])}; update '{action_hint}' into a specific meeting ask so stale work becomes new-business progression."
        )
    for row in conversion_gap_rows[:3]:
        account_name = row["account_name"] or "Unknown account"
        sales_play = row["sales_play"] or "the current sales play"
        bullets.append(
            f"{account_name}: {row['activity_count']} outreach {pluralise(row['activity_count'], 'touchpoint')} exist but no Discovery, NBM or executive meeting is booked. "
            f"Change the route or sharpen {sales_play} into a senior meeting ask so activity converts into pipeline rather than noise."
        )
    for row in executive_gap_rows[:3]:
        account_name = row["account_name"] or "Unknown account"
        bullets.append(
            f"{account_name}: no executive route is mapped yet. Add or identify the senior buyer/assistant path first, then create a focused outreach action aimed at booking a Discovery Meeting."
        )
    for row in untouched_account_rows[:3]:
        account_name = row["account_name"] or "Unknown account"
        sales_play = row["sales_play"] or "a named sales play"
        bullets.append(
            f"{account_name}: there are no open actions, so create the first next step against {sales_play}. "
            f"Use the account's target value to justify a direct Discovery/NBM ask and start generating PG learning."
        )
    if success_accounts:
        bullets.append(f"{success_accounts}: these accounts are proving the meeting-booking pattern with {success_summary}. Reuse the stakeholder route, sales play and timing from them on similar accounts today.")
    if pg_week:
        bullets.append(f"{focus_account_text}: PG week is active, so work at pace on these named accounts. The desired outcome is a scheduled Discovery or NBM meeting, not just completed activity.")
    if lead_count:
        bullets.append(f"{focus_account_text}: {lead_count} active {pluralise(lead_count, 'contact')} still {pluralise(lead_count, 'is', 'are')} marked Lead. Clean the relationship status on the named focus accounts before relying on them for meeting conversion.")
    if overdue_count:
        bullets.append(f"{focus_account_text}: there are {overdue_count} overdue {pluralise(overdue_count, 'action')} across the focus set. Clear them first so new campaign volume is not built on stale follow-up.")
    if untouched_count:
        bullets.append(f"{focus_account_text}: {untouched_count} untouched {pluralise(untouched_count, 'account')} need a confirmed executive route, sales play and dated next action before they can contribute to meeting goals.")
    for insight in execution_insights[:3]:
        bullets.append(f"{focus_account_text}: {insight.get('category', 'Focus')} - {insight.get('action', '')}")
    if not bullets:
        bullets.append(
            f"{focus_account_text}: start here today because these are the best available accounts in the workspace. Add executive contacts, create dated outreach, and record outcomes so PipeFlow can learn what books meetings."
        )
    return format_dashboard_guidance(
        f"Next 24 Hours - {display_date(today)}",
        f"Here is the account-specific focus for {display_date(today)}. Each row names where to act, why it matters, and how the action should create booked meetings or new-business progression.",
        bullets,
        subtitle=display_date(today),
    )


def load_dashboard_weekly_guidance(connection, metric_values, execution_insights):
    now = current_app_datetime()
    today = now.date()
    period_end = today
    period_start = period_end - timedelta(days=6)
    week_key = f"friday-1500-{today.isoformat()}" if today.weekday() == 4 else dashboard_guidance_week_key(today)
    day_key = today.isoformat()
    wrap_key = dashboard_setting(connection, "weekly_wrap_up_key", "")
    focus_key = dashboard_setting(connection, "weekly_ahead_focus_key", "")
    wrap_content = dashboard_setting(connection, "weekly_wrap_up_content", "")
    focus_content = dashboard_setting(connection, "weekly_ahead_focus_content", "")

    should_refresh_wrap = not wrap_content or (today.weekday() == 4 and now.time() >= time(15, 0) and wrap_key != week_key)
    should_refresh_focus = not focus_content or focus_key != day_key
    settings_changed = False

    if should_refresh_wrap:
        generated = generate_weekly_wrap_up(connection, period_start, period_end, metric_values, execution_insights)
        wrap_content = json.dumps(generated)
        save_dashboard_setting(connection, "weekly_wrap_up_key", week_key)
        save_dashboard_setting(connection, "weekly_wrap_up_content", wrap_content)
        settings_changed = True

    if should_refresh_focus:
        generated = generate_next_24_hours_focus(connection, today, metric_values, execution_insights)
        focus_content = json.dumps(generated)
        save_dashboard_setting(connection, "weekly_ahead_focus_key", day_key)
        save_dashboard_setting(connection, "weekly_ahead_focus_content", focus_content)
        settings_changed = True

    if settings_changed:
        commit_with_retry(connection)

    def parse_guidance(payload, fallback_title):
        try:
            parsed = json.loads(payload or "{}")
            if isinstance(parsed, dict):
                return format_dashboard_guidance(fallback_title, parsed.get("lead") or "", parsed.get("bullets") or [], parsed.get("subtitle") or "")
        except json.JSONDecodeError:
            pass
        return format_dashboard_guidance(fallback_title, "", [payload])

    return {
        "weekly_wrap_up": parse_guidance(wrap_content, "Weekly Wrap Up"),
        "weekly_ahead_focus": parse_guidance(focus_content, "Next 24 Hours"),
    }


def build_learning_insights(connection):
    positive_placeholders = ",".join("?" for _ in POSITIVE_OUTCOMES)
    pg_success_placeholders = ",".join("?" for _ in PG_SUCCESS_OUTCOMES)
    primary_pg_success_placeholders = ",".join("?" for _ in PRIMARY_PG_SUCCESS_OUTCOMES)
    nbm_success_placeholders = ",".join("?" for _ in NBM_SUCCESS_OUTCOMES)
    negative_placeholders = ",".join("?" for _ in NEGATIVE_OUTCOMES)
    overdue_predicate = overdue_task_sql("outreach")
    learning_select = f"""
        COUNT(outreach.id) AS total,
        SUM(CASE
            WHEN outreach.outcome IN ({positive_placeholders})
              OR outreach.activity_type = 'Meeting'
            THEN 1 ELSE 0
        END) AS positive_total,
        SUM(CASE
            WHEN outreach.outcome IN ({pg_success_placeholders})
              OR outreach.activity_type = 'Meeting'
            THEN 1 ELSE 0
        END) AS meeting_total,
        SUM(CASE
            WHEN outreach.outcome IN ({primary_pg_success_placeholders})
            THEN 1 ELSE 0
        END) AS primary_pg_success_total,
        SUM(CASE
            WHEN outreach.outcome IN ({nbm_success_placeholders})
            THEN 1 ELSE 0
        END) AS nbm_total,
        SUM(CASE
            WHEN outreach.outcome = 'Exec Meeting Booked'
              OR contacts.category = 'Executive'
              OR contacts.bmc_relationship IN ('Executive Buyer', 'Executive Assistant')
              OR lower(COALESCE(contacts.job_title, '')) LIKE '%chief%'
              OR lower(COALESCE(contacts.job_title, '')) LIKE '%vp%'
              OR lower(COALESCE(contacts.job_title, '')) LIKE '%vice president%'
              OR lower(COALESCE(contacts.job_title, '')) LIKE '%executive%'
              OR lower(COALESCE(contacts.job_title, '')) LIKE '%director%'
              OR lower(COALESCE(contacts.job_title, '')) LIKE '%head of%'
            THEN 1 ELSE 0
        END) AS executive_success_total,
        SUM(CASE
            WHEN outreach.outcome IN ({negative_placeholders})
            THEN 1 ELSE 0
        END) AS negative_total,
        SUM(CASE
            WHEN COALESCE(outreach.task_status, '') IN ('Closed', 'Completed', 'Cancelled')
            THEN 1 ELSE 0
        END) AS completed_total,
        SUM(CASE
            WHEN {overdue_predicate}
            THEN 1 ELSE 0
        END) AS overdue_total
    """
    learning_params = (
        *POSITIVE_OUTCOMES,
        *PG_SUCCESS_OUTCOMES,
        *PRIMARY_PG_SUCCESS_OUTCOMES,
        *NBM_SUCCESS_OUTCOMES,
        *NEGATIVE_OUTCOMES,
        *overdue_task_params(),
    )
    insights = []

    sales_play_rows = add_learning_score(connection.execute(f"""
        SELECT
            outreach.sales_play,
            {learning_select}
        FROM outreach
        LEFT JOIN contacts ON outreach.contact_id = contacts.id
        WHERE outreach.sales_play IS NOT NULL
          AND outreach.sales_play != ''
        GROUP BY outreach.sales_play
    """, learning_params).fetchall())

    for sales_play in sales_play_rows[:3]:
        insights.append({
            "signal": "Sales Play",
            "title": f"{sales_play['sales_play']} is resonating best",
            "message": (
                f"This play has {sales_play['nbm_total']} NBM booking(s), "
                f"{sales_play['primary_pg_success_total']} Discovery/NBM success outcome(s), "
                f"and {sales_play['executive_success_total']} executive route signal(s) from "
                f"{sales_play['total']} touchpoint(s)."
            ),
            "action": "Prioritise this play for executive contacts and use the route that produced Discovery or NBM bookings.",
            "link": url_for("outreach")
        })

    account_rows = add_learning_score(connection.execute(f"""
        SELECT
            accounts.id AS account_id,
            accounts.account_name,
            outreach.sales_play,
            {learning_select}
        FROM outreach
        LEFT JOIN accounts ON outreach.account_id = accounts.id
        LEFT JOIN contacts ON outreach.contact_id = contacts.id
        WHERE accounts.account_name IS NOT NULL
          AND outreach.sales_play IS NOT NULL
          AND outreach.sales_play != ''
        GROUP BY accounts.id, accounts.account_name, outreach.sales_play
    """, learning_params).fetchall())

    for account in account_rows[:3]:
        account_note_rows = connection.execute("""
            SELECT next_action, notes, outcome, activity_type
            FROM outreach
            WHERE account_id = ?
              AND (
                    NULLIF(TRIM(COALESCE(next_action, '')), '') IS NOT NULL
                 OR NULLIF(TRIM(COALESCE(notes, '')), '') IS NOT NULL
              )
            ORDER BY last_updated DESC, id DESC
            LIMIT 8
        """, (account["account_id"],)).fetchall()
        behaviour_action = behaviour_signal_from_notes(
            [row["next_action"] or row["notes"] for row in account_note_rows]
        )
        label_parts = [
            part for part in [account["sales_play"]]
            if part
        ]
        insights.append({
            "signal": "Company",
            "title": f"{account['account_name']} has a working pattern",
            "message": (
                f"{' + '.join(label_parts)} has produced "
                f"{account['nbm_total']} NBM booking(s), "
                f"{account['primary_pg_success_total']} Discovery/NBM success outcome(s), "
                f"and {account['executive_success_total']} executive route signal(s)."
            ),
            "action": behaviour_action,
            "link": url_for("view_account", account_id=account["account_id"])
        })

    contact_category_rows = add_learning_score(connection.execute(f"""
        SELECT
            contacts.category,
            outreach.sales_play,
            {learning_select}
        FROM outreach
        LEFT JOIN contacts ON outreach.contact_id = contacts.id
        WHERE contacts.category IS NOT NULL
          AND contacts.category != ''
          AND outreach.sales_play IS NOT NULL
          AND outreach.sales_play != ''
        GROUP BY contacts.category, outreach.sales_play
    """, learning_params).fetchall())

    for category in contact_category_rows[:2]:
        category_note_rows = connection.execute("""
            SELECT outreach.next_action, outreach.notes
            FROM outreach
            LEFT JOIN contacts ON outreach.contact_id = contacts.id
            WHERE contacts.category = ?
              AND outreach.sales_play = ?
              AND (
                    NULLIF(TRIM(COALESCE(outreach.next_action, '')), '') IS NOT NULL
                 OR NULLIF(TRIM(COALESCE(outreach.notes, '')), '') IS NOT NULL
              )
            ORDER BY outreach.last_updated DESC, outreach.id DESC
            LIMIT 8
        """, (category["category"], category["sales_play"])).fetchall()
        category_action = behaviour_signal_from_notes(
            [row["next_action"] or row["notes"] for row in category_note_rows]
        )
        insights.append({
            "signal": "Contact",
            "title": f"{category['sales_play']} works best with {category['category']} contacts",
            "message": (
                f"This combination has {category['nbm_total']} NBM booking(s), "
                f"{category['primary_pg_success_total']} Discovery/NBM success outcome(s), and "
                f"{category['negative_total']} negative signal(s)."
            ),
            "action": category_action,
            "link": url_for("contacts")
        })

    relationship_rows = add_learning_score(connection.execute(f"""
        SELECT
            contacts.bmc_relationship,
            outreach.sales_play,
            {learning_select}
        FROM outreach
        LEFT JOIN contacts ON outreach.contact_id = contacts.id
        WHERE contacts.bmc_relationship IS NOT NULL
          AND contacts.bmc_relationship != ''
          AND outreach.sales_play IS NOT NULL
          AND outreach.sales_play != ''
        GROUP BY contacts.bmc_relationship, outreach.sales_play
    """, learning_params).fetchall())

    for relationship in relationship_rows[:2]:
        insights.append({
            "signal": "Relationship",
            "title": f"{relationship['sales_play']} is strongest with {relationship['bmc_relationship']} contacts",
            "message": (
                f"The data shows {relationship['primary_pg_success_total']} Discovery/NBM success outcome(s), "
                f"{relationship['nbm_total']} NBM booking(s), and {relationship['positive_total']} positive signal(s) "
                f"from {relationship['total']} touchpoint(s)."
            ),
            "action": "Use this play when a similar executive or buying relationship appears in another account.",
            "link": url_for("contacts")
        })

    failure_rows = add_learning_score(connection.execute(f"""
        SELECT
            outreach.sales_play,
            outreach.activity_type,
            {learning_select}
        FROM outreach
        LEFT JOIN contacts ON outreach.contact_id = contacts.id
        WHERE outreach.sales_play IS NOT NULL
          AND outreach.sales_play != ''
          AND outreach.activity_type IS NOT NULL
          AND outreach.activity_type != ''
        GROUP BY outreach.sales_play, outreach.activity_type
        HAVING SUM(CASE WHEN outreach.outcome IN ({negative_placeholders}) THEN 1 ELSE 0 END) > 0
    """, (*learning_params, *NEGATIVE_OUTCOMES)).fetchall())

    if failure_rows:
        failure_rows.sort(
            key=lambda row: (
                row["negative_total"] or 0,
                row["overdue_total"] or 0,
                row["total"] or 0,
            ),
            reverse=True
        )
        failure = failure_rows[0]
        insights.append({
            "signal": "Failure Indicator",
            "title": f"{failure['activity_type']} is underperforming for {failure['sales_play']}",
            "message": (
                f"This pattern has {failure['negative_total']} negative signal(s) "
                f"from {failure['total']} touchpoint(s)."
            ),
            "action": "Change the channel, refine the message, or switch stakeholder route before repeating this pattern.",
            "link": url_for("outreach")
        })

    stale_open_rows = connection.execute("""
        SELECT
            accounts.id AS account_id,
            accounts.account_name,
            COALESCE(contacts.name, partner_contacts.name) AS contact_name,
            outreach.activity_type,
            outreach.next_action_date,
            outreach.last_updated,
            outreach.notes,
            outreach.next_action,
            CAST(julianday('now') - julianday(COALESCE(NULLIF(outreach.next_action_date, ''), outreach.last_updated, outreach.date_created)) AS INTEGER) AS age_days
        FROM outreach
        LEFT JOIN accounts ON outreach.account_id = accounts.id
        LEFT JOIN contacts ON outreach.contact_id = contacts.id
        LEFT JOIN partner_contacts ON outreach.partner_contact_id = partner_contacts.id
        WHERE COALESCE(outreach.task_status, '') NOT IN ('Closed', 'Completed', 'Cancelled')
        ORDER BY age_days DESC, outreach.last_updated ASC
        LIMIT 1
    """).fetchall()
    if stale_open_rows:
        stale = stale_open_rows[0]
        notes_text = " ".join([stale["notes"] or "", stale["next_action"] or ""]).strip()
        comment_guidance = (
            "The comments are thin, so add what happened, what was learned and the next ask."
            if len(notes_text) < 40
            else "The comments have enough context to decide the next move, so use them to make the next ask specific."
        )
        insights.append({
            "signal": "Open Work",
            "title": f"{stale['account_name'] or 'An account'} has the oldest open outreach thread",
            "message": (
                f"{stale['contact_name'] or 'The contact'} has a {stale['activity_type'] or 'touchpoint'} "
                f"that has been open for about {stale['age_days'] or 0} day(s). {comment_guidance}"
            ),
            "action": "Update the activity with a clear outcome, then either move it to a Discovery/NBM ask or close the loop with a follow-on.",
            "link": url_for("view_account", account_id=stale["account_id"]) if stale["account_id"] else url_for("outreach")
        })

    activity_mix_rows = connection.execute("""
        SELECT
            activity_type,
            COUNT(*) AS total,
            SUM(CASE WHEN outcome IN ('NBM Booked', 'Discovery Booked', 'Exec Meeting Booked', 'Meeting Booked') THEN 1 ELSE 0 END) AS success_total,
            SUM(CASE WHEN outcome IN ('Negative Response', 'Not Relevant') THEN 1 ELSE 0 END) AS negative_total
        FROM outreach
        WHERE COALESCE(activity_type, '') != ''
        GROUP BY activity_type
        HAVING COUNT(*) >= 2
        ORDER BY success_total DESC, negative_total ASC, total DESC
        LIMIT 1
    """).fetchall()
    if activity_mix_rows:
        activity = activity_mix_rows[0]
        insights.append({
            "signal": "Activity Type",
            "title": f"{activity['activity_type']} has the clearest conversion signal",
            "message": (
                f"{activity['activity_type']} has {activity['success_total'] or 0} meeting success outcome(s) "
                f"and {activity['negative_total'] or 0} negative outcome(s) from {activity['total'] or 0} touchpoint(s)."
            ),
            "action": "Use this channel where the account has an executive route, then make the ask explicitly about Discovery or NBM progress.",
            "link": url_for("outreach")
        })

    outcome_gaps = connection.execute("""
        SELECT COUNT(*) AS total
        FROM outreach
        WHERE sales_play IS NOT NULL
          AND sales_play != ''
          AND (
                outcome IS NULL
             OR outcome = ''
             OR outcome IN ('No Response', 'No Response Yet')
        )
    """).fetchone()["total"]

    if not insights and outcome_gaps == 0:
        insights.append({
            "signal": "Learning",
            "title": "Add campaign outcomes to start learning",
            "message": "PipeFlow will compare sales plays, contacts and account patterns once outcomes are captured.",
            "action": "Build a campaign, complete the follow-up tasks, then record the outcome on each touchpoint.",
            "link": url_for("campaign_builder")
        })
    elif outcome_gaps > 0:
        insights.append({
            "signal": "Data Quality",
            "title": f"{outcome_gaps} sales play touchpoint(s) need outcomes",
            "message": "The learning model gets sharper when each campaign step has an outcome.",
            "action": "Update completed touchpoints so the dashboard can recommend what works with more confidence.",
            "link": url_for("tasks")
        })

    return insights[:12]


@app.route("/")
def home():
    connection = get_db_connection()
    if close_expired_completed_outreach(connection):
        connection.commit()
    try:
        return build_dashboard_response(connection)
    except Exception as exc:
        print(f"Dashboard failed: {exc!r}", file=sys.stderr)
        traceback.print_exc()
        return render_dashboard_fallback(connection)
    finally:
        connection.close()


@app.route("/insights/next-24-hours/refresh", methods=("POST",))
def refresh_next_24_hours():
    connection = get_db_connection()
    try:
        metric_values = dashboard_metric_fallback_values(connection)
        learning_insights = build_learning_insights(connection)
        execution_insights = build_dashboard_strategy_insights(connection, metric_values, learning_insights=learning_insights)
        today = current_app_datetime().date()
        generated = generate_next_24_hours_focus(connection, today, metric_values, execution_insights)
        save_dashboard_setting(connection, "weekly_ahead_focus_key", today.isoformat())
        save_dashboard_setting(connection, "weekly_ahead_focus_content", json.dumps(generated))
        connection.commit()
        return redirect(url_for("home", message="Next 24 Hours refreshed."))
    except Exception:
        connection.rollback()
        traceback.print_exc()
        return redirect(url_for("home", error="Next 24 Hours could not be refreshed."))
    finally:
        connection.close()


def dashboard_metric_fallback_values(connection):
    values = {
        "this_week_due": 0,
        "this_week_completed": 0,
        "this_week_overdue": 0,
        "this_week_untouched_accounts": 0,
        "this_week_meetings_booked": 0,
        "total_accounts": 0,
        "total_contacts": 0,
        "total_outreach": 0,
        "total_pg_target": 0,
        "meetings_booked": 0,
        "follow_ups_due": 0,
    }
    try:
        now = current_app_datetime()
        today = now.date()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        values["total_accounts"] = connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
        values["total_contacts"] = connection.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
        values["total_outreach"] = connection.execute("SELECT COUNT(*) FROM outreach").fetchone()[0]
        values["total_pg_target"] = connection.execute("SELECT COALESCE(SUM(pipeline_target), 0) FROM accounts").fetchone()[0]
        rows = connection.execute("SELECT * FROM outreach").fetchall()
        for row in rows:
            next_date = None
            activity_date = None
            try:
                next_date = datetime.strptime(str(row["next_action_date"]), "%Y-%m-%d").date() if row["next_action_date"] else None
            except ValueError:
                next_date = None
            try:
                activity_date = datetime.strptime(str(row["activity_date"]), "%Y-%m-%d").date() if row["activity_date"] else None
            except ValueError:
                activity_date = None
            closed = is_closed_task_status(row["task_status"])
            if next_date and week_start <= next_date <= week_end and not closed:
                values["this_week_due"] += 1
            if is_overdue_task(row["next_action_date"], row["next_action_time"], row["task_status"], now):
                values["this_week_overdue"] += 1
            if closed:
                try:
                    updated_date = datetime.strptime(str(row["last_updated"] or "")[:10], "%Y-%m-%d").date()
                except ValueError:
                    updated_date = None
                if updated_date and week_start <= updated_date <= week_end:
                    values["this_week_completed"] += 1
            if activity_date and week_start <= activity_date <= week_end and is_pg_success_outcome(row["outcome"], row["activity_type"]):
                values["this_week_meetings_booked"] += 1
            if next_date and next_date <= today + timedelta(days=7) and not closed:
                values["follow_ups_due"] += 1
            if is_pg_success_outcome(row["outcome"], row["activity_type"]):
                values["meetings_booked"] += 1
        values["this_week_untouched_accounts"] = connection.execute(f"""
            SELECT COUNT(*)
            FROM accounts
            WHERE NOT EXISTS (
                SELECT 1
                FROM outreach
                WHERE outreach.account_id = accounts.id
                  AND {open_task_sql("outreach")}
                  AND (
                        NULLIF(TRIM(COALESCE(outreach.sales_play, '')), '') IS NOT NULL
                     OR NULLIF(TRIM(COALESCE(outreach.next_action, '')), '') IS NOT NULL
                  )
            )
        """, open_task_params()).fetchone()[0]
    except Exception:
        traceback.print_exc()
    return values


def render_dashboard_fallback(connection=None):
    metric_values = dashboard_metric_fallback_values(connection) if connection else {}
    now = current_app_datetime()
    week_start = now.date() - timedelta(days=now.date().weekday())
    fallback_insights = build_dashboard_strategy_insights(connection, metric_values) if connection else []
    weekly_guidance = {}
    if connection:
        try:
            weekly_guidance = load_dashboard_weekly_guidance(connection, metric_values, fallback_insights)
        except Exception:
            traceback.print_exc()
    if not weekly_guidance:
        weekly_guidance = {
            "weekly_wrap_up": format_dashboard_guidance(
                "Weekly Wrap Up",
                "Key success areas and execution signals from the past week.",
                ["Keep account, contact, outreach and outcome data current so PipeFlow can sharpen execution guidance."],
            ),
            "weekly_ahead_focus": format_dashboard_guidance(
                "Next 24 Hours",
                "Strategic focus for where to spend deliberate PG time in the week ahead.",
                ["Prioritise executive coverage, overdue action clearance and Discovery or NBM asks."],
            ),
        }
    return render_template(
        "index.html",
        this_week_due=metric_values.get("this_week_due", 0),
        this_week_completed=metric_values.get("this_week_completed", 0),
        this_week_overdue=metric_values.get("this_week_overdue", 0),
        this_week_untouched_accounts=metric_values.get("this_week_untouched_accounts", 0),
        this_week_meetings_booked=metric_values.get("this_week_meetings_booked", 0),
        this_week_start=week_start.isoformat(),
        this_week_end=(week_start + timedelta(days=6)).isoformat(),
        total_accounts=metric_values.get("total_accounts", 0),
        total_contacts=metric_values.get("total_contacts", 0),
        total_outreach=metric_values.get("total_outreach", 0),
        total_pg_target=metric_values.get("total_pg_target", 0),
        meetings_booked=metric_values.get("meetings_booked", 0),
        follow_ups_due=metric_values.get("follow_ups_due", 0),
        latest_outreach=[],
        outreach_by_account=[],
        outcome_breakdown=[],
        top_accounts=[],
        needs_attention_accounts=[],
        ai_insights=[],
        learning_insights=[],
        execution_insights=fallback_insights,
        weekly_wrap_up=weekly_guidance["weekly_wrap_up"],
        weekly_ahead_focus=weekly_guidance["weekly_ahead_focus"],
        dashboard_tasks=[],
        task_statuses=DROPDOWN_VALUES["task_statuses"],
        outreach_outcomes=DROPDOWN_VALUES["outreach_outcomes"],
        broadcast_messages=list_broadcast_messages(active_only=True)
    )


def build_dashboard_response(connection):

    total_accounts = connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
    total_contacts = connection.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
    total_outreach = connection.execute("SELECT COUNT(*) FROM outreach").fetchone()[0]
    total_pg_target = connection.execute("""
        SELECT COALESCE(SUM(pipeline_target), 0)
        FROM accounts
    """).fetchone()[0]
    now = current_app_datetime()
    today = now.date()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    week_start_key = week_start.isoformat()
    week_end_key = week_end.isoformat()

    all_accounts = connection.execute("""
        SELECT id, account_name, pipeline_target
        FROM accounts
    """).fetchall()

    weekly_outreach_rows = connection.execute("""
        SELECT
            outreach.*,
            accounts.pipeline_target
        FROM outreach
        LEFT JOIN accounts ON outreach.account_id = accounts.id
    """).fetchall()

    def parse_dashboard_date(value):
        if not value:
            return None
        try:
            return datetime.strptime(str(value), "%Y-%m-%d").date()
        except ValueError:
            return None

    def task_closed(row):
        return is_closed_task_status(row["task_status"])

    this_week_due = 0
    this_week_completed = 0
    this_week_overdue = 0
    this_week_meetings_booked = 0

    for row in weekly_outreach_rows:
        next_action_date = parse_dashboard_date(row["next_action_date"])
        activity_date = parse_dashboard_date(row["activity_date"])

        if next_action_date and week_start <= next_action_date <= week_end and not task_closed(row):
            this_week_due += 1

        if is_overdue_task(row["next_action_date"], row["next_action_time"], row["task_status"], now):
            this_week_overdue += 1

        if task_closed(row):
            last_updated_date = parse_dashboard_date(str(row["last_updated"] or "")[:10])
            if last_updated_date and week_start <= last_updated_date <= week_end:
                this_week_completed += 1

        if activity_date and week_start <= activity_date <= week_end:
            if is_pg_success_outcome(row["outcome"], row["activity_type"]):
                this_week_meetings_booked += 1

    this_week_untouched_accounts = connection.execute(f"""
        SELECT COUNT(*)
        FROM accounts
        WHERE NOT EXISTS (
            SELECT 1
            FROM outreach
            WHERE outreach.account_id = accounts.id
              AND {open_task_sql("outreach")}
              AND (
                    (outreach.sales_play IS NOT NULL AND outreach.sales_play != '')
                 OR (outreach.next_action IS NOT NULL AND outreach.next_action != '')
              )
        )
    """, open_task_params()).fetchone()[0]

    meetings_booked = connection.execute("""
        SELECT COUNT(*) FROM outreach
        WHERE outcome IN ('Discovery Booked', 'NBM Booked', 'Exec Meeting Booked', 'Meeting Booked')
           OR activity_type = 'Meeting'
    """).fetchone()[0]

    follow_ups_due = connection.execute(f"""
        SELECT COUNT(*) FROM outreach
        WHERE next_action_date IS NOT NULL
          AND next_action_date != ''
          AND date(next_action_date) <= date(?)
          AND {open_task_sql("outreach")}
    """, ((today + timedelta(days=7)).isoformat(), *open_task_params())).fetchone()[0]

    outreach_by_account = connection.execute("""
        SELECT
            accounts.account_name,
            outreach.activity_type,
            COUNT(*) as total
        FROM outreach
        LEFT JOIN accounts ON outreach.account_id = accounts.id
        GROUP BY accounts.account_name, outreach.activity_type
        ORDER BY accounts.account_name
    """).fetchall()

    outcome_breakdown = connection.execute("""
        SELECT outcome, COUNT(*) AS total
        FROM outreach
        WHERE outcome IS NOT NULL
          AND outcome != ''
        GROUP BY outcome
        ORDER BY total DESC
    """).fetchall()

    top_accounts = connection.execute("""
        SELECT accounts.account_name, COUNT(outreach.id) AS total
        FROM outreach
        LEFT JOIN accounts ON outreach.account_id = accounts.id
        WHERE accounts.account_name IS NOT NULL
        GROUP BY accounts.account_name
        ORDER BY total DESC
        LIMIT 5
    """).fetchall()

    latest_outreach = connection.execute("""
        SELECT
            outreach.*,
            accounts.account_name,
            accounts.account_tier,
            contacts.name AS contact_name,
            contacts.job_title AS contact_job_title,
            contacts.email AS contact_email,
            contacts.phone AS contact_phone,
            contacts.linkedin AS contact_linkedin
        FROM outreach
        LEFT JOIN accounts ON outreach.account_id = accounts.id
        LEFT JOIN contacts ON outreach.contact_id = contacts.id
        ORDER BY outreach.activity_date DESC, outreach.activity_time DESC
        LIMIT 5
    """).fetchall()

    dashboard_tasks = connection.execute(f"""
        SELECT outreach.*, accounts.account_name, accounts.account_tier, contacts.name AS contact_name
        FROM outreach
        LEFT JOIN accounts ON outreach.account_id = accounts.id
        LEFT JOIN contacts ON outreach.contact_id = contacts.id
        WHERE outreach.next_action IS NOT NULL
          AND outreach.next_action != ''
          AND outreach.next_action_date IS NOT NULL
          AND outreach.next_action_date != ''
          AND {open_task_sql("outreach")}
        ORDER BY
            CASE WHEN {overdue_task_sql("outreach")} THEN 0 ELSE 1 END,
            outreach.next_action_date ASC,
            outreach.next_action_time ASC
        LIMIT 8
    """, (*open_task_params(), *overdue_task_params(now))).fetchall()

    account_health_rows = connection.execute(f"""
        SELECT 
            accounts.*,

            (
                SELECT COUNT(*)
                FROM contacts
                WHERE contacts.account_id = accounts.id
            ) AS contact_count,

            (
                SELECT COUNT(*)
                FROM outreach
                WHERE outreach.account_id = accounts.id
            ) AS outreach_count,

            (
                SELECT COUNT(*)
                FROM outreach
                WHERE outreach.account_id = accounts.id
                  AND (
                        outreach.outcome IN ('Discovery Booked', 'NBM Booked', 'Exec Meeting Booked', 'Meeting Booked')
                     OR outreach.activity_type = 'Meeting'
                  )
            ) AS meeting_count,

            (
                SELECT COUNT(*)
                FROM outreach
                WHERE outreach.account_id = accounts.id
                  AND outreach.outcome IN ('Discovery Booked', 'NBM Booked')
            ) AS primary_pg_success_count,

            (
                SELECT COUNT(*)
                FROM outreach
                WHERE outreach.account_id = accounts.id
                  AND outreach.outcome = 'NBM Booked'
            ) AS nbm_success_count,

            (
                SELECT COUNT(*)
                FROM contacts
                WHERE contacts.account_id = accounts.id
                  AND (
                        contacts.category = 'Executive'
                     OR contacts.bmc_relationship IN ('Executive Buyer', 'Executive Assistant')
                     OR lower(COALESCE(contacts.job_title, '')) LIKE '%chief%'
                     OR lower(COALESCE(contacts.job_title, '')) LIKE '%vp%'
                     OR lower(COALESCE(contacts.job_title, '')) LIKE '%vice president%'
                     OR lower(COALESCE(contacts.job_title, '')) LIKE '%executive%'
                     OR lower(COALESCE(contacts.job_title, '')) LIKE '%director%'
                     OR lower(COALESCE(contacts.job_title, '')) LIKE '%head of%'
                  )
            ) AS executive_contact_count,

            (
                SELECT COUNT(*)
                FROM outreach
                WHERE outreach.account_id = accounts.id
                  AND {overdue_task_sql("outreach")}
            ) AS overdue_followups,

            (
                SELECT MAX(outreach.activity_date)
                FROM outreach
                WHERE outreach.account_id = accounts.id
            ) AS latest_outreach_date,

            (
                SELECT COUNT(*)
                FROM account_partners
                WHERE account_partners.account_id = accounts.id
            ) AS partner_count,

            (
                SELECT COUNT(*)
                FROM account_partners
                WHERE account_partners.account_id = accounts.id
                  AND account_partners.involvement_status IN ('Introduced', 'Engaged', 'Active')
            ) AS active_partner_count,

            (
                SELECT COUNT(*)
                FROM account_partners
                WHERE account_partners.account_id = accounts.id
                  AND account_partners.involvement_status IN ('Introduced', 'Engaged', 'Active')
                  AND (
                        account_partners.next_action IS NULL
                     OR account_partners.next_action = ''
                  )
            ) AS active_partner_next_action_gaps

        FROM accounts
        ORDER BY accounts.account_name
    """, overdue_task_params(now)).fetchall()

    needs_attention_accounts = []
    ai_insights = []

    for row in account_health_rows:
        account = dict(row)

        health = calculate_account_health(
            contact_count=account["contact_count"] or 0,
            outreach_count=account["outreach_count"] or 0,
            meeting_count=account["meeting_count"] or 0,
            overdue_followups=account["overdue_followups"] or 0,
            latest_outreach_date=account["latest_outreach_date"]
        )

        account["health_label"] = health["label"]
        account["health_colour"] = health["colour"]
        account["health_reason"] = health["reason"]

        if account["health_colour"] in ["red", "amber", "yellow"]:
            needs_attention_accounts.append(account)

        if (account["contact_count"] or 0) < 2:
            ai_insights.append({
                "type": "Relationship Gap",
                "severity": "high",
                "title": f"{account['account_name']} has low relationship coverage",
                "message": "There are fewer than 2 contacts mapped. Add more stakeholders to reduce single-thread risk.",
                "action": "Add at least one additional stakeholder, prioritising an executive buyer, executive assistant or senior sponsor.",
                "link": url_for("view_account", account_id=account["id"])
            })

        if (account["executive_contact_count"] or 0) == 0:
            ai_insights.append({
                "type": "Executive Gap",
                "severity": "high",
                "title": f"{account['account_name']} has no executive route mapped",
                "message": "PG success needs executive access. Add an executive buyer, executive assistant or senior sponsor before relying on more lower-level follow-up.",
                "action": "Map at least one executive stakeholder, executive assistant or senior sponsor, then set the next action around a Discovery or NBM ask.",
                "link": url_for("view_account", account_id=account["id"])
            })
        elif (account["primary_pg_success_count"] or 0) == 0:
            ai_insights.append({
                "type": "Executive Route",
                "severity": "medium",
                "title": f"{account['account_name']} has an executive route but no PG success yet",
                "message": f"{account['executive_contact_count']} executive route contact(s) are mapped, but no Discovery or NBM booking has been recorded.",
                "action": "Use the mapped executive route for the next touchpoint and make the ask specifically about Discovery or NBM.",
                "link": url_for("view_account", account_id=account["id"])
            })

        if (account["overdue_followups"] or 0) > 0:
            ai_insights.append({
                "type": "Action Risk",
                "severity": "high",
                "title": f"{account['account_name']} has overdue follow-ups",
                "message": f"{account['overdue_followups']} follow-up(s) are overdue. Review next actions before momentum drops.",
                "action": "Clear the overdue work first, then reset the next action toward an executive Discovery or NBM step.",
                "link": url_for("view_account", account_id=account["id"])
            })

        if (account["outreach_count"] or 0) > 0 and (account["primary_pg_success_count"] or 0) == 0:
            ai_insights.append({
                "type": "PG Conversion Gap",
                "severity": "medium",
                "title": f"{account['account_name']} has outreach but no Discovery or NBM booked",
                "message": "Activity is happening, but the PG success outcome is missing. Change route toward an executive stakeholder or sharpen the Discovery/NBM ask.",
                "action": "Change the route or message before adding more activity; aim the next touchpoint at Discovery Booked or NBM Booked.",
                "link": url_for("view_account", account_id=account["id"])
            })

        contact_context_rows = connection.execute("""
            SELECT
                name,
                job_title,
                category,
                org_dept,
                responsibilities,
                bmc_relationship,
                characteristics,
                background,
                personal_interests,
                personal_win,
                additional_notes
            FROM contacts
            WHERE account_id = ?
            ORDER BY
                CASE
                    WHEN category = 'Executive'
                      OR bmc_relationship IN ('Executive Buyer', 'Executive Assistant')
                      OR lower(COALESCE(job_title, '')) LIKE '%chief%'
                      OR lower(COALESCE(job_title, '')) LIKE '%vp%'
                      OR lower(COALESCE(job_title, '')) LIKE '%vice president%'
                      OR lower(COALESCE(job_title, '')) LIKE '%executive%'
                      OR lower(COALESCE(job_title, '')) LIKE '%director%'
                      OR lower(COALESCE(job_title, '')) LIKE '%head of%'
                    THEN 0 ELSE 1
                END,
                CASE WHEN bmc_relationship IS NULL OR bmc_relationship = '' THEN 1 ELSE 0 END,
                CASE WHEN responsibilities IS NULL OR responsibilities = '' THEN 1 ELSE 0 END,
                name
            LIMIT 5
        """, (account["id"],)).fetchall()

        if contact_context_rows:
            best_contact = contact_context_rows[0]
            contact_label = ", ".join(part for part in [best_contact["name"], best_contact["job_title"]] if part) or "the best mapped contact"
            reason = (
                best_contact["personal_win"]
                or best_contact["responsibilities"]
                or best_contact["bmc_relationship"]
                or best_contact["characteristics"]
                or best_contact["additional_notes"]
                or ""
            )
            reason = str(reason).strip()
            if reason:
                recommended_move = behaviour_signal_from_notes([reason])
                route_label = "executive route" if is_executive_contact(best_contact["category"], best_contact["bmc_relationship"], best_contact["job_title"]) else "stakeholder route"
                ai_insights.append({
                    "type": "Engagement Route",
                    "severity": "medium",
                    "title": f"Use a sharper {route_label} into {account['account_name']}",
                    "message": f"Start with {contact_label}. {recommended_move}",
                    "action": "Use this route for the next executive-facing touchpoint and record whether it converts to Discovery or NBM.",
                    "link": url_for("view_account", account_id=account["id"])
                })

        if (account["partner_count"] or 0) == 0 and (account["outreach_count"] or 0) > 0:
            ai_insights.append({
                "type": "Partner Gap",
                "severity": "medium",
                "title": f"{account['account_name']} has no partner involvement mapped",
                "message": "This account has activity but no partner coverage. Add a relevant partner to test a warmer route in.",
                "action": "Add a partner route if it can help secure executive access or support the Discovery/NBM ask.",
                "link": url_for("view_account", account_id=account["id"])
            })

        if (account["partner_count"] or 0) > 0 and (account["active_partner_count"] or 0) == 0:
            ai_insights.append({
                "type": "Partner Activation",
                "severity": "medium",
                "title": f"{account['account_name']} has partner coverage but no active partner",
                "message": "Partner relationships are mapped, but none are introduced, engaged or active. Pick the best partner and set a next action.",
                "action": "Activate the strongest partner route and align it to the executive stakeholder or NBM target.",
                "link": url_for("view_account", account_id=account["id"])
            })

        if (account["active_partner_next_action_gaps"] or 0) > 0:
            ai_insights.append({
                "type": "Partner Next Step",
                "severity": "medium",
                "title": f"{account['account_name']} has active partner involvement without a next action",
                "message": f"{account['active_partner_next_action_gaps']} active partner relationship(s) need a clear next action.",
                "action": "Set the partner next action around gaining executive access, booking Discovery or progressing to NBM.",
                "link": url_for("view_account", account_id=account["id"])
            })

        if (account["outreach_count"] or 0) >= 3 and (account["primary_pg_success_count"] or 0) > 0:
            ai_insights.append({
                "type": "PG Momentum",
                "severity": "positive",
                "title": f"{account['account_name']} is converting toward PG outcomes",
                "message": f"This account has {account['primary_pg_success_count']} Discovery/NBM success outcome(s). Keep progressing next actions toward NBM completion.",
                "action": "Protect the momentum by keeping the executive path warm and confirming the next NBM or follow-on action.",
                "link": url_for("view_account", account_id=account["id"])
            })

        if (account["nbm_success_count"] or 0) > 0:
            ai_insights.append({
                "type": "NBM Success",
                "severity": "positive",
                "title": f"{account['account_name']} has NBM booked",
                "message": f"{account['nbm_success_count']} NBM booking(s) recorded. Treat this as the strongest PG success signal and keep the executive path warm.",
                "action": "Prepare the NBM follow-through and capture the outcome so future campaign learning can reuse the pattern.",
                "link": url_for("view_account", account_id=account["id"])
            })

        if (account["active_partner_count"] or 0) >= 2 and (account["primary_pg_success_count"] or 0) > 0:
            ai_insights.append({
                "type": "Partner Momentum",
                "severity": "positive",
                "title": f"{account['account_name']} has strong partner coverage",
                "message": "Multiple active partner relationships are mapped alongside Discovery/NBM success. Keep partner owners aligned on the next executive move.",
                "action": "Keep partner owners aligned to the next executive action and record whether the partner route helped the booking.",
                "link": url_for("view_account", account_id=account["id"])
            })

        if account["latest_outreach_date"]:
            latest_outreach_date = parse_dashboard_date(str(account["latest_outreach_date"])[:10])
            days_since_outreach = (today - latest_outreach_date).days if latest_outreach_date else None

            if days_since_outreach is not None and days_since_outreach >= 14:
                ai_insights.append({
                    "type": "Going Cold",
                    "severity": "medium",
                    "title": f"{account['account_name']} has had no outreach for {days_since_outreach} days",
                    "message": "This account may be going cold. Add a relevant touchpoint or next action.",
                    "action": "Restart with an executive-facing touchpoint or partner-backed route rather than a generic follow-up.",
                    "link": url_for("view_account", account_id=account["id"])
                })

    health_order = {
        "red": 1,
        "amber": 2,
        "yellow": 3,
        "green": 4
    }

    needs_attention_accounts.sort(
        key=lambda account: (
            health_order.get(account["health_colour"], 99),
            account["account_name"].lower()
        )
    )

    needs_attention_accounts = needs_attention_accounts[:5]
    metric_values = {
        "this_week_due": this_week_due,
        "this_week_completed": this_week_completed,
        "this_week_overdue": this_week_overdue,
        "this_week_untouched_accounts": this_week_untouched_accounts,
        "this_week_meetings_booked": this_week_meetings_booked,
        "total_accounts": total_accounts,
        "total_contacts": total_contacts,
        "total_outreach": total_outreach,
        "total_pg_target": total_pg_target,
        "meetings_booked": meetings_booked,
        "follow_ups_due": follow_ups_due,
    }
    try:
        learning_insights = build_learning_insights(connection)
    except Exception:
        traceback.print_exc()
        learning_insights = []

    insight_order = {
        "high": 1,
        "medium": 2,
        "positive": 3
    }

    ai_insights.sort(
        key=lambda insight: insight_order.get(insight["severity"], 99)
    )

    ai_insights = ai_insights[:6]
    execution_insights = deduplicate_execution_insights(
        build_dashboard_strategy_insights(connection, metric_values, account_health_rows, learning_insights)
        + build_execution_insights(ai_insights, learning_insights)
    )
    if not execution_insights:
        execution_insights = [{
            "source": "AI Insight",
            "category": "PG Focus",
            "title": "Build an executive route for PG success",
            "message": "Add accounts, executive contacts and outreach outcomes so PipeFlow can identify where Discovery and NBM bookings are most likely.",
            "action": "Start by mapping an executive stakeholder, then record Discovery Booked or NBM Booked outcomes as they happen.",
            "link": url_for("accounts"),
            "priority": "medium",
        }]
    execution_insights = execution_insights[:12]
    try:
        weekly_guidance = load_dashboard_weekly_guidance(connection, metric_values, execution_insights)
    except Exception:
        traceback.print_exc()
        weekly_guidance = {
            "weekly_wrap_up": format_dashboard_guidance(
                "Weekly Wrap Up",
                "Key success areas and execution signals from the past week.",
                ["Review this week's successes, overdue work and account coverage to plan the next PG move."],
            ),
            "weekly_ahead_focus": format_dashboard_guidance(
                "Next 24 Hours",
                "Strategic focus for where to spend deliberate PG time in the week ahead.",
                ["Focus on executive routes, Discovery Booked outcomes and NBM Booked progression."],
            ),
        }

    return render_template(
        "index.html",
        this_week_due=this_week_due,
        this_week_completed=this_week_completed,
        this_week_overdue=this_week_overdue,
        this_week_untouched_accounts=this_week_untouched_accounts,
        this_week_meetings_booked=this_week_meetings_booked,
        this_week_start=week_start_key,
        this_week_end=week_end_key,
        total_accounts=total_accounts,
        total_contacts=total_contacts,
        total_outreach=total_outreach,
        total_pg_target=total_pg_target,
        meetings_booked=meetings_booked,
        follow_ups_due=follow_ups_due,
        latest_outreach=latest_outreach,
        outreach_by_account=outreach_by_account,
        outcome_breakdown=outcome_breakdown,
        top_accounts=top_accounts,
        needs_attention_accounts=needs_attention_accounts,
        ai_insights=ai_insights,
        learning_insights=learning_insights,
        execution_insights=execution_insights,
        weekly_wrap_up=weekly_guidance["weekly_wrap_up"],
        weekly_ahead_focus=weekly_guidance["weekly_ahead_focus"],
        dashboard_tasks=dashboard_tasks,
        task_statuses=DROPDOWN_VALUES["task_statuses"],
        outreach_outcomes=DROPDOWN_VALUES["outreach_outcomes"],
        broadcast_messages=list_broadcast_messages(active_only=True)
    )


def dashboard_setting(connection, key, default=""):
    row = connection.execute(
        "SELECT setting_value FROM dashboard_settings WHERE setting_key = ?",
        (key,),
    ).fetchone()
    return row["setting_value"] if row else default


def save_dashboard_setting(connection, key, value):
    existing = connection.execute(
        "SELECT setting_key FROM dashboard_settings WHERE setting_key = ?",
        (key,),
    ).fetchone()
    if existing:
        connection.execute("""
            UPDATE dashboard_settings
            SET setting_value = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE setting_key = ?
        """, (value, key))
    else:
        connection.execute(
            "INSERT INTO dashboard_settings (setting_key, setting_value) VALUES (?, ?)",
            (key, value),
        )


def contact_has_recent_or_open_activity(connection, contact_id, cutoff_date):
    row = connection.execute(f"""
        SELECT
            MAX(NULLIF(activity_date, '')) AS latest_activity_date,
            SUM(CASE WHEN {open_task_sql("outreach")} THEN 1 ELSE 0 END) AS open_count
        FROM outreach
        WHERE contact_id = ?
           OR id IN (
                SELECT outreach_id
                FROM outreach_recipients
                WHERE contact_id = ?
           )
    """, (*open_task_params(), contact_id, contact_id)).fetchone()
    if not row:
        return False
    if (row["open_count"] or 0) > 0:
        return True
    latest = row["latest_activity_date"]
    if not latest:
        return False
    try:
        return datetime.strptime(str(latest)[:10], "%Y-%m-%d").date() >= cutoff_date
    except ValueError:
        return False


def money_value(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def nbm_colour_index(value):
    try:
        number = int(str(value or "0"))
    except ValueError:
        number = 0
    return number % 12


def pg_progress_rag_status(outcomes, discovery_values=None, nbm_values=None):
    discovery_values = [str(value or "").strip() for value in (discovery_values or [])]
    nbm_values = [str(value or "").strip() for value in (nbm_values or [])]
    if any(value == "Yes" for value in nbm_values):
        return {
            "status": "green",
            "label": "Green",
            "reason": "NBM meeting marked as completed",
        }
    if any(value == "Yes" for value in discovery_values):
        return {
            "status": "amber",
            "label": "Amber",
            "reason": "Discovery meeting marked as completed",
        }
    if any(value == "No" for value in (*discovery_values, *nbm_values)):
        return {
            "status": "red",
            "label": "Red",
            "reason": "Meeting progression marked as no",
        }
    normalised = [normalise_outreach_outcome(outcome) for outcome in outcomes if str(outcome or "").strip()]
    if any(outcome in ("NBM Booked", "Exec Meeting Booked") for outcome in normalised):
        return {
            "status": "green",
            "label": "Green",
            "reason": "NBM or executive meeting booked",
        }
    if any(outcome in (*NEGATIVE_OUTCOMES, "Positive Response", "Discovery Booked", "Meeting Booked") for outcome in normalised):
        return {
            "status": "amber",
            "label": "Amber",
            "reason": "Response or Discovery meeting signal recorded",
        }
    return {
        "status": "red",
        "label": "Red",
        "reason": "No response signal recorded",
    }


def aggregate_pg_progress_rag(contact_rags):
    contact_rags = [rag for rag in contact_rags if rag]
    if any(rag["status"] == "green" for rag in contact_rags):
        return {
            "status": "green",
            "label": "Green",
            "reason": "At least one active contact has NBM or executive meeting evidence",
        }
    if any(rag["status"] == "amber" for rag in contact_rags):
        return {
            "status": "amber",
            "label": "Amber",
            "reason": "At least one active contact has a response or Discovery meeting signal",
        }
    return {
        "status": "red",
        "label": "Red",
        "reason": "No active contact has a response or meeting signal",
    }


def contact_pg_progress_rag(connection, account_id, contact_id, legacy_action_update=None):
    action_update = connection.execute("""
        SELECT *
        FROM pg_action_contact_updates
        WHERE contact_id = ?
    """, (contact_id,)).fetchone()
    discovery_meeting_count = connection.execute("""
        SELECT COUNT(*)
        FROM outreach
        WHERE account_id = ?
          AND (
                contact_id = ?
             OR id IN (
                    SELECT outreach_id
                    FROM outreach_recipients
                    WHERE contact_id = ?
                )
          )
          AND (
                outcome = 'Discovery Booked'
             OR outcome = 'Meeting Booked'
             OR activity_type = 'Meeting'
          )
    """, (account_id, contact_id, contact_id)).fetchone()[0]
    manual_completed_discovery = (
        action_update["completed_discovery_meeting"]
        if action_update
        else (legacy_action_update["completed_discovery_meeting"] if legacy_action_update else "")
    )
    contact_outcome_rows = connection.execute("""
        SELECT outcome
        FROM outreach
        WHERE account_id = ?
          AND (
                contact_id = ?
             OR id IN (
                    SELECT outreach_id
                    FROM outreach_recipients
                    WHERE contact_id = ?
                )
          )
    """, (account_id, contact_id, contact_id)).fetchall()
    completed_discovery = manual_completed_discovery or ("Yes" if discovery_meeting_count else "")
    nbm_completed = action_update["nbm_completed"] if action_update and "nbm_completed" in action_update.keys() else ""
    return {
        "action_update": action_update,
        "completed_discovery": completed_discovery,
        "nbm_completed": nbm_completed,
        "rag": pg_progress_rag_status(
            [row["outcome"] for row in contact_outcome_rows],
            [completed_discovery],
            [nbm_completed],
        ),
    }


def activity_update_is_valid(value):
    return len((value or "").strip()) >= 5


def status_requires_activity_update(status):
    return is_closed_task_status(status)


def parse_due_time(value):
    value = str(value or "").strip()
    if not value:
        return time(23, 59, 59)
    for time_format in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(value, time_format).time()
        except ValueError:
            continue
    return None


def due_rag_class(next_action_date, next_action_time, task_status):
    if is_closed_task_status(task_status):
        return ""
    if not next_action_date:
        return ""
    try:
        due_date = datetime.strptime(next_action_date, "%Y-%m-%d").date()
        due_time_value = parse_due_time(next_action_time)
        if due_time_value is None:
            return ""
        due_at = datetime.combine(due_date, due_time_value, tzinfo=APP_TIMEZONE)
    except (TypeError, ValueError):
        return ""
    now = datetime.now(APP_TIMEZONE)
    if now >= due_at + timedelta(seconds=1):
        return "rag-red"
    return ""


def contact_matches_account(connection, account_id, contact_id):
    if not contact_id:
        return True
    if not account_id:
        return False

    match = connection.execute(
        """
        SELECT id
        FROM contacts
        WHERE id = ?
          AND account_id = ?
        """,
        (contact_id, account_id),
    ).fetchone()
    return bool(match)


def parse_outreach_contact_selection(value):
    value = str(value or "").strip()
    if value.startswith("partner_contact:"):
        return None, value.split(":", 1)[1] or None
    return value or None, None


def parse_outreach_contact_selections(values):
    recipients = []
    seen = set()
    for value in values:
        contact_id, partner_contact_id = parse_outreach_contact_selection(value)
        if not contact_id and not partner_contact_id:
            continue
        key = (str(contact_id or ""), str(partner_contact_id or ""))
        if key in seen:
            continue
        seen.add(key)
        recipients.append((contact_id, partner_contact_id))
    return recipients


def outreach_contact_form_values(form):
    values = form.getlist("contact_ids")
    if not values:
        values = form.getlist("contact_id")
    single_value = form.get("contact_id")
    if single_value and single_value not in values:
        values.insert(0, single_value)
    return values


def partner_contact_matches_account(connection, account_id, partner_contact_id):
    if not partner_contact_id:
        return True
    if not account_id:
        return False
    match = connection.execute("""
        SELECT id
        FROM partner_contacts
        WHERE id = ?
          AND (
                account_id = ?
             OR id IN (
                    SELECT partner_contact_id
                    FROM partner_contact_accounts
                    WHERE account_id = ?
                )
          )
    """, (partner_contact_id, account_id, account_id)).fetchone()
    return bool(match)


def outreach_recipient_matches_account(connection, account_id, contact_id, partner_contact_id):
    return (
        contact_matches_account(connection, account_id, contact_id)
        and partner_contact_matches_account(connection, account_id, partner_contact_id)
    )


def outreach_recipients_match_account(connection, account_id, recipients):
    return all(
        outreach_recipient_matches_account(connection, account_id, contact_id, partner_contact_id)
        for contact_id, partner_contact_id in recipients
    )


def save_outreach_recipients(connection, outreach_id, recipients):
    connection.execute("DELETE FROM outreach_recipients WHERE outreach_id = ?", (outreach_id,))
    for index, (contact_id, partner_contact_id) in enumerate(recipients, start=1):
        connection.execute(
            """
            INSERT INTO outreach_recipients (outreach_id, contact_id, partner_contact_id, sort_order)
            VALUES (?, ?, ?, ?)
            """,
            (outreach_id, contact_id, partner_contact_id, index),
        )


def selected_outreach_contact_values(connection, outreach_item):
    rows = connection.execute(
        """
        SELECT contact_id, partner_contact_id
        FROM outreach_recipients
        WHERE outreach_id = ?
        ORDER BY sort_order, id
        """,
        (outreach_item["id"],),
    ).fetchall()
    values = []
    for row in rows:
        if row["partner_contact_id"]:
            values.append(f"partner_contact:{row['partner_contact_id']}")
        elif row["contact_id"]:
            values.append(str(row["contact_id"]))
    if not values:
        if outreach_item["partner_contact_id"]:
            values.append(f"partner_contact:{outreach_item['partner_contact_id']}")
        elif outreach_item["contact_id"]:
            values.append(str(outreach_item["contact_id"]))
    return values


def partner_contacts_for_outreach(connection, account_id=None):
    query = """
        SELECT
            partner_contacts.*,
            partners.partner_name,
            partners.partner_type,
            accounts.account_name
        FROM partner_contacts
        LEFT JOIN partners ON partners.id = partner_contacts.partner_id
        LEFT JOIN accounts ON accounts.id = partner_contacts.account_id
        WHERE (
            partner_contacts.account_id IS NOT NULL
            OR EXISTS (
                SELECT 1
                FROM partner_contact_accounts
                WHERE partner_contact_accounts.partner_contact_id = partner_contacts.id
            )
        )
    """
    params = []
    if account_id:
        query += """
            AND (
                partner_contacts.account_id = ?
                OR EXISTS (
                    SELECT 1
                    FROM partner_contact_accounts
                    WHERE partner_contact_accounts.partner_contact_id = partner_contacts.id
                      AND partner_contact_accounts.account_id = ?
                )
            )
        """
        params.extend([account_id, account_id])
    query += " ORDER BY accounts.account_name, partners.partner_name, partner_contacts.name"
    return connection.execute(query, params).fetchall()


def create_partner_next_action_outreach(connection, account_id, partner_name, contact_name, next_action, assigned_to=""):
    account_id = account_id or None
    next_action = (next_action or "").strip()
    if not account_id or not next_action:
        return None
    subject_parts = ["Partner follow-up"]
    if partner_name:
        subject_parts.append(str(partner_name))
    if contact_name:
        subject_parts.append(str(contact_name))
    cursor = connection.execute("""
        INSERT INTO outreach (
            account_id,
            activity_type,
            subject,
            notes,
            outcome,
            next_action_date,
            task_status,
            assigned_to
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        account_id,
        "Partner Touchpoint",
        " - ".join(subject_parts),
        f"Created from partner next action: {next_action}",
        "Follow-up Required",
        datetime.now().date().isoformat(),
        "Not Started",
        assigned_to or ""
    ))
    return cursor.lastrowid


def account_sales_play_options(connection, account_id=None):
    rows = []
    if account_id:
        rows = connection.execute("""
            SELECT DISTINCT sales_play
            FROM outreach
            WHERE account_id = ?
              AND sales_play IS NOT NULL
              AND sales_play != ''
            UNION
            SELECT DISTINCT sales_play
            FROM accounts
            WHERE id = ?
              AND sales_play IS NOT NULL
              AND sales_play != ''
            ORDER BY sales_play
        """, (account_id, account_id)).fetchall()
    else:
        rows = connection.execute("""
            SELECT DISTINCT accounts.id AS account_id, outreach.sales_play
            FROM outreach
            JOIN accounts ON accounts.id = outreach.account_id
            WHERE outreach.sales_play IS NOT NULL
              AND outreach.sales_play != ''
            UNION
            SELECT id AS account_id, sales_play
            FROM accounts
            WHERE sales_play IS NOT NULL
              AND sales_play != ''
            ORDER BY sales_play
        """).fetchall()
    return [dict(row) for row in rows if row["sales_play"]]


def normalise_selected_account_ids(values):
    account_ids = []
    seen = set()
    for value in values or []:
        value = str(value or "").strip()
        if not value.isdigit() or value in seen:
            continue
        seen.add(value)
        account_ids.append(value)
    return account_ids


def save_partner_contact_accounts(connection, partner_id, contact_id, account_ids, relationship_status=""):
    account_ids = normalise_selected_account_ids(account_ids)
    connection.execute(
        "DELETE FROM partner_contact_accounts WHERE partner_contact_id = ?",
        (contact_id,),
    )
    for account_id in account_ids:
        connection.execute("""
            INSERT OR IGNORE INTO partner_contact_accounts (
                partner_contact_id,
                partner_id,
                account_id,
                relationship_status
            )
            VALUES (?, ?, ?, ?)
        """, (contact_id, partner_id, account_id, relationship_status))
    primary_account_id = account_ids[0] if account_ids else None
    connection.execute("""
        UPDATE partner_contacts
        SET account_id = ?,
            relationship_status = ?,
            last_updated = CURRENT_TIMESTAMP
        WHERE id = ?
          AND partner_id = ?
    """, (primary_account_id, relationship_status, contact_id, partner_id))
    return account_ids


def account_partner_activity_options(connection):
    return connection.execute("""
        SELECT
            partner_contact_accounts.account_id,
            partners.id AS partner_id,
            partners.partner_name,
            partners.partner_type
        FROM partner_contact_accounts
        JOIN partners ON partners.id = partner_contact_accounts.partner_id
        WHERE partner_contact_accounts.account_id IS NOT NULL
          AND partners.partner_name IS NOT NULL
          AND partners.partner_name != ''
        GROUP BY partner_contact_accounts.account_id, partners.id, partners.partner_name, partners.partner_type
        ORDER BY partners.partner_name
    """).fetchall()


def activity_update_required_message():
    return "Activity Update must be at least 5 characters before a task can be completed, closed or cancelled."


def fy_quarter_required_message():
    return "FY and Quarter are required before this record can be saved."


def fy_quarter_are_valid(fy, quarter):
    return bool((fy or "").strip() and (quarter or "").strip())


def pg_dashboard_context(connection):
    accounts = connection.execute("""
        SELECT *
        FROM accounts
        ORDER BY
            CASE WHEN pg_bible_order IS NULL THEN 1 ELSE 0 END,
            pg_bible_order,
            account_name
    """).fetchall()
    current_pipeline = money_value(dashboard_setting(connection, "current_pipeline", "0"))
    fy_pipeline_target = sum(money_value(account["pipeline_target"]) for account in accounts)
    pipeline_gap = fy_pipeline_target - current_pipeline

    pg_plan_rows = []
    pg_action_rows = []
    seven_days_ago = (datetime.now() - timedelta(days=7)).date().isoformat()
    today_key = datetime.now().date().isoformat()
    seven_days_forward = (datetime.now() + timedelta(days=7)).date().isoformat()
    stale_contact_cutoff = (datetime.now() - timedelta(days=30)).date()
    for account in accounts:
        account_id = account["id"]
        pg_target_number = account["pg_bible_order"] or ""
        contacts = connection.execute("""
            SELECT
                contacts.id,
                contacts.name,
                contacts.job_title,
                contacts.org_dept,
                accounts.account_name,
                accounts.business_unit
            FROM contacts
            LEFT JOIN accounts ON accounts.id = contacts.account_id
            WHERE contacts.account_id = ?
              AND COALESCE(status, 'Active') = 'Active'
            ORDER BY name
        """, (account_id,)).fetchall()
        outreach_sales_play_rows = connection.execute("""
            SELECT DISTINCT sales_play
            FROM outreach
            WHERE account_id = ?
              AND sales_play IS NOT NULL
              AND sales_play != ''
            ORDER BY sales_play
        """, (account_id,)).fetchall()
        outreach_sales_plays = [
            row["sales_play"]
            for row in outreach_sales_play_rows
            if row["sales_play"]
        ]
        pg_sales_play = "; ".join(outreach_sales_plays) or account["sales_play"] or ""
        legacy_action_update = connection.execute("""
            SELECT *
            FROM pg_action_updates
            WHERE account_id = ?
        """, (account_id,)).fetchone()
        contact_rag_payloads = {
            contact["id"]: contact_pg_progress_rag(connection, account_id, contact["id"], legacy_action_update)
            for contact in contacts
        }
        rag = aggregate_pg_progress_rag(payload["rag"] for payload in contact_rag_payloads.values())
        pg_plan_rows.append({
            "account_id": account_id,
            "target_number": pg_target_number,
            "colour_index": nbm_colour_index(pg_target_number),
            "rag_status": rag["status"],
            "rag_label": rag["label"],
            "rag_reason": rag["reason"],
            "sales_play": pg_sales_play,
            "account_name": account["account_name"],
            "business_org": account["business_unit"] or "",
            "estimated_value": money_value(account["pipeline_target"]),
        })

        for contact in contacts:
            contact_id = contact["id"]
            if not contact_has_recent_or_open_activity(connection, contact_id, stale_contact_cutoff):
                continue
            scheduled_action_rows = connection.execute("""
                SELECT subject, activity_type, next_action_date, next_action_time
                FROM outreach
                WHERE account_id = ?
                  AND (
                        contact_id = ?
                     OR id IN (
                            SELECT outreach_id
                            FROM outreach_recipients
                            WHERE contact_id = ?
                        )
                  )
                  AND next_action_date IS NOT NULL
                  AND next_action_date != ''
                  AND next_action_date <= ?
                  AND COALESCE(task_status, '') NOT IN ('Closed', 'Completed', 'Cancelled')
                ORDER BY next_action_date ASC, next_action_time ASC, id DESC
            """, (account_id, contact_id, contact_id, seven_days_forward)).fetchall()
            recent_activity_rows = connection.execute("""
                SELECT activity_date, activity_type, subject, next_action, last_updated
                FROM outreach
                WHERE account_id = ?
                  AND (
                        contact_id = ?
                     OR id IN (
                            SELECT outreach_id
                            FROM outreach_recipients
                            WHERE contact_id = ?
                        )
                  )
                  AND last_updated >= ?
                  AND next_action IS NOT NULL
                  AND next_action != ''
                  AND COALESCE(task_status, '') IN ('Closed', 'Completed', 'Cancelled')
                ORDER BY last_updated DESC, id DESC
            """, (account_id, contact_id, contact_id, seven_days_ago)).fetchall()
            contact_rag_payload = contact_rag_payloads.get(contact_id) or contact_pg_progress_rag(connection, account_id, contact_id, legacy_action_update)
            action_update = contact_rag_payload["action_update"]
            contact_completed_discovery = contact_rag_payload["completed_discovery"]
            contact_nbm_completed = contact_rag_payload["nbm_completed"]
            contact_rag = contact_rag_payload["rag"]

            next_7_days_actions = []
            for action_row in scheduled_action_rows:
                subject = action_row["subject"] or "Scheduled action"
                due_parts = [action_row["next_action_date"] or "", action_row["next_action_time"] or ""]
                next_7_days_actions.append({
                    "subject": subject,
                    "activity_type": action_row["activity_type"] or "",
                    "due": " ".join(part for part in due_parts if part),
                })
            last_7_days_activity_entries = []
            for row in recent_activity_rows:
                submitted_date = str(row["last_updated"] or row["activity_date"] or "No date")[:10]
                last_7_days_activity_entries.append({
                    "date": submitted_date,
                    "activity": row["activity_type"] or row["subject"] or "Activity",
                    "activity_update": row["next_action"],
                })

            pg_action_rows.append({
                "is_partner_row": False,
                "account_id": account_id,
                "contact_id": contact_id,
                "target_number": pg_target_number,
                "colour_index": nbm_colour_index(pg_target_number),
                "rag_status": contact_rag["status"],
                "rag_label": contact_rag["label"],
                "rag_reason": contact_rag["reason"],
                "account_name": account["account_name"],
                "sales_play": pg_sales_play or "No sales play entered",
                "targeted_discovery": contact["name"] or "No contact name",
                "contact_job_title": contact["job_title"] or "",
                "company_name": contact["account_name"] or account["account_name"],
                "business_org": contact["business_unit"] or "",
                "department": contact["org_dept"] or "",
                "completed_discovery_meeting": contact_completed_discovery,
                "exec_first": action_update["exec_first"] if action_update and "exec_first" in action_update.keys() else "",
                "nbm_completed": contact_nbm_completed,
                "last_7_days_activity_entries": last_7_days_activity_entries,
                "next_7_days_actions": next_7_days_actions or [{"subject": "No next action set", "activity_type": "", "due": ""}],
            })

        partner_activity_rows = connection.execute("""
            SELECT
                outreach.activity_date,
                outreach.activity_type,
                outreach.next_action,
                outreach.subject,
                outreach.last_updated,
                outreach.next_action_date,
                outreach.next_action_time,
                outreach.task_status,
                partners.partner_name,
                partner_contacts.name AS partner_contact_name,
                partner_contacts.job_title AS partner_contact_job_title,
                partner_contacts.notes AS partner_notes,
                partner_contacts.last_updated AS partner_last_updated
            FROM partner_contact_accounts
            JOIN partner_contacts ON partner_contacts.id = partner_contact_accounts.partner_contact_id
            LEFT JOIN partners ON partners.id = partner_contacts.partner_id
            LEFT JOIN outreach
              ON outreach.account_id = partner_contact_accounts.account_id
             AND (
                    outreach.activity_type = ('Partner: ' || partners.partner_name)
                 OR outreach.partner_contact_id = partner_contacts.id
             )
            WHERE partner_contact_accounts.account_id = ?
            ORDER BY partners.partner_name, partner_contacts.name, outreach.last_updated DESC
        """, (account_id,)).fetchall()
        partner_activity_entries = []
        partner_scheduled_actions = []
        seen_partner_entries = set()
        partner_group_names = []
        partner_contact_names = []
        for row in partner_activity_rows:
            partner_name = row["partner_name"] or "Partner"
            partner_contact_name = row["partner_contact_name"] or "Partner contact"
            if partner_name not in partner_group_names:
                partner_group_names.append(partner_name)
            contact_label = partner_contact_name
            if row["partner_contact_job_title"]:
                contact_label = f"{contact_label} - {row['partner_contact_job_title']}"
            if contact_label not in partner_contact_names:
                partner_contact_names.append(contact_label)
            if row["next_action"] and row["last_updated"] and str(row["last_updated"])[:10] >= seven_days_ago and is_closed_task_status(row["task_status"]):
                key = ("outreach", row["last_updated"], row["next_action"])
                if key not in seen_partner_entries:
                    seen_partner_entries.add(key)
                    partner_activity_entries.append({
                        "date": str(row["last_updated"])[:10],
                        "activity": row["activity_type"] or f"Partner activity - {partner_name}",
                        "activity_update": f"{partner_name}: {row['next_action']}",
                    })
            if row["partner_notes"] and row["partner_last_updated"] and str(row["partner_last_updated"])[:10] >= seven_days_ago:
                key = ("partner_contact", row["partner_last_updated"], row["partner_notes"])
                if key not in seen_partner_entries:
                    seen_partner_entries.add(key)
                    partner_activity_entries.append({
                        "date": str(row["partner_last_updated"])[:10],
                        "activity": f"Partner activity - {partner_name}",
                        "activity_update": f"{partner_contact_name}: {row['partner_notes']}",
                    })
            if row["next_action_date"] and row["next_action_date"] <= seven_days_forward and not is_closed_task_status(row["task_status"]):
                key = ("scheduled", row["next_action_date"], row["next_action_time"], row["subject"])
                if key not in seen_partner_entries:
                    seen_partner_entries.add(key)
                    due_parts = [row["next_action_date"] or "", row["next_action_time"] or ""]
                    partner_scheduled_actions.append({
                        "subject": row["subject"] or f"Partner activity - {partner_name}",
                        "activity_type": row["activity_type"] or "Partner Touchpoint",
                        "due": " ".join(part for part in due_parts if part),
                    })
        if partner_activity_entries or partner_scheduled_actions:
            partner_group_label = "Partner Account: " + compact_join(partner_group_names, 3) if partner_group_names else "Partner activity"
            pg_action_rows.append({
                "is_partner_row": True,
                "account_id": account_id,
                "contact_id": f"partner_{account_id}",
                "target_number": pg_target_number,
                "colour_index": nbm_colour_index(pg_target_number),
                "rag_status": rag["status"],
                "rag_label": rag["label"],
                "rag_reason": rag["reason"],
                "account_name": account["account_name"],
                "sales_play": pg_sales_play or "No sales play entered",
                "targeted_discovery": compact_join(partner_contact_names, 3) if partner_contact_names else "Partner activity",
                "contact_job_title": "",
                "company_name": account["account_name"],
                "business_org": partner_group_label,
                "department": "",
                "completed_discovery_meeting": "N/A",
                "exec_first": "N/A",
                "nbm_completed": "N/A",
                "last_7_days_activity_entries": partner_activity_entries,
                "next_7_days_actions": partner_scheduled_actions,
            })

    return {
        "fy_pipeline_target": fy_pipeline_target,
        "current_pipeline": current_pipeline,
        "pipeline_gap": pipeline_gap,
        "pg_plan_rows": pg_plan_rows,
        "pg_action_rows": pg_action_rows,
    }


@app.route("/dashboard-new")
def dashboard_new():
    return redirect(url_for("pg_progress"))


@app.route("/pg-progress", methods=("GET", "POST"))
def pg_progress():
    connection = get_db_connection()
    if request.method == "POST":
        save_dashboard_setting(connection, "current_pipeline", request.form.get("current_pipeline", "0"))
        for contact_id in request.form.getlist("pg_action_contact_id"):
            if not str(contact_id).isdigit():
                continue
            account_id = request.form.get(f"pg_action_account_id_{contact_id}", "")
            completed = request.form.get(f"completed_discovery_contact_{contact_id}", "")
            exec_first = request.form.get(f"exec_first_contact_{contact_id}", "")
            nbm_completed = request.form.get(f"nbm_completed_contact_{contact_id}", "")
            next_action = request.form.get(f"next_action_contact_{contact_id}", "")
            existing = connection.execute(
                "SELECT id FROM pg_action_contact_updates WHERE contact_id = ?",
                (contact_id,),
            ).fetchone()
            if existing:
                connection.execute("""
                    UPDATE pg_action_contact_updates
                    SET completed_discovery_meeting = ?,
                        exec_first = ?,
                        nbm_completed = ?,
                        next_action_override = ?,
                        last_updated = CURRENT_TIMESTAMP
                    WHERE contact_id = ?
                """, (completed, exec_first, nbm_completed, next_action, contact_id))
            else:
                connection.execute("""
                    INSERT INTO pg_action_contact_updates (
                        account_id,
                        contact_id,
                        completed_discovery_meeting,
                        exec_first,
                        nbm_completed,
                        next_action_override
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (account_id, contact_id, completed, exec_first, nbm_completed, next_action))
        audit_entry(
            connection,
            "dashboard_new",
            None,
            "update",
            "pg_goals",
            "PG Goals dashboard",
            "",
            "PG Progress saved"
        )
        connection.commit()
        connection.close()
        return redirect(url_for("pg_progress", message="PG Progress saved."))

    context = pg_dashboard_context(connection)
    connection.close()
    return render_template(
        "dashboard_new.html",
        message=request.args.get("message", ""),
        **context,
    )


@app.route("/accounts")
def accounts():
    user = current_user()
    connection = get_db_connection()
    now = current_app_datetime()

    account_rows = connection.execute(f"""
        SELECT 
            accounts.*,

            (
                SELECT COUNT(*)
                FROM contacts
                WHERE contacts.account_id = accounts.id
            ) AS contact_count,

            (
                SELECT COUNT(*)
                FROM outreach
                WHERE outreach.account_id = accounts.id
            ) AS outreach_count,

            (
                SELECT COUNT(*)
                FROM outreach
                WHERE outreach.account_id = accounts.id
                  AND (
                        outreach.outcome IN ('Discovery Booked', 'NBM Booked', 'Exec Meeting Booked', 'Meeting Booked')
                     OR outreach.activity_type = 'Meeting'
                  )
            ) AS meeting_count,

            (
                SELECT COUNT(*)
                FROM outreach
                WHERE outreach.account_id = accounts.id
                  AND {overdue_task_sql("outreach")}
            ) AS overdue_followups,

            (
                SELECT MAX(outreach.activity_date)
                FROM outreach
                WHERE outreach.account_id = accounts.id
            ) AS latest_outreach_date

        FROM accounts
        ORDER BY accounts.account_name
    """, overdue_task_params(now)).fetchall()

    accounts = []

    for row in account_rows:
        account = dict(row)

        health = calculate_account_health(
            contact_count=account["contact_count"] or 0,
            outreach_count=account["outreach_count"] or 0,
            meeting_count=account["meeting_count"] or 0,
            overdue_followups=account["overdue_followups"] or 0,
            latest_outreach_date=account["latest_outreach_date"]
        )

        account["health_label"] = health["label"]
        account["health_colour"] = health["colour"]
        account["health_reason"] = health["reason"]

        accounts.append(account)

    accounts.sort(
        key=lambda account: (
            int(account["account_tier"] or 999),
            int(account["pg_bible_order"] or 9999),
            account["account_name"].lower()
        )
    )

    shareable_accounts = [
        account for account in accounts
        if current_user_owns_account(account)
    ]
    account_shares = connection.execute("""
        SELECT
            account_shared_users.*,
            accounts.account_name,
            accounts.owner_user_id,
            accounts.owner_name
        FROM account_shared_users
        JOIN accounts ON accounts.id = account_shared_users.account_id
        WHERE accounts.owner_user_id IS NULL
           OR accounts.owner_user_id = ?
        ORDER BY accounts.account_name, account_shared_users.full_name
    """, (user["id"] if user else None,)).fetchall()

    connection.close()

    return render_template(
        "accounts.html",
        accounts=accounts,
        shareable_accounts=shareable_accounts,
        account_shares=account_shares,
        assignable_users=list_assignable_users(),
        message=request.args.get("message", ""),
        error=request.args.get("error", ""),
    )


@app.route("/partners")
def partners():
    connection = get_db_connection()

    partner_rows = connection.execute("""
        SELECT
            partners.*,
            (
                SELECT COUNT(*)
                FROM account_partners
                WHERE account_partners.partner_id = partners.id
            ) AS account_count,
            (
                SELECT COUNT(*)
                FROM partner_contacts
                WHERE partner_contacts.partner_id = partners.id
            ) AS contact_count
        FROM partners
        ORDER BY partners.partner_name
    """).fetchall()
    partners_with_permissions = []
    for row in partner_rows:
        partner = dict(row)
        partner["can_delete"] = current_user_can_delete_partner(row)
        partners_with_permissions.append(partner)

    connection.close()

    return render_template("partners.html", partners=partners_with_permissions)


@app.route("/partners/add", methods=("POST",))
def add_partner():
    connection = get_db_connection()
    partner_name = request.form.get("partner_name", "").strip()
    website = normalise_partner_website(request.form.get("website"))
    actor = audit_actor()

    if partner_name and website is not None:
        existing_partner = connection.execute("""
            SELECT id
            FROM partners
            WHERE LOWER(partner_name) = LOWER(?)
        """, (partner_name,)).fetchone()

        if existing_partner:
            partner_id = existing_partner["id"]
        else:
            cursor = connection.execute("""
                INSERT INTO partners (
                    partner_name,
                    partner_type,
                    website,
                    country,
                    city,
                    partner_manager,
                    bmc_partner_manager,
                    relationship_owner,
                    submitted_by_user_id,
                    submitted_by_email,
                    submitted_by_name,
                    notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                partner_name,
                request.form.get("partner_type"),
                website,
                request.form.get("country"),
                request.form.get("city"),
                request.form.get("partner_manager"),
                request.form.get("bmc_partner_manager"),
                request.form.get("bmc_partner_manager"),
                actor["id"],
                actor["email"],
                actor["name"],
                request.form.get("notes")
            ))
            partner_id = cursor.lastrowid
            audit_record_create(connection, "partner", partner_id, {
                "partner_name": partner_name,
                "partner_type": request.form.get("partner_type"),
                "website": website,
                "partner_manager": request.form.get("partner_manager"),
                "bmc_partner_manager": request.form.get("bmc_partner_manager"),
                "city": request.form.get("city"),
                "country": request.form.get("country"),
                "notes": request.form.get("notes"),
            }, {
                "partner_name": "Partner account name",
                "partner_type": "Partner type",
                "website": "Account website",
                "partner_manager": "Partner account manager",
                "bmc_partner_manager": "BMC partner manager",
                "city": "City",
                "country": "Country",
                "notes": "Notes",
            })
            connection.commit()

        connection.close()
        return redirect(url_for("view_partner", partner_id=partner_id))

    connection.close()
    return redirect(url_for("partners"))


@app.route("/partners/<int:partner_id>")
def view_partner(partner_id):
    connection = get_db_connection()

    partner = connection.execute("""
        SELECT *
        FROM partners
        WHERE id = ?
    """, (partner_id,)).fetchone()

    if partner is None:
        connection.close()
        return redirect(url_for("partners"))

    partner_accounts = connection.execute("""
        SELECT
            partner_contact_accounts.account_id,
            partner_contact_accounts.relationship_status AS involvement_status,
            partner_contacts.name AS partner_contact_name,
            partner_contacts.job_title AS partner_contact_job_title,
            partner_contacts.relationship_owner,
            partner_contacts.notes,
            accounts.account_name,
            accounts.industry,
            accounts.country,
            accounts.city
        FROM partner_contact_accounts
        JOIN partner_contacts ON partner_contacts.id = partner_contact_accounts.partner_contact_id
        LEFT JOIN accounts ON partner_contact_accounts.account_id = accounts.id
        WHERE partner_contact_accounts.partner_id = ?
        ORDER BY accounts.account_name, partner_contacts.name
    """, (partner_id,)).fetchall()

    partner_contact_rows = connection.execute("""
        SELECT
            partner_contacts.*,
            accounts.account_name
        FROM partner_contacts
        LEFT JOIN accounts ON partner_contacts.account_id = accounts.id
        WHERE partner_contacts.partner_id = ?
        ORDER BY accounts.account_name, partner_contacts.name
    """, (partner_id,)).fetchall()
    supported_account_rows = connection.execute("""
        SELECT
            partner_contact_accounts.partner_contact_id,
            partner_contact_accounts.account_id,
            accounts.account_name
        FROM partner_contact_accounts
        LEFT JOIN accounts ON accounts.id = partner_contact_accounts.account_id
        WHERE partner_contact_accounts.partner_id = ?
        ORDER BY accounts.account_name
    """, (partner_id,)).fetchall()
    supported_by_contact = {}
    for row in supported_account_rows:
        payload = supported_by_contact.setdefault(row["partner_contact_id"], {"ids": [], "names": []})
        payload["ids"].append(str(row["account_id"]))
        if row["account_name"]:
            payload["names"].append(row["account_name"])
    partner_contacts = []
    for row in partner_contact_rows:
        contact = dict(row)
        supported = supported_by_contact.get(row["id"], {"ids": [], "names": []})
        contact["supported_account_ids"] = supported["ids"] or ([str(row["account_id"])] if row["account_id"] else [])
        contact["supported_account_names"] = supported["names"] or ([row["account_name"]] if row["account_name"] else [])
        partner_contacts.append(contact)

    partner_contact_count = connection.execute("""
        SELECT COUNT(*)
        FROM partner_contacts
        WHERE partner_id = ?
    """, (partner_id,)).fetchone()[0]

    partner_account_count = connection.execute("""
        SELECT COUNT(DISTINCT account_id)
        FROM partner_contact_accounts
        WHERE partner_id = ?
    """, (partner_id,)).fetchone()[0]

    accounts = connection.execute("""
        SELECT *
        FROM accounts
        ORDER BY
            CASE WHEN pg_bible_order IS NULL THEN 1 ELSE 0 END,
            pg_bible_order,
            account_name
    """).fetchall()

    connection.close()

    return render_template(
        "view_partner.html",
        partner=partner,
        partner_accounts=partner_accounts,
        partner_account_count=partner_account_count,
        partner_contacts=partner_contacts,
        partner_contact_count=partner_contact_count,
        accounts=accounts
    )


@app.route("/partners/<int:partner_id>/edit", methods=("POST",))
def edit_partner(partner_id):
    connection = get_db_connection()
    partner_name = request.form.get("partner_name", "").strip()
    website = normalise_partner_website(request.form.get("website"))
    existing_partner = connection.execute("SELECT * FROM partners WHERE id = ?", (partner_id,)).fetchone()

    if existing_partner and partner_name and website is not None:
        new_values = {
            "partner_name": partner_name,
            "partner_type": request.form.get("partner_type"),
            "website": website,
            "country": request.form.get("country"),
            "city": request.form.get("city"),
            "partner_manager": request.form.get("partner_manager"),
            "bmc_partner_manager": request.form.get("bmc_partner_manager"),
            "relationship_owner": request.form.get("bmc_partner_manager"),
            "notes": request.form.get("notes"),
        }
        labels = {
            "partner_name": "Partner account name",
            "partner_type": "Partner type",
            "website": "Account website",
            "country": "Country",
            "city": "City",
            "partner_manager": "Partner account manager",
            "bmc_partner_manager": "BMC partner manager",
            "relationship_owner": "Relationship owner",
            "notes": "Notes",
        }
        connection.execute("""
            UPDATE partners
            SET partner_name = ?,
                partner_type = ?,
                website = ?,
                country = ?,
                city = ?,
                partner_manager = ?,
                bmc_partner_manager = ?,
                relationship_owner = ?,
                notes = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            new_values["partner_name"],
            new_values["partner_type"],
            new_values["website"],
            new_values["country"],
            new_values["city"],
            new_values["partner_manager"],
            new_values["bmc_partner_manager"],
            new_values["relationship_owner"],
            new_values["notes"],
            partner_id
        ))
        audit_record_update(connection, "partner", partner_id, existing_partner, new_values, labels)

        connection.execute("""
            UPDATE account_partners
            SET partner_name = ?
            WHERE partner_id = ?
        """, (partner_name, partner_id))

        connection.commit()

    connection.close()
    return redirect(url_for("view_partner", partner_id=partner_id))


@app.route("/partners/<int:partner_id>/contacts/add", methods=("POST",))
def add_partner_contact(partner_id):
    connection = get_db_connection()
    contact_name = request.form.get("name", "").strip()

    if contact_name:
        account_ids = normalise_selected_account_ids(request.form.getlist("account_ids") or request.form.getlist("account_id"))
        cursor = connection.execute("""
            INSERT INTO partner_contacts (
                partner_id,
                name,
                job_title,
                partner_contact_role,
                coverage_area,
                account_id,
                relationship_owner,
                email,
                phone,
                location,
                linkedin,
                relationship_status,
                next_action,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            partner_id,
            contact_name,
            request.form.get("job_title"),
            request.form.get("partner_contact_role"),
            request.form.get("coverage_area"),
            account_ids[0] if account_ids else None,
            request.form.get("relationship_owner"),
            request.form.get("email"),
            request.form.get("phone"),
            request.form.get("location"),
            request.form.get("linkedin"),
            request.form.get("relationship_status"),
            request.form.get("next_action"),
            request.form.get("notes")
        ))
        contact_id = cursor.lastrowid
        save_partner_contact_accounts(
            connection,
            partner_id,
            contact_id,
            account_ids,
            request.form.get("relationship_status"),
        )
        partner_row = connection.execute("SELECT partner_name FROM partners WHERE id = ?", (partner_id,)).fetchone()
        audit_record_create(connection, "partner_contact", contact_id, {
            "partner_id": partner_id,
            "name": contact_name,
            "job_title": request.form.get("job_title"),
            "partner_contact_role": request.form.get("partner_contact_role"),
            "coverage_area": request.form.get("coverage_area"),
            "account_ids": ", ".join(account_ids),
            "relationship_owner": request.form.get("relationship_owner"),
            "email": request.form.get("email"),
            "relationship_status": request.form.get("relationship_status"),
            "next_action": "",
        })
        connection.commit()

    connection.close()
    return redirect(url_for("view_partner", partner_id=partner_id))


@app.route("/partners/<int:partner_id>/contacts/<int:contact_id>/delete", methods=("POST",))
def delete_partner_contact(partner_id, contact_id):
    connection = get_db_connection()
    contact = connection.execute("""
        SELECT name
        FROM partner_contacts
        WHERE id = ?
          AND partner_id = ?
    """, (contact_id, partner_id)).fetchone()
    if contact:
        audit_record_delete(connection, "partner_contact", contact_id, contact["name"])
    connection.execute("DELETE FROM outreach_recipients WHERE partner_contact_id = ?", (contact_id,))
    connection.execute("DELETE FROM partner_contact_accounts WHERE partner_contact_id = ?", (contact_id,))
    connection.execute("""
        DELETE FROM partner_contacts
        WHERE id = ?
          AND partner_id = ?
    """, (contact_id, partner_id))
    connection.commit()
    connection.close()

    return redirect(url_for("view_partner", partner_id=partner_id))


@app.route("/partners/<int:partner_id>/contacts/<int:contact_id>/edit", methods=("POST",))
def edit_partner_contact(partner_id, contact_id):
    connection = get_db_connection()
    existing = connection.execute("""
        SELECT *
        FROM partner_contacts
        WHERE id = ?
          AND partner_id = ?
    """, (contact_id, partner_id)).fetchone()
    partner = connection.execute("SELECT partner_name FROM partners WHERE id = ?", (partner_id,)).fetchone()

    if existing:
        account_ids = normalise_selected_account_ids(request.form.getlist("account_ids") or request.form.getlist("account_id"))
        new_values = {
            "name": request.form.get("name"),
            "job_title": request.form.get("job_title"),
            "coverage_area": request.form.get("coverage_area"),
            "account_id": account_ids[0] if account_ids else None,
            "relationship_owner": request.form.get("relationship_owner"),
            "email": request.form.get("email"),
            "phone": combined_contact_phone(request.form.get("office_phone"), request.form.get("mobile_phone"), request.form.get("phone")),
            "office_phone": request.form.get("office_phone"),
            "mobile_phone": request.form.get("mobile_phone"),
            "location": request.form.get("location"),
            "linkedin": request.form.get("linkedin"),
            "relationship_status": request.form.get("relationship_status"),
            "next_action": "",
            "notes": request.form.get("notes"),
        }
        labels = {
            "name": "Name",
            "job_title": "Job title",
            "coverage_area": "Coverage / influence area",
            "account_id": "Responsible account",
            "relationship_owner": "Relationship owner",
            "email": "Email",
            "phone": "Phone",
            "office_phone": "Office phone",
            "mobile_phone": "Mobile phone",
            "location": "Location",
            "linkedin": "LinkedIn",
            "relationship_status": "Partner engagement",
            "next_action": "Next partner action",
            "notes": "Notes",
        }
        connection.execute("""
            UPDATE partner_contacts
            SET name = ?,
                job_title = ?,
                partner_contact_role = '',
                coverage_area = ?,
                account_id = ?,
                relationship_owner = ?,
                email = ?,
                phone = ?,
                office_phone = ?,
                mobile_phone = ?,
                location = ?,
                linkedin = ?,
                relationship_status = ?,
                next_action = ?,
                notes = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE id = ?
              AND partner_id = ?
        """, (
            new_values["name"],
            new_values["job_title"],
            new_values["coverage_area"],
            new_values["account_id"],
            new_values["relationship_owner"],
            new_values["email"],
            new_values["phone"],
            new_values["office_phone"],
            new_values["mobile_phone"],
            new_values["location"],
            new_values["linkedin"],
            new_values["relationship_status"],
            new_values["next_action"],
            new_values["notes"],
            contact_id,
            partner_id,
        ))
        save_partner_contact_accounts(
            connection,
            partner_id,
            contact_id,
            account_ids,
            new_values["relationship_status"],
        )
        audit_record_update(connection, "partner_contact", contact_id, existing, new_values, labels)
        connection.commit()

    connection.close()
    return redirect(url_for("view_partner", partner_id=partner_id))


@app.route("/partners/bulk-delete", methods=("POST",))
def bulk_delete_partners():
    partner_ids = selected_record_ids()
    if partner_ids:
        connection = get_db_connection()
        delete_partner_records(connection, partner_ids)
        connection.commit()
        connection.close()
    return redirect(url_for("partners"))


@app.route("/partners/<int:partner_id>/accounts/add", methods=("POST",))
def add_partner_account_relationship(partner_id):
    connection = get_db_connection()

    partner = connection.execute("""
        SELECT partner_name
        FROM partners
        WHERE id = ?
    """, (partner_id,)).fetchone()

    account_id = request.form.get("account_id")

    if partner and account_id:
        existing_relationship = connection.execute("""
            SELECT id
            FROM account_partners
            WHERE account_id = ?
              AND partner_id = ?
        """, (account_id, partner_id)).fetchone()

        if existing_relationship is None:
            cursor = connection.execute("""
                INSERT INTO account_partners (
                    account_id,
                    partner_id,
                    partner_name,
                    partner_role,
                    involvement_status,
                    relationship_owner,
                    next_action,
                    notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                account_id,
                partner_id,
                partner["partner_name"],
                "",
                request.form.get("involvement_status"),
                request.form.get("relationship_owner"),
                "",
                request.form.get("notes")
            ))
            account_partner_id = cursor.lastrowid
            audit_record_create(connection, "account_partner", account_partner_id, {
                "account_id": account_id,
                "partner_id": partner_id,
                "partner_name": partner["partner_name"],
                "partner_role": "",
                "involvement_status": request.form.get("involvement_status"),
                "relationship_owner": request.form.get("relationship_owner"),
                "next_action": "",
                "notes": request.form.get("notes"),
            })

            add_timeline_entry(
                connection,
                "account",
                account_id,
                "Partner Added",
                f"Partner involvement added: {partner['partner_name']}"
            )
            connection.commit()

    connection.close()
    return redirect(url_for("view_partner", partner_id=partner_id))


@app.route("/accounts/add", methods=("GET", "POST"))
def add_account():
    custom_fields = account_custom_field_payload(active_only=True)
    if request.method == "POST":
        connection = get_db_connection()
        customer_logo = save_account_logo(request.files.get("customer_logo"))
        selected_owner = assignable_user_by_id(request.form.get("owner_user_id"))
        owner = {
            "owner_user_id": selected_owner["id"],
            "owner_name": selected_owner["full_name"],
            "owner_email": selected_owner["email"],
        } if selected_owner else current_user_owner_payload()
        try:
            cursor = connection.execute("""
                INSERT INTO accounts
                (account_name, pg_bible_order, account_tier, industry, business_unit, country, city, website, customer_logo, pipeline_target, nbm_target, sales_play, owner_user_id, owner_name, owner_email, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                request.form.get("account_name"),
                request.form.get("pg_bible_order") or None,
                request.form.get("account_tier"),
                request.form.get("industry"),
                request.form.get("business_unit"),
                request.form.get("country"),
                request.form.get("city"),
                request.form.get("website"),
                customer_logo,
                request.form.get("pipeline_target") or None,
                request.form.get("nbm_target"),
                request.form.get("sales_play"),
                owner["owner_user_id"],
                owner["owner_name"],
                owner["owner_email"],
                request.form.get("notes")
            ))
            account_id = cursor.lastrowid
            audit_record_create(connection, "account", account_id, {
                "account_name": request.form.get("account_name"),
                "pg_bible_order": request.form.get("pg_bible_order") or None,
                "account_tier": request.form.get("account_tier"),
                "industry": request.form.get("industry"),
                "business_unit": request.form.get("business_unit"),
                "country": request.form.get("country"),
                "city": request.form.get("city"),
                "website": request.form.get("website"),
                "customer_logo": customer_logo,
                "pipeline_target": request.form.get("pipeline_target"),
                "nbm_target": request.form.get("nbm_target"),
                "sales_play": request.form.get("sales_play"),
                "owner_name": owner["owner_name"],
                "notes": request.form.get("notes"),
            })
            save_account_custom_values(connection, account_id, custom_fields, request.form)
            commit_with_retry(connection)
        except Exception:
            connection.rollback()
            traceback.print_exc()
            connection.close()
            return render_template(
                "add_account.html",
                custom_fields=custom_fields,
                assignable_users=list_assignable_users(),
                error="The account could not be saved. Check the required values and try again.",
                prefill=dict(request.form),
            ), 500
        connection.close()
        return redirect(url_for("accounts"))

    default_owner = current_user_owner_payload()
    return render_template(
        "add_account.html",
        custom_fields=custom_fields,
        assignable_users=list_assignable_users(),
        prefill={"owner_user_id": default_owner["owner_user_id"]},
        error="",
    )


@app.route("/accounts/<int:account_id>")
def view_account(account_id):
    connection = get_db_connection()
    now = current_app_datetime()

    account = connection.execute(
        "SELECT * FROM accounts WHERE id = ?",
        (account_id,)
    ).fetchone()
    if not account:
        connection.close()
        return redirect(url_for("accounts", message="Account could not be found in this workspace."))

    account_stats = connection.execute(f"""
        SELECT
            (
                SELECT COUNT(*)
                FROM contacts
                WHERE contacts.account_id = accounts.id
            ) AS contact_count,

            (
                SELECT COUNT(*)
                FROM outreach
                WHERE outreach.account_id = accounts.id
            ) AS outreach_count,

            (
                SELECT COUNT(*)
                FROM outreach
                WHERE outreach.account_id = accounts.id
                  AND (
                        outreach.outcome IN ('Discovery Booked', 'NBM Booked', 'Exec Meeting Booked', 'Meeting Booked')
                     OR outreach.activity_type = 'Meeting'
                  )
            ) AS meeting_count,

            (
                SELECT COUNT(*)
                FROM outreach
                WHERE outreach.account_id = accounts.id
                  AND {overdue_task_sql("outreach")}
            ) AS overdue_followups,

            (
                SELECT MAX(outreach.activity_date)
                FROM outreach
                WHERE outreach.account_id = accounts.id
            ) AS latest_outreach_date

        FROM accounts
        WHERE accounts.id = ?
    """, (*overdue_task_params(now), account_id)).fetchone()

    account_outreach = connection.execute("""
        SELECT outreach.*, contacts.name AS contact_name
        FROM outreach
        LEFT JOIN contacts ON outreach.contact_id = contacts.id
        WHERE outreach.account_id = ?
        ORDER BY outreach.activity_date DESC, outreach.activity_time DESC
    """, (account_id,)).fetchall()

    account_contacts = connection.execute("""
        SELECT *
        FROM contacts
        WHERE account_id = ?
        ORDER BY name
    """, (account_id,)).fetchall()

    owner = account_owner_payload(account)
    is_account_owner = current_user_owns_account(account)
    if is_account_owner:
        account_shares = connection.execute("""
            SELECT *
            FROM account_shared_users
            WHERE account_id = ?
            ORDER BY full_name, email
        """, (account_id,)).fetchall()
    else:
        account_shares = []

    account_partners = connection.execute("""
        SELECT
            account_partners.*,
            partners.partner_type,
            partners.website AS partner_website,
            (
                SELECT COUNT(*)
                FROM partner_contacts
                WHERE partner_contacts.partner_id = account_partners.partner_id
                  AND partner_contacts.account_id = account_partners.account_id
            ) AS partner_contact_count
        FROM account_partners
        LEFT JOIN partners ON account_partners.partner_id = partners.id
        WHERE account_partners.account_id = ?
        ORDER BY account_partners.partner_name
    """, (account_id,)).fetchall()

    partner_relationships = connection.execute("""
        SELECT
            accounts.account_name,
            partner_contacts.name AS partner_contact_name,
            partner_contacts.job_title,
            COALESCE(partner_contact_accounts.relationship_status, partner_contacts.relationship_status) AS relationship_status,
            partners.id AS partner_id,
            partners.partner_name
        FROM partner_contact_accounts
        JOIN partner_contacts ON partner_contacts.id = partner_contact_accounts.partner_contact_id
        LEFT JOIN partners ON partners.id = partner_contacts.partner_id
        LEFT JOIN accounts ON accounts.id = partner_contact_accounts.account_id
        WHERE partner_contact_accounts.account_id = ?
        ORDER BY partners.partner_name, partner_contacts.name
    """, (account_id,)).fetchall()

    partner_options = connection.execute("""
        SELECT *
        FROM partners
        ORDER BY partner_name
    """).fetchall()

    timeline_entries = connection.execute("""
        SELECT *
        FROM timeline_entries
        WHERE related_type = 'account'
          AND related_id = ?
        ORDER BY date_created DESC
    """, (account_id,)).fetchall()

    custom_fields = account_custom_field_payload(active_only=True)
    custom_values = load_account_custom_values(connection, account_id)

    connection.close()

    return render_template(
        "view_account.html",
        account=account,
        account_stats=account_stats,
        account_outreach=account_outreach,
        account_contacts=account_contacts,
        account_shares=account_shares,
        account_partners=account_partners,
        partner_relationships=partner_relationships,
        partner_options=partner_options,
        timeline_entries=timeline_entries,
        custom_fields=custom_fields,
        custom_values=custom_values,
        owner=owner,
        is_account_owner=is_account_owner
    )


@app.route("/accounts/<int:account_id>/partners/add", methods=("POST",))
def add_account_partner(account_id):
    connection = get_db_connection()
    partner_name = request.form.get("partner_name", "").strip()
    partners_to_add = []

    for selected_partner_id in request.form.getlist("partner_ids"):
        partner = connection.execute("""
            SELECT id, partner_name
            FROM partners
            WHERE id = ?
        """, (selected_partner_id,)).fetchone()
        if partner:
            partners_to_add.append((partner["id"], partner["partner_name"]))

    if partner_name:
        partners_to_add.append((get_or_create_partner(connection, partner_name), partner_name))

    seen_partner_ids = set()
    for partner_id, partner_name in partners_to_add:
        if partner_id in seen_partner_ids:
            continue
        seen_partner_ids.add(partner_id)
        existing = connection.execute("""
            SELECT id
            FROM account_partners
            WHERE account_id = ?
              AND partner_id = ?
        """, (account_id, partner_id)).fetchone()
        if existing:
            continue
        cursor = connection.execute("""
            INSERT INTO account_partners (
                account_id,
                partner_id,
                partner_name,
                partner_role,
                involvement_status,
                relationship_owner,
                next_action,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            account_id,
            partner_id,
            partner_name,
            "",
            request.form.get("involvement_status"),
            request.form.get("relationship_owner"),
            "",
            request.form.get("notes")
        ))
        account_partner_id = cursor.lastrowid
        audit_record_create(connection, "account_partner", account_partner_id, {
            "account_id": account_id,
            "partner_id": partner_id,
            "partner_name": partner_name,
            "partner_role": "",
            "involvement_status": request.form.get("involvement_status"),
            "relationship_owner": request.form.get("relationship_owner"),
            "next_action": "",
            "notes": request.form.get("notes"),
        })

        add_timeline_entry(
            connection,
            "account",
            account_id,
            "Partner Added",
            f"Partner involvement added: {partner_name}"
        )

        commit_with_retry(connection)

    connection.close()
    return redirect(url_for("view_account", account_id=account_id))


@app.route("/accounts/<int:account_id>/partners/<int:partner_id>/edit", methods=("POST",))
def edit_account_partner(account_id, partner_id):
    connection = get_db_connection()

    existing_partner = connection.execute("""
        SELECT *
        FROM account_partners
        WHERE id = ?
          AND account_id = ?
    """, (partner_id, account_id)).fetchone()

    if existing_partner:
        selected_partner_id = request.form.get("selected_partner_id")
        partner_name = request.form.get("partner_name", "").strip()

        if selected_partner_id:
            selected_partner = connection.execute("""
                SELECT partner_name
                FROM partners
                WHERE id = ?
            """, (selected_partner_id,)).fetchone()
            if selected_partner:
                partner_name = selected_partner["partner_name"]
            else:
                selected_partner_id = None

        if partner_name and not selected_partner_id:
            selected_partner_id = get_or_create_partner(connection, partner_name)

        new_values = {
            "partner_id": selected_partner_id,
            "partner_name": partner_name,
            "partner_role": "",
            "involvement_status": request.form.get("involvement_status"),
            "relationship_owner": request.form.get("relationship_owner"),
            "next_action": "",
            "notes": request.form.get("notes")
        }

        labels = {
            "partner_id": "Partner organisation",
            "partner_name": "Partner name",
            "partner_role": "Partner role",
            "involvement_status": "Partner engagement",
            "relationship_owner": "Relationship owner",
            "next_action": "Next action",
            "notes": "Notes"
        }

        changes = build_change_log(existing_partner, new_values, labels)

        if new_values["partner_name"]:
            connection.execute("""
                UPDATE account_partners
                SET partner_id = ?,
                    partner_name = ?,
                    partner_role = ?,
                    involvement_status = ?,
                    relationship_owner = ?,
                    next_action = ?,
                    notes = ?,
                    last_updated = CURRENT_TIMESTAMP
                WHERE id = ?
                  AND account_id = ?
            """, (
                new_values["partner_id"],
                new_values["partner_name"],
                new_values["partner_role"],
                new_values["involvement_status"],
                new_values["relationship_owner"],
                new_values["next_action"],
                new_values["notes"],
                partner_id,
                account_id
            ))

            if changes:
                audit_record_update(connection, "account_partner", partner_id, existing_partner, new_values, labels)
                add_timeline_entry(
                    connection,
                    "account",
                    account_id,
                    "Partner Updated",
                    "Partner updated: " + "; ".join(changes)
                )

            connection.commit()

    connection.close()
    return redirect(url_for("view_account", account_id=account_id))


@app.route("/accounts/<int:account_id>/partners/<int:partner_id>/delete", methods=("POST",))
def delete_account_partner(account_id, partner_id):
    connection = get_db_connection()

    partner = connection.execute("""
        SELECT partner_name
        FROM account_partners
        WHERE id = ?
          AND account_id = ?
    """, (partner_id, account_id)).fetchone()

    if partner:
        audit_record_delete(connection, "account_partner", partner_id, partner["partner_name"])
        connection.execute("""
            DELETE FROM account_partners
            WHERE id = ?
              AND account_id = ?
        """, (partner_id, account_id))

        add_timeline_entry(
            connection,
            "account",
            account_id,
            "Partner Deleted",
            f"Partner involvement deleted: {partner['partner_name']}"
        )

        connection.commit()

    connection.close()
    return redirect(url_for("view_account", account_id=account_id))


@app.route("/accounts/<int:account_id>/edit", methods=("GET", "POST"))
def edit_account(account_id):
    connection = get_db_connection()

    account = connection.execute(
        "SELECT * FROM accounts WHERE id = ?",
        (account_id,)
    ).fetchone()
    custom_fields = account_custom_field_payload(active_only=True)
    custom_values = load_account_custom_values(connection, account_id)

    if request.method == "POST":
        new_values = {
            "account_name": request.form.get("account_name"),
            "pg_bible_order": request.form.get("pg_bible_order") or None,
            "account_tier": request.form.get("account_tier"),
            "industry": request.form.get("industry"),
            "business_unit": request.form.get("business_unit"),
            "country": request.form.get("country"),
            "city": request.form.get("city"),
            "website": request.form.get("website"),
            "customer_logo": save_account_logo(
                request.files.get("customer_logo"),
                account["customer_logo"] if "customer_logo" in account.keys() else "",
            ),
            "pipeline_target": request.form.get("pipeline_target"),
            "nbm_target": request.form.get("nbm_target"),
            "sales_play": request.form.get("sales_play"),
            "notes": request.form.get("notes")
        }

        labels = {
            "account_name": "Account name",
            "pg_bible_order": "PG Bible order",
            "account_tier": "Account tier",
            "industry": "Industry",
            "business_unit": "Business unit / org",
            "country": "Country",
            "city": "City",
            "website": "Website",
            "customer_logo": "Customer logo",
            "pipeline_target": "Pipeline target",
            "nbm_target": "NBM target",
            "sales_play": "Account sales play or initiative",
            "owner_user_id": "Account owner",
            "owner_name": "Account owner name",
            "owner_email": "Account owner email",
            "notes": "Notes"
        }
        previous_owner_id = account["owner_user_id"] if "owner_user_id" in account.keys() else None
        selected_owner = assignable_user_by_id(request.form.get("owner_user_id"))
        if selected_owner:
            new_values["owner_user_id"] = selected_owner["id"]
            new_values["owner_name"] = selected_owner["full_name"]
            new_values["owner_email"] = selected_owner["email"]
        else:
            existing_owner = account_owner_payload(account)
            new_values["owner_user_id"] = existing_owner["owner_user_id"]
            new_values["owner_name"] = existing_owner["owner_name"]
            new_values["owner_email"] = existing_owner["owner_email"]

        changes = build_change_log(account, new_values, labels)
        changes.extend(build_custom_field_changes(custom_fields, custom_values, request.form))

        connection.execute("""
            UPDATE accounts
            SET account_name = ?,
                pg_bible_order = ?,
                account_tier = ?,
                industry = ?,
                business_unit = ?,
                country = ?,
                city = ?,
                website = ?,
                customer_logo = ?,
                pipeline_target = ?,
                nbm_target = ?,
                sales_play = ?,
                owner_user_id = ?,
                owner_name = ?,
                owner_email = ?,
                notes = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            new_values["account_name"],
            new_values["pg_bible_order"],
            new_values["account_tier"],
            new_values["industry"],
            new_values["business_unit"],
            new_values["country"],
            new_values["city"],
            new_values["website"],
            new_values["customer_logo"],
            new_values["pipeline_target"],
            new_values["nbm_target"],
            new_values["sales_play"],
            new_values["owner_user_id"],
            new_values["owner_name"],
            new_values["owner_email"],
            new_values["notes"],
            account_id
        ))

        save_account_custom_values(connection, account_id, custom_fields, request.form)

        if changes:
            audit_record_update(connection, "account", account_id, account, new_values, labels)
            add_timeline_entry(
                connection,
                "account",
                account_id,
                "Auto Audit",
                "Account updated: " + "; ".join(changes)
            )

        connection.commit()

        if selected_owner and str(previous_owner_id or "") != str(selected_owner["id"]):
            source_schema = current_user_schema() if using_postgres() else ""
            if using_postgres() and selected_owner["workspace_schema"]:
                share_full_account_to_member(
                    source_schema,
                    account_id,
                    selected_owner,
                    current_user()["full_name"] if current_user() else "",
                )
            upsert_account_share(connection, account_id, selected_owner)
            add_timeline_entry(
                connection,
                "account",
                account_id,
                "Account Ownership Reassigned",
                f"Account ownership reassigned to {selected_owner['full_name']}."
            )
            connection.commit()
        connection.close()

        return redirect(url_for("view_account", account_id=account_id))

    connection.close()
    return render_template(
        "edit_account.html",
        account=account,
        custom_fields=custom_fields,
        custom_values=custom_values,
        assignable_users=list_assignable_users(),
        owner=account_owner_payload(account)
    )


@app.route("/accounts/<int:account_id>/delete", methods=("POST",))
@admin_required
def delete_account(account_id):
    connection = get_db_connection()
    delete_account_records(connection, [account_id])
    connection.commit()
    connection.close()

    return redirect(url_for("accounts"))


@app.route("/accounts/bulk-delete", methods=("POST",))
@admin_required
def bulk_delete_accounts():
    account_ids = selected_record_ids()
    if account_ids:
        connection = get_db_connection()
        delete_account_records(connection, account_ids)
        connection.commit()
        connection.close()
    return redirect(url_for("accounts"))


@app.route("/accounts/<int:account_id>/timeline/add", methods=("POST",))
def add_account_timeline(account_id):
    connection = get_db_connection()
    add_timeline_entry(
        connection,
        "account",
        account_id,
        request.form.get("entry_type"),
        request.form.get("entry_text"),
        request.form.get("created_by") or "Melissa"
    )
    connection.commit()
    connection.close()

    return redirect(url_for("view_account", account_id=account_id))


def org_chart_person_options(connection, account):
    account_id = account["id"]
    options = []
    contacts = connection.execute("""
        SELECT *
        FROM contacts
        WHERE account_id = ?
          AND COALESCE(status, 'Active') != 'Archived'
        ORDER BY COALESCE(NULLIF(org_dept, ''), 'Unmapped'), name
    """, (account_id,)).fetchall()
    for contact in contacts:
        group_name = contact["org_dept"] or account["business_unit"] or ""
        options.append({
            "value": f"contact:{contact['id']}",
            "person_type": "contact",
            "contact_id": contact["id"],
            "partner_contact_id": None,
            "name": contact["name"] or "Unknown contact",
            "title": contact["job_title"] or "",
            "photo": contact["photo"] if "photo" in contact.keys() else "",
            "group_name": group_name,
            "source": "Customer",
            "link": url_for("edit_contact", contact_id=contact["id"]),
        })

    partner_contacts = connection.execute("""
        SELECT partner_contacts.*, partners.partner_name
        FROM partner_contact_accounts
        JOIN partner_contacts ON partner_contacts.id = partner_contact_accounts.partner_contact_id
        LEFT JOIN partners ON partners.id = partner_contacts.partner_id
        WHERE partner_contact_accounts.account_id = ?
        ORDER BY partners.partner_name, partner_contacts.name
    """, (account_id,)).fetchall()
    for contact in partner_contacts:
        partner_name = contact["partner_name"] or "Partner"
        options.append({
            "value": f"partner:{contact['id']}",
            "person_type": "partner",
            "contact_id": None,
            "partner_contact_id": contact["id"],
            "name": contact["name"] or "Unknown partner contact",
            "title": contact["job_title"] or "",
            "photo": "",
            "group_name": f"Partner: {partner_name}",
            "source": partner_name,
            "link": url_for("view_partner", partner_id=contact["partner_id"]),
        })
    return options


def parse_org_chart_person(value):
    raw_value = str(value or "")
    if ":" not in raw_value:
        return None, None, None
    person_type, raw_id = raw_value.split(":", 1)
    try:
        person_id = int(raw_id)
    except (TypeError, ValueError):
        return None, None, None
    if person_type == "contact":
        return "contact", person_id, None
    if person_type == "partner":
        return "partner", None, person_id
    return None, None, None


def org_chart_person_key(row):
    if row["person_type"] == "partner":
        return f"partner:{row['partner_contact_id']}"
    return f"contact:{row['contact_id']}"


def org_chart_existing_people(connection, chart_id):
    rows = connection.execute("""
        SELECT person_type, contact_id, partner_contact_id
        FROM account_org_chart_people
        WHERE chart_id = ?
    """, (chart_id,)).fetchall()
    return {org_chart_person_key(row) for row in rows}


def org_chart_existing_person_node(connection, chart_id, person_type, contact_id, partner_contact_id):
    if person_type == "partner":
        return connection.execute("""
            SELECT *
            FROM account_org_chart_people
            WHERE chart_id = ?
              AND person_type = 'partner'
              AND partner_contact_id = ?
        """, (chart_id, partner_contact_id)).fetchone()
    return connection.execute("""
        SELECT *
        FROM account_org_chart_people
        WHERE chart_id = ?
          AND person_type = 'contact'
          AND contact_id = ?
    """, (chart_id, contact_id)).fetchone()


def org_chart_manager_for_relationship(connection, chart_id, relationship, related_node_id):
    relationship = relationship or "with"
    try:
        related_node_id = int(related_node_id) if related_node_id else None
    except (TypeError, ValueError):
        related_node_id = None
    if relationship == "under" and related_node_id:
        return related_node_id
    if relationship in ("with", "above") and related_node_id:
        related = connection.execute("""
            SELECT manager_node_id
            FROM account_org_chart_people
            WHERE chart_id = ?
              AND id = ?
        """, (chart_id, related_node_id)).fetchone()
        return related["manager_node_id"] if related else None
    return None


def normalise_org_chart_relationship(value):
    relationship = value or "with"
    if relationship not in ("under", "with", "above"):
        relationship = "with"
    return relationship


def org_chart_level_for_relationship(connection, chart_id, relationship, related_node_id):
    relationship = normalise_org_chart_relationship(relationship)
    offset = {"above": -1, "with": 0, "under": 1}.get(relationship, 0)
    try:
        related_node_id = int(related_node_id) if related_node_id else None
    except (TypeError, ValueError):
        related_node_id = None
    if related_node_id:
        related = connection.execute("""
            SELECT visual_level
            FROM account_org_chart_people
            WHERE chart_id = ?
              AND id = ?
        """, (chart_id, related_node_id)).fetchone()
        related_level = int(related["visual_level"] or 0) if related else 0
        return related_level + offset
    return offset


def apply_org_chart_above_relationship(connection, chart_id, node_id, related_node_id):
    try:
        related_node_id = int(related_node_id) if related_node_id else None
    except (TypeError, ValueError):
        related_node_id = None
    if not related_node_id or node_id == related_node_id:
        return
    connection.execute("""
        UPDATE account_org_chart_people
        SET manager_node_id = ?,
            relationship_type = 'under',
            related_node_id = ?,
            visual_level = ?,
            last_updated = CURRENT_TIMESTAMP
        WHERE chart_id = ?
          AND id = ?
    """, (
        node_id,
        node_id,
        org_chart_level_for_relationship(connection, chart_id, "under", node_id),
        chart_id,
        related_node_id,
    ))


def parse_optional_int(value):
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def save_org_chart_node_position(
    connection,
    chart_id,
    node_id,
    relationship,
    related_node_id,
    visual_level=None,
    sort_order=None,
    x_position=None,
    y_position=None,
):
    relationship = normalise_org_chart_relationship(relationship)
    related_node_id_int = parse_optional_int(related_node_id)
    visual_level_int = parse_optional_int(visual_level)
    sort_order_int = parse_optional_int(sort_order)
    x_position_int = parse_optional_int(x_position)
    y_position_int = parse_optional_int(y_position)
    if related_node_id_int == node_id:
        relationship = "with"
        related_node_id_int = None
    elif related_node_id_int in org_chart_descendant_ids(connection, chart_id, node_id):
        raise ValueError("That move would create a reporting loop. Choose a different person.")

    if visual_level_int is not None:
        manager_node_id = None
        relationship = "with"
        related_node_id_int = None
    else:
        manager_node_id = org_chart_manager_for_relationship(connection, chart_id, relationship, related_node_id_int)
        visual_level_int = org_chart_level_for_relationship(connection, chart_id, relationship, related_node_id_int)
    connection.execute("""
        UPDATE account_org_chart_people
        SET manager_node_id = ?,
            relationship_type = ?,
            related_node_id = ?,
            visual_level = ?,
            sort_order = COALESCE(?, sort_order),
            x_position = COALESCE(?, x_position),
            y_position = COALESCE(?, y_position),
            last_updated = CURRENT_TIMESTAMP
        WHERE chart_id = ?
          AND id = ?
    """, (
        manager_node_id,
        relationship,
        related_node_id_int,
        visual_level_int,
        sort_order_int,
        x_position_int,
        y_position_int,
        chart_id,
        node_id,
    ))
    if relationship == "above" and related_node_id_int:
        apply_org_chart_above_relationship(connection, chart_id, node_id, related_node_id_int)
    return {
        "manager_node_id": manager_node_id,
        "relationship_type": relationship,
        "related_node_id": related_node_id_int,
        "visual_level": visual_level_int,
        "sort_order": sort_order_int,
        "x_position": x_position_int,
        "y_position": y_position_int,
    }


def org_chart_level_label(level):
    try:
        level = int(level or 0)
    except (TypeError, ValueError):
        level = 0
    if level <= -2:
        return "Executive row"
    if level == -1:
        return "Senior row"
    if level == 1:
        return "Supporting row"
    if level >= 2:
        return "Team row"
    return "Current row"


def org_chart_group_levels(nodes, visible_levels=None):
    rows = {}
    for node in nodes:
        try:
            level = int(node.get("visual_level") or 0)
        except (TypeError, ValueError):
            level = 0
        rows.setdefault(level, []).append(node)
    if visible_levels is not None:
        for level in visible_levels:
            rows.setdefault(level["level"], [])
    level_rows = []
    for level, people in sorted(rows.items(), key=lambda item: item[0]):
        sort_org_chart_nodes(people)
        level_rows.append({
            "level": level,
            "label": org_chart_level_label(level),
            "people": people,
        })
    return level_rows


def org_chart_visible_levels(nodes):
    levels = {-2, -1, 0, 1, 2}
    for node in nodes:
        level = parse_optional_int(node.get("visual_level"))
        levels.add(level if level is not None else 0)
    return [{"level": level, "label": org_chart_level_label(level)} for level in sorted(levels)]


def org_chart_descendant_ids(connection, chart_id, node_id):
    rows = connection.execute("""
        SELECT id, manager_node_id
        FROM account_org_chart_people
        WHERE chart_id = ?
    """, (chart_id,)).fetchall()
    children_by_manager = {}
    for row in rows:
        manager_id = row["manager_node_id"]
        if manager_id is not None:
            children_by_manager.setdefault(manager_id, []).append(row["id"])
    descendants = set()
    stack = list(children_by_manager.get(node_id, []))
    while stack:
        child_id = stack.pop()
        if child_id in descendants:
            continue
        descendants.add(child_id)
        stack.extend(children_by_manager.get(child_id, []))
    return descendants


def sort_org_chart_nodes(nodes):
    nodes.sort(key=lambda node: (
        node.get("sort_order") if node.get("sort_order") is not None else 999,
        (node.get("name") or "").casefold(),
        (node.get("title") or "").casefold(),
        node.get("id") or 0,
    ))
    for node in nodes:
        sort_org_chart_nodes(node["children"])


def org_chart_display_group(node, node_lookup, visited=None):
    visited = visited or set()
    node_id = node.get("id")
    if node_id in visited:
        return node.get("group_name") or ""
    visited.add(node_id)
    if node.get("group_name"):
        return node["group_name"]
    related = node_lookup.get(node.get("related_node_id"))
    if related:
        related_group = org_chart_display_group(related, node_lookup, visited)
        if related_group:
            return related_group
    manager = node_lookup.get(node.get("manager_node_id"))
    if manager:
        return org_chart_display_group(manager, node_lookup, visited)
    return ""


def org_chart_context(connection, account, chart_id=None):
    try:
        chart_id = int(chart_id) if chart_id else None
    except (TypeError, ValueError):
        chart_id = None
    charts = connection.execute("""
        SELECT *
        FROM account_org_charts
        WHERE account_id = ?
        ORDER BY last_updated DESC, chart_name
    """, (account["id"],)).fetchall()
    active_chart = None
    if chart_id:
        active_chart = connection.execute("""
            SELECT *
            FROM account_org_charts
            WHERE account_id = ?
              AND id = ?
        """, (account["id"], chart_id)).fetchone()
    if not active_chart and charts:
        active_chart = charts[0]

    person_options = org_chart_person_options(connection, account)
    person_lookup = {option["value"]: option for option in person_options}
    chart_nodes = []
    roots_by_group = {}
    unmapped = []
    if active_chart:
        rows = connection.execute("""
            SELECT *
            FROM account_org_chart_people
            WHERE chart_id = ?
            ORDER BY id
        """, (active_chart["id"],)).fetchall()
        node_lookup = {}
        for row in rows:
            key = org_chart_person_key(row)
            person = person_lookup.get(key)
            if not person:
                continue
            node = {
                "id": row["id"],
                "person_ref": key,
                "manager_node_id": row["manager_node_id"],
                "relationship_type": row["relationship_type"] if "relationship_type" in row.keys() else "with",
                "related_node_id": row["related_node_id"] if "related_node_id" in row.keys() else None,
                "visual_level": row["visual_level"] if "visual_level" in row.keys() else 0,
                "sort_order": row["sort_order"] if "sort_order" in row.keys() else None,
                "x_position": row["x_position"] if "x_position" in row.keys() else 0,
                "y_position": row["y_position"] if "y_position" in row.keys() else 0,
                "name": person["name"],
                "title": person["title"],
                "photo": person["photo"],
                "group_name": person["group_name"],
                "source": person["source"],
                "link": person["link"],
                "children": [],
            }
            node_lookup[node["id"]] = node
            chart_nodes.append(node)

        for node in chart_nodes:
            manager = node_lookup.get(node["manager_node_id"])
            if manager and manager["id"] != node["id"]:
                manager["children"].append(node)
            else:
                display_group = org_chart_display_group(node, node_lookup)
                roots_by_group.setdefault(display_group or "Organisation Chart", []).append(node)
        roots_by_group = dict(sorted(
            roots_by_group.items(),
            key=lambda item: (item[0] or "").casefold(),
        ))
        for people in roots_by_group.values():
            sort_org_chart_nodes(people)
        sort_org_chart_nodes(unmapped)
    chart_labels = []
    if active_chart:
        chart_labels = connection.execute("""
            SELECT *
            FROM account_org_chart_labels
            WHERE chart_id = ?
            ORDER BY id
        """, (active_chart["id"],)).fetchall()
    visible_levels = org_chart_visible_levels(chart_nodes)
    chart_roots = []
    for people in roots_by_group.values():
        chart_roots.extend(people)
    sort_org_chart_nodes(chart_roots)
    roots_by_group_levels = {
        group_name: {
            "top_count": len(people),
            "levels": org_chart_group_levels(people, visible_levels),
        }
        for group_name, people in roots_by_group.items()
    }

    used_people = org_chart_existing_people(connection, active_chart["id"]) if active_chart else set()
    available_people = [option for option in person_options if option["value"] not in used_people]
    return {
        "charts": charts,
        "active_chart": active_chart,
        "person_options": person_options,
        "available_people": available_people,
        "chart_nodes": chart_nodes,
        "roots_by_group": roots_by_group,
        "roots_by_group_levels": roots_by_group_levels,
        "chart_roots": chart_roots,
        "chart_labels": chart_labels,
        "visible_levels": visible_levels,
        "unmapped": unmapped,
    }


@app.route("/accounts/<int:account_id>/org-chart")
def account_org_chart(account_id):
    initialise_database(force=True)
    connection = get_db_connection()
    try:
        account = connection.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if not account:
            connection.close()
            return redirect(url_for("accounts"))
        context = org_chart_context(connection, account, request.args.get("chart_id"))
    except Exception:
        traceback.print_exc()
        connection.close()
        return redirect(url_for("view_account", account_id=account_id, message="Org chart could not be opened. The workspace schema was refreshed; try opening it again."))
    connection.close()
    return render_template(
        "account_org_chart.html",
        account=account,
        message=request.args.get("message", ""),
        **context,
    )


@app.route("/accounts/<int:account_id>/org-chart/create", methods=("POST",))
def create_account_org_chart(account_id):
    connection = get_db_connection()
    account = connection.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if not account:
        connection.close()
        return redirect(url_for("accounts"))
    chart_name = (request.form.get("chart_name") or "Account Org Chart").strip()
    cursor = connection.execute("""
        INSERT INTO account_org_charts (account_id, chart_name, notes)
        VALUES (?, ?, ?)
    """, (account_id, chart_name, request.form.get("notes", "")))
    chart_id = cursor.lastrowid
    audit_record_create(connection, "account_org_chart", chart_id, {
        "account_id": account_id,
        "chart_name": chart_name,
    })
    connection.commit()
    connection.close()
    return redirect(url_for("account_org_chart", account_id=account_id, chart_id=chart_id, message="Org chart created."))


@app.route("/accounts/<int:account_id>/org-chart/<int:chart_id>/update", methods=("POST",))
def update_account_org_chart(account_id, chart_id):
    connection = get_db_connection()
    chart = connection.execute("""
        SELECT *
        FROM account_org_charts
        WHERE account_id = ?
          AND id = ?
    """, (account_id, chart_id)).fetchone()
    if chart:
        new_values = {
            "chart_name": (request.form.get("chart_name") or chart["chart_name"]).strip(),
            "notes": request.form.get("notes", ""),
        }
        labels = {"chart_name": "Chart name", "notes": "Notes"}
        connection.execute("""
            UPDATE account_org_charts
            SET chart_name = ?,
                notes = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (new_values["chart_name"], new_values["notes"], chart_id))
        audit_record_update(connection, "account_org_chart", chart_id, chart, new_values, labels)
        connection.commit()
    connection.close()
    return redirect(url_for("account_org_chart", account_id=account_id, chart_id=chart_id, message="Org chart updated."))


@app.route("/accounts/<int:account_id>/org-chart/<int:chart_id>/delete", methods=("POST",))
def delete_account_org_chart(account_id, chart_id):
    connection = get_db_connection()
    chart = connection.execute("""
        SELECT *
        FROM account_org_charts
        WHERE account_id = ?
          AND id = ?
    """, (account_id, chart_id)).fetchone()
    if chart:
        audit_record_delete(connection, "account_org_chart", chart_id, chart["chart_name"])
        connection.execute("DELETE FROM account_org_chart_labels WHERE chart_id = ?", (chart_id,))
        connection.execute("DELETE FROM account_org_chart_people WHERE chart_id = ?", (chart_id,))
        connection.execute("DELETE FROM account_org_charts WHERE id = ?", (chart_id,))
        connection.commit()
    connection.close()
    return redirect(url_for("account_org_chart", account_id=account_id, message="Org chart deleted."))


@app.route("/accounts/<int:account_id>/org-chart/<int:chart_id>/layout/save", methods=("POST",))
def save_account_org_chart_layout(account_id, chart_id):
    connection = get_db_connection()
    chart = connection.execute("""
        SELECT *
        FROM account_org_charts
        WHERE account_id = ?
          AND id = ?
    """, (account_id, chart_id)).fetchone()
    if not chart:
        connection.close()
        return redirect(url_for("account_org_chart", account_id=account_id))

    try:
        actions = json.loads(request.form.get("layout_actions") or "[]")
    except json.JSONDecodeError:
        actions = []
    if not isinstance(actions, list):
        actions = []

    saved_count = 0
    error_message = ""
    local_node_ids = {}
    try:
        for action in actions:
            if not isinstance(action, dict):
                continue
            if action.get("type") == "label":
                label_text = (action.get("label_text") or "").strip()
                if not label_text:
                    continue
                x_position = parse_optional_int(action.get("x_position")) or 40
                y_position = parse_optional_int(action.get("y_position")) or 40
                label_id = parse_optional_int(action.get("label_id"))
                if label_id:
                    connection.execute("""
                        UPDATE account_org_chart_labels
                        SET label_text = ?,
                            x_position = ?,
                            y_position = ?,
                            last_updated = CURRENT_TIMESTAMP
                        WHERE chart_id = ?
                          AND account_id = ?
                          AND id = ?
                    """, (label_text, x_position, y_position, chart_id, account_id, label_id))
                else:
                    cursor = connection.execute("""
                        INSERT INTO account_org_chart_labels (
                            chart_id,
                            account_id,
                            label_text,
                            x_position,
                            y_position
                        )
                        VALUES (?, ?, ?, ?, ?)
                    """, (chart_id, account_id, label_text, x_position, y_position))
                    audit_record_create(connection, "account_org_chart_label", cursor.lastrowid, {
                        "account_id": account_id,
                        "chart_id": chart_id,
                        "label_text": label_text,
                    })
                saved_count += 1
                continue
            relationship = normalise_org_chart_relationship(action.get("relationship"))
            related_node_id = action.get("related_node_id") or None
            related_local_id = action.get("related_local_id") or ""
            if not related_node_id and related_local_id and related_local_id in local_node_ids:
                related_node_id = local_node_ids[related_local_id]
            manager_node_id = action.get("manager_node_id") or None
            if manager_node_id:
                relationship = "under"
                related_node_id = manager_node_id
            visual_level = action.get("visual_level")
            sort_order = action.get("sort_order")
            x_position = action.get("x_position")
            y_position = action.get("y_position")
            node_id = action.get("node_id")
            local_node_id = action.get("local_node_id") or ""
            if node_id:
                try:
                    node_id = int(node_id)
                except (TypeError, ValueError):
                    continue
                node = connection.execute("""
                    SELECT *
                    FROM account_org_chart_people
                    WHERE account_id = ?
                      AND chart_id = ?
                      AND id = ?
                """, (account_id, chart_id, node_id)).fetchone()
                if not node:
                    continue
                old_values = dict(node)
                new_values = save_org_chart_node_position(
                    connection,
                    chart_id,
                    node_id,
                    relationship,
                    related_node_id,
                    visual_level,
                    sort_order,
                    x_position,
                    y_position,
                )
                audit_record_update(
                    connection,
                    "account_org_chart_person",
                    node_id,
                    old_values,
                    new_values,
                    {
                        "manager_node_id": "Reports to",
                        "relationship_type": "Relationship",
                        "related_node_id": "Related person",
                        "visual_level": "Visual row",
                        "sort_order": "Row order",
                        "x_position": "Canvas x",
                        "y_position": "Canvas y",
                    }
                )
                saved_count += 1
                continue

            person_type, contact_id, partner_contact_id = parse_org_chart_person(action.get("person_ref"))
            if not person_type:
                continue
            existing_node = org_chart_existing_person_node(connection, chart_id, person_type, contact_id, partner_contact_id)
            if existing_node:
                old_values = dict(existing_node)
                new_values = save_org_chart_node_position(
                    connection,
                    chart_id,
                    existing_node["id"],
                    relationship,
                    related_node_id,
                    visual_level,
                    sort_order,
                    x_position,
                    y_position,
                )
                audit_record_update(
                    connection,
                    "account_org_chart_person",
                    existing_node["id"],
                    old_values,
                    new_values,
                    {
                        "manager_node_id": "Reports to",
                        "relationship_type": "Relationship",
                        "related_node_id": "Related person",
                        "visual_level": "Visual row",
                        "sort_order": "Row order",
                        "x_position": "Canvas x",
                        "y_position": "Canvas y",
                    }
                )
                saved_count += 1
                continue

            visual_level_int = parse_optional_int(visual_level)
            sort_order_int = parse_optional_int(sort_order)
            x_position_int = parse_optional_int(x_position) or 40
            y_position_int = parse_optional_int(y_position) or 40
            if visual_level_int is not None:
                manager_node_id = None
                relationship = "with"
                related_node_id = None
            else:
                manager_node_id = org_chart_manager_for_relationship(connection, chart_id, relationship, related_node_id)
                visual_level_int = org_chart_level_for_relationship(connection, chart_id, relationship, related_node_id)
            cursor = connection.execute("""
                INSERT INTO account_org_chart_people (
                    chart_id,
                    account_id,
                    person_type,
                    contact_id,
                    partner_contact_id,
                    manager_node_id,
                    relationship_type,
                    related_node_id,
                    visual_level,
                    sort_order,
                    x_position,
                    y_position
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                chart_id,
                account_id,
                person_type,
                contact_id,
                partner_contact_id,
                manager_node_id,
                relationship,
                related_node_id,
                visual_level_int,
                sort_order_int or 0,
                x_position_int,
                y_position_int,
            ))
            new_node_id = cursor.lastrowid
            if local_node_id:
                local_node_ids[local_node_id] = new_node_id
            if relationship == "above":
                apply_org_chart_above_relationship(connection, chart_id, new_node_id, related_node_id)
            audit_record_create(connection, "account_org_chart_person", new_node_id, {
                "account_id": account_id,
                "chart_id": chart_id,
                "person_type": person_type,
                "contact_id": contact_id,
                "partner_contact_id": partner_contact_id,
            })
            saved_count += 1
        connection.commit()
    except ValueError as exc:
        connection.rollback()
        error_message = str(exc)
    connection.close()

    message = error_message or f"Saved {saved_count} org chart move(s)."
    return redirect(url_for("account_org_chart", account_id=account_id, chart_id=chart_id, message=message))


@app.route("/accounts/<int:account_id>/org-chart/<int:chart_id>/people/add", methods=("POST",))
def add_account_org_chart_person(account_id, chart_id):
    connection = get_db_connection()
    chart = connection.execute("""
        SELECT *
        FROM account_org_charts
        WHERE account_id = ?
          AND id = ?
    """, (account_id, chart_id)).fetchone()
    if not chart:
        connection.close()
        return redirect(url_for("account_org_chart", account_id=account_id))
    person_type, contact_id, partner_contact_id = parse_org_chart_person(request.form.get("person_ref"))
    if not person_type:
        connection.close()
        return redirect(url_for("account_org_chart", account_id=account_id, chart_id=chart_id, message="Select a person before adding them to the chart."))
    person_key = f"partner:{partner_contact_id}" if person_type == "partner" else f"contact:{contact_id}"
    if person_key in org_chart_existing_people(connection, chart_id):
        connection.close()
        return redirect(url_for("account_org_chart", account_id=account_id, chart_id=chart_id, message="That person is already on this chart."))
    relationship = normalise_org_chart_relationship(request.form.get("relationship", "with"))
    related_node_id = request.form.get("related_node_id") or None
    manager_node_id = org_chart_manager_for_relationship(connection, chart_id, relationship, related_node_id)
    visual_level = org_chart_level_for_relationship(connection, chart_id, relationship, related_node_id)
    cursor = connection.execute("""
        INSERT INTO account_org_chart_people (
            chart_id,
            account_id,
            person_type,
            contact_id,
            partner_contact_id,
            manager_node_id,
            relationship_type,
            related_node_id,
            visual_level
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        chart_id,
        account_id,
        person_type,
        contact_id,
        partner_contact_id,
        manager_node_id,
        relationship,
        related_node_id,
        visual_level,
    ))
    node_id = cursor.lastrowid
    if relationship == "above":
        apply_org_chart_above_relationship(connection, chart_id, node_id, related_node_id)
    audit_record_create(connection, "account_org_chart_person", node_id, {
        "account_id": account_id,
        "chart_id": chart_id,
        "person_type": person_type,
        "contact_id": contact_id,
        "partner_contact_id": partner_contact_id,
    })
    connection.commit()
    connection.close()
    return redirect(url_for("account_org_chart", account_id=account_id, chart_id=chart_id, message="Person added to org chart."))


@app.route("/accounts/<int:account_id>/org-chart/<int:chart_id>/people/<int:node_id>/update", methods=("POST",))
def update_account_org_chart_person(account_id, chart_id, node_id):
    connection = get_db_connection()
    node = connection.execute("""
        SELECT *
        FROM account_org_chart_people
        WHERE account_id = ?
          AND chart_id = ?
          AND id = ?
    """, (account_id, chart_id, node_id)).fetchone()
    if node:
        relationship = normalise_org_chart_relationship(request.form.get("relationship", "with"))
        related_node_id = request.form.get("related_node_id") or None
        try:
            related_node_id_int = int(related_node_id) if related_node_id else None
        except (TypeError, ValueError):
            related_node_id_int = None
        if related_node_id_int == node_id:
            related_node_id = None
            relationship = "with"
        elif related_node_id_int in org_chart_descendant_ids(connection, chart_id, node_id):
            connection.close()
            return redirect(url_for(
                "account_org_chart",
                account_id=account_id,
                chart_id=chart_id,
                message="That relationship would create a reporting loop. Choose a different related person."
            ))
        manager_node_id = org_chart_manager_for_relationship(connection, chart_id, relationship, related_node_id)
        visual_level = org_chart_level_for_relationship(connection, chart_id, relationship, related_node_id)
        new_values = {
            "manager_node_id": manager_node_id,
            "relationship_type": relationship,
            "related_node_id": related_node_id,
            "visual_level": visual_level,
        }
        labels = {
            "manager_node_id": "Reports to",
            "relationship_type": "Relationship",
            "related_node_id": "Related person",
            "visual_level": "Visual row",
        }
        connection.execute("""
            UPDATE account_org_chart_people
            SET manager_node_id = ?,
                relationship_type = ?,
                related_node_id = ?,
                visual_level = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (manager_node_id, relationship, related_node_id, visual_level, node_id))
        if relationship == "above":
            apply_org_chart_above_relationship(connection, chart_id, node_id, related_node_id)
        audit_record_update(connection, "account_org_chart_person", node_id, node, new_values, labels)
        connection.commit()
    connection.close()
    return redirect(url_for("account_org_chart", account_id=account_id, chart_id=chart_id, message="Org chart person updated."))


@app.route("/accounts/<int:account_id>/org-chart/<int:chart_id>/people/<int:node_id>/delete", methods=("POST",))
def delete_account_org_chart_person(account_id, chart_id, node_id):
    connection = get_db_connection()
    node = connection.execute("""
        SELECT *
        FROM account_org_chart_people
        WHERE account_id = ?
          AND chart_id = ?
          AND id = ?
    """, (account_id, chart_id, node_id)).fetchone()
    if node:
        connection.execute("""
            UPDATE account_org_chart_people
            SET manager_node_id = ?
            WHERE chart_id = ?
              AND manager_node_id = ?
        """, (node["manager_node_id"], chart_id, node_id))
        audit_record_delete(connection, "account_org_chart_person", node_id, f"Node {node_id}")
        connection.execute("DELETE FROM account_org_chart_people WHERE id = ?", (node_id,))
        connection.commit()
    connection.close()
    return redirect(url_for("account_org_chart", account_id=account_id, chart_id=chart_id, message="Person removed from org chart."))


@app.route("/contacts")
def contacts():
    connection = get_db_connection()
    account_filter = request.args.get("account_id", "")
    name_filter = request.args.get("contact_name", "").strip()
    status_filter = request.args.get("status", "")
    query = """
        SELECT contacts.*, accounts.account_name, accounts.account_tier, accounts.business_unit
        FROM contacts
        LEFT JOIN accounts ON contacts.account_id = accounts.id
        WHERE COALESCE(contacts.status, 'Active') != 'Archived'
    """
    params = []
    if account_filter:
        query += " AND contacts.account_id = ?"
        params.append(account_filter)
    if name_filter:
        query += " AND LOWER(contacts.name) LIKE ?"
        params.append(f"%{name_filter.lower()}%")
    if status_filter:
        query += " AND COALESCE(contacts.status, 'Active') = ?"
        params.append(status_filter)
    query += " ORDER BY contacts.name"
    contacts = connection.execute(query, params).fetchall()
    accounts = connection.execute("SELECT id, account_name FROM accounts ORDER BY account_name").fetchall()
    connection.close()
    return render_template(
        "contacts.html",
        contacts=contacts,
        accounts=accounts,
        account_filter=account_filter,
        name_filter=name_filter,
        status_filter=status_filter
    )


@app.route("/contacts/add", methods=("GET", "POST"))
def add_contact():
    if request.method == "POST":
        connection = get_db_connection()
        photo_path = save_contact_photo(request.files.get("photo"))
        cursor = connection.execute("""
            INSERT INTO contacts (
                account_id, category, photo, name, job_title, org_dept, responsibilities,
                email, phone, office_phone, mobile_phone, location, linkedin, bmc_relationship, characteristics,
                background, personal_interests, personal_win, education,
                social_media, additional_notes, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request.form.get("account_id"),
            request.form.get("category"),
            photo_path,
            request.form.get("name"),
            request.form.get("job_title"),
            request.form.get("org_dept"),
            request.form.get("responsibilities"),
            request.form.get("email"),
            combined_contact_phone(request.form.get("office_phone"), request.form.get("mobile_phone"), request.form.get("phone")),
            request.form.get("office_phone"),
            request.form.get("mobile_phone"),
            request.form.get("location"),
            request.form.get("linkedin"),
            request.form.get("bmc_relationship"),
            request.form.get("characteristics"),
            request.form.get("background"),
            request.form.get("personal_interests"),
            request.form.get("personal_win"),
            request.form.get("education"),
            request.form.get("social_media"),
            request.form.get("additional_notes"),
            request.form.get("status") or "Active"
        ))
        contact_id = cursor.lastrowid
        audit_record_create(connection, "contact", contact_id, {
            "account_id": request.form.get("account_id"),
            "category": request.form.get("category"),
            "name": request.form.get("name"),
            "job_title": request.form.get("job_title"),
            "org_dept": request.form.get("org_dept"),
            "email": request.form.get("email"),
            "phone": combined_contact_phone(request.form.get("office_phone"), request.form.get("mobile_phone"), request.form.get("phone")),
            "office_phone": request.form.get("office_phone"),
            "mobile_phone": request.form.get("mobile_phone"),
            "photo": photo_path,
            "status": request.form.get("status") or "Active",
            "bmc_relationship": request.form.get("bmc_relationship"),
        })
        connection.commit()
        connection.close()

        return redirect(url_for("contacts"))

    connection = get_db_connection()
    accounts = connection.execute("""
        SELECT *
        FROM accounts
        ORDER BY account_name, business_unit
    """).fetchall()
    connection.close()

    return render_template("add_contact.html", accounts=accounts)


@app.route("/contacts/<int:contact_id>")
def view_contact(contact_id):
    connection = get_db_connection()

    contact = connection.execute("""
        SELECT contacts.*, accounts.account_name, accounts.account_tier
        FROM contacts
        LEFT JOIN accounts ON contacts.account_id = accounts.id
        WHERE contacts.id = ?
    """, (contact_id,)).fetchone()

    timeline_entries = connection.execute("""
        SELECT *
        FROM timeline_entries
        WHERE related_type = 'contact'
          AND related_id = ?
        ORDER BY date_created DESC
    """, (contact_id,)).fetchall()

    connection.close()

    return render_template(
        "view_contact.html",
        contact=contact,
        timeline_entries=timeline_entries
    )


@app.route("/contacts/<int:contact_id>/print")
def print_contact(contact_id):
    connection = get_db_connection()
    contact = connection.execute("""
        SELECT contacts.*, accounts.account_name, accounts.account_tier
        FROM contacts
        LEFT JOIN accounts ON contacts.account_id = accounts.id
        WHERE contacts.id = ?
    """, (contact_id,)).fetchone()
    connection.close()
    if not contact:
        return redirect(url_for("contacts", error="The selected contact could not be found."))
    return render_template("print_contact.html", contact=contact)


@app.route("/contacts/<int:contact_id>/timeline/add", methods=("POST",))
def add_contact_timeline(contact_id):
    connection = get_db_connection()
    add_timeline_entry(
        connection,
        "contact",
        contact_id,
        request.form.get("entry_type"),
        request.form.get("entry_text"),
        request.form.get("created_by") or "Melissa"
    )
    connection.commit()
    connection.close()

    return redirect(url_for("view_contact", contact_id=contact_id))


@app.route("/contacts/<int:contact_id>/edit", methods=("GET", "POST"))
def edit_contact(contact_id):
    connection = get_db_connection()

    contact = connection.execute(
        "SELECT * FROM contacts WHERE id = ?",
        (contact_id,)
    ).fetchone()

    accounts = connection.execute("""
        SELECT *
        FROM accounts
        ORDER BY account_name, business_unit
    """).fetchall()

    if request.method == "POST":
        photo_path = save_contact_photo(request.files.get("photo"), contact["photo"] if "photo" in contact.keys() else "")
        new_values = {
            "account_id": request.form.get("account_id"),
            "category": request.form.get("category"),
            "photo": photo_path,
            "name": request.form.get("name"),
            "job_title": request.form.get("job_title"),
            "org_dept": request.form.get("org_dept"),
            "responsibilities": request.form.get("responsibilities"),
            "email": request.form.get("email"),
            "phone": combined_contact_phone(request.form.get("office_phone"), request.form.get("mobile_phone"), request.form.get("phone")),
            "office_phone": request.form.get("office_phone"),
            "mobile_phone": request.form.get("mobile_phone"),
            "location": request.form.get("location"),
            "linkedin": request.form.get("linkedin"),
            "status": request.form.get("status") or "Active",
            "bmc_relationship": request.form.get("bmc_relationship"),
            "characteristics": request.form.get("characteristics"),
            "background": request.form.get("background"),
            "personal_interests": request.form.get("personal_interests"),
            "personal_win": request.form.get("personal_win"),
            "education": request.form.get("education"),
            "social_media": request.form.get("social_media"),
            "additional_notes": request.form.get("additional_notes")
        }

        labels = {
            "account_id": "Account",
            "category": "Category",
            "photo": "Photo",
            "name": "Name",
            "job_title": "Job title",
            "org_dept": "Org / Dept",
            "responsibilities": "Responsibilities",
            "email": "Email",
            "phone": "Phone",
            "office_phone": "Office phone",
            "mobile_phone": "Mobile phone",
            "location": "Location",
            "linkedin": "LinkedIn",
            "status": "Status",
            "bmc_relationship": "BMC relationship",
            "characteristics": "Characteristics",
            "background": "Background",
            "personal_interests": "Personal interests",
            "personal_win": "Personal win",
            "education": "Education",
            "social_media": "Social media",
            "additional_notes": "Additional notes"
        }

        changes = build_change_log(contact, new_values, labels)

        connection.execute("""
            UPDATE contacts
            SET account_id = ?,
                category = ?,
                photo = ?,
                name = ?,
                job_title = ?,
                org_dept = ?,
                responsibilities = ?,
                email = ?,
                phone = ?,
                office_phone = ?,
                mobile_phone = ?,
                location = ?,
                linkedin = ?,
                status = ?,
                bmc_relationship = ?,
                characteristics = ?,
                background = ?,
                personal_interests = ?,
                personal_win = ?,
                education = ?,
                social_media = ?,
                additional_notes = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            new_values["account_id"],
            new_values["category"],
            new_values["photo"],
            new_values["name"],
            new_values["job_title"],
            new_values["org_dept"],
            new_values["responsibilities"],
            new_values["email"],
            new_values["phone"],
            new_values["office_phone"],
            new_values["mobile_phone"],
            new_values["location"],
            new_values["linkedin"],
            new_values["status"],
            new_values["bmc_relationship"],
            new_values["characteristics"],
            new_values["background"],
            new_values["personal_interests"],
            new_values["personal_win"],
            new_values["education"],
            new_values["social_media"],
            new_values["additional_notes"],
            contact_id
        ))

        if changes:
            audit_record_update(connection, "contact", contact_id, contact, new_values, labels)
            add_timeline_entry(
                connection,
                "contact",
                contact_id,
                "Auto Audit",
                "Contact updated: " + "; ".join(changes)
            )

        commit_with_retry(connection)
        connection.close()

        return redirect(url_for("view_contact", contact_id=contact_id))

    connection.close()

    return render_template(
        "edit_contact.html",
        contact=contact,
        accounts=accounts
    )


@app.route("/contacts/<int:contact_id>/delete", methods=("POST",))
def delete_contact(contact_id):
    connection = get_db_connection()
    delete_contact_records(connection, [contact_id])
    connection.commit()
    connection.close()

    return redirect(url_for("contacts"))


@app.route("/contacts/bulk-delete", methods=("POST",))
def bulk_delete_contacts():
    contact_ids = selected_record_ids()
    if contact_ids:
        connection = get_db_connection()
        delete_contact_records(connection, contact_ids)
        connection.commit()
        connection.close()
    return redirect(url_for("contacts"))


@app.route("/admin/contacts/bulk-delete", methods=("GET", "POST"))
@admin_required
def admin_bulk_delete_contacts():
    connection = get_db_connection()
    if request.method == "POST":
        contact_ids = selected_record_ids()
        if contact_ids:
            delete_contact_records(connection, contact_ids)
            connection.commit()
        connection.close()
        return redirect(url_for("admin_bulk_delete_contacts", message=f"Deleted {len(contact_ids)} contact record(s)."))

    contacts = connection.execute("""
        SELECT contacts.*, accounts.account_name
        FROM contacts
        LEFT JOIN accounts ON contacts.account_id = accounts.id
        ORDER BY accounts.account_name, contacts.name
    """).fetchall()
    connection.close()
    return render_template(
        "admin_bulk_delete_contacts.html",
        contacts=contacts,
        message=request.args.get("message", ""),
    )


@app.route("/outreach")
def outreach():
    user = current_user()
    fy_filter = request.args.get("fy")
    quarter_filter = request.args.get("quarter")
    sales_play_filter = request.args.get("sales_play")
    account_filter = request.args.get("account_id")
    outcome_filter = request.args.get("outcome")
    due_start_filter = request.args.get("due_start", "")
    due_end_filter = request.args.get("due_end", "")
    activity_start_filter = request.args.get("activity_start", "")
    activity_end_filter = request.args.get("activity_end", "")
    updated_start_filter = request.args.get("updated_start", "")
    updated_end_filter = request.args.get("updated_end", "")
    overdue_filter = request.args.get("overdue", "")
    followup_due_filter = request.args.get("followup_due", "")
    pg_success_filter = request.args.get("pg_success", "")
    selected_statuses = request.args.getlist("task_status")
    if not selected_statuses:
        selected_statuses = ["All Open"]
    closed_statuses = ["Closed", "Completed", "Cancelled"]

    connection = get_db_connection()
    if close_expired_completed_outreach(connection):
        connection.commit()

    query = """
        SELECT
            outreach.*,
            accounts.account_name,
            accounts.account_tier,
            COALESCE(contacts.name, partner_contacts.name) AS contact_name,
            COALESCE(
                (
                    SELECT COALESCE(recipient_contacts.name, recipient_partner_contacts.name)
                    FROM outreach_recipients
                    LEFT JOIN contacts AS recipient_contacts ON outreach_recipients.contact_id = recipient_contacts.id
                    LEFT JOIN partner_contacts AS recipient_partner_contacts ON outreach_recipients.partner_contact_id = recipient_partner_contacts.id
                    WHERE outreach_recipients.outreach_id = outreach.id
                    ORDER BY outreach_recipients.sort_order, outreach_recipients.id
                    LIMIT 1
                ),
                COALESCE(contacts.name, partner_contacts.name)
            ) AS display_contact_name,
            COALESCE(
                (
                    SELECT COUNT(*)
                    FROM outreach_recipients
                    WHERE outreach_recipients.outreach_id = outreach.id
                ),
                CASE WHEN outreach.contact_id IS NOT NULL OR outreach.partner_contact_id IS NOT NULL THEN 1 ELSE 0 END
            ) AS recipient_count,
            COALESCE(contacts.job_title, partner_contacts.job_title) AS contact_job_title,
            COALESCE(contacts.email, partner_contacts.email) AS contact_email,
            COALESCE(contacts.phone, partner_contacts.phone) AS contact_phone,
            COALESCE(contacts.linkedin, partner_contacts.linkedin) AS contact_linkedin,
            CASE WHEN outreach.partner_contact_id IS NOT NULL THEN 'Partner' ELSE 'Customer' END AS contact_source,
            partners.partner_name AS partner_name
        FROM outreach
        LEFT JOIN accounts ON outreach.account_id = accounts.id
        LEFT JOIN contacts ON outreach.contact_id = contacts.id
        LEFT JOIN partner_contacts ON outreach.partner_contact_id = partner_contacts.id
        LEFT JOIN partners ON partner_contacts.partner_id = partners.id
        WHERE 1 = 1
    """

    params = []

    if fy_filter:
        query += " AND outreach.fy = ?"
        params.append(fy_filter)

    if quarter_filter:
        query += " AND outreach.quarter = ?"
        params.append(quarter_filter)

    if sales_play_filter:
        query += " AND outreach.sales_play = ?"
        params.append(sales_play_filter)

    if account_filter:
        query += " AND outreach.account_id = ?"
        params.append(account_filter)

    if outcome_filter:
        query += " AND outreach.outcome = ?"
        params.append(outcome_filter)

    if due_start_filter:
        query += " AND outreach.next_action_date >= ?"
        params.append(due_start_filter)

    if due_end_filter:
        query += " AND outreach.next_action_date <= ?"
        params.append(due_end_filter)

    if activity_start_filter:
        query += " AND outreach.activity_date >= ?"
        params.append(activity_start_filter)

    if activity_end_filter:
        query += " AND outreach.activity_date <= ?"
        params.append(activity_end_filter)

    if updated_start_filter:
        query += " AND date(outreach.last_updated) >= date(?)"
        params.append(updated_start_filter)

    if updated_end_filter:
        query += " AND date(outreach.last_updated) <= date(?)"
        params.append(updated_end_filter)

    if overdue_filter:
        query += f" AND {overdue_task_sql('outreach')}"
        params.extend(overdue_task_params())

    if followup_due_filter:
        followup_until = request.args.get("followup_until") or (current_app_datetime().date() + timedelta(days=7)).isoformat()
        query += f"""
            AND outreach.next_action_date IS NOT NULL
            AND outreach.next_action_date != ''
            AND date(outreach.next_action_date) <= date(?)
            AND {open_task_sql('outreach')}
        """
        params.append(followup_until)
        params.extend(open_task_params())

    if pg_success_filter:
        query += """
            AND (
                  outreach.outcome IN ('Discovery Booked', 'NBM Booked', 'Exec Meeting Booked', 'Meeting Booked')
               OR outreach.activity_type = 'Meeting'
            )
        """

    if "All" in selected_statuses:
        pass
    elif "All Closed" in selected_statuses:
        placeholders = ",".join("?" for _ in closed_statuses)
        query += f" AND COALESCE(outreach.task_status, 'Not Started') IN ({placeholders})"
        params.extend(closed_statuses)
    elif "All Open" in selected_statuses:
        placeholders = ",".join("?" for _ in closed_statuses)
        query += f" AND COALESCE(outreach.task_status, '') NOT IN ({placeholders})"
        params.extend(closed_statuses)
    elif selected_statuses:
        placeholders = ",".join("?" for _ in selected_statuses)
        query += f" AND COALESCE(outreach.task_status, 'Not Started') IN ({placeholders})"
        params.extend(selected_statuses)

    query += """
        ORDER BY
            CASE
                WHEN outreach.next_action_date IS NULL OR outreach.next_action_date = ''
                THEN 1 ELSE 0
            END,
            outreach.next_action_date ASC,
            outreach.next_action_time ASC,
            outreach.activity_date DESC,
            outreach.id DESC
    """

    workspace_schema = current_user_schema() if using_postgres() else ""
    outreach_records = []
    for row in connection.execute(query, params).fetchall():
        row_dict = dict(row)
        row_dict["workspace_schema"] = workspace_schema
        row_dict["due_rag_class"] = due_rag_class(
            row_dict.get("next_action_date"),
            row_dict.get("next_action_time"),
            row_dict.get("task_status"),
        )
        row_dict["can_modify"] = task_can_be_modified(row_dict)
        row_dict["additional_contact_count"] = max(int(row_dict.get("recipient_count") or 0) - 1, 0)
        outreach_records.append(row_dict)

    accounts = connection.execute(
        "SELECT * FROM accounts ORDER BY account_name"
    ).fetchall()
    existing_sales_plays = connection.execute("""
        SELECT DISTINCT sales_play
        FROM outreach
        WHERE sales_play IS NOT NULL
          AND sales_play != ''
        ORDER BY sales_play
    """).fetchall()
    sales_play_options = sorted(row["sales_play"] for row in existing_sales_plays if row["sales_play"])

    connection.close()

    return render_template(
        "outreach.html",
        outreach_records=outreach_records,
        accounts=accounts,
        sales_play_options=sales_play_options,
        fy_filter=fy_filter,
        quarter_filter=quarter_filter,
        sales_play_filter=sales_play_filter,
        account_filter=account_filter,
        outcome_filter=outcome_filter,
        selected_statuses=selected_statuses,
        assignable_users=list_assignable_users(),
        message=request.args.get("message", ""),
        error=request.args.get("error", ""),
    )


@app.route("/outreach/add", methods=("GET", "POST"))
def add_outreach():
    connection = get_db_connection()
    prefill = {}
    error = ""
    prefill_from_id = request.args.get("prefill_from")
    if prefill_from_id:
        source = connection.execute(
            "SELECT * FROM outreach WHERE id = ?",
            (prefill_from_id,),
        ).fetchone()
        if source:
            source_contact_values = selected_outreach_contact_values(connection, source)
            prefill = {
                "account_id": source["account_id"],
                "contact_ids": source_contact_values,
                "notes": f"Follow-on task from completed outreach #{source['id']}.",
            }

    if request.method == "POST":
        prefill = dict(request.form)
        requested_status = normalise_task_status(request.form.get("task_status", "Not Started"))
        recipient_values = outreach_contact_form_values(request.form)
        recipients = parse_outreach_contact_selections(recipient_values)
        contact_id, partner_contact_id = recipients[0] if recipients else (None, None)
        if not fy_quarter_are_valid(request.form.get("fy"), request.form.get("quarter")):
            error = fy_quarter_required_message()
        elif not outreach_recipients_match_account(connection, request.form.get("account_id"), recipients):
            error = "Select a contact or partner contact that belongs to the selected account."
        elif status_requires_activity_update(requested_status) and not activity_update_is_valid(request.form.get("next_action")):
            error = activity_update_required_message()
        else:
            sales_play_value = request.form.get("sales_play")
            outcome_value = normalise_outreach_outcome(request.form.get("outcome"))
            scheduled_meeting_date, scheduled_meeting_time = split_scheduled_meeting_datetime(
                request.form.get("scheduled_meeting_at") if outcome_requires_scheduled_meeting(outcome_value) else ""
            )
            assigned_to = request.form.get("assigned_to") or default_outreach_assignee()
            cursor = connection.execute("""
                INSERT INTO outreach (
                    fy, quarter, campaign, sales_play, account_id, contact_id, partner_contact_id, activity_type,
                    activity_date, activity_time, subject, notes, outcome,
                    scheduled_meeting_date, scheduled_meeting_time,
                    next_action, next_action_date, next_action_time,
                    task_status, completed_at, assigned_to
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                request.form.get("fy"),
                request.form.get("quarter"),
                sales_play_value,
                sales_play_value,
                request.form.get("account_id"),
                contact_id,
                partner_contact_id,
                request.form.get("activity_type"),
                request.form.get("activity_date"),
                request.form.get("activity_time"),
                request.form.get("subject"),
                request.form.get("notes", ""),
                outcome_value,
                scheduled_meeting_date,
                scheduled_meeting_time,
                request.form.get("next_action"),
                request.form.get("next_action_date"),
                request.form.get("next_action_time"),
                requested_status,
                app_datetime_key() if requested_status == "Completed" else "",
                assigned_to
            ))
            outreach_id = cursor.lastrowid
            save_outreach_recipients(connection, outreach_id, recipients)
            audit_record_create(connection, "outreach", outreach_id, {
                "fy": request.form.get("fy"),
                "quarter": request.form.get("quarter"),
                "campaign": sales_play_value,
                "sales_play": sales_play_value,
                "account_id": request.form.get("account_id"),
                "contact_id": contact_id,
                "partner_contact_id": partner_contact_id,
                "activity_type": request.form.get("activity_type"),
                "activity_date": request.form.get("activity_date"),
                "activity_time": request.form.get("activity_time"),
                "subject": request.form.get("subject"),
                "outcome": outcome_value,
                "scheduled_meeting_date": scheduled_meeting_date,
                "scheduled_meeting_time": scheduled_meeting_time,
                "next_action": request.form.get("next_action"),
                "next_action_date": request.form.get("next_action_date"),
                "next_action_time": request.form.get("next_action_time"),
                "task_status": requested_status,
                "completed_at": app_datetime_key() if requested_status == "Completed" else "",
                "assigned_to": assigned_to,
            })

            connection.commit()
            connection.close()

            return redirect(url_for("outreach"))

    if request.method == "POST":
        selected_contact_values = outreach_contact_form_values(request.form)
        selected_account_id = request.form.get("account_id") or ""
    else:
        selected_contact_values = prefill.get("contact_ids", [])
        selected_account_id = request.args.get("account_id") or prefill.get("account_id", "")

    accounts = connection.execute("SELECT * FROM accounts ORDER BY account_name").fetchall()

    contacts = connection.execute("""
        SELECT contacts.*, accounts.account_name, accounts.account_tier
        FROM contacts
        LEFT JOIN accounts ON contacts.account_id = accounts.id
        WHERE COALESCE(contacts.status, 'Active') = 'Active'
          AND contacts.account_id = ?
        ORDER BY contacts.name
    """, (selected_account_id,)).fetchall() if selected_account_id else []
    sales_play_rows = account_sales_play_options(connection)
    partner_activity_options = account_partner_activity_options(connection)
    partner_contacts = partner_contacts_for_outreach(connection, selected_account_id)

    profile = connection.execute("""
        SELECT *
        FROM user_profile
        WHERE id = 1
    """).fetchone()
    prefill.setdefault("assigned_to", default_outreach_assignee())
    prefill["scheduled_meeting_at"] = scheduled_meeting_datetime_value(
        prefill.get("scheduled_meeting_date", ""),
        prefill.get("scheduled_meeting_time", ""),
    )
    non_working_block_rows = connection.execute("""
        SELECT *
        FROM non_working_blocks
        ORDER BY start_date, end_date, id
    """).fetchall()
    connection.close()

    return render_template(
        "add_outreach.html",
        accounts=accounts,
        contacts=contacts,
        profile=profile,
        non_working_blocks=non_working_block_rows,
        sales_play_options=sales_play_rows,
        partner_activity_options=partner_activity_options,
        partner_contacts=partner_contacts,
        prefill=prefill,
        selected_contact_values=selected_contact_values,
        selected_account_id=selected_account_id,
        error=error
    )


@app.route("/outreach/campaign-builder", methods=("GET", "POST"))
def campaign_builder():
    connection = get_db_connection()
    generated_count = 0
    error = ""
    selected_account_id = request.form.get("account_id") or request.args.get("account_id") or ""
    selected_contact_ids = request.form.getlist("contact_ids")
    selected_pg_week_start = request.form.get("pg_week_start", "")
    selected_campaign_start = request.form.get("campaign_start_date", "")
    selected_campaign_end = request.form.get("campaign_end_date", "")
    selected_total_tasks = request.form.get("total_outreach_tasks", "8")
    selected_times_per_week = request.form.get("times_per_week", "2")
    selected_sales_play = request.form.get("sales_play") or request.form.get("sales_plays", "")
    selected_fy = request.form.get("fy", "")
    selected_quarter = request.form.get("quarter", "")
    success_context_summary = ""
    profile = connection.execute("""
        SELECT *
        FROM user_profile
        WHERE id = 1
    """).fetchone()
    non_working_block_rows = connection.execute("""
        SELECT *
        FROM non_working_blocks
        ORDER BY start_date, end_date, id
    """).fetchall()
    non_working_blocks = parse_non_working_blocks(non_working_block_rows)

    if request.method == "POST":
        account_id = request.form.get("account_id")
        pg_week_start_raw = request.form.get("pg_week_start", "")
        campaign_start_raw = request.form.get("campaign_start_date", "")
        campaign_end_raw = request.form.get("campaign_end_date", "")
        try:
            total_tasks = max(1, min(int(request.form.get("total_outreach_tasks", "8") or 8), 50))
        except ValueError:
            total_tasks = 8
        try:
            times_per_week = max(1, min(int(request.form.get("times_per_week", "2") or 2), 7))
        except ValueError:
            times_per_week = 2
        selected_total_tasks = str(total_tasks)
        selected_times_per_week = str(times_per_week)
        contact_ids = request.form.getlist("contact_ids")
        sales_play = (request.form.get("sales_play") or request.form.get("sales_plays", "")).strip()
        if "\n" in sales_play:
            sales_play = next((line.strip() for line in sales_play.splitlines() if line.strip()), "")
        if not sales_play:
            sales_play = "PG week sales play"
        selected_sales_play = sales_play
        selected_fy = request.form.get("fy", "")
        selected_quarter = request.form.get("quarter", "")

        if not account_id:
            error = "Select an account before generating a campaign."
        elif not contact_ids:
            error = "Select at least one contact for the selected account before generating a campaign."
        elif not fy_quarter_are_valid(selected_fy, selected_quarter):
            error = fy_quarter_required_message()
        elif account_id and pg_week_start_raw and campaign_start_raw and campaign_end_raw and contact_ids:
            today = datetime.now().date()
            pg_week_start = datetime.strptime(pg_week_start_raw, "%Y-%m-%d").date()
            campaign_start = datetime.strptime(campaign_start_raw, "%Y-%m-%d").date()
            campaign_end = datetime.strptime(campaign_end_raw, "%Y-%m-%d").date()
            if campaign_end < campaign_start:
                campaign_start, campaign_end = campaign_end, campaign_start
            if campaign_start < today:
                campaign_start = today
                selected_campaign_start = campaign_start.isoformat()
            if campaign_end < campaign_start:
                error = "Campaign end date cannot be earlier than the campaign start date."
            if error:
                contacts = []
            else:
                placeholders = ",".join("?" for _ in contact_ids)
                contacts = connection.execute(f"""
                    SELECT *
                    FROM contacts
                    WHERE account_id = ?
                      AND id IN ({placeholders})
                    ORDER BY name
                """, [account_id, *contact_ids]).fetchall()

            account = connection.execute("""
                SELECT account_name
                FROM accounts
                WHERE id = ?
            """, (account_id,)).fetchone()

            if not account:
                error = "The selected account could not be found."
            elif not error and not contacts:
                error = "The selected account has no matching selected contacts. Add a contact to the account first, then build the campaign."
            elif not error:
                valid_contact_ids = [str(contact["id"]) for contact in contacts]
                selected_contact_ids = valid_contact_ids
                account_name = account["account_name"] if account else "Selected account"
                campaign_name = sales_play
                assigned_to = request.form.get("assigned_to") or default_outreach_assignee()
                fy = selected_fy
                quarter = selected_quarter
                success_context = build_campaign_success_context(connection, account_id, valid_contact_ids, sales_play)
                success_context_summary = success_context["summary"]
                schedule_templates = success_context["templates"]
                selected_fy = fy
                selected_quarter = quarter
                reserved_rows = connection.execute("""
                    SELECT next_action_date, next_action_time
                    FROM outreach
                    WHERE next_action_date IS NOT NULL
                      AND next_action_date != ''
                      AND COALESCE(task_status, '') NOT IN ('Closed', 'Completed', 'Cancelled')
                """).fetchall()
                reserved_slots = {
                    (row["next_action_date"], row["next_action_time"] or "09:00")
                    for row in reserved_rows
                    if row["next_action_date"]
                }
                submitted_at = current_app_datetime()

                for contact in contacts:
                    for step in build_campaign_schedule(
                        campaign_start,
                        campaign_end,
                        total_tasks,
                        times_per_week,
                        schedule_templates,
                        profile=profile,
                        reserved_slots=reserved_slots,
                        non_working_blocks=non_working_blocks,
                        submitted_at=submitted_at
                    ):
                        action_date = step["action_date"]
                        subject = f"{step['subject_prefix']}: {sales_play}"
                        notes = (
                            f"Auto-generated campaign step for {account_name}. "
                            f"Campaign window: {campaign_start.isoformat()} to {campaign_end.isoformat()}. "
                            f"Total outreach tasks: {total_tasks}. "
                            f"Times per week: {times_per_week}. "
                            f"Sales play: {sales_play}. Contact: {contact['name']}. "
                            f"{success_context_summary}"
                        )
                        connection.execute("""
                            INSERT INTO outreach (
                                fy,
                                quarter,
                                campaign,
                                sales_play,
                                campaign_start_date,
                                campaign_end_date,
                                campaign_tasks_per_week,
                                campaign_total_tasks,
                                account_id,
                                contact_id,
                                activity_type,
                                activity_date,
                                activity_time,
                                subject,
                                notes,
                                outcome,
                                next_action,
                                next_action_date,
                                next_action_time,
                                task_status,
                                assigned_to
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                                fy,
                                quarter,
                                campaign_name,
                                sales_play,
                                campaign_start.isoformat(),
                                campaign_end.isoformat(),
                                times_per_week,
                                total_tasks,
                                account_id,
                                contact["id"],
                                step["activity_type"],
                                action_date.isoformat(),
                                step["time"],
                                subject,
                                notes,
                                "No Response",
                                "",
                                action_date.isoformat(),
                                step["time"],
                                "Not Started",
                                assigned_to
                        ))
                        generated_count += 1

                add_timeline_entry(
                    connection,
                    "account",
                    account_id,
                    "Campaign Built",
                    f"Generated {generated_count} campaign outreach step(s) for sales play {sales_play} from {campaign_start.isoformat()} to {campaign_end.isoformat()} with {total_tasks} task(s) at {times_per_week} time(s) per week. {success_context_summary}"
                )
                connection.commit()

    accounts = connection.execute("""
        SELECT
            accounts.*,
            COUNT(contacts.id) AS contact_count
        FROM accounts
        LEFT JOIN contacts ON contacts.account_id = accounts.id
        GROUP BY accounts.id
        HAVING COUNT(contacts.id) > 0
        ORDER BY accounts.account_name
    """).fetchall()

    contacts = connection.execute("""
        SELECT contacts.*, accounts.account_name
        FROM contacts
        LEFT JOIN accounts ON contacts.account_id = accounts.id
        WHERE COALESCE(contacts.status, 'Active') = 'Active'
        ORDER BY
            CASE WHEN accounts.pg_bible_order IS NULL THEN 1 ELSE 0 END,
            accounts.pg_bible_order,
            accounts.account_name,
            contacts.name
    """).fetchall()
    sales_play_rows = account_sales_play_options(connection)
    partner_activity_options = account_partner_activity_options(connection)

    connection.close()

    return render_template(
        "campaign_builder.html",
        accounts=accounts,
        contacts=contacts,
        profile=profile,
        default_assignee=default_outreach_assignee(),
        generated_count=generated_count,
        selected_account_id=selected_account_id,
        selected_contact_ids=selected_contact_ids,
        selected_pg_week_start=selected_pg_week_start,
        selected_campaign_start=selected_campaign_start,
        selected_campaign_end=selected_campaign_end,
        selected_total_tasks=selected_total_tasks,
        selected_times_per_week=selected_times_per_week,
        selected_sales_play=selected_sales_play,
        sales_play_options=sales_play_rows,
        selected_fy=selected_fy,
        selected_quarter=selected_quarter,
        success_context_summary=success_context_summary,
        error=error
    )


@app.route("/outreach/<int:outreach_id>")
def view_outreach(outreach_id):
    connection = get_db_connection()

    outreach_item = connection.execute("""
        SELECT
            outreach.*,
            accounts.account_name,
            accounts.account_tier,
            COALESCE(contacts.name, partner_contacts.name) AS contact_name,
            COALESCE(contacts.job_title, partner_contacts.job_title) AS contact_job_title,
            CASE WHEN outreach.partner_contact_id IS NOT NULL THEN 'Partner' ELSE 'Customer' END AS contact_source,
            partners.partner_name AS partner_name
        FROM outreach
        LEFT JOIN accounts ON outreach.account_id = accounts.id
        LEFT JOIN contacts ON outreach.contact_id = contacts.id
        LEFT JOIN partner_contacts ON outreach.partner_contact_id = partner_contacts.id
        LEFT JOIN partners ON partner_contacts.partner_id = partners.id
        WHERE outreach.id = ?
    """, (outreach_id,)).fetchone()

    timeline_entries = connection.execute("""
        SELECT *
        FROM timeline_entries
        WHERE related_type = 'outreach'
          AND related_id = ?
        ORDER BY date_created DESC
    """, (outreach_id,)).fetchall()

    outreach_recipients = connection.execute("""
        SELECT
            outreach_recipients.contact_id,
            outreach_recipients.partner_contact_id,
            COALESCE(contacts.name, partner_contacts.name) AS contact_name,
            COALESCE(contacts.job_title, partner_contacts.job_title) AS contact_job_title,
            CASE WHEN outreach_recipients.partner_contact_id IS NOT NULL THEN 'Partner' ELSE 'Customer' END AS contact_source,
            partners.partner_name AS partner_name
        FROM outreach_recipients
        LEFT JOIN contacts ON outreach_recipients.contact_id = contacts.id
        LEFT JOIN partner_contacts ON outreach_recipients.partner_contact_id = partner_contacts.id
        LEFT JOIN partners ON partner_contacts.partner_id = partners.id
        WHERE outreach_recipients.outreach_id = ?
        ORDER BY outreach_recipients.sort_order, outreach_recipients.id
    """, (outreach_id,)).fetchall()

    connection.close()

    return render_template(
        "view_outreach.html",
        outreach_item=outreach_item,
        outreach_recipients=outreach_recipients,
        timeline_entries=timeline_entries
    )


@app.route("/outreach/<int:outreach_id>/timeline/add", methods=("POST",))
def add_outreach_timeline(outreach_id):
    connection = get_db_connection()
    add_timeline_entry(
        connection,
        "outreach",
        outreach_id,
        request.form.get("entry_type"),
        request.form.get("entry_text"),
        request.form.get("created_by") or "Melissa"
    )
    connection.commit()
    connection.close()

    return redirect(url_for("view_outreach", outreach_id=outreach_id))


@app.route("/outreach/<int:outreach_id>/delete", methods=("POST",))
def delete_outreach(outreach_id):
    initialise_database(force=True)
    connection = get_db_connection()
    deleted_count = delete_outreach_records(connection, [outreach_id])
    connection.commit()
    connection.close()

    if deleted_count:
        return redirect(url_for("outreach", message="Deleted 1 outreach record."))
    return redirect(url_for("outreach", error="The selected outreach task could not be found."))


@app.route("/outreach/bulk-delete", methods=("POST",))
def bulk_delete_outreach():
    return_to = safe_redirect_target(request.form.get("return_to") or request.referrer or url_for("outreach"), "outreach")
    outreach_ids = selected_record_ids()
    deleted_count = 0
    if outreach_ids:
        initialise_database(force=True)
        connection = get_db_connection()
        try:
            deleted_count = delete_outreach_records(connection, outreach_ids)
            connection.commit()
        except Exception:
            connection.rollback()
            traceback.print_exc()
            connection.close()
            return redirect_with_query(return_to, error="Selected outreach records could not be deleted. Refresh the table and try again.")
        connection.close()
    if deleted_count:
        return redirect_with_query(return_to, message=f"Deleted {deleted_count} outreach record(s).")
    return redirect_with_query(return_to, error="No selected outreach records could be deleted.")


@app.route("/outreach/bulk-action", methods=("POST",))
def bulk_outreach_action():
    action = request.form.get("bulk_action")
    return_to = safe_redirect_target(request.form.get("return_to") or request.referrer or url_for("outreach"), "outreach")
    outreach_ids = selected_record_ids()
    if not outreach_ids:
        return redirect_with_query(return_to, error="Select at least one outreach task before applying a bulk action.")
    if action == "delete":
        initialise_database(force=True)
        connection = get_db_connection()
        try:
            deleted_count = delete_outreach_records(connection, outreach_ids)
            connection.commit()
        except Exception:
            connection.rollback()
            traceback.print_exc()
            connection.close()
            return redirect_with_query(return_to, error="Selected outreach records could not be deleted. Refresh the table and try again.")
        connection.close()
        if deleted_count:
            return redirect_with_query(return_to, message=f"Deleted {deleted_count} outreach record(s).")
        return redirect_with_query(return_to, error="No selected outreach records could be deleted.")
    if action == "update_due":
        next_action_date = request.form.get("bulk_next_action_date", "")
        next_action_time = request.form.get("bulk_next_action_time", "")
        connection = get_db_connection()
        try:
            updated_count = update_outreach_due_date_records(
                connection,
                outreach_ids,
                next_action_date,
                next_action_time,
                "Bulk due date update from Outreach table",
            )
            connection.commit()
        except Exception:
            connection.rollback()
            traceback.print_exc()
            connection.close()
            return redirect_with_query(return_to, error="Selected outreach due dates could not be updated. Refresh the table and try again.")
        connection.close()
        if updated_count:
            return redirect_with_query(return_to, message=f"Updated the due date for {updated_count} outreach task(s).")
        return redirect_with_query(return_to, error="No selected open outreach tasks could be updated.")
    return redirect_with_query(return_to, error="Select a valid bulk action.")


def update_outreach_due_date_records(connection, outreach_ids, next_action_date, next_action_time, actor_label):
    updated_count = 0
    labels = {
        "next_action_date": "Activity due date",
        "next_action_time": "Activity due time",
    }
    for outreach_id in outreach_ids:
        outreach_item = connection.execute(
            "SELECT * FROM outreach WHERE id = ?",
            (outreach_id,),
        ).fetchone()
        if not outreach_item or not task_can_be_modified(outreach_item):
            continue
        new_values = {
            "next_action_date": next_action_date,
            "next_action_time": next_action_time,
        }
        changes = build_change_log(outreach_item, new_values, labels)
        connection.execute(
            """
            UPDATE outreach
            SET next_action_date = ?,
                next_action_time = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (next_action_date, next_action_time, outreach_id),
        )
        if changes:
            audit_record_update(connection, "outreach", outreach_id, outreach_item, new_values, labels)
            add_timeline_entry(
                connection,
                "outreach",
                outreach_id,
                "Task Updated",
                f"{actor_label}: " + "; ".join(changes),
            )
        updated_count += 1
    return updated_count


@app.route("/outreach/<int:outreach_id>/due-date", methods=("POST",))
def update_outreach_due_date(outreach_id):
    return_to = safe_redirect_target(request.form.get("return_to") or request.referrer or url_for("outreach"), "outreach")
    next_action_date = request.form.get("next_action_date", "")
    next_action_time = request.form.get("next_action_time", "")
    connection = get_db_connection()
    try:
        updated_count = update_outreach_due_date_records(
            connection,
            [outreach_id],
            next_action_date,
            next_action_time,
            "Due date updated from Outreach table",
        )
        connection.commit()
    except Exception:
        connection.rollback()
        traceback.print_exc()
        connection.close()
        return redirect_with_query(return_to, error="Activity due date could not be updated. Refresh the table and try again.")
    connection.close()
    if updated_count:
        return redirect_with_query(return_to, message="Activity due date updated.")
    return redirect_with_query(return_to, error="This outreach task is locked and cannot have its due date changed.")


@app.route("/outreach/bulk-due-date", methods=("POST",))
def bulk_update_outreach_due_date():
    return_to = safe_redirect_target(request.form.get("return_to") or request.referrer or url_for("outreach"), "outreach")
    outreach_ids = selected_record_ids()
    if not outreach_ids:
        return redirect_with_query(return_to, error="Select at least one outreach task before applying a bulk due date update.")
    next_action_date = request.form.get("bulk_next_action_date", "")
    next_action_time = request.form.get("bulk_next_action_time", "")
    connection = get_db_connection()
    try:
        updated_count = update_outreach_due_date_records(
            connection,
            outreach_ids,
            next_action_date,
            next_action_time,
            "Bulk due date update from Outreach table",
        )
        connection.commit()
    except Exception:
        connection.rollback()
        traceback.print_exc()
        connection.close()
        return redirect_with_query(return_to, error="Selected outreach due dates could not be updated. Refresh the table and try again.")
    connection.close()
    if updated_count:
        return redirect_with_query(return_to, message=f"Updated the due date for {updated_count} outreach task(s).")
    return redirect_with_query(return_to, error="No selected open outreach tasks could be updated.")


@app.route("/outreach/<int:outreach_id>/edit", methods=("GET", "POST"))
def edit_outreach(outreach_id):
    connection = get_db_connection()
    error = ""

    outreach_item = connection.execute(
        "SELECT * FROM outreach WHERE id = ?",
        (outreach_id,)
    ).fetchone()
    if not outreach_item:
        connection.close()
        return redirect(url_for("outreach", error="The selected outreach task could not be found."))
    task_locked_value = not task_can_be_modified(outreach_item)
    task_lock_message_value = task_lock_message(outreach_item) if task_locked_value else ""

    accounts = connection.execute(
        "SELECT * FROM accounts ORDER BY account_name"
    ).fetchall()

    selected_account_for_contacts = request.form.get("account_id") if request.method == "POST" else (request.args.get("account_id") or outreach_item["account_id"])
    contacts = connection.execute("""
        SELECT contacts.*, accounts.account_name
        FROM contacts
        LEFT JOIN accounts ON contacts.account_id = accounts.id
        WHERE contacts.account_id = ?
          AND (
                COALESCE(contacts.status, 'Active') = 'Active'
             OR contacts.id = ?
          )
        ORDER BY contacts.name
    """, (selected_account_for_contacts, outreach_item["contact_id"])).fetchall() if selected_account_for_contacts else []
    sales_play_rows = account_sales_play_options(connection)
    partner_activity_options = account_partner_activity_options(connection)
    partner_contacts = partner_contacts_for_outreach(connection, selected_account_for_contacts)

    profile = connection.execute("""
        SELECT *
        FROM user_profile
        WHERE id = 1
    """).fetchone()
    non_working_block_rows = connection.execute("""
        SELECT *
        FROM non_working_blocks
        ORDER BY start_date, end_date, id
    """).fetchall()
    if request.method == "POST":
        if not task_can_be_modified(outreach_item):
            connection.close()
            return redirect(url_for("outreach", error=task_lock_message(outreach_item)))
        submit_action = request.form.get("submit_action", "save")
        sales_play_value = request.form.get("sales_play")
        outcome_value = normalise_outreach_outcome(request.form.get("outcome"))
        scheduled_meeting_date, scheduled_meeting_time = split_scheduled_meeting_datetime(
            request.form.get("scheduled_meeting_at") if outcome_requires_scheduled_meeting(outcome_value) else ""
        )
        recipient_values = outreach_contact_form_values(request.form)
        recipients = parse_outreach_contact_selections(recipient_values)
        contact_id, partner_contact_id = recipients[0] if recipients else (None, None)
        assigned_to = request.form.get("assigned_to") or outreach_item["assigned_to"] or default_outreach_assignee()
        new_values = {
            "fy": request.form.get("fy"),
            "quarter": request.form.get("quarter"),
            "campaign": sales_play_value,
            "sales_play": sales_play_value,
            "account_id": request.form.get("account_id"),
            "contact_id": contact_id,
            "partner_contact_id": partner_contact_id,
            "activity_type": request.form.get("activity_type"),
            "activity_date": request.form.get("activity_date"),
            "activity_time": request.form.get("activity_time"),
            "subject": request.form.get("subject"),
            "notes": outreach_item["notes"] or "",
            "outcome": outcome_value,
            "scheduled_meeting_date": scheduled_meeting_date,
            "scheduled_meeting_time": scheduled_meeting_time,
            "next_action": request.form.get("next_action"),
            "next_action_date": request.form.get("next_action_date"),
            "next_action_time": request.form.get("next_action_time"),
            "task_status": normalise_task_status(request.form.get("task_status", "Not Started")),
            "assigned_to": assigned_to
        }
        follow_on_requested = submit_action == "complete_and_follow"

        if submit_action in ("complete_and_follow", "complete_only"):
            new_values["task_status"] = "Completed"
            new_values["next_action_date"] = ""
            new_values["next_action_time"] = ""
        new_values["completed_at"] = completed_status_timestamp(outreach_item, new_values["task_status"])

        if not fy_quarter_are_valid(new_values["fy"], new_values["quarter"]):
            error = fy_quarter_required_message()
            connection.close()
            return render_template(
                "edit_outreach.html",
                outreach_item=outreach_item,
                accounts=accounts,
                contacts=contacts,
                profile=profile,
                non_working_blocks=non_working_block_rows,
                sales_play_options=sales_play_rows,
                partner_activity_options=partner_activity_options,
                partner_contacts=partner_contacts,
                selected_contact_values=recipient_values,
                selected_account_id=new_values["account_id"],
                scheduled_meeting_at=request.form.get("scheduled_meeting_at", ""),
                error=error,
                task_locked=task_locked_value,
                task_lock_message=task_lock_message_value
            )

        if not outreach_recipients_match_account(connection, new_values["account_id"], recipients):
            error = "Select a contact or partner contact that belongs to the selected account."
            connection.close()
            return render_template(
                "edit_outreach.html",
                outreach_item=outreach_item,
                accounts=accounts,
                contacts=contacts,
                profile=profile,
                non_working_blocks=non_working_block_rows,
                sales_play_options=sales_play_rows,
                partner_activity_options=partner_activity_options,
                partner_contacts=partner_contacts,
                selected_contact_values=recipient_values,
                selected_account_id=new_values["account_id"],
                scheduled_meeting_at=request.form.get("scheduled_meeting_at", ""),
                error=error,
                task_locked=task_locked_value,
                task_lock_message=task_lock_message_value
            )

        if status_requires_activity_update(new_values["task_status"]) and not activity_update_is_valid(new_values["next_action"]):
            error = activity_update_required_message()
            connection.close()
            return render_template(
                "edit_outreach.html",
                outreach_item=outreach_item,
                accounts=accounts,
                contacts=contacts,
                profile=profile,
                non_working_blocks=non_working_block_rows,
                sales_play_options=sales_play_rows,
                partner_activity_options=partner_activity_options,
                partner_contacts=partner_contacts,
                selected_contact_values=recipient_values,
                selected_account_id=new_values["account_id"],
                scheduled_meeting_at=request.form.get("scheduled_meeting_at", ""),
                error=error,
                task_locked=task_locked_value,
                task_lock_message=task_lock_message_value
            )

        labels = {
            "fy": "FY",
            "quarter": "Quarter",
            "campaign": "Sales play or initiative campaign grouping",
            "sales_play": "Sales play or initiative",
            "account_id": "Account",
            "contact_id": "Contact",
            "partner_contact_id": "Partner contact",
            "activity_type": "Activity type",
            "activity_date": "Activity start date",
            "activity_time": "Activity start time",
            "subject": "Subject",
            "notes": "System metadata",
            "outcome": "Outcome",
            "scheduled_meeting_date": "Scheduled meeting date",
            "scheduled_meeting_time": "Scheduled meeting time",
            "next_action": "Activity update",
            "next_action_date": "Activity due date",
            "next_action_time": "Activity due time",
            "task_status": "Task status",
            "completed_at": "Completed at",
            "assigned_to": "Assigned to"
        }

        changes = build_change_log(outreach_item, new_values, labels)

        connection.execute("""
            UPDATE outreach
            SET fy = ?,
                quarter = ?,
                campaign = ?,
                sales_play = ?,
                account_id = ?,
                contact_id = ?,
                partner_contact_id = ?,
                activity_type = ?,
                activity_date = ?,
                activity_time = ?,
                subject = ?,
                notes = ?,
                outcome = ?,
                scheduled_meeting_date = ?,
                scheduled_meeting_time = ?,
                next_action = ?,
                next_action_date = ?,
                next_action_time = ?,
                task_status = ?,
                completed_at = ?,
                assigned_to = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            new_values["fy"],
            new_values["quarter"],
            new_values["campaign"],
            new_values["sales_play"],
            new_values["account_id"],
            new_values["contact_id"],
            new_values["partner_contact_id"],
            new_values["activity_type"],
            new_values["activity_date"],
            new_values["activity_time"],
            new_values["subject"],
            new_values["notes"],
            new_values["outcome"],
            new_values["scheduled_meeting_date"],
            new_values["scheduled_meeting_time"],
            new_values["next_action"],
            new_values["next_action_date"],
            new_values["next_action_time"],
            new_values["task_status"],
            new_values["completed_at"],
            new_values["assigned_to"],
            outreach_id
        ))
        save_outreach_recipients(connection, outreach_id, recipients)

        if changes:
            audit_record_update(connection, "outreach", outreach_id, outreach_item, new_values, labels)
            add_timeline_entry(
                connection,
                "outreach",
                outreach_id,
                "Auto Audit",
                "Outreach updated: " + "; ".join(changes)
            )

        connection.commit()
        connection.close()

        if follow_on_requested:
            return redirect(url_for("add_outreach", prefill_from=outreach_id))

        return redirect(url_for("outreach"))

    selected_contact_values = selected_outreach_contact_values(connection, outreach_item)
    selected_account_id = selected_account_for_contacts
    scheduled_meeting_at = scheduled_meeting_datetime_value(
        outreach_item["scheduled_meeting_date"] if "scheduled_meeting_date" in outreach_item.keys() else "",
        outreach_item["scheduled_meeting_time"] if "scheduled_meeting_time" in outreach_item.keys() else "",
    )
    connection.close()

    return render_template(
        "edit_outreach.html",
        outreach_item=outreach_item,
        accounts=accounts,
        contacts=contacts,
        profile=profile,
        non_working_blocks=non_working_block_rows,
        sales_play_options=sales_play_rows,
        partner_activity_options=partner_activity_options,
        partner_contacts=partner_contacts,
        selected_contact_values=selected_contact_values,
        selected_account_id=selected_account_id,
        scheduled_meeting_at=scheduled_meeting_at,
        error=error,
        task_locked=task_locked_value,
        task_lock_message=task_lock_message_value
    )


@app.route("/search")
def global_search():
    query = request.args.get("q", "").strip()

    account_results = []
    contact_results = []
    partner_results = []
    partner_contact_results = []
    outreach_results = []
    timeline_results = []

    if query:
        search_term = f"%{query}%"
        connection = get_db_connection()

        account_results = connection.execute("""
            SELECT *
            FROM accounts
            WHERE account_name LIKE ?
               OR industry LIKE ?
               OR country LIKE ?
               OR city LIKE ?
               OR website LIKE ?
               OR notes LIKE ?
            ORDER BY account_name
        """, (
            search_term, search_term, search_term,
            search_term, search_term, search_term
        )).fetchall()

        contact_results = connection.execute("""
            SELECT contacts.*, accounts.account_name
            FROM contacts
            LEFT JOIN accounts ON contacts.account_id = accounts.id
            WHERE contacts.name LIKE ?
               OR contacts.job_title LIKE ?
               OR contacts.org_dept LIKE ?
               OR contacts.email LIKE ?
               OR contacts.phone LIKE ?
               OR contacts.location LIKE ?
               OR contacts.linkedin LIKE ?
               OR contacts.bmc_relationship LIKE ?
               OR contacts.responsibilities LIKE ?
               OR contacts.characteristics LIKE ?
               OR contacts.background LIKE ?
               OR contacts.personal_interests LIKE ?
               OR contacts.personal_win LIKE ?
               OR contacts.education LIKE ?
               OR contacts.social_media LIKE ?
               OR contacts.additional_notes LIKE ?
               OR accounts.account_name LIKE ?
            ORDER BY contacts.name
        """, (
            search_term, search_term, search_term, search_term,
            search_term, search_term, search_term, search_term,
            search_term, search_term, search_term, search_term,
            search_term, search_term, search_term, search_term,
            search_term
        )).fetchall()

        partner_results = connection.execute("""
            SELECT *
            FROM partners
            WHERE partner_name LIKE ?
               OR partner_type LIKE ?
               OR website LIKE ?
               OR country LIKE ?
               OR city LIKE ?
               OR partner_manager LIKE ?
               OR bmc_partner_manager LIKE ?
               OR relationship_owner LIKE ?
               OR notes LIKE ?
            ORDER BY partner_name
        """, (
            search_term, search_term, search_term, search_term,
            search_term, search_term, search_term, search_term, search_term
        )).fetchall()

        partner_contact_results = connection.execute("""
            SELECT partner_contacts.*, partners.partner_name, accounts.account_name
            FROM partner_contacts
            LEFT JOIN partners ON partner_contacts.partner_id = partners.id
            LEFT JOIN accounts ON partner_contacts.account_id = accounts.id
            WHERE partner_contacts.name LIKE ?
               OR partner_contacts.job_title LIKE ?
               OR partner_contacts.partner_contact_role LIKE ?
               OR partner_contacts.coverage_area LIKE ?
               OR accounts.account_name LIKE ?
               OR partner_contacts.relationship_owner LIKE ?
               OR partner_contacts.email LIKE ?
               OR partner_contacts.phone LIKE ?
               OR partner_contacts.location LIKE ?
               OR partner_contacts.linkedin LIKE ?
               OR partner_contacts.relationship_status LIKE ?
               OR partner_contacts.next_action LIKE ?
               OR partner_contacts.notes LIKE ?
               OR partners.partner_name LIKE ?
            ORDER BY partner_contacts.name
        """, (
            search_term, search_term, search_term, search_term,
            search_term, search_term, search_term, search_term,
            search_term, search_term, search_term, search_term,
            search_term, search_term
        )).fetchall()

        outreach_results = connection.execute("""
            SELECT outreach.*, accounts.account_name, contacts.name AS contact_name
            FROM outreach
            LEFT JOIN accounts ON outreach.account_id = accounts.id
            LEFT JOIN contacts ON outreach.contact_id = contacts.id
            WHERE outreach.subject LIKE ?
               OR outreach.notes LIKE ?
               OR outreach.outcome LIKE ?
               OR outreach.sales_play LIKE ?
               OR outreach.next_action LIKE ?
               OR outreach.activity_type LIKE ?
               OR accounts.account_name LIKE ?
               OR contacts.name LIKE ?
            ORDER BY outreach.activity_date DESC, outreach.activity_time DESC
        """, (
            search_term, search_term, search_term, search_term,
            search_term, search_term, search_term, search_term
        )).fetchall()

        timeline_results = connection.execute("""
            SELECT *
            FROM timeline_entries
            WHERE entry_type LIKE ?
               OR entry_text LIKE ?
               OR created_by LIKE ?
            ORDER BY date_created DESC
        """, (
            search_term, search_term, search_term
        )).fetchall()

        connection.close()

    return render_template(
        "search.html",
        query=query,
        account_results=account_results,
        contact_results=contact_results,
        partner_results=partner_results,
        partner_contact_results=partner_contact_results,
        outreach_results=outreach_results,
        timeline_results=timeline_results
    )


@app.route("/tasks")
def tasks():
    return redirect(url_for("home", _anchor="dashboard-tasks"))


def row_to_insert_values(row, columns):
    return [row[column] if column in row.keys() else None for column in columns]


def insert_copied_row(connection, table_name, columns, row, overrides=None):
    values = dict(zip(columns, row_to_insert_values(row, columns)))
    values.update(overrides or {})
    placeholders = ", ".join("?" for _ in columns)
    column_sql = ", ".join(columns)
    cursor = connection.execute(
        f"INSERT INTO {table_name} ({column_sql}) VALUES ({placeholders})",
        [values[column] for column in columns],
    )
    return cursor.lastrowid


def assignable_user_by_id(user_id):
    if not user_id:
        return None
    for assignable_user in list_assignable_users():
        if str(assignable_user["id"]) == str(user_id):
            return assignable_user
    return None


def current_user_owner_payload():
    user = current_user()
    if not user:
        return {
            "owner_user_id": None,
            "owner_name": "",
            "owner_email": "",
        }
    return {
        "owner_user_id": user["id"],
        "owner_name": user["full_name"],
        "owner_email": user["email"],
    }


def account_owner_payload(account):
    fallback = current_user_owner_payload()
    if not account:
        return fallback
    return {
        "owner_user_id": account["owner_user_id"] if "owner_user_id" in account.keys() and account["owner_user_id"] else fallback["owner_user_id"],
        "owner_name": account["owner_name"] if "owner_name" in account.keys() and account["owner_name"] else fallback["owner_name"],
        "owner_email": account["owner_email"] if "owner_email" in account.keys() and account["owner_email"] else fallback["owner_email"],
    }


def current_user_owns_account(account):
    user = current_user()
    if not user or not account:
        return False
    owner = account_owner_payload(account)
    return not owner["owner_user_id"] or str(owner["owner_user_id"]) == str(user["id"])


def upsert_account_share(connection, account_id, target_member):
    existing = connection.execute("""
        SELECT id
        FROM account_shared_users
        WHERE account_id = ?
          AND user_id = ?
    """, (account_id, target_member["id"])).fetchone()
    if existing:
        connection.execute("""
            UPDATE account_shared_users
            SET full_name = ?,
                email = ?,
                workspace_schema = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            target_member["full_name"],
            target_member["email"],
            target_member["workspace_schema"],
            existing["id"],
        ))
        return existing["id"]
    cursor = connection.execute("""
        INSERT INTO account_shared_users (
            account_id,
            user_id,
            full_name,
            email,
            workspace_schema
        )
        VALUES (?, ?, ?, ?, ?)
    """, (
        account_id,
        target_member["id"],
        target_member["full_name"],
        target_member["email"],
        target_member["workspace_schema"],
    ))
    return cursor.lastrowid


def account_access_user_ids(connection, account):
    owner = account_owner_payload(account)
    allowed_user_ids = set()
    if owner["owner_user_id"]:
        allowed_user_ids.add(str(owner["owner_user_id"]))
    rows = connection.execute("""
        SELECT user_id
        FROM account_shared_users
        WHERE account_id = ?
    """, (account["id"],)).fetchall()
    allowed_user_ids.update(str(row["user_id"]) for row in rows if row["user_id"])
    current = current_user()
    if current:
        allowed_user_ids.add(str(current["id"]))
    return allowed_user_ids


def assignee_has_account_access(connection, account, assigned_to_user_id):
    if not assigned_to_user_id:
        return True
    return str(assigned_to_user_id) in account_access_user_ids(connection, account)


def share_full_account_to_member(source_schema, account_id, target_member, actor_name):
    restore_schema = session.get("workspace_schema")
    try:
        session["workspace_schema"] = target_member["workspace_schema"]
        initialise_database(force=True)
    finally:
        if restore_schema:
            session["workspace_schema"] = restore_schema
        else:
            session.pop("workspace_schema", None)

    source_connection = get_schema_connection(schema=source_schema) if using_postgres() else get_db_connection()
    target_connection = get_schema_connection(schema=target_member["workspace_schema"]) if using_postgres() else get_db_connection()

    account = source_connection.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if not account:
        source_connection.close()
        target_connection.close()
        return "The selected account could not be found."

    existing_account = target_connection.execute(
        "SELECT id FROM accounts WHERE account_name = ?",
        (account["account_name"],),
    ).fetchone()
    if existing_account:
        target_account_id = existing_account["id"]
        target_connection.execute("DELETE FROM partner_contacts WHERE account_id = ?", (target_account_id,))
        target_connection.execute("DELETE FROM account_partners WHERE account_id = ?", (target_account_id,))
        target_connection.execute("DELETE FROM account_custom_values WHERE account_id = ?", (target_account_id,))
        target_connection.execute("DELETE FROM outreach WHERE account_id = ?", (target_account_id,))
        target_connection.execute("DELETE FROM contacts WHERE account_id = ?", (target_account_id,))
        target_connection.execute("""
            UPDATE accounts
            SET pg_bible_order = ?,
                account_tier = ?,
                industry = ?,
                business_unit = ?,
                country = ?,
                city = ?,
                website = ?,
                customer_logo = ?,
                pipeline_target = ?,
                owner_user_id = ?,
                owner_name = ?,
                owner_email = ?,
                notes = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            account["pg_bible_order"],
            account["account_tier"],
            account["industry"],
            account["business_unit"],
            account["country"],
            account["city"],
            account["website"],
            account["customer_logo"] if "customer_logo" in account.keys() else "",
            account["pipeline_target"],
            account["owner_user_id"] if "owner_user_id" in account.keys() else None,
            account["owner_name"] if "owner_name" in account.keys() else actor_name,
            account["owner_email"] if "owner_email" in account.keys() else "",
            account["notes"],
            target_account_id,
        ))
    else:
        target_account_id = insert_copied_row(
            target_connection,
            "accounts",
            ["account_name", "pg_bible_order", "account_tier", "industry", "business_unit", "country", "city", "website", "customer_logo", "pipeline_target", "owner_user_id", "owner_name", "owner_email", "notes"],
            account,
        )

    contact_id_map = {}
    contacts = source_connection.execute("SELECT * FROM contacts WHERE account_id = ? ORDER BY id", (account_id,)).fetchall()
    for contact in contacts:
        new_contact_id = insert_copied_row(
            target_connection,
            "contacts",
            [
                "account_id", "category", "photo", "name", "job_title", "org_dept", "responsibilities",
                "email", "phone", "location", "linkedin", "bmc_relationship", "characteristics",
                "background", "personal_interests", "personal_win", "education", "social_media",
                "additional_notes"
            ],
            contact,
            {"account_id": target_account_id},
        )
        contact_id_map[contact["id"]] = new_contact_id

    for outreach_item in source_connection.execute("SELECT * FROM outreach WHERE account_id = ? ORDER BY id", (account_id,)).fetchall():
        insert_copied_row(
            target_connection,
            "outreach",
            [
                "fy", "quarter", "account_id", "contact_id", "campaign", "sales_play",
                "campaign_start_date", "campaign_end_date", "campaign_tasks_per_week",
                "campaign_total_tasks", "activity_date", "activity_time", "activity_type",
                "subject", "notes", "outcome", "next_action", "next_action_date",
                "next_action_time", "task_status", "assigned_to"
            ],
            outreach_item,
            {
                "account_id": target_account_id,
                "contact_id": contact_id_map.get(outreach_item["contact_id"]),
            },
        )

    for custom_value in source_connection.execute("SELECT * FROM account_custom_values WHERE account_id = ? ORDER BY id", (account_id,)).fetchall():
        insert_copied_row(
            target_connection,
            "account_custom_values",
            ["account_id", "field_key", "field_value"],
            custom_value,
            {"account_id": target_account_id},
        )

    for partner in source_connection.execute("SELECT * FROM account_partners WHERE account_id = ? ORDER BY id", (account_id,)).fetchall():
        insert_copied_row(
            target_connection,
            "account_partners",
            ["account_id", "partner_id", "partner_name", "partner_role", "involvement_status", "relationship_owner", "next_action", "notes"],
            partner,
            {"account_id": target_account_id},
        )

    for partner_contact in source_connection.execute("SELECT * FROM partner_contacts WHERE account_id = ? ORDER BY id", (account_id,)).fetchall():
        insert_copied_row(
            target_connection,
            "partner_contacts",
            [
                "partner_id", "name", "job_title", "partner_contact_role", "coverage_area",
                "account_id", "relationship_owner", "email", "phone", "location", "linkedin",
                "relationship_status", "next_action", "notes"
            ],
            partner_contact,
            {"account_id": target_account_id},
        )

    add_timeline_entry(
        target_connection,
        "account",
        target_account_id,
        "Account Shared",
        f"Full account shared by {actor_name or 'team member'}."
    )
    target_connection.commit()
    source_connection.close()
    target_connection.close()
    return ""


@app.route("/team", methods=("GET", "POST"))
def team_page():
    user = current_user()
    error = ""
    invite_created = False
    if request.method == "POST":
        error = create_team_invite(
            user,
            request.form.get("invite_email", ""),
            request.form.get("invite_role", "member"),
        )
        invite_created = not error
    return render_template(
        "team.html",
        team=active_team_for_user(user),
        members=list_active_team_members(user),
        invites=list_active_team_invites(user),
        error=error,
        invite_created=invite_created,
    )


@app.route("/team-outreach")
def team_outreach():
    return redirect(url_for("outreach"))


def legacy_team_outreach_context():
    user = current_user()
    team = active_team_for_user(user)
    members = list_active_team_members(user)
    assignable_users = list_assignable_users()
    member_schemas = {member["workspace_schema"]: member for member in members if member["workspace_schema"]}
    rows = []
    current_accounts = []

    if using_postgres():
        for member in members:
            schema = member["workspace_schema"]
            if not schema:
                continue
            try:
                connection = get_schema_connection(schema=schema)
                member_rows = connection.execute("""
                    SELECT
                        outreach.*,
                        accounts.account_name,
                        contacts.name AS contact_name
                    FROM outreach
                    LEFT JOIN accounts ON outreach.account_id = accounts.id
                    LEFT JOIN contacts ON outreach.contact_id = contacts.id
                    WHERE outreach.next_action_date IS NOT NULL
                      AND outreach.next_action_date != ''
                      AND COALESCE(outreach.task_status, '') NOT IN ('Closed', 'Completed', 'Cancelled')
                    ORDER BY
                        outreach.next_action_date ASC,
                        outreach.next_action_time ASC,
                        outreach.id DESC
                """).fetchall()
                for row in member_rows:
                    row_dict = dict(row)
                    row_dict["workspace_schema"] = schema
                    row_dict["owner_name"] = member["full_name"]
                    rows.append(row_dict)
                connection.close()
            except Exception:
                continue
    else:
        connection = get_db_connection()
        member_rows = connection.execute("""
            SELECT outreach.*, accounts.account_name, contacts.name AS contact_name
            FROM outreach
            LEFT JOIN accounts ON outreach.account_id = accounts.id
            LEFT JOIN contacts ON outreach.contact_id = contacts.id
            WHERE outreach.next_action_date IS NOT NULL
              AND outreach.next_action_date != ''
              AND COALESCE(outreach.task_status, '') NOT IN ('Closed', 'Completed', 'Cancelled')
            ORDER BY outreach.next_action_date ASC, outreach.next_action_time ASC
        """).fetchall()
        for row in member_rows:
            row_dict = dict(row)
            row_dict["workspace_schema"] = current_user_schema()
            row_dict["owner_name"] = user["full_name"] if user else ""
            rows.append(row_dict)
        connection.close()

    own_connection = get_db_connection()
    current_accounts = own_connection.execute("""
        SELECT id, account_name
        FROM accounts
        ORDER BY account_name
    """).fetchall()
    own_connection.close()

    rows.sort(key=lambda row: (
        row.get("next_action_date") or "9999-12-31",
        row.get("next_action_time") or "99:99",
        row.get("account_name") or "",
        row.get("sales_play") or "",
    ))

    return {
        "team": team,
        "members": members,
        "assignable_users": assignable_users,
        "outreach_records": rows,
        "current_accounts": current_accounts,
    }


@app.route("/team-outreach/share-account", methods=("POST",))
def share_account_from_team_outreach():
    user = current_user()
    assignable_users = list_assignable_users()
    target_user_ids = request.form.getlist("target_user_ids")
    account_id = request.form.get("account_id")
    return_to = safe_redirect_target(request.form.get("return_to") or url_for("outreach"), "outreach")
    if not target_user_ids:
        return redirect_with_query(return_to, error="Select at least one user before sharing the account.")
    source_connection = get_db_connection()
    account = source_connection.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if not account or not current_user_owns_account(account):
        source_connection.close()
        return redirect_with_query(return_to, error="Only the account owner can share this account.")
    target_members = [
        member for member in assignable_users
        if str(member["id"]) in target_user_ids
           and member["workspace_schema"]
           and (not user or str(member["id"]) != str(user["id"]))
    ]
    if not target_members:
        source_connection.close()
        return redirect_with_query(return_to, error="Select at least one valid user other than yourself.")
    source_schema = current_user_schema() if using_postgres() else ""
    errors = []
    shared_count = 0
    for target_member in target_members:
        error = share_full_account_to_member(source_schema, account_id, target_member, user["full_name"] if user else "")
        if error:
            errors.append(error)
        else:
            upsert_account_share(source_connection, account_id, target_member)
            shared_count += 1
    if shared_count:
        add_timeline_entry(
            source_connection,
            "account",
            account_id,
            "Account Shared",
            f"Full account shared with {shared_count} user(s)."
        )
        source_connection.commit()
    source_connection.close()
    if errors and not shared_count:
        return redirect_with_query(return_to, error=errors[0])
    if errors:
        return redirect_with_query(return_to, message=f"Account shared with {shared_count} user(s). Some shares could not be completed.")
    return redirect_with_query(return_to, message=f"Full account shared with {shared_count} user(s).")


@app.route("/team-outreach/account-share/<int:share_id>/revoke", methods=("POST",))
def revoke_account_share_from_outreach(share_id):
    user = current_user()
    return_to = safe_redirect_target(request.form.get("return_to") or url_for("outreach"), "outreach")
    connection = get_db_connection()
    share = connection.execute("""
        SELECT account_shared_users.*, accounts.account_name, accounts.owner_user_id, accounts.owner_name, accounts.owner_email
        FROM account_shared_users
        JOIN accounts ON accounts.id = account_shared_users.account_id
        WHERE account_shared_users.id = ?
    """, (share_id,)).fetchone()
    if not share:
        connection.close()
        return redirect_with_query(return_to, error="The selected sharing permission could not be found.")

    owner = account_owner_payload(share)
    if user and owner["owner_user_id"] and str(owner["owner_user_id"]) != str(user["id"]):
        connection.close()
        return redirect_with_query(return_to, error="Only the account owner can revoke account sharing permissions.")

    connection.execute("""
        UPDATE outreach
        SET assigned_to = ?,
            last_updated = CURRENT_TIMESTAMP
        WHERE account_id = ?
          AND assigned_to = ?
    """, (
        owner["owner_name"],
        share["account_id"],
        share["full_name"],
    ))
    connection.execute("DELETE FROM account_shared_users WHERE id = ?", (share_id,))
    add_timeline_entry(
        connection,
        "account",
        share["account_id"],
        "Account Share Revoked",
        f"Access revoked for {share['full_name'] or share['email']}. Assigned tasks returned to {owner['owner_name'] or 'the account owner'}."
    )
    connection.commit()
    connection.close()
    return redirect_with_query(return_to, message="Account sharing permission revoked and assigned tasks returned to the account owner.")


@app.route("/team-outreach/reassign", methods=("POST",))
def reassign_team_outreach():
    user = current_user()
    members = list_active_team_members(user)
    assignable_users = list_assignable_users()
    allowed_schemas = {member["workspace_schema"] for member in members if member["workspace_schema"]}
    if not using_postgres():
        allowed_schemas.add("")
    allowed_user_ids = {str(member["id"]) for member in assignable_users}
    workspace_schema = request.form.get("workspace_schema")
    outreach_id = request.form.get("outreach_id")
    assigned_to_user_id = request.form.get("assigned_to_user_id", "")
    assigned_member = assignable_user_by_id(assigned_to_user_id) if assigned_to_user_id else None
    assigned_to = assigned_member["full_name"] if assigned_member else ""
    return_to = safe_redirect_target(request.form.get("return_to") or request.referrer or url_for("outreach"), "outreach")
    if not assigned_to_user_id:
        return redirect_with_query(return_to, error="Select an assignee before reassigning an outreach task.")
    if workspace_schema not in allowed_schemas or (assigned_to_user_id and assigned_to_user_id not in allowed_user_ids):
        return redirect(return_to)
    connection = get_schema_connection(schema=workspace_schema) if using_postgres() else get_db_connection()
    outreach_item = connection.execute("SELECT * FROM outreach WHERE id = ?", (outreach_id,)).fetchone()
    if outreach_item:
        if not task_can_be_modified(outreach_item):
            connection.close()
            return redirect(url_for("outreach", error=task_lock_message(outreach_item)))
        account = connection.execute("SELECT * FROM accounts WHERE id = ?", (outreach_item["account_id"],)).fetchone()
        if account and not assignee_has_account_access(connection, account, assigned_to_user_id):
            connection.close()
            return redirect(url_for(
                "outreach",
                error="The selected assignee does not have access to this account. Share the account first, then assign the task."
            ))
        connection.execute(
            """
            UPDATE outreach
            SET assigned_to = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (assigned_to, outreach_id),
        )
        audit_record_update(connection, "outreach", outreach_id, outreach_item, {
            "assigned_to": assigned_to,
        }, {
            "assigned_to": "Assigned to",
        })
        connection.commit()
    connection.close()
    return redirect(return_to)


@app.route("/tasks/<int:outreach_id>/update", methods=("POST",))
def update_task_from_tasks(outreach_id):
    connection = get_db_connection()
    outreach_item = connection.execute(
        "SELECT * FROM outreach WHERE id = ?",
        (outreach_id,),
    ).fetchone()
    return_target = safe_redirect_target(request.form.get("return_to") or request.referrer or url_for("home"), "home")
    if not outreach_item:
        connection.close()
        return redirect(return_target)
    if not task_can_be_modified(outreach_item):
        connection.close()
        return redirect(return_target)

    new_values = {
        "outcome": normalise_outreach_outcome(request.form.get("outcome")),
        "task_status": normalise_task_status(request.form.get("task_status", "Not Started")),
        "next_action": request.form.get("next_action"),
        "next_action_date": request.form.get("next_action_date"),
        "next_action_time": request.form.get("next_action_time"),
        "notes": outreach_item["notes"] or "",
    }
    new_values["completed_at"] = completed_status_timestamp(outreach_item, new_values["task_status"])
    if status_requires_activity_update(new_values["task_status"]) and not activity_update_is_valid(new_values["next_action"]):
        connection.close()
        return redirect(return_target)
    labels = {
        "outcome": "Outcome",
        "task_status": "Task status",
        "next_action": "Activity update",
        "next_action_date": "Activity due date",
        "next_action_time": "Activity due time",
        "notes": "System metadata",
        "completed_at": "Completed at",
    }
    changes = build_change_log(outreach_item, new_values, labels)

    connection.execute(
        """
        UPDATE outreach
        SET outcome = ?,
            task_status = ?,
            next_action = ?,
            next_action_date = ?,
            next_action_time = ?,
            completed_at = ?,
            last_updated = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            new_values["outcome"],
            new_values["task_status"],
            new_values["next_action"],
            new_values["next_action_date"],
            new_values["next_action_time"],
            new_values["completed_at"],
            outreach_id,
        ),
    )
    if changes:
        audit_record_update(connection, "outreach", outreach_id, outreach_item, new_values, labels)
        add_timeline_entry(
            connection,
            "outreach",
            outreach_id,
            "Task Updated",
            "Task updated from Tasks page: " + "; ".join(changes),
        )
    connection.commit()
    connection.close()
    return redirect(return_target)


@app.route("/tasks/<int:outreach_id>/complete", methods=("POST",))
def complete_task_from_tasks(outreach_id):
    connection = get_db_connection()
    outreach_item = connection.execute(
        "SELECT * FROM outreach WHERE id = ?",
        (outreach_id,),
    ).fetchone()
    return_target = safe_redirect_target(request.form.get("return_to") or request.referrer or url_for("home"), "home")
    if not outreach_item:
        connection.close()
        return redirect(return_target)

    activity_update = (request.form.get("next_action") or "").strip()
    if not activity_update:
        connection.close()
        return redirect(return_target)

    if not task_can_be_modified(outreach_item):
        connection.close()
        return redirect(return_target)

    outcome = normalise_outreach_outcome(request.form.get("outcome")) or outreach_item["outcome"] or "Follow-up Required"
    completed_at = completed_status_timestamp(outreach_item, "Completed")
    connection.execute(
        """
        UPDATE outreach
        SET task_status = 'Completed',
            outcome = ?,
            next_action = ?,
            completed_at = ?,
            last_updated = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (outcome, activity_update, completed_at, outreach_id),
    )
    audit_record_update(connection, "outreach", outreach_id, outreach_item, {
        "task_status": "Completed",
        "outcome": outcome,
        "next_action": activity_update,
        "completed_at": completed_at,
    }, {
        "task_status": "Task status",
        "outcome": "Outcome",
        "next_action": "Activity update",
        "completed_at": "Completed at",
    })
    add_timeline_entry(
        connection,
        "outreach",
        outreach_id,
        "Task Completed",
        f"Task marked Completed from dashboard with outcome: {outcome}. It can be reopened for 10 days before the system moves it to Closed.",
    )
    connection.commit()
    connection.close()
    return redirect(return_target)


@app.route("/profile", methods=("GET", "POST"))
def profile():
    connection = get_db_connection()
    message = request.args.get("message", "")
    error = request.args.get("error", "")

    if request.method == "POST":
        existing_profile = connection.execute("""
            SELECT *
            FROM user_profile
            WHERE id = 1
        """).fetchone()
        new_values = {
            "full_name": request.form.get("full_name"),
            "team": request.form.get("team"),
            "job_title": request.form.get("job_title"),
            "work_day_start": request.form.get("work_day_start") or "09:00",
            "work_day_end": request.form.get("work_day_end") or "17:00",
            "non_working_start_date": request.form.get("non_working_start_date"),
            "non_working_end_date": request.form.get("non_working_end_date"),
        }
        labels = {
            "full_name": "Full Name",
            "team": "Team",
            "job_title": "Job Title",
            "work_day_start": "Work Day Start",
            "work_day_end": "Work Day End",
            "non_working_start_date": "Legacy Non-Working Start Date",
            "non_working_end_date": "Legacy Non-Working End Date",
        }
        connection.execute("""
            UPDATE user_profile
            SET full_name = ?,
                team = ?,
                job_title = ?,
                work_day_start = ?,
                work_day_end = ?,
                non_working_start_date = ?,
                non_working_end_date = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE id = 1
        """, (
            new_values["full_name"],
            new_values["team"],
            new_values["job_title"],
            new_values["work_day_start"],
            new_values["work_day_end"],
            new_values["non_working_start_date"],
            new_values["non_working_end_date"]
        ))
        if existing_profile:
            audit_record_update(connection, "profile", 1, existing_profile, new_values, labels)

        connection.commit()
        connection.close()

        return redirect(url_for("profile", message="Profile saved."))

    profile_record = connection.execute("""
        SELECT *
        FROM user_profile
        WHERE id = 1
    """).fetchone()
    non_working_blocks = connection.execute("""
        SELECT *
        FROM non_working_blocks
        ORDER BY start_date, end_date, id
    """).fetchall()

    connection.close()
    secret_phrase = ""
    secret_phrase_available = False
    user = current_user()
    if user:
        auth_connection = get_auth_connection()
        auth_row = auth_connection.execute("""
            SELECT reset_phrase_plain
            FROM users
            WHERE id = ?
        """, (user["id"],)).fetchone()
        auth_connection.close()
        secret_phrase = auth_row["reset_phrase_plain"] if auth_row and "reset_phrase_plain" in auth_row.keys() and auth_row["reset_phrase_plain"] else ""
        secret_phrase_available = bool(secret_phrase)

    return render_template(
        "profile.html",
        profile=profile_record,
        non_working_blocks=non_working_blocks,
        secret_phrase=secret_phrase,
        secret_phrase_available=secret_phrase_available,
        message=message,
        error=error
    )


@app.route("/profile/secret-phrase", methods=("POST",))
def change_secret_phrase():
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    error = update_current_user_secret_phrase(
        user["id"],
        request.form.get("new_secret_phrase", ""),
        request.form.get("confirm_secret_phrase", ""),
    )
    if error:
        return redirect(url_for("profile", error=error))
    log_admin_audit(
        user,
        "Secret phrase changed",
        "User",
        user["email"],
        "User changed their own secret phrase from Profile."
    )
    return redirect(url_for("profile", message="Secret phrase changed."))


@app.route("/profile/non-working/add", methods=("POST",))
def add_non_working_block():
    start_date = request.form.get("start_date")
    end_date = request.form.get("end_date") or start_date
    reason = request.form.get("reason", "")
    if not start_date:
        return redirect(url_for("profile", error="Non-working start date is required."))
    connection = get_db_connection()
    cursor = connection.execute("""
        INSERT INTO non_working_blocks (start_date, end_date, reason)
        VALUES (?, ?, ?)
    """, (start_date, end_date, reason))
    audit_record_create(connection, "profile", 1, {
        "non_working_block": f"{start_date} to {end_date}",
        "non_working_reason": reason,
    }, {
        "non_working_block": "Non-Working Date Block",
        "non_working_reason": "Non-Working Reason",
    })
    connection.commit()
    connection.close()
    return redirect(url_for("profile", message="Non-working block added."))


@app.route("/profile/non-working/<int:block_id>/delete", methods=("POST",))
def delete_non_working_block(block_id):
    connection = get_db_connection()
    block = connection.execute("SELECT * FROM non_working_blocks WHERE id = ?", (block_id,)).fetchone()
    if block:
        audit_record_delete(connection, "profile", 1, f"Non-working block {block['start_date']} to {block['end_date']}")
    connection.execute("DELETE FROM non_working_blocks WHERE id = ?", (block_id,))
    connection.commit()
    connection.close()
    return redirect(url_for("profile", message="Non-working block deleted."))


@app.route("/profile/delete-data", methods=("POST",))
def delete_profile_data():
    confirmation = (request.form.get("delete_confirmation") or "").strip()

    if confirmation != "DELETE MY DATA":
        return redirect(url_for(
            "profile",
            error="Type DELETE MY DATA to confirm the workspace data deletion."
        ))

    connection = get_db_connection()
    delete_current_profile_workspace_data(connection)
    connection.commit()
    connection.close()

    return redirect(url_for(
        "profile",
        message="Your private PipeFlow workspace data has been deleted. Your login profile has been kept."
    ))


@app.route("/reports")
def reports():
    return render_template("reports.html")


@app.route("/reports/partners")
def partner_reports():
    connection = get_db_connection()
    partner_rows = connection.execute("""
        SELECT
            partners.id,
            partners.partner_name,
            partners.partner_type,
            partner_contact_accounts.relationship_status AS involvement_status,
            accounts.account_name,
            COUNT(DISTINCT partner_contacts.id) AS contact_count
        FROM partners
        LEFT JOIN partner_contact_accounts ON partner_contact_accounts.partner_id = partners.id
        LEFT JOIN accounts ON accounts.id = partner_contact_accounts.account_id
        LEFT JOIN partner_contacts ON partner_contacts.id = partner_contact_accounts.partner_contact_id
        GROUP BY partners.id, partners.partner_name, partners.partner_type, partner_contact_accounts.relationship_status, accounts.account_name
        ORDER BY partners.partner_name, accounts.account_name
    """).fetchall()
    engagement_rows = connection.execute("""
        SELECT COALESCE(NULLIF(relationship_status, ''), 'Not set') AS engagement, COUNT(*) AS total
        FROM partner_contact_accounts
        GROUP BY COALESCE(NULLIF(relationship_status, ''), 'Not set')
        ORDER BY total DESC
    """).fetchall()
    connection.close()
    return render_template("partner_reports.html", partner_rows=partner_rows, engagement_rows=engagement_rows)


@app.route("/reports/partners/export")
def export_partner_reports():
    connection = get_db_connection()
    rows = connection.execute("""
        SELECT
            partners.partner_name,
            partners.partner_type,
            partner_contact_accounts.relationship_status AS involvement_status,
            accounts.account_name,
            partner_contacts.name AS partner_contact_name,
            partner_contacts.job_title,
            partner_contacts.relationship_status
        FROM partners
        LEFT JOIN partner_contact_accounts ON partner_contact_accounts.partner_id = partners.id
        LEFT JOIN accounts ON accounts.id = partner_contact_accounts.account_id
        LEFT JOIN partner_contacts ON partner_contacts.id = partner_contact_accounts.partner_contact_id
        ORDER BY partners.partner_name, accounts.account_name, partner_contacts.name
    """).fetchall()
    connection.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Partner", "Partner Type", "Partner Engagement", "Account", "Partner Contact", "Job Title", "Contact Engagement"])
    for row in rows:
        writer.writerow([
            row["partner_name"],
            row["partner_type"],
            row["involvement_status"],
            row["account_name"],
            row["partner_contact_name"],
            row["job_title"],
            row["relationship_status"],
        ])
    response = Response(output.getvalue(), mimetype="text/csv")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    response.headers["Content-Disposition"] = f"attachment; filename=partner_reports_{timestamp}.csv"
    return response


def audit_retention_cutoff():
    return (datetime.now() - timedelta(days=183)).strftime("%Y-%m-%d %H:%M:%S")


def cleanup_audit_retention():
    if not audit_retention_enabled():
        return
    cutoff = audit_retention_cutoff()
    cleanup_admin_audit_entries_older_than(cutoff)
    if using_postgres():
        for user in list_users(current_user()):
            schema = user["workspace_schema"] if "workspace_schema" in user.keys() else ""
            if not schema:
                continue
            try:
                connection = get_schema_connection(schema=schema)
                connection.execute("DELETE FROM audit_entries WHERE date_created < ?", (cutoff,))
                connection.commit()
                connection.close()
            except Exception:
                continue
    else:
        connection = get_db_connection()
        connection.execute("DELETE FROM audit_entries WHERE date_created < ?", (cutoff,))
        connection.commit()
        connection.close()


def parse_audit_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def audit_entry_date(value):
    if not value:
        return None
    text = str(value)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:len(fmt)], fmt).date()
        except ValueError:
            continue
    return None


def audit_month_label(value):
    parsed = audit_entry_date(value)
    return parsed.strftime("%B %Y") if parsed else "Unknown Month"


def normalise_audit_row(row, source, workspace_owner=""):
    row_dict = dict(row)
    if source == "admin":
        return {
            "source": "Admin",
            "date_created": row_dict.get("date_created", ""),
            "actor_name": row_dict.get("actor_name", ""),
            "actor_email": row_dict.get("actor_email", ""),
            "action_type": row_dict.get("action_type", ""),
            "record": row_dict.get("target_label") or row_dict.get("target_type") or "Admin change",
            "field": row_dict.get("target_type") or "Admin",
            "value_from": "",
            "value_to": row_dict.get("detail", ""),
            "workspace_owner": "Admin",
            "month_label": audit_month_label(row_dict.get("date_created", "")),
        }
    return {
        "source": "Workspace",
        "date_created": row_dict.get("date_created", ""),
        "actor_name": row_dict.get("actor_name", ""),
        "actor_email": row_dict.get("actor_email", ""),
        "action_type": row_dict.get("action_type", ""),
        "record": f"{row_dict.get('entity_type') or 'record'} #{row_dict.get('entity_id') or '-'}",
        "field": row_dict.get("field_label") or row_dict.get("field_name") or "Record",
        "value_from": row_dict.get("value_from", ""),
        "value_to": row_dict.get("value_to", ""),
        "workspace_owner": workspace_owner or "Current workspace",
        "month_label": audit_month_label(row_dict.get("date_created", "")),
    }


def collect_audit_entries():
    cleanup_audit_retention()
    rows = []
    auth_connection = get_auth_connection()
    admin_rows = auth_connection.execute("""
        SELECT *
        FROM admin_audit_entries
        ORDER BY date_created DESC, id DESC
    """).fetchall()
    auth_connection.close()
    rows.extend(normalise_audit_row(row, "admin") for row in admin_rows)

    if using_postgres():
        for user in list_users(current_user()):
            schema = user["workspace_schema"] if "workspace_schema" in user.keys() else ""
            if not schema:
                continue
            try:
                connection = get_schema_connection(schema=schema)
                workspace_rows = connection.execute("""
                    SELECT *
                    FROM audit_entries
                    ORDER BY date_created DESC, id DESC
                """).fetchall()
                connection.close()
            except Exception:
                continue
            owner = user["full_name"] or user["email"]
            rows.extend(normalise_audit_row(row, "workspace", owner) for row in workspace_rows)
    else:
        connection = get_db_connection()
        workspace_rows = connection.execute("""
            SELECT *
            FROM audit_entries
            ORDER BY date_created DESC, id DESC
        """).fetchall()
        connection.close()
        rows.extend(normalise_audit_row(row, "workspace", current_user()["full_name"] if current_user() else "") for row in workspace_rows)

    return rows


def filtered_audit_entries(entries, start_date=None, end_date=None, user_filter=""):
    filtered = []
    user_filter = (user_filter or "").strip().lower()
    for entry in entries:
        entry_date = audit_entry_date(entry["date_created"])
        if start_date and (not entry_date or entry_date < start_date):
            continue
        if end_date and (not entry_date or entry_date > end_date):
            continue
        actor_blob = f"{entry['actor_name']} {entry['actor_email']} {entry['workspace_owner']}".lower()
        if user_filter and user_filter not in actor_blob:
            continue
        filtered.append(entry)
    return sorted(filtered, key=lambda row: row["date_created"] or "", reverse=True)


def audit_filter_users(entries):
    names_by_email = {}
    standalone_names = set()
    for entry in entries:
        name = (entry["actor_name"] or "").strip()
        email = (entry["actor_email"] or "").strip().lower()
        owner = (entry["workspace_owner"] or "").strip()
        if email and name:
            names_by_email[email] = name
        elif name and "@" not in name:
            standalone_names.add(name)
        if owner and owner != "Admin" and "@" not in owner:
            standalone_names.add(owner)
    return sorted(set(names_by_email.values()) | standalone_names)


def group_audit_entries_by_month(entries):
    groups = []
    current_label = None
    current_rows = []
    for entry in entries:
        label = entry["month_label"]
        if current_label is None:
            current_label = label
        if label != current_label:
            groups.append({"month": current_label, "entries": current_rows})
            current_label = label
            current_rows = []
        current_rows.append(entry)
    if current_label is not None:
        groups.append({"month": current_label, "entries": current_rows})
    return groups


@app.route("/audit")
@admin_required
def audit_trail():
    start_date_raw = request.args.get("start_date", "")
    end_date_raw = request.args.get("end_date", "")
    user_filter = request.args.get("user", "")
    all_entries = collect_audit_entries()
    entries = filtered_audit_entries(
        all_entries,
        parse_audit_date(start_date_raw),
        parse_audit_date(end_date_raw),
        user_filter,
    )
    users = audit_filter_users(all_entries)
    return render_template(
        "audit.html",
        audit_groups=group_audit_entries_by_month(entries),
        entries=entries,
        users=users,
        selected_start_date=start_date_raw,
        selected_end_date=end_date_raw,
        selected_user=user_filter,
        audit_retention_enabled=audit_retention_enabled(),
    )


@app.route("/audit/export")
@admin_required
def export_audit_trail():
    start_date_raw = request.args.get("start_date", "")
    end_date_raw = request.args.get("end_date", "")
    user_filter = request.args.get("user", "")
    entries = filtered_audit_entries(
        collect_audit_entries(),
        parse_audit_date(start_date_raw),
        parse_audit_date(end_date_raw),
        user_filter,
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Date Created",
        "Source",
        "Workspace Owner",
        "User",
        "User Email",
        "Action",
        "Record",
        "Field",
        "Value From",
        "Value To",
    ])
    for entry in entries:
        writer.writerow([
            entry["date_created"],
            entry["source"],
            entry["workspace_owner"],
            entry["actor_name"],
            entry["actor_email"],
            entry["action_type"],
            entry["record"],
            entry["field"],
            entry["value_from"],
            entry["value_to"],
        ])
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=audit_trail_{timestamp}.csv"
        },
    )


def documented_sales_play(row):
    sales_play = (row["sales_play"] or "").strip()
    if sales_play:
        return sales_play

    for field in ("notes", "subject"):
        value = row[field] or ""
        match = re.search(r"Sales play:\s*(.+?)(?:\.\s*Contact:|$)", value, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return ""


def pg_bible_meeting_datetime_label(row):
    if not row:
        return ""
    parts = [row["scheduled_meeting_date"] or ""]
    if row["scheduled_meeting_time"]:
        parts.append(row["scheduled_meeting_time"])
    return " ".join(part for part in parts if part).strip()


def pg_bible_outreach_people_label(connection, outreach_row):
    if not outreach_row:
        return ""
    people = connection.execute("""
        SELECT
            COALESCE(contacts.name, partner_contacts.name) AS person_name,
            COALESCE(contacts.job_title, partner_contacts.job_title) AS person_title,
            partners.partner_name
        FROM outreach_recipients
        LEFT JOIN contacts ON outreach_recipients.contact_id = contacts.id
        LEFT JOIN partner_contacts ON outreach_recipients.partner_contact_id = partner_contacts.id
        LEFT JOIN partners ON partner_contacts.partner_id = partners.id
        WHERE outreach_recipients.outreach_id = ?
        ORDER BY outreach_recipients.sort_order, outreach_recipients.id
    """, (outreach_row["id"],)).fetchall()
    if not people:
        people = connection.execute("""
            SELECT
                COALESCE(contacts.name, partner_contacts.name) AS person_name,
                COALESCE(contacts.job_title, partner_contacts.job_title) AS person_title,
                partners.partner_name
            FROM outreach
            LEFT JOIN contacts ON outreach.contact_id = contacts.id
            LEFT JOIN partner_contacts ON outreach.partner_contact_id = partner_contacts.id
            LEFT JOIN partners ON partner_contacts.partner_id = partners.id
            WHERE outreach.id = ?
        """, (outreach_row["id"],)).fetchall()

    labels = []
    for person in people:
        name = person["person_name"] or ""
        title = person["person_title"] or ""
        partner = person["partner_name"] or ""
        if not name and not title:
            continue
        label = ", ".join(part for part in [name, title] if part)
        if partner:
            label = f"{label} ({partner})"
        labels.append(label)
    return "; ".join(labels)


def build_pg_bible_report_from_db(connection):
    from models import ActionItem, OwnerReport, PlanItem, UserProfile, WeeklyResultRow

    profile = connection.execute("""
        SELECT *
        FROM user_profile
        WHERE id = 1
    """).fetchone()

    profile_name = (profile["full_name"] if profile and profile["full_name"] else "PipeFlow")
    accounts = connection.execute("""
        SELECT *
        FROM accounts
        ORDER BY
            CASE WHEN pg_bible_order IS NULL THEN 1 ELSE 0 END,
            pg_bible_order,
            account_name
    """).fetchall()

    plan_items = []
    for account in accounts:
        plan_items.append(PlanItem(
            pg_bible_order=account["pg_bible_order"],
            account_tier=account["account_tier"] or "",
            pipeline_target_value=account["pipeline_target"] or 0,
            notes=account["notes"] or "",
            nbm_target=str(account["pg_bible_order"] or ""),
            customer=account["account_name"] or "",
            sales_play=account["sales_play"] or "",
            estimated_value=account["pipeline_target"] or 0,
        ))

    contacts = connection.execute("""
        SELECT
            contacts.*,
            accounts.pipeline_target,
            accounts.account_name,
            accounts.pg_bible_order,
            accounts.sales_play AS account_sales_play
        FROM contacts
        LEFT JOIN accounts ON contacts.account_id = accounts.id
        ORDER BY
            CASE WHEN accounts.pg_bible_order IS NULL THEN 1 ELSE 0 END,
            accounts.pg_bible_order,
            accounts.account_name,
            contacts.name
    """).fetchall()

    action_items = []
    stale_contact_cutoff = (datetime.now() - timedelta(days=30)).date()
    for contact in contacts:
        if not contact_has_recent_or_open_activity(connection, contact["id"], stale_contact_cutoff):
            continue
        latest_outreach = connection.execute("""
            SELECT *
            FROM outreach
            WHERE contact_id = ?
               OR id IN (
                    SELECT outreach_id
                    FROM outreach_recipients
                    WHERE contact_id = ?
               )
            ORDER BY activity_date DESC, activity_time DESC
            LIMIT 1
        """, (contact["id"], contact["id"])).fetchone()
        open_outreach = connection.execute(f"""
            SELECT *
            FROM outreach
            WHERE (
                    contact_id = ?
                 OR id IN (
                        SELECT outreach_id
                        FROM outreach_recipients
                        WHERE contact_id = ?
                    )
            )
              AND {open_task_sql("outreach")}
            ORDER BY next_action_date ASC, next_action_time ASC, id DESC
            LIMIT 1
        """, (contact["id"], contact["id"], *open_task_params())).fetchone()
        next_action_text = (
            (open_outreach["next_action"] or open_outreach["subject"] or "").strip()
            if open_outreach else ""
        ) or "No next action set"
        contact_sales_play = (
            (latest_outreach["sales_play"] or documented_sales_play(latest_outreach)).strip()
            if latest_outreach else ""
        ) or (contact["account_sales_play"] or "")
        discovery_target_parts = [
            ", ".join(part for part in [contact["name"], contact["job_title"]] if part)
        ]
        if contact_sales_play:
            discovery_target_parts.append(contact_sales_play)

        meeting_count = connection.execute("""
            SELECT COUNT(*)
            FROM outreach
            WHERE (
                    contact_id = ?
                 OR id IN (
                        SELECT outreach_id
                        FROM outreach_recipients
                        WHERE contact_id = ?
                    )
            )
              AND (
                    outcome IN ('Discovery Booked', 'NBM Booked', 'Exec Meeting Booked', 'Meeting Booked')
                 OR activity_type = 'Meeting'
              )
        """, (contact["id"], contact["id"])).fetchone()[0]
        discovery_meeting_count = connection.execute("""
            SELECT COUNT(*)
            FROM outreach
            WHERE (
                    contact_id = ?
                 OR id IN (
                        SELECT outreach_id
                        FROM outreach_recipients
                        WHERE contact_id = ?
                    )
            )
              AND (
                    outcome = 'Discovery Booked'
                 OR outcome = 'Meeting Booked'
                 OR activity_type = 'Meeting'
              )
        """, (contact["id"], contact["id"])).fetchone()[0]
        pg_progress_update = connection.execute("""
            SELECT completed_discovery_meeting
            FROM pg_action_contact_updates
            WHERE contact_id = ?
        """, (contact["id"],)).fetchone()
        discovery_completed = (
            pg_progress_update["completed_discovery_meeting"]
            if pg_progress_update and pg_progress_update["completed_discovery_meeting"]
            else ("Yes" if discovery_meeting_count else "No")
        )
        nbm_booked_outreach = connection.execute("""
            SELECT *
            FROM outreach
            WHERE (
                    contact_id = ?
                 OR id IN (
                        SELECT outreach_id
                        FROM outreach_recipients
                        WHERE contact_id = ?
                    )
            )
              AND outcome = 'NBM Booked'
              AND scheduled_meeting_date IS NOT NULL
              AND scheduled_meeting_date != ''
            ORDER BY scheduled_meeting_date DESC, scheduled_meeting_time DESC, id DESC
            LIMIT 1
        """, (contact["id"], contact["id"])).fetchone()
        nbm_booked_date = pg_bible_meeting_datetime_label(nbm_booked_outreach)
        nbm_booked_people = pg_bible_outreach_people_label(connection, nbm_booked_outreach)

        action_items.append(ActionItem(
            person_name=contact["name"] or "",
            person_title=contact["job_title"] or "",
            related_nbm_target=str(contact["pg_bible_order"] or ""),
            discovery_target_name_title=" - ".join(part for part in discovery_target_parts if part),
            discovery_completed=discovery_completed,
            discovery_next_action=next_action_text,
            nbm_booked_date=nbm_booked_date,
            nbm_booked_name_title=nbm_booked_people,
            why_buy="",
            exec_first="Yes" if contact["category"] == "Executive" else "",
            prep_with_manager="",
            nbm_completed="Yes" if meeting_count else "",
            nbm_next_action=next_action_text,
            vo_value=contact["pipeline_target"] or 0 if meeting_count else 0,
        ))

    weekly_source_rows = connection.execute("""
        SELECT
            outreach.activity_date,
            outreach.activity_type,
            outreach.outcome,
            outreach.task_status,
            accounts.pipeline_target,
            contacts.category
        FROM outreach
        LEFT JOIN accounts ON outreach.account_id = accounts.id
        LEFT JOIN contacts ON outreach.contact_id = contacts.id
        WHERE activity_date IS NOT NULL
          AND activity_date != ''
    """).fetchall()

    weekly_totals = {}
    for row in weekly_source_rows:
        try:
            activity_date = datetime.strptime(str(row["activity_date"]), "%Y-%m-%d").date()
        except ValueError:
            continue
        week_start = activity_date - timedelta(days=activity_date.weekday())
        week_key = week_start.isoformat()
        if week_key not in weekly_totals:
            weekly_totals[week_key] = {
                "vitos_sent": 0,
                "vitos_chased": 0,
                "discovery_booked": 0,
                "discovery_completed": 0,
                "nbms_booked": 0,
                "nbms_exec_firsts": 0,
                "nbms_completed": 0,
                "pipeline_generated_vo_count": 0,
                "pipeline_generated_value": 0,
            }
        totals = weekly_totals[week_key]
        is_discovery_booked = row["outcome"] == "Discovery Booked" or row["activity_type"] == "Meeting"
        is_nbm_booked = row["outcome"] == "NBM Booked"
        is_exec_meeting_booked = row["outcome"] == "Exec Meeting Booked"
        is_pg_success = is_pg_success_outcome(row["outcome"], row["activity_type"])
        is_pipeline_outcome = row["outcome"] in (*PG_SUCCESS_OUTCOMES, "Positive Response", "Referral Made")
        if row["activity_type"] == "VITO":
            totals["vitos_sent"] += 1
            if normalise_outreach_outcome(row["outcome"]) != "No Response":
                totals["vitos_chased"] += 1
        if is_discovery_booked or is_pg_success:
            totals["discovery_booked"] += 1
        if row["activity_type"] == "Meeting":
            totals["discovery_completed"] += 1
        if is_nbm_booked or is_exec_meeting_booked:
            totals["nbms_booked"] += 1
            if row["category"] == "Executive" or is_exec_meeting_booked:
                totals["nbms_exec_firsts"] += 1
            if is_closed_task_status(row["task_status"]):
                totals["nbms_completed"] += 1
        if is_pipeline_outcome:
            totals["pipeline_generated_vo_count"] += 1
            totals["pipeline_generated_value"] += row["pipeline_target"] or 0

    weekly_results = [
        WeeklyResultRow(
            week_key=week_key,
            vitos_sent=totals["vitos_sent"],
            vitos_chased=totals["vitos_chased"],
            discovery_booked=totals["discovery_booked"],
            discovery_completed=totals["discovery_completed"],
            nbms_booked=totals["nbms_booked"],
            nbms_exec_firsts=totals["nbms_exec_firsts"],
            nbms_completed=totals["nbms_completed"],
            pipeline_generated_vo_count=totals["pipeline_generated_vo_count"],
            pipeline_generated_value=totals["pipeline_generated_value"],
        )
        for week_key, totals in sorted(weekly_totals.items())
    ]

    total_account_target = sum(account["pipeline_target"] or 0 for account in accounts)
    total_pipeline_added = sum(row.pipeline_generated_value or 0 for row in weekly_results)
    calc_payload = {
        "starting_pipeline": os.environ.get("PIPEFLOW_PG_STARTING_PIPELINE", total_account_target),
        "pipeline_added": os.environ.get("PIPEFLOW_PG_PIPELINE_ADDED", total_pipeline_added),
        "pipeline_target": os.environ.get("PIPEFLOW_PG_PIPELINE_TARGET", total_account_target),
    }

    return OwnerReport(
        profile=UserProfile(profile_name=profile_name, username=profile_name),
        plan_items=plan_items,
        action_items=action_items,
        weekly_results=weekly_results,
        calc_payload=calc_payload,
    )


@app.route("/reports/pg-bible/export")
def export_pg_bible():
    template_setting = os.environ.get("PG_BIBLE_TEMPLATE_PATH", "").strip()
    if not template_setting:
        template_dir = Path(__file__).resolve().parent / "pg_bible_templates"
        bundled_template = template_dir / "PGBible_Template_May2026.xlsx"
        if not bundled_template.exists():
            bundled_template = template_dir / "PG Bible FY27.xlsx"
        template_setting = str(bundled_template)

    try:
        from excel_exporter import PGBibleExporter
        from models import PGBibleExportError
    except ModuleNotFoundError:
        return Response(
            "PG Bible export requires openpyxl. Install dependencies with python3 -m pip install -r requirements.txt.",
            status=500,
            mimetype="text/plain",
        )

    template_path = Path(template_setting)

    if not template_path.exists():
        return Response(
            f"PG Bible template not found: {template_path}",
            status=400,
            mimetype="text/plain",
        )

    connection = get_db_connection()
    report = build_pg_bible_report_from_db(connection)
    connection.close()

    try:
        output_dir = Path(os.environ.get("PIPEFLOW_DATA_DIR", Path(__file__).resolve().parent / "server_data")) / "exports"
        output_path = PGBibleExporter(template_path, output_dir).export(report)
    except PGBibleExportError as exc:
        return Response(
            f"{exc.error_code}: {exc.human_message}\n" + "\n".join(exc.details),
            status=400,
            mimetype="text/plain",
        )

    return send_file(
        output_path,
        as_attachment=True,
        download_name=output_path.name,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/reports/accounts")
def account_reports():
    initialise_database(force=True)
    connection = get_db_connection()

    accounts = connection.execute("""
        SELECT
            id,
            pg_bible_order,
            account_name,
            customer_logo,
            account_tier,
            industry,
            country,
            city,
            pipeline_target
        FROM accounts
        ORDER BY
            CASE WHEN pg_bible_order IS NULL THEN 1 ELSE 0 END,
            pg_bible_order,
            account_name
    """).fetchall()

    accounts_by_industry = connection.execute("""
        SELECT
            COALESCE(NULLIF(industry, ''), 'Unknown') AS industry,
            COUNT(*) AS total
        FROM accounts
        GROUP BY COALESCE(NULLIF(industry, ''), 'Unknown')
        ORDER BY total DESC
    """).fetchall()

    pipeline_by_account = connection.execute("""
        SELECT
            account_name,
            COALESCE(pipeline_target, 0) AS pipeline_target
        FROM accounts
        ORDER BY pipeline_target DESC
        LIMIT 10
    """).fetchall()

    accounts_by_country = connection.execute("""
        SELECT
            COALESCE(NULLIF(country, ''), 'Unknown') AS country,
            COUNT(*) AS total
        FROM accounts
        GROUP BY COALESCE(NULLIF(country, ''), 'Unknown')
        ORDER BY total DESC
    """).fetchall()

    accounts_by_tier = connection.execute("""
        SELECT
            COALESCE(NULLIF(account_tier, ''), 'Not set') AS account_tier,
            COUNT(*) AS total
        FROM accounts
        GROUP BY COALESCE(NULLIF(account_tier, ''), 'Not set')
        ORDER BY account_tier
    """).fetchall()

    account_metrics = {
        "total_accounts": len(accounts),
        "total_pipeline_target": sum(float(account["pipeline_target"] or 0) for account in accounts),
        "pg_ordered_accounts": sum(1 for account in accounts if account["pg_bible_order"]),
        "tiered_accounts": sum(1 for account in accounts if account["account_tier"]),
        "accounts_with_contacts": connection.execute(
            "SELECT COUNT(DISTINCT account_id) FROM contacts WHERE account_id IS NOT NULL AND COALESCE(status, 'Active') != 'Archived'"
        ).fetchone()[0],
        "accounts_with_open_outreach": connection.execute(f"""
            SELECT COUNT(DISTINCT account_id)
            FROM outreach
            WHERE account_id IS NOT NULL
              AND {open_task_sql("outreach")}
        """, open_task_params()).fetchone()[0],
    }

    connection.close()

    return render_template(
        "account_reports.html",
        accounts=accounts,
        account_metrics=account_metrics,
        accounts_by_industry=report_bar_rows(accounts_by_industry),
        pipeline_by_account=report_bar_rows(pipeline_by_account, "pipeline_target"),
        accounts_by_country=report_bar_rows(accounts_by_country),
        accounts_by_tier=report_bar_rows(accounts_by_tier)
    )


@app.route("/reports/accounts/export")
def export_account_reports():
    connection = get_db_connection()

    accounts = connection.execute("""
        SELECT
            pg_bible_order,
            account_name,
            account_tier,
            industry,
            country,
            city,
            pipeline_target
        FROM accounts
        ORDER BY
            CASE WHEN pg_bible_order IS NULL THEN 1 ELSE 0 END,
            pg_bible_order,
            account_name
    """).fetchall()

    connection.close()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "PG Bible Order",
        "Account Name",
        "Account Tier",
        "Industry",
        "Country",
        "City",
        "Pipeline Target"
    ])

    for account in accounts:
        writer.writerow([
            account["pg_bible_order"],
            account["account_name"],
            account["account_tier"],
            account["industry"],
            account["country"],
            account["city"],
            account["pipeline_target"]
        ])

    response = Response(
        output.getvalue(),
        mimetype="text/csv"
    )

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    response.headers["Content-Disposition"] = (
        f"attachment; filename=account_reports_{timestamp}.csv"
    )

    return response


@app.route("/reports/tasks")
def task_reports():
    return redirect(url_for("outreach_reports"))
    connection = get_db_connection()

    selected_start_date = request.args.get("start_date", "")
    selected_end_date = request.args.get("end_date", "")
    selected_account = request.args.get("account_id", "")
    selected_task_status = request.args.get("task_status", "")
    selected_assigned_to = request.args.get("assigned_to", "")

    accounts = connection.execute("""
        SELECT id, account_name
        FROM accounts
        ORDER BY account_name
    """).fetchall()

    all_tasks = connection.execute("""
        SELECT
            outreach.id,
            outreach.account_id,
            outreach.next_action,
            outreach.next_action_date,
            outreach.next_action_time,
            outreach.task_status,
            outreach.assigned_to,
            outreach.sales_play,
            accounts.account_name,
            accounts.account_tier,
            contacts.name AS contact_name,
            COALESCE(
                (
                    SELECT COALESCE(recipient_contacts.name, recipient_partner_contacts.name)
                    FROM outreach_recipients
                    LEFT JOIN contacts AS recipient_contacts ON outreach_recipients.contact_id = recipient_contacts.id
                    LEFT JOIN partner_contacts AS recipient_partner_contacts ON outreach_recipients.partner_contact_id = recipient_partner_contacts.id
                    WHERE outreach_recipients.outreach_id = outreach.id
                    ORDER BY outreach_recipients.sort_order, outreach_recipients.id
                    LIMIT 1
                ),
                contacts.name
            ) AS display_contact_name,
            COALESCE(
                (
                    SELECT COUNT(*)
                    FROM outreach_recipients
                    WHERE outreach_recipients.outreach_id = outreach.id
                ),
                CASE WHEN outreach.contact_id IS NOT NULL THEN 1 ELSE 0 END
            ) AS recipient_count
        FROM outreach
        LEFT JOIN accounts ON outreach.account_id = accounts.id
        LEFT JOIN contacts ON outreach.contact_id = contacts.id
        WHERE outreach.next_action IS NOT NULL
          AND outreach.next_action != ''
        ORDER BY outreach.next_action_date ASC, outreach.next_action_time ASC
    """).fetchall()

    connection.close()

    def parse_report_date(value):
        if not value:
            return None
        try:
            return datetime.strptime(str(value), "%Y-%m-%d").date()
        except ValueError:
            return None

    start_date = parse_report_date(selected_start_date)
    end_date = parse_report_date(selected_end_date)

    def normalised_status(task):
        return task["task_status"] or "Not Started"

    def include_task(task):
        task_date = parse_report_date(task["next_action_date"])
        if start_date and (not task_date or task_date < start_date):
            return False
        if end_date and (not task_date or task_date > end_date):
            return False
        if selected_account and str(task["account_id"] or "") != selected_account:
            return False
        if selected_task_status and normalised_status(task) != selected_task_status:
            return False
        if selected_assigned_to and (task["assigned_to"] or "") != selected_assigned_to:
            return False
        return True

    tasks = [task for task in all_tasks if include_task(task)]
    now = current_app_datetime()
    today = now.date()
    active_tasks = [task for task in tasks if not is_closed_task_status(normalised_status(task))]
    overdue_tasks = sum(
        1 for task in active_tasks
        if is_overdue_task(task["next_action_date"], task["next_action_time"], task["task_status"], now)
    )
    due_today = sum(
        1 for task in active_tasks
        if parse_report_date(task["next_action_date"]) == today
    )
    upcoming_tasks = sum(
        1 for task in active_tasks
        if parse_report_date(task["next_action_date"]) and parse_report_date(task["next_action_date"]) > today
    )

    task_statuses = [
        {"task_status": status}
        for status in sorted({normalised_status(task) for task in all_tasks})
    ]
    fallback_assignee = default_outreach_assignee()
    assigned_users = [
        {"assigned_to": assigned_to}
        for assigned_to in sorted({task["assigned_to"] or fallback_assignee for task in all_tasks})
    ]

    status_totals = {}
    account_totals = {}
    assignee_totals = {}
    for task in tasks:
        status = normalised_status(task)
        account_name = task["account_name"] or "Unknown"
        assignee = task["assigned_to"] or fallback_assignee
        task_date = parse_report_date(task["next_action_date"])
        status_totals[status] = status_totals.get(status, 0) + 1
        account_totals[account_name] = account_totals.get(account_name, 0) + 1
        if assignee not in assignee_totals:
            assignee_totals[assignee] = {
                "assignee": assignee,
                "active_tasks": 0,
                "overdue_active_tasks": 0,
                "closed_tasks": 0,
            }
        if is_closed_task_status(status):
            assignee_totals[assignee]["closed_tasks"] += 1
        else:
            assignee_totals[assignee]["active_tasks"] += 1
            if is_overdue_task(task["next_action_date"], task["next_action_time"], status, now):
                assignee_totals[assignee]["overdue_active_tasks"] += 1

    tasks_by_status = [
        {"status": status, "total": total}
        for status, total in sorted(status_totals.items(), key=lambda item: (-item[1], item[0]))
    ]
    tasks_by_account = [
        {"account_name": account_name, "total": total}
        for account_name, total in sorted(account_totals.items(), key=lambda item: (-item[1], item[0]))[:10]
    ]
    status_chart_labels = [item["status"] for item in tasks_by_status]
    status_chart_data = [item["total"] for item in tasks_by_status]
    account_chart_labels = [item["account_name"] for item in tasks_by_account]
    account_chart_data = [item["total"] for item in tasks_by_account]
    sla_by_assignee = sorted(
        assignee_totals.values(),
        key=lambda item: (-item["overdue_active_tasks"], -item["active_tasks"], item["assignee"]),
    )

    return render_template(
        "task_reports.html",
        tasks=tasks,
        overdue_tasks=overdue_tasks,
        due_today=due_today,
        upcoming_tasks=upcoming_tasks,
        tasks_by_status=tasks_by_status,
        tasks_by_account=tasks_by_account,
        sla_by_assignee=sla_by_assignee,
        accounts=accounts,
        task_statuses=task_statuses,
        assigned_users=assigned_users,
        selected_start_date=selected_start_date,
        selected_end_date=selected_end_date,
        selected_account=selected_account,
        selected_task_status=selected_task_status,
        selected_assigned_to=selected_assigned_to,
        status_chart_labels=status_chart_labels,
        status_chart_data=status_chart_data,
        account_chart_labels=account_chart_labels,
        account_chart_data=account_chart_data
    )


@app.route("/reports/tasks/export")
def export_task_reports():
    return redirect(url_for("export_outreach_reports"))
    connection = get_db_connection()

    tasks = connection.execute("""
        SELECT
            outreach.next_action,
            outreach.next_action_date,
            outreach.next_action_time,
            outreach.task_status,
            outreach.assigned_to,
            outreach.sales_play,
            outreach.subject,
            outreach.notes,
            outreach.outcome,
            outreach.activity_type,
            outreach.activity_date,
            accounts.account_name,
            accounts.account_tier,
            contacts.name AS contact_name
        FROM outreach
        LEFT JOIN accounts ON outreach.account_id = accounts.id
        LEFT JOIN contacts ON outreach.contact_id = contacts.id
        WHERE outreach.next_action IS NOT NULL
          AND outreach.next_action != ''
        ORDER BY outreach.next_action_date ASC, outreach.next_action_time ASC
    """).fetchall()

    connection.close()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Next Action",
        "Next Action Date",
        "Next Action Time",
        "Task Status",
        "Assigned To",
        "Sales Play",
        "Account",
        "Account Tier",
        "Contact",
        "Subject",
        "System Metadata",
        "Outcome",
        "Activity Type",
        "Activity Date"
    ])

    for task in tasks:
        writer.writerow([
            task["next_action"],
            task["next_action_date"],
            task["next_action_time"],
            task["task_status"],
            task["assigned_to"],
            task["sales_play"],
            task["account_name"],
            task["account_tier"],
            task["contact_name"],
            task["subject"],
            task["notes"],
            task["outcome"],
            task["activity_type"],
            task["activity_date"]
        ])

    response = Response(
        output.getvalue(),
        mimetype="text/csv"
    )

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    response.headers["Content-Disposition"] = (
        f"attachment; filename=task_reports_{timestamp}.csv"
    )

    return response


@app.route("/reports/outreach")
def outreach_reports():
    initialise_database(force=True)
    connection = get_db_connection()

    report_today = current_app_datetime().date()
    default_start = report_today - timedelta(days=6)
    selected_start_date = request.args.get("start_date", default_start.isoformat())
    selected_end_date = request.args.get("end_date", report_today.isoformat())
    selected_account = request.args.get("account_id", "")
    selected_activity_type = request.args.get("activity_type", "")
    selected_outcome = request.args.get("outcome", "")

    accounts = connection.execute("""
        SELECT id, account_name
        FROM accounts
        ORDER BY account_name
    """).fetchall()

    activity_types = connection.execute("""
        SELECT DISTINCT activity_type
        FROM outreach
        WHERE activity_type IS NOT NULL
          AND activity_type != ''
        ORDER BY activity_type
    """).fetchall()

    outcomes = connection.execute("""
        SELECT DISTINCT outcome
        FROM outreach
        WHERE outcome IS NOT NULL
          AND outcome != ''
        ORDER BY outcome
    """).fetchall()

    all_outreach = connection.execute("""
        SELECT
            outreach.id,
            outreach.account_id,
            outreach.activity_date,
            outreach.activity_time,
            outreach.next_action_date,
            outreach.next_action_time,
            outreach.activity_type,
            outreach.outcome,
            outreach.task_status,
            outreach.sales_play,
            outreach.subject,
            outreach.next_action,
            outreach.assigned_to,
            outreach.fy,
            outreach.quarter,
            accounts.account_name,
            accounts.account_tier,
            contacts.name AS contact_name,
            COALESCE(
                (
                    SELECT COALESCE(recipient_contacts.name, recipient_partner_contacts.name)
                    FROM outreach_recipients
                    LEFT JOIN contacts AS recipient_contacts ON outreach_recipients.contact_id = recipient_contacts.id
                    LEFT JOIN partner_contacts AS recipient_partner_contacts ON outreach_recipients.partner_contact_id = recipient_partner_contacts.id
                    WHERE outreach_recipients.outreach_id = outreach.id
                    ORDER BY outreach_recipients.sort_order, outreach_recipients.id
                    LIMIT 1
                ),
                contacts.name
            ) AS display_contact_name,
            COALESCE(
                (
                    SELECT COUNT(*)
                    FROM outreach_recipients
                    WHERE outreach_recipients.outreach_id = outreach.id
                ),
                CASE WHEN outreach.contact_id IS NOT NULL THEN 1 ELSE 0 END
            ) AS recipient_count
        FROM outreach
        LEFT JOIN accounts ON outreach.account_id = accounts.id
        LEFT JOIN contacts ON outreach.contact_id = contacts.id
        ORDER BY outreach.activity_date DESC, outreach.activity_time DESC, outreach.id DESC
    """).fetchall()

    connection.close()

    def parse_report_date(value):
        if not value:
            return None
        try:
            return datetime.strptime(str(value), "%Y-%m-%d").date()
        except ValueError:
            return None

    start_date = parse_report_date(selected_start_date)
    end_date = parse_report_date(selected_end_date)

    def include_item(item):
        activity_date = parse_report_date(item["activity_date"])
        if start_date and (not activity_date or activity_date < start_date):
            return False
        if end_date and (not activity_date or activity_date > end_date):
            return False
        if selected_account and str(item["account_id"] or "") != selected_account:
            return False
        if selected_activity_type and (item["activity_type"] or "") != selected_activity_type:
            return False
        if selected_outcome and (item["outcome"] or "") != selected_outcome:
            return False
        return True

    filtered_outreach = [item for item in all_outreach if include_item(item)]
    filtered_outreach = [
        {
            **dict(item),
            "additional_contact_count": max(int(item["recipient_count"] or 0) - 1, 0),
        }
        for item in filtered_outreach
    ]
    total_outreach = len(filtered_outreach)
    pg_success_count = sum(
        1 for item in filtered_outreach
        if is_pg_success_outcome(item["outcome"], item["activity_type"])
    )
    open_tasks = sum(1 for item in filtered_outreach if not is_closed_task_status(item["task_status"]))
    overdue_tasks = sum(
        1 for item in filtered_outreach
        if is_overdue_task(item["next_action_date"], item["next_action_time"], item["task_status"])
    )

    outcome_totals = {}
    type_totals = {}
    for item in filtered_outreach:
        outcome = item["outcome"] or "Unknown"
        activity_type = item["activity_type"] or "Unknown"
        outcome_totals[outcome] = outcome_totals.get(outcome, 0) + 1
        type_totals[activity_type] = type_totals.get(activity_type, 0) + 1

    outcome_breakdown = [
        {"outcome": outcome, "count": count}
        for outcome, count in sorted(outcome_totals.items(), key=lambda item: (-item[1], item[0]))
    ]
    outreach_by_type = [
        {"activity_type": activity_type, "count": count}
        for activity_type, count in sorted(type_totals.items(), key=lambda item: (-item[1], item[0]))
    ]
    outcome_breakdown = report_bar_rows(outcome_breakdown, "count")
    outreach_by_type = report_bar_rows(outreach_by_type, "count")
    working_week_start = report_today - timedelta(days=report_today.weekday())
    working_week_end = working_week_start + timedelta(days=6)
    working_week_outreach = [
        item for item in filtered_outreach
        if (activity_date := parse_report_date(item["activity_date"]))
        and working_week_start <= activity_date <= working_week_end
    ]

    return render_template(
        "outreach_reports.html",
        total_outreach=total_outreach,
        pg_success_count=pg_success_count,
        open_tasks=open_tasks,
        overdue_tasks=overdue_tasks,
        outcome_breakdown=outcome_breakdown,
        outreach_by_type=outreach_by_type,
        outreach_items=filtered_outreach,
        working_week_outreach=working_week_outreach,
        accounts=accounts,
        activity_types=activity_types,
        outcomes=outcomes,
        selected_start_date=selected_start_date,
        selected_end_date=selected_end_date,
        selected_account=selected_account,
        selected_activity_type=selected_activity_type,
        selected_outcome=selected_outcome,
        working_week_start=working_week_start.isoformat(),
        working_week_end=working_week_end.isoformat(),
        report_range_label=f"{format_display_date(selected_start_date)} to {format_display_date(selected_end_date)}",
    )


@app.route("/reports/outreach/export")
def export_outreach_reports():
    connection = get_db_connection()

    outreach_items = connection.execute("""
        SELECT
            outreach.activity_date,
            outreach.activity_time,
            outreach.next_action_date,
            outreach.next_action_time,
            outreach.task_status,
            outreach.sales_play,
            outreach.fy,
            outreach.quarter,
            accounts.account_name,
            accounts.account_tier,
            contacts.name AS contact_name,
            outreach.activity_type,
            outreach.outcome,
            outreach.next_action,
            outreach.notes
        FROM outreach
        LEFT JOIN accounts ON outreach.account_id = accounts.id
        LEFT JOIN contacts ON outreach.contact_id = contacts.id
        ORDER BY outreach.activity_date DESC
    """).fetchall()

    connection.close()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Date",
        "Time",
        "Due Date",
        "Due Time",
        "Status",
        "FY",
        "Quarter",
        "Sales Play or Initiative",
        "Account",
        "Account Tier",
        "Contact",
        "Activity Type",
        "Outcome",
        "Activity Update",
        "System Metadata"
    ])

    for item in outreach_items:
        writer.writerow([
            item["activity_date"],
            item["activity_time"],
            item["next_action_date"],
            item["next_action_time"],
            item["task_status"],
            item["fy"],
            item["quarter"],
            item["sales_play"],
            item["account_name"],
            item["account_tier"],
            item["contact_name"],
            item["activity_type"],
            item["outcome"],
            item["next_action"],
            item["notes"]
        ])

    response = Response(
        output.getvalue(),
        mimetype="text/csv"
    )

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    response.headers["Content-Disposition"] = (
        f"attachment; filename=outreach_reports_{timestamp}.csv"
    )

    return response


@app.route("/reports/contacts")
def contact_reports():
    initialise_database(force=True)
    connection = get_db_connection()

    contacts = connection.execute("""
        SELECT
            contacts.id,
            contacts.name,
            contacts.job_title,
            contacts.category,
            contacts.status,
            contacts.bmc_relationship,
            contacts.email,
            contacts.office_phone,
            contacts.mobile_phone,
            accounts.account_name,
            accounts.account_tier
        FROM contacts
        LEFT JOIN accounts ON contacts.account_id = accounts.id
        ORDER BY contacts.name
    """).fetchall()

    contacts_by_category = connection.execute("""
        SELECT
            COALESCE(NULLIF(category, ''), 'Unknown') AS category,
            COUNT(*) AS total
        FROM contacts
        WHERE COALESCE(status, 'Active') != 'Archived'
        GROUP BY COALESCE(NULLIF(category, ''), 'Unknown')
        ORDER BY total DESC
    """).fetchall()

    contacts_by_relationship = connection.execute("""
        SELECT
            COALESCE(NULLIF(bmc_relationship, ''), 'Unknown') AS relationship,
            COUNT(*) AS total
        FROM contacts
        WHERE COALESCE(status, 'Active') != 'Archived'
        GROUP BY COALESCE(NULLIF(bmc_relationship, ''), 'Unknown')
        ORDER BY total DESC
    """).fetchall()

    contacts_by_account = connection.execute("""
        SELECT
            accounts.account_name,
            COUNT(contacts.id) AS total
        FROM contacts
        LEFT JOIN accounts ON contacts.account_id = accounts.id
        WHERE COALESCE(contacts.status, 'Active') != 'Archived'
        GROUP BY accounts.account_name
        ORDER BY total DESC
        LIMIT 10
    """).fetchall()

    contacts_by_account_tier = connection.execute("""
        SELECT
            COALESCE(NULLIF(accounts.account_tier, ''), 'Not set') AS account_tier,
            COUNT(contacts.id) AS total
        FROM contacts
        LEFT JOIN accounts ON contacts.account_id = accounts.id
        WHERE COALESCE(contacts.status, 'Active') != 'Archived'
        GROUP BY COALESCE(NULLIF(accounts.account_tier, ''), 'Not set')
        ORDER BY account_tier
    """).fetchall()

    contact_metrics = {
        "total_contacts": len(contacts),
        "active_contacts": sum(1 for contact in contacts if (contact["status"] or "Active") != "Archived"),
        "executive_contacts": sum(
            1 for contact in contacts
            if is_executive_contact(contact["category"], contact["bmc_relationship"], contact["job_title"])
        ),
        "lead_contacts": sum(1 for contact in contacts if (contact["bmc_relationship"] or "") == "Lead"),
    }

    connection.close()

    return render_template(
        "contact_reports.html",
        contacts=contacts,
        contact_metrics=contact_metrics,
        contacts_by_category=report_bar_rows(contacts_by_category),
        contacts_by_relationship=report_bar_rows(contacts_by_relationship),
        contacts_by_account=report_bar_rows(contacts_by_account),
        contacts_by_account_tier=report_bar_rows(contacts_by_account_tier),
        message=request.args.get("message", "")
    )


@app.route("/reports/contacts/export")
def export_contact_reports():
    initialise_database(force=True)
    connection = get_db_connection()

    contacts = connection.execute("""
        SELECT
            contacts.name,
            contacts.job_title,
            contacts.category,
            contacts.status,
            contacts.bmc_relationship,
            contacts.email,
            contacts.office_phone,
            contacts.mobile_phone,
            contacts.location,
            contacts.linkedin,
            contacts.org_dept,
            contacts.responsibilities,
            contacts.characteristics,
            contacts.background,
            contacts.personal_interests,
            contacts.personal_win,
            contacts.education,
            contacts.social_media,
            contacts.additional_notes,
            accounts.account_name,
            accounts.account_tier
        FROM contacts
        LEFT JOIN accounts ON contacts.account_id = accounts.id
        WHERE COALESCE(contacts.status, 'Active') != 'Archived'
        ORDER BY contacts.name
    """).fetchall()

    connection.close()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Name",
        "Job Title",
        "Category",
        "Status",
        "BMC Relationship",
        "Email",
        "Office Phone",
        "Mobile Phone",
        "Location",
        "LinkedIn",
        "Org / Dept",
        "Responsibilities",
        "Characteristics",
        "Background",
        "Personal Interests",
        "Personal Win",
        "Education",
        "Social Media",
        "Additional Notes",
        "Account",
        "Account Tier"
    ])

    for contact in contacts:
        writer.writerow([
            contact["name"],
            contact["job_title"],
            contact["category"],
            contact["status"] or "Active",
            contact["bmc_relationship"],
            contact["email"],
            contact["office_phone"],
            contact["mobile_phone"],
            contact["location"],
            contact["linkedin"],
            contact["org_dept"],
            contact["responsibilities"],
            contact["characteristics"],
            contact["background"],
            contact["personal_interests"],
            contact["personal_win"],
            contact["education"],
            contact["social_media"],
            contact["additional_notes"],
            contact["account_name"],
            contact["account_tier"]
        ])

    response = Response(
        output.getvalue(),
        mimetype="text/csv"
    )

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    response.headers["Content-Disposition"] = (
        f"attachment; filename=contact_reports_{timestamp}.csv"
    )

    return response


def inactive_contacts_for_archive(connection, start_date, end_date):
    query = """
        SELECT
            contacts.*,
            accounts.account_name,
            accounts.account_tier
        FROM contacts
        LEFT JOIN accounts ON contacts.account_id = accounts.id
        WHERE COALESCE(contacts.status, 'Active') = 'Inactive'
          AND COALESCE(contacts.archived_at, '') = ''
    """
    params = []
    if start_date:
        query += " AND contacts.last_updated >= ?"
        params.append(f"{start_date} 00:00:00")
    if end_date:
        query += " AND contacts.last_updated <= ?"
        params.append(f"{end_date} 23:59:59")
    query += " ORDER BY contacts.last_updated DESC, contacts.name"
    return connection.execute(query, params).fetchall()


@app.route("/admin/contacts/archive")
@admin_required
def admin_archive_contacts():
    start_date = request.args.get("archive_start_date", "")
    end_date = request.args.get("archive_end_date", "")
    connection = get_db_connection()
    contacts = inactive_contacts_for_archive(connection, start_date, end_date)
    connection.close()
    return render_template(
        "admin_contact_archive.html",
        contacts=contacts,
        selected_start_date=start_date,
        selected_end_date=end_date,
        message=request.args.get("message", ""),
    )


@app.route("/reports/contacts/archive", methods=("POST",))
@admin_required
def archive_inactive_contacts():
    start_date = request.form.get("archive_start_date", "")
    end_date = request.form.get("archive_end_date", "")
    selected_contact_ids = selected_record_ids()
    connection = get_db_connection()
    contacts_to_archive = inactive_contacts_for_archive(connection, start_date, end_date)
    if selected_contact_ids:
        selected_set = set(selected_contact_ids)
        contacts_to_archive = [contact for contact in contacts_to_archive if contact["id"] in selected_set]
    archived_count = 0
    for contact in contacts_to_archive:
        connection.execute("""
            UPDATE contacts
            SET status = 'Archived',
                archived_at = CURRENT_TIMESTAMP,
                last_updated = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (contact["id"],))
        audit_record_update(
            connection,
            "contact",
            contact["id"],
            contact,
            {"status": "Archived"},
            {"status": "Status"}
        )
        archived_count += 1
    connection.commit()
    connection.close()
    return_target = safe_redirect_target(request.form.get("return_to") or url_for("contact_reports"), "contact_reports")
    return redirect_with_query(return_target, message=f"Archived {archived_count} inactive contact(s).")


@app.route("/reports/contacts/archive/export")
@admin_required
def export_inactive_contacts_for_archive():
    start_date = request.args.get("archive_start_date", "")
    end_date = request.args.get("archive_end_date", "")
    connection = get_db_connection()
    contacts = inactive_contacts_for_archive(connection, start_date, end_date)
    connection.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Job Title", "Email", "Phone", "Account", "Status", "Last Updated"])
    for contact in contacts:
        writer.writerow([
            contact["name"],
            contact["job_title"],
            contact["email"],
            contact["phone"],
            contact["account_name"],
            contact["status"],
            contact["last_updated"],
        ])
    response = Response(output.getvalue(), mimetype="text/csv")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    response.headers["Content-Disposition"] = (
        f"attachment; filename=inactive_contacts_archive_{timestamp}.csv"
    )
    return response


@app.route("/outreach/export")
def export_outreach():
    connection = get_db_connection()

    outreach_records = connection.execute("""
        SELECT
            outreach.fy,
            outreach.quarter,
            outreach.sales_play,
            outreach.activity_date,
            outreach.activity_time,
            accounts.account_name,
            accounts.account_tier,
            contacts.name AS contact_name,
            outreach.activity_type,
            outreach.subject,
            outreach.notes,
            outreach.outcome,
            outreach.next_action,
            outreach.next_action_date,
            outreach.next_action_time
        FROM outreach
        LEFT JOIN accounts ON outreach.account_id = accounts.id
        LEFT JOIN contacts ON outreach.contact_id = contacts.id
        ORDER BY outreach.activity_date DESC, outreach.activity_time DESC
    """).fetchall()

    connection.close()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "FY",
        "Quarter",
        "Sales Play or Initiative",
        "Activity Start Date",
        "Activity Start Time",
        "Account",
        "Account Tier",
        "Contact",
        "Activity Type",
        "Subject",
        "System Metadata",
        "Outcome",
        "Next Action",
        "Activity Due Date",
        "Activity Due Time"
    ])

    for row in outreach_records:
        writer.writerow([
            row["fy"],
            row["quarter"],
            row["sales_play"],
            row["activity_date"],
            row["activity_time"],
            row["account_name"],
            row["account_tier"],
            row["contact_name"],
            row["activity_type"],
            row["subject"],
            row["notes"],
            row["outcome"],
            row["next_action"],
            row["next_action_date"],
            row["next_action_time"]
        ])

    response = Response(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=pipeflow_outreach_export.csv"

    return response


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
