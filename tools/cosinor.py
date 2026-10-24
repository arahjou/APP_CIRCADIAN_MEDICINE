"""Fixed 24-hour harmonic regression with a globally solved linear fit."""
from __future__ import annotations

import numpy as np
import pandas as pd


def cosinor_function(t, mesor, amplitude, acrophase):
    return mesor + amplitude * np.cos(2 * np.pi * t / 24 - acrophase)


def fit_daily_cosinor(df, datetime_col="DATE/TIME", value_col="PIMn"):
    """Fit y=M+b*cos(wt)+c*sin(wt), equivalent to M+A*cos(wt-phase).

    Linear least squares avoids the nonlinear solver's zero-amplitude boundary
    solution. Phase is undefined for a numerically flat signal. Sampling/coverage
    policy is applied by the recording service, not inferred here.
    """
    columns = ["date", "mesor", "amplitude", "acrophase_radians", "acrophase_hours", "r_squared", "n_measurements"]
    results = []
    data = df.copy()
    data[datetime_col] = pd.to_datetime(data[datetime_col], errors="coerce")
    for day, group in data.groupby(data[datetime_col].dt.date):
        time = group[datetime_col]
        hours = (time.dt.hour + time.dt.minute / 60 + time.dt.second / 3600).to_numpy(dtype=float)
        values = pd.to_numeric(group[value_col], errors="coerce").to_numpy(dtype=float)
        valid = np.isfinite(hours) & np.isfinite(values)
        hours, values = hours[valid], values[valid]
        if len(values) < 10:
            continue
        angle = hours * 2 * np.pi / 24
        design = np.column_stack([np.ones(len(angle)), np.cos(angle), np.sin(angle)])
        coefficients, _, rank, _ = np.linalg.lstsq(design, values, rcond=None)
        if rank < 3:
            continue
        mesor, beta_cos, beta_sin = coefficients
        amplitude = float(np.hypot(beta_cos, beta_sin))
        tolerance = 1e-10 * max(1.0, float(np.max(np.abs(values))))
        phase = float(np.arctan2(beta_sin, beta_cos) % (2 * np.pi)) if amplitude > tolerance else np.nan
        residual = float(np.sum((values - design @ coefficients) ** 2))
        total = float(np.sum((values - values.mean()) ** 2))
        r_squared = 1 - residual / total if total > tolerance**2 else np.nan
        results.append({"date": day, "mesor": float(mesor), "amplitude": amplitude,
                        "acrophase_radians": phase, "acrophase_hours": phase * 24 / (2 * np.pi),
                        "r_squared": r_squared, "n_measurements": len(values)})
    return pd.DataFrame(results, columns=columns)
