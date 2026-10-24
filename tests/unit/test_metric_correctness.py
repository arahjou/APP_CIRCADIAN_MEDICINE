"""Ground-truth checks for rhythm and sleep metrics on synthetic signals."""
import numpy as np
import pandas as pd
import pytest

from tools.activity_IS_IV import compute_rolling_2day_is_iv_activity
from tools.activity_L5_M10_RA import compute_daily_L5_M10_RA_activity
from tools.nonparametric import interdaily_stability, intradaily_variability
from tools.sleep_CPD_ms import build_centered_midpoint_hours, calculate_single_person_cpd
from tools.sleep_light_exposure import analyze_sleep_light_exposure
from tools.sleep_on_off_mid import analyze_sleep_periods, main_sleep_only


def _minutes(start, days, tz="Europe/Berlin"):
    ts = pd.date_range(start, periods=days * 1440, freq="min", tz=tz)
    return ts, ts.hour + ts.minute / 60


def _reference_is_iv(hourly):
    x = hourly.to_numpy()
    mu, n = x.mean(), len(x)
    profile = hourly.groupby(hourly.index.hour).mean()
    is_ = n * ((profile - mu) ** 2).sum() / (24 * ((x - mu) ** 2).sum())
    iv = n * (np.diff(x) ** 2).sum() / ((n - 1) * ((x - mu) ** 2).sum())
    return is_, iv


def test_is_iv_match_hourly_textbook_definition():
    ts, h = _minutes("2025-03-10 12:00", 4)
    noisy = 100 + 50 * np.cos(2 * np.pi * (h - 15) / 24) + np.random.default_rng(1).normal(0, 40, len(ts))
    out = compute_rolling_2day_is_iv_activity(pd.DataFrame({"DATE/TIME": ts, "PIMn": noisy}))
    first = out.iloc[0]
    hourly = pd.Series(noisy, index=ts)[: 2 * 1440].resample("1h").mean()
    expected_is, expected_iv = _reference_is_iv(hourly)
    assert first.IS_2day == pytest.approx(expected_is)
    assert first.IV_2day == pytest.approx(expected_iv)


def test_is_is_bounded_and_partial_windows_withheld():
    ts, h = _minutes("2025-03-10 00:00", 4)
    signal = 100 + 50 * np.cos(2 * np.pi * (h - 15) / 24)
    out = compute_rolling_2day_is_iv_activity(pd.DataFrame({"DATE/TIME": ts, "PIMn": signal}))
    assert out.IS_2day.dropna().le(1 + 1e-12).all()
    assert out.IS_2day.dropna().eq(1).all()
    assert np.isnan(out.iloc[0].IS_2day) and np.isnan(out.iloc[-1].IS_2day)


def test_is_ignores_unpaired_hours():
    hourly = pd.Series(np.tile(np.arange(24.0), 2), index=pd.date_range("2025-01-01", periods=48, freq="h"))
    hourly.iloc[30:34] = np.nan
    assert interdaily_stability(hourly) == pytest.approx(1)
    assert np.isfinite(intradaily_variability(hourly))


def test_l5_m10_exact_and_partial_days_omitted():
    ts, h = _minutes("2025-03-10 00:00", 5)
    signal = np.where((h >= 8) & (h < 18), 100.0, np.where((h >= 23) | (h < 4), 0.0, 50.0))
    out = compute_daily_L5_M10_RA_activity(pd.DataFrame({"DATE/TIME": ts, "PIMn": signal}))
    assert len(out) == 4
    assert out.M10_mean.eq(100).all() and out.L5_mean.eq(0).all() and out.RA.eq(1).all()
    assert all(t.hour == 8 for t in out.M10_start) and all(t.hour == 23 for t in out.L5_start)


@pytest.fixture
def nights():
    ts, h = _minutes("2025-04-01 12:00", 4)
    sleep = ((h >= 23) | (h < 7)).astype(float)
    sleep[(h >= 14) & (h < 14.5)] = 1          # daily nap
    sleep[(h >= 3) & (h < 3 + 10 / 60)] = 0    # 10-minute awakening
    light = np.where(sleep == 1, 0.0, np.where((h >= 7) & (h < 10), 100.0, 300.0))
    return pd.DataFrame({"DATE/TIME": ts, "PIMn": 10.0, "SLEEP_STATE": sleep, "MELANOPIC EDI": light})


def test_sleep_periods_merge_awakenings_and_flag_naps(nights):
    periods = analyze_sleep_periods(nights)
    main = main_sleep_only(periods)
    assert len(main) == 4 and main.duration_minutes.eq(480).all()
    assert main.sleep_minutes.eq(470).all() and main.n_bouts.eq(2).all()
    assert periods.loc[~periods.is_main_sleep, "duration_minutes"].eq(30).all()


def test_cpd_is_zero_for_identical_nights(nights):
    main = main_sleep_only(analyze_sleep_periods(nights))
    cpd = calculate_single_person_cpd(build_centered_midpoint_hours(main), "mid_sleep_DATE", "midpoint_hours_centered")
    assert np.allclose(cpd.cpd_hours.dropna(), 0)


def test_sleep_light_exposure_per_night_without_smoothing(nights):
    out = analyze_sleep_light_exposure(nights)
    assert [r["minutes"] for r in out["metric1"]] == [10] * 4    # only the lit awakening
    assert [r["minutes"] for r in out["metric3"]] == [180] * 4
    assert [r["minutes"] for r in out["metric2"]] == [180] * 4   # 300 lux evening
    assert [r["date"] for r in out["metric1"]] == ["2025-04-01", "2025-04-02", "2025-04-03", "2025-04-04"]


def test_sleep_light_exposure_reports_zero_minutes(nights):
    nights["MELANOPIC EDI"] = np.where(nights["SLEEP_STATE"] == 1, 0.0, 0.5)
    out = analyze_sleep_light_exposure(nights)
    assert [r["minutes"] for r in out["metric1"]] == [0] * 4
    assert [r["minutes"] for r in out["metric2"]] == [0] * 4


def test_l5_m10_with_second_offset_timestamps():
    ts, h = _minutes("2025-03-10 00:00:06", 3)
    signal = np.where((h >= 8) & (h < 18), 100.0, 10.0)
    out = compute_daily_L5_M10_RA_activity(pd.DataFrame({"DATE/TIME": ts, "PIMn": signal}))
    assert len(out) == 2 and out.M10_mean.eq(100).all()
