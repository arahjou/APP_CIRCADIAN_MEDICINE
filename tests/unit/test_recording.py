from io import BytesIO

import pandas as pd
import pytest

from services.analysis_service import data_quality_report
from tools.recording import ImportOptions, import_recording
from tools.sleep_SRI import calculate_sri_from_pimn


def read(text, **options):
    return import_recording(BytesIO(text.encode()), ImportOptions(**options))


def test_optional_columns_labels_and_local_midnight():
    r = read("Timestamp;PIMn;SLEEP/WAKE\n2026-01-01 00:10:00;1;1\n2026-01-01 00:11:00;2;\n")
    assert "TEMPERATURE" not in r.data
    assert r.data.SLEEP_STATE.iloc[0] == 1
    assert pd.isna(r.data.SLEEP_STATE.iloc[1])
    assert str(r.data.Transition.iloc[0]) == "2026-01-01 00:00:00"
    assert r.metadata["sleep_source"] == "provided"
    assert len(r.metadata["source_sha256"]) == 64
    assert data_quality_report(r.data)["eligible"]["activity"]
    assert not data_quality_report(r.data)["eligible"]["sleep"]


@pytest.mark.parametrize("header,value", [("TEMPERATURE", "32"), ("MELANOPIC EDI", "100"), ("SLEEP_STATE", "1")])
def test_single_signal_import(header, value):
    r = read(f"Timestamp,{header}\n2026-01-01 12:00:00,{value}\n")
    assert data_quality_report(r.data)["ok"]


def test_explicit_date_order_mapping_and_sort():
    r = read("Time,Count\n02/01/2026 12:01:00,2\n02/01/2026 12:00:00,1\n",
             date_order="monthfirst", timezone="UTC", column_map={"Time": "DATE/TIME", "Count": "PIMn"})
    assert r.data.DATE.iloc[0] == "2026-02-01"
    assert r.data.PIMn.iloc[0] == 1
    assert r.metadata["sorted_input"]


@pytest.mark.parametrize("rows,match", [
    ("bad,1", "invalid timestamps"),
    ("2026-01-01 00:00:00,1\n2026-01-01 00:00:00,2", "duplicate"),
    ("2026-10-25 02:30:00,1", "Ambiguous"),
    ("2026-03-29 02:30:00,1", "nonexistent"),
    ("2026-01-01T00:00:00Z,1\n2026-01-01 00:01:00,2", "mix"),
])
def test_invalid_timestamps_fail_before_metrics(rows, match):
    with pytest.raises(ValueError, match=match):
        read("Timestamp,PIMn\n" + rows + "\n")


def test_offset_timestamps_and_invalid_signals():
    r = read("Timestamp,PIMn,SLEEP_STATE\n2026-10-25T02:30:00+02:00,-1,2\n2026-10-25T02:30:00+01:00,inf,0\n")
    assert not r.data["DATE/TIME"].duplicated().any()
    assert r.data.PIMn.isna().all()
    assert pd.isna(r.data.SLEEP_STATE.iloc[0])
    assert r.metadata["invalid_values"]["PIMn"] == 2


def test_raw_acceleration_not_silently_converted():
    with pytest.raises(ValueError, match="validated adapter"):
        read("Timestamp,ENMO\n2026-01-01 12:00:00,0.01\n")


def test_quality_flags_unsupported_sampling_and_gaps():
    r = read("Timestamp,PIMn\n2026-01-01 00:00:00,1\n2026-01-01 00:05:00,2\n")
    q = data_quality_report(r.data)
    assert q["sampling_minutes_median"] == 5
    assert not q["eligible"]["activity"]
    r = read("Timestamp,PIMn\n2026-01-01 00:00:00,1\n2026-01-01 00:01:00,2\n2026-01-01 00:02:00,3\n2026-01-01 01:00:00,1\n")
    assert data_quality_report(r.data)["gap_count"] == 1


def test_sri_missing_calendar_day_and_coverage():
    ts = pd.date_range("2026-01-01", periods=4 * 1440, freq="min", tz="UTC")
    df = pd.DataFrame({"t": ts, "s": 1.0})
    df = df[df.t.dt.day != 2]
    out = calculate_sri_from_pimn(df, "t", "unused", sleep_state_col="s", local_tz="UTC")
    assert len(out) == 3
    assert out.SRI.notna().sum() == 1
    assert out.SRI.dropna().iloc[0] == 100
    assert list(out.valid_epochs_pct) == [100, 0, 0]


def test_sri_partial_days_use_full_denominator():
    ts = pd.date_range("2026-01-01", periods=2880, freq="min", tz="UTC")
    df = pd.DataFrame({"t": ts, "s": 0.0})
    df = df[df.t.dt.hour < 12]
    out = calculate_sri_from_pimn(df, "t", "unused", sleep_state_col="s", local_tz="UTC")
    assert out.SRI.iloc[0] == 100
    assert out.valid_epochs_pct.iloc[0] == 50


def test_sri_dst_day_excluded_without_duplicate_pivot():
    ts = pd.date_range("2026-10-24", "2026-10-27", freq="min", inclusive="left", tz="Europe/Berlin")
    out = calculate_sri_from_pimn(pd.DataFrame({"t": ts, "s": 1.0}), "t", "unused", sleep_state_col="s")
    assert out.SRI.isna().all()
    assert (out.valid_epochs_pct == 0).all()
