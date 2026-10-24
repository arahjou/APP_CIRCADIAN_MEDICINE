import numpy as np
import pandas as pd


def calculate_sri_from_pimn(
    df: pd.DataFrame,
    timestamp_col: str,
    pimn_col: str,
    sleep_state_col: str | None = None,
    window_days: int = 2,
    slide_interval: int = 1,
    rolling_window: int = 100,
    sleep_threshold: float = 6,
    local_tz: str = "Europe/Berlin",  # use local wall clock
) -> pd.DataFrame:
    """
    Compute SRI for a single participant.

    Steps:
      1) Convert timestamps to local_tz, then drop tz (wall clock alignment).
        2) If `sleep_state_col` is provided/present, use it as Sleep_State.
            Otherwise, compute PIMn_avg and derive Sleep_State from threshold.
      4) Pivot by date x time and compute SRI over sliding windows.
    """
    if window_days < 2:
        raise ValueError("window_days must be at least 2.")
    if slide_interval < 1:
        raise ValueError("slide_interval must be positive.")

    df = df.copy()

    # --- Robust timestamp parsing & localization to wall clock ---
    ts = pd.to_datetime(df[timestamp_col], errors="coerce")
    if ts.isna().any():
        raise ValueError(f"Some timestamps could not be parsed (n={ts.isna().sum()}).")

    # If tz-aware, convert to local_tz; if tz-naive, localize as local_tz (assume local)
    if getattr(ts.dt, "tz", None) is not None:
        ts = ts.dt.tz_convert(local_tz)
    else:
        ts = ts.dt.tz_localize(local_tz)

    transition_dates = set()
    for day in ts.dt.date.unique():
        start = pd.Timestamp(day).tz_localize(local_tz)
        end = (pd.Timestamp(day) + pd.Timedelta(days=1)).tz_localize(local_tz)
        if end - start != pd.Timedelta(hours=24):
            transition_dates.add(day)
    # Drop timezone but keep local wall clock
    ts = ts.dt.tz_localize(None)
    df[timestamp_col] = ts

    # Chronological order before rolling
    df = df.sort_values(timestamp_col)
    if df[timestamp_col].duplicated().any():
        dup = df[timestamp_col].duplicated(keep=False)
        if (~df.loc[dup, timestamp_col].dt.date.isin(transition_dates)).any():
            raise ValueError("Duplicate timestamps are not valid SRI input.")
    if df.empty:
        return pd.DataFrame(columns=["start_date", "end_date", "SRI", "valid_epochs_pct"])

    # --- Sleep state source ---
    selected_sleep_state_col = sleep_state_col if sleep_state_col else ("SLEEP_STATE" if "SLEEP_STATE" in df.columns else None)
    if selected_sleep_state_col and selected_sleep_state_col in df.columns:
        state = pd.to_numeric(df[selected_sleep_state_col], errors="coerce")
        df["Sleep_State"] = state.where(state.isin([0, 1])).astype("float")
    else:
        df["PIMn_avg"] = df[pimn_col].rolling(window=rolling_window).mean()  # NaN until full window
        sleep_state = (df["PIMn_avg"] < sleep_threshold).astype("float")
        sleep_state[df["PIMn_avg"].isna()] = np.nan
        df["Sleep_State"] = sleep_state

    # --- Daily pivot ---
    df["date"] = df[timestamp_col].dt.date
    df["time"] = df[timestamp_col].dt.time  # keeps seconds (e.g., :39) consistent day-to-day

    first_date, last_date = df["date"].min(), df["date"].max()
    df = df[~df["date"].isin(transition_dates)]
    # Full calendar/clock grids prevent comparing nonconsecutive days and keep
    # absent epochs in the coverage denominator. DST transition days are excluded.
    seconds = ts.dt.second.unique()
    if len(seconds) != 1 or (ts.dt.microsecond != 0).any():
        raise ValueError("SRI requires a consistent one-minute clock grid.")
    clock = pd.date_range(pd.Timestamp("2000-01-01") + pd.Timedelta(seconds=int(seconds[0])),
                          periods=1440, freq="min").time
    dates_grid = pd.date_range(first_date, last_date, freq="D").date
    pvt = df.pivot(index="date", columns="time", values="Sleep_State").reindex(
        index=dates_grid, columns=clock).sort_index(ascending=False)

    dates = pvt.index
    n_dates = len(dates)
    results = []

    if n_dates < window_days:
        return pd.DataFrame(columns=["start_date", "end_date", "SRI", "valid_epochs_pct"])

    for start in range(0, n_dates - window_days + 1, slide_interval):
        window = pvt.iloc[start : start + window_days].to_numpy(dtype=float)

        comparisons = window[1:] == window[:-1]
        valid = (~np.isnan(window[1:])) & (~np.isnan(window[:-1]))

        total_valid = valid.sum()
        matches = (comparisons & valid).sum()

        p_match = matches / total_valid if total_valid else np.nan
        sri = 200 * p_match - 100 if total_valid else np.nan
        valid_pct = (total_valid / comparisons.size) * 100 if comparisons.size else np.nan

        d1, d2 = dates[start], dates[start + window_days - 1]
        results.append(
            {
                "start_date": min(d1, d2),
                "end_date": max(d1, d2),
                "SRI": sri,
                "valid_epochs_pct": valid_pct,
            }
        )

    return pd.DataFrame(results)
