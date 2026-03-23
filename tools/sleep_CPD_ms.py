import pandas as pd
import numpy as np
# ---------- helpers for circular math ----------
def _angle_diff(a, b):
    return (a - b + np.pi) % (2 * np.pi) - np.pi

def _circular_mean(theta):
    return np.arctan2(np.sum(np.sin(theta)), np.sum(np.cos(theta)))

def _circular_median(theta):
    candidates = np.unique(theta)
    total_dev = np.array([np.sum(np.abs(_angle_diff(theta, m))) for m in candidates])
    return candidates[np.argmin(total_dev)]

# ---------- your CPD function (expects centered hours) ----------
def calculate_single_person_cpd(df: pd.DataFrame, date_col: str, midpoint_col: str) -> pd.DataFrame:
    out = df.sort_values(by=date_col, kind="mergesort").copy()

    if midpoint_col not in out.columns:
        raise ValueError(f"Column '{midpoint_col}' not found in DataFrame.")
    if not pd.api.types.is_numeric_dtype(out[midpoint_col]):
        raise ValueError(f"'{midpoint_col}' must be numeric decimal hours (−12..+12 from noon).")

    hours = out[midpoint_col].astype(float).to_numpy()
    theta = hours * (2.0 * np.pi / 24.0)  # noon -> 0 rad, domain (−π, π]

    valid_mask = ~np.isnan(theta)
    valid_theta = theta[valid_mask]
    if valid_theta.size == 0:
        raise ValueError("No non-missing midpoints found.")

    mean_angle  = _circular_mean(valid_theta)
    median_angle = _circular_median(valid_theta)

    d_mean = np.full(theta.shape, np.nan)
    d_mean[valid_mask] = _angle_diff(theta[valid_mask], mean_angle)

    d_adj = np.full(theta.shape, np.nan)
    valid_idx = np.where(valid_mask)[0]
    if valid_idx.size > 1:
        d_adj[valid_idx[1:]] = _angle_diff(valid_theta[1:], valid_theta[:-1])

    out["cpd_hours"] = np.sqrt(d_mean**2 + d_adj**2) * (24.0 / (2.0 * np.pi))
    out["mean_midpoint_hours"]   = mean_angle  * (24.0 / (2.0 * np.pi))
    out["median_midpoint_hours"] = median_angle * (24.0 / (2.0 * np.pi))
    return out

# ---------- preprocessing for your current input shape ----------
def build_centered_midpoint_hours(df: pd.DataFrame,
                                  date_col="mid_sleep_DATE",
                                  time_col="Mid_sleep_Time",
                                  out_mid_col="midpoint_hours_centered",
                                  out_dt_col="mid_sleep_dt"):
    """
    Creates:
      - out_dt_col: combined datetime of mid sleep
      - out_mid_col: 12-hour centered midpoint hours (−12..+12 from local noon)
    """
    if df.empty:
        out = df.copy()
        out[out_dt_col] = pd.NaT
        out[out_mid_col] = np.nan
        return out

    # Combine date & time into a single datetime (naive = local)
    dt = pd.to_datetime(df[date_col].astype(str) + " " + df[time_col].astype(str), errors="coerce")
    if dt.isna().all():
        raise ValueError("Could not parse mid sleep date/time; check formats.")
    out = df.copy()
    out[out_dt_col] = dt

    # Local noon of that date
    noon = dt.dt.normalize() + pd.Timedelta(hours=12)

    # Difference in hours from noon, wrapped into (−12, +12]
    delta_hours = (dt - noon).dt.total_seconds() / 3600.0
    centered = ((delta_hours + 12) % 24) - 12  # wrap

    out[out_mid_col] = centered.astype(float)
    return out

