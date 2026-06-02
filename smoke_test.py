import os
import sqlite3
import tempfile
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
    connection.execute(
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
    return account_id, contact_id, second_contact_id, partner_id, outreach_id


def main():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["PIPEFLOW_DATA_DIR"] = tmp
        os.environ.pop("DATABASE_URL", None)
        os.environ["PIPEFLOW_SECRET_KEY"] = "pipeflow-smoke-test-key"

        import app as pipeflow_app

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

        db_path = Path(tmp) / "users" / "1" / "pipeflow.db"
        account_id, contact_id, second_contact_id, partner_id, outreach_id = seed_validation_data(db_path)

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
            "/reports/tasks": "Task Reports",
            "/search?q=Smoke": "Global Search",
            "/profile": "Profile",
            "/admin/permissions": "Admin",
        }
        for path, marker in pages.items():
            response = client.get(path)
            html = response.get_data(as_text=True)
            assert_ok(response.status_code == 200 and marker in html, f"{path} failed")

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

        response = client.post(
            "/outreach/add",
            data={
                "csrf_token": csrf_from_session(client),
                "fy": "27",
                "quarter": "Q1",
                "account_id": str(account_id),
                "sales_play": "Smoke Multi Contact Play",
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
                "next_action": "",
            },
            follow_redirects=False,
        )
        assert_ok(response.status_code in (302, 303), "multi-contact outreach add failed")

        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
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
                "sales_play": "Smoke Multi Contact Play",
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

        response = client.get("/outreach")
        outreach_html = response.get_data(as_text=True)
        assert_ok("bulk_next_action_date" in outreach_html, "bulk Outreach due-date control missing")
        assert_ok("next_action_date_" in outreach_html, "inline Outreach due-date control missing")

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

        response = client.post(
            "/outreach/bulk-due-date",
            data={
                "csrf_token": csrf_from_session(client),
                "return_to": "/outreach",
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
            "/reports/tasks/export",
            "/outreach/export",
        ):
            response = client.get(path)
            assert_ok(response.status_code == 200, f"{path} returned {response.status_code}")
            assert_ok(response.headers.get("Content-Disposition"), f"{path} did not download")

        response = client.get("/reports/pg-bible/export")
        assert_ok(response.status_code == 200, f"PG Bible export returned {response.status_code}")
        assert_ok(response.headers.get("Content-Disposition"), "PG Bible did not download")

    print("PipeFlow smoke test passed.")


if __name__ == "__main__":
    main()
