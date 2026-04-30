"""Project-local Python startup customisations.

This makes bundled dependencies available to any Python command launched from
the PipeFlow project folder, including Flask routes, CLI exports, and quick
health checks.
"""

from pathlib import Path
import sys


LOCAL_VENDOR = Path(__file__).resolve().parent / "vendor"
if LOCAL_VENDOR.exists():
    vendor_path = str(LOCAL_VENDOR)
    if vendor_path not in sys.path:
        sys.path.insert(0, vendor_path)
