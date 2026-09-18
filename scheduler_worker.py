"""Dedicated Render worker for the 23:00 schedule review."""

import os
import time

os.environ.setdefault("PIPEFLOW_DISABLE_INPROCESS_SCHEDULER", "1")

from app import app, run_due_nightly_schedule_review


def main():
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if os.environ.get("PIPEFLOW_REQUIRE_SHARED_DATABASE", "0") == "1" and not database_url:
        app.logger.critical(
            "Dedicated nightly scheduler stopped: DATABASE_URL is missing. "
            "Configure the same shared DATABASE_URL on the web service and this worker."
        )
        raise RuntimeError("PIPEFLOW_REQUIRE_SHARED_DATABASE=1 but DATABASE_URL is not configured")
    app.logger.info(
        "Dedicated nightly Outreach scheduler worker started: timezone=%s interval=60s database_backend=%s",
        os.environ.get("PIPEFLOW_TIMEZONE", "UTC"),
        "postgres" if database_url else "sqlite",
    )
    while True:
        try:
            with app.app_context():
                result = run_due_nightly_schedule_review()
                app.logger.info(
                    "Dedicated nightly Outreach scheduler heartbeat: status=%s run_date=%s updated=%s workspaces=%s detail=%s",
                    result.get("status"),
                    result.get("run_date", ""),
                    result.get("updated", 0),
                    result.get("workspaces", 0),
                    result.get("detail", ""),
                )
        except Exception as exc:
            app.logger.exception("Dedicated nightly Outreach scheduler worker failed")
            app.logger.error("Dedicated nightly Outreach scheduler exception type=%s", type(exc).__name__)
        time.sleep(60)


if __name__ == "__main__":
    main()
