"""Dedicated Render worker for the 23:00 schedule review."""

import os
import time

os.environ.setdefault("PIPEFLOW_DISABLE_INPROCESS_SCHEDULER", "1")

from app import app, run_due_nightly_schedule_review


def main():
    while True:
        try:
            with app.app_context():
                run_due_nightly_schedule_review()
        except Exception:
            app.logger.exception("Dedicated nightly Outreach scheduler worker failed")
        time.sleep(60)


if __name__ == "__main__":
    main()
