import sys
import os
from pathlib import Path
import threading
import webbrowser
import csv
import io
import re
import json
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode

from flask import Flask, render_template, request, redirect, url_for, Response, send_file, session, jsonify
from auth import authenticate_user, create_user, current_user, initialise_auth_database, login_required, admin_required, list_users, reset_user_password, set_user_active, set_user_role, reset_password_with_phrase, list_account_field_definitions, create_account_field_definition, update_account_field_definition, set_account_field_active, list_admin_audit_entries, log_admin_audit, get_user_for_admin, get_account_field_definition, ensure_user_workspace_schema, update_user_identity, list_broadcast_messages, create_broadcast_message, update_broadcast_message, set_broadcast_message_active, get_broadcast_message, delete_broadcast_message, active_team_for_user, list_active_team_members, list_active_team_invites, create_team_invite, list_assignable_users, audit_retention_enabled, set_admin_setting, cleanup_admin_audit_entries_older_than, get_auth_connection
from database import get_db_connection, initialise_database
from dropdown_values import DROPDOWN_VALUES
from db_compat import using_postgres, current_user_schema, get_connection as get_schema_connection
from orgchart_service import (
    delete_node as delete_orgchart_node,
    get_or_create_org_chart,
    get_org_nodes,
    ordered_insert_index,
    renumber_siblings,
    sibling_nodes,
    upsert_node,
    validate_no_cycles,
)


APP_VERSION = "1.4.1"
APP_RELEASE_DATE = "2026-05-15"
APP_BUILD = "2026-05-15-v1.4.1-outreach-orgchart-fixes"

