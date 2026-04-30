from __future__ import annotations

import csv
import json
import os
from dataclasses import fields
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib import request

from models import (
    ActionItem,
    OwnerReport,
    PlanItem,
    UserProfile,
    WeeklyResultRow,
)


class PipeFlowClient:
    """Placeholder API client.

    Endpoint paths are intentionally isolated here because the PipeFlow API
    contract is not yet defined.
    """

    def __init__(self, base_url: str | None = None, api_token: str | None = None):
        self.base_url = (base_url or os.environ.get("PIPEFLOW_BASE_URL", "")).rstrip("/")
        self.api_token = api_token or os.environ.get("PIPEFLOW_API_TOKEN", "")

    def _get_json(self, path: str) -> Any:
        if not self.base_url:
            raise RuntimeError("PIPEFLOW_BASE_URL is not configured")

        req = request.Request(f"{self.base_url}{path}")
        if self.api_token:
            req.add_header("Authorization", f"Bearer {self.api_token}")

        with request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def get_profile(self) -> dict[str, Any]:
        return self._get_json("/api/profile")

    def get_accounts(self) -> list[dict[str, Any]]:
        return self._get_json("/api/accounts")

    def get_plan_items(self) -> list[dict[str, Any]]:
        return self._get_json("/api/pg-plan")

    def get_action_items(self) -> list[dict[str, Any]]:
        return self._get_json("/api/pg-actions")

    def get_weekly_results(self) -> list[dict[str, Any]]:
        return self._get_json("/api/pg-results")

    def build_report(self) -> OwnerReport:
        profile_payload = self.get_profile()
        return OwnerReport(
            profile=UserProfile(
                profile_name=profile_payload.get("profile_name") or profile_payload.get("full_name") or "PipeFlow",
                username=profile_payload.get("username") or profile_payload.get("profile_name") or "PipeFlow",
            ),
            plan_items=[coerce_dataclass(PlanItem, item) for item in self.get_plan_items()],
            action_items=[coerce_dataclass(ActionItem, item) for item in self.get_action_items()],
            weekly_results=[coerce_dataclass(WeeklyResultRow, item) for item in self.get_weekly_results()],
            calc_payload={
                "accounts": self.get_accounts(),
                **profile_payload.get("calc_payload", {}),
            },
        )


def _decimal(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    return Decimal(str(value).replace("$", "").replace(",", ""))


def coerce_dataclass(cls, payload: dict[str, Any]):
    values = {}
    field_names = {field.name for field in fields(cls)}
    for key, value in payload.items():
        if key not in field_names:
            continue
        if key in {"pipeline_target_value", "estimated_value", "vo_value", "pipeline_generated_value"}:
            values[key] = _decimal(value)
        else:
            values[key] = value
    return cls(**values)


def load_report_from_json(path: str | Path) -> OwnerReport:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    profile_payload = payload.get("profile", {})
    return OwnerReport(
        profile=UserProfile(
            profile_name=profile_payload.get("profile_name") or profile_payload.get("full_name") or "PipeFlow",
            username=profile_payload.get("username") or profile_payload.get("profile_name") or "PipeFlow",
        ),
        plan_items=[coerce_dataclass(PlanItem, item) for item in payload.get("plan_items", [])],
        action_items=[coerce_dataclass(ActionItem, item) for item in payload.get("action_items", [])],
        weekly_results=[coerce_dataclass(WeeklyResultRow, item) for item in payload.get("weekly_results", [])],
        calc_payload=payload.get("calc_payload", {}),
    )


def load_report_from_csv(path: str | Path) -> OwnerReport:
    rows = list(csv.DictReader(Path(path).open(newline="", encoding="utf-8-sig")))
    plan_items = []
    action_items = []
    weekly_results = []
    profile = UserProfile(profile_name="PipeFlow", username="PipeFlow")
    calc_payload: dict[str, Any] = {}

    for row in rows:
        row_type = (row.get("record_type") or "").strip().lower()
        if row_type == "profile":
            profile = UserProfile(
                profile_name=row.get("profile_name") or row.get("full_name") or "PipeFlow",
                username=row.get("username") or row.get("profile_name") or "PipeFlow",
            )
        elif row_type == "plan":
            plan_items.append(coerce_dataclass(PlanItem, row))
        elif row_type == "action":
            action_items.append(coerce_dataclass(ActionItem, row))
        elif row_type == "weekly_result":
            weekly_results.append(coerce_dataclass(WeeklyResultRow, row))
        elif row_type == "calc":
            key = row.get("key")
            if key:
                calc_payload[key] = row.get("value")

    return OwnerReport(
        profile=profile,
        plan_items=plan_items,
        action_items=action_items,
        weekly_results=weekly_results,
        calc_payload=calc_payload,
    )
