"""Read-only quality assessment and explicit eligibility for legacy metrics."""
from __future__ import annotations

import numpy as np
import pandas as pd

from tools.recording import SIGNAL_UNITS

REQUIRED_COLUMNS = {"DATE/TIME"}


def data_quality_report(df: pd.DataFrame) -> dict:
    missing = sorted(REQUIRED_COLUMNS - set(df.columns)) if df is not None else ["DATE/TIME"]
    ts = pd.to_datetime(df["DATE/TIME"], errors="coerce") if df is not None and not missing else pd.Series(dtype="datetime64[ns]")
    valid = ts.dropna().sort_values()
    diffs = valid.diff().dropna().dt.total_seconds() / 60
    positive = diffs[diffs > 0]
    interval = float(positive.median()) if not positive.empty else None
    duplicates = int(valid.duplicated().sum())
    invalid_ts = int(ts.isna().sum())
    errors = []
    warnings = []
    if missing or valid.empty:
        errors.append("A nonempty recording with DATE/TIME is required.")
    if invalid_ts:
        errors.append(f"{invalid_ts} timestamps are invalid.")
    if duplicates:
        errors.append(f"{duplicates} timestamps are duplicated.")
    timezone_present = not valid.empty and getattr(valid.dt, "tz", None) is not None
    if not timezone_present:
        errors.append("Timestamps must include a timezone; import the recording first.")
    minute_grid = bool(not positive.empty and np.allclose(positive % 1, 0))
    one_minute = bool(interval is not None and np.isclose(interval, 1) and minute_grid)
    gaps = int((positive > 1).sum()) if one_minute else 0
    dst = False
    if timezone_present:
        tz = valid.dt.tz
        for day in valid.dt.date.unique():
            start = pd.Timestamp(day).tz_localize(tz)
            end = (pd.Timestamp(day) + pd.Timedelta(days=1)).tz_localize(tz)
            if end - start != pd.Timedelta(hours=24):
                dst = True
    signals = {}
    for col in SIGNAL_UNITS:
        if df is None or col not in df:
            continue
        x = pd.to_numeric(df[col], errors="coerce")
        valid_values = np.isfinite(x)
        if col == "SLEEP_STATE":
            valid_values &= x.isin([0, 1])
        elif col != "TEMPERATURE":
            valid_values &= x >= 0
        signals[col] = {"valid_samples": int(valid_values.sum()),
                        "missing_or_invalid_samples": int((~valid_values).sum()),
                        "valid_percent": float(valid_values.mean() * 100) if len(x) else 0}
    if not any(s["valid_samples"] for s in signals.values()):
        errors.append("No valid supported signal samples.")
    if not one_minute:
        warnings.append("Legacy rhythm metrics require one-minute samples; no automatic resampling or unit conversion is performed.")
    if gaps:
        warnings.append(f"{gaps} gaps exceed one minute; incomplete intervals are excluded where required.")
    if dst:
        warnings.append("DST offset change: legacy rhythm/bout metrics withheld; SRI excludes transition days.")
    for col, summary in signals.items():
        if summary["missing_or_invalid_samples"]:
            warnings.append(f"{col}: {summary['missing_or_invalid_samples']} missing/invalid samples.")

    def available(col):
        return col in signals and signals[col]["valid_samples"] > 0

    eligibility = {
        "activity": available("PIMn") and one_minute and not dst,
        "light": available("MELANOPIC EDI") and one_minute and not dst,
        "sleep": available("SLEEP_STATE") and one_minute and not dst and not gaps
                 and signals["SLEEP_STATE"]["missing_or_invalid_samples"] == 0,
        "sri": available("SLEEP_STATE") and one_minute,
    }
    eligibility["sleep_light"] = (eligibility["sleep"] and eligibility["light"]
                                  and signals["MELANOPIC EDI"]["missing_or_invalid_samples"] == 0)
    return {
        "ok": not errors, "missing_columns": missing, "errors": errors, "warnings": warnings,
        "date_coverage_days": int(valid.dt.date.nunique()) if not valid.empty else 0,
        "sampling_minutes_median": interval, "timezone_present": timezone_present,
        "duplicate_timestamps": duplicates, "invalid_timestamps": invalid_ts,
        "gap_count": gaps, "dst_transition": dst, "signals": signals,
        "eligible": {k: bool(v and not errors) for k, v in eligibility.items()},
    }
