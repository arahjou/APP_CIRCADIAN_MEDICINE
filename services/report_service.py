from __future__ import annotations

from typing import Any, Tuple

from tools.report_generator import generate_comparison_report, save_json_report


def build_comparison(ids: list[str]) -> Tuple[str, Any, dict | None]:
    return generate_comparison_report(ids)


def persist_report_json(json_data: dict) -> str:
    return save_json_report(json_data)
