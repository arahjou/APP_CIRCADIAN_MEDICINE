
def analyze_sleep_light_exposure(df_subset):
    import pandas as pd
    import numpy as np
    """
    Analyzes time-series data to calculate sleep and light exposure metrics.

    This function performs the following steps:
    1.  Calculates sleep state based on a rolling average of 'PIMn'.
    2.  Defines lighting conditions based on a rolling average of 'MELANOPIC EDI'.
    3.  Cleans the data by filling short (< 2 hour) wake periods within sleep.
    4.  Binarizes 3-hour time windows around primary sleep/wake events.
    5.  Prints a final report of key metrics, grouped by date.

    Args:
        df_subset (pd.DataFrame): The input DataFrame. Must contain 'DATE/TIME',
                                  'PIMn', and 'MELANOPIC EDI' columns.
    """
    # Best practice: Work on a copy to avoid modifying the original DataFrame
    df = df_subset.copy()

    # =========================================================================
    # 2. FEATURE ENGINEERING
    # =========================================================================
    print("Step 2: Performing feature engineering...")
    if 'SLEEP_STATE' in df.columns:
        # Use the corrected sleep labels from the editor when provided.
        df['Sleep_State'] = pd.to_numeric(df['SLEEP_STATE'], errors='coerce').fillna(0).clip(0, 1).astype(int)
    else:
        # Fallback to activity-derived state estimation.
        df['PIMn_avg'] = df['PIMn'].rolling(window=100, min_periods=1).mean()
        df['Sleep_State'] = np.where(df['PIMn_avg'] < 6, 1, 0)

    df['MELANOPIC EDI_avg'] = df['MELANOPIC EDI'].rolling(window=50, min_periods=1).mean()
    conditions = [
        df['MELANOPIC EDI_avg'] < 1,
        (df['MELANOPIC EDI_avg'] >= 1) & (df['MELANOPIC EDI_avg'] < 10),
        (df['MELANOPIC EDI_avg'] >= 10) & (df['MELANOPIC EDI_avg'] < 250),
        df['MELANOPIC EDI_avg'] >= 250
    ]
    values = [0, 1, 2, 3]
    df['lighting_condition'] = np.select(conditions, values)

    # =========================================================================
    # 2.5. DATA CLEANING: Fill Short Gaps in Sleep
    # =========================================================================
    print("Step 2.5: Searching for and filling short gaps in sleep periods...")
    df = df.sort_values("DATE/TIME").reset_index(drop=True)
    initial_transitions = df['Sleep_State'].diff()
    wake_up_indices = initial_transitions[initial_transitions == -1].index
    sleep_onset_indices = initial_transitions[initial_transitions == 1].index

    for wake_idx in wake_up_indices:
        next_sleep_onsets = sleep_onset_indices[sleep_onset_indices > wake_idx]
        if not next_sleep_onsets.empty:
            next_sleep_idx = next_sleep_onsets[0]
            wake_time = df.loc[wake_idx, 'DATE/TIME']
            next_sleep_time = df.loc[next_sleep_idx, 'DATE/TIME']
            duration = next_sleep_time - wake_time
            if duration < pd.Timedelta(hours=2):
                print(f"  -> Found and filled a sleep gap of {duration} starting at {wake_time.strftime('%Y-%m-%d %H:%M')}")
                df.loc[wake_idx:next_sleep_idx-1, 'Sleep_State'] = 1

    # =========================================================================
    # 3. TIME WINDOW BINARIZATION
    # =========================================================================
    print("Step 3: Binarizing time windows around sleep/wake transitions...")
    df = df.sort_values("DATE/TIME").reset_index(drop=True)
    df['sleep_transition'] = df['Sleep_State'].diff()

    # Binarize 3 hours BEFORE WAKE-UP
    wake_up_times = df[df['sleep_transition'] == -1]['DATE/TIME']
    df['3_hours_before_wake'] = 0
    for wake_time in wake_up_times:
        start_window = wake_time - pd.Timedelta(hours=3)
        mask = (df['DATE/TIME'] >= start_window) & (df['DATE/TIME'] < wake_time)
        df.loc[mask, '3_hours_before_wake'] = 1

    # Binarize 3 hours AFTER WAKE-UP
    df['3_hours_after_wakeup'] = 0
    for wake_time in wake_up_times:
        end_window = wake_time + pd.Timedelta(hours=3)
        mask = (df['DATE/TIME'] > wake_time) & (df['DATE/TIME'] <= end_window)
        df.loc[mask, '3_hours_after_wakeup'] = 1
        
    # Binarize 3 hours BEFORE SLEEP
    sleep_onset_times = df[df['sleep_transition'] == 1]['DATE/TIME']
    df['3_hours_before_sleep'] = 0
    for sleep_time in sleep_onset_times:
        start_window = sleep_time - pd.Timedelta(hours=3)
        mask = (df['DATE/TIME'] >= start_window) & (df['DATE/TIME'] < sleep_time)
        df.loc[mask, '3_hours_before_sleep'] = 1

    # =========================================================================
    # 4. ANALYSIS & REPORTING
    # =========================================================================
    print("Step 4: Calculating and reporting key metrics...\n" + "="*50)
    df['DATE'] = df['DATE/TIME'].dt.date

    # Metric 1
    minutes_light_by_date = df[(df['Sleep_State'] == 1) & (df['lighting_condition'] > 0)].groupby('DATE').size()
    print("\nMinutes of light exposure (MELANOPIC EDI > 1 lux) during sleep by date:")
    print(minutes_light_by_date if not minutes_light_by_date.empty else "No light exposure detected during sleep periods.")

    # Metric 2
    minutes_bright_before_sleep_by_date = df[(df['3_hours_before_sleep'] == 1) & (df['lighting_condition'] > 1)].groupby('DATE').size()
    print(f"\nMinutes of bright light (MELANOPIC EDI > 10 lux) in the 3 hours before sleep by date:")
    print(minutes_bright_before_sleep_by_date if not minutes_bright_before_sleep_by_date.empty else "No bright light exposure detected in the 3 hours before sleep.")

    # Metric 3
    minutes_not_bright_after_wake_by_date = df[(df['3_hours_after_wakeup'] == 1) & (df['lighting_condition'] < 3)].groupby('DATE').size()
    print(f"\nMinutes of non-bright light (MELANOPIC EDI < 250 lux) in the 3 hours after waking up by date:")
    print(minutes_not_bright_after_wake_by_date if not minutes_not_bright_after_wake_by_date.empty else "No non-bright light exposure detected in the 3 hours after waking up.")
    
    print("="*50 + "\nScript finished.")
    
    # Prepare results to return for web app display - convert pandas Series to JSON-serializable format
    results = {}
    
    # Convert pandas Series to list of dictionaries for database storage
    if not minutes_light_by_date.empty:
        results['metric1'] = [{'date': str(date), 'minutes': int(minutes)} for date, minutes in minutes_light_by_date.items()]
    else:
        results['metric1'] = "No light exposure detected during sleep periods."
    
    if not minutes_bright_before_sleep_by_date.empty:
        results['metric2'] = [{'date': str(date), 'minutes': int(minutes)} for date, minutes in minutes_bright_before_sleep_by_date.items()]
    else:
        results['metric2'] = "No bright light exposure detected in the 3 hours before sleep."
    
    if not minutes_not_bright_after_wake_by_date.empty:
        results['metric3'] = [{'date': str(date), 'minutes': int(minutes)} for date, minutes in minutes_not_bright_after_wake_by_date.items()]
    else:
        results['metric3'] = "No non-bright light exposure detected in the 3 hours after waking up."
    
    return results
