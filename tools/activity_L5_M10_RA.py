
import pandas as pd
import numpy as np
def compute_daily_L5_M10_RA_activity(
    df: pd.DataFrame,
    time_col: str = "DATE/TIME",
    value_col: str = "PIMn", 
    anchor_hour: int = 12,
    allow_missing_frac: float = 0.10
):
    """
    Compute daily L5, M10, and RA from actigraphy data.
    
    This is a streamlined function that calculates only the daily activity metrics:
    - L5: Average activity during the least active 5-hour window
    - M10: Average activity during the most active 10-hour window  
    - RA: Relative Amplitude = (M10 - L5) / (M10 + L5)
    
    Parameters
    ----------
    df : DataFrame
        Input data with datetime and activity columns
    time_col : str
        Name of the datetime column
    value_col : str
        Name of the activity column (1-min data)
    anchor_hour : int
        Hour to anchor day boundaries (e.g., 12 = noon-to-noon days)
    allow_missing_frac : float
        Fraction of missing data allowed within rolling windows (0.10 = 10%)
        
    Returns
    -------
    DataFrame
        Daily results with columns: [date, M10_start, M10_mean, L5_start, L5_mean, RA]
    """
    
    # --- Data Preparation ---
    df = df.copy()
    df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
    df = df.dropna(subset=[time_col]).sort_values(time_col).set_index(time_col)
    
    if df.empty or value_col not in df:
        return pd.DataFrame(columns=["date", "M10_start", "M10_mean", "L5_start", "L5_mean", "RA"])
    
    # Create 1-minute grid
    full_idx = pd.date_range(df.index.min(), df.index.max(), freq="1min", tz=df.index.tz)
    x = df.reindex(full_idx)[value_col]
    
    if x.size < 2 or x.notna().sum() == 0:
        return pd.DataFrame(columns=["date", "M10_start", "M10_mean", "L5_start", "L5_mean", "RA"])
    
    # --- Define Day Boundaries ---
    anchored_day_id = (
        (x.index - pd.Timedelta(hours=anchor_hour)).normalize()
        + pd.Timedelta(hours=anchor_hour)
    )
    
    # --- Window Parameters ---
    win10, win5 = 600, 300  # 10 hours, 5 hours in minutes
    minp10 = int(np.ceil((1 - allow_missing_frac) * win10))  # Minimum valid points for M10
    minp5 = int(np.ceil((1 - allow_missing_frac) * win5))    # Minimum valid points for L5
    
    def wrap_to_first_day(ts, day_start):
        """Ensure start times are within the correct anchored day."""
        if pd.isna(ts):
            return ts
        if ts >= day_start + pd.Timedelta(days=1):
            return ts - pd.Timedelta(days=1)
        return ts
    
    def calculate_l5_m10_for_day(s: pd.Series) -> pd.Series:
        """Calculate L5 and M10 for a single day."""
        s = s.asfreq("1min")
        
        if s.empty or s.isna().all() or len(s) < win10:
            return pd.Series({
                "M10_start": pd.NaT, "M10_mean": np.nan, 
                "L5_start": pd.NaT, "L5_mean": np.nan
            })
        
        day_start = s.index[0]
        
        # Extend series to handle wrap-around windows
        extended_index = pd.date_range(s.index[0], periods=len(s)*2, freq='1min')
        ss = pd.concat([s, s])
        ss.index = extended_index
        
        # Calculate rolling means
        r10_mean = ss.rolling(win10, min_periods=minp10).mean()
        r5_mean = ss.rolling(win5, min_periods=minp5).mean()
        
        # Get candidate windows (those that start within the day)
        end10_start = win10 - 1
        end5_start = win5 - 1
        max_candidates = min(len(s), len(r10_mean) - end10_start)
        
        if max_candidates <= 0:
            return pd.Series({
                "M10_start": pd.NaT, "M10_mean": np.nan,
                "L5_start": pd.NaT, "L5_mean": np.nan
            })
        
        r10_candidates = r10_mean.iloc[end10_start : end10_start + max_candidates]
        r5_candidates = r5_mean.iloc[end5_start : end5_start + max_candidates]
        
        # Find M10 (maximum 10-hour window)
        if r10_candidates.notna().any():
            best_end10_ts = r10_candidates.idxmax()
            M10_mean = r10_candidates.loc[best_end10_ts]
            M10_start = best_end10_ts - pd.Timedelta(minutes=win10 - 1)
            M10_start = wrap_to_first_day(M10_start, day_start)
        else:
            M10_start, M10_mean = pd.NaT, np.nan
        
        # Find L5 (minimum 5-hour window)
        if r5_candidates.notna().any():
            best_end5_ts = r5_candidates.idxmin()
            L5_mean = r5_candidates.loc[best_end5_ts]
            L5_start = best_end5_ts - pd.Timedelta(minutes=win5 - 1)
            L5_start = wrap_to_first_day(L5_start, day_start)
        else:
            L5_start, L5_mean = pd.NaT, np.nan
        
        return pd.Series({
            "M10_start": M10_start, "M10_mean": M10_mean,
            "L5_start": L5_start, "L5_mean": L5_mean
        })
    
    # --- Apply to Each Day ---
    daily_series = x.groupby(anchored_day_id).apply(calculate_l5_m10_for_day)
    
    # Convert to DataFrame
    if isinstance(daily_series, pd.Series):
        daily = daily_series.unstack(level=-1)
    else:
        daily = daily_series
    
    # --- Calculate Relative Amplitude ---
    if not daily.empty and {"M10_mean", "L5_mean"}.issubset(daily.columns):
        m10 = daily["M10_mean"]
        l5 = daily["L5_mean"]
        daily["RA"] = np.divide(m10 - l5, m10 + l5).where((m10 + l5) != 0, np.nan)
    else:
        daily["RA"] = np.nan
    
    # --- Format Results ---
    daily = daily.reindex(columns=["M10_start", "M10_mean", "L5_start", "L5_mean", "RA"])
    
    # Add date column and reset index
    daily = daily.reset_index()
    daily.rename(columns={daily.columns[0]: 'date'}, inplace=True)
    daily['date'] = daily['date'].dt.date  # Convert to date only
    
    return daily