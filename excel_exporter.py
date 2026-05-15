from __future__ import annotations

import copy
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

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

from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from models import GoalsSummary, OwnerReport, PGBibleExportError


SECTION_LABELS = ["PG GOALS", "PG PLAN", "PG ACTIONS", "PG RESULTS"]
MAY_2026_SECTION_LABELS = ["PG GOALS", "PG PLAN", "PG ACTIONS"]
INVALID_SHEET_CHARS = r"[]:*?/\\"
NBM_COLOURS = {
    0: ("D90000", "FFFFFF"),
    1: ("F00000", "FFFFFF"),
    2: ("FFC000", "FFFFFF"),
    3: ("FFF200", "111111"),
    4: ("92D050", "111111"),
    5: ("00B050", "FFFFFF"),
    6: ("00B0F0", "FFFFFF"),
    7: ("0070C0", "FFFFFF"),
    8: ("002060", "FFFFFF"),
    9: ("000000", "FFFFFF"),
    10: ("7F7F7F", "FFFFFF"),
    11: ("595959", "FFFFFF"),
}
MONTH_ORDER = {
    "april": 1,
    "may": 2,
    "june": 3,
    "july": 4,
    "august": 5,
    "september": 6,
    "october": 7,
    "november": 8,
    "december": 9,
    "january": 10,
    "february": 11,
    "march": 12,
}
QUARTER_MARKERS = {"Q1 Results", "Q2 Results", "Q3 Results", "Q4 Results"}


@dataclass
class Section:
    label: str
    row: int
    column: int


@dataclass
class TableRegion:
    name: str
    header_rows: set[int]
    columns: dict[str, int]
    start_row: int
    end_row: int


@dataclass
class WeeklyKey:
    column: int
    header: str
    data_type: str


def norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def sanitize_excel_name(name: str) -> str:
    cleaned = "".join(ch for ch in (name or "PipeFlow") if ch not in INVALID_SHEET_CHARS).strip()
    return (cleaned or "PipeFlow")[:31]


def sanitize_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value or "PipeFlow").strip("_")
    return cleaned or "PipeFlow"


def decimal_value(value: Any) -> Decimal:
    if value in (None, ""):
        raise PGBibleExportError("CALC_INPUT_MISSING", "A required calculation input is missing.", ["empty value"])
    return Decimal(str(value).replace("$", "").replace(",", ""))


def compute_starting_pipeline(reporting_date: date, pipeflow_payload: dict[str, Any]) -> Decimal:
    if "starting_pipeline" not in pipeflow_payload:
        raise PGBibleExportError(
            "CALC_INPUT_MISSING",
            "Starting pipeline cannot be calculated because required inputs are missing.",
            ["starting_pipeline"],
        )
    return decimal_value(pipeflow_payload["starting_pipeline"])


def compute_pipeline_added(fy_start: date, reporting_date: date, pipeflow_payload: dict[str, Any]) -> Decimal:
    if "pipeline_added" not in pipeflow_payload:
        raise PGBibleExportError(
            "CALC_INPUT_MISSING",
            "Pipeline added cannot be calculated because required inputs are missing.",
            ["pipeline_added"],
        )
    return decimal_value(pipeflow_payload["pipeline_added"])


def compute_pipeline_target(fy_window: str, pipeflow_payload: dict[str, Any]) -> Decimal:
    if "pipeline_target" not in pipeflow_payload:
        raise PGBibleExportError(
            "CALC_INPUT_MISSING",
            "Pipeline target cannot be calculated because required inputs are missing.",
            ["pipeline_target"],
        )
    return decimal_value(pipeflow_payload["pipeline_target"])


def compute_pipeline_gap(target: Decimal, starting: Decimal, added: Decimal) -> Decimal:
    return (starting + added) - target


