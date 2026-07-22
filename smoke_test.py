import os
import sqlite3
import tempfile
from datetime import date, timedelta
from pathlib import Path


def assert_ok(condition, message):
    if not condition:
        raise AssertionError(message)


def csrf_from_session(client):
    with client.session_transaction() as sess:
        return sess.get("_csrf_token", "")


def seed_validation_data(db_path):
    connection = sqlite3.connect(db_path)
    account_id = connection.execute(
        """
        INSERT INTO accounts (
            account_name, pg_bible_order, account_tier, industry, business_unit,
            country, city, website, pipeline_target, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "Smoke Test Account",
            1,
            "1",
            "Public Sector",
            "BMC",
            "United Kingdom",
            "London",
            "https://example.com",
            500000,
            "Smoke test notes",
        ),
    ).lastrowid
    smoke_logo = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
    )
    connection.execute(
        "UPDATE accounts SET customer_logo = ? WHERE id = ?",
        (smoke_logo, account_id),
    )
    contact_id = connection.execute(
        """
        INSERT INTO contacts (account_id, category, name, job_title, email, phone, location)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (account_id, "Executive", "Smoke Test Contact", "CIO", "contact@example.com", "12345", "London"),
    ).lastrowid
    second_contact_id = connection.execute(
        """
        INSERT INTO contacts (account_id, category, name, job_title, email, phone, location)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (account_id, "Technical", "Smoke Second Contact", "CTO", "second@example.com", "67890", "London"),
    ).lastrowid
    partner_id = connection.execute(
        """
        INSERT INTO partners (partner_name, partner_type, country, city, relationship_owner)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("Smoke Test Partner", "SI", "United Kingdom", "London", "Smoke Tester"),
    ).lastrowid
    partner_contact_id = connection.execute(
        """
        INSERT INTO partner_contacts (partner_id, account_id, name, job_title, partner_contact_role, email)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (partner_id, account_id, "Smoke Partner Contact", "CTO", "Presales", "partner@example.com"),
    ).lastrowid
    connection.execute(
        """
        INSERT INTO account_partners (account_id, partner_id, partner_name, partner_role, involvement_status)
        VALUES (?, ?, ?, ?, ?)
        """,
        (account_id, partner_id, "Smoke Test Partner", "Account Manager", "Active"),
    )
    outreach_id = connection.execute(
        """
        INSERT INTO outreach (
            fy, quarter, account_id, contact_id, campaign, sales_play, campaign_start_date,
            campaign_end_date, campaign_tasks_per_week, campaign_total_tasks, activity_date,
            activity_time, activity_type, subject, notes, outcome, next_action,
            next_action_date, next_action_time, task_status, assigned_to
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "FY27",
            "Q1",
            account_id,
            contact_id,
            "VITO",
            "Smoke Test Play",
            "2026-05-01",
            "2026-05-29",
            3,
            12,
            "2026-05-01",
            "09:00",
            "Call",
            "Smoke test outreach",
            "Sales play: Smoke Test Play. Contact: Smoke Test Contact",
            "Meeting Booked",
            "Follow up",
            "2026-05-05",
            "10:00",
            "Not Started",
            "Smoke Tester",
        ),
    ).lastrowid
    connection.commit()
    connection.close()
    return account_id, contact_id, second_contact_id, partner_id, partner_contact_id, outreach_id


