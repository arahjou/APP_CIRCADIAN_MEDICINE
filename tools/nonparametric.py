"""Non-parametric rhythm metrics (IS, IV, L5, M10, RA) shared by activity and light.

Definitions follow Witting et al. (1990) and van Someren et al. (1999):
IS and IV are computed on hourly means, L5/M10 on one-minute data within
anchored 24-hour days. Incomplete anchored days/windows are withheld rather
than wrapped or extrapolated.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

IS_IV_COLUMNS = ["day_pair", "start_date", "end_date", "IS_2day", "IV_2day", "n_minutes", "n_hours"]
L5_M10_COLUMNS = ["date", "M10_start", "M10_mean", "L5_start", "L5_mean", "RA"]


def _minute_grid(df: pd.DataFrame, time_col: str, value_col: str) -> pd.Series | None:
    data = df.copy()
    data[time_col] = pd.to_datetime(data[time_col], errors="coerce")
    data = data.dropna(subset=[time_col]).sort_values(time_col).set_index(time_col)
    if data.empty or value_col not in data:
        return None
    full_idx = pd.date_range(data.index.min(), data.index.max(), freq="1min", tz=data.index.tz)
    return pd.to_numeric(data[value_col], errors="coerce").reindex(full_idx)


def _anchored_day(index: pd.DatetimeIndex, anchor_hour: int) -> pd.DatetimeIndex:
    return (index - pd.Timedelta(hours=anchor_hour)).normalize() + pd.Timedelta(hours=anchor_hour)


def interdaily_stability(hourly: pd.Series) -> float:
    """IS = N * sum_h (xbar_h - xbar)^2 / (p * sum_i (x_i - xbar)^2) on consecutive 24 h days.

    Only hour-of-day slots valid on every day are used, so the profile is
    balanced and IS stays within [0, 1] when individual hours are missing.
    """
    if len(hourly) % 24:
        raise ValueError("IS requires whole days of hourly bins")
    matrix = hourly.to_numpy(dtype=float).reshape(-1, 24)
    matrix = matrix[:, ~np.isnan(matrix).any(axis=0)]
    if matrix.size < 2:
        return np.nan
    mu = matrix.mean()
    den = float(((matrix - mu) ** 2).sum())
    if den == 0:
        return np.nan
    n_days = matrix.shape[0]
    return float(n_days * ((matrix.mean(axis=0) - mu) ** 2).sum() / den)


def intradaily_variability(hourly: pd.Series) -> float:
    """IV = N * sum (x_i - x_{i-1})^2 / ((N - 1) * sum (x_i - xbar)^2), adjacent valid hours only."""
    valid = hourly.dropna()
    if len(valid) < 3:
        return np.nan
    mu = valid.mean()
    den = float(((valid - mu) ** 2).sum())
    diffs = hourly.diff().dropna()
    if den == 0 or diffs.empty:
        return np.nan
    # Mean squared successive difference over the mean squared deviation.
    return float((diffs ** 2).mean() / (den / len(valid)))


def compute_rolling_2day_is_iv(
    df: pd.DataFrame,
    time_col: str = "DATE/TIME",
    value_col: str = "PIMn",
    anchor_hour: int = 12,
    min_window_coverage: float = 0.7,
    min_minutes_per_hour: int = 30,
) -> pd.DataFrame:
    """IS and IV for each pair of consecutive anchored days (Day 1-2, Day 2-3, ...).

    Minute data are averaged into clock hours (hours with fewer than
    `min_minutes_per_hour` valid minutes are missing). Windows with fewer than
    `min_window_coverage` of their 48 hourly bins are reported as NaN.
    """
    x = _minute_grid(df, time_col, value_col)
    if x is None:
        return pd.DataFrame(columns=IS_IV_COLUMNS)
    day_id = _anchored_day(x.index, anchor_hour)
    unique_days = sorted(day_id.unique())
    if len(unique_days) < 2:
        return pd.DataFrame(columns=IS_IV_COLUMNS)

    results = []
    for day1, day2 in zip(unique_days[:-1], unique_days[1:]):
        if day2 - day1 != pd.Timedelta(days=1):
            continue
        window = x[(day_id == day1) | (day_id == day2)]
        hourly = window.resample("1h").mean().where(window.resample("1h").count() >= min_minutes_per_hour)
        # Index the hourly bins on the full 48 h window so edge days count as incomplete.
        hourly = hourly.reindex(pd.date_range(day1, periods=48, freq="1h"))
        n_hours = int(hourly.notna().sum())
        paired_hours = int(hourly.to_frame().assign(slot=np.arange(48) % 24).dropna()
                           .groupby("slot").size().eq(2).sum())
        complete = n_hours >= min_window_coverage * 48 and paired_hours >= min_window_coverage * 24
        results.append({
            "day_pair": f"{day1.date()} to {day2.date()}",
            "start_date": day1.date(),
            "end_date": day2.date(),
            "IS_2day": interdaily_stability(hourly) if complete else np.nan,
            "IV_2day": intradaily_variability(hourly) if complete else np.nan,
            "n_minutes": int(window.notna().sum()),
            "n_hours": n_hours,
        })
    return pd.DataFrame(results, columns=IS_IV_COLUMNS)


def compute_daily_L5_M10_RA(
    df: pd.DataFrame,
    time_col: str = "DATE/TIME",
    value_col: str = "PIMn",
    anchor_hour: int = 12,
    allow_missing_frac: float = 0.10,
    min_day_coverage: float = 0.7,
) -> pd.DataFrame:
    """Daily L5, M10 and RA = (M10 - L5) / (M10 + L5) on anchored 24-hour days.

    Each anchored day is placed on its own 1440-minute grid so that windows may
    wrap from the end of the day to its start. Days with fewer than
    `min_day_coverage` valid minutes (e.g. the partial first and last day of a
    recording) are omitted. A window needs at least (1 - allow_missing_frac) of
    its minutes to be valid.
    """
    x = _minute_grid(df, time_col, value_col)
    if x is None or x.notna().sum() == 0:
        return pd.DataFrame(columns=L5_M10_COLUMNS)
    day_id = _anchored_day(x.index, anchor_hour)
    win10, win5 = 600, 300
    minp10 = int(np.ceil((1 - allow_missing_frac) * win10))
    minp5 = int(np.ceil((1 - allow_missing_frac) * win5))

    # Devices may stamp samples at a fixed second offset (e.g. hh:mm:06).
    offset = x.index[0] - x.index[0].floor("min")
    rows = []
    for day_start in sorted(day_id.unique()):
        grid = pd.date_range(day_start + offset, periods=1440, freq="1min")
        s = x[day_id == day_start].reindex(grid)
        if s.notna().sum() < min_day_coverage * len(grid):
            continue
        # Circular extension: candidate windows start within the day and may wrap.
        ss = pd.Series(np.concatenate([s.to_numpy(), s.to_numpy()]))
        starts10 = ss.rolling(win10, min_periods=minp10).mean().shift(-(win10 - 1)).iloc[:len(s)]
        starts5 = ss.rolling(win5, min_periods=minp5).mean().shift(-(win5 - 1)).iloc[:len(s)]
        if starts10.notna().any():
            m10_pos = int(starts10.idxmax())
            m10_start, m10_mean = grid[m10_pos], float(starts10.iloc[m10_pos])
        else:
            m10_start, m10_mean = pd.NaT, np.nan
        if starts5.notna().any():
            l5_pos = int(starts5.idxmin())
            l5_start, l5_mean = grid[l5_pos], float(starts5.iloc[l5_pos])
        else:
            l5_start, l5_mean = pd.NaT, np.nan
        total = m10_mean + l5_mean
        ra = (m10_mean - l5_mean) / total if np.isfinite(total) and total != 0 else np.nan
        rows.append({"date": day_start.date(), "M10_start": m10_start, "M10_mean": m10_mean,
                     "L5_start": l5_start, "L5_mean": l5_mean, "RA": ra})
    return pd.DataFrame(rows, columns=L5_M10_COLUMNS)
