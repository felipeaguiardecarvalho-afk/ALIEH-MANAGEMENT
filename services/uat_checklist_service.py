"""Checklist UAT manual — delega ao repositório; a app não importa database.uat_checklist_repo."""

from __future__ import annotations

from database.uat_checklist_repo import (
    UAT_MANUAL_CASES,
    UAT_STATUS_LABELS,
    UAT_STATUS_ORDER,
    fetch_map_for_tenant,
    upsert_uat_record,
)

__all__ = [
    "UAT_MANUAL_CASES",
    "UAT_STATUS_LABELS",
    "UAT_STATUS_ORDER",
    "fetch_map_for_tenant",
    "upsert_uat_record",
]
