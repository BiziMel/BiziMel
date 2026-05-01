from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any


class PGBibleExportError(Exception):
    def __init__(self, error_code: str, human_message: str, details: list[str]):
        super().__init__(human_message)
        self.error_code = error_code
        self.human_message = human_message
        self.details = details

    def as_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "human_message": self.human_message,
            "details": self.details,
        }


@dataclass
class UserProfile:
    profile_name: str
    username: str


@dataclass
class GoalsSummary:
    starting_pipeline: Decimal
    pipeline_added: Decimal
    pipeline_target: Decimal
    pipeline_gap: Decimal


@dataclass
class PlanItem:
    month: str = ""
    pg_bible_order: int | None = None
    account_tier: str = ""
    pipeline_target_value: Decimal = Decimal("0")
    marketing_event: str = ""
    notes: str = ""
    nbm_target: str = ""
    sales_play: str = ""
    customer: str = ""
    estimated_value: Decimal = Decimal("0")


@dataclass
class ActionItem:
    person_name: str = ""
    person_title: str = ""
    manager_notes: str = ""
    related_nbm_target: str = ""
    discovery_target_name_title: str = ""
    made_contact: str = ""
    discovery_completed: str = ""
    discovery_next_action: str = ""
    nbm_booked_date: str = ""
    nbm_booked_name_title: str = ""
    why_buy: str = ""
    exec_first: str = ""
    prep_with_manager: str = ""
    nbm_completed: str = ""
    nbm_next_action: str = ""
    vo_value: Decimal = Decimal("0")


@dataclass
class WeeklyResultRow:
    week_key: date | int | str
    vitos_sent: int = 0
    vitos_chased: int = 0
    discovery_booked: int = 0
    discovery_completed: int = 0
    nbms_booked: int = 0
    nbms_exec_firsts: int = 0
    nbms_completed: int = 0
    pipeline_generated_vo_count: int = 0
    pipeline_generated_value: Decimal = Decimal("0")


@dataclass
class OwnerReport:
    profile: UserProfile
    goals: GoalsSummary | None = None
    plan_items: list[PlanItem] = field(default_factory=list)
    action_items: list[ActionItem] = field(default_factory=list)
    weekly_results: list[WeeklyResultRow] = field(default_factory=list)
    calc_payload: dict[str, Any] = field(default_factory=dict)
