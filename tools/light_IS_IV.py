import numpy as np
import pandas as pd
def compute_rolling_2day_is_iv_light(
    df: pd.DataFrame,
    time_col: str = "DATE/TIME",
    value_col: str = "MELANOPIC EDI",
    anchor_hour: int = 12
):
    """
    Compute IS and IV for consecutive 2-day windows (rolling analysis).
    
    This function calculates IS and IV for each pair of consecutive days:
    - Day 1-2, Day 2-3, Day 3-4, etc.
    
    Scientific rationale:
    - IS measures consistency between the two days
    - IV measures fragmentation across the 48-hour period
    - Reveals temporal changes in rhythm stability
    - Useful for detecting rhythm disruptions or improvements
    
    Parameters
    ----------
    df : DataFrame
        Input data with datetime and activity columns
    time_col : str
        Name of the datetime column
    value_col : str
        Name of the activity column
    anchor_hour : int
        Hour to anchor day boundaries (e.g., 12 = noon-to-noon)
        
    Returns
    -------
    DataFrame
        Results with columns: [day_pair, start_date, end_date, IS_2day, IV_2day, n_minutes]
    """
    
    # Prepare data
    df = df.copy()
    df[time_col] = pd.to_datetime(df[time_col], errors="coerce")
    df = df.dropna(subset=[time_col]).sort_values(time_col).set_index(time_col)
    
    if df.empty or value_col not in df:
        return pd.DataFrame(columns=["day_pair", "start_date", "end_date", "IS_2day", "IV_2day", "n_minutes"])
    
    # Create 1-minute grid
    full_idx = pd.date_range(df.index.min(), df.index.max(), freq="1min", tz=df.index.tz)
    x = df.reindex(full_idx)[value_col]
    
    # Define anchored days
    anchored_day_id = (
        (x.index - pd.Timedelta(hours=anchor_hour)).normalize()
        + pd.Timedelta(hours=anchor_hour)
    )
    
    unique_days = sorted(anchored_day_id.unique())
    
    if len(unique_days) < 2:
        return pd.DataFrame(columns=["day_pair", "start_date", "end_date", "IS_2day", "IV_2day", "n_minutes"])
    
    results = []
    
    # Calculate for each consecutive 2-day pair
    for i in range(len(unique_days) - 1):
        day1 = unique_days[i]
        day2 = unique_days[i + 1]
        
        # Extract 2-day data
        mask = (anchored_day_id == day1) | (anchored_day_id == day2)
        x_2day = x[mask]
        
        if len(x_2day) < 120:  # Need at least 2 hours of data
            results.append({
                'day_pair': f"{day1.date()} to {day2.date()}",
                'start_date': day1.date(),
                'end_date': day2.date(),
                'IS_2day': np.nan,
                'IV_2day': np.nan,
                'n_minutes': len(x_2day)
            })
            continue
        
        # Calculate IS for the 2-day period
        mu_2day = x_2day.mean(skipna=True)
        N_valid_2day = int(x_2day.notna().sum())
        den_2day = ((x_2day - mu_2day) ** 2).sum(skipna=True)
        
        if den_2day == 0 or np.isnan(den_2day) or N_valid_2day == 0:
            IS_2day = np.nan
        else:
            # Calculate hourly means across the 2-day period
            hourly_means_2day = x_2day.groupby(x_2day.index.hour).mean()
            # IS: variance explained by 24h cycle / total variance
            IS_2day = (N_valid_2day * ((hourly_means_2day - mu_2day) ** 2).sum(skipna=True)) / (24 * den_2day)
        
        # Calculate IV for the 2-day period
        x_2day_shifted = x_2day.shift(1)
        valid_pairs_mask_2day = x_2day.notna() & x_2day_shifted.notna()
        num_2day = ((x_2day[valid_pairs_mask_2day] - x_2day_shifted[valid_pairs_mask_2day]) ** 2).sum()
        pairs_2day = int(valid_pairs_mask_2day.sum())
        
        if den_2day == 0 or np.isnan(den_2day) or pairs_2day == 0 or N_valid_2day <= 1:
            IV_2day = np.nan
        else:
            # IV: first-difference variance / total variance
            IV_2day = (N_valid_2day * num_2day) / (pairs_2day * den_2day)
        
        results.append({
            'day_pair': f"{day1.date()} to {day2.date()}",
            'start_date': day1.date(),
            'end_date': day2.date(),
            'IS_2day': float(IS_2day) if pd.notna(IS_2day) else np.nan,
            'IV_2day': float(IV_2day) if pd.notna(IV_2day) else np.nan,
            'n_minutes': len(x_2day)
        })
    
    return pd.DataFrame(results)
