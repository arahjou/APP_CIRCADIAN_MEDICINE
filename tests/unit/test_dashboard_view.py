import json

import numpy as np
import pandas as pd

from tests.unit.test_dashboard_helpers import DummyDB
from tools.dashboard_view import KPIS, build_dashboard_data, judge


def _kpi(key):
    return next(k for k in KPIS if k.key == key)


def test_judge_respects_direction_and_threshold():
    assert judge(_kpi("sri"), 70, 80) == "improved"
    assert judge(_kpi("cpd"), 0.5, 1.0) == "worsened"
    assert judge(_kpi("iv"), 0.80, 0.85) == "stable"
    assert judge(_kpi("duration"), 7, 8) == "changed"
    assert judge(_kpi("ra"), np.nan, 0.9) == "n/a"


def test_build_dashboard_data_uses_main_sleep_and_light_minutes():
    periods = pd.DataFrame({
        "Sleep_onset_DATE": ["2025-01-01", "2025-01-02", "2025-01-02"],
        "Sleep_onset_Time": ["23:00:00", "14:00:00", "23:30:00"],
        "Sleep_offset_DATE": ["2025-01-02", "2025-01-02", "2025-01-03"],
        "Sleep_offset_TIME": ["07:00:00", "14:30:00", "07:30:00"],
        "duration_minutes": [480, 30, 480], "is_main_sleep": [True, False, True],
        "night": ["2025-01-01", "2025-01-02", "2025-01-02"],
    })
    light = {"metric1": [{"date": "2025-01-01", "minutes": 0}, {"date": "2025-01-02", "minutes": 20}]}
    db = DummyDB(df_map={("A", "sleep_analysis", "sleep_periods"): periods},
                 row_map={("A", "sleep_analysis"): [{"analysis_type": "sleep_light_exposure", "results": json.dumps(light)}]})
    data = build_dashboard_data(db, "A", "B")
    kpis = data["kpis"].set_index("key")
    assert kpis.loc["duration", "value_1"] == 8
    assert kpis.loc["light_night", "value_1"] == 10
    assert kpis.loc["sri", "verdict"] == "n/a"
    timing = data["sleep_timing"]
    assert len(timing) == 2 and timing["onset"].tolist() == [11, 11.5] and timing["offset"].tolist() == [19, 19.5]
