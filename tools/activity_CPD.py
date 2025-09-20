import pandas as pd
import numpy as np
import pycircstat as circ  # pip install pycircstat

def calculate_cpd_activity(
    df: pd.DataFrame,
    ms_col: str = "d_ms",
    date_col: str | None = "d_date",
) -> pd.DataFrame:
    """
    Composite Phase Deviation (CPD) from decimal mid-sleep (or acrophase) times
    for a single person (no id grouping).

    Parameters
    ----------
    df : pandas.DataFrame
        Must contain `ms_col` and optionally `date_col`.
    ms_col : str, default "d_ms"
        Mid-sleep/acrophase in decimal hours (0–24).
    date_col : str or None, default "d_date"
        If provided and present in df, used to sort chronologically so the
        deviation-from-previous-night term makes sense.

    Returns
    -------
    pandas.DataFrame
        Same rows as input plus:
        * mean_midpoint_hours
        * median_midpoint_hours
        * deviation_from_mean_hours
        * deviation_from_prev_hours
        * cpd_hours
    """
    out = df.copy()

    # Sort by date if available
    if date_col and (date_col in out.columns):
        out[date_col] = pd.to_datetime(out[date_col])
        out = out.sort_values(date_col).reset_index(drop=True)

    two_pi_over_24 = 2 * np.pi / 24.0

    # Core data
    midpoint_hours = out[ms_col].astype(float).values
    midpoint_radians = midpoint_hours * two_pi_over_24
    valid = ~np.isnan(midpoint_radians)

    if valid.sum() == 0:
        mean_midpoint_hours = np.nan
        median_midpoint_hours = np.nan
        deviation_from_mean_hours = np.full(len(out), np.nan)
        deviation_from_prev_hours = np.full(len(out), np.nan)
        cpd_hours = np.full(len(out), np.nan)
    else:
        # Circular mean & median using only valid values
        mean_angle = circ.mean(midpoint_radians[valid])
        median_angle = circ.median(midpoint_radians[valid])

        mean_midpoint_hours = np.mod(mean_angle / two_pi_over_24, 24)
        median_midpoint_hours = np.mod(median_angle / two_pi_over_24, 24)

        # Deviations (works with NaNs; invalid positions will become NaN)
        deviation_from_mean = circ.cdiff(midpoint_radians, mean_angle)

        prev = midpoint_radians[:-1]
        curr = midpoint_radians[1:]
        dev_prev_vec = np.full(len(out) - 1, np.nan)
        mask_pair = ~np.isnan(curr) & ~np.isnan(prev)
        dev_prev_vec[mask_pair] = circ.cdiff(curr[mask_pair], prev[mask_pair])
        deviation_from_prev = np.concatenate(([np.nan], dev_prev_vec))

        deviation_from_mean_hours = deviation_from_mean / two_pi_over_24
        deviation_from_prev_hours = deviation_from_prev / two_pi_over_24

        # CPD
        cpd = np.sqrt(deviation_from_mean ** 2 + deviation_from_prev ** 2)
        cpd_hours = cpd / two_pi_over_24

    # Attach to rows (broadcast mean/median scalars)
    out["mean_midpoint_hours"] = mean_midpoint_hours
    out["median_midpoint_hours"] = median_midpoint_hours
    out["deviation_from_mean_hours"] = deviation_from_mean_hours
    out["deviation_from_prev_hours"] = deviation_from_prev_hours
    out["cpd_hours"] = cpd_hours

    # Build the return columns list, including the date column if it exists
    return_cols = ['mean_midpoint_hours', 'median_midpoint_hours', 'deviation_from_mean_hours', 'deviation_from_prev_hours', 'cpd_hours']
    if date_col and date_col in out.columns:
        return_cols.insert(0, date_col)
    # Also include the original mid-sleep/acrophase column for reference
    if ms_col in out.columns:
        return_cols.insert(-1, ms_col)  # Insert before cpd_hours
    
    return out[return_cols]
