from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

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

from excel_exporter import PGBibleExporter
from models import PGBibleExportError
from pipeflow_client import PipeFlowClient, load_report_from_csv, load_report_from_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export PipeFlow PG Bible workbook")
    parser.add_argument("--template", required=True, help="Path to PG Bible FY27.xlsx")
    parser.add_argument("--output-dir", default="outputs", help="Directory for the exported workbook")
    parser.add_argument("--json", help="JSON export file to use as input")
    parser.add_argument("--csv", help="CSV export file to use as input")
    parser.add_argument("--api", action="store_true", help="Use PIPEFLOW_BASE_URL and PIPEFLOW_API_TOKEN")
    parser.add_argument("--reporting-date", default=date.today().isoformat(), help="Reporting date in YYYY-MM-DD format")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    
    parser.add_argument(
    "--check",
    action="store_true",
    help="Check inputs and template, but do not create an output file",
)
    
    try:
        if args.json:
            report = load_report_from_json(args.json)
        elif args.csv:
            report = load_report_from_csv(args.csv)
        elif args.api:
            report = PipeFlowClient().build_report()
        else:
            raise ValueError("Choose one input mode: --json, --csv, or --api")

        exporter = PGBibleExporter(args.template, args.output_dir)
        output = exporter.export(report, reporting_date=date.fromisoformat(args.reporting_date))
        print(f"output file: {output}")
        return 0
    except PGBibleExportError as exc:
        print(json.dumps(exc.as_dict(), indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