class PGBibleExporter:
    def __init__(self, template_path: str | Path, output_dir: str | Path = "."):
        self.template_path = Path(template_path)
        self.output_dir = Path(output_dir)
        self.sections: dict[str, Section] = {}
        self.header_cache: dict[str, TableRegion] = {}
        self.weekly_key: WeeklyKey | None = None

    def export(self, report: OwnerReport, reporting_date: date | None = None) -> Path:
        reporting_date = reporting_date or date.today()
        wb = load_workbook(self.template_path, data_only=False)

        template_sheet_name = "Real example" if "Real example" in wb.sheetnames else ("Name" if "Name" in wb.sheetnames else None)
        if template_sheet_name is None:
            raise PGBibleExportError(
                "TEMPLATE_SHEET_MISSING",
                "The template workbook is missing a supported PG Bible worksheet.",
                ["Real example", "Name"],
            )

        ws = wb[template_sheet_name]
        for other in list(wb.worksheets):
            if other.title != template_sheet_name:
                wb.remove(other)

        final_sheet_name = sanitize_excel_name(report.profile.profile_name)
        ws.title = final_sheet_name
        print(f"profile name used: {report.profile.profile_name}")
        print(f"sheet name final: {final_sheet_name}")

        is_may_2026_template = self._is_may_2026_template(ws)
        if is_may_2026_template:
            self._validate_sections(ws, MAY_2026_SECTION_LABELS)
            self._configure_may_2026_mapping()
            self._prepare_may_2026_capacity(ws, report)
            baseline = self._structural_snapshot(ws)
            self._clear_may_2026_template(ws)
            self._write_may_2026_goals(ws, report)
            plan_count = self._write_may_2026_plan(ws, report)
            action_count = self._write_may_2026_actions(ws, report)
            weekly_count = 0
        else:
            self._validate_sections(ws)
            self._validate_tables(ws)
            baseline = self._structural_snapshot(ws)
            report.goals = report.goals or self._compute_goals(report, reporting_date)

            self._clear_goals(ws)
            self._clear_table(ws, self.header_cache["PG PLAN"])
            self._clear_table(ws, self.header_cache["PG ACTIONS"])
            self._clear_weekly_rows(ws, self.header_cache["PG RESULTS"])

            self._write_goals(ws, report.goals)
            plan_count = self._write_plan(ws, report)
            action_count = self._write_actions(ws, report)
            weekly_count = self._write_weekly_results(ws, report)

        print(f"plan rows written: {plan_count}")
        print(f"action rows written: {action_count}")
        print(f"weekly rows written: {weekly_count}")

        output_path = self.output_dir / f"PGBible_{sanitize_filename(report.profile.username)}.xlsx"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if is_may_2026_template:
            baseline = self._structural_snapshot(ws)
        self._self_check(ws, baseline)
        wb.save(output_path)
        saved_wb = load_workbook(output_path, data_only=False)
        self._self_check(saved_wb[final_sheet_name], baseline)
        return output_path

    def _compute_goals(self, report: OwnerReport, reporting_date: date) -> GoalsSummary:
        fy_start = date(reporting_date.year if reporting_date.month >= 4 else reporting_date.year - 1, 4, 1)
        fy_window = f"{fy_start.isoformat()} to {date(fy_start.year + 1, 3, 31).isoformat()}"
        starting = compute_starting_pipeline(reporting_date, report.calc_payload)
        added = compute_pipeline_added(fy_start, reporting_date, report.calc_payload)
        target = compute_pipeline_target(fy_window, report.calc_payload)
        gap = compute_pipeline_gap(target, starting, added)
        print(f"calculation starting_pipeline input: {starting}")
        print(f"calculation pipeline_added input: {added}")
        print(f"calculation pipeline_target input: {target}")
        print(f"calculation pipeline_gap output: {gap}")
        return GoalsSummary(starting_pipeline=starting, pipeline_added=added, pipeline_target=target, pipeline_gap=gap)

    def _is_may_2026_template(self, ws) -> bool:
        return bool(self._find_exact(ws, "FY Current Pipeline")) and not bool(self._find_exact(ws, "PG RESULTS"))

    def _configure_may_2026_mapping(self) -> None:
        self.header_cache["PG PLAN"] = TableRegion(
            "PG PLAN",
            {8, 9},
            {
                "nbm_target": 2,
                "sales_play": 4,
                "customer": 12,
                "estimated_value": 13,
            },
            11,
            29,
        )
        self.header_cache["PG ACTIONS"] = TableRegion(
            "PG ACTIONS",
            {31, 32},
            {
                "related_nbm_target": 2,
                "account_contact": 3,
                "discovery_completed": 6,
                "discovery_next_action": 7,
                "nbm_booked": 16,
                "exec_first": 14,
            },
            33,
            79,
        )

    def _validate_sections(self, ws, labels: list[str] | None = None) -> None:
        missing = []
        for label in labels or SECTION_LABELS:
            matches = self._find_exact(ws, label)
            if not matches:
                missing.append(label)
            elif len(matches) > 1:
                raise PGBibleExportError("SECTION_MISSING", "A section label is ambiguous.", [label])
            else:
                cell = matches[0]
                self.sections[label] = Section(label, cell.row, cell.column)

        if missing:
            raise PGBibleExportError("SECTION_MISSING", "The template is missing one or more required sections.", missing)

    def _clear_may_2026_template(self, ws) -> None:
        for coordinate in ("F3", "L3"):
            cell = ws[coordinate]
            if not self._is_formula(cell):
                cell.value = None
        self._clear_mapped_rows(ws, 11, 29, range(2, 14))
        action_region = self.header_cache["PG ACTIONS"]
        self._clear_mapped_rows(ws, action_region.start_row, action_region.end_row, range(2, 21))

    def _prepare_may_2026_capacity(self, ws, report: OwnerReport) -> None:
        plan_region = self.header_cache["PG PLAN"]
        self._ensure_capacity(ws, plan_region, len(report.plan_items))
        self._sync_following_region_after_insert("PG ACTIONS", plan_region)
        self._ensure_capacity(ws, self.header_cache["PG ACTIONS"], len(report.action_items))

    def _clear_mapped_rows(self, ws, start_row: int, end_row: int, columns) -> None:
        for row in range(start_row, end_row + 1):
            for col in columns:
                cell = ws.cell(row, col)
                if isinstance(cell, MergedCell) or self._is_formula(cell):
                    continue
                cell.value = None

    def _write_may_2026_goals(self, ws, report: OwnerReport) -> None:
        target = report.calc_payload.get("pipeline_target")
        current = report.calc_payload.get("current_pipeline", report.calc_payload.get("starting_pipeline"))
        self._write_value(ws["L3"], decimal_value(target or 0))
        self._write_value(ws["F3"], decimal_value(current or 0))

    def _write_may_2026_plan(self, ws, report: OwnerReport) -> int:
        region = self.header_cache["PG PLAN"]
        rows = sorted(
            report.plan_items,
            key=lambda item: (
                item.pg_bible_order if item.pg_bible_order is not None else 999999,
                item.customer.casefold(),
            ),
        )
        for offset, item in enumerate(rows):
            row = region.start_row + offset
            nbm_value = item.nbm_target or item.pg_bible_order or ""
            self._write_value(ws.cell(row, 2), nbm_value)
            self._apply_nbm_fill(ws.cell(row, 2), nbm_value)
            self._write_value(ws.cell(row, 4), item.sales_play)
            self._format_large_text_cell(ws.cell(row, 4), item.sales_play, 80)
            self._write_value(ws.cell(row, 12), self._join_parts([item.customer, item.customer_business_unit], ", "))
            self._format_large_text_cell(ws.cell(row, 12), self._join_parts([item.customer, item.customer_business_unit], ", "), 35)
            self._write_value(ws.cell(row, 13), item.estimated_value)
            self._expand_row_for_text(ws, row, [4, 12])
        return len(rows)

    def _write_may_2026_actions(self, ws, report: OwnerReport) -> int:
        region = self.header_cache["PG ACTIONS"]
        for offset, item in enumerate(report.action_items):
            row = region.start_row + offset
            nbm_value = item.related_nbm_target or ""
            self._write_value(ws.cell(row, 2), nbm_value)
            self._apply_nbm_fill(ws.cell(row, 2), nbm_value)
            self._write_value(ws.cell(row, 3), item.discovery_target_name_title)
            self._format_large_text_cell(ws.cell(row, 3), item.discovery_target_name_title, 45)
            self._write_value(ws.cell(row, 6), self._yes_no(item.discovery_completed))
            self._write_value(ws.cell(row, 7), item.discovery_next_action)
            self._format_large_text_cell(ws.cell(row, 7), item.discovery_next_action, 55)
            self._write_value(ws.cell(row, 16), self._yes_no_or_na(item.nbm_completed or item.nbm_booked or item.nbm_booked_date))
            self._write_value(ws.cell(row, 14), self._yes_no(item.exec_first))
            self._expand_row_for_text(ws, row, [3, 7])
        return len(report.action_items)

    def _sync_following_region_after_insert(self, following_region_name: str, preceding_region: TableRegion) -> None:
        following = self.header_cache.get(following_region_name)
        if not following:
            return
        expected_start = 33
        shift = preceding_region.end_row - 29
        following.header_rows = {row + shift for row in {31, 32}}
        following.start_row = expected_start + shift
        following.end_row = 79 + shift

    def _apply_nbm_fill(self, cell, value: Any) -> None:
        try:
            colour_index = int(str(value or "0")) % 12
        except ValueError:
            colour_index = 0
        fill_colour, font_colour = NBM_COLOURS[colour_index]
        cell.fill = PatternFill(fill_type="solid", fgColor=fill_colour)
        cell.font = copy.copy(cell.font)
        cell.font = Font(
            name=cell.font.name,
            sz=cell.font.sz,
            b=cell.font.b,
            i=cell.font.i,
            vertAlign=cell.font.vertAlign,
            underline=cell.font.underline,
            strike=cell.font.strike,
            color=font_colour,
        )

    def _validate_tables(self, ws) -> None:
        self.header_cache["PG PLAN"] = self._discover_plan(ws)
        self.header_cache["PG ACTIONS"] = self._discover_actions(ws)
        self.header_cache["PG RESULTS"] = self._discover_results(ws)
        self.weekly_key = self._discover_weekly_key(ws, self.header_cache["PG RESULTS"])
        print(f"Weekly key resolved as: {get_column_letter(self.weekly_key.column)}, data type: {self.weekly_key.data_type}")

    def _discover_plan(self, ws) -> TableRegion:
        return self._discover_header_block(
            ws,
            "PG PLAN",
            "PG ACTIONS",
            {
                "month": ["Month"],
                "marketing_event": ["PG Marketing Event Being Supported"],
                "notes": ["Notes & General PG Actions"],
                "nbm_target": ["NBM Target"],
                "sales_play": ["PG Sales Play or Initative", "PG Sales Play or Initiative"],
                "customer": ["Customer"],
                "estimated_value": ["Estimated Value"],
            },
        )

    def _discover_actions(self, ws) -> TableRegion:
        return self._discover_header_block(
            ws,
            "PG ACTIONS",
            "PG RESULTS",
            {
                "related_nbm_target": ["Related NBM Target"],
                "discovery_target_name_title": ["Targeted or Booked Discovery Meeting (Name & Poistion)", "Targeted or Booked Discovery Meeting (Name & Position)"],
                "discovery_completed": ["Completed Discovery Meeting Yes / No"],
                "discovery_next_action": ["Discovery Meeting Next Action / Notes"],
                "nbm_booked": ["NBM Booked / Date (Name & Position)"],
                "why_buy": ["Why Buy Document Yes / No"],
                "exec_first": ["Exec First Yes / No"],
                "prep_with_manager": ["Preparation With Manager"],
                "nbm_completed": ["Completed NBM Yes / No"],
                "nbm_next_action": ["NBM Next Action / \\Notes", "NBM Next Action / Notes"],
                "vo_value": ["VO Value"],
            },
        )

    def _discover_results(self, ws) -> TableRegion:
        return self._discover_header_block(
            ws,
            "PG RESULTS",
            None,
            {
                "week_number": ["#"],
                "week_commencing": ["WC"],
                "vitos_sent": ["Sent"],
                "vitos_chased": ["Chased"],
                "discovery_booked": ["Booked"],
                "discovery_completed": ["Completed"],
                "nbms_booked": ["Booked"],
                "nbms_exec_firsts": ["Exec Firsts"],
                "nbms_completed": ["Completed"],
                "pipeline_generated_vo_count": ["#VO"],
                "pipeline_generated_value": ["$m"],
            },
            allow_duplicate_labels=True,
        )

    def _discover_header_block(self, ws, section_name: str, next_section_name: str | None, expected: dict[str, list[str]], allow_duplicate_labels: bool = False) -> TableRegion:
        start = self.sections[section_name].row
        end = self.sections[next_section_name].row - 1 if next_section_name else ws.max_row
        search_end = min(end, start + 5)
        columns: dict[str, int] = {}
        header_rows: set[int] = set()
        used_columns: set[int] = set()

        for key, labels in expected.items():
            matches = []
            for row in range(start, search_end + 1):
                for col in range(1, ws.max_column + 1):
                    value = self._merged_value(ws, row, col)
                    if any(norm(value) == norm(label) for label in labels):
                        matches.append((row, col))
            if not matches:
                raise PGBibleExportError("TABLE_HEADER_NOT_FOUND", "A required table header could not be found.", [f"{section_name}: {labels[0]}"])
            chosen = None
            for match in matches:
                if allow_duplicate_labels and match[1] in used_columns:
                    continue
                chosen = match
                break
            if chosen is None:
                chosen = matches[0]
            header_rows.add(chosen[0])
            columns[key] = chosen[1]
            used_columns.add(chosen[1])

        start_row = max(header_rows) + 1
        for merged in ws.merged_cells.ranges:
            if any(merged.min_row <= header_row <= merged.max_row for header_row in header_rows):
                start_row = max(start_row, merged.max_row + 1)

        return TableRegion(section_name, header_rows, columns, start_row, end)

    def _discover_weekly_key(self, ws, region: TableRegion) -> WeeklyKey:
        rows = self._weekly_data_rows(ws, region)
        candidates: list[WeeklyKey] = []
        for col in region.columns.values():
            values = [ws.cell(row, col).value for row in rows if ws.cell(row, col).value not in (None, "")]
            if not values or len(values) != len(set(str(v) for v in values)):
                continue
            if all(isinstance(value, (datetime, date)) for value in values):
                candidates.append(WeeklyKey(col, self._header_for_column(ws, region, col), "date"))
            elif all(isinstance(value, int) and 1 <= value <= 53 for value in values):
                candidates.append(WeeklyKey(col, self._header_for_column(ws, region, col), "int"))

        date_candidates = [candidate for candidate in candidates if candidate.data_type == "date"]
        int_candidates = [candidate for candidate in candidates if candidate.data_type == "int"]
        if len(date_candidates) == 1:
            return date_candidates[0]
        if len(date_candidates) > 1:
            raise PGBibleExportError("WEEK_KEY_AMBIGUOUS", "Multiple weekly date key columns were found.", [c.header for c in date_candidates])
        if len(int_candidates) == 1:
            return int_candidates[0]
        raise PGBibleExportError("WEEK_KEY_AMBIGUOUS", "The weekly key column could not be resolved.", [c.header for c in candidates])

    def _write_goals(self, ws, goals: GoalsSummary) -> None:
        label_map = {
            "FY22 Starting Pipeline Position": goals.starting_pipeline,
            "FY22 Pipeline Added": goals.pipeline_added,
            "FY22 4 Quarter Total Addressable Pipeline TARGET": goals.pipeline_target,
            "FY22 4 Quarter Total Addressable Pipeline GAP": goals.pipeline_gap,
        }
        for label, value in label_map.items():
            cells = self._find_exact(ws, label)
            if cells:
                target = ws.cell(cells[0].row, cells[0].column + 4)
                if not self._is_formula(target):
                    self._write_value(target, value)

    def _write_plan(self, ws, report: OwnerReport) -> int:
        region = self.header_cache["PG PLAN"]
        rows = sorted(
            report.plan_items,
            key=lambda item: (
                MONTH_ORDER.get(norm(item.month), 99),
                item.pg_bible_order if item.pg_bible_order is not None else 999999,
                int(item.account_tier or 99) if str(item.account_tier).isdigit() else 99,
                -float(item.pipeline_target_value or 0),
            ),
        )
        self._ensure_capacity(ws, region, len(rows))
        for offset, item in enumerate(rows):
            row = region.start_row + offset
            mapping = {
                "month": item.month,
                "marketing_event": item.marketing_event,
                "notes": item.notes,
                "nbm_target": item.nbm_target,
                "sales_play": item.sales_play,
                "customer": item.customer,
                "estimated_value": item.estimated_value,
            }
            self._write_mapping(ws, region, row, mapping)
        return len(rows)

    def _write_actions(self, ws, report: OwnerReport) -> int:
        region = self.header_cache["PG ACTIONS"]
        self._ensure_capacity(ws, region, len(report.action_items))
        for offset, item in enumerate(report.action_items):
            row = region.start_row + offset
            discovery_target = item.discovery_target_name_title or " ".join(part for part in [item.person_name, item.person_title] if part)
            nbm_booked = " ".join(part for part in [item.nbm_booked_date, item.nbm_booked_name_title] if part)
            mapping = {
                "related_nbm_target": item.related_nbm_target,
                "discovery_target_name_title": discovery_target,
                "discovery_completed": self._yes_no(item.discovery_completed),
                "discovery_next_action": item.discovery_next_action or item.manager_notes,
                "nbm_booked": nbm_booked,
                "why_buy": self._yes_no(item.why_buy),
                "exec_first": self._yes_no(item.exec_first),
                "prep_with_manager": self._yes_no(item.prep_with_manager),
                "nbm_completed": self._yes_no(item.nbm_completed),
                "nbm_next_action": item.nbm_next_action,
                "vo_value": item.vo_value,
            }
            self._write_mapping(ws, region, row, mapping)
        return len(report.action_items)

    def _write_weekly_results(self, ws, report: OwnerReport) -> int:
        region = self.header_cache["PG RESULTS"]
        key = self.weekly_key
        if key is None:
            raise PGBibleExportError("WEEK_KEY_AMBIGUOUS", "The weekly key column has not been resolved.", [])
        slot_rows = self._weekly_slot_rows(ws, region)
        sorted_results = sorted(report.weekly_results, key=lambda item: self._normal_week_key(item.week_key, key.data_type))
        written = 0
        for index, item in enumerate(sorted_results):
            if index < len(slot_rows):
                row = slot_rows[index]
            else:
                row = self._insert_weekly_row(ws, region)
                slot_rows.append(row)
            self._write_value(ws.cell(row, key.column), self._coerce_week_key(item.week_key, key.data_type))
            mapping = {
                "vitos_sent": item.vitos_sent,
                "vitos_chased": item.vitos_chased,
                "discovery_booked": item.discovery_booked,
                "discovery_completed": item.discovery_completed,
                "nbms_booked": item.nbms_booked,
                "nbms_exec_firsts": item.nbms_exec_firsts,
                "nbms_completed": item.nbms_completed,
                "pipeline_generated_vo_count": item.pipeline_generated_vo_count,
                "pipeline_generated_value": item.pipeline_generated_value,
            }
            self._write_mapping(ws, region, row, mapping)
            written += 1
        return written

    def _clear_goals(self, ws) -> None:
        for label in ["FY22 Starting Pipeline Position", "FY22 Pipeline Added", "FY22 4 Quarter Total Addressable Pipeline TARGET", "FY22 4 Quarter Total Addressable Pipeline GAP"]:
            for cell in self._find_exact(ws, label):
                target = ws.cell(cell.row, cell.column + 4)
                if not self._is_formula(target):
                    target.value = None

    def _clear_table(self, ws, region: TableRegion) -> None:
        for row in range(region.start_row, region.end_row + 1):
            if self._row_contains_any(ws, row, SECTION_LABELS + ["Summary"]):
                break
            for col in set(region.columns.values()):
                cell = ws.cell(row, col)
                if not self._is_formula(cell):
                    self._write_value(cell, None)

    def _clear_weekly_rows(self, ws, region: TableRegion) -> None:
        for row in self._weekly_slot_rows(ws, region):
            for col in set(region.columns.values()):
                cell = ws.cell(row, col)
                if not self._is_formula(cell):
                    self._write_value(cell, None)

    def _weekly_data_rows(self, ws, region: TableRegion) -> list[int]:
        rows = []
        for row in range(region.start_row, region.end_row + 1):
            row_text = self._row_text(ws, row)
            if "Summary" in row_text:
                break
            if any(marker in row_text for marker in QUARTER_MARKERS):
                continue
            if ws.cell(row, region.columns["week_number"]).value not in (None, "") or ws.cell(row, region.columns["week_commencing"]).value not in (None, ""):
                rows.append(row)
        return rows

    def _weekly_slot_rows(self, ws, region: TableRegion) -> list[int]:
        rows = []
        for row in range(region.start_row, region.end_row + 1):
            row_text = self._row_text(ws, row)
            if "Summary" in row_text:
                break
            if any(marker in row_text for marker in QUARTER_MARKERS):
                continue
            rows.append(row)
        return rows

    def _insert_weekly_row(self, ws, region: TableRegion) -> int:
        weekly_rows = self._weekly_slot_rows(ws, region)
        if not weekly_rows:
            raise PGBibleExportError("WRITE_OUT_OF_BOUNDS", "No weekly data row exists to copy formatting from.", [region.name])
        insert_at = weekly_rows[-1] + 1
        ws.insert_rows(insert_at)
        self._copy_row_style(ws, weekly_rows[-1], insert_at)
        region.end_row += 1
        return insert_at

    def _ensure_capacity(self, ws, region: TableRegion, row_count: int) -> None:
        available = region.end_row - region.start_row + 1
        if row_count <= available:
            return
        insert_count = row_count - available
        insert_at = region.end_row + 1
        if self._row_contains_any(ws, insert_at, SECTION_LABELS):
            raise PGBibleExportError("WRITE_OUT_OF_BOUNDS", "The table does not have enough writable rows inside its boundary.", [region.name])
        for _ in range(insert_count):
            ws.insert_rows(insert_at)
            self._copy_row_style(ws, max(region.start_row, insert_at - 1), insert_at)
            region.end_row += 1

    def _write_mapping(self, ws, region: TableRegion, row: int, mapping: dict[str, Any]) -> None:
        if row > region.end_row:
            raise PGBibleExportError("WRITE_OUT_OF_BOUNDS", "A write would exceed the detected table boundary.", [region.name, str(row)])
        for key, value in mapping.items():
            if key in region.columns:
                self._write_value(ws.cell(row, region.columns[key]), value)

    def _write_value(self, cell, value: Any) -> None:
        if isinstance(cell, MergedCell):
            raise PGBibleExportError("WRITE_OUT_OF_BOUNDS", "A write targeted a non-anchor merged cell.", [cell.coordinate])
        if self._is_formula(cell):
            return
        if isinstance(value, Decimal):
            cell.value = float(value)
        else:
            cell.value = value

    def _format_large_text_cell(self, cell, value: Any, chars_per_line: int = 60) -> None:
        cell.alignment = copy.copy(cell.alignment)
        cell.alignment = cell.alignment.copy(
            horizontal="left",
            vertical="top",
            wrap_text=True,
        )

    def _estimated_text_lines(self, value: Any, chars_per_line: int = 60) -> int:
        text = str(value or "")
        if not text:
            return 1
        lines = 0
        for part in text.splitlines() or [""]:
            length = len(part)
            lines += max(1, (length + chars_per_line - 1) // chars_per_line)
        return lines

    def _expand_row_for_text(self, ws, row: int, columns: list[int]) -> None:
        existing_height = ws.row_dimensions[row].height or 18
        estimated_lines = max(self._estimated_text_lines(ws.cell(row, col).value) for col in columns)
        ws.row_dimensions[row].height = max(existing_height, min(180, 16 * estimated_lines + 8))

    def _yes_no(self, value: Any) -> str:
        if value in (None, ""):
            return ""
        text = str(value).strip().casefold()
        if text in {"yes", "y", "true", "1"}:
            return "Yes"
        if text in {"no", "n", "false", "0"}:
            return "No"
        return str(value).strip()

    def _yes_no_or_na(self, value: Any) -> str:
        if value in (None, ""):
            return ""
        text = str(value).strip().casefold()
        if text in {"n/a", "na", "not applicable"}:
            return "N/A"
        return self._yes_no(value)

    def _join_parts(self, parts: list[Any], separator: str) -> str:
        return separator.join(str(part).strip() for part in parts if str(part or "").strip())

    def _coerce_week_key(self, value: Any, data_type: str):
        if data_type == "date" and isinstance(value, str):
            return datetime.fromisoformat(value).date()
        return value

    def _normal_week_key(self, value: Any, data_type: str) -> str:
        value = self._coerce_week_key(value, data_type)
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        return str(value)

    def _self_check(self, ws, baseline: dict[str, Any]) -> None:
        current = self._structural_snapshot(ws)
        mismatches = []
        for key in ["merges", "column_widths", "row_heights", "header_strings"]:
            if current[key] != baseline[key]:
                mismatches.append(key)
        if mismatches:
            raise PGBibleExportError(
                "WRITE_OUT_OF_BOUNDS",
                "The exported sheet structure does not match the cloned template.",
                mismatches,
            )

    def _structural_snapshot(self, ws) -> dict[str, Any]:
        return {
            "merges": sorted(str(rng) for rng in ws.merged_cells.ranges),
            "column_widths": {col: ws.column_dimensions[get_column_letter(col)].width for col in range(1, ws.max_column + 1)},
            "row_heights": {row: ws.row_dimensions[row].height for row in range(1, ws.max_row + 1)},
            "header_strings": self._header_strings(ws),
        }

    def _header_strings(self, ws) -> dict[str, str]:
        protected_rows = set()
        for section in self.sections.values():
            protected_rows.add(section.row)
        for region in self.header_cache.values():
            protected_rows.update(region.header_rows)
        values = {}
        for row in protected_rows:
            for col in range(1, ws.max_column + 1):
                value = ws.cell(row, col).value
                if isinstance(value, str) and value.strip():
                    values[f"{row}:{col}"] = value
        return values

    def _copy_row_style(self, ws, source_row: int, target_row: int) -> None:
        source_merges = [
            merged
            for merged in list(ws.merged_cells.ranges)
            if merged.min_row == source_row and merged.max_row == source_row
        ]
        ws.row_dimensions[target_row].height = ws.row_dimensions[source_row].height
        for col in range(1, ws.max_column + 1):
            source = ws.cell(source_row, col)
            target = ws.cell(target_row, col)
            if source.has_style:
                target._style = copy.copy(source._style)
            if source.number_format:
                target.number_format = source.number_format
        for merged in source_merges:
            target_range = f"{get_column_letter(merged.min_col)}{target_row}:{get_column_letter(merged.max_col)}{target_row}"
            if target_range not in {str(rng) for rng in ws.merged_cells.ranges}:
                ws.merge_cells(target_range)

    def _find_exact(self, ws, text: str):
        matches = []
        target = norm(text)
        for row in ws.iter_rows():
            for cell in row:
                if norm(cell.value) == target:
                    matches.append(cell)
        return matches

    def _merged_value(self, ws, row: int, col: int) -> Any:
        cell = ws.cell(row, col)
        if not isinstance(cell, MergedCell):
            return cell.value
        for merged in ws.merged_cells.ranges:
            if (row, col) in merged.cells:
                return ws.cell(merged.min_row, merged.min_col).value
        return None

    def _row_text(self, ws, row: int) -> str:
        return " ".join(str(ws.cell(row, col).value) for col in range(1, ws.max_column + 1) if ws.cell(row, col).value not in (None, ""))

    def _row_contains_any(self, ws, row: int, needles: list[str]) -> bool:
        text = self._row_text(ws, row)
        return any(needle in text for needle in needles)

    def _header_for_column(self, ws, region: TableRegion, col: int) -> str:
        for row in sorted(region.header_rows, reverse=True):
            value = self._merged_value(ws, row, col)
            if value not in (None, ""):
                return str(value)
        return get_column_letter(col)

    def _is_formula(self, cell) -> bool:
        return isinstance(cell.value, str) and cell.value.startswith("=")
