from __future__ import annotations

import numpy as np
import pandas as pd

from app import (
    _build_comparison_dashboard_payload,
    _build_light_exposure_series,
    _build_raw_tables_for_record,
    _normalize_payload_to_dataframe,
    _safe_delta,
)


class DummyDB:
    def __init__(
        self,
        df_map: dict[tuple[str, str, str], pd.DataFrame] | None = None,
        row_map: dict[tuple[str, str], list[dict]] | None = None,
    ) -> None:
        self.df_map = df_map or {}
        self.row_map = row_map or {}

    def get_analysis_results_as_dataframe(self, record_id: str, table_name: str, analysis_type: str):
        key = (record_id, table_name, analysis_type)
        df = self.df_map.get(key)
        return None if df is None else df.copy()

    def get_analysis_results(self, record_id: str, table_name: str):
        return list(self.row_map.get((record_id, table_name), []))


def _make_full_db() -> DummyDB:
    df_map = {
        ("R1", "sleep_analysis", "sri_sleep"): pd.DataFrame(
            {"start_date": ["2025-01-01", "2025-01-02"], "SRI": [80.0, 82.0]}
        ),
        ("R2", "sleep_analysis", "sri_sleep"): pd.DataFrame(
            {"start_date": ["2025-01-01", "2025-01-02"], "SRI": [76.0, 79.0]}
        ),
        ("R1", "sleep_analysis", "cpd_mid_sleep"): pd.DataFrame(
            {"mid_sleep_DATE": ["2025-01-01", "2025-01-02"], "cpd_hours": [1.5, 1.8]}
        ),
        ("R2", "sleep_analysis", "cpd_mid_sleep"): pd.DataFrame(
            {"mid_sleep_DATE": ["2025-01-01", "2025-01-02"], "cpd_hours": [2.2, 2.0]}
        ),
        ("R1", "activity_analysis", "activity_l5_m10_ra"): pd.DataFrame({"RA": [0.71, 0.76]}),
        ("R2", "activity_analysis", "activity_l5_m10_ra"): pd.DataFrame({"RA": [0.61, 0.64]}),
        ("R1", "light_analysis", "light_l5_m10_ra"): pd.DataFrame({"RA": [0.55, 0.57]}),
        ("R2", "light_analysis", "light_l5_m10_ra"): pd.DataFrame({"RA": [0.48, 0.51]}),
        ("R1", "activity_analysis", "activity_is_iv"): pd.DataFrame(
            {"IS_2day": [0.20, 0.23], "IV_2day": [0.63, 0.66]}
        ),
        ("R2", "activity_analysis", "activity_is_iv"): pd.DataFrame(
            {"IS_2day": [0.15, 0.18], "IV_2day": [0.79, 0.81]}
        ),
        ("R1", "light_analysis", "light_is_iv"): pd.DataFrame(
            {"IS_2day": [0.11, 0.12], "IV_2day": [1.02, 1.03]}
        ),
        ("R2", "light_analysis", "light_is_iv"): pd.DataFrame(
            {"IS_2day": [0.09, 0.10], "IV_2day": [1.20, 1.24]}
        ),
    }
    row_map = {
        ("R1", "sleep_analysis"): [
            {
                "analysis_type": "sleep_light_exposure",
                "results": {
                    "metric1": [{"date": "2025-01-01", "minutes": 10}],
                    "metric2": "No bright light exposure detected in the 3 hours before sleep.",
                    "metric3": [{"date": "2025-01-01", "minutes": 32}],
                },
            }
        ],
        ("R2", "sleep_analysis"): [
            {
                "analysis_type": "sleep_light_exposure",
                "results": {
                    "metric1": [{"date": "2025-01-01", "minutes": 16}],
                    "metric2": "No bright light exposure detected in the 3 hours before sleep.",
                    "metric3": [{"date": "2025-01-01", "minutes": 21}],
                },
            }
        ],
    }
    return DummyDB(df_map=df_map, row_map=row_map)


def test_build_comparison_dashboard_payload_full() -> None:
    db = _make_full_db()
    payload = _build_comparison_dashboard_payload(db, "R1", "R2")

    assert payload["ids"] == ("R1", "R2")
    kpi_df = payload["kpi_df"]
    assert len(kpi_df) == 8
    assert (~kpi_df["missing"].fillna(True)).any()

    sri_trend = payload["sri_trend"]
    assert not sri_trend[~sri_trend["missing"].fillna(True)].empty
    assert set(sri_trend["record_id"].dropna().unique()) == {"R1", "R2"}

    light_df = payload["light_exposure_df"]
    assert set(light_df["exposure_type"].dropna().unique()) == {"During sleep (>1 lux)", "Post wake (<250 lux)"}
    assert not light_df[~light_df["missing"].fillna(True)].empty


def test_build_comparison_dashboard_payload_handles_missing_record_data() -> None:
    full_db = _make_full_db()
    db = DummyDB(
        df_map={
            key: value for key, value in full_db.df_map.items() if key[0] == "R1"
        },
        row_map={
            key: value for key, value in full_db.row_map.items() if key[0] == "R1"
        },
    )
    payload = _build_comparison_dashboard_payload(db, "R1", "R2")
    kpi_df = payload["kpi_df"]

    assert kpi_df["value_2"].isna().any()
    assert kpi_df["missing"].any()
    assert payload["sri_trend"].query("record_id == 'R2'")["missing"].all()


def test_non_tabular_and_malformed_payload_handling() -> None:
    malformed = _normalize_payload_to_dataframe("{broken-json")
    assert list(malformed.columns) == ["value"]
    assert malformed.iloc[0]["value"] == "{broken-json"

    exposure_df = _build_light_exposure_series(
        "R1",
        {"metric1": [], "metric2": "No bright light exposure detected in the 3 hours before sleep."},
        "metric1",
        "During sleep (>1 lux)",
    )
    assert bool(exposure_df["missing"].iloc[0]) is True

    db = DummyDB(
        row_map={
            ("R1", "sleep_analysis"): [
                {
                    "analysis_type": "sleep_light_exposure",
                    "results": {
                        "metric1": [],
                        "metric2": "No bright light exposure detected in the 3 hours before sleep.",
                        "metric3": [],
                    },
                }
            ]
        }
    )
    raw_tables = _build_raw_tables_for_record(db, "R1")
    summary = raw_tables["sleep_light_exposure_summary"]
    metric2_notes = summary.loc[summary["metric"] == "Bright light pre-sleep (>10 lux)", "notes"].iloc[0]
    assert "No bright light exposure" in metric2_notes


def test_safe_delta_nan_and_zero_cases() -> None:
    assert np.isnan(_safe_delta(np.nan, 1.0))
    assert np.isnan(_safe_delta(1.0, np.nan))
    assert _safe_delta(0.0, 0.0) == 0.0
    assert _safe_delta(-1.0, 1.0) == 2.0
