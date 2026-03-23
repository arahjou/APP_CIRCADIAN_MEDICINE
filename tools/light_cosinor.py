import numpy as np
import pandas as pd
from scipy.optimize import curve_fit
from datetime import datetime

# This function remains the same
def cosinor_function(t, mesor, amplitude, acrophase):
    """
    Cosinor function: y = mesor + amplitude * cos(2π * t/24 - acrophase)
    """
    return mesor + amplitude * np.cos(2 * np.pi * t / 24 - acrophase)

# --- MODIFIED FUNCTION ---
def fit_cosinor_daily_activity(df, datetime_col='DATE/TIME', value_col='MELANOPIC EDI'):
    """
    Fits a cosinor model for each day in the dataframe from a single datetime column.
    
    Returns a dataframe with daily cosinor parameters.
    """
    results = []
    
    # Create a copy to avoid SettingWithCopyWarning
    df_copy = df.copy()
    
    # Ensure the datetime column is in the correct format
    df_copy[datetime_col] = pd.to_datetime(df_copy[datetime_col])
    
    # Group by the date part of the datetime column
    for date, day_data in df_copy.groupby(df_copy[datetime_col].dt.date):
        if len(day_data) < 10:  # Skip days with too few measurements
            continue
            
        # --- NEW: Vectorized time conversion ---
        # Convert time to a fractional hour of the day directly from the datetime column
        times_hours = (day_data[datetime_col].dt.hour + 
                       day_data[datetime_col].dt.minute / 60 + 
                       day_data[datetime_col].dt.second / 3600).values
        
        values = day_data[value_col].values
        
        # Remove any NaN values from the data
        mask = ~np.isnan(values)
        if mask.sum() < 10:  # Skip if too few valid measurements
            continue
            
        times_clean = times_hours[mask]
        values_clean = values[mask]
        
        try:
            # Initial parameter estimates
            mesor_init = np.mean(values_clean)
            amplitude_init = (np.max(values_clean) - np.min(values_clean)) / 2
            acrophase_init = 0  # Start with phase 0
            
            # Fit the cosinor model
            popt, pcov = curve_fit(
                cosinor_function, 
                times_clean, 
                values_clean,
                p0=[mesor_init, amplitude_init, acrophase_init],
                bounds=(
                    [-np.inf, 0, -2*np.pi],  # Lower bounds
                    [np.inf, np.inf, 2*np.pi]  # Upper bounds
                ),
                maxfev=2000
            )
            
            mesor, amplitude, acrophase = popt
            
            # Calculate R-squared
            y_pred = cosinor_function(times_clean, *popt)
            ss_res = np.sum((values_clean - y_pred) ** 2)
            ss_tot = np.sum((values_clean - np.mean(values_clean)) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
            
            # Convert acrophase to hours (peak time)
            acrophase_hours = (acrophase * 24 / (2 * np.pi)) % 24
            
            results.append({
                'date': date,
                'mesor': mesor,
                'amplitude': amplitude,
                'acrophase_radians': acrophase,
                'acrophase_hours': acrophase_hours,
                'r_squared': r_squared,
                'n_measurements': len(values_clean)
            })
            
        except Exception as e:
            print(f"Failed to fit cosinor for date {date}: {e}")
            continue
    
    return pd.DataFrame(results)