RELEASE_NOTES = [
    {
        "version": "1.4",
        "release_date": "2026-05-15",
        "title": "Partner activity, contact org charts and outreach scheduling refinement",
        "new": [
            "Added partner activity into PG Progress as a separate partner row when activity has occurred against an account.",
            "Added admin contact archiving for inactive contacts by date range from Admin with CSV export support from reports.",
            "Added editable account contact org charts so customer and partner contacts can be mapped by business organisation, department and reporting relationship.",
            "Added a replacement account Org Chart workspace with draggable contact tiles, relationship drop zones, API persistence and hierarchy connector lines.",
        ],
        "enhanced": [
            "Enhanced Outreach so account partners are clearly identified in the activity selection and only appear when linked to the selected account.",
            "Enhanced create outreach and campaign pages so the Open contact button is compact and only appears after a contact is selected.",
            "Enhanced Outreach Tasks so the contact job title appears on its own row beneath the contact name.",
            "Enhanced outreach activity values so White Paper and Webinar also includes Consensus.",
            "Enhanced outreach outcomes with Webinar Attended and Consensus Viewed.",
            "Enhanced PG Progress so partner activity is labelled clearly against the associated account.",
            "Enhanced PG Progress so the discovery contact cell is limited to company, business/org, department, contact name and job title.",
            "Enhanced account org charts with a single drag-and-drop canvas and connector lines so reporting relationships are visible between managers and direct reports.",
            "Enhanced Outreach task RAG colouring so amber starts on the due day from 00:01 and red starts immediately after the due date and due time expire.",
            "Enhanced PG Progress formatting so only company names and detail labels are bold while row detail values remain regular weight.",
            "Enhanced PG Progress partner rows to show the account, partner company and partner contact names clearly.",
            "Enhanced manual Outreach scheduling so non-working dates and times warn on save and allow the user to confirm or return to the field.",
        ],
        "fixed": [
            "Restored a single PipeFlow logo in the header.",
            "Cleaned PG Progress so the discovery contact cell shows only the person name and job title without extra contact detail clutter.",
            "Cleaned Outreach forms so contact job title appears without email, phone or LinkedIn details.",
            "Renamed the account table action from Build Org Chart to Org Chart.",
        ],
        "sub_releases": [
            {
                "version": "1.4.1",
                "release_date": "2026-05-15",
                "fixed": [
                    "Moved the Outreach edit contact job title display directly beneath the Contact field.",
                    "Fixed the hosted Org Chart page by ensuring the new org chart persistence tables work with the database compatibility layer.",
                    "Removed Closed as a selectable Outreach task status and migrated old Closed values to Completed.",
                    "Hardened workspace security so cross-workspace task reassignment requires explicit account access and storage health no longer displays user email or workspace schema.",
                    "Fixed PG Bible PG Actions mapping so Discovery meeting completed, Exec First and next seven day action notes populate in the May 2026 template.",
                    "Fixed the Insights Dashboard broadcast ticker so longer messages display the full title and message before moving to the next item.",
                    "Fixed the Insights Dashboard broadcast ticker so only one complete broadcast message is visible at a time before moving to the next message.",
                ],
                "enhanced": [
                    "Simplified Outreach edit actions to Save, Complete and Create Follow-Up, and Cancel.",
                    "Updated Complete and Create Follow-Up so it completes the current activity and opens a new pre-populated Outreach activity form.",
                    "Enhanced Org Chart visuals so peer relationships display connector lines as well as manager and direct report relationships.",
                    "Enhanced PG Bible export to use the May 2026 template and map PG Goals, PG Plan and PG Actions from PipeFlow PG Progress data.",
                    "Enhanced browser-side security by using safer session cookie defaults and no-store headers on authenticated app pages.",
                    "Enhanced PG Bible PG Plan and PG Actions mapping to include account business unit or organisation values in the required output cells.",
                    "Enhanced account navigation so selecting an account opens View Account first, with Edit available from the account view.",
                    "Enhanced Outreach activity types by replacing Meeting with Discovery Meeting and NBM Booked.",
                    "Enhanced broadcast management so admins can edit broadcasts in a table and bulk save or delete selected rows.",
                    "Enhanced the Insights Dashboard broadcast ticker so messages roll upward, display for five seconds and continue in a loop.",
                    "Enhanced PG Progress so NBM booked meetings remain visible in next seven day scheduled actions until completed or cancelled.",
                    "Enhanced navigation by moving Release Notes from the main tab row into the header action area beneath User Guide.",
                ],
            },
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
            "Enhanced completed and cancelled outreach tasks so they can no longer be modified or reassigned.",
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
            "Enhanced Outreach filters with a compact status menu for All Open, All Completed, All and individual statuses including Cancelled.",
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
            "Enhanced Outreach so Activity Update is only mandatory when a task is being completed or cancelled.",
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
        "access": "All signed-in users can use the standard navigation. Admin appears only for users with admin permission, and Audit is available inside Admin as an admin-only sub tab.",
        "navigation": [
            "Use the top navigation from left to right as your normal workflow: Dashboard, Outreach Tasks, Accounts, Contacts, Partners, Reports, Profile and Release Notes.",
            "Use the User Guide link in the top right whenever you need help without leaving the application structure.",
            "Use the global search field in the header when you know the account, contact, partner, campaign or outreach text you want to find.",
            "Use Sign Out as the final navigation option when you have finished working.",
        ],
        "steps": [
            "Register or sign in with your PipeFlow profile.",
            "Open Profile and confirm your full name, team, job title and working hours.",
            "Add any non-working date blocks so generated campaigns avoid those days.",
            "Create accounts first, add contacts to those accounts, then create outreach tasks or generate campaigns.",
            "Review Dashboard and Reports regularly to check execution progress and accountability.",
        ],
        "tips": [
            "Your workspace data is private unless you explicitly share an account through Outreach Tasks.",
            "Use the global search field when you know the account, contact, partner or outreach text you are looking for.",
            "If a menu item is missing, it is normally because your profile does not have permission for that function.",
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
            "Use the pipeline target card to see total PG target ACV across your accounts.",
            "Work active outreach tasks directly from the dashboard task table.",
            "Use Execution Insights to decide which account, campaign or sales play needs attention next.",
            "Update task status and due dates as work progresses so the dashboard stays accurate.",
        ],
        "tips": [
            "Untouched accounts are accounts with no active campaign or outreach tasks.",
            "Completed and cancelled work is removed from active execution views by default.",
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
            "Use Account Sharing on the account record to review and revoke access if you own the account.",
        ],
        "tips": [
            "Use business organisation to distinguish large accounts with multiple internal groups.",
            "Keep PG Bible order numeric and unique for your most important accounts.",
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
            "Use contact data to make campaign recommendations more accurate over time.",
            "Keep contact records current when a stakeholder changes role, leaves or becomes more important to the sales play.",
        ],
        "tips": [
            "Accounts must have at least one contact before Campaign Builder can generate a campaign.",
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
            "Use the Share Full Account panel to copy an account package to one or more users and record their access.",
            "Group outreach by account and campaign to understand execution context.",
            "Use the Assigned To dropdown in each row and click Save Assignment to commit task ownership.",
            "Use the compact status filter to show All Open, All Completed, All or specific statuses.",
            "Add an Activity Update before closing or completing an outreach task.",
            "Use Complete and Create Follow-Up when the current task is done but another task is needed.",
        ],
        "tips": [
            "The due date is the Activity Due Date, based on the next action date.",
            "Tasks can only be assigned to users who have access to the related account.",
            "Completed and cancelled outreach is hidden unless you explicitly filter for it.",
            "If a user is missing from the assignment dropdown, check that the account has been shared with them first.",
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
            "Other users' full names are only displayed in Outreach Tasks assignment and share dropdowns.",
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
        "summary": "Review execution data and export account, contact, outreach, task and PG Bible outputs.",
        "navigation": [
            "Open Reports from the main navigation, then select the report type you need.",
            "Use Back to Reports from report pages to return to the report menu.",
            "Use exports when you need to review or share data outside PipeFlow.",
        ],
        "steps": [
            "Open Reports from the top navigation.",
            "Use Account Reports to review account coverage and target values.",
            "Use Contact Reports to review stakeholder coverage.",
            "Use Outreach and Task Reports to review activity volume, outcomes, due dates and ownership.",
            "Export PG Bible when you need the formatted workbook output.",
            "Use filters before exporting when the report supports narrowing by date, account, status or assignee.",
        ],
        "tips": [
            "Reports reflect the same fields used across account, contact, outreach and task views.",
            "PG Bible uses account target and ordering fields configured in the account form.",
            "Task Reports include SLA by assignee so timeliness is measured against the person currently assigned.",
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
        "summary": "Manage users, permissions and broadcasts when signed in as an administrator.",
        "access": "Admin forms are only visible to admin users. Non-admin users will not see Admin in the navigation and cannot access the admin routes.",
        "navigation": [
            "Admin appears near the end of the navigation only for admin users.",
            "Use Admin for user management, role changes, broadcasts and profile administration.",
            "Use the Broadcast Messages sub tab inside Admin to create, pause, edit or delete user messages.",
            "Use the Audit Trail sub tab inside Admin to review administrative and data-change history.",
        ],
        "steps": [
            "Open Admin from the top navigation when available.",
            "Review user profiles and update role, team or email when required.",
            "Deactivate users who should no longer access PipeFlow.",
            "Create broadcast messages with start and stop times for login and dashboard announcements.",
            "Use admin password reset only after confirming the request with the user.",
        ],
        "tips": [
            "Admin actions are recorded in the admin audit trail.",
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
app.config["SECRET_KEY"] = os.environ.get("PIPEFLOW_SECRET_KEY") or secrets.token_hex(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("PIPEFLOW_COOKIE_SECURE", "1" if os.environ.get("RENDER") else "0") == "1"

initialise_auth_database()


@app.after_request
def apply_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    if request.endpoint != "static":
        response.headers.setdefault("Cache-Control", "no-store, max-age=0")
        response.headers.setdefault("Pragma", "no-cache")
    return response


@app.context_processor
def inject_dropdown_values():
    return {
        "dropdown_values": DROPDOWN_VALUES,
        "current_user": current_user(),
        "app_name": "PipeFlow PG Manager",
        "app_version": APP_VERSION,
        "app_release_date": APP_RELEASE_DATE,
        "page_instructions": page_instructions_for_endpoint(request.endpoint),
    }


PAGE_INSTRUCTIONS = {
    "home": {
        "title": "How to Use This Page",
        "items": [
            "Start with the command centre metrics to see what needs attention this week.",
            "Use the task table to update due dates, activity updates and task status without leaving the dashboard.",
            "Review execution insights for suggested next actions across accounts, campaigns and sales plays.",
            "Use the top navigation to move into Outreach Tasks, Accounts, Contacts, Partners, Reports, Profile or Release Notes.",
        ],
    },
    "outreach": {
        "title": "Outreach Tasks Guidance",
        "items": [
            "Only account owners can share accounts, revoke account sharing or see account sharing assignments.",
            "Use the filters to focus active work. All Open excludes Completed and Cancelled records.",
            "Use Save Assignment after changing the assignee. The selected user must already have access to the account.",
            "Open the task to complete it, add a mandatory Activity Update or create a follow-up task.",
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
            "Activity Start Date is when the work begins. Activity Due Date is when the next action must be completed.",
            "Leave Activity Update blank until there is a real update to record.",
        ],
    },
    "edit_outreach": {
        "title": "Edit Outreach Guidance",
        "items": [
            "Add an Activity Update before completing or closing a task.",
            "Save with Completed or Cancelled closes the current task without creating a follow-up.",
            "Complete and Create Follow-Up saves the current task as completed, then opens a new outreach form for the next step.",
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
            "Use reports to review account coverage, contacts, outreach execution, task ownership and PG Bible export readiness.",
            "Exports reflect the current fields used across the application.",
            "PG Bible export requires the template to be available on the server.",
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
            "Review outreach volume, outcomes, campaigns, sales plays and due dates.",
            "Use filters to narrow reporting by account, date range, outcome or activity type.",
            "Compare outcomes to improve future campaign recommendations.",
        ],
    },
    "task_reports": {
        "title": "Task Reports Guidance",
        "items": [
            "Use SLA by Assignee to see who owns active, overdue and completed tasks.",
            "Task timeliness is measured against the current assignee.",
            "Filter by account, status or assignee before exporting.",
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
            "This page is only visible to admin users. Non-admin users do not see Admin in the navigation.",
            "Use user permissions to manage admin access, active users and profile details.",
            "Use broadcasts to publish timed messages on login and the dashboard.",
            "Admin actions are recorded in the admin audit trail.",
        ],
    },
    "admin_users": {
        "title": "Profile Administration Guidance",
        "items": [
            "This admin form is only available to users with admin permission.",
            "Use this page to manage user identity, role and active status.",
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
            "Version changes are only made when the release status is agreed.",
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
            "Completed and Cancelled work is hidden from active views by default.",
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
    public_endpoints = {"login", "register", "forgot_password", "reset_password", "release_notes", "user_guide", "user_guide_section", "storage_health", "static"}
    if request.endpoint in public_endpoints:
        return None

    if not session.get("user_id"):
        return redirect(url_for("login"))

    initialise_database()
    return None





@app.route("/health/version")
def version_health():
    from db_compat import translate_sql
    sample = "datetime(next_action_date || ' ' || IFNULL(next_action_time, '00:00')) < datetime('now', '-1 hour')"
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
        "user_authenticated=true" if session.get("user_id") else "user_authenticated=false",
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
        user = authenticate_user(request.form.get("email", ""), request.form.get("password", ""))
        if user:
            session.clear()
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
            connection.commit()
            connection.close()
            return redirect(url_for("home"))
        error = "Email or password was not recognised."

    return render_template("login.html", error=error, message=message, broadcast_messages=list_broadcast_messages(active_only=True))


@app.route("/forgot-password", methods=("GET", "POST"))
def forgot_password():
    error = ""
    if request.method == "POST":
        email = request.form.get("email", "")
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
    return render_template(
        "admin_permissions.html",
        users=list_users(),
        broadcast_messages=list_broadcast_messages(active_only=False),
        audit_retention_enabled=audit_retention_enabled(),
        message=request.args.get("message", ""),
        error=request.args.get("error", "")
    )


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


@app.route("/admin/broadcasts/add", methods=("POST",))
@admin_required
def admin_add_broadcast():
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
    set_broadcast_message_active(message_id, False)
    return redirect(url_for("admin_users", message="Broadcast message hidden."))


@app.route("/admin/broadcasts/<int:message_id>/reactivate", methods=("POST",))
@admin_required
def admin_reactivate_broadcast(message_id):
    set_broadcast_message_active(message_id, True)
    return redirect(url_for("admin_users", message="Broadcast message restored."))


@app.route("/admin/broadcasts/<int:message_id>/delete", methods=("POST",))
@admin_required
def admin_delete_broadcast(message_id):
    delete_broadcast_message(message_id)
    return redirect(url_for("admin_users", message="Broadcast message deleted."))


@app.route("/admin/broadcasts/bulk", methods=("POST",))
@admin_required
def admin_bulk_broadcasts():
    selected_ids = [
        int(value)
        for value in request.form.getlist("selected_broadcast_ids")
        if str(value).isdigit()
    ]
    action = request.form.get("bulk_action", "save")
    if not selected_ids:
        return redirect(url_for("admin_users", error="Select at least one broadcast message."))

    if action == "delete":
        for message_id in selected_ids:
            delete_broadcast_message(message_id)
        return redirect(url_for("admin_users", message=f"Deleted {len(selected_ids)} broadcast message(s)."))

    errors = []
    saved_count = 0
    for message_id in selected_ids:
        prefix = f"broadcast_{message_id}_"
        error = update_broadcast_message(
            message_id,
            request.form.get(f"{prefix}title", ""),
            request.form.get(f"{prefix}message", ""),
            request.form.get(f"{prefix}severity", "info"),
            request.form.get(f"{prefix}start_at", ""),
            request.form.get(f"{prefix}stop_at", ""),
            bool(request.form.get(f"{prefix}is_active")),
        )
        if error:
            errors.append(f"Broadcast {message_id}: {error}")
        else:
            saved_count += 1

    if errors:
        return redirect(url_for("admin_users", error=" ".join(errors[:3])))
    return redirect(url_for("admin_users", message=f"Saved {saved_count} broadcast message(s)."))


@app.route("/admin/audit-retention", methods=("POST",))
@admin_required
def admin_update_audit_retention():
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
    old_email = user["email"]
    old_name = user["full_name"]
    old_team = user["team"] if "team" in user.keys() and user["team"] else ""
    new_email = request.form.get("email", "")
    new_name = request.form.get("full_name", "")
    new_team = request.form.get("team", "")
    error = update_user_identity(user_id, new_email, new_name, new_team)
    if error:
        return redirect(url_for("admin_users", error=error))

    changes = []
    if old_name != new_name.strip():
        changes.append(f"Name changed from {old_name} to {new_name.strip()}")
    if old_email != new_email.strip().lower():
        changes.append(f"Email changed from {old_email} to {new_email.strip().lower()}")
    if old_team != new_team.strip():
        changes.append(f"Team changed from {old_team or 'Not set'} to {new_team.strip() or 'Not set'}")
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
    if user_id == session.get("user_id"):
        return redirect(url_for("admin_users", error="You cannot change your own admin role."))
    user = get_user_for_admin(user_id)
    old_role = user["role"] if user else "unknown"
    new_role = request.form.get("role", "")
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
        connection.execute("DELETE FROM account_custom_values WHERE account_id = ?", (account_id,))
        connection.execute("DELETE FROM partner_contacts WHERE account_id = ?", (account_id,))
        connection.execute("DELETE FROM outreach WHERE account_id = ?", (account_id,))
        connection.execute("DELETE FROM contacts WHERE account_id = ?", (account_id,))
        connection.execute("DELETE FROM accounts WHERE id = ?", (account_id,))


def delete_contact_records(connection, contact_ids):
    for contact_id in contact_ids:
        contact = connection.execute("SELECT name FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        audit_record_delete(connection, "contact", contact_id, contact["name"] if contact else "")
        connection.execute("DELETE FROM timeline_entries WHERE related_type = 'contact' AND related_id = ?", (contact_id,))
        connection.execute("DELETE FROM outreach WHERE contact_id = ?", (contact_id,))
        connection.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))


def delete_outreach_records(connection, outreach_ids):
    for outreach_id in outreach_ids:
        outreach = connection.execute("SELECT subject FROM outreach WHERE id = ?", (outreach_id,)).fetchone()
        audit_record_delete(connection, "outreach", outreach_id, outreach["subject"] if outreach else "")
        connection.execute("DELETE FROM timeline_entries WHERE related_type = 'outreach' AND related_id = ?", (outreach_id,))
        connection.execute("DELETE FROM outreach WHERE id = ?", (outreach_id,))


def delete_partner_records(connection, partner_ids):
    for partner_id in partner_ids:
        partner = connection.execute("SELECT * FROM partners WHERE id = ?", (partner_id,)).fetchone()
        if not current_user_can_delete_partner(partner):
            continue
        audit_record_delete(connection, "partner", partner_id, partner["partner_name"] if partner else "")
        connection.execute("DELETE FROM account_partners WHERE partner_id = ?", (partner_id,))
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
        if row["outcome"] == "Meeting Booked" or is_meeting_activity_type(activity_type):
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


def available_campaign_time(action_date, preferred_time, profile=None, reserved_slots=None):
    reserved_slots = reserved_slots or set()
    start_time = parse_time_value(profile["work_day_start"] if profile and profile["work_day_start"] else "", "09:00")
    end_time = parse_time_value(profile["work_day_end"] if profile and profile["work_day_end"] else "", "17:00")
    preferred = parse_time_value(preferred_time, "09:00")
    current_dt = datetime.combine(action_date, max(start_time, min(preferred, end_time)))
    end_dt = datetime.combine(action_date, end_time)
    while current_dt <= end_dt:
        slot = (action_date.isoformat(), current_dt.strftime("%H:%M"))
        if slot not in reserved_slots:
            reserved_slots.add(slot)
            return current_dt.strftime("%H:%M")
        current_dt += timedelta(minutes=15)
    fallback = datetime.combine(action_date, start_time)
    slot = (action_date.isoformat(), fallback.strftime("%H:%M"))
    reserved_slots.add(slot)
    return fallback.strftime("%H:%M")


def build_campaign_schedule(campaign_start, campaign_end, total_tasks, times_per_week, templates=None, profile=None, reserved_slots=None, non_working_blocks=None):
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
            template = dict(templates[index % len(templates)])
            if template.get("activity_type") in ("VITO", "Email"):
                template["campaign"] = "Follow-up"
                template["activity_type"] = "Follow-up"
                template["subject_prefix"] = "Follow-up email"
                template["next_action"] = "Send follow-up email"
                template["time"] = template.get("time") or "09:00"
        template["action_date"] = action_date
        template["time"] = available_campaign_time(action_date, template.get("time", "09:00"), profile, reserved_slots)
        template["times_per_week"] = times_per_week
        schedule.append(template)

    return schedule


def build_pg_campaign_steps(pg_week_start):
    return build_campaign_schedule(pg_week_start - timedelta(days=28), pg_week_start - timedelta(days=1), 8, 2)


POSITIVE_OUTCOMES = (
    "Positive Response",
    "Meeting Booked",
    "NBM Booked",
    "Referral Made",
    "Follow-up Required",
)

NEGATIVE_OUTCOMES = (
    "Negative Response",
    "Not Relevant",
)

CLOSED_TASK_STATUSES = (
    "Completed",
    "Cancelled",
)


MEETING_ACTIVITY_TYPES = {
    "Meeting",
    "Meeting Booked",
    "Discovery Meeting",
    "NBM Booked",
}


def is_meeting_activity_type(value):
    return (value or "").strip() in MEETING_ACTIVITY_TYPES


def is_closed_task_status(status):
    return (status or "").strip() in CLOSED_TASK_STATUSES


def score_learning_row(row):
    return (
        (row["meeting_total"] or 0) * 4
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
        combined.append({
            "source": "AI Insight",
            "category": insight.get("type", "Insight"),
            "title": insight.get("title", ""),
            "message": insight.get("message", ""),
            "action": insight.get("message", ""),
            "link": insight.get("link", url_for("home")),
            "priority": insight.get("severity", "medium"),
        })

    for insight in learning_insights:
        combined.append({
            "source": "Campaign Learning",
            "category": insight.get("signal", "Learning"),
            "title": insight.get("title", ""),
            "message": insight.get("message", ""),
            "action": insight.get("action", ""),
            "link": insight.get("link", url_for("campaign_builder")),
            "priority": "learning",
        })

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


def build_learning_insights(connection):
    positive_placeholders = ",".join("?" for _ in POSITIVE_OUTCOMES)
    negative_placeholders = ",".join("?" for _ in NEGATIVE_OUTCOMES)
    learning_select = f"""
        COUNT(outreach.id) AS total,
        SUM(CASE
            WHEN outreach.outcome IN ({positive_placeholders})
              OR outreach.activity_type IN ('Meeting', 'Meeting Booked', 'Discovery Meeting', 'NBM Booked')
            THEN 1 ELSE 0
        END) AS positive_total,
        SUM(CASE
            WHEN outreach.outcome = 'Meeting Booked'
              OR outreach.activity_type IN ('Meeting', 'Meeting Booked', 'Discovery Meeting', 'NBM Booked')
            THEN 1 ELSE 0
        END) AS meeting_total,
        SUM(CASE
            WHEN outreach.outcome IN ({negative_placeholders})
            THEN 1 ELSE 0
        END) AS negative_total,
        SUM(CASE
            WHEN COALESCE(outreach.task_status, '') IN ('Completed', 'Cancelled')
            THEN 1 ELSE 0
        END) AS completed_total,
        SUM(CASE
            WHEN outreach.next_action_date IS NOT NULL
              AND outreach.next_action_date != ''
              AND datetime(
                    outreach.next_action_date || ' ' ||
                    IFNULL(outreach.next_action_time, '00:00')
                  ) < datetime('now', '-1 hour')
              AND COALESCE(outreach.task_status, '') NOT IN ('Completed', 'Cancelled')
            THEN 1 ELSE 0
        END) AS overdue_total
    """
    learning_params = (*POSITIVE_OUTCOMES, *NEGATIVE_OUTCOMES)
    insights = []

    sales_play_rows = add_learning_score(connection.execute(f"""
        SELECT
            outreach.sales_play,
            {learning_select}
        FROM outreach
        WHERE outreach.sales_play IS NOT NULL
          AND outreach.sales_play != ''
        GROUP BY outreach.sales_play
    """, learning_params).fetchall())

    if sales_play_rows:
        sales_play = sales_play_rows[0]
        insights.append({
            "signal": "Sales Play",
            "title": f"{sales_play['sales_play']} is resonating best",
            "message": (
                f"This play has {sales_play['positive_total']} positive signal(s) "
                f"and {sales_play['meeting_total']} meeting(s) from "
                f"{sales_play['total']} touchpoint(s)."
            ),
            "action": "Prioritise this play for contacts with comparable roles, needs or buying context.",
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
        WHERE accounts.account_name IS NOT NULL
          AND outreach.sales_play IS NOT NULL
          AND outreach.sales_play != ''
        GROUP BY accounts.id, accounts.account_name, outreach.sales_play
    """, learning_params).fetchall())

    if account_rows:
        account = account_rows[0]
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
                f"{account['positive_total']} positive signal(s) and "
                f"{account['meeting_total']} meeting(s)."
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

    if contact_category_rows:
        category = contact_category_rows[0]
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
                f"This combination has {category['positive_total']} positive signal(s), "
                f"{category['meeting_total']} meeting(s), and "
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

    if relationship_rows:
        relationship = relationship_rows[0]
        insights.append({
            "signal": "Relationship",
            "title": f"{relationship['sales_play']} is strongest with {relationship['bmc_relationship']} contacts",
            "message": (
                f"The data shows {relationship['positive_total']} positive signal(s) "
                f"from {relationship['total']} touchpoint(s)."
            ),
            "action": "Use this play when a similar relationship type appears in another account.",
            "link": url_for("contacts")
        })

    failure_rows = add_learning_score(connection.execute(f"""
        SELECT
            outreach.sales_play,
            outreach.activity_type,
            {learning_select}
        FROM outreach
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

    outcome_gaps = connection.execute("""
        SELECT COUNT(*) AS total
        FROM outreach
        WHERE sales_play IS NOT NULL
          AND sales_play != ''
          AND (
                outcome IS NULL
             OR outcome = ''
             OR outcome = 'No Response Yet'
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

    return insights[:5]


@app.route("/")
def home():
    connection = get_db_connection()
    try:
        return build_dashboard_response(connection)
    except Exception:
        print("Dashboard failed; fallback rendered.", file=sys.stderr)
        return render_dashboard_fallback()
    finally:
        connection.close()


def render_dashboard_fallback():
    return render_template(
        "index.html",
        this_week_due=0,
        this_week_completed=0,
        this_week_overdue=0,
        this_week_untouched_accounts=0,
        this_week_meetings_booked=0,
        this_week_start="",
        this_week_end="",
        total_accounts=0,
        total_contacts=0,
        total_outreach=0,
        total_pg_target=0,
        meetings_booked=0,
        follow_ups_due=0,
        latest_outreach=[],
        outreach_by_account=[],
        outcome_breakdown=[],
        top_accounts=[],
        needs_attention_accounts=[],
        ai_insights=[{
            "type": "Dashboard Check",
            "severity": "high",
            "title": "Dashboard data needs a refresh",
            "message": "One dashboard query could not be loaded. Other app pages should still be available while this is checked.",
            "link": url_for("reports")
        }],
        learning_insights=[],
        execution_insights=[],
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
    today = datetime.now().date()
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

        if next_action_date and next_action_date < today and not task_closed(row):
            this_week_overdue += 1

        if task_closed(row):
            last_updated_date = parse_dashboard_date(str(row["last_updated"] or "")[:10])
            if last_updated_date and week_start <= last_updated_date <= week_end:
                this_week_completed += 1

        if activity_date and week_start <= activity_date <= week_end:
            if row["outcome"] == "Meeting Booked" or is_meeting_activity_type(row["activity_type"]):
                this_week_meetings_booked += 1

    this_week_untouched_accounts = connection.execute("""
        SELECT COUNT(*)
        FROM accounts
        WHERE NOT EXISTS (
            SELECT 1
            FROM outreach
            WHERE outreach.account_id = accounts.id
              AND COALESCE(outreach.task_status, '') NOT IN ('Completed', 'Cancelled')
              AND (
                    (outreach.sales_play IS NOT NULL AND outreach.sales_play != '')
                 OR (outreach.next_action IS NOT NULL AND outreach.next_action != '')
              )
        )
    """).fetchone()[0]

    meetings_booked = connection.execute("""
        SELECT COUNT(*) FROM outreach
        WHERE outcome = 'Meeting Booked'
           OR activity_type IN ('Meeting', 'Meeting Booked', 'Discovery Meeting', 'NBM Booked')
    """).fetchone()[0]

    follow_ups_due = connection.execute("""
        SELECT COUNT(*) FROM outreach
        WHERE next_action_date IS NOT NULL
          AND next_action_date != ''
          AND date(next_action_date) <= date('now', '+7 days')
          AND COALESCE(task_status, '') NOT IN ('Completed', 'Cancelled')
    """).fetchone()[0]

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

    dashboard_tasks = connection.execute("""
        SELECT outreach.*, accounts.account_name, accounts.account_tier, contacts.name AS contact_name
        FROM outreach
        LEFT JOIN accounts ON outreach.account_id = accounts.id
        LEFT JOIN contacts ON outreach.contact_id = contacts.id
        WHERE outreach.next_action IS NOT NULL
          AND outreach.next_action != ''
          AND outreach.next_action_date IS NOT NULL
          AND outreach.next_action_date != ''
          AND COALESCE(outreach.task_status, '') NOT IN ('Completed', 'Cancelled')
        ORDER BY
            CASE WHEN date(outreach.next_action_date) < date('now') THEN 0 ELSE 1 END,
            outreach.next_action_date ASC,
            outreach.next_action_time ASC
        LIMIT 8
    """).fetchall()

    account_health_rows = connection.execute("""
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
                        outreach.outcome = 'Meeting Booked'
                     OR outreach.activity_type IN ('Meeting', 'Meeting Booked', 'Discovery Meeting', 'NBM Booked')
                  )
            ) AS meeting_count,

            (
                SELECT COUNT(*)
                FROM outreach
                WHERE outreach.account_id = accounts.id
                  AND outreach.next_action_date IS NOT NULL
                  AND outreach.next_action_date != ''
                  AND datetime(
                        outreach.next_action_date || ' ' ||
                        IFNULL(outreach.next_action_time, '00:00')
                      ) < datetime('now', '-1 hour')
                  AND COALESCE(outreach.task_status, '') NOT IN ('Completed', 'Cancelled')
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
    """).fetchall()

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
                "link": url_for("view_account", account_id=account["id"])
            })

        if (account["overdue_followups"] or 0) > 0:
            ai_insights.append({
                "type": "Action Risk",
                "severity": "high",
                "title": f"{account['account_name']} has overdue follow-ups",
                "message": f"{account['overdue_followups']} follow-up(s) are overdue. Review next actions before momentum drops.",
                "link": url_for("view_account", account_id=account["id"])
            })

        if (account["outreach_count"] or 0) > 0 and (account["meeting_count"] or 0) == 0:
            ai_insights.append({
                "type": "Conversion Gap",
                "severity": "medium",
                "title": f"{account['account_name']} has outreach but no meetings",
                "message": "Activity is happening, but no meeting has been booked yet. Consider changing message, route or stakeholder.",
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
                ai_insights.append({
                    "type": "Engagement Route",
                    "severity": "medium",
                    "title": f"Use a sharper route into {account['account_name']}",
                    "message": f"Start with {contact_label}. {recommended_move}",
                    "link": url_for("view_account", account_id=account["id"])
                })

        if (account["partner_count"] or 0) == 0 and (account["outreach_count"] or 0) > 0:
            ai_insights.append({
                "type": "Partner Gap",
                "severity": "medium",
                "title": f"{account['account_name']} has no partner involvement mapped",
                "message": "This account has activity but no partner coverage. Add a relevant partner to test a warmer route in.",
                "link": url_for("view_account", account_id=account["id"])
            })

        if (account["partner_count"] or 0) > 0 and (account["active_partner_count"] or 0) == 0:
            ai_insights.append({
                "type": "Partner Activation",
                "severity": "medium",
                "title": f"{account['account_name']} has partner coverage but no active partner",
                "message": "Partner relationships are mapped, but none are introduced, engaged or active. Pick the best partner and set a next action.",
                "link": url_for("view_account", account_id=account["id"])
            })

        if (account["active_partner_next_action_gaps"] or 0) > 0:
            ai_insights.append({
                "type": "Partner Next Step",
                "severity": "medium",
                "title": f"{account['account_name']} has active partner involvement without a next action",
                "message": f"{account['active_partner_next_action_gaps']} active partner relationship(s) need a clear next action.",
                "link": url_for("view_account", account_id=account["id"])
            })

        if (account["outreach_count"] or 0) >= 3 and (account["meeting_count"] or 0) > 0:
            ai_insights.append({
                "type": "Momentum",
                "severity": "positive",
                "title": f"{account['account_name']} is showing positive engagement",
                "message": "This account has both outreach activity and meetings. Keep progressing next actions.",
                "link": url_for("view_account", account_id=account["id"])
            })

        if (account["active_partner_count"] or 0) >= 2 and (account["meeting_count"] or 0) > 0:
            ai_insights.append({
                "type": "Partner Momentum",
                "severity": "positive",
                "title": f"{account['account_name']} has strong partner coverage",
                "message": "Multiple active partner relationships are mapped alongside meeting activity. Keep partner owners aligned on the next move.",
                "link": url_for("view_account", account_id=account["id"])
            })

        if account["latest_outreach_date"]:
            days_since_outreach = connection.execute("""
                SELECT CAST(julianday('now') - julianday(?) AS INTEGER)
            """, (account["latest_outreach_date"],)).fetchone()[0]

            if days_since_outreach is not None and days_since_outreach >= 14:
                ai_insights.append({
                    "type": "Going Cold",
                    "severity": "medium",
                    "title": f"{account['account_name']} has had no outreach for {days_since_outreach} days",
                    "message": "This account may be going cold. Add a relevant touchpoint or next action.",
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
    learning_insights = build_learning_insights(connection)

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
        build_execution_insights(ai_insights, learning_insights)
    )
    execution_insights = execution_insights[:12]

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


def activity_update_is_valid(value):
    return len((value or "").strip()) >= 5


def status_requires_activity_update(status):
    return is_closed_task_status(status)


def due_rag_class(next_action_date, next_action_time, task_status, now=None):
    if is_closed_task_status(task_status):
        return "rag-closed"
    if not next_action_date:
        return "rag-green"
    try:
        due_day = datetime.strptime(str(next_action_date), "%Y-%m-%d").date()
        due_time = datetime.strptime(str(next_action_time or "23:59"), "%H:%M").time()
    except (TypeError, ValueError):
        return "rag-green"
    now = now or datetime.now()
    due_at = datetime.combine(due_day, due_time)
    amber_start = datetime.combine(due_day, datetime.strptime("00:01", "%H:%M").time())
    red_start = due_at + timedelta(seconds=1)
    if now >= red_start:
        return "rag-red"
    if amber_start <= now <= due_at:
        return "rag-amber"
    return "rag-green"


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


def partner_contact_matches_account(connection, account_id, partner_contact_id):
    if not partner_contact_id:
        return True
    if not account_id:
        return False
    match = connection.execute("""
        SELECT id
        FROM partner_contacts
        WHERE id = ?
          AND account_id = ?
    """, (partner_contact_id, account_id)).fetchone()
    return bool(match)


def outreach_recipient_matches_account(connection, account_id, contact_id, partner_contact_id):
    return (
        contact_matches_account(connection, account_id, contact_id)
        and partner_contact_matches_account(connection, account_id, partner_contact_id)
    )


def partner_contacts_for_outreach(connection):
    return connection.execute("""
        SELECT
            partner_contacts.*,
            partners.partner_name,
            partners.partner_type,
            accounts.account_name
        FROM partner_contacts
        LEFT JOIN partners ON partners.id = partner_contacts.partner_id
        LEFT JOIN accounts ON accounts.id = partner_contacts.account_id
        WHERE partner_contacts.account_id IS NOT NULL
        ORDER BY accounts.account_name, partners.partner_name, partner_contacts.name
    """).fetchall()


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


def account_partner_activity_options(connection):
    return connection.execute("""
        SELECT
            account_partners.account_id,
            account_partners.partner_id,
            account_partners.partner_name,
            partners.partner_type
        FROM account_partners
        LEFT JOIN partners ON partners.id = account_partners.partner_id
        WHERE account_partners.account_id IS NOT NULL
          AND account_partners.partner_name IS NOT NULL
          AND account_partners.partner_name != ''
        ORDER BY account_partners.partner_name
    """).fetchall()


def activity_update_required_message():
    return "Activity Update must be at least 5 characters before a task can be completed or cancelled."


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
              AND COALESCE(status, 'Active') != 'Archived'
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
        pg_plan_rows.append({
            "account_id": account_id,
            "target_number": pg_target_number,
            "colour_index": nbm_colour_index(pg_target_number),
            "sales_play": pg_sales_play,
            "account_name": account["account_name"],
            "business_unit": account["business_unit"] or "",
            "estimated_value": money_value(account["pipeline_target"]),
        })

        legacy_action_update = connection.execute("""
            SELECT *
            FROM pg_action_updates
            WHERE account_id = ?
        """, (account_id,)).fetchone()

        for contact in contacts:
            contact_id = contact["id"]
            latest_contact_activity = connection.execute("""
                SELECT MAX(COALESCE(last_updated, date_created)) AS latest_activity
                FROM outreach
                WHERE account_id = ?
                  AND contact_id = ?
            """, (account_id, contact_id)).fetchone()["latest_activity"]
            scheduled_action_rows = connection.execute("""
                SELECT
                    subject,
                    next_action,
                    next_action_date,
                    next_action_time,
                    activity_date,
                    activity_type,
                    outcome,
                    COALESCE(
                        NULLIF(next_action_date, ''),
                        CASE
                            WHEN activity_type = 'NBM Booked'
                              OR outcome = 'Meeting Booked'
                            THEN NULLIF(activity_date, '')
                            ELSE NULL
                        END
                    ) AS action_due_date
                FROM outreach
                WHERE account_id = ?
                  AND contact_id = ?
                  AND COALESCE(
                        NULLIF(next_action_date, ''),
                        CASE
                            WHEN activity_type = 'NBM Booked'
                              OR outcome = 'Meeting Booked'
                            THEN NULLIF(activity_date, '')
                            ELSE NULL
                        END
                      ) IS NOT NULL
                  AND COALESCE(
                        NULLIF(next_action_date, ''),
                        CASE
                            WHEN activity_type = 'NBM Booked'
                              OR outcome = 'Meeting Booked'
                            THEN NULLIF(activity_date, '')
                            ELSE NULL
                        END
                      ) <= ?
                  AND COALESCE(task_status, '') NOT IN ('Completed', 'Cancelled')
                ORDER BY action_due_date ASC, next_action_time ASC, id DESC
            """, (account_id, contact_id, seven_days_forward)).fetchall()
            if (
                not scheduled_action_rows
                and latest_contact_activity
                and str(latest_contact_activity)[:10] < (datetime.now() - timedelta(days=14)).date().isoformat()
            ):
                continue
            recent_activity_rows = connection.execute("""
                SELECT activity_date, activity_type, subject, next_action, last_updated
                FROM outreach
                WHERE account_id = ?
                  AND contact_id = ?
                  AND last_updated >= ?
                  AND next_action IS NOT NULL
                  AND next_action != ''
                  AND COALESCE(task_status, '') IN ('Completed', 'Cancelled')
                ORDER BY last_updated DESC, id DESC
            """, (account_id, contact_id, seven_days_ago)).fetchall()
            action_update = connection.execute("""
                SELECT *
                FROM pg_action_contact_updates
                WHERE contact_id = ?
            """, (contact_id,)).fetchone()

            next_7_days_actions = []
            for action_row in scheduled_action_rows:
                if action_row["activity_type"] == "NBM Booked" or action_row["outcome"] == "Meeting Booked":
                    subject_parts = [f"NBM Meeting booked: {action_row['subject'] or 'Scheduled meeting'}"]
                else:
                    subject_parts = [action_row["subject"] or "Scheduled action"]
                if action_row["next_action"]:
                    subject_parts.append(action_row["next_action"])
                due_parts = [action_row["action_due_date"] or "", action_row["next_action_time"] or ""]
                next_7_days_actions.append({
                    "subject": " - ".join(subject_parts),
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
                "account_name": account["account_name"],
                "targeted_discovery": contact["name"] or "No contact name",
                "contact_job_title": contact["job_title"] or "",
                "company_name": contact["account_name"] or account["account_name"],
                "business_org": contact["business_unit"] or "",
                "department": contact["org_dept"] or "",
                "completed_discovery_meeting": (
                    action_update["completed_discovery_meeting"]
                    if action_update
                    else (legacy_action_update["completed_discovery_meeting"] if legacy_action_update else "")
                ),
                "exec_first": action_update["exec_first"] if action_update and "exec_first" in action_update.keys() else "",
                "nbm_completed": action_update["nbm_completed"] if action_update and "nbm_completed" in action_update.keys() else "",
                "last_7_days_activity_entries": last_7_days_activity_entries,
                "next_7_days_actions": next_7_days_actions,
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
                partner_contacts.notes AS partner_notes,
                partner_contacts.last_updated AS partner_last_updated
            FROM account_partners
            LEFT JOIN partners ON partners.id = account_partners.partner_id
            LEFT JOIN partner_contacts
              ON partner_contacts.partner_id = account_partners.partner_id
             AND partner_contacts.account_id = account_partners.account_id
            LEFT JOIN outreach
              ON outreach.account_id = account_partners.account_id
             AND (
                    outreach.activity_type = ('Partner: ' || account_partners.partner_name)
                 OR outreach.partner_contact_id = partner_contacts.id
             )
            WHERE account_partners.account_id = ?
            ORDER BY account_partners.partner_name, partner_contacts.name, outreach.last_updated DESC
        """, (account_id,)).fetchall()
        partner_activity_entries = []
        partner_scheduled_actions = []
        seen_partner_entries = set()
        partner_names = []
        partner_contact_names = []
        for row in partner_activity_rows:
            partner_name = row["partner_name"] or "Partner"
            partner_contact_name = row["partner_contact_name"] or "Partner contact"
            if partner_name and partner_name not in partner_names:
                partner_names.append(partner_name)
            if partner_contact_name and partner_contact_name not in partner_contact_names:
                partner_contact_names.append(partner_contact_name)
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
                    subject_parts = [row["subject"] or f"Partner activity - {partner_name}"]
                    if row["next_action"]:
                        subject_parts.append(row["next_action"])
                    partner_scheduled_actions.append({
                        "subject": " - ".join(subject_parts),
                        "due": " ".join(part for part in due_parts if part),
                    })
        if partner_activity_entries or partner_scheduled_actions:
            pg_action_rows.append({
                "is_partner_row": True,
                "account_id": account_id,
                "contact_id": f"partner_{account_id}",
                "target_number": pg_target_number,
                "colour_index": nbm_colour_index(pg_target_number),
                "account_name": account["account_name"],
                "targeted_discovery": ", ".join(partner_contact_names) or "Partner contact",
                "contact_job_title": "Partner activity",
                "company_name": account["account_name"],
                "business_org": "Partner activity",
                "department": ", ".join(partner_names) or "Partner",
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

    account_rows = connection.execute("""
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
                        outreach.outcome = 'Meeting Booked'
                     OR outreach.activity_type IN ('Meeting', 'Meeting Booked', 'Discovery Meeting', 'NBM Booked')
                  )
            ) AS meeting_count,

            (
                SELECT COUNT(*)
                FROM outreach
                WHERE outreach.account_id = accounts.id
                  AND outreach.next_action_date IS NOT NULL
                  AND outreach.next_action_date != ''
                  AND datetime(
                        outreach.next_action_date || ' ' ||
                        IFNULL(outreach.next_action_time, '00:00')
                      ) < datetime('now', '-1 hour')
                  AND COALESCE(outreach.task_status, '') NOT IN ('Completed', 'Cancelled')
            ) AS overdue_followups,

            (
                SELECT MAX(outreach.activity_date)
                FROM outreach
                WHERE outreach.account_id = accounts.id
            ) AS latest_outreach_date

        FROM accounts
        ORDER BY accounts.account_name
    """).fetchall()

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
            account_partners.*,
            accounts.account_name,
            accounts.industry,
            accounts.country,
            accounts.city
        FROM account_partners
        LEFT JOIN accounts ON account_partners.account_id = accounts.id
        WHERE account_partners.partner_id = ?
        ORDER BY accounts.account_name
    """, (partner_id,)).fetchall()

    partner_contacts = connection.execute("""
        SELECT
            partner_contacts.*,
            accounts.account_name
        FROM partner_contacts
        LEFT JOIN accounts ON partner_contacts.account_id = accounts.id
        WHERE partner_contacts.partner_id = ?
        ORDER BY accounts.account_name, partner_contacts.name
    """, (partner_id,)).fetchall()

    partner_contact_count = connection.execute("""
        SELECT COUNT(*)
        FROM partner_contacts
        WHERE partner_id = ?
    """, (partner_id,)).fetchone()[0]

    partner_account_count = connection.execute("""
        SELECT COUNT(*)
        FROM account_partners
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
            request.form.get("account_id") or None,
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
        partner_row = connection.execute("SELECT partner_name FROM partners WHERE id = ?", (partner_id,)).fetchone()
        audit_record_create(connection, "partner_contact", contact_id, {
            "partner_id": partner_id,
            "name": contact_name,
            "job_title": request.form.get("job_title"),
            "partner_contact_role": request.form.get("partner_contact_role"),
            "coverage_area": request.form.get("coverage_area"),
            "account_id": request.form.get("account_id") or None,
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
        new_values = {
            "name": request.form.get("name"),
            "job_title": request.form.get("job_title"),
            "coverage_area": request.form.get("coverage_area"),
            "account_id": request.form.get("account_id") or None,
            "relationship_owner": request.form.get("relationship_owner"),
            "email": request.form.get("email"),
            "phone": request.form.get("phone"),
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
            new_values["location"],
            new_values["linkedin"],
            new_values["relationship_status"],
            new_values["next_action"],
            new_values["notes"],
            contact_id,
            partner_id,
        ))
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
        owner = current_user_owner_payload()
        cursor = connection.execute("""
            INSERT INTO accounts
            (account_name, pg_bible_order, account_tier, industry, business_unit, country, city, website, pipeline_target, nbm_target, sales_play, owner_user_id, owner_name, owner_email, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request.form.get("account_name"),
            request.form.get("pg_bible_order") or None,
            request.form.get("account_tier"),
            request.form.get("industry"),
            request.form.get("business_unit"),
            request.form.get("country"),
            request.form.get("city"),
            request.form.get("website"),
            request.form.get("pipeline_target"),
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
            "pipeline_target": request.form.get("pipeline_target"),
            "nbm_target": request.form.get("nbm_target"),
            "sales_play": request.form.get("sales_play"),
            "owner_name": owner["owner_name"],
            "notes": request.form.get("notes"),
        })
        save_account_custom_values(connection, account_id, custom_fields, request.form)
        connection.commit()
        connection.close()
        return redirect(url_for("accounts"))

    return render_template("add_account.html", custom_fields=custom_fields)


@app.route("/accounts/<int:account_id>")
def view_account(account_id):
    connection = get_db_connection()

    account = connection.execute(
        "SELECT * FROM accounts WHERE id = ?",
        (account_id,)
    ).fetchone()

    account_stats = connection.execute("""
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
                        outreach.outcome = 'Meeting Booked'
                     OR outreach.activity_type IN ('Meeting', 'Meeting Booked', 'Discovery Meeting', 'NBM Booked')
                  )
            ) AS meeting_count,

            (
                SELECT COUNT(*)
                FROM outreach
                WHERE outreach.account_id = accounts.id
                  AND outreach.next_action_date IS NOT NULL
                  AND outreach.next_action_date != ''
                  AND datetime(
                        outreach.next_action_date || ' ' ||
                        IFNULL(outreach.next_action_time, '00:00')
                      ) < datetime('now', '-1 hour')
                  AND COALESCE(outreach.task_status, '') NOT IN ('Completed', 'Cancelled')
            ) AS overdue_followups,

            (
                SELECT MAX(outreach.activity_date)
                FROM outreach
                WHERE outreach.account_id = accounts.id
            ) AS latest_outreach_date

        FROM accounts
        WHERE accounts.id = ?
    """, (account_id,)).fetchone()

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

        connection.commit()

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


def orgchart_contacts_for_account(connection, account_id):
    return connection.execute("""
        SELECT
            id,
            name,
            job_title,
            COALESCE(NULLIF(org_dept, ''), '') AS org_dept
        FROM contacts
        WHERE account_id = ?
          AND COALESCE(status, 'Active') != 'Archived'
        ORDER BY COALESCE(NULLIF(org_dept, ''), 'Unmapped'), name
    """, (account_id,)).fetchall()


def orgchart_contact_ids(connection, account_id):
    return {row["id"] for row in orgchart_contacts_for_account(connection, account_id)}


def orgchart_json_payload(connection, account_id):
    account = connection.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if not account:
        return None
    chart = get_or_create_org_chart(connection, account_id)
    contacts = orgchart_contacts_for_account(connection, account_id)
    nodes = get_org_nodes(connection, chart["id"])
    return {
        "account": {
            "id": account["id"],
            "account_name": account["account_name"],
        },
        "contacts": [
            {
                "id": contact["id"],
                "name": contact["name"] or "Unknown contact",
                "job_title": contact["job_title"] or "Job title not set",
                "org_dept": contact["org_dept"] or "",
            }
            for contact in contacts
        ],
        "nodes": [
            {
                "contact_id": node["contact_id"],
                "parent_contact_id": node["parent_contact_id"],
                "sort_index": node["sort_index"] or 0,
            }
            for node in nodes
        ],
        "layout_prefs": chart["layout_prefs"] or "{}",
    }


def orgchart_target_parent(connection, org_chart_id, target_contact_id, placement):
    if not target_contact_id:
        return None, 0
    target_node = connection.execute("""
        SELECT *
        FROM org_chart_nodes
        WHERE org_chart_id = ?
          AND contact_id = ?
    """, (org_chart_id, target_contact_id)).fetchone()
    if not target_node:
        return None, 0
    if placement == "employee":
        siblings = sibling_nodes(connection, org_chart_id, target_contact_id)
        return target_contact_id, len(siblings)
    if placement in ("peerLeft", "peerRight"):
        parent_contact_id = target_node["parent_contact_id"]
        siblings = sibling_nodes(connection, org_chart_id, parent_contact_id)
        return parent_contact_id, ordered_insert_index(siblings, target_contact_id, placement)
    if placement == "manager":
        parent_contact_id = target_node["parent_contact_id"]
        siblings = sibling_nodes(connection, org_chart_id, parent_contact_id)
        return parent_contact_id, ordered_insert_index(siblings, target_contact_id, "peerLeft")
    return None, 0


def orgchart_move_contact(connection, account_id, org_chart_id, contact_id, target_contact_id, placement):
    valid_contact_ids = orgchart_contact_ids(connection, account_id)
    if contact_id not in valid_contact_ids:
        raise ValueError("That contact does not belong to this account.")
    if target_contact_id and target_contact_id not in valid_contact_ids:
        raise ValueError("The target contact does not belong to this account.")

    existing_nodes = get_org_nodes(connection, org_chart_id)
    if placement == "manager" and target_contact_id:
        validate_no_cycles(existing_nodes, target_contact_id, contact_id)
        parent_contact_id, sort_index = orgchart_target_parent(connection, org_chart_id, target_contact_id, placement)
        upsert_node(connection, org_chart_id, contact_id, parent_contact_id, sort_index)
        upsert_node(connection, org_chart_id, target_contact_id, contact_id, 0)
        renumber_siblings(connection, org_chart_id, parent_contact_id, contact_id, sort_index)
        return

    parent_contact_id, sort_index = orgchart_target_parent(connection, org_chart_id, target_contact_id, placement)
    validate_no_cycles(existing_nodes, contact_id, parent_contact_id)
    upsert_node(connection, org_chart_id, contact_id, parent_contact_id, sort_index)


@app.route("/accounts/<int:account_id>/orgchart")
def account_orgchart(account_id):
    connection = get_db_connection()
    account = connection.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if not account:
        connection.close()
        return redirect(url_for("accounts"))
    payload = orgchart_json_payload(connection, account_id)
    connection.commit()
    connection.close()
    return render_template(
        "org_chart.html",
        account=account,
        initial_orgchart=payload,
        message=request.args.get("message", ""),
        error=request.args.get("error", ""),
    )


@app.route("/api/accounts/<int:account_id>/orgchart")
def api_account_orgchart(account_id):
    connection = get_db_connection()
    payload = orgchart_json_payload(connection, account_id)
    connection.commit()
    connection.close()
    if payload is None:
        return jsonify({"error": "Account not found"}), 404
    return jsonify(payload)


@app.route("/api/accounts/<int:account_id>/orgchart/nodes", methods=("POST",))
def api_account_orgchart_nodes(account_id):
    connection = get_db_connection()
    account = connection.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if not account:
        connection.close()
        return jsonify({"error": "Account not found"}), 404
    chart = get_or_create_org_chart(connection, account_id)
    payload = request.get_json(silent=True) or {}
    operation = payload.get("operation", "")
    try:
        if operation in ("add", "move"):
            raw_contact_id = payload.get("contact_id") or payload.get("dragged_contact_id")
            contact_id = int(raw_contact_id)
            target_contact_id = payload.get("target_contact_id")
            target_contact_id = int(target_contact_id) if target_contact_id else None
            placement = payload.get("placement") or "employee"
            orgchart_move_contact(connection, account_id, chart["id"], contact_id, target_contact_id, placement)
            add_timeline_entry(
                connection,
                "account",
                account_id,
                "Org Chart",
                "Org chart hierarchy updated.",
                audit_actor()["name"],
            )
        elif operation == "delete":
            contact_id = int(payload.get("contact_id"))
            mode = payload.get("mode") or "promote_children"
            if mode not in ("delete_subtree", "promote_children"):
                mode = "promote_children"
            delete_orgchart_node(connection, chart["id"], contact_id, mode)
            add_timeline_entry(
                connection,
                "account",
                account_id,
                "Org Chart",
                "Org chart contact removed.",
                audit_actor()["name"],
            )
        else:
            raise ValueError("Unsupported org chart operation.")
        connection.commit()
        response_payload = orgchart_json_payload(connection, account_id)
    except (TypeError, ValueError) as exc:
        if hasattr(connection, "rollback"):
            connection.rollback()
        connection.close()
        return jsonify({"error": str(exc)}), 400
    connection.close()
    return jsonify(response_payload)


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
        FROM partner_contacts
        LEFT JOIN partners ON partners.id = partner_contacts.partner_id
        WHERE partner_contacts.account_id = ?
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


def save_org_chart_node_position(connection, chart_id, node_id, relationship, related_node_id, visual_level=None, sort_order=None):
    relationship = normalise_org_chart_relationship(relationship)
    related_node_id_int = parse_optional_int(related_node_id)
    visual_level_int = parse_optional_int(visual_level)
    sort_order_int = parse_optional_int(sort_order)
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
            last_updated = CURRENT_TIMESTAMP
        WHERE chart_id = ?
          AND id = ?
    """, (manager_node_id, relationship, related_node_id_int, visual_level_int, sort_order_int, chart_id, node_id))
    if relationship == "above" and related_node_id_int:
        apply_org_chart_above_relationship(connection, chart_id, node_id, related_node_id_int)
    return {
        "manager_node_id": manager_node_id,
        "relationship_type": relationship,
        "related_node_id": related_node_id_int,
        "visual_level": visual_level_int,
        "sort_order": sort_order_int,
    }


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
    chart_roots = []
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
                "manager_node_id": row["manager_node_id"],
                "relationship_type": row["relationship_type"] if "relationship_type" in row.keys() else "with",
                "related_node_id": row["related_node_id"] if "related_node_id" in row.keys() else None,
                "visual_level": row["visual_level"] if "visual_level" in row.keys() else 0,
                "sort_order": row["sort_order"] if "sort_order" in row.keys() else None,
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
                chart_roots.append(node)
                display_group = org_chart_display_group(node, node_lookup)
                roots_by_group.setdefault(display_group or "Organisation Chart", []).append(node)
        roots_by_group = dict(sorted(
            roots_by_group.items(),
            key=lambda item: (item[0] or "").casefold(),
        ))
        for people in roots_by_group.values():
            sort_org_chart_nodes(people)
        sort_org_chart_nodes(chart_roots)
        sort_org_chart_nodes(unmapped)
    used_people = org_chart_existing_people(connection, active_chart["id"]) if active_chart else set()
    available_people = [option for option in person_options if option["value"] not in used_people]
    return {
        "charts": charts,
        "active_chart": active_chart,
        "person_options": person_options,
        "available_people": available_people,
        "chart_nodes": chart_nodes,
        "chart_roots": chart_roots,
        "roots_by_group": roots_by_group,
        "unmapped": unmapped,
    }


@app.route("/accounts/<int:account_id>/org-chart")
def account_org_chart(account_id):
    connection = get_db_connection()
    account = connection.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if not account:
        connection.close()
        return redirect(url_for("accounts"))
    context = org_chart_context(connection, account, request.args.get("chart_id"))
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
    try:
        for action in actions:
            if not isinstance(action, dict):
                continue
            relationship = normalise_org_chart_relationship(action.get("relationship"))
            related_node_id = action.get("related_node_id") or None
            manager_node_id = action.get("manager_node_id") or None
            if manager_node_id:
                relationship = "under"
                related_node_id = manager_node_id
            visual_level = action.get("visual_level")
            sort_order = action.get("sort_order")
            node_id = action.get("node_id")
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
                new_values = save_org_chart_node_position(connection, chart_id, node_id, relationship, related_node_id, visual_level, sort_order)
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
                new_values = save_org_chart_node_position(connection, chart_id, existing_node["id"], relationship, related_node_id, visual_level, sort_order)
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
                    }
                )
                saved_count += 1
                continue

            visual_level_int = parse_optional_int(visual_level)
            sort_order_int = parse_optional_int(sort_order)
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
                    sort_order
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ))
            new_node_id = cursor.lastrowid
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
        cursor = connection.execute("""
            INSERT INTO contacts (
                account_id, category, name, job_title, org_dept, responsibilities,
                email, phone, location, linkedin, bmc_relationship, characteristics,
                background, personal_interests, personal_win, education,
                social_media, additional_notes, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request.form.get("account_id"),
            request.form.get("category"),
            request.form.get("name"),
            request.form.get("job_title"),
            request.form.get("org_dept"),
            request.form.get("responsibilities"),
            request.form.get("email"),
            request.form.get("phone"),
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
            "phone": request.form.get("phone"),
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
        new_values = {
            "account_id": request.form.get("account_id"),
            "category": request.form.get("category"),
            "name": request.form.get("name"),
            "job_title": request.form.get("job_title"),
            "org_dept": request.form.get("org_dept"),
            "responsibilities": request.form.get("responsibilities"),
            "email": request.form.get("email"),
            "phone": request.form.get("phone"),
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
            "name": "Name",
            "job_title": "Job title",
            "org_dept": "Org / Dept",
            "responsibilities": "Responsibilities",
            "email": "Email",
            "phone": "Phone",
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
                name = ?,
                job_title = ?,
                org_dept = ?,
                responsibilities = ?,
                email = ?,
                phone = ?,
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
            new_values["name"],
            new_values["job_title"],
            new_values["org_dept"],
            new_values["responsibilities"],
            new_values["email"],
            new_values["phone"],
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

        connection.commit()
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
    selected_statuses = request.args.getlist("task_status")
    if not selected_statuses:
        selected_statuses = ["All Open"]
    closed_statuses = ["Completed", "Cancelled"]

    connection = get_db_connection()

    query = """
        SELECT
            outreach.*,
            accounts.account_name,
            accounts.account_tier,
            COALESCE(contacts.name, partner_contacts.name) AS contact_name,
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

    if "All" in selected_statuses:
        pass
    elif "All Completed" in selected_statuses:
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
            prefill = {
                "account_id": source["account_id"],
                "contact_id": f"partner_contact:{source['partner_contact_id']}" if source["partner_contact_id"] else source["contact_id"],
                "sales_play": source["sales_play"] or source["campaign"] or "",
                "notes": f"Follow-up task from completed outreach #{source['id']}.",
            }

    if request.method == "POST":
        prefill = dict(request.form)
        requested_status = request.form.get("task_status", "Not Started")
        contact_id, partner_contact_id = parse_outreach_contact_selection(request.form.get("contact_id"))
        if not fy_quarter_are_valid(request.form.get("fy"), request.form.get("quarter")):
            error = fy_quarter_required_message()
        elif not outreach_recipient_matches_account(connection, request.form.get("account_id"), contact_id, partner_contact_id):
            error = "Select a contact or partner contact that belongs to the selected account."
        elif status_requires_activity_update(requested_status) and not activity_update_is_valid(request.form.get("next_action")):
            error = activity_update_required_message()
        else:
            sales_play_value = request.form.get("sales_play")
            cursor = connection.execute("""
                INSERT INTO outreach (
                    fy, quarter, campaign, sales_play, account_id, contact_id, partner_contact_id, activity_type,
                    activity_date, activity_time, subject, notes, outcome,
                    next_action, next_action_date, next_action_time,
                    task_status, assigned_to
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                request.form.get("outcome"),
                request.form.get("next_action"),
                request.form.get("next_action_date"),
                request.form.get("next_action_time"),
                request.form.get("task_status", "Not Started"),
                request.form.get("assigned_to", "")
            ))
            outreach_id = cursor.lastrowid
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
                "outcome": request.form.get("outcome"),
                "next_action": request.form.get("next_action"),
                "next_action_date": request.form.get("next_action_date"),
                "next_action_time": request.form.get("next_action_time"),
                "task_status": request.form.get("task_status", "Not Started"),
                "assigned_to": request.form.get("assigned_to", ""),
            })

            connection.commit()
            connection.close()

            return redirect(url_for("outreach"))

    accounts = connection.execute("SELECT * FROM accounts ORDER BY account_name").fetchall()

    contacts = connection.execute("""
        SELECT contacts.*, accounts.account_name, accounts.account_tier
        FROM contacts
        LEFT JOIN accounts ON contacts.account_id = accounts.id
        WHERE COALESCE(contacts.status, 'Active') = 'Active'
        ORDER BY contacts.name
    """).fetchall()
    sales_play_rows = account_sales_play_options(connection)
    partner_activity_options = account_partner_activity_options(connection)
    partner_contacts = partner_contacts_for_outreach(connection)

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
                assigned_to = request.form.get("assigned_to", "")
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
                      AND COALESCE(task_status, '') NOT IN ('Completed', 'Cancelled')
                """).fetchall()
                reserved_slots = {
                    (row["next_action_date"], row["next_action_time"] or "09:00")
                    for row in reserved_rows
                    if row["next_action_date"]
                }

                for contact in contacts:
                    for step in build_campaign_schedule(
                        campaign_start,
                        campaign_end,
                        total_tasks,
                        times_per_week,
                        schedule_templates,
                        profile=profile,
                        reserved_slots=reserved_slots,
                        non_working_blocks=non_working_blocks
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
                                "No Response Yet",
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

    connection.close()

    return render_template(
        "view_outreach.html",
        outreach_item=outreach_item,
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
    connection = get_db_connection()
    delete_outreach_records(connection, [outreach_id])
    connection.commit()
    connection.close()

    return redirect(url_for("outreach"))


@app.route("/outreach/bulk-delete", methods=("POST",))
def bulk_delete_outreach():
    outreach_ids = selected_record_ids()
    if outreach_ids:
        connection = get_db_connection()
        delete_outreach_records(connection, outreach_ids)
        connection.commit()
        connection.close()
    return redirect(url_for("outreach"))


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

    accounts = connection.execute(
        "SELECT * FROM accounts ORDER BY account_name"
    ).fetchall()

    contacts = connection.execute("""
        SELECT contacts.*, accounts.account_name
        FROM contacts
        LEFT JOIN accounts ON contacts.account_id = accounts.id
        WHERE COALESCE(contacts.status, 'Active') = 'Active'
           OR contacts.id = ?
        ORDER BY contacts.name
    """, (outreach_item["contact_id"],)).fetchall()
    sales_play_rows = account_sales_play_options(connection)
    partner_activity_options = account_partner_activity_options(connection)
    partner_contacts = partner_contacts_for_outreach(connection)

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
        if is_closed_task_status(outreach_item["task_status"]):
            connection.close()
            return redirect(url_for("outreach", error="Completed and cancelled tasks cannot be modified."))
        submit_action = request.form.get("submit_action", "save")
        sales_play_value = request.form.get("sales_play")
        contact_id, partner_contact_id = parse_outreach_contact_selection(request.form.get("contact_id"))
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
            "outcome": request.form.get("outcome"),
            "next_action": request.form.get("next_action"),
            "next_action_date": request.form.get("next_action_date"),
            "next_action_time": request.form.get("next_action_time"),
            "task_status": request.form.get("task_status", "Not Started"),
            "assigned_to": request.form.get("assigned_to", "")
        }
        follow_on_requested = submit_action == "complete_and_follow"

        if submit_action == "complete_and_follow":
            new_values["task_status"] = "Completed"
            new_values["next_action_date"] = ""
            new_values["next_action_time"] = ""

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
                error=error
            )

        if not outreach_recipient_matches_account(connection, new_values["account_id"], new_values["contact_id"], new_values["partner_contact_id"]):
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
                error=error
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
                error=error
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
            "next_action": "Activity update",
            "next_action_date": "Activity due date",
            "next_action_time": "Activity due time",
            "task_status": "Task status",
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
                next_action = ?,
                next_action_date = ?,
                next_action_time = ?,
                task_status = ?,
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
            new_values["next_action"],
            new_values["next_action_date"],
            new_values["next_action_time"],
            new_values["task_status"],
            new_values["assigned_to"],
            outreach_id
        ))

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
        error=error
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


def account_access_user_ids(connection, account, include_current_user=True):
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
    if include_current_user and current:
        allowed_user_ids.add(str(current["id"]))
    return allowed_user_ids


def assignee_has_account_access(connection, account, assigned_to_user_id):
    if not assigned_to_user_id:
        return True
    return str(assigned_to_user_id) in account_access_user_ids(connection, account)


def current_user_has_workspace_account_access(connection, account, workspace_schema):
    user = current_user()
    if not user or not account:
        return False
    if using_postgres() and workspace_schema == current_user_schema():
        return True
    owner = account_owner_payload(account)
    if owner["owner_user_id"] and str(owner["owner_user_id"]) == str(user["id"]):
        return True
    share = connection.execute("""
        SELECT id
        FROM account_shared_users
        WHERE account_id = ?
          AND user_id = ?
    """, (account["id"], user["id"])).fetchone()
    return bool(share)


def known_user_workspace_schemas():
    schemas = {current_user_schema()} if using_postgres() else {""}
    for assignable_user in list_assignable_users():
        if "workspace_schema" in assignable_user.keys() and assignable_user["workspace_schema"]:
            schemas.add(assignable_user["workspace_schema"])
    return schemas


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
            ["account_name", "pg_bible_order", "account_tier", "industry", "business_unit", "country", "city", "website", "pipeline_target", "owner_user_id", "owner_name", "owner_email", "notes"],
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
                      AND COALESCE(outreach.task_status, '') NOT IN ('Completed', 'Cancelled')
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
              AND COALESCE(outreach.task_status, '') NOT IN ('Completed', 'Cancelled')
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
    return_to = request.form.get("return_to") or url_for("outreach")
    if not target_user_ids:
        separator = "&" if "?" in return_to else "?"
        return redirect(f"{return_to}{separator}{urlencode({'error': 'Select at least one user before sharing the account.'})}")
    source_connection = get_db_connection()
    account = source_connection.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if not account or not current_user_owns_account(account):
        source_connection.close()
        separator = "&" if "?" in return_to else "?"
        return redirect(f"{return_to}{separator}{urlencode({'error': 'Only the account owner can share this account.'})}")
    target_members = [
        member for member in assignable_users
        if str(member["id"]) in target_user_ids
           and member["workspace_schema"]
           and (not user or str(member["id"]) != str(user["id"]))
    ]
    if not target_members:
        source_connection.close()
        separator = "&" if "?" in return_to else "?"
        return redirect(f"{return_to}{separator}{urlencode({'error': 'Select at least one valid user other than yourself.'})}")
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
    separator = "&" if "?" in return_to else "?"
    if errors and not shared_count:
        return redirect(f"{return_to}{separator}{urlencode({'error': errors[0]})}")
    if errors:
        return redirect(f"{return_to}{separator}{urlencode({'message': f'Account shared with {shared_count} user(s). Some shares could not be completed.'})}")
    return redirect(f"{return_to}{separator}{urlencode({'message': f'Full account shared with {shared_count} user(s).'})}")


@app.route("/team-outreach/account-share/<int:share_id>/revoke", methods=("POST",))
def revoke_account_share_from_outreach(share_id):
    user = current_user()
    return_to = request.form.get("return_to") or url_for("outreach")
    connection = get_db_connection()
    share = connection.execute("""
        SELECT account_shared_users.*, accounts.account_name, accounts.owner_user_id, accounts.owner_name, accounts.owner_email
        FROM account_shared_users
        JOIN accounts ON accounts.id = account_shared_users.account_id
        WHERE account_shared_users.id = ?
    """, (share_id,)).fetchone()
    if not share:
        connection.close()
        separator = "&" if "?" in return_to else "?"
        return redirect(f"{return_to}{separator}{urlencode({'error': 'The selected sharing permission could not be found.'})}")

    owner = account_owner_payload(share)
    if user and owner["owner_user_id"] and str(owner["owner_user_id"]) != str(user["id"]):
        connection.close()
        separator = "&" if "?" in return_to else "?"
        return redirect(f"{return_to}{separator}{urlencode({'error': 'Only the account owner can revoke account sharing permissions.'})}")

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
    separator = "&" if "?" in return_to else "?"
    return redirect(f"{return_to}{separator}{urlencode({'message': 'Account sharing permission revoked and assigned tasks returned to the account owner.'})}")


@app.route("/team-outreach/reassign", methods=("POST",))
def reassign_team_outreach():
    user = current_user()
    assignable_users = list_assignable_users()
    allowed_schemas = known_user_workspace_schemas()
    allowed_user_ids = {str(member["id"]) for member in assignable_users}
    workspace_schema = request.form.get("workspace_schema")
    outreach_id = request.form.get("outreach_id")
    assigned_to_user_id = request.form.get("assigned_to_user_id", "")
    assigned_member = assignable_user_by_id(assigned_to_user_id) if assigned_to_user_id else None
    assigned_to = assigned_member["full_name"] if assigned_member else ""
    return_to = request.form.get("return_to") or request.referrer or url_for("outreach")
    if workspace_schema not in allowed_schemas or (assigned_to_user_id and assigned_to_user_id not in allowed_user_ids):
        return redirect(return_to)
    connection = get_schema_connection(schema=workspace_schema) if using_postgres() else get_db_connection()
    outreach_item = connection.execute("SELECT * FROM outreach WHERE id = ?", (outreach_id,)).fetchone()
    if outreach_item:
        if is_closed_task_status(outreach_item["task_status"]):
            connection.close()
            return redirect(url_for("outreach", error="Completed and cancelled tasks cannot be reassigned."))
        account = connection.execute("SELECT * FROM accounts WHERE id = ?", (outreach_item["account_id"],)).fetchone()
        if not current_user_has_workspace_account_access(connection, account, workspace_schema):
            connection.close()
            return redirect(url_for(
                "outreach",
                error="You do not have permission to update this account or task."
            ))
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
    return_target = request.form.get("return_to") or request.referrer or url_for("home")
    if not outreach_item:
        connection.close()
        return redirect(return_target)
    if is_closed_task_status(outreach_item["task_status"]):
        connection.close()
        return redirect(return_target)

    new_values = {
        "outcome": request.form.get("outcome"),
        "task_status": request.form.get("task_status", "Not Started"),
        "next_action": request.form.get("next_action"),
        "next_action_date": request.form.get("next_action_date"),
        "next_action_time": request.form.get("next_action_time"),
        "notes": outreach_item["notes"] or "",
    }
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
            last_updated = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            new_values["outcome"],
            new_values["task_status"],
            new_values["next_action"],
            new_values["next_action_date"],
            new_values["next_action_time"],
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
    return_target = request.form.get("return_to") or request.referrer or url_for("home")
    if not outreach_item:
        connection.close()
        return redirect(return_target)

    activity_update = (request.form.get("next_action") or "").strip()
    if not activity_update:
        connection.close()
        return redirect(return_target)

    outcome = request.form.get("outcome") or outreach_item["outcome"] or "Follow-up Required"
    connection.execute(
        """
        UPDATE outreach
        SET task_status = 'Completed',
            outcome = ?,
            next_action = ?,
            last_updated = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (outcome, activity_update, outreach_id),
    )
    audit_record_update(connection, "outreach", outreach_id, outreach_item, {
        "task_status": "Completed",
        "outcome": outcome,
        "next_action": activity_update,
    }, {
        "task_status": "Task status",
        "outcome": "Outcome",
        "next_action": "Activity update",
    })
    add_timeline_entry(
        connection,
        "outreach",
        outreach_id,
        "Task Completed",
        f"Task marked completed from dashboard with outcome: {outcome}",
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

    return render_template(
        "profile.html",
        profile=profile_record,
        non_working_blocks=non_working_blocks,
        message=message,
        error=error
    )


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
            account_partners.involvement_status,
            accounts.account_name,
            COUNT(partner_contacts.id) AS contact_count
        FROM partners
        LEFT JOIN account_partners ON account_partners.partner_id = partners.id
        LEFT JOIN accounts ON accounts.id = account_partners.account_id
        LEFT JOIN partner_contacts ON partner_contacts.partner_id = partners.id
        GROUP BY partners.id, partners.partner_name, partners.partner_type, account_partners.involvement_status, accounts.account_name
        ORDER BY partners.partner_name, accounts.account_name
    """).fetchall()
    engagement_rows = connection.execute("""
        SELECT COALESCE(NULLIF(account_partners.involvement_status, ''), 'Not set') AS engagement, COUNT(*) AS total
        FROM account_partners
        GROUP BY COALESCE(NULLIF(account_partners.involvement_status, ''), 'Not set')
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
            account_partners.involvement_status,
            accounts.account_name,
            partner_contacts.name AS partner_contact_name,
            partner_contacts.job_title,
            partner_contacts.relationship_status
        FROM partners
        LEFT JOIN account_partners ON account_partners.partner_id = partners.id
        LEFT JOIN accounts ON accounts.id = account_partners.account_id
        LEFT JOIN partner_contacts ON partner_contacts.partner_id = partners.id
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
        for user in list_users():
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
        for user in list_users():
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
        sales_play_rows = connection.execute("""
            SELECT sales_play, subject, notes
            FROM outreach
            WHERE account_id = ?
            ORDER BY activity_date, activity_time, id
        """, (account["id"],)).fetchall()
        sales_plays = []
        seen_sales_plays = set()
        for row in sales_play_rows:
            sales_play = documented_sales_play(row)
            sales_play_key = sales_play.casefold()
            if sales_play and sales_play_key not in seen_sales_plays:
                sales_plays.append(sales_play)
                seen_sales_plays.add(sales_play_key)

        plan_items.append(PlanItem(
            pg_bible_order=account["pg_bible_order"],
            account_tier=account["account_tier"] or "",
            pipeline_target_value=account["pipeline_target"] or 0,
            notes=account["notes"] or "",
            nbm_target=str(account["pg_bible_order"] or ""),
            customer=account["account_name"] or "",
            sales_play="; ".join(sales_plays),
            estimated_value=account["pipeline_target"] or 0,
        ))

    contacts = connection.execute("""
        SELECT
            contacts.*,
            accounts.pipeline_target,
            accounts.account_name,
            accounts.pg_bible_order
        FROM contacts
        LEFT JOIN accounts ON contacts.account_id = accounts.id
        ORDER BY
            CASE WHEN accounts.pg_bible_order IS NULL THEN 1 ELSE 0 END,
            accounts.pg_bible_order,
            accounts.account_name,
            contacts.name
    """).fetchall()

    action_items = []
    for contact in contacts:
        latest_outreach = connection.execute("""
            SELECT *
            FROM outreach
            WHERE contact_id = ?
            ORDER BY activity_date DESC, activity_time DESC
            LIMIT 1
        """, (contact["id"],)).fetchone()

        meeting_count = connection.execute("""
            SELECT COUNT(*)
            FROM outreach
            WHERE contact_id = ?
              AND (
                    outcome = 'Meeting Booked'
                 OR activity_type IN ('Meeting', 'Meeting Booked', 'Discovery Meeting', 'NBM Booked')
              )
        """, (contact["id"],)).fetchone()[0]

        action_items.append(ActionItem(
            person_name=contact["name"] or "",
            person_title=contact["job_title"] or "",
            related_nbm_target=str(contact["pg_bible_order"] or ""),
            discovery_target_name_title=", ".join(
                part for part in [contact["name"], contact["job_title"]] if part
            ),
            discovery_completed="Yes" if meeting_count else "",
            discovery_next_action=latest_outreach["next_action"] if latest_outreach else "",
            nbm_booked_date=latest_outreach["activity_date"] if latest_outreach and meeting_count else "",
            nbm_booked_name_title=", ".join(
                part for part in [contact["name"], contact["job_title"]] if part
            ) if meeting_count else "",
            why_buy="",
            exec_first="Yes" if contact["category"] == "Executive" else "",
            prep_with_manager="",
            nbm_completed="Yes" if meeting_count else "",
            nbm_next_action=latest_outreach["next_action"] if latest_outreach else "",
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
        is_meeting_booked = row["outcome"] == "Meeting Booked"
        is_pipeline_outcome = row["outcome"] in ("Meeting Booked", "Positive Response", "Referral Made")
        if row["activity_type"] == "VITO":
            totals["vitos_sent"] += 1
            if row["outcome"] != "No Response Yet":
                totals["vitos_chased"] += 1
        if is_meeting_activity_type(row["activity_type"]) or is_meeting_booked:
            totals["discovery_booked"] += 1
        if is_meeting_activity_type(row["activity_type"]):
            totals["discovery_completed"] += 1
        if is_meeting_booked:
            totals["nbms_booked"] += 1
            if row["category"] == "Executive":
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
    pg_context = pg_dashboard_context(connection)
    plan_items = [
        PlanItem(
            pg_bible_order=int(row["target_number"]) if str(row["target_number"] or "").isdigit() else None,
            pipeline_target_value=row["estimated_value"] or 0,
            nbm_target=str(row["target_number"] or ""),
            customer=row["account_name"] or "",
            customer_business_unit=row.get("business_unit") or "",
            sales_play=" | ".join(
                part.strip()
                for part in str(row["sales_play"] or "").replace(";", "|").split("|")
                if part.strip()
            ),
            estimated_value=row["estimated_value"] or 0,
        )
        for row in pg_context["pg_plan_rows"]
    ]

    action_items = []
    for row in pg_context["pg_action_rows"]:
        account_contact_parts = []
        if row.get("company_name"):
            account_contact_parts.append(row["company_name"])
        if row.get("business_org") and not row.get("is_partner_row"):
            account_contact_parts.append(row["business_org"])
        if row.get("department"):
            account_contact_parts.append(row["department"])
        if row.get("targeted_discovery"):
            account_contact_parts.append(row["targeted_discovery"])

        scheduled_actions = []
        for action in row.get("next_7_days_actions") or []:
            action_text = action.get("subject") or "Scheduled action"
            if action.get("due"):
                action_text = f"{action_text} ({action['due']})"
            scheduled_actions.append(action_text)

        discovery_completed = row.get("completed_discovery_meeting") or ("N/A" if row.get("is_partner_row") else "No")
        exec_first = row.get("exec_first") or ("N/A" if row.get("is_partner_row") else "No")
        nbm_completed = row.get("nbm_completed") or ("N/A" if row.get("is_partner_row") else "No")

        action_items.append(ActionItem(
            related_nbm_target=str(row.get("target_number") or ""),
            discovery_target_name_title=" | ".join(account_contact_parts),
            discovery_completed=discovery_completed,
            discovery_next_action="\n".join(scheduled_actions),
            nbm_completed=nbm_completed,
            exec_first=exec_first,
        ))

    calc_payload = {
        "starting_pipeline": os.environ.get("PIPEFLOW_PG_STARTING_PIPELINE", pg_context["current_pipeline"]),
        "current_pipeline": pg_context["current_pipeline"],
        "pipeline_added": os.environ.get("PIPEFLOW_PG_PIPELINE_ADDED", total_pipeline_added),
        "pipeline_target": os.environ.get("PIPEFLOW_PG_PIPELINE_TARGET", pg_context["fy_pipeline_target"]),
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
        bundled_template = Path(__file__).resolve().parent / "pg_bible_templates" / "PGBible_Template_May2026.xlsx"
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
    connection = get_db_connection()

    accounts = connection.execute("""
        SELECT
            id,
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

    connection.close()

    return render_template(
        "account_reports.html",
        accounts=accounts,
        accounts_by_industry=accounts_by_industry,
        pipeline_by_account=pipeline_by_account,
        accounts_by_country=accounts_by_country,
        accounts_by_tier=accounts_by_tier
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
            contacts.name AS contact_name
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
    today = datetime.now().date()
    active_tasks = [task for task in tasks if not is_closed_task_status(normalised_status(task))]
    overdue_tasks = sum(
        1 for task in active_tasks
        if parse_report_date(task["next_action_date"]) and parse_report_date(task["next_action_date"]) < today
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
    assigned_users = [
        {"assigned_to": assigned_to}
        for assigned_to in sorted({task["assigned_to"] for task in all_tasks if task["assigned_to"]})
    ]

    status_totals = {}
    account_totals = {}
    assignee_totals = {}
    for task in tasks:
        status = normalised_status(task)
        account_name = task["account_name"] or "Unknown"
        assignee = task["assigned_to"] or "Unassigned"
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
            if task_date and task_date < today:
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
    connection = get_db_connection()

    selected_start_date = request.args.get("start_date", "")
    selected_end_date = request.args.get("end_date", "")
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
            outreach.fy,
            outreach.quarter,
            accounts.account_name,
            accounts.account_tier,
            contacts.name AS contact_name
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
    total_outreach = len(filtered_outreach)
    meetings_booked = sum(
        1 for item in filtered_outreach
        if item["outcome"] == "Meeting Booked" or is_meeting_activity_type(item["activity_type"])
    )
    meeting_conversion_total = meetings_booked

    outcome_totals = {}
    type_totals = {}
    monthly_totals = {}
    for item in filtered_outreach:
        outcome = item["outcome"] or "Unknown"
        activity_type = item["activity_type"] or "Unknown"
        outcome_totals[outcome] = outcome_totals.get(outcome, 0) + 1
        type_totals[activity_type] = type_totals.get(activity_type, 0) + 1
        activity_date = parse_report_date(item["activity_date"])
        if activity_date:
            month = activity_date.strftime("%Y-%m")
            if month not in monthly_totals:
                monthly_totals[month] = {"total_outreach": 0, "meetings_booked": 0}
            monthly_totals[month]["total_outreach"] += 1
            if item["outcome"] == "Meeting Booked" or is_meeting_activity_type(item["activity_type"]):
                monthly_totals[month]["meetings_booked"] += 1

    outcome_breakdown = [
        {"outcome": outcome, "count": count}
        for outcome, count in sorted(outcome_totals.items(), key=lambda item: (-item[1], item[0]))
    ]
    outreach_by_type = [
        {"activity_type": activity_type, "count": count}
        for activity_type, count in sorted(type_totals.items(), key=lambda item: (-item[1], item[0]))
    ]
    latest_outreach = filtered_outreach[:10]

    monthly_trends = []
    for month, totals in sorted(monthly_totals.items()):
        total = totals["total_outreach"]
        meetings = totals["meetings_booked"]
        monthly_trends.append({
            "month": month,
            "total_outreach": total,
            "meetings_booked": meetings,
            "meeting_conversion": meetings,
        })

    return render_template(
        "outreach_reports.html",
        total_outreach=total_outreach,
        meetings_booked=meetings_booked,
        conversion_rate=meeting_conversion_total,
        outcome_breakdown=outcome_breakdown,
        outreach_by_type=outreach_by_type,
        latest_outreach=latest_outreach,
        monthly_trends=monthly_trends,
        accounts=accounts,
        activity_types=activity_types,
        outcomes=outcomes,
        selected_start_date=selected_start_date,
        selected_end_date=selected_end_date,
        selected_account=selected_account,
        selected_activity_type=selected_activity_type,
        selected_outcome=selected_outcome,
        outcome_chart_labels=[item["outcome"] for item in outcome_breakdown],
        outcome_chart_data=[item["count"] for item in outcome_breakdown],
        activity_type_chart_labels=[item["activity_type"] for item in outreach_by_type],
        activity_type_chart_data=[item["count"] for item in outreach_by_type],
        monthly_chart_labels=[item["month"] for item in monthly_trends],
        monthly_outreach_data=[item["total_outreach"] for item in monthly_trends],
        monthly_meetings_data=[item["meetings_booked"] for item in monthly_trends],
        monthly_conversion_data=[item["meeting_conversion"] for item in monthly_trends],
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
    connection = get_db_connection()

    contacts = connection.execute("""
        SELECT
            contacts.id,
            contacts.name,
            contacts.job_title,
            contacts.category,
            contacts.bmc_relationship,
            contacts.email,
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

    connection.close()

    return render_template(
        "contact_reports.html",
        contacts=contacts,
        contacts_by_category=contacts_by_category,
        contacts_by_relationship=contacts_by_relationship,
        contacts_by_account=contacts_by_account,
        contacts_by_account_tier=contacts_by_account_tier,
        message=request.args.get("message", "")
    )


@app.route("/reports/contacts/export")
def export_contact_reports():
    connection = get_db_connection()

    contacts = connection.execute("""
        SELECT
            contacts.name,
            contacts.job_title,
            contacts.category,
            contacts.status,
            contacts.bmc_relationship,
            contacts.email,
            contacts.phone,
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
        "Phone",
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
            contact["phone"],
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
    return_target = request.form.get("return_to") or url_for("contact_reports")
    separator = "&" if "?" in return_target else "?"
    return redirect(f"{return_target}{separator}{urlencode({'message': f'Archived {archived_count} inactive contact(s).'})}")


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


def open_browser():
    webbrowser.open_new("http://127.0.0.1:5000")


if __name__ == "__main__":
    if os.environ.get("PIPEFLOW_NO_BROWSER") != "1":
        threading.Timer(1.5, open_browser).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