def main():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["PIPEFLOW_DATA_DIR"] = tmp
        os.environ.pop("DATABASE_URL", None)
        os.environ["PIPEFLOW_SECRET_KEY"] = "pipeflow-smoke-test-key"

        import app as pipeflow_app
        import db_compat

        assert_ok(
            {"outreach_recipients", "audit_entries"}.issubset(db_compat.USER_TABLES),
            "tenant workspace tables missing from Postgres compatibility layer",
        )
        assert_ok(
            len(pipeflow_app.diagnostic_error_code("OUTREACH-ADD")) <= 10,
            "diagnostic error code is too long",
        )

        client = pipeflow_app.app.test_client()
        for path in ("/login", "/register", "/forgot-password"):
            response = client.get(path)
            assert_ok(response.status_code == 200, f"{path} returned {response.status_code}")

        response = client.post(
            "/register",
            data={
                "csrf_token": csrf_from_session(client),
                "full_name": "Smoke Test Admin",
                "email": "smoke-test@example.com",
                "password": "Password123!",
                "reset_phrase": "smoke test secret phrase",
            },
            follow_redirects=True,
        )
        assert_ok(response.status_code == 200, f"register returned {response.status_code}")
        assert_ok(client.get("/health/version").status_code == 200, "health/version failed")

        response = client.post(
            "/logout",
            data={"csrf_token": csrf_from_session(client)},
            follow_redirects=True,
        )
        assert_ok(response.status_code == 200 and "Sign In" in response.get_data(as_text=True), "logout failed")
        response = client.post(
            "/login",
            data={
                "csrf_token": "stale-token-after-deploy",
                "email": "smoke-test@example.com",
                "password": "Password123!",
            },
            follow_redirects=True,
        )
        assert_ok(response.status_code == 200 and "Dashboard" in response.get_data(as_text=True), "stale-token login recovery failed")

        db_path = Path(tmp) / "users" / "1" / "pipeflow.db"
        account_id, contact_id, second_contact_id, partner_id, partner_contact_id, outreach_id = seed_validation_data(db_path)
        today = date.today()
        yesterday = (today - timedelta(days=1)).isoformat()
        tomorrow = (today + timedelta(days=1)).isoformat()

        pages = {
            "/": "Dashboard",
            "/accounts": "Accounts",
            f"/accounts/{account_id}": "Smoke Test Account",
            "/contacts": "Contacts",
            f"/contacts/{contact_id}": "Smoke Test Contact",
            "/partners": "Partners",
            f"/partners/{partner_id}": "Smoke Test Partner",
            "/outreach": "Outreach",
            f"/outreach/{outreach_id}": "Smoke test outreach",
            "/outreach/add": "Add Outreach",
            "/outreach/campaign-builder": "Campaign Builder",
            "/reports": "Reports",
            "/reports/accounts": "Account Reports",
            "/reports/contacts": "Contact Reports",
            "/reports/outreach": "Outreach Reports",
            "/search?q=Smoke": "Global Search",
            "/profile": "Profile",
            "/admin/permissions": "Admin",
        }
        for path, marker in pages.items():
            response = client.get(path)
            html = response.get_data(as_text=True)
            assert_ok(response.status_code == 200 and marker in html, f"{path} failed")

        accounts_html = client.get("/accounts").get_data(as_text=True)
        logo_path = f"/accounts/{account_id}/logo"
        assert_ok(logo_path in accounts_html, "Accounts table logo image source missing")
        logo_response = client.get(logo_path)
        assert_ok(logo_response.status_code == 200, "Account logo image route failed")
        assert_ok(logo_response.content_type.startswith("image/png"), "Account logo route returned the wrong content type")
        assert_ok(logo_response.get_data(), "Account logo route returned no image data")

        account_html = client.get(f"/accounts/{account_id}").get_data(as_text=True)
        add_contact_path = f"/contacts/add?account_id={account_id}"
        assert_ok(add_contact_path in account_html, "Account page Add Contact link is not account-specific")
        add_contact_html = client.get(add_contact_path).get_data(as_text=True)
        assert_ok(f'value="{account_id}"' in add_contact_html and "selected" in add_contact_html, "Add Contact account prefill missing")

        campaign_builder_html = client.get("/outreach/campaign-builder").get_data(as_text=True)
        assert_ok(
            "Smoke Test Play" in campaign_builder_html,
            "Campaign Builder sales play options missing on first load",
        )
        connection = sqlite3.connect(db_path)
        campaign_count_before = connection.execute(
            "SELECT COUNT(*) FROM outreach WHERE campaign = ?",
            ("Smoke Test Play",),
        ).fetchone()[0]
        connection.close()
        campaign_start = (today + timedelta(days=3)).isoformat()
        campaign_end = (today + timedelta(days=14)).isoformat()
        pg_week_start = (today + timedelta(days=21)).isoformat()
        response = client.post(
            "/outreach/campaign-builder",
            data={
                "csrf_token": csrf_from_session(client),
                "account_id": str(account_id),
                "pg_week_start": pg_week_start,
                "campaign_start_date": campaign_start,
                "campaign_end_date": campaign_end,
                "total_outreach_tasks": "3",
                "times_per_week": "2",
                "sales_play": "Smoke Test Play",
                "fy": "27",
                "quarter": "Q1",
                "assigned_to": "Smoke Test Admin",
            },
            follow_redirects=False,
        )
        assert_ok(
            response.status_code in (302, 303)
            and "/outreach" in response.headers.get("Location", ""),
            "Campaign Builder did not redirect to Outreach after save",
        )
        connection = sqlite3.connect(db_path)
        campaign_count_after = connection.execute(
            "SELECT COUNT(*) FROM outreach WHERE campaign = ?",
            ("Smoke Test Play",),
        ).fetchone()[0]
        campaign_recipient_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM outreach_recipients
            WHERE outreach_id IN (
                SELECT id
                FROM outreach
                WHERE campaign = ?
            )
            """,
            ("Smoke Test Play",),
        ).fetchone()[0]
        connection.close()
        assert_ok(campaign_count_after > campaign_count_before, "Campaign Builder did not save generated outreach")
        assert_ok(campaign_recipient_count > 0, "Campaign Builder did not save outreach recipients")

        dashboard_html = client.get("/").get_data(as_text=True)
        assert_ok("header-action-stack" in dashboard_html, "header action stack missing")
        assert_ok(
            dashboard_html.index("User Guide") < dashboard_html.index("Release Notes") < dashboard_html.index("<nav"),
            "Release Notes is not stacked below User Guide before the main nav",
        )

        response = client.post(
            f"/tasks/{outreach_id}/update",
            data={
                "csrf_token": csrf_from_session(client),
                "return_to": "/",
                "next_action": "Updated smoke follow up",
                "next_action_date": "2026-05-06",
                "next_action_time": "11:30",
                "task_status": "In Progress",
                "outcome": "Meeting Booked",
                "notes": "Updated from smoke test",
            },
            follow_redirects=False,
        )
        assert_ok(response.status_code in (302, 303), "dashboard task update failed")

        response = client.get("/outreach/add")
        add_html = response.get_data(as_text=True)
        for outcome in ("NBM Booked", "Discovery Booked", "Exec Meeting Booked"):
            assert_ok(outcome in add_html, f"{outcome} outcome missing from Outreach form")

        response = client.get(f"/outreach/add?account_id={account_id}")
        prefill_account_html = response.get_data(as_text=True)
        assert_ok(
            response.status_code == 200
            and f'value="{account_id}" selected' in prefill_account_html,
            "account quick-create Outreach prefill missing",
        )

        response = client.get(f"/outreach/add?account_id={account_id}&contact_id={contact_id}")
        prefill_contact_html = response.get_data(as_text=True)
        assert_ok(
            response.status_code == 200
            and f'value="{account_id}" selected' in prefill_contact_html
            and f'value="{contact_id}"' in prefill_contact_html
            and "checked" in prefill_contact_html,
            "contact quick-create Outreach prefill missing",
        )

        response = client.get("/admin/permissions")
        admin_html = response.get_data(as_text=True)
        assert_ok(
            response.status_code == 200
            and "broadcast-company-dropdown" in admin_html
            and "admin-company-multiselect" in admin_html,
            "admin company membership or broadcast controls missing",
        )

        response = client.post(
            "/admin/tenants",
            data={
                "csrf_token": csrf_from_session(client),
                "company_name": "Smoke Other Company",
                "country": "United Kingdom",
                "company_contact": "Smoke Tenant Owner",
            },
            follow_redirects=True,
        )
        assert_ok(response.status_code == 200, "tenant create failed")

        response = client.post(
            "/admin/users/create",
            data={
                "csrf_token": csrf_from_session(client),
                "full_name": "Smoke Multi Company Admin",
                "email": "smoke-multi-admin@example.com",
                "password": "Password123!",
                "reset_phrase": "multi company phrase",
                "company": "PipeFlow Administration",
                "company_memberships": ["PipeFlow Administration", "Smoke Other Company"],
                "role": "admin",
                "team_ids": [],
            },
            follow_redirects=True,
        )
        assert_ok(response.status_code == 200, "multi-company admin create failed")

        response = client.post(
            "/admin/broadcasts/add",
            data={
                "csrf_token": csrf_from_session(client),
                "title": "Smoke broadcast",
                "message": "Smoke test message",
                "severity": "info",
                "target_companies": ["PipeFlow Administration", "Smoke Other Company"],
                "start_at": f"{yesterday}T09:00",
                "stop_at": f"{tomorrow}T09:00",
                "is_active": "1",
            },
            follow_redirects=True,
        )
        broadcast_create_html = response.get_data(as_text=True)
        assert_ok(response.status_code == 200 and "Smoke broadcast" in broadcast_create_html, "broadcast create failed")
        assert_ok(
            "Save Changes" in broadcast_create_html
            and "Pause Broadcast" in broadcast_create_html
            and "Delete Broadcast" in broadcast_create_html,
            "broadcast edit action buttons are not grouped on existing broadcasts",
        )

        import auth as pipeflow_auth

        auth_connection = pipeflow_auth.get_auth_connection()
        multi_admin = auth_connection.execute(
            "SELECT id FROM users WHERE email = ?",
            ("smoke-multi-admin@example.com",),
        ).fetchone()
        smoke_broadcast = auth_connection.execute(
            "SELECT id, target_companies FROM broadcast_messages WHERE title = ?",
            ("Smoke broadcast",),
        ).fetchone()
        auth_connection.close()
        assert_ok(multi_admin is not None, "multi-company admin user not found")
        assert_ok(
            set(pipeflow_auth.user_company_names(multi_admin["id"], include_primary=True)) >= {"PipeFlow Administration", "Smoke Other Company"},
            "multi-company admin memberships were not saved",
        )
        assert_ok(smoke_broadcast is not None, "created broadcast not found")

        response = client.post(
            f"/admin/broadcasts/{smoke_broadcast['id']}/update",
            data={
                "csrf_token": csrf_from_session(client),
                "title": "Smoke broadcast updated",
                "message": "Smoke test message updated",
                "severity": "warning",
                "target_companies": ["Smoke Other Company"],
                "start_at": f"{yesterday}T10:00",
                "stop_at": f"{tomorrow}T10:00",
                "is_active": "1",
            },
            follow_redirects=True,
        )
        assert_ok(response.status_code == 200 and "Smoke broadcast updated" in response.get_data(as_text=True), "broadcast update failed")

        updated_broadcast = pipeflow_auth.get_broadcast_message(smoke_broadcast["id"])
        assert_ok(
            pipeflow_auth.decode_broadcast_companies(updated_broadcast["target_companies"]) == ["Smoke Other Company"],
            "broadcast company targets were not updated",
        )

        response = client.post(
            "/outreach/add",
            data={
                "csrf_token": csrf_from_session(client),
                "fy": "27",
                "quarter": "Q1",
                "account_id": str(account_id),
                "sales_play": "Smoke Test Play",
                "contact_ids": [str(contact_id), str(second_contact_id)],
                "task_status": "Not Started",
                "assigned_to": "Smoke Test Admin",
                "activity_type": "Call",
                "activity_date": "2026-05-07",
                "activity_time": "09:00",
                "next_action_date": "2026-05-08",
                "next_action_time": "10:00",
                "subject": "Smoke multi-contact outreach",
                "outcome": "NBM Booked",
                "scheduled_meeting_at": "2026-05-12T09:30",
                "next_action": "",
            },
            follow_redirects=False,
        )
        assert_ok(response.status_code in (302, 303), "multi-contact outreach add failed")

        response = client.post(
            "/outreach/add",
            data={
                "csrf_token": csrf_from_session(client),
                "fy": "27",
                "quarter": "Q1",
                "account_id": str(account_id),
                "sales_play": "Smoke Test Play",
                "contact_ids": [f"partner_contact:{partner_contact_id}"],
                "task_status": "Not Started",
                "assigned_to": "Smoke Test Admin",
                "activity_type": "Meeting",
                "activity_date": "2026-05-13",
                "activity_time": "09:00",
                "next_action_date": "2026-05-20",
                "next_action_time": "10:00",
                "subject": "Smoke account representative meeting outreach",
                "outcome": "Positive Response",
                "next_action": "",
            },
            follow_redirects=False,
        )
        assert_ok(response.status_code in (302, 303), "account representative meeting Outreach add failed")
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        representative_outreach = connection.execute(
            "SELECT partner_contact_id FROM outreach WHERE subject = ?",
            ("Smoke account representative meeting outreach",),
        ).fetchone()
        connection.close()
        assert_ok(
            representative_outreach is not None
            and str(representative_outreach["partner_contact_id"]) == str(partner_contact_id),
            "account representative meeting Outreach was not saved",
        )

        response = client.post(
            "/outreach/add",
            data={
                "csrf_token": csrf_from_session(client),
                "fy": "27",
                "quarter": "Q1",
                "account_id": str(account_id),
                "sales_play": "Smoke Test Play",
                "contact_ids": ["partner_contact:not-a-number"],
                "task_status": "Not Started",
                "assigned_to": "Smoke Test Admin",
                "activity_type": "Meeting",
                "activity_date": "2026-05-13",
                "activity_time": "09:30",
                "next_action_date": "2026-05-20",
                "next_action_time": "10:30",
                "subject": "Smoke malformed representative outreach",
                "outcome": "Positive Response",
            },
            follow_redirects=True,
        )
        malformed_html = response.get_data(as_text=True)
        assert_ok(
            response.status_code == 200 and "Select a contact or partner contact" in malformed_html,
            "malformed representative id did not return validation",
        )

        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        other_account_id = connection.execute(
            """
            INSERT INTO accounts (
                account_name, pg_bible_order, account_tier, industry, business_unit,
                country, city, website, pipeline_target, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Smoke Other Account",
                2,
                "2",
                "Technology",
                "BMC",
                "United Kingdom",
                "London",
                "https://other.example.com",
                250000,
                "Smoke test other account",
            ),
        ).lastrowid
        other_contact_id = connection.execute(
            """
            INSERT INTO contacts (account_id, category, name, job_title, email, phone, location)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (other_account_id, "Technical", "Smoke Other Contact", "Architect", "other@example.com", "55555", "London"),
        ).lastrowid
        connection.commit()
        multi_outreach = connection.execute(
            "SELECT * FROM outreach WHERE subject = ?",
            ("Smoke multi-contact outreach",),
        ).fetchone()
        assert_ok(multi_outreach is not None, "multi-contact outreach was not saved")
        assert_ok(str(multi_outreach["contact_id"]) == str(contact_id), "primary outreach contact was not preserved")
        assert_ok(multi_outreach["outcome"] == "NBM Booked", "NBM Booked outcome was not saved")
        recipient_count = connection.execute(
            "SELECT COUNT(*) FROM outreach_recipients WHERE outreach_id = ?",
            (multi_outreach["id"],),
        ).fetchone()[0]
        connection.close()
        assert_ok(recipient_count == 2, "multi-contact outreach recipients were not saved")

        connection = sqlite3.connect(db_path)
        connection.execute("DROP TABLE outreach_recipients")
        connection.commit()
        connection.close()
        response = client.post(
            "/outreach/add",
            data={
                "csrf_token": csrf_from_session(client),
                "fy": "27",
                "quarter": "Q1",
                "account_id": str(account_id),
                "sales_play": "Smoke Test Play",
                "contact_ids": [str(contact_id)],
                "task_status": "Not Started",
                "assigned_to": "Smoke Test Admin",
                "activity_type": "Email",
                "activity_date": "2026-05-09",
                "activity_time": "08:15",
                "next_action_date": "2026-05-10",
                "next_action_time": "09:15",
                "subject": "Smoke schema-refresh outreach",
                "outcome": "No Response",
                "next_action": "Retry after schema refresh",
            },
            follow_redirects=False,
        )
        assert_ok(response.status_code in (302, 303), "schema-refresh Outreach add failed")
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        recovered_outreach = connection.execute(
            "SELECT id FROM outreach WHERE subject = ?",
            ("Smoke schema-refresh outreach",),
        ).fetchone()
        recovered_recipients = connection.execute(
            "SELECT COUNT(*) FROM outreach_recipients WHERE outreach_id = ?",
            (recovered_outreach["id"] if recovered_outreach else None,),
        ).fetchone()[0]
        connection.close()
        assert_ok(recovered_outreach is not None, "schema-refresh Outreach was not saved")
        assert_ok(recovered_recipients == 1, "schema-refresh Outreach recipient was not saved")

        connection = sqlite3.connect(db_path)
        connection.execute("DROP TABLE audit_entries")
        connection.commit()
        connection.close()
        response = client.post(
            "/outreach/add",
            data={
                "csrf_token": csrf_from_session(client),
                "fy": "27",
                "quarter": "Q1",
                "account_id": str(account_id),
                "sales_play": "Smoke Test Play",
                "contact_ids": [str(contact_id)],
                "task_status": "Not Started",
                "assigned_to": "Smoke Test Admin",
                "activity_type": "Email",
                "activity_date": "2026-05-09",
                "activity_time": "08:45",
                "next_action_date": "2026-05-10",
                "next_action_time": "09:45",
                "subject": "Smoke audit recovery outreach",
                "outcome": "No Response",
                "next_action": "Audit recovery should not block save",
            },
            follow_redirects=False,
        )
        assert_ok(response.status_code in (302, 303), "audit recovery Outreach add failed")
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        audit_recovered_outreach = connection.execute(
            "SELECT id FROM outreach WHERE subject = ?",
            ("Smoke audit recovery outreach",),
        ).fetchone()
        connection.close()
        assert_ok(audit_recovered_outreach is not None, "audit recovery Outreach was not saved")

        response = client.post(
            "/outreach/add",
            data={
                "csrf_token": csrf_from_session(client),
                "fy": "27",
                "quarter": "Q1",
                "account_id": str(account_id),
                "sales_play": "Smoke Test Play",
                "contact_ids": [str(other_contact_id)],
                "task_status": "Not Started",
                "assigned_to": "Smoke Test Admin",
                "activity_type": "Call",
                "activity_date": "2026-05-07",
                "activity_time": "09:00",
                "next_action_date": "2026-05-08",
                "next_action_time": "10:00",
                "subject": "Smoke mismatched-contact outreach",
                "outcome": "No Response Yet",
                "next_action": "",
            },
            follow_redirects=True,
        )
        mismatch_html = response.get_data(as_text=True)
        assert_ok(
            response.status_code == 200
            and "Select a contact or partner contact that belongs to the selected account." in mismatch_html,
            "mismatched account/contact outreach was not rejected",
        )

        response = client.get(f"/outreach/{multi_outreach['id']}/edit")
        edit_html = response.get_data(as_text=True)
        assert_ok(
            response.status_code == 200
            and "class=\"checkbox-select\"" in edit_html
            and "name=\"contact_ids\"" in edit_html,
            "edit Outreach multi-contact checkbox field missing",
        )

        response = client.post(
            f"/outreach/{multi_outreach['id']}/edit",
            data={
                "csrf_token": csrf_from_session(client),
                "submit_action": "save",
                "fy": "27",
                "quarter": "Q1",
                "account_id": str(account_id),
                "sales_play": "Smoke Test Play",
                "contact_ids": [str(second_contact_id)],
                "task_status": "In Progress",
                "assigned_to": "Smoke Test Admin",
                "activity_type": "Call",
                "activity_date": "2026-05-07",
                "activity_time": "09:00",
                "next_action_date": "2026-05-08",
                "next_action_time": "10:00",
                "subject": "Smoke multi-contact outreach",
                "outcome": "Exec Meeting Booked",
                "scheduled_meeting_at": "2026-05-13T10:30",
                "next_action": "",
            },
            follow_redirects=False,
        )
        assert_ok(response.status_code in (302, 303), "multi-contact outreach edit failed")

        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        edited_outreach = connection.execute(
            "SELECT * FROM outreach WHERE id = ?",
            (multi_outreach["id"],),
        ).fetchone()
        edited_recipient_count = connection.execute(
            "SELECT COUNT(*) FROM outreach_recipients WHERE outreach_id = ?",
            (multi_outreach["id"],),
        ).fetchone()[0]
        connection.close()
        assert_ok(str(edited_outreach["contact_id"]) == str(second_contact_id), "edited primary contact was not updated")
        assert_ok(edited_outreach["outcome"] == "Exec Meeting Booked", "Exec Meeting Booked outcome was not saved")
        assert_ok(edited_recipient_count == 1, "edited outreach recipients were not replaced")

        response = client.post(
            "/outreach/add",
            data={
                "csrf_token": csrf_from_session(client),
                "fy": "27",
                "quarter": "Q1",
                "account_id": str(account_id),
                "sales_play": "Smoke Test Play",
                "contact_ids": [str(contact_id)],
                "task_status": "Not Started",
                "assigned_to": "Smoke Test Admin",
                "activity_type": "Email",
                "activity_date": "2026-05-14",
                "activity_time": "08:30",
                "next_action_date": "2026-05-15",
                "next_action_time": "09:45",
                "subject": "Smoke complete follow-on source",
                "outcome": "No Response",
                "next_action": "Prepare completion update",
            },
            follow_redirects=False,
        )
        assert_ok(response.status_code in (302, 303), "complete follow-on source outreach add failed")
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        follow_source = connection.execute(
            "SELECT id FROM outreach WHERE subject = ?",
            ("Smoke complete follow-on source",),
        ).fetchone()
        connection.execute("ALTER TABLE outreach DROP COLUMN scheduled_meeting_time")
        connection.commit()
        connection.close()
        assert_ok(follow_source is not None, "complete follow-on source outreach was not saved")

        response = client.post(
            f"/outreach/{follow_source['id']}/edit",
            data={
                "csrf_token": csrf_from_session(client),
                "submit_action": "complete_and_follow",
                "fy": "27",
                "quarter": "Q1",
                "account_id": str(account_id),
                "sales_play": "Smoke Test Play",
                "contact_ids": [str(contact_id)],
                "task_status": "In Progress",
                "assigned_to": "Smoke Test Admin",
                "activity_type": "Email",
                "activity_date": "2026-05-14",
                "activity_time": "08:30",
                "next_action_date": "2026-05-15",
                "next_action_time": "09:45",
                "subject": "Smoke complete follow-on source",
                "outcome": "No Response",
                "next_action": "Completed and creating follow on",
            },
            follow_redirects=False,
        )
        assert_ok(
            response.status_code in (302, 303) and f"/outreach/add?prefill_from={follow_source['id']}" in response.headers.get("Location", ""),
            "complete and create follow-on did not redirect to the prefilled new Outreach form",
        )
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        completed_follow_source = connection.execute(
            "SELECT task_status, scheduled_meeting_time FROM outreach WHERE id = ?",
            (follow_source["id"],),
        ).fetchone()
        connection.close()
        assert_ok(completed_follow_source["task_status"] == "Completed", "complete and follow-on source was not completed")

        response = client.get("/outreach")
        outreach_html = response.get_data(as_text=True)
        assert_ok("bulk_next_action_date" in outreach_html, "bulk Outreach due-date control missing")
        assert_ok("next_action_date_" in outreach_html, "inline Outreach due-date control missing")
        assert_ok('data-select-all="bulk-outreach-form"' in outreach_html, "bulk Outreach select-all control missing")
        assert_ok("outreach-auto-reschedule-form" in outreach_html, "row Outreach auto-reschedule control missing")

        connection = sqlite3.connect(db_path)
        connection.execute("DROP TABLE timeline_entries")
        connection.commit()
        connection.close()
        response = client.post(
            f"/outreach/{multi_outreach['id']}/due-date",
            data={
                "csrf_token": csrf_from_session(client),
                "return_to": "/outreach",
                "next_action_date": "2026-05-09",
                "next_action_time": "12:15",
            },
            follow_redirects=False,
        )
        assert_ok(response.status_code in (302, 303), "inline Outreach due-date update failed")

        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        inline_due = connection.execute(
            "SELECT next_action_date, next_action_time FROM outreach WHERE id = ?",
            (multi_outreach["id"],),
        ).fetchone()
        connection.close()
        assert_ok(inline_due["next_action_date"] == "2026-05-09", "inline due date was not saved")
        assert_ok(inline_due["next_action_time"] == "12:15", "inline due time was not saved")

        blocked_contact_dates = []
        candidate_day = date.today()
        while len(blocked_contact_dates) < 3:
            if candidate_day.weekday() < 5:
                blocked_contact_dates.append(candidate_day.isoformat())
            candidate_day += timedelta(days=1)
        connection = sqlite3.connect(db_path)
        for index, blocked_date in enumerate(blocked_contact_dates, start=1):
            connection.execute(
                """
                INSERT INTO outreach (
                    fy, quarter, account_id, contact_id, campaign, sales_play,
                    activity_date, activity_time, activity_type, subject, outcome,
                    next_action, next_action_date, next_action_time, task_status, assigned_to
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "27",
                    "Q1",
                    account_id,
                    second_contact_id,
                    "Smoke Test Play",
                    "Smoke Test Play",
                    blocked_date,
                    "09:00",
                    "Email",
                    f"Smoke contact date blocker {index}",
                    "No Response",
                    "Blocking same-contact date",
                    blocked_date,
                    "09:00",
                    "Not Started",
                    "Smoke Test Admin",
                ),
            )
        connection.commit()
        connection.close()

        response = client.post(
            f"/outreach/{multi_outreach['id']}/auto-reschedule",
            data={
                "csrf_token": csrf_from_session(client),
                "return_to": "/outreach",
            },
            follow_redirects=False,
        )
        assert_ok(response.status_code in (302, 303), "single Outreach auto-reschedule failed")
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        auto_due = connection.execute(
            "SELECT next_action_date, next_action_time FROM outreach WHERE id = ?",
            (multi_outreach["id"],),
        ).fetchone()
        connection.close()
        assert_ok(auto_due["next_action_date"] and auto_due["next_action_time"], "single auto-reschedule did not set a due slot")
        assert_ok(date.fromisoformat(auto_due["next_action_date"]).weekday() < 5, "single auto-reschedule selected a weekend")
        assert_ok(auto_due["next_action_date"] not in blocked_contact_dates, "single auto-reschedule selected a date already used by the same contact")

        response = client.post(
            "/outreach/bulk-action",
            data={
                "csrf_token": csrf_from_session(client),
                "return_to": "/outreach",
                "bulk_action": "auto_reschedule",
                "selected_ids": [str(outreach_id), str(multi_outreach["id"])],
            },
            follow_redirects=False,
        )
        assert_ok(response.status_code in (302, 303), "bulk Outreach auto-reschedule failed")
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        auto_bulk_rows = connection.execute(
            "SELECT id, next_action_date, next_action_time FROM outreach WHERE id IN (?, ?) ORDER BY id",
            (outreach_id, multi_outreach["id"]),
        ).fetchall()
        connection.close()
        auto_bulk_slots = {(row["next_action_date"], row["next_action_time"]) for row in auto_bulk_rows}
        assert_ok(len(auto_bulk_rows) == 2 and len(auto_bulk_slots) == 2, "bulk auto-reschedule created clashing due slots")
        assert_ok(all(date.fromisoformat(row["next_action_date"]).weekday() < 5 for row in auto_bulk_rows), "bulk auto-reschedule selected a weekend")

        connection = sqlite3.connect(db_path)
        connection.execute("ALTER TABLE outreach DROP COLUMN scheduled_meeting_time")
        connection.commit()
        connection.close()
        response = client.post(
            "/outreach/add",
            data={
                "csrf_token": csrf_from_session(client),
                "fy": "27",
                "quarter": "Q1",
                "account_id": str(account_id),
                "sales_play": "Smoke Test Play",
                "contact_ids": [str(contact_id)],
                "task_status": "Not Started",
                "assigned_to": "Smoke Test Admin",
                "activity_type": "Email",
                "activity_date": "2026-05-11",
                "activity_time": "08:45",
                "next_action_date": "2026-05-12",
                "next_action_time": "09:15",
                "subject": "Smoke schema recovery outreach",
                "outcome": "No Response",
                "next_action": "Try a different route",
            },
            follow_redirects=False,
        )
        assert_ok(response.status_code in (302, 303), "schema recovery outreach add failed")
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        recovered_outreach = connection.execute(
            "SELECT scheduled_meeting_time FROM outreach WHERE subject = ?",
            ("Smoke schema recovery outreach",),
        ).fetchone()
        connection.close()
        assert_ok(recovered_outreach is not None, "schema recovery outreach was not saved")

        response = client.post(
            "/outreach/bulk-action",
            data={
                "csrf_token": csrf_from_session(client),
                "return_to": "/outreach",
                "bulk_action": "update_due",
                "selected_ids": [str(outreach_id), str(multi_outreach["id"])],
                "bulk_next_action_date": "2026-05-10",
                "bulk_next_action_time": "14:45",
            },
            follow_redirects=False,
        )
        assert_ok(response.status_code in (302, 303), "bulk Outreach due-date update failed")

        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        bulk_due_rows = connection.execute(
            "SELECT next_action_date, next_action_time FROM outreach WHERE id IN (?, ?) ORDER BY id",
            (outreach_id, multi_outreach["id"]),
        ).fetchall()
        connection.close()
        assert_ok(
            all(row["next_action_date"] == "2026-05-10" and row["next_action_time"] == "14:45" for row in bulk_due_rows),
            "bulk due date was not saved for selected outreach tasks",
        )

        for path in (
            "/reports/accounts/export",
            "/reports/contacts/export",
            "/reports/outreach/export",
            "/outreach/export",
        ):
            response = client.get(path)
            assert_ok(response.status_code == 200, f"{path} returned {response.status_code}")
            assert_ok(response.headers.get("Content-Disposition"), f"{path} did not download")

        response = client.get("/reports/pg-bible/export")
        assert_ok(response.status_code == 200, f"PG Bible export returned {response.status_code}")
        assert_ok(response.headers.get("Content-Disposition"), "PG Bible did not download")

        response = client.post(
            "/outreach/bulk-action",
            data={
                "csrf_token": csrf_from_session(client),
                "return_to": "/outreach",
                "bulk_action": "delete",
                "selected_ids": [str(outreach_id), str(multi_outreach["id"])],
            },
            follow_redirects=False,
        )
        assert_ok(response.status_code in (302, 303), "bulk Outreach delete failed")

        connection = sqlite3.connect(db_path)
        remaining_outreach = connection.execute(
            "SELECT COUNT(*) FROM outreach WHERE id IN (?, ?)",
            (outreach_id, multi_outreach["id"]),
        ).fetchone()[0]
        remaining_recipients = connection.execute(
            "SELECT COUNT(*) FROM outreach_recipients WHERE outreach_id IN (?, ?)",
            (outreach_id, multi_outreach["id"]),
        ).fetchone()[0]
        connection.close()
        assert_ok(remaining_outreach == 0, "bulk Outreach delete did not remove selected tasks")
        assert_ok(remaining_recipients == 0, "bulk Outreach delete did not remove selected recipients")

    print("PipeFlow smoke test passed.")


if __name__ == "__main__":
    main()
