import sys
import os
from pathlib import Path
import threading
import webbrowser
import csv
import io
import re
import traceback
from datetime import datetime, timedelta

from flask import Flask, render_template, request, redirect, url_for, Response, send_file, session
from auth import authenticate_user, create_user, current_user, initialise_auth_database, login_required, admin_required, list_users, reset_user_password, set_user_active, set_user_role, reset_password_with_phrase, list_account_field_definitions, create_account_field_definition, update_account_field_definition, set_account_field_active, list_admin_audit_entries, log_admin_audit, get_user_for_admin, get_account_field_definition, ensure_user_workspace_schema, update_user_identity, list_broadcast_messages, create_broadcast_message, update_broadcast_message, set_broadcast_message_active, get_broadcast_message, delete_broadcast_message
from database import get_db_connection, initialise_database
from dropdown_values import DROPDOWN_VALUES
from db_compat import using_postgres, current_user_schema


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
app.config["SECRET_KEY"] = os.environ.get("PIPEFLOW_SECRET_KEY", "pipeflow-server-dev-secret-change-me")

initialise_auth_database()


@app.context_processor
def inject_dropdown_values():
    return {
        "dropdown_values": DROPDOWN_VALUES,
        "current_user": current_user(),
        "app_name": "PipeFlow PG Manager",
    }


@app.before_request
def require_login_and_prepare_database():
    public_endpoints = {"login", "register", "forgot_password", "reset_password", "storage_health", "static"}
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
        "pipeflow_server_build=2026-05-04-dashboard-task-status-fit-v1",
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
        f"user_id={session.get('user_id', '')}",
        f"user_email={session.get('user_email', '')}",
        f"workspace_schema={current_user_schema() if using_postgres() else ''}",
    ]
    return Response("\n".join(lines), mimetype="text/plain")


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
        audit_entries=list_admin_audit_entries(limit=75),
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

    cursor = connection.execute("""
        INSERT INTO partners (partner_name)
        VALUES (?)
    """, (partner_name,))

    return cursor.lastrowid


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
            "activity_type": "Email Sent",
            "subject_prefix": "VITO outreach",
            "next_action": "Send VITO-led message",
            "time": "09:00"
        },
        {
            "campaign": "LinkedIn",
            "activity_type": "LinkedIn Message",
            "subject_prefix": "LinkedIn outreach",
            "next_action": "Send LinkedIn connection or follow-up message",
            "time": "10:00"
        },
        {
            "campaign": "Content and Thought Leadership Sharing",
            "activity_type": "Follow-up",
            "subject_prefix": "Content share",
            "next_action": "Share relevant content or thought leadership",
            "time": "11:00"
        },
        {
            "campaign": "Calls",
            "activity_type": "Call",
            "subject_prefix": "Phone outreach",
            "next_action": "Call contact and progress the sales play",
            "time": "14:00"
        },
        {
            "campaign": "Events",
            "activity_type": "Event Touchpoint",
            "subject_prefix": "Event search and attendance trigger",
            "next_action": "Search for relevant events to attend or reference",
            "time": "15:00"
        }
    ]


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


def build_campaign_schedule(campaign_start, campaign_end, total_tasks, times_per_week):
    templates = campaign_step_templates()
    total_tasks = max(1, int(total_tasks or 1))
    times_per_week = max(1, min(int(times_per_week or 1), 7))
    schedule = []

    for index, action_date in enumerate(evenly_spaced_dates(campaign_start, campaign_end, total_tasks)):
        if action_date < campaign_start:
            action_date = campaign_start
        if action_date > campaign_end:
            action_date = campaign_end
        template = dict(templates[index % len(templates)])
        template["action_date"] = action_date
        template["times_per_week"] = times_per_week
        schedule.append(template)

    return schedule


def build_pg_campaign_steps(pg_week_start):
    return build_campaign_schedule(pg_week_start - timedelta(days=28), pg_week_start - timedelta(days=1), 8, 2)


POSITIVE_OUTCOMES = (
    "Positive Response",
    "Meeting Booked",
    "Referral Made",
    "Follow-up Required",
)

NEGATIVE_OUTCOMES = (
    "Negative Response",
    "Not Relevant",
)


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


