from __future__ import annotations

import pandas as pd


REQUIRED_COLUMNS = {
    "DATE/TIME",
    "PIMn",
    "MELANOPIC EDI",
    "WHITE LIGHT (LUX)",
    "SLEEP/WAKE",
}


def data_quality_report(df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        return {
            "ok": False,
            "missing_columns": sorted(REQUIRED_COLUMNS),
            "date_coverage_days": 0,
            "sampling_minutes_median": None,
            "timezone_present": False,
        }

    cols = set(df.columns)
    missing = sorted(REQUIRED_COLUMNS - cols)

    ts = pd.to_datetime(df["DATE/TIME"], errors="coerce") if "DATE/TIME" in df.columns else pd.Series(dtype="datetime64[ns]")
    valid_ts = ts.dropna().sort_values()

    timezone_present = bool(getattr(valid_ts.dt, "tz", None) is not None) if not valid_ts.empty else False

    sampling_minutes_median = None
    if len(valid_ts) >= 2:
        diffs = valid_ts.diff().dropna().dt.total_seconds() / 60.0
        if not diffs.empty:
            sampling_minutes_median = float(diffs.median())

    days = int(valid_ts.dt.date.nunique()) if not valid_ts.empty else 0

    return {
        "ok": len(missing) == 0 and days > 0,
        "missing_columns": missing,
        "date_coverage_days": days,
        "sampling_minutes_median": sampling_minutes_median,
        "timezone_present": timezone_present,
    }