def build_learning_insights(connection):
    positive_placeholders = ",".join("?" for _ in POSITIVE_OUTCOMES)
    negative_placeholders = ",".join("?" for _ in NEGATIVE_OUTCOMES)
    learning_select = f"""
        COUNT(outreach.id) AS total,
        SUM(CASE
            WHEN outreach.outcome IN ({positive_placeholders})
              OR outreach.activity_type = 'Meeting'
            THEN 1 ELSE 0
        END) AS positive_total,
        SUM(CASE
            WHEN outreach.outcome = 'Meeting Booked'
              OR outreach.activity_type = 'Meeting'
            THEN 1 ELSE 0
        END) AS meeting_total,
        SUM(CASE
            WHEN outreach.outcome IN ({negative_placeholders})
            THEN 1 ELSE 0
        END) AS negative_total,
        SUM(CASE
            WHEN COALESCE(outreach.task_status, '') = 'Completed'
            THEN 1 ELSE 0
        END) AS completed_total,
        SUM(CASE
            WHEN outreach.next_action_date IS NOT NULL
              AND outreach.next_action_date != ''
              AND datetime(
                    outreach.next_action_date || ' ' ||
                    IFNULL(outreach.next_action_time, '00:00')
                  ) < datetime('now', '-1 hour')
              AND COALESCE(outreach.task_status, '') != 'Completed'
            THEN 1 ELSE 0
        END) AS overdue_total
    """
    learning_params = (*POSITIVE_OUTCOMES, *NEGATIVE_OUTCOMES)
    insights = []

    campaign_rows = add_learning_score(connection.execute(f"""
        SELECT
            outreach.campaign,
            {learning_select}
        FROM outreach
        WHERE outreach.campaign IS NOT NULL
          AND outreach.campaign != ''
        GROUP BY outreach.campaign
    """, learning_params).fetchall())

    if campaign_rows:
        campaign = campaign_rows[0]
        insights.append({
            "signal": "Campaign",
            "title": f"{campaign['campaign']} is your strongest campaign signal",
            "message": (
                f"{campaign['positive_total']} positive signal(s), "
                f"{campaign['meeting_total']} meeting(s), "
                f"{campaign['positive_rate']}% positive rate across "
                f"{campaign['total']} touchpoint(s)."
            ),
            "action": "Use this campaign as the default first route when the account and contact profile are similar.",
            "link": url_for("outreach")
        })

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
            outreach.campaign,
            outreach.sales_play,
            {learning_select}
        FROM outreach
        LEFT JOIN accounts ON outreach.account_id = accounts.id
        WHERE accounts.account_name IS NOT NULL
          AND (
                (outreach.campaign IS NOT NULL AND outreach.campaign != '')
             OR (outreach.sales_play IS NOT NULL AND outreach.sales_play != '')
          )
        GROUP BY accounts.id, accounts.account_name, outreach.campaign, outreach.sales_play
    """, learning_params).fetchall())

    if account_rows:
        account = account_rows[0]
        label_parts = [
            part for part in [account["campaign"], account["sales_play"]]
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
            "action": "Repeat this pattern for the next stakeholder before switching route.",
            "link": url_for("view_account", account_id=account["account_id"])
        })

    contact_category_rows = add_learning_score(connection.execute(f"""
        SELECT
            contacts.category,
            outreach.campaign,
            {learning_select}
        FROM outreach
        LEFT JOIN contacts ON outreach.contact_id = contacts.id
        WHERE contacts.category IS NOT NULL
          AND contacts.category != ''
          AND outreach.campaign IS NOT NULL
          AND outreach.campaign != ''
        GROUP BY contacts.category, outreach.campaign
    """, learning_params).fetchall())

    if contact_category_rows:
        category = contact_category_rows[0]
        insights.append({
            "signal": "Contact",
            "title": f"{category['campaign']} works best with {category['category']} contacts",
            "message": (
                f"This combination has {category['positive_total']} positive signal(s), "
                f"{category['meeting_total']} meeting(s), and "
                f"{category['negative_total']} negative signal(s)."
            ),
            "action": "When adding contacts in this category, start with this campaign and track the outcome.",
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

    outcome_gaps = connection.execute("""
        SELECT COUNT(*) AS total
        FROM outreach
        WHERE (
                campaign IS NOT NULL
            AND campaign != ''
        )
          AND (
                sales_play IS NOT NULL
            AND sales_play != ''
        )
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
            "message": "PipeFlow will compare campaigns, sales plays, contacts and account patterns once outcomes are captured.",
            "action": "Build a campaign, complete the follow-up tasks, then record the outcome on each touchpoint.",
            "link": url_for("campaign_builder")
        })
    elif outcome_gaps > 0:
        insights.append({
            "signal": "Data Quality",
            "title": f"{outcome_gaps} campaign touchpoint(s) need outcomes",
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
    except Exception as exc:
        print(f"Dashboard failed: {exc!r}", file=sys.stderr)
        traceback.print_exc()
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
        this_week_pipeline_created=0,
        this_week_start="",
        this_week_end="",
        total_accounts=0,
        total_contacts=0,
        total_outreach=0,
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

    def task_completed(row):
        return (row["task_status"] or "") == "Completed"

    this_week_due = 0
    this_week_completed = 0
    this_week_overdue = 0
    this_week_meetings_booked = 0
    this_week_pipeline_created = 0
    touched_account_ids = set()

    for row in weekly_outreach_rows:
        next_action_date = parse_dashboard_date(row["next_action_date"])
        activity_date = parse_dashboard_date(row["activity_date"])

        if next_action_date and week_start <= next_action_date <= week_end and not task_completed(row):
            this_week_due += 1

        if next_action_date and next_action_date < today and not task_completed(row):
            this_week_overdue += 1

        if task_completed(row):
            last_updated_date = parse_dashboard_date(str(row["last_updated"] or "")[:10])
            if last_updated_date and week_start <= last_updated_date <= week_end:
                this_week_completed += 1

        if activity_date and week_start <= activity_date <= week_end:
            if row["account_id"]:
                touched_account_ids.add(row["account_id"])
            if row["outcome"] == "Meeting Booked" or row["activity_type"] == "Meeting":
                this_week_meetings_booked += 1
            if row["outcome"] in ("Meeting Booked", "Positive Response", "Referral Made"):
                this_week_pipeline_created += row["pipeline_target"] or 0

    this_week_untouched_accounts = max(
        0,
        len(all_accounts) - len(touched_account_ids)
    )

    meetings_booked = connection.execute("""
        SELECT COUNT(*) FROM outreach
        WHERE outcome = 'Meeting Booked'
           OR activity_type = 'Meeting'
    """).fetchone()[0]

    follow_ups_due = connection.execute("""
        SELECT COUNT(*) FROM outreach
        WHERE next_action_date IS NOT NULL
          AND next_action_date != ''
          AND date(next_action_date) <= date('now', '+7 days')
          AND COALESCE(task_status, '') != 'Completed'
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
        SELECT outreach.*, accounts.account_name, accounts.account_tier, contacts.name AS contact_name
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
          AND COALESCE(outreach.task_status, '') != 'Completed'
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
                     OR outreach.activity_type = 'Meeting'
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
                  AND COALESCE(outreach.task_status, '') != 'Completed'
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
    execution_insights = build_execution_insights(ai_insights, learning_insights)

    return render_template(
        "index.html",
        this_week_due=this_week_due,
        this_week_completed=this_week_completed,
        this_week_overdue=this_week_overdue,
        this_week_untouched_accounts=this_week_untouched_accounts,
        this_week_meetings_booked=this_week_meetings_booked,
        this_week_pipeline_created=this_week_pipeline_created,
        this_week_start=week_start_key,
        this_week_end=week_end_key,
        total_accounts=total_accounts,
        total_contacts=total_contacts,
        total_outreach=total_outreach,
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


@app.route("/accounts")
def accounts():
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
                     OR outreach.activity_type = 'Meeting'
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
                  AND COALESCE(outreach.task_status, '') != 'Completed'
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

    health_order = {
        "red": 1,
        "amber": 2,
        "yellow": 3,
        "green": 4
    }

    accounts.sort(
        key=lambda account: (
            health_order.get(account["health_colour"], 99),
            account["account_name"].lower()
        )
    )

    connection.close()

    return render_template("accounts.html", accounts=accounts)


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

    connection.close()

    return render_template("partners.html", partners=partner_rows)


@app.route("/partners/add", methods=("POST",))
def add_partner():
    connection = get_db_connection()
    partner_name = request.form.get("partner_name", "").strip()

    if partner_name:
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
                    relationship_owner,
                    notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                partner_name,
                request.form.get("partner_type"),
                request.form.get("website"),
                request.form.get("country"),
                request.form.get("city"),
                request.form.get("relationship_owner"),
                request.form.get("notes")
            ))
            partner_id = cursor.lastrowid
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
        SELECT *
        FROM partner_contacts
        WHERE partner_id = ?
        ORDER BY name
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

    if partner_name:
        connection.execute("""
            UPDATE partners
            SET partner_name = ?,
                partner_type = ?,
                website = ?,
                country = ?,
                city = ?,
                relationship_owner = ?,
                notes = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            partner_name,
            request.form.get("partner_type"),
            request.form.get("website"),
            request.form.get("country"),
            request.form.get("city"),
            request.form.get("relationship_owner"),
            request.form.get("notes"),
            partner_id
        ))

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
        connection.execute("""
            INSERT INTO partner_contacts (
                partner_id,
                name,
                job_title,
                partner_contact_role,
                coverage_area,
                relationship_owner,
                email,
                phone,
                location,
                linkedin,
                relationship_status,
                next_action,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            partner_id,
            contact_name,
            request.form.get("job_title"),
            request.form.get("partner_contact_role"),
            request.form.get("coverage_area"),
            request.form.get("relationship_owner"),
            request.form.get("email"),
            request.form.get("phone"),
            request.form.get("location"),
            request.form.get("linkedin"),
            request.form.get("relationship_status"),
            request.form.get("next_action"),
            request.form.get("notes")
        ))
        connection.commit()

    connection.close()
    return redirect(url_for("view_partner", partner_id=partner_id))


@app.route("/partners/<int:partner_id>/contacts/<int:contact_id>/delete", methods=("POST",))
def delete_partner_contact(partner_id, contact_id):
    connection = get_db_connection()
    connection.execute("""
        DELETE FROM partner_contacts
        WHERE id = ?
          AND partner_id = ?
    """, (contact_id, partner_id))
    connection.commit()
    connection.close()

    return redirect(url_for("view_partner", partner_id=partner_id))


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
            connection.execute("""
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
                request.form.get("partner_role"),
                request.form.get("involvement_status"),
                request.form.get("relationship_owner"),
                request.form.get("next_action"),
                request.form.get("notes")
            ))

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
        cursor = connection.execute("""
            INSERT INTO accounts
            (account_name, pg_bible_order, account_tier, industry, business_unit, country, city, website, pipeline_target, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            request.form.get("notes")
        ))
        account_id = cursor.lastrowid
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
                     OR outreach.activity_type = 'Meeting'
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
                  AND COALESCE(outreach.task_status, '') != 'Completed'
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

    account_partners = connection.execute("""
        SELECT
            account_partners.*,
            partners.partner_type,
            partners.website AS partner_website,
            (
                SELECT COUNT(*)
                FROM partner_contacts
                WHERE partner_contacts.partner_id = account_partners.partner_id
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
        account_partners=account_partners,
        partner_options=partner_options,
        timeline_entries=timeline_entries,
        custom_fields=custom_fields,
        custom_values=custom_values
    )


@app.route("/accounts/<int:account_id>/partners/add", methods=("POST",))
def add_account_partner(account_id):
    connection = get_db_connection()
    partner_id = request.form.get("partner_id")
    partner_name = request.form.get("partner_name", "").strip()

    if partner_id:
        partner = connection.execute("""
            SELECT partner_name
            FROM partners
            WHERE id = ?
        """, (partner_id,)).fetchone()
        if partner:
            partner_name = partner["partner_name"]
        else:
            partner_id = None

    if partner_name and not partner_id:
        partner_id = get_or_create_partner(connection, partner_name)

    if partner_name:
        connection.execute("""
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
            request.form.get("partner_role"),
            request.form.get("involvement_status"),
            request.form.get("relationship_owner"),
            request.form.get("next_action"),
            request.form.get("notes")
        ))

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
            "partner_role": request.form.get("partner_role"),
            "involvement_status": request.form.get("involvement_status"),
            "relationship_owner": request.form.get("relationship_owner"),
            "next_action": request.form.get("next_action"),
            "notes": request.form.get("notes")
        }

        labels = {
            "partner_id": "Partner organisation",
            "partner_name": "Partner name",
            "partner_role": "Partner role",
            "involvement_status": "Involvement status",
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
            "notes": "Notes"
        }

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
            new_values["notes"],
            account_id
        ))

        save_account_custom_values(connection, account_id, custom_fields, request.form)

        if changes:
            add_timeline_entry(
                connection,
                "account",
                account_id,
                "Auto Audit",
                "Account updated: " + "; ".join(changes)
            )

        connection.commit()
        connection.close()

        return redirect(url_for("view_account", account_id=account_id))

    connection.close()
    return render_template(
        "edit_account.html",
        account=account,
        custom_fields=custom_fields,
        custom_values=custom_values
    )


@app.route("/accounts/<int:account_id>/delete", methods=("POST",))
@admin_required
def delete_account(account_id):
    connection = get_db_connection()
    connection.execute("DELETE FROM timeline_entries WHERE related_type = 'account' AND related_id = ?", (account_id,))
    connection.execute("DELETE FROM account_partners WHERE account_id = ?", (account_id,))
    connection.execute("DELETE FROM account_custom_values WHERE account_id = ?", (account_id,))
    connection.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
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


@app.route("/contacts")
def contacts():
    connection = get_db_connection()
    contacts = connection.execute("""
        SELECT contacts.*, accounts.account_name, accounts.account_tier
        FROM contacts
        LEFT JOIN accounts ON contacts.account_id = accounts.id
        ORDER BY contacts.name
    """).fetchall()
    connection.close()
    return render_template("contacts.html", contacts=contacts)


@app.route("/contacts/add", methods=("GET", "POST"))
def add_contact():
    if request.method == "POST":
        connection = get_db_connection()
        connection.execute("""
            INSERT INTO contacts (
                account_id, category, name, job_title, org_dept, responsibilities,
                email, phone, location, linkedin, bmc_relationship, characteristics,
                background, personal_interests, personal_win, education,
                social_media, additional_notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            request.form.get("additional_notes")
        ))
        connection.commit()
        connection.close()

        return redirect(url_for("contacts"))

    connection = get_db_connection()
    accounts = connection.execute("SELECT * FROM accounts ORDER BY account_name").fetchall()
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

    accounts = connection.execute(
        "SELECT * FROM accounts ORDER BY account_name"
    ).fetchall()

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
    connection.execute("DELETE FROM timeline_entries WHERE related_type = 'contact' AND related_id = ?", (contact_id,))
    connection.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
    connection.commit()
    connection.close()

    return redirect(url_for("contacts"))


@app.route("/outreach")
def outreach():
    fy_filter = request.args.get("fy")
    quarter_filter = request.args.get("quarter")
    campaign_filter = request.args.get("campaign")
    account_filter = request.args.get("account_id")
    outcome_filter = request.args.get("outcome")

    connection = get_db_connection()

    query = """
        SELECT outreach.*, accounts.account_name, accounts.account_tier, contacts.name AS contact_name
        FROM outreach
        LEFT JOIN accounts ON outreach.account_id = accounts.id
        LEFT JOIN contacts ON outreach.contact_id = contacts.id
        WHERE 1 = 1
    """

    params = []

    if fy_filter:
        query += " AND outreach.fy = ?"
        params.append(fy_filter)

    if quarter_filter:
        query += " AND outreach.quarter = ?"
        params.append(quarter_filter)

    if campaign_filter:
        query += " AND outreach.campaign = ?"
        params.append(campaign_filter)

    if account_filter:
        query += " AND outreach.account_id = ?"
        params.append(account_filter)

    if outcome_filter:
        query += " AND outreach.outcome = ?"
        params.append(outcome_filter)

    query += " ORDER BY outreach.activity_date DESC, outreach.activity_time DESC"

    outreach_records = connection.execute(query, params).fetchall()

    accounts = connection.execute(
        "SELECT * FROM accounts ORDER BY account_name"
    ).fetchall()

    connection.close()

    return render_template(
        "outreach.html",
        outreach_records=outreach_records,
        accounts=accounts,
        fy_filter=fy_filter,
        quarter_filter=quarter_filter,
        campaign_filter=campaign_filter,
        account_filter=account_filter,
        outcome_filter=outcome_filter
    )


@app.route("/outreach/add", methods=("GET", "POST"))
def add_outreach():
    connection = get_db_connection()

    if request.method == "POST":
        connection.execute("""
            INSERT INTO outreach (
                fy, quarter, campaign, sales_play, account_id, contact_id, activity_type,
                activity_date, activity_time, subject, notes, outcome,
                next_action, next_action_date, next_action_time,
                task_status, assigned_to
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request.form.get("fy"),
            request.form.get("quarter"),
            request.form.get("campaign"),
            request.form.get("sales_play"),
            request.form.get("account_id"),
            request.form.get("contact_id"),
            request.form.get("activity_type"),
            request.form.get("activity_date"),
            request.form.get("activity_time"),
            request.form.get("subject"),
            request.form.get("notes"),
            request.form.get("outcome"),
            request.form.get("next_action"),
            request.form.get("next_action_date"),
            request.form.get("next_action_time"),
            request.form.get("task_status", "Not Started"),
            request.form.get("assigned_to", "")
        ))

        connection.commit()
        connection.close()

        return redirect(url_for("outreach"))

    accounts = connection.execute("SELECT * FROM accounts ORDER BY account_name").fetchall()

    contacts = connection.execute("""
        SELECT contacts.*, accounts.account_name, accounts.account_tier
        FROM contacts
        LEFT JOIN accounts ON contacts.account_id = accounts.id
        ORDER BY contacts.name
    """).fetchall()

    profile = connection.execute("""
        SELECT *
        FROM user_profile
        WHERE id = 1
    """).fetchone()

    connection.close()

    return render_template(
        "add_outreach.html",
        accounts=accounts,
        contacts=contacts,
        profile=profile
    )


@app.route("/outreach/campaign-builder", methods=("GET", "POST"))
def campaign_builder():
    connection = get_db_connection()
    generated_count = 0
    selected_account_id = request.form.get("account_id") or request.args.get("account_id") or ""
    selected_contact_ids = request.form.getlist("contact_ids")
    selected_pg_week_start = request.form.get("pg_week_start", "")
    selected_campaign_start = request.form.get("campaign_start_date", "")
    selected_campaign_end = request.form.get("campaign_end_date", "")
    selected_total_tasks = request.form.get("total_outreach_tasks", "8")
    selected_times_per_week = request.form.get("times_per_week", "2")
    selected_sales_plays = request.form.get("sales_plays", "")

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
        sales_plays = [
            play.strip()
            for play in request.form.get("sales_plays", "").splitlines()
            if play.strip()
        ]

        if not sales_plays:
            sales_plays = ["PG week sales play"]

        if account_id and pg_week_start_raw and campaign_start_raw and campaign_end_raw and contact_ids:
            pg_week_start = datetime.strptime(pg_week_start_raw, "%Y-%m-%d").date()
            campaign_start = datetime.strptime(campaign_start_raw, "%Y-%m-%d").date()
            campaign_end = datetime.strptime(campaign_end_raw, "%Y-%m-%d").date()
            if campaign_end < campaign_start:
                campaign_start, campaign_end = campaign_end, campaign_start
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

            account_name = account["account_name"] if account else "Selected account"
            assigned_to = request.form.get("assigned_to", "")
            fy = request.form.get("fy", "")
            quarter = request.form.get("quarter", "")

            for contact in contacts:
                for sales_play in sales_plays:
                    for step in build_campaign_schedule(campaign_start, campaign_end, total_tasks, times_per_week):
                        action_date = step["action_date"]
                        subject = f"{step['subject_prefix']}: {sales_play}"
                        notes = (
                            f"Auto-generated campaign step for {account_name}. "
                            f"Campaign window: {campaign_start.isoformat()} to {campaign_end.isoformat()}. "
                            f"Total outreach tasks: {total_tasks}. "
                            f"Times per week: {times_per_week}. "
                            f"Sales play: {sales_play}. Contact: {contact['name']}."
                        )
                        next_action = f"{step['next_action']} for {contact['name']} - {sales_play}"

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
                            step["campaign"],
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
                            next_action,
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
                f"Generated {generated_count} campaign outreach step(s) from {campaign_start.isoformat()} to {campaign_end.isoformat()} with {total_tasks} task(s) at {times_per_week} time(s) per week"
            )
            connection.commit()

    accounts = connection.execute("""
        SELECT *
        FROM accounts
        ORDER BY account_name
    """).fetchall()

    contacts = connection.execute("""
        SELECT contacts.*, accounts.account_name
        FROM contacts
        LEFT JOIN accounts ON contacts.account_id = accounts.id
        ORDER BY
            CASE WHEN accounts.pg_bible_order IS NULL THEN 1 ELSE 0 END,
            accounts.pg_bible_order,
            accounts.account_name,
            contacts.name
    """).fetchall()

    profile = connection.execute("""
        SELECT *
        FROM user_profile
        WHERE id = 1
    """).fetchone()

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
        selected_sales_plays=selected_sales_plays
    )


@app.route("/outreach/<int:outreach_id>")
def view_outreach(outreach_id):
    connection = get_db_connection()

    outreach_item = connection.execute("""
        SELECT outreach.*, accounts.account_name, accounts.account_tier, contacts.name AS contact_name
        FROM outreach
        LEFT JOIN accounts ON outreach.account_id = accounts.id
        LEFT JOIN contacts ON outreach.contact_id = contacts.id
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
    connection.execute("DELETE FROM timeline_entries WHERE related_type = 'outreach' AND related_id = ?", (outreach_id,))
    connection.execute("DELETE FROM outreach WHERE id = ?", (outreach_id,))
    connection.commit()
    connection.close()

    return redirect(url_for("outreach"))


@app.route("/outreach/<int:outreach_id>/edit", methods=("GET", "POST"))
def edit_outreach(outreach_id):
    connection = get_db_connection()

    outreach_item = connection.execute(
        "SELECT * FROM outreach WHERE id = ?",
        (outreach_id,)
    ).fetchone()

    accounts = connection.execute(
        "SELECT * FROM accounts ORDER BY account_name"
    ).fetchall()

    contacts = connection.execute("""
        SELECT contacts.*, accounts.account_name
        FROM contacts
        LEFT JOIN accounts ON contacts.account_id = accounts.id
        ORDER BY contacts.name
    """).fetchall()

    profile = connection.execute("""
        SELECT *
        FROM user_profile
        WHERE id = 1
    """).fetchone()

    if request.method == "POST":
        new_values = {
            "fy": request.form.get("fy"),
            "quarter": request.form.get("quarter"),
            "campaign": request.form.get("campaign"),
            "sales_play": request.form.get("sales_play"),
            "account_id": request.form.get("account_id"),
            "contact_id": request.form.get("contact_id"),
            "activity_type": request.form.get("activity_type"),
            "activity_date": request.form.get("activity_date"),
            "activity_time": request.form.get("activity_time"),
            "subject": request.form.get("subject"),
            "notes": request.form.get("notes"),
            "outcome": request.form.get("outcome"),
            "next_action": request.form.get("next_action"),
            "next_action_date": request.form.get("next_action_date"),
            "next_action_time": request.form.get("next_action_time"),
            "task_status": request.form.get("task_status", "Not Started"),
            "assigned_to": request.form.get("assigned_to", "")
        }

        labels = {
            "fy": "FY",
            "quarter": "Quarter",
            "campaign": "Campaign",
            "sales_play": "Sales play",
            "account_id": "Account",
            "contact_id": "Contact",
            "activity_type": "Activity type",
            "activity_date": "Activity date",
            "activity_time": "Activity time",
            "subject": "Subject",
            "notes": "Notes",
            "outcome": "Outcome",
            "next_action": "Next action",
            "next_action_date": "Next action date",
            "next_action_time": "Next action time",
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
            add_timeline_entry(
                connection,
                "outreach",
                outreach_id,
                "Auto Audit",
                "Outreach updated: " + "; ".join(changes)
            )

        connection.commit()
        connection.close()

        return redirect(url_for("view_outreach", outreach_id=outreach_id))

    connection.close()

    return render_template(
        "edit_outreach.html",
        outreach_item=outreach_item,
        accounts=accounts,
        contacts=contacts,
        profile=profile
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
               OR relationship_owner LIKE ?
               OR notes LIKE ?
            ORDER BY partner_name
        """, (
            search_term, search_term, search_term, search_term,
            search_term, search_term, search_term
        )).fetchall()

        partner_contact_results = connection.execute("""
            SELECT partner_contacts.*, partners.partner_name
            FROM partner_contacts
            LEFT JOIN partners ON partner_contacts.partner_id = partners.id
            WHERE partner_contacts.name LIKE ?
               OR partner_contacts.job_title LIKE ?
               OR partner_contacts.partner_contact_role LIKE ?
               OR partner_contacts.coverage_area LIKE ?
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
            search_term
        )).fetchall()

        outreach_results = connection.execute("""
            SELECT outreach.*, accounts.account_name, contacts.name AS contact_name
            FROM outreach
            LEFT JOIN accounts ON outreach.account_id = accounts.id
            LEFT JOIN contacts ON outreach.contact_id = contacts.id
            WHERE outreach.subject LIKE ?
               OR outreach.notes LIKE ?
               OR outreach.outcome LIKE ?
               OR outreach.campaign LIKE ?
               OR outreach.sales_play LIKE ?
               OR outreach.next_action LIKE ?
               OR outreach.activity_type LIKE ?
               OR accounts.account_name LIKE ?
               OR contacts.name LIKE ?
            ORDER BY outreach.activity_date DESC, outreach.activity_time DESC
        """, (
            search_term, search_term, search_term, search_term,
            search_term, search_term, search_term, search_term,
            search_term
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

    new_values = {
        "outcome": request.form.get("outcome"),
        "task_status": request.form.get("task_status", "Not Started"),
        "next_action": request.form.get("next_action"),
        "next_action_date": request.form.get("next_action_date"),
        "next_action_time": request.form.get("next_action_time"),
        "notes": request.form.get("notes"),
    }
    labels = {
        "outcome": "Outcome",
        "task_status": "Task status",
        "next_action": "Next action",
        "next_action_date": "Next action date",
        "next_action_time": "Next action time",
        "notes": "Notes",
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
            notes = ?,
            last_updated = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            new_values["outcome"],
            new_values["task_status"],
            new_values["next_action"],
            new_values["next_action_date"],
            new_values["next_action_time"],
            new_values["notes"],
            outreach_id,
        ),
    )
    if changes:
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

    outcome = request.form.get("outcome") or outreach_item["outcome"] or "Follow-up Required"
    connection.execute(
        """
        UPDATE outreach
        SET task_status = 'Completed',
            outcome = ?,
            last_updated = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (outcome, outreach_id),
    )
    add_timeline_entry(
        connection,
        "outreach",
        outreach_id,
        "Task Completed",
        f"Task marked completed from Tasks page with outcome: {outcome}",
    )
    connection.commit()
    connection.close()
    return redirect(return_target)


@app.route("/profile", methods=("GET", "POST"))
def profile():
    connection = get_db_connection()

    if request.method == "POST":
        connection.execute("""
            UPDATE user_profile
            SET full_name = ?,
                team = ?,
                job_title = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE id = 1
        """, (
            request.form.get("full_name"),
            request.form.get("team"),
            request.form.get("job_title")
        ))

        connection.commit()
        connection.close()

        return redirect(url_for("profile"))

    profile_record = connection.execute("""
        SELECT *
        FROM user_profile
        WHERE id = 1
    """).fetchone()

    connection.close()

    return render_template("profile.html", profile=profile_record)


@app.route("/reports")
def reports():
    return render_template("reports.html")


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
            customer=account["account_name"] or "",
            sales_play="; ".join(sales_plays),
            estimated_value=account["pipeline_target"] or 0,
        ))

    contacts = connection.execute("""
        SELECT
            contacts.*,
            accounts.pipeline_target,
            accounts.account_name
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
                 OR activity_type = 'Meeting'
              )
        """, (contact["id"],)).fetchone()[0]

        action_items.append(ActionItem(
            person_name=contact["name"] or "",
            person_title=contact["job_title"] or "",
            related_nbm_target=str(contact["account_id"] or ""),
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
            outreach.campaign,
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
        if row["campaign"] == "VITO":
            totals["vitos_sent"] += 1
            if row["outcome"] != "No Response Yet":
                totals["vitos_chased"] += 1
        if row["activity_type"] == "Meeting" or is_meeting_booked:
            totals["discovery_booked"] += 1
        if row["activity_type"] == "Meeting":
            totals["discovery_completed"] += 1
        if is_meeting_booked:
            totals["nbms_booked"] += 1
            if row["category"] == "Executive":
                totals["nbms_exec_firsts"] += 1
            if (row["task_status"] or "") == "Completed":
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
        bundled_template = Path(__file__).resolve().parent / "pg_bible_templates" / "PG Bible FY27.xlsx"
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
    active_tasks = [task for task in tasks if normalised_status(task) != "Completed"]
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
    for task in tasks:
        status = normalised_status(task)
        account_name = task["account_name"] or "Unknown"
        status_totals[status] = status_totals.get(status, 0) + 1
        account_totals[account_name] = account_totals.get(account_name, 0) + 1

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

    return render_template(
        "task_reports.html",
        tasks=tasks,
        overdue_tasks=overdue_tasks,
        due_today=due_today,
        upcoming_tasks=upcoming_tasks,
        tasks_by_status=tasks_by_status,
        tasks_by_account=tasks_by_account,
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
        "Notes",
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
            outreach.activity_type,
            outreach.outcome,
            accounts.account_name,
            accounts.account_tier
        FROM outreach
        LEFT JOIN accounts ON outreach.account_id = accounts.id
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
        if item["outcome"] == "Meeting Booked" or item["activity_type"] == "Meeting"
    )
    conversion_rate = round((meetings_booked / total_outreach) * 100, 2) if total_outreach else 0

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
            if item["outcome"] == "Meeting Booked" or item["activity_type"] == "Meeting":
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
            "conversion_rate": round((meetings / total) * 100, 2) if total else 0,
        })

    return render_template(
        "outreach_reports.html",
        total_outreach=total_outreach,
        meetings_booked=meetings_booked,
        conversion_rate=conversion_rate,
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
        monthly_conversion_data=[item["conversion_rate"] for item in monthly_trends],
    )


@app.route("/reports/outreach/export")
def export_outreach_reports():
    connection = get_db_connection()

    outreach_items = connection.execute("""
        SELECT
            outreach.activity_date,
            accounts.account_name,
            accounts.account_tier,
            contacts.name AS contact_name,
            outreach.activity_type,
            outreach.outcome,
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
        "Account",
        "Account Tier",
        "Contact",
        "Activity Type",
        "Outcome",
        "Notes"
    ])

    for item in outreach_items:
        writer.writerow([
            item["activity_date"],
            item["account_name"],
            item["account_tier"],
            item["contact_name"],
            item["activity_type"],
            item["outcome"],
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
        GROUP BY COALESCE(NULLIF(category, ''), 'Unknown')
        ORDER BY total DESC
    """).fetchall()

    contacts_by_relationship = connection.execute("""
        SELECT
            COALESCE(NULLIF(bmc_relationship, ''), 'Unknown') AS relationship,
            COUNT(*) AS total
        FROM contacts
        GROUP BY COALESCE(NULLIF(bmc_relationship, ''), 'Unknown')
        ORDER BY total DESC
    """).fetchall()

    contacts_by_account = connection.execute("""
        SELECT
            accounts.account_name,
            COUNT(contacts.id) AS total
        FROM contacts
        LEFT JOIN accounts ON contacts.account_id = accounts.id
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
        contacts_by_account_tier=contacts_by_account_tier
    )


@app.route("/reports/contacts/export")
def export_contact_reports():
    connection = get_db_connection()

    contacts = connection.execute("""
        SELECT
            contacts.name,
            contacts.job_title,
            contacts.category,
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
        ORDER BY contacts.name
    """).fetchall()

    connection.close()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Name",
        "Job Title",
        "Category",
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


@app.route("/outreach/export")
def export_outreach():
    connection = get_db_connection()

    outreach_records = connection.execute("""
        SELECT
            outreach.fy,
            outreach.quarter,
            outreach.campaign,
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
        "Campaign",
        "Sales Play",
        "Activity Date",
        "Activity Time",
        "Account",
        "Account Tier",
        "Contact",
        "Activity Type",
        "Subject",
        "Notes",
        "Outcome",
        "Next Action",
        "Next Action Date",
        "Next Action Time"
    ])

    for row in outreach_records:
        writer.writerow([
            row["fy"],
            row["quarter"],
            row["campaign"],
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
